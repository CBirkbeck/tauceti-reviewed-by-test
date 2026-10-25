"""What a run needs on the server, made ready at its start.

Under the answerer's home (`~/tauceti-answerer`): `review`, a clone of the review repository, pulled;
`datasets/<commit>`, the dataset of the commit the site shows (`evidence-store dataset`); `work/TauCeti`,
the library at that commit with its builds from the Lake caches (Mathlib's and Tau Ceti's), prepared again
only when the commit moves; `work/TauCeti-pr`, a second clone for docstring fixes, on the library's
`main`; `state/`, its memory. The API key is read from `~/.config/tauceti/secrets/anthropic.key`.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .state import State


@dataclass
class Paths:
    home: Path

    @classmethod
    def default(cls) -> "Paths":
        return cls(Path(os.environ.get("ANSWERER_HOME", Path.home() / "tauceti-answerer")))

    review = property(lambda s: s.home / "review")
    work = property(lambda s: s.home / "work" / "TauCeti")
    prwork = property(lambda s: s.home / "work" / "TauCeti-pr")
    datasets = property(lambda s: s.home / "datasets")
    scratch = property(lambda s: s.home / "sandbox")
    state = property(lambda s: s.home / "state" / "state.json")
    key = property(lambda s: Path(os.environ.get("ANSWERER_KEY", Path.home() / ".config/tauceti/secrets/anthropic.key")))


def sh(argv: list, cwd: Path | None = None, timeout: int = 3600) -> str:
    return subprocess.run([str(a) for a in argv], cwd=cwd, capture_output=True, text=True, check=True,
                          timeout=timeout).stdout


@dataclass
class Ready:
    settings: dict
    commit: str
    dataset: Path
    lean_path: str
    toolchain: Path


def prepare(p: Paths, state: State, log: Callable[[str], None]) -> Ready:
    sh(["git", "-C", p.review, "pull", "-q", "--ff-only"])
    settings = json.loads((p.review / "data" / "settings.json").read_text(encoding="utf-8"))
    commit, repo = settings["tauceti"], settings["library"]["repo"]
    dataset = p.datasets / commit[:12]
    if not dataset.exists():
        log(f"the dataset of {commit[:12]}")
        sh(["evidence-store", "dataset", "--store", p.review / "evidence", "--commit", commit, "--out", dataset], cwd=p.review)
    for d in (p.work, p.prwork):
        if not d.exists():
            d.parent.mkdir(parents=True, exist_ok=True)
            sh(["git", "clone", "-q", "--filter=blob:none", f"https://github.com/{repo}", d], timeout=7200)
    if state.prepared.get("work") != commit or not state.prepared.get("lean_path"):
        log(f"the library at {commit[:12]}, built from the Lake caches")
        sh(["git", "-C", p.work, "fetch", "-q", "origin", commit])
        sh(["git", "-C", p.work, "checkout", "-q", "-f", "--detach", commit])
        cache(p.work)
        state.prepared.update(work=commit, lean_path=sh(["lake", "env", "printenv", "LEAN_PATH"], cwd=p.work).strip())
        state.save()
    toolchain = Path(sh(["elan", "which", "lean"], cwd=p.work).strip()).resolve().parent.parent
    p.scratch.mkdir(parents=True, exist_ok=True)
    return Ready(settings, commit, dataset, state.prepared["lean_path"], toolchain)


def cache(work: Path) -> None:
    """Mathlib's and the library's builds at the checked-out commit, from their Lake caches."""
    sh(["lake", "exe", "cache", "get"], cwd=work, timeout=7200)
    sh(["bash", "scripts/lake-cache-get.sh", "."], cwd=work, timeout=7200)


def build(work: Path, modules: list[str]) -> str | None:
    """Builds `modules` at the checkout (from the cache where it can): None, or why it failed."""
    if not modules:
        return None
    try:
        sh(["lake", "build", *modules], cwd=work, timeout=3600)
    except subprocess.CalledProcessError as e:
        return (e.stdout + e.stderr).strip()[-1500:]
    except subprocess.TimeoutExpired:
        return "the build did not finish within an hour"
    return None


def roadmaps(repo: str = "TauCetiProject/TauCetiRoadmap") -> set[str]:
    """The roadmap's area names, for a pull request's `Roadmap:` line."""
    names = set()
    for d in ("TauCetiRoadmap", "Completed"):
        out = sh(["gh", "api", f"repos/{repo}/contents/{d}", "--jq", '.[] | select(.type == "dir") | .name'])
        names |= set(out.split())
    return names
