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

Fills per asset, most to fewest: RAVE 900, CHIP 495, BILL 459, ALLO 322, ZEC
261, KAT 230, BIO 226, SPK 220, ORCA 196, BONK 191, CAP 178, PENGU 159, VVV
147, ETH 141, BTC 124, TAO 124, ONDO 119, XRP 119, IMU 113, BICO 87, LINK 83,
DOGE 80, SOL 77, GROVE 75, SUI 74, RE 73, XLM 73, HYPE 66, PUMP 63, NEAR 58,
HBAR 25, AERO 24, ENA 23, ADA 23, AGLD 16, LTC 6, WLFI 6, LSETH 5. Those 38
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
ZEC and ALLO trend up.

Read the line as what it is. A falling running buy VWAP says the average cost
of the base units now held fell as more were bought. It is not profit. It does
not become profit until units are sold, and the index carries no sale in it at
all.

![The running buy VWAP of the eight assets with the most fills, each divided by its own first buy VWAP.](../../artifacts/vwap-charts/vwap_combined.png)

The eight lines are the eight assets with the most fills. Each one is that
asset's running buy VWAP divided by its own first buy VWAP, which puts BONK at
5.71e-06 and ZEC at 359.67 on one axis and one scale. The rule at 1.0 marks the
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
| RAVE | 900 | 1.5915 | 0.672605 | 0.423 |
| CHIP | 495 | 0.10842 | 0.044733 | 0.413 |
| BILL | 459 | 0.11868 | 0.035741 | 0.301 |
| ALLO | 322 | 0.2478 | 0.298528 | 1.205 |
| ZEC | 261 | 359.67 | 485.048 | 1.349 |
| KAT | 230 | 0.01581 | 0.006453 | 0.408 |
| BIO | 226 | 0.05537 | 0.032580 | 0.588 |
| SPK | 220 | 0.0508 | 0.022611 | 0.445 |

Six of the eight end below 1.0 and two end above it. Of the six, five land
between 0.408 and 0.588, and BILL lands at 0.301.

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
exactly on it. PUMP is the highest at 1.351 and BICO the lowest at 0.879.

| Asset | Buys | Sells | Buy VWAP | Sell VWAP | Ratio |
| --- | ---: | ---: | ---: | ---: | ---: |
| RAVE | 538 | 362 | 0.672605 | 0.610801 | 0.908 |
| CHIP | 265 | 230 | 0.044733 | 0.0453964 | 1.015 |
| BILL | 275 | 184 | 0.0357413 | 0.040867 | 1.143 |
| ALLO | 143 | 179 | 0.298528 | 0.328486 | 1.100 |
| ZEC | 140 | 121 | 485.048 | 536.675 | 1.106 |
| KAT | 138 | 92 | 0.00645325 | 0.00627872 | 0.973 |
| BIO | 155 | 71 | 0.0325805 | 0.0317443 | 0.974 |
| SPK | 140 | 80 | 0.0226113 | 0.0212018 | 0.938 |
| ORCA | 113 | 83 | 1.38181 | 1.34298 | 0.972 |
| BONK | 104 | 87 | 5.98261e-06 | 6.10717e-06 | 1.021 |
| CAP | 75 | 103 | 0.0297901 | 0.036577 | 1.228 |
| PENGU | 98 | 61 | 0.00762374 | 0.00758363 | 0.995 |
| VVV | 69 | 78 | 14.6904 | 15.4413 | 1.051 |
| ETH | 95 | 46 | 1996.6 | 2047.62 | 1.026 |
| BTC | 95 | 29 | 68918 | 68393.6 | 0.992 |
| TAO | 69 | 55 | 242.103 | 238.855 | 0.987 |
| ONDO | 66 | 53 | 0.36133 | 0.38167 | 1.056 |
| XRP | 82 | 37 | 1.39501 | 1.40129 | 1.005 |
| IMU | 57 | 56 | 0.00276124 | 0.00283892 | 1.028 |
| BICO | 32 | 55 | 0.0336835 | 0.0296231 | 0.879 |
| LINK | 43 | 40 | 9.06192 | 9.27909 | 1.024 |
| DOGE | 43 | 37 | 0.0881513 | 0.0882367 | 1.001 |
| SOL | 43 | 34 | 82.9528 | 83.4024 | 1.005 |
| GROVE | 47 | 28 | 0.0116845 | 0.0116532 | 0.997 |
| SUI | 41 | 33 | 0.857863 | 0.824958 | 0.962 |
| RE | 41 | 32 | 0.475448 | 0.497449 | 1.046 |
| XLM | 45 | 28 | 0.198142 | 0.21519 | 1.086 |
| HYPE | 29 | 37 | 61.99 | 66.8959 | 1.079 |
| PUMP | 23 | 40 | 0.00205112 | 0.00277049 | 1.351 |
| NEAR | 27 | 31 | 2.03969 | 2.09155 | 1.025 |
| HBAR | 16 | 9 | 0.0828047 | 0.0787786 | 0.951 |
| AERO | 8 | 16 | 0.431039 | 0.480832 | 1.116 |
| ENA | 8 | 15 | 0.145768 | 0.164984 | 1.132 |
| ADA | 10 | 13 | 0.174843 | 0.202243 | 1.157 |
| AGLD | 9 | 7 | 0.160515 | 0.164726 | 1.026 |
| LTC | 3 | 3 | 46.4508 | 51.1833 | not read |
| WLFI | 3 | 3 | 0.0589505 | 0.0591535 | not read |
| LSETH | 1 | 4 | 2148.63 | 2576.19 | not read |

Three rows carry no ratio and the reason is the fill counts beside them. LSETH
has one buy, so its buy figure is a single price and not an average of anything.
LTC and WLFI have three buys and three sells each. A mean over three fills moves
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

Three XLM rows carry a Subtotal that rounds to $0.00 against a quantity that is
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
artifacts/manual-figures/       the manual's own 38 images
artifacts/vwap-charts/
    vwap_combined.png           the eight-line combined chart
    vwap_<ASSET>.png            one per charted base, 38 of them
```

## How to read a per-asset chart

Every chart carries two panels over one time axis.

The upper panel draws every fill as a dot at its price, buys in
`COLORS["series"][0]` and sells in `COLORS["series"][5]`. Two lines cross it:
the running buy VWAP and the running sell VWAP, in those same two colours. Each
line steps at a fill of its own side and holds flat across a fill of the other
side. The price axis turns logarithmic when the highest fill price exceeds the
lowest more than eightfold, which covers RAVE at 10.30 and BILL at 13.25 and no
other asset. A chart of 30 fills or fewer marks each step with a dot: HBAR,
AERO, ENA, ADA, AGLD, LTC, WLFI and LSETH.

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
| RAVE | 900 | 538 | 362 | 1.5915 | 0.672605 | 0.423 | 21 Apr to 2 Sep |
| CHIP | 495 | 265 | 230 | 0.10842 | 0.044733 | 0.413 | 22 Apr to 3 Sep |
| BILL | 459 | 275 | 184 | 0.11868 | 0.035741 | 0.301 | 9 May to 2 Sep |
| ALLO | 322 | 143 | 179 | 0.2478 | 0.298528 | 1.205 | 29 May to 31 Aug |
| ZEC | 261 | 140 | 121 | 359.67 | 485.048 | 1.349 | 24 Apr to 3 Sep |
| KAT | 230 | 138 | 92 | 0.01581 | 0.006453 | 0.408 | 24 Apr to 3 Sep |
| BIO | 226 | 155 | 71 | 0.05537 | 0.032580 | 0.588 | 3 May to 3 Sep |
| SPK | 220 | 140 | 80 | 0.0508 | 0.022611 | 0.445 | 23 Apr to 3 Sep |
| ORCA | 196 | 113 | 83 | 1.4622 | 1.381809 | 0.945 | 27 Apr to 3 Sep |
| BONK | 191 | 104 | 87 | 5.71e-06 | 5.98261e-06 | 1.048 | 12 Apr to 3 Sep |
| CAP | 178 | 75 | 103 | 0.01722 | 0.029790 | 1.730 | 13 Jul to 3 Sep |
| PENGU | 159 | 98 | 61 | 0.009814 | 0.007624 | 0.777 | 27 Apr to 3 Sep |
| VVV | 147 | 69 | 78 | 15.7253 | 14.690407 | 0.934 | 9 May to 1 Sep |
| ETH | 141 | 95 | 46 | 2308.68 | 1996.595 | 0.865 | 23 Apr to 21 Aug |
| BTC | 124 | 95 | 29 | 77782.1 | 68917.999 | 0.886 | 23 Apr to 3 Sep |
| TAO | 124 | 69 | 55 | 273.4 | 242.103 | 0.886 | 2 May to 1 Sep |
| ONDO | 119 | 66 | 53 | 0.35136 | 0.361330 | 1.028 | 7 May to 3 Sep |
| XRP | 119 | 82 | 37 | 1.4278 | 1.395015 | 0.977 | 23 Apr to 3 Sep |
| IMU | 113 | 57 | 56 | 0.00395 | 0.002761 | 0.699 | 9 Aug to 31 Aug |
| BICO | 87 | 32 | 55 | 0.069776 | 0.033684 | 0.483 | 9 Aug to 2 Sep |
| LINK | 83 | 43 | 40 | 9.296 | 9.061918 | 0.975 | 24 Apr to 3 Sep |
| DOGE | 80 | 43 | 37 | 0.09814 | 0.088151 | 0.898 | 25 Apr to 3 Sep |
| SOL | 77 | 43 | 34 | 85.32 | 82.952844 | 0.972 | 23 Apr to 1 Sep |
| GROVE | 75 | 47 | 28 | 0.02809 | 0.011685 | 0.416 | 8 Jul to 31 Aug |
| SUI | 74 | 41 | 33 | 1.0673 | 0.857863 | 0.804 | 9 May to 3 Sep |
| RE | 73 | 41 | 32 | 0.5153 | 0.475448 | 0.923 | 13 Jul to 30 Aug |
| XLM | 73 | 45 | 28 | 0.205737 | 0.198142 | 0.963 | 29 May to 28 Aug |
| HYPE | 66 | 29 | 37 | 64.42 | 61.990016 | 0.962 | 29 May to 30 Aug |
| PUMP | 63 | 23 | 40 | 0.001603 | 0.002051 | 1.280 | 7 Jul to 30 Aug |
| NEAR | 58 | 27 | 31 | 2.411 | 2.039694 | 0.846 | 29 May to 3 Sep |
| HBAR | 25 | 16 | 9 | 0.09457 | 0.082805 | 0.876 | 29 May to 22 Aug |
| AERO | 24 | 8 | 16 | 0.42307 | 0.431039 | 1.019 | 23 Jul to 3 Sep |
| ENA | 23 | 8 | 15 | 0.14222 | 0.145768 | 1.025 | 22 Aug to 3 Sep |
| ADA | 23 | 10 | 13 | 0.1696 | 0.174843 | 1.031 | 23 Jul to 3 Sep |
| AGLD | 16 | 9 | 7 | 0.1695 | 0.160515 | 0.947 | 13 Jul to 2 Sep |
| LTC | 6 | 3 | 3 | 46.33 | 46.450791 | 1.003 | 23 Jul to 3 Sep |
| WLFI | 6 | 3 | 3 | 0.05997 | 0.058950 | 0.983 | 23 Jul to 16 Aug |
| LSETH | 5 | 1 | 4 | 2148.63 | 2148.63 | 1.000 | 23 Jul to 25 Aug |

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

### RAVE

![RAVE, 900 fills, a logarithmic price axis, and a net-units panel that empties twice.](../../artifacts/vwap-charts/vwap_RAVE.png)

The most-traded base of the 38, and one of the two charts whose price axis runs
logarithmic. Both lines step down together to about 1.00 by early May, then to
about 0.67 at the end of June, where the sell line settles below the buy line
and stays there. The net-units panel peaks at 1,037 units in late June and ends
at 209, with two near-vertical drops.

The axis is a measurement, not a choice. RAVE's fills run from 0.2118 to
2.1805, a span of 10.30, and the module turns the axis logarithmic above eight.
BILL is the only other chart over that line.

```python
lo = min(f.price for f in fills)
hi = max(f.price for f in fills)
if hi / lo > 8:
    ax.set_yscale("log")
```

### CHIP

![CHIP, 495 fills, with the sell line above the buy line for the whole window.](../../artifacts/vwap-charts/vwap_CHIP.png)

The sell line runs above the buy line across the whole window and the two meet
in September. Net units climb to 11,699 in mid-August and end at 4,765.

### BILL

![BILL, 459 fills, ending at the lowest index of the eight most-traded assets.](../../artifacts/vwap-charts/vwap_BILL.png)

The second logarithmic axis, at a span of 13.25. Both lines hold near 0.09
through June, then break down in mid-July. Net units end at the highest point
of the window, 18,510.

A logarithmic axis labels the powers of ten. BILL's fills run from 0.01682 to
0.22281, a window holding one of them, and RAVE's window holds one as well. The
module adds five minor ticks per decade and gives them the same price formatter
as the major ones, which is what puts 0.2000 down to 0.0200 on this axis.

```python
SUBS = (1.0, 2.0, 3.0, 5.0, 7.0)

ax.yaxis.set_minor_locator(LogLocator(base=10.0, subs=SUBS, numticks=99))
ax.yaxis.set_minor_formatter(FuncFormatter(fmt_price))
ax.tick_params(axis="y", which="minor", labelsize=TYPE["cap"]["size"])
```

### ALLO

![ALLO, 322 fills, with more sells than buys and both lines rising.](../../artifacts/vwap-charts/vwap_ALLO.png)

One of eleven charts with more sells than buys. Both lines dip to about 0.22 in
early June and climb after it. Net units step from about 120 to about 500
through late July.

### ZEC

![ZEC, 261 fills, the highest final index of the eight most-traded assets.](../../artifacts/vwap-charts/vwap_ZEC.png)

The buy line rises from 359.67 to 485.05, the largest climb among the eight in
the combined chart. Net units fall to near zero in mid-July, then rebuild to
about 0.20.

### KAT

![KAT, 230 fills, with the two lines converging from mid-June.](../../artifacts/vwap-charts/vwap_KAT.png)

The sell line runs above the buy line until mid-June, then the two converge and
the sell line finishes just below. Net units grow to 47,574 and end at 44,795.

### BIO

![BIO, 226 fills, with a step down at the start of June.](../../artifacts/vwap-charts/vwap_BIO.png)

One step down at the start of June takes the buy line from about 0.044 to about
0.039, and a slow decline follows. The sell line crosses below the buy line at
that same step.

### SPK

![SPK, 220 fills, with the sell line crossing below the buy line in mid-June.](../../artifacts/vwap-charts/vwap_SPK.png)

The crossing holds for the rest of the window. Net units peak at 15,301 in
mid-August, then fall to 9,483.

### ORCA

![ORCA, 196 fills, with both lines flat from July onward.](../../artifacts/vwap-charts/vwap_ORCA.png)

Both lines rise to a peak near 1 May, then fall to a flat run from July. Net
units drop from 140 to about 20 at the end of June and hold near 40 after that.

### BONK

![BONK, 191 fills, priced near six millionths of a dollar.](../../artifacts/vwap-charts/vwap_BONK.png)

The lowest-priced base in the record. The buy line holds near 6.3e-06 from late
April while the fill dots fall from 8.0e-06 to 2.3e-06. Net units spike to
1.02e+08 in late April and end at 3.22e+07.

BONK is the only base whose fills fall under a tenth of a cent. The next lowest
is PUMP at 0.001479, so BONK alone reaches the last branch of the tick
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

### CAP

![CAP, 178 fills, and the largest rise of the 38.](../../artifacts/vwap-charts/vwap_CAP.png)

The buy line rises from 0.01722 to 0.02979, an index of 1.730 and the largest
of the 38. Both lines climb through August. Net units drop across that same
climb, 2,669 down to 1,107.

### PENGU

![PENGU, 159 fills, with the sell line dropping below the buy line at the start of June.](../../artifacts/vwap-charts/vwap_PENGU.png)

The buy line holds near 0.0098 through May and the sell line near 0.0105, then
both step down at the start of June. Net units reach 17,089 in early August and
end at 11,612.

### VVV

![VVV, 147 fills, with the sell line above the buy line throughout.](../../artifacts/vwap-charts/vwap_VVV.png)

The sell line stays above the buy line for the whole window, ending near 15.4
against 14.7. Net units peak at 7.13 and end at 4.71.

### ETH

![ETH, 141 fills, ending 21 August.](../../artifacts/vwap-charts/vwap_ETH.png)

The window closes on 21 August, the earliest close of the 38 apart from WLFI.
The two lines run together until the start of June, then split, with the sell
line about 100 dollars above through June and July. They meet again in August.

### BTC

![BTC, 124 fills, with the two lines splitting at the start of June.](../../artifacts/vwap-charts/vwap_BTC.png)

The highest-priced base in the record. Both lines hold near 78,000 through May.
At the start of June the sell line drops to about 68,000 and the buy line to
about 72,000, and the gap holds until late August. Net units end at 0.0031.

### TAO

![TAO, 124 fills, with the sell line above the buy line until mid-June.](../../artifacts/vwap-charts/vwap_TAO.png)

The sell line peaks near 312 in mid-May, about 30 dollars above the buy line,
and crosses below it in mid-June. Net units end at 0.34.

### ONDO

![ONDO, 119 fills, with both lines nearly flat after June.](../../artifacts/vwap-charts/vwap_ONDO.png)

The buy line sits near 0.362 and the sell line near 0.382 from mid-June to the
close, a gap of about 0.02 held across eleven weeks.

### XRP

![XRP, 119 fills, with the two lines almost touching across the window.](../../artifacts/vwap-charts/vwap_XRP.png)

The two lines run within about 0.01 of each other for the whole window. Net
units spike to 175 at the start, then hold near 55.

### IMU

![IMU, 113 fills across 22 days in August.](../../artifacts/vwap-charts/vwap_IMU.png)

The second-shortest window of the 38. The buy line falls from 0.00395 to about
0.0030 in the first four days, then flattens. The two lines nearly overlap
after 17 August.

### BICO

![BICO, 87 fills, with the sell line crossing below the buy line in mid-August.](../../artifacts/vwap-charts/vwap_BICO.png)

Buys number 32 against 55 sells. The buy line starts at 0.0698 and falls to
0.0337 across 24 days, the steepest fall of the three assets that start in
August.

### LINK

![LINK, 83 fills, with both lines turning up in the last two weeks.](../../artifacts/vwap-charts/vwap_LINK.png)

The sell line falls below the buy line at the start of June and stays there
until late August, when both turn up and cross again.

### DOGE

![DOGE, 80 fills, with the two lines meeting in mid-August.](../../artifacts/vwap-charts/vwap_DOGE.png)

The sell line runs above the buy line from May to mid-August, then the two
converge near 0.088 and finish together. Net units end at 1,153.

### SOL

![SOL, 77 fills, with the two lines within about a dollar of each other.](../../artifacts/vwap-charts/vwap_SOL.png)

Both lines hold near 85 through May, step to about 83 at the start of June, and
end within a dollar of each other. Net units end below one whole unit, at 0.75.

### GROVE

![GROVE, 75 fills, with both lines falling by more than half.](../../artifacts/vwap-charts/vwap_GROVE.png)

A July starter. The buy line falls from 0.02809 to 0.01168 in eight weeks, and
the sell line converges onto it by the close. Net units end at 13,268.

### SUI

![SUI, 74 fills, with a step down at the start of June.](../../artifacts/vwap-charts/vwap_SUI.png)

The sell line falls from 1.27 to 0.87 across late May and early June, crossing
below the buy line, and the two hold about 0.04 apart afterwards.

### RE

![RE, 73 fills, with the sell line above the buy line from late July.](../../artifacts/vwap-charts/vwap_RE.png)

The sell line jumps from 0.42 to 0.52 in the last week of July, then settles
near 0.50 against a buy line near 0.476.

### XLM

![XLM, 73 fills, with the sell line about 0.02 above the buy line throughout.](../../artifacts/vwap-charts/vwap_XLM.png)

The gap between the two lines holds across the whole window, and both drift
down. Net units grow to 311 and end at 285.

### HYPE

![HYPE, 66 fills, with more sells than buys.](../../artifacts/vwap-charts/vwap_HYPE.png)

29 buys against 37 sells. The sell line peaks near 72.6 in early June and ends
near 67, and the buy line holds between 61 and 65 across the window.

### PUMP

![PUMP, 63 fills, with both lines rising through August.](../../artifacts/vwap-charts/vwap_PUMP.png)

23 buys against 40 sells. The buy line rises from 0.001603 to 0.002051, and the
sell line rises faster, ending about 0.0007 above it. Net units drop across the
window, 29,987 down to 12,032.

### NEAR

![NEAR, 58 fills, with both lines falling steadily.](../../artifacts/vwap-charts/vwap_NEAR.png)

The sell line runs about 0.1 above the buy line from June to late August, then
the two converge near 2.05. Net units end at 26.

### HBAR

![HBAR, 25 fills, thin enough for the two lines to carry a dot per step.](../../artifacts/vwap-charts/vwap_HBAR.png)

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

### AERO

![AERO, 24 fills, with eight buys and sixteen sells.](../../artifacts/vwap-charts/vwap_AERO.png)

A thin chart. The buy line holds near 0.4225 until late August, then rises to
0.4310. The sell line jumps from 0.444 to 0.481 in the same week.

### ENA

![ENA, 23 fills across 12 days, the shortest window of the 38.](../../artifacts/vwap-charts/vwap_ENA.png)

A thin chart, and the shortest window here. Eight buys against fifteen sells.
Both lines step up once, on 28 August.

### ADA

![ADA, 23 fills, with the sell line stepping up sharply on 22 August.](../../artifacts/vwap-charts/vwap_ADA.png)

A thin chart. The sell line climbs from 0.1645 to about 0.202, while the buy
line moves from 0.1696 to 0.1748 across the same six weeks.

### AGLD

![AGLD, 16 fills, with the buy line flat from late July.](../../artifacts/vwap-charts/vwap_AGLD.png)

A thin chart. The buy line settles at 0.1605 in late July and holds. The sell
line dips to 0.159 in early August, then steps back to 0.1648.

### LTC

![LTC, 6 fills, three buys and three sells.](../../artifacts/vwap-charts/vwap_LTC.png)

The buy line is nearly flat at 46.33, since all three buys land near one price.
The sell line runs about 5 dollars above it. Net units end at 0.49.

### WLFI

![WLFI, 6 fills, closing 16 August.](../../artifacts/vwap-charts/vwap_WLFI.png)

The earliest close of the 38. Three buys and three sells, all inside four
weeks. The buy line drifts from 0.0600 to 0.0590.

### LSETH

![LSETH, 5 fills, one buy and four sells.](../../artifacts/vwap-charts/vwap_LSETH.png)

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
