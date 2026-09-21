"""The search page of Tau Ceti declarations and their marks (scripts/build_site.py)."""
import json
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_site import data, marks_by_declaration, page, review_link, search_index, shards, summary  # noqa: E402

INDEX = {"tauceti": "c0ffee1234567", "read": "2026-09-21T15:00:00Z",
         "modules": [{"module": "TauCeti.NumberTheory.X", "path": "TauCeti/NumberTheory/X.lean", "doc": "# X\n\nAbout X.", "url": "u", "declarations": 2},
                     {"module": "TauCeti.Algebra.Y", "path": "TauCeti/Algebra/Y.lean", "doc": "", "url": "v", "declarations": 1}],
         "declarations": [
             {"name": "TauCeti.X.f", "kind": "def", "keyword": "abbrev", "module": "TauCeti.NumberTheory.X", "path": "TauCeti/NumberTheory/X.lean",
              "line": 3, "end": 4, "doc": "The **function** `f`. It is one.", "source": "abbrev f := 1", "hash": "aaaaaaaaaaaa", "url": "u1"},
             {"name": "TauCeti.X.f_one", "kind": "theorem", "keyword": "lemma", "module": "TauCeti.NumberTheory.X", "path": "TauCeti/NumberTheory/X.lean",
              "line": 6, "end": 6, "doc": "", "source": "lemma f_one : f = 1", "hash": "bbbbbbbbbbbb", "url": "u2"},
             {"name": "TauCeti.Y.g", "kind": "def", "keyword": "def", "module": "TauCeti.Algebra.Y", "path": "TauCeti/Algebra/Y.lean",
              "line": 1, "end": 1, "doc": "A map.", "source": "def g := 2", "hash": "cccccccccccc", "url": "u3"}]}
RECORDS = [
    {"decl": "TauCeti.X.f", "hash": "aaaaaaaaaaaa", "trailer": "Reviewed-by", "by": "alice", "kind": "person", "agent": "", "evidence": "Matches Neukirch.", "source": {"issue": 3}, "at": "2026-09-21T15:10:00Z"},
    {"decl": "TauCeti.X.f", "hash": "000000000000", "trailer": "Tested-by", "by": "bob", "kind": "agent", "agent": "Codex, session c1", "evidence": "", "source": {"issue": 5, "comment": 9}, "at": "2026-09-20T10:00:00Z"},
    {"decl": "TauCeti.Gone", "hash": "dddddddddddd", "trailer": "Acked-by", "by": "carol", "kind": "person", "agent": "", "evidence": "", "source": {"issue": 6}, "at": "2026-09-19T10:00:00Z"}]
SETTINGS = {"repo": "CBirkbeck/test", "bulk_issue": 1, "tauceti": "c0ffee1234567"}


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

    def test_the_marks_file_lists_only_declarations_with_marks(self):
        out = data(INDEX, RECORDS)
        self.assertEqual(list(out["declarations"]), ["TauCeti.X.f"])
        entry = out["declarations"]["TauCeti.X.f"]
        self.assertEqual(entry["hash"], "aaaaaaaaaaaa")
        self.assertEqual([(m["trailer"], m["current"], m["issue"]) for m in entry["marks"]], [("Reviewed-by", True, 3), ("Tested-by", False, 5)])


class Search(unittest.TestCase):
    def test_every_declaration_is_a_row_of_the_search_index(self):
        found = search_index(INDEX)
        self.assertEqual(found["modules"], ["TauCeti.NumberTheory.X", "TauCeti.Algebra.Y"])
        keywords = found["keywords"]
        self.assertEqual([(row[0], keywords[row[1]], found["modules"][row[2]], row[3]) for row in found["rows"]],
                         [("TauCeti.X.f", "abbrev", "TauCeti.NumberTheory.X", 3), ("TauCeti.X.f_one", "lemma", "TauCeti.NumberTheory.X", 6),
                          ("TauCeti.Y.g", "def", "TauCeti.Algebra.Y", 1)])

    def test_a_summary_is_the_first_sentence_of_the_docstring_in_plain_text(self):
        self.assertEqual(summary("The **function** `f`. It is one."), "The function f.")
        self.assertEqual(summary(""), "")
        self.assertTrue(len(summary("word " * 100)) <= 121)

    def test_each_module_has_a_file_with_its_declarations_in_full(self):
        found = shards(INDEX)
        self.assertEqual(sorted(found), [0, 1])
        self.assertEqual([d["name"] for d in found[0]["declarations"]], ["TauCeti.X.f", "TauCeti.X.f_one"])
        self.assertEqual(found[0]["declarations"][0]["source"], "abbrev f := 1")
        self.assertEqual(found[0]["summary"], "About X.")


class Page(unittest.TestCase):
    def test_the_page_carries_its_settings_and_counts(self):
        html = page(INDEX, RECORDS, SETTINGS)
        self.assertIn('"repo": "CBirkbeck/test"', html)
        self.assertIn("3 declarations", html)
        self.assertIn("c0ffee1", html)
        self.assertIn('id="search"', html)

    def test_settings_cannot_close_the_script(self):
        html = page(INDEX, RECORDS, dict(SETTINGS, repo="</script><script>alert(1)</script>"))
        self.assertNotIn("</script><script>alert(1)", html)


if __name__ == "__main__":
    unittest.main()
