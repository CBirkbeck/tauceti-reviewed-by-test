#!/usr/bin/env python3
"""Build the page of Tau Ceti declarations and their review marks.

  python3 scripts/build_site.py

Reads data/declarations.json, reviews/records.jsonl and data/settings.json and
writes site/index.html and site/reviews.json. The JSON is for other readers of
the marks (the atlas, Tau Ceti's own docs): for each declaration, its current
version and every mark, with whether the mark is on that version.
"""
from __future__ import annotations

import html
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
MEANING = {"Reviewed-by": "it is the intended mathematical notion", "Tested-by": "its examples and unit tests check out",
           "Acked-by": "happy with the design, without a full check"}
DEFINITIONS = {"def", "structure", "class", "inductive"}


def review_link(repo: str, item: dict) -> str:
    query = urlencode({"template": "reviewed-by.yml", "title": f"Review: {item['name']}", "declaration": item["name"], "version": item["hash"]})
    return f"https://github.com/{repo}/issues/new?{query}"


def marks_by_declaration(index: dict, records: list) -> dict:
    current = {item["name"]: item["hash"] for item in index["declarations"]}
    marks = defaultdict(list)
    for record in records:
        if record["decl"] in current:
            marks[record["decl"]].append({**record, "current": record["hash"] == current[record["decl"]]})
    for items in marks.values():
        items.sort(key=lambda m: (not m["current"], list(MEANING).index(m["trailer"]), m["at"]))
    return marks


def prose(text: str) -> str:
    """Docstring Markdown, enough of it: paragraphs, code and bold."""
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        block = html.escape(" ".join(block.split()), quote=False)
        block = re.sub(r"`([^`]+)`", r"<code>\1</code>", block)
        block = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", block)
        out.append(f"<p>{block}</p>")
    return "".join(out)


def module_summary(doc: str) -> str:
    paragraphs = [p for p in re.split(r"\n\s*\n", doc.strip()) if p.strip() and not p.lstrip().startswith("#")]
    return prose(paragraphs[0]) if paragraphs else ""


def when(stamp: str) -> str:
    try:
        return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").strftime("%-d %b %Y")
    except ValueError:
        return stamp


def mark_html(repo: str, mark: dict) -> str:
    who = f"{html.escape(mark['agent'])} <span class=\"ai\">AI</span> via @{html.escape(mark['by'])}" if mark["kind"] == "agent" else f"@{html.escape(mark['by'])}"
    issue = mark.get("source", {}).get("issue")
    href = f"https://github.com/{repo}/issues/{issue}" if issue else "#"
    tip = f"{mark['trailer']}: {MEANING[mark['trailer']]}. Version {mark['hash']}, {when(mark['at'])}." + (f" Evidence: {mark['evidence']}" if mark["evidence"] else "")
    classes = "mark " + mark["kind"] + ("" if mark["current"] else " stale")
    note = "" if mark["current"] else ' <span class="note">earlier version</span>'
    return (f'<a class="{classes}" href="{href}" title="{html.escape(tip)}"><span class="tick" aria-hidden="true">✓</span>'
            f'<span class="trailer">{mark["trailer"]}</span> <span class="who">{who}</span>{note}</a>')


def declaration_html(repo: str, item: dict, marks: list) -> str:
    group = "def" if item["kind"] in DEFINITIONS else "theorem"
    reviewed = "yes" if any(m["current"] for m in marks) else "no"
    lines = item["source"].splitlines()
    shown = "\n".join(lines[:40]) + ("\n…" if len(lines) > 40 else "")
    return f"""
<article class="decl" id="{html.escape(item['name'])}" data-group="{group}" data-reviewed="{reviewed}">
  <div class="decl-head"><span class="kind">{item['kind']}</span><h3><code>{html.escape(item['name'])}</code></h3><a class="src" href="{html.escape(item['url'])}">source</a></div>
  {f'<div class="doc">{prose(item["doc"])}</div>' if item["doc"] else ''}
  <pre><code>{html.escape(shown)}</code></pre>
  <div class="marks">{''.join(mark_html(repo, m) for m in marks)}<a class="review" href="{html.escape(review_link(repo, item))}">Review this</a></div>
</article>"""


STYLE = """
:root { color-scheme: light dark; --bg: #f8f7f4; --surface: #ffffff; --ink: #1c2025; --muted: #59626c; --faint: #8b939b; --line: #e3e0da;
  --code: #f3f1ec; --accent: #2b6a99; --person: #2f7d4f; --agent: #6a58b8; --stale: #9aa0a6; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg: #0e1114; --surface: #151a1f; --ink: #e5e8eb; --muted: #a5aeb6;
  --faint: #7b848d; --line: #252b32; --code: #1a1f25; --accent: #82b6de; --person: #6fcf97; --agent: #b2a4f1; --stale: #6b737b; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }
main { max-width: 900px; margin: 0 auto; padding: 32px 16px 64px; }
a { color: var(--accent); }
code, pre { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; }
.eyebrow { text-transform: uppercase; letter-spacing: 1.4px; font-size: 11.5px; color: var(--faint); margin: 0 0 6px; }
h1 { font-size: 28px; line-height: 1.2; margin: 0 0 8px; letter-spacing: -.3px; }
.lede { color: var(--muted); margin: 0 0 6px; font-size: 16px; }
.meta { color: var(--faint); font-size: 13px; margin: 0 0 24px; }
.how { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 16px 20px; margin-bottom: 20px; }
.how ol { margin: 0 0 10px; padding-left: 20px; } .how li { margin: 4px 0; } .how p { margin: 8px 0 0; color: var(--muted); font-size: 14px; }
.legend { display: grid; grid-template-columns: max-content 1fr; gap: 4px 12px; margin: 12px 0 0; font-size: 13.5px; color: var(--muted); }
.legend dt { font-weight: 600; color: var(--ink); } .legend dd { margin: 0; }
.filters { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 8px; }
.filters button { font: inherit; font-size: 13px; padding: 4px 12px; border-radius: 999px; border: 1px solid var(--line); background: var(--surface); color: var(--muted); cursor: pointer; }
.filters button[aria-pressed="true"] { border-color: var(--accent); color: var(--accent); }
.module { margin-top: 28px; }
.module h2 { font-size: 13px; font-weight: 600; margin: 0 0 4px; word-break: break-word; } .module h2 code { font-size: 13.5px; }
.module-doc { color: var(--muted); font-size: 14px; } .module-doc p { margin: 2px 0; }
.count { font-size: 12.5px; color: var(--faint); margin: 2px 0 10px; }
.decl { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px 12px; margin: 10px 0; }
.decl-head { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.decl-head h3 { margin: 0; font-size: 14.5px; font-weight: 600; word-break: break-word; flex: 1 1 auto; min-width: 0; }
.decl-head h3 code { font-size: 14px; }
:not(pre) > code { overflow-wrap: anywhere; }
.kind { font-size: 11px; text-transform: uppercase; letter-spacing: .8px; color: var(--faint); border: 1px solid var(--line); border-radius: 4px; padding: 0 5px; }
.decl[data-group="def"] .kind { color: var(--accent); border-color: currentColor; }
.src { font-size: 12.5px; color: var(--faint); }
.doc { color: var(--muted); font-size: 14px; margin-top: 6px; } .doc p { margin: 4px 0; } .doc code { font-size: 12.5px; }
pre { background: var(--code); border-radius: 6px; padding: 10px 12px; overflow-x: auto; margin: 10px 0 8px; line-height: 1.45; }
.marks { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; }
.mark { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: var(--ink); text-decoration: none; border: 1px solid var(--line); border-radius: 999px; padding: 2px 10px 2px 3px; }
.mark:hover { border-color: var(--faint); }
.tick { display: inline-grid; place-items: center; width: 18px; height: 18px; border-radius: 50%; font-size: 11px; font-weight: 700; }
.mark.person .tick { background: var(--person); color: var(--surface); }
.mark.agent .tick { border: 1.5px solid var(--agent); color: var(--agent); }
.trailer { font-weight: 600; } .ai { font-size: 10.5px; font-weight: 700; letter-spacing: .6px; color: var(--agent); }
.mark.stale { color: var(--stale); } .mark.stale .tick { background: none; border: 1.5px solid var(--stale); color: var(--stale); } .mark.stale .ai { color: var(--stale); }
.note { font-size: 11.5px; font-style: italic; }
.review { margin-left: auto; font-size: 13px; font-weight: 600; text-decoration: none; padding: 3px 12px; border-radius: 6px; border: 1px solid var(--accent); }
.review:hover { background: var(--accent); color: var(--surface); }
footer { margin-top: 40px; color: var(--faint); font-size: 13px; }
body[data-filter="def"] .decl[data-group="theorem"], body[data-filter="reviewed"] .decl[data-reviewed="no"], body[data-filter="open"] .decl[data-reviewed="yes"] { display: none; }
@media (max-width: 560px) { h1 { font-size: 23px; } .how { padding: 14px 14px; } .decl { padding: 12px 12px 10px; } .review { margin-left: 0; } }
"""

SCRIPT = """
document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {
  document.body.dataset.filter = button.dataset.filter;
  document.querySelectorAll('[data-filter]').forEach(other => other.setAttribute('aria-pressed', String(other === button)));
}));
"""


def page(index: dict, records: list, settings: dict) -> str:
    repo, marks = settings["repo"], marks_by_declaration(index, records)
    by_module = defaultdict(list)
    for item in index["declarations"]:
        by_module[item["module"]].append(item)
    sections = []
    for module in index["modules"]:
        items = sorted(by_module[module["module"]], key=lambda d: d["kind"] not in DEFINITIONS)
        reviewed = sum(1 for d in items if any(m["current"] for m in marks.get(d["name"], [])))
        sections.append(f"""
<section class="module">
  <h2><code>{html.escape(module['module'])}</code></h2>
  <div class="module-doc">{module_summary(module['doc'])}</div>
  <p class="count">{reviewed} of {len(items)} reviewed · <a href="{html.escape(module['url'])}">source</a></p>
  {''.join(declaration_html(repo, d, marks.get(d['name'], [])) for d in items)}
</section>""")
    bulk = f"https://github.com/{repo}/issues/{settings['bulk_issue']}"
    legend = "".join(f"<dt>{t}</dt><dd>{m}</dd>" for t, m in MEANING.items())
    total = len(index["declarations"])
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reviewed-by marks</title>
<meta name="description" content="A test of review marks on Tau Ceti declarations, left from the browser without pull requests.">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>✓</text></svg>">
<style>{STYLE}</style>
</head>
<body data-filter="all">
<main>
<header>
  <p class="eyebrow">Test · review marks</p>
  <h1>Reviewed-by for Tau Ceti</h1>
  <p class="lede">Who has checked which Tau Ceti declarations, what they checked, and on which version, recorded from the browser without pull requests.</p>
  <p class="meta">Tau Ceti <a href="https://github.com/TauCetiProject/TauCeti/tree/{index['tauceti']}">{index['tauceti'][:7]}</a> · {total} declarations in {len(index['modules'])} modules · {len(records)} mark{'s' if len(records) != 1 else ''}</p>
</header>
<section class="how" aria-label="How to leave a mark">
  <ol>
    <li><strong>Review this</strong> under a declaration opens a GitHub form with its name and version filled in. Choose a mark, say what you checked, and submit.</li>
    <li>A bot records the mark, answers on the issue and closes it. There is no pull request, and this page updates within a minute or two.</li>
    <li>If the declaration changes later, the mark stays but is greyed: it applies to the earlier version until someone reviews the new one.</li>
  </ol>
  <p>Marking many at once: comment lines like <code>Reviewed-by: TauCeti.X.y — what you checked</code> on <a href="{bulk}">issue #{settings['bulk_issue']}</a>. AI agents use the same routes and name the agent, model and session; their marks are shown apart from people's.</p>
  <dl class="legend">{legend}</dl>
</section>
<nav class="filters" aria-label="Filter">
  <button data-filter="all" aria-pressed="true">All</button><button data-filter="def" aria-pressed="false">Definitions</button>
  <button data-filter="reviewed" aria-pressed="false">Reviewed</button><button data-filter="open" aria-pressed="false">Not yet reviewed</button>
</nav>
{''.join(sections)}
<footer>
  <p>The marks as data, for the atlas or Tau Ceti's own documentation: <a href="reviews.json">reviews.json</a>. The ledger: <a href="https://github.com/{repo}/blob/main/reviews/records.jsonl">reviews/records.jsonl</a>. A test in <a href="https://github.com/{repo}">{repo}</a>; nothing here changes Tau Ceti.</p>
</footer>
</main>
<script>{SCRIPT}</script>
</body>
</html>
"""


def data(index: dict, records: list) -> dict:
    marks = marks_by_declaration(index, records)
    return {"schema": "reviewed-by/v1", "tauceti": index["tauceti"], "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "declarations": {item["name"]: {"hash": item["hash"], "kind": item["kind"], "url": item["url"],
                                            "marks": [{k: m[k] for k in ("trailer", "by", "kind", "agent", "hash", "current", "at", "evidence")}
                                                      for m in marks.get(item["name"], [])]}
                             for item in index["declarations"]}}


def main() -> int:
    index = json.loads((ROOT / "data" / "declarations.json").read_text(encoding="utf-8"))
    settings = json.loads((ROOT / "data" / "settings.json").read_text(encoding="utf-8"))
    ledger = ROOT / "reviews" / "records.jsonl"
    records = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()] if ledger.exists() else []
    out = ROOT / "site"
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(page(index, records, settings), encoding="utf-8")
    (out / "reviews.json").write_text(json.dumps(data(index, records), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"site: {len(index['declarations'])} declarations, {len(records)} marks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
