#!/usr/bin/env python3
"""The migration's inputs: for each declaration whose AI reviews move onto one standard review, a bundle of what is
recorded about it, which the writer reads (scripts/migrate_write.py).

  python3 scripts/migrate_inputs.py --dataset DIR --source TAUCETI [--store evidence] --roadmap ROADMAP
                                    [--roadmap-rev REV] [--ranges RANGES.jsonl] --out BUNDLES.jsonl [--only NAME,…]
  python3 scripts/migrate_inputs.py --dataset DIR --source TAUCETI [--store evidence] [--only NAME,…]
                                    --names-for-ranges NAMES.txt

TAUCETI is a checkout of the library at the dataset's commit (the site's), with `lake exe cache get` done where
declarations outside the library are in scope; ROADMAP a clone of TauCetiRoadmap. The settings are the site's
(`--settings`, data/settings.json by default).

**Scope.** Every declaration the site asks about (the library's own, and Mathlib's) that an AI agent said yes to, in
whatever form, in a review not withdrawn, and that has no standard review yet: no version of it that was not
withdrawn (scripts/standard.py). A person's answers on such a declaration are more of its inputs. **Order:** Voyager's
named results first, the newest announcement first; then the library's other declarations by roadmap (the facet
`roadmap`: its name, then the declaration's), then those of no roadmap, by name; then those outside the library, by
name. `--only` keeps the names it is given, in that order, and refuses any out of scope, saying why, writing nothing.

**A bundle** is a line of JSON, its fields in this order:
- `decl`, `kind`, `package`; `commit`, the dataset's;
- `signature`, as the API docs head the declaration, else as Lean prints it (the site's);
- `docstring`;
- `source`, its statement as written, without its doc comment; `value`, what follows it, for a definition, structure,
  class or inductive type, and empty for anything else. Each holds at most 4,000 characters (`TEXT_CAP`). A
  declaration that another's text makes, whose range lies within that one's, has that one's text under a comment that
  names it: the additive version `@[to_additive]` makes, an `_assoc` lemma `@[reassoc]` makes, a structure's field.
  This is the dataset's `source` facet in the library, and Lean's ranges (RANGES) outside it;
- `rests_on`: what it rests on, as its map draws it (`Site.above`), the first 12, each with its signature and the first
  sentence of its docstring (the dataset's, else Lean's). Empty outside the library, whose declarations the site does
  not follow;
- `reviews`: every review record of the declaration but those of the standard review, in time order; a withdrawn one
  is left out when another has its text (most were withdrawn to be filed again under the exact model's name), and is
  else listed once. Each has `by` (as the site labels it); `verdict`; `state`: `stands`, `withdrawn`, `superseded` (by
  its reviewer's later review), `open`, `fixed`, `intended`, `invalid` or `answered`, followed by ` (earlier version)`
  when it was made for a version of the declaration that has changed since; `text`, its text, then the reference,
  caveats and suggested fix it records; `checked`, its rubric's cells, a no's category among them as `error`; `at`;
- `tests`: those the site lists (test records not withdrawn, and challenges met), each with `test`, `text`, `result`
  at the commit (`passes`, `sorry` or `missing`) and `statement`, the test's signature;
- `checks`: each `*tag*` that a paragraph of a review cites beside a link to a line of a Lean file (`….lean#L<n>`),
  kept only when `*tag*` is in that file of TAUCETI. Each has `tag`, `path`, `line` (where the tag is now; of several,
  the one nearest the cited line) and `result`: `sorry` when the declaration below the tag's doc comment holds
  `sorry`, else `passes`, since Tau Ceti's CI builds every file;
- `named`: Voyager's name and sentence for it, or null;
- `roadmap`: the block of a roadmap of TauCetiRoadmap that names the declaration whole, in Markdown (`git grep -n -F`;
  a name of one part counts only in code or as a link's anchor, since it is a word too: `Path lifting`), from the
  nearest heading above that line to the next heading of the same or a higher level, at most 4,000
  characters (`BLOCK_CAP`; around the line when the block is longer), with `name`, its roadmap, and `path`, its file.
  A roadmap is a directory `TauCetiRoadmap/<name>/` or `Completed/<name>/` that has a `metadata.toml`. Of several
  lines, a line of the declaration's own roadmap comes first, then one of a README.md, a STATUS.md, a PROGRESS.md and
  any other file, in that order, then the first. Null when no roadmap names it. `--roadmap-rev` reads the roadmaps at a
  revision (`origin/main`, after a fetch) instead of the files of the checkout, whatever branch that is on;
- `open_no`: whether a no on it is open.

**Lean's ranges** (RANGES, written by scripts/migrate_ranges.lean from the names `--names-for-ranges` lists: the
declarations outside the library in scope, and those outside it that the others rest on) give a declaration outside
the library its docstring and the place of its text, read from TAUCETI/.lake/packages/<package>/<file>. Without them
such a declaration has its signature only, and the script says how many lack them.

Exit 0 when the bundles (or the names) are written; 1 when a name given to `--only` is out of scope; 2 on bad input,
such as a checkout of the library at another commit than the dataset's.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, SETTINGS, header, load_settings  # noqa: E402
import site_data  # noqa: E402
import standard  # noqa: E402

from evidence_core import docs as docs_mod  # noqa: E402
from evidence_core import rubric as rb  # noqa: E402
from evidence_core import status as st  # noqa: E402
from evidence_core import views  # noqa: E402
from evidence_core.dataset import Decl  # noqa: E402
from evidence_core.source import Sources, split_statement  # noqa: E402

STORE = ROOT / "evidence"
#: How many of the declarations it rests on a bundle lists.
RESTS_ON = 12
#: The most characters of a statement or a value; of a roadmap block; of the signature of what it rests on.
TEXT_CAP = site_data.TEXT_CAP
BLOCK_CAP = 4000
SIGNATURE_CAP = 500
#: The parts of the order (`part`).
PARTS = ("named", "by roadmap", "of no roadmap", "outside the library")
#: The fields of a bundle, in their order.
FIELDS = ("decl", "kind", "package", "commit", "signature", "docstring", "source", "value", "rests_on", "reviews",
          "tests", "checks", "named", "roadmap", "open_no")
#: An example Check's tag, as reviews cite it: a name in single asterisks (`*test_two*`), which bold is not.
TAG = re.compile(r"(?<![\w*])\*([A-Za-z_][\w.']*)\*(?![\w*])")
#: A link to a line of a Lean file: on GitHub (`…/blob/<ref>/<path>.lean#L42`), or relative, in Markdown.
LEAN_LINK = re.compile(r"https?://github\.com/[^/\s]+/[^/\s]+/blob/[^/\s]+/([^\s#()\[\]]+\.lean)#L(\d+)"
                       r"|\]\(([^\s#():]+\.lean)#L(\d+)")
#: A roadmap: a directory of TauCetiRoadmap with a `metadata.toml`.
ROADMAP_DIR = re.compile(r"^((?:TauCetiRoadmap|Completed)/[^/]+)/metadata\.toml$")
#: Which file of a roadmap a block comes from first: its README (its plan), then its status and its progress log.
FILE_RANK = {"README.md": 0, "STATUS.md": 1, "PROGRESS.md": 2}
HEADING = re.compile(r"^(#{1,6})(?:\s|$)")
FENCE = re.compile(r"^\s*(```|~~~)")
#: Nothing but attributes, `@[simp] @[ext]`, or nothing at all.
ATTRIBUTES = re.compile(r"\s*(?:@\[[^\]]*\]\s*)*")


def capped(text: str, cap: int) -> str:
    """The text, cut at `cap` characters with "…" where it is cut."""
    return text if len(text) <= cap else text[:cap - 2].rstrip() + "\n…"


def better(name: str, a: tuple[str, dict], b: tuple[str, dict]) -> bool:
    """Whether declaration `a`, (its name, its range), is a better host for `name` than `b`: it starts earlier, or ends
    later, so that a structure comes before the projection to a parent that is no field, which spans its text but its
    doc comment; else it is the namespace `name` is in; else its name is shorter. As scripts/migrate_ranges.lean
    chooses one."""
    (na, ra), (nb, rb_) = a, b
    if ra["start"] != rb_["start"]:
        return ra["start"] < rb_["start"]
    if ra["end"] != rb_["end"]:
        return ra["end"] > rb_["end"]
    pa, pb = name.startswith(na + "."), name.startswith(nb + ".")
    return pa if pa != pb else len(na) < len(nb)


def holds(a: dict, b: dict) -> bool:
    """Whether range `a` holds range `b`, and more."""
    return a["start"] <= b["start"] and b["end"] <= a["end"] and (a["start"], a["end"]) != (b["start"], b["end"])


def headings(lines: list[str]) -> list[tuple[int, int]]:
    """The Markdown headings of a file, outside its code blocks: (index of the line, level)."""
    out, fence = [], None
    for k, line in enumerate(lines):
        m = FENCE.match(line)
        if m:
            fence = m[1] if fence is None else (None if m[1] == fence else fence)
        elif fence is None and (h := HEADING.match(line)):
            out.append((k, len(h[1])))
    return out


def around(line: str, name: str, room: int) -> str:
    """A line too long for a block, cut to the `room` characters around the first place it names `name`."""
    at = max(line.find(name), 0)
    a = max(0, min(at - (room - len(name)) // 2, len(line) - room))
    return ("…" if a > 0 else "") + line[a:a + room] + ("…" if a + room < len(line) else "")


def block(lines: list[str], k: int, name: str, cap: int = BLOCK_CAP) -> str:
    """The block of a Markdown file that holds line `k` (from 1), which names `name`: from the nearest heading above it
    to the next heading of the same or a higher level, at most `cap` characters. A longer block keeps its heading and
    the lines around line `k`, as many as fit, with a line "…" where lines are left out; a line too long alone is cut
    around the name."""
    i, heads = k - 1, headings(lines)
    above = [(j, level) for j, level in heads if j <= i]
    start, level = above[-1] if above else (0, 7)
    end = next((j for j, lv in heads if j > start and lv <= level), len(lines))
    chunk = lines[start:end]
    while chunk and not chunk[-1].strip():
        chunk.pop()
    if len("\n".join(chunk)) <= cap:
        return "\n".join(chunk)
    h = i - start
    keep = [chunk[0]] if above and h > 0 else []  # the heading, which a window below it may not reach
    room = cap - sum(len(x) + 1 for x in keep) - 4  # and a line "…" on either side of the window
    if len(chunk[h]) > room:
        return "\n".join(keep + (["…"] if h > len(keep) else []) + [around(chunk[h], name, room - 2)]
                         + (["…"] if h + 1 < len(chunk) else []))
    lo, hi, size, floor = h, h + 1, len(chunk[h]), len(keep)
    while True:  # below the line first, then above it, a line at a time
        grew = False
        if hi < len(chunk) and size + len(chunk[hi]) + 1 <= room:
            size, hi, grew = size + len(chunk[hi]) + 1, hi + 1, True
        if lo > floor and size + len(chunk[lo - 1]) + 1 <= room:
            size, lo, grew = size + len(chunk[lo - 1]) + 1, lo - 1, True
        if not grew:
            break
    return "\n".join(keep + (["…"] if lo > floor else []) + chunk[lo:hi] + (["…"] if hi < len(chunk) else []))


def names_whole(line: str, name: str) -> bool:
    """Whether a line of a roadmap names `name` whole: not inside a longer name (`Foo.bar_two`, `Foo.bar.baz`), nor as a
    part of a path (`…/NumberField/README.md`). A name of one part is a word too (`Path lifting`), so it counts only in
    code (between backticks) or as the anchor of a link (`…#Path`)."""
    found = [m.start() for m in re.finditer(rf"(?<![\w'!?./]){re.escape(name)}(?![\w'!?/]|\.\w)", line)]
    if "." in name or not found:
        return bool(found)
    code = [m.span() for m in re.finditer(r"`[^`]*`", line)]
    return any(line[at - 1:at] == "#" or any(a < at < b for a, b in code) for at in found)


class Roadmap:
    """TauCetiRoadmap, a clone of it at `root`: the files of its checkout, or of revision `rev` when one is given."""

    def __init__(self, root: Path, rev: str | None = None):
        self.root, self.rev = Path(root), rev
        listing = self.git("ls-tree", "-r", "-z", "--name-only", rev) if rev else self.git("ls-files", "-z")
        self.dirs = {m[1]: m[1].split("/", 1)[1] for path in listing.split("\0") if (m := ROADMAP_DIR.match(path))}
        self.files: dict[str, list[str]] = {}

    def git(self, *args: str, ok: tuple[int, ...] = (0,)) -> str:
        p = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, encoding="utf-8",
                           errors="replace")
        if p.returncode not in ok:
            raise RuntimeError(f"git {' '.join(args[:2])} in {self.root}: {p.stderr.strip()}")
        return p.stdout

    def lines(self, path: str) -> list[str]:
        if path not in self.files:
            text = self.git("show", f"{self.rev}:{path}") if self.rev else \
                (self.root / path).read_text(encoding="utf-8", errors="replace")
            self.files[path] = text.split("\n")
        return self.files[path]

    def hits(self, name: str) -> list[tuple[str, int, str]]:
        """The lines of the roadmaps' Markdown files that name `name` whole, in the order of their paths: (path, line,
        roadmap)."""
        out = []
        found = self.git("grep", "-n", "-I", "--null", "-F", "-e", name, *([self.rev] if self.rev else []),
                         "--", "*.md", ok=(0, 1))
        for row in found.split("\n"):
            parts = row.split("\0")
            if len(parts) != 3:
                continue
            path, k, text = parts
            if self.rev and path.startswith(self.rev + ":"):
                path = path[len(self.rev) + 1:]
            roadmap = self.dirs.get("/".join(path.split("/")[:2])) if path.count("/") >= 2 else None
            if roadmap and names_whole(text, name):
                out.append((path, int(k), roadmap))
        return out

    def block_of(self, name: str, own: str | None) -> dict | None:
        """The roadmap block that names `name`, whose own roadmap (the facet's) is `own`: {name, path, block}."""
        hits = self.hits(name)
        if not hits:
            return None
        rank = lambda h: (h[2] != own, FILE_RANK.get(PurePosixPath(h[0]).name, 3), h[0], h[1])
        path, k, roadmap = min(hits, key=rank)
        return {"name": roadmap, "path": path, "block": block(self.lines(path), k, name)}


def cited(text: str) -> list[tuple[str, str, int]]:
    """The Checks a review's text may cite, as (tag, path, line): each `*tag*` with each link to a line of a Lean file
    in its paragraph, in the order of the tags."""
    out = []
    for para in re.split(r"\n\s*\n", text):
        links = [(unquote(m[1] or m[3]), int(m[2] or m[4])) for m in LEAN_LINK.finditer(para)]
        out += [(t[1], path, line) for t in TAG.finditer(para) for path, line in links]
    return out


def result_below(lines: list[str], k: int, tag: str) -> str:
    """What became of the declaration that `*tag*`, on line `k` (from 1), heads: `sorry` when it holds `sorry`, else
    `passes`. The declaration starts below the comment that holds the tag: the end of a doc or block comment (within 50
    lines), or the tag's line. It runs past its attributes to the next line at the margin; comments are left out."""
    i = k - 1
    at = lines[i].find(f"*{tag}*")
    before = "\n".join(lines[max(0, i - 50):i] + [lines[i][:at]])
    rest, tail = lines[i + 1:], False
    if before.rfind("/-") > before.rfind("-/"):  # in a block comment: it ends at the first `-/` after the tag
        for j in range(i, min(len(lines), i + 50)):
            line = lines[j][at:] if j == i else lines[j]
            if "-/" in line:
                rest, tail = [line.split("-/", 1)[1]] + lines[j + 1:], True
                break
    body, began = [], False
    for n, line in enumerate(rest):
        if n == 0 and tail:  # what follows the comment's end on its line: the declaration starts there if it is more
            began = not ATTRIBUTES.fullmatch(line)  # than attributes
        elif line[:1] and not line[0].isspace():
            if began:
                break
            began = not line.startswith("@[")
        body.append(line)
    code = re.sub(r"/-.*?-/", " ", "\n".join(body), flags=re.S)
    code = re.sub(r"--[^\n]*", " ", code)
    return "sorry" if re.search(r"\bsorry\b", code) else "passes"


def found(lines: list[str], tag: str, near: int) -> tuple[int, str] | None:
    """Where `*tag*` is in a file, (line, result), the place nearest line `near` when it is in several; None when it is
    not there."""
    marks = [k for k, line in enumerate(lines, 1) if f"*{tag}*" in line]
    if not marks:
        return None
    k = min(marks, key=lambda m: (abs(m - near), m))
    return k, result_below(lines, k, tag)


def said(r: dict) -> str:
    """What a review says: its text, then the reference, caveats and suggested fix it records, each on a line."""
    parts = [r.get("text") or ""]
    ref = r.get("reference")
    if isinstance(ref, dict) and (ref.get("text") or ref.get("url")):
        parts.append("Reference: " + " ".join(x for x in (ref.get("text"), f"({ref['url']})" if ref.get("url") else "")
                                              if x))
    caveats = [f"{c.get('category')}: {c.get('text', '')}" if isinstance(c, dict) else str(c)
               for c in r.get("caveats") or []]
    if caveats:
        parts.append("Caveats: " + "; ".join(caveats))
    if r.get("fix"):
        parts.append(f"Suggested fix: {r['fix']}")
    return "\n\n".join(p for p in parts if p.strip())


def why_not(site: site_data.Site, name: str) -> str | None:
    """Why a declaration is out of the migration's scope; None when it is in it."""
    d = site.ds.by_name.get(name)
    if d is None:
        return "not a declaration of the dataset"
    if not site.answerable(d):
        return "the site does not ask about it"
    ev = site.ev
    if not any(standard.ai_accept(r) and ev.state(r["id"]) != "withdrawn" for r, _ in ev.records_on(name, "review")):
        return "no AI agent said yes to it, in a review not withdrawn"
    if standard.current_version(site.seen(name)) is not None:
        return "it has a standard review"
    return None


def part(site: site_data.Site, name: str) -> int:
    """The part of the order a declaration of the scope is in, as an index of `PARTS`. A named result is named wherever
    it is now: one taken into Mathlib since, which its records followed, is still one."""
    if name in site.named:
        return 0
    if not site.ds.by_name[name].is_project:
        return 3
    return 1 if name in site.roadmaps else 2


def scope(site: site_data.Site) -> list[str]:
    """The declarations of the migration, in its order: Voyager's named results, the newest announcement first; the
    library's others by roadmap and name, then those of no roadmap; then those outside the library."""
    names = [n for n in site.ev.by_decl if why_not(site, n) is None]
    named = sorted((n for n in names if part(site, n) == 0), key=lambda n: (site.named[n].get("at", ""), n),
                   reverse=True)
    return named + sorted((n for n in names if part(site, n) > 0),
                          key=lambda n: (part(site, n), site.roadmaps.get(n, ""), n))


def wanted_ranges(site: site_data.Site, names: list[str]) -> list[str]:
    """The names Lean's ranges are wanted for: the declarations outside the library among `names`, and those outside it
    that the others rest on."""
    out = set()
    for n in names:
        d = site.ds.by_name[n]
        if d.is_project:
            out.update(site.ds.decls[x].name for x in site.above(d)[0][:RESTS_ON] if not site.ds.decls[x].is_project)
        else:
            out.add(n)
    return sorted(out)


def read_ranges(path: Path) -> dict[str, dict]:
    """Lean's ranges, by name: the lines scripts/migrate_ranges.lean printed, but those it could not give."""
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if not row.get("error") and row.get("name"):
                out[row["name"]] = row
    return out


class Bundler:
    """The bundles of a site build (`site`), with the checkout of the library at its commit (`source`), TauCetiRoadmap
    (`roadmap`, or None) and Lean's ranges of declarations outside the library (`ranges`, by name)."""

    def __init__(self, site: site_data.Site, source: Path, roadmap: Roadmap | None, ranges: dict[str, dict]):
        self.site, self.ds, self.ev = site, site.ds, site.ev
        self.source = Path(source)
        self.sources = Sources(self.source)
        self.roadmap, self.ranges = roadmap, ranges
        self.packages: dict[str, Sources] = {}
        self.axes = set(rb.STANDARD.names)
        self._by_path: dict[str, list[tuple[str, dict]]] | None = None

    def bundle(self, name: str) -> dict:
        d = self.ds.by_name[name]
        source, value, doc = self.text(d)
        reviews = self.reviews(name)
        named = self.site.named.get(name)
        out = {"decl": name, "kind": d.kind, "package": d.package, "commit": self.ds.commit,
               "signature": self.signature(name), "docstring": doc, "source": source, "value": value,
               "rests_on": self.rests_on(d), "reviews": reviews, "tests": self.tests(name),
               "checks": self.checks(reviews),
               "named": {"name": named.get("name", ""), "text": named.get("text", "")} if named else None,
               "roadmap": self.roadmap.block_of(name, self.site.roadmaps.get(name)) if self.roadmap else None,
               "open_no": bool(self.ev.open_problems(name))}
        assert tuple(out) == FIELDS
        return out

    # --- the declaration ---------------------------------------------------------------------------

    def signature(self, name: str) -> str:
        """Its signature as the site shows it: the API docs' header, else Lean's, a structure's parents put in."""
        docs = self.ds.facet_row("docs-signature", name)
        if docs:
            return docs.get("text", "")
        sig = self.ds.facet_row("signature", name)
        return header(sig)[0] if sig else ""

    def text(self, d: Decl) -> tuple[str, str, str]:
        """Its statement and value as written, and its docstring: in the library from the dataset and the checkout,
        outside it from Lean's ranges and the package's files. A declaration another's text makes has that text, under a
        comment that names that one."""
        if d.is_project:
            row, doc = self.ds.facet_row("source", d.name), self.site.docstrings.get(d.name, "")
            host, row = self.host(d.name, row) if row else (None, row)
            files = self.sources
        else:
            got = self.ranges.get(d.name) or {}
            doc = self.site.docstrings.get(d.name) or got.get("doc") or ""
            placed = got.get("file") and got.get("start") and got.get("end")
            row = {"path": got["file"], "start": got["start"], "end": got["end"]} if placed else None
            host = got.get("host")
            files = self.package(d.package)
        span = files.span(row, doc_comment=False) if row else None
        if not span:
            return "", "", doc
        stmt, rest = split_statement(span[2])
        stmt = (f"-- Written as part of `{host}`.\n" if host else "") + capped(stmt, TEXT_CAP)
        return stmt, capped(rest, TEXT_CAP) if d.kind in site_data.VALUE_KINDS else "", doc

    def package(self, package: str) -> Sources:
        """The files of a package outside the library, as lake fetched them into the checkout."""
        if package not in self.packages:
            root = self.source / ".lake" / "packages" / package
            self.packages[package] = Sources(root if root.is_dir() else None)
        return self.packages[package]

    def host(self, name: str, row: dict) -> tuple[str | None, dict]:
        """The declaration of the library whose text makes `name`, when its range (`row`, of the facet `source`) lies
        within that one's, and the range to read: (the outermost of them in its file (`better`), its row), else (None,
        `row`)."""
        if self._by_path is None:
            self._by_path = {}
            for n, rows in self.ds.facet("source").items():
                self._by_path.setdefault(rows[0]["path"], []).append((n, rows[0]))
        best = None
        for other in self._by_path.get(row["path"], []):
            if other[0] != name and holds(other[1], row) and (best is None or better(name, other, best)):
                best = other
        return best if best else (None, row)

    def rests_on(self, d: Decl) -> list[dict]:
        out = []
        for x in self.site.above(d)[0][:RESTS_ON]:
            n = self.ds.decls[x].name
            doc = self.site.docstrings.get(n) or (self.ranges.get(n) or {}).get("doc") or ""
            out.append({"name": n, "signature": capped(self.signature(n), SIGNATURE_CAP),
                        "doc": docs_mod.first_sentence(doc) if doc else ""})
        return out

    # --- what is recorded about it -----------------------------------------------------------------

    def reviews(self, name: str) -> list[dict]:
        """Its reviews but those of the standard review, in time order. A review withdrawn is left out when another
        has its text, as most were withdrawn to be filed again under the exact model's name: else it is listed once
        (the last of those with its text), as withdrawn."""
        rows = [(r, s) for r, s in self.ev.records_on(name, "review") if not standard.kind_of(r)]
        gone = lambda r: self.ev.state(r["id"]) == "withdrawn"
        said_by = {said(r) for r, _ in rows if not gone(r)}
        last = {said(r): r["id"] for r, _ in rows if gone(r)}
        out = []
        for r, s in rows:
            if gone(r) and (said(r) in said_by or last[said(r)] != r["id"]):
                continue
            state = "withdrawn" if gone(r) else "superseded" if r["id"] in self.ev.superseded_by \
                else self.ev.state(r["id"])
            if s.state in (st.STALE, st.STALE_UNDERNEATH):
                state += " (earlier version)"
            checked = dict(r.get("checked") or {})
            if r.get("verdict") == "problem" and r.get("category") in self.axes:
                checked[r["category"]] = "error"
            out.append({"by": views.by_view(r.get("by") or {})["label"], "verdict": r.get("verdict", ""),
                        "state": state, "text": said(r), "checked": checked, "at": r.get("at", "")})
        return out

    def tests(self, name: str) -> list[dict]:
        out, seen = [], set()
        for t in self.ev.tests(name):
            if (t["test"], t.get("text", "")) not in seen:
                seen.add((t["test"], t.get("text", "")))
                out.append({"test": t["test"], "text": t.get("text", ""), "result": t["result"],
                            "statement": self.signature(t["test"]) if t["test"] in self.ds.by_name else ""})
        return out

    def checks(self, reviews: list[dict]) -> list[dict]:
        """The Checks the reviews cite that are where they say, at the commit (`cited`, `found`)."""
        out, seen = [], set()
        for review in reviews:
            for tag, path, near in cited(review["text"]):
                if (tag, path) in seen:
                    continue
                seen.add((tag, path))
                parts = PurePosixPath(path).parts
                lines = self.sources.lines(path) if parts and ".." not in parts and not path.startswith("/") else None
                where = found(lines, tag, near) if lines else None
                if where:
                    out.append({"tag": tag, "path": path, "line": where[0], "result": where[1]})
        return out


def checkout_commit(source: Path) -> str | None:
    """The commit a checkout of the library is at; None for a directory that is no checkout."""
    if not (source / ".git").exists():
        return None
    p = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else None


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="migrate_inputs.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset", required=True, type=Path, help="the dataset of the site's commit")
    p.add_argument("--source", required=True, type=Path, help="a checkout of the library at that commit")
    p.add_argument("--store", type=Path, default=STORE, help="the evidence store (default: evidence/)")
    p.add_argument("--roadmap", type=Path, help="a clone of TauCetiRoadmap")
    p.add_argument("--roadmap-rev", help="read the roadmaps at this revision (origin/main, after a fetch)")
    p.add_argument("--ranges", type=Path,
                   help="Lean's ranges of declarations outside the library (scripts/migrate_ranges.lean)")
    p.add_argument("--out", type=Path, help="the bundles to write, one JSON object a line")
    p.add_argument("--only", help="only these declarations, comma-separated")
    p.add_argument("--names-for-ranges", type=Path, help="write the names Lean's ranges are wanted for, and stop")
    p.add_argument("--settings", type=Path, default=SETTINGS, help="the site's settings (default: data/settings.json)")
    a = p.parse_args(argv)
    if a.names_for_ranges is None and (a.out is None or a.roadmap is None):
        print("error: --out and --roadmap are needed to write bundles", file=sys.stderr)
        return 2
    if not (a.dataset / "meta.json").exists() or not a.source.is_dir():
        print(f"error: no dataset at {a.dataset}, or no checkout at {a.source}", file=sys.stderr)
        return 2
    commit = json.loads((a.dataset / "meta.json").read_text(encoding="utf-8")).get("library", {}).get("commit", "")
    at = checkout_commit(a.source)
    if at is not None and at != commit:
        print(f"error: the checkout {a.source} is at {at[:12]}, not at the dataset's commit {commit[:12]}",
              file=sys.stderr)
        return 2
    site = site_data.Site(site_data.load(a.dataset, a.store, None, a.source, load_settings(a.settings)))
    names = scope(site)
    if a.only:
        given = [n.strip() for n in a.only.split(",") if n.strip()]
        refused = [(n, why) for n in given if (why := why_not(site, n))]
        if refused:
            print(f"error: {len(refused)} of the names given are out of scope; nothing is written:", file=sys.stderr)
            for n, why in refused:
                print(f"  {n}: {why}", file=sys.stderr)
            return 1
        chosen = set(given)
        names = [n for n in names if n in chosen]
    if a.names_for_ranges is not None:
        wanted = wanted_ranges(site, names)
        a.names_for_ranges.write_text("".join(n + "\n" for n in wanted), encoding="utf-8")
        print(f"wrote {len(wanted)} names to {a.names_for_ranges}")
        return 0
    ranges = read_ranges(a.ranges) if a.ranges else {}
    try:
        roadmap = Roadmap(a.roadmap, a.roadmap_rev)
    except RuntimeError as e:
        print(f"error: TauCetiRoadmap cannot be read: {e}", file=sys.stderr)
        return 2
    bundler = Bundler(site, a.source, roadmap, ranges)
    bundles = [bundler.bundle(n) for n in names]
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text("".join(json.dumps(b, ensure_ascii=False) + "\n" for b in bundles), encoding="utf-8")
    parts = [sum(1 for n in names if part(site, n) == k) for k in range(len(PARTS))]
    print(f"wrote {len(bundles)} bundles to {a.out}: " + ", ".join(f"{k} {p}" for k, p in zip(parts, PARTS)))
    unranged = [n for n in names if not site.ds.by_name[n].is_project and n not in ranges]
    if unranged:
        print(f"warning: {len(unranged)} declarations outside the library have no range, so no source or docstring: "
              + ", ".join(unranged[:10]) + (" …" if len(unranged) > 10 else ""), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
