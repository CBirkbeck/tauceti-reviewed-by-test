# Reviewing Tau Ceti as an AI agent

The [review site](https://cbirkbeck.github.io/tauceti-reviewed-by-test/) shows each declaration of
[Tau Ceti](https://github.com/TauCetiProject/TauCeti) as its docs show it, with the reviews it has
had. A review answers one question: **is this declaration correctly stated?** Yes, or no and why.
People answer from the page, with the Yes and No of its review box: the forms are for people. An AI
agent answers from the command line, as below; its answer shows in the same box as a mark of its own,
marked AI and counted apart from people's, with its reasons on hover and on its issue. So the reasons
are the review: write them for a mathematician who will read them.

To ask an agent for a review, give it this (each declaration's review box has a button, "Copy
instructions for your AI", that copies it filled in, with the commit the site shows):

> Review `TauCeti.Foo.bar` for the Tau Ceti review site, following
> https://github.com/CBirkbeck/tauceti-reviewed-by-test/blob/main/AI-REVIEWS.md

## What a review says

Yes: the declaration is correctly stated. It says what it should: it is the intended notion, or states
the intended result, as its name, its docstring and the literature say. No: it is not, and why. Not
that its proof is right, which Lean checks. A review is kept against the declaration's meaning
hash, so it goes stale by itself when the declaration, or anything it rests on, changes.

## What you need

- `gh`, signed in as the person running you: the review is filed under their account, shown as AI
  "via" them.
- [evidence-store](https://github.com/LeanTrustBuilders/evidence-store) at the version this repository
  pins (`requirements.txt`), e.g. `uvx --from "git+https://github.com/LeanTrustBuilders/evidence-store@v0.7.2" evidence-store …`.
- Tau Ceti at the commit the site shows (its footer: "Tau Ceti at …"), and
  [TauCetiRoadmap](https://github.com/TauCetiProject/TauCetiRoadmap).

## Steps

1. **Read it as the docs show it**: its page on the site (`#/d/<name>`: the signature, the docstring, a
   definition's value), and its source at the site's commit.
2. **Find what it should be**: the reference in its docstring, and the roadmap target it formalises.
   Search TauCetiRoadmap for its name (`git grep -n "<name>"`): a target's `Lean:` note lists its
   declarations, and its source locator gives the reference.
3. **Compare** them, along the rubric's axes: `object`, `convention`, `edge-cases`, `junk`, `vacuous`,
   `choice`, `generality`, `naming`. Note which you checked, and which you did not.
4. **Run the roadmap's Checks.** A target may list Checks, its unit tests, each named by a tag in
   italics (*test_noetherian*) or by a backticked name. Once the target is formalised, a Check is an
   `example` in Tau Ceti whose docstring starts with its tag, usually under `TauCeti/Examples/`
   (`git grep -n '\*test_noetherian\*' -- TauCeti`), or a theorem of that name. For each Check of the
   target, say whether it:
   - **passes**: it is there at the site's commit, it is about this declaration, and it has no
     `sorry` (Tau Ceti's CI builds every file; run `lake env lean <file>` if you can);
   - is **missing**: nothing carries its tag;
   - has **sorry**: it is there, unproved.

   An `example` has no name, so the site cannot track it as a test: your review is where the Check is
   recorded. List every Check in your reasons, with its result and a link to its line at the commit.
   When a Check is a named theorem, also list it as a test (`evidence-store test`, below), and the
   site will show whether it still passes at each commit. A Check that fails is a problem, not an
   acceptance.
5. **Decide**: yes when it says what it should and every Check there passes; no when it does not, or a
   Check fails. If you cannot tell, do not answer: tell the person running you what stopped you.
6. **File it**, with the site's commit. Yes:

   ```sh
   evidence-store submit --repo CBirkbeck/tauceti-reviewed-by-test \
     --decl TauCeti.Foo.bar --commit <commit> --verdict accept \
     --rationale "$(cat reasons.md)" --agent "Claude Code, claude-opus-5-5"
   ```

   No: `--verdict problem --rationale "$(cat why.md)"`, the same otherwise. Your reasons say what you
   compared it with and what you checked; the page shows them as they are. To list a named test,
   `evidence-store test --repo … --decl TauCeti.Foo.bar --test TauCeti.Foo.bar_zero --checks "*test_zero*: its value at 0" --agent "…"`;
   to propose one that is not there yet, `evidence-store challenge`. Add `--dry-run` to see the issue
   first. Within minutes the intake workflow records it and the site shows it.

Reasons for a yes look like this:

```markdown
Correctly stated: it matches Stacks, Tag 0BSC, the same ring and the same map to its completion.

Checks (TauCetiRoadmap/ModularCurves, strict henselisation):
- *strictHenselization_sepClosed_field*: passes, [TauCeti/Examples/…/Strict.lean#L22](https://github.com/TauCetiProject/TauCeti/blob/<commit>/TauCeti/Examples/…/Strict.lean#L22)
- *strictHenselization_finite_field*: passes, […]
- *strictHenselization_not_complete*: missing

Not checked: generality (the source states it for any henselian pair).
```

## If the issue does not take its label

`submit` opens an issue labelled for the intake. An account that cannot label issues here (it needs
triage access) may lose the label, and then the intake does not see the issue. Then comment instead
on [issue #1](https://github.com/CBirkbeck/tauceti-reviewed-by-test/issues/1), which takes one record
per line, with a line naming the agent:

```
<!-- agent: tool=Claude Code; model=claude-opus-5-5 -->
Reviewed-by: TauCeti.Foo.bar — Matches Stacks 0BSC. Checks: *test_a* passes (TauCeti/Examples/…#L22); *test_b* passes.
Test: TauCeti.Foo.bar — TauCeti.Foo.bar_zero — *test_zero*: its value at 0
```

A line is one record, so its reasons are the rest of the line.

## Rules

- Say what you checked and what you did not; never answer yes to what you have not read at the site's
  commit.
- One declaration per review. When it changes, the site shows your review as of an earlier version;
  review it again.
- If you, or the person running you, wrote the declaration, say so (`--involvement author`).

## Voyager and the red team

Two of Tau Ceti's agents answer as part of their own work, through `scripts/review_site.py` in
[mathlib-quality](https://github.com/CBirkbeck/mathlib-quality), each only for what it checked at the
commit the site shows, and never for its own work:

- **Voyager**, before it posts what is new in Tau Ceti on the Lean Zulip, compares each candidate's
  statement with a source (its full-statement test). It answers for every candidate it compared,
  announced or not: yes when the statement says what its name and docstring say, no when they claim
  more. Its yeses come as one comment on issue #1, its noes as issues, marked `tool=Voyager`.
- **The red team** (`/redteam`) audits a file declaration by declaration, trying to break each one in
  Lean. It answers yes for each declaration whose correctness checks all passed, and no for each
  finding it confirmed in Lean that a declaration is not correctly stated, with the probe and a second
  opinion; marked `tool=Tau Ceti red team`. When its fix lands it marks the no fixed
  (`/fixed <commit>`), and it withdraws a no that review overturns.
