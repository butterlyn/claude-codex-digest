"""The decision pass: two typed questions on every item that passed the code filters.

The questions are PROFILE.md's, word for word where possible. Code routes each item:
sure drops are stored as filtered and never read; everything else goes to the reading pass.
A failed call never drops an item.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import urlsplit

from .config import MAX_DECISIONS_PER_RUN, SOURCES_BY_NAME
from .llm import DECISION_MODEL, LLMError, ask_json
from .store import Store

SYSTEM = """You triage one item for a person's daily digest. They use Claude Code and Codex \
every day, plus the Claude and ChatGPT apps, and they save good items to a to-try list so \
they can update their setup that week.

Each item is a change on an official Claude, Anthropic, Codex or OpenAI website: a new or \
edited docs page (shown as a diff of "added:", "removed:" and "changed:" lines, where \
changed lines mark [-old words-] and {+new words+}), a changelog or release-notes entry, a new web page, or a news \
post. Judge only from what the item says.

relevance (1-5): How much could this change what they do with Claude Code, Codex, or the \
Claude and ChatGPT apps?
1 = Not about these tools: company news, policy, research, funding, customer stories, \
enterprise- or admin-only settings (SSO, admin console, compliance, org billing), ChatGPT \
features unrelated to Codex.
2 = About these tools, but nothing they would do differently: rewording, reorganised pages, \
marketing copy.
3 = A small detail worth knowing: a clarified behaviour, a minor option, a new example.
4 = Something they could try or should adjust: a new or changed command, flag, setting, hook, \
integration or feature, or a new official guide, including ones limited to some plans.
5 = Changes how they work now: a changed default, a removed or deprecated option, a breaking \
change, a major new feature.
An unfamiliar feature, model or product name is not a reason to score lower.

new (true/false): Does it report something new and concrete: a new, changed or removed \
feature, command, flag, setting, default, limit or price, or a newly published guide or \
launch? Typo and formatting fixes, bug-fix-only notes, rewording that keeps the meaning, \
opinions and marketing are false.

reason: at most 15 words, plain."""

SCHEMA = {
    "type": "object",
    "properties": {
        "relevance": {"type": "integer", "minimum": 1, "maximum": 5},
        "new": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["relevance", "new", "reason"],
    "additionalProperties": False,
}

KIND_LABEL = {
    "new_page": "new docs page", "changed_page": "edited page (diff)", "removed_page": "removed docs page",
    "entry": "changelog / release-notes entry", "changed_entry": "edited changelog entry (diff)",
    "new_url": "new web page", "feed_item": "news or changelog post", "rollup": "many changes at once",
}
WORKERS = 4


def route(decision: dict | None) -> str:
    """drop when sure; keep when clearly relevant and new; everything else is unsure."""
    if decision is None:
        return "unsure"
    rel, new = decision["relevance"], decision["new"]
    if rel <= 1 or (not new and rel <= 2):
        return "drop"
    if rel >= 4 and new:
        return "keep"
    return "unsure"


def item_prompt(item: dict) -> str:
    src = SOURCES_BY_NAME.get(item["source"])
    label = src.label if src else item["source"]
    host = urlsplit(item["url"]).hostname or ""
    return (
        f"Source: {label} ({host})\n"
        f"Kind: {KIND_LABEL.get(item['kind'], item['kind'])}\n"
        f"Title: {item['title']}\n"
        f"URL: {item['url']}\n\n"
        f"Content:\n{item['body'][:1500]}"
    )


@dataclass
class Verdict:
    decision: dict | None
    route: str
    error: str | None = None
    tokens: int = 0
    cost_usd: float = 0.0


def decide_one(item: dict) -> Verdict:
    try:
        ans = ask_json(
            item_prompt(item), system=SYSTEM, schema=SCHEMA, model=DECISION_MODEL,
            effort="low", fallback_model="claude-sonnet-5-5", timeout=120,
        )
    except LLMError as exc:
        return Verdict(None, "unsure", error=str(exc))
    decision = {k: ans.data[k] for k in ("relevance", "new", "reason")}
    decision["model"] = ans.model
    return Verdict(decision, route(decision), tokens=ans.input_tokens + ans.output_tokens, cost_usd=ans.cost_usd)


def decide_many(items: list[dict]) -> list[Verdict]:
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        return list(pool.map(decide_one, items))


def run_decisions(store: Store) -> dict:
    rows = store.rows("filtered_by IS NULL AND route IS NULL")
    todo, overflow = rows[:MAX_DECISIONS_PER_RUN], rows[MAX_DECISIONS_PER_RUN:]
    verdicts = decide_many([dict(r) for r in todo])
    counts = {"keep": 0, "unsure": 0, "drop": 0, "failed": 0, "overflow": len(overflow), "tokens": 0, "cost_usd": 0.0}
    for row, v in zip(todo, verdicts):
        store.set_decision(row["id"], v.decision, v.route)
        counts[v.route] += 1
        counts["failed"] += v.error is not None
        counts["tokens"] += v.tokens
        counts["cost_usd"] += v.cost_usd
    for row in overflow:  # no verdict: the reading pass decides
        store.set_decision(row["id"], None, "unsure")
        counts["unsure"] += 1
    store.commit()
    counts["cost_usd"] = round(counts["cost_usd"], 4)
    return counts
