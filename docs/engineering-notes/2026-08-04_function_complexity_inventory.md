<!-- Acervator v3.24.20 — generated 2026-08-04 -->

# Per-Function Time/Space Complexity Inventory

Exhaustive, not ranked. Every function in every source file has a row.

## Coverage proof

Coverage is mechanical, not asserted. An AST walk over `FunctionDef`+`AsyncFunctionDef` produced the expected count per file; the inventory's row count was checked against it.

| metric | value |
|---|---:|
| Source files | 174 |
| Functions found by AST | 2,604 |
| Rows produced | 2,606 |
| Files with zero rows | 0 |
| Workers reporting | 26 / 26 |

Two reconciliations, both explained:

- `tools/harness/coding_archetype.py` reports **+3** over its manifest count. That file was edited during the run (the gate-calibration fix added exactly three functions), so the worker read a newer version than the manifest was built from.
- `src/gui/testnet_tab.py` reports **-1**. Every distinct function name is covered; a `@property`/`@setter` pair sharing one name collapsed into a single row.

No file was skipped and no function name is absent from the inventory.

## Distribution by time complexity

| class | functions | share |
|---|---:|---:|
| O(1) | 1,290 | 49.5% |
| other | 685 | 26.3% |
| O(n) linear | 394 | 15.1% |
| O(n log n) / O(log n) | 124 | 4.8% |
| O(n^2) / O(n*m) | 113 | 4.3% |

## Distribution by call frequency

| frequency | functions |
|---|---:|
| rare | 1,184 |
| startup | 403 |
| periodic | 386 |
| per-trade | 173 |
| per-candle | 166 |
| per-request | 124 |
| per-paint | 102 |
| per-tick | 62 |
| unknown | 6 |

## The actionable subset

Of 2,606 functions, **228** run per-candle or per-tick — the path multiplied by ~525,000 calls in a full-year 35-bot replay. Of those, **30** have a better achievable bound, and **3** are super-linear.

Across the whole codebase, 387 functions carry a better achievable bound; most are cold and not worth touching. Frequency is what makes a bound matter.

### Hot path with a better achievable bound

| file:line | function | now | achievable |
|---|---|---|---|
| `src/core/event_bus.py:129` | `EventBus.emit` | O(P * S_p + H) | O(matching subs) by dict-indexing exact topics and scanning only wildcard patterns |
| `src/exchange/data_pool.py:375` | `MarketDataPool.get_or_fetch_ohlcv` | O(limit) | O(1) if a cached immutable window were shared instead of re-sliced |
| `src/exchange/market_pairs_scout.py:131` | `MarketPairsScout.pairs_for` | O(T) | O(m log m) with a base -> pairs index built during ingest_tickers |
| `src/gui/simulator_tab/fleet/sim_exchange.py:142` | `FleetSimExchange.step` | O(S log C + K) | O(S + open_orders) |
| `src/gui/simulator_tab/fleet/sim_exchange.py:169` | `FleetSimExchange.step_symbol` | O(K) | O(open orders for symbol) |
| `src/gui/simulator_tab/fleet/sim_exchange.py:410` | `FleetSimExchange._sweep_open_limit_orders` | O(K) | O(open orders) |
| `src/gui/simulator_tab/fleet/sim_exchange.py:459` | `FleetSimExchange.get_open_orders` | O(K) | O(open orders) |
| `src/gui/simulator_tab/nuclear_sim_exchange.py:136` | `NuclearSimExchange._resolve_tape` | O(t log t) | O(1) by testing membership against the underlying _wired set |
| `src/gui/simulator_tab/nuclear_sim_exchange.py:162` | `NuclearSimExchange.get_ticker` | O(t log t) | O(1) |
| `src/gui/stock_main_window.py:418` | `StockMainWindow._setup_ui._StockLogHandler._append_to_widget` | O(len(html)) | O(1) bounded memory via QTextEdit.document().setMaximumBlockCount(N) |
| `src/stocks/stock_accumulation_bot.py:176` | `StockAccumulationBot._check_pdt` | O(D) | O(1) with a deque pruned at the cutoff plus a running count |
| `src/stocks/stock_accumulation_bot.py:219` | `StockAccumulationBot.tick` | O(len(candles)) | O(1) amortized with incremental indicators over a rolling window |
| `src/trading/capital_reservation.py:464` | `CapitalReservationRegistry.effective_available` | O(R) | O(1) |
| `src/trading/extractor_bot.py:1438` | `ExtractorBot.tick` | O((P + W) * K) | O(P + W) network round-trips collapsed to 1 via batched ticker fetch |
| `src/trading/mr_inspector.py:111` | `MRInspector.scan` | O(len(candles)) | O(1) amortized |
| `src/trading/phantom_balance.py:322` | `TimeframeCoordinator.get_phantoms_for_parent` | O(P) | O(H) with a parent_bot_id -> phantom-list index |
| `src/trading/phantom_balance.py:370` | `TimeframeCoordinator.is_locked` | O(L) | O(1) amortized with locks bucketed by direction and lazy expiry |
| `src/trading/phantom_balance.py:409` | `TimeframeCoordinator._cleanup_expired` | O(L) | O(1) amortized with lazy expiry checked at read time |
| `src/trading/phantom_balance.py:422` | `TimeframeCoordinator.get_higher_tf_bias` | O(P) | O(H) with a parent-indexed registry |
| `src/trading/scrumming_bot.py:176` | `_extract_signal_detail` | O(S) | O(1) |
| `src/trading/ta_engine.py:156` | `_sma` | O(n*period) | O(n) |
| `src/trading/ta_engine.py:167` | `_stdev` | O(n*period) | O(n) |
| `src/trading/ta_engine.py:616` | `KaufmanERIndicator.compute` | O(n) | O(period) |
| `src/trading/ta_engine.py:702` | `BollingerBands.compute` | O(n*period) | O(n) |
| `src/trading/ta_engine.py:783` | `VortexIndicator.compute` | O(n) | O(period) |
| `src/trading/ta_engine.py:1152` | `StochasticRSI.compute` | O(n*stoch_period) | O(n) |
| `src/trading/ta_engine.py:2145` | `SlingshotIndicator.compute` | O(n*bb_period) | O(n) |
| `src/trading/ta_engine.py:2375` | `VotingEngine.compute_all` | O(n*period) | O(n) |
| `src/trading/ta_engine.py:2551` | `detect_bb_proximity` | O(n*bb_period) | O(n) |
| `src/trading/ta_engine.py:2661` | `detect_landing_strip_v2` | O(n*20) | O(n) |

### Super-linear on the hot path

| file:line | function | time | n | note |
|---|---|---|---|---|
| `src/trading/phantom_balance.py:208` | `PhantomBalanceBot._tick` | O(I*n) | n = len(candles), capped at 100 by limit=100; I = 12 indicators | compute_all runs 12 indicators, each a full pass over the window; candles_from_raw allocat |
| `src/trading/scrumming_bot.py:4500` | `ScrummingBot.tick` | O(C*I) | C = candles fetched (100), I = indicators (~8); also T tranches, L main lots | TA over 100 candles dominates; fold path adds O(T log T) tranche sort + O(L log L) lot sor |
| `src/trading/ta_signal_provider.py:212` | `TASignalProvider.evaluate` | O(k*C) | C = candles fetched (ohlcv_limit, default 100), k = indicators (12) | Awaited get_ohlcv + compute_all dominate; candles[-20:] copies the trend window on every c |

## Full data

All 2,606 rows: [`2026-08-04_function_complexity_inventory.csv`](2026-08-04_function_complexity_inventory.csv)

Columns: `file, line, qualname, time, space, n, freq, better, note`.
