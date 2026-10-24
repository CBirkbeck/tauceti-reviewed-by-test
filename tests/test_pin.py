import base64
import sys
import unittest
from pathlib import Path
from unittest import mock

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

    def run_main(self, pinned: str, docs_runs: list):
        """pin.main() against a fake GitHub: the docgen branch (at the head of ``docs_runs``' first, or
        unreadable when there is none), two commits from d2 back, and main.
        Returns (what it printed, the pin it saved, the API paths it read)."""
        settings = {"tauceti": pinned, "library": {"repo": "o/r", "docs_branch": "docgen"},
                    "extractor": {"repo": "x/e", "series": "0.13"}}
        paths, saved, printed = [], {}, []

        def gh(path):
            paths.append(path)
            if path == "repos/o/r/branches/docgen":
                if not docs_runs:
                    raise pin.subprocess.CalledProcessError(1, "gh")
                return {"commit": {"sha": docs_runs[0]["head_sha"]}}
            if path.startswith("repos/o/r/commits?sha=d2"):
                return [{"sha": "d2"}, {"sha": "d1"}]
            if path.startswith("repos/o/r/commits?sha=main"):
                return [{"sha": "m9"}]
            if "lean-toolchain" in path:
                return {"content": base64.b64encode(b"leanprover/lean4:v4.36.0-rc1\n").decode()}
            raise AssertionError(path)
        with mock.patch.object(pin, "load_settings", return_value=settings), \
             mock.patch.object(pin, "save_settings", side_effect=saved.update), \
             mock.patch.object(pin, "release_tags", return_value=TAGS), \
             mock.patch.object(pin, "gh_json", side_effect=gh), \
             mock.patch.object(pin, "cached_in", return_value=lambda sha, text: True), \
             mock.patch("builtins.print", side_effect=lambda *a, **k: printed.append(a[0] if a else "")):
            pin.main()
        return printed, saved.get("tauceti"), paths

    def test_the_pin_follows_the_docs(self):
        printed, pinned, paths = self.run_main("old", [{"head_sha": "d2"}])
        self.assertEqual((pinned, printed[-1]), ("d2", "moved=true"))
        self.assertEqual(sum("lean-toolchain" in p for p in paths), 1)  # read as needed: the first fits

    def test_nothing_moves_while_the_docs_show_the_pin(self):
        printed, pinned, paths = self.run_main("d2", [{"head_sha": "d2"}])
        self.assertEqual((pinned, printed[-1]), (None, "moved=false"))
        self.assertFalse(any("commits?" in p for p in paths))  # one request, and done

    def test_main_when_there_are_no_docs_to_follow(self):
        printed, pinned, _ = self.run_main("old", [])
        self.assertEqual((pinned, printed[-1]), ("m9", "moved=true"))

    def test_the_cache_is_asked_with_a_user_agent(self):
        # The cache's server refuses Python's default User-Agent: 403 for every commit.
        seen = []

        class Answer:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake(req, timeout):
            seen.append(req)
            return Answer()
        with mock.patch.object(pin.urllib.request, "urlopen", fake):
            self.assertTrue(pin.cached_in("TauCetiProject/TauCeti")("abc", "leanprover/lean4:v4.36.0-rc1\n"))
        self.assertEqual(seen[0].get_method(), "HEAD")
        self.assertTrue(seen[0].get_header("User-agent", "").startswith("tauceti-review"))

    def test_the_cache_address(self):
        self.assertEqual(pin.cache_url("TauCetiProject/TauCeti", "abc", "leanprover/lean4:v4.36.0-rc1\n"),
                         "https://cache.taucetiproject.org/revisions/TauCetiProject/TauCeti/tc/"
                         "leanprover--lean4---v4.36.0-rc1/abc.jsonl")


if __name__ == "__main__":
    unittest.main()
