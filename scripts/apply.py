#!/usr/bin/env python3
"""Write the review lines into Tau Ceti's own sources, in a fork.

  python3 scripts/apply.py --clone DIR [--site URL] [--reviews reviews.json]

Each file's module docstring gains one line under its title, linking to the
file's page on the review site, where any of its declarations can be reviewed.
Each reviewed declaration's docstring gains the counts: how many people and AI
agents reviewed it, and how many tests it passes. A reviewed declaration with no
docstring — 8% of them, mostly API lemmas — gets one holding those lines, so that
a review is never lost between the site and the code. Nothing else is touched, and
running it again with the same marks changes nothing, so a fork can be kept up
to date by rerunning it.

The lines are the same ones the page shows, and only a line holding a URL passes
100 characters, which is what Mathlib's longLine linter allows. This is meant to
run against a **fork** (CBirkbeck/TauCeti): the trial keeps Tau Ceti itself
untouched.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_declarations import read_clone  # noqa: E402
from reviews import count_text, test_count_text  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LINK_TEXT = "Reviews and tests of this file"
DECL_LINK_TEXT = "Who and which"
MARK_LINE = re.compile(r"^(?:Reviewed-by|Tested by):.*$")
LINK_LINE = re.compile(r"^\[(?:" + LINK_TEXT + "|" + DECL_LINK_TEXT + r")\]\(\S+\)\s*$")


def lines_for(entry: dict, name: str = "", site: str = "") -> list:
    """What a declaration's docstring carries: the counts, then the link to who
    reviewed it and which tests it passes. The counts stay short and the link has
    a line of its own, since only a line with a URL may pass 100 characters."""
    found = [f"{trailer}: {count_text(n['people'], n['ai'])}" for trailer, n in (entry.get("tally") or {}).items()
             if n["people"] or n["ai"]]
    tests = (entry.get("tests") or {}).get("tally") or {}
    counted = test_count_text(tests.get("unit", 0), tests.get("results", 0))
    found += [f"Tested by: {counted}"] if counted else []
    return found + [f"[{DECL_LINK_TEXT}]({site}#d={name})"] if found and name else found


def ours(line: str) -> bool:
    return bool(MARK_LINE.match(line.strip()) or LINK_LINE.match(line.strip()))


def without_ours(lines: list) -> list:
    """The docstring's own lines: what we wrote last time removed, with the blank
    line we put in front of it, so that running again leaves the file as it was."""
    kept, n = [], len(lines)
    i = 0
    while i < n:
        if ours(lines[i]):
            if kept and not kept[-1].strip():
                kept.pop()
            while i < n and (ours(lines[i]) or (i + 1 < n and not lines[i].strip() and ours(lines[i + 1]))):
                i += 1
            continue
        kept.append(lines[i])
        i += 1
    return kept


def docstring_before(lines: list, start: int):
    """(first, last) lines of the docstring that belongs to the declaration on
    `start`, skipping attributes between them, or None."""
    i = start - 1
    while i >= 0 and (not lines[i].strip() or lines[i].lstrip().startswith("@[")):
        i -= 1
    if i < 0 or not lines[i].rstrip().endswith("-/"):
        return None
    last = i
    while i >= 0 and not lines[i].lstrip().startswith("/--"):
        i -= 1
        if i >= 0 and lines[i].lstrip().startswith("/-!"):
            return None
    return (i, last) if i >= 0 else None


def fresh_docstring(counts: list, indent: str) -> list:
    """A docstring holding only the review lines, for a declaration that had none."""
    fresh = [indent + line for line in ["/-- " + counts[0]] + counts[1:]]
    fresh[-1] += " -/"
    return fresh


def above_attributes(lines: list, start: int) -> int:
    """Where a docstring would go: above the declaration's attributes."""
    i = start
    while i - 1 >= 0 and lines[i - 1].lstrip().startswith("@["):
        i -= 1
    return i


def module_block(lines: list):
    """(first, last) lines of the module docstring, or None."""
    for i, line in enumerate(lines):
        if line.startswith("/-!"):
            for j in range(i, len(lines)):
                if lines[j].rstrip().endswith("-/"):
                    return i, j
            return None
    return None


def write_module_link(lines: list, module: str, site: str) -> list:
    """The link under the module docstring's title, and nothing else moved."""
    block = module_block(lines)
    if not block:
        return lines
    first, last = block
    if lines[first].strip() != "/-!":
        return lines
    body = without_ours(lines[first:last + 1])
    title = next((i for i in range(1, len(body)) if body[i].strip()), None)
    if title is None or body[title].strip() == "-/":
        return lines
    link = f"[{LINK_TEXT}]({site}#m={module})"
    return lines[:first] + body[:title + 1] + ["", link] + body[title + 1:] + lines[last + 1:]


def write_counts(lines: list, item: dict, entry: dict, site: str = "") -> list:
    """The counts at the end of a declaration's docstring, in place of the last ones,
    with the rest of the docstring left exactly as it is."""
    start = item["line"] - 1
    counts = lines_for(entry, item["name"], site)
    block = docstring_before(lines, start)
    if not block:
        # No docstring: the review lines become one, so the code still carries it.
        if not counts:
            return lines
        at = above_attributes(lines, start)
        indent = lines[start][:len(lines[start]) - len(lines[start].lstrip())]
        return lines[:at] + fresh_docstring(counts, indent) + lines[at:]
    first, last = block
    indent = lines[first][:len(lines[first]) - len(lines[first].lstrip())]
    body = lines[first:last + 1]
    # Take the closing `-/` off first: it may sit on a line we wrote last time.
    body[-1] = body[-1].rstrip()[:-len("-/")].rstrip()
    alone = not body[-1].strip()
    if alone:
        body.pop()
    # An opening line carrying one of ours ("/-- Reviewed-by: …") splits in two.
    head, _, rest = body[0].partition("/--")
    if rest.strip() and ours(rest.strip()):
        body[0:1] = [head + "/--", rest.strip()]
    body = without_ours(body)
    if not [line for line in body if line.strip() and line.strip() != "/--"]:
        # The docstring was one we wrote: rewrite it, or take it away again.
        return lines[:first] + (fresh_docstring(counts, indent) if counts else []) + lines[last + 1:]
    new = body + ([""] + counts if counts else [])
    new = new + [indent + "-/"] if alone and not counts else new[:-1] + [new[-1] + " -/"]
    return lines[:first] + new + lines[last + 1:]


def apply_to_checkout(root: Path, reviews: dict, site: str, index: dict | None = None) -> dict:
    """Write the lines into every module of the checkout. Returns what changed."""
    index = index or read_clone(root, "HEAD")
    entries = reviews.get("declarations", {})
    everything, with_counts = {}, {}
    for item in index["declarations"]:
        everything.setdefault(item["module"], []).append(item)
        if item["name"] in entries and lines_for(entries[item["name"]]):
            with_counts.setdefault(item["module"], []).append(item)
    files, touched = 0, 0
    for module in index["modules"]:
        path = root / module["path"]
        before = path.read_text(encoding="utf-8")
        lines = before.splitlines()
        # Every declaration of a file that already carries our lines, so that a
        # declaration whose marks have gone loses them again.
        mine = with_counts.get(module["module"], [])
        if any(ours(line) for line in lines):
            mine = everything.get(module["module"], [])
        # The declarations first, from the bottom up, so their line numbers still
        # hold; the module link last, since it shifts everything under it.
        for item in sorted(mine, key=lambda item: -item["line"]):
            lines = write_counts(lines, item, entries.get(item["name"], {}), site)
            touched += lines_for(entries.get(item["name"], {})) != []
        lines = write_module_link(lines, module["module"], site)
        after = "\n".join(lines) + ("\n" if before.endswith("\n") else "")
        if after != before:
            path.write_text(after, encoding="utf-8")
            files += 1
    return {"files": files, "declarations": touched, "modules": len(index["modules"])}


def commit_message(reviews: dict, site: str) -> str:
    """The commit that writes the lines, ending in one git trailer per mark on a
    current version, as the kernel's `b4 trailers -u` collects Reviewed-by replies."""
    marks = [(name, mark) for name, entry in sorted(reviews.get("declarations", {}).items())
             for mark in entry.get("marks", []) if mark.get("current")]
    names = sorted({name for name, _ in marks})
    signer = lambda m: f"{m['agent']} (AI) via @{m['by']}" if m["kind"] == "agent" else f"@{m['by']}"
    trailers = "\n".join(f"{mark['trailer']}: {signer(mark)} <{name}@{mark['hash']}>" for name, mark in marks)
    return (f"Review lines: {len(marks)} mark{'s' if len(marks) != 1 else ''} on {len(names)} declaration"
            f"{'s' if len(names) != 1 else ''}\n\nEach file links to its page on the review site, and each reviewed "
            f"declaration carries its counts, from {site}reviews.json.\n\n{trailers}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--clone", type=Path, required=True, help="a checkout of the Tau Ceti fork")
    parser.add_argument("--site", default="https://cbirkbeck.github.io/tauceti-reviewed-by-test/")
    parser.add_argument("--reviews", help="reviews.json (default: the site's)")
    parser.add_argument("--message", type=Path, help="write the commit message here")
    args = parser.parse_args()
    if args.reviews:
        reviews = json.loads(Path(args.reviews).read_text(encoding="utf-8"))
    else:
        with urllib.request.urlopen(args.site.rstrip("/") + "/reviews.json", timeout=60) as handle:
            reviews = json.load(handle)
    summary = apply_to_checkout(args.clone, reviews, args.site)
    if args.message:
        args.message.write_text(commit_message(reviews, args.site), encoding="utf-8")
    print(f"{summary['files']} file(s) changed, {summary['declarations']} declaration(s) with counts, "
          f"{summary['modules']} module(s) linked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
