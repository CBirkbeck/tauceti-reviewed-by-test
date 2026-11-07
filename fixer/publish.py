"""What the run does with a result. The model never pushes, opens or posts anything: this does, after its own checks.

A change (`pr`) is published only if the checkout's changes pass the gate: only Lean files below `TauCeti/`
changed; no added line has what Tau Ceti's source guard refuses or what could run code (`sorry`, `set_option`,
`#eval`, elaborators, macros, initializers, `unsafe`, `IO`, a double quote, …); at most `MAX_ADDED` lines added; and
the changed modules, with every module importing them, build again here, sealed off. Then it is committed on a
branch of its own (`fixer/<record>-<time>`), pushed to the library's repository, the pull request opened, and the
review answered on its issue: `/addressed <pull request>`, which records the link (scripts/pr_links.py).

An existing pull request (`already_addressed`) is linked the same way once GitHub confirms it is one of the
library's or Mathlib's and was not closed without merging. Mathlib's declarations (`mathlib`): the reply says what
a person should propose upstream, and the review is listed for a person; nothing is pushed. `no_change` posts
nothing (the answerer answers every open review within the hour); `gave_up` is listed for a person.
"""
from __future__ import annotations

import datetime as dt
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from answerer.clean import clean
from answerer.model import who
from answerer.post import mark

from .pick import Review
from .tools import WorkTools

MAX_ADDED = 1500
REPLY_LIMIT = 1200
#: What an added line may not have: Tau Ceti's source guard (AGENTS.md), and anything that could run code.
FORBIDDEN = re.compile(
    # anywhere on the line
    r"\bsorry\b|\badmit\b|\bnative_decide\b|\bset_option\b|#eval\b|#exit\b|#print\b|#check\b|#synth\b|#guard\b|"
    r"\brun_cmd\b|\brun_elab\b|\brun_tac\b|\brun_meta\b|\bby_elab\b|\bunsafe\b|\bimplemented_by\b|@\[\s*extern\b|"
    r"\bIO\b|\bSystem\.|\bLean\.(?:Elab|Meta|Parser|Syntax|Expr|Environment)\b|\binclude_str\b|\bdbg_trace\b|"
    r"\bofReduceBool\b|\bguard_min_heartbeats\b|#count_heartbeats|\"|"
    # a command, at the start of the line
    r"^\s*(?:@\[[^\]]*\]\s*)?(?:(?:private|protected|local|scoped|public|noncomputable)\s+)*"
    r"(?:meta|macro|macro_rules|elab|elab_rules|syntax|declare_syntax_cat|initialize|builtin_initialize|axiom|"
    r"notation|infix|infixl|infixr|prefix|postfix)\b|"
    r"^\s*(?:public\s+)?(?:meta\s+)?import\s+(?:Lean|Lake|Mathlib\.Lean)\b",
    re.M)
FOOTER = "🤖 Proposed by the Tau Ceti review fixer ({model}), an AI agent, from a review on the Tau Ceti review site."


@dataclass
class Gate:
    ok: bool
    why: str
    files: list[str]
    modules: list[str]


def git(work: Path, *args: str, check: bool = True) -> str:
    return subprocess.run(["git", "-C", str(work), *args], capture_output=True, text=True, check=check,
                          timeout=600).stdout


def changes(work: Path) -> list[tuple[str, str]]:
    """(status, path) of every change in the checkout, new files included (`git status --porcelain`)."""
    out = []
    for line in git(work, "status", "--porcelain", "--untracked-files=all").splitlines():
        status, path = line[:2], line[3:]
        if " -> " in path:  # a rename: both sides
            old, new = path.split(" -> ", 1)
            out += [("D ", old), ("A ", new)]
        else:
            out.append((status, path))
    return out


def added_lines(work: Path) -> list[tuple[str, str]]:
    """(file, line) of every line the changes add."""
    out, current = [], ""
    for line in git(work, "diff", "-U0", "--", ".").splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else line[4:]
        elif line.startswith("+") and not line.startswith("+++"):
            out.append((current, line[1:]))
    for f in git(work, "ls-files", "--others", "--exclude-standard").split():
        if (work / f).is_file() and not (work / f).is_symlink():  # a link is refused by the gate, never read
            out += [(f, l) for l in (work / f).read_text(encoding="utf-8", errors="replace").splitlines()]
    return out


def module_of(path: str) -> str:
    return path[:-len(".lean")].replace("/", ".")


def gate(work: Path, tools: WorkTools, root: str = "TauCeti") -> Gate:
    """Whether the checkout's changes may be published, and the modules built to check them."""
    found = changes(work)
    if not found:
        return Gate(False, "there are no changes", [], [])
    bad = [p for _, p in found if not (p.startswith(root + "/") and p.endswith(".lean"))]
    if bad:
        return Gate(False, f"files outside {root}/ or not Lean changed: {', '.join(bad[:5])}", [], [])
    links = [p for _, p in found if (work / p).is_symlink() or ((work / p).exists() and not (work / p).is_file())]
    if links:
        return Gate(False, f"not plain files: {', '.join(links[:5])}", [], [])
    added = added_lines(work)
    if len(added) > MAX_ADDED:
        return Gate(False, f"{len(added)} lines added, more than {MAX_ADDED}", [], [])
    for f, line in added:
        m = FORBIDDEN.search(line)
        if m:
            return Gate(False, f"an added line of {f} has {m.group(0)!r}, which Tau Ceti refuses or which could run code", [], [])
    files = sorted({p for _, p in found})
    kept = [p for s, p in found if "D" not in s]
    modules = sorted({module_of(p) for p in kept})
    for p in sorted({p for _, p in found}):
        out, err = tools.t_importers(module_of(p))
        if not err and out != "No file imports it directly.":
            modules += [module_of(q) for q in out.split() if (work / q).exists()]
    modules = sorted(set(modules))
    for i in range(0, len(modules), 8):
        out, failed = tools.build(modules[i:i + 8])
        if failed:
            return Gate(False, f"the build failed: {out[-1500:]}", files, modules)
    return Gate(True, "", files, modules)


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M")


def body(review: Review, result: dict, model: str, gate_: Gate, site: str, review_repo: str, roadmap: str) -> str:
    what = "a no (an answer that it is not correctly stated)" if review.kind == "problem" else "a suggestion"
    issue = f"https://github.com/{review_repo}/issues/{review.issue}"
    built = ", ".join(f"`{m}`" for m in gate_.modules[:12]) + (" and more" if len(gate_.modules) > 12 else "")
    return (f"{clean(result.get('pr_body', ''), limit=6000)}\n\n"
            f"Raised on the [Tau Ceti review site]({site}#/d/{review.decl}) as {what} on `{review.decl}` by "
            f"{who((review.record or {}).get('by') or {})}: {issue}.\n\n"
            f"Validation by the fixer's run, apart from the model: only Lean files below `TauCeti/` change, no added line "
            f"has what Tau Ceti's source guard refuses, and {built} build sealed off.\n\n"
            f"Roadmap: {roadmap}\n\n" + FOOTER.format(model=model) + "\n")


def title_of(result: dict, review: Review) -> str:
    title = " ".join((result.get("pr_title") or "").split())
    title = re.sub(r"[@#]", "", title)[:90]
    if not re.match(r"^(feat|fix|refactor|docs|chore|style|perf)(\([^)]*\))?: ", title):
        title = f"fix: {title}" if title else f"fix: address the review of {review.decl.rsplit('.', 1)[-1]}"
    return title


def commit_message(title: str, review: Review, review_repo: str, model: str) -> str:
    return (f"{title}\n\nAddresses the review https://github.com/{review_repo}/issues/{review.issue} of "
            f"{review.decl}.\n\nProposed by the Tau Ceti review fixer ({model}).\n\n"
            f"Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n")


def addressed(pr: str, result: dict, by: dict) -> str:
    """The comment that names the pull request on the review's issue: the command first, then the reply."""
    head = (result.get("pr_title") or "").strip().splitlines()[0][:120] if result.get("pr_title") else ""
    reply = clean(result.get("reply", ""), limit=REPLY_LIMIT)
    return f"{mark(by)}\n/addressed {pr}" + (f" — {head}" if head else "") + (f"\n\n{reply}" if reply else "")


@dataclass
class Publisher:
    work: Path
    library_repo: str
    review_repo: str
    site: str
    roadmaps: Callable[[], set[str]]
    gh: Callable[[list[str], str | None], str]
    comment: Callable[[int, str], str]
    dry: bool = False

    def open(self, review: Review, result: dict, model: str, gate_: Gate) -> tuple[int | None, str]:
        """Commits the checkout's changes on a branch, pushes it and opens the pull request: its number and the
        branch (-1 in a dry run, which keeps the branch here and pushes nothing), or None and why not."""
        title = title_of(result, review)
        roadmap = result.get("roadmap") or "none"
        roadmap = roadmap if roadmap in self.roadmaps() else "none"
        branch = f"fixer/{review.id}-{stamp()}"
        git(self.work, "checkout", "-q", "-b", branch)
        git(self.work, "add", "-A", "--", "TauCeti")
        subprocess.run(["git", "-C", str(self.work), "commit", "-q", "-F", "-"], check=True, timeout=600,
                       input=commit_message(title, review, self.review_repo, model), capture_output=True, text=True)
        text = body(review, result, model, gate_, self.site, self.review_repo, roadmap)
        if self.dry:
            return -1, branch
        git(self.work, "push", "-q", "origin", f"HEAD:refs/heads/{branch}")
        out = self.gh(["gh", "pr", "create", "--repo", self.library_repo, "--head", branch, "--base", "main",
                       "--title", title, "--body-file", "-"], text)
        m = re.search(r"/pull/(\d+)", out)
        return (int(m.group(1)), branch) if m else (None, f"no pull request was opened: {out.strip()[:300]}")

    def link(self, review: Review, pr: str, result: dict, by: dict) -> str | None:
        """Names the pull request on the review's issue."""
        text = addressed(pr, result, by)
        if self.dry:
            return text
        self.comment(review.issue, text)
        return text

    def reply(self, review: Review, text: str, by: dict) -> str | None:
        body_ = f"{mark(by)}\n{clean(text, limit=REPLY_LIMIT)}"
        if self.dry:
            return body_
        self.comment(review.issue, body_)
        return body_
