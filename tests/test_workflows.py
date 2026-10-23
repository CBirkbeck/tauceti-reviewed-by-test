import unittest
from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def load(name: str) -> dict:
    wf = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    wf["on"] = wf.get("on", wf.get(True))  # YAML 1.1 reads the key `on` as True
    return wf


def steps(job: dict) -> list[dict]:
    return job.get("steps", [])


def runs(job: dict) -> str:
    return "\n".join(s.get("run", "") for s in steps(job))


class DatasetWorkflowTests(unittest.TestCase):
    def test_dataset_extracts_with_the_pinned_series_and_publishes(self):
        wf = load("dataset.yml")
        self.assertIn("workflow_call", wf["on"])
        self.assertIn("workflow_dispatch", wf["on"])
        job = wf["jobs"]["extract"]
        self.assertTrue(any(s.get("uses", "").startswith("astral-sh/setup-uv@") for s in steps(job)),
                        "Tau Ceti's lake-cache-get.sh runs uvx")
        text = runs(job)
        self.assertIn("scripts/extractor.py install", text)
        for arg in ("--parts 8", "--jobs 1", "--skip-modules-file", "--no-statements", "--no-signatures",
                    "--no-upstream-docs"):
            self.assertIn(arg, text)
        self.assertIn('gh release create "$TAG"', text)

    def test_follow_pins_extracts_and_prunes(self):
        wf = load("follow.yml")
        self.assertEqual(wf["on"]["schedule"], [{"cron": "40 5 * * *"}])
        jobs = wf["jobs"]
        self.assertIn("python3 scripts/pin.py", runs(jobs["pin"]))
        self.assertEqual(jobs["dataset"]["uses"], "./.github/workflows/dataset.yml")
        self.assertIn("python3 scripts/prune.py", runs(jobs["prune"]))

    def test_every_checkout_takes_the_tip_of_the_branch(self):
        for f in sorted(WORKFLOWS.glob("*.yml")):
            if f.name.startswith("evidence-"):
                continue  # evidence-store's, generated
            for name, job in load(f.name)["jobs"].items():
                for s in steps(job):
                    if s.get("uses", "").startswith("actions/checkout@"):
                        self.assertEqual((s.get("with") or {}).get("ref"), "${{ github.ref }}", f"{f.name}: {name}")


class VoyagerWorkflowTests(unittest.TestCase):
    def test_reads_twice_a_day_and_records(self):
        wf = load("voyager.yml")
        self.assertEqual(wf["on"]["schedule"], [{"cron": "15 4,16 * * *"}])
        self.assertEqual(wf["on"]["workflow_call"]["inputs"]["site"]["default"], True)
        self.assertEqual(wf["on"]["workflow_call"]["outputs"]["recorded"]["value"], "${{ jobs.named.outputs.recorded }}")
        job = wf["jobs"]["named"]
        text = runs(job)
        self.assertIn("python3 scripts/voyager.py fetch", text)
        self.assertIn('python3 scripts/voyager.py record --dataset "$RUNNER_TEMP/dataset"', text)
        env = next(s for s in steps(job) if s.get("id") == "record")["env"]
        self.assertEqual(env["ZULIP_API_KEY"], "${{ secrets.ZULIP_API_KEY }}")

    def test_follow_records_after_a_new_dataset(self):
        named = load("follow.yml")["jobs"]["named"]
        self.assertEqual(named["uses"], "./.github/workflows/voyager.yml")
        self.assertEqual(named["with"], {"site": False})
        self.assertEqual(named["secrets"], "inherit")


class PagesWorkflowTests(unittest.TestCase):
    def test_builds_checks_and_publishes_from_main_only(self):
        wf = load("pages.yml")
        for trigger in ("push", "workflow_dispatch", "workflow_call"):
            self.assertIn(trigger, wf["on"])
        text = runs(wf["jobs"]["build"])
        for command in ("python -m unittest discover -s tests", "python tests/validate_site.py",
                        "python scripts/build_site.py", "python tests/validate_site.py --site _site --smoke"):
            self.assertIn(command, text)
        self.assertEqual(wf["jobs"]["deploy"]["if"], "github.ref == 'refs/heads/main' && inputs.deploy != false")

    def test_follow_and_voyager_rebuild_the_site(self):
        self.assertEqual(load("follow.yml")["jobs"]["site"]["uses"], "./.github/workflows/pages.yml")
        self.assertEqual(load("voyager.yml")["jobs"]["site"]["uses"], "./.github/workflows/pages.yml")

    def test_intake_rebuilds_the_site(self):
        intake = load("evidence-intake.yml")["jobs"]["intake"]
        self.assertEqual(next(s for s in steps(intake) if "evidence-store/intake" in s.get("uses", ""))["with"]["pages-workflow"],
                         "pages.yml")


if __name__ == "__main__":
    unittest.main()
