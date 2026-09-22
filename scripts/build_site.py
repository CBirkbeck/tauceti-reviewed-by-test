#!/usr/bin/env python3
"""Build the search page of Tau Ceti declarations and their review marks.

  python3 scripts/build_site.py

Reads data/declarations.json (every declaration of Tau Ceti at the pinned
commit, written by fetch_declarations.py), reviews/records.jsonl (the marks),
reviews/problems.jsonl (the problem reports) and data/settings.json, and writes
site/:

- index.html, the page: search every declaration by name or docstring, filter
  definitions from theorems and lemmas, by area and by review, and open one to
  read it and review it;
- data/search.json, one row per declaration (name, keyword, module, line),
  which the page loads first; data/docs.json, each declaration's docstring in
  one sentence, which it loads next;
- data/m/<n>.json, each module's declarations in full, read when one is opened;
- reviews.json, the marks and problem reports, for other readers too (the
  atlas, Tau Ceti's docs): each declaration's current version, every mark on it
  and every report of a problem with it.
"""
from __future__ import annotations

import html
import json
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reviews import load, reports  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MEANING = {"Reviewed-by": "it is the intended mathematical notion", "Tested-by": "its examples and unit tests check out"}
DEFINITIONS = {"def", "structure", "class", "inductive", "instance"}
# What reviews.json says about each problem report.
PROBLEM_KEYS = ("issue", "status", "what", "why", "fix", "by", "kind", "agent", "hash", "current", "at", "closedBy", "closedAt")


def review_link(repo: str, item: dict) -> str:
    query = urlencode({"template": "reviewed-by.yml", "title": f"Review: {item['name']}", "declaration": item["name"], "version": item["hash"]})
    return f"https://github.com/{repo}/issues/new?{query}"


def problem_link(repo: str, item: dict) -> str:
    query = urlencode({"template": "problem.yml", "title": f"Problem: {item['name']}", "declaration": item["name"], "version": item["hash"]})
    return f"https://github.com/{repo}/issues/new?{query}"


def problems_by_declaration(index: dict, events: list) -> dict:
    """Each declaration's problem reports, open ones first, then the newest first."""
    current = {item["name"]: item["hash"] for item in index["declarations"]}
    found = defaultdict(list)
    for report in reports(events).values():
        if report["decl"] in current:
            found[report["decl"]].append({**report, "current": report["hash"] == current[report["decl"]]})
    for items in found.values():
        items.sort(key=lambda p: p["at"], reverse=True)
        items.sort(key=lambda p: p["status"] != "open")
    return found


def marks_by_declaration(index: dict, records: list) -> dict:
    current = {item["name"]: item["hash"] for item in index["declarations"]}
    marks = defaultdict(list)
    for record in records:
        if record["decl"] in current and record["trailer"] in MEANING:
            marks[record["decl"]].append({**record, "current": record["hash"] == current[record["decl"]]})
    for items in marks.values():
        items.sort(key=lambda m: (not m["current"], list(MEANING).index(m["trailer"]), m["at"]))
    return marks


def summary(doc: str, limit: int = 120) -> str:
    """A docstring's first sentence, in plain text."""
    text = " ".join(doc.split())
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*|\*([^*]+)\*", lambda m: m.group(1) or m.group(2), text)
    first = re.split(r"(?<=[.!?])\s+(?=[A-Z(])", text, maxsplit=1)[0]
    return first if len(first) <= limit else first[:limit].rsplit(" ", 1)[0] + " …"


def search_index(index: dict) -> dict:
    modules = [module["module"] for module in index["modules"]]
    position = {name: n for n, name in enumerate(modules)}
    keywords = sorted({item.get("keyword", item["kind"]) for item in index["declarations"]})
    column = {keyword: n for n, keyword in enumerate(keywords)}
    rows = [[item["name"], column[item.get("keyword", item["kind"])], position[item["module"]], item.get("line", 0)]
            for item in index["declarations"]]
    return {"tauceti": index["tauceti"], "read": index["read"], "modules": modules, "keywords": keywords, "rows": rows}


def module_summary(doc: str) -> str:
    paragraphs = [p for p in re.split(r"\n\s*\n", doc.strip()) if p.strip() and not p.lstrip().startswith("#")]
    return " ".join(paragraphs[0].split()) if paragraphs else ""


def shards(index: dict) -> dict:
    """Each module's declarations in full, keyed by the module's position in the search index."""
    position = {module["module"]: n for n, module in enumerate(index["modules"])}
    out = {n: {"module": module["module"], "path": module["path"], "url": module["url"], "summary": module_summary(module["doc"]),
               "declarations": []} for n, module in enumerate(index["modules"])}
    for item in index["declarations"]:
        out[position[item["module"]]]["declarations"].append(
            {key: item.get(key) for key in ("name", "kind", "keyword", "line", "end", "doc", "source", "hash", "url")})
    return out


def data(index: dict, records: list, problems: list = ()) -> dict:
    marks = marks_by_declaration(index, records)
    found = problems_by_declaration(index, list(problems))
    by_name = {item["name"]: item for item in index["declarations"]}
    return {"schema": "reviewed-by/v1", "tauceti": index["tauceti"], "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "declarations": {name: {"hash": by_name[name]["hash"], "kind": by_name[name]["kind"], "url": by_name[name]["url"],
                                    "marks": [{**{k: m[k] for k in ("trailer", "by", "kind", "agent", "hash", "current", "at", "evidence")},
                                               "issue": m.get("source", {}).get("issue")} for m in marks.get(name, [])],
                                    "problems": [{k: p[k] for k in PROBLEM_KEYS if k in p} for p in found.get(name, [])]}
                             for name in sorted(set(marks) | set(found))}}


STYLE = """
:root { color-scheme: light dark; --bg: #f8f7f4; --surface: #ffffff; --ink: #1c2025; --muted: #59626c; --faint: #8b939b; --line: #e3e0da;
  --code: #f3f1ec; --accent: #2b6a99; --person: #2f7d4f; --agent: #6a58b8; --stale: #9aa0a6; --hit: #fff4c2; --problem: #b3261e; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg: #0e1114; --surface: #151a1f; --ink: #e5e8eb; --muted: #a5aeb6;
  --faint: #7b848d; --line: #252b32; --code: #1a1f25; --accent: #82b6de; --person: #6fcf97; --agent: #b2a4f1; --stale: #6b737b; --hit: #3a3417;
  --problem: #f2a29c; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }
a { color: var(--accent); }
code, pre, .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; }
header { max-width: 1280px; margin: 0 auto; padding: 22px 16px 6px; }
.eyebrow { text-transform: uppercase; letter-spacing: 1.4px; font-size: 11.5px; color: var(--faint); margin: 0 0 4px; }
h1 { font-size: 24px; line-height: 1.2; margin: 0 0 6px; letter-spacing: -.3px; }
.lede { color: var(--muted); margin: 0 0 4px; }
.meta { color: var(--faint); font-size: 13px; margin: 0; }
details.how { max-width: 1280px; margin: 10px auto 0; padding: 0 16px; color: var(--muted); font-size: 14px; }
details.how > summary { cursor: pointer; color: var(--accent); font-weight: 600; }
details.how ol { margin: 8px 0; padding-left: 20px; } details.how li { margin: 3px 0; }
.legend { display: grid; grid-template-columns: max-content 1fr; gap: 3px 12px; margin: 8px 0; }
.legend dt { font-weight: 600; color: var(--ink); } .legend dd { margin: 0; }
.bar { position: sticky; top: 0; z-index: 5; background: var(--bg); border-bottom: 1px solid var(--line); }
.bar-inner { max-width: 1280px; margin: 0 auto; padding: 12px 16px 10px; display: flex; flex-wrap: wrap; gap: 8px 10px; align-items: center; }
#search { flex: 1 1 360px; min-width: 0; font: inherit; font-size: 16px; padding: 9px 12px; border-radius: 8px; border: 1px solid var(--line); background: var(--surface); color: var(--ink); }
#search:focus { outline: 2px solid color-mix(in srgb, var(--accent) 45%, transparent); border-color: var(--accent); }
.chips { display: flex; gap: 6px; flex-wrap: wrap; }
.chips button, select { font: inherit; font-size: 13px; padding: 5px 11px; border-radius: 999px; border: 1px solid var(--line); background: var(--surface); color: var(--muted); cursor: pointer; }
.chips button[aria-pressed="true"] { border-color: var(--accent); color: var(--accent); background: color-mix(in srgb, var(--accent) 12%, var(--surface)); font-weight: 600; }
select { border-radius: 8px; max-width: 220px; }
.layout { max-width: 1280px; margin: 0 auto; padding: 10px 16px 60px; display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 7fr); gap: 18px; align-items: start; }
.status { color: var(--faint); font-size: 13px; margin: 4px 0 8px; }
.results { display: flex; flex-direction: column; gap: 6px; }
.result { display: block; width: 100%; text-align: left; font: inherit; color: inherit; background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 8px 11px; cursor: pointer; }
.result:hover, .result:focus-visible { border-color: var(--faint); }
.result[aria-current="true"] { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
.result .name { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13.5px; overflow-wrap: anywhere; }
.result .ns { color: var(--faint); } .result .leaf { font-weight: 600; }
.result .line2 { display: flex; gap: 8px; align-items: baseline; margin-top: 2px; font-size: 12.5px; color: var(--muted); min-width: 0; }
.result .doc1 { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.kw { flex: none; font-size: 10.5px; text-transform: uppercase; letter-spacing: .7px; color: var(--faint); border: 1px solid var(--line); border-radius: 4px; padding: 0 5px; }
.kw.def { color: var(--accent); border-color: currentColor; }
.tickmini { flex: none; font-size: 11px; font-weight: 700; color: var(--person); }
.flag { flex: none; font-size: 11px; font-weight: 700; color: var(--problem); }
.more { font: inherit; font-size: 13px; margin: 6px 0; padding: 6px 12px; border-radius: 6px; border: 1px solid var(--line); background: var(--surface); color: var(--accent); cursor: pointer; }
.panel { position: sticky; top: 70px; max-height: calc(100vh - 86px); overflow: auto; background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 16px 18px; }
.panel h2 { font-size: 16px; margin: 6px 0 4px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; overflow-wrap: anywhere; font-weight: 600; }
.panel .where { color: var(--faint); font-size: 13px; margin: 0 0 8px; overflow-wrap: anywhere; }
.panel .doc { color: var(--muted); font-size: 14.5px; } .panel .doc p { margin: 6px 0; } .panel .doc code { font-size: 12.5px; }
pre { background: var(--code); border-radius: 6px; padding: 10px 12px; overflow-x: auto; margin: 10px 0 8px; line-height: 1.45; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 10px 0 4px; }
.primary { font-size: 13.5px; font-weight: 600; text-decoration: none; padding: 5px 14px; border-radius: 6px; border: 1px solid var(--accent); background: var(--accent); color: var(--surface); }
.quiet { font: inherit; font-size: 13px; padding: 4px 10px; border-radius: 6px; border: 1px solid var(--line); background: var(--surface); color: var(--muted); cursor: pointer; text-decoration: none; }
.marks { display: flex; flex-wrap: wrap; gap: 6px 10px; margin: 8px 0; }
.mark { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: var(--ink); text-decoration: none; border: 1px solid var(--line); border-radius: 999px; padding: 2px 10px 2px 3px; }
.tick { display: inline-grid; place-items: center; width: 18px; height: 18px; border-radius: 50%; font-size: 11px; font-weight: 700; }
.mark.person .tick { background: var(--person); color: var(--surface); }
.mark.agent .tick { border: 1.5px solid var(--agent); color: var(--agent); }
.trailer { font-weight: 600; } .ai { font-size: 10.5px; font-weight: 700; letter-spacing: .6px; color: var(--agent); }
.mark.stale { color: var(--stale); } .mark.stale .tick { background: none; border: 1.5px solid var(--stale); color: var(--stale); } .mark.stale .ai { color: var(--stale); }
.note { font-size: 11.5px; font-style: italic; }
.quiet.warn { color: var(--problem); border-color: color-mix(in srgb, var(--problem) 40%, var(--line)); }
.problem { border: 1px solid color-mix(in srgb, var(--problem) 45%, var(--line)); border-radius: 8px; padding: 8px 12px; margin: 8px 0; font-size: 14px; }
.problem.closed { border-color: var(--line); color: var(--muted); }
.problem .head { margin: 0; font-size: 13px; color: var(--muted); }
.problem .state { font-weight: 700; color: var(--problem); } .problem.closed .state { color: var(--muted); }
.problem p { margin: 6px 0; } .problem .fix { font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: var(--faint); margin: 10px 0 0; }
.problem pre { white-space: pre-wrap; margin: 4px 0; }
.sub { font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: var(--faint); margin: 16px 0 6px; }
.siblings { display: flex; flex-direction: column; gap: 2px; font-size: 13px; }
.siblings button { font: inherit; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12.5px; text-align: left; background: none; border: 0; padding: 2px 0; color: var(--accent); cursor: pointer; overflow-wrap: anywhere; }
.siblings button[aria-current="true"] { color: var(--ink); font-weight: 600; }
.areas { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0 14px; }
.areas button { font: inherit; font-size: 13px; padding: 4px 10px; border-radius: 999px; border: 1px solid var(--line); background: var(--surface); color: var(--ink); cursor: pointer; }
.areas button span { color: var(--faint); margin-left: 4px; }
.empty { color: var(--muted); }
.back { display: none; }
footer { max-width: 1280px; margin: 0 auto; padding: 0 16px 40px; color: var(--faint); font-size: 13px; }
@media (max-width: 860px) {
  .layout { grid-template-columns: minmax(0, 1fr); }
  .panel { display: none; position: fixed; inset: 0; top: 0; max-height: none; border-radius: 0; z-index: 10; padding: 14px 16px 40px; }
  body.reading .panel { display: block; }
  .back { display: inline-block; }
  h1 { font-size: 21px; }
}
"""

SCRIPT = r"""
const SETTINGS = JSON.parse(document.getElementById('settings').textContent);
const $ = id => document.getElementById(id);
const DEFS = new Set(['def', 'abbrev', 'structure', 'class', 'inductive', 'instance', 'class inductive']);
const MEANING = {'Reviewed-by': 'it is the intended mathematical notion', 'Tested-by': 'its examples and unit tests check out'};
const WHAT = {wrong: 'Wrong', misleading: 'Misleading name or docstring', other: 'Something else is off'};
const CLOSED = {fixed: 'Fixed', 'not planned': 'Closed without a fix', duplicate: 'Closed as a duplicate'};
const PAGE = 60;
let index = null, lower = [], leafLower = [], area = [], docs = null, docsLower = null, marks = {}, reviewed = new Set(), flagged = new Set();
let state = {q: '', group: 'all', status: 'all', area: '', d: ''}, shown = PAGE, results = [];
const shardCache = new Map();

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
function prose(text) {
  return String(text || '').trim().split(/\n\s*\n/).filter(Boolean).map(block => '<p>' + esc(block.replace(/\s+/g, ' '))
    .replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2">$1</a>') + '</p>').join('');
}
const when = s => { const d = new Date(s); return isNaN(d) ? s : d.toLocaleDateString(undefined, {day: 'numeric', month: 'short', year: 'numeric'}); };
function reviewLink(name, hash) {
  const q = new URLSearchParams({template: 'reviewed-by.yml', title: 'Review: ' + name, declaration: name, version: hash});
  return 'https://github.com/' + SETTINGS.repo + '/issues/new?' + q.toString();
}
function problemLink(name, hash) {
  const q = new URLSearchParams({template: 'problem.yml', title: 'Problem: ' + name, declaration: name, version: hash});
  return 'https://github.com/' + SETTINGS.repo + '/issues/new?' + q.toString();
}
const issueUrl = n => 'https://github.com/' + SETTINGS.repo + '/issues/' + n;

function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  state = {q: p.get('q') || '', group: p.get('kind') || 'all', status: p.get('status') || 'all', area: p.get('area') || '', d: p.get('d') || ''};
}
function writeHash(replace) {
  const p = new URLSearchParams();
  if (state.q) p.set('q', state.q); if (state.group !== 'all') p.set('kind', state.group); if (state.status !== 'all') p.set('status', state.status);
  if (state.area) p.set('area', state.area); if (state.d) p.set('d', state.d);
  const hash = '#' + p.toString();
  if (location.hash !== hash) history[replace ? 'replaceState' : 'pushState'](null, '', hash || '#');
}

function passes(i) {
  const kw = index.keywords[index.rows[i][1]];
  if (state.group === 'def' && !DEFS.has(kw)) return false;
  if (state.group === 'thm' && DEFS.has(kw)) return false;
  if (state.area && area[i] !== state.area) return false;
  if (state.status === 'reviewed' && !reviewed.has(index.rows[i][0])) return false;
  if (state.status === 'open' && reviewed.has(index.rows[i][0])) return false;
  if (state.status === 'problem' && !flagged.has(index.rows[i][0])) return false;
  return true;
}
function search() {
  const tokens = state.q.toLowerCase().split(/\s+/).filter(Boolean), joined = tokens.join('');
  const found = [];
  for (let i = 0; i < index.rows.length; i++) {
    if (!passes(i)) continue;
    if (!tokens.length) { found.push([0, i]); continue; }
    let score = 0;
    for (const t of tokens) {
      const leaf = leafLower[i], full = lower[i];
      const s = leaf === t ? 100 : leaf.startsWith(t) ? 60 : leaf.includes(t) ? 40 : full.includes(t) ? 25 : docsLower && docsLower[i].includes(t) ? 8 : 0;
      if (!s) { score = -1; break; }
      score += s;
    }
    if (score < 0) continue;
    if (lower[i] === joined) score += 1000;
    found.push([score, i]);
  }
  if (tokens.length) found.sort((a, b) => b[0] - a[0] || lower[a[1]].length - lower[b[1]].length);
  return found.map(x => x[1]);
}

function nameHtml(name) {
  const cut = name.lastIndexOf('.');
  return cut < 0 ? '<span class="leaf">' + esc(name) + '</span>' : '<span class="ns">' + esc(name.slice(0, cut + 1)) + '</span><span class="leaf">' + esc(name.slice(cut + 1)) + '</span>';
}
function resultHtml(i) {
  const [name, k] = index.rows[i], kw = index.keywords[k];
  const doc = docs ? docs[i] : '';
  return '<button class="result" data-i="' + i + '"' + (state.d === name ? ' aria-current="true"' : '') + '><div class="name">' + nameHtml(name) + '</div>' +
    '<div class="line2"><span class="kw' + (DEFS.has(kw) ? ' def' : '') + '">' + esc(kw) + '</span>' + (flagged.has(name) ? '<span class="flag" title="A problem is reported">!</span>' : '') +
    (reviewed.has(name) ? '<span class="tickmini" title="Reviewed">✓</span>' : '') +
    '<span class="doc1">' + esc(doc || index.modules[index.rows[i][2]]) + '</span></div></button>';
}
function renderResults() {
  const box = $('results');
  const filtered = state.q || state.group !== 'all' || state.status !== 'all' || state.area;
  if (!filtered) {
    const counts = {};
    area.forEach(a => { counts[a] = (counts[a] || 0) + 1; });
    const recent = Object.entries(marks).flatMap(([name, entry]) => entry.marks.map(m => ({name, ...m}))).sort((a, b) => (b.at || '').localeCompare(a.at || '')).slice(0, 12);
    const reported = Object.entries(marks).flatMap(([name, entry]) => (entry.problems || []).filter(p => p.status === 'open').map(p => ({name, ...p})))
      .sort((a, b) => (b.at || '').localeCompare(a.at || '')).filter((p, n, all) => all.findIndex(q => q.name === p.name) === n);
    const row = m => { const i = rowOf.get(m.name); return i === undefined ? '' : resultHtml(i); };
    $('status').textContent = index.rows.length.toLocaleString() + ' declarations. Search by name or by words from their docstrings.';
    box.innerHTML = '<p class="sub">Areas</p><div class="areas">' + Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([a, n]) =>
      '<button data-area="' + esc(a) + '">' + esc(a) + '<span>' + n.toLocaleString() + '</span></button>').join('') + '</div>' +
      (reported.length ? '<p class="sub">Open problems</p><div class="results">' + reported.map(row).join('') + '</div>' : '') +
      '<p class="sub">Recently reviewed</p>' + (recent.length ? '<div class="results">' + recent.map(row).join('') + '</div>' : '<p class="empty">No marks yet.</p>');
    return;
  }
  results = search();
  const n = results.length;
  $('status').textContent = n ? n.toLocaleString() + ' match' + (n === 1 ? '' : 'es') + (state.q && !docs ? ' by name (docstrings still loading)' : '') : 'No matches.';
  box.innerHTML = '<div class="results">' + results.slice(0, shown).map(resultHtml).join('') + '</div>' + (n > shown ? '<button class="more" id="more">Show more</button>' : '');
}

async function shard(m) {
  if (!shardCache.has(m)) shardCache.set(m, fetch('data/m/' + m + '.json').then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }));
  return shardCache.get(m);
}
function markHtml(m) {
  const who = m.kind === 'agent' ? esc(m.agent) + ' <span class="ai">AI</span> via @' + esc(m.by) : '@' + esc(m.by);
  const tip = m.trailer + ': ' + (MEANING[m.trailer] || '') + '. Version ' + m.hash + ', ' + when(m.at) + '.' + (m.evidence ? ' Evidence: ' + m.evidence : '');
  const href = m.issue ? 'https://github.com/' + SETTINGS.repo + '/issues/' + m.issue : '#';
  return '<a class="mark ' + esc(m.kind) + (m.current ? '' : ' stale') + '" href="' + esc(href) + '" title="' + esc(tip) + '"><span class="tick" aria-hidden="true">✓</span>' +
    '<span class="trailer">' + esc(m.trailer) + '</span> <span class="who">' + who + '</span>' + (m.current ? '' : ' <span class="note">earlier version</span>') + '</a>';
}
function problemHtml(p) {
  const who = p.kind === 'agent' ? esc(p.agent) + ' <span class="ai">AI</span> via @' + esc(p.by) : '@' + esc(p.by);
  const open = p.status === 'open';
  return '<div class="problem' + (open ? '' : ' closed') + '"><p class="head"><span class="state">' + (open ? 'Open' : esc(CLOSED[p.status] || 'Closed')) + '</span> · ' +
    esc(WHAT[p.what] || 'Problem') + ' · reported by ' + who + ', ' + when(p.at) +
    (p.current ? '' : ' · <span class="note">about an earlier version; the declaration has changed since</span>') + '</p>' + prose(p.why) +
    (p.fix ? '<p class="fix">Suggested fix</p><pre>' + esc(p.fix) + '</pre>' : '') +
    '<p><a href="' + esc(issueUrl(p.issue)) + '">Issue #' + esc(p.issue) + '</a>' + (p.closedAt ? ' · closed by @' + esc(p.closedBy) + ', ' + when(p.closedAt) : '') + '</p></div>';
}
async function renderPanel() {
  const panel = $('panel');
  document.body.classList.toggle('reading', !!state.d);
  if (!state.d) { panel.innerHTML = '<p class="empty">Choose a declaration to read it, see its marks and review it.</p>'; return; }
  const i = rowOf.get(state.d);
  if (i === undefined) { panel.innerHTML = '<button class="quiet back" id="back">← Back</button><p class="empty">' + esc(state.d) + ' is not a declaration at this commit.</p>'; return; }
  const [name, k, m, line] = index.rows[i];
  panel.innerHTML = '<button class="quiet back" id="back">← Back</button><h2>' + esc(name) + '</h2><p class="where">' + esc(index.keywords[k]) + ' in ' + esc(index.modules[m]) + ', line ' + line + '</p><p class="empty">Loading…</p>';
  let data;
  try { data = await shard(m); } catch (e) { panel.querySelector('.empty').textContent = 'Could not load this module.'; return; }
  if (state.d !== name) return;
  const item = data.declarations.find(d => d.name === name);
  const entry = marks[name];
  const lines = item.source.split('\n'), long = lines.length > 60;
  panel.innerHTML = '<button class="quiet back" id="back">← Back</button>' +
    '<span class="kw' + (DEFS.has(item.keyword) ? ' def' : '') + '">' + esc(item.keyword) + '</span><h2>' + nameHtml(name) + '</h2>' +
    '<p class="where"><a href="' + esc(data.url) + '">' + esc(data.module) + '</a>, lines ' + item.line + '–' + item.end + ' · version <span class="mono">' + esc(item.hash) + '</span></p>' +
    (item.doc ? '<div class="doc">' + prose(item.doc) + '</div>' : '') +
    '<pre><code id="src">' + esc(long ? lines.slice(0, 60).join('\n') + '\n…' : item.source) + '</code></pre>' +
    '<div class="actions"><a class="primary" href="' + esc(reviewLink(name, item.hash)) + '">Review this</a>' +
    '<a class="quiet warn" href="' + esc(problemLink(name, item.hash)) + '">Report a problem</a>' +
    '<button class="quiet" id="copy">Copy name</button><a class="quiet" href="' + esc(item.url) + '">Source on GitHub</a>' + (long ? '<button class="quiet" id="all">Show all ' + lines.length + ' lines</button>' : '') + '</div>' +
    (entry && entry.problems && entry.problems.length ? '<p class="sub">Problems</p>' + entry.problems.map(problemHtml).join('') : '') +
    '<p class="sub">Marks</p>' + (entry && entry.marks.length ? '<div class="marks">' + entry.marks.map(markHtml).join('') + '</div>' : '<p class="empty">No marks yet.</p>') +
    '<p class="sub">In ' + esc(data.module.split('.').slice(-1)[0]) + '</p><div class="siblings">' + data.declarations.map(d =>
      '<button data-name="' + esc(d.name) + '"' + (d.name === name ? ' aria-current="true"' : '') + '>' + esc(d.name.split('.').slice(-1)[0]) + '</button>').join('') + '</div>';
  const all = $('all');
  if (all) all.addEventListener('click', () => { $('src').textContent = item.source; all.remove(); });
  $('copy').addEventListener('click', () => navigator.clipboard && navigator.clipboard.writeText(name).then(() => { $('copy').textContent = 'Copied'; }));
}
let rowOf = new Map();
function render() { renderResults(); renderPanel(); syncControls(); }
function syncControls() {
  if (document.activeElement !== $('search') && $('search').value !== state.q) $('search').value = state.q;
  document.querySelectorAll('[data-group]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.group === state.group)));
  $('state-filter').value = state.status; $('area-filter').value = state.area;
}
function update(change, replace) { state = {...state, ...change}; shown = PAGE; writeHash(replace); render(); }

document.addEventListener('click', event => {
  const result = event.target.closest('.result');
  if (result) { update({d: index.rows[+result.dataset.i][0]}); return; }
  const sibling = event.target.closest('.siblings button');
  if (sibling) { update({d: sibling.dataset.name}); return; }
  const chip = event.target.closest('[data-group]');
  if (chip) { update({group: chip.dataset.group}, true); return; }
  const areaButton = event.target.closest('[data-area]');
  if (areaButton) { update({area: areaButton.dataset.area}); return; }
  if (event.target.id === 'more') { shown += PAGE * 2; renderResults(); return; }
  if (event.target.closest('#back')) { update({d: ''}); }
});
let timer;
$('search').addEventListener('input', event => { clearTimeout(timer); timer = setTimeout(() => update({q: event.target.value.trim()}, true), 120); });
$('search').addEventListener('keydown', event => { if (event.key === 'Enter' && results.length) update({q: event.target.value.trim(), d: index.rows[results[0]][0]}); });
$('state-filter').addEventListener('change', event => update({status: event.target.value}, true));
$('area-filter').addEventListener('change', event => update({area: event.target.value}, true));
document.addEventListener('keydown', event => {
  if (event.key === '/' && document.activeElement !== $('search')) { event.preventDefault(); $('search').focus(); }
  if (event.key === 'Escape' && state.d) update({d: ''});
});
window.addEventListener('popstate', () => { readHash(); render(); });

(async () => {
  readHash();
  $('status').textContent = 'Loading ' + SETTINGS.count.toLocaleString() + ' declarations…';
  const [loaded, reviews] = await Promise.all([fetch('data/search.json').then(r => r.json()), fetch('reviews.json').then(r => r.json()).catch(() => ({declarations: {}}))]);
  index = loaded;
  marks = reviews.declarations || {};
  reviewed = new Set(Object.entries(marks).filter(([, e]) => e.marks.some(m => m.current)).map(([name]) => name));
  flagged = new Set(Object.entries(marks).filter(([, e]) => (e.problems || []).some(p => p.status === 'open')).map(([name]) => name));
  lower = index.rows.map(r => r[0].toLowerCase());
  leafLower = lower.map(n => n.slice(n.lastIndexOf('.') + 1));
  area = index.rows.map(r => (index.modules[r[2]].split('.')[1] || index.modules[r[2]]));
  rowOf = new Map(index.rows.map((r, i) => [r[0], i]));
  const areas = [...new Set(area)].sort();
  $('area-filter').innerHTML = '<option value="">Every area</option>' + areas.map(a => '<option value="' + esc(a) + '">' + esc(a) + '</option>').join('');
  window.TauReview = {state: () => ({...state}), results: () => results.map(i => index.rows[i][0]), ready: false};
  render();
  const loadedDocs = await fetch('data/docs.json').then(r => r.json()).catch(() => null);
  if (loadedDocs) { docs = loadedDocs; docsLower = docs.map(d => d.toLowerCase()); renderResults(); }
  window.TauReview.ready = true;
})();
"""


def page(index: dict, records: list, settings: dict, problems: list = ()) -> str:
    total = len(index["declarations"])
    open_problems = sum(p["status"] == "open" for items in problems_by_declaration(index, list(problems)).values() for p in items)
    config = json.dumps({"repo": settings["repo"], "bulk_issue": settings["bulk_issue"], "count": total, "tauceti": index["tauceti"]})
    config = config.replace("<", "\\u003c")
    bulk = f"https://github.com/{settings['repo']}/issues/{settings['bulk_issue']}"
    legend = "".join(f"<dt>{t}</dt><dd>{m}</dd>" for t, m in MEANING.items())
    repo = html.escape(settings["repo"])
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reviewed-by marks</title>
<meta name="description" content="Search every Tau Ceti declaration and leave review marks from the browser, without pull requests. A test.">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>✓</text></svg>">
<style>{STYLE}</style>
</head>
<body>
<header>
  <p class="eyebrow">Test · review marks</p>
  <h1>Reviewed-by for Tau Ceti</h1>
  <p class="lede">Every declaration of Tau Ceti, searchable, with who has checked which and on which version, recorded from the browser without pull requests.</p>
  <p class="meta">Tau Ceti <a href="https://github.com/TauCetiProject/TauCeti/tree/{html.escape(index['tauceti'])}">{html.escape(index['tauceti'][:7])}</a> · {total:,} declarations in {len(index['modules']):,} modules · {len(records)} mark{'s' if len(records) != 1 else ''}{f" · {open_problems} open problem{'s' if open_problems != 1 else ''}" if open_problems else ''}</p>
</header>
<details class="how">
  <summary>How to leave a mark</summary>
  <ol>
    <li>Find the declaration, open it and press <strong>Review this</strong>: a GitHub form opens with its name and version filled in. Choose a mark and submit. Saying what you checked is optional for people; AI agents must.</li>
    <li>A bot records the mark, answers on the issue and closes it. There is no pull request, and this page updates within a few minutes.</li>
    <li>If the declaration changes later, the mark stays but is greyed: it applies to the earlier version until someone reviews the new one.</li>
  </ol>
  <p>If a declaration is wrong, press <strong>Report a problem</strong> instead and say why. The report is the issue for fixing it: it stays open, and the page flags the declaration, until it is closed as fixed or as not a problem.</p>
  <p>Marking many at once: comment lines like <code>Reviewed-by: TauCeti.X.y — what you checked</code> on <a href="{html.escape(bulk)}">issue #{settings['bulk_issue']}</a>. AI agents use the same routes and name the agent, model and session; their marks are shown apart from people's.</p>
  <dl class="legend">{legend}</dl>
</details>
<div class="bar"><div class="bar-inner">
  <input id="search" type="search" placeholder="Search {total:,} declarations: a name, part of one, or words from a docstring" autocomplete="off" spellcheck="false" aria-label="Search declarations">
  <div class="chips" role="group" aria-label="Kind">
    <button data-group="all" aria-pressed="true">All</button><button data-group="def" aria-pressed="false">Definitions</button><button data-group="thm" aria-pressed="false">Theorems and lemmas</button>
  </div>
  <select id="state-filter" aria-label="Review"><option value="all">Reviewed or not</option><option value="reviewed">Reviewed</option><option value="open">Not yet reviewed</option><option value="problem">Reported problems</option></select>
  <select id="area-filter" aria-label="Area"><option value="">Every area</option></select>
</div></div>
<div class="layout">
  <section aria-label="Results"><p class="status" id="status"></p><div id="results"></div></section>
  <aside class="panel" id="panel" aria-live="polite"></aside>
</div>
<footer>
  <p>The marks as data, for the atlas or Tau Ceti's own documentation: <a href="reviews.json">reviews.json</a>. The ledger: <a href="https://github.com/{repo}/blob/main/reviews/records.jsonl">reviews/records.jsonl</a>. A test in <a href="https://github.com/{repo}">{repo}</a>; nothing here changes Tau Ceti.</p>
</footer>
<script type="application/json" id="settings">{config}</script>
<script>{SCRIPT}</script>
</body>
</html>
"""


def main() -> int:
    index = json.loads((ROOT / "data" / "declarations.json").read_text(encoding="utf-8"))
    settings = json.loads((ROOT / "data" / "settings.json").read_text(encoding="utf-8"))
    records = load(ROOT / "reviews" / "records.jsonl")
    problems = load(ROOT / "reviews" / "problems.jsonl")
    out = ROOT / "site"
    if (out / "data").exists():
        shutil.rmtree(out / "data")
    (out / "data" / "m").mkdir(parents=True)
    compact = {"ensure_ascii": False, "separators": (",", ":")}
    (out / "index.html").write_text(page(index, records, settings, problems), encoding="utf-8")
    (out / "data" / "search.json").write_text(json.dumps(search_index(index), **compact), encoding="utf-8")
    (out / "data" / "docs.json").write_text(json.dumps([summary(item["doc"]) for item in index["declarations"]], **compact), encoding="utf-8")
    for n, shard in shards(index).items():
        (out / "data" / "m" / f"{n}.json").write_text(json.dumps(shard, **compact), encoding="utf-8")
    (out / "reviews.json").write_text(json.dumps(data(index, records, problems), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"site: {len(index['declarations'])} declarations in {len(index['modules'])} modules, {len(records)} marks, "
          f"{len(reports(problems))} problem reports")
    return 0


if __name__ == "__main__":
    sys.exit(main())
