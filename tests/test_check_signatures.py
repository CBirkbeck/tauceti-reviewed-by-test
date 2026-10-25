import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import check_signatures as cs  # noqa: E402
from common import header  # noqa: E402

#: The docs' header of the theorem the site showed wrongly on 2026-10-25, and the site's signature then
#: and with binders' types printed.
DOCS = ("theorem AlgebraicGeometry.Scheme.exists_isClosedImmersion_proj {k : Type u} [Field k] (X : Scheme) "
        "[X.Over (Spec ↧k)] [IsCurveOver k] [∀ (y : TauCeti.AlgebraicGeometry.CodimensionOnePoint X), "
        "IsDiscreteValuationRing ↑(X.presheaf.stalk ↑y)] :∃ (V : Submodule k ↑X.functionField) "
        "(_ : FiniteDimensional k ↥V) (f : X ⟶ Proj (TauCeti.SymmetricAlgebra.homogeneousSubmodule k ↥V)), "
        "IsClosedImmersion f ∧ Hom.IsOver f (Spec ↧k)")
HEAD = ("AlgebraicGeometry.Scheme.exists_isClosedImmersion_proj.{u} {k : Type u} [Field k]\n"
        "  (X : AlgebraicGeometry.Scheme) [X.Over (AlgebraicGeometry.Spec ↧k)]\n"
        "  [AlgebraicGeometry.Scheme.IsCurveOver k]\n"
        "  [∀ (y : TauCeti.AlgebraicGeometry.CodimensionOnePoint X),\n"
        "      IsDiscreteValuationRing ↑(X.presheaf.stalk ↑y)] :\n")
WRONG = HEAD + ("  ∃ V,\n    ∃ (_ : FiniteDimensional k ↥V),\n      ∃ f,\n        AlgebraicGeometry.IsClosedImmersion f ∧\n"
                "          AlgebraicGeometry.Scheme.Hom.IsOver f (AlgebraicGeometry.Spec ↧k)")
RIGHT = HEAD + ("  ∃ (V : Submodule k ↑X.functionField) (_ : FiniteDimensional k ↥V)\n"
                "    (f : X ⟶ AlgebraicGeometry.Proj (TauCeti.SymmetricAlgebra.homogeneousSubmodule k ↥V)),\n"
                "    AlgebraicGeometry.IsClosedImmersion f ∧ AlgebraicGeometry.Scheme.Hom.IsOver f (AlgebraicGeometry.Spec ↧k)")

PAGE = """<html><body><div class="decl" id="Fixture.thing"><div class="theorem">
<div class="gh_link"><a href="https://github.com/o/r/blob/da4d8dc48847cea93910477b85cf0cd427f169b3/F.lean#L1-L2">source</a></div>
<div class="decl_header"><span class="decl_kind">theorem</span> <span class="decl_name">Fixture.thing</span>
<span class="decl_args">(<span class="fn">n</span> : <a href="x">ℕ</a>)</span> :<div class="decl_type">∃ (m : ℕ), m &lt; n</div></div>
<div class="decl_doc"><p>Not part of the header.</p></div></div></div></body></html>"""


class UntypedTests(unittest.TestCase):
    def test_binders_without_their_types(self):
        for text in ("∃ V, p V", "∃! x y, p", "∀ x, p x", "fun x => x", "λ x ↦ x", "∑ i, f i", "⋃ i, s i",
                     "∫ x in s, f x", "{x | x ∈ l}", "{x // p x}"):
            self.assertIsNotNone(cs.untyped(text), text)

    def test_binders_with_them(self):
        for text in ("∃ (V : T), p", "∃ x ∈ s, p", "∀ x ∈ s, p x", "∀ (x : α), p", "fun (x : α) => x",
                     "∑ i ∈ s, f i", "∑ (i : ι), f i", "{x : M | x ∈ l}", "{x : T // p x}", "(x : ℕ) → x = x"):
            self.assertIsNone(cs.untyped(text), text)

    def test_not_in_an_arguments_default_tactic(self):
        # Printed as written, in the docs too: `(le : α → α → Bool := by exact fun a b => a ≤ b)`.
        self.assertIsNone(cs.untyped("List.mergeSort (xs : List α) (le : α → α → Bool := by exact fun a b => decide (a ≤ b)) : List α"))
        self.assertEqual(cs.untyped("(f : α → β := fun x => x) : ∃ y, p y"), "fun x =>")

    def test_the_signature_the_site_showed(self):
        self.assertEqual(cs.untyped(WRONG), "∃ V,")
        self.assertIsNone(cs.untyped(RIGHT))


class CompareTests(unittest.TestCase):
    def test_namespaces_universes_keyword_and_spacing_set_aside(self):
        self.assertEqual(cs.normal(DOCS), cs.normal(RIGHT))
        self.assertEqual(cs.normal("noncomputable def A.b.{u} (x : ℕ) : ℕ"), cs.normal("A.b.{u} (x : ℕ) : ℕ"))

    def test_two_notations_written_out(self):
        same = [("S.thm (C : V) (a : A) : (fun₀ | C => a) ∈ S.part C", "theorem S.thm (C : V) (a : A) :Finsupp.single C a ∈ part C"),
                ("T.t (i : Fin m) : f = MonoidAlgebra.single (Multiplicative.ofAdd fun₀ | { down := i } => -1) 1",
                 "theorem T.t (i : Fin m) :f = MonoidAlgebra.single (Multiplicative.ofAdd (Finsupp.single { down := i } (-1))) 1"),
                ("P.ext {X Y : Pointed} {f g : (X ⟹ Y).X} : f = g",
                 "theorem P.ext {X Y : Pointed} {f g : ((CategoryTheory.ihom X).obj Y).X} :f = g"),
                ("S.iso (M : S) : M.over X ⟹ S.unit R ≅ N", "def S.iso (M : S) :(CategoryTheory.ihom (M.over X)).obj (unit R) ≅ N")]
        for site, docs in same:
            self.assertEqual(cs.notation_free(site), cs.notation_free(docs), site)
        # Anything else that differs still does.
        self.assertNotEqual(cs.notation_free("S.thm (C : V) (a : A) : (fun₀ | C => a) ∈ S.part C"),
                            cs.notation_free("theorem S.thm (C : V) (a : A) :Finsupp.single a C ∈ part C"))

    def test_what_was_lost_is_a_difference(self):
        self.assertNotEqual(cs.normal(DOCS), cs.normal(WRONG))

    def test_a_structure_is_headed_with_what_it_extends(self):
        sig = {"text": "Fixture.BigPos : Type", "refs": [],
               "extends": [{"text": "Fixture.Pos", "refs": [[0, 11, "Fixture.Pos"]]}]}
        text, refs = header(sig)
        self.assertEqual(text, "Fixture.BigPos extends Fixture.Pos : Type")
        self.assertEqual([text[s:e] for s, e, _ in refs], ["Fixture.Pos"])
        self.assertEqual(cs.normal("structure Fixture.BigPos extends Pos : Type"), cs.normal(text))
        two = {"text": "S (n : ℕ) : Prop", "refs": [[7, 8, "Nat"], [12, 16, "Prop"]],
               "extends": [{"text": "A n", "refs": [[0, 1, "A"]]}, {"text": "B n", "refs": [[0, 1, "B"]]}]}
        text, refs = header(two)
        self.assertEqual(text, "S (n : ℕ) extends A n, B n : Prop")
        self.assertEqual([text[s:e] for s, e, _ in refs], ["ℕ", "A", "B", "Prop"])
        self.assertEqual(header({"text": "f (x : ℕ) : ℕ", "refs": []}), ("f (x : ℕ) : ℕ", []))


class DocsTests(unittest.TestCase):
    def test_a_module_page(self):
        h = cs.Headers()
        h.feed(PAGE)
        self.assertEqual(h.commit, "da4d8dc48847cea93910477b85cf0cd427f169b3")
        self.assertEqual(" ".join(h.headers["Fixture.thing"].split()), "theorem Fixture.thing (n : ℕ) :∃ (m : ℕ), m < n")

    def dataset(self, sig: str) -> Path:
        d = Path(tempfile.mkdtemp())
        (d / "facets").mkdir()
        (d / "decls.jsonl").write_text(json.dumps({"name": "Fixture.thing", "module": "Fixture.Basic", "scope": "project"}) + "\n")
        (d / "facets" / "signature.jsonl").write_text(json.dumps({"decl": "Fixture.thing", "text": sig}) + "\n")
        (d / "facets" / "source.jsonl").write_text(json.dumps({"decl": "Fixture.thing", "path": "F.lean"}) + "\n")
        (d / "meta.json").write_text(json.dumps({"library": {"commit": "da4d8dc48847cea93910477b85cf0cd427f169b3"}}))
        return d

    def run_check(self, sig: str, exceptions: Path | None = None) -> dict:
        def fetch(docs, module):
            h = cs.Headers()
            h.feed(PAGE)
            return h
        settings = {"library": {"repo": "o/r", "docs": "https://example.org/docs"}}
        store = Path(tempfile.mkdtemp())
        (store / "records").mkdir()
        return cs.check(self.dataset(sig), settings, store, store / "none.jsonl", fetch=fetch, sample=5,
                        exceptions=exceptions)

    def test_as_the_docs_have_it(self):
        r = self.run_check("Fixture.thing (n : ℕ) : ∃ (m : ℕ), m < n")
        self.assertEqual((r["compared"], r["differ"], r["untyped"]), (1, [], []))

    def test_a_reviewed_difference(self):
        site = "Fixture.thing (n : ℕ) : ∃ (m : ℕ), m < n + 0"
        ex = Path(tempfile.mkdtemp()) / "exceptions.json"
        ex.write_text(json.dumps([{"decl": "Fixture.thing", "site": site,
                                   "docs": "theorem Fixture.thing (n : ℕ) :∃ (m : ℕ), m < n", "why": "reviewed"}]))
        r = self.run_check(site, exceptions=ex)
        self.assertEqual((r["differ"], r["excused"]), ([], ["Fixture.thing"]))
        # Either text changing voids it.
        r = self.run_check("Fixture.thing (n : ℕ) : ∃ (m : ℕ), m < n + 1", exceptions=ex)
        self.assertEqual([d["decl"] for d in r["differ"]], ["Fixture.thing"])

    def test_otherwise_it_fails(self):
        r = self.run_check("Fixture.thing (n : ℕ) : ∃ m, m < n")
        self.assertEqual(r["compared"], 1)
        self.assertEqual([d["decl"] for d in r["differ"]], ["Fixture.thing"])
        self.assertEqual(r["untyped"], [["Fixture.thing", "∃ m,"]])


if __name__ == "__main__":
    unittest.main()
