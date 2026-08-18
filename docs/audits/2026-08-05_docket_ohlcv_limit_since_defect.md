# DOCKET — `get_ohlcv` passes `limit` into ccxt's `since` slot

**Filed** 2026-08-05 · **Found in** v3.24.33 (Stone Tablet auto-updater cascade)
**Site** `src/exchange/ccxt_connector.py:876`
**Status** OPEN — deliberately not fixed in the cascade that found it
**Severity** MEDIUM. Not a crash, not data loss. It is a **silent
sim/live divergence** plus a **false claim in `gate_healer`**.

---

## 1. What the defect is

ccxt's signature is positional:

```python
Exchange.fetch_ohlcv(symbol, timeframe='1m', since=None, limit=None, params={})
#                                            ^^^^^ 3rd            ^^^^^ 4th
```

The connector calls it with three positional arguments:

```python
# ccxt_connector.py:876
data = await self._call_sync(self._ex.fetch_ohlcv, symbol, timeframe, limit)
#                                                                     ^^^^^
#                                              lands in the `since` slot
```

So `get_ohlcv(symbol, "1h", limit=100)` reaches the exchange as
`since=100, limit=None`. Epoch-ms 100 is `1970-01-01T00:00:00.100Z`.

## 2. What it is doing / not doing

**Doing:** asking Coinbase for candles since 1970. Coinbase ignores the
absurd `since` and serves its default page.

**Not doing:** applying `limit` *at all*. Measured against live Coinbase
public API on 2026-08-05:

| timeframe | code asks for | **actually returned** | correct call returns |
|---|---:|---:|---:|
| 5m | 100 | **300** | 100 |
| 1h | 100 | **300** | 100 |
| 1h | 200 | **300** | 200 |
| 1d | 100 | **300** | 100 |

**Live always receives exactly 300 candles, whatever it requests.** The
`limit` argument has never had any effect on the live path.

Note the direction: live gets **more** history than requested, never
less. There is no starvation and no missing-data class of bug here. That
is why this is medium and not P0.

## 3. Why it still matters — two real consequences

### 3a. Sim and live feed TA different history lengths

The simulator's exchange honours `limit` exactly:

```
SIM  get_ohlcv(limit=100) -> 100 candles
LIVE get_ohlcv(limit=100) -> 300 candles
```

Most indicators are immune because this cascade converted them to
suffix-only windows (`_sma_tail` / `_stdev_tail`, `_TAIL_DEFAULT = 35`) —
they read the last N values and cannot see the extra 200. The exposed
ones are the **index-0-seeded recurrences**: EMA (SMA-seeded at
`period-1`) and Heikin-Ashi (forward recurrence from index 0,
`ta_engine.py:2522`).

Measured, same BTC tape, 300-candle vs 100-candle input, all 12 voting
indicators:

```
indicators compared            : 12
different on 300 vs 100 input  : 1
   macd   300 -> BEARISH 0.247571
          100 -> BEARISH 0.247687
net_score   300: 0.1813    100: 0.1812
consensus   300: 0.0155    100: 0.0155
```

One indicator, same direction, ~0.05 % relative confidence delta on this
sample. Small — but it is a **parity gap in the exact place this session
has been closing parity gaps**, and its size is tape-dependent, not
bounded by anything we control.

### 3b. `gate_healer`'s reconstruction claim is false

```python
# gate_healer.py:67-69
BB_LOOKBACK = 100
"""Candles fed to the indicator pass. Matches the live bot's
get_ohlcv(limit=100) so the reconstruction sees the same window."""
```

It does not match. The live bot saw 300; the healer reconstructs on 100.
Every healed gate decision is recomputed against a different window than
the one that produced it. The docstring at `:194` repeats the claim.

## 4. Affected live callers

All inherit the 300-candle page regardless of their stated limit:

| Site | Requests |
|---|---|
| `src/exchange/data_pool.py:449` | shared pool fetch |
| `src/exchange/data_pool.py:712` | pool refresh |
| `src/gui/chart_data.py:188` | chart series |
| `src/gui/market_inspector_fetcher.py:171` | `DAILY_BARS` |
| `src/gui/market_inspector_fetcher.py:181` | weekly bars |
| `src/trading/phantom_balance.py:238` | valuation |
| `src/trading/scrumming_bot.py:2388` | `_get_ohlcv` → gate TA |
| `src/trading/scrumming_bot.py:9473` | direct call |
| `src/trading/ta_signal_provider.py:228` | signal provider |

## 5. Why it was not fixed on discovery

Fixing it changes what every live bot's TA sees — 300 candles today,
100 after the fix — which changes MACD/EMA/HA values and therefore live
SCRUM/FOLD gate decisions. That is a live-behaviour change wearing the
costume of a one-line bug fix. It is exactly the kind of drive-by the
no-bridges and green-gate rules exist to stop.

The auto-updater cascade needed `since` to work at all, so it added the
parameter with the **legacy path byte-identical**:

```python
if since is None:
    data = await self._call_sync(self._ex.fetch_ohlcv, symbol, timeframe, limit)
else:
    data = await self._call_sync(self._ex.fetch_ohlcv, symbol, timeframe,
                                 int(since), int(limit))
```

New callers passing `since` get correct positional placement. Every
pre-existing caller keeps the exact bytes it had, so this cascade cannot
have moved a single live gate. The defect is documented in the
`get_ohlcv` docstring at the site.

## 6. What a real fix requires

1. Correct the call to `fetch_ohlcv(symbol, timeframe, None, limit)`.
2. **Before/after indicator comparison** across a real asset spread at
   every timeframe live uses — MACD, EMA and Heikin-Ashi specifically,
   with gate-decision diffs, not just indicator diffs.
3. Decide the intended window deliberately. 300 may well be the better
   number; if so the fix is to make the *requests* say 300, not to cut
   live down to 100 by accident-correction.
4. Re-point `gate_healer.BB_LOOKBACK` at whatever that decision is, and
   fix both docstrings.
5. Confirm sim matches the chosen number so 3a closes.
6. Green gate before any banner bump.

Owner: next cascade. Do not fold into an unrelated change.
