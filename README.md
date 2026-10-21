# claude-codex-digest

When you run it, this reads the official Claude Code, Codex, Claude and ChatGPT docs,
changelogs and sites, keeps only what changed since the last run and would change how you use
them, and opens a GitHub issue with at most ten one-line items, each a checkbox for your
to-try list.

How it decides is written down in [PROFILE.md](PROFILE.md). Change the words there (and in
`engine/decide.py`) to change what it keeps.

## How it works

```
12 official sources -> store (stable ids, snapshots in data/) -> code filters
  -> Claude Haiku 5.5 answers two questions per item -> Claude Sonnet 5.5 writes the digest
  -> digests/YYYY-MM-DD-HHMM.md + a GitHub issue
```

- Docs pages are fetched as Markdown and compared with the copy the last run saved in
  `data/snapshots/`, so silent edits show up as a diff, however long ago the last run was. A
  page's git history is its change history.
- Code drops by fact: older than 7 days, formatting-only edits, bug-fix-only releases,
  non-English pages. The first read of a source only records a starting copy.
- The LLM calls go through Claude Code in headless mode (`claude -p`) on your Claude
  subscription, authenticated by the `CLAUDE_CODE_OAUTH_TOKEN` repository secret.

## Setup

1. On your computer, run `claude setup-token` and copy the token it prints.
2. In this repo on GitHub: Settings -> Secrets and variables -> Actions -> New repository
   secret. Name `CLAUDE_CODE_OAUTH_TOKEN`, value the token.
3. Run it: Actions -> digest -> Run workflow. Or comment `/digest` on any issue in this repo
   (handy from the GitHub mobile app); a rocket reaction means it started.

## Marking misses and noise

Reply on a digest issue with `missed: <what and where>` or `noise: <which line>`. Misses
are fixed by adding a source or rewording a decision question; noise by a code filter or a
sharper question.

## Commands

```sh
uv run python -m engine run                     # the daily run, without opening an issue
uv run python -m engine --data-dir /tmp/x run   # a throwaway test run (never touches data/)
uv run python -m engine eval                    # score the keep/drop examples
uv run python -m engine show --body             # list stored items
uv run --group dev pytest                       # tests
```
