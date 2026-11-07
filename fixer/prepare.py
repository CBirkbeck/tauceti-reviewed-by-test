"""What a run needs on the server, made ready at its start.

Under the fixer's home (`~/tauceti-fixer`): `review`, a clone of the review repository, pulled, which the run reads
the reviews from (its store) and runs from; `work/TauCeti`, its own clone of the library, checked out at the commit
the site shows, with Mathlib's and the library's builds from their Lake caches (fetched again only when that commit
moves), where the model edits and builds; `sandbox`, where a check's file is written; `state/fixer.json`, its memory.
The API key is read from `~/.config/tauceti/secrets/anthropic.key`, as the answerer's is, and never reaches the
model's tools or the sandbox.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from answerer.prepare import cache, sh, site_commit

from .state import State


@dataclass
class Paths:
    home: Path

    @classmethod
    def default(cls) -> "Paths":
        return cls(Path(os.environ.get("FIXER_HOME", Path.home() / "tauceti-fixer")))

    review = property(lambda s: s.home / "review")
    work = property(lambda s: s.home / "work" / "TauCeti")
    scratch = property(lambda s: s.home / "sandbox")
    state = property(lambda s: s.home / "state" / "fixer.json")
    key = property(lambda s: Path(os.environ.get("FIXER_KEY", Path.home() / ".config/tauceti/secrets/anthropic.key")))


@dataclass
class Ready:
    settings: dict
    commit: str
    lean_path: str
    toolchain: Path
    login: str  # the GitHub account it pushes and posts through


def prepare(p: Paths, state: State, log: Callable[[str], None], commit: str | None = None) -> Ready:
    sh(["git", "-C", p.review, "pull", "-q", "--ff-only"])
    settings = json.loads((p.review / "data" / "settings.json").read_text(encoding="utf-8"))
    commit, repo = commit or site_commit(settings), settings["library"]["repo"]
    if not p.work.exists():
        p.work.parent.mkdir(parents=True, exist_ok=True)
        log(f"cloning {repo}")
        sh(["git", "clone", "-q", "--filter=blob:none", f"https://github.com/{repo}", p.work], timeout=7200)
    sh(["git", "-C", p.work, "fetch", "-q", "origin", "main"], timeout=1800)
    sh(["git", "-C", p.work, "fetch", "-q", "origin", commit], timeout=1800)
    sh(["git", "-C", p.work, "checkout", "-q", "-f", "--detach", commit])
    sh(["git", "-C", p.work, "clean", "-fdq", "--", "TauCeti"])
    # Its commits: its own name, linked to the account that pushes them.
    login = sh(["gh", "api", "user", "--jq", ".login"]).strip()
    uid = sh(["gh", "api", f"users/{login}", "--jq", ".id"]).strip()
    sh(["git", "-C", p.work, "config", "user.name", "Tau Ceti review fixer"])
    sh(["git", "-C", p.work, "config", "user.email", f"{uid}+{login}@users.noreply.github.com"])
    if state.prepared.get("work") != commit or not state.prepared.get("lean_path"):
        log(f"the library at {commit[:12]}, built from the Lake caches")
        cache(p.work)
        state.prepared.update(work=commit, lean_path=sh(["lake", "env", "printenv", "LEAN_PATH"], cwd=p.work).strip())
        state.save()
    packages = p.work / ".lake" / "packages"
    if packages.is_symlink():  # the sandbox shows nothing outside the checkout (fixer/tools.py, build_command)
        raise SystemExit(f"{packages} links to {packages.resolve()}: the fixer's checkout needs its own packages")
    toolchain = Path(sh(["elan", "which", "lean"], cwd=p.work).strip()).resolve().parent.parent
    p.scratch.mkdir(parents=True, exist_ok=True)
    return Ready(settings, commit, state.prepared["lean_path"], toolchain, login)
