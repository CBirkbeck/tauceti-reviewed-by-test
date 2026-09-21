"""Reading declarations out of Tau Ceti's Lean sources (scripts/fetch_declarations.py)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetch_declarations import declarations  # noqa: E402

SOURCE = '''/-!
# Ideal arithmetic functions

Functions on the nonzero ideals of a number field.
-/

namespace TauCeti

/-- Arithmetic functions on nonzero ideals. -/
abbrev IdealArithmeticFunction := (Ideal (𝓞 K))⁰ → ℂ

namespace IdealArithmeticFunction

open Classical in
/-- The **ideal von Mangoldt function**. -/
noncomputable def vonMangoldt : IdealArithmeticFunction K := fun A ↦
  if h : IsPrimePow (A : Ideal (𝓞 K)) then
    (Real.log (Ideal.absNorm h.choose) : ℂ)
  else 0

/-- It vanishes at the unit ideal. -/
@[simp]
theorem vonMangoldt_one : (vonMangoldt : IdealArithmeticFunction K) 1 = 0 := by
  simp

private def helper : ℕ := 3

section Transport

/-- Transport along an isomorphism. -/
protected def map (e : K ≃+* L) : IdealArithmeticFunction K → IdealArithmeticFunction L :=
  fun f I => f I

end Transport

/-- A multiplicative ideal function. -/
structure IsMultiplicative (f : IdealArithmeticFunction K) : Prop where
  map_one : f 1 = 1
  map_mul : ∀ I J, f (I * J) = f I * f J

end IdealArithmeticFunction

theorem _root_.foo_bar : True := trivial

end TauCeti
'''


class Declarations(unittest.TestCase):
    def setUp(self):
        self.found = {d["name"]: d for d in declarations(SOURCE, "TauCeti/X.lean", "abc")}

    def test_full_names_follow_namespaces_and_sections(self):
        self.assertEqual(sorted(self.found), sorted([
            "TauCeti.IdealArithmeticFunction", "TauCeti.IdealArithmeticFunction.vonMangoldt",
            "TauCeti.IdealArithmeticFunction.vonMangoldt_one", "TauCeti.IdealArithmeticFunction.map",
            "TauCeti.IdealArithmeticFunction.IsMultiplicative", "foo_bar"]))

    def test_private_declarations_are_not_reviewable(self):
        self.assertNotIn("TauCeti.IdealArithmeticFunction.helper", self.found)

    def test_a_docstring_survives_open_in_and_attributes(self):
        self.assertEqual(self.found["TauCeti.IdealArithmeticFunction.vonMangoldt"]["doc"], "The **ideal von Mangoldt function**.")
        self.assertEqual(self.found["TauCeti.IdealArithmeticFunction.vonMangoldt_one"]["doc"], "It vanishes at the unit ideal.")

    def test_a_definition_is_shown_whole_and_a_theorem_by_its_statement(self):
        definition = self.found["TauCeti.IdealArithmeticFunction.vonMangoldt"]
        self.assertTrue(definition["source"].startswith("noncomputable def vonMangoldt"))
        self.assertTrue(definition["source"].rstrip().endswith("else 0"))
        theorem = self.found["TauCeti.IdealArithmeticFunction.vonMangoldt_one"]
        self.assertEqual(theorem["kind"], "theorem")
        self.assertEqual(theorem["source"], "theorem vonMangoldt_one : (vonMangoldt : IdealArithmeticFunction K) 1 = 0")
        fields = self.found["TauCeti.IdealArithmeticFunction.IsMultiplicative"]["source"]
        self.assertIn("map_mul : ∀ I J, f (I * J) = f I * f J", fields)

    def test_the_hash_ignores_layout_but_not_content(self):
        again = {d["name"]: d for d in declarations(SOURCE.replace("fun A ↦\n  if h", "fun A ↦\n      if h"), "TauCeti/X.lean", "abc")}
        name = "TauCeti.IdealArithmeticFunction.vonMangoldt"
        self.assertEqual(again[name]["hash"], self.found[name]["hash"])
        changed = {d["name"]: d for d in declarations(SOURCE.replace("else 0", "else 1"), "TauCeti/X.lean", "abc")}
        self.assertNotEqual(changed[name]["hash"], self.found[name]["hash"])

    def test_each_declaration_links_to_its_lines(self):
        definition = self.found["TauCeti.IdealArithmeticFunction.vonMangoldt"]
        self.assertEqual(definition["url"], f"https://github.com/TauCetiProject/TauCeti/blob/abc/TauCeti/X.lean#L{definition['line']}-L{definition['end']}")
        self.assertEqual(SOURCE.splitlines()[definition["line"] - 1], "noncomputable def vonMangoldt : IdealArithmeticFunction K := fun A ↦")


COMMENTED = """/-!
# Notes

theorem of Faltings, recalled below.
-/

/- A comment /- with a nested one -/
lemma is not a declaration here either.
-/

/-- A named instance. -/
instance instFooBar : Foo Bar := ⟨⟩

instance : Foo Baz := ⟨⟩

/-- A lemma, kept as written. -/
lemma two_eq : 2 = 2 := rfl
"""


class Kinds(unittest.TestCase):
    def setUp(self):
        self.found = {d["name"]: d for d in declarations(COMMENTED, "TauCeti/Y.lean", "abc")}

    def test_comments_and_module_docs_hold_no_declarations(self):
        self.assertEqual(sorted(self.found), ["instFooBar", "two_eq"])

    def test_a_named_instance_is_reviewable(self):
        self.assertEqual((self.found["instFooBar"]["kind"], self.found["instFooBar"]["keyword"]), ("instance", "instance"))
        self.assertEqual(self.found["instFooBar"]["doc"], "A named instance.")

    def test_the_keyword_is_kept_as_written(self):
        self.assertEqual((self.found["two_eq"]["kind"], self.found["two_eq"]["keyword"]), ("theorem", "lemma"))


class Clone(unittest.TestCase):
    def test_every_module_of_a_clone_is_read(self):
        import tempfile
        from fetch_declarations import read_clone
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "TauCeti" / "A").mkdir(parents=True)
            (root / "TauCeti" / "A" / "B.lean").write_text(SOURCE, encoding="utf-8")
            (root / "TauCeti" / "C.lean").write_text(COMMENTED, encoding="utf-8")
            (root / "Other.lean").write_text(SOURCE, encoding="utf-8")
            index = read_clone(root, "abc")
        self.assertEqual([m["module"] for m in index["modules"]], ["TauCeti.A.B", "TauCeti.C"])
        self.assertEqual(index["tauceti"], "abc")
        self.assertEqual(len(index["declarations"]), 8)
        self.assertEqual(index["modules"][0]["doc"].splitlines()[0], "# Ideal arithmetic functions")


if __name__ == "__main__":
    unittest.main()
