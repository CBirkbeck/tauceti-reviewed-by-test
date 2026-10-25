import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from answerer.leancheck import Sandbox, bad_imports, refuse  # noqa: E402


class RefuseTests(unittest.TestCase):
    """Lean runs code while it elaborates (`#eval`, `run_cmd`, elaborators, initializers, …): a check
    that could is refused before anything runs. The sandbox is what contains one that gets through."""

    def test_mathematics_passes(self):
        for code in ["#check @TauCeti.IsDemushkin",
                     "example : (2 : ℕ) + 2 = 4 := by norm_num",
                     "theorem t (n : ℕ) : n + 0 = n := by simp",
                     "open Real in\n#check Real.pi",
                     "variable (G : Type*) [Group G]\n#check (1 : G)",
                     "example (f : ℕ → ℕ) : @id ℕ (f 0) = f 0 := rfl",
                     "#print axioms Nat.add_comm",
                     "#synth Group (Equiv.Perm (Fin 3))",
                     "-- `IsPrefix` in a comment, and List.IsPrefix\n#check List.IsPrefix"]:
            self.assertIsNone(refuse(code), code)

    def test_code_that_runs_is_refused(self):
        for code in ["#eval IO.Process.run {cmd := \"curl\"}",
                     "#eval (1 : ℕ)",
                     "run_cmd Lean.logInfo m!\"hi\"",
                     "example : True := by run_tac pure ()",
                     "example : True := by_elab pure (Lean.mkConst ``True.intro)",
                     "elab \"x\" : term => pure default",
                     "macro \"x\" : term => `(1)",
                     "local notation \"⋆\" => 1",
                     "syntax \"x\" : term",
                     "initialize foo : Unit ← pure ()",
                     "@[implemented_by f] def g := 1",
                     "unsafe def f : ℕ := 1",
                     "set_option maxHeartbeats 0 in\nexample : True := trivial",
                     "import Mathlib",
                     "example : 2 + 2 = 4 := by native_decide",
                     "#check include_str \"/etc/passwd\"",
                     "attribute [simp] Nat.add_comm",
                     "#check «IO»",
                     "#guard 1 = 1",
                     "def f : System.FilePath := default",
                     "example : True := by exact $(x)"]:
            self.assertIsNotNone(refuse(code), code)

    def test_size(self):
        self.assertIsNotNone(refuse("#check Nat\n" * 2000))


class ImportsTests(unittest.TestCase):
    def test_modules_of_the_library_or_mathlib_that_exist(self):
        exists = {"TauCeti.Foo.Bar", "Mathlib.Data.Nat.Basic"}.__contains__
        self.assertIsNone(bad_imports(["TauCeti.Foo.Bar", "Mathlib.Data.Nat.Basic"], exists))
        self.assertIsNotNone(bad_imports(["Lean.Elab.Command"], exists))
        self.assertIsNotNone(bad_imports(["TauCeti.Missing"], exists))
        self.assertIsNotNone(bad_imports(["TauCeti.Foo.Bar\nrun_cmd x"], exists))
        self.assertIsNotNone(bad_imports([f"Mathlib.M{i}" for i in range(9)], lambda m: True))


class SandboxTests(unittest.TestCase):
    def sandbox(self):
        return Sandbox(toolchain=Path("/home/u/.elan/toolchains/lean"), roots=[Path("/home/u/a/work/TauCeti")],
                       lean_path="/home/u/a/work/TauCeti/.lake/build/lib/lean", home=Path("/home/u"),
                       scratch=Path("/home/u/a/sandbox"))

    def test_sealed_off(self):
        argv = self.sandbox().command(Path("/home/u/a/sandbox/Check.lean"))
        self.assertEqual(argv[0], "bwrap")
        for flag in ("--unshare-all", "--die-with-parent", "--new-session", "--clearenv"):
            self.assertIn(flag, argv)
        # The home directory is an empty tmpfs, mounted before the read-only builds inside it.
        tmpfs_home = [i for i, a in enumerate(argv) if a == "--tmpfs" and argv[i + 1] == "/home/u"]
        binds = [i for i, a in enumerate(argv) if a == "--ro-bind" and argv[i + 1].startswith("/home/u/")]
        self.assertTrue(tmpfs_home and binds and tmpfs_home[0] < min(binds))
        self.assertNotIn("--bind", argv)  # nothing writable from outside
        env = {argv[i + 1]: argv[i + 2] for i, a in enumerate(argv) if a == "--setenv"}
        self.assertEqual(set(env), {"LEAN_PATH", "HOME", "PATH"})
        self.assertEqual(argv[-1], "/tmp/Check.lean")
        self.assertIn("timeout", argv)

    def test_a_build_writes_only_its_checkout(self):
        argv = self.sandbox().build_command(Path("/home/u/a/work/TauCeti-pr"), "TauCeti.A")
        writable = [argv[i + 1] for i, a in enumerate(argv) if a == "--bind"]
        self.assertEqual(writable, ["/home/u/a/work/TauCeti-pr"])
        self.assertIn("--unshare-all", argv)
        self.assertEqual(argv[-3:], ["/home/u/.elan/toolchains/lean/bin/lake", "build", "TauCeti.A"])

    def test_runs_only_what_passes(self):
        ran = []
        sb = self.sandbox()
        sb.runner = lambda argv, timeout: ran.append(argv) or (0, "")
        sb.write = lambda path, text: ran.append(text)
        self.assertIn("refused", sb.check(["Mathlib.Data.Nat.Basic"], "#eval 1", exists=lambda m: True))
        self.assertEqual(ran, [])
        out = sb.check(["Mathlib.Data.Nat.Basic"], "#check Nat", exists=lambda m: True)
        self.assertEqual(ran[0], "import Mathlib.Data.Nat.Basic\n\n#check Nat\n")
        self.assertIn("no errors", out.lower())


if __name__ == "__main__":
    unittest.main()
