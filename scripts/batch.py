#!/usr/bin/env python3
"""Collect the marks recorded since the last batch into one pull request, the
way the kernel's `b4 trailers -u` collects Reviewed-by replies into commits.

  python3 scripts/batch.py --message message.txt

Writes the marks into the tree in the two forms a batch into Tau Ceti could
take, so the pull request shows both:

- snapshot/REVIEWED-BY.md, a data file counting each declaration's current marks
  and the tests it passes;
- snapshot/docstrings.lean, the docstring of each declaration with marks or
  listed tests, as it would read in the Lean source: how many people and AI
  agents reviewed it and how many tests it passes, then a link, on a line of
  its own, to the page that says who and which.

However many marks a declaration collects, the source keeps one line per kind.
The full record is the ledger and the git history: the commit message ends in
one git trailer per new mark. snapshot/batched.json
records how far the ledger has been batched. Prints the number of new marks.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reviews import TRAILERS, count_text, load, tally, test_count_text, tests_by_declaration  # noqa: E402

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


def summary_lines(name: str, marks: list, tests: dict, site: str) -> list:
    """A line counting each kind of mark, one counting the tests, then the link to who and
    which. The counts stay short; the link has a line of its own, because a URL cannot be
    wrapped and Mathlib's longLine linter lets only a line with a URL pass 100 characters."""
    lines = [f"{trailer}: {count_text(n['people'], n['ai'])}" for trailer, n in tally(marks).items()]
    counted = test_count_text(tests["tally"]["unit"], tests["tally"]["results"]) if tests else ""
    return lines + ([f"Tested by: {counted}"] if counted else []) + [f"[Reviews and tests]({site}#d={name})"]


def shown(index: dict, marks: dict, listed: list) -> list:
    """The declarations the snapshot writes: those with current marks or listed tests."""
    named = set(marks) | {record["decl"] for record in listed}
    return [item for item in index["declarations"] if item["name"] in named]


def docstrings(index: dict, records: list, site: str, listed: list) -> str:
    marks, tests = current(index, records), tests_by_declaration(index, listed, [])
    blocks = []
    for item in shown(index, marks, listed):
        lines = "\n".join(summary_lines(item["name"], marks.get(item["name"], []), tests.get(item["name"]), site))
        doc = f"{item['doc']}\n\n{lines}" if item["doc"] else lines
        first = item["source"].splitlines()[0]
        blocks.append(f"-- {item['path']}, line {item['line']}\n/-- {doc} -/\n{first}")
    return ("-- How the current marks would read in Tau Ceti's source, if a batch wrote them into the docstrings.\n\n"
            + "\n\n".join(blocks) + "\n")


def table(index: dict, records: list, site: str, listed: list) -> str:
    marks, tests = current(index, records), tests_by_declaration(index, listed, [])
    rows = []
    for item in sorted(shown(index, marks, listed), key=lambda item: item["name"]):
        name, counts, passing = item["name"], tally(marks.get(item["name"], [])), tests.get(item["name"])
        cells = [count_text(counts[t]["people"], counts[t]["ai"]) if t in counts else "—" for t in TRAILERS]
        cells.append((test_count_text(passing["tally"]["unit"], passing["tally"]["results"]) if passing else "") or "—")
        rows.append(f"| [`{name}`]({site}#d={name}) | " + " | ".join(cells) + " |")
    return (f"# Reviewed-by\n\nCurrent marks on Tau Ceti {index['tauceti'][:7]}: how many people and AI agents reviewed each "
            "declaration's current version, and how many tests it passes. Each declaration's link shows who and which.\n\n"
            "| Declaration | " + " | ".join(TRAILERS) + " | Tested by |\n|---|" + "---|" * (len(TRAILERS) + 1) + "\n" + "\n".join(rows) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--message", required=True)
    args = parser.parse_args()
    index = json.loads((ROOT / "data" / "declarations.json").read_text(encoding="utf-8"))
    owner, _, repo = json.loads((ROOT / "data" / "settings.json").read_text(encoding="utf-8"))["repo"].partition("/")
    site = f"https://{owner.lower()}.github.io/{repo}/"
    ledger = ROOT / "reviews" / "records.jsonl"
    records = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()] if ledger.exists() else []
    mark_file = SNAPSHOT / "batched.json"
    done = json.loads(mark_file.read_text())["records"] if mark_file.exists() else 0
    new = records[done:]
    if new:
        SNAPSHOT.mkdir(exist_ok=True)
        listed = load(ROOT / "reviews" / "tests.jsonl")
        (SNAPSHOT / "REVIEWED-BY.md").write_text(table(index, records, site, listed), encoding="utf-8")
        (SNAPSHOT / "docstrings.lean").write_text(docstrings(index, records, site, listed), encoding="utf-8")
        mark_file.write_text(json.dumps({"records": len(records)}) + "\n")
        Path(args.message).write_text(commit_message(new, index), encoding="utf-8")
    print(len(new))
    return 0


if __name__ == "__main__":
    sys.exit(main())
