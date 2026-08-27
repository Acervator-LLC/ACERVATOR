<!-- Acervator v3.24.20 — generated 2026-08-04 -->

# Time-Space Complexity Audit

**Agents:** 20  
**Findings surviving verification:** 72  
**Refuted:** 1  
**Refuted items:** trading-rest: SmartWireManager._transactions is an append-only audit list that is never pruned, never persisted, and never read

---

# Acervator Performance Audit — Final Report
**Scope:** 9 subsystems, 72 verified findings, merged to 20 actionable items + 6 correctness spinoffs.
**Baseline of record:** GUI-launched replay 2.80 candles/s mean; headless 81.32 candles/s. 29x gap.
**Rule applied throughout:** where a number was not measured, it says *unmeasured*. Where a verifier issued a CORRECTION, the corrected version is what appears here.

---

## Summary — ranked by expected impact

Impact = (cost per call) × (call frequency) × (n). Not by how interesting the algorithm is.

| # | Finding (merged) | Primary file:line | Grp | Measured? | Expected impact |
|---|---|---|---|---|---|
| 1 | **Replay throughput hard-capped at 3.98 candles/s by the 50 ms QTimer asyncio pump** — 5 yield boundaries/candle × 50 ms | `fleet_replay_controller.py:513` + `main.py:955-962` | A | **Yes** (reproduced: 251 ms/candle) | **This is the 29x gap.** 4 → ~80 candles/s |
| 2 | **TA derivative recomputation: suffix-only windows + one shared per-tick bundle** (8 findings merged) | `ta_engine.py:156,167,703,717,1178,1926,2597` | B | **Yes** 1.342 → 0.760 ms/tick, bit-identical | 1.77x on TA pipeline. End-to-end share **contingent** — see §6 |
| 3 | **Stone Tablet ingest re-checksums the entire 406-tablet archive per 350-candle chunk** | `stone_tablets/registry.py:373` | B | **Yes** 7.46 s per persist | ~768 s CPU per single-asset YTD fill; ~86 h across a 406-asset universe build |
| 4 | **Boot deserializes the whole 385 MB archive into the LIVE process** | `stone_tablets/registry.py:173` | B | **Yes** 12.45 s, 2.39 GB RSS | 12.45 s blocking startup stall + 2.4 GB resident on the machine executing real trades |
| 5 | **gate.log analysis path re-reads 262 MB and retains 1.03 GB, on the Qt thread, per page turn** (4 findings merged) | `history_tab.py:774`, `gate_coverage.py:189,211,298` | B/C | **Yes** 165,047 rows / 262.1 MB / 1.03 GB heap | Multi-second GUI freeze per History page turn and per Fleet Replay start |
| 6 | **Sim `get_ohlcv` copies every row twice — 200 list allocs per bot per candle** | `sim_exchange.py:237` | A | **Yes** 11.59 → 0.29 µs/call (40.6x) | 8.0 s → 0.2 s per 19,680-candle replay |
| 7 | **Full 12-indicator vote + BB detection computed on ticks that cannot trade** | `scrumming_bot.py:5741` | B | **No** | Largest remaining lever inside `tick()`. **Not free** — feeds the Indicator Panel |
| 8 | **Balance cache is per-currency over a whole-account endpoint; zero-balance path double-fetches; retry ladders nest 3×3** (3 merged) | `data_pool.py:526`, `ccxt_connector.py:932`, `data_pool.py:510` | B | Partial | ~222 → ~6 CPM against a 600 CPM ceiling; directly reduces order-submission latency |
| 9 | **SimPriceVwapChart issues ~26,000 `drawLine` calls per repaint at 4 Hz** | `sim_visuals.py:479/490` | A/C | **Yes** 15.04 → 5.03 ms/paint | 3.0x. **Compounds with #1** — paint delays the pump slot |
| 10 | **NDJSONWriter re-opens/stats/closes the log file per entry, on the trading thread** | `logging_engine.py:120` | B | **Yes** 248.4 → 6.24 µs (39.8x) | 3 writes/trade × 248 µs = 0.75 ms stall of all 35 bots per fired trade (live only) |
| 11 | **`refresh_exchange_position_health` throttles on WALL clock inside the sim** | `scrumming_bot.py:3668` | B | **Yes** 46 vs 1 refresh per bot | **Fidelity defect, not perf.** GUI and headless run different experiments |
| 12 | **BotStatusTable rebuilds every cell + 2 QPushButtons per row, 30×/min** (+ icon cache, glow registry, double status build, tooltip scan, inspector rebuild) | `main_window.py:1458,4811,4447,4603`, `bot_wizard.py:39`, `market_inspector.py:357` | C | **Yes** ~20 ms per 2000 ms tick | GUI responsiveness only. Fixes hover/focus loss as a side effect |
| 13 | **EventBus `_history` reallocates 1000 pointers per emit and is never read; `ta.voting` has zero subscribers** (3 merged) | `event_bus.py:86,159,172`, `scrumming_bot.py:6010` | B | **Yes** 2.48 → 0.68 µs/emit | ~2.8 s across a full replay + **73.7 MB retained, never read**. Mostly a dead-state cleanup |
| 14 | **100 `Candle` dataclasses rebuilt per action tick when 99 are unchanged** | `scrumming_bot.py:5688` | B | **No** (est. ~100 µs/action tick) | Second-order: ~3–10% of the TA cost it precedes |
| 15 | **Stone Tablet registry has no `(asset,exchange)` index — 5 methods linear-scan** (3 merged) | `registry.py:257,317,385` | B | **Yes** 0.007–0.027 s | Low today. Degrades quadratically once multi-year/multi-exchange lands |
| 16 | **`MarketPairsScout.get_pair` is O(M) over the whole pair book, ~6× per bot row per 2 s** | `market_pairs_scout.py:176` | B | **Yes** 3.94 ms per 2 s tick | Low. Free to fix inside the existing `ingest_tickers` walk |
| 17 | **Sim exchange: order sweep scans every order ever placed; candle cursor re-bisects 45k rows per tick** (2 merged) | `sim_exchange.py:416`, `candle_series.py:91` | A | **Yes** 0.13–0.74 s and 1.14 → 0.16 s | Small absolute, but the sweep is **quadratic in trade count** |
| 18 | **`LogEntry.to_json` deep-copies the nested gate payload via `dataclasses.asdict`** | `logging_engine.py:92` | B | **Yes** 48.12 → 21.18 µs | ~27 µs per fired trade. Ride-along with #10 |
| 19 | **Zero-balance entry runs the vote before 3 cheaper gates — and uses a *differently-weighted* engine** | `scrumming_bot.py:5505` | B | **No** | Perf is minor. **The weights divergence is a latent correctness bug** — see §5 |
| 20 | **VersionSweep re-reads the 673-file tree ~12× with uncompiled regex** | `version_sweep.py:269` | — | **Yes** 2.7x on the secrets scan | Developer-loop seconds. Not a runtime path. Ranked last deliberately |

---

## 1. Grouping

### Group A — sim-only, safe to ship now
Files: `src/gui/simulator_tab/fleet/*`. The live engine never constructs a `FleetSimExchange`, never reads `candle_series.py`, never paints `sim_visuals.py`.

- **#1** pump quantization, fix (A) — `fleet_replay_controller.py`
- **#6** `get_ohlcv` double copy — `sim_exchange.py:237`
- **#9** price/VWAP chart polyline — `sim_visuals.py:479`
- **#17** open-order index + monotonic cursor — `sim_exchange.py:416`, `candle_series.py:91`
- **#58 spinoff** `_ss_exc` NameError — `fleet_replay_panel.py:1061`

Caveat on "safe": #1 and #11 **will change sim trade counts** on the first post-fix run. That is convergence onto the headless result, not a regression. Do not read a changed trade count as breakage.

### Group B — shared with live, needs its own gated cascade
Files under `src/trading/`, `src/exchange/`, `src/core/`. Everything here changes live trading behaviour or live process characteristics.

- **#2** TA bundle — *float-order sensitive, see the hard prohibition in §3*
- **#3, #4, #15** Stone Tablets — metadata/memory only, no gate inputs touched
- **#5** gate.log analysis — read-only display join
- **#7** below-interval TA skip — **must ship sim-gated first**
- **#8** balance fetching — `absent` flag is the MEM-259 phantom-rebuy defence, must survive
- **#10, #13, #18** logging + EventBus
- **#11** sim-clock injection — gate behind the existing `sim_mode` flag
- **#14, #19** tick-internal
- **#16** scout indexing — under `src/exchange/` by the standing rule; no trade-path consumer found

### Group C — GUI-thread only, affects responsiveness not throughput
- **#12** dashboard 2 s tick cluster
- **#5** (History tab half)
- **#9** (partially — but see the compounding note below)

**Group C is not fully insulated from throughput.** The asyncio loop is pumped by a QTimer slot on the Qt main thread (`main.py:958`, the *only* `run_forever` in the repo). A 15 ms paint delays the next `pump_async` slot. At 5 pumps/candle that converts directly into lost replay throughput. **The v3.24.19 docstrings at `fleet_replay_panel.py:1064` and `:1090-1093` are factually wrong** — "Runs on the asyncio worker thread" and "paint cost can no longer feed back into replay throughput" are both false as written. There is no worker thread. `_snapshot_lock` is uncontended and guards a race that cannot occur.

---

## 2. Implementation plan — #1, replay pump quantization

**The measurement.** `loop.call_soon(loop.stop)` is queued *before* `run_forever()`, so each `pump_async` executes exactly one `_run_once()` pass. A task rescheduled by `await asyncio.sleep(0)` lands in `_ready` *after* that pass's `ntodo` snapshot, so it does not run until the next 50 ms timer fire. **One QTimer fire = one yield boundary.**

35 bots / `_YIELD_EVERY_N_BOTS=8` → yields at `_bi ∈ {8,16,24,32}` = 4, plus the per-candle yield at `:513` = **5 yields/candle × 50 ms = 251 ms/candle = 3.98 candles/s**. Reproduced empirically: 50 candles → 250 yield boundaries → 251 pump calls. This brackets the operator's own GUI logs exactly (2.80 mean; 1.42 / 1.52 / 5.47 — the 5.47 is anchored mode, which only yields every 500 skipped candles at `:459-460`).

**Ship (A) now — ~10 lines, replay-local, zero threading risk:**

1. Add `self._last_yield = time.perf_counter()` to `FleetReplayController.__init__`.
2. Replace the unconditional per-candle yield at `fleet_replay_controller.py:513` and the per-8-bots yield with:
   ```python
   _now = time.perf_counter()
   if _now - self._last_yield > 0.020:
       self._last_yield = _now
       await asyncio.sleep(0)
   ```
3. Delete `_YIELD_EVERY_N_BOTS` entirely. v3.24.1 added it to stop a GUI freeze; under this pump it silently cut throughput 5x (1 yield/candle = 20 c/s → 5 yields/candle = 4 c/s).
4. Verify: instrument a pump counter, confirm yields/candle drops from ~5 to ~0.05 and the GUI still repaints at ~50 Hz.

**Then (B), the architectural fix:** create a dedicated loop on a daemon thread in `FleetReplayPanel._on_start_clicked` and route `asyncio.run_coroutine_threadsafe(controller.start(), _loop)` at it. v3.24.19 **already built the correct handoff** — the `_snapshot_lock` / `_pending_snapshot` / `_drain_timer` producer-consumer at `fleet_replay_panel.py:1063-1226`. It just never moved the producer across the boundary. Finishing (B) is what makes those docstrings true and the lock necessary.

**Do NOT** lower `main.py`'s `async_timer` interval. That pump is shared with the live engine — all live bot ticks go through it.

**Correct the docstrings** at `fleet_replay_panel.py:1064` and `:1090-1093` as part of this change. The pre-v3.24.19 diagnosis of "cross-thread widget access" was also wrong — those setter calls were on the Qt main thread all along.

---

## 3. Implementation plan — #2, TA derivative bundle

Eight findings, one root cause: the same window statistics are recomputed from scratch, over the full 100-candle history, by four independent entry points per tick.

**Call sites, all receiving the same `candles` list object within one tick:**
- `scrumming_bot.py:5742` → `self._voting_engine.compute_all(...)` → `BollingerBands.compute` (`ta_engine.py:707`) and `SlingshotIndicator.compute` (`:2152`)
- `scrumming_bot.py:5745-5750` → `detect_bb_proximity` (`ta_engine.py:2571`)
- `scrumming_bot.py:5807-5809` → `detect_landing_strip_v2` (`ta_engine.py:2722`)
- `scrumming_bot.py:5505-5508` → a **second, separately-constructed** `VotingEngine` on the zero-balance path

cProfile over 300 full TA ticks: 900 `_stdev` calls (3.0/tick), 1500 `_sma` calls (5.0/tick), 600 `compute_heikin_ashi` calls.

**Ship in this order — step 1 is a hard blocker:**

**Step 1 — `BollingerBands` widths (`ta_engine.py:717`).** Change the comprehension bound to `for i in range(max(0, len(sma) - self.period), len(sma))` and drop the redundant `[-self.period:]`. Standalone this saves ~0.006 ms/tick. It ships first because **it is the only site that indexes `sma`/`std` across the whole range** — until it is narrowed, any suffix-only `_sma`/`_stdev` reads the unfilled prefix. Empirically confirmed: a suffix patch raises `TypeError: unsupported operand type(s) for *: 'float' and 'NoneType'` at exactly this line.

**Step 2 — suffix-only `_sma_tail` / `_stdev_tail` (`ta_engine.py:156`, `:167`).** Run the **exact same per-window body**, only for `i in range(len(values)-tail, len(values))`. Because each output element's summation order is unchanged, the result is bit-identical (verified: `stdev_tail == _stdev[-35:]` exact `True`). Set `tail` from the max consumer need:
- `SlingshotIndicator` reads `sma_v[i]`/`std_v[i]` for `i in range(n - (squeeze_lookback+5), n)` = **last 35** (`ta_engine.py:2157-2167`)
- `BollingerBands` reads `sma[-1]`, `std[-1]`, `widths[-20:]` = last 20
- `detect_bb_proximity` (`:2580-2582`) and `detect_landing_strip_v2` (`:2728-2730`) read only `[-1]`

Use `tail=35`. Keep the `i < period - 1` warm-up branch — the `StochasticRSI` call sites at `:1185`/`:1187` (period=3 on ~72-element lists) *do* hit it.

Measured: `_stdev` 0.2055 → 0.0762 ms/call (2.7x); `_sma` 0.0309 → 0.0116 ms/call (2.7x).

> ### ⛔ HARD PROHIBITION
> **Do NOT implement `_stdev` as a rolling sum / sum-of-squares.** Measured max relative difference vs current: **2.02e-12 — not bit-identical.** Every BB consumer is a threshold comparison on these values (`bb_pos < 0.15` / `> 0.85` at `:728-739`; `squeeze = band_width < avg_width * 0.75` at `:720`; `near_upper = price >= (upper - tol_val)` at `:2595`), and `upper/lower = mid ± 2*std`, so a 2e-12 drift in `std` propagates straight into a gate decision and can flip a SCRUM/FOLD fire on a knife-edge candle. Suffix-only keeps every float operation and its order identical. Rolling does not. Same prohibition applies to `_sma`.

**Step 3 — the shared bundle.** Preferred form (no `id()` aliasing hazard): have `ScrummingBot` compute the bundle once after `candles_from_raw` and thread it as an **optional kwarg defaulting to `None`** into `compute_all` / `detect_bb_proximity` / `detect_landing_strip_v2`. Every existing external caller keeps working unchanged: `mr_inspector.py:163`, `market_inspector.py:153`, `gate_healer.py:241-252`, `indicator_panel.py:838`, `phantom_balance.py:246`, `stock_accumulation_bot.py:253`.

Bundle contents: `closes` (kills 8–9 full-window rebuilds/tick), `(sma_tail, std_tail)` keyed on `period`, `_wilder_rsi_series(closes, period)` (shared by `StochasticRSI.compute:1159-1171` and `RSIIndicator._compute_metrics:1919-1930` — verified bit-exact between the two implementations, len 85), and the `HACandle` list (shared by `detect_bb_proximity` and `detect_landing_strip_v2`).

> **If you take the memo shortcut instead of threading:** CPython can reuse the `id()` of a freed list. A stale entry served to a different candle list would **silently feed one asset's Bollinger bands to another bot** — a live correctness bug far worse than the perf win. Key on `(len, values[0], values[len//2], values[-1], period)` **and** clear the memo at the top of every tick. Do not memoise Heikin-Ashi on `id()` at all — it is a forward recurrence seeded at index 0 (`ta_engine.py:2522`), so a stale entry is unrecoverable garbage rather than a mildly wrong number.

**Step 4 — `StochasticRSI` suffix (`ta_engine.py:1178`).** Only `k_line[-1]`, `k_line[-2]`, `d_line[-1]`, `d_line[-2]` are consumed (`:1189-1192`); the dependency chain needs exactly the last `k_smooth + d_smooth = 6` stoch values. Bound the loop at `range(max(self.stoch_period - 1, len(rsi_values) - (self.k_smooth + self.d_smooth)), len(rsi_values))`. Measured 0.0390 → 0.0026 ms. Taking fewer than 6 would silently change `k_line[-2]`/`d_line[-2]` and therefore the K/D crossover tests at `:1199`/`:1210`, which drive confidence-0.8 SCRUM/FOLD signals.

**Measured combined result (steps 1–2 + dedupe):** 1.342 → 0.760 ms/tick, **1.77x, output bit-identical** across all 12 Signals' direction/confidence/details + `BBProximityResult` + `TighteningResult`. Steps 3–4 add an estimated further ~0.12 ms/tick (extrapolated from individual measurements, **not** measured as a combined figure).

**Add `slots=True` to `Candle` (`ta_engine.py:118`)** while in here — grep confirms nothing setattrs an undeclared field, and per-instance memory roughly halves.

---

## 4. Implementation plan — #3/#4, Stone Tablets

These are the two highest-value non-tick items and they share one fix shape: **stop deriving from candle bodies what the 0.2 MB MANIFEST already carries.**

### #3 — kill the per-chunk whole-archive re-checksum
`ingest_candles` (`registry.py:373`) calls `_persist_manifest()` → `storage.entry_from_tablet(t)` for **all 406 tablets** → `Tablet.compute_checksum()` on each. Measured: one pass over the live archive = **7.46 s**. `GapFiller.fill_asset` (`fetcher.py:249-278`) uses `chunk_span = 350 × 300_000 ms = 29.17 h`, so a 125-day YTD window is **~103 chunks per asset**.

1. Keep `self._entries: dict[key, TabletEntry]` as registry state, built once at load from `read_manifest()` — which already carries the stored checksum, so nothing is recomputed at boot either.
2. In `ingest_candles`, update **only the single dirty entry** before calling `write_manifest()`.
3. Add `_checksum: str | None = None` to `Tablet`; `compute_checksum()` returns the cached value when non-None; set `tab._checksum = None` at `registry.py:365` where `tab.candles = merged` assigns.
4. **Keep writing the manifest every chunk.** `fetcher.py:212-214` deliberately writes per chunk so "a crash mid-fetch loses at most one chunk." Do not "fix" this by writing less often — that trades a CPU problem for a durability problem.

Also: `compute_checksum` (`storage.py:227`) is **96.5% `json.dumps`, 3.4% SHA-256** (measured 0.084 s vs 0.003 s on XLM's 61,198 candles). Add `verify: bool = False` to `read_tablet()` and move the full-archive sweep into an explicit `verify_archive()` behind the existing CLI at `fetcher.py:583-616`. That removes 7.28 s from boot for free. **Do not change the checksum formula** — it would invalidate all 406 stored checksums; if you must, gate it behind a `SCHEMA_VERSION` bump (`storage.py:41`, currently 2) and a one-shot rehash migration.

The `fetcher.py:466-470` docstring's "~4.3 h wall clock" estimate for `build_universe` counted only the 1.3 s rate-limit sleeps. It is understated by roughly **86 hours of checksum CPU**.

### #4 — make tablet bodies lazy
`_load_from_manifest` (`registry.py:173`) full-parses 406 files at every process start: **12.45 s wall (4.78 s json.load + 7.28 s checksum verify), 2,394 MB RSS** for 7,230,993 candles (331 bytes/candle — each is a 6-element Python list of boxed floats). `main.py:485-496` runs this at app boot, so **this is 2.4 GB resident in the process executing real trades**, plus a 12.45 s blocking startup stall.

1. Populate `self._entries` from `read_manifest()` at init — **0.001 s, 0.2 MB**.
2. Add `self._tablets` as a load-on-demand cache filled by a `_tablet(key)` helper calling `read_tablet()` on first access.
3. Rewrite `coverage_summary` (`:378-401`), `stale_assets` (`:472-491`), `has_coverage`, `get_asset_availability`, `check_window_availability` to read `self._entries`. **Verified from the live MANIFEST**: its rows carry asset, exchange_id, year, candle_count, first_ts_ms, last_ts_ms — every field these return — and `sum(candle_count)` over the manifest alone = **7,230,993, the exact archive total**. main.py's entire boot usage needs zero candle bodies.
4. Only `get_candles` / `_native_slice` / `missing_ranges` force a body load. A 35-bot fleet replay then holds ~35 tablets (~200 MB) instead of 2.39 GB.
5. **Preserve one behaviour:** today a MANIFEST row whose file is missing or corrupt is detected at boot and skipped (`registry.py:174-179`). Keep a cheap `os.stat` existence check (~406 syscalls) so the warning and skip semantics survive lazy loading.
6. Add an LRU cap so a 406-asset universe sweep does not re-accumulate 2.4 GB.

Fold **#15** (the missing `(asset, exchange) → keys` index) into this same change — `self._entries` can serve that role directly. Do not ship #15 on its own merits; at 27 ms combined it is not a current bottleneck.

---

## 5. Implementation plan — #5, the gate.log analysis path

Four findings, one root cause. Measured on the operator's disk **right now**: `gate.log` + `gate.log.1`–`.5` = 481 + 32,700 + 33,082 + 32,811 + 32,871 + 33,102 = **165,047 rows across 262.1 MB** of NDJSON (1,603 B/line average). `live_log_reader._rotated_files_for` (`:176`, glob at `:197`) consumes the whole chain every time.

Two independent consumers, both synchronous on the Qt thread:

- `history_tab.py:774` `_build_joiner_indexes_for_page` — called from `_render_page` (`:540`), which is reached from `_prev_page` (`:819-821`), `_next_page` (`:823-825`), `_apply_filters` (`:507`) and `_reset_filters`. **Every page turn re-reads 262 MB.**
- `fleet_replay_panel.py:615` `gates = list(live_gate_decisions())` inside `_compute_soft_start` — materialises the whole generator, then `build_gate_index` (`gate_coverage.py:189`) holds a second reference to every dict. **Measured 1.03 GB of Python heap.** Whole operation ~4.5 s, of which 3.24 s is the JSON parse.

**Fix, in order:**

1. **Hoist the index build out of the per-page path.** Build the gate/voting index ONCE when a fetch completes (same place that sets `_last_fetched_ts`), keyed over the full `_all_trades` window. `_render_page` only probes it. Every page then joins against one snapshot — arguably more consistent than today.
2. **Narrow what is retained.** `classify_trades`/`TradeGatePairing` only ever read `entry['data']['scrum_armed'|'fold_armed'|'scrum_blockers'|'fold_blockers']` (`gate_coverage.py:102-123`). Store a 4-field projection instead of `e`. Drops the retained set ~20x and lets the parsed line be garbage-collected inside the generator loop.
3. **Stop materialising.** Change `build_gate_index` to accept any `Iterable`; change `fleet_replay_panel.py:615` to `live_gate_decisions(since=<trade window start>)`. `live_gate_decisions` is **already a generator** (`live_log_reader.py:203`) and **already supports `since` — nobody passes it.** Pick the cutoff as `min(trade_ts) - tolerance_s` to keep classification byte-identical.
4. **Make `since` actually save work.** Today `live_log_reader.py:222-229` runs `json.loads` on every line *before* testing the timestamp, so the cutoff discards work already done — the `history_tab.py:732-735` docstring's claim that it stops the iterators scanning back is false. Add a conservative file-level skip (stat mtime, skip a rotated file only when strictly older than `since` — never on a content heuristic, since sim parity tooling shares this reader) plus a cheap date-prefix test on the raw line before `json.loads`.
5. **Pass `validate=False`** on this path — `_validate_gate_entry` runs 9 field checks on all 165,047 rows for a computation that never inspects schema-optional fields.
6. **`_nearest` → bisect** (`gate_coverage.py:211`). `build_gate_index` already sorts each per-bot list (`:192-193`); the structure is there, just unused. Real measured n: **83 distinct bot_ids, average G_b = 1,988, top bot 12,366**. 597 trades × their bot's list = 3,413,906 iterations = **0.971 s**. On a sorted list the argmin of `|ts - target|` is always at the insertion point or one before it, so probing `i-1` then `i` is exact. Probe `i-1` first to preserve the current first-wins tie-break; pin it with a test using two equidistant entries.
7. **Delete the dead `_in_log_gap` call** (`gate_coverage.py:298`). Lines 296-301 assign `GateStatus.LOG_GAP` in **both** the `elif` and the `else` branch, so the scan's result is unused. Measured cost of the dead work: 0.048 s (small — the claim of "roughly doubles" was wrong by ~20x). Real status split: has_gate 374, log_gap 218, before_logging 4, no_gate_for_bot 1. If the distinction *was* intended, the `False` case ("gate entries exist near this trade but none within tolerance") has no named status and is being silently mislabelled — add one, and update the label dict at `:331-340` or it prints the raw status string.

**Related, unresolved:** the live `gate.log` writer stalled 2026-06-11T05:29Z (see #10 — `NDJSONWriter` rotation is a Windows rename hazard, `WinError 32`/`183`, documented at `logging_engine.py:150-159`). Fixing #10's persistent-handle rotation incorrectly would stall it again the same way.

---

## 6. Implementation plan — #6, sim `get_ohlcv`

Smallest diff, best measured ratio in the audit.

`FleetSimExchange.get_ohlcv` (`sim_exchange.py:237-238`) returns `[_ohlcv_row_from_series(r) for r in series.get_history(limit=limit)]`, and `get_history`'s last line is `return [list(r) for r in self.rows[start:end]]`. **Two full row copies — 200 six-element list allocations per call.**

Sim bots really do take this path: `self._data_pool` defaults to `None` in `BotContainer.__init__` (`bot_container.py:872`) and is only assigned by `BotManager` (`:1583`, `:2021`); Fleet Replay builds bots directly via `ScrummingBot(bot_config, exchange, enable_phantoms=False, sim_mode=True)` at `fleet_replay_controller.py:150-152`, never through `BotManager`. So `_get_ohlcv` (`scrumming_bot.py:2226-2234`) falls straight through.

1. Change `get_history`'s last line to `return self.rows[start:end]`. The slice is already a fresh outer list, so callers cannot append or reorder the series.
2. Delete `_ohlcv_row_from_series` (`sim_exchange.py:38-40`); return the slice directly.
3. Same one-line treatment for `CandleSeries.get_current` (`candle_series.py:102-106`), called from `get_ticker`, `get_orderbook`, `place_order`, `_sweep_open_limit_orders` and `_collect_visual_snapshot`.
4. **Belt-and-braces variant if you want zero aliasing risk:** make rows tuples at ingest in `build_candle_series_from_rows` (`candle_series.py:142`, `clean.append([...])` → tuple). Immutable, still ccxt-indexable, still zero-copy.

The only thing given up is protection against a caller mutating a returned row in place. The sole consumer is `candles_from_raw()` at `scrumming_bot.py:5688`/`:5506`, which parses rows into `Candle` objects and never writes back. Confirm that, or ship the tuple variant.

Measured: 11.59 → 0.29 µs/call, **40.6x**. 688,800 calls per 19,680-candle replay = **8.0 s → 0.2 s**; 14.3 s → 0.4 s at the full 35,282-candle YTD span. Values are bit-identical floats — no arithmetic, ordering, or precision changes.

---

## 7. #7 — TA on below-interval ticks: why this is NOT a free win

Recorded here in full because the original claim's headline word was wrong and the correction matters.

Mechanics confirmed: `limit=100` at `scrumming_bot.py:5686`; 12 indicators instantiated at `ta_engine.py:2342-2373`; `below_interval` at `:5754` depends only on `delta_pct` computed at `:5661`; the return at `:5767` fires before any trade path. The gate could mechanically be hoisted above `:5741`.

**But "discarded" is false.** `summary` is written to `self._last_summary` at `:5743` and `bb_result` to `self._last_bb` at `:5751`, and both have live readers:
- `main_window.py:4909-4910` — `if bot and getattr(bot, '_last_summary', None)`
- `fleet_replay_panel.py:1148` — `"summary": getattr(bot, "_last_summary", None)`, feeding `sim_visuals.py`'s per-bot TA grid
- The block comment at `:5676` states the intent verbatim: *"TA VOTING ENGINE — always compute (feeds Indicator Panel)"*
- Both are consumed immediately at `:5758-5759` to build the READ log line

**And `_last_bb` is a trading input on the next tick** — the SMART CARTRIDGE threshold derivation at `scrumming_bot.py:5089-5131` reads it, so a staler `_last_bb` can shift `_cartridge_pct` and change whether Max Cartridge fires.

**Shipping order:**
1. Add `self._panel_wanted`: `False` when `self._sim_mode` is True (`scrumming_bot.py:280`), `True` otherwise.
2. Hoist `below_interval` to immediately after `:5661` (both inputs exist there).
3. Guard the OHLCV fetch + `candles_from_raw` + TA block (`:5685-5751`) with `_needs_ta = (not below_interval) or self._fold_queue_usd > 0 or self._dist_accumulator > 0 or self._panel_wanted`.
4. On the skip path still fetch the ticker (already at `:5802`), emit the READ line, return.
5. Guard `_check_circuit_breakers` separately — it only reads `candles[-1]` (`:2405`), so hand it the raw last row.
6. **Enable the skip ONLY when `self._sim_mode` is True.** Leave live on the always-compute path until a live A/B shows identical gate rows.

Indicator math is untouched, so no float-ordering risk.

---

## 8. Correctness spinoffs found during the perf audit

These are not performance findings. They surfaced while reading hot code and need their own tickets.

| Issue | Location | Why it matters |
|---|---|---|
| **Initial entry uses a differently-weighted VotingEngine** | `scrumming_bot.py:5505` vs `:5742` | The local `VotingEngine()` at `:5505` is constructed with **no weights** → `DEFAULT_WEIGHTS` (`ta_engine.py:2337`). `self._voting_engine` at `:5742` was built with the bot's configured `ta_weights` (`:316-317`). **These two engines can disagree on consensus.** "Just reuse `self._voting_engine`" is NOT a behaviour-neutral refactor — it changes which weights decide initial entry. Resolve deliberately. |
| **`list.remove` can delete the wrong lot** | `scrumming_bot.py:7058` (+ `:8511-8529`, `:8896-8917`) | `list.remove` deletes the FIRST dict that compares equal, not necessarily `_lot`. Two lots with identical `units` and `initial_buy_price` — possible after the proportional reconcile rescale at `:8649-8653` — cause the wrong one to be dropped, corrupting that lot's `initial_buy_price` provenance, which is the MEM-171 profit floor and therefore a real trading input. Fix via index-walk + single filter-rebuild; ship behind `_main_lots_invariant_ok` (`:10769`) with a two-identical-lots fixture. **(The claimed O(M²) dict-compare complexity was wrong — the list is sorted and consumed from the head, so `remove` hits index 0 and short-circuits on identity. The correctness bug is the real finding.)** |
| **Fold dequeue drops non-eligible tranches** | `scrumming_bot.py:7997` | `t not in _eligible` is value-equality. Two tranches with identical `usd/units/ref/initial_buy_price/created_ts` are BOTH dequeued when only one was eligible, silently deleting a queued tranche and its profit floor. `created_ts` is `time.time()` at `:7049` — exact duplicates are unlikely in live but **entirely possible in a replay** where many tranches are created within one clock tick. Fix: `_elig_ids = {id(t) for t in _eligible}`. This also makes the existing FOLD DEQUEUE MISMATCH warning at `:8005-8010` meaningful instead of a false-positive detector. |
| **`EventBus` has no `unsubscribe()` — 3 call sites hit a silent `AttributeError`** | `event_bus.py:89`, `logging_engine.py:557,561,565,571` | `LogManager.attach_to_bus` documents itself as *"Idempotent: calling twice replaces the prior subscription rather than double-writing each trade"* (`:553`). **That guarantee is false** — all four `bus.unsubscribe()` calls raise into `except Exception: pass`. A second `attach_to_bus` would double every trade.log / gate.log / voting.log row. `main.py:520` is currently the only caller, so it is latent. Separately, `BotManager.__init__` leaks 3 global subscribers per Nuclear Mode start cycle. |
| **MEM-220 queue cap is defeated by its own timeout path** | `ccxt_connector.py:578` | The `finally` decrements `_sync_queue_depth` while the sole worker is still blocked, so the cap check at `:523` sees 0 in-flight. Every subsequent submission lands in the executor's unbounded `SimpleQueue`. Worse, the constants are inverted against their own rationale: `MEM_220_CALL_TIMEOUT_SEC = 25.0` (`:54-57`) vs `sync_connect`'s configured `"timeout": 30000` (`:315`) — **our timeout always fires first**, so the "pathological case" the comment describes is the only case. `place_order` shares this worker (`:1049-1058`) and TD-014 (`:946-958`) deliberately does not retry, so a stale queued order can fire late. |
| **OHLCV coalescing permanently defeated for short-history symbols** | `data_pool.py:401` | The guard `len(entry.candles) >= limit` can never be satisfied when the exchange has fewer than 100 candles. The identical guard in the double-check at `:436-437` also fails, so **every call cold-fetches — 100% miss rate, forever**. The bot still trades on those candles (`scrumming_bot.py:5503` only requires ≥30). Strictly worse than the pre-v3.23.74 thundering herd this method was written to eliminate. Fix: record `fetched_limit` on `CacheEntry` and test against that. |
| **`_apply_stat_fields` references an undefined name in its own except handler** | `fleet_replay_panel.py:1061` | `_ss_exc` is bound nowhere; the handler binds `_ap_exc`. The `NameError` is raised *inside* the except block so it is not caught, propagates into `_drain_visual_snapshot` at `:1183` (no try around that call), and kills the whole frame before the per-symbol loop at `:1184` runs. Symptom reads as "gate lights and chart froze" — it would be misdiagnosed as a dead feed. |
| **`place_order` rejects `OrderType.IOC_LIMIT`** | `sim_exchange.py:315-318` | `scrumming_bot.py:9592` emits it when `aggressive_trading` is on; the sim raises `ValueError`. Sim-only, but it means aggressive mode is untestable in replay. |

---

## 9. #11 — the fidelity defect (read this before trusting any parity run)

`refresh_exchange_position_health` throttles on **wall clock** (`scrumming_bot.py:3666-3670`, `EXCHANGE_HEALTH_REFRESH_COOLDOWN_SEC`), including inside the simulator. The refresh **count** is therefore `elapsed_wall_seconds / 300` — proportional to how *slow* the machine ran:

- GUI run at 1.42 candles/s: 19,680 candles = 3.85 h = **~46 refreshes per bot**
- Headless at 105.8 candles/s: 3.1 min = **~1 refresh per bot**

Each refresh rewrites `stats.total_trades`, `stats.exchange_trade_count` (max-of-floors at `:3878-3880`), `realized_pnl_exchange`, `avg_entry_exchange`, `cost_basis_total_exchange`, `fees_paid_exchange`, `cash_balance_usd`, `active_buy_orders`, `active_sell_orders`. **A 46x difference in how many times bot state is rewritten, purely as a function of machine speed.**

This means **the GUI and headless replays are not the same experiment**, and the parity harness at `fleet_replay_panel.py:1326` cannot mean anything until it is fixed. It also means fixing #1 will visibly move sim trade counts — that is convergence, not breakage.

**Fix:** inject a clock on the bot (default `time.time`) and have the Fleet controller point it at `FleetSimExchange._master_clock.current_ts_ms() / 1000.0`. A 300 s cooldown then means 300 **sim** seconds = one refresh per 60 five-minute candles, identically in GUI and headless. Gate the injection behind the existing `sim_mode` flag so live keeps wall clock, which is correct for live.

The CPU cost of the refresh is *not* the problem (measured 53–85 µs per refresh at T=350–680). Index the sim tape (`FleetSimExchange._trades_by_symbol`) as a separate, behaviour-neutral cleanup.

---

## 10. What this audit could NOT determine without profiling

Stated plainly. These are the gaps, and the measurement that settles each.

### 10.1 ⚠️ The single most consequential unknown: **the TA call rate per candle in Fleet Replay**

The audit contains a direct internal contradiction that changes item #2's ranking by two orders of magnitude:

- Findings #11–#18 measured the TA pipeline with `freq=per-candle` and a harness driving `compute_all` once per tick. Prior profiling attributed **~53% of sim runtime** to `_sma`/`_stdev`.
- The verifiers on findings #2, #3 and #10 established that `tick()` returns at `scrumming_bot.py:4553` before reaching the TA block on **59 of every 60 scheduler ticks** (`_base_skip = int(300/5) = 60` at `:4542`, from `tick_interval = 5.0` at `:2159-2161` and `scrum_read_rate_min = 5` at `fleet_replay_controller.py:136-137`). Their arithmetic gives **~250 action ticks per bot per 15,000-candle replay in SEARCH**, ~2,500 in TRACK/FIRE.

If TA runs once per candle: 1.33 ms against a 12.3 ms/candle headless budget = **~11% of runtime**, and the #2 fix is worth ~4.6% end-to-end.
If TA runs once per 60 candles: **~0.18%**, and #2 drops below #10 in the ranking.

These cannot both be true. The 53% profiling attribution suggests the former; the read-rate code suggests the latter. Possible reconciliations: the replay maps one master tick to one candle with an accelerated clock so `tick_interval` and the candle interval coincide; or the fleet spends most of its time in TRACK/FIRE where `_base_skip` shrinks; or the 53% figure came from a harness, not a replay.

**Measurement that settles it in one run:** add a module counter to `ta_engine.VotingEngine.compute_all` and to `FleetReplayController`'s candle loop; run 1,000 candles headless; print `compute_all_calls / (candles × bots)`. If the ratio is near 1.0, ship #2 at rank 2. If near 0.017, demote it below #10.

**Do not ship #2 before running this.** The fix is bit-identical and harmless, but the sequencing and the effort budget depend on the answer.

### 10.2 No end-to-end profile of a GUI replay exists

Every measurement in this audit is a microbenchmark or a targeted reproduction. There is no `cProfile` of an actual GUI Fleet Replay attributing wall time across the pump, paint, tick and TA. Finding #1's 251 ms/candle was reproduced in isolation (`scratchpad/pump.py`) and brackets the operator's logged 1.42–5.47 candles/s exactly — which is strong evidence but not the same as an in-situ profile.

**Measurement:** run a 500-candle GUI replay under `cProfile` with the Qt event loop instrumented, and separately with fix #1(A) applied. The delta is the honest number for #1, and the residual tells you whether #2/#7/#9 matter at all afterward.

**Confound to control:** the screen recorder (`screen_recorder.py:445`) is opt-in but the operator turns it on precisely when capturing GUI performance. On this machine `_best_engine()` resolves to `'gif'` (cv2 absent, ffmpeg not on PATH, PIL present), which samples 1 frame in 3 and does an in-memory LANCZOS half-scale — cheaper than the PNG path the original finding assumed, but not free. **If the 2.80 candles/s figure was measured with the recorder running, it is not comparable to the 81.32 headless number.** Re-measure both with the recorder off.

### 10.3 Unmeasured — the whole `scrumming_bot.tick()` interior

Findings #2, #3, #4, #5, #6, #9, #10, #14, #19 are all **structural analysis with no wall-clock attribution**. The verifiers correctly downgraded several of them (#5 from high to low at ~10–20 µs/action tick; #6 to a two-line change, not a fused-pass rewrite; #9 to a documentation defect; #10 to sub-microsecond). But nobody profiled `tick()` itself.

**Measurement:** `cProfile` a headless 1,000-candle run with `tottime` sorted, restricted to `scrumming_bot.py`. That produces the real ordering of the tick interior and would either promote or kill items #3, #5, #14 outright.

### 10.4 Values of `n` that could not be established from code

| Symbol | Where | Status |
|---|---|---|
| **W** = wire count | `bot_visualizer.py:3142` `_WireCanvas.paintEvent`, O(W²) | **W = 0 today.** `~/.acervator/bot_state.json` holds 35 bots and **zero** `smart_wire_routes`; `paintEvent` early-returns at `:3130-3131`. Latent only — bites if the operator uses Quick Routing Matrix Connect with large selections (35×34 = 1,190 wires). **Present-day cost: exactly zero.** |
| **S** = scored signals | `market_inspector.py:357` `_render_signals` | Bounded by a runtime-populated watch list. Never established. This fails the project's own evidence bar and is why it sits at rank 12, not on its own merits. |
| **W** = MainWindow descendant QObjects | `main_window.py:4603` tooltip scan | Not determinable statically. Three recursive `findChildren` every 5 s over an unknown tree. |
| **M** = exchange pair-book size | `market_pairs_scout.py:250` | Bounded by the exchange's market count (Coinbase ~700, Binance ~2,900), not by the 406-asset archive. Measured indirectly: 210 `get_pair` calls against a 650-pair book = 3.94 ms. |

**Measurement for all four:** one instrumented GUI session logging `len(self._wires)`, `len(self._last_signals)`, `len(self.findChildren(QWidget))` and `len(self._snapshots[eid])` once per minute.

### 10.5 Speedup multipliers deliberately not claimed

- **#7** (below-interval TA skip): no multiplier. Depends entirely on §10.1 and on what fraction of ticks are below `scrumming_interval_pct` (sim default 1.0 at `fleet_replay_controller.py:121`; live default 3%). That fraction is a strategy property, not a code property, and varies by asset volatility.
- **#8** (balance fan-out): 222 → 6 CPM is arithmetic from the 10 s TTL and C ≈ 37 currencies, not a measurement. The downstream claim — that removing ~216 CPM reduces `place_order` latency and `CCXTQueueFullError` incidence — is a mechanism argument (`max_workers=1` at `ccxt_connector.py:263-266`), not a measured latency delta.
- **#2 steps 3–4 combined:** the 1.342 → 0.760 ms figure is measured for steps 1–2 plus dedupe only. The additional ~0.12 ms from steps 3–4 is the **sum of individually measured items**, not a measured combined run. Re-measure after implementing.
- **#12** (~20 ms/2 s tick): an equivalent-shape reconstruction (8 items + 2 buttons + stylesheet + drop-shadow × 35 rows = 10.4 ms, plus 7 ms `_get_coin_icon` and 4 ms `get_pair`), not an in-app measurement.

---

## 11. Demoted — verified real, but not worth queueing

Recorded so nobody re-audits them. Each was confirmed as a real code pattern and then measured or reasoned to below the bar.

| Finding | Why demoted |
|---|---|
| **#5** duplicate gate diagnostics (`scrumming_bot.py:6705`) | "Unconditionally" is false — `:6705` is only reached after the dust-band park (`:4901`) and below-interval (`:5767`) returns, so these are decision-relevant ticks. ~10–20 µs against a millisecond-scale `compute_all` that already ran. **This is a maintenance finding** (two hand-synced sources of truth for blockers, admitted in the comments at `:6644-6654` and `:7376-7382`) **dressed as a performance finding.** Do move (a) — derive blockers from `chain_result.blocked` — for the drift risk, keeping the strings char-identical. Skip (b) and (c). |
| **#6** FOLD_DIAG double scan (`:7480`) | "99% discarded" is false for the first scan — `_per_tranche_eligible` is a live branch condition at `:7495` and `:7541`. Only `_patent_only_eligible` is wasted; move its sum inside the `% 100 == 0` branch. Two-line change. The block is marked *"REMOVE THIS BLOCK after diagnosis is complete"* at `:7475-7476` — **ask the operator whether it can be deleted outright.** |
| **#9** MEM-258 park pre-work (`:4566`) | Hoisting the park above the stack reconcilers (`:4821`, `:4834`) is a **live-money regression** — a bot parked at target would stop reconciling pending stack tranches and stop detecting fills on open Visible-mode orders. No measurable win either (sim no-ops, live already throttled). **What survives is a documentation defect:** the comment at `:4873-4878` claims "No TA evaluated... No fresh balance fetched downstream" when six awaits have already run. Fix the comment; add O(1) pre-checks to the reconcilers; move only `refresh_exchange_position_health` (self-described as "decorative" at `:4567`) below the park. Hysteresis must stay above the return or the fee-thrash regression at `:4851-4863` returns. |
| **#10** `_ensure_capital_reservation` above the skip gate (`:4509`) | Every cited number is exact — and the honest severity is low. One sub-microsecond coroutine allocation × 525,000. Ship move (1) only: `if not self._sim_mode: await ...` — behaviour-identical, same predicate one frame earlier. **Do not ship move (2)** (below the skip gate) without first reading the staleness-prune threshold in `capital_reservation.py`; if it is shorter than `scrum_read_rate_min` minutes, a parked bot's reservation gets reaped and its capital released to siblings. Fund-safety consequence for a sub-microsecond win. |
| **#23** `detect_momentum_funnel` O(A²) | Structurally guaranteed to produce nothing — `main_window.py:5403` declares `correlations = {}` and never populates it ("v3.23.6x future work"). Add the two-line `if not correlations: return []` guard while you are in the file; note the avg-corr double loop at `:314-319` makes it O(A³) in the dense case that will actually arrive when the feature lands. |
| **#24** `_heartbeats` never pruned | The v3.24.14 leak (16,558 bot_ids, 6.5 MB) is fixed; the operator purged the file 2026-08-03 (28 reservations / 35 heartbeats / 11 KB now). The **growth path** remains — `prune_expired` (`:567-614`) deletes reservations but never heartbeats. Ship the `prune_expired` half; gate the `_load` boot-GC behind a stale-file restart test. |
| **#32** `_WireCanvas` O(W²) | W = 0 in live state. Latent. |
| **#33** native_chart Slingshot recompute | Gated behind `self._show_slingshot`, initialised `False` at `native_chart.py:152` and only set via the per-panel "Sling" checkbox. **Defaults OFF — never executes on a stock session.** Worth noting the guard's second conjunct `self._show_bb is not None` is vacuous (`_show_bb` is a bool) — very likely a typo for `and self._show_bb`. Decide intent before touching. |
| **#35** `PerBotVotingReadout` ResizeToContents | The O(B²·C) = 6,125-measurements figure is wrong by ~2 orders. Qt coalesces ResizeToContents through a delayed-resize `QBasicTimer`, and `sizeHintForColumn` iterates only viewport-visible rows. Real cost: 175 item allocations + one column re-measure per drain. Fix the allocations (mutate items instead of replacing) as a ride-along. |
| **#36, #40** native_chart marker scan / font churn | Both real. #40's object counts were wrong (3 QFont + 3 QFontMetrics, not 4+2). **The important half of #40 is not perf:** line `1593` rebinds the local name `fm` from `QFontMetrics(font_sm)` to the marker font's metrics, so the crosshair price badge (`:1631`), time badge (`:1651`), OHLCV tooltip (`:1679`) and `_sub_axis_label` (`:1401`) are all measured with Consolas-7-Bold instead of Consolas-8 once any marker is drawn. Fixing it **changes pixel output** — badges get slightly wider. Flag in the changelog; the operator has rejected chart changes on look before. |
| **#37** locust node repaint | Real, but the constant-factor inventory was partly wrong (one QFont, not three) and the anchor line is `291`, not `300`. Ride-along: move `setToolTip` out of `paintEvent` into `set_bot_data`, hoist the two function-level imports. Gate `update()` carefully — the eye pulse at `:544` advances `self._phase` every frame for every state. |
| **#38** visual-snapshot cadence mismatch | Mechanism real, impact below the bar — the discarded work is 35 getattr chains and dict literals (**#57 measured it: 40.60 µs per refresh, 53 ms across an entire replay, 0.02%**). Frame-dropping is the documented deliberate design (`:1110-1113`). The 26%-discarded figure also imported the headless baseline into a GUI-only path. **Measured and cleared — do not chase it again.** |
| **#39** GateLightsCell hex parsing | Correct and cheap to fix (hoist six `QColor` constants + one `QFont`). Ride-along with #12. |
| **#48** screen recorder | Headline mechanism does not execute here — engine resolves to `'gif'`, not PNG. Relevant only as a **measurement confound** (§10.2). |
| **#50** History `_grade_row` O(R²) | Bounded at 10,000 iterations by `PAGE_SIZE = 100`. A few ms, dwarfed by the gate.log read in the same function. Fix while #5 has the file open. Note `_resolve_bot_label` is *also* called per row in `_export_csv` (`:855`), where it is O(rows_total × B) and unbounded. |
| **#65** double list copy on OHLCV hit | Six-character fix at `data_pool.py:406`, `:439`, `:455`. Worth roughly nothing in wall time; the finding says so itself. |
| **#66** fetch-lock dicts never evicted | K is tens to low hundreds of small objects. Not a memory problem. **Real symptom is cosmetic and already cost the operator time:** the slot counts at `main_window.py:2442-2447` drift up and never come down — that is the "+35 slots between builds" signal chased at `:2438-2441`. Fix the `pop` in `unregister`; guard any sweep with `lock.locked()`. |
| **#72** VersionSweep | Not a runtime path — grep finds callers only in its own `main()` at `:1119` and in `_archive/`. Not imported by `main.py`, not invoked by `tools/check_release_readiness.py`. Developer-loop seconds. |

---

## 12. Suggested cascade sequencing

**Cascade 1 — sim-only, no gate risk (Group A).** #1(A), #6, #17, and the `_ss_exc` crash fix. Then re-measure GUI replay throughput against the 2.80 candles/s baseline **with the screen recorder off**. This is where the 29x lives; everything else is noise until it lands.

**Cascade 2 — measurement.** Run §10.1's `compute_all` call-rate counter and §10.2's in-situ profile against the post-Cascade-1 build. **Re-rank #2, #7, #14 from the result.** Do not skip this — half the ranking above is contingent on it.

**Cascade 3 — Stone Tablets (Group B, no gate inputs touched).** #3 then #4 then #15 as one change; #4 and #15 share the `self._entries` index. Highest-value work that cannot flip a trade decision.

**Cascade 4 — TA bundle (Group B, float-order sensitive).** #2 in the strict order §3 gives: BB widths → suffix `_sma`/`_stdev` → bundle → StochRSI. Bit-identity harness on every step. Honour the rolling-accumulator prohibition.

**Cascade 5 — correctness spinoffs (§8).** These are separate tickets, not performance work, and two of them (wrong-lot removal, tranche dequeue) touch the MEM-171 profit floor. `tests/test_gate_chain_parity.py` against the v3.18.9 baseline fixture exists precisely to catch this class of change.

**Cascade 6 — live-side (Group B, gated).** #8, #10, #11, #13, #18. Ship #11 first — until the sim clock is injected, no parity run comparing GUI to headless means anything.

**Cascade 7 — GUI responsiveness (Group C).** #12, #5's History half, #9's polish items. Preserve the MEM-239/241 visual language byte-for-byte in any extracted style constants — that mapping is the operator's read of what a click will do.

**Standing gate:** `tools/check_release_readiness.py` must return `[OK] Release-ready (vX.Y.Z, N tests)` before any `__version__`, `main.py:current_version`, or CHANGELOG edit in any of these cascades.

---

# Appendix — independent critic / coverage audit

## 1. Files in no subsystem scope — never read

Enumerated with `os.walk` over `src/` + `tools/`, excluding `__init__.py`: **159 source files. The report references 34. 125 files / 47,484 LOC were never opened.**

Most are genuinely cold. Four are not, and one of them is on the trade-decision path:

| File | LOC | Why it should have been in scope |
|---|---|---|
| `src/trading/gate_chain.py` | 877 | **Evaluated twice per action tick** — `scrumming_bot.py:6871` `self._scrum_chain.evaluate(_scrum_ctx)`, `:7643` `self._fold_chain.evaluate(_fold_ctx)`. This is the SCRUM/FOLD fire decision itself. |
| `src/core/state_manager.py` | — | Whole-fleet JSON serialize on a 60 s QTimer (`main.py:975-978`) — see §2. |
| `src/trading/smart_wire.py` | 960 | Called from inside `tick()` at `scrumming_bot.py:1531`, `:1588`. Source of the growth defect in §2. |
| `tools/harness/coding_archetype.py` (+`scaffolding.py` 582, `gui_archetype.py` 567) | 519 | `.claude/settings.json:15` wires **PostToolUse Write\|Edit → archetype_gate**. It runs on *every file write*. The report ranked `version_sweep.py` last (#20) as "developer-loop seconds"; this path fires orders of magnitude more often and was never looked at. |

Whole directories with zero coverage: `src/competition/`, `src/stocks/` (except `stock_accumulation_bot.py`), `src/core/` beyond `event_bus`/`logging_engine`/`version_sweep`.

**I measured `gate_chain.py` rather than assert it** (44 `GateResult(` allocations, 51-field `GateContext`, no short-circuit by design):

```
GateContext field count: 51 (46 required)
scrum chain: 14 gates (13 regular + 1 override)   evaluate: 7.97 us
fold  chain: 10 gates ( 9 regular + 1 override)   evaluate: 6.01 us
GateContext ctor: 1.92 us
TOTAL per action tick (2 ctx + 2 chains): 17.83 us
```

**Verdict: below the bar.** 17.8 µs against a ~1.3 ms `compute_all` is ~1.4%. Recording it so nobody re-audits. The gap is closed, not open. (Blocker f-strings are built only on the failing branch, so the no-short-circuit design is cheaper than it looks.) One doc defect: `GateContext`'s docstring says *"Constructed once per tick"*, but it is constructed twice — `scrumming_bot.py:6791` and `:7571`.

---

## 2. Categories of complexity problem never considered

### 2a. Unbounded per-tranche persistence growth — **real, measured, missed entirely**

`scrumming_bot.py:1804`:
```python
wc = t.setdefault("wire_credits", [])
wc.append({"source": src, "usd": share, "ref": rf, "ts": credit["ts"]})
```

This runs inside `for t in self._fold_tranches:` — **every Smart Wire credit event appends one entry to every open tranche.** `grep -rn "wire_credits" src/` finds **no `pop`, no slice, no cap, no prune anywhere.**

Measured against the operator's live `~/.acervator/bot_state.json` right now:

```
bot_state.json: 1,414,794 bytes (1.41 MB), 35 bots
largest bot 7c4c4ff3: 373,723 B  (next largest: 37,395 B — 10x gap)
  └ scrumming_state 370,429 B
      └ fold_tranches 363,503 B  (27 tranches)
          └ per tranche 19,333 B, of which wire_credits = 19,148 B (99.0%)
            wire_credits len = 99 entries; max fold_tranches len across fleet = 165
```

Growth is O(credit events × open tranches) with no ceiling. This is memory growth **and** I/O amplification **and** repeated JSON serialize — three of the categories the prompt names — in one defect, and it is invisible to every subsystem the audit scoped.

### 2b. Whole-fleet JSON serialize on the Qt main thread, every 60 s

`main.py:975-978`:
```python
def periodic_save():
    bot_manager.save_all_state()
save_timer.start(60000)
```

`state_manager.py:106` does `json.dump(state, f, indent=2, default=str)`, and `:105-110` also does `self._backup_path.write_bytes(self._path.read_bytes())` — a full read+write of the existing file before the replace.

Measured on the real file: **8.0 ms serialize** (1.37 MB out at `indent=2`; 7.5 ms / 0.77 MB compact), plus ~4.2 MB of file I/O per save (1.41 read + 1.41 backup write + 1.37 write).

**This is the report's own Group C mechanism, and it missed it.** §1 correctly argues "a 15 ms paint delays the next `pump_async` slot… at 5 pumps/candle that converts directly into lost replay throughput." An 8 ms+ serialize plus 4.2 MB of synchronous I/O on that same thread is the identical mechanism, on a fixed timer, and it scales with §2a's unbounded growth. It is not in the report at any rank.

### 2c. Negative result worth recording

I tested whether §8's `t not in _eligible` (`scrumming_bot.py:7997`) is also a *perf* problem, given 19 KB tranches:

```
27 tranches / 3 eligible, real data:
  value-equality filter (current)      : 1.9 us
  id()-based filter (proposed fix)     : 1.5 us   -> 1x
  165 tranches / 20 near-identical     : 206 us
```

**The report was right to treat `:7997` as correctness-only.** Dict `__eq__` short-circuits on the first differing key, so `wire_credits` is never reached. Do not re-open this as a perf item.

---

## 3. Speedup numbers not supported by measurement

**Finding #1, summary table: "4 → ~80 candles/s".** This is the headline of the whole audit and the arithmetic does not support it.

The report's own model: 5 yields/candle × 50 ms = 250 ms/candle of pump quantization. I verified the yield sites — `fleet_replay_controller.py:465` (per-8-bots), `:513` (per-candle), and confirmed `tick_delay_s=0.0` at `fleet_replay_panel.py:836` so `:511` is not a third source. The model is sound.

But removing 250 ms from the measured budget gives:

| Baseline | ms/candle | minus 250 ms pump | post-fix ceiling |
|---|---|---|---|
| 2.80 c/s (logged mean) | 357 | 107 | **9.3 c/s** |
| 1.42 c/s (logged low) | 704 | 454 | **2.2 c/s** |
| headless reference | 12.3 | — | 81.32 c/s |

The claimed ~80 c/s is **8.6x to 36x above what subtracting the pump can yield.** It is reachable only if every non-pump cost in the GUI path is zero — i.e. the number is the headless baseline, not a computed post-fix figure.

Related unsupported claim, §2: the 3.98 c/s cap *"brackets the operator's own GUI logs exactly (2.80 mean; 1.42 / 1.52 / 5.47)."* A cap cannot explain observations **below** it, and 1.42 / 1.52 / 2.80 are all below 3.98. The cap explains none of the four numbers directly; 5.47 needs the anchored-mode escape and the rest need ~95–450 ms/candle of unattributed cost. "Brackets exactly" is doing work the evidence does not support.

---

## 4. Likely wrong in a way verifiers sharing the framing would miss

**The audit diagnoses in #38 exactly the error it commits in #1.** §11, finding #38: *"The 26%-discarded figure also imported the headless baseline into a GUI-only path"* — flagged, measured, cleared. Finding #1's "→ ~80 candles/s" imports the headless baseline into a GUI-only path in precisely the same way. A verifier who accepted the framing "#1 is the 29x gap" would check the 250 ms arithmetic (correct) and never subtract it from the actual budget.

This propagates into sequencing. §12 Cascade 1 says *"This is where the 29x lives; everything else is noise until it lands."* If the true post-fix figure is ~9 c/s rather than ~80, then ~107 ms/candle of GUI-only cost survives Cascade 1, and #9 (paint, 15.04 → 5.03 ms) and #12 (~20 ms/2 s tick) are **not** noise — they are a meaningful share of the residual. The report's own §10.2 concedes *"no `cProfile` of an actual GUI Fleet Replay"* exists, yet the summary table prints the 80 figure without that caveat attached.

**Recommended correction:** restate #1's expected impact as *"removes a measured 250 ms/candle; post-fix throughput unmeasured, bounded above by ~9 c/s from the 2.80 baseline"* — and promote §10.2's in-situ profile from Cascade 2 to a Cascade 1 exit criterion, since the ranking of #9 and #12 depends on the residual.

---

## Additions recommended to the queue

| # | Item | File:line | Evidence |
|---|---|---|---|
| N1 | `wire_credits` grows without bound; 99% of a 19 KB tranche, 363 KB in one live bot | `scrumming_bot.py:1804` | measured on live `bot_state.json` |
| N2 | 60 s whole-fleet JSON serialize + 4.2 MB I/O on the Qt/pump thread | `main.py:977`, `state_manager.py:106` | 8.0 ms measured |
| N3 | Correct #1's expected-impact figure and re-sequence Cascade 1/2 | report §1, §12 | arithmetic above |
| N4 | `tools/harness/*` runs on every Write via PostToolUse; unaudited and higher-frequency than #20 | `.claude/settings.json:15` | hook wiring confirmed |
| — | `gate_chain.py` — **audited by me, cleared at 17.8 µs/tick.** Do not re-open. | `gate_chain.py:757` | benchmark above |