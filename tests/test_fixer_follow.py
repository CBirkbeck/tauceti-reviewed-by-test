import json
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from fixer import agent, follow, pick, run  # noqa: E402
from fixer.state import State  # noqa: E402
from test_fixer import LIB, REPO, Checkout, review, sh  # noqa: E402

HEAD = "a" * 40
META = {"head_sha": HEAD, "states": {"correctness": "green", "documentation": "blocking_request"}}
OURS = "<!-- agent: tool=Tau Ceti fixer; model=claude-opus-5-5 -->"


def gql(state="OPEN", merged=False, title="refactor: weaken it", mergeable="MERGEABLE", head=HEAD, threads=(), comments=()):
    return {"data": {"repository": {"pullRequest": {
        "state": state, "merged": merged, "closedAt": None, "title": title, "body": "Body.\n\nRoadmap: none\n",
        "headRefName": "fixer/x-1", "headRefOid": head, "mergeable": mergeable,
        "commits": {"nodes": [{"commit": {"committedDate": "2026-11-07T15:47:00Z"}}]},
        "reviewThreads": {"nodes": list(threads)}, "comments": {"nodes": list(comments)}}}}}


def thread(i, body, commit=HEAD, resolved=False, replies=()):
    cs = [{"databaseId": i, "author": {"login": "roed-math"}, "body": body, "createdAt": "2026-11-07T18:00:00Z",
           "originalCommit": {"oid": commit}}] + list(replies)
    return {"isResolved": resolved, "isOutdated": False, "path": "TauCeti/Foo.lean", "line": 2, "comments": {"nodes": cs}}


def comment(i, body, login="roed-math", at="2026-11-07T18:00:00Z"):
    return {"databaseId": i, "author": {"login": login}, "body": body, "createdAt": at}


SCOREBOARD = comment(1, "<!--tauceti-scoreboard-->\n## AI review — changes requested\n\n<!--tauceti-meta:v1 "
                     + json.dumps(META) + "-->")
FINDING = thread(10, "<!--tauceti-rubric:documentation-->\n### 🟡 documentation — request_changes\n\n- Foo.lean:2 — say more.")


def snap(**kw):
    checks, statuses = kw.pop("checks", []), kw.pop("statuses", [])
    rest = lambda path: {"statuses": statuses} if path.endswith("/status") else {"check_runs": checks}  # noqa: E731
    return follow.read(lambda q, v: gql(**kw), rest, LIB, 32075)


class ReadTests(unittest.TestCase):
    def test_a_pull_request_as_the_round_reads_it(self):
        s = snap(threads=[FINDING, thread(11, "Why not ℕ?")], comments=[SCOREBOARD, comment(2, "Merged.", "tauceti-queue[bot]")],
                 checks=[{"name": "build", "conclusion": "success", "details_url": "u"}])
        self.assertEqual((s.state, s.head, s.branch, s.mergeable), ("OPEN", HEAD, "fixer/x-1", "MERGEABLE"))
        self.assertEqual(s.scoreboard["head"], HEAD)
        self.assertEqual(s.scoreboard["states"]["documentation"], "blocking_request")
        self.assertEqual([(t["id"], t["rubric"]) for t in s.threads], [("10", "documentation"), ("11", "")])
        self.assertEqual(snap(state="CLOSED", title="[Merged by Bors] - refactor: weaken it").state, "MERGED")


class NeedsTests(unittest.TestCase):
    def test_the_first_that_applies(self):
        failing = [{"name": "build", "conclusion": "failure", "details_url": "https://x/actions/runs/1/job/2"},
                   {"name": "reconcile", "conclusion": "failure", "details_url": ""}]
        self.assertEqual(follow.needs(snap(mergeable="CONFLICTING", checks=failing), set()).kind, "conflict")
        w = follow.needs(snap(checks=failing, threads=[FINDING], comments=[SCOREBOARD]), set())
        self.assertEqual((w.kind, [c["name"] for c in w.failed]), ("ci", ["build"]))
        w = follow.needs(snap(threads=[FINDING], comments=[SCOREBOARD]), set())
        self.assertEqual((w.kind, w.key, [t["id"] for t in w.threads]), ("review", "review:1", ["10"]))
        self.assertIsNone(follow.needs(snap(threads=[FINDING], comments=[SCOREBOARD]), {"review:1"}))
        # Tau Ceti's build is a commit status
        status = [{"context": "build", "state": "failure", "target_url": "https://github.com/x/y/actions/runs/9"}]
        w = follow.needs(snap(statuses=status, threads=[FINDING], comments=[SCOREBOARD]), set())
        self.assertEqual((w.kind, w.failed[0]["name"], w.failed[0]["conclusion"]), ("ci", "build", "failure"))
        self.assertIsNone(follow.needs(snap(state="MERGED", threads=[FINDING], comments=[SCOREBOARD]), set()))

    def test_review_findings_of_this_head_not_answered(self):
        old = thread(10, FINDING["comments"]["nodes"][0]["body"], commit="b" * 40)
        self.assertIsNone(follow.needs(snap(threads=[old], comments=[SCOREBOARD]), set()))
        answered = thread(10, FINDING["comments"]["nodes"][0]["body"],
                          replies=[comment(12, OURS + "\nIt is right: see line 2.", "CBirkbeck")])
        self.assertIsNone(follow.needs(snap(threads=[answered], comments=[SCOREBOARD]), set()))
        stale = comment(1, SCOREBOARD["body"].replace(HEAD, "c" * 40))
        self.assertIsNone(follow.needs(snap(threads=[FINDING], comments=[stale]), set()))

    def test_peoples_comments_since_the_head(self):
        later = comment(5, "Please also handle ℤ.", "CBirkbeck", at="2026-11-07T19:00:00Z")
        before = comment(4, "First look.", "someone", at="2026-11-07T10:00:00Z")
        mine = comment(6, OURS + "\nDone.", "CBirkbeck", at="2026-11-07T19:30:00Z")
        bot = comment(7, "Labels.", "github-actions[bot]", at="2026-11-07T19:40:00Z")
        w = follow.needs(snap(comments=[before, later, mine, bot]), set())
        self.assertEqual((w.kind, [c["id"] for c in w.comments], w.key), ("comments", [5], "comments:5"))


class Fakes:
    def github(self):
        self.calls = []
        return follow.GitHub(graphql=None, rest=None, rest_text=lambda path: "2026-11-07T18:00:00.000Z error: bad\n",
                             gh=lambda argv, stdin: self.calls.append((argv, stdin)) or "")


class RoundCase(Checkout, Fakes):
    def setUp(self):
        super().setUp()
        self.remote = self.dir / "remote.git"
        sh("git", "init", "-q", "--bare", str(self.remote), cwd=self.dir)
        sh("git", "remote", "add", "origin", str(self.remote), cwd=self.work)
        sh("git", "push", "-q", "origin", "HEAD:refs/heads/main", cwd=self.work)
        # the pull request: one commit on main, on its branch
        (self.work / "TauCeti" / "Foo.lean").write_text(
            (self.work / "TauCeti" / "Foo.lean").read_text().replace("(h : True) : True", ": True"))
        sh("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "refactor: weaken it", cwd=self.work)
        sh("git", "push", "-q", "origin", "HEAD:refs/heads/fixer/x-1", cwd=self.work)
        self.pr_head = self.rev("HEAD")
        sh("git", "checkout", "-q", "--detach", self.base, cwd=self.work)
        sh("git", "config", "user.name", "fixer", cwd=self.work)
        sh("git", "config", "user.email", "f@f", cwd=self.work)
        self.state = State(self.dir / "state.json")
        self.cfg = run.Config(review_repo=REPO, library_repo=LIB, site="https://site/", commit=self.base,
                              log=lambda s: None)

    def rev(self, ref, repo=None):
        return subprocess.run(["git", "-C", str(repo or self.work), "rev-parse", ref], capture_output=True,
                              text=True).stdout.strip()

    def snapshot(self, **kw):
        s = snap(head=self.pr_head, **kw)
        s.threads = [{**t, "commit": self.pr_head} for t in s.threads]
        if s.scoreboard:
            s.scoreboard["head"] = self.pr_head
        return s

    def round(self, s, w, result, edit=None):
        def work_fn(client, cfg, system, brief_text, tools, log=None, schema=None, outcomes=None):
            self.brief, self.schema = brief_text, schema
            if edit:
                edit(tools)
            return agent.Result(result, 2.0, "claude-opus-5-5", None, 7)
        return follow.round_(s, w, {}, None, None, self.tools, self.github(), self.state, self.cfg, "system",
                             "2026-11-07", {"Probability", "StochasticCalculus"}, work_fn=work_fn)


RESULT = {"outcome": "updated", "summary": "s", "commit_message": "docs: say more\n\nAnswers the documentation finding.",
          "replies": [], "roadmap": "", "close_reason": ""}


class RoundTests(RoundCase):
    def test_findings_fixed_and_pushed_onto_the_branch(self):
        s = self.snapshot(threads=[FINDING], comments=[SCOREBOARD])
        w = follow.needs(s, set())
        edit = lambda tools: tools.run("edit_file", {"path": "TauCeti/Foo.lean", "old": "/-- Doob's maximal inequality. -/",  # noqa: E731
                                                     "new": "/-- Doob's maximal inequality, for every time set. -/"})
        out = self.round(s, w, {**RESULT, "replies": [{"thread": "10", "text": "Also see line 2."},
                                                      {"thread": "99", "text": "unknown thread"}],
                                "roadmap": "StochasticCalculus"}, edit)
        self.assertEqual(out["outcome"], "updated")
        self.assertEqual(self.rev("refs/heads/fixer/x-1", self.remote), out["pushed"])
        parent = subprocess.run(["git", "-C", str(self.remote), "rev-parse", "fixer/x-1~1"], capture_output=True, text=True).stdout.strip()
        self.assertEqual(parent, self.pr_head)  # on top of the branch: no force
        msg = subprocess.run(["git", "-C", str(self.remote), "log", "-1", "--format=%B", "fixer/x-1"], capture_output=True, text=True).stdout
        self.assertTrue(msg.startswith("docs: say more\n\nAnswers the documentation finding."))
        self.assertIn("Co-Authored-By: Claude Opus 5.5", msg)
        replies = [c for c in self.calls if "replies" in " ".join(c[0])]
        self.assertEqual(len(replies), 1)  # the unknown thread is not answered
        self.assertIn("repos/TauCetiProject/TauCeti/pulls/32075/comments/10/replies", replies[0][0])
        self.assertTrue(replies[0][1].startswith(OURS))
        edits = [c for c in self.calls if c[0][:3] == ["gh", "pr", "edit"]]
        self.assertIn("Roadmap: StochasticCalculus", edits[0][1])
        self.assertIn("thread 10 (documentation at TauCeti/Foo.lean:2)", self.brief)
        self.assertIn("<untrusted-", self.brief)
        self.assertEqual(self.schema, follow.FOLLOW)
        self.assertEqual(self.state.spent("2026-11-07"), 2.0)
        self.assertEqual(self.state.prepared.get("work"), "")
        self.assertEqual(self.rev("HEAD"), self.base)  # the checkout back where it was

    def test_contested_pushes_nothing(self):
        s = self.snapshot(threads=[FINDING], comments=[SCOREBOARD])
        out = self.round(s, follow.needs(s, set()), {**RESULT, "outcome": "contested",
                                                     "replies": [{"thread": "10", "text": "Line 2 already says so."}]})
        self.assertNotIn("pushed", out)
        self.assertEqual(self.rev("refs/heads/fixer/x-1", self.remote), self.pr_head)
        self.assertEqual(len([c for c in self.calls if "replies" in " ".join(c[0])]), 1)

    def test_the_gate_still_decides(self):
        s = self.snapshot(threads=[FINDING], comments=[SCOREBOARD])
        edit = lambda tools: tools.run("edit_file", {"path": "TauCeti/Foo.lean", "old": "theorem other : True := trivial",  # noqa: E731
                                                     "new": "theorem other : True := by sorry"})
        out = self.round(s, follow.needs(s, set()), RESULT, edit)
        self.assertIn("was not pushed", out["flag"])
        self.assertEqual(self.rev("refs/heads/fixer/x-1", self.remote), self.pr_head)

    def test_a_conflict_is_resolved_on_main_and_the_branch_replaced(self):
        # main moves under the pull request, changing the same line
        sh("git", "checkout", "-q", "--detach", self.base, cwd=self.work)
        (self.work / "TauCeti" / "Foo.lean").write_text(
            (self.work / "TauCeti" / "Foo.lean").read_text().replace("(h : True) : True", "(h : 1 = 1) : True"))
        sh("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "main moves", cwd=self.work)
        sh("git", "push", "-q", "origin", "HEAD:refs/heads/main", cwd=self.work)
        main = self.rev("HEAD")
        s = self.snapshot(mergeable="CONFLICTING")
        w = follow.needs(s, set())

        def resolve(tools):
            text = (self.work / "TauCeti" / "Foo.lean").read_text()
            self.assertRegex(text, r"(?m)^<<<<<<< ")
            self.seen_conflict = True
            fixed = "/-- Doob's maximal inequality. -/\ntheorem mul_measure_exists_le_lt_le : True := trivial\n\n" \
                    "theorem other : True := trivial\n"
            (self.work / "TauCeti" / "Foo.lean").write_text(fixed)
        out = self.round(s, w, {**RESULT, "commit_message": "fix: resolve the conflict with main"}, resolve)
        self.assertTrue(self.seen_conflict)
        self.assertEqual(out["outcome"], "updated")
        branch = self.rev("refs/heads/fixer/x-1", self.remote)
        self.assertEqual(subprocess.run(["git", "-C", str(self.remote), "rev-parse", "fixer/x-1~1"], capture_output=True,
                                        text=True).stdout.strip(), main)  # one commit on main
        msg = subprocess.run(["git", "-C", str(self.remote), "log", "-1", "--format=%B", branch], capture_output=True, text=True).stdout
        self.assertTrue(msg.startswith("refactor: weaken it\n\nfix: resolve the conflict with main"))
        self.assertIn("conflict markers", self.brief)

    def test_markers_left_are_refused(self):
        sh("git", "checkout", "-q", "--detach", self.base, cwd=self.work)
        (self.work / "TauCeti" / "Foo.lean").write_text(
            (self.work / "TauCeti" / "Foo.lean").read_text().replace("(h : True) : True", "(h : 1 = 1) : True"))
        sh("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "main moves", cwd=self.work)
        sh("git", "push", "-q", "origin", "HEAD:refs/heads/main", cwd=self.work)
        s = self.snapshot(mergeable="CONFLICTING")
        out = self.round(s, follow.needs(s, set()), RESULT)
        self.assertIn("was not pushed", out["flag"])
        self.assertEqual(self.rev("refs/heads/fixer/x-1", self.remote), self.pr_head)


class FollowAllTests(RoundCase):
    def test_merged_closed_and_the_rounds_cap(self):
        st = self.state
        st.items = {"a": {"outcome": "pr", "pr": f"{LIB}#1", "at": "1"}, "b": {"outcome": "pr", "pr": f"{LIB}#2", "at": "2"},
                    "c": {"outcome": "already_addressed", "pr": f"{LIB}#3", "at": "3"},
                    "d": {"outcome": "pr", "pr": f"{LIB}#4", "at": "4", "follow": {"rounds": follow.MAX_ROUNDS, "seen": []}}}
        snaps = {1: gql(state="CLOSED", title="[Merged by Bors] - x"), 2: gql(state="CLOSED"),
                 4: gql(threads=[FINDING], comments=[SCOREBOARD])}
        asked = []
        gh = follow.GitHub(graphql=lambda q, v: asked.append(v["n"]) or snaps[v["n"]],
                           rest=lambda path: {}, rest_text=lambda p: "", gh=lambda a, s: "")
        done = follow.follow_all(st, {}, None, self.tools, gh, self.cfg, "system", "2026-11-07", set(),
                                 work_fn=lambda *a, **k: self.fail("no round"))
        self.assertEqual(asked, [1, 2, 4])  # not #3: it only named that one
        self.assertEqual((st.items["a"]["follow"]["done"], st.items["b"]["follow"]["done"]), ("merged", "closed"))
        self.assertIn("closed without merging", st.items["b"]["flag"])
        self.assertEqual(st.items["d"]["follow"]["done"], "stopped")
        self.assertIn("a person takes over", st.items["d"]["flag"])
        self.assertEqual(done, [])

    def test_a_round_is_remembered(self):
        self.state.items = {"a": {"outcome": "pr", "pr": f"{LIB}#32075", "at": "1"}}
        s = self.snapshot(threads=[FINDING], comments=[SCOREBOARD])
        gh = follow.GitHub(graphql=None, rest=None, rest_text=lambda p: "", gh=lambda a, i: "")
        original = follow.read
        follow.read = lambda *a: s
        try:
            done = follow.follow_all(self.state, {}, None, self.tools, gh, self.cfg, "system", "2026-11-07", set(),
                                     work_fn=lambda *a, **k: agent.Result({**RESULT, "outcome": "nothing"}, 1.0, "m", None, 2))
            again = follow.follow_all(self.state, {}, None, self.tools, gh, self.cfg, "system", "2026-11-07", set(),
                                      work_fn=lambda *a, **k: self.fail("worked twice"))
        finally:
            follow.read = original
        f = self.state.items["a"]["follow"]
        self.assertEqual((f["rounds"], f["seen"], done[0]["outcome"], again), (1, ["review:1"], "nothing", []))


class CiTests(unittest.TestCase):
    def test_the_errors_of_a_failing_job(self):
        log = "\n".join(["2026-11-07T18:00:00.1234567Z ok"] * 100 +
                        ["2026-11-07T18:00:01.0000000Z error: TauCeti/Foo.lean:3:0: line too long"])
        out = follow.ci_errors(lambda path: log if path.endswith("/actions/jobs/77/logs") else "", LIB,
                               {"url": "https://github.com/x/y/actions/runs/5/job/77"})
        self.assertTrue(out.startswith("error: TauCeti/Foo.lean:3:0: line too long"))
        self.assertIn("(no log", follow.ci_errors(lambda p: "", LIB, {"url": "https://example.org/check"}))
        # a status names the whole run: the logs of its failed jobs
        jobs = {"jobs": [{"id": 77, "conclusion": "failure"}, {"id": 78, "conclusion": "success"}]}
        out = follow.ci_errors(lambda path: log if path.endswith("/actions/jobs/77/logs") else "nope", LIB,
                               {"url": "https://github.com/x/y/actions/runs/5"}, rest=lambda path: jobs)
        self.assertTrue(out.startswith("error: TauCeti/Foo.lean:3:0: line too long"))
        self.assertNotIn("nope", out)


if __name__ == "__main__":
    unittest.main()
