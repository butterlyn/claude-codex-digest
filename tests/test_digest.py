import json

from engine.digest import render


def row(i, kind, source, url, **meta):
    return {"id": i, "kind": kind, "source": source, "url": url, "metadata": json.dumps(meta)}


BY_ID = {
    "i1": row("chg:1", "changed_page", "claude-code-docs", "https://code.claude.com/docs/en/settings",
              page_title="Claude Code settings", snapshot="claude-code-docs/docs/en/settings.md"),
    "i2": row("entry:2", "entry", "claude-code-changelog", "https://code.claude.com/docs/en/changelog"),
    "i3": row("feed:3", "feed_item", "openai-news", "https://openai.com/index/x"),
}


def test_render_links_only_real_items_and_adds_history_for_docs_changes():
    data = {
        "headline": "One default changed",
        "sections": [
            {"group": "Claude Code", "entries": [
                {"text": "**Transcripts kept 14 days, not 30** - Raise `cleanupPeriodDays` if you need them.", "items": ["i1", "i2"]},
                {"text": "**Invented entry**", "items": ["i99"]},
            ]},
        ],
        "also": [{"text": "OpenAI posted about X", "items": ["i3"]}],
    }
    md, used = render("2026-10-22", data, BY_ID, read=3)
    assert md.startswith("# 2026-10-22 - One default changed")
    assert "- [ ] **Transcripts kept 14 days, not 30**" in md
    assert "[Claude Code settings](https://code.claude.com/docs/en/settings)" in md
    assert "/commits/main/data/snapshots/claude-code-docs/docs/en/settings.md" in md
    assert "Invented entry" not in md
    assert "- OpenAI posted about X. [OpenAI news](https://openai.com/index/x)" in md
    assert used == ["i1", "i2", "i3"]


def test_issue_title_and_body_split_the_digest():
    from engine.deliver import issue_body, issue_title
    md = "# 2026-10-22 - One default changed\n\n## Claude Code\n\n- [ ] x\n"
    assert issue_title(md) == "2026-10-22 - One default changed"
    assert issue_body(md).startswith("## Claude Code")
