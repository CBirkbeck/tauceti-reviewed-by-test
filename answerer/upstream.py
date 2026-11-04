"""Docstring fixes of declarations from the library's dependencies (Mathlib's, say), proposed upstream by a person.

The answerer opens pull requests only to the library. A no that is right about the docstring of a dependency's
declaration is listed for a person, who proposes the fix upstream and links that pull request in a comment on the
no's own issue. The answerer then posts its reply with the link, follows the pull request, and once it has merged
and the dependency's revision that the library pins, at the commit the site shows, includes it, closes the no as
fixed at that commit.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable, Iterable

from .post import gh as run_gh
from .pulls import pr_state

#: A pull request, as a link or in GitHub's shorthand, `owner/repo#123`.
PULL = re.compile(r"(?:https://github\.com/)?([\w.-]+/[\w.-]+?)(?:/pull/|#)(\d+)\b")


def dependencies(manifest: Path) -> dict[str, dict]:
    """The library's dependencies on GitHub, from its `lake-manifest.json`: {owner/repo, lower case: {name, rev}}."""
    out = {}
    for pkg in json.loads(Path(manifest).read_text(encoding="utf-8")).get("packages", []):
        m = re.fullmatch(r"https://github\.com/([\w.-]+/[\w.-]+?)(?:\.git)?/?", pkg.get("url") or "")
        if m and pkg.get("rev"):
            out[m.group(1).lower()] = {"name": pkg.get("name") or m.group(1), "rev": pkg["rev"]}
    return out


class Upstream:
    def __init__(self, repo: str, deps: dict[str, dict], gh: Callable[..., str] = run_gh):
        self.repo, self.deps, self.gh = repo, deps, gh  # repo: the review repository, where the noes' issues are

    def name(self, repo: str) -> str:
        """The dependency's name as its manifest gives it, capitalised: Mathlib."""
        n = (self.deps.get(repo.lower()) or {}).get("name") or repo.split("/")[-1]
        return n[:1].upper() + n[1:]

    def linked(self, issue: int, maintainers: Iterable[str], tool: str,
               skip: Iterable[tuple[str, int]] = ()) -> tuple[str, int] | None:
        """The last pull request to one of the dependencies that a maintainer linked in a comment on the issue,
        leaving out the answerer's own comments (they link what was already linked) and the pull requests in `skip`."""
        out = self.gh(["gh", "api", "--paginate", f"repos/{self.repo}/issues/{issue}/comments",
                       "--jq", ".[] | {login: .user.login, body: .body} | @json"])
        maintainers, skip, found = set(maintainers), set(skip), None
        for line in out.splitlines():
            c = json.loads(line)
            if c.get("login") not in maintainers or f"tool={tool};" in (c.get("body") or ""):
                continue
            for repo, n in PULL.findall(c.get("body") or ""):
                if repo.lower() in self.deps and (repo.lower(), int(n)) not in skip:
                    found = (repo.lower(), int(n))
        return found

    def state(self, repo: str, number: int) -> tuple[str, str | None]:
        """As `pulls.pr_state`, on the repository's default branch."""
        branch = self.gh(["gh", "api", f"repos/{repo}", "--jq", ".default_branch"]).strip() or "main"
        return pr_state(self.gh, repo, number, branch)

    def includes(self, repo: str, sha: str) -> bool:
        """Whether the dependency's revision that the library pins contains commit `sha`."""
        rev = self.deps[repo.lower()]["rev"]
        status = self.gh(["gh", "api", f"repos/{repo}/compare/{sha}...{rev}?per_page=1", "--jq", ".status"]).strip()
        return status in ("ahead", "identical")
