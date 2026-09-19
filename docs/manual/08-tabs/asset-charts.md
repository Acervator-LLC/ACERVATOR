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
36 px, so the price pane keeps its 220 px and every pane stays on screen.

`src/gui/native_chart.py` - the pane heights

```python
SUB_PANE_H = 60
SUB_PANE_MIN_H = 36
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
