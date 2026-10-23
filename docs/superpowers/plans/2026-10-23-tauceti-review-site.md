# Tau Ceti Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Reviewed-by test site in `CBirkbeck/tauceti-reviewed-by-test` with "Tau Ceti Review": reviews keyed by meaning hash in an S3 evidence store, Voyager's named results as the way in, and a clickable dependency map on every declaration, in the Tau Ceti Atlas's look.

**Architecture:** Four kinds of GitHub workflow (follow/dataset, evidence intake/check, Voyager, pages) around one evidence store in `evidence/`. Python scripts call the pinned LeanTrustBuilders tools (`evidence-core`, `evidence-store`, the extractor's releases) and write sharded JSON under `_site/data/`; a static front end in `web/` (plain JavaScript, no build step) lays it out and computes nothing the tools compute.

**Tech Stack:** Python 3.12 (standard library, `evidence-core` v0.16.1, `evidence-store` v0.7.2), GitHub Actions, plain JavaScript/HTML/CSS, elkjs 0.9.3 (vendored from referee-site), KaTeX 0.16.28 and `markdown.js` (vendored from the Atlas), Playwright 1.57 for the browser check, PyYAML for workflow tests.

**Spec:** `docs/superpowers/specs/2026-10-23-tauceti-review-site-design.md` (read it first; this plan implements it section by section).

## Global Constraints

- Repository `CBirkbeck/tauceti-reviewed-by-test`, branch `suite-site`; the site stays at `https://cbirkbeck.github.io/tauceti-reviewed-by-test/`.
- Library `TauCetiProject/TauCeti`, root module `TauCeti`; API docs at `https://taucetiproject.org/docs/<Module/Path>.html#<declaration>`; Mathlib docs at `https://leanprover-community.github.io/mathlib4_docs/<Module/Path>.html#<declaration>`; Mathlib Explorer at `https://leantrustbuilders.github.io/mathlib-explorer/#/d/<declaration>`.
- Pinned tools: `evidence-core` `v0.16.1`, `evidence-store` `v0.7.2` (`evidence-store init --ref v0.7.2`), extractor releases of series `0.13` only (tags `v0.13.<patch>-lean-v<toolchain>`).
- Datasets: release `dataset-<commit12>`, asset `dataset.tar.gz`; pruned after 30 days except the newest and any whose commit an open `evidence:*` issue names under `### Commit`.
- Two policies only: people (`Policy(agents=False)`) and with AI (`Policy(agents=True)`), every other switch at evidence-core's default.
- State codes everywhere: `0` unreviewed, `1` covered, `2` uncounted, `3` stale, `4` problem, `5` disputed (evidence-core's `DECL_STATES` order is different: always map by name).
- Kind codes: `t` theorem, `d` definition, `s` structure, `c` class, `n` inductive, `i` instance, `a` axiom, `o` opaque.
- Node flags (bits): `1` project, `2` named, `4` basic, `8` routine, `16` documented, `32` auxiliary, `64` sorry.
- Caps: 60 ids per neighbour list (totals kept); a map level shows 12 nodes, then "+ N more"; node shards hold 2,048 nodes; names are in 64 shards by FNV-1a over UTF-16 code units (`common.fnv_shard` and `TauData.fnv` agree: `TauCeti.Place`→47, `Fixture.triple`→60, `Fixture.«term𝟚_»`→38, `ℝ`→8).
- Size budget: the build fails if `_site` exceeds 800 MB.
- Every docstring and record text reaches the page through `TauMarkdown.render` (source HTML stays text); never assign untrusted text to `innerHTML`.
- Zulip: read-only `GET /api/v1/messages`, secrets `ZULIP_SITE`, `ZULIP_EMAIL`, `ZULIP_API_KEY`; channel `Tau Ceti`, topic `new results`, sender `Voyager-bot@leanprover.zulipchat.com`.
- Commit messages in the repository's style (a plain sentence, no type prefix), ending with the line `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- Nothing is pushed, and no other repository is touched, before Task 12; Tasks 12 and 13 do only what they list, and Task 13 starts only when the owner says it is time to switch.
- Tests: `.venv/bin/python -m unittest discover -s tests` (standard-library `unittest`); the browser check: `.venv/bin/python tests/validate_site.py`.

## File map

| file | responsibility |
|---|---|
| `requirements.txt`, `requirements-test.txt` | the pinned tools; PyYAML and Playwright for the tests |
| `data/settings.json` | the pin, the bulk issue, the library, the extractor series, dataset retention, the Zulip topic, the site's name |
| `data/voyager.jsonl` | every Voyager announcement read so far |
| `evidence/` | the S3 store: `store.json` and `records/*.jsonl` |
| `scripts/common.py` | repository paths, settings, `fnv_shard` |
| `scripts/extractor.py` | which extractor release to use for a toolchain; installing it |
| `scripts/pin.py` | moving the pin to the newest extractable commit |
| `scripts/prune.py` | deleting dataset releases nobody needs |
| `scripts/voyager.py` | reading Voyager's topic; parsing announcements; recording `named` records |
| `scripts/site_data.py` | everything a page shows, from the dataset, the store and evidence-core |
| `scripts/build_site.py` | writing `_site/` (data files, the front end) and checking its size |
| `web/index.html`, `web/style.css` | the shell and the Atlas's look |
| `web/data.js` | `TauData`: fetching and caching the data files |
| `web/render.js` | `TauRender`: elements, Markdown, planets, states, links |
| `web/map.js` | `TauMap`: the dependency map |
| `web/app.js` | the router, the rail and every page; `window.TauReview` for the browser check |
| `web/vendor/` | `elk-0.9.3.bundled.js`, `katex.v0.16.28.min.js`, `markdown.js`, their licences, and `NOTICE` (where each comes from) |
| `.github/workflows/dataset.yml`, `follow.yml`, `voyager.yml`, `pages.yml` | the pipeline |
| `.github/workflows/evidence-*.yml`, `.github/ISSUE_TEMPLATE/evidence-*.yml` | generated by `evidence-store init` |
| `tests/fixtures/` | the suite's two-version fixture (dataset B, its sources, its records), Voyager posts, and `NOTICE` |
| `tests/fixture_site.py` | builds a small site from the fixture, for the unit tests and the browser check |
| `tests/test_*.py`, `tests/validate_site.py` | the tests |

---

### Task 1: The store, the settings, and the migrated reviews

**Files:**
- Delete: `scripts/apply.py`, `scripts/fetch_declarations.py`, `scripts/reviews.py`, `scripts/named.py`, `scripts/build_site.py`, `tests/test_apply.py`, `tests/test_fetch.py`, `tests/test_named.py`, `tests/test_reviews.py`, `tests/test_site.py`, `tests/validate_site.py`, `.github/ISSUE_TEMPLATE/reviewed-by.yml`, `.github/ISSUE_TEMPLATE/problem.yml`, `.github/ISSUE_TEMPLATE/test.yml`, `.github/workflows/record.yml`, `.github/workflows/refresh.yml`, `.github/workflows/pages.yml`, `.github/actions/declarations/action.yml`, `data/named-roadmaps.json`, `reviews/` (after step 9)
- Create: `requirements.txt`, `requirements-test.txt`, `data/settings.json` (replace), `scripts/common.py`, `evidence/store.json`, `evidence/records/2026-09.jsonl`, `.github/ISSUE_TEMPLATE/config.yml` (replace), `.github/ISSUE_TEMPLATE/evidence-*.yml`, `.github/workflows/evidence-intake.yml`, `.github/workflows/evidence-check.yml`, `.gitignore` (replace)
- Test: `tests/test_common.py`, `tests/test_store.py`

**Interfaces:**
- Produces: `common.ROOT: Path`, `common.SETTINGS: Path`, `common.load_settings(path=SETTINGS) -> dict`, `common.save_settings(settings: dict, path=SETTINGS) -> None`, `common.fnv_shard(name: str, shards: int) -> int`; the settings keys `repo`, `bulk_issue`, `tauceti`, `library.{name,repo,root,docs}`, `extractor.{repo,series}`, `datasets.keep_days`, `voyager.{site,channel,topic,sender}`, `site.{title,url}`.

- [ ] **Step 1: The pinned tools and a virtual environment**

Create `requirements.txt`:

```
# The LeanTrustBuilders tools this repository runs, pinned: moved on deliberately.
evidence-core @ git+https://github.com/LeanTrustBuilders/evidence-core@v0.16.1
evidence-store @ git+https://github.com/LeanTrustBuilders/evidence-store@v0.7.2
```

Create `requirements-test.txt`:

```
pyyaml==6.0.2
playwright==1.57.0
```

Replace `.gitignore`:

```
__pycache__/
.venv/
.cache/
_site/
_site_fixture/
site/
data/declarations.json
```

Run: `python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt -r requirements-test.txt && .venv/bin/python -m playwright install chromium`
Expected: no error; `.venv/bin/python -c "import evidence_core, evidence_store; print(evidence_core.__name__)"` prints `evidence_core`.

- [ ] **Step 2: Write the failing test for the shared helpers**

Create `tests/test_common.py`:

```python
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import common  # noqa: E402


class FnvTests(unittest.TestCase):
    def test_shards_match_the_page(self):
        # web/data.js computes the same (the browser check compares them).
        self.assertEqual(common.fnv_shard("TauCeti.Place", 64), 47)
        self.assertEqual(common.fnv_shard("Fixture.triple", 64), 60)
        self.assertEqual(common.fnv_shard("Fixture.«term𝟚_»", 64), 38)
        self.assertEqual(common.fnv_shard("ℝ", 64), 8)


class SettingsTests(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "settings.json"
            common.save_settings({"tauceti": "abc", "library": {"name": "Tau Ceti"}}, p)
            self.assertEqual(common.load_settings(p), {"tauceti": "abc", "library": {"name": "Tau Ceti"}})
            self.assertTrue(p.read_text().endswith("\n"))

    def test_the_repository_settings(self):
        s = common.load_settings()
        self.assertEqual(s["repo"], "CBirkbeck/tauceti-reviewed-by-test")
        self.assertEqual(s["library"]["repo"], "TauCetiProject/TauCeti")
        self.assertEqual(s["extractor"], {"repo": "LeanTrustBuilders/extractor", "series": "0.13"})
        self.assertEqual(s["voyager"]["topic"], "new results")
        self.assertEqual(s["site"]["title"], "Tau Ceti Review")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run it to see it fail**

Run: `.venv/bin/python -m unittest tests.test_common -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'common'`.

- [ ] **Step 4: The helpers and the settings**

Create `scripts/common.py`:

```python
"""What the scripts share: where things are, the settings, and the hash that shards names."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "data" / "settings.json"


def load_settings(path: Path = SETTINGS) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_settings(settings: dict, path: Path = SETTINGS) -> None:
    Path(path).write_text(json.dumps(settings, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def fnv_shard(name: str, shards: int) -> int:
    """FNV-1a over the name's UTF-16 code units, modulo ``shards``. The page computes the same
    (web/data.js, `fnv`), so it finds the shard of any name without an index."""
    h = 0x811C9DC5
    data = name.encode("utf-16-le")
    for i in range(0, len(data), 2):
        h ^= data[i] | (data[i + 1] << 8)
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h % shards
```

Replace `data/settings.json`:

```json
{
 "repo": "CBirkbeck/tauceti-reviewed-by-test",
 "bulk_issue": 1,
 "tauceti": "d9068003cb02ec808e548ee70982ffef9379db00",
 "library": {
  "name": "Tau Ceti",
  "repo": "TauCetiProject/TauCeti",
  "root": "TauCeti",
  "docs": "https://taucetiproject.org/docs"
 },
 "extractor": {
  "repo": "LeanTrustBuilders/extractor",
  "series": "0.13"
 },
 "datasets": {
  "keep_days": 30
 },
 "voyager": {
  "site": "https://leanprover.zulipchat.com",
  "channel": "Tau Ceti",
  "topic": "new results",
  "sender": "Voyager-bot@leanprover.zulipchat.com"
 },
 "site": {
  "title": "Tau Ceti Review",
  "url": "https://cbirkbeck.github.io/tauceti-reviewed-by-test/"
 }
}
```

The pin starts at `d9068003cb02…`, the commit of the newest dataset the pilot published (2026-10-19); `follow.yml` moves it.

- [ ] **Step 5: Run the test to see it pass**

Run: `.venv/bin/python -m unittest tests.test_common -v`
Expected: 3 tests, OK.

- [ ] **Step 6: Set the store up**

Run: `.venv/bin/evidence-store init --repo CBirkbeck/tauceti-reviewed-by-test --root TauCeti --name "Tau Ceti" --pages-workflow pages.yml --ref v0.7.2`
Expected: `wrote .github/ISSUE_TEMPLATE/evidence-*.yml and .github/workflows/evidence-{intake,check}.yml`; `evidence/store.json` and `evidence/records/.gitkeep` exist; both workflows use `@v0.7.2`.

Then replace `evidence/store.json` (init names this repository as the library; it is Tau Ceti's store, kept here):

```json
{
 "spec": "ltb-evidence-store/1",
 "name": "Tau Ceti",
 "library": {
  "repo": "TauCetiProject/TauCeti",
  "root": "TauCeti"
 },
 "datasets": {
  "repo": "CBirkbeck/tauceti-reviewed-by-test",
  "tag": "dataset-{commit12}",
  "asset": "dataset.tar.gz"
 },
 "claims": [],
 "maintainers": [
  "CBirkbeck"
 ],
 "imports": [
  {
   "repo": "LeanTrustBuilders/mathlib-probability-evidence"
  }
 ]
}
```

Replace `.github/ISSUE_TEMPLATE/config.yml`:

```yaml
blank_issues_enabled: true
contact_links:
  - name: Tau Ceti Review
    url: https://cbirkbeck.github.io/tauceti-reviewed-by-test/
    about: Open a declaration on the site and use its buttons, which fill these forms in for you.
```

- [ ] **Step 7: Write the failing test for the store**

Create `tests/test_store.py`:

```python
import unittest
from pathlib import Path

from evidence_core import records as rec
from evidence_core.store import Store

ROOT = Path(__file__).resolve().parents[1]
PIN = "d9068003cb02ec808e548ee70982ffef9379db00"


class StoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = Store.load(ROOT / "evidence")

    def test_config(self):
        c = self.store.config
        self.assertEqual(c["name"], "Tau Ceti")
        self.assertEqual(c["library"], {"repo": "TauCetiProject/TauCeti", "root": "TauCeti"})
        self.assertEqual(c["datasets"], {"repo": "CBirkbeck/tauceti-reviewed-by-test",
                                         "tag": "dataset-{commit12}", "asset": "dataset.tar.gz"})
        self.assertEqual(c["imports"], [{"repo": "LeanTrustBuilders/mathlib-probability-evidence"}])
        self.assertEqual(c["maintainers"], ["CBirkbeck"])

    def test_the_migrated_records(self):
        # Only the migrated ones: the store grows with every review, and CI runs this test.
        migrated = [r for r in self.store.records
                    if (r.get("migration") or {}).get("from") in ("reviewed-by/v1", "tests/v1")]
        reviews = [r for r in migrated if r["kind"] == "review"]
        tests = [r for r in migrated if r["kind"] == "test"]
        self.assertEqual((len(reviews), len(tests)), (4, 11))
        for r in reviews + tests:
            self.assertEqual(r["by"]["identity"]["id"], "CBirkbeck")
            self.assertEqual(r["subject"]["hasher"], {"meaning": "ltb-meaning/1", "local": "ltb-local/3"})
            self.assertTrue(r["origin"]["ref"].startswith("CBirkbeck/tauceti-reviewed-by-test#"))
            self.assertEqual(rec.validate(r), [])
        # A review keeps the commit it was made at, its hashes taken at the pin, and says so; the
        # tests' ledger recorded no commit, so a test is keyed at the pin itself.
        for r in reviews:
            self.assertEqual(r["migration"]["hashes_from"], PIN)
        for r in tests:
            self.assertEqual(r["subject"]["commit"], PIN)
        self.assertEqual(sorted({r["subject"]["name"] for r in reviews}),
                         ["HeckeRing.GL2.heckeSlashModularFormEnd", "NumberField.Set.HasNaturalDensity",
                          "TauCeti.IdealArithmeticFunction.vonMangoldt"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 8: Run it to see it fail**

Run: `.venv/bin/python -m unittest tests.test_store -v`
Expected: `test_config` passes; `test_the_migrated_records` FAILS with `AssertionError: Tuples differ: (0, 0) != (4, 11)`.

- [ ] **Step 9: Migrate this repository's ledgers**

The ledgers in `reviews/` are keyed by a text hash; the migration keys them in the pilot's dataset of the pin and says so (`migration.hashes_from`). The text of all four reviewed declarations is unchanged since September (the old site shows each review current at `ffc1a6d`), so the keys are faithful. Voyager's old named ledger is left out: `voyager.py` reads Voyager again.

```bash
mkdir -p .cache/dataset-d9068003cb02
gh release download dataset-d9068003cb02 -R LeanTrustBuilders/reviewed-by-pilot -p dataset.tar.gz -D .cache --clobber
tar -xzf .cache/dataset.tar.gz -C .cache/dataset-d9068003cb02
rm -rf .cache/ledgers && mkdir -p .cache/ledgers
cp reviews/records.jsonl reviews/tests.jsonl reviews/problems.jsonl .cache/ledgers/
: > .cache/ledgers/named.jsonl
.venv/bin/python -m evidence_core migrate reviewed-by .cache/ledgers --dataset .cache/dataset-d9068003cb02 \
  --repo CBirkbeck/tauceti-reviewed-by-test --out evidence/records/2026-09.jsonl
```

Expected: `migrated 15 records to evidence/records/2026-09.jsonl` and no `skipped:` line.

- [ ] **Step 10: Run the tests to see them pass**

Run: `.venv/bin/python -m unittest tests.test_store tests.test_common -v`
Expected: 5 tests, OK.

- [ ] **Step 11: Remove what the suite replaces**

```bash
git rm -q scripts/apply.py scripts/fetch_declarations.py scripts/reviews.py scripts/named.py scripts/build_site.py \
  tests/test_apply.py tests/test_fetch.py tests/test_named.py tests/test_reviews.py tests/test_site.py tests/validate_site.py \
  .github/ISSUE_TEMPLATE/reviewed-by.yml .github/ISSUE_TEMPLATE/problem.yml .github/ISSUE_TEMPLATE/test.yml \
  .github/workflows/record.yml .github/workflows/refresh.yml .github/workflows/pages.yml \
  .github/actions/declarations/action.yml data/named-roadmaps.json
git rm -q -r reviews
```

Run: `.venv/bin/python -m unittest discover -s tests -v`
Expected: 5 tests, OK.

- [ ] **Step 12: Commit**

```bash
git add -A requirements.txt requirements-test.txt .gitignore data/settings.json scripts/common.py evidence .github tests
git commit -q -F - <<'EOF'
The evidence store: Tau Ceti's reviews and tests as S3 records, keyed by meaning hash

The four reviews and eleven tests of the ledgers are migrated with evidence-core
against the pilot's dataset of 2026-10-19; the scripts, forms and workflows of
the old page go.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 2: Which extractor release, and where to pin

**Files:**
- Create: `scripts/extractor.py`, `scripts/pin.py`
- Test: `tests/test_pin.py`

**Interfaces:**
- Consumes: `common.load_settings`, `common.save_settings`.
- Produces: `extractor.toolchain_of(value: str) -> str` (`"leanprover/lean4:v4.36.0-rc1"`, `"v4.36.0-rc1"` or a `lean-toolchain` path → `"4.36.0-rc1"`); `extractor.supported(tags: list[str], series: str) -> dict[str, str]` (toolchain → newest tag of the series); `extractor.release_tags(repo: str) -> list[str]`; CLI `scripts/extractor.py toolchains | tag <toolchain> | install <toolchain> <dir>` (prints the tag). `pin.choose(commits: list[tuple[str, str]], toolchains: set[str], cached) -> str | None`; `pin.cache_url(repo: str, sha: str, toolchain_text: str) -> str`; CLI `scripts/pin.py` prints `moved=true` or `moved=false`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pin.py`:

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import extractor  # noqa: E402
import pin  # noqa: E402

TAGS = ["v4.34.0-rc2", "v0.13.1-lean-v4.36.0-rc1", "v0.13.1-lean-v4.35.0", "v0.13.0-lean-v4.35.0",
        "v0.14.0-lean-v4.37.0-rc1", "v0.12.1-lean-v4.35.0-rc2", "v0.13.1-lean-v4.35.0-rc4"]


class ExtractorTests(unittest.TestCase):
    def test_the_newest_release_of_the_series_for_each_toolchain(self):
        self.assertEqual(extractor.supported(TAGS, "0.13"),
                         {"4.35.0": "v0.13.1-lean-v4.35.0", "4.35.0-rc4": "v0.13.1-lean-v4.35.0-rc4",
                          "4.36.0-rc1": "v0.13.1-lean-v4.36.0-rc1"})

    def test_another_series_is_not_taken(self):
        self.assertEqual(extractor.supported(TAGS, "0.14"), {"4.37.0-rc1": "v0.14.0-lean-v4.37.0-rc1"})

    def test_toolchain_of(self):
        self.assertEqual(extractor.toolchain_of("leanprover/lean4:v4.36.0-rc1\n"), "4.36.0-rc1")
        self.assertEqual(extractor.toolchain_of("v4.35.0"), "4.35.0")


class PinTests(unittest.TestCase):
    COMMITS = [("c3", "leanprover/lean4:v4.37.0-rc1\n"), ("c2", "leanprover/lean4:v4.36.0-rc1\n"),
               ("c1", "leanprover/lean4:v4.36.0-rc1\n")]

    def test_the_newest_supported_and_cached_commit(self):
        self.assertEqual(pin.choose(self.COMMITS, {"4.36.0-rc1"}, lambda sha, text: True), "c2")

    def test_a_commit_the_cache_has_not_built_is_skipped(self):
        self.assertEqual(pin.choose(self.COMMITS, {"4.36.0-rc1"}, lambda sha, text: sha == "c1"), "c1")

    def test_nothing_when_nothing_fits(self):
        self.assertIsNone(pin.choose(self.COMMITS, {"4.35.0"}, lambda sha, text: True))

    def test_the_cache_address(self):
        self.assertEqual(pin.cache_url("TauCetiProject/TauCeti", "abc", "leanprover/lean4:v4.36.0-rc1\n"),
                         "https://cache.taucetiproject.org/revisions/TauCetiProject/TauCeti/tc/"
                         "leanprover--lean4---v4.36.0-rc1/abc.jsonl")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m unittest tests.test_pin -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'extractor'`.

- [ ] **Step 3: The extractor's releases**

Create `scripts/extractor.py`:

```python
#!/usr/bin/env python3
"""The extractor releases this repository uses: those of one series (`extractor.series` in
data/settings.json, `0.13`, which writes `ltb-dataset/2`), the newest for each Lean toolchain. A new
series is taken on deliberately, by changing the setting, never because one was published.

  python3 scripts/extractor.py toolchains                 the toolchains the series has a release for
  python3 scripts/extractor.py tag <toolchain>            the release for a toolchain (or a lean-toolchain file)
  python3 scripts/extractor.py install <toolchain> <dir>  unpack that release into <dir>; print its tag
"""
from __future__ import annotations

import re
import subprocess
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_settings  # noqa: E402

TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)-lean-v(.+)$")
ASSET = "trust-extract-linux-x86_64.tar.gz"


def toolchain_of(value: str) -> str:
    """`leanprover/lean4:v4.36.0-rc1`, `v4.36.0-rc1` or a lean-toolchain file: `4.36.0-rc1`."""
    p = Path(value)
    if p.is_file():
        value = p.read_text(encoding="utf-8")
    return value.strip().split(":", 1)[-1].removeprefix("v")


def supported(tags: list[str], series: str) -> dict[str, str]:
    """For each toolchain, the newest release of ``series`` for it."""
    major, minor = (int(x) for x in series.split("."))
    best: dict[str, tuple[int, str]] = {}
    for tag in tags:
        m = TAG.match(tag)
        if not m or (int(m[1]), int(m[2])) != (major, minor):
            continue
        patch, toolchain = int(m[3]), m[4]
        if toolchain not in best or patch > best[toolchain][0]:
            best[toolchain] = (patch, tag)
    return {t: tag for t, (_, tag) in sorted(best.items())}


def release_tags(repo: str) -> list[str]:
    out = subprocess.run(["gh", "release", "list", "-R", repo, "--limit", "200", "--json", "tagName",
                          "--jq", ".[].tagName"], check=True, capture_output=True, text=True).stdout
    return out.split()


def install(repo: str, tag: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(["gh", "release", "download", tag, "-R", repo, "-p", ASSET, "-D", str(dest), "--clobber"],
                   check=True)
    with tarfile.open(dest / ASSET) as tar:
        tar.extractall(dest, filter="tar")
    (dest / ASSET).unlink()


def main(argv: list[str]) -> int:
    settings = load_settings()
    repo, series = settings["extractor"]["repo"], settings["extractor"]["series"]
    if not argv or argv[0] not in ("toolchains", "tag", "install") or (argv[0] != "toolchains" and len(argv) < 2):
        print(__doc__, file=sys.stderr)
        return 2
    table = supported(release_tags(repo), series)
    if argv[0] == "toolchains":
        print("\n".join(table))
        return 0
    toolchain = toolchain_of(argv[1])
    tag = table.get(toolchain)
    if tag is None:
        print(f"::error::the extractor has no release of series {series} for Lean {toolchain}", file=sys.stderr)
        return 1
    if argv[0] == "install":
        if len(argv) < 3:
            print(__doc__, file=sys.stderr)
            return 2
        install(repo, tag, Path(argv[2]))
    print(tag)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: The pin**

Create `scripts/pin.py`:

```python
#!/usr/bin/env python3
"""Move the pin (`tauceti` in data/settings.json) to the newest commit of Tau Ceti's main that can be
extracted cheaply: among the last 30, the newest whose toolchain the extractor series has a release
for and whose build Tau Ceti's cache has published. When main has moved to a toolchain the series
does not support, the pin waits on the last commit before the move, and says so.

  python3 scripts/pin.py      prints moved=true or moved=false (a line for $GITHUB_OUTPUT)
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_settings, save_settings  # noqa: E402
from extractor import release_tags, supported, toolchain_of  # noqa: E402

CACHE = "https://cache.taucetiproject.org/revisions/{repo}/tc/{scope}/{sha}.jsonl"


def choose(commits: list[tuple[str, str]], toolchains: set[str], cached) -> str | None:
    """The newest of ``commits`` (``(sha, lean-toolchain text)``, newest first) whose toolchain is in
    ``toolchains`` and for which ``cached(sha, text)`` holds."""
    for sha, text in commits:
        if toolchain_of(text) in toolchains and cached(sha, text):
            return sha
    return None


def cache_url(repo: str, sha: str, toolchain_text: str) -> str:
    scope = toolchain_text.strip().replace("/", "--", 1).replace(":", "---", 1)
    return CACHE.format(repo=repo, scope=scope, sha=sha)


def gh_json(path: str):
    return json.loads(subprocess.run(["gh", "api", path], check=True, capture_output=True, text=True).stdout)


def recent_commits(repo: str, n: int = 30) -> list[tuple[str, str]]:
    out = []
    for c in gh_json(f"repos/{repo}/commits?sha=main&per_page={n}"):
        blob = gh_json(f"repos/{repo}/contents/lean-toolchain?ref={c['sha']}")
        out.append((c["sha"], base64.b64decode(blob["content"]).decode("utf-8")))
    return out


def cached_in(repo: str):
    def check(sha: str, text: str) -> bool:
        try:
            with urllib.request.urlopen(urllib.request.Request(cache_url(repo, sha, text), method="HEAD"),
                                        timeout=30) as r:
                return r.status == 200
        except Exception:
            return False
    return check


def main() -> int:
    settings = load_settings()
    repo = settings["library"]["repo"]
    toolchains = set(supported(release_tags(settings["extractor"]["repo"]), settings["extractor"]["series"]))
    commits = recent_commits(repo)
    if commits and toolchain_of(commits[0][1]) not in toolchains:
        print(f"::warning::Tau Ceti's main ({commits[0][0][:7]}) is on Lean {toolchain_of(commits[0][1])}, "
              f"which extractor series {settings['extractor']['series']} has no release for", file=sys.stderr)
    sha = choose(commits, toolchains, cached_in(repo))
    if sha is None or sha == settings["tauceti"]:
        print("moved=false")
        return 0
    settings["tauceti"] = sha
    save_settings(settings)
    print("moved=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `.venv/bin/python -m unittest tests.test_pin -v`
Expected: 7 tests, OK.

- [ ] **Step 6: Check the release table against the real releases**

Run: `.venv/bin/python scripts/extractor.py toolchains`
Expected: at least the line `4.36.0-rc1` (Tau Ceti's toolchain on 2026-10-23).

- [ ] **Step 7: Commit**

```bash
git add scripts/extractor.py scripts/pin.py tests/test_pin.py
git commit -q -F - <<'EOF'
The pin: Tau Ceti's newest commit that the extractor's 0.13 series can read and the cache has built

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 3: Pruning old datasets

**Files:**
- Create: `scripts/prune.py`
- Test: `tests/test_prune.py`

**Interfaces:**
- Consumes: `common.load_settings`.
- Produces: `prune.named_commits(bodies: list[str]) -> set[str]`; `prune.to_delete(releases: list[tuple[str, str]], keep: set[str], now: datetime, days: int) -> list[str]` (tags, oldest first); CLI `scripts/prune.py [--dry-run]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_prune.py`:

```python
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import prune  # noqa: E402

NOW = datetime(2026, 11, 30, tzinfo=timezone.utc)
RELEASES = [("dataset-aaaaaaaaaaaa", "2026-10-01T06:00:00Z"), ("dataset-bbbbbbbbbbbb", "2026-10-15T06:00:00Z"),
            ("dataset-cccccccccccc", "2026-11-20T06:00:00Z"), ("v1.0", "2026-01-01T00:00:00Z"),
            ("dataset-dddddddddddd", "2026-09-01T00:00:00Z")]


class PruneTests(unittest.TestCase):
    def test_datasets_older_than_the_limit_go_oldest_first(self):
        self.assertEqual(prune.to_delete(RELEASES, set(), NOW, 30),
                         ["dataset-dddddddddddd", "dataset-aaaaaaaaaaaa", "dataset-bbbbbbbbbbbb"])

    def test_the_newest_stays_however_old(self):
        self.assertEqual(prune.to_delete([("dataset-aaaaaaaaaaaa", "2026-01-01T00:00:00Z")], set(), NOW, 30), [])

    def test_a_dataset_an_open_issue_names_stays(self):
        self.assertEqual(prune.to_delete(RELEASES, {"bbbbbbbbbbbb1234", "aaaaaaa"}, NOW, 30),
                         ["dataset-dddddddddddd"])

    def test_the_commits_issue_bodies_name(self):
        bodies = ["### Declaration\n\nTauCeti.foo\n\n### Commit\n\nbbbbbbbbbbbb1234567890\n\n### Why\n\nx",
                  "### Commit\n\n_No response_\n", None]
        self.assertEqual(prune.named_commits(bodies), {"bbbbbbbbbbbb1234567890"})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m unittest tests.test_prune -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'prune'`.

- [ ] **Step 3: Write the script**

Create `scripts/prune.py`:

```python
#!/usr/bin/env python3
"""Delete the dataset releases nobody needs any more: those older than `datasets.keep_days` days
(data/settings.json), except the newest and any whose commit an open issue of the store names.
Intake keys a form's record in the dataset of the commit the form names, and waits while that
dataset is missing, so an open form keeps its dataset.

  python3 scripts/prune.py [--dry-run]
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_settings  # noqa: E402

COMMIT = re.compile(r"^###\s+Commit\s*\n+\s*([0-9a-f]{7,40})\s*$", re.M)


def named_commits(bodies: list[str | None]) -> set[str]:
    """The commits (as written, 7 to 40 hex digits) that issue bodies give under `### Commit`."""
    return {m for b in bodies for m in COMMIT.findall(b or "")}


def to_delete(releases: list[tuple[str, str]], keep: set[str], now: datetime, days: int) -> list[str]:
    """Of ``(tag, created_at)`` releases, the `dataset-*` ones made more than ``days`` days before
    ``now``, oldest first, except the newest and those whose commit one of ``keep`` begins."""
    datasets = sorted(((t, c) for t, c in releases if t.startswith("dataset-")), key=lambda r: r[1])
    if not datasets:
        return []
    newest, cutoff = datasets[-1][0], now - timedelta(days=days)
    out = []
    for tag, created in datasets:
        commit12 = tag.removeprefix("dataset-")[:12]
        kept = any(commit12.startswith(k[:12]) for k in keep)
        if tag != newest and not kept and datetime.fromisoformat(created.replace("Z", "+00:00")) < cutoff:
            out.append(tag)
    return out


def gh_json(args: list[str]):
    return json.loads(subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout)


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    settings = load_settings()
    repo = settings["repo"]
    releases = [(r["tagName"], r["createdAt"]) for r in
                gh_json(["release", "list", "-R", repo, "--limit", "1000", "--json", "tagName,createdAt"])]
    issues = gh_json(["issue", "list", "-R", repo, "--state", "open", "--limit", "1000", "--json", "body,labels"])
    bodies = [i["body"] for i in issues if any(label["name"].startswith("evidence:") for label in i["labels"])]
    for tag in to_delete(releases, named_commits(bodies), datetime.now(timezone.utc), settings["datasets"]["keep_days"]):
        print(("would delete " if dry else "deleting ") + tag)
        if not dry:
            subprocess.run(["gh", "release", "delete", tag, "-R", repo, "--yes", "--cleanup-tag"], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/bin/python -m unittest tests.test_prune -v`
Expected: 4 tests, OK.

- [ ] **Step 5: Commit**

```bash
git add scripts/prune.py tests/test_prune.py
git commit -q -F - <<'EOF'
Datasets older than thirty days go, unless they are the newest or an open form names them

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 4: The dataset workflows

**Files:**
- Create: `.github/workflows/dataset.yml`, `.github/workflows/follow.yml`
- Test: `tests/test_workflows.py`

**Interfaces:**
- Consumes: `scripts/extractor.py install`, `scripts/pin.py`, `scripts/prune.py`.
- Produces: the reusable workflow `./.github/workflows/dataset.yml` (input `commit`, default the pin); `follow.yml` jobs `pin` (output `moved`), `dataset`, `prune`. Task 7 adds the job `named`, Task 19 the job `site`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_workflows.py`:

```python
import unittest
from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def load(name: str) -> dict:
    wf = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    wf["on"] = wf.get("on", wf.get(True))  # YAML 1.1 reads the key `on` as True
    return wf


def steps(job: dict) -> list[dict]:
    return job.get("steps", [])


def runs(job: dict) -> str:
    return "\n".join(s.get("run", "") for s in steps(job))


class DatasetWorkflowTests(unittest.TestCase):
    def test_dataset_extracts_with_the_pinned_series_and_publishes(self):
        wf = load("dataset.yml")
        self.assertIn("workflow_call", wf["on"])
        self.assertIn("workflow_dispatch", wf["on"])
        job = wf["jobs"]["extract"]
        self.assertTrue(any(s.get("uses", "").startswith("astral-sh/setup-uv@") for s in steps(job)),
                        "Tau Ceti's lake-cache-get.sh runs uvx")
        text = runs(job)
        self.assertIn("scripts/extractor.py install", text)
        for arg in ("--parts 8", "--jobs 1", "--skip-modules-file", "--no-statements", "--no-signatures",
                    "--no-upstream-docs"):
            self.assertIn(arg, text)
        self.assertIn('gh release create "$TAG"', text)

    def test_follow_pins_extracts_and_prunes(self):
        wf = load("follow.yml")
        self.assertEqual(wf["on"]["schedule"], [{"cron": "40 5 * * *"}])
        jobs = wf["jobs"]
        self.assertIn("python3 scripts/pin.py", runs(jobs["pin"]))
        self.assertEqual(jobs["dataset"]["uses"], "./.github/workflows/dataset.yml")
        self.assertIn("python3 scripts/prune.py", runs(jobs["prune"]))

    def test_every_checkout_takes_the_tip_of_the_branch(self):
        for f in sorted(WORKFLOWS.glob("*.yml")):
            if f.name.startswith("evidence-"):
                continue  # evidence-store's, generated
            for name, job in load(f.name)["jobs"].items():
                for s in steps(job):
                    if s.get("uses", "").startswith("actions/checkout@"):
                        self.assertEqual((s.get("with") or {}).get("ref"), "${{ github.ref }}", f"{f.name}: {name}")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m unittest tests.test_workflows -v`
Expected: FAIL with `FileNotFoundError: ... dataset.yml`.

- [ ] **Step 3: The dataset workflow**

Create `.github/workflows/dataset.yml`:

```yaml
name: Dataset

# Extracts the dataset (S2) of one Tau Ceti commit with the newest extractor release of the series in
# data/settings.json, and publishes it as the release dataset-<commit12> of this repository: what the
# site, intake and the Voyager reader key records in.
on:
  workflow_dispatch:
    inputs:
      commit:
        description: The Tau Ceti commit (default the pinned one)
        required: false
  workflow_call:
    inputs:
      commit:
        type: string
        required: false

permissions:
  contents: write

concurrency:
  group: dataset-${{ inputs.commit || 'pinned' }}
  cancel-in-progress: false

jobs:
  extract:
    runs-on: ubuntu-latest
    timeout-minutes: 150
    env:
      GH_TOKEN: ${{ github.token }}
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.ref }}
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Which commit
        run: |
          commit="${{ inputs.commit }}"
          [ -n "$commit" ] || commit=$(python3 -c "import json; print(json.load(open('data/settings.json'))['tauceti'])")
          echo "COMMIT=$commit" >> "$GITHUB_ENV"
          echo "TAG=dataset-${commit:0:12}" >> "$GITHUB_ENV"
      - name: Already published?
        id: published
        run: |
          if gh release view "$TAG" -R "$GITHUB_REPOSITORY" > /dev/null 2>&1; then
            echo "$TAG is already published"; echo "done=true" >> "$GITHUB_OUTPUT"
          else
            echo "done=false" >> "$GITHUB_OUTPUT"
          fi
      - name: Room on the runner
        if: steps.published.outputs.done != 'true'
        run: |
          sudo rm -rf /usr/share/dotnet /usr/local/lib/android /opt/ghc /opt/hostedtoolcache/CodeQL
          df -h / | tail -1
      - name: Tau Ceti at the commit
        if: steps.published.outputs.done != 'true'
        run: |
          git clone -q --filter=blob:none https://github.com/TauCetiProject/TauCeti "$RUNNER_TEMP/TauCeti"
          git -C "$RUNNER_TEMP/TauCeti" checkout -q "$COMMIT"
          cat "$RUNNER_TEMP/TauCeti/lean-toolchain"
      - name: Lean
        if: steps.published.outputs.done != 'true'
        run: |
          curl -sSfL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh | sh -s -- -y --default-toolchain none
          echo "$HOME/.elan/bin" >> "$GITHUB_PATH"
      - name: uv, which Tau Ceti's lake-cache-get.sh runs
        if: steps.published.outputs.done != 'true'
        uses: astral-sh/setup-uv@v6
      - name: Tau Ceti and Mathlib from their caches
        if: steps.published.outputs.done != 'true'
        working-directory: ${{ runner.temp }}/TauCeti
        run: |
          lake exe cache get
          bash scripts/lake-cache-get.sh .
          if ! lake build --no-build > /dev/null 2>&1; then
            echo "::notice::Not every module is in the cache; building the rest"
            lake build 2>&1 | tail -5 || true
          fi
          { lake build --no-build 2>&1 || true; } | sed -n '/logged failures/,$s/^- //p' > "$RUNNER_TEMP/unbuilt.txt"
          if [ -s "$RUNNER_TEMP/unbuilt.txt" ]; then
            echo "::warning::$(wc -l < "$RUNNER_TEMP/unbuilt.txt") modules do not build at $COMMIT and are left out"
          fi
      - name: The extractor, of the pinned series
        if: steps.published.outputs.done != 'true'
        run: |
          tag=$(python3 scripts/extractor.py install "$RUNNER_TEMP/TauCeti/lean-toolchain" "$RUNNER_TEMP/extractor")
          bin=$(find "$RUNNER_TEMP/extractor" -type f -name trust-extract | head -1)
          [ -x "$bin" ] || { echo "::error::no trust-extract in release $tag"; exit 1; }
          echo "EXTRACTOR_TAG=$tag" >> "$GITHUB_ENV"
          echo "EXTRACTOR_BIN=$bin" >> "$GITHUB_ENV"
      - name: Extract
        if: steps.published.outputs.done != 'true'
        working-directory: ${{ runner.temp }}/TauCeti
        run: |
          sudo sysctl -q -w vm.max_map_count=262144 || true
          lake env "$EXTRACTOR_BIN" extract --root TauCeti --repo TauCetiProject/TauCeti --out "$RUNNER_TEMP/dataset" \
            --parts 8 --jobs 1 --skip-modules-file "$RUNNER_TEMP/unbuilt.txt" \
            --no-statements --no-signatures --no-upstream-docs
          attributes=$(find "$RUNNER_TEMP/extractor" -type f -name attributes.py | head -1)
          if [ -n "$attributes" ]; then python3 "$attributes" --dataset "$RUNNER_TEMP/dataset" --source .; fi
          du -sh "$RUNNER_TEMP/dataset"
      - name: Publish
        if: steps.published.outputs.done != 'true'
        run: |
          tar -czf "$RUNNER_TEMP/dataset.tar.gz" -C "$RUNNER_TEMP/dataset" .
          gh release create "$TAG" "$RUNNER_TEMP/dataset.tar.gz" -R "$GITHUB_REPOSITORY" --latest=false \
            --title "Dataset for Tau Ceti $COMMIT" \
            --notes "The dataset (S2) of TauCetiProject/TauCeti at $COMMIT, by trust-extract $EXTRACTOR_TAG (LeanTrustBuilders/extractor)."
```

- [ ] **Step 4: The daily workflow**

Create `.github/workflows/follow.yml`:

```yaml
name: Follow Tau Ceti

# Daily: pins Tau Ceti's newest main commit the extractor can read (scripts/pin.py), extracts its
# dataset, and deletes the datasets nobody needs any more (scripts/prune.py). Reviews keep the meaning
# hashes they were made on: a declaration whose meaning changed shows them greyed until reviewed again.
on:
  schedule:
    - cron: '40 5 * * *'
  workflow_dispatch:

permissions:
  contents: write
  issues: read
  pages: write
  id-token: write

concurrency:
  group: follow-tauceti
  cancel-in-progress: false

jobs:
  pin:
    runs-on: ubuntu-latest
    outputs:
      moved: ${{ steps.pin.outputs.moved }}
    env:
      GH_TOKEN: ${{ github.token }}
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.ref }}
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - id: pin
        run: |
          python3 scripts/pin.py | tee -a "$GITHUB_OUTPUT"
          if git diff --quiet; then exit 0; fi
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          sha=$(python3 -c "import json; print(json.load(open('data/settings.json'))['tauceti'][:7])")
          git commit -q -am "Follow Tau Ceti to $sha"
          for attempt in 1 2 3 4 5; do git pull --rebase -q && git push -q && break; sleep $((attempt * 5)); done
  dataset:
    needs: pin
    if: needs.pin.outputs.moved == 'true'
    uses: ./.github/workflows/dataset.yml
    permissions:
      contents: write
  prune:
    needs: [pin, dataset]
    if: always() && needs.dataset.result == 'success'
    runs-on: ubuntu-latest
    env:
      GH_TOKEN: ${{ github.token }}
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.ref }}
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: python3 scripts/prune.py
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `.venv/bin/python -m unittest tests.test_workflows -v`
Expected: 3 tests, OK.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/dataset.yml .github/workflows/follow.yml tests/test_workflows.py
git commit -q -F - <<'EOF'
Follow Tau Ceti daily: pin, extract with the 0.13 series (uv installed for the cache script), prune

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
```

### Task 5: Voyager's announcements

**Files:**
- Create: `scripts/voyager.py`, `tests/fixtures/voyager/messages.json`, `tests/fixtures/dataset-b/` (copied), `tests/fixtures/source-b/` (copied), `tests/fixtures/records.jsonl` (copied), `tests/fixtures/NOTICE`
- Test: `tests/test_voyager.py`

**Interfaces:**
- Consumes: `common.ROOT`, `common.load_settings`; evidence-core's `Dataset`, `records.SCHEMA`, `records.subject_from_decl`, `Store`.
- Produces: `voyager.parse_post(message: dict) -> list[dict]` (each `{decl, name, what, about, prs, source: {voyager, stream}, at}`, `what` is `"result"`, `"definition"` or `None`); `voyager.merge(known, new) -> list[dict]`; `voyager.plain(text) -> str`; `voyager.post_url(site, stream, channel, topic, message_id) -> str`; `voyager.named_records(announcements, ds, store, voyager_settings) -> list[dict]`; `voyager.fetch_messages(site, email, key, channel, topic, sender) -> list[dict]`; `voyager.keep(messages, path=ANNOUNCEMENTS) -> tuple[int, int]`; `voyager.read_jsonl(path)`, `voyager.write_jsonl(path, rows)`; CLI `scripts/voyager.py fetch | import <messages.json> | record --dataset DIR [--store DIR]`. The fixture `tests/fixtures/dataset-b` (the suite's version B: 21 declarations of `Fixture`, commit `B`) and `tests/fixtures/source-b` serve Tasks 7 and 8 too.

- [ ] **Step 1: The suite's fixture**

The dataset of the extractor's two-version fixture (version B), its sources, and the records of the suite's conformance vectors (made against version A), all Apache-2.0. `git clone` does not use the GitHub API.

```bash
rm -rf .cache/specs .cache/extractor
git clone -q --depth 1 https://github.com/LeanTrustBuilders/specs .cache/specs
git clone -q --depth 1 https://github.com/LeanTrustBuilders/extractor .cache/extractor
mkdir -p tests/fixtures/voyager tests/fixtures/source-b
cp -r .cache/specs/vectors/fixture-b tests/fixtures/dataset-b
cp .cache/specs/vectors/records.jsonl tests/fixtures/records.jsonl
cp -r .cache/extractor/test/fixture/Fixture .cache/extractor/test/fixture/Fixture.lean tests/fixtures/source-b/
cp .cache/extractor/test/fixture-b/Fixture/Basic.lean tests/fixtures/source-b/Fixture/Basic.lean
```

Expected: `tests/fixtures/dataset-b/meta.json` says `"commit": "B"`; `tests/fixtures/source-b/Fixture/Basic.lean` contains `theorem triple_three'`.

Create `tests/fixtures/NOTICE`:

````
dataset-b/ and records.jsonl are the conformance vectors of LeanTrustBuilders/specs (vectors/fixture-b,
vectors/records.jsonl); source-b/ is the fixture of LeanTrustBuilders/extractor (test/fixture, with
test/fixture-b/Fixture/Basic.lean laid over it): its version B, which dataset-b describes. Both are
Apache-2.0 (the LICENSE files of those repositories). voyager/messages.json is three posts in the form
of Voyager's on the Lean Zulip, shortened.
````

Create `tests/fixtures/voyager/messages.json`: three posts in the form of Voyager's (the first post's subject headings and `†`; today's sections and docs address, a percent-encoded anchor, an "In progress" line; and a repeat):

````json
{
 "result": "success",
 "found_oldest": true,
 "messages": [
  {
   "id": 613614529,
   "stream_id": 610393,
   "timestamp": 1785407289,
   "subject": "new results",
   "content": "**Voyager · what's new in Tau Ceti**\n\nHello — I'm a bot. Once a day I check what named theorems and notable definitions have landed in Tau Ceti.\n\n**Contour integration and the residue calculus**\n\n- **[The argument principle](https://taucetiproject.github.io/TauCeti/docs/TauCeti/Analysis/Contour/Argument.html#TauCeti.Contour.argumentPrinciple)** — the contour integral of `f'/f` counts zeros minus poles, weighted by winding number. (TauCeti#720)\n- **[The generalized winding number](https://taucetiproject.github.io/TauCeti/docs/TauCeti/Analysis/Contour/Winding.html#TauCeti.Contour.windingNumber)**† — (Hungerbühler–Wasem Def 2.1). (TauCeti#703, TauCeti#962)\n- **[The residue theorem](https://github.com/TauCetiProject/TauCeti/blob/main/TauCeti/Analysis/Contour/Residue.lean#L10)** — the integral is 2πi times the sum of the residues. (TauCeti#640)\n\n*† = also being formalised in Mathlib's in-progress Riemann-mapping PR mathlib4#33505.*\n\n*Stats*\n- 158,436 lines of Lean across 871 files (Tau Ceti only, excluding Mathlib)\n- 8,366 declarations\n"
  },
  {
   "id": 634197175,
   "stream_id": 610393,
   "timestamp": 1792726356,
   "subject": "new results",
   "content": "**Voyager · what's new in Tau Ceti** *(AI-generated summary)*\n\n*Named results*\n- **[The Jacobson–Morozov theorem](https://taucetiproject.org/docs/TauCeti/Algebra/Lie/Sl2/JacobsonMorozov.html#TauCeti.exists_isSl2Triple_of_isNilpotent_ad)** — every nonzero ad-nilpotent element is the nilpositive element of an sl₂-triple (Jacobson, *Lie Algebras*, III §11). (TauCeti#19650)\n- **[The 2-Selmer group is finite](https://taucetiproject.org/docs/TauCeti/AlgebraicGeometry/EllipticCurve/MordellWeil/RankBound.html#WeierstrassCurve.Affine.finite_selmerGroup%E2%82%82)** — for an elliptic curve over a number field. (TauCeti#19001)\n\n*Notable definitions*\n- **[Pic⁰ of a curve](https://taucetiproject.org/docs/TauCeti/AlgebraicGeometry/LineBundle/PicZero.html#TauCeti.AlgebraicGeometry.LineBundleClass.picZero)** — the degree-zero line bundles on a proper integral curve (Hartshorne II.6). (TauCeti#7803)\n\n*In progress* — the Perron–Frobenius theorem: positive matrices, eigenvector and spectral radius (TauCeti#19699)\n\n*Stats*\n- 3,733,912 lines of Lean across 17,809 files (Tau Ceti only, excluding Mathlib)\n"
  },
  {
   "id": 634300000,
   "stream_id": 610393,
   "timestamp": 1792769000,
   "subject": "new results",
   "content": "**Voyager · what's new in Tau Ceti** *(AI-generated summary)*\n\n*Named results*\n- **[The Jacobson–Morozov theorem](https://taucetiproject.org/docs/TauCeti/Algebra/Lie/Sl2/JacobsonMorozov.html#TauCeti.exists_isSl2Triple_of_isNilpotent_ad)** — every nonzero ad-nilpotent element is the nilpositive element of an sl₂-triple. (TauCeti#19650)\n\n*Stats*\n- 3,800,000 lines of Lean\n"
  }
 ]
}
````

- [ ] **Step 2: Write the failing tests**

Create `tests/test_voyager.py`:

````python
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import voyager  # noqa: E402

from evidence_core.dataset import Dataset  # noqa: E402
from evidence_core.store import Store, default_config  # noqa: E402

MESSAGES = json.loads((HERE / "fixtures" / "voyager" / "messages.json").read_text(encoding="utf-8"))["messages"]
SETTINGS = {"site": "https://leanprover.zulipchat.com", "channel": "Tau Ceti", "topic": "new results",
            "sender": "voyager@example.org"}


class ParseTests(unittest.TestCase):
    def test_the_first_post_under_subject_headings(self):
        got = voyager.parse_post(MESSAGES[0])
        self.assertEqual([a["decl"] for a in got], ["TauCeti.Contour.argumentPrinciple", "TauCeti.Contour.windingNumber"])
        self.assertEqual([a["what"] for a in got], [None, None])
        self.assertEqual(got[0]["about"], "the contour integral of `f'/f` counts zeros minus poles, weighted by winding number.")
        self.assertEqual(got[1]["prs"], [703, 962])
        self.assertEqual(got[1]["about"], "(Hungerbühler–Wasem Def 2.1).")
        self.assertEqual(got[0]["at"], "2026-07-30T10:28:09Z")
        self.assertEqual(got[0]["source"], {"voyager": 613614529, "stream": 610393})

    def test_sections_today_and_the_new_docs_address(self):
        got = voyager.parse_post(MESSAGES[1])
        self.assertEqual([(a["decl"], a["what"]) for a in got], [
            ("TauCeti.exists_isSl2Triple_of_isNilpotent_ad", "result"),
            ("WeierstrassCurve.Affine.finite_selmerGroup₂", "result"),
            ("TauCeti.AlgebraicGeometry.LineBundleClass.picZero", "definition")])
        self.assertEqual(got[0]["about"], "every nonzero ad-nilpotent element is the nilpositive element of an "
                                          "sl₂-triple (Jacobson, *Lie Algebras*, III §11).")
        self.assertEqual(got[0]["name"], "The Jacobson–Morozov theorem")

    def test_in_progress_and_stats_are_not_announcements(self):
        self.assertNotIn("Perron", json.dumps([a["name"] for m in MESSAGES for a in voyager.parse_post(m)]))

    def test_an_announcement_made_twice_is_kept_once(self):
        first = [a for m in MESSAGES[:2] for a in voyager.parse_post(m)]
        merged = voyager.merge(first, voyager.parse_post(MESSAGES[2]))
        self.assertEqual(len(merged), 5)
        self.assertEqual(merged, sorted(merged, key=lambda a: a["at"]))

    def test_pull_requests_leave_the_sentence(self):
        self.assertEqual(voyager.plain("a sentence. (TauCeti#1, TauCeti#2)"), "a sentence.")
        self.assertEqual(voyager.plain("a (Book, §2) sentence (TauCeti#1 and TauCeti#2)"), "a (Book, §2) sentence")


class FetchTests(unittest.TestCase):
    def test_pages_back_until_the_oldest(self):
        pages = [{"result": "success", "found_oldest": False, "messages": MESSAGES[1:]},
                 {"result": "success", "found_oldest": True, "messages": MESSAGES[:1]}]
        seen = []

        def fake(req, timeout):
            seen.append(req.full_url)
            return io.BytesIO(json.dumps(pages[len(seen) - 1]).encode())
        with mock.patch.object(voyager.urllib.request, "urlopen", fake):
            got = voyager.fetch_messages("https://z.example.org", "bot@example.org", "key", "Tau Ceti", "new results",
                                         "bot@example.org")
        self.assertEqual([m["id"] for m in got], [m["id"] for m in MESSAGES])
        self.assertIn("anchor=newest", seen[0])
        self.assertIn(f"anchor={MESSAGES[1]['id']}", seen[1])
        self.assertIn("include_anchor=false", seen[1])

    def test_a_refusal_is_an_error(self):
        with mock.patch.object(voyager.urllib.request, "urlopen",
                               lambda req, timeout: io.BytesIO(b'{"result": "error", "msg": "Invalid API key"}')):
            with self.assertRaisesRegex(RuntimeError, "Invalid API key"):
                voyager.fetch_messages("https://z", "e", "k", "c", "t", "s")


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.ds = Dataset.load(HERE / "fixtures" / "dataset-b")
        self.dir = Path(tempfile.mkdtemp())
        self.store = Store.init(self.dir / "evidence", default_config("example/store", "Fixture", "Fixture"))
        self.announcements = [
            {"decl": "Fixture.triple_pos", "name": "Positivity", "what": None, "about": "x", "prs": [5],
             "source": {"voyager": 101, "stream": 610393}, "at": "2026-10-20T03:30:00Z"},
            {"decl": "Fixture.IsDouble", "name": "Being double", "what": "definition", "about": "y", "prs": [],
             "source": {"voyager": 102, "stream": 610393}, "at": "2026-10-21T03:30:00Z"},
            {"decl": "Fixture.notYet", "name": "Later", "what": "result", "about": "z", "prs": [],
             "source": {"voyager": 103, "stream": 610393}, "at": "2026-10-22T03:30:00Z"},
            {"decl": "Nat", "name": "Not ours", "what": "definition", "about": "w", "prs": [],
             "source": {"voyager": 104, "stream": 610393}, "at": "2026-10-22T03:30:00Z"}]

    def test_announcements_of_the_library_become_named_records(self):
        got = self.store.add(voyager.named_records(self.announcements, self.ds, self.store, SETTINGS))
        self.assertEqual([(r["subject"]["name"], r["what"]) for r in got],
                         [("Fixture.triple_pos", "result"), ("Fixture.IsDouble", "definition")])
        r = got[0]
        self.assertEqual(r["by"], {"kind": "agent", "agent": {"tool": "Voyager"}})
        self.assertEqual(r["origin"], {"kind": "zulip", "ref": "voyager 101"})
        self.assertEqual(r["reference"], {"text": "Voyager, TauCeti#5", "url":
            "https://leanprover.zulipchat.com/#narrow/channel/610393-Tau-Ceti/topic/new.20results/near/101"})
        self.assertEqual(r["subject"]["commit"], "B")

    def test_a_second_run_records_nothing(self):
        self.store.add(voyager.named_records(self.announcements, self.ds, self.store, SETTINGS))
        self.assertEqual(voyager.named_records(self.announcements, self.ds, self.store, SETTINGS), [])


if __name__ == "__main__":
    unittest.main()
````

- [ ] **Step 3: Run them to see them fail**

Run: `.venv/bin/python -m unittest tests.test_voyager -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'voyager'`.

- [ ] **Step 4: Write the reader**

Create `scripts/voyager.py`:

````python
#!/usr/bin/env python3
"""Voyager's announcements of what is new in Tau Ceti, read from its topic on the Lean Zulip, as
`named` records (S3): the named results and notable definitions the site leads with.

  python3 scripts/voyager.py fetch                    read the topic into data/voyager.jsonl, with
                                                      ZULIP_SITE, ZULIP_EMAIL and ZULIP_API_KEY set
  python3 scripts/voyager.py import <messages.json>   the same from a saved API response
  python3 scripts/voyager.py record --dataset DIR [--store DIR]
                                                      a `named` record for each announcement whose
                                                      declaration the dataset has, once each

An announcement is a bullet `- **[<name>](<docs address>#<declaration>)** — <sentence> (TauCeti#<n>)`;
the heading above it (`*Named results*`, `*Notable definitions*`) says whether it is a result or a
definition. One whose declaration the pinned dataset does not have yet is recorded on a later run,
once the pin includes it.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, load_settings  # noqa: E402

from evidence_core import Dataset  # noqa: E402
from evidence_core import records as rec  # noqa: E402
from evidence_core.store import Store  # noqa: E402

ANNOUNCEMENTS = ROOT / "data" / "voyager.jsonl"
STORE = ROOT / "evidence"
VOYAGER = {"kind": "agent", "agent": {"tool": "Voyager"}}
BULLET = re.compile(r"^\s*[-*] \*\*\[(?P<name>.+?)\]\((?P<url>https://[^)\s]+)\)\*\*[†‡*]*\s*(?:[—–-]\s*)?(?P<about>.*)$")
DOCS = re.compile(r"^https://(?:taucetiproject\.github\.io/TauCeti|taucetiproject\.org)/docs/[^#]+\.html#(?P<decl>.+)$")
HEADING = re.compile(r"^\s*\*(?P<title>[^*\s][^*]*?)\*(?:\s|$)")
PRS = re.compile(r"TauCeti#(\d+)")
WHAT = {"named results": "result", "notable definitions": "definition",
        "notable definitions and infrastructure": "definition"}


def iso(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def plain(text: str) -> str:
    """An announcement's sentence without its pull request numbers."""
    text = re.sub(r"\s*\((?:[\s,;]*(?:and\s+)?TauCeti#\d+)+[\s,;]*\)", "", text)
    return text.strip().rstrip(";,").strip()


def parse_post(message: dict) -> list[dict]:
    """The announcements of one message, as the Zulip API returns it with `apply_markdown=false`."""
    out, what = [], None
    for line in (message.get("content") or "").splitlines():
        b = BULLET.match(line)
        if b:
            m = DOCS.match(b["url"])
            if m:
                about = b["about"].strip()
                out.append({"decl": urllib.parse.unquote(m["decl"]), "name": b["name"].strip(), "what": what,
                            "about": plain(about), "prs": [int(n) for n in PRS.findall(about)],
                            "source": {"voyager": message["id"], "stream": message.get("stream_id")},
                            "at": iso(message["timestamp"])})
            continue
        h = HEADING.match(line)
        if h:
            what = WHAT.get(h["title"].strip().lower())
        elif line.lstrip().startswith("**"):
            what = None
    return out


def merge(known: list[dict], new: list[dict]) -> list[dict]:
    """``known`` and the announcements of ``new`` it lacks (by declaration and name), oldest first."""
    seen = {(a["decl"], a["name"]) for a in known}
    out = list(known)
    for a in new:
        if (a["decl"], a["name"]) not in seen:
            seen.add((a["decl"], a["name"]))
            out.append(a)
    return sorted(out, key=lambda a: (a["at"], a["source"]["voyager"]))


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


def post_url(site: str, stream: int | None, channel: str, topic: str, message_id: int) -> str:
    """The link Zulip gives a message in a topic."""
    where = f"{stream}-{channel.replace(' ', '-')}" if stream else urllib.parse.quote(channel)
    return f"{site}/#narrow/channel/{where}/topic/{topic.replace(' ', '.20')}/near/{message_id}"


def named_records(announcements: list[dict], ds: Dataset, store: Store, voyager: dict) -> list[dict]:
    """A `named` record for each announcement whose declaration is one of ``ds``'s own and that
    Voyager has not yet named in ``store``, keyed in ``ds``."""
    done = {r["subject"]["name"] for r in store.records
            if r.get("kind") == "named" and ((r.get("by") or {}).get("agent") or {}).get("tool") == "Voyager"}
    out = []
    for a in announcements:
        d = ds.by_name.get(a["decl"])
        if d is None or not d.is_project or a["decl"] in done:
            continue
        done.add(a["decl"])
        url = post_url(voyager["site"], a["source"].get("stream"), voyager["channel"], voyager["topic"],
                       a["source"]["voyager"])
        out.append({"schema": rec.SCHEMA, "kind": "named", "subject": rec.subject_from_decl(d, ds), "by": VOYAGER,
                    "at": a["at"], "origin": {"kind": "zulip", "ref": f"voyager {a['source']['voyager']}"},
                    "name": a["name"], "what": a["what"] or ("result" if d.is_prop else "definition"),
                    "text": a["about"],
                    "reference": {"text": ", ".join(["Voyager"] + [f"TauCeti#{n}" for n in a["prs"]]), "url": url}})
    return out


def fetch_messages(site: str, email: str, key: str, channel: str, topic: str, sender: str) -> list[dict]:
    """Every message of the topic by ``sender``, oldest first, as the Zulip API returns them."""
    narrow = json.dumps([{"operator": "channel", "operand": channel}, {"operator": "topic", "operand": topic},
                         {"operator": "sender", "operand": sender}])
    auth = "Basic " + base64.b64encode(f"{email}:{key}".encode("utf-8")).decode("ascii")
    anchor, out = "newest", []
    while True:
        params = {"anchor": anchor, "num_before": 1000, "num_after": 0, "narrow": narrow, "apply_markdown": "false"}
        if anchor != "newest":
            params["include_anchor"] = "false"
        req = urllib.request.Request(f"{site}/api/v1/messages?{urllib.parse.urlencode(params)}",
                                     headers={"Authorization": auth})
        with urllib.request.urlopen(req, timeout=60) as r:
            page = json.loads(r.read().decode("utf-8"))
        if page.get("result") != "success":
            raise RuntimeError(f"Zulip: {page.get('msg', page)}")
        messages = page.get("messages", [])
        out = messages + out
        if page.get("found_oldest") or not messages:
            return out
        anchor = str(messages[0]["id"])


def keep(messages: list[dict], path: Path = ANNOUNCEMENTS) -> tuple[int, int]:
    """Adds the announcements of ``messages`` to the file: (new ones, all)."""
    known = read_jsonl(path)
    merged = merge(known, [a for m in messages for a in parse_post(m)])
    write_jsonl(path, merged)
    for m in messages:
        if "**[" in (m.get("content") or "") and not parse_post(m):
            print(f"::warning::Voyager's post {m['id']} links declarations, but no announcement could be read from it")
    return len(merged) - len(known), len(merged)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="voyager.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch")
    sub.add_parser("import").add_argument("messages")
    rec_cmd = sub.add_parser("record")
    rec_cmd.add_argument("--dataset", required=True)
    rec_cmd.add_argument("--store", default=str(STORE), help="the evidence store (default: evidence/)")
    args = p.parse_args(argv)
    v = load_settings()["voyager"]
    if args.cmd == "fetch":
        env = [os.environ.get(k, "") for k in ("ZULIP_SITE", "ZULIP_EMAIL", "ZULIP_API_KEY")]
        if not all(env):
            print("::error::ZULIP_SITE, ZULIP_EMAIL and ZULIP_API_KEY must be set", file=sys.stderr)
            return 1
        new, total = keep(fetch_messages(*env, v["channel"], v["topic"], v["sender"]))
    elif args.cmd == "import":
        data = json.loads(Path(args.messages).read_text(encoding="utf-8"))
        new, total = keep(data["messages"] if isinstance(data, dict) else data)
    else:
        store = Store.load(args.store)
        added = store.add(named_records(read_jsonl(ANNOUNCEMENTS), Dataset.load(args.dataset), store, v))
        print(f"recorded {len(added)} named results")
        return 0
    print(f"{new} new announcements, {total} in all")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
````

- [ ] **Step 5: Run the tests to see them pass**

Run: `.venv/bin/python -m unittest tests.test_voyager -v`
Expected: 9 tests, OK.

- [ ] **Step 6: Commit**

```bash
git add scripts/voyager.py tests/test_voyager.py tests/fixtures
git commit -q -F - <<'EOF'
Voyager's announcements: read from its Zulip topic, kept, and recorded as named results

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 6: Voyager's workflow

**Files:**
- Create: `.github/workflows/voyager.yml`
- Modify: `.github/workflows/follow.yml` (add the job `named`)
- Test: `tests/test_workflows.py` (add `VoyagerWorkflowTests`)

**Interfaces:**
- Consumes: `scripts/voyager.py fetch` and `record --dataset DIR`; the reusable `dataset.yml`; the store's datasets through `evidence-store dataset`.
- Produces: the reusable workflow `./.github/workflows/voyager.yml` (input `site`, default true; output `recorded`); `follow.yml`'s job `named`. Task 9 adds `voyager.yml`'s job `site`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_workflows.py`, before `if __name__ == "__main__":`:

```python
class VoyagerWorkflowTests(unittest.TestCase):
    def test_reads_twice_a_day_and_records(self):
        wf = load("voyager.yml")
        self.assertEqual(wf["on"]["schedule"], [{"cron": "15 4,16 * * *"}])
        self.assertEqual(wf["on"]["workflow_call"]["inputs"]["site"]["default"], True)
        self.assertEqual(wf["on"]["workflow_call"]["outputs"]["recorded"]["value"], "${{ jobs.named.outputs.recorded }}")
        job = wf["jobs"]["named"]
        text = runs(job)
        self.assertIn("python3 scripts/voyager.py fetch", text)
        self.assertIn('python3 scripts/voyager.py record --dataset "$RUNNER_TEMP/dataset"', text)
        env = next(s for s in steps(job) if s.get("id") == "record")["env"]
        self.assertEqual(env["ZULIP_API_KEY"], "${{ secrets.ZULIP_API_KEY }}")

    def test_follow_records_after_a_new_dataset(self):
        named = load("follow.yml")["jobs"]["named"]
        self.assertEqual(named["uses"], "./.github/workflows/voyager.yml")
        self.assertEqual(named["with"], {"site": False})
        self.assertEqual(named["secrets"], "inherit")
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m unittest tests.test_workflows -v`
Expected: the two new tests FAIL (`FileNotFoundError: ... voyager.yml`, `KeyError: 'named'`).

- [ ] **Step 3: The workflow**

Create `.github/workflows/voyager.yml`:

```yaml
name: Voyager

# Twice a day, after Voyager's usual posts: reads its topic on the Lean Zulip (read only, with the
# ZULIP_* secrets), keeps every announcement in data/voyager.jsonl, records a `named` record for each
# whose declaration the pinned dataset has, and rebuilds the site when it recorded any. follow.yml runs
# it too, after a new dataset, with `site: false`, and rebuilds the site itself.
on:
  schedule:
    - cron: '15 4,16 * * *'
  workflow_dispatch:
  workflow_call:
    inputs:
      site:
        type: boolean
        default: true
    outputs:
      recorded:
        description: Whether named records were added to the store
        value: ${{ jobs.named.outputs.recorded }}

permissions:
  contents: write
  pages: write
  id-token: write

concurrency:
  group: voyager
  cancel-in-progress: false

jobs:
  named:
    runs-on: ubuntu-latest
    outputs:
      recorded: ${{ steps.record.outputs.recorded }}
    env:
      GH_TOKEN: ${{ github.token }}
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.ref }}
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -q -r requirements.txt
      - name: The pinned dataset
        run: |
          commit=$(python3 -c "import json; print(json.load(open('data/settings.json'))['tauceti'])")
          evidence-store dataset --store evidence --commit "$commit" --out "$RUNNER_TEMP/dataset" > /dev/null
      - name: Read the topic, record the announcements
        id: record
        env:
          ZULIP_SITE: ${{ secrets.ZULIP_SITE }}
          ZULIP_EMAIL: ${{ secrets.ZULIP_EMAIL }}
          ZULIP_API_KEY: ${{ secrets.ZULIP_API_KEY }}
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          # From the branch's tip: read, record, commit, push; if someone pushed in between, all again
          # (both steps are idempotent).
          for attempt in 1 2 3 4 5; do
            git fetch -q origin "$GITHUB_REF_NAME" && git reset -q --hard "origin/$GITHUB_REF_NAME"
            python3 scripts/voyager.py fetch
            python3 scripts/voyager.py record --dataset "$RUNNER_TEMP/dataset"
            recorded=false
            [ -z "$(git status --porcelain -- evidence)" ] || recorded=true
            if [ -z "$(git status --porcelain -- evidence data/voyager.jsonl)" ]; then
              echo "recorded=false" >> "$GITHUB_OUTPUT"; exit 0
            fi
            git add evidence data/voyager.jsonl
            git commit -q -m "Voyager's announcements, as named results"
            if git push -q origin "HEAD:$GITHUB_REF_NAME"; then echo "recorded=$recorded" >> "$GITHUB_OUTPUT"; exit 0; fi
            sleep $((attempt * 5))
          done
          echo "::error::could not push the named results"; exit 1
```

Add to `follow.yml`, after the job `dataset`:

```yaml
  named:
    needs: [pin, dataset]
    if: always() && needs.pin.result == 'success' && needs.dataset.result != 'failure'
    uses: ./.github/workflows/voyager.yml
    with:
      site: false
    secrets: inherit
    permissions:
      contents: write
      pages: write
      id-token: write
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/bin/python -m unittest tests.test_workflows -v`
Expected: 5 tests, OK.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/voyager.yml .github/workflows/follow.yml tests/test_workflows.py
git commit -q -F - <<'EOF'
Voyager's topic, read twice a day and after each new dataset

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 7: The site's data

**Files:**
- Create: `scripts/site_data.py`, `scripts/build_site.py`, `tests/fixture_site.py`
- Test: `tests/test_build_site.py`

**Interfaces:**
- Consumes: `common.fnv_shard`, `common.ROOT`, `common.load_settings`; `voyager.named_records`; evidence-core's `Dataset`, `Evidence`, `Policy`, `coverage`, `queue`, `Graphs` (`built_from`, `about`, `proof_uses`, `rank_steps`, `reverse()`, `importance`, `basic`, `routine`, `documented`), `views` (`views_on`, `record_view`, `by_view`), `docs` (`module_docs`, `first_sentence`), `source` (`Sources`, `split_statement`), `store` (`Store`, `with_imports`).
- Produces: `site_data.load(dataset, store, imports, source, settings) -> Inputs`; `site_data.Site(inputs, cap=60)` with `node_shards()`, `name_shards()`, `module_file(i)`, `search() -> (names, titles)`, `named_rows()`, `upstream()`, `activity()`, `counts()`, `meta(counts)`, `modules`, `project_modules`; `build_site.build(dataset, store, out, settings, source=None, imports=None, web=ROOT/"web", budget_mb=800, cap=60) -> dict`; `build_site.SiteTooLarge`; `fixture_site.build(out, budget_mb=800, cap=60) -> dict`, `fixture_site.DATASET`. The data files of spec section 5.4, with these shapes (the front end reads them):
  - `nodes/<k>.json`: rows `[name, kind code, flags, module index, title, state people, state with AI, rests on (ids), proof uses (ids), total rests on, total proof uses]`;
  - `names/<k>.json`: rows `[id, name]`; `modules.json`: rows `[name, package, title, path]`;
  - `m/<n>.json`: `{name, title, path, doc, decls: [{id, name, k, doc, kw, line, stmt, rest, cut?, builtOn?, nBuiltOn?, facts?, nFacts?, examples?, nExamples?, usedIn?, nUsedIn?, nRoutine?, records?, tests?}]}` (lists left out when empty; `records` are evidence-core's record views);
  - `search.json`: rows `[name, kind code]`; `titles.json`: the titles, in the same order;
  - `named.json`: rows `{id, decl, name, what, text, area, mod, at, post, prs, people, ai, s: [state, state], cov: [members, reviewed by people, reviewed counting AI, with problems], imp}`;
  - `upstream.json`: `{name: {records, builtOn?, facts?, usedIn?, …}}`; `activity.json`: `{recent, problems, questions, challenges, reviewers, queue}`; `meta.json`: `{site, library: {name, repo, root, docs, commit, date, toolchain}, dataset, store: {repo, name, bulk}, imports, counts, areas: [[area, declarations, named]], shards: {nodes, names}, built}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_build_site.py`:

````python
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))
import build_site  # noqa: E402
import common  # noqa: E402
import fixture_site  # noqa: E402

OUT: Path
RESULT: dict


def setUpModule():
    global OUT, RESULT
    OUT = Path(tempfile.mkdtemp(prefix="site-test-"))
    RESULT = fixture_site.build(OUT / "site")


def tearDownModule():
    shutil.rmtree(OUT, ignore_errors=True)


def data(path: str, root: Path | None = None):
    return json.loads(((root or OUT / "site") / "data" / path).read_text(encoding="utf-8"))


def node_id(name: str, root: Path | None = None) -> int:
    return next(r[0] for r in data(f"names/{common.fnv_shard(name, 64)}.json", root) if r[1] == name)


def node(name: str, root: Path | None = None) -> list:
    i = node_id(name, root)
    return data(f"nodes/{i // 2048}.json", root)[i % 2048]


def entry(name: str, root: Path | None = None) -> dict:
    module = node(name, root)[3]
    return next(e for e in data(f"m/{module}.json", root)["decls"] if e["name"] == name)


class MetaTests(unittest.TestCase):
    def test_the_build(self):
        m = data("meta.json")
        self.assertEqual(m["library"]["commit"], "B")
        self.assertEqual(m["counts"]["declarations"], 21)
        self.assertEqual(m["shards"], {"nodes": 2048, "names": 64})
        self.assertEqual(m["store"], {"repo": "example/fixture-store", "name": "Fixture", "bulk": 1})
        self.assertEqual([(i["name"], i["commit"]) for i in m["imports"]], [("Test imports", "c0ffee")])
        self.assertEqual(m["areas"], [["Basic", 15, 1], ["Uses", 4, 1], ["Notation", 2, 0]])

    def test_every_node_is_found_by_its_name(self):
        rows = [json.loads(l) for l in (fixture_site.DATASET / "decls.jsonl").read_text().splitlines() if l.strip()]
        for r in rows:
            self.assertEqual(node(r["name"])[0], r["name"])


class NodeTests(unittest.TestCase):
    def test_a_definition(self):
        n = node("Fixture.triple")
        self.assertEqual(n[1:5], ["d", 1 | 16, 1, "A definition that version B leaves alone."])
        self.assertEqual(n[5:7], [1, 1])  # covered, by a person; and counting AI agents

    def test_a_named_result_rests_on_the_library_first(self):
        n = node("Fixture.triple_pos")
        self.assertTrue(n[2] & 2)
        self.assertEqual(n[4], "The positivity of triple")
        self.assertEqual(n[7][0], node_id("Fixture.triple"))

    def test_what_a_proof_uses(self):
        self.assertEqual(node("Fixture.one")[8], [node_id("Fixture.one_pos'")])

    def test_states(self):
        self.assertEqual(node("Fixture.double")[5], 3)        # only an earlier version was reviewed
        self.assertEqual(node("Fixture.double_zero")[5], 3)   # stale underneath, which people-only does not count
        self.assertEqual(node("Fixture.IsDouble")[5], 0)


class EntryTests(unittest.TestCase):
    def test_the_source(self):
        e = entry("Fixture.triple")
        self.assertEqual((e["kw"], e["line"]), ("def", [15, 16]))
        self.assertTrue(e["stmt"].startswith("def triple (n : Nat) : Nat"))
        self.assertTrue(e["rest"].startswith(":= n + n + n"))

    def test_what_rests_on_it(self):
        e = entry("Fixture.triple")
        self.assertEqual(e["nFacts"], 6)
        self.assertIn(node_id("Fixture.triple_pos"), e["facts"])
        self.assertNotIn("usedIn", e)

    def test_statuses_reach_the_page(self):
        status = lambda name: [v["status"] for v in entry(name)["records"] if v["kind"] == "review"]
        self.assertEqual(status("Fixture.double_zero"), ["stale-underneath"])
        self.assertEqual(status("Fixture.double"), ["stale"])
        renamed = [v for v in entry("Fixture.triple_three'")["records"] if v["kind"] == "review"][0]
        self.assertEqual((renamed["status"], renamed["renamedFrom"]), ("renamed", "Fixture.triple_three"))
        problem = [v for v in entry("Fixture.one")["records"] if v["kind"] == "review"][0]
        self.assertEqual((problem["verdict"], problem["state"]), ("problem", "invalid"))

    def test_tests_pass(self):
        self.assertEqual([(t["test"], t["result"]) for t in entry("Fixture.triple")["tests"]],
                         [("Fixture.triple_two", "passes")])


class PageFilesTests(unittest.TestCase):
    def test_named(self):
        rows = {r["decl"]: r for r in data("named.json")}
        self.assertEqual(sorted(rows), ["Fixture.IsDouble", "Fixture.triple_pos"])
        r = rows["Fixture.triple_pos"]
        self.assertEqual((r["name"], r["what"], r["prs"], r["area"]), ("The positivity of triple", "result", [5], "Basic"))
        self.assertEqual(r["post"], "https://zulip.example.org/#narrow/channel/610393-Tau-Ceti/topic/new.20results/near/101")
        self.assertEqual(r["cov"], [2, 2, 2, 0])

    def test_search(self):
        names, titles = data("search.json"), data("titles.json")
        self.assertEqual(len(names), 21)
        self.assertEqual(len(titles), 21)
        i = [n[0] for n in names].index("Fixture.triple")
        self.assertEqual((names[i][1], titles[i]), ("d", "A definition that version B leaves alone."))

    def test_upstream(self):
        up = data("upstream.json")
        self.assertEqual(list(up), ["Int"])
        self.assertEqual(up["Int"]["records"][0]["source"], {"repo": "example/imports", "name": "Test imports"})

    def test_activity(self):
        act = data("activity.json")
        self.assertEqual(act["problems"], [])
        self.assertEqual([v["decl"] for v in act["challenges"]], ["Fixture.double"])
        self.assertIn("Claude Code (claude-opus-5-5) via example", [r["label"] for r in act["reviewers"]])

    def test_a_cap_keeps_the_totals(self):
        root = OUT / "capped"
        fixture_site.build(root, cap=2)
        e = entry("Fixture.triple", root)
        self.assertEqual((len(e["facts"]), e["nFacts"]), (2, 6))

    def test_the_budget(self):
        with self.assertRaises(build_site.SiteTooLarge):
            fixture_site.build(OUT / "over", budget_mb=0)


if __name__ == "__main__":
    unittest.main()
````

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m unittest tests.test_build_site -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'build_site'`.

- [ ] **Step 3: What the pages show**

Create `scripts/site_data.py`:

````python
"""Everything the site's pages show, as JSON, laid out from the dataset (S2), the evidence store (S3)
and what evidence-core computes from them. Nothing here judges a record or a declaration:
evidence-core does (statuses, threads, where a declaration stands, coverage, the review queue, the
dependency graphs summarized for readers). This module only arranges what it says, sharded so that a
page loads only what it shows (web/data.js reads it)."""
from __future__ import annotations

import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from evidence_core import docs as docs_mod
from evidence_core import records as rec
from evidence_core import views
from evidence_core.coverage import Evidence, Policy, coverage, queue
from evidence_core.dataset import Dataset, Decl
from evidence_core.graphs import Graphs, is_auxiliary
from evidence_core.source import Sources, split_statement
from evidence_core.store import Store, with_imports

from common import fnv_shard

NODE_SHARD = 2048
NAME_SHARDS = 64
CAP = 60
TEXT_CAP = 4000
#: People only, and people with AI agents; every other switch at evidence-core's default.
POLICIES = (Policy(agents=False), Policy(agents=True))
#: The page's state codes: the index in this tuple.
STATES = ("unreviewed", "covered", "uncounted", "stale", "problem", "disputed")
KIND_CODE = {"theorem": "t", "definition": "d", "structure": "s", "class": "c", "inductive": "n",
             "instance": "i", "axiom": "a", "opaque": "o"}
PROJECT, NAMED, BASIC, ROUTINE, DOCUMENTED, AUX, SORRY = 1, 2, 4, 8, 16, 32, 64


@dataclass
class Inputs:
    ds: Dataset
    ev: Evidence
    store: Store
    #: the imported stores as read: {repo, path, ref, name, commit, records}
    imports: list
    sources: Sources
    settings: dict
    commit_date: str = ""


def load(dataset: Path, store: Path, imports: Path | None, source: Path | None, settings: dict) -> Inputs:
    """The dataset, the store and the stores it imports (fetched into ``imports`` by
    `evidence-store fetch-imports`), resolved by evidence-core."""
    ds = Dataset.load(dataset)
    st = Store.load(store)
    if imports is not None and st.imports:
        imp = with_imports(st, imports)
        records, sources, read = imp.records, imp.sources, imp.read
    else:
        records, sources, read = st.records, {}, []
    ev = Evidence.resolve(records, ds, sources=sources)
    return Inputs(ds=ds, ev=ev, store=st, imports=read, sources=Sources(source), settings=settings,
                  commit_date=commit_date(source, ds.commit))


def commit_date(source: Path | None, commit: str) -> str:
    """When the commit was made, from a checkout of the library; empty without one."""
    if source is None or not (Path(source) / ".git").exists():
        return ""
    out = subprocess.run(["git", "-C", str(source), "log", "-1", "--format=%cI", commit],
                         capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else ""


def area_of(module: str) -> str:
    """The area a module belongs to: the folder under the library's root."""
    parts = module.split(".")
    return parts[1] if len(parts) > 1 else parts[0]


def is_voyagers(r: dict) -> bool:
    return r.get("kind") == "named" and ((r.get("by") or {}).get("agent") or {}).get("tool") == "Voyager"


class Site:
    """The page data of one build."""

    def __init__(self, inp: Inputs, cap: int = CAP):
        self.inp, self.ds, self.ev, self.cap = inp, inp.ds, inp.ev, cap
        ds = self.ds
        self.g = Graphs(ds)
        self.rev = self.g.reverse()
        self.docstrings = {name: rows[0].get("text", "") for name, rows in ds.facet("docstring").items()}
        self.sorry = {name for name, rows in ds.facet("axioms").items() if rows[0].get("sorry")}
        self.named = self._named()
        self.mdocs = docs_mod.module_docs(ds)
        self.project_modules = len(ds.modules)
        self.modules = self._modules()
        self.mod_index = {m[0]: i for i, m in enumerate(self.modules)}
        self.by_module: dict[str, list[Decl]] = defaultdict(list)
        for d in ds.decls:
            if d.is_project:
                self.by_module[d.module].append(d)
        self.states = {ds.by_name[name].id: tuple(STATES.index(self.ev.decl_state(name, p)) for p in POLICIES)
                       for name in self.ev.by_decl if name in ds.by_name}

    # --- what is known of each declaration ---------------------------------------------------------

    def _named(self) -> dict[str, dict]:
        """Current declaration name → Voyager's `named` record about it (the first, not withdrawn)."""
        out = {}
        for name, rows in self.ev.by_decl.items():
            for r, _ in rows:
                if is_voyagers(r) and self.ev.state(r["id"]) != "withdrawn" and name not in out:
                    out[name] = r
        return out

    def _modules(self) -> list[list]:
        """[name, package, title, path]: the project's modules in the dataset's order, then those of the
        other declarations, by name."""
        package = self.ds.meta.get("library", {}).get("package", "")
        rows = [[m["name"], package, self.mdocs[m["name"]].title if m["name"] in self.mdocs else "", m.get("path", "")]
                for m in self.ds.modules]
        own = {r[0] for r in rows}
        others = sorted({(d.module, d.package) for d in self.ds.decls
                         if not d.is_project and d.module and d.module not in own})
        return rows + [[m, p, "", ""] for m, p in others]

    def title(self, d: Decl) -> str:
        """Voyager's name for it, else its docstring's first sentence, else nothing."""
        if d.name in self.named:
            return self.named[d.name].get("name", "")
        doc = self.docstrings.get(d.name)
        return docs_mod.first_sentence(doc) if doc else ""

    def flags(self, d: Decl) -> int:
        i = d.id
        return ((PROJECT if d.is_project else 0) | (NAMED if d.name in self.named else 0)
                | (BASIC if self.g.basic[i] else 0) | (ROUTINE if self.g.routine[i] else 0)
                | (DOCUMENTED if self.g.documented[i] else 0) | (AUX if is_auxiliary(d.name) else 0)
                | (SORRY if d.name in self.sorry else 0))

    def rank(self, ids) -> list[int]:
        """The library's own declarations first, then the others, each most important first."""
        decls, imp = self.ds.decls, self.g.importance
        return sorted(set(ids), key=lambda x: (not decls[x].is_project, -imp[x], decls[x].name))

    def capped(self, ids) -> tuple[list[int], int]:
        ranked = self.rank(ids)
        return ranked[:self.cap], len(ranked)

    def above(self, d: Decl) -> tuple[list[int], int]:
        """What it rests on in meaning: what a theorem (or instance) is about, what anything else is
        built from."""
        if not d.is_project:
            return [], 0
        i = d.id
        return self.capped(self.g.about(i) if (self.g.result[i] or d.kind == "instance") else self.g.built_from(i))

    def proof_steps(self, d: Decl) -> tuple[list[int], int, int]:
        """The results its proof, or the proofs in its value, use: (the non-routine ones, ranked and
        capped; how many those are; how many routine ones there are besides)."""
        if not d.is_project:
            return [], 0, 0
        uses = self.g.proof_uses(d.id)
        steps = [x for x in uses if not self.g.routine[x]]
        ranked = sorted(self.g.rank_steps(steps), key=lambda x: not self.ds.decls[x].is_project)
        return ranked[:self.cap], len(steps), len(uses) - len(steps)

    # --- the files ---------------------------------------------------------------------------------

    def node_row(self, d: Decl) -> list:
        m, nm = self.above(d)
        p, np_, _ = self.proof_steps(d)
        sp, sa = self.states.get(d.id, (0, 0))
        return [d.name, KIND_CODE.get(d.kind, "o"), self.flags(d), self.mod_index.get(d.module, -1), self.title(d),
                sp, sa, m, p, nm, np_]

    def node_shards(self):
        """(k, rows): `nodes/<k>.json`, the nodes with ids k·NODE_SHARD onwards."""
        decls = self.ds.decls
        for k in range(0, len(decls), NODE_SHARD):
            yield k // NODE_SHARD, [self.node_row(d) for d in decls[k:k + NODE_SHARD]]

    def name_shards(self) -> dict[int, list]:
        out: dict[int, list] = defaultdict(list)
        for d in self.ds.decls:
            out[fnv_shard(d.name, NAME_SHARDS)].append([d.id, d.name])
        return out

    def search(self) -> tuple[list[list], list[str]]:
        """`search.json`, every declaration of the library a reader may look for as [name, kind], and
        `titles.json`, their titles in the same order: read second, for searches by words."""
        listed = [d for d in self.ds.decls if d.is_project and not is_auxiliary(d.name)]
        return [[d.name, KIND_CODE.get(d.kind, "o")] for d in listed], [self.title(d)[:80] for d in listed]

    def module_file(self, mi: int) -> dict:
        name, _, title, path = self.modules[mi]
        md = self.mdocs.get(name)
        start = lambda d: ((self.ds.facet_row("source", d.name) or {}).get("start") or [0])[0]
        return {"name": name, "title": title, "path": path, "doc": md.text if md else "",
                "decls": [self.entry(d) for d in sorted(self.by_module.get(name, []), key=start)]}

    def entry(self, d: Decl) -> dict:
        i, name = d.id, d.name
        e: dict = {"id": i, "name": name, "k": KIND_CODE.get(d.kind, "o"), "doc": self.docstrings.get(name, "")}
        src = self.ds.facet_row("source", name)
        if src:
            e["kw"], e["line"] = src.get("keyword", ""), [src["start"][0], src["end"][0]]
            span = self.inp.sources.span(src, doc_comment=False)
            if span:
                stmt, rest = split_statement(span[2])
                e["stmt"], e["rest"] = stmt[:TEXT_CAP], rest[:TEXT_CAP]
                if len(stmt) > TEXT_CAP or len(rest) > TEXT_CAP:
                    e["cut"] = True
        for key, ids in (("builtOn", self.rev.built_on[i]), ("facts", self.rev.facts[i]),
                         ("examples", self.rev.examples[i]), ("usedIn", self.rev.used_in[i])):
            if ids:  # an empty list is left out: most declarations have most of them empty
                e[key], e["n" + key[0].upper() + key[1:]] = self.capped(ids)
        routine = self.proof_steps(d)[2]
        if routine:
            e["nRoutine"] = routine
        if name in self.ev.by_decl:
            e["records"] = views.views_on(self.ev, name)
            tests = [self.test_view(t) for t in self.ev.tests(name)]
            if tests:
                e["tests"] = tests
        return e

    @staticmethod
    def test_view(t: dict) -> dict:
        r = t["record"]
        return {"test": t["test"], "text": t.get("text", ""), "result": t["result"], "mentions": t.get("mentions"),
                "by": views.by_view(r.get("by", {})), "at": r.get("at", ""), "url": rec.origin_url(r.get("origin")),
                "challenge": bool(t.get("challenge"))}

    def upstream(self) -> dict[str, dict]:
        """The declarations outside the library that some record is about (from the imported stores),
        by name: their records, and what of the library rests on them."""
        out = {}
        for name in self.ev.by_decl:
            d = self.ds.by_name.get(name)
            if d is None or d.is_project:
                continue
            e: dict = {"records": views.views_on(self.ev, name)}
            for key, ids in (("builtOn", self.rev.built_on[d.id]), ("facts", self.rev.facts[d.id]),
                             ("usedIn", self.rev.used_in[d.id])):
                if ids:
                    e[key], e["n" + key[0].upper() + key[1:]] = self.capped(ids)
            out[name] = e
        return out

    def accepts(self, name: str) -> tuple[int, int]:
        """The acceptances in force: (by people, by AI agents)."""
        people = ai = 0
        for r, s in self.ev.records_on(name, "review"):
            if r.get("verdict") == "accept" and self.ev.in_force(r, s):
                if (r.get("by") or {}).get("kind") == "agent":
                    ai += 1
                else:
                    people += 1
        return people, ai

    def named_rows(self) -> list[dict]:
        rows = []
        for name, r in self.named.items():
            d = self.ds.by_name[name]
            cov = [coverage(self.ev, name, p) for p in POLICIES]
            ref = r.get("reference") or {}
            people, ai = self.accepts(name)
            rows.append({"id": d.id, "decl": name, "name": r.get("name", ""), "what": r.get("what", ""),
                         "text": r.get("text", ""), "area": area_of(d.module), "mod": self.mod_index.get(d.module, -1),
                         "at": r.get("at", ""), "post": ref.get("url", ""),
                         "prs": [int(n) for n in re.findall(r"TauCeti#(\d+)", ref.get("text", ""))],
                         "people": people, "ai": ai, "s": list(self.states.get(d.id, (0, 0))),
                         "cov": [len(cov[0].members), len(cov[0].covered), len(cov[1].covered), len(cov[0].with_problems)],
                         "imp": round(self.g.importance[d.id], 2)})
        return sorted(rows, key=lambda x: (x["at"], x["decl"]), reverse=True)

    def activity(self) -> dict:
        ev = self.ev
        recent = [views.record_view(ev, r, s, name) for name, rows in ev.by_decl.items() for r, s in rows
                  if not is_voyagers(r)]
        recent.sort(key=lambda v: (v["at"], v["id"]), reverse=True)
        opened = lambda kind, verdict=None: [v for v in recent if v["kind"] == kind and v["state"] == "open"
                                             and (verdict is None or v.get("verdict") == verdict)]
        who, kind_of = Counter(), {}
        for v in recent:
            if v["kind"] in ("review", "test", "challenge", "comment"):
                who[v["by"]["label"]] += 1
                kind_of[v["by"]["label"]] = v["by"]["kind"]
        named = sorted(self.named)
        return {"recent": recent[:40], "problems": opened("review", "problem"), "questions": opened("review", "question"),
                "challenges": opened("challenge"),
                "reviewers": [{"label": k, "kind": kind_of[k], "n": n} for k, n in who.most_common()],
                "queue": [[d.id, w] for d, w in (queue(ev, named, POLICIES[0], limit=60) if named else [])]}

    def areas(self) -> list[list]:
        decls, named = Counter(), Counter()
        for d in self.ds.decls:
            if d.is_project:
                decls[area_of(d.module)] += 1
        for name in self.named:
            named[area_of(self.ds.by_name[name].module)] += 1
        return [[a, n, named[a]] for a, n in decls.most_common()]

    def counts(self) -> dict:
        people = ai = 0
        for name in self.ev.by_decl:
            p, a = self.accepts(name)
            people, ai = people + p, ai + a
        act = self.activity()
        return {"declarations": sum(1 for d in self.ds.decls if d.is_project), "modules": self.project_modules,
                "named": len(self.named), "accepts": {"people": people, "ai": ai},
                "problems": len(act["problems"]), "challenges": len(act["challenges"]),
                "tests": sum(len(self.ev.tests(n)) for n in self.ev.by_decl)}

    def meta(self, counts: dict) -> dict:
        s, ds = self.inp.settings, self.ds
        lib = s["library"]
        return {"site": s["site"],
                "library": {"name": lib["name"], "repo": lib["repo"], "root": lib["root"], "docs": lib["docs"],
                            "commit": ds.commit, "date": self.inp.commit_date, "toolchain": ds.toolchain},
                "dataset": {"producer": ds.producer(), "spec": ds.meta.get("spec", "")},
                "store": {"repo": s["repo"], "name": self.inp.store.name, "bulk": s["bulk_issue"]},
                "imports": [{"name": r["name"], "repo": r["repo"], "commit": r.get("commit"), "records": r["records"]}
                            for r in self.inp.imports],
                "counts": counts, "areas": self.areas(),
                "shards": {"nodes": NODE_SHARD, "names": NAME_SHARDS},
                "built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
````

- [ ] **Step 4: Writing the site**

Create `scripts/build_site.py`:

````python
#!/usr/bin/env python3
"""Build the site in _site/: the front end (web/) and the data its pages read (scripts/site_data.py).

  python3 scripts/build_site.py --dataset DIR --source CHECKOUT [--store evidence] [--imports DIR]
                                [--out _site] [--budget-mb 800]

`--imports` is where `evidence-store fetch-imports` fetched the stores this one imports. The build
fails when the site is larger than its budget: GitHub Pages serves at most 1 GB.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, load_settings  # noqa: E402
import site_data  # noqa: E402


class SiteTooLarge(RuntimeError):
    pass


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def build(dataset: Path, store: Path, out: Path, settings: dict, source: Path | None = None,
          imports: Path | None = None, web: Path = ROOT / "web", budget_mb: int = 800,
          cap: int = site_data.CAP) -> dict:
    started = time.time()
    site = site_data.Site(site_data.load(dataset, store, imports, source, settings), cap=cap)
    if out.exists():
        shutil.rmtree(out)
    if web.exists():
        shutil.copytree(web, out)
    data = out / "data"
    for k, rows in site.node_shards():
        write(data / "nodes" / f"{k}.json", rows)
    for k, rows in site.name_shards().items():
        write(data / "names" / f"{k}.json", rows)
    for mi in range(site.project_modules):
        write(data / "m" / f"{mi}.json", site.module_file(mi))
    write(data / "modules.json", site.modules)
    names, titles = site.search()
    write(data / "search.json", names)
    write(data / "titles.json", titles)
    write(data / "named.json", site.named_rows())
    write(data / "upstream.json", site.upstream())
    write(data / "activity.json", site.activity())
    counts = site.counts()
    write(data / "meta.json", site.meta(counts))
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    if size > budget_mb * 2 ** 20:
        raise SiteTooLarge(f"the site is {size / 2 ** 20:.0f} MB, over its budget of {budget_mb} MB")
    return {**counts, "megabytes": round(size / 2 ** 20, 1), "seconds": round(time.time() - started)}


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="build_site.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset", required=True, type=Path)
    p.add_argument("--source", type=Path)
    p.add_argument("--store", type=Path, default=ROOT / "evidence")
    p.add_argument("--imports", type=Path)
    p.add_argument("--out", type=Path, default=ROOT / "_site")
    p.add_argument("--budget-mb", type=int, default=800)
    a = p.parse_args(argv)
    try:
        result = build(a.dataset, a.store, a.out, load_settings(), a.source, a.imports, budget_mb=a.budget_mb)
    except SiteTooLarge as e:
        print(f"::error::{e}", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
````

- [ ] **Step 5: The fixture's site**

Create `tests/fixture_site.py`:

````python
#!/usr/bin/env python3
"""A small site built from the suite's fixture (tests/fixtures, from LeanTrustBuilders/specs and
LeanTrustBuilders/extractor, Apache-2.0): the declarations of its version B and their sources, the
records of the suite's conformance vectors (made against version A), Voyager's announcements of two of
its declarations, an AI agent's review, a listed test, a proposed test, and a review of an upstream
declaration in a store this one imports. The unit tests and the browser check read it.

  python3 tests/fixture_site.py OUT
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import build_site  # noqa: E402
import voyager  # noqa: E402

from evidence_core import records as rec  # noqa: E402
from evidence_core.dataset import Dataset  # noqa: E402
from evidence_core.store import Store, default_config  # noqa: E402

FIXTURES = HERE / "fixtures"
DATASET = FIXTURES / "dataset-b"
SOURCE = FIXTURES / "source-b"
SETTINGS = {
    "repo": "example/fixture-store", "bulk_issue": 1, "tauceti": "B",
    "library": {"name": "Fixture", "repo": "test/fixture", "root": "Fixture", "docs": "https://example.org/docs"},
    "voyager": {"site": "https://zulip.example.org", "channel": "Tau Ceti", "topic": "new results",
                "sender": "voyager@example.org"},
    "site": {"title": "Tau Ceti Review", "url": "https://example.org/"},
}
ANNOUNCEMENTS = [
    {"decl": "Fixture.triple_pos", "name": "The positivity of triple", "what": "result",
     "about": "`triple n` is positive when $n > 0$.", "prs": [5],
     "source": {"voyager": 101, "stream": 610393}, "at": "2026-10-20T03:30:00Z"},
    {"decl": "Fixture.IsDouble", "name": "Being double", "what": "definition",
     "about": "`m` is twice `n`.", "prs": [7, 8],
     "source": {"voyager": 102, "stream": 610393}, "at": "2026-10-21T03:30:00Z"},
]
PERSON = {"kind": "person", "identity": {"kind": "github", "id": "example"}}
AGENT = {"kind": "agent", "identity": {"kind": "github", "id": "example"},
         "agent": {"tool": "Claude Code", "model": "claude-opus-5-5"}}


def extra_records(ds: Dataset) -> list[dict]:
    """What the vectors lack: an AI agent's review, a listed test, a proposed test."""
    key = lambda name: rec.subject_from_decl(ds.by_name[name], ds)
    issue = lambda n: {"kind": "issue", "ref": f"example/fixture-store#{n}"}
    return [
        {"schema": rec.SCHEMA, "kind": "review", "subject": key("Fixture.triple"), "verdict": "accept", "by": AGENT,
         "text": "Compared with its definition, `n + n + n`.", "at": "2026-10-22T10:00:00Z", "origin": issue(11)},
        {"schema": rec.SCHEMA, "kind": "test", "subject": key("Fixture.triple"), "test": key("Fixture.triple_two"),
         "text": "its value at 2", "by": PERSON, "at": "2026-10-22T11:00:00Z", "origin": issue(12)},
        {"schema": rec.SCHEMA, "kind": "challenge", "subject": key("Fixture.double"),
         "text": "`double n = n + n` for every `n`", "statement": "theorem double_eq (n : Nat) : double n = n + n",
         "by": PERSON, "at": "2026-10-22T12:00:00Z", "origin": issue(13)},
    ]


def imported_store(ds: Dataset, cache: Path) -> None:
    """A store this one imports, as `evidence-store fetch-imports` leaves it, with a review of `Int`."""
    store = Store.init(cache / "example" / "imports" / "evidence", default_config("example/imports", "Int", "Test imports"))
    store.add([{"schema": rec.SCHEMA, "kind": "review", "subject": rec.subject_from_decl(ds.by_name["Int"], ds),
                "verdict": "accept", "by": PERSON, "text": "The integers, as in any textbook.",
                "at": "2026-10-01T00:00:00Z", "origin": {"kind": "issue", "ref": "example/imports#1"}}])
    (cache / "imports.json").write_text(json.dumps([{"repo": "example/imports", "path": "evidence", "commit": "c0ffee"}]))


def build(out: Path, budget_mb: int = 800, cap: int = 60) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="fixture-site-"))
    ds = Dataset.load(DATASET)
    store = Store.init(tmp / "evidence", {**default_config("example/fixture-store", "Fixture", "Fixture"),
                                           "imports": [{"repo": "example/imports"}]})
    store.add(rec.load(FIXTURES / "records.jsonl"))
    store.add(extra_records(ds))
    store.add(voyager.named_records(ANNOUNCEMENTS, ds, store, SETTINGS["voyager"]))
    imported_store(ds, tmp / "imports")
    return build_site.build(DATASET, tmp / "evidence", Path(out), SETTINGS, source=SOURCE, imports=tmp / "imports",
                            budget_mb=budget_mb, cap=cap)


if __name__ == "__main__":
    print(json.dumps(build(Path(sys.argv[1]))))
````

- [ ] **Step 6: Run the tests to see them pass**

Run: `.venv/bin/python -m unittest tests.test_build_site -v`
Expected: 16 tests, OK.

- [ ] **Step 7: Run every test**

Run: `.venv/bin/python -m unittest discover -s tests`
Expected: 46 tests, OK.

- [ ] **Step 8: Commit**

```bash
git add scripts/site_data.py scripts/build_site.py tests/fixture_site.py tests/test_build_site.py
git commit -q -F - <<'EOF'
The site's data: what evidence-core says of each declaration, sharded for the pages

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 8: The front end

**Files:**
- Create: `web/index.html`, `web/style.css`, `web/data.js`, `web/render.js`, `web/map.js`, `web/app.js`, `web/vendor/elk-0.9.3.bundled.js`, `web/vendor/elk-LICENSE.md`, `web/vendor/katex.v0.16.28.min.js`, `web/vendor/KaTeX-LICENSE.txt`, `web/vendor/markdown.js`, `web/vendor/NOTICE`
- Test: `tests/validate_site.py`

**Interfaces:**
- Consumes: the data files of Task 7.
- Produces: `window.TauData` (`json, meta, node, nodes, idOf, decl, moduleByName, fnv, KINDS, FLAG, STATES, modules, named, search, titles, activity, upstream`); `window.TauRender` (`el, link, ext, md, mdInline, glyph, glyphMarkup, planetMarkup, STATE_TEXT, STATE_RING, URLS, FORMS, date, plural, who, shortName, modulePath, plain`); `window.TauMap.draw(host, centerNode, entry, {ai})`; `window.TauReview` (`ready`, `route()`, `mapNodes()`, `fnv`) for the browser check. Routes `#/`, `#/d/<name>`, `#/m/<module>`, `#/area/<Area>`, `#/browse`, `#/search/<q>`, `#/activity`, `#/help`; the old `#d=`, `#m=`, `#q=`, `#area=` addresses redirect.

- [ ] **Step 1: The vendored files**

Fetched from pinned revisions (raw files, not the GitHub API), then checked:

```bash
mkdir -p web/vendor
R=https://raw.githubusercontent.com/LeanTrustBuilders/referee-site/v0.12.0/referee_site/static/vendor
A=https://raw.githubusercontent.com/CBirkbeck/tauceti-explorer/701724066b7ece30a2e553ef64f9bf429d03ff34
curl -sSfL "$R/elk-0.9.3.bundled.js" -o web/vendor/elk-0.9.3.bundled.js
curl -sSfL "$R/elk-LICENSE.md" -o web/vendor/elk-LICENSE.md
curl -sSfL "$A/vendor/katex.v0.16.28.min.js" -o web/vendor/katex.v0.16.28.min.js
curl -sSfL "$A/vendor/KaTeX-LICENSE.txt" -o web/vendor/KaTeX-LICENSE.txt
curl -sSfL "$A/src/markdown.js" -o web/vendor/markdown.js
shasum -a 256 web/vendor/*
```

Expected:

```
b0745abd7f23cd91690a1587e377edbe19fd7233c783300290936720546216d4  web/vendor/elk-0.9.3.bundled.js
89591d4578fb1ebd91501312a3d25f021bd865a2e436641c1cf7b1bc7e3c1617  web/vendor/elk-LICENSE.md
766ccc1f306c885aa45542a9846bbd0a505b27a0374f146778171c2254ce18e3  web/vendor/KaTeX-LICENSE.txt
5e4f3b03c66a3360fe5c070da797900dd74437f58f23957443f4cbd26149f74e  web/vendor/katex.v0.16.28.min.js
506d454a15eb4447dccea27d2a7d24555c8b190489bb1a79c1b72d79b74ddcc5  web/vendor/markdown.js
```

Create `web/vendor/NOTICE`:

```
Files vendored here, unchanged:

- elk-0.9.3.bundled.js, elk-LICENSE.md: elkjs 0.9.3, the Eclipse Layout Kernel (EPL-2.0), as
  LeanTrustBuilders/referee-site vendors it (v0.12.0, referee_site/static/vendor/).
- katex.v0.16.28.min.js, KaTeX-LICENSE.txt: KaTeX 0.16.28 (MIT), as the Tau Ceti Atlas vendors it
  (CBirkbeck/tauceti-explorer at 701724066b7e, vendor/).
- markdown.js: the Tau Ceti Atlas's Markdown renderer (CBirkbeck/tauceti-explorer at 701724066b7e,
  src/markdown.js, Apache-2.0): source HTML stays text, links are filtered, and mathematics becomes
  vetted MathML through KaTeX.

web/map.js adapts referee-site's layered graphs (referee_site/static/core.js: layout,
transitiveReduction, placeWithElk, placeInRows, pan and zoom; Apache-2.0).
```

- [ ] **Step 2: Write the failing browser check**

Create `tests/validate_site.py`:

````python
#!/usr/bin/env python3
"""The browser check: serves a built site as GitHub Pages would and checks, in Chromium, what a
reader does: the shell, the old addresses, the Named page, search, a declaration, its review panel,
its dependency map, the other pages, and a phone. Without --site it builds the fixture's site first
(tests/fixture_site.py).

  python3 tests/validate_site.py [--site DIR | --url URL] [--only NAME,NAME] [--smoke]

`--smoke` checks a real build instead of the fixture's (`--site _site`, or the published site with
`--url`): the pages open without errors, and the first named declarations draw their maps.
Prints one line per check, then PASS (exit 0) or FAIL (exit 1). Errors in the page's console fail
the check that met them.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import sys
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
CHECKS = {}


class Fail(AssertionError):
    pass


def check(fn):
    CHECKS[fn.__name__] = fn
    return fn


def expect(condition, what: str) -> None:
    if not condition:
        raise Fail(what)


def visit(browser, url: str, route: str, errors: list, **context):
    page = browser.new_context(**({"viewport": {"width": 1440, "height": 900}} | context)).new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(url + route, wait_until="load")
    page.wait_for_function("window.TauReview && window.TauReview.ready", timeout=30000)
    return page


def settle(page, route: str) -> None:
    page.wait_for_function(f"TauReview.route() === {route!r} && TauReview.ready", timeout=30000)


@check
def shell(browser, url, errors):
    page = visit(browser, url, "#/", errors)
    expect(page.locator(".brand").inner_text().strip() == "Tau Ceti Review", "the header names the site")
    expect(page.locator("#rail-areas .nav-item").count() == 3, "the rail lists the three areas")
    expect("@ B" in page.locator("#pin").inner_text(), "the header names the pinned commit")
    expect(page.evaluate("[TauReview.fnv('TauCeti.Place', 64), TauReview.fnv('Fixture.«term𝟚_»', 64), TauReview.fnv('ℝ', 64)]")
           == [47, 38, 8], "the page shards names as scripts/common.py does")


@check
def old_addresses(browser, url, errors):
    page = visit(browser, url, "#d=Fixture.double", errors)
    expect(page.evaluate("location.hash") == "#/d/Fixture.double", "#d= opens the declaration")
    page = visit(browser, url, "#q=triple", errors)
    expect(page.evaluate("location.hash") == "#/search/triple", "#q= searches")


@check
def named(browser, url, errors):
    page = visit(browser, url, "#/", errors)
    expect(page.locator(".card").count() == 2, "both announcements are listed")
    page.click("[data-what=definition]")
    expect(page.locator(".card").count() == 1 and "Being double" in page.locator(".card").inner_text(), "the definitions filter")
    page.click(".card .card-title")
    settle(page, "decl:Fixture.IsDouble")
    expect(page.locator("h1").inner_text() == "Being double", "a card opens its declaration, titled by Voyager")


@check
def search(browser, url, errors):
    page = visit(browser, url, "#/", errors)
    page.fill("#q", "triple")
    settle(page, "search:triple")
    expect(page.locator(".nitem .n").first.inner_text().startswith("Fixture.triple"), "a name finds its declarations")
    page.fill("#q", "leaves alone")
    settle(page, "search:leaves alone")
    expect("Fixture.triple" in page.locator(".nitem .n").all_inner_texts(), "words from a title find it")


@check
def declaration(browser, url, errors):
    page = visit(browser, url, "#/d/Fixture.triple", errors)
    expect(page.locator("h1").inner_text() == "A definition that version B leaves alone.", "titled by its docstring")
    expect("def triple (n : Nat) : Nat" in page.locator(".lean pre").first.inner_text(), "its source")
    hrefs = page.eval_on_selector_all(".links a", "as => as.map(a => a.href)")
    expect("https://example.org/docs/Fixture/Basic.html#Fixture.triple" in hrefs, "the API docs")
    expect("https://github.com/test/fixture/blob/B/Fixture/Basic.lean#L15-L16" in hrefs, "the source at the pin")
    expect(page.locator("h2", has_text="Results about it").count() == 1, "what rests on it, as a list")
    page = visit(browser, url, "#/d/Fixture.triple_pos", errors)
    expect(page.locator("details summary", has_text="Proof").count() == 1, "a theorem's proof is folded")


@check
def review(browser, url, errors):
    page = visit(browser, url, "#/d/Fixture.triple", errors)
    expect("1 person · 1 AI" in page.locator(".state-line").inner_text(), "people are counted apart from AI agents")
    href = page.locator(".actions a", has_text="Review this").get_attribute("href")
    expect(href.startswith("https://github.com/example/fixture-store/issues/new?") and "template=evidence-review.yml" in href
           and "decl=Fixture.triple" in href and "commit=B" in href, "Review this opens the form, filled in")
    expect(page.locator(".actions a").count() == 5, "five forms")
    expect(page.locator(".tests .result.passes").count() == 1, "the listed test passes")
    page = visit(browser, url, "#/d/Fixture.double_zero", errors)
    expect("Something it rests on has changed since." in page.locator(".panel").inner_text(), "stale underneath, said")
    page = visit(browser, url, "#/d/Fixture.double", errors)
    panel = page.locator(".panel").inner_text()
    expect("The declaration has changed since." in panel, "stale, said")
    expect(page.locator(".verdict.challenge").count() == 1 and "Open" in panel, "the open suggested test")
    page = visit(browser, url, "#/d/Int", errors)
    expect("From the Test imports store" in page.locator(".panel").inner_text(), "an imported review names its store")
    expect(page.locator(".actions").count() == 0 and page.locator(".map").count() == 0, "no forms and no map outside the library")


@check
def dependency_map(browser, url, errors):
    page = visit(browser, url, "#/d/Fixture.triple_pos", errors)
    map_drawn(page)
    names = page.evaluate("TauReview.mapNodes()")
    expect("Fixture.triple" in names and "Nat" not in names, "what it rests on in the library, Mathlib hidden")
    page.click(".map-tools button:has-text('Mathlib')")
    page.wait_for_function("TauReview.mapNodes().includes('Nat')")
    page.click(".map .node[data-name='Fixture.triple'] rect")
    settle(page, "decl:Fixture.triple")
    page.wait_for_selector(".map .node[data-name='Fixture.triple_pos']")
    page = visit(browser, url, "#/d/Fixture.one", errors)
    page.wait_for_selector(".map .node[data-name]")
    expect("Fixture.one_pos'" not in page.evaluate("TauReview.mapNodes()"), "proofs left out at first")
    page.click(".map-tools button:has-text('Proof uses')")
    page.wait_for_function("TauReview.mapNodes().includes(\"Fixture.one_pos'\")")


@check
def other_pages(browser, url, errors):
    page = visit(browser, url, "#/m/Fixture.Uses", errors)
    expect(page.locator(".nitem").count() >= 4, "a module lists its declarations")
    page = visit(browser, url, "#/area/Basic", errors)
    expect(page.locator(".mitem").count() == 1 and page.locator(".card").count() == 1, "an area: its modules and named")
    page = visit(browser, url, "#/activity", errors)
    expect("double n = n + n" in page.locator(".block", has_text="Suggested tests").inner_text(), "the open suggested test")
    page = visit(browser, url, "#/help", errors)
    expect("Reviewed-by: TauCeti.Foo.bar" in page.inner_text("body"), "the bulk issue's lines")


@check
def phone(browser, url, errors):
    page = visit(browser, url, "#/d/Fixture.triple_pos", errors, viewport={"width": 390, "height": 844},
                 is_mobile=True, has_touch=True)
    expect(not page.locator("#rail").is_visible(), "the rail is folded away")
    page.click("#rail-toggle")
    expect(page.locator("#rail").is_visible(), "Browse opens it")
    expect(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "nothing is wider than the screen")


def map_drawn(page) -> None:
    """Waits for the map to be drawn: nodes, or the sentence that says there are none."""
    page.wait_for_function("document.querySelector('.map .node[data-name]') || [...document.querySelectorAll('.map-wait')]"
                           ".some(e => !e.textContent.startsWith('Drawing'))", timeout=60000)


def smoke(browser, url, errors):
    """Any build: every kind of page opens, and the first named declarations draw their maps."""
    for route in ("#/", "#/browse", "#/activity", "#/help", "#/search/theorem"):
        visit(browser, url, route, errors)
    page = visit(browser, url, "#/", errors)
    expect(page.locator("h1").inner_text() == "Named results and notable definitions", "the Named page")
    names = page.eval_on_selector_all(".card .card-title", "as => as.slice(0, 5).map(a => decodeURIComponent(a.hash.slice(4)))")
    if not names:  # Voyager's announcements not recorded yet: declarations found by a search instead
        page = visit(browser, url, "#/search/theorem", errors)
        names = page.eval_on_selector_all(".nitem", "as => as.slice(0, 5).map(a => decodeURIComponent(a.hash.slice(4)))")
    expect(len(names) == 5, "five declarations to open")
    for name in names:
        page = visit(browser, url, "#/d/" + name, errors)
        map_drawn(page)
        expect(page.locator("h1").count() == 1 and page.locator(".actions a").count() == 5, f"{name}: its page and its forms")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="validate_site.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", type=Path)
    ap.add_argument("--url")
    ap.add_argument("--only", default="")
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args(argv)
    site = a.site
    if site is None and a.url is None:
        sys.path.insert(0, str(HERE))
        import fixture_site
        site = Path(tempfile.mkdtemp(prefix="site-check-")) / "site"
        fixture_site.build(site)

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def handle(self):
            try:
                super().handle()
            except (BrokenPipeError, ConnectionResetError):
                pass  # the browser closed a page while a file was on its way
    server = None
    if a.url:
        url = a.url.rstrip("/") + "/index.html"
    else:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(site)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_address[1]}/index.html"
    checks = {"smoke": smoke} if a.smoke else CHECKS
    names = [n for n in checks if not a.only or n in a.only.split(",")]
    failed = False
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name in names:
            errors: list = []
            try:
                checks[name](browser, url, errors)
                if errors:
                    raise Fail(f"errors in the page: {errors[:3]}")
                print(f"ok    {name}")
            except Exception as e:  # a failed check, a timeout, or the page's own error
                failed = True
                print(f"FAIL  {name}: {e}")
        browser.close()
    if server:
        server.shutdown()
    print("FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
````

- [ ] **Step 3: Run it to see it fail**

Run: `.venv/bin/python tests/validate_site.py`
Expected: every check FAILs, each after its 30-second wait (the fixture's site has no `index.html` yet: `build_site.build` copies `web/` only when it exists), then `FAIL`.

- [ ] **Step 4: The shell**

Create `web/index.html`:

````html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tau Ceti Review</title>
<meta name="description" content="Tau Ceti's declarations, reviewed by people and AI agents: the named results Voyager announced, every review, problem and test, and what each declaration rests on.">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='-8 -8 16 16'%3E%3Ccircle r='7' fill='%230b1016'/%3E%3Ccircle r='3.2' fill='%23dfc186'/%3E%3C/svg%3E">
<link rel="stylesheet" href="style.css">
</head>
<body>
<header class="app-header">
  <button class="quiet rail-toggle" id="rail-toggle" type="button" aria-controls="rail" aria-expanded="false">Browse</button>
  <a class="brand" href="#/"><svg width="16" height="16" viewBox="-8 -8 16 16" aria-hidden="true"><circle r="6.5" fill="none" stroke="#dfc186" stroke-width="1.2"/><circle r="2.6" fill="#dfc186"/></svg>Tau Ceti Review</a>
  <nav class="header-nav" aria-label="Sections">
    <a class="quiet" href="#/" data-nav="named">Named</a>
    <a class="quiet" href="#/browse" data-nav="browse">Browse</a>
    <a class="quiet" href="#/activity" data-nav="activity">Activity</a>
    <a class="quiet keep" href="#/help" data-nav="help">How to review</a>
    <a class="quiet" id="store-link" href="#" target="_blank" rel="noopener">The store</a>
  </nav>
  <span class="pin" id="pin"></span>
</header>
<div class="layout">
  <aside class="rail" id="rail" aria-label="Browse">
    <div class="search-wrap">
      <label class="search-box"><span class="visually-hidden">Search all declarations</span><input id="q" type="search" placeholder="Search all declarations" autocomplete="off" spellcheck="false"><kbd>⌘K</kbd></label>
    </div>
    <nav class="rail-nav" id="rail-nav" aria-label="Lists"></nav>
    <div class="label">Areas</div>
    <nav class="rail-nav areas-nav" id="rail-areas" aria-label="Areas"></nav>
    <label class="switch"><input type="checkbox" id="ai"> Count AI reviews</label>
    <div class="rail-foot" id="rail-foot"></div>
  </aside>
  <main>
    <div class="context" id="context"></div>
    <div class="page" id="page" tabindex="-1"><p class="faint">Loading…</p></div>
  </main>
</div>
<script src="vendor/katex.v0.16.28.min.js" defer></script>
<script src="vendor/markdown.js" defer></script>
<script src="data.js" defer></script>
<script src="render.js" defer></script>
<script src="map.js" defer></script>
<script src="app.js" defer></script>
</body>
</html>
````

Create `web/style.css`:

````css
/* Tau Ceti Review: the Tau Ceti Atlas's surface (tauceti-explorer, src/style.css). One dark palette,
   system type, flat colour, thin rules; colour on a declaration means its review state, nothing else. */
:root{
  --bg:#0b1016;--panel:#0e141b;--raised:#131a22;--hover:#182029;
  --line:#222c37;--line-soft:#1a222b;
  --ink:#e2e6eb;--ink-soft:#b9c2cc;--muted:#8391a0;--faint:#5b6875;
  --accent:#dfc186;--accent-soft:#3a3324;--accent-ink:#17130a;
  --done:#f7f3e9;--active:#e89678;--started:#8f2e26;--problem:#d4604c;
  --ocean:#6f9fcf;--land:#9cc59a;--sand:#d9c391;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI","Helvetica Neue",Helvetica,Arial,sans-serif;
  --mono:ui-monospace,"SFMono-Regular",Menlo,Consolas,monospace;
  --header:48px;--context:40px;--footer:30px;--rail:260px;
  color-scheme:dark;
}
*{box-sizing:border-box;scrollbar-width:thin;scrollbar-color:#3a4652 transparent}
html,body{min-height:100%}
body{margin:0;font:13px/1.55 var(--sans);color:var(--ink);background:var(--bg);-webkit-font-smoothing:antialiased}
a{color:var(--ink-soft);text-underline-offset:3px}
a:hover{color:var(--ink)}
button,input,select{font:inherit;color:inherit}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
::selection{background:#dfc18655}
.visually-hidden{position:absolute!important;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
.faint{color:var(--faint)}.muted{color:var(--muted)}.small{font-size:11.5px}.mono{font-family:var(--mono)}

/* Header. */
.app-header{position:sticky;top:0;z-index:30;height:var(--header);display:flex;align-items:center;gap:14px;padding:0 16px;border-bottom:1px solid var(--line);background:var(--panel)}
.brand{display:flex;align-items:center;gap:9px;font-weight:600;color:var(--ink);text-decoration:none;white-space:nowrap}
.header-nav{display:flex;gap:2px;margin-left:auto}
.quiet{display:inline-flex;align-items:center;gap:6px;padding:6px 9px;border:0;border-radius:4px;background:none;color:var(--muted);font-size:12px;text-decoration:none;white-space:nowrap;cursor:pointer}
.quiet:hover,.quiet.on{background:var(--hover);color:var(--ink)}
.pin{font:11px var(--mono);white-space:nowrap}
.pin a{color:var(--faint);text-decoration:none}
.pin a:hover{color:var(--ink)}
.rail-toggle{display:none}

/* Frame. */
.layout{display:grid;grid-template-columns:var(--rail) minmax(0,1fr);min-height:calc(100vh - var(--header))}
.rail{position:sticky;top:var(--header);height:calc(100vh - var(--header));overflow:auto;display:flex;flex-direction:column;border-right:1px solid var(--line);background:var(--panel)}
main{min-width:0;display:flex;flex-direction:column}
.context{position:sticky;top:var(--header);z-index:20;height:var(--context);display:flex;align-items:center;gap:8px;padding:0 24px;border-bottom:1px solid var(--line-soft);background:var(--bg);color:var(--muted);font-size:12px;white-space:nowrap;overflow:hidden}
.context a{color:var(--muted);text-decoration:none}
.context a:hover{color:var(--ink)}
.context .sep{color:var(--faint)}
.context .here{color:var(--ink);overflow:hidden;text-overflow:ellipsis}
.context .copy{margin-left:auto}
.page{padding:24px 24px 64px;max-width:1280px;width:100%;outline:none}

/* Rail. */
.search-wrap{padding:12px 12px 8px}
.search-box{display:flex;align-items:center;gap:6px;padding:0 8px;border:1px solid var(--line);border-radius:5px;background:var(--bg)}
.search-box:focus-within{border-color:#4a5866}
.search-box input{width:100%;min-width:0;border:0;background:transparent;font-size:12px;padding:7px 0;outline:none}
.search-box input::placeholder{color:var(--faint);opacity:1}
.search-box kbd{font:10px var(--mono);color:var(--faint);white-space:nowrap}
.rail-nav{display:flex;flex-direction:column;padding:0 8px 8px}
#rail-nav{border-bottom:1px solid var(--line-soft)}
.nav-item{display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:4px;color:var(--ink-soft);font-size:12px;text-decoration:none}
.nav-item span{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.nav-item small{font-size:11px;color:var(--faint)}
.nav-item:hover{background:var(--hover);color:var(--ink)}
.label{margin:14px 16px 6px;font-size:10.5px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--faint)}
.switch{display:flex;align-items:center;gap:8px;margin-top:6px;padding:10px 16px;border-top:1px solid var(--line-soft);color:var(--ink-soft);font-size:12px;cursor:pointer}
.switch input{accent-color:var(--accent)}
.rail-foot{margin-top:auto;padding:12px 16px;border-top:1px solid var(--line-soft);color:var(--faint);font-size:11px;line-height:1.7}
.rail-foot a{color:var(--muted)}

/* Type. */
h1{margin:4px 0 8px;font-size:23px;font-weight:600;letter-spacing:-.01em;line-height:1.25}
h2{margin:30px 0 10px;font-size:10.5px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--faint)}
h3{margin:18px 0 8px;font-size:11.5px;font-weight:600;color:var(--muted)}
.kicker{font-size:10.5px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--accent)}
.lede{max-width:760px;margin:0 0 14px;color:var(--ink-soft);font-size:14px}
.prose{max-width:760px;color:var(--ink-soft);font-size:13.5px}
.page-head{margin-bottom:8px}
.block{margin-top:6px}
code{font:12px var(--mono);background:var(--raised);padding:1px 4px;border-radius:3px;color:var(--ink)}
.small-code{margin:8px 0;padding:10px 12px;border:1px solid var(--line-soft);border-radius:5px;background:var(--panel);font:11.5px/1.55 var(--mono);color:var(--ink-soft);overflow:auto;white-space:pre-wrap}
.md{color:var(--ink-soft)}
.md p{margin:0 0 .65em}
.md code{font-size:11.5px}
.md pre{margin:8px 0;padding:10px;border-radius:5px;background:var(--raised);overflow:auto}
.md a{color:var(--accent)}
.md math{font-size:1.05em}
.doc{max-width:800px;font-size:14px;margin:10px 0}
.doc.announce{color:var(--ink);font-size:14.5px}

/* Controls. */
.btn{display:inline-flex;align-items:center;gap:6px;padding:6px 11px;border:1px solid var(--line);border-radius:5px;background:var(--raised);color:var(--ink);font-size:12px;line-height:1.3;text-decoration:none;cursor:pointer;white-space:nowrap}
.btn:hover{background:var(--hover);border-color:#33404d;color:var(--ink)}
.btn.small{padding:3px 8px;font-size:11.5px}
.btn.primary{background:var(--accent);border-color:var(--accent);color:var(--accent-ink);font-weight:600}
.btn.primary:hover{background:#ead19c;color:var(--accent-ink)}
.btn[aria-pressed=true]{border-color:var(--accent);color:var(--accent);background:var(--accent-soft)}
.chip{display:inline-flex;align-items:center;gap:5px;padding:1px 8px;border:1px solid var(--line);border-radius:999px;color:var(--ink-soft);font-size:11px;white-space:nowrap}
.chip.agent{border-color:#4a3a30}
.chip.state-covered{color:var(--done)}.chip.state-uncounted,.chip.state-stale{color:var(--active)}.chip.state-problem,.chip.state-disputed{color:var(--problem)}.chip.state-unreviewed{color:var(--faint)}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:5px;overflow:hidden}
.seg button{padding:5px 11px;border:0;background:none;color:var(--muted);font-size:12px;cursor:pointer}
.seg button+button{border-left:1px solid var(--line)}
.seg button.on{background:var(--raised);color:var(--ink)}
.select{padding:5px 8px;border:1px solid var(--line);border-radius:5px;background:var(--bg);color:var(--ink-soft);font-size:12px}
.filters{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:14px 0 10px}
.filter-input{flex:1;min-width:200px;padding:6px 10px;border:1px solid var(--line);border-radius:5px;background:var(--bg);font-size:12px}
.filter-input::placeholder{color:var(--faint)}
.count{margin:0 0 10px}
.more-box{margin-top:14px}

/* The Named page. */
.stats{display:flex;flex-wrap:wrap;gap:8px 30px;margin:18px 0 6px;padding:14px 18px;border:1px solid var(--line);border-radius:8px;background:var(--panel);width:fit-content;max-width:100%}
.stat b{display:block;font-size:22px;font-weight:600;letter-spacing:-.01em;color:var(--ink)}
.stat span{font-size:11px;color:var(--muted)}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:10px}
.card{position:relative;display:flex;gap:14px;padding:13px 15px;border:1px solid var(--line);border-radius:8px;background:var(--panel)}
.card:hover{background:var(--raised);border-color:#2e3a47}
.card>.glyph{flex:none;margin-top:1px}
.card-body{min-width:0;flex:1}
.card-title{display:block;color:var(--ink);font-size:14px;font-weight:600;line-height:1.35;text-decoration:none}
.stretched::after{content:"";position:absolute;inset:0;border-radius:8px}
.card a:not(.stretched){position:relative;z-index:1}
.card-text{display:-webkit-box;margin-top:4px;color:var(--ink-soft);font-size:12.5px;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.card-meta{margin-top:8px;font:11px var(--mono);color:var(--faint);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.card-facts{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;margin-top:8px;font-size:11px}
.cov{display:inline-flex;align-items:center;gap:6px}
.bar{display:flex;width:76px;height:4px;border-radius:2px;background:var(--line);overflow:hidden}
.bar i{display:block;height:100%}
.b-done{background:var(--done)}.b-ai{background:var(--active)}.b-problem{background:var(--problem)}

/* Browse. */
.areas{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px;margin-top:16px}
.area-tile{display:flex;flex-direction:column;gap:2px;padding:12px 14px;border:1px solid var(--line);border-radius:7px;background:var(--panel);text-decoration:none}
.area-tile:hover{background:var(--raised)}
.area-tile b{color:var(--ink);font-weight:600}
.area-tile span{color:var(--muted);font-size:11.5px}
.mlist{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:2px 16px}
.mitem{display:flex;flex-direction:column;padding:6px 8px;border-radius:4px;text-decoration:none;min-width:0}
.mitem:hover{background:var(--hover)}
.mitem .t,.mitem .n{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mitem .t{color:var(--ink-soft)}.mitem .n{font:11px var(--mono);color:var(--faint)}

/* Lists of declarations. */
.nlist{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:2px 14px}
.nitem{display:flex;align-items:center;gap:9px;padding:5px 7px;border-radius:5px;color:var(--ink-soft);text-decoration:none;min-width:0}
.nitem:hover{background:var(--hover);color:var(--ink)}
.nitem .glyph{flex:none}
.nitem-text{display:flex;flex-direction:column;min-width:0;flex:1}
.nitem .t,.nitem .n{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.nitem .n{font:10.5px var(--mono);color:var(--faint)}
.nitem .weight{flex:none;font-size:11px;color:var(--accent)}
.nbox .more{margin-top:8px}

/* A declaration. */
.decl{display:grid;grid-template-columns:minmax(0,1fr) 380px;gap:30px;align-items:start}
.decl-main{min-width:0}
.kind{display:flex;flex-wrap:wrap;align-items:center;gap:8px;color:var(--muted);font-size:10.5px;font-weight:600;letter-spacing:.12em;text-transform:uppercase}
.kind a{color:var(--muted);letter-spacing:0;text-transform:none;font-weight:400;font-size:12px}
.kind .sep{color:var(--faint)}
.decl-name{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:0 0 8px;font:12.5px var(--mono);color:var(--muted);word-break:break-all}
.links{display:flex;flex-wrap:wrap;gap:14px;margin:2px 0 12px;font-size:12px}
.links a{color:var(--accent)}
.lean{margin:16px 0;border:1px solid var(--line);border-radius:8px;background:var(--panel);overflow:hidden}
.lean pre{margin:0;padding:13px 15px;font:12px/1.6 var(--mono);color:var(--ink);overflow:auto;white-space:pre}
.lean details{border-top:1px solid var(--line-soft)}
.lean summary{padding:8px 15px;color:var(--muted);font-size:12px;cursor:pointer}
.lean details pre{color:var(--ink-soft);border-top:1px solid var(--line-soft)}
.lean .cut{padding:8px 15px;border-top:1px solid var(--line-soft);color:var(--faint);font-size:12px}
.coverage{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:0 0 10px;color:var(--ink-soft);font-size:12.5px}
.lists .block h2{margin-top:22px}

/* The review panel. */
.panel{position:sticky;top:calc(var(--header) + var(--context) + 16px);max-height:calc(100vh - var(--header) - var(--context) - 32px);overflow:auto;padding:14px 16px 16px;border:1px solid var(--line);border-radius:9px;background:var(--panel)}
.panel-title{margin:0 0 12px}
.state-line{display:flex;align-items:center;gap:12px;margin-bottom:12px}
.state-text{color:var(--ink);font-size:14px;font-weight:600}
.actions{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:6px}
.thread{padding:12px 0;border-top:1px solid var(--line-soft)}
.thread.old{opacity:.62}
.thread-head{display:flex;flex-wrap:wrap;align-items:center;gap:6px 8px;color:var(--muted);font-size:12px}
.thread-head a{color:var(--muted)}
.verdict{padding:1px 6px;border-radius:3px;font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase}
.verdict.accept{color:var(--bg);background:var(--done)}
.verdict.problem{color:#fff;background:var(--problem)}
.verdict.question{color:var(--accent-ink);background:var(--accent)}
.verdict.test,.verdict.challenge{color:#0b1016;background:var(--ocean)}
.verdict.named{color:var(--accent);background:var(--accent-soft)}
.verdict.comment{color:var(--muted);background:var(--raised)}
.who{color:var(--ink)}
.who a{color:var(--ink)}
.ai{color:var(--active);font-weight:600}
.from{margin-top:4px;color:var(--accent);font-size:11.5px}
.status-note{margin-top:5px;color:var(--active);font-size:11.5px}
.state-word{margin-top:5px;color:var(--done);font-size:11.5px;font-weight:600}
.state-word.open{color:var(--problem)}
.named-name{margin-top:4px;color:var(--ink);font-weight:600}
.thread .md{margin-top:6px;font-size:12.5px}
.axes{display:flex;flex-wrap:wrap;gap:4px;margin:7px 0 2px}
.reply{margin:8px 0 0 4px;padding-left:10px;border-left:2px solid var(--line)}
.record-actions{margin-top:6px;color:var(--faint);font-size:11.5px}
.record-actions a{font-family:var(--mono);color:var(--muted)}
.decl-link{display:block;margin-bottom:4px;color:var(--accent)}
.tests{margin-top:6px;border-top:1px solid var(--line-soft)}
.test-line{padding:4px 0;font-size:12px;color:var(--ink-soft)}
.result{margin-right:6px;padding:1px 5px;border-radius:3px;font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase}
.result.passes{color:#0b1016;background:var(--land)}
.result.sorry,.result.missing{color:#fff;background:var(--problem)}
.reviewers{display:flex;flex-wrap:wrap;gap:6px}

/* The map. */
.map{position:relative;margin:4px 0;border:1px solid var(--line);border-radius:9px;background:var(--bg);overflow:hidden}
.map-tools{display:flex;flex-wrap:wrap;align-items:center;gap:6px;padding:8px 10px;border-bottom:1px solid var(--line-soft);background:var(--panel)}
.map-tools .hint{margin-left:auto;color:var(--faint);font-size:11px}
.map-canvas{height:460px;touch-action:none;cursor:grab;user-select:none;-webkit-user-select:none}
.map-canvas.dragging{cursor:grabbing}
.map-canvas svg{display:block;width:100%;height:100%}
.map-wait{padding:20px;color:var(--faint)}
.map.full{position:fixed;inset:0;z-index:60;margin:0;border:0;border-radius:0}
.map.full .map-canvas{height:calc(100vh - 46px)}
.map .edge{fill:none;stroke:#3b4753;stroke-width:1.15}
.map .edge.proof{stroke-dasharray:4 3}
.map .edge.hot{stroke:var(--accent);stroke-width:1.7}
.map .node{cursor:pointer}
.map .node rect{fill:var(--raised);stroke:#283440;stroke-width:1}
.map .node:hover rect{fill:var(--hover);stroke:#46525e}
.map .node.center rect{fill:#1a2029;stroke:var(--accent);stroke-width:1.6}
.map .node.upstream rect{fill:var(--panel)}
.map .node text{fill:var(--ink-soft);font:11.5px var(--sans)}
.map .node.center text{fill:var(--ink);font-weight:600}
.map .node.upstream text{fill:var(--muted)}
.map .node.more rect{fill:none;stroke:#3b4753;stroke-dasharray:3 3}
.map .node.more text{fill:var(--muted)}
.map .open circle{fill:var(--panel);stroke:#3b4753}
.map .open text{fill:var(--muted);font-size:10px}
.map .open:hover circle{stroke:var(--accent)}
.map .open:hover text{fill:var(--accent)}

/* Narrow screens. */
@media (max-width:1180px){.decl{grid-template-columns:minmax(0,1fr)}.panel{position:static;max-height:none}}
@media (max-width:760px){
  .layout{grid-template-columns:minmax(0,1fr)}
  .rail{position:fixed;top:var(--header);left:0;right:0;bottom:0;z-index:25;display:none;height:auto}
  body.rail-open .rail{display:flex}
  .rail-toggle{display:inline-flex}
  .header-nav .quiet:not(.keep),.pin{display:none}
  .page{padding:16px 16px 48px}
  .context{padding:0 16px}
  .cards{grid-template-columns:minmax(0,1fr)}
  .map-canvas{height:380px}
  .map-tools .hint{display:none}
  .stats{gap:8px 20px}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important;scroll-behavior:auto!important}}
````

- [ ] **Step 5: Data and drawing**

Create `web/data.js`:

````javascript
/* Tau Ceti Review: the data the build wrote (scripts/site_data.py), fetched as pages need it and
   kept. Nothing is computed here that the build could have: this only finds and unpacks. */
(function () {
  'use strict';
  const cache = new Map();
  function json(path) {
    if (!cache.has(path)) {
      cache.set(path, fetch('data/' + path).then(r => {
        if (!r.ok) throw new Error(`data/${path}: ${r.status}`);
        return r.json();
      }).catch(e => { cache.delete(path); throw e; }));
    }
    return cache.get(path);
  }
  const KINDS = {t: 'theorem', d: 'definition', s: 'structure', c: 'class', n: 'inductive', i: 'instance', a: 'axiom', o: 'opaque'};
  const FLAG = Object.freeze({PROJECT: 1, NAMED: 2, BASIC: 4, ROUTINE: 8, DOCUMENTED: 16, AUX: 32, SORRY: 64});
  const STATES = ['unreviewed', 'covered', 'uncounted', 'stale', 'problem', 'disputed'];
  let META = null;

  /* FNV-1a over UTF-16 code units: the shard of a name in data/names/ (scripts/common.py, fnv_shard). */
  function fnv(name, shards) {
    let h = 0x811C9DC5;
    for (let i = 0; i < name.length; i++) { h ^= name.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
    return h % shards;
  }
  async function meta() { if (!META) META = await json('meta.json'); return META; }
  function unpack(id, r) {
    return {id, name: r[0], kind: KINDS[r[1]] || 'definition', flags: r[2], mod: r[3], title: r[4],
            state: [STATES[r[5]] || 'unreviewed', STATES[r[6]] || 'unreviewed'], m: r[7], p: r[8], nm: r[9], np: r[10]};
  }
  async function node(id) {
    const m = await meta();
    const rows = await json(`nodes/${Math.floor(id / m.shards.nodes)}.json`);
    const r = rows[id % m.shards.nodes];
    return r ? unpack(id, r) : null;
  }
  const nodes = async ids => (await Promise.all([...new Set(ids)].map(node))).filter(Boolean);
  async function idOf(name) {
    const m = await meta();
    const rows = await json(`names/${fnv(name, m.shards.names)}.json`);
    const hit = rows.find(r => r[1] === name);
    return hit ? hit[0] : null;
  }
  /* A declaration: its node, and for one of the library's its entry and module (data/m/<n>.json). */
  async function decl(name) {
    const id = await idOf(name);
    if (id == null) return null;
    const n = await node(id);
    if (!(n.flags & FLAG.PROJECT) || n.mod < 0) return {node: n, entry: null, module: null};
    const module = await json(`m/${n.mod}.json`);
    return {node: n, entry: module.decls.find(e => e.id === id) || null, module};
  }
  async function moduleByName(name) {
    const rows = await json('modules.json');
    const n = rows.findIndex(r => r[0] === name);
    return n < 0 ? null : {index: n, row: rows[n], file: n < (await meta()).counts.modules ? await json(`m/${n}.json`) : null};
  }
  window.TauData = Object.freeze({
    json, meta, node, nodes, idOf, decl, moduleByName, fnv, KINDS, FLAG, STATES,
    modules: () => json('modules.json'), named: () => json('named.json'), search: () => json('search.json'),
    titles: () => json('titles.json'), activity: () => json('activity.json'), upstream: () => json('upstream.json'),
  });
})();
````

Create `web/render.js`:

````javascript
/* Tau Ceti Review: how things look. Elements, Markdown (the Atlas's TauMarkdown: source HTML stays
   text, mathematics becomes vetted MathML), the Atlas's planets ringed by review state, and links. */
(function () {
  'use strict';
  const SVGNS = 'http://www.w3.org/2000/svg';

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function link(href, text, cls) { const a = el('a', cls, text); a.href = href; return a; }
  function ext(href, text, cls) { const a = link(href, text, cls); a.target = '_blank'; a.rel = 'noopener'; return a; }
  /* Markdown from a docstring or a record: always through TauMarkdown, never as HTML. */
  function md(text, cls) {
    const box = el('div', 'md' + (cls ? ' ' + cls : ''));
    box.append(window.TauMarkdown.render(text || ''));
    return box;
  }
  /* One paragraph's content, for a line of text. */
  function mdInline(text, cls) {
    const frag = window.TauMarkdown.render(text || ''), span = el('span', 'md' + (cls ? ' ' + cls : ''));
    if (frag.childNodes.length === 1 && frag.firstChild.nodeName === 'P') {
      while (frag.firstChild.firstChild) span.append(frag.firstChild.firstChild);
    } else span.append(frag);
    return span;
  }

  /* The Atlas's planets (tauceti-explorer, src/graph.js): a definition is an Earth, a theorem a Saturn;
     an instance here is a small grey moon. Colour round them means review state, and nothing else. */
  const OCEAN = '#6f9fcf', LAND = '#9cc59a', SAND = '#d9c391', RING = '#ece0bf', MOON = '#8a96a3', ACCENT = '#dfc186';
  const LAND_PATH = 'M-.55,-.35Q-.3,-.75 .05,-.55Q.3,-.4 .1,-.15Q-.1,.05 -.35,-.05Q-.7,0 -.55,-.35Z' +
    'M.2,.25Q.55,.1 .65,.35Q.6,.65 .3,.7Q.05,.6 .2,.25Z';
  const ringArc = (r, near) => `M${-1.75 * r},0A${1.75 * r},${.42 * r} 0 0,${near ? 0 : 1} ${1.75 * r},0`;
  const STATE_RING = {unreviewed: '#5b6875', covered: '#f7f3e9', uncounted: '#e89678', stale: '#e89678',
                      problem: '#d4604c', disputed: '#d4604c'};
  const STATE_TEXT = {unreviewed: 'Not reviewed yet', covered: 'Reviewed', uncounted: 'Reviewed, by AI agents only',
                      stale: 'Reviewed on an earlier version', problem: 'An open problem', disputed: 'Reviewed, with an open problem'};
  function planetMarkup(kind, r) {
    if (kind === 'instance') return `<circle r="${(r * .72).toFixed(2)}" fill="${MOON}"/>`;
    if (kind === 'theorem' || kind === 'axiom') {
      const ring = near => `<path d="${ringArc(r, near)}" fill="none" stroke="${RING}" stroke-width="1.1" transform="rotate(-18)"/>`;
      return ring(false) + `<circle r="${r}" fill="${SAND}"/>` + ring(true);
    }
    return `<circle r="${r}" fill="${OCEAN}"/><path d="${LAND_PATH}" fill="${LAND}" transform="scale(${r})"/>`;
  }
  /* The planet with its review ring, its gold ring when named, and a sun mark when it is Mathlib's. */
  function glyphMarkup(kind, state, o) {
    const r = o.r, R = r * 1.7;
    let s = '';
    if (o.named) s += `<circle r="${(R + 3).toFixed(2)}" fill="none" stroke="${ACCENT}" stroke-width="1.2"/>`;
    s += `<circle r="${R.toFixed(2)}" fill="none" stroke="${STATE_RING[state] || STATE_RING.unreviewed}" ` +
         `stroke-width="${state === 'unreviewed' ? 1 : 1.7}"${state === 'stale' ? ' stroke-dasharray="2 2"' : ''}/>`;
    if (state === 'disputed') s += `<circle r="${(R - 2).toFixed(2)}" fill="none" stroke="#f7f3e9" stroke-width="1"/>`;
    s += `<g${o.upstream ? ' opacity=".55"' : ''}>${planetMarkup(kind, r)}</g>`;
    if (o.upstream) s += `<circle cx="${(r * 1.25).toFixed(2)}" cy="${(-r * 1.25).toFixed(2)}" r="${Math.max(1.7, r * .34).toFixed(2)}" fill="${ACCENT}"/>`;
    return s;
  }
  function glyph(kind, state, o = {}) {
    const size = o.size || 22, svg = document.createElementNS(SVGNS, 'svg');
    svg.setAttribute('class', 'glyph');
    svg.setAttribute('width', size); svg.setAttribute('height', size);
    svg.setAttribute('viewBox', `${-size / 2} ${-size / 2} ${size} ${size}`);
    svg.setAttribute('aria-hidden', 'true');
    svg.innerHTML = glyphMarkup(kind, state, {...o, r: size / 2 / (o.named ? 2.6 : 2.15)}); // constants only
    return svg;
  }

  const modulePath = mod => mod.split('.').join('/');
  const anchor = name => encodeURIComponent(name);
  const URLS = {
    docs: (meta, name, mod) => `${meta.library.docs}/${modulePath(mod)}.html#${anchor(name)}`,
    source: (meta, path, line) => `https://github.com/${meta.library.repo}/blob/${meta.library.commit}/${path}` +
      (line ? `#L${line[0]}-L${line[1]}` : ''),
    mathlib: (name, mod) => `https://leanprover-community.github.io/mathlib4_docs/${modulePath(mod)}.html#${anchor(name)}`,
    explorer: name => `https://leantrustbuilders.github.io/mathlib-explorer/#/d/${anchor(name)}`,
    github: login => `https://github.com/${encodeURIComponent(login)}`,
    issues: meta => `https://github.com/${meta.store.repo}/issues`,
    bulk: meta => `https://github.com/${meta.store.repo}/issues/${meta.store.bulk}`,
    form: (meta, template, title, name) => `https://github.com/${meta.store.repo}/issues/new?` +
      new URLSearchParams({template, title: title + name, decl: name, commit: meta.library.commit}).toString(),
    decl: name => '#/d/' + encodeURIComponent(name),
  };
  const FORMS = [
    ['Review this', 'evidence-review.yml', 'Review: ', 'primary'],
    ['Report a problem', 'evidence-problem.yml', 'Problem: ', ''],
    ['Suggest a test', 'evidence-challenge.yml', 'Challenge: ', ''],
    ['List a test', 'evidence-test.yml', 'Test: ', ''],
    ['Ask a question', 'evidence-question.yml', 'Question: ', ''],
  ];

  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  function date(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return isNaN(d) ? iso : `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
  }
  const plural = (n, one, many = one + 's') => `${Number(n).toLocaleString('en')} ${n === 1 ? one : many}`;
  /* Who made a record: a person's account, or the AI agent and the account it acted through. */
  function who(by) {
    const span = el('span', 'who');
    if (by.kind === 'agent') {
      const a = by.agent || {};
      span.append(el('span', 'ai', 'AI'), ' · ' + [a.tool || 'agent', a.model].filter(Boolean).join(' · '));
      if (by.login) span.append(' via ', ext(URLS.github(by.login), by.login));
    } else if (by.login) span.append(ext(URLS.github(by.login), by.login));
    else span.append(by.label || 'someone');
    return span;
  }
  /* A docstring's first sentence as plain text, for a link or a label: its Markdown marks dropped. */
  const plain = text => String(text || '').replace(/\*\*|__|`/g, '').replace(/(^|[^\w])[*_]([^*_]+)[*_](?!\w)/g, '$1$2')
    .replace(/\$\$?([^$]+)\$\$?/g, '$1').trim();
  /* A declaration's last name component, or its title when that is short. */
  function shortName(name) {
    const parts = name.split('.');
    let k = parts.length - 1;
    while (k > 0 && /^[a-z_]/.test(parts[k]) === false && parts[k].length < 3) k--;
    return parts.slice(k).join('.');
  }

  window.TauRender = Object.freeze({el, link, ext, md, mdInline, glyph, glyphMarkup, planetMarkup, STATE_TEXT, STATE_RING,
                                    URLS, FORMS, date, plural, who, shortName, modulePath, plain});
})();
````

- [ ] **Step 6: The dependency map**

Create `web/map.js`:

````javascript
/* Tau Ceti Review: the dependency map of a declaration. What it rests on is above it and what rests
   on it below, laid out by ELK's layered algorithm; rows by depth when ELK cannot load. The layout,
   the transitive reduction and the pan and zoom follow referee-site's (LeanTrustBuilders, Apache-2.0),
   with pinch added. Each node is the Atlas's planet, ringed by its review state. */
(function () {
  'use strict';
  const {FLAG} = TauData;
  const {el, glyphMarkup, shortName, plain} = TauRender;
  const LEVEL = 12, SECOND = 4, H = 30;
  const ELK_SRC = 'vendor/elk-0.9.3.bundled.js';
  const esc = s => String(s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  let elkEngine = null;

  function loadElk() {
    if (!elkEngine) elkEngine = new Promise((ok, fail) => {
      if (window.ELK) { ok(new window.ELK()); return; }
      const s = document.createElement('script');
      s.src = ELK_SRC;
      s.onload = () => window.ELK ? ok(new window.ELK()) : fail(new Error('ELK did not load'));
      s.onerror = () => fail(new Error('ELK could not be loaded'));
      document.head.appendChild(s);
    }).catch(e => { elkEngine = null; throw e; });
    return elkEngine;
  }

  const labelOf = n => {
    const t = (n.flags & FLAG.NAMED) && n.title ? plain(n.title) : shortName(n.name);
    return t.length > 34 ? t.slice(0, 33) + '…' : t;
  };
  const widthOf = text => Math.round(Math.min(34, text.length) * 6.4 + 50);
  const rests = (n, proof) => n.m.concat(proof ? n.p.filter(x => !n.m.includes(x)) : []);
  const restOn = (e, proof) => {
    if (!e) return [];
    const ids = [...(e.builtOn || []), ...(e.facts || []), ...(e.examples || [])];
    return proof ? ids.concat((e.usedIn || []).filter(x => !ids.includes(x))) : ids;
  };
  const restOnTotal = (e, proof) => !e ? 0 :
    (e.nBuiltOn || 0) + (e.nFacts || 0) + (e.nExamples || 0) + (proof ? e.nUsedIn || 0 : 0);

  /* The graph to draw: the centre, two levels up, one level down, and the levels the reader opened. */
  async function compose(center, entry, o) {
    const want = n => o.mathlib || (n.flags & FLAG.PROJECT);
    const nodes = new Map(), more = [];
    const put = (n, role) => { if (!nodes.has(n.id)) nodes.set(n.id, {...n, role, key: String(n.id), label: labelOf(n)}); };
    put(center, 'center');
    // A level: what `owner` rests on (or what rests on it), the first `limit`; `counted` levels end in
    // a "+ N more" node, the second level up does not (its nodes open with their arrows).
    const level = async (owner, ids, role, limit, extra, counted = true) => {
      const all = (await TauData.nodes(ids)).filter(want);
      const shown = o.all.has(owner.id + role) ? all : all.slice(0, limit);
      shown.forEach(n => put(n, role));
      const hidden = all.length - shown.length + extra;
      if (counted && hidden > 0) more.push({owner: owner.id, role, count: hidden, open: all.length > shown.length});
      return shown;
    };
    const capExtra = n => o.mathlib ? Math.max(0, (n.nm || 0) - n.m.length) + (o.proof ? Math.max(0, (n.np || 0) - n.p.length) : 0) : 0;
    const up = await level(center, rests(center, o.proof), 'up', LEVEL, capExtra(center));
    for (const n of up) if (n.flags & FLAG.PROJECT) await level(n, rests(n, o.proof), 'up', o.opened.has(n.id) ? LEVEL : SECOND, 0, o.opened.has(n.id));
    await level(center, restOn(entry, o.proof), 'down', LEVEL, Math.max(0, restOnTotal(entry, o.proof) - restOn(entry, o.proof).length));
    for (const id of o.opened) {
      const n = nodes.get(id);
      if (n && n.role === 'down') {
        const d = await TauData.decl(n.name);
        await level(n, restOn(d && d.entry, o.proof), 'down', LEVEL, 0, true);
      }
    }
    // Every edge between nodes drawn, from what each rests on (so shared dependencies join up).
    const edges = [];
    for (const a of nodes.values()) {
      for (const b of a.m) if (nodes.has(b) && b !== a.id) edges.push({a: a.id, b, proof: false});
      if (o.proof) for (const b of a.p) if (nodes.has(b) && b !== a.id && !a.m.includes(b)) edges.push({a: a.id, b, proof: true});
    }
    for (const n of nodes.values()) {
      if (n.role === 'down' && !edges.some(e => e.a === n.id)) edges.push({a: n.id, b: center.id, proof: o.proof});
    }
    const list = [...nodes.values()];
    for (const m of more) {
      const key = `more-${m.owner}-${m.role}`, text = `+ ${m.count.toLocaleString('en')} more`;
      list.push({key, id: key, role: 'more', label: text, owner: m.owner, dir: m.role, open: m.open, flags: 0});
      edges.push(m.role === 'up' ? {a: m.owner, b: key, proof: false} : {a: key, b: m.owner, proof: false});
    }
    list.forEach(n => { n.w = widthOf(n.label); });
    return {nodes: list, edges: reduce(list, edges)};
  }

  /* The edges no longer path implies (referee-site's transitiveReduction). */
  function reduce(nodes, edges) {
    const adj = new Map(nodes.map(n => [String(n.key), new Set()]));
    const proof = new Map();
    for (const e of edges) {
      const a = String(e.a), b = String(e.b);
      if (adj.has(a) && adj.has(b) && a !== b) { adj.get(a).add(b); proof.set(a + '>' + b, e.proof && !proof.get(a + '>' + b)); }
    }
    const reach = (a, skip) => {
      const seen = new Set(), stack = [...adj.get(a)].filter(x => x !== skip);
      while (stack.length) { const x = stack.pop(); if (seen.has(x)) continue; seen.add(x); stack.push(...adj.get(x)); }
      return seen;
    };
    const out = [];
    for (const [a, bs] of adj) for (const b of bs) if (!reach(a, b).has(b)) out.push({a, b, proof: proof.get(a + '>' + b)});
    return out;
  }

  /* Where things go: ELK's layered layout, top-down, dependencies above. */
  function sectionPath(sec, dx, dy) {
    const pts = [sec.startPoint, ...(sec.bendPoints || []), sec.endPoint].map(p => `${(p.x + dx).toFixed(1)},${(p.y + dy).toFixed(1)}`);
    let d = `M${pts[0]}`;
    if ((pts.length - 1) % 3 === 0) { for (let i = 1; i + 2 < pts.length; i += 3) d += `C${pts[i]} ${pts[i + 1]} ${pts[i + 2]}`; return d; }
    return d + 'L' + pts.slice(1).join('L');
  }
  async function placeWithElk(g) {
    const elk = await loadElk();
    const res = await elk.layout({id: 'root',
      layoutOptions: {'elk.algorithm': 'layered', 'elk.direction': 'DOWN', 'elk.edgeRouting': 'SPLINES',
        'elk.spacing.nodeNode': '16', 'elk.layered.spacing.nodeNodeBetweenLayers': '44',
        'elk.layered.spacing.edgeNodeBetweenLayers': '14', 'elk.spacing.edgeNode': '10', 'elk.spacing.edgeEdge': '6',
        'elk.layered.nodePlacement.strategy': 'BRANDES_KOEPF', 'elk.padding': '[top=20,left=20,bottom=20,right=20]'},
      children: g.nodes.map(n => ({id: 'n' + n.key, width: n.w, height: H})),
      edges: g.edges.map((e, i) => ({id: 'e' + i, sources: ['n' + e.b], targets: ['n' + e.a]}))});
    const coords = new Map((res.children || []).map(c => [c.id.slice(1), {x: c.x, y: c.y}]));
    const byEdge = new Map((res.edges || []).map(e => [e.id, e]));
    const paths = g.edges.map((e, i) => { const s = byEdge.get('e' + i)?.sections?.[0]; return s ? sectionPath(s, 0, 0) : ''; });
    return {coords, paths, width: res.width, height: res.height};
  }
  /* Without ELK: rows by longest path, each centred, one curve per edge. */
  function placeInRows(g) {
    const deps = new Map(g.nodes.map(n => [n.key, []]));
    g.edges.forEach(e => deps.get(e.a)?.push(e.b));
    const depth = new Map(), visiting = new Set();
    const d = k => {
      if (depth.has(k)) return depth.get(k);
      if (visiting.has(k)) return 0;
      visiting.add(k);
      let r = 0;
      for (const t of deps.get(k) || []) r = Math.max(r, d(t) + 1);
      visiting.delete(k); depth.set(k, r); return r;
    };
    const rows = [];
    g.nodes.forEach(n => (rows[d(n.key)] ||= []).push(n));
    rows.reverse();
    const coords = new Map(), GAP = 16, ROW = H + 44;
    let width = 0;
    rows.forEach(r => { width = Math.max(width, (r || []).reduce((s, n) => s + n.w + GAP, -GAP)); });
    rows.forEach((r, k) => {
      let x = (width - (r || []).reduce((s, n) => s + n.w + GAP, -GAP)) / 2 + 20;
      (r || []).forEach(n => { coords.set(n.key, {x, y: 20 + k * ROW}); x += n.w + GAP; });
    });
    const byKey = new Map(g.nodes.map(n => [n.key, n]));
    const paths = g.edges.map(e => {
      const p = coords.get(e.b), q = coords.get(e.a);
      if (!p || !q) return '';
      const x1 = p.x + byKey.get(e.b).w / 2, y1 = p.y + H, x2 = q.x + byKey.get(e.a).w / 2, y2 = q.y, m = (y1 + y2) / 2;
      return `M${x1},${y1} C${x1},${m} ${x2},${m} ${x2},${y2}`;
    });
    return {coords, paths, width: width + 40, height: rows.length * ROW + 40};
  }

  function markup(g, P, ai) {
    let s = '<g class="vp">';
    g.edges.forEach((e, i) => {
      if (P.paths[i]) s += `<path class="edge${e.proof ? ' proof' : ''}" data-a="${esc(e.a)}" data-b="${esc(e.b)}" d="${P.paths[i]}"/>`;
    });
    for (const n of g.nodes) {
      const c = P.coords.get(n.key);
      if (!c) continue;
      if (n.role === 'more') {
        s += `<g class="node more" data-more="${esc(n.key)}" tabindex="0" role="button" transform="translate(${c.x},${c.y})">` +
          `<rect width="${n.w}" height="${H}" rx="${H / 2}"/><text x="${n.w / 2}" y="19" text-anchor="middle">${esc(n.label)}</text>` +
          `<title>${n.open ? 'Show them' : 'More than the map keeps: see the lists below'}</title></g>`;
        continue;
      }
      const project = !!(n.flags & FLAG.PROJECT), state = n.state[ai ? 1 : 0];
      const canOpen = project && n.role !== 'center';
      s += `<g class="node ${n.role}${project ? '' : ' upstream'}" data-name="${esc(n.name)}" tabindex="0" role="link" transform="translate(${c.x},${c.y})">` +
        `<rect width="${n.w}" height="${H}" rx="${H / 2}"/>` +
        `<g transform="translate(16,${H / 2})">${glyphMarkup(n.kind, state, {r: 4.6, named: !!(n.flags & FLAG.NAMED), upstream: !project})}</g>` +
        `<text x="32" y="19">${esc(n.label)}</text>` +
        (canOpen ? `<g class="open" data-open="${n.id}" transform="translate(${n.w - 13},${H / 2})"><circle r="8"/><text y="4" text-anchor="middle">${n.role === 'up' ? '↑' : '↓'}</text><title>Show what ${n.role === 'up' ? 'it rests on' : 'rests on it'}</title></g>` : '') +
        `<title>${esc(n.name + (n.title && plain(n.title) !== n.label ? ' — ' + plain(n.title) : ''))}</title></g>`;
    }
    return s + '</g>';
  }

  /* Pan, zoom and pinch; a press that does not move is a click. */
  function interact(canvas, svg, vp, size, centerAt, onClick) {
    let tx = 0, ty = 0, sc = 1;
    const apply = () => vp.setAttribute('transform', `translate(${tx},${ty}) scale(${sc})`);
    const fit = () => {
      const b = canvas.getBoundingClientRect();
      const s = Math.min(b.width / size.width, b.height / size.height, 1.2);
      if (s >= 0.55 || !centerAt) { sc = s; tx = (b.width - size.width * s) / 2; ty = (b.height - size.height * s) / 2; }
      else { sc = 0.8; tx = b.width / 2 - centerAt.x * sc; ty = b.height / 2 - centerAt.y * sc; }
      apply();
    };
    const zoomAt = (mx, my, f) => { f = Math.min(Math.max(sc * f, 0.2), 3) / sc; tx = mx - (mx - tx) * f; ty = my - (my - ty) * f; sc *= f; apply(); };
    canvas.addEventListener('wheel', e => {
      e.preventDefault();
      const b = canvas.getBoundingClientRect();
      zoomAt(e.clientX - b.left, e.clientY - b.top, Math.exp(-e.deltaY * 0.0015));
    }, {passive: false});
    const pointers = new Map();
    let press = null, pinch = null;
    canvas.addEventListener('pointerdown', e => {
      if (e.button !== 0) return;
      pointers.set(e.pointerId, {x: e.clientX, y: e.clientY});
      if (pointers.size === 2) {
        const [p, q] = [...pointers.values()];
        pinch = {d: Math.hypot(p.x - q.x, p.y - q.y), sc};
        press = null;
      } else press = {x: e.clientX, y: e.clientY, tx, ty, target: e.target, drag: false, id: e.pointerId};
    });
    canvas.addEventListener('pointermove', e => {
      if (!pointers.has(e.pointerId)) return;
      pointers.set(e.pointerId, {x: e.clientX, y: e.clientY});
      if (pinch && pointers.size === 2) {
        const [p, q] = [...pointers.values()], b = canvas.getBoundingClientRect();
        zoomAt((p.x + q.x) / 2 - b.left, (p.y + q.y) / 2 - b.top, pinch.sc * Math.hypot(p.x - q.x, p.y - q.y) / pinch.d / sc);
        return;
      }
      if (!press) return;
      if (!press.drag && Math.hypot(e.clientX - press.x, e.clientY - press.y) > 4) {
        press.drag = true; canvas.setPointerCapture(press.id); canvas.classList.add('dragging');
      }
      if (press.drag) { tx = press.tx + e.clientX - press.x; ty = press.ty + e.clientY - press.y; apply(); }
    });
    const end = e => {
      pointers.delete(e.pointerId);
      if (pointers.size < 2) pinch = null;
      const p = press;
      press = null;
      canvas.classList.remove('dragging');
      if (p && !p.drag && e.type === 'pointerup') onClick(p.target);
    };
    canvas.addEventListener('pointerup', end);
    canvas.addEventListener('pointercancel', end);
    return {fit, zoom: f => { const b = canvas.getBoundingClientRect(); zoomAt(b.width / 2, b.height / 2, f); }};
  }

  /* Draws the map of `center` (a TauData node) in `host`; `entry` is its module entry, null for a
     declaration outside the library. `ai()` says whether the reader counts AI reviews. */
  function draw(host, center, entry, opts) {
    const o = {proof: false, mathlib: false, opened: new Set(), all: new Set()};
    const ai = (opts && opts.ai) || (() => false);
    host.replaceChildren();
    const box = el('div', 'map'), tools = el('div', 'map-tools'), canvas = el('div', 'map-canvas');
    const toggle = (text, key, title) => {
      const b = el('button', 'btn small', text);
      b.type = 'button'; b.title = title; b.setAttribute('aria-pressed', String(o[key]));
      b.addEventListener('click', () => { o[key] = !o[key]; b.setAttribute('aria-pressed', String(o[key])); render(); });
      return b;
    };
    const action = (text, fn, title) => { const b = el('button', 'btn small', text); b.type = 'button'; b.title = title; b.addEventListener('click', fn); return b; };
    let view = null;
    tools.append(toggle('Proof uses', 'proof', 'Add the results its proof uses (dashed), and the proofs that use it'),
                 toggle('Mathlib', 'mathlib', "Show the declarations from Mathlib and Lean's core it rests on"),
                 action('Fit', () => view && view.fit(), 'Fit the map to the frame'),
                 action('Full screen', () => { box.classList.toggle('full'); requestAnimationFrame(() => view && view.fit()); }, 'Fill the window; again to return'),
                 el('span', 'hint', 'Click to open · ↑ ↓ to unfold · drag to move · scroll or pinch to zoom'));
    box.append(tools, canvas);
    host.append(box);
    let gen = 0;
    async function render() {
      const mine = ++gen;
      canvas.replaceChildren(el('p', 'map-wait', 'Drawing the map…'));
      const g = await compose(center, entry, o);
      let P;
      try { P = await placeWithElk(g); } catch (e) { P = placeInRows(g); }
      if (mine !== gen || !canvas.isConnected) return;
      if (g.nodes.length <= 1) {
        canvas.style.height = '';
        canvas.replaceChildren(el('p', 'map-wait', o.mathlib ? 'It rests on nothing drawn here, and nothing here rests on it.'
          : 'Within Tau Ceti it rests on nothing, and nothing rests on it: turn on Mathlib to see what it is built from.'));
        return;
      }
      // As tall as the drawing needs, at the scale that fits its width.
      const wide = canvas.getBoundingClientRect().width || 700;
      canvas.style.height = Math.round(Math.max(240, Math.min(560, P.height * Math.min(1.2, wide / P.width) + 30))) + 'px';
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.innerHTML = markup(g, P, ai()); // names escaped; titles escaped; everything else ours
      canvas.replaceChildren(svg);
      const vp = svg.querySelector('.vp'), at = P.coords.get(String(center.id));
      view = interact(canvas, svg, vp, P, at && {x: at.x + labelOf(center).length * 3.2 + 25, y: at.y + H / 2}, target => {
        const open = target.closest('[data-open]'), moreNode = target.closest('[data-more]'), node = target.closest('[data-name]');
        if (open) { o.opened.add(+open.dataset.open); render(); }
        else if (moreNode) { const m = g.nodes.find(n => n.key === moreNode.dataset.more); if (m && m.open) { o.all.add(m.owner + m.dir); render(); } }
        else if (node && node.dataset.name !== center.name) location.hash = TauRender.URLS.decl(node.dataset.name);
      });
      svg.querySelectorAll('.node[data-name]').forEach(n => {
        n.addEventListener('keydown', e => { if (e.key === 'Enter') location.hash = TauRender.URLS.decl(n.dataset.name); });
        n.addEventListener('mouseenter', () => svg.querySelectorAll('.edge').forEach(p => {
          const k = n.dataset.name, keyOf = g.nodes.find(x => x.name === k)?.key;
          p.classList.toggle('hot', p.dataset.a === keyOf || p.dataset.b === keyOf);
        }));
        n.addEventListener('mouseleave', () => svg.querySelectorAll('.edge.hot').forEach(p => p.classList.remove('hot')));
      });
      requestAnimationFrame(() => view.fit());
    }
    render();
    return {redraw: render};
  }

  window.TauMap = Object.freeze({draw});
})();
````

- [ ] **Step 7: The pages**

Create `web/app.js`:

````javascript
/* Tau Ceti Review: the pages. A hash router (#/…), the rail, and one function per page. Everything
   shown comes from TauData (what the build wrote), laid out with TauRender and TauMap. */
(function () {
  'use strict';
  const {el, link, ext, md, mdInline, glyph, URLS, FORMS, date, plural, who, shortName, STATE_TEXT, modulePath, plain} = TauRender;
  const {FLAG, STATES} = TauData;
  const $ = id => document.getElementById(id);
  const page = $('page'), context = $('context');
  let generation = 0, ready = false, current = '';
  let ai = false;
  try { ai = localStorage.getItem('tauceti-review:ai') === '1'; } catch (e) { /* no storage: the default */ }
  const pick = pair => pair[ai ? 1 : 0];
  const stateOf = n => pick(n.state);
  const rowState = r => STATES[pick(r.s)] || 'unreviewed';
  const kindWord = {theorem: 'Theorem', definition: 'Definition', structure: 'Structure', class: 'Class',
                    inductive: 'Inductive type', instance: 'Instance', axiom: 'Axiom', opaque: 'Definition'};

  /* --- addresses ---------------------------------------------------------------------------------- */
  function parse(hash) {
    const h = (hash || '').replace(/^#/, '');
    if (h && !h.startsWith('/') && h.includes('=')) {          // the old site's addresses: #d=…&m=…&q=…
      const p = new URLSearchParams(h);
      if (p.get('d')) return ['decl', p.get('d')];
      if (p.get('m')) return ['module', p.get('m')];
      if (p.get('q')) return ['search', p.get('q')];
      if (p.get('area')) return ['area', p.get('area')];
      return ['named'];
    }
    const [head, ...rest] = h.replace(/^\//, '').split('/');
    const arg = decodeURIComponent(rest.join('/'));
    return ({'': ['named'], d: ['decl', arg], m: ['module', arg], area: ['area', arg], search: ['search', arg],
             browse: ['browse'], activity: ['activity'], help: ['help']})[head] || ['missing', h];
  }
  const address = r => ({named: '#/', decl: '#/d/', module: '#/m/', area: '#/area/', search: '#/search/',
                         browse: '#/browse', activity: '#/activity', help: '#/help'})[r[0]] + (r[1] != null ? encodeURIComponent(r[1]) : '');

  /* --- frame ---------------------------------------------------------------------------------------- */
  function setContext(trail) {
    context.replaceChildren();
    trail.forEach(([text, href], i) => {
      if (i) context.append(el('span', 'sep', '›'));
      context.append(href ? link(href, text) : el('span', 'here', text));
    });
    const copy = el('button', 'quiet copy', 'Copy link');
    copy.type = 'button';
    copy.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(location.href); copy.textContent = 'Copied'; } catch (e) { copy.textContent = 'Copy the address bar'; }
      setTimeout(() => { copy.textContent = 'Copy link'; }, 1500);
    });
    context.append(copy);
  }
  function setNav(which) {
    document.querySelectorAll('[data-nav]').forEach(a => a.classList.toggle('on', a.dataset.nav === which));
  }
  function show(...nodes) { page.replaceChildren(...nodes); page.scrollTop = 0; window.scrollTo(0, 0); }
  function section(title, ...body) { const s = el('section', 'block'); s.append(el('h2', null, title), ...body); return s; }
  const areaOf = module => { const p = module.split('.'); return p.length > 1 ? p[1] : p[0]; };
  async function moduleTrail(module) {
    const meta = await TauData.meta();
    const tail = module.split('.').slice(1).join('.') || module, area = areaOf(module);
    return [[meta.library.name, '#/browse'], [area, '#/area/' + encodeURIComponent(area)],
            ...(tail !== area ? [[tail, '#/m/' + encodeURIComponent(module)]] : [])];
  }

  /* --- small parts ---------------------------------------------------------------------------------- */
  function nodeItem(n) {
    const a = link(URLS.decl(n.name), null, 'nitem');
    a.append(glyph(n.kind, stateOf(n), {size: 20, named: !!(n.flags & FLAG.NAMED), upstream: !(n.flags & FLAG.PROJECT)}));
    const text = el('span', 'nitem-text');
    text.append(el('span', 't', plain(n.title) || shortName(n.name)), el('span', 'n', n.name));
    a.append(text);
    a.title = `${kindWord[n.kind] || 'Declaration'} · ${STATE_TEXT[stateOf(n)]}`;
    return a;
  }
  /* A ranked list of declarations: the first dozen, then all that the data keeps, then a count. */
  async function nodeList(ids, total, empty) {
    const box = el('div', 'nbox');
    if (!ids || !ids.length) { box.append(el('p', 'faint', empty)); return box; }
    const items = await TauData.nodes(ids), list = el('div', 'nlist');
    const fill = k => list.replaceChildren(...items.slice(0, k).map(nodeItem));
    fill(12);
    box.append(list);
    if (items.length > 12) {
      const b = el('button', 'btn small more', `Show all ${items.length}`);
      b.type = 'button';
      b.addEventListener('click', () => { fill(items.length); b.remove(); });
      box.append(b);
    }
    if (total > ids.length) box.append(el('p', 'faint small', `and ${plural(total - ids.length, 'more')} not listed`));
    return box;
  }
  function verdictBadge(v) {
    const words = {review: {accept: 'Reviewed', problem: 'Problem', question: 'Question'}[v.verdict] || 'Review',
                   test: 'Test', challenge: 'Suggested test', named: 'Named', comment: 'Reply'};
    const kind = v.kind === 'review' ? v.verdict : v.kind;
    return el('span', 'verdict ' + kind, words[v.kind] || v.kind);
  }
  function statusNote(v) {
    return ({'stale-underneath': 'Something it rests on has changed since.', stale: 'The declaration has changed since.',
             renamed: `Written about ${v.renamedFrom}, renamed since.`, unavailable: 'Its module did not build at this commit.',
             orphaned: 'The declaration is gone.', incomparable: 'Made with another hasher: cannot be compared.'})[v.status] || '';
  }
  const STATE_WORDS = {fixed: 'Fixed', intended: 'Behaves as intended', invalid: 'Not a problem', answered: 'Answered',
                       met: 'Met', failed: 'Failed', declined: 'Declined', withdrawn: 'Withdrawn', open: 'Open'};
  function thread(v, byId) {
    const box = el('article', 'thread' + (v.applies === false || !v.inForce ? ' old' : ''));
    const head = el('div', 'thread-head');
    head.append(verdictBadge(v), who(v.by), el('span', 'faint', date(v.at)));
    if (v.url) head.append(ext(v.url, 'issue', 'faint'));
    box.append(head);
    if (v.source) box.append(el('div', 'from', `From the ${v.source.name} store`));
    const note = statusNote(v);
    if (note) box.append(el('div', 'status-note', note));
    if (v.state && !['stands', 'open'].includes(v.state)) box.append(el('div', 'state-word', STATE_WORDS[v.state] || v.state));
    else if (v.state === 'open' && v.kind !== 'review' || (v.kind === 'review' && v.verdict !== 'accept' && v.state === 'open')) box.append(el('div', 'state-word open', 'Open'));
    if (v.kind === 'named') box.append(el('div', 'named-name', v.name));
    if (v.kind === 'test' && v.test) box.append(link(URLS.decl(v.test), v.test, 'mono small'));
    if (v.category) box.append(el('div', 'faint small', 'What is wrong: ' + v.category));
    const checked = Object.entries(v.checked || {}).filter(([, s]) => s === 'checked').map(([axis]) => axis);
    if (checked.length) { const axes = el('div', 'axes'); checked.forEach(a => axes.append(el('span', 'chip', a))); box.append(axes); }
    if (v.reference && (v.reference.text || v.reference.url)) {
      const ref = el('div', 'faint small');
      ref.append(v.kind === 'named' ? 'From: ' : 'Compared with: ');
      ref.append(v.reference.url ? ext(v.reference.url, v.reference.text || v.reference.url) : v.reference.text);
      box.append(ref);
    }
    if (v.text) box.append(md(v.text));
    if (v.statement) { const pre = el('pre', 'small-code'); pre.textContent = v.statement; box.append(pre); }
    if (v.fix) { box.append(el('div', 'faint small', 'Suggested fix:'), md(v.fix)); }
    for (const id of v.replies || []) {
      const r = byId.get(id);
      if (!r) continue;
      const reply = el('div', 'reply'), rh = el('div', 'thread-head');
      rh.append(who(r.by), el('span', 'faint', date(r.at)));
      reply.append(rh, md(r.text));
      box.append(reply);
    }
    for (const s of v.statuses || []) {
      const line = el('div', 'faint small');
      line.append(`${STATE_WORDS[s.state] || s.state} by `, who(s.by), ` on ${date(s.at)}`);
      if (s.text) line.append(': ', mdInline(s.text));
      box.append(line);
    }
    if (v.actions && v.actions.length && v.url) {
      const acts = el('div', 'record-actions');
      acts.append('On its issue: ');
      v.actions.forEach((a, i) => { if (i) acts.append(' · '); acts.append(ext(v.url, '/' + a)); });
      box.append(acts);
    }
    return box;
  }

  /* --- pages ---------------------------------------------------------------------------------------- */
  const VIEWS = {};

  VIEWS.named = async (arg, gen) => {
    const [meta, rows] = await Promise.all([TauData.meta(), TauData.named()]);
    if (gen !== generation) return;
    setContext([['Named', null]]);
    const head = el('div', 'page-head');
    head.append(el('div', 'kicker', 'Announced by Voyager on the Lean Zulip'), el('h1', null, 'Named results and notable definitions'));
    const lede = el('p', 'lede');
    lede.append(`The mathematics Voyager has announced as new in ${meta.library.name}: named theorems and notable definitions, `,
                'the declarations to read first. Open one to read it, see what it rests on, and review it.');
    head.append(lede);
    const results = rows.filter(r => r.what === 'result').length;
    const by = st => rows.filter(r => rowState(r) === st).length;
    const stats = el('div', 'stats');
    [[rows.length, 'named'], [results, 'results'], [rows.length - results, 'definitions'],
     [by('covered') + by('disputed'), ai ? 'reviewed, counting AI' : 'reviewed by people'], [by('unreviewed'), 'not reviewed yet']]
      .forEach(([n, t]) => { const s = el('div', 'stat'); s.append(el('b', null, n.toLocaleString('en')), el('span', null, t)); stats.append(s); });
    head.append(stats);
    // Filters: kind, area, state, order, words.
    const st = {what: 'all', area: '', state: '', sort: 'new', q: '', shown: 60};
    const filters = el('div', 'filters');
    const seg = el('div', 'seg');
    [['all', 'All'], ['result', 'Results'], ['definition', 'Definitions']].forEach(([k, t]) => {
      const b = el('button', k === st.what ? 'on' : '', t);
      b.type = 'button'; b.dataset.what = k;
      b.addEventListener('click', () => { st.what = k; seg.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b)); st.shown = 60; draw(); });
      seg.append(b);
    });
    const select = (options, key, label) => {
      const s = el('select', 'select'); s.setAttribute('aria-label', label);
      options.forEach(([v, t]) => { const o = el('option', null, t); o.value = v; s.append(o); });
      s.addEventListener('change', () => { st[key] = s.value; st.shown = 60; draw(); });
      return s;
    };
    const areas = [...new Set(rows.map(r => r.area))].sort();
    const q = el('input', 'filter-input');
    q.type = 'search'; q.placeholder = 'Filter by name or words'; q.setAttribute('aria-label', 'Filter');
    q.addEventListener('input', () => { st.q = q.value.toLowerCase(); st.shown = 60; draw(); });
    filters.append(seg, select([['', 'Every area'], ...areas.map(a => [a, a])], 'area', 'Area'),
                   select([['', 'Any review state'], ['covered', 'Reviewed'], ['unreviewed', 'Not reviewed yet'],
                           ['uncounted', 'Reviewed by AI only'], ['stale', 'Reviewed on an earlier version'], ['problem', 'With an open problem']], 'state', 'Review state'),
                   select([['new', 'Newest first'], ['name', 'By name'], ['imp', 'Most built upon']], 'sort', 'Order'), q);
    const count = el('p', 'faint small count'), cards = el('div', 'cards'), moreBox = el('div', 'more-box');
    function draw() {
      let list = rows.filter(r => (st.what === 'all' || r.what === st.what) && (!st.area || r.area === st.area) &&
        (!st.state || rowState(r) === st.state || (st.state === 'problem' && rowState(r) === 'disputed')) &&
        (!st.q || (r.name + ' ' + r.decl + ' ' + r.text).toLowerCase().includes(st.q)));
      if (st.sort === 'name') list = [...list].sort((a, b) => a.name.localeCompare(b.name));
      if (st.sort === 'imp') list = [...list].sort((a, b) => b.imp - a.imp);
      count.textContent = `${plural(list.length, 'declaration')}`;
      cards.replaceChildren(...list.slice(0, st.shown).map(namedCard));
      moreBox.replaceChildren();
      if (list.length > st.shown) {
        const b = el('button', 'btn', `Show ${Math.min(60, list.length - st.shown)} more`);
        b.type = 'button';
        b.addEventListener('click', () => { st.shown += 60; draw(); });
        moreBox.append(b);
      }
    }
    draw();
    show(head, filters, count, cards, moreBox);
  };

  function namedCard(r) {
    const card = el('article', 'card');
    const state = rowState(r);
    card.append(glyph(r.what === 'result' ? 'theorem' : 'definition', state, {size: 30, named: true}));
    const body = el('div', 'card-body');
    const title = link(URLS.decl(r.decl), plain(r.name), 'card-title stretched');
    body.append(title, mdInline(r.text, 'card-text'));
    const metaLine = el('div', 'card-meta');
    metaLine.append(el('span', 'mono', r.decl));
    const facts = el('div', 'card-facts');
    facts.append(el('span', 'chip', r.area));
    const reviews = r.people || r.ai ? [r.people ? plural(r.people, 'person', 'people') : '', r.ai ? `${r.ai} AI` : ''].filter(Boolean).join(' · ') : 'not reviewed yet';
    facts.append(el('span', 'chip state-' + state, reviews));
    const [members, people, withAi, problems] = r.cov;
    if (members > 1) facts.append(coverageBar(members, people, withAi, problems));
    facts.append(el('span', 'faint', date(r.at)));
    body.append(metaLine, facts);
    card.append(body);
    return card;
  }
  /* What a named declaration rests on in Tau Ceti, and how much of it is reviewed. */
  function coverageBar(members, people, withAi, problems) {
    const wrap = el('span', 'cov'), bar = el('span', 'bar');
    const part = (n, cls) => { if (n > 0) { const i = el('i', cls); i.style.width = (100 * n / members).toFixed(1) + '%'; bar.append(i); } };
    const counted = ai ? withAi : people;
    part(counted, 'b-done'); part(ai ? 0 : withAi - people, 'b-ai'); part(problems, 'b-problem');
    wrap.append(bar, el('span', 'faint', `${counted}/${members}`));
    wrap.title = `Rests on ${plural(members, 'declaration')} of Tau Ceti: ${people} reviewed by people` +
      (withAi > people ? `, ${withAi - people} more by AI agents only` : '') + (problems ? `, ${problems} with an open problem` : '');
    return wrap;
  }

  VIEWS.decl = async (name, gen) => {
    const [meta, d, named] = await Promise.all([TauData.meta(), TauData.decl(name), TauData.named()]);
    if (gen !== generation) return;
    if (!d) return VIEWS.missing(name, gen, 'No declaration of that name is in this build.');
    const n = d.node, project = !!(n.flags & FLAG.PROJECT);
    const up = project ? {} : ((await TauData.upstream())[name] || {});
    const e = d.entry || up;
    const row = named.find(r => r.decl === name);
    const modName = d.module ? d.module.name : ((await TauData.modules())[n.mod] || [''])[0];
    if (gen !== generation) return;
    setContext(project ? [...await moduleTrail(modName), [shortName(name), null]] : [['Outside ' + meta.library.name, null], [name, null]]);
    const wrap = el('div', 'decl'), main = el('div', 'decl-main'), panel = el('aside', 'panel');
    // Head.
    const kind = el('div', 'kind');
    kind.append(glyph(n.kind, stateOf(n), {size: 26, named: !!row, upstream: !project}), kindWord[n.kind] || 'Declaration');
    if (row) {
      kind.append(el('span', 'sep', '·'), 'announced by Voyager ' + date(row.at));
      row.prs.forEach(p => { kind.append(' ', ext(`https://github.com/${meta.library.repo}/pull/${p}`, `#${p}`)); });
    }
    if (!project) kind.append(el('span', 'sep', '·'), modName.split('.')[0] === 'Mathlib' ? 'from Mathlib' : 'from ' + modName.split('.')[0]);
    const title = row ? row.name : (n.title || shortName(name));
    const leanName = el('div', 'decl-name');
    const copyName = el('button', 'btn small', 'Copy');
    copyName.type = 'button';
    copyName.addEventListener('click', async () => { try { await navigator.clipboard.writeText(name); copyName.textContent = 'Copied'; } catch (x) { /* ignore */ } });
    leanName.append(el('span', null, name), copyName);
    const links = el('div', 'links');
    if (project) {
      links.append(ext(URLS.docs(meta, name, modName), 'API docs'));
      if (e.line && d.module) links.append(ext(URLS.source(meta, d.module.path, e.line), 'Source'));
      if (row && row.post) links.append(ext(row.post, "Voyager's post"));
    } else {
      if (modName.startsWith('Mathlib')) links.append(ext(URLS.mathlib(name, modName), "Mathlib's docs"), ext(URLS.explorer(name), 'Mathlib Explorer'));
    }
    const h1 = el('h1');
    h1.append(mdInline(title));
    main.append(kind, h1, leanName, links);
    if (row && row.text) main.append(md(row.text, 'doc announce'));
    // The docstring, unless all it says is the title above.
    if (e.doc && (row || e.doc.trim() !== (n.title || '').trim())) main.append(md(e.doc, 'doc'));
    if (e.stmt) {
      const lean = el('div', 'lean'), pre = el('pre');
      const theorem = n.kind === 'theorem';
      pre.textContent = theorem ? e.stmt : e.stmt + (e.rest ? '\n' + e.rest : '');
      lean.append(pre);
      if (theorem && e.rest) {
        const det = el('details'), sum = el('summary', null, 'Proof'), proof = el('pre');
        proof.textContent = e.rest;
        det.append(sum, proof);
        lean.append(det);
      }
      if (e.cut && d.module) { const c = el('div', 'cut'); c.append('The text goes on: ', ext(URLS.source(meta, d.module.path, e.line), 'read it in the source')); lean.append(c); }
      main.append(lean);
    }
    // The map, and the same as lists.
    const mapSec = el('section', 'block');
    mapSec.append(el('h2', null, 'What it rests on, and what rests on it'));
    if (row && row.cov[0] > 1) {
      const [members, people, withAi, problems] = row.cov, cov = el('div', 'coverage');
      cov.append(coverageBar(members, people, withAi, problems),
                 `Its meaning rests on ${plural(members, 'declaration')} of ${meta.library.name}: ${people} reviewed by people, ` +
                 `${withAi - people} only by AI agents, ${members - withAi - problems} by nobody` + (problems ? `, ${problems} with an open problem` : '') + '.');
      mapSec.append(cov);
    }
    const mapHost = el('div');
    if (project) { mapSec.append(mapHost); main.append(mapSec); }
    const lists = el('div', 'lists');
    const isResult = n.kind === 'theorem';
    if (project) lists.append(section(isResult ? 'What it is about' : 'What it is built from', await nodeList(n.m, n.nm, 'Nothing here.')));
    if (n.p.length || e.nRoutine) {
      const box = await nodeList(n.p, n.np, 'Only routine steps.');
      if (e.nRoutine) box.append(el('p', 'faint small', `and ${plural(e.nRoutine, 'routine step')} (arithmetic, logic and automation)`));
      lists.append(section(isResult ? 'How it is proved' : 'What the proofs in it use', box));
    }
    if (!project) lists.append(el('p', 'faint', `What it rests on is not followed outside ${meta.library.name}: Mathlib Explorer shows it.`));
    {
      if (e.builtOn) lists.append(section('Built on it', await nodeList(e.builtOn, e.nBuiltOn, '')));
      if (e.facts) lists.append(section('Results about it', await nodeList(e.facts, e.nFacts, '')));
      if (e.examples) lists.append(section('Examples', await nodeList(e.examples, e.nExamples, '')));
      if (e.usedIn) lists.append(section('Used to prove', await nodeList(e.usedIn, e.nUsedIn, '')));
    }
    main.append(lists);
    // The review panel.
    const records = project ? (e.records || []) : (up.records || []);
    if (gen !== generation) return;
    const people = records.filter(v => v.kind === 'review' && v.verdict === 'accept' && v.inForce && v.applies && v.by.kind !== 'agent').length;
    const agents = records.filter(v => v.kind === 'review' && v.verdict === 'accept' && v.inForce && v.applies && v.by.kind === 'agent').length;
    panel.append(el('h2', 'panel-title', 'Review'));
    const stateLine = el('div', 'state-line');
    stateLine.append(glyph(n.kind, stateOf(n), {size: 30, named: !!row, upstream: !project}));
    const words = el('div');
    words.append(el('div', 'state-text', STATE_TEXT[stateOf(n)]),
                 el('div', 'faint small', people || agents ? `Reviewed-by · ${plural(people, 'person', 'people')} · ${agents} AI`
                   : records.some(v => v.kind === 'review' && v.verdict === 'accept') ? 'No review of this version yet.' : 'Nobody has reviewed it yet.'));
    stateLine.append(words);
    panel.append(stateLine);
    if (project) {
      const actions = el('div', 'actions');
      FORMS.forEach(([text, template, prefix, cls]) => actions.append(ext(URLS.form(meta, template, prefix, name), text, 'btn ' + cls)));
      panel.append(actions, el('p', 'faint small', 'Each opens a form on GitHub, filled in. Recorded under your account within minutes.'));
    } else if (records.length) {
      panel.append(el('p', 'faint small', `Reviews of ${name} are kept in the stores that review it; they show here as they are.`));
    } else {
      panel.append(el('p', 'faint small', `Outside ${meta.library.name}: review it where it lives, such as the Mathlib probability store.`));
    }
    const byId = new Map(records.map(v => [v.id, v]));
    // Tests are listed below with whether they pass; Voyager's announcement heads the page.
    const top = records.filter(v => v.kind !== 'comment' && v.kind !== 'test' && !(v.kind === 'named' && v.by.agent && v.by.agent.tool === 'Voyager'));
    const order = v => (v.inForce && v.applies !== false ? 0 : 1);
    top.sort((a, b) => order(a) - order(b) || (b.at || '').localeCompare(a.at || ''));
    if (top.length) top.forEach(v => panel.append(thread(v, byId)));
    if ((e.tests || []).length) {
      const t = el('div', 'tests');
      t.append(el('h3', null, 'Tests'));
      e.tests.forEach(x => {
        const line = el('div', 'test-line');
        line.append(el('span', 'result ' + x.result, {passes: 'passes', sorry: 'with sorry', missing: 'missing'}[x.result]),
                    link(URLS.decl(x.test), shortName(x.test), 'mono'));
        if (x.text) line.append(' — ', mdInline(x.text));
        const by = el('div', 'faint small');
        by.append(x.challenge ? 'Suggested, and met; listed by ' : 'Listed by ', who(x.by), ' · ' + date(x.at));
        if (x.url) by.append(' · ', ext(x.url, 'issue'));
        line.append(by);
        t.append(line);
      });
      panel.append(t);
    }
    wrap.append(main, panel);
    show(wrap);
    if (project) TauMap.draw(mapHost, n, d.entry, {ai: () => ai});
  };

  VIEWS.module = async (name, gen) => {
    const [meta, found] = await Promise.all([TauData.meta(), TauData.moduleByName(name)]);
    if (gen !== generation) return;
    if (!found || !found.file) return VIEWS.missing(name, gen, 'No module of that name is in this build.');
    setContext(await moduleTrail(name));
    const f = found.file, head = el('div', 'page-head');
    head.append(el('div', 'kicker', 'Module'), el('h1', null, f.title || name), el('div', 'decl-name', name));
    const links = el('div', 'links');
    links.append(ext(URLS.source(meta, f.path, null), 'Source'));
    head.append(links);
    if (f.doc) head.append(md(f.doc, 'doc'));
    const ids = f.decls.map(x => x.id), items = await TauData.nodes(ids);
    if (gen !== generation) return;
    items.sort((a, b) => ((b.flags & FLAG.NAMED) - (a.flags & FLAG.NAMED)));
    const list = el('div', 'nlist');
    items.filter(x => !(x.flags & FLAG.AUX)).forEach(x => list.append(nodeItem(x)));
    show(head, section(plural(items.length, 'declaration'), list));
  };

  VIEWS.area = async (area, gen) => {
    const [meta, modules, named] = await Promise.all([TauData.meta(), TauData.modules(), TauData.named()]);
    if (gen !== generation) return;
    setContext([[meta.library.name, '#/browse'], [area, null]]);
    const mine = modules.slice(0, meta.counts.modules).map((m, i) => [m, i]).filter(([m]) => areaOf(m[0]) === area);
    const head = el('div', 'page-head');
    head.append(el('div', 'kicker', 'Area'), el('h1', null, area));
    const ns = named.filter(r => r.area === area), cards = el('div', 'cards');
    ns.slice(0, 24).forEach(r => cards.append(namedCard(r)));
    const list = el('div', 'mlist');
    mine.forEach(([m]) => {
      const a = link('#/m/' + encodeURIComponent(m[0]), null, 'mitem');
      a.append(el('span', 't', m[2] || m[0].split('.').slice(2).join('.') || m[0]), el('span', 'n', m[0]));
      list.append(a);
    });
    show(head, ns.length ? section(`Named here (${ns.length})`, cards) : el('div'), section(plural(mine.length, 'module'), list));
  };

  VIEWS.browse = async (arg, gen) => {
    const meta = await TauData.meta();
    if (gen !== generation) return;
    setContext([[meta.library.name, null]]);
    const head = el('div', 'page-head');
    head.append(el('div', 'kicker', 'Browse'), el('h1', null, `${meta.library.name}, area by area`));
    head.append(el('p', 'lede', `${plural(meta.counts.declarations, 'declaration')} in ${plural(meta.counts.modules, 'module')}, at ${meta.library.commit.slice(0, 7)}.`));
    const grid = el('div', 'areas');
    meta.areas.forEach(([a, n, k]) => {
      const t = link('#/area/' + encodeURIComponent(a), null, 'area-tile');
      t.append(el('b', null, a), el('span', null, `${plural(n, 'declaration')}${k ? ` · ${k} named` : ''}`));
      grid.append(t);
    });
    show(head, grid);
  };

  let searchGen = 0;
  VIEWS.search = async (q, gen) => {
    setContext([['Search', null]]);
    $('q').value = q;
    const head = el('div', 'page-head');
    head.append(el('div', 'kicker', 'Search'), el('h1', null, q ? `“${q}”` : 'Search'));
    const status = el('p', 'faint small', 'Searching…'), list = el('div', 'nlist');
    show(head, status, list);
    if (!q.trim()) { status.textContent = 'Type a name, part of one, or words from a docstring.'; return; }
    const mine = ++searchGen;
    const rows = await TauData.search();
    if (gen !== generation || mine !== searchGen) return;
    const ql = q.trim().toLowerCase(), words = ql.split(/\s+/);
    const scoreName = name => {
      const n = name.toLowerCase(), last = n.slice(n.lastIndexOf('.') + 1);
      if (n === ql) return 0;
      if (last === ql) return 1;
      if (last.startsWith(ql)) return 2;
      if (n.includes(ql)) return 3;
      return words.length > 1 && words.every(w => n.includes(w)) ? 4 : 9;
    };
    const hits = [];
    rows.forEach((r, i) => { const s = scoreName(r[0]); if (s < 9) hits.push([s, r[0].length, i]); });
    const render = extra => {
      const all = hits.concat(extra).sort((a, b) => a[0] - b[0] || a[1] - b[1]).slice(0, 200);
      status.textContent = all.length ? `${plural(hits.length + extra.length, 'match', 'matches')}${hits.length + extra.length > 200 ? ', the first 200' : ''}` : 'Nothing found yet…';
      return TauData.nodes([]).then(() => Promise.all(all.map(h => TauData.idOf(rows[h[2]][0]))))
        .then(ids => TauData.nodes(ids.filter(x => x != null)))
        .then(ns => { if (mine === searchGen) list.replaceChildren(...ns.sort((a, b) => ((b.flags & FLAG.NAMED) - (a.flags & FLAG.NAMED))).map(nodeItem)); });
    };
    await render([]);
    const titles = await TauData.titles();
    if (gen !== generation || mine !== searchGen) return;
    const extra = [];
    const seen = new Set(hits.map(h => h[2]));
    titles.forEach((t, i) => { if (!seen.has(i) && t && words.every(w => t.toLowerCase().includes(w))) extra.push([5, t.length, i]); });
    await render(extra);
    if (!hits.length && !extra.length) status.textContent = 'Nothing matches.';
  };

  VIEWS.activity = async (arg, gen) => {
    const [meta, act] = await Promise.all([TauData.meta(), TauData.activity()]);
    if (gen !== generation) return;
    setContext([['Activity', null]]);
    const head = el('div', 'page-head');
    head.append(el('div', 'kicker', 'Activity'), el('h1', null, 'Reviews, problems and suggested tests'));
    const recordList = (vs, empty) => {
      if (!vs.length) return el('p', 'faint', empty);
      const box = el('div', 'records');
      const byId = new Map(vs.map(v => [v.id, v]));
      vs.forEach(v => { const t = thread(v, byId); t.prepend(link(URLS.decl(v.decl), v.decl, 'mono small decl-link')); box.append(t); });
      return box;
    };
    const queueIds = act.queue.map(q => q[0]);
    const weights = new Map(act.queue);
    const queueBox = el('div', 'nlist');
    (await TauData.nodes(queueIds)).forEach(x => { const item = nodeItem(x); item.append(el('span', 'weight', `${plural(weights.get(x.id), 'named result')} ${weights.get(x.id) === 1 ? 'rests' : 'rest'} on it`)); queueBox.append(item); });
    const reviewers = el('div', 'reviewers');
    act.reviewers.forEach(r => reviewers.append(el('span', 'chip' + (r.kind === 'agent' ? ' agent' : ''), `${r.label} · ${r.n}`)));
    show(head,
      section('Open problems', recordList(act.problems, 'No open problems.')),
      section('Open questions', recordList(act.questions, 'No open questions.')),
      section('Suggested tests, still open', recordList(act.challenges, 'No open suggestions.')),
      section('What to review next', el('p', 'faint small', 'Unreviewed declarations of Tau Ceti that named results rest on, those most of them share first.'), queueBox),
      section('Latest', recordList(act.recent, 'Nothing yet.')),
      section('Reviewers', act.reviewers.length ? reviewers : el('p', 'faint', 'Nobody yet.')));
  };

  VIEWS.help = async (arg, gen) => {
    const meta = await TauData.meta();
    if (gen !== generation) return;
    setContext([['How to review', null]]);
    const head = el('div', 'page-head');
    head.append(el('div', 'kicker', 'How to review'), el('h1', null, 'Leave a review, a problem, a test or a question'));
    const p = (...parts) => { const x = el('p', 'prose'); x.append(...parts); return x; };
    const code = t => { const c = el('pre', 'small-code'); c.textContent = t; return c; };
    show(head,
      p('Open a declaration and use its buttons: each opens a form on GitHub, filled in with the declaration and the commit this page shows. ',
        'Submit it, and the record is kept in this site\'s evidence store under your GitHub account, and shown here within minutes. No pull request.'),
      section('What each form records',
        p(el('b', null, 'Review this'), ': it is the intended mathematical notion, or states the intended result. Say what you compared it with and which ways it could go wrong you checked. A person need not say why; an AI agent must.'),
        p(el('b', null, 'Report a problem'), ': it is wrong, and why. The problem stays open, and the declaration is flagged, until someone marks it fixed, intended, or not a problem.'),
        p(el('b', null, 'Suggest a test'), ': a property it should have, in words and if you can in Lean. It stays open until a declaration of Tau Ceti proves it.'),
        p(el('b', null, 'List a test'), ': a declaration of Tau Ceti that already pins it down, and what it checks.'),
        p(el('b', null, 'Ask a question'), ': anything you want its authors or reviewers to answer.')),
      section('Versions',
        p('A review is pinned to the declaration as it was: to its meaning hash, which changes when the declaration changes or anything it rests on does. ',
          'A review of an earlier version stays, greyed: "the declaration has changed since", or "something it rests on has changed since". Nothing is written into Tau Ceti.')),
      section('Many at once, and AI agents',
        p('Comment lines like these on ', ext(URLS.bulk(meta), `issue #${meta.store.bulk}`), ', one record each:'),
        code('Reviewed-by: TauCeti.Foo.bar — what you checked\nTest: TauCeti.Foo.bar — TauCeti.Foo.bar_zero — its value at 0\nChallenge: TauCeti.Foo.bar — it is additive\nNamed: TauCeti.Foo.bar — The bar theorem — a sentence'),
        p('An AI agent names itself in its comment, and its records are shown apart from people\'s:'),
        code('<!-- agent: tool=Claude Code; model=claude-opus-5-5; session=… -->')),
      section('On a record\'s issue',
        p('A comment whose first line is a command changes its state: ', el('code', null, '/withdraw'), ', ', el('code', null, '/fixed'), ', ',
          el('code', null, '/intended'), ', ', el('code', null, '/invalid'), ', ', el('code', null, '/met <declaration>'), ', ',
          el('code', null, '/declined'), ', ', el('code', null, '/answered'), ', ', el('code', null, '/reopen'), '.')),
      section('Where this comes from',
        p('Built with the ', ext('https://github.com/LeanTrustBuilders', 'LeanTrustBuilders'), ' tools: the dataset of Tau Ceti at ',
          ext(`https://github.com/${meta.library.repo}/commit/${meta.library.commit}`, meta.library.commit.slice(0, 7)),
          ` (${meta.dataset.producer}), the evidence store `, ext(`https://github.com/${meta.store.repo}`, meta.store.repo),
          meta.imports.length ? ', and the stores it imports: ' : '.', ...meta.imports.flatMap((s, i) => [i ? ', ' : '', ext(`https://github.com/${s.repo}`, s.name)]))));
  };

  VIEWS.missing = async (what, gen, why) => {
    setContext([['Not found', null]]);
    const head = el('div', 'page-head');
    head.append(el('h1', null, 'Not here'), el('p', 'lede', why || 'There is no page at this address.'));
    if (what) head.append(link('#/search/' + encodeURIComponent(String(what).split('.').pop()), 'Search for it'));
    show(head);
  };

  /* --- the rail ------------------------------------------------------------------------------------- */
  async function rail() {
    const [meta, named, act] = await Promise.all([TauData.meta(), TauData.named(), TauData.activity()]);
    const nav = $('rail-nav');
    const item = (href, text, count) => { const a = link(href, null, 'nav-item'); a.append(el('span', null, text), el('small', null, count)); return a; };
    nav.replaceChildren(item('#/', 'Named results and definitions', named.length.toLocaleString('en')),
                        item('#/activity', 'Open problems', act.problems.length), item('#/activity', 'Suggested tests', act.challenges.length),
                        item('#/activity', 'Recent reviews', act.recent.filter(v => v.kind === 'review').length));
    $('rail-areas').replaceChildren(...meta.areas.map(([a, n]) => item('#/area/' + encodeURIComponent(a), a, n.toLocaleString('en'))));
    $('rail-foot').replaceChildren(`${meta.library.name} at `,
      ext(`https://github.com/${meta.library.repo}/commit/${meta.library.commit}`, meta.library.commit.slice(0, 7)),
      meta.library.date ? ` (${date(meta.library.date)})` : '', el('br'), `Built ${date(meta.built)} · `, link('#/help', 'about'));
    const pin = $('pin');
    pin.replaceChildren(ext(`https://github.com/${meta.library.repo}/commit/${meta.library.commit}`, `${meta.library.name} @ ${meta.library.commit.slice(0, 7)}`));
    $('store-link').href = `https://github.com/${meta.store.repo}`;
  }

  /* --- wiring --------------------------------------------------------------------------------------- */
  async function route() {
    const r = parse(location.hash);
    if (location.hash && !location.hash.startsWith('#/') && r[0] !== 'missing') history.replaceState(null, '', address(r));
    current = r.join(':');
    document.body.classList.remove('rail-open');
    $('rail-toggle').setAttribute('aria-expanded', 'false');
    setNav({named: 'named', browse: 'browse', area: 'browse', module: 'browse', activity: 'activity', help: 'help'}[r[0]] || '');
    const gen = ++generation;
    ready = false;
    try {
      await VIEWS[r[0]](r[1], gen);
    } catch (e) {
      if (gen === generation) {
        const box = el('div', 'page-head');
        box.append(el('h1', null, 'This page could not be shown'), el('pre', 'small-code', String(e && e.stack || e)));
        show(box);
      }
      console.error(e);
    }
    if (gen === generation) ready = true;
  }
  let typing = null;
  $('q').addEventListener('input', e => {
    clearTimeout(typing);
    typing = setTimeout(() => {
      const target = '#/search/' + encodeURIComponent(e.target.value);
      if (location.hash.startsWith('#/search/')) { history.replaceState(null, '', target); route(); } else location.hash = target;
    }, 250);
  });
  document.addEventListener('keydown', e => {
    if ((e.key === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName))) {
      e.preventDefault(); $('q').focus(); $('q').select();
    }
  });
  const aiBox = $('ai');
  aiBox.checked = ai;
  aiBox.addEventListener('change', () => {
    ai = aiBox.checked;
    try { localStorage.setItem('tauceti-review:ai', ai ? '1' : '0'); } catch (e) { /* not kept */ }
    route();
  });
  $('rail-toggle').addEventListener('click', () => {
    const open = document.body.classList.toggle('rail-open');
    $('rail-toggle').setAttribute('aria-expanded', String(open));
  });
  window.addEventListener('hashchange', route);
  rail().catch(e => console.error(e));
  route();

  /* For the browser check (tests/validate_site.py). */
  window.TauReview = Object.freeze({
    get ready() { return ready; },
    route: () => current,
    mapNodes: () => [...document.querySelectorAll('.map .node[data-name]')].map(g => g.dataset.name),
    fnv: TauData.fnv,
  });
})();
````

- [ ] **Step 8: Run the browser check to see it pass**

Run: `.venv/bin/python tests/validate_site.py`
Expected: `ok` for `shell`, `old_addresses`, `named`, `search`, `declaration`, `review`, `dependency_map`, `other_pages`, `phone`, then `PASS`.

- [ ] **Step 9: Look at it**

Run: `.venv/bin/python tests/fixture_site.py _site_fixture && python3 -m http.server -d _site_fixture 8765`, open `http://127.0.0.1:8765/#/d/Fixture.triple_pos`, and compare with the Atlas (`https://cbirkbeck.github.io/tauceti-explorer/#view=all`): the same dark surface and gold accent; the planets; a gold-ringed centre on the map. Stop the server.

- [ ] **Step 10: Commit**

```bash
git add web tests/validate_site.py
git commit -q -F - <<'EOF'
The front end: Named, search, declarations with their reviews and dependency map, in the Atlas's look

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 9: Building and publishing the site

**Files:**
- Create: `.github/workflows/pages.yml`
- Modify: `.github/workflows/follow.yml` (add the job `site`), `.github/workflows/voyager.yml` (add the job `site`)
- Test: `tests/test_workflows.py` (add `PagesWorkflowTests`)

**Interfaces:**
- Consumes: `scripts/build_site.py`, `tests/validate_site.py` (`--smoke`), the unit tests; `evidence-store dataset` and `fetch-imports`.
- Produces: the reusable workflow `./.github/workflows/pages.yml` (input `deploy`, default true; deploys only from `main`), which intake runs by name (`pages.yml`, set in Task 1 by `evidence-store init --pages-workflow pages.yml`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_workflows.py`, before `if __name__ == "__main__":`:

```python
class PagesWorkflowTests(unittest.TestCase):
    def test_builds_checks_and_publishes_from_main_only(self):
        wf = load("pages.yml")
        for trigger in ("push", "workflow_dispatch", "workflow_call"):
            self.assertIn(trigger, wf["on"])
        text = runs(wf["jobs"]["build"])
        for command in ("python -m unittest discover -s tests", "python tests/validate_site.py",
                        "python scripts/build_site.py", "python tests/validate_site.py --site _site --smoke"):
            self.assertIn(command, text)
        self.assertEqual(wf["jobs"]["deploy"]["if"], "github.ref == 'refs/heads/main' && format('{0}', inputs.deploy) != 'false'")

    def test_follow_and_voyager_rebuild_the_site(self):
        self.assertEqual(load("follow.yml")["jobs"]["site"]["uses"], "./.github/workflows/pages.yml")
        self.assertEqual(load("voyager.yml")["jobs"]["site"]["uses"], "./.github/workflows/pages.yml")

    def test_intake_rebuilds_the_site(self):
        intake = load("evidence-intake.yml")["jobs"]["intake"]
        self.assertEqual(next(s for s in steps(intake) if "evidence-store/intake" in s.get("uses", ""))["with"]["pages-workflow"],
                         "pages.yml")
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m unittest tests.test_workflows -v`
Expected: `test_builds_checks_and_publishes_from_main_only` and `test_follow_and_voyager_rebuild_the_site` FAIL; `test_intake_rebuilds_the_site` passes.

- [ ] **Step 3: The workflow**

Create `.github/workflows/pages.yml`:

```yaml
name: Pages

# Builds the site from the pinned dataset (data/settings.json), the evidence store and the stores it
# imports, checks it, and publishes it. Intake, follow.yml and voyager.yml run it after they record
# something, and a push that changes the site or the store does too. Only main publishes: on another
# branch the site is built and checked, not deployed.
on:
  push:
    branches: [main]
    paths: ['web/**', 'scripts/**', 'evidence/**', 'data/settings.json', 'requirements*.txt', '.github/workflows/pages.yml']
  workflow_dispatch:
    inputs:
      deploy:
        description: Publish the site (from main)
        type: boolean
        default: true
  workflow_call:
    inputs:
      deploy:
        type: boolean
        default: true

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    env:
      GH_TOKEN: ${{ github.token }}
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.ref }}
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: The pinned tools, and Chromium for the browser check
        run: |
          pip install -q -r requirements.txt -r requirements-test.txt
          python -m playwright install --with-deps chromium
      - name: Unit tests
        run: python -m unittest discover -s tests
      - name: The browser check, on the fixture's site
        run: python tests/validate_site.py
      - name: The pinned dataset, Tau Ceti's sources at it, and the stores this one imports
        run: |
          commit=$(python3 -c "import json; print(json.load(open('data/settings.json'))['tauceti'])")
          evidence-store dataset --store evidence --commit "$commit" --out "$RUNNER_TEMP/dataset" > /dev/null
          git init -q "$RUNNER_TEMP/TauCeti"
          git -C "$RUNNER_TEMP/TauCeti" fetch -q --depth 1 https://github.com/TauCetiProject/TauCeti "$commit"
          git -C "$RUNNER_TEMP/TauCeti" checkout -q FETCH_HEAD
          evidence-store fetch-imports --store evidence --out "$RUNNER_TEMP/imports"
      - name: Build
        run: python scripts/build_site.py --dataset "$RUNNER_TEMP/dataset" --source "$RUNNER_TEMP/TauCeti" --imports "$RUNNER_TEMP/imports" --out _site
      - name: The browser check, on the build
        run: python tests/validate_site.py --site _site --smoke
      - uses: actions/upload-pages-artifact@v3
        with:
          path: _site
  deploy:
    needs: build
    if: github.ref == 'refs/heads/main' && format('{0}', inputs.deploy) != 'false'
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

Add to `follow.yml`, after the job `prune`:

```yaml
  site:
    needs: [pin, dataset, named]
    if: always() && needs.pin.result == 'success' && needs.dataset.result != 'failure' && (needs.pin.outputs.moved == 'true' || needs.named.outputs.recorded == 'true')
    uses: ./.github/workflows/pages.yml
    permissions:
      contents: read
      pages: write
      id-token: write
```

Add to `voyager.yml`, after the job `named`:

```yaml
  site:
    needs: named
    if: needs.named.outputs.recorded == 'true' && format('{0}', inputs.site) != 'false'
    uses: ./.github/workflows/pages.yml
    permissions:
      contents: read
      pages: write
      id-token: write
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/bin/python -m unittest tests.test_workflows -v`
Expected: 8 tests, OK.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows tests/test_workflows.py
git commit -q -F - <<'EOF'
Pages: tests, a browser check, the build, and publishing from main

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 10: The README

**Files:**
- Modify: `README.md` (replace)

- [ ] **Step 1: Write it**

Replace `README.md` with:

````markdown
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
| **Review this** | an acceptance: it is the intended mathematical notion, or states the intended result. Saying why is optional for a person; an AI agent must |
| **Report a problem** | what is wrong and why. It stays open, and the declaration is flagged, until it is marked fixed, intended or invalid |
| **Suggest a test** | a property the declaration should have, in words and if possible in Lean. It stays open until a declaration of Tau Ceti proves it |
| **List a test** | a declaration of Tau Ceti that already pins it down, and what it checks |
| **Ask a question** | a question about it |

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
`<!-- agent: tool=Claude Code; model=claude-opus-5-5; session=… -->`.

## What the site shows

- **Named**: Voyager's announcements, each with its review state and how much of what it rests on in
  Tau Ceti has been reviewed. Voyager is the only source of names.
- **A declaration**: its docstring and Lean source, links to the API docs, the source and Voyager's
  post; its **dependency map** (what it rests on above, what rests on it below; the results its proof
  uses and Mathlib's declarations on request), with the same neighbours as lists; and its review
  panel: every review, problem, question and suggested test as a thread, and the tests it passes.
- **Browse**, **Search** (names and docstring titles), **Activity** (open problems, open suggested
  tests, what to review next, reviewers) and **How to review**.

Colour on a declaration means its review state: an open ring for not reviewed, white for reviewed,
salmon for reviewed by AI agents only or on an earlier version, red for an open problem. A switch in
the side bar says whether AI agents' reviews count.

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
````

- [ ] **Step 2: Check every path it names exists**

Run: `grep -o -E '\(\.github/workflows/[a-z-]+\.yml\)|\(docs/[^)]+\)' README.md | tr -d '()' | sort -u | xargs ls`
Expected: every path listed, no `No such file`.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -q -F - <<'EOF'
README: what the site is, how to review on it, and how it is built

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 11: The real build, on this machine

Everything runs against the real Tau Ceti before anything is pushed. Nothing outside this checkout changes, except reading Voyager's topic with the key in `~/.zuliprc` (read only).

**Files:**
- Create: `data/voyager.jsonl`

- [ ] **Step 1: Voyager's history**

```bash
ZULIP_SITE=$(awk -F= '$1=="site"{print $2}' ~/.zuliprc) ZULIP_EMAIL=$(awk -F= '$1=="email"{print $2}' ~/.zuliprc) \
  ZULIP_API_KEY=$(awk -F= '$1=="key"{print $2}' ~/.zuliprc) .venv/bin/python scripts/voyager.py fetch
```

Expected: `… new announcements, … in all` with about 1,380 in all on 2026-10-23, and no warning line.

- [ ] **Step 2: The inputs of a build**

The pinned dataset was unpacked in Task 1 (`.cache/dataset-d9068003cb02`). Tau Ceti's sources at the pin, and the imported store:

```bash
rm -rf .cache/TauCeti && git init -q .cache/TauCeti
git -C .cache/TauCeti fetch -q --depth 1 https://github.com/TauCetiProject/TauCeti d9068003cb02ec808e548ee70982ffef9379db00
git -C .cache/TauCeti checkout -q FETCH_HEAD
.venv/bin/evidence-store fetch-imports --store evidence --out .cache/imports
```

Expected: `LeanTrustBuilders/mathlib-probability-evidence at …: … records`.

- [ ] **Step 3: Named records, in a copy of the store**

The store's own named records are written by `voyager.yml` in CI (a person's push may only add that person's records). The local build reads a copy:

```bash
rm -rf .cache/evidence && cp -r evidence .cache/evidence
.venv/bin/python scripts/voyager.py record --dataset .cache/dataset-d9068003cb02 --store .cache/evidence
```

Expected: `recorded 1210 named results` (the announcements whose declaration the 2026-10-19 dataset has).

- [ ] **Step 4: Build and measure**

```bash
/usr/bin/time -l .venv/bin/python scripts/build_site.py --dataset .cache/dataset-d9068003cb02 --source .cache/TauCeti \
  --store .cache/evidence --imports .cache/imports --out _site 2>&1 | grep -E '^\{|maximum resident'
```

Expected: one JSON line with `"declarations": 195795`, `"named": 1210`, `"accepts": {"people": 3, "ai": 1}`, `"megabytes"` about 310 (under 800), `"seconds"` about 70; peak memory about 3.6 GB.

- [ ] **Step 5: Check it in a browser**

Run: `.venv/bin/python tests/validate_site.py --site _site --smoke`
Expected: `ok    smoke`, `PASS`.

Then serve it (`python3 -m http.server -d _site 8765`) and read, at least: `#/` (about 1,210 cards), `#/d/TauCeti.IdealArithmeticFunction.vonMangoldt` (reviewed: "1 person · 1 AI", eleven tests passing), `#/d/TauCeti.ClassFieldTheory.localWeilArtinEquiv` (a map of Tau Ceti's class field theory above it; "Its meaning rests on 226 declarations"), `#/search/von Mangoldt`, and the same two declarations at a phone's width. Stop the server.

- [ ] **Step 6: Commit the announcements**

```bash
git add data/voyager.jsonl
git commit -q -F - <<'EOF'
Voyager's announcements so far

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 12: In CI, on the branch

The first steps outside this checkout. Each is listed; nothing else is done. The live site does not change: Pages publishes only from `main`.

- [ ] **Step 1: The labels intake uses**

Run: `.venv/bin/python -c "from evidence_store.github import ensure_labels; ensure_labels('CBirkbeck/tauceti-reviewed-by-test')"`
Expected: no error; `gh label list -R CBirkbeck/tauceti-reviewed-by-test --search evidence` lists `evidence:review`, `evidence:problem`, `evidence:question`, `evidence:challenge`, `evidence:test`, `evidence:named`, `evidence:status`, `evidence:bulk`, `evidence:open`, `evidence:needs-fix`.

- [ ] **Step 2: The Zulip secrets**

The key is read from `~/.zuliprc` and piped, never printed:

```bash
for k in site email key; do
  name=$(case $k in site) echo ZULIP_SITE;; email) echo ZULIP_EMAIL;; key) echo ZULIP_API_KEY;; esac)
  awk -F= -v k=$k '$1==k{print $2}' ~/.zuliprc | tr -d '\n' | gh secret set "$name" -R CBirkbeck/tauceti-reviewed-by-test
done
gh secret list -R CBirkbeck/tauceti-reviewed-by-test
```

Expected: `ZULIP_API_KEY`, `ZULIP_EMAIL`, `ZULIP_SITE` listed.

- [ ] **Step 3: The first dataset**

The pilot's dataset of the pin, published unchanged as this repository's release of the same name (the same extractor, 0.13.1), so the site builds before `follow.yml` first runs:

```bash
gh release create dataset-d9068003cb02 .cache/dataset.tar.gz -R CBirkbeck/tauceti-reviewed-by-test --latest=false \
  --title "Dataset for Tau Ceti d9068003cb02ec808e548ee70982ffef9379db00" \
  --notes "The dataset (S2) of TauCetiProject/TauCeti at d9068003cb02ec808e548ee70982ffef9379db00, by trust-extract v0.13.1-lean-v4.36.0-rc1 (LeanTrustBuilders/extractor), as published by LeanTrustBuilders/reviewed-by-pilot."
```

- [ ] **Step 4: Push the branch**

Run: `git push -u origin suite-site`
Expected: the branch is on GitHub; `Evidence check` does not run (it runs on `main` and pull requests).

- [ ] **Step 5: Build the site in CI, without publishing**

`pages.yml` can be run on the branch because a workflow of that name is on `main` (the old page's); GitHub runs the branch's version. `dataset.yml`, `follow.yml` and `voyager.yml` are not on `main` yet, so they first run in Task 13.

```bash
gh workflow run pages.yml -R CBirkbeck/tauceti-reviewed-by-test --ref suite-site -f deploy=false
sleep 10; run=$(gh run list -R CBirkbeck/tauceti-reviewed-by-test --workflow pages.yml --branch suite-site --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$run" -R CBirkbeck/tauceti-reviewed-by-test --exit-status
```

Expected: the job `build` succeeds (unit tests, the fixture's browser check, the build, the smoke check, the artifact uploaded); `deploy` is skipped. The log's build line says `"named": 0` (the store has no named records yet) and `"accepts": {"people": 3, "ai": 1}`. The smoke check, finding no named results, opens declarations found by a search instead.

---

### Task 13: The switch

Replaces the live site. Before starting, confirm with the owner that it is time to switch.

- [ ] **Step 1: Make `main` the branch**

`main` has moved since the branch began (the old workflows' daily commits); the new tree replaces it whole, its history kept:

```bash
git fetch -q origin
git merge -q -s ours origin/main -m "Tau Ceti Review replaces the Reviewed-by test page

The old page's daily commits are kept in history; its tree is replaced.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push origin suite-site:main
```

Expected: the push succeeds. On `main`, `Evidence check` passes (the records are the pusher's), and `Pages` starts and deploys: the new site, with the migrated reviews and no named results yet.

- [ ] **Step 2: Record Voyager's announcements**

```bash
gh workflow run voyager.yml -R CBirkbeck/tauceti-reviewed-by-test --ref main
sleep 10; run=$(gh run list -R CBirkbeck/tauceti-reviewed-by-test --workflow voyager.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$run" -R CBirkbeck/tauceti-reviewed-by-test --exit-status
```

Expected: a commit "Voyager's announcements, as named results" by `github-actions[bot]` (about 1,210 records), then `Pages` deploys again.

- [ ] **Step 3: Follow Tau Ceti once, now**

```bash
gh workflow run follow.yml -R CBirkbeck/tauceti-reviewed-by-test --ref main
sleep 10; run=$(gh run list -R CBirkbeck/tauceti-reviewed-by-test --workflow follow.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$run" -R CBirkbeck/tauceti-reviewed-by-test --exit-status
```

Expected: the pin moves to Tau Ceti's newest extractable commit; `dataset` publishes `dataset-<commit12>` (20 to 40 minutes); `named` records the announcements the new dataset now has; `prune` deletes nothing (no dataset is 30 days old); `site` deploys.

- [ ] **Step 4: Check the live site**

Run: `.venv/bin/python tests/validate_site.py --url https://cbirkbeck.github.io/tauceti-reviewed-by-test/ --smoke`
Expected: `ok    smoke`, `PASS`.

- [ ] **Step 5: Stop the docstring lines**

Run: `gh workflow disable "Review lines" -R CBirkbeck/TauCeti`
Expected: `gh workflow list -R CBirkbeck/TauCeti --all` shows `Review lines` as `disabled_manually`. The lines already on the fork's `main` stay; nothing updates them.

- [ ] **Step 6: The bulk issue**

Write `.cache/bulk.md`:

````markdown
**The bulk issue of [Tau Ceti Review](https://cbirkbeck.github.io/tauceti-reviewed-by-test/).** Comment lines like these, one record each; intake records them under your account and answers here.

```
Reviewed-by: TauCeti.Foo.bar — what you checked
Test: TauCeti.Foo.bar — TauCeti.Foo.bar_zero — what it checks
Challenge: TauCeti.Foo.bar — a property it should have
Named: TauCeti.Foo.bar — The bar theorem — a sentence
```

An AI agent names itself in its comment, and its records are shown apart from people's:

```
<!-- agent: tool=Claude Code; model=claude-opus-5-5; session=… -->
```

One declaration at a time is easier from the site: open it and use its buttons, which fill in the forms.
````

```bash
gh issue edit 1 -R CBirkbeck/tauceti-reviewed-by-test --body-file .cache/bulk.md --add-label evidence:bulk
```

- [ ] **Step 7: A real review, end to end**

Ask the owner to review one declaration through the site's **Review this** button (or to agree that an AI agent files one through the bulk issue, with its marker). Expected: within minutes intake answers on the issue, the record is in `evidence/records/`, `Pages` deploys, and the declaration's panel shows it.

- [ ] **Step 8: Tell LeanTrustBuilders (owner's choice)**

The Mathlib probability store imports `LeanTrustBuilders/reviewed-by-pilot`; importing this store instead is their call. Offer the owner a one-line message for them; send nothing without the owner's word.

