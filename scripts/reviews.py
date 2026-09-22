#!/usr/bin/env python3
"""Record review marks and problem reports on Tau Ceti declarations, without a pull request.

  python3 scripts/reviews.py from-event <event.json> --reply reply.md --out <file>

A mark is a kernel-style trailer, Reviewed-by: it is the intended mathematical
notion. Two ways in, both from a browser:

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

What a declaration is tested by is not a mark but a list of tests it passes:
its unit tests (Tau Ceti's examples that name it, read by
fetch_declarations.py), key results listed with lines
`Test: <declaration> — <result that tests it> — what it checks` in a comment
on the `reviews` issue (reviews/tests.jsonl), and tests anyone suggests with
the "Suggest a test" form (label `test-suggestion`), each an issue that stays
open until the test is written (reviews/suggestions.jsonl).

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
INDEX = ROOT / "data" / "declarations.json"
TRAILERS = ("Reviewed-by",)
# Any "<Word>-by:" line is read, so that one that is not a mark here (Acked-by,
# say) is answered with the marks there are rather than ignored.
LINE = re.compile(r"^\s*([A-Z][a-z]+-by)\s*:\s*`?([^\s`]+)`?(?:\s+(?:—|–|--|-)\s+(.*?))?\s*$")
MARKER = re.compile(r"<!--\s*reviewed-by:v1\s+(\{.*?\})\s*-->", re.S)
TEST_LINE = re.compile(r"^\s*Test\s*:\s*`?([^\s`]+)`?\s+(?:—|–|--|-)\s+`?([^\s`]+)`?(?:\s+(?:—|–|--|-)\s+(.*?))?\s*$")
AGENT_FIELD = "Agent, model and session"
# The problem form's choices, by how they begin, and the names the ledger keeps.
WHAT = {"It is wrong": "wrong", "Its name or docstring is misleading": "misleading", "Something else is off": "other"}
WHAT_TITLE = {"wrong": "Wrong", "misleading": "Misleading name or docstring", "other": "Something else is off"}
# How the issue was closed (GitHub's state_reason), as the ledger records it.
RESOLUTION = {"completed": "fixed", "not_planned": "not planned", "duplicate": "duplicate"}
# What an edit to a report, or to a suggested test, can change.
REPORT_FIELDS = ("decl", "hash", "what", "why", "fix", "kind", "agent")
SUGGESTION_FIELDS = ("decl", "hash", "test", "catches", "kind", "agent")


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
            "trailer": fields.get("Mark", "").split(":")[0].strip() or "Reviewed-by",
            "kind": "agent" if fields.get("Who reviewed", "").startswith("An AI") else "person",
            "agent": agent_field(fields), "evidence": fields.get("Evidence", "").strip()}


def form_report(body: str) -> dict:
    fields = sections(body)
    what = fields.get("What is wrong", "")
    return {"decl": fields.get("Declaration", "").strip().strip("`"), "version": fields.get("Version reported", "").strip().strip("`"),
            "what": next((name for start, name in WHAT.items() if what.startswith(start)), "other"),
            "why": fields.get("Why", "").strip(), "fix": fields.get("Suggested fix", "").strip(),
            "kind": "agent" if fields.get("Who is reporting", "").startswith("An AI") else "person", "agent": agent_field(fields)}


def form_suggestion(body: str) -> dict:
    fields = sections(body)
    return {"decl": fields.get("Declaration", "").strip().strip("`"), "version": fields.get("Version", "").strip().strip("`"),
            "test": fields.get("Test", "").strip(), "catches": fields.get("What it would catch", "").strip(),
            "kind": "agent" if fields.get("Who is suggesting", "").startswith("An AI") else "person", "agent": agent_field(fields)}


def comment_agent(text: str) -> str:
    """The agent a comment's marker names, or "" for a person."""
    found = MARKER.search(text)
    if not found:
        return ""
    try:
        return str(json.loads(found.group(1)).get("agent", "")).strip()
    except ValueError:
        return ""


def comment_tests(text: str) -> list:
    agent = comment_agent(text)
    return [{"decl": match.group(1), "test": match.group(2), "checks": (match.group(3) or "").strip(), "kind": "agent" if agent else "person",
             "agent": agent} for match in map(TEST_LINE.match, text.splitlines()) if match]


def comment_marks(text: str) -> list:
    agent = comment_agent(text)
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
    if mark["trailer"] == "Tested-by":
        return None, ("Tested-by is now the list of tests a declaration passes: list a key result with "
                      "`Test: <declaration> — <result that tests it> — what it checks`, or suggest a test from the page")
    if mark["trailer"] not in TRAILERS:
        return None, "the mark is " + " or ".join(TRAILERS)
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


def make_test(entry: dict, index: dict, login: str, source: dict, at: str):
    """(record, None), or (None, why the test cannot be listed)."""
    item, missing = find(entry["decl"], index)
    if missing:
        return None, missing
    test, missing = find(entry["test"], index)
    if missing:
        return None, "the test " + missing
    if test["name"] == item["name"]:
        return None, "a declaration does not test itself"
    if entry["kind"] == "agent" and not entry["checks"]:
        return None, "an AI says what its test checks"
    return {"schema": "tests/v1", "decl": item["name"], "test": test["name"], "checks": entry["checks"], "by": login, "kind": entry["kind"],
            "agent": entry["agent"], "source": source, "at": at}, None


def make_suggestion(suggestion: dict, index: dict, login: str, number: int, at: str):
    """(the "reported" event, None), or (None, why the suggestion cannot be recorded)."""
    item, missing = find(suggestion["decl"], index)
    if missing:
        return None, missing
    if not suggestion["test"]:
        return None, "a suggestion says what to test"
    if suggestion["kind"] == "agent" and not suggestion["agent"]:
        return None, "an AI suggestion names its agent, model and session"
    return {"schema": "suggestion/v1", "event": "reported", "issue": number, "decl": item["name"], "hash": suggestion["version"] or item["hash"],
            "tauceti": index["tauceti"], "test": suggestion["test"], "catches": suggestion["catches"], "by": login,
            "kind": suggestion["kind"], "agent": suggestion["agent"], "at": at}, None


def reports(events: list, fields: tuple = REPORT_FIELDS) -> dict:
    """Every recorded report (or suggested test), by its issue number, as its events leave it."""
    out = {}
    for event in events:
        number = event.get("issue")
        if event["event"] == "reported":
            out[number] = dict(event, status="open")
        elif number not in out:
            continue
        elif event["event"] == "updated":
            out[number].update({key: event[key] for key in fields if key in event})
        elif event["event"] == "closed":
            out[number].update(status=event.get("resolution", "closed"), closedBy=event.get("by", ""), closedAt=event.get("at", ""))
        elif event["event"] == "reopened":
            out[number]["status"] = "open"
            for key in ("closedBy", "closedAt"):
                out[number].pop(key, None)
    return out


def report_state(events: list, number: int, fields: tuple = REPORT_FIELDS):
    """The report of one issue as its events leave it, or None if it was never recorded."""
    return reports(events, fields).get(number)


def tally(marks: list) -> dict:
    """For each kind of mark: how many people and how many AI agents gave it on
    the current version (each counted once), and how many marks are on earlier
    versions. What the page and the code show instead of every name."""
    out = {}
    for trailer in TRAILERS:
        given = [mark for mark in marks if mark["trailer"] == trailer]
        now = [mark for mark in given if mark.get("current", True)]
        if given:
            out[trailer] = {"people": len({mark["by"] for mark in now if mark["kind"] == "person"}),
                            "ai": len({mark["agent"] for mark in now if mark["kind"] == "agent"}),
                            "earlier": len(given) - len(now)}
    return out


def count_text(people: int, ai: int) -> str:
    """'3 people and 2 AI agents', '1 person', '1 AI agent'."""
    parts = ([f"{people} {'person' if people == 1 else 'people'}"] if people else []) + (
        [f"{ai} AI agent{'' if ai == 1 else 's'}"] if ai else [])
    return " and ".join(parts) or "nobody"


def tests_by_declaration(index: dict, listed: list, suggestions: list) -> dict:
    """What each declaration is tested by: its unit tests (Tau Ceti's examples
    that name it), the key results listed as its tests, and the tests suggested
    for it. A test passes while it is in Tau Ceti at the pinned commit without
    `sorry`; the counts are of tests that pass and of suggestions still open."""
    items = {item["name"]: item for item in index["declarations"]}
    out = {}

    def entry(name):
        return out.setdefault(name, {"unit": [], "results": [], "suggested": []})
    for example in index.get("examples", []):
        for name in example["tests"]:
            if name in items:
                entry(name)["unit"].append({"statement": example["statement"], "path": example["path"], "line": example["line"],
                                            "url": example["url"], "passes": not example["sorry"]})
    for record in listed:
        if record["decl"] not in items:
            continue
        test = items.get(record["test"])
        entry(record["decl"])["results"].append({
            "test": record["test"], "status": "missing" if test is None else "sorry" if test.get("sorry") else "passes",
            "statement": test["source"] if test else "", "url": test["url"] if test else "", "checks": record["checks"],
            "by": record["by"], "kind": record["kind"], "agent": record["agent"], "at": record["at"]})
    for suggestion in reports(suggestions, SUGGESTION_FIELDS).values():
        if suggestion["decl"] in items:
            entry(suggestion["decl"])["suggested"].append({key: suggestion[key] for key in (
                "issue", "status", "test", "catches", "by", "kind", "agent", "hash", "at", "closedBy", "closedAt") if key in suggestion})
    for tests in out.values():
        tests["tally"] = {"unit": sum(test["passes"] for test in tests["unit"]),
                          "results": sum(result["status"] == "passes" for result in tests["results"]),
                          "suggested": sum(suggestion["status"] == "open" for suggestion in tests["suggested"])}
    return out


def test_count_text(unit: int, results: int) -> str:
    """'2 unit tests and 3 key results', '1 unit test', '1 key result'."""
    parts = ([f"{unit} unit test{'' if unit == 1 else 's'}"] if unit else []) + (
        [f"{results} key result{'' if results == 1 else 's'}"] if results else [])
    return " and ".join(parts)


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


def open_issues() -> dict:
    """The issues that stay open until something is done, by label: a problem
    report until the declaration is fixed, a suggested test until it is written."""
    return {
        "problem": {"ledger": "problems.jsonl", "fields": REPORT_FIELDS, "form": form_report, "make": make_report, "noun": "report",
                    "resolution": RESOLUTION, "done": "fixed", "shown": "resolved",
                    "stays": "until the problem is fixed: close it as completed once it is, or as not planned if the declaration is right after all",
                    "line": lambda r: f"- ! **{WHAT_TITLE[r['what']]}:** `{r['decl']}`, version `{r['hash']}`, reported by {who(r)}.",
                    "recorded": "Record the problem reported in #{}"},
        "test-suggestion": {"ledger": "suggestions.jsonl", "fields": SUGGESTION_FIELDS, "form": form_suggestion, "make": make_suggestion,
                            "noun": "suggestion", "resolution": {"completed": "written", "not_planned": "declined", "duplicate": "duplicate"},
                            "done": "written", "shown": "written",
                            "stays": ("until the test is written in Tau Ceti: close it as completed once it is, and list it with a `Test:` line "
                                      "on the marking issue, or as not planned if it should not be written"),
                            "line": lambda r: f"- ? **Suggested test** for `{r['decl']}`, version `{r['hash']}`, by {who(r)}.",
                            "recorded": "Record the test suggested in #{}"},
    }


def report_event(event: dict, index: dict, path: Path, site: str, at: str, kind: dict | None = None) -> tuple:
    """An issue that stays open (a problem report or a suggested test) was opened,
    edited, closed or reopened: (reply, outputs)."""
    kind = kind or open_issues()["problem"]
    issue, action = event["issue"], event.get("action", "opened")
    number, noun = issue["number"], kind["noun"]
    outputs = {"recorded": 0, "invalid": 0, "close": "false", "number": number, "message": ""}
    state = report_state(load(path), number, kind["fields"])
    sender = (event.get("sender") or {}).get("login") or issue["user"]["login"]
    page = f"{site}#d={state['decl']}" if state else site
    if action == "closed":
        if state is None:
            return "", outputs
        resolution = kind["resolution"].get(issue.get("state_reason") or "", "closed")
        append(path, {"schema": "problem/v1" if noun == "report" else "suggestion/v1", "event": "closed", "issue": number,
                      "resolution": resolution, "by": sender, "at": at})
        outputs.update(recorded=1, message=f"Record that #{number} was closed")
        return (f"Recorded as {resolution}. The page shows the {noun} on `{state['decl']}` as {kind['shown']}: {page}\n" if resolution == kind["done"] else
                f"Recorded as closed ({resolution}). The page shows the {noun} on `{state['decl']}` as closed: {page}\n"), outputs
    if action == "reopened":
        if state is None:
            return "", outputs
        append(path, {"schema": "problem/v1" if noun == "report" else "suggestion/v1", "event": "reopened", "issue": number, "by": sender, "at": at})
        outputs.update(recorded=1, message=f"Record that #{number} was reopened")
        return f"Reopened. The page shows the {noun} on `{state['decl']}` again: {page}\n", outputs
    record, refusal = kind["make"](kind["form"](issue["body"] or ""), index, issue["user"]["login"], number, at)
    if refusal:
        outputs["invalid"] = 1
        return ("Nothing was recorded.\n\n- ✗ " + refusal + ("" if refusal.endswith(("?", ".")) else ".") +
                "\n\nEdit the issue to correct it; the bot reads it again.\n"), outputs
    if state is None:
        append(path, record)
        outputs.update(recorded=1, message=kind["recorded"].format(number))
        return (f"Recorded. This issue stays open {kind['stays']}.\n\n{kind['line'](record)}\n\n"
                f"The page shows the {noun} on the declaration within a minute or two: {site}#d={record['decl']}\n"), outputs
    if all(record[key] == state.get(key) for key in kind["fields"]):
        return "", outputs
    append(path, {"schema": record["schema"], "event": "updated", "issue": number, **{key: record[key] for key in kind["fields"]}, "by": sender, "at": at})
    outputs.update(recorded=1, message=f"Record the edit to #{number}")
    return f"Updated the {noun}. The page shows the new version within a minute or two: {site}#d={record['decl']}\n", outputs


def from_event(event: dict, index: dict, ledger: Path, site: str, at: str) -> tuple:
    """Marks and tests from an issue form or a comment, or an issue that stays open
    (a problem report, a suggested test): (reply, outputs). The other ledgers sit
    beside the marks' ledger."""
    issue = event["issue"]
    labels = {label["name"] for label in issue.get("labels") or []}
    for label, kind in open_issues().items():
        if "comment" not in event and label in labels:
            return report_event(event, index, ledger.with_name(kind["ledger"]), site, at, kind)
    if "comment" not in event and event.get("action") in ("closed", "reopened"):
        return "", {"recorded": 0, "invalid": 0, "close": "false", "number": issue["number"], "message": ""}
    tests = []
    if "comment" in event:
        text = event["comment"]["body"] or ""
        login, marks, source = event["comment"]["user"]["login"], comment_marks(text), {"issue": issue["number"], "comment": event["comment"]["id"]}
        tests = comment_tests(text)
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
    listed = ledger.with_name("tests.jsonl")
    for entry in tests:
        record, refusal = make_test(entry, index, login, source, at)
        if refusal:
            invalid += 1
            lines.append(f"- ✗ {refusal}" + ("" if refusal.endswith(("?", ".")) else "."))
        elif any((old["decl"], old["test"]) == (record["decl"], record["test"]) for old in load(listed)):
            lines.append(f"- = `{record['test']}` was already listed as a test of `{record['decl']}`.")
        else:
            append(listed, record)
            recorded += 1
            lines.append(f"- ✓ **Test:** `{record['test']}` for `{record['decl']}`" + (f": {record['checks']}" if record["checks"] else "") + ".")
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
                                f"https://{owner.lower()}.github.io/{repo}/", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    Path(args.reply).write_text(reply, encoding="utf-8")
    with open(args.out, "a", encoding="utf-8") as handle:
        for key, value in outputs.items():
            handle.write(f"{key}={value}\n")
    print(json.dumps(outputs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
