#!/usr/bin/env python3
"""evidence-store's command line, with one more sweep for its intake: the evidence issues still open.

Intake reads the issue its event names, and with `--sweep-days N` every evidence issue updated in the
last N days, for those whose own run was dropped: GitHub keeps one waiting run of a workflow, so a burst
of issues drops the runs of all but the last. On 2026-10-28 the last 14 days held some 900 evidence
issues, and each run spent twenty minutes or more reading them, three requests apiece. Anything pushed
to the branch meanwhile made it read them all again, and the issues waited open.

An issue whose run was dropped is still open: intake closes a review, test or named result once it is
recorded, and a problem, question or challenge stays open until it is settled, so it is read again
anyway. `--sweep-open` reads the event's own issue and the open evidence issues, the bulk issue among
them. Only a comment on a closed issue whose run was dropped waits, until the six-hourly sweep of the
last 14 days (.github/actions/intake).

  python3 scripts/evidence_intake.py intake --repo OWNER/NAME --outcome FILE [--event PATH --event-name NAME] --sweep-open

Everything else is evidence-store's own: `python3 scripts/evidence_intake.py X` is `evidence-store X`.
"""
from __future__ import annotations

import sys

from evidence_store import cli, github
from evidence_store.forms import FORMS
from evidence_store.intake import BULK_LABEL


def open_issues(repo: str, since: str = "") -> list[dict]:
    """The open issues of the store's forms, and the bulk issue: in place of `github.recent_issues`,
    whose `since` it does not need."""
    out, seen = [], set()
    for label in [f["label"] for f in FORMS.values()] + [BULK_LABEL]:
        for i in github.gh_json("api", "--paginate", f"repos/{repo}/issues?state=open&labels={label}&per_page=100") or []:
            if i["number"] not in seen and not i.get("pull_request"):
                seen.add(i["number"])
                out.append(i)
    return sorted(out, key=lambda i: i["number"])


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--sweep-open" in argv:
        argv.remove("--sweep-open")
        github.recent_issues = open_issues
        argv += ["--sweep-days", "1"]  # intake sweeps only with a number of days; which issues is recent_issues'
    return cli.main(argv)


if __name__ == "__main__":
    sys.exit(main())
