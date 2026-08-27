# § 3 — Advanced Scrumming (P1.9) — Bot Details Settings Audit

**Date:** 2026-07-26  |  **Version at audit:** v3.23.30  |  **Widget location:** `src/gui/bot_live_settings.py:2596-2681`

Seventh subsection of the Bot Details → Settings tab. Contains 7 widgets covering BB
DETECT/FIRE thresholds, midline gate, read-rate cadence, band-travel harvest, bullseye
override, and scrum→fold rebuy ratio.

---

## Widget inventory

| # | Widget attr | Config field | Type | Range/Default | Tooltip claim | Runtime consumer(s) |
|---|-------------|--------------|------|---------------|---------------|---------------------|
| 1 | `_detect_pct`    | `scrum_detect_pct`    | int   | 10–90 % / **75** | BB DETECT threshold + HARD GATE (v3.15.57) | `scrumming_bot.py:2527, 5144, 5932, 6785, 7839` |
| 2 | `_fire_pct`      | `scrum_fire_pct`      | float | 0.1–10 % / **0.5** | FIRE threshold — % from BB band | `scrumming_bot.py:5145, 5933` |
| 3 | `_midline_gate`  | `bb_midline_gate`     | bool  | **True** | Scrums above midline, folds below | `scrumming_bot.py:5824, 7818` |
| 4 | `_read_rate`     | `scrum_read_rate_min` | int   | 1–60 min / **5** | SEARCH read rate; TRACK 10× faster | `scrumming_bot.py:3891-3897` |
| 5 | `_band_travel`   | `band_travel_pct`     | int   | 0–100 % / **70** | Secondary harvest trigger; 0 disables | `scrumming_bot.py:5556, 5562` |
| 6 | `_bullseye`      | `bb_bullseye_check`   | bool  | **True** | Rapid Fire override on band touch **within 0.1 %** | `scrumming_bot.py:5728, 6020` |
| 7 | `_scrum_fold_pct`| `scrum_fold_pct`      | int   | 1–100 % / **100** | % of scrum proceeds queued for fold rebuy | `scrumming_bot.py:6634-6676` |

**All 7 fields exist in `BotConfig` (bot_container.py:114-145).**
**All 7 are live-editable** — declared in the live-editable set (bot_container.py:574-577) and
covered by the restore path (bot_container.py:2490-2507).
**All 7 have runtime consumers** (see column).

---

## Findings

### F1 — Bullseye tooltip inaccurate: claims 0.1 %, code uses 0.5 % (5× discrepancy)

**Severity:** Medium (operator-facing display bug — misinforms configuration decisions).

**Widget** (`bot_live_settings.py:2659-2661`):

```python
self._bullseye.setToolTip(
    "Rapid Fire override when price touches BB band within 0.1%.\n"
    "Overrides other gates when active.")
```

**Runtime** (`scrumming_bot.py:5733-5734`):

```python
_touch_tol_inline = 0.005   # ← 0.5 %, not 0.1 %
_wick_tol_inline  = 0.002   # ← 0.2 % (wick-only trigger)
```

The bullseye trigger actually fires when `abs(price - band) / band < 0.005`, i.e. **0.5 %**
from the band centerline, with a secondary 0.2 % wick trigger for candle-based touches.
The tooltip's “0.1 %” is off by 5× and does not mention the wick threshold at all.

**Fix candidate:** update tooltip to
> `"Rapid Fire override when price touches BB band within 0.5% (or the candle wick reaches within 0.2%). Overrides other gates when active."`

### F2 — `_touch_tol_inline` / `_wick_tol_inline` are magic constants

**Severity:** Low (code hygiene, not a live bug).

The two thresholds are hardcoded in the middle of the tick loop. If the tooltip is
truthful about 0.5 %/0.2 %, they should either be class-level constants
(`_BULLSEYE_TOUCH_TOL = 0.005`) or promoted to `BotConfig` fields
(`bb_bullseye_touch_pct`, `bb_bullseye_wick_pct`) so operators can tune them without
editing source. Deferred — flag only, not shipping in this pass.

### F3 — “Overrides other gates” claim is partially true

**Severity:** Info (documentation nuance, no code change).

Bullseye trigger sets `_be_upper` / `_be_lower` flags but does NOT unconditionally
bypass all gates. Downstream (`scrumming_bot.py:6020`) they interact with the
scrum/fold decision, but midline gate + hard-detect-gate still apply in some paths.
Tooltip currently reads absolute; a more precise phrasing:
> `"When triggered, bypasses the fire threshold — bullseye alone can arm a fire, subject to midline gate."`
Deferring wording tweak to future GUI pass.

---

## Verification methodology

1. **Field existence** — grep `bot_container.py` for each field name → confirmed 7/7.
2. **Live-edit path** — grep for name in `_LIVE_EDITABLE` set and restore path → confirmed 7/7.
3. **Runtime consumer** — grep `scrumming_bot.py` for each field name → all 7 have at least one meaningful consumer site (not just a getattr fallback).
4. **Semantic accuracy** — compared tooltip text to actual constant/expression at consumer sites for the two non-obvious cases (bullseye tolerance, TRACK-mode multiplier). TRACK 10× **confirmed** (line 3897: `_base_skip // 10`). Bullseye 0.1 % **falsified** (line 5733: `0.005`).

---

## Recommendation

Ship **F1 tooltip fix** as a small standalone patch (single-line string change, no
behavior change, no test bump beyond a source-shape pin if desired). F2 and F3 are
deferrable annotations for a future GUI-hygiene pass. All 7 fields are functionally
sound — no runtime bugs found in this subsection.

Proceed to § 4 (Hedge Rebalance) after operator approval of the F1 fix.
