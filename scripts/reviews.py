#!/usr/bin/env python3
"""Record review marks and problem reports on Tau Ceti declarations, without a pull request.

  python3 scripts/reviews.py from-event <event.json> --reply reply.md --out <file>

A mark is a kernel-style trailer: Reviewed-by (it is the intended mathematical
notion) or Tested-by (its examples and unit tests check out). Two ways in, both
from a browser:

- the "Review a definition" issue form (label `review`), usually opened from a
  "Review this" link that fills in the declaration and the version shown;
- lines `Reviewed-by: <declaration> — <evidence>` in a comment on an issue
  labelled `reviews`, one mark per line. An AI agent puts the marker
  <!--reviewed-by:v1 {"agent": "<agent, model, session>"}--> in the comment.

A person need not say why a declaration is right; an AI review must give its
evidence. Each mark is appended to reviews/records.jsonl with the GitHub
account that submitted it, which GitHub authenticates, and the version of the
declaration it was made on. The page shows it, greyed once the declaration
changes.

A problem report says that a declaration is wrong, and why: the "Report a
problem" form (label `problem`), opened from the page. The report is the issue
that gets the declaration fixed, so it stays open. Its events (reported, edited,
closed as fixed or not, reopened) are appended to reviews/problems.jsonl, and the
page shows the report on the declaration until its issue is closed.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "reviews" / "records.jsonl"
PROBLEMS = ROOT / "reviews" / "problems.jsonl"
INDEX = ROOT / "data" / "declarations.json"
TRAILERS = ("Reviewed-by", "Tested-by")
# Any "<Word>-by:" line is read, so that one that is not a mark here (Acked-by,
# say) is answered with the marks there are rather than ignored.
LINE = re.compile(r"^\s*([A-Z][a-z]+-by)\s*:\s*`?([^\s`]+)`?(?:\s+(?:—|–|--|-)\s+(.*?))?\s*$")
MARKER = re.compile(r"<!--\s*reviewed-by:v1\s+(\{.*?\})\s*-->", re.S)
AGENT_FIELD = "Agent, model and session"
# The problem form's choices, by how they begin, and the names the ledger keeps.
WHAT = {"It is wrong": "wrong", "Its name or docstring is misleading": "misleading", "Something else is off": "other"}
WHAT_TITLE = {"wrong": "Wrong", "misleading": "Misleading name or docstring", "other": "Something else is off"}
# How the issue was closed (GitHub's state_reason), as the ledger records it.
RESOLUTION = {"completed": "fixed", "not_planned": "not planned", "duplicate": "duplicate"}
# What an edit to a report can change.
REPORT_FIELDS = ("decl", "hash", "what", "why", "fix", "kind", "agent")


def sections(body: str) -> dict:
    """The fields of a rendered issue form: '### Label' followed by the answer."""
    out, current, lines = {}, None, []
    for line in body.splitlines():
        if line.startswith("### "):
            if current is not None:
                out[current] = "\n".join(lines).strip()
            current, lines = line[4:].strip(), []
        elif current is not None:
            lines.append(line)
    if current is not None:
        out[current] = "\n".join(lines).strip()
    return {label: "" if answer == "_No response_" else answer for label, answer in out.items()}


def agent_field(fields: dict) -> str:
    return next((answer for label, answer in fields.items() if label.startswith(AGENT_FIELD)), "").strip()


def form_mark(body: str) -> dict:
    fields = sections(body)
    return {"decl": fields.get("Declaration", "").strip().strip("`"), "version": fields.get("Version reviewed", "").strip().strip("`"),
            "trailer": fields.get("Mark", "").split(":")[0].strip(),
            "kind": "agent" if fields.get("Who reviewed", "").startswith("An AI") else "person",
            "agent": agent_field(fields), "evidence": fields.get("Evidence", "").strip()}


def form_report(body: str) -> dict:
    fields = sections(body)
    what = fields.get("What is wrong", "")
    return {"decl": fields.get("Declaration", "").strip().strip("`"), "version": fields.get("Version reported", "").strip().strip("`"),
            "what": next((name for start, name in WHAT.items() if what.startswith(start)), "other"),
            "why": fields.get("Why", "").strip(), "fix": fields.get("Suggested fix", "").strip(),
            "kind": "agent" if fields.get("Who is reporting", "").startswith("An AI") else "person", "agent": agent_field(fields)}


def comment_marks(text: str) -> list:
    agent = ""
    found = MARKER.search(text)
    if found:
        try:
            agent = str(json.loads(found.group(1)).get("agent", "")).strip()
        except ValueError:
            agent = ""
    return [{"decl": match.group(2), "version": "", "trailer": match.group(1), "kind": "agent" if agent else "person",
             "agent": agent, "evidence": (match.group(3) or "").strip()}
            for match in map(LINE.match, text.splitlines()) if match]


def find(name: str, index: dict):
    """(the declaration, None), or (None, why there is none, with the closest names)."""
    by_name = {item["name"]: item for item in index["declarations"]}
    if name in by_name:
        return by_name[name], None
    close = difflib.get_close_matches(name, list(by_name), n=3, cutoff=.6)
    return None, f"`{name or '(none)'}` is not a declaration on the page" + (
        "; did you mean " + ", ".join(f"`{match}`" for match in close) + "?" if close else "")


def make_record(mark: dict, index: dict, login: str, source: dict, at: str):
    """(record, None), or (None, why the mark cannot be recorded)."""
    item, missing = find(mark["decl"], index)
    if missing:
        return None, missing
    if mark["trailer"] not in TRAILERS:
        return None, "the mark is one of " + ", ".join(TRAILERS)
    if mark["kind"] == "agent" and not mark["agent"]:
        return None, "an AI review names its agent, model and session"
    # A person need not say why a declaration is right; an AI review must.
    if mark["kind"] == "agent" and not mark["evidence"]:
        return None, "an AI review gives its evidence: what it compared the declaration with, or what it checked"
    record = {"schema": "reviewed-by/v1", "decl": item["name"], "hash": mark["version"] or item["hash"], "tauceti": index["tauceti"],
              "trailer": mark["trailer"], "by": login, "kind": mark["kind"], "agent": mark["agent"], "evidence": mark["evidence"],
              "source": source, "at": at}
    if record["hash"] != item["hash"]:
        record["stale"] = True
    return record, None


def make_report(report: dict, index: dict, login: str, number: int, at: str):
    """(the "reported" event, None), or (None, why the report cannot be recorded)."""
    item, missing = find(report["decl"], index)
    if missing:
        return None, missing
    if not report["why"]:
        return None, "a report says why the declaration is wrong, so that it can be fixed"
    if report["kind"] == "agent" and not report["agent"]:
        return None, "an AI report names its agent, model and session"
    return {"schema": "problem/v1", "event": "reported", "issue": number, "decl": item["name"], "hash": report["version"] or item["hash"],
            "tauceti": index["tauceti"], "what": report["what"], "why": report["why"], "fix": report["fix"], "by": login,
            "kind": report["kind"], "agent": report["agent"], "at": at}, None


def reports(events: list) -> dict:
    """Every recorded report, by its issue number, as its events leave it."""
    out = {}
    for event in events:
        number = event.get("issue")
        if event["event"] == "reported":
            out[number] = dict(event, status="open")
        elif number not in out:
            continue
        elif event["event"] == "updated":
            out[number].update({key: event[key] for key in REPORT_FIELDS if key in event})
        elif event["event"] == "closed":
            out[number].update(status=event.get("resolution", "closed"), closedBy=event.get("by", ""), closedAt=event.get("at", ""))
        elif event["event"] == "reopened":
            out[number]["status"] = "open"
            for key in ("closedBy", "closedAt"):
                out[number].pop(key, None)
    return out


def report_state(events: list, number: int):
    """The report of one issue as its events leave it, or None if it was never recorded."""
    return reports(events).get(number)


def identity(record: dict) -> tuple:
    return record["decl"], record["hash"], record["trailer"], record["by"], record["kind"], record["agent"]


def load(ledger: Path) -> list:
    return [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()] if ledger.exists() else []


def append(ledger: Path, record: dict) -> None:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def add(ledger: Path, record: dict) -> bool:
    """Append the record unless the same person already made the same mark on the same version."""
    if any(identity(old) == identity(record) for old in load(ledger)):
        return False
    append(ledger, record)
    return True


def who(record: dict) -> str:
    return f"{record['agent']} (AI), via @{record['by']}" if record["kind"] == "agent" else f"@{record['by']}"


def report_event(event: dict, index: dict, path: Path, site: str, at: str) -> tuple:
    """A problem report's issue was opened, edited, closed or reopened: (reply, outputs)."""
    issue, action = event["issue"], event.get("action", "opened")
    number = issue["number"]
    outputs = {"recorded": 0, "invalid": 0, "close": "false", "number": number, "message": ""}
    state = report_state(load(path), number)
    sender = (event.get("sender") or {}).get("login") or issue["user"]["login"]
    page = f"{site}#d={state['decl']}" if state else site
    if action == "closed":
        if state is None:
            return "", outputs
        resolution = RESOLUTION.get(issue.get("state_reason") or "", "closed")
        append(path, {"schema": "problem/v1", "event": "closed", "issue": number, "resolution": resolution, "by": sender, "at": at})
        outputs.update(recorded=1, message=f"Record that the problem reported in #{number} was closed")
        return (f"Recorded as fixed. The page shows the report on `{state['decl']}` as resolved: {page}\n" if resolution == "fixed" else
                f"Recorded as closed ({resolution}), with no fix. The page shows the report on `{state['decl']}` as closed: {page}\n"), outputs
    if action == "reopened":
        if state is None:
            return "", outputs
        append(path, {"schema": "problem/v1", "event": "reopened", "issue": number, "by": sender, "at": at})
        outputs.update(recorded=1, message=f"Record that the problem reported in #{number} was reopened")
        return f"Reopened. The page shows the problem on `{state['decl']}` again: {page}\n", outputs
    record, refusal = make_report(form_report(issue["body"] or ""), index, issue["user"]["login"], number, at)
    if refusal:
        outputs["invalid"] = 1
        return ("Nothing was recorded.\n\n- ✗ " + refusal + ("" if refusal.endswith(("?", ".")) else ".") +
                "\n\nEdit the issue to correct it; the bot reads it again.\n"), outputs
    if state is None:
        append(path, record)
        outputs.update(recorded=1, message=f"Record the problem reported in #{number}")
        return ("Recorded. This issue stays open until the problem is fixed: close it as completed once it is, "
                "or as not planned if the declaration is right after all.\n\n"
                f"- ! **{WHAT_TITLE[record['what']]}:** `{record['decl']}`, version `{record['hash']}`, reported by {who(record)}.\n\n"
                f"The page shows the report on the declaration within a minute or two: {site}#d={record['decl']}\n"), outputs
    if all(record[key] == state.get(key) for key in REPORT_FIELDS):
        return "", outputs
    append(path, {"schema": "problem/v1", "event": "updated", "issue": number, **{key: record[key] for key in REPORT_FIELDS}, "by": sender, "at": at})
    outputs.update(recorded=1, message=f"Record the edit to the problem reported in #{number}")
    return f"Updated the report. The page shows the new version within a minute or two: {site}#d={record['decl']}\n", outputs


def from_event(event: dict, index: dict, ledger: Path, site: str, at: str, problems: Path | None = None) -> tuple:
    """Marks from an issue form or a comment, or a problem report: (reply, outputs)."""
    issue = event["issue"]
    if "comment" not in event and "problem" in {label["name"] for label in issue.get("labels") or []}:
        return report_event(event, index, problems or ledger.with_name("problems.jsonl"), site, at)
    if "comment" not in event and event.get("action") in ("closed", "reopened"):
        return "", {"recorded": 0, "invalid": 0, "close": "false", "number": issue["number"], "message": ""}
    if "comment" in event:
        login, marks, source = event["comment"]["user"]["login"], comment_marks(event["comment"]["body"] or ""), {"issue": issue["number"], "comment": event["comment"]["id"]}
    else:
        login, marks, source = issue["user"]["login"], [form_mark(issue["body"] or "")], {"issue": issue["number"]}
    lines, recorded, invalid = [], 0, 0
    for mark in marks:
        record, refusal = make_record(mark, index, login, source, at)
        if refusal:
            invalid += 1
            lines.append(f"- ✗ {refusal}" + ("" if refusal.endswith(("?", ".")) else "."))
        elif add(ledger, record):
            recorded += 1
            lines.append(f"- ✓ **{record['trailer']}:** {who(record)} on `{record['decl']}`, version `{record['hash']}`"
                         + (" — an earlier version than the page shows now, so the mark is greyed" if record.get("stale") else "") + ".")
        else:
            lines.append(f"- = {record['trailer']} by {who(record)} on `{record['decl']}` was already recorded.")
    reply = ""
    if lines:
        reply = "\n".join(["Recorded without a pull request." if recorded else "Nothing new was recorded.", "", *lines, "",
                           f"The page updates in a minute or two: {site}" if recorded else
                           "Edit the issue to correct it; the bot reads it again." if invalid and "comment" not in event else ""]).strip() + "\n"
    close = "comment" not in event and not invalid
    return reply, {"recorded": recorded, "invalid": invalid, "close": str(close).lower(), "number": issue["number"],
                   "message": f"Record review marks from #{issue['number']}"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["from-event"])
    parser.add_argument("event")
    parser.add_argument("--reply", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    owner, _, repo = os.environ.get("GITHUB_REPOSITORY", "CBirkbeck/tauceti-reviewed-by-test").partition("/")
    reply, outputs = from_event(json.loads(Path(args.event).read_text()), json.loads(INDEX.read_text()), LEDGER,
                                f"https://{owner.lower()}.github.io/{repo}/", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), PROBLEMS)
    Path(args.reply).write_text(reply, encoding="utf-8")
    with open(args.out, "a", encoding="utf-8") as handle:
        for key, value in outputs.items():
            handle.write(f"{key}={value}\n")
    print(json.dumps(outputs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
