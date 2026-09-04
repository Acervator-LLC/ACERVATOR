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

The running figure is a streaming sum of Subtotal over a streaming sum of
quantity, both carried as floats. Run against the same rows with Python's exact
`Fraction`, the two paths agree to 3.63e-15 across 26 assets, so the float path
loses nothing a chart can show.

One control separates a weighted mean from an unweighted one. One unit bought
at $10 and three at $20 give 17.50 by hand, and both the float path and the
`Fraction` path return 17.50. An unweighted mean of the two prices returns
15.00. An implementation that forgot to weight by quantity would open a gap of
2.50 on that case rather than pass unnoticed.

## What the combined chart plots

Each asset has a chart of its running buy VWAP against time. The line is the
trajectory of the average as accumulation proceeds, and the shape of that
trajectory is the reading. An end-of-period ratio of sell VWAP over buy VWAP
answers a different question and is not what these charts carry.

The combined chart indexes every asset to its own first buy VWAP and plots the
running buy VWAP divided by that first value, so an asset priced in cents and
an asset priced in thousands share one axis and one scale.

Of the eight assets with the most fills, six trend down to between 0.4 and 0.6.
ZEC and ALLO trend up.

Read the line as what it is. A falling running buy VWAP says the average cost
of the base units now held fell as more were bought. It is not profit. It does
not become profit until units are sold, and the ratio carries no sale in it at
all.

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

## Trade grading

`grade_trade` in `src/trading/trade_grader.py` grades one fill on four axes and
no more: `_score_execution` against a reference price at the decision,
`_score_timing` across the prices after the trade, `_score_strategic` across
the shift in the rolling S/B figure, and `_score_outcome` against realised
profit per unit. An axis whose `PriceContext` inputs are absent is left out.
`TradeGrade.overall_numeric` is the unweighted mean of the axes that scored,
and 0.5 when none of them could.

`_letter_from_numeric` maps that mean to `A+`, `A`, `B`, `C`, `D` or `F`.
`PriceContext.regime_tag` reaches `TradeGrade.regime` and the rationale text
carrying no sub-score of its own, which is why a rationale can read five terms
while the grade rests on four. `grade_trades` runs the batch.

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

`classify_trades` in `src/trading/gate_coverage.py` pairs each fill with the
nearest gate entry for the same bot and gives it one `GateStatus`.
`DEFAULT_TOLERANCE_S` is 300 seconds, one five-minute candle either side of the
fill. A fill that finds an entry inside that window is `HAS_GATE`, and
`GateCoverageReport.coverage_pct` counts only those.

The five remaining statuses each name a different reason a fill has no gate.
`BEFORE_LOGGING` marks a fill older than
the first gate entry. `LOG_GAP` marks a fill sitting inside a silence longer
than `LOG_GAP_THRESHOLD_S`, six candles. `NO_GATE_IN_TOLERANCE` marks a bot
that logged either side of the fill but not inside the window.
`NO_GATE_FOR_BOT` marks a bot with no entries at all, and `NO_GATE_DATA` marks
a run given no gate log. A fill the log could not have seen and a fill the log
should have seen are different findings, and the report keeps them apart rather
than folding both into one coverage shortfall. `format_coverage_lines` renders
the counts, one line per status.
