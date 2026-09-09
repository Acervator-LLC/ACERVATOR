# 2026-09-09 - #407 - metals become scannable, and the two volume-reading voters

The brief names three defects. This unit drove all three against the real venue
and the real code. Two of the three turned out to be something other than what
the brief describes, and this report says what each one actually is.

Every run below used `python -X dev -X faulthandler` with
`PYTHONWARNINGS=error`, in a `git worktree` cut from `origin/current`. This unit
wrote no test file, started nothing, attached to nothing, placed no order and
held no credential. It read one public chart endpoint.

`~/.acervator/settings.json` hashed the same before and after:
`18d380c7134dadbb2acbf5cbe5527ea177fe8b23cc77eb3fff6334fb03feeac8`.

---

## 1 The metals map asked for a ticker no venue lists

### The error - a metals scan votes on nothing

A metals scan produced no vote. `ata_spm.evaluate` reported the sector's four
names as unlisted and read no prices, because every row carried `NO_VENUE`.

```
Phase 1 Evaluate unlisted: No configured venue lists XAU/USD, XAG/USD,
XPT/USD, XPD/USD.
```

### The reproduction - twelve tickers, one at a time

This unit pulled the twelve candidate tickers through
`YahooChartAdapter.fetch_chunk`, over a 400-day window, on the `1d` interval.
Every request names a dated window. None sends `range=max`.

```
XAUUSD=X   rows=0    HTTP Error 404: Not Found
XAGUSD=X   rows=0    HTTP Error 404: Not Found
XPTUSD=X   rows=0    HTTP Error 404: Not Found
XPDUSD=X   rows=0    HTTP Error 404: Not Found
GC=F       rows=275  2025-08-06..2026-09-09  vol_zero=4    of 275
SI=F       rows=275  2025-08-06..2026-09-09  vol_zero=7    of 275
PL=F       rows=275  2025-08-06..2026-09-09  vol_zero=132  of 275
PA=F       rows=275  2025-08-06..2026-09-09  vol_zero=129  of 275
GLD        rows=274  2025-08-06..2026-09-08  vol_zero=0    of 274
SLV        rows=274  2025-08-06..2026-09-08  vol_zero=0    of 274
PPLT       rows=274  2025-08-06..2026-09-08  vol_zero=0    of 274
PALL       rows=274  2025-08-06..2026-09-08  vol_zero=0    of 274
```

The four spot pairs answer 404. The eight the brief names each return a full
year of daily bars.

### The cause - every metals row carried NO_VENUE

`METALS_SPOT` in `src/trading/ata_asset_maps.py` named the four spot pairs and
gave each of them `NO_VENUE`. Gold spot is a dealer market with no public
listing, so that absence answers the question correctly and states the world
wrongly. Nothing in the map named an instrument a venue does carry.

### The correction - the funds join the map

`METALS_PHYSICAL` now names `GLD`, `SLV`, `PPLT` and `PALL` on `VENUE_YAHOO`.
The metals sector holds both tuples, so it scans the four listed funds and still
reports the four unlisted spot names.

```python
METALS_PHYSICAL: tuple[AssetListing, ...] = tuple(
    AssetListing(symbol=one, quote=USD, venue=VENUE_YAHOO, ticker=one)
    for one in ("GLD", "SLV", "PPLT", "PALL")
)

MAPS: dict[str, dict[str, tuple[AssetListing, ...]]] = {
    CLASS_METALS: {SECTOR_SPOT: METALS_SPOT + METALS_PHYSICAL},
}
```

**The map carries the funds, not the futures, on two measured grounds.**

A futures chart longer than a few months joins two or more contracts, and every
join is a price step nobody traded. This platform sells against a dollar target,
so a synthetic step moves every level behind it. A fund has no expiry and no
roll.

The futures also carry the hole the second defect is about. `PL=F` sends 132 of
275 daily bars with volume 0, and `PA=F` sends 129. The four funds send none.
Carrying the futures would silence the volume voter on half the metals map.

`MAP_SOURCES[CLASS_METALS]` records both instruments, the date behind each
figure, and why the map leaves the futures out.

### The rerun - Scan Now reaches the venue

This unit drove Scan Now under `pdb`, breaking on `venue_candles`. The stack
names every caller between the button and the venue read.

```
u407mfx_scan_now.py(13)                     run = model.scan_now()
market_inspector_surface.py(2374)scan_now   added = self.board.scan_now(
ata_spm.py(1114)scan_now                    sectors, added, found = self.compute(
ata_spm.py(1084)compute                     run(
ata_spm.py(970)run                          scans = evaluate(sectors, ...)
ata_spm.py(646)evaluate                     _scan_timeframe(voter, assets, ...)
ata_spm.py(669)_scan_timeframe              candles = candles_for(...)
ata_spm.py(562)candles_for                  return list(candle_source(...))
market_inspector_surface.py(2326)scanned_candles
                                            return sector_candles(...)
market_inspector_surface.py(1974)sector_candles
                                            return ata_asset_maps.venue_candles(
                                                symbol, timeframe)
ata_asset_maps.py(255)venue_candles         found = listing_of(symbol)
('GLD', '1h')
```

The sector then answered 16 votes over four timeframes.

```
sector 'spot' class=metals
  assets scanned : ['GLD', 'SLV', 'PPLT', 'PALL']
  unlisted       : ('XAU/USD', 'XAG/USD', 'XPT/USD', 'XPD/USD')
  note           : ''

  1h    GLD  rows=78   2026-08-24..2026-09-08  net=-0.9506  bearish
        SLV  rows=78   2026-08-24..2026-09-08  net=+0.5158  bullish  reversal
        PPLT rows=78   2026-08-24..2026-09-08  net=+0.6276  bullish  reversal
        PALL rows=78   2026-08-24..2026-09-08  net=-0.9158  bearish
  1d    GLD  rows=250  2025-09-10..2026-09-08  net=-0.0122  neutral
        SLV  rows=250  2025-09-10..2026-09-08  net=+0.8762  bullish
        PPLT rows=250  2025-09-10..2026-09-08  net=+1.7784  bullish
        PALL rows=250  2025-09-10..2026-09-08  net=+0.3098  bullish
  1w    GLD  rows=201  2022-11-14..2026-09-08  net=+0.5520  bullish
        SLV  rows=201  2022-11-14..2026-09-08  net=-0.5188  bearish
        PPLT rows=201  2022-11-14..2026-09-08  net=+0.3748  bullish
        PALL rows=201  2022-11-14..2026-09-08  net=-0.0724  neutral
  1M    GLD  rows=198  2010-05-01..2026-09-08  net=+2.5220  bullish
        SLV  rows=198  2010-05-01..2026-09-08  net=+1.2055  bullish
        PPLT rows=198  2010-05-01..2026-09-08  net=+0.7935  bullish
        PALL rows=198  2010-05-01..2026-09-08  net=+0.7583  bullish

run report: Phase 3 Pull: 1 sector(s), 2 call(s), 2 chart(s)
```

The expanded lines the zone draws keep the absence beside the scan.

```
Phase 1 Evaluate 1hr:   4 vote(s), 0 without candles, 0 under 30 candles
Phase 1 Evaluate 1d:    4 vote(s), 0 without candles, 0 under 30 candles
Phase 1 Evaluate 1wk:   4 vote(s), 0 without candles, 0 under 30 candles
Phase 1 Evaluate 1mnth: 4 vote(s), 0 without candles, 0 under 30 candles
Phase 1 Evaluate unlisted: No configured venue lists XAU/USD, XAG/USD,
XPT/USD, XPD/USD.
```

**One transient belongs in the record, because it appeared in the evidence.** On
the first run the venue answered no hourly rows for `GLD` while answering 78 for
the other three. The zone reported `1 without candles` and cast no vote. The
second run answered 78 rows for all four. The venue's answer changed. The code
reported each answer correctly.

---

## 2 The FX pairs report volume 0, so a voter reads nothing

### The error - no FX bar carries volume

Every FX daily bar the venue sends carries volume 0.

```
EUR/USD  273 bars   0 with volume
USD/JPY  266 bars   0 with volume
GBP/USD  277 bars   0 with volume
USD/CHF  275 bars   0 with volume
AUD/USD  268 bars   0 with volume
NZD/USD  268 bars   0 with volume
USD/CAD  275 bars   0 with volume
EUR/GBP  279 bars   0 with volume
EUR/AUD  269 bars   0 with volume
EUR/NZD  266 bars   0 with volume
```

0 of 2,676 bars over ten pairs. Two of the twelve voters read volume:
`VolumeAnalysis` in `src/trading/indicators/volume.py` and `ZScoreIndicator` in
`src/trading/indicators/zscore.py`.

### The reproduction - two voters, two series

This unit ran both voters on `EUR/USD`, which sends no volume, and on `GLD`,
which sends volume on every bar. `GLD` is the positive control. Without it, an
abstention on FX says nothing about whether the voter can vote at all.

```
EUR/USD   VolumeAnalysis   NEUTRAL  conf=0.0000  abstained=True
          ZScoreIndicator  NEUTRAL  conf=0.0000  abstained=False
GLD       VolumeAnalysis   BULLISH  conf=0.6000  abstained=False
          ZScoreIndicator  NEUTRAL  conf=0.0000  abstained=False
```

**`VolumeAnalysis` already abstains, and the control proves it can vote.** The
thing that must not happen — a voter reading an all-zero series and producing a
confident reading from it — does not happen. `compute` returns early twice on
such a series. `_mfi` answers `nan` where no money flow takes a value, and
`avg_vol <= 0.0` returns before the score exists.

**`ZScoreIndicator` does not abstain, and it does not need to.** It publishes a
z-score, which is arithmetic over closes. What it loses is its volume-weighted
smoothing.

### The cause - the smoothing vanishes and says nothing

`_vwma` answers `None` where the bars carry no volume to weight by, so `compute`
falls back to the unsmoothed z-score.

```python
smoothed = _vwma(z_series, z_volumes, self.smoothing_period)
z = z_raw if smoothed is None else smoothed
```

That fallback is right. The defect is that nothing said it happened. The
`Signal` details carried `z` and `z_raw` and no field separating the two, so a
reader of a published post could not tell that the smoothing had vanished on
every FX market.

### The correction - the z-score publishes its own state

**This unit wired no proxy, on two grounds.**

CME currency futures do carry volume on the same endpoint:

```
6E=F  275 rows  2025-08-06..2026-09-09  3 bars with volume 0
6J=F  275 rows  3 bars with volume 0
6B=F  275 rows  3 bars with volume 0
6A=F  275 rows  3 bars with volume 0
6C=F  275 rows  3 bars with volume 0
6S=F  275 rows  3 bars with volume 0
6N=F  275 rows  3 bars with volume 0
```

A currency future's volume is that contract's volume, not the pair's, and spot
FX has no consolidated volume anywhere. Serving one as the other puts a number
in a post that the market in that post never traded. The issue's own standard
for the maps is that a figure names its source, and a proxy served as the thing
fails it. An abstention is honest, and the code already abstains.

`ZScoreIndicator` now publishes which of the two values `z` holds.

```python
smoothed = _vwma(z_series, z_volumes, self.smoothing_period)
z_volume_weighted = smoothed is not None
z = z_raw if smoothed is None else smoothed
```

`"z_volume_weighted": z_volume_weighted` joins the `Signal` details. No formula
changed, no direction changed and no confidence changed.

`MAP_SOURCES[CLASS_FOREX]` records the volume absence, so a reader knows before
scanning that one voter abstains on every pair.

### The rerun - the field separates the two states

The field reports both states, and it separates them on real data.

```
                 before        after
EUR/USD          absent        False
USD/JPY          absent        False
GBP/USD          absent        False
USD/CHF          absent        False
AUD/USD          absent        False
NZD/USD          absent        False
USD/CAD          absent        False
GLD              absent        True
SLV              absent        True
PPLT             absent        True
PALL             absent        True
```

A field reporting only `False` would be a field nobody could read a fault from.
This one reports `True` on four markets and `False` on seven, on the same run.

---

## 3 A voter reads a daily FX open the brief calls feed noise

### The error - the claim under test

`src/trading/indicators/volume.py` gates the capitulation flag on the bar's own
open.

```python
candle_up = candles[-1].close >= candles[-1].open
```

The brief states that the daily FX open is a feed artefact rather than a traded
price, on the evidence that opens sit about 31 pips from the previous close
against a 53-pip average day.

### The reproduction - the gap, and a control market

**The 31-and-53 figures reproduce exactly.** Over 400 days:

```
symbol   mean gap to previous close   mean bar range   gap / range
EUR/USD              31.6 pips            54.7 pips        0.578
USD/JPY              55.0                 91.1             0.603
GBP/USD              41.8                 71.1             0.588
USD/CHF              27.5                 46.9             0.586
AUD/USD              27.3                 46.5             0.587
NZD/USD              24.9                 41.7             0.596
USD/CAD              28.3                 49.7             0.570
                                          mean             0.587
```

**The same measurement on a market whose open is certainly a traded price:**

```
GLD                                                        0.665
SLV                                                        0.705
PPLT                                                       0.730
PALL                                                       0.700
                                          mean             0.700
```

A fund opens at an auction print. Its open sits **further** from the previous
close, as a share of its own day's range, than the FX open does. A gap of this
size is what a daily bar does on any market that stops trading between bars.

**A second measurement points the same way.** A price outside its own bar's high
and low cannot have traded in that bar, so counting those rows says which field
the venue is loose with.

```
group        rows   open outside its bar   close outside its bar
FX spot      1,981          10 (0.5%)             79 (4.0%)
metal fund   1,096           0                     0
```

The FX close falls outside its own bar eight times as often as the open does.
The open is the more internally consistent of the two fields, not the less.
`_candles_of` already refuses those rows one at a time, so no indicator sees
one.

### The cause - the premise does not survive the measurement

Nothing in the three formulae is wrong.

**All three formulae that read the open are the published ones.** `close >=
open` is the standard test for an up bar. Valcu's Heikin Ashi takes the raw open
as an input to `ha_open`. The landing strip measures the size of real candle
bodies. Dropping the open from any of them departs from a published formula to
correct a fault the data does not show, and TA canon does not permit removing a
behaviour in place of correcting it.

### The correction - the open stays, the numbers go on record

All three keep the open. This unit changed the record instead: the numbers above
go here and into the manual, so nobody re-opens the question from the same
starting claim.

### The rerun - three readers, two open series

This unit drove all three readers twice on each of the seven major pairs: once
on the venue's own opens, and once with every open replaced by the previous
close.

```
symbol    heikin ashi colours flipping   landing strip   volume voter
EUR/USD                  23 of 273       False / False   abstain / abstain
USD/JPY                  25 of 266       False / False   abstain / abstain
GBP/USD                  32 of 277       False / False   abstain / abstain
USD/CHF                  36 of 275       False / False   abstain / abstain
AUD/USD                  20 of 268       False / False   abstain / abstain
NZD/USD                  18 of 268       False / False   abstain / abstain
USD/CAD                  24 of 275       False / False   abstain / abstain
```

Heikin Ashi changes 178 of 1,902 bar colours between the two open series, and
nothing downstream of it reaches a different decision. The landing strip detects
on neither series. The volume voter abstains on both, because the venue sends no
volume, so line 225 never runs on this feed.

**Line 225 then ran where it does reach.** The metal funds carry real volume, so
`compute` reaches the capitulation flag on them.

```
symbol   bars   capitulation fires   feed open   previous-close open   conf delta
GLD      274            2             BULLISH        BULLISH             +0.0000
SLV      274            1             BEARISH        BEARISH             +0.0000
PPLT     274            0             BEARISH        BEARISH             +0.0000
PALL     274            3             NEUTRAL        NEUTRAL             +0.0000
```

The flag is live. It fires six times over 1,096 bars, and replacing every open
changes no direction and moves the confidence by 0.0000.

---

## Gate verdicts

`ata_gate_scan.scan_gates` ran both chains over eleven markets, before the
changes and after. That is 21 gate readings per market, 231 in all.

```
gate verdicts compared : 231 over 11 markets
gate verdicts changed  : 0
```

**A control ran before that zero reached this report.** The same comparison ran
between two genuinely different real markets, which is the two-real-inputs
control rather than a planted fault.

```
EUR/USD vs AUD/USD   1 verdict differing of 21
EUR/USD vs USD/JPY   1 verdict differing of 21
EUR/USD vs USD/CAD   1 verdict differing of 21
EUR/USD vs PALL      1 verdict differing of 21
EUR/USD vs EUR/USD   0 verdicts differing of 21
```

The comparison reports a difference where one exists, so the zero above states a
fact about the change and not about the instrument.

**What did change is how many gate readings exist at all.**

```
metals gate readings produced before   0, the sector scanned no asset
metals gate readings produced now     84, four markets at 21 readings each
```

---

## What the operator sees differently

Typing `spot` on the metals class and pressing Scan Now returns votes on four
markets across four timeframes, with two reversal calls and two charts. Before
this change it returned one line saying no venue lists anything. The four spot
names still appear on their own line, marked as unlisted.
