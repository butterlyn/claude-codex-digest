"""The daily run: fetch -> store -> code filters -> decision pass -> reading pass -> digest."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import decide, deliver, digest, filters
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


def run_all(paths: Paths, now: datetime, log: Log, send: bool = False) -> int:
    """The daily run. A source that fails is named at the bottom of the digest and the rest
    carries on. Returns 2 when the digest could not be delivered, else 0."""
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    started = time.monotonic()
    store = Store(paths.db)
    last_run = store.last_run_started(now)  # this run picks up from there
    store.start_run(run_id, now)
    store.close()
    log(f"last run: {last_run.isoformat() if last_run else 'none (first run)'}")

    log("fetch:")
    report = run_fetch(paths, list(SOURCES), now, run_id, log)
    failed_sources = [name for name, r in report.items() if r.get("status", "ok") != "ok"]

    store = Store(paths.db)
    try:
        dropped = filters.run_filters(store, now, last_run)
        log("code filters: " + ", ".join(f"{k}={v}" for k, v in dropped.items()))
        routes = decide.run_decisions(store)
        log("decision pass: " + ", ".join(f"{k}={v}" for k, v in routes.items()))
        notes = [f"{SOURCES_BY_NAME[n].label} ({report[n]['status'].removeprefix('error: ').removeprefix('SourceError: ')[:80]})" for n in failed_sources]
        result = digest.write_digest(store, paths.digests, now, unreadable=notes, last_run=last_run)
        log(f"digest {result.path.name}: " + ", ".join(f"{k}={v}" for k, v in result.stats.items()))

        delivered, code = None, 0
        if send and result.included:
            try:
                delivered = deliver.open_issue(result.markdown)
                log(f"delivered: {delivered}")
            except deliver.DeliveryError as exc:
                log(f"delivery failed (the digest file is saved): {exc}")
                code = 2
        elif send:
            log("nothing new: no issue opened")

        stats = {
            "sources": {k: {kk: v for kk, v in r.items() if kk != "status"} | {"status": r.get("status", "ok")}
                        for k, r in report.items()},
            "filters": dropped, "decisions": routes, "digest": result.stats,
            "delivered": delivered, "seconds": round(time.monotonic() - started, 1),
        }
        store.finish_run(run_id, now, stats)
    finally:
        store.close()
    if failed_sources:
        log(f"sources that failed: {', '.join(failed_sources)}")
    return code
