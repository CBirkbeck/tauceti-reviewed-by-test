"""One run: follow up the docstring fixes waiting to merge, answer the open items it has not answered
(within the limits), act on each verdict, and rewrite the list of what needs a person.

What each verdict does (the code decides, never the model):

| verdict | a no | a suggestion or question |
|---|---|---|
| `answered` | listed for a person | `/answered`, the reply its note |
| `intended` | `/intended`, the reply its note | listed |
| `not_a_problem` | `/invalid`, the reply its note | listed |
| `docstring_fix` | a pull request; the reply, linking it; `/fixed <commit>` once it merges | listed |
| `lean_fix_needed` | the reply; listed | listed |
| `unclear`, or no verdict | listed | listed |
| `not_mathematical` | nothing | nothing |
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable

from evidence_core.coverage import Evidence
from evidence_core.dataset import Dataset

from .clean import clean
from .items import Item, declaration
from .model import Outcome, assess as assess_item, brief, who
from .post import Poster
from .state import State

COMMAND = {"intended": "intended", "not_a_problem": "invalid"}
#: What a reply may run to, in characters: the prompt asks for 120 words; a longer one is cut at a paragraph.
REPLY_LIMIT = 1200


@dataclass
class Config:
    repo: str  # the review repository, where the store is
    library_repo: str  # TauCetiProject/TauCeti
    site: str  # the review site's address
    commit: str  # the library commit the site shows
    maintainers: tuple = ("CBirkbeck",)  # exempt from the per-author limit
    model: str = "claude-fable-5-1"
    effort: str = "high"
    max_tokens: int = 64000
    max_turns: int = 40
    item_budget: float = 6.0  # dollars: past it, the model is asked for its verdict at once
    daily_budget: float = 20.0
    max_items: int = 6  # a run
    per_author: int = 2  # a day
    tool: str = "Tau Ceti answerer"
    log: Callable[[str], None] = field(default=print, repr=False)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def thread_of(ev: Evidence, item: Item) -> list[dict]:
    """The replies to the item and the statuses set on it, in order."""
    out = [{"kind": "reply", "by": c.get("by") or {}, "at": c.get("at", ""), "text": c.get("text", "")}
           for c in ev.replies.get(item.id, [])]
    out += [{"kind": f"status {s.get('state')}", "by": s.get("by") or {}, "at": s.get("at", ""), "text": s.get("text", "")}
            for s in ev.statuses.get(item.id, [])]
    return sorted(out, key=lambda t: t["at"])


def reopened_since(item: Item, at: str) -> bool:
    return any(s.get("state") == "reopened" and s.get("at", "") > at for s in item.view.get("statuses") or [])


def choose(items: list[Item], state: State, cfg: Config, today: str) -> list[Item]:
    per_author: dict[str, int] = {}
    for e in state.items.values():
        if e.get("at", "").startswith(today) and e.get("author") and e.get("author") not in cfg.maintainers:
            per_author[e["author"]] = per_author.get(e["author"], 0) + 1
    chosen = []
    for item in items:
        done = state.items.get(item.id)
        if done and (done.get("pr") or not reopened_since(item, done.get("at", ""))):
            continue
        if item.author not in cfg.maintainers:
            if per_author.get(item.author, 0) >= cfg.per_author:
                continue
            per_author[item.author] = per_author.get(item.author, 0) + 1
        chosen.append(item)
        if len(chosen) >= cfg.max_items:
            break
    return chosen


def pr_link(cfg: Config, number: int) -> str:
    return f"[{cfg.library_repo.split('/')[-1]}#{number}](https://github.com/{cfg.library_repo}/pull/{number})"


def act(item: Item, decl: dict, out: Outcome, poster: Poster, prs: Any, cfg: Config) -> dict:
    """What happens on a verdict: returns what to remember of it."""
    if out.verdict is None:
        return {"verdict": None, "flag": f"no verdict ({out.error})"}
    v, by = out.verdict, {"tool": cfg.tool, "model": out.model or cfg.model}
    verdict, reply, summary = v["verdict"], clean(v.get("reply", ""), limit=REPLY_LIMIT), v.get("summary", "")
    entry = {"verdict": verdict, "summary": summary, "reply": reply, "by": by}
    if verdict == "not_mathematical" or not v.get("mathematical", True):
        return {**entry, "verdict": "not_mathematical"}
    if item.kind == "question":
        if verdict == "answered" and reply:
            poster.close(item, "answered", reply, by)
            return entry
        return {**entry, "flag": summary or verdict}
    if verdict in COMMAND and reply:
        poster.close(item, COMMAND[verdict], reply, by)
        return entry
    if verdict == "docstring_fix":
        entry["edits"] = v.get("edits") or []
        number, err = prs.propose(item, decl, v, by)
        if not number:
            return {**entry, "flag": f"a docstring fix was not proposed: {err}"}
        poster.reply(item, f"{reply}\n\nA fix is proposed in {pr_link(cfg, number)}; this no closes when it is merged.", by)
        return {**entry, "pr": number}
    if verdict == "lean_fix_needed" and reply:
        poster.reply(item, reply, by)
    return {**entry, "flag": summary or verdict}


def follow_up(items: list[Item], prs: Any, poster: Poster, state: State, cfg: Config) -> None:
    """Docstring fixes waiting to merge: merged, the no is closed as fixed at the merge commit."""
    open_ids = {i.id for i in items}
    for item_id, e in state.items.items():
        if not e.get("pr") or e.get("done"):
            continue
        st, sha = prs.state(e["pr"])
        if st == "MERGED" and sha:
            if item_id in open_ids:
                note = f"{e.get('reply', '')}\n\nFixed by {pr_link(cfg, e['pr'])}, merged as `{sha[:12]}`."
                poster.close(SimpleNamespace(id=item_id, issue=e.get("issue")), "fixed", note.strip(),
                             e.get("by") or {"tool": cfg.tool, "model": cfg.model}, commit=sha)
            e["done"] = "fixed"
            cfg.log(f"{item_id}: {cfg.library_repo}#{e['pr']} merged, closed as fixed")
        elif st == "CLOSED":
            e["done"], e["flag"] = "closed", f"its docstring fix, {cfg.library_repo}#{e['pr']}, was closed without merging"


def flag_lines(items: list[Item], state: State, cfg: Config) -> list[str]:
    lines = []
    for item in items:
        e = state.items.get(item.id) or {}
        if e.get("flag"):
            where = f"issue #{item.issue}" if item.issue else "from an AI agent's batch"
            what = "a no" if item.kind == "problem" else "a suggestion"
            lines.append(f"- [ ] [`{item.decl}`]({cfg.site}#/d/{item.decl}): {what} by {who(item.record.get('by') or {})}, "
                         f"{where}, record `{item.id}`. {clean(e['flag'], limit=400)}")
    return lines


def answer(items: list[Item], ev: Evidence, ds: Dataset, lib: Any, tools: Any, client: Any, poster: Poster, prs: Any,
           state: State, cfg: Config, today: str, system: str, assess: Callable = assess_item) -> list[dict]:
    follow_up(items, prs, poster, state, cfg)
    state.save()
    done = []
    for item in choose(items, state, cfg, today):
        if state.spent(today) >= cfg.daily_budget:
            cfg.log(f"the day's budget, ${cfg.daily_budget:.2f}, is spent: the rest waits")
            break
        decl = declaration(ds, lib, item.decl)
        out = assess(client, cfg, system, brief(item, decl, thread_of(ev, item), cfg.commit, cfg.library_repo, cfg.site),
                     tools)
        state.spend(today, out.cost)
        entry = act(item, decl, out, poster, prs, cfg)
        entry.update(at=now(), author=item.author, decl=item.decl, kind=item.kind, issue=item.issue, model=out.model,
                     cost=round(out.cost, 4), turns=out.turns)
        state.handled(item.id, entry)
        state.save()
        cfg.log(f"{item.id} ({item.kind}, {item.decl}): {entry['verdict']} by {out.model} in {out.turns} turns, "
                f"${out.cost:.2f}" + (f"; {entry['flag']}" if entry.get("flag") else ""))
        done.append(entry)
    lines = flag_lines(items, state, cfg)
    if lines or state.flag_issue:
        state.flag_issue = poster.flags(lines, state.flag_issue)
    state.save()
    return done
