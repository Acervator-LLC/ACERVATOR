# Kaufman Efficiency Ratio: the number the gate reads

**Mode: Reference.**

Issue #414 item 2. The item names `+ 1e-9` on a denominator a guard four lines
above has already proved positive. That expression is not in this tree: commit
`e8843729` removed both copies of it on 2026-09-04 and `0ebbde8d` merged that to
`current` on 2026-09-05, a day after the issue was filed. The division is bare
and the module abstains where the window never moved, which is the published
reading of 0/0.

What the item is about survives the epsilon. The ratio the Efficiency Ratio
Regime gate compares against 0.05 and 0.70 was not the published ratio. It was
the published ratio cut to four decimal places, and that is what this unit
repairs.

Every run used a throwaway home. `~/.acervator/settings.json` hashed the same
before and after:

```
before  18D380C7134DADBB2ACBF5CBE5527EA177FE8B23CC77EB3FFF6334FB03FEEAC8
after   18D380C7134DADBB2ACBF5CBE5527EA177FE8B23CC77EB3FFF6334FB03FEEAC8
```

## The error

Kaufman, Smarter Trading (1995), reproduced by StockCharts on the KAMA page:

```
ER         = Change / Volatility
Change     = ABS(Close - Close 10 periods ago)
Volatility = Sum10(ABS(Close - Prior Close))
```

`KaufmanERIndicator.compute` computes exactly that. It then published the
result rounded to four decimals, and the rounded copy is the only one any
consumer can reach.

`src/trading/indicators/kaufman_er.py` — the reading, before

```python
details={
    "er": round(er, 4),
    "er_prev": round(er_prev, 4),
```

## Reproduction

Seventy-one recorded Coinbase tapes from `~/.acervator_ra_tablets`, read-only,
each rescaled so the last close sits at 3.1e-06 and again at 1234.0. Every
window from bar 60 to the end ran through `VotingEngine().compute_all`, and the
reading it published went into a `GateContext` whose other fields all pass. The
chain is the real one, `build_scrumming_scrum_chain()`.

The pre-repair tree is a real checkout, not a copy:

```
git worktree add --detach <path> origin/current
```

```
37,380 readings, 71 tablets, two price scales
the number the gate reads moved on 37,331 of them
    3.1e-06        18,667 of 18,690
    four figures   18,664 of 18,690
the gate changed its verdict on 5
```

## The cause

`round(er, 4)` quantises the ratio to steps of 0.0001. The gate's two
thresholds sit inside that step, so a ratio within 0.00005 of 0.05 or 0.70
lands on the threshold and the gate reads it as touching the boundary. A ratio
within 0.00005 of zero lands on 0.0, which `GateContext.efficiency_ratio`
documents as the not-populated sentinel, so a genuine no-edge reading passed
the gate as though the indicator had never spoken.

Three parts of the platform build that gate input from the same detail:

```
src/trading/scrumming_bot.py:3637   the live bot's tick
src/simulator/back_test.py:334      the Simulator's back test
src/trading/ata_gate_scan.py:644    the ATA gate scan
```

Four more read it for display and each cuts it themselves, so none of them
shows a different number after the repair:

```
src/gui/indicator_panel.py:1911                    .2f
src/gui/main_tabs/indicator_panel_surface.py:412   .2f
src/gui/main_tabs/indicator_panel_surface.py:429   .3f, the hover text
src/trading/ata_spm.py:140                         .4f, the ATA-SMP sentence
```

## The correction

The reading carries the ratio the module computed.

`src/trading/indicators/kaufman_er.py` — the reading, after

```python
details={
    "er": er,
    "er_prev": er_prev,
```

## The rerun

### The new code is reached by the running program

Broken inside the indicator under pdb, entered the way the bot and the ATA gate
scan enter it. The stack is the proof: the frame is reached from the voting
engine, not from a direct call.

```
python -X dev -m pdb -c "b <repo>/src/trading/indicators/kaufman_er.py:85" \
  -c c -c where -c "p net_change, price_travel, er, round(er,4)" -c q \
  <script> <repo> <tablets>
```

```
u414ker_pdb_entry.py(30)<module>()
-> summary = VotingEngine().compute_all(candles, "1h")
  src/trading/ta_engine.py(247)compute_all()
-> sig = ind.compute(candles, timeframe)
> src/trading/indicators/kaufman_er.py(85)compute()
-> return Signal(
(1.258507462686566e-07, 2.516486140724949e-06, 0.05001050640890935, 0.05)
```

DOGE 2025 at bar 264, rescaled to 3.1e-06. The published ratio is
0.05001050640890935 and the number the gate read was 0.05.

### The gate's verdict, both trees, the same bars

Two arms on each row. The first carries the real ADX and Z-Score off the same
summary; the second sets both to their own not-populated sentinels, so
`should_fire` follows the Efficiency Ratio gate alone. `adx_trend_suppression`
blocks on all eight rows in the first arm, which is a fact about these bars and
not about this change.

A reading that crosses 0.05:

```
DOGE_1d_2025_coinbase.json  bar 264  3.1e-06 and four figures
  before  er 0.05                   efficiency_ratio_regime BLOCKS  fire False
  after   er 0.05001050640890935    efficiency_ratio_regime passes  fire True
```

A reading that does not cross:

```
DOGE_1d_2025_coinbase.json  bar 263  3.1e-06 and four figures
  before  er 0.2257                 efficiency_ratio_regime passes  fire True
  after   er 0.2256565656565654     efficiency_ratio_regime passes  fire True
```

The sentinel, which moves the other way:

```
ETH_1d_2025_coinbase.json   bar 233  3.1e-06 and four figures
  before  er 0.0                     efficiency_ratio_regime passes  fire True
  after   er 2.983774235682565e-05   efficiency_ratio_regime BLOCKS  fire False
```

Five verdicts moved across the whole sweep: three of the first shape, two of the
third. The rounding both suppressed a scrum the published ratio allows and
allowed one the published ratio refuses.

### The two price scales

The ratio is a price divided by a price, so it carries no scale of its own and
the repair is not a scale repair. Every row above reads the same at 3.1e-06 and
at 1234.0 to within the last few bits, and the 0.05 crossing at bar 264 happens
at both.

```
3.1e-06        0.05001050640890935
four figures   0.05001050640890904
```

### Nothing else moved

Twelve voters read back over one tape at 88 bars of each price scale, every
field of every reading compared: direction, confidence, weight, the abstention
flag and each detail.

```
readings compared  1056
differing          kaufman_er, 88
identical          adx  bollinger_bands  ichimoku  macd  rsi  slingshot
                   stochastic_rsi  supertrend  volume  vortex  zscore
```

The compare carries its own control: one reading altered by a single character
in the recorded dump is reported as one difference, so a compare that saw
nothing would be reporting on itself.

### Every reader, both trees, the same bar

```
                      before                     after
gate context field    0.05                       0.05001050640890935
ATA-SMP sentence      efficiency ratio 0.0500    efficiency ratio 0.0500
panel cell text       '- 0.05'                   '- 0.05'
panel hover text      er: 0.050                  er: 0.050
```

Three of the four are identical, so no pixel changes and no GUI file is touched.

## Checks run

```
python -m dev_harness.harness.coding_archetype  src/trading/indicators/kaufman_er.py
python -m dev_harness.harness.ta_archetype      src/trading/indicators/kaufman_er.py
python -m dev_harness.harness.docs_archetype    docs/manual/07-indicators.md
python -m tools.local_ci --lane black
python -m tools.local_ci --lane flake8
```

## Named, not changed

`ta_invariants.py` holds `er` inside 0 and 1, and that still holds: the
numerator is one absolute difference and the denominator is a sum that includes
it.

The manual's departures list names two remaining readings, the Vortex overwrite
and the RSI rounding. Both belong to later units of issue #414 and neither is
touched here.
