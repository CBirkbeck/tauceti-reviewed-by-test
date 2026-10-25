#!/usr/bin/env python3
"""Gives an issue the label of the form it was written with, when GitHub dropped it.

Intake reads an issue's form from its label. An answer sent on GitHub from the site's page comes without
one: it opens a plain new issue with the answer written in it, not the form (render.js, `URLS.form`). And
GitHub drops the labels of an issue opened through its API by an account that may not set labels, which is
anyone not a collaborator: so an answer filed from the site's page by a signed-in reader (web/signin.js)
comes without one, and so does an AI agent's from `evidence-store submit` under such an account. All title
the issue as their form does (the site as
.github/ISSUE_TEMPLATE's forms, evidence-store as its own) and write its fields as `### <label>` sections.
An issue with no form's label, whose title starts as a form's does and whose body has that form's first
field, gets that form's label.

  python3 scripts/label_issue.py --event PATH --repo OWNER/NAME [--templates DIR] [--dry-run]

Prints the label it added, if any, and then writes `labelled=true` to $GITHUB_OUTPUT.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / ".github" / "ISSUE_TEMPLATE"


def template_forms(templates: Path) -> list[tuple[str, str, str]]:
    """(title, label, first field's label) of each issue form. The forms write their values as JSON strings,
    as evidence-store generates them, which YAML reads alike: read with a pattern, no YAML library needed."""
    out = []
    for f in sorted(templates.glob("*.yml")):
        text = f.read_text(encoding="utf-8")
        title = re.search(r'^title:\s*(".*")\s*$', text, re.M)
        labels = re.search(r"^labels:\s*(\[.*\])\s*$", text, re.M)
        first = re.search(r'^\s+id:\s*\S+\s*\n\s+attributes:\s*\n\s+label:\s*(".*")\s*$', text, re.M)
        if title and labels and first and json.loads(labels.group(1)):
            out.append((json.loads(title.group(1)), json.loads(labels.group(1))[0], json.loads(first.group(1))))
    return out


def cli_forms() -> list[tuple[str, str, str]]:
    """The same of the forms `evidence-store` opens issues with, where it is installed."""
    try:
        from evidence_store.forms import FORMS
    except ImportError:
        return []
    return [(f["title"], f["label"], f["fields"][0]["label"]) for f in FORMS.values()]


def label_for(issue: dict, forms: list[tuple[str, str, str]]) -> str | None:
    """The label an issue lacks, if it was written with one of `forms` and has none of their labels."""
    have = {(l.get("name") if isinstance(l, dict) else l) for l in issue.get("labels") or []}
    if issue.get("pull_request") is not None or have & {label for _, label, _ in forms}:
        return None
    title, body = issue.get("title") or "", (issue.get("body") or "").replace("\r\n", "\n")
    for prefix, label, first in sorted(forms, key=lambda f: -len(f[0])):
        if title.startswith(prefix.rstrip()) and re.search(rf"^###\s+{re.escape(first)}\s*$", body, re.M):
            return label
    return None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="label_issue.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--event", type=Path, required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--templates", type=Path, default=TEMPLATES)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    issue = json.loads(a.event.read_text(encoding="utf-8")).get("issue") or {}
    label = label_for(issue, template_forms(a.templates) + cli_forms())
    if not label:
        return 0
    print(label)
    if a.dry_run:
        return 0
    subprocess.run(["gh", "issue", "edit", str(issue["number"]), "-R", a.repo, "--add-label", label],
                   check=True, stdin=subprocess.DEVNULL)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
            out.write("labelled=true\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
