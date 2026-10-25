# The review answerer: design

Asked for on 2026-10-25: "some system on the server where every hour claude fable (via the api) will
check any questions or issues and answer them, but it needs to only do this for mathematical
questions, we cant have this be a way for people to hack the server by asking agents to do things.
for issues that were found by reviews we should check carefully if they are actually issues, it seems
to me that some may be a result of the mathlib style where definitions are done super generally
beyond whats normally used ... for any geniune errors we should open a PR to tauceti and fix the
issue. in the end we need to reply to the issues and close them", and "make sure the answers to the
nos are recorded somewhere so that others can see why we said things are ok or what was fixed".

## What it does

Every hour, on the server (`ssh ovh`, a systemd user timer), `python -m answerer run`:

1. Reads the store at the review repository's `main`, resolved against the dataset of the commit
   the site shows (`data/settings.json`'s `tauceti`), and lists the **open items**: each no
   (a review with verdict `problem`) and each suggestion or question (verdict `question`) that is
   in force, still open, and not yet answered by it. People's items come before AI agents', the
   oldest first. At most 6 a run and 2 a day per author (the store's maintainers are exempt), and
   nothing once the day's spending reaches $20.
2. For each, asks Claude Fable 5.1 (`claude-fable-5-1`, effort high) for a verdict, giving it the
   declaration (its source and docstring at that commit, from a Tau Ceti checkout built from the
   Lake cache), the item, and the replies so far. Its tools only read:
   - `read_source` and `search_source`: Tau Ceti at that commit and its pinned Mathlib, through
     `git show` and `git grep`, on paths under `TauCeti/` or `Mathlib/` only;
   - `find_declaration`: where the dataset puts a declaration, and its signature;
   - `lean_check`: a short Lean file (`#check`, `example`, …) against those builds, run by
     `bubblewrap` with no network, an empty home directory, the toolchain and the builds read-only,
     and time and memory limits; text that could run code at elaboration (`#eval`, `run_cmd`,
     `elab`, `macro`, `initialize`, `IO`, `unsafe`, `extern`, `implemented_by`, …) is refused before
     anything runs.
   Its last answer is a JSON verdict (`output_config.format`): whether the item is mathematical,
   one of `answered`, `intended`, `not_a_problem`, `docstring_fix`, `lean_fix_needed`, `unclear`,
   `not_mathematical`, a reply for the page, and, for `docstring_fix`, the edits.
3. Acts on the verdict. The code decides what happens, never the model:

   | verdict | on the item | elsewhere |
   |---|---|---|
   | `answered` (a question) | `/answered` with the reply as its note | |
   | `intended` (a no) | `/intended` with the reply | |
   | `not_a_problem` (a no) | `/invalid` with the reply | |
   | `docstring_fix` (a no) | the reply, saying a fix is proposed | a PR to Tau Ceti changing only that declaration's docstring; once it merges, `/fixed <commit>` with the reply |
   | `lean_fix_needed` (a no) | the reply; it stays open | listed for a person |
   | `unclear` | nothing | listed for a person |
   | `not_mathematical` | nothing | logged |

   An item from an issue gets a comment on its issue (the command on the first line, the reply
   below it, which intake keeps as the status's note). An item from a pull request (an AI agent's
   batch) has no issue: it gets the store's status form instead (`evidence-store status`), the
   reply as the note. Either way the reply is recorded in the store, and the site shows it in full
   under the no and in the Activity page's "Answered no, resolved".
4. Items it cannot settle are listed in one issue on the review repository, "Answerer: needs a
   person", which it rewrites each run.

## Why a report cannot make it do anything else

- The model has no shell, no network and no write access: its tools read public source, and the
  Lean check runs sealed off. Secrets stay in the process that calls the API and GitHub.
- Each action is tied to its item: a comment on its own issue, the state of its own record, a PR
  editing only its own declaration's docstring (checked: inside a doc comment before and after, no
  comment delimiters or double quotes in the new text, lines of 100 characters at most, built in
  the sandbox before it is pushed). Whatever the report says, nothing else is reachable.
- The report and the thread reach the model as quoted data, under a system prompt that says so.
- What it posts is cleaned first: HTML comments (agent marks, Reviewed-by marks) and tags removed,
  links kept only to an allowlist of hosts, `@` mentions and `#` references defused, a line starting
  with a `/command` defused, length capped. Its own agent mark comes first.
- It answers only mathematics: an item it judges not mathematical gets no reply.
- Limits on items per run, per author per day, and dollars per day.

## Attribution

Its comments carry `<!-- agent: tool=Tau Ceti answerer; model=<the model that answered> -->`
through the server's GitHub account (CBirkbeck, the store's maintainer, so its closes count). The
API's refusal fallback (`fallbacks: "default"`) is on; the mark names whichever model answered.
Work done before it existed (the PRs of 2026-10-25) closes under the attribution of whoever did it,
kept in its state.
