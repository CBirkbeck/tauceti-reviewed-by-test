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


if __name__ == "__main__":
    unittest.main()
