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

#### The two glyphs are hermetic characters

Two sentences above are overtaken. Each is quoted whole, with the true sentence
under it.

Overtaken: *"A fill is drawn as one of the two hermetic glyphs the Simulator's
playback draws, from one definition both read: a sell as `dissolve`, a triangle
pointing down as an outline, and a buy as `reform`, a triangle pointing up
filled."*

True now: a fill is drawn as one of two hermetic characters the Simulator's
playback draws, from one definition both read. A sell draws U+1F761, named
ALCHEMICAL SYMBOL FOR DISSOLVE, in gold. A buy draws U+1F75F, named ALCHEMICAL
SYMBOL FOR PRECIPITATE, in blue. The alchemical block carries no COAGULATE
character, and precipitate is the standard's name for a substance leaving
solution and re-forming solid, which is what a fold does.

Overtaken: *"The glyph sits on the candle whose interval holds the fill's stamp,
one candle column wide and a twentieth of the price pane tall, with a tag naming
the role and the price beside it."*

True now: the character sits on the candle whose interval holds the fill's stamp,
set at a twentieth of the price pane in the symbol family, with a tag naming the
role and the price beside it. One candle column still sets the mark's footprint
for placing that tag. The corner list and the fill flag are gone with the
triangles they described, and so is the outline width, because a drawn character
takes no outline.

```python
# U+1F761 is named ALCHEMICAL SYMBOL FOR DISSOLVE, the scrum's operation.
DISSOLVE_GLYPH = "\U0001f761"
# U+1F75F is named ALCHEMICAL SYMBOL FOR PRECIPITATE, a substance leaving
# solution and re-forming solid, which is the fold's operation.
REFORM_GLYPH = "\U0001f75f"
MARK_GLYPHS = {
    SCRUM_SIDE: {"name": DISSOLVE_GLYPH},
    FOLD_SIDE: {"name": REFORM_GLYPH},
}
MARK_GLYPH_FAMILY = ds.FONT_FAMILY_GLYPH
```

The family resolves to Segoe UI Symbol, and both characters resolve on it. The
Simulator's two playback windows draw the same two characters from the same
object.

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

## 2026-09-20 06:10 - #55 - the trade events from the History; the floors gone

His words, 2026-09-20: *"Dotted yellow lines for prior orders are supposed
to be gone. Supposed to have hermetic symbols for trade events based on the
History."* The chart draws no tranche floor on any surface, and every trade
event of the shown market is drawn as its hermetic glyph from the History
tab's rows, in both builds.

### The rule

No dashed floor line, no `FLOOR` tag and no `N FLOORS` tag on the Qt
widget, the React page's image or any venue PNG. For each row the History
tab holds for the shown symbol, one glyph: a sell as `dissolve`, a buy as
`reform`, on the candle whose interval holds the row's stamp, tagged with
the role and the price, `SCRUM` for a sell and `FOLD` for a buy. A row
outside the window is counted and not drawn. The rows are the venue's own
fills, and the History tab is the one place that fetches them; the Charts
tab never calls a venue. A fill the bus carries after launch draws at once
and is not doubled when the History's next fetch carries it. The ATA-SMP
picture and every venue PNG carry no glyph.

### Where the trade events come from

The History tab holds the venue's fills in `_all_trades`, the time of its
last fetch in `_last_fetched_ts` and whether a fetch is in flight in
`_fetch_in_flight`; see [the History tab](history.md). The window builds
it after the Charts tab, so the Charts tab reads it at each `update_charts`
tick under the name the window gives it, `_history_tab`. One surface reader
takes the three names, one reader turns the rows of the shown symbol into
fills, and one join keeps each bus fill the venue has not answered for.

`src/gui/main_tabs/trade_charts_tab_surface.py` - the rows to fills

```python
def history_fills(rows: Any, symbol: Any) -> list:
    """One fill per History row of ``symbol``: the venue's id, side, price and stamp, the role from the side.

    A row whose side is neither buy nor sell, or whose price or stamp is
    not positive, gives no fill.
    """
```

`src/gui/main_tabs/trade_charts_tab_surface.py` - the join

```python
def merged_fills(venue: Any, logged: Any) -> list:
    """``venue`` fills, then each ``logged`` fill no venue fill names.

    A venue fill names a logged fill when both carry the same venue id, or
    when their prices sit within ``FILL_MATCH_PRICE`` and their stamps
    within ``FILL_MATCH_WINDOW_S`` of each other.
    """
```

The bus fill carries no venue id today, so every join is by stamp and
price. A fill the venue answers as several rows at several prices keeps its
bus glyph beside them until the next launch.

### The one ask, and the landing

When the History has never fetched and no fetch is in flight, the Charts
tab asks `refresh()` once in its life, the same call the window makes when
the History tab is activated. The Charts tab also connects the History's
`history_refreshed` signal once, so the rows landing redraw the shown market
without waiting for the two-second tick. The window's own rule keeps the
History fresh after that.

`src/gui/main_tabs/trade_charts_tab_surface.py` - the one time the tab asks

```python
def history_never_fetched(state: dict) -> bool:
    """True when the History has never landed a fetch and none is in flight: the one time the Charts tab asks."""
    return state["fetched_ts"] == NEVER_FETCHED_TS and not state["in_flight"]
```

`src/gui/widgets/trade_charts_tab.py` - the Qt tab's draw

```python
        def _draw_history(self) -> None:
            """Put the shown market's trade events on the chart: the History's fills
            for its symbol, then each bus fill since launch the venue has not
            answered for.

            A History that has never fetched is asked to ``refresh`` once, the
            call the window makes on activation; ``history_refreshed`` is
            connected once so the landing redraws without waiting for the tick.
            A called market on the ATA-SMP list gets none.
            """
```

The React widget hands the same three names to its model through
`set_history`, and the model's `feed_history` runs in `update_charts` before
the bot's own annotations. Both builds read the same glyph set on the same
candles from one painter.

### The floors gone

`ChartPainter` no longer holds `_tranche_floors`, `set_tranche_floors` or
`_draw_floors`; `FLOOR_LINE` is no longer a palette role; the two floor tag
formats are gone. The Qt tab no longer reads the bot's lots, the React model
no longer carries floors, and the page no longer stamps a floor count. The
annotation emitter `charts.annotations.drawn` names fills, target lines, the
strip, the glow and positions, and no floors; it now also fires when the
fed count or the off-window count moves, so a row landing outside the window
writes a row. The standing scrums off the bot's fold tranches are no longer
a source of markers: the History's rows are the venue's answer for the same
sells.

### The History readings, off the running program, both builds

Both builds, the real window, the home on a scratch directory, every socket
but loopback refused, a two-bot fleet off a scratch copy of one seed record,
100 recorded BTC 1h candles rolled from the 5m tablet by the registry's own
rollup and shifted by whole hours so the newest candle opens at the current
hour, and a History venue on loopback answering `get_my_trades` with 40
BTC/USD rows (26 on distinct candles inside the window, 14 older than it)
and 6 ETH/USD rows, through the History tab's own fetch path:

| reading | Qt | React |
| ------- | -- | ----- |
| `_draw_floors` and `set_tranche_floors` on the painter | absent; 0 floors held; the emitter names no floor | the same |
| the History at the tab's first tick | never fetched; the tab asks once; the venue is asked once per market, 2 of 2; 46 rows land in 0.21 s | the same |
| the shown market's rows against its glyphs | 40 rows for BTC/USD, 40 markers held, 26 drawn on 26 candles, 14 counted off the window | the same 40, 26 and 14 |
| a six-notch zoom to 36 candles, then a reset | 5 drawn and 35 off; back to 26 and 14 | the same |
| one bus fill on the newest candle | drawn at once, 27 of 41; the History's next fetch carrying it leaves 27 of 41 | the same |
| a row planted inside the window, then one outside | 28 drawn of 42; then 28 drawn of 43 with 15 off | the same |
| ETH/USD shown, then BTC/USD again | 6 rows, 4 drawn, 2 off; back to 28 of 43 | the same |
| the History tab after these fetches | 49 of 49 trades shown, page 1 of 1 | the same |
| the venue image with a call | no glyph, no floor | one painter |

**Figures.** `artifacts/u55/C7/` holds the tab, the chart and the window at
1920 and 1400 in both builds, before and after.

### Six sentences the History glyphs overtake

They were not reworded. They are quoted here.

"`set_tranche_floors` | The standing fold-tranche floors" - the setter table
row; the setter no longer exists and nothing places a floor.

"The fills come from two figures of the bot. Each tab subscribes to the bus
topic every fill crosses and records it, so a fill made after launch draws
on the next status tick. And each standing fold tranche the bot holds was
made at a scrum: its reference price is that sell and its stamp is that
sell's time, so the tab draws each one as a scrum glyph." - the fills come
from the History tab's rows for the shown symbol, then the bus fills since
launch the venue has not answered for; the fold tranches are no longer a
source.

"Each tranche floor keeps its dashed line; floors whose tags would overlap
share one tag naming their count and their price span, so 16 floors in one
pane read as seven tags." - no floor draws on any surface.

"`charts.annotations.drawn` is written when the set of annotations the
paint pass drew changes, with the counts drawn against the counts fed that
fall inside the pane, and the fills fed and the fills off the window in its
context." - it is also written when the fills fed or the fills off the
window change, and it names no floor.

"55 floors off the record | 55 lines fed, 16 inside the pane, 7 tags | the
same" - a reading of the floors, which no longer draw.

"An ATA-SMP market has no bot behind it, so the chart draws its candles
without the trade markers, the target lines, the tranche floors and the
fire glow that a traded asset carries." - the sentence holds; there are no
tranche floors on any market now.

## 2026-09-20 09:45 - #55 - the oscillators: one readable sub-pane height, whole-pixel pens, tags that never cross

His words, 2026-09-20: *"Oscillators are not being drawn at the highest
quality and are too compressed vertically to be read clearly."* And: *"it
does not appear that the GUI Archetype organized all of the elements properly
using any kind of rules."* Three rules now govern the seven sub-panes, the
pens and the fill tags, and each is proved on the running program in both
builds. The GUI Archetype carries no layout or draw-quality rule, so the
rules are stated here and read off the widget and the page.

### The height rule

Every sub-pane on the Charts tab draws at one readable height. The figure is
derived from what a sub-pane holds: a label row one tag tall over a plot of
five bands one tag tall each - room over the upper ruled level, the upper
level, the value tag at the middle, the lower level, and room under the
lower level. A tag is 14 px, so a sub-pane is 14 + 5 x 14 = 84 px. The
lines, the histogram and the ruled levels plot under the label row and never
through it. The value tag sits at the plot's middle. The price pane never
falls under 220 px.

`src/gui/main_tabs/native_chart_surface.py` - the figure beside the pane numbers

```python
TAG_HEIGHT_PX = 14
#: A sub-pane's label row, one tag tall, over its plot.
SUB_PANE_LABEL_PX = TAG_HEIGHT_PX
#: The tag-tall bands a sub-pane's plot holds: over the upper ruled level, the
#: upper level, the value tag at the middle, the lower level, under the lower level.
SUB_PANE_PLOT_BANDS = 5
#: The height every sub-pane draws at on the Charts tab: the label row over
#: the plot's bands. A host shorter than the panes' height scrolls.
SUB_PANE_READABLE_PX = SUB_PANE_LABEL_PX + SUB_PANE_PLOT_BANDS * TAG_HEIGHT_PX
#: The least height a sub-pane folds to on a fixed-height venue image.
SUB_PANE_FOLD_PX = 28
```

The chart's height is the natural height of the panes on. With the volume
strip and the seven sub-panes it is 28 + 18 + 220 + 28 + 7 x 84 + 18 = 900 px.
A panel taller than that gives the rest to the price pane. A panel shorter
than that keeps the chart at 900 and scrolls it.

`src/gui/native_chart.py` - the widget's height

```python
        def _apply_height_for_panes(self) -> None:
            """Set the minimum height to ``_natural_height_for_panes`` at the widget's width.

            ``_height_override`` from a grip drag wins when it is taller. The
            scroll area holding the chart scrolls when its viewport is shorter
            than this height; a taller viewport's extra height goes to the price pane.
            """
            target = self._natural_height_for_panes(self.width())
```

### The scroll hosts

On the Qt panel the chart sits in a scroll area with a vertical bar as needed
and no horizontal bar. A wheel over the chart zooms the window, as before,
and never scrolls the area, because the chart takes the wheel. The bar
scrolls. The toggle row sits under the scroll area at the tab's foot.

`src/gui/native_chart.py` - the scroll area in the panel

```python
            self._scroll = QScrollArea(self)
            self._scroll.setAccessibleName(CHART_SCROLL_NAME)
            self._scroll.setWidgetResizable(True)
            self._scroll.setFrameShape(QFrame.NoFrame)
            self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self._scroll.setWidget(self._chart)
            layout.addWidget(self._scroll)
```

On the page the chart mount scrolls the same way. The image host inside it
is never under the natural height, so a shorter mount scrolls and the
toggle row under the mount stays at the panel's foot. The wheel listener on
the host already takes the wheel for the zoom.

`src/gui/web/trade_charts_tab.js` - the mount and the host

```javascript
      style: {
        flex: AUTO,
        minHeight: ZERO_PX,
        overflowX: HIDDEN,
        overflowY: AUTO,
        display: FLEX,
        flexDirection: COLUMN
      }
```

```javascript
    into.style.minHeight = height(
      answer[IMAGE_NATURAL_HEIGHT] === undefined
        ? answer[IMAGE_HEIGHT]
        : answer[IMAGE_NATURAL_HEIGHT]
    );
```

The image the page asks for is never under the natural height either.

`src/gui/react_charts_tab.py` - the image's height

```python
            natural = int(self._painter._natural_height_for_panes(width))
            minimum = int(self._painter._minimum_height_for_panes(width))
            height = max(natural, asked_height)
```

A fixed-height venue image keeps the fold of 2026-09-19: each sub-pane
shrinks from the readable height toward 28 px, then the reading strip folds,
then the price pane shrinks toward 120 px, and a height under the least
layout is refused by name.

### The quality rule

Every stroke pen's width is its logical width scaled by the device pixel
ratio to whole device pixels, never under one. The five logical widths 0.8,
1.0, 1.2, 1.4 and 1.5 draw 1, 1, 1, 1 and 2 device pixels at ratio 1.0 and
1, 1, 2, 2 and 2 at 1.25. Lines draw with anti-aliasing on. Axis rules - the
grid, the pane separators, the ruled levels, the reference lines and the
MACD zero line - draw with anti-aliasing off, one device pixel wide, on
coordinates snapped to the centre of a device pixel. Bars - the volume bars
and the MACD histogram - draw with anti-aliasing off on whole device pixels.
Text stays at the caption size in the mono family.

`src/gui/main_tabs/native_chart_surface.py` - the pen width

```python
def device_pen_width(width_px: float, ratio: float) -> float:
    """``width_px`` logical pixels scaled by ``ratio`` to whole device pixels, never
    under one, given back in logical pixels."""
    scale = float(ratio) if float(ratio) > 0 else 1.0
    return max(1, round(float(width_px) * scale)) / scale
```

`src/gui/native_chart.py` - one ruled level

```python
                def _rule_line(y: float, colour=None, dashed: bool = True) -> None:
                    """One ruled level across the pane at ``y``: one device pixel, aliased, snapped."""
                    pen = QPen(colour if colour is not None else self.GRID_MINOR, px)
                    if dashed:
                        pen.setStyle(Qt.DashLine)
                    p.setRenderHint(QPainter.Antialiasing, False)
                    p.setPen(pen)
                    p.drawLine(QPointF(ML, snap(y)), QPointF(w - MR, snap(y)))
                    p.setRenderHint(QPainter.Antialiasing, True)
```

### The tag rule and the readout

Every glyph draws first. A fill tag is then placed at the right of its glyph,
or at the left when the right would cross the price scale. A tag that would
cross a glyph or a tag already drawn is not drawn. The glyph count does not
move. Merging two tags into one naming a count was not chosen, because a
count names no price and no role.

`src/gui/native_chart.py` - where a tag goes

```python
        def _tag_place(
            self,
            right_x: float,
            left_x: float,
            y: float,
            width: float,
            drawn: list,
            scale_x: float,
        ) -> Optional[QRectF]:
            """The rect a fill tag draws in: ``TAG_H_PX`` tall at ``right_x`` when
            ``_tag_clear``, else at ``left_x`` when clear, else None and no tag."""
            for x in (right_x, left_x):
                rect = QRectF(x, y, width, TAG_H_PX)
                if self._tag_clear(rect, drawn, scale_x):
                    return rect
            return None
```

The crosshair's readout names every fill on the candle under the pointer.
One row per fill follows the six candle rows: its label is the side's glyph
character, a sell as a filled triangle pointing down and a buy as one
pointing up, and its text is the tag's text in the marker's colour. The
painter's own tip and the page's canvas tip both draw the rows, because the
page reads them off the geometry the image answer carries.

`src/gui/main_tabs/native_chart_surface.py` - one readout row for a fill

```python
def fill_row(fill: FillLike) -> list[str]:
    """One readout row for ``fill``: the side's glyph, the tag's text and its role."""
    is_buy = str(fill.side).lower() == FILL_BUY_SIDE
    return [
        READOUT_BUY_GLYPH if is_buy else READOUT_SELL_GLYPH,
        FILL_TAG_FORMAT.format(label=fill_label(fill), price=fmt_price(fill.price)),
        fill_role(fill),
    ]
```

### The oscillator readings, off the running program, both builds

Each build ran the real window with the home on a scratch directory, every
socket but loopback refused, two bots off a scratch copy of one record, 100
BTC 1h candles and a loopback History venue answering 40 fills, 26 inside the
window. The chart's host was resized to 690, 900 and 1100 px. Each run was
driven under the debugger with a breakpoint on the paint pass, ignored on
every crossing and counted at the end.

| reading | before, Qt / React | after, Qt / React |
| ------- | ------------------ | ----------------- |
| seven sub-panes at a 690 px host | 54.0 px each, the price pane 220, no scroll | 84.0 px each, the price pane 220, the chart 900 tall, the bar's range 210 |
| at 900 | 60.0 each, 388 | 84.0 each, 220, range 0 |
| at 1100 | 60.0 each, 588 | 84.0 each, 420, range 0 |
| the toggle row | under the chart | under the scroll host at the tab's foot: y 738 on Qt, 740.8 on the page, at 690 |
| the wheel over the chart | zooms 100 to 85 candles | zooms 100 to 85; the bar stays at 0 |
| the stroke pens in device pixels, ratio 1.0 | 0.8, 1.0, 1.2, 1.4, 1.5, 1.7 | 1, 2 |
| ratio 1.25 | 1.0, 1.25, 1.5, 1.75, 1.875, 2.12 | 1, 2 |
| the fills at 100 candles | 26 glyphs, 26 tags, 24 overlapping pairs | 26 glyphs, 15 tags, 0 overlapping pairs |
| at 36 candles | 5 glyphs, 5 tags, 0 pairs | 5 glyphs, 4 tags, 0 pairs |
| the squat venue, Facebook 1200 by 630, eight voters | seven sub-panes at 40 px, the strip folded, the price pane 226 | the same |
| the readable figure planted to 20 | - | seven sub-panes at 20.0, the chart 452 tall; 84.0 restored |
| the tag rule planted off | - | 26 tags, 24 overlapping pairs; 15 and 0 restored |

The crops at 1.25, four times enlarged: before, the RSI line smeared over
two to three device rows and the 30 and 70 rules over two faint rows; after,
the line two device pixels and each rule one crisp dashed row, the label in
its own row over the plot, the value tag legible. Renders sit under
`artifacts/u55/C8/` before and after.

### Four sentences the oscillators overtake

They were not reworded. They are quoted here.

"Each takes 60 px at the chart's natural height. When the window gives less,
every sub-pane shrinks alike, down to 28 px, so the price pane keeps its 220
px and every pane stays on screen." - each takes 84 px on the tab at every
window height, and the panel scrolls when the window gives less; only a
fixed-height venue image shrinks a sub-pane, toward 28 px.

"`SUB_PANE_H = 60`" and "`SUB_PANE_MIN_H = 28`" - the two names are gone;
the painter reads the surface's readable figure and its fold floor.

"The wick is a share of one candle column and never under one device pixel;
the candle border is one device pixel; the indicator lines keep their
logical width and stay anti-aliased. Read on a 1200 pixel image at ratio 1.0
the pens are 0.8, 1.0, 1.2, 1.4, 1.5 and 1.56 logical pixels; at ratio 2.0
the set gains 0.5, the one-device-pixel pen." - every stroke pen is now a
whole number of device pixels; at ratio 1.0 the set is 1 and 2, at 1.25 it
is 0.8 and 1.6 logical, which are 1 and 2 device pixels.

"The glyph sits on the candle whose interval holds the fill's stamp, one
candle column wide and a twentieth of the price pane tall, with a tag naming
the role and the price beside it." - the glyph holds; its tag draws only
where it crosses no glyph and no other tag, and the readout names the fill
under the pointer.

## 2026-09-23 17:30 - #55 - the oscillators are a third taller, and the bottom bar drags both heights

His words, 2026-09-23: *"Oscillator default height should be increased by 30%
- Oscillator and chart height needs to be adjustable by dragging the bottom
bar. Said adjustments must move all subsequent elements down and not overlap
them"*.

### The default height

A sub-pane's plot now holds seven tag-tall bands, not five: two over the
upper ruled level, the upper level, the value tag at the middle, the lower
level, and two under it. A tag is 14 px, so a sub-pane is 14 + 7 x 14 = 112
px. Read off the running chart before the change it was 84.0 px. His figure,
84 x 1.3, is 109.2 px, which is not a whole number of bands; seven bands is
the least count that reaches it, and it gives the plot the same room above
the upper level as below the lower one. The rise is 33.3%.

`src/gui/main_tabs/native_chart_surface.py` - the band count

```python
#: The tag-tall bands a sub-pane's plot holds: two over the upper ruled level,
#: the upper level, the value tag at the middle, the lower level, two under the
#: lower level. Seven is the least count whose height clears 84 px by the 30%
#: the operator asked for: 14 + 7 x 14 = 112, a rise of 33.3%.
SUB_PANE_PLOT_BANDS = 7
```

The chart's natural height follows. With the volume strip and the seven
sub-panes it is 28 + 18 + 220 + 28 + 7 x 112 + 18 = 1096 px, where it was
900. A panel shorter than that scrolls to it.

### The bottom bar

Three short dashes draw across the chart's bottom edge, in a strip 8 px tall.
Pressing in that strip and dragging down sets the chart's height, and every
sub-pane keeps the share of the chart it holds at the natural height. One
drag therefore raises the price pane and every oscillator together. Dragged up, the
height stops at the natural 1096 and the sub-panes return to 112 px. The
pointer turns to the vertical resize arrows over the strip on the Qt widget.

`src/gui/main_tabs/native_chart_surface.py` - the share the drag gives a sub-pane

```python
def sub_pane_height(dragged_height_px: int, readable_height_px: int) -> int:
    scaled = SUB_PANE_READABLE_PX * int(dragged_height_px) // int(readable_height_px)
    return max(SUB_PANE_READABLE_PX, scaled)
```

`CandlestickChart.mouseMoveEvent` drives it on the widget, and `chart_view`
drives it on the page from the same press, drag and release the page already
sends. Both call `set_pane_drag_height`, so both builds answer one grab of
the bar the same way.

### Nothing below the drag overlaps

Inside the chart the panes are laid one under the next: each pane's top is the
pane above's bottom, so a drag moves every pane under it down by the height it
won. Outside the chart the panes sit in a scroll host, with the toggle row
under the host, so the host's own height never changes and the toggle row
never moves. Read on the running program at 700, 900 and 1400 px wide:

| drag | sub-pane | price pane | vortex | rsi | time axis | chart bottom |
| ---- | -------- | ---------- | ------ | --- | --------- | ------------ |
| at rest | 112.0 | 46.0 - 266.0 | 294.0 - 406.0 | 966.0 - 1078.0 | 1078.0 - 1096.0 | 1096 |
| +260 | 138.0 | 46.0 - 344.0 | 372.0 - 510.0 | 1200.0 - 1338.0 | 1338.0 - 1356.0 | 1356 |
| +4000 | 520.0 | 46.0 - 1410.0 | 1438.0 - 1958.0 | 4558.0 - 5078.0 | 5078.0 - 5096.0 | 5096 |
| dragged up | 112.0 | 46.0 - 266.0 | 294.0 - 406.0 | 966.0 - 1078.0 | 1078.0 - 1096.0 | 1096 |

On the Qt panel at 700 px wide the scroll host reads 0.0 - 668.0 and the
toggle row 674.0 - 686.0 at every one of those positions; at 900 the host
reads 0.0 - 878.0 and the row 884.0 - 896.0; at 1400 the host reads
0.0 - 1078.0 and the row 1084.0 - 1096.0. On the page at 700 the chart mount
reads 50.8 - 656.8 and the toggle row 660.6 - 674.6 at every position, and
the image inside the mount grows from 1146.8 to 4002.8 while the mount
scrolls.

### The height and drag readings, off the running program, both builds

Each build ran with the home on a scratch directory and every socket but
loopback refused, 100 BTC 1h candles, seven sub-panes on, the panel at 700,
900 and 1400 px wide. The Qt numbers come from `ChartPainter.geometry_payload`,
which reports what the last paint laid out; the page's numbers come from the
same payload carried on the image answer, and its element rectangles from the
page's own `getBoundingClientRect`.

| reading | before, Qt / React | after, Qt / React |
| ------- | ------------------ | ----------------- |
| each sub-pane at rest, every width | 84.0 / 84.0 | 112.0 / 112.0 |
| the chart's natural height | 900 / 900 | 1096 / 1096 |
| the bar dragged +260 | 84.0, the chart 1160 / no answer, the image 900 | 138.0, the chart 1356 / 138.0, the image 1356 |
| the bar dragged +4000 | 84.0, the chart 4900 / no answer, the image 900 | 520.0, the chart 5096 / 520.0, the image 5096 |
| the bar dragged up | 84.0, the chart 900 / 900 | 112.0, the chart 1096 / 1096 |
| the panes' tops and bottoms, every position | each top the one above's bottom | the same |
| the toggle row against the scroll host | 674.0 under 668.0 / 660.6 under 656.8 | the same at every drag position |
| the band count planted back to 5 | - | 84.0 at rest and the natural height 900, in both builds; 112.0 restored |

Renders sit under `artifacts/u55/C9/`, one per width and drag position in each
build.

### Three sentences the drag overtakes

They were not reworded. They are quoted here.

"A tag is 14 px, so a sub-pane is 14 + 5 x 14 = 84 px." - a sub-pane's plot
holds seven bands, so a sub-pane is 14 + 7 x 14 = 112 px.

"With the volume strip and the seven sub-panes it is 28 + 18 + 220 + 28 + 7 x
84 + 18 = 900 px." - it is 28 + 18 + 220 + 28 + 7 x 112 + 18 = 1096 px.

"each takes 84 px on the tab at every window height" - each takes 112 px at
every window height, and a drag of the bottom bar raises that figure with the
chart.

## 2026-09-23 22:10 - #55 - the trade markers draw on every timeframe

His words, 2026-09-23: *"Historical trade markers ... do not consistently appear and I could
only get them to do so on the weekly timeframe during the previous test."* The chart now draws
a fill's glyph at 5m, 1h, 1d and 1w, and where a timeframe cannot reach a fill it says so in
the header.

### The window rule and what each timeframe reaches

One fetch asks for `FETCH_LIMIT` candles, and a fill can only be drawn on a candle the fetch
brought back. The window a chart draws is therefore the candle count times the timeframe's own
length, and a fill older than the first candle is counted, named in the header, and not drawn.

`FETCH_LIMIT` is 300. One request carries at most 300 candles on the Coinbase candles route,
which the tree records as `RA_CHUNK_DAYS`, and the Advanced Trade route's own ceiling is 350.
The lower of the two is the figure the chart asks for, so no fetch asks a route for more than it
serves. The fetch is one request either way, because the count is a parameter of that one call.

`src/gui/main_tabs/trade_charts_tab_surface.py` - the one declaration

```python
#: Candles one fetch asks for, and so the span a fill's glyph can land in;
#: 300 is the Coinbase candles route's one-request ceiling, recorded as
#: ``RA_CHUNK_DAYS``. ``src.gui.widgets.trade_charts_tab`` imports this name.
FETCH_LIMIT = 300
```

What 300 candles reach, from `TIMEFRAME_SECONDS`:

| timeframe | window span | reaches a fill this old |
| --- | --- | --- |
| 5m | 1.042 days | one day |
| 1h | 12.500 days | twelve and a half days |
| 1d | 300.000 days | ten months |
| 1w | 2100.000 days | five years nine months |

A five-minute chart cannot reach a fill five months old. Reaching 152 days at 5m needs 44,011
candles, which is 147 requests and 0.014 px a candle in the pane; at 1h it needs 3,668 candles
and 12 requests. The daily and the weekly reach every fill a bot of this fleet holds, and the
two short timeframes draw what they reach and name the rest.

### One declaration of the candle count

`FETCH_LIMIT` was declared in two files with the same value. Nothing compares the two, so the
two copies could disagree without anything reporting it. The surface declares the name now, and
the Qt tab imports it.

`src/gui/widgets/trade_charts_tab.py` - the import

```python
from ..main_tabs.trade_charts_tab_surface import (
    FETCH_LIMIT,
    bot_timeframe,
    fill_record,
```

### The header names the fills it could not draw

The paint pass counts each fill it refused, under the reason it refused it: older than the first
candle, past the last one, or at a price outside the drawn scale. The header carries one phrase
per reason that counted anything, beside the symbol, the timeframe, the source and the candle
count. A chart with nothing refused carries none of them, and its picture is unchanged.

`src/gui/native_chart.py` - the three phrases

```python
FILLS_OLDER_HEADER_FORMAT = "{count} {fills} older than this chart"
FILLS_NEWER_HEADER_FORMAT = "{count} {fills} newer than this chart"
FILLS_OFF_SCALE_HEADER_FORMAT = "{count} {fills} off the price scale"
```

`charts.annotations.drawn` carries the same counts split by reason:
`fills_older_than_window`, `fills_newer_than_window` and `fills_off_price_scale`, with
`fills_off_window` the sum of the first two. It previously folded a fill at a price off the
drawn scale into `fills_off_window`, which named the window for an absence the window did not
cause.

### The marker readings per timeframe

One market, 37 fills fed, read off the running program in both builds at 700, 900 and 1400 px
wide. The candles come from a read-only copy of one five-minute stone tablet on disk, folded to
each timeframe by the registry's own rollup; the fills carry the fill ages of the running
fleet, read from a read-only copy of its state file. No venue was contacted, every socket but
loopback was refused, and no bot was started and no order placed, priced or cancelled.

| timeframe | candles before | candles after | window before | window after | drawn before | drawn after | header after |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 5m | 100 | 300 | 0.347 days | 1.042 days | **0** | **6** | 31 fills older than this chart |
| 1h | 100 | 300 | 4.167 days | 12.500 days | 12 | **18** | 19 fills older than this chart |
| 1d | 100 | 213 | 100.0 days | 213.0 days | 31 | **37** | none |
| 1w | 31 | 31 | 217.0 days | 217.0 days | 37 | 37 | none |

The daily and the weekly answered fewer candles than the 300 asked for, because the tablet on
disk holds 212.771 days; a venue serving the whole 300 reaches 300 days at 1d.

Every marker sat on the candle holding its own stamp at every timeframe and every width, with
no fault in any reading. One fill planted at 400 days, outside every window including the
weekly's, raised every timeframe's refused count by exactly one and turned the daily and the
weekly from no phrase to `1 fill older than this chart`.

Read off the saved renders rather than off the painter: at the weekly, before and after differ
by **0 pixels** in both builds and in the image the page is handed, and the planted phrase
differs by 720 pixels inside rows 14 to 22, the header's own band. At 700 px wide the longest
header this draws ends 89 px clear of the right edge, so no phrase is clipped at the narrowest
width.

A paint pass costs 40.58 ms at 300 candles against 27.64 ms at 100, at 700 px; 28.10 against
15.82 at 900; 30.51 against 19.43 at 1400. The tick that redraws the chart runs every two
seconds.

Renders sit under `artifacts/u55/C11a/`, one per build, stage, width and timeframe.

### Sentences the window rule overtakes

They were not reworded. They are quoted here.

"A fill whose stamp falls before the window or past its end is counted and not drawn." - it is
counted, named in the header under the reason it was refused, and not drawn.

"A row outside the window is counted and not drawn." - a row outside the window is counted,
named in the header, and not drawn.

"`charts.annotations.drawn` is written when the set of annotations the paint pass drew changes,
with the counts drawn against the counts fed that fall inside the pane, and the fills fed and
the fills off the window in its context." - the context now carries the fills fed, the fills off
the window, and that figure split into the fills older than the window, the fills newer than it
and the fills at a price off the drawn scale.
