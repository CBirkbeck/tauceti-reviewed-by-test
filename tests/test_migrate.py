import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from evidence_core import records as rec
from evidence_core.dataset import Dataset
from evidence_core.store import Store
from evidence_store.intake import Context

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))
import fixture_site  # noqa: E402
import migrate_inputs  # noqa: E402
import migrate_records  # noqa: E402
import site_data  # noqa: E402
import standard_intake  # noqa: E402

DATASET = HERE / "fixtures" / "dataset-b"
URL = "https://github.com/o/r/issues/1#issuecomment-6529887317"
#: Another comment on the bulk issue, where Voyager gave its yeses of other days.
OTHER = "https://github.com/o/r/issues/1#issuecomment-6393454856"
AT = "2026-10-30T18:01:39Z"
SESSION = "voyager-2026-10-30-1603"
VOYAGER = {"kind": "agent", "identity": {"kind": "github", "id": "CBirkbeck"}, "involvement": "unknown",
           "agent": {"tool": "Voyager", "model": "claude-fable-5-1", "session": SESSION}}
#: Voyager as the intake recorded its yeses of other days: the same reviewer, without a session.
VOYAGER_THEN = {**VOYAGER, "agent": {"tool": "Voyager", "model": "claude-fable-5-1"}}
TRANSCRIBED = " (Reasons transcribed from Voyager's run notes; the line it posted had none.)"
TRIPLE = "Correctly stated: three times its argument (Fixture notes, §1); compared in Voyager's full-statement test."
ZERO = "Correctly stated: the double of 0 is 0 (Fixture notes, §2); compared in Voyager's full-statement test."
#: The comment the lines were refused from, as GitHub gives it: an agent line, a line of prose, then bare yeses.
COMMENT = {"id": 6529887317, "html_url": URL, "created_at": AT, "author_association": "OWNER",
           "user": {"login": "CBirkbeck", "type": "User"},
           "body": "\n".join(["<!-- agent: tool=Voyager; model=claude-fable-5-1 -->",
                              "Checked in Voyager's full-statement test for the update of 2026-10-30.",
                              "Reviewed-by: Fixture.triple", "", "Reviewed-by: Fixture.double_zero"])}
BULK = {"number": 1, "labels": [{"name": "evidence:bulk"}]}


class VoyagerRefusedTests(unittest.TestCase):
    """Voyager's bare yeses of 2026-10-30, refused for want of reasons, filed with the reasons from its notes."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        (self.dir / "evidence" / "records").mkdir(parents=True)
        shutil.copy(HERE.parent / "evidence" / "store.json", self.dir / "evidence" / "store.json")
        self.ds = Dataset.load(DATASET)

    def store(self, *records: dict) -> Store:
        """The temporary store, holding `records` (each given its id) besides what it has."""
        if records:
            with (self.dir / "evidence" / "records" / "earlier.jsonl").open("a", encoding="utf-8") as f:
                for r in records:
                    f.write(json.dumps(rec.with_id(r), ensure_ascii=False, sort_keys=True) + "\n")
        return Store.load(self.dir / "evidence")

    def run_main(self, *rows: str, out: Path | None = None) -> tuple[int, Path, str]:
        tsv, out = self.dir / "reasons.tsv", out or self.dir / "voyager.jsonl"
        tsv.write_text("".join(row + "\n" for row in rows), encoding="utf-8")
        said = io.StringIO()
        with contextlib.redirect_stdout(said), contextlib.redirect_stderr(said):
            code = migrate_records.main(["voyager-refused", str(tsv), "--dataset", str(DATASET),
                                         "--store", str(self.dir / "evidence"), "--comment-url", URL, "--at", AT,
                                         "--session", SESSION, "--out", str(out)])
        return code, out, said.getvalue()

    def yes(self, name: str, at: str, ref: str) -> dict:
        """Voyager's yes of the earlier form, with its reasons, as the intake recorded those of other days."""
        return {"schema": rec.SCHEMA, "kind": "review", "verdict": "accept",
                "subject": rec.subject_from_decl(self.ds.by_name[name], self.ds), "by": VOYAGER_THEN, "at": at,
                "origin": {"kind": "comment", "ref": ref},
                "text": "Correctly stated: an earlier reason; compared in Voyager's full-statement test."}

    def test_voyager_refused_records_match_the_lines(self):
        code, out, said = self.run_main(f"3\tFixture.triple\t{TRIPLE}", f"5\tFixture.double_zero\t{ZERO}")
        self.assertEqual(code, 0, said)
        records = rec.load(out)
        self.assertEqual([r["origin"] for r in records], [{"kind": "comment", "ref": f"{URL}/line/3"},
                                                          {"kind": "comment", "ref": f"{URL}/line/5"}])
        self.assertEqual([r["subject"]["name"] for r in records], ["Fixture.triple", "Fixture.double_zero"])
        self.assertEqual([r["text"] for r in records], [TRIPLE + TRANSCRIBED, ZERO + TRANSCRIBED])
        rubric = Store.load(self.dir / "evidence").rubric
        for r in records:
            self.assertEqual((r["kind"], r["verdict"], r["at"], r["by"]), ("review", "accept", AT, VOYAGER))
            self.assertEqual(r["subject"]["commit"], self.ds.commit)
            self.assertEqual(r["subject"], rec.subject_from_decl(self.ds.by_name[r["subject"]["name"]], self.ds))
            self.assertNotIn("standard", r)
            self.assertNotIn("links", r)
            self.assertEqual(r["id"], rec.record_id(r))
            self.assertEqual(rec.validate(r, {rubric.name: rubric}), [])
            self.assertTrue(standard_intake.earlier_form(r))  # an old-form AI yes: an approval of an earlier version

    def test_the_intake_finds_the_lines_recorded(self):
        code, out, said = self.run_main(f"3\tFixture.triple\t{TRIPLE}", f"5\tFixture.double_zero\t{ZERO}",
                                        out=self.dir / "evidence" / "records" / "voyager.jsonl")
        self.assertEqual(code, 0, said)
        store = Store.load(self.dir / "evidence")
        ctx = Context("o/r", store, lambda commit: self.ds, frozenset())
        got = standard_intake.process_bulk_comment(COMMENT, BULK, ctx)
        self.assertEqual(got.records, [])
        self.assertEqual(len(got.replies), 1)
        self.assertIn("Recorded 2 of 2 lines", got.replies[0][1])
        self.assertNotIn("Not recorded", got.replies[0][1])

    def test_a_yes_supersedes_voyager_s_earlier_one_of_the_declaration(self):
        earlier = rec.with_id(self.yes("Fixture.triple", "2026-10-25T04:30:29Z", f"{OTHER}/line/3"))
        records, problems = migrate_records.voyager_refused(
            [(3, "Fixture.triple", TRIPLE)], self.ds, self.store(earlier), URL, AT, SESSION)
        self.assertEqual(problems, [])
        self.assertEqual(records[0]["links"], {"supersedes": earlier["id"]})
        self.assertEqual(records[0]["id"], rec.record_id(records[0]))

    def test_what_cannot_be_recorded_is_refused_and_nothing_is_written(self):
        store = self.store(self.yes("Fixture.double_zero", "2026-10-31T04:47:06Z", f"{OTHER}/line/7"),
                           self.yes("Fixture.triple_one", AT, f"{URL}/line/9"))
        rows = [(3, "Fixture.notThere", TRIPLE),  # not a declaration of the dataset
                (5, "Fixture.double_zero", ZERO),  # Voyager said yes again later, with its reasons
                (9, "Fixture.triple_one", TRIPLE),  # this line is recorded already
                (11, "Fixture.triple_two", "  "),  # no reasons
                (11, "Fixture.triple_pos", TRIPLE),  # the same line twice
                (13, "Fixture.one_pos'", TRIPLE)]  # fine
        records, problems = migrate_records.voyager_refused(rows, self.ds, store, URL, AT, SESSION)
        self.assertEqual(len(problems), 5, problems)
        for line, word in ((3, "not a declaration"), (5, "later"), (9, "recorded already"), (11, "no reasons"),
                           (11, "twice")):
            self.assertTrue(any(p.startswith(f"line {line}") and word in p for p in problems), (line, word, problems))
        self.assertEqual([r["subject"]["name"] for r in records], ["Fixture.one_pos'"])
        code, out, said = self.run_main(f"3\tFixture.notThere\t{TRIPLE}", f"13\tFixture.one_pos'\t{TRIPLE}")
        self.assertEqual(code, 1)
        self.assertFalse(out.exists())
        self.assertIn("line 3", said)

    def test_a_malformed_row_is_refused(self):
        for row in ("three\tFixture.triple\treasons", "3\tFixture.triple", "0\tFixture.triple\treasons"):
            code, out, said = self.run_main(row)
            self.assertEqual(code, 1, row)
            self.assertFalse(out.exists(), row)
        code, out, said = self.run_main(f"3\tFixture.triple\t{TRIPLE}", "", f"5\tFixture.double_zero\t{ZERO}")
        self.assertEqual(code, 0, said)  # blank lines are skipped
        self.assertEqual(len(rec.load(out)), 2)


#: Two `example`s carrying the tags of Checks, put after the end of `Fixture/Basic.lean` in a copy of the fixture's source:
#: one proved, and one with `sorry`.
EXAMPLES = """
/-- *test_triple_two*: `triple 2` is `6`. -/
example : Fixture.triple 2 = 6 := rfl

/-- *test_triple_three*: `triple 3` is `9`. -/
example : Fixture.triple 3 = 9 := by
  sorry
"""
#: Where the reviews link the fixture's file, at the commit of version A.
BASIC = "https://github.com/test/fixture/blob/A/Fixture/Basic.lean"
#: An AI agent's yes of the earlier form that cites Checks: two whose tags are in the file it links, one that is not
#: (removed since), and one in a file there is not; bold and a word in italics are no tags.
CITING = (f"**Correctly stated.** `triple b` is `b + b + b`, by *definition*. Its Checks: *test_triple_two* passes "
          f"([the example]({BASIC}#L58)), *test_triple_three* has `sorry` ([the example]({BASIC}#L61)), and "
          f"*test_gone* was removed ([once here]({BASIC}#L63)).\n\n"
          f"*test_elsewhere* is in [another file](https://github.com/test/fixture/blob/A/Fixture/Gone.lean#L3).")
#: The roadmap of `Fixture.triple`: a heading block that names it, under a title whose paragraph names only a longer
#: name that begins with it; and an audit, which is no roadmap (it has no `metadata.toml`), that names two others.
ROADMAP_README = """# Arithmetic

Tripling and doubling. The first unit test is `Fixture.triple_two`.

## Layer 1: tripling

Define `Fixture.triple`, three times a natural number, as `n + n + n`.

### 1.1 Its values

*test_triple_two*: `triple 2 = 6`.

## Layer 2: doubling

Being double (`Fixture.IsDouble`) is the graph of doubling.
"""
TRIPLE_BLOCK = """## Layer 1: tripling

Define `Fixture.triple`, three times a natural number, as `n + n + n`.

### 1.1 Its values

*test_triple_two*: `triple 2 = 6`."""
AUDIT = "# An audit\n\nIt read `Fixture.IsSmall` and `Fixture.triple`.\n"
#: A file of a package outside the library, where Lean's ranges (RANGES) place two of its declarations.
LEMMAS = """-- A file of a package outside the library.
/-- Casting a sum to `Int` is the sum of the casts. -/
@[simp, norm_cast] theorem natCast_add (n m : Nat) : ((n + m : Nat) : Int) = n + m :=
  rfl
"""
RANGES = [{"name": "Int.natCast_add", "module": "Init.Data.Int.Lemmas", "file": "Init/Data/Int/Lemmas.lean",
           "start": [2, 0], "end": [4, 5], "doc": "Casting a sum to `Int` is the sum of the casts."},
          # Made by another declaration's text: Lean gives that one's range, and names it.
          {"name": "List.decidableBAll", "module": "Init.Data.List.Basic", "file": "Init/Data/Int/Lemmas.lean",
           "start": [2, 0], "end": [4, 5], "doc": None, "host": "Int.natCast_add"}]
#: Voyager's announcement of one more declaration, later than the fixture's two.
ANNOUNCED = {"decl": "Fixture.isDouble_double", "name": "Doubling is double", "what": "result",
             "about": "`double n` is twice `n`.", "prs": [9], "source": {"voyager": 103, "stream": 610393},
             "at": "2026-10-25T03:30:00Z"}
#: The order the bundles come in: Voyager's named results, the newest announcement first; the library's others by
#: roadmap, then those of none; then those outside the library.
ORDER = ["Fixture.isDouble_double", "Fixture.IsDouble", "Fixture.triple_comm", "Fixture.double_triple",
         "Fixture.IsSmall", "Int.natCast_add", "List.decidableBAll"]


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), "-c", "user.name=fixture", "-c", "user.email=fixture@example.org", *args],
                   check=True, capture_output=True)


class MigrationInputsTests(unittest.TestCase):
    """The bundles the migration's writer reads (scripts/migrate_inputs.py), built from the fixture: its store with AI
    agents' yeses of the earlier form on more declarations, a copy of its source with two tagged `example`s and a file of
    a package outside it, a roadmap repository, and Lean's ranges of two declarations outside the library."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tmp = Path(tempfile.mkdtemp(prefix="migrate-inputs-"))
        cls.source = tmp / "source"
        shutil.copytree(fixture_site.SOURCE, cls.source)
        basic = cls.source / "Fixture" / "Basic.lean"
        basic.write_text(basic.read_text(encoding="utf-8") + EXAMPLES, encoding="utf-8")
        cls.basic = basic.read_text(encoding="utf-8").split("\n")
        outside = cls.source / ".lake" / "packages" / "lean4" / "Init" / "Data" / "Int" / "Lemmas.lean"
        outside.parent.mkdir(parents=True)
        outside.write_text(LEMMAS, encoding="utf-8")
        cls.roadmap = tmp / "roadmap"
        for path, text in (("TauCetiRoadmap/Arithmetic/README.md", ROADMAP_README),
                           ("TauCetiRoadmap/Arithmetic/metadata.toml", 'topic = "math.NT"\n'),
                           ("Completed/Audit/notes.md", AUDIT)):
            (cls.roadmap / path).parent.mkdir(parents=True, exist_ok=True)
            (cls.roadmap / path).write_text(text, encoding="utf-8")
        git(cls.roadmap, "init", "-q")
        git(cls.roadmap, "add", ".")
        git(cls.roadmap, "commit", "-q", "-m", "roadmaps")
        cls.ranges = tmp / "ranges.jsonl"
        cls.ranges.write_text("".join(json.dumps(r) + "\n" for r in RANGES), encoding="utf-8")
        cls.settings = tmp / "settings.json"
        cls.settings.write_text(json.dumps(fixture_site.SETTINGS), encoding="utf-8")
        ds = Dataset.load(fixture_site.DATASET)
        key = lambda name: rec.subject_from_decl(ds.by_name[name], ds)
        issue = lambda n: {"kind": "issue", "ref": f"example/fixture-store#{n}"}

        def yes(name: str, by: dict, n: int, text: str = "Correctly stated.") -> dict:
            return rec.with_id({"schema": rec.SCHEMA, "kind": "review", "verdict": "accept", "subject": key(name),
                                "by": by, "text": text, "at": f"2026-10-28T10:{n:02d}:00Z", "origin": issue(100 + n)})

        agent, astra = fixture_site.AGENT, fixture_site.ASTRA
        withdrawn = yes("Fixture.double_zero", agent, 9)
        # A no withdrawn since, whose text no other review has, and the same no filed twice and withdrawn twice.
        nope = lambda n: rec.with_id({**yes("Fixture.IsSmall", agent, n, "Twelve is small too."), "verdict": "problem",
                                      "category": "edge-cases", "rubric": "ltb-rubric/1"})
        noes = [nope(10), nope(11)]
        cls.more = [yes("Fixture.IsDouble", astra, 1), yes("Fixture.isDouble_double", agent, 2),
                    yes("Fixture.triple_comm", agent, 3, CITING), yes("Fixture.double_triple", astra, 4),
                    yes("Fixture.IsSmall", agent, 5), yes("Int.natCast_add", agent, 6),
                    yes("List.decidableBAll", agent, 7),
                    yes("Nat.pred", agent, 8),  # outside the library, and not a declaration the site asks about
                    withdrawn, *noes] + [
                    {"schema": rec.SCHEMA, "kind": "status", "target": r["id"], "state": "withdrawn", "by": agent,
                     "text": "Filed by mistake.", "at": f"2026-10-28T11:0{k}:00Z", "origin": issue(109 + k)}
                    for k, r in enumerate([withdrawn, *noes])]
        cls.dataset, cls.store, _ = fixture_site.inputs(tmp / "inputs", more=cls.more,
                                                        announcements=fixture_site.ANNOUNCEMENTS + [ANNOUNCED])
        cls.code, cls.out, cls.said = cls.run_main()
        cls.bundles = {b["decl"]: b for b in cls.read(cls.out)} if cls.code == 0 else {}
        cls.order = [b["decl"] for b in cls.read(cls.out)] if cls.code == 0 else []

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def run_main(cls, *more: str, out: Path | None = None) -> tuple[int, Path, str]:
        out = out or cls.tmp / "bundles.jsonl"
        said = io.StringIO()
        with contextlib.redirect_stdout(said), contextlib.redirect_stderr(said):
            code = migrate_inputs.main(["--dataset", str(cls.dataset), "--source", str(cls.source),
                                        "--store", str(cls.store), "--roadmap", str(cls.roadmap),
                                        "--ranges", str(cls.ranges), "--out", str(out),
                                        "--settings", str(cls.settings), *more])
        return code, out, said.getvalue()

    @staticmethod
    def read(path: Path) -> list[dict]:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def bundle(self, name: str) -> dict:
        """The bundle of any declaration, in scope or not, as the script builds it."""
        site = site_data.Site(site_data.load(self.dataset, self.store, None, self.source, fixture_site.SETTINGS))
        return migrate_inputs.Bundler(site, self.source, migrate_inputs.Roadmap(self.roadmap),
                                      migrate_inputs.read_ranges(self.ranges)).bundle(name)

    def line_of(self, tag: str) -> int:
        return next(k for k, line in enumerate(self.basic, 1) if f"*{tag}*" in line)

    def test_bundle_of_a_definition(self):
        b = self.bundle("Fixture.triple")
        self.assertEqual(list(b), ["decl", "kind", "package", "commit", "signature", "docstring", "source", "value",
                                   "rests_on", "reviews", "tests", "checks", "named", "roadmap", "open_no"])
        self.assertEqual((b["decl"], b["kind"], b["package"], b["commit"]), ("Fixture.triple", "definition", "Fixture", "B"))
        self.assertEqual(b["signature"], "Fixture.triple (n : Nat) : Nat")
        self.assertEqual(b["docstring"], "A definition that version B leaves alone. ")
        self.assertEqual((b["source"], b["value"]), ("def triple (n : Nat) : Nat", ":= n + n + n"))
        self.assertEqual(b["rests_on"], [{"name": "Nat", "signature": "Nat : Type",
                                          "doc": "The natural numbers, starting at zero."}])
        # Every review but those of the standard review, in time order: a person's yes (its reference is in its text), an
        # AI agent's yes its edit of the standard review superseded, and a person's suggestion; a yes withdrawn is not.
        self.assertEqual([(r["by"], r["verdict"], r["state"], r["text"]) for r in b["reviews"]],
                         [("example", "accept", "stands", "Reference: Fixture documentation"),
                          ("Claude Code (claude-opus-5-5) via example", "accept", "superseded",
                           "Compared with its definition, `n + n + n`."),
                          ("someone", "question", "open",
                           "It could be stated for any semiring: `n + n + n` makes sense there.")])
        self.assertEqual(b["reviews"][0]["checked"],
                         {"convention": "checked", "edge-cases": "unchecked", "object": "checked"})
        self.assertEqual(b["reviews"][0]["at"], "2026-09-25T10:00:00Z")
        self.assertEqual(b["tests"], [{"test": "Fixture.triple_two", "text": "its value at 2", "result": "passes",
                                       "statement": "Fixture.triple_two : Fixture.triple 2 = 6"}])
        self.assertEqual(b["checks"], [])
        self.assertIsNone(b["named"])
        self.assertEqual(b["roadmap"], {"name": "Arithmetic", "path": "TauCetiRoadmap/Arithmetic/README.md",
                                        "block": TRIPLE_BLOCK})
        self.assertFalse(b["open_no"])
        json.dumps(b, ensure_ascii=False)  # it is plain JSON

    def test_scope_and_order(self):
        self.assertEqual(self.code, 0, self.said)
        # AI agents' yeses only: not a person's alone (`triple_two`), nor one withdrawn (`double_zero`), nor one of a
        # declaration outside the library the site does not ask about (`Nat.pred`); and none with a standard review
        # (`triple`, `triple_pos`, `double`, `Int`).
        self.assertEqual(self.order, ORDER)
        self.assertEqual(self.bundles["Fixture.IsDouble"]["named"], {"name": "Being double", "text": "`m` is twice `n`."})
        self.assertTrue(self.bundles["Fixture.triple_comm"]["open_no"])  # someone's no is open
        # A no withdrawn is no open no, and it is listed once, as withdrawn, its category the cell it found in error.
        small = self.bundles["Fixture.IsSmall"]
        self.assertFalse(small["open_no"])
        self.assertEqual([(r["verdict"], r["state"], r["text"], r["checked"]) for r in small["reviews"]],
                         [("accept", "stands", "Correctly stated.", {}),
                          ("problem", "withdrawn", "Twelve is small too.", {"edge-cases": "error"})])
        self.assertEqual([r["by"] for r in self.bundles["Fixture.IsDouble"]["reviews"]], ["Codex (GPT-6 Astra) via example"])
        # Only some: in the same order. A name out of scope is refused, saying why, and nothing is written.
        code, out, said = self.run_main("--only", "Fixture.IsSmall,Fixture.IsDouble", out=self.tmp / "only.jsonl")
        self.assertEqual((code, [b["decl"] for b in self.read(out)]), (0, ["Fixture.IsDouble", "Fixture.IsSmall"]), said)
        code, out, said = self.run_main("--only", "Fixture.IsSmall,Fixture.triple,Fixture.nothing",
                                        out=self.tmp / "refused.jsonl")
        self.assertEqual(code, 1, said)
        self.assertFalse(out.exists())
        self.assertIn("Fixture.triple: it has a standard review", said)
        self.assertIn("Fixture.nothing: not a declaration", said)

    def test_checks_are_verified(self):
        self.assertEqual(self.code, 0, self.said)
        self.assertEqual(self.bundles["Fixture.triple_comm"]["checks"],
                         [{"tag": "test_triple_two", "path": "Fixture/Basic.lean", "line": self.line_of("test_triple_two"),
                           "result": "passes"},
                          {"tag": "test_triple_three", "path": "Fixture/Basic.lean",
                           "line": self.line_of("test_triple_three"), "result": "sorry"}])
        self.assertNotEqual(self.line_of("test_triple_two"), 58)  # where it is now, not where the review saw it

    def test_binder_groups_unchanged(self):
        sig = lambda text, *names: {"text": text, "refs": [[text.index(n), text.index(n) + len(n), n] for n in names]}
        bar = sig("Foo.bar {R : Type u_1} [CommRing R] ⦃x : R⦄ (h : x ≠ 0) : Foo.baz x = x", "Foo.baz")
        self.assertEqual(site_data.binder_groups("Foo.bar", bar),
                         [("{", "{R : Type u_1}"), ("[", "[CommRing R]"), ("⦃", "⦃x : R⦄"), ("(", "(h : x ≠ 0)")])
        regular = sig("T.r (R : Type u_1) [CommRing R] [T.IsRegularRing R] : T.IsClosed R", "T.IsRegularRing", "T.IsClosed")
        self.assertEqual(site_data.binder_groups("T.r", regular),
                         [("(", "(R : Type u_1)"), ("[", "[CommRing R]"), ("[", "[IsRegularRing R]")])
        self.assertEqual(site_data.binder_groups("Foo.g", None), [])
        brackets = sig("Foo.f (g : (ℕ → ℕ) → ℕ) [Fact (0 < {n | n = 1}.ncard)] : Prop")
        self.assertEqual(site_data.binder_groups("Foo.f", brackets),
                         [("(", "(g : (ℕ → ℕ) → ℕ)"), ("[", "[Fact (0 < {n | n = 1}.ncard)]")])
        # What brief() says of them, as tests/test_build_site.py's BriefTests have it.
        brief = site_data.brief
        self.assertEqual(brief("Foo.bar", bar), "[CommRing R] (h : x ≠ 0) : baz x = x")
        self.assertEqual(brief("Foo.bar", sig("Foo.bar.{u} {α : Type u} (a : α) : a = a")), "(a : α) : a = a")
        self.assertEqual(brief("T.r", regular), "[CommRing R] [IsRegularRing R] : IsClosed R")
        text = "T.c (C D : Type u₁) (S : Sort*) [CategoryTheory.Category.{v, u} C] (F : C ⥤ D) : F = F"
        at = text.index("CategoryTheory")
        self.assertEqual(brief("T.c", {"text": text, "refs": [[at, at + 30, "CategoryTheory.Category"]]}),
                         "[Category C] (F : C ⥤ D) : F = F")
        self.assertEqual(brief("Foo.c", sig("Foo.c (x : ℕ)\n    (y : ℕ) : x + y =\n  y + x")),
                         "(x : ℕ) (y : ℕ) : x + y = y + x")
        long = "Foo.d [A " + "a" * 90 + "] (h : " + "b" * 50 + ") : c = c"
        self.assertEqual(brief("Foo.d", sig(long)), "… (h : " + "b" * 50 + ") : c = c")
        self.assertEqual(brief("Foo.d", sig("Foo.d (h : " + "b" * 150 + ") : c = c")), "… c = c")
        cut = brief("Foo.e", sig("Foo.e : " + "x + " * 60 + "x = x"))
        self.assertEqual((len(cut), cut[-1]), (site_data.BRIEF_CAP, "…"))
        self.assertEqual(brief("Foo.g", None), "")

    def test_outside_the_library_from_lean_s_ranges(self):
        self.assertEqual(self.code, 0, self.said)
        b = self.bundles["Int.natCast_add"]
        self.assertEqual((b["package"], b["kind"], b["rests_on"]), ("lean4", "theorem", []))
        self.assertEqual(b["signature"], "Int.natCast_add (n m : Nat) : ↑(n + m) = ↑n + ↑m")
        self.assertEqual(b["docstring"], "Casting a sum to `Int` is the sum of the casts.")
        self.assertEqual((b["source"], b["value"]),
                         ("@[simp, norm_cast] theorem natCast_add (n m : Nat) : ((n + m : Nat) : Int) = n + m", ""))
        # One whose text is another's says so.
        made = self.bundles["List.decidableBAll"]
        self.assertEqual(made["source"], "-- Written as part of `Int.natCast_add`.\n" + b["source"])
        self.assertEqual(made["docstring"], "")
        # The names Lean's ranges are wanted for: those outside the library in scope, and those its others rest on.
        names = self.tmp / "names.txt"
        code, _, said = self.run_main("--names-for-ranges", str(names), out=self.tmp / "unwritten.jsonl")
        self.assertEqual(code, 0, said)
        self.assertFalse((self.tmp / "unwritten.jsonl").exists())
        wanted = names.read_text(encoding="utf-8").split()
        self.assertEqual(wanted, sorted(set(wanted)))
        self.assertTrue({"Int.natCast_add", "List.decidableBAll", "Nat"} <= set(wanted), wanted)
        self.assertFalse([n for n in wanted if n.startswith("Fixture.")], wanted)

    def test_a_declaration_made_by_another_s_text(self):
        # As `@[to_additive]` makes the additive version: its range is the attribute's word, here `claim` in
        # `@[claim "Fixture, Theorem 1"]` above `triple_pos`. Its bundle has that text, under a line that says so.
        dataset = self.tmp / "made"
        shutil.copytree(self.dataset, dataset)
        facet = dataset / "facets" / "source.jsonl"
        rows = [json.loads(line) for line in facet.read_text(encoding="utf-8").splitlines() if line.strip()]
        word = next(r for r in rows if r["decl"] == "Fixture.triple_pos")["start"][0] + 1
        for r in rows:
            if r["decl"] == "Fixture.one_pos'":
                r.update(start=[word, 2], end=[word, 7], keyword="claim")
        facet.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        site = site_data.Site(site_data.load(dataset, self.store, None, self.source, fixture_site.SETTINGS))
        bundler = migrate_inputs.Bundler(site, self.source, None, {})
        stated = '@[claim "Fixture, Theorem 1"]\ntheorem triple_pos (n : Nat) (h : 0 < n) : 0 < triple n'
        for _ in range(2):  # and the dataset is as it was: the second time reads the same
            self.assertEqual(bundler.bundle("Fixture.one_pos'")["source"],
                             "-- Written as part of `Fixture.triple_pos`.\n" + stated)
            self.assertEqual(bundler.bundle("Fixture.triple_pos")["source"], stated)

    def test_a_roadmap_that_cannot_be_read(self):
        code, out, said = self.run_main("--roadmap", str(self.tmp / "nowhere"), out=self.tmp / "nowhere.jsonl")
        self.assertEqual(code, 2, said)
        self.assertFalse(out.exists())
        self.assertIn("TauCetiRoadmap cannot be read", said)

    def test_roadmap_blocks_come_from_roadmaps(self):
        self.assertEqual(self.code, 0, self.said)
        # A declaration of no roadmap named in one has that roadmap's block; one named only outside the roadmaps has none.
        self.assertEqual(self.bundles["Fixture.IsDouble"]["roadmap"],
                         {"name": "Arithmetic", "path": "TauCetiRoadmap/Arithmetic/README.md",
                          "block": "## Layer 2: doubling\n\nBeing double (`Fixture.IsDouble`) is the graph of doubling."})
        self.assertIsNone(self.bundles["Fixture.IsSmall"]["roadmap"])
        # The roadmap's main, read whatever its checkout holds.
        (self.roadmap / "TauCetiRoadmap" / "Arithmetic" / "README.md").write_text("# Emptied\n", encoding="utf-8")
        try:
            site = site_data.Site(site_data.load(self.dataset, self.store, None, self.source, fixture_site.SETTINGS))
            at_head = migrate_inputs.Bundler(site, self.source, migrate_inputs.Roadmap(self.roadmap, "HEAD"), {})
            self.assertEqual(at_head.bundle("Fixture.triple")["roadmap"]["block"], TRIPLE_BLOCK)
            in_tree = migrate_inputs.Bundler(site, self.source, migrate_inputs.Roadmap(self.roadmap), {})
            self.assertIsNone(in_tree.bundle("Fixture.triple")["roadmap"])
        finally:
            git(self.roadmap, "checkout", "--", ".")


class RoadmapLineTests(unittest.TestCase):
    def test_a_line_names_a_declaration_whole(self):
        whole = migrate_inputs.names_whole
        self.assertTrue(whole("Define `Fixture.triple`, three times n.", "Fixture.triple"))
        self.assertTrue(whole("[`triple`](https://example.org/docs/Fixture.html#Fixture.triple)", "Fixture.triple"))
        self.assertFalse(whole("`Fixture.triple_two` and `Fixture.triple.ext`", "Fixture.triple"))  # longer names
        self.assertFalse(whole("See [it](../Fixture.triple/README.md).", "Fixture.triple"))  # part of a path
        # A name of one part is a word too: only in code, or as a link's anchor.
        self.assertFalse(whole("Path lifting and homotopy lifting are proved.", "Path"))
        self.assertTrue(whole("Use Mathlib's `Path x y` and `Path.refl`.", "Path"))
        self.assertTrue(whole("hypotheses `[CommRing R] [IsDomain R]` throughout", "IsDomain"))
        self.assertTrue(whole("[paths](https://example.org/docs/Topology.html#Path)", "Path"))


class CheckPlaceTests(unittest.TestCase):
    """Where a Check's tag is in a file, and what became of the declaration below it (`migrate_inputs.found`)."""

    LINES = ["/-- *a*: proved. -/", "example : 1 = 1 := rfl", "",
             "/-- Two lines of doc,", "and *b* on the second. -/", "@[simp]", "theorem b_eq : 2 = 2 := by", "  sorry", "",
             "/-- *c*, the declaration on the doc's last line -/ example : 3 = 3 := by sorry",
             "-- *d* in a line comment, which says sorry, above a theorem",
             "theorem d_eq : 4 = 4 := by", "  rfl -- no sorry here",
             "/-- *e* -/ @[simp] theorem e_eq : 5 = 5 := rfl",
             "theorem after : sorry := sorry"]

    def test_the_declaration_below_the_tag(self):
        found = migrate_inputs.found
        self.assertEqual(found(self.LINES, "a", 1), (1, "passes"))
        self.assertEqual(found(self.LINES, "b", 1), (5, "sorry"))  # past its doc comment's end and its attribute
        self.assertEqual(found(self.LINES, "c", 1), (10, "sorry"))
        self.assertEqual(found(self.LINES, "d", 1), (11, "passes"))  # a comment's `sorry` is none
        self.assertEqual(found(self.LINES, "e", 1), (14, "passes"))  # it ends before the next line at the margin
        self.assertIsNone(found(self.LINES, "f", 1))
        twice = ["/-- *x* -/", "example : True := trivial", "/-- *x* -/", "example : True := sorry"]
        self.assertEqual((found(twice, "x", 1), found(twice, "x", 3)), ((1, "passes"), (3, "sorry")))  # the nearest

    def test_what_a_review_cites(self):
        text = (f"*t_one* and **bold** ([here]({BASIC}#L3), [there](Fixture/Uses.lean#L9)); *t_two*\n\n"
                f"*t_three* alone.\n\n[Linked]({BASIC}#L5) but no tag.")
        self.assertEqual(migrate_inputs.cited(text),
                         [("t_one", "Fixture/Basic.lean", 3), ("t_one", "Fixture/Uses.lean", 9),
                          ("t_two", "Fixture/Basic.lean", 3), ("t_two", "Fixture/Uses.lean", 9)])


if __name__ == "__main__":
    unittest.main()
