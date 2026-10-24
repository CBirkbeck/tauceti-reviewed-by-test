#!/usr/bin/env python3
"""Move the pin (`tauceti` in data/settings.json) to the commit Tau Ceti's API docs show, so that the
site and the docs it links to show the same declarations: the head of the newest successful run on
main of the docs workflow (`library.docs_workflow`), or main itself when there is none. From there
back, among 30 commits, the pin takes the newest that can be extracted cheaply: whose toolchain the
extractor series has a release for and whose build Tau Ceti's cache has published. When the docs have
moved to a toolchain the series does not support, the pin waits on the last commit before the move,
and says so.

  python3 scripts/pin.py      prints moved=true or moved=false (a line for $GITHUB_OUTPUT)
"""
from __future__ import annotations

import base64
import itertools
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_settings, save_settings  # noqa: E402
from extractor import release_tags, supported, toolchain_of  # noqa: E402

CACHE = "https://cache.taucetiproject.org/revisions/{repo}/tc/{scope}/{sha}.jsonl"
#: The cache's server refuses Python's default User-Agent (403 for every commit): say who asks.
USER_AGENT = "tauceti-review (+https://github.com/CBirkbeck/tauceti-reviewed-by-test)"


def choose(commits: list[tuple[str, str]], toolchains: set[str], cached) -> str | None:
    """The newest of ``commits`` (``(sha, lean-toolchain text)``, newest first) whose toolchain is in
    ``toolchains`` and for which ``cached(sha, text)`` holds."""
    for sha, text in commits:
        if toolchain_of(text) in toolchains and cached(sha, text):
            return sha
    return None


def cache_url(repo: str, sha: str, toolchain_text: str) -> str:
    scope = toolchain_text.strip().replace("/", "--", 1).replace(":", "---", 1)
    return CACHE.format(repo=repo, scope=scope, sha=sha)


def gh_json(path: str):
    return json.loads(subprocess.run(["gh", "api", path], check=True, capture_output=True, text=True).stdout)


def docs_commit(repo: str, workflow: str) -> str | None:
    """The commit of the library's newest API docs: the head of the docs workflow's newest successful
    run on main. None when there is none, or it cannot be read."""
    try:
        runs = gh_json(f"repos/{repo}/actions/workflows/{workflow}/runs?branch=main&status=success&per_page=1")
    except subprocess.CalledProcessError:
        return None
    runs = (runs or {}).get("workflow_runs") or []
    return runs[0]["head_sha"] if runs else None


def recent_commits(repo: str, start: str = "main", n: int = 30):
    """``(sha, lean-toolchain text)`` from ``start`` back, newest first, each toolchain read only when
    asked for: the pin usually takes the first."""
    for c in gh_json(f"repos/{repo}/commits?sha={start}&per_page={n}"):
        blob = gh_json(f"repos/{repo}/contents/lean-toolchain?ref={c['sha']}")
        yield c["sha"], base64.b64decode(blob["content"]).decode("utf-8")


def cached_in(repo: str):
    def check(sha: str, text: str) -> bool:
        req = urllib.request.Request(cache_url(repo, sha, text), method="HEAD", headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status == 200
        except Exception:
            return False
    return check


def main() -> int:
    settings = load_settings()
    repo = settings["library"]["repo"]
    toolchains = set(supported(release_tags(settings["extractor"]["repo"]), settings["extractor"]["series"]))
    workflow = settings["library"].get("docs_workflow")
    start = (docs_commit(repo, workflow) if workflow else None) or "main"
    if start == settings["tauceti"]:
        print("moved=false")  # the docs show the pinned commit already
        return 0
    commits = recent_commits(repo, start)
    first = next(commits, None)
    if first and toolchain_of(first[1]) not in toolchains:
        print(f"::warning::Tau Ceti's {'docs' if start != 'main' else 'main'} ({first[0][:7]}) is on Lean "
              f"{toolchain_of(first[1])}, which extractor series {settings['extractor']['series']} has no release for",
              file=sys.stderr)
    sha = choose(itertools.chain([first] if first else [], commits), toolchains, cached_in(repo))
    if sha is None or sha == settings["tauceti"]:
        print("moved=false")
        return 0
    settings["tauceti"] = sha
    save_settings(settings)
    print("moved=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
