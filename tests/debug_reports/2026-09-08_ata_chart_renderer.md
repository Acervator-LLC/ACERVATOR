# The Chart Renderer, Redesigned For The Charts Tab

**Mode: Reference.**

The Asset Charts tab drew one chart per running bot down a scroll, every
indicator switched off except Volume, and the toggles in the toolbar above the
chart. This unit rebuilds it as one chart at a time, chosen with arrows and a
ticker list, with the toggles underneath and every indicator on except the two
that paint over the bands.

Nothing here was measured against a running Acervator. No process was started,
attached to or queried, no order was touched, and no exchange call was made.

## What each indicator draws, and which two start off

The test is what an overlay paints over the price pane. An overlay that fills a
shape there can hide the Bollinger bands or the Ichimoku cloud; one that draws a
line, or sits in its own pane below, cannot. The alpha byte below is the
transparency each fill is painted at, read from the shipped paint calls.

| overlay | what it paints | pane | starts |
|---|---|---|---|
| BB | a cloud between the upper and lower bands at alpha 32, and three lines | price | on |
| Ichi | the kumo between Span A and Span B at alpha 50, four lines and Chikou | price | on |
| Vortex | VI+ and VI- against a 1.0 reference | own pane | on |
| MACD | a histogram, the line and the signal | own pane | on |
| SRsi | one line against 0.2 and 0.8 | own pane | on |
| Vol | bars beside each candle, and a rule above the strip | own strip | on |
| **Sling** | **solid marks at alpha 230, anchored on the candle high and low** | price | **off** |
| **BBull** | **four filled envelopes at alpha 55 and 95, drawn on the bands** | price | **off** |

Slingshot is the operator's own case and it is confirmed: its marks are painted
at alpha 230, which is very nearly opaque, and they land on the price where a
band line runs.

**BB Bullseye is the third occluder, and it was not named in advance.** It
paints four polygons at alpha 55 and 95 whose whole purpose is to shade a
±0.5% and ±0.2% envelope *around the Bollinger bands themselves*. At alpha 95
it is three times the Bollinger cloud's own alpha 32, sitting directly over it.

**Z-Score has no overlay to switch off.** The operator named it as a case. The
renderer draws eight overlays and none of them is Z-Score, so there is nothing
to default off; adding one is the first use of the seam this unit leaves.

## Every overlay was toggled and every one moved pixels

The panel was built offscreen at 1440 by 1100, fed 200 generated candles, and
rendered once per toggle state. The number is the size of the symmetric
difference between the two sampled pixel sets, every third pixel on both axes.

```
bb         starts on   pixel-set delta 2731
vortex     starts on   pixel-set delta 4356
macd       starts on   pixel-set delta 4746
stochrsi   starts on   pixel-set delta 4838
ichimoku   starts on   pixel-set delta 1303
volume     starts on   pixel-set delta 3828
slingshot  starts off  pixel-set delta  416
bbullseye  starts off  pixel-set delta 1651

overlays that moved pixels: 8 of 8
```

## The selector, driven

The tab was built offscreen and fed four bot statuses, one of them an Extractor
carrying the wildcard symbol the fetch path refuses.

```
empty ticker : "No asset"  position "0 of 0"  arrows disabled
after statuses: assets ['BTC/USD', 'ETH/USD', 'SOL/USD']   (the wildcard dropped)
shown          : 0  BTC/USD  "1 of 3"
after next     : 1  ETH/USD  "2 of 3"
after two prev : 2  SOL/USD  "3 of 3"   (the list wraps)
after the list : 1  ETH/USD  chart symbol ETH/USD
arrows enabled : True True
toggles on the panel: 8
```

## The two sides, read against each other

The Qt tab and the Qt-free surface were driven over one set of bot statuses and
every value either side reports was compared: the selector's texts, tooltips and
sizes, the ticker items, the position readout, the asset order, the overlay
registry with its labels, colours, defaults and occlusion, and every mirrored
palette colour.

```
values compared: 53
matched        : 53
```

The same reads over two different asset lists differ on 4 of 4, so the
comparison was watched reporting a difference before its agreement was read as
one.

The renderer module was then handed the surface's own view model inside
`QJSEngine` and asked what it holds.

```
faults    : []
panelOrder: ["b1","b2","b3"]
content   : {"margins_px":[4,4,4,4],"spacing_px":12,"layout_slots":3}
```

**This is a comparison of reported values, not of two pictures.** The React
half draws inside the Electron shell, and this unit may not start it. A value
both sides report is the stronger reading in any case: two renders can agree
because a host lacks a font, while a reported value cannot.

## The colours, measured

Twenty-one chart tokens were added to `ThemeTokens`, one set per theme, and the
renderer resolves 56 painted colours through them. No colour literal remains in
any paint call.

`src/design_system.py` — `contrast_ratio`, run over every token against its own
theme's ground:

```
ink tokens measured: 85
under 3.0:1        : 0
```

Before the correction the same run reported 17 under 3:1. Five carried a
reading and were corrected; the rest were the grid and the crosshair, which are
drawn under the data on purpose and are listed with their measurements rather
than raised.

## The errors the runs reported, and the corrections

### The follow guard read the wrong value

`_follow_current` compared the chart's own symbol against the asset it should
draw, to avoid clearing a tape it was already showing. The chart's symbol
carries the price and the state, because the price label writes it directly.

```
AttributeError: 'PanelSink' object has no attribute 'symbol'
```

The surface raised first, which is what surfaced it. The comparison would have
been false on every pass after the first label, so the chart would have cleared
its candles and refetched on every update. Both sides now track the plain
symbol in a field of their own.

### The renderer named a field before it held one

`trade_charts_tab.js` listed `PANEL` in `DECLARED_FIELDS`, and `var PANEL` was
assigned further down the file. JavaScript hoists the declaration and not the
assignment, so the array held `undefined` and the module reported a field it
could not name.

```
faults: [{"where":null,"fault":"missing","detail":null}]
```

The declaration moved above the array. The module now reports no faults.

### The pane bounds read as band arithmetic

`ta_archetype` reported two high findings on `native_chart.py` **before this
unit changed anything**:

```
TA004 units mismatch: 'y' (dimensionless) compared against 'mt' (absolute).
```

The line is `_draw_positions` testing whether a price maps inside the price
pane. The names `y`, `mt` and `ch` collide with the symbols a Bollinger
squeeze uses, so the rule read pixel geometry as band width. The names now say
what they hold — `price_y_px`, `pane_top_px`, `pane_height_px` — and the
archetype reports `passed=True` on the file.

## The seam this unit leaves

Adding the ninth overlay is two things and touches no existing overlay:

1. One `ChartOverlay` entry in `CHART_OVERLAYS`, naming its key, label, theme
   colour field, pane, whether it occludes, its draw method and its tooltip.
2. One draw method. The pane fixes what it is handed: a price-pane overlay
   takes one `PaintContext`; a sub-pane overlay takes one plus its top and
   bottom; the volume strip takes the painter, both edges and the strip's top.

The registry already drives the defaults, the toggle row, the sub-pane layout
and the paint dispatch, so nothing else enumerates the overlays.

**What is left in the paint routine.** The candle bodies, the price and time
grid, the axis labels, the last-price badge, the trade markers, the target
balance lines, the tranche floors, the fire-armed glow and the crosshair are
still painted inline. They are the chart itself rather than overlays, and none
of them holds a colour any more.

## What the operator sees differently

One chart instead of a scrolling column. Blue arrows and a ticker drop-down to
move between assets, with a readout saying which of how many. Every indicator
drawn by default except Slingshot and BB Bullseye, and a check box for each
along the bottom. Bolder candles, and a chart whose colours change with the
theme.

## What is not done

The manual still carries one sentence describing the old layout — *"The tab
scrolls one panel per active bot"* — because this unit was told to add to the
manual and never to reword it. That sentence and the passage added beneath it
now disagree.
