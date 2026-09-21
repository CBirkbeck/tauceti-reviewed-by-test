# Reviewed-by for Tau Ceti — a test

A test of **review marks** on Tau Ceti declarations: who has checked which
definition, what they checked, and on which version. It is modelled on the
Linux kernel's `Reviewed-by:` trailers, and every mark is left from a browser,
without a pull request. Nothing here changes Tau Ceti: the page reads a sample
of its declarations, read-only, at one pinned commit.

**Page:** https://cbirkbeck.github.io/tauceti-reviewed-by-test/

## Marks

| Mark | Meaning |
|---|---|
| `Reviewed-by` | it is the intended mathematical notion |
| `Tested-by` | its examples and unit tests check out |
| `Acked-by` | happy with the design, without a full check |

A mark is pinned to a hash of the declaration's source (a definition whole, a
theorem by its statement). When the declaration changes, the mark stays but is
greyed: it applies to the earlier version until someone reviews the new one.
Marks by AI agents name the agent, model and session and are shown apart from
people's.

## Leaving a mark, from a browser

1. **Review this**, under any declaration on the page, opens the
   [Review a definition](.github/ISSUE_TEMPLATE/reviewed-by.yml) form with the
   declaration and its version filled in. Choose a mark, say what you checked,
   and submit.
2. The [Record review marks](.github/workflows/record.yml) workflow checks the
   declaration exists, appends the mark to
   [`reviews/records.jsonl`](reviews/records.jsonl) (committed directly: no pull
   request), answers on the issue, closes it and rebuilds the page.
3. To mark many at once, comment lines such as
   `Reviewed-by: TauCeti.IdealArithmeticFunction.vonMangoldt — what you checked`
   on [issue #1](../../issues/1). An AI agent adds
   `<!--reviewed-by:v1 {"agent": "<agent, model, session>"}-->` to its comment.

GitHub authenticates who submitted each mark.

## Batching into the code

[Batch marks into the code](.github/workflows/batch.yml) (run by hand here,
weekly in real use) collects the marks since the last batch into one pull
request, as the kernel's `b4 trailers -u` collects Reviewed-by replies. The pull
request shows two forms such a batch into Tau Ceti could take: a data file
(`snapshot/REVIEWED-BY.md`) and the declarations' docstrings with their marks
as trailer lines (`snapshot/docstrings.lean`). Its commit message ends in one
git trailer per mark.

## For other readers

The marks as data, for the Tau Ceti atlas or Tau Ceti's own documentation:
[`reviews.json`](https://cbirkbeck.github.io/tauceti-reviewed-by-test/reviews.json).

## Files

- `scripts/fetch_declarations.py` reads the modules in `data/modules.txt` at
  one Tau Ceti commit into `data/declarations.json`.
- `scripts/reviews.py` records marks from forms and comments.
- `scripts/build_site.py` builds the page and `reviews.json`.
- `scripts/batch.py` prepares a batch.
- `python3 -m unittest discover -s tests` runs the tests.
