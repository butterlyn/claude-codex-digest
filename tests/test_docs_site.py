from engine.sources.docs_site import clean_page, human_url, page_key, parse_index

INDEX = """# Docs
- [Overview](https://code.claude.com/docs/en/overview.md): intro
- [Changelog](https://code.claude.com/docs/en/changelog.md): notes
- [Overview again](https://code.claude.com/docs/en/overview.md): duplicate
- [French (228 pages)](https://code.claude.com/docs/_llms/fr.txt): not a page
- [Japanese page](https://code.claude.com/docs/ja/overview.md): other locale
- [Elsewhere](https://example.com/docs/en/x.md): other site
"""


def test_parse_index_keeps_english_pages_under_prefix_once():
    pages, skipped, links = parse_index(
        INDEX, "https://code.claude.com/docs/", ["https://code.claude.com/docs/en/changelog.md"]
    )
    assert pages == {"https://code.claude.com/docs/en/overview.md": "Overview"}
    assert skipped == 1
    assert links == {}


def test_parse_index_keyword_filter_and_other_links():
    index = """- [Codex prompting guide](https://developers.openai.com/cookbook/examples/codex/guide.md): tips
- [Image evals](https://developers.openai.com/cookbook/examples/image_evals.md): not about it
- [Codex in JetBrains IDEs](https://www.youtube.com/watch?v=1): How to use Codex in JetBrains
"""
    pages, _, links = parse_index(index, "https://developers.openai.com/cookbook/", [], keyword="codex")
    assert list(pages) == ["https://developers.openai.com/cookbook/examples/codex/guide.md"]
    assert links == {"https://www.youtube.com/watch?v=1": ("Codex in JetBrains IDEs", "How to use Codex in JetBrains")}


def test_clean_page_drops_the_index_note():
    md = "> ## Documentation Index\n> Fetch the index at: x\n> Use it.\n\n# Title\n\nBody\r\n"
    assert clean_page(md) == "# Title\n\nBody\n"


def test_keys_and_urls():
    url = "https://learn.chatgpt.com/docs/agent-configuration/rules.md"
    assert page_key(url) == "docs/agent-configuration/rules.md"
    assert human_url(url) == "https://learn.chatgpt.com/docs/agent-configuration/rules"


def test_html_responses_are_not_markdown():
    from engine.http import Page
    from engine.sources.docs_site import is_markdown
    assert not is_markdown(Page("u", 200, "<!DOCTYPE html><html>", "u", None, "text/html; charset=utf-8"))
    assert is_markdown(Page("u", 200, "# Title\n", "u", None, "text/markdown; charset=utf-8"))


def test_signed_cdn_query_strings_are_dropped():
    md = "![x](https://mintlify.s3.mintcdn.com/a/b.png?fit=max&s=abc123)\n"
    assert clean_page(md) == "![x](https://mintlify.s3.mintcdn.com/a/b.png)\n"
