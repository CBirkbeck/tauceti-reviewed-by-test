import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import voyager  # noqa: E402

from evidence_core.dataset import Dataset  # noqa: E402
from evidence_core.store import Store, default_config  # noqa: E402

MESSAGES = json.loads((HERE / "fixtures" / "voyager" / "messages.json").read_text(encoding="utf-8"))["messages"]
SETTINGS = {"site": "https://leanprover.zulipchat.com", "channel": "Tau Ceti", "topic": "new results",
            "sender": "voyager@example.org"}


class ParseTests(unittest.TestCase):
    def test_the_first_post_under_subject_headings(self):
        got = voyager.parse_post(MESSAGES[0])
        self.assertEqual([a["decl"] for a in got], ["TauCeti.Contour.argumentPrinciple", "TauCeti.Contour.windingNumber"])
        self.assertEqual([a["what"] for a in got], [None, None])
        self.assertEqual(got[0]["about"], "the contour integral of `f'/f` counts zeros minus poles, weighted by winding number.")
        self.assertEqual(got[1]["prs"], [703, 962])
        self.assertEqual(got[1]["about"], "(Hungerbühler–Wasem Def 2.1).")
        self.assertEqual(got[0]["at"], "2026-07-30T10:28:09Z")
        self.assertEqual(got[0]["source"], {"voyager": 613614529, "stream": 610393})

    def test_sections_today_and_the_new_docs_address(self):
        got = voyager.parse_post(MESSAGES[1])
        self.assertEqual([(a["decl"], a["what"]) for a in got], [
            ("TauCeti.exists_isSl2Triple_of_isNilpotent_ad", "result"),
            ("WeierstrassCurve.Affine.finite_selmerGroup₂", "result"),
            ("TauCeti.AlgebraicGeometry.LineBundleClass.picZero", "definition")])
        self.assertEqual(got[0]["about"], "every nonzero ad-nilpotent element is the nilpositive element of an "
                                          "sl₂-triple (Jacobson, *Lie Algebras*, III §11).")
        self.assertEqual(got[0]["name"], "The Jacobson–Morozov theorem")

    def test_in_progress_and_stats_are_not_announcements(self):
        self.assertNotIn("Perron", json.dumps([a["name"] for m in MESSAGES for a in voyager.parse_post(m)]))

    def test_an_announcement_made_twice_is_kept_once(self):
        first = [a for m in MESSAGES[:2] for a in voyager.parse_post(m)]
        merged = voyager.merge(first, voyager.parse_post(MESSAGES[2]))
        self.assertEqual(len(merged), 5)
        self.assertEqual(merged, sorted(merged, key=lambda a: a["at"]))

    def test_pull_requests_leave_the_sentence(self):
        self.assertEqual(voyager.plain("a sentence. (TauCeti#1, TauCeti#2)"), "a sentence.")
        self.assertEqual(voyager.plain("a (Book, §2) sentence (TauCeti#1 and TauCeti#2)"), "a (Book, §2) sentence")


class FetchTests(unittest.TestCase):
    def test_pages_back_until_the_oldest(self):
        pages = [{"result": "success", "found_oldest": False, "messages": MESSAGES[1:]},
                 {"result": "success", "found_oldest": True, "messages": MESSAGES[:1]}]
        seen = []

        def fake(req, timeout):
            seen.append(req.full_url)
            return io.BytesIO(json.dumps(pages[len(seen) - 1]).encode())
        with mock.patch.object(voyager.urllib.request, "urlopen", fake):
            got = voyager.fetch_messages("https://z.example.org", "bot@example.org", "key", "Tau Ceti", "new results",
                                         "bot@example.org")
        self.assertEqual([m["id"] for m in got], [m["id"] for m in MESSAGES])
        self.assertIn("anchor=newest", seen[0])
        self.assertIn(f"anchor={MESSAGES[1]['id']}", seen[1])
        self.assertIn("include_anchor=false", seen[1])

    def test_a_refusal_is_an_error(self):
        with mock.patch.object(voyager.urllib.request, "urlopen",
                               lambda req, timeout: io.BytesIO(b'{"result": "error", "msg": "Invalid API key"}')):
            with self.assertRaisesRegex(RuntimeError, "Invalid API key"):
                voyager.fetch_messages("https://z", "e", "k", "c", "t", "s")


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.ds = Dataset.load(HERE / "fixtures" / "dataset-b")
        self.dir = Path(tempfile.mkdtemp())
        self.store = Store.init(self.dir / "evidence", default_config("example/store", "Fixture", "Fixture"))
        self.announcements = [
            {"decl": "Fixture.triple_pos", "name": "Positivity", "what": None, "about": "x", "prs": [5],
             "source": {"voyager": 101, "stream": 610393}, "at": "2026-10-20T03:30:00Z"},
            {"decl": "Fixture.IsDouble", "name": "Being double", "what": "definition", "about": "y", "prs": [],
             "source": {"voyager": 102, "stream": 610393}, "at": "2026-10-21T03:30:00Z"},
            {"decl": "Fixture.notYet", "name": "Later", "what": "result", "about": "z", "prs": [],
             "source": {"voyager": 103, "stream": 610393}, "at": "2026-10-22T03:30:00Z"},
            {"decl": "Nat", "name": "Not ours", "what": "definition", "about": "w", "prs": [],
             "source": {"voyager": 104, "stream": 610393}, "at": "2026-10-22T03:30:00Z"}]

    def test_announcements_of_the_library_become_named_records(self):
        got = self.store.add(voyager.named_records(self.announcements, self.ds, self.store, SETTINGS))
        self.assertEqual([(r["subject"]["name"], r["what"]) for r in got],
                         [("Fixture.triple_pos", "result"), ("Fixture.IsDouble", "definition")])
        r = got[0]
        self.assertEqual(r["by"], {"kind": "agent", "agent": {"tool": "Voyager"}})
        self.assertEqual(r["origin"], {"kind": "zulip", "ref": "voyager 101"})
        self.assertEqual(r["reference"], {"text": "Voyager, TauCeti#5", "url":
            "https://leanprover.zulipchat.com/#narrow/channel/610393-Tau-Ceti/topic/new.20results/near/101"})
        self.assertEqual(r["subject"]["commit"], "B")

    def test_a_second_run_records_nothing(self):
        self.store.add(voyager.named_records(self.announcements, self.ds, self.store, SETTINGS))
        self.assertEqual(voyager.named_records(self.announcements, self.ds, self.store, SETTINGS), [])


if __name__ == "__main__":
    unittest.main()
