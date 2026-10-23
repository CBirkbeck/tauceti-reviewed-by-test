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


def entry(name: str, root: Path | None = None) -> dict:
    module = node(name, root)[3]
    return next(e for e in data(f"m/{module}.json", root)["decls"] if e["name"] == name)


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


class EntryTests(unittest.TestCase):
    def test_the_source(self):
        e = entry("Fixture.triple")
        self.assertEqual((e["kw"], e["line"]), ("def", [15, 16]))
        self.assertTrue(e["stmt"].startswith("def triple (n : Nat) : Nat"))
        self.assertTrue(e["rest"].startswith(":= n + n + n"))  # a definition's value, as the docs' Equations

    def test_what_the_docs_show(self):
        # The signature as Lean prints it (section variables included), each name its declaration.
        e = entry("Fixture.triple_pos")
        self.assertEqual(e["sig"], "Fixture.triple_pos (n : Nat) (h : 0 < n) : 0 < Fixture.triple n")
        linked = {e["sig"][a:b]: e["sigNames"][k] for a, b, k in e["sigRefs"]}
        self.assertEqual(linked["Fixture.triple"], "Fixture.triple")
        self.assertEqual(linked["Nat"], "Nat")
        self.assertEqual(linked["<"], "LT")  # a class's field stands for its class

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
        self.assertEqual(act["problems"], [])
        self.assertEqual([v["decl"] for v in act["challenges"]], ["Fixture.double"])
        self.assertIn("Claude Code (claude-opus-5-5) via example", [r["label"] for r in act["reviewers"]])

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
