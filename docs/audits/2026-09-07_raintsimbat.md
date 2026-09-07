# RAIntSimBat — what is real in the archive

Reference. The operator's directive of 7 September 2026 names this archive as
the source material for the Simulator's new Portfolio Battery mode, and says the
results look fabricated. This page measures that claim. The audit reads one
archive: a module of 5,503 lines, a README, and 209 result files. Nothing from
the archive enters this repository.

The verdict in one line: the module runs a real trading loop over invented price
data, and every headline figure in the archive describes that invented data.

## The audit read the module and never ran it

The first check asks whether the module can run safely. The module calls two web
services and writes a cache folder beside itself. Under the rule for this unit
that ends the question. This audit read the module, read the reports, and ran
nothing.

```
line 4416   https://api.coingecko.com/api/v3/search?query=...
line 4455   https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart/range
line 4514   https://query1.finance.yahoo.com/v8/finance/chart/{sym}
line 4278   CACHE_DIR = Path(__file__).parent / "data" / "cache"
```

The cache folder in the archive holds no files. No run in this archive ever
fetched anything.

## 1. Does the module simulate, or does it produce numbers?

The module simulates. A real decision loop runs one pass per candle, with buy
and sell branches, fees, a spread and a running ledger. Nobody typed the results
in by hand.

The data underneath that loop comes from nowhere real. Three numbers produce a
whole year of hourly prices — 8,760 candles. A start price, a middle price and
an end price, joined by a smooth curve. Every candle takes the curve and
multiplies it by a fresh random wiggle.

```
RAIntSimBat.py   gen_from_anchors   line 797

    target = start_price + (mid_price - start_price) * smoothstep(t)
    noise_pct = rng.gauss(0, noise_std)
    close = target * (1 + noise_pct)
```

Each wiggle starts fresh and never carries forward. Real prices carry their last
move; this series never does. Every candle snaps straight back to the smooth
curve. A strategy that sells above a line and buys below the same line cannot
lose money on data built this way. The 100% win rate belongs to the data
generator, not to the strategy.

The module's own header states both halves of the contradiction, eight lines
apart.

```
line 25   Network is DISABLED in Claude's environment.
line 26   ALL data comes from embedded ASSET_PERIODS dictionary.
line 31   Target result: 39/39 wins (100%), ~$33,024 advantage
line 68   HISTORICAL ANCHOR POINTS (web-search-verified real prices)
```

Line 31 names the answer the run should produce, ahead of any run. Line 68 calls
the anchor prices verified by web search, while line 25 states that the
environment had no network.

One reported figure never came from a trading decision. The code multiplies the
result by a constant.

```
RAIntSimBat.py   run_portfolio   line 4975

    smart_wire_bonus = total_adv * 0.543   # +54.3% from Smart Wire testing
```

That constant fills the smart-wire estimate field in every portfolio report. In
one of them a total advantage of 14,286.52 becomes an estimate of 22,044.10 —
exactly 1.543 times the input.

## 2. Do the reports match the module?

The reports carry genuine output from this module. Their field names, their
layout and their arithmetic all match the code that writes them. Nobody
fabricated them by hand.

The numbers inside them still do not measure anything. Three findings say so,
and the report files themselves supply all three.

**The same battery, run 81 times, never loses and never agrees with itself.**
Each of the 81 standard battery reports commits 400 dollars to each of 39
simulations — 15,600 dollars in total. Each one claims 39 wins from 39. The
total advantage they claim ranges across eight decimal places.

```
81 battery reports, 39 simulations each, $15,600 committed

  files claiming other than 39 of 39 .......  0
  lowest total advantage ................... $182,972.72
  highest total advantage .................. $12,918,053,685,381.47

largest single simulation, inside the highest file:

  asset DOGE   period Apr24-Apr25   price change -41.5%
  capital in ............................... $400.00
  final .................. $10,675,079,557,098.86
  fees paid ................. $666,981,072,950.10
```

Four hundred dollars becomes ten trillion on an asset that fell 41 per cent.
That figure reports a broken ledger, not a trading result.

**The ledger mints money on one line.** Every sale in the engine credits the
proceeds twice — once to cash, and once to the fold queue that tracks the sale.
The final valuation then adds both together. While a fold stays open the two
copies cancel, because the buy-back spends the cash and clears the queue. One
line breaks that.

```
RAIntSimBat.py   run_v3192   line 1163

    if fold_q > 0: fold_age += 1
    else:          fold_age  = 0
    if (fold_age > 150 and fold_q > 0 and fold_tranches
            and all(price > t["ref"] * 1.08 for t in fold_tranches)):
        usd += fold_q; fold_q = 0.0; fold_tranches = []
```

That line adds the queue balance into cash and then clears the queue. Cash
already held the same balance. Every sale path in the module credits both at
once, so no case exists where the queue holds money that cash does not.

```
line 1590 / 1591   usd += scrum_usd_net   fold_q = sum(tranches)
line 1655 / 1656   usd += scrum_usd_net   fold_q += scrum_usd_net
line 1821 / 1830   usd += sell_usd        fold_q += sell_usd
line 2052          final = holdings*price + usd + fold_q + boost_q + hedge_bal
```

Cash doubles each time that release fires, and the run compounds from there.
Ten trillion comes from there.

**No run repeats.** Each simulation takes its random seed from Python's built-in
text hash, which differs deliberately in every process.

```
RAIntSimBat.py   run_battery   line 3138

    seed = hash(symbol + period_label) % 99999
```

Two Monte Carlo runs of the identical configuration, 35 seconds apart on 17
April, report a mean advantage of 3,672.50 and 3,954.62 for the same asset in
the same year. A comment on line 3289 calls the runs reproducible. They do not
repeat.

**One headline number appears in no report.** The module header claims about
33,024 dollars of advantage for the 39-simulation battery. The lowest total
across all 81 reports reaches 182,972.72, and no report carries a total between
30,000 and 36,000.

## 3. Does the archive contain a Monte Carlo at all?

A loop exists, and it does more than relabel a single run. The code makes ten
runs per configuration, each with a different seed, and prints the spread across
those ten. The report files keep all ten values, so anyone can check the claim.

The loop still does not sample market outcomes, and it mislabels its bands.

```
RAIntSimBat.py   run_monte_carlo   line 4187

    MONTE_CARLO_N = 10
    seed = (hash(sym + pl) + n * 1337) % 99999
    cands = gen_from_anchors(p_s, p_m, p_e, n_candles=8760, seed=seed, symbol=sym)
    p10 = run_advs[max(0, int(n_runs * 0.10))]
    p50 = run_advs[int(n_runs * 0.50)]
    p90 = run_advs[min(n_runs-1, int(n_runs * 0.90))]
```

At ten runs, the index for the 90th percentile lands on 9, the last item of a
sorted list of ten. The printed P90 names the largest of the ten runs. The
printed P10 names the second smallest. Checked against the stored values in all
three full reports:

```
rows where p90 equals the largest value .... 39 of 39, in each of 3 reports
rows where p10 equals the 2nd smallest ..... 39 of 39, in each of 3 reports
total runs per full report ................. 390        wins 390
```

All ten runs of a configuration share the same three anchor prices. The start
price, the middle price and the end price never move. Only the random wiggle
moves. The year's outcome settles before the loop begins, and the spread
measures noise rather than market risk. A Monte Carlo of market outcomes has to
vary the path the market takes.

The summary row averages the 39 per-configuration bands instead of pooling the
390 runs. An average of thirty-nine 90th percentiles gives the 90th percentile
of nothing. The README's headline band — P10 4,939, P50 7,803, P90 10,853 —
comes from that average, and it reproduces exactly from the 17 April file.

## 4. What is worth keeping

The portfolio and price definitions carry the value here. They feed a run rather
than come out of one, they stand clear of the broken ledger, and rebuilding them
would cost real work.

```
35  named portfolios, crypto and non-crypto

    SIXTY_FORTY  BOGLEHEAD  BUFFETT  ALL_WEATHER  CRYPTO_BLUE  LONG_BONDS
    RETIREMENT  DEFENSIVE  DIGITAL_GOLD  SECTOR_TECH  GROWTH_STOCK  INCOME
    ARK_SUITE  PANDEMIC_DARLINGS  CHINA_TECH  SPAC_BUST  MEME_HANGOVER
    CRYPTO_COLLAPSE  RATE_SENSITIVE  SIXTY_FORTY_FAIL  and 15 more

63  symbols carrying price anchors
378 anchor rows — six periods per symbol, three prices per period
    2020, 2021, 2022, Apr23-Apr24, Apr24-Apr25, Apr25-Apr26
```

Three more tables survive the same way: fee tiers by exchange and volume band,
spreads per asset, and volatility per asset. Each lists plausible market
parameters that a real venue model needs.

The rest carries forward as nothing:

```
every advantage figure          every win rate          every Sharpe ratio
every P10/P50/P90 band          every smart-wire estimate
every compound-chain result     every fee break-even conclusion
the README research table       the 39/39 and 156/156 headlines
```

One label needs a correction before anyone reuses the definitions. The module
tags nine portfolios as live-data portfolios. Every symbol in all nine carries
hardcoded anchors, so the code never reaches its fetch branch for them. The
reports prove it: across all 208 readable report files, 4,415 simulation rows
record a candle count, and every one reads 8,760. Both fetchers return daily
candles, so a real fetch would have written roughly 252 or 365 there. None did.

## What Portfolio Battery would need to be real

The operator's mode runs a Monte Carlo of Scrumming Bot and Extractor Bot logic
over crypto and non-crypto portfolios, and produces a genuine distribution of
outcomes. Against that target, here is what the archive supplies and what it
lacks.

**What exists.** Thirty-five portfolio definitions spanning crypto, equities,
commodities, bonds and a set of real historical failures. Sixty-three symbols
with six periods each. Fee, spread and volatility tables. A working shape for a
battery run: a loop over assets and periods, a per-run result record, and a JSON
report.

**What does not exist.** Any real price history — the archive holds none, and
its cache stands empty. Any run that repeats. A ledger that conserves money. A
percentile calculation that holds at the sample size in use. A set of paths to
sample from. And the module carries none of the product's own logic: the
trading loop inside it belongs to the module, not to the Scrumming Bot and not
to the Extractor Bot.

**What the first build unit has to establish.** Two things, in this order.
First, where the price history comes from and how the Simulator keeps it,
because a distribution of outcomes needs many paths and this archive supplies
none. Second, that a battery run drives the product's own bot logic rather than
a copy of it, which matches the rule the rest of this rebuild already carries:
one trading logic, three data sources.

Nothing beyond those two belongs here. The operator sets the mode's shape.

## How this audit took its readings

The audit extracted the archive to a temporary directory outside this repository
and read it there. Nothing executed the module. Every number above comes either
from a quoted line of the module or from the archive's own report files, read as
data.

The document archetype control ran first: the known-good fixture passes with all
five tools reporting, and the known-bad fixture fails.
