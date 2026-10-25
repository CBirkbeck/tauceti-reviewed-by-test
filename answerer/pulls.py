"""Docstring fixes proposed to the library as pull requests, and whether they have merged.

They are made in a second checkout of the library (`work`), kept on its `main`: the edits are checked
against the declaration's file there (`docfix.apply_edits`), made on a branch `answerer/<record id>`,
and the module is built (by `build`, sandboxed on the server) before the branch is pushed and the
pull request opened. The pull request says where the no came from and that only a docstring changes,
names the roadmap area the model gave if it is one of the roadmap's (else `none`), and says that the
answerer, an AI agent, proposed it, with the model that did.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from .clean import clean
from .docfix import apply_edits
from .model import who
from .post import gh as run_gh


class PullRequests:
    def __init__(self, work: Path, repo: str, build: Callable[[str], tuple[bool, str]], roadmaps: Callable[[], set[str]],
                 site: str, gh: Callable[[list[str], str | None], str] = run_gh, dry: bool = False):
        self.work, self.repo, self.build, self.roadmaps, self.site, self.gh, self.dry = \
            Path(work), repo, build, roadmaps, site, gh, dry

    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", str(self.work), *args], capture_output=True, text=True, check=True,
                              timeout=600).stdout

    def propose(self, item: Any, decl: dict, verdict: dict, by: dict) -> tuple[int | None, str | None]:
        """The pull request's number, or None and why there is none."""
        path, edits = decl.get("path"), verdict.get("edits") or []
        if not path:
            return None, "the declaration is not in the library's own source"
        if any(e.get("file") != path for e in edits):
            return None, f"an edit is not to the declaration's own file, {path}"
        self.git("fetch", "-q", "origin", "main")
        text = self.git("show", f"origin/main:{path}")
        new, err = apply_edits(text, edits)
        if err:
            return None, err
        if new == text:
            return None, "the edits change nothing"
        branch, module = f"answerer/{item.id}", path[:-len(".lean")].replace("/", ".")
        self.git("checkout", "-q", "-B", branch, "origin/main")
        (self.work / path).write_text(new, encoding="utf-8")
        ok, out = self.build(module)
        if not ok:
            self.git("checkout", "-q", "-f", "--detach", "origin/main")
            return None, f"{module} did not build with the edits: {out.strip()[-500:]}"
        title = title_of(verdict.get("pr_title", ""), decl["name"])
        self.git("commit", "-q", "-am", f"{title}\n\nProposed by the Tau Ceti review answerer ({by['model']}).")
        if self.dry:  # built and committed here, not pushed: -1 for the pull request it would have opened
            self.git("checkout", "-q", "-f", "--detach", "origin/main")
            return -1, None
        self.git("push", "-q", "-f", "origin", branch)
        out = self.gh(["gh", "pr", "create", "--repo", self.repo, "--head", branch, "--base", "main", "--title", title,
                       "--body-file", "-"], self.body(item, decl, verdict, by, module))
        self.git("checkout", "-q", "-f", "--detach", "origin/main")
        m = re.search(r"/pull/(\d+)", out)
        return (int(m.group(1)), None) if m else (None, f"no pull request was opened: {out.strip()[:300]}")

    def body(self, item: Any, decl: dict, verdict: dict, by: dict, module: str) -> str:
        roadmap = verdict.get("roadmap", "")
        roadmap = roadmap if roadmap in self.roadmaps() else "none"
        what = "a no (an answer that it is not correctly stated)" if item.kind == "problem" else "a suggestion"
        return (f"{clean(verdict.get('reply', ''), limit=6000)}\n\n"
                f"Raised on the [Tau Ceti review site]({self.site}#/d/{decl['name']}) as {what} by "
                f"{who((item.record or {}).get('by') or {})}. The review answerer, an AI agent, checked it and proposes "
                f"this change to the docstring only: the Lean is unchanged.\n\n"
                f"Validation: each edit lies inside a doc comment and adds no comment delimiters or double quotes, "
                f"its lines are at most 100 characters, and `lake build {module}` succeeds.\n\n"
                f"Roadmap: {roadmap}\n\n"
                f"🤖 Proposed by the Tau Ceti review answerer ({by['model']}).\n")

    def state(self, number: int) -> tuple[str, str | None]:
        """("OPEN" | "CLOSED" | "MERGED", the merge commit if merged)."""
        out = json.loads(self.gh(["gh", "pr", "view", str(number), "--repo", self.repo, "--json", "state,mergeCommit"]))
        return out.get("state", ""), ((out.get("mergeCommit") or {}).get("oid"))


def title_of(title: str, name: str) -> str:
    title = " ".join((title or "").split())
    title = re.sub(r"[@#]", "", title)[:90]
    if not title.startswith("docs: "):
        title = f"docs: correct the docstring of {name.rsplit('.', 1)[-1]}" if not title else "docs: " + title
    return title
