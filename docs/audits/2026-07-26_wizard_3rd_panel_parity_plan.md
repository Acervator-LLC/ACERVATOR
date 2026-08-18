# Wizard 3rd Panel — Bot Details Settings Parity Plan

**Date:** 2026-07-26  |  **Version:** v3.23.33  |  **Target:** `src/gui/bot_wizard.py` `TradingParamsPage` (line 517+)  |  **Reference:** `src/gui/bot_live_settings.py` mode/scrum/adv/hedge/cb/risk groups (lines 2311-2973)

Operator directive (2026-07-26):
> `3rd panel (Trading Parameters) must have an identical option set and style to
> the bot details -> settings tab excluding the Self-Destruct function. It must
> also be divided into identical sub sections.`

Scope: **Accumulation Trading Mode (Scrumming) only.** Grid mode is dead; Extractor
retains its own separate `Extractor — Pool & Artillery` group.

---

## Target sub-section structure (mirrors Bot Details Settings)

For Scrumming/Accumulation mode, the wizard's 3rd panel must present these six
`QGroupBox` sub-sections in this order:

1. **Trading Parameters** (6 widgets)
2. **Scrumming Settings** (9 widgets)
3. **Advanced Scrumming (P1.9)** (7 widgets)
4. **Hedge Rebalance** (2 widgets)
5. **Circuit Breakers (v3.15.58)** (6 widgets — no reset button; that's a live-only action)
6. **Risk Controls (MEM-244)** (5 widgets)

**Explicitly excluded per operator:** § 6 DANGER ZONE — Self-Destruct (live-only action).

---

## Field-by-field delta

### § 1 Trading Parameters (6 widgets)

| Bot Details field | Wizard current | Action |
|---|---|---|
| Order Visibility (combo) | `_visibility` (present) | move into new `mode_group` |
| Aggressive Trading (chk) | `_aggressive` (present) | move + retitle to match Bot Details (“Aggressive Trading (force IOC-limit takers)”) |
| Stack Mode (chk) | ❌ missing | **ADD** |
| Split Distance (spin) | ❌ missing | **ADD** |
| Tranche Count (spin) | ❌ missing | **ADD** |
| Spacing (combo linear/quadratic/exponential) | ❌ missing | **ADD** |

Note: wizard currently has `_bulk_group` (grid-only Bulk Trading) that pre-dates
the v3.23.25 Stack Mode rename. It should be removed on this pass since Grid mode
is dead. (Its visibility is gated on `_is_grid` which is hardcoded False since
v3.23.21 — dead UI.)

### § 2 Scrumming Settings (9 widgets)

| Bot Details field | Wizard current | Action |
|---|---|---|
| Opposing Trade Interval | `_scrumming_interval` (labeled “Opposing Trade Interval”) | move; label already matches |
| BB Tolerance | `_bb_tolerance` | move |
| Landing Strip Candles | `_ls_candles` | move |
| TA Timeframe | `_ta_timeframe` | move |
| Target Balance | `_target_balance` | move |
| Max Entry Price | ❌ missing | **ADD** |
| Min Entry Price | ❌ missing | **ADD** |
| Trading Fee % | ❌ missing | **ADD** |
| Max Target Growth % | `_max_target_growth_pct` | move |

### § 3 Advanced Scrumming (P1.9) (7 widgets)

| Bot Details field | Wizard current | Action |
|---|---|---|
| Detect Threshold | `_scrum_detect_pct` | move |
| Fire Threshold | `_scrum_fire_pct` | move |
| BB Midline Gate | `_bb_midline_gate` | move |
| Read Rate | `_scrum_read_rate` | move |
| Band Travel | `_band_travel_pct` | move |
| BB Bullseye Check | `_bb_bullseye` | move + refresh tooltip to match v3.23.31 (0.5 % + 0.2 % wick, not 0.1 %) |
| Scrum Fold Ratio | `_scrum_fold_pct` | move |

### § 4 Hedge Rebalance (2 widgets)

| Bot Details field | Wizard current | Action |
|---|---|---|
| Hedge Rebalance Active | `_hedge_rebalance` | move |
| Hedge Balance | `_hedge_amount` | move |

### § 5 Circuit Breakers (v3.15.58) (6 widgets)

| Bot Details field | Wizard current | Action |
|---|---|---|
| Soft CB Threshold | `_cb_soft_pct` | move |
| Hard CB Threshold | `_cb_hard_pct` | move |
| Soft CB Cooldown | `_cb_cooldown` | move |
| Max Cartridge Size | `_max_cartridge_pct` | move |
| Smart Cartridge | `_cartridge_smart_chk` | move + refresh version comment (v3.15.92) |
| Smart Ceiling | `_cartridge_smart_ceiling` | move |

(No reset button — reset is a runtime-only action, not a config field.)

### § 6 Risk Controls (MEM-244) (5 widgets)

| Bot Details field | Wizard current | Action |
|---|---|---|
| Enable Position Ceiling | `_position_ceiling_enabled` | move |
| Ceiling Multiple | `_position_ceiling_multiple` | move |
| Enable Detonation | `_detonation_enabled` | move + refresh tooltip to match v3.23.33 (“must be above anchor” gate) |
| Detonation TF | `_detonation_timeframe` | move |
| Min Confidence | `_detonation_confidence_min` | move |

---

## Wizard-only fields that Bot Details Settings tab does NOT expose

These are LIVE runtime-consumed config fields that the wizard captures at creation
but Bot Details never surfaces for live edit. **Operator decision needed for each:**

| Field | Runtime? | Options |
|---|---|---|
| `_scrum_profit_fold` → `profit_folding_active` | YES (drives fold-target growth) | (a) add to § 2 Scrumming Settings so it's editable everywhere; (b) drop from wizard (would default True); © keep on wizard 3rd panel but outside the 6 sub-sections in a “wizard-only” trailing area |
| `_scrum_upward_dist` → upward-distribution flag | YES (unclear consumer — needs verification) | same three options |
| `_wire_inflow_stack_pct` → `wire_inflow_stack_pct` | YES (Wire Stack routing) | same three options |
| `_profit_route`, `_profit_fold_pct`, `_profit_route_bot_id` (v3.20.85 profit-routing cluster, 3 fields) | YES (cross-bot routing) | same three options |
| `_gate_scrum_ta_chk`, `_gate_scrum_uptrend_chk`, `_gate_scrum_htf_chk`, `_gate_fold_ta_chk`, `_gate_fold_htf_chk` (v3.16.15 Strategy Gate Flags, 5 checkboxes) | YES (drives Conservative vs Lean profile) | same three options |
| `_check_interval` (Market Check Interval combo) | **NO** — v3.23.25 removed backing field | drop from wizard (retired) |

Grid-only fields to remove unconditionally (Grid mode dead since v3.23.21):
- `_investment`, `_positions`, `_distance`, `_increment`, `_spacing_style`,
  `_grid_summary`, `_bulk_group`, `_bulk_partial`.

---

## Style parity notes

Bot Details Settings pattern (used in every group):

```python
group = QGroupBox("Section Name")
form = QFormLayout(group)
self._configure_form(form)
# … addRow calls …
layout.addWidget(group)
```

Wizard currently:
- No `QGroupBox` per section — flat `QFormLayout` on the scroll area
- Individual `setVisible(False)` toggling on ~30 widgets in `set_mode()`

Refactor pattern for the wizard 3rd panel:
- Keep the outer `QScrollArea` (needed for dense form on narrow screens)
- Replace the flat form with a `QVBoxLayout` of six `QGroupBox` widgets
- `set_mode()` toggles ENTIRE groups: for Scrumming mode, show all six; for
  Extractor, hide all six and show `_extractor_group` (unchanged)

---

## Data-collection compatibility

The wizard's `get_config()` method reads values from `self._foo` attributes. As long
as attribute names are preserved during the move, `get_config()` continues to work
without change. Every field listed above keeps its existing attribute name; only
its container and visibility gate change.

New attributes to add (for the 3 currently-missing Scrumming Settings fields):
- `_max_entry_px` (new)
- `_min_entry_px` (new)
- `_trading_fee` (new)

And the 4 currently-missing Trading Parameters fields:
- `_stack_mode` (new)
- `_split_distance` (new)
- `_stack_count` (new)
- `_stack_spacing` (new)

`get_config()` must be extended to read these 7 new attributes and emit them into
the returned dict/BotConfig. Verified equivalent widgets already exist in Bot Details
so tooltips + defaults can be copied verbatim for consistency.

---

## Post-decision refined scope (2026-07-26)

Operator decisions received: Q1=(a) add to Bot Details too, Q2=(a) delete grid,
Q3=(a) drop check interval. Additional findings from BotConfig audit:

- `profit_folding_active`: already has a dedicated wizard page (`ProfitFoldingPage`,
  line 1746). Add to Bot Details § 2 for live-edit parity. **Don't** add to wizard
  3rd panel (already has its own dedicated page).
- `upward_distribution`: DEAD field — one write in wizard (line 1650), zero reads
  anywhere. Drop the wizard's hidden widget; leave the config schema alone so
  legacy bot_state.json entries don't break.

Final Bot Details additions (9 fields, 2 new groups):

- **§ 2 Scrumming Settings** — add `profit_folding_active` checkbox (existing
  `Advanced Scrumming` sits after; profit-folding gate is a scrumming behavior)
- **§ 3 Advanced Scrumming (P1.9)** — add `wire_inflow_stack_pct` spin
- **NEW § between Risk Controls and end: “Strategy Gate Flags (v3.16.15)”** — 5
  checkboxes (scrum_require_ta_bullish, scrum_hold_in_uptrend, scrum_defer_to_htf,
  fold_require_ta_bearish, fold_defer_to_htf)
- **NEW § after Strategy Gate Flags: “Profit Routing (v3.20.85)”** — combo
  (`profit_route`), spin (`profit_fold_pct`), line edit (`profit_route_bot_id`)

Final wizard 3rd panel target (8 groups for Scrumming mode):

1. Trading Parameters (existing 2 + 4 added Stack Mode fields)
2. Scrumming Settings (existing 5 + 3 added Max/Min Entry + Trading Fee — NOT
   profit_folding_active; that has its own page)
3. Advanced Scrumming (P1.9) (existing 7 + 1 added wire_inflow_stack_pct)
4. Hedge Rebalance (2)
5. Circuit Breakers (6)
6. Risk Controls (MEM-244) (5)
7. Strategy Gate Flags (v3.16.15) (5)
8. Profit Routing (v3.20.85) (3)

Extractor mode still shows `_extractor_group` in place of the 8 Scrumming groups.
Grid widgets deleted entirely.

## Implementation sub-phases

- **Phase A**: extend `bot_live_settings.py` with 9 new widgets across 2 existing +
  2 new groups. Live-edit + restore paths already exist for all 9 (verified). No
  BotConfig schema changes.
- **Phase B**: rewrite `TradingParamsPage.__init__` — replace flat form with
  QVBoxLayout of 8 QGroupBoxes, delete Grid + Check Interval + retired
  `_scrum_profit_fold`/`_scrum_upward_dist` widgets. Preserve every attribute
  name so `get_config()` continues to work.
- **Phase C**: run `gui_archetype` on both files; only self-report done if
  `passed=True`.
- **Phase D**: cascade v3.23.33 → v3.23.34.

## Operator decisions needed before implementation (resolved above)

1. **Wizard-only fields fate** — for the 10 fields listed above (profit_folding_active,
   upward_distribution, wire_inflow_stack_pct, profit_route cluster ×3, strategy gate
   flags ×5), what's the disposition?
   - (a) Add to the equivalent Bot Details sub-section too (bidirectional parity —
     bigger scope, touches bot_live_settings.py too)
   - (b) Drop from wizard 3rd panel entirely — fall back to defaults (simplest;
     assumes defaults are correct for all new bots)
   - © Keep on wizard 3rd panel in a trailing “Advanced (wizard-only)” group
     that Bot Details doesn't mirror (operator can still tune at creation)

2. **Grid-mode field removal** — confirm we can delete the dead grid widgets
   (`_investment`/`_positions`/etc. + `_bulk_group`)? Grid mode is hardcoded off
   since v3.23.21 so nothing consumes these.

3. **Check Interval retirement** — confirm we can drop `_check_interval` from the
   wizard? Bot Details removed it in v3.23.25 (backing field never read).

Once these three are answered, implementation is a mechanical reorganization + 7
new widget adds. Estimated diff: ~200 lines net (remove flat form + grid-only,
add 6 groups + 7 new widgets).
