import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from evidence_core import records as rec
from evidence_core.store import Store
from evidence_store import cli, github, intake
from evidence_store.intake import Context

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import evidence_intake  # noqa: E402
import pr_links  # noqa: E402

LIB = "TauCetiProject/TauCeti"
A = "<!-- agent: tool=Claude Code; model=claude-opus-5-5 -->"
SHA = "c" * 40
SUBJECT = {"aspect": "statement", "commit": "a" * 40, "module": "TauCeti.Foo", "name": "TauCeti.Foo.bar",
           "package": "TauCeti", "hashes": {"local": "1" * 16, "meaning": "2" * 16},
           "hasher": {"local": "ltb-local/3", "meaning": "ltb-meaning/1"}, "toolchain": "leanprover/lean4:v4.36.0-rc2"}
PERSON = {"kind": "person", "identity": {"kind": "github", "id": "RemyDegenne"}, "involvement": "unknown"}


def review(verdict: str, n: int, **extra) -> dict:
    r = {"schema": rec.SCHEMA, "kind": "review", "verdict": verdict, "subject": SUBJECT, "by": PERSON,
         "at": "2026-11-07T13:38:27Z", "origin": {"kind": "issue", "ref": f"o/r#{n}"}, "text": "It could be more general.",
         **extra}
    if verdict == "problem":
        r.update(category="other", rubric="ltb-rubric/1")
    return rec.with_id(r)


def comment(n: int, body: str, login: str = "CBirkbeck", association: str = "OWNER", minute: int = 0) -> dict:
    return {"id": 5000 + n * 100 + minute, "body": body, "user": {"login": login, "type": "User"},
            "author_association": association, "created_at": f"2026-11-07T14:{minute:02d}:00Z",
            "html_url": f"https://github.com/o/r/issues/{n}#issuecomment-{5000 + n * 100 + minute}"}


def looking(state: str, sha: str = "", at: str = "2026-11-08T09:00:00Z", calls: list | None = None):
    def look(pr: str) -> dict:
        if calls is not None:
            calls.append(pr)
        return {"state": state, "sha": sha, "at": at}
    return look


def never(pr: str) -> dict:
    raise AssertionError(f"looked up {pr}")


class ParseTests(unittest.TestCase):
    def test_a_pull_request_as_a_link_or_in_shorthand(self):
        for token, want in [("https://github.com/TauCetiProject/TauCeti/pull/31833", f"{LIB}#31833"),
                            ("https://github.com/TauCetiProject/TauCeti/pull/31833/files", f"{LIB}#31833"),
                            ("TauCetiProject/TauCeti#31833", f"{LIB}#31833"),
                            ("TauCeti#31833", f"{LIB}#31833"), ("`TauCeti#31833`", f"{LIB}#31833"),
                            ("[TauCeti#12](https://github.com/TauCetiProject/TauCeti/pull/12)", f"{LIB}#12"),
                            ("mathlib4#45669", "leanprover-community/mathlib4#45669"),
                            ("leanprover-community/mathlib4#45669", "leanprover-community/mathlib4#45669"),
                            ("#31833", None), ("Other#3", None), ("31833", None), ("generalises", None)]:
            self.assertEqual(pr_links.pull_ref(token, LIB), want, token)

    def test_the_commands_that_name_a_pull_request(self):
        for text, want in [
                (f"{A}\n/addressed TauCeti#12 — generalises it", ("addressed", "", f"{LIB}#12", "generalises it")),
                ("/addressed by https://github.com/TauCetiProject/TauCeti/pull/12\nIt drops a hypothesis.",
                 ("addressed", "", f"{LIB}#12", "It drops a hypothesis.")),
                ("/addressed", ("addressed", "", "", "")),
                ("/addressed #12 soon", ("addressed", "", "", "#12 soon")),
                ("/fixed abc1234 TauCeti#12 the note", ("fixed", "abc1234", f"{LIB}#12", "the note")),
                ("/fixed TauCeti#12", ("fixed", "", f"{LIB}#12", "")),
                ("/answered mathlib4#5: upstream", ("answered", "", "leanprover-community/mathlib4#5", "upstream"))]:
            self.assertEqual(pr_links.parse(text, LIB), want, text)
        for text in ["/fixed abc1234 the note", "/fixed", "/answered", "/answered Yes, and here is why.",
                     "/intended TauCeti#12", "It is addressed in TauCeti#12.", ""]:
            self.assertIsNone(pr_links.parse(text, LIB), text)  # evidence-store's to read, as it always has


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        (self.dir / "evidence" / "records").mkdir(parents=True)
        shutil.copy(HERE.parent / "evidence" / "store.json", self.dir / "evidence" / "store.json")
        self.store = Store.load(self.dir / "evidence")
        self.ctx = Context("o/r", self.store, lambda c: None, frozenset())
        self.no, self.idea, self.yes = review("problem", 7), review("question", 8), review("accept", 9)
        self.store.add([self.no, self.idea, self.yes])

    def read(self, target: dict, body: str, look=never, **kw):
        n = int(target["origin"]["ref"].split("#")[1])
        out = pr_links.process_comment(comment(n, body, **kw), {"number": n}, target, self.ctx, True, look=look)
        self.store.add(out.records)
        return out


class AddressedTests(StoreCase):
    def test_a_merged_pull_request_answers_a_suggestion_at_its_commit(self):
        calls = []
        out = self.read(self.idea, f"{A}\n/addressed TauCeti#12 — generalises it", looking("MERGED", SHA, calls=calls))
        self.assertEqual(calls, [f"{LIB}#12"])
        (r,) = out.records
        self.assertEqual((r["kind"], r["target"], r["state"], r["pr"], r["commit"], r["text"]),
                         ("status", self.idea["id"], "answered", f"{LIB}#12", SHA, "generalises it"))
        self.assertEqual(r["by"]["agent"], {"tool": "Claude Code", "model": "claude-opus-5-5"})
        self.assertEqual(out.close, [(8, "completed")])
        self.assertEqual(out.replies, [(8, f"Recorded: `{self.idea['id']}` is now **answered** by "
                                           f"[TauCeti#12](https://github.com/{LIB}/pull/12) (merged as `{SHA[:12]}`), "
                                           f"by Claude Code (claude-opus-5-5) via CBirkbeck.")])
        self.assertEqual(rec.validate(r), [])

    def test_an_open_pull_request_is_linked_and_the_no_stays_open(self):
        out = self.read(self.no, f"/addressed {LIB}#12", looking("OPEN"))
        (r,) = out.records
        self.assertEqual((r["kind"], r["links"], r["pr"], r["text"]),
                         ("comment", {"replies_to": self.no["id"]}, f"{LIB}#12", f"Addressed in {LIB}#12."))
        self.assertEqual((out.close, out.labels), ([], []))
        self.assertIn("It has not merged yet: once it does, this no is recorded as **fixed**", out.replies[0][1])
        self.assertEqual(rec.validate(r), [])

    def test_github_out_of_reach_links_it_to_be_looked_at_again(self):
        out = self.read(self.no, "/addressed TauCeti#12", looking("UNKNOWN"))
        self.assertEqual([r["kind"] for r in out.records], ["comment"])

    def test_closed_without_merging_or_unknown_is_kept_as_a_reply(self):
        for state, why in [("CLOSED", "was closed without merging"), ("MISSING", "is not a pull request GitHub knows")]:
            out = self.read(self.no, f"/addressed TauCeti#{len(state)}", looking(state), minute=len(state))
            (r,) = out.records
            self.assertEqual((r["kind"], "pr" in r), ("comment", False))
            self.assertTrue(out.replies[0][1].startswith("Not recorded: [TauCeti#"), out.replies)
            self.assertIn(why, out.replies[0][1])
            self.assertEqual(out.close, [])

    def test_another_repositorys_pull_request_is_linked_for_a_person_to_settle(self):
        out = self.read(self.no, "/addressed mathlib4#45669", looking("MERGED", SHA))
        (r,) = out.records
        self.assertEqual((r["kind"], r["pr"]), ("comment", "leanprover-community/mathlib4#45669"))
        self.assertIn("`/fixed <commit> leanprover-community/mathlib4#45669`", out.replies[0][1])
        self.assertEqual(out.close, [])

    def test_who_may(self):
        out = self.read(self.no, "/addressed TauCeti#12", login="someone", association="NONE")
        self.assertIn("only the author of a problem or a maintainer can mark it fixed", out.replies[0][1])
        self.assertEqual([r["kind"] for r in out.records], ["comment"])  # kept as a reply
        out = self.read(self.idea, "/addressed TauCeti#12", looking("OPEN"), login="RemyDegenne", association="NONE")
        self.assertEqual(out.records[0]["pr"], f"{LIB}#12")  # its author may

    def test_only_on_a_no_or_a_suggestion(self):
        out = self.read(self.yes, "/addressed TauCeti#12")
        self.assertIn("`/addressed` is for a no or a suggestion, and this is a review", out.replies[0][1])

    def test_without_its_pull_request(self):
        out = self.read(self.no, "/addressed #12")
        self.assertIn("`/addressed` needs the pull request after it", out.replies[0][1])

    def test_read_once(self):
        self.read(self.no, "/addressed TauCeti#12", looking("OPEN"))
        out = self.read(self.no, "/addressed TauCeti#12", never)
        self.assertEqual((out.records, out.replies), ([], []))


class FixedAnsweredTests(StoreCase):
    def test_a_pull_request_named_by_fixed_is_recorded_as_given(self):
        out = self.read(self.no, f"/fixed abc1234 {LIB}#12\nMerged.")
        (r,) = out.records
        self.assertEqual((r["state"], r["commit"], r["pr"], r["text"]), ("fixed", "abc1234", f"{LIB}#12", "Merged."))
        self.assertEqual(out.close, [(7, "completed")])
        out = self.read(self.idea, "/answered TauCeti#3", minute=1)
        self.assertEqual((out.records[0]["state"], out.records[0]["pr"], "commit" in out.records[0]),
                         ("answered", f"{LIB}#3", False))

    def test_without_a_pull_request_evidence_store_reads_it(self):
        out = self.read(self.no, "/fixed abc1234 the note")
        (r,) = out.records
        self.assertEqual((r["state"], r["commit"], "pr" in r, r["text"]), ("fixed", "abc1234", False, "the note"))

    def test_refusals_are_evidence_stores(self):
        out = self.read(self.idea, "/fixed TauCeti#12")  # a suggestion is answered, not fixed
        self.assertIn("`/fixed` is for a problem, and this is a question", out.replies[0][1])


class FollowTests(StoreCase):
    def link(self, target: dict, pr: str = f"{LIB}#12", minute: int = 0) -> dict:
        out = self.read(target, f"{A}\n/addressed {pr}", looking("OPEN"), minute=minute)
        return out.records[0]

    def follow(self, look, said=()):
        return pr_links.follow("o/r", self.store, LIB, look, lambda repo, n: list(said))

    def test_merged_since_it_settles_the_no_by_whoever_linked_it(self):
        ln = self.link(self.no)
        out = self.follow(looking("MERGED", SHA, at="2026-11-08T09:00:00Z"))
        (r,) = out.records
        self.assertEqual((r["state"], r["pr"], r["commit"], r["by"], r["at"], r["origin"]),
                         ("fixed", f"{LIB}#12", SHA, ln["by"], "2026-11-08T09:00:00Z",
                          {"kind": "pull", "ref": f"https://github.com/{LIB}/pull/12"}))
        self.assertEqual(out.close, [(7, "completed")])
        self.assertIn("as Claude Code (claude-opus-5-5) via CBirkbeck linked it", out.replies[0][1])
        self.assertEqual(rec.validate(r), [])
        again = self.follow(never)  # settled: not looked at again
        self.assertEqual((again.records, again.replies), ([], []))
        self.assertEqual(len(Store.load(self.dir / "evidence").records), len(self.store.records))

    def test_open_still_it_waits(self):
        self.link(self.no)
        out = self.follow(looking("OPEN"))
        self.assertEqual((out.records, out.replies, out.close), ([], [], []))

    def test_closed_without_merging_it_says_so_once(self):
        ln = self.link(self.no)
        out = self.follow(looking("CLOSED"))
        self.assertEqual(out.records, [])
        (n, text), = out.replies
        self.assertEqual(n, 7)
        self.assertIn("was closed without merging, so it no longer addresses", text)
        self.assertTrue(text.endswith(f"<!-- pr-link-closed: {ln['id']} -->"))
        again = self.follow(looking("CLOSED"), said=[{"body": text}])
        self.assertEqual(again.replies, [])

    def test_a_decision_since_the_link_leaves_it_alone(self):
        self.link(self.no)
        self.read(self.no, "/invalid It is not a problem.", minute=5)
        self.assertEqual(self.follow(never).records, [])

    def test_a_suggestion_answered_before_its_link_is_answered_again_by_the_pull_request(self):
        self.read(self.idea, "/answered Yes, it generalises.", minute=0)
        self.link(self.idea, minute=5)
        (r,) = self.follow(looking("MERGED", SHA)).records
        self.assertEqual((r["state"], r["pr"]), ("answered", f"{LIB}#12"))

    def test_only_the_librarys_and_only_the_latest_link(self):
        self.link(self.no, "mathlib4#45669")
        self.assertEqual(self.follow(never).records, [])
        self.link(self.idea, "TauCeti#3", minute=1)
        self.link(self.idea, "TauCeti#4", minute=2)
        calls = []
        self.follow(looking("OPEN", calls=calls))
        self.assertEqual(calls, [f"{LIB}#4"])

    def test_into_the_runs_outcome(self):
        self.link(self.no)
        outcome = self.dir / "outcome.json"
        outcome.write_text(json.dumps({"records": ["x"], "replies": [[3, "hi"]], "close": [], "reopen": [],
                                       "labels": [], "reactions": []}), encoding="utf-8")
        n = pr_links.follow_into("o/r", str(self.dir / "evidence"), str(outcome), looking("MERGED", SHA),
                                 lambda repo, n: [])
        self.assertEqual(n, 1)
        got = json.loads(outcome.read_text(encoding="utf-8"))
        self.assertEqual(got["records"][0], "x")
        self.assertEqual(len(got["records"]), 2)
        self.assertEqual([r[0] for r in got["replies"]], [3, 7])
        self.assertEqual(got["close"], [[7, "completed"]])


class LookupTests(unittest.TestCase):
    def gh(self, answers: dict):
        def run(argv):
            key = " ".join(argv[:3])
            if key not in answers:
                raise AssertionError(argv)
            a = answers[key]
            if isinstance(a, Exception):
                raise a
            return a
        return run

    def test_merged_on_github(self):
        run = self.gh({"gh pr view": json.dumps({"state": "MERGED", "mergeCommit": {"oid": SHA},
                                                 "mergedAt": "2026-11-08T09:00:00Z", "closedAt": "2026-11-08T09:00:00Z"})})
        self.assertEqual(pr_links.lookup(f"{LIB}#12", run), {"state": "MERGED", "sha": SHA, "at": "2026-11-08T09:00:00Z"})

    def test_merged_by_bors(self):
        view = {"state": "CLOSED", "mergeCommit": None, "mergedAt": None, "closedAt": "2026-11-07T14:42:52Z",
                "title": "[Merged by Bors] - refactor: split it"}
        run = self.gh({"gh pr view": json.dumps(view), "gh api repos/TauCetiProject/TauCeti": "main\n",
                       "gh api --paginate": f"{SHA}\trefactor: split it (#12)\n"})
        self.assertEqual(pr_links.lookup(f"{LIB}#12", run)["state"], "MERGED")
        self.assertEqual(pr_links.lookup(f"{LIB}#12", run)["sha"], SHA)

    def test_closed_without_merging_and_missing(self):
        import subprocess
        view = {"state": "CLOSED", "mergeCommit": None, "mergedAt": None, "closedAt": "2026-11-07T14:42:52Z",
                "title": "feat: abandoned"}
        run = self.gh({"gh pr view": json.dumps(view), "gh api repos/TauCetiProject/TauCeti": "main\n",
                       "gh api --paginate": ""})
        self.assertEqual(pr_links.lookup(f"{LIB}#12", run)["state"], "CLOSED")
        gone = subprocess.CalledProcessError(1, "gh", stderr="GraphQL: Could not resolve to a PullRequest with the number of 99.")
        self.assertEqual(pr_links.lookup(f"{LIB}#99", self.gh({"gh pr view": gone}))["state"], "MISSING")
        down = subprocess.CalledProcessError(1, "gh", stderr="HTTP 502")
        self.assertEqual(pr_links.lookup(f"{LIB}#99", self.gh({"gh pr view": down}))["state"], "UNKNOWN")


class IntakeTests(unittest.TestCase):
    """The six-hourly run follows the linked pull requests; an event's run does not."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        (self.dir / "evidence" / "records").mkdir(parents=True)
        shutil.copy(HERE.parent / "evidence" / "store.json", self.dir / "evidence" / "store.json")

    def run_intake(self, *extra: str) -> list:
        followed = []

        def follow_into(repo, store, outcome, *a, **k):
            followed.append((repo, store, outcome))
            return 0

        with mock.patch.object(github, "gh_json", lambda *a: []), \
                mock.patch.object(github, "recent_issues", lambda repo, since: []), \
                mock.patch.object(cli, "process", cli.process), \
                mock.patch.object(intake, "process_issue", intake.process_issue), \
                mock.patch.object(intake, "process_comment", intake.process_comment), \
                mock.patch.object(pr_links, "follow_into", follow_into):
            code = evidence_intake.main(["intake", "--repo", "o/r", "--store", str(self.dir / "evidence"), *extra,
                                         "--outcome", str(self.dir / "outcome.json")])
        self.assertEqual(code, 0)
        return followed

    def test_the_schedule_follows_and_an_event_does_not(self):
        self.assertEqual(self.run_intake("--sweep-days", "14", "--follow-pulls"),
                         [("o/r", str(self.dir / "evidence"), str(self.dir / "outcome.json"))])
        self.assertEqual(self.run_intake("--sweep-days", "14"), [])

    def test_intake_reads_addressed_through_pr_links(self):
        with mock.patch.object(intake, "process_comment", intake.process_comment), \
                mock.patch.object(cli, "process", cli.process), \
                mock.patch.object(intake, "process_issue", intake.process_issue):  # put back as they were
            evidence_intake.standard_intake.install()
            self.assertIs(intake.process_comment, pr_links.process_comment)


if __name__ == "__main__":
    unittest.main()
