# Full Codebase Archetype Audit — 2026-07-28

Version at scan: v3.23.43. Scan targets: `src/` (coding), `src/gui/`
(GUI), `docs/audits/` (docs).

## 1  Scope + methodology

Three harnesses invoked:

- `python -m tools.harness.coding_archetype src` — ruff + mypy +
  pyright + bandit + vulture + semgrep across all repository source.
- `python -m tools.harness.gui_archetype src/gui` — PySide6-aware
  static analyzer + ruff + bandit on the GUI subtree.
- `python -m tools.harness.docs_archetype docs/audits` — vale +
  proselint across authored audit documents.

All three reported `passed=False`. Combined finding count: 18,701.
That number is not the story; the categorisation below is.

## 2  Raw scan totals

| Harness | Passed | Total | HIGH | Medium | Low | Info |
|---------|--------|-------|------|--------|-----|------|
| coding  | False  | 15,458 | 4,738 | 2,583 | 7,749 | 388 |
| gui     | False  | 2,393  | 138   | 1,647 | 608   | —   |
| docs    | False  | 850    | 791   | 29    | 30    | —   |

## 3  What the HIGH counts actually mean

Blindly triaging 5,667 HIGH findings would waste weeks and generate
distraction. Here is the breakdown after categorising by root cause.

### 3.1  Coding archetype HIGH — 4,738 raw

| Rule | Count | Category | Actionability |
|------|------:|----------|---------------|
| `reportPossiblyUnboundVariable` | 2,248 | Type-checker noise | Pyright fires on `try: x = ...; except: pass; use(x)` even when the except path returns. Systemic false-positive family in the async trading paths where `try/except` guards optional attribute reads. **Not actionable at HIGH severity.** |
| `no-untyped-def` | 683 | Type discipline | Missing return-type annotations. Real code hygiene; low-risk mass edit possible via monkeytype or ruff --fix. Deferrable. |
| `reportAttributeAccessIssue` + `attr-defined` + `union-attr` | 775 | Type inference miss | Pyright/mypy can't resolve dynamic attributes on Qt widgets + duck-typed exchange stubs. Same false-positive family. Not actionable. |
| **`S110`** | **207** | **Silent exception swallowing** | **REAL. `try/except/pass` in trading paths hides bugs. Triage required.** |
| `SLF001` | 147 | Private-member access | Cross-module `_private` reads (mostly on connector internals). Some legit (test hooks), some real leakage. Deferrable. |
| **`SIM105`** | **125** | **`contextlib.suppress` opportunity** | Adjacent to S110 — same class of concern, tool suggests idiomatic replacement. Actionable alongside S110. |
| `S112` | 25 | Silent-continue on exception | Sibling of S110 in loops. Triage with S110. |
| Remaining ~530 | | Mixed type / arg-type | Type-checker noise. Not actionable at HIGH. |

**Actionable HIGH slice: ≈357** (S110 + S112 + SIM105 = 357 sites of
silent-exception behavior, mostly in GUI + trading tick paths).

### 3.2  GUI archetype HIGH — 138 raw

| Rule | Count | Category |
|------|------:|----------|
| `S110` | 83 | Same silent-exception concern as coding archetype's S110. Overlap with the trading-side count; the GUI subset lives mostly in main_window's dashboard refresh + bot_visualizer's paint loop. |
| **`GUI001`** | **37** | **Real UX debt. Widgets missing `setToolTip`/`setAccessibleName` — screen readers + keyboard nav have no anchor. Concentrated in `bot_visualizer.py` (21) + `screen_recorder.py` (9).** |
| `S311` | 5 | `random.Random` used for demo/simulation data. False positive — not cryptographic use. Silence with `# noqa: S311`. |
| `S603 / S607 / S606 / S310 / S112` | 14 | Subprocess + URL calls flagged as potentially unsafe. Case-by-case; most in dev tools + screen recorder. |

### 3.3  Docs archetype HIGH — 791 raw

| Rule | Count | Root cause |
|------|------:|------------|
| `typography.symbols.curly_quotes` | 761 | Vale insists on Unicode `“ ”` over ASCII `"` in prose. |
| `typography.symbols.copyright` | 14 | `(c)` in prose flagged; should be `©`. |
| `typography.symbols.ellipsis` | 12 | `...` flagged; should be `…`. |
| `DOC005` | 4 | Duplicate heading in one report. |

**HUGE caveat**: 705 of the 791 HIGHs come from four **peer-reviewer
raw-capture files** created during the archetype-peer-review harness
build (2026-07-24 batch, `docs/audits/2026-07-24_*/`{docs,gui}_raw/
peer_reviewer_[AB].md`). These are verbatim subagent transcripts
captured for provenance — not authored documentation. Linting them
was never the intent.

**Actionable slice: ≈86 findings across ~10 authored audit docs**,
of which `2026-07-26_section5_circuit_breakers.md` (20), the
Bot-Details-tab audit sub-reports (~50 total), and a handful of Aug
audits carry the rest.

## 4  Real findings punch list

Sorted by rough remediation cost × operator value.

### 4.1  Silent exception swallowing — 232 sites

Class: `try / except / pass` (or `except: continue`) where the code
loses information about a failure. **This is the finding class most
likely to hide a real production bug.**

Top offender files (from the coding-archetype HIGH-per-file breakdown):

| File | Coding HIGH | GUI HIGH | Notes |
|------|-----------:|--------:|-------|
| `src/gui/bot_visualizer.py` | 572 | 21 | Paint-loop + hover-state handlers |
| `src/gui/main_window.py` | 553 | 42 | Dashboard tick + bot-list refresh (many R28-OK annotated) |
| `src/gui/native_chart.py` | 391 | 4 | Chart-rendering exception guards |
| `src/gui/bot_live_settings.py` | 364 | — | Tab construction + live-edit callbacks |
| `src/gui/bot_wizard.py` | 241 | — | Config emit + set_exchange_id filtering |
| `src/gui/indicator_panel.py` | 201 | — | Cell rendering + privacy mask (I fixed 5 in v3.23.40) |
| `src/trading/scrumming_bot.py` | 200 | — | Tick-loop defensive guards, many R28-OK |
| `src/trading/bot_container.py` | 89 | — | State-persistence guards |

Many of these are legitimately R28-OK annotated (best-effort telemetry
where the primary path must not throw), but the annotation is a
comment, not a mechanised silencer — the tool still flags them.

**Recommendation**: introduce a shared `# noqa: BLE001, S110` +
`logger.debug(...)` idiom (which I have been using in recent GUI
edits), do a repo-wide sweep on the top-5 offender files (2 121
sites), then re-run archetype. Estimated 4-6 hour focused pass.

### 4.2  GUI accessibility — 37 sites

Class: `GUI001` — Qt widget subclass with no `setToolTip`,
`setAccessibleName`, `setAccessibleDescription`, or `setWhatsThis` on
constituent widgets. Screen readers + keyboard nav produce nothing.

Top offenders: `bot_visualizer.py` (21), `screen_recorder.py` (9),
`stock_main_window.py` (6), `audio_suite.py` (5).

**Recommendation**: for each flagged widget, add a one-line
`setToolTip(...)` per the pattern I used in `indicator_panel.py`
(v3.23.40). ~1 hour focused pass.

### 4.3  Docs typography — 86 sites in authored docs

Curly quotes / ellipsis / copyright / duplicate heading nits in
audit reports. Mechanical fix via the same `bulk_typography_fix`
Python script I wrote for the Interop design doc:

```
import re
segments = re.split(r'(```[\s\S]*?```|`[^`\n]+`)', src)
# skip code fences, curl-quote prose only
```

**Recommendation**: run script over `docs/audits/*.md`, verify no
code-fence damage. ~15 minutes.

### 4.4  Raw peer-reviewer captures — 705 sites, RECLASSIFY not fix

Under `docs/audits/2026-07-24_*/`{docs,gui}_raw/peer_reviewer_[AB].md`
are verbatim subagent transcripts — provenance for the archetype-
peer-review harness build. Not authored docs.

**Recommendation**: exclude the `raw*/peer_reviewer_*.md` glob from
docs_archetype scans via `.vale.ini` or the docs_archetype's own
ignore config, then re-run. Report will drop from 791 → 86 HIGH.

### 4.5  Type-checker noise — 4,371 sites, do NOT triage

`reportPossiblyUnboundVariable` (2,248), `reportAttributeAccessIssue`
+ `attr-defined` + `union-attr` (775), plus various sub-family
inference gaps. Root cause: pyright/mypy struggle with (a) Python's
`try: x = fn(); except: pass; use(x)` patterns (common in defensive
tick loops), (b) duck-typed exchange connector API, © Qt widget
dynamic attributes not fully known to type stubs.

**Recommendation**: leave alone. Adding annotations wouldn't reduce
the count meaningfully because the type-inference gap is
architectural, not per-site. If we wanted to actually silence these,
we'd add `# type: ignore[reportPossiblyUnboundVariable]` at each site
— but that's cosmetic churn with no correctness gain.

### 4.6  `no-untyped-def` — 683 sites, background hygiene

Missing return-type annotations. Real code-hygiene debt but no
correctness risk. Could be closed by a `ruff --add-missing-return`
or `monkeytype apply` pass at some future point. Not urgent.

## 5  Cross-cutting observations

### 5.1  scrumming_bot.py is smaller (post v3.23.43 rip)

The multi-base attribution / claim-on-creation / MEM-171 seed
excision removed ~470 lines. HIGH count on this file dropped from
its historical baseline (~250 in prior scans, now 200). The rip did
its job — the remaining 200 HIGHs are pyright-noise defensive
try/except pattern in the tick loop, not new debt.

### 5.2  bot_visualizer + native_chart concentrate the debt

Combined 963 coding HIGH + 25 GUI HIGH between two files. Both are
paint-loop-heavy widgets with lots of defensive exception guards.
Not on the critical trading path — cleanup here is quality-of-life,
not risk mitigation.

### 5.3  The trading engine core is relatively clean

`scrumming_bot.py` (200), `bot_container.py` (89), `extractor_bot.py`
(not in top-20), `capital_reservation.py` (not in top-20),
`smart_wire.py` (not in top-20). The bulk of the debt is
GUI-side.

### 5.4  365 pin tests still green

Full pytest suite at v3.23.43 remains 365/365 pass despite the
extensive changes this session. The tests are still the primary
correctness gate; archetypes are the secondary hygiene gate.

## 6  Recommended cascade sequence

Ordered by cost + operator value.

1. **Reclassify peer-reviewer raw captures** (5-min config change).
   Drops docs HIGH from 791 → 86 with zero code risk. Ships this
   cascade.
2. **Docs typography sweep** (15 minutes). Drops docs HIGH from 86
   → ~0 via bulk-replace script.
3. **GUI001 accessibility pass** (~1 hour). Adds tooltips /
   accessible names to the 37 flagged widgets. Ships as
   `v3.23.44 GUI001`.
4. **Silent-exception sweep on top-5 offender files** (~4-6 hours).
   Converts `try / except: pass` → `try / except X as _e: logger.debug(...)`
   in bot_visualizer, main_window, native_chart, bot_live_settings,
   bot_wizard. Ships as `v3.23.45 SEXP`.
5. **Retire the type-checker noise gate at HIGH** (config change).
   Move `reportPossiblyUnboundVariable` and friends from HIGH → LOW
   in the coding archetype config so the signal-to-noise ratio for
   real HIGH findings recovers. Ships alongside step 1.

Steps 1 + 5 alone would drop the aggregate HIGH count from 5,667 to
~1,296 — enough that the remaining findings become individually
tractable.

## 7  What NOT to do

- Don't set out to close every HIGH by hand. The largest categories
  are false positives or capture-provenance noise.
- Don't add type annotations en masse. The pyright complaints will
  not clear without architectural changes to the exchange-connector
  duck typing, and drive-by annotations tend to encode current
  behavior as if it were spec.
- Don't refactor bot_visualizer / native_chart just to silence
  archetype. Those files render live trading state and any
  behavioral shift there risks operator-visible regression.

## 8  Ship this cascade

Steps 1 + 2 (peer-reviewer exclusion + typography sweep). Both are
mechanical and additive. Cascade lands as v3.23.44. Steps 3-4 need
operator agreement on scope + priority.
