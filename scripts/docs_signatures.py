#!/usr/bin/env python3
"""Each declaration's statement as Tau Ceti's API docs show it, added to a dataset as the facet
`docs-signature` (schema `docs-signature/1`), which is what the site shows (2026-10-26). A docs page is
printed with its module's imports alone; the dataset is printed with the whole library loaded, which has
Mathlib's notation and delaborators for every module (`∃ a b` for `∃ a, ∃ b`, `∀ x ∈ s` for
`∀ x, x ∈ s →`, `fun₀`, `⟹`), so the same statement can read differently in the two. The docs are the
reference: their text is taken, not printed again.

  python3 scripts/docs_signatures.py --dataset DIR [--source TAUCETI_CHECKOUT] [--jobs N] [--max-unread N]

For each module of the library, its page `<docs>/<Module/Path>.html`, and on it each declaration's header
(`div.decl_header`): its name, arguments, parents (`extends`) and type, written `<name> <arguments> :\\n
<type>` as the facet `signature` writes them, the type's lines broken where the docs' printer broke them
(a docs page keeps the indentation of a line break and drops the break: a run of n spaces is a break and
n - 1 spaces), with `refs` [start, stop, constant] in code points for each name the header links (its own
name aside). A page built at an older commit whose module has changed since is left out, as is a module
the docs do not have: their declarations keep the extractor's signature, and are counted. Fields and
constructors, which the docs show inside their structure or type, keep theirs too.

Exit 0 when the facet is written; 1 when more pages than --max-unread could not be read, and then nothing
is written; 2 on bad input.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_signatures import BLOB, changed as changed_between  # noqa: E402
from common import load_settings  # noqa: E402

FACET = {"name": "docs-signature", "file": "facets/docs-signature.jsonl", "schema": "docs-signature/1",
         "description": "each declaration's header as Tau Ceti's API docs show it (`name (x : α) … :\\n  β`, from its "
                        "module's page; scripts/docs_signatures.py), with `refs` for the names it links, as in the "
                        "signature facet; what the site shows"}
#: Tags without an end tag, which never enclose text.
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
SPACES = re.compile(r"\s+")


def constant(href: str) -> str | None:
    """The constant a header's link names: in these docs `…/Module.html#Name`, in Mathlib's
    `…/find/?pattern=Name#doc`; none for the docs' page of foundational types and the like."""
    url = urllib.parse.urlsplit(href)
    for part in url.query.split("&"):
        key, _, value = part.partition("=")
        if key == "pattern" and value:
            return urllib.parse.unquote(value)
    if url.path.endswith(".html") and url.fragment and url.fragment != "doc":
        return urllib.parse.unquote(url.fragment)
    return None


class DocsPage(HTMLParser):
    """A docs page's headers, as rows of the facet by declaration name, and the commit its source links name."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: dict[str, dict] = {}
        self.commit: str | None = None
        self.decl: str | None = None
        self.stack: list[tuple[str, str | None, str | None]] | None = None  # inside a header: (tag, part, constant)
        self.chars: list[tuple[str, str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        a = dict(attrs)
        if tag == "a" and self.commit is None:
            m = BLOB.search(a.get("href") or "")
            if m:
                self.commit = m.group(1)
        cls = (a.get("class") or "").split()
        if self.stack is None:
            if tag == "div" and "decl" in cls and a.get("id"):
                self.decl = a["id"]
            elif tag == "div" and "decl_header" in cls and self.decl:
                self.stack, self.chars = [("div", None, None)], []
            return
        if tag in VOID:
            return
        part = next((p for c, p in (("decl_kind", "kind"), ("decl_name", "name"), ("decl_type", "type")) if c in cls), None)
        self.stack.append((tag, part, constant(a.get("href") or "") if tag == "a" else None))

    def handle_endtag(self, tag: str) -> None:
        if self.stack is None or tag in VOID:
            return
        while self.stack and self.stack[-1][0] != tag:  # an unclosed tag ends with its parent
            self.stack.pop()
        if self.stack:
            self.stack.pop()
        if not self.stack:
            self.rows[self.decl] = assemble(self.chars)
            self.stack, self.decl = None, None

    def handle_data(self, data: str) -> None:
        if self.stack is None:
            return
        part = next((p for _, p, _ in reversed(self.stack) if p), "args")
        const = next((c for _, _, c in reversed(self.stack) if c), None)
        self.chars.extend((ch, part, const) for ch in data)


def collapse(chars: list[tuple[str, str | None]]) -> list[tuple[str, str | None]]:
    """Each run of white space as one space, none at either end."""
    out: list[tuple[str, str | None]] = []
    for ch, const in chars:
        if ch.isspace():
            if out and out[-1][0] != " ":
                out.append((" ", const))
        else:
            out.append((ch, const))
    while out and out[-1][0] == " ":
        out.pop()
    return out


def broken(chars: list[tuple[str, str | None]]) -> list[tuple[str, str | None]]:
    """The type's text with its line breaks put back and each line indented two spaces: a run of n > 1
    spaces is a break and n - 1 spaces (a newline in the run, a break and the spaces after it)."""
    out: list[tuple[str, str | None]] = [(" ", None), (" ", None)]
    i, n = 0, len(chars)
    while i < n and chars[i][0].isspace():
        i += 1
    while i < n:
        ch, const = chars[i]
        if not ch.isspace():
            out.append((ch, const))
            i += 1
            continue
        j = i
        while j < n and chars[j][0].isspace():
            j += 1
        run = "".join(c for c, _ in chars[i:j])
        if j < n:  # white space at the end goes
            if "\n" in run or len(run) > 1:
                indent = len(run) - run.rfind("\n") - 1 if "\n" in run else len(run) - 1
                out.extend([("\n", None)] + [(" ", None)] * (indent + 2))
            else:
                out.append((" ", const))
        i = j
    return out


def assemble(chars: list[tuple[str, str, str | None]]) -> dict:
    """A header's text, as the signature facet writes it, and its refs."""
    name = "".join(ch for ch, part, _ in chars if part == "name").strip()
    args = collapse([(ch, const) for ch, part, const in chars if part == "args"])
    kind = [(ch, const) for ch, part, const in chars if part == "type"]
    out: list[tuple[str, str | None]] = [(ch, None) for ch in name]
    if args:
        out += [(" ", None)] + args
    if any(not ch.isspace() for ch, _ in kind):
        out += [("\n", None)] + broken(kind)
    text = "".join(ch for ch, _ in out)
    refs, start = [], None
    for i, (_, const) in enumerate(out + [(None, None)]):
        if start is not None and const != out[start][1]:
            refs.append([start, i, out[start][1]])
            start = None
        if start is None and const is not None:
            start = i
    return {"text": text, "refs": refs}


def parse(html: str) -> DocsPage:
    p = DocsPage()
    p.feed(html)
    p.close()
    return p


def fetch_page(docs: str, module: str, tries: int = 4) -> str | None:
    """A module's docs page, or None when the docs have no such page."""
    url = f"{docs}/{module.replace('.', '/')}.html"
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                return r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if i == tries - 1:
                raise
        except OSError:
            if i == tries - 1:
                raise
        time.sleep(2 ** i)
    raise AssertionError("unreachable")


def jsonl(path: Path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def run(dataset: Path, settings: dict, source: Path | None = None, fetch=fetch_page, changed=None,
        jobs: int = 16, max_unread: int = 20) -> dict:
    """Write the facet into ``dataset`` from the docs' pages of its library's modules; what was read,
    left out and missed. ``changed(old, new)`` is the paths that differ between two commits of the library,
    None when that cannot be told."""
    meta = json.loads((dataset / "meta.json").read_text(encoding="utf-8"))
    commit, docs = meta["library"]["commit"], settings["library"]["docs"].rstrip("/")
    if changed is None:
        changed = lambda old, new: changed_between(source, settings["library"]["repo"], old, new)  # noqa: E731
    names: dict[str, set[str]] = {}
    for d in jsonl(dataset / "decls.jsonl"):
        if d.get("scope") == "project":
            names.setdefault(d["module"], set()).add(d["name"])
    pages: dict[str, DocsPage] = {}
    missing, unread = [], []

    def read(module: str) -> DocsPage | None:
        html = fetch(docs, module)
        return None if html is None else parse(html)

    with cf.ThreadPoolExecutor(jobs) as pool:
        futures = {pool.submit(read, m): m for m in sorted(names)}
        for f in cf.as_completed(futures):
            m = futures[f]
            try:
                p = f.result()
            except Exception:  # noqa: BLE001 -- a page that did not come is counted below
                unread.append(m)
                continue
            if p is None:
                missing.append(m)
            else:
                pages[m] = p
    moved: dict[str, set[str] | None] = {}
    stale, rows = [], []
    for m, p in sorted(pages.items()):
        if p.commit != commit:
            if p.commit not in moved:
                moved[p.commit] = changed(p.commit, commit) if p.commit else None
            diff = moved[p.commit]
            if diff is None or m.replace(".", "/") + ".lean" in diff:
                stale.append(m)
                continue
        rows += [{"decl": n, **p.rows[n]} for n in sorted(names[m] & p.rows.keys())]
    out = {"written": False, "modules": len(names), "pages": len(pages), "rows": len(rows),
           "stale": sorted(stale), "missing": sorted(missing), "unread": sorted(unread)}
    if len(unread) > max_unread:
        return out
    (dataset / "facets").mkdir(exist_ok=True)
    with (dataset / FACET["file"]).open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    meta["facets"] = [x for x in meta.get("facets", []) if x.get("name") != FACET["name"]] + [{**FACET, "count": len(rows)}]
    (dataset / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    out["written"] = True
    return out


def summary(r: dict) -> str:
    listed = lambda xs: (": " + ", ".join(xs)) if xs and len(xs) <= 20 else ""  # noqa: E731
    return (f"Statements as the docs show them: {r['rows']} declarations, from {r['pages'] - len(r['stale'])} of "
            f"{r['modules']} modules' pages; {len(r['stale'])} pages left out, their module changed since they were "
            f"built{listed(r['stale'])}; {len(r['missing'])} modules the docs do not have{listed(r['missing'])}; "
            f"{len(r['unread'])} pages that did not come{listed(r['unread'])}.")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="docs_signatures.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", required=True, type=Path)
    ap.add_argument("--source", type=Path)
    ap.add_argument("--jobs", type=int, default=16)
    ap.add_argument("--max-unread", type=int, default=20)
    a = ap.parse_args(argv)
    if not (a.dataset / "meta.json").exists():
        print(f"no dataset at {a.dataset}", file=sys.stderr)
        return 2
    r = run(a.dataset, load_settings(), a.source, jobs=a.jobs, max_unread=a.max_unread)
    print(summary(r))
    if not r["written"]:
        print(f"more than {a.max_unread} pages did not come: nothing written", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
