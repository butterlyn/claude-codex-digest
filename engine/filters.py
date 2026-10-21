"""Code filters: drop by fact, never by taste (PROFILE.md -> Code filters).

Non-English pages and the first-read baseline are handled while fetching; these run on the
stored items that no stage has looked at yet.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from .config import MAX_AGE_DAYS
from .store import Store


def _too_old(row, now: datetime) -> bool:
    if not row["published_at"]:
        return False
    return datetime.fromisoformat(row["published_at"]) < now - timedelta(days=MAX_AGE_DAYS)


FILTERS = (
    ("too_old", lambda row, meta, now: _too_old(row, now)),
    ("format_only", lambda row, meta, now: bool(meta.get("format_only"))),
    ("bugfix_only", lambda row, meta, now: bool(meta.get("bugfix_only"))),
)


def run_filters(store: Store, now: datetime) -> dict[str, int]:
    counts = {name: 0 for name, _ in FILTERS}
    counts["passed"] = 0
    for row in store.rows("filtered_by IS NULL AND route IS NULL"):
        meta = json.loads(row["metadata"])
        for name, test in FILTERS:
            if test(row, meta, now):
                store.set_filtered(row["id"], name)
                counts[name] += 1
                break
        else:
            counts["passed"] += 1
    store.commit()
    return counts
