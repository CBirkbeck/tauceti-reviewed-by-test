import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from evidence_core import records as rec
from evidence_core.dataset import Dataset
from evidence_core.store import Store
from evidence_store.intake import Context

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import migrate_records  # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
