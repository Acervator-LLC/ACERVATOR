# Re-validation of issues #107, #111 and #117-#127

**Date:** 2026-08-26
**Auditor role:** re-verify only. No production code was written. No file in the
repository was changed except this report.
**Clone:** a throwaway clone (`reval`) outside the repository
**Tree measured at:** `2c1bef3` — *R5: the tick pump is pluggable and Qt-free*
**Original audit measured at:** `a51756b`. 156 commits separate the two.
**Live application:** running throughout. It was never started, stopped, attached
to or queried. `~/.acervator/bot_state.json` was read, never written.

---

## 1. The answer in numbers

63 separate claims were re-checked.

| Verdict | Count |
| --- | ---: |
| **STILL TRUE** | **58** |
| **FIXED** | **3** |
| **NEVER TRUE** | **1** |
| **CANNOT VERIFY** | **1** |

Broken down:

| Claim set | Still true | Fixed | Never true | Cannot verify | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| The 51 rows in #118-#127 | 49 | 1 | 1 | 0 | 51 |
| The 7 structural claims in #117 | 6 | 0 | 0 | 1 | 7 |
| #111 (three claims) | 1 | 2 | 0 | 0 | 3 |
| #107 (two claims) | 2 | 0 | 0 | 0 | 2 |

Of the 51 rows, 45 were called violations. Of those 45: **43 still true, 1 fixed,
1 never true as written.** The other 6 rows were called legitimate or latent. All
6 of those calls hold.

**Nothing here was hallucinated.** The audit's file names, class names, method
names and numbers reproduce. Section 5 names what did not: one measurement error,
one claim I could not settle, and one place where the audit understated its own
finding.

---

## 2. Operator table — plain language

One line per claim group, in words you can act on. "Practice venue" means the
fake exchange the Simulator trades against.

| Issue | What it says, plainly | Verdict | Survives? |
| --- | --- | --- | --- |
| **#117** | The Simulator and Live are two different exchanges, not one exchange with two data feeds. 45 differences counted. | STILL TRUE (43 of 45) | Yes — as ONE statement, not ten issues |
| **#118** | The practice venue accepts orders a real exchange refuses. An order for MINUS one coin filled, and the wallet went UP $100.60 and DOWN to minus one coin. | STILL TRUE (11 of 11) | Yes |
| **#119** | The same bot, on the same tape, reads 100 candles live and 300 in practice. The vote comes out different. | STILL TRUE (2 of 3) | Yes |
| **#119 H4** | A practice bot could not afford its own opening position when it ran alone. | **FIXED** | No — strike this row |
| **#120** | The practice venue states coin decimal places in a unit real ccxt reads as whole coins. Fed its own rate card, real ccxt refuses the order. | STILL TRUE (6 of 6) | Yes |
| **#121** | Every practice trade is cheaper than the real one. A market order pays 0.6% where the venue's own rate card says 1.2%. | STILL TRUE (2 of 2) | Yes |
| **#122** | Live retries a network hiccup 3 times. Practice retries once. The retry code has never run in a replay. | STILL TRUE (2 of 2) | Yes |
| **#123** | The bot is not the same code. It takes a `sim_mode` switch, and in practice it runs on a private wire that nothing listens to. | STILL TRUE (6 of 6) | Yes |
| **#124** | Practice has no spread, one fake order-book level a billion deep, and reports errors in a language the bot's handlers do not catch. | STILL TRUE (5 of 5) | Yes |
| **#125 A1/A2/A3/A5** | Nothing states what a venue must do when it refuses. Paper trading does not exist. | STILL TRUE (4 of 5) | Yes |
| **#125 A4** | "Both dead practice exchanges are built nowhere in the source." | **NEVER TRUE** — one of the two IS built, at `nuclear_controller.py:278` | No — rewrite the row |
| **#126** | The practice venue never connects. No preflight, no coin list, no trade-history scan. | STILL TRUE (3 of 5) | Yes |
| **#127** | The practice venue calls back into the application on every fill. Live has no such channel, and the callback is still read two different ways. | STILL TRUE (2 of 2) | Yes |
| **#111 defect 1** | The topology stress tool asks for a 1-hour candle the tape cannot serve, so every trial's higher-timeframe read fails. | STILL TRUE | Yes — small, tooling only |
| **#111 defect 2A** | The bot believed it held coins the tape never sold it. | **FIXED** by #111A | No |
| **#111 defect 2B** | Whether a bot could trade depended on how many OTHER bots existed. | **FIXED** by #111B | No |
| **#107** | Detonation fires once per bull run inside one session, then fires AGAIN on the same bull run after a restart. | STILL TRUE | Yes — dormant, see section 6 |

---

## 3. Method, and what the instrument was checked against

Three probe files were written into the clone's `tests/` directory and run
**through pytest**, never as bare scripts. They were deleted after the run; the
clone's tracked files are unchanged.

```
python -m pytest tests/test_zz_reval_probe_venue.py     -q -s -p no:randomly   26 passed
python -m pytest tests/test_zz_reval_probe_connector.py -q -s -p no:randomly    6 passed
python -m pytest tests/test_zz_reval_probe_107_111.py   -q -s -p no:randomly    7 passed
```

Exit code 0 on all three. No 139, no 127.

**43 surviving rows: 30 were reproduced by running code today. 13 were verified
by reading the current source.** The 13 are the ones with no runtime surface to
drive — a missing class, a missing rule book, a branch on a flag.

**The live-tree guard reported DEGRADED on every run**, because Acervator is
running. It named 5 files under `~/.acervator_logs` as modified. Those are the
live application's own writes — its console log, its heartbeat, its signal
files. The probes wrote nothing there. This is stated so the guard's own words
are on the record and not quietly dropped.

### Two calibration failures, recorded rather than hidden

**First instrument, first answer: wrong.** The candle probe reported LIVE 1
candle / SIM 1 candle. `TabletBackend` starts every cursor at row 0, so an
unstepped tape shows exactly ONE candle. The instrument was measuring the cursor,
not the window. After walking the tape to its end, the same probe reported LIVE
100 / SIM 300. **A zero from an uncalibrated reader is a claim about the reader.**
The unstepped run is retained in the probe as its own negative control.

**Second instrument, first answer: wrong.** The rejected-resting-order probe
reported `status=open`. The synthetic tape never fell far enough to cross the
resting price, so no sweep ever ran. With a tape that steps from 100 to 80 and a
resting buy at 75, the same probe reported `status=rejected`, and the connector
parsed it as `OrderStatus.FAILED, filled=0.0, average=0.0` — exactly what the
original audit said.

Both first answers would have been reported as FIXED. Neither was.

---

## 4. Evidence — group by group

Line numbers are as they are TODAY. Many moved: R1 relocated the whole Simulator
engine from `src/gui/` to `src/simulator/`, and `scrumming_bot.py` shifted by
about 70 lines.

### Group E — order writes (#118). 11 of 11 still true.

Driven through `CCXTConnector.place_order` with `TabletBackend` attached, which
is the path a bot takes.

| Row | Measured today |
| --- | --- |
| E1 | `place_order(..., amount=-1.0)` returned `Order(amount=-1.0, filled=-1.0, status=FILLED, fee=-0.60)`. Wallet before: `USD 1,000,000`, `CHIP 0`. After: **`USD 1,000,100.60`, `CHIP -1.0`**. The ledger ran backwards and the wallet gained money. |
| E2 | `amount=0.0` returned `status=closed, filled=0.0`. |
| E3 | `amount=NaN` raised `ValueError: cannot convert float NaN to integer` — out of precision arithmetic, not out of a refusal. |
| E4 | LIMIT with no price raised `TypeError: float() argument must be a string or a real number, not 'NoneType'`. |
| E5 | IOC limit at the last price: `status=closed, filled=1.0, remaining=0.0`. Filled 100%, no cancel-remainder. |
| E6 | 1,000,000-unit market buy: `filled=1000000.0`, `average=100.0`, last=100.0, **slippage exactly 0.0**. |
| E7 | Same `client_order_id` twice: two distinct order ids, **2.0 CHIP booked**. |
| E8 | Resting BUY 5 @ 50 with 1,000 USD: `free=1000.0`, `used=0.0`, `total=1000.0`. Nothing was held. |
| E9 | Resting BUY 5 @ 75, wallet drained, tape steps to 80: `status=rejected`; connector parses `OrderStatus.FAILED, filled=0.0, average=0.0`. |
| E10 | `cancel_order("nope")` and `fetch_order("nope")` both raise `ValueError: no such order 'nope'`. |
| E11 | `order["info"] == {"sim": True, "params": {...}}`. |

**The agreement the audit recorded also holds.** An unfundable marketable buy
raises `ccxt.InsufficientFunds`, with the arithmetic in the message:
`"CHIP/USD buy 5.00000000 at 100.00000000 needs 503.00000000 USD (notional
500.00000000 + fee 3.00000000) but the wallet holds 1.00000000 USD"`. #111A's fix
is intact.

**Why E5, E8 and E9 are on the main path, not a corner.** `ScrummingBot` places
LIMIT sells for every visible bot (`scrumming_bot.py:17170` and `:17827`), and
IOC_LIMIT when Aggressive is on. Read from `bot_state.json` today: **37 of 38
bots carry `visibility: "orderbook"`.** One is `internal`. Zero are aggressive.
A replay of the real fleet therefore places resting orders for 37 bots.

### Group H — wrappers (#119). 2 of 3 still true. 1 fixed.

**H1 — reproduced exactly.** One `TabletBackend` with 400 candles, walked to the
end, attached to a real `CCXTConnector`, driving `ScrummingBot._get_ohlcv` and
`_get_balance` five times each:

| Configuration | Candles the bot got | `fetch_ohlcv` calls | `fetch_balance` calls |
| --- | ---: | ---: | ---: |
| LIVE (pool wired) | **100** | 1 | 1 |
| SIM (no pool) | **300** | 5 | 5 |

The mechanism is intact on both sides. `MarketDataPool.get_or_fetch_ohlcv`
returns `entry.candles[-limit:]` (`data_pool.py:561` and `:617`) — 100.
`CCXTConnector.get_ohlcv` still passes `limit` into ccxt's `since` slot
(`ccxt_connector.py:1268`), so the direct call returns the 300-row default page.
`ScrummingBot._get_ohlcv` falls through to the direct call when `_data_pool is
None` (`scrumming_bot.py:4624-4634`). Every live bot gets the pool: `main.py:1036`
sets it on the manager, `bot_container.py:2430` pushes it to existing bots, and
`bot_container.py:3165` gives it to every bot registered afterwards.

**H2** — the same run: 1 balance call live, 5 in the Simulator.

**H3 — latent, unchanged.** `VolumeGuard.enabled` still hard-returns `False`
(`volume_guard.py:189-196`, MEM-259). It is constructed on the live manager only
(`main.py:1029`). Not a divergence today. Do not count it as fixed.

**H4 — FIXED.** The row said a lot-less Simulator bot must buy its whole target
at `target × (1 + fee)`, and that the last bot in a fleet is therefore always
short. #111B closed it, not by adding fee headroom but by opening such a bot with
a locked side: `_open_locked_sides` (`fleet_replay_controller.py:1293`) and
`opening_lot_for_lotless` (`:447`).

Measured today, running the real `FleetReplayController` at three fleet sizes on
the same 400-candle tape:

| Fleet size | Total fills | Per-symbol fills | AAA/USD units at the end |
| ---: | ---: | --- | --- |
| 1 | 2 | `AAA/USD: 2` | **1.08977198** |
| 2 | 3 | `AAA/USD: 2, BBB/USD: 1` | **1.08977198** |
| 3 | 5 | `AAA/USD: 2, CCC/USD: 2, BBB/USD: 1` | **1.08977198** |

**AAA fires the same number of trades and ends holding the same units at every
fleet size.** The total rises only because more bots exist. The original table
was 0 / 3 / 6 fills, with the single-bot fleet firing nothing at all. That
coupling is gone.

**H5 — legitimate, confirmed.** `_make_sim_capital_registry`
(`fleet_replay_controller.py:149-175`) builds a real `CapitalReservationRegistry`
with `autosave=False` and a temp state path. The reservation code path runs for
real; only the persistence to the operator's tree is removed.

### Group C — market metadata (#120). 6 of 6 still true.

- **C1.** `ccxt.coinbase().precisionMode == 4 == ccxt.TICK_SIZE`. Same for
  `binance` and `kraken`. The Simulator's template says
  `precision: {price: 8, amount: 8}` (`tablet_backend.py:~210`). Loading that
  market dict into a real `ccxt.coinbase()` and calling
  `amount_to_precision("CHIP/USD", 1.23456789)` raises
  **`InvalidOrder: coinbase amount of CHIP/USD must be greater than minimum
  amount precision of 8`**. The Simulator's own method returns `'1.23456788'`.
  The two read the same field as different units.
- **C2.** `limits.amount.min == 0.0` for every symbol.
- **C3.** `limits.cost.min == 1.0` for every symbol.
- **C4.** The market dict declares `maker 0.006 / taker 0.012`. A market (taker)
  order was charged `rate=0.006`. The advertised fee and the charged fee are
  different numbers.
- **C5.** Market `id` is `symbol.replace("/", "-")` — `CHIP/USD` becomes
  `CHIP-USD`.
- **C6.** `int(1e-08) == 0`. The connector rescues it with
  `int(precision.get("amount", 8) or 8)` at two sites. The two sides agree at 8
  by accident of that fallback.

### Group F — fees (#121). 2 of 2 still true.

A market order on 100.0 notional was charged 0.60 — an effective rate of
**0.600000%** — while the same venue's market dict declares taker 1.2%.
`TabletBackend._fee_rate(self, symbol)` takes no side argument
(`tablet_backend.py:465`). One flat rate per symbol, default 0.006. No maker /
taker split, no volume tier.

### Group G — errors and retry (#122). 2 of 2 still true.

**G1.** Every Simulator failure is a Python builtin or a Simulator-only class,
never a ccxt one:

| What failed | Simulator raises | ccxt class? |
| --- | --- | --- |
| unknown symbol ticker | `ValueError` | no |
| unknown symbol candles | `ValueError` | no |
| unknown order | `ValueError` | no |
| unknown market | `ValueError` | no |
| LIMIT with no price | `TypeError` | no |
| bad timeframe | `ValueError` | no |
| tape not yet open | `TabletNotStarted` | no — MRO is `[TabletNotStarted, Exception, BaseException, object]` |

`InsufficientFunds` is the only shared class.

**G2 — measured, not read.** `_with_retry` retries when the exception's class
NAME contains ratelimit, timeout, network or request
(`ccxt_connector.py:239-262`). Counting backend calls:

| Exception raised by the backend | Backend attempts |
| --- | ---: |
| `ccxt.RequestTimeout` | **3** |
| `ccxt.NetworkError` | **3** |
| `ccxt.RateLimitExceeded` | **3** |
| `ccxt.BadSymbol` | 1 |
| `ValueError` | **1** |
| `TypeError` | **1** |

Every Simulator failure name misses the keyword filter. The retry-and-back-off
path has never run in a replay.

### Group D — market data reads (#124). 5 of 5 still true, D6 legitimate.

- **D1.** `bid == ask == last == 105.0`. Spread exactly `0.0`.
- **D2.** One level per side, price = last close, size `1e9`.
- **D3.** Unknown symbol raises `ValueError("no candles for 'NOPE/USD'")`, not
  `ccxt.BadSymbol`.
- **D4.** `fetch_ohlcv(symbol, "1h")` raises
  `ValueError("no 1h series for 'CHIP/USD'...")`.
- **D5.** `TabletNotStarted` is a Simulator-only class with no live analogue.
- **D6 — legitimate.** `fetch_tickers` omitted `B/USD` while its tape had not
  opened, and served `A/USD`. A symbol with no data cannot be priced.

### Group I — bot sim branches (#123). 6 of 6 still true, I5 legitimate.

`ScrummingBot.__init__` still takes `sim_mode: bool` — now at
`scrumming_bot.py:544`, set at `:567`.

| Row | Where it lives today |
| --- | --- |
| I1 | private `EventBus` at `scrumming_bot.py:582-635`; fails closed if it cannot be built |
| I2 | `_crr()` returns `None` in sim with no injected registry, `scrumming_bot.py:1395` |
| I3 | `_total_holdings = None` on the first reserve only, `scrumming_bot.py:1516-1517` |
| I4 | `phantom_balance.py:275` branches on `_sim_mode` |
| I5 | `sim_run_log.py:554` — **legitimate**, an extra artefact, not a change in bot behaviour |
| I6 | `nuclear_verification.py:222` |
| I7 | `indicator_panel.py:926` and `:1464` |

### Group A — venue topology (#125). 4 of 5 still true, 1 never true.

- **A1 — still true.** `BotMode` has exactly two members: `SCRUMMING` and
  `EXTRACTOR` (`bot_container.py:99-100`). The only file in the repository with
  "paper" in its name is `docs/engineering-notes/2026-08-05_paper_trader_concept_spec.md`.
  No backend, no bot, no mode value, no source file.
- **A2 — still true.** `class TabletBackend:` (`tablet_backend.py:103`).
  Subclasses nothing.
- **A3 — still true.** Three classes exist: `TabletBackend`,
  `FleetSimExchange` (`simulator/fleet/sim_exchange.py:70`),
  `NuclearSimExchange` (`simulator/nuclear_sim_exchange.py:91`).
- **A4 — NEVER TRUE as written.** See section 5.
- **A5 — still true, with a moved number.** `src/exchange/base.py` is **282**
  lines today, not 273. It still states failure behaviour exactly once: one
  `raise NotImplementedError` at `base.py:271` for `get_my_trades`. Nothing
  states what a venue does on insufficient funds, unknown symbol, unknown order
  or missing price. The substance holds; the line count moved by 9.

### Group B — connection lifecycle (#126). 3 of 5 still true, 2 legitimate.

Measured:

| | before `attach_backend` | after |
| --- | --- | --- |
| `is_connected` | `False` | **`True`** |
| `_ccxt` | `None` | **`None`** |
| `_ccxt_sync` | `None` | **`None`** |
| `_min_request_interval` | `0.1` | **`0.0`** |

- **B1 — still true.** `connect()` never runs. `attach_backend` sets
  `_connected = True` directly (`ccxt_connector.py:1119`), and both ccxt handles
  stay `None`.
- **B2 — legitimate.** Credentials are write access.
- **B3 — still true.** `load_markets()` never runs. Markets come from
  `_default_market` (`tablet_backend.py:199-218`).
- **B4 — legitimate.** `0.1` to `0.0`, and there is no network to limit.
- **B5 — still true.** The `trade-historian` thread is spawned inside the connect
  path (`ccxt_connector.py:637-641`), which `attach_backend` bypasses.

### Group J — callbacks (#127). 2 of 2 still true.

- **J1.** `ExchangeInterface` declares 17 members. `on_trade` is not among them.
  `TabletBackend` has it; `CCXTConnector` does not. The venue calls into the
  application on every fill, and the contract does not know the channel exists.
- **J2.** `_read_fill` (`fleet_replay_controller.py:1608-1668`) still carries two
  branches — a dict branch for `TabletBackend` and an object branch for
  `FleetSimExchange`, with different time units on each. This is #110's exact
  home, and it is still two-shaped.

---

## 5. The two errors in the original audit

### A4 — "both are instantiated zero times in `src/`". NEVER TRUE.

Half is right. `FleetSimExchange` is built nowhere in `src/`; its only
`FleetSimExchange(` hit is inside its own class docstring
(`sim_exchange.py:78`). Dead, confirmed.

The other half is wrong. **`NuclearSimExchange` IS built in `src/`, at
`src/simulator/nuclear_controller.py:278.`** What makes it unreachable is one
level up: `NuclearController` itself is constructed only in its own docstring
(`:63`) and in one test. The substance — nothing in the running application
builds it — survives, but the sentence as written is false and will not
reproduce if anyone re-runs the check.

The row's test counts also drift. Measured today: **11 test files import
`FleetSimExchange`** — the audit said 11, correct. **4 test files reference
`NuclearSimExchange`** — the audit said 5.

### #117 — "two more compare the two dead venues to each other". CANNOT VERIFY.

Six test files carry `parity` in the name, plus one source file
(`src/trading/stone_tablets/parity_harness.py`). That is the seven.

Two of the six do target the dead `FleetSimExchange`:
`test_sim_live_ohlcv_parity.py` and `test_state_parity_on_import.py`. That
sub-claim holds.

I found no pair that compares `FleetSimExchange` to `NuclearSimExchange`. It may
exist under a name without "parity" in it. To settle it I would need the original
audit's file list, which the issue does not carry. **Recorded as unverifiable
rather than guessed either way.**

### And one thing the audit UNDERSTATED

`tests/test_sim_live_ohlcv_parity.py` does pin the 300-candle divergence open, as
#117 says. But its stated premise is **backwards**. Its docstring and its test
name say *"ScrummingBot asks for 100 and live hands back 300."* Measured today, a
live bot receives **100**, because `MarketDataPool` truncates the 300-row page
before the bot sees it. The connector returns 300; the bot never does.

The test therefore does not merely pin a divergence. It encodes an inverted model of
Live, and it pins the dead venue to match that inverted model. Whoever eventually
works H1 will read this file first and start from a false premise.

---

## 6. #107 — the detonation double-fire. STILL TRUE.

You recalled this one as real. It is real. Both halves of it.

### Driven, not read

A bot object was built with the real `_check_detonation_trigger` method, a real
`VotingEngine` reading a rising daily tape, and detonation enabled:

| Call | Result |
| --- | --- |
| Fire 1 — fresh process, bull run begins | **True** |
| Fire 2 — SAME process, same bull run, hourly limit stepped past | **False** |
| Fire 3 — AFTER a restart, same bull run, same tape | **True** |

Fire 2 is the control. It proves the edge trigger genuinely works inside one
session, so Fire 3 is not a vacuous pass. **The double-fire across a restart is
reachable.**

### Why

`_detonation_last_signal_bullish` and `_detonation_last_check_ts` are set at
`scrumming_bot.py:930-931` and written by nothing that persists. The code says so
in its own words, at `scrumming_bot.py:5832-5834`:

> What's NOT preserved (deliberately reset on restart):
> `_detonation_last_*` — detonation edge-trigger resets so first tick evaluates
> fresh (correct behavior after a session gap)

Confirmed by search: the string "detonation" does not appear in
`export_scrumming_state`, and "_detonation_last" does not appear in
`BotContainer.get_full_state`.

A daily candle that stays bullish across a restart reads as a fresh crossing. The
bot detonates again. Your directive says once per bull run.

### The second half also holds

`_execute_detonation` (`scrumming_bot.py:16798`) sizes the harvest from
`self._current_holdings`, not from an exchange read. The exchange is the
authority.

### The precondition, confirmed from your own state file today

`~/.acervator/bot_state.json`, saved **2026-08-26 12:18:04**, 38 bots:

- `detonation_enabled: False` on **38 of 38**.
- **0 bots have it enabled.**
- Zero configs are missing the key, so this is a real count, not a default.
- The declared default is `False` (`bot_container.py:445`).

**What would have to be true for this to bite you.** All four, together:

1. You enable detonation on a bot.
2. That bot's daily candle turns BULLISH at confidence 0.75 or above.
3. It detonates — sells everything above its anchor and resets its target.
4. Acervator restarts while that same daily candle is still bullish.

Then it detonates a second time on the same bull run, and it sizes the second
harvest from an internal number rather than the wallet.

**Today, step 1 is false on every bot. The defect is unreachable.** It stays
DORMANT, and the standing precondition stands: repair it BEFORE enabling
detonation on any bot.

---

## 7. #111 — one of three claims survives

**Defect 1 — STILL TRUE, and small.** `topology_stress._config_for` still
hardcodes `"ta_timeframe": "1h"` (`topology_stress.py:241`). `_run_one_trial`
passes no `tf_rows`. `FleetReplayController._build_sim` passes no `tf_rows` to
`TabletBackend` (`fleet_replay_controller.py:1007-1013`). Driven: a 1h read on a
controller-shaped tape raises
`ValueError: no 1h series for 'CHIP/USD'...`. Positive control: the same tape
serves 5m without error. Every stress trial's higher-timeframe read fails.
This is a tooling defect, exactly as originally filed.

**Defect 2A — FIXED.** The bot no longer books a position the venue never sold
it, because the venue now refuses by raising. Measured:
`ccxt.InsufficientFunds` with the shortfall arithmetic in the message. #111A's
fix is in place and holds.

**Defect 2B — FIXED.** See H4 above. A bot's fills and closing units no longer
change with fleet size.

**Disposition:** #111 should be reduced to defect 1 only, or folded into section
8 as one line.

---

## 8. The Simulator, collapsed into one statement

Per your direction of 2026-08-25 — *"Anything Simulator-related needs to be
collapsed and reconsidered in the context of the spec"* — the surviving Simulator
rows are not restated as a work queue. They are the evidence for one statement.

### What the Simulator does not yet do, measured 2026-08-26

The spec says three venues, one trading logic, one bot list, one indicator voting
panel. Live alone writes to a real exchange. The only other difference allowed is
where the price data comes from.

Measured today, the Simulator differs from Live in **four ways that are not the
data source**, across 43 verified rows.

**One. It is a different exchange, not a different data feed.** (34 rows)
The practice venue was written from scratch and was never told what an exchange
must do, because no such rule exists — the contract file is 282 lines and states
failure behaviour once. It accepts orders a real exchange refuses, including
an order for minus one coin that filled and ran the wallet backwards. It charges
0.6% where its own rate card says 1.2%. It never holds money behind a resting
order, so the same money can be spent twice. It fills the same order reference
twice. It has never shown a spread, never partially filled, and never produced
slippage. It states coin precision in a unit real ccxt reads as whole coins. It
reports its errors in Python builtins the bot's ccxt handlers do not catch, so a
network hiccup that Live retries three times is retried once. It never connects,
never loads a coin list, and never starts the trade-history scan. And it calls
back into the application on every fill through a channel Live does not have.

**Two. It feeds the bot a different amount of data.** (2 rows)
Same bot method, same tape, same call: Live 100 candles, Simulator 300. The
project's own test proves 100 and 300 produce a different indicator vote. **Until
this closes, no Simulator result is evidence about Live** — which is the
Simulator's entire purpose. Gate-latch parity, the Simulator's stated validation
criterion, cannot be measured while the two sides read different windows.

**Three. It is not the same bot code.** (6 rows)
`ScrummingBot` takes a `sim_mode` switch. In the Simulator the bot runs on a
private event bus, so nothing downstream hears it — trade log, gate log, sounds,
GUI. Capital reservation reports unavailable instead of being simulated. One
drift check is skipped on the first reservation.

**Four. Paper does not exist.** (1 row)
No backend, no bot, no mode value, no source file. The three-venue comparison has
been a two-venue comparison throughout.

**And the tests cannot see any of it.** Seven parity files exist. None compares
Live behaviour to Simulator behaviour on the same call. Two target a venue that
is dead. One pins the 300-candle divergence open on a premise that is backwards —
it says Live hands the bot 300 candles, and Live hands the bot 100.

**This is not a work queue.** It is the input to a future unitization, after the
CTO's issues clear.

---

## 9. Consolidation — what the ten children should become

No child issue is empty. Every one still carries at least two true rows. But ten
issues for one seam is ten re-openings of the same files, which is the shape you
ruled against.

**Recommended:**

| Action | Issues |
| --- | --- |
| Close as consolidated INTO #117 | #118, #119, #120, #121, #122, #123, #124, #125, #126, #127 |
| Rewrite #117 as the single statement in section 8, keeping the 51-row table as its evidence appendix | #117 |
| Strike row H4 from the evidence — fixed by #111B | #119 |
| Rewrite row A4 — one of the two dead venues IS built in `src/` | #125 |
| Reduce to defect 1 only, or fold into #117 | #111 |
| Leave open, DORMANT, unchanged | #107 |

The 43 surviving rows group into 12 real defects, not 43:

1. The practice venue accepts orders a real exchange refuses. *(E1-E4, E10, D3-D5, G1)*
2. Every practice trade is cheaper and cleaner than the real one. *(F1, F2, C4, D1, D2, E5, E6)*
3. A resting order does not hold the money it claimed. *(E8, E9)*
4. The same order reference fills twice. *(E7)*
5. The bot reads 100 candles live and 300 in practice. *(H1, H2)*
6. Coin precision means two different things on the two sides. *(C1, C2, C3, C5, C6)*
7. A network hiccup is retried 3 times live and once in practice. *(G2)*
8. The bot is not the same code in both places. *(I1-I4, I6, I7)*
9. The practice venue never connects. *(B1, B3, B5)*
10. Nothing states what a venue owes the bot when it refuses. *(A5, A2)*
11. Three practice venues exist, two are dead, and 11 test files still import one of them. *(A3, A4)*
12. The practice venue has a feedback channel Live does not have, read two ways. *(J1, J2)*

Plus, outside the venue: **13.** Paper does not exist *(A1)*, and **14.** the
topology stress tool asks for a candle its tape cannot serve *(#111 defect 1)*.

---

## 10. Priority order

**Everything in this report sits behind the CTO's issues.** Per your instruction
of 2026-08-26 — *"wanting to put all of my Issues behind those of the CTO's"* —
nothing below starts until #71-#91, #112-#114 and #128 are clear.

**Behind the CTO's queue, in this order:**

| Rank | Item | Why here |
| ---: | --- | --- |
| **1** | **#107** — detonation double-fire | The only survivor that is LIVE bot code, not Simulator code. It is dormant and unreachable today, and it costs nothing to leave sitting. But it is a gate on a feature you may want to switch on, and the repair is two small changes. Rank 1 because it is the only item that touches real money at all. |
| **2** | **#117 collapsed** — the Simulator statement | The largest body of work and the one you have already ruled must be unitized as a whole. Inside it, the candle-window gap comes first: while Live reads 100 and Sim reads 300, no other Simulator repair can be verified against Live. Second inside it comes the venue rule book, because every order-write defect exists for the same reason — nothing ever stated what a venue owes the bot when it refuses. |
| **3** | **#19** — Paper Trader | Owned elsewhere. It must be born conforming to the venue rule book, so it follows rank 2 rather than leading it. |
| **4** | **#111 defect 1** — the 1-hour candle the stress tool cannot get | Tooling only. No bot, no money, no Live path. Small enough to fold into whatever touches `topology_stress.py` next. |

---

## 11. What was not done

- No production code was written. No file in the repository was changed except
  this report.
- No branch was created. Nothing was committed.
- `Acervator.exe` was not started, stopped, attached to or queried.
- `~/.acervator/coinbase_credentials.json` was never opened.
- `~/.acervator/stone_tablets/` was never touched.
- `dev_harness/` and `~/.claude/` were not edited.
- The three probe files were created under `tests/`, run through pytest, and
  then deleted from the clone. Copies are kept outside the repository, in the
  session scratchpad, named `test_zz_reval_probe_*.py`. Every number they
  produced is in the tables above.
