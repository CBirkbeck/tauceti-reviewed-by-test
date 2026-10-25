import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from test_answerer_items import evidence  # noqa: E402

import fixture_site  # noqa: E402
from evidence_core import records as rec  # noqa: E402
from answerer.items import open_items  # noqa: E402
from answerer.model import Outcome  # noqa: E402
from answerer.post import Poster  # noqa: E402
from answerer.run import REPLY_LIMIT, Config, answer  # noqa: E402
from answerer.state import State  # noqa: E402


def verdict(v, reply="Because.", **kw):
    return {"mathematical": v != "not_mathematical", "verdict": v, "summary": f"summary {v}", "reply": reply,
            "edits": [], "pr_title": "", "roadmap": "", **kw}


class FakePRs:
    def __init__(self, state="OPEN"):
        self.proposed, self.st = [], state

    def propose(self, item, decl, v, by):
        self.proposed.append((item.id, v))
        return 501, None

    def state(self, number):
        return (self.st, "c" * 40 if self.st == "MERGED" else None)


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, argv, stdin=None):
        self.calls.append((argv, stdin))
        return "https://github.com/example/fixture-store/issues/90\n"


class RunTests(unittest.TestCase):
    def setUp(self):
        self.ev, self.ds = evidence()
        self.items = open_items(self.ev, "example/fixture-store")  # the no on triple_comm (#14), the suggestion (#15)
        self.state = State(Path(tempfile.mkdtemp()) / "state.json")
        self.gh = Recorder()
        self.poster = Poster("example/fixture-store", self.gh)
        self.prs = FakePRs()
        self.cfg = Config(repo="example/fixture-store", library_repo="TauCetiProject/TauCeti", site="https://example.org/",
                          commit="B", maintainers=("example",), log=lambda s: None)
        self.lib = NS(text=lambda p: None)

    def go(self, outcomes, items=None, **cfg):
        outs = list(outcomes)
        assess = lambda client, cfg_, system, brief, tools: outs.pop(0)  # noqa: E731
        cfg_ = Config(**{**vars(self.cfg), **cfg})
        return answer(items if items is not None else self.items, self.ev, self.ds, self.lib, None, None, self.poster,
                      self.prs, self.state, cfg_, today="2026-10-25", system="S", assess=assess)

    def bodies(self):
        return [(argv[:4], stdin) for argv, stdin in self.gh.calls]

    def test_a_no_intended_and_a_suggestion_answered(self):
        self.go([Outcome(verdict("intended", reply="It is the junk value <!-- agent: tool=X; model=Y --> at 0."), 2.0,
                         "claude-fable-5-1", None, 3),
                 Outcome(verdict("answered", reply="A semiring would do; see `Fixture.triple`."), 1.0, "claude-fable-5-1", None, 2)])
        (a, b) = self.bodies()
        self.assertEqual(a[0], ["gh", "issue", "comment", "14"])
        self.assertEqual(a[1], "<!-- agent: tool=Tau Ceti answerer; model=claude-fable-5-1 -->\n/intended\n\n"
                               "It is the junk value  at 0.")
        self.assertEqual(b[0], ["gh", "issue", "comment", "15"])
        self.assertTrue(b[1].split("\n")[1] == "/answered")
        self.assertAlmostEqual(self.state.spent("2026-10-25"), 3.0)
        self.assertEqual(self.state.items[self.items[0].id]["verdict"], "intended")

    def test_a_long_reply_is_cut_at_a_paragraph(self):
        first = "It is the junk value at 0, which the theorems built on it exclude by assuming `0 < n`."
        long = first + "\n\n" + "\n\n".join(["More evidence, at length. " * 12] * 8)
        self.go([Outcome(verdict("intended", reply=long), 1.0, "m", None, 1), Outcome(verdict("answered"), 1.0, "m", None, 1)])
        body = self.bodies()[0][1].split("/intended\n\n", 1)[1]
        self.assertLessEqual(len(body), REPLY_LIMIT)
        self.assertTrue(body.startswith(first) and body.endswith("\n\n…"))

    def test_handled_items_are_not_answered_again(self):
        self.go([Outcome(verdict("intended"), 1.0, "m", None, 1), Outcome(verdict("answered"), 1.0, "m", None, 1)])
        self.gh.calls.clear()
        self.go([])
        self.assertEqual(self.gh.calls, [])

    def test_nothing_posted_for_what_is_not_mathematics(self):
        self.go([Outcome(verdict("not_mathematical"), 0.5, "m", None, 1), Outcome(verdict("unclear"), 0.5, "m", None, 1)])
        posted = [c for c in self.gh.calls if c[0][:3] == ["gh", "issue", "comment"]]
        self.assertEqual(posted, [])
        # The unclear one is listed for a person; the other is not.
        create = [c for c in self.gh.calls if c[0][:3] == ["gh", "issue", "create"]]
        self.assertEqual(len(create), 1)
        self.assertIn("Fixture.triple", create[0][1])
        self.assertNotIn("triple_comm", create[0][1])

    def test_no_verdict_is_listed_for_a_person(self):
        self.go([Outcome(None, 0.3, "m", "refused", 1), Outcome(verdict("answered"), 0.1, "m", None, 1)])
        create = [c for c in self.gh.calls if c[0][:3] == ["gh", "issue", "create"]]
        self.assertIn("refused", create[0][1])

    def test_a_docstring_fix_waits_for_its_merge(self):
        self.go([Outcome(verdict("docstring_fix", reply="The docstring is wrong."), 2.0, "claude-fable-5-1", None, 4),
                 Outcome(verdict("answered"), 0.5, "m", None, 1)], items=self.items[:1])
        self.assertEqual(self.prs.proposed[0][0], self.items[0].id)
        reply = self.bodies()[0]
        self.assertEqual(reply[0], ["gh", "issue", "comment", "14"])
        self.assertNotIn("/fixed", reply[1])
        self.assertIn("[TauCeti#501](https://github.com/TauCetiProject/TauCeti/pull/501)", reply[1])
        self.gh.calls.clear()
        self.prs.st = "MERGED"
        self.go([], items=self.items[:1])
        fixed = self.bodies()[0]
        self.assertEqual(fixed[1].split("\n")[1], "/fixed " + "c" * 40)
        self.assertIn("The docstring is wrong.", fixed[1])
        self.assertEqual(self.state.items[self.items[0].id]["done"], "fixed")

    def test_work_done_by_hand_closes_under_its_own_name(self):
        # A fix proposed before the answerer existed: its state names who did it.
        item = self.items[0]
        self.state.handled(item.id, {"pr": 21165, "reply": "Transposed indices.", "issue": None, "decl": item.decl,
                                     "kind": "problem", "by": {"tool": "Claude Code", "model": "claude-opus-5-5"}})
        self.prs.st = "MERGED"
        self.go([], items=self.items[:1])
        argv = self.gh.calls[0][0]
        a = dict(zip(argv[2::2], argv[3::2]))
        self.assertEqual((argv[:2], a["--action"], a["--agent"], a["--commit"]),
                         (["evidence-store", "status"], "fixed", "Claude Code, claude-opus-5-5", "c" * 40))

    def test_the_days_budget(self):
        self.state.spend("2026-10-25", 20.0)
        self.go([])
        self.assertEqual([c for c in self.gh.calls if "comment" in c[0]], [])

    def test_at_most_so_many_a_day_from_one_author(self):
        ds = self.ds
        more = [{"schema": rec.SCHEMA, "kind": "review", "verdict": "question", "by": fixture_site.SOMEONE,
                 "subject": rec.subject_from_decl(ds.by_name[n], ds), "text": f"Why {n}?", "at": f"2026-10-23T1{i}:00:00Z",
                 "origin": {"kind": "issue", "ref": f"example/fixture-store#{30 + i}"}}
                for i, n in enumerate(["Fixture.double", "Fixture.one"])]
        ev, _ = evidence(more)
        items = open_items(ev, "example/fixture-store")
        self.assertEqual(len(items), 4)
        self.go([Outcome(verdict("answered" if it.kind == "question" else "intended"), 0.1, "m", None, 1) for it in items],
                items=items, per_author=2, maintainers=())
        self.assertEqual(len(self.state.items), 2)


if __name__ == "__main__":
    unittest.main()
