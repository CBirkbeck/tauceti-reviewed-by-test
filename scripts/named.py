#!/usr/bin/env python3
"""The named results and notable definitions of Tau Ceti: the declarations worth
looking at first, since most of a library is API, glue and steps of proofs.

  python3 scripts/named.py roadmaps <TauCetiRoadmap checkout>
  python3 scripts/named.py voyager <posts.json>

Two sources name them:

- the roadmaps: each roadmap's generated STATUS.md lists its "Named results" and
  "Notable definitions and infrastructure", each a bold name, a sentence and
  links to the declarations. `roadmaps` rewrites data/named-roadmaps.json from a
  checkout of TauCetiRoadmap (the "Follow Tau Ceti" workflow does this daily);
- Voyager, the bot that announces new results on the Lean Zulip: each bullet of
  a post is a bold link to a declaration's docs page, a sentence and the pull
  requests. `voyager` appends the announcements in an export of its topic
  (the messages as the Zulip API returns them) to reviews/named.jsonl, the
  ledger that `Named:` lines on the marking issue also add to (scripts/reviews.py).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROADMAPS = ROOT / "data" / "named-roadmaps.json"
LEDGER = ROOT / "reviews" / "named.jsonl"
DOCS_LINK = re.compile(r"\[`?([^\]`]+?)`?\]\((https://taucetiproject\.github\.io/TauCeti/docs/[^)\s]*?#([^)\s]+))\)")
STATUS_BULLET = re.compile(r"^- \*\*(.+?)\*\*\s*(?:—|-)\s*(.*)$")
POST_BULLET = re.compile(r"^- \*\*\[(.+?)\]\((https://[^)\s]+)\)\*\*[†*]*\s*(?:—|-)?\s*(.*)$")
SECTIONS = {"Named results": "result", "Notable definitions and infrastructure": "definition", "Notable definitions": "definition"}


def plain(text: str) -> str:
    """A sentence without its declaration links, pull request numbers or trailing clutter."""
    text = re.sub(r"\s*\(\[`?[^\]]+`?\]\([^)]+\)\)", "", text)
    text = DOCS_LINK.sub(lambda m: m.group(1), text)
    text = re.sub(r"\s*\((?:TauCeti#\d+(?:,\s*)?)+\)\s*$", "", text)
    text = re.sub(r"\s+,", ",", text)
    return " ".join(text.split())


def roadmap_names(root: Path) -> list:
    """Every named result and notable definition in the roadmaps' STATUS.md files."""
    found = []
    for path in sorted(root.glob("TauCetiRoadmap/*/STATUS.md")) + sorted(root.glob("Completed/*/STATUS.md")):
        what = None
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("#"):
                what = SECTIONS.get(line.lstrip("#").strip()) if line.startswith("### ") else None
                continue
            bullet = STATUS_BULLET.match(line)
            if what and bullet:
                for link in DOCS_LINK.finditer(bullet.group(2)):
                    found.append({"decl": link.group(3), "name": bullet.group(1), "what": what, "about": plain(bullet.group(2)),
                                  "source": {"roadmap": path.parent.name, "path": path.relative_to(root).as_posix()}})
    return found


def voyager_names(posts: list) -> list:
    """Every announcement in Voyager's posts: the declaration its link points to."""
    found = []
    for post in posts:
        what = "result"
        at = datetime.fromtimestamp(post["timestamp"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for line in post["content"].splitlines():
            heading = line.strip().strip("*").strip()
            if heading in SECTIONS:
                what = SECTIONS[heading]
                continue
            bullet = POST_BULLET.match(line)
            if bullet and "#" in bullet.group(2):
                found.append({"decl": bullet.group(2).split("#", 1)[1], "name": bullet.group(1), "what": what,
                              "about": plain(bullet.group(3)), "source": {"voyager": post["id"], "prs": [int(n) for n in re.findall(r"TauCeti#(\d+)", bullet.group(3))]},
                              "at": at})
    return found


def named_by_declaration(index: dict, roadmap: list, ledger: list) -> dict:
    """Each named declaration of the index: the first name it was given (the roadmaps
    first, then the ledger in order), and every source that names it."""
    kinds = {item["name"]: item["kind"] for item in index["declarations"]}
    found = {}
    for entry in list(roadmap) + list(ledger):
        if entry["decl"] not in kinds:
            continue
        named = found.setdefault(entry["decl"], {"name": entry["name"], "what": entry["what"], "about": entry.get("about", ""), "sources": []})
        named["sources"].append({key: entry[key] for key in ("name", "source", "at", "by", "kind", "agent") if key in entry})
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", choices=["roadmaps", "voyager"])
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    if args.source == "roadmaps":
        found = roadmap_names(args.path)
        ROADMAPS.write_text(json.dumps(found, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{len(found)} named declarations from {len({n['source']['roadmap'] for n in found})} roadmaps")
        return 0
    known = {(entry["decl"], json.dumps(entry.get("source"), sort_keys=True))
             for entry in (json.loads(line) for line in LEDGER.read_text(encoding="utf-8").splitlines() if line.strip())} if LEDGER.exists() else set()
    added = 0
    with LEDGER.open("a", encoding="utf-8") as handle:
        for entry in voyager_names(json.loads(args.path.read_text(encoding="utf-8"))):
            if (entry["decl"], json.dumps(entry["source"], sort_keys=True)) in known:
                continue
            handle.write(json.dumps({"schema": "named/v1", **entry, "by": "voyager", "kind": "agent", "agent": "Voyager"}, ensure_ascii=False) + "\n")
            added += 1
    print(f"{added} announcements added to {LEDGER.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
