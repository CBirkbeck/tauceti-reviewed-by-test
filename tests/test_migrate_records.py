"""`migrate_records.py standard`: the migration's checked results as records of the store, and the list held for the
owner. Built on a temporary store and the fixture dataset (version B), as the tests of `voyager-refused` are."""
import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from evidence_core import records as rec
from evidence_core.dataset import Dataset
from evidence_core.store import Store

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))
import fixture_site  # noqa: E402
import migrate_records  # noqa: E402
import site_data  # noqa: E402
import standard  # noqa: E402

DATASET = HERE / "fixtures" / "dataset-b"
AT = "2026-11-02T09:30:00Z"
PREFIX = "standard-migration-2026-11-02"
#: The migration, as its records name it: Claude through CBirkbeck's account, in the run named by the prefix.
MIGRATION = {"kind": "agent", "identity": {"kind": "github", "id": "CBirkbeck"}, "involvement": "unknown",
             "agent": {"tool": "Tau Ceti review migration", "model": "claude-opus-5-5", "session": PREFIX}}
#: The same reviewer in an earlier run.
MIGRATION_BEFORE = {**MIGRATION, "agent": {**MIGRATION["agent"], "session": "standard-migration-pilot"}}
#: Where the records files are in the repository, as an origin links them.
ORIGIN = "https://github.com/CBirkbeck/tauceti-reviewed-by-test/blob/main/evidence/records/"
SITE = "https://cbirkbeck.github.io/tauceti-reviewed-by-test/"
HELD_NOTE = "Written in the migration; held for the owner."
#: An AI's cells: every axis looked at, one not applicable.
CELLS = {**fixture_site.CELLS, "choice": "na"}
AGENT, ASTRA, SOMEONE = fixture_site.AGENT, fixture_site.ASTRA, fixture_site.SOMEONE


def review(name: str) -> str:
    """A review that passes `standard.check`: the three parts, none empty."""
    return (f"## What it says\n`{name}` is what its signature says.\n\n## References and tests\n"
            f"- Fixture documentation, §1.\n\n## Lean subtleties\nNone.")


def link(name: str) -> str:
    return f"{SITE}#/d/{name}"


#: A reference no text of a bundle gives: the checker fails a review that holds it.
UNTRACED = "- Bourbaki, *Algebra*, Chapter II."


class StandardRecordsTests(unittest.TestCase):
    """The records and the held list the `standard` subcommand makes of bundles, results and checks."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        self.records_dir = self.dir / "evidence" / "records"
        self.records_dir.mkdir(parents=True)
        shutil.copy(HERE.parent / "evidence" / "store.json", self.dir / "evidence" / "store.json")
        self.ds = Dataset.load(DATASET)
        self.held = self.dir / "docs" / "standard-reviews-held.md"
        self.source = self.dir / "tauceti"  # Tau Ceti at the bundles' commit: a directory, with no Check to look for
        self.source.mkdir()
        self.n = 0

    # --- what the store holds ----------------------------------------------------------------------

    def key(self, name: str) -> dict:
        return rec.subject_from_decl(self.ds.by_name[name], self.ds)

    def put(self, *records: dict) -> list[dict]:
        """The records (each given its id) added to the temporary store, as they were filed in one file."""
        self.n += 1
        out = [rec.with_id(r) for r in records]
        with (self.records_dir / f"earlier-{self.n}.jsonl").open("w", encoding="utf-8") as f:
            for r in out:
                f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
        return out

    def verdict(self, name: str, verdict: str, by: dict, at: str, text: str = "It is fine.", **more) -> dict:
        """A review of an earlier form, as the intake recorded it."""
        r = {"schema": rec.SCHEMA, "kind": "review", "verdict": verdict, "subject": self.key(name), "by": by,
             "at": at, "origin": {"kind": "issue", "ref": f"example/fixture-store#{1000 + self.n}"}, "text": text}
        if verdict == "problem":
            r.update(category="edge-cases", rubric="ltb-rubric/1")
        return {**r, **more}

    def yes(self, name: str, by: dict = AGENT, at: str = "2026-10-22T10:00:00Z") -> dict:
        return self.put(self.verdict(name, "accept", by, at))[0]

    # --- what the writer and the checker left ------------------------------------------------------

    @staticmethod
    def bundle(name: str, **more) -> dict:
        """A bundle whose docstring gives the reference of `review`."""
        return {"decl": name, "kind": "theorem", "package": "Fixture", "commit": "B",
                "docstring": "As the Fixture documentation, §1, has it.", "reviews": [], "tests": [], "checks": [],
                "named": None, "roadmap": None, "open_no": False, **more}

    @staticmethod
    def result(name: str, verdict: str = "approve", hold: str = "", **more) -> dict:
        return {"decl": name, "cells": dict(CELLS), "verdict": verdict, "hold": hold, "review": review(name), **more}

    @staticmethod
    def failing(name: str, verdict: str = "approve", hold: str = "") -> dict:
        """A result the checker fails: its reference is in no text of its bundle."""
        result = StandardRecordsTests.result(name, verdict, hold)
        return {**result, "review": result["review"].replace("- Fixture documentation, §1.", UNTRACED)}

    @staticmethod
    def check(name: str, ok: bool = True, *problems: str) -> dict:
        return {"decl": name, "ok": ok, "problems": list(problems)}

    def run_main(self, results: list[dict], bundles: list[dict] | None = None, checks: list[dict] | None = None,
                 *more: str, at: str | None = AT, source: Path | None = None) -> tuple[int, str]:
        """The subcommand on these results, each with a bundle and a passing check unless given."""
        bundles = [self.bundle(r["decl"]) for r in results] if bundles is None else bundles
        checks = [self.check(r["decl"]) for r in results] if checks is None else checks
        paths = []
        for name, rows in (("bundles", bundles), ("results", results), ("checks", checks)):
            path = self.dir / f"{name}.jsonl"
            path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
            paths.append(str(path))
        said = io.StringIO()
        with contextlib.redirect_stdout(said), contextlib.redirect_stderr(said):
            code = migrate_records.main(["standard", *paths, "--dataset", str(DATASET),
                                         "--source", str(source or self.source),
                                         "--store", str(self.dir / "evidence"), "--out-dir", str(self.records_dir),
                                         "--prefix", PREFIX, "--held", str(self.held),
                                         *(["--at", at] if at else []), *more])
        return code, said.getvalue()

    def written(self) -> list[dict]:
        """The migration's records, in the order of its files and of their lines."""
        return [r for f in sorted(self.records_dir.glob(f"{PREFIX}-*.jsonl")) for r in rec.load(f)]

    def held_lines(self) -> list[str]:
        return [x for x in self.held.read_text(encoding="utf-8").splitlines() if x.startswith("- ")] \
            if self.held.exists() else []

    def held_line(self, name: str) -> str:
        found = [x for x in self.held_lines() if f"`{name}`" in x]
        self.assertEqual(len(found), 1, (name, found))
        return found[0]

    def site(self) -> site_data.Site:
        """The site as it reads the store now."""
        return site_data.Site(site_data.load(DATASET, self.dir / "evidence", None, None, fixture_site.SETTINGS))

    def rubric(self):
        return Store.load(self.dir / "evidence").rubric

    # --- the brief's four ---------------------------------------------------------------------------

    def test_approved_becomes_a_version_accept(self):
        old = self.yes("Fixture.triple")
        code, said = self.run_main([self.result("Fixture.triple")])
        self.assertEqual(code, 0, said)
        self.assertEqual(sorted(f.name for f in self.records_dir.glob(f"{PREFIX}-*")), [f"{PREFIX}-01.jsonl"])
        [r] = self.written()
        self.assertEqual(r, rec.with_id({
            "schema": rec.SCHEMA, "kind": "review", "verdict": "accept", "subject": self.key("Fixture.triple"),
            "by": MIGRATION, "at": AT, "origin": {"kind": "file", "ref": f"{ORIGIN}{PREFIX}-01.jsonl#L1"},
            "text": review("Fixture.triple"), "rubric": "ltb-rubric/1", "checked": CELLS,
            "standard": {"spec": standard.SPEC}}))  # no parent, note or dropped: it is a first version, not an edit
        self.assertEqual(rec.validate(r, {self.rubric().name: self.rubric()}), [])
        self.assertEqual(standard.kind_of(r), "version")
        # The site reads it as the declaration's current version, approved by the migration, the earlier yes counted
        # as an approval of an earlier version.
        summary = standard.summary(self.site().seen("Fixture.triple"))
        self.assertEqual(summary["version"], standard.version_of(review("Fixture.triple")))
        self.assertEqual(summary["record"]["id"], r["id"])
        self.assertTrue(summary["approving"] and summary["current"])
        self.assertEqual([a.record["id"] for a in summary["approvers"]], [r["id"]])
        self.assertEqual(summary["approvers"][0].record["by"], MIGRATION)
        self.assertEqual(summary["approvers"][0].record["checked"], CELLS)
        self.assertEqual(summary["earlier"], 1, old)
        self.assertFalse(self.held.exists())  # nothing was held

    def test_held_becomes_a_comment_and_a_held_line(self):
        name = "Fixture.double_zero"
        why = "`double 0 = 0` is stated for the naturals only, and an earlier yes took it for `Int`."
        first = self.yes(name, AGENT, "2026-10-22T10:01:00Z")
        latest = self.yes(name, ASTRA, "2026-10-23T10:00:00Z")  # the latest yes: any reviewer's
        no = self.put(self.verdict(name, "problem", SOMEONE, "2026-10-24T10:00:00Z", "Its name hides the cast."))[0]
        question = self.put(self.verdict(name, "question", SOMEONE, "2026-10-25T10:00:00Z", "Why not `Int`?"))[0]
        code, said = self.run_main([self.result(name, "hold", why)])
        self.assertEqual(code, 0, said)
        [r] = self.written()
        self.assertEqual(r, rec.with_id({
            "schema": rec.SCHEMA, "kind": "comment", "subject": self.key(name), "by": MIGRATION, "at": AT,
            "origin": {"kind": "file", "ref": f"{ORIGIN}{PREFIX}-01.jsonl#L1"}, "text": review(name),
            "standard": {"spec": standard.SPEC, "note": HELD_NOTE},
            "links": {"replies_to": latest["id"]}}))  # to the latest yes, not to the no or the question after it
        self.assertEqual(rec.validate(r, {self.rubric().name: self.rubric()}), [])
        self.assertEqual(standard.kind_of(r), "version")
        # The line for the owner: the declaration, the reason, and where to read it on the site.
        line = self.held_line(name)
        self.assertIn(why, line)
        self.assertIn(link(name), line)
        # On the site it is the declaration's review, but nobody approved it, and the no stays unanswered.
        site = self.site()
        summary = standard.summary(site.seen(name))
        self.assertEqual(summary["record"]["id"], r["id"])
        self.assertFalse(summary["approving"])
        self.assertEqual(summary["approvers"], [])
        self.assertEqual(summary["earlier"], 2, first)
        self.assertNotIn(no["id"], site.ev.replies)
        self.assertNotIn(question["id"], site.ev.replies)
        self.assertEqual([x["id"] for x in site.ev.replies[latest["id"]]], [r["id"]])
        # Run again: the comment is the declaration's review now, so there is no second one, and no second line.
        code, said = self.run_main([self.result(name, "hold", why)])
        self.assertEqual(code, 0, said)
        self.assertEqual(len(self.written()), 1)
        self.assertEqual(len(self.held_lines()), 1)

    def test_failed_checks_write_nothing_but_the_list(self):
        for name in ("Fixture.triple_one", "Fixture.triple_two", "Fixture.IsSmall"):
            self.yes(name)
        results = [self.failing("Fixture.triple_one"), {"decl": "Fixture.triple_two", "error": "unparseable line"},
                   self.failing("Fixture.IsSmall", "hold", "Twelve is small too, so the no stands.")]
        checks = [self.check("Fixture.triple_one", False, "an older checker's words"),
                  self.check("Fixture.triple_two", False, "its result line is not valid JSON"),
                  self.check("Fixture.IsSmall", False, "a reference cannot be traced")]
        code, said = self.run_main(results, None, checks)
        self.assertEqual(code, 0, said)
        self.assertEqual(list(self.records_dir.glob(f"{PREFIX}-*")), [])  # no file, let alone a record
        one = self.held_line("Fixture.triple_one")
        # What the check finds now, as this run checked it.
        self.assertIn('failed checks: the reference "Bourbaki, *Algebra*, Chapter II." is not in the bundle', one)
        self.assertIn(link("Fixture.triple_one"), one)
        two = self.held_line("Fixture.triple_two")
        self.assertIn("no result: unparseable line", two)  # an error: the error is the reason, not the check's line
        self.assertIn(link("Fixture.triple_two"), two)
        # A review held and then failed is a failure to record, but the writer's concern is not lost with it.
        held = self.held_line("Fixture.IsSmall")
        self.assertIn("failed checks: the reference", held)
        self.assertIn("Twelve is small too, so the no stands.", held)
        # Beside a result that passes, only that one is recorded.
        self.yes("Fixture.double")
        code, said = self.run_main(results + [self.result("Fixture.double")], None,
                                   checks + [self.check("Fixture.double")])
        self.assertEqual(code, 0, said)
        self.assertEqual([r["subject"]["name"] for r in self.written()], ["Fixture.double"])
        self.assertEqual(len(self.held_lines()), 3)  # the three lines were there already: not said twice

    def test_a_run_takes_only_what_was_written(self):
        """A run is a wave: the writing is spread over several runs, as usage limits allow, and `collect` gives each
        bundle not written yet `no result`. Such a declaration is not in the run: it gets no record and no line, and its
        check, if it has one, is not read."""
        self.yes("Fixture.triple")
        results = [self.result("Fixture.triple"), {"decl": "Fixture.double", "error": "no result"}]
        checks = [self.check("Fixture.triple"), self.check("Fixture.double", False, "no result was written for it")]
        code, said = self.run_main(results, None, checks)
        self.assertEqual(code, 0, said)
        self.assertEqual([r["subject"]["name"] for r in self.written()], ["Fixture.triple"])
        self.assertFalse(self.held.exists())  # nothing for the owner
        code, said = self.run_main([{"decl": "Fixture.IsSmall", "error": "no result"}], None, [])
        self.assertEqual(code, 0, said)
        self.assertFalse(self.held.exists())

    def test_the_held_list_follows_the_runs(self):
        """The final review's Important 2: the held list is reconciled with each run, not only added to. A later run,
        a retry round or the next wave, takes out the line of a declaration it approves, and gives one it lists again
        one line, the new one; a run's heading goes with its last line."""
        for name in ("Fixture.IsSmall", "Fixture.double"):
            self.yes(name)
        first = [self.result("Fixture.one", "hold", "It is `1`, not one."),  # no yes to reply to: no record
                 self.failing("Fixture.triple"), self.failing("Fixture.IsSmall"), self.failing("Fixture.double")]
        checks = [self.check("Fixture.one"), *(self.check(r["decl"], False, "x") for r in first[1:])]
        code, said = self.run_main(first, None, checks)
        self.assertEqual(code, 0, said)
        self.assertEqual(self.written(), [])
        self.assertEqual(len(self.held_lines()), 4)
        # The next run approves two of them and holds a third; the fourth is not in it.
        second = [self.result("Fixture.one"), self.result("Fixture.triple"),
                  self.result("Fixture.IsSmall", "hold", "Twelve is small too.")]
        later = "2026-11-03T09:30:00Z"
        code, said = self.run_main(second, at=later)
        self.assertEqual(code, 0, said)
        self.assertEqual({r["subject"]["name"]: r["kind"] for r in self.written()},
                         {"Fixture.one": "review", "Fixture.triple": "review", "Fixture.IsSmall": "comment"})
        self.assertEqual([x.split("`")[1] for x in self.held_lines()], ["Fixture.double", "Fixture.IsSmall"])
        self.assertIn("Twelve is small too.", self.held_line("Fixture.IsSmall"))
        self.assertNotIn("failed checks", self.held_line("Fixture.IsSmall"))
        text = self.held.read_text(encoding="utf-8")
        self.assertEqual([x for x in text.split("\n") if x.startswith("#")],
                         ["# Standard reviews held for the owner", f"## {PREFIX}, {AT}", f"## {PREFIX}, {later}"])
        self.assertNotIn("\n\n\n", text)
        # A run that approves the last line of a heading takes the heading too; the title stays.
        code, said = self.run_main([self.result("Fixture.double")], at="2026-11-04T09:30:00Z")
        self.assertEqual(code, 0, said)
        text = self.held.read_text(encoding="utf-8")
        self.assertEqual([x for x in text.split("\n") if x.startswith("#")],
                         ["# Standard reviews held for the owner", f"## {PREFIX}, {later}"])
        self.assertTrue(text.startswith(migrate_records.HELD_TITLE))
        self.assertEqual([x.split("`")[1] for x in self.held_lines()], ["Fixture.IsSmall"])
        self.assertNotIn("\n\n\n", text)

    def test_files_cap_at_2000(self):
        self.assertEqual(migrate_records.PER_FILE, 2000)
        name = "Fixture.triple"
        records = [{"schema": rec.SCHEMA, "kind": "review", "verdict": "accept", "subject": self.key(name),
                    "by": MIGRATION, "at": AT, "text": review(name) + f"\n\n(No. {k}.)", "rubric": "ltb-rubric/1",
                    "checked": dict(CELLS), "standard": {"spec": standard.SPEC}} for k in range(4001)]
        files, problems = migrate_records.write_files(records, self.dir / "capped", PREFIX, self.rubric())
        self.assertEqual(problems, [])
        self.assertEqual([f.name for f in files], [f"{PREFIX}-{k:02d}.jsonl" for k in (1, 2, 3)])
        self.assertEqual([len(rec.load(f)) for f in files], [2000, 2000, 1])
        for f in files:
            for n, r in enumerate(rec.load(f), 1):
                # Its own file, and its own line of it.
                self.assertEqual(r["origin"], {"kind": "file", "ref": f"{ORIGIN}{f.name}#L{n}"})
                self.assertEqual(r["id"], rec.record_id(r))
        # And through the subcommand: six results, two to a file.
        names = ["Fixture.triple", "Fixture.double", "Fixture.IsSmall", "Fixture.one", "Fixture.Pos",
                 "Fixture.double_two"]
        for each in names:
            self.yes(each)
        with mock.patch.object(migrate_records, "PER_FILE", 2):
            code, said = self.run_main([self.result(each) for each in names])
        self.assertEqual(code, 0, said)
        by_file = {f.name: [r["subject"]["name"] for r in rec.load(f)]
                   for f in sorted(self.records_dir.glob(f"{PREFIX}-*.jsonl"))}
        self.assertEqual(by_file, {f"{PREFIX}-01.jsonl": names[0:2], f"{PREFIX}-02.jsonl": names[2:4],
                                   f"{PREFIX}-03.jsonl": names[4:6]})

    # --- the rest of what the records must do ------------------------------------------------------------

    def test_a_hold_with_no_yes_to_reply_to_writes_no_record(self):
        name = "Fixture.one_pos'"
        self.put(self.verdict(name, "problem", SOMEONE, "2026-10-24T10:00:00Z", "Positive, it says, of `1`."))
        code, said = self.run_main([self.result(name, "hold", "The statement is about `1`, not `n`.")])
        self.assertEqual(code, 0, said)
        self.assertEqual(self.written(), [])  # a no is not a yes to answer
        line = self.held_line(name)
        self.assertIn("no yes to attach the review to", line)
        self.assertIn("The statement is about `1`, not `n`.", line)  # the owner still learns why it was held
        self.assertIn(link(name), line)

    def test_an_open_no_holds_an_approval(self):
        # The bundle says so: the check fails an approval, and the writer is told to hold it.
        self.yes("Fixture.IsSmall")
        # The store says so now, though the bundle was made before the no.
        yes_three = self.yes("Fixture.isSmall_three")
        no = self.put(self.verdict("Fixture.isSmall_three", "problem", SOMEONE, "2026-10-25T10:00:00Z",
                                   "Not small."))[0]
        # An open no beside a yes is no reason for a hold if it has been dealt with.
        self.yes("Fixture.double_two")
        closed = self.put(self.verdict("Fixture.double_two", "problem", SOMEONE, "2026-10-25T11:00:00Z", "Wrong."))[0]
        self.put({"schema": rec.SCHEMA, "kind": "status", "target": closed["id"], "state": "invalid", "by": AGENT,
                  "text": "It is right.", "at": "2026-10-26T10:00:00Z",
                  "origin": {"kind": "issue", "ref": "example/fixture-store#2000"}})
        names = ["Fixture.IsSmall", "Fixture.isSmall_three", "Fixture.double_two"]
        bundles = [self.bundle("Fixture.IsSmall", open_no=True), self.bundle("Fixture.isSmall_three"),
                   self.bundle("Fixture.double_two")]
        checks = [self.check("Fixture.IsSmall", False, "open"), self.check("Fixture.isSmall_three"),
                  self.check("Fixture.double_two")]
        code, said = self.run_main([self.result(each) for each in names], bundles, checks)
        self.assertEqual(code, 0, said)
        by_name = {r["subject"]["name"]: r for r in self.written()}
        self.assertEqual({k: v["kind"] for k, v in by_name.items()},
                         {"Fixture.isSmall_three": "comment", "Fixture.double_two": "review"})
        self.assertIn("failed checks: the declaration has an open no", self.held_line("Fixture.IsSmall"))
        self.assertEqual(by_name["Fixture.isSmall_three"]["standard"], {"spec": standard.SPEC, "note": HELD_NOTE})
        self.assertIn("a no on it is open", self.held_line("Fixture.isSmall_three"))
        self.assertEqual(by_name["Fixture.isSmall_three"]["links"]["replies_to"], yes_three["id"], no)  # to the yes
        self.assertEqual(len(self.held_lines()), 2)

    def test_a_declaration_with_a_standard_review_already_is_left_alone(self):
        name = "Fixture.triple_pos"
        self.yes(name, ASTRA)
        version = self.put(fixture_site.accepting(self.key(name), AGENT, "2026-10-30T10:00:00Z", review(name),
                                                  fixture_site.bulk(4101), {}))[0]
        withdrawn = "Fixture.double"  # a version withdrawn since is none
        self.yes(withdrawn, ASTRA)
        gone = self.put(fixture_site.accepting(self.key(withdrawn), AGENT, "2026-10-30T10:00:00Z", review(withdrawn),
                                               fixture_site.bulk(4102), {}))[0]
        self.put({"schema": rec.SCHEMA, "kind": "status", "target": gone["id"], "state": "withdrawn", "by": AGENT,
                  "text": "Withdrawn.", "at": "2026-10-30T11:00:00Z", "origin": fixture_site.bulk(4103)})
        held = "Fixture.IsSmall"  # a hold on a declaration with a review is said to the owner, and writes no comment
        self.yes(held)
        self.put(fixture_site.accepting(self.key(held), AGENT, "2026-10-30T10:00:00Z", review(held),
                                        fixture_site.bulk(4104), {}))
        results = [self.result(name), self.result(withdrawn), self.result(held, "hold", "Edge cases differ.")]
        code, said = self.run_main(results)
        self.assertEqual(code, 0, said)
        self.assertEqual([r["subject"]["name"] for r in self.written()], [withdrawn])
        self.assertIn(name, said)  # said in the run's report
        # The review there is still the current one.
        self.assertEqual(standard.summary(self.site().seen(name))["record"]["id"], version["id"])
        self.assertIn("Edge cases differ.", self.held_line(held))
        self.assertEqual(len(self.held_lines()), 1)
        # Run again: it is all there already, so nothing is written and nothing said twice.
        before = self.held.read_text(encoding="utf-8")
        code, said = self.run_main(results)
        self.assertEqual(code, 0, said)
        self.assertEqual([r["subject"]["name"] for r in self.written()], [withdrawn])
        self.assertEqual(self.held.read_text(encoding="utf-8"), before)

    def test_the_accept_supersedes_only_the_migration_s_own_earlier_yes(self):
        name = "Fixture.triple"
        mine_then = self.yes(name, MIGRATION_BEFORE, "2026-10-21T10:00:00Z")
        mine_later = self.yes(name, MIGRATION_BEFORE, "2026-10-23T10:00:00Z")
        self.yes(name, ASTRA, "2026-10-24T10:00:00Z")  # the latest yes, but another reviewer's
        code, said = self.run_main([self.result(name)])
        self.assertEqual(code, 0, said)
        [r] = self.written()
        self.assertEqual(r["links"], {"supersedes": mine_later["id"]}, mine_then)
        self.assertEqual(r["id"], rec.record_id(r))
        site = self.site()
        self.assertEqual(site.ev.superseded_by[mine_later["id"]], r["id"])
        # A migration review held for the owner is a comment: it supersedes nothing.
        self.yes("Fixture.double", MIGRATION_BEFORE)
        code, said = self.run_main([self.result("Fixture.double", "hold", "Check it.")])
        self.assertEqual(code, 0, said)
        self.assertEqual(self.written()[-1]["kind"], "comment")
        self.assertNotIn("supersedes", self.written()[-1]["links"])

    def test_what_cannot_be_recorded_is_refused_and_nothing_is_written(self):
        self.yes("Fixture.triple")
        for name in ("Fixture.double", "Fixture.IsSmall", "Fixture.one"):
            self.yes(name)
        good = self.result("Fixture.triple")
        too_short = {**self.result("Fixture.double"), "review": "## What it says\nIt is `double`."}
        error_cell = {**self.result("Fixture.IsSmall"), "cells": {**CELLS, "junk": "error"}}
        for what, results, bundles, checks, word in (
                ("a result with no check", [good, self.result("Fixture.double")], None, [self.check("Fixture.triple")],
                 "no check"),
                ("a check with no result", [good], None, [self.check("Fixture.triple"), self.check("Fixture.double")],
                 "no result"),
                ("a result with no bundle", [good, self.result("Fixture.double")], [self.bundle("Fixture.triple")],
                 None, "no bundle"),
                ("a bundle at another commit", [good, self.result("Fixture.double")],
                 [self.bundle("Fixture.triple", commit="A"), self.bundle("Fixture.double", commit="A")], None,
                 "another commit"),
                ("a declaration the dataset lacks", [good, self.result("Fixture.notThere")], None, None, "notThere"),
                ("a declaration twice", [good, good], [self.bundle("Fixture.triple")], [self.check("Fixture.triple")],
                 "twice"),
                ("a review that is no review", [good, too_short], None, None, "Fixture.double"),
                ("an approval with an error cell", [good, error_cell], None, None, "Fixture.IsSmall")):
            with self.subTest(what):
                code, said = self.run_main(results, bundles, checks)
                self.assertEqual(code, 1, said)
                self.assertIn(word, said)
                self.assertEqual(said.count("another commit"), word == "another commit")  # said once, not for each
                self.assertEqual(list(self.records_dir.glob(f"{PREFIX}-*")), [])  # not even the good one
                self.assertFalse(self.held.exists())
        for at in ("2026-11-02", "2026-11-02 09:30:00", "now", "2026-11-02T09:30:00+00:00"):
            with self.subTest(at=at):
                code, said = self.run_main([good], None, None, at=at)
                self.assertEqual(code, 2, said)
                self.assertEqual(list(self.records_dir.glob(f"{PREFIX}-*")), [])

    def test_each_result_is_checked_again(self):
        """The final review's Minor 2: the run checks each result again, as migrate_check.py does, against Tau Ceti at
        the bundles' commit. A check of CHECKS that passes a result this check fails, or fails one it passes, stops the
        run: checks from an older checker, or of other results, never let a result through."""
        for name in ("Fixture.triple", "Fixture.double"):
            self.yes(name)
        results = [self.result("Fixture.triple"), self.failing("Fixture.double")]
        for what, checks, name in (
                ("a pass of a result it fails", [self.check("Fixture.triple"), self.check("Fixture.double")],
                 "Fixture.double"),
                ("a failure of a result it passes",
                 [self.check("Fixture.triple", False, "an older rule"), self.check("Fixture.double", False, "x")],
                 "Fixture.triple")):
            with self.subTest(what):
                code, said = self.run_main(results, None, checks)
                self.assertEqual(code, 1, said)
                self.assertIn(f"`{name}`", said)
                self.assertEqual(list(self.records_dir.glob(f"{PREFIX}-*")), [])  # not even the other one
                self.assertFalse(self.held.exists())
        # Checks that agree: the result it passes is recorded, and the other listed with what this check finds.
        code, said = self.run_main(results, None, [self.check("Fixture.triple"),
                                                   self.check("Fixture.double", False, "an older checker's words")])
        self.assertEqual(code, 0, said)
        self.assertEqual([r["subject"]["name"] for r in self.written()], ["Fixture.triple"])
        self.assertIn("is not in the bundle", self.held_line("Fixture.double"))
        self.assertNotIn("an older checker's words", self.held_line("Fixture.double"))

    def test_tau_ceti_is_given_at_the_bundles_commit(self):
        self.yes("Fixture.triple")
        results = [self.result("Fixture.triple")]
        # It is required: the check looks for a Check's tag there.
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            migrate_records.main(["standard", "b", "r", "c", "--dataset", str(DATASET), "--prefix", PREFIX])
        # A checkout at another commit than the bundles', and a path that is no directory, are refused.
        checkout = self.dir / "checkout"
        checkout.mkdir()
        (checkout / "README.md").write_text("Tau Ceti\n", encoding="utf-8")
        for args in (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "Tau Ceti"]):
            subprocess.run(["git", "-C", str(checkout), "-c", "user.name=t", "-c", "user.email=t@e.org", *args],
                           check=True, capture_output=True)
        for source in (checkout, self.dir / "nowhere"):
            with self.subTest(source=source.name):
                code, said = self.run_main(results, source=source)
                self.assertEqual(code, 2, said)
                self.assertIn(str(source), said)
                self.assertEqual(list(self.records_dir.glob(f"{PREFIX}-*")), [])
        code, said = self.run_main(results)  # a directory that is no checkout is taken as it is
        self.assertEqual(code, 0, said)

    def test_a_refusal_prints_no_more_than_it_can_read(self):
        names = [d.name for d in self.ds.decls][:60]
        code, said = self.run_main([self.result(name) for name in names], None, [])  # not one has its check
        self.assertEqual(code, 1, said)
        self.assertEqual(said.count("it has a result but no check"), migrate_records.SHOWN)
        self.assertIn(f"60 problems", said)
        self.assertIn(f"and {60 - migrate_records.SHOWN} more", said)
        self.assertEqual(list(self.records_dir.glob(f"{PREFIX}-*")), [])

    def test_bundles_without_a_result_are_not_part_of_the_run(self):
        # A retry round's results hold only what it ran again: the bundles are the whole batch's.
        self.yes("Fixture.triple")
        bundles = [self.bundle("Fixture.triple"), self.bundle("Fixture.double"), self.bundle("Fixture.IsSmall")]
        code, said = self.run_main([self.result("Fixture.triple")], bundles)
        self.assertEqual(code, 0, said)
        self.assertEqual([r["subject"]["name"] for r in self.written()], ["Fixture.triple"])
        self.assertFalse(self.held.exists())

    def test_unreadable_input_is_an_error_and_nothing_is_written(self):
        self.yes("Fixture.triple")
        good = self.result("Fixture.triple")
        self.run_main([good])  # the three files, as they should be
        for which, damage in (("results", "{not json}\n"), ("checks", "[1, 2]\n"), ("bundles", None)):
            with self.subTest(which):
                path = self.dir / f"{which}.jsonl"
                kept = path.read_text(encoding="utf-8")
                path.unlink() if damage is None else path.write_text(damage, encoding="utf-8")
                said = io.StringIO()
                with contextlib.redirect_stdout(said), contextlib.redirect_stderr(said):
                    code = migrate_records.main(
                        ["standard", *(str(self.dir / f"{x}.jsonl") for x in ("bundles", "results", "checks")),
                         "--dataset", str(DATASET), "--source", str(self.source),
                         "--store", str(self.dir / "evidence"), "--out-dir", str(self.dir / "elsewhere"),
                         "--prefix", PREFIX, "--held", str(self.dir / "held.md"), "--at", AT])
                self.assertEqual(code, 2, said.getvalue())
                self.assertFalse((self.dir / "elsewhere").exists() or (self.dir / "held.md").exists())
                path.write_text(kept, encoding="utf-8")

    def test_a_review_is_recorded_as_the_agent_s_version_of_it(self):
        # A Unicode line separator in a line is no line end (JSON lines end at `\n` alone), and a version is the hash of
        # the text normalized: no space at the end of a line. (A `\r` is a control character, which the check refuses:
        # `migrate_write.py add` writes none.)
        name = "Fixture.triple"
        self.yes(name)
        raw = review(name).replace("None.", "A line\u2028separator and a \x85 next line, here.   ")
        code, said = self.run_main([{**self.result(name), "review": raw}])
        self.assertEqual(code, 0, said)
        [r] = self.written()
        self.assertEqual(r["text"], standard.normalize(raw))
        self.assertIn("A line\u2028separator and a \x85 next line, here.", r["text"])
        self.assertNotIn("here. ", r["text"])
        self.assertEqual(standard.version_of(r["text"]), standard.version_of(raw))

    def test_the_held_list_is_appended_to(self):
        for name in ("Fixture.triple_one", "Fixture.triple_two", "Fixture.double"):
            self.yes(name)
        code, said = self.run_main([self.failing("Fixture.triple_one")], None,
                                   [self.check("Fixture.triple_one", False, "x")])
        self.assertEqual(code, 0, said)
        first = self.held.read_text(encoding="utf-8")
        self.assertTrue(first.startswith("# "))  # a title, once
        code, said = self.run_main([self.failing("Fixture.triple_two"), self.result("Fixture.double", "hold", "Look.")],
                                   None, [self.check("Fixture.triple_two", False, "y"), self.check("Fixture.double")])
        self.assertEqual(code, 0, said)
        text = self.held.read_text(encoding="utf-8")
        self.assertTrue(text.startswith(first))  # what was there is left as it was
        self.assertEqual(text.count("\n# "), 0)
        self.assertNotIn("\n\n\n", text)  # a blank line between a list and the next heading, not two
        self.assertEqual([x.split("`")[1] for x in self.held_lines()],
                         ["Fixture.triple_one", "Fixture.triple_two", "Fixture.double"])
        self.assertEqual(sum(PREFIX in x for x in text.splitlines() if x.startswith("#")), 2)  # a heading a run

    def test_a_run_writes_new_files_and_never_touches_the_old(self):
        self.yes("Fixture.triple")
        self.yes("Fixture.double")
        code, said = self.run_main([self.result("Fixture.triple")])
        self.assertEqual(code, 0, said)
        first = (self.records_dir / f"{PREFIX}-01.jsonl").read_bytes()
        code, said = self.run_main([self.result("Fixture.double")])
        self.assertEqual(code, 0, said)
        self.assertEqual((self.records_dir / f"{PREFIX}-01.jsonl").read_bytes(), first)
        [second] = rec.load(self.records_dir / f"{PREFIX}-02.jsonl")
        self.assertEqual(second["subject"]["name"], "Fixture.double")
        self.assertEqual(second["origin"]["ref"], f"{ORIGIN}{PREFIX}-02.jsonl#L1")

    def test_the_records_name_the_model_that_wrote_them(self):
        """A run takes one model's results, and its records name that model: Claude Opus wrote the first reviews, and
        Claude Sonnet writes the rest."""
        for name in ("Fixture.triple", "Fixture.double", "Fixture.IsSmall"):
            self.yes(name)
        code, said = self.run_main([self.result("Fixture.triple")])
        self.assertEqual(code, 0, said)
        sonnet = {**MIGRATION, "agent": {**MIGRATION["agent"], "model": "claude-sonnet-5-5"}}
        code, said = self.run_main([self.result("Fixture.double"), self.result("Fixture.IsSmall", "hold", "Look.")],
                                   None, None, "--model", "claude-sonnet-5-5")
        self.assertEqual(code, 0, said)
        self.assertIn("claude-sonnet-5-5", said)
        self.assertEqual([(r["subject"]["name"], r["kind"], r["by"]) for r in self.written()],
                         [("Fixture.triple", "review", MIGRATION),  # claude-opus-5-5 unless a run names another
                          ("Fixture.double", "review", sonnet), ("Fixture.IsSmall", "comment", sonnet)])

    def test_the_time_is_the_run_s_unless_given(self):
        self.yes("Fixture.triple")
        code, said = self.run_main([self.result("Fixture.triple")], at=None)
        self.assertEqual(code, 0, said)
        [r] = self.written()
        self.assertRegex(r["at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertGreater(r["at"], "2026-10-31T00:00:00Z")

    def test_a_declaration_links_to_the_site_as_the_page_does(self):
        # JavaScript's encodeURIComponent: UTF-8 percent-escaped; letters, digits and - _ . ! ~ * ' ( ) as they are.
        self.assertEqual(migrate_records.site_link("Fixture.one_pos'"), SITE + "#/d/Fixture.one_pos'")
        self.assertEqual(migrate_records.site_link("Fixture.«term𝟚_»"),
                         SITE + "#/d/Fixture.%C2%ABterm%F0%9D%9F%9A_%C2%BB")
        self.assertEqual(migrate_records.site_link("a b/c?d#e"), SITE + "#/d/a%20b%2Fc%3Fd%23e")


if __name__ == "__main__":
    unittest.main()
