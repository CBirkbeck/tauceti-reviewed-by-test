#!/usr/bin/env python3
"""Record review marks on Tau Ceti declarations, without a pull request.

  python3 scripts/reviews.py from-event <event.json> --reply reply.md --out <file>

A mark is a kernel-style trailer: Reviewed-by (it is the intended mathematical
notion) or Tested-by (its examples and unit tests check out). Two ways in, both
from a browser:

- the "Review a definition" issue form (label `review`), usually opened from a
  "Review this" link that fills in the declaration and the version shown;
- lines `Reviewed-by: <declaration> — <evidence>` in a comment on an issue
  labelled `reviews`, one mark per line. An AI agent puts the marker
  <!--reviewed-by:v1 {"agent": "<agent, model, session>"}--> in the comment.

Each mark is appended to reviews/records.jsonl with the GitHub account that
submitted it, which GitHub authenticates, and the version of the declaration
it was made on. The page shows it, greyed once the declaration changes.
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
TRAILERS = ("Reviewed-by", "Tested-by")
# Any "<Word>-by:" line is read, so that one that is not a mark here (Acked-by,
# say) is answered with the marks there are rather than ignored.
LINE = re.compile(r"^\s*([A-Z][a-z]+-by)\s*:\s*`?([^\s`]+)`?(?:\s+(?:—|–|--|-)\s+(.*?))?\s*$")
MARKER = re.compile(r"<!--\s*reviewed-by:v1\s+(\{.*?\})\s*-->", re.S)
AGENT_FIELD = "Agent, model and session (AI reviews only)"


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


def form_mark(body: str) -> dict:
    fields = sections(body)
    return {"decl": fields.get("Declaration", "").strip().strip("`"), "version": fields.get("Version reviewed", "").strip().strip("`"),
            "trailer": fields.get("Mark", "").split(":")[0].strip(),
            "kind": "agent" if fields.get("Who reviewed", "").startswith("An AI") else "person",
            "agent": fields.get(AGENT_FIELD, "").strip(), "evidence": fields.get("Evidence", "").strip()}


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


def make_record(mark: dict, index: dict, login: str, source: dict, at: str):
    """(record, None), or (None, why the mark cannot be recorded)."""
    by_name = {item["name"]: item for item in index["declarations"]}
    item = by_name.get(mark["decl"])
    if not item:
        close = difflib.get_close_matches(mark["decl"], list(by_name), n=3, cutoff=.6)
        return None, f"`{mark['decl'] or '(none)'}` is not a declaration on the page" + (
            "; did you mean " + ", ".join(f"`{name}`" for name in close) + "?" if close else "")
    if mark["trailer"] not in TRAILERS:
        return None, "the mark is one of " + ", ".join(TRAILERS)
    if "comment" not in source and not mark["evidence"]:
        return None, "the form needs evidence: what you compared the declaration with, or what you checked"
    if mark["kind"] == "agent" and not mark["agent"]:
        return None, "an AI review names its agent, model and session"
    record = {"schema": "reviewed-by/v1", "decl": item["name"], "hash": mark["version"] or item["hash"], "tauceti": index["tauceti"],
              "trailer": mark["trailer"], "by": login, "kind": mark["kind"], "agent": mark["agent"], "evidence": mark["evidence"],
              "source": source, "at": at}
    if record["hash"] != item["hash"]:
        record["stale"] = True
    return record, None


def identity(record: dict) -> tuple:
    return record["decl"], record["hash"], record["trailer"], record["by"], record["kind"], record["agent"]


def load(ledger: Path) -> list:
    return [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()] if ledger.exists() else []


def add(ledger: Path, record: dict) -> bool:
    """Append the record unless the same person already made the same mark on the same version."""
    if any(identity(old) == identity(record) for old in load(ledger)):
        return False
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return True


def who(record: dict) -> str:
    return f"{record['agent']} (AI), via @{record['by']}" if record["kind"] == "agent" else f"@{record['by']}"


def from_event(event: dict, index: dict, ledger: Path, site: str, at: str) -> tuple:
    """Marks from an issue form or a comment: (reply, outputs)."""
    issue = event["issue"]
    if "comment" in event:
        login, marks, source = event["comment"]["user"]["login"], comment_marks(event["comment"]["body"] or ""), {"issue": issue["number"], "comment": event["comment"]["id"]}
    else:
        login, marks, source = issue["user"]["login"], [form_mark(issue["body"] or "")], {"issue": issue["number"]}
    lines, recorded, problems = [], 0, 0
    for mark in marks:
        record, problem = make_record(mark, index, login, source, at)
        if problem:
            problems += 1
            lines.append(f"- ✗ {problem}" + ("" if problem.endswith(("?", ".")) else "."))
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
                           "Edit the issue to correct it; the bot reads it again." if problems and "comment" not in event else ""]).strip() + "\n"
    close = "comment" not in event and not problems
    return reply, {"recorded": recorded, "problems": problems, "close": str(close).lower(), "number": issue["number"]}


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
