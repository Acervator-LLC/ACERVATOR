# VWAP Charts and Trade Grading

Reference. What a year of live fills measures, how the volume-weighted average
price is drawn from it, and what the platform's own grading and gate logs add
to a fill.

The fill record is the operator's own venue export. It is not committed to this
repository and no row of it is reproduced anywhere in this manual. Every figure
below is an aggregate over that record.

## The record behind the charts

The export holds 5,709 physical rows and 5,705 body rows. 5,661 of the body
rows are fills.

Body rows by transaction type: Advanced Trade Buy 3,189; Advanced Trade Sell
2,472; Reward Income 16; Deposit 15; Buy 8; Sell 4; Withdrawal 1.

44 body rows carry no fill, and each one is accounted for by name: 16 Reward
Income, 15 Deposit, 12 USDC cash legs of a trade priced elsewhere, and 1
Withdrawal. Nothing is dropped without a reason that says what it was.

40 distinct assets appear in the record. USD and USDC are quote currencies,
which leaves 38 charted bases, one for each bot in the fleet, and each of the
38 has fills of its own.

Fills per asset, most to fewest: A01 900, A02 495, A03 459, A04 322, A05
261, A06 230, A07 226, A08 220, A09 196, A10 191, A11 178, A12 159, A13
147, A14 141, A15 124, A16 124, A17 119, A18 119, A19 113, A20 87, A21 83,
A22 80, A23 77, A24 75, A25 74, A26 73, A27 73, A28 66, A29 63, A30 58,
A31 25, A32 24, A33 23, A34 23, A35 16, A36 6, A37 6, A38 5. Those 38
counts sum to 5,661, the fill total above.

## Subtotal is the price

A row carries both a Subtotal and a Total, and only one of them belongs in a
VWAP. On every row the absolute quantity times the price equals the absolute
Subtotal to within 5e-6. Total is that same figure plus the fee.

A fee is a transaction cost, not a price. Fee drag measures between 0.92 and
1.20 percent per asset, so a VWAP built on Total would sit roughly that far
above the price the venue actually filled at, on every buy in the record.

## How a VWAP is computed here

The running figure is a streaming sum of price times quantity over a streaming
sum of quantity, both carried as floats. The price is the export's Price at
Transaction column. The generator never reads Subtotal, and it does not need
to. The section above measures quantity times price against Subtotal and finds
the two equal to within 5e-6.

Run against the same rows with Python's exact `Fraction`, the two paths agree
to 3.63e-15 across 26 assets, so the float path loses nothing a chart can show.

One control separates a weighted mean from an unweighted one. One unit bought
at $10 and three at $20 give 17.50 by hand, and both the float path and the
`Fraction` path return 17.50. An unweighted mean of the two prices returns
15.00. An implementation that forgot to weight by quantity would open a gap of
2.50 on that case rather than pass unnoticed.

## What the combined chart plots

Each asset has a chart of its running buy VWAP against time. The line is the
trajectory of the average as accumulation proceeds, and the shape of that
trajectory is the reading.

Two metrics run through this part and they answer different questions. The
trajectory answers what the units now held cost on average, and it keeps moving
while the position is open. The sell-over-buy ratio answers whether the trades
already closed sold above what they cost, and it is one settled figure per asset
across the whole record. One reads the position, the other reads the realised
trades. This part carries both, and neither stands in for the other.

The combined chart indexes every asset to its own first buy VWAP and plots the
running buy VWAP divided by that first value, so an asset priced in cents and
an asset priced in thousands share one axis and one scale.

Of the eight assets with the most fills, six trend down to between 0.4 and 0.6.
A05 and A04 trend up.

Read the line as what it is. A falling running buy VWAP says the average cost
of the base units now held fell as more were bought. It is not profit. It does
not become profit until units are sold, and the index carries no sale in it at
all.

![The running buy VWAP of the eight assets with the most fills, each divided by its own first buy VWAP.](figures/vwap_combined.png)

The eight lines are the eight assets with the most fills. Each one is that
asset's running buy VWAP divided by its own first buy VWAP, which puts A10 at
5.71e-06 and A05 at 359.67 on one axis and one scale. The rule at 1.0 marks the
first value. The legend names the asset and its fill count in three columns.
The note under the axis reads:

```
38 charted bases. USD and USDC are excluded as quote currencies.
```

Five pens carry the eight lines. The chart takes the series palette from
`src/design_system.py` and keeps only the colours reaching a contrast ratio of
3.0 against the page background. Five of the eight qualify. The five run solid
for the first five assets and dashed for the last three.

| Series colour | Contrast on the page background | In the chart |
| --- | ---: | --- |
| #000000 | 21.00 | yes |
| #0072B2 | 5.19 | yes |
| #D55E00 | 3.87 | yes |
| #009E73 | 3.42 | yes |
| #CC79A7 | 3.06 | yes |
| #56B4E9 | 2.31 | no |
| #E69F00 | 2.25 | no |
| #F0E442 | 1.32 | no |

Measured over the same 5,661 fills, the eight lines end here:

| Asset | Fills | First buy VWAP | Final buy VWAP | Final index |
| --- | ---: | ---: | ---: | ---: |
| A01 | 900 | 1.5915 | 0.672605 | 0.423 |
| A02 | 495 | 0.10842 | 0.044733 | 0.413 |
| A03 | 459 | 0.11868 | 0.035741 | 0.301 |
| A04 | 322 | 0.2478 | 0.298528 | 1.205 |
| A05 | 261 | 359.67 | 485.048 | 1.349 |
| A06 | 230 | 0.01581 | 0.006453 | 0.408 |
| A07 | 226 | 0.05537 | 0.032580 | 0.588 |
| A08 | 220 | 0.0508 | 0.022611 | 0.445 |

Six of the eight end below 1.0 and two end above it. Of the six, five land
between 0.408 and 0.588, and A03 lands at 0.301.

## The buy and sell ratio

The second metric is one figure per asset: the sell VWAP divided by the buy
VWAP, across every fill in the record. Above 1.000 the average sale price beat
the average buy price. Below it the average sale came in under the average cost.
The figure reads how the closed trades performed, and nothing else.

No chart needs redrawing for it. Every per-asset chart already carries both
lines, and the ratio is where the two of them finish: the sell line's last value
over the buy line's last value. Both averages come from the same two columns as
the charts, the export's Price at Transaction and its Quantity Transacted. Each
side keeps its own pair of sums, so neither average pulls on the other.

Of the 38 charted bases, 35 have enough fills on both sides for the figure to
mean anything. 23 of those finish above 1.000 and 12 below, and none lands
exactly on it. A29 is the highest at 1.351 and A20 the lowest at 0.879.

| Asset | Buys | Sells | Buy VWAP | Sell VWAP | Ratio |
| --- | ---: | ---: | ---: | ---: | ---: |
| A01 | 538 | 362 | 0.672605 | 0.610801 | 0.908 |
| A02 | 265 | 230 | 0.044733 | 0.0453964 | 1.015 |
| A03 | 275 | 184 | 0.0357413 | 0.040867 | 1.143 |
| A04 | 143 | 179 | 0.298528 | 0.328486 | 1.100 |
| A05 | 140 | 121 | 485.048 | 536.675 | 1.106 |
| A06 | 138 | 92 | 0.00645325 | 0.00627872 | 0.973 |
| A07 | 155 | 71 | 0.0325805 | 0.0317443 | 0.974 |
| A08 | 140 | 80 | 0.0226113 | 0.0212018 | 0.938 |
| A09 | 113 | 83 | 1.38181 | 1.34298 | 0.972 |
| A10 | 104 | 87 | 5.98261e-06 | 6.10717e-06 | 1.021 |
| A11 | 75 | 103 | 0.0297901 | 0.036577 | 1.228 |
| A12 | 98 | 61 | 0.00762374 | 0.00758363 | 0.995 |
| A13 | 69 | 78 | 14.6904 | 15.4413 | 1.051 |
| A14 | 95 | 46 | 1996.6 | 2047.62 | 1.026 |
| A15 | 95 | 29 | 68918 | 68393.6 | 0.992 |
| A16 | 69 | 55 | 242.103 | 238.855 | 0.987 |
| A17 | 66 | 53 | 0.36133 | 0.38167 | 1.056 |
| A18 | 82 | 37 | 1.39501 | 1.40129 | 1.005 |
| A19 | 57 | 56 | 0.00276124 | 0.00283892 | 1.028 |
| A20 | 32 | 55 | 0.0336835 | 0.0296231 | 0.879 |
| A21 | 43 | 40 | 9.06192 | 9.27909 | 1.024 |
| A22 | 43 | 37 | 0.0881513 | 0.0882367 | 1.001 |
| A23 | 43 | 34 | 82.9528 | 83.4024 | 1.005 |
| A24 | 47 | 28 | 0.0116845 | 0.0116532 | 0.997 |
| A25 | 41 | 33 | 0.857863 | 0.824958 | 0.962 |
| A26 | 41 | 32 | 0.475448 | 0.497449 | 1.046 |
| A27 | 45 | 28 | 0.198142 | 0.21519 | 1.086 |
| A28 | 29 | 37 | 61.99 | 66.8959 | 1.079 |
| A29 | 23 | 40 | 0.00205112 | 0.00277049 | 1.351 |
| A30 | 27 | 31 | 2.03969 | 2.09155 | 1.025 |
| A31 | 16 | 9 | 0.0828047 | 0.0787786 | 0.951 |
| A32 | 8 | 16 | 0.431039 | 0.480832 | 1.116 |
| A33 | 8 | 15 | 0.145768 | 0.164984 | 1.132 |
| A34 | 10 | 13 | 0.174843 | 0.202243 | 1.157 |
| A35 | 9 | 7 | 0.160515 | 0.164726 | 1.026 |
| A36 | 3 | 3 | 46.4508 | 51.1833 | not read |
| A37 | 3 | 3 | 0.0589505 | 0.0591535 | not read |
| A38 | 1 | 4 | 2148.63 | 2576.19 | not read |

Three rows carry no ratio and the reason is the fill counts beside them. A38
has one buy, so its buy figure is a single price and not an average of anything.
A36 and A37 have three buys and three sells each. A mean over three fills moves
with any one of them, so a ratio built on it says more about which trade landed
last than about how the asset performed. The table keeps both averages, since
the export supports each one, and leaves the division out, since a number there
would read as a result.

Every other row rests on at least seven fills a side, and 30 of the 38 rest on
at least 23 a side.

The two metrics leave out different things and both gaps matter. The ratio
counts only what completed on both sides, so it says nothing about units still
held — and on most of these assets the held position is the larger part of the
story. The trajectory counts every buy and no sale at all, so it says nothing
about whether a sale ever cleared its cost. A cycle needs both readings. Either
one alone overstates what it knows.

## Traps in the export

Three shapes in the record break a reader that takes every row the same way.

A plain `Sell` row carries a negative quantity against a positive Subtotal. An
`Advanced Trade Sell` row pairs those signs the other way round. Taking the
sign from one column and the magnitude from the other turns four trades
backwards.

One row carries a negative fee.

Three A27 rows carry a Subtotal that rounds to $0.00 against a quantity that is
real. A filter that drops zero-value rows drops those base units with them.

## Where the figures live

The charts are generated output, so they are not tracked. They belong beside
the manual's other images in `artifacts/manual-figures/` under the repository
root, a path `.gitignore` excludes. [FIGURES.md](FIGURES.md) inventories the
images the manual itself embeds. No chart image is committed to this
repository.

The 39 charts of this part live one level down, in a directory of their own
beside the manual figures and under the same ignore rule. Keeping the two sets
apart keeps the manual's own 38 images and this part's 39 charts from mixing.
The combined view above sits in the first file below, and each charted base has
one chart of its own.

```
docs/manual/figures/
    p<page>-i<index>.png        the manual's own 38 images
    vwap_combined.png           the eight-line combined chart
    vwap_a<NN>.png              one per charted base, 38 of them
    weekly_a<NN>.png            one weekly chart per charted base, 38 of them
    trace_a<NN>.png             one price trace per charted base, 38 of them
```

## The charts are tracked, and they name no asset

Three sentences above are overtaken. They are quoted whole, and the sentence
that replaces each one follows it.

> The charts are generated output, so they are not tracked.

The 39 charts are tracked, under `docs/manual/figures/`, so a clone can rebuild
the manual without the venue export.

> They belong beside the manual's other images in `artifacts/manual-figures/`
> under the repository root, a path `.gitignore` excludes.

Both sets sit together in `docs/manual/figures/`, which `.gitignore` does not
exclude.

> No chart image is committed to this repository.

Every chart is committed, and every one of them has the asset name painted out
of its title, out of its price-axis label, and out of the combined view's
legend. The file name carries the label this part uses, `vwap_a01.png` through
`vwap_a38.png`, and never the asset.

The repository carries one manual, and that manual names no traded asset. The
build that names them runs only from a checkout holding the unobscured charts,
which this repository does not carry.

## How to read a per-asset chart

Every chart carries two panels over one time axis.

The upper panel draws every fill as a dot at its price, buys in
`COLORS["series"][0]` and sells in `COLORS["series"][5]`. Two lines cross it:
the running buy VWAP and the running sell VWAP, in those same two colours. Each
line steps at a fill of its own side and holds flat across a fill of the other
side. The price axis turns logarithmic when the highest fill price exceeds the
lowest more than eightfold, which covers A01 at 10.30 and A03 at 13.25 and no
other asset. A chart of 30 fills or fewer marks each step with a dot: A31,
A32, A33, A34, A35, A36, A37 and A38.

The lower panel draws net units accumulated — every bought quantity minus every
sold quantity, running — in `COLORS["accent"]`, filled down to zero. It answers
what the price panel cannot: whether the base position grew.

Every chart in this part draws its colours, its type sizes and its page size
from `src/design_system.py`, which holds them under five names.

```python
COLORS = {"bg": ..., "ink": ..., "accent": ..., "series": [...]}
TYPE = {"h1": ..., "body": ..., "cap": ...}
GRID = {"unit": 8, "page_w_in": 11.0, "page_h_in": 8.5}


def apply_rcparams(): ...


def contrast_ratio(fg: str, bg: str) -> float: ...
```

Read the buy line as a trajectory of average cost. A falling line says the
average cost of the units bought so far fell. That fall is not profit, for the
same reason the combined chart above carries none: no sale enters that line.

## The Bollinger band behind the price

A grey channel sits behind the fills on the upper panel. It is a Bollinger
band, and it is there so a trade at a volatility extreme can be seen rather
than asserted. A scrum sells into the top of the channel and a fold buys into
the bottom, and the channel puts both on the picture.

The band is the published one. A middle line is a simple moving average over a
fixed number of bars, and the outer lines sit a fixed number of population
standard deviations above and below it, taken over the same bars.

```
Middle = SMA(period)
Upper  = Middle + std_dev * sigma(period)
Lower  = Middle - std_dev * sigma(period)
```

The setting is the conventional one: period 20, width 2 standard deviations.

### Where the band maths comes from

The platform already computes this band for its own trading decisions, and the
charts read the same code rather than a second copy of the formula. The method
returns one upper, middle and lower value per bar, and nothing before the
twentieth bar, because no window has closed yet.

```python
# src/trading/indicators/bollinger.py
BollingerBands(period=20, std_dev=2.0).bands(candles)
```

The deviation is the population one, divided by the window length, which is
what Bollinger publishes. It is computed in `src/trading/indicators/helpers.py`
and shared by every indicator that needs a rolling deviation.

### What a fill at a band edge means

The upper line is two standard deviations above the recent average price, so a
sell dot sitting on it or above it is a sale made while the price was at the
top of its own recent range. The lower line is the mirror of that, so a buy dot
on it or below it is a purchase made into the bottom of that range. Those two
readings are the whole reason the band is drawn.

A dot inside the channel is an ordinary trade. Nothing about a fill at an edge
says it was profitable. It says where in the recent price distribution the
trade landed.

### Which bar length the band uses

The export carries a timestamp and a price per fill and no candles, so the bars
are built from the fills: the last fill in a bar closes it, and a bar with no
fill closes where the one before it closed. That construction decides whether a
short bar can carry a band at all. Twenty consecutive bars with no trade have
no spread between them, so the deviation is zero and the band collapses onto
the price line.

Measured over all 38 charted bases, counting every band the method returned and
how many of them had zero width:

| Bar length | Bands drawn | Zero width | Share | At or above upper | At or below lower | Fills in a banded bar |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 5 minutes | 1,288,981 | 1,064,990 | 82.6% | 2,921 | 3,134 | 6,868 |
| 15 minutes | 429,202 | 315,054 | 73.4% | 2,578 | 2,609 | 6,842 |
| 1 hour | 106,790 | 52,205 | 48.9% | 1,972 | 1,854 | 6,702 |
| 4 hours | 26,182 | 4,994 | 19.1% | 1,167 | 939 | 6,272 |
| 1 day | 3,792 | 35 | 0.9% | 605 | 460 | 4,955 |

At five minutes, 82.6 percent of the channel has no width. The band traces the
price line as a hairline and shows no extreme at all. At one day, 0.9 percent
has no width and the channel is wide enough to read across the whole window.
The charts use one-day bars.

The cost of the coarse bar is the warm-up. Twenty one-day bars must close
before the first band appears, so the first twenty days of each asset carry no
channel, and 4,955 of the 6,997 fills land in a bar that has one.

### The band edges, counted over every base

One row per charted base, in fill-count order. The two edge columns count fills
against the band of the bar holding them, on one-day bars at period 20 and
width 2.

| Asset | Fills | Buy | Sell | At or above upper | At or below lower | In a banded bar | First buy VWAP | Final buy VWAP | Index | Window |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| A01 | 925 | 551 | 374 | 20 | 56 | 400 | 1.5915 | 0.652338 | 0.410 | 21 Apr to 25 Sep |
| A02 | 589 | 314 | 275 | 57 | 10 | 454 | 0.10842 | 0.0449093 | 0.414 | 22 Apr to 26 Sep |
| A03 | 537 | 315 | 222 | 13 | 28 | 409 | 0.11868 | 0.0257786 | 0.217 | 9 May to 27 Sep |
| A04 | 378 | 170 | 208 | 21 | 13 | 225 | 0.2478 | 0.277471 | 1.120 | 29 May to 27 Sep |
| A05 | 323 | 172 | 151 | 35 | 28 | 283 | 359.67 | 534.024 | 1.485 | 24 Apr to 26 Sep |
| A06 | 292 | 165 | 127 | 21 | 11 | 218 | 0.01581 | 0.00614089 | 0.388 | 24 Apr to 26 Sep |
| A08 | 274 | 165 | 109 | 20 | 19 | 209 | 0.0508 | 0.0223169 | 0.439 | 23 Apr to 27 Sep |
| A07 | 261 | 171 | 90 | 10 | 14 | 198 | 0.05537 | 0.0320055 | 0.578 | 3 May to 27 Sep |
| A10 | 237 | 122 | 115 | 25 | 24 | 167 | 5.71e-06 | 5.84811e-06 | 1.024 | 12 Apr to 27 Sep |
| A11 | 220 | 95 | 125 | 49 | 7 | 166 | 0.01722 | 0.033729 | 1.959 | 13 Jul to 25 Sep |
| A09 | 215 | 118 | 97 | 18 | 9 | 138 | 1.4622 | 1.38509 | 0.947 | 27 Apr to 27 Sep |
| A12 | 210 | 118 | 92 | 26 | 20 | 181 | 0.009814 | 0.00778479 | 0.793 | 27 Apr to 27 Sep |
| A13 | 205 | 93 | 112 | 21 | 7 | 170 | 15.7253 | 16.3105 | 1.037 | 9 May to 27 Sep |
| A14 | 169 | 108 | 61 | 18 | 31 | 149 | 2308.68 | 2037.61 | 0.883 | 23 Apr to 24 Sep |
| A16 | 157 | 80 | 77 | 13 | 20 | 141 | 273.4 | 243.486 | 0.891 | 2 May to 27 Sep |
| A17 | 155 | 82 | 73 | 10 | 4 | 132 | 0.35136 | 0.364156 | 1.036 | 7 May to 27 Sep |
| A15 | 152 | 107 | 45 | 11 | 39 | 143 | 77782.1 | 70016.9 | 0.900 | 23 Apr to 24 Sep |
| A18 | 148 | 97 | 51 | 18 | 22 | 123 | 1.4278 | 1.39586 | 0.978 | 23 Apr to 26 Sep |
| A19 | 147 | 79 | 68 | 2 | 3 | 40 | 0.00395 | 0.0024861 | 0.629 | 9 Aug to 27 Sep |
| A25 | 121 | 55 | 66 | 19 | 5 | 101 | 1.0673 | 0.850641 | 0.797 | 9 May to 27 Sep |
| A20 | 116 | 44 | 72 | 0 | 1 | 42 | 0.0697757 | 0.0309713 | 0.444 | 9 Aug to 27 Sep |
| A22 | 112 | 56 | 56 | 15 | 22 | 103 | 0.09814 | 0.0884351 | 0.901 | 25 Apr to 26 Sep |
| A24 | 108 | 62 | 46 | 4 | 3 | 73 | 0.02809 | 0.0104166 | 0.371 | 8 Jul to 27 Sep |
| A21 | 107 | 53 | 54 | 10 | 18 | 102 | 9.296 | 9.38981 | 1.010 | 24 Apr to 25 Sep |
| A23 | 101 | 52 | 49 | 11 | 24 | 88 | 85.32 | 84.0803 | 0.985 | 23 Apr to 25 Sep |
| A29 | 98 | 40 | 58 | 15 | 5 | 85 | 0.001603 | 0.00239143 | 1.492 | 7 Jul to 27 Sep |
| A30 | 98 | 40 | 58 | 21 | 2 | 69 | 2.411 | 2.2074 | 0.916 | 29 May to 27 Sep |
| A27 | 87 | 51 | 36 | 9 | 4 | 44 | 0.205737 | 0.197296 | 0.959 | 29 May to 25 Sep |
| A33 | 86 | 36 | 50 | 20 | 0 | 60 | 0.14222 | 0.155404 | 1.093 | 22 Aug to 26 Sep |
| A26 | 85 | 46 | 39 | 6 | 1 | 42 | 0.5153 | 0.471505 | 0.915 | 13 Jul to 27 Sep |
| A28 | 81 | 35 | 46 | 9 | 0 | 46 | 64.42 | 63.7886 | 0.990 | 29 May to 27 Sep |
| A32 | 49 | 15 | 34 | 15 | 0 | 37 | 0.42307 | 0.465448 | 1.100 | 23 Jul to 26 Sep |
| A31 | 42 | 21 | 21 | 9 | 4 | 28 | 0.09457 | 0.0825252 | 0.873 | 29 May to 24 Sep |
| A34 | 36 | 15 | 21 | 7 | 0 | 26 | 0.1696 | 0.179876 | 1.061 | 23 Jul to 26 Sep |
| A35 | 35 | 15 | 20 | 13 | 0 | 27 | 0.1695 | 0.166708 | 0.984 | 13 Jul to 25 Sep |
| A36 | 18 | 6 | 12 | 8 | 0 | 17 | 46.33 | 47.883 | 1.034 | 23 Jul to 25 Sep |
| A37 | 15 | 7 | 8 | 1 | 5 | 12 | 0.05997 | 0.057538 | 0.959 | 23 Jul to 25 Sep |
| A38 | 8 | 2 | 6 | 5 | 1 | 7 | 2148.63 | 2168.26 | 1.009 | 23 Jul to 21 Sep |

Across the 38, 605 fills sit at or above the upper band and 460 at or below the
lower one. A02 and A11 sell into the top most often, at 57 and 49. A01 buys
into the bottom most often, at 56.

## The newest export, beside the one the figures above measure

The figures and tables above were measured on an earlier export. A later one
covers the same account over a longer window. Both sets of numbers are below,
so a reader holding either can tell which is which.

The following sentence is overtaken:

> The export holds 5,709 physical rows and 5,705 body rows. 5,661 of the body
> rows are fills.

The later export holds 7,049 physical rows and 7,045 body rows, and 6,997 of
the body rows are fills on a charted base.

The following sentence is overtaken:

> Of the eight assets with the most fills, six trend down to between 0.4 and
> 0.6. A05 and A04 trend up.

On the later export, five of the eight trend down to between 0.388 and 0.578,
A03 falls further to 0.217, and A05 and A04 still trend up, to 1.485 and
1.120.

Side by side:

| Reading | Earlier export | Later export |
| --- | ---: | ---: |
| Physical rows | 5,709 | 7,049 |
| Body rows | 5,705 | 7,045 |
| Fills on a charted base | 5,661 | 6,997 |
| Charted bases | 38 | 38 |
| First fill | 12 Apr | 12 Apr |
| Last fill | 3 Sep | 27 Sep |
| Rows carrying no fill | 44 | 48 |

The charted bases are the same 38 assets in both. The later export adds 1,336
fills and 24 days, and its extra rows carrying no fill are three more reward
payments and one more cash leg.

One check separates a longer record from a different calculation. Of the 38
first buy VWAP values the table above publishes, 37 come out of the later
export identical to the digit, and the one that differs is A20, published
rounded to 0.069776 against a computed 0.0697757. A different price column or a
different weighting would have moved all 38.

## What this repository holds for these charts

The rows behind the charts take the shape `fetch_all_history_chunked` in
`src/exchange/history_helpers.py` returns for the History tab, one dict per
fill.

The closest committed figure to the buy line is the average entry price
`compute_position_health` derives in `src/exchange/position_health.py` from the
records a venue returns for its own trade history. The two differ, and the
difference matters to a reader holding a chart beside the platform. The average
entry follows the open position only: a buy re-weights it, a sell leaves it
alone, and a full close resets it to zero. The buy line here counts every buy
in the record and never resets.

```python
if t.side == OrderSide.BUY:     # t is one get_my_trades record
    new_qty = qty + t.amount
    if new_qty > 0:
        avg_entry = (qty * avg_entry + t.amount * t.price) / new_qty
    qty = new_qty
elif t.side == OrderSide.SELL:
    qty -= t.amount
    if qty < 1e-12:
        qty = 0.0
        avg_entry = 0.0
```

No committed module computes an average sell price, and none computes a ratio
of one average over the other. Five names were searched across the source, the
harness and the tools, ignoring case, and every one of them returns no file. The
control returns files for both of its terms and none for a coined one.

```
searched in src/, dev_harness/ and tools/, ignoring case
    avg_sell             0 files
    average_sell         0 files
    sell_vwap            0 files
    avg_sell_price       0 files
    sb_ratio             0 files
control
    avg_entry           13 files
    vwap                 6 files
    a coined term        0 files
```

The chart module computes no ratio either. It draws the two lines and stops
there. The ratio table above comes from the export directly, on the same two
columns the charts read.

No committed file produces these charts. A walk of every path any commit ever
added, renamed or deleted reaches 1,626 distinct paths, and exactly one of them
carries the letters vwap: a Simulator test for the price band. A pickaxe over
every Python file in every commit returns nothing for the three names a chart
builder would carry. The charts and the record behind them belong to the
operator. This repository cannot regenerate either.

```
git log --all --diff-filter=ADR --name-only
    1,626 distinct paths
    tests/test_vwap_band_scales_to_price.py     the one vwap name
                                                deleted; not in the tree

git log -S<name> -- '*.py'
    draw_combined         0 commits
    vwap_combined         0 commits
    buy_vwap              0 commits
control
    avg_entry            16 commits
    sync_ytd_trade_count  7 commits
    a coined term         0 commits
```

## The 38 per-asset charts

One chart per charted base, in fill-count order. The table gives what each
chart's two lines start and end at, and the window its axis spans.

| Asset | Fills | Buy | Sell | First buy VWAP | Final buy VWAP | Index | Window |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| A01 | 900 | 538 | 362 | 1.5915 | 0.672605 | 0.423 | 21 Apr to 2 Sep |
| A02 | 495 | 265 | 230 | 0.10842 | 0.044733 | 0.413 | 22 Apr to 3 Sep |
| A03 | 459 | 275 | 184 | 0.11868 | 0.035741 | 0.301 | 9 May to 2 Sep |
| A04 | 322 | 143 | 179 | 0.2478 | 0.298528 | 1.205 | 29 May to 31 Aug |
| A05 | 261 | 140 | 121 | 359.67 | 485.048 | 1.349 | 24 Apr to 3 Sep |
| A06 | 230 | 138 | 92 | 0.01581 | 0.006453 | 0.408 | 24 Apr to 3 Sep |
| A07 | 226 | 155 | 71 | 0.05537 | 0.032580 | 0.588 | 3 May to 3 Sep |
| A08 | 220 | 140 | 80 | 0.0508 | 0.022611 | 0.445 | 23 Apr to 3 Sep |
| A09 | 196 | 113 | 83 | 1.4622 | 1.381809 | 0.945 | 27 Apr to 3 Sep |
| A10 | 191 | 104 | 87 | 5.71e-06 | 5.98261e-06 | 1.048 | 12 Apr to 3 Sep |
| A11 | 178 | 75 | 103 | 0.01722 | 0.029790 | 1.730 | 13 Jul to 3 Sep |
| A12 | 159 | 98 | 61 | 0.009814 | 0.007624 | 0.777 | 27 Apr to 3 Sep |
| A13 | 147 | 69 | 78 | 15.7253 | 14.690407 | 0.934 | 9 May to 1 Sep |
| A14 | 141 | 95 | 46 | 2308.68 | 1996.595 | 0.865 | 23 Apr to 21 Aug |
| A15 | 124 | 95 | 29 | 77782.1 | 68917.999 | 0.886 | 23 Apr to 3 Sep |
| A16 | 124 | 69 | 55 | 273.4 | 242.103 | 0.886 | 2 May to 1 Sep |
| A17 | 119 | 66 | 53 | 0.35136 | 0.361330 | 1.028 | 7 May to 3 Sep |
| A18 | 119 | 82 | 37 | 1.4278 | 1.395015 | 0.977 | 23 Apr to 3 Sep |
| A19 | 113 | 57 | 56 | 0.00395 | 0.002761 | 0.699 | 9 Aug to 31 Aug |
| A20 | 87 | 32 | 55 | 0.069776 | 0.033684 | 0.483 | 9 Aug to 2 Sep |
| A21 | 83 | 43 | 40 | 9.296 | 9.061918 | 0.975 | 24 Apr to 3 Sep |
| A22 | 80 | 43 | 37 | 0.09814 | 0.088151 | 0.898 | 25 Apr to 3 Sep |
| A23 | 77 | 43 | 34 | 85.32 | 82.952844 | 0.972 | 23 Apr to 1 Sep |
| A24 | 75 | 47 | 28 | 0.02809 | 0.011685 | 0.416 | 8 Jul to 31 Aug |
| A25 | 74 | 41 | 33 | 1.0673 | 0.857863 | 0.804 | 9 May to 3 Sep |
| A26 | 73 | 41 | 32 | 0.5153 | 0.475448 | 0.923 | 13 Jul to 30 Aug |
| A27 | 73 | 45 | 28 | 0.205737 | 0.198142 | 0.963 | 29 May to 28 Aug |
| A28 | 66 | 29 | 37 | 64.42 | 61.990016 | 0.962 | 29 May to 30 Aug |
| A29 | 63 | 23 | 40 | 0.001603 | 0.002051 | 1.280 | 7 Jul to 30 Aug |
| A30 | 58 | 27 | 31 | 2.411 | 2.039694 | 0.846 | 29 May to 3 Sep |
| A31 | 25 | 16 | 9 | 0.09457 | 0.082805 | 0.876 | 29 May to 22 Aug |
| A32 | 24 | 8 | 16 | 0.42307 | 0.431039 | 1.019 | 23 Jul to 3 Sep |
| A33 | 23 | 8 | 15 | 0.14222 | 0.145768 | 1.025 | 22 Aug to 3 Sep |
| A34 | 23 | 10 | 13 | 0.1696 | 0.174843 | 1.031 | 23 Jul to 3 Sep |
| A35 | 16 | 9 | 7 | 0.1695 | 0.160515 | 0.947 | 13 Jul to 2 Sep |
| A36 | 6 | 3 | 3 | 46.33 | 46.450791 | 1.003 | 23 Jul to 3 Sep |
| A37 | 6 | 3 | 3 | 0.05997 | 0.058950 | 0.983 | 23 Jul to 16 Aug |
| A38 | 5 | 1 | 4 | 2148.63 | 2148.63 | 1.000 | 23 Jul to 25 Aug |

Those 38 fill counts sum to 5,661, the fill total this part opens with. Eleven
of the 38 end at or above 1.000 and 27 end below it.

The 39 charts of this part, the combined view above included, come from one
module, `vwap_charts`. It reads the export once, groups the fills by asset, and
writes one PNG per charted base.

The line each chart draws is a running mean of price weighted by quantity. The
price is the export's Price at Transaction column and the quantity is its
Quantity Transacted column. Buys and sells accumulate in two separate pairs of
sums, so a fill on one side steps that side's line and leaves the other flat.
The lower panel is the same walk of quantities, added on a buy and taken away
on a sell.

The module is not committed to this repository. Neither is the export it reads.

```python
def load_fills(src: Path):
    """Return the Fill list and a Counter keyed by drop cause."""
    ...
    price = parse_money(r[idx["Price at Transaction"]])
    qty = abs(parse_money(r[idx["Quantity Transacted"]]))
    ...
    fills.append(Fill(asset, when, side, price, qty))


def trajectory(fills):
    """Return times and the running buy VWAP, sell VWAP and net units."""
    ordered = sorted(fills, key=lambda f: f.when)
    t, buy_v, sell_v, held = [], [], [], []
    bn = bd = sn = sd = pos = 0.0
    for f in ordered:
        if f.side == "buy":
            bn += f.price * f.qty
            bd += f.qty
            pos += f.qty
        else:
            sn += f.price * f.qty
            sd += f.qty
            pos -= f.qty
        t.append(f.when)
        buy_v.append(bn / bd if bd > 0 else float("nan"))
        sell_v.append(sn / sd if sd > 0 else float("nan"))
        held.append(pos)
    return t, buy_v, sell_v, held
```

Four of the 38 charts below carry a block of their own. Each one is a chart
where the module takes a turn it does not take for the rest: a logarithmic
price axis, the minor ticks that axis needs, a tick label small enough to go
scientific, and a fill count low enough to mark every step. The other 34 are
drawn by the two functions above and nothing else.

Each of the 38 headings below holds three charts for one base, under one label:
its VWAP chart, its weekly chart and its price trace. The VWAP chart draws the
fills. The weekly chart and the price trace draw the market those fills ran in,
from the Stone Tablet rows the next two sections set out.

A fourth figure follows those three: the venue's own position card for that base,
obscured as the position-card section below sets out. A33 is the one base the
venue supplied no card for, and its heading holds three figures and a line saying
so.

### A01

![A01, 900 fills, a logarithmic price axis, and a net-units panel that empties twice.](figures/vwap_a01.png)

![A01 weekly chart, 34 weekly candles built from 50,380 five-minute rows.](figures/weekly_a01.png)

![A01 price trace, 50,380 five-minute closes across the recorded window.](figures/trace_a01.png)

![A01 position card, with the mark, the name and the code square painted out.](figures/card_a01.png)
The most-traded base of the 38, and one of the two charts whose price axis runs
logarithmic. Both lines step down together to about 1.00 by early May, then to
about 0.67 at the end of June, where the sell line settles below the buy line
and stays there. The net-units panel peaks at 1,037 units in late June and ends
at 209, with two near-vertical drops.

The axis is a measurement, not a choice. A01's fills run from 0.2118 to
2.1805, a span of 10.30, and the module turns the axis logarithmic above eight.
A03 is the only other chart over that line.

```python
lo = min(f.price for f in fills)
hi = max(f.price for f in fills)
if hi / lo > 8:
    ax.set_yscale("log")
```

### A02

![A02, 495 fills, with the sell line above the buy line for the whole window.](figures/vwap_a02.png)

![A02 weekly chart, 24 weekly candles built from 38,463 five-minute rows.](figures/weekly_a02.png)

![A02 price trace, 38,463 five-minute closes across the recorded window.](figures/trace_a02.png)

![A02 position card, with the mark, the name and the code square painted out.](figures/card_a02.png)
The sell line runs above the buy line across the whole window and the two meet
in September. Net units climb to 11,699 in mid-August and end at 4,765.

### A03

![A03, 459 fills, ending at the lowest index of the eight most-traded assets.](figures/vwap_a03.png)

![A03 weekly chart, 22 weekly candles built from 39,186 five-minute rows.](figures/weekly_a03.png)

![A03 price trace, 39,186 five-minute closes across the recorded window.](figures/trace_a03.png)

![A03 position card, with the mark, the name and the code square painted out.](figures/card_a03.png)
The second logarithmic axis, at a span of 13.25. Both lines hold near 0.09
through June, then break down in mid-July. Net units end at the highest point
of the window, 18,510.

A logarithmic axis labels the powers of ten. A03's fills run from 0.01682 to
0.22281, a window holding one of them, and A01's window holds one as well. The
module adds five minor ticks per decade and gives them the same price formatter
as the major ones, which is what puts 0.2000 down to 0.0200 on this axis.

```python
SUBS = (1.0, 2.0, 3.0, 5.0, 7.0)

ax.yaxis.set_minor_locator(LogLocator(base=10.0, subs=SUBS, numticks=99))
ax.yaxis.set_minor_formatter(FuncFormatter(fmt_price))
ax.tick_params(axis="y", which="minor", labelsize=TYPE["cap"]["size"])
```

### A04

![A04, 322 fills, with more sells than buys and both lines rising.](figures/vwap_a04.png)

![A04 weekly chart, 40 weekly candles built from 47,201 five-minute rows.](figures/weekly_a04.png)

![A04 price trace, 47,201 five-minute closes across the recorded window.](figures/trace_a04.png)

![A04 position card, with the mark, the name and the code square painted out.](figures/card_a04.png)
One of eleven charts with more sells than buys. Both lines dip to about 0.22 in
early June and climb after it. Net units step from about 120 to about 500
through late July.

### A05

![A05, 261 fills, the highest final index of the eight most-traded assets.](figures/vwap_a05.png)

![A05 weekly chart, 40 weekly candles built from 79,004 five-minute rows.](figures/weekly_a05.png)

![A05 price trace, 79,004 five-minute closes across the recorded window.](figures/trace_a05.png)

![A05 position card, with the mark, the name and the code square painted out.](figures/card_a05.png)
The buy line rises from 359.67 to 485.05, the largest climb among the eight in
the combined chart. Net units fall to near zero in mid-July, then rebuild to
about 0.20.

### A06

![A06, 230 fills, with the two lines converging from mid-June.](figures/vwap_a06.png)

![A06 weekly chart, 29 weekly candles built from 33,344 five-minute rows.](figures/weekly_a06.png)

![A06 price trace, 33,344 five-minute closes across the recorded window.](figures/trace_a06.png)

![A06 position card, with the mark, the name and the code square painted out.](figures/card_a06.png)
The sell line runs above the buy line until mid-June, then the two converge and
the sell line finishes just below. Net units grow to 47,574 and end at 44,795.

### A07

![A07, 226 fills, with a step down at the start of June.](figures/vwap_a07.png)

![A07 weekly chart, 40 weekly candles built from 49,638 five-minute rows.](figures/weekly_a07.png)

![A07 price trace, 49,638 five-minute closes across the recorded window.](figures/trace_a07.png)

![A07 position card, with the mark, the name and the code square painted out.](figures/card_a07.png)
One step down at the start of June takes the buy line from about 0.044 to about
0.039, and a slow decline follows. The sell line crosses below the buy line at
that same step.

### A08

![A08, 220 fills, with the sell line crossing below the buy line in mid-June.](figures/vwap_a08.png)

![A08 weekly chart, 40 weekly candles built from 52,751 five-minute rows.](figures/weekly_a08.png)

![A08 price trace, 52,751 five-minute closes across the recorded window.](figures/trace_a08.png)

![A08 position card, with the mark, the name and the code square painted out.](figures/card_a08.png)
The crossing holds for the rest of the window. Net units peak at 15,301 in
mid-August, then fall to 9,483.

### A09

![A09, 196 fills, with both lines flat from July onward.](figures/vwap_a09.png)

![A09 weekly chart, 40 weekly candles built from 53,988 five-minute rows.](figures/weekly_a09.png)

![A09 price trace, 53,988 five-minute closes across the recorded window.](figures/trace_a09.png)

![A09 position card, with the mark, the name and the code square painted out.](figures/card_a09.png)
Both lines rise to a peak near 1 May, then fall to a flat run from July. Net
units drop from 140 to about 20 at the end of June and hold near 40 after that.

### A10

![A10, 191 fills, priced near six millionths of a dollar.](figures/vwap_a10.png)

![A10 weekly chart, 40 weekly candles built from 72,287 five-minute rows.](figures/weekly_a10.png)

![A10 price trace, 72,287 five-minute closes across the recorded window.](figures/trace_a10.png)

![A10 position card, with the mark, the name and the code square painted out.](figures/card_a10.png)
The lowest-priced base in the record. The buy line holds near 6.3e-06 from late
April while the fill dots fall from 8.0e-06 to 2.3e-06. Net units spike to
1.02e+08 in late April and end at 3.22e+07.

A10 is the only base whose fills fall under a tenth of a cent. The next lowest
is A29 at 0.001479, so A10 alone reaches the last branch of the tick
formatter, and this is the only chart of the 38 labelled in scientific
notation.

```python
def fmt_price(v, _pos=None) -> str:
    """Format a y-axis price tick, keeping a micro-cap significand visible."""
    if v == 0:
        return "0"
    if abs(v) >= 1000:
        return f"{v:,.0f}"
    if abs(v) >= 1:
        return f"{v:,.2f}"
    if abs(v) >= 0.001:
        return f"{v:.4f}"
    return f"{v:.2e}"
```

### A11

![A11, 178 fills, and the largest rise of the 38.](figures/vwap_a11.png)

![A11 weekly chart, 15 weekly candles built from 26,750 five-minute rows.](figures/weekly_a11.png)

![A11 price trace, 26,750 five-minute closes across the recorded window.](figures/trace_a11.png)

![A11 position card, with the mark, the name and the code square painted out.](figures/card_a11.png)
The buy line rises from 0.01722 to 0.02979, an index of 1.730 and the largest
of the 38. Both lines climb through August. Net units drop across that same
climb, 2,669 down to 1,107.

### A12

![A12, 159 fills, with the sell line dropping below the buy line at the start of June.](figures/vwap_a12.png)

![A12 weekly chart, 40 weekly candles built from 78,332 five-minute rows.](figures/weekly_a12.png)

![A12 price trace, 78,332 five-minute closes across the recorded window.](figures/trace_a12.png)

![A12 position card, with the mark, the name and the code square painted out.](figures/card_a12.png)
The buy line holds near 0.0098 through May and the sell line near 0.0105, then
both step down at the start of June. Net units reach 17,089 in early August and
end at 11,612.

### A13

![A13, 147 fills, with the sell line above the buy line throughout.](figures/vwap_a13.png)

![A13 weekly chart, 40 weekly candles built from 76,386 five-minute rows.](figures/weekly_a13.png)

![A13 price trace, 76,386 five-minute closes across the recorded window.](figures/trace_a13.png)

![A13 position card, with the mark, the name and the code square painted out.](figures/card_a13.png)
The sell line stays above the buy line for the whole window, ending near 15.4
against 14.7. Net units peak at 7.13 and end at 4.71.

### A14

![A14, 141 fills, ending 21 August.](figures/vwap_a14.png)

![A14 weekly chart, 40 weekly candles built from 79,004 five-minute rows.](figures/weekly_a14.png)

![A14 price trace, 79,004 five-minute closes across the recorded window.](figures/trace_a14.png)

![A14 position card, with the mark, the name and the code square painted out.](figures/card_a14.png)
The window closes on 21 August, the earliest close of the 38 apart from A37.
The two lines run together until the start of June, then split, with the sell
line about 100 dollars above through June and July. They meet again in August.

### A15

![A15, 124 fills, with the two lines splitting at the start of June.](figures/vwap_a15.png)

![A15 weekly chart, 40 weekly candles built from 79,005 five-minute rows.](figures/weekly_a15.png)

![A15 price trace, 79,005 five-minute closes across the recorded window.](figures/trace_a15.png)

![A15 position card, with the mark, the name and the code square painted out.](figures/card_a15.png)
The highest-priced base in the record. Both lines hold near 78,000 through May.
At the start of June the sell line drops to about 68,000 and the buy line to
about 72,000, and the gap holds until late August. Net units end at 0.0031.

### A16

![A16, 124 fills, with the sell line above the buy line until mid-June.](figures/vwap_a16.png)

![A16 weekly chart, 40 weekly candles built from 78,992 five-minute rows.](figures/weekly_a16.png)

![A16 price trace, 78,992 five-minute closes across the recorded window.](figures/trace_a16.png)

![A16 position card, with the mark, the name and the code square painted out.](figures/card_a16.png)
The sell line peaks near 312 in mid-May, about 30 dollars above the buy line,
and crosses below it in mid-June. Net units end at 0.34.

### A17

![A17, 119 fills, with both lines nearly flat after June.](figures/vwap_a17.png)

![A17 weekly chart, 40 weekly candles built from 78,992 five-minute rows.](figures/weekly_a17.png)

![A17 price trace, 78,992 five-minute closes across the recorded window.](figures/trace_a17.png)

![A17 position card, with the mark, the name and the code square painted out.](figures/card_a17.png)
The buy line sits near 0.362 and the sell line near 0.382 from mid-June to the
close, a gap of about 0.02 held across eleven weeks.

### A18

![A18, 119 fills, with the two lines almost touching across the window.](figures/vwap_a18.png)

![A18 weekly chart, 40 weekly candles built from 79,004 five-minute rows.](figures/weekly_a18.png)

![A18 price trace, 79,004 five-minute closes across the recorded window.](figures/trace_a18.png)

![A18 position card, with the mark, the name and the code square painted out.](figures/card_a18.png)
The two lines run within about 0.01 of each other for the whole window. Net
units spike to 175 at the start, then hold near 55.

### A19

![A19, 113 fills across 22 days in August.](figures/vwap_a19.png)

![A19 weekly chart, 27 weekly candles built from 15,736 five-minute rows.](figures/weekly_a19.png)

![A19 price trace, 15,736 five-minute closes across the recorded window.](figures/trace_a19.png)

![A19 position card, with the mark, the name and the code square painted out.](figures/card_a19.png)
The second-shortest window of the 38. The buy line falls from 0.00395 to about
0.0030 in the first four days, then flattens. The two lines nearly overlap
after 17 August.

### A20

![A20, 87 fills, with the sell line crossing below the buy line in mid-August.](figures/vwap_a20.png)

![A20 weekly chart, 27 weekly candles built from 21,070 five-minute rows.](figures/weekly_a20.png)

![A20 price trace, 21,070 five-minute closes across the recorded window.](figures/trace_a20.png)

![A20 position card, with the mark, the name and the code square painted out.](figures/card_a20.png)
Buys number 32 against 55 sells. The buy line starts at 0.0698 and falls to
0.0337 across 24 days, the steepest fall of the three assets that start in
August.

### A21

![A21, 83 fills, with both lines turning up in the last two weeks.](figures/vwap_a21.png)

![A21 weekly chart, 40 weekly candles built from 79,003 five-minute rows.](figures/weekly_a21.png)

![A21 price trace, 79,003 five-minute closes across the recorded window.](figures/trace_a21.png)

![A21 position card, with the mark, the name and the code square painted out.](figures/card_a21.png)
The sell line falls below the buy line at the start of June and stays there
until late August, when both turn up and cross again.

### A22

![A22, 80 fills, with the two lines meeting in mid-August.](figures/vwap_a22.png)

![A22 weekly chart, 40 weekly candles built from 79,000 five-minute rows.](figures/weekly_a22.png)

![A22 price trace, 79,000 five-minute closes across the recorded window.](figures/trace_a22.png)

![A22 position card, with the mark, the name and the code square painted out.](figures/card_a22.png)
The sell line runs above the buy line from May to mid-August, then the two
converge near 0.088 and finish together. Net units end at 1,153.

### A23

![A23, 77 fills, with the two lines within about a dollar of each other.](figures/vwap_a23.png)

![A23 weekly chart, 40 weekly candles built from 79,004 five-minute rows.](figures/weekly_a23.png)

![A23 price trace, 79,004 five-minute closes across the recorded window.](figures/trace_a23.png)

![A23 position card, with the mark, the name and the code square painted out.](figures/card_a23.png)
Both lines hold near 85 through May, step to about 83 at the start of June, and
end within a dollar of each other. Net units end below one whole unit, at 0.75.

### A24

![A24, 75 fills, with both lines falling by more than half.](figures/vwap_a24.png)

![A24 weekly chart, 13 weekly candles built from 8,734 five-minute rows.](figures/weekly_a24.png)

![A24 price trace, 8,734 five-minute closes across the recorded window.](figures/trace_a24.png)

![A24 position card, with the mark, the name and the code square painted out.](figures/card_a24.png)
A July starter. The buy line falls from 0.02809 to 0.01168 in eight weeks, and
the sell line converges onto it by the close. Net units end at 13,268.

### A25

![A25, 74 fills, with a step down at the start of June.](figures/vwap_a25.png)

![A25 weekly chart, 40 weekly candles built from 78,996 five-minute rows.](figures/weekly_a25.png)

![A25 price trace, 78,996 five-minute closes across the recorded window.](figures/trace_a25.png)

![A25 position card, with the mark, the name and the code square painted out.](figures/card_a25.png)
The sell line falls from 1.27 to 0.87 across late May and early June, crossing
below the buy line, and the two hold about 0.04 apart afterwards.

### A26

![A26, 73 fills, with the sell line above the buy line from late July.](figures/vwap_a26.png)

![A26 weekly chart, 16 weekly candles built from 25,946 five-minute rows.](figures/weekly_a26.png)

![A26 price trace, 25,946 five-minute closes across the recorded window.](figures/trace_a26.png)

![A26 position card, with the mark, the name and the code square painted out.](figures/card_a26.png)
The sell line jumps from 0.42 to 0.52 in the last week of July, then settles
near 0.50 against a buy line near 0.476.

### A27

![A27, 73 fills, with the sell line about 0.02 above the buy line throughout.](figures/vwap_a27.png)

![A27 weekly chart, 40 weekly candles built from 79,003 five-minute rows.](figures/weekly_a27.png)

![A27 price trace, 79,003 five-minute closes across the recorded window.](figures/trace_a27.png)

![A27 position card, with the mark, the name and the code square painted out.](figures/card_a27.png)
The gap between the two lines holds across the whole window, and both drift
down. Net units grow to 311 and end at 285.

### A28

![A28, 66 fills, with more sells than buys.](figures/vwap_a28.png)

![A28 weekly chart, 35 weekly candles built from 68,265 five-minute rows.](figures/weekly_a28.png)

![A28 price trace, 68,265 five-minute closes across the recorded window.](figures/trace_a28.png)

![A28 position card, with the mark, the name and the code square painted out.](figures/card_a28.png)
29 buys against 37 sells. The sell line peaks near 72.6 in early June and ends
near 67, and the buy line holds between 61 and 65 across the window.

### A29

![A29, 63 fills, with both lines rising through August.](figures/vwap_a29.png)

![A29 weekly chart, 27 weekly candles built from 51,228 five-minute rows.](figures/weekly_a29.png)

![A29 price trace, 51,228 five-minute closes across the recorded window.](figures/trace_a29.png)

![A29 position card, with the mark, the name and the code square painted out.](figures/card_a29.png)
23 buys against 40 sells. The buy line rises from 0.001603 to 0.002051, and the
sell line rises faster, ending about 0.0007 above it. Net units drop across the
window, 29,987 down to 12,032.

### A30

![A30, 58 fills, with both lines falling steadily.](figures/vwap_a30.png)

![A30 weekly chart, 40 weekly candles built from 78,491 five-minute rows.](figures/weekly_a30.png)

![A30 price trace, 78,491 five-minute closes across the recorded window.](figures/trace_a30.png)

![A30 position card, with the mark, the name and the code square painted out.](figures/card_a30.png)
The sell line runs about 0.1 above the buy line from June to late August, then
the two converge near 2.05. Net units end at 26.

### A31

![A31, 25 fills, thin enough for the two lines to carry a dot per step.](figures/vwap_a31.png)

![A31 weekly chart, 40 weekly candles built from 78,993 five-minute rows.](figures/weekly_a31.png)

![A31 price trace, 78,993 five-minute closes across the recorded window.](figures/trace_a31.png)

![A31 position card, with the mark, the name and the code square painted out.](figures/card_a31.png)
The first of the eight thin charts. The sell line starts at 0.1048, steps down
through June and July, and crosses below the buy line in late July. Net units
end at 626.

25 fills is under the module's threshold of 30, so both lines carry a marker at
every step. Sixteen dots sit on the buy line and nine on the sell line. The
seven charts after this one are drawn the same way.

```python
THIN_FILLS = 30

dot = "o" if len(fills) <= THIN_FILLS else None
ax.plot(t, buy_v, color=COLORS["series"][0], lw=2.0, marker=dot,
        markersize=4, label="running buy VWAP")
```

### A32

![A32, 24 fills, with eight buys and sixteen sells.](figures/vwap_a32.png)

![A32 weekly chart, 27 weekly candles built from 52,521 five-minute rows.](figures/weekly_a32.png)

![A32 price trace, 52,521 five-minute closes across the recorded window.](figures/trace_a32.png)

![A32 position card, with the mark, the name and the code square painted out.](figures/card_a32.png)
A thin chart. The buy line holds near 0.4225 until late August, then rises to
0.4310. The sell line jumps from 0.444 to 0.481 in the same week.

### A33

![A33, 23 fills across 12 days, the shortest window of the 38.](figures/vwap_a33.png)

![A33 weekly chart, 27 weekly candles built from 50,503 five-minute rows.](figures/weekly_a33.png)

![A33 price trace, 50,503 five-minute closes across the recorded window.](figures/trace_a33.png)

A33 has no position card. The venue's card set covers the other 37 bases.

A thin chart, and the shortest window here. Eight buys against fifteen sells.
Both lines step up once, on 28 August.

### A34

![A34, 23 fills, with the sell line stepping up sharply on 22 August.](figures/vwap_a34.png)

![A34 weekly chart, 40 weekly candles built from 78,986 five-minute rows.](figures/weekly_a34.png)

![A34 price trace, 78,986 five-minute closes across the recorded window.](figures/trace_a34.png)

![A34 position card, with the mark, the name and the code square painted out.](figures/card_a34.png)
A thin chart. The sell line climbs from 0.1645 to about 0.202, while the buy
line moves from 0.1696 to 0.1748 across the same six weeks.

### A35

![A35, 16 fills, with the buy line flat from late July.](figures/vwap_a35.png)

![A35 weekly chart, 27 weekly candles built from 10,940 five-minute rows.](figures/weekly_a35.png)

![A35 price trace, 10,940 five-minute closes across the recorded window.](figures/trace_a35.png)

![A35 position card, with the mark, the name and the code square painted out.](figures/card_a35.png)
A thin chart. The buy line settles at 0.1605 in late July and holds. The sell
line dips to 0.159 in early August, then steps back to 0.1648.

### A36

![A36, 6 fills, three buys and three sells.](figures/vwap_a36.png)

![A36 weekly chart, 40 weekly candles built from 79,004 five-minute rows.](figures/weekly_a36.png)

![A36 price trace, 79,004 five-minute closes across the recorded window.](figures/trace_a36.png)

![A36 position card, with the mark, the name and the code square painted out.](figures/card_a36.png)
The buy line is nearly flat at 46.33, since all three buys land near one price.
The sell line runs about 5 dollars above it. Net units end at 0.49.

### A37

![A37, 6 fills, closing 16 August.](figures/vwap_a37.png)

![A37 weekly chart, 27 weekly candles built from 49,654 five-minute rows.](figures/weekly_a37.png)

![A37 price trace, 49,654 five-minute closes across the recorded window.](figures/trace_a37.png)

![A37 position card, with the mark, the name and the code square painted out.](figures/card_a37.png)
The earliest close of the 38. Three buys and three sells, all inside four
weeks. The buy line drifts from 0.0600 to 0.0590.

### A38

![A38, 5 fills, one buy and four sells.](figures/vwap_a38.png)

![A38 weekly chart, 27 weekly candles built from 6,257 five-minute rows.](figures/weekly_a38.png)

![A38 price trace, 6,257 five-minute closes across the recorded window.](figures/trace_a38.png)

![A38 position card, with the mark, the name and the code square painted out.](figures/card_a38.png)
The only base in the record with a single buy. One buy makes the buy line a
single horizontal line at 2,148.63 and its index exactly 1.000. The sell line
rises across the four sells, 2,307 up to 2,577. Net units drop across the
window, 0.0114 down to 0.0088.

## Trade grading

One function in `src/trading/trade_grader.py` grades a completed fill, on four
axes and no more. Execution scores against a reference price at the decision,
timing across the prices after the trade, strategy across the shift in the
rolling S/B figure, and outcome against realised profit per unit. An axis whose
price inputs are absent is left out, and the overall figure is the unweighted
mean of the axes that scored — 0.5 when none of them could.

```python
def grade_trade(record: TradeRecord, ctx: PriceContext) -> TradeGrade: ...


def _score_execution(...): ...
def _score_timing(...): ...
def _score_strategic(...): ...
def _score_outcome(...): ...
```

A second function maps that mean to a letter.

```python
def _letter_from_numeric(num: float) -> str:
    if num >= 0.93:
        return "A+"
    elif num >= 0.85:
        return "A"
    elif num >= 0.70:
        return "B"
    elif num >= 0.55:
        return "C"
    elif num >= 0.40:
        return "D"
    else:
        return "F"
```

The market regime rides beside the grade rather than inside it.
`PriceContext.regime_tag` reaches `TradeGrade.regime` and the rationale text,
and it carries no sub-score of its own, which is why a rationale can read five
terms while the grade rests on four.

`grade_trades` runs the batch.

The screen these grades reach is in
[the History tab reference](08-tabs/history.md).

## Gate logs behind each trade

A fill says what happened. The gate log says which decision produced it.

`gate_light_row` in `src/trading/gate_vocabulary.py` returns nineteen lights
for one decision, the scrum bank first and the fold bank second, each entry
carrying its bank, label, state and colour. The History table and the Simulator
draw their lights from that one function, so both surfaces name the same gates
in the same order. The labels themselves, and the indicator readings behind
them, are in [the indicator reference](07-indicators.md).

`lookup_gate_entry` in `src/exchange/history_helpers.py` pairs each fill with
the nearest gate entry for the same bot. The tolerance is 60 seconds either
side of the fill, and a fill that finds an entry inside that window carries its
gate. A fill that finds none carries no gate.

```python
JOIN_TOLERANCE_SECONDS = 60.0


def gate_cell_text(entry: Optional[dict]) -> str:
    if not entry:
        return "no record"
```

A fill with no entry reads "no record" in the Gates column, and its tooltip
says no gate record joined to the trade. Nothing measures coverage over a set
of fills, and nothing names a reason a fill has no gate.

### One gate log per exchange and per sector

A decision is written to the venue it was taken on and the sector of the market
it was taken in. The path is `trade/gate/<exchange>/<sector>/gate.log` under the
log root, and the row carries its own sector in `data.asset_class`, so a row
names the file it is in.

```
~/.acervator_logs/trade/gate/coinbase/crypto/gate.log
~/.acervator_logs/trade/gate/robinhood/crypto/gate.log
~/.acervator_logs/trade/gate/robinhood/stocks/gate.log
```

`src/core/log_paths.py, in gate_log_path` composes it, and `path_segment` folds
each name to one lowercase directory, so a venue id cannot reach a parent
directory through the path. `src/core/logging_engine.py, in
LogManager._gate_writer_for` holds one writer per pair and opens it on the first
decision, so every bot on one venue trading one sector appends to a single file.

The sector reaches the writer from the bot.
`src/trading/scrumming/snapshots.py, in _emit_gate_decision_at_fire` reads
`BotContainer._asset_class` for the traded symbol, which answers the sector the
venue's market recording holds, then the sector the bot's own config declares,
then crypto. The Simulator answers the same question through
`src/simulator/sim_bus.py, in sim_asset_class`, so a sim decision is filed where
its live twin is filed.

Each pair's active file rotates at 50 MB and keeps five backups, so one pair
bounds at 300 MB and each further pair adds 300 MB of its own.

#### Reading every decision, wherever it was written

`src/core/log_paths.py, in gate_log_files` lists every gate log once: the
pre-split file while it is still there, then each pair's archive members,
rotations and active file. Every reader goes through it.

| reader | what it draws |
|---|---|
| `src/trading/live_log_reader.py, in live_gate_decisions` | the entries the History tab and the parity tools join against |
| `src/exchange/history_helpers.py, in build_page_gate_index` | the per-page bot-and-minute index |
| `src/gui/history_tab.py, in read_join_indexes` | the same index, read off the GUI thread |
| `src/simulator/gate_log_source.py, in GateLogSource.files` | the Simulator's read-only `GateRow` records |
| `src/simulator/sim_bus.py, in sim_log_paths` | the paths the parity report prints |
| `tools/capture_live_baseline.py, in gate_members` | the baseline snapshot's latch distribution |

#### What became of the records written before the split

`src/core/logging_engine.py, in migrate_legacy_gate_logs` carries them, once,
when the first `LogManager` of a build with this layout is built. It runs before
any gate writer opens, so no handle is held on a file it moves.

Each pre-split file leaves every reader's view in one rename before any bucket
file appears, under a `.consumed-` name the archive member will take. A file
whose records all belong to one pair is then renamed again into that pair's
archive, with no byte copied. A file holding more than one pair is streamed into
a `.pending-` file per pair, and each is promoted in turn. A carry cut short
leaves the `.consumed-` name in place and the next `LogManager` finishes it, so
a decision is never recorded twice.

An archive member never rotates and nothing prunes it. The records are
decisions behind real fills, not a running stream.

Measured over a full-size copy of the operator's own gate records, with no write
to his tree:

```
in     6 files   167,947 decisions   268,798,267 bytes
out    7 files   167,947 decisions   268,798,267 bytes   1.81 seconds

gate/coinbase/crypto/archive/     6 files, the five rotations and the active file
gate/fleet_sim/crypto/archive/    1 file, 136 decisions an older simulator wrote
```

The byte totals are equal because the carry copies each line as the bytes on
disk hold it. The two destinations are the two values the `exchange` field
carries across those records: `coinbase` on 167,811 of them and `fleet_sim` on
136. No record carried a sector, so every one is filed under the sector
`src/core/logging_engine.py, in default_gate_sector` answers, which is the
sector `BotContainer._asset_class` answers for a market the recording labels
none.

Two controls were read on the same copy. A comparison of the line sets before
and against after reports `lost=1` when one decision is removed from the result
and `duplicated=1` when one is repeated, so the equal reading above is a
measurement. A carry interrupted after its first pair was promoted reads 3,245
of 3,381 decisions readable, 136 lost and 0 duplicated; the next `LogManager`
reads 3,381, 0 lost and 0 duplicated.

## Weekly candles behind the fills

The 38 charts above draw fills. This set draws the market those fills ran in.
Each panel is one charted base and carries the same label, ten panels to a page.

The bars are built here, not fetched. `weekly_bars` in
`tools/build_product_manual.py` groups a base's five-minute Stone Tablet rows by
the Monday 00:00 UTC that `week_start_ms` returns for each stamp. Each group
gives one bar: the first row's open, the highest high across the group, the
lowest low across the group, and the last row's close. A week the venue recorded
no trade in produces no bar.

One week of one series checks that rule against hand arithmetic. On A05, the
week opening 2026-05-18 holds 2,016 five-minute rows.

```
weekly_bars   open 535.96  high 688.52  low 515.24  close 662.04
by hand       open 535.96  high 688.52  low 515.24  close 662.04
control       a last-open rule returns 662.10 for the open
```

The control matters because three of the four figures survive a wrong grouping.
A rule taking the last open rather than the first moves only the open, and the
comparison reports it.

A panel's price axis turns logarithmic when its highest high exceeds its lowest
low more than eightfold, the same rule the per-asset charts above use.

One sentence above is overtaken. It is quoted whole, and the sentence that
replaces it follows.

> Each panel is one charted base and carries the same label, ten panels to a page.

Each charted base has a weekly chart of its own, and it sits in that base's group
above, beside that base's VWAP chart.

`_write_asset_weekly` in `tools/build_product_manual.py` writes one figure per
base, named for the base's label and titled with it.

## The price at the finest resolution the record carries

Five minutes is the finest resolution the Stone Tablets hold.
`StoneTabletsRegistry` in `src/trading/stone_tablets/registry.py` stores every
tablet at that step and rolls every longer timeframe up from it, so no finer
price exists in this repository. These panels plot the close of every
five-minute candle across the recorded window, one line per charted base.

The weekly bars above and these lines read the same rows and answer different
questions. A weekly bar hides what happens inside its week, and inside the week
is where the Scrum and Fold cycle works. A week that opens and closes at the
same price can still hold the swings the engine sells into and buys back from.

Each charted base has a price trace of its own, and it sits in that base's group
above, under the same label as that base's VWAP chart and weekly chart.

`_write_asset_traces` in `tools/build_product_manual.py` writes one figure per
base, from the same five-minute rows the weekly bars are built from.

## The venue's own position cards

The venue renders one card per open position. 37 cards cover the 38 charted
bases, and A33 has none. Each card carries the entry price the venue holds for
the open position, the current price, and the gain or loss in dollars and in
percent.

A card's entry price is not the buy line of the chart above it. The card follows
the open position only: a buy re-weights it, a sell leaves it alone, and a full
close resets it to zero. The buy line counts every buy in the record and never
resets. That is the same difference this part sets out against
`compute_position_health` in `src/exchange/position_health.py`.

Each card is obscured before it is committed. `obscured_placard` in
`tools/build_product_manual.py` converts the card to grey, paints the asset mark
and the asset name out with the card's own ground colour, paints the code square
out with the footer's ground colour, and writes the label where the name was.
The venue's own figures are left as the venue rendered them.

`_write_asset_placards` in `tools/build_product_manual.py` writes one card per
base, named for that base's label. Each card is embedded under its own heading
above, beside that base's three charts. A base the venue supplied no card for is
reported absent and stops the build, so no heading can carry another base's card.
