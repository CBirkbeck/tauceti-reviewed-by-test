#!/usr/bin/env python3
"""A small site built from the suite's fixture (tests/fixtures, from LeanTrustBuilders/specs and
LeanTrustBuilders/extractor, Apache-2.0): the declarations of its version B and their sources, the
records of the suite's conformance vectors (made against version A), Voyager's announcements of two of
its declarations, an AI agent's review, a no still open, a suggestion of what could be better, a listed
test, a proposed test, and a review of an upstream declaration in a store this one imports. The unit tests and the browser check read it.

  python3 tests/fixture_site.py OUT
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import build_site  # noqa: E402
import voyager  # noqa: E402

from evidence_core import records as rec  # noqa: E402
from evidence_core.dataset import Dataset  # noqa: E402
from evidence_core.store import Store, default_config  # noqa: E402

FIXTURES = HERE / "fixtures"
DATASET = FIXTURES / "dataset-b"
SOURCE = FIXTURES / "source-b"
SETTINGS = {
    "repo": "example/fixture-store", "bulk_issue": 1, "tauceti": "B", "review_outside": ["Init.Data"],
    "library": {"name": "Fixture", "repo": "test/fixture", "root": "Fixture", "docs": "https://example.org/docs"},
    "voyager": {"site": "https://zulip.example.org", "channel": "Tau Ceti", "topic": "new results",
                "sender": "voyager@example.org"},
    "site": {"title": "Tau Ceti Review", "url": "https://example.org/"},
    "signin": {"client_id": "Iv23fixture", "exchange": "https://signin.example.org/token"},
}
ANNOUNCEMENTS = [
    {"decl": "Fixture.triple_pos", "name": "The positivity of triple", "what": "result",
     "about": "`triple n` is positive when $n > 0$.", "prs": [5],
     "source": {"voyager": 101, "stream": 610393}, "at": "2026-10-20T03:30:00Z"},
    {"decl": "Fixture.IsDouble", "name": "Being double", "what": "definition",
     "about": "`m` is twice `n`.", "prs": [7, 8],
     "source": {"voyager": 102, "stream": 610393}, "at": "2026-10-21T03:30:00Z"},
]
PERSON = {"kind": "person", "identity": {"kind": "github", "id": "example"}}
AGENT = {"kind": "agent", "identity": {"kind": "github", "id": "example"},
         "agent": {"tool": "Claude Code", "model": "claude-opus-5-5"}}
SOMEONE = {"kind": "person", "identity": {"kind": "github", "id": "someone"}}


#: Why the no on `Fixture.one` was closed: two paragraphs, as an answer to a no can run.
INTENDED = ("`Pos` admits `0` on purpose: it is the predicate, and the theorems about it assume `0 < n` where they need it.\n\n"
            "With that usual hypothesis it is the positive integers, so the declaration says what it should.")


def extra_records(ds: Dataset) -> list[dict]:
    """What the vectors lack: an AI agent's review (and the same review under its model's family name,
    withdrawn), a no still open (as the form records one), a suggestion (the question form's record), a
    listed test, a proposed test, and why the vectors' no on `Fixture.one` (closed as invalid, without a
    word) behaves as intended."""
    key = lambda name: rec.subject_from_decl(ds.by_name[name], ds)
    issue = lambda n: {"kind": "issue", "ref": f"example/fixture-store#{n}"}
    one = next(r["id"] for r in rec.load(FIXTURES / "records.jsonl")
               if r.get("verdict") == "problem" and r["subject"]["name"] == "Fixture.one")
    # The AI agent's yes on `Fixture.triple`, first filed under its model's family name and withdrawn when
    # filed again under the exact one: the page shows it once.
    relabelled = rec.with_id({"schema": rec.SCHEMA, "kind": "review", "subject": key("Fixture.triple"), "verdict": "accept",
                              "by": {**AGENT, "agent": {"tool": "Claude Code", "model": "Opus 5"}},
                              "text": "Compared with its definition, `n + n + n`.", "at": "2026-10-21T10:00:00Z",
                              "origin": issue(10)})
    return [
        relabelled,
        {"schema": rec.SCHEMA, "kind": "status", "target": relabelled["id"], "state": "withdrawn", "by": AGENT,
         "text": "Filed again under the exact model.", "at": "2026-10-22T09:59:00Z", "origin": issue(10)},
        {"schema": rec.SCHEMA, "kind": "status", "target": one, "state": "intended", "by": AGENT, "text": INTENDED,
         "at": "2026-10-24T12:00:00Z", "origin": issue(16)},
        {"schema": rec.SCHEMA, "kind": "review", "subject": key("Fixture.triple"), "verdict": "accept", "by": AGENT,
         "text": "Compared with its definition, `n + n + n`.", "at": "2026-10-22T10:00:00Z", "origin": issue(11)},
        {"schema": rec.SCHEMA, "kind": "review", "subject": key("Fixture.triple_comm"), "verdict": "problem",
         "category": "other", "rubric": "ltb-rubric/1", "by": SOMEONE, "at": "2026-10-23T09:00:00Z", "origin": issue(14),
         "text": "Its name says commutativity, but it states `triple b = b + b + b`: the definition, unfolded."},
        {"schema": rec.SCHEMA, "kind": "review", "subject": key("Fixture.triple"), "verdict": "question", "by": SOMEONE,
         "text": "It could be stated for any semiring: `n + n + n` makes sense there.", "at": "2026-10-23T10:00:00Z",
         "origin": issue(15)},
        {"schema": rec.SCHEMA, "kind": "test", "subject": key("Fixture.triple"), "test": key("Fixture.triple_two"),
         "text": "its value at 2", "by": PERSON, "at": "2026-10-22T11:00:00Z", "origin": issue(12)},
        {"schema": rec.SCHEMA, "kind": "challenge", "subject": key("Fixture.double"),
         "text": "`double n = n + n` for every `n`", "statement": "theorem double_eq (n : Nat) : double n = n + n",
         "by": PERSON, "at": "2026-10-22T12:00:00Z", "origin": issue(13)},
    ]


def imported_store(ds: Dataset, cache: Path) -> None:
    """A store this one imports, as `evidence-store fetch-imports` leaves it, with a review of `Int`."""
    store = Store.init(cache / "example" / "imports" / "evidence", default_config("example/imports", "Int", "Test imports"))
    store.add([{"schema": rec.SCHEMA, "kind": "review", "subject": rec.subject_from_decl(ds.by_name["Int"], ds),
                "verdict": "accept", "by": PERSON, "text": "The integers, as in any textbook.",
                "at": "2026-10-01T00:00:00Z", "origin": {"kind": "issue", "ref": "example/imports#1"}}])
    (cache / "imports.json").write_text(json.dumps([{"repo": "example/imports", "path": "evidence", "commit": "c0ffee"}]))


def build(out: Path, budget_mb: int = 800, cap: int = 60, settings: dict | None = None,
          dataset: Path = DATASET) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="fixture-site-"))
    ds = Dataset.load(dataset)
    store = Store.init(tmp / "evidence", {**default_config("example/fixture-store", "Fixture", "Fixture"),
                                           "imports": [{"repo": "example/imports"}]})
    store.add(rec.load(FIXTURES / "records.jsonl"))
    store.add(extra_records(ds))
    store.add(voyager.named_records(ANNOUNCEMENTS, ds, store, SETTINGS["voyager"]))
    imported_store(ds, tmp / "imports")
    return build_site.build(dataset, tmp / "evidence", Path(out), settings or SETTINGS, source=SOURCE,
                            imports=tmp / "imports", budget_mb=budget_mb, cap=cap)


if __name__ == "__main__":
    print(json.dumps(build(Path(sys.argv[1]))))
