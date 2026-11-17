"""The rules the intake keeps since the bulk run of 2026-11-17: no one reviews their own work (`authorship`), an account
withdraws what it filed (`Withdraw:`), an edit that moves only links is an approval, a roadmap target named is one
TauCetiRoadmap has, a text longer than the guide is said to be, and a Check the roadmap gives by a Lean name or in prose
is recorded as one. The invented logins are alice, bob and carol; `boss` is a maintainer."""
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))
import authorship  # noqa: E402
import standard  # noqa: E402
import standard_intake  # noqa: E402
from evidence_store import intake  # noqa: E402
from test_standard_intake import (A, B, CELLS, NOTE, V1, V2, VER1, VER2, IntakeCase, approve, comment,  # noqa: E402
                                  person, write)

#: An agent through alice's account, and through bob's.
ALICE, BOB = "alice", "bob"


def by(login: str, *lines: str, n: int, association: str = "NONE") -> dict:
    return comment(n, *lines, login=login, association=association)


def with_authors(ds, authors: dict[str, list[str]], unknown: dict[str, int] | None = None):
    """The dataset with the facet `authors` (scripts/authors.py), held in memory."""
    rows = {name: [{"decl": name, "authors": a, "commits": 1, **({"unknown": unknown[name]} if name in (unknown or {})
                                                                  else {})}] for name, a in authors.items()}
    meta = {**ds.meta, "facets": [*ds.meta.get("facets", []), {"name": "authors", "file": "facets/authors.jsonl"}]}
    return replace(ds, meta=meta, _facets={**ds._facets, "authors": rows})


class OwnWorkTests(IntakeCase):
    def setUp(self):
        super().setUp()
        self.ds = with_authors(self.ds, {"Fixture.triple": ["alice", "carol"], "Fixture.double": []},
                               unknown={"Fixture.double": 2})

    def test_an_author_approves_writes_and_edits_nothing(self):
        out = self.process(by(ALICE, A, f"Write: Fixture.triple — {CELLS}", "~~~review", V1, "~~~", n=1))
        self.assertEqual(out.records, [])
        said = self.last(out)
        for words in ("`Fixture.triple` is the work of alice", "`alice`", "own work", "AI-REVIEWS.md"):
            self.assertIn(words, said)
        version, = self.process(write(2, B)).records  # by another account
        out = self.process(by(ALICE, A, f"Approve: Fixture.triple — {VER1} — {CELLS}", n=3),
                           by(ALICE, A, f"Edit: Fixture.triple — {VER1} — {CELLS} — {NOTE}", "~~~review", V2, "~~~", n=4))
        self.assertEqual(out.records, [])
        self.assertTrue(all("is the work of alice" in text for _, text in out.replies))
        # Logins are compared in any case, as GitHub compares them.
        self.assertEqual(self.process(by("Carol", A, f"Approve: Fixture.triple — {VER1} — {CELLS}", n=5)).records, [])
        # A maintainer who is an author is refused too; a restore approves nothing, and is theirs to make.
        self.assertEqual(self.process(by("carol", f"Edit: Fixture.triple — {VER1} — {NOTE}", "~~~review", V2, "~~~",
                                         n=6, association="OWNER")).records, [])
        # Someone else approves it.
        self.assertEqual(len(self.process(by(BOB, A, f"Approve: Fixture.triple — {VER1} — {CELLS}", n=7)).records), 1)

    def test_one_persons_other_account_is_theirs_too(self):
        self.process(write(1, B))
        with mock.patch.object(authorship, "groups", return_value=(("alice", "alice-two"),)):
            out = self.process(by("alice-two", A, f"Approve: Fixture.triple — {VER1} — {CELLS}", n=2))
        self.assertEqual(out.records, [])
        self.assertIn("names `alice` among its authors", self.last(out))

    def test_what_the_reply_says_when_authorship_is_partly_known(self):
        out = self.process(by(BOB, A, f"Write: Fixture.double — {CELLS}", "~~~review", V1.replace("triple", "double"),
                              "~~~", n=1))
        self.assertEqual(len(out.records), 1)
        said = self.last(out)
        self.assertIn("2 of the people in its history have no GitHub login the site knows", said)
        self.assertNotIn("Authorship was not checked", said)


class UncheckedTests(IntakeCase):
    def test_a_dataset_that_records_no_authors_is_said_once(self):
        out = self.process(comment(1, A, f"Write: Fixture.triple — {CELLS}", "~~~review", V1, "~~~",
                                   f"Write: Fixture.double — {CELLS}", "~~~review", V1.replace("triple", "double"), "~~~"))
        self.assertEqual(len(out.records), 2)
        self.assertEqual(self.last(out).count("Authorship was not checked"), 1)


class WithdrawTests(IntakeCase):
    def withdraw(self, n: int, login: str, version: str, note: str = "it was meant for another declaration",
                 agent: str = A, decl: str = "Fixture.triple") -> dict:
        return by(login, agent, f"Withdraw: {decl} — {version} — {note}", n=n)

    def test_an_edit_withdrawn_puts_back_the_text_it_replaced(self):
        self.process(by(ALICE, A, f"Write: Fixture.triple — {CELLS}", "~~~review", V1, "~~~", n=1))
        self.process(by(BOB, B, f"Edit: Fixture.triple — {VER1} — {CELLS} — {NOTE}", "~~~review", V2, "~~~", n=2))
        self.process(by(ALICE, A, f"Approve: Fixture.triple — {VER2} — {CELLS}", n=3))
        out = self.process(self.withdraw(4, BOB, VER2[:8]))
        status, = out.records
        edit = next(r for r in self.store.records if standard.kind_of(r) == "version" and r["text"] == V2.rstrip("\n"))
        self.assertEqual((status["kind"], status["target"], status["state"], status["text"]),
                         ("status", edit["id"], "withdrawn", "it was meant for another declaration"))
        self.assertIn(f"Recorded the withdrawal `{status['id']}` of `{edit['id']}`", self.last(out))
        # The text it replaced is current again; the approval of the withdrawn text approves a text no longer current.
        out = self.process(approve(5, B, VER2), approve(6, B, VER1))
        self.assertEqual([r["standard"]["approves"] for r in out.records], [VER1])
        self.assertIn(f"which is `{VER1}`", out.replies[0][1])

    def test_withdrawing_the_only_text_leaves_none(self):
        self.process(by(ALICE, A, f"Write: Fixture.triple — {CELLS}", "~~~review", V1, "~~~", n=1))
        self.assertEqual(len(self.process(self.withdraw(2, ALICE, VER1, agent="")).records), 1)  # no agent line needed
        self.assertEqual(len(self.process(write(3, B, V2)).records), 1)  # a first text may be written again

    def test_an_approval_withdrawn(self):
        self.process(write(1, A))
        approval, = self.process(by(BOB, B, f"Approve: Fixture.triple — {VER1} — {CELLS}", n=2)).records
        status, = self.process(self.withdraw(3, BOB, VER1, agent=B)).records
        self.assertEqual(status["target"], approval["id"])
        self.assertEqual(intake.current_state(self.ctx, approval), "withdrawn")
        # Withdrawn once, there is nothing of bob's left to withdraw.
        out = self.process(self.withdraw(4, BOB, VER1, agent=B))
        self.assertEqual(out.records, [])
        self.assertIn("names no approval, write or edit", self.last(out))

    def test_only_what_ones_own_account_filed(self):
        self.process(write(1, A))  # through the maintainer's account
        out = self.process(self.withdraw(2, BOB, VER1), by(BOB, A, "Withdraw: Fixture.triple", n=3),
                           by(BOB, A, f"Withdraw: Fixture.triple — {VER1[:7]} — why", n=4))
        self.assertEqual(out.records, [])
        mine, short, few = [text for _, text in out.replies]
        self.assertIn("that bob filed and has not withdrawn", mine)
        self.assertIn("`Withdraw: <decl> — <version> — <note>`", short)
        self.assertIn("names no approval", few)  # fewer than eight digits name no version

    def test_a_withdrawal_and_an_edit_of_one_review_in_one_comment(self):
        self.process(by(ALICE, A, f"Write: Fixture.triple — {CELLS}", "~~~review", V1, "~~~", n=1))
        out = self.process(by(ALICE, A, f"Withdraw: Fixture.triple — {VER1} — wrong declaration",
                              f"Edit: Fixture.triple — {VER1} — {CELLS} — {NOTE}", "~~~review", V2, "~~~", n=2))
        self.assertEqual([r["kind"] for r in out.records], ["status"])
        self.assertIn("a comment changes it once", self.last(out))

    def test_a_withdrawal_says_why(self):
        self.process(by(ALICE, A, f"Write: Fixture.triple — {CELLS}", "~~~review", V1, "~~~", n=1))
        out = self.process(by(ALICE, A, f"Withdraw: Fixture.triple — {VER1}", n=2))
        self.assertEqual(out.records, [])
        self.assertIn("a withdrawal says why", self.last(out))


class LinkEditTests(IntakeCase):
    LINKED = V1.replace("- Fixture documentation, §1.",
                        "- [Fixture documentation, §1](https://example.org/blob/0123456789abcdef/docs.md#L3).")

    def test_an_edit_that_moves_only_links_is_an_approval(self):
        self.process(write(1, A, self.LINKED))
        moved = self.LINKED.replace("0123456789abcdef", "fedcba9876543210").replace("#L3", "#L4")
        out = self.process(by(BOB, B, f"Edit: Fixture.triple — {standard.version_of(self.LINKED)} — {CELLS} — "
                                      "the link at the current commit", "~~~review", moved, "~~~", n=2))
        self.assertEqual(out.records, [])
        self.assertIn("approve the text instead", self.last(out))

    def test_an_edit_that_adds_a_roadmap_line_is_recorded_as_one(self):
        self.process(write(1, A))
        roadmap = V1.replace("- Fixture documentation, §1.\n", "- Fixture documentation, §1.\n- TauCetiRoadmap, "
                             "Arithmetic, [Layer 1](https://github.com/TauCetiProject/TauCetiRoadmap/blob/abc1234/"
                             "TauCetiRoadmap/Arithmetic/README.md#L10), which states it.\n")
        out = self.process(by(BOB, B, f"Edit: Fixture.triple — {VER1} — {CELLS} — adds the roadmap target",
                              "~~~review", roadmap, "~~~", n=2))
        r, = out.records
        self.assertEqual(r["standard"]["scope"], "roadmap")
        self.assertIn(standard_intake.ROADMAP_EDIT, self.last(out))
        # An edit that changes something else besides is an edit like any other.
        r, = self.process(by(ALICE, A, f"Edit: Fixture.triple — {standard.version_of(roadmap)} — {CELLS} — {NOTE}",
                             "~~~review", roadmap.replace("None.", "On ℕ it never truncates."), "~~~", n=3)).records
        self.assertNotIn("scope", r["standard"])


class TargetTests(IntakeCase):
    def setUp(self):
        super().setUp()
        standard_intake.ROADMAP_NAMES[str(self.ds.root)] = frozenset({"vanDerBlij", "Layer", "1"})
        self.addCleanup(standard_intake.ROADMAP_NAMES.pop, str(self.ds.root), None)

    def text(self, target: str) -> str:
        return V1.replace("- Fixture documentation, §1.", f"- TauCetiRoadmap, Arithmetic, Layer 1, target `{target}`.")

    def test_a_target_the_roadmap_does_not_have_is_refused(self):
        out = self.process(write(1, A, self.text("sharp-perimeter-inequality")))
        self.assertEqual(out.records, [])
        said = self.last(out)
        self.assertIn("roadmap target `sharp-perimeter-inequality`", said)
        self.assertIn("`tauceti-target` id", said)
        self.assertEqual(len(self.process(write(2, A, self.text("vanDerBlij"))).records), 1)

    def test_a_text_that_names_one_is_edited_not_approved(self):
        standard_intake.ROADMAP_NAMES.pop(str(self.ds.root))  # written before the dataset recorded the names
        with mock.patch.object(standard_intake, "roadmap_names", return_value=None):
            self.process(write(1, A, self.text("an-invented-id")))
        version = standard.version_of(self.text("an-invented-id"))
        standard_intake.ROADMAP_NAMES[str(self.ds.root)] = frozenset({"vanDerBlij"})
        out = self.process(approve(2, B, version))
        self.assertEqual(out.records, [])
        self.assertIn("edit it instead", self.last(out))


class LengthTests(IntakeCase):
    def test_a_long_text_is_recorded_with_its_length(self):
        long = V1.replace("None.", " ".join(["word"] * 420))
        out = self.process(write(1, A, long))
        self.assertEqual(len(out.records), 1)
        self.assertIn(f"its text is {standard.words(long)} words, over the 150 to 400", self.last(out))
        self.assertNotIn("words, over", self.last(self.process(write(2, A, V1, decl="Fixture.double"))))


class CheckFormTests(IntakeCase):
    def text(self, *checks: str) -> str:
        return V1.replace("- `Fixture.triple_two` — its value at 2", "\n".join(["- `Fixture.triple_two` — its value at 2",
                                                                              *checks]))

    def test_a_check_named_by_a_lean_name_or_given_in_prose(self):
        good = self.text("- Check `Fixture.triple_one` — passes: its value at 1",
                         "- Check `Fixture.triple_seven` — missing: no declaration has that name",
                         '- Check "Tripling 0 gives 0", `Fixture.triple_comm` — passes: it commutes',
                         '- Check "In ℤ it is odd at odd numbers" — missing: nothing in the library states it')
        self.assertEqual(len(self.process(write(1, A, good)).records), 1)
        self.assertEqual(standard.items(good).checks, ["Fixture.triple_one", "Fixture.triple_seven",
                                                       "Tripling 0 gives 0", "In ℤ it is odd at odd numbers"])

    def test_what_is_refused_of_them(self):
        cases = {"- Check `Fixture.triple_seven` — passes: it does": "is not a declaration that exists",
                 "- Check `Fixture.triple_one` — missing: none": "is a declaration of the library",
                 '- Check "Tripling 0 gives 0", `Fixture.nowhere` — passes: yes': "`Fixture.nowhere`, which is not",
                 '- Check "Tripling 0 gives 0": its value at 0': "says nothing of what was found"}
        for n, (bullet, why) in enumerate(cases.items(), 1):
            out = self.process(write(n, A, self.text(bullet), decl="Fixture.double" if n % 2 else "Fixture.triple"))
            self.assertEqual(out.records, [], bullet)
            self.assertIn(why, self.last(out), bullet)

    def test_an_edit_keeps_a_prose_check_reworded_by_a_word(self):
        old = self.text('- Check "In ℤ it is odd at odd numbers and even at even ones" — missing: nothing states it')
        self.process(write(1, A, old))
        new = old.replace("it is odd at odd numbers", "it is odd at the odd numbers")
        self.assertEqual(len(self.process(by(BOB, B, f"Edit: Fixture.triple — {standard.version_of(old)} — {CELLS} — "
                                                     f"{NOTE}", "~~~review", new.replace("None.", "On ℕ."), "~~~",
                                             n=2)).records), 1)
        gone = new.replace('- Check "In ℤ it is odd at the odd numbers and even at even ones" — missing: nothing '
                           'states it\n', "")
        out = self.process(by(BOB, B, f"Edit: Fixture.triple — {standard.version_of(new.replace('None.', 'On ℕ.'))} — "
                                      f"{CELLS} — {NOTE}", "~~~review", gone, "~~~", n=3))
        self.assertIn("the edit drops the Check", self.last(out))


if __name__ == "__main__":
    unittest.main()
