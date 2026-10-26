import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from answerer.prepare import Paths, fetch_dataset, site_commit  # noqa: E402

SETTINGS = {"tauceti": "c0ffee0000000000000000000000000000000000",
            "site": {"url": "https://example.org/review/"}}


class SiteCommitTests(unittest.TestCase):
    """The commit a run works at is the one the site shows: the pin moves first, when a new dataset is
    being extracted, and that dataset is published only some forty minutes later (2026-10-26)."""

    def test_the_commit_the_site_shows(self):
        asked = []
        shown = "5eed000000000000000000000000000000000000"
        got = site_commit(SETTINGS, fetch=lambda url: asked.append(url) or {"library": {"commit": shown}})
        self.assertEqual((got, asked), (shown, ["https://example.org/review/data/meta.json"]))

    def test_the_pin_when_the_site_cannot_be_read(self):
        def fetch(url):
            raise OSError("no connection")
        self.assertEqual(site_commit(SETTINGS, fetch=fetch), SETTINGS["tauceti"])


class FetchDatasetTests(unittest.TestCase):
    """A download that failed left an empty folder, which every later run took for the dataset and failed
    on (from 2026-10-25 14:02): a dataset is there only with its meta.json, and a download lands whole."""

    def setUp(self):
        self.p = Paths(Path(tempfile.mkdtemp()))
        (self.p.review / "evidence").mkdir(parents=True)
        self.calls = []

    def download(self, argv, cwd=None, timeout=3600):
        self.calls.append(argv)
        out = Path(argv[argv.index("--out") + 1])
        out.mkdir(parents=True)
        (out / "meta.json").write_text("{}", encoding="utf-8")
        return ""

    def test_an_empty_folder_is_fetched_again(self):
        (self.p.datasets / "c0ffee000000").mkdir(parents=True)
        got = fetch_dataset(self.p, SETTINGS["tauceti"], run=self.download)
        self.assertEqual(len(self.calls), 1)
        self.assertTrue((got / "meta.json").exists())
        self.assertEqual(got, self.p.datasets / "c0ffee000000")

    def test_a_dataset_there_is_kept(self):
        d = self.p.datasets / "c0ffee000000"
        d.mkdir(parents=True)
        (d / "meta.json").write_text("{}", encoding="utf-8")
        self.assertEqual(fetch_dataset(self.p, SETTINGS["tauceti"], run=self.download), d)
        self.assertEqual(self.calls, [])

    def test_a_failed_download_leaves_nothing(self):
        def fail(argv, cwd=None, timeout=3600):
            out = Path(argv[argv.index("--out") + 1])
            out.mkdir(parents=True)  # as evidence-store does before it fails
            raise subprocess.CalledProcessError(1, argv)
        with self.assertRaises(subprocess.CalledProcessError):
            fetch_dataset(self.p, SETTINGS["tauceti"], run=fail)
        self.assertEqual([x.name for x in self.p.datasets.iterdir()], [])  # so the next run fetches it again


if __name__ == "__main__":
    unittest.main()
