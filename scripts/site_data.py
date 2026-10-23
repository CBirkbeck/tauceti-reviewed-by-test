"""Everything the site's pages show, as JSON, laid out from the dataset (S2), the evidence store (S3)
and what evidence-core computes from them. Nothing here judges a record or a declaration:
evidence-core does (statuses, threads, where a declaration stands, coverage, the review queue, the
dependency graphs summarized for readers). This module only arranges what it says, sharded so that a
page loads only what it shows (web/data.js reads it)."""
from __future__ import annotations

import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from evidence_core import docs as docs_mod
from evidence_core import records as rec
from evidence_core import views
from evidence_core.coverage import Evidence, Policy, coverage, queue
from evidence_core.dataset import Dataset, Decl
from evidence_core.graphs import Graphs, is_auxiliary
from evidence_core.source import Sources, split_statement
from evidence_core.store import Store, with_imports

from common import fnv_shard

NODE_SHARD = 2048
NAME_SHARDS = 64
CAP = 60
TEXT_CAP = 4000
#: People only, and people with AI agents; every other switch at evidence-core's default.
POLICIES = (Policy(agents=False), Policy(agents=True))
#: The page's state codes: the index in this tuple.
STATES = ("unreviewed", "covered", "uncounted", "stale", "problem", "disputed")
KIND_CODE = {"theorem": "t", "definition": "d", "structure": "s", "class": "c", "inductive": "n",
             "instance": "i", "axiom": "a", "opaque": "o"}
#: The kinds whose text past the statement is shown, as the docs show it: a definition's value (the docs'
#: Equations), a structure's or inductive type's fields. A theorem's proof and an instance's value are not.
VALUE_KINDS = frozenset({"definition", "opaque", "structure", "class", "inductive"})
PROJECT, NAMED, BASIC, ROUTINE, DOCUMENTED, AUX, SORRY = 1, 2, 4, 8, 16, 32, 64
#: The longest statement a list shows.
BRIEF_CAP = 140
BRACKETS = {"(": ")", "[": "]", "{": "}", "⦃": "⦄"}
CLOSING = frozenset(BRACKETS.values())
#: An argument that only introduces a type, `(R : Type u_1)`, which a short statement leaves out as it
#: leaves out the implicit ones; and a universe annotation, `.{v, u}`.
TYPE_ARGUMENT = re.compile(r"\([^()\[\]{}:]+ : (?:Type|Sort)(?:\*|\s+[^\s()]+|\s*\([^()]*\))?\)")
UNIVERSES = re.compile(r"\.\{[\w\s,+()]*\}")


def brief(name: str, sig: dict | None, cap: int = BRIEF_CAP) -> str:
    """What a declaration states, short enough for a list: its signature (the S2 facet) on one line,
    without its name, its implicit arguments, the arguments that only introduce a type and universe
    annotations, each name in it by its last component. When that is too long, its instance arguments
    go first, then its other arguments ("… " says so), then the end of the line."""
    if not sig or not sig.get("text"):
        return ""
    text = sig["text"]
    # A name printed in full, its universes too (`Foo.Bar.{u}`), by its last component.
    short = {start: (stop, const.rsplit(".", 1)[1]) for start, stop, const in sig.get("refs") or []
             if "." in const and text.startswith(const, start) and text[start + len(const):stop][:2] in ("", ".{")}

    def piece(a: int, b: int) -> str:
        out, i = [], a
        for start in sorted(s for s in short if a <= s and short[s][0] <= b):
            if start >= i:
                out.append(text[i:start] + short[start][1])
                i = short[start][0]
        return UNIVERSES.sub("", " ".join(("".join(out) + text[i:b]).split()))

    n, i = len(text), len(name) if text.startswith(name) else max(text.find(" "), 0)
    if text.startswith(".{", i):  # universe parameters
        i = text.find("}", i) + 1
    groups = []  # the arguments: (opening bracket, start, stop)
    while i < n:
        if text[i].isspace():
            i += 1
            continue
        if text[i] not in BRACKETS:
            break
        depth, j = 0, i
        while j < n:
            depth += 1 if text[j] in BRACKETS else -1 if text[j] in CLOSING else 0
            if depth == 0:
                break
            j += 1
        if j == n:  # unbalanced: the rest is the statement
            break
        groups.append((text[i], i, j + 1))
        i = j + 1
    stated = piece(i + 1 if text.startswith(":", i) else i, n)
    kept = [(c, p) for c, p in ((c, piece(a, b)) for c, a, b in groups if c in "([") if not TYPE_ARGUMENT.fullmatch(p)]
    for keep in ("([", "(", ""):
        chosen = [p for c, p in kept if c in keep]
        line = ("… " if len(chosen) < len(kept) else "") + (" ".join(chosen) + " : " + stated if chosen else stated)
        if len(line) <= cap:
            return line
    return line[:cap - 1].rstrip() + "…"


@dataclass
class Inputs:
    ds: Dataset
    ev: Evidence
    store: Store
    #: the imported stores as read: {repo, path, ref, name, commit, records}
    imports: list
    sources: Sources
    settings: dict
    commit_date: str = ""


def load(dataset: Path, store: Path, imports: Path | None, source: Path | None, settings: dict) -> Inputs:
    """The dataset, the store and the stores it imports (fetched into ``imports`` by
    `evidence-store fetch-imports`), resolved by evidence-core."""
    ds = Dataset.load(dataset)
    st = Store.load(store)
    if imports is not None and st.imports:
        imp = with_imports(st, imports)
        records, sources, read = imp.records, imp.sources, imp.read
    else:
        records, sources, read = st.records, {}, []
    ev = Evidence.resolve(records, ds, sources=sources)
    return Inputs(ds=ds, ev=ev, store=st, imports=read, sources=Sources(source), settings=settings,
                  commit_date=commit_date(source, ds.commit))


def commit_date(source: Path | None, commit: str) -> str:
    """When the commit was made, from a checkout of the library; empty without one."""
    if source is None or not (Path(source) / ".git").exists():
        return ""
    out = subprocess.run(["git", "-C", str(source), "log", "-1", "--format=%cI", commit],
                         capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else ""


def area_of(module: str) -> str:
    """The area a module belongs to: the folder under the library's root."""
    parts = module.split(".")
    return parts[1] if len(parts) > 1 else parts[0]


def is_voyagers(r: dict) -> bool:
    return r.get("kind") == "named" and ((r.get("by") or {}).get("agent") or {}).get("tool") == "Voyager"


class Site:
    """The page data of one build."""

    def __init__(self, inp: Inputs, cap: int = CAP):
        self.inp, self.ds, self.ev, self.cap = inp, inp.ds, inp.ev, cap
        ds = self.ds
        self.g = Graphs(ds)
        self.rev = self.g.reverse()
        self.docstrings = {name: rows[0].get("text", "") for name, rows in ds.facet("docstring").items()}
        self.sorry = {name for name, rows in ds.facet("axioms").items() if rows[0].get("sorry")}
        self.named = self._named()
        self.mdocs = docs_mod.module_docs(ds)
        self.project_modules = len(ds.modules)
        self.modules = self._modules()
        self.mod_index = {m[0]: i for i, m in enumerate(self.modules)}
        self.by_module: dict[str, list[Decl]] = defaultdict(list)
        for d in ds.decls:
            if d.is_project:
                self.by_module[d.module].append(d)
        self.states = {ds.by_name[name].id: tuple(STATES.index(self.ev.decl_state(name, p)) for p in POLICIES)
                       for name in self.ev.by_decl if name in ds.by_name}

    # --- what is known of each declaration ---------------------------------------------------------

    def _named(self) -> dict[str, dict]:
        """Current declaration name → Voyager's `named` record about it (the first, not withdrawn)."""
        out = {}
        for name, rows in self.ev.by_decl.items():
            for r, _ in rows:
                if is_voyagers(r) and self.ev.state(r["id"]) != "withdrawn" and name not in out:
                    out[name] = r
        return out

    def _modules(self) -> list[list]:
        """[name, package, title, path]: the project's modules in the dataset's order, then those of the
        other declarations, by name."""
        package = self.ds.meta.get("library", {}).get("package", "")
        rows = [[m["name"], package, self.mdocs[m["name"]].title if m["name"] in self.mdocs else "", m.get("path", "")]
                for m in self.ds.modules]
        own = {r[0] for r in rows}
        others = sorted({(d.module, d.package) for d in self.ds.decls
                         if not d.is_project and d.module and d.module not in own})
        return rows + [[m, p, "", ""] for m, p in others]

    def title(self, d: Decl) -> str:
        """Voyager's name for it, else its docstring's first sentence, else nothing."""
        if d.name in self.named:
            return self.named[d.name].get("name", "")
        doc = self.docstrings.get(d.name)
        return docs_mod.first_sentence(doc) if doc else ""

    def flags(self, d: Decl) -> int:
        i = d.id
        return ((PROJECT if d.is_project else 0) | (NAMED if d.name in self.named else 0)
                | (BASIC if self.g.basic[i] else 0) | (ROUTINE if self.g.routine[i] else 0)
                | (DOCUMENTED if self.g.documented[i] else 0) | (AUX if is_auxiliary(d.name) else 0)
                | (SORRY if d.name in self.sorry else 0))

    def rank(self, ids) -> list[int]:
        """The library's own declarations first, then the others, each most important first."""
        decls, imp = self.ds.decls, self.g.importance
        return sorted(set(ids), key=lambda x: (not decls[x].is_project, -imp[x], decls[x].name))

    def capped(self, ids) -> tuple[list[int], int]:
        ranked = self.rank(ids)
        return ranked[:self.cap], len(ranked)

    def above(self, d: Decl) -> tuple[list[int], int]:
        """What it rests on in meaning: what a theorem (or instance) is about, what anything else is
        built from."""
        if not d.is_project:
            return [], 0
        i = d.id
        return self.capped(self.g.about(i) if (self.g.result[i] or d.kind == "instance") else self.g.built_from(i))

    def proof_steps(self, d: Decl) -> tuple[list[int], int, int]:
        """The results its proof, or the proofs in its value, use: (the non-routine ones, ranked and
        capped; how many those are; how many routine ones there are besides)."""
        if not d.is_project:
            return [], 0, 0
        uses = self.g.proof_uses(d.id)
        steps = [x for x in uses if not self.g.routine[x]]
        ranked = sorted(self.g.rank_steps(steps), key=lambda x: not self.ds.decls[x].is_project)
        return ranked[:self.cap], len(steps), len(uses) - len(steps)

    # --- the files ---------------------------------------------------------------------------------

    def node_row(self, d: Decl) -> list:
        m, nm = self.above(d)
        p, np_, _ = self.proof_steps(d)
        sp, sa = self.states.get(d.id, (0, 0))
        return [d.name, KIND_CODE.get(d.kind, "o"), self.flags(d), self.mod_index.get(d.module, -1), self.title(d),
                sp, sa, m, p, nm, np_, brief(d.name, self.ds.facet_row("signature", d.name))]

    def node_shards(self):
        """(k, rows): `nodes/<k>.json`, the nodes with ids k·NODE_SHARD onwards."""
        decls = self.ds.decls
        for k in range(0, len(decls), NODE_SHARD):
            yield k // NODE_SHARD, [self.node_row(d) for d in decls[k:k + NODE_SHARD]]

    def name_shards(self) -> dict[int, list]:
        out: dict[int, list] = defaultdict(list)
        for d in self.ds.decls:
            out[fnv_shard(d.name, NAME_SHARDS)].append([d.id, d.name])
        return out

    def search(self) -> tuple[list[list], list[str]]:
        """`search.json`, every declaration of the library a reader may look for as [name, kind], and
        `titles.json`, their titles in the same order: read second, for searches by words."""
        listed = [d for d in self.ds.decls if d.is_project and not is_auxiliary(d.name)]
        return [[d.name, KIND_CODE.get(d.kind, "o")] for d in listed], [self.title(d)[:80] for d in listed]

    def module_file(self, mi: int) -> dict:
        name, _, title, path = self.modules[mi]
        md = self.mdocs.get(name)
        start = lambda d: ((self.ds.facet_row("source", d.name) or {}).get("start") or [0])[0]
        names: dict[str, int] = {}  # what its signatures link to, each once
        decls = [self.entry(d, names) for d in sorted(self.by_module.get(name, []), key=start)]
        return {"name": name, "title": title, "path": path, "doc": md.text if md else "", "names": list(names),
                "decls": decls}

    def entry(self, d: Decl, names: dict[str, int]) -> dict:
        i, name = d.id, d.name
        e: dict = {"id": i, "name": name, "k": KIND_CODE.get(d.kind, "o"), "doc": self.docstrings.get(name, "")}
        sig = self.ds.facet_row("signature", name)
        if sig:
            e["sig"] = sig.get("text", "")
            e["sigRefs"] = self.links(sig.get("refs") or [], names)
        src = self.ds.facet_row("source", name)
        if src:
            e["kw"], e["line"] = src.get("keyword", ""), [src["start"][0], src["end"][0]]
            span = self.inp.sources.span(src, doc_comment=False)
            if span:
                stmt, rest = split_statement(span[2])
                stmt = "" if sig else stmt  # the signature stands for it
                rest = rest if d.kind in VALUE_KINDS else ""
                if stmt:
                    e["stmt"] = stmt[:TEXT_CAP]
                if rest:
                    e["rest"] = rest[:TEXT_CAP]
                if len(stmt) > TEXT_CAP or len(rest) > TEXT_CAP:
                    e["cut"] = True
        for key, ids in (("builtOn", self.rev.built_on[i]), ("facts", self.rev.facts[i]),
                         ("examples", self.rev.examples[i]), ("usedIn", self.rev.used_in[i])):
            if ids:  # an empty list is left out: most declarations have most of them empty
                e[key], e["n" + key[0].upper() + key[1:]] = self.capped(ids)
        routine = self.proof_steps(d)[2]
        if routine:
            e["nRoutine"] = routine
        if name in self.ev.by_decl:
            e["records"] = views.views_on(self.ev, name)
            tests = [self.test_view(t) for t in self.ev.tests(name)]
            if tests:
                e["tests"] = tests
        return e

    def links(self, refs: list, names: dict[str, int]) -> list[list]:
        """A signature's names, each the declaration it stands for: a node, or for a field of a structure
        or class (`LT.lt`), the structure. [[start, stop, k]], positions in code points and k the name's
        place in `names`, the module's table, which it joins if new."""
        out = []
        for start, stop, const in refs:
            target = const if const in self.ds.by_name else (const.rsplit(".", 1)[0] if "." in const else "")
            if target in self.ds.by_name:
                out.append([start, stop, names.setdefault(target, len(names))])
        return out

    @staticmethod
    def test_view(t: dict) -> dict:
        r = t["record"]
        return {"test": t["test"], "text": t.get("text", ""), "result": t["result"], "mentions": t.get("mentions"),
                "by": views.by_view(r.get("by", {})), "at": r.get("at", ""), "url": rec.origin_url(r.get("origin")),
                "challenge": bool(t.get("challenge"))}

    def upstream(self) -> dict[str, dict]:
        """The declarations outside the library that some record is about (from the imported stores),
        by name: their records, and what of the library rests on them."""
        out = {}
        for name in self.ev.by_decl:
            d = self.ds.by_name.get(name)
            if d is None or d.is_project:
                continue
            e: dict = {"records": views.views_on(self.ev, name)}
            for key, ids in (("builtOn", self.rev.built_on[d.id]), ("facts", self.rev.facts[d.id]),
                             ("usedIn", self.rev.used_in[d.id])):
                if ids:
                    e[key], e["n" + key[0].upper() + key[1:]] = self.capped(ids)
            out[name] = e
        return out

    def accepts(self, name: str) -> tuple[int, int]:
        """The acceptances in force: (by people, by AI agents)."""
        people = ai = 0
        for r, s in self.ev.records_on(name, "review"):
            if r.get("verdict") == "accept" and self.ev.in_force(r, s):
                if (r.get("by") or {}).get("kind") == "agent":
                    ai += 1
                else:
                    people += 1
        return people, ai

    def named_rows(self) -> list[dict]:
        rows = []
        for name, r in self.named.items():
            d = self.ds.by_name[name]
            cov = [coverage(self.ev, name, p) for p in POLICIES]
            ref = r.get("reference") or {}
            people, ai = self.accepts(name)
            rows.append({"id": d.id, "decl": name, "name": r.get("name", ""), "what": r.get("what", ""),
                         "text": r.get("text", ""), "area": area_of(d.module), "mod": self.mod_index.get(d.module, -1),
                         "at": r.get("at", ""), "post": ref.get("url", ""),
                         "prs": [int(n) for n in re.findall(r"TauCeti#(\d+)", ref.get("text", ""))],
                         "people": people, "ai": ai, "s": list(self.states.get(d.id, (0, 0))),
                         "cov": [len(cov[0].members), len(cov[0].covered), len(cov[1].covered), len(cov[0].with_problems)],
                         "imp": round(self.g.importance[d.id], 2)})
        return sorted(rows, key=lambda x: (x["at"], x["decl"]), reverse=True)

    def activity(self) -> dict:
        ev = self.ev
        recent = [views.record_view(ev, r, s, name) for name, rows in ev.by_decl.items() for r, s in rows
                  if not is_voyagers(r)]
        recent.sort(key=lambda v: (v["at"], v["id"]), reverse=True)
        opened = lambda kind, verdict=None: [v for v in recent if v["kind"] == kind and v["state"] == "open"
                                             and (verdict is None or v.get("verdict") == verdict)]
        who, kind_of = Counter(), {}
        for v in recent:
            if v["kind"] in ("review", "test", "challenge", "comment"):
                who[v["by"]["label"]] += 1
                kind_of[v["by"]["label"]] = v["by"]["kind"]
        named = sorted(self.named)
        return {"recent": recent[:40], "problems": opened("review", "problem"), "questions": opened("review", "question"),
                "challenges": opened("challenge"),
                "reviewers": [{"label": k, "kind": kind_of[k], "n": n} for k, n in who.most_common()],
                "queue": [[d.id, w] for d, w in (queue(ev, named, POLICIES[0], limit=60) if named else [])]}

    def areas(self) -> list[list]:
        decls, named = Counter(), Counter()
        for d in self.ds.decls:
            if d.is_project:
                decls[area_of(d.module)] += 1
        for name in self.named:
            named[area_of(self.ds.by_name[name].module)] += 1
        return [[a, n, named[a]] for a, n in decls.most_common()]

    def counts(self) -> dict:
        people = ai = 0
        for name in self.ev.by_decl:
            p, a = self.accepts(name)
            people, ai = people + p, ai + a
        act = self.activity()
        return {"declarations": sum(1 for d in self.ds.decls if d.is_project), "modules": self.project_modules,
                "named": len(self.named), "accepts": {"people": people, "ai": ai},
                "problems": len(act["problems"]), "challenges": len(act["challenges"]),
                "tests": sum(len(self.ev.tests(n)) for n in self.ev.by_decl)}

    def meta(self, counts: dict) -> dict:
        s, ds = self.inp.settings, self.ds
        lib = s["library"]
        return {"site": s["site"],
                "library": {"name": lib["name"], "repo": lib["repo"], "root": lib["root"], "docs": lib["docs"],
                            "commit": ds.commit, "date": self.inp.commit_date, "toolchain": ds.toolchain},
                "dataset": {"producer": ds.producer(), "spec": ds.meta.get("spec", "")},
                "store": {"repo": s["repo"], "name": self.inp.store.name, "bulk": s["bulk_issue"]},
                "imports": [{"name": r["name"], "repo": r["repo"], "commit": r.get("commit"), "records": r["records"]}
                            for r in self.inp.imports],
                "counts": counts, "areas": self.areas(),
                "shards": {"nodes": NODE_SHARD, "names": NAME_SHARDS},
                "built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
