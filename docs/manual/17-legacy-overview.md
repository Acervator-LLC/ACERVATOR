# Overview Carried From The Legacy Manual

Reference. Source: LEGACY, the fourteen-part manual, Part 1 "Frontmatter and
Overview", pages 5 and 6. The claim audit in
[docs/audits/manual-original-parts-audit.md](../audits/manual-original-parts-audit.md)
scored that part 10 ANCHORED out of 28 checkable claims. The passages below are
the anchored ones, re-checked here against the code, with every wrong number
corrected in place.

[03-executive-summary.md](03-executive-summary.md) holds the operator's own
summary for this part. This file sits beside it and adds the legacy material.
Nothing here replaces a sentence there.

## Harvest and fold, in the legacy manual's words

A position opens against a base currency and carries an explicit dollar target.
Price oscillates. The bot harvests profit at thresholds below the target without
closing the position, and puts the freed capital back to work at a better cost
basis. When a harvest sells above the target, a fold fires: the profit is
realised and the target grows by that amount. Targets ratchet upward and never
shrink.

The loop runs in `ScrummingBot` in `src/trading/scrumming_bot.py`, and the
per-tick work is in `src/trading/scrumming/tick_phases.py`. The tranche book in
that module keeps each buy as its own lot with its own `initial_buy_price`, and
`_fold_eligible_tranches` only offers a lot back to the fold while the market
sits at or below that lot's own price. That test is the floor which makes the
per-unit advantage compound.

The legacy summary is right about a result that looks wrong on a spreadsheet.
Converting dollars into an asset position is negative cash flow by definition,
so a window of buys and sells that ignores the value of what the bot still holds
reads negative while the strategy works exactly as designed. Read the venue's
own total balance, the per-asset discipline ratio and the cost-basis charts
instead. [13-live-evidence.md](13-live-evidence.md) names the readers this
repository holds.

## The bot types that run

The legacy summary names three production bot types. Two exist.

- **The Scrumming Bot** runs the harvest-fold loop on one asset against one base
  currency. `src/trading/scrumming_bot.py`, constructed at five call sites
  including `src/gui/main_window.py:3444` and
  `src/trading/container/restore.py:361`.
- **The Extractor Bot** holds one pool of base currency and fires fixed-dollar
  rounds across several pairs from a watchlist.
  `src/trading/extractor_bot.py`, constructed at three call sites. The operator
  marks it partially built and untested.
  [16-operator-settings.md](16-operator-settings.md) carries its fields.

The third named type has no source here. The identifier the legacy manual gives
it has never appeared in any Python file in any commit, and the whole of the
legacy Part 5c rests on it. [15-patent-portfolio.md](15-patent-portfolio.md)
carries the probe and both of its controls.

## The two counts that hold, and the two that do not

- **Seventeen gate classes — exact.** `src/trading/gate_chain.py` defines
  exactly 17 concrete subclasses of the abstract `Gate`. Calling `Gate()` raises
  `TypeError`, which is the control that the abstract-and-concrete split the
  count rests on is real. No `Gate` subclass exists anywhere else in `src/`.
- **Twelve voters — exact.** `VotingEngine._create_indicators` in
  `src/trading/ta_engine.py` builds exactly 12 indicators, and `DEFAULT_WEIGHTS`
  in the same module holds exactly 12 keys, one per voter. Reading the weight
  off each built object rather than off the dictionary returns the same twelve
  values, so no fallback literal has drifted away from the table. The weights
  run from 0.8 to 1.2 and sum to 11.7.
- **Not five timeframes; eleven.** The legacy summary says the panel votes
  across five timeframes. `VotingEngine.aggregate_multi_timeframe` at
  `src/trading/ta_engine.py:319` weights eleven — 1m, 5m, 15m, 30m, 1h, 2h, 4h,
  6h, 12h, 1d and 1w — from 0.3 up to 1.6. `TIMEFRAME_ORDER` at
  `src/gui/main_tabs/indicator_panel_surface.py:243` carries the same eleven in
  the same order. No five-timeframe set exists anywhere in the tree.
- **Not seventeen gates per tick.** Seventeen is the class count, not the chain
  length. `build_scrumming_scrum_chain()` at `src/trading/gate_chain.py:593`
  builds a sell-side chain of 14, and `build_scrumming_fold_chain()` at line 619
  builds a buy-side chain of 10. The last entry on each side is an override that
  runs in a second pass, so it appears in the chain's own name list and never in
  the pass or block list. [07-indicators.md](07-indicators.md) prints both
  chains in order.

## What the legacy overview claims that this repository cannot support

The legacy summary names a stocks path served by two market-data providers.
Neither provider name has ever appeared in a Python file here. The stock
connector that exists is `src/stocks/alpaca_connector.py`, with
`src/stocks/tradingview_bridge.py` beside it.

It also names a governance tree as the truth source for the patent portfolio,
and six tooling scripts by file name. No path under that tree has ever been
committed, and none of the six scripts was ever added. The positive control on
the same query returns `src/core/log_paths.py` and its commit; a coined name
returns nothing.

The live-trading totals in the legacy summary are not checkable from this
repository, and the runtime trees were deliberately not opened. Its own
arithmetic is at least self-consistent: 20 good plus 4 flat plus 1 wind-down
equals the 25 pairs it claims.
