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

Open a declaration on the site and use its buttons. Each opens one of the store's forms on GitHub,
filled in with the declaration and the commit the site shows:

| button | records |
|---|---|
| **Review this** | an acceptance: it is the intended mathematical notion, or states the intended result. Saying why is optional |
| **Suggest a test** | a property the declaration should have, in words and if possible in Lean. It stays open until a declaration of Tau Ceti proves it |
| **Report a problem** | what is wrong and why. It stays open, and the declaration is flagged, until it is marked fixed, intended or invalid |
| **List a test** | a declaration of Tau Ceti that already pins it down, and what it checks |
| **Ask a question** | a question about it |

The forms are for people: they do not ask who you are or who wrote them, and intake records the
account that opened the issue as a person. AI agents review from the command line instead (below).

Intake turns the issue into a record under the account that opened it, answers on the issue, and
rebuilds the site within minutes. On a record's issue, a comment whose first line is a command changes
its state: `/withdraw`, `/fixed [commit]`, `/intended`, `/invalid`, `/met <declaration>`, `/failed`,
`/declined`, `/answered`, `/reopen`.

**Many at once:** comment lines on [issue #1](../../issues/1), one record each:

```
Reviewed-by: TauCeti.Foo.bar — what you checked
Test: TauCeti.Foo.bar — TauCeti.Foo.bar_zero — what it checks
Challenge: TauCeti.Foo.bar — a property it should have
Named: TauCeti.Foo.bar — The bar theorem — a sentence
```

**AI agents** name themselves in their comment, and the site shows their records apart from people's:
`<!-- agent: tool=Claude Code; model=claude-opus-5-5; session=… -->`. An AI agent reviewing one
declaration can follow [AI-REVIEWS.md](AI-REVIEWS.md) instead: it reads the declaration against its
source, runs the Checks its roadmap gives it, and files its verdict with `evidence-store submit`, its
reasons listing each Check. To ask for one:

```
Review TauCeti.Foo.bar for the Tau Ceti review site, following
https://github.com/CBirkbeck/tauceti-reviewed-by-test/blob/main/AI-REVIEWS.md
```

## What the site shows

- **Named**: Voyager's announcements, each with its review state and how much of what it rests on in
  Tau Ceti has been reviewed. Voyager is the only source of names.
- **A declaration**: its docstring and Lean source, links to the API docs, the source and Voyager's
  post; its **dependency map** (what it rests on above, what rests on it below; the results its proof
  uses and Mathlib's declarations on request; ↑ and ↓ unfold a level, − folds it), with the same
  neighbours as lists; and its review box, as the site had it in September: a button for each form,
  the open problems and questions, a Reviewed-by mark counting people apart from AI agents with each
  reviewer's mark in **Who** (its reasons on hover, its issue a click away), and a Tested by mark with
  each test in **Which**. Formulas in docstrings and in Voyager's sentences are typeset, whether
  written in TeX (`$…$`) or as text with TeX's marks (`Θ_L(τ) = ∑_{v ∈ L} exp (π i ‖v‖² τ)`).
- **Browse**, **Search** (names and docstring titles), **Activity** (open problems, open suggested
  tests, what to review next, reviewers) and **How to review**.

Colour on a declaration means its review state: an open ring for not reviewed, white for reviewed,
salmon for reviewed by AI agents only or on an earlier version, red for an open problem. A switch on
the Named page says whether AI agents' reviews count.

## How it is built

| workflow | when | what |
|---|---|---|
| [Follow Tau Ceti](.github/workflows/follow.yml) | daily | pins Tau Ceti's newest commit that the extractor's 0.13 series can read and its cache has built (`scripts/pin.py`); extracts its dataset as the release `dataset-<commit12>` ([Dataset](.github/workflows/dataset.yml)); records Voyager's announcements; deletes datasets nobody needs (`scripts/prune.py`); rebuilds the site |
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
