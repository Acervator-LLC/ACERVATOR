# Asset Charts

Reference. One candlestick panel per traded symbol.

## What builds it

The builder mixin makes the tab and adds it to the row. The tab is a scroll
area holding one panel per active bot.

`src/gui/main_tabs/charts_tab.py` — `ChartsTabMixin._build_charts_tab`

```python
def _build_charts_tab(self) -> None:
    """Build the Charts tab and add it to the main tab widget."""
    self._charts_tab = TradeChartsTab()
    self._main_tabs.addTab(self._charts_tab, CHARTS_TAB)
```

Issue #450 renamed the tab from Asset Charts to Charts, and `CHARTS_TAB` holds
that one word.

One method rebuilds that panel set from the current roster.

`src/gui/widgets/trade_charts_tab.py` — `TradeChartsTab.update_charts`

```python
def update_charts(
    self,
    bot_statuses: list[dict],
    bot_manager=None,
    exchange_connectors: dict = None,
) -> None:
    """Create or update chart panels for each bot.
```

Three more methods keep a panel current.

| Method | What it does |
| ------ | ------------ |
| `_on_tf_changed` | Changes one panel's timeframe, leaving the others alone |
| `log_trade` | Adds a fill marker to the panel that owns the symbol |
| `push_synthetic_candles` | Feeds a panel whose venue returned no history |

## The chart widget

`CandlestickChart` in `src/gui/native_chart.py` paints each panel with
QPainter. No browser and no WebEngine dependency.

Four record types carry everything drawn over the candles.

| Record | Draws |
| ------ | ----- |
| `Candle` | One open, high, low, close and volume bar |
| `TradeMarker` | An executed buy or sell |
| `PositionMarker` | A holding, with a distinct icon for invisible and visible |
| `GridLine` | A buy or sell level |

The position record is the one that carries the visibility mode, which is what
tells an invisible holding from one resting on the book.

`src/gui/native_chart.py` — `PositionMarker`

```python
@dataclass
class PositionMarker:
    """Active position shown on chart with visibility mode icon."""

    price: float
    side: str  # "buy" or "sell"
    visibility: str  # "internal" (invisible) or "orderbook" (visible)
    level: int = 0  # Grid level index
    filled: bool = False
    asset_held: float = 0.0
```

The setters name what they place.

| Setter | Places |
| ------ | ------ |
| `set_candles` | The candle series |
| `add_marker` | One executed fill |
| `set_trade_history_markers` | The fills already on record |
| `set_positions` | The holdings, invisible and on book |
| `set_grid_lines` | The buy and sell levels |
| `set_tranche_floors` | The standing fold-tranche floors |
| `set_target_balance_lines` | The dollar target |
| `set_fire_armed_state` | An armed manual fire |
| `set_source_label` | The feed the candles arrived on |
| `set_error` | A failure message in place of the panel body |

The mouse handlers give the panel a crosshair with a price and time readout,
drag panning and a wheel zoom bounded by `_effective_visible_start` and
`_effective_visible_count`.

## Indicators on the chart

The chart calls the engine rather than computing anything of its own. Five
series arrive that way, and an entry with no value is skipped when the panel
paints.

`src/gui/native_chart.py` — `CandlestickChart._compute_indicators`

```python
def _compute_indicators(self):
    """Fill ``_bb_data``, ``_vortex_data``, ``_macd_data``,
    ``_stochrsi_data`` and ``_ichimoku_data`` from the engine
    classes. A ``None`` entry marks a candle with no value, and
    ``paintEvent`` skips it.
    """
```

The toolbar under each panel holds the timeframe picker and eight toggles.

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

Volume starts on and the other seven start off.

`src/gui/main_tabs/native_chart_surface.py` — `INDICATOR_DEFAULTS`

```python
INDICATOR_DEFAULTS = {
    "bb": False,
    "vortex": False,
    "macd": False,
    "stochrsi": False,
    "ichimoku": False,
    "volume": True,
    "slingshot": False,
    "bbullseye": False,
}
```

Sling and BBull paint a placeholder shape rather than the indicator, and each
says as much in its own tooltip. Issue #430 carries one further disagreement
between a tooltip on this toolbar and what the chart paints.

The complete voter set and the maths behind each indicator belong to
[the Indicator Voting Panel](../07-indicators.md).

## Where the candles come from

Three sources in order: the connected exchange first, a public API second, and
the last successful fetch third. Each source that fails is recorded and the
next one runs.

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

With every source exhausted the fetcher returns an empty list and a label
naming what failed, and the panel draws that label rather than an empty grid.

`src/exchange/chart_data.py` — `ChartDataFetcher.fetch`

```python
# All sources failed
error_detail = " | ".join(errors) if errors else "No sources available"
```

Each row arrives as an `OHLCVCandle`.

## The other chart

`src/gui/tradingview_chart.py` holds the QWebEngineView chart, which runs HTML
and JavaScript inside the Chromium that PySide6 already ships. The Asset Charts
tab does not use it; the panels above are painted natively. Its one
construction site is the stock window, and the application builds no stock
window, so no screen draws it today.

`src/gui/stock_main_window.py` — the one construction site

```python
from .tradingview_chart import TradingViewChart

self._chart = TradingViewChart(symbol="AAPL", theme="dark")
```

## Bridge

Three methods serve this screen.

| Bridge method | Renderer module |
| ------------- | --------------- |
| `native_chart.state` | `native_chart.js` |
| `trade_charts_tab.state` | `trade_charts_tab.js` |
| `tradingview.chart` | `tradingview_chart.js` |

## 2026-09-08 13:30 - #407 - a Live / ATA-SMP toggle over the arrows

The tab now walks two lists of markets. Live is the markets the bots are
trading. ATA-SMP is the markets the TA engine has called and queued. One
selector serves both: the arrows, the ticker menu and the readout all follow
whichever list the toggle names.

The toggle is a button on its own row, above the blue arrows and the ticker
menu. It reads the list on screen, so the button says Live while the Live list
is up and ATA-SMP while the called markets are up.

`src/gui/main_tabs/trade_charts_tab_surface.py` — the two lists and their words

```python
LIST_LIVE = "live"
LIST_ATA = "ata_smp"
LIST_MODES = (LIST_LIVE, LIST_ATA)
LIST_LIVE_TEXT = "Live"
LIST_ATA_TEXT = "ATA-SMP"
```

Pressing the toggle swaps the list, points the chart at that list's own
selected market, and writes its header. Each list remembers where it was, so
coming back to Live returns to the asset that was on screen.

`src/gui/main_tabs/trade_charts_tab_surface.py` — pressing the toggle

```python
def toggle_list(self) -> str:
    """Move the arrows to the other list and answer the mode on screen."""
    self.list_mode = LIST_ATA if self.list_mode == LIST_LIVE else LIST_LIVE
    self.calls.append([SELECT_LIST_TOGGLED, self.list_mode, len(self.list_order())])
    self._follow_shown()
    self._label_shown()
    self._feed_shown()
    return self.list_mode
```

A market joins the ATA-SMP list when it reaches the Ready to Send bucket. It
does not have to be posted. A call that is queued and then declined is still
tracked, because the trigger is the bucket rather than the delivery.

The tab holds no register of its own. It reads the markets through a callable
the Market Inspector hands it, so the list the operator walks and the calls
phase seven is watching are one set of markets read twice.

`src/gui/main_tabs/market_inspector_tab.py` — where the two are joined

```python
def _wire_ata_chart_list(self, inspector: Any) -> None:
    """Point the Charts tab's ATA-SMP list at ``inspector``'s ``PushBoard``.

    The Charts tab is built first, so it reads the board through a
    callable instead of holding a second copy of the markets.
    """
```

No entry is ever invented. With nothing bound, or with an empty bucket, the
ticker offers one line reading No called market, the readout says 0 of 0, the
arrows go grey, and a note beside the toggle says what the list is waiting for.

`src/gui/main_tabs/trade_charts_tab_surface.py` — the empty state's own words

```python
ATA_EMPTY_TICKER_TEXT = "No called market"
ATA_EMPTY_HINT = "A market joins this list when it reaches Ready to Send."
```

An ATA-SMP market has no bot behind it, so the chart draws its candles without
the trade markers, the target lines, the tranche floors and the fire glow that a
traded asset carries. Nuclear Mode returns the tab to the Live list before it
draws, because a Nuclear scenario belongs to a bot.

**Figures.** This page carries no figure. The screen changed on this date and no
capture of the toggle row exists yet, so the paragraphs above are the only
record of it.

## 2026-09-08 13:30 - #407 - the arrows now reach the renderer

The React half of this tab drew the arrows and the ticker menu, and pressing
either one changed nothing. The buttons called the bridge with the step it
wanted, and the handler read every other request field and dropped that one, so
the answer that came back was the state the tab was already in.

`src/gui/main_tabs/trade_charts_tab_surface.py` — the three the handler now reads

```python
        params.get("step_by"),
        params.get("pick_at"),
        params.get("toggle_list", False),
```

The same tab also refused to draw at all under the renderer. One of its own
checks read a name the file never declared, which stopped the whole payload
before a single row was placed. The check now compares the number of rows the
Python side declares against the number the renderer draws, which is the
disagreement it was written to catch.

`src/gui/web/trade_charts_tab.js` — the check, repaired

```javascript
  // The surface and this module must name the same number of tab rows.
  function checkSlots(model) {
    var content = objectField(model, CONTENT);
    if (!owns(content, LAYOUT_SLOTS)) {
      return;
    }
    if (content[LAYOUT_SLOTS] !== LAYOUT_SLOT_COUNT) {
      chartFaults.push(
        fault(CONTENT, LAYOUT_SLOTS, DISAGREES_FAULT, LAYOUT_SLOT_COUNT)
      );
    }
  }
```

## 2026-09-13 15:40 - #23 - the Charts tab draws in the desktop window

The tab draws under the window the operator launches. `ChartsTabReact` in
`src/gui/react_charts_tab.py` builds one web view and loads one page. The page
carries every script and every rule inside it, so it fetches nothing.

`src/gui/react_charts_tab.py` — the modules the page carries, in load order

```python
def roster() -> tuple[str, ...]:
    """Every module the page carries, in load order.

    ``STYLE_SOURCE_ASSETS`` leads: ``trade_charts_tab.js`` reads a payload
    colour back to its token through ``shared_widgets.variableFor``.
    """
    return STYLE_SOURCE_ASSETS + CHILD_MODULES + (PANEL_MODULE,)
```

`trade_charts_tab.js` draws the tab. `native_chart.js` draws the candles into
the slot that module keeps. Both register with the shell's own panel host, so
the page in the window and the page in the shell run the same two modules.

The page reaches the model over one console channel. Each ask leaves the page as
a line under `ASK_PREFIX`, and `ChartsTabPage` hands that line to `run_ask`. The
answer returns by the ask's own number. The arrows, the ticker menu and the TF
picker each move the asset the window holds.

`src/gui/react_charts_tab.py` — the call the dashboard pass makes

```python
        def update_charts(
            self,
            bot_statuses: list,
            bot_manager=None,
            exchange_connectors: Optional[dict] = None,
        ) -> None:
            """Rebuild the asset list for one pass of bot statuses and redraw."""
            self._model.update_charts(bot_statuses, bot_manager, exchange_connectors)
            self.redraw()
```

`fetch_chart_data` refetches the asset on screen. `set_ata_source` takes the
callable behind the ATA-SMP list. Both answer the calls the main window and the
Market Inspector tab already make on the Qt tab.

### The tab's own style sheet

`src/gui/web/trade_charts_tab.css` paints the chrome around the chart. It holds
no colour of its own. Every rule names a design token, and `design_tokens.js`
writes each token onto the page as a CSS variable.

`src/gui/web/trade_charts_tab.css` — the arrows and the list toggle

```css
[data-part="asset-prev"],
[data-part="asset-next"],
[data-part="chart-list-toggle"] {
  background: var(--SURFACE_CONTROL, var(--btn-bg));
  color: var(--PRIMARY, var(--accent));
  border: 1px solid var(--GLOW_PRIMARY_EDGE, var(--border));
  border-radius: 4px;
  font-family: inherit;
  font-size: 12px;
  font-weight: bold;
  cursor: pointer;
}
```

An arrow with one asset to walk goes grey. The panel takes a border and a
rounded ground. The header line, the toolbar and the toggle row each take a rule
between them. The readout beside the arrows and the empty-list hint take the low
text colour at ten pixels.

### The chart keeps a host of its own

`native_chart.js` opens a React root of its own. It draws into `chart-host`, a
child element the tab declares and never fills. One element under two roots lost
the whole tab the moment the waiting line cleared.

`src/gui/web/trade_charts_tab.js` — the slot the chart draws into

```javascript
    var hostProps = { key: CHART_HOST_PART, style: { flex: AUTO, overflow: HIDDEN } };
    hostProps[PART_ATTR] = CHART_HOST_PART;
    hostProps[BOT_ATTR] = text(props.botId);
```

A missing chart module says so on the slot. `renderChartMounts` asks the panel
host to mount the slot with no model, and the host writes the reason it refused
where the candles belong.

The tab redraws when its width changes. `resizeEvent` re-arms a short timer, and
the timer pushes the payload again. The chart then takes the width the tab has.

### What the page draws

The page draws the Live toggle, the two arrows, the ticker menu and the readout
saying which asset of how many. Under them one panel header names the symbol,
the price and the bot state. The chart draws the candles, the Bollinger cloud,
the Ichimoku cloud, the last price on the right axis, the volume strip and the
Vortex, MACD and Stochastic RSI panes. Eight indicator switches close the panel,
with Sling and BBull off.

The legend beside the feed name carries its own colour. `native_chart_surface`
holds the two Qt style sheets for it, and the tab surface sends them as
`legend_styles`.

Back to [the subsystem index](README.md).
