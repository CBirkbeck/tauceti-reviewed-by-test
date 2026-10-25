import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from answerer.pulls import PullRequests  # noqa: E402

LEAN = "/-- **Thing**, never `0`. -/\ndef thing (n : Nat) : Nat := n + n\n"
BY = {"tool": "Tau Ceti answerer", "model": "claude-fable-5-1"}


def git(d, *a):
    return subprocess.run(["git", "-C", str(d), *a], capture_output=True, text=True, check=True).stdout


class PullRequestTests(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        origin, seed, self.work = tmp / "origin.git", tmp / "seed", tmp / "work"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], check=True)
        (seed / "TauCeti").mkdir()
        (seed / "TauCeti" / "A.lean").write_text(LEAN)
        git(seed, "add", "-A")
        git(seed, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q", "-m", "c")
        git(seed, "push", "-q", str(origin), "main")
        subprocess.run(["git", "clone", "-q", str(origin), str(self.work)], check=True)
        git(self.work, "config", "user.name", "t")
        git(self.work, "config", "user.email", "t@e")
        self.gh_calls, self.built = [], []

        def gh(argv, stdin=None):
            self.gh_calls.append((argv, stdin))
            if argv[:3] == ["gh", "pr", "create"]:
                return "https://github.com/TauCetiProject/TauCeti/pull/77\n"
            if argv[:3] == ["gh", "pr", "view"]:
                return json.dumps({"state": "MERGED", "mergeCommit": {"oid": "f" * 40}})
            return ""

        self.prs = PullRequests(self.work, "TauCetiProject/TauCeti", gh=gh,
                                build=lambda module: self.built.append(module) or (True, ""),
                                roadmaps=lambda: {"PDE", "ModularForms"}, site="https://example.org/")
        self.item = NS(id="abc123", kind="problem", decl="TauCeti.thing", record={"by": {"kind": "person", "identity": {"id": "x"}}})
        self.decl = {"name": "TauCeti.thing", "path": "TauCeti/A.lean", "module": "TauCeti.A"}

    def verdict(self, **kw):
        return {"verdict": "docstring_fix", "reply": "The docstring says never 0; it is 0 at 0.",
                "edits": [{"file": "TauCeti/A.lean", "old": "never `0`", "new": "`0` exactly at `0`"}],
                "pr_title": "docs: say when thing is 0", "roadmap": "PDE", **kw}

    def test_a_pull_request_with_only_the_docstring_changed(self):
        number, err = self.prs.propose(self.item, self.decl, self.verdict(), BY)
        self.assertEqual((number, err), (77, None))
        self.assertEqual(self.built, ["TauCeti.A"])
        shown = git(self.work, "show", "origin/answerer/abc123:TauCeti/A.lean")
        self.assertEqual(shown, LEAN.replace("never `0`", "`0` exactly at `0`"))
        argv, body = next(c for c in self.gh_calls if c[0][:3] == ["gh", "pr", "create"])
        a = dict(zip(argv[3::2], argv[4::2]))
        self.assertEqual((a["--repo"], a["--head"], a["--base"], a["--title"]),
                         ("TauCetiProject/TauCeti", "answerer/abc123", "main", "docs: say when thing is 0"))
        self.assertIn("\nRoadmap: PDE\n", body)
        self.assertIn("claude-fable-5-1", body)
        self.assertIn("https://example.org/#/d/TauCeti.thing", body)

    def test_an_unknown_roadmap_is_none(self):
        self.prs.propose(self.item, self.decl, self.verdict(roadmap="Nonsense"), BY)
        body = next(c for c in self.gh_calls if c[0][:3] == ["gh", "pr", "create"])[1]
        self.assertIn("\nRoadmap: none\n", body)

    def test_edits_elsewhere_are_refused(self):
        number, err = self.prs.propose(self.item, self.decl, self.verdict(edits=[
            {"file": "TauCeti/B.lean", "old": "x", "new": "y"}]), BY)
        self.assertIsNone(number)
        self.assertIn("own file", err)
        number, err = self.prs.propose(self.item, self.decl, self.verdict(edits=[
            {"file": "TauCeti/A.lean", "old": "n + n", "new": "0"}]), BY)
        self.assertIsNone(number)
        self.assertIn("doc comment", err)
        self.assertFalse(any(c[0][:3] == ["gh", "pr", "create"] for c in self.gh_calls))

    def test_a_failed_build_pushes_nothing(self):
        self.prs.build = lambda module: (False, "error: unexpected token")
        number, err = self.prs.propose(self.item, self.decl, self.verdict(), BY)
        self.assertIsNone(number)
        self.assertIn("did not build", err)
        self.assertNotIn("answerer/abc123", git(self.work, "ls-remote", "origin"))

    def test_merged(self):
        self.assertEqual(self.prs.state(77), ("MERGED", "f" * 40))


if __name__ == "__main__":
    unittest.main()
