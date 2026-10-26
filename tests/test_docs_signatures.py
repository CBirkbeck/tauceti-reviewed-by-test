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


if __name__ == "__main__":
    unittest.main()
