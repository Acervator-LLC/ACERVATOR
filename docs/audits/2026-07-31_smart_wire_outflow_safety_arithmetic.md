# Smart Wire Outflow Safety Arithmetic — Design Spec

Version at write: v3.23.62. Consumer: v3.23.64 implementation cascade.
Author: Claude Opus 4.7 (1M context). Reviewer: operator (Ekthelius).

## 1  Problem

Smart Wire routes a configurable percentage of each Scrumming bot's
realized fold profit to one or more target bots
(`smart_wire.py::SmartWireManager._process_wire_backs`,
line 818). The percentage is a static operator input via the
Rate spinbox (the “25” visible in the Bot Swarm sidebar), scaled
by a fixed 70 % maturity haircut
(`smart_wire.py::BotLedger.MATURE_RATIO = 0.7`).

Neither the 70 % maturity constant nor the operator's Rate value
consults the source bot's own state before firing the outbound
transfer. As a result a bot can be drained below the level it needs
to execute its next Fold (buy-back) OR below the retained profit it
needs to sustain its programmed Compounding Growth cadence
(`max_target_growth_pct`). Operator directive 2026-07-31: "determine,
based on current price ranges, what percentage of profit from a
given Scrum can be routed out of a given bot without jeopardizing
its next Fold or Compounding Growth."

This document specifies the `safe_outflow_pct(…)` function that
replaces the blanket 70 % maturity haircut with a per-scrum, per-bot,
price-aware safety ceiling.

## 2  Definitions

Symbols used across the formulas below. All USD values.

| Symbol                | Type    | Source                                                                            |
|-----------------------|---------|-----------------------------------------------------------------------------------|
| `scrum_profit_usd`    | float ≥ 0 | Realized USD profit from this scrum trade                                       |
| `target_balance_usd`  | float > 0 | `bot.config.target_balance` — operator-set anchor                               |
| `current_price`       | float > 0 | Latest observed market price of target asset                                    |
| `band_lower`          | float > 0 | Price threshold where the bot's next Fold fires                                 |
| `band_upper`          | float > 0 | Price threshold where the bot's next Scrum fires                                |
| `next_fold_ammo_usd`  | float ≥ 0 | USD cost to fill the bot's next Fold — position_size × band_lower               |
| `current_cash_usd`    | float ≥ 0 | Bot's cash-available-to-buy (USD + USDC balance attributed to this bot)         |
| `compound_growth_pct` | float ≥ 0 | `bot.config.max_target_growth_pct` — % growth-per-cycle programmed              |
| `retained_this_cycle_usd` | float ≥ 0 | USD retained (not yet exported) from this cycle's realized scrums              |
| `distance_to_fold_pct`| float 0..1 | (current_price − band_lower) ÷ (band_upper − band_lower)                        |
| `safe_outflow_pct`    | float 0..100 | **Output** — safe % of `scrum_profit_usd` to export via smart wire            |

## 3  The formula

Two independent reserves must be satisfied from the bot's own funds
before any profit is available for export.

### 3.1  Fold reserve

The bot must retain enough dollars to execute its **next** Fold at
`band_lower` without needing exchange-side rebalancing. If existing
cash already covers it, no reserve is needed from this scrum's
profit. Otherwise reserve the shortfall, scaled by a **safety
factor** that grows as the price approaches `band_lower`:

```
fold_shortfall_usd = max(0, next_fold_ammo_usd - current_cash_usd)
safety_factor     = 0.2 + 1.8 × (1.0 - distance_to_fold_pct)
                    // 0.2 deep in scrum territory (upper band)
                    // 2.0 at the fold band (imminent)
                    // v3.23.64: steeper endpoints per operator
                    //          directive 2026-07-31 § 8.1.
fold_reserve_usd  = fold_shortfall_usd × safety_factor
```

`distance_to_fold_pct` is clamped to `[0, 1]`. When
`band_upper == band_lower` (degenerate) the safety factor is
forced to `1.5` (conservative). When `next_fold_ammo_usd == 0`
(bot has no next fold, e.g. fully drained target)
`fold_reserve_usd = 0`.

### 3.2  Compound-growth reserve

The bot's target grows up to `compound_growth_pct` per cycle. To
sustain that cadence the bot must retain, per cycle, at least:

```
compound_target_usd = target_balance_usd × (compound_growth_pct / 100)
compound_reserve_usd = max(0,
    compound_target_usd - retained_this_cycle_usd)
```

If `retained_this_cycle_usd` already covers the compound target
(prior scrums this cycle retained enough), no additional reserve
comes off this scrum's profit.

### 3.3  Safe outflow

```
reserves_total_usd = fold_reserve_usd + compound_reserve_usd
exportable_usd     = max(0, scrum_profit_usd - reserves_total_usd)
raw_safe_pct       = 100.0 × exportable_usd / scrum_profit_usd
                     if scrum_profit_usd > 0 else 0.0
safe_outflow_pct   = 0.0 if raw_safe_pct < 1.0 else raw_safe_pct
                     // v3.23.64 minimum-export floor per operator
                     //          directive 2026-07-31 § 8.4 — avoids
                     //          dust transfers.
```

The output is clamped to `[0, 100]`.

### 3.4  Composition with the operator's Rate spinbox

The Rate spinbox stays as the **operator's declared max**. Actual
outflow is the *lower* of the two:

```
effective_outflow_pct = min(operator_rate_pct, safe_outflow_pct)
```

Semantics: operator's Rate is the ceiling they're willing to
tolerate; safety math is the ceiling above which the bot self-
sabotages. Whichever binds first wins. A safety violation never
gets overridden by the operator's Rate; the operator's Rate never
gets exceeded by safety math.

## 4  Invariants

Enumerated so the pin tests can assert them individually.

1. **Non-negative reserves.** `fold_reserve_usd ≥ 0` and
   `compound_reserve_usd ≥ 0` always.
2. **Bounded output.** `0 ≤ safe_outflow_pct ≤ 100` always.
3. **Zero profit → zero export.** `scrum_profit_usd = 0`
   ⇒ `safe_outflow_pct = 0`.
4. **Zero cash + deep-in-fold → high reserve.**
   `current_cash_usd = 0` AND `distance_to_fold_pct = 0`
   ⇒ `fold_reserve_usd = next_fold_ammo_usd × 1.5`.
5. **Sufficient cash → zero fold reserve.**
   `current_cash_usd ≥ next_fold_ammo_usd`
   ⇒ `fold_reserve_usd = 0`.
6. **Retained ≥ target → zero compound reserve.**
   `retained_this_cycle_usd ≥ compound_target_usd`
   ⇒ `compound_reserve_usd = 0`.
7. **Operator floor wins on the low side.** When
   `operator_rate_pct < safe_outflow_pct`, effective =
   `operator_rate_pct`.
8. **Safety wins on the low side.** When
   `safe_outflow_pct < operator_rate_pct`, effective =
   `safe_outflow_pct`.
9. **Degenerate band → conservative safety factor.**
   `band_upper == band_lower` ⇒ `safety_factor = 1.5`.
10. **Distance clamp.** `current_price < band_lower`
    ⇒ `distance_to_fold_pct = 0` (imminent-fold treatment). \
    `current_price > band_upper`
    ⇒ `distance_to_fold_pct = 1` (deep-in-scrum treatment).

## 5  Edge cases

| Scenario | Behavior |
|----------|----------|
| `scrum_profit_usd = 0` | `safe_outflow_pct = 0`; wire fires nothing. |
| `next_fold_ammo_usd = 0` (fully drained) | `fold_reserve_usd = 0`; compound reserve alone gates. |
| `compound_growth_pct = 0` (compounding disabled) | `compound_reserve_usd = 0`; fold reserve alone gates. |
| Both reserves ≥ `scrum_profit_usd` | `exportable_usd = 0`; `safe_outflow_pct = 0`. |
| `current_price` missing / stale | Use last-known-price with a `[STALE]` diagnostic log; do not throw. |
| Bot has multiple outbound wires (operator wired A→B, A→C) | Formula runs ONCE per scrum. Each outbound wire uses the same `safe_outflow_pct` as its ceiling before its own Rate is applied. |
| `retained_this_cycle_usd > compound_target_usd` | Compound reserve = 0 (already satisfied). |
| `band_upper == band_lower` | Safety factor forced to 1.5 (see invariant 9). |

## 6  Integration points

Concrete files + functions the implementation cascade will touch.

### 6.1  New pure function

**`src/trading/smart_wire.py`** — module-level function:

```python
def compute_safe_outflow_pct(
    scrum_profit_usd: float,
    target_balance_usd: float,
    current_price: float,
    band_lower: float,
    band_upper: float,
    next_fold_ammo_usd: float,
    current_cash_usd: float,
    compound_growth_pct: float,
    retained_this_cycle_usd: float,
) -> float:
    ...
```

Pure function, no I/O, no logging. Testable in isolation without
Qt or a live bot. Returns `float` in `[0.0, 100.0]`.

### 6.2  Call site

**`src/trading/smart_wire.py::SmartWireManager._process_wire_backs`**
(around line 818). Currently:

```python
wire_amount = ledger.available_profit * self._wire_back_pct
```

Becomes (illustrative):

```python
safe_pct = compute_safe_outflow_pct(
    scrum_profit_usd=ledger.available_profit,
    target_balance_usd=source_bot.config.target_balance,
    current_price=source_bot.stats.current_price,
    band_lower=source_bot._fold_lower_band(),
    band_upper=source_bot._scrum_upper_band(),
    next_fold_ammo_usd=source_bot._next_fold_ammo_usd(),
    current_cash_usd=source_bot.stats.cash_balance_usd,
    compound_growth_pct=source_bot.config.max_target_growth_pct,
    retained_this_cycle_usd=source_bot._retained_this_cycle_usd(),
)
effective_pct = min(self._wire_back_pct * 100.0, safe_pct)
wire_amount = ledger.available_profit * (effective_pct / 100.0)
```

The `_next_fold_ammo_usd()`, `_retained_this_cycle_usd()`, and
band-accessor helpers on ScrummingBot may need thin new accessors
if they don't already exist; the implementation cascade will
enumerate them precisely.

### 6.3  Retire the 70 % maturity haircut (defer)

`BotLedger.MATURE_RATIO = 0.7` remains for the *mature-profit-cascade*
spawn logic (a distinct feature: it gates when a bot may seed a
child, not when a wire fires). Keep it; the SWOS formula supplants
only the pre-wire outflow ceiling.

### 6.4  GUI surfacing

Two small changes to `src/gui/bot_visualizer.py` /
`bot_wizard.py` when the Rate spinbox is edited:

- Rate spinbox tooltip updated to note it's an operator ceiling
  and the actual per-fire % may be lower due to safety math.
- Bot Swarm tab's `% Out` column (v3.23.62) already reflects the
  operator-configured sum. Add a hover-tooltip breakdown per bot:
  `"Operator ceiling: N% | Latest safe: M% | Effective: min(N,M)%"`.

## 7  Pin-test table

Ten explicit tests to lock the formula in the implementation
cascade. Each row is one `pytest` case. All are pure-Python calls
against `compute_safe_outflow_pct(…)` — no Qt, no bot state.

| # | Test name                                            | Inputs (partial)                                                                 | Expected `safe_outflow_pct` |
|---|------------------------------------------------------|----------------------------------------------------------------------------------|------------------------------|
| 1 | `test_zero_profit_returns_zero`                      | `scrum_profit_usd = 0`, everything else arbitrary                                | `0.0`                        |
| 2 | `test_zero_cash_imminent_fold_high_reserve`          | cash=0, price=band_lower, ammo=100, profit=200                                  | `≤ 25.0` (150 reserved)     |
| 3 | `test_full_cash_deep_scrum_high_export`              | cash=100, ammo=100 (fully covered), profit=100, price=band_upper, retained=0, growth=0 | `100.0`               |
| 4 | `test_compound_reserve_satisfies_on_prior_retention` | retained=50, target=1000, growth=5 % (⇒ target_compound=50), profit=100, cash≥ammo | `100.0`                  |
| 5 | `test_reserves_exceed_profit_returns_zero`           | profit=10, ammo=100, cash=0, safety=1.5 (150 reserved > 10)                     | `0.0`                        |
| 6 | `test_operator_rate_binds_low`                       | safe=80, operator_rate=25 → `effective = min(25, 80) = 25`                       | (composition test)           |
| 7 | `test_safety_binds_low`                              | safe=15, operator_rate=25 → `effective = min(25, 15) = 15`                       | (composition test)           |
| 8 | `test_degenerate_band_forces_conservative_factor`    | band_upper = band_lower, cash=0, ammo=100, profit=200                            | `≤ 25.0` (150 reserved)      |
| 9 | `test_output_always_bounded_0_to_100`                | property-based: `hypothesis`, any positive floats                                | always `0 ≤ result ≤ 100`    |
| 10| `test_next_fold_ammo_zero_gates_only_on_compound`    | ammo=0, growth=10 %, target=1000, retained=0, profit=200 → compound=100, safe=100/200=50 | `50.0`                 |

## 8  Open questions — operator answers (2026-07-31)

1. **Safety-factor endpoints: STEEPER.** Endpoints become
   `0.2 → 2.0` across `[band_upper, band_lower]`. New formula:
   `safety_factor = 0.2 + 1.8 × (1.0 - distance_to_fold_pct)`.
   Same clamping rules as § 3.1.
2. **`retained_this_cycle_usd` reset on Fold — accepted.**
   Counter resets to 0 on every Fold execution; increments on
   every Scrum's realized profit; checked at each wire-fire.
3. **Multi-outbound: DIVIDE ceiling across wires.**
   If safety says 40 % is safe and the source bot has 4 outbound
   wires, each wire caps at 10 % (not each at 40 %). Formula
   becomes `per_wire_safe = safe_outflow_pct / n_outbound_wires`.
   Operator additional constraint: **recompute at wire-fire time**
   (not at scrum-detect time) so the divisor reflects the current
   market structure. See § 6.2 update below.
4. **Minimum-export floor: 1 % — accepted.**
   If `safe_outflow_pct < 1.0`, return `0.0` — do not fire the
   wire this cycle. Prevents $0.02 dust transfers.

## 9  Adversarial verification

What would falsify this design:

- **Empirical:** a bot follows the safety math and *still* runs out
  of Fold ammo. Root cause would be a stale `current_cash_usd` OR a
  band that shifted (widened) between the safety compute and the
  Fold fire. Mitigation: recompute safety at wire-fire time, not at
  scrum-detect time.
- **Empirical:** compounding-growth cadence *drops* despite the
  compound reserve. Root cause: `retained_this_cycle_usd` counter
  reset semantics wrong (question 2 above). Mitigation: log the
  three values per wire fire so we can post-hoc reconstruct.
- **Operator preference:** the operator finds the composition
  rule (safety vs Rate — whichever binds) confusing. Alternative:
  the Rate becomes a *floor* not a ceiling (operator says
  "always try 25 % if safe"). That's a semantic flip; not
  cost-free. State a preference before v3.23.64.

## 10  Sign-off gate

Implementation cascade v3.23.64 proceeds when:

1. Operator approves the formula in § 3 as-drafted OR states
   deltas.
2. Operator answers the four open questions in § 8.
3. All ten pin tests in § 7 are written and green.
4. `gui_archetype` + `check_release_readiness.py` pass on the
   post-implementation cascade.

Once signed off, no further design churn in v3.23.64 — the
implementation is a straight port of §§ 3, 6, 7 to code.
