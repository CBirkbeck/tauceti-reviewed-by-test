import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from answerer.upstream import Upstream, dependencies  # noqa: E402

MATHLIB = "leanprover-community/mathlib4"
DEPS = {MATHLIB: {"name": "mathlib", "rev": "r" * 40}}


class Gh:
    """A fake `gh`: the answer of the first key found in the call's arguments."""

    def __init__(self, answers: dict):
        self.answers, self.calls = answers, []

    def __call__(self, argv, stdin=None):
        self.calls.append(argv)
        for key, out in self.answers.items():
            if any(key in a for a in argv):
                return out
        return ""


def comments(*cs):
    return "".join(json.dumps({"login": login, "body": body}) + "\n" for login, body in cs)


class UpstreamTests(unittest.TestCase):
    def test_dependencies_from_the_manifest(self):
        manifest = Path(tempfile.mkdtemp()) / "lake-manifest.json"
        manifest.write_text(json.dumps({"packages": [
            {"url": "https://github.com/leanprover-community/mathlib4.git", "name": "mathlib", "rev": "a" * 40},
            {"url": "https://github.com/leanprover-community/Batteries", "name": "batteries", "rev": "b" * 40},
            {"url": "https://gitlab.com/someone/thing", "name": "thing", "rev": "c" * 40},
            {"url": "https://github.com/someone/unpinned", "name": "unpinned"}]}))
        self.assertEqual(dependencies(manifest), {MATHLIB: {"name": "mathlib", "rev": "a" * 40},
                                                  "leanprover-community/batteries": {"name": "batteries", "rev": "b" * 40}})
        self.assertEqual(Upstream("x/y", DEPS).name(MATHLIB), "Mathlib")

    def test_the_last_pull_request_a_maintainer_linked(self):
        gh = Gh({"issues/978/comments": comments(
            ("github-actions[bot]", f"Recorded problem, see https://github.com/{MATHLIB}/pull/1"),
            ("CBirkbeck", f"<!-- agent: tool=Tau Ceti answerer; model=claude-fable-5-1 -->\nhttps://github.com/{MATHLIB}/pull/2"),
            ("someone", f"Fixed in {MATHLIB}#3"),
            ("CBirkbeck", "<!-- agent: tool=Claude Code; model=claude-opus-5-5 -->\n"
                          f"The fix: https://github.com/{MATHLIB}/pull/45669/files"),
            ("CBirkbeck", "Compare https://github.com/other/repo/pull/7, which is not a dependency."))})
        up = Upstream("example/store", DEPS, gh=gh)
        self.assertEqual(up.linked(978, ("CBirkbeck",), "Tau Ceti answerer"), (MATHLIB, 45669))
        self.assertIn("repos/example/store/issues/978/comments", gh.calls[0])
        self.assertIsNone(up.linked(978, ("CBirkbeck",), "Tau Ceti answerer", skip=[(MATHLIB, 45669)]))
        gh.answers["issues/978/comments"] += comments(("CBirkbeck", "Now Leanprover-Community/Mathlib4#45700 instead."))
        self.assertEqual(up.linked(978, ("CBirkbeck",), "Tau Ceti answerer", skip=[(MATHLIB, 45669)]), (MATHLIB, 45700))

    def test_included_when_the_pinned_revision_is_ahead(self):
        for status, included in [("ahead", True), ("identical", True), ("behind", False), ("diverged", False)]:
            gh = Gh({"/compare/": status + "\n"})
            self.assertEqual(Upstream("x/y", DEPS, gh=gh).includes(MATHLIB, "f" * 40), included)
            self.assertIn(f"repos/{MATHLIB}/compare/{'f' * 40}...{'r' * 40}?per_page=1", gh.calls[0])

    def test_merged_by_bors_on_master(self):
        gh = Gh({"/commits?": "e" * 40 + "\tdoc(AlgebraicGeometry/EllipticCurve/Reduction): c₄, not a₄ (#45669)\n",
                 "view": json.dumps({"state": "CLOSED", "mergeCommit": None, "closedAt": "2026-11-06T10:00:00Z"}),
                 f"repos/{MATHLIB}": "master\n"})
        self.assertEqual(Upstream("x/y", DEPS, gh=gh).state(MATHLIB, 45669), ("MERGED", "e" * 40))
        listed = next(a for argv in gh.calls for a in argv if "/commits?" in a)
        self.assertEqual(listed, f"repos/{MATHLIB}/commits?sha=master&per_page=100"
                                 "&since=2026-11-05T10:00:00Z&until=2026-11-06T11:00:00Z")


if __name__ == "__main__":
    unittest.main()
