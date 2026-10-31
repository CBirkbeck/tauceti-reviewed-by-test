import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from evidence_core.dataset import Dataset
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
BULK = {"number": 1, "labels": [{"name": "evidence:bulk"}]}
BOT = {"id": 1, "user": {"login": "github-actions[bot]", "type": "Bot"}, "body": "Not recorded: …",
       "created_at": "2026-10-31T10:02:00Z", "author_association": "NONE",
       "html_url": "https://github.com/o/r/issues/1#issuecomment-1"}


def url(n: int) -> str:
    return f"https://github.com/o/r/issues/1#issuecomment-{900 + n}"


def comment(n: int, *lines: str, login: str = "CBirkbeck", association: str = "OWNER") -> dict:
    """Comment `n` on the bulk issue, at the n-th minute: its lines, by `login` (an agent through it, when a
    line is an agent mark)."""
    return {"id": 900 + n, "user": {"login": login, "type": "User"}, "body": "\n".join(lines),
            "created_at": f"2026-10-31T10:{n:02d}:00Z", "author_association": association, "html_url": url(n)}


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
        self.assertIn("line 15", self.last(out))
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

    def test_a_maintainers_write_replies_to_the_latest_review(self):
        out = self.process(person(1, "Write: Fixture.double", "~~~review", V1, "~~~"))
        self.assertEqual(out.records, [])  # a comment needs a review to reply to, and there is none
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
        out = self.process(c)
        self.assertEqual((out.records, out.replies), ([], []))
        self.assertEqual(len(Store.load(self.dir / "evidence").records), 2)

    def test_refusals_are_said_once(self):
        c1 = comment(1, A, f"Approve: Fixture.triple — {VER1} — {CELLS}",
                     "Test: Fixture.triple — Fixture.triple_two — its value at 2")
        c3 = comment(3, A, f"Approve: Fixture.double — {VER1} — {CELLS}")
        out = self.process(c1, BOT, c3)
        self.assertEqual([r["kind"] for r in out.records], ["test"])  # recorded all the same
        said = self.last(out)
        self.assertEqual(len(out.replies), 1)
        self.assertIn("Fixture.double", said)
        self.assertNotIn("Fixture.triple", said)
        self.assertEqual(self.process(c1, BOT, c3, announce=False).replies, [])  # a sweep says nothing

    def test_a_missing_dataset_is_read_again(self):
        def missing(commit):
            raise LookupError(commit)
        self.ctx.dataset = missing
        out = self.process(write(1, A))
        self.assertEqual(out.records, [])
        self.assertIn("line 2: there is no dataset of the library yet; it will be read again", self.last(out))


class OldFormTests(IntakeCase):
    def test_old_forms_say_what_to_do_now(self):
        out = self.process(comment(1, A, "Reviewed-by: Fixture.triple"),
                           comment(2, A, "Reviewed-by: Fixture.double — Matches the fixture's docs, §2."),
                           person(3, "Reviewed-by: Fixture.one", login="alice"))
        bare, reasons, persons = [text for _, text in out.replies]
        self.assertIn("Approve:", bare)
        self.assertNotIn("needs its text", bare)
        old, yes = out.records
        self.assertEqual((old["by"]["kind"], old["text"]), ("agent", "Matches the fixture's docs, §2."))
        self.assertNotIn("standard", old)
        self.assertIn("yes of the earlier form", reasons)
        self.assertIn(standard_intake.APPROVE_INSTEAD, reasons)
        self.assertNotIn(standard_intake.APPROVE_INSTEAD, persons)  # a person's yes is no AI agent's
        # The review form says the same, and evidence_intake's `recorded` as this does.
        out, r = standard_intake.process_issue(form(7), self.ctx)
        self.assertIsNone(r)
        (n, said), = out.replies
        self.assertIn("Approve:", said)
        self.assertNotIn("needs its text", said)
        out, r = standard_intake.process_issue(form(8, rationale="Matches §1."), self.ctx)
        (n, said), = out.replies
        self.assertEqual((n, r["text"]), (8, "Matches §1."))
        self.assertIn(standard_intake.APPROVE_INSTEAD, said)
        self.assertEqual(said, evidence_intake.recorded(r))
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
        self.assertIn(standard_intake.APPROVE_INSTEAD, said)


if __name__ == "__main__":
    unittest.main()
