# Subsystem Tabs

Reference. Each heading below names a screen. The manual's own text for it
comes first, and under that is what the code does today. Longer descriptions
live one file per screen in [08-tabs/](08-tabs/README.md).

One list names the seven tabs the window builds, and every screen below that
the window does not build says as much in its own entry.

`src/gui/main_window.py` — `CANONICAL_TAB_ORDER`

```python
CANONICAL_TAB_ORDER = [
    "Trading",
    "Market Inspector",
    "Bot Swarm",
    "Asset Charts",
    "History",
    "Simulator",
    "Console",
]
```

The Trading tab has its own section, [06-trading-tab.md](06-trading-tab.md),
and the Indicator Voting Panel has [07-indicators.md](07-indicators.md).

A strategy reaches real money through four steps: Market Inspector, Simulator,
Paper Trader, Live. Each step is a gate.
[08-tabs/promotion-pipeline.md](08-tabs/promotion-pipeline.md) draws the chain
and marks where it breaks.

The sections below run in the order
[04-manual-parts.md](04-manual-parts.md) lists the tabs.

## Main Window

### Portfolio Information Panels

Found at the top of the Main Window at all times, this provides metrics for total performance and activity of the platform.

The window is built in three parts: the menu bar, the header strip, and the tab
row. The panels above fill that strip, and each tab below sits in that row.

The strip is one row. Five labelled columns run down the left — SPENDABLE,
REALISED, LOCKED, MATURE and EXCH — and five counter cards close it on the
right.

`src/gui/main_tabs/header_strip.py` — `HeaderStripMixin._build_header_strip`

```python
self._spendable_widget = SpendableProfitsWidget()
top_row.addWidget(self._spendable_widget, stretch=3)
```

The five cards are Scrummed, Folded, Trades, Bots and Errors. One aggregate
call fills every field on the strip once a tick, which keeps two cards from
disagreeing about the same fleet.

`src/gui/main_window.py` — `_refresh_dashboard`

```python
agg = self._bot_manager.get_aggregate_stats()
_scr = float(agg.get("total_scrummed_usd", 0.0) or 0.0)
_fld = float(agg.get("total_folded_usd", 0.0) or 0.0)
self._stat_scrummed.set_value(f"${_scr:,.2f}")
self._stat_folded.set_value(f"${_fld:,.2f}")
```

Each field carries a privacy dot that masks the value through the registry the
Bot Swarm tab shares. The strip hides itself while the Simulator is active, and
the Simulator draws its own copy of the same ten fields against sim balances.
The absent live strip is itself the signal that the screen is not live trading.

![The header strip and the tab row, with Privacy Mode off.](p29-i0.png)

The chrome above the strip carries four menus. File holds Settings, Reset All
Settings and Exit. Exchange holds Add Exchange. Theme lists the five display
names the theme engine declares, and Help holds About.

`src/gui/main_window.py` — the menu bar

```python
file_menu = menu_bar.addMenu("&File")
file_menu.addAction("&Settings", self._open_settings)
file_menu.addAction("&Reset All Settings", self._reset_settings)
```

Privacy Mode is off in the figure, so each field draws its own value rather
than four asterisks. SPENDABLE and LOCKED carry dollar figures. EXCH counts the
open exchange sub-tabs. Crypto Mode at the right swaps the window between the
crypto layer and the stock layer.

REALISED and MATURE draw an em dash. Both take a literal absence at the one
call site that fills them, on every tick.

`src/gui/main_window.py` — `_refresh_dashboard`

```python
self._spendable_widget.update_profits(
    {
        "spendable": _wallet_cash,
        "total_realised": None,
        "locked": _crypto_value,
        "mature": None,
        "exchange_count": exchanges,
    }
)
```

Turning Privacy Mode on masks that em dash to asterisks, which reads as a
hidden number rather than an empty column.
[06-trading-tab.md](06-trading-tab.md) carries the proposal for the first of
the two. Issue #428 carries a second disagreement on this strip, between what
the counter tooltips promise and what the cards draw.

Detail: [08-tabs/portfolio-panels.md](08-tabs/portfolio-panels.md).

## Simulator Tab (Hot Mess; Complete Rebuild In Progress)

The tab stacks two panels. Fleet Replay loads every bot from the operator's own
state file, builds one real bot per config, and plays Stone Tablet candles
through them against a fake exchange. The sim uses the bot class body
unchanged, which is the parity guarantee: it runs live's code against a fake
exchange rather than a second implementation.

`src/gui/simulator_tab/fleet/fleet_replay_panel.py` — `_spawn_sim_fleet`

```python
def _spawn_sim_fleet(self) -> int:
    """Construct a real sim bot for every loaded config.

    Returns the number spawned. Reads the Stone Tablet registry
    through the same call Start Replay uses, rather than adding a
    second candle path.
```

The criterion is the gates latching identically on the same data. Not profit
and loss, and not the trade count. The sim's gate cell reads the same
vocabulary the History table reads, which stops the two surfaces drifting
apart.

`src/gui/simulator_tab/fleet/sim_visuals.py` — `GateLightsCell`

```python
class GateLightsCell(QWidget):
    """One linear labelled row of trading gates.
```

Nuclear Mode loops the same fleet over the tablet window with per-cycle market
noise and a load pulse, writing over no tablet. It stands as a soak test,
judged on coverage and survival, and it compares nothing to live.

![The Simulator tab, with no fleet loaded.](p33-i0.png)

The strip along the top replaces the window's own while this tab is active. It
names the same ten readings against sim balances, and every one draws an em
dash in the figure, because no fleet is loaded.

Mode is the picker beside it. Three modes, each with its own line saying what
it collects.

`src/gui/simulator_tab/simulator_tab.py` — `SimulatorTab.SIM_MODES`

```python
SIM_MODES = (
    (
        "Validation",
        "validation",
        "Stone Tablets paired with YTD data. Verifies trade-gate "
        "parity at documented events.",
    ),
    (
        "Looping Back Test",
        "looping",
        "Loops the tablets with market-restructuring noise at a fixed "
        "rate. Strategy development and calibration.",
    ),
    (
        "Nuclear",
        "nuclear",
        "Load oscillation, swarm injection and high-traffic smart "
        "wire. Measures performance, stability and reliability — not "
        "trade validity.",
    ),
)
```

The table under it is the same class the Trading tab uses, with the same ten
columns and a privacy dot on each header.

`src/gui/widgets/bot_status_table.py` — `BotStatusTable.SCRUMMING_COLUMNS`

```python
SCRUMMING_COLUMNS = ColumnSpec(
    labels=(
        "Bot ID",
        "Symbol",
        "Mode",
        "Trades",
        "Target",
        "Target BTC",
        "Target ETH",
        "Ammo",
        "Fire",
        "",
    ),
```

Fleet Replay fills the left column. Load live fleet builds the bots, Fetch YTD
pulls the year of live trades the run is compared against, and Reset clears
both. Full evaluation widens the run. The line beside the buttons counts the
trades and symbols the History tab front-loaded. Loaded fleet carries three
columns: Symbol, Target USD and Sim Trades, and the last of those increments
during a run. The progress label reads `Replay idle` until Start Replay runs,
and Stop drains the current tick and exits.

The panel says so out loud when a run cannot be compared to live, rather than
letting a synthetic run look like a parity run.

`src/gui/simulator_tab/fleet/fleet_replay_panel.py` — `_note_parity_state`

```python
def _note_parity_state(self) -> None:
    """Say so when the run cannot be compared to live.
```

The right column stacks two panels, each with its own Expand button. The first
charts historical price against position VWAP for the bot its picker names,
drawn from that bot's Stone Tablet candles. The second is the same Indicator
Voting Panel the Trading tab carries: a bot picker, the vote count badge, the
TF Lock, the currency rate line, then the first six voters — BB, VTX, MACD,
SRsi, Ichi and Vol — with Net, Comp and Conf, and the confidence bars under
them. The remaining six, Sling, ADX, STrd, ZSc, KER and RSI, sit below the area
the figure shows.

Simulator Log and Gate Status close the tab. Gate Status draws the same
nineteen lights the History table draws, and `No fleet loaded.` stands in its
place until a fleet loads.

Detail: [08-tabs/simulator.md](08-tabs/simulator.md).

## Paper Trader Tab (To Be Built)

Real-time, API-fed trades against a fake budget. This is designed as the second tier of strategy validation within the platform.

No module implements it. One method assigns nothing-at-all to the four
attributes the tab would own, so a legacy code path that reads one gets that
sentinel rather than an error.

`src/gui/main_tabs/retired_tabs.py` — `RetiredTabsMixin._install_retired_tab_sentinels`

```python
self._paper_trader = None
self._paper_trader_stack = None
self._paper_trader_crypto = None
self._paper_trader_equity = None
```

The Bot Swarm tab's Paper Swarm sub-tab is chrome: its Start button flips a
flag and relabels itself, and no bot is constructed. Issue #422 carries the
caption on it.

Live, Paper and the Simulator differ in one thing only, where the data comes
from. The trading logic stays one body of pure code all three call, and only
the stateful shells fork. Real time is Paper's defining property, and its
budget is twice the dollar target.

`src/trading/container/config.py` — `BotConfig`, the field that budget doubles

```python
target_balance: float = 200.0  # Balance the bot trades relative to
```

Two places already expect the tab. The window treats it as isolated alongside
the Simulator, and the header-strip surface carries the same pair, so the strip
will hide itself the day the tab arrives with no change to either site.

`src/gui/main_tabs/header_strip_surface.py` — `ISOLATED_TABS`

```python
ISOLATED_TABS = ("Simulator", "Paper Trader")
```

The step needs its own exchange shell, forked from the Simulator's rather than
imported: same base class, live candles instead of stored ones.

*Proposed, not present, in a package of its own:*

```python
class PaperExchange(ExchangeInterface):
    """Live-feed prices, fake balances. Orders fill against the last ticker."""

    def __init__(self, connector, starting_balances: dict[str, float]):
        self._connector = connector
        self._balances = dict(starting_balances)
```

Paper waits on the Simulator and on Nuclear Mode, both gates ahead of it in
[08-tabs/promotion-pipeline.md](08-tabs/promotion-pipeline.md).

Detail: [08-tabs/paper-trader.md](08-tabs/paper-trader.md).

## Proof of Accumulation (Anonymized Trading Tournaments Via Blockchain)

This is currently proposed as a concept but will likely require the building of a supporting blockchain team for proper / full implementation. This system is designed to enable users of Acervator to compete against each anonymously via our own Proof of Accumulation blockchain. The idea is to convert trades executed into videogame metrics such as damage to a coliseum style monster or a fellow trader in a 1v1 face off. This further positions the platform as a surgical tool that can be finely tuned and customized to produce intense competition scenarios between entire groups of traders. This, of course, opens the door for actual tokenized Trading Guilds who may require their members to have a certain number of PoA tokens under their belt to join. There will be much more to follow on this as I do intend to scaffold it out for internal testing.

`src/competition/` is the Proof of Accumulation package. Each bot signs every
trade with an Ed25519 key and signs no strategy parameter, so authorship is
provable while the method stays private.

`src/competition/bot_identity.py` — `BotIdentity`

```python
class BotIdentity:
    """
    Manages a bot's Ed25519 keypair.  The private key never leaves this object
    unencrypted.  The public key is the bot's network-visible identity.
```

The signed trades commit to a Merkle root a third party can verify one trade
against without receiving the log. The competition itself runs four phases.

`src/competition/competition_engine.py` — the module's own summary

```python
  1. REGISTRATION  — bots register with capital commitment + config hash
  2. ACTIVE        — bots trade; each trade appended to their Merkle log
  3. SUBMISSION    — trading closes; bots submit Merkle root + performance claim
  4. ADJUDICATION  — arbiter verifies submissions, ranks bots, awards tokens
```

The token ledger is append-only and idempotent, with five rarity tiers by rank.
Its hard cap is ten million ACRV, and each season awards less than the one
before it.

`src/competition/season_schedule.py` — the supply constants

```python
TOTAL_SUPPLY_CAP = 10_000_000  # Hard cap — immutable
GENESIS_SEASON = 1
INITIAL_REWARD = 500_000  # Season 1 reward pool
DECAY_FACTOR = 0.85  # Each season awards 85% of the prior season
MIN_SEASON_REWARD = 100  # Floor — never less than this per season
```

`TournamentEngine` in `src/trading/poa_tournament.py` builds the duel, the
melee and the gauntlet. A local testnet module beside it simulates the whole
Base environment in memory, with no wallet and no network.

The engine runs with no screen in front of it. `src/gui/competition_tab.py` and
`src/gui/testnet_tab.py` both exist, and the window builds neither.

`src/gui/main_tabs/retired_tabs.py` — `RetiredTabsMixin._install_retired_tab_sentinels`

```python
self._competition_tab = None

self._testnet_tab = None
```

That makes this an initial implementation rather than a repair.

Detail: [08-tabs/proof-of-accumulation.md](08-tabs/proof-of-accumulation.md).

## Market Inspector Tab

The concept with the Market Inspector Tab is evaluate markets from a higher point of view and provide strategy proposals in three forms: Oppositional Trading Pairs (Trading Pairs w/ Opposing Trends), Bot Swarm Topologies (Bot Swarm Network Proposals), and Exchange Comparison Arbitrage.

The tab splits in two. The left half holds the HTF Signals table and the
Opposing Pairs table, both scored by one analyzer. One method drives the whole
pipeline and keeps the results on that analyzer.

`src/trading/market_inspector.py` — `MarketInspector.scan_universe`

```python
def scan_universe(
    self,
    candles_by_symbol_by_tf: dict,
    active_symbols: set,
    closes_by_symbol: dict,
) -> None:
```

The right half holds proposal cards from four detectors: momentum funnel,
mean-reversion pair, sector cluster and distance to band. The engine takes a
plain dictionary, unions the detectors, drops overlapping proposals by asset
and caps the result.

`src/trading/topology_proposals.py` — `detect_all_topologies`

```python
def detect_all_topologies(
    context: dict[str, Any],
    cap: int = PROPOSAL_CAP,
) -> list[dict[str, Any]]:
```

Adopting a card names the new bots, their combined budget and every existing
wire the adopt would change before it creates anything.

`src/gui/main_window.py` — `_adopt_topology_proposal`

```python
new_bots = [
    b for b in proposal.get("bots", []) if not b.get("existing_bot_id")
]
wires = list(proposal.get("wires", []))
new_count = len(new_bots)
```

Two of the three proposal forms reach the screen. Exchange comparison arbitrage
has a module, `src/trading/arbitrage.py`, and no importer under `src/`; the tab
draws no arbitrage panel.

In development.

![The Market Inspector tab, before the first scan.](p29-i1.png)

Refresh and the Include active markets checkbox sit above the two tables, and
the status line reads `No data yet — press Refresh.` until a scan lands, which
is the state the figure captures. Leaving the checkbox clear hides the markets
a bot already holds.

HTF Signals carries six columns: Asset, Signal, Score, Daily, Weekly and
Active. Opposing Pairs carries four: Long side, Short side, Correlation and
Score. The pairing enumerates every long against every short and keeps the ones
whose thirty-day return correlation sits in the configured negative window.

`src/trading/market_inspector.py` — `MarketInspector._find_opposing_pairs`

```python
def _find_opposing_pairs(self, signals: list, closes_by_symbol: dict) -> list:
    """Enumerate long × short candidates; keep pairs whose 30-day
    return correlation sits in the configured negative window."""
    longs = [s for s in signals if s.direction == "long" and s.score >= 0.3]
    shorts = [s for s in signals if s.direction == "short" and s.score >= 0.3]
```

Refresh proposals runs the detectors, and the line beside it counts the
proposals held and the cards dismissed. Each card names its archetype and the
assets in it, then a line reading the score, the asset count, the wire count
and the number of bots an adopt would create. The badge takes its colour from
the score: teal at the high threshold and above, amber at the middle one, grey
below. Every card in the figure comes from the sector-cluster detector. Preview
lists the wires as Source, Target, Pct and Rationale.

Dismiss hides a card for a day, and the dismissal does not survive a restart.
The write-through never raises, so the pane logs the failure and carries on,
which leaves the dismissed count at zero on every launch.

`src/gui/market_inspector_topologies.py` — `_persist_dismissed`

```python
def _persist_dismissed(self) -> None:
    """Best-effort write-through. Never raises: losing a
    dismissal is a nuisance, taking down the pane is not."""
    if self._dismiss_store is None:
        return
    try:
        self._dismiss_store.set(DISMISS_SETTINGS_KEY, dict(self._dismissed))
```

The key it writes is not one the settings schema declares, so the write fails
every time. Issue #424 carries it.

The footer names the auto-refresh period and the adopt route. The status bar
under it carries the API load pill, drawn green below half load, amber above
it, and red past the monitor's safety percentage, then the `AI:` state label.

Detail: [08-tabs/market-inspector.md](08-tabs/market-inspector.md).

## Bot Swarm Tab

(List View)

(Grid View)

The Bot Swarm is a proprietary capital reinforcement network system that allows profit to be dynamically and strategically routed between positions with the primary intention of this being to accelerate accumulation curves. Smart Wires are dragged between active bots or the quick connection matrix can be used to route multiple streams to different destinations. Each wire can carry a different percentage amount of profit. Profit sent over Smart Wires are registered at the destination as Wire Credits and these are then distributed into standing Fold Tranches which allow them to have a Surplus that will be spent to increase the Target Balance up to the Maximum Growth Per Cycle. Yes, that is probably a mouth full but hopefully the settings and names are, for the most part, self-explanatory.

Each bot draws as one locust card, and the tab switches between the list and
the grid. Wires drag between nodes on the grid.

`src/gui/visualizer/bot_node.py` — `BotNodeWidget`

```python
class BotNodeWidget(QWidget):
    """Paint one bot as a locust, fed by set_bot_data and animate.

    paintEvent draws the wings, abdomen, thorax and head, then the
    symbol, the P/L and the bot_id as text.
    """
```

`SmartWireManager` in `src/trading/smart_wire.py` owns the topology and one
ledger per bot. One function bounds what a bot may export, reading the target
balance, the band edges and the ammunition the next fold needs, which stops a
bot sending away the capital it holds for its own dip.

`src/trading/smart_wire.py` — `compute_safe_outflow_pct`

```python
def compute_safe_outflow_pct(
    scrum_profit_usd: float,
    target_balance_usd: float,
    current_price: float,
    band_lower: float,
    band_upper: float,
    next_fold_ammo_usd: float,
    current_cash_usd: float,
    compound_growth_pct: float,
    retained_this_cycle_usd: float,
) -> float:
```

At the far end, arriving USD spreads across the open fold tranches, or parks as
a pending wire credit while no tranche stands.

`src/trading/scrumming/wire_routing.py` — `apply_wire_income`

```python
def apply_wire_income(self, usd: float, source: str, ref: str = "") -> dict:
    """Apply incoming Smart Wire USD to this bot's fold queue.
```

Three functions collapse or remove a tranche and no others: merge, despawn and
clear. Despawn removes an aged record outright rather than holding it in a
delisted state, and the count lands in the discarded ledger rather than the
closed one.

`src/trading/scrumming/fold_tranches.py` — `_despawn_aged_tranches`

```python
_days = self._despawn_threshold_days()
report = {
    "threshold_days": _days,
    "fold_delisted": 0,
    "stack_delisted": 0,
    "stack_kept_live_order": 0,
    "ageless_kept": 0,
    "usd_delisted": 0.0,
}
```

The fleet, and its wires, ledgers and tranches with it, comes from one state
file alone. A restored bot connects to nothing and places no order until the
operator starts it.

`src/trading/container/restore.py` — `StateRestoreMixin.restore_bots_from_state`

```python
def restore_bots_from_state(self, state: dict) -> list[str]:
    """Recreate every persisted bot in IDLE state; return the ids restored.
```

![The Bot Swarm tab in List view, with the quick routing matrix.](p30-i0.png)

Three sub-tabs open the screen: Bot Swarm, Simulator Swarm and Paper Swarm. The
header row holds the drag hint, an identifier privacy dot that masks the bot
hashes and the symbol labels together, the Privacy Mode button, and four
controls. Exchange filters both the swarm and the quick routing scope. Theme
lists the four palettes. View chooses List or Grid. The Wires slider sets wire
opacity from 0 to 100 %.

The table carries four named columns and eight wire lanes.

`src/gui/bot_swarm_list.py` — `COLUMN_HEADERS`

```python
COLUMN_HEADERS = ["Ticker", "Inflow", "Outflow", "% Out"] + [
    f"L{i + 1}" for i in range(LANE_COUNT)
]
```

Inflow draws green and Outflow red. % Out sums a bot's outbound wire
percentages, and a bot with no outbound wire reads 0 %. Two wires share a lane
only when their row spans do not overlap, and the dot at each end of a lane
marks the source row and the target row.

The quick routing matrix fills the right half in three zones: the source list,
the Rate field between them, and the destination list. Every checked source
wires to every checked destination at that rate, and four conditions are
refused out loud before anything is created.

`src/gui/visualizer/quick_routing.py` — `QuickRoutingMatrix._on_connect_clicked`

```python
if not (0.0 <= pct <= 100.0):
    self._reject(f"Rate {pct} is outside 0–100%.")
    return
if not sources:
    self._reject("No SOURCE bots are checked.")
    return
if not dests:
    self._reject("No DESTINATION bots are checked.")
    return
if pct <= 0:
    self._reject(
        "Rate is 0% — that would create wires that route " "nothing."
    )
    return
```

A confirmation puts the count in front of the operator before Connect,
Disconnect or Disconnect All runs.

![The same tab in Grid view.](p30-i1.png)

The view switch swaps the table for the node canvas. Each card carries the
masked symbol above, the realised profit below it, and the first eight
characters of the bot id at the foot. The profit colour is the theme's success
colour at zero and above and the error colour below, and the abdomen gradient
takes that same colour with its alpha scaled by the size of the figure.

The wires cover the grid alone, because the grid is the only view whose
coordinates a wire can be drawn against. Each wire carries its own percentage,
drawn beside it. Drag between two nodes to create a wire, and right-click a
wire to remove it. The quick routing matrix on the right is the same widget the
List view shows.

Detail: [08-tabs/bot-swarm.md](08-tabs/bot-swarm.md).

## Asset Charts

Under the Asset Charts Tab, you will find our active bot (position) chart display. This will be upgraded to display only one chart at a time and will be able to display all indicators found in the Indicator Voting Panel.

The tab scrolls one panel per active bot, each painted with QPainter and no
browser, carrying trade markers, position markers, grid lines, the standing
tranche floors and the target balance line.

`src/gui/main_tabs/charts_tab.py` — `ChartsTabMixin._build_charts_tab`

```python
def _build_charts_tab(self) -> None:
    """Build the Asset Charts tab and add it to the main tab widget."""
    # --- Tab 2: Charts ---
    self._charts_tab = TradeChartsTab()
    self._main_tabs.addTab(self._charts_tab, "Asset Charts")
```

The chart reads its overlays from the engine rather than computing any of them.

`src/gui/native_chart.py` — `CandlestickChart._compute_indicators`

```python
candles = self._candles
self._bb_data = BollingerBands(20, 2.0).bands(candles)
vi_plus, vi_minus = VortexIndicator(14).lines(candles)
```

Candles arrive through a fetcher with three sources in order: exchange OHLCV
first, a public API second, the last good fetch third.

`src/exchange/chart_data.py` — `ChartDataFetcher.fetch`

```python
# --- Source 1: Exchange OHLCV via CCXT ---
if exchange is not None:
    try:
        candles, source = await self._fetch_exchange(
            exchange, symbol, timeframe, limit
        )
        if candles:
            self._set_cache(symbol, timeframe, candles)
            return candles, source
```

![The Asset Charts tab, one panel per running bot.](p31-i0.png)

The panel set rebuilds from the current bot roster, and the tab scrolls them.

The header line of a panel names the symbol, the last price, the bot state, the
timeframe, the feed and the candle count. The line under it carries the open,
high, low and close of the current candle, the change in price and in percent,
and the volume. Rising candles draw teal and falling candles red.

The dashed lines across the plot are the standing fold-tranche floors, each
labelled with its price. `TB-Ceiling` is the dollar-target line. The price axis
runs down the right edge with the last price boxed on it, and the volume bars
run along the foot.

The toolbar under each panel holds the TF picker and eight indicator toggles.

`src/gui/main_tabs/native_chart_surface.py` — `INDICATOR_TOGGLES`

```python
INDICATOR_TOGGLES = (
    ("bb", "BB", "#50a0f0"),
    ("vortex", "Vortex", "#00ff88"),
    ("macd", "MACD", "#ffcc00"),
    ("stochrsi", "SRsi", "#ff9060"),
    ("ichimoku", "Ichi", "#c080ff"),
    ("volume", "Vol", "#80ffcc"),
    ("slingshot", "Sling", "#ff4488"),
    ("bbullseye", "BBull", "#ff00aa"),
)
```

Volume starts on and the other seven start off, which is the state the figure
shows. Sling and BBull paint a placeholder shape rather than the indicator, and
each says as much in its own tooltip. Issue #430 carries a tooltip on this
toolbar that names a colour the chart does not paint.

The legend at the right names the two position markers, Invisible and On Book,
and the feed label closes the row.

Detail: [08-tabs/asset-charts.md](08-tabs/asset-charts.md).

## History Tab

History Tab (React):

The History Tab is able to pull trade history from all active exchanges via their respective APIs. It also pairs each imported trade with its in-platform trading logic and applies our trade grading system.

The tab fetches from every active venue and draws the rows with React. Every
cell value comes from one read contract; the table renders those fields and
derives none, which stops a second History growing behind the renderer.

`src/exchange/history_read_contract.py` — `build_page`

```python
def build_page(
    filtered: list[dict],
    page: int = 0,
    bot_manager: Any = None,
    gate_index: Optional[dict] = None,
    voting_index: Optional[dict] = None,
) -> HistoryPage:
```

The grade comes from the trade grader and the gate lights come from the same
vocabulary the Simulator's gate cell reads. A refresh also hands the Simulator
its year of live trades, so the tab's signal front-loads the parity run.

![The History tab: filters, graded rows and the gate lights.](p32-i0.png)

The Filters group carries From and To date pickers, then Exchange, Symbol and
Side, each filled from the rows in hand. Apply narrows the set, Reset restores
it, and Refresh goes back to the venues. The line under the group counts the
retained rows against the loaded rows, both sides with their dollar totals, and
the age of the last fetch.

Thirteen columns carry a row, newest first, and nothing re-sorts. BUY draws
green and SELL red.

`src/exchange/history_read_contract.py` — `COLUMNS`, the first ten

```python
COLUMNS: tuple[HistoryColumn, ...] = (
    HistoryColumn(0, "timestamp", "Timestamp (UTC)"),
    HistoryColumn(1, "exchange", "Exchange"),
    HistoryColumn(2, "symbol", "Symbol"),
    HistoryColumn(3, "bot", "Bot"),
    HistoryColumn(4, "side", "Side"),
    HistoryColumn(5, "amount", "Amount"),
    HistoryColumn(6, "price", "Price"),
    HistoryColumn(7, "cost", "Cost USD"),
    HistoryColumn(8, "fee", "Fee"),
    HistoryColumn(9, "trade_id", "Trade ID"),
```

Grade, Gates and Voting close the set.

The Gates cell opens with the blocker text, then the lights. Nineteen of them:
the ten scrum gates TGT, INT, BB, FIRE, TA, LS, TRND, HTF, CB and OTD, then the
nine fold gates BB, MID, TA, LS, TRNQ, CEIL, HTF, CB and OTD. Each light draws
under its own label, and each bank ends with an `S` or an `F` marker. Five
states, five colours.

`src/trading/gate_vocabulary.py` — `LIGHT_COLORS`

```python
LIGHT_COLORS: dict[str, str] = {
    "override": "#22d3ee",
    "not_evaluated": "#333340",
    "blocked": "#ff3366",
    "passed": "#00cc55",
    "not_the_blocker": "#c8901e",
}
```

Green passed, red the gate that blocked, amber not armed for another reason,
grey not evaluated at this candle, and cyan a landing-strip override. The
blocker text and the light banks overlap in the figure; both occupy the one
cell.

Prev, the page counter and Next page the result at the foot, and Export CSV
writes the current selection out. The tab builds the summary line and the page
counter itself, and the read contract already declares both, so two
implementations of the same two strings stand in the tree. Issue #425 carries
it.

![The History tab during a fetch, with the header strip above it.](p32-i1.png)

The same tab, captured while the asynchronous fetch runs. Five fixed status
strings cover the states before any row exists, and the one on screen is the
fetching entry.

`src/exchange/history_read_contract.py` — `STATUS_TEXT`

```python
STATUS_TEXT = {
    "idle": "No history loaded yet — click Refresh.",
    "no_bot_manager": "Bot manager unavailable — cannot fetch history.",
    "no_async_loop": "Async loop not ready — try again after platform starts.",
    "fetching": "Fetching trade history from exchanges…",
    "timeout": "Fetch timeout (60s). Exchange may be rate-limited; try again.",
}
```

Two constants bound the fetch, in the same module: the poll runs on a 400 ms
timer, so an observed latency is the true latency plus up to one interval, and
the fetch is abandoned after sixty seconds.

`src/exchange/history_read_contract.py` — the fetch bounds

```python
FETCH_POLL_INTERVAL_S = 0.4
```

The header strip is visible here, which marks the screen as a live-trading tab.
REALISED and MATURE draw the same em dash the Trading tab draws. A row whose
gate log holds no entry inside the join window reads `no record`.

Detail: [08-tabs/history.md](08-tabs/history.md).

### Trade grading

The grader scores a trade that has already happened. It never feeds a trading
decision, it never tunes a parameter, and no gate consults it. The same inputs
always give the same grade.

Four axes are scored. An axis with no input is skipped: it neither credits nor
penalises, and the overall number is the unweighted mean of the rest.

`src/trading/trade_grader.py` — `grade_trade`

```python
exec_score, exec_bps = _score_execution(record, ctx)
timing_score, mfe, mae = _score_timing(record, ctx)
strategic_score, sb_delta = _score_strategic(record, ctx)
outcome_score, realized = _score_outcome(record, ctx)
```

| Axis | What it reads | What a 1.0 means |
| ---- | ------------- | ---------------- |
| Execution | fill price against the reference price at decision time | no slippage |
| Timing | the favourable excursion against the adverse one over the following candles | the trade went far more right than wrong before it closed |
| Strategic | the asset's discipline ratio before the trade against after it | the trade moved the ratio the operator's way |
| Outcome | realised profit per unit | a clear gain |

The regime tag reaches the grade and the rationale string and gets no score of
its own. Grading the same record with a regime tag and without one returns the
same number, which is the control that proves it.

The scale is 0.0 to 1.0, not 0 to 100, and the mean becomes a letter at fixed
boundaries.

`src/trading/trade_grader.py` — `_letter_from_numeric`

```python
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

Driving the mapper across each boundary and just under it flips the letter
exactly where the code says, in both directions.

**One trap worth knowing.** A trade with no gradeable input at all scores 0.5
and therefore reads as a **D**, not as ungraded. A fully specified trade scores
1.0 and reads A+. A column of Ds may mean the trades were poor, or it may mean
the surrounding price context never arrived.

## Console

This tab is focused on displaying Python activity and errors. The lower half, which is displaying the Emitter Network activity, will be migrated to the System Status Tab (under the Watchdog) which is to be built in the near future.

The tab builds both panes into a vertical splitter. The upper one is a raw log
tail: a handler formats each record and a relay paints it on the GUI thread,
which lets a log call from any thread reach the pane safely.

`src/gui/main_tabs/console_tab.py` — `ConsoleTabMixin._build_console_tab`

```python
self._console = QPlainTextEdit()
self._console.setReadOnly(True)
self._console.setFont(QFont("Consolas", 9))
```

The tab sets its own handler to debug and changes no logger's level; an earlier
build raised the root logger and never restored it.

`src/gui/main_tabs/console_tab.py` — `ConsoleTabMixin._build_console_tab`

```python
# The tab sets its own handler's level and leaves every logger level alone.
qt_handler.setLevel(logging.DEBUG)
```

Pause holds lines in a bounded buffer and announces anything it had to drop.

`src/gui/main_tabs/console_log_handler.py` — `_QtLogHandler.set_paused`

```python
self._paused = bool(paused)
if not self._paused and self._buffer:
    for msg, r, g, b in self._buffer:
        self._append_signal.emit(msg, r, g, b)
    self._buffer.clear()
```

The lower pane is the Emitter Network. It reads the sink twice a second and
renders the newest 200 records with their expected and actual values, keeping
seven counters, which lets a quiet sink and a stopped timer read differently.

`src/gui/main_window.py` — `_drain_signals`

```python
sink = get_sink()
if sink is None:
    return
new = sink.since(getattr(self, "_signal_seq", 0))
```

![The Console tab: the log tail above, the Emitter Network below.](p34-i0.png)

Pause and Clear sit above the upper pane. Pause holds lines in the bounded
buffer and announces anything it had to drop when it resumes. Clear empties the
pane.

Each line in the upper pane carries the time, the level, the logger name and
the message, coloured by level. Three logger names appear in the figure.

| Logger | Writes |
| ------ | ------ |
| `acervator.scrumming` | The bot warnings |
| `acervator.api` | The venue calls |
| `acervator.gui` | The panel feed |

Two of those lines are worth reading against the code. The repeated warning
naming a capital-reservation over-commit comes from
`src/trading/capital_reservation.py`, where a claim whose total would pass the
holdings is refused and the existing claims, the request and the holdings are
named. The `FETCH_OHLCV` line names a seven-indicator engine and lists seven
indicators; the voting engine builds twelve and the Indicator Voting Panel
shows twelve, so the count in the log line and the count in the engine
disagree.

The lower pane opens with the header `SIGNALS — name · expected · actual`. Each
record draws a pass marker, a fail marker or a neutral one, then the signal
name, the site that emitted it, the actual value and the expected one. A
satisfied expectation is recorded the same as a violated one, which keeps a
call site that never ran distinct from one that always passed.

Detail: [08-tabs/console.md](08-tabs/console.md).

### The two snapshot emitters

Two symmetric records go to the bot log, and the Console tab is where an
operator reads them. A blocked trade and a fired trade write the same shape, so
the log holds both halves of the decision and not only the half that acted.

`src/trading/scrumming/snapshots.py` — `SnapshotEmitterMixin._emit_risk_gate_snapshot`

```python
f"RISK GATE SNAPSHOT [{side.upper()}] "
f"risk_blockers={risk_blockers_sorted} "
f"ticker_last={ticker_last:.6g} "
f"panel={snapshot}"
```

The fired-side companion carries the same prefix shape.

`src/trading/scrumming/snapshots.py` — `SnapshotEmitterMixin._emit_trade_fire_snapshot`

```python
f"TRADE FIRED SNAPSHOT [{side.upper()}] "
f"ticker_last={ticker_last:.6g} "
f"panel={snapshot}{extra_str}"
```

| Method | Line prefix | Written when |
| ------ | ----------- | ------------ |
| `_emit_risk_gate_snapshot` | `RISK GATE SNAPSHOT [SIDE] ` | a risk gate blocks a trade |
| `_emit_trade_fire_snapshot` | `TRADE FIRED SNAPSHOT [SIDE] ` | a scrum or a fold actually fires |

Both lines carry the last ticker price and a panel dictionary holding every
voter's direction, confidence, weight and detail at that moment. The fire
record adds the list of overrides that engaged, so a reader can tell an
override-driven fire from a consensus-driven one without opening anything else.

Three further emitters sit in the same mixin: a trade notification carrying its
own text prefix, a voting-panel snapshot at fire time, and a gate decision at
fire time. The last two emit events rather than text lines, and the Console
tab's signal pane reads them.

## System Status Tab (To Be Built)

This tab consists of two distinct but closely related parts. The Emitter Network is an embedded system of data activity detectors intended to allow for detailed subsystem performance monitoring. The Watchdog is the raw signal capture for the Emitter Network’s output.

No tab exists, and the tab row names seven screens without it. Both halves run
today.

The Emitter Network is one plain function and one sink. A call site says what
it expected and what it actually saw, and a satisfied expectation is recorded
the same as a violated one, which keeps a call site that never ran distinct
from one that always passed.

`src/core/signal_contract.py` — `emit`

```python
def emit(
    name: str,
    actual: Any,
    expected: Any = None,
    ok: Optional[bool] = None,
    context: Optional[dict] = None,
    every: float = 0.0,
    instance: Optional[str] = None,
    module: Optional[str] = None,
    duration: Optional[float] = None,
) -> Optional[Signal]:
```

A second module declares every emitter. A contract names a topic's required
fields and its vocabulary, and the observer reports a topic that never fired, a
missing field or a value outside that vocabulary.

`src/core/emit_contracts.py` — the gate-decision contract

```python
EmitContract(
    topic="bot.gate_decision",
    required=("symbol",),
    optional=(
        "scrum_armed",
        "fold_armed",
        "scrum_blockers",
        "fold_blockers",
        "scrum_fixture",
        "fold_fixture",
    ),
    description="Gate evaluation snapshot at fire time.",
),
```

The Watchdog is `acervator_watchdog.py` at the repository root. It launches the
application as a child process, tees both output streams to its own log, polls
the heartbeat file, and writes a post-mortem after the child dies.

`acervator_watchdog.py` — the stall threshold and the poll

```python
DEFAULT_STALL_SECONDS = 60  # must match or exceed Acervator's longest sync call (CCXT: ~15s typical, 30s timeout)
HEARTBEAT_POLL_INTERVAL = 2.0
```

The screen the operator's text describes needs a name in the tab row and a pane
for each half. The upper pane's renderer already exists and nothing on any
screen calls it.

*Proposed, not present, in `src/gui/main_window.py`:*

```python
CANONICAL_TAB_ORDER = [
    "Trading",
    "Market Inspector",
    "Bot Swarm",
    "Asset Charts",
    "History",
    "Simulator",
    "Console",
    "System Status",
]
```

Detail: [08-tabs/system-status.md](08-tabs/system-status.md).

### Post-mortem bundle rotation

The Watchdog writes a post-mortem bundle every time the application dies. Each
bundle copies the runner's console log, the crash log, the fault-handler log
and a thread dump, which runs to hundreds of megabytes. Per-run log rotation
capped the size of one run's logs and capped nothing about the number of
bundles, so weeks of restarts grew without limit until the log directory took
the host down.

`acervator_watchdog.py` — `prune_postmortem_bundles`

```python
def prune_postmortem_bundles(
    keep_latest: int = POSTMORTEM_KEEP_LATEST,
    max_age_days: int = POSTMORTEM_MAX_AGE_DAYS,
    log_dir: Path | None = None,
) -> tuple[int, int]:
```

It keeps the most recent bundles, drops anything past a maximum age whatever
its position, and runs at two sites: once at Watchdog startup, which clears
what earlier runs left behind, and once after each post-mortem is written,
which holds the ceiling during a long session.

`acervator_watchdog.py` — the three constants

```python
POSTMORTEM_KEEP_LATEST: int = 20  # most-recent N bundles preserved
POSTMORTEM_MAX_AGE_DAYS: int = 30  # anything older is dropped
POSTMORTEM_SIZE_WARN_BYTES: int = 5 * 1024 * 1024 * 1024  # 5 GB warning threshold
```

The third is a warning threshold read by `report_log_dir_footprint` and it
deletes nothing, so two constants govern the rotation and one reports on it.
The only other inputs are the log directory itself, derived from the home
directory, and the literal bundle-name prefix inside the function. Neither is a
rotation constant.

No test in this repository references any of the three names. The cap runs and
nothing holds it in place.

## Settings

### Settings > User Tab

This needs to be built out to accept and contain individual end user credentials. This will also be where a license is entered or a keyfile is imported depending on how we design the authentication piece.

The dialog holds the eleven pages below, added in one order.

`src/gui/settings_dialog.py` — `SettingsDialog._setup_ui`

```python
tabs.addTab(self._create_user_tab(), "User")
tabs.addTab(self._create_exchange_tab(), "Exchanges")
tabs.addTab(self._create_trading_tab(), "Trading")
tabs.addTab(self._create_folding_tab(), "Profit Folding")
tabs.addTab(self._create_ta_tab(), "TA Indicators")
tabs.addTab(self._create_phantom_tab(), "Phantom Bots")
tabs.addTab(self._create_theme_tab(), "Theme")
tabs.addTab(self._create_logging_tab(), "Logging")
tabs.addTab(self._create_sound_tab(), "Sound")
tabs.addTab(self._create_sms_tab(), "SMS")
tabs.addTab(self._create_ai_monitor_tab(), "AI Monitor")
```

`_save` and `_load_current` decide which of them persists, and each page says
which under its own heading. Issue #423 carries the four pages whose controls
Save never reads.

The User page itself is one form row, and the settings manager persists it. No
credential field, no licence field and no key import.

`src/gui/settings_dialog.py` — `_create_user_tab`

```python
def _create_user_tab(self) -> QWidget:
    w = QWidget()
    form = QFormLayout(w)
    self._username = QLineEdit()
    form.addRow("Username:", self._username)
    return w
```

Both halves a credential store would rest on already exist, and the page reads
neither. `src/core/encryption.py` encrypts a secret with AES-256-GCM under a
key derived from a passphrase and a random salt.

`src/core/encryption.py` — `derive_key`

```python
def derive_key(passphrase: str, salt: bytes) -> bytes:
    """Derive a 256-bit AES key from *passphrase* + *salt* via PBKDF2."""
```

`src/core/usb_auth.py` writes an encrypted credential file keyed to a USB
volume's serial, which decrypts on that stick and nowhere else.

`src/core/usb_auth.py` — `write_auth_file`

```python
def write_auth_file(
    usb_path: Path,
    volume_serial: str,
    credentials: list[dict],
) -> Path:
```

![Settings, the User page.](p34-i1.png)

The title bar names the wing the dialog was opened for. The arrows at each end
of the page row scroll it, because the eleven do not fit the dialog's minimum
width. Cancel and Save close the dialog, and Save always closes it, reporting
any group that failed to persist. The page itself carries one row, Username,
and nothing else.

Detail: [08-tabs/settings.md](08-tabs/settings.md).

### Settings > Exchanges

The page lists the configured exchanges and adds one: the exchange picker, an
API key, an API secret, and a passphrase field that appears only when the venue
needs it. The picker fills from the connector layer, so it lists what that
layer can reach.

`src/exchange/ccxt_connector.py` — `SUPPORTED_EXCHANGES`, the first six

```python
SUPPORTED_EXCHANGES: dict[str, str] = {
    "binance": "binance",
    "coinbase": "coinbase",
    "kraken": "kraken",
    "kucoin": "kucoin",
    "bybit": "bybit",
    "okx": "okx",
```

Three venues need the passphrase field, and it appears for those alone.

`src/exchange/ccxt_connector.py` — `PASSPHRASE_EXCHANGES`

```python
PASSPHRASE_EXCHANGES: set[str] = {
    "kucoin",
    "okx",
    "bitget",
}
```

The key field accepts a Coinbase CDP key string and the secret field a PEM
elliptic-curve private key. The connection test runs before anything is stored,
and adding one routes the new tab to the crypto or the stock layer.

`src/gui/main_window.py` — `add_exchange_tab`

```python
def add_exchange_tab(self, exchange_id: str, display_name: str) -> None:
    """Add exchange tab to the correct layer (crypto or stock)."""
    is_equity = self._is_equity_exchange(exchange_id)
```

The same page in the stock wing shows a banner and disables Add and Test,
because no broker connector ships yet.

`src/gui/settings_dialog.py` — `_create_exchange_tab`

```python
_banner = QLabel(
    "<b>Stock Wing:</b> equity-broker integration is "
    "queued — no live brokers are wired up yet. The "
    "list below shows the planned brokers; Add / Test "
    "are disabled until the broker connectors ship. "
    "Use the Crypto Wing for active trading today."
)
```

![Settings, the Exchanges page.](p35-i0.png)

Configured Crypto Exchanges lists what the manager returns for this wing, each
entry naming its display name and its exchange id. The stock wing lists the
equity ids instead and disables both buttons.

The Add Crypto Exchange group holds four rows. Exchange fills from the
supported list. API Key takes a plain key or a Coinbase CDP key string, and its
placeholder shows the CDP shape. API Secret takes a plain secret or a PEM
elliptic-curve private key, and escaped newlines inside a pasted PEM convert on
the way in. The passphrase checkbox appears for the three venues above.

Test Connection runs the check and reports the answer. Test and Add Exchange
runs the same check first and stores nothing when it fails. Remove Selected
drops the highlighted entry.

Detail: [08-tabs/settings.md](08-tabs/settings.md).

### Settings > Trading

![Settings, the Trading page.](p36-i0.png)

Six rows carry the defaults a new bot starts from, not a running bot's
settings.

`src/gui/settings_dialog.py` — `_create_trading_tab`

```python
self._pos_distance = QDoubleSpinBox()
self._pos_distance.setRange(1.0, 50.0)
self._pos_distance.setSuffix("%")
self._pos_distance.setDecimals(1)
form.addRow("Position Distance:", self._pos_distance)
self._increment_style = QComboBox()
self._increment_style.addItems(["linear", "logarithmic"])
form.addRow("Increment Style:", self._increment_style)
self._default_positions = QSpinBox()
self._default_positions.setRange(1, 100)
form.addRow("Default Positions:", self._default_positions)
self._default_balance = QDoubleSpinBox()
self._default_balance.setRange(1.0, 1000000.0)
self._default_balance.setPrefix("$")
self._default_balance.setDecimals(2)
form.addRow("Default Target Balance:", self._default_balance)
self._visibility = QComboBox()
self._visibility.addItems(["orderbook", "internal"])
form.addRow("Bot Visibility:", self._visibility)
self._aggressive = QCheckBox("Enable aggressive trading mode")
```

Save writes all six. The load path reads back the first four only, so Bot
Visibility and the aggressive checkbox open at their built-in defaults whatever
was stored, and a Save with no edit overwrites the stored pair.

`src/gui/settings_dialog.py` — `_load_current`, the four it restores

```python
self._username.setText(self._sm.get("username", ""))
self._pos_distance.setValue(self._sm.get("position_distance_pct", 2.0))
self._default_positions.setValue(self._sm.get("default_position_count", 10))
self._default_balance.setValue(
    self._sm.get("default_target_balance", 200.0)
)
```

### Settings > Profit Folding

![Settings, the Profit Folding page.](p37-i0.png)

One master checkbox and three groups of radio buttons.

- Profit Folding / Upward Distribution Active, the master switch.
- Distribution Mode: Equal distribution or Logarithmic distribution.
- Profit Folding Target: fold to ALL buy positions, to a count of them, or to
  the most recent. The count spinbox holds 1 to 100.
- Upward Distribution Target: the same three choices on the sell side, with its
  own count.

Save collapses the two target groups into one dictionary.

`src/gui/settings_dialog.py` — `_save`

```python
fold_target = "all_buy"
if self._fold_x.isChecked():
    fold_target = "x_buy"
elif self._fold_recent.isChecked():
    fold_target = "most_recent_buy"
dist_target = "all_sell"
```

The load path restores the master switch alone, so the mode and both targets
open at the checked defaults the figure shows.

`src/gui/settings_dialog.py` — `_load_current`

```python
pf = self._sm.get("profit_folding", {})
self._folding_active.setChecked(pf.get("active", True))
```

### Settings > TA Indicators

![Settings, the TA Indicators page.](p38-i0.png)

One slider per weight, twelve in all, each labelled from its key and each
running 0.00 to 2.00. The value beside a slider follows it as it moves, and the
starting values are the weights themselves.

`src/trading/ta_engine.py` — `DEFAULT_WEIGHTS`

```python
DEFAULT_WEIGHTS = {
    "bollinger_bands": 1.0,
    "vortex": 0.9,
    "macd": 1.2,
    "stochastic_rsi": 1.0,
    "ichimoku": 1.1,
    "volume": 0.8,
    "slingshot": 1.0,
    "adx": 1.0,
    "kaufman_er": 1.0,  # Perry Kaufman Efficiency Ratio (regime classifier)
    "supertrend": 1.0,  # Olivier Seban ATR-trailing trend (reactive flip)
    "zscore": 0.9,  # Statistical extremity over a longer window than BB
    # Both are built on Wilder's RSI, so this vote overlaps stochastic_rsi.
    "rsi": 0.8,
}
```

A weight moved here reaches nothing. Save reads no widget on this page, the
load path restores none, and the settings schema declares no field for
indicator weights. The voting engine takes a weights argument and falls back to
the defaults above, and no construction site under `src/` supplies one from the
settings store. The page label promises an adjustment the engine never sees.
Issue #423 carries it.

### Settings > Phantom Bots

![Settings, the Phantom Bots page.](p39-i0.png)

The master checkbox, eleven timeframe boxes — 1m, 5m, 15m, 30m, 1h, 2h, 4h, 6h,
12h, 1d and 1w — and one Higher-TF Lock Settings group holding Lock duration in
candles, 1 to 10. The build checks 5m, 15m, 1h, 4h and 1d, which is the state
the figure shows.

These three controls carry the same gap the TA Indicators page carries. Save
reads none of them, the load path restores none, and the schema refuses a key
it does not declare rather than storing it somewhere unread.

`src/core/settings.py` — `SettingsManager.set`

```python
with self._lock:
    if not hasattr(self._settings, key):
        raise KeyError(f"Unknown setting: {key}")
    setattr(self._settings, key, value)
    self._save()
```

The per-bot equivalents in the wizard's phantom page and in the Live Bot
Settings dialog do persist, through the bot's own config.

### Settings > Theme

![Settings, the Theme page.](p40-i0.png)

The theme picker, the accent colour field and a Font Settings group.

- Visual Theme lists five display names: Cyberpunk Dark, Neon Light, Classic
  Terminal, Minimal Modern and Glass & Metal.
- Accent Color is a free-text field, placeholder `#00ffcc`.
- Font Family is an editable combo over twelve named families.
- Base Font Size, 8 pt to 24 pt. Heading Font Size, 10 pt to 32 pt. Log Font
  Size, 8 pt to 18 pt.
- Preview redraws in the chosen family and base size as either changes.

The five come from one mapping built off the five theme objects.

`src/gui/theme_engine.py` — `THEMES`

```python
THEMES: dict[str, ThemeTokens] = {
    t.name: t
    for t in [CYBERPUNK_DARK, NEON_LIGHT, CLASSIC_TERMINAL, MINIMAL_MODERN, GLASS_METAL]
}
```

Save writes the theme, the Accent Color field and all four font values.

`src/gui/settings_dialog.py` — `_save`, the theme and font keys

```python
"theme": lambda: self._theme_combo.currentData(),
"accent_color": lambda: self._accent_color.text().strip(),
"font_family": lambda: self._font_family.currentText(),
"font_size": lambda: self._font_size.value(),
"heading_font_size": lambda: self._heading_size.value(),
"log_font_size": lambda: self._log_font_size.value(),
```

The load path reads back the theme and the accent field only, so the four font
rows open at Segoe UI, 11, 14 and 10 whatever was stored.

### Settings > Logging

![Settings, the Logging page.](p41-i0.png)

Two checkboxes and four periodicity boxes:

- Log TA signal samples with all values and timestamps, checked at build.
- Highlight entries near Scrumming Bot trades, checked at build.
- P/L Log Periodicity: 24 Hours, 1 Week, 1 Month and 1 Year. The build checks
  the first two.

Save collapses all six into one dictionary holding the two flags and the list
of active periodicities. The load path reads none of them back, so every open
shows the build state rather than the stored one.

In development. What the load path should restore for this page has not been
settled against the rest of the dialog, so nothing is proposed here.

### Settings > Sound

![Settings, the Sound page.](p42-i0.png)

The master switch, eight event checkboxes, a volume slider and six test
buttons. Every checkbox is checked at build.

- Buy order fills, Sell order fills, Errors, Bot state changes, Scrum/Fold
  Fire, Tracking beeps, P/L increase and Accumulation. Each names its sound in
  the label, and six of the eight carry a tooltip naming when it fires: the
  tracking beep is silent in SEARCH, slow in TRACK and fast in FIRE, and the
  water drip fires on FOLD alone.
- SFX Volume, 0 % to 100 %, at 70 %.
- Test Buy, Test Sell, Test Fire, Test Track, Test Profit and Test Drip play one
  sample each.

One handler is the only path from this page to the engine. It builds a
configuration from every checkbox and the slider, pushes it in and clears the
sample cache, because each sample bakes its volume at synthesis time.

`src/gui/settings_dialog.py` — `_on_sfx_volume_changed`

```python
se = get_sound_engine()
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

That path runs when the slider moves or a test button is pressed, and at no
other time. Save reads no widget on this page and the schema declares no sound
field, so nothing here survives the dialog closing. Issue #423 carries it.

### Settings > SMS

![Settings, the SMS page.](p43-i0.png)

A scrolling page holding the master switch and three groups.

- SMS Provider: Provider, offering Email-to-SMS Gateway or Twilio API, and
  Phone Number.
- Email Gateway Settings: Carrier, then Gateway Email, SMTP Username and SMTP
  Password. The password field masks its input.
- Notification Events: Buy fills, Sell fills, Bot state changes, API errors and
  failures, P/L threshold alerts with its dollar amount, Low balance warnings,
  and Exchange connection status. The first four are checked at build.
- Rate Limiting, below the area the figure shows: Max messages per hour, 1 to
  100 at 20, and Min time between messages, 5 to 300 seconds at 30.

The Carrier list fills from one mapping of carrier name to gateway address.

`src/core/sms_engine.py` — `CARRIER_GATEWAYS`, the first four

```python
CARRIER_GATEWAYS = {
    "AT&T": "{number}@txt.att.net",
    "T-Mobile": "{number}@tmomail.net",
    "Verizon": "{number}@vtext.com",
    "Sprint": "{number}@messaging.sprintpcs.com",
```

None of it reaches the SMS engine. Save reads no widget on this page and the
schema declares no SMS field. Neither provider label the combo offers matches
the value the engine tests for, and the page carries no field for the three
Twilio credentials the send path reads.

`src/core/sms_engine.py` — `SMSConfig.provider`, the value the send path tests

```python
    provider: str = "email_gateway"
```

Issue #423 carries the page.

### Settings > AI Monitor

![Settings, the AI Monitor page.](p44-i0.png)

A scrolling page holding four groups.

- Claude API Connection: Anthropic API Key, masked, and Check interval, 0.5 to
  24.0 hours at 4.0.
- Handshake Authentication: a note naming what each phrase does, then Connect
  phrase and Confirm phrase.
- Monitor Behavior: Enable AI Monitor feedback loop, clear at build, then
  Auto-handshake on first analysis and Log AI feedback to trade journal, both
  checked.
- Connection Status, below the area the figure shows: a status line, a journal
  hash, a completed-check count and a Test Handshake button.

Save writes all seven controls into one dictionary and the load path reads all
seven back, which makes this the one page besides User whose whole state
round-trips.

`src/gui/settings_dialog.py` — `_load_current`, the seven it restores

```python
ai = self._sm.get("ai_monitor", {})
self._ai_api_key.setText(ai.get("api_key", ""))
self._ai_interval.setValue(ai.get("interval_hours", 4.0))
self._ai_connect_phrase.setText(ai.get("connect_phrase", ""))
self._ai_confirm_phrase.setText(ai.get("confirm_phrase", ""))
self._ai_enabled.setChecked(ai.get("enabled", False))
self._ai_auto_handshake.setChecked(ai.get("auto_handshake", True))
self._ai_log_feedback.setChecked(ai.get("log_feedback", True))
```

Test Handshake runs no handshake. It checks that the key and both phrases hold
text, then writes either an error line or the message saying the handshake runs
on the next bot cycle.

`src/gui/settings_dialog.py` — `_test_ai_handshake`

```python
self._ai_status.setText("Settings saved — handshake runs on next bot cycle")
self._ai_status.setStyleSheet("color: #00ddff; font-weight: bold;")
```

The button reports the fields it read, never a venue answer.
