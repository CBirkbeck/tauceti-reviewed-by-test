#!/usr/bin/env python3
"""The pull request that addresses a no or a suggestion: `/addressed <pull request>` on its issue, and the pull
request that `/fixed` and `/answered` can name.

A no (a review answering no) or a suggestion (What could be better, a review on the question form) is often
settled by a pull request. Its author or a maintainer (an AI agent through a maintainer's account too) says which,
in a comment on its issue whose first line is one of

  /addressed TauCetiProject/TauCeti#123 — what it changes
  /addressed https://github.com/TauCetiProject/TauCeti/pull/123
  /addressed TauCeti#123                       (the library's name alone, short for its repository)

and intake records it by where the pull request stands when it reads the comment:

- a pull request to the library that has merged (Bors squashes it into one commit on `main`, whose subject ends
  `(#123)`, and closes it): the no is fixed, the suggestion answered, at that commit, and the status names the
  pull request. The issue closes.
- one to the library still open: the link is recorded, as a reply naming the pull request, and the issue stays
  as it is. The scheduled intake looks again every six hours (`follow`): once it has merged, the status is
  recorded as above, by whoever linked it, and the issue closes; closed without merging, intake says so on the
  issue, once, and the link stops counting.
- one to another repository (Mathlib's, say): the link is recorded, and the no stays open until someone comments
  `/fixed <commit> <pull request>` once the library includes the fix, as the answerer does for the fixes it
  proposed upstream.
- not a pull request, or one closed without merging: nothing but the comment is recorded, as a reply, and intake
  says why.

`/fixed [commit] <pull request>` and `/answered <pull request>` record the pull request with the status, as given.
The site shows it with the no or the suggestion: Fixed by TauCeti#123, Fix proposed in TauCeti#123.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

from evidence_core import records as rec
from evidence_core.store import Store
from evidence_store import github, intake
from evidence_store.intake import Context, Outcome

from common import load_settings

sys.path.append(str(Path(__file__).resolve().parents[1]))  # last, so that nothing in the repository shadows a module
from answerer.pulls import squashed_commit  # noqa: E402  (how a pull request merged through Bors is found)

#: A pull request as a link, and in GitHub's shorthand: `owner/repo#123`, or a name alone, `TauCeti#123`.
URL = re.compile(r"https://github\.com/([\w.-]+/[\w.-]+?)/pull/(\d+)")
SHORT = re.compile(r"(?<![\w/#])([\w.-]+/[\w.-]+|[\w.-]+)#(\d+)\b")
#: Names that stand for a repository other than the library's.
NAMES = {"mathlib": "leanprover-community/mathlib4", "mathlib4": "leanprover-community/mathlib4"}
#: A comment whose first line is one of these commands, which may name a pull request.
COMMAND = re.compile(r"^/(addressed|fixed|answered)\b\s*(.*)$")
COMMIT = re.compile(r"^([0-9a-f]{7,40})\b\s*(.*)$", re.S)
#: What a pull request that addresses it makes of a no, and of a suggestion.
STATE_OF = {"problem": "fixed", "question": "answered"}
WHAT_OF = {"problem": "no", "question": "suggestion"}
#: The text of a link given without a note of its own.
BARE = "Addressed in {pr}."
NAME_IT = ("`/addressed` needs the pull request after it: `/addressed TauCetiProject/TauCeti#123`, or its link "
           "(a bare `#123` would be an issue of this repository)")
#: The mark of intake's reply that a linked pull request closed without merging, so that it says so once.
CLOSED_MARK = "<!-- pr-link-closed: {link} -->"


def library() -> str:
    """The library's repository, `owner/name`, as the site's settings give it."""
    return load_settings()["library"]["repo"]


def pull_ref(token: str, lib: str) -> str | None:
    """The pull request `token` names, as `owner/repo#123`; None if it names none."""
    m = URL.search(token)
    if m:
        return f"{m.group(1)}#{m.group(2)}"
    m = SHORT.search(token)
    if not m:
        return None
    repo, number = m.group(1), m.group(2)
    if "/" not in repo:
        if repo.lower() == lib.split("/")[1].lower():
            repo = lib
        elif repo.lower() in NAMES:
            repo = NAMES[repo.lower()]
        else:
            return None
    return f"{repo}#{number}"


def parse(text: str, lib: str) -> tuple[str, str, str, str] | None:
    """`(command, commit, pull request, note)` of a comment whose first line is `/addressed`, or `/fixed` or
    `/answered` naming a pull request; None for any other comment, which evidence-store reads as it always has."""
    lines = intake.REVIEWED_BY_MARK.sub("", intake.AGENT_MARK.sub("", text or "")).strip().splitlines()
    if not lines:
        return None
    m = COMMAND.match(lines[0].strip())
    if not m:
        return None
    name, rest, commit = m.group(1), m.group(2).strip(), ""
    if name == "fixed":
        cm = COMMIT.match(rest)
        if cm:
            commit, rest = cm.group(1), cm.group(2).strip()
    if name == "addressed":
        rest = re.sub(r"^by\b\s*", "", rest)
    words = rest.split(None, 1)
    pr = pull_ref(words[0], lib) if words else None
    if pr is None and name != "addressed":
        return None
    after = (words[1] if len(words) > 1 else "") if pr else rest
    note = "\n".join([after.lstrip("—–-: ").strip()] + lines[1:]).strip()
    return name, commit, pr or "", note


def pr_url(pr: str) -> str:
    repo, number = pr.split("#")
    return f"https://github.com/{repo}/pull/{number}"


def pr_text(pr: str) -> str:
    """A pull request as a reply names it: `[TauCeti#123](its link)`."""
    repo, number = pr.split("#")
    return f"[{repo.split('/')[1]}#{number}]({pr_url(pr)})"


def run(argv: list[str]) -> str:
    return subprocess.run(argv, capture_output=True, text=True, check=True, timeout=120).stdout


def lookup(pr: str, gh: Callable[[list[str]], str] = run) -> dict:
    """Where a pull request stands: `{state, sha, at}`, `state` one of MERGED, OPEN, CLOSED (without merging),
    MISSING (GitHub knows no such pull request) or UNKNOWN (GitHub could not be asked). One merged through Bors is
    closed on GitHub, and its commit found on the default branch (`answerer.pulls.squashed_commit`); `sha` is empty
    when it cannot be found."""
    repo, number = pr.split("#")
    try:
        out = json.loads(gh(["gh", "pr", "view", number, "--repo", repo, "--json",
                             "state,mergeCommit,mergedAt,closedAt,title"]))
    except subprocess.CalledProcessError as e:
        said = (e.stderr or "") + (e.stdout or "")
        return {"state": "MISSING" if re.search(r"could not resolve|not found", said, re.I) else "UNKNOWN",
                "sha": "", "at": ""}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {"state": "UNKNOWN", "sha": "", "at": ""}
    state, sha = out.get("state", "UNKNOWN"), (out.get("mergeCommit") or {}).get("oid") or ""
    at = intake.iso(out.get("mergedAt") or out.get("closedAt") or "")
    if state == "CLOSED" and out.get("closedAt"):
        try:
            branch = gh(["gh", "api", f"repos/{repo}", "--jq", ".default_branch"]).strip() or "main"
            sha = squashed_commit(gh, repo, int(number), out["closedAt"], branch) or ""
        except (subprocess.SubprocessError, OSError, ValueError):
            return {"state": "UNKNOWN", "sha": "", "at": ""}
        if sha or (out.get("title") or "").startswith("[Merged by Bors]"):
            state = "MERGED"
    return {"state": state, "sha": sha, "at": at}


def status(target: dict, state: str, by: dict, at: str, origin: dict, note: str = "", commit: str = "",
           pr: str = "") -> dict:
    """A status of `target` that names the pull request `pr` (and the commit it merged as)."""
    r = {"schema": rec.SCHEMA, "kind": "status", "target": target["id"], "state": state, "by": by, "at": at,
         "origin": origin}
    if note:
        r["text"] = note
    if commit:
        r["commit"] = commit
    if pr:
        r["pr"] = pr
    return rec.with_id(r)


def link(target: dict, pr: str, by: dict, at: str, origin: dict, note: str) -> dict:
    """The link of `target` to the pull request `pr`, still open or outside the library: a reply naming it."""
    return rec.with_id({"schema": rec.SCHEMA, "by": by, "at": at, "origin": origin, "kind": "comment",
                        "text": note or BARE.format(pr=pr), "links": {"replies_to": target["id"]}, "pr": pr,
                        **({"subject": target["subject"]} if target.get("subject") else {})})


THEIR_PROCESS_COMMENT = intake.process_comment


def process_comment(comment: dict, issue: dict, target: dict, ctx: Context, announce: bool = True,
                    look: Callable[[str], dict] = lookup) -> Outcome:
    """evidence-store's `process_comment`, with `/addressed` and the pull request `/fixed` and `/answered` can name
    read here; every other comment is evidence-store's to read."""
    user = comment.get("user") or {}
    lib = library()
    cmd = None if user.get("login") in intake.BOTS else parse(comment.get("body") or "", lib)
    if cmd is None:
        return THEIR_PROCESS_COMMENT(comment, issue, target, ctx, announce)
    ref = comment.get("html_url") or f"{ctx.repo}#{issue['number']}/comment/{comment.get('id')}"
    if ctx.store.from_origin(ref):
        return Outcome()
    name, commit, pr, note = cmd
    what = rec.target_kind(target)
    if name == "addressed" and what not in STATE_OF:
        state, refusal = None, f"`/addressed` is for a no or a suggestion, and this is {intake.WHAT_OF.get(what, what)}"
    else:
        state, refusal = intake.decide(ctx, target, STATE_OF[what] if name == "addressed" else name,
                                       user.get("login", ""), comment.get("author_association", ""))
    if state is not None and name == "addressed" and not pr:
        state, refusal = None, NAME_IT
    if state is None:
        if name != "addressed":
            return THEIR_PROCESS_COMMENT(comment, issue, target, ctx, announce)  # it says why itself
        out = THEIR_PROCESS_COMMENT(comment, issue, target, ctx, announce)  # kept as a reply
        if announce:
            out.replies.insert(0, (issue["number"], f"Not recorded: {refusal}. The comment is kept as a reply."))
        return out
    text = comment.get("body") or ""
    by = intake.author_of(user, intake.parse_agent_mark(text))
    at = intake.iso(comment.get("created_at", ""))
    origin = {"kind": "comment", "ref": ref}
    n, out, who = issue["number"], Outcome(), rec.who(by)
    if name != "addressed":  # `/fixed` or `/answered` naming a pull request: recorded as given
        r = status(target, state, by, at, origin, note, commit, pr)
        out.records.append(r)
        at_commit = f" (`{commit[:12]}`)" if commit else ""
        out.replies.append((n, f"Recorded: `{target['id']}` is now **{intake.LABEL_OF[state]}**{at_commit} by "
                               f"{pr_text(pr)}, by {who}."))
        intake.on_target_issue(out, n, state)
        return out
    ours = pr.split("#")[0].lower() == lib.lower()
    stands = look(pr)
    if not ours and stands["state"] not in ("CLOSED", "MISSING"):
        stands = {**stands, "state": "LINK"}  # another repository's, merged or not: linked, for a person to settle
    if stands["state"] in ("CLOSED", "MISSING"):
        why = (f"{pr_text(pr)} was closed without merging" if stands["state"] == "CLOSED"
               else f"{pr_text(pr)} is not a pull request GitHub knows")
        out = THEIR_PROCESS_COMMENT(comment, issue, target, ctx, announce)
        if announce:
            out.replies.insert(0, (n, f"Not recorded: {why}. The comment is kept as a reply."))
        return out
    if stands["state"] == "MERGED":
        r = status(target, state, by, at, origin, note, stands["sha"], pr)
        out.records.append(r)
        merged = f" (merged as `{stands['sha'][:12]}`)" if stands["sha"] else " (merged)"
        out.replies.append((n, f"Recorded: `{target['id']}` is now **{intake.LABEL_OF[state]}** by {pr_text(pr)}"
                               f"{merged}, by {who}."))
        intake.on_target_issue(out, n, state)
        return out
    r = link(target, pr, by, at, origin, note)
    out.records.append(r)
    kind = WHAT_OF[what]
    if ours:
        then = (f"It has not merged yet: once it does, this {kind} is recorded as **{intake.LABEL_OF[state]}** by it "
                f"and the issue closes. Intake looks every six hours.")
    else:
        then = (f"This {kind} stays as it is until a maintainer comments `/{'fixed <commit>' if state == 'fixed' else 'answered'}"
                f" {pr}` once {load_settings()['library']['name']} includes the change.")
    out.replies.append((n, f"Recorded: {who} links `{target['id']}` to {pr_text(pr)}. {then}"))
    return out


def follow(repo: str, store: Store, lib: str, look: Callable[[str], dict] = lookup,
           comments: Callable[[str, int], list[dict]] = github.comments) -> Outcome:
    """Each no or suggestion whose latest word is a link to one of the library's pull requests, looked at again: once
    it has merged, its status, as `/addressed` records it for one merged already, by whoever linked it, and its issue
    closed; closed without merging, intake says so on the issue, once, and the link stops counting. Statuses of the
    no or suggestion after its link (a decision since, a withdrawal) leave it alone."""
    out = Outcome()
    by_id = {r["id"]: r for r in store.records}
    statuses: dict[str, list[dict]] = {}
    latest: dict[str, dict] = {}
    for r in sorted(store.records, key=lambda r: (r.get("at", ""), r.get("id", ""))):
        if r.get("kind") == "status":
            statuses.setdefault(r.get("target", ""), []).append(r)
        elif r.get("kind") == "comment" and r.get("pr") and (r.get("links") or {}).get("replies_to") in by_id:
            latest[r["links"]["replies_to"]] = r
    for target_id, ln in sorted(latest.items()):
        target, pr = by_id[target_id], ln["pr"]
        state = STATE_OF.get(rec.target_kind(target))
        if state is None or pr.split("#")[0].lower() != lib.lower():
            continue
        said = statuses.get(target_id, [])
        if any(s.get("pr") == pr for s in said) or any(s.get("at", "") >= ln.get("at", "") for s in said):
            continue
        stands = look(pr)
        n = intake.issue_number(target, repo)
        if stands["state"] == "MERGED":
            at = max(ln.get("at", ""), stands["at"] or "")
            merged = f"merged as `{stands['sha'][:12]}`" if stands["sha"] else "merged"
            r = status(target, state, ln["by"], at, {"kind": "pull", "ref": pr_url(pr)},
                       f"{pr_text(pr)} {merged}.", stands["sha"], pr)
            store.add([r])
            out.records.append(r)
            if n:
                out.replies.append((n, f"Recorded: `{target_id}` is now **{intake.LABEL_OF[state]}** by {pr_text(pr)} "
                                       f"({merged}), as {rec.who(ln['by'])} linked it."))
                intake.on_target_issue(out, n, state)
        elif stands["state"] == "CLOSED" and n:
            mark = CLOSED_MARK.format(link=ln["id"])
            if not any(mark in (c.get("body") or "") for c in comments(repo, n)):
                out.replies.append((n, f"{pr_text(pr)} was closed without merging, so it no longer addresses "
                                       f"`{target_id}`. Link another with `/addressed <pull request>`.\n\n{mark}"))
    return out


def follow_into(repo: str, store_dir: str, outcome_file: str, look: Callable[[str], dict] = lookup,
                comments: Callable[[str, int], list[dict]] = github.comments) -> int:
    """Runs `follow` after an intake run and adds what it did to the run's outcome file. Returns the records added."""
    out = follow(repo, Store.load(store_dir), library(), look, comments)
    path = Path(outcome_file)
    outcome = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    done = out.as_json()
    outcome["records"] = outcome.get("records", []) + done["records"]
    for key in ("replies", "close", "reopen", "labels", "reactions"):
        outcome[key] = outcome.get(key, []) + done[key]
    path.write_text(json.dumps(outcome, indent=1), encoding="utf-8")
    if out.records:
        print(f"intake: {len(out.records)} linked pull requests merged")
    return len(out.records)
