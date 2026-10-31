"""The standard review: the one text a declaration's review box shows, and the rules that text keeps.

A declaration has one standard review, which AI agents approve or edit in place of each leaving a text of
its own (docs/superpowers/specs/2026-10-30-standard-reviews-design.md). This module owns what that text
is, so that the intake, the site build and the migration agree on it: its three parts, its version, the
check an edit must pass and the rubric cells a tick carries. It judges nothing about the mathematics.

A version is named by the hash of its text, and the hash is never stored, so an approval made before the
site shows a new text can still name it. The text is normalized first: GitHub hands back a comment body
with `\\r\\n` line endings, and an editor leaves trailing spaces, yet the intake must hash such a body to
the version the agent computed from its own file. mathlib-quality's review_site.py keeps a copy of
`normalize` and `version_of`, since two repositories cannot share a module; the vector in
tests/test_standard.py, which its tests hold too, pins the copies equal.

An edit goes live as soon as it passes `check`, so the check is all that stands between an agent and the
text every reader sees. It asks that the three parts are there, that a test the text lists exists, and
that an edit says what it changes and loses no reference, test or example Check without a stated reason.
A reference that is only reworded counts as kept, by how alike the two read. A first version, and a
restore, which puts back a text that passed the check when it was recorded, are not compared with a
parent: they get the first two questions only.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable, Sequence

SPEC = "tauceti-standard/1"
#: The part headings, each a line of its own, in this order.
HEADINGS = ("## What it says", "## References and tests", "## Lean subtleties")
#: How alike two references must read, by `SequenceMatcher`'s ratio, to be one reference reworded.
SIMILAR = 0.6
#: A Lean identifier, as the dataset spells declarations: Greek letters, subscripts and primes included.
IDENT = r"[^\W\d][\w'!?]*"
#: A bullet of Part 2. A test opens with the Lean name in backticks, an example Check with `Check *tag*`.
BULLET = re.compile(r"^-[ \t]+(\S.*)$")
TEST = re.compile(rf"^`({IDENT}(?:\.[\w'!?]+)*)`")
CHECK = re.compile(r"^Check\s+\*([^*]+)\*")
#: A cell: its axis alone, `axis n/a`, or `axis=state`.
CELL = re.compile(r"^([^\s=]+)(?:\s*=\s*(\S+)|\s+(n/a))?$")
CELL_STATES = {"checked": "checked", "na": "na", "n/a": "na"}


def normalize(text: str) -> str:
    """The text as its version is taken: `\\r\\n` and `\\r` as `\\n`, no whitespace at the end of a line, and no
    newline before the first line or after the last."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).strip("\n")


def version_of(text: str) -> str:
    """The version a text is: the first 16 hex digits of the SHA-256 of its normalized form."""
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()[:16]


def sections(text: str) -> tuple[str, list[tuple[str, str]]]:
    """The text cut at its part headings: what comes before the first, and then each heading with its body."""
    before: list[str] = []
    found: list[tuple[str, list[str]]] = []
    for line in normalize(text).split("\n"):
        if line in HEADINGS:
            found.append((line, []))
        else:
            (found[-1][1] if found else before).append(line)
    return "\n".join(before).strip(), [(heading, "\n".join(body).strip("\n")) for heading, body in found]


def parts(text: str) -> tuple[list[str] | None, list[str]]:
    """The three bodies of a review, in order, and no problems; or None and what is wrong: text before the
    first heading, a part missing or twice, the parts out of order, a part empty."""
    before, found = sections(text)
    names = [heading for heading, _ in found]
    problems = []
    if before:
        problems.append(f"there is text before `{HEADINGS[0]}`: every line must be in one of the three parts")
    for heading in HEADINGS:
        if heading not in names:
            problems.append(f"the part `{heading}` is missing")
        elif names.count(heading) > 1:
            problems.append(f"the part `{heading}` comes {names.count(heading)} times: it must come once")
    if len(set(names)) == len(names) and names != sorted(names, key=HEADINGS.index):
        problems.append("the parts are out of order: they must come as " + ", ".join(f"`{h}`" for h in HEADINGS))
    problems += [f"the part `{heading}` is empty: if there is nothing to say, say so in a line (`None.`)"
                 for heading, body in found if not body]
    return (None, problems) if problems else ([body for _, body in found], [])


@dataclass(frozen=True)
class Items:
    """What Part 2 lists: the text of each reference, the Lean names of the tests and the tags of the
    example Checks."""
    references: list[str]
    tests: list[str]
    checks: list[str]


def bullets(body: str) -> list[str]:
    """The `- ` bullets of a part's body, each on one line: lines indented under a bullet go on from it,
    and a blank line or a line of prose ends it."""
    out: list[list[str]] = []
    going = False
    for line in body.split("\n"):
        m = BULLET.match(line)
        if m:
            out.append([m[1]])
            going = True
        elif going and line[:1] in (" ", "\t") and line.strip():
            out[-1].append(line.strip())
        else:
            going = False
    return [" ".join(b) for b in out]


def items(text: str) -> Items:
    """The items of the text's Part 2. It reads what it finds, so a text with its parts wrong still has
    items, and a text with no Part 2 has none."""
    body = next((b for heading, b in sections(text)[1] if heading == HEADINGS[1]), "")
    references, tests, checks = [], [], []
    for bullet in bullets(body):
        if m := TEST.match(bullet):
            tests.append(m[1])
        elif m := CHECK.match(bullet):
            checks.append(m[1].strip())
        else:
            references.append(bullet)
    return Items(references, tests, checks)


def squash(text: str) -> str:
    """Text as references are compared: in lowercase, with only its letters, digits and spaces."""
    return "".join(c for c in " ".join(text.lower().split()) if c.isalnum() or c == " ")


def like(a: str, b: str) -> bool:
    """Whether two references read alike enough to be one reference reworded (`SIMILAR`). `autojunk` is
    off: from 200 characters on it sets aside the commonest letters, and a long citation with its title
    shortened and a page added then reads as nothing like itself."""
    return SequenceMatcher(None, squash(a), squash(b), autojunk=False).ratio() >= SIMILAR


def mentions(item: str, name: str) -> bool:
    """Whether `item` holds `name` whole: `Foo.bar` is in `Foo.bar.` but not in `Foo.bar_two`, `Foo.bar'`
    or `Foo.bar.baz`, which are other names."""
    return re.search(rf"(?<![\w'!?.]){re.escape(name)}(?![\w'!?]|\.\w)", item) is not None


def losses(old: Items, new: Items, dropped: Sequence[tuple[str, str]]) -> list[str]:
    """What `new` leaves out of `old` that no `dropped` line names, with a reason: a test or a Check is
    named by a line whose item holds its name or tag, a reference by one whose item reads alike."""
    said = [item for item, why in dropped if why.strip()]
    ask = "keep it, or give the reason on a `Dropped:` line that names it"
    problems = [f"the edit drops the test `{name}`: {ask}" for name in dict.fromkeys(old.tests)
                if name not in new.tests and not any(mentions(item, name) for item in said)]
    problems += [f"the edit drops the Check *{tag}*: {ask}" for tag in dict.fromkeys(old.checks)
                 if tag not in new.checks and not any(mentions(item, tag) for item in said)]
    problems += [f'the edit drops the reference "{ref}": {ask}' for ref in dict.fromkeys(old.references)
                 if not any(like(ref, other) for other in new.references + said)]
    return problems


def check(text: str, parent: str | None = None, dropped: Sequence[tuple[str, str]] = (),
          exists: Callable[[str], bool] = lambda n: True, note: str | None = None) -> list[str]:
    """What stops `text` becoming the review, as problems; none means it passes. Its three parts must be
    there, and each test it lists must exist (`exists`). An edit, which has the `parent` text it replaces,
    must also change something, carry a `note` saying what it adds or changes, and lose no test, example
    Check or reference of the parent unless a (item, reason) pair in `dropped` names it. The items are
    compared only when the parts are right: with a part missing, every item would be a loss."""
    bodies, problems = parts(text)
    if parent is not None:
        if not (note or "").strip():
            problems.append("an edit says what it adds or changes: give a note")
        if normalize(text) == normalize(parent):
            problems.append("the edit changes nothing: its text is its parent's")
    if bodies is not None:
        new = items(text)
        problems += [f"the test `{name}` is not a declaration that exists" for name in dict.fromkeys(new.tests)
                     if not exists(name)]
        if parent is not None:
            problems += losses(items(parent), new, dropped)
    return problems


def cells(spec: str, axes: Sequence[str]) -> tuple[dict[str, str] | None, str]:
    """The rubric cells of a tick, a write or an edit, from the comma-separated list its line gives. An
    axis is written alone or as `axis=checked` when it was looked at, and as `axis n/a`, `axis=na` or
    `axis=n/a` when it does not apply. Each axis appears once, since a tick is the evidence that every
    one was looked at. Returns the cells in the order of `axes` and an empty reason; or None and every
    reason the list is not that."""
    got: dict[str, str] = {}
    named: set[str] = set()
    reasons = []
    for entry in (" ".join(e.split()) for e in spec.split(",")):
        if not entry:
            continue
        m = CELL.match(entry)
        if not m:
            reasons.append(f"`{entry}` is not a cell: write an axis alone, `axis n/a`, `axis=na` or `axis=checked`")
            continue
        axis, given, na = m.groups()
        state = "na" if na else CELL_STATES.get(given or "checked")
        if axis not in axes:
            reasons.append(f"`{axis}` is not an axis of the rubric: its axes are {', '.join(axes)}")
            continue
        if axis in named:
            reasons.append(f"`{axis}` comes twice")
        elif state is None:
            reasons.append(f"`{entry}`: a cell is checked or n/a, and `{given}` is neither")
        else:
            got[axis] = state
        named.add(axis)
    missing = [axis for axis in axes if axis not in named]
    if missing:
        reasons.append(f"every axis needs a cell; missing: {', '.join(missing)}")
    return (None, "; ".join(reasons)) if reasons else ({axis: got[axis] for axis in axes}, "")


def kind_of(record: dict) -> str | None:
    """What a record is to the standard review. A "version" is a review (an accept) or a comment that
    carries the spec and a text of its own, and approves nothing; an "approval" is an accept that names
    the version it approves. Anything else, a plain accept of the earlier form among it, is None."""
    s = record.get("standard")
    if not isinstance(s, dict) or s.get("spec") != SPEC:
        return None
    accept = record.get("kind") == "review" and record.get("verdict") == "accept"
    if "approves" in s:
        return "approval" if accept and isinstance(s["approves"], str) and s["approves"] else None
    text = record.get("text")
    if (accept or record.get("kind") == "comment") and isinstance(text, str) and text.strip():
        return "version"
    return None


def act(record: dict) -> str:
    """What the record did to the review: "approved" a version, or for a version "restored" an earlier
    one, "edited" its parent, or "wrote" a first. A restore names its parent too, so it is told first."""
    kind = kind_of(record)
    if kind is None:
        raise ValueError("not a record of the standard review")
    s = record["standard"]
    if kind == "approval":
        return "approved"
    return "restored" if s.get("restores") else "edited" if s.get("parent") else "wrote"
