# Operator Settings, Field by Field

Reference. Source: LEGACY, the fourteen-part manual, Part 4 "Features
Catalogue", pages 32 to 44 for the Scrumming Bot and pages 45 to 49 for the
Extractor Bot, plus the risk-control table on page 7. The claim audit calls
these two sections the highest-value block in the whole legacy manual, and
measurement against `src/trading/container/config.py` agrees.

Every default below was read at runtime from `dataclasses.fields(BotConfig)`.
`BotConfig` carries 72 fields. The legacy manual says "80 or more"; 72 is the
count. `_BOT_CONFIG_SCRUMMING_ONLY_FIELDS` names 40 of them and
`_BOT_CONFIG_EXTRACTOR_ONLY_FIELDS` names 15. Every name in both manifests
resolves to a real field, so neither manifest carries a dead entry.

## Read this first: eleven settings do not reach the bot

The legacy operator sections document eleven settings with types and defaults,
as though an operator could set them. `_DEPRECATED_KWARGS` in
`src/trading/container/config.py:379` holds all eleven.
`_sanitize_deprecated_kwargs` at `config.py:564` strips them, and
`make_bot_config` at `config.py:605` calls that stripper before it constructs
the `BotConfig` at `config.py:632`.

| Setting | Legacy default | State |
| ------- | -------------- | ----- |
| `market_check_interval` | 5 seconds | dropped |
| `bulk_trading` | False | dropped |
| `bulk_partial_on_return` | True | dropped |
| `fold_mode` | equal | dropped |
| `fold_target` | all_buy | dropped |
| `fold_target_count` | 5 | dropped |
| `profit_fold_pct` | 100 | dropped |
| `distribute_target` | all_sell | dropped |
| `distribute_target_count` | 5 | dropped |
| `position_count` | 10 | dropped |
| `position_distance_pct` | 2.0 | dropped |

An operator who sets one of these gets no error and no effect. Building a bot
with all eleven passed in succeeds, and afterwards none of the eleven appears on
the object. Calling `BotConfig(**kwargs)` directly with the same eleven raises
`TypeError`, which proves the stripper does real work rather than a permissive
constructor swallowing them. Passing an invented field name through
`make_bot_config` still raises, so the stripper drops a named list and not
anything unknown.

Set none of the eleven. Their behaviour, where the platform still has it, lives
elsewhere: the fold routing runs from the tranche book in
`src/trading/scrumming/tick_phases.py`, and the wire routing runs from
`src/trading/scrumming/wire_routing.py`.

## Scrumming Bot

### Identity and lifecycle

- **`exchange_id`** — required. The internal identifier of the connected
  exchange. A bot does not change exchange at runtime; a different exchange
  means a new bot. `CapitalReservationRegistry.effective_available` in
  `src/trading/capital_reservation.py:443` returns a bot's holdings minus every
  other bot's claim on the same asset, keyed by asset and bot, so the bot's
  identity decides what it may spend.
- **`symbol`** — required, in `BASE/QUOTE` form. The bot follows this exact
  pair. Five symbols means five bots.
- **`mode`** — `BotMode.SCRUMMING` for this section. `make_bot_config` validates
  the mode against the field manifests and refuses a mode-foreign field before
  the bot exists.
- **`visibility`** — default `orderbook`. The bot reacts to orderbook events.
  The `internal` setting polls instead, and the legacy manual pairs it with
  settings the deprecated list now drops.
- **`aggressive_trading`** — default `False`. Permits more than one fire per
  confirmed signal, up to the cartridge ceiling.
- **`base_currency`** and **`target_asset`** — required. The currency the bot
  spends and the asset it accumulates. The Extractor reverses the meaning of
  both, which is the defect the configuration-factory arc closed; see
  [14-development-chronicle.md](14-development-chronicle.md).

### Strategy settings

- **`target_balance`** — default 200.0 USD. The dollar value the bot holds in
  the asset. A fall in price buys more units for the same dollars; a rise sells
  the excess back toward the target. Report a return against this number, not
  against cumulative buy value.
- **`scrumming_interval_pct`** — default 1.0 percent. The smallest price move
  between two fires. The largest single knob on trade frequency.
- **`max_target_growth_pct`** — default 1.0 percent per cycle, range 1 to 100.
  Caps how far one fold may grow the target.
- **`bb_tolerance_pct`** — default 1.0 percent, range 0.25 to 5. How close to a
  band counts as a touch.
- **`bb_landing_strip_candles`** — default 3. Consecutive tight Heikin-Ashi
  candles before the landing strip arms.
- **`scrum_detect_pct`** — default 75. Distance from the band midline, in
  percent of band width, that arms detect. `_bb_detect_thresholds()` in
  `src/trading/scrumming/circuit_breakers.py:243` turns 75 into the band pair
  0.125 and 0.875. The wizard exposes the range 10 to 90. A missing or
  unreadable value falls back to 75; a deliberate 0 collapses both thresholds
  onto the midline.
- **`scrum_fire_pct`** — default 0.5 percent. Distance from the band that fires
  once detect has armed.
- **`bb_midline_gate`** — default `True`. Keeps a scrum on its own side of the
  midline. `MidlineGate` in `src/trading/gate_chain.py` enforces it.
- **`scrum_read_rate_min`** — default 5 minutes. Poll rate while searching.
- **`band_travel_pct`** — default 70. A secondary harvest trigger measured as a
  fraction of band width, for a move that walks the band without a clean
  reversal.
- **`bb_bullseye_check`** — default `True`. Lets a direct band touch fire
  without the detect step.
- **`scrum_require_ta_bullish`** — default `True`. `TADirectionGate` refuses a
  scrum against a bearish panel.
- **`scrum_hold_in_uptrend`** — default `True`. `TrendHoldGate` blocks a sell
  while a trend still extends.
- **`scrum_defer_to_htf`** — default `True`. `HTFDeferGate` waits when the
  slower timeframe disagrees.
- **`ta_timeframe`** — default `1h`. The timeframe the indicators read.

### Profit folding and routing

- **`profit_folding_active`** — default `True`. The master switch. Off sends
  every realised profit to the operator's spendable balance.
- **`profit_route`** — default `fold_to_target`. Also accepts `spendable`,
  `split` and `cross_bot`.
- **`profit_route_bot_id`** — default empty. Names the receiving bot for
  `cross_bot`.
- **`scrum_fold_pct`** — default 100 percent. How much of a scrum's proceeds
  queue for the fold.
- **`fold_require_ta_bearish`** — default `True`. `TADirectionGate` on the buy
  side.
- **`fold_hold_in_downtrend`** — default `True`. The mirror of
  `scrum_hold_in_uptrend`.
- **`fold_defer_to_htf`** — default `True`. `HTFDeferGate` on the buy side.

`fold_mode`, `fold_target`, `fold_target_count` and `profit_fold_pct` appear in
the legacy section with defaults. All four are in the deprecated list above and
never reach the bot.

### Hedge reserve

- **`hedge_rebalance_active`** — default `True`. A separate dollar reserve the
  bot may draw on when its primary capital is committed.
- **`hedge_balance`** — default 200.0 USD.

### Circuit breakers and cartridge

These bound the damage from one event. They do not stop a long decline from
accumulating a loss, and the legacy section says so plainly.

- **`circuit_breaker_soft_pct`** — default 25.0 percent. A soft trip cools the
  bot down and re-opens without the operator.
- **`circuit_breaker_hard_pct`** — default 35.0 percent. A hard trip halts the
  bot until the operator looks.
- **`circuit_breaker_cooldown_candles`** — default 3.
- **`max_cartridge_size_pct`** — default 10.0 percent of `target_balance`. The
  largest single trade.
- **`max_cartridge_smart`** — default `False`. Lets the bot size a cartridge by
  signal strength.
- **`max_cartridge_smart_ceiling_pct`** — default 30.0 percent. The ceiling for
  that sizing, three times the fixed cap.

`CircuitBreakerGate` in `src/trading/gate_chain.py` carries the trip into both
chains.

### Position ceiling

- **`position_ceiling_enabled`** — default `False`.
- **`position_ceiling_multiple`** — default 5.0, range 1.0 to 10.0.

`SmartCeilingGate` in `src/trading/gate_chain.py` refuses a buy above the
ceiling. The legacy guidance is worth repeating: for an operator who does not
watch the bot through a long drawdown, turning the ceiling on with a multiple
between 3.0 and 5.0 is the structural protection against an unintended large
position.

### Detonation

**The legacy prose has this backwards on two of its three passages.** Two
passages describe detonation as an exit on a bearish higher-timeframe signal.
`ScrummingBot._check_detonation_trigger` at `src/trading/scrumming_bot.py:4265`
requires `SignalDirection.BULLISH` at or above the confidence floor. The word
`BEARISH` does not appear in the method. The legacy risk-control table on page 7
gets it right, so the legacy manual disagrees with itself and the majority
reading is the wrong one.

- **`detonation_enabled`** — default `False`.
- **`detonation_timeframe`** — default `1d`.
- **`detonation_confidence_min`** — default 0.75. The floor
  `summary.consensus_confidence` must reach. The trigger fires on the rising
  edge, so a reading that stays high does not fire twice.

### Entry-price limits and fees

- **`max_entry_price`** — default `None`. A hard ceiling on a buy price.
- **`min_entry_price`** — default `None`. A hard floor on a sell price.
- **`trading_fee_pct`** — default 0.6 percent. The fee the decision maths
  assumes. Check it against the venue's current rate card. Under-stating the fee
  makes every decision look better than it is.
- **`wire_inflow_stack_pct`** — default 1.0 percent. How much of a wire inflow
  the bot stacks onto an open position.

### Grid legacy fields

`investment_amount`, `increment_style` and `spacing_style` remain on
`BotConfig` for older persisted states. `position_count` and
`position_distance_pct` are in the deprecated list. Scrumming mode reads none of
them.

### Three pieces of operator guidance

- **Target Balance is the variable and the strategy is the constant.** The
  legacy live run held every other Scrumming setting identical across 25
  positions and moved only `target_balance`, from $30 to $200. That isolates
  what the asset did from what tuning did.
- **The gates are not optional.** `scrum_require_ta_bullish`,
  `scrum_hold_in_uptrend`, `scrum_defer_to_htf`, `fold_require_ta_bearish`,
  `fold_hold_in_downtrend` and `fold_defer_to_htf` all default on. Each one
  turned off adds a failure mode.
- **The position ceiling is opt-in and worth opting in.**

## Extractor Bot

The Extractor holds one pool of base currency and fires fixed-dollar rounds at
several pairs from a watchlist, instead of holding one position against one
target. All fifteen extractor-only defaults below were read at runtime and every
one matches the legacy section.

[08-tabs/promotion-pipeline.md](08-tabs/promotion-pipeline.md) and
[06-trading-tab.md](06-trading-tab.md) carry the operator's own assessment of
this bot's state. Read that assessment first; the settings below describe a bot
the operator marks as partially built.

### Direction

- **`extractor_direction`** — default `normal`. Rounds buy into dips and exit on
  a bounce. The `inverted` setting sells into spikes against a standing alt
  position and buys back on a dip.
- **`inverted_extractor_standing_alt_units`** — default 0.0. Required above zero
  for `inverted`. `make_bot_config` refuses the pair of `inverted` and zero
  units.

### Capital sizing

- **`extractor_chunk_size_usd`** — default 100.0 USD. The budget for one
  opportunity.
- **`extractor_artillery_size_usd`** — default 5.0 USD. One round. The two
  defaults together give up to twenty rounds per chunk.
- **`extractor_pool_reserve_pct`** — default 50.0 percent. The share of the pool
  the bot never deploys.
- **`extractor_exit_pct`** — default 100.0 percent. A triggered exit closes the
  whole position.

### Watchlist

- **`extractor_alt_targets`** — required, and empty by default. A list of
  symbols. An empty list disables the bot, and a perfect signal on a symbol
  outside the list is ignored.
- **`extractor_scan_top_n`** — default 8. How many ranked candidates the bot
  considers each cycle.
- **`extractor_scan_refresh_candles`** — default 60. Candles between two
  rankings. At a 1h timeframe that is about two and a half days, which is
  deliberately slow.

### Drawdown and correction discipline

- **`extractor_drawdown_threshold_pct`** — default 3.0 percent. How far a chunk
  must fall before a correction round may fire.
- **`extractor_correction_skip_candles`** — default 4. The minimum wait between
  two corrections on one chunk.
- **`extractor_max_cost_basis_multiple`** — default 2.0. The hard ceiling on how
  far corrections may grow a chunk's cost basis.
- **`extractor_max_compounding_tier`** — default 3. The deepest correction tier
  on any one chunk.

These three together bound how far into a falling position the bot may go.
Raising any of them raises the capital at risk per chunk.

### Signal threshold and hedge budget

- **`extractor_trend_strength_threshold`** — default 0.65, on a 0.0 to 1.0
  scale.
- **`extractor_hedge_budget_usd`** — default 0.0, which disables hedging. A
  positive value carves that amount out of the pool, and an ordinary round
  cannot draw on it.

### Spike protection, and where it actually lives

The legacy section describes dollar-anchored sizing protected by a ten percent
spike guard with a median-of-three fallback. That guard is real and it is **not
a configuration field**. `ExtractorBot._rate_spike_threshold_pct` at
`src/trading/extractor_bot.py:198` holds 10.0 and
`ExtractorBot._rate_spike_window` on the next line holds 3, both hard-coded.
`ExtractorBot.update_base_usd_rate` takes the median of the recent rates when an
incoming rate diverges by more than ten percent, and refuses to append the
suspect sample, so two spikes in a row fall back the same way instead of walking
the window toward the spike. An operator cannot change either number from the
wizard.

### What the inverted mode does not model

The legacy section leads with its limits, which is the right order and carries
forward unchanged.

- Slippage on a sell-side round is not measured against the live fill
  behaviour.
- A standing alt position managed from outside the bot can drift away from the
  bot's own reservation arithmetic. `src/trading/capital_reservation.py` tracks
  the claim; it does not poll the venue for ground truth.
- An asset that goes to zero leaves the bot with nothing to fire and no
  automatic move to another asset.

## Risk controls, as one table

Source: LEGACY Part 4 page 7. Each row below names the control and the symbol
that carries it today. Rows whose mechanism has no source here are marked.

| Control | What it does | Where it runs |
| ------- | ------------ | ------------- |
| Initial-purchase-price floor | Every rebought unit costs at or under the lot's original price | `src/trading/scrumming/tick_phases.py`, `_fold_eligible_tranches` |
| Hedge reserve isolation | Hedge capital cannot flow to the main target | `hedge_rebalance_active`, `hedge_balance` |
| Entry-price conservation | Target growth capped at the held units' entry value | `apply_profit_fold` in `src/trading/profit_fold.py`; no module imports it |
| Band-travel suppression | Mean-reversion sells held back during a trend move | `band_travel_pct`, `TrendHoldGate` |
| Higher-timeframe bias gate | Counter-trend entries suppressed | `HTFDeferGate` |
| Position-aware weighting | Band position gates the signal | `BBProximityGate` reading `bb_pos` |
| Fail-closed buy safety | Refuse a buy when the venue balance reads ambiguous | `src/trading/buy_safety.py` |
| Position ceiling | Cap accumulation at a multiple of the anchor | `SmartCeilingGate` |
| Detonation | Sell above the anchor on a strong **bullish** slower-timeframe reading | `ScrummingBot._check_detonation_trigger` |
| ADX trend suppression | Block a mean-reversion sell in a strong trend | `ADXTrendSuppressionGate`, at or above 30.0 |
| Efficiency-ratio regime gate | Block a sell at both ends of the efficiency range | `EfficiencyRatioRegimeGate`, 0.05 and 0.70 |
| Z-score extremity | Block a scrum under −2 and a fold over +2 | `ZScoreExtremityGate` |
| Mode-shape validation | Refuse a mode-foreign field at construction | `make_bot_config` |

Four rows of the legacy table name mechanisms with no source here: the volume
guard's fill-price verification, the charge-up threshold, satiety decay and
Spectre isolation. The runtime parity harness is a fifth. Each is recorded in
the claim audit, with the identifier probed and both controls.

The efficiency-ratio row is the one the legacy manual gets wrong twice and in
opposite directions. Page 7 says the gate suppresses above 0.7; page 27 says it
suppresses below 0.25. `EfficiencyRatioRegimeGate` at
`src/trading/gate_chain.py:452` takes `upper_threshold` of 0.70 and
`lower_threshold` of **0.05**, and blocks at both ends. A reading at or below
zero is the not-populated sentinel and passes.
