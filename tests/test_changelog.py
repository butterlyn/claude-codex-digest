from engine.sources.changelog import (
    DATE_HEADING, MONTH_HEADING, VERSION_LINE, first_real_sentence, is_bugfix_only, split_entries,
)

CC = """# Claude Code changelog

**2.1.306**

* Fixed `claude -p` reporting "Not logged in"
* \\[VSCode] Fixed a crash on start

**2.1.305**

**Added**

* Added `sandbox.allowNestedUserNamespaces` so sandboxed commands can create user namespaces

**22 bug fixes**

* Fixed a hang

**2.1.303**

Bug fixes and reliability improvements
"""


def test_versions_split_and_bugfix_only():
    entries = dict(split_entries(CC, VERSION_LINE))
    assert list(entries) == ["2.1.306", "2.1.305", "2.1.303"]
    assert is_bugfix_only(entries["2.1.306"])
    assert not is_bugfix_only(entries["2.1.305"])
    assert is_bugfix_only(entries["2.1.303"])


def test_title_skips_section_labels_and_prefers_non_fix_lines():
    entries = dict(split_entries(CC, VERSION_LINE))
    assert first_real_sentence(entries["2.1.305"]).startswith("Added `sandbox.allowNestedUserNamespaces`")


NOTES = """# Release notes

## October 2026

### October 7, 2026

**Claude Haiku 5.5 launch**

We just launched Claude Haiku 5.5.

## September 2026

### September 28, 2026

**Sonnet**

### September 28, 2026

Second entry the same day.
"""


def test_date_headings_skip_month_headings_and_number_repeats():
    entries = split_entries(NOTES, DATE_HEADING, skip=MONTH_HEADING)
    assert [h for h, _ in entries] == ["October 7, 2026", "September 28, 2026", "September 28, 2026 (2)"]
    assert "September 2026" not in entries[0][1]
