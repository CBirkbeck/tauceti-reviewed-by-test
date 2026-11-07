"""Which reviews the fixer takes: the noes (verdict `problem`) and suggestions (verdict `question`) that a person
wrote, on an issue of the review repository, still in force (neither withdrawn nor superseded), not yet linked to a
pull request (`/addressed`, or a status naming one), filed since the fixer started and not taken before. The
oldest first. Whether the answerer has answered one does not matter: an answer is not a fix."""
from __future__ import annotations

from dataclasses import dataclass, field

from answerer.items import issue_of


@dataclass
class Review:
    id: str
    kind: str  # "problem" (a no) or "question" (a suggestion)
    record: dict
    issue: int | None
    thread: list[dict] = field(default_factory=list)  # the replies to it and the statuses set on it, in order

    @property
    def decl(self) -> str:
        return (self.record.get("subject") or {}).get("name", "")

    @property
    def module(self) -> str:
        return (self.record.get("subject") or {}).get("module", "") or ""

    @property
    def at(self) -> str:
        return self.record.get("at", "")

    @property
    def author(self) -> str:
        return ((self.record.get("by") or {}).get("identity") or {}).get("id", "")

    def outside(self, root: str) -> bool:
        """Whether it is about a declaration of a dependency (Mathlib's, Lean's), not of the library."""
        return self.module.split(".")[0] != root

    def linked(self) -> str | None:
        """The pull request already linked to it or settling it, as `owner/repo#N`."""
        return next((t["pr"] for t in reversed(self.thread) if t.get("pr")), None)


def reviews(records: list[dict], repo: str) -> list[Review]:
    """People's noes and suggestions from issues of `repo`, in force, with their threads, the oldest first."""
    statuses: dict[str, list[dict]] = {}
    replies: dict[str, list[dict]] = {}
    superseded = set()
    for r in records:
        links = r.get("links") or {}
        if r.get("kind") == "status":
            statuses.setdefault(r.get("target", ""), []).append(r)
        elif r.get("kind") == "comment" and links.get("replies_to"):
            replies.setdefault(links["replies_to"], []).append(r)
        if links.get("supersedes"):
            superseded.add(links["supersedes"])
    at = lambda r: (r.get("at", ""), r.get("id", ""))  # noqa: E731
    out = []
    for r in records:
        if r.get("kind") != "review" or r.get("verdict") not in ("problem", "question"):
            continue
        if (r.get("by") or {}).get("kind") != "person" or r["id"] in superseded:
            continue
        said = sorted(statuses.get(r["id"], []), key=at)
        if said and said[-1].get("state") == "withdrawn":
            continue
        issue = issue_of(r, repo)
        if issue is None:
            continue
        out.append(Review(r["id"], r["verdict"], r, issue, sorted(replies.get(r["id"], []) + said, key=at)))
    return sorted(out, key=lambda v: (v.at, v.id))


def choose(found: list[Review], taken: dict, since: str, max_items: int, only: list[str] | None = None) -> list[Review]:
    """The reviews to take this run: those `only` names (any of the people's, for a test), else the new ones."""
    if only:
        return [v for v in found if v.id in set(only)]
    new = [v for v in found if v.at >= since and v.id not in taken and not v.linked()]
    return new[:max_items]
