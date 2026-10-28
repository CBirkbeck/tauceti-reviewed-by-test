import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import docs_signatures as dsig  # noqa: E402

DOCS = HERE / "fixtures" / "docs"
#: The commit the fixture pages' source links name (RowInsertion.html's page was built there).
BUILT = "feaf13fb8a52df4dd3d9216fa8ec7abe27a65f20"


def fixture(name: str) -> str:
    return (DOCS / name).read_text(encoding="utf-8")


def rows(name: str) -> dict:
    return dsig.parse(fixture(name)).rows


def linked(row: dict) -> dict:
    """Each linked piece of a row's text, the first time it occurs, and the constant it names."""
    out: dict = {}
    for a, b, const in row["refs"]:
        out.setdefault(row["text"][a:b], const)
    return out


class HeaderTests(unittest.TestCase):
    def test_a_theorem_as_the_docs_head_it(self):
        # The docs' own notation (this page was printed without Mathlib's delaborators), and the lines of
        # the type broken where the docs' printer broke them.
        row = rows("RowInsertion.html")["TauCeti.reverseRowBump_eq_some_iff"]
        self.assertEqual(row["text"],
                         "TauCeti.reverseRowBump_eq_some_iff {α : Type u_1} [LinearOrder α] (x y : α) (row result : List α) :\n"
                         "  reverseRowBump y row = (result, some x) ↔\n"
                         "    ∃ (before : List α),\n"
                         "      ∃ (after : List α),\n"
                         "        row = before ++ x :: after ∧ result = before ++ y :: after ∧ (∀ (z : α), z ∈ after → y ≤ z) ∧ x < y")

    def test_each_link_names_its_constant(self):
        row = rows("RowInsertion.html")["TauCeti.reverseRowBump_eq_some_iff"]
        names = linked(row)
        self.assertEqual(names["LinearOrder"], "LinearOrder")         # a link to Mathlib's docs: ?pattern=
        self.assertEqual(names["reverseRowBump"], "TauCeti.reverseRowBump")  # a link in these docs: #anchor
        self.assertEqual(names["some"], "Option.some")
        self.assertEqual((names["="], names["↔"], names["∃"]), ("Eq", "Iff", "Exists"))  # notation, as the docs link it
        self.assertNotIn("Type", names)  # the docs' page of foundational types names no constant
        self.assertNotIn(0, [a for a, _, _ in row["refs"]])  # its own name is not a reference

    def test_a_structure_with_its_parents(self):
        row = rows("Cat.html")["TauCeti.PointRepresentationCat"]
        self.assertEqual(row["text"],
                         "TauCeti.PointRepresentationCat (R : Type u) [CommRing R] (H : Type v) [CommRing H] [HopfAlgebra R H] "
                         "extends SemimoduleCat R :\n  Type (max (max (u + 1) (v + 1)) (w + 1))")
        self.assertEqual(linked(row)["SemimoduleCat"], "SemimoduleCat")

    def test_fields_are_not_headers(self):
        # The docs show a structure's fields inside it, not as declarations of their own.
        self.assertEqual(list(rows("Cat.html")), ["TauCeti.PointRepresentationCat"])

    def test_an_instance(self):
        row = rows("AlbertAlgebra.html")["TauCeti.AlbertAlgebra.instDistribMulAction"]
        self.assertEqual(row["text"],
                         "TauCeti.AlbertAlgebra.instDistribMulAction {R : Type u_1} {S : Type u_2} [Monoid S] [AddCommMonoid R] "
                         "[DistribMulAction S R] :\n  DistribMulAction S (AlbertAlgebra R)")
        self.assertEqual(linked(row)["AlbertAlgebra"], "TauCeti.AlbertAlgebra")

    def test_no_arguments(self):
        self.assertEqual(rows("Noncommutative.html")["TauCeti.TwistedExamples.ThreeArrow"]["text"],
                         "TauCeti.TwistedExamples.ThreeArrow :\n  Type")

    def test_the_commit_the_page_was_built_at(self):
        self.assertEqual(dsig.parse(fixture("RowInsertion.html")).commit, BUILT)

    def test_refs_are_code_points(self):
        # The page counts positions in code points (Array.from), as Python indexes a str.
        row = rows("RowInsertion.html")["TauCeti.reverseRowBump_eq_some_iff"]
        for a, b, const in row["refs"]:
            self.assertTrue(0 < a < b <= len(row["text"]), (a, b, const))


class FieldTests(unittest.TestCase):
    """A structure's or a class's fields, as the docs list them under its header: those of its parents
    first (inherited), then its own, each `name binders : type`, with a docstring when it has one
    (asked for on 2026-10-28: a structure's header alone says only `: Type`)."""

    def fields(self, page: str, name: str) -> list[dict]:
        return rows(page)[name]["fields"]

    def test_a_structures_fields_its_parents_first(self):
        fs = self.fields("Cat.html", "TauCeti.PointRepresentationCat")
        self.assertEqual([f["text"] for f in fs],
                         ["carrier : Type w", "isAddCommMonoid : AddCommMonoid ↑self.toSemimoduleCat",
                          "isModule : Module R ↑self.toSemimoduleCat", "representation : HopfAlgebra.PointRepresentation"])
        self.assertEqual([bool(f.get("inherited")) for f in fs], [True, True, True, False])
        self.assertEqual(fs[3]["doc"], "The natural point action on the underlying module.")
        self.assertNotIn("doc", fs[0])
        self.assertEqual(linked(fs[0])["carrier"], "SemimoduleCat.carrier")  # an inherited field names its parent's
        self.assertEqual(linked(fs[1])["toSemimoduleCat"], "TauCeti.PointRepresentationCat.toSemimoduleCat")
        self.assertEqual(linked(fs[3])["HopfAlgebra.PointRepresentation"], "TauCeti.HopfAlgebra.PointRepresentation")

    def test_mathlibs_docs_and_their_binders(self):
        # Mathlib's docs put `   :  ` between a field and its type, and a field's own binders after its name.
        self.assertEqual([f["text"] for f in self.fields("MathlibModularForms.html", "ModularForm")],
                         ["toFun : UpperHalfPlane → ℂ",
                          "slash_action_eq' (γ : GL (Fin 2) ℝ) : γ ∈ Γ → SlashAction.map k γ self.toFun = self.toFun",
                          "holo' : MDiff ⇑self.toSlashInvariantForm",
                          "bdd_at_cusps' {c : OnePoint ℝ} (hc : IsCusp c Γ) : c.IsBoundedAt self.toFun k"])

    def test_a_class(self):
        fs = self.fields("MathlibModularForms.html", "ModularFormClass")
        self.assertEqual([f["text"] for f in fs],
                         ["slash_action_eq (f : F) (γ : GL (Fin 2) ℝ) : γ ∈ Γ → SlashAction.map k γ ⇑f = ⇑f",
                          "holo (f : F) : MDiff ⇑f",
                          "bdd_at_cusps (f : F) {c : OnePoint ℝ} (hc : IsCusp c Γ) : c.IsBoundedAt (⇑f) k"])
        self.assertEqual([bool(f.get("inherited")) for f in fs], [True, False, False])
        self.assertEqual(linked(fs[2])["IsCusp"], "IsCusp")

    def test_a_long_type_broken_as_the_docs_break_it_and_code_in_a_docstring(self):
        fs = self.fields("Unramified.html", "TauCeti.IsUnramified")
        self.assertEqual(fs[0], {**fs[0], "text": "ramificationIndex_eq_one : ramificationIndex K L = 1",
                                 "doc": "The ramification index of an unramified extension is `1`."})
        self.assertEqual(fs[1]["text"],
                         "isSeparable_residueField : Algebra.IsSeparable (IsLocalRing.ResidueField ↥(ValuativeRel.valuation K).integer)\n"
                         "    (IsLocalRing.ResidueField ↥(ValuativeRel.valuation L).integer)")
        for f in fs:
            for a, b, const in f["refs"]:
                self.assertTrue(0 <= a < b <= len(f["text"]), (a, b, const))

    def test_under_a_constructor_of_its_own_name(self):
        # `structure BrauerAlgebra … where ofCoeff :: coeff : …`: the docs list the fields under `ofCoeff :: (`.
        fs = self.fields("Brauer.html", "TauCeti.BrauerAlgebra")
        self.assertEqual(fs, [{**fs[0], "text": "coeff : BrauerDiagram k →₀ R",
                               "doc": "The coefficients of an element of the Brauer algebra in the diagram basis."}])

    def test_only_structures_and_classes_have_them(self):
        self.assertNotIn("fields", rows("RowInsertion.html")["TauCeti.reverseRowBump_eq_some_iff"])
        self.assertNotIn("fields", rows("AlbertAlgebra.html")["TauCeti.AlbertAlgebra.instDistribMulAction"])

    def test_where_the_page_comes_from(self):
        self.assertEqual(dsig.parse(fixture("MathlibModularForms.html")).blob,
                         ("leanprover-community/mathlib4", "cc5a8f804aa0eabe95091bf318bef6c1c353f78e",
                          "Mathlib/NumberTheory/ModularForms/Basic.lean"))


class FacetTests(unittest.TestCase):
    """The facet written into a dataset: what the docs have, page by page, for the dataset's declarations."""

    PAGES = {"M.Row": "RowInsertion.html", "M.Cat": "Cat.html", "M.Albert": "AlbertAlgebra.html"}

    def dataset(self, commit: str = BUILT) -> Path:
        d = Path(tempfile.mkdtemp())
        (d / "facets").mkdir()
        decls = [("TauCeti.reverseRowBump_eq_some_iff", "M.Row"), ("TauCeti.PointRepresentationCat", "M.Cat"),
                 ("TauCeti.AlbertAlgebra.instDistribMulAction", "M.Albert"), ("TauCeti.Gone", "M.Gone"),
                 ("Mathlib.thing", "Mathlib.Thing")]
        with (d / "decls.jsonl").open("w", encoding="utf-8") as f:
            for name, module in decls:
                scope = "upstream" if name.startswith("Mathlib") else "project"
                f.write(json.dumps({"name": name, "module": module, "scope": scope}) + "\n")
        meta = {"library": {"commit": commit},
                "facets": [{"name": "signature", "file": "facets/signature.jsonl", "schema": "signature/1"}]}
        (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        return d

    def fetch(self, unread: set[str] = frozenset()):
        def fetch(docs: str, module: str) -> str | None:
            if module in unread:
                raise OSError("the page did not come")
            page = self.PAGES.get(module)
            return fixture(page) if page else None  # None: the docs have no such page
        return fetch

    def run_it(self, d: Path, changed=lambda old, new: set(), **kw) -> dict:
        settings = {"library": {"repo": "o/r", "docs": "https://example.org/docs"}}
        return dsig.run(d, settings, fetch=kw.pop("fetch", self.fetch()), changed=changed, jobs=2, **kw)

    def facet(self, d: Path) -> dict:
        rows = [json.loads(line) for line in (d / "facets" / "docs-signature.jsonl").read_text(encoding="utf-8").splitlines()]
        return {r["decl"]: r for r in rows}

    def test_the_dataset_gets_the_facet(self):
        d = self.dataset()
        r = self.run_it(d)
        self.assertTrue(r["written"])
        self.assertEqual(sorted(self.facet(d)), ["TauCeti.AlbertAlgebra.instDistribMulAction",
                                                 "TauCeti.PointRepresentationCat", "TauCeti.reverseRowBump_eq_some_iff"])
        self.assertEqual(r["missing"], ["M.Gone"])  # no page: its declarations keep the extractor's signature
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        entry = next(f for f in meta["facets"] if f["name"] == "docs-signature")
        self.assertEqual((entry["file"], entry["schema"], entry["count"]), ("facets/docs-signature.jsonl", "docs-signature/1", 3))
        self.assertEqual([f["name"] for f in meta["facets"]], ["signature", "docs-signature"])
        self.run_it(d)  # again: the entry is replaced, not repeated
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual([f["name"] for f in meta["facets"]], ["signature", "docs-signature"])

    def test_only_the_librarys_own_modules_are_read(self):
        asked = []
        fetch = self.fetch()
        self.run_it(self.dataset(), fetch=lambda docs, m: asked.append(m) or fetch(docs, m))
        self.assertNotIn("Mathlib.Thing", asked)

    def test_a_page_older_than_its_module_is_left_out(self):
        # The page was built at BUILT, the dataset is of a later commit, and Cat's file changed in between.
        d = self.dataset(commit="0123456789abcdef0123456789abcdef01234567")
        r = self.run_it(d, changed=lambda old, new: {"M/Cat.lean"})
        self.assertNotIn("TauCeti.PointRepresentationCat", self.facet(d))
        self.assertIn("TauCeti.reverseRowBump_eq_some_iff", self.facet(d))
        self.assertEqual(r["stale"], ["M.Cat"])

    def test_when_what_changed_cannot_be_told_every_older_page_is_left_out(self):
        d = self.dataset(commit="0123456789abcdef0123456789abcdef01234567")
        r = self.run_it(d, changed=lambda old, new: None)
        self.assertEqual(sorted(r["stale"]), ["M.Albert", "M.Cat", "M.Row"])

    def test_pages_that_do_not_come(self):
        d = self.dataset()
        r = self.run_it(d, fetch=self.fetch(unread={"M.Cat"}), max_unread=1)
        self.assertTrue(r["written"])
        self.assertEqual(r["unread"], ["M.Cat"])
        d = self.dataset()
        r = self.run_it(d, fetch=self.fetch(unread={"M.Cat", "M.Albert"}), max_unread=1)
        self.assertFalse(r["written"])  # too many: nothing is written, and the dataset is not published
        self.assertFalse((d / "facets" / "docs-signature.jsonl").exists())


class OutsideTests(unittest.TestCase):
    """Declarations outside the library, from Mathlib's docs (which hold Lean's, Batteries' and Aesop's too).
    Those show Mathlib's latest version, not the one the dataset pins, so a header is taken only where it
    says what Lean prints at the pin: the same text, namespaces, universes and spacing aside, and the same
    constants linked."""

    MODULE = "Mathlib.Algebra.GroupWithZero.Action.Defs"
    #: Lean's printing at the pin (the dataset's signature facet), as the extractor wrote them.
    ZERO = {"decl": "zero_smul",
            "text": "zero_smul.{u_2, u_7} (M₀ : Type u_2) {A : Type u_7} [Zero M₀] [Zero A] [SMulWithZero M₀ A] (m : A) :\n  0 • m = 0",
            "refs": [[53, 57, "Zero"], [63, 67, "Zero"], [72, 84, "SMulWithZero"], [105, 106, "HSMul.hSMul"], [109, 110, "Eq"]]}
    SMUL = {"decl": "smul_zero",
            "text": "smul_zero.{u_1, u_7} {M : Type u_1} {A : Type u_7} [Zero A] [SMulZeroClass M A] (a : M) : a • 0 = 0",
            "refs": [[52, 56, "Zero"], [61, 74, "SMulZeroClass"], [92, 93, "HSMul.hSMul"], [96, 97, "Eq"]]}

    def dataset(self, *lean: dict) -> Path:
        d = Path(tempfile.mkdtemp())
        (d / "facets").mkdir()
        decls = [{"name": "TauCeti.reverseRowBump_eq_some_iff", "module": "M.Row", "scope": "project"},
                 {"name": "zero_smul", "module": self.MODULE, "scope": "upstream"},
                 {"name": "smul_zero", "module": self.MODULE, "scope": "upstream"},
                 {"name": "Nat.gone", "module": "Init.Gone", "scope": "upstream"}]
        (d / "decls.jsonl").write_text("".join(json.dumps(x) + "\n" for x in decls), encoding="utf-8")
        (d / "facets" / "signature.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in lean),
                                                      encoding="utf-8")
        meta = {"library": {"commit": BUILT}, "facets": [{"name": "signature", "file": "facets/signature.jsonl"}]}
        (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        return d

    def run_it(self, d: Path, unread: bool = False) -> dict:
        pages = {("https://example.org/docs", "M.Row"): "RowInsertion.html",
                 ("https://example.org/mathlib", self.MODULE): "MathlibActionDefs.html"}

        def fetch(docs: str, module: str) -> str | None:
            if unread and docs.endswith("/mathlib") and module == self.MODULE:
                raise OSError("the page did not come")
            page = pages.get((docs, module))
            return fixture(page) if page else None
        settings = {"library": {"repo": "o/r", "docs": "https://example.org/docs",
                                "upstream_docs": "https://example.org/mathlib"}}
        return dsig.run(d, settings, fetch=fetch, changed=lambda old, new: set(), jobs=2)

    def facet(self, d: Path) -> dict:
        rows = [json.loads(line) for line in (d / "facets" / "docs-signature.jsonl").read_text(encoding="utf-8").splitlines()]
        return {r["decl"]: r for r in rows}

    def test_a_header_that_says_what_lean_prints_at_the_pin(self):
        d = self.dataset(self.ZERO, self.SMUL)
        r = self.run_it(d)
        self.assertEqual(self.facet(d)["zero_smul"]["text"],
                         "zero_smul (M₀ : Type u_2) {A : Type u_7} [Zero M₀] [Zero A] [SMulWithZero M₀ A] (m : A) :\n  0 • m = 0")
        self.assertIn("smul_zero", self.facet(d))
        self.assertIn("TauCeti.reverseRowBump_eq_some_iff", self.facet(d))  # the library's own, as before
        self.assertEqual((r["outside"]["rows"], r["outside"]["disagree"], r["outside"]["missing"]), (2, 0, ["Init.Gone"]))

    def test_a_header_of_another_version_is_left_out(self):
        # Mathlib changed the statement since the pin: Lean's printing at the pin is what the site shows.
        changed = {**self.SMUL, "text": self.SMUL["text"].replace("a • 0 = 0", "a • 0 = 0 + 0")}
        d = self.dataset(self.ZERO, changed)
        r = self.run_it(d)
        self.assertNotIn("smul_zero", self.facet(d))
        self.assertEqual(r["outside"]["disagree"], 1)

    def test_other_constants_are_another_statement(self):
        other = {**self.SMUL, "refs": [[52, 56, "Zero"], [61, 74, "SMulWithZero"], [92, 93, "HSMul.hSMul"], [96, 97, "Eq"]]}
        d = self.dataset(self.ZERO, other)
        self.run_it(d)
        self.assertNotIn("smul_zero", self.facet(d))

    #: Lean's printing of ModularForm at the pin, from the dataset of 36f24f5d94cc.
    FORM = {"decl": "ModularForm", "extends": [{"refs": [[0, 18, "SlashInvariantForm"]], "text": "SlashInvariantForm Γ k"}],
            "refs": [[17, 25, "Subgroup"], [27, 29, "Matrix.GeneralLinearGroup"], [31, 34, "Fin"], [38, 39, "Real"],
                     [47, 48, "Int"]],
            "text": "ModularForm (Γ : Subgroup (GL (Fin 2) ℝ)) (k : ℤ) : Type"}
    FORMS = "Mathlib.NumberTheory.ModularForms.Basic"
    FILE = ("leanprover-community/mathlib4", "Mathlib/NumberTheory/ModularForms/Basic.lean")
    PIN = "2cabef97b63d3275776b8b060d802de6a6fa1055"

    def fields_run(self, files: dict) -> tuple[dict, dict]:
        """The ModularForm page of Mathlib's docs, built at cc5a8f80, read with Mathlib pinned at PIN, where
        `files` gives the module's file at each revision (`raw`)."""
        d = self.dataset(self.FORM)
        decls = (d / "decls.jsonl").read_text(encoding="utf-8")
        (d / "decls.jsonl").write_text(decls + json.dumps({"name": "ModularForm", "module": self.FORMS, "scope": "upstream"}) + "\n",
                                       encoding="utf-8")
        pages = {("https://example.org/mathlib", self.FORMS): "MathlibModularForms.html",
                 ("https://example.org/docs", "M.Row"): "RowInsertion.html"}
        asked = []

        def raw(repo: str, rev: str, path: str) -> str | None:
            asked.append((repo, rev, path))
            return files.get(rev)
        settings = {"library": {"repo": "o/r", "docs": "https://example.org/docs",
                                "upstream_docs": "https://example.org/mathlib"}}
        r = dsig.run(d, settings, fetch=lambda docs, m: fixture(pages[(docs, m)]) if (docs, m) in pages else None,
                     changed=lambda old, new: set(), jobs=2, pins={self.FILE[0]: self.PIN}, raw=raw)
        self.assertTrue(all((repo, path) == self.FILE for repo, _, path in asked))
        return self.facet(d)["ModularForm"], r

    def test_a_structures_fields_where_its_file_is_the_same_at_the_pin(self):
        row, r = self.fields_run({self.PIN: "the file", "cc5a8f804aa0eabe95091bf318bef6c1c353f78e": "the file"})
        self.assertEqual([f["text"] for f in row["fields"]][2], "holo' : MDiff ⇑self.toSlashInvariantForm")
        self.assertEqual(r["outside"]["unfielded"], 0)

    def test_not_where_its_file_changed_since(self):
        row, r = self.fields_run({self.PIN: "the file", "cc5a8f804aa0eabe95091bf318bef6c1c353f78e": "the file, changed"})
        self.assertNotIn("fields", row)
        self.assertTrue(row["text"].startswith("ModularForm (Γ : Subgroup (GL (Fin 2) ℝ)) (k : ℤ) extends"))  # the header stays
        self.assertEqual(r["outside"]["unfielded"], 1)
        row, _ = self.fields_run({"cc5a8f804aa0eabe95091bf318bef6c1c353f78e": "the file"})  # the pin's did not come
        self.assertNotIn("fields", row)

    def test_the_pins_are_the_librarys_packages_and_its_lean(self):
        d = Path(tempfile.mkdtemp())
        (d / "lake-manifest.json").write_text(json.dumps({"packages": [
            {"name": "mathlib", "url": "https://github.com/leanprover-community/mathlib4", "rev": self.PIN},
            {"name": "batteries", "url": "https://github.com/leanprover-community/batteries.git", "rev": "b" * 40}]}),
            encoding="utf-8")
        (d / "lean-toolchain").write_text("leanprover/lean4:v4.36.0-rc1\n", encoding="utf-8")
        self.assertEqual(dsig.pins_of(d), {"leanprover-community/mathlib4": self.PIN,
                                           "leanprover-community/batteries": "b" * 40, "leanprover/lean4": "v4.36.0-rc1"})
        self.assertEqual(dsig.pins_of(None), {})

    def test_pages_of_mathlibs_docs_that_do_not_come_block_nothing(self):
        d = self.dataset(self.ZERO, self.SMUL)
        r = self.run_it(d, unread=True)
        self.assertTrue(r["written"])
        self.assertEqual(sorted(self.facet(d)), ["TauCeti.reverseRowBump_eq_some_iff"])
        self.assertEqual(r["outside"]["unread"], [self.MODULE])


if __name__ == "__main__":
    unittest.main()
