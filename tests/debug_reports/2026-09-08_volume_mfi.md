# Volume: the Money Flow Index on a market that never traded

**Mode: Reference.**

Issue #414 item 5. The item names two tests that read a money flow below 1e-09
as zero and answer 100, and a volume average with an absolute constant added to
it. Neither expression is in this tree. Commit `b27c6cdb` removed all three on
2026-09-04. What the item is about survives that commit, one input further in:
a window that credited neither money-flow bucket has no index at all, and the
module answered 50 on it.

```
71 recorded Coinbase tapes, windows from 36 bars, two price scales
    3,750 readings, 15,000 gate verdicts
        gate verdicts changed              0
        vote, strength, abstention flag    0
        panel consensus                    0
        the other eleven voters            0
    the index itself
        bit-identical on 1,843, moved on 1,907
        largest gap 2.1316282072803006e-14, identical at one decimal place
    the reading published
        hover cell moved on 3,710 of 3,750
        ATA-SMP sentence moved on 0 of 3,750
```

Every run used a throwaway home. `~/.acervator/settings.json` hashed the same
before and after:

```
before  18d380c7134dadbb2acbf5cbe5527ea177fe8b23cc77eb3fff6334fb03feeac8
after   18d380c7134dadbb2acbf5cbe5527ea177fe8b23cc77eb3fff6334fb03feeac8
```

## The error

Quong and Soudack, as StockCharts and Wikipedia reproduce them. Wikipedia
carries the closed second form; StockCharts carries the first.

```
TP_t = (H_t + L_t + C_t) / 3
MF_t = TP_t * V_t

positive money flow = sum of MF over the 14 bars where TP rose
negative money flow = sum of MF over the 14 bars where TP fell

MFI = 100 - 100 / (1 + positive / negative)
MFI = 100 * positive / (positive + negative)
```

Both sources say the same thing about an unchanged typical price: that bar is
discarded and credits neither bucket. Neither source addresses a window in
which every bar is discarded, or in which every bar traded nothing. There the
ratio is nothing over nothing and the index does not exist.

`src/trading/indicators/volume.py` — `VolumeAnalysis._mfi`, before

```python
if pos_mf <= 0.0 and neg_mf <= 0.0:
    return 50.0
if neg_mf <= 0.0:
    return 100.0
return 100.0 - 100.0 / (1.0 + pos_mf / neg_mf)
```

Fifty is the middle of the scale and it is a number. It reached the voting
panel's hover cell, the ATA-SMP post sentence and the emitter recorder, and the
Volume column went on to cast a vote and count in the panel's denominator, on a
market where the indicator had measured nothing.

The short-history branch above answered 50 for the same reason, on a candle
list too short for the formula.

A second departure sits beside it. The reading was published through
`round(mfi, 1)`. The vote always tested the computed number, so no gate read
the short one, but the panel's hover cell prints three decimals and was handed
a number carrying one.

## Reproduction

Seventy-one recorded Coinbase tapes from `~/.acervator_ra_tablets`, read-only,
each rescaled so the last close sits at 3.1e-06 and again at 1234.0. Every
window from 36 bars in steps of 11 ran through `VotingEngine().compute_all`,
and the summary built a GateContext whose other fields all pass. The chains are
the real ones, evaluated on both states of the two TA-direction flags, which
gives four verdicts per reading.

The pre-repair tree and the tree that still holds the epsilons are real
checkouts, not copies:

```
git worktree add --detach <path> origin/current
git worktree add --detach <path> b27c6cdb^
```

The window with no money flow does not occur in the recorded data, so it is
constructed. Across all 411 tablets:

```
411 tablets, every one daily bars
    bars compared                       104,925
    typical price repeated                  127
    zero-volume bars                         15
    longest run of repeats                    5   UWMC 2020, bar 17
    14-bar windows                       99,582
    windows crediting neither bucket          0
```

Fourteen consecutive repeats are needed and the longest recorded run is five.
The live fleet is 38 bots and every one of them computes on five-minute
candles, which the tablets do not contain, so the recorded data says nothing
about whether a seventy-minute flat window occurs live.

## The cause

The published formula has one undefined input and the module answered it with a
number rather than with an abstention. The first published form also has a
second undefined input, a negative money flow of zero, which the second form
answers at 100 without a branch.

Writing the index in the closed form leaves exactly one test, and that test is
exact at every price and volume scale because both money flows sum non-negative
terms.

## The correction

`src/trading/indicators/volume.py` — `VolumeAnalysis._mfi`, after

```python
if len(candles) < period + 1:
    return math.nan
```

```python
total_mf = pos_mf + neg_mf
if total_mf <= 0.0:
    return math.nan
return 100.0 * (pos_mf / total_mf)
```

`src/trading/indicators/volume.py` — `VolumeAnalysis.compute`, after

```python
mfi = self._mfi(candles, self.mfi_period)
if math.isnan(mfi):
    # `_mfi` has no money ratio; `mfi_ob` and `mfi_os` read False on nan.
    return Signal(
        "volume",
        timeframe,
        SignalDirection.NEUTRAL,
        0.0,
        self.weight,
        abstained=True,
    )
```

Abstaining is what this module already does when the window's average volume is
zero, and what four siblings do at their own missing denominator. It is also
what the two comparisons demand: both read False on a not-a-number, so an
absent index would otherwise be indistinguishable from an index between 20 and
80.

`src/trading/indicators/volume.py` — the reading, after

```python
"mfi": mfi,
```

## The rerun

### The new code is reached by the running program

Broken inside the indicator under `pdb`, entered the way a bot tick enters it.
The stack is the proof: the frame is reached from the voting engine, not from a
direct call.

```
python -X dev -X faulthandler -m pdb \
  -c "b <repo>/src/trading/indicators/volume.py:164" -c c -c where \
  -c "p mfi, math.isnan(mfi)" \
  -c "p len(candles), candles[-1].close, candles[-1].volume" -c c -c q \
  u414vol_pdb_entry.py <repo>
```

```
u414vol_pdb_entry.py(23)<module>()
-> summary = VotingEngine().compute_all(candles, "5m")
  src/trading/ta_engine.py(247)compute_all()
-> sig = ind.compute(candles, timeframe)
> src/trading/indicators/volume.py(164)compute()
-> if math.isnan(mfi):
(nan, True)
(40, 3.1e-06, 1000.0)
volume NEUTRAL 0.0 True {}
```

Forty five-minute bars at one price, which is what a halted market prints.

### The constructed windows, in three trees

Each tape ran through `VotingEngine.compute_all` in the tree that holds the
epsilons, in the pre-repair tree and in this one.

| tape | epsilon tree | origin/current | this tree |
| --- | --- | --- | --- |
| halted market, 3.1e-06 | 50.0, NEUTRAL, votes | 50.0, NEUTRAL, votes | no reading, abstains |
| halted market, 1234.0 | 50.0, NEUTRAL, votes | 50.0, NEUTRAL, votes | no reading, abstains |
| last 14 bars traded nothing | 50.0, BULLISH 0.37 | 50.0, BULLISH 0.37 | no reading, abstains |
| falling bars at volume 1e-05 | **100.0** | 99.999001008 | 99.999001008 |
| falling bars at volume 1e-320 | 100.0 | 100.0 | 100.0 |
| ordinary alternating window | 50.024987506 | 50.024987506 | 50.024987506 |

Row four is the underflow the item describes, reached: positive flow
2.17217e-05, negative flow 2.1699999999999997e-10, which is below 1e-09. The
tree that still holds the epsilons answers 100.0, the top of the scale, and
sets the overbought flag on a window that was 99.999 percent buying rather than
100 percent. That much was already repaired by `b27c6cdb`.

Row five is the only route left by which an absent reading could print as the
top of the scale, and it is not reachable. Measured by bisection: at a price of
3.1e-06 the product of price and volume is exactly zero for any volume at or
below 7.9688e-319, and nonzero at 7.96883e-319. The smallest volume in the 411
recorded tablets is 100. Where the falling side does underflow, the ratio puts
the index at 100 to every digit a double carries, which is the correct answer
and not an absent one.

Rows one to three are the reading this repair changes. On the halted market the
column had voted NEUTRAL at zero strength and still counted in the panel's
denominator; the panel consensus moves from 0.0667 to 0.0909 when it stops
counting. On the window whose last fourteen bars traded nothing the column had
voted BULLISH at 0.37, and the panel consensus moves from NEUTRAL to BEARISH
when that vote is withdrawn.

### The two price scales

The index is a ratio of two money flows, so it carries no price unit, and this
repair does not change that. Measured over the 1,875 window pairs, the index at
3.1e-06 and the index at 1234.0 differ by more than 0.05 on 17 pairs before the
change and on the same 17 after it.

Those 17 are the measuring method rather than the indicator. Rescaling
multiplies every price by one factor and the product rounds differently at the
two scales, so a bar whose typical price genuinely repeated can read as a rise
at one of them. ATOM 2022 at a 135-bar window does exactly that on one bar:
equal on the tape as recorded and equal at 1234.0, a rise at 3.1e-06, which
moves the index from 30.602690746573963 to 40.40912627360686. The
classification at the four-figure scale matches the tape as recorded, so the
rescale is what moved it.

The other 860 pairs differ only in the last bits of that same multiply. The old
reading was cut to one decimal place and hid them.

### The index itself

`VolumeAnalysis._mfi` was dumped at full precision over the same 3,750 windows
in the pre-repair tree and in this one.

```
values                    3,750
bit-identical             1,843
moved                     1,907
largest absolute gap      2.1316282072803006e-14
largest relative gap      1.5406667372919226e-15
identical at one decimal  3,750
range of the values       3.747182689358553 to 97.54432248701947
```

The widest row is LINK 2020 at a 234-bar window: 52.47053014584313 against
52.47053014584311. That is the last bits of double arithmetic, not the formula.

### The gate verdicts

```
3,750 readings x 2 chains x 2 flag states = 15,000 verdicts
    scrum verdicts changed, TA flags on      0
    fold verdicts changed, TA flags on       0
    scrum verdicts changed, TA flags off     0
    fold verdicts changed, TA flags off      0
```

The compare carries a control: one row altered at parity in the post-repair
dump — its vote, strength, abstention flag, its index, the consensus, one other
voter's strength and all four chain arms — makes every one of those zeros read
1. A compare that saw nothing would be reporting on itself.

No recorded window reaches the abstention, so no verdict could change on this
data. The abstention is proved by the constructed windows above, driven through
the same entry point.

### Every reader

Six parts of the platform read this indicator.

| reader | at three millionths of a dollar |
| --- | --- |
| `ta_invariants.py` bound | bounds the computed number; no bound applies on an abstention |
| `ta_engine.py` recorder | records the computed number, and an empty reading on an abstention |
| `ata_spm.py` sentence | `Money Flow Index 56.5`, unchanged on all 3,750 |
| `indicator_panel.py` hover | `mfi: 56.450`, was `mfi: 56.500` |
| `indicator_panel_surface.py` hover | `mfi: 56.450`, was `mfi: 56.500` |
| the panel's consensus | loses one voter from its denominator on an abstention |

The ATA-SMP sentence formats to one decimal place itself, so uncutting the
reading does not reach it. The hover cells format to three, and moved on 3,710
of 3,750. `native_chart.py` names this voter to drive an overlay toggle and
draws raw volume bars; it reads no reading.

The bound is `0 <= mfi <= 100`. The closed form cannot leave that interval,
because the numerator is one of the two terms in its own denominator and both
are non-negative.

### Nothing else moved

Twelve voters read back over 71 tapes at both price scales, every vote,
strength and abstention flag compared.

```
readings compared  3,750 per voter
differing          volume, the index only
identical          adx  bollinger_bands  ichimoku  kaufman_er  macd  rsi
                   slingshot  stochastic_rsi  supertrend  vortex  zscore
```

### The checkers

```
coding_archetype  src/trading/indicators/volume.py     passed
ta_archetype      src/trading/indicators/volume.py     passed
docs_archetype    docs/manual/07-indicators.md         passed
docs_archetype    tests/debug_reports/2026-09-08_volume_mfi.md   passed
```

The fixture pair proved each instrument first: `known_good` exit 0 and
`known_bad` exit 1, for all three.

### What is not repaired here

`VolumeAnalysis.compute` still evaluates `mfi > mfi_prev` as a bare statement
whose value nothing binds. Issue #414 groups that with the second dead statement
in `ichimoku.py` as its own unit.
