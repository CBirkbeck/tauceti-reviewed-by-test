import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from answerer.leancheck import Sandbox  # noqa: E402
from evidence_core import records as rec  # noqa: E402
from fixer import agent, pick, publish, run  # noqa: E402
from fixer.state import State  # noqa: E402
from fixer.tools import WorkTools  # noqa: E402

REPO = "o/r"
LIB = "TauCetiProject/TauCeti"
PERSON = {"kind": "person", "identity": {"kind": "github", "id": "RemyDegenne"}, "involvement": "unknown"}
AGENT = {"kind": "agent", "identity": {"kind": "github", "id": "CBirkbeck"}, "agent": {"tool": "Codex", "model": "m"}}
FILE = """/-- Doob's maximal inequality. -/
theorem mul_measure_exists_le_lt_le (h : True) : True := trivial

theorem other : True := trivial
"""


def review(n: int, verdict: str = "question", by: dict = PERSON, at: str = "2026-11-07T13:38:27Z",
           module: str = "TauCeti.Foo", **extra) -> dict:
    return rec.with_id({"schema": rec.SCHEMA, "kind": "review", "verdict": verdict, "by": by, "at": at,
                        "subject": {"name": f"{module}.mul_measure_exists_le_lt_le", "module": module, "commit": "a" * 40},
                        "origin": {"kind": "issue", "ref": f"{REPO}#{n}"}, "text": f"Review {n}.", **extra})


def status(target: dict, state: str, at: str, **extra) -> dict:
    return rec.with_id({"schema": rec.SCHEMA, "kind": "status", "target": target["id"], "state": state, "by": AGENT,
                        "at": at, "origin": {"kind": "comment", "ref": "x"}, **extra})


def reply(target: dict, at: str, **extra) -> dict:
    return rec.with_id({"schema": rec.SCHEMA, "kind": "comment", "by": AGENT, "at": at, "text": "Yes.",
                        "links": {"replies_to": target["id"]}, "origin": {"kind": "comment", "ref": "y"}, **extra})


class PickTests(unittest.TestCase):
    def test_peoples_noes_and_suggestions_in_force_from_issues(self):
        a, b = review(1), review(2, "problem", at="2026-11-06T10:00:00Z")
        by_agent, yes = review(3, by=AGENT), review(4, "accept")
        gone, old = review(5), review(6)
        from_file = rec.with_id({**{k: v for k, v in review(7).items() if k != "id"}, "origin": {"kind": "migration", "ref": "m"}})
        newer = rec.with_id({**{k: v for k, v in review(8).items() if k != "id"}, "links": {"supersedes": old["id"]}})
        records = [a, b, by_agent, yes, gone, old, from_file, newer, status(gone, "withdrawn", "2026-11-07T14:00:00Z"),
                   reply(a, "2026-11-07T14:04:55Z"), status(a, "answered", "2026-11-07T14:05:00Z")]
        found = pick.reviews(records, REPO)
        self.assertEqual([v.id for v in found], [b["id"], a["id"], newer["id"]])
        self.assertEqual([t["kind"] for t in found[1].thread], ["comment", "status"])
        self.assertEqual((found[1].issue, found[1].author, found[1].decl), (1, "RemyDegenne", "TauCeti.Foo.mul_measure_exists_le_lt_le"))

    def test_the_new_ones_not_taken_nor_linked(self):
        a, b, c = review(1), review(2, at="2026-11-01T00:00:00Z"), review(3)
        d = review(4)
        records = [a, b, c, d, reply(d, "2026-11-07T15:00:00Z", pr=f"{LIB}#9")]
        found = pick.reviews(records, REPO)
        got = pick.choose(found, {c["id"]: {}}, "2026-11-06T00:00:00Z", 5)
        self.assertEqual([v.id for v in got], [a["id"]])  # b is too old, c taken, d linked
        self.assertEqual([v.id for v in pick.choose(found, {}, "2026-11-08", 5, only=[b["id"]])], [b["id"]])

    def test_not_what_the_answerer_is_fixing(self):
        a, b, c = review(1), review(2), review(3)
        found = pick.reviews([a, b, c], REPO)
        state = Path(tempfile.mkdtemp()) / "state.json"
        state.write_text(json.dumps({"items": {a["id"]: {"pr": 501}, b["id"]: {"pr": 502, "done": "fixed"},
                                               c["id"]: {"outside": True, "upstream": {"repo": "x/y", "pr": 1}}}}))
        busy = pick.answerer_busy(state)
        self.assertEqual(busy, {a["id"], c["id"]})  # a docstring fix waiting, a fix upstream followed; not one done
        self.assertEqual([v.id for v in pick.choose(found, {}, "2026-11-01", None, busy=busy)], [b["id"]])
        self.assertEqual(pick.answerer_busy(Path(tempfile.mkdtemp()) / "none.json"), set())

    def test_outside_the_library(self):
        self.assertTrue(pick.Review("x", "problem", review(1, module="Mathlib.Order.Basic"), 1).outside("TauCeti"))
        self.assertFalse(pick.Review("x", "problem", review(1), 1).outside("TauCeti"))


def sh(*argv, cwd):
    subprocess.run(list(argv), cwd=cwd, check=True, capture_output=True)


class Checkout(unittest.TestCase):
    """A checkout of a small library, with a Mathlib beside it, as the fixer's has them."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        self.work = self.dir / "TauCeti"
        (self.work / "TauCeti").mkdir(parents=True)
        (self.work / "TauCeti" / "Foo.lean").write_text(FILE, encoding="utf-8")
        (self.work / "TauCeti" / "Bar.lean").write_text("public import TauCeti.Foo\n\ntheorem bar : True := trivial\n",
                                                        encoding="utf-8")
        (self.work / ".gitignore").write_text(".lake\n", encoding="utf-8")
        for args in (["git", "init", "-q"], ["git", "config", "user.name", "t"], ["git", "config", "user.email", "t@t"],
                     ["git", "add", "-A"], ["git", "commit", "-qm", "base"]):
            sh(*args, cwd=self.work)  # its own identity: CI's runners have none
        self.base = subprocess.run(["git", "-C", str(self.work), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        ml = self.work / ".lake" / "packages" / "mathlib"
        (ml / "Mathlib" / "Order").mkdir(parents=True)
        (ml / "Mathlib" / "Order" / "Basic.lean").write_text("theorem le_rfl' : True := trivial\n", encoding="utf-8")
        for args in (["git", "init", "-q"], ["git", "add", "-A"],
                     ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "m"]):
            sh(*args, cwd=ml)
        (self.dir / "secret").write_text("key", encoding="utf-8")
        self.calls: list = []

        def runner(argv, timeout):
            self.calls.append(argv)
            return self.build_result
        self.build_result = (0, "Build completed successfully.")
        sandbox = Sandbox(toolchain=self.dir / "tc", roots=[self.work], lean_path="", home=self.dir / "home",
                          scratch=self.dir / "scratch", runner=runner)
        self.tools = WorkTools(self.work, sandbox, runner=runner)


class ToolsTests(Checkout):
    def test_paths_stay_inside(self):
        (self.work / "TauCeti" / "link.lean").symlink_to(self.dir / "secret")
        for path in ["../secret", "TauCeti/../../secret", "/etc/passwd", "TauCeti/link.lean", "Mathlib/../../x",
                     ".lake/packages/mathlib/Mathlib/Order/Basic.lean", "TauCeti/.git/config", "secret", ""]:
            out, err = self.tools.run("read_file", {"path": path, "start_line": 1, "end_line": 0})
            self.assertTrue(err, path)
            self.assertNotIn("key", out.split(":")[-1] if path == "TauCeti/link.lean" else "")
        out, err = self.tools.run("read_file", {"path": "Mathlib/Order/Basic.lean", "start_line": 1, "end_line": 0})
        self.assertFalse(err)
        self.assertIn("1: theorem le_rfl'", out)

    def test_only_the_librarys_lean_files_change(self):
        for path in ["Mathlib/Order/Basic.lean", "TauCeti/notes.md", "lakefile.toml", ".github/workflows/x.yml"]:
            out, err = self.tools.run("write_file", {"path": path, "content": "x"})
            self.assertTrue(err, path)
        out, err = self.tools.run("edit_file", {"path": "TauCeti/Foo.lean", "old": "trivial", "new": "x"})
        self.assertTrue(err)
        self.assertIn("occurs 2 times", out)
        out, err = self.tools.run("edit_file", {"path": "TauCeti/Foo.lean", "old": "(h : True) : True", "new": ": True"})
        self.assertFalse(err, out)
        self.assertIn("2: theorem mul_measure_exists_le_lt_le : True := trivial", out)
        self.assertTrue(self.tools.run("write_file", {"path": "TauCeti/Foo.lean", "content": "x"})[1])  # exists
        self.assertFalse(self.tools.run("write_file", {"path": "TauCeti/New/Baz.lean", "content": "theorem baz : True := trivial"})[1])
        self.assertFalse(self.tools.run("write_file", {"path": "TauCeti/New/Baz.lean", "content": "theorem baz' : True := trivial"})[1])

    def test_search_importers_and_diff(self):
        out, err = self.tools.run("search", {"pattern": "mul_measure", "scope": "TauCeti", "within": "", "fixed": True})
        self.assertEqual(out, "TauCeti/Foo.lean:2:theorem mul_measure_exists_le_lt_le (h : True) : True := trivial")
        out, err = self.tools.run("search", {"pattern": "le_rfl", "scope": "Mathlib", "within": "Order", "fixed": False})
        self.assertIn("Mathlib/Order/Basic.lean:1:", out)
        self.assertTrue(self.tools.run("search", {"pattern": "x", "scope": "TauCeti", "within": "../..", "fixed": True})[1])
        self.assertEqual(self.tools.run("importers", {"module": "TauCeti.Foo"})[0], "TauCeti/Bar.lean")
        self.tools.run("write_file", {"path": "TauCeti/Baz.lean", "content": "import TauCeti.Foo\n"})
        self.assertEqual(self.tools.run("importers", {"module": "TauCeti.Foo"})[0].split(), ["TauCeti/Bar.lean", "TauCeti/Baz.lean"])
        self.tools.run("edit_file", {"path": "TauCeti/Foo.lean", "old": "(h : True) : True", "new": ": True"})
        out, _ = self.tools.run("show_diff", {})
        self.assertIn("-theorem mul_measure_exists_le_lt_le (h : True)", out)
        self.assertIn("--- new file TauCeti/Baz.lean", out)

    def test_builds_are_sealed_off(self):
        out, err = self.tools.run("lean_build", {"modules": ["TauCeti.Foo", "TauCeti.Bar"]})
        self.assertFalse(err, out)
        argv = self.calls[-1]
        self.assertEqual(argv[:2], ["bwrap", "--unshare-all"])
        self.assertIn("--clearenv", argv)
        self.assertEqual(argv[-3:], ["build", "TauCeti.Foo", "TauCeti.Bar"])
        # the checkout read only, but for the sources and the build's outputs: not .git, not .lake/packages
        w = str(self.work.resolve())
        self.assertIn(["--ro-bind", w, w], [argv[i:i + 3] for i in range(len(argv))])
        writable = [argv[i + 1] for i in range(len(argv)) if argv[i] == "--bind"]
        self.assertEqual(writable, [f"{w}/TauCeti", f"{w}/.lake/build"])
        overlaid = [argv[i + 1] for i in range(len(argv)) if argv[i] == "--tmp-overlay"]
        self.assertEqual(overlaid, [f"{w}/.lake/packages"])  # written to a throwaway layer only
        self.assertIn(["--setenv", "LAKE_ARTIFACT_CACHE", "true"], [argv[i:i + 3] for i in range(len(argv))])
        self.assertTrue(self.tools.run("lean_build", {"modules": ["Mathlib.Order.Basic"]})[1])
        self.assertTrue(self.tools.run("lean_build", {"modules": ["TauCeti.Missing"]})[1])
        self.build_result = (1, "error: TauCeti/Foo.lean:2:0: unknown identifier")
        out, err = self.tools.run("lean_build", {"modules": ["TauCeti.Foo"]})
        self.assertTrue(err)
        self.assertIn("unknown identifier", out)

    def test_lean_check_refuses_what_runs_code(self):
        out, err = self.tools.run("lean_check", {"imports": ["TauCeti.Foo"], "code": "#eval IO.println 1"})
        self.assertTrue(err)
        self.assertIn("refused", out)


class GateTests(Checkout):
    def test_a_change_that_builds(self):
        self.tools.run("edit_file", {"path": "TauCeti/Foo.lean", "old": "(h : True) : True", "new": ": True"})
        g = publish.gate(self.work, self.tools)
        self.assertTrue(g.ok, g.why)
        self.assertEqual((g.files, g.modules), (["TauCeti/Foo.lean"], ["TauCeti.Bar", "TauCeti.Foo"]))
        self.assertEqual(self.calls[-1][-3:], ["build", "TauCeti.Bar", "TauCeti.Foo"])

    def test_refused(self):
        self.assertEqual(publish.gate(self.work, self.tools).why, "there are no changes")
        (self.work / "lakefile.toml").write_text("x", encoding="utf-8")
        self.assertIn("files outside TauCeti/", publish.gate(self.work, self.tools).why)
        (self.work / "lakefile.toml").unlink()
        for bad in ["  sorry", "set_option maxHeartbeats 0 in", "/-- a \"word\" -/", "#eval 1", "local macro x : term => y"]:
            self.tools.run("write_file", {"path": "TauCeti/Bad.lean", "content": f"theorem t : True := by\n{bad}\n"})
            self.assertIn("refuses or which could run code", publish.gate(self.work, self.tools).why, bad)
        (self.work / "TauCeti" / "Bad.lean").unlink()
        (self.work / "TauCeti" / "Link.lean").symlink_to(self.dir / "secret")
        self.assertIn("not plain files: TauCeti/Link.lean", publish.gate(self.work, self.tools).why)
        (self.work / "TauCeti" / "Link.lean").unlink()
        self.tools.run("edit_file", {"path": "TauCeti/Foo.lean", "old": "(h : True) : True", "new": ": True"})
        self.build_result = (1, "error: oops")
        g = publish.gate(self.work, self.tools)
        self.assertFalse(g.ok)
        self.assertIn("the build failed", g.why)


class PublisherTests(Checkout):
    def publisher(self, dry):
        self.posted, self.created = [], []
        return publish.Publisher(self.work, LIB, REPO, "https://site/", lambda: {"Probability"},
                                 gh=lambda argv, stdin: self.created.append((argv, stdin)) or "https://github.com/x/pull/77\n",
                                 comment=lambda n, text: self.posted.append((n, text)), dry=dry)

    def test_a_dry_run_keeps_its_branch_and_posts_nothing(self):
        r = review(1239)
        rv = pick.Review(r["id"], "question", r, 1239)
        self.tools.run("edit_file", {"path": "TauCeti/Foo.lean", "old": "(h : True) : True", "new": ": True"})
        g = publish.gate(self.work, self.tools)
        result = {"pr_title": "feat: state it under second countability", "pr_body": "Drops a hypothesis.",
                  "roadmap": "Probability", "reply": "It now assumes `SecondCountableTopology`."}
        p = self.publisher(dry=True)
        number, branch = p.open(rv, result, "claude-opus-5-5", g)
        self.assertEqual(number, -1)
        self.assertTrue(branch.startswith(f"fixer/{r['id']}-"))
        msg = subprocess.run(["git", "-C", str(self.work), "log", "-1", "--format=%B"], capture_output=True, text=True).stdout
        self.assertTrue(msg.startswith("feat: state it under second countability\n\nAddresses the review https://github.com/o/r/issues/1239"))
        self.assertIn("Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>", msg)
        said = p.link(rv, f"{LIB}#N", result, {"tool": "Tau Ceti fixer", "model": "claude-opus-5-5"})
        self.assertEqual(said.split("\n")[:2], ["<!-- agent: tool=Tau Ceti fixer; model=claude-opus-5-5 -->",
                                                f"/addressed {LIB}#N — feat: state it under second countability"])
        self.assertEqual((self.posted, self.created), ([], []))

    def test_a_real_run_pushes_opens_and_names_it(self):
        remote = self.dir / "remote.git"
        sh("git", "init", "-q", "--bare", str(remote), cwd=self.dir)
        sh("git", "remote", "add", "origin", str(remote), cwd=self.work)
        r = review(1239)
        rv = pick.Review(r["id"], "question", r, 1239)
        self.tools.run("edit_file", {"path": "TauCeti/Foo.lean", "old": "(h : True) : True", "new": ": True"})
        g = publish.gate(self.work, self.tools)
        p = self.publisher(dry=False)
        number, branch = p.open(rv, {"pr_title": "generalise it", "pr_body": "Body.", "roadmap": "Nowhere", "reply": "R."},
                                "claude-opus-5-5", g)
        self.assertEqual(number, 77)
        argv, text = self.created[0]
        self.assertEqual(argv[:5], ["gh", "pr", "create", "--repo", LIB])
        self.assertIn("fix: generalise it", argv)
        self.assertIn("\n\nRoadmap: none\n\n🤖 Proposed by the Tau Ceti review fixer (claude-opus-5-5)", text)
        self.assertIn("`TauCeti.Bar`, `TauCeti.Foo` build sealed off", text)
        self.assertIn(branch, subprocess.run(["git", "-C", str(remote), "branch"], capture_output=True, text=True).stdout)


class FakeStream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.msg


class FakeClient:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []
        self.beta = NS(messages=NS(stream=self.stream))

    def stream(self, **kw):
        self.calls.append(json.loads(json.dumps(kw, default=str)))
        return FakeStream(self.replies.pop(0))


def msg(stop, content, cost_tokens=1000):
    return NS(stop_reason=stop, content=content, model="claude-opus-5-5",
              usage=NS(input_tokens=cost_tokens, output_tokens=cost_tokens, cache_read_input_tokens=0,
                       cache_creation_input_tokens=0))


RESULT = {"outcome": "pr", "summary": "s", "reply": "r", "pr_title": "feat: x", "pr_body": "b", "roadmap": "none",
          "existing_pr": ""}


class AgentTests(unittest.TestCase):
    cfg = NS(model="claude-opus-5-5", effort="high", max_tokens=64000, max_turns=6, item_budget=10.0)

    def test_tools_then_the_result(self):
        use = NS(type="tool_use", id="t1", name="read_file", input={"path": "TauCeti/Foo.lean", "start_line": 1, "end_line": 0})
        client = FakeClient([msg("tool_use", [use]), msg("end_turn", [NS(type="text", text=json.dumps(RESULT))])])
        tools = NS(run=lambda name, inp: (f"ran {name}", False))
        out = agent.work(client, self.cfg, "system", "brief", tools)
        self.assertEqual((out.result, out.turns, out.model, out.error), (RESULT, 2, "claude-opus-5-5", None))
        first = client.calls[0]
        self.assertEqual((first["model"], first["output_config"]["effort"], first["fallbacks"]),
                         ("claude-opus-5-5", "high", "default"))
        self.assertNotIn("thinking", first)
        self.assertNotIn("tool_choice", first)
        self.assertEqual(client.calls[1]["messages"][-1]["content"][0]["content"], "ran read_file")
        self.assertAlmostEqual(out.cost, 2 * (1000 * 4 + 1000 * 20) / 1e6)

    def test_near_the_budget_it_is_told_and_past_it_asked_for_the_result(self):
        use = NS(type="tool_use", id="t", name="show_diff", input={})
        client = FakeClient([msg("tool_use", [use], 200_000), msg("tool_use", [use], 200_000),
                             msg("end_turn", [NS(type="text", text=json.dumps(RESULT))])])
        out = agent.work(client, NS(**{**vars(self.cfg), "item_budget": 6.0}), "s", "b", NS(run=lambda n, i: ("ok", False)))
        self.assertEqual(out.result, RESULT)
        texts = lambda call: [b.get("text") for b in call["messages"][-1]["content"] if isinstance(b, dict) and b.get("type") == "text"]  # noqa: E731
        self.assertIn(agent.NEARLY, texts(client.calls[1]))  # $4.80 spent of $6
        self.assertIn(agent.FINAL, texts(client.calls[2]))  # $9.60 spent
        self.assertEqual(client.calls[2]["tool_choice"], {"type": "none"})

    def test_a_refusal_or_no_result(self):
        self.assertEqual(agent.work(FakeClient([msg("refusal", [])]), self.cfg, "s", "b", None).error, "refused")
        bad = FakeClient([msg("end_turn", [NS(type="text", text="I fixed it.")])])
        self.assertEqual(agent.work(bad, self.cfg, "s", "b", None).error, "the last answer was not the result")


class FixTests(Checkout):
    def setUp(self):
        super().setUp()
        self.state = State(self.dir / "state.json")
        self.cfg = run.Config(review_repo=REPO, library_repo=LIB, site="https://site/", commit=self.base, log=lambda s: None)
        self.posted = []
        self.pub = publish.Publisher(self.work, LIB, REPO, "https://site/", lambda: set(),
                                     gh=lambda argv, stdin: "", comment=lambda n, t: self.posted.append((n, t)), dry=True)

    def fix(self, result, module="TauCeti.Foo", edit=True, error=None):
        r = review(1239, module=module)
        rv = pick.Review(r["id"], "question", r, 1239)

        def work_fn(client, cfg, system, brief_text, tools, log=None):
            self.brief = brief_text
            if edit:
                tools.run("edit_file", {"path": "TauCeti/Foo.lean", "old": "(h : True) : True", "new": ": True"})
            return agent.Result(result, 3.5, "claude-opus-5-5", error, 9)
        return run.fix(rv, None, self.tools, self.pub, self.state, self.cfg, "system", "2026-11-07", {"Probability"},
                       gh=lambda argv: json.dumps({"state": "OPEN", "mergeCommit": None, "closedAt": None}), work_fn=work_fn)

    def clean(self):
        return subprocess.run(["git", "-C", str(self.work), "status", "--porcelain"], capture_output=True, text=True).stdout

    def test_a_change_is_drafted_in_a_dry_run(self):
        e = self.fix({**RESULT, "roadmap": "Probability"})
        self.assertEqual((e["outcome"], e["cost"], e["turns"]), ("pr", 3.5, 9))
        self.assertTrue(e["draft"].startswith("fixer/"))
        self.assertIn("/addressed TauCetiProject/TauCeti#N — feat: x", e["would_reply"])
        self.assertIn(e["draft"].split("/")[1].split("-")[0], self.state.drafts)
        self.assertEqual(self.state.spent("2026-11-07"), 3.5)
        self.assertEqual(self.clean(), "")  # the checkout is reset
        self.assertIn("<untrusted-", self.brief)
        self.assertIn("It is in TauCeti/Foo.lean, from line 2.", self.brief)
        self.assertIn("# Roadmap areas\nProbability", self.brief)

    def test_mathlibs_declaration_is_never_a_pull_request(self):
        e = self.fix({**RESULT, "reply": "Mathlib should drop it."}, module="Mathlib.Order.Basic")
        self.assertEqual(e["outcome"], "mathlib")
        self.assertNotIn("draft", e)
        self.assertIn("a person proposes the change upstream", e["flag"])
        self.assertIn("left for a person to propose there", e["would_reply"])
        self.assertEqual(self.state.drafts, {})

    def test_the_gate_refusing_and_giving_up_are_listed_for_a_person(self):
        self.build_result = (1, "error: nope")
        e = self.fix(RESULT)
        self.assertIn("its change was not published: the build failed", e["flag"])
        e = self.fix({**RESULT, "outcome": "gave_up", "summary": "too hard"}, edit=False)
        self.assertEqual(e["flag"], "it gave up: too hard")
        e = self.fix(None, edit=False, error="refused")
        self.assertEqual((e["outcome"], e["flag"]), ("error", "no result: refused"))

    def test_an_existing_pull_request_is_confirmed_before_it_is_named(self):
        e = self.fix({**RESULT, "outcome": "already_addressed", "existing_pr": f"{LIB}#31833"}, edit=False)
        self.assertEqual(e["pr"], f"{LIB}#31833")
        e = self.fix({**RESULT, "outcome": "already_addressed", "existing_pr": "evil/repo#1"}, edit=False)
        self.assertIn("which GitHub does not confirm", e["flag"])


if __name__ == "__main__":
    unittest.main()
