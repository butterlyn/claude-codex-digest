"""HTML helpers: page to Markdown, and a page's title, description and publish date."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from markdownify import markdownify

TITLE_SUFFIX = re.compile(r"\s*(?:\||\\|—|–|-)\s*(?:Claude by Anthropic|Anthropic|Claude|OpenAI)\s*$")


def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def to_markdown(node) -> str:
    for tag in node.find_all(["script", "style", "noscript", "svg", "button", "form", "iframe"]):
        tag.decompose()
    md = markdownify(str(node), heading_style="ATX", bullets="-", strip=["img"])
    lines = [line.rstrip() for line in md.replace("\xa0", " ").splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    for fmt in (None, "%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00")) if fmt is None else datetime.strptime(value, fmt)
        except ValueError:
            continue
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def _meta(doc: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = doc.find("meta", attrs={"property": name}) or doc.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def _json_ld_date(doc: BeautifulSoup) -> str | None:
    for tag in doc.find_all("script", attrs={"type": "application/ld+json"}):
        match = re.search(r'"datePublished"\s*:\s*"([^"]+)"', tag.string or "")
        if match:
            return match.group(1)
    return None


def page_meta(html: str) -> dict:
    """Title, description, publish date and the opening text of an article-like page."""
    doc = soup(html)
    title = _meta(doc, "og:title", "twitter:title") or (doc.title.string if doc.title and doc.title.string else "")
    title = TITLE_SUFFIX.sub("", " ".join(title.split()))
    published = parse_datetime(
        _meta(doc, "article:published_time", "datePublished", "publish_date") or _json_ld_date(doc)
    )
    if published is None:
        time_tag = doc.find("time", attrs={"datetime": True})
        published = parse_datetime(time_tag["datetime"]) if time_tag else None
    description = _meta(doc, "description", "og:description", "twitter:description") or ""
    main = doc.find("article") or doc.find("main") or doc.body
    text = ""
    if main is not None:
        for tag in main.find_all(["script", "style", "noscript", "svg", "nav", "header", "footer", "button", "form"]):
            tag.decompose()
        text = " ".join(main.get_text(" ", strip=True).split())
    return {"title": title, "description": description, "published": published, "text": text[:1500]}


def json_or_none(text: str):
    try:
        return json.loads(text)
    except ValueError:
        return None
