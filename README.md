# claude-codex-digest

When you run it, this reads the official Claude Code, Codex, Claude and ChatGPT docs,
changelogs, help center, guides and sites, keeps only what changed since the last run and
matters to how you use them (new features and defaults, and new or updated guides and
explainers), and opens a GitHub issue with at most ten one-line items, each a checkbox for
your to-try list.

How it decides is written down in [PROFILE.md](PROFILE.md). Change the words there (and in
`engine/decide.py`) to change what it keeps.

## How it works

```
17 official sources -> store (stable ids, snapshots in data/) -> code filters
  -> Claude Haiku 5.5 answers two questions per item -> Claude Sonnet 5.5 writes the digest
  -> digests/YYYY-MM-DD-HHMM.md + a GitHub issue
```

- Docs pages are fetched as Markdown and compared with the copy the last run saved in
  `data/snapshots/`, so silent edits show up as a diff, however long ago the last run was. A
  page's git history is its change history.
- Code drops by fact: older than 7 days, formatting-only edits, bug-fix-only releases,
  non-English pages. The first read of a source only records a starting copy.
- The LLM calls go through Claude Code in headless mode (`claude -p`) on your Claude
  subscription, using the login of the Claude session that runs it.

## Running it

In the Claude app, start a Claude Code session on this repo and type `/digest`. The session
runs the engine, commits `data/` and `digests/`, opens the issue and replies with the digest.
There is no schedule; each run picks up from the last one.

## Marking misses and noise

Tell the session `missed: <what and where>` or `noise: <which line>` (saved to
`data/feedback.md`), or reply on the issue. Misses are fixed by adding a source or rewording
a decision question; noise by a code filter or a sharper question.

## Commands

```sh
uv run python -m engine run                     # the live run (what /digest does first)
uv run python -m engine --data-dir /tmp/x run   # a throwaway test run (never touches data/)
uv run python -m engine eval                    # score the keep/drop examples
uv run python -m engine show --body             # list stored items
uv run --group dev pytest                       # tests
```
