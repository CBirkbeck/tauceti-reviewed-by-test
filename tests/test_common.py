import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import common  # noqa: E402


class FnvTests(unittest.TestCase):
    def test_shards_match_the_page(self):
        # web/data.js computes the same (the browser check compares them).
        self.assertEqual(common.fnv_shard("TauCeti.Place", 64), 47)
        self.assertEqual(common.fnv_shard("Fixture.triple", 64), 60)
        self.assertEqual(common.fnv_shard("Fixture.«term𝟚_»", 64), 38)
        self.assertEqual(common.fnv_shard("ℝ", 64), 8)


class SettingsTests(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "settings.json"
            common.save_settings({"tauceti": "abc", "library": {"name": "Tau Ceti"}}, p)
            self.assertEqual(common.load_settings(p), {"tauceti": "abc", "library": {"name": "Tau Ceti"}})
            self.assertTrue(p.read_text().endswith("\n"))

    def test_the_repository_settings(self):
        s = common.load_settings()
        self.assertEqual(s["repo"], "CBirkbeck/tauceti-reviewed-by-test")
        self.assertEqual(s["library"]["repo"], "TauCetiProject/TauCeti")
        # The fork carries 0.13.2 (signatures with binders' types) until LeanTrustBuilders/extractor does.
        self.assertEqual(s["extractor"], {"repo": "CBirkbeck/extractor", "series": "0.13"})
        self.assertEqual(s["voyager"]["topic"], "new results")
        self.assertEqual(s["site"]["title"], "Tau Ceti Review")


if __name__ == "__main__":
    unittest.main()
