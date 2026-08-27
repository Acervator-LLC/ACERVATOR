# Ammo refresh cadence — measured, and the fix is cheaper than the status quo

Operator item 1 of 3, 2026-08-06:

> "The Ammo read out is not updating often enough."

Confirmed, quantified, and the obvious remedy turns out to be backwards:
the fresher design costs **fewer** API calls than what runs today.

## The complaint is real and worse than it looks

The dashboard recomputes Ammo every 2s. That part is fine. The *price* it
recomputes from is not.

`stats.current_price` is written at `scrumming_bot.py:5136`, which sits
**after** the read-rate gate at `:4883`:

```python
_base_skip = max(1, int((self.config.scrum_read_rate_min * 60) / _tick_sec))
if self._scrum_target_mode in ('track', 'fire'):
    self._tick_skip = max(1, _base_skip // 10)
else:
    self._tick_skip = _base_skip
self._tick_counter += 1
if self._tick_counter < self._tick_skip and self._initialised:
    return
```

The gate returns before the price read, which leaves the display price
refreshing at the bot's *decision* cadence, not the dashboard's.

Measured against live state, `tick_interval = 5.0s`:

| bots | mode | `read_rate_min` | price refresh |
|-----:|------|----------------:|--------------:|
| 1  | search | 5 | **300s** (ALLO/USDC) |
| 17 | search | 1 | **60s** |
| 5  | track/fire | 5 | 30s |
| 12 | track/fire | 1 | 5s |

**18 of 35 bots refresh at 60s or slower.** ALLO/USDC updates its Ammo
price once every five minutes while the cell repaints 150 times.

The number on screen is not wrong. It is old, and nothing on the cell
says so.

## Two dead ends, ruled out by measurement

**Read the shared pool for display.** `MarketDataPool.get_ticker()` is a
pure dict read — free, no network. But the fleet runs **35 distinct
symbols with zero overlap**, so each pool entry has exactly one writer:
the bot itself. The pool returns the same stale value. No gain.

**Lower `scrum_read_rate_min`.** That is an operator setting that governs
*decisions*, and the repair plan flags the risk correctly: it multiplies
per-bot polling across 35 live bots. Rejected as written.

## The batch endpoint inverts the trade-off

`ccxt_connector.py:838` already exposes:

```python
async def get_all_tickers(self) -> dict:
    """Fetch all tickers for this exchange in one bulk call."""
```

One rate-limited call returns **every symbol**. Per-bot polling spends 35
calls to cover the same ground.

| design | calls/hour | cache freshness |
|--------|-----------:|----------------:|
| **today** — per-bot polling | **10,272** | **up to 300s** |
| batch every 10s | 360 | 10s |
| batch every 5s | 720 | 5s |
| batch every 2s | 1,800 | 2s |

A batch refresh every 5s is **14x fewer API calls** than what runs now,
while keeping the shared cache fresher. This is not a freshness-vs-cost
trade; the current design is dominated.

> **CORRECTION, 2026-08-07.** The right-hand column was originally
> labelled "worst display staleness", and this report claimed the change
> takes the readout from 300s to 5s. **That was wrong.** It describes the
> *pool cache*, not the readout. The dashboard reads
> `stats.current_price`, which only the gated tick writes
> (`scrumming_bot.py:5136`); warming the cache never touches that field.
> The API reduction and the fresher decision-time price are real and
> unaffected. Display freshness needed a separate reader, shipped
> 2026-08-07 — see
> [2026-08-07_manual_fire_rezero.md](2026-08-07_manual_fire_rezero.md).

## The part that needs your ruling

`scrumming_bot._get_ticker` (`:2430`) already routes through the pool
with a 5s TTL. A fleet refresher writing fresh entries into that pool
would therefore be seen by the **trading path**, not just the display.

That is not a cadence change — bots would still decide on their existing
gated schedule, `scrum_read_rate_min` untouched. It is a **data-quality**
change: a bot that decides every 300s would do so against a 5s-old price
instead of a 300s-old one.

I believe that is strictly better and is what you already think is
happening. It is still a change to what the trading logic sees, and you
have been burned by silent behaviour changes, so I am not slipping it in
under a display ticket.

**Two ways to take it:**

- **(A) Display-only.** Refresher writes to a separate display cache the
  GUI reads; the pool and trading path are bit-identical to today. Fixes
  the complaint, banks none of the API savings, adds a second price path
  to keep honest.
- **(B) Pool-level.** Refresher warms the shared pool. Display gets
  fresh, trading path gets *better* data at an unchanged decision
  cadence, and fleet API volume drops ~14x. One price path.

I recommend **(B)**, with the batch interval as a config key defaulting
to 5s, and the Ammo cell carrying a staleness marker regardless of which
path so the number can never silently rot again.

**(A) is the reversible one.** If you want the freshness now and the API
reduction as a separate decision later, take (A) and I will bank the
savings in its own cascade.

## Shipped 2026-08-06 (operator ruled pool-level)

- `MarketDataPool.refresh_all_tickers(connector, exchange_id)` — warms
  every already-cached entry from one bulk call. Refuses to adopt
  uncached symbols (the payload lists every pair on the exchange),
  refuses to blank a good price with a junk row, and refuses to clobber
  an individual fetch that landed mid-flight. Never raises.
- `BotManager.refresh_all_tickers_once()` /
  `_ticker_refresh_loop` / `start_ticker_refresher` /
  `stop_ticker_refresher` — one connector per **exchange**, not per bot,
  which is the whole economic argument. A failing exchange does not stop
  the others; a failing cycle does not kill the loop.
- `main.py` starts it after `set_async_loop` at 5.0s — matched to the
  pool's own `TickerEntry.is_stale` TTL, so the cache is rewarmed exactly
  as it expires. Refreshing faster would spend calls on entries still
  fresh to every reader. Wrapped so it can never block startup.
- Telemetry: `ticker_batch_refreshes`, `ticker_batch_symbols`,
  `ticker_batch_races` in `get_status()`.

31 new tests, suite 1656 passing.

**The field mapping was the trap.** `volume_24h` comes from CCXT's
`quoteVolume`, not `baseVolume`, and `timestamp` is milliseconds needing
`/1000`. Guessing either wrong would not raise — it would quietly corrupt
the cache for every consumer. Both are locked against the connector's own
source, so a future change there breaks the test rather than the data.

**Follow-up:** the 5.0s interval is a literal at the call site. Promoting
it to a config key is worth doing but adds settings-schema surface, so it
is deliberately not bundled here.

## Unrelated: the docs archetype is not measuring anything

While verifying this work, two pre-existing failures surfaced on a clean
tree (`test_docs_archetype.py::TestGroundTruthRecall` D4 and D5). Root
cause: the installed proselint no longer exposes `proselint.tools.lint`,
so the prose layer returns **zero findings** rather than erroring — it has
been passing every document it checked. Docketed separately; the
ground-truth tests are the positive control that caught it and must not
be weakened to green the suite.

## What this does not address

Item 1 only. The Ammo *arithmetic* was verified separately: C10 made the
per-bot cell recompute from `holdings x price`, and
`tools/harness/reconcile_position_values.py` compares that against the
persisted record with a positive control that fails loudly at exit 3
when it measures nothing. Staleness was the remaining defect, and it is
in the price input, not the formula.

Items 2 (Manual Fire re-zeroing) and 3 (Target Delta vs API inputs)
remain open.
