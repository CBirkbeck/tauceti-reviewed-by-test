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
declaration's records are those evidence-core puts on it, as the page reads them (`records_of`): by its name, or by
its meaning hash once it is renamed, and a comment where the record it replies to went. A comment makes one change to
a declaration's review, counting what any of its lines recorded on the declaration as the page reads it: its lines
share one time, and evidence-core orders records of one time by their ids.

A line is decided once, as of its comment. The store it is read against holds only what came before it, by
`standard.order`, as the current version is chosen: a record of a line of a comment by that comment's time, its id
and the line, and any other record by its time, before the lines of its second; a status, which that order does not
place among them, only when it is older than the comment. A comment is answered once a reply of the bot names it,
or when it is older than the bot's latest reply from before the replies named any, and a line refused in a comment
answered is not read again: its refusal is final, however the store or the library moves on. Two refusals wait
instead: a line read when there was no dataset of the library, and one whose declaration the latest dataset lacks,
which may be one the dataset is yet to be built with (refused with the dataset's nearest names, so that a typo is
said once). The reply names them in its closing line, `<!-- bulk-reply: <comment id> deferred: <k>,<k> -->`, and
later runs read those lines again, as of their comment: a line now recorded, or refused for good, is said in a new
reply to the comment, whose closing line names the lines that still wait; and so is a line read without a dataset
that now waits for its declaration, since what it lacks was never said (`UNREAD`).

An AI's write, edit and approval are accepts that carry the rubric's cells, and each supersedes its reviewer's
latest earlier accept of the declaration, as evidence-store's accepts do, among the records the page puts on it, so
that one made after a rename supersedes the reviewer's accept under the old name. A maintainer's write, edit or
restore approves nothing, so it is a comment: it replies to the version it replaces, or for a first version to the
declaration's latest yes, never to a no or a suggestion (a record with a reply is taken for answered), and with no
yes it is refused. People say yes with the page's form, never with `Approve:`.

The agent a comment names is read from its lines outside the review blocks, the lines of its commands and its
`Dropped:` lines (`naming`): a review, a note or a reason that quotes a mark names no one, where evidence-store's
`parse_agent_mark`, given the whole comment, would take the reviewed-by form wherever it is. A comment whose mark is
only on the line of a command or of a `Dropped:` item, as `Reviewed-by: X — reasons <!-- agent: … -->`, has every line
refused, and nothing of it recorded (`misplaced`): its author meant an agent, and read as no agent's, its records would
be the account's own, as a person's, for good. The reply asks for the agent line on a line of its own.

The lines of evidence-store's own kinds (`Reviewed-by:`, `Test:`, `Named:`, `Challenge:`) are read as its bulk
handler reads them, into the same records. An AI agent's yes of the earlier form, without the standard review, is
recorded with a note on what agents do now, pointing to AI-REVIEWS.md in the repository the intake runs for, and a
bare one is refused with the approval to give instead, in a comment on the bulk issue, linked; the review form's
replies say the same (`process_issue`), with the bulk issue the site's settings name.

A comment's records are made whenever it is read, each added to the store at once so that later lines see it, and
none twice, since a record's origin names its comment and line; a run finds a line's records in a map of the store by
origin that it makes once (`origins`). It looks the latest dataset up once too, a failure included (`latest_once`):
every line of a run is decided against one outcome, and a line waiting for a declaration is looked up before the store
is read as of its comment, so it costs neither a request nor a pass over the store. Every run is given the whole issue
again, and evidence-store read all of it, saying the refusals of every old comment again each time. So a reply ends with
a hidden line naming the comment it answers (`marker`), and a comment is read whole while no reply of the bot names it
in its closing lines (a reply quotes what it was given, so a marker anywhere else names nothing): one posted while a
run was reading the issue is answered by the next, and one whose reply GitHub refused is answered again, with what it
recorded then. An answered comment is read again only for the lines its latest reply deferred. The bot's replies from
before these lines name nothing, so no comment older than the latest of them is read again. A reply holds what fits in
a comment (`CAP`), a reason given once for all the lines it refused: GitHub refuses a comment over 65,536 characters,
and the reply to the oldest comment unanswered is made first on every run. `install` puts this module in place of
evidence-store's reading, for every run of its intake.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from functools import partial
from typing import Callable, Sequence

from evidence_core import records as rec
from evidence_core.dataset import Dataset, Decl
from evidence_core.status import classify
from evidence_store import cli, forms, intake
from evidence_store.intake import Context, Outcome

import standard
from common import load_settings

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
#: Why each line of a comment is refused whose agent mark is only on a command or `Dropped:` line (`misplaced`).
MISPLACED = ("the comment's agent mark is on the line of a command or of a `Dropped:` item, where it names no one: put "
             "the agent line on a line of its own, `<!-- agent: tool=…; model=… -->`")
#: What a reply says of a line read when there was no dataset of the library: it waits, and is read again.
NO_DATASET = "there is no dataset of the library yet; it will be read again"
#: A row of a reply that says so (`refusals`): for one line, or as the reason given for the lines after it. A row of a line
#: that names a declaration reads `- line k (`…`)`, so no text a reply quotes makes one.
UNREAD = re.compile(rf"^- (?:line \d+: )?{re.escape(NO_DATASET)}$", re.M)
#: Where AI agents learn what they do now: AI-REVIEWS.md in the repository the intake runs for (`repo`).
APPROVE_INSTEAD = ("AI agents now approve or edit the declaration's standard review: AI-REVIEWS.md "
                   "(https://github.com/{repo}/blob/main/AI-REVIEWS.md).")
#: The note on recording an AI agent's yes of the earlier form.
EARLIER_FORM = ("Recorded as an AI agent's yes of the earlier form: it counts as an approval of an earlier version "
                "of the standard review. " + APPROVE_INSTEAD)
#: The most characters a reply holds, as a comment of ours does (review_site.py's COMMENT_CAP): GitHub refuses one over
#: 65,536.
CAP = 60_000
#: The line a reply on the bulk issue ends with (`marker`), as a later run finds it among the reply's closing lines
#: (`answered`): the comment it answers, and the lines of it that wait, to be read again.
ANSWERED = re.compile(r"<!--\s*bulk-reply:\s*(\d+)(?:\s+deferred:\s*(\d+(?:\s*,\s*\d+)*))?\s*-->")
#: What evidence-core says of an AI agent's yes without its reasons, and what it is told now: the approval to give, in
#: a comment on the bulk issue (`bulk`, issue #1 on the site) of the repository the intake runs for (`repo`).
NEEDS_TEXT = "a review by an agent needs its text: why"
BARE_YES = ("an AI agent's yes is now an approval of the standard review: the line "
            "`Approve: <decl> — <version> — <cells>` in a comment on issue #{bulk} "
            "(https://github.com/{repo}/issues/{bulk}), see AI-REVIEWS.md.")
#: evidence-store's own, kept before `install` puts ours in their place.
THEIR_PROCESS, THEIR_PROCESS_ISSUE = intake.process, intake.process_issue


class NotInDataset(LookupError):
    """A line whose declaration the latest dataset of the library does not have: refused with the dataset's nearest
    names, and read again on later runs, since it may be one the dataset is yet to be built with."""


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
    bulk = intake.BULK_LINE.match(line)
    return Command(k, m[1], [bulk[2], (bulk[3] or "").strip()]) if bulk else None


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


def outside(text: str) -> list[str]:
    """The lines of a comment in no review block (`closing`)."""
    lines = (text or "").splitlines()
    out: list[str] = []
    k = 0
    while k < len(lines):
        end = closing(lines, k) if lines[k].rstrip() == OPEN else None
        if end is not None:
            k = end + 1
            continue
        out.append(lines[k])
        k += 1
    return out


def naming(text: str) -> str:
    """The lines of a comment that can name its agent: those in no review block (`outside`), and no line of a command or
    of a `Dropped:` item. A review's text, an edit's note and the reason for a dropped item are words about a declaration,
    and may quote a mark. evidence-store's `parse_agent_mark` takes the reviewed-by form wherever it is in what it is
    given, so over the whole comment it would credit the comment to the agent that text names."""
    return "\n".join(line for line in outside(text) if not (COMMAND.match(line) or DROPPED.match(line)))


def misplaced(text: str) -> bool:
    """Whether a comment's agent mark is only on the line of a command or of a `Dropped:` item, as at the end of
    `Reviewed-by: X — reasons <!-- agent: … -->`: there is a mark outside the review blocks, and none on the lines that
    can name the comment's agent (`naming`). Its author meant an agent, but read by `naming` the comment would be the
    account's own, as a person's, and its records would say so for good: its lines are refused instead (`MISPLACED`)."""
    return intake.parse_agent_mark(naming(text)) is None and \
        intake.parse_agent_mark("\n".join(outside(text))) is not None


def as_of(ctx: Context, at: str, comment: int, line: int) -> Context:
    """The context as it stood at line `line` of the comment with id `comment`, made at `at`: its store holds only the
    records before that line by `standard.order`, the order the current version is chosen by, so that the two agree on
    records made in one second. A status, which that order does not place among the lines of its second, counts only
    when it is older than the comment."""
    here = (at, comment, line)

    def before(r: dict) -> bool:
        return r.get("at", "") < at if r.get("kind") == "status" else standard.order(r)[:3] < here
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
    with_note = names[-1] == "note"
    if len(cmd.fields) < len(names) - with_note or (len(cmd.fields) > len(names) and not with_note):
        return None
    out = dict(zip(names, cmd.fields))
    if with_note:
        out["note"] = " — ".join(cmd.fields[len(names) - 1:])
    return out


def named(version: str, versions: set[str]) -> set[str]:
    """The versions that `version`, at least `DIGITS` leading hex digits of a hash, names."""
    prefix = intake.clean(version).lower()
    return {v for v in versions if v.startswith(prefix)} if HEX.fullmatch(prefix) else set()


def placing(ids: dict[str, dict], ds: Dataset) -> Callable[[dict], str | None]:
    """Where evidence-core puts each record of a store, whose records by id are `ids` (`Evidence.resolve`), and so
    where the page shows it: the name of a declaration of `ds`, or None. A record goes by its subject
    (`status.classify`): by its name, or by its meaning hash once it is renamed. A comment goes where the record it
    replies to went, when that record came before it, by time and then id as evidence-core reads them, and went
    somewhere; else by its own subject. A status, and a record evidence-core cannot read, go nowhere."""
    memo: dict[str, str | None] = {}

    def on(r: dict) -> str | None:
        if r.get("id") not in memo:
            memo[r.get("id")] = place(r)
        return memo[r.get("id")]

    def place(r: dict) -> str | None:
        if not rec.readable(r) or r.get("kind") == "status":
            return None
        if r.get("kind") == "comment":
            target = ids.get((r.get("links") or {}).get("replies_to"))
            if target is not None and (target.get("at", ""), target.get("id", "")) < (r.get("at", ""), r.get("id", "")):
                name = on(target)
                if name is not None:
                    return name
            if not r.get("subject"):
                return None
        decl = classify(r.get("subject") or {}, ds).decl
        return decl.name if decl is not None else None
    return on


def records_of(ctx: Context, ds: Dataset, decl: Decl) -> list[dict]:
    """The records about a declaration: those evidence-core puts on it (`placing`), and so those the page reads. Only a
    record whose subject has the declaration's name or meaning hash, or for a comment the subject of a record it replies
    to, in turn, can be on it, so only those are placed."""
    records = ctx.store.records
    ids = {r.get("id"): r for r in records}
    on = placing(ids, ds)

    def might(r: dict) -> bool:
        subject = r.get("subject") or {}
        return subject.get("name") == decl.name or bool(decl.meaning) and \
            (subject.get("hashes") or {}).get("meaning") == decl.meaning

    def thread(r: dict):
        """The comment, the record it replies to, the record that one replies to, and so on."""
        seen = set()
        while r is not None and r.get("id") not in seen:
            yield r
            seen.add(r.get("id"))
            r = ids.get((r.get("links") or {}).get("replies_to")) if r.get("kind") == "comment" else None

    out = []
    for r in records:
        if r.get("kind") == "comment":
            if not any(might(x) for x in thread(r)):
                continue
        elif not might(r):
            continue
        if on(r) == decl.name:
            out.append(r)
    return out


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


def supersedes(mine: list[dict], by: dict) -> dict:
    """The `links` of a new accept by `by` of a declaration whose records are `mine` (`records_of`), as evidence-store's
    `record_for` sets them: it supersedes its reviewer's latest earlier accept of the declaration (`standard.order`).
    They are chosen among the records the page puts on the declaration, so that after a rename the new accept supersedes
    one under the old name, and the page counts its reviewer once."""
    earlier = [x for x in mine if standard.is_accept(x) and rec.same_reviewer(x.get("by", {}), by)]
    return {"links": {"supersedes": max(earlier, key=standard.order)["id"]}} if earlier else {}


def ours(cmd: Command, by: dict, maintainer: bool, at: str, origin: dict, ctx: Context,
         changed: Callable[[Dataset, Decl], bool], view: Callable[[], Context]) -> tuple[dict | None, str]:
    """The record an `Approve:`, `Write:`, `Edit:` or `Restore:` line asks for, or why it cannot be made: an AI
    agent's accept, or a person's comment. The declaration is looked up in `ctx` first, and only one the latest dataset
    has is read against the store, as of the line (`view`, which makes `as_of`'s context): a line waiting for a declaration
    costs no pass over the store. `changed` says whether the comment changes a declaration's review in another line.
    Raises `DatasetMissing`, as evidence-store's `record_for` does, and `NotInDataset` for a declaration the latest dataset
    does not have."""
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
        if name:
            raise NotInDataset(intake.not_found(name, ds))
        return None, intake.not_found(name, ds)  # no dataset will have it
    ctx = view()
    mine = records_of(ctx, ds, decl)
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
    if cmd.keyword != "Approve" and changed(ds, decl):
        return None, (f"this comment changes the standard review of `{name}` in another line, and a comment "
                      "changes it once")
    r = {"schema": rec.SCHEMA, "subject": rec.subject_from_decl(decl, ds), "by": by, "at": at, "origin": origin,
         "text": text, "standard": {"spec": standard.SPEC, **s}}
    if agent:
        r.update(kind="review", verdict="accept", rubric=rubric.name, checked=cells, **supersedes(mine, by))
    else:
        # A comment replies to the version it replaces; a first version, to the declaration's latest yes: not to a no or
        # a suggestion, which the pages would take for answered by it.
        yeses = [x for x in mine if standard.is_accept(x)]
        target = now or max(yeses, key=standard.order, default=None)
        if target is None:
            return None, (f"a maintainer's first version replies to a yes of `{name}`, and it has none yet "
                          "(a no or a suggestion is not one)")
        r.update(kind="comment", links={"replies_to": target["id"]})
    r = rec.with_id(r)
    errs = rec.validate(r, {rubric.name: rubric})
    return (None, "; ".join(errs)) if errs else (r, "")


def theirs(cmd: Command, by: dict, at: str, origin: dict, ctx: Context, bulk: int,
           view: Callable[[], Context]) -> tuple[dict | None, str]:
    """The record a line of evidence-store's own kinds asks for, as its bulk handler makes it, or why it cannot be
    made; an AI agent's bare yes is told what it is now, an approval on the bulk issue, number `bulk`. As in `ours`, the
    declaration is looked up in `ctx` before the store is read as of the line (`view`). Raises `DatasetMissing`, and
    `NotInDataset` for a declaration the latest dataset does not have."""
    kind, answers = intake.bulk_answers(cmd.keyword, *cmd.fields)
    name = intake.clean(answers.get("decl"))
    if name:
        ds, decl = intake.lookup(ctx, name, "")
        if decl is None:
            raise NotInDataset(intake.not_found(name, ds))
        # record_for looks the declaration up again, in the latest dataset (a bulk line names no commit): this one.
        dataset = ctx.dataset
        ctx = replace(view(), dataset=lambda commit: dataset(commit) if commit else ds)
    r, errs = intake.record_for(kind, answers, by, at, origin, ctx)
    instead = BARE_YES.format(repo=ctx.repo, bulk=bulk)
    return r, "; ".join(instead if e == NEEDS_TEXT else e for e in errs)


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


def where(line: int, name: str) -> str:
    """A line of a comment as a reply names it: its number, and the declaration it names, if any."""
    return f"line {line}" + (f" (`{name}`)" if name else "")


def refusals(refused: list[tuple[int, str, str]]) -> list[tuple[str, int]]:
    """The rows of a reply that say what was not recorded, from each (line, declaration, reason), each row with how many
    lines it names. A reason given for one line follows it; one given for more is said once, the lines after it."""
    lines: dict[str, list[tuple[int, str]]] = {}
    for line, name, why in refused:
        lines.setdefault(why, []).append((line, name))
    rows = []
    for why, these in lines.items():
        if len(these) == 1:
            rows.append((f"- {where(*these[0])}: {why}", 1))
        else:
            rows += [(f"- {why}", 0)] + [(f"  - {where(*x)}", 1) for x in these]
    return rows


def fit(rows: list[tuple[str, int]], room: int) -> tuple[list[str], int]:
    """The first of `rows` that fit in `room` characters, each with its line break, and how many lines or records the
    rest name. A reason is not shown without a line it was given for."""
    shown: list[tuple[str, int]] = []
    for row in rows:
        room -= len(row[0]) + 1
        if room < 0:
            break
        shown.append(row)
    while shown and not shown[-1][1]:
        shown.pop()
    return [text for text, _ in shown], sum(n for _, n in rows) - sum(n for _, n in shown)


def marker(comment: int | str, deferred: Sequence[int] = ()) -> str:
    """The line a reply on the bulk issue ends with: the comment it answers, and the lines of it deferred, which later
    runs read again."""
    waiting = f" deferred: {','.join(map(str, deferred))}" if deferred else ""
    return f"<!-- bulk-reply: {comment}{waiting} -->"


def reply(made: list[dict], refused: list[tuple[int, str, str]], lines: int, comment: dict, repo: str,
          deferred: Sequence[int] = ()) -> str:
    """One reply to a comment, worded as evidence-store's bulk handler words it: what was recorded and what was not,
    from each refused (line, declaration, reason). Then the note on the earlier form once, and the line naming the
    comment it answers and the lines `deferred`, last (`marker`). It holds at most `CAP` characters: GitHub refuses a
    comment over 65,536, and the reply to the oldest comment unanswered is made first on every run. So each list shows
    what fits, what was not recorded first, since its lines are to be posted again, and then says how many more there
    are."""
    done = [(f"- {said(r)}", 1) for r in made]
    rows = refusals(refused)

    def text(shown: list[str], unshown: int, rows_shown: list[str], rows_unshown: int) -> str:
        parts = []
        if made:
            more = [f"- … and {unshown} more recorded"] if unshown else []
            parts.append(f"Recorded {len(made)} of {lines} lines:\n\n" + "\n".join(shown + more))
        if refused:
            more = [f"- … and {rows_unshown} more not recorded"] if rows_unshown else []
            parts.append("Not recorded:\n\n" + "\n".join(rows_shown + more) +
                         "\n\nPost the corrected lines in a new comment.")
        if any(map(earlier_form, made)):
            parts.append(EARLIER_FORM.format(repo=repo))
        if comment.get("id") is not None:
            parts.append(marker(comment["id"], deferred))
        return "\n\n".join(parts)

    room = CAP - len(text([], len(made), [], len(refused)))  # each row shown takes its length and a line break
    rows_shown, rows_unshown = fit(rows, room)
    shown, unshown = fit(done, room - sum(len(row) + 1 for row in rows_shown))
    return text(shown, unshown, rows_shown, rows_unshown)


def origins(records: list[dict]) -> dict[str, list[dict]]:
    """The records by the ref of their origin, as evidence-store's `Store.from_origin` finds them; a run makes this
    once, and adds to it each record it makes, since `from_origin` reads the whole store, some 25,000 records, at each
    call, and a comment of some hundreds of lines asked it once a line."""
    out: dict[str, list[dict]] = {}
    for r in records:
        out.setdefault((r.get("origin") or {}).get("ref", ""), []).append(r)
    return out


def latest_once(dataset: Callable[[str], Dataset]) -> Callable[[str], Dataset]:
    """`dataset` with its look-up of the latest dataset (commit `""`) made once, a failure too, so that every line of a run
    sees the outcome of the first. evidence-store's `Datasets` lists the library's releases at each look-up of the latest,
    a request to GitHub, so a line cost one; and one failing partway through a run left some of its lines read and the rest
    waiting, which can make a typo first met during an outage be said never. A commit asked for by name goes through. The
    memory is this function's: `process` makes one for each run."""
    found: list[Dataset | Exception] = []  # what the first look-up gave, once it was made

    def look(commit: str) -> Dataset:
        if commit:
            return dataset(commit)
        if not found:
            try:
                found.append(dataset(commit))
            except Exception as e:  # as `intake.lookup` takes it: no dataset, or none yet
                found.append(e)
        outcome = found[0]
        if isinstance(outcome, Exception):
            raise outcome.with_traceback(None)  # a traceback is one raise's, not the sum of a run's
        return outcome
    return look


def process_bulk_comment(comment: dict, issue: dict, ctx: Context, announce: bool = True,
                         index: dict[str, list[dict]] | None = None,
                         deferred: Sequence[int] | None = None, unread: bool = False) -> Outcome:
    """The records the commands of a comment on the bulk issue ask for, in order and each added to the store as it
    is made, and one reply: what was recorded, now or on an earlier run, and what was not and why, its marker naming the
    lines deferred. `index` is the store's records by origin (`origins`), made once a run and kept current here. A
    comment answered already is read again only for the lines its latest reply deferred (`deferred`), and its reply,
    if it has one, says only what is new: a line recorded, or refused for good. A line that waits again was said,
    unless that reply said there was no dataset (`unread`) and the line now waits for its declaration."""
    out = Outcome()
    user = comment.get("user", {})
    if user.get("login") in intake.BOTS:
        return out
    index = origins(ctx.store.records) if index is None else index
    base = comment.get("html_url") or f"{ctx.repo}#{issue['number']}/comment/{comment.get('id')}"
    text = comment.get("body") or ""
    by = intake.author_of(user, intake.parse_agent_mark(naming(text)))
    astray = misplaced(text)  # its agent mark is on a command's line: none of it is recorded
    at = intake.iso(comment.get("created_at", ""))
    maintainer = intake.is_maintainer(ctx, comment)
    cmds = commands(text)
    comment_id = int(comment.get("id") or 0)
    versions = [r for cmd in cmds for r in index.get(f"{base}/line/{cmd.line}", []) if standard.kind_of(r) == "version"]

    def changed(ds: Dataset, decl: Decl) -> bool:
        """Whether a line of the comment recorded a version of `decl`'s review, now or on an earlier run, on the
        declaration as the page puts it (`placing`)."""
        if not versions:
            return False
        on = placing({r.get("id"): r for r in ctx.store.records}, ds)
        return any(on(v) == decl.name for v in versions)

    made, refused, waiting = [], [], []
    for cmd in cmds:
        if deferred is not None and cmd.line not in deferred:
            continue
        ref = f"{base}/line/{cmd.line}"
        had = index.get(ref)
        if had:
            made += had  # said again if the comment is answered now: the reply that said them was refused
            continue
        origin = {"kind": "comment", "ref": ref}
        view = partial(as_of, ctx, at, comment_id, cmd.line)  # the store as of this line, made when a declaration is found
        name = intake.clean(cmd.fields[0]) if cmd.fields else ""
        if astray:
            refused.append((cmd.line, name, MISPLACED))
            continue
        try:
            r, why = ours(cmd, by, maintainer, at, origin, ctx, changed, view) if cmd.keyword in OURS else \
                theirs(cmd, by, at, origin, ctx, issue["number"], view)
        except intake.DatasetMissing:
            r, why, name = None, NO_DATASET, ""
            waiting.append(cmd.line)
        except NotInDataset as e:
            r, why = None, str(e)
            waiting.append(cmd.line)
        if r is None:
            refused.append((cmd.line, name, why))
            continue
        out.records.append(r)
        ctx.store.add([r])
        index.setdefault(ref, []).append(r)
        made.append(r)
        if standard.kind_of(r) == "version":
            versions.append(r)
    if deferred is not None:
        refused = [x for x in refused if x[0] not in waiting or unread and x[2] != NO_DATASET]
    if announce and (made or refused):
        out.replies.append((issue["number"], reply(made, refused, len(cmds), comment, ctx.repo, waiting)))
    return out


def answered(body: str) -> dict[str, tuple[int, ...]]:
    """The comments a reply of the bot answers, each with the lines of it deferred: those its closing lines name, the
    markers after its last line that is not one. A reply quotes what it was given, declaration names among it, so a
    marker anywhere else names none."""
    out: dict[str, tuple[int, ...]] = {}
    for line in reversed((body or "").rstrip().splitlines()):
        m = ANSWERED.fullmatch(line.strip())
        if m is None:
            break
        out.setdefault(m[1], tuple(int(k) for k in m[2].split(",")) if m[2] else ())
    return out


def when(comment: dict) -> tuple[str, int]:
    """Where a comment stands on its issue: when it was made, then its id, which grows with time."""
    return comment.get("created_at", ""), int(comment.get("id") or 0)


def process(issue: dict, comments: list[dict], ctx: Context, announce: bool = True,
            events: list[dict] = ()) -> Outcome:
    """evidence-store's `process`, with the bulk issue read here: its comments in the order `as_of` reads them, by
    time and then id. A comment that no reply of the bot names (`answered`), newer than the bot's latest reply from
    before the replies named any, is read whole and answered. One a reply names is read again only for the lines its
    latest reply deferred, and one older than those replies, decided and answered then, is not read again. The latest
    dataset is looked up once for the call (`latest_once`), which is the issue's part of a run of the intake: every line
    sees the one outcome, and the next run looks again."""
    if not intake.is_bulk(issue):
        return THEIR_PROCESS(issue, comments, ctx, announce, events)
    ctx = replace(ctx, dataset=latest_once(ctx.dataset))  # one look-up of the latest dataset for this run, a failure too
    deferred: dict[str, tuple[int, ...]] = {}  # each comment answered, and the lines its latest reply deferred
    unread: set[str] = set()  # those whose latest reply said there was no dataset to read a line against
    legacy = ""  # when the bot made its latest reply from before the replies named the comments they answer
    for c in sorted(comments, key=when):
        if (c.get("user") or {}).get("login") in intake.BOTS:
            these = answered(c.get("body"))
            deferred.update(these)
            unread.difference_update(these)
            if UNREAD.search(c.get("body") or ""):
                unread.update(these)
            if not these:
                legacy = max(legacy, c.get("created_at", ""))
    index = origins(ctx.store.records)
    out = Outcome()
    for c in sorted(comments, key=when):
        if (c.get("user") or {}).get("login") in intake.BOTS:
            continue
        lines = deferred.get(str(c.get("id")))
        if lines is not None:
            if lines:
                out.merge(process_bulk_comment(c, issue, ctx, announce, index, lines, str(c.get("id")) in unread))
        elif c.get("created_at", "") > legacy:
            out.merge(process_bulk_comment(c, issue, ctx, announce, index))
    return out


def bulk_issue() -> int:
    """The bulk issue's number, as the site's settings give it (data/settings.json): a reply on another issue names it,
    though the intake knows the bulk issue itself by its label."""
    return load_settings()["bulk_issue"]


def process_issue(issue: dict, ctx: Context, announce: bool = True) -> tuple[Outcome, dict | None]:
    """evidence-store's `process_issue`, saying what an AI agent's yes is now: the review form from an agent
    without its reasons is refused with the approval to give instead, on the bulk issue, and an AI agent's yes is
    recorded with the note on the earlier form."""
    out, r = THEIR_PROCESS_ISSUE(issue, ctx, announce)
    review = forms.kind_of(issue.get("labels", [])) == "review"
    made = r is not None and r in out.records

    def say(text: str) -> str:
        if review and NEEDS_TEXT in text:
            text = text.replace(NEEDS_TEXT, BARE_YES.format(repo=ctx.repo, bulk=bulk_issue()))
        return noted(text, r, ctx.repo) if made else text

    out.replies = [(n, say(text) if n == issue.get("number") else text) for n, text in out.replies]
    return out, r


def install() -> None:
    """Puts this module in place of evidence-store's reading: its command line's `process`, and the `process_issue`
    that its own `process` calls."""
    cli.process = process
    intake.process_issue = process_issue
