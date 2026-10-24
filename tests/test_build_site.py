import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))
import build_site  # noqa: E402
import common  # noqa: E402
import fixture_site  # noqa: E402
import site_data  # noqa: E402

OUT: Path
RESULT: dict


def setUpModule():
    global OUT, RESULT
    OUT = Path(tempfile.mkdtemp(prefix="site-test-"))
    RESULT = fixture_site.build(OUT / "site")


def tearDownModule():
    shutil.rmtree(OUT, ignore_errors=True)


def data(path: str, root: Path | None = None):
    return json.loads(((root or OUT / "site") / "data" / path).read_text(encoding="utf-8"))


def node_id(name: str, root: Path | None = None) -> int:
    return next(r[0] for r in data(f"names/{common.fnv_shard(name, 64)}.json", root) if r[1] == name)


def node(name: str, root: Path | None = None) -> list:
    i = node_id(name, root)
    return data(f"nodes/{i // 2048}.json", root)[i % 2048]


def module_of(name: str, root: Path | None = None) -> dict:
    return data(f"m/{node(name, root)[3]}.json", root)


def entry(name: str, root: Path | None = None) -> dict:
    return next(e for e in module_of(name, root)["decls"] if e["name"] == name)


class MetaTests(unittest.TestCase):
    def test_the_build(self):
        m = data("meta.json")
        self.assertEqual(m["library"]["commit"], "B")
        self.assertEqual(m["counts"]["declarations"], 21)
        self.assertEqual(m["shards"], {"nodes": 2048, "names": 64})
        self.assertEqual(m["store"], {"repo": "example/fixture-store", "name": "Fixture", "bulk": 1})
        self.assertEqual([(i["name"], i["commit"]) for i in m["imports"]], [("Test imports", "c0ffee")])
        self.assertEqual(m["areas"], [["Basic", 15, 1], ["Uses", 4, 1], ["Notation", 2, 0]])

    def test_every_node_is_found_by_its_name(self):
        rows = [json.loads(l) for l in (fixture_site.DATASET / "decls.jsonl").read_text().splitlines() if l.strip()]
        for r in rows:
            self.assertEqual(node(r["name"])[0], r["name"])


class NodeTests(unittest.TestCase):
    def test_a_definition(self):
        n = node("Fixture.triple")
        self.assertEqual(n[1:5], ["d", 1 | 16, 1, "A definition that version B leaves alone."])
        self.assertEqual(n[5:7], [1, 1])  # covered, by a person; and counting AI agents

    def test_a_named_result_rests_on_the_library_first(self):
        n = node("Fixture.triple_pos")
        self.assertTrue(n[2] & 2)
        self.assertEqual(n[4], "The positivity of triple")
        self.assertEqual(n[7][0], node_id("Fixture.triple"))

    def test_what_a_proof_uses(self):
        self.assertEqual(node("Fixture.one")[8], [node_id("Fixture.one_pos'")])

    def test_states(self):
        self.assertEqual(node("Fixture.double")[5], 3)        # only an earlier version was reviewed
        self.assertEqual(node("Fixture.double_zero")[5], 3)   # stale underneath, which people-only does not count
        self.assertEqual(node("Fixture.IsDouble")[5], 0)

    def test_how_much_the_map_can_unfold(self):
        # Of what it rests on, how many are the library's (the map unfolds those); and how many rest on it.
        n = node("Fixture.triple_pos")
        self.assertEqual((n[9], n[12]), (len(n[7]), 1))  # Fixture.triple, then Lean's own
        e = entry("Fixture.triple")
        self.assertEqual(node("Fixture.triple")[13], e["nFacts"] + e.get("nBuiltOn", 0) + e.get("nExamples", 0))
        self.assertEqual(node("Fixture.triple_two")[13], 0)

    def test_what_it_states(self):
        self.assertEqual(node("Fixture.triple_pos")[11], "(n : Nat) (h : 0 < n) : 0 < triple n")
        self.assertEqual(node("Fixture.triple")[11], "(n : Nat) : Nat")
        self.assertEqual(node("Fixture.triple_two")[11], "triple 2 = 6")


def sig(text: str, *names: str) -> dict:
    """A signature facet row whose refs are `names`, each where it first occurs in `text`."""
    return {"text": text, "refs": [[text.index(n), text.index(n) + len(n), n] for n in names]}


class BriefTests(unittest.TestCase):
    brief = staticmethod(site_data.brief)

    def test_implicit_arguments_and_the_name_go(self):
        self.assertEqual(self.brief("Foo.bar", sig("Foo.bar {R : Type u_1} [CommRing R] ⦃x : R⦄ (h : x ≠ 0) : Foo.baz x = x", "Foo.baz")),
                         "[CommRing R] (h : x ≠ 0) : baz x = x")
        self.assertEqual(self.brief("Foo.bar", sig("Foo.bar.{u} {α : Type u} (a : α) : a = a")), "(a : α) : a = a")

    def test_types_and_universes_go(self):
        self.assertEqual(self.brief("T.r", sig("T.r (R : Type u_1) [CommRing R] [T.IsRegularRing R] : T.IsClosed R", "T.IsRegularRing", "T.IsClosed")),
                         "[CommRing R] [IsRegularRing R] : IsClosed R")
        text = "T.c (C D : Type u₁) (S : Sort*) [CategoryTheory.Category.{v, u} C] (F : C ⥤ D) : F = F"
        at = text.index("CategoryTheory")  # the extractor's reference covers the universes too
        self.assertEqual(self.brief("T.c", {"text": text, "refs": [[at, at + 30, "CategoryTheory.Category"]]}),
                         "[Category C] (F : C ⥤ D) : F = F")
        self.assertEqual(self.brief("T.f", sig("T.f (F : Type u → Type v) : Prop")), "(F : Type u → Type v) : Prop")

    def test_brackets_inside_an_argument(self):
        self.assertEqual(self.brief("Foo.f", sig("Foo.f (g : (ℕ → ℕ) → ℕ) [Fact (0 < {n | n = 1}.ncard)] : Prop")),
                         "(g : (ℕ → ℕ) → ℕ) [Fact (0 < {n | n = 1}.ncard)] : Prop")

    def test_one_line(self):
        self.assertEqual(self.brief("Foo.c", sig("Foo.c (x : ℕ)\n    (y : ℕ) : x + y =\n  y + x")), "(x : ℕ) (y : ℕ) : x + y = y + x")

    def test_too_long(self):
        long = "Foo.d [A " + "a" * 90 + "] (h : " + "b" * 50 + ") : c = c"
        self.assertEqual(self.brief("Foo.d", sig(long)), "… (h : " + "b" * 50 + ") : c = c")
        self.assertEqual(self.brief("Foo.d", sig("Foo.d (h : " + "b" * 150 + ") : c = c")), "… c = c")
        cut = self.brief("Foo.e", sig("Foo.e : " + "x + " * 60 + "x = x"))
        self.assertEqual((len(cut), cut[-1]), (site_data.BRIEF_CAP, "…"))

    def test_without_a_signature(self):
        self.assertEqual(self.brief("Foo.g", None), "")


class EntryTests(unittest.TestCase):
    def test_the_source(self):
        e = entry("Fixture.triple")
        self.assertEqual((e["kw"], e["line"]), ("def", [15, 16]))
        self.assertNotIn("stmt", e)  # the signature stands for the statement
        self.assertTrue(e["rest"].startswith(":= n + n + n"))  # a definition's value, as the docs' Equations

    def test_what_the_docs_show(self):
        # The signature as Lean prints it (section variables included), each name its declaration, from
        # one table of names for the module.
        e, names = entry("Fixture.triple_pos"), module_of("Fixture.triple_pos")["names"]
        self.assertEqual(e["sig"], "Fixture.triple_pos (n : Nat) (h : 0 < n) : 0 < Fixture.triple n")
        linked = {e["sig"][a:b]: names[k] for a, b, k in e["sigRefs"]}
        self.assertEqual(linked["Fixture.triple"], "Fixture.triple")
        self.assertEqual(linked["Nat"], "Nat")
        self.assertEqual(linked["<"], "LT")  # a class's field stands for its class
        self.assertEqual(len(names), len(set(names)))
        self.assertIn("Nat", [names[k] for _, _, k in entry("Fixture.triple")["sigRefs"]])  # shared

    def test_no_proofs(self):
        self.assertNotIn("rest", entry("Fixture.triple_pos"))        # a theorem's proof
        self.assertNotIn("rest", entry("Fixture.instInhabitedPos"))  # an instance's value
        self.assertIn("val : Nat", entry("Fixture.Pos")["rest"])     # a structure's fields stay

    def test_what_rests_on_it(self):
        e = entry("Fixture.triple")
        self.assertEqual(e["nFacts"], 6)
        self.assertIn(node_id("Fixture.triple_pos"), e["facts"])
        self.assertNotIn("usedIn", e)

    def test_statuses_reach_the_page(self):
        status = lambda name: [v["status"] for v in entry(name)["records"] if v["kind"] == "review"]
        self.assertEqual(status("Fixture.double_zero"), ["stale-underneath"])
        self.assertEqual(status("Fixture.double"), ["stale"])
        renamed = [v for v in entry("Fixture.triple_three'")["records"] if v["kind"] == "review"][0]
        self.assertEqual((renamed["status"], renamed["renamedFrom"]), ("renamed", "Fixture.triple_three"))
        problem = [v for v in entry("Fixture.one")["records"] if v["kind"] == "review"][0]
        self.assertEqual((problem["verdict"], problem["state"]), ("problem", "invalid"))

    def test_tests_pass(self):
        self.assertEqual([(t["test"], t["result"]) for t in entry("Fixture.triple")["tests"]],
                         [("Fixture.triple_two", "passes")])


class PageFilesTests(unittest.TestCase):
    def test_named(self):
        rows = {r["decl"]: r for r in data("named.json")}
        self.assertEqual(sorted(rows), ["Fixture.IsDouble", "Fixture.triple_pos"])
        r = rows["Fixture.triple_pos"]
        self.assertEqual((r["name"], r["what"], r["prs"], r["area"]), ("The positivity of triple", "result", [5], "Basic"))
        self.assertEqual(r["post"], "https://zulip.example.org/#narrow/channel/610393-Tau-Ceti/topic/new.20results/near/101")
        self.assertEqual(r["cov"], [2, 2, 2, 0])

    def test_search(self):
        names, titles = data("search.json"), data("titles.json")
        self.assertEqual(len(names), 21)
        self.assertEqual(len(titles), 21)
        i = [n[0] for n in names].index("Fixture.triple")
        self.assertEqual((names[i][1], titles[i]), ("d", "A definition that version B leaves alone."))

    def test_upstream(self):
        up = data("upstream.json")
        self.assertEqual(list(up), ["Int"])
        self.assertEqual(up["Int"]["records"][0]["source"], {"repo": "example/imports", "name": "Test imports"})

    def test_activity(self):
        act = data("activity.json")
        self.assertEqual([v["decl"] for v in act["problems"]], ["Fixture.triple_comm"])
        self.assertEqual([v["decl"] for v in act["challenges"]], ["Fixture.double"])
        self.assertIn("Claude Code (claude-opus-5-5) via example", [r["label"] for r in act["reviewers"]])

    def test_reviewed(self):
        # Every declaration answered for, the latest answer first, its answers as [people, AI agents]: the
        # yeses of this version, the noes still open, and those that no longer stand.
        rows = {r["name"]: r for r in data("reviewed.json")}
        self.assertEqual(data("reviewed.json")[0]["name"], "Fixture.triple_comm")
        self.assertEqual((rows["Fixture.triple_comm"]["yes"], rows["Fixture.triple_comm"]["no"]), ([1, 0], [1, 0]))
        self.assertEqual(rows["Fixture.triple"]["yes"], [1, 1])                # a person and an AI agent
        self.assertEqual(rows["Fixture.double"]["earlier"], [1, 0])            # a yes of an earlier version
        self.assertEqual((rows["Fixture.one"]["no"], rows["Fixture.one"]["earlier"]), ([0, 0], [1, 0]))  # a no resolved
        self.assertEqual(rows["Fixture.triple"]["id"], node_id("Fixture.triple"))
        self.assertNotIn("Int", rows)                                          # the library's own only
        m = data("meta.json")["counts"]
        self.assertEqual((m["reviewed"], m["accepts"]), (len(rows), {"people": 5, "ai": 1}))

    def test_a_cap_keeps_the_totals(self):
        root = OUT / "capped"
        fixture_site.build(root, cap=2)
        e = entry("Fixture.triple", root)
        self.assertEqual((len(e["facts"]), e["nFacts"]), (2, 6))

    def test_the_budget(self):
        with self.assertRaises(build_site.SiteTooLarge):
            fixture_site.build(OUT / "over", budget_mb=0)


if __name__ == "__main__":
    unittest.main()
