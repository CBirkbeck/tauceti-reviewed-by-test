import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import fixture_site  # noqa: E402
from evidence_core import records as rec  # noqa: E402
from evidence_core.coverage import Evidence  # noqa: E402
from evidence_core.dataset import Dataset  # noqa: E402
from evidence_core.store import Store, default_config  # noqa: E402

from answerer.items import declaration, open_items  # noqa: E402
from answerer.library import Library  # noqa: E402


def evidence(extra: list[dict] = ()) -> tuple[Evidence, Dataset]:
    ds = Dataset.load(fixture_site.DATASET)
    store = Store.init(Path(tempfile.mkdtemp()) / "evidence", default_config("example/fixture-store", "Fixture", "F"))
    store.add(rec.load(fixture_site.FIXTURES / "records.jsonl"))
    store.add(fixture_site.extra_records(ds))
    store.add(list(extra))
    return Evidence.resolve(Store.load(store.root).records, ds), ds


class OpenItemsTests(unittest.TestCase):
    def test_the_open_noes_and_suggestions(self):
        ev, _ = evidence()
        items = open_items(ev, "example/fixture-store")
        self.assertEqual([(i.kind, i.decl, i.issue) for i in items],
                         [("problem", "Fixture.triple_comm", 14), ("question", "Fixture.triple", 15)])
        self.assertEqual(items[0].author, "someone")
        self.assertFalse(items[0].by_agent)

    def test_closed_or_withdrawn_ones_are_not(self):
        ev, ds = evidence()
        first = open_items(ev, "example/fixture-store")[0]
        closed = {"schema": rec.SCHEMA, "kind": "status", "target": first.id, "state": "invalid",
                  "by": fixture_site.PERSON, "at": "2026-10-24T00:00:00Z", "origin": {"kind": "issue", "ref": "example/fixture-store#14"}}
        ev, _ = evidence([closed])
        self.assertEqual([i.decl for i in open_items(ev, "example/fixture-store")], ["Fixture.triple"])

    def test_people_before_agents(self):
        ds = Dataset.load(fixture_site.DATASET)
        agents = {"schema": rec.SCHEMA, "kind": "review", "verdict": "problem", "category": "other", "rubric": "ltb-rubric/1",
                  "subject": rec.subject_from_decl(ds.by_name["Fixture.double"], ds), "by": fixture_site.AGENT,
                  "at": "2026-01-01T00:00:00Z", "text": "An AI agent's no, the oldest of all.",
                  "origin": {"kind": "file", "ref": "https://example.org/batch.jsonl#L1"}}
        ev, _ = evidence([agents])
        items = open_items(ev, "example/fixture-store")
        self.assertEqual([i.decl for i in items], ["Fixture.triple_comm", "Fixture.triple", "Fixture.double"])
        self.assertTrue(items[-1].by_agent)
        self.assertIsNone(items[-1].issue)  # from a pull request's file: no issue of its own


class DeclarationTests(unittest.TestCase):
    def test_its_source_with_its_docstring(self):
        tmp = Path(tempfile.mkdtemp())
        shutil.copytree(fixture_site.SOURCE, tmp / "src")
        run = lambda *a: subprocess.run(["git", "-C", str(tmp / "src"), *a], capture_output=True, text=True, check=True).stdout
        run("init", "-q"); run("add", "-A"); run("-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q", "-m", "c")
        lib = Library(tmp / "src", run("rev-parse", "HEAD").strip(), root="Fixture")
        _, ds = evidence()
        d = declaration(ds, lib, "Fixture.triple_comm")
        self.assertEqual((d["path"], d["kind"], d["module"]), ("Fixture/Basic.lean", "theorem", "Fixture.Basic"))
        self.assertIn("theorem triple_comm", d["source"])
        self.assertEqual(d["signature"], "Fixture.triple_comm (b : Nat) : Fixture.triple b = b + b + b")
        up = declaration(ds, lib, "Int")
        self.assertEqual((up["path"], up["source"], up["module"]), (None, None, "Init.Data.Int.Basic"))


if __name__ == "__main__":
    unittest.main()
