"""The page of declarations and their marks (scripts/build_site.py)."""
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_site import marks_by_declaration, page, review_link  # noqa: E402

INDEX = {"tauceti": "c0ffee1234567", "read": "2026-09-21T15:00:00Z",
         "modules": [{"module": "TauCeti.X", "path": "TauCeti/X.lean", "doc": "# X\n\nAbout X.", "url": "u", "declarations": 2}],
         "declarations": [
             {"name": "TauCeti.X.f", "kind": "def", "module": "TauCeti.X", "doc": "The **function** `f`.", "source": "def f := 1", "hash": "aaaaaaaaaaaa", "url": "u1"},
             {"name": "TauCeti.X.f_one", "kind": "theorem", "module": "TauCeti.X", "doc": "", "source": "theorem f_one : f = 1", "hash": "bbbbbbbbbbbb", "url": "u2"}]}
RECORDS = [
    {"decl": "TauCeti.X.f", "hash": "aaaaaaaaaaaa", "trailer": "Reviewed-by", "by": "alice", "kind": "person", "agent": "", "evidence": "Matches Neukirch.", "source": {"issue": 3}, "at": "2026-09-21T15:10:00Z"},
    {"decl": "TauCeti.X.f", "hash": "000000000000", "trailer": "Tested-by", "by": "bob", "kind": "agent", "agent": "Codex, session c1", "evidence": "", "source": {"issue": 5, "comment": 9}, "at": "2026-09-20T10:00:00Z"}]


class Links(unittest.TestCase):
    def test_review_this_fills_in_the_declaration_and_the_version_shown(self):
        url = urlparse(review_link("CBirkbeck/test", INDEX["declarations"][0]))
        query = parse_qs(url.query)
        self.assertEqual((url.netloc, url.path), ("github.com", "/CBirkbeck/test/issues/new"))
        self.assertEqual(query["template"], ["reviewed-by.yml"])
        self.assertEqual(query["declaration"], ["TauCeti.X.f"])
        self.assertEqual(query["version"], ["aaaaaaaaaaaa"])


class Marks(unittest.TestCase):
    def test_marks_on_an_earlier_version_are_stale(self):
        marks = marks_by_declaration(INDEX, RECORDS)["TauCeti.X.f"]
        self.assertEqual([(m["trailer"], m["current"]) for m in marks], [("Reviewed-by", True), ("Tested-by", False)])

    def test_the_page_shows_current_marks_plainly_and_stale_ones_greyed(self):
        html = page(INDEX, RECORDS, {"repo": "CBirkbeck/test", "bulk_issue": 1})
        self.assertIn('class="mark person"', html)
        self.assertIn('class="mark agent stale"', html)
        self.assertIn("earlier version", html)
        self.assertIn("1 of 2 reviewed", html)
        self.assertIn("<strong>function</strong> <code>f</code>", html)
        self.assertEqual(html.count('class="review"'), 2)

    def test_a_declaration_name_cannot_inject_markup(self):
        index = dict(INDEX, declarations=[dict(INDEX["declarations"][0], doc="<script>x</script>")])
        self.assertNotIn("<script>x", page(index, [], {"repo": "CBirkbeck/test", "bulk_issue": 1}))


if __name__ == "__main__":
    unittest.main()
