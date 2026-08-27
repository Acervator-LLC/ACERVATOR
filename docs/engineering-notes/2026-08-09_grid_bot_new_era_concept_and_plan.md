# New-era Grid Bot — concept, evidence and development plan

**Scope.** Read-only audit of `acervator_session25_CLOSE_hop5_v3_15_27` on branch `cascade/c43-release-gate-integrity`. Every codebase claim carries `file:line`, read from source. Every external claim carries a URL. Unverified claims say HYPOTHESIS.

---

## 1. Verdict up front

**DO NOT BUILD a new grid bot class. BUILD-MODIFIED: extend the existing Stack Mode into a fee-clamped, two-sided ladder inside `ScrummingBot`.**

The single strongest piece of evidence is the P0b stacked-order guard. `_execute_sell` fetches `get_open_orders(symbol)` and returns `None` if **any** open SELL exists on that symbol (`src/trading/scrumming_bot.py:11306-11332`). `_execute_buy` mirrors it for BUY (`src/trading/scrumming_bot.py:11688-11717`). Both refuse on a fetch exception ("Cannot verify absence of stacked orders. Refusing."). The filter is a bare truthiness test on the list — no count threshold, no rung exemption. A grid's defining property is N resting orders per side. On the autonomous path this platform permits exactly one. The guard exists because "Stacked sells can oversell below zero if both fills land" (`src/trading/scrumming_bot.py:11302-11304`), which is precisely what a grid does on purpose.

### Fee break-even arithmetic

A completed round trip pays fee twice. Buy one unit at `P_low` and pay `f_buy` on notional. Sell at `P_high` and pay `f_sell` on notional.

```
cost      = P_low  * (1 + f_buy)
proceeds  = P_high * (1 - f_sell)
profit    <=>  P_high / P_low  >  (1 + f_buy) / (1 - f_sell)

BREAK-EVEN RATIO   r* = (1 + f_buy) / (1 - f_sell)
MINIMUM STEP       s* = r* - 1
BAND for N steps   r*^N
```

| f_buy / f_sell | r* | s* (min step) | Band for 3 | for 5 | for 10 | for 20 |
|---|---|---|---|---|---|---|
| 0.10% / 0.10% | 1.0020020 | 0.2002% | 0.60% | 1.00% | 2.02% | 4.09% |
| 0.25% / 0.40% | 1.0065261 | 0.6526% | 1.97% | 3.31% | 6.73% | 13.9% |
| 0.40% / 0.40% | 1.0080321 | 0.8032% | 2.43% | 4.08% | 8.33% | 17.4% |
| **0.60% / 0.60%** — the repo's own assumption (`src/trading/bot_container.py:345`) | **1.0120724** | **1.2072%** | **3.67%** | **6.18%** | **12.75%** | **27.13%** |
| 0.60% / 1.20% — the sim backend's own market stub (`src/exchange/tablet_backend.py:163-164`) | 1.0182186 | 1.8219% | 5.57% | 9.45% | 19.79% | 43.49% |

`trading_fee_pct: float = 0.6` at `src/trading/bot_container.py:345` is the platform's own worst-case assumption, recorded from the operator directive at `src/trading/bot_container.py:333-344`. It is not a fetched Coinbase tier. The Coinbase help pages returned HTTP 403 and no tier table is reproduced in this report.

**The arithmetic does not close for a dense grid.** Twenty profitable rungs need a 27.13% band at the platform's own fee assumption, and 43.49% at the sim backend's maker/taker pair. At that width the outer rungs are a limit-order wish list, not a grid. The arithmetic closes cleanly at 3 to 6 rungs. Stack Mode already ships 3 (`src/trading/bot_container.py:292`, `stack_tranche_count_target: int = 3`) and it is OFF on every bot (`src/trading/bot_container.py:281`, `stack_mode: bool = False`).

### Three further reasons the "new grid bot class" framing fails

**The operator already deleted one, twice.** `grid_bot.py` was removed at v3.16.0 per directive 2026-04-28, quoted in source: "Delete the grid bot code. We have grown beyond it and we do not need souvenirs" (`src/trading/bot_container.py:56-58`). Follow-up 2026-05-23: "Grid code and dangling mentions can be cleaned out" (`src/trading/bot_container.py:64-65`). `BotMode.GRID` was removed at v3.20.4.

**A unit-denominated grid is Scrum/Fold with more levels.** Only constant-quote-value rung sizing accumulates units; constant base quantity returns exactly what was sold. Constant quote value means: when price rises, holdings value exceeds target, sell the excess; when it falls, spend the banked quote to buy back. That is the shipped delta rule verbatim (`src/trading/scrumming_bot.py:14-17`). KuCoin publishes the same mechanic as Infinity Grid. The only real difference is resting orders instead of market orders — and resting orders are what the P0b guard forbids.

**The platform's accumulation metric is fee-blind.** `extra_asset` is computed from gross notional on both legs: `scrum_usd = scrum_asset * sell_fill` (`src/trading/scrumming_bot.py:7806`), `buy_asset = buy_cost / buy_fill` (`:8857`), `asset_at_scrum = sum(t["usd"] / t["ref"])` (`:8858`), `extra_asset = buy_asset - asset_at_scrum` (`:8859`). No fee term appears anywhere in that region. `trading_fee_pct` is read at `:5960, :6919, :7504, :7662, :8235, :8517, :10904, :11186, :11608` and at none of the accounting sites. Building a new bot on this metric would report accumulation while units fell. Section 5, attack A4, gives the exact identity.

### Recommendation

Build a **fee-correct two-sided Stack**: the existing sell ladder plus a mirrored buy ladder, behind a real cancel path, a per-rung order-id record, and a fee-inclusive unit metric. That is a bounded fix to shipped code. It does not reopen a design the operator has closed twice, and it does not require a new bot class, a new tick loop, or a new persistence schema.

---

## 2. What a grid bot is, and how grid bots die

### Mechanics

A grid places a ladder of buy and sell orders across a band and profits from oscillation. Two spacing laws exist. Every venue names them the same way.

**Arithmetic** — equal price difference per level. `d = (Upper - Lower) / Number of Grids` ([Binance parameters](https://www.binance.com/en/support/faq/binance-spot-grid-trading-parameters-688ff6ff08734848915de76a07b953dd)). Bitget: "Each grid has an equal price difference (e.g., 1, 2, 3, 4)" ([Bitget glossary](https://www.bitget.com/support/articles/12560603791272)).

**Geometric** — equal price ratio per level. `r = (Upper / Lower) ^ (1 / Number of Grids)` (same Binance page). Bitget: "Each grid has an equal price ratio (e.g., 1, 2, 4, 8)."

Binance publishes profit-per-grid, with `c` the trading fee (0.1% in their example):

```
arithmetic maximum = (1 - c) * d / Lower - 2c
arithmetic minimum = (Upper * (1 - c)) / (Upper - d) - 1 - c
geometric          = (1 - c) * r - 1 - c
```

Their worked example (U=450, L=400, 5 grids, c=0.001, d=10) publishes 2.29% / 2.07% / 2.18%. All three reproduce by hand. Note the fetched text renders the minimum-profit denominator as `Lower - d`; substituted, that gives 15.17%, not the page's own 2.07%. `Upper - d` gives 449.55/440 − 1.001 = 2.07% and matches. HYPOTHESIS: the rendered form is an extraction artefact. Do not ship it as written.

An arithmetic grid's percentage step **shrinks** as price rises, so its worst step is at the top of the band. A geometric grid holds one percentage step everywhere. This is my inference from the two formulas above; Binance does not state the contrast in prose. Consequence at 0.60%/0.60% over a 100–125 band: geometric carries `floor(ln(1.25)/ln(1.0120724)) = 18` profitable rungs; arithmetic carries 16, because the top pair binds. Check: n=16 gives a top ratio of 125/123.4375 = 1.012658 (passes r*); n=17 gives 125/123.5294 = 1.011905 (fails).

### How grid bots die

**1. The static grid has zero expectation.** Chen, Chen and Jang model a geometric grid with n grids and n+1 levels around a centre P, levels at `P*(1+k)^m`, and assume "the probability of the price rising or falling by k is equal". Under that model the expected return of the traditional grid is essentially zero before costs; fees then make it negative. Their fix is a reset: "The strategy resets the grid whenever the price breaks above the upper limit or falls below the lower limit, with the current price becoming the new center." On an upward break capital is recovered and reinvested; on a downward break the strategy holds the asset and uses accumulated profit as the new principal. ([arXiv 2506.11921](https://arxiv.org/abs/2506.11921), submitted 13 June 2025; backtest on Binance 1-minute BTC and ETH, January 2021 to July 2024, fee 0.0008.)

The implication is structural. **Re-centring is not a refinement. It is the whole edge.** A grid that never re-anchors is a bet on a range.

**2. Breakout strands the ladder.** Binance's answer is Trailing Up, quantised to one grid gap. Worked example on their page: range 25,000–45,000 with 5 grids gives a 4,000 step, so the trigger is 45,000 + 4,000 = 49,000. The bot cancels the lowest buy and places a new buy at the old upper limit. The first shift yields 29,000–49,000; the second yields 33,000–53,000. Trailing halts on minimum notional, maximum pair price, or minimum order quantity. The page restricts one thing after start: "you cannot change the Stop Loss price once it has been set." ([Binance Trailing Up](https://www.binance.com/en/support/faq/how-to-use-the-trailing-up-function-in-spot-grid-trading-3d987afd7906495cb4d997eccb8515bf))

**3. Fee bleed at sub-break-even spacing.** This is the death that looks healthy: fill counts rise while units fall. Bitget ships a venue-side refusal — "Trading bots ensure that orders will only be opened if the profits on the grid are greater than the transaction fees" — and defines profit net: "Grid profit = arbitrage profit - transaction fees" ([Bitget FAQ](https://www.bitget.com/support/articles/12560603791273)). It also warns that "adding too many grids will shrink both the price difference and order amount per grid". Separately, the glossary page carries one sentence on a matching mechanism: "When you set a high number of grids within a narrow price range, the system activates interval matching to optimize your profits" ([Bitget glossary](https://www.bitget.com/support/articles/12560603791272)). The rule behind it is not published.

**4. Density fights the band.** The two constraints — minimum profitable step and available band — are multiplicative, and Section 1's table is the result. Hummingbot solves the same problem in code with two independent caps: `max_levels_by_step = int(grid_range / min_step_size)` and a notional cap from `min_notional_with_margin = min_notional * Decimal("1.05")`, then `n_levels = min(max_possible_levels, max_levels_by_step)` ([grid_executor.py](https://raw.githubusercontent.com/hummingbot/hummingbot/master/hummingbot/strategy_v2/executors/grid_executor/grid_executor.py)).

**5. Thin books.** A dense ladder on a low-volume alt becomes the order book. Binance permits up to 170 grids per bot and up to 50 bots (same Binance overview family); OKX raised its ceiling from "only up to 300 grids were supported" to "you can set up to 1,000 grids" ([OKX](https://www.okx.com/en-us/help/how-do-i-manually-set-up-spot-grid-trading-bots)). No venue in this survey exposes a market-participation cap.

**6. Silence.** No published grid bot ships a runtime record that can falsify its own adaptation. Hummingbot logs orders. Binance logs fills. The literature reports IRR. None of them answers "did the spacing rule run on this candle, and did it produce the value it promised". That is the gap Acervator's emitter network can close, and it is the only defensible claim to novelty in this whole design.

---

## 3. What Acervator already provides

### REUSABLE AS-IS — pure or stateless, no `ScrummingBot` required

| Component | Evidence |
|---|---|
| Gate framework: `Gate` ABC, `GateChain`, `GateContext` (51 fields), `GateResult`, `ChainResult` | `src/trading/gate_chain.py:202, :728, :54, :173, :183` |
| 17 concrete `Gate` subclasses | `src/trading/gate_chain.py:223, 234, 248, 259, 282, 294, 317, 329, 355, 369, 387, 422, 444, 467, 490, 567, 643` |
| Chain evaluation — two-pass, non-short-circuiting; `should_fire` is the empty-blocked-list test | `src/trading/gate_chain.py:752-802`, verdict at `:798` |
| Working proof of reuse: drives both production chains with no `ScrummingBot` in the process | `tools/harness/decision_diff.py:15-26, 137-183, 232-263` |
| `TASignalProvider.evaluate(symbol)` behind a one-method exchange shim; returns `None` on failure, never raises | `src/trading/ta_signal_provider.py:179-200, 212-313` |
| 12 voting indicators; `VotingEngine.compute_all`; `DEFAULT_WEIGHTS` | `src/trading/ta_engine.py:2524-2557, 2559, 2467-2489` |
| Pure helpers: `candles_from_raw`, `detect_bb_proximity`, `detect_landing_strip_v2`, `analyze` | `src/trading/ta_engine.py:129, 2843, 2954, 2757` |
| `stack_math.split_scrum_into_tranches` — pure, no `src.trading` imports by design | `src/trading/stack_math.py:146-224`, purity claim at `:22-23` |
| `ta_invariants.check` — 12 indicators, formula-derived bounds, fail-soft | `src/trading/ta_invariants.py:139-231, 238-277` |
| `gate_coverage`: `build_gate_index`, `classify_trades`, `format_coverage_lines`, `compute_validation_window`, `format_window_lines` | `src/trading/gate_coverage.py:206, 305, 379, 486, 541` |
| `buy_safety.verify_buy_safe_or_refuse` — parameterised on `expected_units`, so a new state shape works without inheritance | `src/trading/buy_safety.py:78-84` |
| `VolumeGuard` — LIVE and wired | `main.py:748-749` → `src/trading/bot_container.py:1812` → `guarded_place_order` at `:996` |
| `SignalSink.emit` / frozen `Signal` record | `src/core/signal_contract.py:319-364, 189-240` |
| `emit_contracts` (`nested_key` at `:71`), `feature_telemetry` | `src/core/emit_contracts.py:110-138, 208-220`; `src/core/feature_telemetry.py:34-42` |
| `topology_stress` — measures base units gained, reports dispersion | `src/trading/topology_stress.py:70-114, 81-89` |
| `trade_grader.grade_trade`, `_score_execution` (slippage in bps) | `src/trading/trade_grader.py:244, 114-133` |
| `ATRIndicator` — built, correct-looking, **zero consumers** | `src/trading/ta_engine.py:1987`; repo-wide grep over `src`, `tools`, `tests`, `main.py` returns only the class definition |
| `FVGIndicator` — same posture | `src/trading/ta_engine.py:2163`; absent from `_create_indicators` at `:2524-2557` |

### REUSABLE WITH WORK

**Regime gates need the sentinel inverted.** `ADXTrendSuppressionGate` blocks at `adx >= 30.0` (`src/trading/gate_chain.py:490, :546, :553-560`). `EfficiencyRatioRegimeGate` blocks above ER 0.70 and below ER 0.05 (`:567, :606-607, :618-634`). Both **pass** on their zero sentinel (`:553-554`, `:618-619`). That additive-landing policy is correct for retrofitting a gate into a running strategy. It is fail-open for a new money path.

**`stack_math` has no geometric law.** `_delta_multiplier` returns a multiplier on the **step**, not on the price: linear `1`, quadratic `i`, exponential `2^(i-1)` (`src/trading/stack_math.py:64-81`). The generator accumulates a percent **offset** against a fixed base: `cum_pct_offset += _delta_multiplier(mode, i) * split_distance_pct` then `price = first_price * (1.0 + cum_pct_offset / 100.0)` (`:207-209`). The config comment says the same thing — "Δp between tranches i and i+1, in units of `split_distance`" (`src/trading/bot_container.py:294-300`). With exponential and SD=1%, cumulative offsets run 0, 1, 3, 7, 15, 31 and the step-to-step **ratios grow**: 1.0100, 1.0198, 1.0388, 1.0748. A constant-ratio ladder needs `price_i = first_price * r**i`. No branch produces it. A geometric ladder requires a **new price law**, not a mode selection.

**`_apply_min_order_size` breaks its own falsifier on one branch.** When `total_size // min_order_size` evaluates to 0, it returns a single `Tranche` with `size=total_size` (`src/trading/stack_math.py:132-137`) — by construction below `min_order_size`, which the module's own falsification clause forbids (`:30-35`). The comment defers refusal to the caller.

**`CapitalReservationRegistry` is live but leaks.** `reserve` `:265`, `effective_available` `:464`, `release` `:345`, `heartbeat` `:556`. `prune_expired` (`:567`) has zero callers in `src`, `main.py`, `tools`, `tests`, so the documented backstop cited at `src/trading/scrumming_bot.py:1340-1341` never runs. `HEARTBEAT_TTL = 120.0` (`:88`). Measured orphan state: 16,551 reservations, 28 belonging to live bots, heartbeats up to 71.8 days old, 6.5 MB file (`tools/purge_orphan_reservations.py:8-13`).

**`WalletReservations` is live at exactly one call site.** `available` `:52-58`, `reserve` `:60-69` (no refusal branch), `release` `:71-84`. `_held` is one float per key with no owner (`:46`). Only consumer is the manual/cartridge FOLD path (`src/trading/scrumming_bot.py:10142, :10195, :10205`), correctly `try/finally`-wrapped. `_execute_buy` places its order at `:11984` with no cash hold.

**`MarketInspector` emits nothing.** Results sit on `self._last_signals` / `self._last_pairs` (`src/trading/market_inspector.py:113-114, 338-340`). No bus emit, no `Signal`. Its WATCHLIST tier (score 0.15, `:232-241`) is exactly the "tightening, no extreme" state a grid wants, and is the scanner's discard pile.

**`TimeframeCoordinator.get_higher_tf_bias`** (`src/trading/phantom_balance.py:482-559`), live at `src/trading/scrumming_bot.py:7423`. Weights by `max(1, rank) * consensus_confidence`; NEUTRAL contributes to neither side; returns `None` when no higher-TF phantom has a summary, which the caller must read as "no override".

### ENTANGLED WITH `ScrummingBot`

| Behaviour | Where it lives | Note |
|---|---|---|
| SEARCH/TRACK/FIRE target FSM | `src/trading/scrumming_bot.py:7158-7230` | Reads mutable bot attributes |
| OTD hysteresis (armed-only; uses `interval + fee`) | `src/trading/scrumming_bot.py:6916-6939`; gate at `src/trading/gate_chain.py:387-420` | Conditional, not always-on |
| Circuit breaker side latch | `src/trading/scrumming_bot.py:7415, :8175` | |
| Smart position ceiling | `src/trading/scrumming_bot.py:8140-8149` | |
| Fold eligibility, cap, taper, post-fill accounting | `src/trading/scrumming_bot.py:8624-8909` | Inline inside `tick()`, not functions |
| `_apply_fold_target_growth` | `src/trading/scrumming_bot.py:1524-1670` | Reads config, anchor, cycle counter, standing pool, target, stats, bus |
| `_dist_accumulator` | declared `:496`, summed `:9177`, persisted `:3791`, rehydrated `:4060-4061`, **drained to 0.0** `:9442` | A pending-SELL buffer, not a lifetime total |

### DEAD — do not build on these

- `capital_registry.py` (574L). `set_capital_registry` (`src/trading/bot_container.py:2146`) has zero callers; `_capital_registry = None` at `:1628`; the comment at `:1621` claims `main.py` wires it and nothing does.
- `capital_arbiter_bridge.py` (163L) and `opportunity_arbiter.py` (294L) — no importer.
- `profit_fold.apply_profit_fold` (`src/trading/profit_fold.py:45`) — definition plus eight self-test calls, no `src/` caller. The live growth formula is `_apply_fold_target_growth` and it differs in four ways.
- `stats.accumulated_fold` (`src/trading/bot_container.py:794`) — read by the fleet panel under the label "Mature" (`src/gui/simulator_tab/fleet/fleet_replay_panel.py:1676, :1701`), assigned nowhere in `src/`. Always 0.0.
- No position VWAP exists in the trading layer. The only VWAP under `src/` is a rolling 30-candle **market** VWAP in a chart widget, labelled "position VWAP" (`src/gui/simulator_tab/fleet/sim_visuals.py:811-820, :906-912`).

---

## 4. The fusion

Each subsection applies to the recommended two-sided Stack, not to a new bot class.

### 4.1 Two-sided regime arming, with the sentinel inverted

**Feature.** `ADXTrendSuppressionGate` (`src/trading/gate_chain.py:490-560`) and `EfficiencyRatioRegimeGate` (`:567-634`), assembled with `Gate` / `GateChain` (`:202-212, :728-810`).

**Grid problem.** A trend kills a ladder: the mean outruns reversion, every buy fills, no sell does. A dead market bleeds it: fees are paid and there is no amplitude to harvest. Binance and OKX offer only a manual stop-loss price against either.

**Mechanism.** Build a third chain, beside the SCRUM and FOLD chains, that arms and disarms the whole ladder. Both classes are stateless — `evaluate(ctx)` reads only `GateContext` fields. `EfficiencyRatioRegimeGate` is already the exact two-sided suppressor a ladder wants, and its own docstring states the reason (`:584-588`). Subclass both to return `passed=False` on the zero sentinel, matching the `buy_safety` posture.

**Emitter.** `stack.arm.decision` — actual = tuple of blocked gate names, expected = `()`, ok = `should_fire`. Plus `stack.arm.input` — actual = `(adx, efficiency_ratio)`, expected = "both populated", ok = both > 0.0. The second emitter catches an unwired feed and must fire on the armed path too.

**Risk if wrong.** `ScrummingBot` populates these two fields at `src/trading/scrumming_bot.py:7684-7685` with a 0.0 default. A ladder that copies the gate but not the feed is permanently armed behind a filter that reports green forever. That is the ADX-at-761 failure class: a zero that is a claim about the instrument, not about the world (`src/trading/ta_invariants.py:1-25`).

### 4.2 The blocked-list reason vector

**Feature.** `GateChain.evaluate` — two passes, no short-circuit (`src/trading/gate_chain.py:752-802`); `should_fire = (not final_blocked)` at `:798`.

**Grid problem.** Every published grid post-mortem is a P&L curve with no reason vector. "The grid ran and earned nothing" and "the grid never armed" are indistinguishable.

**Mechanism.** Pass 1 collects `(name, message)` for every failure without short-circuiting. Pass 2 lets override gates move named targets from blocked to passed. The verdict is the inverse of the blocked list by construction, so the diagnostic and the trigger cannot drift inside the chain. An override gate that does not fire appears in neither list (`:770-773`) — correct semantics for an advisory re-centre trigger.

**Emitter.** `stack.arm.blockers` — actual = the frozen blocked-name tuple, expected = `()` on the armed path. **One list. Not two.**

**Risk if wrong.** `tick()` already keeps a second, hand-written blocker list (`src/trading/scrumming_bot.py:7469-7518, :8204-8245`), and that advisory list is what reaches `gate.log` via `_last_gate_state` (`:7515-7516, :8244-8245`; reader at `:4934-4991`). The advisory SCRUM list has 10 conditions and omits `adx_trend_suppression`, `efficiency_ratio_regime` and `zscore_extremity`. Repeat that pattern and the ladder's own log reports armed on ticks where its chain refused.

### 4.3 Fee-clamped step floor

**Feature.** The Minimum Opposing Trade Distance rule, `eff_pct = scrumming_interval_pct + trading_fee_pct` (`src/trading/gate_chain.py:405`), restated for Stack at `src/trading/scrumming_bot.py:10901-10905`.

**Grid problem.** Sub-break-even spacing is the most common grid death, and the fill count looks healthy while it happens.

**Mechanism.** Derive the floor, do not assume it. Pass `min_opposing_pct = 100 * (r* - 1)` into `split_scrum_into_tranches`, so the first rung is fee-safe by construction at `src/trading/stack_math.py:200`. Derive the rung **count** from the floor and the band, rather than asking the operator for a number. Read `f_buy` and `f_sell` at runtime from the venue: [Coinbase CDP Get Transaction Summary](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/fees/get-transaction-summary) returns `pricing_tier`, `maker_fee_rate`, `taker_fee_rate`, `aop_from`, `aop_to`. The operator's own comment asked for exactly this (`src/trading/bot_container.py:335-338`).

**Emitter.** `stack.step.floor` — actual = the placed adjacent-rung ratio, expected = `r*`, ok = `actual >= expected`. **Positive control, mandatory before any zero is trusted:** feed the generator a deliberately sub-break-even step (0.30% at 0.6%/0.6% fees) and assert the refusal fires.

**Risk if wrong.** The existing OTD rule adds **one** fee, not two (`src/trading/gate_chain.py:405`). At 0.60% both sides the two-sided floor is 1.2072%, not 0.60%. The larger risk is the temptation to widen the clamp so more rungs fit. That is exactly how `ADXTrendSuppressionGate.adx_threshold` reached 500.0 around a broken indicator before the smoother was fixed and the threshold reset to 30.0 (`src/trading/gate_chain.py:508-528`). Fix the ladder, never the clamp.

### 4.4 Ladder generation

**Feature.** `split_scrum_into_tranches` (`src/trading/stack_math.py:146-224`), `_apply_merge_rule` (`:84-115`), monotonicity assert (`:218-222`).

**Grid problem.** Level generation is the fiddly part every grid re-implements badly: price collisions, exchange minimum order size, monotonicity.

**Mechanism.** The ascending ladder already exists as pure math. Keep the merge rule (0.1% collision, combine upwards, `:47, :101-109`) and the monotonicity assert. **Add a fourth spacing mode, `geometric`, that multiplies the price rather than accumulating a step offset** — `price_i = first_price * r**i`. Then mirror the generator descending for the buy side. Do not fork the module.

**Emitter.** `stack.ladder.built` — actual = the `(price, size)` tuple list, expected = the module's own four falsification clauses restated as a predicate (no size below `min_order_size`, no two prices within 0.1%, strictly increasing, sum of sizes ≤ requested), ok = all four hold.

**Risk if wrong.** Two, both verified. First, none of the three existing modes is constant-ratio (Section 3), so a "use exponential for geometric" instruction silently produces a ladder that leaves the band far earlier than the formula promises. Second, `_apply_min_order_size` emits a sub-minimum tranche on the `max_viable_n <= 0` branch (`:132-137`), breaking the module's own falsifier. A ladder must close that branch itself or it emits unfillable rungs.

### 4.5 Wire the dormant ATR as the spacing source

**Feature.** `ATRIndicator` (`src/trading/ta_engine.py:1987-2027`) — Wilder true range at `:2006-2009`, Wilder smoothing at `:2011-2013`, returns `atr`, `atr_pct`, `expanding`, `contracting`, `extreme_high` at `:2021-2027`. Its docstring already names the use case: "Dynamic interval calibration (widen when ATR/price % is high)" (`:1991`).

**Grid problem.** Fixed spacing is wrong in both directions. Too tight in a volatile tape means churn and fee bleed. Too wide in a calm tape means no fills.

**Mechanism.** Set `split_distance_pct = k * atr_pct`, then clamp between an operator floor (never below the Section 4.3 fee floor) and a ceiling. The `expanding` / `contracting` flags give a re-spacing trigger without a second indicator. Start `k` at 1.5 pending a fixture sweep — that is the unreviewed default in [GridMaster Pro MT5](https://raw.githubusercontent.com/sajidmahamud835/grid-master-pro-mt5-ea/main/README.md) (`ATRPeriod = 14`, `ATRMultiplier = 1.5`), not a result. The clamp pattern comes from [WickHunter](https://docs.wickhunter.io/en/articles/11826956-atr-based-grid-bot-full-setup-guide), which exposes "Minimum Step (%)" and "Maximum Step (%)" and gives the example "never closer than 0.4% and never wider than 2%, even if ATR fluctuates" — its ATR-to-step mapping is not published, so the rule cannot be replicated from that source.

**Emitter.** `stack.spacing.computed` — actual = clamped step percent, expected = the clamp band `(floor, ceiling)`, ok = `floor <= actual <= ceiling`. Payload must carry `atr_pct`, `k`, `raw_step_pct`, `clamp_floor`, `clamp_ceiling`, or a pinned step is indistinguishable from a calm market.

**Risk if wrong.** `ATRIndicator` has never run. It returns a plain dict, not a `Signal`, is absent from `_create_indicators` (`:2524-2557`), and therefore has **no `ta_invariants` entry and no runtime bound check**. An unbounded `k * atr_pct` feeding a money path repeats the unchecked-indicator shape exactly. Section 4.6 is not optional here.

### 4.6 Definitional invariants for the ladder

**Feature.** `ta_invariants` — bounds table (`src/trading/ta_invariants.py:139-231`), `check` (`:238-277`), admission rule (`:15-25`).

**Grid problem.** A spacing parameter computed from a broken indicator mis-sizes every rung, and the ladder still looks well-formed.

**Mechanism.** Add one entry for `atr` carrying only formula-derived bounds: `atr >= 0`, `atr_pct >= 0`. Nothing observed, nothing tuned. Add the ladder's own definitional invariants in the same style: `step_pct > 0`; rung prices strictly increasing; sum of rung sizes ≤ requested size; `clamp_floor <= clamped_step <= clamp_ceiling`. The first three are already `stack_math`'s own falsification clause (`src/trading/stack_math.py:30-35`), so the invariant and the ladder agree by construction.

**Emitter.** `stack.ta.raw.atr` — actual = the ATR dict, expected = the rule string returned by `check()`, ok = its verdict. Emit on the satisfied path.

**Risk if wrong.** `ta_invariants` is a recording instrument, not a gate. A violation only flips an emitted record's `ok`; nothing consumes `ok=False` at trade time. Wire the refusal explicitly. Separately, measure every candidate bound before adding it: `0 <= bb_position <= 1` was **rejected** after failing on 148 of 1181 real records, because a band break legitimately exceeds 1 and that break is the signal (`src/trading/ta_invariants.py:27-45`). A ladder that clamps `bb_position` destroys its own breakout information. **And see attack A11: `check()` itself has a counting defect that can return a PASS from a bound that never evaluated.**

### 4.7 Per-rung capital claim across a shared wallet

**Feature.** The two live registries. `CapitalReservationRegistry` for base units (`src/trading/capital_reservation.py:265, :464, :345, :556`). `WalletReservations` for quote USD (`src/trading/wallet_reservations.py:52-58, :60-69, :71-84`).

**Grid problem.** A multi-rung ladder is N simultaneous claims. Acervator runs 35–37 bots against one wallet, and `src/trading/wallet_reservations.py:9-15` records the measurement: all 35 bots report the same `cash_balance_usd` and each reads it with no reservation. No exchange grid bot has fleet-level capital arbitration, because no exchange grid bot shares a wallet with 36 siblings.

**Mechanism.** Two-sided, because the two registries are invisible to each other. SELL side: reserve the ladder's total base units once at arm time; `update()` on re-space; `release()` on disarm. `effective_available(asset, bot_id, total_holdings)` subtracts only **other** bots' claims (`:464-497`), which is correct — a ladder may act freely inside its own claim. BUY side: call `available(key, free_usd)` first, then reserve the buy-ladder notional, with `release` in a `finally` — the shape already proven at `src/trading/scrumming_bot.py:10195-10205`.

**Emitter.** `stack.reserve.ladder` — actual = `effective_available` before placement, expected = the ladder's base-unit sum, ok = `actual >= expected`. And `stack.wallet.headroom` — actual = `available(key, free_usd)`, expected = the buy-ladder notional. Both emit on the **granted** path, not only on refusal.

**Risk if wrong.** Three verified leaks, detailed in attack A10. The one that bites a ladder hardest: `release()` needs a token that lives only in memory (`src/trading/capital_reservation.py:345-362`) while the row is persisted on every mutation (`:217-237`). A ladder that re-spaces often strands a row per crash and shrinks its own headroom permanently.

### 4.8 Market-impact ceiling per rung

**Feature.** `VolumeGuard` — config (`src/trading/volume_guard.py:34-65`), wired `main.py:748-749` → `src/trading/bot_container.py:1812` → `guarded_place_order` at `:996`.

**Grid problem.** A dense ladder on a thin alt becomes the order book. This is the parameter no exchange grid exposes, and it is the one that decides whether the pair is ladderable at all.

**Mechanism.** Route every rung through the same guarded path the live bots use. Caps: `max_single_order_volume_pct = 0.001` of 24h volume (`:39`), `max_hourly_participation_pct = 0.02` (`:42`), `max_book_depth_pct = 0.25` of visible depth (`:45`), `max_slippage_pct = 1.0` (`:48`). Oversized rungs become adaptive chunks with 200–5000 ms delays (`:51-52`). `min_daily_volume_usd = 1000.0` (`:59`) doubles as a pair screen: a pair the guard calls untradeable is a pair that gets no ladder.

**Emitter.** `stack.rung.refused` — actual = the chunk-plan reason and estimated slippage, expected = "within participation limits". Route through `feature_telemetry.record_skip(reason=...)` so refusal **counts** are visible without reading logs.

**Risk if wrong.** Chunking splits one intended price into several fills. The realised round-trip ratio can therefore fall below the fee floor the ladder was built to satisfy. The `stack.step.floor` check must re-run on the **realised average fill price**, not only on the intended rung price. Verifying the intended ladder and shipping the chunked one is the fix-must-reach-the-read-path failure.

### 4.9 Exchange-truth verification before a buy rung

**Feature.** `buy_safety.verify_buy_safe_or_refuse` (`src/trading/buy_safety.py:78-84`); `.total` preferred over `.free` (`:138-143`); phantom-zero cross-check (`:144-157`); exception refusal (`:158-162`).

**Grid problem.** After a restart, or after a bad balance response, a ladder re-buys a position it already holds. The rung state machine says the level is empty; the exchange says otherwise.

**Mechanism.** Call it before every buy rung with `expected_units` set from the ladder's own tracked units and `path="stack_rung_buy"`. The `.total`-over-`.free` preference matters enormously here, because a ladder's whole design is resting orders and units locked in a resting sell must still count.

**Emitter.** `stack.buy.verified` — actual = `verified_units` returned, expected = the ladder's tracked units, ok = agreement within tolerance. On refusal, actual = the refusal string, ok = False.

**Risk if wrong.** It proves one thing, and it is not affordability. Its only exchange call is `get_balance(target_asset)` (`:134`). It never reads the quote balance, never consults either registry, never compares against a target or ceiling. It returns rather than raising, and never logs — its module logger is declared at `:75` and unused in the function body. Enforcement is entirely the caller's.

### 4.10 A net-of-fee unit accumulator

**Feature.** The unit-gain formula at `src/trading/scrumming_bot.py:8857-8859`. The persistence pattern at `:3791` and `:4060-4061`.

**Grid problem.** Every commodity grid books profit in quote currency. On a platform whose purpose is unit accumulation that is the wrong objective function.

**Mechanism.** Three parts. First, size each rung by constant **quote** value, so lower rungs buy more units and the holding ratchets up — the convention [KuCoin's Infinity Grid](https://www.kucoin.com/learn/trading-bot/what-is-infinity-grid-trading-bot-and-how-does-it-work) publishes ("sells 500 USDT worth of BTC" to restore a 50,000 USDT holding) and the one `strategy_compare` already uses (`cap_per = capital / (n_levels + 1)`, `src/trading/strategy_compare.py:419`). Second, **subtract both fees** from the unit measurement — see attack A4 for the exact correction. Third, add the net figure to a persisted lifetime counter that is never drained.

**Emitter.** `stack.units.accumulated` — actual = the lifetime total after this round trip, expected = prior total + this cycle's **net** extra units, ok = equality within 1e-9. This is a monotonic-increase check by construction. It is also the metric `topology_stress` already reports (`src/trading/topology_stress.py:81-89`).

**Risk if wrong.** Two verified traps. `_dist_accumulator` looks like the counter to copy — it does sum `extra_asset` (`:9177`) and is persisted (`:3791`, `:4060-4061`) — but it is zeroed the moment the DIST sell fires (`:9442`) on a bullish read (`:9393-9394`). Copy it and the ladder sells its accumulated units back. Separately, a tranche's `units` and its `usd/ref` are not the same number once Smart Wire has taken its cut: `usd` is pro-rated after routing while `units` is the full amount consumed (`:7835-7843, :7864-7871`). `asset_at_scrum` uses `usd/ref`; the rebuy lot split uses `units`. Pick one field, name it in the emitter context, and reconcile against `_main_lots` (`:12134-12146`).

### 4.11 Coverage classification as the validation instrument

**Feature.** `GateStatus` (`src/trading/gate_coverage.py:77-93`), `classify_trades` (`:305-376`), `compute_validation_window` (`:486-531`).

**Grid problem.** "The ladder agreed with the gates on 100% of trades" computed over 11% coverage is the standard grid-validation lie.

**Mechanism.** The classifier is bot-agnostic. It reads only dicts carrying `timestamp`, `bot_id` and `data{scrum_armed, fold_armed, scrum_blockers, fold_blockers}` (`:177-203`), pairs each trade with the nearest decision row for the same bot, and **names** why when it cannot: `HAS_GATE`, `BEFORE_LOGGING`, `LOG_GAP`, `NO_GATE_IN_TOLERANCE`, `NO_GATE_FOR_BOT`, `NO_GATE_DATA`. Emit the same four keys for arm and disarm and the whole instrument comes free. `compute_validation_window` floors the replay window at the oldest `HAS_GATE` trade and backs off `warmup_candles * step_ms`.

**Emitter.** `stack.coverage.classified` — actual = the status histogram, expected = zero rows in `NO_GATE_IN_TOLERANCE` and `NO_GATE_FOR_BOT`. Report coverage percent **alongside** any agreement percent, never instead of it.

**Risk if wrong.** `gate.log` records the advisory list, not the chain verdict (Section 4.2). Compare chain to chain in-process. Also: the parity test both docstrings cite, `tests/test_gate_chain_parity.py` (`src/trading/gate_chain.py:24`, `src/trading/scrumming_bot.py:66`), is not in the active suite — it lives under `_archive/tests_pre_2026_07_25/`. No active test constructs a `GateChain`.

---

## 5. Adversarial review

### A1 — FATAL. The P0b guard forbids a ladder on the autonomous path

`_execute_sell` returns `None` if any open SELL exists on the symbol (`src/trading/scrumming_bot.py:11306-11332`). `_execute_buy` mirrors it (`:11688-11717`). No count threshold, no whitelist. Both refuse on a `get_open_orders` exception. The `except` fallback is **wider** than the happy path — it treats all open orders on the symbol as blocking regardless of side, so one resting sell also blocks every buy.

Removing the guard reopens the oversell-below-zero incident it was written for. **It cannot be tuned away.** The only architectural escape is the one Stack Mode already takes: `_open_stack_from_scrum` calls `guarded_place_order` directly (`:10955`) and never traverses `_execute_sell`. The ladder path and the safety path are therefore already mutually exclusive in shipped code, and that is nowhere documented as a property.

### A2 — FATAL. Nothing in the bot layer ever cancels an order

Repo-wide grep for `cancel_order` over `src`, `main.py`, `tools`, `tests` returns two call sites in the trading layer: `src/trading/reconciliation.py:303` and `src/trading/smart_orders.py:388`. `ReconciliationEngine` is constructed only by the GUI (`src/gui/main_window.py:3355`), is operator-driven, and its recommender returns "monitor" for a partially-filled order — so a half-filled ladder is explicitly not cancelled. The `smart_orders` site is a limit-timeout fallback inside one execution strategy, unreachable from the stack path. `ScrummingBot` contains **zero** `cancel_order` calls, and `stop()` (`:12181-12189`) releases the capital reservation, stops phantoms, and exits without touching the book.

Consequence: `gate_chain` gates the **decision to place**, not the book. A ladder gated off by `adx_trend_suppression` or the circuit breaker holds its resting orders live on Coinbase indefinitely, filling against a strategy that has decided to stand down. No code path retracts it. No emitter reports it. Scrum/Fold is immune only because it leaves nothing resting.

### A3 — FATAL for a dense ladder, manageable for a sparse one. The fee arithmetic

Section 1's table is the finding. Twenty rungs need a 27.13% band at the platform's own 0.6%/0.6% assumption and 43.49% at the sim backend's 0.6%/1.2%. Six rungs need 7.47% and 11.4% respectively. **The concept survives only at 3 to 6 rungs**, which is Stack Mode's shipped default of 3 (`src/trading/bot_container.py:292`).

Serious in shipped code, independent of any grid: the FOLD eligibility filter is `ticker.last <= t["ref"] * _otd_factor` where `_otd_factor = 1 - scrumming_interval_pct/100` clamped to `[0,50]` (`src/trading/scrumming_bot.py:8314-8323, :8624-8627`). No fee term. At the shipped `scrumming_interval_pct = 1.0` (`src/trading/bot_container.py:134`) the gate fires 0.207 points **inside** break-even. Three sites hold two definitions: the SCRUM/FOLD hysteresis adds one fee (`src/trading/scrumming_bot.py:6916-6922`; `src/trading/gate_chain.py:405`) and is armed-only; Stack adds one fee (`:10901-10905`); the fold eligibility filter adds none.

### A4 — SERIOUS (downgraded from FATAL on verification). The unit metric is fee-blind, by exactly r*

Read every input. `scrum_usd = scrum_asset * sell_fill` (`:7806`) — gross. `buy_cost = _fusd * _taper` (`:8749`) — gross, with `_taper` the ceiling taper (`:3659-3682`), not a fee. `buy_asset = buy_cost / buy_fill` (`:8857`). `asset_at_scrum = sum(t["usd"] / t["ref"])` (`:8858`). `extra_asset = buy_asset - asset_at_scrum` (`:8859`).

Both legs are gross, so the implied unit factor is `ref / buy_fill` (with `_taper = 1`). The true post-fee unit factor is `ref(1 - f_sell) / (buy_fill(1 + f_buy))`. Divide:

```
reported_factor / true_factor = (1 + f_buy) / (1 - f_sell) = r*
```

**The overstatement is exactly the break-even ratio, independent of price, interval and fill.** At 0.6%/0.6% the metric overstates the unit factor by 1.0120724 on every fold.

**CORRECTED 2026-08-09 on direct verification.** The original claim here
was that the gate admits a fold at `ref/buy_fill >= 1/0.99 = 1.010101`,
so every fold in `[1.010101, 1.0120724)` would report a gain and lose
units. That is WRONG, and the error was using the wrong gate.

The opposing-hysteresis gates DO add the fee. `scrumming_bot.py:11186-11190`
(scrum side) and `:11608-11612` (fold side) both compute
`_eff_pct = _interval + _fee` and require the move to clear it. At the
shipped defaults (`scrumming_interval_pct` 1.0, `trading_fee_pct` 0.6)
that is **1.6%**, which exceeds break-even `r* = 1.2072%`. On that path
the gate is CONSERVATIVE, and the loss band claimed above sits below it
and is refused.

What survives is narrower and still worth fixing: the REPORTED figure is
gross. `extra_asset` overstates the true post-fee unit factor by exactly
`r*` — 1.2072% per fold at 0.6%/0.6%. The bot accumulates; the number it
prints for how much is optimistic by a fixed ratio.

NOT ESTABLISHED, and not to be repeated without work: what happens when
the opposing hysteresis is NOT armed (`_hyst_armed_fold_side` false, or
`_hyst_ref_fold_side` 0). Those gates are conditional. Whether an
unarmed path can admit a sub-break-even fold was not traced.

Nothing contradicts it, because no lifetime net counter exists (Section 4.10 risk). This is the `ta_invariants` ADX pattern repeating: a plausible number, no expectation attached. **Fix the reported metric before designing anything that consumes it.**

### A5 — SERIOUS. A unit-denominated grid is Scrum/Fold with more levels

Constant-quote-value rung sizing is the only sizing that accumulates units. Constant quote value means "sell the excess above a target USD value, buy back below it". That is the shipped delta rule verbatim: `delta = (holdings x price) - target; If delta > 0 and delta_pct >= interval: SCRUM ...; If fold_queue > 0 and price < fold_ref: FOLD` (`src/trading/scrumming_bot.py:14-17`). KuCoin publishes the same mechanic. The only genuine difference is resting orders instead of market orders, and Scrum/Fold's one-market-order-per-event design is exactly what dodges A1, A2 and half of A3.

**Falsifier, not rhetoric:** run a constant-quote ladder and Scrum/Fold on one tape and diff the fill sequence. If the ladder's fills differ only by rung quantisation, the new class contributes order-management surface and nothing else. Judge on gate-latch parity, per the standing criterion — not on P&L.

### A6 — SERIOUS. The operator deleted the grid bot, and said why

`src/trading/bot_container.py:56-58` and `:64-65`. Eight grid-legacy config fields were excised at v3.23.3; several more are quarantined as deprecated kwargs. Any new grid proposal must answer that directive in its first paragraph, not its appendix. This report's answer is: do not propose one.

### A7 — SERIOUS. `stack_math` has no geometric law, and the obvious reuse is wrong

Detailed in Section 3. `_delta_multiplier` scales the **step** (`src/trading/stack_math.py:64-81`), the generator accumulates a percent **offset** (`:207-209`), and the config comment agrees (`src/trading/bot_container.py:294-300`). Exponential mode gives cumulative offsets 0, 1, 3, 7, 15, 31 × SD, so ratios **grow**. Linear mode gives 0, 1, 2, 3 × SD, so ratios **shrink** — the same top-of-range decay that makes arithmetic grids waste their top rungs.

The formula `N = floor(ln(U/L) / ln(r*))` holds only for a constant-ratio ladder. Paired with exponential mode at L=100, U=125, SD=1.2072%, the ladder leaves the band at rung 5 while the formula promises 18. **This defect ships green**: the module's own falsification clause (`:30-35`) checks monotonicity, merge distance and minimum size, and says nothing about ratio constancy.

### A8 — SERIOUS, and new. The operator's Split Distance setting never reaches the ladder

`BotConfig` is a strict `@dataclass` (`src/trading/bot_container.py:74-75`) whose field is **`split_distance: float = 1.0`** (`:285`). It is in the shared-fields allowlist as `"split_distance"` (`:594`), plumbed from the GUI as `"split_distance"` (`src/gui/bot_live_settings.py:2275, :2282`; `src/gui/bot_wizard.py:1493`; `src/gui/main_window.py:7429`) and rebuilt as `"split_distance"` (`src/trading/bot_container.py:2941`).

The reader is `split_dist = float(getattr(self.config, "split_distance_pct", 1.0) or 1.0)` (`src/trading/scrumming_bot.py:10908`). **`split_distance_pct` is not a field on `BotConfig`.** The `getattr` always misses. The ladder's spacing is permanently 1.0%, whatever the operator sets in the range 0.1–20.0.

The test that should catch it pins the wrong name: `tests/test_stack_mode_visible.py:224` defines `split_distance_pct = 1.0` on a stub config, so the test agrees with the reader and not with the dataclass. This is the `emit_contracts` failure class exactly — a verifier read `data["action"]` while the producer wrote `data["type"]`, reported coverage 0/17, and let 665 trades flow past unseen (`src/core/emit_contracts.py:17-26`). Named here, not fixed; this report is read-only.

Note the arithmetic consequence: a permanent 1.0% inter-rung spacing is **below** the 1.2072% two-sided floor.

### A9 — SERIOUS. The advisory blocker list is what `gate.log` records

`tick()` builds `_scrum_blockers` and `_fold_blockers` by hand (`src/trading/scrumming_bot.py:7469-7518, :8204-8245`) and writes them to `_last_gate_state` (`:7515-7516, :8244-8245`). `_emit_gate_decision_at_fire` reads only that dict (`:4934-4991`). The SCRUM accumulator carries 10 conditions and omits `adx_trend_suppression`, `efficiency_ratio_regime` and `zscore_extremity`; the FOLD accumulator carries 8 and omits `zscore_extremity`. `gate.log` can therefore report `scrum_armed=true` on a tick where the binding chain refused. Any parity work that reads `gate.log` measures the advisory chain.

### A10 — SERIOUS. Three verified capital-claim leaks

1. `prune_expired` (`src/trading/capital_reservation.py:567`) and `force_release_all` (`:438`) have zero callers. The documented backstop never runs. Measured: 16,551 rows, 28 live, heartbeats to 71.8 days (`tools/purge_orphan_reservations.py:8-13`).
2. `release()` needs an in-memory token while the row is persisted on every mutation (`:345-362`, `:217-237`). A hard kill strands the row forever; `_load()` rehydrates it and the bot reserves afresh.
3. `WalletReservations.reserve()` has no refusal branch (`src/trading/wallet_reservations.py:60-69`), `_held` is one float per key with no owner (`:46`), and `release()` takes an amount from any caller. An over-release reads as "nobody holds anything" and hands the next caller the full wallet. Its documented lock-free design (`:23-29`) is sound against coroutines on one loop and offers nothing against a second thread.

Both persistence layers swallow write failures and keep trading (`src/trading/capital_reservation.py:233-237`; `src/trading/capital_registry.py:547-565`).

### A11 — MANAGEABLE, but it undermines the invariant channel. `check()` counts a throwing predicate as applied

`ta_invariants.check` increments `applied += 1` at `src/trading/ta_invariants.py:262`, **before** running the predicate at `:263`. The `except` at `:265-274` logs at debug and continues, but `applied` stays incremented. When a throwing invariant is the only applicable one, `check()` returns `(True, "1 invariants")` at `:277` — a PASS verdict from a bound that never evaluated. The module's own comment at `:270-271` names that outcome as the thing it wants to avoid: "a bound that never evaluates looks identical to a bound that always passes."

### A12 — MANAGEABLE. The existing GRID baseline is not a fair comparison

`run_grid` is arithmetic, anchored to `closes[0]` forever (`src/trading/strategy_compare.py:412`), with `fee_rate: float = 0.001` (`:400`) — one sixth of the platform's own `trading_fee_pct = 0.6` and `default_fee_rate = 0.006`. It never re-centres, so it is the zero-expectation static grid the literature analyses. Publishing any GRID-versus-ACERVATOR ranking from that row would be a fabricated win. Either fix the baseline or state plainly that no comparison has been run.

### A13 — MANAGEABLE. `stack_math` violates its own falsifier on one branch

`src/trading/stack_math.py:132-137`, described in Section 3. Close the branch in the caller or the ladder emits unfillable rungs.

### A14 — MANAGEABLE. No active test constructs a `GateChain`

`tests/test_gate_chain_parity.py` is cited by two docstrings (`src/trading/gate_chain.py:24`, `src/trading/scrumming_bot.py:66`) and lives only in `_archive/tests_pre_2026_07_25/`. The release gate does not currently re-prove chain equivalence. A related stale citation: `src/trading/ta_engine.py:302` names `ScrummingTrendRegimeGate`, which does not exist; the class is `ADXTrendSuppressionGate` (`src/trading/gate_chain.py:490`).

---

## 6. Comparative implementations

| System | What it does | Key published mechanism | Source |
|---|---|---|---|
| **Binance Spot Grid — parameters** | Publishes the spacing and profit formulas every other venue paraphrases | `d = (Upper - Lower)/N`; `r = (Upper/Lower)^(1/N)`; three profit formulas (Section 2). Worked example U=450 L=400 N=5 c=0.001 → 2.29% / 2.07% / 2.18%, all three reproduced by hand. The fetched minimum-profit denominator reads `Lower - d` and does not reproduce the page's own 2.07%; `Upper - d` does (HYPOTHESIS: extraction artefact) | [link](https://www.binance.com/en/support/faq/binance-spot-grid-trading-parameters-688ff6ff08734848915de76a07b953dd) |
| **Binance Spot Grid — auto parameters** | Derives bounds from historical volatility | Bollinger bands on 1-day candles over 7/30/180 periods with "BBM is set to 3"; range clamped to min `1% * n^(1/3)`, max `15% * n^(1/3)`, default `5% * n^(1/3)`; defaults to Arithmetic Mode; "You can only create 5 grid strategies for each trading pair". **No ATR rule on this page** | [link](https://www.binance.com/en/support/faq/how-to-use-spot-grid-trading-auto-parameters-76bd4effa3c4456c971a1c6835762742) |
| **Binance Futures Grid — AI parameters** | The ATR rung-count rule. **This is the FUTURES product, not spot** | `Grid Number = (1 + buffer) * (grid_upper_limit - grid_lower_limit) / ATR` with buffer "currently set to 30%"; ATR on 30-minute/168, 1-hour/360 or 2-hour/1,080 periods per selection | [link](https://www.binance.com/en/support/faq/binance-futures-grid-trading-ai-parameters-guide-647b0dba72d145219688b04aa51405fc) |
| **Binance Spot Grid — Trailing Up** | Step-quantised re-anchor | Trigger = upper limit + one grid step. Cancel the lowest buy, place a new buy at the old upper limit. Example: 25,000–45,000, 5 grids, 4,000 step, trigger 49,000 → 29,000–49,000, then 33,000–53,000. Halts on minimum notional, maximum pair price, minimum order quantity. The stop-loss price cannot be changed once set | [link](https://www.binance.com/en/support/faq/how-to-use-the-trailing-up-function-in-spot-grid-trading-3d987afd7906495cb4d997eccb8515bf) |
| **OKX Spot Grid** | Highest published level ceiling | Prose definitions only: arithmetic "position each grid line at fixed price intervals (for example, every 20 USDT)"; geometric "sets the grids using a fixed percentage from the current price, resulting in widening grids further out". Ceiling raised from "only up to 300 grids were supported" to "you can set up to 1,000 grids". No profit-per-grid formula published | [link](https://www.okx.com/en-us/help/how-do-i-manually-set-up-spot-grid-trading-bots) |
| **Bitget Spot Grid — FAQ** | A venue-side fee refusal | "Trading bots ensure that orders will only be opened if the profits on the grid are greater than the transaction fees." `Grid profit = (price difference per grid) x (amount per order) x (number of filled sell orders)`. "You can run up to 50 bots across all types" | [link](https://www.bitget.com/support/articles/12560603791273) |
| **Bitget — glossary** | Parameter vocabulary and net accounting | "Grid profit = arbitrage profit - transaction fees"; "Total profit = Est. asset value of bot - Total investment". One sentence on interval matching: "When you set a high number of grids within a narrow price range, the system activates interval matching to optimize your profits" — no rule published | [link](https://www.bitget.com/support/articles/12560603791272) |
| **KuCoin Infinity Grid** | The published twin of Scrum/Fold | No upper limit. Constant **quote value** sizing: hold 50,000 USDT of BTC at 1% per grid; at 50,500 the bot "sells 500 USDT worth of BTC", restoring 50,000. "The bot stops trading when it hits the lower limit and resumes once the price exceeds it." Guidance: "Smaller grids (<1%) result in more transactions with smaller profits, while larger grids (>1%) yield fewer transactions with larger profits", roughly 1% in bear markets and 2.5–3.5% in bull | [link](https://www.kucoin.com/learn/trading-bot/what-is-infinity-grid-trading-bot-and-how-does-it-work) |
| **Hummingbot GridExecutor** | The only open-source level generator read in full | `grid_range = (end_price - start_price)/start_price`; `min_notional_with_margin = min_notional * Decimal("1.05")`; `max_levels_by_step = int(grid_range / min_step_size)`; `n_levels = min(max_possible_levels, max_levels_by_step)`; `self.step = grid_range/(n_levels - 1)`; **`take_profit = max(self.step, config.triple_barrier_config.take_profit)`** — the per-rung exit can never be tighter than the step. Level states NOT_ACTIVE → OPEN_ORDER_PLACED → OPEN_ORDER_FILLED → CLOSE_ORDER_PLACED → COMPLETE | [link](https://raw.githubusercontent.com/hummingbot/hummingbot/master/hummingbot/strategy_v2/executors/grid_executor/grid_executor.py) |
| **Hummingbot GridStrike guide** | Full parameter surface and budget arithmetic | Config defaults: `start_price 0.58`, `end_price 0.95`, `limit_price 0.55`, `total_amount_quote 1000`, `min_spread_between_orders 0.001`, `min_order_amount_quote 5`, `max_open_orders 2`, `max_orders_per_batch 1`, `order_frequency 3`, `activation_bounds null`, `keep_position false`, take_profit 0.001, LIMIT_MAKER. Bounds: max orders by budget "$100 / $7 = 14.28 = 14 orders"; "Max Levels = Price Range % / min_spread_between_orders" with "23.6% / 0.7% = 33.7 levels". `limit_price` is a hard stop, distinct from the lower bound | [link](https://hummingbot.org/blog/strategy-guide-grid-strike/) |
| **infinity-grid (btschwertfeger)** | Open-source grid whose default strategy accumulates base units | `--interval` default 0.02 (percentage distance between buy and sell); `--n-open-buy-orders` default 3; `--amount-per-grid` is a fixed **quote** amount, so each lower fill returns more base units; `--max-investment` default 100000000000.0. Strategies GridHODL, GridSell, SWING, cDCA. Sizing guidance: "If the interval is defined to 2%, a number of 5 open buy positions ensures that a rapid price drop of almost 10% ... can be caught" | [config](https://infinity-grid.readthedocs.io/en/latest/04_configuration.html), [strategies](https://infinity-grid.readthedocs.io/en/latest/02_strategies.html) |
| **GridMaster Pro MT5** | Explicit ATR-multiplier spacing | "Grid spacing = ATR × multiplier". `ATRPeriod = 14`, `ATRMultiplier = 1.5`, `MaxOrders = 5`, `MaxDrawdownPct = 5.0` with `CloseOnDrawdown = true`. **Unreviewed hobby code, no published backtest** — treat 1.5 as a starting value, not a result | [link](https://raw.githubusercontent.com/sajidmahamud835/grid-master-pro-mt5-ea/main/README.md) |
| **WickHunter** | Clamped ATR spacing | Parameters "ATR Period", "ATR Timeframe", "Minimum Step (%)", "Maximum Step (%)". Clamp example: "never closer than 0.4% and never wider than 2%, even if ATR fluctuates". The ATR-to-step mapping is not published, so the rule cannot be replicated from this source | [link](https://docs.wickhunter.io/en/articles/11826956-atr-based-grid-bot-full-setup-guide) |
| **Avellaneda–Stoikov (via Hummingbot)** | The only formal model that centres quoting on inventory | Reservation price `r(s,q,t,σ)=s−qγσ²(T−t)`; optimal spread `δᵃ+δᵇ=γσ²(T−t)+2/γ ln(1+γ/κ)`. The spread term is volatility-scaled spacing; the `−qγσ²(T−t)` term is an inventory-driven re-anchor. Config exposes `risk_factor`, `order_amount_shape_factor`, `inventory_target_base_pct`, `execution_timeframe`, `volatility_buffer_size` 200, `trading_intensity_buffer_size` 200, `min_spread`, `order_level_mode`. The v1 page lists `parameters_based_on_spread`, `max_spread`, `order_book_depth_factor` and others as **removed** | [deep dive](https://hummingbot.org/blog/technical-deep-dive-into-the-avellaneda--stoikov-strategy/), [v1 strategy](https://hummingbot.org/strategies/v1-strategies/avellaneda-market-making/) |
| **Chen, Chen & Jang — DGT** | Proves the static grid has ~zero expectation, then fixes it | Geometric ladder `P*(1+k)^m`; equal up/down probability; expected return essentially zero before costs, negative after. Reset rule: re-centre on the current price when price breaks either bound. Upward break recovers and reinvests capital; downward break holds the asset and uses accumulated arbitrage profit as the new principal. Binance 1-minute BTC and ETH, January 2021 to July 2024, fee 0.0008 | [arXiv 2506.11921](https://arxiv.org/abs/2506.11921) |
| **Yang & Malik — RL with dynamic scaling** | Cleanest published template for learning position size over a discretised spread. Not a grid | State = Position ∈ [−1,1], Spread (z-score normalised), Zone ∈ {Short, Neutral Short, Close, Neutral Long, Long}. Action = continuous allocation ∈ [−1,1]. Reward = portfolio reward on close + zone-appropriate action reward − transaction punishment. PPO, A2C, DQN, SAC. Formation Oct–Nov 2023, test Dec 2023; 1-minute 121,500 entries, 3-minute 40,500, 5-minute 24,300. Dynamic-scaling variant 31.53% annualised vs 8.33% fixed-threshold | [arXiv 2407.16103](https://arxiv.org/html/2407.16103v1) |
| **Yeh, Hsieh & Huang — SSO + FNN/LSTM** | Optimise grid parameters offline per regime, then learn the regime→parameter map | HYPOTHESIS on everything but the architecture: only the abstract listing was read. It gives no decision-variable names, no fitness function, no dataset and no results. **Do not cite parameter names from this work** | [arXiv 2211.12839](https://arxiv.org/abs/2211.12839) |
| **Stevens Institute FSC project** | Negative result worth respecting | Random Forest and LSTM parameter adjustment "did not offer significant improvements over traditional grid trading" | [link](https://fsc.stevens.edu/cryptocurrency-market-making-improving-grid-trading-strategies-in-bitcoin/) |
| **Coinbase CDP — Get Transaction Summary** | The runtime source of truth for the fee that sets `r*` | Returns `pricing_tier` ("Pricing tier for user, determined by notional (USD) volume"), `taker_fee_rate`, `maker_fee_rate`, `aop_from`, `aop_to`. The documented example tier is "<$10k". **The full tier table is not on this page, and `help.coinbase.com` returned HTTP 403, so no Coinbase tier percentages are reported in this document** | [link](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/fees/get-transaction-summary) |

Two supporting indicator references. Bollinger BandWidth: `(Upper Band - Lower Band) / Middle Band * 100`, defaults Length 20, StdDev 2, Source close ([TradingView](https://www.tradingview.com/support/solutions/43000501972-bollinger-bandwidth-bbw/)). ADX: DX = |+DI14 − −DI14| / (+DI14 + −DI14) × 100, smoothed by "multiplying the previous 14-day ADX value by 13, adding the most recent DX value and dividing this total by 14"; above 25 = strong trend, below 20 = no trend, 20–25 grey zone ([StockCharts](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/average-directional-index-adx)). The `0 <= adx <= 100` bound is **not published on that page**; it is asserted in-repo at `src/trading/ta_invariants.py:15-25` as derivable from the formula.

---

## 7. Refined concept — the Fee-Correct Two-Sided Stack

**Not a new bot class.** An extension of `ScrummingBot`'s existing Stack Mode, gated behind `stack_mode` (`src/trading/bot_container.py:281`), which is already off on all 35–37 bots.

**What it is.** On a SCRUM decision, instead of one market sell, place a small ladder of resting SELL rungs above the scrum price. When any rung fills, create its fold tranche as today. Mirror the same generator downward to place a small ladder of resting BUY rungs at fold-eligible prices. Re-anchor the whole pair of ladders on a bound breach, quantised to one rung, holding units on the downward break.

### Invariants

| # | Invariant | ENFORCED by | OBSERVED by |
|---|---|---|---|
| I1 | Every adjacent rung ratio ≥ `r* = (1+f_buy)/(1-f_sell)`, with fees read from the venue at runtime | Refusal in the ladder generator before placement; the ladder is not built if it cannot satisfy the floor | `stack.step.floor` (actual = placed ratio, expected = `r*`) |
| I2 | The realised round trip also clears `r*`, computed from actual fill prices | Post-fill check; a breach disarms the ladder for the cycle | `stack.step.realised` (actual = `sell_fill/buy_fill`, expected = `r*`) |
| I3 | Rung prices are strictly increasing, no two within 0.1%, no rung below `min_order_size`, sizes sum to the requested size | `stack_math` merge + monotonicity assert (`src/trading/stack_math.py:101-109, 218-222`) **plus a new refusal on the `max_viable_n <= 0` branch** | `stack.ladder.built` (actual = tuple list, expected = the four clauses) |
| I4 | Spacing = `clamp(k * atr_pct, floor, ceiling)` where `floor >= s*` | Clamp in the spacing helper; refuse if `ceiling < floor` | `stack.spacing.computed` (payload carries `atr_pct`, `k`, raw, clamped, both bounds) |
| I5 | The ladder arms only when ADX and Efficiency Ratio are **populated** and in range | Grid-chain subclasses that return `passed=False` on the 0.0 sentinel | `stack.arm.decision` + `stack.arm.input` |
| I6 | The ladder's base units are reserved before placement; the buy ladder's notional is reserved before placement | `CapitalReservationRegistry.reserve` / `WalletReservations.reserve` with `try/finally` release | `stack.reserve.ladder`, `stack.wallet.headroom` |
| I7 | Every rung passes the market-impact caps | `VolumeGuard` via `guarded_place_order` (`src/trading/bot_container.py:996`) | `stack.rung.refused` + `feature_telemetry.record_skip` |
| I8 | No buy rung is placed unless exchange truth agrees with tracked units | `buy_safety.verify_buy_safe_or_refuse` | `stack.buy.verified` |
| I9 | **On disarm, stand-down, stop, or re-anchor, every resting rung is cancelled** | A new `_teardown_ladder()` that calls `exchange.cancel_order` per recorded rung id, invoked from the disarm branch and from `stop()` | `stack.ladder.cancelled` (actual = cancel confirmations, expected = rung count at teardown) |
| I10 | The lifetime net unit counter is monotonically non-decreasing and is **never drained** | A dedicated persisted field, separate from `_dist_accumulator` | `stack.units.accumulated` (expected = prior + this cycle's net) |
| I11 | Every rung and every fill carries a distinguishable order id in the persisted ledger | Extend the existing `_stack_tranches` entry shape (`src/trading/scrumming_bot.py:10942-10952`), which already carries `order_id` | `stack.rung.identified` |

### How this differs from Scrum/Fold — stated plainly

It differs in **three** ways and no more.

1. **Execution shape.** N resting limit rungs replace one market order per event. That is a fill-quality change, measurable on `trade_grader`'s execution axis (`src/trading/trade_grader.py:114-133`), not a strategy change.
2. **Fee correctness.** The step floor `r*` and the net unit metric are new. Both are **bug fixes to shipped Scrum/Fold**, not features of a ladder — see A3 and A4. They should land in Scrum/Fold whether or not the ladder ships.
3. **Explicit re-anchoring.** Quantised re-centre on a bound breach, asymmetric on the downward break (hold units). Scrum/Fold re-anchors implicitly through `_last_trade_price` and the hysteresis pivot; it has no bound concept.

**The honest reading.** Point 2 is the largest available gain and it does not need a ladder. Point 1 is the only genuine ladder benefit and it is capped by the fee arithmetic at 3–6 rungs. Point 3 is the literature's identified source of edge and it is untested here.

**Therefore: if Stage 0 or Stage 1 shows that the fee-corrected metric leaves Scrum/Fold's accumulation near zero, the correct action is to fix Scrum/Fold and stop.** The ladder does not rescue an unprofitable round trip; it multiplies it.

---

## 8. Development plan

Each stage names what ships, files touched, the test **and its positive control**, the emitter, and the exit criterion. Every stage runs on an isolated hard copy and promotes only after `python -m tools.harness.check_release_readiness` returns `[OK] Release-ready`.

### Stage 0 — Fee-floor rung census (offline, read-only). The cheap falsifier.

**What ships.** A harness script only. No `src/` change. It reads a tablet, computes for each live-universe asset the realised band over rolling windows, reads the live Coinbase fee tier, computes `r*`, and reports the distribution of `N_max = floor(ln(band)/ln(r*))` per asset.

**Files touched.** `tools/harness/` only.

**Test.** Assert the census returns the analytic answer on a synthetic asset with a known band.
**Positive control.** Inject a synthetic asset with an exact 27.13% band at 0.6%/0.6% and assert the census returns exactly 20. Then inject a 6.0% band and assert it returns 4. A census that returns the same number for both is measuring nothing.

**Emitter.** `stack.census.rungs` — actual = per-asset `N_max`, expected = "≥ 4", ok = the predicate holds.

**Exit criterion.** The median live asset supports **≥ 4** fee-clearing rungs at the live fee tier over its typical band. **If it does not, stop the project here.** One script, no production risk, and it answers the only question that matters.

### Stage 1 — Net unit accounting

**What ships.** A fee-inclusive net-unit computation beside `extra_asset`, and a persisted lifetime counter that is never drained. Both apply to shipped Scrum/Fold, not only to the ladder.

**Files touched.** `src/trading/scrumming_bot.py` (the `:8857-8868` region, the export at `:3742-3867`, the import at `:4060-4061`), `src/core/emit_contracts.py`.

**Test.** Feed a fold with known `ref`, `buy_fill` and fee rates; assert `net_units` equals `gross_units / r*` within 1e-12.
**Positive control.** Set fees to 0.0 and assert `net_units == gross_units` exactly. A net figure that never differs from gross is an unwired fee term.

**Emitter.** `stack.units.accumulated` and `stack.units.net`.

**Exit criterion.** On a full tablet replay of a live bot, the net lifetime counter and the gross sum differ by the expected multiplicative factor, and the counter never decreases.

### Stage 2 — Geometric price law and the fee floor in `stack_math`

**What ships.** A fourth spacing mode, `geometric`, with `price_i = first_price * r**i`. A refusal on the `max_viable_n <= 0` branch. `min_opposing_pct` fed from `r*`. **And the `split_distance_pct` → `split_distance` name fix** (A8), with its test corrected.

**Files touched.** `src/trading/stack_math.py`, `src/trading/scrumming_bot.py:10908`, `tests/test_stack_math.py`, `tests/test_stack_mode_visible.py`.

**Test.** Assert every adjacent ratio in geometric mode is constant to 1e-12 and ≥ `r*`. Assert the operator's `split_distance` value reaches the generator by constructing a **real `BotConfig`**, not a stub.
**Positive control.** Build a ladder with `split_distance_pct = 0.30` at 0.6%/0.6% fees and assert the floor refusal fires. Build one at 2.0% and assert it does not. A generator with zero refusals in both cases has an unwired clamp.

**Emitter.** `stack.step.floor`, `stack.ladder.built`.

**Exit criterion.** No ladder can be produced whose adjacent ratio is below `r*`, proven by the negative fixture.

### Stage 3 — Ladder lifecycle: cancel, identify, tear down

**What ships.** `_teardown_ladder()` on `ScrummingBot`, called from the disarm branch, from re-anchor, and from `stop()`. Per-rung order id recorded in the persisted ledger.

**Files touched.** `src/trading/scrumming_bot.py:10942-10993` and `:12181-12189`; `src/gui/simulator_tab/fleet/sim_exchange.py` already implements `cancel_order` at `:728` for the sim.

**Test.** Place 3 rungs in sim, disarm, assert the sim book is empty and three cancel confirmations were emitted.
**Positive control.** Place 3 rungs and do **not** disarm; assert the book still holds 3 and zero cancels were emitted. A teardown that reports success in both runs is not reading the book.

**Emitter.** `stack.ladder.cancelled` — actual = cancel confirmations, expected = rung count at teardown.

**Exit criterion.** No sim run ends with resting orders on the book. This closes attack A2 and is a prerequisite for any live exposure.

### Stage 4 — Buy-side mirror ladder, sim only

**What ships.** The descending generator, the buy-rung path through `guarded_place_order`, and `buy_safety` per rung. Sim only. **No live path.**

**Files touched.** `src/trading/scrumming_bot.py`, `src/gui/simulator_tab/fleet/` (forked class bodies, no imports of live stateful classes).

**Test.** A fixture where price oscillates across a 10% band; assert every buy rung that fills has a matching sell rung ≥ `r*` above it.
**Positive control.** A monotone-down tape; assert every buy rung fills, no sell rung fills, and `stack.step.realised` reports the shortfall rather than silence.

**Emitter.** `stack.rung.placed`, `stack.rung.filled`, `stack.step.realised`, `stack.buy.verified`.

**Exit criterion.** On the oscillating fixture, net units increase and `stack.step.realised` never reports a breach.

### Stage 5 — Regime arming chain with the sentinel inverted

**What ships.** A third `GateChain` with subclassed ADX and ER gates that refuse on the zero sentinel.

**Files touched.** `src/trading/gate_chain.py` (new subclasses, no change to existing classes), `src/trading/scrumming_bot.py` (chain construction beside `:449-450`).

**Test.** A strong-trend tape; assert the chain latches closed and names `adx_trend_suppression` in the blocked list.
**Positive control.** Run the chain with `ctx.adx = 0.0` and assert it **refuses**. If it arms, the sentinel inversion did not land.

**Emitter.** `stack.arm.decision`, `stack.arm.input`.

**Exit criterion.** The ladder never arms on an unpopulated regime field, proven by the sentinel fixture.

### Stage 6 — Capital claim and impact ceiling per rung

**What ships.** Ladder-level reservation on both registries, with `try/finally` release. Every rung through `guarded_place_order`.

**Files touched.** `src/trading/scrumming_bot.py`; `src/trading/wallet_reservations.py` and `src/trading/capital_reservation.py` untouched except for a call to `prune_expired` on a timer (this also closes leak 1 of A10 for the whole platform).

**Test.** Two bots on one wallet; assert the second sees reduced headroom and sizes down.
**Positive control.** One bot alone; assert headroom equals free balance. A reservation system that reports the same headroom in both runs is not netting.

**Emitter.** `stack.reserve.ladder`, `stack.wallet.headroom`, `stack.rung.refused`.

**Exit criterion.** No run over-commits the wallet, and `prune_expired` demonstrably clears a dead claim within `HEARTBEAT_TTL`.

### Stage 7 — Sim validation on gate-latch parity, then dispersion

**What ships.** No new behaviour. A validation run.

**Files touched.** `tools/harness/`, sim fixtures.

**Test.** Compare the ladder's chain verdicts against Scrum/Fold's chain verdicts **in process**, never through `gate.log` (A9). Then run `topology_stress` on the same topology under different noise realisations.
**Positive control.** Report the `gate_coverage` status histogram alongside every agreement percentage. A 100% agreement over an 11% `HAS_GATE` share is a coverage claim, not a parity claim.

**Emitter.** `stack.coverage.classified`, `stack.score.compared` (actual = both fee rates used and both unit totals, expected = identical fee rates and identical tape).

**Exit criterion.** Gate-latch parity on the same data, with coverage reported, and no sign change in accumulation across noise trials (`src/trading/topology_stress.py:20-32`).

### Stage 8 — One live bot, visible ladder, smallest target

**What ships.** `stack_mode = True` on exactly one bot with the smallest target balance and the deepest book.

**Test.** Daily reconciliation of the persisted ledger against `get_open_orders` and against `_main_lots` (`src/trading/scrumming_bot.py:12134-12146`).
**Positive control.** Deliberately kill the process with rungs resting; assert the recovery path finds every rung by its recorded id and either adopts or cancels it. A recovery that reports "nothing to do" has not read the book.

**Emitter.** All of the above, plus `stack.sink.health` (`src/core/signal_contract.py:448-457`) so a partial record set announces itself.

**Exit criterion.** Seven days with the net unit counter monotonically non-decreasing, zero orphan orders at any daily reconciliation, and zero `stack.step.realised` breaches.

---

## 9. Relationship to the Extractor

**Three order paths exist, with three different safety postures.**

1. **`ScrummingBot` autonomous.** `_execute_buy` / `_execute_sell` — P0b guard (`:11306-11332`, `:11688-11717`), `buy_safety` (`:11801-11807`), entry-price bounds (`:11646-11660`).
2. **Stack Mode.** `_open_stack_from_scrum` → `guarded_place_order` directly (`:10955`). **No P0b guard.**
3. **Extractor.** `guarded_place_order` directly at `src/trading/extractor_bot.py:1018, :1218, :1379`, with `buy_safety` at `:1000` and `:1362`. **No P0b guard. Zero `get_open_orders` calls. Zero `cancel_order` calls.**

The Extractor already runs concurrent multi-pair positions on path 3. It is the existing proof that the platform tolerates a ladder-shaped order pattern — and also the existing proof of what goes wrong when it does.

**The grid inherits the Extractor's unsolved blockers. Directly.**

- **Asset contention.** The Extractor's stated concept is to pull base currency into volatile alts across many pairs concurrently (`src/trading/extractor_bot.py:6-16`). A two-sided Stack on the same alts contends for the same wallet and the same asset, and the only live arbitration is `effective_available` (`src/trading/capital_reservation.py:464`), which is advisory — nothing in the registry blocks an order.
- **Reservation leakage, already measured, already attributed.** The Extractor's `reserve()` has no `if self._crr_token is None` guard and overwrites the token (`src/trading/extractor_bot.py:318-333`). Its reason string, "Extractor chunk + hedge" (`:328`), is on 15,837 of the 16,523 orphaned rows the purge tool found (`tools/purge_orphan_reservations.py:11-12`). Its `stop()` deliberately does not clear the token on a failed release (`:504-513`). Note the site is presently unreachable — `set_initial_chunk_rate` (`:234`) has no caller — so the damage is historical and returns the moment the method is wired back.
- **No bot stand-down.** Neither bot can retract resting or in-flight exposure when a gate closes, because neither has a cancel path (A2).

**One architectural fix serves both.** Two, precisely:

1. **An owner-attributed claim ledger with a working release.** Call `prune_expired` on a timer; make `WalletReservations` per-owner instead of one float per key; give both registries a token-free operator sweep. This closes A10 for the Extractor and for the Stack in the same change.
2. **A teardown contract on the order layer.** A single `_teardown_orders(bot_id, symbol)` on the container, called from every `stop()` and every disarm path, backed by `exchange.cancel_order`. This closes A2 for path 1, path 2 and path 3 simultaneously.

Both fixes are worth doing **whether or not the ladder ships**, because path 3 is already live. Neither is a grid feature.

---

## 10. What this report does not settle

1. **The census answer.** Stage 0 has not been run. This report proves what `r*` requires; it does not know how many rungs the live universe actually supports. That number decides the project.
2. **The live Coinbase fee tier.** `help.coinbase.com` returned HTTP 403 and no tier table is reproduced here. `trading_fee_pct = 0.6` is the platform's own worst-case assumption (`src/trading/bot_container.py:345`), not a fetched figure. Reading the tier at runtime from Get Transaction Summary is a design decision the operator has not made.
3. **Whether `scrumming_interval_pct` was intended to absorb the second fee.** HYPOTHESIS. The full arming and pivot semantics were not read end-to-end. The fold eligibility filter demonstrably adds no fee (`src/trading/scrumming_bot.py:8314-8323, :8624-8627`); whether that is a defect or a deliberate choice is an operator call. It changes A3's severity, not its arithmetic.
4. **Whether Stack Mode has ever run.** `stack_mode` defaults to False (`src/trading/bot_container.py:281`) and this report found no evidence of a live enablement. No runtime evidence therefore exists that a multi-rung resting ladder works on this platform at all. HYPOTHESIS: it works, because `_open_stack_from_scrum` bypasses P0b — untested.
5. **Which re-anchor rule.** Binance shifts one rung per trigger; DGT re-centres the whole grid. Both are published; they differ; this report does not pick one. It picks a requirement: whichever is chosen must carry an emitter with the computed new bounds as `expected`, because a re-anchor that never fires looks exactly like a calm market.
6. **Five modules were not read.** No claim is made about `cross_pool.py`, `smart_wire.py`, `risk_manager.py`, `topology_proposals.py` or `system_load_oscillator.py`. `smart_wire` in particular touches tranche `usd` (Section 4.10 risk) and should be read before Stage 1.
7. **Whether the operator wants this at all.** The grid bot was deleted twice by directive (`src/trading/bot_container.py:56-58, :64-65`). This report recommends an extension of an existing, shipped, disabled feature rather than a new bot class, partly for that reason. If the operator reads "two-sided Stack" as "grid bot by another name", the directive applies and the answer is no.

### Two defects named, not fixed (read-only; one thing at a time)

- **`split_distance_pct` does not exist on `BotConfig`.** The reader at `src/trading/scrumming_bot.py:10908` misses the real field `split_distance` (`src/trading/bot_container.py:285`), so the operator's Split Distance setting never reaches the ladder generator. `tests/test_stack_mode_visible.py:224` pins the wrong name and cannot catch it.
- **`ta_invariants.check` counts a throwing predicate as applied.** `applied += 1` at `src/trading/ta_invariants.py:262` runs before the predicate at `:263`, so a bound that raises can still yield `(True, "1 invariants")` at `:277`.