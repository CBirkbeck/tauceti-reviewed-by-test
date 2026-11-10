import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import dataset_commit  # noqa: E402

A, B, C = "a" * 40, "b" * 12 + "1" * 28, "c" * 40
RELEASES = [(f"dataset-{A[:12]}", f"Dataset for Tau Ceti {A}", "2026-11-07T06:00:00Z"),
            (f"dataset-{B[:12]}", f"Dataset for Tau Ceti {B}", "2026-11-08T16:00:00Z"),
            ("v1.0", "A release that is no dataset", "2026-11-09T00:00:00Z")]


class DatasetCommitTests(unittest.TestCase):
    def test_the_pin_when_its_dataset_is_published(self):
        self.assertEqual(dataset_commit.choose(A, RELEASES), A)

    def test_the_newest_published_when_the_pins_is_not(self):
        self.assertEqual(dataset_commit.choose(C, RELEASES), B)

    def test_none_when_no_dataset_is_published(self):
        self.assertIsNone(dataset_commit.choose(C, [RELEASES[2]]))

    def test_a_title_that_names_another_commit_is_passed_over(self):
        odd = (f"dataset-{C[:12]}", f"Dataset for Tau Ceti {A}", "2026-11-09T06:00:00Z")
        self.assertEqual(dataset_commit.choose("d" * 40, RELEASES + [odd]), B)


if __name__ == "__main__":
    unittest.main()
