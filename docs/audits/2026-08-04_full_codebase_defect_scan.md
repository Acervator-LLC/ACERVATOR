<!-- Acervator v3.24.20 — generated 2026-08-04 -->

# Whole-Codebase Defect Scan

**Agents:** 26  
**Findings surviving verification:** 164  
**Refuted:** 0  
**By class:** `{"broken-ref": 15, "dead-feature": 29, "silent-failure": 8, "correctness": 36, "data-integrity": 15, "duplication": 5, "scaffolding": 28, "stale-doc": 22, "error-handling": 3, "threading": 3}`

---

# Acervator v3.24.19 — Needed-Fixes List

**Scope:** correctness + dead-code defects across 174 source files / 96,425 lines. 164 partition-level claims merged into 108 work items. Time-space complexity is out of scope (see [Deliberately Not Listed](#deliberately-not-listed)).

**Section rule used for P0 vs P1:** an item is P1 if fixing it *changes live order flow or live-persisted state*. Everything else that is broken today is P0, regardless of which directory it lives in.

---

## Count by severity

| Section | Items | Confirmed by verifier | `[UNVERIFIED PROOF]` |
|---|---:|---:|---:|
| **P0 — Broken now** | 15 | 8 | 7 |
| **P1 — Shared with live (gated cascade)** | 21 | 11 | 10 |
| **P2 — Dead weight** | 38 | 19 | 19 |
| **P3 — Misleading docs/comments** | 20 | 12 | 8 |
| **P4 — Hardening** | 14 | 6 | 8 |
| **Total** | **108** | **56** | **52** |

`[UNVERIFIED PROOF]` = the adversarial verifier did not re-run the evidence. The claim may still be right; check the proof before budgeting time.

### Top 10 by bite (crosses sections)

| # | Item | Section | Why it's here |
|---:|---|---|---|
| 1 | `main.py:664/1107` UnboundLocalError on fresh install | P0-1 | App does not start on a new machine |
| 2 | `ccxt_connector.py:876` `limit` lands in ccxt's `since` slot | P1-1 | Every Coinbase OHLCV fetch may return empty |
| 3 | `scrumming_bot.py:5445` `_sum_sibling_base_currency_claims` missing | P1-2 | Bot cannot enter a position; error/cooldown loop |
| 4 | Stack Mode cluster (`9563` / `9810` / `stack_math.py:138`) | P1-3 | Opt-in feature raises on first SCRUM |
| 5 | `scrumming_bot.py:6878` SCRUM sizing missing `_quote_to_usd` | P1-4 | 100,000× oversized sell on crypto-quoted pairs |
| 6 | `bot_visualizer.py:3045` `logger` undefined | P0-2 | Bot Swarm silently stops updating |
| 7 | `indicator_panel.py:383` RNG data rendered as live TA | P0-4 | Operator sanity-checks scrums against noise |
| 8 | `bot_visualizer.py:2556` GUI clobbers live `bot_state.json` | P0-7 | Fold tranches / main lots can revert |
| 9 | `history_tab.py:699` grader runs time backwards | P0-5 | Every Grade letter is inverted |
| 10 | `settings_dialog.py:978` six settings never re-read | P0-6 | Settings silently revert on every Save |

---

## P0 — BROKEN NOW

Wired up, reachable, and either non-functional or producing wrong data. No live-order blast radius, so these can ship in a normal cascade.

### P0-1. `main.py:1107` — `UnboundLocalError` kills startup when there is no saved bot state
`class=correctness` · **confirmed**

```python
if _autostart_bot_count > 0:
```
The only Store of `_autostart_bot_count` is `main.py:699`, nested inside `if state_mgr.has_saved_state():` (`main.py:664`). The Load at 1107 is at `main()` body indentation. `has_saved_state()` returns False on fresh install, on "operator deleted all bots", and on a parse failure (`state_manager.py:164-173`).

**Operator sees:** splash appears, app dies before `app.exec()`. Traceback goes to `~/.acervator_logs/crash_*.log`, so the visible symptom is "Acervator flashes a logo then vanishes." This is the Mac-Mini / new-machine install path.

**Fix:** insert `_autostart_bot_count = 0` immediately before `main.py:664`.

---

### P0-2. `src/gui/bot_visualizer.py:3045` — `logger` is undefined; the "best-effort" handler raises `NameError`
`class=broken-ref` · `[UNVERIFIED PROOF]`

```python
except Exception as _rl_exc:  # noqa: BLE001 - list mirror best-effort
    logger.debug("list-view row refresh raised: %s", _rl_exc)
```
The module never imports `logging` and never binds `logger`; line 3045 is the only occurrence of the name in 3,257 lines. The `NameError` escapes `update_bots()` entirely (called at `main_window.py:4826`), aborting the exchange-selector rebuild, visible-bot filter, quick-routing scope and wire-canvas raise at 3048-3082.

**Operator sees:** Bot Swarm grid + list freeze on stale data with no log line.

**Fix:** add `import logging` / `logger = logging.getLogger("acervator.gui")` at module top, matching `native_chart.py:19-24`.

---

### P0-3. `src/gui/start_all_progress_dialog.py:108` — reads `event.payload`; `Event` only has `.data`
`class=silent-failure` · **confirmed**

```python
phase = event.payload.get("phase", "")
```
`event_bus.py:34-48` defines `Event(topic, timestamp, data)` with a `__getattr__` that raises `AttributeError("Event has no data field 'payload'")`. All six emits in `BotManager.start_all` (`bot_container.py:2858-2909`) pass kwargs into `data`. The bare `except Exception: pass` at 113-114 eats it, so `_handle_progress_main_thread` is unreachable.

**Operator sees:** Start All pops a dialog stuck on "Preparing to auto-start bots…" with an empty list and a disabled Close button for the whole staggered start, then never auto-dismisses. Live path confirmed at `main_window.py:6302`.

**Fix:** `event.payload.get(...)` → `event.data.get(...)` ×4; replace the bare `pass` with `logger.exception`.

---

### P0-4. `src/gui/indicator_panel.py:383` — synthetic RNG TA rendered under the operator's real symbol
`class=data-integrity` · **confirmed**

```python
QTimer.singleShot(3000, self._auto_init_demo)
```
Three paths inject fake data: `_auto_init_demo` (874-879), `_on_bot_selected` (793-802), and `force_refresh` (881-892, clears `_data` then regenerates unconditionally). `_generate_demo_ta` builds 60 candles from `rng.gauss(0, 0.015)` (827-836), runs the **real** VotingEngine, and pushes through the normal `update_data(..., sym_text)` path (866) with the unmasked bot label (848-851). No badge, no tooltip, no style branch distinguishes it.

**Operator sees:** three seconds after launch, a fully populated 12-indicator voting matrix labelled `BONK/USD` derived from a gaussian random walk — the panel used to sanity-check scrum/fold timing.

**Fix:** delete the demo path, or gate it behind an explicit debug flag **and** force `_symbol_label` to `"SIM"` + a "DEMO DATA — NOT LIVE" banner until the first real `update_data`.

---

### P0-5. `src/gui/history_tab.py:699` — trade grader inverts past and future
`class=correctness` · **confirmed**

```python
if j < row_i:
    same_sym_prior_prices.append(op)
elif j > row_i:
    same_sym_future_prices.append(op)
```
`history_helpers.py:295` sorts `reverse=True` ("Returns newest-first list", docstring line 252). `_apply_filters` (491-505) and `_render_page` (534) preserve order. So a **lower** index is a **later** trade. `ref_price_at_decision` is the median of post-trade prices; `future_prices` is filled with pre-trade prices. `trade_grader.py:71` documents `future_prices` as "next N candles **after** the trade."

**Operator sees:** every Grade letter is computed with time reversed. Buy-the-dip grades F; chasing a top grades A. The tooltip confidently explains the wrong verdict.

**Fix:** swap the two append targets for a newest-first page; take `same_sym_prior_prices[:5]` not `[-5:]`. Pin with a synthetic buy-the-dip → A test.

---

### P0-6. `src/gui/settings_dialog.py:978` — `_load_current` never reads back six+ settings that `_save` writes
`class=data-integrity` · **confirmed**

`_save` (1022-1123) persists `bot_visibility`, `aggressive_trading`, `font_family`, `font_size`, `heading_font_size`, `log_font_size`, the profit-folding target/count fields and the data-logging periodicities. `_load_current` (978-1020, the sole restore path, called once at line 74) restores none of them, so the widgets come up at their construction defaults (`_visibility` index 0 at 380, `_font_size` 11 at 526, `_fold_all` checked at 410, `_log_24h`/`_log_1w` at 575/577) and the next Save overwrites the persisted values with those defaults.

**Operator sees:** "my settings don't stick" — font sizes, bot visibility, fold target and P/L log periodicity revert every time Settings is opened and saved for any unrelated reason. Dialog is live (`main_window.py:6321`, `6468`).

**Fix:** extend `_load_current` to read every key `_save` writes. Add a set→save→reconstruct→assert round-trip pin test.

---

### P0-7. `src/gui/bot_visualizer.py:2556` — Quick Routing does a whole-file read-modify-write of the operator's live `bot_state.json`
`class=data-integrity` · `[UNVERIFIED PROOF]`

```python
p = Path.home() / ".acervator" / "bot_state.json"
tmp = p.with_suffix(".tmp")
tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
tmp.replace(p)
```
Three compounding problems: (a) **same temp path** as `StateManager.save_state` (`state_manager.py:59`, `103` → identical `~/.acervator/bot_state.tmp`), so two unsynchronised writers can promote a half-written document; (b) **no backup** — StateManager copies to `bot_state.backup.json` first (108-112), this path does not; (c) **whole-document clobber** from a stale in-memory snapshot. Worse, the key it writes (`scrumming_state.smart_wire_routes`) is not in the persistence schema at all — `grep -c "smart_wire_routes" src/trading/scrumming_bot.py` → **0**, so `save_all_state()` erases it anyway.

**Operator sees:** clicking Connect / Disconnect / Disconnect All in Quick Routing can revert fold tranches, main lots, circuit-breaker trip state and target-balance anchors to whatever was on disk when the panel loaded.

**Fix:** stop writing `bot_state.json` from the GUI. The handlers already emit `wire.created`/`wire.removed`, which `BotContainer._on_wire_created_mgr` (`bot_container.py:1465-1495`) consumes and `SmartWireManager.export_wires()` persists under the schema's own `smart_wires` key. Delete `_save_bot_state_dict`, `_apply_routes_to_state`, `_clear_all_routes_in_state`; point `_hydrate_smart_wire_routes_from_disk` at `state["smart_wires"]`.

---

### P0-8. `src/gui/main_window.py:1511` — Ammo column takes `max()` of stale and fresh position value
`class=correctness` · `[UNVERIFIED PROOF]`

```python
# Prefer the LARGER of stats.position_value and freshly
# computed — whichever is non-zero is the real exposure.
position_val = max(stats_pv, fresh_pv)
```
The comment says "whichever is non-zero"; `max()` selects whichever is larger. `stats.current_price` is written at `scrumming_bot.py:4574`/`4803` and `_current_holdings` at `4702`/`8655`/`8878`/`9429`, but `stats.position_value` only at `5655` — any tick that updates price then returns early leaves `position_value` stale while price is fresh. Bias is one-directional: it can only overstate.

**Operator sees:** 100 units, last `position_value` write $200 @ $2.00, price falls to $1.50. `max()` → $200. Target $175: true delta −$25 (Fold, red, BUY) renders as +$25 (Scrum, green, SELL). The primary decision surface shows the opposite trade direction — the exact column MEM-248/MEM-250 exist to make trustworthy.

**Fix:** `position_val = fresh_pv if fresh_pv > 0 else stats_pv`; update the comment. Optionally export `position_value_ts` so the GUI can pick by freshness explicitly.

---

### P0-9. `src/gui/simulator_tab/fleet/fleet_replay_panel.py:723` — every symbol reports a fake tablet shortfall
`class=correctness` · `[UNVERIFIED PROOF]`

```python
_shortfall = max(0, _expected_per_sym - len(rows))
```
`_expected_per_sym` is computed once at 673-674 from the **full** YTD span (`(now_ms - YTD_START_MS)/86_400_000 * 288`). v3.24.16 then narrows the fetch window at 700-706 (`_since_ms = _win.replay_start_ms`) and fetches `[soft_start, now]` at 715-720. The two spans are never reconciled.

**Operator sees:** with the soft-start cap active, the Activity Log reports every tablet at ~40 % coverage with a ~20,000-candle shortfall, and lines 770-773 instruct the operator to re-run `stone_tablets.fetcher build-ytd` to fix tablets that are already complete — a command that itself refuses to run (P0-11).

**Fix:** move the `_ytd_days` / `_expected_per_sym` computation after `_since_ms` is finalised (line 706) and base it on `(now_ms - _since_ms)`. Drop the hardcoded "(122 days × 288 5m candles)" literal at line 743, which contradicts the computed value in the same string.

---

### P0-10. `fleet_replay_panel.py:1061` — `NameError` in the stat-strip handler aborts the whole drain frame
`class=correctness` · `[UNVERIFIED PROOF]`

```python
except Exception as _ap_exc:  # noqa: BLE001
    _tel_exc("sim.stat_strip.feed", _ap_exc)
    logger.debug("stat strip feed raised: %s", _ss_exc)
```
`_ss_exc` is the except-target of a *different* method (`_collect_stat_fields`, line 1044) and Python deletes that name at block exit. `_apply_stat_fields` is called unguarded at 1183 inside `_drain_visual_snapshot`; the per-symbol try only starts at 1185.

**Operator sees:** any stat-strip write failure (deleted widget after Reset mid-drain) kills the entire 250 ms drain frame — gate lights, price+VWAP chart and voting readout all skip.

**Fix:** `logger.debug("stat strip feed raised: %s", _ap_exc)`.

---

### P0-11. Stone Tablets fetch subsystem is unreachable and its two remedies point at each other
`class=dead-feature` · `[UNVERIFIED PROOF]`

- `src/trading/stone_tablets/fetcher.py:130` — `CoinbaseAdapter.fetch_chunk` passes `since=since_ms/1000.0` to `get_ohlcv`. **No connector accepts `since`**: `base.py:192-194` and `ccxt_connector.py:869-871` are both `(symbol, timeframe='1h', limit=100)`. `TypeError` on the first call, swallowed by the `except Exception` at 153, 30 s of backoff per chunk, 0 candles. Also `/1000.0` would be wrong by 1000× even after the parameter is added.
- `fetcher.py:671` — the CLI refuses `build-ytd`/`universe`/`ensure` and redirects to a Simulator button *"Fetch missing coverage"* that does not exist anywhere in the tree. `fleet_replay_panel.py:770-773` redirects back to the CLI. `BuildOrchestrator`, `build_universe`, `build_ytd`, `ensure_asset_coverage`, `GapFiller`, `CoinbaseAdapter` have zero callers outside `fetcher.py`.

**Operator sees:** 406 tablets all end 2026-08-01, `main.py:492` reports them stale at boot, and there is no working path to un-stale them — the operator bounces between a CLI that says "click the button" and a panel that says "run the CLI."

**Fix:** add `since_ms: Optional[int]` (milliseconds, integer) to `ExchangeInterface.get_ohlcv` and `CcxtConnector.get_ohlcv`; change `fetcher.py:130-133` to `since_ms=int(since_ms)`. Then either build the Simulator action (`ensure_asset_coverage(asset, exchange_id, connector)`) or rewrite both messages to name the real procedure. Add a test that drives `CoinbaseAdapter.fetch_chunk` against a stub whose signature matches `ExchangeInterface.get_ohlcv` exactly — today `tests/test_stone_tablets_fetcher.py:53` overrides `fetch_chunk` wholesale and covers nothing.

---

### P0-12. `src/gui/market_inspector.py:322` — `_status_line` has no branch for the only source the fetcher emits
`class=correctness` (reported as stale-doc; it is executing code) · **confirmed**

`_status_line` recognises `"coingecko"`, `"cache"`, `"error"`, `"network-partial"`. `market_inspector_fetcher.py` only ever sets `meta["source"]` to `"exchange"` (282, 294) or `"no-exchange"` (232, unreachable behind the guard at 262). A successful scan falls through to the terminal `return "No data yet — press Refresh."`

**Operator sees:** presses Refresh, waits 10-30 s, watches the HTF Signals and Opposing Pairs tables fill with real rows — and the status label says "No data yet." Market count, elapsed time and partial-connector errors are never surfaced. Tab is live (`main_window.py:3715`, `3732`).

**Fix:** add an `"exchange"` branch rendering `symbol_count` + `elapsed_seconds` + optional partial-error tail. Delete the dead `coingecko` / `network-partial` branches.

---

### P0-13. `src/gui/simulator_tab/nuclear_controller.py:298` — Nuclear scout built without `sim_mode=True`, writes sim reservations into the live capital registry
`class=data-integrity` · `[UNVERIFIED PROOF]`

```python
scout = ScrummingBot(cfg, self._exchange, enable_phantoms=False)
```
Fleet does it right: `fleet_replay_controller.py:150-152` passes `sim_mode=True`. `ScrummingBot._ensure_capital_reservation` (`scrumming_bot.py:956`) is gated **only** by `if getattr(self, "_sim_mode", False): return` at 987, and its v3.24.14 comment records the prior leak: *"16,558 bot_ids in that file against 35 real ones — 16,523 orphans, 6.5 MB."* Setting `scout._bus` at line 299 closes the event-bus route but not the on-disk `~/.acervator/reservation_state.json` route — which the same comment calls out as "worse … survives on disk and feeds live allocation decisions."

**Operator sees:** latent only because Nuclear Mode has no tapes today. Arms the moment tapes are re-pointed at Stone Tablets.

**Fix:** add `sim_mode=True` at line 298 and drop the now-redundant `scout._bus = self._sim_bus` at 299.

---

### P0-14. Sim candle addresses are window-relative, violating `addressing.py`'s stated contract
`class=correctness` · `[UNVERIFIED PROOF]`

`src/gui/simulator_tab/fleet/sim_exchange.py:344` — `format_address(ticker_from_symbol(symbol), idx)` where `idx` comes from `series.cursor`, and the series was built from the windowed slice (`fleet_replay_panel.py:715-720`, `_since_ms` = the v3.24.16 soft-start cap). `addressing.py:37-41` states: *"The index is the position within THAT TABLET'S full candle list … NOT a global clock tick."* Every stamped address is offset by the number of tablet candles before the soft-start, and the offset moves when the soft-start moves. Related: **`fleet_replay_controller.py:659`** `build_anchor_indices` divides by a nominal 300,000 ms step while the consumer compares against MasterClock **union** indices (`master_clock.py:62-76`), and the panel sizes anchor space with `max(len(r))` (883-884) instead of `total_clock_ticks()`.

The one validator that would catch this — `sim_validation_guard.py:325-334` `ADDRESS_MISMATCH` — has zero callers, and `verify_addressing_stable` (`addressing.py:184`) is referenced only by tests.

**Operator sees:** "at 1234_BTC live fired BUY; did the sim gate arm at 1234_BTC?" silently compares different candles. Anchored runs (the default) can evaluate candles that are not the ones carrying historical trades.

**Fix:** resolve addresses from the timestamp via the existing `address_for_ts(symbol, full_tablet_rows, sim_ts_ms)`, which is immune to windowing; build anchors by bisect against `exchange.master_clock.timestamps`; replace `_n` at panel 883-884 with `exchange.total_clock_ticks()`. Then wire `validate_trade_event`.

---

### P0-15. Release-readiness gate can print `[OK] Release-ready` with zero checks run
`class=silent-failure` · **confirmed**

Two compounding holes in the mechanism the operator's own rule depends on:

| File:line | Defect |
|---|---|
| `tools/harness/check_release_readiness.py:193` | `--no-pytest --no-archetypes --no-claims` short-circuits all three checks (165, 173, 180); `failures` stays empty; the identical `[OK] Release-ready (vX.Y.Z, 0 tests)` banner prints and a green sidecar is written. The sidecar payload (133-138) records no skip state, and `.claude/hooks/verify_release_gate.py:67-81` gates only on `timestamp` — never `tests` — so a `tests: 0` sidecar unblocks Write/Edit on `src/__init__.py`. |
| `tools/harness/coding_archetype.py:213` | The `"missing"` branch can never fire for the four tools invoked as `[sys.executable, "-m", …]` (ruff 293, mypy 342, bandit 408, vulture 448). A missing module returns rc=1 with **empty stdout** (diagnostic goes to stderr, never read), each runner takes its `if not proc.stdout.strip(): return findings, "ok"` early-out, and the report is green. Reproduced: four dead tools → `tool_availability` all `"ok"`, `errors: []`, `passed: True`. Same pattern at `gui_archetype.py:495`/`528` and `docs_archetype.py:267`. Latent on this machine (all six installed); fires on a fresh clone / CI / the Mac-Mini install. |

**Fix:** (a) when any `--no-*` flag is set, refuse to write the sidecar and print `[SKIP]`/`[PARTIAL]`; add a `checks_skipped` field and make `verify_release_gate.py` deny when non-empty. (b) in each `_run_*`, when `returncode != 0 and not stdout.strip() and "No module named" in stderr`, raise `FileNotFoundError` so the existing `missing` branch fires.

---

## P1 — SHARED WITH LIVE (own gated cascade)

Every item below is in `src/trading/` or `src/exchange/` **and** changes live order flow or live-persisted state. Ship these behind `tools/check_release_readiness.py` with per-item regression tests.

### P1-1. `src/exchange/ccxt_connector.py:876` — `limit` is passed into ccxt's `since` slot
`class=correctness` · `[UNVERIFIED PROOF]` · **highest-impact unverified item in the list — check this first**

```python
data = await self._call_sync(self._ex.fetch_ohlcv, symbol, timeframe, limit)
```
`_call_sync(self, fn, *args, **kwargs)` (489) forwards positionally. ccxt's signature is `fetch_ohlcv(symbol, timeframe='1m', since=None, limit=None, params={})` — the third positional is **`since`**. So `limit=100` becomes 100 ms since epoch; ccxt's own `limit` stays `None`. Inside `ccxt.coinbase.fetch_ohlcv` that yields `request['start'] = '0'` and `request['end'] = '0' + 300*granularity` — Coinbase is asked for the 300 candles beginning 1970-01-01.

**Operator sees:** every Coinbase OHLCV fetch returns `[]`; `ccxt_connector.py:882` logs "No data" for every `FETCH_OHLCV`; the 7-indicator TA engine gets zero candles on the live path. Live callers: `data_pool.py:449`, `data_pool.py:712` → `ScrummingBot._get_ohlcv` (`scrumming_bot.py:2233`).

**Fix:** `self._call_sync(self._ex.fetch_ohlcv, symbol, timeframe, None, limit)`, or a `functools.partial` with `since=None, limit=limit`. Add a regression test asserting the ccxt stub receives `since is None` and `limit == 100`.

**Verify first:** `python -c "import inspect, ccxt; print(inspect.signature(ccxt.Exchange.fetch_ohlcv))"` and one live `get_ohlcv` call against Coinbase.

---

### P1-2. `src/trading/scrumming_bot.py:5445` — `tick()` calls a method that does not exist
`class=broken-ref` · **confirmed**

```python
_sibling_claims = self._sum_sibling_base_currency_claims()
```
Not defined on `ScrummingBot` (AST walk: 75 methods, zero containing "sibling") nor on `BotContainer` (836-1411). The real helper is `BotManager.sum_sibling_base_currency_claims` (`bot_container.py:2218`) — a class `ScrummingBot` does not inherit from. The bridging wrapper was deleted; only `_archive/tests_pre_2026_07_25/test_scrumming_base_currency_claim_isolation.py` still references it.

**Reachability (narrowed by verifier):** with the default `max_cartridge_size_pct=10.0`, a fresh bot fires the CARTRIDGE branch and returns at 5278 before reaching 5445. The real triggers are `max_cartridge_size_pct = 0` (a documented, GUI-settable disable — `scrumming_bot.py:5023`, spin box at `bot_live_settings.py:2539`) or the hysteresis-block at 5189 which deliberately falls through ("Do NOT return", 5210).

**Operator sees:** not a crash — `bot_container.py:1162-1200` `_run_with_guard` catches it, increments `stats.consecutive_errors`, and cooldowns after `MAX_CONSECUTIVE_ERRORS`. The bot sits in an error/cooldown loop and never buys in.

**Fix:** re-add the wrapper delegating to `self._bot_manager` (set by `set_bot_manager`, 1075), returning `0.0` when it is `None`. Unit-test a manager-less bot driven through the initial-entry branch.

---

### P1-3. Stack Mode cluster — three defects, must ship together
`class=dead-feature + correctness` · **confirmed** · `stack_mode` defaults `False` (`bot_container.py:249`), so only opt-in operators are affected

| # | File:line | Defect |
|---|---|---|
| a | `scrumming_bot.py:9563` | `float(getattr(self.exchange_interface, "min_order_size", 0.0) or 0.0)` — **`ScrummingBot` has no `exchange_interface`**. `BotContainer` stores it as `self.exchange` (`bot_container.py:862`). `getattr` guards the *inner* name; the outer attribute access raises first. The line sits **above** the `try:` at 9565 and neither `_execute_sell` (9801) nor the SCRUM call site (6964) wraps it — `AttributeError` unwinds out of `tick()`. Even fixed, `ExchangeInterface` has no `min_order_size`; the real field is `AssetInfo.min_amount` (`exchange/base.py:140`). |
| b | `scrumming_bot.py:9810-9811` | `if _n > 0: return None` — the docstring five lines above (9789-9797) says it "Returns a sentinel **non-None** to signal handled." Every caller treats `None` as failure: SCRUM at 6973 emits "SCRUM ABORTED: sell failed", skips tranche creation, leaves `_main_lots` untouched. Since no units sold, `delta` is unchanged, the gate re-arms, and `_open_stack_from_scrum` appends another N tranches — **unbounded**, with no "stack already open" guard anywhere (`_stack_tranches` is only ever appended at 9635 and never pruned). In Visible mode each entry places a real LIMIT SELL (9608). |
| c | `stack_math.py:138` | `_apply_min_order_size` runs **after** `_apply_merge_rule` (212-215). Merging collapses the count but leaves surviving tranches at the original `scrum_size/n_target`. The guard compares `max_viable_n >= len(tranches)` — the post-merge **count**, not the per-tranche **size** — and early-returns "already fine." Reproduced: `split_scrum_into_tranches(100.0, 10.0, 4, 0.06, 'quadratic', 1.0, min_order_size=3.0)` → sizes `[5.0, 2.5, 2.5]` against a 3.0 floor, violating the module's own FALSIFICATION clause (line 31). |

**Why the 875-test suite is green:** `tests/test_stack_mode_execution.py:157` and `tests/test_stack_mode_visible.py:235` both set `self.exchange_interface = _StubExchangeInterface()` on a `_StubBot` whose docstring says *"NOT a ScrummingBot"*, then invoke the unbound method. The suite fabricates the attribute production lacks.

**Fix:** (a) `_min_amt, _min_cost, _ = await self._get_market_limits(self.config.symbol)` (`bot_container.py:899`, already awaited at 6911 and 7876) and pass `_min_amt`. (b) return a dedicated `STACK_OPENED` sentinel or set `self._stack_open_for_scrum = True` that the SCRUM caller checks before emitting ABORTED; add an `any(t["status"] == "pending")` guard at the top of `_open_stack_from_scrum`. (c) in `_apply_min_order_size`, check that **every** tranche size ≥ `min_order_size` and redistribute when any falls short. Add a merge-collapsing regression case and one end-to-end `stack_mode=True` SCRUM test.

---

### P1-4. `src/trading/scrumming_bot.py:6878` — autonomous SCRUM omits the quote-to-USD divisor
`class=correctness` · **confirmed** · manifests only when `_quote_to_usd != 1.0` (crypto-quoted pairs)

```python
scrum_asset = abs(delta) / ticker.last
```
`delta` is USD (`current_value = holdings * ticker.last * _quote_to_usd`, 4847-4849; `delta = current_value - _target_balance`, 5660). `ticker.last` is QUOTE. Every other sizing site converts correctly: `_execute_manual_rebalance` 8809-8810, `_execute_detonation` 9373, `_execute_buy` 10570-10571. Only the autonomous path was missed by the v3.15.55 sweep.

**Operator sees:** SOL/BTC bot, `_quote_to_usd = 100000`, 2 SOL @ 0.0015 BTC, target $250 → correct sell 0.333 SOL, computed 33,333 SOL (100,000×). The CRR gate at 9905 refuses it, so every autonomous SCRUM on a crypto-quoted pair logs "SELL REFUSED (capital reservation)" and never fires. If the CRR pre-check itself raises (swallowed at 9926) the order reaches the exchange, and on the success path `self._current_holdings -= amount` (10050) has no floor.

**Fix:** `_denom = float(ticker.last) * float(self._quote_to_usd or 1.0); scrum_asset = (abs(delta) / _denom) if _denom > 0 else 0.0` — mirroring 8809-8810. Regression test with `_quote_to_usd != 1.0` asserting the computed sell re-zeros the USD delta.

---

### P1-5. `src/trading/scrumming_bot.py:7309` — Smart Ceiling FOLD gate compares quote-denominated position to a USD ceiling
`class=correctness` · **confirmed** · requires crypto-quoted pair **and** `position_ceiling_enabled=True`

```python
_mem253_current_pos = float(self._current_holdings) * float(ticker.last)
```
Missing `* self._quote_to_usd`. Compared two lines later against `_anchor * _smart_mult_253` (7320-7322), where the anchor is operator-stated USD. Three sibling sites do it correctly: `ceiling_ratio` (3145-3146), the fold-taper log (7838-7841), `_pre_buy_allowed` (4092).

**Operator sees:** position understated by `_quote_to_usd`, so `_mem253_at_smart_ceiling` is effectively always False — the maturity stop never engages, the bot compounds past the configured `position_ceiling_multiple`, and no "FOLD HOLD (Smart Ceiling)" line is ever emitted. The wrong number is also written into `gate.log`'s `fold_fixture` (7440-7441), corrupting forensics.

**Fix:** add the factor, or better replace all four sites with the existing `self.position_value_usd` property (3014) so there is one implementation.

---

### P1-6. `_execute_buy`'s `cost` parameter has no documented unit — one caller passes USD, the other QUOTE
`class=data-integrity` · **PARTIAL — the original diagnosis was inverted at one anchor; read this carefully**

The verifier refuted the claim's primary anchor. Actual state:

| Site | Unit of `buy_cost` | Verdict |
|---|---|---|
| FOLD, `scrumming_bot.py:7856` | **QUOTE** — `_fusd = sum(t["usd"] …)` (7851) where the tranche `usd` field is derived at 7043 from `scrum_usd`, which 7188-7190 explicitly documents as *"scrum_usd is in QUOTE currency"*. Re-confirmed at 7874, 8209, 8219. | `buy_asset = buy_cost / buy_fill` at **7964 is CORRECT**. The defect is inside `_execute_buy`: **10570-10571** applies `amount = amount / _qrate_buy` to a cost that is already QUOTE, so the exchange **under-buys** by `_quote_to_usd` and `_current_holdings` is under-credited. |
| INITIAL ENTRY, `scrumming_bot.py:5593` | **USD** — `buy_cost = self._target_balance` | `_execute_buy`'s divisor is right here, so **5624** `bought_units = buy_cost / entry_fill` genuinely **overstates** units by `_quote_to_usd`. |

Either way the documented invariant breaks — `scrumming_bot.py:442`: *"sum(l["units"] for l in _main_lots) == _current_holdings"*, checked by `_main_lots_invariant_ok()` (10769-10781). And it is load-bearing: the init handshake rebuilds holdings from lots (`4702-4704`), and `_main_lots` is persisted (`export_scrumming_state`, 3288), so the corruption survives restart.

**Do NOT "add a `/_qrate`" at 7964** — that doubles the error.

**Fix:** give `_execute_buy` an explicit unit contract. Either rename the parameter (`cost_quote`) and have the initial-entry caller convert USD→QUOTE before calling, or add a `cost_is_usd: bool` and branch the divisor. Have `_execute_buy` return (or expose) the base-unit amount it actually placed, and have both callers append **that** rather than re-deriving `cost/fill`. Assert `_main_lots_invariant_ok()` in fold/entry tests with `_quote_to_usd != 1.0`.

---

### P1-7. `src/trading/extractor_bot.py:1377` — Inverted Extractor sizes its artillery SELL by 1/price too much
`class=correctness` · `[UNVERIFIED PROOF]` · claimed critical

```python
alt_units_to_buy = artillery_base / alt_price_in_base
```
For a NORMAL Extractor the pair is ALT/base (`_pair_filter_matches` keeps `m_quote == base_currency`), so `artillery_base` is QUOTE and the divide is right. For an **INVERTED** Extractor `_pair_filter_matches` keeps `m_base == base_currency` (737-739), so the pair is BASE/QUOTE where BASE **is** the ammo asset and `artillery_base` (from `_usd_to_base`, 695-699) is already in the pair's base units. Dividing again yields `base²/quote`. Identical bug at **`extractor_bot.py:1016`** (`_maybe_fire_correction`). Then `actual_base_spent = filled_units * fill_price` (1405) multiplies the error back out, so the internal ledger shows a correct-looking small debit while the wallet lost 1/price times that quantity.

Worked example: standing 5 LINK @ $20 (rate 20), `artillery_size_usd=5` → `artillery_base = 0.25 LINK`; pair LINK/BTC @ 0.0002 → order = 1250 LINK instead of 0.25 (**5000×**).

Test coverage: the only inverted tests (`_archive/tests_pre_2026_07_25/test_inverted_extractor_v3_20_74.py`) pin *which side* is used, never the *amount* — and that file is no longer in `tests/`. Inverted is operator-selectable at `bot_wizard.py:1288`.

**Operator sees:** the first artillery round on an Inverted Extractor attempts to sell the entire standing position (or the whole wallet balance of that asset), while the Pool/Chunk readouts continue showing a small correct-looking debit.

**Fix:** branch on `self._is_inverted` in both `_fire_artillery` and `_maybe_fire_correction`: for inverted, `amount = artillery_base` / `add_amount_base` directly, and `actual_base_spent = filled_units`. Regression test asserting the `amount` kwarg passed to `guarded_place_order` equals `artillery_base` within tolerance.

---

### P1-8. `src/trading/ta_engine.py:289` — ADX is on an accumulation scale ≈14× textbook; its own bands never fire
`class=correctness` · `[UNVERIFIED PROOF]`

`_wilder_smooth` (231-240) seeds `sum(values[:period])` and recurses in **sum** form — correct for DM±/TR (the scale cancels in `DI = 100*sDM/sTR`) but wrong for the DX series, where textbook ADX is the **average**. Result: `adx ≈ period * true_ADX`. The regime flags and confidence formula at 294-320 were written for the 0-100 scale and never recalibrated:

```
ranging      = adx < 20      # unreachable
developing   = 20 <= adx < 35 # unreachable
parabolic    = adx >= 50      # always True
confidence   = min(1.0, (adx - 35) / 30 + 0.5)  # saturates at 1.0
```
Measured on a 200-candle choppy synthetic: `adx=253.66, di+=15.86, di-=10.96` → true Wilder ADX 18.3 ("ranging"); 253.66/14 = 18.12. The repo already knows: `gate_chain.py:509-518` states *"`_wilder_smooth` accumulates rather than averages … ADX values spanning 62-681 with median 239"* — but **only the gate was recalibrated** (threshold 500 at `gate_chain.py:551`); the indicator's own bands were left at textbook values.

**Operator sees:** the dashboard ADX cell can never show "Rng NN" (`indicator_panel.py:1073`) — the accumulation-ideal regime — and ADX contributes a maximum-strength directional vote (weight 1.0 × confidence 1.0) on essentially every tick, skewing every VotingEngine consensus. The tooltip (`indicator_panel.py:528-541`) tells the operator the value is "0-100" and "ADX <20: ranging."

**Fix:** add a dedicated averaging smoother for the DX series so ADX returns to 0-100 — **then `ADXTrendSuppressionGate`'s default MUST be reset from 500.0 to ~30** (`gate_chain.py:551`), and the tooltip becomes correct. This is a live gate threshold change: gate it.

---

### P1-9. `src/trading/scrumming_bot.py:8456` — DIST balance clamp compares a float to a `Balance` object
`class=silent-failure` · **confirmed** · severity downgraded high→medium by verifier

```python
dist_asset = min(dist_asset, bal)
```
`bal` is `exchange.base.Balance` (`@dataclass`, no `order=True`, 116-131), so `min(float, Balance)` raises `TypeError` — caught by the bare `except Exception: pass` on the next line (8457-8458, annotated "R28-OK"). Reproduced: `min(5.0, Balance(...))` → `TypeError: '<' not supported`. Every other read in the file does `float(getattr(_bal, 'free', 0) or 0)`.

**Correction to the original narrative:** this is defense-in-depth that never fires. The MEM-235 BONK `INSUFFICIENT_FUND` incident documented at 8232-8265 was root-caused and fixed at the accumulator formula itself (551× reduction), **not** at this clamp.

**Fix:** `_bal_free = float(getattr(bal, 'free', 0) or 0); dist_asset = min(dist_asset, _bal_free)`. Narrow the except to `(TypeError, ValueError, AttributeError)` and log at WARNING with the exception type.

---

### P1-10. `src/trading/scrumming_bot.py:2131` — `update_phantom_config` carries a stale hardcoded timeframe blocklist
`class=duplication` · **confirmed, reproduced exactly**

```python
"coinbase": {"4h", "2h", "30m", "1m"},
```
`__init__` (361-370) reads from `exchange/timeframes.py::available_timeframes`, whose Coinbase entry is `frozenset({'1m','5m','15m','30m','1h','2h','6h','1d'})` (line 39). The `__init__` comment at 358-359 says so explicitly. This forked dict declares three **supported** TFs unsupported, and the comment at 2129 falsely claims it is "consistent with `__init__`". Live caller: `bot_live_settings.py:534-536`.

**Operator sees:** applying any phantom-timeframe change on a Coinbase bot silently drops the 30m phantom (the tactical-timing screen added deliberately in v3.19.23) with the caveat "Dropped unsupported TFs for coinbase: [30m]" — factually wrong. It returns only on a full bot restart.

**Fix:** delete `_EXCHANGE_UNSUPPORTED_TFS`; extract the `__init__` filter into `_filter_phantom_timeframes()` and call it from both sites.

---

### P1-11. `src/exchange/ccxt_connector.py:681` — N bots spawn N threads that swap the shared `_scan_symbols` set
`class=threading` · `[UNVERIFIED PROOF]`

```python
if symbol:
    orig = self._scan_symbols.copy()
    self._scan_symbols = {symbol}
    self._scan_trade_history()
    self._scan_symbols = orig
```
`add_scan_symbol` (645-666) spawns a daemon thread running `refresh_history(symbol=…)` when already connected, and `BotContainer.set_connector` calls it inside a `for bot in self._bots.values()` loop (`bot_container.py:1755-1757`). Non-atomic read-swap-restore, no lock. Two-bot interleave: thread-A captures `{A,B}` and sets `{A}`; thread-B captures the truncated `{A}` and sets `{B}`; B restores `{A}` — B is permanently gone from the registry. Worse, `_scan_trade_history` reads `list(self._scan_symbols)` at 604 after another thread replaced it, so a thread can scan someone else's symbol and never its own.

**Operator sees:** with >1 bot, History shows trade history for a random subset and **stays that way** — the manual Refresh (`bot_container.py:2146`) and the next reconnect both iterate the truncated set. Recurrence of the MEM-248 symptom the `add_scan_symbol` docstring (635-643) claims to have fixed.

**Fix:** stop mutating shared state to pass an argument. Give `_scan_trade_history` a `symbols: list[str] | None = None` parameter; guard `_scan_symbols` with a `threading.Lock` and read through a snapshot copy. Consider serialising late-registration scans onto one worker.

---

### P1-12. `src/exchange/api_load_monitor.py:90` — API-load gauge is structurally capped at 500 CPM by a 500-entry ring
`class=correctness` · `[UNVERIFIED PROOF]`

```python
all_entries = self._api_log().get_for_exchange(exchange, count=10_000)
```
`APIInteractionLog.__init__(max_entries=500)` (`api_logger.py:34`) truncates to 500 entries **total across all exchanges** (93-94), and `get_api_log()` (176) is the only construction site and passes no argument. So `cpm = n * 60.0 / 60` can never exceed 500.0 against `DEFAULT_CEILING_CPM = 600.0`; `load_score` saturates at 0.83 and can never reach 1.0. The `count=10_000` argument is the author's own evidence a larger window was intended. Corroborating: `data_pool.py:157` records *"the biggest contributor to the operator-observed 500/600 CPM saturation"* — 500/600 is exactly this arithmetic ceiling, not a measurement.

**Operator sees:** the status-bar pill (`main_window.py:4386-4389`) pins at ~500/600 CPM (83 %), turns red and stops moving no matter how much worse real load gets — no signal about whether a fix helped. Separately `should_allow_new_phantom_set` compares an under-measured CPM against the 450 CPM threshold and will approve phantom sets that push real load past the ceiling.

**Fix:** evict by **age** (drop entries older than ~120 s) rather than by count, so the CPM math is window-bounded; or at minimum `APIInteractionLog(max_entries=10_000)`. Regression test asserting `sample()` reports >600 CPM when 700 entries land in the 60 s window.

---

### P1-13. `src/exchange/circuit_breaker.py:313` — `call_with_breaker` has zero callers; every exchange READ path is unprotected
`class=dead-feature` · `[UNVERIFIED PROOF]`

The breaker is wired at exactly **one** site: the hand-rolled inline block in `CCXTConnector.place_order` (`ccxt_connector.py:976-983`, `1063-1066`). `get_ticker`, `get_ohlcv`, `get_balances`, `get_balance`, `get_orderbook`, `get_open_orders`, `get_order`, `cancel_order`, `get_my_trades`, `get_all_tickers` have **no breaker** — and all are decorated with `@_with_retry()` (181-207), which retries 3× with 1 s + 2 s backoff. During an outage each read amplifies 3× with nothing to short-circuit it. The module docstring (32-37) states the whole purpose is *"prevents retry storms from depleting the operator's API rate-limit quota"* and cites *"8 bots … 240 wasted calls per outage, plus IP-ban risk."*

**Fix:** route reads through `call_with_breaker(f"{exchange_id}:{symbol}", …)`, or factor `place_order`'s inline block into a `_with_breaker` decorator. **Order matters:** the breaker check must be *outside* `_with_retry`, else the retry loop still fires 3× before the breaker sees anything.

---

### P1-14. `src/exchange/ccxt_connector.py:193` — `_with_retry` treats `ccxt.BadRequest` as retryable
`class=correctness` · `[UNVERIFIED PROOF]`

```python
retryable = any(kw in exc_name.lower()
                for kw in ("ratelimit", "timeout", "network", "request"))
```
`"request"` is a substring test with no word boundary, so it matches `BadRequest` → `"badrequest"`. `BadRequest` is a permanent 4xx (bad granularity, unsupported param) — retrying cannot succeed. `"timeout"` already covers `RequestTimeout`, so `"request"` is redundant for its stated purpose. The sibling classifier in `circuit_breaker.py:62-74` uses exact patterns and does **not** include a bare `"request"` — the two have drifted.

**Operator sees:** a misconfigured request takes 3+ seconds and 3 wasted API calls to report, inflating the CPM the operator is trying to keep under 600.

**Fix:** drop `"request"` from the tuple; better, `from .circuit_breaker import _is_transient_error` so retry and breaker classifiers cannot drift again.

---

### P1-15. `src/trading/bot_container.py:927` — one transient `get_markets()` failure permanently disables the pre-flight guard
`class=silent-failure` · `[UNVERIFIED PROOF]`

```python
fallback = (0.0, 0.0, 8)
self._market_limits_cache[symbol] = fallback
```
The comment says "negative-cache the failure **briefly**", but there is **no TTL and no invalidation method** anywhere on the class (`grep` finds declaration 880, read 914, three writes 927/936/940 — no `.pop`, `.clear`, `del`). Once `(0.0, 0.0, 8)` is stored, the guards at 1002 (`if _min_amount > 0`) and 1009 (`if _min_cost > 0`) are short-circuited **for the lifetime of the bot object**. The `__init__` comment at 873-879 compounds it: *"refreshed only when explicitly invalidated"* — nothing ever invalidates. Logged at DEBUG only.

**Operator sees:** if `get_markets()` fails once during a 35-bot staggered start (the documented rate-limit pattern — see `start_all`'s v3.23.86 note), that bot spends the rest of the session re-sending under-minimum orders and getting them rejected server-side. That is exactly the API spam the v3.15.78 guard exists to stop, and the operator sees generic 'SELL FAILED' with no `PRE-FLIGHT REJECTED` prefix.

**Fix:** store `(limits, timestamp)`; expire **negative** entries after 30-60 s while keeping positive entries long-lived. Raise the failure log to WARNING. Add `invalidate_market_limits(symbol=None)` so the comment becomes true.

---

### P1-16. `src/trading/bot_container.py:2802` — `restore_bots_from_state` ignores `register()`'s refusal tuple
`class=error-handling` · `[UNVERIFIED PROOF]`

```python
self.register(bot)
restored.append(bid)
logger.info("Restored bot %s (%s on %s) in IDLE state%s", ...)
```
`register()` returns `(granted, reason)` and on a CapitalRegistry over-allocation refusal does **not** add the bot to `self._bots` — it emits `bot.register_refused` and `return False, reason` at 2001-2007, before the insert at 2017. This call site discards the return and unconditionally appends + logs success. Every other production caller checks it (`main_window.py:6824-6837`, `stock_main_window.py:585`).

**Operator sees:** `main.py:669-673` logs "Restored 12 bot(s) from previous session" while only 9 exist. The missing bots never appear in the table and never trade; the only clue is an uncorrelated WARNING-level `bot.register_refused`.

**Fix:** `granted, reason = self.register(bot)`; on `not granted`, log ERROR with `bid`/`symbol`/`reason` and `continue` without appending. Optionally return a refusals list so `main.py` can surface "N bot(s) refused."

---

### P1-17. `src/trading/smart_orders.py:85` — the promised execution-level capital backstop does not exist
`class=dead-feature` · **confirmed**

`capital_reservation.py:29-35` declares *"Two enforcement layers (defense in depth): … 2. **Execution-level**: order placement (smart_orders.py) pre-flights against the registry."* `scrumming_bot.py` repeats it three times (9875, 9888, 9926) — including at the point where it matters: `# R28-OK: registry call defensive — smart_orders backstop still in effect`.

`SmartOrderEngine` has **zero constructions** anywhere in `src/`, `tools/`, `main.py` or the live `tests/` tree. Live orders go `ScrummingBot → BotContainer.guarded_place_order → exchange.place_order` (read 940-1045: VolumeGuard or `place_order`, nothing else).

**Operator sees:** when the decision-level registry pre-check at 9900 raises, the `except` at 9926 logs at DEBUG and **falls through to place the sell with zero reservation enforcement**. A Scrumming bot can sell base currency an Extractor has reserved — the exact predation the 2026-05-23 directive exists to prevent.

**Fix:** either re-wire the pre-flight from `smart_orders.execute` into `BotContainer.guarded_place_order` so the backstop exists, **or** delete `smart_orders.py` and correct all three comments plus the `capital_reservation.py` docstring. Do **not** leave the comments — they are what make the fall-through at 9926 look safe.

---

### P1-18. `src/trading/capital_registry.py:471` — drift metric recomputes free capital
`class=correctness` · **PARTIAL — math bug real, claimed effect refuted**

```python
drift_usd = wallet_usd - sum(
    r.reserved_usd for r in self._reservations.values()
    if r.exchange_id == exchange_id and r.base_currency == base)
```
Character-for-character the same generator already assigned to `reserved_usd` at 465-467. So `drift_usd == free_usd` identically and `drift_pct` is just "percent of wallet not reserved."

**Effect refuted:** there is **no reconcile cycle**. `reconcile_capital_registry` appears only at its def (`bot_container.py:1795`), in its own log string (1860), and one internal call from `reconcile_all_capital` (1882) — which itself has zero external callers. Its docstring at 1870-1872 says *"The 5-min cadence callers (Phase D background task / GUI manual-refresh) invoke this"* — those callers were never built. So the operator gets **no** drift alerts, ever.

**Fix:** define drift against a second source (exchange-reported balance vs the registry's last-known snapshot), or remove `drift_usd`/`drift_pct` from the returned dict and delete the threshold branch. Decide separately whether the 5-min reconcile cadence should be built.

---

### P1-19. `src/trading/volume_guard.py:228` — MEM-259 disable is enforced at one call site only
`class=correctness` · **confirmed**

The force-disable is a property override always returning `False` (182-190), with a setter that writes `self.config.enabled` and notes it "does not affect the disabled property" (192-196). But `execute()` at 228 reads `self.config.enabled`, which `main.py:638-640` leaves at the dataclass default `True` (line 62). The disable holds **only** because `BotContainer.guarded_place_order` happens to test the property (`bot_container.py:1027`). `get_status()` (674) reports `"enabled": self.config.enabled` → `True` for a force-disabled guard.

**Operator sees:** the "Disable the fucking thing" directive is one bypass away from being undone — a new call site reaching `guard.execute()` directly re-enables iceberg chunking with no code change and no warning.

**Fix:** make it structural — `enabled: bool = False` on `VolumeGuardConfig`, `execute()` short-circuits on the **property**, `get_status()` reports the property. Delete `get_volume_guard` (737), `get_status`, `get_market_profile`, `get_execution_history` — all zero-caller.

---

### P1-20. `src/trading/risk_manager.py:436` — no rule action is ever executed
`class=dead-feature` · **confirmed**

```python
if rule.action == RiskAction.PAUSE_BOT and bot_id:
    self._paused_by_risk.add(bot_id)
elif rule.action == RiskAction.PAUSE_ALL:
    pass  # Caller should handle this
```
The module header (5-6) says it *"Can auto-pause bots that breach thresholds"*; the class docstring lists *"Emergency stop all bots."* `DEFAULT_RULES` ship `PAUSE_ALL` on `critical_drawdown` (133) and `rapid_loss` (163) and `PAUSE_BOT` on `per_bot_loss` (139). But `_paused_by_risk` is read **only** to suppress re-alerting (274), `PAUSE_ALL` is a literal `pass` deferring to a caller that does not exist, and the sole `evaluate()` caller (`main_window.py:5017`) only forwards `severity == "critical"` to the notification manager. `AlertEvent.BOT_PAUSED_BY_RISK` (`notifications.py:39`) is never emitted.

**Operator sees:** at 25 % portfolio drawdown or a 5 %-in-5-minutes flash crash, a notification popup appears and every bot keeps trading. The Risk tab shows `action='pause_all'`, which reads as armed automatic protection.

**Fix:** wire the actions (return alerts to a handler calling `bot_manager.pause_bot` / `pause_all`, emit `BOT_PAUSED_BY_RISK`) **or** downgrade every `DEFAULT_RULES` action to `RiskAction.WARN` and rewrite the header + class docstring to promise alerting only.

---

### P1-21. `src/trading/scrumming_bot.py:6705` — 27 `tick()` early returns skip the gate-fixture write
`class=data-integrity` · **confirmed**, severity downgraded high→medium (forensics only, no trading-behaviour impact)

`_last_gate_state` is written only in the SCRUM block (6694-6750) and FOLD block (7414-7455). `tick()` has 27 returns before 6705, five of which are taken **after a trade fires**: WIRE_STACK (5006), CARTRIDGE (5278), AUTO_DETONATION (5292), ENTRY (5652), Manual Fire (4942). `__init__` seeds only five keys (332-336) with no fixture keys.

**Verifier corrections:** the docstring at 4361-4365 already disclaims the `_execute_manual_rebalance` / `_execute_detonation` paths — so CARTRIDGE, WIRE_STACK and AUTO_DETONATION are covered. **ENTRY (5652) is the one genuinely undisclaimed fire path.** And "at-target bot never refreshes" is true only for a bot inside the MEM-258 dust band (4901) continuously since restart; otherwise the state goes stale rather than staying literal `['pre-tick']`.

**Operator sees:** `gate.log` rows for ENTRY (and stale rows elsewhere) carry `scrum_fixture=null`, `fold_fixture=null`, `scrum_blockers=['pre-tick']` — the fire cannot be reconstructed. The dashboard fire button (`bot_container.py:1337` → `main_window.py:1117`) can show 'pre-tick' blockers indefinitely for a dust-band bot.

**Fix:** hoist a minimal fixture write to a point every path passes — after `current_value` is computed (4849), seed `{'ticker_last':…, 'delta':…, 'stage':'pre-gate'}` and let 6705 overwrite it. Add a `'stage'` key so consumers can distinguish "gates never evaluated" from "gates evaluated and passed." Add ENTRY to the `_emit_gate_decision_at_fire` docstring's out-of-band list.

---

## P2 — DEAD WEIGHT

Cheap to delete; deleting stops future confusion. None of these change live behaviour. Grouped by cluster; `SWL` = lives under `src/trading/` or `src/exchange/`.

### P2-A. Whole subsystems with zero reachable entry point

| # | Anchor | What is dead | Evidence | Disposition |
|---|---|---|---|---|
| 1 | `src/stocks/alpaca_connector.py:48` | **Entire `src/stocks` package — 1,872 lines / 7 modules.** `AlpacaConnector` is the only concrete `BrokerBase` and is never instantiated. It hangs off `LauncherWindow` (`launcher.py:98`) and `StockMainWindow` (`stock_main_window.py:110`) — **neither class is ever constructed**; `main.py:627` says "Direct launch to Crypto MainWindow (no launcher)". Nothing connects `stocks_selected`. | confirmed | Move to `_archive/` and drop `src.stocks` from the `test_subpackage_imports` parametrize, **or** put an UNREACHABLE banner in the currently-0-byte `src/stocks/__init__.py`. Do not leave it ambiguous. |
| 2 | `src/core/mini_display.py:843` | 848-line hardware display subsystem. `init_displays`, `get_manager`, `MiniDisplayManager`, `DisplayType`, `MessageType` and all five adapters: zero importers repo-wide. Header says "initialised lazily by AcervatorOS" — nothing initialises it. **Ships in every build** (`Acervator_win.spec:47`, `:75`; 4 hits in `Analysis-00.toc`) and appears in the product manual. | confirmed | Delete, or call `init_displays()` from `main.py` and route off `trade.filled` / `bot.state` / `bot.error`. If revived, note `notify_price` (747) emits a literal `%%` — `f"…{x:+.2f}%%"` is not an escape inside an f-string. |
| 3 | `src/core/system_load_oscillator.py:55` | 260-line Nuclear Mode dual-oscillator. Zero references to `SystemLoadOscillator`, `current_multiplier`, `tick_workload`, `effective_tick_interval`. The v3.13.7 operator directive quoted at lines 4-7 is unimplemented at the call site. | confirmed | Wire into `nuclear_controller.py`'s tick loop or delete with the directive record. |
| 4 | `src/gui/screen_recorder.py:535` | 685 lines, four capture backends. `RecorderToolbarWidget` (the only entry point) is never instantiated; nothing imports the module. Two latent bugs if revived: `_open_folder` (669) resolves `Path("")` → CWD, not the recorder's own `logs/simulator/recordings`; `_write_cv2` (511-512) reshapes without `bytesPerLine()`, so any width not a multiple of 4 raises into a `log.debug` swallow (the GIF path at 478 gets this right). | confirmed | Delete, or wire + fix both bugs first. |
| 5 | `src/exchange/api_docs.py:5` | 195 lines. Zero importers; `get_api_docs`/`list_all_docs`/`get_docs_summary` never called. The advertised "download to `docs/api/`" feature was never written (no HTTP, no writer; `docs/api/` does not exist) — `from pathlib import Path` (13) exists solely for it. | confirmed | Wire `get_docs_summary()` into the Exchange tab as a links panel, or delete. Either way drop the unused import and the download sentence. |
| 6 | `src/gui/usb_auth_widget.py:111` + `src/core/usb_auth.py:468` | `USBStatusIndicator.paintEvent` uses `QPainter`/`QPen`/`QBrush` that are never imported (line 19 imports only `QColor, QFont`). Moot: **`USBAuthWidget` has zero importers** — no Settings > Hardware Key panel exists. Correspondingly `import_credentials_from_usb` / `find_auth_volume` have zero callers, and nothing reads `hardware_mode`/`hw_volume_serial` back (`main_window.py:5787-5802` goes straight to the local vault). | confirmed (PARTIAL: original framed it as a false security assurance — impossible, there is no reachable UI) | ~500 orphaned lines. Delete, or wire it and add the missing `QtGui` imports. |
| 7 | `src/trading/triangular_swarm.py:325` | 1,090 lines, zero importers. Also carries a real bug: `score_triad`'s insufficient-data early return (203) omits `"arm_scores"` which `rank_triads` dereferences unconditionally → reproduced `KeyError: 'arm_scores'` for any triad whose shortest series is <20 points. The synthetic-cross fallback at 310 is inverted (tests arm lengths, not the cross pair the comment at 311 describes). | confirmed, reproduced | Delete all 1,090 lines. If kept, give the early return the same key set and fix the inverted guard. |
| 8 | `src/competition/*` | Whole PoA subsystem unreachable: `main_window.py:3804` `self._competition_tab = None`, `:3810` `self._testnet_tab = None`. Carries four latent defects — `local_testnet.py:486` `merkle_root.lstrip("0x")` corrupts ~6.25 % of roots (char-set strip, not prefix strip, then `ljust` pads right); `token_ledger.py:204` `load()` appends without clearing, so a double load doubles every ACRV balance and the next `award()` persists it (same shape at `merkle_log.py:239-243`); `competition_engine.py:110` writes results to the process CWD (`Path("competition_results")`) — `run_demo_competition` redirects identities and ledger to a tempdir but forgets this one; `bot_identity.py:263` `_fallback_verify` returns `len(sig_bytes) == 32` with no crypto, silently, when `cryptography` fails to import. | confirmed | Shelve explicitly with a header banner listing these four, or fix them before any un-shelving. Do not un-shelve as-is. |

### P2-B. Wired-into-the-GUI but non-functional

| # | Anchor | Defect | Verified | Fix |
|---|---|---|---|---|
| 9 | `main_window.py:665` | `CapitalRegistryPanel` — 9-column reservation table + `update_from_registry()`, **never instantiated**. Its docstring claims "The MainWindow wires a QTimer at 300000ms" — no such timer exists anywhere in `src/`. Backend is live (`BotManager.capital_registry`, `bot_container.py:1791`). | `[UNVERIFIED]` | Wire it (instantiate in `_setup_ui`, add `QTimer(self)` at 300000 ms) or delete the class **and** the docstring's timer claim. |
| 10 | `main_window.py:3816` + `:3821` | `self._simulator.set_bot_viz(self._bot_viz)` — `set_bot_viz` **exists nowhere**; the only two occurrences in the repo are these two call sites. `AttributeError` on every boot, swallowed by `except Exception: pass`. `SimulatorTab` defines no `__getattr__`. The twin at 3821 targets `_paper_trader`, which is hard-`None` at 3779 and whose only reassignment (`6393`/`6411`) is gated on `_paper_trader_stack`, hard-`None` at 3780 and never reassigned. | `[UNVERIFIED]` / 3821 branch **confirmed** | Delete both blocks. If kept, guard `hasattr(self._simulator, 'set_bot_viz')` like the v3.23.80 hooks at 3767/3774 already do, and log instead of `pass`. |
| 11 | `bot_visualizer.py:1609` | Simulator Swarm + Paper Swarm "+ Add" rows are inert. `_toggle_run` / `_toggle` (1734) flip a dict flag, swap stylesheets, set "RUNNING" — no engine, no coroutine, no bus emit. `asset_combo`/`preset_combo`/`pair_edit`/`src_combo` are stored and never read; `pnl_lbl`/`price_lbl` (1571, 1686, 1692) are never `setText` anywhere; `bot_data["paper_exch"]` is `None` at 1727 and never assigned. `_run_all_sims`/`_start_all_paper` just fan the no-op out via `btn.click()`. | `[UNVERIFIED]` | Delete the "+ Add" / Run All / Stop All controls and both row builders; leave the tabs as read-only mirrors fed by the working `register_sim_run`/`register_paper_run` API. |
| 12 | `bot_visualizer.py:2185` | `_paper_swarm_pnl` → literal `"Net PnL: —"` and `_sim_swarm_trades` → `"Aggregate trades: —"`, forever. Each has exactly one `setText`, both string literals. The data exists: `update_paper_run` (2059-2073) stashes `h["_pnl"]` on every tick and calls `_update_paper_summary` at the end; the sim side already sums `_pnl` for its own row (2172-2177). | `[UNVERIFIED]` | Sum `_live_paper_rows` `_pnl`; stash `h["_trades"] = trades` in `update_sim_run` and sum it. |
| 13 | `journal_tab.py:142` | `_btn_recon` ("Run Reconciliation") and `_btn_snapshot` ("Save Snapshot") constructed, styled, `addWidget`'d — **never `.clicked.connect`'d**, no `setObjectName` so no auto-connect. Moot: `JournalTab` is never instantiated (`main_window.py:3840` `self._journal_tab = None`, "REMOVED per P1.7 / MEM-178"). | confirmed (PARTIAL: unreachable) | Delete with the tab. |
| 14 | `reconciliation.py:260` `SWL` | `ReconciliationEngine.reconcile()` has **zero callers** (constructed at `main_window.py:3154`, handed to Journal at 5054, never awaited), so `get_latest_result()` is permanently `None`. And `local_order_ids: set = set()` is unconditional, so the `if oid in local_order_ids` test at 271 can never be true and **every** open exchange order would be classified `OrphanedOrder` with a `cancel` recommendation. `cancel_orphaned` (300) having zero callers is the only thing preventing that from cancelling real bot orders. | confirmed | Delete `ReconciliationEngine` + `OrphanedOrder` + the construction at 3154, **or** populate `local_order_ids` from `_main_lots`/`_stack_tranches`/`_positions`, wire the button, and gate `cancel_orphaned` behind operator confirmation. |
| 15 | `analytics_engine.py:88` `SWL` | `record_trade` / `record_trade_from_dict` have **zero external callers** — `self._trades` is empty for the life of the process. `get_portfolio_summary()` returns all-zeros, `get_bot_performance()` → `[]`, `get_timeframe_comparison()` → `{}`. Only `snapshot_equity()` is driven (`main_window.py:5028/5031`). `main.py:649`'s `shared_analytics` has zero further references — that instance is dead too. | confirmed | Emit a `TradeRecord` from the fill path on a completed scrum→fold round trip and pass `shared_analytics` to `BotManager` the way `set_volume_guard`/`set_state_manager` do — **or** delete `AnalyticsEngine` and `analytics_tab` together. Do not ship a permanently-zero panel. |
| 16 | `bot_wizard.py:1834` | `ProfitFoldingPage` is unreachable: `ModeSelectionPage.is_grid()` is hard-coded `return False  # Grid Bot deprecated` (295), and `PAGE_FOLDING` is the target of that one dead branch. Worse, `get_bot_config()` (1842-1868) **never calls** `self._folding_page.get_config()`, so its six keys would be discarded anyway. `TradingParamsPage.get_config()`'s docstring (1446-1448) asserts the opposite. | `[UNVERIFIED]` | Delete the page + `PAGE_FOLDING` + lines 1772/1778/1833-1834/1836 and correct the docstring; **or** add a `profit_folding_active` checkbox to `TradingParamsPage` §2 (mirroring `bot_live_settings.py:2329-2342`). Today every wizard-created bot silently gets `profit_folding_active=True` (`bot_container.py:98`) with no operator control. |
| 17 | `main_window.py:4421` | `pulse_targets` still animates `self._stat_pnl`, a parentless orphan: constructed 3268, `setVisible(False)` 3269, deliberately excluded from the header layout loop 3306-3308. Meanwhile `_stat_scrummed` / `_stat_folded` — the cards v3.15.50 shipped to replace it — get no effect. `refresh_all_privacy_widgets` (4501) *was* updated to the new set; `_setup_pulse` was not. | `[UNVERIFIED]` | Replace `_stat_pnl` with `_stat_scrummed, _stat_folded`. A hidden widget is currently repainted 12.5×/s for the whole session. |
| 18 | `main_window.py:134` | `PulseManager`, `PULSE_CSS`, `NotificationSpool` — definitions only, no live references. `PULSE_CSS` is a keyframes stylesheet the adjacent comment declares unusable in PySide6. `PulseManager.__init__` unconditionally starts a 50 ms QTimer, so it is booby-trapped for anyone who constructs it (it would fight `_pulse_tick`). `NotificationSpool` was superseded by the inline `_NotifyStub` at 3473. | `[UNVERIFIED]` | Delete all three (~80 lines). |
| 19 | `main_window.py:4608` | Four abbreviation-tooltip entries (`'Realised'`, `'Locked'`, `'Mature'`, `'Exch'`, lines 4556-4558/4591) can never match — v3.19.29 made the labels all-caps (`QLabel('REALISED')` etc., line 849) and `abbrev in text` is case-sensitive. Manually enumerated: no key matches any of the four. | `[UNVERIFIED]` | Lowercase both sides (`abbrev.lower() in text.lower()`) **and** sort keys longest-first so `StochRSI` beats `RSI`; or set the four tooltips directly in `SpendableProfitsWidget.__init__` next to the SPENDABLE one at 820. |
| 20 | `bot_visualizer.py:2119` | `register_live_run` dereferences `self._live_rows_layout` / `_live_rows_empty`, which are **assigned nowhere** — the Session-26 refactor kept only `_live_bot_rows` (1201). The comment at 1198-1201 promises all four legacy methods "remain safe no-ops"; the other three are, this one raises `AttributeError`. Zero callers today. | `[UNVERIFIED]` | Do the Session-27 cleanup the comment schedules: delete 2098-2164 and the shim at 1201, plus the now-false comment. |

### P2-C. Fields, params and helpers that are never fed or never read

| # | Anchor | Defect | Verified |
|---|---|---|---|
| 21 | `bot_container.py:762` `SWL` | `BotStats.accumulated_fold` / `accumulated_distribute` — **zero assignments repo-wide**. `accumulated_fold` has a live consumer: `fleet_replay_panel.py:1016` sums it for the operator-facing **"Mature"** cell, which therefore always reads 0.00. Same class as the v3.24.8/9 dash-strip defect the panel's own docstring (981-985) describes fixing. | `[UNVERIFIED]` |
| 22 | `bot_container.py:764` `SWL` | `BotStats.extended_positions_created` — declared, exposed as `get_status()['stats']['extended_positions']` (1316), never incremented. Grid-era leftover. Trap: the next surface adding an "Extended positions" column gets a permanent zero with no test signal. | `[UNVERIFIED]` |
| 23 | `bot_container.py:3006` `SWL` | `BotState.ERROR` is **never assigned anywhere** — `_run_with_guard` sets `BotState.COOLDOWN` (1207) instead. So `get_aggregate_stats()['errored']` is permanently 0, consumed live at `main_window.py:4746`, `:5434`, `analytics_engine.py:126`. | `[UNVERIFIED]` |
| 24 | `bot_container.py:1724` `SWL` | `check_live_monitor` sums `s.get("portfolio_value", 0)` + `s.get("passive_value", 0)` — **neither key is emitted by any `get_status()`** (`BotContainer` 1242-1343, `ExtractorBot` 1573-1594 are the only two). Every AI Monitor check bills an LLM call whose prompt reads `"Portfolio: $0.00 | Passive: $0.00 | Adv: $+0.00"` (`live_monitor.py:218`) and the result is shown to the operator as a real performance assessment. | `[UNVERIFIED]` |
| 25 | `extractor_bot.py:1548` `SWL` | `positions_for_gui` sets `current_price = p.avg_buy_price_base_per_alt`, so "Current (USD)" ≡ "Entry (USD)" and "Δ% (USD)" ≡ +0.00 % structurally. The docstring's "the detail dialog can refresh … asynchronously" was never built — `bot_live_settings.py:902-903` formats the values straight into cells with no timer and no re-population path. Operator sees a red DRAWDOWN state cell next to +0.00 % P/L. | `[UNVERIFIED]` |
| 26 | `extractor_bot.py:1258` `SWL` | Compounding-tier ROLL branch is byte-identical to LOCK (`self._chunk_free_base += base_received` in both); only the `log_kind` string differs. `extractor_max_compounding_tier` is operator-settable at `bot_live_settings.py:2988/2998` and `bot_wizard.py:1469`. Setting it to 5 vs 1 produces identical trading behaviour and identical capital flows. | `[UNVERIFIED]` |
| 27 | `scrumming_bot.py:3581` `SWL` | `import_scrumming_state`'s drift check is **structurally unreachable**: MEM-254 removed `current_holdings` from persistence (3253-3254) and the import explicitly does not restore it (3418-3424), so `self._current_holdings` is always exactly `0.0` at line 3581 and `> 0` is always False. The docstring (3335-3338) still advertises the warning; the trailing comment at 3603 still says "Saved `_current_holdings` becomes our starting assumption." | confirmed |
| 28 | `scrumming_bot.py:3779` `SWL` | `YTD_TRADE_MAX_PAGES = 40  # 20k-trade ceiling, safety cap` — never read. The v3.23.58 rewrite hardcoded the bound at line 3820 (`_windows < 12`). Sibling constants `YTD_TRADE_PAGE_LIMIT` (3826) and `YTD_TRADE_ANCHOR_UTC` (3811) *are* read. Tuning it has zero effect. | confirmed |
| 29 | `scrumming_bot.py:6798` + `:7578` `SWL` | `GateContext.delta_pct=abs(float(delta))` — a raw USD magnitude in a field `gate_chain.py:78` documents as `|delta| / target_balance × 100`. The correct local `delta_pct` already exists at 5661 and is used everywhere else (5754, 6174, 6296, 6377). Latent: no gate reads `ctx.delta_pct` today. Live trap: the obvious next gate comparing it against `ctx.scrumming_interval_pct` would compare dollars to percent. | confirmed |
| 30 | `gate_coverage.py:298` `SWL` | `elif _in_log_gap(...)` and `else:` assign the **identical** `GateStatus.LOG_GAP`, so the call is a pure no-op and `LOG_GAP_THRESHOLD_S = 1800.0` influences no classification. `_in_log_gap` (220) is called nowhere else. Given the known 2026-06-11 writer stall, this is exactly the count used to size the stall — inflated by every near-miss tolerance failure. | confirmed |
| 31 | `capital_arbiter_bridge.py:156` `SWL` | `pool_capacity_fraction = free_usd` — an absolute USD figure passed where `select_top_n_within_pool` documents a `[0,1]` fraction (`opportunity_arbiter.py:275-277`) and subtracts `pool_share_needed` (documented as a fraction at 90-92) from it. With a $200 pool and candidates at 0.1, ~2,000 candidates fit. Zero production callers (the abandoned 30-line reasoning block at 124-148 shows the decision was never made). | confirmed |
| 32 | `fleet_replay_controller.py:190` | `_window_since_ms` / `_window_until_ms` stored and **never read anywhere in the tree**. The docstring (182-189) quotes the 2026-08-02 operator directive as satisfied, and `_build_sim`'s comment (300-307) says "The YTD window is applied at master-clock iteration time (see the run loop)" — `_run()` (410-531) contains no window check. No caller passes them either (`fleet_replay_panel.py:831-840` omits both). Real narrowing happens panel-side at 700-720. | `[UNVERIFIED]` |
| 33 | `fleet_replay_controller.py:56` | `ReplayProgress.anchored` written at three panel sites, read nowhere; `candles_skipped` incremented at 451, read only by tests. Neither appears in `_refresh_progress`'s status line nor in the `finish_run(summary=…)` payload (558-575). Also `candles_played` (458) counts skipped candles, so `trades_per_1k_candles` and `candles_per_s` are diluted. Default mode is anchored (checkbox unchecked, 245), so most persisted runs are screening passes indistinguishable from authoritative parity runs. | `[UNVERIFIED]` |
| 34 | `sim_exchange.py:169` | `step_symbol` — zero callers, and the class docstring (70-71) **recommends** it (`# or per-symbol: ex.step_symbol("BTC/USD")`). It calls `CandleSeries.step()` without touching `self._master_clock`, permanently desyncing that symbol — exactly the index-based stepping v3.24.3 removed for producing "desynchronized playback" (`master_clock.py:5-13`). | `[UNVERIFIED]` |
| 35 | `fleet_replay_panel.py:171` | `self._real_candles` initialised and never touched again (only a past-tense comment at 655). **`src/core/feature_telemetry.py:26` lists it by name as a canonical scaffolding exemplar** — "referenced, never populated" — and it is still here, with a 7-line comment justifying it. | `[UNVERIFIED]` |
| 36 | `registry.py:241` (stone_tablets) | `missing_ranges` and `has_coverage` both take a `timeframe` parameter their bodies never reference (they use `NATIVE_TIMEFRAME` internally). Neither validates it, unlike `get_candles` (292-295) which raises on an unsupported timeframe — so `missing_ranges(asset, a, b, "7m")` is accepted silently. | `[UNVERIFIED]` |
| 37 | `storage.py:118` (stone_tablets) | `Tablet.listed_at_ms` returns `first_ts_ms` unconditionally, `entry_from_tablet` copies it, and `read_manifest` falls back to `first_ts_ms` when absent — the two values can never differ. It is also per-**year**, so a multi-year asset's 2026 tablet reports 2026-01-01 regardless of listing date. `Tablet.listed_at_iso` (126) and `TabletEntry.listed_at_iso` (82) have zero callers. Confirmed absent from the operator's real MANIFEST (all 406 rows take the fallback). | `[UNVERIFIED]` |
| 38 | `fetcher.py:656` + `:187` (stone_tablets) | `main()` reads only `args.cmd`; `--since-ms` (declared 3×), `--exchange`, `--quote-filter` and `--asset` (declared `required=True`!) are all discarded. Separately `CoinGeckoAdapter.fetch_chunk` (187) returns a hardcoded error with no I/O, yet `_build_adapter` (573-574) still hands it out — so callers get a FillReport of chunk errors indistinguishable from a network outage. Its `chunk_limit`/`chunk_sleep_s`/`retry_*` (175-178) configure a fetch that never happens. | `[UNVERIFIED]` |

### P2-D. Dev tooling that cannot run

| # | Anchor | Defect | Verified |
|---|---|---|---|
| 39 | `tools/orphan_widget_scan.py:10` | `import sadp._tools.orphan_widget_scan` — **no `sadp/` directory exists**. `python tools/orphan_widget_scan.py` → `ModuleNotFoundError`. The invocation is allowlisted in `.claude/settings.local.json:3100`, so the operator is expected to run it. This is the tool built to find the exact defect class in this report. | confirmed |
| 40 | `tools/build_agents_md.py:18` | Identical failure. `AGENTS.md` — the generated AI-developer onboarding file — can no longer be regenerated. | confirmed |
| 41 | `src/core/rule_registry.py:58` | `REGISTRY_PATH = ROOT / "sadp" / "RULE_REGISTRY.json"`. `_load` tolerates the miss; `_save` (181-187) is a bare `write_text` with no `mkdir(parents=True)`. Reproduced: `RuleRegistry()._save()` → `FileNotFoundError`. Every mutating RULE command and `python src/core/rule_registry.py` (591) crashes — while `version_sweep.py:594-597` prints that exact command as the remedy. | confirmed, reproduced |
| 42 | `src/core/version_sweep.py:732` | R25 gate can never pass: `MANDATORY` requires `simulator.py:_sim_scrumming_tick`, and `simulator.py` no longer exists → one permanent `Severity.HIGH`, and `SweepResult.passed` (74) requires zero HIGHs → `sys.exit(1)` always. Compounded by `registry_path` (723) resolving to the nonexistent `sadp/RULE_REGISTRY.json` → `registry = {}` → every annotation flagged "unknown rule". **Ran it: 217 findings = 215 MEDIUM + 1 HIGH + 1 INFO, `passed=False`.** | confirmed, reproduced |
| 43 | `src/core/version_sweep.py:419` + `:518` | `check_r6_two_paths` (CHECK 7) and `check_snapshot_consistency` (CHECK 11) both `return` early on missing `src/gui/simulator.py` / `sadp/RAIntSimBat/RAIntSimBat.py`. The `run()` loop (697-712) prints `✓` when the finding delta is zero, so **a check that did nothing is indistinguishable from a pass**. Ran both: 0 findings each. CHECK 11's own docstring says it guards a bug class "invisible at runtime and undetectable by syntax checking." | confirmed, reproduced |
| 44 | `src/core/version_sweep.py:452` + `:955` | `check_requirements` reads `requirements.txt` / `requirements-optional.txt`, **neither of which exists** (deps moved to `pyproject.toml`), producing 4 permanent false MEDIUMs pointing at a nonexistent file (ran it: PySide6, ccxt, reportlab, cryptography). And `save_json_report` does `mkdir(parents=True)` on `ROOT/"sadp"/"RAIntSimBat"/"reports"` — **re-creating the deprecated tree on every run** — unconditionally (1138), while the `--json` flag (1128-1130) is declared and never read. | confirmed, reproduced |
| 45 | `tools/build_release_zip.py:321` | `read_session_number` reads `sadp/EPISODIC_MEMORY.json`; the `FileNotFoundError` is caught at 327 and returns the hardcoded `27` with **no log line**. Live call returns `27` while the repo dir is `acervator_session25_*` and MEMORY records Session 79. Every zip is named `acervator_session27_CLOSE_hop5_v3_24_19.zip`; successive releases collide. Also dead: `_RAINTSIMBAT_REPORTS_REL` (223) and the empty `ADDITIONAL_REGEXES` (150). | confirmed |
| 46 | `main.py:648` | `shared_risk = RiskManager(bot_manager)` and `shared_analytics = AnalyticsEngine()` assigned under `# Shared subsystems`, never read; `MainWindow` (653) takes only `bot_manager=` and `settings_manager=`. `RiskManager.__init__` (168-187) performs no registration. Same shape at `main.py:511` `keyring = KeyringManager()`. **Correction:** `shared_notif = get_notification_manager()` (650) *is* a lazy singleton getter (`notifications.py:353-357`) — only the local name is unused. Contrast the neighbouring lines that do wire (`set_volume_guard` 640, `set_data_pool` 645). | confirmed |
| 47 | `native_chart.py:118` | `CandlestickChart.TIMEFRAMES` is a dead duplicate of `ChartPanel.TIMEFRAMES` (1875); only the ChartPanel copy is read (1888). Both lists are wrong (see P3-15). Fixing one leaves the other stale. | confirmed |
| 48 | `sim_visuals.py:287` | `GateLightsCell.clear_gates` omits `_ls_scrum` / `_fold_ls`, and `_draw_bank` tests the LS override **before** the `_evaluated` check (331-335) — so the cyan LS light would survive a clear. **Zero callers repo-wide**, so it is latent: reclassify as scaffolding (a public reset method nothing calls) with the LS omission to fix if ever wired. | confirmed (PARTIAL: effect unreachable) |
| 49 | `stock_accumulation_bot.py:188` | `_record_day_trade` has **zero callers**, so `_day_trades` is always empty, `_check_pdt` (176-182) always returns True, and the PDT gate at 271/289/310 is open unconditionally. Three config knobs (71-73) and a `day_trades_5d` status field (399) hang off it. Unreachable package (P2-A-1). | confirmed |
| 50 | `season_schedule.py:52` | `RarityTier.qualifies()` — zero callers. The live path `classify_tier` (115) hardcodes every threshold (0.001@122, 0.01@124, 0.25@126, 0.10@128, 0.50@130) duplicating the `rank_pct_max` fields at 69/78/87/96/105, and the two have **already diverged** (branch ordering for Bear Slayer). Editing `RARITY_TIERS` — the obvious, self-describing place — changes nothing. Same duplication for `max_ever` (21/1000) re-hardcoded at `local_testnet.py:387/391/539/540`. Also `competition_engine.py:278` passes `consecutive_top1 = 0  # TODO` so the Grand Accumulator tier is permanently unreachable despite a working Elo tracker feeding a value nothing reads (`challenge_protocol.py:64/84/121/122`). | confirmed |

---

## P3 — MISLEADING

Comments and docstrings that contradict the code. Zero runtime impact, real debugging cost.

| # | File:line | Says | Actually | Verified |
|---:|---|---|---|---|
| 1 | `gate_chain.py:30` `SWL` | *"Until then, this module is **dead code** — present but unused by production tick()."* (CURRENT STATUS v3.18.11 block, 20-31) | The cutover happened. `scrumming_bot.py:346` constructs `build_scrumming_scrum_chain()`; `:6871` evaluates it; `:6877` `if _scrum_chain_result.should_fire:` opens the fire block. **The chain IS the live SCRUM trigger.** Editing any `Gate` subclass here changes live fire decisions immediately. Cited line 30 is the single most-wrong line. | confirmed |
| 2 | `scrumming_bot.py:8-11` `SWL` | AI DEVELOPER NOTE: mirror every change into `src/gui/simulator.py::_sim_scrumming_tick`; "See ARCHITECTURE.md for full invariants list" (25) | `src/gui/simulator.py` does not exist (`execution_discipline.py:9` records it deleted); no `ARCHITECTURE.md` outside `_archive`. The instruction is now actively harmful — it invites recreating the retired dual implementation the no-bridges rule forbids. First thing anyone reads when opening a 10,824-line live engine. | confirmed |
| 3 | `mr_inspector.py:16` `SWL` | Gate 1 "30-candle SMA"; Gate 2 "BB position > 0.85"; "all 3 gates pass → Boost Sell (sell **2.5 %**)"; architecture block (28) "z-score > 2σ" | 20-candle SMA (132-135); `bb_pos > 0.80` (156); **the sizing rule is inverted** — 2.5 % is the *unconfirmed* branch (188-189), confirmed spans **5 %–20 %** (182-184 with defaults at 101-102); z threshold is 1.8 at line 12 and in the constructor. Live consumer: `stock_accumulation_bot.py:135`. An 8× sizing surprise for anyone tuning from the header. | confirmed |
| 4 | `bot_live_settings.py:2018` + `bot_wizard.py:615-620` `SWL` | Checkbox "Aggressive Trading (force IOC-limit takers)" + tooltip "every engine-initiated buy/sell executes as an Immediate-Or-Cancel limit order priced through the spread"; comment says enforcement "lands in Sub-phase 2D" | Sub-phase 2D never landed. `_aggressive` is read at exactly one execution site — Stack-tranche placement (`scrumming_bot.py:9592`). `_execute_sell`'s order-type block (9995-10001) and `_execute_buy`'s (10599-10605) never reference it. Every ordinary SCRUM and FOLD ignores the flag. | `[UNVERIFIED]` |
| 5 | `live_log_reader.py:1`/`:6` `SWL` | Self-declares path `sadp/_tools/live_log_reader.py`; *"caught by the static check `tools/check_sim_live_boundary.py`"* | File is at `src/trading/`; **no `sadp/` tree**; **the named tool does not exist** — so the sim/live boundary the 2026-06-09 directive asked for has zero automated enforcement. Same wrong-path header verbatim on `trade_grader.py:2` and `opportunity_arbiter.py:2`. | confirmed |
| 6 | `state_manager.py:74-75` `SWL` | *"When None, the current file's existing wires field (if any) is preserved."* | `save_state` builds `state = {...}` from scratch (86-96) and never reads the file to merge; `list(None or [])` is `[]`. Compounded: `bot_container.py:2335-2336` initialise `wires = []` / `ledgers = []` and both `except` branches only `logger.warning`, so **one transient export failure erases the persisted Smart Wire topology and lifetime `wired_in`/`wired_out` ledgers** — the exact operator-reported v3.16.57 bug. *(Cite `:93`, not `:92`.)* | confirmed |
| 7 | `privacy_mask_registry.py:135-137` `SWL` | *"`set_masked` records the value even for unknown ids so a wired-up call site that uses a new id starts working without a separate registration step."* | `mask_or` (290-293) short-circuits on any id not in `ALL_FIELD_IDS` and returns the value **unmasked**. `mask_or`'s own docstring (286-288) documents that as the deliberate TA-leak-guard — so the class docstring is the wrong one. A privacy control that fails **open**. (Direct `reg.is_masked(...)` sites — `bot_visualizer.py:2235/2263`, `indicator_panel.py:754`, `main_window.py:638/1431/2528` — would honour a new id; only the 14 `mask_or` sites would not.) Also the "18 canonical ids" comments at 52/137/169 vs `assert len(ALL_FIELD_IDS) == 19` at 101. | confirmed |
| 8 | `rule_registry.py:196` | `"Unknown rule: {rule!r}. Valid rules: R1–R27."` | `VALID_RULES` derives from `RULE_META`, whose last key is **R35** (103) — so the message is wrong even about its own ceiling. The tree annotates itself with R44/R55/R57 (`execution_discipline.py:20-22`), R71/R76 (`safe_url.py:26`), R68 (`rule_registry.py:492`'s own docstring). Reproduced: `_validate_rule('R55')` raises. The operator cannot administer any rule above R35 — most of the active set. | confirmed, reproduced |
| 9 | `circuit_breaker.py:39-43` `SWL` | CONFIG defaults: `failure_threshold=5`, `cooldown_seconds=30.0`, `success_threshold=2`, `rolling_window=60.0` | Actual signature defaults (132-135): **20 / 5.0 / 1 / 30.0**. The same docstring 20 lines earlier already announces the change (17-18) — the v3.16.6 edit updated the changelog paragraph and left the reference block. Also bullet 5's "force-close-all on registry init" is not implemented: `get_breaker_registry` (292-304) never calls `reset_all()`. | `[UNVERIFIED]` |
| 10 | `main.py:540` + `:555` | `log_manager.info("Acervator v3.1.26 starting")` / `app.setApplicationVersion("3.1.26")` | 23 lines later `current_version = "3.24.19"` (612), matching `src/__init__.py:15`. **The first line of every session's log says v3.1.26** — the exact failure mode that cost three sessions in the v3.15.97 stale-binary incident. `check_release_readiness._read_version` (53-59) reads only `src/__init__.py` and never compares against `main.py`, despite `main.py:10-11` declaring the invariant. (Qt's `applicationVersion` has zero readers — that half is inert.) | confirmed |
| 11 | `main_window.py:6893` | Help → About: `"Acervator v1.7"`, "Grid Mode - Speculative Scrumming", "TradingView Charts" | Version is 3.24.19 (the same class renders it correctly in the title bar at 3120). `BotMode.GRID` removed v3.20.4, `grid_bot.py` deleted v3.16.0; `TradingViewChart` is imported only by `stock_main_window.py:243`, and the trading tab has no chart (`main_window.py:3452`). Module docstring line 3 carries the same stale v1.7. Any support conversation anchored on this dialog starts from a false version. | `[UNVERIFIED]` |
| 12 | `main_window.py:3752` | *"Basic Modes panel launches RAIntSimBat batteries via subprocess; Nuclear Mode is placeholder until Phase B lands NuclearSimExchange"* | `nuclear_sim_exchange.py` exists and is 356 lines; the simulator_tab tree is a built-out subsystem. And RAIntSimBat is the deprecated tree. Someone diagnosing an inert Nuclear Mode reads this, concludes it was never implemented, and stops — instead of finding the dead cache path in `nuclear_candle_source.py:62`. | `[UNVERIFIED]` |
| 13 | `main_window.py:1338`, `:1380`, `:1405`, `:1654`, `:1888` | Comments place Fire at column 6/7 and Detail at column 7 | v3.23.49 inserted Target BTC / Target ETH: Fire is column **8** (`setCellWidget(row, 8, …)`, 1886), Detail column **9** (1897), and `PRIVACY_FIELD_BY_COL` maps 6 → `bot_table.target`. **Live consequence:** `_refresh_header_dots` (1417) rebuilds every header item and re-attaches tooltips only for maskable columns, so `COLUMN_TOOLTIPS[9]` set at 1392 is discarded at 1428 — the Detail header has no tooltip. | `[UNVERIFIED]` |
| 14 | `native_chart.py:1912-1914` + `:1956-1963` | *"Slingshot and BB-Bullseye remain disabled until R46 MLHCI"*; Sling tooltip "placeholder paint at HA color flips"; BBull tooltip "shaded band at **BB middle**" | Both are created with `enabled=True` (default at 1916). BB-Bullseye is implemented at 1124-1179 and its own comment says *"the 'bullseye' is the SNIPE ZONE at each BB **band edge**, not the middle"* — four polygons at ±0.5 % / ±0.2 % around both bands. Slingshot is the real CM implementation at 1181-1290 (BB(20,2), squeeze_lookback 30, threshold 0.6). A reader trusting the BBull tooltip misreads the snipe zones by the full band width. | `[UNVERIFIED]` |
| 15 | `native_chart.py:1875` | `TIMEFRAMES = ["1m","5m","15m","1h","4h","1d","1w"]` — a seventh hardcoded TF list | `exchange/timeframes.py` was built in v3.15.61 under an explicit directive ("4h should be disabled for Coinbase") and Coinbase's set is `{1m,5m,15m,30m,1h,2h,6h,1d}`. Three other selectors call `available_timeframes()` (`bot_live_settings.py:2169`, `bot_wizard.py:1389`, `:1689`); ChartPanel does not, and `ChartPanel(symbol)` (`main_window.py:1013`, `1238`) carries no exchange context. Error runs both ways: 4h/1w offered but unavailable, 30m/2h/6h available but unreachable. `chart_data.py:90-93` passes them straight through. | `[UNVERIFIED]` |
| 16 | `bot_wizard.py:265` | Accumulation Trading description advertises "MR Inspector Boosted Fold" | v3.23.37 retired it on the crypto path — `scrumming_bot.py:646-650`: *"the crypto path never invoked the setter, so the attribute was a phantom."* `MRInspector` survives only in `stock_accumulation_bot.py`. (The "12-indicator TA voting" half is accurate — `ta_engine.py:2342-2373` returns exactly 12.) The identical claim at `stock_main_window.py:568` is legitimate; leave that one. | `[UNVERIFIED]` |
| 17 | `fleet_replay_panel.py:193` + `:296-298` | Visible header label + Start Replay tooltip: *"Start Replay currently plays **synthetic candles**… real YTD candle feed lands v3.23.79-B"* | Since v3.24.1 `_on_start_clicked` reads exclusively from the Stone Tablets registry (661-720) and line 727 states *"No tablet → skip. NO synthetic fallback."* `_synthesize_candles_for_symbol` (67) has zero production callers. The operator reads on screen that Fleet Replay is a synthetic toy four minor versions after it stopped being one. | `[UNVERIFIED]` |
| 18 | `fleet_replay_panel.py:217` | Fetch YTD tooltip: "Pull real 1d OHLCV (limit=200 candles) … Coalesced through MarketDataPool. After this completes, Start Replay uses real market data instead of synthetic sine waves." | Every clause false since v3.23.84. The handler (470) calls `fetch_all_history_chunked` — **trades**, not OHLCV; no MarketDataPool import exists in the file; Start Replay reads Stone Tablets, never `_ytd_trades`. The button's own docstring (471-479) correctly describes the trade fetch, contradicting its tooltip. Points the operator away from the real fix. | confirmed |
| 19 | `sim_visuals.py:180` | *"a single row of **10** LEDs — the 5 scrum gates then the 5 fold gates — each with its label printed **beneath**"* | v3.24.18 made the banks asymmetric (its own comment at 47-60 says the 5-gate symmetric model "was wrong three ways"): `_GATE_ORDER_SCRUM` has **10**, `_GATE_ORDER_FOLD` has **9** — 19 LEDs. `_draw_bank` (322-347) draws labels **above** per operator directive. The widget's own tooltip (229-261) says 10+9, disagreeing with the docstring. Also line 213 cites a gate `"TRNCH"` that does not exist (fold-side is `TRNQ`). | `[UNVERIFIED]` |
| 20 | `storage.py:11` + `fetcher.py:25` (stone_tablets) | Layout block shows `BTC_5m_2026.json` and a `_scratch/` "pre-verified fetches" staging dir; CLI block documents a `fill` subcommand | Real filenames carry the v3.23.98 exchange suffix (`tablet_filename`, 157-163) — the operator's 408 files are all `BTC_5m_2026_coinbase.json`. `_scratch/` is created (183) and never written; `SCRATCH_DIR` and `MANIFEST_PATH` are exported and unused (`read_manifest`/`write_manifest` recompute the literal inline at 255/300). There is **no `fill` subparser** — `main()` registers status/discover/build-ytd/universe/ensure, so `fill` → argparse `SystemExit(2)`; meanwhile `discover` and `universe`, which do work, are undocumented. | `[UNVERIFIED]` |

**Also:** `data_pool.py:8-19` still teaches the dead push architecture (`await pool.refresh_all(connectors)  # 2 API calls, not 3`) after the v3.23.74/76 rewrite to passive `get_or_fetch_*` coalescing — `refresh_all` (664), `get_candles` (211), `is_fresh` (226), `get_status` (730) all have zero callers. Anyone reviving `refresh_all` also inherits a latent bug: it copies `last/bid/ask/volume_24h/fetch_time` at 690-694 but never `ticker.timestamp`. `[UNVERIFIED]` · `SWL` · **also P2**.

**Also:** `token_ledger.py:67` docstring advertises `remaining_supply()`; the method is `remaining_ever()` (157) with different semantics — and `LocalACRV.remaining_supply()` *does* exist at `local_testnet.py:243` on a different class with different units, so a reader lands on the wrong object. The error message at 103 surfaces the correct name, contradicting the docstring one screen above. **confirmed**

**Also:** `src/gui/design_system.py:216`/`:59`/`:19` and `theme_engine.py:19` instruct maintainers to run `tools/gui_lint.py` and `tools/wcag_audit.py` — **neither exists**, so the R65/R54 hex-literal ban presented as machine-enforced is unenforced. Proof of drift: `design_system.py:92` reads `DANGER = "#ff5577"  # adjusted from #ff3366 to clear WCAG AA`, while the rejected `#ff3366` is still hardcoded in **16 files** under `src/gui/` (main_window ×21, bot_live_settings ×17, risk_tab ×6, journal_tab ×4, alerts_tab ×3, …). **confirmed**

---

## P4 — HARDENING

Silent failures and missing guards on paths where the failure matters.

| # | File:line | Defect | Fix | Verified |
|---:|---|---|---|---|
| 1 | `logging_engine.py:557` `SWL` | `attach_to_bus` calls `bus.unsubscribe(...)` ×4 (557/561/565/571) — **`EventBus` has no `unsubscribe` method**; `subscribe()` returns a closure (120). `AttributeError` swallowed by `except Exception: pass`, then execution falls through and **subscribes all four handlers a second time**. The docstring (552-553) claims *"Idempotent: calling twice replaces the prior subscription rather than double-writing each trade."* | Store the closures returned by `bus.subscribe` in `self._bus_unsubs` and call them, or add a real `unsubscribe(topic, callback)`. Stop swallowing `AttributeError` — a missing bus API is a wiring bug. Today only `main.py:520` calls it, so nothing doubles **yet**; any reconnect/settings-reload/second-LogManager path silently doubles every trade in `trade.log`, every gate decision in `gate.log`, and every `pnl.event` — the logs the sim parity tool treats as ground truth. | confirmed, reproduced |
| 2 | `main.py:124` | `_check_stale_dist_binary`'s three `except` handlers (89/121/124) all call `logger.debug(...)`, but module-level `logger` is not bound until **line 225** while the function is invoked at module scope on **line 130**. Any exception inside the try raises `NameError` **from inside the "guard must NEVER raise" handler**, killing the import. Reproduced with `sys.stderr = None` (pythonw / `--windowed`). **Currently latent** — the guard returns at 78-79 unless `dist/Acervator/_internal/src/__init__.py` exists, and it does not in this tree. Live scenario: a dev tree that *has* a stale `dist/` build (build_windows.ps1 produces these) launched under pythonw. | Replace the three `logger.debug` calls with `pass` or stderr-guarded prints; guard line 111's `sys.stderr.write` with `if sys.stderr is not None:`. Or move the `logger =` assignment above line 130. | confirmed, reproduced |
| 3 | `live_monitor.py:61` `SWL` | `TradeJournal.verify()` **never verifies the hash chain** — it counts lines and returns hardcoded `True`. `record()` (46) does compute `chain_hash = sha256(prev + record_hash)`; `verify()` never reads it. A journal with edited/deleted/reordered rows verifies clean. Also `_resume()` (37-43) restores only `_s["trades"]` — volume, harvests, folds, boost_*, wires, wins, peak, max_dd all reset to 0 and are then published in the report's `activity` block (104-105) and `portfolio.max_dd` (103). **Two proof corrections:** `main_window.py:3153`'s `TradeJournal` is a *different* class from `reconciliation.py:81` with no chain at all; and `grep '\.verify()'` returns **zero** matches — nothing calls it. The only live-monitor `TradeJournal` construction is `bot_container.py:1700`, reached only when live-monitor settings carry both `enabled` and `api_key`. | Implement `verify()`: walk the file recomputing the chain, return `(False, first_bad_seq)` on mismatch, and have callers surface it. Extend `_resume()` to replay every counter. Until then, do not present `integrity.journal_hash` as a verified quantity. | confirmed (PARTIAL) |
| 4 | `bot_container.py:1755` / `extractor_bot.py:1165` `SWL` | `manual_fire_position` mutates the **shared** `self.config.extractor_exit_pct = 100.0` across an `await self._execute_bullish_exit(...)` — a network round trip — on the same event loop the bot ticks on (dispatched via `run_coroutine_threadsafe` onto `BotManager._async_loop`, `bot_live_settings.py:962-974`). `tick()` (1438-1523) can resume mid-window and process a *different* open position, closing it at 100 % instead of the configured `extractor_exit_pct`, logged as a normal EXTRACTOR EXIT. A shutdown inside the window persists `extractor_exit_pct=100.0` to `bot_state.json`. | Do not mutate shared config. Give `_execute_bullish_exit` an `exit_pct: Optional[float] = None` defaulting to `self.config.extractor_exit_pct`, and pass `exit_pct=100.0`. That removes the window **and** the try/finally restore dance at 1163-1180. *(Confidence: suspected — the interleave is reasoned from the code, not observed.)* | `[UNVERIFIED]` |
| 5 | `idempotency.py:29-30` `SWL` | The module docstring promises *"On confirmed failure (4xx other than 409), marks for deletion so a future legitimate retry generates a new coid"* — **that behaviour does not exist**, and `invalidate()` (135) and `is_known()` (143) written to provide it are dead (`bot_container.py` calls only `derive_coid` 1076 and `mark_fulfilled` 1083, the latter only on success; the `except` at 1085-1091 deliberately re-raises without invalidating). *(The related "fingerprint collision" claim is **not** a defect — `TradeIntent`'s docstring at 60-62 says identical intents collide deliberately. No runtime evidence it has ever fired.)* | Implement the documented invalidation for non-409 rejections in `guarded_place_order`'s except branch, or delete `invalidate`/`is_known` and correct the docstring. | confirmed (PARTIAL) |
| 6 | `notifications.py:288` `SWL` | `_send_in_app` computes `level` on all three branches and then emits a hardcoded `logger.info(...)` at 293 — `level` is never read. Every in-app notification lands at INFO in `console/system.log` (propagates via `acervator.notifications` → the `acervator` FileHandler, `logging_engine.py:313-326`). *(Correction: only `DRAWDOWN_CRITICAL` and `PNL_MILESTONE` are ever emitted anywhere — `BOT_PAUSED_BY_RISK`, `BOT_ERROR`, `CONNECTION_LOST` have no emit site. And the priority IS greppable in the message text; it is the levelname that is wrong.)* | `getattr(logger, level)("NOTIFICATION [%s]: %s — %s", …)`. | confirmed |
| 7 | `notifications.py:330` `SWL` | `_send_sms` calls `engine.send(phone, f"{title}: {message}")` against `SMSEngine.send(message, event_type="info")` — arg order swapped, so `type_checks.get(event_type)` (`sms_engine.py:85`) always misses. Moot anyway: `update_config` has **zero callers** so the singleton stays `SMSConfig(enabled=False)`, and `_send_sms` returns at 324-326 because `_sms_config` is `{}` — its only populator `configure_sms` (187) is called only from `AlertsTab._save_config` (`alerts_tab.py:206`), and `AlertsTab` is never instantiated (`main_window.py:3842-3844`, "REMOVED per P1.7 / MEM-178"). Residual real defect: the early `return` raises nothing, so `channels_sent.append("SMS")` (234) records a delivery that did not occur. | Decide SMS's fate. If kept: build an `SMSConfig` from `_sms_config`, `engine.update_config(cfg)`, `engine.send(f"{title}: {message}", event_type="error")`, and make a `False` return skip the `channels_sent` append. If not: delete `_send_sms` and the SMS channel from `DEFAULT_RULES`. | confirmed (PARTIAL) |
| 8 | `sound_engine.py:421` `SWL` | Playback is gated on `if sys.platform == "win32":` with **no `else`** — no darwin, no linux, no fallback. `_ensure_sounds` (39-60) is *not* platform-gated, so on macOS the full synth pipeline (sniper, coins-in-bucket, water drip) runs, writes WAVs to a tempdir, sets `_available = True`, and `play()` falls through to nothing. `Acervator_mac.spec` and `build_mac.sh` both exist; the operator maintains a Mac Mini install. | Add `subprocess.Popen(["afplay", path])` on darwin and `["aplay","-q",path]` on linux, falling back to `QSoundEffect`. Short-circuit `_ensure_sounds` when no backend exists so the synth loops stop burning CPU. | confirmed |
| 9 | `registry.py:192` (stone_tablets) | `_persist_manifest` rebuilds the MANIFEST **from `self._tablets` only**. `_load_from_manifest` drops any entry whose file is unreadable (174-179, `logger.warning` + `continue`) — a transient OneDrive/AV lock or a JSON parse error is enough (`read_tablet` returns `None` on both, `storage.py:210-213`). The next `ingest_candles` calls `_persist_manifest` (373) and writes a MANIFEST without that row. Since the MANIFEST is the **sole enumerator** (no directory glob exists anywhere in the module), the tablet becomes permanently invisible even after it becomes readable. | Merge instead of replace: read the existing MANIFEST first and carry forward any row whose file still exists on disk; or track skipped entries in `self._unloadable` and re-emit them verbatim. Promote the skip to an operator-visible notice. | `[UNVERIFIED]` |
| 10 | `registry.py:167` (stone_tablets) | `TabletEntry.checksum_sha256` is written on every persist (`storage.py:320`) and round-tripped (282) but **never read** — `_load_from_manifest` uses only asset/timeframe/year/exchange. The only checksum comparison (`storage.py:226-232`) is against the checksum stored *inside the same file*, self-consistent by construction for any wholesale rewrite — and even when it trips it is a `logger.warning` that **returns the tablet anyway** (233). The MANIFEST checksum is the only out-of-band witness and nothing looks at it. In a subsystem the operator's directive declares immutable. | After `read_tablet` succeeds, compare `tab.compute_checksum()` against `e.checksum_sha256`; on mismatch refuse to load, record it, and surface it (boot log + Simulator activity log). Make the intra-file drift branch return `None` rather than handing back suspect data. | `[UNVERIFIED]` |
| 11 | `registry.py:241` (stone_tablets) | `missing_ranges` assumes every 5-minute slot in `[since_ms, until_ms]` must contain a candle. It never consults `listed_at_ms` / `AvailabilityInfo` (which the same class exposes at 405) and keeps no record of slots the exchange has already confirmed empty. Two permanently unfillable classes: pre-listing slots and no-trade windows. Measured against the operator's real archive: **25 of 406 tablets** start >24 h after `YTD_START_MS` (CAP 2026-06-26 → ~24,768 unfillable slots); `BTC_5m_2026` holds 61,200 candles across a 61,279-slot span (79 slots the exchange never had). | Clamp the walk to `max(since_ms, availability.listed_at_ms)` and persist a `filled_through_ms` watermark (or `confirmed_empty_slots`) so answered slots are not re-requested. Emit `AvailabilityInfo.listing_notice` instead of a gap for the pre-listing span. **Do this before fixing P0-11**, or a universe build re-requests hours of impossible windows every run. | `[UNVERIFIED]` |
| 12 | `fetcher.py:489` (stone_tablets) | `build_universe` iterates `(base, quote)` pairs with `quote_filter=("USD","USDC")` but calls `fill_asset(base, …)` with the same base for both. The tablet key carries no quote (`registry.py:351`) and neither does the filename (`storage.py:163`); `ingest_candles` dedupes on **timestamp only** (358-360). `sorted()` puts USD first, so USD wins every contested slot and USDC silently backfills the holes — **one tablet blended from two order books**, with a `source` string recording neither. Confirmed the archive schema physically cannot distinguish them (408 files, no quote in any name). *Whether the existing 406 tablets are already blended is unverified.* | Add `quote` to the key + filename + `Tablet`/`TabletEntry`, with a manifest migration. One-line stopgap: set `quote_filter` default to `("USD",)` at 463 and skip a base already filled under a different quote. | `[UNVERIFIED]` |
| 13 | `registry.py:131` (stone_tablets) | `AvailabilityInfo.listing_notice(exchange_display="Coinbase")` hardcodes the default while the instance already carries the correct `exchange_id` (112), and the sole caller (`fleet_replay_panel.py:799`) passes nothing — after the panel went to real trouble to route `_eid` (788) into the two registry calls. This is the exact failure the adjacent v3.24.3 comment (678-682) calls *"a silent hallucination-vector the moment multi-exchange lands."* | `def listing_notice(self, exchange_display: str = "") -> str:` then `name = exchange_display or self.exchange_id.title()`. Leave the caller alone. | `[UNVERIFIED]` |
| 14 | `live_bot_window.py:288` | `_on_start` optimistically disables START / enables STOP / sets "running" (270-272) **before** the worker connects. On `CONNECT FAILED` (288-289) `_main` returns without ever assigning `self._bot`, so `_on_stop`'s first guard (`if self._bot is None: return`, 328-329) skips the unsubscribe loop (342-345), the button re-enable (349-350) and the status reset (351). The four bus subscriptions (250-255) leak and keep pumping. Only recovery is killing the process. **Reachability: `LiteLiveBotWindow` is only constructed by this module's own `if __name__ == "__main__"` entry point (361-370)** — the shipping app never opens it. | Add a `_sig_failed` Signal marshalling a UI reset to the GUI thread, and make `_on_stop` reset buttons + unsubscribe even when `self._bot is None`. Or delete the standalone window. | confirmed (PARTIAL) |

### P4-bis — Harness rule defects (these make the reviewer under-report)

| # | File:line | Defect | Fix | Verified |
|---:|---|---|---|---|
| 15 | `tools/harness/rules/scaffolding.py:409` | S003 filters on `ast.FunctionDef` only — **`ast.AsyncFunctionDef` is not a subclass**, so every `async def` is skipped. The same module handles both correctly at 337, 348-349 and 124. No async exclusion is declared in the spec (32-37) or FALSIFICATION list (46-56). Probe: identical sync/async methods → one finding, async twin silent. Acervator's hottest paths (bot ticks, exchange coroutines, chart fetches) are async, so the v3.23.87 defect class this rule exists to catch is invisible exactly where it matters. | `isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))`. | confirmed, reproduced |
| 16 | `tools/harness/rules/hallucination.py:165` + `:125` | `_LOCAL_IMPORT_PREFIXES = ("src.", "tests.", "tools.")` — H003 never resolves `sadp._tools.*`. And `_RETIRED_NAMES` lists `"sadp/"` / `"sadp\\"` **with path separators**, so H002 misses the dotted form. Ran `hallucination.scan(Path('tools/orphan_widget_scan.py'))` — the file whose only two statements raise `ModuleNotFoundError` — and got **zero findings**. The operator's own hallucination detector certifies two entirely dead files as sound. | Add `"sadp."` to `_LOCAL_IMPORT_PREFIXES`, and the bare dotted forms `"sadp."`, `"RAIntSimBat."` to `_RETIRED_NAMES`. | confirmed, reproduced |
| 17 | `tools/harness/gui_archetype.py:215` + `:332` | (a) `is_interactive_widget = any(b in _INTERACTIVE_QT_WIDGETS or b in _QT_WIDGET_BASES …)` — `_INTERACTIVE_QT_WIDGETS ⊆ _QT_WIDGET_BASES` and the line is only reached after `_is_qt_widget_class` already proved membership, so it is unconditionally True and **GUI001 fires HIGH on decorative QLabel/QFrame subclasses** (reproduced on a read-only `StatusBadge`), driving `passed=False`. (b) GUI004's `has_parent = bool(node.args)` counts *any* positional — but Qt's idiom is `QPushButton("Click me")` where the parent is the **second** positional. Reproduced: a parentless `QPushButton("Click me")` produced no GUI004. The rule is effectively inert across Acervator's GUI tree. | (a) `any(b in _INTERACTIVE_QT_WIDGETS for b in base_list)`, or key off the already-collected `self._interactive_instances` (178). (b) `has_parent = any(kw.arg == "parent" …) or any(not (isinstance(a, ast.Constant) and isinstance(a.value, str)) for a in node.args)`. | confirmed, reproduced |
| 18 | `tools/harness/gui_archetype.py:539` | `_BANDIT_SEVERITY_OVERRIDES` and `_run_bandit` are forked into `coding_archetype.py` (115-128 / 420-431) and `gui_archetype.py` (380-384 / 526-551). v3.24.5 added the B101 test-file suppression (`if _is_test_file and rule_id == "B101": continue`) to the coding copy only. The two now give opposite verdicts on the same GUI test file. *(Correction: the dicts are semantically identical, not byte-identical.)* Low bite today — the release gate points GUIArchetype at one fixture (`check_release_readiness.py:95`), so this only hits an ad-hoc human review. | Extract `_BANDIT_SEVERITY_OVERRIDES` + `_run_bandit` into `tools/harness/rules/_bandit.py` and import from both. | confirmed |
| 19 | `tools/harness/claim_ledger.py:80` | `_load_all` skips unparseable lines with `continue` — no counter, no warning — so an `open` claim vanishes from `list_open()` and `check_no_open()` prints `[OK]`. `_write_all` (86-90) then opens with mode `"w"` and rewrites from the in-memory list, **permanently erasing** them. `Claim(**d)` (82) is unguarded, so an extra key raises `TypeError` that `check_release_readiness._run_claim_ledger_check` does not catch (it catches only `ImportError`, 123) — the whole gate dies with a raw traceback. **Currently unreachable: `docs/audits/CLAIMS.jsonl` does not exist**, so `_load_all` returns `[]` at 71-72 and step 3 passes vacuously for a different reason. | Count and report unparseable lines; preserve them verbatim in `_write_all`; wrap `Claim(**d)` in `try/except TypeError`; broaden line 123 to `except Exception`. | confirmed (PARTIAL) |
| 20 | `bot_identity.py:263` | `_fallback_verify` returns `len(sig_bytes) == 32` — no cryptography at all — and is the R28 integrity gate for the append-only trade log (`merkle_log.py:143-145`). The downgrade is **completely silent**: no warning at import (33-42), no field in `submission_summary()` or the on-chain payload recording that the log was built unsigned. The module header (19) claims *"R28: All cryptographic failures raise explicitly — no silent fallbacks."* Doubly latent: `cryptography` 50.0.0 is installed and is a hard `pyproject.toml` dependency, and the competition subsystem is unreachable. | Log a WARNING in the `ImportError` handler naming the consequence; add a `crypto_backend` field to `submission_summary()`; make `verify_trade` raise `RuntimeError` rather than return `True` for third-party records. Best: refuse to construct `BotIdentity` at all when `_CRYPTO_OK is False`. | `[UNVERIFIED]` |
| 21 | `crypto_assets.py:310` | The bulk `_register` loop hardcodes `logo_url=f".../coins/images/1/small/{cgid}.png"` — **image directory `1` is Bitcoin's** — for all 30 assets (MATIC, UNI, ATOM, SHIB, **BONK**, PEPE, …), while the individually registered coins each carry their correct numeric id (ETH `/279/` at 82, XRP `/44/` at 138, DOT `/12171/` at 211). Every such URL 404s. The `logo_fallback_url` on the next line **can never be tried**, because `get_logo_url` (379-384) is `asset.logo_url or asset.logo_fallback_url` and the primary is always truthy. `download_logo` swallows at `logger.debug` (376). *(Not HTTP-verified; conclusion rests on the URL scheme being per-coin, which the file's own correct entries demonstrate.)* | In the bulk loop set `logo_url=""` and keep only the fallback, **or** make `get_logo_url` probe the primary and fall through on failure. Raise line 376 to INFO. The operator's live BONK bot is in the affected set. | `[UNVERIFIED]` |

---

## Deliberately not listed

**Time-space complexity / performance.** A separate concurrent audit covers algorithmic complexity, hot-loop cost, allocation churn and I/O amplification. Nothing in this list is here because it is slow. Where a defect happens to have a performance side effect — the hidden `_stat_pnl` repainted 12.5×/s (P2-B-17), the mac sound synth generating WAVs nothing plays (P4-8), 30 s of dead backoff per Stone Tablets chunk (P0-11) — it is listed for its **correctness or dead-code** character, and the timing figure is context only. Do not treat overlap with the complexity audit as a duplicate finding; treat it as two audits independently reaching the same line.

**Also out of scope, deliberately:**

- **Style, naming, formatting, type-annotation coverage.** The operator asked for actionable defects, not preferences. No item here is "consider refactoring."
- **Broad `except Exception` that is genuinely best-effort.** Only handlers that *hide real breakage on a path that matters* are listed (P0-2, P0-3, P2-B-10, P4-1, P4-3). The many `# R28-OK` handlers around optional telemetry and cosmetic updates were read and left alone.
- **`_archive/`, `.session26_backups/`, `build/`, `dist/`.** Referenced only as evidence that a live symbol used to be tested (e.g. the archived `test_mem220_ccxt_serialization.py`, the archived `test_circuit_breaker.py`). No defects are reported *inside* those trees.
- **Stone Tablets file contents.** The 406 JSON tablets were parsed for metadata (MANIFEST fields, first/last timestamps, candle counts) as evidence for P4-11 and P4-12. Whether the existing archive already contains USD/USDC-blended rows is **unverified** — the `source` field records no quote, so it cannot be determined from the data on disk.
- **`~/.acervator/` mutations.** `bot_state.json`, `credentials`, `reservation_state.json` and `stone_tablets/` were read only. Every fix that touches them (P0-7, P0-13, P3-6) is proposed, never applied.
- **Stone Tablets immutability.** No fix proposes mutating an existing tablet. P4-9/10/12 propose changes to the *manifest write path*, the *load-time integrity check*, and the *key/filename schema going forward* — with a migration, not an in-place rewrite of tablet contents.
- **Live-account state.** No fix proposes cancelling, replacing or reconciling any resting exchange order. P2-B-14's `cancel_orphaned` is explicitly recommended to stay behind operator confirmation *or* be deleted.

### One structural note for the operator

Twelve separate findings across seven partitions trace to a single root: **the `sadp/` tree was deleted and its references were not.** `tools/orphan_widget_scan.py`, `tools/build_agents_md.py`, `src/core/rule_registry.py`, four checks in `src/core/version_sweep.py`, `tools/build_release_zip.py`, `populate_nuclear_cache.py`, the `live_log_reader.py` / `trade_grader.py` / `opportunity_arbiter.py` headers, and the Nuclear Mode empty-state message all point into it. Two of the tools that would have *caught* this (the orphan-widget scanner and the hallucination detector, P4-16) are themselves blinded by it. A single sweep — `grep -rn "sadp" --include=*.py src/ tools/ main.py` — closes most of P2-D and a third of P3 in one cascade, and should probably go first.

---

# Appendix — independent critic / coverage audit

# Coverage Audit — 12-Partition Scan

## 1. Ground truth

```
find src tools main.py -name "*.py" -not -path "*__pycache__*"
```

**174 files.** Matches the stated inventory (174 files / 96,425 lines) exactly.

Union of all `files_scanned` across the 12 partitions, deduplicated: **173 unique paths.**

Arithmetic cross-check (independent of the set diff):
- `wc -l` over the 173 reported paths = **95,862 lines**
- `wc -l` over all 174 real paths = **96,425 lines**
- Delta = **563 lines** = exactly `src/design_system.py`

Two independent methods agree. No phantom files were reported — every path in every `files_scanned` list resolves to a real file on disk (`comm -13` returned empty).

---

## 2. COVERAGE GAP — 1 file

### `src/design_system.py` (563 lines) — NEVER ASSIGNED, NEVER READ

Repo path: `src/design_system.py`

**Why it fell through:** classic partition-boundary orphan. It is the only non-`__init__` module sitting directly at `src/` top level. `periphery` swept `src/__init__.py`, `src/utils/`, `src/competition/`, `src/stocks/` — it took the top-level `__init__.py` but not its sibling. `gui-rest` scanned the *similarly named* `src/gui/design_system.py` (256 lines), which likely made the gap invisible to a name-based reconciliation.

**I opened it. Verdict: YES, worth a follow-up scan — it is a strong dead-feature candidate, and it contains at least one visible rendering defect.**

One-line assessment: **a 563-line matplotlib/PDF token + page-template library with zero importers anywhere in `src/`, `tools/`, or `main.py`, whose only historical consumers (`sadp/RAIntSimBat` and two coverage test files) have both been deleted from the tree.**

Evidence:

```
$ grep -rn "design_system" --include=*.py src tools main.py
src/design_system.py:2,7,11        (self-references in its own docstring)
src/gui/design_system.py:3,9,12,39 (docstring cross-reference only)
src/gui/theme_engine.py:20,22,27   (docstring cross-reference to src/gui/design_system.py, NOT this file)
```
Zero `import` / `from` statements target it. All live references are prose inside docstrings.

```
$ ls -d sadp/RAIntSimBat
ls: cannot access 'sadp/RAIntSimBat': No such file or directory

$ ls tests/*design_system*.py
ls: cannot access 'tests/*design_system*.py': No such file or directory
```
`tests/` contains 56 `.py` files; the only surviving trace of its coverage is stale bytecode — `tests/__pycache__/test_design_system_coverage.cpython-314-pytest-9.0.3.pyc` — with no `.py` source. The real tests are at `_archive/tests_pre_2026_07_25/test_design_system_coverage.py`.

Its own module header (lines 11-12) asserts a live relationship that no longer has a consumer:

> `` `src.gui.design_system`, not this module. TD-017 audit (2026-04-23) formalized this relationship — they look like duplicates but aren't.``

Additionally, a concrete rendering bug is visible at lines 499-508 in `callout_value()` — the same string is drawn twice at the identical transAxes coordinate `(0.5, 0.50)`, once via `_put(... level="h1" ...)` and again as a raw 54pt `ax.text`, producing overstruck glyphs:

```python
    _put(ax, 0.5, 0.50, value, level="h1",
         color=COLORS["accent"], align="center",
         weight_override="bold")
    # Larger than h1 — render at 54pt manually
    ax.text(0.5, 0.50, value,
            fontsize=54, fontweight="bold",
```

Also at line 471: `bar_h(..., value_at_bar_end=True)` — the parameter is accepted and never read anywhere in the function body (lines 470-490); the actual gate is `if direct_labels and label_fmt:`. Scaffolding parameter.

**Recommendation:** assign `src/design_system.py` a single-file follow-up scan. Do not fold it into an existing partition's report — it was never in anyone's scope, so no partition can claim it.

---

## 3. Files reported as SKIPPED — 1

| Partition | File | Reason given | Verified? |
|---|---|---|---|
| `periphery` | `src/competition/trophy_generator.py` | Partial read: 200 lines / 80,537 bytes; lines 19-174 are minified single-line SVG string literals up to 8 KB wide. Header (1-18), grep of dispatch structure, and tail (176-200) read verbatim. Bytes inside SVG literals not read. | **CONFIRMED.** `wc -l` = 200, `wc -c` = 80,537. Longest lines: L155 = 7,802 chars, L152 = 7,615, L30 = 6,905, L88 = 3,914, L61 = 3,726, L156 = 3,242, L126 = 2,697. Seven lines exceed 2,000 chars. The skip reason is accurate and the residual risk (a defect buried inside SVG markup) is correctly characterized as low-value. |

No other partition reported a skip.

---

## 4. Partition plausibility

Line volume actually covered per partition (primary assignment, not counting corroboration re-reads):

| Partition | Files | Lines | Plausible? |
|---|---|---|---|
| `scrumming-bot` | 1 full + 6 partial | 10,824 (`scrumming_bot.py`) | **Yes.** The 6 "partial/grep-only" entries are all files fully owned by other partitions (`bot_container.py`→trading-core, `base.py`/`ccxt_connector.py`/`timeframes.py`→exchange, `execution_discipline.py`→core, `gate_chain.py`→trading-rest). Correctly labelled as corroboration, not double-claimed coverage. |
| `main-window` | 1 | 6,900 | Yes — single largest GUI file. |
| `trading-core` | 3 | 7,794 | Yes (`bot_container` 3,052 + `ta_engine` 3,050 + `extractor_bot` 1,692). |
| `trading-rest` | 32 | 14,898 | Yes. |
| `stone-tablets` | 6 primary + 9 corroboration | 2,115 | Yes; all 9 corroboration files owned elsewhere. Lowest primary volume of any partition, but the assignment is a 6-file package. |
| `gui-widgets` | 5 | 10,511 | **Yes, with a caveat.** One of the 5, `tools/orphan_widget_scan.py`, is **18 lines** and is also claimed by `tools-entrypoint`. Effective scope = 4 GUI files / 10,493 lines. Not a gap — a harmless double-claim. |
| `gui-rest` | 33 | 13,782 | Yes. |
| `simulator-tab` | 16 | 5,741 | Yes — full recursive sweep of `simulator_tab/` incl. `fleet/`; matches disk exactly. |
| `exchange` | 17 | 4,929 | Yes — matches `ls src/exchange/*.py` exactly (17/17). |
| `core` | 21 | 8,274 | Yes — matches `ls src/core/*.py` exactly (21/21). |
| `periphery` | 20 (1 partial) | 4,450 | Yes — `src/__init__.py` + `src/utils/__init__.py` + 10 competition + 8 stocks = 20/20. |
| `tools-entrypoint` | 19 | 5,662 | Yes — matches `main.py` + `tools/**/*.py` exactly (19/19). |

**No partition under-reported relative to its scope.** Every directory-scoped partition (`exchange`, `core`, `simulator-tab`, `tools-entrypoint`, `periphery`) matches its directory listing file-for-file.

**Only overlap issue:** `tools/orphan_widget_scan.py` claimed by both `gui-widgets` and `tools-entrypoint`. Redundant, not a gap.

---

## 5. Verdict

> **173 of 174 source files were genuinely read. Coverage is 99.4% by file count, 99.42% by line count.**

The claim "we scanned the whole codebase" is **not yet a fact.** It becomes one after `src/design_system.py` is scanned — and that file is not an empty stub; it is a live-looking, well-documented, zero-consumer module that is exactly the class of defect this audit was commissioned to find.

Scratchpad artifacts (both file lists, for reproduction):
- `<session scratchpad>/actual.txt`
- `<session scratchpad>/reported_sorted.txt`