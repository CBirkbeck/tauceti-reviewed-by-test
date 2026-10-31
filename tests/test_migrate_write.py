"""The migration's writing: the batches Claude Code agents write the standard reviews from, with their instructions,
the results they add, collected (scripts/migrate_write.py), and the quality bar each result must pass before it
becomes a record (scripts/migrate_check.py). The bundles are written here in the format scripts/migrate_inputs.py
gives them; no model is asked anything."""
import contextlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from evidence_core import rubric as rb

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import migrate_check  # noqa: E402
import migrate_inputs  # noqa: E402
import migrate_write  # noqa: E402
import standard  # noqa: E402

AXES = rb.STANDARD.names
CELLS = {axis: "checked" for axis in AXES}
COMMIT = "d7dad3786f4cb95dbc0b2f5a2e47a989c1ebadad"
BEGIN, END = "<!-- standard-review:begin -->", "<!-- standard-review:end -->"

NILPOTENT = "TauCeti.Foo.mem_nilradical_of_isNilpotent"
SIGNATURE = "{name} {{R : Type u_1}} [CommRing R] {{x : R}} (hx : IsNilpotent x) :\n  x ∈ nilradical R"
TEST = {"test": "TauCeti.Foo.nilpotent_two_mem",
        "text": "The class of 2 in ZMod 4 is nilpotent, so it is in the nilradical.",
        "result": "passes", "statement": "TauCeti.Foo.nilpotent_two_mem : 2 ∈ nilradical (ZMod 4)"}
HX = "- `(hx : IsNilpotent x)`: the hypothesis that $x^n = 0$ for some natural number $n$."
SAYS = f"""In a commutative ring $R$, a nilpotent element $x$ lies in the nilradical of $R$.

- `[CommRing R]`: a commutative ring structure on $R$, with a $1$.
{HX}
- The conclusion: `x ∈ nilradical R`, $x$ is in the nilradical, the ideal of the nilpotent elements of $R$."""
REFS = """- Atiyah and Macdonald, *Introduction to Commutative Algebra*, Proposition 1.7.
- `TauCeti.Foo.nilpotent_two_mem` — the class of $2$ in $\\mathbb{Z}/4\\mathbb{Z}$, which squares to $0$, is in it."""
SUBTLE = "- `[CommRing R]` is a hypothesis carried as a typeclass: Lean finds the ring structure by itself."


def text(says: str = SAYS, refs: str = REFS, subtle: str = SUBTLE) -> str:
    return f"## What it says\n{says}\n\n## References and tests\n{refs}\n\n## Lean subtleties\n{subtle}\n"


def bundle(decl: str = NILPOTENT, **fields) -> dict:
    """A bundle as scripts/migrate_inputs.py writes one, its fields in their order."""
    b = {"decl": decl, "kind": "theorem", "package": "TauCeti", "commit": COMMIT,
         "signature": SIGNATURE.format(name=decl),
         "docstring": "A nilpotent element is in the nilradical "
                      "(Atiyah and Macdonald, *Introduction to Commutative Algebra*, Proposition 1.7).",
         "source": "theorem mem_nilradical_of_isNilpotent {x : R} (hx : IsNilpotent x) :\n    x ∈ nilradical R",
         "value": "",
         "rests_on": [{"name": "nilradical", "signature": "nilradical (R : Type u_1) [CommSemiring R] :\n  Ideal R",
                       "doc": "The nilradical of a commutative semiring is the ideal of nilpotent elements."}],
         "reviews": [{"by": "Codex (GPT-6 Astra) via CBirkbeck", "verdict": "accept", "state": "stands",
                      "text": "Correctly stated: a nilpotent element is in the nilradical, which is its definition.",
                      "checked": dict(CELLS), "at": "2026-10-26T14:16:10Z"}],
         "tests": [TEST], "checks": [], "named": None, "roadmap": None, "open_no": False}
    b.update(fields)
    return b


def result(b: dict | None = None, review: str | None = None, **fields) -> dict:
    """A writing agent's result for bundle `b`: an approval of `review`, all eight checks made."""
    b = b or bundle()
    out = {"decl": b["decl"], "cells": dict(CELLS), "verdict": "approve", "hold": "",
           "review": text() if review is None else review}
    out.update(fields)
    return out


def run(main, *argv: str, stdin: str | None = None) -> tuple[int, str, str]:
    """A script's `main` on `argv`: its exit code, and what it printed to stdout and to stderr."""
    out, err, before = io.StringIO(), io.StringIO(), sys.stdin
    try:
        if stdin is not None:
            sys.stdin = io.StringIO(stdin)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(argv))
    finally:
        sys.stdin = before
    return code, out.getvalue(), err.getvalue()


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def jsonl(path: Path, rows: list) -> Path:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return path


class Temporary(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="migrate-write-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.work = self.tmp / "work"

    def split(self, bundles: list[dict], name: str = "pilot", *more: str) -> tuple[int, str, str]:
        path = jsonl(self.tmp / f"{name}-bundles.jsonl", bundles)
        return run(migrate_write.main, "split", str(path), "--name", name, "--work", str(self.work), *more)

    def assertNamed(self, problems: list[str], *words: str):
        """Some one problem holds all the words."""
        self.assertTrue(any(all(w in p for w in words) for p in problems), f"{words} are in none of {problems}")


class SplitTests(Temporary):
    """The batch files one agent each takes, in the bundles' order, and the instructions beside them."""

    def test_split_sizes_and_order(self):
        bundles = [bundle(f"TauCeti.Foo.n{k}") for k in range(7)]
        code, out, err = self.split(bundles, "pilot", "--size", "3")
        self.assertEqual(code, 0, err)
        d = self.work / "pilot"
        names = sorted(p.name for p in d.glob("batch-*.jsonl"))
        self.assertEqual(names, ["batch-001.jsonl", "batch-002.jsonl", "batch-003.jsonl"])
        batches = [read(d / name) for name in names]
        self.assertEqual([len(b) for b in batches], [3, 3, 1])
        # The bundles in their order, each with its line in BUNDLES from 0, added last.
        self.assertEqual([b for batch in batches for b in batch], [{**b, "index": k} for k, b in enumerate(bundles)])
        self.assertEqual(list(batches[0][0])[-1], "index")
        # One line per batch file: where it is, and how many bundles it has.
        lines = out.splitlines()
        self.assertEqual(len(lines), 3, out)
        for line, name, n in zip(lines, names, (3, 3, 1)):
            self.assertIn(str(d / name), line)
            self.assertIn(f"{n} bundles", line)
        self.assertTrue((d / "prompt.md").is_file())
        self.assertFalse(list(d.glob("result-*")))
        # At most 40 to a batch unless told otherwise.
        code, out, err = self.split([bundle(f"TauCeti.Foo.m{k}") for k in range(81)], "all")
        self.assertEqual(code, 0, err)
        self.assertEqual([len(read(p)) for p in sorted((self.work / "all").glob("batch-*.jsonl"))], [40, 40, 1])
        # A name is split once: agents' results may be in its directory.
        (d / "result-001.jsonl").write_text("{}\n", encoding="utf-8")
        code, out, err = self.split(bundles[:2], "pilot", "--size", "3")
        self.assertEqual(code, 2)
        self.assertIn("pilot", err)
        self.assertEqual(sorted(p.name for p in d.glob("batch-*.jsonl")), names)
        self.assertEqual(len(read(d / "batch-001.jsonl")), 3)
        # A declaration given twice is refused: results are matched to bundles by name.
        code, out, err = self.split([bundles[0], bundles[0]], "twice")
        self.assertEqual(code, 2)
        self.assertIn(bundles[0]["decl"], err)

    def test_split_retry_takes_only_failures_with_problems(self):
        bundles = [bundle(f"TauCeti.Foo.n{k}") for k in range(6)]
        n = [b["decl"] for b in bundles]
        # The round's results: two pass, two fail, one has no result; n5 was in no batch of that round.
        results = jsonl(self.tmp / "results.jsonl", [
            result(bundles[0]), result(bundles[1], review="R1"), {"decl": n[2], "error": "no result"},
            result(bundles[3], review="R3"), result(bundles[4], review="R4")])
        checks = jsonl(self.tmp / "checks.jsonl", [
            {"decl": n[0], "ok": True, "problems": []}, {"decl": n[1], "ok": False, "problems": ["p1", "p2"]},
            {"decl": n[2], "ok": False, "problems": ["no result was written for it"]},
            {"decl": n[3], "ok": True, "problems": []}, {"decl": n[4], "ok": False, "problems": ["p4"]}])
        code, out, err = self.split(bundles, "retry-1", "--retry", str(checks), "--results", str(results),
                                    "--size", "2")
        self.assertEqual(code, 0, err)
        d = self.work / "retry-1"
        self.assertEqual(sorted(p.name for p in d.glob("batch-*.jsonl")), ["batch-001.jsonl", "batch-002.jsonl"])
        got = read(d / "batch-001.jsonl") + read(d / "batch-002.jsonl")
        self.assertEqual(got, [
            {**bundles[1], "index": 1, "retry": {"problems": ["p1", "p2"], "previous": "R1"}},
            {**bundles[2], "index": 2, "retry": {"problems": ["no result was written for it"], "previous": ""}},
            {**bundles[4], "index": 4, "retry": {"problems": ["p4"], "previous": "R4"}}])
        self.assertTrue((d / "prompt.md").is_file())
        self.assertEqual(len(out.splitlines()), 2)
        # CHECKS must be the check of RESULTS: a result it does not cover is refused, and nothing is written.
        partial = jsonl(self.tmp / "partial.jsonl", read(checks)[:4])
        code, out, err = self.split(bundles, "retry-2", "--retry", str(partial), "--results", str(results))
        self.assertEqual(code, 2)
        self.assertIn(n[4], err)
        self.assertFalse((self.work / "retry-2").exists())
        # A retry needs both files; nothing to retry writes no batch.
        code, out, err = self.split(bundles, "retry-3", "--retry", str(checks))
        self.assertEqual(code, 2)
        passing = jsonl(self.tmp / "passing.jsonl", [{"decl": n[0], "ok": True, "problems": []}])
        code, out, err = self.split(bundles, "retry-4", "--retry", str(passing), "--results",
                                    str(jsonl(self.tmp / "one.jsonl", [result(bundles[0])])))
        self.assertEqual((code, out), (0, ""), err)
        self.assertIn("nothing to retry", err)
        self.assertFalse((self.work / "retry-4").exists())

    def test_prompt_holds_the_marked_section(self):
        code, out, err = self.split([bundle()], "pilot")
        self.assertEqual(code, 0, err)
        prompt = (self.work / "pilot" / "prompt.md").read_text(encoding="utf-8")
        guide = (HERE.parent / "AI-REVIEWS.md").read_text(encoding="utf-8")
        section = guide.split(BEGIN)[1].split(END)[0].strip("\n")
        self.assertIn(section, prompt)
        self.assertNotIn(BEGIN, prompt)
        self.assertNotIn("{{", prompt)
        # The migration's six points, in the brief's order; the definition of the review comes after the hold, before
        # the rules on references, which narrow it.
        heads = [line for line in prompt.splitlines() if re.match(r"## \d\. ", line)]
        self.assertEqual([h[3] for h in heads], list("123456"), heads)
        at = [prompt.index(h) for h in heads]
        self.assertLess(at[1], prompt.index(section))
        self.assertLess(prompt.index(section), at[2])
        for k, words in enumerate((("Review the Lean first", "hold or write"), ("Hold", "`open_no`"),
                                   ("References only from the bundle", "numbers as given"),
                                   ("Tests only from `tests`", "`checks`"), ("`checked`, `na` or `error`",),
                                   ("result",))):
            for word in words:
                self.assertIn(word, heads[k])
        for word in ("`retry`", "`retry.problems`", "`retry.previous`", "result-", "batch-", "END_OF_REVIEW"):
            self.assertIn(word, prompt)
        # The command that adds a result is this script's, runnable as written.
        self.assertIn(f"{Path(migrate_write.__file__).resolve()}", prompt)
        self.assertIn(" add RESULT_FILE", prompt)
        # A guide that marks no section, or two, is refused.
        for guide in ("# AI-REVIEWS.md\n", f"{BEGIN}\na\n{END}\n{BEGIN}\nb\n{END}\n", f"{END}\na\n{BEGIN}\n"):
            with self.assertRaises(ValueError):
                migrate_write.section(guide)


class AddTests(Temporary):
    """How an agent adds a result: the review read as written, a line of JSON per declaration."""

    def setUp(self):
        super().setUp()
        self.bundles = [bundle(), bundle("TauCeti.Foo.other")]
        code, out, err = self.split(self.bundles, "pilot")
        self.assertEqual(code, 0, err)
        self.results = self.work / "pilot" / "result-001.jsonl"

    def add(self, review: str, *more: str, decl: str = NILPOTENT, cells: str = "object, convention, edge-cases, junk, "
            "vacuous, choice n/a, generality, naming") -> tuple[int, str, str]:
        return run(migrate_write.main, "add", str(self.results), "--decl", decl, "--cells", cells, *more,
                   stdin=review)

    def test_add_writes_the_contract_s_line_with_the_review_as_written(self):
        # TeX that JSON written by hand would spoil: \t of \theta, \f of \frac, \n of \nabla.
        tex = text(subtle=SUBTLE + "\n- $\\theta$, $\\frac{1}{2}$ and $\\nabla$ are as written.")
        code, out, err = self.add(tex + "\n\n", "--verdict", "approve")
        self.assertEqual(code, 0, err)
        lines = self.results.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0]), {"decl": NILPOTENT, "cells": {**CELLS, "choice": "na"},
                                                "verdict": "approve", "hold": "", "review": standard.normalize(tex)})
        self.assertEqual(list(json.loads(lines[0])), ["decl", "cells", "verdict", "hold", "review"])
        self.assertIn("1 of 2", out)
        self.assertIn("TauCeti.Foo.other", out)  # the next to do
        # Adding again replaces the declaration's line; a hold carries its reason and the cell that found the error.
        why = "`nilradical` is taken in `R` as a semiring, so the statement is about the wrong ideal."
        code, out, err = self.add(text(), "--verdict", "hold", "--hold", why,
                                  cells="object=error, convention, edge-cases, junk, vacuous, choice=na, generality, "
                                        "naming")
        self.assertEqual(code, 0, err)
        got = read(self.results)
        self.assertEqual(len(got), 1)
        self.assertEqual((got[0]["verdict"], got[0]["hold"], got[0]["cells"]["object"]), ("hold", why, "error"))
        self.assertIn("replac", out)
        # The review is checked as migrate_check.py will check it, and what it finds is said; the line is written.
        code, out, err = self.add(text(says=SAYS.replace(HX + "\n", "")), "--verdict", "approve",
                                  decl="TauCeti.Foo.other")
        self.assertEqual(code, 0, err)
        self.assertIn("hx", out)
        self.assertEqual([r["decl"] for r in read(self.results)], [NILPOTENT, "TauCeti.Foo.other"])
        self.assertIn("2 of 2", out)

    def test_add_refuses_what_the_contract_does_not_allow(self):
        before = "unchanged\n"
        self.results.write_text(before, encoding="utf-8")
        for argv, decl, cells, word in (
                (("--verdict", "approve"), "TauCeti.Foo.notInTheBatch", None, "TauCeti.Foo.notInTheBatch"),
                (("--verdict", "approve"), NILPOTENT, "object, convention", "naming"),
                (("--verdict", "approve"), NILPOTENT, "object, convention, edge-cases, junk, vacuous, choice=maybe, "
                                                      "generality, naming", "maybe"),
                (("--verdict", "hold"), NILPOTENT, None, "hold"),
                (("--verdict", "approve", "--hold", "why not"), NILPOTENT, None, "hold"),
                (("--verdict", "approve"), NILPOTENT, "object=error, convention, edge-cases, junk, vacuous, choice, "
                                                      "generality, naming", "error")):
            more = {"cells": cells} if cells else {}
            code, out, err = self.add(text(), *argv, decl=decl, **more)
            self.assertEqual(code, 1, (argv, decl, cells, out, err))
            self.assertIn(word, err)
            self.assertEqual(self.results.read_text(encoding="utf-8"), before)
        code, out, err = self.add("  \n", "--verdict", "approve")
        self.assertEqual(code, 1)
        code, out, err = run(migrate_write.main, "add", str(self.work / "pilot" / "batch-001.jsonl"), "--decl",
                             NILPOTENT, "--cells", ", ".join(AXES), "--verdict", "approve", stdin=text())
        self.assertEqual(code, 1)  # a batch file is no result file
        self.assertEqual(read(self.work / "pilot" / "batch-001.jsonl"), [{**b, "index": k}
                                                                         for k, b in enumerate(self.bundles)])


class CollectTests(Temporary):
    def test_collect_merges_and_reports_missing_unparseable_and_double(self):
        bundles = [bundle(f"TauCeti.Foo.n{k}") for k in range(7)]
        n = [b["decl"] for b in bundles]
        code, out, err = self.split(bundles, "pilot", "--size", "3")
        self.assertEqual(code, 0, err)
        d = self.work / "pilot"
        line = lambda r: json.dumps(r, ensure_ascii=False)
        (d / "result-001.jsonl").write_text("\n".join([
            line(result(bundles[0])),
            # A TeX backslash left single, `\m` of `\mathbb`: not JSON. It names its declaration, which gets the error.
            '{"decl": "TauCeti.Foo.n1", "cells": {}, "verdict": "approve", "hold": "", "review": "$\\mathbb{Z}$"}',
            line(result(bundles[2], review="first")), line(result(bundles[2], review="second")),
            ""]), encoding="utf-8")
        (d / "result-002.jsonl").write_text("\n".join([
            line(result(bundles[3])), line(result(bundles[3])),  # the same line twice is one result
            line(result(bundles[5])),
            line({**result(bundles[5]), "decl": "TauCeti.Foo.elsewhere"}),  # no bundle of this batch
            "and a line of no JSON at all"]) + "\n", encoding="utf-8")
        # batch-003 (n6) has no result file: its agent has not run.
        code, out, err = run(migrate_write.main, "collect", "pilot", "--work", str(self.work))
        self.assertEqual(code, 0, err)
        self.assertEqual(read(d / "results.jsonl"), [
            result(bundles[0]), {"decl": n[1], "error": "unparseable line"}, {"decl": n[2], "error": "two results"},
            result(bundles[3]), {"decl": n[4], "error": "no result"}, result(bundles[5]),
            {"decl": n[6], "error": "no result"}])
        for words in ("7 bundles", "3 results", "2 with no result", "1 with an unparseable line", "1 with two results"):
            self.assertIn(words, out)
        self.assertIn("batch-003.jsonl", out)
        self.assertIn("TauCeti.Foo.elsewhere", out)
        self.assertIn("2 lines", out)
        # Nothing to collect from a name never split.
        code, out, err = run(migrate_write.main, "collect", "never", "--work", str(self.work))
        self.assertEqual(code, 2)


class CheckTests(Temporary):
    """The quality bar: a result, its review and the bundle it was written from."""

    def problems(self, b: dict, r: dict, source: Path | None = None) -> list[str]:
        return migrate_check.problems(b, r, source)

    def test_a_good_result_passes(self):
        self.assertEqual(tuple(bundle()), migrate_inputs.FIELDS)  # the bundles here are migrate_inputs.py's
        self.assertEqual(self.problems(bundle(), result()), [])

    def test_check_part_one_follows_the_signature(self):
        b = bundle()
        skipping = self.problems(b, result(b, text(says=SAYS.replace(HX + "\n", ""))))
        self.assertEqual(len(skipping), 1, skipping)
        self.assertNamed(skipping, "`hx`", "(hx : IsNilpotent x)", "What it says")
        # An anonymous instance is named by its class; the implicit `{x : R}` and `{R : Type u_1}` need nothing.
        unnamed = self.problems(b, result(b, text(says=SAYS.replace("`[CommRing R]`", "The ring structure"))))
        self.assertNamed(unnamed, "`CommRing`", "[CommRing R]")
        self.assertNotIn("{x : R}", " ".join(unnamed))
        # A whole word: `hxy` and `hx'` are other names, while `hx.` ends a sentence.
        for said, ok in (("`hxy`", False), ("`hx'`", False), ("hx.", True), ("(hx : IsNilpotent x)", True)):
            got = self.problems(b, result(b, text(says=SAYS.replace("`(hx : IsNilpotent x)`", said))))
            self.assertEqual(got == [], ok, (said, got))
        # What it says only: the conclusion's words in another part do not count.
        self.assertTrue(self.problems(b, result(b, text(says=SAYS.replace(HX + "\n", ""),
                                                        subtle=SUBTLE + "\n- `hx` is explicit."))))
        # Groups of every shape: a type argument and implicit groups need nothing; a named instance is named by its name
        # or its class; an instance over a family by its class; a qualified class by its last component; an explicit
        # group of several names by any of them.
        sig = ("TauCeti.Foo.bar {ι : Type u_1} (C : Type u_2) [CategoryTheory.Category C] [hp : Fact (Nat.Prime p)] "
               "[∀ (i : ι), AddCommMonoid (M i)] [(x y : ι) → Fintype (Q x y)] (f g : ι → C) ⦃k : ℕ⦄ "
               "[(commutator G).FiniteIndex] [∀ (i : ι), (ρ i).IsIrreducible] :\n  f = g")
        self.assertEqual(migrate_check.needs("TauCeti.Foo.bar", sig), [
            ("[CategoryTheory.Category C]", ("Category",)), ("[hp : Fact (Nat.Prime p)]", ("hp", "Fact")),
            ("[∀ (i : ι), AddCommMonoid (M i)]", ("AddCommMonoid",)), ("[(x y : ι) → Fintype (Q x y)]", ("Fintype",)),
            ("(f g : ι → C)", ("f", "g")), ("[(commutator G).FiniteIndex]", ("FiniteIndex",)),
            ("[∀ (i : ι), (ρ i).IsIrreducible]", ("IsIrreducible",))])
        family = bundle("TauCeti.Foo.bar", signature=sig, tests=[])
        says = ("- `[CategoryTheory.Category C]`: a category $C$.\n- `Fact (Nat.Prime p)`: $p$ is prime.\n"
                "- `(f g : ι → C)`: two families $f$ and $g$ of objects of $C$.\n"
                "- `[(commutator G).FiniteIndex] [∀ (i : ι), (ρ i).IsIrreducible]`: finite index, irreducible.\n"
                "- The conclusion: they are equal.")
        got = self.problems(family, result(family, text(says=says, refs="None recorded.")))
        self.assertEqual(len(got), 1, got)
        self.assertNamed(got, "`AddCommMonoid`", "`Fintype`")
        self.assertNotIn("Category", got[0])

    def test_check_references_are_traced(self):
        serre = "Serre, A Course in Arithmetic, VII §4"
        b = bundle("TauCeti.ModularForm.isModularForm_E₄", signature="TauCeti.ModularForm.isModularForm_E₄ :\n  "
                   "IsModularForm 4 E₄", docstring=f"The Eisenstein series of weight 4 is a modular form ({serre}).",
                   tests=[], reviews=[
                       {"by": "Codex (GPT-6 Astra) via CBirkbeck", "verdict": "accept", "state": "stands",
                        "text": "Proposition 7 of that chapter covers weight 6.", "checked": {},
                        "at": "2026-10-26T14:16:10Z"},
                       {"by": "Claude Code (claude-fable-5-1) via CBirkbeck", "verdict": "accept", "state": "stands",
                        "text": "Compared with [Proposition7.3, pp.40–41](https://example.org/notes.pdf).",
                        "checked": {}, "at": "2026-10-27T14:16:10Z"},
                       {"by": "Claude Code (claude-opus-5-5) via CBirkbeck", "verdict": "accept", "state": "stands",
                        "text": "Theorem 7.3.1 of Hartshorne, *Algebraic Geometry*, is the general case.",
                        "checked": {}, "at": "2026-10-28T14:16:10Z"}])
        says = "The Eisenstein series $E_4$ of weight $4$ is a modular form."
        check = lambda ref: self.problems(b, result(b, text(says=says, refs=ref, subtle="None.")))
        self.assertEqual(check("- Serre, *A Course in Arithmetic*, VII §4."), [])
        got = check("- Serre, *A Course in Arithmetic*, VII §4, Thm 99.")
        self.assertEqual(len(got), 1, got)
        self.assertNamed(got, "Serre", "give it: 99")
        # Its words and its numbers come from one text: Proposition 7 is in another review than Serre's book.
        self.assertNamed(check("- Serre, *A Course in Arithmetic*, VII §4, Proposition 7."), "give it: 7")
        # A number counts glued to a word, as the text writes it, but not inside a longer number; words of the
        # writer's own, without a number, may follow.
        self.assertEqual(check("- [Proposition 7.3, pp. 40–41](https://example.org/notes.pdf), on Eisenstein series."),
                         [])
        self.assertNamed(check("- Hartshorne, *Algebraic Geometry*, Theorem 7.3."), "give it: 7.3")
        # A reference no text of the bundle gives is not in it, however well known.
        self.assertNamed(check("- Atiyah and Macdonald, *Introduction to Commutative Algebra*, Proposition 1.8."),
                         "Atiyah", "not in the bundle")
        # A bullet of prose is read as a reference too.
        self.assertNamed(check("- No reference is recorded for it."), "No reference is recorded")
        self.assertEqual(check("No reference is recorded for it."), [])
        # The roadmap block is a text of the bundle, with its roadmap and its file.
        rb_ = bundle(roadmap={"name": "Arithmetic", "path": "TauCetiRoadmap/Arithmetic/README.md",
                              "block": "## Layer 1: tripling\n\nDefine `Fixture.triple`."})
        cite = "- TauCetiRoadmap, Arithmetic, `TauCetiRoadmap/Arithmetic/README.md`, Layer 1: tripling."
        self.assertEqual(self.problems(rb_, result(rb_, text(refs=REFS + "\n" + cite))), [])
        self.assertNamed(self.problems(rb_, result(rb_, text(refs=REFS + "\n" + cite.replace("1", "2")))),
                         "give it: 2")

    def test_check_tests_and_checks_come_from_the_bundle(self):
        source = self.tmp / "tauceti"
        (source / "TauCeti" / "Examples").mkdir(parents=True)
        (source / "TauCeti" / "Examples" / "Foo.lean").write_text(
            "import TauCeti.Foo\n\n/-- *test_nilpotent_two*: the class of 2 in `ZMod 4` is nilpotent. -/\n"
            "example : IsNilpotent (2 : ZMod 4) := ⟨2, rfl⟩\n", encoding="utf-8")
        found = {"tag": "test_nilpotent_two", "path": "TauCeti/Examples/Foo.lean", "line": 3, "result": "passes"}
        gone = {"test": "TauCeti.Foo.nilpotent_gone", "text": "Removed since.", "result": "missing", "statement": ""}
        b = bundle(tests=[TEST, gone], checks=[found])
        listed = lambda *more: result(b, text(refs="\n".join([REFS, *more])))
        check_line = "- Check *test_nilpotent_two*, `TauCeti/Examples/Foo.lean:3` — passes: $2^2 = 0$ in it."
        self.assertEqual(self.problems(b, listed(check_line), source), [])
        # A test the bundle does not give; one it gives as missing at the commit.
        self.assertNamed(self.problems(b, listed("- `TauCeti.Foo.nilpotent_three_mem` — $3$ is not.")),
                         "`TauCeti.Foo.nilpotent_three_mem`", "tests")
        self.assertNamed(self.problems(b, listed("- `TauCeti.Foo.nilpotent_gone` — gone.")),
                         "`TauCeti.Foo.nilpotent_gone`", "exist")
        # A Check the bundle does not give, even as missing; one at a place other than the bundle's; one whose tag is
        # not at its line in Tau Ceti.
        self.assertNamed(self.problems(b, listed("- Check *test_nilpotent_three* — missing")), "test_nilpotent_three")
        self.assertNamed(self.problems(b, listed(check_line.replace(":3`", ":4`")), source), "test_nilpotent_two",
                         "Foo.lean:4")
        self.assertNamed(self.problems(b, listed(check_line.replace(", `TauCeti/Examples/Foo.lean:3`", "")), source),
                         "test_nilpotent_two", "place")
        moved = self.tmp / "moved"
        shutil.copytree(source, moved)
        (moved / "TauCeti" / "Examples" / "Foo.lean").write_text("\n\n\n/-- *test_nilpotent_two* -/\n",
                                                                 encoding="utf-8")
        self.assertNamed(self.problems(b, listed(check_line), moved), "test_nilpotent_two", "Tau Ceti")
        # As every bundle today, one with no checks takes no Check bullet at all.
        none = bundle()
        missing = text(refs=REFS + "\n- Check *test_nilpotent_two* — missing")
        self.assertNamed(self.problems(none, result(none, missing)), "test_nilpotent_two", "checks")

    def test_check_hold_and_error_cells(self):
        b = bundle()
        found = {**CELLS, "junk": "error"}
        self.assertNamed(self.problems(b, result(b, cells=found)), "`junk`", "error", "approve")
        why = "`nilradical` is taken in `R` as a semiring, so it is the wrong ideal."
        self.assertEqual(self.problems(b, result(b, cells=found, verdict="hold", hold=why)), [])
        # A hold says why, and an approval holds nothing.
        self.assertNamed(self.problems(b, result(b, verdict="hold", hold="  ")), "hold")
        self.assertNamed(self.problems(b, result(b, hold=why)), "hold")
        # Each of the eight checks once, as checked, na or error.
        lacking = {a: s for a, s in CELLS.items() if a != "naming"}
        self.assertNamed(self.problems(b, result(b, cells=lacking)), "naming")
        self.assertNamed(self.problems(b, result(b, cells={**CELLS, "style": "checked"})), "style")
        self.assertNamed(self.problems(b, result(b, cells={**CELLS, "choice": "n/a"})), "choice", "n/a")
        self.assertNamed(self.problems(b, result(b, verdict="yes")), "verdict", "yes")
        self.assertNamed(self.problems(b, {k: v for k, v in result(b).items() if k != "review"}), "review")
        self.assertNamed(self.problems(b, {**result(b), "notes": "mine"}), "notes")
        # A declaration with an open no is held.
        opened = bundle(open_no=True)
        self.assertNamed(self.problems(opened, result(opened)), "open")
        self.assertEqual(self.problems(opened, result(opened, verdict="hold", hold="It has an open no.")), [])
        # No result at all fails with what collect found; a line of no shape at all fails, and breaks nothing.
        self.assertNamed(self.problems(b, {"decl": NILPOTENT, "error": "two results"}), "more than one")
        self.assertNamed(self.problems(b, {"decl": NILPOTENT, "error": ["two"]}), "no usable result")
        self.assertNamed(self.problems(b, {"decl": NILPOTENT, "error": "a crash"}), "no usable result", "a crash")
        self.assertNamed(self.problems(b, ["a list"]), "not a JSON object")
        # A control character is a TeX backslash JSON read as an escape: `\t` of `\theta`.
        self.assertNamed(self.problems(b, result(b, text(subtle=SUBTLE + "\n- $\theta$ is an angle."))), "control")

    def test_check_writes_one_line_a_result(self):
        source = self.tmp / "tauceti"
        source.mkdir()
        (source / "README.md").write_text("Tau Ceti\n", encoding="utf-8")
        git = lambda *args: subprocess.run(["git", "-C", str(source), "-c", "user.name=t", "-c", "user.email=t@e.org",
                                            *args], check=True, capture_output=True, text=True).stdout.strip()
        git("init", "-q")
        git("add", ".")
        git("commit", "-q", "-m", "Tau Ceti")
        head = git("rev-parse", "HEAD")
        bundles = [bundle(name, commit=head) for name in (NILPOTENT, "TauCeti.Foo.other", "TauCeti.Foo.third")]
        b0, b1, b2 = bundles
        path = jsonl(self.tmp / "bundles.jsonl", bundles)
        results = jsonl(self.tmp / "results.jsonl", [
            result(b0), result(b1, cells={**CELLS, "junk": "error"}), {"decl": b2["decl"], "error": "no result"},
            result(bundle("TauCeti.Foo.stranger")), {**result(b0), "decl": ["not", "a", "name"]}])
        out_path = self.tmp / "checks.jsonl"
        check = lambda bundles_path: run(migrate_check.main, str(bundles_path), str(results), "--source", str(source),
                                         "--out", str(out_path))
        code, out, err = check(path)
        self.assertEqual(code, 0, err)
        rows = read(out_path)
        self.assertEqual([(r["decl"], r["ok"]) for r in rows], [
            (b0["decl"], True), (b1["decl"], False), (b2["decl"], False), ("TauCeti.Foo.stranger", False),
            (["not", "a", "name"], False)])
        self.assertEqual([list(r) for r in rows], [["decl", "ok", "problems"]] * 5)
        self.assertEqual(rows[0]["problems"], [])
        self.assertNamed(rows[3]["problems"], "not a declaration of the bundles")
        self.assertIn("1 pass", out)
        self.assertIn("4 fail", out)
        # Tau Ceti at another commit than the bundles' is refused, and nothing is written.
        out_path.unlink()
        code, out, err = check(jsonl(self.tmp / "other.jsonl", [bundle()]))
        self.assertEqual(code, 2)
        self.assertFalse(out_path.exists())
        self.assertIn(COMMIT[:12], err)


if __name__ == "__main__":
    unittest.main()
