#!/usr/bin/env python3
"""Delete the dataset releases nobody needs any more: those older than `datasets.keep_days` days
(data/settings.json), except the newest and any whose commit an open issue of the store names.
Intake keys a form's record in the dataset of the commit the form names, and waits while that
dataset is missing, so an open form keeps its dataset.

  python3 scripts/prune.py [--dry-run]
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_settings  # noqa: E402

COMMIT = re.compile(r"^###\s+Commit\s*\n+\s*([0-9a-f]{7,40})\s*$", re.M)


def named_commits(bodies: list[str | None]) -> set[str]:
    """The commits (as written, 7 to 40 hex digits) that issue bodies give under `### Commit`."""
    return {m for b in bodies for m in COMMIT.findall(b or "")}


def to_delete(releases: list[tuple[str, str]], keep: set[str], now: datetime, days: int) -> list[str]:
    """Of ``(tag, created_at)`` releases, the `dataset-*` ones made more than ``days`` days before
    ``now``, oldest first, except the newest and those whose commit one of ``keep`` begins."""
    datasets = sorted(((t, c) for t, c in releases if t.startswith("dataset-")), key=lambda r: r[1])
    if not datasets:
        return []
    newest, cutoff = datasets[-1][0], now - timedelta(days=days)
    out = []
    for tag, created in datasets:
        commit12 = tag.removeprefix("dataset-")[:12]
        kept = any(commit12.startswith(k[:12]) for k in keep)
        if tag != newest and not kept and datetime.fromisoformat(created.replace("Z", "+00:00")) < cutoff:
            out.append(tag)
    return out


def gh_json(args: list[str]):
    return json.loads(subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout)


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    settings = load_settings()
    repo = settings["repo"]
    releases = [(r["tagName"], r["createdAt"]) for r in
                gh_json(["release", "list", "-R", repo, "--limit", "1000", "--json", "tagName,createdAt"])]
    issues = gh_json(["issue", "list", "-R", repo, "--state", "open", "--limit", "1000", "--json", "body,labels"])
    bodies = [i["body"] for i in issues if any(label["name"].startswith("evidence:") for label in i["labels"])]
    for tag in to_delete(releases, named_commits(bodies), datetime.now(timezone.utc), settings["datasets"]["keep_days"]):
        print(("would delete " if dry else "deleting ") + tag)
        if not dry:
            subprocess.run(["gh", "release", "delete", tag, "-R", repo, "--yes", "--cleanup-tag"], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
