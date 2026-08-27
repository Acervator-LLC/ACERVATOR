# Acervator Review — Simulator + Nuclear 2.0 Pass, and Codebase/Optimization Audit

**Repo:** `acervator_session25_CLOSE_hop5_v3_15_27` · v3.24.31 · 1098 tests green
**Date:** 2026-08-05

**Evidence legend** — every item below cites `file:line` from code that was read.
- **[V]** = a second verifier re-derived the claim from source; where the verifier issued a CORRECTION, the corrected version is what appears here.
- **[1P]** = single-pass finding: cites checked by the author, no independent re-derivation. Treat quantitative claims in **[1P]** items as *unmeasured* unless a measurement is explicitly named.

---

## DO THIS FIRST (6 items, both parts)

| # | Action | Why first | Refs |
|---|---|---|---|
| 1 | Seed sim wallets **per quote currency**, not all under `"USD"` | 10 of 35 bots (29% of the fleet) fired **0 trades** in the last real replay. Every backtest result on record is invalid for those symbols. | `fleet_replay_controller.py:511`, `sim_exchange.py:100-101` |
| 2 | Stop hand-enumerating sim bot config; pass every `BotConfig` field through, and drive `fee_pct` from it | `trading_fee_pct=1.6` on 24/35 bots silently reverts to `0.6`, and the sim charges **zero** fees. Both bias the exact metric the harness measures. | `fleet_replay_controller.py:150`, `:512` |
| 3 | Give the sim its own `FeatureTelemetry` instance/path | Every replay — including cancelled ones — writes `~/.acervator/feature_telemetry.json` and `~/.acervator_logs/feature_validation.md`. Both files are on disk right now, timestamped 2026-08-05 10:16:26, produced by a sim run. Direct breach of the isolation directive. | `fleet_replay_controller.py:779`, `:784` |
| 4 | Nuclear scout: add `sim_mode=True`, `capital_registry=<private>`, `enable_phantoms=True` | The only GUI-reachable Nuclear path builds a bot that resolves the **live** capital registry and runs with a whole subsystem switched off. | `nuclear_controller.py:321` |
| 5 | Fix the two lying numbers in the Simulator panel: the coverage-table denominator, and the silent Fetch-YTD failure | The panel currently reports ~8.5% tablet coverage on perfectly current tablets, and reports the *previous* run's trade count as a fresh fetch result. | `fleet_replay_panel.py:750`, `:544` |
| 6 | Wire `CapitalReservationRegistry.prune_expired()` onto a timer in the live process | Zero callers repo-wide. It is the **only** automatic reclamation path, and orphans feed the over-commit gate that refuses live SCRUMs. | `capital_reservation.py:567` |

One-line follow-on worth doing in the same sitting: the Expand re-entrancy guard (`sim_visuals.py:43-102`) — two clicks permanently removes the chart from the Simulator tab with no recovery short of an app restart.

---

# PART 1 — SIMULATOR + NUCLEAR 2.0 PASS

## 1.0 — WHAT NUCLEAR MODE IS FOR (operator, 2026-08-07)

*Added because none of it was written down, and its absence was about to
produce wrong exit criteria for the C23 cascade.*

**Nuclear is an abuse instrument, not a measurement instrument. It is gated
BEHIND parity, and its trades are never validated against anything.**

> "Nuclear mode trades are not for validation against YTD data. They are meant
> to exercise the system brutally **after** it has been proven accurate by the
> YTD data and Stone Tablet simulated trade alignment that demonstrates
> identical (but not forced or form fitted!) trade logic behavior."

The ordering is a precondition:

1. **Fleet Replay** proves trade-logic alignment against YTD + Stone Tablets —
   gates latching identically on the same data. Earned, never forced or
   form-fitted.
2. **Only then** does Nuclear exercise the system brutally.

**This forbids:** comparing Nuclear trades to YTD or live trades, and writing
any Nuclear exit criterion in terms of trade match, P&L, or trade count.
Nuclear injects market noise *on purpose*, so its tape deliberately is not
history — trade-alignment comparison there is meaningless **by construction**.

**Nuclear's actual criteria** are coverage and survival: which declared
features were exercised, tranches fed, wires routed, swarm rows driven,
exceptions, throughput, data reliability under load. `nuclear_verification.py`
already models this correctly — `CoverageReport` measures "Which declared
features were actually exercised", and `unverified` states "Declared but never
exercised. **NOT the same as passing.**" Keep that framing.

*Verified 2026-08-07: Nuclear performs no parity/YTD comparison anywhere.*

## 1.0b — WHAT NUCLEAR MODE IS SUPPOSED TO DO (operator, 2026-08-07)

> "It is a special mode of the Simulator that attempts to abuse all aspects of
> the application. It **does not run on a single tape or stone tablet**. It runs
> stone tablets **in a loop** through the simulator bots. These loops are
> supposed to have **varied market structure via an oscillator that injects
> noise** to simulate varied market structures **without writing over the stone
> tablets**."

Subsystems it must exercise: Trades; Bot Swarm (Sim Swarm); Market Inspector
(Swarm Topology Proposal and Propagation); compounding (fold and stack
tranches); system performance and stability; data reliability under load.

**Two controllers exist — do not confuse them:**

| | Reachable | Tape model | Market noise |
|---|---|---|---|
| `nuclear_controller.py` (v1) — what the panel drives | **yes** | single tape A/B | **has** `NuclearCandleSource.reroll_noise` |
| `NuclearFleetController` (v2) | **no** — zero production callers (W3) | loops tablets across the fleet | **none** |

The single-tape design the operator objects to is **v1, and v1 is what runs**.
v2 has the loop-and-fleet architecture but the panel was never repointed at it.

**A gap in neither design doc, found 2026-08-07:** v2 never re-rolls market
noise. It loads tablets once (`nuclear_fleet_controller.py:283`) and hands the
same dict to every cycle (`:427`). Its oscillator is `SystemLoadOscillator` —
CPU load, **not** market structure. The noise machinery exists only in
`NuclearCandleSource.reroll_noise`, which only v1 uses. v2's loop therefore
varies *load* while replaying an identical tape. Wiring per-cycle noise into v2
is a **missing feature**, not a defect, and it is a precondition for the mode
doing what it exists to do.

**Operator directive on sequencing:** *"No need to fix the wrong design so fix
them first."* Design and missing features precede defect hardening — which is
also what D18 already says: fix those defects *as part of* the rewiring.

---

## 1a. Defects

### D1 — Ten USDC-quoted bots open with a $0 wallet and never trade **[V]**
**Symptom:** you run a 35-bot replay, it completes, `meta.json` says `"bots": 35`, and ten symbols show zero activity as if the market simply never triggered them.

`seed_usd` sums `target_balance` across *all* tableted bots ($3,300 total, of which $450 belongs to the ten USDC bots) but deposits the whole pot under one key:

- `fleet_replay_controller.py:511` — `starting_balances={"USD": seed_usd},`
- `sim_exchange.py:100-101` — `self._balances.setdefault(quote.upper(), 0.0)` → USDC opens at `0.0` with `absent=False`, so the MEM-254 absent-side handshake passes and nothing warns.
- `scrumming_bot.py:5596` reads `_get_balance(self.config.base_currency)` (= USDC) and the funding gate at `:5636` returns at `:5660` forever.

**Measured, not inferred:** run `20260805T045429_926437` (15,211 candles, 35 bots) logged 510 fills across exactly 25 distinct symbols, all USD-quoted. ADA/AERO/ALLO/HBAR/HYPE/LSETH/LTC/NEAR/WLFI/XLM — all `/USDC` — logged zero.

**Fix:** bucket `target_balance` by `base_currency` and pass a per-currency `starting_balances` dict. Then assert at the end of `_build_sim` that every instantiated bot's quote leg opened non-zero, with a loud `_activity()` line naming any underfunded bot.

### D2 — Sim bots are rebuilt from a 26-key whitelist; 44 of 70 live config keys are dropped **[V for `trading_fee_pct`; 1P for the wider census]**
**Symptom:** the sim fires opposing trades that the live bot would refuse, on 24 of 35 bots, for the whole replay.

`_instantiate_bot` hand-enumerates kwargs at `fleet_replay_controller.py:150-196` and never passes `trading_fee_pct`, so `BotConfig` falls back to `0.6` (`bot_container.py:313`). Live census: `trading_fee_pct` = 1.6 on 24 bots, 0.6 on 11; `scrumming_interval_pct` = 5.0 on all 35. That field is the Minimum Opposing Trade Distance term (`scrumming_bot.py:10018-10020`, gate at `:10023`; mirrored at `:10440-10442` and `:9737-9738`). **Live requires a 6.6% reversal, sim requires 5.6%.**

The verifier found the finding *understates* scope: `trading_fee_pct` is read at eight sites, not three — `5319, 6275, 6849, 7007-7008, 7571, 7793-7794, 9737, 10019, 10441`. The live restore path *does* forward it (`bot_container.py:2500`) and it is already in the shared allowlist (`bot_container.py:556`), so this is a pure omission.

Also dropped by the same whitelist: `max_cartridge_smart` (True on 12 bots, default False), `max_cartridge_size_pct` (5.0 on 6 bots, default 10.0), `hedge_balance` (0.0 on 33 bots, default 200.0), the six v3.16.15 strategy gates, all three `circuit_breaker_*`, `position_ceiling_*`, `detonation_*`, `max_entry_price`/`min_entry_price`, `self_reserve_capital`, `personal_hold_qty`, `wire_inflow_stack_pct`. Those sit at defaults in *today's* fleet, so the whitelist looks like it works — until the operator tunes one.

**Fix:** filter `cfg` by `dataclasses.fields(BotConfig)` and splat it; assert on unrecognised keys so schema drift fails loudly. Add a test that diffs the sim-constructed `BotConfig` against the `bot_state` config and fails on any silently-defaulted field.

### D3 — The sim charges zero trading fees **[V]**
**Symptom:** the accumulation curve is biased upward on every single trade, always in the same direction.

`fleet_replay_controller.py:512` — `fee_pct=0.0,`; `sim_exchange.py:405` — `fee = notional * self._fee_pct`; `sim_exchange.py:562` advertises `maker_fee=0.0, taker_fee=0.0`.

**Measured** on run `20260805T045429_926437`: 510 fills, **$7,687.18 gross notional**. At 0.6% that is $46.12 of uncharged fees; at the 1.6% that 24 of 35 bots actually pay, **$122.99** — 1.4%–3.7% of the entire $3,300 wallet seed over ~52.8 days of replay. Independently reproduced by the verifier to the cent.

**Unit trap for whoever fixes it:** `sim_exchange` multiplies by `_fee_pct` as a *fraction*; `BotConfig.trading_fee_pct` is a *percent* consumed as `_eff_pct/100.0` at `scrumming_bot.py:10021`. Passing it straight through charges 60–160%.

### D4 — `get_ohlcv` discards `timeframe`; all six phantoms read the same 5m series **[V, and worse than reported]**
**Symptom:** the higher-timeframe bias gate — which blocks SCRUM on HTF-bullish and FOLD on HTF-bearish, enabled on all 35 bots — acts on a fabricated signal that is a near-duplicate of the parent's own 5m TA.

`sim_exchange.py:249` — `del timeframe`. Every phantom calls `get_ohlcv(symbol, timeframe=self.timeframe, limit=100)` (`phantom_balance.py:238-240`) across `["5m","15m","30m","1h","4h","1d"]` (`scrumming_bot.py:300`) and gets the identical tablet slice. Consumed at `scrumming_bot.py:6774-6779`, blocking at `:6786` and `:7527`.

Two facts the verifier added, both making it worse:
1. `ta_timeframe` is `5m` on all 35 live bots, so **all five** higher phantoms feed the bias, not just the daily one.
2. `bot_state.json` records `phantoms_enabled=False` on all 35 saved bots and `_instantiate_bot` never reads that field. So the sim is not merely feeding phantoms bad data — it runs an entire subsystem that live currently has **off**.

Compounding: the phantom loop sleeps `min(self.candle_seconds, 60)` of **wall** time (`phantom_balance.py:206`), so in a 552-second replay of 15,211 candles each phantom ticked ~9 times. The HTF bias the gate reads is a stale snapshot from an arbitrary wall-clock point, decoupled from the master clock.

**Fix:** resample the native tablet series per timeframe (open=first, high=max, low=min, close=last, volume=sum) and return `[]` where coverage is absent so the TA engine's <30-candle hold fires honestly. Separately drive phantom `_tick()` from the replay clock, not `asyncio.sleep`.

### D5 — Expand is re-entrant; a second Expand permanently orphans the chart **[V, critical→high]**
**Symptom:** expand the chart twice, close both dialogs, and the chart is gone from the Simulator tab for the rest of the process.

`sim_visuals.py:101-102` — `dlg.finished.connect(lambda _r: _restore())` / `dlg.show()`. Modeless, no `WA_ShowModal`, no re-entry guard anywhere in `_show_expanded` (43-102). The Expand button lives in the **main-window** header row (`simulator_tab.py:249`, wired at `:258-260`, added at `:262`), so it stays clickable while a dialog is open. A second click captures `prior_parent = widget.parentWidget()` (`:72`) as *dlg1*, and the closure at `:90-99` strongly retains that stale parent.

Reproduced offscreen on PySide6 6.11.1: expand D1, expand D2, close D1, close D2 → `chart.parentWidget()` is QDialog 'D1', `chart.isVisible()` is False, while `area.widget() is chart` still returns True. No recovery short of an app restart.

**Fix (one line at the top of `_show_expanded`):** `_w = widget.window(); if isinstance(_w, QDialog): _w.raise_(); _w.activateWindow(); return`. Same guard fixes `PerBotVotingReadout`, which shares the helper.

### D6 — Per-symbol coverage table divides a capped-window read by the full-YTD expectation **[1P]**
**Symptom:** the Activity Log tells you every tablet is ~8.5% covered with a ~33,000-candle shortfall — then, a few lines later, tells you the opposite.

`_expected_per_sym` is computed at `fleet_replay_panel.py:700-701` from the full YTD span. But v3.24.16 narrows the actual read at `:727`/`:731-733` to `_win.replay_start_ms` when the soft-start cap applies, and passes `since_ms=_since_ms` at `:742-747`. So `len(rows)` covers the soft-start window while the denominator covers all of YTD. The table at `:782-787` and the summary at `:774-776` label it "gap between YTD expected and what tablets actually cover" — which is false.

Gate-log coverage only begins 2026-07-25, so `replay_start_ms` lands in late July against `YTD_START_MS` = 2026-04-01. The *correct* scoping is emitted a few lines later by `format_window_lines` at `:885-887` (`window scoped {full} -> {scoped} candles`), so one run contradicts itself and the louder number is the wrong one. This is the class of mis-anchored metric that drives a false "my tablets are stale" conclusion and a needless re-fetch.

**Fix:** move the expectation calc below `:737` and compute it against `_since_ms`; relabel "YTD" → "window". If the full-YTD figure is still wanted, print both explicitly so they cannot be confused.

### D7 — Fetch YTD failure is completely silent, then a stale count is presented as a fresh result **[1P]**
**Symptom:** you press Fetch YTD, it fails, and the panel says *"YTD trades fetched: 4,040 across 12 symbol(s)"* — last run's numbers.

`_do_fetch` (`fleet_replay_panel.py:504-518`) has no try/except. If `fetch_all_history_chunked` raises, `self._ytd_trades` is never reassigned and `_bounce_to_qt` discards `_fut` without ever calling `_fut.exception()`. `asyncio.run_coroutine_threadsafe` returns a `concurrent.futures.Future`, which — unlike an asyncio Task — emits no "exception was never retrieved" warning on GC. The traceback goes nowhere: not the status label, not the Activity Log, not the console log.

`_on_fetch_ytd_done` (`:546-565`) then reads the untouched list. On a first-ever fetch it says *"Fetch YTD returned no trades… Check console log for details"* — pointing at a console log containing nothing. The panel's own comment at `:520-528` documents that this reporting path was already got wrong once (the v3.23.85 wall-clock-timer bug); the error branch never got the same treatment.

**Fix:** try/except in `_do_fetch` recording `self._last_fetch_error`; have `_bounce_to_qt` call `_fut.exception()` and stash it; render it in `_on_fetch_ytd_done` with `logger.exception` and an Activity-Log line. Clear `self._ytd_trades` at the *start* of `_on_fetch_ytd_clicked`.

### D8 — Reset stops neither QTimer; Start is later re-enabled on an empty fleet **[1P]**
**Symptom:** you press Reset, it says "Replay idle", and half a second later the progress row is showing live counters for a fleet you just unloaded. Later you press Start and nothing at all happens.

Both timers are stopped in exactly one place — inside `if p.finished:` at `fleet_replay_panel.py:1367-1375`. Reset (`:455`) stops neither and never clears `self._controller`:
1. `:467` sets "Replay idle…"; 500 ms later `_refresh_progress` (`:1296`, guarded only by `if self._controller is None`) overwrites it.
2. When the cooperative stop lands, `:1376` `self._start_btn.setEnabled(True)` fires unconditionally — Start is enabled with `self._configs == []`, and clicking hits `:664-665` `if not self._configs: return`: no status text, no log line. Identical to the silent-Start failure called out in the v3.23.88 comment at `:164-170`.
3. `self._gate_cells` is cleared only in `_populate_fleet_table` (`:429`), never in Reset, so the still-running drain timer calls `cell.update_gates(...)` at `:1254` on widgets Qt destroyed via `setRowCount(0)`; the RuntimeError is swallowed to `logger.debug` at `:1282-1284`.

Separately, Reset destroys an in-flight replay whose ETA can read hours (`:1322`) with no confirmation.

### D9 — Load during a running replay re-enables Start, and Start has no re-entrancy guard **[1P]**
**Symptom:** reachable in four clicks — Load, Start, Load, Start — after which throughput halves for no visible reason.

Load is never disabled during a run and `_on_load_clicked` (`:417`) re-enables Start on config count alone. `_on_start_clicked` guards only on `self._configs` (`:664-665`) and the loop, then assigns `self._controller = FleetReplayController(...)` at `:858`, dropping the in-flight controller without `request_stop()`. `FleetReplayController`'s own guard (`fleet_replay_controller.py:289-292`) is per-instance, so a fresh instance never trips it. The abandoned `_run()` task keeps ticking on the same loop, keeps its sim exchange and bots alive, and opens a second `SimRunLog` run directory — while `_refresh_progress` reports only the new controller.

**Fix:** bail at the top of `_on_start_clicked` if `self._controller is not None and not self._controller.progress.finished`; disable `_load_btn` and `_full_eval_chk` for the run's duration.

### D10 — Trade markers are applied one snapshot frame early, and first-frame markers are dropped **[V]**
**Symptom:** the green/red validation markers you asked for on 2026-08-04 sit systematically ~15 candles to the left of the candle where the trade actually fired.

In `_drain_visual_snapshot` the marker loop is at `fleet_replay_panel.py:1238-1243`, **before** the per-symbol `append_tick` at `:1268`. `mark_trade` pins `len(prices) - 1` (`sim_visuals.py:508`) — the point appended by the *previous* drain. The producer builds the marker list and the candle close in the same snapshot (`_collect_visual_snapshot` `:1195-1202`, `:1208-1212`), so the correct anchor is the point appended at `:1268`. With `every_n_candles=15` (`:987`) that is a systematic 15-candle leftward offset on **every** marker.

Additionally, on the first drain after `set_symbols` (which resets `_series` to empty at `sim_visuals.py:480`) the guard at `:505-506` silently discards the marker — no log — and `drain_markers` has already popped the queue (`fleet_replay_controller.py:580-582`), so it is unrecoverable. Scope of the drop is small (first 15 candles); the systematic lag is the substantive defect.

### D11 — Chart x-axis is exponentially warped by halving decimation **[V — mechanism confirmed, magnitude REFUTED]**
**Symptom:** older price history is compressed toward the left edge and markers drift progressively left of their true candle.

`sim_visuals.py:537-538` halves by keeping every other point, so the array becomes `[oldest at stride 2^k | … | newest 250 at stride 1]` while x maps linearly to index (`:590`). The `i//2` remap at `:546-547` is arithmetically faithful — it just faithfully follows a warped series.

**Correction to the original magnitude claim, which is what should reach the operator:** `append_tick` is *not* driven at 4 Hz. `_drain_visual_snapshot` early-returns when `_pending_snapshot` is None (`fleet_replay_panel.py:1230-1231`), and the producer writes a snapshot only every 15 candles (`:987`, fired at `fleet_replay_controller.py:699-700`). For the canonical 19,680-candle replay that is ~1,312 appends → ~4 halvings, not 43. At 4 halvings a marker created at index 500 lands at ~31, not 0. The originally-reported "82% of markers stack on index 0" and "after ~10 minutes the markers are a single stack" figures are **artifacts of a 4× inflated append count and should not be repeated**. Real defect: non-uniform time axis and progressive marker drift. Severity medium.

### D12 — Nuclear scout writes into (and reads from) LIVE capital-reservation state **[V — mechanism confirmed, consequence corrected]**
**Symptom:** every Start Scout click runs a bot that consults, and can mutate, the operator's live `~/.acervator/reservation_state.json`.

`nuclear_controller.py:321` — `scout = ScrummingBot(cfg, self._exchange, enable_phantoms=False)`. No `sim_mode`, no `capital_registry`. So `_capital_registry` is None (`scrumming_bot.py:344`), `_sim_mode` is False (`:330`), and `_crr()` falls through to the process-wide singleton (`:1027-1032`) whose state file is `~/.acervator/reservation_state.json` (`capital_reservation.py:83`) with `autosave=True` (`:183`). `tick()` calls `_ensure_capital_reservation` at `scrumming_bot.py:4675`, and v3.24.31 deliberately removed the old `if _sim_mode: return` short-circuit (`:1068-1074`, "Isolation comes from WHICH registry the bot holds"). Reachable end to end: `simulator_tab.py:158` → `nuclear_mode_panel.py:383` → `_construct_scout()`.

**Corrected consequence — do not repeat the original framing.** The write is gated by an over-commit check the original claim omitted: `NuclearSimExchange` seeds every TAPEx base at 0.0 (`nuclear_sim_exchange.py:103-105`), so `total_holdings` is 0.0 and `capital_reservation.py:314-320` raises *before* any mutation, swallowed to a WARNING at `scrumming_bot.py:1129-1136`. The routine outcome is a **per-tick warning flood**, with a live-file write only on ticks where sim holdings exceed 1.1× target. The claim of "every click accumulates orphans / 6.5 MB" is **not** established.

What *is* unconditional is the **read**: `scrumming_bot.py:10095` resolves `self._crr()` and consults `effective_available` — a sim bot's sell decision is being made against live registry state. Still a genuine isolation gap; fix it the way `fleet_replay_controller.py:208-210` does.

### D13 — Sim exchange never rejects for insufficient funds **[V, high→medium]**
**Symptom:** the sim can mint capital. Balances go arbitrarily negative and the run still reads as a valid outcome.

`sim_exchange.py:284-286` and `place_order` (`:288-352`) validate only `amount > 0` and symbol-known; `_settle_fill` (`:399-411`) adjusts balances unconditionally. Probe reproduced exactly: $10 wallet, MARKET BUY 100 @ $100 → FILLED, USD = **-9990.0**; MARKET SELL 1e6 with 0 held → FILLED, base = **-999900.0**. Reachable because no `VolumeGuard` is attached in sim (`bot_container.py:871`), so `guarded_place_order` falls through to `:1080`.

**Evidentiary refinement from the verifier:** reconstructing the last run's USD trajectory across 510 fills gives final $0.0000, minimum $0.0000, zero negative events. So this is proven latent by probe but did not materialize in that replay — a missing rejection shape, not a currently-corrupted result. Live Coinbase returns `InsufficientFunds` here; that error shape, the most common real rejection an accumulation bot meets, is unrepresented, so nothing in the fold/rebuy path is ever tested against it.

### D14 — Every LIMIT order fills on the same candle at the exact limit price **[V, high→medium]**
**Symptom:** the entire resting-order model — queue risk, partial fills, duplicate-open-SELL refusal — never exercises in a replay.

`sim_exchange.py:338-340` is unconditionally true for every order the bot places: `get_ticker` returns `last=close` (`:216-222`), `_execute_sell` uses `OrderType.LIMIT` for every non-invisible bot (`scrumming_bot.py:10198`) at `fill_price` = `close * (1 - slip)` ≤ close (`execution_discipline.py:113`), and `candle_high >= close` by the OHLC invariant. Buy side mirrors it. Verified on **303,208 real Stone Tablet candles** across ZEC/CHIP/BTC/RAVE/BONK/ADA: zero rows violating `low <= close <= high`. 34 of 35 live bots run `visibility='orderbook'` (= LIMIT).

Correction on wording: `_sweep_open_limit_orders` (`:459`) and `get_open_orders` (`:521`) **do** execute every step — they execute and always find nothing. It is the fill/refusal *branches* that never fire. A non-marketable LIMIT does rest correctly (probe: far sell at $1000 vs high $110 → OPEN); the bot's own pricing is what guarantees marketability.

No partial fill is ever produced either — `_settle_fill` hardcodes `order.filled = amount; order.remaining = 0.0` (`:414-415`), so `OrderStatus.PARTIALLY_FILLED` (`base.py:40`) and the `order.filled or order.amount` fallback (`scrumming_bot.py:9026-9030`) are untested.

### D15 — `Balance.used` is hardcoded 0.0; resting orders never lock capital **[V]**
**Symptom:** the MEM-257 defect class — the operator-rage case where a $50-target bot holding $50 bought $100 more — cannot be reproduced in sim.

`sim_exchange.py:270-281` always reports `used=0.0` and `free==total`; `place_order` debits nothing on an OPEN order. Probe: $1,000 wallet with a resting LIMIT on the book → `free=1000.0, used=0.0`. The bot's own code records the input condition at `scrumming_bot.py:10618`: `# (a) used Balance.free (BTC locked-in-open-order reports free=0);`. So the FAIL-CLOSED guard `_verify_buy_safe_or_refuse` is never tested against the state it was written for.

**Sequencing matters:** this is currently masked by D14 (no order ever rests). Fixing D14 without fixing D15 converts a benign mask into a **double-pledged-capital bug**. Fix them in the same change.

### D16 — Fabricated uniform market limits; the sim enforces none of them **[V]**
**Symptom:** a "PRE-FLIGHT REJECTED … below min_cost $1.0000" message that came from the bot, not the venue — and a sim that will happily fill a $0.10 order if you go around the bot.

`sim_exchange.py:560-562` hardcodes `min_cost=1.0`, `min_amount=1e-8`, `amount_precision=8` for every symbol (the only `min_cost=1.0` literal in `src/`). Enforcement lives in the bot: `bot_container.py:929-937` reads them, `:1002` is the min_amount branch, `:1017-1021` raises the pre-flight message. Probe confirms `FleetSimExchange.place_order` itself fills a $0.10-notional SELL as FILLED.

Knock-ons: `min_amount=1e-8` makes the `:1002` branch unreachable, so the v3.15.78 truncation logic at `:987-999` — written for the operator-reported RAVE 0.1-minimum incident — is never exercised; `amount_precision=8` lets orders fill at full float precision that Coinbase would truncate.

*Presentation caveat from the verifier:* the "$1.0000" in the originally-quoted log line was inferred from code, not observed — `'ZEC/USD min_cost'` appears nowhere in `~/.acervator_logs`; its only occurrence in the tree is `CHANGELOG.md:198` without the value. The inference is sound; do not cite it as a log quote.

### D17 — `IOC_LIMIT` raises `ValueError`; Aggressive Trading cannot be simulated **[V, medium→low — reached=false today]**
**Symptom (latent):** flip Aggressive Trading or Stack mode on and run a replay, and you get zero tranches that read as a market outcome.

`sim_exchange.py:344-347` rejects `OrderType.IOC_LIMIT`; probe reproduces `ValueError: FleetSimExchange.place_order: unsupported type <OrderType.IOC_LIMIT: 'ioc_limit'>`. The consumer is `scrumming_bot.py:9771-9773`, and the call site swallows the exception into `entry["status"] = "cancelled"` at `:9804-9810`. **Not reached today**: `aggressive_trading` and `stack_mode` are False on all 35 live configs. A trap, not a current corruption.

### D18 — Nuclear v2 latent defects (module has no production driver — all `reached=false`)
These become live the instant the panel is rewired. Fix them *as part of* the rewiring, not after.

| Defect | Symptom once wired | Ref |
|---|---|---|
| `_bot_for_asset` zips full config list against a **filtered** bot-id list | A BTC→ETH topology proposal registers a wire between two unrelated bots, and `format_coverage_lines` still reports link 4 as **PASS** because `cross_bot_credits` only checks `src != bot_id`. **[V]** | `nuclear_fleet_controller.py:598`; filter at `fleet_replay_controller.py:518-519`, `:211-215`; false PASS at `nuclear_verification.py:293`, `:356-362` |
| `record_gate(payload=…)` — no such parameter | Soak run directory contains only start/finish rows: **zero** cycle records, zero coverage, zero emit-contract data, against a docstring promising "records everything so a failure on cycle 40 can be traced back". Executed: `TypeError: SimRunLog.record_gate() got an unexpected keyword argument 'payload'`, swallowed to `logger.debug`. **[V]** | `nuclear_fleet_controller.py:649`, `:682`, `:695`; signature `sim_run_log.py:220-224` |
| Stop and COOLING evaluated only *between* cycles | Stop does nothing for the rest of a multi-minute cycle (3000 candles × up to 6 fleets × 35 bots), and a CRITICAL machine cannot shed the 4× load pulse — contradicting the file's own SAFETY section at `:41-48`. `ctl.request_stop()` (`fleet_replay_controller.py:356-359`) is never called; ctl objects are local to `_one()`. **[V]** | `nuclear_fleet_controller.py:356`, `:362`, `:395`, `:421` |
| A worker fleet that instantiates zero bots spins forever inside `asyncio.gather` | Stop becomes permanently ineffective and the swarm row floods. After a failed `start()`, `stopped_event` is SET (`fleet_replay_controller.py:274`) and `finished` is FALSE (`:272`) because the early return at `:293-297` precedes both `:298` and `:304` — so `while not ctl.progress.finished` never breaks and `wait_for` returns immediately. **[1P]** | `nuclear_fleet_controller.py:462`, `:473-474`, `:491` |
| One shared `SwarmFeatureVerifier`/`EmitObserver` across all gathered fleets | Tranche/wire quantities are multiplied by worker count, and because `workers` is oscillator-driven the same soak reports different numbers depending on where in the 120 s cycle it landed. Booleans stay correct; only quantities are wrong. **[1P]** | `nuclear_fleet_controller.py:337`, `:343`, `:480`; `nuclear_verification.py:280`, `:285-286`, `:364-367` |
| One worker exception discards the whole cycle's candles/trades/**exceptions** | `total_exceptions` is zeroed precisely on the cycles that had failures — the signal a soak exists to accumulate. `:496` also overwrites `cyc.error` per worker, so a 6-way failure reports as one. Mitigation: `_record_cycle` at `:645-651` writes `cyc.to_dict()` before the branch, so only the GUI aggregate undercounts. **[V, medium→low]** | `nuclear_fleet_controller.py:373`, `:375-377`, `:495-500`, `:722` |
| `SmartWireManager` resolves the **global** event bus | Sim `WIRE FLOW: $x from A -> B` lines would interleave with real trading output in the live status log. Zero present-day contamination: `SmartWireManager` is instantiated only at `bot_container.py:1459` (live) and `nuclear_fleet_controller.py:551` (dead), and `distribute_fold_profit` returns at `smart_wire.py:457-458` before the bus lookup when no wires are registered. **[V, medium→low]** | `nuclear_fleet_controller.py:558`; `smart_wire.py:464-465`, `:648-651`; `main_window.py:3159`, `:5540` |
| N+1 durable run logs per cycle | Up to 7 run directories per multi-minute cycle, indefinitely. **[V]** (The *reached* half of this finding — sim writing live `feature_telemetry.json` — is promoted to Part 2, F1.) | `nuclear_fleet_controller.py:425-432`, `:491`, `:628-629`; `fleet_replay_controller.py:314-316` |

---

## 1b. Missing wiring

### W1 — Fleet Replay never loads the live Smart Wire topology: 40 wires become 0 **[1P]**
**Symptom:** the primary parity harness replays a fleet whose compounding engine is switched off, so every sim-vs-live accumulation comparison is biased low by construction.

The live `bot_state.json` top-level keys are `['bot_count','bots','saved_at','saved_at_human','smart_wire_ledgers','smart_wires','version']`. `bot_state_loader.py:68` reads only `data['bots']`. `_instantiate_bot` never calls `set_smart_wire`, and `_wire_topology` exists only on the Nuclear path (`nuclear_fleet_controller.py:459`, its sole caller). So every Fleet Replay bot has `_smart_wire_mgr = None` (`scrumming_bot.py:715`) and both wire routes short-circuit (`:1587-1590`, `:8280`).

The operator's live file carries **40 wires with real flow** (CHIP ledger `wired_out` $102.77, SPK $46.26). Per the project's own definition, fold tranches "are fed by Smart Wire transactions to boost compounding across a topology." `nuclear_fleet_controller.py:527` already documented the symptom ("9 tranches created, 0 fed") for Nuclear without fixing Fleet Replay.

**Fix:** return `data['smart_wires']` from the loader, construct one `SmartWireManager` per replay, `attach_bot` each sim bot, and `register_wire` per live wire remapped via `_src_bot_id` (already stamped at `bot_state_loader.py:86` for exactly this join). Log "N wires replayed" so a zero is visible.

### W2 — Nuclear Mode's chart and voting readout are wired but can never populate **[V]**
**Symptom:** the operator's original report — *"No activity in any of these panel after Start Scout is clicked"* (`simulator_tab.py:298-299`) — is still true for the two data panels after v3.24.28.

`set_symbols` has exactly one caller repo-wide (`fleet_replay_panel.py:974`) and `set_bots` exactly one (`:976`). Nuclear calls neither — `nuclear_mode_panel.py:436-438` only stores the handles. So `_series` and `_sym_to_row` are empty, and `_feed_visuals` (`:440-473`) hits three silent early returns: `append_tick` at `sim_visuals.py:522-523`, `update_bot_row` at `:707-709`, `paintEvent` at `:557-558`. None of them log.

The wiring is genuinely live (`simulator_tab.py:305-309` passes the same widget instances; the 500 ms `_refresh_timer` at `nuclear_mode_panel.py:289-291` starts at `:404`), which is what makes it read as "wired but empty". Nuance: if a Fleet Replay ran first with a fleet containing the scout's symbol, the feed would land — on the wrong chart bands. Nuclear-only session = both panels dead.

**Fix:** lazily register on first snapshot (`chart.set_symbols([symbol])` / `readout.set_bots([symbol])` for an unknown symbol), or add `ensure_symbol()` to both widgets. At minimum replace the bare `return` with `logger.debug`.

### W3 — Nuclear v2 controller has zero production callers **[V]**
**Symptom:** the tab labelled Nuclear Mode still drives the Phase-B single-tape prototype the v2 module was written to replace.

`grep -rn NuclearFleetController` returns the definition at `nuclear_fleet_controller.py:193` plus 8 references, **all** in `tests/test_nuclear_fleet_controller.py`. A wider grep across `.py`/`.md`/`.json` adds only `CHANGELOG.md:99` and three `.claude/settings.local.json` permission entries. The panel imports the old class (`nuclear_mode_panel.py:35`, constructed at `:383`), and `simulator_tab.py:156-158` says so in-tree: *"Nuclear panel still hosts the old tape-based prototype."*

Two seams the operator directive asked for are dead on arrival: `set_topologies` (`:246`) and `set_swarm_hooks` (`:251`) have **zero callers anywhere, including the tests**. The verifier added that the tests never touch `_run`, `_run_cycle`, `_wire_topology`, `_topology_pairs` or `_bot_for_asset` either — most of the module has never executed. The module has reproduced the exact failure it was written to detect (`nuclear_verification.py:14-19`: *"register_sim_run() zero callers -> swarm rows never driven"*).

**Rewiring checklist:**
1. Replace the tape combo / seed / world-clock form with `cycle_candles`, `max_cycles`, load-oscillation toggle — v2 reads the fleet from `bot_state` itself (`:200-209`, `:267`).
2. `_on_start_clicked` must call `prepare()` and surface its `False` return, then schedule `start()` — note v2's `start()` is a **coroutine** (`:322`) while `NuclearController.start(loop)` is sync, so the existing call site cannot be reused.
3. Call `set_swarm_hooks(...)` and `set_topologies(...)` before `start()`.
4. Repoint `_refresh_status`: `_STATUS_FIELDS` wants `scout_state`/`tape_position`/`tape_wraps` (`nuclear_mode_panel.py:40-54`); v2 emits `cycles_completed`/`load_multiplier`/`cooling`/`failed_cycles` (`:711-728`).
5. Do **not** delete `nuclear_controller.py` / `nuclear_candle_source.py` / `nuclear_sim_exchange.py` in the same change — they are the currently-reachable path.

### W4 — Parity comparison accepts only `_ytd_trades`, so it is skipped on exactly the runs where anchoring succeeded **[1P]**
**Symptom:** you Load, Start, watch a fully-anchored replay finish, and are then told *"Parity: skipped — no live trades loaded. Run Fetch YTD before Start Replay"* — after burning the whole run.

v3.24.16 fixed this for anchoring: `_live_trade_timestamps` (`fleet_replay_panel.py:567-599`) falls back to `live_trades()` when `_ytd_trades` is empty, with a docstring explaining that v3.24.15 "silently degraded to full evaluation." `_run_parity_comparison` (`:1386-1431`) never got the same treatment, so anchors come from the fallback at `:934` while parity refuses at `:1406-1408`. Its own docstring at `:1378-1382` calls this "the 'does sim reproduce live?' measurement the whole harness exists for."

**Fix:** (a) mirror the fallback in `_run_parity_comparison`, normalising to the dict shape `compare_trades` expects; (b) regardless, warn in the Activity Log at Start time when `not self._ytd_trades` — the panel knows before it schedules the controller.

### W5 — `clear_markers()` has zero callers **[V]**
`sim_visuals.py:510`, shipped with the v3.24.29 marker feature, is not called anywhere in `src/` or `tests/` and is not in `__all__`. It is precisely the API that would make D-below (`clear_data` leaving stale markers) and the unbounded-marker item fixable from the caller side. Same class as `GateLightsCell.clear_gates`, already recorded as zero-caller scaffolding in `docs/engineering-notes/2026-08-04_full_codebase_defect_scan.md` row 48.

Related latent invariant: `clear_data()` (`sim_visuals.py:549-553`) resets `_series` and `_vwap_window` but leaves `_markers` populated. **[V]** Safe today only because its single caller (`fleet_replay_panel.py:973`) immediately calls `set_symbols`, which does reset markers (`:482`). Add `self._markers[s] = []` to the loop.

---

## 1c. Usability

| Item | Symptom | Ref | Conf |
|---|---|---|---|
| **U1 — Status label is the sole surface for 8 failure messages, styled identically to success** | Pressing Start with no tablets produces 11px grey text at the far right of the load row behind `addStretch()`, visually identical to "Loaded 35 bot(s)". The fleet table doesn't change and the progress row still reads "Replay idle", so a missed label reads as the panel doing nothing. None of the 8 failures are mirrored to the Activity Log — the large, scrollable surface the operator is actually watching. Only one `setStyleSheet` on `_status_lbl` exists (`:259`) against 15 `setText` sites. | `fleet_replay_panel.py:259`; failures at `:409, :481, :486, :490, :533, :668, :673, :842, :992` | [1P] |
| **U2 — Fetch YTD tooltip documents a retired v3.23.80 OHLCV path** | Every clause is false: it names a data type, a 200-candle limit, a `1d` timeframe, a MarketDataPool and an effect that no longer exist. The button actually fetches **trades** (`:470-544` via `fetch_all_history_chunked`) and its real, undocumented effect is to enable the parity report — which the tooltip never mentions. Candles come from Stone Tablets (`:688-747`). | `fleet_replay_panel.py:216` | [1P] |
| **U3 — Header and Start tooltip promise synthetic sine-wave candles** | A permanent on-screen banner tells the operator the run he is watching is fake data. It is real 5m tablet data: `:753-755` reads `# No tablet -> skip. NO synthetic fallback.` and `_synthesize_candles_for_symbol` (`:67`) has **zero** production call sites. The abort message at `:842-844` tells him to "Run Fetch YTD first", which cannot fix the abort; the correct remedy is already in the Activity Log at `:797-800`. Version pointer "v3.23.79-B" is ~50 patch releases stale. | `fleet_replay_panel.py:193-196`, `:296` | [1P] |
| **U4 — Hardcoded "122 days" beside a live-computed day count** | The first line of the run report reads *"YTD window: 126.2 days · expected ~36,346 candles per symbol (122 days × 288 5m candles)"* — the explanation openly disagrees with the number it explains. Only `122 days` literal in `src/`. | `fleet_replay_panel.py:770`, derived from `:700` | [1P] |
| **U5 — Start freezes the GUI for up to three full trade-log walks** | The panel is frozen with a stale status label and no first Activity-Log line until `:767`. `live_trades(validate=False)` is walked at `:625` (inside `_compute_soft_start`, called at `:730`) and again at `:590` from both `:913` and `:934`, back to back, no memoisation, all inline on the Qt main thread. v3.24.24 already bounded the gate-log side of this (`:618-623` documents 165,062 rows / 250.7 MB) — the trade side wasn't given the same attention. | `fleet_replay_panel.py:913` | [1P] |
| **U6 — Reset destroys an in-flight replay with no confirmation** | ETA display can read hours (`:1322`); Reset takes it out with one click. | `fleet_replay_panel.py:455` | [1P] |
| **U7 — Expand-then-Load shrinks the chart to 7 of 35 bands with no scrollbar** | `_restore()` clobbers `minimumHeight` with a value captured before the reparent, but nothing in `_show_expanded` ever changes it — so the restore can only undo a legitimate change. Reproduced: expand → `set_symbols(12)` → 432 → close → **0**; against the real container (`simulator_tab.py:216` `setWidgetResizable(True)`, `:221` `setMinimumHeight(80)`) the chart drops 1260 → 280 px and the scrollbar disappears. Narrow trigger (requires Expand *before* Load), and a strictly weaker instance of D5's root cause. | `sim_visuals.py:94`, capture at `:73` | [V, med→low] |
| **U8 — Every Expand click leaks a QDialog parented to the main window** | No `WA_DeleteOnClose`; after 4 expand/close cycles `win.findChildren(QDialog)` returned 4 live dialogs. Bounded by operator clicks, a few KB each — its real value is as the shared root cause that makes D5's stale restore land in a hidden-but-alive dialog. | `sim_visuals.py:65` | [V, med→low] |
| **U9 — `mx` rebound from price-max to a pixel x-coordinate inside an 85-line `paintEvent`** | Not a defect today — `span` is computed at `:586` before the rebind at `:629`, and both recompute per band. But the two values differ by orders of magnitude in one scope; any future edit that moves the span calc silently rescales the polylines with a pixel coordinate and nothing raises. | `sim_visuals.py:585-586`, `:629` | [V] |
| **U10 — Uncapped `_markers` makes paint cost grow with run length** | Nothing prunes `_markers` (`sim_visuals.py:507`); `clear_markers` has no callers and `clear_data` doesn't touch it. `paintEvent` (`:623-637`) does setPen + setBrush + antialiased `drawEllipse` per marker per repaint. **The originally-reported "27.6 ms → 123.8 ms at 4 Hz / ~0.5 s of every second in paint" figure is REFUTED** — repaints are producer-gated to ~1 Hz, and marker count is bounded by *fills* (`fleet_replay_controller.py:558-570`), realistically tens per symbol, not 627. No memory leak. Genuine residual: linear paint growth with no pruning API in use. | `sim_visuals.py:507` | [V, high→low] |

---

# PART 2 — CODEBASE + OPTIMIZATION AUDIT

Ranked by expected impact = cost × frequency × input size.

## F1 — Sim writes the LIVE runtime tree on every replay **[V — critical→high, reached, physically confirmed]**
**Rank 1 — isolation breach, reached on the production path, every run.**

`fleet_replay_controller.py:779` (`_tel.save()`) and `:784` (`_tel.write_markdown_report(`) sit inside the `finally:` that opens at `:706`, so they execute at the end of **every** replay including cancelled ones.

- `feature_telemetry.py:87` — `TELEMETRY_PATH = Path.home() / ".acervator" / "feature_telemetry.json"` — the live directory holding `bot_state.json`, `coinbase_credentials.json`, `reservation_state.json`.
- `feature_telemetry.py:399` — the markdown report defaults to `~/.acervator_logs/feature_validation.md`.

**On disk right now:** `~/.acervator/feature_telemetry.json` (3,706 B, Aug 5 10:16) sitting beside `coinbase_credentials.json`, its `declared` array carrying `sim.*` and `swarm.*` names; `~/.acervator_logs/feature_validation.md` (1,331 B, same timestamp) headed `Scope: \`sim.\`` with "Candles played: 19 / 20".

The verifier found evidence *stronger* than claimed: a repo-wide grep shows the **only** callers of `save()`/`write_markdown_report()` anywhere in `src/` or `main.py` are these two sim lines — the sim replay is the sole producer of both live-tree files, not merely a polluter. There is no env override (`no getenv` in `feature_telemetry.py`) and `tests/conftest.py` does not isolate it, so the whole 1098-test suite writes the operator's live telemetry file undetected — `_assert_no_live_tree_writes` only diffs `~/.acervator_logs/sim/runs`.

Compounding: the persisted `declared` set is restored at `:552-554` and re-saved at `:564`, never pruned, so it monotonically accumulates every feature name ever declared. And `nuclear_verification.py:213` feeds sim-only `swarm.*` names into the same singleton.

**Fix:** construct a per-replay `FeatureTelemetry(path=<sim log root>/feature_telemetry.json)` in `FleetReplayController.__init__` and use it at `:775-794`; same at `nuclear_verification.py:203-213`. Add an `ACERVATOR_TELEMETRY_PATH` env override mirroring `SIM_LOG_ROOT_ENV` (`sim_run_log.py:63`), set it in `tests/conftest.py`, and extend `_assert_no_live_tree_writes` to cover both files.

## F2 — `prune_expired()` has zero callers; reservations are append-only on disk **[V — critical→high, live money]**
**Rank 2 — the only item on this list that can cancel a real SCRUM.**

`capital_reservation.py:567` is defined and never called: repo-wide grep returns the comment at `:92`, the definition at `:567`, the log string at `:608`, plus hits confined to `./_archive/`. Nothing in `src/`, `main.py`, `tools/` or live `tests/` invokes it. It is the **only** automatic reclamation path — `_reservations` is otherwise removed only by explicit `release()`/`force_release()`, and `_heartbeats` only by `force_release_all` (`:450`). Every `reserve()` rewrites the whole file (`:338` → `:225-232`).

**Evidence the finding missed, and it is the strongest piece:** `_load()` at `:239-252` rehydrates every persisted reservation with **no age or staleness filter**, so orphans from an unclean shutdown survive every restart forever.

**Consequence is broader than disk:** orphan qty is summed into the over-commit gate at `:310-313`, *and* `scrumming_bot.py:10098` calls `effective_available(...)` with `:10103` returning None on "SELL REFUSED (capital reservation, v3.20.2)". Accumulated orphans directly cancel live SCRUMs.

This has already fired once — `scrumming_bot.py:1059-1063` documents *"16,558 bot_ids in that file against 35 real ones — 16,523 orphans, 6.5 MB"*. Purge residue is still on disk: `reservation_state.json.pre_purge_20260803_182306` = 6,507,704 B and `orphan_reservations_quarantine_20260803_182306.json` = 6,001,026 B beside a current file of 11,430 B. v3.24.31 removed the sim *source* of orphans and left the retention defect intact.

**Correction to carry forward:** "each exception permanently orphans one entry" is **overstated**. The common failure — over-commit in `reserve()` — raises at `:314-321` *before* `self._reservations[token] = r` at `:335`, so no orphan is created. Orphaning via `scrumming_bot.py:1135` requires a successful reserve followed by a later raise (`update()` over-commit at `:396-400`, or `heartbeat()`) — a much rarer path. So present-day accrual is slow; the reclamation gap is total.

**Fix:** run `prune_expired()` on a timer next to the other periodic work where BotManager/registry is constructed (`main.py:513` area), every `HEARTBEAT_INTERVAL`. Extend it to drop `_heartbeats` entries with no remaining reservation past TTL (it currently only deletes from `_reservations` at `:605`).

## F3 — Phantom TA loop: 60s poll regardless of timeframe, and it bypasses the MarketDataPool **[1P]**
**Rank 3 — highest cost × frequency in the live process.**

- **Frequency:** `phantom_balance.py:206` — `await asyncio.sleep(min(self.candle_seconds, 60))` clamps *every* phantom to 60s, discarding `TIMEFRAME_SECONDS` (`:75-79`, 1d = 86400) for every TF above 1m.
- **Input size:** 100 candles per fetch, then a full 12-indicator `compute_all` (`:246`, measured 0.61 ms).
- **Bypass:** `PhantomBalanceBot` has no `_data_pool` member at all (constructor `:145` stores only `self.exchange`), so `:238` issues a raw `get_ohlcv` and never touches the v3.23.74 coalescer.
- **Reachability:** `enable_phantoms: bool = True` (`scrumming_bot.py:309`), started from `tick()` at `:4917-4926`, 6 phantoms per bot (`:300`).

That is **360 raw OHLCV calls/hour/bot; 12,600/hour = 210/min at 35 bots.** Information-redundancy by TF (poll rate vs candle close rate): 5m 4/5, 15m 14/15, 30m 29/30, 1h 59/60, 4h 239/240, 1d 1439/1440 — **94.6% of those calls return data identical to the previous call.** This is exactly the CPM burn the v3.23.74 note at `scrumming_bot.py:2374-2379` claims to have fixed; the fix covered the parent path and left the larger consumer untouched.

**Fix (two independent changes):** (1) inject a `_data_pool` into `PhantomBalanceBot` the way `BotManager` does (`bot_container.py:1583`, `:2021`) and route `:238` through it — the pool's TF-derived TTL (`data_pool.py:57-62`) then collapses same-(exchange, symbol, TF) phantoms across all 35 bots to one fetch per candle interval. (2) Drop the `min(..., 60)` clamp, or gate `_tick()` on the last candle timestamp changing. Both are behaviour-preserving: `compute_all` is a pure function of the candle list.

## F4 — Phantom bots and TimeframeCoordinator bind the global EventBus **[1P]**
**Rank 4 — isolation invariant broken; consequence latent.**

v3.24.12 gave each sim bot a private `EventBus` specifically so "a future emit site that forgets to check the flag" could not leak (`scrumming_bot.py:364-367`). Phantoms defeat that structurally: `phantom_balance.py:150` calls `get_event_bus()` (the process singleton, `event_bus.py:207-214`) rather than inheriting the parent's bus, and `TimeframeCoordinator.__init__` does the same at `phantom_balance.py:313`.

v3.24.31 turned phantoms ON for sim (`fleet_replay_controller.py:209`), and `scrumming_bot.py:4917-4927` starts a phantom set per bot — ~175 phantoms per 35-bot replay, each emitting `phantom.started` (`:173`), `phantom.analysis` every cycle (`:251`) and `phantom.error` (`:200`) onto the **live** bus, plus `timeframe.lock_created` per coordinator (`:358`).

**Honest reachability caveat:** a repo-wide grep finds no current subscriber for `phantom.*` or `timeframe.lock_created`, and `LogManager` subscribes only to `trade.filled`/`pnl.event`/gate+voting (`logging_engine.py:577-603`). There is **no observable live-log corruption today**. The defect is the broken invariant — the next handler wired to `phantom.analysis` (e.g. feeding the live Indicator Voting Panel) silently receives sim TA.

**Fix:** optional `bus` parameter on both classes defaulting to `get_event_bus()`; pass `self._bus` down through `create_phantom_set` / coordinator construction (`scrumming_bot.py:414-415`, `:4918-4926`). Add a test asserting a `sim_mode` bot with phantoms started emits zero events on the global bus.

## F5 — TA duplicate-computation cluster: ~0.16 ms of a 0.741 ms per-tick block **[1P, measured at 100 candles]**
**Rank 5 — modest absolute CPU at 35 bots, but it runs on the GUI's asyncio loop and scales linearly with fleet size.**

All five are bit-identity-verified range narrowings or shared computations, not approximations.

| Sub-item | Duplication | Measured | Ref |
|---|---|---|---|
| **Bollinger(20) SMA/stdev computed 3–4× per tick on identical closes** — BollingerBands (tail=20), Slingshot (tail=35), `detect_bb_proximity` (tail=1), `detect_landing_strip_v2` (tail=1); all period 20 in production | 0.0578 ms/tick pure duplication of a 0.146 ms family | `_stdev_tail` is the **#1 hot function in cProfile at 17.8% of cumtime**; it allocates a fresh 20-element slice plus a generator pass per output element (`ta_engine.py:224-230`) | `ta_engine.py:766`, `:2252-2253`, `:2678-2679`, `:2827-2828` |
| **`compute_heikin_ashi` runs twice per tick over the same 100-candle list** | 0.0451 ms/tick (6.1% of block) | cProfile: 600 calls / 300 ticks = exactly 2.0 per tick; top function by tottime, 0.052s of 0.527s, 14.1% of cumtime | `ta_engine.py:2697`, `:2785`; both fed the same `candles` local from `scrumming_bot.py:5911`, `:5973` |
| **True Range built three times per tick** — ADX inline (`:311`), Supertrend inline (`:441-444`), Vortex via `_true_range` (`:234-241`) | 0.0291 ms/tick (3.9%) | Element-wise identity verified on 100 real-shaped candles: ADX-inline == Supertrend-inline == `_true_range(candles)[1:]` | `ta_engine.py:865` |
| **Wilder RSI series built twice** — StochasticRSI (`:1231-1243`) and RSIIndicator (`:2015-2025`), both period 14 by default | 0.0271 ms/tick (3.7%) | Arrays verified equal; independent reimplementation reproduces `rsi_series[-1]` exactly (38.79654869768831) | `ta_engine.py:2015` |
| **`detect_landing_strip_v2` allocates two 100-element lists when ≤13 entries are read** | 87 of 100 entries per list discarded per call | Consumer walks backward with `break` and a hard `shrink_count >= 12` cap (`:2796-2806`); lowest read index is `len(norm)-13` (`:2812`) | `ta_engine.py:2786`, `:2791` |
| **`VolumeAnalysis` copies 97 of 100 candles for a 15-candle MFI window** | 82 of 97 copied refs never touched | `_mfi(candles[:-3],14) == _mfi(candles[-18:-3],14)` → True (75.20860594142161 both ways), slice 97 vs 15 | `ta_engine.py:1783`, `_mfi` at `:1678-1693` |

**Fix shape:** build a small per-`compute_all` context (or optional pre-computed kwargs) carrying the period-20 SMA/stdev pair at the widest tail any consumer needs (35), the TR series, the Wilder RSI series, and the Heikin-Ashi list; pass it to the consumers. Guard the RSI sharing on `stoch.rsi_period == rsi.period` so a non-default config falls back rather than silently borrowing the wrong period. **Do not** truncate `compute_heikin_ashi` to a tail — its open is a recurrence from index 0 (`:2621`), so that would be a value change, not a range narrowing. Bound the two landing-strip comprehensions to the last 14 entries and the MFI slice to `[-(period+4):-3]`.

## F6 — The whole TA block is recomputed while the OHLCV pool serves byte-identical candles **[1P]**
`compute_all`, `detect_bb_proximity` and `detect_landing_strip_v2` are pure functions of `candles` plus static config. With the pool wired (live only), `_get_ohlcv` returns a cached list whose TTL equals the timeframe (`data_pool.py:57-62`; fast path `:401-406` returns `list(entry.candles[-limit:])` — same contents, new object).

`tick_interval` is hardcoded 5.0s (`scrumming_bot.py:2315-2316`) and the read-rate gate at `:4706-4714` gives an action tick every 300s in SEARCH, 30s in TRACK/FIRE. Against a 3600s cache TTL that is 12 action ticks per cache window in SEARCH and **120 in TRACK/FIRE** — so 11 of 12, or 119 of 120, TA blocks provably reproduce the previous result. At 0.741 ms × 35 bots in TRACK steady state that is ~3.1 s CPU/hour, of which ~3.09 s is waste.

**Fix:** memoize `(summary, bb_result, tightening)` on `(len(raw_candles), raw_candles[-1][0])`. Not a behaviour change — the bot already sees frozen candles for the whole TTL window, so derived TA is already frozen in fact, just not in code. Price-sensitive logic is unaffected (`ticker.last` comes from the separate 5s ticker path at `:4968`). In sim `_data_pool` is None and the master clock advances every tick, so the key changes each tick and the memo correctly no-ops — no sim/live divergence introduced.

## F7 — Nuclear Mode start leaks 3 permanent global-EventBus subscribers plus a whole BotManager graph, per start **[V, high→medium]**
`nuclear_controller.py:253-254` builds a `BotManager`, whose `__init__` sets `self._bus = get_event_bus()` (`bot_container.py:1423`) and subscribes three bound methods to it — `profit.cross_bot` (`:1461`), `wire.created` (`:1465`), `wire.removed` (`:1466`) — **before** line 254 rebinds the attribute to the sim bus. The rebind is cosmetic. `_build_context()` runs on every `start()` (`:132`), and `stop()` unsubscribes only `self._bus_unsubs` (`:172-177`), which are the sim-bus subscriptions from `:302-304`. `nuclear_mode_panel.py:406` additionally drops the controller on a failed start without even calling `stop()`. `EventBus` holds strong refs (`event_bus.py:113-114`), so nothing is collectable.

**Corrected blast radius:** consequence (b) as originally written is overstated. `_on_wire_created_mgr` (`:1474-1485`) registers into the *leaked* manager's own private `SmartWireManager`, and `_on_cross_bot_profit` (`:1498-1528`) looks up the leaked manager's own `_bots` dict — a live wire drag does wasted work in a dead object graph but does **not** corrupt live wire or P/L state. The real defect is unbounded per-start growth of `_subscribers`, each entry then walked under the lock on every global emit.

**Fix:** accept the bus as a constructor argument — `BotManager(bus=None)` defaulting to `get_event_bus()` — so `_build_context` passes `self._sim_bus` and the subscriptions never touch the global bus. Add a test asserting `len(get_event_bus()._subscribers['wire.created'])` is unchanged across a Nuclear start/stop.

## F8 — `ScrummingBot._memorised_trades` grows forever; its only consumer has zero callers **[V, high→medium]**
Appended unconditionally on every successful fill — sell at `scrumming_bot.py:10285`, buy at `:10883` — with no trim anywhere. Declared at `:319`. Each entry retains a full `VotingSummary`, which holds `signals: list[Signal]` (`ta_engine.py:103`), each `Signal` holding a `details: dict` (`ta_engine.py:84`).

The only reader is `memorize_to_grid()` at `:10923`, and a repo-wide grep finds it nowhere outside its own body (`:10928`, `:10932-10933`, `:10960`) — no GUI, no tool, no test. Pure retention with no consumer, in the live trading process, on the hottest path. `memorize_to_grid` is also O(buys × sells) (`:10932-10945`), quadratic the moment anything calls it.

*The "10,759 bytes retained per trade / ~108 MB per 10,000 fills" figure could not be independently reproduced — treat as **unmeasured**.* Even accepting it, growth is bounded by real fill frequency (tens per bot per day), so this is slow retention, not a near-term OOM.

**Fix:** delete both, or bound with `deque(maxlen=…)` at `:319` and stop retaining `voting_summary` — store `consensus_confidence`/`consensus_direction` scalars, all `memorize_to_grid` would need. The retained Signal graph is the dominant cost, not the trade tuple.

## F9 — Sim orders share the process-wide `IdempotencyLayer` with live trading **[V, medium→low]**
`bot_container.py:1067-1075` resolves `get_idempotency_layer()`, a true process singleton with no sim variant (`idempotency.py:180-187`). `derive_coid` (`:102-124`) unconditionally inserts into `self._cache` and calls `_enforce_size_limit`. Sim's hot path routes through `guarded_place_order` at seven `scrumming_bot.py` sites (2816, 9004, 9213, 9566, 9788, 10211, 10817).

**Unproven consequence — do not repeat it as fact.** Evicting live entries requires >5000 distinct intents inside a 300 s window (`max_entries=5000` at `:91`, TTL 300.0 at `:90`, oldest-first at `:155-162`), and nothing in the repo measures sim fills per wall-second. *Unmeasured.* Rate the defect as **the shared mutable singleton itself**, not the eviction argument.

Coid collision is not the risk: the fingerprint includes `bot_id` and sim bot_ids are fresh uuids.

**Fix:** optional idempotency handle on `BotContainer` alongside the v3.24.31 `capital_registry` injection, defaulting to the singleton; sim controllers inject a private instance.

## F10 — `SmartWireManager._transactions` is an unbounded write-only audit list in the live process **[V, medium→low]**
Three append paths, no trim, no eviction: `smart_wire.py:621`, `:850`, `:947`. The instance is a live singleton (`bot_container.py:1459`, created once per BotManager, held for process lifetime), and the fold path is genuinely hot (`scrumming_bot.py:8296-8299`, once per wired target per compounding fold).

The only reader is the `stats` property (`:954-959`), and a repo-wide grep for `total_wired` returns exactly one hit — `:958` itself. Nothing consumes it. `WireTransaction` is a small dataclass, so a multi-day session accrues kilobytes — real dead-weight growth, no measurable operational cost.

**Fix:** `deque(maxlen=5000)` at `:228`. Note `:958` sums the whole list, so an unbounded list also makes `stats` O(n) if ever wired.

## F11 — `~/.acervator_logs/sim/runs/` directories are never pruned; the index caps at 500 and orphans the rest **[V, medium→low]**
`sim_run_log.py:365-366` truncates `index.json` to 500 entries; grep for `rmtree`/`.unlink(` across `sim_run_log.py` and `src/gui/simulator_tab/` returns **nothing**. Each replay mkdirs a fresh `runs/<run_id>/` (`fleet_replay_controller.py:315`; `sim_run_log.py:146-147`).

**Current measured state:** 68 run directories, 2,647,076 bytes, index (at `~/.acervator_logs/sim/index.json`, `:341` — *not* under `runs/`) at 68 entries. The cap is years away via the reachable Fleet Replay path. The overnight-soak scenario that crosses 500 depends entirely on `NuclearFleetController`, which has no production driver (W3). The module's own docstring at `:69-70` records the failure shape already occurring: *"54 of the 62 directories there were 4-to-59-candle test artifacts."*

**Fix:** in `_append_index`, `rmtree` the directories for entries that fall off the tail — the truncation already decides what is retained; directory removal just makes the two agree.

## F12 — Ring buffers implemented as O(N) list re-slice on every append **[V, low]**
`event_bus.py:159-161`, inside `emit()` under `self._lock` (acquired at `:137`), with `_max_history = 1000` (`:87`). Once saturated, every emit allocates and copies a 1000-element list while holding the lock all emitters contend on. Same anti-pattern with larger N: `analytics_engine.py:93-94` (`_max_trades = 50000` at `:85`), `reconciliation.py:99-100` (10000 at `:91`), `risk_manager.py:243-244` (8640 at `:187`), `volume_guard.py:276-278`.

All correctly **bounded** — not leaks — but trimmed O(N) instead of O(1). `grep -rn maxlen src/` returns a single hit: `main_window.py:3170`. The trim only fires at cap, so the cost is one 1000-pointer memcpy per emit — microseconds. Cleanup, not defect.

**Fix:** `collections.deque(maxlen=N)` at all five; only care needed is `event_bus.py:176` `get_history`, which slices.

## F13 — Correctness spillover found during the audit (affects live, not just sim)

**`split_distance_pct` reads a config field that does not exist** — `scrumming_bot.py:9741` **[1P]**. The `BotConfig` field is `split_distance` (`bot_container.py:253`; allowlist `:562`; restore path `:2492`); there is no `split_distance_pct` anywhere in `bot_container.py`. So the `getattr` always misses and the 1.0 fallback is used unconditionally, then passed as `split_distance_pct=split_dist` into `split_scrum_into_tranches` (`:9750`, consumed at `stack_math.py:207`). **Any operator who sets Split Distance to something other than 1.0 is silently ignored, on both live and sim — Stack tranches are always spaced at 1% steps.** The neighbouring lines read the correct names (`stack_tranche_count_target` at `:9740`, `stack_spacing_mode` at `:9742`), which is what makes this a typo rather than an alias. Fleet Replay does copy `split_distance` into the sim config (`fleet_replay_controller.py:160`), so the value survives the whitelist and is discarded here anyway.
**Fix:** rename to `"split_distance"`. Add a fitness check that flags `getattr(self.config, X)` where X is not a `BotConfig` field — this class of bug is invisible by construction.

**`ChartsTab.log_trade()` has zero callers — tactical chart markers never render** — `main_window.py:1212` **[V]**. `self._trade_log` is declared at `:977` and this is its only writer; repo-wide grep finds no caller (the other `log_trade` hits are the unrelated bus-wired `LogManager.log_trade` at `logging_engine.py:338`). So the consumer at `:1066-1073` always filters an empty list and `set_trade_history_markers` (`native_chart.py:394`) is never reached with data — against the operator directive quoted in-code at `:1058-1059` ("*a tactical aid showing where soldiers are on the battlefield and where they have been fighting*"). Safe only because it is dead: wire it without a cap and `_trade_log` becomes an unbounded per-session list scanned linearly for every bot on every 2-second dashboard refresh (`:4820`, timer `:4407`).
**Fix:** subscribe ChartsTab to `trade.filled` alongside the other handlers at `:3159-3171`, bound `_trade_log` with `deque(maxlen=…)`, and replace the linear scan at `:1066` with a `dict[(bot_id, symbol)] -> deque` index.

**Detonation check builds a throwaway `VotingEngine` with DEFAULT weights and bypasses the pool** — `scrumming_bot.py:9486` **[1P]**. `VotingEngine()` with no weights falls back to `DEFAULT_WEIGHTS.copy()` (`ta_engine.py:2436`), discarding `self._voting_engine` built with the bot's configured weights (`:381`). **Latent today**: nothing outside `phantom_balance.py` ever passes `ta_weights`, so both resolve to defaults. The moment weights become operator-configurable, a full-position harvest votes with different weights than every other decision. Same pattern at `:5671`. Separately `:9473` calls `self.exchange.get_ohlcv(...)` directly rather than `self._get_ohlcv`, skipping the pool the neighbouring site was explicitly converted to use (v3.23.74 note at `:5665-5666`); rate-limited to 1/hour/bot (`:9466`), so 35 uncoalesced 1d fetches/hour where an 86400s TTL would collapse them.
**Fix:** both one-liners, zero behaviour delta today.

## F14 — Concurrency: the v3.24.19 snapshot handoff crosses no thread boundary **[1P]**
Not a defect — a **wrong causal story left in the docstrings**, which is how the next throughput regression gets misdiagnosed.

There is exactly one driver of the app's asyncio loop: `main.py:965-968` `def pump_async(): loop.call_soon(loop.stop); loop.run_forever()` bound to `async_timer.timeout` with `start(50)` at `:971-972`. A QTimer created on the main thread fires on the main thread, and `grep run_forever` over `src/` + `main.py` returns only that site plus a docstring copy at `fleet_replay_controller.py:371`.

So `_on_visual_refresh_tick` — documented "Runs on the asyncio worker thread" (`fleet_replay_panel.py:1109`) — and `_drain_visual_snapshot` — "Runs on the Qt main thread" (`:1221`) — execute on the **same** thread. Therefore: (a) `self._snapshot_lock = threading.Lock()` (`:150`) guards a boundary that does not exist; (b) the docstring claim at `:1117-1123` that the pre-v3.24.19 code "was cross-thread widget access, which Qt does not define" is factually wrong — it was same-thread, just expensive; (c) the independence claim is false, since the drain timer runs on the thread that pumps asyncio, so 35 gate cells + 35 chart appends + `chart.update()` block the pump for their whole duration.

What v3.24.19 actually bought is a bounded repaint **frequency**. The 19× throughput gap was closed by the yield budget in v3.24.20 (`_maybe_yield`, `fleet_replay_controller.py:361-416`), not by the snapshot.

**Fix:** correct the three docstrings to "replay task (same thread, pumped from the Qt QTimer)" and restate the benefit as bounded repaint frequency. Keep the lock — harmless, and correct if the loop ever moves to a thread — with a note saying why.

**Related, and worth fixing because cited line numbers get clicked:** `fleet_replay_controller.py:367` and `:41` both point at `main.py:955`, which is inside a `log_manager.warning` string about `BotManager.set_async_loop wiring failed`. The pump is at `main.py:965-968`. The stale reference has propagated into the brief for this audit. Cite `main.py pump_async` rather than a line number so it survives the next edit.

## F15 — `_make_sim_capital_registry` leaks one `tempfile.mkdtemp` directory per replay **[1P]**
`fleet_replay_controller.py:116` — `grep -rn "acervator-sim-crr"` finds only this line: no `rmtree`, no `TemporaryDirectory` context, no `atexit`. One directory per `_build_sim()` call (`:508`) = one per Start Replay click. `autosave=False` means they stay empty, so clutter rather than disk pressure — but under Nuclear Mode as designed it is one per worker per cycle, i.e. hundreds over a multi-hour soak, for a harness whose point is running "forever under varying load".
**Fix:** hold a `tempfile.TemporaryDirectory()` as an instance attribute so cleanup follows the controller's lifetime.

---

# EXPLICIT CALLOUT: WHERE SIM **DISABLES** A FEATURE INSTEAD OF ISOLATING IT

Standing operator directive: *"simulator equivalents with all of the same functionality except that operate in a simulated environment — features must be SIMULATED, never switched off."*

| # | Site | What is switched off | Status |
|---|---|---|---|
| 1 | `nuclear_controller.py:321` | `enable_phantoms=False`. Real subsystem switch, not a no-op — `scrumming_bot.py:309` defaults it ON, `:447` stores it. The **only** GUI-reachable nuclear path, so the phantom subsystem is never exercised there. The fleet path was corrected in v3.24.31 with the rationale spelled out inline at `fleet_replay_controller.py:202-207`: *"enable_phantoms=False removed the subsystem from sim entirely… Phantom balance is per-bot in-memory state, so enabling it needs no external isolation — it was simply switched off."* **[V]** | **Open. One-line fix.** |
| 2 | `fleet_replay_controller.py:512` and `nuclear_controller.py:264` | `fee_pct=0.0`. The fee machinery exists and works (`sim_exchange.py:405`, `:407`, `:410`, `:443-444`) and is simply passed zero. `get_markets` compounds it by advertising a free venue (`:562`) where the live connector reports real values (`ccxt_connector.py:1177-1178`). **[V]** | **Open.** See F/D3. |
| 3 | `scrumming_bot.py:1966` | `_emit_trade_notification` early-returns on `_sim_mode`, deleting the SENT/PLACED/FILLED/CANCELLED lifecycle trace from sim. The guard was written at v3.24.1, **before** v3.24.12 gave each sim bot a private bus (`:345-377`) — its own rationale ("every simulated fill emits on the *shared* bus") no longer holds, so it is now a redundant guard on top of a working isolation boundary. The cost is real diagnostic signal: CANCELLED carries *why a trade did not fire*, e.g. `:10115-10117` `"capital reservation (avail …)"`. In a replay the operator sees the trade not happen with no recorded reason. **[1P]** | **Open. Delete the early return**; gate at the main_window subscriber if sound-engine silence is still wanted. |
| 4 | `sim_exchange.py:249` | `del timeframe` — the multi-TF feature is collapsed rather than simulated, so the HTF bias gate can never express a genuine disagreement. **[V]** | **Open.** See D4. |
| 5 | `bot_state_loader.py:68` + `_wire_topology` absent from Fleet Replay | Smart Wire — the compounding mechanism — is absent from every replay. 40 live wires → 0. **[1P]** | **Open.** See W1. |
| 6 | `fleet_replay_controller.py:150-196` | 44 of 70 live config fields silently revert to dataclass defaults. Not "disabled" by intent, but the operator-visible effect is that configured behaviour vanishes with no error and no log line. **[V for `trading_fee_pct`]** | **Open.** See D2. |
| 7 | `bot_container.py:871` / `:1571-1583` / `:2018-2021` | `VolumeGuard` and `MarketDataPool` are populated only by `BotManager`, which `FleetReplayController` never constructs — `_build_sim` appends straight to `self._bots` (`fleet_replay_controller.py:517-524`). So the guard branch at `bot_container.py:1027` is never taken (every sim order is one whole-size fill, and the partial-fill/failure path at `:1035-1037` cannot reproduce), and `_data_pool is None` means the sim always takes the direct-fetch fallbacks (`scrumming_bot.py:2352`, `:2381`, `:2403`) and never exercises cache coherency including `invalidate_balance` (`:2428`). "Never wired" rather than "explicitly disabled" — identical operator-visible result. Both are per-instance objects with no live file or singleton backing, so isolation is free. **[1P]** | **Open.** Same shape as the injected capital registry. |
| 8 | `scrumming_bot.py:4573` | Sim gate-emit failures are recorded under the hardcoded **`'live.'`** telemetry namespace, then persisted into `~/.acervator/feature_telemetry.json` by F1. The rest of the sim namespaces under `'sim.'` (`fleet_replay_controller.py:777`). Polluting a live counter from sim degrades exactly the signal the file exists to provide. Exception branch only; one-line fix: `("sim." if self._sim_mode else "live.") + "gate_decision.emit"`. **[1P]** | **Open.** Audit every `get_telemetry()` call reachable from a sim bot for the same prefix. |

### Inverse violation — sim runs features live currently does *not*
Two sites where the sim is **not equivalent in the other direction**, which is equally a fidelity defect:

- `bot_state.json` records `phantoms_enabled=False` on all 35 saved bots, and `_instantiate_bot` never reads that field. Live runs **zero** phantoms; sim runs **six**. **[V]**
- `fleet_replay_controller.py:151` overwrites `exchange_id='coinbase'` with `'fleet_sim'`, which is absent from `_AVAILABILITY` (`timeframes.py:36-62`), so `available_timeframes` returns the permissive `ALL_TIMEFRAMES` (`:76-77`) instead of Coinbase's list, which excludes `4h` (`:39`). **Empirically proven** in `~/.acervator_logs/console/system.log` P0g-DIAG rows: exactly two timeframe lists exist — `['5m','15m','30m','1h','1d']` (1,863 rows, coinbase bots) and `['5m','15m','30m','1h','4h','1d']` (282 rows, sim bots). So sim carries a 4h phantom that cannot exist on Coinbase. **[V, medium→low]** — largely subsumed by D4; on its own it adds one duplicate 4h vote inside an already-fabricated bias. Fix by passing `cfg.get('exchange_id','coinbase')` through and gating sim-awareness on `sim_mode`, not a spoofed venue name.

*Evidence caveat carried from the verifier:* every P0g-DIAG row in the captured log shows `_phantoms_enabled=False`, i.e. **no captured run has yet exercised the v3.24.31 `enable_phantoms=True` path**, and `~/.acervator_logs/console/system.log` contains zero fleet-replay lines for 2026-08-05. D4/D-inverse rest on code, not on that log.