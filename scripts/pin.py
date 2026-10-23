#!/usr/bin/env python3
"""Move the pin (`tauceti` in data/settings.json) to the newest commit of Tau Ceti's main that can be
extracted cheaply: among the last 30, the newest whose toolchain the extractor series has a release
for and whose build Tau Ceti's cache has published. When main has moved to a toolchain the series
does not support, the pin waits on the last commit before the move, and says so.

  python3 scripts/pin.py      prints moved=true or moved=false (a line for $GITHUB_OUTPUT)
"""
from __future__ import annotations

import base64
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


def recent_commits(repo: str, n: int = 30) -> list[tuple[str, str]]:
    out = []
    for c in gh_json(f"repos/{repo}/commits?sha=main&per_page={n}"):
        blob = gh_json(f"repos/{repo}/contents/lean-toolchain?ref={c['sha']}")
        out.append((c["sha"], base64.b64decode(blob["content"]).decode("utf-8")))
    return out


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
    commits = recent_commits(repo)
    if commits and toolchain_of(commits[0][1]) not in toolchains:
        print(f"::warning::Tau Ceti's main ({commits[0][0][:7]}) is on Lean {toolchain_of(commits[0][1])}, "
              f"which extractor series {settings['extractor']['series']} has no release for", file=sys.stderr)
    sha = choose(commits, toolchains, cached_in(repo))
    if sha is None or sha == settings["tauceti"]:
        print("moved=false")
        return 0
    settings["tauceti"] = sha
    save_settings(settings)
    print("moved=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
