import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import extractor  # noqa: E402
import pin  # noqa: E402

TAGS = ["v4.34.0-rc2", "v0.13.1-lean-v4.36.0-rc1", "v0.13.1-lean-v4.35.0", "v0.13.0-lean-v4.35.0",
        "v0.14.0-lean-v4.37.0-rc1", "v0.12.1-lean-v4.35.0-rc2", "v0.13.1-lean-v4.35.0-rc4"]


class ExtractorTests(unittest.TestCase):
    def test_the_newest_release_of_the_series_for_each_toolchain(self):
        self.assertEqual(extractor.supported(TAGS, "0.13"),
                         {"4.35.0": "v0.13.1-lean-v4.35.0", "4.35.0-rc4": "v0.13.1-lean-v4.35.0-rc4",
                          "4.36.0-rc1": "v0.13.1-lean-v4.36.0-rc1"})

    def test_another_series_is_not_taken(self):
        self.assertEqual(extractor.supported(TAGS, "0.14"), {"4.37.0-rc1": "v0.14.0-lean-v4.37.0-rc1"})

    def test_toolchain_of(self):
        self.assertEqual(extractor.toolchain_of("leanprover/lean4:v4.36.0-rc1\n"), "4.36.0-rc1")
        self.assertEqual(extractor.toolchain_of("v4.35.0"), "4.35.0")


class PinTests(unittest.TestCase):
    COMMITS = [("c3", "leanprover/lean4:v4.37.0-rc1\n"), ("c2", "leanprover/lean4:v4.36.0-rc1\n"),
               ("c1", "leanprover/lean4:v4.36.0-rc1\n")]

    def test_the_newest_supported_and_cached_commit(self):
        self.assertEqual(pin.choose(self.COMMITS, {"4.36.0-rc1"}, lambda sha, text: True), "c2")

    def test_a_commit_the_cache_has_not_built_is_skipped(self):
        self.assertEqual(pin.choose(self.COMMITS, {"4.36.0-rc1"}, lambda sha, text: sha == "c1"), "c1")

    def test_nothing_when_nothing_fits(self):
        self.assertIsNone(pin.choose(self.COMMITS, {"4.35.0"}, lambda sha, text: True))

    def test_the_cache_address(self):
        self.assertEqual(pin.cache_url("TauCetiProject/TauCeti", "abc", "leanprover/lean4:v4.36.0-rc1\n"),
                         "https://cache.taucetiproject.org/revisions/TauCetiProject/TauCeti/tc/"
                         "leanprover--lean4---v4.36.0-rc1/abc.jsonl")


if __name__ == "__main__":
    unittest.main()
