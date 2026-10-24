# Tau Ceti Review: the review site on the LeanTrustBuilders suite

*Design of 2026-10-23, agreed in conversation; the implementation plan is written from it.*

## 1. What it is for

The site replaces <https://cbirkbeck.github.io/tauceti-reviewed-by-test/>, in the same repository and
at the same address. It must:

1. let people and AI agents **review** Tau Ceti's declarations, **report problems**, **propose and
   list tests** and **ask questions** from the browser, without pull requests, as the current site
   does;
2. key every record to the declaration's **meaning hash** (spec S1), so that a review says which
   version it was made on, instead of writing review lines into Tau Ceti's sources through a fork's
   pull request;
3. show, for any declaration, **what it rests on and what rests on it**, as a map whose nodes open the
   declarations they stand for;
4. lead with the **named results and notable definitions Voyager has announced** on the Lean Zulip:
   the declarations people are likely to care about, rather than API and steps of proofs;
5. **look like Mathlib Explorer** (<https://leantrustbuilders.github.io/mathlib-explorer/>), in the
   colours of the Tau Ceti Atlas (<https://cbirkbeck.github.io/tauceti-explorer/#view=all>).

## 2. Decisions, and why

| decision | why |
|---|---|
| The store, the pipeline and the site live in `CBirkbeck/tauceti-reviewed-by-test`. | A section of taucetiproject.org was considered first. Tau Ceti's `main` is behind a merge queue that refuses direct pushes, so intake could not write records there, and the site's Pages workflow takes 30 minutes to 5 hours and failed in half of its last ten finished runs, so reviews would appear hours late. The LeanTrustBuilders repositories are read-only for this account. Records are keyed by hashes, not by repository, so the store can move later. |
| Everything behind the page is the LeanTrustBuilders suite: the extractor's datasets (S2), an evidence store (S3) with evidence-store's forms and intake, and evidence-core for everything computed. | The suite does what this repository's own scripts do, keyed by the meaning hash, and its stores import each other: the Mathlib probability store's reviews of the Mathlib declarations Tau Ceti uses show here. |
| A front end of our own (the "A" approach), its data laid out as Mathlib Explorer's is. | Re-skinning referee-site, or extending the pilot's page, gives neither the Atlas's look nor navigation through the dependency graph; a whole-library referee-site is also near GitHub Pages' size limit for a library this size. |
| Named results come from Voyager alone. | Voyager's announcements are checked to be named and new. The roadmaps' `STATUS.md` lists, which the current site also reads, name much that is neither. |
| A workflow reads Voyager's topic with a Zulip key kept as an Actions secret. | The list keeps up with Voyager without anyone running anything. |
| The front end computes nothing. | The suite's rule: statuses, threads, coverage and the graph summaries come from evidence-core; the page lays them out. |
| The suite's tools are pinned to release tags. | So an upstream change cannot break the daily build unannounced; they are moved on deliberately. |
| Mathlib Explorer's layout and type, dark by default in the Atlas's palette, with a light palette to switch to. | Asked for on 2026-10-23, after the first version (the Atlas's shell, rail and planets) went live: the page reads like the suite's other reader, and keeps Tau Ceti's colours. |

## 3. What exists, and what is reused

- **The suite** (public, under github.com/LeanTrustBuilders):
  - `specs`: S1 (declaration key), S2 (dataset), S3 (evidence records and stores);
  - `extractor`: `trust-extract` and its GitHub actions (`setup`, `extract`);
  - `evidence-store`: issue forms, intake from issues and comments, the store check, `init`,
    `dataset`, `fetch-imports`;
  - `evidence-core`: statuses, threads, coverage, the review queue, record views, `graphs`, `docs`,
    `source`;
  - `referee-site`: its ELK layout of dependency graphs (elkjs, vendored);
  - `mathlib-explorer`: its sharded JSON and its use of `graphs` for 314,000 declarations.
- **The pilot**, `LeanTrustBuilders/reviewed-by-pilot`: this repository's page rebuilt on the suite.
  - Reused: its dataset workflow, which has failed since 2026-10-21 because Tau Ceti's
    `scripts/lake-cache-get.sh` now runs `uvx`, which its runner lacks (fixed here by installing
    `uv`); its pinning rule; and its parser of Voyager's bullets, extended to today's docs addresses.
  - Not reused: its page (this repository's old one), its roadmap reader, `apply.py`, and its
    records, which are keyed under the hasher the suite dropped on 2026-09-28 (7.1).
- **Mathlib Explorer's page** (`LeanTrustBuilders/mathlib-explorer`, `static/`, Apache-2.0): its
  layout and type, its lists, and its words for Lean's basic notions.
- **The Atlas** (`CBirkbeck/tauceti-explorer`): its dark palette, its `markdown.js` and its copy of
  KaTeX.

## 4. The repository after the change

```
.github/ISSUE_TEMPLATE/evidence-*.yml, config.yml   from `evidence-store init`, less You are, Written by, Agent;
                                                     the review and problem forms cut to yes and no,
                                                     the question form recast as What could be better,
                                                     the challenge form cut down for Suggest a test
.github/workflows/
  follow.yml           hourly: pin the commit Tau Ceti's API docs show; when it moves, extract its
                       dataset, record Voyager's announcements, prune old datasets, then pages
  dataset.yml          one commit's dataset as a release (called by follow.yml, or by hand)
  voyager.yml          twice daily: Voyager's announcements as named records, then pages
  evidence-intake.yml  from `evidence-store init`
  evidence-check.yml   from `evidence-store init`
  pages.yml            build and deploy the site
data/settings.json     the pinned Tau Ceti commit, the bulk issue, the Zulip topic
data/voyager.jsonl     every announcement read so far
evidence/store.json    the store's description
evidence/records/      the records, one JSONL file per month
scripts/voyager.py     read the topic, record the named results
scripts/prune.py       delete old dataset releases
scripts/build_site.py  dataset, store and imports to _site/data, through evidence-core
web/                   the front end: index.html, app.js, map.js, style.css, vendor/
tests/                 unit tests, fixtures and the browser check
docs/superpowers/specs/this design
README.md              what the site is and how to use it
```

Removed, kept in git history: `scripts/apply.py`, `fetch_declarations.py`, `reviews.py`, `named.py`
and the old `build_site.py`; `reviews/*.jsonl`; `data/named-roadmaps.json`; the old forms
(`reviewed-by.yml`, `problem.yml`, `test.yml`); the workflows `record.yml`, `refresh.yml` and the
old `pages.yml`; `.github/actions/declarations`.

## 5. How data flows

```
Tau Ceti main ──follow.yml──> pin ──dataset.yml──> release dataset-<commit12>
Zulip "Tau Ceti > new results" ──voyager.yml──> data/voyager.jsonl ──> named records ──┐
issues and comments ──evidence-intake.yml──> reviews, problems, tests, challenges … ────┤
                                                                         evidence/ <───┘
dataset + evidence/ + imported stores ──pages.yml: build_site.py──> _site ──> GitHub Pages
```

### 5.1 Datasets: `follow.yml`, `dataset.yml`, `scripts/prune.py`

- **When:** hourly at 20 past (asked for on 2026-10-24: the site should follow Tau Ceti's API docs,
  which are rebuilt a few times a day, each run taking one to three hours), and by hand. A run whose
  pin does not move stops after a minute.
- **The pin:** the commit Tau Ceti's API docs show (the head of the newest successful run of its
  `api-docs.yml` on main, `library.docs_workflow` in the settings; `main` when there is none), or the
  newest of the 30 commits from there back whose toolchain the extractor has a release for and whose
  build Tau Ceti's cache has published (the pilot's rule). It is written to `data/settings.json` and
  committed. An unchanged pin ends the run; so does a docs commit that is the pin already, after one
  request.
- **Extraction:** a blob-less clone of Tau Ceti at the pin; Tau Ceti and Mathlib from their caches
  (`lake exe cache get`, then Tau Ceti's `scripts/lake-cache-get.sh`, with `uv` installed first);
  then the extractor's `extract` action with the pilot's arguments: `--parts 8 --jobs 1
  --skip-modules-file <modules that do not build> --no-statements --no-signatures
  --no-upstream-docs`. It is published as the release `dataset-<commit12>` (asset
  `dataset.tar.gz`, about 120 MB). Modules that do not build are left out and listed in the
  dataset's `library.unavailable`.
- **Pruning** (`scripts/prune.py`, after a new dataset is published): the `dataset-*` releases older
  than 30 days are deleted, except the newest and any whose commit an open issue of the store names
  (intake keys a form's record in the dataset of the commit the form names, and waits while that
  dataset is missing).

### 5.2 The evidence store

`evidence/store.json`:

```json
{
 "spec": "ltb-evidence-store/1",
 "name": "Tau Ceti",
 "library": {"repo": "TauCetiProject/TauCeti", "root": "TauCeti"},
 "datasets": {"repo": "CBirkbeck/tauceti-reviewed-by-test", "tag": "dataset-{commit12}", "asset": "dataset.tar.gz"},
 "claims": [],
 "maintainers": ["CBirkbeck"],
 "imports": [{"repo": "LeanTrustBuilders/mathlib-probability-evidence"}]
}
```

- **Forms and intake** are evidence-store's, set up by `evidence-store init`: review a declaration,
  report a problem, propose a test (a challenge), list a test, ask a question, name a result, and a
  change of state. The forms leave out "You are", "Written by" and "Agent" (asked for on 2026-10-24):
  only people fill them in, and intake records the account that opened the issue as a person, of
  unknown involvement; AI agents submit from the command line with `evidence-store submit`. A review
  answers one question, "is it correctly stated?" (asked for on 2026-10-24): the review form is the
  yes (the declaration and the commit, filled in by the site, and an optional why) and the problem
  form the no (the same, and a why it will not submit without; with no "What is wrong", intake records
  `other`). Under the question, "What could be better" (asked for the same day) takes suggestions for
  a declaration that is correct but could be done better, on the question form recast for it (its
  field keeps the label "Question", by which intake reads it): recorded as questions, open until dealt
  with, neither yes nor no. Under Tests, "Suggest a test" (asked for the same day) opens the
  challenge form, cut to the property it should have (required), a Lean statement and what it would
  catch (both optional). The site offers no other form. Intake turns an issue into a record keyed in the dataset of the commit the form
  names, answers on the issue, and starts `pages.yml`. A comment whose first line is a command
  changes a record's state (`/withdraw`, `/fixed [commit]`, `/intended`, `/invalid`,
  `/met <declaration>`, `/failed`, `/declined`, `/answered`, `/reopen`); so does closing or reopening
  the issue by hand.
- **Issue #1** stays the bulk issue (label `evidence:bulk`): one record per line,
  `Reviewed-by: <declaration> — <note>`, `Test: <declaration> — <test> — <what it checks>`,
  `Challenge: <declaration> — <property>`, `Named: <declaration> — <name> — <sentence>`. An AI agent
  adds `<!-- agent: tool=…; model=…; session=… -->` to its comment, and its records are shown apart
  from people's.
- **AI agents can review from the command line:** `AI-REVIEWS.md` says how. An agent reads the
  declaration against its source; runs the Checks its roadmap gives it (in TauCetiRoadmap a target's
  unit tests, each an `example` in `TauCeti/Examples/` carrying its tag once formalised, which the
  dataset cannot see, so the review is where they are recorded); and files its verdict with
  `evidence-store submit`, its reasons listing each Check and whether it passes. Without the right to
  label issues it comments on the bulk issue instead.
- **Imports:** the Mathlib probability store. Its records about declarations of this dataset (the
  Mathlib declarations Tau Ceti rests on) show here, marked with that store's name, without actions.

### 5.3 Voyager's announcements: `voyager.yml`, `scripts/voyager.py`

- **When:** 04:15 and 16:15 UTC (Voyager posts at about 03:30 and 15:20), and by hand.
- **Reading:** the Zulip API's `GET /api/v1/messages`, narrowed to channel `Tau Ceti`, topic
  `new results`, sender Voyager's bot account, with `apply_markdown=false`, paging back from the
  newest until `found_oldest`. Credentials are the secrets `ZULIP_SITE`, `ZULIP_EMAIL` and
  `ZULIP_API_KEY` (Voyager's own key). The job only reads.
- **Parsing:** an announcement is a bullet `- **[<name>](<docs address>#<declaration>)**`, possibly
  followed by `†` or `*`, then `—` and a sentence ending in `(TauCeti#<n>)` pull requests. The docs
  address is either form: `https://taucetiproject.github.io/TauCeti/docs/<Module path>.html` (posts
  until mid-October) or `https://taucetiproject.org/docs/<Module path>.html`. The anchor is the
  declaration's full name. The heading above a bullet sets `what`: `*Named results*` gives `result`,
  `*Notable definitions*` gives `definition`; under any other heading (the first post's subject
  headings) the declaration decides, `result` for a proof and `definition` otherwise. The
  `*In progress*` and `*Stats*` lines have no such bullets, so they are never announcements.
- **Keeping:** each new announcement is appended to `data/voyager.jsonl` (`decl`, `name`, `what`,
  `about`, `at`, and `source`: the message id, the channel id and the pull requests), deduplicated by
  declaration and name. The file keeps the history if the key is ever lost.
- **Recording:** for each announcement whose declaration is a node of the pinned dataset and that
  Voyager has not yet named in the store, a `named` record:
  - `by`: `{"kind": "agent", "agent": {"tool": "Voyager"}}`;
  - `origin`: `{"kind": "zulip", "ref": "voyager <message id>"}`;
  - `name`, `what`, and `text`: the sentence without its links and pull request numbers;
  - `reference`: `{"text": "Voyager, TauCeti#<n>", "url": "<the post's Zulip link>"}`;
  - `at`: the post's time; `subject`: the declaration's key in the pinned dataset.

  An announcement whose declaration the pin does not have yet is recorded on a later run, once it
  does. Running twice records nothing new; the push is retried when it races another, as the
  pilot's is. The first run reads Voyager's whole history (119 posts on 2026-10-23, about 1,377
  bullets).

### 5.4 Building the site: `pages.yml`, `scripts/build_site.py`

- **When:** after `follow.yml`, `voyager.yml` or intake change anything; on a push to `main` that
  touches `web/`, `scripts/build_site.py` or `evidence/`; and by hand.
- **Inputs:** the pinned dataset (`evidence-store dataset --commit`), Tau Ceti's sources at the pin
  (a blob-less clone, for source text), `evidence/`, and the imported stores
  (`evidence-store fetch-imports`).
- **What evidence-core computes,** and the page only shows:
  - every record's status against the dataset, its thread, latest state, whether it is in force and
    the changes of state it allows (`Evidence.resolve` with the imports, and `views`);
  - where each declaration stands (`decl_state`) under two policies: people only, and people with AI
    agents; every other switch at evidence-core's default;
  - tests (listed tests and met challenges: passing, with `sorry`, missing) and open challenges;
  - the coverage of each named declaration under both policies, and the review queue over the named
    declarations;
  - `graphs`: for each node, `built_from`, `about` and `proof_uses`; the reverse, `built_on`, `facts`,
    `examples` and `used_in`; `importance`, `basic` and `routine`;
  - `docs` (module docstrings, declarations' titles) and `source` (a statement apart from its proof).
- **Outputs,** under `_site/data/`, compact JSON:

  | file | contents |
  |---|---|
  | `meta.json` | the pinned commit, its date and toolchain; the dataset's tag and extractor version; the store's name and repository, the form addresses, the bulk issue; the imported stores and the commits read; counts; the build time |
  | `named.json` | one row per named declaration: each `named` record not withdrawn whose declaration is still in the dataset (by its name, or by its meaning hash when renamed; one whose statement changed stays named). Id, Lean name, Voyager's name, `what`, the sentence, area, when and where announced (post link, pull requests), review counts (people, AI), state and coverage under both policies |
  | `search.json` | one row per project declaration: name and kind, loaded at the first search; `titles.json` has their titles in the same order, loaded next, for searches by words |
  | `nodes/<k>.json` | every node by id, 2,048 per file: name, kind, project or Mathlib, module, title, whether named, state under both policies, and `built_from`, `about`, `proof_uses` (ids, most important first, at most 60 each): what the map draws without opening modules |
  | `names/<k>.json` | name to id, sharded by the FNV-1a hash of the name, as Mathlib Explorer does |
  | `m/<n>.json` | module number `n` (its place in the dataset's modules): its docstring, and for each of its declarations the docstring, the statement in Lean, whether it has a proof, its source range and keyword; `built_on`, `facts`, `examples`, `used_in` (ids, most important first, at most 60 each, with totals); its record threads, tests and open challenges; its announcement |
  | `activity.json` | the newest records, open problems, open challenges, the reviewers (people and agents), and the review queue of the named declarations |
  | `reviewed.json` | every declaration of the library answered for, the latest answer first: its id and name, its yeses of this version, its noes still open and its earlier answers, each as [people, AI agents], and the latest answer's date |
  | `modules.json` | every module a node belongs to: name, package, title, source path; the project's first, in the dataset's order, then the others |
  | `upstream.json` | the record threads about declarations outside Tau Ceti (from the imported stores), by name |

- **Budget:** the build fails if `_site` exceeds 800 MB (GitHub Pages allows 1 GB). Sizes are
  measured on a real dataset before CI depends on them.

## 6. The front end (`web/`)

Static HTML, CSS and JavaScript, without a framework or a build step, as the Atlas is. Vendored:
elkjs 0.9.3 (EPL-2.0, the copy referee-site vendors, loaded the first time a map is drawn); the
Atlas's `markdown.js` with its KaTeX 0.16.28 (MIT): Markdown in which source HTML stays text, links
are filtered, and `$…$` becomes vetted MathML; and Mathlib Explorer's three faces, Source Serif 4,
Inter and JetBrains Mono (OFL-1.1, the latin, latin-ext and greek subsets), so that the page fetches
nothing from elsewhere. Record texts come from anyone's issues, so every
docstring and record text goes through it, never into the page as HTML. Pan and zoom are pointer
events (referee-site's code, Apache-2.0, with pinch added): no D3.

### 6.1 Look

Mathlib Explorer's page: one centred column at most 1120 px wide under a sticky top bar; serif
headings and prose (Source Serif 4, else Georgia), a sans-serif for everything else (Inter), Lean in
JetBrains Mono. Dark by default, in the Atlas's tokens; the ◐ button switches to a light palette and
the browser remembers it.

```
dark   --bg #0b1016  --surface #0e141b  --raised #131a22  --line #222c37
       --ink #e2e6eb  --muted #8391a0  --faint #5b6875  --accent #dfc186 (gold)
       kinds: notion #7fa9d6  result #9cc59a  instance #b9a0dd
       states: covered #f7f3e9  uncounted, stale #e89678  problem #e0705c
light  --bg #fbfaf7  --surface #ffffff  --ink #1d2126  --accent #8a6a1f
       kinds: notion #2c5f8a  result #2f7a55  instance #7a5b9a
       states: covered #2f7a55  uncounted, stale #b4562f  problem #b0392a
```

- **A kind is a colour**, as in Mathlib Explorer: a pill over a declaration's title (Definition,
  Theorem, Instance…), the left edge of each item in a list, the border of its box on the map. A named
  declaration has a gold badge, and a gold border on the map.
- **A review state is a badge,** under the policy the reader chose (AI reviews counted or not): a dot
  in the state's colour and a word.

  | evidence-core's state | badge |
  |---|---|
  | unreviewed | open ring, "Not reviewed yet" (left off in lists) |
  | covered | filled dot, "Reviewed" |
  | uncounted: accepted only by reviewers the policy does not count | salmon dot, "AI only" |
  | stale: reviewed, but no acceptance the policy counts applies to the current version | salmon ring, "Earlier version" |
  | problem: an open problem in force | red dot, "Problem" |
  | disputed: an acceptance and an open problem in force | red dot ringed, "Disputed" |

- Flat fills and thin strokes; no transitions under `prefers-reduced-motion`.

### 6.2 Shell

- **Top bar:** "Tau Ceti Review"; the search box (`⌘K` or `/`, results as you type); Named, Reviewed,
  Browse, Activity, How to review; the theme button.
- **Footer:** the pinned commit and its date, when the site was built, the store, How to review.
- **Phone width:** the sections wrap under the search box, and the page is one column.

### 6.3 Addresses

`#/` (home), `#/named`, `#/reviewed`, `#/d/<name>`, `#/m/<module>`, `#/area/<Area>`, `#/search/<query>`,
`#/browse`, `#/activity`, `#/help`. The old site's addresses, query-style hashes, still work:
`#d=<name>` opens `#/d/<name>`, `#m=<module>` opens `#/m/<module>`, `#area=<Area>` opens
`#/area/<Area>`, and `#q=<query>` opens `#/search/<query>`.

### 6.4 Pages

- **Home:** what the site is; the counts (declarations, named, reviewed (a link to Reviewed), yeses
  by people and by AI agents, noes still open); tiles for Named, Reviewed, Browse, Activity and How to
  review; the eight latest named; the areas.
- **Named:** Voyager's announcements grouped by area, each with Voyager's name and sentence, the Lean
  name, its review state, a coverage bar (how much of what it rests on in Tau Ceti has been reviewed)
  and the date. Filters: results or definitions, area, review state, words; sorted by newest, by
  name, or by how much rests on it; the "Count AI reviews" switch.
- **Reviewed** (asked for on 2026-10-24): every declaration of Tau Ceti answered for, the latest
  answer first (`data/reviewed.json`), each with its yeses of this version and its noes still open,
  people apart from AI agents, and how many earlier answers; filters for yes or no, for people or AI
  agents, and words.
- **Declaration,** one column:
  1. the breadcrumbs; the kind's pill, "Named by Voyager" and the review state; the title (Voyager's
     name, else the docstring's first sentence, else the Lean name; a first sentence cut short for
     lists, past 160 characters, gives way to the Lean name); the Lean name, with copy; links
     to Tau Ceti's API docs (`taucetiproject.org/docs/<Module path>.html#<name>`), to the source at
     the pinned commit, to the Voyager post and its pull requests;
  2. Voyager's sentence, and the docstring, less what the title already says (asked for on
     2026-10-24): its first sentence when that is the title, and under Voyager's name a bold opening
     that is a sentence or a heading of its own and only names it ("**Strassmann's theorem.** Let …"),
     but not one that goes on in its sentence or says more; its maths rendered: `$…$` as KaTeX renders it, and a
     formula written as text with TeX's marks (`Θ_L(τ) = ∑_{v ∈ L} exp (π i ‖v‖² τ)`, in a code span
     or in a sentence) typeset too (`web/formulas.js`); Lean in a code span stays code;
  3. **In Lean,** what the docs show of it: the signature Lean prints (the dataset's `signature`
     facet: section variables included, every name a link, and on hover what it is), a definition's
     value folded (the docs' Equations), a structure's fields, and never a proof;
  4. the **review box**, as the site had it in September (asked for on 2026-10-24), asking one
     question (asked for the same day): "Is this theorem correctly stated?" (lemma, definition,
     structure, …: a lemma by its keyword, else its kind) with **Yes** and **No**, "Read it in the API
     docs", and a line saying that either opens a short form and a no asks why; then "Copy
     instructions for your AI" (asked for on 2026-10-24), which copies, and shows, a request for an AI
     agent to review it following AI-REVIEWS.md, with the declaration, the commit and its page; then, under small
     capitals, **Reviews** (a mark "✓ Correctly stated · 2 people · 1 AI" for the yeses of this
     version, a mark "✗ Not correctly stated · 1 person" for the noes still open, then a mark for each
     answer: a person's filled, an AI agent's ringed and marked AI, a tick for a yes and a cross for a
     no, one that no longer stands grey with "earlier version", "what it rests on has changed" or what
     resolved it, an imported one "from the Mathlib probability store". A yes that gives reasons (an
     AI agent's always do) is a twisty (asked for on 2026-10-24) that opens to them, typeset, and to
     its issue; a bare yes links to its issue. Then each no in full: where it stands, who said it and when,
     why, the replies, its issue and what was decided on it), **What could be better** (a line asking
     whether it could be done better, with "Suggest an improvement", and each suggestion: where it
     stands, who made it and when, what it says, the replies and its issue), and **Tests** (a line
     asking for a property it should have, with "Suggest a test"; then a mark "✓ Tested by · 1 test
     that passes · 1 suggested", and each test a twisty (asked for the same day): a listed one says
     whether it passes, which it is and what it checks, and opens to its statement as the docs show it
     (fetched when first opened); a suggested one says where it stands and opens to the rest);
  5. **What it rests on, and what rests on it:** the coverage line of a named declaration, and the
     dependency map (6.5), shown;
  6. the same neighbours as lists, in two columns, each ranked with its first dozen shown: built from
     or about (what comes from Mathlib and Lean as a line of chips, named as Mathlib Explorer names
     Lean's basic notions), proof uses (routine steps counted, not listed), results about it, built on
     it, examples, used to prove. Each item: its title, what it states (its signature without its
     name, its implicit arguments and the arguments that only introduce a type, names by their last
     component, at most 140 characters: `[CommRing R] [IsRegularRing R] [IsDomain R] :
     IsIntegrallyClosed R`), its Lean name, and its review state when reviewed.
- **A declaration outside Tau Ceti** (a Mathlib declaration reached from a map or a list): its kind,
  links to Mathlib's docs and to Mathlib Explorer, the records about it from the imported stores (no
  forms: they are its store's), and what in Tau Ceti rests on it; no map, since the dataset does not
  follow what it rests on.
- **Module:** its docstring; its notions and its results in two columns, named ones first; its
  instances folded.
- **Browse:** a tile for each area. **Area:** its named declarations and its modules.
- **Search:** names and titles of every declaration, notions and results in two columns, named ones
  first.
- **Activity:** the noes and the suggestions still open, any open suggested tests, what to review next for the named
  results (the unreviewed declarations they rest on, those most of them share first), the newest
  records, and the reviewers.
- **How to review:** the question and its two answers, what "correctly stated" means, What could be
  better, versions, AI agents (AI-REVIEWS.md and the bulk issue's lines), and the commands on an
  answer's issue.

Yes and No open `https://github.com/CBirkbeck/tauceti-reviewed-by-test/issues/new?template=<form>`
(`evidence-review.yml`, `evidence-problem.yml`) with the form's `decl` and `commit` fields filled in
(the declaration and the pinned commit).

### 6.5 The dependency map

- **Shape:** what a declaration rests on is above it and what rests on it below, as in a blueprint.
  Laid out by ELK's layered algorithm, as referee-site lays out its graphs, without the edges a longer
  path implies. Without elkjs the page falls back to rows by depth.
- **What it shows by default:** the meaning graph, two levels up (what a definition is built from, what
  a theorem's statement is about) and one level down (built on it, results about it).
  - **Proof uses** adds the results a proof uses (dashed edges) above, and the results whose proofs use
    it below. Routine steps are counted, not drawn.
  - **Mathlib** shows or hides Mathlib's (and Lean's) declarations; hidden at first, so that the map
    shows Tau Ceti's own structure, which is what can be reviewed here (the lists below the map include
    Mathlib's). They are leaves (the dataset follows no dependencies inside Mathlib).
  - Only the first level up ends in a "+ N more" node; the second level up shows four per node.
  - **Arrows:** a node of Tau Ceti has ↑ (or ↓) while unfolding it would draw something the map leaves
    out, at any depth: what it rests on above, what rests on it below. Each node row says how many of
    the declarations it rests on are Tau Ceti's and how many rest on it, so the arrows are exact for
    statements; with proofs they are a guess. An unfolded node shows −, which folds it again. An arrow
    that finds nothing says so in a note on the map, and goes.
- **Nodes:** a box bordered in its kind's colour (gold when named, dashed when from Mathlib), a dot
  for its review state, and a short name. Hovering shows its name, title and statement; clicking goes
  to the declaration and the map re-centres; a node's expand control adds its own level in place.
  A level with more than 12 nodes shows the 12 most important and a "+ N more" node that shows the
  rest, up to the 60 the data keeps; beyond those the node and the lists give only the total.
- **Controls:** proof uses, Mathlib, fit, full screen; pan and zoom by pointer, wheel and pinch. In
  full screen the button reads "✕ Leave full screen", and Esc leaves it too.
- **For a named declaration,** a line above the map gives its coverage: of the Tau Ceti declarations
  in its meaning closure (what its statement mentions, and a definition's value, proofs left out),
  how many people have reviewed, how many only AI agents, and how many nobody.

## 7. Moving over

1. **Records:** this repository's own ledgers (`reviews/records.jsonl`, `reviews/tests.jsonl`,
   `reviews/problems.jsonl`: 4 reviews and 11 tests, all by `CBirkbeck`, some through an AI agent),
   migrated with `evidence-core migrate reviewed-by` against the first pinned dataset, with their
   origins on this repository's issues. The pilot's copies cannot be reused: they are keyed under
   the hasher the suite dropped on 2026-09-28 (`semantic_hash`), so they read as incomparable. The
   migration takes the hashes from the pinned dataset and says so (`migration.hashes_from`). That is
   faithful because the four declarations' text has not changed since they were reviewed: the old
   site still shows every review as current at Tau Ceti `ffc1a6d` (2026-10-23). Their author pushes
   them, so `evidence-check.yml` accepts them.
2. **Named results:** Voyager's whole history, read again from Zulip and keyed in the new pinned
   dataset.
3. **Issue #1:** stays the bulk issue, labelled `evidence:bulk`, with its description replaced by the
   new lines.
4. **The fork:** the "Review lines" workflow (`.github/workflows/review-lines.yml`) on
   `CBirkbeck/TauCeti` is disabled. The lines already on the fork's `main` stay; nothing updates them.
5. **Secrets:** `ZULIP_SITE`, `ZULIP_EMAIL`, `ZULIP_API_KEY` set on this repository from
   `~/.zuliprc` with `gh secret set`.

## 8. Testing

- **Unit tests** (`python3 -m unittest discover -s tests`, the standard library):
  - `scripts/voyager.py` on saved posts: both docs addresses, both sections, the first post's subject
    headings, `†` markers, the "In progress" and "Stats" lines, the same announcement in two posts, an
    announcement ahead of the pin, and a second run recording nothing;
  - `scripts/build_site.py` on the suite's two-version fixture (`specs/vectors`): a review current,
    stale, stale underneath and renamed each reaches the page data as such; every id in `nodes/`,
    `m/` and `named.json` resolves; the size check fails above its budget;
  - `scripts/prune.py`: keeps the newest dataset, those under 30 days old and those an open issue
    names.
- **Browser check** (`tests/validate_site.py`, Playwright with Chromium), on the fixture's build in
  CI and on the real build before the switch: the page is dark, light at a click, and stays light;
  the home page; the Named page lists announcements by area; search finds a declaration by name and
  by title; a declaration shows its signature (and no proof), what its names are on hover, reviews,
  map, and lists with statements; clicking a node opens it; Proof uses adds edges; every button's
  address carries the declaration and the commit; old `#d=` addresses resolve; no errors in the
  console; the same at phone width.
- **End to end,** after the switch and with the owner's go-ahead: one real review through a form,
  recorded by intake and shown by the page.

## 9. Rollout

1. Work on the branch `suite-site`. The current site keeps serving until the switch.
2. Locally: the 2026-10-19 dataset of the pilot, the carried-over records and Voyager's history; the
   front end built against them and checked in a browser. The named records made here serve the
   local build only: the store's are written by `voyager.yml` in CI, as the pilot's are.
3. In CI, still on the branch: the labels, the Zulip secrets, the first dataset (the pilot's of the
   pin, published unchanged as this repository's release), and `pages.yml` building without
   deploying. GitHub runs a workflow by hand only if one of that name is on `main`: `pages.yml` is (the
   old page's), so it can be tried on the branch; `dataset.yml`, `follow.yml` and `voyager.yml` run
   for the first time after the switch.
4. The switch: `main` becomes the branch (the site at the same address is replaced); `voyager.yml`
   records Voyager's announcements, `follow.yml` moves the pin; disable "Review lines" on the fork;
   replace issue #1's description.

## 10. Risks

- **Size and memory** for about 196,000 declarations and 24 million edges (7.5 million meaning, 16
  million proof). Mathlib Explorer builds 314,000 in CI with the same sharding; ours is measured on
  the real dataset before CI depends on it, and the build enforces its budget.
- **Tau Ceti moving to a toolchain the extractor has no release for.** The pin waits on the last
  commit before the move, and the page always names the commit it shows.
- **The suite's tools changing.** Pinned to release tags and moved on deliberately.
- **Voyager's post format changing.** The parser's tests cover today's two formats; a post with no
  bullet it can read is reported in the workflow's summary rather than ignored.

## 11. Not in this version

- Every identifier in a statement linked to its declaration: needs the extractor's statement facet,
  a slower and larger extraction.
- A private "my reviews" mode in the browser, as referee-site has.
- Naming which dependency changed under a review that is stale underneath: needs the dataset of the
  review's commit at build time.
- A link from taucetiproject.org's navigation, or the store moved into the TauCetiProject
  organization.
- The Mathlib probability store importing this store instead of the pilot's: LeanTrustBuilders' call.
