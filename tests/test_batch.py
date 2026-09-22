"""Batching marks into the code periodically (scripts/batch.py)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from batch import commit_message, docstrings, headers, table  # noqa: E402

INDEX = {"tauceti": "c0ffee1234567",
         "modules": [{"module": "TauCeti.X", "path": "TauCeti/X.lean", "doc": "# The function f\n\nIt is one, and this is the rest.", "url": "u"},
                     {"module": "TauCeti.Y", "path": "TauCeti/Y.lean", "doc": "", "url": "v"}],
         "declarations": [
    {"name": "TauCeti.X.f", "kind": "def", "module": "TauCeti.X", "path": "TauCeti/X.lean", "line": 7, "doc": "The function `f`.",
     "source": "def f : ℕ := 1", "hash": "aaaaaaaaaaaa"},
    {"name": "TauCeti.X.g", "kind": "def", "module": "TauCeti.X", "path": "TauCeti/X.lean", "line": 9, "doc": "", "source": "def g : ℕ := 2", "hash": "cccccccccccc"}]}
ALICE = {"decl": "TauCeti.X.f", "hash": "aaaaaaaaaaaa", "trailer": "Reviewed-by", "by": "alice", "kind": "person", "agent": "", "evidence": "", "at": "2026-09-21T15:10:00Z"}
BOT = {"decl": "TauCeti.X.f", "hash": "aaaaaaaaaaaa", "trailer": "Reviewed-by", "by": "bob", "kind": "agent", "agent": "Codex, session c1", "evidence": "", "at": "2026-09-21T16:00:00Z"}
SITE = "https://example.org/reviews/"
OLD = {"decl": "TauCeti.X.g", "hash": "000000000000", "trailer": "Reviewed-by", "by": "alice", "kind": "person", "agent": "", "evidence": "", "at": "2026-09-01T10:00:00Z"}


class Batch(unittest.TestCase):
    def test_the_commit_message_ends_in_one_trailer_per_mark(self):
        message = commit_message([ALICE, BOT], INDEX)
        self.assertTrue(message.startswith("Record 2 review marks"))
        self.assertEqual(message.strip().splitlines()[-2:], [
            "Reviewed-by: @alice <TauCeti.X.f@aaaaaaaaaaaa>",
            "Reviewed-by: Codex, session c1 (AI) via @bob <TauCeti.X.f@aaaaaaaaaaaa>"])

    def test_docstrings_count_the_current_marks_and_tests_and_link_to_them(self):
        tested = dict(INDEX, examples=[{"statement": "example : f = 1", "sorry": False, "tests": ["TauCeti.X.f"], "path": "p", "line": 1, "url": "u"}])
        text = docstrings(tested, [ALICE, BOT, OLD], SITE, [])
        self.assertIn("/-- The function `f`.\n\n"
                      "Reviewed-by: 1 person and 1 AI agent\n"
                      "Tested by: 1 unit test\n"
                      "[Reviews and tests](https://example.org/reviews/#d=TauCeti.X.f) -/\ndef f : ℕ := 1", text)
        # A mark on an earlier version is not carried into the source.
        self.assertNotIn("def g", text)

    def test_many_marks_still_take_one_line_each(self):
        many = [dict(ALICE, by=f"person{n}") for n in range(12)] + [dict(BOT, agent=f"Agent {n}") for n in range(5)]
        text = docstrings(INDEX, many, SITE, [])
        self.assertIn("Reviewed-by: 12 people and 5 AI agents\n[Reviews and tests](https://example.org/reviews/#d=TauCeti.X.f) -/", text)
        self.assertEqual(text.count("Reviewed-by:"), 1)

    def test_only_the_link_may_pass_the_line_limit(self):
        # Mathlib's longLine linter, which Tau Ceti runs with warnings as errors, allows 100
        # characters on every line except one with a URL.
        name = "TauCeti.NumberTheory.SomeLongNamespace.AnotherLongPart.aVeryLongDeclarationNameIndeed"
        index = {"tauceti": "c0ffee1234567", "declarations": [dict(INDEX["declarations"][0], name=name)]}
        many = [dict(ALICE, decl=name, by=f"person{n}") for n in range(1234)] + [dict(BOT, decl=name, agent=f"Agent {n}") for n in range(567)]
        text = docstrings(index, many, "https://cbirkbeck.github.io/tauceti-reviewed-by-test/", [])
        self.assertTrue(any(len(line) > 100 for line in text.splitlines()))
        self.assertEqual([line for line in text.splitlines() if len(line) > 100 and "http" not in line], [])

    def test_a_file_gets_one_link_at_the_top_of_its_module_docstring(self):
        text = headers(INDEX, [ALICE], SITE)
        self.assertIn("-- TauCeti/X.lean\n/-!\n# The function f\n\n"
                      "[Reviews and tests of this file](https://example.org/reviews/#m=TauCeti.X)\n\n"
                      "It is one, and this is the rest.\n-/", text)
        # Only the files with something to show, and nothing over the line limit but the link.
        self.assertNotIn("TauCeti/Y.lean", text)
        self.assertEqual([line for line in text.splitlines() if len(line) > 100 and "http" not in line], [])

    def test_a_file_without_a_module_docstring_gets_one(self):
        index = dict(INDEX, modules=[dict(INDEX["modules"][0], doc="")])
        self.assertIn("-- TauCeti/X.lean\n/-!\n# TauCeti.X\n\n"
                      "[Reviews and tests of this file](https://example.org/reviews/#m=TauCeti.X)\n-/", headers(index, [ALICE], SITE))

    def test_the_table_counts_each_mark(self):
        text = table(INDEX, [ALICE, BOT, OLD], SITE, [])
        self.assertIn("| [`TauCeti.X.f`](https://example.org/reviews/#d=TauCeti.X.f) | 1 person and 1 AI agent | — |", text)
        self.assertNotIn("TauCeti.X.g", text)


if __name__ == "__main__":
    unittest.main()
