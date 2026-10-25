import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from answerer.library import Library  # noqa: E402


def git(d: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(d), *args], capture_output=True, text=True, check=True).stdout


def repo(d: Path, files: dict[str, str]) -> str:
    d.mkdir(parents=True)
    git(d, "init", "-q")
    for path, text in files.items():
        (d / path).parent.mkdir(parents=True, exist_ok=True)
        (d / path).write_text(text)
    git(d, "add", "-A")
    git(d, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q", "-m", "c")
    return git(d, "rev-parse", "HEAD").strip()


class LibraryTests(unittest.TestCase):
    """The model reads Tau Ceti at the site's commit and the Mathlib it pins, through git: a path it
    gives can only name a file of theirs."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        work = cls.tmp / "TauCeti"
        cls.commit = repo(work, {"TauCeti/Foo/Bar.lean": "".join(f"line {i}\n" for i in range(1, 501)) + "theorem bar_eq : True := trivial\n",
                                 "TauCeti/Baz.lean": "def baz := 1\n", "secret.txt": "nope\n"})
        (work / "TauCeti" / "Foo" / "Bar.lean").write_text("changed in the working tree\n")  # git shows the commit
        repo(work / ".lake" / "packages" / "mathlib", {"Mathlib/Data/Nat/Basic.lean": "theorem Nat.foo : True := trivial\n"})
        cls.lib = Library(work, cls.commit)

    def test_reads_numbered_lines_at_the_commit(self):
        out = self.lib.read("TauCeti/Foo/Bar.lean", 2, 3)
        self.assertEqual(out, "TauCeti/Foo/Bar.lean, lines 2–3 of 501:\n2: line 2\n3: line 3")
        self.assertIn("1: theorem Nat.foo", self.lib.read("Mathlib/Data/Nat/Basic.lean"))
        self.assertIn("at most 400 lines", self.lib.read("TauCeti/Foo/Bar.lean"))

    def test_only_the_libraries_files(self):
        for path in ["secret.txt", "../secret.txt", "TauCeti/../secret.txt", "/etc/passwd", "TauCeti/Foo/../../secret.txt",
                     "Lean/Elab.lean", "TauCeti//Baz.lean", "TauCeti/Baz.lean:secret.txt", "~/x.lean"]:
            self.assertTrue(self.lib.read(path).startswith("No such file"), path)

    def test_search(self):
        out = self.lib.search("bar_eq", "TauCeti")
        self.assertEqual(out, "TauCeti/Foo/Bar.lean:501:theorem bar_eq : True := trivial")
        self.assertIn("Mathlib/Data/Nat/Basic.lean:1:", self.lib.search("Nat.foo", "Mathlib"))
        self.assertEqual(self.lib.search("nothing_here", "TauCeti"), "No matches.")
        self.assertTrue(self.lib.search("x", "TauCeti", "../").startswith("Not searched"))
        self.assertTrue(self.lib.search("x", "Elsewhere").startswith("Not searched"))
        self.assertIn("120 matches", Library(self.lib.work, self.commit, max_matches=120).search("line", "TauCeti"))

    def test_modules(self):
        self.assertTrue(self.lib.module_exists("TauCeti.Foo.Bar"))
        self.assertTrue(self.lib.module_exists("Mathlib.Data.Nat.Basic"))
        self.assertFalse(self.lib.module_exists("TauCeti.Nope"))
        self.assertFalse(self.lib.module_exists("TauCeti.Foo/../Baz"))


if __name__ == "__main__":
    unittest.main()
