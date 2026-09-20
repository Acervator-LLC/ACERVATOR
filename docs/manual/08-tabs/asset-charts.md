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

### Where the chart draws

The Charts tab host mounts the chart module inside itself. The tab draws in the
window the operator launches, not only in the shell. `CHILD_MODULES` in
`react_charts_tab.py` names the one module the tab slot takes.

```
modules the page registered   header_strip, native_chart, trade_charts_tab
panel faults                  none
drawn from forty candles      40 candles, 40 wicks, 40 volume bars
indicator panes               Vortex, MACD, Stochastic RSI
```

With the chart module absent the page still draws its own chrome, and the panel
host records the loss rather than drawing an empty slot.

```
native_chart.js registered no panel to draw
```

## 2026-09-15 10:38 - #55 - one painter draws the chart in both builds

The chart area of the Charts tab is the image one painter paints, in both
builds. The Qt build's chart widget already painted through that routine; the
React build now shows the same image where its own drawing used to be. The
ATA-SPM post images come from the same routine, so one chart looks one way in
the Qt tab, in the React tab and in a post.

`src/gui/native_chart.py` — the routine both builds and ATA-SPM paint through

```python
    def paint_image(
        painter: ChartPainter,
        width_px: int,
        height_px: int,
        device_pixel_ratio: float = 1.0,
    ) -> QImage:
        ratio = float(device_pixel_ratio) if float(device_pixel_ratio) > 0 else 1.0
        image = QImage(
            int(round(int(width_px) * ratio)),
            int(round(int(height_px) * ratio)),
            QImage.Format_ARGB32,
        )
        image.setDevicePixelRatio(ratio)
        image.fill(painter.BG_TOP)
        image_painter = QPainter(image)
        painter.paint_to(image_painter, int(width_px), int(height_px))
        image_painter.end()
        return image
```

Fed the same hundred candles, the same label and the same six overlays, the
three agree byte for byte at 1200 pixels wide: the Qt widget, the React image
and the ATA-SPM image all read `d8932829dcf760c1`. A planted change to one
candle's close moves the Qt widget and the React image to the same new digest,
`4dbcb29e360c363e`, so the agreement is a reading and not an artefact. The
ATA-SPM image for its own inputs is unchanged by this work.

### How the React page gets the image

The tab holds one painter beside its model. Each time the page draws, the chart
slot asks the tab for the image at the slot's own width and height and at the
page's device pixel ratio. The tab feeds the painter what the panel holds and
answers a PNG as a data URI, which the slot shows as one image element.

`src/gui/react_charts_tab.py` — what the painter is fed, as the Qt tab feeds its chart

```python
        def _feed_painter(self) -> None:
            """Give ``painter`` what ``PanelSink`` holds, as the Qt tab gives its chart."""
            panel = self._model.panel
            painter = self._painter
            painter.symbol = str(panel.label)
            painter.set_timeframe(str(panel.chart_timeframe or panel.timeframe))
            painter.set_candles(
```

The image carries the display's pixels. At a device pixel ratio of 1.25 the
page asked for 1201 by 731 CSS pixels and received a 1501 by 914 pixel image;
at 2x, 600 by 492 CSS pixels received 1200 by 984. In the header band the 2x
image holds 395 distinct colours where the 1x image scaled up holds 305, and
the thinnest vertical run in the price pane is one device pixel where the
scaled 1x image needs two.

The page no longer carries `native_chart.js`. The tab's list of child modules
is empty, the page registers two modules, and the file stays in the tree
unmounted.

`src/gui/react_charts_tab.py` — the modules the chart slot mounts

```python
CHILD_MODULES: tuple[str, ...] = ()
```

### The eight toggles reach the painter

Each check box under the chart now asks the tab to switch that overlay on the
painter, and reads the painter's own state back off the answer. The Qt build's
boxes drive the same switch on the same painter.

`src/gui/web/trade_charts_tab.js` — a click on one box

```javascript
  function overlayChosen(key, on) {
    if (!global.acervator || typeof global.acervator.call !== "function") {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    var params = {};
    params[TOGGLE_KEY_PARAM] = key;
    params[TOGGLE_ON_PARAM] = Boolean(on);
    return global.acervator
      .call(METHOD, params)
```

Each of the eight, flipped from its starting state, moves the image to a new
digest in both builds, and the two builds' digests agree on every flip; flipped
back, each returns to the starting digest. A toggle left alone answers the last
image with no repaint. The starting states are six on and two off: BB, Vortex,
MACD, SRsi, Ichi and Vol on; Sling and BBull off.

### What a repaint costs

The tab answers the last image again when nothing it reads has changed. When
something has, the painter repaints and the PNG is encoded on the window's own
thread. Measured ten runs each, six overlays on, one hundred candles:

| width x height | ratio | image | paint | PNG + base64 |
| --- | --- | --- | --- | --- |
| 1200 x 492 | 1x | 1200x492 | 7.6 ms | 21.6 ms |
| 1920 x 492 | 1x | 1920x492 | 9.0 ms | 31.5 ms |
| 1200 x 492 | 2x | 2400x984 | 18.0 ms | 76.9 ms |
| 1920 x 492 | 2x | 3840x984 | 22.1 ms | 112.9 ms |

The dashboard pass calls `update_charts` every two seconds, and the header
label carries the price, so a moving price repaints on most passes. Candles
refetch at most every 30 seconds.

### Live candles reach the React chart

The React tab's fetch handed the fetcher's rows to `list`, and the fetcher's
row type is not iterable, so every live fetch ended in an error line and no
candles. The rows now pass through `candle_row`, which reads an object, a dict
or a six-number row.

`src/gui/main_tabs/trade_charts_tab_surface.py` — the fetch, repaired

```python
            if rows:
                self.panel.set_candles([candle_row(one) for one in rows])
                self.panel.set_source(answered)
```

**Figures.** `artifacts/issue-55/` holds the Qt tab, the React tab and the
ATA-SPM image before and after, for the same hundred candles. The React page
draws the tab header line and the painter draws its own header line under it,
so the label reads twice on that build.

## 2026-09-19 08:23 - #55 - every Voting Panel indicator on the chart

His words, 2026-08-21: *"Asset Charts Tab - Restructure - Must now display
only one chart at a time with all indicators from the Indicator Voting Panel
loaded and properly visualized."* And 2026-09-08: *"Want charts tab to only
display one richly detailed and Acervator-annonated chart at a time with all
Indicators visible by default excluding that might visually oclude BB or ICHI
as Sling or Z-Score Algo Point. All indicators will need toggle check boxes at
the bottom."*

### The five series the indicator classes now answer

ADX, Supertrend, Z-Score, KER and RSI each gain one method beside their vote,
named as the Vortex and Ichimoku classes name theirs. The vote reads that
method, so the line on the chart and the vote in the Voting Panel are one
arithmetic.

`src/trading/indicators/adx.py` - the series and the vote reading it

```python
    def lines(self, candles: list) -> tuple[_Line, _Line, _Line]:
        """+DI, -DI and ADX, one entry per candle, for a chart to draw.
```

```python
        di_plus_series, di_minus_series, adx_series = self.lines(candles)
```

| class | `lines` answers, one entry per candle |
| ----- | ------------------------------------- |
| `ADXIndicator` | +DI, -DI and ADX |
| `SupertrendIndicator` | the line, its side and the ATR under it |
| `ZScoreIndicator` | a `ZScoreBar`: the smoothed score, the two projected prices and the window figures |
| `KaufmanERIndicator` | the ratio |
| `RSIIndicator` | Wilder's RSI |
| `SlingshotIndicator` | a `SlingshotBar`: the squeeze state, the release, the snapback and the momentum |

The vote is unchanged. `compute` from the commit before and `compute` from
this one ran over every prefix of 600 recorded BTC 1h candles, six classes,
every Signal field compared: 0 of 600 prefixes differ for any class. The
control: shifting one class's series by one candle makes the same comparison
report 549 to 589 differing prefixes.

### Fourteen overlays, seven sub-panes

The overlay registry now holds the twelve Voting Panel indicators in the
panel's own order, then the two overlays that draw no voter: the Z-Score
algo point and BB Bullseye.

`src/gui/native_chart.py` - one of the six new entries

```python
    ChartOverlay(
        key="adx",
        label="ADX",
        colour_field="chart_last_price",
        pane=SUB_PANE,
        occludes=False,
        draw="_draw_adx",
        tooltip="ADX (14) with +DI and -DI, 0..100, 20 and 25 ruled, sub-pane",
        voter="adx",
    ),
```

| overlay | pane | what it paints | ruled |
| ------- | ---- | -------------- | ----- |
| ADX | sub-pane | +DI, -DI and ADX on 0..100 | 20 and 25 |
| STrd | price pane | the Supertrend line, green under price while bullish, red over it while bearish | |
| ZSc | sub-pane | the smoothed score on a symmetric scale of at least 3 | +2 and -2 |
| KER | sub-pane | the Efficiency Ratio on 0..1 | |
| RSI | sub-pane | Wilder's RSI on 0..100 | 30 and 70 |
| ZPt | price pane | the resistance and support prices the averaged reversals project, dashed | |

Slingshot now draws the indicator's own marks. Before, the painter re-derived
a bandwidth squeeze of its own and drew marks the indicator never fired; now
each diamond is a bar the class read as a squeeze release, signed by its
momentum, and each circle a bar it read as a Bollinger snapback.

`src/gui/native_chart.py` - the slingshot marks

```python
                if bar.released and bar.momentum != 0.0:
                    marks.append(("release", bar.momentum > 0.0))
                if bar.snapback:
                    marks.append(("snapback", "bull" in bar.snapback))
```

The sub-panes sit under the volume strip in registry order: Vortex, MACD,
Stoch RSI, ADX, Z-Score, KER, RSI. Each takes 60 px at the chart's natural
height. When the window gives less, every sub-pane shrinks alike, down to
28 px, so the price pane keeps its 220 px and every pane stays on screen.

`src/gui/native_chart.py` - the pane heights

```python
SUB_PANE_H = 60
SUB_PANE_MIN_H = 28
PRICE_PANE_LAYOUT_H = 220
PRICE_PANE_MIN_H = 120
```

### The legend

A band under the OHLC row names every overlay with the last candle's value of
its series, in the overlay's colour. An overlay that is off reads `off` in
grey. The band wraps to the chart's width. It is painted by the painter, so
the Qt widget, the React image and the ATA-SPM post images all carry it.

`src/gui/native_chart.py` - what one legend entry carries

```python
                found.append(
                    {
                        "key": overlay.key,
                        "label": overlay.label,
                        "text": text,
                        "colour": self.overlay_colour(overlay).name(),
                        "on": on,
                        "has_value": value is not None,
                    }
                )
```

### Fourteen toggles

The toggle row under the chart holds one box per overlay, in the same order.
The three occluders start off: Sling, ZPt and BBull, each a mark or a fill
over the price pane. Every other indicator starts on.

`src/gui/main_tabs/native_chart_surface.py` - the occluders

```python
INDICATOR_OCCLUDES = {
    "bb": False,
    "vortex": False,
    "macd": False,
    "stochrsi": False,
    "ichimoku": False,
    "volume": False,
    "slingshot": True,
    "adx": False,
    "supertrend": False,
    "zscore": False,
    "ker": False,
    "rsi": False,
    "zscore_point": True,
    "bbullseye": True,
}
```

Both hosts flip an overlay through one method on the painter. The Qt check
box calls it, and the React box asks the tab, which calls it.

`src/gui/native_chart.py` - the Qt press

```python
            self._chart.set_overlay(name, on)
```

### The two emitters

`charts.indicator.toggled` is written once per press, with the key, the state
asked and the variant; `ok` is true when the painter's state after the press
is the state asked. `charts.indicators.drawn` is written once the candles
arrive and the series recompute, with the symbol, the timeframe, the keys
shown and each one's legend value; `ok` is true when every shown overlay
holds a value on the last candle. Both go through the emitter network's one
wire and nothing else.

`src/gui/native_chart.py` - the two names

```python
TOGGLED_PIN = "charts.indicator.toggled"

DRAWN_PIN = "charts.indicators.drawn"
```

### Read off the running program

The real window in each build, the home on a scratch directory, every socket
but loopback refused, a two-bot fleet read off a copy of the operator's
`bot_state.json`, and the real fetcher fed 100 recorded BTC 1h candles by a
stand-in connector:

| reading | Qt | React |
| ------- | -- | ----- |
| toggles under the chart, in order | 14: BB, Vortex, MACD, SRsi, Ichi, Vol, Sling, ADX, STrd, ZSc, KER, RSI, ZPt, BBull | the same 14 on the page |
| starting states | 11 on, Sling, ZPt and BBull off | the same |
| legend entries | 14, 11 with a value, 3 reading `off` | the same 14 in the image answer |
| ADX on the last candle, by hand and on the painter | 20.16, +DI 10.91, -DI 40.24 | the same |
| Supertrend | 63,003.61, bearish | the same |
| Z-Score | -1.24 | the same |
| KER | 0.7617 | the same |
| RSI | 25.44 | the same |
| each new toggle pressed off then on | the line gone and back, the image digest moved and returned, one emitter record per press | the same through the page's box |
| sub-pane rules | RSI 30 and 70, ADX 20 and 25, Z-Score +2 and -2: 692 to 727 pixels on each ruled row differ from a repaint with no rules, 0 on the row above and 0 on a control row | the same |
| `bot_state.json` after every press | byte-identical | byte-identical |
| the planted legend value | the legend reads 99.99 where the series reads 25.44, and the comparison reports it | the same |

The two builds paint one image: the painter's image for the same candles
reads one digest in both.

### Sentences this entry overtakes

They were not reworded. They are quoted here.

`docs/manual/08-tabs/asset-charts.md:97` - "The chart calls the engine rather
than computing anything of its own. Five series arrive that way, and an entry
with no value is skipped when the panel paints." Fourteen series arrive that
way now.

`docs/manual/08-tabs/asset-charts.md:112` - "The toolbar under each panel
holds the timeframe picker and eight toggles." Fourteen toggles.

`docs/manual/08-tabs/asset-charts.md:128` - "Volume starts on and the other
seven start off." Eleven start on and three start off.

`docs/manual/08-tabs/asset-charts.md:146` - "Sling and BBull paint a
placeholder shape rather than the indicator, and each says as much in its own
tooltip." Both paint the indicator, and neither tooltip says placeholder.

`docs/manual/08-tabs/asset-charts.md:552` - "The starting states are six on
and two off: BB, Vortex, MACD, SRsi, Ichi and Vol on; Sling and BBull off."
Eleven on and three off.

**Figures.** `artifacts/u55/C2/` holds the Qt window and the React page at
1400 by 900 and at 1960 by 1200, the painter's image, and one venue PNG,
before and after.

## 2026-09-19 17:40 - #55 - the painter's skin and the Acervator annotations

His words, 2026-08-21: *"Charts did get a slight visual over all during the
last past some instances ago but I am still not completely satisfied."* And
2026-09-08: *"I want our chart renderer to be top notch. I want to be able to
add modern features and graphics and styling to it so that we can help asset
trading migrate away from the pastel and bland."*

### Every colour is a theme token

The painter holds no colour of its own. Each colour it paints is one role in
its palette table, and each role names a theme field and an alpha. A theme
press on the Theme menu now reaches the painter in both builds: the window's
theme switch calls the Charts tab, the tab calls the painter, and the painter
resolves every role again. The toggle boxes under the chart and the two
position labels above it read their colours from the painter, so they follow
the press too. The toggle table in the chart's surface carries a theme field
name per entry, not a hex string. A theme that lacks a field keeps the default
theme's value for that role and the emitter row names how many roles it did
resolve.

`src/gui/native_chart.py` - the roles added this day

```python
        PALETTE_ROLES: dict[str, tuple[str, int]] = {
            "PANEL_SOURCE_TEXT": (PANEL_SOURCE_FIELD, 255),
            "TAG_TEXT": ("chart_bg_top", 255),
            "STRIP_FILL": ("chart_band", 40),
            "STRIP_EDGE": ("chart_band", 210),
            "FILL_TAG_SURFACE": ("chart_bg_top", 215),
```

`src/gui/main_window.py` - the one line the theme switch gained

```python
                self._charts_tab.set_theme(tm.current)
```

At build the painter starts in the theme the window is in, and the venue image
paints in that theme too when its caller names none.

`src/gui/native_chart.py` - the theme in force

```python
    def theme_in_force():
        """The ``ThemeTokens`` ``ThemeManager.apply_theme`` last painted."""
        return THEMES.get(applied_theme(), DEFAULT_THEME_TOKENS)
```

### Crisp at every device pixel ratio

The paint pass reads the device pixel ratio of the surface it paints and holds
one device pixel as a logical length. The grid, the time ticks and the pane
separators draw with anti-aliasing off, one device pixel wide, on coordinates
moved to the centre of a device pixel. The wick is a share of one candle column
and never under one device pixel; the candle border is one device pixel; the
indicator lines keep their logical width and stay anti-aliased. Read on a
1200 pixel image at ratio 1.0 the pens are 0.8, 1.0, 1.2, 1.4, 1.5 and 1.56
logical pixels; at ratio 2.0 the set gains 0.5, the one-device-pixel pen.

`src/gui/native_chart.py` - the device pixel and the snap

```python
            ratio = self._device_ratio(p)
            px = 1.0 / ratio

            def snap(value: float) -> float:
                """``value`` moved to the centre of the device pixel it falls in."""
                return (int(value * ratio) + 0.5) / ratio
```

### The type

The header symbol is set in the design system's UI family at the card-title
size, the OHLC row in the mono family at the label size, and the legend, the
axes, the tags and the caption in the mono family at the caption size. The
legend wraps at the chart's width as before; at 1400, 1366 and 1200 pixels it
takes two rows and its widest row ends before the price scale.

`src/gui/native_chart.py` - the fonts

```python
    def caption_font() -> QFont:
        """The mono font the legend, the axes, the tags and the caption are set in."""
        return design_font(ds.FONT_FAMILY_MONO, CAPTION_FONT_PX)

    def header_font() -> QFont:
        """The UI font the header symbol is set in."""
        return design_font(ds.FONT_FAMILY_UI, HEADER_FONT_PX, bold=True)
```

### Every fill as the two glyphs

A fill is drawn as one of the two hermetic glyphs the Simulator's playback
draws, from one definition both read: a sell as `dissolve`, a triangle pointing
down as an outline, and a buy as `reform`, a triangle pointing up filled. The
definition moved from the Simulator's surface to the chart's surface, and the
Simulator imports it from there. The glyph sits on the candle whose interval
holds the fill's stamp, one candle column wide and a twentieth of the price
pane tall, with a tag naming the role and the price beside it. A fill whose
stamp falls before the window or past its end is counted and not drawn.

`src/gui/main_tabs/native_chart_surface.py` - the one definition

```python
MARK_GLYPHS = {
    SCRUM_SIDE: {
        "name": DISSOLVE_GLYPH,
        "points": [[-0.5, -0.5], [0.5, -0.5], [0.0, 0.5]],
        "filled": False,
    },
    FOLD_SIDE: {
        "name": REFORM_GLYPH,
        "points": [[-0.5, 0.5], [0.5, 0.5], [0.0, -0.5]],
        "filled": True,
    },
}
```

The fills come from two figures of the bot. Each tab subscribes to the bus
topic every fill crosses and records it, so a fill made after launch draws on
the next status tick. And each standing fold tranche the bot holds was made at
a scrum: its reference price is that sell and its stamp is that sell's time,
so the tab draws each one as a scrum glyph. Before this day nothing called the
tab's trade recorder, so no fill had ever reached the chart.

`src/gui/widgets/trade_charts_tab.py` - the subscription and the handler

```python
            get_event_bus().subscribe(FILLED_TOPIC, self._on_trade_filled)
```

```python
        def _on_trade_filled(self, event) -> None:
            """Record one ``trade.filled`` bus event through ``log_trade``.

            The next ``update_charts`` tick draws it as a glyph on its candle.
            """
```

### The target, the floors, the strip, the glow and the position

Each annotation carries a tag at the right edge, a badge filled in the line's
colour with the theme's ground colour for text. The target line and the
ceiling line read `TARGET` and `CEILING` with their prices. Each tranche
floor keeps its dashed line; floors whose tags would overlap share one tag
naming their count and their price span, so 16 floors in one pane read as
seven tags. The landing strip is a band between the side's Bollinger band and
its tolerance edge, over the strip's candles at the bot's own timeframe,
tagged with the side and the count; it draws from the bot's own proximity
reading. The fire glow keeps its gradient and gains `SCRUM ARMED` or
`FOLD ARMED`. The position is the venue's average entry with the units held,
drawn as its line, its icon and a `POSITION` tag.

`src/gui/native_chart.py` - the strip's bounds

```python
        def _strip_bounds(self) -> Optional[tuple]:
            """The landing strip's two prices, ``(top, bottom)``, or None with no strip set.

            The band lies between the side's Bollinger band and its tolerance
            edge, ``(upper - lower) * tolerance_pct / 100`` inside it.
            """
```

`src/gui/main_tabs/trade_charts_tab_surface.py` - the readers both tabs share

```python
def landing_strip(bb: Any, timeframe: Any = "") -> Optional[dict]:
```

```python
def position_reading(bot: Any) -> Optional[dict]:
```

```python
def tranche_scrums(tranches: Any, bot_id: Any, symbol: Any) -> list:
```

### The theme and annotation emitters

`charts.theme.applied` is written once per theme applied, with the theme, the
variant and the symbol; `ok` is true when every palette role resolved from
that theme. `charts.annotations.drawn` is written when the set of annotations
the paint pass drew changes, with the counts drawn against the counts fed that
fall inside the pane, and the fills fed and the fills off the window in its
context. Both go through the emitter network's one wire.

`src/gui/native_chart.py` - the two names

```python
THEME_PIN = "charts.theme.applied"

ANNOTATIONS_PIN = "charts.annotations.drawn"
```

### The skin readings, off the running program

Both builds, the real window, the home on a scratch directory, every socket
but loopback refused, one BTC/USD bot's figures off a scratch copy of the
operator's fleet file, and 100 recorded BTC 1h candles rolled from the 5m
tablet by the registry's own rollup:

| reading | Qt | React |
| ------- | -- | ----- |
| each of the five Theme menu entries pressed | 79 of 79 roles move on the four non-default themes, 0 on the default; the toggle boxes and the two labels restyle | the same 79; the image digest moves on each press and the page's boxes recolour |
| literal colours in the painter and its surface | 3 and 17 before, 0 and 0 after; a literal planted into one draw call reads 1 | the same files |
| two fills handed to the tab's handler, one live-shaped fill on the bus, three standing scrums off the record | 6 fills fed, 2 drawn as triangles on candles 60 and 80 of 100, 4 off the window and counted | the same 6, the same 2 triangles at the same vertices |
| the glyph corners against the Simulator's | one object, `MARK_GLYPHS` | the same object |
| 55 floors off the record | 55 lines fed, 16 inside the pane, 7 tags | the same |
| the target and ceiling prices | equal to the anchor and the cycle ceiling over the units held and the quote rate; outside the pane on these candles | the same |
| the position | the venue's average entry off the record, one `POSITION` tag | the same |
| the strip | the bot's own detector reads none on any window of this tablet; a chosen 3-candle upper strip draws its band between the detector's own band and tolerance edge, tagged `STRIP upper 3c` | the same |
| the glow | `SCRUM ARMED` tagged | the same |
| pens at ratio 1.0 and 2.0 | 0.8 to 1.56 logical, then 0.5 joins at 2.0; anti-aliasing off eight times for the grid and the separators, on again after each | the same |
| a theme with one role | no crash; that role takes the planted colour, every other keeps the default, the emitter row reads 5 of 79 and false | the same |
| the legend at 1400, 1366 and 1200 | two rows, none clipped | the same |
| `charts.theme.applied` | 7 rows, 79 of 79 on each | 7 rows |
| `charts.annotations.drawn` | 2 rows, drawn equal to fed inside the pane | 2 rows |
| `bot_state.json` after every press | byte-identical; a copy with one byte appended reads a different digest | the same |
| the venue image under Neon Light and Cyberpunk Dark | the top-left pixel equals each theme's ground and the foot pixel its lower ground; the two files differ; the message stamp is drawn in the theme's own axis text colour | one painter |

### Two sentences this entry overtakes

They were not reworded. They are quoted here.

`docs/manual/08-tabs/asset-charts.md:76` - "The setters name what they
place." The table under it lacks `set_landing_strip`, which places the
landing strip band.

`docs/manual/08-tabs/simulator.md:8634` - "One definition, `MARK_GLYPHS`,
names both marks, and both hosts read it". The definition now lives in the
chart's surface, and the Charts painter is a third reader.

**Figures.** `artifacts/u55/C3/` holds the Qt window and the React page at
1400 by 900 and at 1960 by 1200, the painter's image at ratio 1.0 and 2.0
with a crop of each, and the venue image under two themes, before and after.

## 2026-09-19 20:10 - #55 - the ATA-SMP list draws the venue image's picture

His words, 2026-09-08: *"After a market qualifies, has its chart rendered
with the appropriate confirming indicators and test, and is to be sent to the
Ready to Send bucket the Charts tabs will continue to track said market under
a ATA-SMP chart list."* And 2026-09-19: *"After its chart renderer is fully
upgraded, it will need to be migrated to ATA-SMP."* A called market on the
ATA-SMP list now draws the picture its venue images carry: the candles the
call was made on, at the call's timeframe, the overlays of its confirming
voters and no other, the reversal badge, the reading strip and the caption
band. The Live list is unchanged.

### What a called market's chart draws now

The chart takes the call's own candles, so it draws the same bars the venue
image drew, and it fetches nothing for that market. The overlays switched on
are exactly the ones the venue image switched on, the badge names the same
direction, the strip carries the same readings and the foot carries the root
image's caption. The bot annotations stay off: no fill glyph, no floor, no
target line, no landing strip, no fire glow, no position marker.

`src/gui/widgets/trade_charts_tab.py` - what one call puts on the panel

```python
        def _draw_call(self, entry: dict, call) -> None:
            """Draw ``call`` on the panel: its candles at its timeframe, its
            overlays, its badge and its caption, with no bot annotation.

            The overlay set the Live list showed is held in ``_live_overlays``
            until ``_leave_call`` restores it.
            """
            chart = self._panel.chart
            if not self._live_overlays:
                self._live_overlays = [
                    key for key, on in chart.overlays_shown().items() if on
                ]
            self._clear_annotations()
            chart.set_timeframe(str(call.timeframe))
            self._panel.show_only(list(call.overlays))
            chart.set_candles(list(call.candles))
            chart.set_call(call.direction, call.readings)
            chart.set_caption(call.caption)
```

The toggle boxes at the bottom follow the picture. The panel's own
`show_only` flips the painter and sets each box to match, with the boxes'
signals blocked so no press is counted, and the React page reads the same
set off the payload it is drawn from.

### Where the call comes from

Phase three keeps, on the chart it pulled, the candles the images drew and the
overlay keys they switched on. The Inspector's sector board turns each pulled
call into one record per symbol when the run lands, and the Charts tab reads
that record through a second callable beside the one that lists the markets.

`src/trading/ata_spm.py` - one call as the tab draws it

```python
@dataclass(frozen=True)
class ChartCall:
    """One call as the Charts tab draws it: the picture its venue images carry.

    ``overlays`` are the keys the images switched on, ``readings`` the
    ``(voter, message)`` pairs ``set_call`` takes, ``caption`` the root
    image's ``post_caption`` and ``candles`` the ``chart_candles`` rows.
    """
```

`src/gui/main_tabs/market_inspector_tab.py` - the second callable

```python
        charts.set_ata_source(inspector.watched_markets)
        # MarketInspectorTab keeps its SectorBoard as _ata_board and offers no accessor.
        board = getattr(inspector, "_ata_board", None)
        if board is None or not hasattr(charts, "set_ata_call_source"):
            logger.debug("no SectorBoard reachable; ATA-SMP charts draw no call")
            return
        charts.set_ata_call_source(board.chart_call)
```

The newest call per symbol is the one drawn, which is the vote the list shows.
A market on the list with no call held, because no run in this session called
it, draws as before: its candles fetched, no badge.

### The Live set held and given back

The overlay set the Live list showed is held the moment a call is drawn and
put back when the list returns to Live or moves to a market with no call. The
badge, the strip and the caption clear at the same moment.

`src/gui/widgets/trade_charts_tab.py` - leaving a call

```python
        def _leave_call(self) -> None:
            """Clear the call's badge and caption and restore the Live overlay set."""
            chart = self._panel.chart
            chart.set_call("", ())
            chart.set_caption("")
            if self._live_overlays:
                self._panel.show_only(self._live_overlays)
                self._live_overlays = []
            if self._showing_ata():
                self._clear_annotations()
```

### The tab's ATA-SMP readings, off the running program, both variants

The real window in each variant, the home on a scratch directory, every
socket but loopback refused, a connector shaped like Coinbase Exchange
serving the operator's own tablet copies, his scan shape (crypto, nothing
typed, 1hr 1d 1wk, target 3), then the Charts tab's toggle pressed:

| reading | Qt | React |
| ------- | -- | ----- |
| the list after the press | XLM bear 1d, AXS bear 1h | the same |
| the chart | XLM, 1d, 213 candles | the same |
| overlays on | adx, ichimoku, ker, macd, slingshot, supertrend, vortex; no other | the same |
| badge and strip | bearish, 7 readings; caption 3 lines | the same |
| floors, target line, glow, strip, position | none | none |
| boxes checked at the bottom | the same seven | the same seven off the page |
| X, Instagram, TikTok images against the chart | overlays equal, badge equal, candles 213 and 213 | the same |
| a market with no voter, planted | 50 candles, no overlay, the badge and nothing else | the same |
| `charts.ata.rendered` rows | one per call drawn, `ok` True | the same |
| the scratch `bot_state.json` | the same bytes before and after every press | the same |

### The rendered emitter

`charts.ata.rendered` writes when a called market's chart draws: the overlays
the painter shows against the call's, with the symbol, the timeframe, the
list, the widget's size, the direction, the candle count and the variant.

`src/gui/widgets/trade_charts_tab.py` - the row

```python
                _emit(
                    ATA_RENDERED_PIN,
                    actual=shown,
                    expected=sorted(call.overlays),
                    context={
                        "symbol": call.symbol,
                        "timeframe": call.timeframe,
                        "list": LIST_ATA,
                        "width": chart.width(),
                        "height": chart.height(),
                        "direction": call.direction,
                        "candles": len(call.candles),
                        "variant": "qt",
                    },
                )
```

### The sentence the ATA-SMP picture overtakes

It was not reworded. It is quoted here.

`docs/manual/08-tabs/asset-charts.md:266` - "An ATA-SMP market has no bot
behind it, so the chart draws its candles without the trade markers, the
target lines, the tranche floors and the fire glow that a traded asset
carries." The sentence holds, and holds on screen now: on `5819ced6` the last
bot's 55 floors, its target line and its glow stayed drawn when the list moved
to a called market, and the candles were fetched. A called market's candles
are the call's own, and its picture carries the call's overlays, badge, strip
and caption, which the sentence does not name.

**Figures.** `artifacts/u55/C5/` holds the tab's ATA-SMP chart in both
variants, the three comparisons side by side and the seven venue images.

## 2026-09-19 20:53 - #55 - the page's chart answers the pointer as the widget does

The React page's chart takes the same five pointer inputs the Qt widget
takes, and answers each one the same way to the candle: a hover draws a
crosshair with its readout, a wheel tick zooms about the pointer, a drag pans,
a double-click fits every candle again, and a leave takes the crosshair off.
The mechanism differs by input. A hover repaints nothing: the page draws the
crosshair itself on a canvas over the image, from the geometry the painter
exports beside every image. A zoom, a pan and a reset move the painter's
window and repaint the image, as the widget repaints itself.

### One arithmetic, called by both

The widget's handlers and the page's asks reach the same methods on
`ChartPainter`, and those methods call the pure functions
`native_chart_surface` already held: `zoom_window`, `pan_start`,
`zoom_factor`, `clamp_y_zoom`, `effective_visible_start`,
`effective_visible_count` and `fmt_price`. The drag state moved from the Qt
widget onto the painter, so both variants keep it in one place.

`src/gui/native_chart.py` - the wheel, on the painter both variants hold

```python
        def wheel_turned(
            self, x: int, wheel_delta: float, width_px: int, control_held: bool = False
        ) -> bool:
            if not self._candles:
                return False
            if control_held:
                self._y_zoom_pct = clamp_y_zoom(
                    self._y_zoom_pct * zoom_factor(wheel_delta)
                )
                self._emit_view(
                    VIEW_CAUSE_Y_ZOOM, self._visible_start, self._visible_count
                )
                self._repaint()
                return True
            window = zoom_window(
                wheel_delta,
                int(x),
                int(width_px),
                len(self._candles),
                self._visible_start,
                self._visible_count,
            )
            if window is None:
                return False
            self._visible_start = window["start"]
            self._visible_count = window["count"]
            self._emit_view(VIEW_CAUSE_ZOOM, window["start"], window["count"])
            self._repaint()
            return True
```

`CandlestickChart.wheelEvent` calls `wheel_turned` with the event's x, its
angle delta, the widget's width and whether Ctrl is held.
`CandlestickChart.mouseMoveEvent` calls `pointer_moved`, which places the
crosshair and pans through `pan_to` while a drag is active;
`mousePressEvent` and `mouseReleaseEvent` call `pointer_pressed` and
`pointer_released`; `mouseDoubleClickEvent` calls `view_reset`;
`leaveEvent` calls `pointer_left`. The grip drag along the bottom strip stays
on the widget, which is the only variant that draws a grip.

### The page's asks

The page sends each input that moves the window as one ask on the bridge
method `trade_charts_tab.view`, with the pointer's x and y, the host's width
and height and the page's device pixel ratio. `ChartsTabReact.chart_view`
answers it on the tab's painter through the same methods.

`src/gui/react_charts_tab.py` - the ask answered

```python
            if action == surface.VIEW_ACTION_WHEEL:
                moved = painter.wheel_turned(
                    x,
                    float(asked.get(surface.VIEW_DELTA_PARAM) or 0.0),
                    width,
                    bool(asked.get(surface.VIEW_CONTROL_PARAM, False)),
                )
            elif action == surface.VIEW_ACTION_PRESS:
                painter.pointer_pressed(x)
            elif action == surface.VIEW_ACTION_DRAG:
                moved = painter.pan_to(x, width)
            elif action == surface.VIEW_ACTION_RELEASE:
                painter.pointer_released()
            elif action == surface.VIEW_ACTION_RESET:
                painter.view_reset()
                moved = True
```

The answer carries the window's start and count and, when the window moved,
the repainted image with its geometry, so a zoom costs one round trip. The
image key now carries the window and the price padding, so the two-second
`update_charts` pass answers the zoomed image again instead of the fitted one.
A drag sends one move at a time; a move that arrives while one is in flight
waits, and the latest goes when the answer lands.

### The crosshair drawn by the page

Every image answer carries `geometry`: the pane rect, the price scale, the
candle column width, the window, and for each visible candle its time label
and the six readout lines the painter formats with `readout_lines` - the
same function `paint_to` draws the widget's readout from - with the theme's
colours as CSS text. The page's `pointermove` handler draws the dotted
crosshair, the price badge, the time badge and the readout box on the canvas
from those numbers, at the positions `paint_to` uses, and writes what it drew
on the chart host as `data-crosshair-x`, `data-crosshair-y`,
`data-crosshair-candle` and `data-readout`. A `pointerleave` clears the canvas
and the attributes. The price badge at the pointer's row is the one text the
page formats itself, from `PRICE_FORMAT_BANDS`, the bands `fmt_price` reads.

`src/gui/main_tabs/native_chart_surface.py` - the readout both draw from

```python
def readout_lines(candle: CandleLike) -> list[list[str]]:
    accent = READOUT_ROLE_UP if candle.close >= candle.open else READOUT_ROLE_DOWN
    change = candle.close - candle.open
    return [
        ["O", fmt_price(candle.open), READOUT_ROLE_LIGHT],
        ["H", fmt_price(candle.high), READOUT_ROLE_LIGHT],
        ["L", fmt_price(candle.low), READOUT_ROLE_LIGHT],
        ["C", fmt_price(candle.close), accent],
```

### The two pointer emitters

Two pins through `signal_contract.emit`. `charts.view.changed` writes each
time the window moves, with `actual` the window the painter holds,
`expected` the window the surface function answered, and the cause: `zoom`,
`y_zoom`, `pan` or `reset`. `charts.crosshair.shown` writes at most once per
quarter second per painter, with `actual` the candle `candle_at_x` places
under the pointer and `expected` the candle the drawing pass placed: the
widget's `paint_to` on the Qt build, the page's throttled `crosshair` ask on
the React build.

### The five inputs read off the running program

Both variants built the real `MainWindow` with the home on scratch, every
socket but loopback refused, one BTC/USD bot off a scratch copy of
`bot_state.json`, 100 BTC 1h candles rolled from a copy of the operator's 5m
tablet, at a device pixel ratio of 1.25, the widget and the page's chart host
both 1358 pixels wide.

| input | Qt widget | React page |
| ----- | --------- | ---------- |
| pointer at x 679 in the price pane | candle 52; readout O 64,634.01, H 64,846.02, L 64,632.71, C 64,741.54, delta +107.53 (+0.17%), V 445 | candle 52; the same six lines to the character |
| one wheel tick in at x 679 | window None, None to 7, 85 | 7, 85; the image digest moved |
| a drag of 120 px left | start 7 to 15 | 7 to 15 |
| a double-click | None, None; padding 1.0 | None, None; padding 1.0 |
| a leave | `_mouse_x` None; the crosshair pixels gone | the canvas holds 0 painted pixels; the attributes gone |
| a pointer in the header band | no readout | no readout, no canvas pixels |

With `ZOOM_IN_FACTOR` set to 0.5 in the React process only, the same wheel
tick reads 26, 50 on the page against 7, 85 on the widget, so the equality
reading can fail. The scratch `bot_state.json` and the tablet copy read the
same digest after every input in both variants.

### What a hover and a zoom cost

Measured on the page at 1.25, the chart host 1358 by 561 CSS pixels: a hover
draws in 0.3 to 0.4 ms per move over 60 moves, the widget's repaint reading
13.9 ms per move over the same 60. A wheel tick on the page runs 66 to 83 ms
from the ask to the image placed - 14.3 ms to paint, 41.1 ms to encode a
222 KB PNG at 1698 by 701 pixels, the rest transport and the 30 KB geometry -
against 13.4 ms on the widget. A hover on the page repaints nothing.

**Figures.** `artifacts/u55/C4/` holds the crosshair and readout in both
variants on the same candle, and both after the same wheel tick.

## 2026-09-20 05:40 - #55 - the frame: one control row, compact toggles, the value field on the ATA-SMP picture

His words, 2026-09-20: *"it does not appear that the GUI Archetype organized
all of the elements properly using any kind of rules as we still have a
significant void space and poorly placed or incorrect icons"*; *"TA values
are smashed together in a long row above the chart when they should be
stacked in the lower left corner in their own field with a dark background
and these only need to be present for ATA-SMP posting"*; *"Check boxes for
indicators are over large and taking up too much real estate."* The tab now
lays its controls by one rule, in both builds.

### The layout rule

One control row sits at the top of the tab. From the left: the list toggle,
the previous arrow, the ticker menu, the next arrow, the `n of N` counter,
the empty-list hint when the ATA-SMP list is empty, the `TF:` word and the
timeframe menu, then a stretch, then the two legend labels and the source
label at the right edge. Every control in the row is `CONTROL_HEIGHT_PX`
tall and the gap between two controls is `SELECTOR_SPACING_PX`. The type is
the design system's: the buttons and the menus at `TYPE_SMALL` in
`FONT_FAMILY_UI`, the counter and the labels at `TYPE_CAPTION`, the two
arrow glyphs at `ARROW_GLYPH_PX` in `FONT_FAMILY_GLYPH`. The chart fills
the tab's width from the row's bottom edge to the toggle row. The toggle row
is one line of fourteen boxes in `CHART_OVERLAYS` order, left-aligned, with
no stretch between them; each box is `TOGGLE_BOX_PX` square, under the
caption line height, and its label is at `TYPE_CAPTION` in the overlay's
colour. The tab draws no legend band. The ATA-SMP picture draws the value
field at the lower-left corner of the price pane. Nothing else moves.

`src/gui/main_tabs/native_chart_surface.py` - the numbers both builds read

```python
CONTROL_HEIGHT_PX = 26
ARROW_GLYPH_PX = 16
ARROW_GLYPH_FAMILY = ds.FONT_FAMILY_GLYPH
CONTROL_FONT_FAMILY = ds.FONT_FAMILY_UI
CONTROL_FONT_PX = ds.TYPE_SMALL
CAPTION_PX = ds.TYPE_CAPTION
TOGGLE_BOX_PX = 12
```

### Who lays the row

The Qt tab lays one `QHBoxLayout`. `ChartPanel` builds the `TF:` label, the
timeframe menu, the two legend labels and the source label as before, and the
tab places them in its row through `timeframe_widgets` and `legend_widgets`.
The panel keeps the chart and the toggle row.

`src/gui/widgets/trade_charts_tab.py` - the panel's controls join the row

```python
            for widget in self._panel.timeframe_widgets():
                widget.setFixedHeight(CONTROL_HEIGHT_PX)
                control_row.addWidget(widget)
            control_row.addStretch()
            for widget in self._panel.legend_widgets():
                widget.setFixedHeight(CONTROL_HEIGHT_PX)
                control_row.addWidget(widget)
            layout.addLayout(control_row)
```

The React page draws the same row in `ControlRow`, from the sizes and the
families `selector_values` carries, and the surface's `LAYOUT_SLOTS` reads
three: the control row, the chart and the toggle row. The page no longer
draws a header line of its own over the image; the painter's header line
inside the image is the one both builds show.

### The arrows draw their glyphs

The arrows carry U+25C0 and U+25B6. In the UI family those glyphs are 6 by 7
pixels at 12 pixels, a mark under a quarter of the button's height, which
reads as an empty button. The buttons now set `FONT_FAMILY_GLYPH` at
`ARROW_GLYPH_PX`, and the glyph reads 12 by 13 pixels in a 34 by 26 button.

`src/gui/design_system.py` - the family for symbol glyphs

```python
FONT_FAMILY_GLYPH = "'Segoe UI Symbol', 'DejaVu Sans', 'Apple Symbols', sans-serif"
```

### The toggle boxes

Each Qt box takes its own style sheet: the label in the overlay's colour at
the caption size, the indicator `TOGGLE_BOX_PX` square with a one-pixel
border. The page sizes each box's input from the same number, carried as
`toggle_box_px` in the panel chrome.

`src/gui/native_chart.py` - one box's style sheet

```python
TOGGLE_STYLE_FORMAT = (
    "QCheckBox {{ color: {color}; font-size: {font_px}px; spacing: {gap}px; }}"
    "QCheckBox::indicator {{ width: {box}px; height: {box}px; "
    "border-width: 1px; border-radius: 2px; }}"
)
```

### The value field on the ATA-SMP picture

The legend band under the OHLC row is gone from every surface: the OHLC row
sits directly over the price pane and the chart's natural height loses the
band's rows. The values now draw as a field at the lower-left corner of the
price pane, only on a chart that carries a call. Every venue PNG and the
tab's ATA-SMP list call `set_call` with a direction; the Live list never
does, so the tab shows no field. The field holds one caption-size line per
overlay that is on, the label in the overlay's colour and the value in the
axis text colour, on the theme's `chart_bg_top` at alpha 205 so the candles
under it stay faint, inside a one-pixel border in `chart_grid`, `FIELD_PAD_PX`
in from the pane's left edge and bottom edge. Lines past the pane's room are
not drawn.

`src/gui/native_chart.py` - what makes a chart the ATA-SMP picture

```python
        def draws_value_field(self) -> bool:
            """True when the chart carries a call, which makes it the ATA-SMP picture.

            Every venue PNG and the tab's ATA-SMP list call ``set_call`` with a
            direction; the Live list never does, so the tab draws no field.
            """
            return CALL_DIRECTION_ROLES.get(self._call_direction) is not None
```

A market on both lists keeps one symbol and draws two pictures, the bot's and
the call's, so a list press now clears the followed symbol before the chart
follows the shown market. Before this, a market that was both traded and
called kept the bot's picture on the ATA-SMP list.

### Read off the running program, both builds

Both builds built the real `MainWindow` with the home on scratch, every
socket but loopback refused, one BTC/USD bot off a scratch copy of
`bot_state.json`, 100 BTC 1h candles rolled from a copy of the 5m tablet, at
the display's ratio of 1.25, the window 1920, 1400 and 900 pixels wide, each
under `python -m pdb` with a breakpoint on the first statement of
`_draw_legend`.

| reading | before, Qt / React | after, Qt / React |
| ------- | ------------------ | ----------------- |
| distinct y of the controls | 8, 42, 78 / 12, 50, 115 | 8 / 12 |
| the chart's top edge against the controls' bottom | 108 against 104 / 136.4 against 134.4 | 42 against 34 / 50.8 against 38 |
| the arrow glyph | Segoe UI 12 px, 59 pixels of ink in the grabbed button / the browser's fallback | Segoe UI Symbol 16 px, 138 pixels of ink / the same family and size on the page |
| the box | indicator 16 by 16 in a 24 px box, label 9 px / input 13 by 13, label 9 px | indicator 12 by 12 in a 14 px box, label 10 px / input 12 by 12, label 10 px; the caption line height 12 |
| `_draw_legend` on the Live tab, the presses and ten repaints | 19 hits / 14 to 16 hits | 0 hits / 0 hits |
| the natural chart height at 1886 wide | 764 / 764 | 732 / 732 |
| the field on one planted call, on the tab | none | 191 by 51, three lines, at the pane's lower-left corner in both builds; gone again on the Live list |
| the field on the six venue sizes | none | 191 by 51 with three voters, 191 by 181 with thirteen overlays on, inside the price pane on every size |

With the row's spacing planted to zero in the driver's process only, the
gaps between the controls read 0 in both builds against 8 unplanted, so the
reading can fail.

**Figures.** `artifacts/u55/C6/` holds the tab, the arrow buttons, one box,
the window and the page at each width before and after, the six venue PNGs
with three voters and with all twelve, and the tab on the planted call.

### Five sentences the frame overtakes

"The toggle is a button on its own row, above the blue arrows and the ticker
menu." - the toggle is now the first control of the one row.

"A band under the OHLC row names every overlay with the last candle's value
of its series, in the overlay's colour. An overlay that is off reads `off` in
grey. The band wraps to the chart's width. It is painted by the painter, so
the Qt widget, the React image and the ATA-SPM post images all carry it." -
no surface carries the band; the ATA-SMP picture carries the field, and an
overlay that is off has no line in it.

"The legend wraps at the chart's width as before; at 1400, 1366 and 1200
pixels it takes two rows and its widest row ends before the price scale." -
the field does not wrap; each value is one line.

"The React page draws the tab header line and the painter draws its own
header line under it, so the label reads twice on that build." - the page
draws no header line of its own.

"The header line, the toolbar and the toggle row each take a rule between
them." - the page has no toolbar and no header line; the toggle row keeps
its rule.
