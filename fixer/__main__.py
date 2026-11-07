"""python -m fixer run | publish | show

`run` takes the people's reviews filed since the fixer started that it has not taken (at most a few a run, within the
day's budget), and acts on each (`run.fix`). `--dry-run` publishes and posts nothing: a change is kept on a local
branch and remembered as a draft, its reply printed. `--only RECORD ...` takes those reviews, whether or not they are
new (a test). `publish RECORD` publishes a dry run's draft: the gate again, then the pull request and the reply.
`show` prints what it remembers.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

from evidence_core.store import Store

from answerer.leancheck import Sandbox
from answerer.post import Poster, gh as run_gh
from answerer.prepare import roadmaps

from .pick import choose, reviews
from .prepare import Paths, prepare
from .publish import Publisher, gate, git
from .run import Config, flag_lines, fix, now, reset
from .state import State
from .tools import WorkTools

FLAG_TITLE = "Fixer: needs a person"
FLAG_INTRO = ("Reviews by people that the review fixer took but could not settle with a pull request: Mathlib's "
              "declarations (a person proposes the change upstream), changes the gate refused, and reviews it gave up "
              "on. It rewrites this list after every run; a review leaves it once a pull request is linked to it "
              "(`/addressed`).")


def log(s: str) -> None:
    print(f"{dt.datetime.now(dt.timezone.utc):%H:%M:%S} {s}", flush=True)


def gh_out(argv: list[str]) -> str:
    return subprocess.run(argv, capture_output=True, text=True, check=True, timeout=300).stdout


def setup(p: Paths, state: State, dry: bool, commit: str | None = None):
    ready = prepare(p, state, log, commit)
    settings = ready.settings
    store = Store.load(p.review / "evidence")
    maintainers = tuple(store.config.get("maintainers") or ())
    if ready.login not in maintainers:  # `/addressed` from anyone else is refused
        raise SystemExit(f"gh acts as {ready.login}, not one of the store's maintainers ({', '.join(maintainers)})")
    sandbox = Sandbox(toolchain=ready.toolchain, roots=[p.work], lean_path=ready.lean_path, home=Path.home(),
                      scratch=p.scratch)
    tools = WorkTools(p.work, sandbox, root=settings["library"]["root"])
    poster = Poster(settings["repo"], dry=dry)
    publisher = Publisher(p.work, settings["library"]["repo"], settings["repo"], settings["site"]["url"], roadmaps,
                          gh=run_gh, comment=poster.comment, dry=dry)
    cfg = Config(review_repo=settings["repo"], library_repo=settings["library"]["repo"], site=settings["site"]["url"],
                 commit=ready.commit, root=settings["library"]["root"], log=log)
    return store, tools, poster, publisher, cfg


def cmd_run(a: argparse.Namespace) -> int:
    import anthropic

    p = Paths.default()
    with State.locked(p.state):
        state = State(p.state)
        if not state.since:
            start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
            state.since = a.since or start.strftime("%Y-%m-%dT%H:%M:%SZ")
            state.save()
        store, tools, poster, publisher, cfg = setup(p, state, a.dry_run)
        if a.max is not None:
            cfg.max_items = a.max
        if a.budget is not None:
            cfg.item_budget = a.budget
        found = reviews(store.records, cfg.review_repo)
        picked = choose(found, state.items if not a.only else {}, state.since, cfg.max_items, a.only)
        log(f"{len(picked)} review(s) to take, of {len(found)} by people; since {state.since}")
        client = anthropic.Anthropic(api_key=p.key.read_text(encoding="utf-8").strip(), timeout=1800, max_retries=3)
        system = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")
        today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        areas = roadmaps()
        for review in picked:
            if state.spent(today) >= cfg.daily_budget:
                log(f"the day's budget, ${cfg.daily_budget:.2f}, is spent: the rest waits")
                break
            log(f"{review.id} ({review.kind}, {review.decl}, issue #{review.issue})")
            entry = fix(review, client, tools, publisher, state, cfg, system, today, areas, gh_out)
            if not a.dry_run:
                state.taken(review.id, entry)
            state.save()
            log(f"{review.id}: {entry.get('outcome')} by {entry.get('model')} in {entry.get('turns')} turns, "
                f"${entry.get('cost', 0):.2f}" + (f"; {entry['pr']}" if entry.get("pr") else "") +
                (f"; {entry['flag']}" if entry.get("flag") else ""))
            if a.dry_run:
                print(json.dumps(entry, ensure_ascii=False, indent=1))
        if not a.dry_run:
            lines = flag_lines(reviews(Store.load(p.review / "evidence").records, cfg.review_repo), state, cfg)
            if lines or state.flag_issue:
                state.flag_issue = poster.flags(lines, state.flag_issue, title=FLAG_TITLE, intro=FLAG_INTRO)
            state.save()
    return 0


def cmd_publish(a: argparse.Namespace) -> int:
    """A dry run's draft, published: its branch's changes on the commit it was made at, the gate, then the pull
    request and the reply."""
    p = Paths.default()
    with State.locked(p.state):
        state = State(p.state)
        draft = state.drafts.get(a.record)
        if draft is None:
            print(f"no draft for {a.record}", file=sys.stderr)
            return 2
        store, tools, poster, publisher, cfg = setup(p, state, dry=False, commit=draft["base"])
        review = next((v for v in reviews(store.records, cfg.review_repo) if v.id == a.record), None)
        if review is None:
            print(f"{a.record} is not a review by a person in force", file=sys.stderr)
            return 2
        reset(p.work, draft["base"])
        git(p.work, "restore", f"--source={draft['branch']}", "--worktree", "--", "TauCeti")
        try:
            g = gate(p.work, tools, cfg.root)
            if not g.ok:
                print(f"the gate refuses it: {g.why}", file=sys.stderr)
                return 1
            by = {"tool": cfg.tool, "model": draft["model"]}
            number, note = publisher.open(review, draft["result"], draft["model"], g)
            if number is None:
                print(note, file=sys.stderr)
                return 1
            pr = f"{cfg.library_repo}#{number}"
            publisher.link(review, pr, draft["result"], by)
            state.taken(review.id, {"at": now(), "decl": review.decl, "kind": review.kind, "issue": review.issue,
                                    "author": review.author, "model": draft["model"], "outcome": "pr", "pr": pr,
                                    "branch": note, "cost": draft.get("cost", 0), "summary": draft["result"].get("summary", "")})
            del state.drafts[a.record]
            state.save()
            log(f"{a.record}: published as {pr}")
        finally:
            reset(p.work, draft["base"])
    return 0


def cmd_show(a: argparse.Namespace) -> int:
    state = State(Paths.default().state)
    print(json.dumps({"since": state.since, "spend": state.days, "flag_issue": state.flag_issue,
                      "prepared": {k: v for k, v in state.prepared.items() if k != "lean_path"},
                      "drafts": state.drafts, "items": state.items}, indent=1, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m fixer", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--only", nargs="*")
    r.add_argument("--since", help="on the first run: take reviews filed since then (ISO time); default a day before")
    r.add_argument("--max", type=int)
    r.add_argument("--budget", type=float, help="dollars for each review")
    sub.add_parser("publish").add_argument("record")
    sub.add_parser("show")
    a = ap.parse_args(argv)
    return {"run": cmd_run, "publish": cmd_publish, "show": cmd_show}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
