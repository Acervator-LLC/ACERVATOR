# GUI-thread pump measurement

Reference document. Item 11.0. Acervator v3.25.5, 2026-08-13.

This unit measures. It moves nothing. No product code changed, no
island was made, no version banner moved. Every number below comes
either from source, from a synthetic harness in a separate process, or
from read-only samples of files the running application already writes.

The operator's application ran throughout, trading real money on 37
live bots. It was never started, stopped, or attached to.

## Scope

Six questions were asked. Each is answered with a number and with an
instrument that was shown able to produce a different number.

Instruments and their raw output live in the session scratchpad,
`.../4da5bb5e-28d1-4b08-8ff4-f9549a4fb83c/scratchpad/`, each `.py`
beside a `.txt` or `.json` of its output:

| script | what it produces |
|---|---|
| `probe_drain_semantics.py` | what one pump drains |
| `static_estimate.py` | ready callbacks per pump, from source |
| `pump_harness.py` | the drain curve, paint budget, breaking N |
| `pump_callgraph.py` | reachability walk from pump roots |
| `plant_control.py` | the walker's planted-defect control |
| `sync_net_inventory.py` | every synchronous network call site |
| `heartbeat_watch.py` | live heartbeat sampling, with control |
| `heartbeat_under_load.py` | what does and does not delay a 2 s timer |
| `timer_granularity.py` | why a 50 ms timer fires at 62.6 ms |
| `log_gaps.py` | historical console-log gaps |

Two other jobs were editing `src/trading/scrumming_bot.py`,
`src/trading/bot_container.py`, `src/gui/bot_live_settings.py`,
`src/gui/bot_wizard.py` and `src/core/signal_contract.py` while this
ran. Every line citation below is anchored to the tree as read on
2026-08-13 between 07:05 and 07:45. Citations into those five files may
have shifted since. Re-anchor before acting on one; the surrounding
quoted text, not the number, is the identifier.

## 1. The mechanism

### 1.1 The pump as written

`main.py:1104-1111`:

```python
    def pump_async():
        """Run pending async callbacks."""
        loop.call_soon(loop.stop)
        loop.run_forever()

    async_timer = QTimer()
    async_timer.timeout.connect(pump_async)
    async_timer.start(50)
```

The loop it pumps is created at `main.py:1050-1051` and is the only
loop in the application. `main.py:1107` holds the only `run_forever`
in `src/` or `main.py`. A post-mortem the application wrote about
itself confirms coroutines execute inside it, on the GUI thread:

```
  File "main.py", line 1109, in main
  File "main.py", line 937, in pump_async
  File "asyncio\base_events.py", line 677, in run_forever
  File "asyncio\base_events.py", line 2057, in _run_once
  File "asyncio\events.py", line 94, in _run
  File "src\gui\history_helpers.py", line 290, in fetch_all_history_chunked
```

Source: `~/.acervator_logs/postmortem_20260731_194435/SUMMARY.txt`.
The premise that every coroutine runs on the Qt GUI thread holds.

### 1.2 Timers sharing that thread

Every timer below runs on the same thread as the pump and as painting.

| file:line | interval | work |
|---|---|---|
| `main.py:1109-1111` | 50 ms | `pump_async` |
| `main.py:1118-1120` | 2000 ms | `_write_heartbeat` |
| `main.py:666-668` | 5000 ms | `gc.collect()` |
| `main.py:1126-1128` | 60000 ms | `save_all_state` |
| `main.py:860-862` | 25 ms | splash animation, startup only |
| `main.py:1243` | 250 ms | `singleShot` restart poll, startup only |
| `main.py:1276` | 9500 ms | `singleShot` auto-restart, once |
| `src/gui/indicator_panel.py:210` | 16 ms | indicator animation |
| `src/gui/bot_visualizer.py:1708` | 33 ms | swarm animation |
| `src/gui/audio_suite.py:377` | 33 ms | waveform animation |
| `src/gui/main_window.py:341` | 50 ms | widget animation |
| `src/gui/main_window.py:4911` | 80 ms | pulse animation |
| `src/gui/main_window.py:4561` | 500 ms | signal refresh |
| `src/gui/main_window.py:4569` | 500 ms | console pause refresh |
| `src/gui/main_window.py:2490` | 1000 ms | pull-rate refresh |
| `src/gui/main_window.py:4885` | 2000 ms | dashboard refresh |
| `src/gui/main_window.py:5076` | 5000 ms | tooltip refresh |

The steady-state animation timers alone ask for a callback every 16 ms.
The pump asks for the thread every 50 ms and holds it for an unbounded
time. They are in direct contention.

### 1.3 What one pump drains

The brief states that `call_soon(loop.stop)` puts the stop callback at
the end of the ready queue, so `run_forever()` drains every callback
ready at that moment, and that the pump is unbounded. This was checked
against CPython 3.14.4 `asyncio/base_events.py`, then confirmed by
running the pump body against a real loop.

`run_forever` at line 672 is `while True: self._run_once(); if
self._stopping: break`. `stop()` at line 721 only sets `_stopping`.
`_run_once` at line 1977 takes a snapshot, `ntodo = len(self._ready)`
at line 2040, and runs exactly that many handles.

`probe_drain_semantics.py` put four different questions to the real
pump body and got four different answers, so it is not a canned
verdict:

```
[A] flat ready queue: does one pump run all of it?
    queued=1      ran_in_1_pump=1      left_over=1
    queued=10     ran_in_1_pump=10     left_over=1
    queued=100    ran_in_1_pump=100    left_over=1
    queued=5000   ran_in_1_pump=5000   left_over=1

[B] cascade: does one pump CHASE callbacks that callbacks schedule?
    depth=2    ran_in_1st_pump=1    ran_total=2    pumps_needed=7
    depth=5    ran_in_1st_pump=1    ran_total=5    pumps_needed=10
    depth=50   ran_in_1st_pump=1    ran_total=50   pumps_needed=55

[C] does the position of loop.stop change the extent?
    queued=10     stop_FIRST ran=10     left=1 | stop_LAST ran=10     left=1
    queued=1000   stop_FIRST ran=1000   left=1 | stop_LAST ran=1000   left=1

[D] do already-due call_later timers join the same snapshot?
    due_timers=10     ran_in_1_pump=10     left_over=1
    due_timers=500    ran_in_1_pump=500    left_over=1
```

### 1.4 Two corrections to the brief

The brief is right that the pump has no time budget. Two details in its
reasoning are wrong, and both matter to whoever changes this later.

**The stop position is not the reason.** Result [C]: putting
`loop.stop` first drains exactly as much as putting it last. The extent
comes from the `ntodo` snapshot, which is taken before any handle runs.
What `call_soon(loop.stop)` actually buys is that the loop performs
exactly ONE `_run_once` iteration. It is an iteration limiter, not a
queue-position trick.

**One pump does not drain a cascade.** Result [B]: callbacks scheduled
by callbacks run on the NEXT pump, not this one. A 50-deep chain needs
50 pumps, which at 50 ms is 2.5 seconds of wall time. The pump is
unbounded in the SIZE of one snapshot and in the COST of each handle
in it. It is strictly bounded to one iteration.

The practical consequence: a bot coroutine that suspends ten times per
tick is served over ten separate pumps, at best one suspension per
50 ms. That is a latency floor as well as a jank source.

### 1.5 The loop is not the one the code asks for

`main.py:251` runs `asyncio.set_event_loop(asyncio.SelectorEventLoop())`
on Windows, with a v3.19.9 comment explaining the choice. `main.py:1050`
then calls `asyncio.new_event_loop()`, which on Windows returns a
`ProactorEventLoop` (verified on this interpreter), and `main.py:1051`
installs it. The pumped loop is a ProactorEventLoop. The selector
choice at line 251 is discarded 799 lines later.

This is recorded as a finding, not fixed here. The harness reproduces
the real situation: it calls `asyncio.new_event_loop()` too, so it
pumps a ProactorEventLoop exactly as the application does.

## 2. The static estimate

This section is arithmetic over source. It is not an observation.

A coroutine does not cost the pump one callback per `await`. It costs
one callback per SUSPENSION. An await that yields and is later resumed
schedules exactly one `Task.__step` in `loop._ready`. An await whose
target finishes without yielding is an ordinary call and costs nothing
extra. `asyncio.Event.wait()` on a set event does not suspend, so
`_run_with_guard`'s `await self._pause_event.wait()` is not counted.

Each bot is one task, created at `bot_container.py:1253`. Its loop body
(`bot_container.py:1299-1372`) awaits `self.tick()` and then
`asyncio.sleep(self.tick_interval)`. `ScrummingBot.tick_interval` is
5.0 s (`scrumming_bot.py:3544-3545`).

`ScrummingBot.tick` (`scrumming_bot.py:5969`) holds 33 lexical awaits.
One is unconditional: `await self._get_ticker(symbol)` at
`scrumming_bot.py:6478`. The transitive closure over ScrummingBot's own
async methods reaches 22 methods and 78 await sites, 58 of which reach
the executor and therefore suspend.

The live fleet is 37 bots, read from `~/.acervator/bot_state.json`
(`bot_count` 37, all `base_currency` USD or USDC).

| case | suspends per tick | callbacks per 5 s | mean per pump | if perfectly bunched |
|---|---|---|---|---|
| floor, nominal 50 ms tick | 1 | 74 | 0.74 | 74 |
| floor, observed 62.6 ms tick | 1 | 74 | 0.93 | 74 |
| ceiling, nominal 50 ms tick | 58 | 2183 | 21.8 | 2183 |
| ceiling, observed 62.6 ms tick | 58 | 2183 | 27.3 | 2183 |

The estimate is a range because branch coverage inside `tick()` is not
knowable from source. The floor assumes only the unconditional path
runs. The ceiling assumes every reachable suspender fires on every tick,
which no real tick does.

The honest reading: in steady state this fleet puts roughly 1 to 27
callbacks on the ready queue per pump. That is far below the count at
which the pump breaks. The exposure is per-callback COST, not count.
Section 4 gives the cost at which that few callbacks still break the
budget.

## 3. The synthetic curve

### 3.1 How faithful the harness is

`pump_harness.py` runs in its own process with a real `QApplication`, a
real `QTimer` at 50 ms, a real `asyncio.new_event_loop()`, and the pump
body copied verbatim. A `QWidget` counts completed `paintEvent` calls
while an independent 16 ms timer demands repaints, so a 60 fps painter
competes for the same thread the pump holds.

Two load shapes were run. `plain` queues bare `call_soon` callbacks, the
cheapest possible ready entry. `task` queues one `Task.__step`
resumption each, which is what a suspended bot coroutine actually costs.

### 3.2 Drain against callback count

Per-callback cost fixed at about 20 microseconds. 50 ticks per row,
first 3 discarded. Shape `plain`:

| N | drain median ms | p95 ms | max ms | gap median ms | paint left ms | % of 50 ms | fps | us/callback |
|---|---|---|---|---|---|---|---|---|
| 0 | 0.113 | 0.15 | 0.18 | 62.61 | 49.89 | 0.2 | 69.7 | - |
| 1 | 0.166 | 0.22 | 0.26 | 62.57 | 49.83 | 0.3 | 73.8 | 166.40 |
| 10 | 0.416 | 0.66 | 0.74 | 62.63 | 49.58 | 0.8 | 72.6 | 41.64 |
| 37 | 1.039 | 1.30 | 1.63 | 62.60 | 48.96 | 2.1 | 71.5 | 28.08 |
| 74 | 1.913 | 2.42 | 2.86 | 62.60 | 48.09 | 3.8 | 73.5 | 25.85 |
| 111 | 2.481 | 2.87 | 3.87 | 62.55 | 47.52 | 5.0 | 70.7 | 22.36 |
| 185 | 3.891 | 5.51 | 6.01 | 62.57 | 46.11 | 7.8 | 68.5 | 21.04 |
| 370 | 7.485 | 11.55 | 11.97 | 62.60 | 42.52 | 15.0 | 68.7 | 20.23 |
| 740 | 14.601 | 17.07 | 21.10 | 62.61 | 35.40 | 29.2 | 58.6 | 19.73 |
| 1480 | 29.568 | 41.83 | 49.05 | 62.65 | 20.43 | 59.1 | 42.6 | 19.98 |
| 2960 | 59.321 | 71.97 | 122.22 | 66.43 | -9.32 | 118.6 | 24.6 | 20.04 |
| 5920 | 141.018 | 161.40 | 164.35 | 186.54 | -91.02 | 282.0 | 15.2 | 23.82 |

Shape `task`, same sweep:

| N | drain median ms | gap median ms | paint left ms | fps |
|---|---|---|---|---|
| 0 | 0.034 | 62.55 | 49.97 | 69.5 |
| 37 | 0.950 | 62.55 | 49.05 | 72.0 |
| 185 | 5.606 | 62.54 | 44.39 | 65.1 |
| 370 | 10.127 | 62.15 | 39.87 | 63.5 |
| 740 | 16.965 | 62.48 | 33.03 | 54.4 |
| 1480 | 29.872 | 62.58 | 20.13 | 41.0 |
| 2960 | 60.444 | 124.71 | -10.44 | 33.3 |
| 5920 | 121.841 | 187.85 | -71.84 | 21.4 |

**The curve is linear in N.** Cost per callback holds near 20
microseconds across three orders of magnitude, from N=37 to N=5920. It
does not degrade super-linearly. Answering question 6 directly: drain
time scales with bot count LINEARLY, not worse. The pump itself holds
no hidden quadratic.

The control is satisfied. Drain rises monotonically from 0.113 ms to
141.018 ms, a factor of 1248 across the sweep. A harness reporting a
flat figure would be measuring itself. This one is not.

### 3.3 Drain against per-callback cost

N held at 370, per-callback cost swept:

| cost target us | drain median ms | paint left ms | measured us/callback | N to reach 50 ms |
|---|---|---|---|---|
| 0 | 0.244 | 49.76 | 0.66 | 75819 |
| 5 | 2.217 | 47.78 | 5.99 | 8344 |
| 20 | 9.619 | 40.38 | 26.00 | 1923 |
| 80 | 28.694 | 21.31 | 77.55 | 644 |

Second control satisfied. Holding N fixed and moving only the work per
callback moves drain by a factor of 118. The harness responds to both
of its inputs independently.

### 3.4 The zero-load floor

Third control. At N=0 the pump costs 0.113 ms (`plain`) and 0.034 ms
(`task`). The instrument's own overhead is under a quarter of a
millisecond, which is 0.2 percent of the tick. Every figure above is
therefore the load, not the meter.

### 3.5 The tick is 62.6 ms, not 50 ms

`gap median` sits at 62.6 ms in every unsaturated row, at every load,
in both shapes. The pump runs 25 percent less often than
`main.py:1111` asks for.

62.5 ms is exactly four Windows system ticks of 15.625 ms, so the
system scheduler granularity is the obvious cause. It was tested and it
is **wrong**. `timer_granularity.py` raised the scheduler resolution
with `timeBeginPeriod(1)` and measured the same timer again:

```
    default system tick        requested=50 ms  observed_median=62.60 ms
    after timeBeginPeriod(1)   requested=50 ms  observed_median=62.30 ms
    after timeEndPeriod(1)     requested=50 ms  observed_median=62.64 ms
    system-tick explanation REFUTED
```

The real cause is Qt's timer TYPE. `QTimer` defaults to
`Qt::CoarseTimer` for intervals of 20 ms and above, and coarse timers
are aligned rather than honoured:

```
    Qt.PreciseTimer      requested=50 ms  observed_median=49.96 ms
    Qt.CoarseTimer       requested=50 ms  observed_median=62.63 ms
    Qt.VeryCoarseTimer   requested=50 ms  observed_median=999.83 ms
    period moved with the timer type  : True
```

`main.py:1109-1111` never calls `setTimerType`, so the pump runs on a
coarse timer and fires every 62.6 ms. Asking for a precise timer
recovers 49.96 ms.

Both figures should be carried forward. The pump fires less often than
intended, so more work accumulates between drains. The real budget per
firing is 62.6 ms rather than 50 ms, so each drain has more headroom
than the nominal figure suggests.

## 4. Paint budget and the breaking N

The paint budget is the tick interval minus the drain. Measured against
the nominal 50 ms, `plain` shape:

- N=37, one callback per live bot: 48.96 ms left, 97.9 percent of the
  tick, 71.5 fps sustained.
- N=370: 42.52 ms left, 85 percent, 68.7 fps.
- N=740: 35.40 ms left, 71 percent, 58.6 fps.
- N=1480: 20.43 ms left, 41 percent, 42.6 fps.
- N=2960: budget exhausted, drain 59.3 ms exceeds the interval,
  24.6 fps.
- N=5920: drain 141 ms, timer gap stretches to 186.5 ms, 15.2 fps.

Frame rate is the operator-visible number. It falls from 69.7 fps
unloaded to 15.2 fps at N=5920, a 78 percent loss, with no change
anywhere except the depth of the ready queue.

The breaking N was measured by bisection, not interpolated, at about
20 microseconds per callback:

```
    N=4000   drain_med=  106.48 ms  OVER
    N=2000   drain_med=   61.37 ms  OVER
    N=1000   drain_med=   24.69 ms  under
    N=1500   drain_med=   51.88 ms  OVER
    N=1250   drain_med=   34.42 ms  under
    N=1375   drain_med=   43.39 ms  under
    N=1437   drain_med=   36.88 ms  under
    N=1468   drain_med=   41.27 ms  under
    BREAKING N (drain >= 50 ms) is between 1468 and 1500
```

**Breaking N is 1468 to 1500 callbacks** against the nominal 50 ms
budget, at 20 microseconds each. Against the 62.6 ms interval the
machine actually delivers, the same sweep puts it at about 2000: N=2000
measured 61.37 ms, which is the interval.

Breaking N is not one number. It is a hyperbola in per-callback cost,
and section 3.3 gives four points on it: 75819 callbacks at 0.66
microseconds, 8344 at 6, 1923 at 26, 644 at 78.

**The number that matters for this fleet.** Section 2 puts the steady
state at 1 to 27 callbacks per pump. Breaking on count alone needs 1468.
The fleet is two orders of magnitude away from that. Invert the
question instead: with 27 callbacks in the queue, each must average
50 / 27 = **1.85 ms** to exhaust the nominal budget, or 62.6 / 27 =
**2.32 ms** to exhaust the real one. With the floor case of 1 callback,
one handle costing 50 ms does it alone.

A `ScrummingBot.tick` continuation runs a whole synchronous stretch of
trading logic between two awaits, including indicator maths over
candles. Whether that stretch exceeds 1.85 ms is the question the next
unit must answer. This unit did not measure it: doing so needs a bot
ticking against real data, which would mean touching the live
application.

## 5. Synchronous I/O

### 5.1 The walker and its control

`pump_callgraph.py` walks from every coroutine handed to the pumped
loop by `create_task`, `ensure_future`, or `run_coroutine_threadsafe`.
Ten such roots belong to the live trading app; the rest belong to the
Simulator, the Nuclear controllers, and the stocks side.

Two oracle defects were found in the walker and fixed before its output
was believed.

The first version flagged `await exchange.fetch_ticker(...)` at
`src/trading/smart_orders.py:207` as synchronous. It is awaited, and
awaited exchange calls reach `CCXTConnector._call_sync`, which offloads
to a thread at `ccxt_connector.py:578`. That was a false positive.

The second version resolved `self.tick()` inside
`BotContainer._run_with_guard` to `BotContainer.tick`, which is the stub
that raises `NotImplementedError`. The walk stopped there and reported
ZERO sinks over 19 functions. A zero is a claim about the instrument.
Adding virtual dispatch took the walk to 119 functions and reached
`ScrummingBot.tick`.

The planted-defect control then ran on a copy of the tree:

```
plant A  scrumming_bot.py:5970  (inside ScrummingBot.tick, REACHABLE per baseline)
plant B  theme_engine.py:229  (inside generate_qss, UNREACHABLE per baseline)

--- baseline (unplanted) tree ---
  functions reached : 119
  sink call sites   : 1
--- planted tree ---
  functions reached : 119
  sink call sites   : 2
    src/trading/scrumming_bot.py:5970 requests.get()

--- VERDICT ---
  A reachable plant   REPORTED : True   (must be True)
  B unreachable plant REPORTED : False   (must be False)
  DISCRIMINATES               : True
```

Both plants are the same call. Only their reachability differs, so the
verdict tests reachability rather than text matching.

### 5.2 Every synchronous network call in the tree

Reachability alone would let a walker blind spot read as a clean tree,
so the whole population was inventoried separately by
`sync_net_inventory.py`. It found **19 synchronous network call sites**.

**Every one of the 19 sits in a plain `def`. Not one is inside an
`async def`, and not one is reachable from a coroutine the pump runs.**

| file:line | call | reached from |
|---|---|---|
| `src/trading/bot_container.py:2476` | `_ccxt_sync.fetch_ticker()` | `register` at startup, and the GUI |
| `src/trading/bot_container.py:2313` | `_ccxt_sync.fetch_balance()` | dead, see below |
| `src/gui/main_window.py:6740` | `_ccxt_sync.fetch_balance()` | `_connect_exchange_for_bot`, GUI slot |
| `src/gui/main_window.py:6798` | `_ccxt_sync.fetch_ticker()` | `_connect_exchange_for_bot`, GUI slot |
| `src/gui/main_window.py:3052` | `fetch_ticker()` | API tester tab |
| `src/gui/main_window.py:3054` | `fetch_balance()` | API tester tab |
| `src/gui/main_window.py:3058` | `fetch_ohlcv()` | API tester tab |
| `src/gui/main_window.py:3061` | `fetch_open_orders()` | API tester tab |
| `src/gui/main_window.py:3063` | `fetch_my_trades()` | API tester tab |
| `src/gui/bot_wizard.py:165` | `load_markets()` | wizard asset page |
| `src/gui/bot_wizard.py:174` | `fetch_tickers()` | wizard asset page |
| `src/gui/bot_wizard.py:407` | `load_markets()` | wizard extractor page |
| `src/gui/bot_wizard.py:420` | `fetch_tickers()` | wizard extractor page |
| `src/gui/preflight_check.py:103` | `load_markets()` | `check_symbol`, GUI |
| `src/gui/preflight_check.py:143` | `fetch_ticker()` | `check_symbol`, GUI |
| `src/exchange/ccxt_connector.py:457` | `load_markets()` | `sync_connect` |
| `src/exchange/api_validator.py:66` | `fetch_balance()` | credential validation |
| `src/core/trade_historian.py:423` | `fetch_my_trades()` | worker thread |
| `src/exchange/tablet_backend.py:358` | `fetch_ticker()` | tablet backend |

The brief names `_ccxt_sync.fetch_ticker` reachable from
`_usd_per_base_for`. That is correct: `bot_container.py:2476` sits in
`BotManager._usd_per_base_for` (`bot_container.py:2437`). But
`_usd_per_base_for` is a plain `def` with two callers, and neither is a
coroutine:

- `bot_container.py:2318`, inside `reconcile_capital_registry`, whose
  only caller is `reconcile_all_capital` (`bot_container.py:2359`),
  which **has no callers anywhere in the tree**. That path is dead, and
  with it the `fetch_balance` at `bot_container.py:2313`.
- `bot_container.py:2521`, inside `BotManager.register`
  (`bot_container.py:2493`), called from
  `restore_bots_from_state` (`bot_container.py:3873`) at startup and
  from `MainWindow._create_bot` (`main_window.py:7897`). Both run on
  the GUI thread, neither is a coroutine.

For the current fleet that call cannot fire at all.
`_usd_per_base_for` returns 1.0 at `bot_container.py:2467` when the
currency is dollar-pegged, and `DOLLAR_PEGGED_CURRENCIES`
(`bot_container.py:61-63`) contains both USD and USDC. All 37 live bots
are one or the other. The network line is unreachable for this fleet
and becomes reachable the moment a bot is created on a non-pegged base
currency.

### 5.3 What bounds each call

No direct `_ccxt_sync` call has an application-level timeout. The only
bound is ccxt's own, `"timeout": 30000` at `ccxt_connector.py:345`, so
30 seconds per call.

`sync_connect` (`ccxt_connector.py:454`) retries `load_markets()` three
times, so its worst case is 3 x 30 s = 90 seconds on the GUI thread.
Its pre-flight probe at `ccxt_connector.py:416` is separately bounded at
`timeout=15`.

By contrast the awaited path is bounded twice: ccxt's 30 s, plus
`asyncio.wait_for(fut, timeout=MEM_220_CALL_TIMEOUT_SEC)` with
`MEM_220_CALL_TIMEOUT_SEC = 25.0` at `ccxt_connector.py:57` and `:584`,
and it runs in an executor thread rather than on the GUI thread.

The answer to question 5 is therefore: **zero synchronous network calls
are reachable from a coroutine the pump runs.** The worst single
observed bound on the GUI thread is 90 seconds, at
`ccxt_connector.py:454-457` during connect. This is a real freeze
source on the same thread as the pump, but the pump is not the path to
it, and no pump change would fix it.

## 6. The heartbeat evidence

### 6.1 What the application records about itself

`main.py:1117-1120` writes `~/.acervator_logs/heartbeat.txt` every
2000 ms. `_write_heartbeat` (`main.py:454-460`) opens the file with
mode `"w"`.

**The file is overwritten on every beat, so no history exists.** The
application has not been keeping the freeze record the brief expects.
A gap can only be seen by watching the mtime while the app runs.

The out-of-process watchdog cannot supply it either.
`acervator_watchdog.py:68` sets `DEFAULT_STALL_SECONDS = 60`. The
watchdog is blind to everything under a minute, which is the entire
range the pump operates in.

Eight post-mortems exist in `~/.acervator_logs/`. Seven record a child
process death. One records a stall:

| directory | generated | cause |
|---|---|---|
| `postmortem_20260716_041033` | 2026-07-16T04:10:33 | heartbeat stalled for 20999.3 s |
| `postmortem_20260716_041034` | 2026-07-16T04:10:34 | heartbeat stalled for 20999.3 s |
| `postmortem_20260725_131123` | 2026-07-25T13:11:23 | child died, exit 1 |
| `postmortem_20260730_225834` | 2026-07-30T22:58:34 | child died, exit 1 |
| `postmortem_20260731_003502` | 2026-07-31T00:35:02 | child died, exit 1 |
| `postmortem_20260731_091444` | 2026-07-31T09:14:44 | child died, exit 1 |
| `postmortem_20260731_122612` | 2026-07-31T12:26:12 | child died, exit 1 |
| `postmortem_20260731_194435` | 2026-07-31T19:44:35 | child died, exit 3489660927 |

The single recorded stall is 20999.3 s, which is 5 hours 50 minutes.
That is not a pump drain. It is consistent with a stale heartbeat file
from an earlier run or with the machine sleeping, and the two entries
one second apart are the same event written twice.

The 1977 `faulthandler_*.log` files are NOT freeze evidence and must
not be read as such. `main.py:218` calls `faulthandler.enable()`, which
dumps on fatal signals only, never on a hang. 1524 of them are 92 bytes,
which is the header alone. Of the 27 larger than 1 KB, the ones
inspected are access violations inside pytest runs from development
sessions, not the trading application.

### 6.2 Live sampling of the running application

Since no history exists, the heartbeat was sampled directly.
`heartbeat_watch.py` calls `stat()` on the file every 50 ms and records
each advance of the mtime. It opens nothing, writes nothing, and never
touches the process.

The instrument carries a positive control. Before watching the live
file it runs the same gap logic against a scratch file it writes itself
every 2.0 s, with one deliberate 6.0 s stall planted in the middle:

```
--- SELFTEST (planted 6.0 s stall among 2.0 s beats) ---
    beats: 8
    median_gap_s: 2.001
    worst_gap_s: 6.001
    over_2_5s: 1
    planted stall DETECTED : True   (must be True)
    normal beats  ~2.0 s   : True   (must be True)
    INSTRUMENT VALID       : True
```

The watcher resolves a planted stall to within 1 ms and reports normal
beats at 2.001 s. A zero from it is now a statement about the
application rather than about the meter.

Two windows were sampled on the operator's running application, pid
11328, 37 live bots, on 2026-08-13.

| | 420 s window | 240 s window |
|---|---|---|
| beats observed | 180 | 98 |
| beats expected at 2.0 s | 210 | 120 |
| median gap | 2.004 s | 1.922 s |
| mean gap | 2.33 s | 2.45 s |
| p95 gap | 4.305 s | 4.362 s |
| worst gap | 4.436 s | 4.530 s |
| gaps over 2.5 s | 75 of 180 | 48 of 98 |

**The worst heartbeat gap observed is 4.530 s, at 2026-08-13T07:47:42.928.**
Over the 420 s window the worst was 4.436 s at 07:41:32.773.

The application is losing roughly one scheduled beat in five: 180 beats
arrived where 210 were due, and 98 where 120 were due.

The distribution is not a bell around 2.0 s. It is multimodal:

```
    gap histogram (0.25 s bins), 240 s window
       0.00s  ## (2)
       0.50s  ####### (7)
       0.75s  ################# (17)
       1.50s  ##### (5)
       1.75s  ################ (16)
       2.00s  ### (3)
       3.25s  ################### (19)
       3.50s  ##### (5)
       4.00s  ## (2)
       4.25s  ################# (17)
       4.50s  ##### (5)

    gaps under 2.5 s (timer kept up)   : 50
    gaps 3.5-5.0 s (one fire missed)   : 27
    gaps 2.5-3.5 s (timer ran late)    : 21
```

Gaps SHORTER than 2.0 s appear, which one 2000 ms timer cannot produce
alone. A second writer was the obvious explanation, so it was checked:
sampling content as well as mtime for 30 s found exactly one writer,
pid 11328. The short gaps are Qt serving a timer that was already
overdue, immediately after the thread frees up.

The raw sequence shows a repeating four-beat cycle of about 10 s:

```
    07:51:38.419
    07:51:42.606  +4.189
    07:51:44.413  +1.806
    07:51:47.732  +3.320
    07:51:48.447  +0.715
    07:51:52.731  +4.284
    07:51:54.412  +1.682
    07:51:57.649  +3.236
    07:51:58.399  +0.750
```

Long gap, then a short catch-up, repeating. That is the signature of
something periodically holding the GUI thread for seconds, not of a
timer running slow.

### 6.3 What does NOT explain the gaps

The obvious reading is that the pump drain causes these gaps. It was
tested and it does not.

`heartbeat_under_load.py` runs the real pair on one thread: a 50 ms
pump timer and a 2000 ms heartbeat timer, with the pump load swept.

```
  pump N  beats   median     mean     min     max  >2.5s
       0     13    2.000    2.000   1.988   2.009      0
     370     13    2.001    2.001   1.992   2.013      0
    1480     13    1.999    2.000   1.956   2.016      0
    2960     13    2.001    2.004   1.979   2.044      0
    5920     13    1.987    2.000   1.875   2.121      0
```

At N=5920 the drain is 141 ms, nearly three times the pump interval,
and the heartbeat still beats at 2.000 s with not one gap over 2.5 s.
**Queue depth does not delay the heartbeat.** However deep the ready
queue gets, each callback is short, and Qt gets the thread back between
drains.

Swapping many cheap callbacks for one expensive one changes the answer:

```
 cost_ms  beats   median     mean     min     max  >2.5s
     100     13    2.001    2.003   1.990   2.018      0
     500     13    2.070    1.999   1.566   2.244      0
    1500     13    1.550    1.994   1.505   3.050      4
    2500     11    2.525    2.535   2.512   2.559     11
```

At 1500 ms per callback the long-gap-then-short-catch-up signature
appears: minimum 1.505 s, maximum 3.050 s, four gaps over 2.5 s. That
is the shape the live application shows.

The conclusion this unit reaches, and the reason it matters to whoever
takes Item 11 next: **the live heartbeat gaps are consistent with a
periodic multi-second blocking stretch on the GUI thread, and are NOT
consistent with pump queue depth.** Section 4 reached the same place
from the other direction. The exposure is per-callback cost.

This unit did not identify which callback. Doing so needs a bot ticking
against live data, which would mean touching the running application.
The 10 s cycle and the 5.0 s `tick_interval`
(`scrumming_bot.py:3544-3545`) are a lead, not a finding.

### 6.4 Console-log gaps, a weak cross-check

`log_gaps.py` measured the interval between consecutive timestamped
lines across the 12 most recent console logs, 14865 gaps in total.
Median 6.0 ms, p99 6.53 s, 392 gaps over 2 s, 66 over 10 s, maximum
31494.7 s.

**This instrument is weak and the numbers above should not be quoted as
freezes.** Silence is not a stall: an idle application logs nothing
either. The 31494.7 s maximum is 8.75 hours and is plainly an overnight
idle period. The figures are an upper bound on responsiveness, nothing
more. They are recorded because they are the only historical record at
sub-minute resolution that exists at all.

## 7. Findings

Findings only. Nothing here was changed.

**F1. The selector loop choice is discarded.** `main.py:251` installs a
`SelectorEventLoop` on Windows. `main.py:1050` calls
`asyncio.new_event_loop()`, which returns a `ProactorEventLoop`, and
`main.py:1051` installs that instead. The v3.19.9 intent is not in
effect.

**F2. A capital-reconciliation path is dead.**
`BotManager.reconcile_all_capital` (`bot_container.py:2359`) has no
callers. It is the only caller of `reconcile_capital_registry`
(`bot_container.py:2280`), so the synchronous
`_ccxt_sync.fetch_balance()` at `bot_container.py:2313` and the drift
alerting below it can never run.

**F3. The heartbeat keeps no history.** `main.py:457` opens the file
with mode `"w"`. Combined with `DEFAULT_STALL_SECONDS = 60` at
`acervator_watchdog.py:68`, the application cannot record any stall
shorter than a minute, which is every stall the pump can cause.

**F4. `sync_connect` can hold the GUI thread for 90 seconds.**
`ccxt_connector.py:454-457` retries `load_markets()` three times with
no outer timeout, against ccxt's 30 s (`ccxt_connector.py:345`).

**F5. A non-pegged base currency arms a synchronous fetch at startup.**
`bot_container.py:2476` runs once per restored bot through
`restore_bots_from_state` (`bot_container.py:3873`). Today all 37 bots
short-circuit at `bot_container.py:2467`. One bot on a non-pegged base
currency puts a 30 s-bounded blocking call into the startup path.

**F6. The 50 ms pump timer fires every 62.6 ms.** `main.py:1109-1111`
never calls `setTimerType`, so the timer is a `Qt::CoarseTimer`.
Measured at every load in both shapes, and isolated by comparison
against `Qt::PreciseTimer`, which delivers 49.96 ms. Any later reasoning
that assumes a 50 ms period is wrong by 25 percent. The same applies to
the 2000 ms heartbeat timer at `main.py:1118-1120`.

**F7. The live heartbeat misses about one beat in five.** Measured on
pid 11328 over two windows: 180 beats where 210 were due, and 98 where
120 were due. Worst gap 4.530 s at 2026-08-13T07:47:42.928. Pump queue
depth is excluded as the cause by measurement, not by argument: a
141 ms drain at N=5920 produced zero gaps over 2.5 s.

## 8. The numbers a later unit is judged against

| quantity | value | how obtained |
|---|---|---|
| Pump interval, requested | 50 ms | `main.py:1111` |
| Pump interval, delivered | 62.6 ms | measured, all loads |
| Drain, empty queue | 0.113 ms plain, 0.034 ms task | measured, N=0 |
| Cost per callback | 20 us plain, 20-27 us task | measured, N=37 to 5920 |
| Scaling in N | linear | flat us/callback over 160x range |
| Ready callbacks per pump, 37 bots | 0.74 to 27.3 mean | static estimate |
| Ready callbacks per 5 s cycle | 74 to 2183 | static estimate |
| Breaking N at 20 us, vs 50 ms | 1468 to 1500 | bisection |
| Breaking N at 20 us, vs 62.6 ms | about 2000 | measured |
| Breaking N at 0.66 us | 75819 | measured |
| Breaking N at 78 us | 644 | measured |
| Per-callback cost that breaks 27 | 1.85 ms vs 50, 2.32 ms vs 62.6 | arithmetic |
| Paint budget at N=37 | 48.96 ms, 97.9 percent | measured |
| Paint budget at N=1480 | 20.43 ms, 41 percent | measured |
| Frame rate, unloaded | 69.7 fps | measured |
| Frame rate at N=1480 | 42.6 fps | measured |
| Frame rate at N=5920 | 15.2 fps | measured |
| Sync network calls in tree | 19 | AST inventory |
| Sync network calls in an `async def` | 0 | AST inventory |
| Sync network calls from a pumped coroutine | 0 | walk plus hand check |
| Worst GUI-thread bound | 90 s | `ccxt_connector.py:454-457` |
| Recorded stalls under 60 s | 0, and unrecordable | F3 |
| Live heartbeat, worst gap | 4.530 s at 07:47:42.928 | live sampling |
| Live heartbeat, mean gap | 2.33 s and 2.45 s | live sampling |
| Live heartbeat, beats lost | about 1 in 5 | live sampling |
| Drain depth needed to delay a beat | none found to N=5920 | measured |
| Callback cost that delays a beat | 1500 ms | measured |

A later unit that moves coroutines off the GUI thread should be able to
show: drain time on the GUI thread falling toward the N=0 floor of
0.113 ms, the paint budget holding above 48 ms under fleet load, frame
rate holding near 69.7 fps, the pump timer gap holding at its 62.6 ms
baseline rather than stretching, and the live heartbeat holding 2.0 s
with beats-lost at zero.

The last of those is the honest headline. The pump's queue depth is not
what hurts today: this fleet sits two orders of magnitude below the
breaking N, and a drain three times the tick interval still did not
delay a 2 s timer. What hurts is a single callback that holds the
thread for seconds, and the live heartbeat shows one doing so on a
roughly 10 s cycle.

Three things this unit could not settle, which a later unit must
measure rather than assume:

1. The real per-callback cost of a `ScrummingBot.tick` continuation
   against live data. Everything in section 4 turns on it.
2. Which callback holds the GUI thread on the observed cycle.
3. Whether the 1 to 27 steady-state callback count ever bunches toward
   the 2183 per-cycle ceiling.
