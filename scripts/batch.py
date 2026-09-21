#!/usr/bin/env python3
"""Collect the marks recorded since the last batch into one pull request, the
way the kernel's `b4 trailers -u` collects Reviewed-by replies into commits.

  python3 scripts/batch.py --message message.txt

Writes the marks into the tree in the two forms a batch into Tau Ceti could
take, so the pull request shows both:

- snapshot/REVIEWED-BY.md, a data file listing each declaration's current marks;
- snapshot/docstrings.lean, each reviewed declaration's docstring with its
  current marks as trailer lines, as they would read in the Lean source.

The commit message ends in one git trailer per new mark. snapshot/batched.json
records how far the ledger has been batched. Prints the number of new marks.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "snapshot"


def signer(mark: dict) -> str:
    return f"{mark['agent']} (AI) via @{mark['by']}" if mark["kind"] == "agent" else f"@{mark['by']}"


def commit_message(new: list, index: dict) -> str:
    names = sorted({mark["decl"] for mark in new})
    body = "\n".join(f"- {name}" for name in names)
    trailers = "\n".join(f"{m['trailer']}: {signer(m)} <{m['decl']}@{m['hash']}>" for m in new)
    return (f"Record {len(new)} review mark{'s' if len(new) != 1 else ''} on {len(names)} declaration{'s' if len(names) != 1 else ''}\n\n"
            f"Collected from the review issues since the last batch, against Tau Ceti {index['tauceti'][:7]}:\n\n{body}\n\n{trailers}\n")


def current(index: dict, records: list) -> dict:
    """Each declaration's marks on its current version."""
    version = {item["name"]: item["hash"] for item in index["declarations"]}
    out = {}
    for mark in records:
        if version.get(mark["decl"]) == mark["hash"]:
            out.setdefault(mark["decl"], []).append(mark)
    return out


def docstrings(index: dict, records: list) -> str:
    marks = current(index, records)
    blocks = []
    for item in index["declarations"]:
        if item["name"] not in marks:
            continue
        lines = "\n".join(f"{m['trailer']}: {signer(m)}, {m['at'][:10]}" for m in marks[item["name"]])
        doc = f"{item['doc']}\n\n{lines}" if item["doc"] else lines
        first = item["source"].splitlines()[0]
        blocks.append(f"-- {item['path']}, line {item['line']}\n/-- {doc} -/\n{first}")
    return ("-- How the current marks would read in Tau Ceti's source, if a batch wrote them into the docstrings.\n\n"
            + "\n\n".join(blocks) + "\n")


def table(index: dict, records: list) -> str:
    marks = current(index, records)
    rows = ["| `{}` | {} |".format(name, ", ".join("{}: {}".format(m["trailer"], signer(m)) for m in marks[name])) for name in sorted(marks)]
    return (f"# Reviewed-by\n\nCurrent marks on Tau Ceti {index['tauceti'][:7]}, one row per reviewed declaration.\n\n"
            "| Declaration | Marks |\n|---|---|\n" + "\n".join(rows) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--message", required=True)
    args = parser.parse_args()
    index = json.loads((ROOT / "data" / "declarations.json").read_text(encoding="utf-8"))
    ledger = ROOT / "reviews" / "records.jsonl"
    records = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()] if ledger.exists() else []
    mark_file = SNAPSHOT / "batched.json"
    done = json.loads(mark_file.read_text())["records"] if mark_file.exists() else 0
    new = records[done:]
    if new:
        SNAPSHOT.mkdir(exist_ok=True)
        (SNAPSHOT / "REVIEWED-BY.md").write_text(table(index, records), encoding="utf-8")
        (SNAPSHOT / "docstrings.lean").write_text(docstrings(index, records), encoding="utf-8")
        mark_file.write_text(json.dumps({"records": len(records)}) + "\n")
        Path(args.message).write_text(commit_message(new, index), encoding="utf-8")
    print(len(new))
    return 0


if __name__ == "__main__":
    sys.exit(main())
