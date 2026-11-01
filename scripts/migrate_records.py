#!/usr/bin/env python3
"""Makes the records of the migration to standard reviews, as files for the evidence store.

  python3 scripts/migrate_records.py voyager-refused TSV --dataset DIR [--store DIR] --comment-url URL
                                     --at TIME --session S --out FILE
  python3 scripts/migrate_records.py standard BUNDLES RESULTS CHECKS --dataset DIR --source TAUCETI [--store DIR]
                                     [--out-dir DIR] --prefix PREFIX [--model MODEL] [--held FILE] [--at TIME]

`voyager-refused`: Voyager's yeses that the intake refused for want of their reasons, filed with the reasons
transcribed from Voyager's run notes. On 2026-10-30 Voyager posted bare `Reviewed-by: <decl>` lines on the bulk
issue, and the intake refused each one: a review by an agent needs its text. Each row of TSV is a line of that
comment, `<line k>\t<decl>\t<reasons>`, k counted as the intake counts the lines of a comment, from 1. Each becomes
the record the intake would have made of the line had it carried the reasons: an accept of the declaration, keyed in
the dataset Voyager checked (DIR), by Voyager through CBirkbeck's account, made at the comment's time (TIME) and
coming from its line k (`<URL>/line/<k>`), so that the intake finds the line recorded. Its text is the reasons and
a note saying where they came from. It carries no `standard`: it is an AI yes of the earlier form, which counts as an
approval of an earlier version of the declaration's standard review. As the intake's accepts do, it supersedes
Voyager's latest earlier yes of the declaration, among the store's records.

A row is refused, and nothing is written, when its line is not a positive number or is given twice, when it has no
reasons, when the dataset lacks its declaration, when the store has the line recorded already, or when Voyager said
yes to the declaration again at or after TIME: that yes counts already, and this one would count beside it.

`standard`: the standard reviews the migration's writers made, as records. BUNDLES are scripts/migrate_inputs.py's;
RESULTS the writers' (scripts/migrate_write.py collect, or merge for several rounds), `{"decl", "cells", "verdict",
"hold", "review"}` or `{"decl", "error"}`; CHECKS scripts/migrate_check.py's of RESULTS, a `{"decl", "ok", "problems"}`
to each result. The run checks each result again, as migrate_check.py does, against TAUCETI, a checkout of the library
at the bundles' commit, and each check of CHECKS must agree with it, so that checks from an older checker, or of other
results, never let a result through. The records are keyed in the dataset DIR, which is the bundles' (the same commit),
and made by the migration (Tau Ceti review migration, as MODEL, the model that wrote the results, claude-opus-5-5 unless
given, through CBirkbeck's account, in the run PREFIX) at TIME, which is the time of the run unless given: make them
just before they are pushed, so that the records that come between are few. They go to `<PREFIX>-<nn>.jsonl` in OUT-DIR
(evidence/records), at most 2,000 to a file, numbered on from the files of that prefix there already, none changed; each
comes from its own line of its file, which its origin links in evidence/records on main. The store is read as it stands,
for a declaration's latest accept, an open no and a standard review there already: bring it up to date first. The
results are the run, and a run is a wave, since the writing is spread over several: a bundle with no result is not in
it, as a retry round's results hold only what it ran again, and nor is one whose result is `collect`'s `no result`, not
written yet, which gets no record and no line in HELD. A run takes one model's results, so that each record names the
model that wrote it. A result is:
- passed by its check, approved, and no no on the declaration is open (the bundle says so, or the store does now): an
  accept holding the review as a first version, with its cells as `checked`. Writing the review approves it, as an AI's
  write does. As evidence-store's accepts do, it supersedes the migration's own latest earlier accept of the
  declaration, among the records the page puts on it;
- passed by its check, and held, or approved for a declaration with an open no: a comment, a version nobody approves,
  with `standard.note` saying it was held for the owner. It replies to the declaration's latest accept, any
  reviewer's, never to a no or a question, which would then be taken for answered (Ruling R14). A declaration with no
  accept has no record, since there is none to reply to;
- an error, or failed by its check: no record.
HELD (docs/standard-reviews-held.md), the owner's list, is reconciled with the run, not only added to. A declaration
the run holds or records nothing for has one line: the reason (`no result: …` for another error of `collect`;
`failed checks: …`, what this run's check finds, with the writer's own reason added when it held the review; `no yes
to attach the review to`; or the writer's own) and its address on the site. It takes the place of any line of the
declaration there: a line there already as it is stays where it is, and new ones go under a heading for the run. A
declaration the run approves loses its line, and a heading left with no line goes; the rest is kept as it is. A
declaration that has a standard review already (a version not withdrawn) gets no record, since the migration's would
replace that review: the report names it, and HELD lists it if the run held it, and else keeps any line it had.

Nothing is written, and the exit is 1, when a result has no bundle or no check, a check no result, a check passes a
result that this run's check fails or fails one it passes, a declaration is given twice, a bundle is at another commit
than the dataset, the dataset lacks a declaration, or a result that its check passed is no review `standard.check`
passes or has cells that are not each axis of the rubric once, checked or n/a. The exit is 2 on a time that is not like
2026-11-02T09:30:00Z, a file that cannot be read, or a TAUCETI that is no directory or a checkout at another commit than
the dataset's.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT  # noqa: E402
import migrate_check  # noqa: E402
import migrate_inputs  # noqa: E402
import standard  # noqa: E402

from evidence_core import Dataset  # noqa: E402
from evidence_core import records as rec  # noqa: E402
from evidence_core.coverage import Evidence  # noqa: E402
from evidence_core.rubric import Rubric  # noqa: E402
from evidence_core.store import Store  # noqa: E402

STORE = ROOT / "evidence"
HELD = ROOT / "docs" / "standard-reviews-held.md"
#: What follows the reasons in a record's text.
TRANSCRIBED = " (Reasons transcribed from Voyager's run notes; the line it posted had none.)"
#: A record's time, as the intake keeps GitHub's: RFC 3339 in UTC, to the second.
TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
#: Where the files of records stand in the repository, as an origin links them (`<file>#L<n>`), and the site, where the
#: held list links each declaration.
RECORDS_URL = "https://github.com/CBirkbeck/tauceti-reviewed-by-test/blob/main/evidence/records/"
SITE_URL = "https://cbirkbeck.github.io/tauceti-reviewed-by-test/"
#: What JavaScript's `encodeURIComponent`, which the page addresses a declaration by, leaves as it is besides letters,
#: digits and `-_.`.
URI_SAFE = "!~*'()"
#: The most records a file holds.
PER_FILE = 2000
#: The model that wrote the migration's first reviews: the records' model, unless a run names the one that wrote its
#: results.
MODEL = "claude-opus-5-5"
#: The most problems a refused run prints: files that do not belong together make one for every result.
SHOWN = 50
#: The note of a review held for the owner (`standard.note`), and the reasons a declaration is listed that no result or
#: check gives.
HELD_NOTE = "Written in the migration; held for the owner."
NO_YES = "no yes to attach the review to"
OPEN_NO = "a no on it is open"
#: A line of the held list (`held_line`), with the declaration it is of.
HELD_LINE = re.compile(r"^- \[`(.+?)`\]\(<")
#: The held list's title, written when the file is made.
HELD_TITLE = (
    "# Standard reviews held for the owner\n\n"
    "Declarations the migration to standard reviews did not approve, a line each: why, and where the site shows the "
    "declaration. A review held for the owner is recorded as a comment on the declaration's latest yes, which nobody "
    "approved; one that failed its checks, or was not written, has no record. No no was filed.\n")


def voyager(session: str) -> dict:
    """Voyager, as its comments on the bulk issue name it, through CBirkbeck's account, in the run `session`."""
    return {"kind": "agent", "identity": {"kind": "github", "id": "CBirkbeck"}, "involvement": "unknown",
            "agent": {"tool": "Voyager", "model": "claude-fable-5-1", "session": session}}


def read_rows(path: Path) -> tuple[list[tuple[int, str, str]], list[str]]:
    """The rows of a TSV file, `<line k>\t<decl>\t<reasons>`, blank lines skipped, and what is wrong with the others."""
    rows, problems = [], []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) != 3 or not re.fullmatch(r"[1-9]\d*", fields[0].strip()):
            problems.append(f"{path}:{n}: a row is `<line k>\\t<decl>\\t<reasons>`, k from 1")
            continue
        rows.append((int(fields[0]), fields[1].strip(), fields[2].strip()))
    return rows, problems


def voyager_refused(rows: list[tuple[int, str, str]], ds: Dataset, store: Store, url: str, at: str,
                    session: str) -> tuple[list[dict], list[str]]:
    """The records of Voyager's refused lines, from (line, declaration, reasons) rows: each made at `at`, from line k
    of the comment at `url`, keyed in `ds`. Also what is wrong with the rows that make none."""
    by = voyager(session)
    rubric = store.rubric
    out, problems, seen = [], [], set()
    for k, name, reasons in rows:
        ref = f"{url}/line/{k}"
        decl = ds.by_name.get(name)
        if k in seen:
            problems.append(f"line {k} (`{name}`): the line is given twice")
            continue
        seen.add(k)
        if store.from_origin(ref):
            problems.append(f"line {k} (`{name}`): the store has the line recorded already")
            continue
        if not reasons.strip():
            problems.append(f"line {k} (`{name}`): no reasons")
            continue
        if decl is None:
            problems.append(f"line {k} (`{name}`): not a declaration of the dataset at `{ds.commit[:12]}`")
            continue
        yeses = [x for x in store.records if x.get("kind") == "review" and x.get("verdict") == "accept"
                 and (x.get("subject") or {}).get("name") == name and rec.same_reviewer(x.get("by") or {}, by)]
        later = [x for x in yeses if x.get("at", "") >= at]
        if later:
            problems.append(f"line {k} (`{name}`): Voyager said yes to it again later, in record "
                            f"`{max(later, key=lambda x: x.get('at', ''))['id']}`, which counts already")
            continue
        r = {"schema": rec.SCHEMA, "kind": "review", "verdict": "accept", "subject": rec.subject_from_decl(decl, ds),
             "by": by, "at": at, "origin": {"kind": "comment", "ref": ref}, "text": reasons.strip() + TRANSCRIBED}
        if yeses:
            r["links"] = {"supersedes": max(yeses, key=lambda x: x.get("at", ""))["id"]}
        r = rec.with_id(r)
        errs = rec.validate(r, {rubric.name: rubric})
        if errs:
            problems.append(f"line {k} (`{name}`): " + "; ".join(errs))
            continue
        out.append(r)
    return out, problems


def migration(session: str, model: str = MODEL) -> dict:
    """The migration, as the records name it: Claude writing the standard reviews, as the model `model`, through
    CBirkbeck's account, in the run `session`."""
    return {"kind": "agent", "identity": {"kind": "github", "id": "CBirkbeck"}, "involvement": "unknown",
            "agent": {"tool": "Tau Ceti review migration", "model": model, "session": session}}


def now() -> str:
    """The time of the run, as a record keeps one (`TIME`)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def count(n: int, word: str) -> str:
    """`n` of a thing, in the plural unless there is one."""
    return f"{n} {word}{'' if n == 1 else 's'}"


def one_line(text: object) -> str:
    """A text on one line: each run of whitespace, newlines among it, as a space."""
    return " ".join(str(text).split())


def site_link(name: str) -> str:
    """Where the site shows a declaration, addressed as the page does (`encodeURIComponent` of its name)."""
    return f"{SITE_URL}#/d/{quote(name, safe=URI_SAFE)}"


def read_jsonl(path: Path) -> list[dict]:
    """The objects on the lines of a JSONL file, blank lines skipped. The lines are cut at `\\n` only: a review may hold
    a Unicode line separator, which `splitlines` would cut at. ValueError for a line that is no object."""
    rows = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").split("\n"), 1):
        if line.strip():
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{n}: {e}") from e
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{n}: a line is a JSON object")
            rows.append(row)
    return rows


def keyed(rows: list[dict], what: str, problems: list[str]) -> dict[str, dict]:
    """The rows by their declaration. A row with none, or a second row of a declaration, is a problem."""
    out: dict[str, dict] = {}
    for row in rows:
        name = row.get("decl")
        if not isinstance(name, str) or not name:
            problems.append(f"a line of the {what} names no declaration")
        elif name in out:
            problems.append(f"`{name}`: it is in the {what} twice")
        else:
            out[name] = row
    return out


@dataclass
class Plan:
    """What the results come to."""
    #: The records to write, without their origins and ids, in the order of the results.
    records: list[dict] = field(default_factory=list)
    #: The declarations for the owner, each with the reason it is listed, in the order of the results.
    held: list[tuple[str, str]] = field(default_factory=list)
    #: The declarations that have a standard review already, and get no record.
    skipped: list[str] = field(default_factory=list)
    #: What stops the run: while there is any, nothing is written.
    problems: list[str] = field(default_factory=list)


def standard_records(bundles: list[dict], results: list[dict], checks: list[dict], ds: Dataset, store: Store, at: str,
                     session: str, source: Path | None, model: str = MODEL) -> Plan:
    """The records and the held list the results make (see the module's docstring), keyed in `ds`, made at `at` by
    the migration in the run `session`, as the model `model` that wrote the results, against the records of `store` as
    the page reads them for `ds` (evidence-core's `Evidence`: a declaration renamed keeps its records). Each result is
    checked again as migrate_check.py checks it, against `source`, the library at the bundles' commit, and its check
    must agree."""
    plan = Plan()
    by, rubric = migration(session, model), store.rubric
    bundle_of = keyed(bundles, "bundles", plan.problems)
    check_of = keyed(checks, "checks", plan.problems)
    result_of = keyed(results, "results", plan.problems)
    for name in [name for name, result in result_of.items() if migrate_check.unwritten(result)]:
        del result_of[name]  # not written yet: not in this wave, and its check says nothing
        check_of.pop(name, None)
    for name in result_of:
        plan.problems += [f"`{name}`: it has a result but no {what}" for what, rows in
                          (("bundle", bundle_of), ("check", check_of)) if name not in rows]
    plan.problems += [f"`{name}`: it has a check but no result" for name in check_of if name not in result_of]
    off = [name for name in result_of if name in bundle_of and bundle_of[name].get("commit") != ds.commit]
    if off:
        plan.problems.append(f"{len(off)} bundles are at another commit than the dataset's `{ds.commit[:12]}`; "
                             f"`{off[0]}` is at `{str(bundle_of[off[0]].get('commit'))[:12]}`")
    ev = Evidence.resolve(store.records, ds)
    for name, result in result_of.items():
        bundle, check = bundle_of.get(name), check_of.get(name)
        if bundle is None or check is None or name in off:
            continue
        decl = ds.by_name.get(name)
        if decl is None:
            plan.problems.append(f"`{name}`: not a declaration of the dataset at `{ds.commit[:12]}`")
            continue
        # Checked again here, so that a check of another checker, or of other results, decides nothing.
        found = migrate_check.problems(bundle, result, source)
        if (check.get("ok") is True) == bool(found):
            plan.problems.append(f"`{name}`: CHECKS " + (
                "passes it, but checked again here it fails: " + "; ".join(one_line(p) for p in found) if found
                else "fails it, but checked again here it passes") + ". CHECKS is not migrate_check.py's check of "
                "RESULTS as they are: check them again")
            continue
        if "error" in result:
            plan.held.append((name, f"no result: {one_line(result['error'])}"))
            continue
        if found:
            why = "failed checks: " + "; ".join(one_line(p) for p in found)
            if result.get("verdict") == "hold" and one_line(result.get("hold") or ""):
                why += f"; the writer held it: {one_line(result['hold'])}"  # the review is lost, the concern is not
            plan.held.append((name, why))
            continue
        verdict, text, cells = result.get("verdict"), result.get("review"), result.get("cells")
        if verdict not in ("approve", "hold") or not isinstance(text, str):
            plan.problems.append(f"`{name}`: its check passed, but the result is neither an approval nor a hold "
                                 "with a review")
            continue
        text = standard.normalize(text)
        # The checker passed it, so this is a net against a CHECKS file that is not RESULTS': the intake would
        # refuse a first version that fails it.
        wrong = standard.check(text, exists=ds.by_name.__contains__)
        if wrong:
            plan.problems.append(f"`{name}`: its check passed, but the review does not pass `standard.check`: "
                                 + "; ".join(wrong))
            continue
        mine = [r for r, _ in ev.records_on(name)]
        open_no = bundle.get("open_no") is True or bool(ev.open_problems(name))
        hold = verdict == "hold" or open_no
        reason = one_line(result.get("hold") or "") or (OPEN_NO if open_no else "held, with no reason given")
        if any(standard.kind_of(r) == "version" and ev.state(r["id"]) != "withdrawn" for r in mine):
            plan.skipped.append(name)
            if hold:
                plan.held.append((name, reason))
            continue
        subject = rec.subject_from_decl(decl, ds)
        if not hold:
            if not isinstance(cells, dict) or set(cells) != set(rubric.names) \
                    or any(state not in ("checked", "na") for state in cells.values()):
                plan.problems.append(f"`{name}`: an approval's cells are each axis of {rubric.name} once, `checked` or "
                                     f"`na`: {cells!r}")
                continue
            r = {"schema": rec.SCHEMA, "kind": "review", "verdict": "accept", "subject": subject, "by": by, "at": at,
                 "text": text, "rubric": rubric.name, "checked": {axis: cells[axis] for axis in rubric.names},
                 "standard": {"spec": standard.SPEC}}
            earlier = [x for x in mine if standard.is_accept(x) and rec.same_reviewer(x.get("by") or {}, by)]
            if earlier:
                r["links"] = {"supersedes": max(earlier, key=standard.order)["id"]}
            plan.records.append(r)
            continue
        accepts = [x for x in mine if standard.is_accept(x)]
        if not accepts:
            plan.held.append((name, f"{NO_YES}; held because: {reason}"))
            continue
        plan.records.append({"schema": rec.SCHEMA, "kind": "comment", "subject": subject, "by": by, "at": at,
                             "text": text, "standard": {"spec": standard.SPEC, "note": HELD_NOTE},
                             "links": {"replies_to": max(accepts, key=standard.order)["id"]}})
        plan.held.append((name, reason))
    return plan


def write_files(records: list[dict], out_dir: Path, prefix: str, rubric: Rubric) -> tuple[list[Path], list[str]]:
    """Writes `records`, which lack their origins and ids, to `<prefix>-<nn>.jsonl` files of `out_dir`: `PER_FILE` to a
    file, numbered on from the highest number of that prefix there already, and no file there is changed. Each record
    comes from its own line of its file (`RECORDS_URL`). The files written, and what is wrong with the records: while
    any is, nothing is written."""
    out_dir = Path(out_dir)
    have = [int(m[1]) for f in out_dir.glob(f"{prefix}-*.jsonl")
            if (m := re.fullmatch(rf"{re.escape(prefix)}-(\d+)\.jsonl", f.name))] if out_dir.is_dir() else []
    first = max(have, default=0) + 1
    made: list[tuple[str, list[dict]]] = []
    problems: list[str] = []
    for start in range(0, len(records), PER_FILE):
        file = f"{prefix}-{first + start // PER_FILE:02d}.jsonl"
        chunk = []
        for n, r in enumerate(records[start:start + PER_FILE], 1):
            r = rec.with_id({**r, "origin": {"kind": "file", "ref": f"{RECORDS_URL}{file}#L{n}"}})
            problems += [f"`{r['subject']['name']}`: {e}" for e in rec.validate(r, {rubric.name: rubric})]
            chunk.append(r)
        made.append((file, chunk))
    if problems or not made:
        return [], problems
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for file, chunk in made:
        with (out_dir / file).open("x", encoding="utf-8") as f:
            f.write("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in chunk))
        paths.append(out_dir / file)
    return paths, []


def held_line(name: str, why: str) -> str:
    """A declaration's line in the held list: its name, linked to the site, and why it is there."""
    return f"- [`{name}`](<{site_link(name)}>) — {one_line(why)}"


def write_held(path: Path, held: list[tuple[str, str]], approved: list[str], heading: str) -> tuple[int, int]:
    """Reconciles the held list with a run (Important 2 of the final review): the lines of each declaration it approved
    (`approved`) go, and each (declaration, reason) of `held` has one line, the run's, in place of any other of that
    declaration: a line there already as it is stays where it is, and the others go under a heading `heading`, for the
    run. A heading left with no line goes too; the rest of the file is kept as it is. The file is made, with its title,
    when there is none and the run has a line for it. How many lines it added, and how many it took out."""
    path = Path(path)
    lines = path.read_text(encoding="utf-8").split("\n") if path.exists() else HELD_TITLE.split("\n")
    wanted = {name: held_line(name, why) for name, why in held}
    gone, kept, placed = set(approved), [], set()
    for line in lines:
        name = m[1] if (m := HELD_LINE.match(line)) else None
        if name in gone or name in wanted and (line != wanted[name] or name in placed):
            continue
        if name in wanted:
            placed.add(name)
        kept.append(line)
    new = [line for name, line in wanted.items() if name not in placed]
    removed = len(lines) - len(kept)
    if not new and not removed:
        return 0, 0
    # The title and each heading's part, and a heading's part only while it has a line that is not blank.
    parts: list[list[str]] = [[]]
    for line in kept:
        if line.startswith("## "):
            parts.append([])
        parts[-1].append(line)
    blocks = ["\n".join(part).strip("\n") for k, part in enumerate(parts) if k == 0 or any(x.strip() for x in part[1:])]
    if new:
        blocks.append(f"## {heading}\n\n" + "\n".join(new))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(block for block in blocks if block) + "\n", encoding="utf-8")
    return len(new), removed


def run_standard(args: argparse.Namespace) -> int:
    at = args.at or now()
    if not TIME.fullmatch(at):
        print(f"error: --at {at!r} is not a time like 2026-11-02T09:30:00Z", file=sys.stderr)
        return 2
    source = Path(args.source)
    if not source.is_dir():
        print(f"error: no checkout of the library at {source}", file=sys.stderr)
        return 2
    try:
        bundles, results, checks = (read_jsonl(Path(p)) for p in (args.bundles, args.results, args.checks))
        ds, store = Dataset.load(args.dataset), Store.load(args.store)
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    head = migrate_inputs.checkout_commit(source)
    if head is not None and head != ds.commit:
        print(f"error: the checkout {source} is at {head[:12]}, the dataset at {ds.commit[:12]}: give the library at "
              "the bundles' commit", file=sys.stderr)
        return 2
    plan = standard_records(bundles, results, checks, ds, store, at, args.prefix, source, args.model)
    files, problems = [], plan.problems
    if not problems:
        files, problems = write_files(plan.records, Path(args.out_dir), args.prefix, store.rubric)
    if problems:
        print(f"error: {count(len(problems), 'problem')}; nothing is written:", file=sys.stderr)
        for problem in problems[:SHOWN]:
            print(f"  {problem}", file=sys.stderr)
        if len(problems) > SHOWN:
            print(f"  … and {len(problems) - SHOWN} more", file=sys.stderr)
        return 1
    approved = [r["subject"]["name"] for r in plan.records if r["kind"] == "review"]
    added, removed = write_held(Path(args.held), plan.held, approved, f"{args.prefix}, {at}")
    print(f"wrote {count(len(plan.records), 'record')} to {count(len(files), 'file')} in {args.out_dir}, as written by "
          f"{args.model}: {len(approved)} approved, {len(plan.records) - len(approved)} held for the owner as comments")
    print(f"{count(len(plan.held), 'declaration')} for the owner: {count(added, 'line')} added to {args.held}, and "
          f"{count(removed, 'line')} taken out, of declarations approved now or listed again")
    if plan.skipped:
        print(f"{len(plan.skipped)} left alone, since they have a standard review already: "
              + ", ".join(plan.skipped[:10]) + (" …" if len(plan.skipped) > 10 else ""))
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="migrate_records.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    refused = sub.add_parser("voyager-refused", help="Voyager's yeses refused for want of their reasons")
    refused.add_argument("tsv", help="the rows `<line k>\\t<decl>\\t<reasons>`")
    refused.add_argument("--dataset", required=True, help="the dataset of the commit Voyager checked")
    refused.add_argument("--store", default=str(STORE), help="the evidence store (default: evidence/)")
    refused.add_argument("--comment-url", required=True, help="the comment's URL, as GitHub gives it (html_url)")
    refused.add_argument("--at", required=True, help="the comment's time, e.g. 2026-10-30T18:01:39Z")
    refused.add_argument("--session", required=True, help="Voyager's run, e.g. voyager-2026-10-30-1603")
    refused.add_argument("--out", required=True, help="the file of records to write")
    std = sub.add_parser("standard", help="the migration's checked standard reviews, and the list held for the owner")
    std.add_argument("bundles", help="the bundles (scripts/migrate_inputs.py)")
    std.add_argument("results", help="the writers' results (scripts/migrate_write.py collect, or merge)")
    std.add_argument("checks", help="the checks of RESULTS (scripts/migrate_check.py), which this run checks again")
    std.add_argument("--dataset", required=True, help="the dataset of the bundles' commit")
    std.add_argument("--source", required=True, help="a checkout of the library at the bundles' commit, as "
                     "migrate_check.py takes it")
    std.add_argument("--store", default=str(STORE), help="the evidence store (default: evidence/)")
    std.add_argument("--out-dir", default=str(STORE / "records"), help="where the files go (default: evidence/records)")
    std.add_argument("--prefix", required=True, help="the files' name and the run, e.g. standard-migration-2026-11-02")
    std.add_argument("--model", default=MODEL, help=f"the model that wrote the results, which the records name "
                     f"(default {MODEL}): a run takes one model's results")
    std.add_argument("--held", default=str(HELD),
                     help="the list for the owner (default: docs/standard-reviews-held.md)")
    std.add_argument("--at", help="the records' time, e.g. 2026-11-02T09:30:00Z (default: now)")
    args = p.parse_args(argv)
    return run_standard(args) if args.cmd == "standard" else run_voyager_refused(args)


def run_voyager_refused(args: argparse.Namespace) -> int:
    if not TIME.fullmatch(args.at):
        print(f"error: --at {args.at!r} is not a time like 2026-10-30T18:01:39Z", file=sys.stderr)
        return 2
    rows, problems = read_rows(Path(args.tsv))
    records, more = voyager_refused(rows, Dataset.load(args.dataset), Store.load(args.store), args.comment_url,
                                    args.at, args.session)
    problems += more
    if problems:
        print(f"error: {len(problems)} rows cannot be recorded; nothing is written:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records),
                   encoding="utf-8")
    print(f"wrote {len(records)} records to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
