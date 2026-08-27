# Archetype census, 2026-08-24

Reference. This document records a measurement. It does not propose a repair.

- Tree measured: clone of `acervator_session27_CLOSE_hop5_v3_25_8` at HEAD `e7958a8`, version 3.26.0.
- The auditor made no production edit. The only file added is this one.
- Method, controls and raw numbers appear below the summary.

## Summary for the project owner

Your CTO asked two questions. Here are the measured answers.

**Question 1 — do the code audits pass?** No. One file in four fails.

I ran the audit tool over every source file in the repository, one file at a
time. 651 files were examined. **165 of them fail (25.3%).** The failures carry
**1,075 high-severity findings** and **zero critical findings**.

**Question 2 — is this the AI's doing?** Almost entirely no.

I dated every one of those findings against the repository history. **907 of the
913 findings in the main pass date to the day the repository was first uploaded
(2026-08-18).** They arrived with the code. The 201 commits made since then —
the recent AI work your CTO is asking about — introduced **6 findings, and all 6
are prose-style notes in Markdown documents** (a sentence that begins with the
word "So"). No AI commit in the recorded history introduced a single
high-severity code finding.

**The uncomfortable part.** The release gate says `[OK] Release-ready` while all
165 files fail. The gate is not lying and it is not broken. The gate simply never
looks at your source files. It runs the test suite, then it points the audit tool
at **three tiny sample files** kept for that purpose, and those three pass. A file
in `src/` can fail its audit every single day and the gate stays green forever,
because the gate never asks it. This is a real gap, and it explains why nobody
had a count before tonight.

**Two things that need a person to look at them, whatever you decide about the
rest:**

1. `src/gui/usb_auth_widget.py` line 115 uses `QPainter`, `QPen` and `QBrush`.
   None of the three is imported in that file. Every time that widget repaints,
   it should raise an error. This is shipped GUI code, and it predates the
   recorded history.
2. `tests/test_suite_integrity.py` line 215 calls `pytest.skip(...)`, and that
   file never imports `pytest`. The test passes today only because that line is
   never reached. If the condition it guards ever becomes true, the test crashes
   instead of skipping.

Neither of these is an AI-introduced defect. Both are older than the repository's
git history.

## What was examined and what was not

| group | files | examined | archetype used |
|---|---|---|---|
| `.py` under `src/` (not `src/gui/`) | 133 | yes | `coding_archetype` |
| `.py` under `src/gui/` | 57 | yes | `gui_archetype` **and** `coding_archetype` |
| `.py` under `tools/` | 10 | yes | `coding_archetype` |
| `.py` under `tests/` | 291 | yes | `coding_archetype` |
| `.py` at repository root (production) | 14 | yes | `coding_archetype` (4 also `gui_archetype`) |
| `.md` anywhere tracked | 146 | yes | `docs_archetype` |
| **total examined** | **651** | | |

712 archetype invocations ran in total, one file per invocation.

### Files not examined, and the reason for each

The repository tracks 771 files. 651 were examined. 120 were not:

| not examined | count | reason |
|---|---|---|
| `dev_harness/**/*.py` | 19 | the harness itself; the audit brief forbids touching it, and an archetype auditing its own source is not independent evidence |
| `docs/audits/**/fixtures/*.py` | 29 | deliberate `known_good` / `known_bad` test fixtures; several are designed to fail, so counting them would inflate the failure rate |
| `.claude/hooks/*.py` | 4 | tooling configuration outside the shipped product |
| non-source files | 68 | `.json` (23), `.sh` (10), `.yml` (8), `.jsonl` (4), `.txt` (3), `.sol` (3), `.spec` (2), and one each of `.toml`, `.service`, `.ps1`, `.png`, `.lock`, `.ini`, `.ico`, `.icns`, `.gitignore`, `.gitattributes`, `.csv`, `.bat`, `NOTICE`, `LICENSE`, `.githooks/pre-push` — no archetype accepts these file types |

**A skipped file is not a passing file.** The 52 skipped Python files and the 68
skipped data files carry no verdict at all. The 29 fixtures include one that is
green while its own name promises red — see the control section.

## Instrument control

A census that reports zero failures because the tool silently did nothing is
worse than no census. Four controls establish that the runner works.

### Control A — coding archetype, deliberately broken file

I appended one function to `tools/deps.py` that calls
`subprocess.check_output(user_supplied, shell=True)`, ran the archetype, then
restored the file.

| state | exit code | `passed` | severities |
|---|---|---|---|
| before | 0 | `True` | low 18, medium 5 |
| broken | 1 | `False` | low 21, medium 5, **high 3** |
| after restore | 0 | `True` | low 18, medium 5 |

The three high findings came from three independent analyzers — `ruff S602`,
`bandit B602` and `semgrep subprocess-shell-true` — all at line 324, the injected
line. `git status` reports the tree clean after restore.

### Control B — docs archetype, deliberately broken file

I appended a duplicate `## Overview` heading to `README.md`.

| state | `passed` | evidence |
|---|---|---|
| before | `True` | medium 19, low 2 |
| broken | `False` | `structure DOC005` at line 341, "Duplicate heading text 'overview'" |

Restored. Tree clean.

### Control C — GUI archetype, deliberately broken file

I appended a bare `try` / `except Exception` / `pass` block to
`src/gui/theme_engine.py`.

| state | `passed` | evidence |
|---|---|---|
| before | `True` | no high finding |
| broken | `False` | `ruff S110` at line 648 |

Restored. Tree clean.

### Control D — absent target

I pointed the coding archetype at `src/does_not_exist_audit.py`. It answered
`passed=False`, `scanned=False`, and stated: "target was never scanned … an
empty report is not a clean one". A path typo therefore cannot masquerade as a
pass in this census.

### Exit-code and crash accounting

The runner records the exit code of every invocation and refuses to treat
unparseable output as a result. Across all 712 invocations:

- exit 0: 568
- exit 1: 144
- exit 139 (SIGSEGV): **0**
- exit 127 (`std::terminate`): **0**
- timeouts: **0**
- unparseable stdout: **0**
- reports with `scanned=false`: **0**
- reports with a non-empty `errors` array: **0**
- reports with an unavailable required analyzer: **0**

Every analyzer the archetypes need was installed and reported `ok` on every run:
`ruff`, `mypy`, `pyright`, `bandit`, `vulture`, `semgrep`, `proselint`, `vale`,
plus the four in-tree rule modules. No result in this census rests on a missing
tool.

### One control that came back yellow

`tests/harness_fixtures/2026-08-01_slop_rule/fixtures/known_bad.py` is named `known_bad`, and
it reports **`passed=True`**. I read it before reporting it. The slop rule does
detect both defects the fixture's docstring declares (`SL001` at line 15, `SL002`
at line 35), but it emits them at `medium` and `low`, and neither severity blocks.
The detector works; the fixture's name promises a red verdict that its own ground
truth cannot produce. Anyone who uses "does `known_bad` go red?" as a control on
this rule gets a false negative. The other six `known_bad` fixtures all report
`passed=False` correctly.

## Headline numbers

Two views of the same repository follow. The difference between them is itself a
finding, so both appear.

### View 1 — as the brief specified the routing

`gui_archetype` for `src/gui/`, `coding_archetype` for other Python,
`docs_archetype` for Markdown. 637 files.

| archetype | files | `passed=False` | files with high/critical | high | critical |
|---|---|---|---|---|---|
| `coding_archetype` | 434 | 96 | 96 | 380 | 0 |
| `gui_archetype` | 57 | 7 | 7 | 21 | 0 |
| `docs_archetype` | 146 | 41 | 41 | 512 | 0 |
| **total** | **637** | **144 (22.6%)** | **144** | **913** | **0** |

Every file that fails does so because of a high finding. No file failed for a
run-quality reason.

### View 2 — deepest available scan on every file

`coding_archetype` on all Python including `src/gui/`, plus the 14 root-level
production files. 651 files.

| group | files | `passed=False` | high | critical |
|---|---|---|---|---|
| Python | 505 | 124 (25%) | 563 | 0 |
| Markdown | 146 | 41 (28%) | 512 | 0 |
| **total** | **651** | **165 (25.3%)** | **1,075** | **0** |

All 53,791 findings at every severity, across the 637-file pass:

| severity | count |
|---|---|
| critical | 0 |
| high | 913 |
| medium | 22,147 |
| low | 27,718 |
| info | 3,013 |

### Rules that fired at blocking severity

Deepest-scan view, 1,075 blocking findings:

| count | rule | what it means |
|---|---|---|
| 333 | `structure:DOC005` | duplicate heading text in a Markdown file |
| 322 | `vulture:dead-code` | unused import, variable or function |
| 122 | `vale:write-good-so` | a sentence begins with "So" |
| 57 | `vale:write-good-thereis` | a sentence opens with an expletive construction |
| 38 | `ruff:S110` | `try` / `except` / `pass` — an error is discarded |
| 28 | `scaffolding:S003` | `self._x` is used in a method but never set in `__init__` |
| 20 | `ruff:S311` | non-cryptographic random used |
| 17 | `ruff:S101` | `assert` in production code |
| 17 | `bandit:B101` | the same assert, seen by a second analyzer |
| 13 | `ruff:S603` | subprocess spawn with a variable argument |
| 12 | `pyright:reportMissingImports` | an imported module cannot be resolved |
| 11 | `pyright:reportOptionalCall` | a possibly-`None` value is called |

The four largest rules — 834 of the 1,075 — measure style and hygiene, not
correctness. Prose rules alone (`DOC005`, `write-good-so`, `write-good-thereis`)
account for **512**, and every one of them lives in a Markdown file.

### Worst 15 files by high-finding count

| high | file |
|---|---|
| 265 | `docs-archive/llm-session-history/ACERVATOR_HOP5.md` |
| 62 | `docs/engineering-notes/2026-08-04_needed_fixes_list.md` |
| 47 | `src/core/mini_display.py` |
| 30 | `src/trading/profit_fold.py` |
| 29 | `docs-archive/llm-session-history/ACERVATOR_HOP2.md` |
| 29 | `docs-archive/llm-session-history/ACERVATOR_HOP3.md` |
| 29 | `docs-archive/llm-session-history/ACERVATOR_HOP4.md` |
| 26 | `src/exchange/base.py` |
| 25 | `acervator_watchdog.py` |
| 20 | `docs-archive/llm-session-history/DEVELOPMENT_CHRONICLE.md` |
| 18 | `src/stocks/broker_base.py` |
| 17 | `tests/test_topology_proposals_gui.py` |
| 16 | `tests/test_scrumming_capital_reservation.py` |
| 16 | `docs/engineering-notes/2026-08-05_sim_nuclear_2point0_and_optimization_audit.md` |
| 14 | `src/gui/competition_tab.py` |

## Age of each finding

I ran `git blame` on the exact line of all 984 distinct offending locations and
read the author date of the commit that last touched it.

| class | main-pass findings |
|---|---|
| dates to `be6aa04`, 2026-08-18, "initial upload" | 907 |
| dates to a commit in the recorded history, 2026-08-19 to 2026-08-24 | 6 |

### The six findings introduced during the recorded history

| file and line | rule | commit | date |
|---|---|---|---|
| `docs/EMITTER_IDENTIFICATION.md:1772` | `vale:write-good-so` | `3f2a76c` | 2026-08-24 |
| `docs/engineering-notes/2026-08-23_issue_100_abstention_leaves_the_denominator.md:193` | `vale:write-good-so` | `8d37ca8` | 2026-08-24 |
| `docs/engineering-notes/2026-08-23_issue_100_abstention_leaves_the_denominator.md:248` | `vale:write-good-so` | `8d37ca8` | 2026-08-24 |
| `docs/engineering-notes/2026-08-23_issue_100_abstention_leaves_the_denominator.md:296` | `vale:write-good-so` | `8d37ca8` | 2026-08-24 |
| `docs/engineering-notes/2026-08-24_issue_106_the_growth_cap_compounds.md:19` | `vale:write-good-so` | `d297206` | 2026-08-24 |
| `docs/engineering-notes/2026-08-24_issue_104_the_remaining_boosts_can_refuse.md:85` | `vale:write-good-so` | `eb90f77` | 2026-08-24 |

Zero of the six touch executable code. Zero affect behaviour.

### Limit on the dating, stated plainly

The repository's git history begins on 2026-08-18 with a single commit named
"initial upload". Everything written before that date collapses into that one
commit. Blame therefore cannot separate code written last month from code written
last year — it can only separate "arrived with the upload" from "written since the
upload". Read every PRE-EXISTING row as *predates the recorded history*, not as
*written on 2026-08-18*. This limit does not weaken the answer to the CTO's
question, because the AI work under scrutiny all falls inside the recorded window.

## Does the release gate catch these?

**No. A file can report `passed=False` while `python -m tools.gate` prints
`[OK] Release-ready`. That is the state of the repository right now: the gate is
green at version 3.26.0 with 8,263 tests, and 165 files fail their archetype.**

### The gap, for a non-programmer

Think of the archetype as a building inspector and the gate as the sign-off form.
The form has three boxes. Box one asks "did the fire alarms all ring when
tested?" — that is the test suite, and 8,263 alarms rang. Box two asks "does the
inspector's own equipment still work?" — and to check that, the gate hands the
inspector **three sample bricks** kept in a drawer, and the inspector correctly
reports that all three bricks are sound. Box three asks "is any paperwork left
open?" — none is. All three boxes tick, the form is signed, and the building is
declared ready. Nobody ever walked the inspector through the actual building. The
three bricks are not the building. That is the whole of the gap, and it is
structural rather than accidental: the gate was built to prove the inspector
works, and somewhere along the way that got read as proving the building is sound.

### The same statement in engineering terms

`dev_harness/harness/check_release_readiness.py` runs exactly three checks:

1. `_run_pytest()` — `pytest tests -q --tb=no` over the whole suite.
2. `_run_archetype_selfcheck()` — it constructs `CodingArchetype`, `GUIArchetype`
   and `DocsArchetype`, then calls `.review()` on **three hard-coded fixture
   paths**: `CODING_GOOD`, `GUI_GOOD`, `DOCS_GOOD`. It asserts each report is
   `passed=true`, carries a `falsification` string, and had no required analyzer
   absent.
3. `_run_claim_ledger_check()` — zero open claims in the ledger.

No line in that file enumerates `src/`, `tools/`, `tests/` or `docs/`. The
archetypes never see repository source. The check is a **self-test of the
instrument**, and its own docstring says so: "Each archetype self-check … against
its `known_good` fixture".

`tools/gate.py` wraps the above and adds one thing: it records which commit was
proved, and refuses to stamp a dirty tree. It adds no coverage.

Three consequences follow:

- **The gate proves the archetype does not false-positive. It never proves the
  archetype still detects.** The gate runs only `known_good` fixtures. It never
  runs a single `known_bad` fixture. If a detector silently stopped detecting
  tomorrow, the gate would stay green and nothing would notice. I ran the
  `known_bad` fixtures by hand for this audit; six of seven still go red, and the
  seventh is the yellow control noted above.
- **A repository-wide archetype pass belongs to no gate.** Nothing in the release
  path, the pre-push hook or the sidecar consults one.
- **The sidecar names a file that does not exist.** `.release_ready.json` records
  `"generator": "tools/harness/check_release_readiness.py"`. That path is absent
  from the tree; the real module lives at
  `dev_harness/harness/check_release_readiness.py`. The stamp is otherwise
  correct — commit `e7958a8`, matching HEAD.

### What the gate does catch, and it is not nothing

The gate is a strong instrument for the thing it measures: 8,263 tests over a
clean tree, a commit-pinned stamp, a dirty-tree refusal, and a self-test that
fails closed when an analyzer is missing. The failure is one of scope, not of
rigour.

## Findings of the "fails green" class

A fails-green check reports success when the thing it examines is broken or
absent. The census surfaced these without a dedicated hunt.

### In the harness and the gate

1. **The gate's archetype self-check runs three `known_good` fixtures and no
   `known_bad` fixture.** A detector that stopped firing keeps the gate green.
   One instance, described above.
2. **Routing a GUI file to `gui_archetype` produces a green verdict that
   `coding_archetype` contradicts — 15 measured cases.** `gui_archetype` runs
   `gui-static`, `ruff` and `bandit`. `coding_archetype` runs those plus `mypy`,
   `pyright`, `vulture` and `semgrep`. 15 of the 57 files in `src/gui/` report
   `passed=True` under `gui_archetype` and `passed=False` under
   `coding_archetype`. `src/gui/native_chart.py` is one of them, and its
   `coding_archetype` findings are exactly the four another unit reported tonight:
   unused imports of `field`, `QPushButton`, `QTimer` and `QPainterPath`. A green
   `gui_archetype` verdict is not evidence that a GUI file is clean, and View 1
   above (7 GUI failures) understates the truth by a factor of three (22 under
   View 2).
3. **`gui_archetype` never runs `pyright`, so it cannot see an undefined name.**
   `src/gui/usb_auth_widget.py` is green under `gui_archetype` and carries four
   `reportUndefinedVariable` findings under `coding_archetype`.
4. **`report.py` documents five previously-measured instances of this class**, all
   fixed before this census: a green report for a scan that never happened; a
   green report when every analyzer was absent; a missing `by_severity`; a green
   report with a non-empty `errors` array; a rule module that read nothing and
   reported `ok`. That base rate is the reason this section exists. The fixes
   hold — controls A through D confirm all five paths now fail closed.
5. **A severity split between two analyzers on one defect class.**
   `coding_archetype` exempts `ruff S101/S105/S106` for test files, with the
   comment "fixture credentials are fake", and separately suppresses `bandit B101`
   for test files — but not `bandit B105/B106/B107`.
   `tests/test_scrumming_capital_reservation.py` therefore carries five blocking
   `B105` findings for the exact fixture credentials the sibling exemption
   declares harmless.

### In the product code

The census counts these directly. Each is a place where the running program
discards a failure and carries on as though it succeeded:

| count | rule | mechanism |
|---|---|---|
| 38 | `ruff:S110` | `try` / `except` / `pass` — the exception is discarded, execution continues |
| 5 | `ruff:S112` | `try` / `except` / `continue` — the same, inside a loop |
| 28 | `scaffolding:S003` | an attribute is read that `__init__` never set; the resulting `AttributeError` is typically absorbed by a Qt slot, and the control silently does nothing |

**71 findings** of the fails-green class in shipped code. Concentrations:
`src/core/mini_display.py` (7 `S110` plus 23 `S003`), `acervator_watchdog.py`
(14 `S110`, 2 `S112`, 3 `S003`), `src/gui/testnet_tab.py` (4 `S110`),
`src/trading/smart_orders.py` (3 `S110`).

Two `S003` sites deserve a named mention because of where they sit:
`src/competition/bot_identity.py:184` reads `self._fallback_privkey_b64` and
`:260` reads `self._fallback_secret`, and `__init__` sets neither.

## Two defects worth a person's attention

I did not hunt for these. The census produced them, and I verified each by reading
the file.

### Three undefined names in a paint handler

`src/gui/usb_auth_widget.py` lines 20-22 import `Qt, QTimer, Signal, QObject` from
`QtCore` and `QColor, QFont` from `QtGui`. `QPainter`, `QPen` and `QBrush` are
never imported. `paintEvent` uses all three:

```
115:        p = QPainter(self)
116:        p.setRenderHint(QPainter.RenderHint.Antialiasing)
123:        p.setPen(QPen(colour.darker(150), 1))
124:        p.setBrush(QBrush(colour))
```

Static analysis reports `NameError` at each site. I did not execute the widget, so
I report the static verdict, not an observed crash. Blame: `be6aa04`, 2026-08-18 —
predates the recorded history. `gui_archetype` reports this file green, because it
does not run `pyright`.

### A skip path that raises

`tests/test_suite_integrity.py` line 215 calls
`pytest.skip("simulator tab not constructed in this build")`. The file contains no
`import pytest`. The line sits inside an `if sim is None:` branch. The suite is
green today, which means the branch is never taken. On the day it is taken, the
test raises `NameError` instead of skipping — a fails-green guard that turns into
a false red. Blame: `be6aa04`, 2026-08-18.

## Method and cost

- Runner: a read-only Python script that spawns one archetype subprocess per file,
  captures the exit code and the JSON report, and refuses to record an
  unparseable result as a pass. `MYPY_CACHE_DIR` is set per worker so parallel
  `mypy` runs cannot share a cache.
- Concurrency: 10 workers. The archetypes themselves ran unmodified, from the
  repository root, exactly as their CLI defines.
- Cost: **5,989 seconds of analyzer time** (99.8 minutes serial), compressed to
  **10.3 minutes of wall clock**. The 637-file main pass took 532 seconds; the
  57-file GUI cross-check took 63 seconds; the 14-file root supplement took 16
  seconds. `git blame` over 984 lines and the four controls added the remainder.
  The whole audit finished inside about 35 minutes.
- Per-invocation median: `coding_archetype` 10.5 s (max 127.5 s),
  `gui_archetype` 0.57 s, `docs_archetype` 0.47 s.

### What this census can and cannot support

It **can** support: the count of failing files, the count and identity of
high-severity findings, the rule that fired for each, the commit that last touched
each offending line, and the claim that the gate does not consult any of it.

It **cannot** support: any statement about the 52 unexamined Python files or the
68 unexamined data files; any dating finer than "before or after 2026-08-18"; any
claim that a finding is or is not a genuine defect in behaviour, except for the
two I read and verified by hand.

### Reproduction

```
python -m dev_harness.harness.coding_archetype <path>
python -m dev_harness.harness.gui_archetype    <path>
python -m dev_harness.harness.docs_archetype   <path>
```

One file per invocation. Passing several paths analyses only the first, which
understates the answer.

## Full list of failing files

Generated from the deepest-scan view. "Oldest blame" and "newest blame" are the
author dates of the commits that last touched the offending lines. A verdict of
PRE-EXISTING means every offending line dates to the initial upload.

### PYTHON -- 124 files passed=False

| file | high | rules that fired | oldest blame | newest blame | verdict |
|---|---|---|---|---|---|
| `EXCHANGE_DIAGNOSTIC.py` | 6 | ruff:S310 x2, pyright:reportPossiblyUnboundVariable x2, vulture:dead-code x2 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `acervator_watchdog.py` | 25 | ruff:S110 x14, scaffolding:S003 x3, ruff:S603 x2, ruff:S112 x2, ruff:S607 x1, ruff:S101 x1, mypy:call-overload x1, bandit:B101 x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `cartoon_screen.py` | 1 | ruff:S311 x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `download_archive.py` | 12 | ruff:S310 x5, ruff:S112 x3, mypy:var-annotated x2, ruff:S603 x1, vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `generate_essay_localized.py` | 2 | vulture:dead-code x2 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `os/splash/generate_splash.py` | 8 | vulture:dead-code x7, ruff:S108 x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/competition/base_config.py` | 2 | vulture:dead-code x2 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/competition/bot_identity.py` | 3 | scaffolding:S003 x2, vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/competition/competition_engine.py` | 3 | vulture:dead-code x2, pyright:reportReturnType x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/competition/local_testnet.py` | 3 | vulture:dead-code x2, ruff:S311 x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/competition/merkle_log.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/competition/season_schedule.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/competition/token_ledger.py` | 2 | mypy:var-annotated x1, vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/competition/trophy_generator.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/core/encryption.py` | 4 | vulture:dead-code x3, bandit:B107 x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/core/mini_display.py` | 47 | scaffolding:S003 x23, ruff:S110 x7, pyright:reportMissingImports x7, mypy:import-not-found x5, vulture:dead-code x4, mypy:truthy-function x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/core/notifications.py` | 2 | mypy:var-annotated x1, bandit:B107 x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/core/privacy_mask_registry.py` | 3 | ruff:S101 x1, ruff:S110 x1, bandit:B101 x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/core/settings.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/core/sound_engine.py` | 7 | ruff:S311 x7 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/core/trade_historian.py` | 1 | mypy:valid-type x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/core/usb_auth.py` | 6 | ruff:S607 x3, ruff:S603 x2, vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/design_system.py` | 7 | vulture:dead-code x4, mypy:call-overload x2, pyright:reportReturnType x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/exchange/api_docs.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/exchange/api_validator.py` | 1 | bandit:B107 x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/exchange/base.py` | 26 | vulture:dead-code x26 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/exchange/circuit_breaker.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/exchange/crypto_assets.py` | 4 | vulture:dead-code x3, ruff:S310 x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/exchange/currency_rate_monitor.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/exchange/idempotency.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/exchange/market_data.py` | 2 | ruff:S110 x1, vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/exchange/market_pairs_scout.py` | 2 | vulture:dead-code x2 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/gui/alerts_tab.py` | 3 | vulture:dead-code x3 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/gui/analytics_tab.py` | 6 | vulture:dead-code x6 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/gui/audio_suite.py` | 11 | vulture:dead-code x5, pyright:reportOptionalCall x4, mypy:no-redef x1, pyright:reportRedeclaration x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/gui/bot_swarm_list.py` | 2 | vulture:dead-code x2 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/gui/buy_confirmation_dialog.py` | 5 | vulture:dead-code x3, pyright:reportRedeclaration x2 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/gui/competition_tab.py` | 14 | vulture:dead-code x12, mypy:no-redef x1, pyright:reportRedeclaration x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/gui/init_wizard.py` | 3 | vulture:dead-code x3 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/gui/journal_tab.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/gui/launcher.py` | 4 | vulture:dead-code x4 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/gui/live_bot_window.py` | 3 | vulture:dead-code x2, ruff:S110 x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/gui/native_chart.py` | 4 | vulture:dead-code x4 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/gui/preflight_check.py` | 2 | bandit:B107 x1, vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/gui/qt_safe_events.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/gui/risk_tab.py` | 5 | vulture:dead-code x5 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/gui/screen_recorder.py` | 14 | ruff:S603 x4, ruff:S607 x3, pyright:reportMissingImports x3, ruff:S606 x1, mypy:import-not-found x1, pyright:reportRedeclaration x1, vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/gui/settings_dialog.py` | 5 | vulture:dead-code x3, ruff:S110 x1, mypy:has-type x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/gui/shared_testnet.py` | 3 | ruff:S110 x2, vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/gui/stock_main_window.py` | 9 | vulture:dead-code x6, mypy:import-not-found x1, pyright:reportMissingImports x1, pyright:reportIncompatibleMethodOverride x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/gui/testnet_tab.py` | 12 | vulture:dead-code x6, ruff:S110 x4, mypy:no-redef x1, pyright:reportRedeclaration x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/gui/theme_engine.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/gui/tradingview_chart.py` | 11 | vulture:dead-code x9, mypy:no-redef x1, pyright:reportRedeclaration x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/gui/usb_auth_widget.py` | 10 | vulture:dead-code x6, pyright:reportUndefinedVariable x4 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/stocks/alpaca_connector.py` | 3 | ruff:S110 x1, bandit:B105 x1, vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/stocks/broker_base.py` | 18 | vulture:dead-code x18 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/stocks/stock_accumulation_bot.py` | 2 | vulture:dead-code x2 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/stocks/stock_bot.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/stocks/tradingview_bridge.py` | 6 | vulture:dead-code x3, ruff:S104 x2, pyright:reportIncompatibleMethodOverride x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/trading/analytics_engine.py` | 2 | vulture:dead-code x2 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/trading/arbitrage.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/trading/capital_reservation.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/trading/cross_pool.py` | 2 | vulture:dead-code x2 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/trading/live_monitor.py` | 2 | vulture:dead-code x2 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/trading/market_inspector.py` | 2 | pyright:reportOptionalCall x1, vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/trading/mr_inspector.py` | 3 | vulture:dead-code x3 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/trading/phantom_balance.py` | 2 | vulture:dead-code x2 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/trading/poa_tournament.py` | 8 | ruff:S311 x7, ruff:S110 x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/trading/profit_fold.py` | 30 | ruff:S101 x15, bandit:B101 x15 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/trading/reconciliation.py` | 2 | ruff:S110 x1, mypy:var-annotated x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/trading/smart_orders.py` | 3 | ruff:S110 x3 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/trading/strategy_compare.py` | 6 | pyright:reportReturnType x3, mypy:call-overload x2, mypy:var-annotated x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/trading/ta_signal_provider.py` | 2 | vulture:dead-code x2 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/trading/triangular_swarm.py` | 4 | vulture:dead-code x2, ruff:S311 x1, mypy:var-annotated x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `src/trading/volume_guard.py` | 1 | ruff:S110 x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_api_load_monitor.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_bot_config_position_count_regression.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_build_sim_smart_wires.py` | 2 | vulture:dead-code x2 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_bus_injection_isolation.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_c01_preflight_snapshot.py` | 4 | vulture:dead-code x4 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_c06b_wire_removal_confirmation.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_c10_swarm_clears_on_last_delete.py` | 3 | vulture:dead-code x3 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_c39f_wire_does_not_rewrite_config.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_c51_indicator_panel_no_fabrication.py` | 4 | vulture:dead-code x4 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_c54_bot_status_contract.py` | 1 | mypy:var-annotated x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_canonical_tab_order.py` | 6 | pyright:reportOptionalCall x5, pyright:reportReturnType x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_claim_ledger.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_crypto_news_ticker.py` | 3 | vulture:dead-code x3 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_currency_rate_monitor.py` | 3 | vulture:dead-code x3 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_data_pool_ohlcv_coalescing.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_event_bus_unsubscribe.py` | 2 | vulture:dead-code x2 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_exchange_chart_urls.py` | 5 | vulture:dead-code x5 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_exchange_tab_boot_smoke.py` | 3 | vulture:dead-code x3 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_fleet_replay_panel_state_machine.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_fleet_sim_infrastructure.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_hooks.py` | 5 | vulture:dead-code x2, ruff:S603 x1, mypy:import-not-found x1, pyright:reportMissingImports x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_hooks_integration.py` | 3 | ruff:S603 x3 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_main_table_denom_cells.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_manual_fire_settled_fill.py` | 6 | vulture:dead-code x6 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_market_inspector.py` | 2 | vulture:dead-code x2 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_nuclear_capital_registry_fail_closed.py` | 8 | vulture:dead-code x8 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_nuclear_drives_the_sim_swarm.py` | 1 | pyright:reportOptionalCall x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_nuclear_panel_drives_v2.py` | 2 | vulture:dead-code x2 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_nuclear_receives_topology_injections.py` | 4 | vulture:dead-code x4 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_nuclear_stop_is_responsive.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_nuclear_uses_the_real_fleet_topology.py` | 2 | vulture:dead-code x2 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_release_gate_hook.py` | 1 | pyright:reportFunctionMemberAccess x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_scrumming_capital_reservation.py` | 16 | vulture:dead-code x11, bandit:B105 x5 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_sim_bus_fail_closed.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_sim_capital_registry_fail_closed.py` | 4 | vulture:dead-code x4 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_sim_ta_input_fidelity.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_sim_visuals_expand_reentrancy.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_simulator_tab_boot_armour.py` | 10 | vulture:dead-code x10 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_stack_mode_schema.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_start_refusal_does_not_spin.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_status_tab_sources.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_suite_integrity.py` | 1 | pyright:reportUndefinedVariable x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_target_denom_rows.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_ticker_refresher_wiring.py` | 2 | vulture:dead-code x2 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_topology_dismiss_persistence.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_topology_proposal_ranking_stability.py` | 3 | ruff:S311 x3 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_topology_proposals_gui.py` | 17 | vulture:dead-code x17 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_ytd_scrum_fold_and_errors_reset.py` | 1 | vulture:dead-code x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `tests/test_ytd_trade_sync.py` | 3 | vulture:dead-code x3 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |

### MARKDOWN -- 41 files passed=False

| file | high | rules that fired | oldest blame | newest blame | verdict |
|---|---|---|---|---|---|
| `docs-archive/llm-session-history/ACERVATOR_HOP2.md` | 29 | structure:DOC005 x25, vale:write-good-so x4 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs-archive/llm-session-history/ACERVATOR_HOP3.md` | 29 | structure:DOC005 x25, vale:write-good-so x4 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs-archive/llm-session-history/ACERVATOR_HOP4.md` | 29 | structure:DOC005 x25, vale:write-good-so x4 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs-archive/llm-session-history/TESTNET_POA_VERIFY_REPORT.md` | 1 | vale:write-good-thereis x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/EMITTER_IDENTIFICATION.md` | 1 | vale:write-good-so x1 | 2026-08-24 | 2026-08-24 | RECENT |
| `docs/audits/2026-07-24_gui_docs_archetypes/docs_fixtures/known_bad.md` | 1 | structure:DOC005 x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-07-25_bot_details_status_tab/REPORT.md` | 1 | vale:write-good-thereis x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-07-26_section4_hedge_rebalance.md` | 1 | vale:write-good-so x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-07-26_section8_extractor_pool_artillery.md` | 1 | vale:write-good-thereis x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-07-27_interop_usd_denom_settlement_audit_and_design.md` | 1 | vale:write-good-so x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-07-27_market_inspector_audit_and_design_proposal.md` | 3 | vale:write-good-thereis x2, vale:write-good-so x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-07-28_multibase_coordination_and_cross_pair_intelligence_plan.md` | 1 | vale:write-good-so x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-07-28_prior_art_multibase_coordination_research.md` | 1 | vale:write-good-thereis x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-08-04_full_codebase_defect_scan.md` | 7 | vale:write-good-so x6, vale:write-good-thereis x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-08-04_gate_log_stall_resolved.md` | 1 | vale:write-good-thereis x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-08-04_needed_fixes_list.md` | 62 | vale:write-good-so x41, vale:write-good-thereis x21 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-08-04_time_space_complexity_audit.md` | 3 | vale:write-good-thereis x2, vale:write-good-so x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-08-05_C01_save_state_merge_design.md` | 6 | vale:write-good-thereis x6 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-08-05_C01_simple_rule_design.md` | 1 | vale:write-good-so x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-08-05_C43_archived_pin_classification.md` | 1 | vale:write-good-so x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-08-05_docket_ohlcv_limit_since_defect.md` | 2 | vale:write-good-so x1, vale:write-good-thereis x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-08-05_paper_trader_concept_spec.md` | 3 | vale:write-good-so x2, vale:write-good-thereis x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-08-05_remediation_methodology.md` | 1 | vale:write-good-thereis x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-08-05_sim_nuclear_2point0_and_optimization_audit.md` | 16 | vale:write-good-so x13, vale:write-good-thereis x3 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-08-06_analysis_why_folds_do_not_fire.md` | 2 | vale:write-good-so x1, vale:write-good-thereis x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-08-06_defect_severity_triage.md` | 1 | vale:write-good-thereis x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-08-06_docket_ivp_regression_3_24_35_to_50.md` | 1 | vale:write-good-so x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-08-06_docket_scrummed_folded_card_reliability.md` | 1 | vale:write-good-so x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-08-06_docket_symbol_for_state_reload.md` | 1 | vale:write-good-so x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-08-06_docket_ta_skill_and_archetype.md` | 1 | vale:write-good-thereis x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-08-06_docket_target_balance_write_paths.md` | 2 | vale:write-good-so x2 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-08-06_investigation_ivp_blank_panel_verdict.md` | 2 | vale:write-good-thereis x2 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-08-06_measurement_tranche_compounding_fleet.md` | 2 | vale:write-good-so x2 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-08-06_tranche_lifecycle_audit_and_repair_plan.md` | 5 | vale:write-good-thereis x3, vale:write-good-so x2 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-08-09_cascade_series_validity_sweep.md` | 1 | vale:write-good-thereis x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-08-09_position_attribution_shared_account_research.md` | 1 | vale:write-good-thereis x1 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs/engineering-notes/2026-08-23_issue_100_abstention_leaves_the_denominator.md` | 3 | vale:write-good-so x3 | 2026-08-24 | 2026-08-24 | RECENT |
| `docs/engineering-notes/2026-08-24_issue_104_the_remaining_boosts_can_refuse.md` | 1 | vale:write-good-so x1 | 2026-08-24 | 2026-08-24 | RECENT |
| `docs/engineering-notes/2026-08-24_issue_106_the_growth_cap_compounds.md` | 1 | vale:write-good-so x1 | 2026-08-24 | 2026-08-24 | RECENT |
| `docs-archive/llm-session-history/ACERVATOR_HOP5.md` | 265 | structure:DOC005 x257, vale:write-good-so x8 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |
| `docs-archive/llm-session-history/DEVELOPMENT_CHRONICLE.md` | 20 | vale:write-good-so x16, vale:write-good-thereis x4 | 2026-08-18 | 2026-08-18 | PRE-EXISTING |

## Appendix — this document audited itself

The exact vale rule identifiers, written here inside a fenced block because vale
skips fenced blocks:

```
write-good.So        "Don't start a sentence with 'So '."
write-good.ThereIs   "Don't start a sentence with 'There is' / 'There are'."
structure DOC005     duplicate heading text
```

Elsewhere in this document those two identifiers appear as
`vale:write-good-so` and `vale:write-good-thereis`, with the dot replaced and the
suffix lowercased. The reason is a measured false positive, and it is worth
recording.

The first draft of this report failed its own `docs_archetype` run with 30 high
findings. 28 of the 30 were vale matching the literal rule name `write-good.So`
inside the evidence tables: vale's segmenter reads `good.` as a sentence end and
`So x4` as a new sentence opening with "So". The findings were real matches on
real text, and none of them described a defect in the writing. Two further hits
came from one table cell that spelled out the phrases the rule forbids.

Rewriting the labels cleared all 30. The document now reports:

```
passed = True    medium 38    low 75    high 0    critical 0
```

Two lessons carry over to the census numbers above:

1. **A high finding is not automatically a defect.** 179 of the 1,075 blocking
   findings in this census are `write-good` prose preferences, and 333 more are
   duplicate headings in archived chronicles. Any remediation plan should triage
   by rule before it counts files.
2. **A green verdict on this document is worth exactly one thing**: it proves the
   instrument ran over this file and found nothing blocking in it. It says nothing
   about the other 650. That is the same limit the release gate hits, at a scale
   of three.
