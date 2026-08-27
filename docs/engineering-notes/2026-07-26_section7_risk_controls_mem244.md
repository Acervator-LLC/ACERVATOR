# § 7 — Risk Controls (MEM-244) — Bot Details Settings Audit

**Date:** 2026-07-26  |  **Version at audit:** v3.23.32  |  **Widget location:** `src/gui/bot_live_settings.py:2894-2973`

Five configuration widgets governing Position Ceiling (accumulation cap with fold
taper) and Detonation (auto-harvest on higher-TF bullish transition). Both features
default OFF; operator opt-in per bot.

## Widget inventory

| # | Widget attr | Config field | Type | Range/Default | Runtime consumer(s) |
|---|-------------|--------------|------|---------------|---------------------|
| 1 | `_ceiling_enabled`  | `position_ceiling_enabled`   | bool  | **False** | `scrumming_bot.py:2773, 3023, 3605, 4985, 6868, 10075` |
| 2 | `_ceiling_mult`     | `position_ceiling_multiple`  | float | 1.0–10.0 / **5.0** | `scrumming_bot.py:2776 (clamped)` |
| 3 | `_deto_enabled`     | `detonation_enabled`         | bool  | **False** | `scrumming_bot.py:4872, 8817` |
| 4 | `_deto_tf`          | `detonation_timeframe`       | enum  | “1d” or “1w” / **“1d”** | `scrumming_bot.py:8838` |
| 5 | `_deto_conf`        | `detonation_confidence_min`  | float | 0.50–1.00 / **0.75** | `scrumming_bot.py:8864` |

**All 5 fields exist in `BotConfig`** (bot_container.py:336-340).
**All 5 live-editable** (bot_container.py:590-592).
**All 5 in restore path** (bot_container.py:2511-2520).
**Additional runtime persistence** at bot_container.py:1246-1256 (state pickling).

## Runtime behavior spot-checks

### Position Ceiling

- **Ceiling formula** (scrumming_bot.py:2779): `anchor_target_balance * position_ceiling_multiple`
  — anchor is the STABLE creation-time anchor (NOT current target_balance, which grows
  via v3.23.7/Option B).
- **Defensive clamp** (2778): `mult = max(1.0, min(10.0, mult))` — even if config is
  corrupted, ceiling stays in the documented [1x, 10x] range.
- **Ratio calculation** (2801-2803): `_current_holdings * price * quote_to_usd / ceiling`
  — v3.15.55 quote→USD-aware for crypto-quoted pairs.
- **Fold-rate taper math** (2812-2828):
  ```
  ratio < 0.5   → 1.0    (100 % full rate)
  ratio 0.5-1.0 → 1.0 - (ratio - 0.5) / 0.5 * 0.9   (linear 100 % → 10 %)
  ratio >= 1.0  → 0.0    (hard stop)
  ```
  **Tooltip claim “100% → 10% as value approaches ceiling (ratio 0.5 → 1.0)” is
  exactly correct.** Formula verified at 2828.
- **Scrum always allowed** — no ceiling gate on scrum path; only fold rate is tapered.
  Matches tooltip.

### Detonation

- **Rate limit** (scrumming_bot.py:8833): `if now - self._detonation_last_check_ts < 3600` —
  literally 1 check per hour. Tooltip accurate.
- **Edge trigger** (8869): `fired = is_bullish and not self._detonation_last_signal_bullish`
  — fires ONCE on transition; sustained bullish state does not re-fire. Tooltip accurate.
- **Confidence gate** (8865-8866): `is_bullish = consensus_direction == BULLISH and
  consensus_confidence >= conf_min`. Both conditions AND-ed.
- **Additional gate** (8827-8829): `current_value <= anchor_target_balance` short-circuits
  detonation with **“Nothing above anchor to harvest”** — this is NOT surfaced in the
  operator-facing tooltip. See F18.
- **Check → execute wiring** (4872-4880): `_check_detonation_trigger` returns bool;
  `_execute_detonation` fires only on True; early return prevents downstream logic
  from acting on just-mutated state.

## Findings

### F18 — Detonation tooltip omits the “must be above anchor” gate

**Severity:** Low — real operator-facing knowledge gap.

Runtime gate at `scrumming_bot.py:8827-8829`:

```python
if current_value <= self._anchor_target_balance:
    # Nothing above anchor to harvest
    return False
```

The runtime docstring (8809-8810) documents this: `"current_value must be above
anchor (nothing to harvest if bot is below its anchor)"`. But the operator-facing
tooltip at `bot_live_settings.py:2933-2940` never mentions it. An operator whose
position is underwater (current value ≤ initial anchor) will see NOTHING fire even
though every documented gate (BULLISH, confidence ≥ 0.75, edge-triggered, once/hour)
appears to be met.

**Fix candidate:** append to the `_deto_enabled` tooltip:
> `"Additional gate: fires only when current value is above the anchor (no harvest
> if the bot is below its initial anchor)."`

### F19 — Everything else verified sound

All 5 fields fully wired end-to-end. Taper math exactly matches tooltip. Detonation
rate-limit and edge-trigger exactly match tooltip. Defensive clamps present. Check
→ execute wiring includes an early return to protect downstream state. R28 SSS
compliance on the try/except at 4881. No mechanical defects.

---

## Verification methodology

- BotConfig existence + live-editable + restore path + runtime consumers (mechanical).
- Ceiling formula, ratio math, and taper schedule cross-checked with tooltip.
- Detonation rate-limit (3600s), edge-trigger, confidence gate, and check→execute
  wiring cross-checked with tooltip.

**One real finding (F18 tooltip gap).** No defects.

Proceed to § 8 (Extractor — Pool & Artillery) after operator approves batching F18
with § 8's findings.
