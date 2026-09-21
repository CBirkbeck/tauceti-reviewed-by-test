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


if __name__ == "__main__":
    unittest.main()
