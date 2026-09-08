# ATA-SMP and the live detection path

**Mode: Explanation.** This page answers one question the operator asked on
7 September 2026. Can ATA-SMP detect a trade opportunity the way a live
Scrumming Bot does, and stay isolated from the streams the live bots use?

He asked whether a path through the live analytical system is possible. This
page measures the code and answers. It builds nothing and it changes no
product file.

The platform ran while this page took its measurements, with two Acervator
processes resident. Nobody started a second instance and nobody attached to the
running one. The last section names what that ruled out.

The module files on disk carry the spelling `ata_spm.py` and `ata_spm_push.py`
today. This page cites those filenames as they stand, so every citation
resolves. The feature is ATA-SMP.

## How a Scrumming Bot detects

Detection happens inside one method. The tick method of the bot class runs once
per bot per pass, reads the candles and the ticker, and ends either in an order
or in a list of refusals. It holds both gate chains as fields, built once when
the bot is new.

`src/trading/scrumming_bot.py` — the two chains the bot keeps

```python
self._scrum_chain = build_scrumming_scrum_chain()
self._fold_chain = build_scrumming_fold_chain()
```

### Where the indicator values come from

The bot calls one engine and nothing else. The engine runs twelve indicator
objects over the candle list and answers one summary.

`src/trading/scrumming_bot.py` — the only indicator read in the tick

```python
summary = self._voting_engine.compute_all(
    candles, ta_tf, symbol=self.config.symbol
)
```

One method in `src/trading/ta_engine.py` creates those twelve objects once and
the engine reuses them. Each object keeps its own periods and its weight, and
nothing else. Three modules show the same shape — the Bollinger, MACD and
Supertrend files under `src/trading/indicators/` assign periods and a weight in
the constructor, and no indicator carries a value from one call to the next.

Every value therefore starts in the candles the caller hands in. No indicator
reads a bot, a venue or a cache.

`src/trading/ta_engine.py` — the twelve, built once

```python
def _create_indicators(self) -> list:
    """Instantiate all indicator instances with configured weights."""
```

### The vote, and how it becomes a direction

The engine sums the weighted votes into a net score, then divides by the weight
of the voters that did not abstain.

`src/trading/ta_engine.py` — the two numbers the panel prints

```python
net = bull_score - bear_score
voted_weight = sum(s.weight for s in signals if not s.abstained)
consensus_conf = abs(net) / voted_weight if voted_weight > 0.0 else 0.0
```

A property on the summary type turns the net score into a direction, with a
deadband of plus and minus 0.1. Above it the panel reads bullish, below it
bearish, and inside it neutral.

`src/trading/indicators/types.py` — `VotingSummary.consensus_direction`

```python
if self.net_score > 0.1:
    return SignalDirection.BULLISH
elif self.net_score < -0.1:
    return SignalDirection.BEARISH
return SignalDirection.NEUTRAL
```

The bot then folds that direction and the confidence into one boolean per side,
against a floor. The floor starts at 0.25 and a skew relaxes it.

`src/trading/scrumming_bot.py` — `_skewed_confidence_floor`

```python
denominator = 1.0 + skew
if denominator <= 0.0:
    return math.inf
return floor / denominator
```

The skew sums three favours the tick already computed. A position boost comes
from four named voters. A second boost comes from the landing strip. A fixed
band-priority term of 0.30 arms when the price sits at a band and the delta and
the hysteresis both clear.

### Where Landing Strip Detection enters

Two detectors run, and they enter at two different points.

The first detector lives in `src/trading/indicators/bb_proximity.py`. The tick
calls it with the bot's own landing-strip candle setting as the shortest
pattern it will accept. Its result carries the strip, the side and the candle
count, and the side sets a direction flag outright.

`src/trading/scrumming_bot.py` — the strip overrides the vote

```python
if bb_result and bb_result.landing_strip and bb_result.landing_strip_side == "upper":
    is_bullish = True
if bb_result and bb_result.landing_strip and bb_result.landing_strip_side == "lower":
    is_bearish = True
```

The same result also raises the confidence boost, and it supplies a direction
when the panel reads neutral. The second detector sits in
`src/trading/indicators/landing_strip.py`, and the tick runs it once the tape
holds at least 25 candles. It adds its own boost and does nothing else.

`src/trading/scrumming_bot.py` — the second detector, and what it contributes

```python
tightening = detect_landing_strip_v2(
    candles,
    min_consecutive=3,
    shrink_threshold=0.90,
    bb_tolerance_pct=3.0,
)
if tightening and tightening.detected:
    bb_confidence_boost += tightening.confidence_boost
```

The strip therefore reaches the decision twice. Once it sets a side flag
directly, and once it lowers the floor the confidence must clear.

### The gate chain, in the order the bot evaluates it

The bot builds one context per side and hands it to the chain. The context type
carries 51 fields. The bot's tick method builds one in exactly two places, and
nothing else under `src/` builds one at all.

The sell side runs thirteen gates and one override.

`src/trading/gate_chain.py` — `build_scrumming_scrum_chain`

```python
gates=[
    DeltaPositiveGate(),
    IntervalGate(),
    TADirectionGate(side="scrum"),
    TrendHoldGate(),
    MidlineGate(side="scrum"),
    TargetFiresGate(),
    BBProximityGate(side="scrum"),
    CircuitBreakerGate(side="scrum"),
    HTFDeferGate(side="scrum"),
    HysteresisGate(side="scrum"),
    ADXTrendSuppressionGate(),
    EfficiencyRatioRegimeGate(),
    ZScoreExtremityGate(side="scrum"),
    RipeHarvestScrumOverride(),
]
```

The buy side runs nine gates and one override.

`src/trading/gate_chain.py` — `build_scrumming_fold_chain`

```python
gates=[
    TranchesQueuedGate(),
    TADirectionGate(side="fold"),
    MidlineGate(side="fold"),
    SmartCeilingGate(),
    BBProximityGate(side="fold"),
    CircuitBreakerGate(side="fold"),
    HTFDeferGate(side="fold"),
    HysteresisGate(side="fold"),
    ZScoreExtremityGate(side="fold"),
    DeepFoldOverride(),
]
```

That makes 22 gate positions across the two chains, from fifteen gate classes
and two override classes. The list order fixes the order the chain collects
refusals, which is the order the log prints them. Gate for gate this matches
what [07-indicators.md](../manual/07-indicators.md) records.

### How a gate latches, and what unlatches it

**No gate latches.** The chain's evaluate method builds a fresh pass list and a
fresh block list on every call, reads only the context handed in, and stores
nothing on itself. A gate class holds a name and a side. The chain recomputes
every gate from scratch on every tick.

What latches sits in the bot, and the gates read only the booleans the bot
publishes. Three fields hold across ticks: the hysteresis pivot armed at the
last trade, the circuit breaker trip, and the phantom timeframe lock. Each is a
field on the bot, which the arming event sets and the clearing event clears.

An override is the one thing that changes a verdict after the fact. It runs in
a second pass and rewrites a refusal rather than holding a state.

`src/trading/gate_chain.py` — `GateChain.evaluate`, the second pass

```python
for target_name in result.override_gates:
    if target_name in blocked_index:
        idx = blocked_index.pop(target_name)
        _name, _msg = blocked[idx]
        blocked[idx] = (_name, f"OVERRIDDEN_BY:{gate.name}({_msg})")
        overrides_applied.append(target_name)
```

### How the votes and the gates combine into a decision

Four routes carry readings into the chain, and they stay separate.

The collated vote reaches one gate. The TA direction gate reads the two
booleans the tick folded, and two strategy flags decide whether it may refuse
at all.

Three regime gates skip the vote and read one indicator's own number each. A
helper in `src/trading/scrumming_bot.py` pulls those numbers out of the summary
for the ADX gate, the efficiency ratio gate and the Z-Score gate. A reading of
zero or below marks the field as unpopulated, and all three pass on it.

The band position reaches four gates by the fourth route. Its thresholds come
from `src/trading/scrumming/circuit_breakers.py`, expressed in band positions
and never in prices.

The chain answers one boolean, and one refusal holds the trade.

`src/trading/gate_chain.py` — the verdict

```python
return ChainResult(
    should_fire=(not final_blocked),
    passed=passed,
    blocked=final_blocked,
    overrides_applied=overrides_applied,
)
```

### Where Opposing Trade Distance enters, and what reads it

The distance is one sum. It adds the bot's scrumming interval percentage to its
trading fee percentage, then clamps the result between 0 and 50.

`src/trading/otd_math.py` — `minimum_opposing_trade_distance_pct`

```python
total = float(interval_pct) + float(fee_pct)
return max(OTD_MIN_PCT, min(OTD_MAX_PCT, total))
```

Four places read it, and one of them decides a trade.

```
src/trading/gate_chain.py           HysteresisGate rebuilds the sum from the
                                    context to write its refusal message
src/trading/scrumming_bot.py        tick computes the percentage and the
                                    factor, and hands both to the fold
                                    diagnostics
src/trading/scrumming/execution.py  fold_rebuy_factor decides which tranche
                                    may be bought back
src/gui/live_settings/fold_tranches_tab.py   the Fold-Tranche panel shows the
                                    same number to the operator
```

One disagreement sits inside the tick, and this page records it without
repairing it. The tick computes the hysteresis pass or fail from the two config
values directly, and falls back to 0.036 when that read raises. The call into
the distance module in the same method feeds only the diagnostics, and it falls
back to 0.0. Two computations of one quantity therefore live in one method,
with different fallbacks and different clamping. Whichever unit next opens that
method owns this.

`src/trading/scrumming_bot.py` — the second computation, inside the tick

```python
_eff_hyst_pct = (
    float(self.config.scrumming_interval_pct)
    + float(getattr(self.config, "trading_fee_pct", 0.6) or 0.6)
) / 100.0
```

## The three options, measured

### The facts all three answer to

**The thread.** A Qt timer in `main.py` calls the pump function every 50
milliseconds, and that timer fires on the window-drawing thread. The whole
asyncio loop therefore advances on that thread. The bot container creates one
task per bot on that loop, and the main window schedules every other coroutine
onto the same loop.

`src/core/tick_driver.py` — one loop iteration per timer fire

```python
def pump_once(loop: asyncio.AbstractEventLoop) -> None:
    loop.call_soon(loop.stop)
    loop.run_forever()
```

Work that does not yield holds that thread for its whole duration. While it
holds, the window does not draw and no bot ticks.

**The venue.** The main window creates one connector per exchange and gives the
same object to the bot that trades there.

`src/gui/main_window.py` — one object, two consumers

```python
bot.exchange = connector
self._exchange_connectors[eid] = connector
```

The Market Inspector's exchange source reads that same dictionary. A scan that
fetches through it therefore spends the venue budget the bots place orders
with.

**What two callers may safely share.** The engine's compute method writes
nothing to itself, and the indicators keep nothing between calls, so two
callers cannot disturb each other's reading. The chain's evaluate method
behaves the same way. One process-wide channel exists inside the compute
method, the signal sink in `src/core/signal_contract.py`, and only simulator
files call its setter. The live run therefore leaves the sink unset and the
instrumentation short-circuits.

`src/trading/ta_engine.py` — the compute loop, which mutates nothing

```python
signals: list[Signal] = []
for ind in self._indicators:
    sig = ind.compute(candles, timeframe)
    signals.append(sig)
```

**What no bot shares.** The shared analyzer in
`src/trading/market_inspector.py` is a process-wide singleton the scan writes
to. Measured across `src/trading/` and `src/exchange/`, it has no reader beyond
its own definition. Every reader is a screen. A scan writing there cannot reach
a bot.

### Clone

ATA-SMP runs its own copy of the analytical stack. **The tree already does
this.**

`src/trading/ata_spm.py` — the run builds its own engine

```python
voter = engine if engine is not None else VotingEngine()
```

The run reads candles, votes, and stops at the vote. Its reversal test compares
the Bollinger voter's direction against the panel consensus, and it touches no
gate.

`src/trading/ata_spm.py` — `AssetVote.is_reversal`

```python
if self.direction == SignalDirection.NEUTRAL:
    return False
return self.band_direction == self.direction
```

**Isolation: real.** The run keeps its own engine, its own summary and its own
vote rows. No live bot reads any of it.

**Extends to stocks: yes.** The module already names crypto, stocks, metals,
derivatives and forex, and it answers a different timeframe set per class. The
engine reads candles alone, so a stock tape votes by the same arithmetic.

`src/trading/ata_spm.py` — the four timeframes each class carries

```python
CRYPTO_TIMEFRAMES = ("5m", "1h", "1d", "1w")
SLOWER_TIMEFRAMES = ("1h", "1d", "1w", "1M")
```

**The thread: wrong today, and that is the whole cost.** The board's scan
method calls the phase run straight through, with no await anywhere in it. Its
two callers are a Qt clicked slot and a bridge handler, and both run on the
window-drawing thread.

`src/gui/market_inspector.py` — the button, wired to a plain slot

```python
self._scan_now_btn.clicked.connect(self._on_scan_now)
```

The module's own throughput control does not protect that thread, because its
author sized it against a different budget. The budget function answers the
seconds of one candle of the shortest timeframe a class scans, which is 300 for
crypto. The support function divides that budget by the measured round cost. A
round costing 75 seconds still returns four timeframes, and a round costing 300
seconds still returns one.

`src/trading/ata_spm.py` — the budget, measured against candle age

```python
fits = int(scan_budget_s(asset_class) // cost)
return max(MIN_TIMEFRAMES_PER_ASSET, min(available, fits))
```

That budget asks whether the chart will still be fresh. It does not ask whether
the thread may be held. A scan sized to fit inside a five-minute candle is a
five-minute freeze on a thread that must return every 50 milliseconds.

**Verdict: possible, and only off the drawing thread.** The mechanism is
correct and its placement is not. As the tree stands, the clone falls to the
brief's own rule, because it puts analytical work on the thread that is the
measured root cause of the freeze class.

### Parallel

ATA-SMP runs beside the live stream, reading the same code rather than a copy.

For the vote this is sound. Both entry points are pure, so a second caller on
another thread reads the same arithmetic and touches no live bot. This option
also drops the second engine object the clone keeps, so a refinement to a voter
reaches the posts and the bots together.

For the gate chain it does not work, and the context is the reason. The context
type carries 51 fields. Candles and a price supply fourteen of them. Every
other field needs a bot that holds a position on that market.

```
delta, delta_pct, below_interval        a target balance and holdings
target_fires                            that bot's target ramp
hyst_ref_scrum_side, hyst_ref_fold_side pivot prices from that bot's trades
has_fold_tranches, n_fold_tranches      that bot's fold queue
cb_blocks_scrum, cb_blocks_fold         that bot's circuit breaker
mem253_at_ceiling and two beside it     that bot's position against its ceiling
scrum_ok                                the midline plus that bot's phantom lock
five strategy flags, two config rates   that bot's own configuration
```

A market ATA-SMP scans has no bot, so those fields hold no value to read. Only
invention can supply them, and an invented delta yields a gate verdict that
would print beside real ones and read as the platform's own.

No second door exists either. Both constructions of the context sit inside the
bot's tick method.

`src/trading/gate_chain.py` — what a context must carry before any gate runs

```python
delta: float  # current_value - target_balance
below_interval: bool  # delta_pct < scrumming_interval_pct
hyst_ref_scrum_side: float  # pivot price captured at arming
has_fold_tranches: bool
```

**Isolation: real, for the vote.** A live bot cannot observe anything the
second caller does, because neither entry point writes shared state.

**Cost to the live path: none, when it runs on its own thread over candles
already in hand.** A cost appears only when it fetches through the shared
connectors, which spends the venue budget the bots trade on.

**Extends to stocks: yes for the vote.** The gate half does not extend, because
`src/stocks/` carries no Scrumming Bot to own the state a context needs.

**Verdict: possible, for the twelve voters and the band position, on its own
thread. Not possible for the gate chain.**

### Live pipe

ATA-SMP's requests travel the live analytical system itself.

The live analytical system is the bot's tick method, and what that method is
settles the question. It is not a function of a symbol. It reads the bot's own
symbol, holdings, target, tranche queue, hysteresis pivots and breaker state,
it writes to all of those, and when the chain clears it places a real order.

`src/trading/scrumming_bot.py` — what the chain result reaches

```python
elif _scrum_chain_result.should_fire:
    await self._tick_execute_scrum(...)
```

Routing a scanned market's candles through a live bot's tick would move that
bot's own state, and it could send an order against the wrong tape. No
read-only entry exists, because the call that reads is the call that trades.

The thread makes it worse rather than better. Every bot already runs as a task
on the drawing thread, so a scan routed through a bot's tick lengthens that
tick, and 38 bots share the thread it lengthens.

**Isolation: none, and nobody can add it.** The pipe is per-bot mutable state
by construction.

**Extends to stocks: no.** It needs a live bot holding a position on every
market scanned, which is the opposite of scanning.

**Verdict: disqualified.** The live analytical path is the order path. A
request travelling it is a trade attempt, whatever anyone calls it.

## What the Trading tab would need

The Indicator Voting Panel draws twelve columns from one list, and today it
fills them from the summary of whichever bot the Bot selector names.

`src/gui/indicator_panel.py` — the first three of the twelve columns

```python
INDICATOR_COLS = [
    ("bollinger_bands", "BB", "S"),
    ("vortex", "VTX", "T"),
    ("macd", "MACD", "M"),
]
```

An ATA-SMP button would fill the same columns from the last vote the run
produced, for the symbol and timeframe that vote covered. The vote row already
carries everything the panel reads.

`src/trading/ata_spm.py` — `AssetVote`, the fields a panel needs

```python
direction: SignalDirection = SignalDirection.NEUTRAL
net_score: float = 0.0
confidence: float = 0.0
band_position: float = MIDLINE_POSITION
band_direction: SignalDirection = SignalDirection.NEUTRAL
signals: list = field(default_factory=list)
```

The signals list holds the same twelve signal objects the panel renders for a
bot, and Net, Comp and Conf come from the same aggregation. The twelve cells,
the two bar charts and the three totals would therefore carry identical
arithmetic.

**Would the two panels show the same numbers?** For the twelve voters, yes,
whenever both read the same vote row. The Market Inspector panel shows two
things the Trading tab panel has no column for: the phase readbacks, and the
timeframe agreement that phase eight produces.

**One column would stay blank, and it is the one that matters.** The live panel
sits beside a bot that has a gate chain result. An ATA-SMP vote has none,
because a market with no bot cannot fill a context. A button that showed gate
states for a scanned market would show invented numbers.

The proposal, if the button gets built:

```python
PROPOSED -- src/gui/indicator_panel.py

def show_ata_vote(self, vote) -> None:
    """Draw the twelve columns from one ata_spm.AssetVote.

    Hands the same twelve Signal objects to _populate_indicator_cell that
    a bot summary hands it, so both paths print one arithmetic.
    """
```

## Recommendation, and what it costs

**Take the parallel option, on its own thread, for the vote only.**

It gives the operator both things he asked for. ATA-SMP reads the same code the
live bots read, so refining a voter upgrades the posts and the trading at once,
and one arithmetic serves both. It isolates in fact and not only in appearance,
because neither the voting engine nor the gate chain writes state a second
caller could disturb. It reaches stocks, metals and forex with no change to the
engine, because the engine reads candles.

**The one thing it costs: the gate chain does not come with it.** A post can
say what the twelve voters said, at what net score and what confidence, and
where the price sits between the bands. It cannot say which gates latched and
which blocked, because that sentence needs a bot holding a position on the
market under scan. The issue names the gate results as the differentiator, and
this is the honest limit on that claim.

A second cost is smaller and immediate. The scan runs on the drawing thread
today, and moving it is work rather than a setting. Until it moves, pressing
Scan Now holds the thread that 38 bots tick on.

**Nobody can build the live pipe safely.** Engineering effort is not the
obstacle. The live analytical path is the order path, and no read-only way in
exists.

### What could not be measured

Nobody measured how long one compute call takes on this machine. The platform
was running with two resident processes, and the brief forbids a second
instance and forbids attaching to the running one. Every statement above about
the drawing thread therefore describes structure, not a measured number of
seconds.

That number matters for sizing a scan, and it changes no verdict here. Where a
synchronous call runs disqualifies it, not how long it takes.
