import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import prune  # noqa: E402

NOW = datetime(2026, 11, 30, tzinfo=timezone.utc)
RELEASES = [("dataset-aaaaaaaaaaaa", "2026-10-01T06:00:00Z"), ("dataset-bbbbbbbbbbbb", "2026-10-15T06:00:00Z"),
            ("dataset-cccccccccccc", "2026-11-20T06:00:00Z"), ("v1.0", "2026-01-01T00:00:00Z"),
            ("dataset-dddddddddddd", "2026-09-01T00:00:00Z")]


class PruneTests(unittest.TestCase):
    def test_datasets_older_than_the_limit_go_oldest_first(self):
        self.assertEqual(prune.to_delete(RELEASES, set(), NOW, 30),
                         ["dataset-dddddddddddd", "dataset-aaaaaaaaaaaa", "dataset-bbbbbbbbbbbb"])

    def test_the_newest_stays_however_old(self):
        self.assertEqual(prune.to_delete([("dataset-aaaaaaaaaaaa", "2026-01-01T00:00:00Z")], set(), NOW, 30), [])

    def test_a_dataset_an_open_issue_names_stays(self):
        self.assertEqual(prune.to_delete(RELEASES, {"bbbbbbbbbbbb1234", "aaaaaaa"}, NOW, 30),
                         ["dataset-dddddddddddd"])

    def test_the_commits_issue_bodies_name(self):
        bodies = ["### Declaration\n\nTauCeti.foo\n\n### Commit\n\nbbbbbbbbbbbb1234567890\n\n### Why\n\nx",
                  "### Commit\n\n_No response_\n", None]
        self.assertEqual(prune.named_commits(bodies), {"bbbbbbbbbbbb1234567890"})


if __name__ == "__main__":
    unittest.main()
