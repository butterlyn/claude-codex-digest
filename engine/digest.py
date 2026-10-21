"""The reading pass and the digest: one Claude Sonnet 5.5 call over what the decision pass
let through, rendered to Markdown in code so every link is a real item's link.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import DIGEST_CAP, GROUPS, READING_CAP, REPO_URL, SOURCES_BY_NAME, TIMEZONE
from .decide import KIND_LABEL
from .llm import READING_MODEL, ask_json
from .store import Store

SYSTEM = f"""You write a digest for one person. They keep up with changes to Claude Code and \
Codex (features, commands, flags, settings, defaults, deprecations), the Claude and ChatGPT \
apps, and every new or updated official guide, explainer, tutorial or launch post about them, \
including guides about features that already exist. They read the digest to \
decide what to save to their to-try list and what to change in their setup this week.

You get every item that passed their filter since their last digest, as JSON. It may cover one \
day or several weeks. Items with route "unsure" passed only partly: include one only if it \
clearly reports something new and concrete that matters to them.

Rules:
- At most {DIGEST_CAP} entries in total, counting "also". Pick the ones that change what they \
would do this week. Leaving items out is expected.
- Group items about the same thing into one entry: a changelog line and the docs page that \
documents it are one entry. Never list the same change twice.
- Each entry's text: "**<what changed, at most 10 words>** - <what to try or change>." One or \
two short sentences after the bold part. For a docs change, give before -> after when the \
excerpt shows it. For a new or updated guide, say what it teaches and who should read it.
- Put each entry under one group: {", ".join(GROUPS)}.
- Refer to items only by their "id" in the entry's "items" list. Never write a URL, and never \
state a detail that is not in the items.
- Say plainly when something is a minor update, a deprecation or a removal.
- A changelog entry is a launch only if it says something launched.
- No hype words, no exclamation marks.
- "headline": one plain line on what mattered most since the last digest.
- For a changelog or release entry, name the version.
- "also": up to 3 one-line mentions that matter less; each still names the specific change."""

_ENTRY = {
    "type": "object",
    "properties": {"text": {"type": "string"}, "items": {"type": "array", "items": {"type": "string"}}},
    "required": ["text", "items"],
    "additionalProperties": False,
}
SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"group": {"type": "string", "enum": list(GROUPS)}, "entries": {"type": "array", "items": _ENTRY}},
                "required": ["group", "entries"],
                "additionalProperties": False,
            },
        },
        "also": {"type": "array", "items": _ENTRY},
    },
    "required": ["headline", "sections", "also"],
    "additionalProperties": False,
}


@dataclass
class DigestResult:
    date: str
    path: Path
    markdown: str
    included: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


def local_date(now: datetime) -> str:
    return now.astimezone(ZoneInfo(TIMEZONE)).date().isoformat()


def local_stamp(now: datetime) -> str:
    """File name for a run: runs are on demand, so there can be several a day."""
    return now.astimezone(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d-%H%M")


def _since_line(last_run: datetime | None) -> str:
    if last_run is None:
        return "First run: the past week's dated changes. Docs page edits show from the next run."
    when = last_run.astimezone(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M")
    return f"Changes since the last run, {when} Perth time."


def _rank(row) -> tuple:
    d = json.loads(row["decision"]) if row["decision"] else {}
    return (row["route"] != "keep", -(d.get("relevance") or 0), row["published_at"] or "")


def candidates(store: Store, ignore_decisions: bool = False) -> list:
    """Every item not yet read: everything since the last digest, including anything a failed
    run left behind."""
    gate = (
        "(filtered_by IS NULL OR filtered_by = 'decision:drop')"  # measuring: pretend no decision pass
        if ignore_decisions else "route IN ('keep', 'unsure')"
    )
    rows = store.rows(f"read_on IS NULL AND {gate}")
    return sorted(rows, key=_rank)[:READING_CAP]


def _excerpt(row) -> str:
    limit = 1200 if row["kind"] in ("changed_page", "changed_entry", "rollup") else 600
    return row["body"][:limit]


def reading_input(rows: list, ignore_decisions: bool = False) -> list[dict]:
    items = []
    for n, row in enumerate(rows, 1):
        d = json.loads(row["decision"]) if row["decision"] else {}
        src = SOURCES_BY_NAME.get(row["source"])
        items.append({
            "id": f"i{n}",
            "group": src.group if src else "News & guides",
            "source": src.label if src else row["source"],
            "kind": KIND_LABEL.get(row["kind"], row["kind"]),
            "title": row["title"],
            "published": (row["published_at"] or "")[:10] or None,
            "route": "unsure" if ignore_decisions else (row["route"] or "unsure"),
            "relevance": None if ignore_decisions else d.get("relevance"),
            "excerpt": _excerpt(row),
        })
    return items


def _link_label(row) -> str:
    meta = json.loads(row["metadata"])
    if row["kind"] in ("changed_page", "new_page", "removed_page") and meta.get("page_title"):
        return meta["page_title"]
    src = SOURCES_BY_NAME.get(row["source"])
    return src.label if src else row["source"]


def _links(ids: list[str], by_id: dict) -> str:
    parts: list[str] = []
    for i in ids:
        row = by_id[i]
        parts.append(f"[{_link_label(row)}]({row['url']})")
        snapshot = json.loads(row["metadata"]).get("snapshot")
        if snapshot and row["kind"] == "changed_page":
            parts.append(f"[history]({REPO_URL}/commits/main/data/snapshots/{snapshot})")
    return " · ".join(dict.fromkeys(parts))


def _footer(read: int, used: int, unreadable: list[str]) -> list[str]:
    lines = []
    if unreadable:
        lines.append(f"<sub>Couldn't read this run: {'; '.join(unreadable)}.</sub>")
        lines.append("")
    lines.append(f"<sub>{read} items read, {used} used. Reply with `missed: ...` or `noise: ...`.</sub>")
    return lines


def render(
    date: str, data: dict, by_id: dict, read: int, unreadable: list[str] | None = None,
    since: str = "",
) -> tuple[str, list[str]]:
    lines = [f"# {date} - {data['headline'].strip()}", ""]
    if since:
        lines += [f"_{since}_", ""]
    used: list[str] = []
    count = 0
    for group in GROUPS:
        entries = [e for s in data["sections"] if s["group"] == group for e in s["entries"]]
        rendered = []
        for entry in entries:
            ids = [i for i in entry["items"] if i in by_id]
            if not ids or count >= DIGEST_CAP:
                continue  # an entry that points at no real item is never printed
            rendered.append(f"- [ ] {entry['text'].strip()} {_links(ids, by_id)}")
            used += ids
            count += 1
        if rendered:
            lines += [f"## {group}", "", *rendered, ""]
    also = []
    for entry in data.get("also", []):
        ids = [i for i in entry["items"] if i in by_id]
        if ids and count < DIGEST_CAP:
            text = entry["text"].strip()
            also.append(f"- {text}{'' if text.endswith(('.', ':')) else '.'} {_links(ids, by_id)}")
            used += ids
            count += 1
    if also:
        lines += ["## Also worth a look", "", *also, ""]
    if count == 0:
        lines += ["Nothing today changes what you would do.", ""]
    lines += _footer(read, len(dict.fromkeys(used)), unreadable or [])
    return "\n".join(lines) + "\n", list(dict.fromkeys(used))


def write_digest(
    store: Store, digests_dir: Path, now: datetime, ignore_decisions: bool = False,
    unreadable: list[str] | None = None, last_run: datetime | None = None,
) -> DigestResult:
    date = local_date(now)
    path = digests_dir / f"{local_stamp(now)}.md"
    since = _since_line(last_run)
    rows = candidates(store, ignore_decisions)
    stats = {"read": len(rows), "tokens": 0, "seconds": 0.0, "cost_usd": 0.0}
    if not rows:
        markdown = "\n".join([f"# {date} - Nothing new", "", f"_{since}_", "",
                              "No changes passed the filters.", "", *_footer(0, 0, unreadable or [])]) + "\n"
        included: list[str] = []
    else:
        items = reading_input(rows, ignore_decisions)
        by_id = {item["id"]: row for item, row in zip(items, rows)}
        started = time.monotonic()
        ans = ask_json(
            "Today's items:\n" + json.dumps(items, ensure_ascii=False, indent=1),
            system=SYSTEM, schema=SCHEMA, model=READING_MODEL, effort="medium",
            fallback_model="claude-opus-5-5", timeout=600,
        )
        stats.update(tokens=ans.input_tokens + ans.output_tokens, seconds=round(time.monotonic() - started, 1),
                     cost_usd=round(ans.cost_usd, 4), model=ans.model, models=ans.models)
        markdown, used_ids = render(date, ans.data, by_id, len(rows), unreadable, since)
        included = [by_id[i]["id"] for i in used_ids]
        store.mark_read([r["id"] for r in rows], local_stamp(now))
        store.mark_in_digest(included, local_stamp(now))
        store.commit()
    digests_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")  # written before any delivery is tried
    stats["included"] = len(included)
    return DigestResult(date=date, path=path, markdown=markdown, included=included, stats=stats)
