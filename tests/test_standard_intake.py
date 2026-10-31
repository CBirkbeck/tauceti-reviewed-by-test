import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from evidence_core import records as rec
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


class AnnounceTests(IntakeCase):
    """Which comments are answered: those that no reply of the bot names yet, and none older than its replies from
    before the markers. Their records are made either way."""

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
        self.assertEqual([r["kind"] for r in out.records], ["test"])  # recorded all the same
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


class AsOfTests(IntakeCase):
    """Each run reads every comment of the issue again, the bot's replies among them, as production does. A line is
    decided as of its comment, so what was refused stays refused however the store moves on, and nothing is recorded
    late and unsaid (Ruling R12)."""

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

    def withdraw(self, r: dict, n: int) -> None:
        """Its author withdraws `r` at the n-th minute, with `/withdraw` on the record's own issue."""
        on_its_issue = {"kind": "comment", "ref": f"https://github.com/o/r/issues/7#issuecomment-{n}"}
        self.store.add([intake.status_record(r, "withdrawn", r["by"], f"2026-10-31T10:{n:02d}:00Z", on_its_issue)])

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


if __name__ == "__main__":
    unittest.main()
