# Bot Details — Settings tab § 2 Scrumming Settings (v3.23.29)

**Display surface**: `src/gui/bot_live_settings.py` lines 2434–2588. Rendered only when `cfg.mode.value == "scrumming"`.
**Apply flow**: `_apply_changes()` at line 376. `target_balance` runtime-routed (`set_target_balance_live`); the remaining 8 fields fall through to plain `setattr(cfg, field, value)`.

**FALSIFICATION**: this report is wrong if (a) any listed field has been renamed or removed after this session, (b) a field marked “live-read” is actually snapshotted at init on a code path I missed, or © a runtime consumer count is off from the actual grep.

---

## Per-widget verdict — 9/9 correct

| Widget label | BotConfig field | Type / Default | Runtime route | Consumer reads | Verdict |
|---|---|---|---|---|---|
| Opposing Trade Interval | `scrumming_interval_pct` | `float` / `1.0` | setattr | `self.config.scrumming_interval_pct` (24 hits in src/trading/) | ✓ correct |
| BB Tolerance | `bb_tolerance_pct` | `float` / `1.0` | setattr | `self.config.bb_tolerance_pct` (2 hits) | ✓ correct |
| Landing Strip Candles | `bb_landing_strip_candles` | `int` / `3` | setattr | `self.config.bb_landing_strip_candles` (2 hits) | ✓ correct |
| TA Timeframe | `ta_timeframe` | `str` / `"1h"` | setattr | `self.config.ta_timeframe` (4 hits) | ✓ correct |
| Target Balance | `target_balance` | `float` / `200.0` | **`set_target_balance_live`** (MEM-244 anchor sync) | routes via bot method | ✓ correct |
| Max Entry Price | `max_entry_price` | `Optional[float]` / `None` | setattr | `self.config.max_entry_price` (1 hit) | ✓ correct |
| Min Entry Price | `min_entry_price` | `Optional[float]` / `None` | setattr | `self.config.min_entry_price` (1 hit) | ✓ correct |
| Trading Fee % | `trading_fee_pct` | `float` / `0.6` | setattr | `self.config.trading_fee_pct` (4 hits) | ✓ correct |
| Max Target Growth % | `max_target_growth_pct` | `float` / `1.0` | setattr | `getattr(self.config, 'max_target_growth_pct', 1.0)` (3 hits: lines 3420, 6722, 7177) | ✓ correct |

**Zero dead widgets in this subsection.** Every widget's backing field is live-read by trading logic; setattr on the config immediately affects the next tick.

---

## Notes on the correct-but-noteworthy items

### `target_balance` — the only runtime-routed field here

The Apply path routes this through `set_target_balance_live()` on ScrummingBot rather than plain `setattr` because:
- `target_balance` is the MEM-244 anchor for the hard position cap (target × (1 + max_target_growth%/100))
- The runtime uses `self._target_balance` as a stable anchor snapshot, plus growth-drain tracking
- Live-updating the anchor without also updating the drain accounting would leave the cap incoherent

Route: [_RUNTIME_ROUTED at bot_live_settings.py:423](src/gui/bot_live_settings.py:423). Live method: `set_target_balance_live()` at `scrumming_bot.py`. Verdict: correctly plumbed.

### `max_entry_price` / `min_entry_price` — Optional pattern

Widget uses `0.0` as the “no bound” sentinel; Apply-time lambda maps 0 → None before storing on cfg. Consumer at [scrumming_bot.py:? via `self.config.max_entry_price`] short-circuits when the field is None. Correct on both sides.

### `scrumming_interval_pct` — the “Opposing Trade Interval” rename

Widget label reads “Opposing Trade Interval” per operator directive 2026-04-25 (v3.15.53) but the config field name is retained as `scrumming_interval_pct` to avoid a wide refactor. Not a bug — deliberate cosmetic decoupling.

### `bb_tolerance_pct` + `bb_landing_strip_candles` — used together

Both consumed by the same Bollinger-band landing-strip detection logic. Two runtime hits each is normal (one at the consumer, one in a related helper).

### `trading_fee_pct` — feeds hysteresis math

Consumed 4 times, all in the opposing-direction hysteresis formula: effective deviation = `scrumming_interval_pct + trading_fee_pct`. Changing this at runtime instantly changes the effective SCRUM/FOLD trigger threshold. Correct.

---

## Not-in-scope but noticed in passing

None. The 9 widgets in this subsection are a clean set.

---

## Summary — action items for § 2

**None.** All 9 widgets in Scrumming Settings correctly toggle → apply → affect bot behavior on the next tick.

Correctly-plumbed widgets: **9/9 (100%)**.
Dead widgets: **0**.

Moving to § 3 Advanced Scrumming (P1.9) next.
