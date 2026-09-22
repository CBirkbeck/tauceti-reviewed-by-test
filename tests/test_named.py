"""The named results and definitions: harvested from the roadmaps and from Voyager (scripts/named.py)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from named import named_by_declaration, roadmap_names, voyager_names  # noqa: E402

DOCS = "https://taucetiproject.github.io/TauCeti/docs/TauCeti/NumberTheory"
STATUS = f"""# Status: ArithmeticDirichletSeries

## Where this roadmap stands

### Named results

- **Landau's theorem** — a Dirichlet series with nonnegative coefficients admits no continuation across its abscissa ([`TauCeti.LSeries.landau`]({DOCS}/LSeries/Landau.html#TauCeti.LSeries.landau)), now with its corollary ([`TauCeti.LSeries.meromorphicOrderAt_lt_zero_of_eq_LSeries`]({DOCS}/LSeries/Landau.html#TauCeti.LSeries.meromorphicOrderAt_lt_zero_of_eq_LSeries)).

### Notable definitions and infrastructure

- **Euler-product data** — the package the export contract names ([`TauCeti.EulerProductData`]({DOCS}/EulerProduct/Data.html#TauCeti.EulerProductData)).

### Roadmap coverage

- **Not a result** — layers 0 to 5 are done ([`TauCeti.Nope`]({DOCS}/Nope.html#TauCeti.Nope)).

## The frontier

- **Wiener–Ikehara** — what remains is the sharp cutoff.
"""

POST = f"""**Voyager · what's new in Tau Ceti** *(AI-generated summary)*

*Named results*
- **[Landau's theorem]({DOCS}/LSeries/Landau.html#TauCeti.LSeries.landau)** — no continuation across the abscissa (Landau 1905). (TauCeti#7001)
- **[Rouché's theorem]({DOCS}/Rouche.html#TauCeti.rouche)**† — equal zero counts under domination. (TauCeti#7002, TauCeti#7010)

*Notable definitions*
- **[The ideal von Mangoldt function]({DOCS}/VonMangoldt.html#TauCeti.IdealArithmeticFunction.vonMangoldt)** — log N(P) on prime powers. (TauCeti#6990)

† = also being formalised in Mathlib.
"""
INDEX = {"tauceti": "c0ffee", "declarations": [
    {"name": "TauCeti.LSeries.landau", "kind": "theorem"}, {"name": "TauCeti.EulerProductData", "kind": "structure"},
    {"name": "TauCeti.rouche", "kind": "theorem"}, {"name": "TauCeti.IdealArithmeticFunction.vonMangoldt", "kind": "def"}]}


class Roadmaps(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        root = Path(self.folder.name)
        (root / "TauCetiRoadmap" / "ArithmeticDirichletSeries").mkdir(parents=True)
        (root / "TauCetiRoadmap" / "ArithmeticDirichletSeries" / "STATUS.md").write_text(STATUS, encoding="utf-8")
        self.found = roadmap_names(root)

    def tearDown(self):
        self.folder.cleanup()

    def test_named_results_and_notable_definitions_are_read_with_every_declaration_they_link(self):
        self.assertEqual([(n["decl"], n["name"], n["what"]) for n in self.found], [
            ("TauCeti.LSeries.landau", "Landau's theorem", "result"),
            ("TauCeti.LSeries.meromorphicOrderAt_lt_zero_of_eq_LSeries", "Landau's theorem", "result"),
            ("TauCeti.EulerProductData", "Euler-product data", "definition")])

    def test_each_keeps_its_sentence_without_the_links_and_its_roadmap(self):
        first = self.found[0]
        self.assertEqual(first["about"], "a Dirichlet series with nonnegative coefficients admits no continuation across its abscissa, "
                                         "now with its corollary.")
        self.assertEqual(first["source"], {"roadmap": "ArithmeticDirichletSeries",
                                           "path": "TauCetiRoadmap/ArithmeticDirichletSeries/STATUS.md"})


class Voyager(unittest.TestCase):
    def test_each_announcement_names_a_declaration(self):
        found = voyager_names([{"id": 614, "timestamp": 1790000000, "content": POST}])
        self.assertEqual([(n["decl"], n["name"], n["what"]) for n in found], [
            ("TauCeti.LSeries.landau", "Landau's theorem", "result"),
            ("TauCeti.rouche", "Rouché's theorem", "result"),
            ("TauCeti.IdealArithmeticFunction.vonMangoldt", "The ideal von Mangoldt function", "definition")])
        self.assertEqual(found[1]["source"], {"voyager": 614, "prs": [7002, 7010]})
        self.assertEqual(found[1]["about"], "equal zero counts under domination.")
        self.assertEqual(found[1]["at"], "2026-09-21T14:13:20Z")


class Merged(unittest.TestCase):
    def test_a_declaration_named_twice_keeps_every_source_and_the_first_name(self):
        roadmap = [{"decl": "TauCeti.LSeries.landau", "name": "Landau's theorem", "what": "result", "about": "a.", "source": {"roadmap": "R"}}]
        ledger = [{"schema": "named/v1", "decl": "TauCeti.LSeries.landau", "name": "Landau's nonnegativity theorem", "what": "result",
                   "about": "b.", "source": {"voyager": 614, "prs": [7001]}, "at": "t"},
                  {"schema": "named/v1", "decl": "TauCeti.Gone", "name": "Gone", "what": "result", "about": "", "source": {}, "at": "t"}]
        found = named_by_declaration(INDEX, roadmap, ledger)
        self.assertEqual(list(found), ["TauCeti.LSeries.landau"])
        self.assertEqual(found["TauCeti.LSeries.landau"]["name"], "Landau's theorem")
        self.assertEqual([s["source"] for s in found["TauCeti.LSeries.landau"]["sources"]],
                         [{"roadmap": "R"}, {"voyager": 614, "prs": [7001]}])


if __name__ == "__main__":
    unittest.main()
