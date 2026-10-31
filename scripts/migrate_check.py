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
- **a reference cannot be traced.** One text of the bundle (its docstring, source or value, an earlier review, a
  test's text, Voyager's announcement, the roadmap block) must share three consecutive words with it (all of them,
  when it has fewer), and give every number it gives, glued to no other digit;
- **a test is not one of the bundle's `tests`, or a Check is not one of its `checks`**, at the place the bundle gives
  for it, with its tag at that line of TAUCETI.

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
#: A word, as a reference and a text are compared: a run of letters, or a number (`7.3`, `40-41`).
WORD = re.compile(r"[^\W\d_]+|\d+(?:[.:-]\d+)*")
#: A number a reference gives: from a digit on, through letters and digits, and through a `.`, `:` or `-` before more
#: digits: `4`, `1.8`, `10.161.1`, `40-41`, `032f`, a commit's hash.
NUMBER = re.compile(r"\d[^\W_]*(?:[.:-]\d[^\W_]*)*")
#: How many consecutive words a reference shares with a text of the bundle.
RUN = 3
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
    """Text as references are compared: in Unicode's compatibility form, its dashes `-`, in lowercase."""
    return unicodedata.normalize("NFKC", text).translate(DASHES).lower()


def texts(bundle: dict) -> list[str]:
    """The texts of a bundle a reference may come from, each apart, plain: its docstring, source and value, each
    earlier review, each test's text, Voyager's announcement, and the roadmap block with its roadmap and file."""
    out = [bundle.get("docstring"), bundle.get("source"), bundle.get("value")]
    out += [r.get("text") for r in bundle.get("reviews") or []]
    out += [t.get("text") for t in bundle.get("tests") or []]
    named, roadmap = bundle.get("named"), bundle.get("roadmap")
    if named:
        out.append(f"{named.get('name') or ''}\n{named.get('text') or ''}")
    if roadmap:
        out.append(f"{roadmap.get('name') or ''}\n{roadmap.get('path') or ''}\n{roadmap.get('block') or ''}")
    return [plain(t) for t in out if isinstance(t, str) and t.strip()]


def runs(words: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def gives(text: str, number: str) -> bool:
    """Whether a (plain) text gives `number`, glued to no other digit: `§4` gives `4` and `Proposition7.3` gives
    `7.3`, but `14`, `1.4` and `7.3.1` give neither."""
    return re.search(rf"(?<!\d)(?<!\d[.:-]){re.escape(number)}(?![^\W_])(?![.:-]\d)", text) is not None


def untraced(ref: str, sources: list[str]) -> str | None:
    """Why reference `ref` cannot be traced to the (plain) texts of its bundle, `sources`; None when one of them shares
    `RUN` consecutive words with it, all of them when it has fewer, and gives every number it gives."""
    mine = plain(ref)
    words = WORD.findall(mine)
    if not words:
        return f'the reference "{ref}" says nothing that could be looked for: a reference names a source'
    n = min(RUN, len(words))
    grams = runs(words, n)
    sharing = [t for t in sources if grams & runs(WORD.findall(t), n)]
    if not sharing:
        return (f'the reference "{ref}" is not in the bundle: no text of it (the docstring, an earlier review, '
                f"Voyager's announcement, the roadmap block) has {'three' if n == RUN else 'all'} of its words in a "
                "row. Cite only what the bundle gives, in its words")
    numbers = list(dict.fromkeys(NUMBER.findall(mine)))
    missing = min(([x for x in numbers if not gives(t, x)] for t in sharing), key=len)
    if missing:
        return (f'the reference "{ref}" has numbers the bundle does not give it: {", ".join(missing)}. Give its '
                "numbers as the text it comes from does, or leave it out")
    return None


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


def listed(review: str, bundle: dict, source: Path | None) -> list[str]:
    """What is wrong with the items of References and tests: a test that is not one of the bundle's `tests`; a Check
    that is not one of its `checks`, at its place there, with its tag at that line of `source` (when given); a
    reference that cannot be traced (`untraced`)."""
    found = standard.items(review)
    tests = {t.get("test") for t in bundle.get("tests") or []}
    problems = [f"the test `{name}` is not one of the declaration's tests in the bundle (`tests`): name only those"
                for name in dict.fromkeys(found.tests) if name not in tests]
    places: dict[str, list[tuple[str, int]]] = {}
    for c in bundle.get("checks") or []:
        places.setdefault(c.get("tag"), []).append((c.get("path"), int(c.get("line") or 0)))
    for bullet in standard.bullets(part(review, standard.HEADINGS[1]) or ""):
        m = standard.CHECK.match(bullet)
        if not m:
            continue
        tag = m[1].strip()
        if tag not in places:
            problems.append(f"the Check *{tag}* is not one of the bundle's `checks`: list a Check only as `checks` "
                            "gives it" + (", and so none, since it gives none" if not places else ""))
            continue
        at = PLACE.match(bullet)
        given = " or ".join(f"`{p}:{n}`" for p, n in places[tag])
        if not at:
            problems.append(f"the Check *{tag}* gives no place: write it with its place in backticks, {given}")
        elif (at[1], int(at[2])) not in places[tag]:
            problems.append(f"the Check *{tag}* is at {given} in the bundle, not at `{at[1]}:{at[2]}`")
        elif source is not None and not tag_at(source, at[1], int(at[2]), tag):
            problems.append(f"the Check *{tag}* is not at `{at[1]}:{at[2]}` in Tau Ceti at the site's commit")
    sources = texts(bundle)
    problems += [why for ref in standard.distinct(found.references) if (why := untraced(ref, sources))]
    return problems


def review_problems(review: str, bundle: dict, source: Path | None = None) -> list[str]:
    """What is wrong with a review, written from `bundle`: `standard.check`, a control character, What it says against
    the signature, and the items of References and tests (`listed`)."""
    problems = []
    if CONTROL.search(review):
        problems.append("the review holds a control character (a tab, a form feed, …): JSON reads a TeX backslash "
                        "written once as one, `\\t` of `\\theta`, `\\f` of `\\frac`. Add the result with "
                        "`migrate_write.py add`, which needs nothing escaped")
    gone = {t.get("test") for t in bundle.get("tests") or [] if t.get("result") == "missing"}
    problems += standard.check(review, exists=lambda name: name not in gone)
    return problems + follows(review, bundle) + listed(review, bundle, source)


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
    """The JSON values of a file, one a line, blank lines skipped. A line that is not JSON is a ValueError naming it."""
    out = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
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
