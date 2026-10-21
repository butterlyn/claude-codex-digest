"""Delivery: the digest becomes a GitHub issue assigned to the repo owner.

The digest file is always written first (digest.py), so a failed delivery loses nothing.
Needs GITHUB_TOKEN and GITHUB_REPOSITORY, which GitHub Actions provides.
"""

from __future__ import annotations

import os

import httpx

API = "https://api.github.com"


class DeliveryError(Exception):
    pass


def issue_title(markdown: str) -> str:
    first = markdown.splitlines()[0].lstrip("# ").strip()
    return first if len(first) <= 120 else first[:117].rstrip() + "..."


def issue_body(markdown: str) -> str:
    return "\n".join(markdown.splitlines()[1:]).strip() + "\n"


def open_issue(markdown: str, label: str = "digest") -> str:
    repo = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN")
    if not repo or not token:
        raise DeliveryError("GITHUB_REPOSITORY and GITHUB_TOKEN must be set to open an issue")
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER") or repo.split("/")[0]
    payload = {
        "title": issue_title(markdown),
        "body": issue_body(markdown),
        "assignees": [owner],
        "labels": [label],
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        resp = httpx.post(f"{API}/repos/{repo}/issues", json=payload, headers=headers, timeout=30)
    except httpx.HTTPError as exc:
        raise DeliveryError(f"GitHub issue: {exc}") from exc
    if resp.status_code >= 300:
        raise DeliveryError(f"GitHub issue: HTTP {resp.status_code} {resp.text[:300]}")
    return resp.json()["html_url"]
