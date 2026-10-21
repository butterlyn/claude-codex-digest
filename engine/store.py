"""SQLite store: every item ever seen, why it was dropped, what the decision pass said."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .items import Item

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id            TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    kind          TEXT NOT NULL,
    title         TEXT NOT NULL,
    url           TEXT NOT NULL,
    body          TEXT NOT NULL,
    published_at  TEXT,
    engagement    REAL,
    metadata      TEXT NOT NULL DEFAULT '{}',
    first_seen_at TEXT NOT NULL,
    run_id        TEXT,
    filtered_by   TEXT,
    decision      TEXT,
    route         TEXT,
    in_digest     TEXT
);
CREATE INDEX IF NOT EXISTS items_source ON items(source);
CREATE INDEX IF NOT EXISTS items_first_seen ON items(first_seen_at);

CREATE TABLE IF NOT EXISTS sources (
    name            TEXT PRIMARY KEY,
    last_fetched_at TEXT,
    last_status     TEXT,
    last_stats      TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    id          TEXT PRIMARY KEY,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    stats       TEXT
);
"""


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).isoformat() if dt else None


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.commit()
        self.db.close()

    # items -----------------------------------------------------------------
    def add_items(self, items: list[Item], run_id: str, now: datetime) -> tuple[int, int]:
        """Insert new items; ids already stored are skipped. Returns (added, already_seen)."""
        added = 0
        for item in items:
            cur = self.db.execute(
                """INSERT OR IGNORE INTO items
                   (id, source, kind, title, url, body, published_at, engagement, metadata,
                    first_seen_at, run_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item.id, item.source, item.kind, item.title, item.url, item.body,
                    iso(item.published_at), item.engagement,
                    json.dumps(item.metadata, ensure_ascii=False, sort_keys=True),
                    iso(now), run_id,
                ),
            )
            added += cur.rowcount
        self.db.commit()
        return added, len(items) - added

    def rows(self, where: str = "1=1", params: tuple = ()) -> list[sqlite3.Row]:
        return self.db.execute(
            f"SELECT * FROM items WHERE {where} ORDER BY first_seen_at, id", params
        ).fetchall()

    def set_filtered(self, item_id: str, reason: str) -> None:
        self.db.execute("UPDATE items SET filtered_by = ? WHERE id = ?", (reason, item_id))

    def set_decision(self, item_id: str, decision: dict | None, route: str) -> None:
        self.db.execute(
            "UPDATE items SET decision = ?, route = ?, filtered_by = ? WHERE id = ?",
            (
                json.dumps(decision, sort_keys=True) if decision is not None else None,
                route,
                "decision:drop" if route == "drop" else None,
                item_id,
            ),
        )

    def mark_in_digest(self, item_ids: list[str], date: str) -> None:
        self.db.executemany(
            "UPDATE items SET in_digest = ? WHERE id = ?", [(date, i) for i in item_ids]
        )

    def commit(self) -> None:
        self.db.commit()

    # sources and runs ------------------------------------------------------
    def source_fetched(self, name: str, now: datetime, status: str, stats: dict) -> None:
        self.db.execute(
            """INSERT INTO sources (name, last_fetched_at, last_status, last_stats)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET last_fetched_at = excluded.last_fetched_at,
                   last_status = excluded.last_status, last_stats = excluded.last_stats""",
            (name, iso(now), status, json.dumps(stats, sort_keys=True)),
        )
        self.db.commit()

    def start_run(self, run_id: str, now: datetime) -> None:
        self.db.execute("INSERT OR REPLACE INTO runs (id, started_at) VALUES (?, ?)", (run_id, iso(now)))
        self.db.commit()

    def finish_run(self, run_id: str, now: datetime, stats: dict) -> None:
        self.db.execute(
            "UPDATE runs SET finished_at = ?, stats = ? WHERE id = ?",
            (iso(now), json.dumps(stats, sort_keys=True), run_id),
        )
        self.db.commit()
