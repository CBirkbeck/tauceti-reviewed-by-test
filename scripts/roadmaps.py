#!/usr/bin/env python3
"""Which roadmap each of the library's declarations belongs to, added to a dataset as the facet `roadmap`
(schema `roadmap/1`), by which the Reviewed page finds the answers about a roadmap's declarations (asked for
on 2026-10-29). Tau Ceti labels every PR with the roadmap it advances, `roadmap/<Area>`, and each commit of
its main is one PR's, which its subject names (`… (#123)`, or `Merge pull request #123 …`). So each line of
a declaration is credited to the PR that last changed it (`git blame --first-parent` at the dataset's
commit) and through that PR's label to a roadmap, and the declaration belongs to the roadmap credited with
most of its lines; on a tie, to the one of them that changed a line last. `roadmap/none` (infrastructure,
dependencies, cross-cutting work) and `roadmap/Unknown` (an attribution missing or invalid) credit nothing,
nor does a commit that names no PR, so a declaration none of whose lines is credited has no row. Each row:
`roadmap`, and `lines`, [how many of its lines are credited to it, how many it has].

  python3 scripts/roadmaps.py --dataset DIR --source CLONE [--roadmap ROADMAP_CLONE] [--jobs N]

`--source` is a clone of the library with its history, not a shallow one; its commit graph is written,
with the paths each commit changed (`git commit-graph write --changed-paths`), which makes blaming a file
seven times faster. The labels are read with `gh` (GitHub's GraphQL API, a request for every hundred PRs:
about 220 for Tau Ceti's).

With `--roadmap CLONE`, a clone of TauCetiRoadmap, it also records the names TauCetiRoadmap has at the commit the
clone is at, which the intake checks a review's roadmap targets against (scripts/standard_intake.py): a review named
TauCeti pull requests' `tauceti-target` ids as roadmap targets (asked for on 2026-11-17). They are the file
`roadmap-names.json` of the dataset, `{"repo", "commit", "names"}`, every word of the roadmaps' Markdown, Lean and TOML
files (`names_in`: a Lean name, a heading's word, a kebab-case label), and the meta's `roadmap`, `{"repo", "commit",
"names": "roadmap-names.json", "count"}`. Some 285,000 names, 6 MB, on 2026-11-17.

Exit 0 when the facet is written; 1 when the labels could not be read, and then nothing is written; 2 on bad
input.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_settings  # noqa: E402

FACET = {"name": "roadmap", "file": "facets/roadmap.jsonl", "schema": "roadmap/1",
         "description": "the roadmap each declaration belongs to: of the PRs that last changed its lines, by their "
                        "`roadmap/<Area>` labels, the roadmap credited with most of its lines (scripts/roadmaps.py), "
                        "and `lines`, [how many of its lines are credited to it, how many it has]"}
#: The labels that name no roadmap: infrastructure and cross-cutting work, and an attribution missing or invalid.
NOT_ROADMAPS = frozenset({"none", "Unknown"})
PR = re.compile(r"\(#(\d+)\)$|^Merge pull request #(\d+)\b")
#: A group of lines in `git blame --incremental`: its commit, its first line before and now, how many lines.
GROUP = re.compile(r"^([0-9a-f]{40}) \d+ (\d+) (\d+)$")
QUERY = """query($owner: String!, $name: String!, $after: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(states: [MERGED, CLOSED], first: 100, after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes { number labels(first: 50) { nodes { name } } } } } }"""


#: The roadmap repository, whose names `--roadmap` records.
ROADMAP_REPO = "TauCetiProject/TauCetiRoadmap"
NAMES_FILE = "roadmap-names.json"
#: A word of a roadmap, as a name is written: a Lean name (`Foo.bar_two'`), a word, a kebab-case label (`SSP-D16`).
NAME = re.compile(r"[^\W][\w'!?.\-]*[\w'!?]|[^\W]")
#: The files of TauCetiRoadmap whose words are names: its roadmaps' READMEs, plans, Lean and metadata.
NAMED_FILES = re.compile(r"^(?:TauCetiRoadmap|Completed)/.*\.(?:md|lean|toml)$")


class LabelsUnread(RuntimeError):
    pass


def names_in(text: str) -> set[str]:
    """The names a text has (`NAME`)."""
    return set(NAME.findall(text))


def roadmap_names(clone: Path) -> tuple[str, list[str]]:
    """The commit a clone of TauCetiRoadmap is at, and the names of its roadmaps' files there, sorted."""
    commit = subprocess.run(["git", "-C", str(clone), "rev-parse", "HEAD"], check=True, capture_output=True,
                            text=True).stdout.strip()
    paths = subprocess.run(["git", "-C", str(clone), "ls-tree", "-r", "-z", "--name-only", commit], check=True,
                           capture_output=True).stdout.decode("utf-8", "replace").split("\0")
    names: set[str] = set()
    for path in paths:
        if NAMED_FILES.match(path):
            blob = subprocess.run(["git", "-C", str(clone), "show", f"{commit}:{path}"], capture_output=True).stdout
            names |= names_in(blob.decode("utf-8", "replace"))
    return commit, sorted(names)


def write_names(dataset: Path, commit: str, names: list[str]) -> None:
    """Put TauCetiRoadmap's names into ``dataset``: `roadmap-names.json`, and the meta's `roadmap`."""
    (dataset / NAMES_FILE).write_text(json.dumps({"repo": ROADMAP_REPO, "commit": commit, "names": names},
                                                 ensure_ascii=False), encoding="utf-8")
    meta = json.loads((dataset / "meta.json").read_text(encoding="utf-8"))
    meta["roadmap"] = {"repo": ROADMAP_REPO, "commit": commit, "names": NAMES_FILE, "count": len(names)}
    (dataset / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def read_names(root: Path | str, meta: dict) -> frozenset[str] | None:
    """The names a dataset recorded of TauCetiRoadmap (`write_names`), or None when it recorded none."""
    entry = meta.get("roadmap") or {}
    path = Path(root) / entry["names"] if entry.get("names") else None
    if path is None or not path.exists():
        return None
    return frozenset(json.loads(path.read_text(encoding="utf-8")).get("names") or [])


def has_name(names: frozenset[str], name: str) -> bool:
    """Whether a roadmap target a review names is among TauCetiRoadmap's names: the name as given, or without the
    library's `TauCeti.` (a roadmap writes its names short); a name of several words, each word."""
    name = name.strip()
    if name in names or name.removeprefix("TauCeti.") in names:
        return True
    words = NAME.findall(name)
    return len(words) > 1 and all(w in names for w in words)


def pr_of(subject: str) -> int | None:
    """The PR a commit of the library's main is, by its subject: a squashed PR's `… (#123)`, or a merge's."""
    m = PR.search(subject)
    return int(m.group(1) or m.group(2)) if m else None


def roadmap_of(labels) -> str | None:
    """The roadmap a PR's labels name: its one `roadmap/<Area>` label, unless that names none."""
    areas = [x[len("roadmap/"):] for x in labels if x.startswith("roadmap/")]
    return areas[0] if len(areas) == 1 and areas[0] not in NOT_ROADMAPS else None


def ask_github(owner: str, name: str, after: str | None) -> dict:
    """A page of the repository's merged and closed PRs (Bors closes the PRs it merges), tried three times."""
    args = ["gh", "api", "graphql", "-f", f"query={QUERY}", "-f", f"owner={owner}", "-f", f"name={name}"]
    if after:
        args += ["-f", f"after={after}"]
    for attempt in range(3):
        try:
            out = subprocess.run(args, check=True, capture_output=True, text=True).stdout
            return json.loads(out)["data"]["repository"]["pullRequests"]
        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError, TypeError) as e:
            if attempt == 2:
                raise LabelsUnread(getattr(e, "stderr", None) or str(e)) from e
            time.sleep(10 * (attempt + 1))
    raise AssertionError("unreachable")


def fetch(repo: str, ask: Callable[[str, str, str | None], dict] = ask_github) -> dict[int, str | None]:
    """Every merged or closed PR of ``repo`` (owner/name) and the roadmap its labels name, if any."""
    owner, name = repo.split("/", 1)
    out, after = {}, None
    while True:
        page = ask(owner, name, after)
        try:
            for n in page["nodes"]:
                out[n["number"]] = roadmap_of(x["name"] for x in n["labels"]["nodes"])
            more, after = page["pageInfo"]["hasNextPage"], page["pageInfo"]["endCursor"]
        except (KeyError, TypeError) as e:
            raise LabelsUnread(f"a page of PRs that says nothing of them: {e}") from e
        if not more:
            return out


def history(source: Path, commit: str) -> tuple[dict[str, int], list[int | None]]:
    """The commits of the library's main up to ``commit``: each one's age (0 for ``commit``, 1 for its parent,
    …), and the PR of each age."""
    out = subprocess.run(["git", "-C", str(source), "log", "--first-parent", "--format=%H %s", commit],
                         check=True, capture_output=True, text=True).stdout
    ages, prs = {}, []
    for line in out.splitlines():
        sha, _, subject = line.partition(" ")
        ages[sha] = len(prs)
        prs.append(pr_of(subject))
    return ages, prs


def blame(source: Path, commit: str, path: str, ages: dict[str, int]) -> list[int | None] | None:
    """The age of the commit that last changed each line of ``path`` at ``commit``, of those of its main (a
    merged branch's lines are the merge's); None when git cannot say."""
    r = subprocess.run(["git", "-C", str(source), "blame", "--first-parent", "--incremental", commit, "--", path],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    lines: dict[int, int | None] = {}
    for line in r.stdout.splitlines():
        m = GROUP.match(line)
        if m:
            age, first, n = ages.get(m.group(1)), int(m.group(2)), int(m.group(3))
            lines.update((k, age) for k in range(first, first + n))
    return [lines.get(k) for k in range(1, max(lines, default=0) + 1)]


def attribute(line_ages: list[int | None], credits: list[str | None]) -> tuple[str, int, int] | None:
    """Of a declaration's lines, each the age of the commit that last changed it, the roadmap credited with most
    (``credits``: each age's roadmap), how many lines it is credited with, and how many there are; on a tie, the
    roadmap of the newest of those lines. None when no line is credited."""
    votes, newest = Counter(), {}
    for age in line_ages:
        roadmap = credits[age] if age is not None and age < len(credits) else None
        if roadmap:
            votes[roadmap] += 1
            newest[roadmap] = min(newest.get(roadmap, age), age)
    if not votes:
        return None
    best = max(votes, key=lambda r: (votes[r], -newest[r]))
    return best, votes[best], len(line_ages)


def rows(source: Path, commit: str, sources: list[dict], labels: dict[int, str | None],
         jobs: int) -> tuple[list[dict], list[str]]:
    """The facet's rows for the declarations ``sources`` places (rows of the facet `source`), and the files git
    could not blame."""
    subprocess.run(["git", "-C", str(source), "commit-graph", "write", "--reachable", "--changed-paths"],
                   capture_output=True)
    ages, prs = history(source, commit)
    credits = [labels.get(pr) if pr is not None else None for pr in prs]
    by_path: dict[str, list[dict]] = defaultdict(list)
    for s in sources:
        by_path[s["path"]].append(s)
    out, unblamed = [], []
    with cf.ThreadPoolExecutor(max(1, jobs)) as ex:
        paths = sorted(by_path)
        for path, line_ages in zip(paths, ex.map(lambda p: blame(source, commit, p, ages), paths)):
            if line_ages is None:
                unblamed.append(path)
                continue
            for s in by_path[path]:
                got = attribute(line_ages[s["start"][0] - 1:s["end"][0]], credits)
                if got:
                    out.append({"decl": s["decl"], "roadmap": got[0], "lines": [got[1], got[2]]})
    return sorted(out, key=lambda r: r["decl"]), unblamed


def write(dataset: Path, facet_rows: list[dict]) -> None:
    """Put the facet into ``dataset``: its file, and its entry in the dataset's meta, in place of any earlier."""
    (dataset / "facets").mkdir(exist_ok=True)
    with (dataset / FACET["file"]).open("w", encoding="utf-8") as f:
        for r in facet_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    meta = json.loads((dataset / "meta.json").read_text(encoding="utf-8"))
    meta["facets"] = [x for x in meta.get("facets", []) if x.get("name") != FACET["name"]] + [{**FACET, "count": len(facet_rows)}]
    (dataset / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def source_rows(dataset: Path, meta: dict) -> list[dict]:
    entry = next((f for f in meta.get("facets", []) if f.get("name") == "source"), None)
    if entry is None:
        return []
    with (dataset / entry["file"]).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def run(dataset: Path, source: Path, settings: dict, labels: Callable[[str], dict] = fetch,
        jobs: int = os.cpu_count() or 4) -> dict:
    meta = json.loads((dataset / "meta.json").read_text(encoding="utf-8"))
    sources = source_rows(dataset, meta)
    out = {"written": False, "declarations": len(sources)}
    try:
        prs = labels(settings["library"]["repo"])
    except LabelsUnread as e:
        out["error"] = str(e)
        return out
    facet_rows, unblamed = rows(source, meta["library"]["commit"], sources, prs, jobs)
    write(dataset, facet_rows)
    return {**out, "written": True, "prs": len(prs), "rows": len(facet_rows),
            "roadmaps": len({r["roadmap"] for r in facet_rows}), "unblamed": unblamed}


def summary(r: dict) -> str:
    return (f"Roadmaps: {r['rows']} of {r['declarations']} declarations credited to {r['roadmaps']} roadmaps, by the "
            f"labels of {r['prs']} PRs; {len(r['unblamed'])} files git could not blame"
            + (": " + ", ".join(r["unblamed"][:20]) if r["unblamed"] else "") + ".")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="roadmaps.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", required=True, type=Path)
    ap.add_argument("--source", required=True, type=Path)
    ap.add_argument("--roadmap", type=Path, help="a clone of TauCetiRoadmap: record its names (`roadmap-names.json`)")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    a = ap.parse_args(argv)
    if not (a.dataset / "meta.json").exists():
        print(f"no dataset at {a.dataset}", file=sys.stderr)
        return 2
    shallow = subprocess.run(["git", "-C", str(a.source), "rev-parse", "--is-shallow-repository"],
                             capture_output=True, text=True)
    if shallow.returncode != 0 or shallow.stdout.strip() != "false":
        print(f"{a.source} is not a clone of the library with its history", file=sys.stderr)
        return 2
    commit = json.loads((a.dataset / "meta.json").read_text(encoding="utf-8"))["library"]["commit"]
    if subprocess.run(["git", "-C", str(a.source), "cat-file", "-e", f"{commit}^{{commit}}"], capture_output=True).returncode:
        print(f"{a.source} does not have the dataset's commit {commit}", file=sys.stderr)
        return 2
    if a.roadmap is not None:
        commit, names = roadmap_names(a.roadmap)
        write_names(a.dataset, commit, names)
        print(f"Roadmap names: {len(names)} names of TauCetiRoadmap at {commit[:12]}.")
    r = run(a.dataset, a.source, load_settings(), jobs=a.jobs)
    if not r["written"]:
        print(f"the PRs' labels could not be read ({r['error']}): nothing written", file=sys.stderr)
        return 1
    print(summary(r))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
