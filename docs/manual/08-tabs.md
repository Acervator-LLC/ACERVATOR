# Subsystem Tabs

Reference. Main Window, Market Inspector and Asset Charts each have a heading
below, and the manual's own text for the screen comes first with what the code
does today under it. Every other screen has one section of its own, one file per
screen in [08-tabs/](08-tabs/README.md), and this part points at it rather than
repeating it.

Detail: [08-tabs/simulator.md](08-tabs/simulator.md).
Detail: [08-tabs/paper-trader.md](08-tabs/paper-trader.md).
Detail: [08-tabs/proof-of-accumulation.md](08-tabs/proof-of-accumulation.md).
Detail: [08-tabs/bot-swarm.md](08-tabs/bot-swarm.md).
Detail: [08-tabs/history.md](08-tabs/history.md).
Detail: [08-tabs/console.md](08-tabs/console.md).
Detail: [08-tabs/system-status.md](08-tabs/system-status.md).
Detail: [08-tabs/settings.md](08-tabs/settings.md).

One list names the ten tabs the window builds, and every screen below that the
window does not build says as much in its own entry. Two are skeletons now:
Status and Accumulation each draw a name, one sentence saying the tab is not
built, and the issue that carries the build-out. Sim and Paper were skeletons
until issues #117 and #19 built them, and both are full screens today.

`src/gui/main_tabs/main_window_surface.py` — the order before issue #450

```python
CANONICAL_TAB_ORDER = (
    TRADING_TAB,
    MARKET_INSPECTOR_TAB,
    BOT_SWARM_TAB,
    ASSET_CHARTS_TAB,
    HISTORY_TAB,
    SIMULATOR_TAB,
    CONSOLE_TAB,
    PAPER_TRADER_TAB,
    SYSTEM_STATUS_TAB,
    PROOF_OF_ACCUMULATION_TAB,
)
```

Each of those names is a constant holding the label the tab bar shows. The
skeletons take their label from their own surface, so the bar and the
screen cannot carry two spellings of one name. Issue #450 renamed every one of
those constants and reordered the tuple, and the section under this one holds
what the file carries today.

`src/gui/main_tabs/main_window_surface.py` — the labels before issue #450

```python
TRADING_TAB = "Trading"
MARKET_INSPECTOR_TAB = "Market Inspector"
BOT_SWARM_TAB = "Bot Swarm"
ASSET_CHARTS_TAB = "Asset Charts"
HISTORY_TAB = "History"
SIMULATOR_TAB = "Simulator"
CONSOLE_TAB = "Console"

PAPER_TRADER_TAB = paper_trader_tab_surface.HEADING
SYSTEM_STATUS_TAB = system_status_tab_surface.HEADING
PROOF_OF_ACCUMULATION_TAB = proof_of_accumulation_tab_surface.HEADING
```

### The order, the names and the colours today

The bar now opens on Sim and every tab carries a single word. The order below is
what the window ends with, and it is decided in the one place named above.

`src/gui/main_tabs/main_window_surface.py` — `CANONICAL_TAB_ORDER`

```python
CANONICAL_TAB_ORDER = (
    SIM_TAB,
    PAPER_TAB,
    LIVE_TAB,
    CHARTS_TAB,
    INSPECTOR_TAB,
    SWARM_TAB,
    ACCUMULATION_TAB,
    HISTORY_TAB,
    STATUS_TAB,
    CONSOLE_TAB,
)
```

Eight of the ten labels are new words for screens that already existed. History
and Console were already one word and did not change. Each constant was renamed
to match the word it now holds.

`src/gui/main_tabs/main_window_surface.py` — the labels

```python
LIVE_TAB = "Live"
INSPECTOR_TAB = "Inspector"
SWARM_TAB = "Swarm"
CHARTS_TAB = "Charts"
HISTORY_TAB = "History"
SIM_TAB = "Sim"
CONSOLE_TAB = "Console"

PAPER_TAB = paper_trader_tab_surface.HEADING
STATUS_TAB = system_status_tab_surface.HEADING
ACCUMULATION_TAB = proof_of_accumulation_tab_surface.HEADING
```

The eight renames, in the order the bar reads them:

| was | is now |
| --- | ------ |
| Simulator | Sim |
| Paper Trader | Paper |
| Trading | Live |
| Asset Charts | Charts |
| Market Inspector | Inspector |
| Bot Swarm | Swarm |
| Proof of Accumulation | Accumulation |
| System Status | Status |

Sim, Paper and Live carry the promotion pipeline, and three different grounds
separate them at a glance. The other seven tabs share the gold ground.

`src/gui/main_tabs/main_window_surface.py` — `TAB_GROUNDS`

```python
TAB_GROUNDS = {
    SIM_TAB: BLACK_GROUND,
    PAPER_TAB: WHITE_GROUND,
    LIVE_TAB: GOLD_GROUND,
    CHARTS_TAB: GOLD_GROUND,
    INSPECTOR_TAB: GOLD_GROUND,
    SWARM_TAB: GOLD_GROUND,
    ACCUMULATION_TAB: GOLD_GROUND,
    HISTORY_TAB: GOLD_GROUND,
    STATUS_TAB: GOLD_GROUND,
    CONSOLE_TAB: GOLD_GROUND,
}
```

No tab holds a colour of its own. A ground names two theme tokens, and every
theme fills those tokens with its own values, so gold is the yellow that suits
each theme rather than one hex value everywhere.

`src/gui/theme_engine.py` — the six tab tokens each theme carries

```
theme             tab_gold_bg tab_gold_text tab_black_bg tab_black_text tab_white_bg tab_white_text
cyberpunk_dark    #fcee0a     #8c0018       #0a0a0f      #ff5577        #f5f5fa      #0a0a0f
neon_light        #f0cf1f     #99001f       #1a1a2e      #ff6b8a        #ffffff      #1a1a2e
classic_terminal  #ffff00     #990000       #0a0a0a      #ff3333        #e8e8e8      #0a0a0a
minimal_modern    #eab308     #7f1d1d       #1a1a1a      #ff6b6b        #ffffff      #1a1a1a
glass_metal       #e8b34a     #6b1020       #1c1c24      #ff6688        #e8e8f0      #1c1c24
```

Every pair above clears WCAG 2.2 AA at 4.5 to 1. The narrowest margin is red on
gold under Minimal Modern, at 5.22 to 1.

The Qt bar paints those colours itself, because a Qt style sheet cannot colour
one tab by its position. The theme's own style sheet sets the six colours on the
bar, so switching theme repaints it.

`src/gui/main_tabs/main_tab_bar.py` — `MainWindowTabBar.paintEvent`

```python
painter.fillRect(self.tabRect(index), ground)
painter.setPen(text)
painter.drawText(self.tabRect(index), int(Qt.AlignCenter), self.tabText(index))
```

The React bar draws the same ten buttons with the same two colours each. The
window publishes the colours beside the labels, so the page holds no palette of
its own.

`src/gui/main_tabs/main_window_surface.py` — what the frontend reads

```python
"tab_labels": list(self.tab_labels),
"tab_methods": dict(self.tab_methods),
"tab_colours": {tab: dict(pair) for tab, pair in self.tab_colours.items()},
"theme": self.theme,
```

The Live tab, which the manual's part list calls the Trading Tab, has its own
section, [06-trading-tab.md](06-trading-tab.md), and the Indicator Voting Panel
has [07-indicators.md](07-indicators.md).

A strategy reaches real money through four steps: Market Inspector, Simulator,
Paper Trader, Live. Each step is a gate, and all four screens are built.
[08-tabs/promotion-pipeline.md](08-tabs/promotion-pipeline.md) draws the chain
and marks where a step still hands nothing to the next.

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
Swarm tab shares. The strip hides itself while the Sim tab or the Paper tab is
active, and the Paper tab draws four figures of its own in place of it.
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

Both columns now carry an exchange figure. The window hands the strip the same
payload the React strip receives, built by one function, so the two hosts cannot
show different numbers.

`src/gui/main_window.py` — `_refresh_dashboard`

```python
self._spendable_widget.update_profits(
    header_strip_surface.profits_payload(agg, exchanges)
)
```

REALISED is the venue's matched profit and loss across the fleet. MATURE is the
profit held in positions worth more than three times what they cost. Where the
venue has answered for no bot, both stay empty, and the mask now leaves an empty
column empty instead of drawing four asterisks over it.

`src/gui/main_tabs/header_strip_surface.py` — `exchange_amount`

```python
answered = int(data.get(EXCHANGE_FRESHNESS_KEY, 0) or 0)
if answered <= 0:
    return None
```

Detail: [08-tabs/portfolio-panels.md](08-tabs/portfolio-panels.md).

## Market Inspector Tab

The concept with the Market Inspector Tab is evaluate markets from a higher point of view and provide strategy proposals in three forms: Oppositional Trading Pairs (Trading Pairs w/ Opposing Trends), Bot Swarm Topologies (Bot Swarm Network Proposals), and Exchange Comparison Arbitrage.

The tab is now called Inspector. It sits fifth on the bar, on the gold
ground with red text.

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

`src/gui/main_tabs/market_inspector_topologies_surface.py` — `persist_dismissed`

```python
def persist_dismissed(self) -> None:
    """Best-effort write-through. Never raises."""
    if self.dismiss_store is None:
        return
    try:
    self.dismiss_store.set(DISMISS_SETTINGS_KEY, dict(self.dismissed))
```

The key it writes is not one the settings schema declares, so the write fails
every time. Issue #424 carries it.

The footer names the auto-refresh period and the adopt route. The status bar
under it carries the API load pill, drawn green below half load, amber above
it, and red past the monitor's safety percentage, then the `AI:` state label.

React draws this screen. Both halves are one web page inside a single view,
and the build decides which class the tab builder makes.
`src/gui/main_tabs/market_inspector_tab.py` — `_build_market_inspector_tab`

```python
from ..variant_surface import MARKET_INSPECTOR, surface_class

self._market_inspector = surface_class(MARKET_INSPECTOR)()
```

`MarketInspectorReactTab` subclasses the Qt tab, so the scan cycle, the
filtering and the analyzer writes are the same code on both sides. Five
accessors are what the two sides answer differently: `_set_status`,
`_set_refresh_enabled`, `_shown_signals`, `_fill_signal_rows` and
`_fill_pair_rows`. The Qt tab writes them into its widgets and the React tab
writes them into the page.

`src/gui/react_market_inspector_tab.py` — `MarketInspectorReactTab._build_ui`

```python
self._web = QWebEngineView(self)
self._web_page = MarketInspectorPage(self)
self._web.setPage(self._web_page)
self._web.loadFinished.connect(self._on_load_finished)
self._web.setHtml(tab_html())
```

Refresh and the Include active markets checkbox report their press back to
Python, and the right pane reports Refresh proposals, Preview, Dismiss, Cancel
and Adopt the same way. Setting `ACERVATOR_VARIANT` to `qt` builds the Qt
widgets instead, unchanged.

Detail: [08-tabs/market-inspector.md](08-tabs/market-inspector.md).

## Asset Charts

Under the Asset Charts Tab, you will find our active bot (position) chart display. This will be upgraded to display only one chart at a time and will be able to display all indicators found in the Indicator Voting Panel.

The tab is now called Charts. It sits fourth on the bar, straight after
Live, on the gold ground with red text.

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

### One chart, chosen with the arrows

The tab now draws one chart at a time. A left arrow, a centre ticker list and a
right arrow choose which traded asset it shows, and a readout beside them says
which of how many is on screen. The list wraps, so neither arrow dead-ends, and
the ticker readout is itself a drop-down. With no bots running the readout says
zero of zero and both arrows are switched off.

`src/gui/widgets/trade_charts_tab.py` — the readout beside the arrows

```python
POSITION_FORMAT = "{at} of {total}"
EMPTY_TICKER_TEXT = "No asset"
EMPTY_POSITION_TEXT = "0 of 0"
```

### The toggles, and the two that start off

Every indicator the chart can draw now starts switched on, and a check box for
each sits along the bottom of the panel. Two start off, because each paints a
filled shape over the price where the Bollinger bands and the Ichimoku cloud
are drawn. Slingshot paints solid marks at a squeeze release and a snapback.
BB Bullseye paints four shaded envelopes directly on the bands themselves.

`src/gui/native_chart.py` — one entry per drawn indicator

```python
class ChartOverlay:
    key: str
    label: str
    colour_field: str
    pane: str
    occludes: bool
    draw: str
    tooltip: str
```

### The renderer is built to grow

`CHART_OVERLAYS` declares each indicator once, and the paint routine walks that
list rather than naming any of them. Another overlay is one entry in the list
and one draw method; no existing overlay is touched to add it.

The renderer holds no colour of its own. Every painted value resolves through
`PALETTE_ROLES`, which names the theme field and the transparency each role
reads, so a theme sets the look and the renderer does not.

### 2026-09-08 23:40 - #128 - the chart registers a panel in the shell

The chart now joins the Electron shell's roster of panels. Before this change
the shell listed fifteen panels and said of this one that it registered nothing
to draw. It now lists sixteen and says nothing.

`src/gui/web/native_chart.js` — the chart joins the roster

```javascript
  if (global.acervatorPanelHost) {
    global.acervatorPanelHost.register({
      render: renderChart,
      load: loadChart,
      loadError: loadError
    });
  }
```

The chart takes no tab of its own. It names no bridge method the application
serves a tab from, so the tab bar passes over it and the chart draws where it
belongs, inside the Charts tab. The ten tabs the application reports are the
same ten before and after.

The chart in the shell still draws its waiting line rather than a price. The
Charts tab asks it for a symbol and a timeframe and sends none of the 180
candles the tab itself holds, and the symbol it sends is empty. Both values
belong to the Charts tab file, not to the chart, so the row below keeps `no`
under Registers in Electron until they are carried across.

### 2026-09-09 01:20 - #128 - the Charts tab hands the chart its data

The chart in the shell draws the price now. The tab passes it the asset it is
following, the feed name, the candles it is holding and the size of the space
the chart has, and the shell's panel host does the drawing rather than the tab
reaching past it.

`src/gui/web/trade_charts_tab.js` — what the chart slot asks for

```javascript
          return global.acervator.call(api.method, {
            reset: true,
            symbol: symbol,
            timeframe: mount.getAttribute(CHART_TF_ATTR),
            source: text(panel[SOURCE]),
            candles: candles,
            width: mount.clientWidth,
            height: mount.clientHeight
          });
```

The panel carries the asset it follows. It was built once with a blank name and
renamed only its header line, so the name the chart was asked for was always
blank.

`src/gui/main_tabs/trade_charts_tab_surface.py` — the panel's own asset

```python
    def set_symbol_property(self, symbol: Any) -> None:
        """Rename the chart through its public setter, which repaints."""
        self.symbol = symbol
        self.label = symbol
```

Both builds now draw the same header, the same 180 candles, the same last price
of 78,623.00, the same three axis prices and the same time axis. The two
pictures still differ on the indicator lines. The Bollinger bands, the Ichimoku
cloud and the Vortex, MACD and Stochastic RSI panes draw in the Qt build and in
neither place in the shell, because nothing hands the chart those five readings
yet. The eight indicator switches under the Qt chart are absent in the shell for
the same reason. The row below keeps `no` under Registers in Electron until the
readings arrive.

### 2026-09-09 03:05 - #128 - the indicators draw in both builds

The chart in the shell draws every indicator the Qt chart draws. The five
readings now reach it: the Bollinger bands with their cloud, the Ichimoku cloud
with its four lines and the lagging line, and the Vortex, MACD and Stochastic
RSI panes under the price. The eight switches sit under the chart with Slingshot
and BB Bullseye off, and the two position markers sit on the toolbar beside the
feed name.

Each reading is the one the indicator itself published. The chart asks the five
indicator classes for their values and paints what they answer.

`src/gui/main_tabs/native_chart_surface.py` — the chart takes its readings

```python
        self.set_indicator_series(
            bb=BollingerBands(BOLLINGER_PERIOD, BOLLINGER_STD).bands(candles),
```

Both builds were driven from the same 38 running bots and the same 180 daily
BTC/USD candles. Both draw the same header, the same candles, the same last
price of 78,623.00, the same four axis prices, the same time axis, and the same
three panes reading Vortex 0.8761, MACD -245.82 and Stoch RSI 0.2318. The row
below now reads `yes` under Registers in Electron.

Two figures moved to make that true. The Qt chart asked for 492 pixels and was
given 250 until an indicator switch was pressed, so its MACD pane, its Stochastic
RSI pane and its time axis were cut off; it now takes its full height as soon as
the candles arrive. The panes were also listed as MACD, Vortex, Stochastic RSI in
one place and Vortex, MACD, Stochastic RSI in the other; the switch order decides,
so both now read Vortex, MACD, Stochastic RSI.

The volume bars are empty in both pictures. The public feed serves no volume with
its daily candles, so that one row of the comparison rests on two empty strips.

`src/gui/theme_engine.py` — the chart tokens each theme carries

```python
chart_bg_top: str = "#08080e"
chart_up: str = "#00e5a0"
chart_down: str = "#ff2d6f"
chart_zone_fold: str = "#fcee0a"
```

Detail: [08-tabs/asset-charts.md](08-tabs/asset-charts.md).

## Converting the Interface to React

Every screen in this application is drawn by Qt. Issue #128 replaces them with
React and keeps the backend in Python. This section is the running record of
that work. One row per screen, one column per step, and a mark only where the
step is finished.

One screen draws React in the application today: the History table. It runs
inside the Chromium that the Qt toolkit already ships, not inside Electron.

`src/gui/react_history_panel.py` — `HistoryWebTable._setup_ui`

```python
self._web = QWebEngineView()
self._web.loadFinished.connect(self._on_load_finished)
self._web.setHtml(panel_html(theme))
layout.addWidget(self._web, 1)
```

### What the tree holds

Measured on 5 September 2026 over the tracked files.

```
React modules             70 files, 80,292 lines, 0 stub markers
                          65 of them call React.createElement
                          React and ReactDOM are vendored on disk
View-model modules        74 files, 74,207 lines
Parity tests              72 files, 170,244 lines
Electron shell             8 code files, 791 lines, plus a package manifest
Renderer manifest         70 names
Qt modules under src/gui  69, every one importing PySide6
Tabs drawn by React        0
```

No file in this repository has ever carried a JavaScript extension other than
plain `.js`. A history search over every branch returns no commit that added,
deleted or renamed one, and the same search for the plain extension returns 81
paths, so the search does find a file that existed.

```
git log --all --diff-filter=ADR --name-only -- "*.jsx" "*.tsx" "*.ts"   no commits
git log --all --diff-filter=ADR --name-only -- "*.js"                   81 paths
```

### What the Electron shell drew

The shell has been started once, and what it drew is measured. All 70 renderer
modules loaded and none failed. Two of them register a panel for the page to
draw, so the page had nothing to ask the other 68 for. The window showed an
empty History table, with no tab bar and no navigation.

```
React modules the page list names   70
modules that failed to load          0
modules that register a panel        2
panels the page asked to draw        2
panels that failed to draw           0
```

The two that register are the Console tab panel and the header strip. The full
per-file record is in
[docs/audits/2026-09-05_128_file_verification.md](../audits/2026-09-05_128_file_verification.md).

### The tab bar the shell draws now

The shell builds the same ten tabs the application builds, with the same labels
and in the same order. It holds no list of its own. `main_window.state` reports
`tab_labels` and `tab_methods`; the bar keeps one tab per label, filled by the
registered panel that calls that label's bridge method.

```
Sim  Paper  Live  Charts  Inspector
Swarm  Accumulation  History  Status  Console
```

A module that draws a screen inside a dialog registers no bridge method and
takes no tab. `market_inspector_tab.js` and `bot_swarm_tab.js` are the two:
both belong to the Live Bot Settings dialog.

Measured in one Electron launch, with the backend serving a two-bot fleet:

```
tabs on the bar                     10
panels that drew text               10
panels that failed to draw           0
child panels drawn inside a tab      7
```

The header strip stays above the bar for every tab.

### How to read the table

Each row is a Qt module the running window builds. The columns are the steps of
the conversion, in the order the work happens.

| Column | What the mark means |
| ------ | ------------------- |
| React module | A renderer module in `src/gui/web` serves this screen |
| Surface | A Python view model of the screen exists, with no toolkit in it |
| Bridge | The view model is registered as a method the frontend may call |
| Manifest | The renderer module is named in the shell's module list |
| Ships in the build | The built React application carries the module inside it |
| RENDERS | What the operator sees when he opens that screen |
| Scope | Whether the row is work this item must do |

The last column is the item. A row is finished only when it reads `yes`. Every
other column can be marked while the operator sees no change, and that is the
difference between wiring written and a screen replaced.

The RENDERS column takes three values, and none of them is derived from the
bridge or the manifest. `yes` means React draws where Qt used to. `shell` means
the module draws in the Electron shell and nowhere else. A dash means the Qt
widget is still the screen.

The Scope column names the module that builds a screen the item has still to
convert. Header strip and window chrome are the parts of the Main Window that
sit outside the tab row.

The table carries nine columns and no tab column. The screen a module draws is
named in that screen's own section above. Header strip and window chrome are
the parts of the Main Window that sit outside the tab row.

The Scope column takes five values.

| Value | What it means |
| ----- | ------------- |
| in scope | The running window builds this screen, and the cell names what builds it |
| React side | The file exists because of this conversion, so a React module for it would be a module for a module |
| not a screen | The module defines no view |
| builds the shell | The module fills the tab bar rather than sitting in it |
| shelved | Nothing the window builds reaches it |

The walk that answers the column starts at the main window. It follows an
imported name only where the module calls that name, subclasses it or reads an
attribute of it, so a re-export block reaches nothing. A row is in scope when
some module on that walk builds one of the classes the row defines.

`tools/conversion_scope.py` writes the column, so the answers are re-measured
rather than typed.

### The conversion table

| Qt file | React module | Uses React | Bridge | Manifest | Registers in Electron | Ships in the build | RENDERS | Scope |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `splash_screen.py` | no | - | yes | no | no | - | no | shelved |
| `src/gui/alerts_tab.py` | `alerts_tab.js` | yes | yes | yes | no | yes | yes | in scope |
| `src/gui/analytics_tab.py` | `analytics_tab.js` | yes | yes | yes | no | yes | no | shelved |
| `src/gui/audio_suite.py` | `audio_suite.js` | yes | yes | yes | no | yes | no | shelved |
| `src/gui/bot_live_settings.py` | `bot_live_settings.js` | yes | yes | yes | no | yes | yes | in scope |
| `src/gui/bot_swarm_list.py` | removed | - | - | - | - | - | - | deleted |
| `src/gui/bot_visualizer.py` | `bot_visualizer.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/bot_wizard.py` | `bot_wizard.js` | yes | yes | yes | no | yes | yes | in scope |
| `src/gui/buy_confirmation_dialog.py` | `buy_confirmation.js` | yes | yes | yes | no | yes | yes | in scope |
| `src/gui/competition_tab.py` | `competition_tab.js` | yes | yes | yes | no | yes | no | shelved |
| `src/gui/crypto_news_ticker.py` | `crypto_news_ticker.js` | yes | yes | yes | no | yes | yes | in scope |
| `src/gui/history_qt_table.py` | no | - | no | no | no | - | no | React side |
| `src/gui/history_tab.py` | `history_tab.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/indicator_panel.py` | `indicator_panel.js` | yes | yes | yes | no | yes | yes | in scope |
| `src/gui/init_wizard.py` | `init_wizard.js` | yes | yes | yes | no | yes | no | shelved |
| `src/gui/instance_consent_dialog.py` | `instance_consent_dialog.js` | yes | no | yes | no | yes | no | shelved |
| `src/gui/journal_tab.py` | `journal_tab.js` | yes | yes | yes | no | yes | no | shelved |
| `src/gui/launcher.py` | `launcher.js` | yes | yes | yes | no | yes | no | shelved |
| `src/gui/live_bot_window.py` | no | - | yes | no | no | - | no | shelved |
| `src/gui/live_settings/bot_swarm_tab.py` | `bot_swarm_tab.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/live_settings/fold_chrome.py` | `fold_chrome.js` | yes | yes | yes | no | yes | yes | in scope |
| `src/gui/live_settings/fold_tokens.py` | `fold_tokens.js` | yes | yes | yes | no | yes | no | not a screen |
| `src/gui/live_settings/fold_tranches_tab.py` | `fold_tranches_tab.js` | yes | yes | yes | no | yes | yes | in scope |
| `src/gui/live_settings/market_inspector_tab.py` | `market_inspector_tab.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/live_settings/phantom_bots_tab.py` | `phantom_bots_tab.js` | yes | yes | yes | no | yes | yes | in scope |
| `src/gui/live_settings/positions_held_tab.py` | no | - | no | no | no | - | yes | in scope |
| `src/gui/live_settings/settings_tab.py` | `live_settings_tab.js` | yes | yes | yes | no | yes | yes | in scope |
| `src/gui/live_settings/stack_tranches_tab.py` | `stack_tranches_tab.js` | yes | yes | yes | no | yes | yes | in scope |
| `src/gui/live_settings/status_tab.py` | no | - | yes | no | no | - | yes | in scope |
| `src/gui/main_tabs/audio_suite_surface.py` | no | - | yes | no | no | - | no | React side |
| `src/gui/main_tabs/buy_confirmation_surface.py` | no | - | yes | no | no | - | no | React side |
| `src/gui/main_tabs/console_log_handler.py` | no | - | no | no | yes | - | yes | in scope |
| `src/gui/main_tabs/console_tab.py` | `console_tab.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/main_tabs/empty_tabs.py` | `system_status_tab.js`, `proof_of_accumulation_tab.js` | yes | yes | yes | yes | no | yes | in scope |
| `src/gui/main_tabs/header_strip.py` | `header_strip.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/main_tabs/stock_main_window_surface.py` | no | - | yes | no | no | - | no | React side |
| `src/gui/main_tabs/trading_tab.py` | `trading_tab.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/main_tabs/tradingview_chart_surface.py` | no | - | yes | no | no | - | no | React side |
| `src/gui/main_window.py` | `main_window.js` | yes | yes | yes | no | no | yes | in scope |
| `src/gui/market_inspector.py` | `market_inspector.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/market_inspector_topologies.py` | `market_inspector_topologies.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/native_chart.py` | `native_chart.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/paper_trader_tab.py` | `paper_trader_tab.js` | yes | yes | yes | yes | no | yes | in scope |
| `src/gui/qt_safe_events.py` | no | - | yes | no | no | - | no | not a screen |
| `src/gui/react_history_panel.py` | no | - | yes | no | no | - | no | React side |
| `src/gui/react_history_tab.py` | no | - | no | no | no | - | no | React side |
| `src/gui/react_paper_trader_tab.py` | no | - | no | no | no | - | no | React side |
| `src/gui/react_simulator_tab.py` | no | - | no | no | no | - | no | React side |
| `src/gui/risk_tab.py` | `risk_tab.js` | yes | yes | yes | no | yes | no | shelved |
| `src/gui/settings_dialog.py` | `settings_dialog.js` | yes | yes | yes | no | yes | yes | in scope |
| `src/gui/shared_testnet.py` | `shared_testnet.js` | no | yes | yes | no | yes | no | shelved |
| `src/gui/simulator_tab.py` | `simulator_tab.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/simulator_tab/fleet/fleet_replay_panel.py` | `fleet_replay_panel.js` | yes | yes | yes | no | yes | yes | shelved |
| `src/gui/simulator_tab/fleet/sim_visuals.py` | `sim_visuals.js` | yes | yes | yes | no | yes | yes | shelved |
| `src/gui/simulator_tab/nuclear_mode_panel.py` | `nuclear_mode_panel.js` | yes | yes | yes | no | yes | yes | shelved |
| `src/gui/simulator_tab/sim_stat_strip.py` | `sim_stat_strip.js` | yes | yes | yes | no | yes | yes | shelved |
| `src/gui/simulator_tab/simulator_tab.py` | `simulator_tab.js` | yes | yes | yes | yes | yes | yes | shelved |
| `src/gui/start_all_progress_dialog.py` | `start_all_progress.js` | yes | yes | yes | no | yes | yes | in scope |
| `src/gui/stock_main_window.py` | no | - | yes | no | no | - | no | shelved |
| `src/gui/testnet_tab.py` | `testnet_tab.js` | yes | yes | yes | no | yes | no | shelved |
| `src/gui/tradingview_chart.py` | `tradingview_chart.js` | yes | yes | yes | no | yes | no | shelved |
| `src/gui/usb_auth_widget.py` | `usb_auth_widget.js` | yes | yes | yes | no | yes | no | shelved |
| `src/gui/visualizer/bot_node.py` | `bot_node.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/visualizer/quick_routing.py` | `quick_routing.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/visualizer/themes.py` | `visualizer_themes.js` | - | yes | yes | yes | yes | yes | in scope |
| `src/gui/visualizer/wire_canvas.py` | `wire_canvas.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/widgets/__init__.py` | no | - | yes | no | no | - | no | not a screen |
| `src/gui/widgets/api_tester_tab.py` | `api_tester_tab.js` | yes | yes | yes | no | yes | no | shelved |
| `src/gui/widgets/bot_selection.py` | `bot_selection.js` | yes | yes | yes | no | yes | no | not a screen |
| `src/gui/widgets/bot_status_table.py` | `bot_status_table.js` | yes | yes | yes | no | yes | yes | in scope |
| `src/gui/widgets/capital_registry_panel.py` | no | - | no | no | no | - | no | shelved |
| `src/gui/widgets/dashboard_stat_card.py` | `dashboard_stat_card.js` | yes | yes | yes | no | yes | yes | in scope |
| `src/gui/widgets/exchange_tab.py` | `exchange_tab.js` | yes | yes | yes | no | yes | yes | in scope |
| `src/gui/widgets/extractor_bot_table.py` | `extractor_bot_table.js` | yes | yes | yes | no | yes | yes | in scope |
| `src/gui/widgets/notification_spool.py` | `notification_spool.js` | yes | yes | yes | no | yes | no | shelved |
| `src/gui/widgets/privacy_dot.py` | `privacy_dot.js` | yes | yes | yes | no | yes | yes | in scope |
| `src/gui/widgets/pulse_manager.py` | `pulse_manager.js` | yes | yes | yes | no | yes | no | shelved |
| `src/gui/widgets/spendable_profits.py` | `spendable_profits.js` | yes | yes | yes | no | yes | yes | in scope |
| `src/gui/widgets/status_log.py` | `status_log.js` | yes | yes | yes | no | yes | yes | in scope |
| `src/gui/widgets/trade_charts_tab.py` | `trade_charts_tab.js` | yes | yes | yes | yes | yes | yes | in scope |
The Simulator rebuild removed the files above; they are not in the tree.

Totals across the 76 rows above, measured on 5 September 2026:

```
React module             62
Uses React               60
Bridge                   72
Manifest                 62
Registers in Electron    18
Ships in the build       59
RENDERS                  48
RENDERS, in scope        43 of 43
out of scope             37
```

Four columns are all but complete. RENDERS, the column that is the item, is not.

Re-measured on 6 September 2026, counted off the 76 rows above:

```
React module             55
Uses React               53
Bridge                   67
Manifest                 55
Registers in Electron    15
Ships in the build       55
RENDERS                  29
```

Only the last column moved. The Settings row already carried a React module, a
bridge method and a manifest entry; what it gained is the screen.

Re-measured later on 6 September 2026, counted off the same 76 rows:

```
React module             55
Uses React               53
Bridge                   67
Manifest                 55
Registers in Electron    15
Ships in the build       55
RENDERS                  30
RENDERS, in scope        30 of 43
out of scope             33
```

The Create Auto Trader wizard is the row that moved. `bot_wizard.js` draws it
into a space the React exchange screen keeps once + New Bot is pressed, so the
wizard is a screen and no longer a module with nowhere to draw.

Counted once more the same day, after the Live Bot Settings window went over:

```
React module             55
Uses React               53
Bridge                   67
Manifest                 55
Registers in Electron    15
Ships in the build       55
RENDERS                  38
RENDERS, in scope        38 of 43
out of scope             33
```

Eight rows moved together: the window a bot row opens, six of the files its
tabs are built from, and the delegate that draws the fold-tranche row borders.
`fold_tokens.py` keeps its dash. Its colours are on the drawn rows, and the
file names no screen of its own.

When that count was taken the Paper Trader, Proof of Accumulation and System
Status tabs had no Qt module to replace and no React module to replace it with,
so the table carried no row for them. `empty_tabs.py` drew all three empty, and
its own row read `builds the shell`. Issue #19 has since built the Paper tab,
which now has a Qt module and a React module of its own.

In development.

That is no longer the state. Each of the three has a renderer module in
`src/gui/web`, a bridge method and a manifest entry, and `empty_tabs.py`
carries the row for all three. Its Scope cell reads `in scope` and its RENDERS
cell reads `yes`. The section below says what each tab draws.

Counted once more on 6 September 2026, after the header strip and the Start All
dialog went over:

```
React module             58
Uses React               56
Bridge                   69
Manifest                 58
Registers in Electron    15
Ships in the build       58
RENDERS                  42
RENDERS, in scope        42 of 43
out of scope             33
```

Six rows moved. Three are the header strip parts. One is the Start All progress
dialog. One is the Live Bot Settings screen tab, where the React module cell was
the wrong one and now names the module that draws it. The last is the buy
confirmation dialog, which gained a module, a bridge method and a build entry and
still reads `no` under RENDERS.

Counted again on 6 September 2026, after the buy confirmation dialog went over:

```
React module             58
Uses React               56
Bridge                   69
Manifest                 58
Registers in Electron    15
Ships in the build       58
RENDERS                  43
RENDERS, in scope        43 of 43
out of scope             33
```

One row moved. It is the buy confirmation dialog, and it was the last in-scope
row reading `no`. The count comes from `tools/conversion_table.py`, which reads
the cells of the table above.

Counted again on 6 September 2026, after the window's own tab bar went over:

```
React module             59
Uses React               57
Bridge                   69
Manifest                 59
Registers in Electron    15
Ships in the build       58
RENDERS                  44
RENDERS, in scope        44 of 44
out of scope             32
```

One row moved, and it is `main_window.py`. The row read `builds the shell`
because the module filled the tab bar rather than sitting in it; the bar it
fills is now React, so the row is in scope and it renders. `Ships in the build`
stays `no`: the newest bundle under `dist` carries 70 renderer modules and
`main_window.js` is not one of them, because the module is newer than that
build.

Counted again on 6 September 2026, after the three unbuilt tabs went over:

```
React module             60
Uses React               58
Bridge                   70
Manifest                 60
Registers in Electron    16
Ships in the build       58
RENDERS                  45
RENDERS, in scope        45 of 45
out of scope             31
```

One row moved, and it is `empty_tabs.py`. It is the second row that read
`builds the shell`, and it is the only row naming three React modules: the
Paper Trader, System Status and Proof of Accumulation skeletons each have a
renderer module, a bridge method and a manifest entry, and all three register a
panel with the Electron shell. `Ships in the build` reads `no` for the same
reason as the row above: the newest bundle under `dist` carries 70 renderer
modules and these three are not among them.

No row now reads `builds the shell`.

Counted again on 6 September 2026, after the Notifications and Alerts tab went
over:

```
React module             60
Uses React               58
Bridge                   70
Manifest                 60
Registers in Electron    16
Ships in the build       58
RENDERS                  46
RENDERS, in scope        45 of 45
out of scope             31
```

One row moved, and it is `alerts_tab.py`. Its Scope cell still reads `shelved`,
because nothing the running window builds reaches the screen. `variant_surface`
now holds the row under the name `ALERTS`, so the React build makes
`AlertsReactTab` and the Qt build makes `AlertsTab` unchanged. The React tab
draws the whole screen in one web view from `src/gui/web/alerts_tab.js`, and
`AlertsTab.refresh`, `AlertsTab._save_config`, `AlertsTab._test_telegram` and
`AlertsTab._acknowledge_all` are the same methods on both sides.

### The window's own tab bar

The row of tab names across the top of the window is drawn by React under the
React build. `MainWindow._setup_ui` no longer builds a `QTabWidget` by name. It
asks the variant seam for the tab book, so one builder gives the operator the
Qt bar he runs today or the React one.

```python
            self._main_tabs = _main_tab_book_class()()
            self._main_tabs.setMovable(True)
```

Under the Qt build the seam answers with the widget the operator runs today and
nothing changes. Under the React build it answers with a book that keeps that
widget as the stack of pages, hides its own bar, and puts a web view above it.
Every call the window makes is answered over the widget behind the bar, so the
tab order and the pages are the same objects on both sides.

```python
        def addTab(self, widget, label: str) -> int:
            """Add ``widget`` under ``label`` and redraw the bar."""
            index = self._book.addTab(widget, label)
            self._push_tabs()
            return index
```

The bar itself is the Electron shell's navigation, run inside the window. The
page is built from the shell's own scripts, read off disk, and the buttons are
drawn by one React module both sides reach. Neither host holds a bar of its
own, so the two cannot draw a different one.

```python
#: The shell's own navigation, read from ``desktop/renderer`` and inlined.
SHELL_SCRIPTS: tuple[str, ...] = ("panel_host.js", "tab_bar.js")
```

The shell's navigation asks that React module for the buttons and passes it the
tab names, the selected one, and what to do with a press and a drop. It holds
no button of its own.

```javascript
    drawn.renderTabBar(bar, {
      names: found,
      selected: current,
      onSelect: select,
      onMove: onMove
    });
```

A press on a button is reported back to Python, which moves the real tab book
to that tab. Dragging a tab onto another reports the two slots the same way,
and the same handler hands them to the hidden bar, so a drag reorders the pages
as it did before.

```python
            move = request.get("move") or {}
            if "from" in move and "to" in move:
                self._book.tabBar().moveTab(int(move["from"]), int(move["to"]))
```

The menu bar, the window title, the window icon and the status bar are still
Qt. `MainWindow._setup_menu` builds the four menus and `_setup_status_bar`
builds the status line; neither was changed, and every menu action the window
offered before it is on it now.

### The three tabs with nothing behind them yet

Paper Trader, System Status and Proof of Accumulation were named on the tab bar
and were not built when that count was taken. Each one drew a heading, a
sentence saying the tab is not built, and the issue that carries the build-out.
Every word of it came from that tab's own Python surface, so the page invented
nothing. Two of the three are still empty; issue #19 built the Paper tab.

```python
    return {
        "accessible_name": HEADING,
        "built": BUILT,
        "heading": HEADING,
        "issue": ISSUE,
        "issue_text": ISSUE_TEXT,
        "method": METHOD,
        "state_text": STATE_TEXT,
    }
```

Under the Qt build the three sentences are Qt labels, as before. Under the
React build the same view model goes to the tab's renderer module, which draws
it in a web view. The builder asks the variant seam which of the two to make,
and it hands both the same values.

```python
        model = surface.view_model({})
        panel = _empty_tab_class()(model)
```

Neither side holds a colour or a size of its own. `SKIN` names the ground, the
two text colours, the two text sizes, the padding and the gap; the Qt style
sheets are built from it and the page reads it as custom properties.

```python
SKIN = {
    "--empty-tab-ground": ds.SURFACE_0,
    "--empty-tab-heading-colour": ds.TEXT_MAX,
    "--empty-tab-body-colour": ds.TEXT_EMPTY_STATE,
```

The page runs the Electron shell's `panel_host.js`, so the module is drawn the
same way the shell draws it: by name, into one host element, with the reason
written onto the page when it does not draw.

### The header strip

The strip and the five counters above the tab row are no longer built by name.
`HeaderStripMixin._build_header_strip` asks the variant seam for each class, so
one builder draws the Qt widgets or the React pages.

```python
        self._spendable_widget = _spendable_profits_class()()
        top_row.addWidget(self._spendable_widget, stretch=3)

        card_class = _stat_card_class()
        self._stat_scrummed = card_class("Scrummed", "$0.00")
```

The spendable strip is drawn by `SpendableProfitsReact`, which hosts the strip
module in one web view. It answers the two calls the main window makes, and
writes both into the same view model the Qt strip is described by.

```python
        def update_profits(self, data: dict) -> None:
            self._model.update_profits(data)
            self._push()
```

Each column carries a privacy dot drawn by the dot module. A press on one runs
the model in `privacy_dot_surface`, which flips the field in the process privacy
registry and repaints the amount as four stars.

```python
    def clicked(self) -> None:
        self.calls.append(CLICKED)
        try:
            registry = get_privacy_mask_registry()
            registry.set_masked(self._field_id, not registry.is_masked(self._field_id))
        except Exception:
            self.calls.append(TOGGLE_FAILED)
        self.refresh()
```

One card is drawn by `StatCardReact`. A press on the card emits the card's one
signal, and only while the header strip has armed it.

The glyph, the tooltip and the skin of a dot now have one home. Both header
surfaces return what the dot surface paints, so the card and the strip cannot
drift apart.

```python
def privacy_dot(field_id: str, masked: Optional[bool] = None) -> dict:
    painted = privacy_dot_surface.dot_view(field_id, masked)
    return {name: painted[name] for name in _DOT_FIELDS}
```

### The Start All progress dialog

The dialog the Start All button opens is drawn by
`StartAllProgressReactDialog`. It replaces only the method that builds the
controls. The progress handling, the Cancel press and the unsubscribe on close
are the same code the Qt dialog runs.

```python
        def store(self) -> surface.StartAllProgressModel:
            return self._model
```

Every control it needs is a small holder over that store. The list answers
`addItem` and `count`; the buttons answer `setEnabled`. Both build sites, in the
main window and in the launcher, now ask the variant seam for the class.

### The buy confirmation dialog

This is the one in-scope row that still reads `no`, and the reason is
reachability rather than missing work.

The main window builds the broker in this file. Nothing calls the broker's
request method, which is the only sender of the signal that opens the dialog, so
the running window has no path to the screen.

```python
        async def request_confirmation(
            self,
            *,
            bot_id: str,
            symbol: str,
            reason: str,
```

Measured by walking every call in `src` and `main.py`: zero call sites, and no
import of that name under another. The module, the bridge method and the build
entry are all present, so the screen is one caller away.

Re-measured on 6 September 2026, by the same walk over 354 modules: still zero
call sites. That count decides what the operator can reach, and it did not move.
The row's RENDERS cell moved for a different measurement — the class the broker
raises.

The dialog the broker raises is now `BuyConfirmationReactDialog`. The broker
asks the variant seam for that class, so the React build opens the page and
`ACERVATOR_VARIANT=qt` opens the same Qt widgets as before.

```python
def dialog_class() -> type:
    """The confirmation dialog class the running build variant draws."""
    from .variant_surface import BUY_CONFIRMATION, surface_class

    return surface_class(BUY_CONFIRMATION)
```

Every figure the page shows is written in Python. `details_text` in
`buy_confirmation_surface` writes the seven detail rows. The Qt label is set
from it, and the browser draws the same seven lines sliced into their values.
No arithmetic runs in the page.

```python
def after_buy_usd(holdings_before: float, price: float, cost_usd: float) -> float:
    """Dollar value the position reaches once this buy fills."""
    return holdings_usd(holdings_before, price) + cost_usd
```

A press on the page names a button. Python turns that name into an answer and
accepts the dialog through the same `_answer` the Qt buttons call. The page
places no order and decides nothing.

```python
        def run_action(self, name: str) -> bool:
            answer = surface.BUTTON_ANSWERS.get(name)
            if answer is None:
                return False
            self._answer(answer)
            return True
```

A window closed without a press is still `no`. A request nobody answers inside
sixty seconds is refused too.

### The gap

Issue #128 says this item replaces the Qt screens with React. Measured against
that sentence:

```
screens the running window builds     52
screens that draw React                1
screens that draw in the shell only    2
tabs drawn by React                     0
```

The renderer manifest names 70 modules. The application the operator runs hosts
no manifest, and loads exactly one of those modules: the History table's, which
one Qt widget puts on a page of its own. The shell that does host the manifest
draws two panels and offers no way to reach a third.

One call site carries the whole difference between the React build and the Qt
build. `src/gui/history_table_variant.py` holds the only call to the variant
resolver in the tree, and every other tab builds the same Qt widget either way.

`src/gui/history_table_variant.py` — `history_table_class`

```python
chosen = resolve_variant() if variant is None else variant
if chosen == QT:
    from .history_qt_table import HistoryQtTable

    return HistoryQtTable
from .react_history_panel import HistoryWebTable

return HistoryWebTable
```

### Why the count read as near-complete

Two instruments report on this work, and both answer a narrower question than
the item asks.

The progress tool marks a screen paired when a bridge method reaches a renderer
module the manifest names. A manifest entry declares that the shell would load
the file. It does not put a screen in front of the operator.

`tools/conversion_state.py` — `served_methods`, the pairing rule

```python
def served_methods(root: pathlib.Path) -> dict[str, str]:
    """Bridge method to the renderer module that speaks it, loaded ones only.

    A method absent from `registered_surfaces` is left out of the result.
    """
    loaded = renderer_modules(root)
```

The parity tests compare a Qt view model against the React view model of the
same screen. Both sides are plain Python data and neither has to be displayed.
A passing test proves the two descriptions agree with each other. It does not
prove either one is on screen.

`parity_pins` reads only a parity test that imports exactly one surface module
and exactly one Qt module. It collects the names on both sides and pairs them.

`tools/conversion_state.py` — `parity_pins`, what a pin reads

```python
def parity_pins(root: pathlib.Path) -> dict[str, set[str]]:
    qt_by_name = {dotted_name(root, path) for path in qt_modules(root)}
    surfaces = surface_methods(root)
    pins: dict[str, set[str]] = {}
```

Both readings were true. Neither measured the item, and the RENDERS column is
the one that does.

### Not reached from a live tab

These Qt modules are not built by the live window or by any of its tab
builders. They are outside this conversion. One row is a package marker rather
than a screen, and it stays where it is.

| Qt module | Why it is out of scope |
| --------- | ---------------------- |
| `alerts_tab.py` | Not reachable from a live tab |
| `analytics_tab.py` | Not reachable from a live tab |
| `audio_suite.py` | Not reachable from a live tab |
| `competition_tab.py` | Not reachable from a live tab |
| `init_wizard.py` | Not reachable from a live tab |
| `journal_tab.py` | Not reachable from a live tab |
| `launcher.py` | Not reachable from a live tab |
| `live_bot_window.py` | Not reachable from a live tab |
| `risk_tab.py` | Not reachable from a live tab |
| `stock_main_window.py` | Not reachable from a live tab |
| `testnet_tab.py` | Not reachable from a live tab |
| `usb_auth_widget.py` | Not reachable from a live tab |
| `widgets/__init__.py` | Package marker, no screen |
| `widgets/api_tester_tab.py` | Not reachable from a live tab |
| `widgets/capital_registry_panel.py` | Not reachable from a live tab |
| `widgets/notification_spool.py` | Not reachable from a live tab |
| `widgets/pulse_manager.py` | Not reachable from a live tab |

The rows in that table are inside this item. The operator's 6 September 2026
directive puts the whole interface in scope, so a screen the window does not
build is converted like any other. A converted row keeps `shelved` in the Scope
cell of the table above, because that cell answers reachability. Its RENDERS
cell reads `yes` once `variant_surface` holds the row and the React class draws
the screen.

The reachability walk is rooted at the window and its tab builders, and an edge
is a use rather than an import: a call, a base class, or a returned class. An
import alone is not an edge, so the re-export block in the main window leaves a
widget unreached. Ten screens known to be built and eleven known to be dead
were run through the walk as a control, and all twenty-one came back on the
expected side.

Detail on each live screen sits one file down, in
[08-tabs/README.md](08-tabs/README.md).

## 2026-09-09 22:12 - #128 - the Swarm tab loses List View

The Swarm tab no longer offers a choice of view. The grid of locust cards is the
whole screen, and the View picker that used to sit between Theme and Wires is
gone from both builds. The table below carries the row for every file the change
touched; the rows in the table above are the state before it.

| Qt file | React module | Uses React | Bridge | Manifest | Registers in Electron | Ships in the build | RENDERS | Scope |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `src/gui/bot_swarm_list.py` | removed | - | - | - | - | - | - | deleted |
| `src/gui/bot_visualizer.py` | `bot_visualizer.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/visualizer/bot_node.py` | `bot_node.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/visualizer/wire_canvas.py` | `wire_canvas.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/visualizer/growth_stage.py` | shared, no module of its own | - | - | - | - | yes | yes | in scope |
| `src/gui/react_bot_swarm_tab.py` | host for `bot_visualizer.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/theme_engine.py` | `design_tokens.js` | - | yes | yes | yes | yes | yes | in scope |

The Qt widget file went. `BotListView` and `LaneWireCanvas` had one caller, the
Swarm tab, and nothing else built either of them. The live bot settings window
draws its own wire table from `QTableWidget`, so it lost nothing.

`src/gui/bot_swarm_list.py` — what was deleted

```python
class BotListView(QTableWidget):
class LaneWireCanvas(QWidget):
class BotSwarmLaneAllocator:
```

List View is removed whole. The surface `bot_swarm_list_surface.py` and the
module `bot_swarm_list.js` are deleted. The bridge method, the manifest line
and the renderer page's script tag that reached them are gone.

`src/gui/web/bot_swarm_tab.js` — the shell that still names the list globals

```javascript
  var LIST_API = "acervatorSwarmList";
  var LIST_LOADER = "acervatorLoadBotSwarmList";
```

Nothing defines those two globals now. The bot settings shell reads them in
four places and guards every read, so the list region draws nothing and
raises nothing.

`src/gui/react_bot_swarm_tab.py` — `TAB_SCRIPT_ASSETS`, the tail

```python
    "quick_routing.js",
    "bot_visualizer.js",
)
```

One control in `tools/conversion_state.py` named the deleted file. A control
pointed at a file that no longer exists reports `born React` rather than
`paired`, which reads as a pass and proves nothing, so it now names a Qt file
that is still paired.

`tools/conversion_state.py` — `CONTROLS`

```python
CONTROLS = ("bot_visualizer", "theme_engine", "design_tokens")
```

Both builds were opened with the change in place. Qt draws eight main tabs and
React draws ten, the same counts as before, and the Swarm tab in each carries no
View picker, no row list and no lane sheet.

## 2026-09-09 23:05 - #128 - the Electron shell draws the Inspector tab and its proposals pane

The Inspector tab draws in the Electron shell. The shell asks the application
which tabs it builds, matches `market_inspector.state` to the module that serves
it, and gives that module the Inspector tab.

`desktop/renderer/panel_host.js` — `register`

```javascript
    panels[name] = spec;
    dropFault(name);
    kinds[name] = declaredKind(name, spec);
```

The panel host now draws the proposals pane into the right-hand slot, under the
name `market_inspector_topologies.js` registers. The slot used to be filled by a
call straight to the module, so the registration drew nothing and removing it
changed no pixel.

`src/gui/web/market_inspector.js` — `fillSlot`

```javascript
    host.mount(TOPOLOGY_PANEL, slot, null);
```

`desktop/renderer/index.html` links `market_inspector.css`, the stylesheet that
carries the colour, border and type of every part the two modules stamp. The
file shipped and nothing loaded it, so every button on the screen drew in the
browser default. The button rule reads the design token that holds the ground
the theme gives a Qt push button.

`src/gui/web/market_inspector.css` — the button ground

```css
  background: var(--SURFACE_2, var(--btn-bg));
```

One picture item still differs. The Include active markets box is the browser
checkbox, where Qt draws an 18 pixel box with a `#7a7a9c` border on `#0e0e1a`,
and no design-system token carries `#0e0e1a`.

Both screens were driven on one payload of 54 markets, 300 daily candles each
and three ranked proposals. Twenty-six of twenty-seven picture items match, so
rows 878 and 879 read `yes` under Registers in Electron. The run is in
[2026-09-09_market_inspector_register.md](../../tests/debug_reports/2026-09-09_market_inspector_register.md).
