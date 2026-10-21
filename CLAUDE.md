# claude-codex-digest

A personal digest of changes to the official Claude Code, Codex, Claude and ChatGPT docs,
changelogs and sites. `PROFILE.md` is the plan (sources, code filters, decision questions,
digest format); the engine in `engine/` follows it.

- Runs on demand from a Claude session with the `digest` skill (`/digest`), never on a
  schedule or in CI. Each run picks up from the last one through `data/` (page snapshots
  and `engine.db`), so always commit and push `data/` and `digests/` after a run.
- The engine's LLM calls go through `claude -p`, using the session's own Claude login.
- Test runs use `--data-dir <throwaway dir>`; never point a test at `data/`.
- Tests: `uv run --group dev pytest`. Keep/drop examples: `uv run python -m engine eval`.
- When the user says `missed: ...` or `noise: ...` about a digest, append a dated line naming
  the digest file to `data/feedback.md`, then commit and push. The first week's feedback is
  how the sources and decision questions get tuned.
