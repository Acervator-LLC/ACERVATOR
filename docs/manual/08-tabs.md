# Subsystem Tabs

Reference. Each heading below names a screen. The manual's own text for it
comes first, and under that is what the code does today, named by module and
symbol. Longer descriptions live one file per screen in
[08-tabs/](08-tabs/README.md).

`CANONICAL_TAB_ORDER` in `src/gui/main_window.py` names the seven tabs the
window builds: Trading, Market Inspector, Bot Swarm, Asset Charts, History,
Simulator and Console. The Trading tab has its own section,
[06-trading-tab.md](06-trading-tab.md), and the Indicator Voting Panel has
[07-indicators.md](07-indicators.md). A screen below that the window does not
build says as much in its own entry.

A strategy reaches real money through four steps: Market Inspector, Simulator,
Paper Trader, Live. Each step is a gate.
[08-tabs/promotion-pipeline.md](08-tabs/promotion-pipeline.md) draws the chain
and marks where it breaks.

The sections below run in the order
[04-manual-parts.md](04-manual-parts.md) lists the tabs.

## Main Window

`MainWindow` in `src/gui/main_window.py` builds the window in three parts: the
menu bar from `menuBar`, the header strip from `_build_header_strip`, and the
tab row `_reorder_main_tabs` fixes to `CANONICAL_TAB_ORDER`. The Portfolio
Information Panels fill that strip, and each tab below sits in that row.

### Portfolio Information Panels

Found at the top of the Main Window at all times, this provides metrics for total performance and activity of the platform.

`HeaderStripMixin._build_header_strip` in
`src/gui/main_tabs/header_strip.py` builds the strip. On the left,
`SpendableProfitsWidget` draws five columns: SPENDABLE, REALISED, LOCKED,
MATURE and EXCH. On the right, five `StatCard` widgets count Scrummed, Folded,
Trades, Bots and Errors, and a click on the Errors card opens the rolling error
log. `_refresh_dashboard` in `src/gui/main_window.py` fills every field from one
call to `get_aggregate_stats`, which keeps two cards from disagreeing about the
same fleet. Each field carries a privacy dot that masks the value through the
registry the Bot Swarm tab shares.

The strip hides itself while the Simulator tab is active, and the Simulator
draws its own copy of the same ten fields against sim balances. The absent live
strip is itself the signal that the screen is not live trading.

![The header strip and the tab row, with Privacy Mode off.](p29-i0.png)

The chrome above the strip carries four menus, built in
`src/gui/main_window.py`: File holds Settings, Reset All Settings and Exit;
Exchange holds Add Exchange; Theme lists the five `THEMES` display names from
`src/gui/theme_engine.py`; Help holds About.

Privacy Mode is off in the figure, so each field draws its own value rather
than four asterisks:

- SPENDABLE and LOCKED carry dollar figures. `_refresh_dashboard` fills them
  from `wallet_cash_usd` and `crypto_position_value_usd`.
- REALISED and MATURE draw an em dash. Both take a literal `None` at the two
  `_refresh_dashboard` call sites, so `_money_text` in
  `src/gui/widgets/spendable_profits.py` draws the no-reading marker on every
  tick. Turning Privacy Mode on masks that em dash to asterisks, which reads
  as a hidden number rather than an empty column.
- EXCH counts the open exchange sub-tabs.
- Scrummed, Folded, Trades, Bots and Errors are the five `StatCard` widgets.
  Bots counts the fleet in the running state, and a click on Errors opens the
  rolling error log.
- Crypto Mode at the right is `_mode_btn`. `_toggle_trading_mode` swaps the
  window between the crypto layer and the stock layer.
- The dot under each field is a `PrivacyDot`, and it masks that one field
  through the registry the Bot Swarm tab shares.

The tab row below takes its order from `CANONICAL_TAB_ORDER`, and
`_reorder_main_tabs` moves each tab into that position after the builders run.

Detail: [08-tabs/portfolio-panels.md](08-tabs/portfolio-panels.md).

## Simulator Tab (Hot Mess; Complete Rebuild In Progress)

`SimulatorTab` in `src/gui/simulator_tab/simulator_tab.py` stacks two panels.
Fleet Replay loads every bot from `bot_state.json` through
`load_bot_configs_from_state` in `src/simulator/fleet/bot_state_loader.py`,
builds one real `ScrummingBot` per config, and plays Stone Tablet candles
through them against `FleetSimExchange`. The sim uses the bot class body
unchanged, which is the parity guarantee: it runs live's code against a fake
exchange rather than a second implementation.

The criterion is the gates latching identically on the same data. Not profit and
loss, and not the trade count. `GateLightsCell` in
`src/gui/simulator_tab/fleet/sim_visuals.py` draws each sim bot's scrum and fold
arm state, and it reads the same `src/trading/gate_vocabulary.py` the History
table reads, which stops the two surfaces drifting apart.

Nuclear Mode loops the same fleet over the tablet window with per-cycle market
noise and a load pulse, writing over no tablet. It stands as a soak test, judged
on coverage and survival, and it compares nothing to live.

![The Simulator tab, with no fleet loaded.](p33-i0.png)

`SimStatStrip` in `src/gui/simulator_tab/sim_stat_strip.py` replaces the
window's header strip while this tab is active. `FIELDS` names the same ten
readings — Spendable, Realised, Locked, Mature, Exch, Scrummed, Folded,
Trades, Bots and Errors — against sim balances. Every one draws an em dash in
the figure, because no fleet is loaded.

Mode is `_mode_selector`. `SIM_MODES` holds three: Validation, Looping Back
Test and Nuclear. `_on_sim_mode_changed` writes the hint beside it naming
what that mode collects, and routes the stack to the Nuclear page or the
fleet page. Active simulator bots filters the readouts to one loaded bot.

The table under it is `BotStatusTable`, the same class the Trading tab uses,
with the same columns and a privacy dot on each header.

Fleet Replay is `FleetReplayPanel`. Load live fleet calls `_spawn_sim_fleet`,
which builds one real `ScrummingBot` per config that
`load_bot_configs_from_state` read. Fetch YTD pulls the year of live trades
the run is compared against, and Reset clears both. Full evaluation widens
the run. The line beside the buttons counts the trades and symbols the
History tab front-loaded through `on_history_refreshed`.

Loaded fleet carries three columns: Symbol, Target USD and Sim Trades, and
Sim Trades increments during a run. `_progress_lbl` reads `Replay idle` until
Start Replay runs, and Stop drains the current tick and exits.

The right column stacks two panels, each with its own Expand button. The
first charts historical price against position VWAP for the bot its picker
names, drawn from that bot's Stone Tablet candles. The second is the same
`IndicatorVotingPanel` the Trading tab carries: a bot picker, the vote count
badge, the TF Lock, the currency rate line, then the first six voters —
BB, VTX, MACD, SRsi, Ichi and Vol — with Net, Comp and Conf, and the
confidence bars under them. `_ROW_B_INDICATOR_COLS` holds the remaining six,
Sling, ADX, STrd, ZSc, KER and RSI, below the area the figure shows.

Simulator Log and Gate Status close the tab. Gate Status is `GateLightsCell`
in `src/gui/simulator_tab/fleet/sim_visuals.py`, which reads the same
`src/trading/gate_vocabulary.py` the History table reads and draws the same
nineteen lights. `No fleet loaded.` stands in its place until a fleet loads.

The banner above the buttons and the Start Replay tooltip both name an
internal release identifier for the work that replaces the synthetic candles
with the real feed.

Detail: [08-tabs/simulator.md](08-tabs/simulator.md).

### Lead with what the simulation does not model

Source: LEGACY, the fourteen-part manual, Part 9 page 2 and Part 5a pages 5 and
6. Both are editorial posture rather than a code claim, and the posture is worth
more than the engine those parts describe, which has no source in this
repository at all.

The legacy standalone part on the simulation engine opens with what the
simulation does **not** model, and says why in one line: a simulation engine
that opens with its capabilities and footnotes its limits builds false
confidence. A reader deciding whether to trust a result should read the limits
first, then the regime distribution, then everything else. That ordering carries
forward here unchanged, and this section is placed to obey it.

Three design principles come with it, from the methodology part.

- **Fix the universe and fix the periods.** A run whose asset list drifts is not
  comparable with the run before it. Adding an asset can raise a win rate
  without improving anything. Name a new constant for a new universe and keep
  the old one.
- **Be deterministic.** The same input gives the same output, with the seed a
  function of the asset, the period and the run. Then a change of one thing
  makes any difference in the result attributable to that one thing.
- **Measure against passive holding, not against zero.** A bull market returns
  something to anybody who holds. A strategy that returns 50 percent where
  holding returned 80 percent destroyed 30 points of value.

Four classes of fact sit outside any such run, and the legacy manual names all
four.

1. **Regime boundaries.** One run is one regime. Real markets change regime, and
   the change is where a strategy usually breaks.
2. **Execution failure.** Timeouts, partial fills, a venue freeze, a network
   split — none of these appear in a replay of stored candles. The live record
   is the only place they show up.
3. **The bot's own footprint.** A replay treats stored candles as ground truth.
   A live order participates in the book it is trading against. At small size
   the effect is small, and a replay cannot tell an operator when the size has
   stopped being small.
4. **Drift over time.** Parameters fitted to one span of history are a snapshot
   of fit, not a law.

The engine the legacy parts describe has no source here. Its file name has never
been committed and no path under its directory has ever existed in this
repository. What this repository holds instead is the Simulator tab above, and
the operator's own label on it stands: hot mess, complete rebuild in progress.
The criterion for that rebuild is gate-latch parity on the same data, not a
matching profit figure. [08-tabs/simulator.md](08-tabs/simulator.md) carries it.

## Paper Trader Tab (To Be Built)

Real-time, API-fed trades against a fake budget. This is designed as the second tier of strategy validation within the platform.

No module implements it. `git log --all --diff-filter=ADR --name-only` over
every commit reachable from every ref returns two paths carrying the word
`paper`, both markdown documents under `docs/`. The same query returns modules
and tests for `history_tab`, which proves it finds files that existed.

`RetiredTabsMixin` in `src/gui/main_tabs/retired_tabs.py` holds the `None`
sentinel the window reads in its place, and the Bot Swarm tab's Paper Swarm
sub-tab is chrome: its rows flip a label and construct no bot.

Live, Paper and the Simulator differ in one thing only, where the data comes
from. The trading logic stays one body of pure code all three call, and only the
stateful shells fork. Real time is Paper's defining property, and its budget is
twice the dollar target. Paper waits on the Simulator and on Nuclear Mode, both
gates ahead of it in
[08-tabs/promotion-pipeline.md](08-tabs/promotion-pipeline.md).

Detail: [08-tabs/paper-trader.md](08-tabs/paper-trader.md).

## Proof of Accumulation (Anonymized Trading Tournaments Via Blockchain)

This is currently proposed as a concept but will likely require the building of a supporting blockchain team for proper / full implementation. This system is designed to enable users of Acervator to compete against each anonymously via our own Proof of Accumulation blockchain. The idea is to convert trades executed into videogame metrics such as damage to a coliseum style monster or a fellow trader in a 1v1 face off. This further positions the platform as a surgical tool that can be finely tuned and customized to produce intense competition scenarios between entire groups of traders. This, of course, opens the door for actual tokenized Trading Guilds who may require their members to have a certain number of PoA tokens under their belt to join. There will be much more to follow on this as I do intend to scaffold it out for internal testing.

`src/competition/` is the Proof of Accumulation package. `BotIdentity` signs
each trade with an Ed25519 key and signs no strategy parameter.
`MerkleTradeLog` commits the trades to a root a third party can verify one trade
against without receiving the log. `CompetitionEngine` runs registration, active
trading, submission and adjudication. `TokenLedger` awards ACRV against a
ten-million hard cap, append-only and idempotent, with five rarity tiers by
rank. `TournamentEngine` in `src/trading/poa_tournament.py` builds the duel, the
melee and the gauntlet, and `local_testnet.py` simulates the whole Base
environment in memory with no wallet and no network.

The engine runs with no screen in front of it.
`src/gui/competition_tab.py` and `src/gui/testnet_tab.py` both exist, and
`RetiredTabsMixin` sets both attributes to `None`, so the window builds neither.
That makes this an initial implementation rather than a repair.

`harvest_svg` in `src/competition/trophy_generator.py` letters
`SOLVE · ET · COAGULA` around the trophy ring, which is the epigraph's own
instruction in its usual form.

Detail: [08-tabs/proof-of-accumulation.md](08-tabs/proof-of-accumulation.md).

## Market Inspector Tab

The concept with the Market Inspector Tab is evaluate markets from a higher point of view and provide strategy proposals in three forms: Oppositional Trading Pairs (Trading Pairs w/ Opposing Trends), Bot Swarm Topologies (Bot Swarm Network Proposals), and Exchange Comparison Arbitrage.

`MarketInspectorTab` in `src/gui/market_inspector.py` splits in two. The left
half holds the `HTF Signals` table and the `Opposing Pairs (30-day Pearson)`
table, both scored by `MarketInspector` in `src/trading/market_inspector.py`
through `scan_universe`, `_score_market` and `_find_opposing_pairs`. The right
half holds proposal cards from `detect_all_topologies` in
`src/trading/topology_proposals.py`, which offers four archetypes: momentum
funnel, mean-reversion pair, sector cluster and distance to band.

Adopting a card reaches `_adopt_topology_proposal` in
`src/gui/main_window.py`, which names the new bots, their combined budget and
every existing wire the adopt would change before it creates anything.

Two of the three proposal forms reach the screen. Exchange comparison arbitrage
has a module, `src/trading/arbitrage.py`, and no importer under `src/`; the tab
draws no arbitrage panel.

![The Market Inspector tab, before the first scan.](p29-i1.png)

`MarketInspectorTab` fills the left half. Refresh and the Include active
markets checkbox sit above the two tables, and `_status_lbl` reads `No data
yet — press Refresh.` until a scan lands, which is the state the figure
captures. Leaving the checkbox clear hides the markets a bot already holds.

- `HTF Signals` carries six columns: Asset, Signal, Score, Daily, Weekly and
  Active. `scan_universe` and `_score_market` fill them.
- `Opposing Pairs (30-day Pearson)` carries four: Long side, Short side,
  Correlation and Score (Long+Short). `_find_opposing_pairs` fills them from
  `_pearson` over `_returns`.

`MarketInspectorTopologies` in `src/gui/market_inspector_topologies.py` fills
the right half. Refresh proposals runs the detectors, and the line beside it
counts the proposals held and the cards dismissed.

Each card names its archetype and the assets in it, then a line reading the
score, the asset count, the wire count and the number of bots an adopt would
create. The badge takes its colour from the score: teal at `SCORE_HIGH` and
above, amber at `SCORE_MID` and above, grey below. Every card in the figure
comes from `detect_sector_cluster`, which reads
`src/trading/sector_map.json`. Preview opens `TopologyPreviewDialog`, which
lists the wires as Source, Target, Pct and Rationale.

Dismiss hides a card for a day, and the dismissal does not survive a restart.
`_persist_dismissed` calls `set` on the settings manager under a key
`AppSettings` in `src/core/settings.py` does not declare, and that call
raises `KeyError`. The pane catches the failure and logs it, which leaves the
dismissed count at zero on every launch.

The footer names the auto-refresh period and the adopt route. The status bar
under it carries the API load pill from `_refresh_api_load_pill`, drawn green
below half load, amber above it, and red past the monitor's safety
percentage, then the `AI:` state label.

Detail: [08-tabs/market-inspector.md](08-tabs/market-inspector.md).

## Bot Swarm Tab

(List View)

(Grid View)

The Bot Swarm is a proprietary capital reinforcement network system that allows profit to be dynamically and strategically routed between positions with the primary intention of this being to accelerate accumulation curves. Smart Wires are dragged between active bots or the quick connection matrix can be used to route multiple streams to different destinations. Each wire can carry a different percentage amount of profit. Profit sent over Smart Wires are registered at the destination as Wire Credits and these are then distributed into standing Fold Tranches which allow them to have a Surplus that will be spent to increase the Target Balance up to the Maximum Growth Per Cycle. Yes, that is probably a mouth full but hopefully the settings and names are, for the most part, self-explanatory.

`BotVisualizationTab` in `src/gui/bot_visualizer.py` draws each bot as a
`BotNodeWidget` locust card and switches between the list and the grid. Wires
drag between nodes on the grid. `QuickRoutingMatrix` in
`src/gui/visualizer/quick_routing.py` is the quick connection matrix: tick the
sources, tick the destinations, confirm the count, and every pair lands at once.

`SmartWireManager` in `src/trading/smart_wire.py` owns the topology and one
`BotLedger` per bot. `compute_safe_outflow_pct` bounds what a bot may export,
reading the target balance, the band edges and the ammunition the next fold
needs, which stops a bot sending away the capital it holds for its own dip. At
the far end, `apply_wire_income` in `src/trading/scrumming/wire_routing.py`
spreads arriving USD across the open fold tranches, or parks it as a pending
wire credit while no tranche stands.

The tranche book is `FoldTrancheAccountingMixin` in
`src/trading/scrumming/fold_tranches.py`. Three functions collapse or remove a
tranche and no others: merge, through `_top_up_remnant_fold_tranches` and
`_bound_new_fold_tranches`; despawn, through `_despawn_aged_tranches`, which
removes an aged record outright rather than holding it in a delisted state; and
clear, through `clear_fold_tranches`, which discards the queue and trades
nothing.

The fleet, and its wires, ledgers and tranches with it, comes from
`bot_state.json` alone. `StateManager` in `src/core/state_manager.py` reads and
writes that file, and `StateRestoreMixin` in
`src/trading/container/restore.py` rebuilds the fleet and its topology from it.

![The Bot Swarm tab in List view, with the quick routing matrix.](p30-i0.png)

Three sub-tabs open the screen: Bot Swarm, Simulator Swarm and Paper Swarm.
The header row holds the drag hint, an identifier privacy dot that masks the
bot hashes and the symbol labels together, the Privacy Mode button, and four
controls. Exchange filters both the swarm and the quick routing scope. Theme
lists the four palettes in `src/gui/visualizer/themes.py`. View chooses List
or Grid. The Wires slider sets wire opacity from 0 to 100 %.

The table is `BotSwarmList` in `src/gui/bot_swarm_list.py`. `COLUMN_HEADERS`
names twelve columns: Ticker, Inflow, Outflow, % Out, then the eight wire
lanes L1 to L8 that `LANE_COUNT` fixes. Inflow draws green and Outflow red.
% Out sums a bot's outbound wire percentages, and a bot with no outbound wire
reads 0 %. `BotSwarmLaneAllocator.assign` gives each wire the first free
lane, so two wires share a lane only when their row spans do not overlap. The
dot at each end of a lane marks the source row and the target row.

`QuickRoutingMatrix` in `src/gui/visualizer/quick_routing.py` fills the right
half in three zones: the source list, the Rate field between them, and the
destination list. Every checked source wires to every checked destination at
that rate. `_on_connect_clicked` refuses a rate that is not a number, a rate
outside 0 to 100 %, and a rate of zero, and `_reject` says which. `_confirm_mass`
puts the count in front of the operator before Connect, Disconnect or
Disconnect All runs.

![The same tab in Grid view.](p30-i1.png)

`_on_view_mode_changed` swaps the table for the node canvas. Each bot draws
as one `BotNodeWidget` locust card from `src/gui/visualizer/bot_node.py`.
The card carries the masked symbol above, the realised profit below it, and
the first eight characters of the bot id at the foot.
`pnl_color` is the theme's success colour at zero and above and the error
colour below, and the abdomen gradient takes that same colour with its alpha
scaled by the size of the figure. `src/gui/visualizer/particle.py` supplies
the drifting motes.

The wires cover the grid alone, because the grid is the only view whose
coordinates a wire can be drawn against. Each wire carries its own percentage,
drawn beside it. Drag between two nodes to create a wire, and right-click a
wire to remove it. The quick routing matrix on the right is the same widget
the List view shows.

Detail: [08-tabs/bot-swarm.md](08-tabs/bot-swarm.md).

## Asset Charts

Under the Asset Charts Tab, you will find our active bot (position) chart display. This will be upgraded to display only one chart at a time and will be able to display all indicators found in the Indicator Voting Panel.

`TradeChartsTab` in `src/gui/widgets/trade_charts_tab.py` scrolls one panel per
active bot. Each panel is `CandlestickChart` in `src/gui/native_chart.py`,
painted with QPainter and no browser, carrying trade markers, position markers,
grid lines, the standing tranche floors and the target balance line.
`_compute_indicators` reads its overlays from `src/trading/ta_engine.py` rather
than computing any of them. Candles arrive through `ChartDataFetcher` in
`src/exchange/chart_data.py`: exchange OHLCV first, the CoinGecko public API
second, the last good fetch third.

![The Asset Charts tab, one panel per running bot.](p31-i0.png)

`update_charts` rebuilds the panel set from the current bot roster, and the
tab scrolls them.

The header line of a panel names the symbol, the last price, the bot state,
the timeframe, the feed `set_source_label` reports, and the candle count.
The line under it carries the open, high, low and close of the current
candle, the change in price and in percent, and the volume. Rising candles
draw teal and falling candles red.

The dashed lines across the plot are the standing fold-tranche floors that
`set_tranche_floors` places, each labelled with its price.
`TB-Ceiling` is the dollar-target line from `set_target_balance_lines`. The
price axis runs down the right edge with the last price boxed on it, and the
volume bars run along the foot.

The toolbar under each panel holds the TF picker and eight indicator toggles.
`INDICATOR_TOGGLES` in `src/gui/main_tabs/native_chart_surface.py` names
them: BB, Vortex, MACD, SRsi, Ichi, Vol, Sling and BBull.
`INDICATOR_DEFAULTS` starts Vol on and the other seven off, which is the
state the figure shows. Sling and BBull paint a placeholder shape rather than
the indicator, and each says as much in its own tooltip.

The legend at the right names the two position markers `set_positions`
draws, Invisible and On Book, and the feed label closes the row.

Detail: [08-tabs/asset-charts.md](08-tabs/asset-charts.md).

## History Tab

History Tab (React):

The History Tab is able to pull trade history from all active exchanges via their respective APIs. It also pairs each imported trade with its in-platform trading logic and applies our trade grading system.

`HistoryTab` in `src/gui/history_tab.py` fetches through
`fetch_all_history_chunked` in `src/exchange/history_helpers.py`, and
`HistoryWebTable` in `src/gui/react_history_panel.py` draws the rows. Every cell
value comes from `build_page` in `src/exchange/history_read_contract.py`; the
table renders those fields and derives none, which stops a second History
growing behind the renderer. `grade_trade` in `src/trading/trade_grader.py`
supplies the letter grade, and `gate_light_row` in
`src/trading/gate_vocabulary.py` supplies the gate lights from the same
vocabulary the Simulator's gate cell reads.

A refresh also hands the Simulator its year of live trades: the tab's
`history_refreshed` signal connects to `FleetReplayPanel.on_history_refreshed`.

![The History tab: filters, graded rows and the gate lights.](p32-i0.png)

The Filters group carries From and To date pickers, then Exchange, Symbol and
Side, each filled by `_populate_filter_options` from the rows in hand. Apply
narrows the set, Reset restores it, and Refresh goes back to the venues. The
line under the group counts the retained rows against the loaded rows, both
sides with their dollar totals, and the age of the last fetch.

`COLUMNS` in `src/exchange/history_read_contract.py` names thirteen columns:
Timestamp (UTC), Exchange, Symbol, Bot, Side, Amount, Price, Cost USD, Fee,
Trade ID, Grade, Gates and Voting. `ROW_ORDER` fixes newest first and nothing
re-sorts. BUY draws green and SELL red.

Grade comes from `grade_trade`, which averages four sub-scores —
`_score_execution`, `_score_timing`, `_score_strategic` and `_score_outcome`
— and skips an axis that lacks inputs. `_letter_from_numeric` turns that mean
into A+, A, B, C, D or F. `PriceContext.regime_tag` reaches the rationale and
carries no sub-score of its own.

The Gates cell opens with the blocker text, then the lights. `gate_light_row`
returns nineteen: the ten scrum gates TGT, INT, BB, FIRE, TA, LS, TRND, HTF,
CB and OTD, then the nine fold gates BB, MID, TA, LS, TRNQ, CEIL, HTF, CB and
OTD. Each light draws under its own label, and each bank ends with an `S` or
an `F` marker. `LIGHT_COLORS` holds the five states: green passed, red the
gate that blocked, amber not armed for another reason, grey not evaluated at
this candle, and cyan a landing-strip override. The blocker text and the
light banks overlap in the figure; both occupy the one cell.

Prev, the page counter and Next page the result at the foot, and Export
CSV writes the current selection out.

![The History tab during a fetch, with the header strip above it.](p32-i1.png)

The same tab, captured while `_kick_async_fetch` runs. `STATUS_TEXT` holds
the five fixed status strings shown before any row exists, and the one on
screen is the `fetching` entry. `FETCH_POLL_INTERVAL_S` sets the 400 ms poll
and `FETCH_TIMEOUT_S` abandons a fetch after sixty seconds.

The header strip is visible here, which marks the screen as a live-trading
tab. REALISED and MATURE draw the same em dash the Trading tab draws.

A row whose gate log holds no entry inside the join window reads `no record`.
`build_page_gate_index` buckets the entries by bot id and minute, and
`lookup_gate_entry` picks the closest.

`HistoryTab._render_page` builds the summary line and the page counter
itself. `summary_line` and `page_label` in
`src/exchange/history_read_contract.py` declare both strings, and three
surface modules call them. The tab calls neither, so two implementations of
the same two strings stand in the tree. `_grade_row` in the same tab
delegates to the contract's `grade_row`, which is the pattern the two footer
strings depart from.

Detail: [08-tabs/history.md](08-tabs/history.md).

### Trade grading

Source: LEGACY, the fourteen-part manual, Part 8, pages 40 to 42. The claim
audit reports this chapter as verifying almost completely: the scored axes, the
letter boundaries and the grade column's place in the history contract all
match. One number in it is wrong, and the correction is below.

The grader scores a trade that has already happened. It never feeds a trading
decision, it never tunes a parameter, and no gate consults it. The same inputs
always give the same grade.

`src/trading/trade_grader.py` holds it, and
`src/exchange/history_read_contract.py` calls it at three sites, which is how
the grade reaches the History tab's grade column.

**Four axes are scored, not five.** The legacy chapter counts the regime tag as
a fifth axis and then says on the same page that the regime is used for
attribution rather than scored. Four is the number.

| Axis | What it reads | What a 1.0 means |
| ---- | ------------- | ---------------- |
| Execution | fill price against the reference price at decision time | no slippage |
| Timing | the favourable excursion against the adverse one over the following candles | the trade went far more right than wrong before it closed |
| Strategic | the asset's discipline ratio before the trade against after it | the trade moved the ratio the operator's way |
| Outcome | realised profit per unit | a clear gain |

`PriceContext.regime_tag` reaches `TradeGrade.regime` and the rationale string
and gets no score of its own. Grading the same record with a regime tag and
without one returns the same number, which is the control that proves it.

The overall number is the unweighted mean of the axes whose inputs were present.
An axis with no input is skipped: it neither credits nor penalises. The scale is
0.0 to 1.0, not 0 to 100.

| Letter | Lower bound |
| ------ | ----------: |
| A+ | 0.93 |
| A | 0.85 |
| B | 0.70 |
| C | 0.55 |
| D | 0.40 |
| F | below 0.40 |

Driving the mapper across each boundary and just under it flips the letter
exactly where the table says, in both directions.

**One trap worth knowing.** A trade with no gradeable input at all scores 0.5 and
therefore reads as a **D**, not as ungraded. A fully specified trade scores 1.0
and reads A+. A column of Ds may mean the trades were poor, or it may mean the
surrounding price context never arrived.

The legacy chapter names three files for the grader and its two command-line
tools. None of the three has ever been committed here. The grading that runs
today runs through the History tab.

## Console

This tab is focused on displaying Python activity and errors. The lower half, which is displaying the Emitter Network activity, will be migrated to the System Status Tab (under the Watchdog) which is to be built in the near future.

`ConsoleTabMixin._build_console_tab` in `src/gui/main_tabs/console_tab.py`
builds both panes into a vertical splitter. The upper one is a raw log tail:
`_QtLogHandler` formats each record and `_QtLogRelay` paints it on the GUI
thread, which lets a log call from any thread reach the pane safely. The tab
sets its own handler to DEBUG and changes no logger's level; an earlier build
raised the root logger and never restored it. Pause holds lines in a bounded
buffer and announces anything it had to drop.

The lower pane is the Emitter Network. `_drain_signals` in
`src/gui/main_window.py` reads the sink from `src/core/signal_contract.py` twice
a second and renders the newest 200 records with their expected and actual
values, keeping seven counters, which lets a quiet sink and a stopped timer read
differently.

![The Console tab: the log tail above, the Emitter Network below.](p34-i0.png)

Pause and Clear sit above the upper pane. Pause calls `set_paused` on
`_QtLogHandler`, which then holds lines in a bounded buffer and announces
anything it had to drop when it resumes. Clear empties the pane.

Each line in the upper pane carries the time, the level, the logger name and
the message, coloured by level. Three logger names appear in the figure:
`acervator.scrumming` for the bot warnings, `acervator.api` for the venue
calls, and `acervator.gui` for the panel feed.

Two of those lines are worth reading against the code:

- The repeated warning naming a capital-reservation over-commit comes from
  `src/trading/capital_reservation.py`, where `reserve` refuses a claim whose
  total would pass the holdings and names the existing claims, the request
  and the holdings.
- The `FETCH_OHLCV` line names a seven-indicator engine and lists seven
  indicators. `get_ohlcv` in `src/exchange/ccxt_connector.py` writes that
  text. `VotingEngine._create_indicators` builds twelve, and the Indicator
  Voting Panel shows twelve. The count in the log line and the count in the
  engine disagree.

The lower pane opens with the header `SIGNALS — name · expected · actual`.
Each record draws `OK`, `FAIL` or a neutral marker, then the signal name, the
site that emitted it, the actual value and the expected one. A satisfied
expectation is recorded the same as a violated one, which keeps a call site
that never ran distinct from one that always passed.

Detail: [08-tabs/console.md](08-tabs/console.md).

### The two snapshot emitters

Source: LEGACY, the fourteen-part manual, Part 8, pages 70 and 71. The claim
audit checked the quoted line prefixes against the code and found them exact.
They are still exact.

`SnapshotEmitterMixin` in `src/trading/scrumming/snapshots.py` writes two
symmetric records to the bot log, and the Console tab is where an operator reads
them.

| Method | Line prefix | Written when |
| ------ | ----------- | ------------ |
| `_emit_risk_gate_snapshot` | `RISK GATE SNAPSHOT [SIDE] ` | a risk gate blocks a trade |
| `_emit_trade_fire_snapshot` | `TRADE FIRED SNAPSHOT [SIDE] ` | a scrum or a fold actually fires |

`SIDE` is the upper-case side of the decision. Both lines continue with the last
ticker price and a panel dictionary holding every voter's direction, confidence,
weight and detail at that moment. The fire record adds the list of overrides
that engaged, so a reader can tell an override-driven fire from a
consensus-driven one without opening anything else.

The pair is the point. A blocked trade and a fired trade write the same shape,
so the log holds both halves of the decision and not only the half that acted.

Three further emitters sit in the same mixin: a trade notification carrying its
own text prefix, a voting-panel snapshot at fire time, and a gate decision at
fire time. The last two emit events rather than text lines, and the Console
tab's signal pane reads them.

The legacy chapter also describes a command-line tool that samples the log,
re-derives the net and confidence from each snapshot, and classifies the trade.
That tool has never been committed here. The emitters it reads are real, and the
reader is not.

## System Status Tab (To Be Built)

This tab consists of two distinct but closely related parts. The Emitter Network is an embedded system of data activity detectors intended to allow for detailed subsystem performance monitoring. The Watchdog is the raw signal capture for the Emitter Network’s output.

No tab exists. `git log --all --diff-filter=ADR --name-only` returns no path
whose name carries `system_status`, while the same query returns a surface
module, a renderer module and two tests for `live_status_tab`, the per-bot
readout inside the Live Bot Settings dialog.

Both halves run today. The Emitter Network is `src/core/signal_contract.py`,
whose `emit` records a satisfied expectation the same as a violated one, which
keeps a call site that never ran distinct from one that always passed.
`src/core/emit_contracts.py` declares every emitter, where `EmitContract` names
a topic's required fields and its vocabulary and `EmitObserver` reports a topic
that never fired, a missing field or a value outside that vocabulary. The
Watchdog is `acervator_watchdog.py` at the repository root: it launches the
application as a child process, tees both output streams to its own log, polls
the heartbeat file, and writes a post-mortem after the child dies.

Detail: [08-tabs/system-status.md](08-tabs/system-status.md).

### Post-mortem bundle rotation

Source: LEGACY, the fourteen-part manual, Part 3 "System Architecture", page 19.

The Watchdog writes a post-mortem bundle every time the application dies. Each
bundle copies the runner's console log, the crash log, the fault-handler log and
a thread dump, which runs to hundreds of megabytes. Per-run log rotation already
capped the size of one run's logs and capped nothing about the number of
bundles, so weeks of restarts grew without limit. The operator's log directory
reached roughly 400 gigabytes and took the host down with it.

`prune_postmortem_bundles` in `acervator_watchdog.py:421` is the cap. It keeps
the most recent bundles, drops anything past a maximum age whatever its
position, and runs at two sites: once at Watchdog startup, which clears what
earlier runs left behind, and once after each post-mortem is written, which
holds the ceiling during a long session.

**The legacy page names four constants. Three exist.**

| Constant | Value | What it does |
| -------- | ----: | ------------ |
| `POSTMORTEM_KEEP_LATEST` | 20 | bundles preserved, newest first |
| `POSTMORTEM_MAX_AGE_DAYS` | 30 | anything older is dropped |
| `POSTMORTEM_SIZE_WARN_BYTES` | 5 GB | warns at startup, prunes nothing |

All three are at `acervator_watchdog.py:389` to 391. The third is a warning
threshold read by `report_log_dir_footprint` and it deletes nothing, so two
constants govern the rotation and one reports on it. The only other inputs are
the log directory itself, derived from the home directory at
`acervator_watchdog.py:64`, and the literal bundle-name prefix inside the
function. Neither is a rotation constant.

No test in this repository references any of the three names. The cap runs and
nothing holds it in place.

## Settings

`SettingsDialog` in `src/gui/settings_dialog.py` holds the eleven pages below.
`_save` and `_load_current` decide which of them persists, and each page says
which under its own heading.

### Settings > User Tab

This needs to be built out to accept and contain individual end user credentials. This will also be where a license is entered or a keyfile is imported depending on how we design the authentication piece.

`_create_user_tab` in `src/gui/settings_dialog.py` builds one form row, a
`Username` line edit, and `SettingsManager` in `src/core/settings.py` persists
it. The page carries no credential field, no licence field and no key import.

Both halves a credential store would rest on already exist, and the page reads
neither. `src/core/encryption.py` encrypts a secret with AES-256-GCM under a
PBKDF2-derived key and keeps the passphrase in the operating system's credential
store. `src/core/usb_auth.py` writes an encrypted credential file keyed to a USB
volume's serial, which decrypts on that stick and nowhere else.

![Settings, the User page.](p34-i1.png)

The title bar names the wing the dialog was opened for. `_setup_ui` adds
eleven pages in one order: User, Exchanges, Trading, Profit Folding, TA
Indicators, Phantom Bots, Theme, Logging, Sound, SMS and AI Monitor. The
arrows at each end of the row scroll it, because the eleven do not fit the
dialog's minimum width. Cancel and Save close the dialog, and Save always
closes it, reporting any group that failed to persist.

The page itself carries one row, `Username`, and nothing else.

Detail: [08-tabs/settings.md](08-tabs/settings.md).

### Settings > Exchanges

`_create_exchange_tab` in `src/gui/settings_dialog.py` lists the configured
exchanges and adds one: the exchange picker, an API key, an API secret, and a
passphrase field that appears only when the venue needs it. The picker fills
from `SUPPORTED_EXCHANGES` in `src/exchange/ccxt_connector.py`, so it lists what
the connector layer can reach. The key field accepts a Coinbase CDP key string
and the secret field a PEM elliptic-curve private key.

`_test_api_connection` runs before `_add_exchange` stores anything, and
`_remove_exchange` drops a selected entry. Adding one calls `add_exchange_tab`
in `src/gui/main_window.py`, which routes the new tab to the crypto or the stock
layer and reports which layer it landed in. The same page in the stock wing
shows a banner and disables Add and Test, because no broker connector ships yet.

![Settings, the Exchanges page.](p35-i0.png)

`Configured Crypto Exchanges` lists what `list_exchanges` returns for this
wing, each entry naming its display name and its exchange id. The stock wing
lists the equity ids instead and disables both buttons.

The Add Crypto Exchange group holds four rows. Exchange fills from
`SUPPORTED_EXCHANGES`. API Key takes a plain key or a Coinbase CDP key
string, and its placeholder shows the CDP shape. API Secret takes a plain
secret or a PEM elliptic-curve private key, and escaped newlines inside a
pasted PEM convert on the way in. The passphrase checkbox appears for the
venues `PASSPHRASE_EXCHANGES` names.

Test Connection runs `_test_api_connection` and reports through
`_set_feedback`. Test and Add Exchange runs the same check first and stores
nothing when it fails. Remove Selected drops the highlighted entry.

Detail: [08-tabs/settings.md](08-tabs/settings.md).

### Settings > Trading

![Settings, the Trading page.](p36-i0.png)

`_create_trading_tab` in `src/gui/settings_dialog.py` builds six rows. These
are the defaults a new bot starts from, not a running bot's settings. The
figure shows every row at the value the page opens with.

Position Distance - Sets the spacing a new bot puts between its positions.
Key `position_distance_pct`, 1.0 % to 50.0 %, at 2.0 %.

Increment Style - Chooses whether that spacing stays even or widens on a
curve. Key `increment_style`, linear or logarithmic, at linear.

Default Positions - Sets how many positions a new bot opens with. Key
`default_position_count`, 1 to 100, at 10.

Default Target Balance - Sets the dollar figure the wizard's own Target
Balance field opens at. Key `default_target_balance`, $1.00 to $1,000,000.00,
at $200.00.

Bot Visibility - Chooses whether a new bot rests its orders on the book or
tracks them inside the platform. Key `bot_visibility`, orderbook or internal,
at orderbook.

Enable aggressive trading mode - Starts a new bot pricing for an immediate
fill. Key `aggressive_trading`, a checkbox, off.

`_save` writes all six. `_load_current` reads back the first four only, so
Bot Visibility and the aggressive checkbox open at their built-in defaults
whatever was stored, and a Save with no edit overwrites the stored pair.

One of the six reaches a new bot. `TradingParamsPage` in
`src/gui/bot_wizard.py` opens its Target Balance field at the stored default
target balance. No bot builder reads the other five.

Position Distance carries a second gap. Its key is one of the eleven names
`_DEPRECATED_KWARGS` holds in `src/trading/container/config.py`, and every
name in that set is stripped before a bot is constructed, so the value cannot
reach a bot by any route.

`src/gui/settings_dialog.py` — `_save`, the six keys this page writes

```python
"position_distance_pct": lambda: self._pos_distance.value(),
"increment_style": lambda: self._increment_style.currentText(),
"default_position_count": lambda: self._default_positions.value(),
"default_target_balance": lambda: self._default_balance.value(),
"bot_visibility": lambda: self._visibility.currentText(),
"aggressive_trading": lambda: self._aggressive.isChecked(),
```

### Settings > Profit Folding

![Settings, the Profit Folding page.](p37-i0.png)

`_create_folding_tab` builds one master checkbox and three groups of radio
buttons, eleven controls in all. Every key below sits inside one stored
`profit_folding` group.

Profit Folding / Upward Distribution Active - Turns the whole page on. Key
`active`, a checkbox, clear at build and set to on when the stored group
loads.

Distribution Mode - Chooses whether a fold spreads evenly across the chosen
positions or on a curve. Key `mode`, equal or logarithmic, at equal.

Profit Folding Target - Chooses which buy positions a fold reaches: all of
them, a counted number of them, or the most recent. Key `fold_target`, at all
buy positions.

Fold to X# of buy positions - Sets that counted number. Key
`fold_target_count`, 1 to 100, at 5.

Upward Distribution Target - The same three choices on the sell side. Key
`distribute_target`, at all sell positions.

Distribute to X# of sell positions - Sets the sell-side count. Key
`distribute_target_count`, 1 to 100, at 5.

`_save` collapses the whole page into one stored dictionary. Six values go in
and `_load_current` restores the master switch alone, so the mode and both
targets open at the checked defaults the figure shows. Issue #322 carries
that.

Four of those six keys fail a second time further down. The two target names
and their two counts are four of the eleven entries in `_DEPRECATED_KWARGS`,
and every entry there is stripped before a bot is constructed. A group that
did round-trip still could not carry those four to a bot.

`src/gui/settings_dialog.py` — `_save`, the group this page writes

```python
fold_target = "all_buy"
if self._fold_x.isChecked():
    fold_target = "x_buy"
elif self._fold_recent.isChecked():
    fold_target = "most_recent_buy"
dist_target = "all_sell"
if self._dist_x.isChecked():
    dist_target = "x_sell"
elif self._dist_recent.isChecked():
    dist_target = "most_recent_sell"
self._sm.set(
    "profit_folding",
    {
        "active": self._folding_active.isChecked(),
        "mode": (
            "logarithmic" if self._fold_log.isChecked() else "equal"
        ),
        "fold_target": fold_target,
        "fold_target_count": self._fold_x_count.value(),
        "distribute_target": dist_target,
        "distribute_target_count": self._dist_x_count.value(),
    },
)
```

### Settings > TA Indicators

![Settings, the TA Indicators page.](p38-i0.png)

`_create_ta_tab` builds one slider per entry in `DEFAULT_WEIGHTS` from
`src/trading/ta_engine.py`, twelve in all, each labelled from its key. The
value beside a slider follows it as it moves.

Indicator weight - Sets how far one indicator's vote counts against the other
eleven in the voting engine. Twelve sliders, each 0.00 to 2.00, each starting
at that indicator's own declared weight.

The twelve sliders, the key behind each, and where each starts:

| Slider | Key | Starts at |
| ------ | --- | --------: |
| Bollinger Bands | `bollinger_bands` | 1.00 |
| Vortex | `vortex` | 0.90 |
| Macd | `macd` | 1.20 |
| Stochastic Rsi | `stochastic_rsi` | 1.00 |
| Ichimoku | `ichimoku` | 1.10 |
| Volume | `volume` | 0.80 |
| Slingshot | `slingshot` | 1.00 |
| Adx | `adx` | 1.00 |
| Kaufman Er | `kaufman_er` | 1.00 |
| Supertrend | `supertrend` | 1.00 |
| Zscore | `zscore` | 0.90 |
| Rsi | `rsi` | 0.80 |

A weight moved here reaches nothing. `_save` reads no widget on this page and
`_load_current` restores none.

`AppSettings` in `src/core/settings.py` declares no field an indicator weight
could land in, so there is nowhere for the page to write even if it tried.

`VotingEngine.__init__` takes a `weights` argument and falls back to the
declared table above, and no construction site in the source tree supplies
one from the settings store. The page label promises an adjustment the engine
never sees. Issue #423 carries this page and three others in the same state.

`src/gui/settings_dialog.py` — `_create_ta_tab`, where the range and the
starting value come from

```python
for ind_name, default_w in DEFAULT_WEIGHTS.items():
    slider = QSlider(Qt.Horizontal)
    slider.setRange(0, 200)
    slider.setValue(int(default_w * 100))
```

### Settings > Phantom Bots

![Settings, the Phantom Bots page.](p39-i0.png)

`_create_phantom_tab` builds the master checkbox, eleven timeframe boxes and
one Higher-TF Lock Settings group. Thirteen controls in all.

Enable Phantom Balance Bots for Scrumming - Turns the phantom overrides on
for a new bot. Per-bot key `enable_phantoms`, a checkbox, checked at build.

Default Phantom Timeframes - Chooses which charts a phantom watches: 1m, 5m,
15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d and 1w. Per-bot key `phantom_timeframes`,
eleven boxes, with 5m, 15m, 1h, 4h and 1d checked at build.

Lock duration (candles) - Sets how many candles a higher-timeframe lock holds
an opposing trade back for. Per-bot key `lock_candle_count`, 1 to 10, at 2.

Those eleven boxes are the eleven timeframes the voting engine already
weights. `aggregate_multi_timeframe` in `src/trading/ta_engine.py` runs the
same list from 1m at 0.3 up to 1w at 1.6, so a heavier chart counts for more
when several are combined.

These three controls carry the same gap the TA Indicators page carries:
`_save` reads none of them, `_load_current` restores none, and `AppSettings`
declares no field for a phantom default. Issue #423 carries this page.

The per-bot equivalents do persist. `PhantomConfigPage` in
`src/gui/bot_wizard.py` emits the same three names into the bot's own config,
and the Live Bot Settings dialog edits them there.

`src/gui/bot_wizard.py` — `PhantomConfigPage.get_config`, the three keys that
do reach a bot

```python
return {
    "enable_phantoms": self._enable.isChecked(),
    "phantom_timeframes": checked,
    "lock_candle_count": self._lock_candles.value(),
}
```

### Settings > Theme

![Settings, the Theme page.](p40-i0.png)

`_create_theme_tab` builds the theme picker, the accent colour field and a
Font Settings group. Six controls and one preview.

Visual Theme - Chooses the palette the whole window paints in. Key `theme`,
the five `THEMES` display names — Cyberpunk Dark, Neon Light, Classic
Terminal, Minimal Modern and Glass & Metal — at Cyberpunk Dark.

Accent Color - Sets the highlight colour. Key `accent_color`, a free-text
field, at `#00ffcc`.

Font Family - Sets the typeface for application text. Key `font_family`, an
editable combo over twelve named families, at Segoe UI.

Base Font Size - Sets the size of ordinary interface text. Key `font_size`,
8 pt to 24 pt, at 11 pt.

Heading Font Size - Sets the size of headings and stat-card values. Key
`heading_font_size`, 10 pt to 32 pt, at 14 pt.

Log Font Size - Sets the size of the Activity Log and API Log text. Key
`log_font_size`, 8 pt to 18 pt, at 10 pt.

Preview redraws in the chosen family and base size as either changes. It is a
sample line, not a setting, and nothing stores it.

`_save` writes the theme, the Accent Color field and all four font values.
`_load_current` reads back the theme and that field only, so the four font
rows open at Segoe UI, 11, 14 and 10 whatever was stored.

Of the six, the theme alone reaches the window. `main.py` reads it at startup,
and the window reads it again in `_on_settings_changed` when the dialog saves
and repaints on it.

The other five are stored and never read again. Each palette carries its own
typeface in the `ThemeTokens` it declares, so the theme decides the font and
the four font rows decide nothing. The accent field has the same shape: it is
declared, written, read back into its own line edit, and painted nowhere.

`src/gui/settings_dialog.py` — `_save`, the six keys this page writes

```python
"theme": lambda: self._theme_combo.currentData(),
"accent_color": lambda: self._accent_color.text().strip(),
"font_family": lambda: self._font_family.currentText(),
"font_size": lambda: self._font_size.value(),
"heading_font_size": lambda: self._heading_size.value(),
"log_font_size": lambda: self._log_font_size.value(),
```

### Settings > Logging

![Settings, the Logging page.](p41-i0.png)

`_create_logging_tab` builds two checkboxes and four periodicity boxes. Every
key below sits inside one stored `data_logging` group.

Log TA signal samples with all values and timestamps - Writes each indicator
reading out with its value and its time. Key `ta_signal_logging`, a checkbox,
checked at build.

Highlight entries near Scrumming Bot trades - Marks the log lines that sit
close to a fire, so a decision can be read in its own context. Key
`highlight_trade_proximity`, a checkbox, checked at build.

P/L Log Periodicity - Chooses the windows a profit and loss figure is
summarised over: 24 Hours, 1 Week, 1 Month and 1 Year. Key
`active_periodicities`, a list of four boxes, with 24 Hours and 1 Week
checked at build.

`_save` collapses all six controls into one stored dictionary. The two
checkboxes go in under their own names and the four periodicity boxes go in
as one list, written as 24h, 1_week, 1_month and 1_year.

`_load_current` reads none of them back, so every open shows the build state
rather than the stored one. No reader outside this dialog reads the group
either, which leaves the six controls writing to a key nothing consults.
Issue #322 carries this page.

`src/gui/settings_dialog.py` — `_save`, the group this page writes

```python
self._sm.set(
    "data_logging",
    {
        "ta_signal_logging": self._ta_logging.isChecked(),
        "highlight_trade_proximity": self._highlight_trades.isChecked(),
        "active_periodicities": periods,
    },
)
```

### Settings > Sound

![Settings, the Sound page.](p42-i0.png)

`_create_sound_tab` builds the master switch, eight event checkboxes, a
volume slider and six test buttons. Every checkbox is checked at build, and
each names its sound in its own label. The key behind each control is a field
of `SoundConfig` in `src/core/sound_engine.py`.

Enable sound notifications - Turns every sound on or off at once. Key
`enabled`, a checkbox, on.

Buy order fills - Plays a low rising tone when a buy fills. Key `buy_sound`,
a checkbox, on.

Sell order fills - Plays a bright bell when a sell fills. Key `sell_sound`, a
checkbox, on.

Errors - Plays an alert tone on an error. Key `error_sound`, a checkbox, on.

Bot state changes - Plays a click when a bot starts, pauses or stops. Key
`bot_state_sound`, a checkbox, on.

Scrum/Fold Fire - Plays a rifle shot when a scrum or a fold actually
executes, and on a Manual Fire. Key `fire_sound`, a checkbox, on.

Tracking beeps - Paces a beep by the scrum phase: silent in SEARCH, slow in
TRACK, fast in FIRE. Key `track_sound`, a checkbox, on.

P/L increase - Plays coins dropping into a bucket on any trade that realised
a profit. Key `profit_sound`, a checkbox, on.

Accumulation - Plays a water drip on a FOLD, and on nothing else. Key
`drip_sound`, a checkbox, on.

SFX Volume - Sets how loud every sample plays. Key `volume`, 0 % to 100 %, at
70 %.

Test Buy, Test Sell, Test Fire, Test Track, Test Profit and Test Drip play one
sample each through `get_sound_engine`. They are buttons, not settings.

`_on_sfx_volume_changed` is the only path from this page to the engine. It
builds a `SoundConfig` from every checkbox and the slider, pushes it into the
engine and clears the sample cache, because each sample bakes its volume at
synthesis time. That path runs when the slider moves or a test button is
pressed, and at no other time.

`_save` reads no widget on this page and `AppSettings` declares no sound
field, so nothing here survives the dialog closing. A checkbox cleared and
the dialog saved comes back checked. Issue #423 carries this page.

`src/gui/settings_dialog.py` — `_on_sfx_volume_changed`, the ten fields this
page fills

```python
new_cfg = SoundConfig(
    enabled=self._sound_enabled.isChecked(),
    buy_sound=self._sound_buy.isChecked(),
    sell_sound=self._sound_sell.isChecked(),
    error_sound=self._sound_error.isChecked(),
    bot_state_sound=self._sound_state.isChecked(),
    fire_sound=self._sound_fire.isChecked(),
    track_sound=self._sound_track.isChecked(),
    profit_sound=self._sound_profit.isChecked(),
    drip_sound=self._sound_drip.isChecked(),
    volume=v / 100.0,
)
```

### Settings > SMS

![Settings, the SMS page.](p43-i0.png)

`_create_sms_tab` builds a scrolling page holding the master switch and three
groups, seventeen controls in all. The key behind each control is a field of
`SMSConfig` in `src/core/sms_engine.py`.

Enable SMS notifications - Turns every message on or off at once. Key
`enabled`, a checkbox, clear at build.

Provider - Chooses how a message leaves the machine: a carrier's email
gateway, or the Twilio web interface. Key `provider`, at the email gateway.
Nothing loads a stored choice into the picker, so it opens on the first entry
whatever the figure shows.

Phone Number - Sets the number every message goes to. Key `phone_number`,
free text, empty, with a placeholder showing the international shape.

Carrier - Names the carrier whose gateway address a message would be built
for. Filled from `CARRIER_GATEWAYS`, ten entries, at AT&T. It has no stored
field of its own, and nothing on the page reads the choice.

Gateway Email - Sets the full gateway address the message is sent to. Key
`gateway_email`, free text, empty.

SMTP Username - Sets the mailbox the message is sent from. Key
`smtp_username`, free text, empty.

SMTP Password - Sets that mailbox's application password. Key
`smtp_password`, masked, empty.

Buy fills - Sends a message when a buy fills. Key `notify_buy_fills`, a
checkbox, checked at build.

Sell fills - Sends a message when a sell fills. Key `notify_sell_fills`, a
checkbox, checked at build.

Bot state changes - Sends a message when a bot starts, stops or errors. Key
`notify_bot_state_changes`, a checkbox, checked at build.

API errors and failures - Sends a message when a venue call fails. Key
`notify_errors`, a checkbox, checked at build.

P/L threshold alerts - Sends a message when profit or loss passes a dollar
figure. Key `notify_pl_threshold`, a checkbox, clear at build.

P/L threshold - Sets that dollar figure. Key `pl_threshold_amount`, $1 to
$100,000, at $100.

Low balance warnings - Sends a message when a balance runs low. Key
`notify_balance_warning`, a checkbox, clear at build.

Exchange connection status - Sends a message when a venue connects or drops.
Key `notify_connection_status`, a checkbox, clear at build.

Max messages per hour - Caps how many messages one hour may carry. Key
`max_messages_per_hour`, 1 to 100, at 20. Below the area the figure shows.

Min time between messages - Sets the wait between two messages. Key
`cooldown_seconds`, 5 to 300 seconds, at 30. Below the area the figure shows.

None of it reaches `SMSEngine`. `_save` reads no widget on this page and
`AppSettings` declares no SMS field. Issue #423 carries this page.

Two further gaps sit inside the page itself. Neither provider label the combo
offers matches a stored provider value, which are `email_gateway` and
`twilio`. And the page carries no row for the three Twilio credentials the
sender reads, so the Twilio choice has no way to be supplied.

`src/core/sms_engine.py` — `SMSConfig`, the three credentials no row fills

```python
twilio_sid: str = ""
twilio_auth_token: str = ""
twilio_from_number: str = ""
```

### Settings > AI Monitor

![Settings, the AI Monitor page.](p44-i0.png)

`_create_ai_monitor_tab` builds a scrolling page holding four groups and
seven settings. Every key below sits inside one stored `ai_monitor` group.

Anthropic API Key - Holds the key the monitor authenticates with. Key
`api_key`, masked, empty.

Check interval - Sets how long the monitor waits between two reviews. Key
`interval_hours`, 0.5 to 24.0 hours, at 4.0.

Connect phrase - Sets the phrase the platform puts into the prompt it sends.
Key `connect_phrase`, free text, empty.

Confirm phrase - Sets the phrase the answer must carry back to prove it came
from the same conversation. Key `confirm_phrase`, free text, empty. Change
both phrases together and keep both secret.

Enable AI Monitor feedback loop - Turns the monitor on. Key `enabled`, a
checkbox, clear at build.

Auto-handshake on first analysis - Runs the phrase exchange on the first
review rather than waiting for one to be asked for. Key `auto_handshake`, a
checkbox, checked at build.

Log AI feedback to trade journal - Writes each answer into the trade journal.
Key `log_feedback`, a checkbox, checked at build.

Connection Status closes the page, below the area the figure shows: a status
line, a journal hash, a completed-check count and a Test Handshake button.
The three readings report and the button acts. None of the four stores
anything, so the page holds seven settings and four other things.

`_save` writes all seven controls into one `ai_monitor` dictionary and
`_load_current` reads all seven back, which makes this the one page besides
User whose whole state round-trips.

Six of the seven then reach the engine. `configure_live_monitor` in
`src/trading/bot_container.py` reads five of them and builds or clears the
monitor, and the main window reads the journal switch when an answer arrives.
The auto-handshake box is the seventh: it is written, it is read back, and
nothing else reads it.

Test Handshake runs no handshake. `_test_ai_handshake` checks that the key
and both phrases hold text, then writes either an error line or the message
saying the handshake runs on the next bot cycle. The button reports the
fields it read, never a venue answer. Issue #327 carries this.

`src/trading/bot_container.py` — `configure_live_monitor`, the five keys it
reads

```python
if not settings.get("enabled") or not settings.get("api_key"):
    self._live_monitor = None
    logger.info("LiveMonitor disabled")
    return
journal = TradeJournal()
self._live_monitor = LiveMonitor(
    api_key=settings["api_key"],
    journal=journal,
    interval_hours=settings.get("interval_hours", 4.0),
    connect_phrase=settings.get("connect_phrase", ""),
    confirm_phrase=settings.get("confirm_phrase", ""),
)
```
