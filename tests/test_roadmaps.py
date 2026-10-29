import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import roadmaps  # noqa: E402


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.org", *args],
                          check=True, capture_output=True, text=True).stdout


def page(nodes: list, after: str | None = None) -> dict:
    """One page of PRs as GitHub's GraphQL API answers: each [number, labels]."""
    return {"pageInfo": {"hasNextPage": after is not None, "endCursor": after},
            "nodes": [{"number": n, "labels": {"nodes": [{"name": x} for x in labels]}} for n, labels in nodes]}


class LabelTests(unittest.TestCase):
    def test_the_pr_a_commit_is(self):
        self.assertEqual(roadmaps.pr_of("feat: almost-split sequences exist over every finite-dimensional algebra (#22526)"), 22526)
        self.assertEqual(roadmaps.pr_of("Merge pull request #20292 from TauCetiProject/fix/git-only-review"), 20292)
        self.assertIsNone(roadmaps.pr_of("Align status and Pages consumers with Git-only review policy"))
        self.assertIsNone(roadmaps.pr_of("fix: what (#12) said, again"))  # a PR named in passing is not the commit's

    def test_the_roadmap_a_pr_is_labelled_with(self):
        self.assertEqual(roadmaps.roadmap_of(["ready-to-merge", "roadmap/StableReduction"]), "StableReduction")
        # Infrastructure and cross-cutting work, an attribution missing or invalid, none, and two at once credit nothing.
        for labels in (["roadmap/none"], ["roadmap/Unknown"], [], ["ready-to-merge"], ["roadmap/PDE", "roadmap/Yamabe"]):
            self.assertIsNone(roadmaps.roadmap_of(labels), labels)

    def test_every_page_of_prs_is_read(self):
        pages = {None: page([(1, ["roadmap/PDE", "ready-to-merge"]), (2, ["roadmap/none"])], after="x"),
                 "x": page([(3, [])])}
        asked = []

        def ask(owner, name, after):
            asked.append((owner, name, after))
            return pages[after]
        self.assertEqual(roadmaps.fetch("TauCetiProject/TauCeti", ask), {1: "PDE", 2: None, 3: None})
        self.assertEqual(asked, [("TauCetiProject", "TauCeti", None), ("TauCetiProject", "TauCeti", "x")])


class AttributeTests(unittest.TestCase):
    """A declaration's lines, each the age of the commit that last changed it (0 the newest), and the roadmap each
    commit credits."""

    CREDITS = ["Yamabe", None, "PDE", "Yamabe"]

    def test_the_roadmap_with_most_lines(self):
        self.assertEqual(roadmaps.attribute([2, 2, 0], self.CREDITS), ("PDE", 2, 3))

    def test_a_line_that_credits_nothing_is_counted_but_credits_nothing(self):
        self.assertEqual(roadmaps.attribute([2, 1, 1], self.CREDITS), ("PDE", 1, 3))

    def test_a_tie_goes_to_the_roadmap_that_wrote_a_line_last(self):
        self.assertEqual(roadmaps.attribute([3, 2], self.CREDITS), ("PDE", 1, 2))
        self.assertEqual(roadmaps.attribute([2, 0], self.CREDITS), ("Yamabe", 1, 2))

    def test_no_line_credited(self):
        self.assertIsNone(roadmaps.attribute([1, None], self.CREDITS))


class RunTests(unittest.TestCase):
    """A library whose first-parent history is: #1 (PDE) writes `a`; #2 (roadmap/none) rewrites a line of `a` and
    adds `c`; #3 (Yamabe) adds `b`; a commit that names no PR rewrites a line of `b`; and a branch, its own commits
    naming no PR, merged as #5 (Orbifolds), adds `e`."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="roadmaps-test-"))
        repo = cls.repo = cls.tmp / "lib"
        (repo / "Lib").mkdir(parents=True)
        git(repo, "init", "-q", "-b", "main")
        lines: list[str] = []

        def commit(subject: str, *edits: tuple[int, str]) -> None:
            for at, text in edits:
                if at < len(lines):
                    lines[at] = text
                else:
                    lines.append(text)
            (repo / "Lib" / "A.lean").write_text("".join(t + "\n" for t in lines), encoding="utf-8")
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", subject)
        commit("feat: a (#1)", (0, "/-- One is one. -/"), (1, "theorem a : 1 = 1 := by"), (2, "  rfl"))
        commit("refactor: golf (#2)", (2, "  exact rfl"), (3, "theorem c : 3 = 3 := rfl"))
        commit("feat: b (#3)", (4, "theorem b : 2 = 2 := by"), (5, "  rfl"))
        commit("chore: tidy", (5, "  exact rfl"))
        git(repo, "checkout", "-q", "-b", "feature")
        commit("wip", (6, "theorem e : 4 = 4 := rfl"))
        git(repo, "checkout", "-q", "main")
        git(repo, "merge", "-q", "--no-ff", "feature", "-m", "Merge pull request #5 from someone/feature")
        lines.pop()  # main has `e` from the merge, not from a commit of its own
        cls.head = git(repo, "rev-parse", "HEAD").strip()
        cls.labels = {1: "PDE", 2: None, 3: "Yamabe", 5: "Orbifolds"}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def dataset(self, name: str) -> Path:
        """A dataset of the library at its head: its meta and the facet `source`, `a` on lines 1-3 and so on, and `x`
        in a file the commit does not have."""
        d = self.tmp / name
        (d / "facets").mkdir(parents=True)
        source = [("a", "Lib/A.lean", 1, 3), ("c", "Lib/A.lean", 4, 4), ("b", "Lib/A.lean", 5, 6),
                  ("e", "Lib/A.lean", 7, 7), ("x", "Lib/Gone.lean", 1, 2)]
        (d / "facets" / "source.jsonl").write_text("".join(
            json.dumps({"decl": n, "path": path, "start": [a, 0], "end": [b, 10], "keyword": "theorem"}) + "\n"
            for n, path, a, b in source), encoding="utf-8")
        (d / "meta.json").write_text(json.dumps({"library": {"commit": self.head, "repo": "test/lib"}, "facets": [
            {"name": "source", "file": "facets/source.jsonl", "schema": "source/1"}]}), encoding="utf-8")
        return d

    def facet(self, d: Path) -> list[dict]:
        return [json.loads(line) for line in (d / "facets" / "roadmap.jsonl").read_text(encoding="utf-8").splitlines()]

    def test_each_declaration_the_roadmap_of_most_of_its_lines(self):
        d = self.dataset("credited")
        out = roadmaps.run(d, self.repo, {"library": {"repo": "test/lib"}}, labels=lambda repo: self.labels, jobs=2)
        self.assertTrue(out["written"])
        # `a`: two lines of #1's, one of #2's, which credits nothing; `c`, only #2's, has no row; `b`: one line of
        # #3's and one of a commit that names no PR; `e`, from a branch's commit, is the merge's (#5).
        self.assertEqual(self.facet(d), [{"decl": "a", "roadmap": "PDE", "lines": [2, 3]},
                                         {"decl": "b", "roadmap": "Yamabe", "lines": [1, 2]},
                                         {"decl": "e", "roadmap": "Orbifolds", "lines": [1, 1]}])
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        entry = next(f for f in meta["facets"] if f["name"] == "roadmap")
        self.assertEqual((entry["file"], entry["schema"], entry["count"]), ("facets/roadmap.jsonl", "roadmap/1", 3))
        # A file git cannot blame is said, and its declarations have no row.
        self.assertEqual((out["declarations"], out["rows"], out["roadmaps"], out["unblamed"]), (5, 3, 3, ["Lib/Gone.lean"]))
        # The commit graph, with the paths each commit changed, which makes blaming a file seven times faster.
        self.assertTrue((self.repo / ".git" / "objects" / "info" / "commit-graph").exists())
        # Run again, it replaces the facet rather than listing it twice.
        roadmaps.run(d, self.repo, {"library": {"repo": "test/lib"}}, labels=lambda repo: self.labels, jobs=1)
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual([f["name"] for f in meta["facets"]], ["source", "roadmap"])

    def test_labels_that_do_not_come_write_nothing(self):
        d = self.dataset("unread")

        def labels(repo):
            raise roadmaps.LabelsUnread("GitHub did not answer")
        out = roadmaps.run(d, self.repo, {"library": {"repo": "test/lib"}}, labels=labels)
        self.assertFalse(out["written"])
        self.assertFalse((d / "facets" / "roadmap.jsonl").exists())
        self.assertEqual([f["name"] for f in json.loads((d / "meta.json").read_text(encoding="utf-8"))["facets"]], ["source"])

    def test_a_shallow_clone_is_refused(self):
        shallow = self.tmp / "shallow"
        subprocess.run(["git", "clone", "-q", "--depth", "1", self.repo.as_uri(), str(shallow)], check=True)
        self.assertEqual(roadmaps.main(["--dataset", str(self.dataset("shallow-dataset")), "--source", str(shallow)]), 2)

    def test_a_clone_without_the_commit_is_refused(self):
        d = self.dataset("elsewhere")
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        meta["library"]["commit"] = "0" * 40
        (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        self.assertEqual(roadmaps.main(["--dataset", str(d), "--source", str(self.repo)]), 2)
        self.assertFalse((d / "facets" / "roadmap.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
