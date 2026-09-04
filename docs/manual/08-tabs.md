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

## Portfolio Information Panels

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

Detail: [08-tabs/portfolio-panels.md](08-tabs/portfolio-panels.md).

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

Detail: [08-tabs/history.md](08-tabs/history.md).

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

Detail: [08-tabs/simulator.md](08-tabs/simulator.md).

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

Detail: [08-tabs/console.md](08-tabs/console.md).

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

## Settings > User Tab

This needs to be built out to accept and contain individual end user credentials. This will also be where a license is entered or a keyfile is imported depending on how we design the authentication piece.

`_create_user_tab` in `src/gui/settings_dialog.py` builds one form row, a
`Username` line edit, and `SettingsManager` in `src/core/settings.py` persists
it. The page carries no credential field, no licence field and no key import.

Both halves a credential store would rest on already exist, and the page reads
neither. `src/core/encryption.py` encrypts a secret with AES-256-GCM under a
PBKDF2-derived key and keeps the passphrase in the operating system's credential
store. `src/core/usb_auth.py` writes an encrypted credential file keyed to a USB
volume's serial, which decrypts on that stick and nowhere else.

Detail: [08-tabs/settings.md](08-tabs/settings.md).

## Settings > Exchanges

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

Detail: [08-tabs/settings.md](08-tabs/settings.md).
