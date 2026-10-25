#!/usr/bin/env python3
"""Whether the signatures the site shows say what the API docs say: the safeguard set up on
2026-10-25, after the extractor printed existentials without their binders' types (the site showed
`AlgebraicGeometry.Scheme.exists_isClosedImmersion_proj` as `∃ V, … ∃ f, …`, hiding
`f : X ⟶ Proj (TauCeti.SymmetricAlgebra.homogeneousSubmodule k ↥V)`, which the docs show).

Two checks on a dataset:
- every signature, without the network: no binder printed without its type (`∃ x,`, `fun x =>`);
- against the docs: each declaration Voyager named, each one with a record in the store, and two
  samples of the rest (one from all of them, one from those that bind variables), each compared with
  the header the docs show for it, namespaces, universes and spacing set aside. A module that changed
  between the dataset's commit and the commit the docs were built at is left out, and counted.

  python3 scripts/check_signatures.py --dataset DIR [--source TAUCETI_CHECKOUT] [--offline]
         [--sample N] [--report FILE]

Exit 0 when both pass, 1 when either finds a difference, 2 when the docs cannot be read.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, header, load_settings  # noqa: E402

IDENT = r"[^\W\d][\w'!?]*"
#: A binder printed without its type: `∃ x,`, `∃! x y,`, `∀ x,`, `fun x =>`, `∑ i,`, `⋃ i,`, `∫ x in s,`,
#: `{x | p x}`, `{x // p x}`. (`∃ x ∈ s,`, whose type the set gives, is not one.)
UNTYPED = re.compile(rf"(?:∃!?|∀|fun|λ|∑|∏|⋃|⋂|⨆|⨅|∫⁻?) {IDENT}(?: {IDENT})*\s*(?:,|=>|↦)"
                     rf"|\{{{IDENT}(?: {IDENT})* (?:\||//)")
#: A signature that binds variables, where a lost type would hide something.
BINDS = re.compile(r"∃|∀|fun |λ|∑|∏|⋃|⋂|⨆|⨅|∫")
UNIVERSES = re.compile(r"\.\{[^{}]*\}")
#: The namespaces before a name (`AlgebraicGeometry.Scheme.` of `AlgebraicGeometry.Scheme.Hom.IsOver`):
#: the docs print names relative to the declaration's namespace, the extractor in full.
PREFIX = re.compile(rf"(?<![\w'!?.])(?:{IDENT}\.)+(?={IDENT})")
KEYWORDS = {"theorem", "lemma", "def", "abbrev", "instance", "structure", "class", "inductive", "axiom",
            "opaque", "example", "irreducible_def"}
#: What the docs may write before the keyword (`noncomputable def`).
MODIFIERS = {"noncomputable", "private", "protected", "partial", "unsafe", "nonrec"}
BLOB = re.compile(r"/blob/([0-9a-f]{40})/")


def untyped(text: str) -> str | None:
    """The first binder printed without its type, if there is one."""
    m = UNTYPED.search(text)
    return m.group(0) if m else None


def normal(text: str) -> str:
    """A header as compared: no keyword, universes, namespaces or spacing."""
    words = text.split(None, 3)
    k = 0
    while k < len(words) - 1 and words[k] in MODIFIERS:
        k += 1
    if k < len(words) and words[k] in KEYWORDS:
        text = text.split(None, k + 1)[k + 1] if len(words) > k + 1 else ""
    return re.sub(r"\s+", "", PREFIX.sub("", UNIVERSES.sub("", text)))


class Headers(HTMLParser):
    """The text of each declaration's header on one of the docs' module pages, by name, and the commit
    its source links name."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.headers: dict[str, str] = {}
        self.commit: str | None = None
        self.decl: str | None = None
        self.depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        a = dict(attrs)
        if tag == "a" and self.commit is None:
            m = BLOB.search(a.get("href") or "")
            if m:
                self.commit = m.group(1)
        if tag != "div":
            return
        if self.depth:
            self.depth += 1
            return
        cls = (a.get("class") or "").split()
        if "decl" in cls and a.get("id"):
            self.decl = a["id"]
        elif "decl_header" in cls and self.decl:
            self.depth, self.parts = 1, []

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self.depth:
            self.depth -= 1
            if not self.depth:
                self.headers[self.decl] = "".join(self.parts)
                self.decl = None

    def handle_data(self, data: str) -> None:
        if self.depth:
            self.parts.append(data)


def page(url: str, tries: int = 4) -> str:
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                return r.read().decode("utf-8")
        except Exception:  # noqa: BLE001 -- a page that will not come is a failure below
            if i == tries - 1:
                raise
            time.sleep(2 ** i)
    raise AssertionError("unreachable")


def headers_of(docs: str, module: str) -> Headers:
    """The headers on a module's page: none for a module the docs do not have (newer than they are)."""
    h = Headers()
    try:
        h.feed(page(f"{docs}/{module.replace('.', '/')}.html"))
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    return h


def changed(source: Path | None, repo: str, old: str, new: str) -> set[str] | None:
    """The paths that differ between two commits of the library (None when that cannot be told)."""
    if old == new:
        return set()
    if source is None:
        return None
    git = lambda *a: subprocess.run(["git", "-C", str(source), *a], capture_output=True, text=True)  # noqa: E731
    for c in (old, new):
        if git("cat-file", "-e", f"{c}^{{commit}}").returncode:
            git("fetch", "-q", "--depth", "1", f"https://github.com/{repo}", c)
    out = git("diff", "--name-only", old, new)
    return set(out.stdout.split()) if out.returncode == 0 else None


def rows(path: Path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def recorded(store: Path) -> set[str]:
    """The declarations the store has a record about."""
    names = set()
    for f in sorted((store / "records").glob("*.jsonl")):
        for r in rows(f):
            name = (r.get("subject") or {}).get("name")
            if name:
                names.add(name)
    return names


def check(dataset: Path, settings: dict, store: Path, voyager: Path, source: Path | None = None,
          offline: bool = False, sample: int = 400, fetch=headers_of, jobs: int = 12) -> dict:
    sigs = {r["decl"]: header(r)[0] for r in rows(dataset / "facets" / "signature.jsonl")}
    out: dict = {"signatures": len(sigs), "untyped": [], "compared": 0, "differ": [], "missing": [],
                 "skipped": 0, "docs": None}
    for name, text in sigs.items():
        bad = untyped(text)
        if bad:
            out["untyped"].append([name, bad])
    if offline:
        return out
    decls = {d["name"]: d for d in rows(dataset / "decls.jsonl") if d.get("scope") == "project"}
    paths = {r["decl"]: r["path"] for r in rows(dataset / "facets" / "source.jsonl") if r.get("path")}
    meta = json.loads((dataset / "meta.json").read_text(encoding="utf-8"))
    commit, repo = meta["library"]["commit"], settings["library"]["repo"]
    named = {r["decl"] for r in rows(voyager)} if voyager.exists() else set()
    first = sorted((named | recorded(store)) & decls.keys() & sigs.keys())
    pool = sorted(n for n in decls.keys() & sigs.keys() if n not in set(first))
    rnd = random.Random(commit)
    picked = set(rnd.sample(pool, min(sample, len(pool))))
    binding = sorted(n for n in pool if n not in picked and BINDS.search(sigs[n]))
    picked |= set(rnd.sample(binding, min(sample, len(binding))))
    chosen = first + sorted(picked)
    modules = sorted({decls[n]["module"] for n in chosen})
    with cf.ThreadPoolExecutor(jobs) as pool_:
        pages = dict(zip(modules, pool_.map(lambda m: fetch(settings["library"]["docs"].rstrip("/"), m), modules)))
    docs_commits = {h.commit for h in pages.values() if h.commit}
    out["docs"] = sorted(docs_commits)
    moved = {c: changed(source, repo, c, commit) for c in docs_commits}
    for name in chosen:
        h = pages[decls[name]["module"]]
        diff = moved.get(h.commit, set()) if h.commit else set()
        if diff is None or paths.get(name) in diff:
            out["skipped"] += 1
            continue
        theirs = h.headers.get(name)
        if theirs is None:
            out["missing"].append(name)
            continue
        out["compared"] += 1
        if normal(theirs) != normal(sigs[name]):
            out["differ"].append({"decl": name, "site": sigs[name], "docs": " ".join(theirs.split())})
    return out


def report(r: dict, limit: int = 40) -> str:
    lines = [f"Signatures checked: {r['signatures']} for binders without their types, "
             f"{len(r['untyped'])} found."]
    if r["docs"] is not None:
        lines.append(f"Against the docs (built at {', '.join(c[:12] for c in r['docs']) or 'an unknown commit'}): "
                     f"{r['compared']} compared, {len(r['differ'])} differ; {r['skipped']} left out (their file "
                     f"changed since the docs were built), {len(r['missing'])} not in the docs.")
    for name, bad in r["untyped"][:limit]:
        lines.append(f"- `{name}`: `{bad}`")
    for d in r["differ"][:limit]:
        lines += [f"- `{d['decl']}`", f"  - site: `{' '.join(d['site'].split())}`", f"  - docs: `{d['docs']}`"]
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="check_signatures.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", required=True, type=Path)
    ap.add_argument("--source", type=Path)
    ap.add_argument("--store", type=Path, default=ROOT / "evidence")
    ap.add_argument("--voyager", type=Path, default=ROOT / "data" / "voyager.jsonl")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--sample", type=int, default=400)
    ap.add_argument("--report", type=Path)
    a = ap.parse_args(argv)
    try:
        r = check(a.dataset, load_settings(), a.store, a.voyager, a.source, a.offline, a.sample)
    except OSError as e:
        print(f"the docs could not be read: {e}", file=sys.stderr)
        return 2
    text = report(r)
    if a.report:
        a.report.write_text(text, encoding="utf-8")
    print(text, end="")
    return 1 if r["untyped"] or r["differ"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
