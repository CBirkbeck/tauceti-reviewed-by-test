"""Writing the review lines into Tau Ceti's own sources (scripts/apply.py)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from apply import apply_to_checkout, commit_message  # noqa: E402

SITE = "https://example.org/reviews/"
SOURCE = '''/-
Copyright (c) 2026 Tau Ceti. All rights reserved.
-/
import Mathlib.Tactic

/-!
# Ideal arithmetic functions

Functions on the nonzero ideals of a number field.
-/

namespace TauCeti

/-- The **ideal von Mangoldt function**. -/
noncomputable def vonMangoldt : ℕ → ℂ := fun _ ↦ 0

/-- It vanishes at the unit ideal. -/
@[simp]
theorem vonMangoldt_one : vonMangoldt 1 = 0 := by simp

def noDocstring : ℕ := 3

end TauCeti
'''
REVIEWS = {"declarations": {
    "TauCeti.vonMangoldt": {"tally": {"Reviewed-by": {"people": 2, "ai": 1, "earlier": 0}},
                            "tests": {"tally": {"unit": 1, "results": 3, "suggested": 0}}},
    "TauCeti.noDocstring": {"tally": {"Reviewed-by": {"people": 1, "ai": 0, "earlier": 0}}, "tests": {"tally": {"unit": 0, "results": 0, "suggested": 0}}},
    "TauCeti.vonMangoldt_one": {"tally": {"Reviewed-by": {"people": 0, "ai": 1, "earlier": 0}}, "tests": {"tally": {"unit": 2, "results": 0, "suggested": 0}}}}}


class Apply(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.path = self.root / "TauCeti" / "NumberTheory" / "VonMangoldt.lean"
        self.path.parent.mkdir(parents=True)
        self.path.write_text(SOURCE, encoding="utf-8")

    def tearDown(self):
        self.folder.cleanup()

    def run_apply(self, reviews=None):
        return apply_to_checkout(self.root, reviews if reviews is not None else REVIEWS, SITE), self.path.read_text(encoding="utf-8")

    def test_a_file_gets_one_link_after_the_title_of_its_module_docstring(self):
        _, text = self.run_apply()
        self.assertIn("/-!\n# Ideal arithmetic functions\n\n"
                      "[Reviews and tests of this file](https://example.org/reviews/#m=TauCeti.NumberTheory.VonMangoldt)\n\n"
                      "Functions on the nonzero ideals of a number field.\n-/", text)

    def test_a_reviewed_declaration_gets_its_counts_at_the_end_of_its_docstring(self):
        _, text = self.run_apply()
        self.assertIn("/-- The **ideal von Mangoldt function**.\n\n"
                      "Reviewed-by: 2 people and 1 AI agent\n"
                      "Tested by: 1 unit test and 3 key results -/\n"
                      "noncomputable def vonMangoldt", text)

    def test_a_declaration_with_no_marks_is_left_alone(self):
        _, text = self.run_apply({"declarations": {}})
        self.assertIn("/-- It vanishes at the unit ideal. -/\n@[simp]\ntheorem vonMangoldt_one", text)
        self.assertIn("\ndef noDocstring : ℕ := 3\n", text)

    def test_a_reviewed_declaration_with_no_docstring_gets_one_holding_its_review(self):
        _, text = self.run_apply()
        self.assertIn("/-- Reviewed-by: 1 person -/\ndef noDocstring : ℕ := 3", text)

    def test_the_new_lines_go_above_the_attributes_the_docstring_would(self):
        _, text = self.run_apply()
        self.assertIn("/-- It vanishes at the unit ideal.\n\n"
                      "Reviewed-by: 1 AI agent\n"
                      "Tested by: 2 unit tests -/\n@[simp]\ntheorem vonMangoldt_one", text)

    def test_running_it_again_changes_nothing(self):
        first, text = self.run_apply()
        again, twice = self.run_apply()
        self.assertEqual(text, twice)
        self.assertEqual((first["files"], again["files"]), (1, 0))

    def test_the_lines_follow_the_marks_when_they_change(self):
        self.run_apply()
        fewer = {"declarations": {"TauCeti.vonMangoldt": {"tally": {"Reviewed-by": {"people": 1, "ai": 0, "earlier": 0}},
                                                          "tests": {"tally": {"unit": 0, "results": 0, "suggested": 0}}}}}
        summary, text = self.run_apply(fewer)
        self.assertIn("/-- The **ideal von Mangoldt function**.\n\nReviewed-by: 1 person -/", text)
        self.assertNotIn("Tested by:", text)
        self.assertEqual(summary["declarations"], 1)

    def test_nothing_it_writes_passes_the_line_limit_but_a_link(self):
        _, text = self.run_apply()
        self.assertEqual([line for line in text.splitlines() if len(line) > 100 and "http" not in line], [])


class Message(unittest.TestCase):
    def test_the_commit_ends_in_one_trailer_per_mark(self):
        reviews = {"declarations": {"TauCeti.vonMangoldt": {"hash": "aaaaaaaaaaaa", "marks": [
            {"trailer": "Reviewed-by", "by": "alice", "kind": "person", "agent": "", "hash": "aaaaaaaaaaaa", "current": True},
            {"trailer": "Reviewed-by", "by": "bob", "kind": "agent", "agent": "Codex, session c1", "hash": "aaaaaaaaaaaa", "current": True},
            {"trailer": "Reviewed-by", "by": "carol", "kind": "person", "agent": "", "hash": "000000000000", "current": False}]}}}
        message = commit_message(reviews, SITE)
        self.assertTrue(message.startswith("Review lines: 2 marks on 1 declaration"))
        self.assertEqual(message.strip().splitlines()[-2:], [
            "Reviewed-by: @alice <TauCeti.vonMangoldt@aaaaaaaaaaaa>",
            "Reviewed-by: Codex, session c1 (AI) via @bob <TauCeti.vonMangoldt@aaaaaaaaaaaa>"])


if __name__ == "__main__":
    unittest.main()
