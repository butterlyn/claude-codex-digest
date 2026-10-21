"""Changelogs and release notes: split the page into entries, report new and edited ones.

The whole page is kept as a snapshot, so an entry that gains a line later the same day comes
back as an edit with just that line, instead of being missed or re-reported in full.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Callable

from ..config import MAX_AGE_DAYS, Source
from ..diffing import content_hash, describe_change, is_format_only
from ..items import Item, stable_id
from . import Context, SourceError, SourceResult
from .docs_site import clean_page, human_url
from .htmltext import json_or_none, parse_datetime, soup, to_markdown

VERSION_LINE = re.compile(r"^(?:#{1,4}\s+|\*\*)v?(\d+(?:\.\d+){1,3})(?:\*\*)?\s*$")
_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
DATE_HEADING = re.compile(rf"^#{{2,4}}\s+((?:{_MONTHS})\s+\d{{1,2}},\s+\d{{4}})\s*$")
MONTH_HEADING = re.compile(rf"^#{{1,3}}\s+(?:{_MONTHS})\s+\d{{4}}\s*$")
BULLET = re.compile(r"^\s*[-*]\s+(.*\S)")
FIX = re.compile(r"^(?:\\?\[[^\]]*\]\s*)*(?:fix|fixed|fixes|fixing)\b", re.IGNORECASE)


def split_entries(text: str, heading: re.Pattern, skip: re.Pattern | None = None) -> list[tuple[str, str]]:
    """(heading, body) pairs in page order. Repeated headings get ' (2)', ' (3)' ..."""
    raw: list[tuple[str, list[str]]] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if skip and skip.match(stripped):
            continue
        match = heading.match(stripped)
        if match:
            raw.append((match.group(1), []))
        elif raw:
            raw[-1][1].append(line)
    seen: Counter = Counter()
    out = []
    for head, lines in raw:
        seen[head] += 1
        out.append((head if seen[head] == 1 else f"{head} ({seen[head]})", "\n".join(lines).strip()))
    return out


def bullets(body: str) -> list[str]:
    return [m.group(1) for m in map(BULLET.match, body.split("\n")) if m]


GENERIC_FIX_NOTE = re.compile(
    r"^(?:minor\s+)?bug\s*fixes(?:\s+and\s+(?:minor\s+)?(?:reliability|stability|performance)"
    r"(?:\s+improvements)?)?\.?$", re.IGNORECASE,
)


def is_bugfix_only(body: str) -> bool:
    """Every bullet is a fix, or the whole entry is a stock 'Bug fixes ...' line."""
    def is_fix(text: str) -> bool:
        text = " ".join(re.sub(r"[*_`]", "", text).split())
        return bool(FIX.match(text) or GENERIC_FIX_NOTE.match(text))

    items = bullets(body)
    return all(is_fix(b) for b in items) if items else is_fix(body)


def first_real_sentence(body: str) -> str:
    """The first line worth reading: skips section labels, tag lines and short fragments,
    and prefers a line that is not a bug fix."""
    candidates = []
    for line in body.split("\n"):
        match = BULLET.match(line)
        text = re.sub(r"\*\*|__|\\(?=\[)", "", match.group(1) if match else line).strip()
        if len(text.split()) < 5 or text.startswith(("#", "|", ">")):
            continue
        candidates.append(text)
    non_fix = [c for c in candidates if not FIX.match(c)]
    pick = (non_fix or candidates or [""])[0]
    return re.split(r"(?<=[.!?])\s", pick, maxsplit=1)[0][:160]


def diff_entries(
    src: Source, ctx: Context, key: str, new_text: str,
    split: Callable[[str], list[tuple[str, str]]],
    date_for: Callable[[str], datetime | None], url: str,
) -> SourceResult:
    old_text = ctx.snapshots.read(src.name, key)
    baseline = old_text is None
    old = dict(split(old_text)) if old_text else {}
    entries = split(new_text)
    if not entries:
        raise SourceError(f"{src.url}: no entries found; the page layout may have changed")
    cutoff = ctx.now - timedelta(days=MAX_AGE_DAYS)
    res = SourceResult()
    stats = {"entries": len(entries), "baseline": baseline, "new": 0, "changed": 0, "skipped_old": 0}
    for heading, body in entries:
        published = date_for(heading)
        if heading not in old:
            # First read: report only dated entries inside the age window; the rest is history.
            if baseline and (published is None or published < cutoff):
                stats["skipped_old"] += 1
                continue
            stats["new"] += 1
            res.items.append(Item(
                id=stable_id("entry", src.name, src.url, heading), source=src.name, kind="entry",
                title=f"{src.label} {heading}: {first_real_sentence(body)}", url=url, body=body,
                published_at=published or ctx.now,
                metadata={"heading": heading, "bullets": len(bullets(body)), "bugfix_only": is_bugfix_only(body)},
            ))
        elif old[heading] != body:
            stats["changed"] += 1
            diff, counts = describe_change(old[heading], body)
            res.items.append(Item(
                id=stable_id("chg", src.name, heading, content_hash(old[heading]), content_hash(body)),
                source=src.name, kind="changed_entry", title=f"{src.label} {heading}: entry edited",
                url=url, body=diff, published_at=ctx.now,
                metadata=dict(counts, heading=heading, format_only=is_format_only(old[heading], body)),
            ))
    if old_text != new_text:
        res.writes[key] = new_text
    res.stats = stats
    return res


def _npm_release_dates(ctx: Context, package: str) -> dict[str, datetime]:
    page = ctx.fetcher.get(f"https://registry.npmjs.org/{package}")
    data = json_or_none(page.text) if page.ok else None
    if not isinstance(data, dict):
        return {}
    times = data.get("time", {})
    return {v: d for v, t in times.items() if (d := parse_datetime(t)) and v[0].isdigit()}


def fetch_md_changelog(src: Source, ctx: Context) -> SourceResult:
    """A Markdown changelog with one bold or heading line per version (**2.1.306**)."""
    page = ctx.fetcher.get(src.url)
    if not page.ok:
        raise SourceError(f"{src.url}: {page.error}")
    dates = _npm_release_dates(ctx, src.options["npm_package"]) if src.options.get("npm_package") else {}
    res = diff_entries(
        src, ctx, "changelog.md", clean_page(page.text),
        split=lambda text: split_entries(text, VERSION_LINE),
        date_for=lambda version: dates.get(version), url=human_url(src.url),
    )
    res.stats["release_dates"] = len(dates)
    return res


def _heading_date(heading: str) -> datetime | None:
    return parse_datetime(re.sub(r"\s+\(\d+\)$", "", heading))


def fetch_release_notes(src: Source, ctx: Context) -> SourceResult:
    """A help-center article with one dated heading per release (### October 7, 2026).
    Reads the article's Markdown twin when the URL ends in .md, else the HTML."""
    page = ctx.fetcher.get(src.url)
    if not page.ok:
        raise SourceError(f"{src.url}: {page.error}")
    if src.url.endswith(".md"):
        text = clean_page(page.text)
    else:
        doc = soup(page.text)
        article = doc.select_one("div.article_body article") or doc.find("article")
        if article is None:
            raise SourceError(f"{src.url}: article body not found")
        text = to_markdown(article)
    return diff_entries(
        src, ctx, "release-notes.md", text,
        split=lambda body: split_entries(body, DATE_HEADING, skip=MONTH_HEADING),
        date_for=_heading_date, url=human_url(src.url),
    )
