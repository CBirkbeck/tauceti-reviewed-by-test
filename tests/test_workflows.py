import unittest
from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
TEMPLATES = Path(__file__).resolve().parents[1] / ".github" / "ISSUE_TEMPLATE"


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
        for arg in ("--parts 8", "--jobs 1", "--skip-modules-file", "--no-statements", "--no-upstream-docs"):
            self.assertIn(arg, text)
        # The signature, as the docs show it (section variables included), is what a declaration's page shows.
        self.assertNotIn("--no-signatures", text)
        self.assertIn('gh release create "$TAG"', text)
        self.assertIn('gh release upload "$TAG"', text)  # replacing the dataset of a commit
        self.assertEqual(wf["on"]["workflow_dispatch"]["inputs"]["replace"]["type"], "boolean")

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


class ConditionTests(unittest.TestCase):
    def test_no_input_is_compared_with_false(self):
        # GitHub compares loosely: an input a trigger does not give is null, and null == false (both
        # become 0), so `inputs.x != false` is false on a push or a schedule. Compare strings instead.
        for f in sorted(WORKFLOWS.glob("*.yml")):
            for name, job in load(f.name)["jobs"].items():
                cond = str(job.get("if", ""))
                self.assertNotRegex(cond, r"inputs\.\w+\s*[!=]=\s*false", f"{f.name}: {name}")


class PagesWorkflowTests(unittest.TestCase):
    def test_builds_checks_and_publishes_from_main_only(self):
        wf = load("pages.yml")
        for trigger in ("push", "workflow_dispatch", "workflow_call"):
            self.assertIn(trigger, wf["on"])
        text = runs(wf["jobs"]["build"])
        for command in ("python -m unittest discover -s tests", "python tests/validate_site.py",
                        "python scripts/build_site.py", "python tests/validate_site.py --site _site --smoke"):
            self.assertIn(command, text)
        self.assertEqual(wf["jobs"]["deploy"]["if"], "github.ref == 'refs/heads/main' && format('{0}', inputs.deploy) != 'false'")

    def test_follow_and_voyager_rebuild_the_site(self):
        self.assertEqual(load("follow.yml")["jobs"]["site"]["uses"], "./.github/workflows/pages.yml")
        self.assertEqual(load("voyager.yml")["jobs"]["site"]["uses"], "./.github/workflows/pages.yml")

    def test_intake_rebuilds_the_site(self):
        intake = load("evidence-intake.yml")["jobs"]["intake"]
        self.assertEqual(next(s for s in steps(intake) if "evidence-store/intake" in s.get("uses", ""))["with"]["pages-workflow"],
                         "pages.yml")



class FormTests(unittest.TestCase):
    """The forms are evidence-store's, less what only an AI agent would answer: what is left must still
    read as intake reads it, by label, and a form says nothing of who wrote it, so intake records a person."""

    def templates(self):
        for f in sorted(TEMPLATES.glob("evidence-*.yml")):
            yield f.name, yaml.safe_load(f.read_text(encoding="utf-8"))

    def test_each_field_is_one_intake_knows(self):
        from evidence_store import forms
        for name, t in self.templates():
            kind = forms.kind_of(t["labels"])
            self.assertIsNotNone(kind, name)
            known = {f["label"]: f for f in forms.forms()[kind]["fields"]}
            for f in (f for f in t["body"] if f["type"] != "markdown"):
                label = f["attributes"]["label"]
                self.assertIn(label, known, name)
                self.assertEqual(f["id"], known[label]["id"], name)
                if f["type"] == "dropdown":
                    self.assertEqual(f["attributes"]["options"], [text for _, text in known[label]["options"]], name)

    def test_no_form_asks_who_wrote_it(self):
        for name, t in self.templates():
            ids = {f.get("id") for f in t["body"]}
            self.assertFalse(ids & {"involvement", "who", "agent"}, name)
            self.assertNotIn("AI agent", yaml.safe_dump(t["body"], allow_unicode=True), name)

    def test_a_review_from_the_form_is_a_persons(self):
        from evidence_store import forms, intake
        t = dict(self.templates())["evidence-review.yml"]
        answers = {"decl": "Fixture.triple", "rationale": "Compared with its definition."}
        body = "\n\n".join(f"### {f['attributes']['label']}\n\n{answers.get(f['id'], '_No response_')}"
                           for f in t["body"] if f["type"] != "markdown")
        read = forms.parse("review", body)
        self.assertEqual(read, {**answers, "checked": {}})  # nothing ticked
        self.assertEqual(intake.author_of({"login": "someone"}, None, read.get("involvement") or "unknown")["kind"], "person")


if __name__ == "__main__":
    unittest.main()
