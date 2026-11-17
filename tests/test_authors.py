import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import authors  # noqa: E402


def git(repo: Path, *args: str, name: str = "Test", email: str = "test@example.org") -> str:
    env = {"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email, "GIT_COMMITTER_NAME": "Committer",
           "GIT_COMMITTER_EMAIL": "committer@example.org", "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(repo)}
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env).stdout


#: The accounts GitHub knows of the addresses that are not its noreply ones; Zed's it does not know.
GITHUB = {"bot@example.org": "helper-bot", "bob@example.org": "bob", "dave@example.org": "dave",
          "merger@example.org": "merger"}


class HistoryTests(unittest.TestCase):
    """A library whose main has, in order: alice writes `a`, `b` and `c` in Lib/A.lean; a bot account, with bob as
    co-author, changes a hypothesis of `a`; carol renames the file Lib/B.lean; dave moves `b` to Lib/C.lean; erin deletes
    a line from inside `a`; frank rewrites `c` wholesale; carol changes a line of `c` with two co-authors, GitHub's own
    address and one GitHub does not know; and a merger merges grace's branch, which adds `d` in Lib/D.lean."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="authors-test-"))
        repo = cls.repo = cls.tmp / "lib"
        (repo / "Lib").mkdir(parents=True)
        git(repo, "init", "-q", "-b", "main")

        def put(path: str, *lines: str) -> None:
            (repo / path).write_text("".join(line + "\n" for line in lines), encoding="utf-8")

        def commit(who: str, email: str, subject: str) -> None:
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", subject, name=who, email=email)

        a = ["/-- The first one. -/", "theorem a_long_name (h : 0 < 1)", "    (h' : 1 < 2) :", "    1 = 1 := by",
             "  exact rfl", ""]
        b = ["theorem b_moved_somewhere_else : 2 = 2 := by", "  exact (rfl : (2 : Nat) = 2)", ""]
        c = ["theorem c_rewritten_wholesale : 3 = 3 := by", "  exact rfl"]
        put("Lib/A.lean", *a, *b, *c)
        commit("Alice", "1001+alice@users.noreply.github.com", "feat: a, b and c (#1)")
        a[1] = "theorem a_long_name (h : 0 < 2)"
        put("Lib/A.lean", *a, *b, *c)
        commit("Helper Bot", "bot@example.org", "fix: a's hypothesis (#2)\n\nCo-authored-by: Bob <bob@example.org>")
        git(repo, "mv", "Lib/A.lean", "Lib/B.lean")
        commit("Carol", "carol@users.noreply.github.com", "chore: rename (#3)")
        put("Lib/B.lean", *a, *c)
        put("Lib/C.lean", *b[:2])
        commit("Dave", "dave@example.org", "refactor: move b (#4)")
        del a[2]
        put("Lib/B.lean", *a, *c)
        commit("Erin", "erin@users.noreply.github.com", "refactor: drop a hypothesis (#5)")
        c = ["theorem c_rewritten_wholesale : (3 : Nat) = 3 := by", "  norm_num", "  -- done"]
        put("Lib/B.lean", *a, *c)
        commit("Frank", "frank@users.noreply.github.com", "refactor: c again (#6)")
        c[1] = "  simp"
        put("Lib/B.lean", *a, *c)
        commit("Carol", "carol@users.noreply.github.com",
               "golf: c (#7)\n\nCo-authored-by: Claude Code <noreply@github.com>\nCo-authored-by: Zed <zed@nowhere.example>")
        git(repo, "checkout", "-q", "-b", "feature")
        put("Lib/D.lean", "theorem d_from_a_branch : 4 = 4 := rfl")
        commit("Grace", "grace@users.noreply.github.com", "wip")
        git(repo, "checkout", "-q", "main")
        git(repo, "merge", "-q", "--no-ff", "feature", "-m", "Merge pull request #8 from grace/feature",
            name="Merger", email="merger@example.org")
        cls.head = git(repo, "rev-parse", "HEAD").strip()
        cls.asked: list[list[str]] = []

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def ask(self, repo: str, oids: list[str]) -> dict:
        """GitHub, faked: each commit's people with the account of each address it knows."""
        self.asked.append(list(oids))
        _, people = authors.commits_of(self.repo, self.head)
        return {oid: [(p.email, GITHUB.get(p.email)) for p in people[oid]] for oid in oids}

    def dataset(self, name: str) -> Path:
        d = self.tmp / name
        (d / "facets").mkdir(parents=True)
        source = [("a", "Lib/B.lean", 1, 5), ("c", "Lib/B.lean", 6, 8), ("b", "Lib/C.lean", 1, 2),
                  ("d", "Lib/D.lean", 1, 1), ("x", "Lib/Gone.lean", 1, 2)]
        (d / "facets" / "source.jsonl").write_text("".join(
            json.dumps({"decl": n, "path": path, "start": [s, 0], "end": [e, 10], "keyword": "theorem"}) + "\n"
            for n, path, s, e in source), encoding="utf-8")
        (d / "meta.json").write_text(json.dumps({"library": {"commit": self.head, "repo": "test/lib"}, "facets": [
            {"name": "source", "file": "facets/source.jsonl", "schema": "source/1"}]}), encoding="utf-8")
        return d

    def facet(self, d: Path) -> dict[str, dict]:
        rows = [json.loads(line) for line in (d / "facets" / "authors.jsonl").read_text(encoding="utf-8").splitlines()]
        return {r.pop("decl"): r for r in rows}

    def test_every_author_of_every_line_and_its_co_authors(self):
        d = self.dataset("all")
        out = authors.run(d, self.repo, "test/lib", {}, ask=self.ask)
        self.assertTrue(out["written"])
        got = self.facet(d)
        # `a`: alice wrote it; the bot changed a hypothesis with bob as co-author; erin deleted a line inside it. Carol
        # only renamed its file, which changed none of its lines.
        self.assertEqual(got["a"]["authors"], ["alice", "bob", "erin", "helper-bot"])
        # `b` moved to another file with its lines: alice wrote them, dave moved them.
        self.assertEqual(got["b"]["authors"], ["alice", "dave"])
        # `c`, rewritten wholesale by frank, keeps alice; carol changed a line, with GitHub's own address as co-author,
        # who is no one, and an address GitHub does not know, which is counted.
        self.assertEqual((got["c"]["authors"], got["c"]["unknown"]), (["alice", "carol", "frank"], 1))
        # `d` came with a merge: grace's, not the merger's.
        self.assertEqual(got["d"]["authors"], ["grace"])
        self.assertNotIn("x", got)  # a file the commit does not have
        self.assertEqual([got[n]["commits"] for n in "abcd"], [3, 2, 3, 1])
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        entry = next(f for f in meta["facets"] if f["name"] == "authors")
        self.assertEqual((entry["file"], entry["schema"], entry["count"]), ("facets/authors.jsonl", "authors/1", 4))
        self.assertEqual(entry["unresolved"], [{"email": "zed@nowhere.example", "name": "Zed", "commits": 1}])
        self.assertEqual((out["unresolved"], out["unknown"]), (1, 1))

    def test_github_is_asked_only_for_addresses_it_alone_can_map(self):
        self.asked.clear()
        authors.run(self.dataset("asked"), self.repo, "test/lib", {}, ask=self.ask)
        _, people = authors.commits_of(self.repo, self.head)
        emails = {p.email for oid in sum(self.asked, []) for p in people[oid]}
        # One request, one commit for each address that is not a noreply one: not GitHub's own, and not the merger's,
        # who is no merged commit's person.
        self.assertEqual(len(self.asked), 1)
        self.assertTrue({"bot@example.org", "bob@example.org", "dave@example.org", "zed@nowhere.example"} <= emails)
        self.assertNotIn("merger@example.org", emails)

    def test_the_owners_map_of_addresses_comes_first(self):
        d = self.dataset("mapped")
        authors.run(d, self.repo, "test/lib", {"Zed@Nowhere.example": "zed"}, ask=self.ask)
        got = self.facet(d)
        self.assertEqual(got["c"], {"authors": ["alice", "carol", "frank", "zed"], "commits": 3})

    def test_github_not_answering_writes_nothing(self):
        d = self.dataset("unread")

        def ask(repo, oids):
            raise authors.GitHubUnread("GitHub did not answer")
        self.assertFalse(authors.run(d, self.repo, "test/lib", {}, ask=ask)["written"])
        self.assertFalse((d / "facets" / "authors.jsonl").exists())

    def test_a_shallow_clone_is_refused(self):
        shallow = self.tmp / "shallow"
        subprocess.run(["git", "clone", "-q", "--depth", "1", self.repo.as_uri(), str(shallow)], check=True)
        self.assertEqual(authors.main(["--dataset", str(self.dataset("shallow-dataset")), "--source", str(shallow)]), 2)


class PeopleTests(unittest.TestCase):
    def test_a_commits_people(self):
        got = authors.people_of("Bot", "Bot@Example.org", "Bob <bob@example.org>\x1fBob <bob@example.org>\x1fno address")
        self.assertEqual(got, [authors.Person("Bot", "bot@example.org"), authors.Person("Bob", "bob@example.org")])

    def test_noreply_addresses(self):
        self.assertEqual(authors.noreply_login("1001+alice-b@users.noreply.github.com"), "alice-b")
        self.assertEqual(authors.noreply_login("alice@users.noreply.github.com"), "alice")
        self.assertEqual(authors.noreply_login("41898282+github-actions[bot]@users.noreply.github.com"),
                         "github-actions[bot]")
        self.assertIsNone(authors.noreply_login("alice@example.org"))

    def test_one_login_is_spelt_one_way(self):
        got = authors.canonical({"a@x": "Alice", "b@x": "alice", "c@x": "Alice", "d@x": "bob"})
        self.assertEqual(got, {"a@x": "Alice", "b@x": "Alice", "c@x": "Alice", "d@x": "bob"})


class ApplyTests(unittest.TestCase):
    """A file's lines through one commit's hunks: each line the set of commits it carries."""

    def lines(self, state: authors.FileState, prov: authors.Provenances) -> list[set]:
        return [set(prov.sets[i]) for i in state.lines]

    def test_a_replacement_carries_what_it_replaced(self):
        prov = authors.Provenances()
        state = authors.FileState([prov.of({0})] * 3 + [prov.of({1})], [0] * 4)
        hunk = authors.Hunk(2, 2, 2, 1, ["x", "y"], ["z"])  # lines 2 and 3 become one
        after = authors.apply(state, [hunk], 5, prov, {})
        self.assertEqual(self.lines(after, prov), [{0}, {0, 5}, {1}])

    def test_an_insertion_carries_its_commit_alone(self):
        prov = authors.Provenances()
        state = authors.FileState([prov.of({0})] * 2, [0, 0])
        after = authors.apply(state, [authors.Hunk(1, 0, 2, 2, [], ["new", "lines"])], 7, prov, {})
        self.assertEqual(self.lines(after, prov), [{0}, {7}, {7}, {0}])

    def test_a_deletion_leaves_its_commit_on_the_gap(self):
        prov = authors.Provenances()
        state = authors.FileState([prov.of({0}), prov.of({1}), prov.of({2})], [0, 0, 0])
        after = authors.apply(state, [authors.Hunk(2, 1, 1, 0, ["gone"], [])], 9, prov, {})
        self.assertEqual(self.lines(after, prov), [{0}, {2}])
        self.assertEqual(set(prov.sets[after.gaps[1]]), {1, 9})

    def test_a_moved_line_carries_where_it_came_from(self):
        prov = authors.Provenances()
        moved = {authors.key("theorem moved_here : True := trivial"): [prov.of({3})]}
        after = authors.apply(authors.FileState(), [authors.Hunk(0, 0, 1, 2, [], ["theorem moved_here : True := trivial",
                                                                               "  rfl"])], 8, prov, moved)
        self.assertEqual(self.lines(after, prov), [{3, 8}, {8}])
        self.assertIsNone(authors.key("  rfl"))  # too short and too common to say where it came from


if __name__ == "__main__":
    unittest.main()
