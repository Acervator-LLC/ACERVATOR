# The Venue Seam — the complete list of ways Simulator, Paper and Live differ

Audit date: 2026-08-25. Repository version `3.26.0`, branch `current`, HEAD `a51756b`.
Clone under audit: a throwaway clone (`seam`) outside the repository.
Auditor role: read-only. No production file was changed. No fix is proposed.

---

## THE STANDARD THIS IS MEASURED AGAINST

Operator, verbatim:

> "Simulator, Paper, and Live Scrumming bots are and must be the same with the exception
> of their data source. Live is the only one with bidirectional API access since it trades
> on the exchange."

> "If the bot is not acting like a live trading bot with a different data feed, I do not
> want to hear about it, because any variation is a violation of the design spec."

Two differences are allowed. Where the market numbers come from, and whether an order
actually reaches the exchange. Every other difference is a defect.

---

# PART 1 — SUMMARY FOR THE OPERATOR

## The three headline numbers

| Question | Answer |
| --- | --- |
| **How many divergences exist?** | **50** |
| **How many are violations of the spec?** | **45** |
| **How many are legitimate?** | **5** |
| **Is the list complete?** | **No. It is complete for the surface named below and honestly incomplete elsewhere. Section 6.3 states exactly what is missing and why.** |

## Does Paper exist?

**No.** No Paper venue, no Paper backend, no Paper bot and no Paper source file exist.

What exists is: one concept document that says Paper is not built and is gated behind
Sim and Nuclear; four attributes in the main window that are set to `None` and never
reassigned; a "Paper Swarm" tab in the Bot Swarm view that displays rows and computes
nothing; and one import of a file that does not exist. No Paper mode value exists in
any enum. `BotMode` has exactly two members, `scrumming` and `extractor`.

The three-venue comparison this audit was asked for is, therefore, in fact a
**two-venue** comparison. Paper contributes zero rows to the table because Paper contributes zero code
to the tree. That is itself the first violation: a venue the design requires is absent.

## The five worst findings, in plain language

**1. The Simulator feeds its indicators three times as much history as Live does.**
Measured on the same tape, the same call: a Live bot receives **100 candles**, a
Simulator bot receives **300 candles**. This is not a small drift. The project's own test
file proves that 100 candles and 300 candles produce a *different vote* from the
indicator engine. The Simulator's buy and sell decisions are therefore computed from a
different input than Live's, on identical data. Cause: Live routes every candle read through a
shared cache (`MarketDataPool`) that trims the result to the requested size; the
Simulator has no such cache and receives the exchange's untrimmed page.

**2. The Simulator charges the wrong fee on every trade.** A market order is a *taker*
order and a real venue charges the taker rate. The Simulator's own market description
says taker is 1.2%. Measured: it charged **0.6%** — the maker rate — on a market buy.
Every simulated trade is therefore cheaper than the same trade on the exchange, which
flatters every strategy the Simulator is used to judge.

**3. The Simulator will fill an order of any size, instantly, at the candle close, with
no price impact.** Measured: a one-million-unit market buy filled 100% at exactly the
closing price. Zero slippage. The Simulator's order book is a single price level with a
depth of one billion units and a spread of zero. A real venue partially fills, moves the
price, and refuses what it cannot serve.

**4. The Simulator will accept a negative order size and run the ledger backwards.**
Measured: a market buy for **minus one unit** returned a *filled* order and moved the
wallet in the wrong direction. A real venue rejects this outright. A zero-size order is
likewise reported as filled. A guard higher up catches this before it
reaches the venue on the normal path — but the venue itself does not refuse it, and
Live's venue does.

**5. A resting order in the Simulator holds no money.** On the exchange, when you place
an order that waits, the money is held aside immediately and is no longer spendable.
Measured in the Simulator: place a resting order, and the spendable balance does not
change at all. The Simulator can therefore commit the same money twice. Related: send
the same order twice with the same anti-duplicate key and the Simulator fills it twice;
the exchange refuses the second.

## Why this keeps happening

Three structural causes, each verified rather than assumed.

**The contract describes shapes, not behaviour.** `src/exchange/base.py` is 282 lines. It
names methods and the types they return. It contains **one** statement about what happens
when something fails (`get_my_trades` raises `NotImplementedError` if unimplemented).
Nothing in it says what a venue does when funds are short, when a symbol is unknown, when
an order does not exist, or when a price is missing. Every one of those is a divergence
today, and none of them could have been caught by the contract, because the contract does
not mention them.

**The Simulator's venue is not covered by the contract at all.** `TabletBackend` — the
class the Simulator actually runs on — does **not** subclass `ExchangeInterface`. It
attaches underneath the live connector through `attach_backend`. Nothing type-checks it,
nothing enforces its shape, and the 14 members it must provide are listed only in a
docstring.

**Three Simulator venue classes exist, and two of them are dead.**
`FleetSimExchange` and `NuclearSimExchange` both *do* subclass `ExchangeInterface`, both
implement all 17 methods, and both are instantiated **nowhere** in the product. Every one
of their instantiations is in a test. Meanwhile the class the Simulator does run,
`TabletBackend`, subclasses nothing.

## And the tests that were supposed to catch this

Seven files carry "parity" in the name. **None of them compares Live behaviour to
Simulator behaviour on the same call.**

- Two of them test `FleetSimExchange` — **dead code**. One of those two asserts that the
  Simulator returns 300 candles, which is exactly the number that disagrees with Live.
  The test pins the defect open.
- One tests the Simulator's state save/load against itself. Live is not involved.
- One tests the Live connector against its own earlier version. The Simulator is not
  involved.
- One tests three code paths inside the bot. No venue is involved.
- One tests a measuring tool whose "Live" input is a hand-written dictionary.
- One is about PyInstaller build files and has nothing to do with venues.

Two further files not on that list (`test_sim_market_limits_agree`, `test_sim_ioc_limit`)
do compare venues — but they compare the **two dead ones** to each other.

---

# PART 2 — METHOD, AND THE CONTROL BESIDE EVERY MEASUREMENT

## 2.1 How the measurements were made

Every behavioural claim in Part 4 marked **[M]** was produced by executing code, not by
reading it. Four probe files were written into `tests/` and run with
`python -m pytest`, never as bare scripts, so that `tests/conftest.py` loaded and
redirected all log and state writes away from the operator's live tree.

| Probe | Tests | Exit code | Result |
| --- | --- | --- | --- |
| `test_zz_seam_probe.py` | 9 | 0 | 9 passed |
| `test_zz_seam_probe2.py` | 8 | 0 (after one fix) | 8 passed |
| `test_zz_seam_probe3.py` | 2 | 0 | 2 passed |
| `test_zz_seam_probe4.py` | 2 | 0 | 2 passed |

Exit codes were read on every run. None was 139 (SIGSEGV) or 127.

The probe files were removed from the clone after the runs and preserved at
a scratch directory (`seam_probes/`) outside the repository. Their raw JSON output is at
`seam_probe_out{,2,3,4}.json` beside it.

The live-tree guard reported `created 0` on every run. It reported `modified 3-4` and
declared itself DEGRADED, because a live `Acervator.exe` was running and writing its own
logs; the guard cannot attribute those to the suite. The files it named are all
`Acervator.exe`'s own outputs (`console/system.log`, `heartbeat.txt`,
`signals/session.jsonl`, `trade/diagnostics.log`). No probe writes to those paths.

## 2.2 The instrument's control

**Positive control** (`test_control_instrument_is_alive`, passed): the probe was required
to demonstrate, before any finding was accepted, that it could see both a real difference
and a real agreement between the two objects it compares. It asserted that the real ccxt
exchange has `fetch_status` and `TabletBackend` does not (difference visible), and that
both have `fetch_ohlcv` (agreement visible). A zero from this probe would otherwise have
been a claim about the probe.

**The live side is a real `ccxt` object, not a mock.** `ccxt 4.5.75`, `ccxt.coinbase()`,
constructed offline. For the members that are pure local code — `market`,
`amount_to_precision`, `price_to_precision`, `markets`, `precisionMode` — the real
Coinbase implementation was executed with markets set by hand, so those rows are genuine
live-code measurements, not readings of documentation.

**The shared layer was exercised with genuine ccxt exception classes.** For members that
require a network round-trip, a backend that raises the real `ccxt.InsufficientFunds`,
`ccxt.BadSymbol`, `ccxt.OrderNotFound`, `ccxt.NetworkError` and so on was injected, and
the connector's handling was measured (retry counts, re-raise behaviour). That measures
the shared code truthfully. It does **not** measure what Coinbase itself returns.

## 2.3 The one thing that was NOT measured, and must be said plainly

**No live network call was made.** No credentials were opened. `Acervator.exe` was never
touched. Therefore, wherever this report states what *Live* does on a network-dependent
call, the evidence is one of:

- **[M]** measured by execution (real ccxt local code, or the shared connector layer); or
- **[C]** ccxt's own published exception contract and normalisation code, read from the
  installed package; or
- **[S]** source reading of this repository.

Every row in Part 4 carries its evidence class. A row marked **[C]** is weaker than one
marked **[M]** and is labelled so. Nothing in this report claims a Coinbase response was
observed, because none was.

---

# PART 3 — THE SEAM, ENUMERATED FROM THE BOT

The interface is known to be incomplete, so the seam was enumerated from the consumers.

## 3.1 The two-layer shape of the seam

```
        ScrummingBot  (and BotContainer, VolumeGuard, PhantomBalance,
             |         BuySafety, SmartOrders, Reconciliation,
             |         TASignalProvider, ExtractorBot, ChartData, HistoryTab)
             v
    [ LAYER 1 ]  ExchangeInterface  — 17 members
             |
        CCXTConnector   <-- LIVE and SIM BOTH RUN THIS CLASS
             |
             |  self._ex  (property, ccxt_connector.py:968)
             v
    [ LAYER 2 ]  the raw ccxt surface — 14 members
             |
      +------+------+
      |             |
  ccxt.coinbase   TabletBackend        (attach_backend, ccxt_connector.py:999)
    (LIVE)          (SIM)
```

Since v3.24.84 the Simulator runs Live's connector. That was the correct move and it
closed a large class of divergence. What this audit finds is what is left **below** that
line (Layer 2), what sits **above** it (the wrappers), and what the bot does **differently
on purpose** when it knows it is a simulator.

## 3.2 Layer 1 — the `ExchangeInterface` surface (17 members)

Declared at `src/exchange/base.py:159-282`. Consumed by the bot as follows.

| Member | Called from | Line(s) |
| --- | --- | --- |
| `get_ticker` | `ScrummingBot._get_ticker` | `scrumming_bot.py:1798` |
| `get_ohlcv` | `ScrummingBot._get_ohlcv`, `_check_detonation_trigger` | `scrumming_bot.py:1820, 4236` |
| `get_orderbook` | `VolumeGuard` | `volume_guard.py` |
| `get_balance` | `ScrummingBot._get_balance`, `BuySafety` | `scrumming_bot.py:1831`; `buy_safety.py` |
| `get_balances` | `ScrummingBot` | `src/trading/scrumming/execution.py:977` |
| `place_order` | `BotContainer.guarded_place_order` | `bot_container.py:145` |
| `cancel_order` | `SmartOrders`, `Reconciliation` | `smart_orders.py`, `reconciliation.py` |
| `get_order` | `ScrummingBot` | `scrumming_bot.py:4636`; `src/trading/scrumming/execution.py:217` |
| `get_open_orders` | `ScrummingBot` | `scrumming_bot.py:4620`; `src/trading/scrumming/execution.py:1516, 1859`; `src/trading/scrumming/reconciliation.py:114` |
| `get_my_trades` | `ScrummingBot` (position health, window P/L) | `src/trading/scrumming/reconciliation.py:66, 174` |
| `get_markets` | `BotContainer._get_market_limits`, `ExtractorBot` | `bot_container.py:110` |
| `get_asset_logo_url` | GUI | — |
| `connect` / `disconnect` / `is_connected` | `LiveBotWindow`, `main_window` | — |
| `exchange_id` / `display_name` | throughout | — |

## 3.3 Layer 2 — the raw ccxt surface (14 members)

Named at `ccxt_connector.py:1003-1007` and confirmed by measurement to be exactly the set
reached through `self._ex`.

`fetch_ohlcv`, `fetch_ticker`, `fetch_tickers`, `fetch_balance`, `create_order`,
`cancel_order`, `fetch_order`, `fetch_open_orders`, `fetch_my_trades`, `fetch_order_book`,
`markets`, `market`, `amount_to_precision`, `price_to_precision`.

**[M] All 14 are present on `TabletBackend` and on `ccxt.coinbase()`.** Nothing is
missing. The divergences are behavioural, not structural — which is precisely why
shape-only comparison never found them.

## 3.4 Members that exist on one side only

**Sim-only, on `TabletBackend`** (14 members with no live counterpart): `step`,
`has_data`, `current_ts_ms`, `total_clock_ticks`, `ticks_elapsed`, `clock_window`,
`cursor_for`, `history`, `symbols`, `balances`, `credit`, `mark_opening_balances`,
`snapshot`, `on_trade`.

These are the replay control surface. The Simulator's controller drives them; no bot
touches them. That is by design and is documented at
`src/simulator/fleet/fleet_replay_controller.py:1004-1006`. **One of them is not benign: `on_trade` is a
callback the venue makes *into* the application, and Live has no such thing** (row J1).

**Live-only**: everything else on a ccxt exchange object — `fetch_status`,
`load_markets`, `fetch_currencies`, `withdraw`, WebSocket surfaces, and the whole
authentication path. None of it is reached by the bot, so none of it appears in the table.

## 3.5 The four backends

| Class | File | Subclasses `ExchangeInterface`? | Surface | Instantiated in `src/`? | Verdict |
| --- | --- | --- | --- | --- | --- |
| `CCXTConnector` | `src/exchange/ccxt_connector.py:239` | **Yes** | Layer 1 | yes (live and sim) | **ALIVE — both venues** |
| `TabletBackend` | `src/exchange/tablet_backend.py:103` | **No** | Layer 2 (raw ccxt) | yes, `src/simulator/fleet/fleet_replay_controller.py:1007` | **ALIVE — the Simulator's venue** |
| `FleetSimExchange` | `src/simulator/fleet/sim_exchange.py:70` | Yes | Layer 1 | **no — zero instantiations** | **DEAD** (replaced v3.24.84) |
| `NuclearSimExchange` | `src/simulator/nuclear_sim_exchange.py:91` | Yes | Layer 1 | one, at `src/simulator/nuclear_controller.py:278` — and `NuclearController` itself has no importer outside `tests/` | **DEAD** (two hops from anything running) |
| *Paper backend* | — | — | — | — | **DOES NOT EXIST** |

`FleetSimExchange`'s module is still loaded on the live Simulator path, but only for the
helper function `make_symbol_series_map` (`src/simulator/fleet/fleet_replay_controller.py:58`). The class
itself is used by 11 test files and by nothing else.

---

# PART 4 — THE DIVERGENCE TABLE

**Granularity note, stated so the count can be checked.** A "divergence" here is one
distinct observable behaviour that differs between venues at the seam. A different
granularity would give a different number; this one was chosen so that each row names one
thing a next unit could fix and verify independently. 50 rows follow.

**Legend.** `[M]` measured by execution. `[C]` ccxt's installed code or published
contract. `[S]` source reading. Verdict: **VIOLATION** or **LEGITIMATE**.

## GROUP A — Venue topology (5 rows, 5 violations)

| # | The fact | Live | Simulator | Paper | Ev | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | A Paper venue exists | yes (it *is* live) | n/a | **nothing exists** — no backend, no bot, no mode value, no source file | [S] | **VIOLATION** — a required venue is absent |
| A2 | The venue is covered by the declared contract | `CCXTConnector(ExchangeInterface)` | `TabletBackend` subclasses **nothing**; its required surface is a docstring at `ccxt_connector.py:1003` | — | [S] | **VIOLATION** |
| A3 | Number of Simulator venue implementations | 1 | **3** (`TabletBackend` alive, `FleetSimExchange` dead, `NuclearSimExchange` dead) | — | [S] | **VIOLATION** |
| A4 | Dead venues still carry the parity tests | — | 11 test files import `FleetSimExchange`; 5 import `NuclearSimExchange`; both are instantiated zero times in `src/` | — | [S] | **VIOLATION** |
| A5 | The contract states failure behaviour | `base.py` is 282 lines and contains **one** statement of failure behaviour (`base.py:271`, `get_my_trades` → `NotImplementedError`). Nothing states what a venue does on insufficient funds, unknown symbol, unknown order, or missing price | — | — | [S] | **VIOLATION** — this is the root cause of Group E |

## GROUP B — Connection lifecycle (5 rows, 3 violations, 2 legitimate)

| # | The fact | Live | Simulator | Ev | Verdict |
| --- | --- | --- | --- | --- | --- |
| B1 | `connect()` | runs preflight URL check, credential load, `load_markets`, circuit-breaker registration | **never called.** `attach_backend` sets `_connected = True` directly (`ccxt_connector.py:1013`). **[M]** `_ccxt` and `_ccxt_sync` are both `None` after attach; `is_connected` is `True` | [M] | **VIOLATION** |
| B2 | Credentials / passphrase / API auth | required, venue-specific | absent | [S] | **LEGITIMATE** — this is write access |
| B3 | `load_markets()` | populates real per-symbol metadata from the venue | **never runs.** Market metadata comes from a hardcoded template (see Group C) | [S] | **VIOLATION** |
| B4 | Request rate limiter | `_min_request_interval = 0.1` **[M]** | `0.0` **[M]** (set by `attach_backend`, `ccxt_connector.py:1027`) | [M] | **LEGITIMATE** — no network, nothing to limit; documented as changing no computed value |
| B5 | Trade-historian background thread | spawned on every successful `sync_connect` | never spawned | [S] | **VIOLATION** |

## GROUP C — Market metadata (6 rows, 6 violations)

The Simulator's controller builds `TabletBackend` **without** a `markets` argument
(`src/simulator/fleet/fleet_replay_controller.py:1007-1013`). Every symbol therefore receives the single
hardcoded template at `tablet_backend.py:201-218`.

| # | The fact | Live | Simulator | Ev | Verdict |
| --- | --- | --- | --- | --- | --- |
| C1 | What `precision` *means* | **[M]** `ccxt.coinbase().precisionMode == 4 == ccxt.TICK_SIZE`. Same for `binance` and `kraken`. `precision.amount` is a **tick size** (e.g. `1e-08`) | `precision: {price: 8, amount: 8}` — **decimal places**. **[M]** Consequence: real ccxt raises `InvalidOrder("amount of CHIP/USD must be greater than minimum amount precision of 8")` on the sim's own market dict, because it reads `8` as a tick of eight whole units | [M] | **VIOLATION** |
| C2 | `limits.amount.min` | real per-symbol minimum | **`0.0` for every symbol.** **[M]** the pre-flight minimum-size gate can never fire in the Simulator | [M] | **VIOLATION** |
| C3 | `limits.cost.min` | real per-symbol minimum | **`1.0` hardcoded for every symbol** | [S] | **VIOLATION** |
| C4 | `maker` / `taker` in the market dict | real, per-symbol, fee-tier dependent | `0.006` / `0.012` hardcoded for every symbol — and these **disagree with the fee the same class actually charges** (per-symbol from `bot_state`, default `0.006`). The venue's advertised fee and its charged fee are different numbers | [M] | **VIOLATION** |
| C5 | Market `id` | the venue's own id | mechanical `symbol.replace("/","-")` | [S] | **VIOLATION** (low impact) |
| C6 | `AssetInfo.amount_precision` | **[M]** `int(1e-08) == 0`, then `int(... or 8)` at `ccxt_connector.py:1339` rescues it to `8` | `8` | [M] | **VIOLATION (latent)** — the two agree at `8` **by accident of an `or 8` fallback**, not by design. Remove the fallback and they diverge |

## GROUP D — Market data reads (6 rows, 5 violations, 1 legitimate)

| # | The fact | Live | Simulator | Ev | Verdict |
| --- | --- | --- | --- | --- | --- |
| D1 | Bid/ask spread on `get_ticker` | a real spread | **[M]** `bid == ask == last == 105.0`. Spread is exactly zero | [M] | **VIOLATION** |
| D2 | Order book | 20 levels of real depth | **[M]** one level, price = last close, size `1e9` on both sides | [M] | **VIOLATION** |
| D3 | Unknown symbol on `get_ticker` / `get_ohlcv` / `get_orderbook` | `ccxt.BadSymbol` **[M]** (`"coinbase does not have market symbol NOPE/USD"`) | **[M]** `ValueError("no candles for 'NOPE/USD'")` | [M] | **VIOLATION** — different exception type; a handler written for one will not catch the other |
| D4 | Timeframe with no series | the venue serves any supported timeframe | **[M]** `ValueError("no 1h series for 'CHIP/USD'...")`. A Simulator fleet whose bots use a non-5m TA timeframe cannot run at all unless `tf_rows` were supplied | [M] | **VIOLATION** |
| D5 | `TabletNotStarted` | no analogue | a Simulator-only exception class (`tablet_backend.py:93`), raised on read before a tape opens, and caught nowhere in the connector or the bot | [S] | **VIOLATION** |
| D6 | `fetch_tickers` on a not-yet-started symbol | returns every listed symbol | silently omits the symbol | [S] | **LEGITIMATE** — a symbol with no data cannot be priced; this is the data source |

## GROUP E — Order writes (11 rows, 11 violations)

This is the group #111A lived in, and it is still the largest.

| # | The fact | Live | Simulator | Ev | Verdict |
| --- | --- | --- | --- | --- | --- |
| E1 | **Negative order amount** | `InvalidOrder` | **[M]** returns `Order(amount=-1.0, filled=-1.0, status=FILLED, fee=-0.63)` and moves the ledger **backwards** | [M]/[C] | **VIOLATION — most severe row in the table** |
| E2 | Zero order amount | `InvalidOrder` | **[M]** returns `Order(amount=0.0, filled=0.0, status=FILLED)` | [M]/[C] | **VIOLATION** |
| E3 | NaN order amount | `InvalidOrder` | **[M]** `ValueError("cannot convert float NaN to integer")` — raised from precision arithmetic, not from a refusal | [M]/[C] | **VIOLATION** |
| E4 | LIMIT order with no price | `ArgumentsRequired` / `InvalidOrder` | **[M]** `TypeError("float() argument must be a string or a real number, not 'NoneType'")` | [M]/[C] | **VIOLATION** |
| E5 | IOC semantics | connector sends `type=limit, timeInForce=IOC` (`ccxt_connector.py:1312-1314`); the venue fills what is available and cancels the rest | **[M]** treated as an ordinary marketable limit. Fills 100% at the limit price. No partial fill, no cancel-remainder | [M] | **VIOLATION** |
| E6 | Partial fills and slippage | routine | **[M]** a 1,000,000-unit market buy filled **100%** at exactly the candle close. Slippage `0.0`. The Simulator has never produced a partial fill | [M] | **VIOLATION** |
| E7 | Duplicate `client_order_id` | the venue refuses the duplicate (Coinbase 409, Binance −2010) — the entire point of `src/exchange/idempotency.py` | **[M]** same coid twice → two distinct order ids, **two fills, 2.0 CHIP booked** | [M]/[C] | **VIOLATION** |
| E8 | Funds held by a resting order | held at placement; visible as `used`, removed from `free` | **[M]** resting BUY for 5 units at 50: `free` **unchanged** at 1000.0, `used` **0.0**, `_reserved` map **empty**. `used` is never written anywhere in `TabletBackend` | [M] | **VIOLATION** — the Simulator can commit the same money twice |
| E9 | A resting order that cannot fund when the sweep crosses it | unreachable in Live (funds were held at placement) | **[M]** backend marks it `rejected`; a later `get_order` returns `Order(status=FAILED, filled=0.0, average=0.0)` — a state Live cannot produce. Documented and accepted at `tablet_backend.py:595-599` | [M] | **VIOLATION** |
| E10 | Unknown order on `cancel_order` / `get_order` | `ccxt.OrderNotFound` | **[M]** `ValueError("no such order 'nope'")` | [M]/[C] | **VIOLATION** |
| E11 | `Order.raw` / `info` content | the venue's response | `{"sim": True, "params": {...}}` | [M] | **VIOLATION** (low impact; any consumer reading `raw` sees different content) |

**AGREEMENT worth recording (not counted as a divergence):** a marketable order that the
wallet cannot fund raises `ccxt.InsufficientFunds` on **both** sides. **[M]** verified,
with the shortfall arithmetic in the message. This is issue #111A's fix and it holds.

## GROUP F — Fees (2 rows, 2 violations)

| # | The fact | Live | Simulator | Ev | Verdict |
| --- | --- | --- | --- | --- | --- |
| F1 | Fee side on a market (taker) order | taker rate | **[M]** charged `0.63` on `105.0` notional = **0.6%**, the *maker* rate, while its own market dict declares taker `1.2%`. `TabletBackend._fee_rate` returns one number regardless of side (`tablet_backend.py:469-470`) | [M] | **VIOLATION** — every simulated trade is cheaper than the same live trade |
| F2 | Fee structure | maker/taker split, volume tiers, per-symbol | one flat rate per symbol from `bot_state`, default `0.006` | [S] | **VIOLATION** |

## GROUP G — Error handling and retry (2 rows, 2 violations)

| # | The fact | Live | Simulator | Ev | Verdict |
| --- | --- | --- | --- | --- | --- |
| G1 | Exception vocabulary | `ccxt` exception hierarchy (`BaseError` → `ExchangeError` → `BadSymbol`, `InvalidOrder`, `OrderNotFound`, `InsufficientFunds`; `NetworkError` → `RequestTimeout`, `RateLimitExceeded`) | Python builtins: `ValueError`, `TypeError`, plus one Simulator-only class `TabletNotStarted`. Only `InsufficientFunds` is shared | [M] | **VIOLATION** — umbrella of D3, D4, E3, E4, E10 |
| G2 | Retry behaviour | **[M]** `_with_retry` retries on exception *names* containing ratelimit/timeout/network/request: `NetworkError`, `RequestTimeout`, `RateLimitExceeded` → **3 backend calls**; all others → 1 | **[M]** every Simulator failure name misses that keyword filter, so every Simulator failure gets exactly **1** attempt. The retry and backoff path is never exercised in the Simulator | [M] | **VIOLATION by omission** — a whole live code path is untested by every replay ever run |

## GROUP H — What wraps the connector (5 rows, 3 violations, 1 legitimate, 1 latent)

| # | The fact | Live | Simulator | Ev | Verdict |
| --- | --- | --- | --- | --- | --- |
| H1 | `MarketDataPool` | wired: `main.py:628-629` → `BotManager.set_data_pool` (`src/trading/bot_container.py:767-773`) → every bot, plus a late-join site for a bot added after wiring (`src/trading/container/registry.py:115-118`) | **never wired.** `src/simulator/fleet/fleet_replay_controller.py:358-362` states so explicitly | [M] | **VIOLATION — the largest measured divergence.** See H1-detail below |
| H2 | Balance freshness | pool cache, 10 s TTL (`data_pool.py:84-86`) | read fresh from the venue on every call. **[M]** 5 reads → 5 backend calls in sim, 1 in live | [M] | **VIOLATION** |
| H3 | `VolumeGuard` | constructed on the live manager only (`main.py:623-624`) | never constructed | [M] | **LATENT, not a divergence today** — `VolumeGuard.enabled` hard-returns `False` (`src/trading/volume_guard.py:188-196`, MEM-259), so both venues take the direct path. It becomes a divergence the moment it is re-enabled, and the guarded path builds a *synthetic* `Order` (`id="vg_..."`) and raises a bare `Exception` instead of `InsufficientFunds` (`src/trading/bot_container.py:259-277`) |
| H4 | Wallet seeding | a real account balance | `Σ target_balance` with **no fee headroom** (`src/simulator/fleet/fleet_replay_controller.py:923-934`). A lot-less bot must buy its opening position at `target_balance × (1 + fee)`, so the last bot in the fleet is always short — issue **#111B, unfixed** | [S] | **VIOLATION, open** |
| H5 | Capital-reservation registry | process-wide singleton persisted to `~/.acervator/reservation_state.json` | injected private non-persisting instance (`scrumming_bot.py:509`) | [S] | **LEGITIMATE** — persisting to the operator's live state file is a real-world write |

**H1-detail — the measurement.** Probe 4 built one `TabletBackend` with 400 candles,
attached it to a real `CCXTConnector`, and drove the **same** `ScrummingBot._get_ohlcv`
and `_get_balance` methods five times, once with a real `MarketDataPool` wired (Live's
configuration) and once without (the Simulator's configuration):

| Configuration | Candles the bot received | Backend `fetch_ohlcv` calls | Backend `fetch_balance` calls |
| --- | --- | --- | --- |
| **LIVE** (pool wired) | **100** | 1 | 1 |
| **SIM** (no pool) | **300** | 5 | 5 |

The bot's TA path asks for `limit=100` (`src/trading/scrumming/tick_phases.py:787` and
`src/trading/scrumming_bot.py:2826-2829`). The
pool returns `entry.candles[-limit:]` — exactly 100. The direct connector call returns
300, because of the documented `since`-slot defect. **Live's indicators therefore run on
100 candles and the Simulator's run on 300, from the same tape, on the same call.**

`tests/test_sim_live_ohlcv_parity.py:139-151` independently proves that 100 and 300
produce a different `net_score` from `VotingEngine`. The gate decisions differ.

## GROUP I — The bot's own simulator branches (7 rows, 6 violations, 1 legitimate)

`ScrummingBot.__init__` takes `sim_mode: bool` (`src/trading/scrumming_bot.py:323`). The bot is
therefore **not** the same code in both venues.

| # | The fact | Live | Simulator | Ev | Verdict |
| --- | --- | --- | --- | --- | --- |
| I1 | The event bus | the process-wide `EventBus` singleton | a **private** `EventBus` (`src/trading/scrumming_bot.py:341-357`). Every bus consumer — `LogManager`, `trade.log`, `gate.log`, the sound engine, the GUI — is disconnected in the Simulator. Construction **fails closed** if the private bus cannot be made | [S] | **VIOLATION** (the isolation is necessary; the *mechanism* means the Simulator exercises none of the emit path) |
| I2 | Capital reservation resolution | resolves the process-wide registry | `_crr()` returns **`None`** when no registry was injected (`src/trading/scrumming/capital_reservation_mixin.py:35-43`). Reservation is unavailable rather than simulated | [S] | **VIOLATION** |
| I3 | First reservation's drift assertion | holdings are passed and checked | `_total_holdings = None` on the first reserve only (`src/trading/scrumming/capital_reservation_mixin.py:113-114`), skipping the assertion | [S] | **VIOLATION** |
| I4 | `PhantomBalance` cadence | sleeps `min(candle_seconds, 60)` wall-clock | awaits the stop event and breaks (`src/trading/phantom_balance.py:275-277`); driven by `tick_for_cursor` instead | [S] | **VIOLATION** |
| I5 | `sim_run_log` | not written | written, gated on `_sim_mode` (`src/trading/sim_run_log.py:554`) | [S] | **LEGITIMATE** — an extra Simulator artefact, not a change to bot behaviour |
| I6 | `nuclear_verification` | skips | gated on `_sim_mode` (`src/trading/nuclear_verification.py:222`) | [S] | **VIOLATION** (low) |
| I7 | `indicator_panel` | live branch | `_sim_mode` branches at `src/gui/indicator_panel.py:923, 1461` | [S] | **VIOLATION** (low, GUI) |

## GROUP J — Venue-to-application callbacks (2 rows, 2 violations)

| # | The fact | Live | Simulator | Ev | Verdict |
| --- | --- | --- | --- | --- | --- |
| J1 | `on_trade` | **no such thing.** Live's fill accounting comes from the event bus | the venue calls **into** the application on every fill (`tablet_backend.py:303, 643`). Not declared in `ExchangeInterface`. `scrumming_bot.py:535` states the Simulator counts fills through this callback and *not* the bus | [M] | **VIOLATION** — an entire feedback channel exists on one side only |
| J2 | The callback's argument shape | — | `TabletBackend` passes a **dict** (ms timestamps, `side` a lowercase string). `FleetSimExchange` passes a **`Trade` object** (seconds, `side` an enum). Both shapes are still handled at `src/simulator/fleet/fleet_replay_controller.py:1640-1654` | [M] | **VIOLATION** — this is issue #110's exact home, still two-shaped |

## 4.1 The tally

| Group | Rows | Violations | Legitimate |
| --- | --- | --- | --- |
| A — Venue topology | 5 | 5 | 0 |
| B — Connection lifecycle | 5 | 3 | 2 |
| C — Market metadata | 6 | 6 | 0 |
| D — Market data reads | 6 | 5 | 1 |
| E — Order writes | 11 | 11 | 0 |
| F — Fees | 2 | 2 | 0 |
| G — Errors and retry | 2 | 2 | 0 |
| H — Wrappers | 5 | 3 | 1 (+1 latent, not counted) |
| I — Bot sim branches | 7 | 6 | 1 |
| J — Callbacks | 2 | 2 | 0 |
| **TOTAL** | **51 listed** | **45** | **5** |

**50 divergences** (H3 is listed but is **not** a divergence today — it is a latent one,
recorded so it is not rediscovered by accident). **45 violations. 5 legitimate.**

Legitimate, in full, so they can be checked: **B2** credentials, **B4** rate limiter,
**D6** unpriceable symbol omitted, **H5** reservation-state isolation, **I5** the
Simulator's own run log.

Agreements recorded but not counted: `InsufficientFunds` on a marketable order (E-note);
all 14 raw members present on both sides (3.3); the `since`-slot OHLCV quirk faithfully
reproduced (`tablet_backend.py:29-44`, verified in probe 1).

---

# PART 5 — THE SEVEN PARITY FILES, AND WHAT FALLS BETWEEN THEM

## 5.1 What each file actually covers

| File | What it really compares | Backends touched | Failure paths? | Verdict |
| --- | --- | --- | --- | --- |
| `test_exchange_dataclass_parity.py` (161 ln, 4 tests) | **AST text** of `ccxt_connector.py` against **`sim_exchange.py`**. Asserts the set of dataclass field *names* live populates is a subset of the set sim populates | **none instantiated** — both read as text. `TabletBackend` not mentioned | **no** — nothing is executed | Targets **DEAD** code. Structural only |
| `test_sim_live_ohlcv_parity.py` (152 ln, 8 tests) | `FleetSimExchange.get_ohlcv` against **one integer constant**, `EFFECTIVE_OHLCV_PAGE_SIZE == 300`. Asserts `len(rows) == 300` | **`FleetSimExchange` only.** `CCXTConnector.get_ohlcv` is never called | **no** — success only | Targets **DEAD** code, and **asserts the number that disagrees with Live** (H1) |
| `test_state_parity_on_import.py` (225 ln, 11 tests) | A `ScrummingBot` state export → import → export round trip. Sim to sim | `FleetSimExchange` as an inert carrier | no (its two "failure" tests are instrument controls) | Live is **entirely absent** |
| `test_unitc_ccxt_connector_behaviour_parity.py` (663 ln, 20 tests) | `CCXTConnector` **before vs after a refactor**. Preflight, passphrase, retry budgets, circuit breaker, queue cap | `CCXTConnector` + two hand-written doubles | **yes, heavily** — the only file that does | The **Simulator is never mentioned** |
| `test_scrum_fold_pct_mirrored_on_every_path.py` (949 ln, 17 tests) | Three code paths **inside** `ScrummingBot` agreeing with each other | **no exchange at all** | no | Not about venues |
| `test_parity_harness.py` (448 ln, 20 tests) + `parity_harness.py` | The trade-tape **comparison tool**. `TabletBackend` is driven as a tape | `TabletBackend` (tape only); the "live" side is always a hand-built dict | no venue failures; no `pytest.raises` in the file | A measuring instrument, not a parity check. Its "Live" input is written by hand |
| `test_specs_parity.py` (409 ln, 39 tests) | PyInstaller build specs | none | one (`ValueError` on unknown platform) | **Confirmed irrelevant** to venues |

Two further files not on the list of seven **do** compare venues — and compare the two
**dead** ones to each other: `test_sim_market_limits_agree.py` (Fleet vs Nuclear
`min_cost`) and `test_sim_ioc_limit.py` (Fleet and Nuclear IOC behaviour).

The files that **do** exercise `TabletBackend` behaviourally are not called "parity" and
were not on the list: `test_tablet_backend_is_the_live_path.py` (12 tests: `_ex`
resolution, arity of every call site, tape causality, balance seeding) and
`test_sim_bot_agrees_with_its_venue.py` (7 tests: `InsufficientFunds` raised, book agrees
with wallet, fleet-size table). These are the strongest venue pins in the suite.

## 5.2 The gaps between them

**GAP 1 — Nothing compares Live and Sim on the same call.** Not one of the seven executes
both a live-shaped venue and a sim venue with identical arguments and compares the two
answers. The nearest approach, `test_sim_live_ohlcv_parity`, replaces the live side with
an integer. **This gap contains rows C1-C6, D1-D6, E1-E11, F1-F2, G1-G2.**

**GAP 2 — Two files test a class the product does not run.** `test_exchange_dataclass_parity`
and `test_sim_live_ohlcv_parity` both target `FleetSimExchange`. Both are green. Both
would stay green if `TabletBackend` were deleted. **This gap contains every row in the
table, because it means the alive venue has no parity file at all.**

**GAP 3 — The one file rich in failure-path coverage has no sim side.**
`test_unitc_ccxt_connector_behaviour_parity` is the only file that systematically drives
refusals, and it drives them on the Live connector alone. **This gap contains D3, D4, E1-E11, G1, G2.**

**GAP 4 — Nothing tests above the connector.** No parity file constructs a
`MarketDataPool`, so nothing sees that the two venues hand the indicator engine different
candle counts. **This gap contains H1, H2.** Worse: `test_sim_ta_input_fidelity.py`
*names* the absence of the pool in sim and calls the hazard "latent, not active",
converting the divergence into a pinned invariant.

**GAP 5 — Nothing tests the bot's own `sim_mode` branches for behavioural equivalence.**
`sim_mode` exists in 5 files; no parity file asserts that a bot with `sim_mode=True`
behaves as one with `sim_mode=False`. **This gap contains I1-I7.**

**GAP 6 — Nothing asserts the interface is complete.** No test asserts that the members
`ScrummingBot` calls are the members `ExchangeInterface` declares, nor that
`TabletBackend` satisfies a specification. **This gap contains A2, A5, J1.**

**GAP 7 — Nothing asserts a venue's exception vocabulary.** No test compares the exception
*type* raised by a sim venue against the one ccxt raises for the same condition.
**This gap contains D3, D4, E3, E4, E10, G1.**

## 5.3 The five known defects, mapped to the gaps — the validation of this analysis

| Defect | Seam item | Layer | Path | Gap it lived in |
| --- | --- | --- | --- | --- |
| **#31** `fetch_balance` omitted a currency; no sim bot initialised for nine months | `fetch_balance` → `Balance.absent` → `ScrummingBot.tick` handshake | Layer 2 (backend response content) | **success** | **GAP 1** — a live/sim comparison of the same `fetch_balance` call would have shown one side listing the base currency and the other not |
| **#109** nothing asserted a replay fires a trade | `ReplayProgress.trades_fired` | test suite | neither — a vacuous negative assertion | **GAP 2** — the suite's positive assertions pointed at a class the product had stopped running |
| **#110** `on_trade` passed a dict where its predecessor passed an object; five more consumers found by sweep | the `on_trade` callback the venue makes into the app | venue → application callback | **success** (`getattr` on a dict never raises) | **GAP 6** — `on_trade` is not declared in `ExchangeInterface`, so nothing specified its argument shape |
| **#111A** `create_order` returned `"rejected"` where live raises `InsufficientFunds` | `create_order` refusal shape | Layer 2 | **FAILURE** | **GAP 3 and GAP 7** — the only failure-path file has no sim side, and nothing compares exception vocabularies |
| **#111B** fleet-size coupling on the lot-less path (wallet = Σ target_balance, no fee headroom) | wallet magnitude at construction | the Simulator harness, above both layers | success before #111A, failure after | **GAP 4** — nothing tests above the connector, and the wallet is seeded above it |

**All five map onto gaps this analysis identified independently.** Six of the seven gaps
(1, 2, 3, 4, 6, 7) are each occupied by at least one known defect. That is the
ground-truth check on the gap analysis, and it passes.

It also predicts the next one. **GAP 5 has no known defect in it yet** and contains seven
live rows (I1-I7). **GAP 4 contains the largest unfixed measured divergence (H1).**

---

# PART 6 — COMPLETENESS

## 6.1 What this list covers, in full

- All **14** members of the raw ccxt surface named by `attach_backend`, checked for
  presence, signature, coroutine-ness, success behaviour and failure behaviour on both
  sides.
- All **17** members of `ExchangeInterface`, driven end-to-end through a real
  `CCXTConnector` with `TabletBackend` attached.
- **15** distinct failure conditions driven through the seam and recorded.
- The full lifecycle: construction, `attach_backend`, connection state, rate limiting.
- Everything wrapped around the connector that a bot's read passes through:
  `MarketDataPool`, `VolumeGuard`, `guarded_place_order`, the idempotency layer, the
  capital registry, wallet seeding.
- Every `sim_mode` branch in `src/` outside `src/gui/simulator_tab/` and
  `src/simulator/`.
- All four backend classes, with liveness determined by instantiation-site census.
- The complete absence of Paper, established by filename search, full-tree grep with
  every hit classified, venue-discriminator search, and the concept document's own status.

## 6.2 Confidence classes

| Class | Rows | Meaning |
| --- | --- | --- |
| **[M] measured** | 29 | The Simulator side was executed; and the Live side was either executed as real ccxt local code, or driven through the shared connector layer with genuine ccxt exception classes |
| **[S] source** | 22 | Read from this repository's source. Cited by file and line |
| of which **[C]** | 7 | Rows whose **Live** answer additionally rests on ccxt's installed contract rather than on an observed Coinbase response: D3, E1, E2, E3, E4, E7, E10 |

29 + 22 = 51 listed rows.

## 6.3 What this list does NOT cover — stated so the next unit does not believe it is done

1. **No live network call was made.** Where a row says "Live raises `InvalidOrder`", the
   evidence is ccxt's contract, not a Coinbase response. Rows E1, E2, E3, E4, E7, E10 and
   D3 carry this caveat. **To close it: capture one real Coinbase response per condition
   on a throwaway account and pin them.** This is the single largest weakness in the
   report and it cannot be removed from an offline audit.

2. **`ExtractorBot`'s seam is not enumerated.** It calls `get_ticker`, `get_markets` and
   `get_balance` and is recorded as not release-ready. Its rows are absent.

3. **GUI consumers are not enumerated** beyond noting they exist: `chart_data`,
   `history_tab`, `market_inspector_fetcher`, `live_bot_window`, `main_window`. Whether a
   Simulator-attached connector reaches them was not tested.

4. **`src/stocks/` is out of scope** — a separate `BrokerBase` hierarchy, never imported,
   with its own unrelated meaning of the word "paper".

5. **Timing, ordering and concurrency were not compared.** The Simulator's replay clock
   versus Live's wall clock is the legitimate data-source difference, but its second-order
   effects — fill ordering within one candle, all fills in a candle sharing one timestamp,
   the 10 s balance TTL against a 300 s candle — were not systematically enumerated. Row
   H2 is one instance; there are probably more.

6. **The two dead venues' internal divergences were catalogued but not counted.** They
   differ from each other (`min_cost` 1.00 vs 0.01) and from `TabletBackend`. Since
   neither runs, their rows would inflate the count without describing the product. The
   table describes `TabletBackend` versus Live. **If either dead class is ever revived,
   this table does not describe it.**

7. **Granularity is a choice.** 50 rows at this granularity. A coarser reading merges
   E1-E4 into "argument validation" and G1 into one row and reports ~30. A finer reading
   splits C4 and F1 into per-field rows and reports ~70. The number is defensible at the
   stated granularity and is not defensible as an absolute.

## 6.4 The answer to the question asked

**How many divergences exist?** 50 at the stated granularity, across ten groups.

**How many are violations?** 45. Five are legitimate: credentials, the rate limiter, the
omission of an unpriceable symbol, reservation-state isolation, and the Simulator's own
run log. One further row (H3, `VolumeGuard`) is latent rather than live and is excluded
from the count.

**Is the list complete?** For the surface in 6.1 — the raw ccxt surface, the
`ExchangeInterface` surface, the wrappers, the `sim_mode` branches and the backend census
— **yes, and it is the first time that surface has been enumerated in one place.** For
the seven exclusions in 6.3 — **no, and each is named.** The largest remaining weakness
is that no live venue response was ever observed; seven Live answers rest on ccxt's
contract rather than on a measurement.

---

# APPENDIX A — Probe sources and raw output

Probe files, removed from the clone after use and preserved at
a scratch directory (`seam_probes/`) outside the repository:

- `test_zz_seam_probe.py` — surface presence and signatures; local-member behaviour
  against real ccxt; sim success paths; 15 sim failure paths; resting-order refusal;
  live exception classes through the shared layer; `on_trade` shape. Includes the
  positive control.
- `test_zz_seam_probe2.py` — fee side; fund reservation; idempotency; depth and partial
  fill; precision mode; `get_markets` precision reading; connection state after attach.
- `test_zz_seam_probe3.py` — the pre-flight gate under both market-metadata shapes.
- `test_zz_seam_probe4.py` — the `MarketDataPool` seam (H1).

Raw JSON output: `seam_probe_out.json`,
`seam_probe_out2.json`, `seam_probe_out3.json`, `seam_probe_out4.json`.

All four were run with `python -m pytest <file> -p no:randomly -q -s`, so
`tests/conftest.py` loaded and redirected every log and state write away from
`~/.acervator/` and `~/.acervator_logs/`. Exit codes: 0, 0, 0, 0.

# APPENDIX B — Key file and line references

| Subject | Location |
| --- | --- |
| The contract (shape only) | `src/exchange/base.py:159-282`; its one failure statement at `:271` |
| Live connector | `src/exchange/ccxt_connector.py:239` |
| The injection point | `src/exchange/ccxt_connector.py:968` (`_ex`), `:999` (`attach_backend`), `:1013` (marks connected), `:1027` (rate limiter to 0) |
| Retry decorator | `src/exchange/ccxt_connector.py:207-233` |
| `get_ohlcv` `since`-slot defect | `src/exchange/ccxt_connector.py:1095-1152` |
| `get_markets` precision read | `src/exchange/ccxt_connector.py:1339` |
| Simulator's venue | `src/exchange/tablet_backend.py:103` |
| Hardcoded market template | `src/exchange/tablet_backend.py:201-218` |
| Fee rate (one number, no side) | `src/exchange/tablet_backend.py:469-470` |
| `create_order` and the #111A fix | `src/exchange/tablet_backend.py:473-556` |
| Sweep leaves `rejected` | `src/exchange/tablet_backend.py:586-609, 654-675` |
| `on_trade` invocation | `src/exchange/tablet_backend.py:303, 640-651` |
| Simulator wiring | `src/simulator/fleet/fleet_replay_controller.py:1007-1026` |
| Wallet seeding (#111B) | `src/simulator/fleet/fleet_replay_controller.py:923-934, 1240-1256` |
| Pool absent in sim, stated | `src/simulator/fleet/fleet_replay_controller.py:358-362` |
| Pool wired in live | `main.py:628-629`; `src/trading/bot_container.py:767-773`; late-join site `src/trading/container/registry.py:115-118` |
| Pool trims to `limit` | `src/exchange/data_pool.py` (`get_or_fetch_ohlcv`, `entry.candles[-limit:]`) |
| `guarded_place_order` | `src/trading/bot_container.py:145-303` |
| `_get_market_limits` | `src/trading/bot_container.py:110-141` |
| VolumeGuard force-disabled | `src/trading/volume_guard.py:188-196` |
| `sim_mode` branches | `src/trading/scrumming_bot.py:323, 339, 341-357`; `src/trading/scrumming/capital_reservation_mixin.py:35-43, 113-114`; `src/trading/phantom_balance.py:275`; `src/trading/sim_run_log.py:554`; `src/trading/nuclear_verification.py:222`; `src/gui/indicator_panel.py:923, 1461` |
| Bot TA asks for 100 candles | `src/trading/scrumming/tick_phases.py:787`; `src/trading/scrumming_bot.py:2826-2829` |
| Dead venue 1 | `src/simulator/fleet/sim_exchange.py:70` |
| Dead venue 2 | `src/simulator/nuclear_sim_exchange.py:91` |
| Paper: the concept doc | **`docs/engineering-notes/2026-08-05_paper_trader_concept_spec.md` no longer exists anywhere in the tree.** It moved to that path from `docs/audits/` in commit `fc0d778`, then was removed in a later merge (`d1bf755`, cleanup/remove-non-documentation-from-docs) that did not carry across this branch's copy. No replacement doc states Paper's status. |
| Paper: permanently-None attributes | `src/gui/main_tabs/retired_tabs.py:11-16` |
| Paper: import of a file that does not exist | `src/gui/stock_main_window.py:396` |
