"""What the engine watches and its limits. PROFILE.md is the human version of this file."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LIVE_DATA = REPO / "data"
LIVE_DIGESTS = REPO / "digests"

TIMEZONE = "Australia/Perth"  # the digest is dated in the reader's time (AWST)
REPO_URL = (
    f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}"
    if os.environ.get("GITHUB_REPOSITORY") and os.environ.get("GITHUB_SERVER_URL")
    else "https://github.com/butterlyn/claude-codex-digest"
)

# Code filters and caps (PROFILE.md -> Code filters)
# The engine runs on demand and picks up from the last run. Changes are found by comparing
# with the copies the last run saved, so a gap of weeks loses nothing.
MAX_AGE_DAYS = 7  # first read of a source: dated entries older than this are history
AGE_GRACE_DAYS = 30  # later runs: entries dated this long before the last run are history
MAX_PAGES_PER_SITE = 400
MAX_ITEMS_PER_SOURCE = 300  # more changed pages than this on one site at once -> one rollup item
MAX_DECISIONS_PER_RUN = 400
DIGEST_CAP = 10
READING_CAP = 250  # most items the reading pass reads in one run

# A path segment that names a non-English locale: /ja/, /de/, /zh-CN/, /_llms/fr.txt ...
LOCALE_SEGMENT = re.compile(
    r"/(?:de|fr|it|ja|jp|es|es-419|ko|zh|zh-cn|zh-tw|zh-hans|zh-hant|ru|id|pt|pt-br|nl|pl|tr"
    r"|uk|vi|th|ar|hi|he|sv|da|fi|nb|cs|hu|ro|el|bg|ms)(?:/|\.|$)",
    re.IGNORECASE,
)

GROUPS = ("Claude Code", "Codex", "Claude & ChatGPT apps", "News & guides")


@dataclass(frozen=True)
class Source:
    name: str  # stable; used in ids and snapshot paths
    label: str  # how the digest names it
    group: str  # one of GROUPS
    kind: str  # which fetcher in engine/sources handles it
    url: str
    options: dict = field(default_factory=dict)


SOURCES: list[Source] = [
    Source(
        "claude-code-docs", "Claude Code docs", "Claude Code", "docs_site",
        "https://code.claude.com/docs/llms.txt",
        {
            "include_prefix": "https://code.claude.com/docs/en/",
            "exclude": ["https://code.claude.com/docs/en/changelog.md"],
        },
    ),
    Source(
        "claude-code-changelog", "Claude Code changelog", "Claude Code", "md_changelog",
        "https://code.claude.com/docs/en/changelog.md",
        {"npm_package": "@anthropic-ai/claude-code"},
    ),
    Source(
        "claude-app-docs", "Claude app docs", "Claude & ChatGPT apps", "docs_site",
        "https://claude.com/docs/llms.txt",
        {
            "include_prefix": "https://claude.com/docs/",
            "exclude": ["https://claude.com/docs/cowork/changelog.md"],
        },
    ),
    Source(
        "claude-desktop-changelog", "Claude Desktop changelog", "Claude & ChatGPT apps",
        "md_changelog", "https://claude.com/docs/cowork/changelog.md",
    ),
    Source(
        "claude-release-notes", "Claude release notes", "Claude & ChatGPT apps",
        "release_notes", "https://support.claude.com/en/articles/12138966-release-notes.md",
    ),
    Source(
        "claude-com-pages", "claude.com", "News & guides", "sitemap_new",
        "https://claude.com/sitemap.xml",
        {"host": "https://claude.com/"},
    ),
    Source(
        "anthropic-news", "Anthropic news", "News & guides", "sitemap_new",
        "https://www.anthropic.com/sitemap.xml",
        {"host": "https://www.anthropic.com/", "include_prefix": "https://www.anthropic.com/news/"},
    ),
    Source(
        "claude-com-guides", "claude.com guides", "News & guides", "page_set_text",
        "https://claude.com/resources/guides",
        {"sitemap": "https://claude.com/sitemap.xml", "include_prefix": "https://claude.com/resources/guides/"},
    ),
    Source(
        "anthropic-engineering", "Anthropic engineering blog", "News & guides", "page_set_text",
        "https://www.anthropic.com/engineering",
        {"index_page": "https://www.anthropic.com/engineering", "link_prefix": "/research/", "selector": "article"},
    ),
    Source(
        "anthropic-site", "anthropic.com", "News & guides", "sitemap_new",
        "https://www.anthropic.com/sitemap.xml",
        {"host": "https://www.anthropic.com/", "exclude_prefix": ["https://www.anthropic.com/news/"]},
    ),
    Source(
        "claude-help-center", "Claude Help Center", "Claude & ChatGPT apps", "sitemap_docs",
        "https://support.claude.com/sitemap.xml",
        {
            "include_prefix": "https://support.claude.com/en/articles/",
            "exclude": ["https://support.claude.com/en/articles/12138966-release-notes"],
            "crawl_delay": 1.0,  # the site's robots.txt asks for one request a second
        },
    ),
    Source(
        "claude-plans", "Claude plans", "Claude & ChatGPT apps", "page_text",
        "https://claude.com/pricing",
    ),
    Source(
        "codex-docs", "Codex docs", "Codex", "docs_site",
        "https://learn.chatgpt.com/docs/llms.txt",
        {"include_prefix": "https://learn.chatgpt.com/docs/"},
    ),
    Source(
        "chatgpt-codex-changelog", "ChatGPT & Codex changelog", "Codex", "rss",
        "https://learn.chatgpt.com/docs/changelog/rss.xml",
    ),
    Source(
        "openai-news", "OpenAI news", "News & guides", "rss",
        "https://openai.com/news/rss.xml",
    ),
    Source(
        "openai-site-codex", "openai.com", "News & guides", "sitemap_new",
        "https://openai.com/sitemap.xml",
        {
            "host": "https://openai.com/",
            "require_in_url": ["codex"],
            "exclude_prefix": ["https://openai.com/index/",  # articles come through the news feed
                               "https://openai.com/supply/"],  # the merch shop
            "children": ["/page/", "/product/", "/release/", "/learn-", "/engineering/",
                         "/openai-academy/", "/webinar/", "/chatgpt/", "/api/"],
            "fetch_pages": False,  # openai.com pages refuse automated reads; the sitemap does not
        },
    ),
    Source(
        "openai-dev-blog", "OpenAI developer blog", "News & guides", "docs_site",
        "https://developers.openai.com/blog/llms.txt",
        {"include_prefix": "https://developers.openai.com/blog/"},
    ),
    Source(
        "openai-cookbook-codex", "OpenAI Cookbook", "Codex", "docs_site",
        "https://developers.openai.com/cookbook/llms.txt",
        {"include_prefix": "https://developers.openai.com/cookbook/", "require_keyword": "codex"},
    ),
    Source(
        "openai-learn-codex", "OpenAI learning resources", "Codex", "docs_site",
        "https://developers.openai.com/learn/llms.txt",
        {
            "include_prefix": "https://developers.openai.com/learn/",
            "require_keyword": "codex",
            "track_links": True,  # videos and other non-Markdown entries
            "links_skip_prefix": "https://developers.openai.com/",  # those pages are watched already
        },
    ),
]

SOURCES_BY_NAME = {s.name: s for s in SOURCES}
