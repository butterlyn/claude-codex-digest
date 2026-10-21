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
    pages, skipped = parse_index(
        INDEX, "https://code.claude.com/docs/", ["https://code.claude.com/docs/en/changelog.md"]
    )
    assert pages == {"https://code.claude.com/docs/en/overview.md": "Overview"}
    assert skipped == 1


def test_clean_page_drops_the_index_note():
    md = "> ## Documentation Index\n> Fetch the index at: x\n> Use it.\n\n# Title\n\nBody\r\n"
    assert clean_page(md) == "# Title\n\nBody\n"


def test_keys_and_urls():
    url = "https://learn.chatgpt.com/docs/agent-configuration/rules.md"
    assert page_key(url) == "docs/agent-configuration/rules.md"
    assert human_url(url) == "https://learn.chatgpt.com/docs/agent-configuration/rules"
