#!/usr/bin/env python3
"""The migration's writing: the batches Claude Code agents write the standard reviews from, the results they add, and
those results collected. Agents in a session write the reviews, not the Message Batches API (Ruling R31).

  python3 scripts/migrate_write.py split BUNDLES --name NAME [--size 40] [--work .cache/migration]
  python3 scripts/migrate_write.py split BUNDLES --name NAME --retry CHECKS --results RESULTS [--size …] [--work …]
  python3 scripts/migrate_write.py add RESULT --decl DECL --verdict approve|hold --cells CELLS [--hold WHY]
                                   [--review FILE]
  python3 scripts/migrate_write.py collect NAME [--work .cache/migration]

**split** cuts BUNDLES (scripts/migrate_inputs.py) into `<work>/<NAME>/batch-<nnn>.jsonl`, `nnn` from 001: at most
`--size` bundles each, in their order, each given `index`, its line in BUNDLES from 0. It writes
`<work>/<NAME>/prompt.md` beside them, the agents' instructions: scripts/migrate_prompt.md, with AI-REVIEWS.md's
definition of the standard review (its section between `<!-- standard-review:begin -->` and
`<!-- standard-review:end -->`) put in where it says, and the command that adds a result. It prints one line per batch:
its path, and how many bundles it has. An agent takes one batch: it reads prompt.md and the batch, and for each bundle
adds one line to `result-<nnn>.jsonl` beside it, of the batch's number: `{"decl", "cells", "verdict", "hold",
"review"}`, and nothing else.

With `--retry`, it takes only the bundles whose result in RESULTS (`collect`'s) failed its check in CHECKS
(scripts/migrate_check.py, run on RESULTS), no result among them; a bundle that is not in RESULTS was not in that round.
Each gets `retry`: `{"problems": [what the check found], "previous": "<the review it was given>"}`.

A name is split once: `split` refuses a directory that holds batches or results already, since agents' work is in it.

**add** is how an agent adds a result to its RESULT file, `result-<nnn>.jsonl`. The review is read from FILE, or from
stdin, as written: an agent gives it in a here-document, with nothing to escape, so that a TeX backslash stays one (JSON
written by hand reads `\\theta` as a tab and `heta`). The line replaces any line of the declaration the file had. `add`
refuses a declaration that is not in the batch, and a result whose cells, verdict or hold break the contract
(`migrate_check.shape`), writing nothing; it then checks the review as migrate_check.py will and says what it finds, so
that the agent can fix it and add it again.

**collect** merges the result files of NAME into `<work>/<NAME>/results.jsonl`: one line per bundle, in the bundles'
order, its result, or `{"decl", "error"}`, the error `no result`, `unparseable line` or `two results`. A line that is
not JSON counts as its declaration's when it names one of the batch; a line that repeats another exactly counts once.
It prints how many of each, the lines that name no bundle of their batch, and the batches without a result file yet.

Exit 0 when done, 1 when `add` refuses a result, 2 on bad input.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT  # noqa: E402
import migrate_check  # noqa: E402
import standard  # noqa: E402

WORK = ROOT / ".cache" / "migration"
TEMPLATE = Path(__file__).resolve().with_name("migrate_prompt.md")
GUIDE = ROOT / "AI-REVIEWS.md"
BEGIN, END = "<!-- standard-review:begin -->", "<!-- standard-review:end -->"
#: Where the template takes AI-REVIEWS.md's section, and the command that adds a result.
SECTION, ADD = "{{STANDARD_REVIEW}}", "{{ADD}}"
#: The most bundles a batch holds, unless told otherwise.
SIZE = 40
NAME = re.compile(r"\w[\w.-]*")
BATCH = re.compile(r"batch-(\d+)\.jsonl")
RESULT = re.compile(r"result-(\d+)\.jsonl")
#: A declaration named in a line that is not JSON: its `decl` field, as JSON writes a string.
DECL = re.compile(r'"decl"\s*:\s*("(?:[^"\\\n]|\\.)*")')


class Refused(Exception):
    """A request that cannot be done; its message says why."""


def section(guide: str) -> str:
    """The section of AI-REVIEWS.md (`guide`) between its markers: the one definition of a standard review."""
    if guide.count(BEGIN) != 1 or guide.count(END) != 1 or guide.index(BEGIN) > guide.index(END):
        raise ValueError(f"AI-REVIEWS.md must mark one section, {BEGIN} … {END}")
    return guide.split(BEGIN, 1)[1].split(END, 1)[0].strip("\n")


def add_command() -> str:
    """The command an agent adds a result with: this script run by this Python, so that it runs as written."""
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(Path(__file__).resolve()))} add"


def prompt(template: str, guide: str, add: str) -> str:
    """The agents' instructions: the template with the guide's section, and the command `add`, put in their places."""
    for slot in (SECTION, ADD):
        if slot not in template:
            raise ValueError(f"{TEMPLATE.name} has no {slot}")
    return template.replace(SECTION, section(guide)).replace(ADD, add)


def write_jsonl(path: Path, rows: list) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def read_bundles(path: Path) -> list[dict]:
    """The bundles of a file, each a declaration of its own."""
    bundles = migrate_check.read_jsonl(path)
    seen: set[str] = set()
    for n, b in enumerate(bundles, 1):
        if not isinstance(b, dict) or not isinstance(b.get("decl"), str):
            raise Refused(f"{path}: bundle {n} is not an object with a `decl`")
        if b["decl"] in seen:
            raise Refused(f"{path}: `{b['decl']}` has two bundles; results are matched to bundles by name")
        seen.add(b["decl"])
    return bundles


def placed(b: dict, k: int) -> dict:
    """Bundle `b`, line `k` of BUNDLES, as a batch holds it: with its `index` added, last."""
    return {**{key: v for key, v in b.items() if key not in ("index", "retry")}, "index": k}


def retried(bundles: list[dict], checks: list, results: list) -> list[dict]:
    """The bundles to write again, from a round's results (`collect`'s) and their checks: those of the round whose
    result failed, each with its problems and the review it was given. CHECKS must cover every result."""
    given = {r.get("decl"): r for r in results if isinstance(r, dict)}
    checked = {c.get("decl"): c for c in checks if isinstance(c, dict)}
    unchecked = [d for d in given if d not in checked]
    if unchecked:
        raise Refused(f"CHECKS has no check of {len(unchecked)} results of RESULTS, among them `{unchecked[0]}`: run "
                      "migrate_check.py on RESULTS, and give its output")
    out = []
    for k, b in enumerate(bundles):
        r, c = given.get(b["decl"]), checked.get(b["decl"])
        if r is None or c.get("ok") is True:
            continue
        previous = r.get("review") if isinstance(r.get("review"), str) and not migrate_check.errored(r) else ""
        out.append({**placed(b, k), "retry": {"problems": list(c.get("problems") or []), "previous": previous}})
    return out


def split(a: argparse.Namespace) -> int:
    if (a.retry is None) != (a.results is None):
        raise Refused("--retry and --results come together: the checks of a round's results, and those results")
    if a.size < 1 or not NAME.fullmatch(a.name):
        raise Refused("--size is at least 1, and --name is a name of letters, digits, `.`, `_` and `-`")
    bundles = read_bundles(a.bundles)
    if a.retry is not None:
        chosen = retried(bundles, migrate_check.read_jsonl(a.retry), migrate_check.read_jsonl(a.results))
    else:
        chosen = [placed(b, k) for k, b in enumerate(bundles)]
    out = (a.work / a.name).resolve()
    if out.is_dir() and any(BATCH.fullmatch(p.name) or RESULT.fullmatch(p.name) for p in out.iterdir()):
        raise Refused(f"{out} holds batches or results already: give the round another --name")
    if not chosen:
        print("nothing to retry: every result of RESULTS passed its check" if a.retry else
              f"nothing to split: {a.bundles} holds no bundle", file=sys.stderr)
        return 0
    text = prompt(TEMPLATE.read_text(encoding="utf-8"), GUIDE.read_text(encoding="utf-8"), add_command())
    out.mkdir(parents=True, exist_ok=True)
    (out / "prompt.md").write_text(text, encoding="utf-8")
    for k in range(0, len(chosen), a.size):
        path = out / f"batch-{k // a.size + 1:03d}.jsonl"
        batch = chosen[k:k + a.size]
        write_jsonl(path, batch)
        print(f"{path}\t{len(batch)} bundles")
    return 0


# --- an agent's results ----------------------------------------------------------------------------------------

def parsed(line: str) -> tuple[dict | None, str | None]:
    """A line of a result file: the result it holds, when it is a JSON object, and the declaration it is of, its `decl`;
    for a line that is not JSON, None and the `decl` found in it."""
    try:
        got = json.loads(line)
    except ValueError:
        m = DECL.search(line)
        try:
            return None, json.loads(m[1]) if m else None
        except ValueError:
            return None, None
    if not isinstance(got, dict):
        return None, None
    return got, got["decl"] if isinstance(got.get("decl"), str) else None


def named_in(line: str) -> str | None:
    """The declaration a line of a result file is of (`parsed`)."""
    return parsed(line)[1]


def read_results(path: Path, decls: set[str]) -> tuple[dict[str, list[dict]], Counter, list[str]]:
    """A result file, read against its batch's declarations: the results of each (a line repeated exactly counts once),
    how many lines of each are not JSON, and what the lines that are of none of them name."""
    given: dict[str, list[dict]] = {}
    broken: Counter = Counter()
    stray: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        got, decl = parsed(line)
        if decl not in decls:
            stray.append(f"`{decl}`" if decl else "a line that names no declaration")
        elif isinstance(got, dict):
            if got not in given.setdefault(decl, []):
                given[decl].append(got)
        else:
            broken[decl] += 1
    return given, broken, stray


def batches(d: Path) -> list[Path]:
    """The batch files of a round's directory, by their number."""
    found = [(int(m[1]), p) for p in d.iterdir() if (m := BATCH.fullmatch(p.name))] if d.is_dir() else []
    return [p for _, p in sorted(found)]


def result_of(batch: Path) -> Path:
    return batch.with_name("result-" + BATCH.fullmatch(batch.name)[1] + ".jsonl")


def collect(a: argparse.Namespace) -> int:
    d = (a.work / a.name).resolve()
    files = batches(d)
    if not files:
        raise Refused(f"{d} holds no batch: split the round first")
    rows, counts, strays, silent = [], Counter(), [], []
    for path in files:
        decls = [b["decl"] for b in migrate_check.read_jsonl(path)]
        results = result_of(path)
        if results.exists():
            given, broken, stray = read_results(results, set(decls))
            strays += [f"{results.name}: {s}" for s in stray]
        else:
            given, broken = {}, Counter()
            silent.append(path.name)
        for decl in decls:
            found, bad = given.get(decl, []), broken[decl]
            if len(found) == 1 and not bad:
                rows.append(found[0])
                counts["result"] += 1
                continue
            error = "no result" if not found and not bad else "unparseable line" if not found else "two results"
            rows.append({"decl": decl, "error": error})
            counts[error] += 1
    write_jsonl(d / "results.jsonl", rows)
    print(f"collected {len(rows)} bundles of {len(files)} batches into {d / 'results.jsonl'}: "
          f"{counts['result']} results, {counts['no result']} with no result, "
          f"{counts['unparseable line']} with an unparseable line, {counts['two results']} with two results")
    if silent:
        print(f"{len(silent)} batches have no result file yet: {', '.join(silent)}")
    if strays:
        print(f"{len(strays)} lines name no bundle of their batch: {'; '.join(strays)}")
    return 0


def add(a: argparse.Namespace) -> int:
    path = a.result.resolve()
    m = RESULT.fullmatch(path.name)
    batch = path.with_name(f"batch-{m[1]}.jsonl") if m else None
    if batch is None or not batch.is_file():
        raise Refused(f"{a.result} is not a result file: it is named result-<nnn>.jsonl, beside batch-<nnn>.jsonl")
    bundles = migrate_check.read_jsonl(batch)
    bundle = next((b for b in bundles if b.get("decl") == a.decl), None)
    if bundle is None:
        raise Refused(f"`{a.decl}` is not in {batch.name}: give the `decl` of one of its bundles")
    cells, why = migrate_check.parse_cells(a.cells)
    if cells is None:
        raise Refused(f"--cells: {why}")
    review = standard.normalize(a.review.read_text(encoding="utf-8") if a.review else sys.stdin.read())
    result = {"decl": a.decl, "cells": cells, "verdict": a.verdict, "hold": (a.hold or "").strip(), "review": review}
    wrong = migrate_check.shape(result, bundle)
    if wrong:
        raise Refused("; ".join(wrong))
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    kept = [line for line in lines if line.strip() and named_in(line) != a.decl]
    replaced = len(kept) < len([line for line in lines if line.strip()])
    kept.append(json.dumps(result, ensure_ascii=False))
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".result-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(kept) + "\n")
    os.replace(tmp, path)
    done = {named_in(line) for line in kept}
    left = [b["decl"] for b in bundles if b.get("decl") not in done]
    print(f"added `{a.decl}` to {path.name}" + (", replacing its earlier line" if replaced else "")
          + f": {len(bundles) - len(left)} of {len(bundles)} bundles of {batch.name} have their line"
          + (f"; next: `{left[0]}`" if left else "; the batch is done"))
    found = migrate_check.review_problems(review, bundle)
    if found:
        print("The check finds, in this review:\n" + "\n".join(f"- {p}" for p in found)
              + "\nFix the review and add it again: the new line replaces this one.")
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="migrate_write.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("split", help="cut the bundles into batches, and write the agents' instructions")
    s.add_argument("bundles", type=Path, help="the bundles (scripts/migrate_inputs.py)")
    s.add_argument("--name", required=True, help="the round's name: its directory under --work")
    s.add_argument("--size", type=int, default=SIZE, help=f"the most bundles a batch holds (default {SIZE})")
    s.add_argument("--work", type=Path, default=WORK, help="where rounds go (default .cache/migration)")
    s.add_argument("--retry", type=Path, help="the checks of a round's results: write again those that failed")
    s.add_argument("--results", type=Path, help="that round's results, as collect merged them")
    r = sub.add_parser("add", help="add a result to a result file (for the writing agents)")
    r.add_argument("result", type=Path, help="the result file, result-<nnn>.jsonl beside batch-<nnn>.jsonl")
    r.add_argument("--decl", required=True, help="the declaration, as its bundle names it")
    r.add_argument("--verdict", required=True, choices=migrate_check.VERDICTS)
    r.add_argument("--cells", required=True, help="the eight checks: `object, choice=na, junk=error, …`")
    r.add_argument("--hold", help="why it is held (a hold only)")
    r.add_argument("--review", type=Path, help="the review's file (default: stdin)")
    c = sub.add_parser("collect", help="merge a round's result files into results.jsonl")
    c.add_argument("name", help="the round's name")
    c.add_argument("--work", type=Path, default=WORK, help="where rounds go (default .cache/migration)")
    a = p.parse_args(argv)
    try:
        return {"split": split, "add": add, "collect": collect}[a.command](a)
    except Refused as e:
        print(f"{'refused' if a.command == 'add' else 'error'}: {e}", file=sys.stderr)
        return 1 if a.command == "add" else 2
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
