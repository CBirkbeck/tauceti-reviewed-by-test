"""The standard review: the one text a declaration's review box shows, and the rules that text keeps.

A declaration has one standard review, which AI agents approve or edit in place of each leaving a text of
its own (docs/superpowers/specs/2026-10-30-standard-reviews-design.md). This module owns what that text
is, so that the intake, the site build and the migration agree on it: its three parts, its version, the
check an edit must pass, the rubric cells a tick carries, and which version is current and who approved it.
It judges nothing about the mathematics.

A version is named by the hash of its text. Its record does not store that hash, which is computed from
the text wherever it is needed, so an approval made before the site shows a new text can still name it;
what names a version holds its hash in full (an approval's `approves`, an edit's `parent`, a shard's
`version`). The text is normalized first: GitHub hands back a comment body
with `\\r\\n` line endings, and an editor leaves trailing spaces, yet the intake must hash such a body to
the version the agent computed from its own file. mathlib-quality's review_site.py keeps a copy of
`normalize` and `version_of`, since two repositories cannot share a module; the vector in
tests/test_standard.py, which its tests hold too, pins the copies equal.

An edit goes live as soon as it passes `check`, so the check is all that stands between an agent and the
text every reader sees. It asks that the three parts are there, that a test the text lists exists, and
that an edit says what it changes and loses no reference, test or example Check without a stated reason.
A reference that is only reworded counts as kept, by how alike the two read, and so does one with more
said after it, since the new text then holds the old. A reference keeps one of the parent's by likeness,
or else two tags of the Stacks Project, which read alike, would let an edit drop either; one that holds
several whole, references merged, keeps them all. A first version, and a restore, which puts back a
text that passed the check when it was recorded, are not compared with a parent: they get the first two
questions only.

Which version is current is read from a declaration's records alone. The caller says, of each, whether it
applies to the declaration as it is now, was withdrawn, or was superseded by its reviewer's later review
(`Seen`): the intake reads that from the store, the site build from evidence-core. Records go in time by
`order`, which the intake reads a line's store by too, so that the two agree on records made in one second.
Only an AI approves. A person says yes with the page's form, and that yes is no approval of the text.
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
#: A bullet of Part 2, opened by `- `, `* ` or `+ `. A test opens with the Lean name in backticks, an example
#: Check with `Check *tag*`.
BULLET = re.compile(r"^[-*+][ \t]+(\S.*)$")
TEST = re.compile(rf"^`({IDENT}(?:\.[\w'!?]+)*)`")
CHECK = re.compile(r"^Check\s+\*([^*]+)\*")
#: A Check of Part 2, by how the roadmap names it (`check_of`): its tag in asterisks (`Check *test_two*`), the Lean name
#: it gives in backticks (`Check `Foo.bar_two``), or, for a Check the roadmap gives in prose, its first words in quotes
#: (`Check "The constant S₃ over ℂ …"`).
CHECK_ANY = re.compile(r'^Check\s+(?:\*(?P<tag>[^*]+)\*|`(?P<name>[^`]+)`|"(?P<quote>[^"]+)"|“(?P<quote2>[^”]+)”)')
#: What a Check found, after the spaced dash that ends its name and where it is: it passes, it is missing, or it has
#: `sorry`.
RESULT = re.compile(r"^[^—]*?\s(?:—|--)\s+(passes|missing|sorry)\b", re.I)
#: Where a Check is carried, after its name: `, ` and a declaration's name or a place `path:line`, in backticks.
CARRIER = re.compile(r"^,\s*(?:by\s+|in\s+)?`([^`]+)`")
#: A Lean name as a test or a carrier gives it, whole.
LEAN_NAME = re.compile(rf"^{IDENT}(?:\.[\w'!?]+)*$")
#: The guide's length of a text, in words (`words`): a reading guide, not a paper.
WORDS = (150, 400)
#: A Markdown link's target, `](…)` with its title, which `words` and `unlinked` set aside.
LINK_TARGET = re.compile(r"\]\((?:[^()\s]|\([^()\s]*\))*(?:\s+\"[^\"]*\")?\)")
#: A commit in a GitHub address (`/blob/<sha>/`, `/tree/<sha>/`, `/commit/<sha>`), which `unlinked` sets aside.
LINK_COMMIT = re.compile(r"(/(?:blob|tree|commit|blame)/)[0-9a-f]{7,40}\b")
#: A roadmap target as a text names one: `target `name``, `the target `name``, in a line or a bullet that speaks of a
#: roadmap (`targets`); the name a word, a Lean name or a label, so that a map's target (`X ⟶ Y`) is none.
TARGET = re.compile(r"\b[Tt]argets?\s*:?\s+`([\w.'!?\-]+)`")
#: A cell: its axis alone, `axis n/a`, or `axis=state`.
CELL = re.compile(r"^([^\s=]+)(?:\s*=\s*(\S+)|\s+(n/a))?$")
CELL_STATES = {"checked": "checked", "na": "na", "n/a": "na"}
#: Where a record of a line of a comment came from, at the end of its origin's ref: the comment's id and the line. The
#: intake writes it `<comment url>/line/<k>`, the url GitHub's (`…#issuecomment-<id>`) or evidence-store's
#: (`<repo>#<issue>/comment/<id>`).
FROM_LINE = re.compile(r"(?:#issuecomment-|/comment/)(\d+)/line/(\d+)$")


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
    """The bullets of a part's body, each on one line: lines indented under a bullet go on from it, and a
    blank line or a line of prose ends it."""
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


@dataclass(frozen=True)
class Check:
    """A Check a bullet of Part 2 records (`check_of`): how the roadmap names it (`kind`: "tag", "name" or "prose") and
    by what (`key`: the tag, the Lean name, or the first words quoted), its `result` (passes, missing, sorry; None when
    the bullet gives none) and what carries it, as the bullet gives it after the name (`carrier`: a declaration's name,
    or a place `path:line`; None)."""
    kind: str
    key: str
    result: str | None
    carrier: str | None

    @property
    def label(self) -> str:
        return {"tag": f"*{self.key}*", "name": f"`{self.key}`", "prose": f'"{self.key}"'}[self.kind]


def check_of(bullet: str) -> Check | None:
    """The Check a bullet of Part 2 records, if it records one: a bullet that opens with `Check` and the name the roadmap
    gives it (`CHECK_ANY`)."""
    m = CHECK_ANY.match(bullet)
    if m is None:
        return None
    kind = "tag" if m["tag"] is not None else "name" if m["name"] is not None else "prose"
    key = " ".join((m["tag"] or m["name"] or m["quote"] or m["quote2"] or "").split())
    rest = bullet[m.end():]
    carried = CARRIER.match(rest)
    result = RESULT.match(rest)
    return Check(kind, key, result[1].lower() if result else None, carried[1].strip() if carried else None)


def part_two(text: str) -> list[str]:
    """The bullets of the text's Part 2 (`bullets`); none when it has no Part 2."""
    return bullets(next((b for heading, b in sections(text)[1] if heading == HEADINGS[1]), ""))


def items(text: str) -> Items:
    """The items of the text's Part 2. It reads what it finds, so a text with its parts wrong still has
    items, and a text with no Part 2 has none."""
    references, tests, checks = [], [], []
    for bullet in part_two(text):
        if m := TEST.match(bullet):
            tests.append(m[1])
        elif c := check_of(bullet):
            checks.append(c.key)
        else:
            references.append(bullet)
    return Items(references, tests, checks)


def checks_of(text: str) -> list[Check]:
    """The Checks the text's Part 2 records, in order."""
    return [c for b in part_two(text) if not TEST.match(b) and (c := check_of(b)) is not None]


def squash(text: str) -> str:
    """Text as references are compared: in lowercase, with only its letters, digits and spaces."""
    return "".join(c for c in " ".join(text.lower().split()) if c.isalnum() or c == " ")


def likeness(a: str, b: str) -> float:
    """How alike two references read, from 0 to 1: `SequenceMatcher`'s ratio of their squashed texts. `autojunk`
    is off: from 200 characters on it sets aside the commonest letters, and a long citation with its title
    shortened and a page added then reads as nothing like itself."""
    return SequenceMatcher(None, squash(a), squash(b), autojunk=False).ratio()


def like(a: str, b: str) -> bool:
    """Whether two references read alike enough to be one reference reworded (`SIMILAR`)."""
    return likeness(a, b) >= SIMILAR


def plain(ref: str) -> str:
    """A reference as references are told apart: squashed, and the spaces that taking out its punctuation left
    closed up."""
    return " ".join(squash(ref).split())


def extends(new: str, old: str) -> bool:
    """Whether reference `new` is `old` with more said: the plain text of `old` is inside that of `new`. A
    clause said after a reference can leave it reading too little like itself for `like`, though nothing of it
    is gone. A reference with no letter or digit is inside no other."""
    mine = plain(old)
    return bool(mine) and mine in plain(new)


def distinct(refs: Sequence[str]) -> list[str]:
    """The references, each once: two that differ only in case, punctuation or spacing are one."""
    first: dict[str, str] = {}
    for ref in refs:
        first.setdefault(plain(ref), ref)
    return list(first.values())


def kept(old: Sequence[str], new: Sequence[str]) -> set[str]:
    """The references of a parent, `old`, that those of its edit, `new`, keep. A new reference keeps every old
    one it holds whole (`extends`), so that references merged into one are all kept. One that holds none keeps
    at most one by likeness (`like`): two tags of the Stacks Project read alike, and keeping one does not keep
    the other. The old references go to the new ones they read like in the way that keeps the most of them,
    each offered first the one most like it; the most alike old references are placed first. A reference
    given twice counts once."""
    old, new = distinct(old), distinct(new)
    whole = {o for o in old if any(extends(n, o) for n in new)}
    free = [n for n in new if not any(extends(n, o) for o in old)]
    rest = [o for o in old if o not in whole]
    score = {(o, n): likeness(o, n) for o in rest for n in free}
    alike = {o: sorted((n for n in free if score[o, n] >= SIMILAR), key=lambda n: -score[o, n]) for o in rest}
    keeper: dict[str, str] = {}  # a new reference, and the old one it keeps by likeness

    def place(o: str, tried: set[str]) -> bool:
        """Gives `o` a new reference like it: a free one, or one whose old reference can move to another."""
        for n in alike[o]:
            if n not in tried:
                tried.add(n)
                if n not in keeper or place(keeper[n], tried):
                    keeper[n] = o
                    return True
        return False

    for o in sorted(rest, key=lambda o: -max((score[o, n] for n in alike[o]), default=0)):
        place(o, set())
    return whole | set(keeper.values())


def mentions(item: str, name: str) -> bool:
    """Whether `item` holds `name` whole: `Foo.bar` is in `Foo.bar.` but not in `Foo.bar_two`, `Foo.bar'`
    or `Foo.bar.baz`, which are other names."""
    return re.search(rf"(?<![\w'!?.]){re.escape(name)}(?![\w'!?]|\.\w)", item) is not None


def same_check(a: str, b: str) -> bool:
    """Whether two Checks' names are one: the same tag or Lean name, or first words that read the same, case and
    punctuation aside, or alike (`like`), as a quote shortened or lengthened by a word does."""
    return a == b or plain(a) == plain(b) or (" " in a and " " in b and like(a, b))


def losses(old: Items, new: Items, dropped: Sequence[tuple[str, str]]) -> list[str]:
    """What `new` leaves out of `old` that no `dropped` line names, with a reason: a test or a Check is
    named by a line whose item holds its name or tag (or, for a Check given in prose, its first words), a
    reference by one whose item reads alike. A reference is not left out while a new one keeps it (`kept`)."""
    said = [item for item, why in dropped if why.strip()]
    ask = "keep it, or give the reason on a `Dropped:` line that names it"
    problems = [f"the edit drops the test `{name}`: {ask}" for name in dict.fromkeys(old.tests)
                if name not in new.tests and not any(mentions(item, name) for item in said)]
    problems += [f"the edit drops the Check *{tag}*: {ask}" for tag in dict.fromkeys(old.checks)
                 if not any(same_check(tag, n) for n in new.checks)
                 and not any(mentions(item, tag) or same_check(item.strip(' "“”*`'), tag) for item in said)]
    refs = distinct(old.references)
    keeps = kept(refs, new.references)
    problems += [f'the edit drops the reference "{ref}": {ask}' for ref in refs
                 if ref not in keeps and not any(like(ref, item) for item in said)]
    return problems


def check_problems(text: str, exists: Callable[[str], bool] | None) -> list[str]:
    """What is wrong with the Checks the text records (`checks_of`). One named by a Lean name or given in prose says
    what it found (`RESULT`). One named by a Lean name passes, or has `sorry`, only if a declaration of that name exists,
    and is missing only if none does: a Check the roadmap names by a Lean name that nothing carries is missing. A
    carrier given by its Lean name exists. Whether a name exists is `exists`'s to say; without it, nothing is said of
    names."""
    out = []
    for c in checks_of(text):
        if c.kind != "tag" and c.result is None:
            out.append(f"the Check {c.label} says nothing of what was found: follow its name (and what carries it) "
                       "with ` — passes`, ` — missing` or ` — sorry`, then a line on what it shows")
        if exists is None:
            continue
        if c.kind == "name" and LEAN_NAME.match(c.key) and c.result in ("passes", "sorry") and not exists(c.key):
            out.append(f"the Check `{c.key}` is said to be there, but `{c.key}` is not a declaration that exists: if "
                       "nothing carries it, it is missing; if something else does, name that after a comma")
        if c.kind == "name" and LEAN_NAME.match(c.key) and c.result == "missing" and c.carrier is None and \
                exists(c.key):
            out.append(f"the Check `{c.key}` is said to be missing, but `{c.key}` is a declaration of the library: say "
                       "whether it passes or has `sorry`")
        if c.carrier and LEAN_NAME.match(c.carrier) and not exists(c.carrier):
            out.append(f"the Check {c.label} is carried by `{c.carrier}`, which is not a declaration that exists")
    return out


def targets(text: str) -> list[str]:
    """The roadmap targets the text names, as it names them (`TARGET`), each once: in a line, or a bullet of Part 2 with
    its indented lines, that speaks of a roadmap (`roadmap`, `TauCetiRoadmap`)."""
    units = part_two(text) + normalize(text).split("\n")
    return list(dict.fromkeys(m for unit in units if re.search(r"roadmap", unit, re.I) for m in TARGET.findall(unit)))


def target_problems(text: str, roadmap: Callable[[str], bool] | None) -> list[str]:
    """The roadmap targets the text names that TauCetiRoadmap does not have (`roadmap(name)`, None: not checked)."""
    if roadmap is None:
        return []
    return [f"the text names the roadmap target `{name}`, and TauCetiRoadmap has no such name: a target is named as "
            "its roadmap names it (a heading, or a name in its README or Suggested.lean); a `tauceti-target` id of a "
            "Tau Ceti pull request is no roadmap's. Link the README line instead, or leave the name out"
            for name in targets(text) if not roadmap(name)]


def words(text: str) -> int:
    """How many words the text has, as the guide counts them (`WORDS`): its words, names and formulas, but not its
    headings, its links' addresses, or marks with no letter or digit (a bullet's dash)."""
    lines = [line for line in normalize(text).split("\n") if line not in HEADINGS]
    return sum(1 for w in LINK_TARGET.sub("]", "\n".join(lines)).split() if any(c.isalnum() for c in w))


def unlinked(text: str) -> str:
    """The text with its links' targets and the commits in its addresses set aside: what a reader reads of it."""
    return LINK_COMMIT.sub(r"\1<commit>", LINK_TARGET.sub("]()", normalize(text)))


def roadmap_line(bullet: str) -> bool:
    """Whether a bullet of Part 2 is a roadmap reference: it names TauCetiRoadmap, or opens with `Roadmap`."""
    return "TauCetiRoadmap" in bullet or bool(re.match(r"^(?:\*\*)?Roadmap\b", bullet))


def without_roadmap_lines(text: str) -> str:
    """The text without the bullets of Part 2 that are roadmap references (`roadmap_line`), their indented lines with
    them."""
    out, part, dropping = [], None, False
    for line in normalize(text).split("\n"):
        if line in HEADINGS:
            part, dropping = line, False
        elif part == HEADINGS[1]:
            m = BULLET.match(line)
            if m:
                dropping = roadmap_line(m[1])
            elif not (dropping and line[:1] in (" ", "\t") and line.strip()):
                dropping = False
            if dropping:
                continue
        out.append(line)
    return "\n".join(out)


def scope(parent: str, text: str) -> str | None:
    """What an edit changes when it changes only links: "links" when its text and its parent's differ only in their
    links' targets and the commits in their addresses (`unlinked`), nothing a reader reads; "roadmap" when, those set
    aside, they differ only in bullets of Part 2 that are roadmap references (`roadmap_line`); None when they differ in
    anything else."""
    a, b = unlinked(parent), unlinked(text)
    if a == b:
        return "links"
    if without_roadmap_lines(a) == without_roadmap_lines(b):
        return "roadmap"
    return None


def check(text: str, parent: str | None = None, dropped: Sequence[tuple[str, str]] = (),
          exists: Callable[[str], bool] | None = None, note: str | None = None,
          roadmap: Callable[[str], bool] | None = None) -> list[str]:
    """What stops `text` becoming the review, as problems; none means it passes. Its three parts must be
    there, each test it lists must exist (`exists`; None: every name does), its Checks must say what they found
    (`check_problems`), and each roadmap target it names must be TauCetiRoadmap's (`roadmap`; None: not checked).
    An edit, which has the `parent` text it replaces, must also change something a reader reads (not only the
    targets of its links, `scope`), carry a `note` saying what it adds or changes, and lose no test, example Check
    or reference of the parent unless a (item, reason) pair in `dropped` names it. The items are compared only when
    the parts are right: with a part missing, every item would be a loss."""
    bodies, problems = parts(text)
    if parent is not None:
        if not (note or "").strip():
            problems.append("an edit says what it adds or changes: give a note")
        if normalize(text) == normalize(parent):
            problems.append("the edit changes nothing: its text is its parent's")
        elif scope(parent, text) == "links":
            problems.append("the edit changes only where its links point (their addresses, or the commit in them), "
                            "which no reader reads: approve the text instead. A new version would leave behind every "
                            "approval of the text it replaces")
    if bodies is not None:
        new = items(text)
        problems += [f"the test `{name}` is not a declaration that exists" for name in dict.fromkeys(new.tests)
                     if exists is not None and not exists(name)]
        problems += check_problems(text, exists)
        problems += target_problems(text, roadmap)
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


def is_accept(record: dict) -> bool:
    """Whether the record is a review that says yes."""
    return record.get("kind") == "review" and record.get("verdict") == "accept"


def kind_of(record: dict) -> str | None:
    """What a record is to the standard review. A "version" is a review (an accept) or a comment that
    carries the spec and a text of its own, and approves nothing; an "approval" is an accept that names
    the version it approves. Anything else, a plain accept of the earlier form among it, is None."""
    s = record.get("standard")
    if not isinstance(s, dict) or s.get("spec") != SPEC:
        return None
    accept = is_accept(record)
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


@dataclass(frozen=True)
class Seen:
    """A record of a declaration and how the store reads it now: whether it applies to the declaration as it
    is (evidence-core's status), whether it was withdrawn, and whether its reviewer's later review
    superseded it. The caller says so, since the intake and the site build each know it their own way."""
    record: dict
    applies: bool
    withdrawn: bool
    superseded: bool


def by_author(record: dict) -> bool:
    """Whether the record is by an author of its declaration: the site marks those (`involvement: author`, from the
    dataset's facet `authors`, scripts/site_data.py), and no approval of an author's counts."""
    return ((record.get("by") or {}).get("involvement")) == "author"


def ai_accept(record: dict) -> bool:
    """Whether an AI said yes in the record: an accept by an agent, in whichever form. A person's accept is
    not one, whatever it carries."""
    by = record.get("by")
    return is_accept(record) and isinstance(by, dict) and by.get("kind") == "agent"


def approved(record: dict) -> str | None:
    """The version an accept approves: the one an approval names, or for a version its own text's. A comment,
    and an accept of the earlier form, approve none."""
    kind = kind_of(record)
    if kind == "approval":
        return record["standard"]["approves"]
    return version_of(record["text"]) if kind == "version" and is_accept(record) else None


def order(record: dict) -> tuple[str, int, int, str]:
    """Where a record stands in time: when it was made; then, for a record of a line of a comment, the comment's
    id and the line (`FROM_LINE`); and last its id. The times are RFC 3339, which sort as text. GitHub gives a
    comment's time to the second and its ids grow with time, so two comments of one second go by their ids, and
    the lines of one comment in their order, where the records' ids, hashes, would order them by chance. Any
    other record comes before the lines of its second. The intake reads a line against the records before it
    by this order, and the current version is the latest by it, so the two agree on records of one second."""
    ref = (record.get("origin") or {}).get("ref")
    m = FROM_LINE.search(ref) if isinstance(ref, str) and "/line/" in ref else None
    return record.get("at") or "", int(m[1]) if m else 0, int(m[2]) if m else 0, record.get("id") or ""


def current_version(seen: list[Seen]) -> Seen | None:
    """The version the review stands at: the latest record of a version (`order`) that was not withdrawn; None
    when there is none. A version whose accept was superseded still counts, since its reviewer's later review
    may be a tick of the same text. A withdrawn one is an edit undone, and the version before it is current
    again."""
    return max((s for s in seen if kind_of(s.record) == "version" and not s.withdrawn),
               key=lambda s: order(s.record), default=None)


def summary(seen: list[Seen]) -> dict | None:
    """The standard review of a declaration as its page shows it, or None while it has no version. It holds
    the current version's `text` as recorded, its `version` and its `record`. `approving` is whether that
    record is an AI's accept, which approves the text by writing it, by someone who is not an author of the
    declaration; a comment, held for the owner, and a person's accept approve nothing. `approvers` are the AI
    accepts of this version that apply to the declaration as it is now, by others than its authors (`by_author`),
    latest first, and `earlier` counts the other AI accepts by others than its authors: yeses of the earlier
    form, approvals of other texts, and approvals of this one made for an earlier version of the declaration.
    `earlier_approvals` are those of them that approved a text, the last two kinds, latest first. `by_authors` are
    the AI accepts of its authors that approved a text, which count in nothing, latest first. An accept withdrawn
    or superseded counts in none. The text is `current` when the version's record or any accept that approves it
    applies, an author's too; otherwise it was written for an earlier version of the declaration. `checked_for` is
    the latest record that wrote or approved this text, an author's too: the declaration as it was last read with
    it, whose subject says at which commit."""
    now = current_version(seen)
    if now is None:
        return None
    text = now.record["text"]
    version = version_of(text)
    live = [s for s in seen if ai_accept(s.record) and not (s.withdrawn or s.superseded)]
    counted = [s for s in live if not by_author(s.record)]
    latest = lambda rows: sorted(rows, key=lambda s: order(s.record), reverse=True)  # noqa: E731
    approves = lambda s: s.applies and approved(s.record) == version  # noqa: E731
    approvers = latest(s for s in counted if approves(s))
    mine = [s for s in live if by_author(s.record) and approved(s.record) is not None]
    read = [now] + [s for s in live if approved(s.record) == version]
    return {"text": text, "version": version, "record": now.record,
            "approving": ai_accept(now.record) and not by_author(now.record),
            "current": bool(now.applies or approvers or any(approves(s) for s in mine)), "approvers": approvers,
            "earlier": len(counted) - len(approvers),
            "earlier_approvals": latest(s for s in counted if approved(s.record) is not None and not approves(s)),
            "by_authors": latest(mine), "checked_for": max(read, key=lambda s: order(s.record)).record}
