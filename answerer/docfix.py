"""A docstring fix to the library, proposed as a pull request.

When a no is right about the prose and not the Lean (a docstring that says more, or other, than the
declaration does), the model may propose edits to that declaration's file. An edit replaces text
found exactly once, and both the text it replaces and the text it puts there lie inside one doc
comment (`/-- … -/` or `/-! … -/`): the new text has no comment delimiters, so it cannot reach the
code, and no double quotes (Tau Ceti's source guard refuses them in comments). Lines stay within
100 characters. `apply_edits` checks all this on the file as it is on the library's `main`; the
file is then built (only comments changed, but a build is cheap) before the branch is pushed.

A model may quote the doc comment's own closing `-/` (or opening `/--`, `/-!`) at the same end of
both texts. That delimiter stays where it was, so it is left out of the edit before the checks.
"""
from __future__ import annotations

MAX_EDITS, MAX_LEN, MAX_LINE = 3, 3000, 100
OPENERS, CLOSER = ("/--", "/-!"), "-/"


def doc_spans(text: str) -> list[tuple[int, int]]:
    """The doc comments' bodies, as (start, end) offsets: what lies between `/--` or `/-!` and the
    matching `-/` (block comments nest), outside strings and line comments."""
    out, i, n = [], 0, len(text)
    while i < n:
        if text.startswith("--", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text[i] == '"':
            i += 1
            while i < n and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
            i += 1
        elif text.startswith("/-", i):
            doc = text.startswith(("/--", "/-!"), i) and not text.startswith("/--/", i)
            start = i + (3 if doc else 2)
            depth, j = 1, i + 2
            while j < n and depth:
                if text.startswith("/-", j):
                    depth, j = depth + 1, j + 2
                elif text.startswith("-/", j):
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
            if doc and depth == 0:
                out.append((start, j - 2))
            i = j
        else:
            i += 1
    return out


def inside(spans: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(s <= start and end <= e for s, e in spans)


def unquote(old: str, new: str) -> tuple[str, str]:
    """`old` and `new` without a doc comment delimiter that both quote at the same end."""
    if old.endswith(CLOSER) and new.endswith(CLOSER):
        old, new = old[:-len(CLOSER)], new[:-len(CLOSER)]
    for d in OPENERS:
        if old.startswith(d) and new.startswith(d):
            old, new = old[len(d):], new[len(d):]
    return old, new


def apply_edits(text: str, edits: list[dict]) -> tuple[str | None, str | None]:
    """The file with `edits` made, or None and why not."""
    if not edits:
        return None, "no edits"
    if len(edits) > MAX_EDITS:
        return None, f"at most {MAX_EDITS} edits"
    for e in edits:
        old, new = unquote(e.get("old") or "", e.get("new") or "")
        if not old:
            return None, "an edit's old text is empty"
        if len(old) > MAX_LEN or len(new) > MAX_LEN:
            return None, f"an edit is longer than {MAX_LEN} characters"
        if "/-" in new or "-/" in new:
            return None, "the new text has comment delimiters"
        if '"' in new:
            return None, "the new text has a double quote, which the library's source guard refuses"
        if "\t" in new:
            return None, "the new text has a tab"
        k = text.count(old)
        if k != 1:
            return None, ("the old text was not found" if k == 0 else "the old text is found more than once") + \
                f": {old[:80]!r}"
        at = text.index(old)
        if not inside(doc_spans(text), at, at + len(old)):
            return None, f"the old text is not inside a doc comment: {old[:80]!r}"
        text = text[:at] + new + text[at + len(old):]
        if not inside(doc_spans(text), at, at + len(new)):
            return None, "the new text is not inside a doc comment"
        first, last = text.rfind("\n", 0, at) + 1, text.find("\n", at + len(new))
        for line in text[first:last if last >= 0 else len(text)].split("\n"):
            if len(line) > MAX_LINE:
                return None, f"a line would be longer than {MAX_LINE} characters"
    return text, None
