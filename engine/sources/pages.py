"""Website pages: new URLs in a sitemap, help-center articles tracked by their lastmod, and
changes to the text of a single page."""

from __future__ import annotations

import json
import re
from datetime import timedelta
from urllib.parse import urlsplit

from ..config import LOCALE_SEGMENT, MAX_AGE_DAYS, MAX_PAGES_PER_SITE, Source
from ..diffing import content_hash, describe_change, is_format_only
from ..items import Item, stable_id
from . import Context, SourceError, SourceResult
from .docs_site import compare_page, new_stats, page_key, removed_items, title_of
from .htmltext import page_meta, parse_datetime, soup, to_markdown

BLOCK = re.compile(r"<(url|sitemap)>(.*?)</\1>", re.DOTALL)
LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")
LASTMOD = re.compile(r"<lastmod>\s*([^<\s]+)\s*</lastmod>")
MAX_NEW_PAGES_PER_RUN = 30


def read_sitemap(ctx: Context, url: str, children: list[str] | None = None, depth: int = 0) -> dict[str, str | None]:
    """URL -> lastmod. Follows a sitemap index one level down (only into the children whose
    URL contains one of `children`, when given)."""
    page = ctx.fetcher.get(url)
    if not page.ok:
        raise SourceError(f"{url}: {page.error}")
    entries: dict[str, str | None] = {}
    nested: list[str] = []
    for tag, body in BLOCK.findall(page.text):
        loc = LOC.search(body)
        if not loc:
            continue
        if tag == "sitemap":
            nested.append(loc.group(1))
        else:
            lastmod = LASTMOD.search(body)
            entries[loc.group(1)] = lastmod.group(1) if lastmod else None
    if nested and depth == 0:
        for child in nested:
            if children and not any(c in child for c in children):
                continue
            entries.update(read_sitemap(ctx, child, None, depth + 1))
    return entries


def _wanted(src: Source, url: str) -> bool:
    opts = src.options
    if not url.startswith(opts.get("include_prefix", opts["host"])):
        return False
    if url.rstrip("/") == opts.get("include_prefix", opts["host"]).rstrip("/"):
        return False
    if any(url.startswith(p) for p in opts.get("exclude_prefix", [])):
        return False
    words = opts.get("require_in_url")
    if words and not any(w in url.lower() for w in words):
        return False
    return not LOCALE_SEGMENT.search(urlsplit(url).path)


def _slug_title(url: str) -> str:
    path = urlsplit(url).path.strip("/")
    return path.replace("-", " ").replace("/", " / ") or url


def fetch_sitemap_new(src: Source, ctx: Context) -> SourceResult:
    """New pages on a site. Options: host, include_prefix, exclude_prefix, require_in_url,
    children (which sitemaps of an index to read), fetch_pages (False when the site blocks
    page fetches: the title then comes from the address)."""
    urls = {u: lm for u, lm in read_sitemap(ctx, src.url, src.options.get("children")).items() if _wanted(src, u)}
    if not urls:
        raise SourceError(f"{src.url}: no URLs matched")
    fetch_pages = src.options.get("fetch_pages", True)

    old = ctx.snapshots.read(src.name, "urls.txt")
    baseline = old is None
    cutoff = ctx.now - timedelta(days=MAX_AGE_DAYS)
    if baseline and fetch_pages:
        # First read: the sitemap is history, except pages it says changed this week, which
        # are reported if they were also published this week. lastmod moves on site rebuilds,
        # so take only the most recently modified few.
        recent = [(d, u) for u, lm in urls.items() if (d := parse_datetime(lm)) and d >= cutoff]
        candidates = [u for _, u in sorted(recent, reverse=True)[:MAX_NEW_PAGES_PER_RUN]]
    elif baseline:
        candidates = []
    else:
        candidates = sorted(set(urls) - set(old.split()))

    res = SourceResult()
    stats = {"urls": len(urls), "baseline": baseline, "candidates": len(candidates), "new": 0}
    overflow = [] if baseline else candidates[MAX_NEW_PAGES_PER_RUN:]
    batch = candidates[:MAX_NEW_PAGES_PER_RUN]
    pages = ctx.fetcher.get_many(batch) if fetch_pages else {}
    for url in batch:
        page = pages.get(url)
        if page is not None and page.ok:
            meta = page_meta(page.text)
        else:
            meta = {"title": "", "description": "", "published": None, "text": ""}
        if baseline and not (meta["published"] and meta["published"] >= cutoff):
            continue
        title = meta["title"] or _slug_title(url)
        if fetch_pages:
            body = "\n\n".join(x for x in (meta["description"], meta["text"]) if x) or "(page could not be read)"
        else:
            body = f"New page at {url} (the site blocks automated reads, so only its address is known)."
        stats["new"] += 1
        res.items.append(Item(
            id=stable_id("url", src.name, url), source=src.name, kind="new_url",
            title=f"{src.label}: {title}", url=url, body=body,
            published_at=meta["published"] or parse_datetime(urls.get(url)) or ctx.now,
            metadata={"path": urlsplit(url).path, "fetch_error": page.error if page else None},
        ))
    if overflow:
        stats["overflow"] = len(overflow)
        res.items.append(Item(
            id=stable_id("rollup", src.name, *overflow), source=src.name, kind="rollup",
            title=f"{src.label}: {len(overflow)} more new pages", url=src.options["host"],
            body="\n".join(f"- {u}" for u in overflow[:200]), published_at=ctx.now,
            metadata={"count": len(overflow)},
        ))
    snapshot = "\n".join(sorted(urls)) + "\n"
    if snapshot != old:
        res.writes["urls.txt"] = snapshot
    res.stats = stats
    return res


def fetch_sitemap_docs(src: Source, ctx: Context) -> SourceResult:
    """Articles listed in a sitemap whose lastmod is reliable (a help center): only articles
    that are new or whose lastmod moved are fetched, as Markdown twins, and diffed.
    Options: include_prefix, exclude, crawl_delay (seconds between requests)."""
    host = urlsplit(src.url).hostname or ""
    if src.options.get("crawl_delay"):
        ctx.fetcher.pace(host, src.options["crawl_delay"])
    prefix = src.options["include_prefix"]
    exclude = set(src.options.get("exclude", []))
    urls = {u: lm for u, lm in read_sitemap(ctx, src.url).items()
            if u.startswith(prefix) and u not in exclude and not LOCALE_SEGMENT.search(urlsplit(u).path)}
    if not urls:
        raise SourceError(f"{src.url}: no URLs under {prefix}")

    key = "_lastmod.json"
    old_raw = ctx.snapshots.read(src.name, key)
    baseline = old_raw is None
    known: dict[str, str | None] = json.loads(old_raw) if old_raw else {}
    todo = [u for u in sorted(urls) if baseline or u not in known or urls[u] != known[u]][:MAX_PAGES_PER_SITE]
    fetched = ctx.fetcher.get_many([u + ".md" for u in todo])

    res = SourceResult()
    stats = new_stats(baseline, len(urls))
    stats["to_check"] = len(todo)
    previous = {page_key(u + ".md") for u in known}
    seen = dict(known)
    for url in todo:
        page = fetched[url + ".md"]
        compare_page(src, ctx, res, stats, url + ".md", None, page, previous, baseline,
                     published=parse_datetime(urls[url]))
        if page.ok:
            seen[url] = urls[url]  # a failed fetch keeps the old lastmod, so it is retried
    gone = set(known) - set(urls)
    if gone and len(urls) >= len(known) / 2:
        removed_items(src, ctx, res, stats, {page_key(u + ".md") for u in gone}, f"https://{host}")
        for u in gone:
            seen.pop(u, None)
    text = json.dumps(seen, indent=0, sort_keys=True) + "\n"
    if text != old_raw:
        res.writes[key] = text
    res.stats = stats
    return res


def fetch_page_text(src: Source, ctx: Context) -> SourceResult:
    """One page's visible text, compared with the last run's copy."""
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


def index_links(html: str, page_url: str, prefix: str) -> list[str]:
    """Absolute URLs of the links on a page whose path is `prefix` plus one slug."""
    parts = urlsplit(page_url)
    found = re.findall(r'href="(?:https?://[^/"]+)?(' + re.escape(prefix) + r'[a-z0-9-]+)"', html)
    return sorted({f"{parts.scheme}://{parts.hostname}{path}" for path in found})


def fetch_page_set_text(src: Source, ctx: Context) -> SourceResult:
    """Edits to a set of HTML guide pages, by comparing their article text with the last run's
    copy. New pages are only recorded: the site's sitemap source reports those.
    Options: sitemap + include_prefix, or index_page + link_prefix (links found on that page);
    selector: "article" or "main" (the element holding the page's own text)."""
    opts = src.options
    if opts.get("index_page"):
        index = ctx.fetcher.get(opts["index_page"])
        if not index.ok:
            raise SourceError(f"{opts['index_page']}: {index.error}")
        urls = index_links(index.text, opts["index_page"], opts["link_prefix"])
    else:
        urls = sorted(u for u in read_sitemap(ctx, opts["sitemap"])
                      if u.startswith(opts["include_prefix"]) and not LOCALE_SEGMENT.search(urlsplit(u).path))
    if not urls:
        raise SourceError(f"{src.url}: no pages found")
    urls = urls[:MAX_PAGES_PER_SITE]
    fetched = ctx.fetcher.get_many(urls)

    res = SourceResult()
    stats = {"pages": len(urls), "fetched": 0, "errors": 0, "recorded": 0, "changed": 0, "unchanged": 0}
    for url in urls:
        page = fetched[url]
        node = None
        if page.ok:
            doc = soup(page.text)
            node = doc.find(opts.get("selector", "main")) or doc.find("main")
        if node is None:
            stats["errors"] += 1
            continue
        stats["fetched"] += 1
        new = to_markdown(node)
        key = urlsplit(url).path.strip("/") + ".md"
        old = ctx.snapshots.read(src.name, key)
        if old == new:
            stats["unchanged"] += 1
            continue
        res.writes[key] = new
        if old is None:
            stats["recorded"] += 1
            continue
        stats["changed"] += 1
        title = re.sub(r"[*_]", "", title_of(new, key))
        diff, counts = describe_change(old, new)
        res.items.append(Item(
            id=stable_id("chg", src.name, key, content_hash(old), content_hash(new)), source=src.name,
            kind="changed_page", title=f'{src.label}: "{title}" changed', url=url, body=diff,
            published_at=ctx.now,
            metadata=dict(counts, page_title=title, format_only=is_format_only(old, new), snapshot=f"{src.name}/{key}"),
        ))
    res.stats = stats
    return res
