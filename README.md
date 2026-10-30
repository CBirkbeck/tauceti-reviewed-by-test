# Tau Ceti Review

**Site:** https://cbirkbeck.github.io/tauceti-reviewed-by-test/

Every declaration of [Tau Ceti](https://github.com/TauCetiProject/TauCeti), reviewed by people and by
AI agents, from the browser and without pull requests: what each declaration is, what it rests on and
what rests on it, who has checked it and on which version, the problems reported, the tests it passes
and the tests people would like. It leads with the named results and notable definitions Voyager has
announced on the Lean Zulip, the declarations people are likely to care about.

Nothing here changes Tau Ceti. Every record is kept in this repository's evidence store, pinned to the
declaration's meaning hash: when the declaration, or anything it rests on, changes, the record stays
and says so.

It is built with the [LeanTrustBuilders](https://github.com/LeanTrustBuilders) tools: Tau Ceti's
dataset (spec S2) from the extractor, records (spec S3) in an evidence store filled by evidence-store's
forms, and evidence-core for everything computed from them. The design:
[docs/superpowers/specs/2026-10-23-tauceti-review-site-design.md](docs/superpowers/specs/2026-10-23-tauceti-review-site-design.md).

## Reviewing

A review answers one question: **is this declaration correctly stated?** Open a declaration on the site:
its review box asks the question, with two buttons. **Yes** opens a short form in the box, a reason
optional, and **No** one that asks why; **Send on GitHub** opens a new issue there with the declaration,
the commit the site shows and what you wrote already in it, for one click there to file it (what you
wrote goes on your clipboard too). For whoever reviews several declarations, each form offers to sign in
with GitHub (below) once: signed in, **Yes** files your answer at once, with Undo, and Add why to give a
reason, and Send files a no from the page. Either way the issue is written as the form writes it:

| answer | form | records |
|---|---|---|
| **Yes** | `evidence-review.yml`: nothing more to fill in; why is optional | an acceptance: it says what it should, the intended notion or the intended result |
| **No** | `evidence-problem.yml`: why, required | a problem, open until it is marked fixed, intended or invalid |

Below the question, **What could be better** takes suggestions for a declaration that is correct but
could be done better: more general, a better name or docstring, a cleaner statement. **Suggest an
improvement** opens `evidence-question.yml`, recast for it (the suggestion required; GitHub labels
the field "Question", the label intake reads it by). A suggestion is recorded as a question, open
until it is dealt with, and counts as neither a yes nor a no.

Under **Tests**, **Suggest a test** opens `evidence-challenge.yml`, cut to a property the declaration
should have (required), as a Lean statement and what it would catch (both optional). It is recorded
as a challenge, open until a declaration of Tau Ceti proves it; the page then lists that declaration
as a test and checks at every commit that it still passes.

The forms are for people: they do not ask who you are or who wrote them, and intake records the
account that opened the issue as a person. AI agents answer from the command line instead (below).
The store's other forms (listing a test, names, statuses) are still there for intake, but the site
does not offer them.

Intake turns the issue into a record under the account that opened it, answers on the issue, and
rebuilds the site within minutes. Intake reads an issue's form by its label, and some answers come
without one: one filed from the page by someone who is not a collaborator (GitHub drops it), and every
one sent on GitHub, which opens as a plain new issue. The Label answers workflow gives each its label,
from the title and the fields, and has intake read it (`scripts/label_issue.py`; it does the same for an
AI agent's `evidence-store submit`). On an answer's issue, a comment whose first line is a command
changes where it stands: `/withdraw`; on a no, `/fixed [commit]`, `/intended`, `/invalid`, `/reopen`.

**Many yeses at once:** comment lines on [issue #1](../../issues/1), one record each (it also takes
tests, challenges and names):

```
Reviewed-by: TauCeti.Foo.bar — why it is correctly stated
Test: TauCeti.Foo.bar — TauCeti.Foo.bar_zero — what it checks
```

**AI agents** name themselves in their comment, tool and exact model, and the site shows their records
apart from people's: `<!-- agent: tool=Codex; model=GPT-6 Astra; session=… -->`. An AI agent reviewing one
declaration can follow [AI-REVIEWS.md](AI-REVIEWS.md) instead: it reads the declaration against its
source, runs the Checks its roadmap gives it, and files its answer, yes or no, with
`evidence-store submit`, its reasons listing each Check. Each declaration's review box has **Copy instructions for your AI**, which
copies the request below, filled in with the declaration and the commit the site shows. To ask for one
by hand:

```
Review TauCeti.Foo.bar for the Tau Ceti review site, following
https://github.com/CBirkbeck/tauceti-reviewed-by-test/blob/main/AI-REVIEWS.md
Give your exact model, as AI-REVIEWS.md says: GPT-6 Astra, not GPT-6.
```

Two agents review as part of their own work: **Voyager**, every result whose statement it compares
with a source before a post, and **the red team**, which says yes to each declaration of a file it
audits that passes its checks and fixes the rest in Tau Ceti instead of answering no
([AI-REVIEWS.md](AI-REVIEWS.md#voyager-and-the-red-team)). Any answer counts, a person's or an
agent's, but its reasons add only what the answers already there lack.

## Signing in with GitHub

So that an answer is filed from the page, the site signs its readers in with GitHub (`web/signin.js`):

- **The GitHub App** "Tau Ceti Review", public so that anyone can sign in with it, asks for one
  permission, issues (read and write), and is installed on this repository alone, with no webhook and
  expiring tokens. A reader's token can file issues and comments here under their own account, the
  issue marked as made through the app, and nothing else; it lasts eight hours. The app has no private
  key: it never acts as itself.
- **The sign-in helper** (`signin/worker.js`, on Cloudflare Workers): GitHub hands the page a one-time
  code, and swapping it for a token takes the app's client secret, which no page can hold (and
  GitHub's token endpoint does not answer browsers). The page posts the code to the helper; the helper
  posts it on with the secret and returns the token, keeping nothing. PKCE makes a code worth nothing
  to anyone but the tab that asked for it. From `signin/`: `npx wrangler deploy`, and
  `npx wrangler secret put CLIENT_SECRET` for the secret; `node --test worker.test.mjs` tests it.
- **The settings:** `data/settings.json`'s `signin`, `{"client_id": …, "exchange": "https://…workers.dev/token"}`,
  neither of them secret. Without it the site has no sign-in, and every form opens on GitHub.

The token is kept in the reader's browser (`localStorage`) until it ends or they sign out, and on no
server.

## The answerer

Every hour, on the server, the review answerer (`answerer/`) takes the open noes and the open
suggestions and questions, at most six a run, and has Claude Fable 5.1, through the API, check each
against the library's source and Lean. Mathlib's style of stating definitions more generally than
the classical notion counts as intended: a definition is right when it agrees with the classical one
under the hypotheses its results assume. Then:

- a question is answered, and closed as answered;
- a no that is not an error is closed as intended, or as not a problem;
- a no that is right about a docstring gets a pull request to Tau Ceti changing only that docstring,
  and is closed as fixed, at the merge commit, once it merges;
- a no that is right about the Lean, or anything it cannot settle, stays open, listed in the issue
  "Answerer: needs a person".

Its reply is recorded with the item, so the site shows under each no why it was closed, and the
Activity page lists the noes answered. It answers only mathematics, and what an item says cannot make
it do anything else: its tools only read the library and Mathlib and run small Lean checks sealed off
(`bubblewrap`: no network, no home directory), the code (not the model) decides what to post, and
what it posts is cleaned of marks, links elsewhere, mentions and commands. It spends at most $20 a
day. The design: `docs/superpowers/specs/2026-10-25-review-answerer-design.md`. On the server:
`systemctl --user status tauceti-answerer.timer`, its log with `journalctl --user -u tauceti-answerer`,
and `python -m answerer run --dry-run` to see what it would do.

## What the site shows

- **Named**: Voyager's announcements, each with its review state and how much of what it rests on in
  Tau Ceti has been reviewed. Voyager is the only source of names. A review state counts people's
  reviews; one reviewed by AI agents alone says so ("AI only"). Since 2026-10-29 there is no switch to
  count AI agents' reviews as people's.
- **Reviewed**: every declaration answered for, the latest answer first, with its yeses and noes
  counted (people apart from AI agents), Mathlib's marked; filters for yes or no, for people, AI agents
  or one AI model, and for the roadmap a declaration of Tau Ceti belongs to (below; asked for on
  2026-10-29); and an order with most answers standing first (this version's yeses and the noes still
  open, of those counted), which since 2026-10-30 replaces the filter by how many.
- **A declaration**: its docstring and Lean source (hover over a name for its card: what it is, its signature
  with its names linked, a definition's value; a name in a card opens its own card, and so on; a
  variable shows its type and lights up its uses), links to the API docs, the source and Voyager's
  post; its **dependency map** (what it rests on above, what rests on it below; the results its proof
  uses and Mathlib's declarations on request; ↑ and ↓ unfold a level, − folds it), then as lists how
  it is proved, what is built on it, its examples and what it is used to prove; and its review box, as the site had it in September, asking "Is this theorem
  (lemma, definition, …) correctly stated?" with Yes and No (each opens a short form in the box whose Send
  opens it on GitHub filled in; signed in, which the forms offer to whoever reviews several, Yes files at
  once and Send files from the page): below, a Correctly stated mark counting
  people apart from AI agents, a Not correctly stated mark for the noes still open, then each answer's
  mark, a twisty when it gives reasons that opens to why and its issue, and
  each no in full until it is answered, then folded into a twisty (where it stands, who said it, its
  first line) that opens to the no, the replies and what was decided; **What could be better**, its suggestions and the button to add one; and **Tests**,
  the button to suggest one and, when something tests it, a Tested by mark and each test as a twisty
  that opens to what it checks and its statement as the docs show it. Formulas in docstrings and in Voyager's
  sentences are typeset, whether written in TeX (`$…$`) or as text with TeX's marks
  (`Θ_L(τ) = ∑_{v ∈ L} exp (π i ‖v‖² τ)`).
- **A Mathlib declaration** (one of the packages outside Tau Ceti that `review_outside` in the settings
  names): a link to Mathlib's docs, and the same review box, asking the same question of the Mathlib
  Tau Ceti builds on. Reach one from a Tau Ceti declaration
  that uses it, or by its Lean name in Search.
- **Browse**, **Search** (names and docstring titles), **Activity** (the noes and the suggestions
  still open, the noes resolved, what to review next, reviewers; an answered no folded as on its page;
  the home page's count of noes still open leads to them, `#/activity/open`) and **How to review**.

Colour on a declaration means its review state: an open ring for not reviewed, white for reviewed,
salmon for reviewed by AI agents only or on an earlier version, red for a no still open. A switch on
the Named page says whether AI agents' reviews count.

## How it is built

| workflow | when | what |
|---|---|---|
| [Follow Tau Ceti](.github/workflows/follow.yml) | every 20 minutes, going on only when new docs have gone live (a few times a day); and by Voyager, when the site is behind at the time of a post | pins the commit Tau Ceti's published API docs show, its `docgen` branch, where Voyager's window also ends, or the newest before it that the extractor's 0.13 series can read and its cache has built (`scripts/pin.py`), so that the site has every declaration Voyager can announce and link to it, and shows what the docs show; when that moves, extracts its dataset as the release `dataset-<commit12>` ([Dataset](.github/workflows/dataset.yml)); records Voyager's announcements; deletes datasets nobody needs (`scripts/prune.py`); rebuilds the site |
| [Voyager](.github/workflows/voyager.yml) | 04:15 and 16:15 UTC | reads Voyager's topic on the Lean Zulip (secrets `ZULIP_SITE`, `ZULIP_EMAIL`, `ZULIP_API_KEY`; read only) into `data/voyager.jsonl`, and records a `named` record for each announcement whose declaration the pinned dataset has (`scripts/voyager.py`) |
| [Evidence intake](.github/workflows/evidence-intake.yml), [Evidence check](.github/workflows/evidence-check.yml) | on every issue event; on every change to `evidence/` | evidence-store's: records from forms, comments and the bulk issue; the check that the store only grows, and that a push adds only its author's records |
| [Label answers](.github/workflows/label.yml) | on every new issue | gives an answer that came without its form's label (filed from the page, or by `evidence-store submit`, under an account that cannot label) that label, from its title and fields, then runs intake on it (`scripts/label_issue.py`) |
| [Pages](.github/workflows/pages.yml) | after any of these | runs the tests, builds the site (`scripts/build_site.py`), checks it in a browser, and publishes it from `main` |
| [Tests](.github/workflows/tests.yml) | on every change to a workflow or a test | runs the unit tests, which Pages runs only when the site or the store changes; among them, that every call of a workflow grants the permissions the called workflow asks for, without which GitHub refuses to start the run |

The tools are pinned: evidence-core `v0.16.1`, evidence-store `v0.7.2` (`requirements.txt`), the
extractor's 0.13 series (`data/settings.json`; from the fork `CBirkbeck/extractor`, whose 0.13.2 prints
binders with their types and 0.13.3 a structure's parents, until LeanTrustBuilders/extractor has them).
The store imports no other store.

**A page shows each statement as the docs do, and that is checked.** On 2026-10-25 the site showed
existentials without their binders' types (`∃ V, … ∃ f, …` for
`AlgebraicGeometry.Scheme.exists_isClosedImmersion_proj`, whose `f : X ⟶ Proj (SymmetricAlgebra …)`
the docs show): the extractor printed signatures with Lean's default `pp.funBinderTypes`, false, and
nothing compared them with the docs. Now:
- since 2026-10-26 the statement is the docs' own: the Dataset workflow reads every module's docs page
  (`scripts/docs_signatures.py`, about five minutes) into the facet `docs-signature`, each header with
  its names linked and its lines broken where the docs' printer broke them. A docs page is printed with
  its module's imports alone and the dataset with the whole library loaded, so Lean's own printing of a
  statement can differ in notation (`∃ (a : A), ∃ (b : B)` against `∃ (a : A) (b : B)`, `∀ (z : α),
  z ∈ s → …` against `∀ z ∈ s, …`). Lean's printing is kept only where the docs have no header (fields,
  constructors, declarations the compiler makes) or the page is older than a change to its module.
  Outside the library (Mathlib, Lean, Batteries, Aesop) the statement comes from Mathlib's docs
  (`library.upstream_docs`), which show Mathlib's latest version, so a header is taken only where it says
  what Lean prints at the version the library pins (the same text and constants); elsewhere Lean's
  printing at the pin stands (asked for on 2026-10-26, when `zero_smul` showed no statement at all);
- the Dataset workflow publishes a dataset only if `scripts/check_signatures.py` passes: no signature
  prints a binder without its type, and the signatures of every declaration Voyager named, every one
  with a record, and two samples of the rest (800) say what the docs' headers say, namespaces, universes
  and spacing set aside, and two notations a docs page writes out (`fun₀ | i => a`, `X ⟹ Y`: a docs page
  is built from its module's imports alone); otherwise it opens an issue and the site stays on the last
  dataset that passed. What is compared is what the site shows, so a statement taken from the docs is
  compared with its own page, and a misreading of it is caught. A difference reviewed and accepted goes in
  `data/signature-exceptions.json`;
- the browser check of every build reads, on real pages, that what is shown is the dataset's signature;
- the extractor's own test checks that binders keep their types and a structure says what it extends.

**Each declaration's roadmap** is the facet `roadmap`, which the Dataset workflow adds
(`scripts/roadmaps.py`, a few minutes) from Tau Ceti's PR labels, `roadmap/<Area>`, which are complete:
each line of a declaration is credited to the PR that last changed it (`git blame --first-parent` at the
dataset's commit; every commit of Tau Ceti's main names its PR), and the declaration belongs to the
roadmap credited with most of its lines, on a tie the one that changed a line last. `roadmap/none`
(infrastructure, dependencies, cross-cutting work), `roadmap/Unknown` (an attribution missing or
invalid) and a commit that names no PR credit nothing. At 36f24f5d, 98% of the reviewed declarations of
Tau Ceti had a roadmap; Mathlib's have none. When the labels cannot be read the dataset is published
without the facet, and the Reviewed page has no roadmap filter until the next one.

## Files

- `evidence/`: the store (`store.json`, `records/*.jsonl`).
- `data/settings.json`: the pin, the library, the packages outside it the site also asks about
  (`review_outside`: Mathlib), the extractor series, dataset retention, Voyager's topic, signing in
  (`signin`).
- `data/voyager.jsonl`: every announcement Voyager has made.
- `scripts/`: `pin.py`, `extractor.py`, `prune.py`, `voyager.py`, `label_issue.py`; `site_data.py`
  (everything a page shows, from evidence-core) and `build_site.py` (writes `_site/`).
- `web/`: the front end (`index.html`, `style.css`, `data.js`, `render.js`, `map.js`, `signin.js`,
  `app.js`) and `vendor/` (elkjs, KaTeX, the Atlas's `markdown.js`; see `web/vendor/NOTICE`).
- `signin/`: the sign-in helper (`worker.js`, `wrangler.toml`) and its tests.
- `answerer/`: the review answerer (above), its prompt (`prompt.md`) and its systemd units.
- `tests/`: unit tests, the suite's fixture (`tests/fixtures`, see its NOTICE), `fixture_site.py`, and
  the browser check `validate_site.py`.

## Working on it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-test.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python -m unittest discover -s tests       # unit tests
.venv/bin/python tests/validate_site.py              # the browser check, on the fixture's site
.venv/bin/python scripts/build_site.py --dataset DIR --source TAUCETI_CHECKOUT --imports DIR --out _site
.venv/bin/python tests/validate_site.py --site _site --smoke
```

`evidence-store dataset --store evidence --commit <pin> --out DIR` fetches the pinned dataset, and
`evidence-store fetch-imports --store evidence --out DIR` the imported stores.

## History

Until October 2026 this repository was a test of Reviewed-by marks, with its own scripts, ledgers in
`reviews/`, and lines written into a fork of Tau Ceti by pull request. Its four reviews and eleven
tests were migrated to the store (`evidence-core migrate reviewed-by`); the rest is in the history.
