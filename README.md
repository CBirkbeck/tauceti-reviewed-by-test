# Reviewed-by for Tau Ceti — a test

A test of **review marks** on Tau Ceti declarations: who has checked which
definition, what they checked, and on which version. It is modelled on the
Linux kernel's `Reviewed-by:` trailers, and every mark is left from a browser,
without a pull request. A declaration that is wrong gets a **problem report**
instead: what is wrong and why, in an issue that stays open until it is fixed. Nothing here changes Tau Ceti: the page reads every
declaration of Tau Ceti's main branch, read-only, at a pinned commit that
follows main once a day.

**Page:** https://cbirkbeck.github.io/tauceti-reviewed-by-test/

## Finding a declaration

Search every definition, structure, class, instance, theorem and lemma by
name, part of a name, or words from its docstring; filter definitions from
theorems and lemmas, by area (`NumberTheory`, `AlgebraicGeometry`, …) and by
whether it has been reviewed. Open one to read its docstring and source, see
its marks and the rest of its module, and review it. Every search and every
declaration has its own link (`#q=…`, `#d=<full name>`); `/` jumps to the
search box.

## Marks

| Mark | Meaning |
|---|---|
| `Reviewed-by` | it is the intended mathematical notion |
| `Tested-by` | its examples and unit tests check out |

A mark is pinned to a hash of the declaration's source (a definition whole, a
theorem by its statement). When the declaration changes, the mark stays but is
greyed: it applies to the earlier version until someone reviews the new one.
Marks by AI agents name the agent, model and session and are shown apart from
people's. A person need not say why a declaration is right; an AI agent must
give its evidence.

## Leaving a mark, from a browser

1. **Review this**, on any declaration the page opens, opens the
   [Review a definition](.github/ISSUE_TEMPLATE/reviewed-by.yml) form with the
   declaration and its version filled in. Choose a mark and submit. Saying what
   you checked is optional for a person and required of an AI agent.
2. The [Record review marks](.github/workflows/record.yml) workflow checks the
   declaration exists, appends the mark to
   [`reviews/records.jsonl`](reviews/records.jsonl) (committed directly: no pull
   request), answers on the issue, closes it and rebuilds the page.
3. To mark many at once, comment lines such as
   `Reviewed-by: TauCeti.IdealArithmeticFunction.vonMangoldt — what you checked`
   on [issue #1](../../issues/1). An AI agent adds
   `<!--reviewed-by:v1 {"agent": "<agent, model, session>"}-->` to its comment.

GitHub authenticates who submitted each mark.

## Reporting a problem

1. **Report a problem**, next to Review this, opens the
   [Report a problem](.github/ISSUE_TEMPLATE/problem.yml) form with the
   declaration and its version filled in. Say what is wrong (wrong: false as
   stated or not the intended notion; a misleading name or docstring; something
   else) and why: a counterexample, the source it disagrees with, or the step
   that fails. The why is required, since it is what a fix starts from; a
   suggested fix is optional.
2. The same workflow records the report in
   [`reviews/problems.jsonl`](reviews/problems.jsonl) and answers, but leaves
   the issue **open**: the report is the issue for getting the declaration
   fixed. The page flags the declaration (`!`), lists it under Open problems and
   the Reported problems filter, and shows the report with a link to its issue.
3. Close the issue as **completed** once the declaration is fixed, or as **not
   planned** if it is right after all; the bot records which, and the page shows
   the report as fixed or closed. Reopening it flags the declaration again, and
   editing it updates the report. A report about a version that has since
   changed says so, as a prompt to check whether the change fixed it.

In Tau Ceti itself the report would be an issue on Tau Ceti, for its workers to
pick up, and the fix's commit would carry `Reported-by:` and `Closes:` trailers,
as the kernel's do. This test keeps the reports in its own repository.

## Batching into the code

[Batch marks into the code](.github/workflows/batch.yml) (run by hand here,
weekly in real use) collects the marks since the last batch into one pull
request, as the kernel's `b4 trailers -u` collects Reviewed-by replies. The pull
request shows two forms such a batch into Tau Ceti could take: a data file
(`snapshot/REVIEWED-BY.md`) and the declarations' docstrings with their marks
as trailer lines (`snapshot/docstrings.lean`). Its commit message ends in one
git trailer per mark.

## For other readers

The marks and problem reports as data, for the Tau Ceti atlas or Tau Ceti's own documentation:
[`reviews.json`](https://cbirkbeck.github.io/tauceti-reviewed-by-test/reviews.json).

## Following Tau Ceti

`data/settings.json` pins the Tau Ceti commit the page shows. The
[Follow Tau Ceti](.github/workflows/refresh.yml) workflow moves the pin to
main once a day and rebuilds the page; marks keep the versions they were made
on, so a declaration that changed shows its marks greyed.

## Files

- `scripts/fetch_declarations.py` reads every module of a Tau Ceti checkout
  into `data/declarations.json` (generated, not committed; the workflows check
  out the pinned commit with `.github/actions/declarations`).
- `scripts/reviews.py` records marks from forms and comments, and problem
  reports and what becomes of their issues.
- `scripts/build_site.py` builds the page: `index.html`, the search index
  `data/search.json` and docstring summaries `data/docs.json` it loads first,
  one file per module in `data/m/` read when a declaration is opened, and
  `reviews.json`.
- `scripts/batch.py` prepares a batch.
- `python3 -m unittest discover -s tests` runs the tests;
  `python3 tests/validate_site.py` checks the built page in a browser.
