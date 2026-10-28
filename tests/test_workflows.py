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


LEVELS = {"none": 0, "read": 1, "write": 2}


def asked(wf: dict) -> dict[str, int]:
    """The most a workflow asks of its token for each scope, at the top or in any of its jobs."""
    out: dict[str, int] = {}
    for block in [wf.get("permissions")] + [job.get("permissions") for job in wf["jobs"].values()]:
        for scope, level in (block or {}).items():
            out[scope] = max(out.get(scope, 0), LEVELS[level])
    return out


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

    def test_the_statements_come_from_the_docs_before_the_check_and_the_publishing(self):
        names = [s.get("name", "") for s in steps(load("dataset.yml")["jobs"]["extract"])]
        text = [s.get("run", "") for s in steps(load("dataset.yml")["jobs"]["extract"])]
        at = lambda command: next(i for i, t in enumerate(text) if command in t)  # noqa: E731
        self.assertIn('python3 scripts/docs_signatures.py --dataset "$RUNNER_TEMP/dataset" --source "$RUNNER_TEMP/TauCeti"',
                      text[at("scripts/docs_signatures.py")])
        self.assertLess(at('"$EXTRACTOR_BIN" extract'), at("scripts/docs_signatures.py"))
        self.assertLess(at("scripts/docs_signatures.py"), at("scripts/check_signatures.py"))
        self.assertLess(at("scripts/docs_signatures.py"), names.index("Publish"))

    def test_follow_pins_extracts_and_prunes(self):
        wf = load("follow.yml")
        self.assertEqual(wf["on"]["schedule"], [{"cron": "*/20 * * * *"}])  # has docgen moved?
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
        self.assertIn("needs.pin.outputs.moved == 'true'", named["if"])  # not every hour: only after a new dataset
        jobs = load("follow.yml")["jobs"]
        for name in ("named", "prune", "site"):  # a cancelled run stops: no site without its dataset
            self.assertTrue(jobs[name]["if"].startswith("!cancelled()"), name)
        self.assertIn("needs.dataset.result == 'success' || needs.dataset.result == 'skipped'", jobs["site"]["if"])
        self.assertEqual(named["with"], {"site": False})
        self.assertEqual(named["secrets"], "inherit")


class PermissionTests(unittest.TestCase):
    def test_a_called_workflow_is_granted_what_it_asks_for(self):
        # GitHub refuses to start a run whose called workflow asks for more than the calling job grants
        # (`startup_failure`, no job runs): on 2026-10-25 dataset.yml asked for issues: write while
        # follow.yml's dataset job granted only contents, and the site stopped following Tau Ceti.
        for f in sorted(WORKFLOWS.glob("*.yml")):
            wf = load(f.name)
            for name, job in wf["jobs"].items():
                called = job.get("uses", "")
                if not called.startswith("./.github/workflows/"):
                    continue
                granted = job.get("permissions", wf.get("permissions"))
                if granted is None:
                    continue  # the repository's default token, which the files do not say
                for scope, level in asked(load(Path(called).name)).items():
                    self.assertGreaterEqual(LEVELS[granted.get(scope, "none")], level,
                                            f"{f.name}: {name} calls {called}, which asks for {scope}")


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
        self.assertEqual(intake_step(intake)["with"]["pages-workflow"], "pages.yml")


ACTIONS = WORKFLOWS.parent / "actions"


def intake_step(job: dict) -> dict:
    return next(s for s in steps(job) if s.get("uses") == "./.github/actions/intake")


class IntakeTests(unittest.TestCase):
    def test_an_event_reads_the_open_issues_and_the_schedule_the_last_14_days(self):
        wf = load("evidence-intake.yml")
        self.assertEqual(wf["on"]["schedule"], [{"cron": "23 */6 * * *"}])
        self.assertIn("workflow_dispatch", wf["on"])  # a run by hand reads what is open, as an event's does
        self.assertEqual(intake_step(wf["jobs"]["intake"])["with"]["sweep"],
                         "${{ github.event_name == 'schedule' && '--sweep-days 14' || '--sweep-open' }}")

    def test_the_action_is_evidence_stores_with_that_sweep(self):
        action = yaml.safe_load((ACTIONS / "intake" / "action.yml").read_text(encoding="utf-8"))
        self.assertEqual(action["runs"]["using"], "composite")
        self.assertEqual(action["inputs"]["sweep"]["default"], "--sweep-days 14")
        self.assertEqual(intake_step(load("evidence-intake.yml")["jobs"]["intake"])["with"]["ref"], "v0.7.2")
        named = {s.get("name"): s for s in action["runs"]["steps"]}
        self.assertEqual(named["evidence-store"]["run"],
                         'pip install -q "git+https://github.com/LeanTrustBuilders/evidence-store@${{ inputs.ref }}"')
        push = named["Read issues and comments, and commit the records"]
        self.assertEqual(push["env"]["SWEEP"], "${{ inputs.sweep }}")
        self.assertIn("python scripts/evidence_intake.py intake", push["run"])
        self.assertIn("$SWEEP --outcome", push["run"])
        self.assertIn("python scripts/evidence_intake.py apply", named["Reply on the issues"]["run"])
        self.assertIn('gh workflow run "${{ inputs.pages-workflow }}"', named["Rebuild the page"]["run"])


class LabelWorkflowTests(unittest.TestCase):
    def test_labels_what_lost_its_label_then_reads_it_as_intake_does(self):
        wf = load("label.yml")
        self.assertEqual(wf["on"], {"issues": {"types": ["opened"]}})
        self.assertEqual(wf["permissions"], {"contents": "write", "issues": "write", "actions": "write"})
        job = wf["jobs"]["label"]
        self.assertIn("github.event.sender.type != 'Bot'", job["if"])  # as intake: not the bot's own
        label = next(s for s in steps(job) if s.get("id") == "label")
        self.assertIn("pip install -q -r requirements.txt", label["run"])  # evidence-store's own titles too
        self.assertIn('python scripts/label_issue.py --event "$GITHUB_EVENT_PATH" --repo "$GITHUB_REPOSITORY"', label["run"])
        mine, theirs = intake_step(job), intake_step(load("evidence-intake.yml")["jobs"]["intake"])
        self.assertEqual(mine["if"], "steps.label.outputs.labelled == 'true'")
        self.assertEqual((mine["uses"], mine["with"]), (theirs["uses"], theirs["with"]), "the same intake, pinned alike")



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

    def test_one_question_yes_or_no(self):
        # The yes asks nothing more; the no asks why, and will not go without it.
        forms = dict(self.templates())
        fields = lambda name: [(f["id"], bool(f.get("validations", {}).get("required")))
                               for f in forms[name]["body"] if f["type"] != "markdown"]
        self.assertEqual(fields("evidence-review.yml"), [("decl", True), ("commit", False), ("rationale", False)])
        self.assertEqual(fields("evidence-problem.yml"), [("decl", True), ("commit", False), ("rationale", True)])
        self.assertEqual((forms["evidence-review.yml"]["labels"], forms["evidence-problem.yml"]["labels"]),
                         (["evidence:review"], ["evidence:problem"]))
        # What could be better: a suggestion, on the question form, required.
        self.assertEqual(fields("evidence-question.yml"), [("decl", True), ("commit", False), ("question", True)])
        self.assertEqual(forms["evidence-question.yml"]["name"], "What could be better")
        # Suggest a test: the property it should have, required; the rest optional.
        self.assertEqual(fields("evidence-challenge.yml"), [("decl", True), ("commit", False), ("property", True),
                                                            ("statement", False), ("catches", False)])
        self.assertEqual(forms["evidence-challenge.yml"]["name"], "Suggest a test")

    def test_a_no_from_the_form_says_why(self):
        from evidence_store import forms
        t = dict(self.templates())["evidence-problem.yml"]
        answers = {"decl": "Fixture.triple_comm", "commit": "B", "rationale": "It states the definition, unfolded."}
        body = "\n\n".join(f"### {f['attributes']['label']}\n\n{answers[f['id']]}" for f in t["body"] if f["type"] != "markdown")
        self.assertEqual(forms.parse("problem", body), answers)  # no category: intake records "other"

    def test_a_review_from_the_form_is_a_persons(self):
        from evidence_store import forms, intake
        t = dict(self.templates())["evidence-review.yml"]
        answers = {"decl": "Fixture.triple", "rationale": "Compared with its definition."}
        body = "\n\n".join(f"### {f['attributes']['label']}\n\n{answers.get(f['id'], '_No response_')}"
                           for f in t["body"] if f["type"] != "markdown")
        read = forms.parse("review", body)
        self.assertEqual(read, answers)  # the yes, and why: nothing else to tick or choose
        self.assertEqual(intake.author_of({"login": "someone"}, None, read.get("involvement") or "unknown")["kind"], "person")


if __name__ == "__main__":
    unittest.main()
