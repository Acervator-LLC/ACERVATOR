# Indicator rounding: the reading published is not the reading computed

**Mode: Reference.**

Issue #414 item 6, and the rounding the eight items turned out to share. The
two epsilons item 6 names are already gone from this tree. What remains is a
cut applied where the number is computed rather than where it is shown.

```
71 recorded Coinbase tapes, windows from 36 bars, two price scales
    3,750 readings, 30,000 gate verdicts
        round(...) calls in src/trading/indicators/       53 removed, 0 kept
        band half-span exactly 0.0 at 3.1e-06      before 1,014 of 1,855
                                                    after 0 of 1,875
        band refused outright at 3.1e-06           before 20, after 0
        target_fires disagreeing between scales    before 162, after 0
        gate verdicts changed                             58
            scrum refused -> scrum fires                  50
            scrum fires -> scrum refused                   8
            fold verdicts changed                          0
            changed verdicts at 1234.0                     0
        vote direction moved                               0
        panel consensus direction moved                    0
        ta_invariants breaches, before and after           0
    non-numeric readings compared                    339,170
        moved                                              0
        dropped                                            0
        added                              3,750 mfi_rising
```

Every run used a throwaway home. `~/.acervator/settings.json` hashed the same
before and after.

```
before  18d380c7134dadbb2acbf5cbe5527ea177fe8b23cc77eb3fff6334fb03feeac8
after   18d380c7134dadbb2acbf5cbe5527ea177fe8b23cc77eb3fff6334fb03feeac8
```

## The error

John Bollinger's bands, as StockCharts reproduces him. One middle line and two
edges, each an ordinary price in the asset's own units.

```
Middle Band = SMA(period)
Upper Band  = Middle + std_dev * sigma(period)
Lower Band  = Middle - std_dev * sigma(period)
BandWidth   = (Upper - Lower) / Middle
```

Nothing in the publication fixes the number of decimal places a band carries. A
band on an asset at four figures and a band on an asset at three millionths of
a dollar are the same formula over different units.

`src/trading/indicators/bollinger.py` on `origin/current` cut all three to six
decimals before publishing them.

```python
details={
    "upper": round(upper, 6),
    "middle": round(mid, 6),
    "lower": round(lower, 6),
```

Six decimals is a step of one millionth of a dollar. BONK trades at 3.1e-06, so
the whole channel is narrower than the step, and the three bands land on the
same number.

The same cut sits on every other indicator in that folder: fifty-three calls
across thirteen files, on band prices, cloud edges, the Supertrend line, the
Z-Score, the money-flow ratio, the Stochastic lines and the vote strength.

Two statements in the folder compute a value and bind it to nothing.

```python
src/trading/indicators/ichimoku.py    not above_cloud and not below_cloud
src/trading/indicators/volume.py      mfi > mfi_prev
```

The two epsilons item 6 names, `price + 1e-9` in the Ichimoku and
`st_line + 1e-9` in the Supertrend, were removed on 2026-09-04 by commit
`b27c6cdb`. That is the eighth item of eight whose named expression had already
been repaired and whose surviving defect was a rounded copy reaching a reader.

## Reproduction

Seventy-one recorded Coinbase tapes from `~/.acervator_ra_tablets`, read-only,
each rescaled so the last close sits at 3.1e-06 and again at 1234.0. Every
window from 36 bars in steps of 11 ran through the real voting engine, and each
summary built a gate context through the shipped scan so the readings reach the
chains the way an ATA scan reaches them. Both chains ran on all four states of
the two direction switches.

The pre-repair tree is a real checkout, not a copy.

```
git worktree add --detach <path> origin/current
```

The band half-span is the distance from the midline to the edge the ramp
measures against. At 3.1e-06 it read exactly zero on 1,014 of the 1,855
windows that published a band at all, and on a further 20 windows the lower
band rounded to zero and the scan refused the channel outright. At 1234.0 it
read zero on none of 1,875 and never fell below 7.76.

That pair is the control. The same instrument, the same windows, the same code
— one price scale reports a zero on more than half the windows and the other
reports none, so the instrument is known able to report a non-zero span.

## The cause

A band price is cut where it is computed, and the consumer downstream divides
by what is left of it. The scan's ramp reads the published band, takes the
midline-to-edge span, and asks how far the price has travelled across it.

`src/trading/ata_gate_scan.py` — the ramp step that decides `target_fires`

```python
middle = band[BAND_MIDDLE_KEY]
edge = band[BAND_UPPER_KEY] if price > middle else band[BAND_LOWER_KEY]
span = max(abs(edge - middle), BAND_SPAN_FLOOR)
travel_frac = abs(price - middle) / span
```

`BAND_SPAN_FLOOR` is 1e-12. When the published span is zero the floor takes
over, `travel_frac` becomes an enormous number, and the ramp walks a different
path than the same market at a larger price would.

Measured at the frame, entered the way a bot tick enters it.

```
python -X dev -m pdb \
  -c "b <repo>/src/trading/indicators/bollinger.py:140" -c c -c where \
  -c "p upper, mid, lower" -c "p upper - lower" \
  -c q u414round_entry.py <repo> ~/.acervator_ra_tablets
```

```
  u414round_entry.py(48)<module>()
-> summary = VotingEngine().compute_all(candles, "1d", "DOT-USD")
  src/trading/ta_engine.py(247)compute_all()
-> sig = ind.compute(candles, timeframe)
> src/trading/indicators/bollinger.py(140)compute()
-> return Signal(

DOT 2023, 342 bars, rescaled to 3.1e-06
  the locals, both trees   2.8970884453749354e-06
                           2.494883805904706e-06
                           2.092679166434477e-06
  published, origin/current   3e-06   2e-06   2e-06   span 1.0000000000000002e-06
  published, this tree        the locals                span 8.044092789404584e-07
```

The stack is the proof of reach: the frame is entered from the voting engine,
not from a direct call. On `origin/current` the computed span is 8.04e-07 and
the published span is 1.0e-06, two and a half times too wide.

At 102 bars of the same tape the three bands collapse completely.

```
DOT 2023, 102 bars, rescaled to 3.1e-06
  origin/current   upper 2e-06   middle 2e-06   lower 2e-06   half-span 0.0
  this tree        upper 2.4790939509515373e-06
                   middle 2.3508144355035356e-06
                   lower 2.222534920055534e-06
                   half-span 1.2827951544800168e-07
```

The two bare statements have no reader at all. Their values are computed and
dropped, so no comparison of two trees can see them and only reading the file
finds them.

## The correction

Every cut in `src/trading/indicators/` moves to the point of display. Fifty-three
calls removed, none kept. Each published reading is now the number the formula
produced.

`src/trading/indicators/bollinger.py` — what the reading carries

```python
details={
    "upper": upper,
    "middle": mid,
    "lower": lower,
    "bb_position": bb_pos,
    "band_width": band_width,
```

Nothing on a screen loses its shape, because every display already applies its
own format. The panel hover cell prints three decimals, the bot log line prints
four, and each confirming sentence in the ATA-SMP carries its own width.

`src/trading/ata_spm.py` — one voter's sentence, formatted where it is shown

```python
"bollinger_bands": (
    "Bollinger Bands",
    (BAND_POSITION_KEY,),
    "band position {value:.4f}",
),
```

The Ichimoku statement becomes the binding the reading beside it already uses.
The cloud has three states and the code named two of them.

```python
inside_cloud = not above_cloud and not below_cloud
```

The published reading now reads that binding instead of deriving the same
answer a second time, so one expression decides the state.

```python
"price_vs_cloud": (
    "inside" if inside_cloud else "above" if above_cloud else "below"
),
```

The volume statement becomes the money-flow slope, published beside the
balance-volume slope the same module already publishes.

```python
mfi_rising = mfi > mfi_prev
```

The thresholds are untouched. No gate demands anything different; the numbers
handed to the gates are the computed ones.

## The rerun

### The band at BONK's scale

```
1,875 windows at 3.1e-06
    half-span exactly 0.0        before 1,014      after 0
    half-span under 1e-12        before 1,014      after 0
    smallest half-span           before 0          after 1.95022e-08
    band refused outright        before 20         after 0
1,875 windows at 1234.0
    half-span exactly 0.0        before 0          after 0
    smallest half-span           before 7.76315    after 7.76315
```

### The ramp, at the two price scales

```
1,875 windows, target_fires compared between 3.1e-06 and 1234.0
    before   agree 1,713   disagree 162
    after    agree 1,875   disagree 0
target_fires changed by the repair    162 of 3,750
```

The two price scales now answer the same. That is the property the fleet needs,
because one detect threshold serves every bot.

### The gate verdicts

```
3,750 readings x 2 chains x 4 switch states = 30,000 verdicts
    fire before the repair                 1,322
    changed                                   58
        scrum refused -> scrum fires          50
        scrum fires -> scrum refused           8
        fold verdicts changed                  0
    changed verdicts at 1234.0                 0
    changed verdicts at 3.1e-06               58
    rows carrying them                        27
        rows where target_fires moved         27
        rows where the Z-Score crossed 2.0     0
```

Every changed verdict sits on a window where the ramp state moved, and every
one is at the small price scale. Nothing moved at four figures, which is what a
scale defect looks like once it is repaired.

### The other readings

```
3,750 readings
    published readings that moved, by voter
        bollinger_bands   18,748
        slingshot         24,244
        zscore            22,710
        ichimoku          17,978
        supertrend        11,250
        volume             7,500
        stochastic_rsi     7,300
    vote direction moved                       0
    vote strength moved                      358
    panel consensus direction moved            0
    panel consensus strength moved             8
    Z-Score published moved                3,470
    Z-Score crossed the 2.0 gate threshold     0
    Bollinger band position published moved 3,750
```

The Z-Score reading reaches a gate that blocks at two standard deviations. It
moved on 3,470 of the readings and crossed the threshold on none, so the gate
reads the computed number today and behaves as it did.

### The two statements

```
339,170 non-numeric readings compared
    moved                                      0
    dropped                                    0
    added                    3,750 mfi_rising
price_vs_cloud after     below 1,579   above 1,112   inside 499   absent 560
mfi_rising after         True 2,025    False 1,725
```

The cloud state is identical on every window, which is what a pure rebinding
has to look like, and the inside branch runs on 499 of them rather than never.
The money-flow slope takes both values, so the published flag discriminates
rather than answering one way for ever.

### The definitional bounds

`src/trading/ta_invariants.py` holds each indicator to the bounds its formula
implies. It breached on none of the 45,000 readings before the repair and on
none after, so removing the cuts exposed no bound the rounding had been hiding.

```
ta_invariants on the published bands   (True, '2 invariants')
the same bands with lower above upper  (False, 'lower <= middle <= upper')
```

That pair is the control for the zero above. The checker reports a breach when
one is put in front of it.

### What changes about a live reading

A bot on a market priced in millionths of a dollar now sees a Bollinger channel
with a real width instead of a flat line, so its scrum ramp reaches the fire
state on the same bars a bot on a four-figure market would.
