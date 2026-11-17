#!/usr/bin/env python3
"""Who wrote each of the library's declarations, as GitHub logins, added to a dataset as the facet `authors`
(schema `authors/1`): the intake refuses an approval, a write or an edit of a declaration's standard review from one
of its authors, and the site counts none of their yeses (AI-REVIEWS.md, "Rules"; asked for on 2026-11-17, after a
bulk run reviewed eight declarations of its own account's).

An author of a declaration is anyone who wrote or changed a line of it, at any time: its statement, its proof, its
docstring and its attributes, the lines `source` places it at in the dataset's commit. Each of those lines is followed
back through every commit of the library's main that changed it (its history: `git log --first-parent -p -U0`, read
once, oldest first, for every Lean file at once):

- a line a commit changed carries that commit and everything the lines it replaced carried, so a declaration rewritten
  wholesale keeps the authors of what it replaced, and a hypothesis changed in place names its changer;
- a line a commit deleted from inside a declaration leaves that commit, and what the line carried, on the gap it left;
- a file renamed keeps its lines (`-M`, with no limit on how many files a commit renames), and a line moved, to
  another file or within one, in the same commit (a file split in two), carries what the line it was moved from
  carried: a line of at least `MOVED` characters, or one that opens a declaration, deleted and added in one commit with
  the same text, is the same line;
- a merge's lines are its pull request's commits', not its merger's.

A commit's people are its author and every `Co-authored-by:` trailer: much of the library is committed by a bot account
with the person it works for as co-author, and counting authors alone missed them. A person is a GitHub login: from a
`users.noreply.github.com` address directly, from the owner's map of addresses to logins (`authors.emails` in
data/settings.json, or the JSON object `--emails` names), and else from GitHub, which knows the account of every address
a user has verified (`Commit.authors` in its GraphQL API, which lists the co-authors too: a request for every `BATCH`
commits, one commit for each address). GitHub's own address (`NOT_PEOPLE`) is no one. An address none of these resolves
is counted in the row's `unknown`, and listed in the facet's entry in the meta, so that the owner can map it: a check
that cannot name every author says so. One person's several accounts are the settings' `authors.same_person`, which the
intake and the site read (scripts/authorship.py); git cannot know them.

Each row: `decl`, `authors` (the logins, sorted), `commits` (how many commits its lines' history holds), and `unknown`
when some of their people have no login.

  python3 scripts/authors.py --dataset DIR --source CLONE [--emails FILE]

`--source` is a clone of the library with its history, not a shallow one, which has the dataset's commit. The logins
are asked of GitHub with `gh`. On 2026-11-17, over Tau Ceti's 37,390 commits and 417,617 declarations, the history
took 45 seconds and 0.7 GB of memory, and the addresses three requests, after which 36 addresses of 335 commits had no
login. `git log -L` for each declaration instead would take some 40 hours (0.34 s each), and misses moved lines.

Exit 0 when the facet is written; 1 when GitHub could not be asked, and then nothing is written; 2 on bad input.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_settings  # noqa: E402

FACET = {"name": "authors", "file": "facets/authors.jsonl", "schema": "authors/1",
         "description": "the GitHub logins of everyone who wrote or changed a line of the declaration, in any commit of "
                        "the library's main, its co-authors (`Co-authored-by:`) too, across renames, rewrites and moves "
                        "(scripts/authors.py); `commits`, how many commits its lines' history holds; `unknown`, how many "
                        "of their people have no login"}
#: A GitHub noreply address: `12345+login@users.noreply.github.com`, or the older `login@users.noreply.github.com`.
NOREPLY = re.compile(r"^(?:\d+\+)?([A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\[bot\])?)@users\.noreply\.github\.com$",
                     re.I)
#: Addresses that are no person's: GitHub's own (`Co-authored-by: Claude Code <noreply@github.com>` names its web-flow
#: account, which commits what is merged on the web), and an AI assistant's trailer (`Co-Authored-By: Claude
#: <noreply@anthropic.com>`), which names no reviewer.
NOT_PEOPLE = frozenset({"noreply@github.com", "noreply@anthropic.com"})
#: A `Co-authored-by:` trailer's value: `Name <address>`.
PERSON = re.compile(r"^\s*(.*?)\s*<([^<>]+)>\s*$")
#: The fewest characters (spaces aside) a line has that is taken for the same line when a commit deletes it in one
#: place and adds it in another; shorter lines (`simp`, `rfl`, `· exact h`) are too common to say so.
MOVED = 25
#: A line that opens a declaration, which names it: the same line wherever it moves, however short.
OPENS = re.compile(r"^(?:@\[.*\]\s*)?(?:(?:private|protected|noncomputable|nonrec|partial|unsafe)\s+)*"
                   r"(?:theorem|lemma|def|abbrev|instance|structure|class|inductive|opaque|axiom)\s+\S")
#: A hunk of a diff without context: `@@ -a,b +c,d @@`.
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
#: The line that starts each commit of the history (`--format=%x00commit %H`).
MARK = "\x00commit "
BATCH = 50
QUERY_ITEM = '{alias}: object(oid: "{oid}") {{ ... on Commit {{ authors(first: 50) {{ nodes {{ email user {{ login }} }} }} }} }}'


class GitHubUnread(RuntimeError):
    pass


# --- who a commit's people are --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Person:
    name: str
    email: str


def people_of(author_name: str, author_email: str, trailers: str) -> list[Person]:
    """A commit's people: its author, then each `Co-authored-by:` trailer's (`Name <address>`), each once."""
    out = [Person(author_name, author_email.strip().lower())]
    for value in trailers.split("\x1f"):
        m = PERSON.match(value)
        if m and m[2].strip():
            out.append(Person(m[1], m[2].strip().lower()))
    return list(dict.fromkeys(out))


def noreply_login(email: str) -> str | None:
    """The login a GitHub noreply address names, or None for any other address."""
    m = NOREPLY.match(email or "")
    return m[1] if m else None


def ask_github(repo: str, oids: list[str]) -> dict[str, list[tuple[str, str | None]]]:
    """For each commit of ``repo`` (owner/name), its people as GitHub knows them: (address, login or None), in one
    GraphQL request, tried three times."""
    owner, name = repo.split("/", 1)
    items = " ".join(QUERY_ITEM.format(alias=f"c{k}", oid=oid) for k, oid in enumerate(oids))
    query = f'query {{ repository(owner: "{owner}", name: "{name}") {{ {items} }} }}'
    for attempt in range(3):
        try:
            out = subprocess.run(["gh", "api", "graphql", "-f", f"query={query}"], check=True, capture_output=True,
                                 text=True).stdout
            data = json.loads(out)["data"]["repository"]
            return {oid: [(n.get("email") or "", (n.get("user") or {}).get("login"))
                          for n in ((data.get(f"c{k}") or {}).get("authors") or {}).get("nodes") or []]
                    for k, oid in enumerate(oids)}
        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError, TypeError) as e:
            if attempt == 2:
                raise GitHubUnread(getattr(e, "stderr", None) or str(e)) from e
            time.sleep(10 * (attempt + 1))
    raise AssertionError("unreachable")


def logins(people_by_commit: dict[str, list[Person]], repo: str, overrides: dict[str, str],
           ask: Callable[[str, list[str]], dict] = ask_github) -> dict[str, str]:
    """Each address of ``people_by_commit`` (commit → its people) that names a GitHub account, and its login: a noreply
    address by itself, one of ``overrides`` (address → login) as it says, and the rest as GitHub knows them, asked
    `BATCH` commits a request, each commit chosen for an address not yet known."""
    out: dict[str, str] = {}
    first: dict[str, str] = {}  # an address not known yet, and a commit it is a person of
    for oid, people in people_by_commit.items():
        for p in people:
            if p.email in NOT_PEOPLE:
                continue
            login = overrides.get(p.email) or noreply_login(p.email)
            if login:
                out[p.email] = login
            elif p.email not in out:
                first.setdefault(p.email, oid)
    asked: set[str] = set()
    while True:
        todo = sorted({oid for email, oid in first.items() if email not in out and email not in asked})
        if not todo:
            return out
        for k in range(0, len(todo), BATCH):
            for oid, found in ask(repo, todo[k:k + BATCH]).items():
                for email, login in found:
                    if login and email and email.strip().lower() not in NOT_PEOPLE:
                        out.setdefault(email.strip().lower(), login)
        # An address GitHub knows no account of is asked once: its commit was asked.
        asked |= {email for email, oid in first.items() if oid in set(todo)}


def canonical(login_of: dict[str, str]) -> dict[str, str]:
    """``login_of`` with each login spelt one way: GitHub's logins are the same in any case, and a noreply address may
    spell one in lowercase that GitHub spells `AbC`. The spelling taken is the one most addresses give."""
    spellings: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for login in login_of.values():
        spellings[login.lower()][login] += 1
    best = {k: max(v, key=lambda x: (v[x], x != x.lower())) for k, v in spellings.items()}
    return {email: best[login.lower()] for email, login in login_of.items()}


# --- the lines' history ---------------------------------------------------------------------------------------------

class Provenances:
    """The sets of commits a line can carry, each kept once and named by its place in `sets` (0: none)."""

    def __init__(self):
        self.sets: list[frozenset] = [frozenset()]
        self.index: dict[frozenset, int] = {frozenset(): 0}

    def of(self, commits: Iterable[int]) -> int:
        s = frozenset(commits)
        if s not in self.index:
            self.index[s] = len(self.sets)
            self.sets.append(s)
        return self.index[s]

    def union(self, ids: Iterable[int], *more: int) -> int:
        ids = [i for i in ids if i]
        if not more and len(set(ids)) <= 1:
            return ids[0] if ids else 0
        out: set[int] = set(more)
        for i in set(ids):
            out |= self.sets[i]
        return self.of(out)


@dataclass
class FileState:
    """A file's lines, each the provenance (a `Provenances` id) of the line, and of the gap before it: what a commit
    deleted there."""
    lines: list[int] = field(default_factory=list)
    gaps: list[int] = field(default_factory=list)


@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    deleted: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)


@dataclass
class FileDiff:
    old: str | None  # None: a new file
    new: str | None  # None: a deleted file
    hunks: list[Hunk] = field(default_factory=list)


def key(line: str) -> str | None:
    """What a deleted line and an added line must share to be one line moved: its text, its spaces aside, when it is
    long enough to tell apart (`MOVED`) or opens a declaration; else None."""
    text = " ".join(line.split())
    return text if len(text.replace(" ", "")) >= MOVED or OPENS.match(text) else None


def apply(state: FileState, hunks: list[Hunk], commit: int, prov: Provenances, moved: dict[str, list[int]]) -> FileState:
    """The file after a commit's ``hunks`` (`-U0`, in order): a line it adds carries the commit, what the lines its hunk
    replaces carried and the gaps among them, and what the line it was moved from carried (``moved``, by `key`); a
    deletion with nothing added leaves the commit and what it deleted on the gap after it."""
    old_lines, old_gaps = state.lines, state.gaps
    lines: list[int] = []
    gaps: list[int] = []
    pos = 0  # the next line of the old file to copy
    pending = 0  # what a deletion left, for the gap before the next line copied
    for h in hunks:
        start = h.old_start - 1 if h.old_count else h.old_start  # where the hunk's old lines start (0-based)
        start = max(start, pos)
        if start > pos:
            lines += old_lines[pos:start]
            gaps += old_gaps[pos:start]
            if pending:
                gaps[len(gaps) - (start - pos)] = prov.union([gaps[len(gaps) - (start - pos)], pending])
                pending = 0
        end = min(start + h.old_count, len(old_lines))
        replaced = old_lines[start:end] + old_gaps[start + 1:end]
        if h.new_count:
            base = prov.union(replaced, commit)
            first = prov.union([old_gaps[start] if h.old_count and start < len(old_gaps) else 0, pending])
            pending = 0
            for k, text in enumerate(h.added[:h.new_count] + [""] * (h.new_count - len(h.added))):
                k_ = key(text)
                came = moved.get(k_) if k_ is not None else None
                lines.append(prov.union([base, came.pop()]) if came else base)
                gaps.append(first if k == 0 else 0)
        elif h.old_count:
            before = old_gaps[start] if start < len(old_gaps) else 0
            pending = prov.union([pending, before, *replaced], commit)
        pos = end
    if pos < len(old_lines):
        lines += old_lines[pos:]
        gaps += old_gaps[pos:]
        if pending:
            gaps[len(gaps) - (len(old_lines) - pos)] = prov.union([gaps[len(gaps) - (len(old_lines) - pos)], pending])
    return FileState(lines, gaps)


def parse(stream: Iterable[str]) -> Iterator[tuple[str, list[FileDiff]]]:
    """The commits of `git log -p -U0 --format=<MARK>%H` output, oldest first as it was asked for: each commit and the
    diffs of its files. A binary file has no hunks, and is left as it is."""
    sha, files, current, hunk = None, [], None, None
    for raw in stream:
        line = raw.rstrip("\n")
        if line.startswith(MARK):
            if sha is not None:
                yield sha, files
            sha, files, current, hunk = line[len(MARK):].strip(), [], None, None
            continue
        if line.startswith("diff --git "):
            m = re.match(r'^diff --git "?a/(.*?)"? "?b/(.*)"?$', line)
            path_a, path_b = (m[1], m[2].rstrip('"')) if m else (None, None)
            current, hunk = FileDiff(path_a, path_b), None
            files.append(current)
            continue
        if current is None:
            continue
        if hunk is None or not line[:1] in ("+", "-", "\\"):
            if line.startswith("new file mode"):
                current.old = None
            elif line.startswith("deleted file mode"):
                current.new = None
            elif line.startswith("rename from "):
                current.old = line[len("rename from "):]
            elif line.startswith("rename to "):
                current.new = line[len("rename to "):]
            elif m := HUNK.match(line):
                hunk = Hunk(int(m[1]), int(m[2]) if m[2] is not None else 1, int(m[3]), int(m[4]) if m[4] is not None else 1)
                current.hunks.append(hunk)
            continue
        if line.startswith("-"):
            hunk.deleted.append(line[1:])
        elif line.startswith("+"):
            hunk.added.append(line[1:])
    if sha is not None:
        yield sha, files


def history(commits: list[str], diffs: Iterable[tuple[str, list[FileDiff]]]) -> tuple[dict[str, FileState], Provenances]:
    """Every file's lines after the commits ``diffs`` gives, oldest first, each with the commits of its history (their
    places in ``commits``)."""
    place = {sha: k for k, sha in enumerate(commits)}
    prov = Provenances()
    files: dict[str, FileState] = {}
    for sha, changed in diffs:
        commit = place[sha]
        moved: dict[str, list[int]] = defaultdict(list)  # a deleted line's key, and what each such line carried
        for d in changed:
            if d.old is None:
                continue
            state = files.get(d.old, FileState())
            for h in d.hunks:
                for k, text in enumerate(h.deleted):
                    i = h.old_start - 1 + k
                    k_ = key(text)
                    if k_ is not None and 0 <= i < len(state.lines):
                        moved[k_].append(state.lines[i])
        before = dict(files)
        for d in changed:
            if d.old is not None and d.old != d.new:
                files.pop(d.old, None)
        for d in changed:
            if d.new is None:
                continue
            state = before.get(d.old, FileState()) if d.old is not None else FileState()
            files[d.new] = apply(state, d.hunks, commit, prov, moved) if d.hunks else state
    return files, prov


def git_lines(source: Path, args: list[str]) -> Iterator[str]:
    """The lines git prints, as they come, decoded leniently: some files of a history are not UTF-8."""
    p = subprocess.Popen(["git", "-C", str(source), *args], stdout=subprocess.PIPE)
    assert p.stdout is not None
    for raw in p.stdout:
        yield raw.decode("utf-8", "replace")
    if p.wait():
        raise subprocess.CalledProcessError(p.returncode, args)


def commits_of(source: Path, commit: str) -> tuple[list[str], dict[str, list[Person]]]:
    """The commits of the library's main up to ``commit``, oldest first, and each one's people. A merge's people are
    those of its pull request's commits, which the merge brings in."""
    fmt = "%H%x00%P%x00%an%x00%ae%x00%(trailers:key=Co-authored-by,valueonly,separator=%x1f)%x1e"

    def read(*rev: str) -> list[list[str]]:
        out = subprocess.run(["git", "-C", str(source), "log", f"--format={fmt}", *rev], check=True,
                             capture_output=True).stdout.decode("utf-8", "replace")
        return [row.strip("\n").split("\x00") for row in out.split("\x1e") if row.strip()]

    order, people = [], {}
    for sha, parents, name, email, trailers in read("--first-parent", "--reverse", commit):
        order.append(sha)
        parents_ = parents.split()
        if len(parents_) > 1:
            merged = read(f"{parents_[0]}..{parents_[1]}")
            people[sha] = list(dict.fromkeys(p for row in merged for p in people_of(row[2], row[3], row[4])))
        else:
            people[sha] = people_of(name, email, trailers)
    return order, people


def lines_history(source: Path, commit: str, commits: list[str]) -> tuple[dict[str, FileState], Provenances]:
    stream = git_lines(source, ["-c", "diff.renameLimit=0", "-c", "core.quotePath=false", "log", "--first-parent", "--reverse", "-p", "-U0", "-M",
                                "--no-color", "--no-ext-diff", "--format=%x00commit %H", commit, "--", "*.lean"])
    return history(commits, parse(stream))


# --- the facet ------------------------------------------------------------------------------------------------------

def rows(sources: list[dict], files: dict[str, FileState], prov: Provenances, people: list[list[Person]],
         login_of: dict[str, str]) -> list[dict]:
    """The facet's rows for the declarations ``sources`` places (rows of the facet `source`, lines from 1): the logins
    of the people of every commit its lines and the gaps among them carry."""
    out = []
    for s in sources:
        state = files.get(s["path"])
        if state is None:
            continue
        a, b = s["start"][0] - 1, s["end"][0]
        ids = state.lines[a:b] + state.gaps[a + 1:b]
        commits = set().union(*(prov.sets[i] for i in set(ids))) if ids else set()
        names, unknown = set(), set()
        for c in commits:
            for p in people[c]:
                login = login_of.get(p.email)
                if login:
                    names.add(login)
                elif p.email not in NOT_PEOPLE:
                    unknown.add(p.email)
        row = {"decl": s["decl"], "authors": sorted(names, key=str.lower), "commits": len(commits)}
        if unknown:
            row["unknown"] = len(unknown)
        out.append(row)
    return sorted(out, key=lambda r: r["decl"])


def write(dataset: Path, facet_rows: list[dict], unresolved: list[dict]) -> None:
    """Put the facet into ``dataset``: its file, and its entry in the dataset's meta, in place of any earlier, with the
    addresses that have no login."""
    (dataset / "facets").mkdir(exist_ok=True)
    with (dataset / FACET["file"]).open("w", encoding="utf-8") as f:
        for r in facet_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    meta = json.loads((dataset / "meta.json").read_text(encoding="utf-8"))
    entry = {**FACET, "count": len(facet_rows), "unresolved": unresolved}
    meta["facets"] = [x for x in meta.get("facets", []) if x.get("name") != FACET["name"]] + [entry]
    (dataset / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def source_rows(dataset: Path, meta: dict) -> list[dict]:
    entry = next((f for f in meta.get("facets", []) if f.get("name") == "source"), None)
    if entry is None:
        return []
    with (dataset / entry["file"]).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def run(dataset: Path, source: Path, repo: str, overrides: dict[str, str],
        ask: Callable[[str, list[str]], dict] = ask_github) -> dict:
    meta = json.loads((dataset / "meta.json").read_text(encoding="utf-8"))
    commit = meta["library"]["commit"]
    sources = source_rows(dataset, meta)
    started = time.time()
    order, people = commits_of(source, commit)
    try:
        login_of = canonical(logins(people, repo, {k.lower(): v for k, v in overrides.items()}, ask))
    except GitHubUnread as e:
        return {"written": False, "error": str(e)}
    files, prov = lines_history(source, commit, order)
    facet_rows = rows(sources, files, prov, [people[sha] for sha in order], login_of)
    counts: dict[str, int] = defaultdict(int)
    names: dict[str, str] = {}
    for sha in order:
        for p in people[sha]:
            if p.email not in login_of and p.email not in NOT_PEOPLE:
                counts[p.email] += 1
                names.setdefault(p.email, p.name)
    unresolved = [{"email": e, "name": names[e], "commits": n} for e, n in sorted(counts.items(), key=lambda x: -x[1])]
    write(dataset, facet_rows, unresolved)
    return {"written": True, "declarations": len(sources), "rows": len(facet_rows), "commits": len(order),
            "logins": len(set(login_of.values())), "unresolved": len(unresolved),
            "unknown": sum(1 for r in facet_rows if r.get("unknown")), "seconds": round(time.time() - started)}


def summary(r: dict) -> str:
    return (f"Authors: {r['rows']} of {r['declarations']} declarations, from {r['commits']} commits and "
            f"{r['logins']} logins in {r['seconds']} s; {r['unresolved']} addresses have no login, which "
            f"{r['unknown']} declarations' histories hold.")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="authors.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", required=True, type=Path)
    ap.add_argument("--source", required=True, type=Path)
    ap.add_argument("--emails", type=Path, help="a JSON object, address to GitHub login, for addresses GitHub cannot map "
                                                "(default: `authors.emails` in data/settings.json)")
    a = ap.parse_args(argv)
    if not (a.dataset / "meta.json").exists():
        print(f"no dataset at {a.dataset}", file=sys.stderr)
        return 2
    shallow = subprocess.run(["git", "-C", str(a.source), "rev-parse", "--is-shallow-repository"],
                             capture_output=True, text=True)
    if shallow.returncode != 0 or shallow.stdout.strip() != "false":
        print(f"{a.source} is not a clone of the library with its history", file=sys.stderr)
        return 2
    meta = json.loads((a.dataset / "meta.json").read_text(encoding="utf-8"))
    commit, repo = meta["library"]["commit"], meta["library"].get("repo", "")
    if subprocess.run(["git", "-C", str(a.source), "cat-file", "-e", f"{commit}^{{commit}}"],
                      capture_output=True).returncode:
        print(f"{a.source} does not have the dataset's commit {commit}", file=sys.stderr)
        return 2
    overrides = json.loads(a.emails.read_text(encoding="utf-8")) if a.emails else \
        load_settings().get("authors", {}).get("emails", {})
    r = run(a.dataset, a.source, repo, overrides)
    if not r["written"]:
        print(f"GitHub could not be asked for the logins ({r['error']}): nothing written", file=sys.stderr)
        return 1
    print(summary(r))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
