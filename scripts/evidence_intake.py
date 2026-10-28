#!/usr/bin/env python3
"""evidence-store's command line, with one more sweep for its intake, the evidence issues still open, and
replies that outlast GitHub's limits.

Intake reads the issue its event names, and with `--sweep-days N` every evidence issue updated in the
last N days, for those whose own run was dropped: GitHub keeps one waiting run of a workflow, so a burst
of issues drops the runs of all but the last. On 2026-10-28 the last 14 days held some 900 evidence
issues, and each run spent twenty minutes or more reading them, three requests apiece. Anything pushed
to the branch meanwhile made it read them all again, and the issues waited open.

An issue whose run was dropped is still open: intake closes a review, test or named result once it is
recorded, and a problem, question or challenge stays open until it is settled, so it is read again
anyway. `--sweep-open` reads the event's own issue and the evidence issues still open, the bulk issue
among them. Only a comment on a closed issue whose run was dropped waits, until the six-hourly sweep of
the last 14 days (.github/actions/intake).

Intake commits the records first and replies after. GitHub lets an account post some 500 comments an
hour, and evidence-store's `apply` stops at the first reply it refuses, before closing anything; intake,
which has the records, never answers those issues again. So `apply` here goes issue by issue and leaves
an issue whose reply was refused open, and the open sweep finishes what an earlier run left undone
(`unfinished`).

  python3 scripts/evidence_intake.py intake --repo OWNER/NAME --outcome FILE [--event PATH --event-name NAME] --sweep-open
  python3 scripts/evidence_intake.py apply --repo OWNER/NAME --outcome FILE

Everything else is evidence-store's own: `python3 scripts/evidence_intake.py X` is `evidence-store X`.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Callable

from evidence_core.store import Store
from evidence_store import cli, github, intake
from evidence_store.forms import FORMS
from evidence_store.intake import BULK_LABEL

#: What GitHub says when it refuses for a while: the secondary limit on comments, or the hourly one.
LIMITED = re.compile(r"rate limit", re.I)
#: The records whose issue intake closes once it has recorded them (evidence-store's process_issue).
CLOSING = ("accept", "test", "named")


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


def recorded(r: dict) -> str:
    """What intake replies on recording `r` from its issue, as evidence-store's process_issue says it."""
    k = intake.kind_key(r)
    footer = intake.FOOTER[k].format(name=r["subject"]["name"])
    if k == "accept" and r["by"]["kind"] == "agent":
        footer = footer.replace("It counts from now on.", "It is recorded as an AI agent's review: each reader "
                                "chooses whether those count.")
    return intake.describe(r) + "\n\n" + footer


def unfinished(repo: str, store: Store, swept: list[dict], outcome: dict, comments_of: Callable[[int], list[dict]],
               events_of: Callable[[int], list[dict]]) -> None:
    """Adds to `outcome` the reply, label and close that intake gives a review, test or named result it
    records, for each open issue swept whose record the store has from an earlier run: its reply only if
    the bot never posted one. An issue closed once and reopened since is left open, as intake leaves it."""
    closing = {n for n, _ in outcome.get("close", [])}
    for i in swept:
        n = i["number"]
        if n in closing or i.get("state", "open") != "open":
            continue
        r = next((r for r in store.from_origin(f"{repo}#{n}") if r.get("kind") in ("review", "test", "named")), None)
        if r is None or intake.kind_key(r) not in CLOSING:
            continue
        if any(e.get("event") == "closed" for e in events_of(n)):
            continue
        said = comments_of(n) if i.get("comments") else []
        if not any((c.get("user") or {}).get("login") in intake.BOTS for c in said):
            outcome.setdefault("replies", []).append([n, recorded(r)])
        if "evidence:needs-fix" in {l.get("name") for l in i.get("labels", [])}:
            outcome.setdefault("labels", []).append([n, [], ["evidence:needs-fix"]])
        outcome.setdefault("close", []).append([n, "completed"])


def apply(outcome: dict, repo: str, gh: Callable = github.gh, wait: Callable[[float], None] = time.sleep) -> list[int]:
    """Says and does on GitHub what intake decided, as evidence-store's `github.apply` does, but issue by
    issue: its replies, then its labels, then its close. An issue whose reply GitHub refuses keeps its
    labels and stays open, for the next run. Refused for a rate limit, it waits a minute and tries once
    more, and if refused again posts no more replies this run, but still closes what needs no reply.
    Returns the issues whose replies were refused."""
    if outcome.get("labels"):
        for name, colour in github.LABEL_COLOURS.items():
            gh("label", "create", name, "-R", repo, "--color", colour, "--force", check=False)
    order: list[int] = []
    for key in ("replies", "labels", "close"):
        for entry in outcome.get(key, []):
            if entry[0] not in order:
                order.append(entry[0])
    refused, limited = [], False

    def comment(n: int, text: str) -> None:
        gh("issue", "comment", str(n), "-R", repo, "--body-file", "-", input=text)

    for n in order:
        ok = True
        for m, text in outcome.get("replies", []):
            if m != n:
                continue
            if limited:
                ok = False
                break
            try:
                comment(n, text)
            except RuntimeError as e:
                if not LIMITED.search(str(e)):
                    ok = False
                    break
                wait(60)
                try:
                    comment(n, text)
                except RuntimeError as e2:
                    limited, ok = bool(LIMITED.search(str(e2))), False
                    break
        if not ok:
            refused.append(n)
            continue
        for m, add, remove in outcome.get("labels", []):
            args = [a for l in add for a in ("--add-label", l)] + [a for l in remove for a in ("--remove-label", l)]
            if m == n and args:
                gh("issue", "edit", str(n), "-R", repo, *args, check=False)
        for m, reason in outcome.get("close", []):
            if m == n:
                gh("issue", "close", str(n), "-R", repo, "--reason", reason, check=False)
    for n in outcome.get("reopen", []):
        gh("issue", "reopen", str(n), "-R", repo, check=False)
    for cid, content in outcome.get("reactions", []):
        gh("api", "-X", "POST", f"repos/{repo}/issues/comments/{cid}/reactions", "-f", f"content={content}", check=False)
    return refused


def value(argv: list[str], flag: str, default: str = "") -> str:
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    repo, outcome_file = value(argv, "--repo"), value(argv, "--outcome")
    if argv[:1] == ["apply"]:
        for n in apply(json.loads(Path(outcome_file).read_text(encoding="utf-8")), repo):
            print(f"::warning::GitHub refused the reply on #{n}: it stays open, and the next run answers it")
        return 0
    if "--sweep-open" not in argv:
        return cli.main(argv)
    argv.remove("--sweep-open")
    swept: list[dict] = []
    said: dict[int, list[dict]] = {}
    listed, fetch = github.recent_issues, github.comments

    def sweep(repo_: str, since: str) -> list[dict]:
        swept[:] = open_issues(repo_, since)
        return swept

    def comments(repo_: str, n: int) -> list[dict]:
        said[n] = fetch(repo_, n)
        return said[n]

    github.recent_issues, github.comments = sweep, comments
    try:
        code = cli.main(argv + ["--sweep-days", "1"])  # intake sweeps only with a number of days; which issues is ours
    finally:
        github.recent_issues, github.comments = listed, fetch
    if code != 0:
        return code
    outcome = json.loads(Path(outcome_file).read_text(encoding="utf-8"))
    unfinished(repo, Store.load(value(argv, "--store", "evidence")), swept, outcome,
               comments_of=lambda n: said[n] if n in said else fetch(repo, n),
               events_of=lambda n: github.events(repo, n))
    Path(outcome_file).write_text(json.dumps(outcome, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
