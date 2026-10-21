"""Website pages: new URLs in a sitemap, and changes to the text of a single page."""

from __future__ import annotations

import re
from datetime import timedelta
from urllib.parse import urlsplit

from ..config import LOCALE_SEGMENT, MAX_AGE_DAYS, Source
from ..diffing import content_hash, describe_change, is_format_only
from ..items import Item, stable_id
from . import Context, SourceError, SourceResult
from .htmltext import page_meta, parse_datetime, soup, to_markdown

LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>(?:\s*<lastmod>\s*([^<\s]+)\s*</lastmod>)?")
MAX_NEW_PAGES_PER_RUN = 30


def read_sitemap(ctx: Context, url: str, depth: int = 0) -> dict[str, str | None]:
    """URL -> lastmod, following a sitemap index one level down."""
    page = ctx.fetcher.get(url)
    if not page.ok:
        raise SourceError(f"{url}: {page.error}")
    found = dict(LOC.findall(page.text))
    if "<sitemapindex" in page.text[:500] and depth == 0:
        merged: dict[str, str | None] = {}
        for child in found:
            merged.update(read_sitemap(ctx, child, depth + 1))
        return merged
    return {u: (lm or None) for u, lm in found.items()}


def fetch_sitemap_new(src: Source, ctx: Context) -> SourceResult:
    host = src.options["host"]
    prefix = src.options.get("include_prefix", host)
    urls = {
        u: lm for u, lm in read_sitemap(ctx, src.url).items()
        if u.startswith(prefix) and u.rstrip("/") != prefix.rstrip("/")
        and not LOCALE_SEGMENT.search(urlsplit(u).path)
    }
    if not urls:
        raise SourceError(f"{src.url}: no URLs under {prefix}")

    old = ctx.snapshots.read(src.name, "urls.txt")
    baseline = old is None
    cutoff = ctx.now - timedelta(days=MAX_AGE_DAYS)
    if baseline:
        # First read: the sitemap is history, except pages it says changed this week,
        # which are reported if they were also published this week.
        # lastmod moves on site rebuilds, so take only the most recently modified few.
        recent = [(d, u) for u, lm in urls.items() if (d := parse_datetime(lm)) and d >= cutoff]
        candidates = [u for _, u in sorted(recent, reverse=True)[:MAX_NEW_PAGES_PER_RUN]]
    else:
        candidates = sorted(set(urls) - set(old.split()))

    res = SourceResult()
    stats = {"urls": len(urls), "baseline": baseline, "candidates": len(candidates), "new": 0}
    overflow = [] if baseline else candidates[MAX_NEW_PAGES_PER_RUN:]
    pages = ctx.fetcher.get_many(candidates[:MAX_NEW_PAGES_PER_RUN])
    for url, page in pages.items():
        meta = page_meta(page.text) if page.ok else {"title": "", "description": "", "published": None, "text": ""}
        if baseline and not (meta["published"] and meta["published"] >= cutoff):
            continue
        title = meta["title"] or urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")
        body = "\n\n".join(x for x in (meta["description"], meta["text"]) if x) or "(page could not be read)"
        stats["new"] += 1
        res.items.append(Item(
            id=stable_id("url", src.name, url), source=src.name, kind="new_url",
            title=f"{src.label}: {title}", url=url, body=body,
            published_at=meta["published"] or ctx.now,
            metadata={"path": urlsplit(url).path, "fetch_error": page.error},
        ))
    if overflow:
        stats["overflow"] = len(overflow)
        res.items.append(Item(
            id=stable_id("rollup", src.name, *overflow), source=src.name, kind="rollup",
            title=f"{src.label}: {len(overflow)} more new pages", url=host,
            body="\n".join(f"- {u}" for u in overflow[:200]), published_at=ctx.now,
            metadata={"count": len(overflow)},
        ))
    snapshot = "\n".join(sorted(urls)) + "\n"
    if snapshot != old:
        res.writes["urls.txt"] = snapshot
    res.stats = stats
    return res


def fetch_page_text(src: Source, ctx: Context) -> SourceResult:
    """One page's visible text, compared with yesterday's copy."""
    page = ctx.fetcher.get(src.url)
    if not page.ok:
        raise SourceError(f"{src.url}: {page.error}")
    doc = soup(page.text)
    main = doc.find("main") or doc.body
    if main is None:
        raise SourceError(f"{src.url}: no page body")
    new = to_markdown(main)
    old = ctx.snapshots.read(src.name, "page.md")
    res = SourceResult(stats={"baseline": old is None, "changed": 0})
    if old == new:
        return res
    res.writes["page.md"] = new
    if old is None:
        return res
    diff, counts = describe_change(old, new)
    res.stats["changed"] = 1
    res.items.append(Item(
        id=stable_id("chg", src.name, content_hash(old), content_hash(new)), source=src.name,
        kind="changed_page", title=f"{src.label}: page changed", url=src.url, body=diff,
        published_at=ctx.now,
        metadata=dict(counts, format_only=is_format_only(old, new), snapshot=f"{src.name}/page.md"),
    ))
    return res
