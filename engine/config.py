"""What the engine watches and its limits. PROFILE.md is the human version of this file."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LIVE_DATA = REPO / "data"
LIVE_DIGESTS = REPO / "digests"

# Code filters and caps (PROFILE.md -> Code filters)
MAX_AGE_DAYS = 7
MAX_PAGES_PER_SITE = 400
MAX_ITEMS_PER_SOURCE = 100
MAX_DECISIONS_PER_RUN = 150
DIGEST_CAP = 10

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
        "codex-cli-releases", "Codex CLI", "Codex", "github_releases",
        "https://github.com/openai/codex/releases", {"repo": "openai/codex"},
    ),
    Source(
        "openai-news", "OpenAI news", "News & guides", "rss",
        "https://openai.com/news/rss.xml",
    ),
]

SOURCES_BY_NAME = {s.name: s for s in SOURCES}
