# Standard Reviews Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the per-AI review texts on the Tau Ceti review site with one standard review per declaration, which AI agents approve or edit only after reviewing the Lean in depth, and move every existing AI-reviewed declaration onto it.

**Architecture:** The standard review is stored as ordinary `ltb-evidence/2` records (`review` and `comment`) that carry one new field, `standard`. There is no new record kind, so the pinned evidence-store check keeps passing. One module, `scripts/standard.py`, owns the format: the three parts, the version hash, the automatic check, and which version is current and who approved it. Our intake copy uses it to turn `Approve:`, `Write:`, `Edit:` and `Restore:` lines on the bulk issue into records. The site build uses it to write shard files, which the declaration page reads. Agents read and post through mathlib-quality's `review_site.py`, and Voyager and the red team switch to it. The migration writes the replacement reviews through the Message Batches API and pushes them as record files.

**Tech Stack:**
- Python 3.12: the standard library, evidence-core v0.16.1, evidence-store v0.7.2, and the `anthropic` SDK for the migration only;
- the plain-JavaScript front end;
- the Playwright browser check;
- GitHub Actions;
- one Lean 4 script, for Mathlib's source ranges.

**Spec:** `docs/superpowers/specs/2026-10-30-standard-reviews-design.md` (this repository). The section "Formats" below settles what the spec left to the builder; every task uses it.

## Global Constraints

- No new record kind. Records stay `ltb-evidence/2`, and evidence-store stays pinned at `v0.7.2`, evidence-core at `v0.16.1`. The new field `standard` is read only by our intake (`.github/actions/intake`, `scripts/`) and the site build, and the README says so.
- `standard.spec` is `"tauceti-standard/1"`.
- The three part headings are, exactly and in this order: `## What it says`, `## References and tests`, `## Lean subtleties`.
- The rubric's axes are `object`, `convention`, `edge-cases`, `junk`, `vacuous`, `choice`, `generality`, `naming` (the store's rubric, `ltb-rubric/1`). An AI's tick, write or edit carries all eight, each `checked` or `na`.
- Version hash: `sha256(normalize(text)).hexdigest()[:16]`, where `normalize` turns `\r\n` and `\r` into `\n`, strips trailing whitespace from each line, and strips leading and trailing newlines. It is the same function in both repositories, pinned by the test vector in Task 1 (`dd83c85a488e22c8`).
- History stays in the store and never reaches the page: no list of earlier texts, no per-AI text boxes, and no AI reasons shown on a declaration's page.
- A review is 150–400 words, guidance only (not enforced). References come only from recorded inputs or are verified with their theorem or section number.
- Exact model names everywhere: `Voyager, <model>`; `Codex, GPT-6 Astra`; the gate's fallback is `Claude Code, claude-fable-5-1`; the migration is `Tau Ceti review migration, claude-opus-5-5`.
- A GitHub comment holds at most 60,000 characters of ours (`COMMENT_CAP`), and a review block is never split across comments.
- The site deploys from `main` on push, so push only after the full unit suite and the browser check pass.
- Never change Tau Ceti. Never merge a PR (`gh pr merge` is the user's). Poll `gh` at most every 2–3 minutes. No bare @-mentions in commits, PRs or comments.
- Commits end with `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`. PR bodies end with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
- The answerer and the flow of noes are unchanged.

## Review Focus

These are the likeliest ways for real input to break the feature where no obvious test looks. Each line names the input and what a reasonable person expects; its test is added to the owning task.

1. **GitHub returns comment bodies with `\r\n` line endings and trailing spaces.** The intake must hash such a body to the same version the agent computed from its own file. Test: Task 3, `test_crlf_body_hashes_like_the_agent_did`. The shared vector is in Tasks 1 and 8.
2. **A review that holds its own code fence or a bare `~~~` line.** The text must reach the store whole, not cut at the inner fence. Test: Task 3, `test_a_block_keeps_inner_fences`.
3. **Agent-written text that holds raw HTML (`<img src=x onerror=…>`).** On the page it must show as text, never run. Test: Task 5, browser check `standard_review_html_is_inert`.
4. **An approval written from a stale page (the site lags the store by a build).** It must be refused, with the current version named, and record nothing. Test: Task 3, `test_approving_an_old_version_is_refused_with_the_current_one`.
5. **A batch of reviews longer than a GitHub comment.** `post` must split it into several comments, never inside a block, and refuse locally a single action over the cap. Test: Task 8, `test_post_splits_between_actions_never_inside_a_block`.

---

## Formats

### Records

**A version written by an AI.** Writing approves it, so it is an accept:

```json
{"schema": "ltb-evidence/2", "kind": "review", "verdict": "accept",
 "subject": "<the declaration's key>", "by": "<the agent>", "at": "…", "origin": "…",
 "text": "<the review: three parts>",
 "rubric": "ltb-rubric/1", "checked": {"object": "checked", "…": "…", "choice": "na"},
 "standard": {"spec": "tauceti-standard/1", "parent": "<version>", "note": "…", "dropped": [{"item": "…", "why": "…"}]},
 "links": {"supersedes": "<this reviewer's latest earlier accept of the declaration>"}}
```

- `parent`, `note` and `dropped` appear only on an edit.
- `links.supersedes` appears only when the same reviewer has an earlier accept, as evidence-store's `record_for` sets it.

**A version nobody approves by recording it.** This covers a maintainer's edit or restore, and a migration review held for the owner. It is a `comment`:
- it has the same `subject`, `text` and `standard`, with `restores: "<version>"` on a restore;
- `links.replies_to` is the id of the current version's record, or, for a first version, the declaration's latest review record;
- it has no `verdict`, `rubric` or `checked`.

**An approval** (a tick):

```json
{"schema": "ltb-evidence/2", "kind": "review", "verdict": "accept", "subject": "…", "by": "<the agent>",
 "at": "…", "origin": "…", "text": "Approves the standard review `<version>`.",
 "rubric": "ltb-rubric/1", "checked": {"…": "…"},
 "standard": {"spec": "tauceti-standard/1", "approves": "<version>"}, "links": {"supersedes": "…"}}
```

**An old-form AI yes** is any accept by an agent without `standard`, whatever its route. It counts as an approval of an earlier version.

A version is identified by `version_of(text)`. The hash is not stored; it is computed from the text wherever it is needed. So an approval made before the site shows a new text can still name it.

### The text

The text has three parts. Each part's heading is a line exactly as in Global Constraints, the parts come in that order, and none is empty: "None." is a valid Part 3.

In Part 2, each `- ` bullet is one item:
- **a test**, when it starts with a backticked Lean name: `` - `TauCeti.Foo.bar_two` — its value at 2 ``;
- **an example Check**, when it starts with `Check`, then its tag in asterisks and its place in backticks: ``- Check *test_two*, `TauCeti/Examples/Foo.lean:42` — passes``;
- **a reference**, anything else.

Prose may sit between the bullets.

### Lines on the bulk issue

The bulk issue is `meta.store.bulk`, issue #1. A field separator is a spaced em dash ` — ` or ` -- `, and the last field takes the rest of the line.

```
Approve: <decl> — <version> — <cells>
Write: <decl> — <cells>                          (an agent)    Write: <decl>                 (a maintainer)
Edit: <decl> — <parent> — <cells> — <note>       (an agent)    Edit: <decl> — <parent> — <note>   (a maintainer)
Dropped: <item> — <why>                          (between an Edit line and its block; any number)
Restore: <decl> — <earlier version> — <note>     (a maintainer only)
~~~review
<the text>
~~~
```

- **Cells.** A comma-separated list in which each axis appears once: `object`, `choice n/a`, `choice=na`, `choice=n/a` or `choice=checked`.
- **Versions.** A `<version>` or `<parent>` is at least 8 leading hex digits of the hash.
- **Who may post what.** A comment carrying an agent mark (or written by a Bot account) is the agent's. A comment without one is the account's own:
  - people may use only `Write`, `Edit` and `Restore`, and only if they are maintainers (`intake.is_maintainer`);
  - people say yes with the page's form.
- **The block.** A `~~~review` line opens the block. It closes at the **last** line that is exactly `~~~` before the next command line, or before the end of the comment. A command line is one starting with `Approve:`, `Write:`, `Edit:`, `Restore:`, `Reviewed-by:`, `Test:`, `Named:` or `Challenge:`.
- **Origin.** A command's origin is `<comment url>/line/<k>`, where k is its keyword line. This keeps the intake idempotent, as evidence-store's per-line refs are.
- **One change per declaration per comment.** A second Write or Edit of the same declaration in one comment is refused.

### Which version is current, and who approved it

- **Current version:** the latest version record of the declaration, by `(at, id)`, that is not withdrawn. A superseded accept is still a candidate. A withdrawn version undoes its edit.
- **Current approvers:**
  - which records count: AI accepts that are neither superseded nor withdrawn, and that apply to the declaration as it is now (evidence-core's status `applies`);
  - what they must approve: `standard.approves`, or the record's own text hash for a version, must equal the current version;
  - order: latest first.
- **Earlier:** the number of other AI accepts that are neither superseded nor withdrawn. This counts old-form yeses, approvals of other texts, and approvals of this text made for an earlier version of the declaration.
- **Current-ness:** the text is current when the current version record, or any current approver, applies. Otherwise the page marks it as written for an earlier version of the declaration.

---

## Part A: the review site (this repository)

Work on a branch. Rebase `design/standard-reviews` (the spec and this plan) onto `origin/main` and rename it `feature/standard-reviews`. Run the unit suite with `.venv/bin/python -m unittest discover -s tests`.

### Task 1: The format: parts, version, check, cells

**Files:**
- Create: `scripts/standard.py`
- Test: `tests/test_standard.py`

**Interfaces:**
- Produces:
  - `SPEC = "tauceti-standard/1"`, `HEADINGS: tuple[str, str, str]`
  - `normalize(text: str) -> str`, `version_of(text: str) -> str`
  - `parts(text: str) -> tuple[list[str] | None, list[str]]`: the three bodies, or the problems
  - `Items` (frozen dataclass): `references: list[str]`, `tests: list[str]` (Lean names), `checks: list[str]` (tags)
  - `items(text: str) -> Items`
  - `check(text: str, parent: str | None = None, dropped: list[tuple[str, str]] = (), exists: Callable[[str], bool] = lambda n: True, note: str | None = None) -> list[str]`: problems; empty means it passes
  - `cells(spec: str, axes: Sequence[str]) -> tuple[dict[str, str] | None, str]`: the cells, or why not
  - `kind_of(record: dict) -> str | None`: `"version"`, `"approval"` or None
  - `act(record: dict) -> str`: `"wrote"`, `"edited"`, `"restored"` or `"approved"`

- [ ] **Step 1: Write the failing tests.**

  ```python
  VECTOR = "\n## What it says\r\n`triple n` is $3n$.  \r\n\r\n## References and tests\n- Fixture documentation.\n\n## Lean subtleties\nNone.\n\n"

  def test_the_shared_vector(self):
      self.assertEqual(standard.version_of(VECTOR), "dd83c85a488e22c8")
      self.assertEqual(standard.version_of(standard.normalize(VECTOR)), "dd83c85a488e22c8")

  def test_three_parts_in_order_none_empty(self):            # check(GOOD) == []; a missing, reordered or empty part each named
  def test_items_tell_tests_checks_and_references_apart(self):
      it = standard.items(TEXT_WITH_ALL_THREE)
      self.assertEqual(it.tests, ["Fixture.triple_two"]); self.assertEqual(it.checks, ["test_two"])
      self.assertEqual(it.references, ["Fixture documentation, §1."])
  def test_an_edit_keeps_or_says_why(self):                  # dropping the test without a Dropped line → a problem naming `Fixture.triple_two`;
                                                             # with ("`Fixture.triple_two`", "it was renamed") → passes
  def test_a_reworded_reference_is_kept(self):               # "Fixture documentation, §1" → "Fixture documentation, section 1" passes (similarity ≥ 0.6)
  def test_an_edit_says_what_it_adds_and_changes_something(self):  # note None or "" → problem; text == parent → problem
  def test_a_test_must_exist(self):                          # exists=lambda n: False → problem naming the test
  def test_cells(self):                                      # all eight, with "choice n/a" → {..., "choice": "na"}; a missing axis, an unknown one,
                                                             # or "junk=unchecked" → (None, reason naming it)
  def test_kinds_and_acts(self):                             # accept+standard{text} → version/wrote; with parent → edited; comment with restores →
                                                             # restored; standard.approves → approval/approved; a plain accept → None
  ```

- [ ] **Step 2: Run them, and see them fail.** `.venv/bin/python -m unittest tests.test_standard -v`. Expected: an ImportError on `standard`.

- [ ] **Step 3: Implement `scripts/standard.py`.** Reference similarity is `difflib.SequenceMatcher` ratio ≥ 0.6, on text lowercased with only letters, digits and spaces kept. A parent item counts as named in a `Dropped:` line when:
  - for a test or a Check, the line's item holds its name or tag;
  - for a reference, the line's item reaches the same similarity.

- [ ] **Step 4: Run them, and see them pass.** Then run the whole suite.

- [ ] **Step 5: Commit.** `git commit -m "Standard reviews: the format, its version hash and the automatic check"`

### Task 2: Which version is current, and who approved it

**Files:**
- Modify: `scripts/standard.py`
- Test: `tests/test_standard.py`

**Interfaces:**
- Consumes: Task 1's `version_of` and `kind_of`.
- Produces:
  - `Seen` (frozen dataclass): `record: dict`, `applies: bool`, `withdrawn: bool`, `superseded: bool`
  - `current_version(seen: list[Seen]) -> Seen | None`
  - `summary(seen: list[Seen]) -> dict | None` returns `{"text", "version", "record", "approving": bool, "current": bool, "approvers": list[Seen], "earlier": int}`, following the rules in "Formats". An approver here is an agent's record only.

- [ ] **Step 1: Write the failing tests.** Records are built inline, with `at` values in order.

  ```python
  def test_the_latest_version_not_withdrawn_is_current(self):   # v1, v2 (edit), then v2 withdrawn → v1; v1 superseded but not withdrawn → still a candidate
  def test_approvers_are_this_texts_and_apply_now(self):        # v2 by A; approval of v2 by B; approval of v1 by C; old-form yes by D; stale approval of v2 by E
      s = standard.summary(seen)
      self.assertEqual([x.record["by"]["agent"]["tool"] for x in s["approvers"]], ["B", "A"])
      self.assertEqual(s["earlier"], 3)                         # C, D, E
  def test_a_comment_version_approves_nothing(self):            # held comment version only → approving False, approvers [], current True
  def test_out_of_date_when_nothing_about_it_applies(self):     # v1 and all approvals stale → current False
  def test_people_are_never_approvers(self):                    # a person's accept carrying standard text → not in approvers or earlier
  ```

- [ ] **Step 2: Run them, and see them fail.**
- [ ] **Step 3: Implement `current_version` and `summary`.**
- [ ] **Step 4: Run them, and see them pass.** Run the suite.
- [ ] **Step 5: Commit.** `git commit -m "Standard reviews: the current version, its approvers and those of earlier ones"`

### Task 3: The intake: approve, write, edit and restore on the bulk issue

**Files:**
- Create: `scripts/standard_intake.py`
- Modify: `scripts/evidence_intake.py` (install the hooks for every `intake` run, not only `--sweep-open`; extend `recorded()`)
- Test: `tests/test_standard_intake.py`; update `tests/test_evidence_intake.py`

**Interfaces:**
- Consumes:
  - Tasks 1 and 2;
  - evidence-store's `intake.Context`, `Outcome`, `record_for`, `bulk_answers`, `lookup`, `DatasetMissing`, `parse_agent_mark`, `author_of`, `is_maintainer`, `current_state`, `describe` and `BOTS`.
- Produces:
  - `commands(text: str) -> list[Command]`, where `Command` holds `line: int`, `keyword: str`, `fields: list[str]`, `dropped: list[tuple[str, str]]` and `block: str | None`
  - `process_bulk_comment(comment, issue, ctx, announce=True) -> Outcome`: the same signature as evidence-store's
  - `process(issue, comments, ctx, announce=True, events=()) -> Outcome`: bulk issues through ours, announcing a comment's refusals only when it is newer than the bot's latest comment on the issue; anything else goes to evidence-store's `process`
  - `process_issue(issue, ctx, announce=True)`: wraps evidence-store's, for the old-form notes below
  - `install() -> None`: sets `evidence_store.cli.process = process` and `evidence_store.intake.process_issue = process_issue`
  - `APPROVE_INSTEAD: str`, a constant (below)

Old forms keep working, and their replies change:

- **A bare `Reviewed-by:` line from an agent.** It is still refused. The reason "a review by an agent needs its text: why" becomes:

  > an AI agent's yes is now an approval of the standard review: `Approve: <decl> — <version> — <cells>`, see AI-REVIEWS.md.

  The same rewrite applies to the review form's refusal in `process_issue`.
- **An agent's yes with reasons** (bulk line, form or `submit`). It is recorded as today, and the reply adds:

  > Recorded as an AI agent's yes of the earlier form: it counts as an approval of an earlier version of the standard review. ` + APPROVE_INSTEAD

  where `APPROVE_INSTEAD = "AI agents now approve or edit the declaration's standard review: AI-REVIEWS.md (https://github.com/<repo>/blob/main/AI-REVIEWS.md)."`

  `recorded()` in `evidence_intake.py` gives the same note.

- [ ] **Step 1: Write the failing tests.**
  - **Setup.** A temporary store from `evidence/store.json`, and the fixture dataset (`tests/fixtures/dataset-b`).
  - **Context:** `Context("o/r", store, lambda c: ds, frozenset({"boss"}))`.
  - **Comments** are dicts with `user`, `body`, `created_at`, `html_url` and `author_association`.

  ```python
  def test_write_then_approve_in_order(self):          # agent A writes (all cells); agent B's later comment approves version_of(text)
      # → 2 records; the version: accept with checked & standard.spec; the approval: standard.approves == version; reply lists both
  def test_approving_an_old_version_is_refused_with_the_current_one(self):   # Review Focus 4
      # A writes v1, A edits to v2, B approves v1 → nothing recorded for B; the reply names version_of(v2)
  def test_a_write_where_one_exists_is_refused(self):
  def test_an_edit_failing_the_check_is_refused_with_why(self):   # drops a test without a Dropped line
  def test_a_tick_needs_every_cell(self):              # 7 axes → refused, naming the missing one
  def test_people_cannot_approve_and_only_maintainers_edit(self):  # unmarked comment by "alice": Approve refused, Edit refused;
                                                                   # by "boss": Edit → a comment record replying to the current version's record
  def test_restore_puts_back_an_earlier_text(self):    # boss restores v1 → comment, text == v1, standard.restores == version_of(v1), parent == v2's
  def test_crlf_body_hashes_like_the_agent_did(self):  # Review Focus 1: body with \r\n and trailing spaces → current version == version_of(file text)
  def test_a_block_keeps_inner_fences(self):           # Review Focus 2: a ```lean fence and a bare ~~~ line inside → stored text keeps both
  def test_lines_inside_a_block_are_not_commands(self):    # a "Test: X — Y — Z" line inside the block records no test
  def test_running_twice_records_once(self):           # process the same comment twice → the store grows once
  def test_refusals_are_said_once(self):               # comment c1 with a bad line, then a bot reply, then comment c2:
      # processing both announces only c2's refusals
  def test_old_forms_say_what_to_do_now(self):         # bare agent Reviewed-by → refusal text contains "Approve:";
      # agent Reviewed-by with reasons → recorded, reply contains APPROVE_INSTEAD
  def test_install_covers_every_intake_run(self):      # evidence_intake.main(["intake", ..., "--sweep-days", "14"]) with GitHub faked
      # → ours handled the bulk issue (an Approve line is recorded)
  ```

- [ ] **Step 2: Run them, and see them fail.** `.venv/bin/python -m unittest tests.test_standard_intake -v`
- [ ] **Step 3: Implement `scripts/standard_intake.py`, and call `install()` in `evidence_intake.main` before any `intake` command.**
  - The current version is found from `ctx.store.records` with `subject.name == decl`, and `withdrawn` from `intake.current_state(...) == "withdrawn"`.
  - Each record is checked with `rec.validate`, then added with `ctx.store.add([r])` as soon as it is made. This way later lines and comments see it, as evidence-store's bulk handler does.
  - The Edit check's `exists` is `lambda n: n in ds.by_name`.
- [ ] **Step 4: Run them, and see them pass.** Then the whole suite, including `tests/test_evidence_intake.py`.
- [ ] **Step 5: Commit.** `git commit -m "Intake: approvals, writes, edits and restores of the standard review; old forms say what to do now"`

### Task 4: The site build: standard shards and one-line views

**Files:**
- Modify: `scripts/site_data.py`, `scripts/build_site.py`, `tests/fixture_site.py`
- Test: `tests/test_build_site.py`

**Interfaces:**
- Consumes: Task 2's `Seen` and `summary`; Task 1's `kind_of` and `act`.
- Produces:
  - **`data/standard/<k>.json`** for every `k` in `range(256)` (`{}` where empty), keyed by `fnv_shard(name, 256)`. Each maps a name to:

    ```json
    {"text": "…", "version": "…", "at": "…", "by": "<views.by_view>", "approving": true, "url": "<origin_url>",
     "current": true, "approvers": [{"by": "…", "at": "…", "checked": {"…": "…"}, "url": "…"}], "earlier": 0}
    ```

    It covers every declaration the site asks about that has a version, including those outside the library.
  - `meta.json` gains `shards.standard = 256`.
  - In `entry()`, `upstream()` and `activity()`, a standard record's view carries `"std": act(r)` and `"text": ""`. The text lives only in the shard.
  - `Site.standard_shards() -> dict[int, dict[str, dict]]`, and `STANDARD_SHARDS = 256`.

Fixture additions in `extra_records`. The agents are `AGENT`, `ASTRA`, a new `VOYAGER` (`{"tool": "Voyager", "model": "claude-fable-5-1"}`) and a new `MIGRATION` (`{"tool": "Tau Ceti review migration", "model": "claude-opus-5-5"}`):
- `Fixture.triple`:
  - V1 by ASTRA at 2026-10-25;
  - V2 (`TRIPLE_V2`), an edit by AGENT at 2026-10-26, with `links.supersedes` on AGENT's 10-22 yes. Its Part 3 quotes `<img src=x onerror="window.pwned=1">` as text, for Task 5's check that raw HTML stays inert;
  - VOYAGER's approval of V2 at 2026-10-27, its cells with `choice: na`.
- `Fixture.double`: a version by AGENT whose subject is the stale subject of the fixture's existing `Fixture.double` record.
- `Fixture.triple_pos`: a held comment version by MIGRATION, replying to ASTRA's yes.
- `Int`: a version by AGENT.

- [ ] **Step 1: Write the failing tests.**

  ```python
  def std(name): return data(f"standard/{common.fnv_shard(name, 256)}.json")[name]

  def test_the_current_text_and_its_approvers(self):
      s = std("Fixture.triple")
      self.assertEqual(s["version"], standard.version_of(fixture_site.TRIPLE_V2))
      self.assertEqual([a["by"]["agent"]["model"] for a in s["approvers"]], ["claude-fable-5-1", "claude-opus-5-5"])
      self.assertEqual((s["earlier"], s["current"], s["approving"]), (1, True, True))
      self.assertEqual(s["approvers"][0]["checked"]["choice"], "na")
  def test_out_of_date_and_held(self):            # std("Fixture.double")["current"] is False; std("Fixture.triple_pos") approving False, approvers [], earlier 1
  def test_outside_the_library_too(self):         # "Int" in its shard
  def test_every_shard_is_written(self):          # 256 files; meta["shards"]["standard"] == 256
  def test_history_stays_off_the_page(self):      # entry("Fixture.triple")["records"]: standard views have text "" and std in {"wrote","edited","approved"};
                                                  # same in activity.json "recent"
  ```

  Update `test_reviewed` to the new fixture. Each value follows from the "Formats" rules and is checked by hand once:
  - `Fixture.triple` yes is `[1, 3]`;
  - models are `{"claude-opus-5-5": [1,0,0], "GPT-6 Astra": [1,0,0], "claude-fable-5-1": [1,0,0]}`;
  - `Fixture.double` earlier is `[1, 1]`, and `Int` yes is `[1, 1]`;
  - `counts.accepts` is `{"people": 6, "ai": 5}`.
- [ ] **Step 2: Run them, and see them fail.** `.venv/bin/python -m unittest tests.test_build_site -v`
- [ ] **Step 3: Implement.** Build `Seen` from `self.ev.records_on(name)`:
  - `applies` comes from the record's status. A comment gets `st.classify(r["subject"], ds).applies`, because evidence-core marks every comment current.
  - `withdrawn` is `ev.state(id) == "withdrawn"`, and `superseded` is `id in ev.superseded_by`.
- [ ] **Step 4: Run them, and see them pass.** Run the whole suite.
- [ ] **Step 5: Commit.** `git commit -m "Site build: the standard review of each declaration, sharded; history kept off the page"`

### Task 5: The page: the review box, Activity, copy instructions, How to review

**Files:**
- Modify: `web/data.js`, `web/app.js`, `web/style.css`
- Test: `tests/validate_site.py`

**Interfaces:**
- Consumes: Task 4's shards and `std` views.
- Produces: `TauData.standard(name) -> Promise<view | null>`.

The review box. Its new copy is exact, because the browser check reads it:
- **Order.** The question and its actions, the how-to line and the AI offer stay as they are. Then come the sub heading **`Standard review`**, then **`Answers`**, then What could be better and Tests, as today.
- **With a version:**
  - the text, rendered with `md()` inside `div.standard`;
  - the line `Version <first 8 hex> · <date> · <markWho(by)>`;
  - the line `Approved by` followed by each approver's mark: a blue tick plus `markWho`, whose `title` is `Checked: <axes> · Not applicable: <axes> · <date>`, leaving out an empty half.
- **Earlier approvals.** Then ` · 1 approved an earlier version` or ` · N approved earlier versions`.
- **No approvers:** `Not yet approved by an AI agent.`
- **When `current` is false:** `Written for an earlier version of this declaration, which has changed since.`
- **Without a version:** `No standard review yet.` and, if AI agents said yes, `N AI agents said yes in the earlier form of review.`
- **`Answers`.** As today's `answers()`, with two changes:
  - the yes marks and the yes tally are **people's only**;
  - the noes (people's and AI agents') are unchanged.
- **Activity's Latest.** A view with `std` is one line: `<who> <wrote|edited|restored|approved> the standard review`, with the declaration link and no body.
- **Copy instructions for your AI.** After the AI-REVIEWS.md line, add `Read its Lean in depth and look for errors first; then approve, edit or write its standard review.` Then either `Its standard review is version <full hash>; its text is under its name in <site url>data/standard/<k>.json.` or `It has no standard review yet.` The exact-model line stays. An agent needs the raw Markdown to edit, and the page shows it rendered.
- **How to review, "AI agents".** It describes reviewing the Lean first and approving, editing or writing, with this example:

  ```
  <!-- agent: tool=Claude Code; model=claude-opus-5-5 -->
  Approve: TauCeti.Foo.bar — dd83c85a488e22c8 — object, convention, edge-cases, junk, vacuous, choice n/a, generality, naming
  ```

  It drops the `Reviewed-by:` example.

- [ ] **Step 1: Write the failing browser checks.** Update `review` and `other_pages` to the new layout, and add these:

  ```python
  @check
  def standard_review(browser, url, errors):
      page = visit(browser, url, "#/d/Fixture.triple", errors); box = page.locator(".review")
      expect([h.inner_text() for h in box.locator(".standard h2").all()] == ["What it says", "References and tests", "Lean subtleties"], "the three parts")
      marks = box.locator(".approvers .mark.agent")
      expect(marks.count() == 2 and "1 approved an earlier version" in box.locator(".approvers").inner_text(), "who approved this text, and how many an earlier one")
      expect("Not applicable: choice" in marks.first.get_attribute("title"), "what each approver checked, on hover")
      expect(box.locator(".answers-list .mark.agent").count() == 0 and box.locator(".answers-list .mark.person").count() == 1, "people's yeses only")
      # Fixture.double: "Written for an earlier version of this declaration"; Fixture.triple_pos: "Not yet approved by an AI agent.";
      # #/d/Int shows its standard review; #/d/Fixture.one: "No standard review yet."
  @check
  def standard_review_html_is_inert(browser, url, errors):   # Review Focus 3: the fixture's V2 holds `<img src=x onerror="window.pwned=1">`
      page = visit(browser, url, "#/d/Fixture.triple", errors)
      expect(page.evaluate("window.pwned") is None and "<img" in page.locator(".review .standard").inner_text(), "raw HTML stays text")
  ```

  Keep the colour check: the person's tick green; the approver's tick and AI mark blue. Add checks for the copy instructions' text with the version, and for Activity's one-line entry.
- [ ] **Step 2: Run them, and see them fail.** `.venv/bin/python tests/validate_site.py --only standard_review,standard_review_html_is_inert,review,other_pages`
- [ ] **Step 3: Implement.** In `VIEWS.decl`, `await TauData.standard(name)` beside the records, and pass it to `reviewCard(meta, name, read, records, tests, word, std)` and `aiOffer(meta, name, from, std)`.
- [ ] **Step 4: Run them, and see them pass.** Run the full browser check (`.venv/bin/python tests/validate_site.py`) and the unit suite.
- [ ] **Step 5: Commit.** `git commit -m "Page: one standard review per declaration, its approvers on hover, people's answers apart"`

### Task 6: AI-REVIEWS.md and the README

**Files:**
- Modify: `AI-REVIEWS.md`, `README.md`
- Test: `tests/test_standard_intake.py` (the docs' examples parse)

**Interfaces:**
- Produces: the section of AI-REVIEWS.md between `<!-- standard-review:begin -->` and `<!-- standard-review:end -->`. It is the single definition of a good standard review. The migration's prompt (Task 13) and `review_site.py guide`/`astra-question` (Tasks 8–9) read it, so it must stand alone.

AI-REVIEWS.md is rewritten in this order:
1. **The question.** It is unchanged: is it correctly stated?
2. **The standard review,** between the markers: the audience; the three parts and what each holds (the spec's "The standard review"); the format above; the anti-goals as rules:
   - no invented references, and every theorem or section number from a source or checked;
   - Part 1 follows the signature hypothesis by hypothesis, as the docs print it;
   - Lean jargon is explained;
   - no edits that only reword;
   - 150–400 words.
3. **Steps:**
   - read the Lean at the site's commit (statement, value, what it rests on);
   - run the eight checks;
   - on an error, file a no (as today) and approve nothing;
   - otherwise read the standard review, then approve it if it is right and complete, edit it if something is missing or unclear, or write one if there is none. The page shows its version, and its raw text is under its name in `data/standard/<k>.json`, the address the copy instructions give; `review_site.py standard` (mathlib-quality ≥ 0.82.0) prints both. The doc must work without mathlib-quality, since it goes live before Part B merges;
   - run the roadmap's Checks as today's step 4, now recorded in Part 2.
4. **Filing.** The lines on issue #1 (the "Lines on the bulk issue" format), `review_site.py post`, the version hash shown on the page, and the cells.
5. **The rules,** Mathlib's declarations, Voyager and the red team (approve, edit, write), and the old forms (recorded as approvals of an earlier version).

In the README:
- Reviewing: many yeses at once becomes approvals.
- What the site shows: the review box.
- Files: the new scripts.
- A paragraph **"The standard review in the store"**: the field `standard`, read only by our intake and site build, with no new record kind, and the pinned versions unchanged.

- [ ] **Step 1: Write the failing test** `test_the_docs_examples_parse`. Every `Approve:`/`Write:`/`Edit:` example in AI-REVIEWS.md and the README must parse with `standard_intake.commands`. Every `~~~review` example block in AI-REVIEWS.md must pass `standard.check`. The markers must be present.
- [ ] **Step 2: Run it, and see it fail.**
- [ ] **Step 3: Rewrite AI-REVIEWS.md and the README.**
- [ ] **Step 4: Run it, and see it pass.** Run the suite.
- [ ] **Step 5: Commit.** `git commit -m "AI-REVIEWS.md: review the Lean first, then approve, edit or write the standard review"`

### Task 7: Ship the site

- [ ] **Step 1: Check before pushing.**
  - Run the full unit suite and the browser check.
  - Build against the pinned dataset (README, "Working on it"): `scripts/build_site.py --dataset … --source … --out _site`.
  - Run `tests/validate_site.py --site _site --smoke`. It must PASS, and the build must stay under its budget.
- [ ] **Step 2: Push.** Merge `feature/standard-reviews` into `main` (fast-forward) and push.
- [ ] **Step 3: Watch the deploy.** Watch Pages (polling every ≥ 2 minutes), then run `tests/validate_site.py --url https://cbirkbeck.github.io/tauceti-reviewed-by-test/ --smoke`. Check that `data/meta.json` has `shards.standard == 256`.
- [ ] **Step 4: Watch the intake.** Check that the next run on issue #1 passes, in the action log. No test records go into the live store: it is append-only.

---

## Part B: mathlib-quality (`CBirkbeck/mathlib-quality`, a PR the user merges)

Branch `feat/standard-reviews` from `origin/main`. If PR #39 (v0.81.2) is still open, rebase on it once it merges. Tests: `python3 -m unittest discover -s tests`, which creates `tests/`. Import the script with `sys.path.insert(0, "scripts")`, and fake the site by patching `review_site.get`.

### Task 8: `review_site.py`: standard, hash, guide, post

**Files:**
- Modify: `scripts/review_site.py`
- Create: `tests/test_review_site.py`

**Interfaces:**
- Produces subcommands:
  - `standard NAME... [--json]`: per name, the current text, version, approvers with cells, earlier count and current-ness, read from `standard/<fnv(name, shards.standard)>.json`. It also prints the reasons of old-form AI yeses recorded since the current version (from the record views `answers_on` already reads) and the open noes. `--json` prints `{name: {"version": …|null, "text": …, "unfolded": [...], "noes": [...]}}`. It refuses with exit 2 when `meta.shards.standard` is missing ("the site does not show standard reviews yet").
  - `hash FILE`: prints `version_of(text)`.
  - `guide`: prints the marked section of AI-REVIEWS.md, from `https://raw.githubusercontent.com/<REPO>/main/AI-REVIEWS.md`.
  - `post ACTIONS.jsonl --agent A --commit SHA [--note TEXT] [--drafts FILE] [--dry-run]`. This one replaces `yes`, which is removed.
- **Action lines:**

  ```json
  {"approve": "<decl>", "version": "<hash>", "cells": {"…": "…"}}
  {"write": "<decl>", "cells": {"…": "…"}, "text": "…"}
  {"edit": "<decl>", "parent": "<hash>", "cells": {"…": "…"}, "note": "…", "dropped": [{"item": "…", "why": "…"}], "text": "…"}
  ```

- **`post` checks locally, then posts the bulk lines of "Formats".** The local checks:
  - the names are on the site;
  - all eight cells are present, each `checked` or `na`;
  - the three headings are present, in order;
  - a version or parent is the site's current one, or the hash of that declaration's text in `--drafts` (a JSONL of actions posted just before, for approvals of drafts the site does not show yet).

  Each comment starts with `agent_mark(A)`, then the note line, by default `Reviews of declarations checked at Tau Ceti <commit12>.` `normalize` and `version_of` are copied from the site's `scripts/standard.py`.

- [ ] **Step 1: Write the failing tests.**

  ```python
  def test_the_shared_vector(self): self.assertEqual(review_site.version_of(VECTOR), "dd83c85a488e22c8")   # same VECTOR as the site's Task 1
  def test_post_formats_the_bulk_lines(self):         # one approve, one write, one edit with dropped → exact lines, the block fenced ~~~review … ~~~
  def test_post_refuses_a_stale_version(self):        # fake site current "aaaa…", action version "bbbb…" → exit 1, nothing posted
  def test_post_accepts_a_drafts_version(self):       # --drafts holds a write of that decl → its hash accepted
  def test_post_refuses_incomplete_cells_or_parts(self):
  def test_post_splits_between_actions_never_inside_a_block(self):   # Review Focus 5: 30 writes of 3,000 chars → ≥ 2 comments, each ≤ COMMENT_CAP,
                                                                     # each block whole; one action > COMMENT_CAP → refused
  def test_standard_needs_a_site_that_shows_it(self): # meta without shards.standard → exit 2
  def test_yes_is_gone(self):                         # main(["yes", ...]) → argparse error
  ```

- [ ] **Step 2: Run them, and see them fail.**
- [ ] **Step 3: Implement.** Update the module docstring's usage block.
- [ ] **Step 4: Run them, and see them pass.**
- [ ] **Step 5: Commit.** `git commit -m "review_site.py: read, hash and post approvals, writes and edits of the standard review"`

### Task 9: `review_site.py`: Astra's review question and answer

**Files:**
- Modify: `scripts/review_site.py`
- Test: `tests/test_review_site.py`

**Interfaces:**
- Consumes: Task 8's site reads and `version_of`.
- Produces two subcommands.
  - `astra-question NAME... --tauceti CHECKOUT [--drafts FILE] --out FILE`. At most 12 names per file, else refused. It writes three things:
    - the instructions: Astra looks for errors first and fills the eight cells, and only then approves or edits;
    - the marked AI-REVIEWS.md section (`guide`);
    - per name, numbered: its kind; its Lean source at the site's commit (`git -C CHECKOUT show <commit>:<path>`, the entry's `line` range); up to 12 statements it rests on (the node's `m` ids, then their entries' `sig`); and the current standard review with its version, taken from `--drafts` first, else from the site.
  - `astra-answer ANSWER --question QFILE --out ACTIONS.jsonl --noes NOES.jsonl`. It parses each item's block (below):
    - APPROVE and EDIT with complete cells go to `--out` as Task 8 actions;
    - NO goes to `--noes` as `{"decl", "category", "why"}`;
    - an item with missing or inconsistent cells (an `ERROR` cell under APPROVE), or one it cannot parse, is printed as "not filed: <name>: <why>".

The answer format, which the instructions ask for, per item:

```
### <n>. <name>
CELLS: object=checked, convention=checked, edge-cases=checked, junk=checked, vacuous=checked, choice=n/a, generality=checked, naming=checked
VERDICT: APPROVE            (or EDIT, or NO)
NOTE: <what the edit adds>                      (EDIT)
DROPPED: <item> — <why>                         (EDIT, any number)
~~~review
<the full new text>                             (EDIT)
~~~
CATEGORY: <axis>   WHY: <the error>             (NO)
```

- [ ] **Step 1: Write the failing tests.** Use a temporary git checkout with one `.lean` file and a fake site.

  ```python
  def test_question_holds_source_rests_on_and_review(self):   # the source lines, the rested-on signatures, the review and its version, the guide text
  def test_question_uses_a_draft_over_the_site(self):
  def test_question_refuses_more_than_12(self):
  def test_answer_to_actions_and_noes(self):                  # APPROVE → approve action with version; EDIT → edit with parent, note, dropped, text;
                                                              # NO → noes; APPROVE with a missing cell → "not filed"
  ```

- [ ] **Step 2: Run them, and see them fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run them, and see them pass.**
- [ ] **Step 5: Commit.** `git commit -m "review_site.py: Astra's review question and its answer as approvals, edits and noes"`

### Task 10: Voyager, the red team, the version, the PR

**Files:**
- Modify:
  - `skills/voyager/SKILL.md` (§4 one paragraph, and §8 rewritten) and `skills/voyager/HANDOVER.md` (one line);
  - `commands/redteam.md` (R0, and R6 steps 8–10) and `skills/mathlib-quality/references/tauceti-redteam.md` (its section on yes reasons);
  - `scripts/redteam.py` (`yes_problems`, `cmd_reviews`, a new `yes` subcommand);
  - the version: 0.81.x becomes **0.82.0** wherever it appears (`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `CLAUDE.md`, the README's changelog).
- Create: `tests/test_redteam_reviews.py`

**Voyager §8 must say,** in the skill's own voice:
1. **What to cover.** Every candidate whose statement it compared, announced or not.
2. **Review first.** Review the Lean in depth at the window's `docgen` commit: the statement, the value, and what it rests on. Run the eight checks. On an error, file a no (today's `no`) and approve nothing.
3. **Then the standard review.** Read it with `python3 "$RS" standard <names>`. If there is none, draft one following `python3 "$RS" guide`. It may draft in subagents of 10, from the full-statement comparison and the Lean source, using only references from that comparison, the docstring or the roadmap. If there is one, approve it if it is right and complete, or edit it.
4. **Voyager's actions.** Write them to `voyager.jsonl`, then `python3 "$RS" post voyager.jsonl --agent "Voyager, <model>" --commit <docgen sha> --note "Checked in Voyager's full-statement test for the update of <date>: <post link>."`
5. **Astra's review.**
   - Build the questions: `python3 "$RS" astra-question <≤12 names> --tauceti <checkout> --drafts voyager.jsonl --out q-<k>.txt`.
   - Ask, **after the significance gate and one at a time**: `~/.claude3/voyager/gate.sh ask q-<k>.txt a-<k>.md`. It handles `GATE_PENDING` as in §4. gate.sh stops a call for a different question, so the calls never run concurrently.
   - Read the answers: `python3 "$RS" astra-answer a-<k>.md --question q-<k>.txt --out astra-<k>.jsonl --noes noes-<k>.jsonl`.
   - Post under the model that served the call: `GATE_SERVED_BY=.codex*` is `Codex, GPT-6 Astra`, and `claude-fallback` is `Claude Code, claude-fable-5-1`. Use `post astra-<k>.jsonl --drafts voyager.jsonl --agent "<that>" …`, and one `no` per item in the noes file, under the same agent.
   - Items "not filed" are named in the run log. An answer without the cells is never filed as an approval.
6. **Order and failure.** Do this after the post and the state DM, as now. A failure is logged, and it never touches the post.

**Voyager §4:** one paragraph saying the review calls of §8 follow the gate call, never alongside it.

**The red team.** R6 step 8 becomes "Review on the site". For each declaration whose correctness checks passed (today's rule), record the site's eight cells and one decision against the current text (`python3 "$RS" standard --json`). The audit's `yes` becomes:

```json
{"<full name>": {"cells": {"…": "…"}, "approve": "<version>"}
                | {"cells": {"…": "…"}, "write": "<text>"}
                | {"cells": {"…": "…"}, "edit": "<parent>", "note": "…", "dropped": [], "text": "…"}}
```

- **`yes_problems`** refuses:
  - missing or incomplete cells;
  - none, or more than one, of `approve`, `write` and `edit`;
  - a text without the three headings;
  - and everything it refuses today.
- **`cmd_reviews`** keeps the gate "the site shows the file as audited". It then:
  - reads the current versions (`review_site.py standard --json`) and posts with `review_site.py post --agent "Tau Ceti red team, <model>, session <owner>" --commit <site>`;
  - gives an entry whose version or parent is no longer current, or a write where one exists now, the state `re-review` in the reviews ledger, and prints its names;
  - drops an audit row of the old shape (reasons strings) with `why: "the site takes standard-review approvals now"`.
- **`python3 "$RT" yes @update.json`** records replacement entries for a file's audit (`{"file": …, "yes": {...}}`), validated as above, for R0's re-reviews.

- [ ] **Step 1: Write the failing tests** in `tests/test_redteam_reviews.py`. Use a temporary ledger, patch `run` for `review_site.py`, and a fake site.

  ```python
  def test_yes_needs_cells_and_one_decision(self):
  def test_reviews_posts_actions_for_a_file_the_site_shows(self):   # the actions file passed to post holds the approve/edit/write lines
  def test_a_changed_review_waits_for_re_review(self):              # site current ≠ audit's version → state "re-review", nothing posted for it
  def test_old_shaped_rows_are_dropped_with_why(self):
  def test_yes_command_replaces_entries(self):
  ```

- [ ] **Step 2: Run them, and see them fail.**
- [ ] **Step 3: Implement `redteam.py`, then rewrite the skill and command texts.** Run `python3 scripts/redteam.py --help` and `python3 scripts/review_site.py --help`: both must print cleanly.
- [ ] **Step 4: Run all tests, and see them pass.** Run `bash scripts/style_checker.sh` if the repository's CI runs it.
- [ ] **Step 5: Commit, push, and open the PR.** Title: `feat(voyager,redteam): approve, edit or write the standard review on the Tau Ceti review site (v0.82.0)`, with a short body ending in the Claude Code line.
  - Ask the user to merge.
  - After the merge, list the server's config dirs (`ssh ovh 'ls -d ~/.claude*'`) and give the user one `! ssh ovh …` line that runs `claude plugin marketplace update` and `claude plugin update` for each.
  - Voyager reads the skill from its clone at `origin/main`, so it changes on its next run.

---

## Part C: records and the migration (this repository)

### Task 11: Voyager's 86 refused yeses of 2026-10-30

**Files:**
- Create: `scripts/migrate_records.py` (subcommand `voyager-refused`)
- Test: `tests/test_migrate.py`
- Output: `evidence/records/voyager-2026-10-30.jsonl`

**Interfaces:**
- Produces `migrate_records.py voyager-refused TSV --dataset DIR --store evidence --comment-url URL --at TIME --session S --out FILE`.
  - The TSV's columns are `<line k>\t<decl>\t<reasons>`.
  - Each record is an accept by `{"kind": "agent", "identity": {"kind": "github", "id": "CBirkbeck"}, "involvement": "unknown", "agent": {"tool": "Voyager", "model": "claude-fable-5-1", "session": S}}`.
  - Its `origin` is `{"kind": "comment", "ref": "<URL>/line/<k>"}`, and its `at` is TIME.
  - Its subject is from the dataset of the commit Voyager checked (df319cee080d…). The text is the reasons, then ` (Reasons transcribed from Voyager's run notes; the line it posted had none.)`
  - It has no `standard`.

- [ ] **Step 1: Write the failing test.** `test_voyager_refused_records_match_the_lines`, on the fixture: the origin refs, `at`, `by`, the subject commit, and that each passes `rec.validate`.
- [ ] **Step 2: Run it, and see it fail.**
- [ ] **Step 3: Implement it, then rebuild the reasons.**
  - Read comment 6529887317 on issue #1 for the lines and their numbers.
  - On the server (read only), read `~/voyager/notes/2026-10-30-1603-run.md`, `~/voyager/work/candidate-details.md` and the 10-30 gate question and answer.
  - Write one line per declaration to the TSV: `Correctly stated: <what it asserts> (<the source it was compared with>); compared in Voyager's full-statement test.` Use only what the notes say.
  - If the dataset `dataset-df319cee080d` was pruned, use the oldest dataset that has the declaration with the same meaning hash, and say so in the commit message.
- [ ] **Step 4: Run the test and the suite.** Generate the file, then check it with `.venv/bin/evidence-store check --store evidence --base origin/main --author CBirkbeck`. The output must end in `ok`.
- [ ] **Step 5: Commit and push to `main`.**
  - Verify locally that the lines are now recorded: fetch comment 6529887317 (`gh api`), run `standard_intake.process_bulk_comment` on it against the updated store, and check that it records nothing new and refuses nothing.
  - Check the site shows Voyager's yes on two of the declarations.

### Task 12: The migration's inputs

**Files:**
- Create: `scripts/migrate_inputs.py`, `scripts/migrate_ranges.lean`
- Modify: `scripts/site_data.py` (extract `binder_groups(name, sig) -> list[tuple[str, str]]` from `brief()`, unchanged in behaviour)
- Test: `tests/test_migrate.py`

**Interfaces:**
- Produces `migrate_inputs.py --dataset DIR --source TAUCETI --store evidence --roadmap ROADMAP --ranges RANGES.jsonl --out BUNDLES.jsonl [--only N,…]`.
- **Scope.** Every declaration with an AI accept that is not withdrawn, and no standard version yet, ordered as follows: Voyager's named results first, newest announcement first; then by roadmap (name, then declaration); Mathlib's last.
- One JSON object per declaration:

  ```json
  {"decl": "…", "kind": "theorem", "package": "TauCeti", "commit": "…", "signature": "<docs header>", "docstring": "…",
   "source": "<statement span>", "value": "<value span, definitions only>",
   "rests_on": [{"name": "…", "signature": "…", "doc": "<first sentence>"}],
   "reviews": [{"by": "<label>", "verdict": "…", "state": "…", "text": "…", "checked": {"…": "…"}, "at": "…"}],
   "tests": [{"test": "…", "text": "…", "result": "…", "statement": "…"}],
   "checks": [{"tag": "…", "path": "…", "line": 42, "result": "…"}],
   "named": {"name": "…", "text": "…"},
   "roadmap": {"name": "…", "path": "…", "block": "…"},
   "open_no": false}
  ```

  `named` and `roadmap` are null when absent.
- **Rests on:** `Site.above(d)`, at most 12. For a declaration outside the library it is empty, as the site does not follow what those rest on.
- **Checks:** each `*tag*` that a review text cites with a `….lean#L<n>` link, kept only when the tag is found in that file at the site's commit (the line stored is where it is now).
- **The roadmap block:** `git -C ROADMAP grep -n -F <decl>`. The block runs from the nearest heading above to the next heading of the same or a higher level, capped at 4,000 characters.
- **Mathlib's source and docstring:** from RANGES. `scripts/migrate_ranges.lean` reads names on stdin and prints `{"name", "module", "file", "start", "end", "doc"}` per name, using `Lean.findDeclarationRanges?` and `Lean.findDocString?`. Run it from a Tau Ceti checkout at the site's commit, with `lake exe cache get` done: `lake env lean --run …/migrate_ranges.lean < names.txt`. The source lines are read from `.lake/packages/mathlib/<file>`.

- [ ] **Step 1: Write the failing tests,** on the fixture (dataset-b, source-b, a temporary roadmap repo with one heading block that names `Fixture.triple`):

  ```python
  def test_bundle_of_a_definition(self):     # signature, docstring, value, rests_on names, reviews with texts, tests with statements, roadmap block
  def test_scope_and_order(self):            # declarations with an AI accept only; named first; one with a standard version left out
  def test_checks_are_verified(self):        # a cited tag present in source-b is kept with its current line; an absent one is dropped
  def test_binder_groups_unchanged(self):    # brief() outputs of tests/test_build_site.py BriefTests still hold
  ```

- [ ] **Step 2: Run them, and see them fail.**
- [ ] **Step 3: Implement.** Then run the Lean script on 3 Mathlib names (`Finset.sum_comm`, `Nat.Prime`, `zero_smul`) and compare with Mathlib's source by eye.
- [ ] **Step 4: Run them, and see them pass.** Run the suite.
- [ ] **Step 5: Commit.** `git commit -m "Migration: each declaration's inputs, Mathlib's sources from Lean"`

### Task 13: The writer and the checker

**Files:**
- Create: `scripts/migrate_write.py`, `scripts/migrate_prompt.md`, `scripts/migrate_check.py`
- Test: `tests/test_migrate.py`

**Interfaces:**
- Consumes: Task 12's bundles; Task 1's `check` and `items`; AI-REVIEWS.md's marked section (Task 6).
- Produces:
  - `migrate_write.py submit BUNDLES --name NAME [--retry CHECKS] [--work .cache/migration]` creates one Message Batch. Each request is built as follows:
    - model `claude-opus-5-5`, `thinking: {"type": "adaptive"}`, `output_config: {"effort": "high", "format": <schema>}`, `max_tokens: 16000`;
    - the system prompt is `migrate_prompt.md` with the marked section inserted, behind a `cache_control` breakpoint;
    - the user message is the bundle, plus the checker's problems on a retry;
    - `custom_id` is the declaration's index in the bundle file.

    It saves `<work>/<NAME>/batch.json`.
  - `migrate_write.py collect NAME` writes `<work>/<NAME>/results.jsonl`, one per declaration, as `{"decl", "cells", "verdict": "approve"|"hold", "hold": "…", "review": "…"}`, and prints the usage totals and their cost at batch prices ($2 per M input tokens, $10 per M output). A refusal or an error becomes `{"decl", "error": …}`.
  - `migrate_check.py BUNDLES RESULTS --source TAUCETI --out CHECKS` gives one `{"decl", "ok": bool, "problems": [...]}` per result. It fails a result when:
    - the shape is wrong, or a cell is missing;
    - any cell is `error` under `approve`;
    - `standard.check(review, exists=…)` finds a problem;
    - **Part 1 does not follow the signature:** for each explicit `(…)` and instance `[…]` binder group (`binder_groups`), Part 1 must name one of its binder names, or, for an anonymous instance, its class, as a whole word. Groups that only introduce a type are skipped;
    - **a reference cannot be traced:** it must share 3 consecutive normalised words with the bundle's texts, and every token holding a digit must appear in them;
    - **a test is not one of the bundle's `tests`, or a Check is not one of its `checks`.**

`migrate_prompt.md` says, in order:
1. Review the Lean first, then hold or write.
2. Hold, filling `hold`, when the declaration looks wrongly stated, when an earlier AI yes looks wrong, or when `open_no` is set.
3. Use references only from the bundle, with their numbers as given.
4. Name tests only from `tests` and `checks`.
5. Each cell is `checked`, `na` or `error`.

- [ ] **Step 1: Write the failing tests.** No network:

  ```python
  def test_request_shape(self):              # model, thinking, effort, schema, system holds the marked section, custom_id
  def test_retry_adds_the_problems(self):
  def test_check_part_one_follows_the_signature(self):   # a review skipping `(hx : IsNilpotent x)` fails naming hx
  def test_check_references_are_traced(self):            # "Serre, A Course in Arithmetic, VII §4" traced; the same with "Thm 99" fails on "99"
  def test_check_tests_and_checks_come_from_the_bundle(self):
  def test_check_hold_and_error_cells(self):             # error under approve fails; under hold passes the cell rule
  ```

- [ ] **Step 2: Run them, and see them fail.**
- [ ] **Step 3: Implement.** Check the batch request against the claude-api skill's Python batches reference before the first real call.
- [ ] **Step 4: Run them, and see them pass.** Run the suite.
- [ ] **Step 5: Commit.** `git commit -m "Migration: the writer (Message Batches, claude-opus-5-5) and the quality bar"`

### Task 14: The records

**Files:**
- Modify: `scripts/migrate_records.py` (subcommand `standard`)
- Test: `tests/test_migrate.py`

**Interfaces:**
- Produces `migrate_records.py standard BUNDLES RESULTS CHECKS --dataset DIR --store evidence --out-dir evidence/records --prefix standard-migration-<date> --held docs/standard-reviews-held.md`.
- **For a result whose check passes**, the verdict is `approve` and `open_no` is false: a version accept (`checked` = its cells), by `{"kind": "agent", "identity": {"kind": "github", "id": "CBirkbeck"}, "involvement": "unknown", "agent": {"tool": "Tau Ceti review migration", "model": "claude-opus-5-5", "session": "<prefix>"}}`.
- **For a hold, or an open no:** a comment version replying to the declaration's latest review record, with `standard.note` `Written in the migration; held for the owner.`, and a line in the held list: `decl`, the reason, the site link.
- **A result that fails its checks after 2 retries:** no record, and a line in the held list, "failed checks: …".
- **Files.** Records go to `<prefix>-<nn>.jsonl`, at most 2,000 per file. `origin` is `{"kind": "file", "ref": "https://github.com/CBirkbeck/tauceti-reviewed-by-test/blob/main/evidence/records/<file>#L<n>"}`. `at` is the time of the run.

- [ ] **Step 1: Write the failing tests.**

  ```python
  def test_approved_becomes_a_version_accept(self):      # passes rec.validate; standard.spec; checked == cells; summary() makes it current with the migration as approver
  def test_held_becomes_a_comment_and_a_held_line(self):
  def test_failed_checks_write_nothing_but_the_list(self):
  def test_files_cap_at_2000(self):
  ```

- [ ] **Step 2: Run them, and see them fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run them, and see them pass.** Run the suite.
- [ ] **Step 5: Commit.** `git commit -m "Migration: approved reviews as versions, held ones as comments, and the list for the owner"`

### Task 15: The pilot, and the owner's go-ahead

- [ ] **Step 1: Build bundles for the first 50 named results.** Run the Mathlib ranges script first if any of them are Mathlib's.
- [ ] **Step 2: Get the credentials, then submit the batch.**
  - Ask the user which credentials to use: an `ant auth login` profile, or `ANTHROPIC_API_KEY`.
  - Submit, collect, check, and retry the failures (twice at most).
- [ ] **Step 3: Show the owner, without writing to the store.**
  - Publish an artifact page with the 50 reviews, each beside its declaration's signature and its held or failed status.
  - Give the measured cost per review and its extrapolation to the full scope.
  - Nothing goes into the store: records are permanent.
- [ ] **Step 4: Stop.** Wait for the owner's go-ahead on the reviews and the cost. Fold their corrections into `migrate_prompt.md` or AI-REVIEWS.md, re-running the pilot if they ask.

### Task 16: The full run (only after the go-ahead)

- [ ] **Step 1: Bundles for the full scope.** Re-pin to the site's commit at that time.
- [ ] **Step 2: Batches in order.** First the named results (including the pilot's, re-run or reused as the owner said), then the rest by roadmap, then Mathlib's.
- [ ] **Step 3: Check and retry each batch.** Check it, retry its failures (twice at most), and build its records with Task 14.
- [ ] **Step 4: Push each batch's files to `main` once its evidence check passes locally.**
  - Watch the Evidence check and Pages runs.
  - Spot-check 5 pages per batch on the live site.
- [ ] **Step 5: Commit the held list. Report to the owner:**
  - how many were approved, held and failed;
  - the cost;
  - the held list's link.

---

## Cost of the migration (for the go-ahead)

**Scope.** 7,698 declarations had an AI yes on 2026-10-31: 5,838 of Tau Ceti and 1,860 of Mathlib.

**Assumed tokens per declaration** (the pilot measures the real numbers before the full run):
- about 5,500 input: about 2,500 of bundle and 3,000 of instructions;
- about 3,600 output: the in-depth review's thinking and a review of about 600 tokens.

**Prices.** claude-opus-5-5 at Message Batches prices (half of $4 and $20 per million tokens) is $2 per million input and $10 per million output.

**Estimate:**

| | tokens | cost |
|---|---|---|
| input | about 42M | about $85 |
| output | about 28M | about $280 |
| retries, about 15% | | about $55 |
| **total** | | **about $420** |

If the thinking runs twice as long, the total is about $800. Prompt caching can lower the input share.

**The alternative** is to run the writer as Claude Code agents. That needs no API bill, but it uses the subscription's limits for several days, the same limits Voyager, the red team and the roadmap workers rely on. It also needs a workflow, which the user must ask for.
