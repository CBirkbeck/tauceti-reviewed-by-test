import dataclasses
import hashlib
import sys
import unittest
from pathlib import Path

from evidence_core import rubric as rb

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import standard  # noqa: E402

AXES = rb.STANDARD.names
#: The vector mathlib-quality's review_site.py is pinned to as well: CRLF, trailing spaces, blank lines at both ends.
VECTOR = "\n## What it says\r\n`triple n` is $3n$.  \r\n\r\n## References and tests\n- Fixture documentation.\n\n## Lean subtleties\nNone.\n\n"
SAYS = "## What it says\n`triple n` is $3n$."
REFERENCE = "- Fixture documentation, §1."
TEST = "- `Fixture.triple_two` — its value at 2"
CHECK = "- Check *test_two*, `TauCeti/Examples/Fixture.lean:42` — passes"
SUBTLE = "## Lean subtleties\nNone."


def refs(*bullets: str) -> str:
    return "\n".join(["## References and tests", *bullets])


def review(*parts: str) -> str:
    """A review of the given parts: the three above when none."""
    return "\n\n".join(parts or (SAYS, refs(REFERENCE, TEST, CHECK), SUBTLE)) + "\n"


GOOD = review()


class StandardTests(unittest.TestCase):
    def assertNamed(self, problems, *words):
        """Some one problem holds all the words."""
        self.assertTrue(any(all(w in p for w in words) for p in problems), f"{words} are in none of {problems}")


class VersionTests(StandardTests):
    def test_the_shared_vector(self):
        self.assertEqual(standard.version_of(VECTOR), "dd83c85a488e22c8")
        self.assertEqual(standard.version_of(standard.normalize(VECTOR)), "dd83c85a488e22c8")

    def test_normalize(self):
        self.assertEqual(standard.normalize("\r\n\r\nA  \r\nB\t\rC\n\n\n"), "A\nB\nC")
        # Blank lines inside stay, and so does an indent; a line of spaces is blank.
        self.assertEqual(standard.normalize("  A\n\n\n B \n   \nC"), "  A\n\n\n B\n\nC")
        text = "\n \n## A  \r\n x\r\r\n\n"
        self.assertEqual(standard.normalize(standard.normalize(text)), standard.normalize(text))

    def test_the_version_is_the_normalized_texts_hash(self):
        want = hashlib.sha256("§ℂ𝔾\nb".encode("utf-8")).hexdigest()[:16]
        self.assertEqual(standard.version_of("§ℂ𝔾  \r\nb\r\n"), want)
        self.assertEqual(standard.version_of(GOOD.replace("\n", "  \r\n")), standard.version_of(GOOD))
        self.assertNotEqual(standard.version_of(GOOD), standard.version_of(GOOD.replace("3n", "2n")))


class PartsTests(StandardTests):
    def test_three_parts_in_order_none_empty(self):
        self.assertEqual(standard.check(GOOD), [])
        bodies, problems = standard.parts(GOOD)
        self.assertEqual(problems, [])
        self.assertEqual(bodies, ["`triple n` is $3n$.", "\n".join([REFERENCE, TEST, CHECK]), "None."])
        self.assertEqual(standard.HEADINGS, ("## What it says", "## References and tests", "## Lean subtleties"))
        # A part missing, out of order or empty is named.
        for heading, kept in ((standard.HEADINGS[0], (refs(REFERENCE), SUBTLE)), (standard.HEADINGS[1], (SAYS, SUBTLE)),
                              (standard.HEADINGS[2], (SAYS, refs(REFERENCE)))):
            bodies, problems = standard.parts(review(*kept))
            self.assertIsNone(bodies)
            self.assertNamed(problems, heading, "missing")
            self.assertNamed(standard.check(review(*kept)), heading, "missing")
        self.assertNamed(standard.check(review(refs(REFERENCE), SAYS, SUBTLE)), "order")
        self.assertNamed(standard.check(review(SAYS, "## References and tests", SUBTLE)), "## References and tests", "empty")
        self.assertNamed(standard.check(review(SAYS, refs(REFERENCE), "## Lean subtleties\n \n")), "## Lean subtleties", "empty")
        self.assertNamed(standard.check(""), "## What it says", "missing")

    def test_every_part_that_is_wrong_is_named(self):
        problems = standard.check(review(SAYS))
        self.assertNamed(problems, "## References and tests", "missing")
        self.assertNamed(problems, "## Lean subtleties", "missing")

    def test_a_heading_is_a_line_exactly(self):
        for wrong in ("## What it says:", "### What it says", "## what it says", "## What it says (1)", " ## What it says"):
            self.assertNamed(standard.check(GOOD.replace("## What it says", wrong, 1)), "## What it says", "missing")
        # Trailing spaces and CRLF do not hide one: the vector has both.
        self.assertEqual(standard.parts(VECTOR), (["`triple n` is $3n$.", "- Fixture documentation.", "None."], []))
        self.assertEqual(standard.check(VECTOR), [])

    def test_nothing_comes_before_the_first_part(self):
        self.assertNamed(standard.check("# A title\n\n" + GOOD), "before", "## What it says")

    def test_a_part_comes_once(self):
        self.assertNamed(standard.check(review(SAYS, refs(REFERENCE), SUBTLE, SUBTLE)), "## Lean subtleties", "2 times")

    def test_other_headings_belong_to_the_part_they_are_in(self):
        text = review("## What it says\n### The binders\nfoo\n\n## An aside\nbar", refs(REFERENCE), SUBTLE)
        self.assertEqual(standard.parts(text)[0][0], "### The binders\nfoo\n\n## An aside\nbar")
        self.assertEqual(standard.check(text), [])


class ItemsTests(StandardTests):
    def test_items_tell_tests_checks_and_references_apart(self):
        it = standard.items(GOOD)
        self.assertEqual(it.tests, ["Fixture.triple_two"])
        self.assertEqual(it.checks, ["test_two"])
        self.assertEqual(it.references, ["Fixture documentation, §1."])
        self.assertEqual(it, standard.Items(["Fixture documentation, §1."], ["Fixture.triple_two"], ["test_two"]))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            it.tests = []

    def test_only_a_name_makes_a_test(self):
        # The names of the dataset's declarations: primes, subscripts and Greek letters are in them.
        names = ["Foo.bar'", "Foo.baz₂", "Real.log", "TauCeti.Foo.bar_two", "ι"]
        it = standard.items(review(SAYS, refs(*(f"- `{n}` — a test" for n in names)), SUBTLE))
        self.assertEqual(it.tests, names)
        elsewhere = ["- `2` is the base case", "- `TauCeti/Examples/Foo.lean` — the file", "- `a + b = b + a` — commutativity",
                     "- Check the roadmap", "- A test: `Foo.bar` is not first"]
        it = standard.items(review(SAYS, refs(*elsewhere), SUBTLE))
        self.assertEqual((it.tests, it.checks), ([], []))
        self.assertEqual(it.references, [e[2:] for e in elsewhere])

    def test_a_dash_a_star_or_a_plus_opens_a_bullet(self):
        text = review(SAYS, refs("- `Fixture.a` — a test", "* `Fixture.b` — a test", "+ `Fixture.c` — a test",
                                 "* Check *tag_b*, `x:1` — passes", "+ A reference", "*  Another, after two spaces", "",
                                 "*Note:* emphasis is not a bullet", "**Bold** is not one", "+1 is not one", "-1 neither", "-", "* "),
                      SUBTLE)
        it = standard.items(text)
        self.assertEqual(it.tests, ["Fixture.a", "Fixture.b", "Fixture.c"])
        self.assertEqual(it.checks, ["tag_b"])
        self.assertEqual(it.references, ["A reference", "Another, after two spaces"])

    def test_a_bullet_goes_on_over_its_indented_lines(self):
        text = review(SAYS, refs("- Stacks Project, Tag 0BSC,", "  Lemma 10.156.3 (the same", "\tring).", "", "Prose between.",
                                 "- Hartshorne, II.1.", "  - a nested one", "", "More prose."), SUBTLE)
        self.assertEqual(standard.items(text).references,
                         ["Stacks Project, Tag 0BSC, Lemma 10.156.3 (the same ring).", "Hartshorne, II.1. - a nested one"])

    def test_only_part_two_holds_items(self):
        text = review("## What it says\n- `Fixture.in_part_one` — a bullet\n- Check *test_in_one*, `x:1`", refs(REFERENCE),
                      "## Lean subtleties\n- `Fixture.in_part_three` — a bullet")
        self.assertEqual(standard.items(text), standard.Items([REFERENCE[2:]], [], []))
        self.assertEqual(standard.items("nothing like a review"), standard.Items([], [], []))

    def test_crlf_and_trailing_spaces_do_not_change_the_items(self):
        self.assertEqual(standard.items(GOOD.replace("\n", "  \r\n")), standard.items(GOOD))


class CheckTests(StandardTests):
    def test_a_first_version_needs_no_note_and_has_nothing_to_drop(self):
        # With no parent (a first version, or a restore) only the parts and the tests' existence are checked.
        self.assertEqual(standard.check(review(SAYS, refs(REFERENCE), SUBTLE)), [])
        self.assertEqual(standard.check(GOOD, note=None, dropped=[]), [])

    def test_an_edit_keeps_or_says_why(self):
        edit = review(SAYS, refs(REFERENCE, CHECK), SUBTLE)  # without the test
        problems = standard.check(edit, parent=GOOD, note="shorter")
        self.assertEqual(len(problems), 1)
        self.assertNamed(problems, "Fixture.triple_two")
        said = [("`Fixture.triple_two`", "it was renamed")]
        self.assertEqual(standard.check(edit, parent=GOOD, dropped=said, note="shorter"), [])

    def test_a_check_is_named_by_its_tag(self):
        edit = review(SAYS, refs(REFERENCE, TEST), SUBTLE)  # without the Check
        problems = standard.check(edit, parent=GOOD, note="n")
        self.assertEqual(len(problems), 1)
        self.assertNamed(problems, "test_two")
        for item in ("Check *test_two*", "*test_two*", "test_two", "Check *test_two*, `TauCeti/Examples/Fixture.lean:42`"):
            self.assertEqual(standard.check(edit, parent=GOOD, dropped=[(item, "it moved")], note="n"), [], item)

    def test_a_longer_name_does_not_name_the_one_dropped(self):
        edit = review(SAYS, refs(REFERENCE, CHECK), SUBTLE)
        for item in ("`Fixture.triple_two_ne`", "`Fixture.triple_two'`", "Fixture.triple_two.foo", "`triple_two`",
                     "`Other.Fixture.triple_two`", "other"):
            problems = standard.check(edit, parent=GOOD, dropped=[(item, "gone")], note="n")
            self.assertNamed(problems, "Fixture.triple_two")
        # A sentence's full stop after the name is not a longer name.
        self.assertEqual(standard.check(edit, parent=GOOD, dropped=[("Fixture.triple_two.", "gone")], note="n"), [])

    def test_a_dropped_line_needs_its_reason(self):
        edit = review(SAYS, refs(REFERENCE, CHECK), SUBTLE)
        for why in ("", "  "):
            problems = standard.check(edit, parent=GOOD, dropped=[("`Fixture.triple_two`", why)], note="n")
            self.assertNamed(problems, "Fixture.triple_two")
        # One line may name a test and a Check together; and pairs as lists, as JSON gives them, do as tuples.
        edit = review(SAYS, refs("Nothing yet."), SUBTLE)
        said = [["`Fixture.triple_two` and Check *test_two*", "both moved"], ["Fixture documentation, §1.", "gone"]]
        self.assertEqual(standard.check(edit, parent=GOOD, dropped=said, note="n"), [])

    def test_a_reference_is_named_by_its_likeness(self):
        edit = review(SAYS, refs(TEST, CHECK), SUBTLE)  # without the reference
        problems = standard.check(edit, parent=GOOD, note="n")
        self.assertEqual(len(problems), 1)
        self.assertNamed(problems, "Fixture documentation, §1.")
        for item in ("Fixture documentation, §1.", "Fixture documentation, section 1", "fixture documentation"):
            self.assertEqual(standard.check(edit, parent=GOOD, dropped=[(item, "not about this")], note="n"), [], item)
        for item in ("Stacks Project, Tag 0BSC", "`Fixture.triple_two`", "Fixture"):
            self.assertNamed(standard.check(edit, parent=GOOD, dropped=[(item, "gone")], note="n"), "Fixture documentation")

    def test_a_reworded_reference_is_kept(self):
        edit = GOOD.replace("Fixture documentation, §1.", "Fixture documentation, section 1.")
        self.assertEqual(standard.check(edit, parent=GOOD, note="spelled out"), [])
        # Another reference in its place is a drop, and the new one is not what names the old.
        edit = GOOD.replace("Fixture documentation, §1.", "Stacks Project, Tag 0BSC, Lemma 10.156.3.")
        self.assertNamed(standard.check(edit, parent=GOOD, note="n"), "Fixture documentation, §1.")

    def test_a_long_reference_reworded_is_kept(self):
        # From 200 characters on, SequenceMatcher's default `autojunk` sets the commonest letters aside and
        # finds almost no likeness (0.05 here, for a title shortened and a page added), so it is off.
        long = ("Hartshorne, Algebraic Geometry, Chapter II, Proposition 8.20: for a smooth morphism of schemes the sheaf of "
                "relative differentials is locally free of finite rank, and the rank is the relative dimension of the "
                "morphism; compare also the discussion of the sheaf of differentials in Bosch, Luetkebohmert and Raynaud, "
                "Neron Models, section 2.2.")
        edit = long.replace("Algebraic ", "").replace("section 2.2.", "section 2.2, p. 22.")
        self.assertEqual(standard.check(review(SAYS, refs(f"- {edit}"), SUBTLE), parent=review(SAYS, refs(f"- {long}"), SUBTLE),
                                        note="shortens the title and adds the page"), [])

    def test_an_extended_reference_is_kept(self):
        # More said after a reference leaves it the same reference, though it then reads too little like the old
        # one (0.40) to be that one reworded.
        old = review(SAYS, refs("- Stacks Project, Tag 0BSC", TEST), SUBTLE)
        new = review(SAYS, refs("- Stacks Project, Tag 0BSC, the strict henselisation of a local ring and its universal "
                                "property", TEST), SUBTLE)
        self.assertEqual(standard.check(new, parent=old, note="says what the tag is about"), [])
        # Its text must be inside, as likeness is read: whatever the case and punctuation.
        new = new.replace("Stacks Project, Tag", "STACKS PROJECT; tag")
        self.assertEqual(standard.check(new, parent=old, note="n"), [])
        # A reference with no letter or digit is inside no other, nor is one of punctuation and spaces.
        for bare in ("—", "- -", "* *"):
            old = review(SAYS, refs(f"- {bare}", TEST), SUBTLE)
            new = review(SAYS, refs("- Another book", TEST), SUBTLE)
            self.assertNamed(standard.check(new, parent=old, note="n"), f'"{bare}"')
        # Spaces left where punctuation was taken out, in either, do not keep a reference from being inside another.
        clause = ", and a clause that makes it read too little like the old"
        for was, becomes in (("Stacks - Project, Tag 0BSC", "Stacks Project, Tag 0BSC" + clause),
                             ("Stacks Project, Tag 0BSC", "Stacks Project - Tag 0BSC" + clause)):
            self.assertFalse(standard.like(was, becomes))
            old = review(SAYS, refs(f"- {was}", TEST), SUBTLE)
            self.assertEqual(standard.check(review(SAYS, refs(f"- {becomes}", TEST), SUBTLE), parent=old, note="n"), [])

    def test_a_reference_in_any_bullet_is_not_dropped_silently(self):
        edit = review(SAYS, refs(TEST, CHECK), SUBTLE)  # without the reference
        said = [("Fixture documentation, §1.", "not about this")]
        for marker in ("-", "*", "+"):
            old = review(SAYS, refs(f"{marker} Fixture documentation, §1.", TEST, CHECK), SUBTLE)
            problems = standard.check(edit, parent=old, note="n")
            self.assertEqual(len(problems), 1, marker)
            self.assertNamed(problems, "Fixture documentation, §1.")
            self.assertEqual(standard.check(edit, parent=old, dropped=said, note="n"), [], marker)

    def test_adding_drops_nothing(self):
        edit = review(SAYS, refs(REFERENCE, "- Another book, Theorem 2.", TEST, CHECK), "## Lean subtleties\nx / 0 = 0 here.")
        self.assertEqual(standard.check(edit, parent=GOOD, note="adds a book and the junk value"), [])

    def test_an_edit_says_what_it_adds_and_changes_something(self):
        edit = GOOD.replace("None.", "Division by zero is zero.")
        for note in (None, "", " \n"):
            self.assertNamed(standard.check(edit, parent=GOOD, note=note), "note")
        self.assertEqual(standard.check(edit, parent=GOOD, note="adds the junk value"), [])
        self.assertNamed(standard.check(GOOD, parent=GOOD, note="same"), "changes nothing")
        # A text that differs only in line endings and trailing spaces is the same version.
        self.assertNamed(standard.check(GOOD.replace("\n", "  \r\n"), parent=GOOD, note="same"), "changes nothing")

    def test_a_test_must_exist(self):
        problems = standard.check(GOOD, exists=lambda n: False)
        self.assertEqual(len(problems), 1)
        self.assertNamed(problems, "Fixture.triple_two")
        asked = []
        self.assertEqual(standard.check(GOOD, exists=lambda n: asked.append(n) or True), [])
        self.assertEqual(asked, ["Fixture.triple_two"])  # the tests only: a Check's tag is no name
        edit = GOOD.replace("None.", "Division by zero is zero.")
        self.assertNamed(standard.check(edit, parent=GOOD, note="n", exists=lambda n: False), "Fixture.triple_two")
        twice = review(SAYS, refs(TEST, TEST), SUBTLE)
        self.assertEqual(len(standard.check(twice, exists=lambda n: False)), 1)

    def test_what_is_wrong_is_said_at_once_but_items_wait_for_the_parts(self):
        broken = review(SAYS, SUBTLE)  # no Part 2: not a drop of every item, just the part missing
        problems = standard.check(broken, parent=GOOD, note=None, exists=lambda n: False)
        self.assertNamed(problems, "## References and tests", "missing")
        self.assertNamed(problems, "note")
        self.assertFalse([p for p in problems if "drops" in p or "exist" in p], problems)


class CellsTests(StandardTests):
    def test_cells(self):
        spec = "object, convention, edge-cases, junk, vacuous, choice n/a, generality, naming"
        want = {**{a: "checked" for a in AXES}, "choice": "na"}
        self.assertEqual(standard.cells(spec, AXES), (want, ""))
        self.assertEqual(list(standard.cells(spec, AXES)[0]), AXES)
        for bad, word in ((spec.replace(", naming", ""), "naming"), (spec + ", style", "style"),
                          (spec.replace("junk", "junk=unchecked"), "junk"), ("", "object")):
            got, why = standard.cells(bad, AXES)
            self.assertIsNone(got)
            self.assertIn(word, why)

    def test_a_cell_is_spelt_in_any_of_its_forms(self):
        for entry, state in (("choice", "checked"), ("choice=checked", "checked"), ("choice n/a", "na"), ("choice=na", "na"),
                             ("choice=n/a", "na"), ("choice = n/a", "na"), ("  choice   n/a ", "na")):
            spec = ",".join(entry if a == "choice" else a for a in AXES)
            self.assertEqual(standard.cells(spec, AXES), ({**{a: "checked" for a in AXES}, "choice": state}, ""), entry)

    def test_cells_come_in_the_rubrics_order_whatever_the_order_given(self):
        got, why = standard.cells(", ".join(reversed(AXES)), AXES)
        self.assertEqual((list(got), why), (AXES, ""))

    def test_an_axis_twice_is_refused(self):
        got, why = standard.cells(", ".join(AXES) + ", junk n/a", AXES)
        self.assertIsNone(got)
        self.assertIn("junk", why)

    def test_what_is_no_cell_is_named(self):
        for entry in ("junk checked", "choice n/a please", "junk=", "junk==na", "junk=unchecked", "=na", "Junk"):
            spec = ", ".join(entry if a == "junk" else a for a in AXES)
            got, why = standard.cells(spec, AXES)
            self.assertIsNone(got, entry)
            self.assertIn(entry, why)

    def test_every_trouble_is_said_at_once(self):
        got, why = standard.cells("object, style, junk=unchecked", AXES)
        self.assertIsNone(got)
        for word in ("style", "junk=unchecked", "convention", "naming"):
            self.assertIn(word, why)
        self.assertNotIn("junk", why.split("missing: ")[1])  # its entry is said bad, not also missing

    def test_the_axes_are_the_callers(self):
        self.assertEqual(standard.cells("a, b n/a", ["a", "b"]), ({"a": "checked", "b": "na"}, ""))
        self.assertIsNone(standard.cells("a", ["a", "b"])[0])


def record(kind="review", **fields) -> dict:
    return {"kind": kind, **({"verdict": "accept"} if kind == "review" else {}), "text": GOOD, **fields}


class RecordTests(StandardTests):
    def test_kinds_and_acts(self):
        self.assertEqual(standard.SPEC, "tauceti-standard/1")
        v = standard.version_of(GOOD)
        wrote = record(standard={"spec": standard.SPEC})
        edited = record(standard={"spec": standard.SPEC, "parent": v, "note": "n", "dropped": []})
        restored = record("comment", standard={"spec": standard.SPEC, "parent": "0123456789abcdef", "restores": v})
        held = record("comment", standard={"spec": standard.SPEC})
        approval = record(text=f"Approves the standard review `{v}`.", standard={"spec": standard.SPEC, "approves": v})
        for r, kind, act in ((wrote, "version", "wrote"), (edited, "version", "edited"), (restored, "version", "restored"),
                             (held, "version", "wrote"), (approval, "approval", "approved")):
            self.assertEqual((standard.kind_of(r), standard.act(r)), (kind, act), r)
        self.assertIsNone(standard.kind_of({"kind": "review", "verdict": "accept", "text": "Correctly stated."}))

    def test_what_is_no_standard_record(self):
        spec = {"spec": standard.SPEC}
        for r in (
            record(),  # an accept of the earlier form, with a text of its own
            record(standard={"spec": "tauceti-standard/2"}),
            record(standard="tauceti-standard/1"),
            record(verdict="problem", standard=spec),
            record(text="", standard=spec),
            record(text=" \n", standard=spec),
            {"kind": "review", "verdict": "accept", "standard": spec},  # no text at all
            record("comment", standard={**spec, "approves": "dd83c85a"}),  # a comment approves nothing
            record(standard={**spec, "approves": ""}),  # an approval that names no version is neither
            record(standard={**spec, "approves": None}),
            record(standard={**spec, "approves": 123}),
            record("test", standard=spec),
            record("status", standard=spec),
        ):
            self.assertIsNone(standard.kind_of(r), r)
            with self.assertRaises(ValueError):
                standard.act(r)

    def test_a_restore_is_a_restore_though_it_has_a_parent(self):
        r = record("comment", standard={"spec": standard.SPEC, "parent": "0123456789abcdef", "restores": "fedcba9876543210"})
        self.assertEqual(standard.act(r), "restored")

    def test_an_accept_is_a_review_that_says_yes(self):
        self.assertTrue(standard.is_accept({"kind": "review", "verdict": "accept"}))
        for r in ({"kind": "review", "verdict": "problem"}, {"kind": "review"}, {"verdict": "accept"}, {},
                  {"kind": "comment", "verdict": "accept"}):
            self.assertFalse(standard.is_accept(r), r)
        # A comment that says `accept` is no accept to the standard review either: it has no approval in it.
        spec = {"spec": standard.SPEC, "approves": "dd83c85a488e22c8"}
        self.assertIsNone(standard.kind_of({"kind": "comment", "verdict": "accept", "text": "t", "standard": spec}))


V1 = GOOD
V2 = GOOD.replace("None.", "Division by zero is zero.")
VER1, VER2 = standard.version_of(V1), standard.version_of(V2)
PERSON = {"kind": "person", "identity": {"kind": "github", "id": "example"}}


def made(n: int, who, kind="review", **fields) -> dict:
    """What happened at time `n`, by the agent whose tool is `who` (a test tells agents apart by it), or by the
    `by` given: an accept, or a comment when `kind` says so. The times and the ids both run in order."""
    by = {"kind": "agent", "agent": {"tool": who, "model": "m"}} if isinstance(who, str) else who
    return record(kind, id=f"r{n}", at=f"2026-10-25T10:{n:02d}:00Z", by=by, **fields)


def wrote(n: int, who, text=V1, parent=None) -> dict:
    """A version an AI wrote, which is an accept: an edit when it names its parent."""
    s = {"spec": standard.SPEC, **({"parent": parent, "note": "n", "dropped": []} if parent else {})}
    return made(n, who, text=text, standard=s)


def held(n: int, who, text=V1) -> dict:
    """A version nobody approves by recording it: a comment."""
    return made(n, who, "comment", text=text, standard={"spec": standard.SPEC})


def ticked(n: int, who, version: str) -> dict:
    """An approval of `version`."""
    return made(n, who, text=f"Approves the standard review `{version}`.",
                standard={"spec": standard.SPEC, "approves": version})


def yes(n: int, who) -> dict:
    """An accept of the earlier form: reasons of its own, and no `standard`."""
    return made(n, who, text="Correctly stated.")


def seen(r: dict, applies=True, withdrawn=False, superseded=False) -> standard.Seen:
    return standard.Seen(r, applies, withdrawn, superseded)


def tools(rows) -> list[str]:
    return [s.record["by"].get("agent", {}).get("tool", s.record["by"]["kind"]) for s in rows]


class SeenTests(StandardTests):
    def test_a_seen_is_a_record_and_what_the_store_says_of_it(self):
        r = yes(1, "A")
        s = standard.Seen(r, True, False, True)
        self.assertEqual([f.name for f in dataclasses.fields(s)], ["record", "applies", "withdrawn", "superseded"])
        self.assertEqual((s.record, s.applies, s.withdrawn, s.superseded), (r, True, False, True))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            s.applies = False


class CurrentVersionTests(StandardTests):
    def test_the_latest_version_not_withdrawn_is_current(self):
        v1 = seen(wrote(1, "A", V1), superseded=True)  # A's edit superseded A's yes of v1, but v1 stays a candidate
        v2 = seen(wrote(2, "A", V2, parent=VER1))
        self.assertIs(standard.current_version([v1, v2]), v2)
        # The edit withdrawn is undone: v1, though superseded, is current again; with both withdrawn none is.
        v2 = seen(v2.record, withdrawn=True)
        self.assertIs(standard.current_version([v1, v2]), v1)
        self.assertIsNone(standard.current_version([seen(v1.record, withdrawn=True), v2]))

    def test_versions_are_ordered_by_time_then_id_not_by_position(self):
        a, b = seen(wrote(1, "A", V1)), seen(wrote(2, "B", V2))
        self.assertIs(standard.current_version([a, b]), b)
        self.assertIs(standard.current_version([b, a]), b)
        # At the same instant the later id wins, whichever comes first.
        c = seen({**a.record, "at": b.record["at"], "id": "r9"})
        for rows in ([c, b], [b, c]):
            self.assertIs(standard.current_version(rows), c)
        # Time comes before id: a later version whose id sorts earlier is still the later.
        early, late = seen({**a.record, "id": "z"}), seen({**b.record, "id": "a"})
        self.assertIs(standard.current_version([early, late]), late)

    def test_only_a_version_can_be_current(self):
        rows = [seen(yes(1, "A")), seen(ticked(2, "B", VER1)), seen(made(3, "C", verdict="problem", text="Wrong.")),
                seen(made(4, "D", "comment", text="A remark."))]
        self.assertIsNone(standard.current_version(rows))
        self.assertIsNone(standard.current_version([]))
        # A comment that carries the spec and a text is one: a maintainer's edit, a migration review held for the owner.
        c = seen(held(5, "M"))
        self.assertIs(standard.current_version([*rows, c]), c)


class SummaryTests(StandardTests):
    def test_what_a_summary_holds(self):
        v1, v2 = wrote(1, "A", V1), wrote(2, "A", V2, parent=VER1)
        s = standard.summary([seen(v1, superseded=True), seen(v2)])
        self.assertEqual(set(s), {"text", "version", "record", "approving", "current", "approvers", "earlier"})
        self.assertEqual((s["text"], s["version"]), (V2, VER2))
        self.assertIs(s["record"], v2)
        self.assertEqual((s["approving"], s["current"], s["earlier"]), (True, True, 0))
        self.assertEqual(s["approvers"], [seen(v2)])
        # With no version there is no summary.
        self.assertIsNone(standard.summary([]))
        self.assertIsNone(standard.summary([seen(yes(1, "A")), seen(ticked(2, "B", VER1))]))
        self.assertIsNone(standard.summary([seen(v2, withdrawn=True)]))

    def test_what_an_accept_approves(self):
        self.assertEqual(standard.approved(wrote(1, "A", V2)), VER2)  # a version: its own text's
        self.assertEqual(standard.approved(ticked(2, "B", VER1)), VER1)  # an approval: the one it names
        self.assertIsNone(standard.approved(held(3, "C", V2)))  # a comment approves nothing,
        self.assertIsNone(standard.approved(yes(4, "D")))  # nor does a yes of the earlier form
        self.assertEqual(standard.approved(wrote(5, "E", V2.replace("\n", "  \r\n"))), VER2)

    def test_an_ai_accept_is_an_agents_accept_in_any_form(self):
        for r in (wrote(1, "A"), ticked(2, "B", VER1), yes(3, "C"), made(4, "D", standard={"spec": "other"})):
            self.assertTrue(standard.ai_accept(r), r)
        # Not an AI's yes: a comment, a no, a person's yes, and an author that is not a `by`.
        for r in (held(5, "E"), made(6, "F", verdict="problem"), made(7, PERSON), {**yes(8, "G"), "by": None},
                  {**yes(9, "H"), "by": "Voyager"}, {"kind": "review", "verdict": "accept"}):
            self.assertFalse(standard.ai_accept(r), r)

    def test_approvers_are_this_texts_and_apply_now(self):
        rows = [seen(wrote(1, "A", V1), superseded=True),  # A's first version, which A's edit superseded
                seen(wrote(2, "A", V2, parent=VER1)),      # v2 by A, who approves it by writing it
                seen(ticked(3, "B", VER2)),                # approval of v2 by B
                seen(ticked(4, "C", VER1)),                # approval of v1 by C
                seen(yes(5, "D")),                         # old-form yes by D
                seen(ticked(6, "E", VER2), applies=False)]  # approval of v2 by E, which no longer applies
        s = standard.summary(rows)
        self.assertEqual(tools(s["approvers"]), ["B", "A"])
        self.assertEqual(s["earlier"], 3)  # C, D, E
        self.assertEqual((s["version"], s["approving"], s["current"]), (VER2, True, True))
        # Whatever order the caller holds them in.
        self.assertEqual(standard.summary(rows[::-1]), s)

    def test_a_yes_withdrawn_or_superseded_counts_nowhere(self):
        rows = [seen(wrote(1, "A", V2)),
                seen(ticked(2, "B", VER2), superseded=True),  # B ticked again at 3
                seen(ticked(3, "B", VER2)),
                seen(ticked(4, "C", VER2), withdrawn=True),
                seen(ticked(5, "C", VER1), superseded=True),
                seen(yes(6, "D"), superseded=True),
                seen(yes(7, "E"), withdrawn=True)]
        s = standard.summary(rows)
        self.assertEqual([x.record["id"] for x in s["approvers"]], ["r3", "r1"])
        self.assertEqual(s["earlier"], 0)

    def test_approvers_come_latest_first_by_time_then_id(self):
        tied = {**ticked(5, "E", VER2), "at": made(3, "C")["at"], "id": "r9"}  # at C's instant, with the later id
        rows = [seen(wrote(1, "A", V2)), seen(ticked(3, "C", VER2)), seen(ticked(2, "B", VER2)),
                seen(ticked(4, "D", VER2)), seen(tied)]
        self.assertEqual(tools(standard.summary(rows)["approvers"]), ["D", "E", "C", "B", "A"])

    def test_only_an_accept_counts(self):
        rows = [seen(wrote(1, "A", V1)),
                seen(made(2, "B", verdict="problem", text="Wrong.")),
                seen(made(3, "C", verdict="question", text="Why?")),
                seen(made(4, "D", "comment", text="A remark.")),
                seen(held(5, "E", V2))]  # a version, but a comment: it approves nothing
        s = standard.summary(rows[:4])
        self.assertEqual((tools(s["approvers"]), s["earlier"]), (["A"], 0))
        s = standard.summary(rows)
        self.assertEqual((s["version"], tools(s["approvers"]), s["earlier"]), (VER2, [], 1))

    def test_a_version_is_its_texts_hash_whatever_its_line_endings(self):
        crlf = V2.replace("\n", "  \r\n")
        s = standard.summary([seen(wrote(1, "A", crlf)), seen(ticked(2, "B", VER2))])
        self.assertEqual((s["version"], tools(s["approvers"]), s["earlier"]), (VER2, ["B", "A"], 0))
        self.assertEqual(s["text"], crlf)  # as recorded

    def test_a_comment_version_approves_nothing(self):
        mine = held(1, "M")
        s = standard.summary([seen(mine)])
        self.assertEqual((s["approving"], s["approvers"], s["current"], s["earlier"]), (False, [], True, 0))
        self.assertEqual((s["version"], s["text"]), (VER1, V1))
        self.assertIs(s["record"], mine)
        # An AI that then approves it is its approver, and the comment is not.
        s = standard.summary([seen(mine), seen(ticked(2, "B", VER1))])
        self.assertEqual((s["approving"], tools(s["approvers"]), s["current"], s["earlier"]), (False, ["B"], True, 0))

    def test_a_maintainers_edit_strands_the_approvals_and_a_restore_brings_them_back(self):
        a, b = seen(wrote(1, "A", V1)), seen(ticked(2, "B", VER1))
        edit = seen(made(3, PERSON, "comment", text=V2, standard={"spec": standard.SPEC, "parent": VER1, "note": "n"}))
        s = standard.summary([a, b, edit])
        self.assertEqual((s["version"], s["approving"], s["approvers"], s["current"]), (VER2, False, [], True))
        self.assertEqual(s["earlier"], 2)  # A's and B's, of the text before
        restores = {"spec": standard.SPEC, "parent": VER2, "restores": VER1}
        restore = seen(made(4, PERSON, "comment", text=V1, standard=restores))
        s = standard.summary([a, b, edit, restore])
        self.assertEqual((s["version"], s["approving"], tools(s["approvers"])), (VER1, False, ["B", "A"]))
        self.assertEqual(s["earlier"], 0)

    def test_out_of_date_when_nothing_about_it_applies(self):
        v1, tick = wrote(1, "A", V1), ticked(2, "B", VER1)
        s = standard.summary([seen(v1, applies=False), seen(tick, applies=False)])
        self.assertEqual((s["current"], s["approvers"], s["earlier"], s["approving"]), (False, [], 2, True))
        self.assertFalse(standard.summary([seen(held(1, "M"), applies=False)])["current"])
        # One approver that applies is enough, though the version's own record does not,
        s = standard.summary([seen(v1, applies=False), seen(tick)])
        self.assertEqual((s["current"], tools(s["approvers"]), s["earlier"]), (True, ["B"], 1))
        # and so is the version's own record, a comment, though every approval is stale.
        s = standard.summary([seen(tick, applies=False), seen(held(3, "M"))])
        self.assertEqual((s["current"], s["approvers"], s["earlier"]), (True, [], 1))

    def test_people_are_never_approvers(self):
        mine = wrote(4, "A", V1)
        people = [made(1, PERSON, text=V1, standard={"spec": standard.SPEC}),  # an accept that carries the same text
                  made(2, PERSON, text="Approves.", standard={"spec": standard.SPEC, "approves": VER1}),  # a tick of it
                  made(3, PERSON, text="The integers, as in any textbook.")]  # a yes of the earlier form
        s = standard.summary([*map(seen, people), seen(mine)])
        self.assertEqual((tools(s["approvers"]), s["earlier"]), (["A"], 0))
        # Alone, the first is the text that is current, and it approves itself for nobody.
        s = standard.summary([seen(people[0])])
        self.assertEqual((s["version"], s["approving"], s["approvers"], s["current"]), (VER1, False, [], True))
        self.assertEqual(s["earlier"], 0)
        # Nor does a person's tick, or a person's yes, count as an approval of an earlier text.
        for r in people[1:]:
            s = standard.summary([seen(r), seen(held(5, "M"))])
            self.assertEqual((s["approvers"], s["earlier"]), ([], 0))


if __name__ == "__main__":
    unittest.main()
