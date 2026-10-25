"""What the answerer answers, and what it knows of each before the model reads anything.

An item is a no (a review with verdict `problem`) or a suggestion or question (verdict `question`)
that is in force (neither withdrawn nor superseded) and open (no status yet, or reopened), as
evidence-core resolves the store against the dataset of the commit the site shows: the same
reading the site makes. People's items come first, then AI agents', the oldest first.
"""
from __future__ import annotations

from dataclasses import dataclass

from evidence_core import views
from evidence_core.coverage import Evidence
from evidence_core.dataset import Dataset
from evidence_core.source import Sources

from .library import Library


@dataclass
class Item:
    id: str
    kind: str  # "problem" (a no) or "question" (a suggestion or question)
    decl: str  # the declaration's name now
    view: dict  # evidence-core's view of the record: its state, statuses, replies, issue address, …
    record: dict
    issue: int | None  # its own issue on the review repository, when it came from one

    @property
    def author(self) -> str:
        return ((self.record.get("by") or {}).get("identity") or {}).get("id", "")

    @property
    def by_agent(self) -> bool:
        return (self.record.get("by") or {}).get("kind") == "agent"

    @property
    def at(self) -> str:
        return self.record.get("at", "")


def issue_of(r: dict, repo: str) -> int | None:
    """The number of the record's own issue, when it came from an issue of `repo`."""
    origin = r.get("origin") or {}
    ref = origin.get("ref", "")
    if origin.get("kind") == "issue" and ref.startswith(repo + "#") and ref.split("#", 1)[1].isdigit():
        return int(ref.split("#", 1)[1])
    return None


def open_items(ev: Evidence, repo: str) -> list[Item]:
    seen, items = set(), []
    for name, rows in ev.by_decl.items():
        for r, s in rows:
            if r.get("kind") != "review" or r.get("verdict") not in ("problem", "question") or r["id"] in seen:
                continue
            seen.add(r["id"])
            v = views.record_view(ev, r, s, name)
            if v["inForce"] and v["state"] == "open":
                items.append(Item(r["id"], r["verdict"], name, v, r, issue_of(r, repo)))
    return sorted(items, key=lambda i: (i.by_agent, i.at, i.id))


class GitSources(Sources):
    """evidence-core's source reader, reading through the library at its commit."""

    def __init__(self, lib: Library):
        super().__init__(None)
        self.lib = lib

    def lines(self, path: str) -> list[str] | None:
        if path not in self._files:
            text = self.lib.text(path)
            self._files[path] = text.split("\n") if text is not None else None
        return self._files[path]


def declaration(ds: Dataset, lib: Library, name: str) -> dict:
    """What the dataset says of a declaration, and its source with its docstring when it is the
    library's own: name, kind, module, path, lines, signature, source."""
    d, src, sig = ds.by_name.get(name), ds.facet_row("source", name), ds.facet_row("signature", name)
    span = GitSources(lib).span(src, doc_comment=True) if src else None
    return {"name": name, "kind": d.kind if d else None, "module": d.module if d else None,
            "path": src.get("path") if src else None, "lines": [span[0], span[1]] if span else None,
            "signature": (sig or {}).get("text"), "source": span[2] if span else None}
