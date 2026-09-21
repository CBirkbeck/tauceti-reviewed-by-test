"""Batching marks into the code periodically (scripts/batch.py)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from batch import commit_message, docstrings  # noqa: E402

INDEX = {"tauceti": "c0ffee1234567", "declarations": [
    {"name": "TauCeti.X.f", "kind": "def", "module": "TauCeti.X", "path": "TauCeti/X.lean", "line": 7, "doc": "The function `f`.",
     "source": "def f : ℕ := 1", "hash": "aaaaaaaaaaaa"},
    {"name": "TauCeti.X.g", "kind": "def", "module": "TauCeti.X", "path": "TauCeti/X.lean", "line": 9, "doc": "", "source": "def g : ℕ := 2", "hash": "cccccccccccc"}]}
ALICE = {"decl": "TauCeti.X.f", "hash": "aaaaaaaaaaaa", "trailer": "Reviewed-by", "by": "alice", "kind": "person", "agent": "", "evidence": "", "at": "2026-09-21T15:10:00Z"}
BOT = {"decl": "TauCeti.X.f", "hash": "aaaaaaaaaaaa", "trailer": "Tested-by", "by": "bob", "kind": "agent", "agent": "Codex, session c1", "evidence": "", "at": "2026-09-21T16:00:00Z"}
OLD = {"decl": "TauCeti.X.g", "hash": "000000000000", "trailer": "Reviewed-by", "by": "alice", "kind": "person", "agent": "", "evidence": "", "at": "2026-09-01T10:00:00Z"}


class Batch(unittest.TestCase):
    def test_the_commit_message_ends_in_one_trailer_per_mark(self):
        message = commit_message([ALICE, BOT], INDEX)
        self.assertTrue(message.startswith("Record 2 review marks"))
        self.assertEqual(message.strip().splitlines()[-2:], [
            "Reviewed-by: @alice <TauCeti.X.f@aaaaaaaaaaaa>",
            "Tested-by: Codex, session c1 (AI) via @bob <TauCeti.X.f@aaaaaaaaaaaa>"])

    def test_docstrings_carry_the_current_marks_as_trailer_lines(self):
        text = docstrings(INDEX, [ALICE, BOT, OLD])
        self.assertIn("/-- The function `f`.\n\nReviewed-by: @alice, 2026-09-21\nTested-by: Codex, session c1 (AI) via @bob, 2026-09-21 -/\ndef f : ℕ := 1", text)
        # A mark on an earlier version is not carried into the source.
        self.assertNotIn("def g", text)


if __name__ == "__main__":
    unittest.main()
