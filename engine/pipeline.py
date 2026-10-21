"""The daily run: fetch -> store -> code filters -> decision pass -> reading pass -> digest."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .config import LIVE_DATA, LIVE_DIGESTS, SOURCES, SOURCES_BY_NAME, Source
from .http import Fetcher
from .snapshots import Snapshots
from .sources import Context, registry
from .store import Store

Log = Callable[[str], None]


@dataclass(frozen=True)
class Paths:
    data: Path
    digests: Path

    @property
    def db(self) -> Path:
        return self.data / "engine.db"

    @property
    def snapshots(self) -> Path:
        return self.data / "snapshots"


def paths_for(data_dir: Path | None) -> Paths:
    """The live data lives in the repo; any other --data-dir is a throwaway test run."""
    if data_dir is None:
        return Paths(LIVE_DATA, LIVE_DIGESTS)
    return Paths(data_dir, data_dir / "digests")


def select_sources(names: list[str] | None) -> list[Source]:
    if not names:
        return list(SOURCES)
    unknown = [n for n in names if n not in SOURCES_BY_NAME]
    if unknown:
        raise SystemExit(f"unknown source(s): {', '.join(unknown)}")
    return [SOURCES_BY_NAME[n] for n in names]


def run_fetch(paths: Paths, sources: list[Source], now: datetime, run_id: str, log: Log) -> dict:
    store = Store(paths.db)
    snaps = Snapshots(paths.snapshots)
    fetcher = Fetcher()
    ctx = Context(fetcher=fetcher, snapshots=snaps, now=now)
    kinds = registry()
    report: dict[str, dict] = {}
    try:
        for src in sources:
            fetch = kinds.get(src.kind)
            if fetch is None:
                report[src.name] = {"status": "not built yet"}
                continue
            started = time.monotonic()
            try:
                res = fetch(src, ctx)
            except Exception as exc:  # one broken source must not stop the others
                status = f"error: {type(exc).__name__}: {exc}"
                store.source_fetched(src.name, now, status, {})
                report[src.name] = {"status": status}
                log(f"  {src.name}: {status}")
                continue
            added, seen = store.add_items(res.items, run_id, now)
            for key, text in res.writes.items():
                snaps.write(src.name, key, text)
            for key in res.deletes:
                snaps.delete(src.name, key)
            stats = dict(
                res.stats, status="ok", items=len(res.items), added=added, already_seen=seen,
                seconds=round(time.monotonic() - started, 1),
            )
            store.source_fetched(src.name, now, "ok", stats)
            report[src.name] = stats
            log(f"  {src.name}: " + ", ".join(
                f"{k}={v}" for k, v in stats.items() if k not in ("status",) and v not in (0, False)
            ))
    finally:
        fetcher.close()
        store.close()
    return report
