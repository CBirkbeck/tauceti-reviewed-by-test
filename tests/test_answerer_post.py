import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from answerer.post import Poster, mark  # noqa: E402
from answerer.state import State  # noqa: E402

BY = {"tool": "Tau Ceti answerer", "model": "claude-fable-5-1"}


class Calls:
    def __init__(self, out="https://github.com/o/r/issues/9\n"):
        self.calls, self.out = [], out

    def __call__(self, argv, stdin=None):
        self.calls.append((argv, stdin))
        return self.out


class PosterTests(unittest.TestCase):
    def poster(self, dry=False):
        self.run = Calls()
        return Poster("o/r", self.run, dry=dry)

    def test_on_its_own_issue_the_command_comes_first(self):
        p = self.poster()
        p.close(NS(id="abc", issue=14), "intended", "It is intended.", BY)
        argv, body = self.run.calls[0]
        self.assertEqual(argv[:4], ["gh", "issue", "comment", "14"])
        self.assertEqual(body, f"{mark(BY)}\n/intended\n\nIt is intended.")
        p.close(NS(id="abc", issue=14), "fixed", "Fixed.", BY, commit="0123456789abcdef")
        self.assertTrue(self.run.calls[1][1].startswith(f"{mark(BY)}\n/fixed 0123456789abcdef\n\nFixed."))

    def test_without_an_issue_the_status_form(self):
        p = self.poster()
        p.close(NS(id="abc", issue=None), "invalid", "Not a problem here.", BY)
        argv, _ = self.run.calls[0]
        self.assertEqual(argv[:2], ["evidence-store", "status"])
        a = dict(zip(argv[2::2], argv[3::2]))
        self.assertEqual((a["--repo"], a["--record"], a["--action"], a["--note"], a["--agent"]),
                         ("o/r", "abc", "invalid", "Not a problem here.", "Tau Ceti answerer, claude-fable-5-1"))

    def test_a_reply_alone_only_on_an_issue(self):
        p = self.poster()
        self.assertIsNotNone(p.reply(NS(id="a", issue=3), "Confirmed.", BY))
        self.assertEqual(self.run.calls[0][1], f"{mark(BY)}\nConfirmed.")
        self.assertIsNone(p.reply(NS(id="a", issue=None), "Confirmed.", BY))
        self.assertEqual(len(self.run.calls), 1)

    def test_a_dry_run_posts_nothing(self):
        p = self.poster(dry=True)
        p.close(NS(id="abc", issue=14), "intended", "x", BY)
        p.reply(NS(id="abc", issue=14), "x", BY)
        self.assertEqual(self.run.calls, [])
        self.assertEqual(len(p.would), 2)

    def test_the_list_for_a_person(self):
        p = self.poster()
        self.run.out = "https://github.com/o/r/issues/42\n"
        n = p.flags(["- a", "- b"], None)
        self.assertEqual(n, 42)
        self.assertEqual(self.run.calls[0][0][:3], ["gh", "issue", "create"])
        p.flags(["- a"], 42)
        self.assertEqual(self.run.calls[1][0][:4], ["gh", "issue", "edit", "42"])
        self.assertIn("- a", self.run.calls[1][1])
        self.assertEqual(self.run.calls[2][0], ["gh", "api", "-X", "PATCH", "repos/o/r/issues/42", "-f", "state=open"])
        # With nothing left for a person, it says so and closes.
        p.flags([], 42)
        self.assertIn("Nothing now.", self.run.calls[3][1])
        self.assertEqual(self.run.calls[4][0][-1], "state=closed")


class StateTests(unittest.TestCase):
    def test_kept_between_runs(self):
        path = Path(tempfile.mkdtemp()) / "state.json"
        s = State(path)
        s.handled("abc", {"verdict": "intended"})
        s.spend("2026-10-25", 1.25)
        s.spend("2026-10-25", 0.5)
        s.save()
        t = State(path)
        self.assertEqual(t.items["abc"]["verdict"], "intended")
        self.assertAlmostEqual(t.spent("2026-10-25"), 1.75)
        self.assertEqual(t.spent("2026-10-26"), 0.0)

    def test_one_run_at_a_time(self):
        path = Path(tempfile.mkdtemp()) / "state.json"
        with State.locked(path):
            with self.assertRaises(BlockingIOError):
                with State.locked(path):
                    pass


if __name__ == "__main__":
    unittest.main()
