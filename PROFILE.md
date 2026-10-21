# Signal engine profile

<!-- Written by the build-signal-engine interview. Every stage reads this file. Edit it
     freely; the engine follows it. -->

## What I keep up with

Changes to **Claude Code** and **Codex** (features, commands, flags, settings, defaults,
deprecations), plus the Claude and ChatGPT apps' features and the official guides and
launch posts about them. When I know on the day, I **save the item to my to-try list** and
update my setup that week. A silent edit to a docs page counts as much as an announced
change.

## Sources

Data platform: none. Picked per source: every source below is free and fetched over plain
HTTP (Markdown twins, RSS, sitemaps).

| Source | What it is | How it is pulled | Why it is here |
|---|---|---|---|
| Claude Code docs | ~264 English pages on code.claude.com/docs | page list from `llms.txt`, each page's `.md` twin, diffed against yesterday's copy | R1.2: the thing I found out late was a silent docs change |
| Claude Code changelog | version notes (`2.1.x`) | `code.claude.com/docs/en/changelog.md`, split on version lines; release dates from the npm registry | R2.1: Claude Code |
| Claude app docs | ~279 pages on claude.com/docs, including the Claude Desktop changelog | same as the Claude Code docs; the Desktop changelog is split into versions | R2.1: Claude apps |
| Claude release notes | support.claude.com release notes | the article's `.md` twin, split on its dated headings | R2.1: Claude apps |
| claude.com new pages | guides, articles, launch posts, product pages | `sitemap.xml`: new English URLs, with title and date read from the page | R2.3: the Code Review GA article |
| Anthropic news | anthropic.com/news | `sitemap.xml`: new `/news/` URLs | R2.1: company news and blogs |
| Claude plans | claude.com/pricing | page text, diffed | R2.1: plans and usage limits |
| Codex docs | ~200 pages on learn.chatgpt.com/docs (developers.openai.com/codex redirects here) | page list from the Codex `llms.txt`, each page's `.md` twin, diffed | R1.2: silent docs changes |
| ChatGPT & Codex changelog | the official changelog feed | RSS | R2.1: Codex and the ChatGPT apps |
| Codex CLI releases | release notes for openai/codex | GitHub releases API (free; pre-releases skipped) | R2.1: Codex CLI flags and commands only appear here |
| OpenAI news | openai.com/news | RSS | R2.1: company news and blogs |

Left out, and why:
- **help.openai.com** (ChatGPT release notes, the Codex changelog article) and **openai.com**
  pages refuse automated requests (HTTP 403). The ChatGPT & Codex changelog feed carries the
  same changes.
- **Claude API docs and release notes**: not one of the surfaces I use.
- **Communities** (GitHub issues, Reddit, HN): official sources only.

## Code filters

<!-- R2.4: facts only. Each one a number or a pattern. -->
- First read of a source is a **baseline**: pages and sitemaps are recorded, not reported; dated
  entries (changelogs, release notes, feeds) from the last 7 days are reported.
- Max age: on the first run, dated entries older than **7 days** are dropped. After that every
  run picks up from the last one: anything new since then counts, however long ago that was,
  except entries dated more than **30 days** before the last run.
- English only: localized paths (`/ja/`, `/de/`, `/zh-CN/`, ...) are skipped.
- Format-only edits: a page change whose words are identical once whitespace, punctuation,
  Markdown formatting and link targets are removed is dropped. One-word changes are **not**
  dropped in code, because a changed default can be one word.
- Bug-fix-only releases: a changelog version whose every bullet is a fix, or whose whole note is
  a stock "Bug fixes and reliability improvements", is dropped. Codex CLI pre-releases are skipped.
- Engagement floor: none (official sources have no votes).
- Caps: at most 400 pages per docs site per run; more than 300 changes on one source at once
  become a single rollup item; at most 400 decision calls and 250 items read per run.

## The decision question(s)

<!-- One thing per question. Written from the examples below. Asked per item by
     Claude Haiku 5.5 with structured output. -->

1. **Relevance (score 1-5):** How much could this change what I do with Claude Code, Codex,
   or the Claude and ChatGPT apps?
   1. Not about these tools: company news, policy, research, funding, customer stories,
      enterprise- or admin-only settings (SSO, admin console, compliance, org billing),
      ChatGPT features unrelated to Codex.
   2. About these tools, but nothing I would do differently: rewording, reorganised pages,
      marketing copy.
   3. A small detail worth knowing: a clarified behaviour, a minor option, a new example.
   4. Something I could try or should adjust: a new or changed command, flag, setting, hook,
      integration or feature, or a new official guide, including ones limited to some plans.
   5. Changes how I work now: a changed default, a removed or deprecated option, a breaking
      change, a major new feature.

   An unfamiliar feature, model or product name is not a reason to score lower.
2. **Reports something new and concrete (yes/no):** a new, changed or removed feature,
   command, flag, setting, default, limit or price, or a newly published guide or launch.
   Typo and formatting fixes, bug-fix-only notes, rewording that keeps the meaning, opinions
   and marketing are "no".

Routing: drop when relevance is 1, or "new" is no and relevance is 2 or less; keep when
relevance is 4 or more and "new" is yes; everything else goes to the reading pass.
<!-- R2.5: missing something big is worse than wasting time, so only sure drops are dropped. -->

### Keep examples
<!-- R2.3. Mostly kinds rather than real items, so Stage 4 also scores a sample of real
     items sorted by me. -->
- A changed default on a Claude Code or Codex docs page, with no announcement
- A new slash command, CLI flag, hook or setting in a changelog or docs page
- A post launching a new Claude Code or Codex feature
- Real: "Code Review is now generally available", claude.com, Oct 15 2026
  (https://claude.com/resources/articles/code-review-is-now-generally-available)

### Drop examples
- Policy, research and funding posts on anthropic.com/news and openai.com/news
- Customer stories and case studies
- ChatGPT features unrelated to Codex (images, voice, shopping)
- Enterprise- or admin-only changes (SSO, admin console, compliance, org billing)

## The digest

- Where I read it: a GitHub issue in `butterlyn/claude-codex-digest`, assigned to me, each
  time I run it; also committed as `digests/YYYY-MM-DD-HHMM.md` (Perth time). A run with
  nothing new writes the file but opens no issue.
- Length cap: 10 items
- Format: grouped as Claude Code, Codex, Claude & ChatGPT apps, News & guides. Each item is
  one checkbox line for my to-try list: `- [ ] **What changed** - what to try. [page](url)`.
  A docs change shows before -> after when it is short.
- Extras: none

## Models

- Claude subscription through Claude Code headless (`claude -p`), authenticated with a
  token from `claude setup-token`, stored as the repo secret `CLAUDE_CODE_OAUTH_TOKEN`
- Decision pass: Claude Haiku 5.5, one call per item, structured output
- Reading pass: Claude Sonnet 5.5, one call per run

## Runs

- On demand, no schedule: Actions -> digest -> Run workflow, or a comment starting with
  `/digest` on any issue in the repo. Each run covers everything since the last run that
  finished.
- Shadow week: the first seven runs. I reply on each issue with `missed: ...` or
  `noise: ...`.
