# The Patent Candidate Portfolio

Reference. Source: LEGACY, the fourteen-part manual, Part 2 "Patent Portfolio",
pages 5 to 51. [05-novel-concepts.md](05-novel-concepts.md) holds the operator's
own catalogue for this part. This file sits beside it and adds the legacy
entries. Nothing here replaces a sentence there.

The legacy part catalogues 26 numbered inventions. The claim audit in
[docs/audits/manual-original-parts-audit.md](../audits/manual-original-parts-audit.md)
scored 19 of its 30 checkable claims ANCHORED, the highest share of any legacy
part. Seventeen inventions carry forward. Two carry with a corrected constant.
Seven do not carry, and the reason for each appears at the foot of this file.

Each entry below names the module and the symbol behind it. Where the mechanism
exists but nothing calls it, the entry says so.

## The seventeen that carry

### Speculative scrumming

A position opens against a dollar target. When price rises, the bot sells the
excess above the target. When price falls, the bot buys back more units for the
same dollars. Each completed cycle ends holding more of the asset. The target
grows on a profitable close rather than the position closing out.

The loop runs in `ScrummingBot` in `src/trading/scrumming_bot.py`, with the tick
phases in `src/trading/scrumming/tick_phases.py`. `scrumming_interval_pct` in
`src/trading/container/config.py` sets the minimum price move between two
actions, and defaults to 1.0 percent.

### Phantom balance

The bot copies its own position onto longer timeframes and reads those copies as
a bias check. A phantom never places an order. It answers one question: what
would this position look like on the slower chart.

`src/trading/phantom_balance.py` holds the copies.
`ScrummingBot.DEFAULT_PHANTOM_TIMEFRAMES` at `src/trading/scrumming_bot.py:313`
carries six entries: 5m, 15m, 30m, 1h, 4h and 1d. The legacy manual describes
two copies in one place and three in another; six is the measured default.

### Landing strip detection

A Bollinger Band touch on its own is a weak signal. The landing strip asks for a
second thing: several tight Heikin-Ashi candles resting against the band. The
consolidation is the confirmation.

`detect_landing_strip_v2` in `src/trading/indicators/landing_strip.py` returns
the detection, with `TighteningResult` carrying the measurement.
`bb_landing_strip_candles` in `src/trading/container/config.py` sets how many
consecutive candles the strip needs, and defaults to 3.

### Band travel detection

A fixed percentage threshold means two different things in a quiet market and a
violent one. Band travel measures the move as a fraction of the current
Bollinger Band width instead, so the threshold follows the volatility.

`band_travel_pct` in `src/trading/container/config.py:100` defaults to 70. The
band arithmetic itself is in `src/trading/indicators/` and the panel maths is in
[07-indicators.md](07-indicators.md).

### The mean-reversion inspector

A z-score watcher runs in the background. It never opens a trade of its own. It
reports how far price sits from its own mean, and the fold reads that reading.

`src/trading/mr_inspector.py` holds the watcher and
`src/trading/indicators/zscore.py` holds `ZScoreIndicator`.
`ZScoreExtremityGate` in `src/trading/gate_chain.py` is the gate that consumes
the same value, and it blocks symmetrically at plus and minus 2.0.

The z-score reading reaches the gate. The inspector itself does not run in the
crypto path: an `ast.Call` scan across 383 files under `src/`, `main.py`,
`dev_harness/` and `tools/` finds one construction of `MRInspector`, at
`src/stocks/stock_accumulation_bot.py:136`, and the 223-file import closure of
`main.py` does not hold `mr_inspector.py`. The positive control on the same
scan returns five call sites for `ScrummingBot`; three coined names return
zero. `src/gui/live_settings/market_inspector_tab.py:33` records the same
finding in a comment: no caller wires `ScrummingBot._mr_inspector`.

### Smart wire

Profit from one bot can travel to another bot along a declared channel, and the
channel records where the money came from. Every unit of capital keeps its
origin.

`src/trading/smart_wire.py` holds the network.
`src/trading/scrumming/wire_routing.py` routes a fill along it, and
`wire_inflow_stack_pct` in `src/trading/container/config.py` sets how much of an
inflow a bot stacks onto an open position.

### Proof of accumulation

A trading tournament where a competitor proves what it accumulated without
showing how. Entrants commit to their trades in advance as hashes and reveal at
the end.

`src/trading/poa_tournament.py` holds 16 classes, among them `Season`,
`Participant`, `RoundResult`, `Tournament` and `TournamentEngine`.
`src/competition/` holds the on-chain side, with chain ids and contract
addresses.

Nothing calls any of it. The `ast.Call` scan over 383 files returns zero call
sites for every public symbol in `poa_tournament.py`, the module sits outside
the 223-file import closure of `main.py`, and no test references it either. The
tournament is written and it does not run. [08-tabs.md](08-tabs.md) and
[08-tabs/proof-of-accumulation.md](08-tabs/proof-of-accumulation.md) record the
state of the screen.

### The provenance fold queue

Each buy stays its own lot with its own cost basis. Averaging never merges them.
When the fold fires, the bot picks the lots whose own basis makes them worth
buying back, and leaves the rest alone.

`self._fold_tranches` and `_fold_eligible_tranches` in
`src/trading/scrumming/tick_phases.py` hold and filter the lots. Each lot
carries an `initial_buy_price` key, which is the basis the fold compares
against.

### The entry-price conservation cap

Target growth stops at a ceiling tied to what the held units cost, so the target
stays recoverable when price falls back to entry.

`apply_profit_fold` in `src/trading/profit_fold.py` implements it: the growth
scales by `min(price, entry_price) / price`, and `portfolio_value * 0.995` caps
the new target. The module's own docstring states that no module in this
repository imports `apply_profit_fold`. The mechanism exists and no production
caller reaches it. Read the entry as a design that is written, not as behaviour
that runs today.

### The tier-four signal suite

Signals sort into tiers rather than stacking flat. A structural signal can open
a trade. A contextual signal can only move confidence.

The twelve voters and their weights live in `VotingEngine._create_indicators`
in `src/trading/ta_engine.py`, and the weights run from 0.8 to 1.2 for a total
of 11.7. [07-indicators.md](07-indicators.md) carries the published formula for
each one and the departures the code takes.

### Fair value gaps as fold magnets

A gap between non-adjacent candles marks a price the market skipped. The bot
treats an unfilled gap as a level that draws the fold toward it.

`FVGIndicator` in `src/trading/indicators/fvg.py` finds the gaps and tracks
whether each one has filled. `src/trading/indicators/__init__.py` and
`src/trading/ta_engine.py` both re-export it, and the `INDICATOR_MODULES` map
names it, so the module sits inside the import closure of `main.py`. The
`ast.Call` scan finds no construction of `FVGIndicator` anywhere in `src/`,
`main.py`, `dev_harness/` or `tools/`, and nothing in `src/` reads
`INDICATOR_MODULES`. The class is imported and never built.

### Multi-timeframe regime bias

When the slower timeframe disagrees with the faster one, the faster entry waits.
The suppression is a hard refusal, not a confidence discount.

`HTFDeferGate` in `src/trading/gate_chain.py` carries it, and it sits in both
chains: `htf_defer_scrum` on the sell side and `htf_defer_fold` on the buy side.
`scrum_defer_to_htf` and `fold_defer_to_htf` in
`src/trading/container/config.py` both default to `True`.

### The initial-purchase-price floor

Every unit bought back after a fold costs at or below what the lot originally
cost. If price sits above that floor, the rebuy waits.

The test runs in `src/trading/scrumming/tick_phases.py`:
`ticker.last <= float(_t.get("initial_buy_price", ...))` decides whether a
tranche is eligible, and the hold message names `initial_buy_price floor` as the
binding gate when price sits above the cheapest lot. This is the invariant the
legacy Part 5b charts report as holding on 78 of 78 simulations; that battery
has no source here, and [FIGURES.md](FIGURES.md) records the figure and its
absent producer.

### The fire-window override

Normal discipline blocks a harvest above the band midline. The override lets the
bot act anyway when the profit is large and price already sits at the opposing
band extreme, because the band geometry alone justifies the trade.

`_ripe_scrum` and `_deep_fold` in `src/trading/scrumming_bot.py` hold the two
sides. `_bb_detect_thresholds()` in
`src/trading/scrumming/circuit_breakers.py:243` derives the band trigger from
`scrum_detect_pct`, which defaults to 75 and yields a band pair of 0.125 and
0.875.

### The initial-entry discipline gate

A bot holding none of the asset clears the same gates as a loaded bot before its
first buy. No looser path exists for the first entry.

The buy-side chain is `build_scrumming_fold_chain()` in
`src/trading/gate_chain.py:619`, and it runs the same ten gates whatever the bot
holds. `MidlineGate`, `BBProximityGate`, `TADirectionGate` and
`CircuitBreakerGate` are the four that decide entry geometry and consensus.

### The ripe-harvest and deep-fold overrides

The two overrides are deliberately asymmetric. Claiming profit asks for more
conviction than buying a dip does, because a premature harvest gives up the
compounding the target growth would have earned.

`RipeHarvestScrumOverride` and `DeepFoldOverride` in
`src/trading/gate_chain.py` are the last entry in their chains, and both run in
a second pass after every regular gate has been evaluated. The chain evaluates
every gate with no short circuit, so the blocker list is the exact inverse of
the fire decision.

### The position ceiling and detonation

Two paired controls. The ceiling caps how far the position may grow above a
fixed anchor. Detonation watches a slower timeframe and, on a strong reading,
sells everything above the anchor and resets.

`SmartCeilingGate` in `src/trading/gate_chain.py` enforces the ceiling, and
`position_ceiling_enabled` and `position_ceiling_multiple` in
`src/trading/container/config.py` configure it, defaulting to `False` and 5.0.
`ScrummingBot._check_detonation_trigger` at
`src/trading/scrumming_bot.py:4265` reads
`summary.consensus_direction == SignalDirection.BULLISH` against
`detonation_confidence_min`, default 0.75, and fires on the rising edge.

## The two that carry with a corrected constant

### The full-override fire window

The legacy entry gives a band trigger of 0.80 and a fixed delta trigger of 10
percent. Neither number is in the code. `_bb_detect_thresholds()` in
`src/trading/scrumming/circuit_breakers.py` derives the band trigger from
`scrum_detect_pct` and returns 0.875 at the default of 75. Driving that field
across its range returns (0.25, 0.75) at 50 and (0.05, 0.95) at 90, so the value
is configurable rather than constant. The delta trigger reads the bot's own
`scrumming_interval_pct`.

### Position-aware technical analysis

The legacy entry names a `sign_context` multiplier that downweights a signal the
band position contradicts. That identifier has never existed here. Band-position
gating itself is real: `BBProximityGate` in `src/trading/gate_chain.py` reads
`bb_pos` and blocks in both chains. Carry the idea, drop the named multiplier.

## The seven that do not carry, and the proof

Each name below was probed with the identifiers the legacy manual itself
supplies, over every commit on every ref. The positive control on the same
instrument returns `src/core/log_paths.py`; the negative control on a coined
name returns nothing.

| Invention | Identifier probed | Result |
| --------- | ----------------- | ------ |
| Hunger Index | `hunger`, `max_hunger` | never in any Python file |
| Satiety Index | `satiety` | never in any Python file |
| Shadow Secondary Add | `shadow_secondary` | never in any Python file |
| Charge-Up Permission Gate | `charge_up`, `chargeup` | never in any Python file |
| Spectre bot | `spectre` | never in any Python file |
| Spectre scrum skipping | `spectre` | never in any Python file |
| Spectre inverse philosophy | `spectre_reserve` | never in any Python file |

Shadow Secondary Add names one real thing inside a mechanism that does not
exist: its trough test reads `bb_pos`, which `BBProximityGate` also reads. The
name being real does not make the mechanism real.

The three Spectre entries carry the whole of the legacy Part 5c with them.
[FIGURES.md](FIGURES.md) records both of that part's figures, and
[14-development-chronicle.md](14-development-chronicle.md) records what the
absence means for the evidence chain.

## Where the supporting numbers went

Every evidence block in the legacy part attributes its figures to a simulation
battery. No engine of that name has any source in this repository. The claim
scopes and the equations carry; the numbers beside them do not.

Six legacy figures carry those numbers, four in Part 5b and two in Part 5c.
[FIGURES.md](FIGURES.md) holds a row for each, with its digest and its pixel
size. What each one shows, and what it is worth:

- **Outcomes by regime.** 41 bull wins, 17 bear wins against 4 losses, and 16
  sideways wins. The bars total 78. The same part defines its universe as 26
  assets across 3 periods, which would put 26 runs in each regime, and the chart
  shows 41, 21 and 16. The figure contradicts its own part's universe.
- **Median advantage by regime.** $2,300,000 in the bull regime, $5,625 in
  sideways and $180 in bear — a spread of four orders of magnitude, drawn on a
  log axis, produced by an instrument this repository does not hold.
- **Price-floor compliance.** 78 runs hold the floor and none violate it. The
  floor is real and runs today, in `src/trading/scrumming/tick_phases.py`. The
  78 is not reproducible here.
- **Charge-up fee economics.** $214 of average fees unbundled against $87
  bundled. The gate this figure measures is one of the seven with no code:
  neither `charge_up` nor `chargeup` has ever appeared in a Python file. The
  chart measures a mechanism that does not exist here.
- **The two bear-regime accumulator figures.** One compares units held on the
  same $100 of capital, 0.002175 against 0.003918. The other draws a three-year
  lifecycle with a spawn threshold, an explode threshold and a shaded
  accumulation band. Both illustrate the subsystem whose identifier has never
  appeared in any Python file. The second is a schematic rather than a tape: its
  price line holds flat for sixteen months and then steps almost vertically, and
  its spawn marker sits far below the spawn threshold it marks.

The figures are carried because the operator's instruction is that everything
goes in and nothing is dropped. Each is carried with its producer named as
absent, which is the only honest way to carry a number nothing here can
regenerate.
