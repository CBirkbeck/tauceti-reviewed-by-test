#!/usr/bin/env python3
"""A small site built from the suite's fixture (tests/fixtures, from LeanTrustBuilders/specs and
LeanTrustBuilders/extractor, Apache-2.0): the declarations of its version B and their sources, the
records of the suite's conformance vectors (made against version A), Voyager's announcements of two of
its declarations, two AI models' reviews, a no still open, a suggestion of what could be better, a listed
test, a proposed test, a review of an upstream declaration in a store this one imports, the roadmaps
of some declarations (the facet `roadmap`), and the standard reviews of four declarations (a text written, edited and
approved; one written for version A; one held for the owner; one outside the library). The unit tests and the
browser check read it.

  python3 tests/fixture_site.py OUT
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import build_site  # noqa: E402
import roadmaps  # noqa: E402
import standard  # noqa: E402
import voyager  # noqa: E402

from evidence_core import records as rec  # noqa: E402
from evidence_core import rubric as rb  # noqa: E402
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
#: A second AI model, which answers for another declaration.
ASTRA = {"kind": "agent", "identity": {"kind": "github", "id": "example"}, "agent": {"tool": "Codex", "model": "GPT-6 Astra"}}
#: The roadmaps of some declarations, as scripts/roadmaps.py credits them: the others have none.
ROADMAPS = {"Fixture.triple": "Arithmetic", "Fixture.triple_pos": "Arithmetic", "Fixture.triple_comm": "Arithmetic",
            "Fixture.double": "Doubling", "Fixture.double_triple": "Doubling"}


#: Why the no on `Fixture.one` was closed: two paragraphs, as an answer to a no can run.
INTENDED = ("`Pos` admits `0` on purpose: it is the predicate, and the theorems about it assume `0 < n` where they need it.\n\n"
            "With that usual hypothesis it is the positive integers, so the declaration says what it should.")

#: Two more AI agents: Voyager, which approves a standard review it has read, and the migration of the earlier
#: reviews, whose reviews are held for the owner.
VOYAGER = {"kind": "agent", "identity": {"kind": "github", "id": "example"},
           "agent": {"tool": "Voyager", "model": "claude-fable-5-1"}}
MIGRATION = {"kind": "agent", "identity": {"kind": "github", "id": "example"},
             "agent": {"tool": "Tau Ceti review migration", "model": "claude-opus-5-5"}}

#: The standard reviews of the fixture, as the intake records a text: three parts and no newline at either end. ASTRA
#: wrote the first of `triple`, and AGENT edited it: a reference more, and in its third part a quoted tag that the page
#: must show as text and never run (Review Focus 3).
TRIPLE_V1 = """## What it says
`triple n` is `n + n + n`, three times `n`.

## References and tests
- Fixture documentation, §1.
- `Fixture.triple_two` — its value at 2

## Lean subtleties
None."""
TRIPLE_V2 = """## What it says
`triple n` is `n + n + n`, three times the natural number `n`: $3n$ in the usual notation.

## References and tests
- Fixture documentation, §1.
- Fixture documentation, §1.2, the definition of tripling.
- `Fixture.triple_two` — its value at 2

## Lean subtleties
`triple n = 3 * n` is a theorem, not a definitional equality. A review may quote markup,
such as <img src=x onerror="window.pwned=1">, which is only text."""
#: Written for version A of `double`, which has changed since.
DOUBLE_V1 = """## What it says
`double n` is twice `n`.

## References and tests
- Fixture documentation, §2.

## Lean subtleties
None."""
#: The migration's review of `triple_pos`, held for the owner.
TRIPLE_POS_V1 = """## What it says
`triple n` is positive when `n` is: $0 < n$ gives $0 < 3n$.

## References and tests
- Fixture, Theorem 1.

## Lean subtleties
None."""
#: A declaration outside the library, which the site asks about too (`review_outside`).
INT_V1 = """## What it says
`Int` is the type of integers: a natural number `n` is `Int.ofNat n`, and `-(n + 1)` is `Int.negSucc n`.

## References and tests
- Lean core library, `Int` in `Init.Data.Int.Basic`.

## Lean subtleties
None."""
#: The cells of an AI agent's write, edit or approval: every axis of the rubric looked at.
CELLS = {axis: "checked" for axis in rb.STANDARD.names}


def vector(name: str, verdict: str = "accept") -> dict:
    """The suite's vector review of ``name`` with that verdict (records.jsonl, made against version A)."""
    return next(r for r in rec.load(FIXTURES / "records.jsonl")
                if r["kind"] == "review" and r.get("verdict") == verdict and r["subject"]["name"] == name)


def bulk(comment: int, line: int = 2) -> dict:
    """Where a record of a line of a comment on the bulk issue came from, as the intake sets it; a record's link leaves
    the line off."""
    return {"kind": "comment", "ref": f"https://github.com/{SETTINGS['repo']}/issues/{SETTINGS['bulk_issue']}"
                                      f"#issuecomment-{comment}/line/{line}"}


def accepting(subject: dict, by: dict, at: str, text: str, origin: dict, std: dict, checked: dict = CELLS,
              supersedes: str | None = None) -> dict:
    """An AI agent's accept that carries the standard review (a write, an edit or an approval), as the intake records
    one: the rubric's cells, the `standard` field, and the yes of its own that it supersedes, if it has one."""
    return {"schema": rec.SCHEMA, "kind": "review", "verdict": "accept", "subject": subject, "by": by, "at": at,
            "origin": origin, "text": text, "rubric": rb.STANDARD.name, "checked": dict(checked),
            "standard": {"spec": standard.SPEC, **std}, **({"links": {"supersedes": supersedes}} if supersedes else {})}


def extra_records(ds: Dataset) -> list[dict]:
    """What the vectors lack: an AI agent's review (and the same review under its model's family name,
    withdrawn), another model's review of another declaration, a no still open (as the form records one), a
    suggestion (the question form's record), a listed test, a proposed test, why the vectors' no on
    `Fixture.one` (closed as invalid, without a word) behaves as intended, and the standard reviews of four
    declarations: one written, edited and approved by three AI agents, one written for version A, one held for the
    owner, and one outside the library."""
    key = lambda name: rec.subject_from_decl(ds.by_name[name], ds)
    issue = lambda n: {"kind": "issue", "ref": f"example/fixture-store#{n}"}
    one = vector("Fixture.one", "problem")["id"]
    # The AI agent's yes on `Fixture.triple`, first filed under its model's family name and withdrawn when
    # filed again under the exact one: the page shows it once.
    relabelled = rec.with_id({"schema": rec.SCHEMA, "kind": "review", "subject": key("Fixture.triple"), "verdict": "accept",
                              "by": {**AGENT, "agent": {"tool": "Claude Code", "model": "Opus 5"}},
                              "text": "Compared with its definition, `n + n + n`.", "at": "2026-10-21T10:00:00Z",
                              "origin": issue(10)})
    agent_yes = {"schema": rec.SCHEMA, "kind": "review", "subject": key("Fixture.triple"), "verdict": "accept",
                 "by": AGENT, "text": "Compared with its definition, `n + n + n`.", "at": "2026-10-22T10:00:00Z",
                 "origin": issue(11)}
    astra_yes = {"schema": rec.SCHEMA, "kind": "review", "subject": key("Fixture.triple_pos"), "verdict": "accept",
                 "by": ASTRA, "text": "`triple n` is `3 * n`, positive when `n` is.", "at": "2026-10-21T08:00:00Z",
                 "origin": issue(17)}
    approved = standard.version_of(TRIPLE_V2)
    return [
        relabelled,
        {"schema": rec.SCHEMA, "kind": "status", "target": relabelled["id"], "state": "withdrawn", "by": AGENT,
         "text": "Filed again under the exact model.", "at": "2026-10-22T09:59:00Z", "origin": issue(10)},
        {"schema": rec.SCHEMA, "kind": "status", "target": one, "state": "intended", "by": AGENT, "text": INTENDED,
         "at": "2026-10-24T12:00:00Z", "origin": issue(16)},
        agent_yes,
        astra_yes,
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
        # The standard review of `Fixture.triple`: ASTRA wrote it, AGENT edited it (which supersedes AGENT's yes
        # above), and Voyager approved the edit, finding `choice` not applicable.
        accepting(key("Fixture.triple"), ASTRA, "2026-10-25T10:00:00Z", TRIPLE_V1, bulk(4101), {}),
        accepting(key("Fixture.triple"), AGENT, "2026-10-26T10:00:00Z", TRIPLE_V2, bulk(4102),
                  {"parent": standard.version_of(TRIPLE_V1), "note": "Adds a reference, and what to know of the proof.",
                   "dropped": []}, supersedes=rec.with_id(agent_yes)["id"]),
        accepting(key("Fixture.triple"), VOYAGER, "2026-10-27T10:00:00Z", f"Approves the standard review `{approved}`.",
                  bulk(4103), {"approves": approved}, checked={**CELLS, "choice": "na"}),
        # Written for version A of `double`, whose subject the vectors' yes holds: stale since.
        accepting(vector("Fixture.double")["subject"], AGENT, "2026-10-24T09:00:00Z", DOUBLE_V1, bulk(4104), {}),
        # The migration's review of `triple_pos` is held for the owner: a comment, replying to ASTRA's yes.
        {"schema": rec.SCHEMA, "kind": "comment", "subject": key("Fixture.triple_pos"), "by": MIGRATION,
         "text": TRIPLE_POS_V1, "standard": {"spec": standard.SPEC},
         "links": {"replies_to": rec.with_id(astra_yes)["id"]}, "at": "2026-10-27T12:00:00Z", "origin": bulk(4105)},
        # One outside the library.
        accepting(key("Int"), AGENT, "2026-10-24T10:00:00Z", INT_V1, bulk(4106), {}),
    ]


def imported_store(ds: Dataset, cache: Path) -> None:
    """A store this one imports, as `evidence-store fetch-imports` leaves it, with a review of `Int`."""
    store = Store.init(cache / "example" / "imports" / "evidence", default_config("example/imports", "Int", "Test imports"))
    store.add([{"schema": rec.SCHEMA, "kind": "review", "subject": rec.subject_from_decl(ds.by_name["Int"], ds),
                "verdict": "accept", "by": PERSON, "text": "The integers, as in any textbook.",
                "at": "2026-10-01T00:00:00Z", "origin": {"kind": "issue", "ref": "example/imports#1"}}])
    (cache / "imports.json").write_text(json.dumps([{"repo": "example/imports", "path": "evidence", "commit": "c0ffee"}]))


def with_roadmaps(dataset: Path, out: Path) -> Path:
    """A copy of ``dataset`` with the facet `roadmap` as scripts/roadmaps.py writes it, of ROADMAPS."""
    shutil.copytree(dataset, out)
    roadmaps.write(out, [{"decl": d, "roadmap": r, "lines": [2, 2]} for d, r in sorted(ROADMAPS.items())])
    return out


def inputs(tmp: Path, dataset: Path = DATASET, more: list[dict] = (),
           announcements: list[dict] = ANNOUNCEMENTS) -> tuple[Path, Path, Path]:
    """What a build of the fixture's site reads, laid out in ``tmp``: the dataset (a copy, with the facet `roadmap`),
    the store and the stores it imports. ``more`` are records for the store besides the fixture's own, and
    ``announcements`` Voyager's, recorded after them."""
    dataset = with_roadmaps(dataset, tmp / "dataset")
    ds = Dataset.load(dataset)
    store = Store.init(tmp / "evidence", {**default_config("example/fixture-store", "Fixture", "Fixture"),
                                           "imports": [{"repo": "example/imports"}]})
    store.add(rec.load(FIXTURES / "records.jsonl"))
    store.add(extra_records(ds))
    store.add(list(more))
    store.add(voyager.named_records(list(announcements), ds, store, SETTINGS["voyager"]))
    imported_store(ds, tmp / "imports")
    return dataset, tmp / "evidence", tmp / "imports"


def build(out: Path, budget_mb: int = 950, cap: int = 60, settings: dict | None = None,
          dataset: Path = DATASET, more: list[dict] = ()) -> dict:
    """The fixture's site in ``out``; ``more`` are records for its store besides the fixture's own."""
    dataset, store, imports = inputs(Path(tempfile.mkdtemp(prefix="fixture-site-")), dataset, more)
    return build_site.build(dataset, store, Path(out), settings or SETTINGS, source=SOURCE, imports=imports,
                            budget_mb=budget_mb, cap=cap)


if __name__ == "__main__":
    print(json.dumps(build(Path(sys.argv[1]))))
