# § 5 — Circuit Breakers (v3.15.58) — Bot Details Settings Audit

**Date:** 2026-07-26  |  **Version at audit:** v3.23.31  |  **Widget location:** `src/gui/bot_live_settings.py:2712-2836`

Six configuration widgets plus an operator reset button. Covers soft/hard price-move
circuit breakers and the Max Cartridge / Smart Cartridge threshold system that fires
aggressive rebalances on target drift.

## Widget inventory

| # | Widget attr | Config field | Type | Range/Default | Runtime consumer(s) |
|---|-------------|--------------|------|---------------|---------------------|
| 1 | `_cb_soft_pct`             | `circuit_breaker_soft_pct`         | float | 0–100 % / **25.0** | `scrumming_bot.py:2084, 6803, 7856` |
| 2 | `_cb_hard_pct`             | `circuit_breaker_hard_pct`         | float | 0–100 % / **35.0** | `scrumming_bot.py:2083` |
| 3 | `_cb_cooldown`             | `circuit_breaker_cooldown_candles` | int   | 1–100  / **3**     | `scrumming_bot.py:2138` |
| 4 | `_max_cartridge_pct`       | `max_cartridge_size_pct`           | float | 0–200 % / **10.0** | `scrumming_bot.py:4652` |
| 5 | `_cartridge_smart_chk`     | `max_cartridge_smart`              | bool  | **False**          | `scrumming_bot.py:4678` |
| 6 | `_cartridge_smart_ceiling` | `max_cartridge_smart_ceiling_pct`  | float | 1–100 % / **30.0** | `scrumming_bot.py:4693-4697` |
| — | `_cb_reset_all_btn`        | (action) → `reset_circuit_breaker("all")` | button | — | `scrumming_bot.py:2446-2499` |

**All 6 fields exist in `BotConfig`** (bot_container.py:158-186).
**All 6 live-editable** (bot_container.py:579-582).
**All 6 in restore path** (bot_container.py:2521-2532).
**Reset method exists** (scrumming_bot.py:2446) — documented as "Always non-raising —
fail-soft for GUI buttons", returns `{"applied": [...], "scope": ...}` dict.

## Runtime behavior spot-checks

- **Soft CB semantic** (scrumming_bot.py:2118-2159): tripped side = “scrum” or “fold”
  based on which direction the offending candle moved. Blocks that side only; other
  side continues. Self-resets after `cooldown_candles`. Confirmed matches tooltip.
- **Hard CB semantic** (2078-2093): both sides frozen, `_cb_hard_tripped=True`, bot
  transitions to `BotState.PAUSED`. Persists across restart via `restore_state`
  (line 3141-3152). Operator MUST call `reset_circuit_breaker("hard")` to resume.
  Confirmed matches tooltip.
- **Smart Cartridge clamp** (4695-4697):
  ```python
  _smart_pct = max(_interval_floor, min(_smart_ceiling, _bb_range_pct))
  ```
  Ceiling is a hard-clamped upper bound; floor is `scrumming_interval_pct` (structural
  anti-fee-thrash floor).
- **UnboundLocalError fix** (v3.15.94, comment at 4665-4676): earlier
  smart-cartridge code read bare `bb_result` which Python promoted to a
  function-local from later assignment. Now reads `self._last_bb` (previous tick's
  cached bb_result). First-tick behavior falls back to static — correct.

## Findings

### F10 — Version marker mismatch: Smart Cartridge section

**Severity:** Trivial (comment/doc rot, no runtime impact).

Section comment says v3.15.93, but two tooltips inside the section say v3.15.92:

| Location | Text |
|----------|------|
| `bot_live_settings.py:2781` | `# v3.15.93 — Smart Cartridge calibration` |
| `bot_live_settings.py:2791` (tooltip) | `Default OFF preserves static behavior. v3.15.92.` |
| `bot_live_settings.py:2808` (tooltip) | `Default 30%. v3.15.92.` |
| `scrumming_bot.py:4656` (runtime comment) | `# v3.15.92 SMART CARTRIDGE:` |
| `scrumming_bot.py:4665` (runtime comment) | `# v3.15.94 hot-fix:` |

Runtime code says v3.15.92 for the feature + v3.15.94 for the UnboundLocalError
hot-fix. The GUI section comment is the outlier — should say v3.15.92 to match
runtime, or drop the version entirely.

**Fix candidate:** change `# v3.15.93 — Smart Cartridge calibration` →
`# v3.15.92 — Smart Cartridge calibration` at `bot_live_settings.py:2781`.

### F11 — Reset button gives no direct on-screen feedback

**Severity:** Low (UX). Not shipping in this pass unless operator prioritizes it.

`bot_live_settings.py:2820-2833`:

```python
def _on_cb_reset_all():
    if hasattr(self._bot, "reset_circuit_breaker"):
        try:
            self._bot.reset_circuit_breaker("all")
        except Exception:
            pass
```

The button ignores the returned `{"applied": [...]}` dict — operator only sees the
`CIRCUIT BREAKER RESET (all): ...` line if they scroll to the log tab. On a live
mid-day panic reset the operator wants immediate on-button confirmation ("reset
applied: hard breaker cleared“ or ”no circuit breakers active"). No visible feedback
= “did it actually click?” doubt.

**Fix candidate options:**
- Flash button text briefly (“Reset OK ✓” / “Nothing to reset”).
- Show a QToolTip.showText or a status-bar transient message.
- Emit a QMessageBox.information if any items in `applied`.
- Do nothing (log-only pattern is intentional, per existing hooks convention).

Deferrable — depends on operator preference for GUI verbosity.

### F12 — “Soft ceiling” terminology

**Severity:** Info. No fix.

Runtime treats `max_cartridge_smart_ceiling_pct` as a hard clamp — `min(ceiling,
bb_range)` — but the tooltip calls it “Soft ceiling”. Two readings:

- **Operator-facing lens** (defensible current wording): “soft” = operator-configurable
  soft limit, as opposed to `scrumming_interval_pct` which is a **hard structural
  floor** (never violated). Under this lens, tooltip is accurate.
- **Implementation lens** (would call it “hard”): the ceiling clamps in code —
  volatility expansion cannot push the effective cartridge threshold above it.

Existing convention across Acervator uses “hard floor / soft ceiling” for the
“structural vs operator-tunable” distinction, so keeping the tooltip as-is is
internally consistent. Not a defect.

### F13 — `max_cartridge_size_pct` range 0–200 %

**Severity:** Info. No fix.

Widget accepts up to 200 % — huge range for a rebalance trigger. Intentional
(accommodates severely-drifting positions after catastrophic price moves), and 0
disables. No behavioral concern; noting for the record.

---

## Verification methodology

- Same as prior sections: BotConfig existence, live-editable set, restore path,
  runtime consumer sites.
- Additional runtime-semantic spot-checks on soft/hard trip machinery
  (`scrumming_bot.py:2046-2159, 2446-2499`), smart cartridge clamp (4655-4697),
  and restore-persistence for hard breaker (3141-3152).
- Reset method contract (`Always non-raising — fail-soft`) verified against widget
  handler.

**No mechanical defects.** All 6 fields wired end-to-end. Reset button connects
correctly; behavior contract holds. Three annotations (F10 comment rot, F11 UX
polish, F12 terminology) plus one info (F13 range). Recommend shipping **F10**
tooltip/comment fix; F11 as an operator call; F12/F13 leave alone.

Proceed to § 6 (DANGER ZONE — Self-Destruct) after operator batches F10 with any
§ 6 findings.
