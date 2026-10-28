import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from evidence_store import cli, github
from evidence_store.forms import FORMS
from evidence_store.intake import BULK_LABEL

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import evidence_intake  # noqa: E402

LABELS = {f["label"] for f in FORMS.values()} | {BULK_LABEL}


def label_of(url: str) -> str:
    return url.split("labels=")[1].split("&")[0]


class OpenIssuesTests(unittest.TestCase):
    def test_the_open_issues_of_the_forms_and_the_bulk_issue(self):
        asked = []
        pr = {"url": "https://api.github.com/repos/o/r/pulls/4"}
        lists = {"evidence:review": [{"number": 9}, {"number": 3}, {"number": 4, "pull_request": pr}],
                 "evidence:test": [{"number": 9}, {"number": 5}],
                 "evidence:bulk": [{"number": 1}]}

        def gh_json(*args):
            asked.append(args[-1])
            return lists.get(label_of(args[-1]), [])

        with mock.patch.object(github, "gh_json", gh_json):
            got = evidence_intake.open_issues("o/r", "2026-10-14T00:00:00Z")
        self.assertEqual([i["number"] for i in got], [1, 3, 5, 9])  # each once, in order, no pull request
        self.assertEqual({label_of(u) for u in asked}, LABELS)
        for u in asked:
            self.assertIn("state=open", u)
            self.assertNotIn("since=", u)


class IntakeTests(unittest.TestCase):
    """evidence-store's own intake, run through the wrapper with GitHub faked: which issues it reads."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        store = self.dir / "evidence"
        (store / "records").mkdir(parents=True)
        shutil.copy(HERE.parent / "evidence" / "store.json", store / "store.json")
        self.event = self.dir / "event.json"
        self.event.write_text(json.dumps({"issue": {"number": 40}}), encoding="utf-8")
        self.read: list[int] = []
        self.listed: list[str] = []

    def run_intake(self, *sweep: str) -> int:
        def gh_json(*args):
            self.listed.append(args[-1])
            open_ = "state=open" in args[-1]
            return {"evidence:review": [{"number": 7}] + ([] if open_ else [{"number": 3}]),
                    "evidence:challenge": [{"number": 25}]}.get(label_of(args[-1]), [])

        def issue(repo, n):
            self.read.append(n)
            return {"number": n, "labels": [], "comments": 0, "closed_at": None, "body": ""}

        with mock.patch.object(github, "gh_json", gh_json), mock.patch.object(github, "issue", issue), \
                mock.patch.object(github, "recent_issues", github.recent_issues):
            return evidence_intake.main(["intake", "--repo", "o/r", "--store", str(self.dir / "evidence"),
                                         "--event", str(self.event), "--event-name", "issues", *sweep,
                                         "--outcome", str(self.dir / "outcome.json")])

    def test_an_event_reads_its_issue_then_the_open_ones(self):
        self.assertEqual(self.run_intake("--sweep-open"), 0)
        self.assertEqual(self.read, [40, 7, 25])
        self.assertTrue(self.listed and all("state=open" in u for u in self.listed))

    def test_the_sweep_by_days_is_evidence_stores_own(self):
        self.assertEqual(self.run_intake("--sweep-days", "14"), 0)
        self.assertEqual(self.read, [40, 3, 7, 25])
        self.assertTrue(self.listed and all("state=all" in u and "since=" in u for u in self.listed))

    def test_the_open_sweep_finishes_an_issue_recorded_before(self):
        from evidence_core import records as rec
        r = rec.with_id({k: v for k, v in FIXTURE["agent-accept"]["record"].items() if k != "id"} |
                        {"origin": {"kind": "issue", "ref": "o/r#7"}})
        (self.dir / "evidence" / "records" / "2026-10.jsonl").write_text(json.dumps(r) + "\n", encoding="utf-8")
        before = github.comments
        with mock.patch.object(github, "events", lambda repo, n: []):
            self.assertEqual(self.run_intake("--sweep-open"), 0)
        out = json.loads((self.dir / "outcome.json").read_text(encoding="utf-8"))
        self.assertEqual(out["replies"], [[7, evidence_intake.recorded(r)]])
        self.assertEqual(out["close"], [[7, "completed"]])
        self.assertIs(github.comments, before)  # put back as it was


FIXTURE = json.loads((HERE / "fixtures" / "intake" / "recorded.json").read_text(encoding="utf-8"))


class RecordedTests(unittest.TestCase):
    def test_the_reply_intake_posted(self):
        for case, f in FIXTURE.items():  # issues 556, 557 and 103, as the bot answered them
            self.assertEqual(evidence_intake.recorded(f["record"]), f["reply"], case)


class FakeStore:
    def __init__(self, by_issue: dict[int, dict]):
        self.by_issue = by_issue

    def from_origin(self, ref: str) -> list[dict]:
        n = int(ref.split("#")[1])
        return [self.by_issue[n]] if n in self.by_issue else []


def bot(text="Recorded"):
    return {"user": {"login": "github-actions[bot]"}, "body": text}


class UnfinishedTests(unittest.TestCase):
    """What an earlier run left undone: a review, test or named result recorded from its issue whose
    reply or close GitHub refused is still open, and intake, which has it, says nothing more."""

    def setUp(self):
        accept, test = FIXTURE["agent-accept"]["record"], FIXTURE["test"]["record"]
        problem = {**accept, "verdict": "problem", "category": "other"}
        self.store = FakeStore({10: accept, 11: test, 12: accept, 13: problem, 15: accept, 16: accept})
        self.comments = {11: [bot()], 16: [bot()]}
        self.events = {12: [{"event": "closed"}, {"event": "reopened"}]}

    def issue(self, n, comments=0, labels=()):
        return {"number": n, "state": "open", "comments": comments, "labels": [{"name": l} for l in labels]}

    def finish(self, swept, outcome):
        evidence_intake.unfinished("o/r", self.store, swept, outcome,
                                   comments_of=lambda n: self.comments.get(n, []),
                                   events_of=lambda n: self.events.get(n, []))
        return outcome

    def test_replies_where_it_had_not_and_closes(self):
        out = self.finish([self.issue(10), self.issue(11, comments=1, labels=["evidence:test", "evidence:needs-fix"])],
                          {"replies": [], "labels": [], "close": []})
        self.assertEqual(out["replies"], [[10, FIXTURE["agent-accept"]["reply"]]])
        self.assertEqual(out["labels"], [[11, [], ["evidence:needs-fix"]]])
        self.assertEqual(out["close"], [[10, "completed"], [11, "completed"]])

    def test_leaves_what_is_meant_to_be_open(self):
        out = self.finish([self.issue(12), self.issue(13), self.issue(14), self.issue(15), self.issue(16, comments=1)],
                          {"replies": [[15, "new"]], "close": [[15, "completed"]]})
        # 12 was closed once and reopened on purpose; 13 is a problem; 14 is not recorded; this run
        # already closes 15; 16, replied to but left open, is closed
        self.assertEqual(out["replies"], [[15, "new"]])
        self.assertEqual(out["close"], [[15, "completed"], [16, "completed"]])


class Runner:
    """`gh` faked: refuses a comment on the issues in `refuse`, and the first `limited` comments with
    GitHub's secondary rate limit."""

    def __init__(self, refuse=(), limited=0):
        self.calls, self.refuse, self.limited = [], set(refuse), limited

    def __call__(self, *args, input=None, check=True):
        self.calls.append(args)
        if args[:2] == ("issue", "comment"):
            if self.limited:
                self.limited -= 1
                raise RuntimeError("gh issue comment 5…: HTTP 403: You have exceeded a secondary rate limit.")
            if int(args[2]) in self.refuse:
                raise RuntimeError("gh issue comment …: HTTP 422")
        return ""

    def did(self, what):
        return [int(a[2]) for a in self.calls if a[:2] == ("issue", what)]


class ApplyTests(unittest.TestCase):
    OUTCOME = {"replies": [[5, "a"], [6, "b"], [7, "c"]], "labels": [[6, [], ["evidence:needs-fix"]]],
               "close": [[5, "completed"], [6, "completed"], [7, "completed"], [8, "completed"]],
               "reopen": [], "reactions": []}

    def apply(self, runner):
        waited = []
        refused = evidence_intake.apply(json.loads(json.dumps(self.OUTCOME)), "o/r", gh=runner, wait=waited.append)
        return refused, waited

    def test_issue_by_issue(self):
        runner = Runner()
        self.assertEqual(self.apply(runner), ([], []))
        self.assertEqual(runner.did("comment"), [5, 6, 7])
        self.assertEqual(runner.did("close"), [5, 6, 7, 8])
        self.assertLess(runner.calls.index(("issue", "close", "5", "-R", "o/r", "--reason", "completed")),
                        next(i for i, a in enumerate(runner.calls) if a[:3] == ("issue", "comment", "6")))

    def test_an_issue_whose_reply_is_refused_stays_open(self):
        runner = Runner(refuse={6})
        refused, _ = self.apply(runner)
        self.assertEqual(refused, [6])
        self.assertEqual(runner.did("close"), [5, 7, 8])
        self.assertNotIn(6, runner.did("edit"))

    def test_waits_out_the_rate_limit_once_then_only_closes(self):
        runner = Runner(limited=1)
        self.assertEqual(self.apply(runner), ([], [60]))  # waited, and the second try went through
        self.assertEqual(runner.did("close"), [5, 6, 7, 8])
        runner = Runner(limited=2)
        refused, waited = self.apply(runner)
        self.assertEqual((refused, waited), ([5, 6, 7], [60]))  # no further replies once refused twice
        self.assertEqual(runner.did("comment"), [5, 5])
        self.assertEqual(runner.did("close"), [8])


if __name__ == "__main__":
    unittest.main()
