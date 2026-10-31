# Writing standard reviews for the Tau Ceti review site

The [Tau Ceti review site](https://cbirkbeck.github.io/tauceti-reviewed-by-test/) asks one question of each
declaration of Tau Ceti, and of each Mathlib declaration Tau Ceti uses: is it correctly stated? Until now, each AI agent
that said yes left a text of its own. Each declaration now gets one **standard review** instead: a reading guide for a
mathematician who knows the subject but does not read Lean. You write the first standard review of each declaration in
your batch, after reviewing its Lean in depth, or you hold it for the site's owner. A program checks every result
against what is recorded before anything is published; a result that fails is written again.

## What you have

This file, and one batch file, `batch-<nnn>.jsonl`, in the same directory. Each line of the batch file is the
**bundle** of one declaration: a JSON object holding everything recorded about it at the commit the site shows. Read
the batch a bundle at a time: the Read tool with `offset` at the bundle's line and `limit` 1.

Work from the bundles alone. Do not open Tau Ceti, Mathlib, TauCetiRoadmap or the web, and do not run Lean: what a
review says must be borne out by its bundle, and the program checks it against the bundle.

Your result file is your batch file's path with `batch-` turned into `result-`: `result-007.jsonl` for
`batch-007.jsonl`. First run

```sh
{{WRITE}} todo RESULT_FILE
```

It lists the bundles of your batch that have no line in your result file yet, by their line in the batch file. Take
those, in order. If an agent before you began your batch, the bundles it finished are not listed: begin with the first
one listed, and do not write the others again. For each bundle: review its Lean (1), decide whether to hold it (2),
write its review by the definition and rules below (3 to 5), and add its result (6), before you read the next one.

A bundle's fields:

- `decl`: the declaration's Lean name. `kind`: `theorem`, `definition`, `instance`, `class`, `structure` or
  `inductive`. `package`: `TauCeti` for Tau Ceti's own, else the package it comes from, such as `mathlib`. `commit`:
  Tau Ceti's commit the site shows.
- `signature`: the statement as the API docs print it, every argument included. What it says follows this.
- `docstring`: its docstring, which may be empty.
- `source`: the statement as written in its file. `value`: what follows it, for whatever is not a proof: a
  definition's value, a structure's, class's or inductive type's fields or constructors, the operations of an instance
  that carries data. It is empty for a theorem, and for an instance of a class that is a proposition. Each holds at
  most 4,000 characters, and a last line `…` marks a cut. A first line ``-- Written as part of `X`.`` says that the
  text is `X`'s, which makes this declaration too: the additive version `@[to_additive]` makes, a structure's field.
- `rests_on`: up to 12 declarations its statement uses, each with its `signature` and the first sentence of its `doc`.
  Empty for a declaration outside Tau Ceti.
- `reviews`: its earlier reviews, oldest first. `by`: who. `verdict`: `accept` is a yes, `problem` a no, `question` a
  question. `state`: `stands`; `superseded` by the same reviewer's later review; `withdrawn`; for a no, `open`,
  `fixed`, `intended` or `invalid`. ` (earlier version)` after the state means it was made for a version of the
  declaration that has changed since. `text`: what it says, with any reference, caveats and suggested fix it records.
  `checked`: the rubric's cells it recorded, a no's check as `error`. `at`: when.
- `tests`: its recorded tests. `test`: a declaration of the library that checks it. `text`: what it checks. `result`
  at the commit: `passes`, `sorry` or `missing`. `statement`: the test's signature.
- `checks`: the roadmap's `example` Checks that its reviews cite and that are at their tag in Tau Ceti at the commit,
  each with `tag`, `path`, `line` and `result`. Empty for every bundle today.
- `named`: Voyager's announcement of it on the Lean Zulip, its `name` and `text`; or null.
- `roadmap`: the block of TauCetiRoadmap, the plan Tau Ceti follows, that names the declaration: `name` (the roadmap),
  `path` (its file) and `block` (the text, from the heading above); or null.
- `open_no`: whether a no on it is open.
- `index`: its place in the migration. `retry`: only on a second attempt; see 6.

## 1. Review the Lean first, then hold or write

First work out, from the Lean, what the declaration says: its `signature`, `source` and `value`, and the signatures
in `rests_on` of what it uses. Then work out what it should say: its name, its docstring, `named`, the roadmap block,
and the mathematics you know. The question is whether it is correctly stated: whether it is the intended notion, or
states the intended result, as its name, its docstring and the literature say. Not whether its proof is right, which
Lean checks.

Run the rubric's eight checks against what it should be:

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

Weigh the earlier reviews once you have your own reading, as claims to test against the Lean, not conclusions to
copy: a reference, property or test of theirs counts only when the bundle bears it out. Read every no, whatever its
state: a `fixed` one names what was once wrong, so check that it is right now. A review of an earlier version may
describe a statement that has changed.

Then hold the declaration (2) or approve it, and either way write its review.

## 2. Hold when it looks wrongly stated, when an earlier AI yes looks wrong, or when `open_no` is set

Hold it, with `verdict` `hold` and the reason in `hold`, when:

- **it looks wrongly stated**: one of the checks found an error. Mark that check's cell `error`.
- **an earlier AI yes looks wrong**: an AI agent said yes on grounds the Lean does not bear out, such as a reference
  the statement does not match, or a hypothesis, a case or a property it does not have; even when the declaration
  itself is right.
- **`open_no` is true**: someone said no, and the no is still open.

Otherwise approve it: `verdict` `approve`, `hold` empty, and no cell `error`.

Hold for what the declaration says, as far as the bundle shows it; not for its style, a missing docstring, a broken
link or a vague earlier review. A claim of an earlier review that the bundle can neither confirm nor refute, such as
one about a declaration it does not give, is left out of the review: it is no reason to hold. Check first that what
looks wrong is not Mathlib's generality: a definition may take odd values where the classical notion is undefined
(`x / 0 = 0`, `Real.log 0 = 0`), and it is correctly stated when it agrees with the classical notion under the
hypotheses that the results about it assume. Such values are Lean subtleties for the review, not errors.

The reason in `hold` is for the site's owner, who decides what happens next: one to three plain sentences. First what
is wrong: which hypothesis, term or claim, what it says, and what it should say. Then the evidence: the case where it
fails, or what it disagrees with. A held declaration still gets its review, which describes the declaration as it is
and keeps the problem out of it: the problem is in `hold`, and nowhere in the review. No no is filed.

## Writing the review

The next section is quoted whole from AI-REVIEWS.md, the site's guide for AI agents: it defines the standard review.
Write yours by it, with the migration's rules after it, which hold where the two differ, since you have only the
bundle and the program checks the review against it:

- a reference, and any book, paper or numbered result the review names, comes only from the bundle, never from a
  source you open or know (3);
- the roadmap is cited only where its block states the declaration, and without a link, since the bundle gives no
  commit (3);
- no Check is listed that `checks` does not give, not even as missing (4);
- an error is not filed as a no: the declaration is held (2), and the review still describes it.

The guide's example lists a Check and names a book that a bundle may not give; the migration's own example follows 4.
The guide's rules on edits do not concern you: you write first versions.

{{STANDARD_REVIEW}}

## What it says follows the signature

Take the binder groups of `signature` in order. Give each explicit group `(…)` and each instance group `[…]` a bullet
that opens with the group in backticks, exactly as the signature prints it, and says what it means; then the
conclusion. Instance groups that say one thing together may share a bullet:
``- `[NormedAddCommGroup E] [InnerProductSpace ℝ E] [CompleteSpace E]`: $E$ is a real Hilbert space.`` Implicit
groups, `{…}` and `⦃…⦄`, and groups that only introduce a type, such as `(R : Type u_1)`, need no bullet of their own:
say what they range over where they first matter. For a definition, then say what its value is; for a structure or a
class, its fields; for an instance, what it provides, and for which types.

The program reads What it says for each explicit group's binder name, and for each instance group its class (`Module`
for `[Module ℚ V]`) or its name, as a whole word spelled as the signature spells it: `μ`, not `$\mu$`.

An instance that carries data, one that defines operations or a structure (a `Module`, a `TopologicalSpace`, a
`Field`), has a value: the data it chooses, which `value` gives. Review it as a definition's value, since another
choice of data would be another instance (`choice`, `convention`), and say in What it says what the data is. An
instance of a class that is a proposition has only a proof, and its `value` is empty, as a theorem's is. A
`deriving instance` has no value of its own: its `source` is the `deriving instance … for T` command that makes it.

## 3. References only from the bundle, with their numbers as given

A reference says where the definition or the result appears in this form: in a book, a paper, lecture notes, the
Stacks Project, or the roadmap. Take each one from a single text of the bundle: the docstring, a comment in `value`, an
earlier review, Voyager's announcement (`named`) or the roadmap block. Open its bullet with the citation as that text
gives it, in its words: its author, its title, and its theorem, definition, section or page number, its tag, year or
arXiv number. You may shorten it. Words of your own, on what it shows, come after a colon or a dash (` — `), and add no
number and no link that this one text does not give.

The program looks for the citation, the words before the first `:` or ` — ` (and any title in italics), in one text
of the bundle, which must also give every number and hold every link of the bullet. The Lean code and the tests' texts
are no such text: a citation that only shares a phrase with them, or with your own description, is not traced.

- Nothing else is a reference, however standard or well known to you: no source the bundle does not name, no number it
  does not give, and no link it does not hold. Nor is a link to Lean source, Tau Ceti's or Mathlib's, which shows the
  Lean, not where the mathematics is stated.
- The same holds for the whole review: wherever it names a theorem, proposition, lemma, corollary, definition, section,
  chapter or tag with its number, in What it says, in the prose of References and tests, in a test's line or in Lean
  subtleties, the program looks for that number in the bundle's texts. You may say without a source that a notion or a
  result is the standard one.
- The roadmap block is a reference when it states the definition or the result, as a target or a milestone does. A
  block that only reports progress, such as a dated entry of a `PROGRESS.md` or a note of a `STATUS.md`, is context
  for you, not a reference. Cite it by its roadmap, its file and its heading, without a link, since the bundle gives no
  commit: ``- TauCetiRoadmap, Arithmetic, `TauCetiRoadmap/Arithmetic/README.md`, Layer 1: tripling.`` A link to the
  roadmap at a commit that an earlier review gives may be copied as it is.
- A reference never opens with a backticked name, which is how a test opens.
- In References and tests, a Lean name in backticks is one of `tests`, the declaration, or one of `rests_on`; or a name
  a reference copies from its text.
- When the bundle gives no reference, list none, and say so in a line of prose: `No reference is recorded for it.`
- Every bullet under References and tests is a reference, a test or a Check, and each is a bullet, `- `, never an item
  of a numbered list: the site's edit check protects bullets only, so the program refuses a numbered item. Anything
  else, such as `No test is recorded.`, is a line of prose, not a bullet: the program reads every other bullet as a
  reference, and looks for it in the bundle.

## 4. Tests only from `tests`, Checks only from `checks`

- A test is one of `tests`: a bullet that opens with its `test` name in backticks, then says what it shows, from its
  `text` and its `statement`. Leave out a test whose `result` is `missing`. When there are many, give the telling ones
  and say in prose how many there are.
- A Check is one of `checks`: ``- Check *<tag>*, `<path>:<line>` — <result>: what it shows``, with the tag, path, line
  and result `checks` gives.
- `checks` is empty for every bundle today, so list no Check: not one an earlier review cites, and not one as missing.
  A Check that is not in `checks` was not found at its tag in Tau Ceti at the site's commit.

## An example

The guide's example, as the migration writes it. Suppose the bundle of `TauCeti.Foo.nilradical_eq_sInf` has the
docstring "The nilradical is the intersection of the prime ideals (Atiyah and Macdonald, *Introduction to Commutative
Algebra*, Proposition 1.8).", the test `TauCeti.Foo.nilradical_zmod_four` in `tests`, and no `checks`. Then:

~~~review
## What it says
For a commutative ring $R$, the nilradical of $R$, the set of its nilpotent elements, is the
intersection of its prime ideals.

- `[CommRing R]`: a commutative ring structure on the type $R$, with a $1$.
- The conclusion: `nilradical R`, the ideal of the $x \in R$ with $x^n = 0$ for some $n$, equals
  `sInf {P : Ideal R | P.IsPrime}`, the greatest lower bound of the prime ideals $P$ of $R$ among its
  ideals, which is their intersection.

This is Proposition 1.8 of Atiyah and Macdonald, for the same rings: commutative, with a $1$.

## References and tests
- Atiyah and Macdonald, *Introduction to Commutative Algebra*, Proposition 1.8: the statement itself.
- `TauCeti.Foo.nilradical_zmod_four` — in $\mathbb{Z}/4\mathbb{Z}$ both sides are the ideal $(2)$.

The test works out both sides in a ring where the answer is known by hand, so `nilradical` and `sInf`
mean here what they mean in the book.

## Lean subtleties
- `[CommRing R]` is a hypothesis carried as a typeclass: Lean finds the ring structure by itself.
- The `sInf` of no ideals is the whole ring. The zero ring has no prime ideals, so there the right side
  is the whole ring; so is the left, since $1 = 0$ is nilpotent there.
~~~

It differs from the guide's example in two ways. It lists no Check, since `checks` is empty. And its reference, and the
book its comparison with the literature names, are the docstring's, word for word and with its number: in the
migration, every citation of a review comes from the bundle. Its test is the one `tests` gives, and the group that only
introduces a type, `(R : Type u_1)`, has no bullet of its own.

## 5. Each cell is `checked`, `na` or `error`

Your result gives each of the eight checks of 1 a cell, once:

- `checked`: you made the check and found nothing wrong;
- `na`: it does not apply, since it cannot fail for this declaration, such as `choice` where nothing is chosen;
- `error`: it found an error. A result with a cell `error` is a hold.

## 6. Your result: one line per bundle

For each bundle, add its result to your result file with this command, the review between the two `END_OF_REVIEW`
lines exactly as you wrote it, with nothing escaped:

```sh
{{WRITE}} add RESULT_FILE --decl "DECL" --verdict approve \
  --cells object,convention,edge-cases,junk,vacuous,choice=na,generality,naming <<'END_OF_REVIEW'
## What it says
…

## References and tests
…

## Lean subtleties
…
END_OF_REVIEW
```

In `--cells`, a check alone is `checked`, `check=na` does not apply, and `check=error` found an error. A hold is
`--verdict hold --hold 'the reason'`, the reason in single quotes, each `'` in it written `'\''`.

The command writes the line the program reads, `{"decl", "cells", "verdict", "hold", "review"}`, in place of any line
of that declaration the file had. It refuses a result that breaks the rules of 2 and 5, saying why, and writes nothing.
Then it checks the review as the program will, and prints any problem it finds: fix the review, and add it again; the
new line replaces the old one. If a problem remains after two more tries, leave it and go on. It also names the next
bundle without a line, by its line in the batch.

Your result file holds one line per bundle of your batch, and nothing else. Write nothing else: no other file, and no
change to the batch. When every bundle has its line, reply in one line: how many you approved, and how many you held.

### On a retry

A bundle that has `retry` was written before, and the program found problems in its result: `retry.problems` lists
them, and `retry.previous` is the review it was given (empty when there was none it could read). Review the Lean again,
as in 1: the cells and the verdict are yours. Then write the review again, fixing every problem listed and keeping what
was right in `previous`.
