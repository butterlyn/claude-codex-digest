"""Polite HTTP: one shared client, a few requests per host at a time, retries on 429/5xx."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

USER_AGENT = (
    "claude-codex-digest/0.1 (personal docs-change digest; "
    "+https://github.com/butterlyn/claude-codex-digest)"
)
RETRY_STATUS = {429, 500, 502, 503, 504}


@dataclass
class Page:
    url: str
    status: int
    text: str
    final_url: str
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class Fetcher:
    def __init__(self, per_host: int = 4, timeout: float = 30.0, retries: int = 2):
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            follow_redirects=True,
        )
        self._per_host = per_host
        self._sems: dict[str, threading.Semaphore] = {}
        self._lock = threading.Lock()
        self.retries = retries
        self.requests = 0

    def _sem(self, url: str) -> threading.Semaphore:
        host = urlsplit(url).hostname or ""
        with self._lock:
            return self._sems.setdefault(host, threading.Semaphore(self._per_host))

    def get(self, url: str, headers: dict | None = None) -> Page:
        error = "no attempt"
        for attempt in range(self.retries + 1):
            wait = 2.0**attempt
            try:
                with self._sem(url):
                    resp = self._client.get(url, headers=headers)
                with self._lock:
                    self.requests += 1
            except httpx.HTTPError as exc:
                error = f"{type(exc).__name__}: {exc}"
            else:
                if resp.status_code in RETRY_STATUS and attempt < self.retries:
                    retry_after = resp.headers.get("retry-after", "")
                    if retry_after.isdigit():
                        wait = min(float(retry_after), 30.0)
                    error = f"HTTP {resp.status_code}"
                else:
                    ok = 200 <= resp.status_code < 300
                    return Page(
                        url=url,
                        status=resp.status_code,
                        text=resp.text if ok else "",
                        final_url=str(resp.url),
                        error=None if ok else f"HTTP {resp.status_code}",
                    )
            if attempt < self.retries:
                time.sleep(wait)
        return Page(url=url, status=0, text="", final_url=url, error=error)

    def get_many(self, urls: list[str], workers: int = 8) -> dict[str, Page]:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return dict(zip(urls, pool.map(self.get, urls)))

    def close(self) -> None:
        self._client.close()
