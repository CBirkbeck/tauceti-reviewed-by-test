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
its review box asks the question, with two buttons, each opening a short form on GitHub filled in with
the declaration and the commit the site shows:

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
rebuilds the site within minutes. On an answer's issue, a comment whose first line is a command
changes where it stands: `/withdraw`; on a no, `/fixed [commit]`, `/intended`, `/invalid`, `/reopen`.

**Many yeses at once:** comment lines on [issue #1](../../issues/1), one record each (it also takes
tests, challenges and names):

```
Reviewed-by: TauCeti.Foo.bar — why it is correctly stated
Test: TauCeti.Foo.bar — TauCeti.Foo.bar_zero — what it checks
```

**AI agents** name themselves in their comment, and the site shows their records apart from people's:
`<!-- agent: tool=Claude Code; model=claude-opus-5-5; session=… -->`. An AI agent reviewing one
declaration can follow [AI-REVIEWS.md](AI-REVIEWS.md) instead: it reads the declaration against its
source, runs the Checks its roadmap gives it, and files its answer, yes or no, with
`evidence-store submit`, its reasons listing each Check. Each declaration's review box has **Copy instructions for your AI**, which
copies the request below, filled in with the declaration and the commit the site shows. To ask for one
by hand:

```
Review TauCeti.Foo.bar for the Tau Ceti review site, following
https://github.com/CBirkbeck/tauceti-reviewed-by-test/blob/main/AI-REVIEWS.md
```

## What the site shows

- **Named**: Voyager's announcements, each with its review state and how much of what it rests on in
  Tau Ceti has been reviewed. Voyager is the only source of names.
- **Reviewed**: every declaration answered for, the latest answer first, with its yeses and noes
  counted (people apart from AI agents); filters for yes or no, and for people or AI agents.
- **A declaration**: its docstring and Lean source, links to the API docs, the source and Voyager's
  post; its **dependency map** (what it rests on above, what rests on it below; the results its proof
  uses and Mathlib's declarations on request; ↑ and ↓ unfold a level, − folds it), with the same
  neighbours as lists; and its review box, as the site had it in September, asking "Is this theorem
  (lemma, definition, …) correctly stated?" with Yes and No: below, a Correctly stated mark counting
  people apart from AI agents, a Not correctly stated mark for the noes still open, then each answer's
  mark, a twisty when it gives reasons (an AI agent's always do) that opens to why and its issue, and
  each no in full; **What could be better**, its suggestions and the button to add one; and **Tests**,
  the button to suggest one and, when something tests it, a Tested by mark and each test as a twisty
  that opens to what it checks and its statement as the docs show it. Formulas in docstrings and in Voyager's
  sentences are typeset, whether written in TeX (`$…$`) or as text with TeX's marks
  (`Θ_L(τ) = ∑_{v ∈ L} exp (π i ‖v‖² τ)`).
- **Browse**, **Search** (names and docstring titles), **Activity** (the noes and the suggestions
  still open, what to review next, reviewers) and **How to review**.

Colour on a declaration means its review state: an open ring for not reviewed, white for reviewed,
salmon for reviewed by AI agents only or on an earlier version, red for a no still open. A switch on
the Named page says whether AI agents' reviews count.

## How it is built

| workflow | when | what |
|---|---|---|
| [Follow Tau Ceti](.github/workflows/follow.yml) | every 20 minutes, going on only when new docs have gone live (a few times a day); and by Voyager, when the site is behind at the time of a post | pins the commit Tau Ceti's published API docs show, its `docgen` branch, where Voyager's window also ends, or the newest before it that the extractor's 0.13 series can read and its cache has built (`scripts/pin.py`), so that the site has every declaration Voyager can announce and link to it, and shows what the docs show; when that moves, extracts its dataset as the release `dataset-<commit12>` ([Dataset](.github/workflows/dataset.yml)); records Voyager's announcements; deletes datasets nobody needs (`scripts/prune.py`); rebuilds the site |
| [Voyager](.github/workflows/voyager.yml) | 04:15 and 16:15 UTC | reads Voyager's topic on the Lean Zulip (secrets `ZULIP_SITE`, `ZULIP_EMAIL`, `ZULIP_API_KEY`; read only) into `data/voyager.jsonl`, and records a `named` record for each announcement whose declaration the pinned dataset has (`scripts/voyager.py`) |
| [Evidence intake](.github/workflows/evidence-intake.yml), [Evidence check](.github/workflows/evidence-check.yml) | on every issue event; on every change to `evidence/` | evidence-store's: records from forms, comments and the bulk issue; the check that the store only grows, and that a push adds only its author's records |
| [Pages](.github/workflows/pages.yml) | after any of these | runs the tests, builds the site (`scripts/build_site.py`), checks it in a browser, and publishes it from `main` |

The tools are pinned: evidence-core `v0.16.1`, evidence-store `v0.7.2` (`requirements.txt`), the
extractor's 0.13 series (`data/settings.json`). The store imports the
[Mathlib probability store](https://github.com/LeanTrustBuilders/mathlib-probability-evidence): its
reviews of the Mathlib declarations Tau Ceti rests on show here.

## Files

- `evidence/`: the store (`store.json`, `records/*.jsonl`).
- `data/settings.json`: the pin, the library, the extractor series, dataset retention, Voyager's topic.
- `data/voyager.jsonl`: every announcement Voyager has made.
- `scripts/`: `pin.py`, `extractor.py`, `prune.py`, `voyager.py`; `site_data.py` (everything a page
  shows, from evidence-core) and `build_site.py` (writes `_site/`).
- `web/`: the front end (`index.html`, `style.css`, `data.js`, `render.js`, `map.js`, `app.js`) and
  `vendor/` (elkjs, KaTeX, the Atlas's `markdown.js`; see `web/vendor/NOTICE`).
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
