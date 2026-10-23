import unittest
from pathlib import Path

from evidence_core import records as rec
from evidence_core.store import Store

ROOT = Path(__file__).resolve().parents[1]
PIN = "d9068003cb02ec808e548ee70982ffef9379db00"


class StoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = Store.load(ROOT / "evidence")

    def test_config(self):
        c = self.store.config
        self.assertEqual(c["name"], "Tau Ceti")
        self.assertEqual(c["library"], {"repo": "TauCetiProject/TauCeti", "root": "TauCeti"})
        self.assertEqual(c["datasets"], {"repo": "CBirkbeck/tauceti-reviewed-by-test",
                                         "tag": "dataset-{commit12}", "asset": "dataset.tar.gz"})
        self.assertEqual(c["imports"], [{"repo": "LeanTrustBuilders/mathlib-probability-evidence"}])
        self.assertEqual(c["maintainers"], ["CBirkbeck"])

    def test_the_migrated_records(self):
        # Only the migrated ones: the store grows with every review, and CI runs this test.
        migrated = [r for r in self.store.records
                    if (r.get("migration") or {}).get("from") in ("reviewed-by/v1", "tests/v1")]
        reviews = [r for r in migrated if r["kind"] == "review"]
        tests = [r for r in migrated if r["kind"] == "test"]
        self.assertEqual((len(reviews), len(tests)), (4, 11))
        for r in reviews + tests:
            self.assertEqual(r["by"]["identity"]["id"], "CBirkbeck")
            self.assertEqual(r["subject"]["hasher"], {"meaning": "ltb-meaning/1", "local": "ltb-local/3"})
            self.assertTrue(r["origin"]["ref"].startswith("CBirkbeck/tauceti-reviewed-by-test#"))
            self.assertEqual(rec.validate(r), [])
        # A review keeps the commit it was made at, its hashes taken at the pin, and says so; the
        # tests' ledger recorded no commit, so a test is keyed at the pin itself.
        for r in reviews:
            self.assertEqual(r["migration"]["hashes_from"], PIN)
        for r in tests:
            self.assertEqual(r["subject"]["commit"], PIN)
        self.assertEqual(sorted({r["subject"]["name"] for r in reviews}),
                         ["HeckeRing.GL2.heckeSlashModularFormEnd", "NumberField.Set.HasNaturalDensity",
                          "TauCeti.IdealArithmeticFunction.vonMangoldt"])


if __name__ == "__main__":
    unittest.main()
