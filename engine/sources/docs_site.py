"""A docs site that lists its pages in llms.txt and serves each page as Markdown.

Every page is compared with yesterday's copy: new pages, changed pages and removed pages
become items. The first read of a site only records the starting copy.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from ..config import LOCALE_SEGMENT, MAX_ITEMS_PER_SOURCE, MAX_PAGES_PER_SITE, Source
from ..diffing import content_hash, describe_change, is_format_only
from ..items import Item, stable_id
from . import Context, SourceError, SourceResult

INDEX_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+?\.md)\)")
H1 = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def parse_index(text: str, include_prefix: str, exclude: list[str]) -> tuple[dict[str, str], int]:
    """Page URL -> title for the English pages under include_prefix, and how many were skipped
    as non-English."""
    pages: dict[str, str] = {}
    skipped_lang = 0
    for title, url in INDEX_LINK.findall(text):
        if not url.startswith(include_prefix) or url in exclude:
            continue
        if LOCALE_SEGMENT.search(urlsplit(url).path):
            skipped_lang += 1
            continue
        pages.setdefault(url, title.strip())
    return pages, skipped_lang


def clean_page(md: str) -> str:
    """Drop the 'Documentation Index' note every page starts with; normalise line endings."""
    lines = md.replace("\r\n", "\n").split("\n")
    if lines and lines[0].startswith(">") and "Documentation Index" in "\n".join(lines[:3]):
        i = 0
        while i < len(lines) and lines[i].startswith(">"):
            i += 1
        lines = lines[i:]
    return "\n".join(lines).strip() + "\n"


def page_key(url: str) -> str:
    return urlsplit(url).path.lstrip("/")


def human_url(md_url: str) -> str:
    return md_url[:-3] if md_url.endswith(".md") else md_url


def _title_of(text: str, fallback: str) -> str:
    match = H1.search(text)
    return match.group(1) if match else fallback


def fetch(src: Source, ctx: Context) -> SourceResult:
    index = ctx.fetcher.get(src.url)
    if not index.ok:
        raise SourceError(f"index {src.url}: {index.error}")
    pages, skipped_lang = parse_index(
        index.text, src.options["include_prefix"], src.options.get("exclude", [])
    )
    if not pages:
        raise SourceError(f"index {src.url} listed no pages")
    listed = len(pages)
    pages = dict(list(pages.items())[:MAX_PAGES_PER_SITE])

    previous = ctx.snapshots.keys(src.name)
    baseline = not previous
    fetched = ctx.fetcher.get_many(list(pages))

    res = SourceResult()
    stats = {
        "listed": listed, "fetched": 0, "errors": 0, "skipped_non_english": skipped_lang,
        "baseline": baseline, "new": 0, "changed": 0, "removed": 0, "unchanged": 0,
    }
    current_keys: set[str] = set()
    for url, title in pages.items():
        page = fetched[url]
        key = page_key(url)
        current_keys.add(key)
        if not page.ok:
            stats["errors"] += 1
            continue
        stats["fetched"] += 1
        new = clean_page(page.text)
        old = ctx.snapshots.read(src.name, key)
        if old == new:
            stats["unchanged"] += 1
            continue
        res.writes[key] = new
        if baseline:
            continue
        meta = {"page_title": title, "snapshot": f"{src.name}/{key}"}
        if old is None:
            stats["new"] += 1
            res.items.append(Item(
                id=stable_id("new", src.name, key), source=src.name, kind="new_page",
                title=f'{src.label}: new page "{title}"', url=human_url(url),
                body=new[:1500], published_at=ctx.now, metadata=meta,
            ))
            continue
        stats["changed"] += 1
        diff, counts = describe_change(old, new)
        meta.update(counts, format_only=is_format_only(old, new))
        res.items.append(Item(
            id=stable_id("chg", src.name, key, content_hash(old), content_hash(new)),
            source=src.name, kind="changed_page",
            title=f'{src.label}: "{title}" changed', url=human_url(url),
            body=diff, published_at=ctx.now, metadata=meta,
        ))

    # Pages gone from the index. Skip this if the index suddenly shrank by half or more,
    # which is far more likely a broken index than a mass deletion.
    gone = previous - current_keys
    if gone and not baseline and len(current_keys) >= len(previous) / 2:
        for key in sorted(gone):
            old = ctx.snapshots.read(src.name, key) or ""
            title = _title_of(old, key)
            stats["removed"] += 1
            res.deletes.append(key)
            res.items.append(Item(
                id=stable_id("rm", src.name, key, content_hash(old)), source=src.name,
                kind="removed_page", title=f'{src.label}: page removed "{title}"',
                url=human_url(f"https://{urlsplit(src.url).hostname}/{key}"),
                body=old[:800], published_at=ctx.now,
                metadata={"page_title": title, "snapshot": f"{src.name}/{key}"},
            ))

    if len(res.items) > MAX_ITEMS_PER_SOURCE:
        res.items = [_rollup(src, res.items, ctx)]
        stats["rolled_up"] = True
    res.stats = stats
    return res


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
