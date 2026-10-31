#!/usr/bin/env python3
"""Records the migration to standard reviews files in the evidence store, as files of records.

  python3 scripts/migrate_records.py voyager-refused TSV --dataset DIR [--store DIR] --comment-url URL
                                     --at TIME --session S --out FILE

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
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT  # noqa: E402

from evidence_core import Dataset  # noqa: E402
from evidence_core import records as rec  # noqa: E402
from evidence_core.store import Store  # noqa: E402

STORE = ROOT / "evidence"
#: What follows the reasons in a record's text.
TRANSCRIBED = " (Reasons transcribed from Voyager's run notes; the line it posted had none.)"
#: A record's time, as the intake keeps GitHub's: RFC 3339 in UTC, to the second.
TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


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
    args = p.parse_args(argv)
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
