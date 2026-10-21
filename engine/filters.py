"""Code filters: drop by fact, never by taste (PROFILE.md -> Code filters).

Non-English pages and the first-read baseline are handled while fetching; these run on the
stored items that no stage has looked at yet.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from .config import AGE_GRACE_DAYS, MAX_AGE_DAYS
from .store import Store


def age_cutoff(now: datetime, last_run: datetime | None) -> datetime:
    """Dated entries before this are history. Docs often post a release days or weeks after
    it shipped, so later runs allow a grace period before the last run."""
    if last_run is None:
        return now - timedelta(days=MAX_AGE_DAYS)
    return last_run - timedelta(days=AGE_GRACE_DAYS)


def _too_old(row, cutoff: datetime) -> bool:
    return bool(row["published_at"]) and datetime.fromisoformat(row["published_at"]) < cutoff


FILTERS = (
    ("too_old", lambda row, meta, cutoff: _too_old(row, cutoff)),
    ("format_only", lambda row, meta, cutoff: bool(meta.get("format_only"))),
    ("bugfix_only", lambda row, meta, cutoff: bool(meta.get("bugfix_only"))),
)


def run_filters(store: Store, now: datetime, last_run: datetime | None = None) -> dict[str, int]:
    cutoff = age_cutoff(now, last_run)
    counts = {name: 0 for name, _ in FILTERS}
    counts["passed"] = 0
    for row in store.rows("filtered_by IS NULL AND route IS NULL"):
        meta = json.loads(row["metadata"])
        for name, test in FILTERS:
            if test(row, meta, cutoff):
                store.set_filtered(row["id"], name)
                counts[name] += 1
                break
        else:
            counts["passed"] += 1
    store.commit()
    return counts
