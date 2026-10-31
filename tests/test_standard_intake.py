import contextlib
import io
import json
import re
import shutil
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from evidence_core import records as rec
from evidence_core.coverage import Evidence
from evidence_core.dataset import Dataset
from evidence_core.rubric import STANDARD as RUBRIC
from evidence_core.status import classify
from evidence_core.store import Store
from evidence_store import cli, forms, github, intake
from evidence_store.intake import Context

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import evidence_intake  # noqa: E402
import standard  # noqa: E402
import standard_intake  # noqa: E402

DATASET = HERE / "fixtures" / "dataset-b"
SPEC = "tauceti-standard/1"
A = "<!-- agent: tool=Claude Code; model=claude-opus-5-5 -->"
B = "<!-- agent: tool=Codex; model=GPT-6 Astra -->"
CELLS = "object, convention, edge-cases, junk, vacuous, choice n/a, generality, naming"
CHECKED = {"object": "checked", "convention": "checked", "edge-cases": "checked", "junk": "checked",
           "vacuous": "checked", "choice": "na", "generality": "checked", "naming": "checked"}
V1 = """## What it says
`Fixture.triple n` is $3n$, three times its argument.

## References and tests
- Fixture documentation, §1.
- `Fixture.triple_two` — its value at 2

## Lean subtleties
None.
"""
V2 = V1.replace("None.", "On ℕ, `Fixture.triple` never truncates.")
VER1, VER2 = standard.version_of(V1), standard.version_of(V2)
NOTE = "adds that it never truncates"
ZERO = "Its value at 0 is 0."
BULK = {"number": 1, "labels": [{"name": "evidence:bulk"}]}
#: AI-REVIEWS.md in the repository the intake runs for: the context's, `o/r`.
GUIDE = "(https://github.com/o/r/blob/main/AI-REVIEWS.md)."


def url(n: int) -> str:
    return f"https://github.com/o/r/issues/1#issuecomment-{900 + n}"


def comment(n: int, *lines: str, login: str = "CBirkbeck", association: str = "OWNER") -> dict:
    """Comment `n` on the bulk issue, at the n-th minute: its lines, by `login` (an agent through it, when a
    line is an agent mark)."""
    return {"id": 900 + n, "user": {"login": login, "type": "User"}, "body": "\n".join(lines),
            "created_at": f"2026-10-31T10:{n:02d}:00Z", "author_association": association, "html_url": url(n)}


def bot(n: int, body: str) -> dict:
    """The intake bot's comment `n` on the bulk issue, at the n-th minute."""
    return {"id": 800 + n, "user": {"login": "github-actions[bot]", "type": "Bot"}, "body": body,
            "created_at": f"2026-10-31T10:{n:02d}:00Z", "author_association": "NONE",
            "html_url": f"https://github.com/o/r/issues/1#issuecomment-{800 + n}"}


def person(n: int, *lines: str, login: str = "boss") -> dict:
    """Comment `n` by a person: `boss` is a maintainer by the store's config, `alice` is not."""
    return comment(n, *lines, login=login, association="NONE")


def write(n: int, agent: str, text: str = V1, decl: str = "Fixture.triple", cells: str = CELLS) -> dict:
    return comment(n, agent, f"Write: {decl} — {cells}", "~~~review", text, "~~~")


def edit(n: int, agent: str, parent: str, text: str = V2, note: str = NOTE, dropped: tuple = ()) -> dict:
    return comment(n, agent, f"Edit: Fixture.triple — {parent} — {CELLS} — {note}",
                   *(f"Dropped: {item} — {why}" for item, why in dropped), "~~~review", text, "~~~")


def approve(n: int, agent: str, version: str, decl: str = "Fixture.triple", cells: str = CELLS) -> dict:
    return comment(n, agent, f"Approve: {decl} — {version} — {cells}")


def dataset(ds: Dataset, decls: list) -> Dataset:
    """`ds` with these declarations in place of its own: the library at another commit."""
    by_meaning: dict[str, list] = {}
    for d in decls:
        if d.meaning:
            by_meaning.setdefault(d.meaning, []).append(d)
    return replace(ds, decls=decls, by_name={d.name: d for d in decls}, by_meaning=by_meaning)


def without(ds: Dataset, *names: str) -> Dataset:
    """`ds` without the declarations named: the library before they were added."""
    return dataset(ds, [d for d in ds.decls if d.name not in names])


#: A fence of a Markdown code block: three or more backticks or tildes, then its info string.
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})\s*([^`]*?)\s*$")
#: A code span of prose, in single backticks.
SPAN = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
#: A field of a form, not of an example: `<decl>`, `<earlier version>`.
PLACEHOLDER = re.compile(r"<[a-z][a-z ]*>")


def fences(text: str) -> tuple[list[tuple[str, str]], str]:
    """A Markdown text's fenced code blocks, each as its info string and its body, and the prose around them. A block
    closes at a line of its own fence's character, as long as its fence or longer: a `~~~` line in a ``` block, the end
    of a review written on the bulk issue, is the block's body."""
    found, prose, lines, k = [], [], text.split("\n"), 0
    while k < len(lines):
        m = FENCE.match(lines[k])
        if m is None:
            prose.append(lines[k])
            k += 1
            continue
        close = re.compile(rf"^ {{0,3}}{re.escape(m[1][0])}{{{len(m[1])},}}\s*$")
        end = next((j for j in range(k + 1, len(lines)) if close.match(lines[j])), len(lines))
        found.append((m[2], "\n".join(lines[k + 1:end])))
        k = end + 1
    return found, "\n".join(prose)


def form(n: int, kind: str = "review", **answers) -> dict:
    """Issue `n`, opened with one of the store's forms by an agent through CBirkbeck's account."""
    answers = {"decl": "Fixture.triple", "who": "agent", "agent": "Claude Code, claude-opus-5-5", **answers}
    return {"number": n, "labels": [{"name": forms.FORMS[kind]["label"]}], "created_at": "2026-10-31T11:00:00Z",
            "user": {"login": "CBirkbeck", "type": "User"}, "body": forms.body(kind, answers)}


class CommandsTests(unittest.TestCase):
    def test_the_commands_of_a_comment(self):
        text = "\n".join([A,
                          "Approve: `Fixture.triple` — dd83c85a — object, choice n/a",
                          f"Edit: Fixture.double — 0123abcd — {CELLS} — a note — with a dash",
                          "Dropped: `Fixture.double_zero` — it moved — to Part 1",
                          "",
                          "~~~review",
                          "## What it says",
                          "~~~",
                          "Reviewed-by: Fixture.one — Matches -- the docs",
                          "Some prose, then a bare yes.",
                          "Reviewed-by: `Fixture.one`",
                          "Restore: Fixture.one -- 89abcdef -- why"])
        got = [(c.line, c.keyword, c.fields, c.dropped, c.block) for c in standard_intake.commands(text)]
        self.assertEqual(got, [
            (2, "Approve", ["`Fixture.triple`", "dd83c85a", "object, choice n/a"], [], None),
            (3, "Edit", ["Fixture.double", "0123abcd", CELLS, "a note", "with a dash"],
             [("`Fixture.double_zero`", "it moved — to Part 1")], "## What it says"),
            (9, "Reviewed-by", ["Fixture.one", "Matches -- the docs"], [], None),  # as evidence-store reads it
            (11, "Reviewed-by", ["Fixture.one", ""], [], None),
            (12, "Restore", ["Fixture.one", "89abcdef", "why"], [], None)])

    def test_a_block_closes_at_the_last_fence_before_the_next_command(self):
        text = "\n".join(["Write: Fixture.one — cells", "~~~review", "one", "~~~", "inner", "~~~",
                          "Write: Fixture.double — cells", "~~~review", "two", "Test: x — y — z", "~~~",
                          "Test: Fixture.triple — Fixture.triple_two — its value at 2"])
        got = [(c.line, c.keyword, c.block) for c in standard_intake.commands(text)]
        # A command line before a block's first fence is its text; one after a fence ends it.
        self.assertEqual(got, [(1, "Write", "one\n~~~\ninner"), (7, "Write", "two\nTest: x — y — z"),
                               (12, "Test", None)])

    def test_dropped_lines_go_with_the_command_before_them(self):
        text = "\n".join(["Dropped: `Fixture.a` — before any command", "Edit: Fixture.one — 0123abcd — note",
                          "~~~review", "text", "~~~", "Dropped: `Fixture.b` — after its block",
                          "Approve: Fixture.two — 0123abcd — cells"])
        edit, approve = standard_intake.commands(text)
        self.assertEqual((edit.dropped, approve.dropped), ([("`Fixture.b`", "after its block")], []))

    def test_a_block_not_closed_gives_no_text(self):
        text = "\n".join(["Write: Fixture.one — cells", "~~~review", "one, its fence forgotten",
                          "Write: Fixture.double — cells", "~~~review", "two", "~~~"])
        got = [(c.line, c.block) for c in standard_intake.commands(text)]
        self.assertEqual(got, [(1, None), (4, "two")])  # a review holds no ~~~review line: the first was not closed
        self.assertEqual([c.block for c in standard_intake.commands("Write: Fixture.one\n~~~review\none")], [None])


class IntakeCase(unittest.TestCase):
    """Our intake on the bulk issue, against a store of our own and the fixture dataset."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        (self.dir / "evidence" / "records").mkdir(parents=True)
        shutil.copy(HERE.parent / "evidence" / "store.json", self.dir / "evidence" / "store.json")
        self.store = Store.load(self.dir / "evidence")
        self.ds = Dataset.load(DATASET)
        self.ctx = Context("o/r", self.store, lambda c: self.ds, frozenset({"boss"}))

    def process(self, *comments: dict, announce: bool = True):
        return standard_intake.process(BULK, list(comments), self.ctx, announce=announce)

    def last(self, out) -> str:
        """The reply to the last comment that had one."""
        n, text = out.replies[-1]
        self.assertEqual(n, 1)
        return text


class ApproveTests(IntakeCase):
    def test_write_then_approve_in_order(self):
        out = self.process(write(1, A), approve(2, B, VER1))
        version, approval = out.records
        self.assertEqual(self.store.records, [version, approval])  # each added as it was made
        self.assertEqual({k: version[k] for k in ("kind", "verdict", "rubric", "checked", "standard", "text")},
                         {"kind": "review", "verdict": "accept", "rubric": "ltb-rubric/1", "checked": CHECKED,
                          "standard": {"spec": SPEC}, "text": V1.rstrip("\n")})
        self.assertEqual(version["by"], {"kind": "agent", "identity": {"kind": "github", "id": "CBirkbeck"},
                                         "involvement": "unknown",
                                         "agent": {"tool": "Claude Code", "model": "claude-opus-5-5"}})
        self.assertEqual((version["subject"]["name"], version["subject"]["commit"]), ("Fixture.triple", "B"))
        self.assertEqual((version["at"], version["origin"]),
                         ("2026-10-31T10:01:00Z", {"kind": "comment", "ref": url(1) + "/line/2"}))
        self.assertEqual({k: approval[k] for k in ("kind", "verdict", "rubric", "checked", "standard", "text")},
                         {"kind": "review", "verdict": "accept", "rubric": "ltb-rubric/1", "checked": CHECKED,
                          "standard": {"spec": SPEC, "approves": VER1},
                          "text": f"Approves the standard review `{VER1}`."})
        self.assertEqual(approval["by"]["agent"], {"tool": "Codex", "model": "GPT-6 Astra"})
        self.assertNotIn("links", approval)  # its reviewer had said nothing of the declaration before
        (n1, wrote), (n2, approved) = out.replies
        self.assertEqual((n1, n2), (1, 1))
        for words in (VER1, "Fixture.triple", "written by Claude Code (claude-opus-5-5) via CBirkbeck", version["id"]):
            self.assertIn(words, wrote)
        for words in (approval["id"], VER1, "Fixture.triple", "Codex (GPT-6 Astra)"):
            self.assertIn(words, approved)

    def test_approving_an_old_version_is_refused_with_the_current_one(self):
        out = self.process(write(1, A), edit(2, A, VER1), approve(3, B, VER1))
        self.assertEqual([r["by"]["agent"]["tool"] for r in self.store.records], ["Claude Code", "Claude Code"])
        said = self.last(out)
        self.assertIn("Not recorded", said)
        self.assertIn(VER2, said)  # the current one, in full
        self.assertNotIn("Recorded 1", said)

    def test_a_prefix_is_stored_as_the_full_hash(self):
        self.process(write(1, A))
        out = self.process(approve(2, B, VER1[:8]), edit(3, A, VER1[:8].upper()))
        approval, version = out.records
        self.assertEqual((approval["standard"]["approves"], version["standard"]["parent"]), (VER1, VER1))
        out = self.process(approve(4, B, VER2[:7]))  # fewer than eight digits name no version
        self.assertEqual(out.records, [])
        self.assertIn(VER2, self.last(out))

    def test_a_tick_needs_every_cell(self):
        seven = CELLS.replace(", naming", "")
        out = self.process(write(1, A), approve(2, B, VER1, cells=seven),
                           write(3, B, decl="Fixture.double", cells=seven))
        self.assertEqual(len(self.store.records), 1)
        tick, wrote = [text for _, text in out.replies[1:]]
        for said in (tick, wrote):
            self.assertIn("Not recorded", said)
            self.assertIn("naming", said)

    def test_a_line_with_too_few_or_too_many_fields_is_refused_with_its_form(self):
        self.process(write(1, A))
        out = self.process(comment(2, B, f"Approve: Fixture.triple — {VER1}"),
                           comment(3, B, f"Approve: Fixture.triple — {VER1} — {CELLS} — and more"),
                           comment(4, B, "Write: Fixture.double", "~~~review", V1, "~~~"))
        self.assertEqual(out.records, [])
        few, many, uncelled = [text for _, text in out.replies]
        for said in (few, many):
            self.assertIn("`Approve: <decl> — <version> — <cells>`", said)
        self.assertIn("`Write: <decl> — <cells>`", uncelled)  # an AI's write carries its cells

    def test_a_withdrawn_edit_is_undone(self):
        self.process(write(1, A), edit(2, A, VER1))
        v2 = self.store.records[-1]
        self.store.add([intake.status_record(v2, "withdrawn", v2["by"], "2026-10-31T10:03:00Z",
                                             {"kind": "comment", "ref": url(3)})])
        out = self.process(approve(4, B, VER2), approve(5, B, VER1))
        approval, = out.records
        self.assertEqual(approval["standard"]["approves"], VER1)
        self.assertIn(f"which is `{VER1}`", out.replies[0][1])  # V1 is current again

    def test_a_new_yes_supersedes_the_reviewers_latest(self):
        old = self.process(comment(1, B, "Reviewed-by: Fixture.triple — Matches the fixture's docs, §1.")).records[0]
        version = self.process(write(2, A)).records[0]
        approval = self.process(approve(3, B, VER1)).records[0]
        edited = self.process(edit(4, A, VER1)).records[0]
        self.assertNotIn("links", version)
        self.assertEqual(approval["links"], {"supersedes": old["id"]})  # as evidence-store's record_for sets it
        self.assertEqual(edited["links"], {"supersedes": version["id"]})


class WriteEditTests(IntakeCase):
    def test_a_write_where_one_exists_is_refused(self):
        out = self.process(write(1, A), write(2, B, V2))
        self.assertEqual(len(self.store.records), 1)
        said = self.last(out)
        self.assertIn("Not recorded", said)
        self.assertIn(VER1, said)

    def test_an_edit_failing_the_check_is_refused_with_why(self):
        without = V1.replace("- `Fixture.triple_two` — its value at 2\n", "")
        out = self.process(write(1, A), edit(2, B, VER1, without, note="shorter"))
        self.assertEqual(len(self.store.records), 1)
        said = self.last(out)
        self.assertIn("Not recorded", said)
        self.assertIn("Fixture.triple_two", said)
        self.assertIn("Dropped:", said)
        # With its reason on a Dropped line, the same edit goes in, and says what it dropped and why.
        why = [("`Fixture.triple_two`", "it is no test of the definition")]
        r, = self.process(edit(3, B, VER1, without, note="shorter", dropped=why)).records
        self.assertEqual(r["standard"], {"spec": SPEC, "parent": VER1, "note": "shorter", "dropped": [
            {"item": "`Fixture.triple_two`", "why": "it is no test of the definition"}]})
        self.assertEqual((r["kind"], r["verdict"], r["checked"]), ("review", "accept", CHECKED))

    def test_an_edit_says_what_it_changes(self):
        self.process(write(1, A))
        out = self.process(comment(2, A, f"Edit: Fixture.triple — {VER1} — {CELLS}", "~~~review", V2, "~~~"))
        self.assertEqual(out.records, [])
        self.assertIn("note", self.last(out))
        out = self.process(comment(3, A, f"Edit: Fixture.triple — {VER1} — {CELLS} — {NOTE}"))  # with no text
        self.assertEqual(out.records, [])
        self.assertIn("~~~review", self.last(out))

    def test_one_change_per_declaration_per_comment(self):
        both = comment(1, A, f"Write: Fixture.triple — {CELLS}", "~~~review", V1, "~~~",
                       f"Edit: Fixture.triple — {VER1} — {CELLS} — {NOTE}", "~~~review", V2, "~~~")
        out = self.process(both)
        self.assertEqual([r["standard"] for r in out.records], [{"spec": SPEC}])
        self.assertIn("line 15 (`Fixture.triple`): this comment changes the standard review of `Fixture.triple` in "
                      "another line", self.last(out))
        # Read again, the edit is still refused: the write before it is in the store now.
        self.assertEqual(self.process(both).records, [])

    def test_people_cannot_approve_and_only_maintainers_edit(self):
        version, = self.process(write(1, A)).records
        out = self.process(person(2, f"Approve: Fixture.triple — {VER1} — {CELLS}", login="alice"),
                           person(3, f"Edit: Fixture.triple — {VER1} — {NOTE}", "~~~review", V2, "~~~",
                                  login="alice"))
        self.assertEqual(out.records, [])
        tick, change = [text for _, text in out.replies]
        self.assertIn("form", tick)
        self.assertIn("maintainer", change)
        out = self.process(person(4, f"Approve: Fixture.triple — {VER1} — {CELLS}"))  # a maintainer neither
        self.assertEqual(out.records, [])
        self.process(approve(5, B, VER1))  # the latest review of the declaration now, though not its version
        r, = self.process(person(6, f"Edit: Fixture.triple — {VER1} — {NOTE}", "~~~review", V2, "~~~")).records
        self.assertEqual({k: r[k] for k in ("kind", "text", "standard", "links", "by")},
                         {"kind": "comment", "text": V2.rstrip("\n"),
                          "standard": {"spec": SPEC, "parent": VER1, "note": NOTE, "dropped": []},
                          "links": {"replies_to": version["id"]},
                          "by": {"kind": "person", "identity": {"kind": "github", "id": "boss"},
                                 "involvement": "unknown"}})
        self.assertFalse({"verdict", "rubric", "checked"} & set(r))
        self.assertEqual(r["subject"]["name"], "Fixture.triple")
        self.assertEqual(len(self.process(approve(7, B, VER2)).records), 1)  # it is the current version

    def said(self, n: int, verdict: str, decl: str = "Fixture.double") -> dict:
        """A person's yes, no or suggestion of the declaration (`verdict`: accept, problem or question), as the page's
        forms record one, made at the n-th minute: older than the comments with a number above n."""
        text = {"accept": "It says what it should.", "problem": "It says the wrong thing.",
                "question": "Could it be more general?"}[verdict]
        extra = {"category": "other", "rubric": "ltb-rubric/1"} if verdict == "problem" else {}
        return {"schema": rec.SCHEMA, "kind": "review", "verdict": verdict, "text": text,
                "by": {"kind": "person", "identity": {"kind": "github", "id": "alice"}},
                "subject": rec.subject_from_decl(self.ds.by_name[decl], self.ds), "at": f"2026-10-31T10:{n:02d}:00Z",
                "origin": {"kind": "issue", "ref": f"o/r#{n}"}, **extra}

    def test_a_maintainers_write_replies_to_the_latest_yes(self):
        out = self.process(person(1, "Write: Fixture.double", "~~~review", V1, "~~~"))
        self.assertEqual(out.records, [])  # a comment needs a yes to reply to, and there is none
        self.assertIn("Not recorded", self.last(out))
        self.process(comment(2, A, "Reviewed-by: Fixture.double — Matches the docs."),
                     comment(3, B, "Reviewed-by: Fixture.double — Twice its argument, as the docs say."))
        latest = self.store.records[-1]
        out = self.process(person(4, f"Write: Fixture.double — {CELLS}", "~~~review", V1, "~~~"))
        self.assertEqual(out.records, [])  # a person's line carries no cells
        self.assertIn("`Write: <decl>`", self.last(out))
        r, = self.process(person(5, "Write: Fixture.double", "~~~review", V1, "~~~")).records
        self.assertEqual((r["kind"], r["standard"], r["links"]),
                         ("comment", {"spec": SPEC}, {"replies_to": latest["id"]}))

    def test_a_first_version_hangs_from_the_latest_yes_not_from_a_newer_no_or_suggestion(self):
        # A comment must reply to a record, and a record with a reply is taken for answered: so a version nobody approves
        # never hangs from a no or a suggestion, newer than the yes though they are. A person's yes is a yes.
        self.process(comment(1, A, "Reviewed-by: Fixture.double — Matches the docs."))
        yes = self.said(2, "accept")
        self.store.add([yes, self.said(3, "problem"), self.said(4, "question")])
        r, = self.process(person(5, "Write: Fixture.double", "~~~review", V1, "~~~")).records
        self.assertEqual((r["kind"], r["links"]), ("comment", {"replies_to": rec.with_id(yes)["id"]}))

    def test_a_first_version_with_only_a_no_or_a_suggestion_is_refused_and_says_so(self):
        self.store.add([self.said(1, "problem"), self.said(2, "question")])
        out = self.process(person(3, "Write: Fixture.double", "~~~review", V1, "~~~"))
        self.assertEqual(out.records, [])
        said = self.last(out)
        self.assertIn("Not recorded", said)
        self.assertIn("replies to a yes", said)
        self.assertIn("a no or a suggestion is not one", said)


class RestoreTests(IntakeCase):
    def test_restore_puts_back_an_earlier_text(self):
        self.process(write(1, A), edit(2, A, VER1))
        v2 = self.store.records[-1]
        self.process(approve(3, B, VER2))  # the latest review now, though not the version
        r, = self.process(person(4, f"Restore: Fixture.triple — {VER1[:8]} — the edit added nothing true")).records
        self.assertEqual({k: r[k] for k in ("kind", "text", "standard", "links")},
                         {"kind": "comment", "text": V1.rstrip("\n"),
                          "standard": {"spec": SPEC, "parent": VER2, "restores": VER1,
                                       "note": "the edit added nothing true"},
                          "links": {"replies_to": v2["id"]}})
        self.assertIn(f"`{VER1}`", self.process(approve(5, B, VER1)).records[0]["text"])  # it is the current version

    def test_only_a_maintainer_restores_and_only_an_earlier_version(self):
        self.process(write(1, A), edit(2, A, VER1))
        out = self.process(comment(3, A, f"Restore: Fixture.triple — {VER1} — why"),
                           person(4, f"Restore: Fixture.triple — {VER1} — why", login="alice"),
                           person(5, f"Restore: Fixture.triple — {VER2} — why"),
                           person(6, f"Restore: Fixture.triple — {'f' * 8} — why"),
                           person(7, f"Restore: Fixture.triple — {VER1}"))
        self.assertEqual(len(self.store.records), 2)
        agent, alice, current, nothing, unsaid = [text for _, text in out.replies]
        self.assertIn("maintainer", agent)
        self.assertIn("maintainer", alice)
        self.assertIn(VER2, current)
        self.assertIn(VER2, nothing)
        self.assertIn("note", unsaid)


class RenameTests(IntakeCase):
    """A declaration renamed since its standard review was written: `Fixture.triple_three'`, which was
    `Fixture.triple_three` at commit A, with the same meaning (tests/fixtures/records.jsonl). The intake reads its
    records as evidence-core does, and so as the page does: a record follows the declaration by its meaning hash."""

    OLD, NEW = "Fixture.triple_three", "Fixture.triple_three'"
    TEXT = ("## What it says\n`Fixture.triple 3` is 9.\n\n## References and tests\n- Fixture documentation, §1.\n"
            "- `Fixture.triple_two` — its value at 2\n\n## Lean subtleties\nNone.")
    VER = standard.version_of(TEXT)

    def setUp(self):
        super().setUp()
        fixture = (json.loads(line) for line in (HERE / "fixtures" / "records.jsonl").read_text().splitlines())
        self.yes = next(r for r in fixture if r["subject"]["name"] == self.OLD)  # a person's yes, under the old name
        status = classify(self.yes["subject"], self.ds)
        self.assertEqual((status.state, status.decl.name), ("renamed", self.NEW))

    def written(self) -> dict:
        """A's write of the standard review, under the old name, before the rename."""
        version, = self.store.add([{
            "schema": rec.SCHEMA, "kind": "review", "verdict": "accept", "subject": self.yes["subject"],
            "at": "2026-10-30T10:00:00Z",
            "by": {"kind": "agent", "identity": {"kind": "github", "id": "CBirkbeck"}, "involvement": "unknown",
                   "agent": {"tool": "Claude Code", "model": "claude-opus-5-5"}},
            "origin": {"kind": "comment", "ref": "https://github.com/o/r/issues/1#issuecomment-700/line/2"},
            "text": self.TEXT, "rubric": "ltb-rubric/1", "checked": CHECKED, "standard": {"spec": SPEC}}])
        return version

    def test_a_version_under_the_old_name_is_the_current_one(self):
        self.written()
        out = self.process(approve(1, B, VER1, decl=self.NEW))
        self.assertEqual(out.records, [])
        self.assertIn(f"which is `{self.VER}`", self.last(out))  # the one the page shows

    def test_approving_it_is_recorded(self):
        self.written()
        approval, = self.process(approve(1, B, self.VER[:8], decl=self.NEW)).records
        self.assertEqual((approval["subject"]["name"], approval["standard"]["approves"]), (self.NEW, self.VER))

    def test_a_write_is_refused_since_one_exists(self):
        self.written()
        out = self.process(write(1, B, decl=self.NEW))
        self.assertEqual(out.records, [])
        self.assertIn(f"`{self.NEW}` has a standard review already, `{self.VER}`", self.last(out))

    def test_an_edit_is_checked_against_it(self):
        self.written()
        shorter = self.TEXT.replace("- `Fixture.triple_two` — its value at 2\n", "")
        out = self.process(comment(1, B, f"Edit: {self.NEW} — {self.VER} — {CELLS} — shorter", "~~~review", shorter,
                                   "~~~"))
        self.assertEqual(out.records, [])
        self.assertIn("the edit drops the test `Fixture.triple_two`", self.last(out))
        r, = self.process(comment(2, B, f"Edit: {self.NEW} — {self.VER} — {CELLS} — {NOTE}", "~~~review",
                                  self.TEXT.replace("None.", "It is `rfl`."), "~~~")).records
        self.assertEqual(r["standard"]["parent"], self.VER)

    def test_a_restore_finds_it(self):
        self.written()
        edited, = self.process(comment(1, B, f"Edit: {self.NEW} — {self.VER} — {CELLS} — {NOTE}", "~~~review",
                                       self.TEXT.replace("None.", "It is `rfl`."), "~~~")).records
        r, = self.process(person(2, f"Restore: {self.NEW} — {self.VER} — the edit added nothing")).records
        self.assertEqual((r["standard"]["restores"], r["links"]), (self.VER, {"replies_to": edited["id"]}))

    def test_a_maintainers_first_write_replies_to_a_yes_under_the_old_name(self):
        yes, = self.store.add([self.yes])
        r, = self.process(person(1, f"Write: {self.NEW}", "~~~review", self.TEXT, "~~~")).records
        self.assertEqual((r["kind"], r["subject"]["name"], r["links"]),
                         ("comment", self.NEW, {"replies_to": yes["id"]}))

    def test_an_approval_supersedes_its_reviewers_accept_under_the_old_name(self):
        version = self.written()
        approval, = self.process(approve(1, A, self.VER[:8], decl=self.NEW)).records
        self.assertEqual(approval["links"], {"supersedes": version["id"]})
        # So the page lists A once, by its approval, and counts no earlier approval.
        ev = Evidence.resolve(self.store.records, self.ds)
        seen = [standard.Seen(r, s.applies, ev.state(r["id"]) == "withdrawn", r["id"] in ev.superseded_by)
                for r, s in ev.records_on(self.NEW)]
        review = standard.summary(seen)
        self.assertEqual(([a.record["id"] for a in review["approvers"]], review["earlier"]), ([approval["id"]], 0))

    def test_the_intake_reads_a_declarations_records_as_the_page_does(self):
        # A's write under the old name, then a maintainer's edit under the new one: a comment, replying to the write.
        wrote = self.written()
        text = self.TEXT.replace("None.", "It is `rfl`.")
        edited, = self.process(person(1, f"Edit: {self.NEW} — {self.VER} — a maintainer's edit", "~~~review", text,
                                      "~~~")).records
        self.assertEqual(edited["links"], {"replies_to": wrote["id"]})
        # Then the statement under the new name changes, and a new declaration has its old one, its meaning hash. The write
        # follows that one, and the edit goes where the record it replies to went, whatever its own subject says
        # (comment_route_probe.py, `Evidence.resolve`).
        new = self.ds.by_name[self.NEW]
        p = replace(new, id=max(d.id for d in self.ds.decls) + 1, name="Fixture.p")
        later = dataset(self.ds, [replace(new, meaning="f" * 16) if d is new else d for d in self.ds.decls] + [p])
        ev = Evidence.resolve(self.store.records, later)
        for name, want in ((self.NEW, []), (p.name, [wrote["id"], edited["id"]])):
            site = sorted(r["id"] for r, _ in ev.records_on(name))
            mine = sorted(r["id"] for r in standard_intake.records_of(self.ctx, later, later.by_name[name]))
            self.assertEqual((mine, site), (sorted(want), sorted(want)), name)
        # And so the intake decides as the page shows: the new declaration's review is the edit's text, and the renamed one
        # has none.
        self.ctx.dataset = lambda commit: later
        out = self.process(approve(2, B, standard.version_of(text)[:8], decl=p.name),
                           approve(3, B, standard.version_of(text)[:8], decl=self.NEW))
        approval, = out.records
        self.assertEqual((approval["subject"]["name"], approval["standard"]["approves"]),
                         (p.name, standard.version_of(text)))
        self.assertIn(f"`{self.NEW}` has no standard review yet", self.last(out))

    def test_a_comment_changes_a_renamed_declaration_once(self):
        # Read when the declaration had its old name, a comment's Write of it went in, and its Edit under the new name waited
        # for a dataset that has it. Read again then, the Edit changes the declaration the Write changed: refused.
        before = dataset(self.ds, [replace(d, name=self.OLD) if d.name == self.NEW else d for d in self.ds.decls])
        self.ctx.dataset = lambda commit: before
        text = self.TEXT.replace("None.", "It is `rfl`.")
        both = comment(1, B, f"Write: {self.OLD} — {CELLS}", "~~~review", self.TEXT, "~~~",
                       f"Edit: {self.NEW} — {self.VER} — {CELLS} — {NOTE}", "~~~review", text, "~~~")
        k = 1 + next(j for j, line in enumerate(both["body"].splitlines()) if line.startswith("Edit:"))
        out = self.process(both)
        wrote, = out.records
        self.assertEqual(wrote["subject"]["name"], self.OLD)
        said = self.last(out)
        self.assertTrue(said.endswith(f"\n\n<!-- bulk-reply: 901 deferred: {k} -->"), said)
        self.ctx.dataset = lambda commit: self.ds
        out = self.process(both, bot(2, said))
        self.assertEqual(out.records, [])
        self.assertIn(f"line {k} (`{self.NEW}`): this comment changes the standard review of `{self.NEW}` in another "
                      "line", self.last(out))


class BodyTests(IntakeCase):
    def test_crlf_body_hashes_like_the_agent_did(self):
        c = write(1, A)  # the agent hashed V1, its file; GitHub hands back CRLF, and an editor left spaces
        c["body"] = "\r\n".join(line + "  " for line in [A, f"Write: Fixture.triple — {CELLS}", "~~~review",
                                                           *V1.split("\n"), "~~~"])
        r, = self.process(c).records
        self.assertEqual(standard.version_of(r["text"]), standard.version_of(V1))
        self.assertEqual(r["text"], V1.rstrip("\n"))
        self.assertEqual(len(self.process(approve(2, B, standard.version_of(V1))).records), 1)

    def test_a_block_keeps_inner_fences(self):
        text = V1.replace("None.", "Its value at 2, in Lean:\n\n```lean\nexample : Fixture.triple 2 = 6 := rfl\n```\n\n"
                                   "and as `#eval` shows it:\n\n~~~\n#eval Fixture.triple 2\n~~~")
        r, = self.process(write(1, A, text)).records
        self.assertEqual(r["text"], text.rstrip("\n"))

    def test_lines_inside_a_block_are_not_commands(self):
        inside = "Test: Fixture.triple — Fixture.triple_one — its value at 1"
        text = V1.replace("its value at 2\n", f"its value at 2\n{inside}\n")
        c = comment(1, A, f"Write: Fixture.triple — {CELLS}", "~~~review", text, "~~~",
                    "Test: Fixture.triple — Fixture.triple_two — its value at 2")
        version, test = self.process(c).records
        self.assertIn(inside, version["text"])
        self.assertEqual((test["kind"], test["test"]["name"]), ("test", "Fixture.triple_two"))
        self.assertEqual(test["origin"]["ref"], f"{url(1)}/line/{len(c['body'].splitlines())}")

    def test_running_twice_records_once(self):
        c = comment(1, A, f"Write: Fixture.triple — {CELLS}", "~~~review", V1, "~~~",
                    "Test: Fixture.triple — Fixture.triple_two — its value at 2")
        self.assertEqual(len(self.process(c).records), 2)
        self.assertEqual(self.process(c).records, [])
        self.assertEqual(len(Store.load(self.dir / "evidence").records), 2)

    def test_a_missing_dataset_is_read_again(self):
        def missing(commit):
            raise LookupError(commit)
        self.ctx.dataset = missing
        out = self.process(write(1, A))
        self.assertEqual(out.records, [])
        self.assertIn("line 2: there is no dataset of the library yet; it will be read again", self.last(out))


class AgentMarkTests(IntakeCase):
    """A comment names its agent on a line of its own. A review's text, an edit's note and the reason for a dropped item are
    words an agent writes about a declaration, and may quote a mark; evidence-store's `parse_agent_mark` takes the
    reviewed-by form wherever it is in a comment, so read over the whole comment it would credit the comment to the agent
    that text names (Task 8's review, Part B's final review)."""

    FORM = '<!--reviewed-by:v1 {"agent": "Codex, GPT-6 Astra"}-->'  # B, as the reviewed-by form names it
    LINE = "<!-- agent: tool=Codex; model=GPT-6 Astra -->"  # B, as an agent line does
    A_IS = {"tool": "Claude Code", "model": "claude-opus-5-5"}

    @staticmethod
    def quoting(mark: str) -> str:
        return V1.replace("None.", f"A review may quote a mark, {mark}, which is only text.")

    def test_a_reviewed_by_mark_in_a_review_does_not_name_the_comments_agent(self):
        r, = self.process(write(1, A, self.quoting(self.FORM))).records
        self.assertIn(self.FORM, r["text"])  # the text goes in whole
        self.assertEqual(r["by"]["agent"], self.A_IS)

    def test_an_agent_mark_in_a_review_does_not_name_it_either(self):
        # A's line comes last, so the first mark of the comment is the one in the text.
        c = comment(1, f"Write: Fixture.triple — {CELLS}", "~~~review", self.quoting(self.LINE), "~~~", A)
        r, = self.process(c).records
        self.assertIn(self.LINE, r["text"])
        self.assertEqual(r["by"]["agent"], self.A_IS)

    def test_a_mark_in_a_note_or_in_a_reason_for_a_dropped_item_does_not_name_it(self):
        self.process(write(1, A))
        shorter = V1.replace("- `Fixture.triple_two` — its value at 2\n", "")
        why = f"it is no test of the definition {self.FORM}"
        r, = self.process(edit(2, A, VER1, shorter, note=f"shorter {self.LINE}",
                               dropped=(("`Fixture.triple_two`", why),))).records
        self.assertEqual(r["standard"]["note"], f"shorter {self.LINE}")
        self.assertEqual(r["standard"]["dropped"], [{"item": "`Fixture.triple_two`", "why": why}])
        self.assertEqual(r["by"]["agent"], self.A_IS)

    def test_a_mark_in_the_reasons_of_an_earlier_form_line_does_not_name_it(self):
        r, = self.process(comment(1, A, f"Reviewed-by: Fixture.double — Matches the docs. {self.FORM}")).records
        self.assertIn(self.FORM, r["text"])
        self.assertEqual(r["by"]["agent"], self.A_IS)

    def test_the_line_naming_the_agent_is_read_wherever_it_is_outside_the_blocks(self):
        self.process(write(1, B))
        approval = f"Approve: Fixture.triple — {VER1} — {CELLS}"
        for n, lines in enumerate([(A, approval), (approval, "", A), (approval, "A comment about it.", f"  {A}  ")], 2):
            with self.subTest(lines=lines):
                r, = self.process(comment(n, *lines)).records
                self.assertEqual(r["by"]["agent"], self.A_IS)

    def test_a_text_that_quotes_a_mark_is_still_its_maintainers(self):
        # No mark outside the block: the account's own comment, as a comment without one is.
        self.process(comment(1, A, "Reviewed-by: Fixture.double — Matches the docs."))  # a yes for the text to hang from
        r, = self.process(person(2, "Write: Fixture.double", "~~~review", self.quoting(self.FORM), "~~~")).records
        self.assertEqual((r["kind"], r["by"]["kind"]), ("comment", "person"))
        self.assertEqual(r["text"], self.quoting(self.FORM).rstrip("\n"))


class OriginTests(IntakeCase):
    def test_a_run_reads_the_store_by_origin_once(self):
        # A comment's lines each look up what the store holds from them, and the comment's changes, in a map made once a
        # run: evidence-store's `Store.from_origin` reads the whole store at each call, some 25,000 records and more.
        self.process(write(1, A))
        many = comment(2, B, *[f"Approve: Fixture.triple — {VER1} — {CELLS}"] * 20,
                       "Test: Fixture.triple — Fixture.triple_two — its value at 2",
                       f"Write: Fixture.double — {CELLS}", "~~~review", V1, "~~~",
                       f"Edit: Fixture.double — {VER1} — {CELLS} — {NOTE}", "~~~review", V2, "~~~",
                       "Reviewed-by: Fixture.nothing — Matches the docs.")
        calls: list[str] = []
        real = Store.from_origin
        with mock.patch.object(Store, "from_origin", lambda store, ref: calls.append(ref) or real(store, ref)):
            first = self.process(many)
            once = len(calls)
            again = self.process(many)  # its reply was refused: no reply of the bot names it
        self.assertLessEqual(max(once, len(calls) - once), 1, f"{len(calls)} calls in two runs")
        self.assertEqual([standard.kind_of(r) or r["kind"] for r in first.records],
                         ["approval"] * 20 + ["test", "version"])
        said = self.last(first)
        self.assertTrue(said.startswith("Recorded 22 of 24 lines:\n\n"), said[:100])
        self.assertIn("(`Fixture.double`): this comment changes the standard review of `Fixture.double` in another line",
                      said)
        self.assertIn("(`Fixture.nothing`): `Fixture.nothing` is not a declaration", said)
        self.assertEqual((again.records, again.replies), ([], first.replies))  # what it recorded then, and what it did not


class AnnounceTests(IntakeCase):
    """Which comments are answered: those that no reply of the bot names yet, and none older than its replies from
    before the markers, which are not read again either. A sweep makes the records of the others, unsaid till the next
    run that answers."""

    def test_a_reply_names_the_comment_it_answers(self):
        said = self.last(self.process(write(1, A)))
        self.assertTrue(said.endswith("\n\n<!-- bulk-reply: 901 -->"), said)

    def test_a_comment_answered_is_not_answered_again(self):
        c1 = write(1, A)
        said = self.last(self.process(c1))
        out = self.process(c1, bot(2, said))
        self.assertEqual((out.records, out.replies), ([], []))

    def test_a_comment_posted_while_a_run_read_the_issue_is_answered(self):
        c1 = write(1, A)
        said = self.last(self.process(c1))  # the run read the issue with c1 alone, and c2 came before its reply
        out = self.process(c1, approve(2, B, VER1), bot(3, said))
        approval, = out.records
        (n, text), = out.replies
        self.assertIn(approval["id"], text)
        self.assertTrue(text.endswith("\n\n<!-- bulk-reply: 902 -->"), text)

    def test_comments_before_the_markers_are_not_answered_again(self):
        c1 = comment(1, A, f"Approve: Fixture.triple — {VER1} — {CELLS}",
                     "Test: Fixture.triple — Fixture.triple_two — its value at 2")
        c3 = comment(3, A, f"Approve: Fixture.double — {VER1} — {CELLS}")
        out = self.process(c1, bot(2, "Not recorded: …"), c3)  # a reply from before the markers
        self.assertEqual(out.records, [])  # nor read again: its lines were decided when it was answered
        (n, said), = out.replies
        self.assertIn("Fixture.double", said)
        self.assertNotIn("Fixture.triple", said)
        # A sweep answers nothing.
        self.assertEqual(self.process(c1, bot(2, "Not recorded: …"), c3, announce=False).replies, [])

    def test_a_reply_github_refused_is_said_again(self):
        c1 = comment(1, A, f"Write: Fixture.triple — {CELLS}", "~~~review", V1, "~~~",
                     "Test: Fixture.triple — Fixture.triple_two — its value at 2",
                     f"Approve: Fixture.double — {VER1} — {CELLS}")
        first = self.process(c1)
        again = self.process(c1)  # no reply of the bot names c1: GitHub refused the first
        self.assertEqual(again.records, [])
        self.assertEqual(again.replies, first.replies)  # what it recorded then, and what it did not
        self.assertIn("Recorded 2 of 3 lines", self.last(again))

    def test_a_marker_quoted_in_a_reply_answers_nothing(self):
        # A reply quotes what it was given, so a line can put a marker in its body: only its closing lines name
        # comments.
        c1 = comment(1, A, f"Approve: <!-- bulk-reply: 903 --> — {VER1} — {CELLS}")
        said = self.last(self.process(c1))
        self.assertIn("(`<!-- bulk-reply: 903 -->`)", said)
        out = self.process(c1, bot(2, said), write(3, A))
        version, = out.records
        (n, text), = out.replies
        self.assertIn(version["id"], text)
        self.assertTrue(text.endswith("\n\n<!-- bulk-reply: 903 -->"), text)


class ReplyTests(IntakeCase):
    """A reply fits in a GitHub comment, which holds 65,536 characters: the reply to the oldest comment not yet answered
    is built first on every run, so one that GitHub refused would be refused again each time."""

    LONG = "Lean.Omega.Constraint.not_sat'_of_isImpossible"

    def test_a_long_reply_lists_what_fits(self):
        self.process(write(1, A, decl=self.LONG))
        out = self.process(comment(2, B, *[f"Approve: {self.LONG} — {VER1} — {CELLS}"] * 400))
        self.assertEqual(len(out.records), 400)  # every line is recorded, whatever the reply says of them
        said = self.last(out)
        rows = [standard_intake.said(r) for r in out.records]
        self.assertGreater(sum(len(row) + 3 for row in rows), standard_intake.CAP)  # all of them would not fit
        self.assertLessEqual(len(said), standard_intake.CAP)
        self.assertTrue(said.startswith("Recorded 400 of 400 lines:\n\n"), said[:100])
        shown = [row for row in rows if f"\n- {row}\n" in said]
        self.assertEqual(shown, rows[:len(shown)])  # the first ones
        self.assertGreater(len(shown), 300)  # as many as fit: some 340 of these
        self.assertIn(f"\n- … and {400 - len(shown)} more recorded\n\n<!-- bulk-reply: 902 -->", said)
        self.assertTrue(said.endswith("\n\n<!-- bulk-reply: 902 -->"))

    def test_a_reason_is_given_once_for_the_lines_it_refuses(self):
        names = [d.name for d in self.ds.decls if d.is_project]
        out = self.process(comment(1, A, *(f"Reviewed-by: {names[k % len(names)]}" for k in range(400))))
        self.assertEqual(out.records, [])
        said = self.last(out)
        bare = standard_intake.BARE_YES.format(repo="o/r", bulk=1)
        each = [f"- line {k + 2} (`{names[k % len(names)]}`): {bare}" for k in range(400)]
        self.assertGreater(len("\n".join(each)), standard_intake.CAP)  # said for each line, it would not fit
        self.assertLessEqual(len(said), standard_intake.CAP)
        self.assertTrue(said.startswith(f"Not recorded:\n\n- {bare}\n"), said[:400])
        self.assertEqual(said.count(bare), 1)
        for k in range(400):
            self.assertIn(f"\n  - line {k + 2} (`{names[k % len(names)]}`)\n", said)
        self.assertNotIn("more not recorded", said)
        self.assertTrue(said.endswith("\n\nPost the corrected lines in a new comment.\n\n<!-- bulk-reply: 901 -->"))

    def test_a_reason_for_one_line_follows_it(self):
        out = self.process(comment(1, A, "Reviewed-by: Fixture.triple", "Reviewed-by: Fixture.nothing",
                                   "Reviewed-by: Fixture.double"))
        said = self.last(out)
        bare = standard_intake.BARE_YES.format(repo="o/r", bulk=1)
        self.assertIn(f"- {bare}\n  - line 2 (`Fixture.triple`)\n  - line 4 (`Fixture.double`)\n", said)
        self.assertIn("\n- line 3 (`Fixture.nothing`): `Fixture.nothing` is not a declaration", said)

    def test_the_refusals_are_cut_last(self):
        # What was not recorded is what the author must post again: it is listed first, and the rest of the room goes to
        # what was recorded.
        self.process(write(1, A, decl=self.LONG))
        approvals = [f"Approve: {self.LONG} — {VER1} — {CELLS}"] * 400
        out = self.process(comment(2, B, *approvals, "Reviewed-by: Fixture.nothing"))
        said = self.last(out)
        self.assertLessEqual(len(said), standard_intake.CAP)
        self.assertIn("\n- line 402 (`Fixture.nothing`): `Fixture.nothing` is not a declaration", said)
        self.assertRegex(said, r"\n- … and \d+ more recorded\n\nNot recorded:\n\n- line 402 ")


class IssueCase(IntakeCase):
    """Runs over the whole issue, as production makes them: each is given every comment of the issue, the bot's replies
    among them, and posts its own replies."""

    def setUp(self):
        super().setUp()
        self.issue: list[dict] = []

    def run_all(self):
        """One run over the issue as it stands; its replies are posted, as `apply` posts them."""
        out = standard_intake.process(BULK, self.issue, self.ctx)
        for _, text in out.replies:
            self.issue.append(bot(30 + len(self.issue), text))
        return out

    def rerun(self) -> None:
        """A later run over every comment: it records nothing."""
        before = len(self.store.records)
        self.assertEqual(self.run_all().records, [])
        self.assertEqual(len(Store.load(self.dir / "evidence").records), before)

    def quiet(self) -> None:
        """A later run over every comment: it records nothing, and says nothing."""
        out = self.run_all()
        self.assertEqual((out.records, out.replies), ([], []))

    def withdraw(self, r: dict, n: int) -> None:
        """Its author withdraws `r` at the n-th minute, with `/withdraw` on the record's own issue."""
        on_its_issue = {"kind": "comment", "ref": f"https://github.com/o/r/issues/7#issuecomment-{n}"}
        self.store.add([intake.status_record(r, "withdrawn", r["by"], f"2026-10-31T10:{n:02d}:00Z", on_its_issue)])


class FinalityTests(IssueCase):
    """A line is decided once. A line refused in a comment answered is not read again, however the store and the
    library move on; but two wait, named in the reply's marker, and are read again: a line read when there was no
    dataset of the library, and one whose declaration the latest dataset lacks (Ruling R20)."""

    def test_a_stale_approval_stays_refused_when_the_store_and_the_library_change(self):
        self.issue += [write(1, A), edit(2, A, VER1), approve(3, B, VER1)]
        out = self.run_all()
        self.assertEqual(len(out.records), 2)  # B named V1 while V2 was current
        self.assertTrue(self.issue[-1]["body"].endswith("\n\n<!-- bulk-reply: 903 -->"))  # nothing deferred
        # A withdrawal of V2 older than the approval reaches the store only now, as the migration's records will: as of
        # the approval, V1 was current after all. And the library moves on.
        v2 = out.records[1]
        self.store.add([intake.status_record(v2, "withdrawn", v2["by"], "2026-10-31T10:02:30Z",
                                             {"kind": "migration", "ref": "late"})])
        self.ctx.dataset = lambda commit: without(self.ds, "Fixture.double")
        self.quiet()

    def test_a_write_refused_for_a_test_not_in_the_library_stays_refused_when_it_is(self):
        self.ctx.dataset = lambda commit: without(self.ds, "Fixture.triple_two")
        self.issue += [write(1, A)]
        (n, said), = self.run_all().replies
        self.assertIn("line 2 (`Fixture.triple`): the test `Fixture.triple_two` is not a declaration that exists", said)
        self.assertTrue(said.endswith("\n\n<!-- bulk-reply: 901 -->"), said)
        self.ctx.dataset = lambda commit: self.ds  # the test is in the library now
        self.quiet()
        self.assertEqual(self.store.records, [])

    def test_lines_read_without_a_dataset_are_read_again_and_said_once_recorded(self):
        def missing(commit):
            raise LookupError(commit)
        self.ctx.dataset = missing
        test = "Test: Fixture.triple — Fixture.triple_two — its value at 2"
        c = comment(1, A, f"Approve: Fixture.triple — {VER1}", f"Write: Fixture.triple — {CELLS}", "~~~review", V1,
                    "~~~", test)
        k = len(c["body"].splitlines())  # the Test line, after the block
        self.issue += [c]
        (n, said), = self.run_all().replies
        self.assertIn("- line 2 (`Fixture.triple`): the line is `Approve: <decl> — <version> — <cells>`", said)
        self.assertIn(f"- there is no dataset of the library yet; it will be read again\n  - line 3\n  - line {k}\n", said)
        self.assertTrue(said.endswith(f"\n\n<!-- bulk-reply: 901 deferred: 3,{k} -->"), said)
        self.quiet()  # still none: nothing new to say
        self.ctx.dataset = lambda commit: self.ds
        out = self.run_all()
        version, test = out.records
        (n, said), = out.replies
        self.assertEqual((standard.kind_of(version), test["kind"]), ("version", "test"))
        self.assertTrue(said.startswith("Recorded 2 of 3 lines:\n\n"), said)
        self.assertIn(version["id"], said)
        self.assertNotIn("Not recorded", said)  # the line refused for good is not said again
        self.assertTrue(said.endswith("\n\n<!-- bulk-reply: 901 -->"), said)
        self.quiet()

    def test_a_line_read_without_a_dataset_whose_declaration_is_not_there_is_said_once(self):
        def missing(commit):
            raise LookupError(commit)
        self.ctx.dataset = missing
        self.issue += [approve(1, B, VER1, decl="Fixture.tripel")]
        (n, said), = self.run_all().replies
        self.assertIn("- line 2: there is no dataset of the library yet; it will be read again", said)
        self.ctx.dataset = lambda commit: self.ds
        # Read with a dataset, it waits for its declaration: that was never said, so it is said now, with its nearest names.
        (n, said), = self.run_all().replies
        self.assertIn("- line 2 (`Fixture.tripel`): `Fixture.tripel` is not a declaration of the library at `B`. "
                      "Did you mean `Fixture.triple`", said)
        self.assertTrue(said.endswith("\n\n<!-- bulk-reply: 901 deferred: 2 -->"), said)
        self.quiet()  # and once
        # A reply that quotes those words did not say them: else it would be said again on every run.
        self.issue += [approve(2, B, VER1, decl=standard_intake.NO_DATASET)]
        (n, said), = self.run_all().replies
        self.assertIn(f"(`{standard_intake.NO_DATASET}`)", said)
        self.quiet()

    def test_a_declaration_the_dataset_lacks_is_refused_once_and_recorded_once_it_has_it(self):
        lacking = without(self.ds, "Fixture.double")
        self.ctx.dataset = lambda commit: lacking
        c = comment(1, A, f"Write: Fixture.double — {CELLS}", "~~~review", V1, "~~~",
                    "Test: Fixture.double — Fixture.double_zero — its value at 0")
        k = len(c["body"].splitlines())  # the Test line, after the block
        self.issue += [c]
        (n, said), = self.run_all().replies
        self.assertIn("- `Fixture.double` is not a declaration of the library at `B`. Did you mean", said)
        self.assertIn(f"\n  - line 2 (`Fixture.double`)\n  - line {k} (`Fixture.double`)\n", said)
        self.assertTrue(said.endswith(f"\n\n<!-- bulk-reply: 901 deferred: 2,{k} -->"), said)
        self.quiet()  # read again, and still not there: a typo is said once
        self.ctx.dataset = lambda commit: self.ds  # a dataset built with it
        out = self.run_all()
        self.assertEqual([(r["kind"], r["subject"]["name"]) for r in out.records],
                         [("review", "Fixture.double"), ("test", "Fixture.double")])
        (n, said), = out.replies
        self.assertTrue(said.startswith("Recorded 2 of 2 lines:\n\n"), said)
        self.assertTrue(said.endswith("\n\n<!-- bulk-reply: 901 -->"), said)
        self.quiet()

    def test_a_comment_from_before_the_markers_is_never_read_again(self):
        self.issue += [approve(1, B, VER1), bot(2, "Not recorded: …")]  # answered before the replies named comments
        self.quiet()
        # A version older than the approval reaches the store only now, as the migration's records will: read again, the
        # approval would go in, late and unsaid.
        triple = self.ds.by_name["Fixture.triple"]
        self.store.add([rec.with_id({
            "schema": rec.SCHEMA, "kind": "review", "verdict": "accept", "subject": rec.subject_from_decl(triple, self.ds),
            "by": {"kind": "agent", "agent": {"tool": "Tau Ceti review migration", "model": "claude-opus-5-5"}},
            "at": "2026-10-31T10:00:30Z", "origin": {"kind": "migration", "ref": "late"}, "text": V1,
            "rubric": "ltb-rubric/1", "checked": CHECKED, "standard": {"spec": SPEC}})])
        self.quiet()


class LatestDatasetTests(IssueCase):
    """The latest dataset is looked up once a run, and what that look-up found, a failure too, is what every line of the run
    sees. evidence-store's `Datasets` lists the library's releases (a request to GitHub) at each look-up of the latest, so a
    line cost one; and a request failing partway through a run left some of its lines read and the rest waiting, which can
    make a typo first met during an outage be said never (Task 7b's review)."""

    def scripted(self, *outcomes) -> list[str]:
        """The dataset answers its look-ups by `outcomes`, one for each call and the last for those after it: a dataset to give
        or an exception to raise. Returns the commits asked for, one for each call."""
        calls: list[str] = []

        def dataset(commit):
            calls.append(commit)
            outcome = outcomes[min(len(calls), len(outcomes)) - 1]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        self.ctx.dataset = dataset
        return calls

    def test_every_line_of_a_run_sees_the_first_lookup(self):
        calls = self.scripted(self.ds, LookupError("the list of releases failed"))  # the second look-up would fail
        out = self.process(write(1, A), approve(2, B, VER1), comment(3, B, f"Approve: Fixture.double — {VER1} — {CELLS}"))
        self.assertEqual([standard.kind_of(r) for r in out.records], ["version", "approval"])
        self.assertEqual(calls, [""])
        said = out.replies[-1][1]
        self.assertIn("`Fixture.double` has no standard review yet", said)  # the line was read, not left waiting
        self.assertNotIn(standard_intake.NO_DATASET, said)

    def test_a_failure_is_what_the_whole_run_sees_and_the_next_run_looks_again(self):
        calls = self.scripted(LookupError("the list of releases failed"), self.ds)  # the second look-up would not
        c1, c2 = write(1, A), approve(2, B, VER1)
        out = self.process(c1, c2)
        self.assertEqual((out.records, calls), ([], [""]))
        self.assertEqual(len(out.replies), 2)
        for n, said in out.replies:
            self.assertIn(standard_intake.NO_DATASET, said)
        out = self.process(c1, c2)  # a later run: the memory of the last is gone
        self.assertEqual([standard.kind_of(r) for r in out.records], ["version", "approval"])
        self.assertEqual(calls, ["", ""])

    def test_only_the_latest_is_remembered(self):
        asked: list[str] = []
        look = standard_intake.latest_once(lambda commit: asked.append(commit) or commit + "!")
        self.assertEqual([look(""), look(""), look("a1"), look("a1")], ["!", "!", "a1!", "a1!"])
        self.assertEqual(asked, ["", "a1", "a1"])

    def test_lines_waiting_for_a_declaration_cost_one_lookup_a_run_and_no_pass_over_the_store(self):
        typos = [f"Approve: Fixture.tripel{k} — {VER1} — {CELLS}" for k in range(5)]  # no dataset will have them
        self.issue += [comment(1, A, *typos), comment(2, B, *typos, "Reviewed-by: Fixture.tripel")]
        calls = self.scripted(self.ds)
        with mock.patch.object(standard_intake, "as_of", wraps=standard_intake.as_of) as view:
            (n1, first), (n2, second) = self.run_all().replies
        self.assertEqual((calls, view.call_count), ([""], 0))
        self.assertTrue(first.endswith("\n\n<!-- bulk-reply: 901 deferred: 2,3,4,5,6 -->"), first)
        self.assertTrue(second.endswith("\n\n<!-- bulk-reply: 902 deferred: 2,3,4,5,6,7 -->"), second)
        for run in range(2):  # and each later run reads them again
            calls.clear()
            with mock.patch.object(standard_intake, "as_of", wraps=standard_intake.as_of) as view:
                self.quiet()
            self.assertEqual((calls, view.call_count), ([""], 0), f"run {run + 2}")

    def test_a_typo_first_met_during_an_outage_is_said_once(self):
        typo = f"Approve: Fixture.tripel — {VER1} — {CELLS}"
        self.issue += [comment(1, A, typo, f"Write: Fixture.double — {CELLS}", "~~~review", V1, "~~~")]
        self.scripted(LookupError("an outage"))
        (n, said), = self.run_all().replies
        self.assertIn("- there is no dataset of the library yet; it will be read again\n  - line 2\n  - line 3\n", said)
        # The outage goes on, but a look-up made once would not know: its first look-up fails and its second would not.
        calls = self.scripted(LookupError("an outage"), self.ds)
        out = self.run_all()
        self.assertEqual((out.records, out.replies, calls), ([], [], [""]))  # the typo's line and the write's both wait
        self.scripted(self.ds)
        out = self.run_all()
        (n, said), = out.replies
        self.assertTrue(said.startswith("Recorded 1 of 2 lines:\n\n"), said)
        self.assertEqual(said.count("line 2 (`Fixture.tripel`): `Fixture.tripel` is not a declaration of the library at "
                                    "`B`. Did you mean `Fixture.triple`"), 1)
        self.quiet()  # said once


class AsOfTests(IssueCase):
    """A line is decided as of its comment, against the records before it (`standard.order`), so what was refused
    stays refused however the store moves on, and nothing is recorded late and unsaid (Ruling R12)."""

    def test_versions_in_one_second_go_by_comment_and_line(self):
        # A write in comment 901 and an edit of it in comment 902, in one second: the edit is the later, for the intake and
        # for the page, though by time and then id the write would be.
        second = "2026-10-31T10:01:00Z"
        self.issue += [{**write(1, A), "created_at": second},
                       {**edit(2, A, VER1, note="says it never truncates"), "created_at": second}]
        wrote, edited = self.run_all().records
        self.assertGreater(wrote["id"], edited["id"])
        self.issue += [approve(3, B, VER2)]
        approval, = self.run_all().records
        self.assertEqual(approval["standard"]["approves"], VER2)
        seen = [standard.Seen(r, True, False, r is wrote) for r in (wrote, edited, approval)]
        self.assertEqual(standard.summary(seen)["version"], VER2)
        self.rerun()

    def test_a_version_from_elsewhere_in_the_comments_second_comes_before_it(self):
        # A record not of a line of a comment comes before the lines of its second, as the page orders versions: a
        # migration's version made in the second an approval of it was posted is current as of the approval. (A status
        # in that second does not count: test_a_status_in_the_comments_own_second_does_not_count.)
        second = "2026-10-31T10:01:00Z"
        self.store.add([rec.with_id({
            "schema": rec.SCHEMA, "kind": "review", "verdict": "accept", "at": second,
            "subject": rec.subject_from_decl(self.ds.by_name["Fixture.triple"], self.ds),
            "by": {"kind": "agent", "agent": {"tool": "Tau Ceti review migration", "model": "claude-opus-5-5"}},
            "origin": {"kind": "migration", "ref": "a version"}, "text": V1, "rubric": "ltb-rubric/1",
            "checked": CHECKED, "standard": {"spec": SPEC}})])
        self.issue += [{**approve(1, B, VER1), "created_at": second}]
        approval, = self.run_all().records
        self.assertEqual(approval["standard"]["approves"], VER1)
        self.rerun()

    def test_a_stale_edit_stays_refused_when_the_edit_it_missed_is_withdrawn(self):
        self.issue += [write(1, A), edit(2, A, VER1), edit(3, B, VER1, V1.replace("None.", ZERO), note="adds the zero")]
        out = self.run_all()
        self.assertEqual(len(out.records), 2)  # B's edit named V1 while V2 was current
        self.withdraw(out.records[1], 4)  # V1 is current again, but B wrote against V2
        self.rerun()

    def test_a_stale_approval_stays_refused_when_its_version_is_restored(self):
        self.issue += [write(1, A), edit(2, A, VER1), approve(3, B, VER1),
                       person(4, f"Restore: Fixture.triple — {VER1} — the edit added nothing true")]
        out = self.run_all()
        self.assertEqual([standard.act(r) for r in out.records], ["wrote", "edited", "restored"])  # B's named V1, at V2
        self.rerun()

    def test_one_comment_makes_one_version_after_withdrawals(self):
        both = comment(3, B, f"Edit: Fixture.triple — {VER1} — {CELLS} — adds the zero", "~~~review",
                       V1.replace("None.", ZERO), "~~~",
                       f"Edit: Fixture.triple — {VER2} — {CELLS} — adds the zero", "~~~review",
                       V2.replace("truncates.", f"truncates. {ZERO}"), "~~~")
        self.issue += [write(1, A), edit(2, A, VER1), both]
        out = self.run_all()
        # The comment's first Edit named V1 while V2 was current; its second went in.
        self.assertEqual(len(out.records), 3)
        self.withdraw(out.records[2], 4)
        self.withdraw(out.records[1], 5)  # V1 is current again
        self.rerun()

    def test_a_maintainers_first_write_stays_refused_when_reviews_arrive(self):
        self.issue += [person(1, "Write: Fixture.double", "~~~review", V1, "~~~")]
        self.assertEqual(self.run_all().records, [])  # no review of it to reply to
        self.issue += [comment(2, A, "Reviewed-by: Fixture.double — Twice its argument, as the docs say.")]
        # The yes, and not the write before it.
        self.assertEqual([r["kind"] for r in self.run_all().records], ["review"])
        self.rerun()

    def test_a_comment_makes_one_change_even_when_an_earlier_version_arrives_late(self):
        vx = V1.replace("three times its argument", "thrice its argument")
        both = comment(3, B, f"Edit: Fixture.triple — {standard.version_of(vx)} — {CELLS} — adds the zero",
                       "~~~review", vx.replace("None.", ZERO), "~~~",
                       f"Edit: Fixture.triple — {VER1} — {CELLS} — {NOTE}", "~~~review", V2, "~~~")
        self.issue += [write(1, A), both]
        out = self.run_all()
        # Its first Edit named a version the store did not hold; its second went in.
        self.assertEqual(len(out.records), 2)
        # A version older than the comment reaches the store only now, as the migration's records will; and the
        # comment's own edit is withdrawn, so that version is current as of the comment's first Edit, and now.
        wrote = out.records[0]
        self.store.add([rec.with_id({"schema": rec.SCHEMA, "kind": "comment", "subject": wrote["subject"],
                                     "by": {"kind": "agent", "agent": {"tool": "Tau Ceti review migration",
                                                                       "model": "claude-opus-5-5"}},
                                     "at": "2026-10-31T10:02:00Z", "origin": {"kind": "migration", "ref": "held"},
                                     "text": vx, "standard": {"spec": SPEC}, "links": {"replies_to": wrote["id"]}})])
        self.withdraw(out.records[1], 4)
        self.rerun()  # one change a comment, counting the change its later line made

    def test_a_line_does_not_see_the_lines_after_it(self):
        own = comment(3, B, f"Approve: Fixture.triple — {VER2} — {CELLS}",
                      f"Edit: Fixture.triple — {VER1} — {CELLS} — {NOTE}", "~~~review", V2, "~~~")
        self.issue += [write(1, A), own]
        # Its approval named the version its own later line makes: there was none to approve as of the approval.
        self.assertEqual([standard.act(r) for r in self.run_all().records], ["wrote", "edited"])
        self.rerun()

    def test_a_status_in_the_comments_own_second_does_not_count(self):
        self.issue += [write(1, A), edit(2, A, VER1)]
        v2 = self.run_all().records[1]
        self.withdraw(v2, 3)  # in the second the approval below was posted: not before it
        self.issue += [approve(3, B, VER1)]
        self.assertEqual(self.run_all().records, [])  # as of the approval, V2 was current
        self.rerun()

    def test_comments_in_one_second_go_by_their_ids(self):
        second = "2026-10-31T10:01:00Z"
        wrote, ticked = {**write(1, A), "created_at": second}, {**approve(2, B, VER1), "created_at": second}
        self.issue += [ticked, wrote]  # GitHub gives them in either order; the approval came after the write
        self.assertEqual([standard.kind_of(r) for r in self.run_all().records], ["version", "approval"])
        self.rerun()


class OldFormTests(IntakeCase):
    def test_old_forms_say_what_to_do_now(self):
        out = self.process(comment(1, A, "Reviewed-by: Fixture.triple"),
                           comment(2, A, "Reviewed-by: Fixture.double — Matches the fixture's docs, §2."),
                           person(3, "Reviewed-by: Fixture.one", login="alice"))
        bare, reasons, persons = [text for _, text in out.replies]
        self.assertIn("Approve:", bare)
        self.assertIn("in a comment on issue #1 (https://github.com/o/r/issues/1)", bare)  # where the approval goes
        self.assertNotIn("needs its text", bare)
        old, yes = out.records
        self.assertEqual((old["by"]["kind"], old["text"]), ("agent", "Matches the fixture's docs, §2."))
        self.assertNotIn("standard", old)
        self.assertIn("yes of the earlier form", reasons)
        self.assertIn(GUIDE, reasons)
        self.assertNotIn("AI-REVIEWS.md (", persons)  # a person's yes is no AI agent's
        # The review form says the same, and evidence_intake's `recorded` as this does.
        out, r = standard_intake.process_issue(form(7), self.ctx)
        self.assertIsNone(r)
        (n, said), = out.replies
        self.assertIn("Approve:", said)
        # The bulk issue, as the site's settings give it: the form's issue is not it.
        self.assertIn("in a comment on issue #1 (https://github.com/o/r/issues/1)", said)
        self.assertNotIn("needs its text", said)
        out, r = standard_intake.process_issue(form(8, rationale="Matches §1."), self.ctx)
        (n, said), = out.replies
        self.assertEqual((n, r["text"]), (8, "Matches §1."))
        self.assertIn(GUIDE, said)
        self.assertEqual(said, evidence_intake.recorded(r, "o/r"))
        # An agent's no without its reasons is told what evidence-store tells it.
        out, r = standard_intake.process_issue(form(9, "problem", category="junk"), self.ctx)
        (n, said), = out.replies
        self.assertIn("a review by an agent needs its text: why", said)
        self.assertNotIn("Approve:", said)


class InstallTests(IntakeCase):
    def run_intake(self, *args: str) -> dict:
        """evidence_intake's command line as the intake action runs it, with GitHub faked: the bulk issue holds
        A's write and B's approval of it."""
        bulk = {**BULK, "comments": 2, "closed_at": None, "body": ""}
        said = [write(1, A), approve(2, B, VER1)]
        with mock.patch.object(github, "recent_issues", lambda repo, since: [bulk]), \
                mock.patch.object(github, "issue", lambda repo, n: bulk), \
                mock.patch.object(github, "comments", lambda repo, n: said), \
                mock.patch.object(cli, "process", cli.process), \
                mock.patch.object(intake, "process_issue", intake.process_issue), \
                contextlib.redirect_stdout(io.StringIO()):
            code = evidence_intake.main(["intake", "--repo", "o/r", "--store", str(self.dir / "evidence"),
                                         "--dataset", str(DATASET), *args, "--outcome", str(self.dir / "outcome.json")])
        self.assertEqual(code, 0)
        return json.loads((self.dir / "outcome.json").read_text(encoding="utf-8"))

    def approvals(self) -> list[dict]:
        return [r for r in Store.load(self.dir / "evidence").records if "approves" in (r.get("standard") or {})]

    def test_install_covers_every_intake_run(self):
        outcome = self.run_intake("--sweep-days", "14")  # the six-hourly sweep, evidence-store's own
        approval, = self.approvals()
        self.assertEqual(approval["standard"]["approves"], VER1)
        self.assertIn(approval["id"], outcome["records"])
        self.assertEqual(outcome["replies"], [])  # a sweep announces nothing

    def test_an_event_run_too(self):
        event = self.dir / "event.json"
        event.write_text(json.dumps({"issue": {"number": 1}}), encoding="utf-8")
        outcome = self.run_intake("--event", str(event), "--event-name", "issue_comment")
        self.assertEqual(len(self.approvals()), 1)
        self.assertEqual([n for n, _ in outcome["replies"]], [1, 1])

    def test_install_reaches_the_forms_too(self):
        with mock.patch.object(cli, "process", cli.process), \
                mock.patch.object(intake, "process_issue", intake.process_issue):
            standard_intake.install()
            out = cli.process(form(8, rationale="Matches §1."), [], self.ctx)
        (n, said), = out.replies
        self.assertIn(GUIDE, said)


class DocsTests(unittest.TestCase):
    """AI-REVIEWS.md and the README as an agent follows them: each line they show is one the intake takes, each text
    passes the check, and AI-REVIEWS.md marks the one definition of a standard review, which the migration's prompt
    and `review_site.py guide` read without the rest of the file."""

    BEGIN, END = "<!-- standard-review:begin -->", "<!-- standard-review:end -->"

    def test_the_docs_examples_parse(self):
        root = HERE.parent
        docs = {name: (root / name).read_text(encoding="utf-8") for name in ("AI-REVIEWS.md", "README.md")}
        guide = docs["AI-REVIEWS.md"]
        self.assertEqual((guide.count(self.BEGIN), guide.count(self.END)), (1, 1))
        self.assertLess(guide.index(self.BEGIN), guide.index(self.END))
        marked = guide.split(self.BEGIN)[1].split(self.END)[0]
        self.assertNotIn("](#", marked)  # no link into the rest of the file, which its readers do not have
        for heading in standard.HEADINGS:
            self.assertIn(heading, marked)
        self.assertTrue([body for info, body in fences(marked)[0] if info == "review"], "the marked section's example")
        # The page's example of an approval (How to review) is the guide's too.
        page = (root / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn(re.search(r"Approve: TauCeti\.Foo\.bar — [^'\\]+", page)[0], guide)

        texts, examples, templates = [], [], []
        for name, doc in docs.items():
            found, prose = fences(doc)
            for info, body in found:
                if info == "review":
                    texts.append(body)
                    continue
                agent = intake.parse_agent_mark(body) is not None
                for cmd in standard_intake.commands(body):
                    if cmd.keyword in standard_intake.OURS:
                        (templates if PLACEHOLDER.search(" ".join(cmd.fields)) else examples).append((name, cmd, agent))
                        texts += [cmd.block] if cmd.block is not None else []
            for span in SPAN.findall(prose):
                if re.match(r"(Approve|Write|Edit|Restore):\s*\S", span):
                    cmd, = standard_intake.commands(span)
                    templates.append((name, cmd, None))
        self.assertTrue(templates)
        self.assertEqual({cmd.keyword for _, cmd, _ in examples} & {"Approve", "Write", "Edit"},
                         {"Approve", "Write", "Edit"})

        for text in texts:
            with self.subTest(text=text[:80]):
                self.assertEqual(standard.check(text), [])
        for name, cmd, _ in templates:  # a form, `<decl>` and all: the fields of an agent's line or a person's
            with self.subTest(doc=name, form=cmd.fields):
                self.assertTrue(any(standard_intake.given(cmd, line) is not None
                                    for (keyword, _), line in standard_intake.FORMS.items() if keyword == cmd.keyword))
        for name, cmd, agent in examples:
            with self.subTest(doc=name, line=cmd.line, keyword=cmd.keyword):
                line = standard_intake.FORMS.get((cmd.keyword, agent))
                self.assertIsNotNone(line, "an agent approves, and a person restores")
                f = standard_intake.given(cmd, line)
                self.assertIsNotNone(f, line)
                if agent:
                    self.assertEqual(standard.cells(f["cells"], RUBRIC.names)[1], "")
                for version in (f[key] for key in ("version", "parent", "earlier version") if key in f):
                    self.assertTrue(standard_intake.HEX.fullmatch(intake.clean(version).lower()), version)
                if cmd.keyword in ("Write", "Edit"):
                    self.assertIsNotNone(cmd.block, "a write or an edit gives its text")
                if cmd.keyword == "Edit":  # against the text it names, which the docs show too
                    versions = {standard.version_of(t): t for t in texts}
                    parent, = [t for v, t in versions.items() if v.startswith(intake.clean(f["parent"]).lower())]
                    self.assertEqual(standard.check(cmd.block, parent=parent, dropped=cmd.dropped, note=f["note"]), [])


if __name__ == "__main__":
    unittest.main()
