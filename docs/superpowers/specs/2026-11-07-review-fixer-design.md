# The review fixer

Asked on 2026-11-07: every day, check whether people have left reviews on the review site; if so, have a Claude
agent, on the API with Opus, look at each and address it, open the pull request if one is needed, and reply naming
the pull request that addresses it. Mathlib's declarations are the exception: never a pull request to Mathlib, the
change is left to a person.

## What it takes

People's noes and suggestions (`by.kind == "person"`, verdicts `problem` and `question`) from issues of the review
repository, in force, not linked to a pull request yet, filed since the fixer started (`since`, a day before its
first run), not taken before; the oldest first, at most three a run. The answerer (hourly, Claude Fable 5.1) may
have answered one already: an answer is not a fix, so it is taken all the same, and the model reads the answer.

## How

`python -m fixer run`, a systemd user timer on the server at 06:30 UTC (`fixer/systemd`), from its own clone of
this repository (`~/tauceti-fixer/review`) with the answerer's virtual environment.

1. Prepare (`fixer/prepare.py`): its own clone of Tau Ceti (`~/tauceti-fixer/work/TauCeti`) at the commit the site
   shows, with Mathlib's and Tau Ceti's builds from the Lake caches.
2. For each review (`fixer/run.py`), the model (`fixer/agent.py`): `claude-opus-5-5`, effort high, the refusal
   fallback on, a JSON result (`output_config.format`), about $25 a review and $75 a day. Its tools
   (`fixer/tools.py`) read and search Tau Ceti and Mathlib, edit and create Lean files below `TauCeti/`, find a
   module's importers, build modules and check short files with Lean sealed off (`bwrap`: no network, an empty
   environment, a fresh home; the API key and the GitHub login stay outside), and show the diff. No shell. The
   review and its thread reach the model between `untrusted-…` tags.
3. The run acts on the result (`fixer/publish.py`), never the model:
   - `pr`: the gate (only Lean files below `TauCeti/`; no added line with what Tau Ceti's source guard refuses or
     what could run code; at most 1500 added lines; the changed modules and their importers build again, sealed
     off); then a branch `fixer/<record>-<time>`, pushed to Tau Ceti, the pull request (the model's description,
     the review's link, the validation, `Roadmap:` checked against TauCetiRoadmap's areas, the footer naming the
     model), and on the review's issue `/addressed TauCetiProject/TauCeti#N — <title>` and the reply. Intake
     records the link and settles the review when the pull request merges (`scripts/pr_links.py`).
   - `already_addressed`: `/addressed` with that pull request, once GitHub confirms it is Tau Ceti's or Mathlib's
     and not closed without merging.
   - `mathlib` (and anything the model proposes for a dependency's declaration): the reply, saying what a person
     should propose upstream; listed for a person.
   - `no_change`: nothing posted (the answerer answers every open review); `gave_up`, no result, or the gate
     refusing: listed for a person.
4. The issue "Fixer: needs a person" is rewritten after each run; a review leaves it once a pull request is linked.

`--dry-run` publishes nothing: a change stays on its local branch as a draft, and `python -m fixer publish
<record>` publishes it later, through the gate again. `--only <record>` takes the reviews named, new or not.

The pull requests then go through Tau Ceti's own CI and AI review like any other.
