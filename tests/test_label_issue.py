import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import yaml
from evidence_store import forms

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import label_issue  # noqa: E402

TEMPLATES = HERE.parent / ".github" / "ISSUE_TEMPLATE"
FORMS = label_issue.template_forms(TEMPLATES) + label_issue.cli_forms()


def site_body(fields: list[tuple[str, str]]) -> str:
    """An issue's body as the site writes it (web/render.js, issueBody): the form's fields, in order."""
    return "\n\n".join(f"### {label}\n\n{value or '_No response_'}" for label, value in fields) + "\n"


class TemplateFormsTests(unittest.TestCase):
    def test_read_as_yaml_reads_them(self):
        want = []
        for f in sorted(TEMPLATES.glob("*.yml")):
            t = yaml.safe_load(f.read_text(encoding="utf-8"))
            if "title" in t:
                first = next(b for b in t["body"] if b["type"] != "markdown")
                want.append((t["title"], t["labels"][0], first["attributes"]["label"]))
        self.assertEqual(label_issue.template_forms(TEMPLATES), want)
        self.assertEqual(len(want), 7)

    def test_and_evidence_stores_own(self):
        self.assertIn(("Review: ", "evidence:review", "Declaration"), label_issue.cli_forms())
        self.assertIn(("Status: ", "evidence:status", "Record"), label_issue.cli_forms())


class LabelForTests(unittest.TestCase):
    def issue(self, title, body, labels=()):
        return {"number": 7, "title": title, "body": body, "labels": [{"name": l} for l in labels]}

    def test_what_the_site_files(self):
        decl = [("Declaration", "TauCeti.Foo.bar"), ("Commit", "abc123")]
        cases = {"Correctly stated: ": ("evidence:review", [("Why", "")]),
                 "Not correctly stated: ": ("evidence:problem", [("Why", "It is the wrong object.")]),
                 "What could be better: ": ("evidence:question", [("Question", "State it for any semiring.")]),
                 "Suggested test: ": ("evidence:challenge", [("What it should satisfy", "its value at 0"),
                                                              ("As a Lean statement", ""), ("What it would catch", "")])}
        for prefix, (label, rest) in cases.items():
            self.assertEqual(label_issue.label_for(self.issue(prefix + "TauCeti.Foo.bar", site_body(decl + rest)), FORMS),
                             label, prefix)

    def test_what_evidence_store_files(self):
        body = forms.body("review", {"decl": "TauCeti.Foo.bar", "commit": "abc123", "who": "agent",
                                     "agent": "Codex, GPT-6 Astra", "rationale": "Matches Stacks 0BSC."})
        self.assertEqual(label_issue.label_for(self.issue("Review: TauCeti.Foo.bar", body), FORMS), "evidence:review")
        status = forms.body("status", {"record": "0123456789abcdef", "action": "withdraw"})
        self.assertEqual(label_issue.label_for(self.issue("Status: withdraw", status), FORMS), "evidence:status")

    def test_not_what_has_its_label_or_is_no_form(self):
        body = site_body([("Declaration", "TauCeti.Foo.bar"), ("Commit", "abc123"), ("Why", "")])
        self.assertIsNone(label_issue.label_for(self.issue("Correctly stated: TauCeti.Foo.bar", body, ["evidence:review"]), FORMS))
        self.assertIsNone(label_issue.label_for(self.issue("Correctly stated: TauCeti.Foo.bar", body, ["evidence:problem"]), FORMS),
                          "any form's label: intake reads that one")
        self.assertIsNone(label_issue.label_for(self.issue("Question: why this convention?", "Why is it defined so?"), FORMS),
                          "a person's own issue, which only looks like a form's title")
        self.assertIsNone(label_issue.label_for(self.issue("A typo on the page", body), FORMS))
        self.assertIsNone(label_issue.label_for({**self.issue("Correctly stated: X", body), "pull_request": {}}, FORMS))

    def test_other_labels_do_not_matter(self):
        body = site_body([("Declaration", "TauCeti.Foo.bar"), ("Commit", "abc123"), ("Why", "")])
        self.assertEqual(label_issue.label_for(self.issue("Correctly stated: TauCeti.Foo.bar", body.replace("\n", "\r\n"), ["bug"]), FORMS),
                         "evidence:review")


class MainTests(unittest.TestCase):
    def test_a_dry_run_says_the_label(self):
        body = site_body([("Declaration", "TauCeti.Foo.bar"), ("Commit", "abc123"), ("Why", "It is the wrong object.")])
        with tempfile.TemporaryDirectory() as tmp:
            event = Path(tmp) / "event.json"
            event.write_text(json.dumps({"action": "opened", "issue": {"number": 9, "title": "Not correctly stated: TauCeti.Foo.bar",
                                                                       "body": body, "labels": []}}))
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(label_issue.main(["--event", str(event), "--repo", "o/r", "--dry-run"]), 0)
        self.assertEqual(out.getvalue(), "evidence:problem\n")


if __name__ == "__main__":
    unittest.main()
