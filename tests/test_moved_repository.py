"""The review repository moved, CBirkbeck/tauceti-reviewed-by-test to TauCetiProject/TauCetiReviewSite: GitHub keeps its
issues, their numbers and their comments' ids, and names them under the new name from then on, while the store's
records, which are never changed, name them under the old one. Intake compares origins by their keys
(common.origin_key), so nothing recorded before the move is recorded again, and what is new is recorded under the new
name; the answerer and the fixer find a record's issue under either name."""
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
from evidence_core.store import Store
from evidence_store import cli, forms, github, intake

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "scripts"))
import common  # noqa: E402
import evidence_intake  # noqa: E402
import pr_links  # noqa: E402
import standard_intake  # noqa: E402

from answerer.items import issue_of  # noqa: E402
from fixer import pick  # noqa: E402

OLD, NEW = "CBirkbeck/tauceti-reviewed-by-test", "TauCetiProject/TauCetiReviewSite"
DATASET = HERE / "fixtures" / "dataset-b"
LIB = "TauCetiProject/TauCeti"
#: The settings while the move is under way: the fix merged, the settings still naming the old repository, and GitHub
#: already naming it the new way.
BEFORE = {**common.load_settings(), "repo": OLD}
BEFORE.pop("formerly", None)
#: The settings once the move is merged.
AFTER = {**common.load_settings(), "repo": NEW, "formerly": [OLD]}


def user(login: str) -> dict:
    return {"login": login, "type": "User"}


def at(day: int, minute: int = 0) -> str:
    return f"2026-11-{day:02d}T10:{minute:02d}:00Z"


class World:
    """GitHub as intake reads it, naming the repository `repo`: the bulk issue #1 with one comment of two lines, nobody's
    reply to it yet; a no, #7, with one comment; a question, #8, closed by its author; and a test, #9, recorded and not
    yet closed. Each request names the repository as the run was told to."""

    def __init__(self, repo: str):
        self.repo = repo
        self.issues = {
            1: {"number": 1, "labels": [{"name": "evidence:bulk"}], "state": "open", "closed_at": None, "body": "",
                "user": user("CBirkbeck"), "created_at": at(1)},
            7: self.form(7, "problem", decl="Fixture.triple", category="other", rationale="It should say n is natural."),
            8: {**self.form(8, "question", decl="Fixture.double", question="Why ℕ?"), "state": "closed",
                "closed_at": at(3)},
            9: self.form(9, "test", decl="Fixture.triple", test="Fixture.triple_two", checks="its value at 2"),
        }
        self.comments = {1: [self.comment(1, 1001, "alice", "Test: Fixture.triple — Fixture.triple_two — at 2",
                                          "Test: Fixture.double — Fixture.double_two — at 2")],
                         7: [self.comment(7, 7001, "bob", "I agree: it should.")], 8: [], 9: []}
        self.events = {8: [{"id": 8001, "event": "closed", "actor": user("alice"), "created_at": at(3),
                            "state_reason": "completed"}]}

    @staticmethod
    def form(n: int, kind: str, **answers) -> dict:
        return {"number": n, "labels": [{"name": forms.FORMS[kind]["label"]}], "state": "open", "closed_at": None,
                "user": user("alice"), "created_at": at(2), "body": forms.body(kind, answers)}

    def comment(self, n: int, cid: int, login: str, *lines: str) -> dict:
        return {"id": cid, "user": user(login), "author_association": "NONE", "body": "\n".join(lines),
                "created_at": at(4, cid % 60), "html_url": f"https://github.com/{self.repo}/issues/{n}#issuecomment-{cid}"}

    def asked(self, repo: str) -> None:
        if repo != self.repo:
            raise AssertionError(f"asked GitHub about {repo}, not {self.repo}")

    def patches(self):
        def issue(repo, n):
            self.asked(repo)
            return {**self.issues[n], "comments": len(self.comments[n])}

        def comments(repo, n):
            self.asked(repo)
            return self.comments[n]

        def events(repo, n):
            self.asked(repo)
            return self.events.get(n, [])

        def recent(repo, since):
            self.asked(repo)
            return [issue(repo, n) for n in sorted(self.issues)]

        def gh_json(*args):  # the open issues by label, for `--sweep-open`
            self.asked(args[-1].split("repos/")[1].split("/issues")[0])
            label = args[-1].split("labels=")[1].split("&")[0]
            return [issue(self.repo, n) for n, i in sorted(self.issues.items())
                    if i["state"] == "open" and label in {x["name"] for x in i["labels"]}]

        return [mock.patch.object(github, "issue", issue), mock.patch.object(github, "comments", comments),
                mock.patch.object(github, "events", events), mock.patch.object(github, "recent_issues", recent),
                mock.patch.object(github, "gh_json", gh_json)]


class MovedIntakeCase:
    """The intake run before the move, under the old name, then after it, under the new: with `SETTINGS` as they
    stand during the move (BEFORE) or after it (AFTER)."""

    SETTINGS: dict = {}

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        (self.dir / "evidence" / "records").mkdir(parents=True)
        shutil.copy(HERE.parent / "evidence" / "store.json", self.dir / "evidence" / "store.json")
        self.outcome = self.dir / "outcome.json"

    def run_intake(self, world: World, *sweep: str) -> dict:
        """evidence_intake's command line as the intake action runs it, for the repository GitHub names `world.repo`:
        the six-hourly sweep of the last 14 days unless `sweep` says otherwise. What `install` replaces is put back."""
        with contextlib.ExitStack() as stack:
            for p in [mock.patch.object(common, "load_settings", lambda path=None: self.SETTINGS),
                      mock.patch.object(cli, "process", cli.process),
                      mock.patch.object(intake, "process_issue", intake.process_issue),
                      mock.patch.object(intake, "process_comment", intake.process_comment),
                      mock.patch.object(intake, "issue_number", intake.issue_number), *world.patches()]:
                stack.enter_context(p)
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            code = evidence_intake.main(["intake", "--repo", world.repo, "--store", str(self.dir / "evidence"),
                                         "--dataset", str(DATASET), *(sweep or ("--sweep-days", "14")),
                                         "--outcome", str(self.outcome)])
        self.assertEqual(code, 0)
        return json.loads(self.outcome.read_text(encoding="utf-8"))

    def records(self) -> list[dict]:
        return Store.load(self.dir / "evidence").records

    def recorded_before(self) -> list[dict]:
        """What the intake recorded before the move: each of the world's issues, comments, lines and events once."""
        self.run_intake(World(OLD))
        before = self.records()
        refs = sorted(r["origin"]["ref"] for r in before)
        self.assertEqual(refs, sorted([
            f"{OLD}#7", f"{OLD}#8", f"{OLD}#8/event/8001", f"{OLD}#9",
            f"https://github.com/{OLD}/issues/1#issuecomment-1001/line/1",
            f"https://github.com/{OLD}/issues/1#issuecomment-1001/line/2",
            f"https://github.com/{OLD}/issues/7#issuecomment-7001"]))
        return before

    def test_nothing_recorded_before_the_move_is_recorded_again(self):
        before = self.recorded_before()
        outcome = self.run_intake(World(NEW))  # the six-hourly sweep of the last 14 days, every issue read again
        self.assertEqual(outcome["records"], [])
        self.assertEqual(self.records(), before)
        outcome = self.run_intake(World(NEW), "--sweep-open")  # an event's run: the open issues
        self.assertEqual(outcome["records"], [])
        self.assertEqual(self.records(), before)

    def test_a_new_comment_is_recorded_once_under_the_new_name(self):
        before = self.recorded_before()
        world = World(NEW)
        world.comments[7].append(world.comment(7, 7002, "carol", "Agreed, and the docstring says so too."))
        outcome = self.run_intake(world)
        new = self.records()[len(before):]
        self.assertEqual(self.records()[:len(before)], before)
        self.assertEqual(len(new), 1)
        self.assertEqual(outcome["records"], [new[0]["id"]])
        self.assertEqual(new[0]["origin"], {"kind": "comment", "ref": f"https://github.com/{NEW}/issues/7#issuecomment-7002"})
        self.assertEqual(new[0]["links"]["replies_to"], next(r["id"] for r in before if r["origin"]["ref"] == f"{OLD}#7"))
        self.assertEqual(self.run_intake(world)["records"], [])  # and read again, it is recorded already

    def test_a_new_line_on_the_bulk_issue_is_recorded_once_under_the_new_name(self):
        before = self.recorded_before()
        world = World(NEW)
        world.comments[1].append(world.comment(1, 1002, "alice", "Test: Fixture.triple — Fixture.triple_one — at 1"))
        self.run_intake(world)
        new = self.records()[len(before):]
        self.assertEqual([r["origin"] for r in new],
                         [{"kind": "comment", "ref": f"https://github.com/{NEW}/issues/1#issuecomment-1002/line/1"}])

    def test_the_open_sweep_finishes_an_issue_recorded_under_the_old_name(self):
        self.recorded_before()  # its outcome closed the test, #9, and the reply was never made: still open
        outcome = self.run_intake(World(NEW), "--sweep-open")
        self.assertEqual(outcome["records"], [])
        self.assertIn([9, "completed"], outcome["close"])
        self.assertIn(9, [n for n, _ in outcome["replies"]])


class DuringTheMoveTests(MovedIntakeCase, unittest.TestCase):
    """GitHub names the new repository, and the settings still the old one: the fix merged before the move."""
    SETTINGS = BEFORE


class AfterTheMoveTests(MovedIntakeCase, unittest.TestCase):
    """The settings name the new repository, and the old one as `formerly`."""
    SETTINGS = AFTER


class OriginKeyTests(unittest.TestCase):
    def test_either_form_under_any_name_has_the_new_name(self):
        key = common.origin_key(NEW, AFTER)
        for ref, want in [
                (f"{OLD}#7", f"{NEW}#7"),
                (f"{OLD}#8/event/8001", f"{NEW}#8/event/8001"),
                (f"{OLD}#1 comment 5780057622", f"{NEW}#1 comment 5780057622"),
                (f"https://github.com/{OLD}/issues/1#issuecomment-9/line/3", f"https://github.com/{NEW}/issues/1#issuecomment-9/line/3"),
                (f"https://github.com/{OLD}/blob/main/evidence/records/a.jsonl#L2",
                 f"https://github.com/{NEW}/blob/main/evidence/records/a.jsonl#L2"),
                (f"https://github.com/{OLD.lower()}/issues/3", f"https://github.com/{NEW}/issues/3"),  # GitHub's names ignore case
                (f"{NEW}#7", f"{NEW}#7"),
                (f"https://github.com/{NEW}/issues/1#issuecomment-9/line/3", f"https://github.com/{NEW}/issues/1#issuecomment-9/line/3")]:
            self.assertEqual(key(ref), want, ref)

    def test_other_refs_are_their_own_keys(self):
        key = common.origin_key(NEW, AFTER)
        for ref in [f"{OLD}2#7", f"https://github.com/{OLD}-2/issues/7", f"https://github.com/{LIB}/pull/12",
                    "voyager 2026-10-24", "o/r#7", "", f"x{OLD}#7"]:
            self.assertEqual(key(ref), ref)

    def test_during_the_move_the_settings_name_is_a_former_one(self):
        key = common.origin_key(NEW, BEFORE)  # the settings still name the old repository; GitHub, the new
        self.assertEqual(key(f"{OLD}#7"), f"{NEW}#7")
        self.assertEqual(common.origin_key(OLD, BEFORE)(f"{OLD}#7"), f"{OLD}#7")  # before the move, nothing changes

    def test_found_as_evidence_cores_store_finds_them_but_by_key(self):
        records = [{"id": "a", "origin": {"kind": "issue", "ref": f"{OLD}#7"}}, {"id": "b", "origin": None}, {"id": "c"},
                   {"id": "d", "origin": {"kind": "issue", "ref": f"{NEW}#7"}}]
        self.assertEqual([r["id"] for r in common.from_origin(records, f"{NEW}#7", common.origin_key(NEW, AFTER))], ["a", "d"])
        self.assertEqual([r["id"] for r in common.from_origin(records, f"{NEW}#7", lambda ref: ref)], ["d"])


class IssueNumberTests(unittest.TestCase):
    """evidence-store's `issue_number`, on which its status form and pr_links.follow find a record's own issue."""

    def setUp(self):
        self.settings = mock.patch.object(common, "load_settings", lambda path=None: AFTER)
        self.settings.start()
        self.addCleanup(self.settings.stop)
        self.no = rec.with_id({"schema": rec.SCHEMA, "kind": "review", "verdict": "problem", "category": "other",
                               "rubric": "ltb-rubric/1", "text": "It should say n is natural.",
                               "subject": {"name": "Fixture.triple", "commit": "B"}, "at": at(2),
                               "by": {"kind": "person", "identity": {"kind": "github", "id": "alice"}},
                               "origin": {"kind": "issue", "ref": f"{OLD}#7"}})

    def test_under_either_name(self):
        self.assertIsNone(standard_intake.THEIR_ISSUE_NUMBER(self.no, NEW))  # evidence-store's own, by the name alone
        self.assertEqual(standard_intake.issue_number(self.no, NEW), 7)
        self.assertEqual(standard_intake.issue_number(self.no, OLD), 7)
        elsewhere = {**self.no, "origin": {"kind": "issue", "ref": "someone/else#7"}}
        self.assertIsNone(standard_intake.issue_number(elsewhere, NEW))  # another repository's issue is not its own

    def test_install_puts_it_in_place(self):
        with mock.patch.object(cli, "process", cli.process), \
                mock.patch.object(intake, "process_issue", intake.process_issue), \
                mock.patch.object(intake, "process_comment", intake.process_comment), \
                mock.patch.object(intake, "issue_number", intake.issue_number):
            standard_intake.install()
            self.assertIs(intake.issue_number, standard_intake.issue_number)

    def test_a_merged_pull_request_closes_a_no_recorded_under_the_old_name(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d)
        (d / "evidence" / "records").mkdir(parents=True)
        shutil.copy(HERE.parent / "evidence" / "store.json", d / "evidence" / "store.json")
        store = Store.load(d / "evidence")
        linked = pr_links.link(self.no, f"{LIB}#12", self.no["by"], at(5),
                               {"kind": "comment", "ref": f"https://github.com/{OLD}/issues/7#issuecomment-7003"}, "")
        store.add([self.no, linked])
        merged = lambda pr: {"state": "MERGED", "sha": "c" * 40, "at": at(6)}  # noqa: E731
        with mock.patch.object(intake, "issue_number", standard_intake.issue_number):  # as install puts it
            out = pr_links.follow(NEW, store, LIB, merged, lambda repo, n: [])
        self.assertEqual(out.close, [(7, "completed")])
        self.assertEqual([n for n, _ in out.replies], [7])


class AnswererAndFixerTests(unittest.TestCase):
    def review(self, ref: str, kind: str = "issue") -> dict:
        return rec.with_id({"schema": rec.SCHEMA, "kind": "review", "verdict": "question", "text": "Why ℕ?",
                            "subject": {"name": "Fixture.double", "module": "Fixture", "commit": "B"}, "at": at(2),
                            "by": {"kind": "person", "identity": {"kind": "github", "id": "alice"}},
                            "origin": {"kind": kind, "ref": ref}})

    def test_the_issue_of_a_record_under_either_name(self):
        old, new = self.review(f"{OLD}#8"), self.review(f"{NEW}#9")
        self.assertIsNone(issue_of(old, NEW))  # without the former name, as before
        self.assertEqual(issue_of(old, NEW, [OLD]), 8)
        self.assertEqual(issue_of(self.review(f"{OLD.lower()}#8"), NEW, [OLD]), 8)
        self.assertEqual(issue_of(new, NEW, [OLD]), 9)
        self.assertIsNone(issue_of(self.review(f"{OLD}#8/event/3"), NEW, [OLD]))
        self.assertIsNone(issue_of(self.review(f"{OLD}#8", kind="comment"), NEW, [OLD]))
        self.assertIsNone(issue_of(self.review(f"{OLD}2#8"), NEW, [OLD]))

    def test_the_fixer_takes_the_reviews_filed_before_the_move(self):
        old, new = self.review(f"{OLD}#8"), self.review(f"{NEW}#9")
        self.assertEqual([v.issue for v in pick.reviews([old, new], NEW)], [9])
        self.assertEqual(sorted(v.issue for v in pick.reviews([old, new], NEW, (OLD,))), [8, 9])

    def test_the_settings_give_the_fixer_the_former_names(self):
        main = " ".join((HERE.parent / "fixer" / "__main__.py").read_text(encoding="utf-8").split())
        self.assertTrue('review_formerly=tuple(settings.get("formerly", ()))' in main, "the fixer's Config")
        self.assertEqual(main.count("cfg.review_repo, cfg.review_formerly)"), main.count("reviews("), "each reviews()")
        answerer = (HERE.parent / "answerer" / "__main__.py").read_text(encoding="utf-8")
        self.assertTrue('open_items(ev, settings["repo"], settings.get("formerly", ()))' in answerer, "the answerer's")


if __name__ == "__main__":
    unittest.main()
