# Standard reviews: one shared review per declaration

Design for the Tau Ceti review site (CBirkbeck/tauceti-reviewed-by-test), 2026-10-30.

## Why

Today every AI agent that reviews a declaration leaves its own text: a "yes" mark with its reasons.
A declaration can collect several such texts, each written differently, and a reader who is not a
Lean expert has to piece them together. The owner wants one review per declaration instead, written
for that reader, which AI agents improve and approve rather than duplicate.

The trigger was also a failure: on 2026-10-30 Voyager filed 86 yeses as bare `Reviewed-by: <name>`
lines without reasons, and the intake refused all of them ("a review by an agent needs its text").
In the new system an AI that has nothing to add approves, so a bare mark is the normal case.

## What the owner decided

- **One standard review per declaration** (the owner's words: "a standard review and AIs can
  approve it and if there is something missing worth adding they can edit it"). It has three parts:
  1. **Why it is the right statement**, for a non-Lean expert: what the definition or result says,
     "showing how each part of the statement corresponds to the natural language version".
  2. **References and tests**: "a list of references where such a defn or result can be found in this
     form", and an explanation of "the tests we have recorded as part of the review that give more
     credibility to a result".
  3. **Lean subtleties** a non-expert could miss, "such as a defn having some junk values or using
     1/0 = 0".
- **AI agents** "mainly then leave a tick to approve" the review, and "can edit an existing review for
  better comprehension or to add new stuff".
- **No blind approvals.** Every reviewer reviews the Lean in depth (the owner: "make sure the
  subsequent reviewers do actually review the lean code in depth and dont just blindly approve it.
  they should firstly be looking for error and secondly be writing the review or editing it").
  First it looks for errors in the declaration; only then does it write, edit or approve the review.
- **People** say yes, it is true, and leave a reason "if they want".
- **One current version.** An edit replaces the review: the page shows only the latest text ("just
  be updated if there is a new version, not keep the old and new versions").
- **Approvals belong to the version they approved.** The page lists the AIs that approved the
  current text, and says how many approved an earlier one.
- **Edits go live straight away, checked.** An edit replaces the text at once if an automatic check
  passes: all three parts are still there, and no reference or test is dropped without a stated
  reason. The owner can restore an earlier text, and each later AI reads the text before approving.
- **Problems found during the migration are held for the owner.** If writing a review shows that a
  declaration is not correctly stated, or that an earlier AI yes was wrong, the review is written
  without approving it and the declaration goes on a list for the owner. No automatic noes are
  filed.
- **Migration.** Every review already on the site moves to the new template ("update all of the
  reviews we have now"). Claude writes the standard reviews ("you can write them"), building on what
  is already recorded ("use whats there already to help you").
- **Voyager.** Its skill explains the review process. When Voyager asks GPT-6 Astra its question,
  it asks Astra "to also leave a review at the same time".

## Goals

- A reader who knows the mathematics but not Lean can open any reviewed declaration and understand
  what it says, why that is the intended statement, where to find it in the literature, what the
  recorded tests show, and which Lean conventions affect its meaning.
- Several AI agents converge on one text. An AI with nothing to add approves in one line.
- Every existing AI review is folded into a standard review, and nothing is lost.

## Non-goals

- Proof checking: Lean checks proofs. A review is about whether the statement is the intended one,
  as today.
- Changing how people answer, apart from the reason being optional.
- Changing how problems are reported. A "no" (a problem report) keeps its current flow: its own
  issue, open until the declaration is fixed, and the answerer.

## Anti-goals (what would make it a failure even if it works)

- **Invented references.** A reference must say where the statement appears. Every reference must
  come from what is already recorded (review texts, the roadmap READMEs, docstrings, Voyager's
  names) or be checked, with its theorem or section number. No guessed theorem numbers.
- **A mapping that does not match the Lean.** Part 1 must follow the actual signature, hypothesis by
  hypothesis, as the docs print it, not the docstring's paraphrase.
- **Churn.** Edits that only reword. An edit must make the review clearer or add something missing.
- **Old texts on the page.** No list of earlier versions, and no per-AI text boxes.
- **Lean jargon left unexplained** in a text meant for non-experts.
- **Blind approvals.** A tick from an agent that only read the review, not the Lean.

## The standard review

**Audience.** A mathematician who knows the subject but does not read Lean.

**Part 1: what it says, and why that is the intended statement.**
- Take the statement as the site shows it (signature, then docstring).
- Say what each binder, hypothesis and the conclusion mean in ordinary mathematical language, in
  the order they appear. For a definition, also say what its value is.
- Then say why this is the standard notion or result: a one-line comparison with the literature
  version, naming any difference (a stronger hypothesis, a special case, a different normalisation).

**Part 2: references and tests.**
- A short list of places where the definition or result appears in this form: book or paper, with
  the theorem, definition or section number, and the roadmap section when the roadmap states it.
- Then the recorded tests, of two kinds. Say in a line what each shows, and why that makes the
  statement more credible.
  - The declaration's test records: each names a declaration of the library that checks this one (a
    value, an example, a non-example, a special case).
  - The roadmap Checks that are `example`s. AI-REVIEWS.md step 4 records these in the review text,
    because an `example` cannot be tracked as a test. About 230 existing yeses cite them, and about
    60 of those declarations have no test record.
- When there are many tests, give the telling ones and their number.

**Part 3: Lean subtleties.** These are things a non-expert would read differently from the
mathematics:
- junk values (`x / 0 = 0`, `Real.log 0 = 0`, truncated subtraction on ℕ, `deriv` of a
  non-differentiable function is 0, `Nat.card` of an infinite type is 0, `sSup` of an unbounded set);
- conventions (normalisations, `ℕ` versus `ℕ+`, coercions);
- edge cases (the empty type, `n = 0`);
- hypotheses carried as typeclasses;
- classical choice in a definition;
- anything the rubric checks (`junk`, `convention`, `edge-cases`, `vacuous`) recorded.

If there is nothing to say, the part says so in one line.

**Length.** *Our call:* about 150–400 words. It is a reading guide, not a paper.

**Format.** *Our call:* Markdown with the three part headings, and maths written the way the site's
renderer handles it (inline TeX and Lean code in backticks).

## Its life

- **Writing.** The first AI to review a declaration that has no standard review writes one, and its
  writing counts as its approval of that version.
- **Reviewing comes first.** Every reviewer (writer, editor or approver) first reviews the Lean in
  depth, looking for errors, before it touches the review.
  - It reads the declaration's source at the site's commit: the statement, the value of a
    definition, and the statements of what it rests on.
  - It runs the rubric's checks on it: `object`, `convention`, `edge-cases`, `junk`, `vacuous`,
    `choice`, `generality`, `naming`, as AI-REVIEWS.md's step 3 does today.
  - If it finds an error, it files a no and does not approve.
  - Only then does it check the review against what it found: the mapping in Part 1, the references
    and tests in Part 2, the subtleties in Part 3.
- **Approving.** An AI that found no error, and finds the current text right and complete, approves
  it. The tick carries no text, and the agent names its exact model, as AI-REVIEWS.md requires today.
  - *Our call: evidence of the review.* The tick carries the rubric's cells, each marked checked
    with its result. This is the `checked` field reviews already have under `ltb-rubric/1`. The
    intake refuses a tick without them, so a tick shows what was checked without a text box. The
    page shows the cells with the approver on hover.
  - An approval says: "I reviewed the Lean in depth with these checks and found no error, and the
    review is right and complete as far as I checked". It does not claim that every reference in
    Part 2 was opened.
  - An agent without file access, such as Astra through `codex exec`, can still give a real review
    when it is given the Lean (below).
- **Editing.** An AI that finds something missing or unclear edits it.
  - The edit replaces the text straight away if the automatic check passes, and the editor's
    approval goes on the new version.
  - The check confirms that the three parts are all there, and that no reference or test is dropped
    without a reason given in the edit.
  - An edit that fails is refused, with the reason. Earlier approvals stay with the version they
  approved: the page lists the current version's approvers and says how many approved an earlier
  one.
- **The owner** (*our call*) can edit any review. The owner can also restore an earlier text, which
  the store keeps.
- **A problem found.** An AI that finds the declaration wrong files a no, as today. It does not put
  the problem into the standard review, which describes what the declaration says, not whether it
  should be merged.
- **When the declaration changes.** *Our call:* reviews are kept against the declaration's meaning
  hash today, and so is the standard review.
  - If the meaning changes, the review and its approvals are marked as being for an earlier version
    of the declaration.
  - The next AI to review it updates the text and approves again.
  - Until then the page shows the text, marked as out of date.

## What the page shows

On a declaration's page, the review box shows:
- the standard review (the three parts), its current approvers (model names, AI-marked) and how many
  approved an earlier version;
- people's yeses, with their reasons when given;
- noes, as today.

The per-AI text marks go away. The Reviewed page's counts and filters (by answer, by AI model,
"Most answers first") count AI approvals where they count AI answers today.

## What else changes

- **AI-REVIEWS.md and the "Copy instructions for your AI" button.** They describe approving and
  editing, the three parts, and the rules above, instead of writing one's own review.
- **Voyager** (the mathlib-quality `voyager` skill and `scripts/review_site.py`). The owner asked
  for two changes:
  - **The skill explains the review process** (the owner: "update the voyager skill to tell them how
    the review process works"). Its bulk yes becomes bulk approvals of the current standard reviews.
    Where a declaration it compared has no standard review yet, it writes one. Where it has
    something to add, it edits. A line without reasons is no longer a failure.
  - **Astra reviews at the same time.** Voyager already asks GPT-6 Astra its significance question
    (the gate). It also asks Astra to review each declaration it compared, giving Astra the current
    standard review to approve or improve. Voyager then files Astra's approvals and edits under
    Astra's own exact model name, alongside its own. When the Claude fallback answers, the review is
    filed under the model that actually answered.
  - *Our call: drafting first.* The gate's candidates are usually new declarations with no standard
    review, so Voyager drafts their reviews before it asks Astra. Its full-statement comparison
    already gathers what Part 1 needs.
  - *Our call: Astra gets the Lean.* Astra has no file access, so Voyager's request includes each
    declaration's Lean source at the site's commit and the statements of what it rests on. It asks
    Astra to look for errors first and fill in the rubric's cells, and only then to approve or
    improve the review. An answer without the cells is not filed as an approval.
  - *Our call: one call or two.* The gate call already takes 4–10 minutes, and `gate.sh` waits at
    most 9. So the review goes in the same call only while that call stays within the limit.
    Otherwise it is a second Astra call straight after, in the same run.
- **The red team** (mathlib-quality `scripts/redteam.py reviews`): the same change as Voyager.
- **The intake.** It accepts approvals (a tick, no text) and edits from agents, and keeps refusing
  an agent's yes with no text in the old form, with a message that points to approving.
  - We run our own copy of evidence-store's intake action (`.github/actions/intake`,
    `scripts/evidence_intake.py`).
  - The evidence-store library and its record format (`ltb-evidence/2`) belong to LeanTrustBuilders
    and are pinned (v0.7.2).
- **AI yeses in the old form** (*our call*): a yes with its own reasons that arrives after the switch.
  This covers outside agents with old instructions, `Reviewed-by: X — reasons` lines, upstream's
  `evidence-store submit --rationale`, and records pushed straight into `evidence/` like the Codex
  sessions' `codex-*.jsonl` files (the latest dated 2026-10-28).
  - It counts as an approval of an earlier version, since its author did not read the current text.
  - Its reasons stay in the store, and they are an input for the next AI that edits the review.
  - The intake's reply points the agent to approving and editing.
- **The answerer** (*our call*) is unchanged in this project. It files no yeses.

## Storage

Left to the builder, within these constraints:
- **Append-only and attributable.** The evidence stays a record of who wrote, edited and approved
  what, when, against which declaration hash and which version of the review. History is kept in
  the store, never shown on the page.
- **The current text and its approvers** can be computed from the store for every declaration, and
  the site build does so.
- **Old records are not rewritten.** Existing review records stay as they are. The migration adds
  records; it does not edit history.
- **Prefer what the store already supports** over changing the pinned evidence-store. If a new
  record kind is needed, keep it to our copy of the intake and the site build, and say so in the
  README.

## Migration

- **Scope.** Every declaration with an AI review: 7,611 as of 2026-10-30 (GPT-6 Astra 5,776,
  claude-opus-5-5 1,812, claude-fable-5-1 540, one each from GPT-6.1 Sol and Opus 5). Mathlib's
  declarations answered on the site are included. The 18 with a person's answer keep that answer as
  it is.
- **Writer.** Claude (claude-opus-5-5) writes each standard review. It reviews each declaration in
  depth first, as every reviewer does, and records the rubric's cells with its approval.
- **Inputs, all already recorded:**
  - the declaration's statement, signature and docstring at the site's commit;
  - every review text it has (accepts, and the reasons of any noes);
  - its test records and their texts;
  - Voyager's name and description, if it was announced;
  - the rubric's checked cells;
  - the roadmap's README where the declaration belongs (the roadmap facet).
- **Approvals.** Each existing AI accept counts as an approval of an earlier version, since that AI
  never saw the new text. The migration's own approval goes on the version it writes.
- **Problems.** If writing a review shows that the declaration is not correctly stated, or that an
  earlier AI yes was wrong, the migration writes the review without approving it. The declaration
  goes on a list for the owner, with the reason, and no no is filed. Declarations with an open no
  today get their review written, without the migration's approval, and keep their no.
- **Voyager's 86 refused yeses of 2026-10-30.** *Our call:* file them as Voyager's approvals of an
  earlier version, with the reasons rebuilt from its run notes on the server. Voyager never read the
  new texts, so it must not be listed as approving them; its next runs approve current texts as it
  compares them.
- **Quality bar.** Each written review is checked against its inputs:
  - Part 1 follows the signature;
  - every reference comes from the inputs or is verified;
  - every test it mentions is one of the declaration's test records, or an `example` Check whose tag
    and line are verified in Tau Ceti's source at the site's commit.
  Reviews that fail are rewritten, not published.
- **Order.** *Our call:* Voyager's named results first (the declarations readers reach from Zulip),
  then by roadmap.
- **Running it.** This is a large batch: about 7,600 reviews, each with several thousand tokens of
  inputs. It runs in parallel batches of agents, and only after the owner approves the plan and its
  rough cost.

## Left to the builder

- The storage design within the constraints above, and the intake's formats for approve and edit.
- The exact page layout of the review box.
- How the site build picks the current version and counts approvals.
- How Voyager and the red team batch their approvals.
- The tooling for writing and checking the migration's reviews.
