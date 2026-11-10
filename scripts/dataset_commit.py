#!/usr/bin/env python3
"""The commit whose dataset the site is built from: the pin (`tauceti` in data/settings.json) when its
dataset is published, otherwise the newest published dataset's. follow.yml moves the pin before the new
dataset is extracted, and a dataset the checks stop is never published: until one is, the site, and the
reader of Voyager's announcements, keep to the last dataset that passed, and say so.

  python3 scripts/dataset_commit.py      prints the commit (a warning on stderr when it is not the pin)
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_settings  # noqa: E402

TITLE = re.compile(r"\b([0-9a-f]{40})\b")


def choose(pin: str, releases: list[tuple[str, str, str]]) -> str | None:
    """Of ``(tag, title, created_at)`` releases, the commit to build from: ``pin`` when `dataset-<pin12>`
    is among them, otherwise the commit the newest `dataset-*` release's title names. None when no
    dataset is published, or the newest names no commit."""
    datasets = sorted(((t, n, c) for t, n, c in releases if t.startswith("dataset-")), key=lambda r: r[2])
    if any(t == f"dataset-{pin[:12]}" for t, _, _ in datasets):
        return pin
    for tag, title, _ in reversed(datasets):
        m = TITLE.search(title or "")
        if m and m.group(1).startswith(tag.removeprefix("dataset-")):
            return m.group(1)
    return None


def main() -> int:
    settings = load_settings()
    pin, repo = settings["tauceti"], settings["repo"]
    out = subprocess.run(["gh", "release", "list", "-R", repo, "--limit", "1000", "--json", "tagName,name,createdAt"],
                         check=True, capture_output=True, text=True).stdout
    commit = choose(pin, [(r["tagName"], r["name"], r["createdAt"]) for r in json.loads(out)])
    if commit is None:
        print(f"::error::no dataset is published for the pin {pin[:12]}, nor any other", file=sys.stderr)
        return 1
    if commit != pin:
        print(f"::warning::the pinned dataset ({pin[:12]}) is not published: building from {commit[:12]}, "
              "the newest that is", file=sys.stderr)
    print(commit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
