#!/usr/bin/env python3
"""The migration's quality bar: each result a writing agent gave (scripts/migrate_write.py), checked against the bundle
of what is recorded about its declaration (scripts/migrate_inputs.py) before it becomes a record.

  python3 scripts/migrate_check.py BUNDLES RESULTS --source TAUCETI --out CHECKS

TAUCETI is a checkout of the library at the bundles' commit, the site's. CHECKS gets one line per line of RESULTS, in
its order: `{"decl", "ok", "problems"}`, `ok` when there are no problems. The check is deterministic: it reads the
result, the bundle, and Tau Ceti's files for the Checks a review lists, and asks no model. A result fails when:

- **its shape is wrong.** It is not `{"decl", "cells", "verdict", "hold", "review"}`, or `cells` does not give each of
  the rubric's eight checks once, as `checked`, `na` or `error`, or `verdict` is neither `approve` nor `hold`. Or a
  hold does not say why, or an approval holds a reason, a cell `error`, or a declaration with an open no. Or it is no
  result at all, but the error `collect` put in its place;
- **its review fails `standard.check`**: its three parts are not all there, or it lists a test the bundle gives as
  missing at the commit. A review that holds a control character fails too, since that is what JSON makes of a TeX
  backslash written once (`\\t` of `\\theta`);
- **What it says does not follow the signature.** For each explicit `(…)` and instance `[…]` binder group of the
  bundle's signature (`site_data.binder_groups`), Part 1 must name one of its binder names, or, for an instance
  group, its class, by the class's last component, as a whole word. A group that only introduces a type,
  `(R : Type u_1)`, needs nothing, nor does an implicit one;
- **a reference cannot be traced** (Ruling R48). A reference is a bullet of References and tests that does not open
  with a backticked name or `Check`. One text of the bundle (its docstring, the comments in its value, an earlier
  review, Voyager's announcement, the roadmap block; not its Lean code, nor its tests' texts) must hold its citation,
  what comes before its first `:` or ` — `: three consecutive words of it (all, when fewer), a name or a number among
  them; its first name, mostly its author, never an initial; and the words of each title in italics it gives, outside
  mathematics and code (Rulings R52, R53, R55). The same text must give every number of it, a Roman numeral of its
  citation too, glued to no other digit (a range gives its ends), but none from the mathematics of the words after its
  citation (`$c_{(1)}$`); and hold every link of it;
- **a citation anywhere in the review gives a number no text of the bundle gives.** A theorem, proposition, lemma,
  corollary, definition, section, chapter, tag or `§` with its number (in English, abbreviated, French or German),
  and after a plural every number of its list, is looked for in What it says, the prose of References and tests, its
  tests' lines, and Lean subtleties alike; and **a link anywhere in the review is in no text of the bundle**, as
  written (Ruling R53): a whole link of the text, not the start of one, and read without the backtick, asterisk or
  quotation mark around it;
- **a test is not one of the bundle's `tests`, or a Check is not one of its `checks`**, at the place the bundle gives
  for it, with its tag at that line of TAUCETI; or **References and tests names in backticks a Lean name** that is
  none of its tests, the declaration or what it rests on, unless a reference copies it from its text; or **it holds a
  numbered item, or a bullet indented under prose**, which the site's edit check, reading bullets at the margin only,
  would not protect (Rulings R51, R53).

`problems` gives all of them; `shape` and `review_problems` each half, for `migrate_write.py add`, which refuses a
result the shape rules forbid and shows an agent what the rest find while it can still fix it.

Exit 0 when the checks are written, whatever they find; 2 on bad input, such as TAUCETI at another commit.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
import migrate_inputs  # noqa: E402
import site_data  # noqa: E402
import standard  # noqa: E402

from evidence_core import rubric as rb  # noqa: E402

#: The rubric's eight checks: a result gives each a cell.
AXES = tuple(rb.STANDARD.names)
#: What a cell says: the check was made and found nothing wrong; it cannot fail here; it found an error.
STATES = ("checked", "na", "error")
#: A cell as `migrate_write.py add` takes it, by the words of the bulk issue's cells, with `error` too.
SAYING = {"checked": "checked", "na": "na", "n/a": "na", "error": "error"}
VERDICTS = ("approve", "hold")
#: A result's keys, in their order.
KEYS = ("decl", "cells", "verdict", "hold", "review")
#: What each error `collect` gives in place of a result says of it.
ERRORS = {"no result": "no result was written for it",
          "unparseable line": "its result line is not valid JSON",
          "two results": "it has more than one result line"}
#: A character no review holds: a TeX backslash written once in JSON reads as one, `\t` of `\theta`, `\f` of `\frac`.
CONTROL = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")

#: A binder name of Lean's, `hx`, `x₁`, `h'`, `A✝`.
IDENT = r"[^\W\d][\w'!?✝]*"
NAMES = re.compile(rf"{IDENT}(?:\s+{IDENT})*")
#: A class, as an instance group gives it: a name of one or more parts.
CLASS = re.compile(rf"{IDENT}(?:\.{IDENT})*")
OPEN, CLOSE = "([{⦃⟨", ")]}⦄⟩"

#: Dashes of every kind, read as `-`.
DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")
#: A word, as a citation and a text are compared: a run of letters, or a number (`7.3`); a range is two (`61–63`).
WORD = re.compile(r"[^\W\d_]+|\d+(?:[.:]\d+)*")
#: A number, as a reference or a citation gives it: from a digit on, through letters and digits, and through a `.`, `:`
#: or `-` before more of them: `4`, `1.8`, `10.161.1`, `2B.2`, `3.C`, `40-41`, `032F`, a commit's hash.
NUMERAL = r"\d[^\W_]*(?:[.:-][^\W_]+)*"
NUMBER = re.compile(NUMERAL)
#: How many consecutive words of its citation a reference shares with a text of the bundle.
RUN = 3
#: Words that begin a sentence as often as a name does, which a citation's run of words needs besides them.
COMMON = frozenset("a an the this that these those it its in on at for see as by of and or with from to also here "
                   "there compare cf no not is are was".split())
#: The words a citation names a place by, in any case, abbreviated, or in French or German, as the bundles write them.
KEYWORD = ("theorems?|thms?|th(?=\\.)|propositions?|props?|lemmas?|lemmata|lems?|corollar(?:y|ies)|cors?|"
           "definitions?|defns?|defs?|sections?|sects?|secs?|chapters?|chaps?|ch|tags?|"
           "théorèmes?|lemmes?|corollaires?|définitions?|chapitres?|exposés?|"
           "satz|sätze|korollare?|kapitel|abschnitte?|stacks(?:\\s+project)?(?:,?\\s+tags?)?")
#: What a citation names: a number (a Stacks tag is one), or a Roman numeral, `VII`, `II.5.3`.
MARK = rf"{NUMERAL}|[IVXLC]+(?![^\W_])(?:[.:-][^\W_]+)*"
#: A citation: one of those words and its number (`Theorem 4.12`, `Prop. 1.3`, `Stacks 02IO`), or `§` and its number;
#: the word (or the `§`s) and the number are its groups.
CITATION = re.compile(rf"(?<![^\W\d_])((?i:{KEYWORD}))(?:\.\s*|\s+)({MARK})|(§+)\s*({MARK})")
#: The next number of a citation's list, after a plural: `, 4.12`, ` and 5.1`, `, and II`.
LIST = re.compile(rf"[ \t]*(?:,[ \t]*(?:and|or)?|;|&|and|or|et|und)[ \t]*({MARK})")
#: A citation word where a citation names its place, with the phrase it may stand in (`Stacks Project, Tag`).
KEYWORD_AT = re.compile(rf"(?<![^\W\d_])(?i:{KEYWORD})(?![^\W\d_])")
#: A Roman numeral a citation gives on its own: `VII`, `II.5.3`, `V.2`; a lone `I`, `V` or `X` is too likely a word.
NUMERAL_ROMAN = re.compile(r"(?<![^\W_])(?:[IVXLC]{2,}(?:[.:-][^\W_]+)*|[IVXLC](?:[.:-][^\W_]+)+)(?![^\W_])")
#: A link's address: up to a space, a bracket or an angle, with the parentheses of one like `…/Ring_(mathematics)`.
URL = re.compile(r"https?://[^\s<>()\[\]]+(?:\([^\s<>()]*\)[^\s<>()\[\]]*)*")
#: What a link's match takes in after the link: a stop, or the backtick, asterisk, quotation mark or angle that closes
#: the code, italics or quotation the link is in.
AFTER_LINK = ".,;:!?`*\"'>"
#: Where a reference's citation ends and the writer's own words begin: its first `: `, ` — `, ` – ` or ` -- `.
SPLIT = re.compile(r":\s| [—–] | -- ")
#: A title in italics, `*…*` or `_…_`.
ITALIC = re.compile(r"(?<![*\w])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![*\w])|(?<![_\w])_(?!\s)([^_\n]+?)(?<!\s)_(?![_\w])")
#: An item of References and tests: a bullet, `- `, `* ` or `+ `, as `standard.bullets` reads them.
ITEM = re.compile(r"^[-*+][ \t]+(\S.*)$")
#: A numbered item, `1. ` or `1) `, at the margin: refused, since the site's edit check protects bullets only (R51).
NUMBERED = re.compile(r"^\d+[.)][ \t]+(\S.*)$")
#: A comment of Lean's, where a definition's value may cite its source: `/-- … -/`, `/- … -/`, `-- …`.
COMMENT = re.compile(r"/-.*?-/|--[^\n]*", re.S)
#: A Lean name of two parts or more, `TauCeti.Foo.bar`, as a backticked span may be; and the endings of a file's name.
DOTTED = re.compile(rf"{IDENT}(?:\.[\w'!?✝]+)+")
FILES = frozenset({"md", "lean", "pdf", "html", "toml", "txt", "json", "yml", "yaml", "py"})
#: Mathematics, `$…$` or `$$…$$`, whose digits are no numbers a citation gives.
MATH = re.compile(r"\$\$.*?\$\$|\$[^$\n]*\$", re.S)
#: Code and mathematics, which no citation is looked for in.
CODE = re.compile(r"`[^`\n]*`|" + MATH.pattern, re.S)
#: A Check's place, after its tag: `path:line`, in backticks.
PLACE = re.compile(r"^Check\s+\*[^*]+\*[\s,;:]*`([^`\s]+):(\d+)`")


# --- the shape -----------------------------------------------------------------------------------------------------

def errored(result: dict) -> bool:
    """Whether a line of RESULTS is the error `collect` put in place of a result."""
    return "error" in result and set(result) <= {"decl", "error"}


def shape(result, bundle: dict) -> list[str]:
    """What is wrong with a result's form, its cells and its verdict, for its declaration's bundle."""
    if not isinstance(result, dict):
        return ["the result is not a JSON object"]
    if errored(result):
        error = result["error"]
        said = ERRORS.get(error) if isinstance(error, str) else None
        return [said or f"it has no usable result: {error}"]
    problems = []
    lacking = [k for k in KEYS if k not in result]
    if lacking:
        problems.append("the result lacks " + ", ".join(f"`{k}`" for k in lacking) + ": it is `{"
                        + ", ".join(f'"{k}"' for k in KEYS) + "}`")
    extra = [k for k in result if k not in KEYS]
    if extra:
        problems.append("the result has keys that are not its own: " + ", ".join(f"`{k}`" for k in extra))
    if "decl" in result and result["decl"] != bundle["decl"]:
        problems.append(f"`decl` is `{result['decl']}`, not the bundle's `{bundle['decl']}`")
    cells = result.get("cells")
    if "cells" in result:
        if not isinstance(cells, dict):
            problems.append("`cells` is not an object that gives each of the eight checks a cell")
            cells = {}
        else:
            missing = [a for a in AXES if a not in cells]
            if missing:
                problems.append("`cells` lacks " + ", ".join(f"`{a}`" for a in missing)
                                + ": it gives each of the eight checks a cell")
            unknown = [a for a in cells if a not in AXES]
            if unknown:
                problems.append("`cells` has " + ", ".join(f"`{a}`" for a in unknown)
                                + ", which are not checks of the rubric: they are " + ", ".join(AXES))
            bad = [f"`{a}` is `{s}`" for a, s in cells.items() if a in AXES and s not in STATES]
            if bad:
                problems.append("in `cells`, " + ", ".join(bad) + ": a cell is `checked`, `na` or `error`")
    verdict, hold = result.get("verdict"), result.get("hold")
    if "verdict" in result and verdict not in VERDICTS:
        problems.append(f"`verdict` is `{verdict}`: it is `approve` or `hold`")
    if "hold" in result and not isinstance(hold, str):
        problems.append("`hold` is not a text")
    elif verdict == "hold" and not (hold or "").strip():
        problems.append("a hold says why in `hold`: what is wrong, and the evidence")
    elif verdict == "approve" and (hold or "").strip():
        problems.append("`hold` gives a reason, but the verdict is approve: hold it, or leave `hold` empty")
    if verdict == "approve":
        errors = [a for a in AXES if isinstance(cells, dict) and cells.get(a) == "error"]
        if errors:
            problems.append("the cell " + ", ".join(f"`{a}`" for a in errors) + " is `error` under approve: a "
                            "declaration a check found an error in is held")
        if bundle.get("open_no"):
            problems.append("the declaration has an open no (`open_no`): hold it")
    review = result.get("review")
    if "review" in result and not (isinstance(review, str) and review.strip()):
        problems.append("`review` is not a text, or is empty: a held declaration gets its review too")
    return problems


# --- the review ----------------------------------------------------------------------------------------------------

def depth0(text: str, what: str) -> int | None:
    """Where `what` first comes in `text` outside every bracket; None when it does not."""
    depth = 0
    for i, c in enumerate(text):
        if c in OPEN:
            depth += 1
        elif c in CLOSE:
            depth -= 1
        elif depth == 0 and text.startswith(what, i):
            return i
    return None


def closing(text: str) -> int | None:
    """Where the bracket `text` opens with closes; None when it does not."""
    depth = 0
    for i, c in enumerate(text):
        depth += 1 if c in OPEN else -1 if c in CLOSE else 0
        if depth == 0:
            return i
    return None


def class_of(kind: str) -> str | None:
    """The class an instance group is of, by its last component: `Module` for `Module ℚ V`, `Category` for
    `CategoryTheory.Category C`; through a family's binders, `AddCommMonoid` for `∀ (i : ι), AddCommMonoid (M i)` and
    `(x : M) → AddCommMonoid (V x)`; after a term in brackets, `FiniteIndex` for `(commutator G).FiniteIndex`. None when
    it starts with no name."""
    t = kind.strip()
    while True:
        if t.startswith("∀"):
            at = depth0(t, ",")
            if at is None:
                return None
            t = t[at + 1:].strip()
        elif t[:1] in OPEN and (end := closing(t)) is not None and t[end + 1:].lstrip().startswith("→"):
            t = t[end + 1:].lstrip()[1:].strip()
        else:
            break
    if t[:1] in OPEN and (end := closing(t)) is not None and t[end + 1:].startswith("."):
        t = t[end + 2:]  # a term in brackets, and the class by its dot: `(K.tensorObj L).HasHomology n`
    m = CLASS.match(t)
    return m[0].rsplit(".", 1)[-1] if m else None


def needs(decl: str, signature: str) -> list[tuple[str, tuple[str, ...]]]:
    """What What it says must name, by the signature's binder groups (`site_data.binder_groups`): for each explicit
    group `(…)` and instance group `[…]`, (the group, the words any one of which names it). An explicit group is named
    by a binder name of it, an instance group by its name, when it has one, or its class. A group that only introduces
    a type (`site_data.TYPE_ARGUMENT`) needs nothing, nor does an implicit one."""
    out = []
    for bracket, group in site_data.binder_groups(decl, {"text": signature or ""}):
        if bracket not in "([" or site_data.TYPE_ARGUMENT.fullmatch(group):
            continue
        inner = group[1:-1].strip()
        at = depth0(inner, " : ")
        named = at is not None and NAMES.fullmatch(inner[:at].strip())
        names = [n for n in inner[:at].split() if n != "_"] if named else []
        words = names if bracket == "(" else names + [c for c in [class_of(inner[at + 3:] if named else inner)] if c]
        if words:
            out.append((group, tuple(dict.fromkeys(words))))
    return out


def says(text: str, word: str) -> bool:
    """Whether `text` holds `word` whole: not within a longer name (`hxy`, `hx'`). A `.` may come before, as in a
    qualified name (`CategoryTheory.Category`), or after, as at the end of a sentence."""
    return re.search(rf"(?<![\w'!?✝]){re.escape(word)}(?![\w'!?✝])", text) is not None


def part(review: str, heading: str) -> str | None:
    """The body of one of the review's parts; None when it has no such part."""
    return next((body for h, body in standard.sections(review)[1] if h == heading), None)


def follows(review: str, bundle: dict) -> list[str]:
    """The problem when What it says leaves out an explicit or instance argument of the signature (`needs`)."""
    body = part(review, standard.HEADINGS[0])
    if body is None:
        return []
    skipped = [(group, words) for group, words in needs(bundle["decl"], bundle.get("signature") or "")
               if not any(says(body, w) for w in words)]
    if not skipped:
        return []
    listed = "; ".join(f"`{group}` (name " + " or ".join(f"`{w}`" for w in words) + ")" for group, words in skipped)
    return [f"What it says skips arguments of the signature: {listed}. Give each explicit `(…)` and instance `[…]` "
            "argument a bullet that opens with it in backticks, as the signature prints it, and says what it means"]


def plain(text: str) -> str:
    """Text as citations are compared: in Unicode's compatibility form, its dashes `-`, in lowercase."""
    return unicodedata.normalize("NFKC", text).translate(DASHES).lower()


def links_in(text: str) -> list[str]:
    """The links of a text (`URL`), each without what its match took in after it (`AFTER_LINK`), nor a last `)` it does
    not open: a link in backticks, italics or quotes, or at the end of a sentence, is the link itself."""
    out = []
    for link in URL.findall(text):
        while True:
            cut = link.rstrip(AFTER_LINK)
            if cut.endswith(")") and cut.count(")") > cut.count("("):
                cut = cut[:-1]
            if cut == link:
                break
            link = cut
        out.append(link)
    return out


@dataclass(frozen=True)
class Source:
    """A text of a bundle that a reference may come from: what it is, as a problem names it, the text as written, the
    text as citations are compared (`plain`), its words (`WORD`), its plain text without links' addresses, where a
    citation's first name is looked for, and its links (`links_in`), each of which a review may give, whole."""
    label: str
    text: str
    plain: str
    words: tuple[str, ...] = ()
    unlinked: str = ""
    links: frozenset[str] = frozenset()


def source(label: str, text: str) -> Source:
    """A text of a bundle, read once for every reference traced to it."""
    p = plain(text)
    return Source(label, text, p, tuple(WORD.findall(p)), URL.sub(" ", p), frozenset(links_in(text)))


def sources(bundle: dict) -> list[Source]:
    """The texts of a bundle a reference may come from, each apart: its docstring, the comments in its value, each
    earlier review, Voyager's announcement, and the roadmap block with its roadmap and file. Not its Lean code, nor its
    tests' texts, whose words a writer's own description of the declaration could share."""
    found = [("the docstring", bundle.get("docstring")),
             ("the comments in its value", "\n".join(COMMENT.findall(bundle.get("value") or "")))]
    for r in bundle.get("reviews") or []:
        at = f" of {str(r['at'])[:10]}" if r.get("at") else ""
        found.append((f"the review by {r.get('by') or 'someone'}{at}", r.get("text")))
    named, roadmap = bundle.get("named"), bundle.get("roadmap")
    if named:
        found.append(("Voyager's announcement", f"{named.get('name') or ''}\n{named.get('text') or ''}"))
    if roadmap:
        found.append(("the roadmap block", "\n".join(roadmap.get(k) or "" for k in ("name", "path", "block"))))
    return [source(label, text) for label, text in found if isinstance(text, str) and text.strip()]


def grams(words: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def gives(text: str, mark: str) -> bool:
    """Whether a (plain) text gives a number or a numeral, in lowercase, glued to nothing that would make it another:
    `§4` gives `4` and `Proposition7.3` gives `7.3`, but `14`, `1.4`, `7.3.1` and `7.3a` give neither, nor `xvii` a
    `vii`. A range gives its ends: `§§6.3–6.5` gives `6.3` and `6.5`."""
    before = r"(?<!\d)(?<!\d[.:])" if mark[:1].isdigit() else r"(?<![^\W_])"
    return re.search(rf"{before}{re.escape(mark)}(?![^\W_])(?![.:][^\W_])", text) is not None


def ends(mark: str) -> list[str]:
    """A number, or the ends of a range each apart: `6.3-6.5` is `6.3` and `6.5`."""
    parts = [p for p in mark.split("-") if p[:1].isdigit()] if mark[:1].isdigit() else []
    return parts or [mark]


def plural(word: str) -> bool:
    """Whether a citation word names several places, so that a list may follow it: `Propositions`, `Thms`, `§§`."""
    w = word.lower()
    return (word[:1] == "§" and len(word) > 1) or (w.endswith("s") and not w.startswith("stacks")) \
        or w in ("lemmata", "sätze", "korollare", "abschnitte")


#: The citation words that are abbreviations, which a dot may follow: after a whole word a dot ends a sentence.
ABBREVIATIONS = frozenset("th thm thms prop props lem lems cor cors def defs defn defns sec secs sect sects ch chap "
                          "chaps".split())


def citations(text: str) -> list[re.Match]:
    """The citations of a text (`CITATION`), but what only looks like one: a whole word and a dot, which end a
    sentence (`the theorem. I`), and a lone Roman letter after a word in lower case, which is a variable
    (`the def C`)."""
    out = []
    for c in CITATION.finditer(text):
        if c[1]:
            word = c[1].split()[0].rstrip(",").lower()
            if text[c.end(1):c.end(1) + 1] == "." and word not in ABBREVIATIONS:
                continue
            if c[1][0].islower() and re.fullmatch(r"[IVXLC]", c[2]):
                continue
        out.append(c)
    return out


def cited_marks(c: re.Match, text: str) -> tuple[list[str], int]:
    """The numbers one citation (`CITATION`, a match in `text`) names, and where it ends: its number, and after a plural
    every one of its list (`Propositions 1.7, 4.12 and 5.1`, `§§1.7, 4.12`; Ruling R53), each end of a range apart."""
    word, found, at = (c[1] or c[3]), [c[2] or c[4]], c.end()
    while plural(word) and (m := LIST.match(text, at)):
        found.append(m[1])
        at = m.end()
    return [e for mark in found for e in ends(mark)], at


def marks(text: str) -> list[str]:
    """What of a text the bundle must give too, in lowercase: every number in it, each end of a range apart, and each
    Roman numeral one of its citations names (`Chapter VII`, `Chapters II and III`)."""
    norm = unicodedata.normalize("NFKC", text).translate(DASHES)
    found = [e for token in NUMBER.findall(norm.lower()) for e in ends(token)]
    found += [m.lower() for c in citations(norm) for m in cited_marks(c, norm)[0] if not m[:1].isdigit()]
    return list(dict.fromkeys(found))


def named_words(text: str) -> list[tuple[str, bool]]:
    """The words of a citation (`WORD`), in lowercase, each with whether it is a name or a number: whether it holds a
    digit, or begins with a capital and is no word as common as `The`, which opens a sentence as often as a name."""
    found = WORD.findall(unicodedata.normalize("NFKC", text).translate(DASHES))
    return [(w.lower(), any(c.isdigit() for c in w) or (w[0].isupper() and w.lower() not in COMMON)) for w in found]


def first_name(text: str) -> str | None:
    """The first name a citation gives (Rulings R53, R55): its first word that begins with a capital and is no word as
    common as `The`, no citation word (`Proposition`, `Ch.`, `Stacks Project`), no Roman numeral, all letters (no number
    or tag, nor the letters within one, `02RV`), and longer than one letter, since an initial is not the name it stands
    for (`N. Bourbaki` names Bourbaki). Mostly its author, else the first word of its title; None when it gives none."""
    norm = unicodedata.normalize("NFKC", text).translate(DASHES)
    spans = [m.span() for m in KEYWORD_AT.finditer(norm)]
    for m in re.finditer(r"[^\W_]+", norm):
        w = m[0]
        if len(w) > 1 and w.isalpha() and w[0].isupper() and w.lower() not in COMMON \
                and not re.fullmatch(r"[IVXLC]+", w) and not any(a <= m.start() < b for a, b in spans):
            return w
    return None


def trace(ref: str, texts: list[Source]) -> tuple[Source | None, str | None]:
    """The text of the bundle reference `ref` comes from, and None; or None, and why it cannot be traced. Its
    citation is what comes before its first `:` or ` — `. The text must hold `RUN` consecutive words of it (all, when
    fewer), among which is a name or a number (`named_words`), so that a run of common words does not trace an
    invented source; its first name (`first_name`), so that an author the text does not name is not taken from a
    phrase it shares; and the words of each title in italics the citation gives, outside mathematics and code (Rulings
    R52, R53). It must give every number of the reference (`marks`, `gives`), the Roman numerals of its citation too,
    but none from the mathematics of the writer's words after the citation, and hold every link of it. The writer's own
    words, after the citation, do not trace it."""
    bare = URL.sub(" ", ref)
    hint = "; a reference does not open with a backticked name" if ref.lstrip().startswith("`") else ""
    cite = SPLIT.split(bare, 1)[0]
    if not named_words(cite):
        cite = bare
    cited = named_words(cite)
    if not cited:
        return None, f'the reference "{ref}" says nothing that could be looked for: a reference names a source{hint}'
    size = min(RUN, len(cited))
    wanted = {tuple(w for w, _ in cited[i:i + size]) for i in range(len(cited) - size + 1)
              if any(named for _, named in cited[i:i + size])}
    if not wanted:
        return None, (f'the reference "{ref}" names no source: its citation, the words before its first `:` or ` — `, '
                      f"holds no name and no number{hint}")
    outside = CODE.sub(" ", cite)
    titles = [t for t in (a or b for a, b in ITALIC.findall(outside)) if WORD.findall(plain(t))]
    name = first_name(cite)

    named_at = re.compile(rf"(?<![^\W_]){re.escape(name.lower())}(?![^\W_])") if name else None
    title_words = [(title, WORD.findall(plain(title))) for title in titles]

    def lacks(t: Source) -> list[str]:
        """What text `t`, which holds a run of the citation, lacks of its first name and its titles."""
        out = [] if named_at is None or named_at.search(t.unlinked) else [f"does not name {name}"]
        out += [f"does not hold its title *{title}*" for title, w in title_words
                if not grams(w, len(w)) & grams(t.words, len(w))]
        return out

    holding = [t for t in texts if wanted & grams(t.words, size)]
    if not holding:
        return None, (f'the reference "{ref}" is not in the bundle: no text of it (the docstring, an earlier review, '
                      "Voyager's announcement, the roadmap block) holds its citation, the words before its first `:` "
                      f"or ` — `. Cite only what the bundle gives, in its words{hint}")
    whole = [t for t in holding if not lacks(t)]
    if not whole:
        t = min(holding, key=lambda t: len(lacks(t)))
        return None, (f'the reference "{ref}" takes its citation from {t.label}, which ' + " and ".join(lacks(t))
                      + ". A reference comes whole from one text, its author and its title too; its citation is what "
                      "comes before its first `:` or ` — `, and words of your own come after" + hint)
    # The words after the citation give numbers in their prose only, as the rest of the review is read: `$c_{(1)}$`
    # gives none.
    prose = cite + MATH.sub(" ", bare[len(cite):])
    numbers = list(dict.fromkeys(marks(prose) + [m.lower() for m in NUMERAL_ROMAN.findall(outside)]))
    links = links_in(ref)
    best: tuple[Source, list[str], list[str]] | None = None
    for t in whole:
        missing = [mark for mark in numbers if not gives(t.plain, mark)]
        unlinked = [u for u in links if u not in t.links]
        if not missing and not unlinked:
            return t, None
        if best is None or len(missing) + len(unlinked) < len(best[1]) + len(best[2]):
            best = (t, missing, unlinked)
    t, missing, unlinked = best
    said = []
    for mark in missing:
        other = next((o for o in texts if gives(o.plain, mark)), None)
        said.append(f"{mark} is in {other.label}, not in {t.label}" if other else f"no text of the bundle gives {mark}")
    said += [f"{t.label} does not hold the link {u}" for u in unlinked]
    return None, (f'the reference "{ref}" takes its citation from {t.label}, but ' + "; ".join(said)
                  + ". A reference comes whole from one text, its numbers and links too" + hint)


@dataclass(frozen=True)
class Item:
    """An item of References and tests: a `test`, a `check` or a `reference`; its text, on one line; the lines of the
    part it takes; and a test's name or a Check's tag."""
    kind: str
    text: str
    lines: tuple[int, ...]
    name: str | None


def items_of(body: str) -> list[Item]:
    """The items of References and tests, its bullets, read as `standard.bullets` reads them: an item's indented lines
    go on from it, and a blank line or a line of prose, a numbered item among them, ends it. One that opens with a
    backticked Lean name is a test, one that opens with `Check *tag*` a Check, any other a reference."""
    found: list[tuple[list[str], list[int]]] = []
    going = False
    for i, line in enumerate(body.split("\n")):
        m = ITEM.match(line)
        if m:
            found.append(([m[1]], [i]))
            going = True
        elif going and line[:1] in (" ", "\t") and line.strip():
            found[-1][0].append(line.strip())
            found[-1][1].append(i)
        else:
            going = False
    out = []
    for said, lines in found:
        text = " ".join(said)
        if m := standard.TEST.match(text):
            kind, name = "test", m[1]
        elif m := standard.CHECK.match(text):
            kind, name = "check", m[1].strip()
        else:
            kind, name = "reference", None
        out.append(Item(kind, text, tuple(lines), name))
    return out


def binder_names(bundle: dict) -> set[str]:
    """The binder names of the declaration's signature, its implicit ones too."""
    out: set[str] = set()
    for _, group in site_data.binder_groups(bundle["decl"], {"text": bundle.get("signature") or ""}):
        inner = group[1:-1].strip()
        at = depth0(inner, " : ")
        if at is not None and NAMES.fullmatch(inner[:at].strip()):
            out.update(inner[:at].split())
    return out


def strangers(text: str, allowed: set, heads: set[str], source: str = "") -> list[str]:
    """What References and tests may not name in backticks: a dotted Lean name that is none of `allowed` (whole, or as
    the last parts of one, `Foo.bar` for `TauCeti.Foo.bar`), that is not headed by a binder name of the signature or a
    single letter (`e.symm`, `x.1`), that names no file (`README.md`), and that `source`, the text a reference comes
    from, does not hold."""
    out = []
    for span in re.findall(r"`([^`\n]+)`", text):
        name = span.strip()
        if not DOTTED.fullmatch(name) or name.rsplit(".", 1)[1].lower() in FILES:
            continue
        head = name.split(".", 1)[0]
        if head in heads or len(head) == 1 or name in source:
            continue
        if not any(isinstance(a, str) and (a == name or a.endswith("." + name)) for a in allowed):
            out.append(f"References and tests names `{name}`, which is not one of the declaration's tests: name in "
                       "backticks only its tests, the declaration and what it rests on")
    return out


def tag_at(source: Path, path: str, line: int, tag: str) -> bool:
    """Whether line `line` of `path` in the checkout `source` holds `*tag*`."""
    parts = PurePosixPath(path).parts
    if not parts or ".." in parts or path.startswith("/"):
        return False
    try:
        lines = (source / path).read_text(encoding="utf-8").split("\n")
    except OSError:
        return False
    return 1 <= line <= len(lines) and f"*{tag}*" in lines[line - 1]


def placed(item: Item, places: dict[str, list[tuple[str, int]]], source: Path | None) -> list[str]:
    """What is wrong with a Check: it is not one of the bundle's `checks`, it is not at the place `checks` gives, or
    its tag is not at that line of `source` (when given)."""
    tag = item.name
    if tag not in places:
        return [f"the Check *{tag}* is not one of the bundle's `checks`: list a Check only as `checks` gives it"
                + (", and so none, since it gives none" if not places else "")]
    at = PLACE.match(item.text)
    given = " or ".join(f"`{p}:{n}`" for p, n in places[tag])
    if not at:
        return [f"the Check *{tag}* gives no place: write it with its place in backticks, {given}"]
    if (at[1], int(at[2])) not in places[tag]:
        return [f"the Check *{tag}* is at {given} in the bundle, not at `{at[1]}:{at[2]}`"]
    if source is not None and not tag_at(source, at[1], int(at[2]), tag):
        return [f"the Check *{tag}* is not at `{at[1]}:{at[2]}` in Tau Ceti at the site's commit"]
    return []


def listed(review: str, bundle: dict, texts: list[Source], source: Path | None) -> list[str]:
    """What is wrong with the items of References and tests (`items_of`): a test that is not one of the bundle's
    `tests`; a Check that is not one of its `checks` (`placed`); a reference that cannot be traced (`trace`); a Lean
    name in backticks it may not name (`strangers`), in an item or in its prose; and a line the site's edit check would
    not read as an item, though it looks like one (`unprotected`)."""
    body = part(review, standard.HEADINGS[1]) or ""
    items = items_of(body)
    tests = {t.get("test"): t for t in bundle.get("tests") or []}
    allowed = set(tests) | {bundle["decl"]} | {r.get("name") for r in bundle.get("rests_on") or []}
    heads = binder_names(bundle)
    places: dict[str, list[tuple[str, int]]] = {}
    for c in bundle.get("checks") or []:
        places.setdefault(c.get("tag"), []).append((c.get("path"), int(c.get("line") or 0)))
    problems = []
    for item in items:
        if item.kind == "test":
            if item.name not in tests:
                problems.append(f"the test `{item.name}` is not one of the declaration's tests in the bundle "
                                "(`tests`): name only those; a reference does not open with a backticked name")
            problems += strangers(item.text[len(item.name) + 2:], allowed, heads)
        elif item.kind == "check":
            problems += placed(item, places, source)
        else:
            found, why = trace(item.text, texts)
            problems += [why] if why else strangers(item.text, allowed, heads, found.text)
    problems += unprotected(body)
    taken = {i for item in items for i in item.lines}
    return problems + strangers("\n".join(line for i, line in enumerate(body.split("\n")) if i not in taken),
                                allowed, heads)


def unprotected(body: str) -> list[str]:
    """The lines of References and tests that look like items but that the site's edit check, which reads bullets at the
    margin as `standard.bullets` does, would not protect (Rulings R51, R53): a numbered item, at the margin or indented,
    and a bullet indented under prose. A line indented under a bullet goes on from that bullet, and is protected."""
    out, going = [], False
    for line in body.split("\n"):
        if ITEM.match(line):
            going = True
            continue
        if going and line[:1] in (" ", "\t") and line.strip():
            continue
        going = False
        if m := NUMBERED.match(line.strip()):
            out.append(f'a numbered item, "{m[1]}": use `- ` bullets, which the site\'s edit check protects')
        elif line[:1] in (" ", "\t") and (m := ITEM.match(line.strip())):
            out.append(f'a bullet indented under prose, "{m[1]}": use `- ` bullets at the margin, which the site\'s '
                       "edit check protects")
    return out


def parts_apart(review: str) -> list[tuple[str, str]]:
    """The review part by part, (part, text): all of it but the references of References and tests, which are checked
    whole against the text they come from (`trace`)."""
    before, found = standard.sections(review)
    out = [("The text before What it says", before)] if before.strip() else []
    for heading, body in found:
        if heading == standard.HEADINGS[1]:
            refs = {i for item in items_of(body) if item.kind == "reference" for i in item.lines}
            body = "\n".join(line for i, line in enumerate(body.split("\n")) if i not in refs)
        out.append((heading[3:], body))
    return out


def scanned(review: str) -> list[tuple[str, str]]:
    """The review as its citations are looked for (`parts_apart`): without code, mathematics or links' addresses."""
    return [(where, CODE.sub(" ", URL.sub(" ", text))) for where, text in parts_apart(review)]


def unsupported(review: str, texts: list[Source]) -> list[str]:
    """The citations of a review outside its references (`scanned`) whose number no text of the bundle gives: a
    theorem, a section, a tag and their kin (`CITATION`), every number of the list after a plural (`cited_marks`), in
    What it says, the prose of References and tests, a test's line or Lean subtleties alike."""
    problems = []
    for where, text in scanned(review):
        norm = unicodedata.normalize("NFKC", text).translate(DASHES)
        for c in citations(norm):
            found, end = cited_marks(c, norm)
            said = " ".join(norm[c.start():end].split())
            problems += [f'{where} cites "{said}", but no text of the bundle gives {mark}: cite only what the bundle '
                         "gives, with its numbers as given" for mark in found
                         if not any(gives(t.plain, mark.lower()) for t in texts)]
    return problems


def unlinked(review: str, texts: list[Source]) -> list[str]:
    """The links of a review outside its references (`parts_apart`) that no text of the bundle holds as written (Ruling
    R53), whole (`links_in`): in What it says, the prose of References and tests, a test's line or Lean subtleties, code
    included."""
    problems = []
    for where, text in parts_apart(review):
        for link in dict.fromkeys(links_in(text)):
            if not any(link in t.links for t in texts):
                problems.append(f"{where} links {link}, which no text of the bundle holds: link only what the bundle "
                                "gives, as it gives it")
    return problems


def review_problems(review: str, bundle: dict, source: Path | None = None) -> list[str]:
    """What is wrong with a review, written from `bundle`: `standard.check`, a control character, What it says against
    the signature, the items of References and tests (`listed`), and the citations and links of the rest
    (`unsupported`, `unlinked`)."""
    problems = []
    if CONTROL.search(review):
        problems.append("the review holds a control character (a tab, a form feed, …): JSON reads a TeX backslash "
                        "written once as one, `\\t` of `\\theta`, `\\f` of `\\frac`. Add the result with "
                        "`migrate_write.py add`, which needs nothing escaped")
    gone = {t.get("test") for t in bundle.get("tests") or [] if t.get("result") == "missing"}
    problems += standard.check(review, exists=lambda name: name not in gone)
    texts = sources(bundle)
    problems += follows(review, bundle) + listed(review, bundle, texts, source) + unsupported(review, texts)
    problems += unlinked(review, texts)
    return list(dict.fromkeys(problems))


def problems(bundle: dict, result, source: Path | None = None) -> list[str]:
    """Everything that fails `result`, written from `bundle`; none when it passes. `source` is a checkout of the library
    at the bundle's commit, where each Check's tag is looked for at its line; without it, they are not looked for."""
    out = shape(result, bundle)
    if isinstance(result, dict) and not errored(result) and isinstance(result.get("review"), str) \
            and result["review"].strip():
        out += review_problems(result["review"], bundle, source)
    return out


def parse_cells(spec: str) -> tuple[dict[str, str] | None, str]:
    """The cells of a result, from a comma-separated list such as `migrate_write.py add` takes: each of the eight checks
    once, alone or `=checked` when it was made and found nothing wrong, `n/a`, `=na` or `=n/a` when it does not apply,
    `=error` when it found an error. Returns the cells in the order of `AXES` and an empty reason; or None and every
    reason the list is not that."""
    got: dict[str, str] = {}
    named: set[str] = set()
    reasons = []
    for entry in (" ".join(e.split()) for e in spec.split(",")):
        if not entry:
            continue
        m = standard.CELL.match(entry)
        if not m:
            reasons.append(f"`{entry}` is not a cell: write a check alone, or `check=na` or `check=error`")
            continue
        axis, given, na = m.groups()
        state = "na" if na else SAYING.get(given or "checked")
        if axis not in AXES:
            reasons.append(f"`{axis}` is not a check of the rubric: they are {', '.join(AXES)}")
        elif axis in named:
            reasons.append(f"`{axis}` comes twice")
        elif state is None:
            reasons.append(f"`{entry}`: a cell is checked, na or error, and `{given}` is none of them")
        else:
            got[axis] = state
        named.add(axis)
    missing = [a for a in AXES if a not in named]
    if missing:
        reasons.append(f"every check needs a cell; missing: {', '.join(missing)}")
    return (None, "; ".join(reasons)) if reasons else ({a: got[a] for a in AXES}, "")


# --- the command ---------------------------------------------------------------------------------------------------

def read_jsonl(path: Path) -> list:
    """The JSON values of a file, one a line, blank lines skipped. A line that is not JSON is a ValueError naming it. The
    lines are cut at `\\n` only, as JSON lines end: a review may hold a Unicode line separator, which `splitlines` would
    cut at."""
    out = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").split("\n"), 1):
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError as e:
                raise ValueError(f"{path}:{n}: not JSON ({e})") from None
    return out


def kind(problem: str) -> str:
    """A problem with what it names left out, so that problems of one kind count together."""
    return re.sub(r"`[^`]*`|\"[^\"]*\"|\*[^*\s][^*]*\*", "…", problem).split(":")[0]


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="migrate_check.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("bundles", type=Path, help="the bundles the results were written from (scripts/migrate_inputs.py)")
    p.add_argument("results", type=Path, help="the results, as `migrate_write.py collect` merges them")
    p.add_argument("--source", required=True, type=Path, help="a checkout of the library at the bundles' commit")
    p.add_argument("--out", required=True, type=Path, help="the checks to write, one JSON object a line")
    a = p.parse_args(argv)
    try:
        bundles, results = read_jsonl(a.bundles), read_jsonl(a.results)
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    by_decl = {b.get("decl"): b for b in bundles if isinstance(b, dict)}
    if len(by_decl) != len(bundles) or None in by_decl:
        print(f"error: each line of {a.bundles} is a bundle, of a declaration of its own", file=sys.stderr)
        return 2
    commits = {b.get("commit") for b in bundles}
    if not a.source.is_dir():
        print(f"error: no checkout at {a.source}", file=sys.stderr)
        return 2
    at = migrate_inputs.checkout_commit(a.source)
    if len(commits) > 1 or (at is not None and commits and at not in commits):
        print(f"error: the checkout {a.source} is at {(at or '?')[:12]}, the bundles at "
              + ", ".join(sorted(str(c)[:12] for c in commits)), file=sys.stderr)
        return 2
    rows = []
    for r in results:
        decl = r.get("decl") if isinstance(r, dict) else None
        b = by_decl.get(decl) if isinstance(decl, str) else None
        found = problems(b, r, a.source) if b is not None else ["it is not a declaration of the bundles"]
        rows.append({"decl": decl, "ok": not found, "problems": found})
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    passed = sum(r["ok"] for r in rows)
    print(f"checked {len(rows)} results into {a.out}: {passed} pass, {len(rows) - passed} fail")
    common = Counter(kind(p) for r in rows for p in r["problems"]).most_common(8)
    for what, n in common:
        print(f"  {n:5d}  {what}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
