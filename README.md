# Reviewed-by for Tau Ceti — a test

A test of **review marks** on Tau Ceti declarations: who has checked which
definition, what they checked, and on which version; and of the **tests** each
declaration passes. It is modelled on the
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

What a declaration is tested by is not a mark but a list of tests it passes
(below).

A mark is pinned to a hash of the declaration's source (a definition whole, a
theorem by its statement). When the declaration changes, the mark stays but is
greyed: it applies to the earlier version until someone reviews the new one.
Marks by AI agents name the agent, model and session and are shown apart from
people's. A person need not say why a declaration is right; an AI agent must
give its evidence.

However many marks a declaration collects, the page shows one line per kind of
mark, counting people apart from AI agents ("Reviewed-by · 12 people · 5 AI");
**Who** opens the full list, with each mark's date, version and evidence.

## Leaving a mark, from a browser

1. **Review this**, on any declaration the page opens, opens the
   [Review a definition](.github/ISSUE_TEMPLATE/reviewed-by.yml) form with the
   declaration and its version filled in. Submit it to say the declaration is
   the intended mathematical notion. Saying what you checked is optional for a
   person and required of an AI agent.
2. The [Record review marks](.github/workflows/record.yml) workflow checks the
   declaration exists, appends the mark to
   [`reviews/records.jsonl`](reviews/records.jsonl) (committed directly: no pull
   request), answers on the issue, closes it and rebuilds the page.
3. To mark many at once, comment lines such as
   `Reviewed-by: TauCeti.IdealArithmeticFunction.vonMangoldt — what you checked`
   on [issue #1](../../issues/1). An AI agent adds
   `<!--reviewed-by:v1 {"agent": "<agent, model, session>"}-->` to its comment.

GitHub authenticates who submitted each mark.

## Tests

What gives confidence that a definition or result is right is the tests it
passes, so the page lists them under **Tests**, counted
("Tested by · 7 unit tests · 2 key results · 1 suggested"), with **Which**
showing each test's statement and whether it passes. There are three kinds:

- **Unit tests**, found automatically: the `example`s in Tau Ceti whose
  statement names the declaration, resolved as Lean resolves names (through
  the namespaces around the example and those its file opens).
  `scripts/fetch_declarations.py` reads them with the declarations.
- **Key results**, mostly listed by AI agents: lemmas of Tau Ceti that pin the
  declaration down (a value, a degenerate case, agreement with a Mathlib
  notion), each with what it checks. List them with lines such as
  `Test: TauCeti.IdealArithmeticFunction.vonMangoldt — TauCeti.IdealArithmeticFunction.vonMangoldt_one — the unit ideal gets 0`
  in a comment on [issue #1](../../issues/1), where an AI agent adds its marker
  as for marks and must say what the test checks. They are recorded in
  [`reviews/tests.jsonl`](reviews/tests.jsonl).
- **Suggested tests**, from anyone: **Suggest a test** opens the
  [Suggest a test](.github/ISSUE_TEMPLATE/test.yml) form, whose issue stays
  open until the test is written in Tau Ceti (close it as completed then, or as
  not planned). Suggestions are recorded in
  [`reviews/suggestions.jsonl`](reviews/suggestions.jsonl).

A test passes while it is in Tau Ceti at the pinned commit without `sorry`;
since the page follows Tau Ceti's main branch daily, a test that is removed or
renamed shows as no longer found. Tests do not go stale as marks do: Lean
checks them again at every commit. The unit tests and API planned for the
atlas's roadmaps arrive the same way: once a planned definition is in Tau Ceti
with the `example`s of its suggested Lean file, those are its unit tests here.

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
(`snapshot/REVIEWED-BY.md`) and the declarations' docstrings
(`snapshot/docstrings.lean`). Both count the marks, so a docstring gains one
line per kind of mark however many there are, with a link to the page that says
who:

```lean
Reviewed-by: 12 people and 5 AI agents ([who](https://cbirkbeck.github.io/tauceti-reviewed-by-test/#d=TauCeti.X.y))
```

The full record stays in the ledger and in the git history: the batch's commit
message ends in one git trailer per new mark.

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
