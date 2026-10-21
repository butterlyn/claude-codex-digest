"""The one item shape every source maps to (see PROFILE.md and the item schema)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime

BODY_CAP = 4000


def stable_id(prefix: str, *parts: str) -> str:
    """Same inputs, same id, every run."""
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


@dataclass
class Item:
    id: str
    source: str
    kind: str  # new_page, changed_page, removed_page, entry, changed_entry, new_url, feed_item
    title: str
    url: str
    body: str
    published_at: datetime | None = None
    engagement: float | None = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.title = " ".join(self.title.split())[:300]
        if len(self.body) > BODY_CAP:
            self.body = self.body[:BODY_CAP] + "\n...(truncated)"
