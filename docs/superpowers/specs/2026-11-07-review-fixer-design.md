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

The pull requests then go through Tau Ceti's own CI and AI review like any other, and the fixer sees them through
it (asked the same day: "make sure the worker that opens the pr also deals with the reviews").

## Seeing its pull requests through review

`python -m fixer follow`, every two hours (`fixer/systemd/tauceti-fixer-follow.*`; `fixer/follow.py`,
instructions `fixer/follow.md`, which takes the rules and the way of working from `fixer/prompt.md`). For each pull
request the fixer opened and that is open, the first of these that applies is the round's work:

1. a merge conflict: the change is put on the current `main` again (`git apply --3way`), the model resolves the
   markers, and the branch is replaced (`--force-with-lease`, one commit on `main`);
2. CI failing on the head: the failing jobs' errors, from their logs;
3. Tau Ceti's AI review of the head asking for changes: the scoreboard's `<!--tauceti-meta:v1 …-->` names the head
   and each rubric's state; the threads of the rubrics not green (`<!--tauceti-rubric:NAME-->`) on that head, not
   resolved and not answered by the fixer, are the findings;
4. people's comments and review threads since the head was committed.

The model fixes what is right and contests what is wrong (a reply in the finding's thread, which Tau Ceti's review
takes as the author's contest); it may correct the `Roadmap:` line, or close a pull request that should not go in.
A change passes the same gate and is pushed on top of the branch. The builds of each round's checkout are prepared
from the Lake caches first (its base may pin another Mathlib). A round is keyed by the head, the scoreboard or the
comments, and never worked twice; at most eight rounds a pull request, about $15 a round, within the day's $75.
Merged: done, and intake settles the review on the site. Closed without merging, eight rounds spent, or a round
given up or refused: listed for a person.
