#!/usr/bin/env python3
"""Read the declarations a reviewer can mark from Tau Ceti's Lean sources.

  python3 scripts/fetch_declarations.py [--commit SHA]

Reads the modules listed in data/modules.txt at one Tau Ceti commit (default:
the current main) from GitHub, read-only, and writes data/declarations.json.
Each declaration has its full name, kind, docstring, the source a reviewer
signs off (a definition whole, a theorem by its statement) and a hash of that
source with the layout ignored. A mark records this hash, so it goes stale
when the declaration changes. (A deployment inside Tau Ceti would hash the
elaborated terms instead; the source is enough for this test.)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = "TauCetiProject/TauCeti"
KEYWORDS = r"def|theorem|lemma|abbrev|structure|class|inductive"
DECLARATION = re.compile(r"^(?:@\[[^\]]*\]\s*)*(?P<mods>(?:(?:private|protected|noncomputable|nonrec|partial|unsafe)\s+)*)"
                         r"(?P<kind>" + KEYWORDS + r")\s+(?P<name>[^\s:({\[⦃]+)")
NAMESPACE = re.compile(r"^namespace\s+(\S+)")
SECTION = re.compile(r"^(?:@\[[^\]]*\]\s*)?(?:(?:noncomputable|public|private)\s+)*section\b")
END = re.compile(r"^end\b")
ATTRIBUTE = re.compile(r"^\s*@\[[^\]]*\]\s*$")
KIND = {"def": "def", "abbrev": "def", "theorem": "theorem", "lemma": "theorem",
        "structure": "structure", "class": "class", "inductive": "inductive"}


def fingerprint(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()[:12]


def statement(text: str) -> str:
    """A theorem up to its proof."""
    return text.split(":=", 1)[0].rstrip()


def declarations(source: str, path: str, commit: str) -> list:
    lines = source.splitlines()
    scopes, found, doc = [], [], None
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("/--"):
            start = i
            while "-/" not in lines[i]:
                i += 1
            text = "\n".join(lines[start:i + 1])
            doc = (text[3:text.rindex("-/")].strip(), i)
            i += 1
            continue
        if NAMESPACE.match(line):
            scopes.append(NAMESPACE.match(line).group(1).split("."))
        elif SECTION.match(line) or line.startswith("mutual"):
            scopes.append([])
        elif END.match(line) and scopes:
            scopes.pop()
        match = DECLARATION.match(line)
        if match:
            start = i
            i += 1
            # A declaration runs until the next line that starts at the margin.
            while i < len(lines) and (not lines[i] or lines[i][0].isspace() or lines[i].startswith(("deriving", "|"))):
                i += 1
            end = start + len("\n".join(lines[start:i]).rstrip().splitlines())
            text = "\n".join(lines[start:end])
            attached = doc and all(ATTRIBUTE.match(lines[k]) or not lines[k].strip() for k in range(doc[1] + 1, start))
            name = match.group("name")
            if "private" not in match.group("mods").split():
                prefix = [part for scope in scopes for part in scope]
                full = name[len("_root_."):] if name.startswith("_root_.") else ".".join(prefix + [name])
                kind = KIND[match.group("kind")]
                shown = statement(text) if kind == "theorem" else text
                found.append({"name": full, "kind": kind, "module": path[:-len(".lean")].replace("/", "."), "path": path,
                              "line": start + 1, "end": end, "doc": doc[0] if attached else "", "source": shown,
                              "hash": fingerprint(shown), "url": f"https://github.com/{UPSTREAM}/blob/{commit}/{path}#L{start + 1}-L{end}"})
            doc = None
            continue
        i += 1
    return found


def module_doc(source: str) -> str:
    found = re.search(r"/-!(.*?)-/", source, re.S)
    return found.group(1).strip() if found else ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--commit", help="Tau Ceti commit (default: current main)")
    args = parser.parse_args()
    commit = args.commit or subprocess.run(["gh", "api", f"repos/{UPSTREAM}/commits/main", "--jq", ".sha"],
                                           capture_output=True, text=True, check=True).stdout.strip()
    modules, found = [], []
    for path in (ROOT / "data" / "modules.txt").read_text().split():
        with urllib.request.urlopen(f"https://raw.githubusercontent.com/{UPSTREAM}/{commit}/{path}") as response:
            source = response.read().decode("utf-8")
        these = declarations(source, path, commit)
        modules.append({"module": path[:-len(".lean")].replace("/", "."), "path": path, "doc": module_doc(source),
                        "url": f"https://github.com/{UPSTREAM}/blob/{commit}/{path}", "declarations": len(these)})
        found += these
    out = {"tauceti": commit, "read": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "modules": modules, "declarations": found}
    (ROOT / "data" / "declarations.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(found)} declarations from {len(modules)} modules at {commit[:7]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
