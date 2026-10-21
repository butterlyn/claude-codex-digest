"""RSS and Atom feeds: every entry not seen before is an item."""

from __future__ import annotations

import calendar
import json
import os
import re
from datetime import datetime, timedelta, timezone

import feedparser

from ..config import MAX_AGE_DAYS, MAX_ITEMS_PER_SOURCE, Source
from ..items import Item, stable_id
from . import Context, SourceError, SourceResult
from .changelog import bullets, first_real_sentence, is_bugfix_only
from .htmltext import json_or_none, parse_datetime, soup, to_markdown

KEY = "feed.jsonl"


def _published(entry) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc) if parsed else None


def _body(entry) -> str:
    content = entry.get("content")
    raw = content[0].get("value", "") if content else entry.get("summary", "")
    return to_markdown(soup(raw)) if "<" in raw and ">" in raw else raw.strip()


def fetch_rss(src: Source, ctx: Context) -> SourceResult:
    page = ctx.fetcher.get(src.url)
    if not page.ok:
        raise SourceError(f"{src.url}: {page.error}")
    feed = feedparser.parse(page.text)
    if not feed.entries:
        raise SourceError(f"{src.url}: no entries ({feed.get('bozo_exception', 'empty feed')})")

    old = ctx.snapshots.read(src.name, KEY)
    baseline = old is None
    seen = {json.loads(line)["key"] for line in (old or "").splitlines() if line.strip()}
    cutoff = ctx.now - timedelta(days=MAX_AGE_DAYS)

    res = SourceResult()
    stats = {"entries": len(feed.entries), "baseline": baseline, "new": 0, "skipped_old": 0}
    rows = []
    for entry in feed.entries:
        key = entry.get("id") or entry.get("link")
        if not key:
            continue
        published = _published(entry)
        rows.append({"key": key, "title": entry.get("title", ""), "published": published.isoformat() if published else None})
        if key in seen:
            continue
        if baseline and (published is None or published < cutoff):
            stats["skipped_old"] += 1
            continue
        body = _body(entry)
        title = " ".join(entry.get("title", "").split()) or "untitled"
        if len(title.split()) < 4:  # "Codex app" says nothing on its own
            sentence = first_real_sentence(body)
            title = f"{title}: {sentence}" if sentence else title
        stats["new"] += 1
        res.items.append(Item(
            id=stable_id("feed", src.name, key), source=src.name, kind="feed_item",
            title=f"{src.label}: {title}", url=entry.get("link") or src.url, body=body,
            published_at=published or ctx.now,
            metadata={"categories": [t.get("term") for t in entry.get("tags", []) if t.get("term")]},
        ))

    res.items.sort(key=lambda i: i.published_at, reverse=True)
    res.items = res.items[:MAX_ITEMS_PER_SOURCE]
    snapshot = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in sorted(rows, key=lambda r: r["key"]))
    if snapshot != old:
        res.writes[KEY] = snapshot
    res.stats = stats
    return res


PRERELEASE_TAG = re.compile(r"-(?:alpha|beta|rc|pre|nightly)\b", re.IGNORECASE)


def fetch_github_releases(src: Source, ctx: Context) -> SourceResult:
    """Published releases of a GitHub repo (drafts and pre-releases skipped)."""
    repo = src.options["repo"]
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    page = ctx.fetcher.get(f"https://api.github.com/repos/{repo}/releases?per_page=30", headers=headers)
    releases = json_or_none(page.text) if page.ok else None
    if not isinstance(releases, list):
        raise SourceError(f"GitHub releases for {repo}: {page.error or 'unexpected response'}")

    key = "releases.jsonl"
    old = ctx.snapshots.read(src.name, key)
    baseline = old is None
    seen = {json.loads(line)["key"] for line in (old or "").splitlines() if line.strip()}
    cutoff = ctx.now - timedelta(days=MAX_AGE_DAYS)
    res = SourceResult()
    stats = {"releases": len(releases), "baseline": baseline, "new": 0, "skipped_prerelease": 0, "skipped_old": 0}
    rows = []
    for rel in releases:
        tag = rel.get("tag_name") or ""
        if rel.get("draft") or rel.get("prerelease") or PRERELEASE_TAG.search(tag):
            stats["skipped_prerelease"] += 1
            continue
        rid = str(rel.get("id"))
        published = parse_datetime(rel.get("published_at"))
        rows.append({"key": rid, "tag": tag, "published": published.isoformat() if published else None})
        if rid in seen:
            continue
        if baseline and (published is None or published < cutoff):
            stats["skipped_old"] += 1
            continue
        body = (rel.get("body") or "").strip()
        name = rel.get("name") or tag
        stats["new"] += 1
        res.items.append(Item(
            id=stable_id("release", src.name, rid), source=src.name, kind="entry",
            title=f"{src.label} {name}: {first_real_sentence(body)}",
            url=rel.get("html_url") or src.url, body=body or "(no release notes)",
            published_at=published or ctx.now,
            metadata={"tag": tag, "bullets": len(bullets(body)), "bugfix_only": is_bugfix_only(body)},
        ))
    snapshot = "".join(json.dumps(r, sort_keys=True) + "\n" for r in sorted(rows, key=lambda r: r["key"]))
    if snapshot != old:
        res.writes[key] = snapshot
    res.stats = stats
    return res
