from engine.diffing import describe_change, inline_diff, is_format_only, words


def test_format_only_ignores_punctuation_emphasis_case_and_link_targets():
    old = "Run **`claude`** in your terminal. See [setup](/docs/en/setup)."
    new = "Run `claude` in your terminal; see [setup](/docs/en/install#setup)"
    assert is_format_only(old, new)


def test_one_word_value_change_is_not_format_only():
    assert not is_format_only("The default is `true`.", "The default is `false`.")


def test_tag_attribute_text_counts_as_words():
    assert words('<Tab title="macOS">x</Tab>') == ["macos", "x"]


def test_inline_diff_marks_the_changed_word():
    out = inline_diff("The default model is sonnet for all plans", "The default model is opus for all plans")
    assert "[-sonnet-]" in out and "{+opus+}" in out


def test_describe_change_groups_under_heading_and_counts_lines():
    old = "# Page\n\n## Flags\n\n- `--fast` runs fast\n"
    new = "# Page\n\n## Flags\n\n- `--fast` runs faster\n- `--slow` runs slow\n"
    text, stats = describe_change(old, new)
    assert text.startswith("## Flags")
    assert stats["changed_lines"] == 1 and stats["added_lines"] == 1
