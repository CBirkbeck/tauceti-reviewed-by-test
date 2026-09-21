"""Recording review marks without a pull request (scripts/reviews.py)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from reviews import add, comment_marks, form_mark, from_event, make_record  # noqa: E402

INDEX = {"tauceti": "c0ffee", "declarations": [
    {"name": "TauCeti.IdealArithmeticFunction.vonMangoldt", "hash": "aaaaaaaaaaaa"},
    {"name": "NumberField.Set.HasNaturalDensity", "hash": "bbbbbbbbbbbb"}]}

FORM = """### Declaration

TauCeti.IdealArithmeticFunction.vonMangoldt

### Version reviewed

aaaaaaaaaaaa

### Mark

Reviewed-by: it is the intended mathematical notion

### Who reviewed

I did (a person)

### Agent, model and session (AI reviews only)

_No response_

### Evidence

It is log N(P) on powers of a prime P and 0 elsewhere, as in Neukirch VII.
"""


class Form(unittest.TestCase):
    def test_the_rendered_form_gives_one_mark(self):
        self.assertEqual(form_mark(FORM), {"decl": "TauCeti.IdealArithmeticFunction.vonMangoldt", "version": "aaaaaaaaaaaa",
                                           "trailer": "Reviewed-by", "kind": "person", "agent": "",
                                           "evidence": "It is log N(P) on powers of a prime P and 0 elsewhere, as in Neukirch VII."})

    def test_an_ai_review_names_its_agent(self):
        body = FORM.replace("I did (a person)", "An AI agent (details below)").replace(
            "### Agent, model and session (AI reviews only)\n\n_No response_", "### Agent, model and session (AI reviews only)\n\nClaude Code, Opus 5, session 095781b9")
        mark = form_mark(body)
        self.assertEqual((mark["kind"], mark["agent"]), ("agent", "Claude Code, Opus 5, session 095781b9"))


class Comments(unittest.TestCase):
    def test_each_line_is_a_mark(self):
        text = ("Checked these against Neukirch.\n\n"
                "Reviewed-by: TauCeti.IdealArithmeticFunction.vonMangoldt — log N(P) on prime powers\n"
                "Tested-by: NumberField.Set.HasNaturalDensity\n"
                "Reviewed-by is what the kernel calls it.\n")
        self.assertEqual(comment_marks(text), [
            {"decl": "TauCeti.IdealArithmeticFunction.vonMangoldt", "version": "", "trailer": "Reviewed-by", "kind": "person", "agent": "",
             "evidence": "log N(P) on prime powers"},
            {"decl": "NumberField.Set.HasNaturalDensity", "version": "", "trailer": "Tested-by", "kind": "person", "agent": "", "evidence": ""}])

    def test_an_agent_says_so_in_a_marker(self):
        text = ('<!--reviewed-by:v1 {"agent": "Codex, GPT-6, session codex-a71f92"}-->\n'
                "Tested-by: NumberField.Set.HasNaturalDensity")
        mark = comment_marks(text)[0]
        self.assertEqual((mark["kind"], mark["agent"], mark["trailer"]), ("agent", "Codex, GPT-6, session codex-a71f92", "Tested-by"))

    def test_a_mark_that_is_not_used_is_refused_with_the_marks_there_are(self):
        [mark] = comment_marks("Acked-by: NumberField.Set.HasNaturalDensity — looks right")
        record, problem = make_record(mark, INDEX, "someone", {"issue": 1, "comment": 2}, "now")
        self.assertIsNone(record)
        self.assertEqual(problem, "the mark is one of Reviewed-by, Tested-by")


class Records(unittest.TestCase):
    def mark(self, **changes):
        mark = form_mark(FORM)
        mark.update(changes)
        return mark

    def test_a_mark_is_pinned_to_the_version_reviewed(self):
        record, problem = make_record(self.mark(), INDEX, "someone", {"issue": 4}, "2026-09-21T15:00:00Z")
        self.assertIsNone(problem)
        self.assertEqual({k: record[k] for k in ("decl", "hash", "tauceti", "trailer", "by", "kind")},
                         {"decl": "TauCeti.IdealArithmeticFunction.vonMangoldt", "hash": "aaaaaaaaaaaa", "tauceti": "c0ffee",
                          "trailer": "Reviewed-by", "by": "someone", "kind": "person"})

    def test_a_mark_without_a_version_takes_the_current_one(self):
        record, _ = make_record(self.mark(version=""), INDEX, "someone", {"issue": 4}, "now")
        self.assertEqual(record["hash"], "aaaaaaaaaaaa")

    def test_an_earlier_version_is_kept_and_flagged(self):
        record, _ = make_record(self.mark(version="999999999999"), INDEX, "someone", {"issue": 4}, "now")
        self.assertEqual(record["hash"], "999999999999")
        self.assertTrue(record["stale"])

    def test_an_unknown_name_is_refused_with_a_suggestion(self):
        record, problem = make_record(self.mark(decl="TauCeti.IdealArithmeticFunction.vonMangold"), INDEX, "someone", {}, "now")
        self.assertIsNone(record)
        self.assertIn("TauCeti.IdealArithmeticFunction.vonMangoldt", problem)

    def test_a_form_needs_evidence(self):
        record, problem = make_record(self.mark(evidence=""), INDEX, "someone", {"issue": 4}, "now")
        self.assertIsNone(record)
        self.assertIn("evidence", problem)

    def test_the_same_mark_twice_is_recorded_once(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = Path(folder) / "records.jsonl"
            record, _ = make_record(self.mark(), INDEX, "someone", {"issue": 4}, "now")
            self.assertTrue(add(ledger, record))
            self.assertFalse(add(ledger, dict(record, at="later", source={"issue": 5})))
            self.assertEqual(len(ledger.read_text().splitlines()), 1)
            self.assertEqual(json.loads(ledger.read_text())["decl"], "TauCeti.IdealArithmeticFunction.vonMangoldt")


class Events(unittest.TestCase):
    def run_event(self, event):
        with tempfile.TemporaryDirectory() as folder:
            ledger = Path(folder) / "records.jsonl"
            reply, outputs = from_event(event, INDEX, ledger, "https://example.org/", "2026-09-21T15:00:00Z")
            return reply, outputs, ledger.read_text().splitlines() if ledger.exists() else []

    def test_a_submitted_form_is_recorded_and_its_issue_closed(self):
        reply, outputs, lines = self.run_event({"issue": {"number": 7, "user": {"login": "alice"}, "body": FORM}})
        self.assertEqual((outputs["recorded"], outputs["close"], len(lines)), (1, "true", 1))
        self.assertIn("✓ **Reviewed-by:** @alice on `TauCeti.IdealArithmeticFunction.vonMangoldt`", reply)

    def test_a_comment_records_its_good_lines_and_explains_the_rest(self):
        comment = {"id": 99, "user": {"login": "bob"}, "body": "Reviewed-by: NumberField.Set.HasNaturalDensity\nTested-by: TauCeti.Nope"}
        reply, outputs, lines = self.run_event({"issue": {"number": 1, "user": {"login": "alice"}, "body": ""}, "comment": comment})
        self.assertEqual((outputs["recorded"], outputs["problems"], outputs["close"], len(lines)), (1, 1, "false", 1))
        self.assertIn("`TauCeti.Nope` is not a declaration on the page", reply)

    def test_a_comment_without_marks_gets_no_reply(self):
        comment = {"id": 5, "user": {"login": "bob"}, "body": "Which ones should I look at first?"}
        reply, outputs, _ = self.run_event({"issue": {"number": 1, "user": {"login": "alice"}, "body": ""}, "comment": comment})
        self.assertEqual((reply, outputs["recorded"]), ("", 0))


if __name__ == "__main__":
    unittest.main()
