import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from answerer.docfix import apply_edits, doc_spans  # noqa: E402

LEAN = '''/-!
# A module

Its documentation, with `code` and a /- nested -/ comment.
-/

namespace Foo

-- a line comment with /- in it
/-- **The thing** is `n + n`.

It is never `0` for `n > 0`. -/
def thing (n : Nat) : Nat := n + n

theorem thing_pos (n : Nat) (h : 0 < n) : 0 < thing n := by
  simp [thing]; omega

end Foo
'''


class DocSpansTests(unittest.TestCase):
    def test_the_doc_comments_and_only_them(self):
        bodies = [LEAN[s:e] for s, e in doc_spans(LEAN)]
        self.assertEqual(len(bodies), 2)
        self.assertTrue(bodies[0].startswith("\n# A module") and bodies[0].endswith("comment.\n"))
        self.assertEqual(bodies[1], " **The thing** is `n + n`.\n\nIt is never `0` for `n > 0`. ")


class ApplyEditsTests(unittest.TestCase):
    def test_an_edit_inside_a_docstring(self):
        new, err = apply_edits(LEAN, [{"old": "It is never `0` for `n > 0`.", "new": "It is `0` exactly at `n = 0`."}])
        self.assertIsNone(err)
        self.assertIn("/-- **The thing** is `n + n`.\n\nIt is `0` exactly at `n = 0`. -/\ndef thing", new)

    def refused(self, edits, why):
        new, err = apply_edits(LEAN, edits)
        self.assertIsNone(new)
        self.assertIn(why, err)

    def test_code_is_out_of_reach(self):
        self.refused([{"old": "def thing (n : Nat) : Nat := n + n", "new": "def thing (n : Nat) : Nat := 0"}],
                     "inside a doc comment")
        self.refused([{"old": "for `n > 0`. -/\ndef thing", "new": "for `n > 0`. thing"}],
                     "inside a doc comment")
        self.refused([{"old": "for `n > 0`. -/\ndef thing (n", "new": "for `n > 0`. (n"}],
                     "inside a doc comment")
        self.refused([{"old": "`0` for `n > 0`. -/\ndef thing (n : Nat)", "new": "`0`"}],
                     "inside a doc comment")
        self.refused([{"old": "simp [thing]", "new": "simp"}], "inside a doc comment")

    def test_the_new_text_cannot_end_the_comment(self):
        self.refused([{"old": "is `n + n`.", "new": "is. -/ #eval 1 /-"}], "comment delimiters")
        self.refused([{"old": "is `n + n`.", "new": "is `n + n`, as in \"twice\"."}], "double quote")
        self.refused([{"old": "for `n > 0`.", "new": "for `n > 0`. -/"}], "comment delimiters")

    def test_the_comment_own_delimiters_quoted_at_both_ends_stay(self):
        # A model quotes the closing `-/` (or the opening `/--`) in both texts, as on 2026-10-26: the
        # delimiter stays where it was, so the edit changes only what lies between.
        new, err = apply_edits(LEAN, [{"old": "It is never `0` for `n > 0`. -/",
                                       "new": "It is `0` exactly at `n = 0`. -/"}])
        self.assertIsNone(err)
        self.assertIn("/-- **The thing** is `n + n`.\n\nIt is `0` exactly at `n = 0`. -/\ndef thing", new)
        new, err = apply_edits(LEAN, [{"old": "/-- **The thing** is", "new": "/-- **The doubling** is"}])
        self.assertIsNone(err)
        self.assertIn("/-- **The doubling** is `n + n`.", new)
        self.refused([{"old": "for `n > 0`. -/", "new": "for `n > 0`. -/ #eval 1 /- -/"}], "comment delimiters")
        self.refused([{"old": "-/", "new": "-/"}], "empty")

    def test_lines_stay_short(self):
        self.refused([{"old": "is `n + n`.", "new": "is " + "very " * 25 + "long."}], "100 characters")

    def test_the_old_text_once(self):
        self.refused([{"old": "nothing like this", "new": "x"}], "not found")
        self.refused([{"old": "`n", "new": "x"}], "more than once")
        self.refused([{"old": "", "new": "x"}], "empty")
        self.refused([{"old": "is `n + n`.", "new": "x"}] * 4, "at most 3")


if __name__ == "__main__":
    unittest.main()
