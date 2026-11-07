"""The fixer's pull requests, seen through Tau Ceti's review. Every two hours (`python -m fixer follow`) each pull
request the fixer opened, while it is open, is read from GitHub, and if it needs something from its author, the
model works on it in the fixer's checkout (instructions: `follow.md`) and the run, not the model, pushes and replies.

What a pull request may need, the first that applies being the round's work:

1. a merge conflict with `main`: its change is put on the current `main` again (`git apply --3way`), the files that
   did not apply cleanly carrying conflict markers; the push replaces the branch (`--force-with-lease`);
2. CI failing on its head: the failing jobs' errors, from their logs;
3. Tau Ceti's AI review on its head asking for changes: the latest scoreboard (`<!--tauceti-scoreboard-->`, whose
   `<!--tauceti-meta:v1 …-->` names the head it reviewed and each rubric's state) has a rubric not green, and that
   rubric's threads (`<!--tauceti-rubric:NAME-->`) on that head are unresolved and not yet answered by the fixer;
4. people's comments, and their review threads, since the head was committed and not yet answered.

The model fixes what is right and contests what is wrong; the change passes the same gate as a first change
(`publish.gate`) before it is committed and pushed to the pull request's branch, and the replies are posted in their
threads, marked as the fixer's. Each round has a key (the head, the scoreboard, the comments): a round worked is not
worked again, so a contest stands until the reviewers answer it. A merged pull request is done (intake settles the
review on the site); one closed without merging, one still needing work after `MAX_ROUNDS` rounds, and a round the
model gives up on or the gate refuses are listed for a person. There is no daily cap: each round has its own budget.
"""
from __future__ import annotations

import json
import re
import secrets
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from answerer.clean import clean
from answerer.model import untrusted, who
from answerer.post import mark

from . import agent
from .pick import Review
from .publish import Gate, Publisher, gate, git
from .run import Config, reset
from .state import State
from .tools import WorkTools

SCOREBOARD = "<!--tauceti-scoreboard-->"
META = re.compile(r"<!--tauceti-meta:v1 (\{.*?\})-->", re.S)
RUBRIC = re.compile(r"<!--tauceti-rubric:([\w-]+)-->")
OURS = "tool=Tau Ceti fixer;"
#: Checks that say nothing about the pull request's content.
IGNORED = {"reconcile", "rebuild", "pick-runner / pick", "pick", "publish-merge-group-cache", "finalize-merge-group-build"}
FAILED = ("failure", "timed_out", "startup_failure")
MAX_ROUNDS = 8
MARKERS = re.compile(r"^(<<<<<<<|>>>>>>>)( |$)|^=======$", re.M)

FOLLOW_OUTCOMES = ["updated", "contested", "nothing", "close", "gave_up"]
FOLLOW = {
    "type": "object",
    "properties": {
        "outcome": {"type": "string", "enum": FOLLOW_OUTCOMES},
        "summary": {"type": "string", "description": "One line on what you found and did, for the run's log."},
        "commit_message": {"type": "string", "description": "For updated: a first line of at most 72 characters, "
                           "then a blank line and what changed and which findings it answers. Else empty."},
        "replies": {"type": "array", "description": "Replies to review threads, by the thread's id as the brief "
                    "gives it: findings you contest, and findings answered other than by the change.",
                    "items": {"type": "object", "properties": {"thread": {"type": "string"}, "text": {"type": "string"}},
                              "required": ["thread", "text"], "additionalProperties": False}},
        "roadmap": {"type": "string", "description": "A new Roadmap area for the description, from the brief's "
                    "list, if a finding shows the current one is wrong; else empty."},
        "close_reason": {"type": "string", "description": "For close: why the pull request should not go in."},
    },
    "required": ["outcome", "summary", "commit_message", "replies", "roadmap", "close_reason"],
    "additionalProperties": False,
}

QUERY = """query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){pullRequest(number:$n){
state merged closedAt title body headRefName headRefOid mergeable
commits(last:1){nodes{commit{committedDate}}}
reviewThreads(first:100){nodes{isResolved isOutdated path line
  comments(first:30){nodes{databaseId author{login} body createdAt originalCommit{oid}}}}}
comments(last:60){nodes{databaseId author{login} body createdAt}}}}}"""


@dataclass
class Snapshot:
    number: int
    state: str  # OPEN, MERGED (on GitHub, or by Bors), CLOSED
    title: str
    body: str
    branch: str
    head: str
    mergeable: str  # MERGEABLE, CONFLICTING, UNKNOWN
    pushed_at: str  # when its head was committed
    checks: list[dict] = field(default_factory=list)  # {name, conclusion, url}
    scoreboard: dict | None = None  # {id, head, states, at}
    threads: list[dict] = field(default_factory=list)  # {id, rubric, path, line, resolved, commit, comments: [{by, body, at}]}
    comments: list[dict] = field(default_factory=list)  # {id, by, body, at}


@dataclass
class Work:
    kind: str  # conflict, ci, review, comments
    key: str
    failed: list[dict] = field(default_factory=list)
    threads: list[dict] = field(default_factory=list)
    comments: list[dict] = field(default_factory=list)


def ours(body: str) -> bool:
    return OURS in (body or "")


def person(login: str) -> bool:
    return bool(login) and not login.endswith("[bot]")


def read(graphql: Callable[[str, dict], dict], rest: Callable[[str], Any], repo: str, number: int) -> Snapshot:
    owner, name = repo.split("/")
    pr = graphql(QUERY, {"o": owner, "r": name, "n": number})["data"]["repository"]["pullRequest"]
    state = "MERGED" if pr.get("merged") or (pr.get("title") or "").startswith("[Merged by Bors]") else pr["state"]
    head = pr["headRefOid"]
    runs = (rest(f"repos/{repo}/commits/{head}/check-runs?per_page=100") or {}).get("check_runs", [])
    checks = [{"name": c.get("name", ""), "conclusion": c.get("conclusion"), "url": c.get("details_url") or ""} for c in runs]
    # Tau Ceti's `build`, `scope` and `bump-guard` are commit statuses, set from its CI's run
    statuses = (rest(f"repos/{repo}/commits/{head}/status") or {}).get("statuses", [])
    checks += [{"name": c.get("context", ""), "conclusion": "failure" if c.get("state") in ("failure", "error") else c.get("state"),
                "url": c.get("target_url") or ""} for c in statuses]
    comments = [{"id": c["databaseId"], "by": (c.get("author") or {}).get("login", ""), "body": c.get("body") or "",
                 "at": c.get("createdAt", "")} for c in pr["comments"]["nodes"]]
    scoreboard = None
    boards = [c for c in comments if SCOREBOARD in c["body"]]
    if boards:
        c = max(boards, key=lambda c: c["at"])
        m = META.search(c["body"])
        try:
            meta = json.loads(m.group(1)) if m else {}
        except ValueError:
            meta = {}
        scoreboard = {"id": c["id"], "head": meta.get("head_sha", ""), "states": meta.get("states") or {}, "at": c["at"]}
    threads = []
    for t in pr["reviewThreads"]["nodes"]:
        cs = t["comments"]["nodes"]
        if not cs:
            continue
        m = RUBRIC.search(cs[0].get("body") or "")
        threads.append({"id": str(cs[0]["databaseId"]), "rubric": m.group(1) if m else "", "path": t.get("path"),
                        "line": t.get("line"), "resolved": t.get("isResolved", False),
                        "commit": (cs[0].get("originalCommit") or {}).get("oid", ""),
                        "comments": [{"by": (c.get("author") or {}).get("login", ""), "body": c.get("body") or "",
                                      "at": c.get("createdAt", "")} for c in cs]})
    commits = pr["commits"]["nodes"]
    return Snapshot(number, state, pr.get("title") or "", pr.get("body") or "", pr["headRefName"], head,
                    pr.get("mergeable") or "UNKNOWN", commits[0]["commit"]["committedDate"] if commits else "",
                    checks, scoreboard, threads, comments)


def needs(s: Snapshot, seen: set[str]) -> Work | None:
    """This round's work on an open pull request, or None: nothing new needs its author."""
    if s.state != "OPEN":
        return None
    if s.mergeable == "CONFLICTING":
        w = Work("conflict", f"conflict:{s.head}")
        return None if w.key in seen else w
    failed = [c for c in s.checks if c["conclusion"] in FAILED and c["name"] not in IGNORED]
    if failed:
        w = Work("ci", f"ci:{s.head}", failed=failed)
        return None if w.key in seen else w
    sb = s.scoreboard
    if sb and sb["head"] == s.head:
        bad = {r for r, st in sb["states"].items() if st != "green"}
        findings = [t for t in s.threads if t["rubric"] in bad and not t["resolved"] and t["commit"] == s.head
                    and not ours(t["comments"][-1]["body"])]
        if findings:
            w = Work("review", f"review:{sb['id']}", threads=findings)
            return None if w.key in seen else w
    said = [c for c in s.comments if person(c["by"]) and not ours(c["body"]) and "<!--tauceti-" not in c["body"]
            and c["at"] > s.pushed_at]
    asked = [t for t in s.threads if not t["rubric"] and not t["resolved"] and person(t["comments"][-1]["by"])
             and not ours(t["comments"][-1]["body"]) and t["comments"][-1]["at"] > s.pushed_at]
    if said or asked:
        key = "comments:" + ",".join([str(c["id"]) for c in said] + [f"{t['id']}@{t['comments'][-1]['at']}" for t in asked])
        w = Work("comments", key, threads=asked, comments=said)
        return None if w.key in seen else w
    return None


def ci_errors(rest_text: Callable[[str], str], repo: str, check: dict, limit: int = 6000,
              rest: Callable[[str], Any] | None = None) -> str:
    """The errors of a failing check, from its job's log (or, for a status naming a whole run, from the logs of the
    run's failed jobs): lines naming an error, then the log's end."""
    url = check.get("url", "")
    m = re.search(r"/actions/runs/\d+/job/(\d+)", url)
    jobs = [m.group(1)] if m else []
    run_ = re.search(r"/actions/runs/(\d+)", url)
    if not jobs and run_ and rest is not None:
        try:
            listed = (rest(f"repos/{repo}/actions/runs/{run_.group(1)}/jobs?per_page=100") or {}).get("jobs", [])
        except (subprocess.SubprocessError, OSError, ValueError):
            listed = []
        jobs = [str(j["id"]) for j in listed if j.get("conclusion") in FAILED][:3]
    if not jobs:
        return "(no log: the check names no GitHub Actions job that failed)"
    parts = []
    for job in jobs:
        try:
            log = rest_text(f"repos/{repo}/actions/jobs/{job}/logs")
        except (subprocess.SubprocessError, OSError) as e:
            parts.append(f"(the log of job {job} could not be read: {e})")
            continue
        lines = [re.sub(r"^\d{4}-\d\d-\d\dT[\d:.]+Z ", "", l) for l in log.splitlines()]
        errors = [l for l in lines if re.search(r"\berror\b|✖|FAIL", l, re.I)][:60]
        parts.append("\n".join(errors) + "\n…\n" + "\n".join(lines[-80:]))
    return "\n\n".join(parts)[-limit:]


def brief(s: Snapshot, w: Work, review: Review | None, cfg: Config, areas: set[str], errors: dict[str, str],
          conflicts: list[str], main: str, nonce: str | None = None) -> str:
    nonce = nonce or secrets.token_hex(6)
    roadmap = next((l.split(":", 1)[1].strip() for l in s.body.splitlines() if l.startswith("Roadmap:")), "none")
    parts = ["# Your pull request",
             f"{cfg.library_repo}#{s.number}: {s.title} (branch `{s.branch}`, head {s.head[:12]}, `Roadmap: {roadmap}`)."]
    if review is not None:
        parts += [f"It addresses a {'no' if review.kind == 'problem' else 'suggestion'} on `{review.decl}`, written on "
                  f"the review site by {who(review.record.get('by') or {})}:",
                  untrusted("review", review.record.get("text", ""), nonce)]
    parts += ["", "# What it needs now"]
    if w.kind == "conflict":
        parts.append(f"A merge conflict with `main`. Your change was put on `main` at {main[:12]}; it did not apply "
                     f"cleanly to {', '.join(conflicts) or 'some files'}, which now carry conflict markers. Resolve them.")
    elif w.kind == "ci":
        for c in w.failed:
            parts += [f"## The check `{c['name']}` failed ({c['conclusion']}): its errors (Tau Ceti's CI)",
                      "```", errors.get(c["name"], ""), "```"]
    else:
        if w.kind == "review" and s.scoreboard:
            bad = ", ".join(f"{r} ({st})" for r, st in sorted(s.scoreboard["states"].items()) if st != "green")
            parts.append(f"Tau Ceti's AI review of this head asks for changes: {bad}. Their findings:")
        for t in w.threads:
            thread = "\n\n".join(f"[{c['by']}, {c['at'][:16]}]\n{c['body']}" for c in t["comments"])
            parts.append(untrusted(f"thread {t['id']} ({t['rubric'] or 'a comment'} at {t['path']}:{t['line']})",
                                   thread, nonce))
        for c in w.comments:
            parts.append(untrusted(f"comment by {c['by']} on {c['at'][:16]}", c["body"], nonce))
    parts += ["", "# Your checkout",
              (f"`main` at {main[:12]} with your change applied." if w.kind == "conflict" else
               f"The pull request's branch at its head, {s.head[:12]}."),
              "", "# Roadmap areas", ", ".join(sorted(areas)) if areas else "(not available)",
              "", f"Your budget for this round is about ${cfg.item_budget:.0f}."]
    return "\n".join(parts)


def checkout(work: Path, s: Snapshot, w: Work, builds: Callable[[Path], None] = lambda work: None) -> tuple[str, list[str]]:
    """The checkout made ready for the round: `main` and its sha, with the pull request's change applied and its
    conflicts marked, for a conflict; else the pull request's head. Returns (main's sha, the files in conflict)."""
    git(work, "fetch", "-q", "origin", "main", s.branch)
    main = git(work, "rev-parse", "origin/main").strip()
    if w.kind != "conflict":
        reset(work, s.head)
        builds(work)
        return main, []
    base = git(work, "merge-base", "origin/main", s.head).strip()
    patch = git(work, "diff", "--binary", base, s.head, "--", "TauCeti")
    reset(work, main)
    subprocess.run(["git", "-C", str(work), "apply", "--3way", "-"], input=patch, capture_output=True, text=True,
                   timeout=600)
    git(work, "reset", "-q")  # unstaged, so that the gate sees every change against `main`
    builds(work)
    conflicts = [p for p in git(work, "diff", "--name-only").split() + git(work, "ls-files", "--others",
                                                                            "--exclude-standard").split()
                 if (work / p).is_file() and MARKERS.search((work / p).read_text(encoding="utf-8", errors="replace"))]
    return main, sorted(set(conflicts))


def message(result: dict, s: Snapshot, recreated: bool, model: str) -> str:
    text = clean(result.get("commit_message", ""), limit=3000).strip() or "fix: answer the review"
    first, _, rest = text.partition("\n")
    first = re.sub(r"[@#]", "", first)[:90]
    if recreated:  # the pull request's whole change again, on main: its title first
        rest = f"{first}\n{rest}".strip()
        first = re.sub(r"^\[Merged by Bors\] - ", "", s.title)
    return (f"{first}\n\n{rest}\n\n" if rest.strip() else f"{first}\n\n") + \
        f"Proposed by the Tau Ceti review fixer ({model}), answering the review of #{s.number}.\n\n" \
        f"Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n"


@dataclass
class GitHub:
    """What a round reads from and does on GitHub: `gh` behind small functions, faked in tests."""
    graphql: Callable[[str, dict], dict]
    rest: Callable[[str], Any]
    rest_text: Callable[[str], str]
    gh: Callable[[list[str], str | None], str]
    #: Mathlib's and the library's builds for the checkout as it is, from their Lake caches (`answerer.prepare.cache`),
    #: run outside the sandbox before the model touches anything: a pull request's base may pin another Mathlib.
    builds: Callable[[Path], None] = lambda work: None


def round_(s: Snapshot, w: Work, entry: dict, review: Review | None, client: Any, tools: WorkTools, gh: GitHub,
           state: State, cfg: Config, system: str, today: str, areas: set[str], dry: bool = False,
           work_fn: Callable = agent.work) -> dict:
    """One round of work on a pull request: what to remember of it."""
    work, repo = tools.work, cfg.library_repo
    by = {"tool": cfg.tool, "model": cfg.model}
    try:
        main, conflicts = checkout(work, s, w, gh.builds)
        state.prepared["work"] = ""  # the checkout's builds are this round's now: the next run prepares them again
        state.save()
        if dry:
            return {"kind": w.kind, "would": "work", "conflicts": conflicts}
        errors = {c["name"]: ci_errors(gh.rest_text, repo, c, rest=gh.rest) for c in w.failed}
        tools.created.clear()
        res = work_fn(client, cfg, system, brief(s, w, review, cfg, areas, errors, conflicts, main), tools,
                      log=cfg.log, schema=FOLLOW, outcomes=FOLLOW_OUTCOMES)
        state.spend(today, res.cost)
        by["model"] = res.model or cfg.model
        out = {"kind": w.kind, "head": s.head, "cost": round(res.cost, 4), "turns": res.turns, "model": res.model}
        if res.result is None:
            return {**out, "outcome": "error", "flag": f"a round on {repo}#{s.number} gave no result: {res.error}"}
        r = res.result
        out.update(outcome=r["outcome"], summary=r.get("summary", "")[:400])
        if r["outcome"] == "updated":
            g: Gate = gate(work, tools, cfg.root)
            if not g.ok:
                return {**out, "flag": f"a round's change to {repo}#{s.number} was not pushed: {g.why[:500]}"}
            recreated = w.kind == "conflict"
            git(work, "add", "-A", "--", "TauCeti")
            subprocess.run(["git", "-C", str(work), "commit", "-q", "-F", "-"], input=message(r, s, recreated, by["model"]),
                           capture_output=True, text=True, check=True, timeout=600)
            lease = [f"--force-with-lease=refs/heads/{s.branch}:{s.head}"] if recreated else []
            git(work, "push", "-q", *lease, "origin", f"HEAD:refs/heads/{s.branch}")
            out["pushed"] = git(work, "rev-parse", "HEAD").strip()
        if r["outcome"] in ("updated", "contested", "nothing"):
            known = {t["id"] for t in s.threads}
            for reply in r.get("replies") or []:
                if reply.get("thread") in known and reply.get("text", "").strip():
                    gh.gh(["gh", "api", "-X", "POST", f"repos/{repo}/pulls/{s.number}/comments/{reply['thread']}/replies",
                           "-F", "body=@-"], f"{mark(by)}\n{clean(reply['text'], limit=1200)}")
            out["replies"] = len(r.get("replies") or [])
            area = (r.get("roadmap") or "").strip()
            if area and area in areas and not re.search(rf"^Roadmap: {re.escape(area)}\s*$", s.body, re.M):
                body = re.sub(r"^Roadmap: .*$", f"Roadmap: {area}", s.body, count=1, flags=re.M)
                gh.gh(["gh", "pr", "edit", str(s.number), "--repo", repo, "--body-file", "-"], body)
                out["roadmap"] = area
        if r["outcome"] == "close":
            reason = clean(r.get("close_reason") or r.get("summary", ""), limit=1200)
            gh.gh(["gh", "pr", "close", str(s.number), "--repo", repo, "--comment", f"{mark(by)}\n{reason}"], None)
            return {**out, "flag": f"it closed {repo}#{s.number}: {reason[:300]}"}
        if r["outcome"] == "gave_up":
            return {**out, "flag": f"it gave up on a round of {repo}#{s.number}: {r.get('summary', '')[:300]}"}
        return out
    finally:
        reset(work, cfg.commit)


def follow_all(state: State, reviews_by_id: dict[str, Review], client: Any, tools: WorkTools, gh: GitHub, cfg: Config,
               system: str, today: str, areas: set[str], dry: bool = False, only: int | None = None,
               work_fn: Callable = agent.work) -> list[dict]:
    """A round on each open pull request the fixer opened that needs one."""
    done = []
    for item_id, e in sorted(state.items.items(), key=lambda kv: kv[1].get("at", "")):
        pr = e.get("pr") or ""
        if e.get("outcome") != "pr" or not pr.startswith(cfg.library_repo + "#"):
            continue  # a pull request it opened; not one it only named
        number = int(pr.split("#")[1])
        if only is not None and number != only:
            continue
        f = e.setdefault("follow", {"rounds": 0, "seen": []})
        if f.get("done"):
            continue
        s = read(gh.graphql, gh.rest, cfg.library_repo, number)
        if s.state == "MERGED":
            f["done"] = "merged"
            cfg.log(f"{pr}: merged")
        elif s.state == "CLOSED":
            f["done"] = "closed"
            e.setdefault("flag", f"its pull request {pr} was closed without merging")
            cfg.log(f"{pr}: closed without merging")
        else:
            w = needs(s, set(f["seen"]))
            if w is None:
                continue
            if f["rounds"] >= MAX_ROUNDS:
                f["done"] = "stopped"
                e["flag"] = f"{pr} still needs work after {MAX_ROUNDS} rounds: a person takes over"
                cfg.log(e["flag"])
            else:
                cfg.log(f"{pr}: {w.kind} ({w.key})")
                out = round_(s, w, e, reviews_by_id.get(item_id), client, tools, gh, state, cfg, system, today, areas,
                             dry=dry, work_fn=work_fn)
                done.append({"pr": pr, **out})
                if not dry:
                    f["rounds"] += 1
                    f["seen"] = (f["seen"] + [w.key])[-50:]
                    f["last"] = {k: v for k, v in out.items() if k != "flag"}
                    if out.get("flag"):
                        e["flag"] = out["flag"]
                cfg.log(f"{pr}: {out.get('outcome', out.get('would'))}, ${out.get('cost', 0):.2f}"
                        + (f", pushed {out['pushed'][:12]}" if out.get("pushed") else "")
                        + (f"; {out['flag']}" if out.get("flag") else ""))
        if not dry:
            state.save()
    return done


def system_prompt(here: Path) -> str:
    """`follow.md`, with the rules and the way of working of `prompt.md`, so that the two never differ."""
    base = (here / "prompt.md").read_text(encoding="utf-8")
    section = lambda title: re.search(rf"(## {re.escape(title)}\n.*?)(?=\n## |\Z)", base, re.S).group(1).strip()  # noqa: E731
    return (here / "follow.md").read_text(encoding="utf-8").replace("{rules}", section("Tau Ceti's rules (its CI and its reviewers enforce them)")) \
        .replace("{working}", section("Working"))
