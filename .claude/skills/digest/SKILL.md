---
name: digest
description: Run the Claude Code / Codex change digest now. Reads the official docs, changelogs and sites, compares them with the last run, filters, writes the digest, saves it to the repo and opens the GitHub issue. Use when the user types /digest, says "run the digest", or asks what changed in Claude Code, Codex or the Claude/ChatGPT apps since last time.
---

# Run the digest

This is the live run. Do every step in order without stopping to ask, unless a step fails
twice.

1. Install the engine: `uv sync --frozen`.
2. Pick up from the last run: `git pull --ff-only origin main`.
3. Run it: `uv run python -m engine run`. Use a timeout of 15 minutes. It fetches every source,
   compares with `data/snapshots/`, filters, asks Claude Haiku per item and Claude Sonnet for
   the digest (both through `claude -p`), and ends with a line `DIGEST: <path>`.
   Never add `--data-dir`: that is for test runs only. If the run fails, show the last 20
   lines of output and stop.
4. Save the state, or the next run starts over from the previous one:
   `git add data digests && git commit -m "digest <file name>" && git push origin HEAD:main`.
   Push to `main`, not a session branch: the next run clones `main`, so state saved anywhere
   else is lost and the same changes get reported again. The owner asked for this. If the
   push is rejected, `git pull --rebase origin main` and push again.
5. If the digest's first line does not end in "Nothing new", open an issue in
   `butterlyn/claude-codex-digest` with the GitHub MCP tool: title = the first line without
   "# ", body = the rest of the file, assignee `butterlyn`, label `digest`.
6. Reply with the digest exactly as written in the file (links intact), then one line: the
   issue link and "N items read". Include any "Couldn't read this run" line as it is.
