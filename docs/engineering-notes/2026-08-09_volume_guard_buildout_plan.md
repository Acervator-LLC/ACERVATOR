# Volume Guard — build-out plan

## 1. Verdict up front

**Build a small guard. Do not build the module its docstring describes.**

VolumeGuard is not half-finished. It is finished, switched off, and unreachable. `enabled` is a property whose body is `return False` (`src/trading/volume_guard.py:182-190`). The only live read of that property is the dispatch test at `src/trading/bot_container.py:1080`. `execute()` and every method below it therefore never run. The 744 lines have never profiled, chunked, or slippage-checked a live order.

**The arithmetic that decides whether the guard trips at all.**

Permitted order size comes from `_compute_safe_sizes` (`volume_guard.py:352-387`): `safe = max(min(vol_limit, book_limit, avg_limit), 0.01)`.

- `vol_limit = V × 0.001` (`:358`, config `:39`)
- `book_limit = min(bid_depth_20, ask_depth_20) × 0.25` (`:362-364`, config `:45`)
- `avg_limit = (V / TRADES_PER_DAY_EST[tier]) × 10` (`:319-321`, `:371`, table `:161-167`)

Ignore the book limb for a moment. The volume-derived limbs give:

| 24h quote volume V | tier | binding limb | safe order |
|---|---|---|---|
| $100,000 | small | V/1000 | $100 |
| $999,999 | small | V/1000 | $1,000 |
| $1,000,000 | mid | V/1500 | $667 |
| $9,999,999 | mid | V/1500 | $6,667 |
| $10,000,000 | large | V/5000 | $2,000 |
| $99,999,999 | large | V/5000 | $20,000 |
| $100,000,000 | mega | V/20000 | $5,000 |

Now the order sizes. A Scrum fires when `delta_pct >= scrumming_interval_pct` (`src/trading/gate_chain.py:241-245`), default `1.0` (`bot_container.py:134`), and sizes as `delta = current_value - self._target_balance` (`src/trading/scrumming_bot.py:6469`) converted by `scrum_asset = abs(delta) / ticker.last` (`scrumming_bot.py:7699`). The code default target is `200.0` (`bot_container.py:101`). A routine fire is therefore about 1% of target — roughly **$2**.

Invert the table. An order Q trips the guard only when V falls below a crossover:

| order Q | trips when 24h volume is below |
|---|---|
| $2 | $2,000 |
| $5 | $5,000 |
| $25 | $25,000 |
| $200 | $200,000 |
| $500 | $500,000 |
| $2,000 | $3,000,000 |

**Conclusion 1 — the guard is inert for routine trading.** A $2 scrum needs a market under $2,000/day to trip. No Coinbase pair in the fleet is that thin. Chunking machinery for routine fires is machinery that never fires.

**Conclusion 2 — the guard is NOT inert for full-position exits.** `self_destruct` sells the entire holdings (`scrumming_bot.py:3171`) and `_execute_detonation` sells `min(sell_amount, self._current_holdings)` (`scrumming_bot.py:10700`). Those are target-sized, not 1%-sized. A $200 full exit trips below $200,000/day. A $500 bot's full exit trips below $500,000/day. Long-tail Coinbase alts live in that band. This is the only regime where the guard has real work.

**Conclusion 3 — the size function is broken in a way that matters.** A $5,000 order trips at V = $7M/day (safe $4,667), passes at V = $9M/day (safe $6,000), and trips again at V = $11M/day (safe $2,200). The guard is stricter on a deeper market. Cause: `avg_limit` divides by a tier constant that jumps faster than volume at each boundary (`:161-167` against `:389-399`).

**Conclusion 4 — chunking is close to break-even at these sizes, and clearly negative at 50 chunks.** The delay formula (`:445-454`) pins the gap at the 5000 ms ceiling for any market under $2.4M/day, because `volume_factor = min(V_hourly/100_000, 10)` reaches 1.0 only at $100,000/hour. A 3-chunk plan costs 10 s of exposure; the 50-chunk cap costs 245 s (the sleep is skipped after the last chunk, `:606`). At 5% daily volatility that is 5.4 bp and 26.6 bp of one-sigma price drift. The impact it would avoid on a $200 exit into a $200k/day book is about 23 bp (HYPOTHESIS — see §5). The trade is marginal at 3 chunks and losing at 50.

**Build this:** emitters, an arming record that cannot lie, a fail-closed profile path, a monotonic size function, a refusal path, an estimator with a price unit, and chunk re-entry into the order funnel. **Do not build:** TWAP, Almgren-Chriss trajectories, fleet-wide participation accounting, or 50-chunk icebergs. **Delete** `src/trading/smart_orders.py`.

Strongest single piece of evidence for each: for "build" — the guard fires zero emitters, so nothing it claims is falsifiable (`grep emit src/trading/volume_guard.py` returns no match, and `volume_guard` is absent from `src/core/emit_contracts.py`). For "do not build" — the crossover table above.

---

## 2. What VolumeGuard does today

**Measured behaviour: nothing.** `enabled` returns a literal `False` (`volume_guard.py:182-190`). The comment names the cause: "MEM-259 (Session 26 operator directive)". `bot_container.py:1080` is the only read. The setter at `:192-196` writes `self.config.enabled`, which the property ignores.

**Authority is split.** `execute()` gates on `self.config.enabled` (`:228`), which defaults `True` (`:62`). A direct caller would run the full machinery with no MEM-259 protection.

**The intended algorithm, traced.**

`execute():200` — passthrough if `config.enabled` false (`:229`); error report if no exchange (`:233`); profile (`:243`); passthrough if `not profile.is_tradeable` (`:250`); plan (`:255`); `_execute_single` or `_execute_iceberg` (`:265-270`); track hourly usage (`:273`); append history, trim to 500 (`:276-278`). Both passthrough returns skip steps 4 and 5.

`_get_market_profile():284` — 30 s cache (`:291`); `get_ticker` (`:301`); spread and `wide_spread = spread > 0.5` (`:308-311`); `volume_hourly_est = V/24` (`:314`); tier and `avg_trade_size_est` (`:319-321`); `get_orderbook` summed over 20 levels (`:325-332`); thin-market flag (`:339-340`); `_compute_safe_sizes` (`:343`). The profile is written to cache at `:349` whether it succeeded or threw.

`_compute_chunk_plan():403` — early return `within_safe_limits` if `safe_base <= 0 or amount <= safe_base` (`:417-421`); `chunk_base = safe_base × 0.7` (`:427`); `n = ceil(amount/chunk_base)`, `n = min(n, 50)`, `chunk_base = amount/n` (`:432-435`); delay (`:445-454`); slippage estimate (`:456-463`); reason string (`:467-472`).

`_execute_iceberg():556` — loop, place, accumulate, log; on chunk failure log a warning and **continue** (`:599-603`); every sixth chunk pop the cache and re-profile (`:608-612`); `success = total_filled > 0` (`:630`).

**Constants and defaults** (`VolumeGuardConfig:35-65`):

| field | default | line | status |
|---|---|---|---|
| `max_single_order_volume_pct` | 0.001 | :39 | live, used at :358 |
| `max_hourly_participation_pct` | 0.02 | :42 | **dead** — computed, never gates |
| `max_book_depth_pct` | 0.25 | :45 | live, used at :364 |
| `max_slippage_pct` | 1.0 | :48 | **never compared to slippage** |
| `min_chunk_delay_ms` | 200 | :51 | **dead** — delay floor is 500 ms |
| `max_chunk_delay_ms` | 5000 | :52 | live, both numerator and ceiling |
| `chunk_headroom_pct` | 0.7 | :53 | live, sets the chunk count |
| `book_depth_levels` | 20 | :56 | live, used at :326-330 |
| `min_daily_volume_usd` | 1000.0 | :59 | **dead** — see the tautology below |
| `enabled` | True | :62 | overridden by the property |
| `profile_cache_ttl` | 30.0 | :65 | live |

Six unconfigurable literals carry no config field: `0.5` wide-spread cut (`:311`), `0.1` fabricated-depth factor (`:335-336`), `0.02` thin-market cut (`:340`), `10` average-trade multiplier (`:371`), `50` chunk cap (`:434`), `10` slippage clamp (`:461`). Plus the five tier trade-counts at `:161-167`. Not one value in the module carries a source, a backtest, or an exchange rule.

**Emitters: NONE.** `grep -rn "emit\|signal_contract" src/trading/volume_guard.py` returns no match. `grep -n "volume_guard" src/core/emit_contracts.py` returns no match. All observability is `logging` on the `acervator.execution` logger (`:27`), at seven sites — warnings `:246`, `:346`, `:600`, `:615`; info `:257`, `:573`; debug `:596`. Every one sits inside the unreachable branch. `src/trading/bot_container.py` imports `signal_contract` zero times, so the order funnel itself is un-emitted.

---

## 3. How it is reached, and how it is bypassed

**The order path is a single funnel.** Every live order goes through `BotContainer.guarded_place_order` (`bot_container.py:996`). Ten call sites reach it:

- `scrumming_bot.py:3171` `self_destruct` — MARKET SELL, full holdings
- `scrumming_bot.py:9932` `_execute_manual_rebalance` SCRUM branch — Manual Fire
- `scrumming_bot.py:10197` same method, FOLD branch — Manual Fire
- `scrumming_bot.py:10700` `_execute_detonation` — MARKET SELL
- `scrumming_bot.py:10955` `_open_stack_from_scrum` — LIMIT or IOC_LIMIT
- `scrumming_bot.py:11378` `_execute_sell`
- `scrumming_bot.py:11984` `_execute_buy`
- `extractor_bot.py:1018`, `:1218`, `:1379` — all MARKET (`ExtractorBot` inherits the funnel)

Inside the funnel: min_amount / min_cost pre-flight (`bot_container.py:1030-1074`), guard-branch test (`:1080`), idempotency coid (`:1118-1129`), `exchange.place_order` (`:1133`).

**The bypass is the guard branch itself.** `if self._volume_guard and self._volume_guard.enabled:` is False for every order, so every order falls through to the direct path. This is not runtime state. No config key, no GUI toggle, no environment variable, and no caller exist. Re-enabling requires editing `volume_guard.py:190`.

**Nothing observes the disable.** `get_status():667` reports `"enabled": self.config.enabled` (`:674`) — that is `True`. Its three reporting methods (`:667`, `:688`, `:712`) have zero callers repo-wide. `grep -rn "volume_guard\|VolumeGuard" src/gui/` returns nothing. A status surface, if one existed, would therefore report the guard as ON while it is OFF.

**Correction to the task brief.** `src/exchange/base.py:125` and `src/exchange/ccxt_connector.py:1102` are not the disable path. They are prose about the `Balance.absent` flag for the phantom-rebuy fix. Neither file references VolumeGuard in code. The disable is one line: `volume_guard.py:190`.

**Second bypass, latent.** If the branch were re-enabled it would `return` at `bot_container.py:1093-1106`, before the idempotency block at `:1118-1129`. Every order would ship with `client_order_id=None`, disabling the TD-004 double-fill protection described at `base.py:217-228`.

**Third bypass, latent.** `_execute_iceberg` calls `exchange.place_order` directly (`volume_guard.py:580`). Chunks never re-enter the funnel, so no chunk is re-checked against min_amount or min_cost.

**Sim and live take the same branch.** Sim bots hold `_volume_guard = None` (`bot_container.py:924`; `set_volume_guard` is never called on the sim's private manager). Live bots hold a guard reporting `False`. Both fail the test at `:1080`. VolumeGuard is not a sim-versus-live asymmetry today.

---

## 4. Gaps

### Missing

- **No emitters.** Confirmed by grep, and by absence from `emit_contracts.py`.
- **No refusal path.** Trace every exit of `execute()`: disabled places, not-tradeable places, within-limits places, above-limits places. The only non-placing exit is "no exchange connector" (`:233-240`). The guard cannot say no.
- **No abort on slippage.** `max_slippage_pct` appears at exactly three lines: the definition (`:48`), a spread test at twice its value on every sixth chunk (`:614`), and the status dict (`:684`). `plan.estimated_slippage_pct` is computed at `:456-463` and read only by a log line (`:576`) and a report field (`:637`). The config comment at `:47` promises "abort if estimated slippage exceeds this". That behaviour does not exist.
- **No participation gate.** `hourly_budget_remaining` is written at `:293` and `:386` and read at `:704` — a UI dict. No branch consults it.
- **No volatility.** `MarketProfile` (`:73-104`) has no volatility field, so no dimensioned impact estimate is possible.
- **No deadline.** The iceberg loop (`:578-621`) has no elapsed-time check.

### Wrong

- **FAIL-OPEN on a money path.** Any profiling exception sets `is_tradeable = False` (`:345-347`); `execute()` then routes the order through unguarded, with the verbatim comment `# Still allow the trade but log warning` (`:249`). The failed profile is cached at `:349`, so the next 30 seconds of orders on that symbol take the same unguarded path without retrying.
- **Silent depth fabrication.** When `get_orderbook` raises, a bare `except Exception` substitutes `volume_hourly_est * 0.1` for both sides (`:333-336`). It logs nothing. `MarketProfile` has no field marking depth as estimated. That fabricated number then feeds `book_limit_quote` (`:363-364`) and the slippage estimate (`:457-460`).
- **`is_tradeable` is a tautology.** `not profile.low_volume or profile.volume_24h_quote > 0` (`:316`) is True for any positive volume. `min_daily_volume_usd = 1000.0` gates nothing; it only selects the wording of a log line at `:248`.
- **The 50-cap widens chunks.** `n = min(n, 50)` (`:434`) is followed by `chunk_base = amount / n` (`:435`). When the cap binds, each chunk exceeds the safe size the module just derived. No post-cap assertion exists anywhere in `:403-474`. (Below the cap the headroom still holds: `n >= amount/(0.7·safe)` implies `amount/n <= 0.7·safe`.)
- **The mid-iceberg abort is dead.** `:612` calls `self._get_market_profile(symbol)` with no exchange argument. `:287` falls back to `self._exchange`, which is None: `main.py:748` builds `VolumeGuard(config=VolumeGuardConfig())` with no exchange, and `set_exchange():178` has zero callers. The ticker call therefore raises, the profiler's own handler swallows it (`:345`), `fresh.spread_pct` is 0, the abort never fires, and the dead profile is cached — turning a safety check into a 30-second guard bypass.
- **Status counters are structurally zero.** `:669-670` filters with `time.time() - r.execution_time_ms / 1000 < 3600`. `execution_time_ms` is a duration assigned from `(time.monotonic() - start) * 1000` (`:494`, `:531`, `:623`). `ExecutionReport` has no timestamp field (`:120-137`). The left side is about 1.8e9. `recent_executions` and `iceberg_executions` are permanently 0. This is the exact "a zero is a claim about the instrument" case.
- **Delay comment contradicts the code.** `:447` claims "at $10K/hr, ~3000ms". Trace it: `volume_factor = 0.1`, floored to 0.5 by `:449`, `5000/0.5 = 10000 ms`, clamped to 5000 ms.

### Dead

`get_volume_guard():737` — zero callers; `_instance` is never populated. `set_exchange():178` — zero callers. `_compute_chunk_plan` `:428-431` — unreachable after the `:417` guard. The `# sadp: R28 R29` markers at `:204`, `:483`, `:520`, `:561` reference a deprecated scheme.

### Untested

178 test files in `tests/`. The only mention of the module is a comment at `tests/test_manual_fire_settled_fill.py:23`. The two regression pins named in archive documents — `tests/test_exchange_path_verification.py` and `tests/test_volume_guard_is_a_noop.py` — do not exist. Nothing goes red if someone edits `volume_guard.py:190`.

### Harness output (run this session)

`python -m tools.harness.coding_archetype src/trading/volume_guard.py` → **exit 1, `passed: false`, 118 findings** (ruff 81, mypy 18, vulture 11, pyright 7, bandit 1; severity: 1 high, 31 medium, 82 low, 4 info).

`python -m tools.harness.coding_archetype src/trading/smart_orders.py` → **exit 1, `passed: false`, 88 findings** (3 high).

**REAL (act on these):**

| finding | line | why real |
|---|---|---|
| `S110` + `B110` try-except-pass (the only high) | :618 | This is the handler that hides the dead mid-iceberg abort. |
| `BLE001` × 6 blind excepts | :333, :345, :504, :545, :599, :618 | Two of these (`:333`, `:618`) destroy information on a money path; `:345` inverts fail-closed. |
| `vulture` unused method `execute` | :200 | Independent confirmation the algorithm is unreachable. |
| `vulture` unused `get_status`, `get_market_profile`, `get_execution_history`, `get_volume_guard` | :667, :688, :712, :737 | No consumer for any telemetry. |
| `vulture` unused attributes `bid_depth_levels` / `ask_depth_levels` | :92, :93, :331, :332 | The module records how many book levels it read and never uses it — the field that would prove depth is real. |
| `pyright reportOptionalMemberAccess` × 5 | :301, :325, :491, :528, :580 | `"get_ticker"/"get_orderbook"/"place_order" is not a known attribute of "None"` — the type checker independently found the None-exchange defect. |
| `PLR2004` magic values | :311, :391-397, :467, :469 | The tier boundaries and the reason thresholds, all unsourced. |
| `RUF012` mutable class attribute | :161 | `TRADES_PER_DAY_EST` — the constant table that causes the tier inversion. |
| smart_orders 3 × `S110` high | :373, :389, :431 | Same class, in a module with zero importers. |

**NOISE (do not act on):** `ANN001`/`ANN201`/`ANN202`/`ANN204` (missing annotations, 11 sites), `mypy no-untyped-def` × 11, `E501` line length × 8, `D2xx`/`D4xx` docstring style × 11, `TID252` relative imports × 6, `UP045` `Optional` syntax × 3, `RUF001` ambiguous Unicode × 3, `I001` import sort × 3, `N817` acronym import alias × 3, `COM812` trailing comma, `PLR0913`/`PLR0917` argument counts × 8. These are style. They do not describe a defect in behaviour.

**One borderline:** `PLC0415` × 3 (`:485`, `:522`, `:563`) — imports inside function bodies. Style, but they hide the `OrderSide`/`OrderType` coupling; fix them while rewriting those functions.

**What the harness did NOT find, and cannot:** the fail-open, the fabricated depth, the tautology, the cap-then-widen, the duration-as-timestamp, the split authority, and the dead abort. Static tools cannot catch runtime semantics. That is why the rebuild starts with emitters.

---

## 5. What the research says the arithmetic should be

**Fetch status, stated once.** I did not fetch any external page in this session. Every external figure below comes from the research pass and was checked by the adversarial verifier against the source. I mark all of them **HYPOTHESIS** for the purpose of this plan, and §8 Stage 0 replaces every one with a measurement on Acervator's own fills. No unfetched constant goes into a money path.

**HYPOTHESIS — the square-root law.** Metaorder impact fits `I(Q) ≈ Y · σ · (Q/V)^δ`, where σ is daily volatility and V is daily volume, both contemporaneous. Reported: δ ≈ 0.5 on Bitcoin over four decades of size with Y ≈ 0.9 (Donier & Bonart, MtGox, `https://arxiv.org/pdf/1412.4503`); δ = 0.500 ± 0.0020 on a whole-exchange survey (`https://arxiv.org/html/2411.13965v1`); δ = 0.600 ± 0.038 on US equities (Almgren et al., `https://www.cis.upenn.edu/~mkearns/finread/costestim.pdf`).

**What it implies for the 25% book-depth default.** No fetched source contains a fraction-of-visible-book participation rule. The rule appears to be invented. Three reasons it is the wrong instrument:

1. Most liquidity is latent. Toth et al. (`https://www.cfm.com/wp-content/uploads/2022/12/76-2011-anomalous-price-impact-and-the-critical-nature-of-liquidity-in-financial-markets.pdf`) estimate the visible book at about 1% of a day's flow. Sizing against the visible book measures the tip.
2. The code sums 20 **levels** (`volume_guard.py:326-330`). Tick size differs per pair, so 20 levels spans a different price distance on every symbol. The number is not comparable across the fleet.
3. Kaiko documents that a widely used depth level was gamed by exchanges (`https://www.kaiko.com/resources/understanding-centralized-exchange-liquidity-data`). A visible-book number is manipulable by a counterparty.

Obizhaeva & Wang show the correct use of depth: `P(x) = A + x/q`, where q is depth per unit price — a slope, not a budget to spend 25% of.

**What it implies for the 1% slippage default.** Two problems, one of which is internal and needs no citation.

*Internal:* `plan.estimated_slippage_pct = (quote_value / relevant_depth) × 100`, clamped to 10 (`:460-461`). That is the fraction of visible depth consumed, expressed as a percent. It is a fill ratio, not a price move. It has the wrong unit. An order equal to the visible book reads 10 after the clamp.

*Against the model:* at Y = 0.9 and σ = 5%, a 1% price move needs `Q/V = (0.01/0.045)² = 4.9%` of daily volume. The module's own single-order cap is 0.1% of daily volume (`:39`). The abort threshold sits about 50× beyond the cap that binds first. The two defaults are mutually inconsistent by roughly a factor of 50. At the 0.1% cap the model predicts about 14 bp of impact.

For calibration: Almgren et al. excluded orders below 0.25% of average daily volume as too small to measure impact on. VolumeGuard's cap sits below the floor at which published equity work could detect impact at all.

**What it implies for the participation limit.** `max_hourly_participation_pct = 0.02` is the one parameter with literature in its neighbourhood, and it is dead code. Published anchors: Zarinelli et al. discard metaorders above 30% participation as outside the credible band (`https://arxiv.org/pdf/1412.2152`); Donier & Bonart note participation rarely exceeds 20–30%; Interactive Brokers exposes the POV rate as a free fraction bounded by 1, with 5% as its worked example (`https://ibkrguides.com/traderworkstation/fox-pov.htm`).

**What it implies for scheduling.** Almgren & Chriss (`https://www.smallake.kr/wp-content/uploads/2016/03/optliq.pdf`) give the closed form. For the constant-rate path, expected cost scales as `X²/T` and variance as `T`; the chunk count N enters only through `(1-1/N)(1-1/(2N))`, which is nearly flat past a handful of chunks. **Read that carefully: fast-versus-slow is first-order, many-small-versus-few-large is second-order.** VolumeGuard tunes the second-order knob and leaves the first-order one unbounded.

**What it implies for Acervator's venue.** Coinbase Advanced Trade's documented `order_configuration` keys are `market_market_ioc`, `market_market_fok`, `limit_limit_gtc/gtd/fok`, `sor_limit_ioc`, `stop_limit_*`, `trigger_bracket_*` (`https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/guides/orders`). No iceberg key, no hidden-quantity key, no TWAP key. Binance exposes `icebergQty` and Kraken exposes `displayvol` with a 1/15-of-volume floor. On Acervator's venue a client-side chunker is therefore the only path — and Kraken's 1/15 floor is a venue-set precedent of about 15 slices against VolumeGuard's arbitrary 50.

**HYPOTHESIS — detection.** Zotikov (`https://arxiv.org/pdf/1909.09495`) detects a client-side iceberg from three joint conditions: a refill within a short delay, at the same price level, with volume equal to the initial tranche. The paper states it cannot detect one with varying peak sizes or price levels. VolumeGuard builds `chunks = [chunk_base] * n_chunks` (`:437`) at one fixed delay — the exact detectable signature.

**The one number that is not a hypothesis.** `trading_fee_pct = 0.6` (`bot_container.py:345`), documented there as the Coinbase Advanced Trade max-tier fee. A round trip costs 120 bp. The hysteresis floor is `interval + fee` = 1.6%. Set the modelled impact against that: a $2 fire on a $1M/day alt is about **0.64 bp**, or 0.5% of the trade's own fee cost. A $200 full exit into a $200k/day book at σ = 8% is about **23 bp**, or 19%. The first is noise. The second is worth a guard.

---

## 6. Adversarial review

**FATAL — The guard does not trip at routine Acervator order size.**
Evidence: §1 crossover table, derived from `volume_guard.py:352-377` and `:161-167` against `scrumming_bot.py:6469`/`:7699` and `bot_container.py:101`/`:134`. A $2 fire needs a sub-$2,000/day market. Consequence: any plan that funds full chunking machinery for routine trading funds a no-op. The plan in §8 shrinks accordingly — chunking survives only for full-position exits, and capped low.

**FATAL — Chunking pays no fee saving and buys time risk.**
Evidence: `trading_fee_pct = 0.6` is a percentage of notional (`bot_container.py:345`), so N chunks pay the same total as one order. The delay is pinned at the 5000 ms ceiling for every market under $2.4M/day (`:445-454`), which is the only band where the guard trips at all. A 3-chunk plan is 10 s of exposure (5.4 bp of one-sigma drift at σ = 5%); the 50-chunk cap is 245 s (26.6 bp). Consequence: chunk counts must be small and the horizon must be bounded, or the guard loses more than it saves. *The fee-proportionality claim is HYPOTHESIS — I did not fetch Coinbase's fee schedule.*

**FATAL — The chunker manufactures the API spam the funnel exists to stop.**
Evidence: the pre-flight validates the whole amount (`bot_container.py:1030-1074`) under a verbatim operator directive quoted at `:1011` — "We should not be spamming the APIs with improperly valued orders." `_execute_iceberg` calls `exchange.place_order` directly (`volume_guard.py:580`) and continues after failures (`:599-603`). A $25 order split 50 ways produces $0.50 chunks, all below min_cost, all rejected, 50 API calls burned. Consequence: chunk re-entry into the funnel is a precondition for enabling chunking at all, and once min_cost binds the chunk count is bounded by the venue, not by the guard's own maths.

**SERIOUS — Acervator already ships a better splitter for its own strategy.**
Evidence: `_open_stack_from_scrum` (`scrumming_bot.py:10879-10970`) splits a scrum into tranches spaced by **price**, with a fee-aware floor `min_opposing_pct = interval + fee` (`:10901-10905`), each placed through `guarded_place_order` (`:10955`). Consequence: for a bot that profits from volatility, price-spaced tranches capture the move; time-spaced chunks at one price are designed to fill at the same price, which is the opposite of what a Scrum wants. Do not present VolumeGuard's iceberg as an accumulation feature. It is a market-impact tool for exits.

**SERIOUS — Profiling adds an uncoalesced API class the budget may not have.**
Evidence: the connector enforces `_min_request_interval = 0.1` and a single-worker executor, and `_get_market_profile` calls `get_ticker` (`:301`) and `get_orderbook` (`:325`) directly rather than through the shared `MarketDataPool` that `ScrummingBot` uses. `get_orderbook` has exactly one consumer in live `src/` — `volume_guard.py:325` — so there is no orderbook cache. Consequence: Stage 0 must measure the call cost before Stage 3 turns profiling on. *Marked SERIOUS not FATAL because the 30 s profile cache (`:65`, `:291`) and the low trip rate bound the exposure — but neither is measured.*

**SERIOUS — Re-enabling silently breaks three live protections.**
Evidence: the guard branch returns at `bot_container.py:1093-1106`, before the idempotency block at `:1118-1129` (every order ships `client_order_id=None`); the synthetic id `vg_<ms>` at `:1094` is stored as an exchange order id by the stack reconciler (`scrumming_bot.py:10963`) and fed to `exchange.get_order` (`:11038`); `bot_container.py:1082` flattens the order type to `"market"`/`"limit"` and `volume_guard.py:488`/`:525`/`:566` map it back, so `OrderType.IOC_LIMIT` becomes a resting LIMIT and the `timeInForce=IOC` translation at `ccxt_connector.py:1221-1224` never fires. Aggressive Trading selects IOC_LIMIT at `scrumming_bot.py:10938-10940` precisely for taker execution. Consequence: these are prerequisites, not follow-ups.

**SERIOUS — No positive control exists for the claim "the guard never fired".**
Evidence: zero emitters; three zero-caller reporting methods; `recent_executions` structurally 0 (`:669-670`). Consequence: "the guard never mattered" is currently a statement about the absence of instrumentation. Stage 0 exists to make it a statement about the world.

**MANAGEABLE — The fill-fabrication `or` chains.**
Evidence: `volume_guard.py:493`, `:530`, `:585` use `order.average or price or …` and `order.filled or amount`. `tests/test_manual_fire_settled_fill.py:1-26` names those lines. Consequence: the root cause — `_parse_order` never populating `Order.average` — is **already fixed** (`ccxt_connector.py:1402-1414` now sets it). These lines are latent, not losing money, and they are in dead code. Fix them during the rewrite. Do not report them as an active loss.

**MANAGEABLE — The 50-cap widening.**
Evidence: `:434-435`, no post-cap assertion in `:403-474`. The cap binds only above about 35× the safe size — over $23,000 on a $1M/day alt. Acervator order sizes do not reach that. Consequence: real defect, latent blast radius. Fix by refusing or raising the count. Never widen.

**MANAGEABLE — smart_orders cannot be wired without a new bypass.**
Evidence: it calls `exchange.create_order` (`smart_orders.py:249`, `:280`, `:322`, `:359`, `:392`), `fetch_ticker` (`:207`, `:418`), `fetch_order` (`:369`). `ExchangeInterface` declares none of those (`base.py:183-272`: `get_ticker`, `get_orderbook`, `get_ohlcv`, `get_balances`, `get_balance`, `place_order`, `cancel_order`, `get_order`, `get_open_orders`, `get_markets`). An adapter would route future callers around the circuit breaker, the IOC translation, and the coid contract. Consequence: delete, do not wire. See §7.

---

## 7. The design

**What the built-out guard is:** a market-impact refusal gate that sits inside the order funnel, observes everything, and blocks a small number of large exits into thin books. It is not an execution-algorithm framework.

### The smart_orders question — settled: DELETE

`src/trading/smart_orders.py` has **zero importers**. The four files that mention it (`capital_reservation.py:33`, `extractor_bot.py:312`/`:488`, `scrumming_bot.py:11222`/`:11235`/`:11291`) mention it only in prose. It cannot be wired without a raw-ccxt adapter that creates a second route around the connector's protections. Its three strategies fabricate fills (`:288`, `:330`, `:398` — where `total_filled = filled + remaining` always equals the request, and `:403` returns `success=True` unconditionally).

- **TWAP:** do not absorb. §5's cost/risk arithmetic says a multi-minute schedule is a first-order risk increase for a second-order cost saving, and §1 says the fleet's sizes never justify it.
- **ADAPTIVE picker:** do not absorb. The new guard has one decision function; a strategy picker adds a branch with nothing to pick between.
- **LIMIT_TIMEOUT:** name it and queue it. It is a genuine gap — no module in the repo posts a limit and cancels on a deadline. But it belongs to the order-placement layer, not to a volume guard. Separate arc.
- **The capital-reservation pre-flight (`:143-203`):** absorb the *intent*, and put it in the **funnel**, not in the guard. Reason: a check inside `execute()` disappears whenever the guard is off — which is exactly how this one got stranded. `capital_reservation.py:33-35` declares an "execution-level" layer that has never run. `registry.effective_available()` is called from exactly one of ten order sites (`scrumming_bot.py:11265`, inside `_execute_sell`), and Manual Fire bypasses the decision gates by design (`scrumming_bot.py:11176`, `:11598`, `:11764`). Manual Fire therefore has no reservation enforcement at any level today. Move the check to `guarded_place_order` beside the min_amount pre-flight, and make it fail-closed. Today the two handlers each defer to the other: `smart_orders.py:184-194` says the decision gate is still in effect; `scrumming_bot.py:11291-11296` says the smart_orders backstop is still in effect. One is dead. The repo has the right precedent twelve lines away — `scrumming_bot.py:11305-11313` refuses when `get_open_orders` raises.

Then delete the file.

### Invariants

| # | Invariant | ENFORCED by | OBSERVED by |
|---|---|---|---|
| 1 | The state the dispatch point reads equals the configured state | One arming record; the property and `execute()` read the same field; delete the duplicate check at `:228` and the setter at `:192-196` | `volume_guard.armed` — `actual` = state read at `bot_container.py:1080`, `expected` = configured state, on every order |
| 2 | A disarmed guard still observes | Disarm sets `blocks = False`; it never skips profiling, estimation, tracking, or history (today disabled routes to passthrough at `:229-230` and skips `:273-278` entirely) | `volume_guard.decision` emits `pass_disarmed` with the full estimate attached |
| 3 | Disarm expires | The record carries `expires_at`; the guard re-arms itself on expiry | `volume_guard.armed` context carries `reason`, `actor`, `expires_at`; a FAIL line writes on every order while disarmed |
| 4 | Depth is measured or the order is refused | Delete the fabrication at `:333-336`; add `depth_source` to `MarketProfile`; refuse when it is not `orderbook` | `volume_guard.profile` — `actual` includes `depth_source` and `levels_in_band`, `expected` `depth_source == "orderbook"` |
| 5 | A profile failure refuses, and is never cached | Move the cache write out of the exception path (`:349`); replace the passthrough at `:250-251` with a raise | `volume_guard.profile_fetch` — `actual` = `"ok"` or the exception class |
| 6 | The estimate has a price unit | Replace `(quote/depth)*100` (`:460`) with a book walk: integrate the retained ladder to the order size, report `VWAP_walk/mid - 1` | `volume_guard.impact_estimate` — `actual` = walk impact %, `expected` = `max_impact_pct`, `ok` = `actual <= expected` |
| 7 | The estimate is compared to the budget, and the guard can refuse | A refusal raising `GUARD REJECTED:` through the funnel, mirroring `PRE-FLIGHT REJECTED:` at `bot_container.py:1056-1060` so all ten call sites' existing `SELL FAILED` / `BUY FAILED` handlers catch it unchanged | `volume_guard.decision` — `actual` ∈ {`pass`, `single`, `chunk`, `refuse`, `halted`} |
| 8 | The permitted size never falls when liquidity rises | Delete Method 3 and `TRADES_PER_DAY_EST`; delete the `0.01` floor at `:376` so the guard can conclude "do not trade" | `volume_guard.safe_size` — `actual` = `{book_limit, impact_limit, chosen, binding}`; `binding` names the winning limb, so a limb that never binds is visible in one query |
| 9 | No chunk exceeds the safe size | When the cap binds, refuse or raise the count; assert `max(chunks) * price <= safe_quote` before executing | `volume_guard.chunk_plan` — `actual` `{n_chunks, max_chunk_quote, horizon_s}`, `expected` `{max_chunk_quote <= safe_quote, horizon_s <= max_execution_seconds}` |
| 10 | Execution is bounded in time | `max_execution_seconds` in config; `delay = horizon / (n-1)`; deadline check at the top of each loop iteration | `volume_guard.deadline` — `actual` = seconds remaining |
| 11 | Chunks get the same protections as a whole order | Each chunk re-enters `guarded_place_order` with its own coid and the unflattened `OrderType` | `volume_guard.reentry` — `actual` `{path, coid_present, order_type}`, `expected` = the caller's `OrderType` |
| 12 | An unknown fill is not a full fill | Replace `order.filled or chunk_amount` (`:585`, and `:497`, `:538`) with `order.filled if order.filled is not None else 0.0`; stop after two consecutive zero-fill chunks | `volume_guard.chunk_fill` — `actual` `{filled_known, filled}`, `expected` `{filled_known: True}` |
| 13 | A repeatedly failing symbol halts | Reuse the existing `CLOSED/OPEN/HALF_OPEN` machine (`src/exchange/circuit_breaker.py:93-143`), keyed per symbol, opened on guard-relevant failures — not on transport failures | `volume_guard.halt` — emitted on **every** consultation while halted, so a latch cannot be forgotten. No environment-variable bypass. |
| 14 | Realised slippage is compared to the prediction | Log `(predicted, realised, Q, V, σ, duration)` per fill | `volume_guard.slippage_realised` — this is also the training signal that fits Acervator's own coefficients |
| 15 | A sell never exceeds the reservation ceiling | The pre-flight in the funnel, fail-closed, on all ten sites | `volume_guard.reservation_preflight` — `actual` `{requested, effective_available, registry_ok}` |

Use `src.core.signal_contract.emit(name, actual, expected, ok, context, every, module)` (`signal_contract.py:507-511`). The live process sink installs at `main.py:610-611`, so these record in production.

**Every emitter needs a positive control before it counts as an instrument.** `get_status()` proves why: it reports a hard zero for activity because it subtracts a duration from wall-clock time. Each emitter in the table gets a paired test that makes it emit `ok=False` on demand. An emitter that cannot be made to fail is not evidence.

### The disable path

Replace the hardcoded `return False` (`:190`) **and** the duplicate `config.enabled` check (`:228`) with one record:

```
{state: armed|disarmed, blocks: bool, reason: str, actor: str, set_at: float, expires_at: float}
```

One authority. No indefinite disarm. A FAIL emitted on every order while disarmed. Disarm means "does not block", never "does not observe". That is the difference between a guard that is off and a guard that is blind — and it is what makes re-arming a decision backed by data.

### Also remove in the same change

`get_volume_guard():737-744` (zero callers), `set_exchange():178-180` (zero callers — the root cause of the dead abort), the unreachable branch at `:428-431`, the stale `# sadp:` markers at `:204`/`:483`/`:520`/`:561`, and the three function-body imports at `:485`/`:522`/`:563`.

---

## 8. Implementation plan

Island discipline throughout: edit and test on an isolated hard copy, promote only after `python -m tools.harness.check_release_readiness` reports `[OK] Release-ready`. Run `python -m tools.harness.coding_archetype` on every file touched and compare against this session's baseline (volume_guard 118 findings / 1 high; smart_orders 88 / 3 high), not against zero.

### Stage 0 — The census. The cheapest measurement that can kill the plan.

**Ships:** a read-only script that, for each live symbol, fetches the ticker and the orderbook, and joins them against the fleet's real order sizes from a `bot_state` load. For every historical fire in the trade record it computes: order quote value Q, 24h volume V, the safe size the current code would have produced, the book-walk impact, and whether the guard would have tripped.

**Files touched:** one new file under `tools/`. No `src/` changes. No live behaviour change.

**Test:** the script runs against a fixture book and produces the known trip decision for a hand-computed case.
**Positive control:** feed it a synthetic order at 5% of daily volume and assert a non-trivial impact; feed it one at 1e-6 of daily volume and assert near zero. An instrument that returns the same number for both is broken and Stage 0 stops.

**Emitter:** `volume_guard.census` — `actual` `{symbol, Q, V, safe_now, walk_impact_pct, would_trip}`, `expected` `{would_trip: false}`, one record per historical fire.

**Also measure here:** the API cost. Time 37 `get_orderbook` calls through the connector's rate limiter and record the queue depth. This is the SERIOUS attack in §6 and it must have a number before Stage 3.

**Exit criterion:** a distribution of `would_trip` across real fires and real books.
**Kill condition — state it now:** if fewer than 1% of historical fires would trip at a corrected safe size, **stop after Stage 2**. Ship the emitters and the arming record, leave the guard disarmed, and delete the chunker. That outcome is a success, not a failure.

### Stage 1 — Instrument the funnel. No behaviour change.

**Ships:** `signal_contract` emitters at the order funnel. `volume_guard.armed` on every call at `bot_container.py:1080`. `volume_guard.reservation_preflight` in shadow mode — compute `effective_available` on every sell at all ten sites and emit, but do not block.

**Files touched:** `src/trading/bot_container.py` (it imports `signal_contract` zero times today), `src/core/emit_contracts.py`.

**Test:** a fake bot places an order; assert both signals appear in the sink.
**Positive control:** set the arming record to `armed` in the fixture while the property returns `False`; assert `volume_guard.armed` emits `ok=False`. Today that mismatch is invisible.

**Exit criterion:** one live session's signal file shows a record for every order placed, and the reservation shadow shows how many sells would have been refused.

### Stage 2 — The arming record and loud disarm.

**Ships:** invariants 1, 2, 3. One authority. `execute()` and the property read the same field. Delete `:192-196`. Disarm keeps observing.

**Files touched:** `src/trading/volume_guard.py`, `src/trading/bot_container.py:1080-1106`.

**Test:** `tests/test_volume_guard_arming.py` — assert `guard.enabled`, `guard.config.enabled`, and `get_status()["enabled"]` all report the same value; assert a disarm without a reason or an expiry raises; assert an expired disarm re-arms.
**Positive control:** set a 1-second expiry, sleep past it, assert the state flips and a signal records the flip.

**Emitter:** `volume_guard.armed`.
**Exit criterion:** editing the arming default turns a test red. Today editing `:190` turns nothing red.

### Stage 3 — Honest measurement. Still no blocking.

**Ships:** invariants 4, 5, 8. Band-based depth (request more levels, keep those within X% of mid, record `levels_in_band`). `depth_source` on `MarketProfile`. The book walk replaces `(quote/depth)*100`. Delete `TRADES_PER_DAY_EST`, Method 3, and the `0.01` floor. Fix `is_tradeable`. Never cache a failed profile.

**Files touched:** `src/trading/volume_guard.py` only.

**Test:** `tests/test_volume_guard_sizing.py` — assert `safe_size(V)` is monotonic non-decreasing across the range $50k to $500M; assert the $7M / $9M / $11M case from §1 no longer trips-passes-trips.
**Positive control:** feed a book with a known ladder and assert the walk returns the hand-computed VWAP impact; feed an empty book and assert refusal, not a fabricated depth.

**Emitters:** `volume_guard.profile`, `volume_guard.profile_fetch`, `volume_guard.safe_size`, `volume_guard.impact_estimate`.
**Exit criterion:** one live session where the guard runs in observe-only mode and the emitted `would_trip` rate matches the Stage 0 census within a stated tolerance. **If it does not match, Stage 0's instrument was wrong and Stage 4 does not start.**

### Stage 4 — Refusal. The first stage that changes an outcome.

**Ships:** invariants 6, 7, 15. `GUARD REJECTED:` raising through the funnel. The capital-reservation pre-flight moved into `guarded_place_order`, fail-closed, out of shadow mode. Refuse on: impact above budget, depth not measured, profile unavailable.

**Files touched:** `src/trading/volume_guard.py`, `src/trading/bot_container.py`, `src/trading/capital_reservation.py` (docstring at `:29-35` — make it true), `src/trading/scrumming_bot.py:11291-11296` (delete the comment that names a dead backstop).

**Test:** each of the ten call sites, given a refusing guard, logs its failure and does not place. Assert `registry` raising on a sell produces a refusal, not a fall-through.
**Positive control:** a guard configured to refuse everything must produce zero `place_order` calls and ten `volume_guard.decision` records with `actual="refuse"`. A guard configured to refuse nothing must produce ten placements. Both directions must be demonstrable.

**Emitter:** `volume_guard.decision`, `volume_guard.reservation_preflight`.
**Exit criterion:** the refusal rate in a live session equals the Stage 3 observe-only prediction.

### Stage 5 — Chunking, capped low. Only if Stage 0 justified it.

**Ships:** invariants 9, 10, 11, 12. Chunks re-enter the funnel with their own coid and unflattened `OrderType`. A horizon-first schedule with a deadline. A chunk cap set from the venue's min_cost and the measured impact, not from the literal 50 — Stage 0's data sets it, and Kraken's 1/15 displayvol floor is the sanity anchor. Jitter on chunk size and delay.

**Files touched:** `src/trading/volume_guard.py`, `src/trading/bot_container.py:1082`/`:1093-1106`/`:1118-1129`.

**Test:** assert `max(chunk) <= safe_size` for every input including the cap-binding case; assert an `IOC_LIMIT` caller receives `IOC_LIMIT` chunks; assert every chunk carries a distinct coid; assert a plan exceeding the horizon reduces its chunk count.
**Positive control:** a stub exchange returning `filled=0` must produce `executed_amount == 0` and `success=False`. Today the `or` chain produces a full fill and `success=True`. Set jitter to zero and assert the shape emitter reports `cv=0` with `ok=False`.

**Emitters:** `volume_guard.chunk_plan`, `volume_guard.chunk_fill`, `volume_guard.reentry`, `volume_guard.deadline`.
**Exit criterion:** a chunked order in the Simulator produces identical gate latching to the unchunked path on the same data, and the realised-versus-predicted slippage record shows the chunked path did not cost more.

### Stage 6 — Halt and re-arm.

**Ships:** invariants 13, 14. A per-symbol breaker reusing `circuit_breaker.py:93-182`. Half-open promotion admits one probe at the smallest permitted size. No environment-variable bypass.

**Files touched:** `src/trading/volume_guard.py`.

**Test:** two consecutive chunk failures open the breaker; a cooldown admits exactly one probe; a good probe closes it.
**Positive control:** assert the halted state emits on every consultation, not once. A latch that stops emitting is a latch that gets forgotten.

**Emitters:** `volume_guard.halt`, `volume_guard.rearm`, `volume_guard.slippage_realised`.

### Stage 7 — Delete smart_orders.py.

**Ships:** the file removal, plus corrections to the four prose references (`capital_reservation.py:33`, `extractor_bot.py:312`, `:488`, `scrumming_bot.py:11222`, `:11235`, `:11291`) so no comment names a module that no longer exists.

**Test:** a grep test asserting no source file references `smart_orders`.
**Positive control:** the test must fail if the string is reintroduced.
**Exit criterion:** the release gate is green and the smart_orders archetype baseline (88 findings, 3 high) drops out of the harness entirely.

---

## 9. Sequencing against other work

**Stage 1 goes first, before the Extractor rebuild and before any Grid bot.** It instruments `guarded_place_order`, which is the single funnel every bot's orders pass through — including the Extractor's three sites (`extractor_bot.py:1018`, `:1218`, `:1379`) and any Grid bot's future sites. `bot_container.py` currently imports `signal_contract` zero times, so the platform's only order gate emits nothing. Every later claim about any bot's order behaviour depends on that. **Stage 1 unblocks both.**

**Stage 4's reservation move also goes before the Grid bot.** A Grid bot places many orders on one asset. `effective_available` is called from one of ten sites today, and the "execution-level" layer declared at `capital_reservation.py:33-35` has never run. Adding a bot that shares assets with 35+ others, on top of an enforcement layer that covers 10% of order sites, is a known failure waiting for a schedule. **Stage 4 unblocks the Grid bot.**

**Stages 3, 5, 6 sit behind the Extractor rebuild.** The Extractor is not release-ready for architectural reasons — asset sharing and bot stand-down. Its three order sites are all MARKET and all full-size corrections, which is exactly the regime where a working impact guard earns its keep. But sizing machinery for a bot whose sizing is being redesigned is wasted work. **The Extractor rebuild blocks Stages 5 and 6.** Stage 3 can proceed in parallel because it changes no behaviour.

**Nothing here blocks the Simulator parity arc.** VolumeGuard is not a sim-versus-live asymmetry today: sim bots hold `None` and live bots hold a guard reporting `False`, and both take the same else-branch at `bot_container.py:1080`. Stage 5 is the first stage that could create an asymmetry, so gate-latch parity must be re-verified there and nowhere earlier.

**Where this belongs in the queue:** Stage 0 and Stage 1 now — they are cheap, read-only or observe-only, and they unblock everything downstream. Stages 2–4 after. Stages 5–7 after the Extractor rebuild, and only if Stage 0's census says chunking has customers.

---

## 10. What this report does not settle

1. **The live fleet's real target balances.** I used the code default `target_balance = 200.0` (`bot_container.py:101`). The live values come from a `bot_state` load, which I did not read (runtime paths are out of scope for this pass). `src/trading/asset_target_defaults.json` is **not** the fleet's targets — its own `_meta` scopes it to new bots created via a topology-proposal Adopt handoff, and its only consumer is `topology_proposals.py`. Targets also grow through profit-fold. Stage 0 must read the real values. Every crossover in §1 scales linearly with them.

2. **The traded pairs' real 24h volumes and book depths.** No number in this report came from a live market. The claim "no Coinbase pair in the fleet trades under $2,000/day" is an inference, not a measurement. Stage 0 measures it.

3. **Every external constant.** I fetched nothing this session. Y ≈ 0.9, δ ≈ 0.5, the 20–30% participation ceiling, the Kaiko band convention, Kraken's 1/15 floor, the absence of an iceberg key on Coinbase Advanced Trade, and Coinbase's fee proportionality are all **HYPOTHESIS**. The design in §7 deliberately depends on none of them: the book walk needs only the ladder Acervator already fetches.

4. **Whether market impact has ever cost Acervator anything.** No fill record has been compared against a prediction. That is the honest question underneath the operator's request, and Stage 0 plus Stage 3's `slippage_realised` record answer it. Until then, "the guard would have helped" is unfalsifiable.

5. **The API budget for profiling.** `get_orderbook` has exactly one consumer in live `src/` and no shared-pool entry. Stage 0 must time it. If 37 uncoalesced orderbook fetches do not fit the connector's serialized queue, Stage 3 needs a pool entry first and this report does not design one.

6. **What the operator wants disarm to mean.** §7 proposes that a disarmed guard still profiles, estimates, and emits. That costs API calls on a path that blocks nothing. It is the right default for building evidence, and it may be the wrong default for steady state. Operator decision.

7. **Limit-with-timeout.** Named as a real gap in §7 and explicitly not scoped here. No module in the repo posts a limit and cancels on a deadline. It needs its own arc.

8. **Nothing was executed against live state.** Every codebase claim is static reading plus two harness runs. No test suite was run. No `~/.acervator` path was touched.