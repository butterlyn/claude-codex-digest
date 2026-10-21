"""Compare two versions of a page: was it only reformatted, and what changed, in few words."""

from __future__ import annotations

import difflib
import hashlib
import re

_LINK = re.compile(r"\[([^\]]*)\]\([^)\s]*(?:\s+\"[^\"]*\")?\)")  # [text](target) -> text
_AUTOLINK = re.compile(r"<(https?://[^>\s]+)>")  # <https://...> -> the url
_TAG = re.compile(r"<[^>\n]+>")  # html / mdx tags -> their quoted attribute values
_ATTR = re.compile(r'"([^"]*)"')
_WORD = re.compile(r"\w+")
_HEADING = re.compile(r"^#{1,6}\s+(.*\S)")


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def words(text: str) -> list[str]:
    """The words of a Markdown page, ignoring formatting, punctuation, case and link targets."""
    text = _LINK.sub(r" \1 ", text)
    text = _AUTOLINK.sub(r" \1 ", text)
    text = _TAG.sub(lambda m: " " + " ".join(_ATTR.findall(m.group(0))) + " ", text)
    return _WORD.findall(text.lower())


def is_format_only(old: str, new: str) -> bool:
    return words(old) == words(new)


def _clip(line: str, limit: int = 400) -> str:
    line = line.strip()
    return line if len(line) <= limit else line[:limit] + " ..."


def inline_diff(old: str, new: str, context: int = 6) -> str:
    """One line, with [-removed-] and {+added+} words and a few words of context."""
    a, b = old.split(), new.split()
    ops = difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
    out: list[str] = []
    for n, (tag, i1, i2, j1, j2) in enumerate(ops):
        if tag == "equal":
            seg = a[i1:i2]
            first, last = n == 0, n == len(ops) - 1
            if first and len(seg) > context:
                out.append("... " + " ".join(seg[-context:]))
            elif last and len(seg) > context:
                out.append(" ".join(seg[:context]) + " ...")
            elif not first and not last and len(seg) > 2 * context:
                out.append(" ".join(seg[:context]) + " ... " + " ".join(seg[-context:]))
            else:
                out.append(" ".join(seg))
            continue
        if i2 > i1:
            out.append("[-" + " ".join(a[i1:i2]) + "-]")
        if j2 > j1:
            out.append("{+" + " ".join(b[j1:j2]) + "+}")
    return _clip(" ".join(out), 600)


LONG_LINE = 3000  # longer lines are compared whole, never word by word (keeps diffs fast)


def _similar(a: str, b: str) -> float:
    if len(a) > LONG_LINE or len(b) > LONG_LINE:
        return 0.0
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return sm.ratio() if sm.real_quick_ratio() > 0.5 and sm.quick_ratio() > 0.5 else 0.0


def _line_key(line: str) -> str:
    """What the line matcher compares: long lines by prefix plus a hash of the whole line."""
    return line if len(line) <= LONG_LINE else line[:200] + "#" + content_hash(line)


def _pair(olds: list[str], news: list[str]) -> list[tuple[str | None, str | None]]:
    """Pair each removed line with the most similar added line, keeping order."""
    pairs: list[tuple[str | None, str | None]] = []
    j = 0
    for old in olds:
        best, best_ratio = None, 0.5
        for k in range(j, min(len(news), j + 5)):
            ratio = _similar(old, news[k])
            if ratio > best_ratio:
                best, best_ratio = k, ratio
        if best is None:
            pairs.append((old, None))
            continue
        pairs.extend((None, news[k]) for k in range(j, best))
        pairs.append((old, news[best]))
        j = best + 1
    pairs.extend((None, news[k]) for k in range(j, len(news)))
    return pairs


def _section(lines: list[str], idx: int) -> str | None:
    for i in range(min(idx, len(lines) - 1), -1, -1):
        match = _HEADING.match(lines[i])
        if match:
            return match.group(1)
    return None


def describe_change(old: str, new: str, max_chars: int = 3000) -> tuple[str, dict]:
    """A compact, readable diff grouped under the page's headings, plus line counts."""
    a, b = old.splitlines(), new.splitlines()
    out: list[str] = []
    stats = {"added_lines": 0, "removed_lines": 0, "changed_lines": 0}
    last_section: object = object()
    keys_a, keys_b = [_line_key(x) for x in a], [_line_key(x) for x in b]
    matcher = difflib.SequenceMatcher(None, keys_a, keys_b, autojunk=len(a) + len(b) > 20000)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        olds = [line for line in a[i1:i2] if line.strip()]
        news = [line for line in b[j1:j2] if line.strip()]
        if not olds and not news:
            continue
        section = _section(b, j1) if news else _section(a, i1)
        if section != last_section:
            out.append(f"## {section}" if section else "## (top of page)")
            last_section = section
        for o, n in _pair(olds, news):
            if o is not None and n is not None:
                out.append("changed: " + inline_diff(o, n))
                stats["changed_lines"] += 1
            elif o is not None:
                out.append("removed: " + _clip(o))
                stats["removed_lines"] += 1
            elif n is not None:
                out.append("added: " + _clip(n))
                stats["added_lines"] += 1
    text = "\n".join(out)
    if len(text) > max_chars:
        text = text[:max_chars].rsplit("\n", 1)[0] + "\n...(more changes not shown)"
    return text, stats
