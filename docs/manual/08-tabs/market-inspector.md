# Market Inspector Tab

Reference. The higher-timeframe scanner and the topology proposal pane.
First step of [the promotion pipeline](promotion-pipeline.md).

## What builds it

`MarketInspectorTabMixin._build_market_inspector_tab` in
`src/gui/main_tabs/market_inspector_tab.py` constructs
`MarketInspectorTab` from `src/gui/market_inspector.py` and wires its
three injection points before adding the tab.

The tab splits horizontally. The left half holds the scanner, the right
half holds the proposal cards.

## Left half: the scanner

A filter row carries a Refresh button and an "Include active markets"
checkbox. The default hides the markets already under a bot, which keeps
the table on entry opportunities.

`HTF Signals` lists one row per market: Asset, Signal, Score, Daily,
Weekly, Active.

`Opposing Pairs (30-day Pearson)` lists Long side, Short side,
Correlation and the combined score.

## Where the analysis happens

`MarketInspector` in `src/trading/market_inspector.py` owns the maths.
`scan_universe` drives it, `_analyze_tf` reduces one timeframe to a
`TimeframeAnalysis`, `_score_market` returns a `MarketSignal`, and
`_find_opposing_pairs` pairs anti-correlated markets into an
`OpposingPair` using `_pearson` over `_returns`.

`get_shared_inspector` returns the single analyzer instance. The tab owns
the fetch cycle and writes into it; the per-bot Market Inspector page in
the Bot Details dialog reads back out of it through `build_per_bot_view`.
One analyzer, two readers, no second copy of the score.

## Fetching

`set_exchange_source` binds a connectors getter and the application
scheduler, so the tab always sees the current connector dict rather than
a snapshot taken at build time.

`fetch_htf_universe` in `src/exchange/market_inspector_fetcher.py` does
the work: `_pick_universe` ranks each connector's bulk tickers by 24-hour
quote volume, `_fetch_one_symbol` pulls per-symbol OHLCV on the
connector's single-worker executor, and `_resample_daily_to_weekly`
derives the weekly series on the client when the venue lists no weekly
timeframe. The fetcher serves the last network result while it stays
younger than `DEFAULT_MIN_REFRESH_S`; the Refresh button passes a force
flag that goes to the network regardless.

## Right half: topology proposals

`MarketInspectorTopologies` in `src/gui/market_inspector_topologies.py`
renders one `_ProposalCard` per proposal and opens a
`TopologyPreviewDialog` on Preview.

`detect_all_topologies` in `src/trading/topology_proposals.py` produces
them from a plain context dict, which keeps the engine free of any
exchange or bot-manager coupling. Four detectors:

| Detector | Shape |
| -------- | ----- |
| `detect_momentum_funnel` | Correlated cluster, leader into laggers |
| `detect_mean_reversion_pair` | Anti-correlated pair, wired both ways |
| `detect_sector_cluster` | Same-sector star, hub into spokes |
| `detect_distance_to_band` | One asset, scrum-deep into fold-deep |

`suggested_target_usd` sizes each proposed bot from
`src/trading/asset_target_defaults.json`, and `load_sector_map` reads
`src/trading/sector_map.json`. The orchestrator unions the detectors,
drops overlapping proposals by asset and caps the result.

`dismiss` hides a card, `is_dismissed` and `_sweep_dismissed` expire the
dismissal after a day, and `set_dismiss_store` hands the pane the
settings manager it persists through. The pane never resolves settings
itself.

## Adopt

`set_adopt_handler` connects the pane's `adoptRequested` signal to
`_adopt_topology_proposal` in `src/gui/main_window.py`. The handler
counts the new bots and their combined budget, asks
`_topology_wire_collisions` which of the proposed wires already exist and
would change, and shows all of it before anything is created. An adopt
that aborts part way calls `_report_adopt_orphans`, which names the bot
ids it created and left unwired.

## Exchange comparison arbitrage

`src/trading/arbitrage.py` holds the cross-exchange price monitor and its
spread tracking. No module under `src/` imports it, and the tab draws no
arbitrage panel. The first two proposal forms are on screen; the third is
not.

## Bridge

Three methods serve this screen:
`market_inspector_surface` answers `market_inspector.state`,
`market_inspector_tab_surface` answers `market_inspector_tab.state`, and
`market_inspector_topologies_surface` answers
`market_inspector_topologies.state`. The renderer modules are
`market_inspector.js`, `market_inspector_tab.js` and
`market_inspector_topologies.js`.

Back to [the subsystem index](README.md).
