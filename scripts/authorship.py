"""Whether an account is an author of one of the library's declarations, so that no one approves, writes or edits the
standard review of their own work (AI-REVIEWS.md, "Rules"): the intake refuses those lines (scripts/standard_intake.py),
and the site counts no yes of an author's (scripts/site_data.py).

The authors are the dataset's facet `authors` (scripts/authors.py): the GitHub logins of everyone who wrote or changed a
line of the declaration, co-authors among them. Git knows accounts, not people, so one person's several accounts are
the owner's to say, in data/settings.json: `authors.same_person`, a list of lists of logins, each the accounts of one
person. Logins are compared in any case, as GitHub compares them.

A dataset without the facet (one extracted before it) says nothing of authors, and a declaration outside the library
(Mathlib's) has none recorded: for both `authors_of` is None, and whoever relies on it says that authorship was not
checked, rather than take it for none.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Iterable, Sequence

from evidence_core.dataset import Dataset, Decl

from common import load_settings

FACET = "authors"


def known(ds: Dataset) -> bool:
    """Whether the dataset says who wrote its declarations."""
    return FACET in ds.facet_names()


def authors_of(ds: Dataset, decl: Decl) -> list[str] | None:
    """The logins of the declaration's authors, or None when the dataset cannot say: it has no facet `authors`, or the
    declaration is not the library's."""
    if not known(ds) or not decl.is_project:
        return None
    return list((ds.facet_row(FACET, decl.name) or {}).get("authors") or [])


@lru_cache(maxsize=1)
def groups() -> tuple[tuple[str, ...], ...]:
    """The accounts of one person each, from the settings (`authors.same_person`)."""
    return tuple(tuple(g) for g in load_settings().get("authors", {}).get("same_person", []))


def accounts(login: str, same: Iterable[Sequence[str]] | None = None) -> set[str]:
    """The accounts of the person behind ``login``, in lowercase: the login, and the others of its group in ``same``
    (default: the settings')."""
    mine = {login.lower()} if login else set()
    for group in groups() if same is None else same:
        lowered = {x.lower() for x in group}
        if mine & lowered:
            mine |= lowered
    return mine


def which(login: str, authors: Iterable[str], same: Iterable[Sequence[str]] | None = None) -> list[str]:
    """The authors that are ``login``'s person: none when it is no author's."""
    mine = accounts(login, same)
    return [a for a in authors if a.lower() in mine]


def login_of(by: dict) -> str:
    """The GitHub account a record's `by` names."""
    return ((by or {}).get("identity") or {}).get("id") or ""
