"""Calls Claude through Claude Code in headless mode (`claude -p`), on the user's subscription.

Authentication comes from the environment: CLAUDE_CODE_OAUTH_TOKEN (made with
`claude setup-token`) in GitHub Actions, or an existing login when run by hand.
Every call has no tools, no settings, no MCP servers and runs in an empty directory, so the
model sees only the prompt it is given. Answers are JSON checked against a schema.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass

CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
DECISION_MODEL = os.environ.get("DIGEST_DECISION_MODEL", "claude-haiku-5-5")
READING_MODEL = os.environ.get("DIGEST_READING_MODEL", "claude-sonnet-5-5")
_EMPTY_DIR = tempfile.mkdtemp(prefix="digest-llm-")


class LLMError(Exception):
    pass


@dataclass
class Answer:
    data: dict
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float  # list-price equivalent; on a subscription it counts against plan limits
    seconds: float


def ask_json(
    prompt: str, *, system: str, schema: dict, model: str, effort: str = "low",
    fallback_model: str | None = None, timeout: float = 180, retries: int = 1,
) -> Answer:
    cmd = [
        CLAUDE_BIN, "-p", "--model", model, "--effort", effort,
        "--tools", "", "--setting-sources", "", "--strict-mcp-config",
        "--disable-slash-commands", "--no-session-persistence",
        "--system-prompt", system, "--json-schema", json.dumps(schema),
        "--output-format", "json",
    ]
    if fallback_model:
        cmd += ["--fallback-model", fallback_model]
    error = "no attempt"
    for attempt in range(retries + 1):
        started = time.monotonic()
        try:
            proc = subprocess.run(
                cmd, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=_EMPTY_DIR,
            )
        except subprocess.TimeoutExpired:
            error = f"timed out after {timeout:.0f}s"
            continue
        try:
            envelope = json.loads(proc.stdout)
        except ValueError:
            error = f"exit {proc.returncode}: {(proc.stderr or proc.stdout).strip()[:300]}"
            time.sleep(2 * (attempt + 1))
            continue
        if envelope.get("is_error"):
            error = str(envelope.get("result") or envelope.get("subtype") or "error")[:300]
            time.sleep(2 * (attempt + 1))
            continue
        data = envelope.get("structured_output")
        if data is None:
            try:
                data = json.loads(envelope.get("result") or "")
            except ValueError:
                error = "no structured output"
                continue
        usage = envelope.get("usage") or {}
        used = envelope.get("modelUsage") or {}
        return Answer(
            data=data,
            model=next(iter(used), model),
            input_tokens=int(usage.get("input_tokens", 0))
            + int(usage.get("cache_creation_input_tokens", 0))
            + int(usage.get("cache_read_input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            cost_usd=float(envelope.get("total_cost_usd") or 0.0),
            seconds=round(time.monotonic() - started, 1),
        )
    raise LLMError(error)
