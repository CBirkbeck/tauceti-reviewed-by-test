"""The standard review on the bulk issue: approvals, writes, edits and restores, read from the lines of a comment.

AI agents approve, write and edit a declaration's standard review (scripts/standard.py) in comments on the bulk
issue, issue #1, and the maintainers edit and restore it there, as themselves. A command is a line, its fields
apart at a spaced em dash ` — ` or ` -- `, the last field taking the rest of the line:

    Approve: <decl> — <version> — <cells>
    Write: <decl> — <cells>                          Write: <decl>                       (an agent; a maintainer)
    Edit: <decl> — <parent> — <cells> — <note>       Edit: <decl> — <parent> — <note>
    Dropped: <item> — <why>                          (after an Edit line, any number)
    Restore: <decl> — <earlier version> — <note>     (a maintainer)

A write or an edit gives its text in a block: a `~~~review` line, the text, and a `~~~` line. A review can hold
fences of its own, so the block closes at the last `~~~` line before the next command line, or before the end of
the comment; a command line in the text before its first `~~~` line is text too. Nothing in a block is a command,
so a `Test:` line in a review is no test. A block with no `~~~` line after it, or with another `~~~review` line
before one, is not closed: its command has no text, and the lines after it are read as they come.

A version is named by at least 8 leading hex digits of its hash, and stored in full. An approval or an edit names
the current version, so one made from a page that the store has moved past is refused, and the reply gives the
current version. A write is for a declaration with no standard review, an edit must pass `standard.check` against
the text it replaces, and a restore puts back an earlier text of the store, checked as a first version is. A
comment makes one change to a declaration's review, counting what any of its lines recorded: its lines share one
time, and two versions at one time would be ordered by their ids.

A line is decided as of its comment. Every run reads the whole issue again, and a line refused once is read again
each time; read against the store as it is now, it could go in late and unsaid, with its comment's time, once the
edit it missed is withdrawn or the version it named restored. So the store a line is read against holds only what
came before it: a record of a bulk line by its comment's time, that comment's id and its line, and any other record
or status by its time. A refusal then stays one on every run, unless something older than its comment reaches the
store only later, as the migration's records will.

An AI's write, edit and approval are accepts that carry the rubric's cells, and each supersedes its reviewer's
latest earlier accept of the declaration, as evidence-store's accepts do. A maintainer's write, edit or restore
approves nothing, so it is a comment: it replies to the version it replaces, or for a first version to the
declaration's latest yes, never to a no or a suggestion (a record with a reply is taken for answered), and with
no yes it is refused. People say yes with the page's form, never with `Approve:`.

The lines of evidence-store's own kinds (`Reviewed-by:`, `Test:`, `Named:`, `Challenge:`) are read as its bulk
handler reads them, into the same records. An AI agent's yes of the earlier form, without the standard review, is
recorded with a note on what agents do now, pointing to AI-REVIEWS.md in the repository the intake runs for, and a
bare one is refused with the approval to give instead; the review form's replies say the same (`process_issue`).

A comment's records are made whenever it is read, each added to the store at once so that later lines see it, and
none twice, since a record's origin names its comment and line. Every run reads the whole issue again, and
evidence-store said the refusals of every old comment again each time. So a reply ends with a hidden line naming the
comment it answers (`<!-- bulk-reply: <comment id> -->`), and a comment is answered while no reply of the bot names
it: one posted while a run was reading the issue is answered by the next, and one whose reply GitHub refused is
answered again, with what it recorded then. The bot's replies from before these lines name nothing, so no comment
older than the latest of them is answered again. `install` puts this module in place of evidence-store's reading,
for every run of its intake.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from evidence_core import records as rec
from evidence_store import cli, forms, intake
from evidence_store.intake import Context, Outcome

import standard

OURS = ("Approve", "Write", "Edit", "Restore")
#: A command line: ours, or evidence-store's. A block ends before the next one.
COMMAND = re.compile(r"^\s*(Approve|Write|Edit|Restore|Reviewed-by|Test|Named|Challenge)\s*:\s*(.*?)\s*$")
DROPPED = re.compile(r"^\s*Dropped\s*:\s*(.*?)\s*$")
OPEN, CLOSE = "~~~review", "~~~"
#: The fewest leading hex digits that name a version.
DIGITS = 8
HEX = re.compile(rf"[0-9a-f]{{{DIGITS},16}}")
#: Each command's line, by whether an AI agent gives it. A person's carries no cells: only an AI ticks.
FORMS = {("Approve", True): "Approve: <decl> — <version> — <cells>",
         ("Write", True): "Write: <decl> — <cells>",
         ("Write", False): "Write: <decl>",
         ("Edit", True): "Edit: <decl> — <parent> — <cells> — <note>",
         ("Edit", False): "Edit: <decl> — <parent> — <note>",
         ("Restore", False): "Restore: <decl> — <earlier version> — <note>"}
TEXT = "its text is missing: a `~~~review` line, the text, then a line `~~~`"
#: Where AI agents learn what they do now: AI-REVIEWS.md in the repository the intake runs for (`repo`).
APPROVE_INSTEAD = ("AI agents now approve or edit the declaration's standard review: AI-REVIEWS.md "
                   "(https://github.com/{repo}/blob/main/AI-REVIEWS.md).")
#: The note on recording an AI agent's yes of the earlier form.
EARLIER_FORM = ("Recorded as an AI agent's yes of the earlier form: it counts as an approval of an earlier version "
                "of the standard review. " + APPROVE_INSTEAD)
#: Where a record of a bulk line came from: its comment's id and the line, at the end of its origin's ref.
FROM_LINE = re.compile(r"(?:#issuecomment-|/comment/)(\d+)/line/(\d+)$")
#: The line a reply on the bulk issue ends with, for the comment it answers; and how a later run finds it.
ANSWERS = "<!-- bulk-reply: {} -->"
ANSWERED = re.compile(r"<!--\s*bulk-reply:\s*(\d+)\s*-->")
#: What evidence-core says of an AI agent's yes without its reasons, and what it is told now.
NEEDS_TEXT = "a review by an agent needs its text: why"
BARE_YES = ("an AI agent's yes is now an approval of the standard review: "
            "`Approve: <decl> — <version> — <cells>`, see AI-REVIEWS.md.")
#: evidence-store's own, kept before `install` puts ours in their place.
THEIR_PROCESS, THEIR_PROCESS_ISSUE = intake.process, intake.process_issue


@dataclass
class Command:
    """A command of a comment: the line it is on (from 1), its keyword, its fields, the `Dropped:` pairs after
    it, and the text of the block after it, if one is closed. Our commands' fields are split at every separator,
    the declaration first; evidence-store's are the declaration and the rest of the line, as its bulk handler
    reads them."""
    line: int
    keyword: str
    fields: list[str]
    dropped: list[tuple[str, str]] = field(default_factory=list)
    block: str | None = None


def command(k: int, line: str) -> Command | None:
    """The command on line `k`, if there is one."""
    m = COMMAND.match(line)
    if m is None:
        return None
    if m[1] in OURS:
        return Command(k, m[1], intake.FIELD_SEP.split(m[2]) if m[2] else [])
    theirs = intake.BULK_LINE.match(line)
    return Command(k, m[1], [theirs[2], (theirs[3] or "").strip()]) if theirs else None


def pair(rest: str) -> tuple[str, str]:
    """A `Dropped:` line's item, and its reason, which takes the rest of the line."""
    item, *why = intake.FIELD_SEP.split(rest, maxsplit=1)
    return item, why[0] if why else ""


def closing(lines: list[str], start: int) -> int | None:
    """The line that closes the block opened on line `start` (from 0), or None when it is not closed."""
    end = None
    for j in range(start + 1, len(lines)):
        line = lines[j].rstrip()
        if line == CLOSE:
            end = j
        elif end is None and line == OPEN:
            return None
        elif end is not None and COMMAND.match(line):
            break
    return end


def commands(text: str) -> list[Command]:
    """The commands of a comment, in order. The first block after a command is its text, taken whole with its
    own line breaks and normalized as its version is; the lines of a block are nobody's commands."""
    lines = (text or "").splitlines()
    whole = (text or "").splitlines(keepends=True)
    out: list[Command] = []
    owner = None
    k = 0
    while k < len(lines):
        if lines[k].rstrip() == OPEN:
            end = closing(lines, k)
            if owner is not None and end is not None:
                owner.block = standard.normalize("".join(whole[k + 1:end]))
            owner = None
            if end is not None:
                k = end + 1
                continue
        elif (cmd := command(k + 1, lines[k])) is not None:
            out.append(cmd)
            owner = cmd
        elif out and (m := DROPPED.match(lines[k])):
            out[-1].dropped.append(pair(m[1]))
        k += 1
    return out


def as_of(ctx: Context, at: str, comment: int, line: int) -> Context:
    """The context as it stood at line `line` of the comment with id `comment`, made at `at`: its store holds only the
    records that came before that line. A record of a bulk line comes before it by its comment's time, then that
    comment's id, then its line; any other record or status, by being older than the comment."""
    def before(r: dict) -> bool:
        ref = (r.get("origin") or {}).get("ref", "")
        m = FROM_LINE.search(ref) if "/line/" in ref else None
        return (r.get("at", ""), int(m[1]), int(m[2])) < (at, comment, line) if m else r.get("at", "") < at
    return replace(ctx, store=replace(ctx.store, records=[r for r in ctx.store.records if before(r)]))


def may(keyword: str, agent: bool, maintainer: bool) -> str:
    """Why the author of a comment may not give a command of ours; empty when they may."""
    if keyword == "Approve":
        return "" if agent else "only an AI agent approves the standard review: a person says yes with the page's form"
    if keyword == "Restore":
        return "" if maintainer and not agent else \
            "only a maintainer restores an earlier text, as a person (with no agent line); an AI agent edits it instead"
    return "" if agent or maintainer else ("only the maintainers write or edit the standard review as themselves; "
                                           "an AI agent says it is one in an agent line "
                                           "(`<!-- agent: tool=…; model=… -->`)")


def given(cmd: Command, form: str) -> dict[str, str] | None:
    """A command's fields by the names its form gives them; a note takes the rest of the line, and when it is left
    out the check asks for it. None when the line has too few fields, or too many for a line without a note."""
    names = [name.strip("<>") for name in form.split(": ", 1)[1].split(" — ")]
    noted = names[-1] == "note"
    if len(cmd.fields) < len(names) - noted or (len(cmd.fields) > len(names) and not noted):
        return None
    out = dict(zip(names, cmd.fields))
    if noted:
        out["note"] = " — ".join(cmd.fields[len(names) - 1:])
    return out


def named(version: str, versions: set[str]) -> set[str]:
    """The versions that `version`, at least `DIGITS` leading hex digits of a hash, names."""
    prefix = intake.clean(version).lower()
    return {v for v in versions if v.startswith(prefix)} if HEX.fullmatch(prefix) else set()


def current(ctx: Context, versions: list[dict]) -> dict | None:
    """The record of the current version, among a declaration's version records: the latest not withdrawn."""
    now = standard.current_version([standard.Seen(r, True, intake.current_state(ctx, r) == "withdrawn", False)
                                    for r in versions])
    return now.record if now else None


def restored(version: str, versions: list[dict], name: str, full: str) -> tuple[str | None, str]:
    """The earlier version a restore names, in full, among the declaration's versions; or why it names none."""
    found = named(version, {standard.version_of(r["text"]) for r in versions})
    if not found:
        return None, f"`{version}` names no version of the standard review of `{name}`; its current one is `{full}`"
    if len(found) > 1:
        return None, f"`{version}` names more than one version of the standard review of `{name}`: give more digits"
    earlier = found.pop()
    if earlier == full:
        return None, f"`{full}` is the current version of the standard review of `{name}` already"
    return earlier, ""


def supersedes(ctx: Context, name: str, by: dict) -> dict:
    """The `links` of a new accept by `by`, as evidence-store's `record_for` sets them: it supersedes its
    reviewer's latest earlier accept of the declaration."""
    earlier = [x for x in ctx.store.records if standard.is_accept(x)
               and (x.get("subject") or {}).get("name") == name and rec.same_reviewer(x.get("by", {}), by)]
    return {"links": {"supersedes": max(earlier, key=lambda x: x.get("at", ""))["id"]}} if earlier else {}


def ours(cmd: Command, by: dict, maintainer: bool, at: str, origin: dict, ctx: Context,
         changed: set[str]) -> tuple[dict | None, str]:
    """The record an `Approve:`, `Write:`, `Edit:` or `Restore:` line asks for, or why it cannot be made: an AI
    agent's accept, or a person's comment. `ctx` is as of the line (`as_of`), and `changed` holds the declarations
    whose review the comment changes in another line. Raises `DatasetMissing`, as evidence-store's `record_for`
    does."""
    agent = by["kind"] == "agent"
    refusal = may(cmd.keyword, agent, maintainer)
    if refusal:
        return None, refusal
    form = FORMS[cmd.keyword, agent]
    f = given(cmd, form)
    if f is None:
        return None, f"the line is `{form}`" + (", then its text" if cmd.keyword in ("Write", "Edit") else "")
    name = intake.clean(f["decl"])
    ds, decl = intake.lookup(ctx, name, "")
    if decl is None:
        return None, intake.not_found(name, ds)
    mine = [r for r in ctx.store.records if (r.get("subject") or {}).get("name") == name]
    versions = [r for r in mine if standard.kind_of(r) == "version"]
    now = current(ctx, versions)
    full = standard.version_of(now["text"]) if now else ""
    if cmd.keyword == "Write" and now:
        return None, f"`{name}` has a standard review already, `{full}`: approve it, or edit it"
    if cmd.keyword != "Write" and not now:
        return None, f"`{name}` has no standard review yet: write the first one"
    if cmd.keyword in ("Approve", "Edit"):
        version = f["version"] if cmd.keyword == "Approve" else f["parent"]
        if full not in named(version, {full}):
            return None, (f"`{version}` is not the current version of the standard review of `{name}`, which is "
                          f"`{full}`: read that text, then {cmd.keyword.lower()} it")
    rubric, exists = ctx.store.rubric, ds.by_name.__contains__
    cells, why = standard.cells(f["cells"], rubric.names) if agent else (None, "")
    problems = [why] if why else []
    if cmd.keyword == "Approve":
        text, s = f"Approves the standard review `{full}`.", {"approves": full}
    elif cmd.keyword == "Restore":
        earlier, why = restored(f["earlier version"], versions, name, full)
        if earlier is None:
            return None, why
        if not f["note"].strip():
            return None, "a restore says why: give a note"
        text = next(x["text"] for x in versions if standard.version_of(x["text"]) == earlier)
        s = {"parent": full, "restores": earlier, "note": f["note"]}
        problems += standard.check(text, exists=exists)
    elif cmd.block is None:
        return None, "; ".join(problems + [TEXT])
    elif cmd.keyword == "Write":
        text, s = cmd.block, {}
        problems += standard.check(text, exists=exists)
    else:
        text = cmd.block
        s = {"parent": full, "note": f["note"], "dropped": [{"item": item, "why": why} for item, why in cmd.dropped]}
        problems += standard.check(text, parent=now["text"], dropped=cmd.dropped, exists=exists, note=f["note"])
    if problems:
        return None, "; ".join(problems)
    if cmd.keyword != "Approve" and name in changed:
        return None, (f"this comment changes the standard review of `{name}` in another line, and a comment "
                      "changes it once")
    r = {"schema": rec.SCHEMA, "subject": rec.subject_from_decl(decl, ds), "by": by, "at": at, "origin": origin,
         "text": text, "standard": {"spec": standard.SPEC, **s}}
    if agent:
        r.update(kind="review", verdict="accept", rubric=rubric.name, checked=cells, **supersedes(ctx, name, by))
    else:
        # A comment replies to the version it replaces; a first version, to the declaration's latest yes: not to a no or
        # a suggestion, which the pages would take for answered by it.
        yeses = [x for x in mine if standard.is_accept(x)]
        target = now or max(yeses, key=lambda x: (x.get("at", ""), x.get("id", "")), default=None)
        if target is None:
            return None, (f"a maintainer's first version replies to a yes of `{name}`, and it has none yet "
                          "(a no or a suggestion is not one)")
        r.update(kind="comment", links={"replies_to": target["id"]})
    r = rec.with_id(r)
    errs = rec.validate(r, {rubric.name: rubric})
    return (None, "; ".join(errs)) if errs else (r, "")


def theirs(cmd: Command, by: dict, at: str, origin: dict, ctx: Context) -> tuple[dict | None, str]:
    """The record a line of evidence-store's own kinds asks for, as its bulk handler makes it, or why it cannot be
    made; an AI agent's bare yes is told what it is now."""
    kind, answers = intake.bulk_answers(cmd.keyword, *cmd.fields)
    r, errs = intake.record_for(kind, answers, by, at, origin, ctx)
    return r, "; ".join(BARE_YES if e == NEEDS_TEXT else e for e in errs)


def earlier_form(r: dict) -> bool:
    """Whether `r` is an AI agent's yes of the earlier form: an accept by an agent without `standard`. It counts as
    an approval of an earlier version of the standard review."""
    return standard.ai_accept(r) and "standard" not in r


def noted(text: str, r: dict, repo: str) -> str:
    """A reply on recording `r` for repository `repo`, with the note for an AI agent's yes of the earlier form."""
    return text + "\n\n" + EARLIER_FORM.format(repo=repo) if earlier_form(r) else text


def said(r: dict) -> str:
    """What a reply says of a record made: what it is to the standard review, or evidence-store's words."""
    kind = standard.kind_of(r)
    if kind is None:
        return intake.describe(r)
    name, who = r["subject"]["name"], rec.who(r["by"])
    if kind == "approval":
        version = r["standard"]["approves"]
        return f"Recorded the approval `{r['id']}` of the standard review `{version}` of `{name}`, by {who}."
    act = {"wrote": "written", "edited": "edited", "restored": "restored"}[standard.act(r)]
    version = standard.version_of(r["text"])
    return f"Recorded the standard review `{version}` of `{name}`, {act} by {who} (record `{r['id']}`)."


def reply(made: list[dict], refused: list[str], lines: int, comment: dict, repo: str) -> str:
    """One reply to a comment, worded as evidence-store's bulk handler words it: what was recorded and what was not.
    Then the note on the earlier form once, and the line naming the comment it answers."""
    msg = (f"Recorded {len(made)} of {lines} lines:\n\n" + "\n".join(f"- {said(r)}" for r in made)) if made else ""
    if refused:
        msg += ("\n\n" if msg else "") + "Not recorded:\n\n" + "\n".join(f"- {e}" for e in refused) + \
            "\n\nPost the corrected lines in a new comment."
    if any(map(earlier_form, made)):
        msg += "\n\n" + EARLIER_FORM.format(repo=repo)
    return msg + ("\n\n" + ANSWERS.format(comment["id"]) if comment.get("id") is not None else "")


def process_bulk_comment(comment: dict, issue: dict, ctx: Context, announce: bool = True) -> Outcome:
    """The records the commands of a comment on the bulk issue ask for, in order and each added to the store as it
    is made, and one reply: what was recorded, now or on an earlier run, and what was not and why."""
    out = Outcome()
    user = comment.get("user", {})
    if user.get("login") in intake.BOTS:
        return out
    base = comment.get("html_url") or f"{ctx.repo}#{issue['number']}/comment/{comment.get('id')}"
    text = comment.get("body") or ""
    by = intake.author_of(user, intake.parse_agent_mark(text))
    at = intake.iso(comment.get("created_at", ""))
    maintainer = intake.is_maintainer(ctx, comment)
    cmds = commands(text)
    made, refused = [], []
    changed = {r["subject"]["name"] for r in ctx.store.records if standard.kind_of(r) == "version"
               and (r.get("origin") or {}).get("ref", "").startswith(f"{base}/line/")}
    for cmd in cmds:
        ref = f"{base}/line/{cmd.line}"
        had = ctx.store.from_origin(ref)
        if had:
            made += had  # said again if the comment is answered now: the reply that said them was refused
            continue
        origin = {"kind": "comment", "ref": ref}
        then = as_of(ctx, at, int(comment.get("id") or 0), cmd.line)
        try:
            r, why = ours(cmd, by, maintainer, at, origin, then, changed) if cmd.keyword in OURS else \
                theirs(cmd, by, at, origin, then)
        except intake.DatasetMissing:
            refused.append(f"line {cmd.line}: there is no dataset of the library yet; it will be read again")
            continue
        if r is None:
            name = intake.clean(cmd.fields[0]) if cmd.fields else ""
            refused.append(f"line {cmd.line}" + (f" (`{name}`)" if name else "") + f": {why}")
            continue
        out.records.append(r)
        ctx.store.add([r])
        made.append(r)
        if standard.kind_of(r) == "version":
            changed.add(r["subject"]["name"])
    if announce and (made or refused):
        out.replies.append((issue["number"], reply(made, refused, len(cmds), comment, ctx.repo)))
    return out


def process(issue: dict, comments: list[dict], ctx: Context, announce: bool = True,
            events: list[dict] = ()) -> Outcome:
    """evidence-store's `process`, with the bulk issue read here: its comments in the order `as_of` reads them, by
    time and then id, each answered while no reply of the bot names it and it is newer than the bot's latest reply
    from before the replies named any."""
    if not intake.is_bulk(issue):
        return THEIR_PROCESS(issue, comments, ctx, announce, events)
    bots = [c for c in comments if (c.get("user") or {}).get("login") in intake.BOTS]
    answered = {n for c in bots for n in ANSWERED.findall(c.get("body") or "")}
    before = max((c.get("created_at", "") for c in bots if not ANSWERED.search(c.get("body") or "")), default="")
    out = Outcome()
    for c in sorted(comments, key=lambda c: (c.get("created_at", ""), int(c.get("id") or 0))):
        unanswered = str(c.get("id")) not in answered and c.get("created_at", "") > before
        out.merge(process_bulk_comment(c, issue, ctx, announce and unanswered))
    return out


def process_issue(issue: dict, ctx: Context, announce: bool = True) -> tuple[Outcome, dict | None]:
    """evidence-store's `process_issue`, saying what an AI agent's yes is now: the review form from an agent
    without its reasons is refused with the approval to give instead, and an AI agent's yes is recorded with the
    note on the earlier form."""
    out, r = THEIR_PROCESS_ISSUE(issue, ctx, announce)
    review = forms.kind_of(issue.get("labels", [])) == "review"
    made = r is not None and r in out.records

    def say(text: str) -> str:
        text = text.replace(NEEDS_TEXT, BARE_YES) if review else text
        return noted(text, r, ctx.repo) if made else text

    out.replies = [(n, say(text) if n == issue.get("number") else text) for n, text in out.replies]
    return out, r


def install() -> None:
    """Puts this module in place of evidence-store's reading: its command line's `process`, and the `process_issue`
    that its own `process` calls."""
    cli.process = process
    intake.process_issue = process_issue
