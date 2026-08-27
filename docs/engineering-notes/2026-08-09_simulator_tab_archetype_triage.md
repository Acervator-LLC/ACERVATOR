# Simulator Tab — archetype triage and work plan

Date: 2026-08-09
Scope: `src/gui/simulator_tab/` — 18 files, 11,961 lines
Archetypes: coding, gui, ta, docs

## Why this audit exists

The operator asked why only the GUI archetype fired. The router chose one
archetype per file. Every file under `src/gui/` went to `gui_archetype`.

Measured tool sets:

| archetype | tools |
|---|---|
| coding | ruff, mypy, pyright, bandit, vulture, semgrep |
| gui | gui-static, ruff, bandit |

The GUI archetype omits mypy, pyright, vulture and semgrep. No file under
`src/gui/` was ever type-checked or dead-code-checked. That is the whole GUI,
including 11,961 lines of Simulator.

A GUI-only sweep of this tab reported **0 high findings**. The same tab with all
archetypes reports **11**. The harness was live and evaluating a third of what it
should have.

## Scan results

First scan: 17 high findings.
After correcting the TA archetype: **11**.

Six of the original 17 were defects in the TA archetype itself, written the same
day. They are listed under "Archetype defects" below.

| rule | count | class |
|---|---|---|
| `pyright:reportOptionalCall` | 7 | real, one root cause |
| `vulture:dead-code` | 4 | real, trivial |

## Triage

### P1 — `_act` may be None, called 7 times

`fleet_replay_panel.py` 1368, 1373, 1410, 1440, 1446, 1454, 1465.

Line 1242 binds `_act = self._activity_log_cb`. That attribute defaults to
`None` at line 170. `Start Replay` then calls `_act(...)` seven times.

The same file uses the guarded form three times — lines 535, 546 and 1322:

```python
self._activity_log_cb or (lambda m: logger.info("[FleetReplay] %s", m))
```

One binding of four is unguarded.

Reachability: `set_log_callbacks` has one caller, `simulator_tab.py:249`, behind
a `hasattr` guard. Any path that builds the panel without that call raises
`TypeError` on Start Replay.

Fix: bind `_act` with the same fallback the other three sites use.
Effort: one line. Risk: none.

### P2 — four dead imports

- `fleet_replay_panel.py:56` — `Qt`
- `fleet_replay_panel.py:57` — `QSizePolicy`
- `sim_stat_strip.py:23` — `Qt`
- `simulator_tab.py:28` — `QTabBar`

`QTabBar` is mine, left behind when the tab bar became the mode dropdown in
v3.24.97.

Fix: delete the four imports. Verify each name is unused first; `Qt` is a common
name and a false delete breaks the module.
Effort: minutes. Risk: low, and the archetype re-run proves it.

### P3 — 16 functions never called

Out of 302 defined in the tab. Qt slots connected by name produce false
positives here, so each needs a check before removal. Three are plain functions
with no caller at all:

- `master_clock.py:108` — `MasterClock.progress_pct`
- `sim_exchange.py:288` — `FleetSimExchange.cursor_ts_ms`
- `simulator_bot_state.py:215` — `load_sim_state`

`load_sim_state` is mine, written this session and never wired: nothing reads
the persisted simulator state back.

Fix: wire or delete, one at a time. `load_sim_state` should be wired — the file
it reads is written on every Load.

## Archetype defects found by running it

The TA archetype was written today. Running it on the real tab exposed six false
positives, all in rules I wrote. Each is now fixed and re-verified against the
positive control.

1. **TA003 substring matching.** `if k in name` matched the indicator `er`
   inside `every`, `every_n_candles`, `_MAX_MARKERS`, `WORKER_WAIT_CAP_S`. Four
   findings, all noise. Fixed with whole-word matching on snake_case components.

2. **TA004 and `pathlib`.** `Path(...) / ".acervator" / "bot_state.json"` is an
   `ast.Div`, so building a path read as a normalising division and produced a
   units mismatch on `p.resolve() == BOT_STATE_PATH.resolve()`. Two paths, no
   units. Fixed by ignoring string operands and path-like names.

3. **TA004 and duration division.** `(ts_ms - base_ts_ms) // step_ms` yields a
   candle index, legitimately compared against `n_candles`. Fixed by treating
   step and interval denominators as count-like.

4. **TA003 scanned prose.** The regex ran over raw file text, so any comment or
   docstring that MENTIONED a bound tripped it. This archetype documents the
   `adx_threshold = 500.0` incident and failed itself three times. Fixed by
   blanking comments and string literals before the scan, preserving offsets so
   line numbers stay correct.

5. **f-strings survived the strip.** Python 3.12+ tokenises them as
   `FSTRING_MIDDLE`, not `STRING`. The archetype's own message text still
   tripped it. Fixed by adding the f-string token types.

6. **`\b` became a backspace.** A shell heredoc turned the regex word-boundary
   into `\x08`, so TA003 matched an invisible control character and silently
   found nothing. It looked correct in `sed` output because backspace does not
   render. Caught only because the positive control went from six rules firing
   to five.

Item 6 is the important one. Without a positive control, a rule that matches
nothing is indistinguishable from a clean file.

## Positive control

`ta_probe.py` reconstructs all six incidents. Current state:

```
fired : TA001 TA002 TA003 TA004 TA010 TA011
MISSED: none
```

The archetype also scans clean on itself: 0 high.

## Execution — v3.25.0

All 11 findings are cleared. `coding_archetype` reports 0 high on all three
files. Gate before the bump: `[OK] Release-ready (v3.24.99, 2474 tests)`.
Gate after: `[OK] Release-ready (v3.25.0, 2474 tests)`. Both exit 0.

| item | action | proof |
|---|---|---|
| P1 `_act` | guarded with the same fallback as lines 535/546/1322 | pyright `reportOptionalCall` 7 → 0 |
| P2 four imports | deleted | vulture `dead-code` 4 → 0 |
| P3 `progress_pct` | deleted | measures clock position, not candles played |
| P3 `cursor_ts_ms` | deleted | duplicate of `MasterClock.current_ts_ms()` |
| P3 `load_sim_state` | wired via new `diff_spawns` | 3-press probe, control passes |

Each of the four imports was confirmed unused by AST. An earlier regex pass
reported 18/1/0/1 because the shell mangled the pattern; the regex was the
broken instrument, not the finding.

`progress_pct` was deleted rather than wired. It reports clock cursor position;
the panel's on-screen percentage reports candles executed. Wiring one to the
other would state one number and measure another — the units error TA004 exists
to catch.

### One finding this work added

`tests/test_hooks.py::test_archetype_pick_logic_module_level` asserted the
one-archetype-per-file rule — the rule the operator replaced. It passed on the
island only because the island still carried the old `archetype_gate.py`. It now
asserts the SET, requires `coding` on every `.py` file, and keeps a negative half
so a router returning everything for everything still fails. Mutation-verified:
restoring the old behaviour makes it fail, and the router was restored
byte-identical.

The island was not a faithful copy for that file. A green island gate did not
predict the working tree.

## Not done

- Time and space complexity pass. Covered separately in
  [`2026-08-09_simulator_tab_complexity.md`](2026-08-09_simulator_tab_complexity.md).
- `_pick_archetypes` over-includes: `signal_contract.py` gets the TA archetype
  because it mentions indicators three times. Over-coverage is preferred to
  under-coverage, but the marker heuristic is crude.
