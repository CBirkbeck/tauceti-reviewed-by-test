#!/usr/bin/env python3
"""Voyager's announcements of what is new in Tau Ceti, read from its topic on the Lean Zulip, as
`named` records (S3): the named results and notable definitions the site leads with.

  python3 scripts/voyager.py fetch                    read the topic into data/voyager.jsonl, with
                                                      ZULIP_SITE, ZULIP_EMAIL and ZULIP_API_KEY set
  python3 scripts/voyager.py import <messages.json>   the same from a saved API response
  python3 scripts/voyager.py record --dataset DIR [--store DIR]
                                                      a `named` record for each announcement whose
                                                      declaration the dataset has, once each

An announcement is a bullet `- **[<name>](<link>)** — <sentence> (TauCeti#<n>)`, the link to the
declaration's page on this site (`…/#/d/<declaration>`, since 2026-10-24) or, before, its anchor in
the API docs (`<docs address>#<declaration>`);
the heading above it (`*Named results*`, `*Notable definitions*`) says whether it is a result or a
definition. One whose declaration the pinned dataset does not have yet is recorded on a later run,
once the pin includes it.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, load_settings  # noqa: E402

from evidence_core import Dataset  # noqa: E402
from evidence_core import records as rec  # noqa: E402
from evidence_core.status import classify  # noqa: E402
from evidence_core.store import Store  # noqa: E402

ANNOUNCEMENTS = ROOT / "data" / "voyager.jsonl"
STORE = ROOT / "evidence"
VOYAGER = {"kind": "agent", "agent": {"tool": "Voyager"}}
BULLET = re.compile(r"^\s*[-*] \*\*\[(?P<name>.+?)\]\((?P<url>https://[^)\s]+)\)\*\*[†‡*]*\s*(?:[—–-]\s*)?(?P<about>.*)$")
DOCS = re.compile(r"^https://(?:taucetiproject\.github\.io/TauCeti|taucetiproject\.org)/docs/[^#]+\.html#(?P<decl>.+)$")
#: A declaration's page on this site, as Voyager links it since 2026-10-24: `<site>/#/d/<name>`.
SITE = re.compile(r"^https://[^/\s]+/[^#\s]*#/d/(?P<decl>[^\s)]+)$")
HEADING = re.compile(r"^\s*\*(?P<title>[^*\s][^*]*?)\*(?:\s|$)")
PRS = re.compile(r"TauCeti#(\d+)")
WHAT = {"named results": "result", "notable definitions": "definition",
        "notable definitions and infrastructure": "definition"}


def iso(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def plain(text: str) -> str:
    """An announcement's sentence without its pull request numbers."""
    text = re.sub(r"\s*\((?:[\s,;]*(?:and\s+)?TauCeti#\d+)+[\s,;]*\)", "", text)
    return text.strip().rstrip(";,").strip()


def parse_post(message: dict) -> list[dict]:
    """The announcements of one message, as the Zulip API returns it with `apply_markdown=false`."""
    out, what = [], None
    for line in (message.get("content") or "").splitlines():
        b = BULLET.match(line)
        if b:
            m = DOCS.match(b["url"]) or SITE.match(b["url"])
            if m:
                about = b["about"].strip()
                out.append({"decl": urllib.parse.unquote(m["decl"]), "name": b["name"].strip(), "what": what,
                            "about": plain(about), "prs": [int(n) for n in PRS.findall(about)],
                            "source": {"voyager": message["id"], "stream": message.get("stream_id")},
                            "at": iso(message["timestamp"])})
            continue
        h = HEADING.match(line)
        if h:
            what = WHAT.get(h["title"].strip().lower())
        elif line.lstrip().startswith("**"):
            what = None
    return out


def merge(known: list[dict], new: list[dict]) -> list[dict]:
    """``known`` and the announcements of ``new`` it lacks (by declaration and name), oldest first."""
    seen = {(a["decl"], a["name"]) for a in known}
    out = list(known)
    for a in new:
        if (a["decl"], a["name"]) not in seen:
            seen.add((a["decl"], a["name"]))
            out.append(a)
    return sorted(out, key=lambda a: (a["at"], a["source"]["voyager"]))


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


def post_url(site: str, stream: int | None, channel: str, topic: str, message_id: int) -> str:
    """The link Zulip gives a message in a topic."""
    where = f"{stream}-{channel.replace(' ', '-')}" if stream else urllib.parse.quote(channel)
    return f"{site}/#narrow/channel/{where}/topic/{topic.replace(' ', '.20')}/near/{message_id}"


def named_records(announcements: list[dict], ds: Dataset, store: Store, voyager: dict) -> list[dict]:
    """A `named` record for each announcement whose declaration is one of ``ds``'s own and that
    Voyager has not yet named in ``store``, keyed in ``ds``. A declaration named under an earlier name
    and renamed since counts as named: a post whose link was moved to the new name names it again."""
    done = set()
    for r in store.records:
        if r.get("kind") == "named" and ((r.get("by") or {}).get("agent") or {}).get("tool") == "Voyager":
            done.add(r["subject"]["name"])
            now = classify(r["subject"], ds).decl
            if now is not None:
                done.add(now.name)
    out = []
    for a in announcements:
        d = ds.by_name.get(a["decl"])
        if d is None or not d.is_project or a["decl"] in done:
            continue
        done.add(a["decl"])
        url = post_url(voyager["site"], a["source"].get("stream"), voyager["channel"], voyager["topic"],
                       a["source"]["voyager"])
        out.append({"schema": rec.SCHEMA, "kind": "named", "subject": rec.subject_from_decl(d, ds), "by": VOYAGER,
                    "at": a["at"], "origin": {"kind": "zulip", "ref": f"voyager {a['source']['voyager']}"},
                    "name": a["name"], "what": a["what"] or ("result" if d.is_prop else "definition"),
                    "text": a["about"],
                    "reference": {"text": ", ".join(["Voyager"] + [f"TauCeti#{n}" for n in a["prs"]]), "url": url}})
    return out


def fetch_messages(site: str, email: str, key: str, channel: str, topic: str, sender: str) -> list[dict]:
    """Every message of the topic by ``sender``, oldest first, as the Zulip API returns them."""
    narrow = json.dumps([{"operator": "channel", "operand": channel}, {"operator": "topic", "operand": topic},
                         {"operator": "sender", "operand": sender}])
    auth = "Basic " + base64.b64encode(f"{email}:{key}".encode("utf-8")).decode("ascii")
    anchor, out = "newest", []
    while True:
        params = {"anchor": anchor, "num_before": 1000, "num_after": 0, "narrow": narrow, "apply_markdown": "false"}
        if anchor != "newest":
            params["include_anchor"] = "false"
        req = urllib.request.Request(f"{site}/api/v1/messages?{urllib.parse.urlencode(params)}",
                                     headers={"Authorization": auth})
        with urllib.request.urlopen(req, timeout=60) as r:
            page = json.loads(r.read().decode("utf-8"))
        if page.get("result") != "success":
            raise RuntimeError(f"Zulip: {page.get('msg', page)}")
        messages = page.get("messages", [])
        out = messages + out
        if page.get("found_oldest") or not messages:
            return out
        anchor = str(messages[0]["id"])


def keep(messages: list[dict], path: Path = ANNOUNCEMENTS) -> tuple[int, int]:
    """Adds the announcements of ``messages`` to the file: (new ones, all)."""
    known = read_jsonl(path)
    merged = merge(known, [a for m in messages for a in parse_post(m)])
    write_jsonl(path, merged)
    for m in messages:
        if "**[" in (m.get("content") or "") and not parse_post(m):
            print(f"::warning::Voyager's post {m['id']} links declarations, but no announcement could be read from it")
    return len(merged) - len(known), len(merged)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="voyager.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch")
    sub.add_parser("import").add_argument("messages")
    rec_cmd = sub.add_parser("record")
    rec_cmd.add_argument("--dataset", required=True)
    rec_cmd.add_argument("--store", default=str(STORE), help="the evidence store (default: evidence/)")
    args = p.parse_args(argv)
    v = load_settings()["voyager"]
    if args.cmd == "fetch":
        env = [os.environ.get(k, "") for k in ("ZULIP_SITE", "ZULIP_EMAIL", "ZULIP_API_KEY")]
        if not all(env):
            print("::error::ZULIP_SITE, ZULIP_EMAIL and ZULIP_API_KEY must be set", file=sys.stderr)
            return 1
        new, total = keep(fetch_messages(*env, v["channel"], v["topic"], v["sender"]))
    elif args.cmd == "import":
        data = json.loads(Path(args.messages).read_text(encoding="utf-8"))
        new, total = keep(data["messages"] if isinstance(data, dict) else data)
    else:
        store = Store.load(args.store)
        added = store.add(named_records(read_jsonl(ANNOUNCEMENTS), Dataset.load(args.dataset), store, v))
        print(f"recorded {len(added)} named results")
        return 0
    print(f"{new} new announcements, {total} in all")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
