"""One fetcher per kind of source. Each returns items plus the snapshot updates to apply.

Snapshots are written only after the items are stored, so a crash in between means the
next run finds the same changes again, with the same ids.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from ..config import Source
from ..http import Fetcher
from ..items import Item
from ..snapshots import Snapshots


class SourceError(Exception):
    """The source could not be read this run; nothing about it should change."""


@dataclass
class Context:
    fetcher: Fetcher
    snapshots: Snapshots
    now: datetime


@dataclass
class SourceResult:
    items: list[Item] = field(default_factory=list)
    writes: dict[str, str] = field(default_factory=dict)  # snapshot key -> text
    deletes: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


Fetch = Callable[[Source, Context], SourceResult]


def registry() -> dict[str, Fetch]:
    from . import docs_site

    kinds: dict[str, Fetch] = {"docs_site": docs_site.fetch}
    try:  # kinds added in Stage 2
        from . import changelog, feeds, pages

        kinds.update(
            md_changelog=changelog.fetch_md_changelog,
            release_notes_html=changelog.fetch_release_notes_html,
            rss=feeds.fetch_rss,
            sitemap_new=pages.fetch_sitemap_new,
            page_text=pages.fetch_page_text,
        )
    except ImportError:
        pass
    return kinds
