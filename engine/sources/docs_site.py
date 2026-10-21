"""A docs site that lists its pages in llms.txt and serves each page as Markdown.

Every page is compared with the copy the last run saved: new pages, changed pages and removed
pages become items. The first read of a site only records the starting copy. The page list
itself is kept too (_index.txt), so "new" means new to the index, not just missing a copy
because the last fetch failed.

Options: include_prefix (required), exclude (URLs), require_keyword (only index lines that
mention it), track_links (also report new non-Markdown links in the index, such as videos).
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from ..config import LOCALE_SEGMENT, MAX_ITEMS_PER_SOURCE, MAX_PAGES_PER_SITE, Source
from ..diffing import content_hash, describe_change, is_format_only
from ..http import Page
from ..items import Item, stable_id
from . import Context, SourceError, SourceResult

INDEX_KEY = "_index.txt"
LINKS_KEY = "_links.txt"
INDEX_LINE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)(?::\s*(.*))?")
H1 = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
SIGNED_CDN_URL = re.compile(r"(https://[\w.-]*mintcdn\.com/[^\s)\"'?]*)\?[^\s)\"']*")


def parse_index(
    text: str, include_prefix: str, exclude: list[str], keyword: str | None = None,
) -> tuple[dict[str, str], int, dict[str, tuple[str, str]]]:
    """From an llms.txt: Markdown page URL -> title for English pages under include_prefix,
    how many were skipped as non-English, and the other links (URL -> (title, description))."""
    pages: dict[str, str] = {}
    links: dict[str, tuple[str, str]] = {}
    skipped_lang = 0
    for line in text.splitlines():
        match = INDEX_LINE.search(line)
        if not match:
            continue
        title, url, desc = match.group(1).strip(), match.group(2), (match.group(3) or "").strip()
        if url in exclude or url.endswith(".txt"):  # .txt: other indexes, not pages
            continue
        if keyword and keyword.lower() not in line.lower():
            continue
        if LOCALE_SEGMENT.search(urlsplit(url).path):
            skipped_lang += 1
            continue
        if url.endswith(".md"):
            if url.startswith(include_prefix):
                pages.setdefault(url, title)
        else:
            links.setdefault(url, (title, desc))
    return pages, skipped_lang, links


def clean_page(md: str) -> str:
    """Drop the 'Documentation Index' note every page starts with, and the signatures on CDN
    image links; normalise line endings."""
    lines = md.replace("\r\n", "\n").split("\n")
    if lines and lines[0].startswith(">") and "Documentation Index" in "\n".join(lines[:3]):
        i = 0
        while i < len(lines) and lines[i].startswith(">"):
            i += 1
        lines = lines[i:]
    return SIGNED_CDN_URL.sub(r"\1", "\n".join(lines).strip()) + "\n"


def is_markdown(page: Page) -> bool:
    """Some listed pages redirect to an HTML page; those are not this source's to compare."""
    head = page.text.lstrip()[:200].lower()
    return "html" not in page.content_type and not head.startswith(("<!doctype", "<html"))


def page_key(url: str) -> str:
    return urlsplit(url).path.lstrip("/")


def human_url(md_url: str) -> str:
    return md_url[:-3] if md_url.endswith(".md") else md_url


def title_of(text: str, fallback: str) -> str:
    match = H1.search(text)
    return match.group(1) if match else fallback


def compare_page(
    src: Source, ctx: Context, res: SourceResult, stats: dict, url: str, title: str | None,
    page: Page, previous: set[str], baseline: bool, published=None,
) -> None:
    """Compare one fetched Markdown page with its saved copy; add an item if it is new or changed."""
    key = page_key(url)
    if not page.ok:
        stats["errors"] += 1
        return
    if not is_markdown(page):
        stats["not_markdown"] += 1
        return
    stats["fetched"] += 1
    new = clean_page(page.text)
    old = ctx.snapshots.read(src.name, key)
    if old == new:
        stats["unchanged"] += 1
        return
    res.writes[key] = new
    title = title or title_of(new, key)
    meta = {"page_title": title, "snapshot": f"{src.name}/{key}"}
    if old is None:
        if baseline or key in previous:  # first read, or the last fetch failed
            return
        stats["new"] += 1
        res.items.append(Item(
            id=stable_id("new", src.name, key), source=src.name, kind="new_page",
            title=f'{src.label}: new page "{title}"', url=human_url(url),
            body=new[:1500], published_at=published or ctx.now, metadata=meta,
        ))
        return
    stats["changed"] += 1
    diff, counts = describe_change(old, new)
    meta.update(counts, format_only=is_format_only(old, new))
    res.items.append(Item(
        id=stable_id("chg", src.name, key, content_hash(old), content_hash(new)),
        source=src.name, kind="changed_page", title=f'{src.label}: "{title}" changed',
        url=human_url(url), body=diff, published_at=published or ctx.now, metadata=meta,
    ))


def removed_items(src: Source, ctx: Context, res: SourceResult, stats: dict, gone: set[str], base: str) -> None:
    for key in sorted(gone):
        old = ctx.snapshots.read(src.name, key) or ""
        title = title_of(old, key)
        stats["removed"] += 1
        res.deletes.append(key)
        res.items.append(Item(
            id=stable_id("rm", src.name, key, content_hash(old)), source=src.name,
            kind="removed_page", title=f'{src.label}: page removed "{title}"',
            url=human_url(f"{base.rstrip('/')}/{key}"), body=old[:800], published_at=ctx.now,
            metadata={"page_title": title, "snapshot": f"{src.name}/{key}"},
        ))


def new_stats(baseline: bool, listed: int, skipped_lang: int = 0) -> dict:
    return {
        "listed": listed, "fetched": 0, "errors": 0, "not_markdown": 0,
        "skipped_non_english": skipped_lang, "baseline": baseline,
        "new": 0, "changed": 0, "removed": 0, "unchanged": 0,
    }


def fetch(src: Source, ctx: Context) -> SourceResult:
    index = ctx.fetcher.get(src.url)
    if not index.ok:
        raise SourceError(f"index {src.url}: {index.error}")
    pages, skipped_lang, links = parse_index(
        index.text, src.options["include_prefix"], src.options.get("exclude", []),
        src.options.get("require_keyword"),
    )
    if not pages and not links:
        raise SourceError(f"index {src.url} listed no pages")
    listed = len(pages)
    pages = dict(list(pages.items())[:MAX_PAGES_PER_SITE])

    old_index = ctx.snapshots.read(src.name, INDEX_KEY)
    baseline = old_index is None
    previous = set(old_index.split()) if old_index else set()
    fetched = ctx.fetcher.get_many(list(pages))

    res = SourceResult()
    stats = new_stats(baseline, listed, skipped_lang)
    current = {page_key(url) for url in pages}
    for url, title in pages.items():
        compare_page(src, ctx, res, stats, url, title, fetched[url], previous, baseline)

    # Pages gone from the index. Skip this if the index suddenly shrank by half or more,
    # which is far more likely a broken index than a mass deletion.
    gone = previous - current
    if gone and len(current) >= len(previous) / 2:
        host = urlsplit(src.url)
        removed_items(src, ctx, res, stats, gone, f"{host.scheme}://{host.hostname}")
    elif gone:
        stats["index_shrank"] = len(gone)
        current |= gone  # keep watching them until the index recovers

    if src.options.get("track_links"):
        _new_links(src, ctx, res, stats, links, baseline)

    index_text = "\n".join(sorted(current)) + "\n"
    if index_text != old_index:
        res.writes[INDEX_KEY] = index_text
    if len(res.items) > MAX_ITEMS_PER_SOURCE:
        res.items = [_rollup(src, res.items, ctx)]
        stats["rolled_up"] = True
    res.stats = stats
    return res


def _new_links(src: Source, ctx: Context, res: SourceResult, stats: dict, links: dict, baseline: bool) -> None:
    """New entries in the index that are not Markdown pages (videos, external guides)."""
    skip = src.options.get("links_skip_prefix")
    links = {u: v for u, v in links.items() if not (skip and u.startswith(skip))}
    old = ctx.snapshots.read(src.name, LINKS_KEY)
    known = {line.split("\t", 1)[0] for line in (old or "").splitlines() if line}
    stats["links"] = len(links)
    if old is not None:
        for url, (title, desc) in links.items():
            if url in known:
                continue
            stats["new_links"] = stats.get("new_links", 0) + 1
            res.items.append(Item(
                id=stable_id("link", src.name, url), source=src.name, kind="new_url",
                title=f"{src.label}: {title}", url=url, body=desc or title, published_at=ctx.now,
            ))
    text = "".join(f"{u}\t{t}\n" for u, (t, _) in sorted(links.items()))
    if text != old:
        res.writes[LINKS_KEY] = text


def _rollup(src: Source, items: list[Item], ctx: Context) -> Item:
    """Too many changes at once (a site reorganisation): one item that lists them."""
    lines = [f"- {i.title} ({i.url})" for i in items[:80]]
    body = f"{len(items)} pages changed at once on {src.label}.\n" + "\n".join(lines)
    return Item(
        id=stable_id("rollup", src.name, *sorted(i.id for i in items)), source=src.name,
        kind="rollup", title=f"{src.label}: {len(items)} pages changed at once",
        url=src.url.removesuffix("llms.txt"), body=body, published_at=ctx.now,
        metadata={"count": len(items)},
    )
