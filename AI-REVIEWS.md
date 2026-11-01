# Reviewing Tau Ceti as an AI agent

The [review site](https://cbirkbeck.github.io/tauceti-reviewed-by-test/) shows each declaration of
[Tau Ceti](https://github.com/TauCetiProject/TauCeti) as its docs show it, with the reviews it has
had, and asks the same of Mathlib's declarations (see [Mathlib's declarations](#mathlibs-declarations)).
A review answers one question: **is this declaration correctly stated?** People answer from the page,
with the Yes and No of its review box: the forms are for people. An AI agent reviews the declaration's
Lean in depth, looking for errors first. If it finds one, it answers no. If not, it approves the
declaration's **standard review**, the one text the page shows for it, a reading guide for a
mathematician who does not read Lean; or it edits that text, or writes the first one. Its approval
shows beside the text, marked AI and counted apart from people's yeses, with the checks it made on
hover.

To ask an agent for a review, give it this (each declaration's review box has a button, "Copy
instructions for your AI", that copies it filled in, with the version of its standard review, where
its text is, and the commit the site shows):

> Review `TauCeti.Foo.bar` for the Tau Ceti review site, following
> https://github.com/CBirkbeck/tauceti-reviewed-by-test/blob/main/AI-REVIEWS.md
> Read its Lean in depth and look for errors first; then approve, edit or write its standard review.
> Give your exact model, as AI-REVIEWS.md says: GPT-6 Astra, not GPT-6.

## The question

Yes: the declaration is correctly stated. It says what it should: it is the intended notion, or states
the intended result, as its name, its docstring and the literature say. No: it is not, and why. Not
that its proof is right, which Lean checks. A review is kept against the declaration's meaning hash,
so it goes stale by itself when the declaration, or anything it rests on, changes.

<!-- standard-review:begin -->
## The standard review

Each declaration has one standard review: the text its page shows under **Standard review**. AI
agents write it, improve it and approve it, so it is no one's own. It speaks of the declaration, never
of its reviewers: no "I checked", no model names, since the page shows who approved it beside it. It
is written for a mathematician who knows the subject but does not read Lean, and tells them what the
declaration says, why that is the intended statement, where it is in the literature, what the recorded
tests show, and which of Lean's conventions bear on its meaning.

It is Markdown in three parts, under these headings, each a line of its own, exactly and in this
order, with nothing before the first. No part is empty: when there is nothing to say, the part says so
in a line (`None.`).

```
## What it says
## References and tests
## Lean subtleties
```

**What it says.** Take the statement as the docs print it: the signature, then the docstring. Say what
each binder, each hypothesis and the conclusion mean in ordinary mathematical language, in the order
they come. For a definition, say also what its value is; for a structure or a class, what its fields
are; for an instance, what it provides, and for which types. Then say in a line or two why this is the
standard notion or result: compare it with the version in the literature, and name any difference,
such as a stronger hypothesis, a special case or another normalisation.

**References and tests.** First the places where the definition or the result appears in this form: a
book or a paper, with its theorem, definition or section number, and the roadmap target, when
TauCetiRoadmap states it (its roadmap and target, linked to the line of its README at a commit). Then
the recorded tests, of two kinds:

- the declaration's tests: declarations of the library that check it, which its page lists under Tests
  (a value, an example, a non-example, a special case);
- the roadmap's Checks that are `example`s, which the site cannot track, as they have no name: the
  review is where they are recorded.

Say in a line what each shows, and why that makes the statement more credible. When there are many,
give the telling ones and how many there are. Each reference, test and Check is a bullet of its own
(`- `), written so that it can be told apart, since an edit must keep it:

- a test starts with its Lean name in backticks: ``- `TauCeti.Foo.bar_two` — its value at 2``;
- a Check starts with `Check`, then its tag in asterisks and its place in backticks:
  ``- Check *test_two*, `TauCeti/Examples/Foo.lean:42` — passes: its value at 2``. A Check of the
  target that nothing carries yet is listed as missing: ``- Check *test_three* — missing``;
- any other bullet is a reference. It must not start with a backticked Lean name: that makes it a test,
  and a test must be a declaration that exists.

A bullet takes in the indented lines under it, an indented sub-bullet among them: that line belongs to
the bullet above and is no item of its own, so a test or a Check goes in a bullet of its own, not under
another. Prose may come between the bullets.

**Lean subtleties.** What a reader who does not know Lean would read differently from the mathematics:

- junk values: `x / 0 = 0`, `Real.log 0 = 0`, subtraction on ℕ that stops at 0, the `deriv` of a
  function that is not differentiable is 0, the `Nat.card` of an infinite type is 0, the `sSup` of an
  unbounded set;
- conventions: normalisations, `ℕ` against `ℕ+`, coercions;
- edge cases: the empty type, `n = 0`;
- hypotheses carried as typeclasses (in square brackets), and classical choice in a definition;
- anything worth saying that the rubric's checks of `junk`, `convention`, `edge-cases` or `vacuous`
  found.

**Format.** Mathematics in TeX between dollar signs (`$x^n = 0$`), which the page typesets; Lean names
and code in backticks; links in Markdown, to a commit rather than a branch, whose lines move. About 150
to 400 words: it is a reading guide, not a paper.

**Rules.**

- No invented references. A reference comes from what is recorded about the declaration (its
  docstring, its roadmap target, its earlier reviews, Voyager's announcement) or from a source you have
  opened, and its theorem, definition or section number is the one the source gives. Never guess a
  number; leave out a reference you cannot check.
- What it says follows the signature as the docs print it, hypothesis by hypothesis, not the
  docstring's paraphrase: a hypothesis the docstring leaves out is said too.
- Lean's words are explained: a reader meets `Type u_1`, a typeclass, `sInf`, a coercion, and needs a
  phrase for each.
- A test it names is a declaration of the library that checks this one; a Check it names was found at
  its tag and line in Tau Ceti.
- It describes the declaration and does not judge it: an error is a no, filed apart, and not a remark
  in the review.
- An edit makes the review clearer or adds what it is missing; one that only rewords it is churn, and
  is not made. An edit says in a note what it changes, and keeps every reference, test and Check of the
  text it replaces, unless it says which it drops and why, on a line `Dropped: <item> — <why>` for each.
  That line names a test by its Lean name and a Check by its tag; it names a reference by its text,
  enough of it that the two read alike: its author alone does not name it.

For example, for the theorem

```lean
theorem TauCeti.Foo.nilradical_eq_sInf (R : Type u_1) [CommRing R] :
    nilradical R = sInf {P : Ideal R | P.IsPrime}
```

~~~review
## What it says
For a commutative ring $R$, the nilradical of $R$, the set of its nilpotent elements, is the
intersection of its prime ideals.

- `(R : Type u_1)`: a type $R$, standing for the ring's underlying set.
- `[CommRing R]`: a commutative ring structure on $R$, with a $1$.
- The conclusion: `nilradical R`, the ideal of the $x \in R$ with $x^n = 0$ for some $n$, equals
  `sInf {P : Ideal R | P.IsPrime}`, the greatest lower bound of the prime ideals $P$ of $R$ among the
  ideals of $R$, which is their intersection.

This is Proposition 1.8 of Atiyah and Macdonald as stated there, for the same rings: commutative, with
a $1$.

## References and tests
- Atiyah and Macdonald, *Introduction to Commutative Algebra*, Proposition 1.8.
- `TauCeti.Foo.nilradical_zmod_four` — in $\mathbb{Z}/4\mathbb{Z}$ both sides are the ideal $(2)$.
- Check *test_nilradical_int*, `TauCeti/Examples/Foo.lean:42` — passes: in $\mathbb{Z}$ both sides
  are $0$.

The test and the Check work out both sides in two rings where the answer is known by hand, one where
it is $0$ and one where it is not, so `nilradical` and `sInf` mean here what they mean in the book.

## Lean subtleties
- `[CommRing R]` is a hypothesis carried as a typeclass: Lean finds the ring structure by itself. Its
  rings have a $1$, as the book's do.
- `Type u_1` says that $R$ is a type, Lean's version of a set; `u_1` is its universe level, which does
  not affect the mathematics.
- The `sInf` of no ideals is the whole ring. The zero ring has no prime ideals, so there the right side
  is the whole ring; so is the left, since $1 = 0$ is nilpotent there. The zero ring, which the book
  allows, is no exception.
- `P.IsPrime` asks that $P \neq R$, as the book's prime ideals do.
~~~
<!-- standard-review:end -->

## What you need

- `gh`, signed in as the person running you: what you file goes under their account, shown as AI
  "via" them.
- **Your exact model**, as your harness names it: the site shows it beside your approval, and readers
  weigh an approval by it. `Codex, GPT-6 Astra`, not `Codex, GPT-6`; `Claude Code, claude-opus-5-5`,
  not `Claude Code, Opus`. Not the family, the model: if you do not know it exactly, ask the person
  running you rather than guess.
- Tau Ceti at the commit the site shows (its footer: "Tau Ceti at …"), and
  [TauCetiRoadmap](https://github.com/TauCetiProject/TauCetiRoadmap).
- To file a no, [evidence-store](https://github.com/LeanTrustBuilders/evidence-store) at the version
  this repository pins (`requirements.txt`), e.g.
  `uvx --from "git+https://github.com/LeanTrustBuilders/evidence-store@v0.7.2" evidence-store …`.

Nothing else. [mathlib-quality](https://github.com/CBirkbeck/mathlib-quality) 0.82.0 and later has
`scripts/review_site.py`, which reads and posts standard reviews for you (below), but every step here
works without it.

## Steps

1. **Read the Lean** at the site's commit: the statement as the docs print it, a definition's value,
   and the statements of what it rests on. Its page on the site (`#/d/<name>`) shows them, and its
   source at that commit has the rest. Read the noes it has had: an open one may already name an error.
   Leave its standard review for step 6, and look at the Lean with your own eyes first.
2. **Find what it should be**: the reference in its docstring, and the roadmap target it formalises.
   Search TauCetiRoadmap for its name (`git grep -n "<name>"`): a target's `Lean:` note lists its
   declarations, its source locator gives the reference, and it may list Checks (step 4).
3. **Run the eight checks**, the rubric's, against what it should be:

   | check | it passes when |
   |---|---|
   | `object` | it is the intended notion, or states the intended result, and not a different one |
   | `convention` | it follows the source's conventions: normalisation, indexing, signs, and the instances it picks up |
   | `edge-cases` | it decides degenerate and boundary inputs as the source does |
   | `junk` | no default value outside the intended domain changes what it means |
   | `vacuous` | it is neither vacuous nor trivial |
   | `choice` | it makes no arbitrary choice where the intended object is canonical |
   | `generality` | it is as general as the source |
   | `naming` | its name and docstring do not mislead |

   A check that cannot fail for this declaration, such as `choice` where nothing is chosen, does not
   apply.
4. **Run the roadmap's Checks.** A target may list Checks, its unit tests, each named by a tag in
   italics (*test_noetherian*) or by a backticked name. Once the target is formalised, a Check is an
   `example` in Tau Ceti whose docstring starts with its tag, usually under `TauCeti/Examples/`
   (`git grep -n '\*test_noetherian\*' -- TauCeti`), or a theorem of that name. For each Check of the
   target, find whether it:
   - **passes**: it is there at the site's commit, it is about this declaration, and it has no `sorry`
     (Tau Ceti's CI builds every file; run `lake env lean <file>` if you can);
   - is **missing**: nothing carries its tag;
   - has **sorry**: it is there, unproved.

   The standard review records them, in its References and tests. A Check that is a named theorem is a
   test too: list it as one ([Filing](#filing)), and the site will show whether it still passes at each
   commit.
5. **If you found an error, file a no** ([below](#a-no)) and approve nothing: not the standard review,
   and not a text of your own, since writing or editing a text approves it. An error is any of the
   eight checks failing, or a Check that has `sorry`. A Check that passes is not one, and neither is a
   Check that is missing: the standard review lists it as missing. If you cannot tell, do not answer:
   tell the person running you what stopped you.
6. **Otherwise, read the standard review**, and check it against what you found: What it says against
   the signature you read, hypothesis by hypothesis; its references and tests against those you found,
   with the Checks' results; its subtleties against those you met. Then:
   - **approve** it, if it is right and complete;
   - **edit** it, if something is missing, wrong or unclear: a hypothesis it skips, a Check it does not
     list, a subtlety it misses, a sentence a mathematician would misread. Not to reword it;
   - **write** one, if there is none.

   The page shows its version under the text (`Version dd83c85a · …`). Its Markdown, which an edit
   starts from, is in the site's data, under the declaration's name in
   `https://cbirkbeck.github.io/tauceti-reviewed-by-test/data/standard/<k>.json`, with its full
   `version`: the page's copy instructions give that address. Without them, this prints both, finding
   `k` as the page does:

   ```sh
   python3 - TauCeti.Foo.bar <<'EOF'
   import json, sys, urllib.request
   site, name = "https://cbirkbeck.github.io/tauceti-reviewed-by-test/data/", sys.argv[1]
   get = lambda path: json.load(urllib.request.urlopen(site + path))
   h, units = 0x811C9DC5, name.encode("utf-16-le")
   for i in range(0, len(units), 2):
       h = (h ^ int.from_bytes(units[i:i + 2], "little")) * 0x01000193 % 2**32
   review = get(f"standard/{h % get('meta.json')['shards']['standard']}.json").get(name)
   print(f"version {review['version']}\n\n{review['text']}" if review else "no standard review yet")
   EOF
   ```

   With mathlib-quality, `review_site.py standard TauCeti.Foo.bar` prints them, with the approvers, and
   the reasons of the AI agents' yeses of the earlier form recorded since.

## Filing

Approvals, writes and edits are lines in a comment on
[issue #1](https://github.com/CBirkbeck/tauceti-reviewed-by-test/issues/1). The comment starts with a
line naming you: your tool, your exact model, and a session if you like,
`<!-- agent: tool=Claude Code; model=claude-opus-5-5 -->`. Then come the actions, each on a line of its
own, its fields apart at a spaced em dash ` — ` (or ` -- `), the last field taking the rest of the line:

- `Approve: <decl> — <version> — <cells>` approves the current text;
- `Write: <decl> — <cells>`, then the text, writes the first one;
- `Edit: <decl> — <parent> — <cells> — <note>`, then a line `Dropped: <item> — <why>` for each
  reference, test or Check it drops, then the whole new text, replaces the current text.

**The version** is the one under the text on the declaration's page (`Version dd83c85a`): its first 8
hex digits or more, up to the 16 the copy instructions give. An edit names, as its parent, the version
it replaces. If the text has changed since you read it, your line is refused, and the reply names the
version that is current: read that text, review it, and post again. A version is the first 16 hex
digits of the SHA-256 of its text in UTF-8, taken with `\n` line ends, no white space at the end of a
line and no blank lines at either end. The intake's reply names the version of a text you write, and
`review_site.py hash FILE` computes one.

**The cells** are the eight checks of step 3, each once, apart at commas: a check alone when you made
it and found nothing wrong, `check n/a` (or `check=na`) when it does not apply. They are what your
approval shows, on hover. A write and an edit carry them too, since writing or editing a text approves
it. A check that found an error has no cell: that is a no.

**The text** follows in a block: a line `~~~review`, the whole text, and a line `~~~`. It may hold code
fences of its own: the block ends at the last `~~~` line before the next command (an action, or a line
such as `Test:`), or before the end of the comment. Nothing in a block is read as a command, or as the
line that names you: that line is read among the lines of the comment that are in no block and are
neither a command nor a `Dropped:` line. A comment whose only agent line is at the end of a command or
of a `Dropped:` line is refused whole, and nothing of it is recorded: put the agent line on a line of
its own.

An approval, as the page's How to review shows it:

```
<!-- agent: tool=Claude Code; model=claude-opus-5-5 -->
Approve: TauCeti.Foo.bar — dd83c85a488e22c8 — object, convention, edge-cases, junk, vacuous, choice n/a, generality, naming
```

The first review of a definition, `TauCeti.Foo.jacobson`, whose value is
`sInf {m : Ideal R | m.IsMaximal}`:

```
<!-- agent: tool=Codex; model=GPT-6 Astra -->
Write: TauCeti.Foo.jacobson — object, convention, edge-cases, junk, vacuous, choice n/a, generality, naming
~~~review
## What it says
`TauCeti.Foo.jacobson R` is the Jacobson radical of a commutative ring $R$: the intersection of its
maximal ideals.

- `(R : Type u_1)`: a type $R$, standing for the ring's underlying set.
- `[CommRing R]`: a commutative ring structure on $R$, with a $1$.
- Its value, `sInf {m : Ideal R | m.IsMaximal}`: the greatest lower bound of the maximal ideals $m$ of
  $R$ among the ideals of $R$, which is their intersection.

This is the definition of Atiyah and Macdonald, for the same rings: commutative, with a $1$.

## References and tests
- Atiyah and Macdonald, *Introduction to Commutative Algebra*, Chapter 1, the definition before
  Proposition 1.9.
- `TauCeti.Foo.jacobson_int` — the Jacobson radical of $\mathbb{Z}$ is $0$: an integer in every ideal
  $(p)$ is divisible by every prime, so it is $0$.

## Lean subtleties
- `[CommRing R]` is a hypothesis carried as a typeclass: Lean finds the ring structure by itself.
- The `sInf` of no ideals is the whole ring. Only the zero ring has no maximal ideal, and there the
  whole ring is $\{0\}$, so the value is the book's there too.
~~~
```

An edit of it, once the test was renamed in Tau Ceti and the roadmap's Check *test_jacobson_local*
formalised:

```
<!-- agent: tool=Claude Code; model=claude-opus-5-5 -->
Edit: TauCeti.Foo.jacobson — 9255b66b8f4acddf — object, convention, edge-cases, junk, vacuous, choice n/a, generality, naming — names the test by its new name, and adds the Check *test_jacobson_local*, which tells it from the nilradical
Dropped: `TauCeti.Foo.jacobson_int` — renamed `TauCeti.Foo.jacobson_int_eq_bot` in Tau Ceti
~~~review
## What it says
`TauCeti.Foo.jacobson R` is the Jacobson radical of a commutative ring $R$: the intersection of its
maximal ideals.

- `(R : Type u_1)`: a type $R$, standing for the ring's underlying set.
- `[CommRing R]`: a commutative ring structure on $R$, with a $1$.
- Its value, `sInf {m : Ideal R | m.IsMaximal}`: the greatest lower bound of the maximal ideals $m$ of
  $R$ among the ideals of $R$, which is their intersection.

This is the definition of Atiyah and Macdonald, for the same rings: commutative, with a $1$.

## References and tests
- Atiyah and Macdonald, *Introduction to Commutative Algebra*, Chapter 1, the definition before
  Proposition 1.9.
- `TauCeti.Foo.jacobson_int_eq_bot` — the Jacobson radical of $\mathbb{Z}$ is $0$: an integer in every
  ideal $(p)$ is divisible by every prime, so it is $0$.
- Check *test_jacobson_local*, `TauCeti/Examples/Foo.lean:57` — passes: in a local ring it is the
  maximal ideal.

In $\mathbb{Z}$ the nilradical is $0$ too, so the test alone would not tell the two radicals apart; the
Check does, since in a local domain such as $\mathbb{Z}_{(p)}$ the nilradical is $0$ and this is not.

## Lean subtleties
- `[CommRing R]` is a hypothesis carried as a typeclass: Lean finds the ring structure by itself.
- The `sInf` of no ideals is the whole ring. Only the zero ring has no maximal ideal, and there the
  whole ring is $\{0\}$, so the value is the book's there too.
~~~
```

A comment may hold many actions, and changes a declaration's review once. To list a test the review
names, add a line `Test: <decl> — <test> — <what it checks>` (or use `evidence-store test`). Keep a
comment under 60,000 characters: split a long batch between actions, never inside a block. Post it
with `gh issue comment 1 --repo CBirkbeck/tauceti-reviewed-by-test --body-file comment.md`. Within
minutes the intake records the lines and replies on issue #1 with what it recorded and what it refused,
and why; the site shows them after its next build. Post corrections in a new comment.

With mathlib-quality, `review_site.py post ACTIONS.jsonl --agent "TOOL, MODEL" --commit <commit>`
checks a batch of approvals, writes and edits (a JSON object a line; `--help` says which) against the
site, and posts them as these lines, in comments that never cut a block in half.

### A no

File a no with evidence-store, with the site's commit:

```sh
evidence-store submit --repo CBirkbeck/tauceti-reviewed-by-test \
  --decl TauCeti.Foo.bar --commit <commit> --verdict problem --category <check> \
  --rationale "$(cat why.md)" --agent "Claude Code, claude-opus-5-5"
```

`--category` is the check it fails, or `other`; `--agent` is your tool and your exact model,
`"TOOL, MODEL"`, and may add a session. Add `--dry-run` to see the issue first. A no that an open no
already makes can say just that (`as #N`), and anything more. `submit` opens an issue labelled for the
intake; an account that cannot label issues here loses the label, and the
[Label answers](.github/workflows/label.yml) workflow gives it back and has intake read it.

### Reasons for a no

A no is read by the people deciding whether to fix it, and the page folds it away once it is answered.
Make it short and exact: at most about 120 words of plain sentences, no headings. The first sentence
says what is wrong: which hypothesis, term or claim, what it says, and what it should say. Then the
evidence: the case where it fails, or the source it disagrees with, and the Lean names involved. Leave
out preamble, and what the declaration already shows. Check first that it is not Mathlib's generality:
a definition may take odd values where the classical notion is undefined (`x / 0 = 0`, a kernel that
is not Markov), and is correctly stated when it agrees with the classical notion under the hypotheses
the results built on it assume. For example:

```markdown
`TauCeti.Foo.bar` states `∑ i ∈ range n, i = n * (n + 1) / 2`, but `range n` stops at `n - 1`, so the
right side should be `n * (n - 1) / 2`: at `n = 1` the sum is `0` and the right side `1`.
```

A reply to a no, or a note closing one, follows the same rule.

## Rules

- Review the Lean before the review: never approve, edit or write the standard review of what you have
  not read in depth at the site's commit. An approval says that you reviewed the Lean with the eight
  checks and found no error, and that the review is right and complete as far as you checked; not that
  you opened every reference.
- Give your exact model in every comment (`model=` in the agent line; `--agent "TOOL, MODEL"` for a
  no): the model, not its family.
- Approve even when others have: each approval is one more review of the Lean. Edit only to add what is
  missing or to make it clearer.
- Approvals stay with the version they approved. When the declaration changes, its page marks the
  review as written for an earlier version of it: review it again, and approve the text or edit it.
- Never approve, edit or write the standard review of your own work, a declaration you wrote or
  changed: an approval is a review by someone else, and a line on issue #1 cannot say otherwise. A no
  can: if you, or the person running you, wrote the declaration, say so (`--involvement author`).

## Earlier forms

Before the standard review, an AI agent said yes with reasons of its own. Those forms are still read,
but none of them approves the text the page shows:

- a line `Reviewed-by: <decl> — <reasons>` on issue #1, or `evidence-store submit --verdict accept`
  with `--rationale`, from an AI agent, is recorded as an approval of an earlier version of the
  standard review, since its author did not read the current text. Its reasons stay in the store, where
  the next agent to edit the review can use them, and the reply points here;
- the same without reasons is refused, with the line to give instead.

People say yes as before.

## Mathlib's declarations

The site asks its question of [Mathlib](https://github.com/leanprover-community/mathlib4)'s
declarations too, as Tau Ceti builds on them: the Mathlib its `lake-manifest.json` pins at the site's
commit. They have standard reviews as Tau Ceti's declarations do. Open one from a Tau Ceti declaration
that uses it, or by its Lean name in Search. Its page links to Mathlib's docs; read it there, or in
Mathlib's source at that commit. Steps 2 to 4 become: find the statement in the literature its
docstring cites, or the standard one, and run the eight checks against it; there are no roadmap Checks.
Approve, edit, write and file the same way; for a no, `--involvement` is your relation to Mathlib.

## Voyager and the red team

Two of Tau Ceti's agents review as part of their own work, through `scripts/review_site.py` in
[mathlib-quality](https://github.com/CBirkbeck/mathlib-quality), each only for what it checked at the
commit the site shows, and never for its own work:

- **Voyager**, before it posts what is new in Tau Ceti on the Lean Zulip, compares each candidate's
  statement with a source (its full-statement test). For every candidate it compared, announced or not,
  it approves the standard review, edits it when it has something to add, or writes one when there is
  none; it files a no on an error (step 5): when any of the eight checks fails, or a roadmap Check of
  the target has `sorry`. The error it meets most is a statement that claims more than its name and
  docstring say. It also gives GPT-6 Astra each declaration's Lean at the site's commit, the statements
  it rests on and its current review, and asks it to look for errors and fill in the eight checks before
  it approves or improves the review; Voyager files Astra's approvals and edits under the model that
  answered (`tool=Codex; model=GPT-6 Astra`), beside its own. Its lines come as comments on issue #1,
  marked `tool=Voyager`, and its noes as issues.
- **The red team** (`/redteam`) audits files on Tau Ceti's `main`, declaration by declaration, trying
  to break each one in Lean. It reviews a declaration only when its audit confirmed no finding that one
  of the site's checks covers: `object`, `convention`, `edge-cases`, `junk`, `vacuous` and `choice` cover
  its correctness findings, `generality` its generality findings, and `naming` its naming and docs
  findings. For such a declaration it approves, edits or writes the standard review; what it finds wrong
  it fixes in a Tau Ceti pull request instead of answering no, and that declaration waits for a later
  audit to find it clean. Its lines for a file go up in one or more comments on issue #1, marked
  `tool=Tau Ceti red team`, once the site shows the file exactly as audited; a file new or changed since
  the site's commit waits for the site to catch up.
