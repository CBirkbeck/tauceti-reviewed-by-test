"""Recording review marks without a pull request (scripts/reviews.py)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from reviews import add, comment_marks, count_text, form_mark, form_report, from_event, make_record, make_report, tally  # noqa: E402

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


class Tally(unittest.TestCase):
    """How many people and AI agents gave each mark: what the page and the code show instead of every name."""

    def mark(self, trailer, kind, by, agent="", current=True):
        return {"trailer": trailer, "kind": kind, "by": by, "agent": agent, "current": current}

    def test_people_and_ai_agents_are_counted_apart_on_the_current_version(self):
        marks = [self.mark("Reviewed-by", "person", "alice"), self.mark("Reviewed-by", "person", "bob"),
                 self.mark("Reviewed-by", "agent", "alice", "Claude Code, Opus 5, session a1"),
                 self.mark("Reviewed-by", "agent", "bob", "Codex, GPT-6, session c1"),
                 self.mark("Tested-by", "person", "carol"),
                 self.mark("Reviewed-by", "person", "dave", current=False)]
        self.assertEqual(tally(marks), {"Reviewed-by": {"people": 2, "ai": 2, "earlier": 1},
                                        "Tested-by": {"people": 1, "ai": 0, "earlier": 0}})

    def test_the_same_reviewer_twice_counts_once(self):
        marks = [self.mark("Reviewed-by", "person", "alice"), self.mark("Reviewed-by", "person", "alice"),
                 self.mark("Reviewed-by", "agent", "alice", "Claude Code, Opus 5, session a1"),
                 self.mark("Reviewed-by", "agent", "bob", "Claude Code, Opus 5, session a1")]
        self.assertEqual(tally(marks)["Reviewed-by"], {"people": 1, "ai": 1, "earlier": 0})

    def test_marks_without_a_version_flag_are_current(self):
        # The batch passes only current marks, without the flag.
        self.assertEqual(tally([{"trailer": "Tested-by", "kind": "person", "by": "alice", "agent": ""}]),
                         {"Tested-by": {"people": 1, "ai": 0, "earlier": 0}})

    def test_the_counts_read_as_words(self):
        self.assertEqual(count_text(3, 2), "3 people and 2 AI agents")
        self.assertEqual(count_text(1, 0), "1 person")
        self.assertEqual(count_text(0, 1), "1 AI agent")
        self.assertEqual(count_text(0, 0), "nobody")


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

    def test_a_person_need_not_say_why_a_declaration_is_right(self):
        record, problem = make_record(self.mark(evidence=""), INDEX, "someone", {"issue": 4}, "now")
        self.assertIsNone(problem)
        self.assertEqual((record["kind"], record["evidence"]), ("person", ""))

    def test_an_ai_review_must_give_its_evidence(self):
        mark = self.mark(kind="agent", agent="Claude Code, Opus 5, session 095781b9", evidence="")
        record, problem = make_record(mark, INDEX, "someone", {"issue": 4}, "now")
        self.assertIsNone(record)
        self.assertIn("evidence", problem)

    def test_an_ai_mark_in_a_comment_must_give_its_evidence_too(self):
        [mark] = comment_marks('<!--reviewed-by:v1 {"agent": "Codex, GPT-6, session c1"}-->\nTested-by: NumberField.Set.HasNaturalDensity')
        record, problem = make_record(mark, INDEX, "someone", {"issue": 1, "comment": 2}, "now")
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
        self.assertEqual((outputs["recorded"], outputs["invalid"], outputs["close"], len(lines)), (1, 1, "false", 1))
        self.assertIn("`TauCeti.Nope` is not a declaration on the page", reply)

    def test_a_comment_without_marks_gets_no_reply(self):
        comment = {"id": 5, "user": {"login": "bob"}, "body": "Which ones should I look at first?"}
        reply, outputs, _ = self.run_event({"issue": {"number": 1, "user": {"login": "alice"}, "body": ""}, "comment": comment})
        self.assertEqual((reply, outputs["recorded"]), ("", 0))


PROBLEM = """### Declaration

TauCeti.IdealArithmeticFunction.vonMangoldt

### Version reported

aaaaaaaaaaaa

### What is wrong

It is wrong: false as stated, or not the intended notion

### Why

It is log N(P) on prime ideals P only; the von Mangoldt function is log N(P) on every power of P (Neukirch VII.1).

### Suggested fix

_No response_

### Who is reporting

I am (a person)

### Agent, model and session (AI reports only)

_No response_
"""


class Reports(unittest.TestCase):
    def report(self, **changes):
        report = form_report(PROBLEM)
        report.update(changes)
        return report

    def test_the_problem_form_gives_one_report(self):
        self.assertEqual(form_report(PROBLEM), {
            "decl": "TauCeti.IdealArithmeticFunction.vonMangoldt", "version": "aaaaaaaaaaaa", "what": "wrong",
            "why": "It is log N(P) on prime ideals P only; the von Mangoldt function is log N(P) on every power of P (Neukirch VII.1).",
            "fix": "", "kind": "person", "agent": ""})

    def test_the_other_kinds_of_problem(self):
        self.assertEqual(form_report(PROBLEM.replace("It is wrong: false as stated, or not the intended notion",
                                                     "Its name or docstring is misleading"))["what"], "misleading")
        self.assertEqual(form_report(PROBLEM.replace("It is wrong: false as stated, or not the intended notion",
                                                     "Something else is off: hypotheses, conventions or generality"))["what"], "other")

    def test_a_report_is_pinned_to_the_version_it_is_about(self):
        record, problem = make_report(self.report(), INDEX, "alice", 12, "2026-09-22T15:00:00Z")
        self.assertIsNone(problem)
        self.assertEqual({k: record[k] for k in ("event", "issue", "decl", "hash", "tauceti", "what", "by", "kind", "at")},
                         {"event": "reported", "issue": 12, "decl": "TauCeti.IdealArithmeticFunction.vonMangoldt", "hash": "aaaaaaaaaaaa",
                          "tauceti": "c0ffee", "what": "wrong", "by": "alice", "kind": "person", "at": "2026-09-22T15:00:00Z"})

    def test_a_report_must_say_why(self):
        record, problem = make_report(self.report(why=""), INDEX, "alice", 12, "now")
        self.assertIsNone(record)
        self.assertIn("why", problem)

    def test_an_ai_report_names_its_agent(self):
        record, problem = make_report(self.report(kind="agent"), INDEX, "alice", 12, "now")
        self.assertIsNone(record)
        self.assertIn("agent", problem)

    def test_a_report_on_an_unknown_declaration_is_refused_with_a_suggestion(self):
        record, problem = make_report(self.report(decl="TauCeti.IdealArithmeticFunction.vonMangold"), INDEX, "alice", 12, "now")
        self.assertIsNone(record)
        self.assertIn("TauCeti.IdealArithmeticFunction.vonMangoldt", problem)


class ReportEvents(unittest.TestCase):
    """A report is its own issue: recorded when it is opened, kept open until the declaration is fixed."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.ledger = Path(self.folder.name) / "records.jsonl"
        self.problems = Path(self.folder.name) / "problems.jsonl"

    def tearDown(self):
        self.folder.cleanup()

    def send(self, action, body=PROBLEM, state_reason=None, sender="alice"):
        issue = {"number": 12, "user": {"login": "alice"}, "body": body, "labels": [{"name": "problem"}], "state_reason": state_reason}
        return from_event({"action": action, "issue": issue, "sender": {"login": sender}}, INDEX, self.ledger, "https://example.org/",
                          "2026-09-22T15:00:00Z")

    def events(self):
        return [json.loads(line) for line in self.problems.read_text().splitlines()] if self.problems.exists() else []

    def test_a_report_is_recorded_and_its_issue_stays_open(self):
        reply, outputs = self.send("opened")
        self.assertEqual((outputs["recorded"], outputs["invalid"], outputs["close"]), (1, 0, "false"))
        self.assertEqual([(e["event"], e["issue"], e["decl"]) for e in self.events()],
                         [("reported", 12, "TauCeti.IdealArithmeticFunction.vonMangoldt")])
        self.assertFalse(self.ledger.exists())
        self.assertIn("stays open", reply)

    def test_an_incomplete_report_is_answered_and_not_recorded(self):
        body = PROBLEM.replace("It is log N(P) on prime ideals P only; the von Mangoldt function is log N(P) on every power of P (Neukirch VII.1).",
                               "_No response_")
        reply, outputs = self.send("opened", body)
        self.assertEqual((outputs["recorded"], outputs["invalid"], outputs["close"]), (0, 1, "false"))
        self.assertEqual(self.events(), [])
        self.assertIn("why", reply)

    def test_an_edit_updates_the_report_once(self):
        self.send("opened")
        edited = PROBLEM.replace("(Neukirch VII.1)", "(Neukirch VII.1, and Iwaniec–Kowalski 1.2)")
        reply, outputs = self.send("edited", edited)
        self.assertEqual(outputs["recorded"], 1)
        self.assertEqual(self.events()[-1]["event"], "updated")
        self.assertIn("Iwaniec", self.events()[-1]["why"])
        reply, outputs = self.send("edited", edited)
        self.assertEqual((reply, outputs["recorded"], len(self.events())), ("", 0, 2))

    def test_closing_the_issue_as_completed_records_the_fix(self):
        self.send("opened")
        reply, outputs = self.send("closed", state_reason="completed", sender="carol")
        self.assertEqual(outputs["recorded"], 1)
        self.assertEqual({k: self.events()[-1][k] for k in ("event", "issue", "resolution", "by")},
                         {"event": "closed", "issue": 12, "resolution": "fixed", "by": "carol"})

    def test_closing_it_as_not_planned_records_that_nothing_was_fixed(self):
        self.send("opened")
        self.send("closed", state_reason="not_planned", sender="carol")
        self.assertEqual(self.events()[-1]["resolution"], "not planned")

    def test_reopening_the_issue_reopens_the_report(self):
        self.send("opened")
        self.send("closed", state_reason="completed")
        reply, outputs = self.send("reopened")
        self.assertEqual((outputs["recorded"], self.events()[-1]["event"]), (1, "reopened"))

    def test_closing_a_report_that_was_never_recorded_changes_nothing(self):
        reply, outputs = self.send("closed", state_reason="not_planned")
        self.assertEqual((reply, outputs["recorded"], self.events()), ("", 0, []))


if __name__ == "__main__":
    unittest.main()
