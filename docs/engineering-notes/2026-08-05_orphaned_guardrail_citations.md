# Orphaned guardrail citations — the 2026-07-25 archive sweep

**Filed** 2026-08-05 · **Build** v3.24.32, gate green (1105 tests)
**Trigger** The Bot Swarm audit found `bot_visualizer.py:1789` citing
`tests/test_swarm_row_parity.py`, which does not exist. This is a sweep
to find out whether that was isolated. **It was not.**

---

## 1. The measurement

```
archived tests (_archive/tests_pre_2026_07_25/)  : 317
live tests (tests/test_*.py)                     :  71
archived and never restored                      : 316
```

The reduction itself is not the finding — 1105 test cases still run and
the suite is green, so most of that 317 was consolidated, not lost.

**The finding is the citations.** 16 live source files tell the next
reader that an invariant is protected by a test that is not collected:

| Cited test | Cited by |
|---|---|
| `test_architectural_fitness.py` | `src/trading/bot_container.py:681` |
| `test_build_release_zip.py` | `tools/build_release_zip.py` |
| `test_cross_pool_coverage.py` | `src/trading/cross_pool.py` |
| `test_extractor_bot.py` | `src/trading/extractor_bot.py` |
| `test_extractor_start_balance_v3_20_66.py` | `src/gui/start_balance_check.py` |
| `test_gate_chain_parity.py` | `src/trading/gate_chain.py:23`, `src/trading/scrumming_bot.py:65` |
| `test_indicator_coverage.py` | `src/gui/bot_wizard.py:263` |
| `test_indicator_panel_coverage.py` | `src/gui/indicator_panel.py` |
| `test_mem171_scrumming_bot_port.py` | `src/trading/scrumming_bot.py:10975` |
| `test_mem220_ccxt_serialization.py` | `src/exchange/ccxt_connector.py:46` |
| `test_mem221_thread_safe_log_handler.py` | `src/gui/main_window.py` |
| `test_risk_manager_coverage.py` | `src/trading/risk_manager.py` |
| `test_rule_registry_coverage.py` | `src/core/rule_registry.py` |
| `test_swarm_row_parity.py` | `src/gui/bot_visualizer.py:1789` |
| `test_v1_1.py` | `src/trading/scrumming_bot.py` |
| `test_v3_23_7_surplus_realignment.py` | `src/trading/scrumming_bot.py` |

## 2. What is actually at risk — and what is not

I checked whether the unprotected invariants have already been
violated. **For the ones inspected, they have not.** This is a latent
gap, not a realised defect, and it should not be reported as one.

`bot_container.py:679-681` makes a **present-tense enforcement claim**:

> Direct `BotConfig(...)` calls outside this factory are flagged by the
> architectural fitness rule in `tests/test_architectural_fitness.py`.

Nothing flags them today. Measured — the only `BotConfig(` construction
in `src/` is `bot_container.py:736`, which is *inside* `make_bot_config`
(def at `:663`). **The invariant holds by discipline, not by
enforcement.** One drive-by construction would land unnoticed.

The citations split into two kinds, and they need different treatment:

- **Present-tense enforcement claims** — `bot_container.py:681`,
  `bot_visualizer.py:1789`, the `*_coverage.py` set. These assert an
  active guard. Restore the test or strike the claim.
- **Historical validation records** — `scrumming_bot.py:65`
  ("validated … bit-identical across 200 ticks *before this cutover
  landed*"). Accurate as history. The gap is that **no ongoing pin
  replaced it**, and gate-chain bit-identity is the most load-bearing
  invariant in the engine.

## 3. The release gate has no self-test

`tools/harness/check_release_readiness.py` is the single control between
a broken build and a version banner. Its pin test was archived and never
restored:

```
tests/test_check_release_readiness.py            -> absent
tests/__pycache__/test_check_release_readiness…pyc -> last ran 2026-06-17
_archive/tests_pre_2026_07_25/test_…readiness.py -> the copy
grep -c "def test_" tools/harness/check_release_readiness.py -> 0
```

The archived file's own rationale was that *a broken gate returning 0 is
worse than no gate*. That is exactly the current state: the gate is
unpinned and self-reports `[OK]`.

**Note also** the gate's path moved to `tools/harness/`. Anything (docs,
memory, habit) still invoking `tools/check_release_readiness.py` fails
with `Errno 2` — which reads as a tooling glitch, not a skipped gate.

## 4. Stale in the same region

`gate_chain.py:18-30` is headed `CURRENT STATUS (v3.18.11)` at build
v3.24.32 and says "this module is dead code — present but unused" —
contradicted by `scrumming_bot.py:67`, which imports and uses it. Fix
with the citation, same edit pass.

## 5. Recommended handling

Not a standalone cascade. Fold into the remediation sequence as a rule:

> **Any cascade touching a file that cites an archived test must, in the
> same pass, either restore the test or strike the claim.**

Restore first, in priority order:
1. `test_check_release_readiness.py` — pins the gate everything else
   depends on. Cheapest and highest leverage.
2. `test_architectural_fitness.py` — the only present-tense enforcement
   claim on a structural invariant.
3. `test_gate_chain_parity.py` — re-establishes an ongoing pin on
   SCRUM/FOLD bit-identity.
4. `test_swarm_row_parity.py` — the lock on the three-implementation
   row duplication (see Bot Swarm audit §4.16/4.17).

Archived copies restore from `_archive/tests_pre_2026_07_25/`. Expect
each to need repair against current APIs — the swarm-parity copy asserts
`self._live_rows_empty`, an attribute no longer assigned anywhere.
**Repair the test to the current contract; never weaken it to pass.**
