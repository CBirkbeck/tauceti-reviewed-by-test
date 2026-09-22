"""The search page of Tau Ceti declarations and their marks (scripts/build_site.py)."""
import json
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_site import data, marks_by_declaration, page, problem_link, problems_by_declaration, review_link, search_index, shards, summary  # noqa: E402

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
    {"decl": "TauCeti.Gone", "hash": "dddddddddddd", "trailer": "Tested-by", "by": "carol", "kind": "person", "agent": "", "evidence": "", "source": {"issue": 6}, "at": "2026-09-19T10:00:00Z"}]
SETTINGS = {"repo": "CBirkbeck/test", "bulk_issue": 1, "tauceti": "c0ffee1234567"}
PROBLEMS = [
    {"schema": "problem/v1", "event": "reported", "issue": 12, "decl": "TauCeti.Y.g", "hash": "cccccccccccc", "tauceti": "c0ffee1234567",
     "what": "wrong", "why": "It should be 3.", "fix": "def g := 3", "by": "alice", "kind": "person", "agent": "", "at": "2026-09-22T15:00:00Z"},
    {"schema": "problem/v1", "event": "reported", "issue": 13, "decl": "TauCeti.X.f", "hash": "000000000000", "tauceti": "0ld",
     "what": "misleading", "why": "The docstring says two.", "fix": "", "by": "bob", "kind": "agent", "agent": "Codex, session c1", "at": "2026-09-20T10:00:00Z"},
    {"schema": "problem/v1", "event": "closed", "issue": 13, "resolution": "fixed", "by": "carol", "at": "2026-09-21T10:00:00Z"}]


class Links(unittest.TestCase):
    def test_review_this_fills_in_the_declaration_and_the_version_shown(self):
        url = urlparse(review_link("CBirkbeck/test", INDEX["declarations"][0]))
        query = parse_qs(url.query)
        self.assertEqual((url.netloc, url.path), ("github.com", "/CBirkbeck/test/issues/new"))
        self.assertEqual(query["template"], ["reviewed-by.yml"])
        self.assertEqual(query["declaration"], ["TauCeti.X.f"])
        self.assertEqual(query["version"], ["aaaaaaaaaaaa"])

    def test_report_a_problem_fills_in_the_declaration_and_the_version_shown(self):
        url = urlparse(problem_link("CBirkbeck/test", INDEX["declarations"][2]))
        query = parse_qs(url.query)
        self.assertEqual((url.netloc, url.path), ("github.com", "/CBirkbeck/test/issues/new"))
        self.assertEqual((query["template"], query["title"]), (["problem.yml"], ["Problem: TauCeti.Y.g"]))
        self.assertEqual((query["declaration"], query["version"]), (["TauCeti.Y.g"], ["cccccccccccc"]))


class Problems(unittest.TestCase):
    def test_a_report_is_open_until_its_issue_is_closed(self):
        status = lambda events: problems_by_declaration(INDEX, events)["TauCeti.Y.g"][0]["status"]
        closed = {"schema": "problem/v1", "event": "closed", "issue": 12, "resolution": "fixed", "by": "carol", "at": "2026-09-23T10:00:00Z"}
        reopened = {"schema": "problem/v1", "event": "reopened", "issue": 12, "by": "alice", "at": "2026-09-24T10:00:00Z"}
        self.assertEqual(status(PROBLEMS[:1]), "open")
        self.assertEqual(status(PROBLEMS[:1] + [closed]), "fixed")
        self.assertEqual(status(PROBLEMS[:1] + [closed, reopened]), "open")

    def test_an_edit_replaces_what_the_report_says(self):
        updated = dict(PROBLEMS[0], event="updated", why="It should be 4.", at="2026-09-22T16:00:00Z")
        [report] = problems_by_declaration(INDEX, PROBLEMS[:1] + [updated])["TauCeti.Y.g"]
        self.assertEqual((report["why"], report["at"], report["issue"]), ("It should be 4.", "2026-09-22T15:00:00Z", 12))

    def test_a_report_on_an_earlier_version_says_so(self):
        found = problems_by_declaration(INDEX, PROBLEMS)
        self.assertTrue(found["TauCeti.Y.g"][0]["current"])
        self.assertEqual((found["TauCeti.X.f"][0]["current"], found["TauCeti.X.f"][0]["status"], found["TauCeti.X.f"][0]["closedBy"]),
                         (False, "fixed", "carol"))

    def test_open_reports_come_first(self):
        again = dict(PROBLEMS[1], issue=14, hash="aaaaaaaaaaaa", at="2026-09-19T10:00:00Z")
        found = problems_by_declaration(INDEX, PROBLEMS + [again])["TauCeti.X.f"]
        self.assertEqual([(p["issue"], p["status"]) for p in found], [(14, "open"), (13, "fixed")])


class Marks(unittest.TestCase):
    def test_marks_on_an_earlier_version_are_stale(self):
        marks = marks_by_declaration(INDEX, RECORDS)["TauCeti.X.f"]
        self.assertEqual([(m["trailer"], m["current"]) for m in marks], [("Reviewed-by", True), ("Tested-by", False)])

    def test_a_mark_of_a_kind_no_longer_used_is_not_shown(self):
        retired = dict(RECORDS[0], trailer="Acked-by", by="dave")
        marks = marks_by_declaration(INDEX, RECORDS + [retired])["TauCeti.X.f"]
        self.assertEqual([m["by"] for m in marks], ["alice", "bob"])

    def test_the_marks_file_lists_only_declarations_with_marks(self):
        out = data(INDEX, RECORDS)
        self.assertEqual(list(out["declarations"]), ["TauCeti.X.f"])
        entry = out["declarations"]["TauCeti.X.f"]
        self.assertEqual(entry["hash"], "aaaaaaaaaaaa")
        self.assertEqual([(m["trailer"], m["current"], m["issue"]) for m in entry["marks"]], [("Reviewed-by", True, 3), ("Tested-by", False, 5)])

    def test_the_marks_file_carries_the_problem_reports_too(self):
        out = data(INDEX, RECORDS, PROBLEMS)
        self.assertEqual(list(out["declarations"]), ["TauCeti.X.f", "TauCeti.Y.g"])
        self.assertEqual(out["declarations"]["TauCeti.Y.g"]["marks"], [])
        self.assertEqual([(p["issue"], p["status"], p["why"]) for p in out["declarations"]["TauCeti.Y.g"]["problems"]],
                         [(12, "open", "It should be 3.")])
        self.assertEqual([p["status"] for p in out["declarations"]["TauCeti.X.f"]["problems"]], ["fixed"])


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

    def test_the_page_counts_open_problems_and_can_filter_them(self):
        html = page(INDEX, RECORDS, SETTINGS, PROBLEMS)
        self.assertIn("1 open problem", html)
        self.assertIn('<option value="problem">', html)

    def test_settings_cannot_close_the_script(self):
        html = page(INDEX, RECORDS, dict(SETTINGS, repo="</script><script>alert(1)</script>"))
        self.assertNotIn("</script><script>alert(1)", html)


if __name__ == "__main__":
    unittest.main()
