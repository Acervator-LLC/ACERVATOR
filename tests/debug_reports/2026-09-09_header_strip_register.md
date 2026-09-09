# 2026-09-09 — Header strip: the spendable panel registers, the privacy dot does not

Issue #128, the rows for `src/gui/widgets/spendable_profits.py` and
`src/gui/widgets/privacy_dot.py` in the conversion table in
[08-tabs.md](../../docs/manual/08-tabs.md). Files changed:
`src/gui/web/spendable_profits.js`, `src/gui/web/header_strip.js` and the two
table rows. No test file was written.

The Electron shell ran from `desktop/main.js` under the installed Electron
binary with a throwaway home, and the renderer was read over the Chrome
DevTools Protocol. The Qt strip was built by `HeaderStripMixin`
under `PYTHONWARNINGS=error` with `python -X dev -X faulthandler`.

The header strip answers `ACERVATOR_VARIANT`. `variant_surface.py` registers
`SPENDABLE_PROFITS` and `DASHBOARD_STAT_CARD`, and `_build_header_strip` asks
`surface_class` for each, so `ACERVATOR_VARIANT=qt` builds
`SpendableProfitsWidget` and `StatCard` and the default builds the React
classes. The measurement in the brief that only the History tab honours the
switch does not hold for this strip.

Pictures:

```
qt    <scratchpad>/u128/qt_header_strip_128.png
react <scratchpad>/u128/react_header_strip_128.png
```

Both sides ran on one fleet snapshot and one privacy state: wallet cash
4821.37, position value 17394.06, exchange realised 1263.48, exchange mature
402.19, 38 bots answering the venue, scrummed 92184.55, folded 88760.12,
realised profit and loss 3424.43, 1476 trades, 38 running, 7 lifetime errors,
two exchange sub-tabs, and `kpi.locked` and `counter.folded` masked with the
other seventeen fields revealed.

---

## 1 — Panels or components: what the running shell says

### 1.1 the error

No traceback. The shell was read before any edit. Eighteen panels registered
and neither module was among them.

```
registered = bot_live_settings, bot_swarm_tab, bot_visualizer, console_tab,
             header_strip, history_tab, indicator_panel, market_inspector,
             market_inspector_tab, market_inspector_topologies, native_chart,
             paper_trader_tab, proof_of_accumulation_tab, simulator_tab,
             status_log, system_status_tab, trade_charts_tab, trading_tab
kindOf('header_strip')                     chrome
reasonFor('spendable_profits')             spendable_profits.js registered no panel to draw
reasonFor('privacy_dot')                   privacy_dot.js registered no panel to draw
acervatorModules.missing()                 []
typeof acervatorProfits                    object
typeof acervatorDot                        object
```

Both modules load and neither registers.

### 1.2 reproduction

```
electron.exe <tree>/desktop --user-data-dir=<scratchpad> --remote-debugging-port=9351
ACERVATOR_BRIDGE_ARGV="-m src.core.desktop_bridge"
PYTHONWARNINGS=error
window.acervatorPanelHost.registered()
```

`ELECTRON_RUN_AS_NODE=1` is set in this session and is inherited by a child
process. With it set, `electron.exe` runs as plain Node, `require("electron")`
resolves to the npm package, and the shell dies on
`Cannot read properties of undefined (reading 'whenReady')`. The run clears it.

### 1.3 the cause

The two modules are not the same kind of thing, and the shell shows which is
which.

`spendable_profits.js` draws into a target element of its own. The strip
renders an empty div for it and reaches the module directly:

```javascript
  function SpendablePanel(props) {
    ...
    return element("div", panelProps, null);
  }

  function renderSpendable(target) {
    var api = global[SPENDABLE_API];
    ...
    return api.renderStrip(space);
  }
```

That is the shape the Live tab and the Charts tab were already corrected away
from. Both now draw their children through the panel host, and both say why in
the file:

`src/gui/web/trading_tab.js`

```javascript
  // `status_log.js` draws its own lines into the slot this tab keeps. The
  // panel host does the drawing, so a module that registers no panel is
  // named on the slot rather than leaving it blank.
```

`privacy_dot.js` has no target anywhere. `acervatorDot.Dot` is a React element
that `spendable_profits.js` and `dashboard_stat_card.js` render inside their
own trees, and `renderDot` has no caller in the tree. A registration would name
a panel the host can never draw into anything, and `mountAll` would build it a
host element of its own under `#panels`.

### 1.4 the correction

`spendable_profits.js` registers, on the terms `status_log.js`,
`indicator_panel.js` and `native_chart.js` use — a render, a loader and a load
error, and no bridge method, so the tab bar draws it no tab.

```javascript
  if (global.acervatorPanelHost) {
    global.acervatorPanelHost.register({
      render: renderStrip,
      load: loadProfits,
      loadError: loadError
    });
  }
```

`header_strip.js` draws it through the host and hands on the model the loader
answered with:

```javascript
  function renderSpendable(target, model) {
    var host = global.acervatorPanelHost;
    var space = spaceNamed(target, SPENDABLE);
    if (!host || space === null) {
      return null;
    }
    space.setAttribute(CHILD_ATTR, SPENDABLE_MODULE);
    return host.mount(SPENDABLE_MODULE, space, model) ? space : null;
  }
```

`privacy_dot.js` is unchanged. Its row records that the column does not apply.

### 1.5 the rerun

```
registered                                 19 names, spendable_profits among them
kindOf('spendable_profits')                screen
methodOf('spendable_profits')              null, so the bar gives it no tab
reasonFor('spendable_profits')             null
host.mount('spendable_profits', space)     true
faults()                                   []
data-panel-error on the page               absent
data-child-module in the strip             spendable_profits, then dashboard_stat_card
                                           and privacy_dot five times each
[data-panel="spendable_profits"]           none: no stray host was built
[data-panel="privacy_dot"]                 none
```

---

## 2 — The control on each answer

### 2.1 the registration is the draw path

The registration was taken out of `spendable_profits.js` and the same payload
driven again.

| | registered | registration removed |
| --- | --- | --- |
| panels registered | 19 | 18 |
| `host.mount` answered | true | false |
| markup in the space | 7,542 characters | 86 |
| the space reads | `SPENDABLE $4,821.37 …` | `Panel spendable_profits did not draw: spendable_profits.js registered no panel to draw` |
| column values | five | none |
| `faults()` | empty | one, naming the panel |
| page fault attribute | absent | `spendable_profits` |

```
<scratchpad>/u128/react_header_strip_128_control_registration.png
```

Before this change the same failure drew a blank box and recorded nothing.

### 2.2 the dot is a component

`window.acervatorDot` was removed at runtime and the same payload driven again.

| | privacy_dot.js loaded | removed |
| --- | --- | --- |
| `typeof acervatorDot` | object | undefined |
| pressable wrappers in the columns | 5 | 0 |
| hover style blocks | 5 | 0 |
| glyph spans | 5 | 5 |
| glyph text | ● ● ○ ● ● | ● ● ○ ● ● |
| elements marked `data-child-module="privacy_dot"` | 5 | 0 |
| panels registered | 19 | 19 |

The glyph stays because `header_strip.js` declares it and
`spendable_profits.js` falls back to it. What falls away is the press wrapper
and its hover rule, composed into another module's tree. Nothing named a panel
failure, because the host never drew one.

---

## 3 — The strip's slots did not share the row the way Qt shares it

### 3.1 the error

The five counter cards drew at five widths where Qt draws them equal.

```
react   scrummed 152  folded 118  trades 117  bots 108  errors 114
qt      153 153 153 153 153
```

### 3.2 reproduction

Both strips were driven with the same payload and the width of every slot read
back, from `getBoundingClientRect` on the page and `QWidget.width` in Qt.

### 3.3 the cause

`header_strip.js` wrote the Qt stretch as a CSS `flex-grow` and nothing else. A
`QHBoxLayout` stretch divides the whole row in the ratio; `flex-grow` divides
only the space left after every item has taken its content width, so a wider
label made a wider card.

### 3.4 the correction

One helper, used by the spendable panel, the counter card and the mode button.

```javascript
  function withStretch(style, stretch) {
    if (stretch !== undefined) {
      style.flexGrow = stretch;
      style.flexBasis = 0;
    }
    return style;
  }
```

A flex item keeps `min-width: auto`, so a slot still refuses to shrink below
its own content, which is what Qt's minimum size hint does.

### 3.5 the rerun

```
react   five cards 148 each, spendable panel 480 of a 1386 row  (34.6 per cent)
qt      five cards 153 each, spendable panel 502 of a 1444 row  (34.8 per cent)
```

---

## The two pictures

Both were driven with the fleet snapshot and privacy state named above.

| # | item | Qt picture | React picture |
| --- | --- | --- | --- |
| 1 | strip contents, left to right | spendable panel, five counter cards, mode button | the same seven, same order |
| 2 | SPENDABLE label | `SPENDABLE`, `#00ffcc`, 10px, weight 700 | the same, `rgb(0, 255, 204)` |
| 3 | SPENDABLE label tooltip | `Cash balance pulled from the exchange, across the bots sharing one wallet.` | the same |
| 4 | SPENDABLE figure | `$4,821.37`, `#00ff88`, 16px bold | the same, `rgb(0, 255, 136)` |
| 5 | REALISED | `REALISED` `#888`, `$1,263.48` `#cccccc` | the same, `rgb(136,136,136)` and `rgb(204,204,204)` |
| 6 | LOCKED, masked | `LOCKED`, `****` | the same |
| 7 | MATURE | `MATURE`, `$402.19` | the same |
| 8 | EXCH | `EXCH`, `2` | the same |
| 9 | column separators | four `|`, `#2a2a3a`, 24px | four `|`, `rgb(42, 42, 58)`, 24px |
| 10 | column dot glyphs | ● ● ○ ● ● | the same five |
| 11 | column dot colour | `#00ffee`, 14px | `rgb(0, 255, 238)`, 14px |
| 12 | column dot position | under its own value, centred | the same |
| 13 | column dot tooltips | `kpi.spendable: REVEALED. Click to mask.` and its four siblings | the same five |
| 14 | column widths | 74, 74, 43, 60, 29 | 73, 73, 43, 60, 29 |
| 15 | counter labels | Scrummed, Folded, Trades, Bots, Errors, `#7a7d99`, 10px | the same five, `rgb(122, 125, 153)` |
| 16 | counter values | `$92,184.55`, `****`, `1476`, `38`, `7`, `#00ffcc`, 14px bold | the same five, `rgb(0, 255, 204)` |
| 17 | counter dots | ● ○ ● ● ●, `#00ffee` | the same, `rgb(0, 255, 238)` |
| 18 | counter tooltips | five, each naming what the card counts | the same five, word for word |
| 19 | Errors card is pressable | yes | `data-clickable="true"` |
| 20 | counter widths | 153 each | 148 each |
| 21 | spendable panel share of the row | 34.8 per cent | 34.6 per cent |
| 22 | spendable panel ground | green gradient, `rgba(0,255,180,80)` edge, 4px radius | the same |
| 23 | mode button text and tooltip | `Crypto Mode`, `Toggle between Crypto and Stock trading layers` | the same |
| 24 | mode button skin | `#00ccaa` on `rgba(0,200,160,40)`, `rgba(0,200,160,100)` edge, 4px radius, 11px bold | `rgb(0,204,170)` on `rgba(0,200,160,0.157)`, `rgba(0,200,160,0.392)` edge, 4px, 11px 700 |
| 25 | mode button pressed state | not checked | `aria-pressed="false"` |
| 26 | P/L card | present, hidden, `$+3,424.4300` | present, `hidden`, `$+3,424.4300` |
| 27 | counter card edge | a one pixel panel edge | none |

Twenty-six of twenty-seven match. No item matched because both sides were
empty: every figure, label, glyph and tooltip carried a value on both sides.

Item 26 is a card neither picture shows. It is in both documents, hidden on
both, carrying the same text on both, so it is a match on the element and not
on anything drawn.

Item 27 is the one difference. `dashboard_stat_card_surface.FRAME_STYLE` is the
empty string and the `StyledPanel` frame shape reaches the page as an attribute
no rule reads, so Qt's style engine paints an edge the page does not. That is
`src/gui/widgets/dashboard_stat_card.py`, a row of its own.

Item 14 differs by one pixel on the two widest labels, which is Chromium and Qt
rounding the same text metric.

## What the strip still cannot draw

The shell asks `header.strip` with an empty request, so the fleet the strip
reports is an empty one: every counter zero and every column an em dash. The
figures above reached the page because the run pushed the payload in. Neither
`header_strip.js` nor `spendable_profits.js` can supply a fleet, and neither
should compute one — what is missing is the aggregate in the shell's own
request.

Each privacy dot on the page draws with the default cursor where Qt gives it a
pointing hand. `dot_view` publishes `cursor_shape`, and the three surfaces that
build a dot for a strip column, a counter card and the strip itself each cut it
away.

```python
_DOT_FIELDS = ("field_id", "masked", "text", "tooltip", "style_sheet")
```

## Where this page carries the dated block

The header strip belongs to `## Main Window`, which sits above every dated
block on the page, so a block nested there would fail `docs_archetype` rule
DOC012: it walks every dated heading against one running maximum. The true time
of this work is 07:23, earlier than the two blocks that close the page, so the
block sits between `06:35` and `22:12`, which is where its own stamp belongs
and where the walk stays green.

```
576   2026-09-08 23:40
605   2026-09-09 01:20
648   2026-09-09 03:05
703   2026-09-09 06:35
1602  2026-09-09 07:23   this block
1671  2026-09-09 22:12
1738  2026-09-09 23:05
```
