"""Command line: python -m engine <command> [--data-dir DIR]

Without --data-dir the engine uses the live data in data/ and digests/. Use a throwaway
--data-dir for every test run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import filters, pipeline
from .store import Store, utcnow


def _log(msg: str) -> None:
    print(msg, flush=True)


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # titles carry non-ASCII text
    except AttributeError:
        pass
    parser = argparse.ArgumentParser(prog="python -m engine")
    parser.add_argument("--data-dir", type=Path, default=None, help="throwaway data dir for tests")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_fetch = sub.add_parser("fetch", help="fetch sources into the store")
    p_fetch.add_argument("--source", action="append", help="only this source (repeatable)")

    sub.add_parser("filter", help="run the code filters on items not yet looked at")

    p_show = sub.add_parser("show", help="list stored items")
    p_show.add_argument("--source")
    p_show.add_argument("--limit", type=int, default=50)
    p_show.add_argument("--body", action="store_true", help="print each item's body too")

    args = parser.parse_args(argv)
    paths = pipeline.paths_for(args.data_dir)
    now = utcnow()

    if args.cmd == "fetch":
        run_id = now.strftime("%Y%m%dT%H%M%SZ")
        _log(f"fetch -> {paths.data}")
        report = pipeline.run_fetch(paths, pipeline.select_sources(args.source), now, run_id, _log)
        total = sum(r.get("added", 0) for r in report.values())
        _log(f"new items stored: {total}")
        return 0

    if args.cmd == "filter":
        store = Store(paths.db)
        counts = filters.run_filters(store, now)
        store.close()
        _log("code filters: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
        return 0

    if args.cmd == "show":
        store = Store(paths.db)
        where, params = ("source = ?", (args.source,)) if args.source else ("1=1", ())
        rows = store.rows(where, params)[-args.limit:]
        for r in rows:
            flags = " ".join(x for x in (r["filtered_by"], r["route"]) if x)
            _log(f"{r['id']}  {r['kind']:<13} {r['title']}  {('[' + flags + ']') if flags else ''}")
            if args.body:
                _log("    " + r["url"])
                _log("    " + r["body"].replace("\n", "\n    "))
                _log("    meta: " + json.dumps(json.loads(r["metadata"]), ensure_ascii=False))
        _log(f"{len(rows)} item(s)")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
