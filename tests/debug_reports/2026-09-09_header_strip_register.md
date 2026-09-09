# 2026-09-09 — Header strip: the spendable panel registers, the privacy dot does not

Issue #128, the rows for `src/gui/widgets/spendable_profits.py` and
`src/gui/widgets/privacy_dot.py` in the conversion table in
[08-tabs.md](../../docs/manual/08-tabs.md). Files changed:
`src/gui/web/spendable_profits.js`, `src/gui/web/header_strip.js`,
`src/gui/main_tabs/header_strip_surface.py`,
`src/gui/main_tabs/spendable_profits_surface.py`,
`src/core/desktop_bridge.py` and the two table rows. No test file was written.

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
two configured exchanges, and `kpi.locked` and `counter.folded` masked with the
other seventeen fields revealed.

**Nothing is written into the page.** The snapshot is held by the bot manager
the bridge is bound to, and the shell fetches every figure over the bridge. The
first version of this report took its picture match on values pushed into the
renderer by hand; section 4 is why that proved nothing, and every reading below
is from a fetched draw.

The manager is `main_window_surface.FleetSource`, the class the main-window
model already uses to stand for the manager, carrying that one aggregate.
`BotManager.restore_bots_from_state` against the operator's own saved fleet
would be the stronger arm and this run cannot take it: the state file is the
live tree of a process trading real money, so it is neither copied nor read
here. What is proved is the path, not whose bots travel it.

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

The registration was taken out of `spendable_profits.js` and the shell opened
again, with nothing pushed in.

| | registered | registration removed |
| --- | --- | --- |
| panels registered | 19 | 18 |
| markup in the space | 8,087 characters | 86 |
| the space reads | `SPENDABLE $4,821.37 …` | `Panel spendable_profits did not draw: spendable_profits.js registered no panel to draw` |
| column values | five | none |
| `faults()` | empty | one, naming the panel |
| page fault attribute | absent | `spendable_profits` |
| the five counter cards | drawn, with their figures | drawn, with their figures |

The counters keep their values in both arms, which is the positive control on
the instrument: the run still reached the bridge and still drew a strip, so the
empty box is the registration and not a dead page.

```
<scratchpad>/u128/react_header_strip_128_control_registration.png
```

Before this change the same failure drew a blank box and recorded nothing.

### 2.2 the dot is a component

`window.acervatorDot` was removed at runtime and the panel reopened through the
host, which refetches over the bridge with nothing pushed in.

| | privacy_dot.js loaded | removed |
| --- | --- | --- |
| `typeof acervatorDot` | object | undefined |
| pressable wrappers in the columns | 5 | 0 |
| hover style blocks | 5 | 0 |
| dot cursor | pointer on all five | none, the wrapper is gone |
| glyph spans | 5 | 5 |
| glyph text | ● ● ○ ● ● | ● ● ○ ● ● |
| column values | five, fetched | the same five, fetched |
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

## 4 — The strip drew nothing the shell had fetched

### 4.1 the error

The strip registered, drew, and reported an empty fleet on every figure. The
run that produced the first picture match had pushed the values into the
renderer itself, so the match measured a page being handed values by hand.

```
column values   —  —  —  —  —
counters        Scrummed $0.00  Folded ****  Trades 0  Bots 0  Errors 0
P/L             $+0.0000
```

### 4.2 reproduction

The shell was opened and read with nothing pushed in.

```
electron.exe <tree>/desktop --user-data-dir=<scratchpad> --remote-debugging-port=9351
ACERVATOR_BRIDGE_ARGV=<scratchpad>/u128/live_bridge.py
PYTHONWARNINGS=error
window.acervatorPanelHost.registered()  and the strip read out of the document
```

### 4.3 the cause

`panel_host.requestOf` asks a panel that declares no `request` with `{}`, and
`build_registry` served `header.strip` and `spendable_profits.state` from the
unbound `view_model`. Both then answered for a fleet nobody had named.

```python
        header_strip_surface.METHOD: header_strip_surface.view_model,
        ...
        spendable_profits_surface.METHOD: spendable_profits_surface.view_model,
```

Every surface that already draws live figures answers this the same way, with a
`bind_live` the registry installs when the running program serves the bridge.
Neither header-strip surface had one.

### 4.4 the correction

`header_strip_surface` reads the aggregate off the bot manager the bridge is
bound to, and the exchange count off the settings manager. Neither is derived.

```python
def fleet_aggregate(live: Any) -> Optional[dict]:
    """``BotManager.get_aggregate_stats`` from ``live``, or None with no fleet."""
    manager = getattr(live, "bot_manager", None)
    reader = getattr(manager, "get_aggregate_stats", None)
    if not callable(reader):
        return None
    found = reader()
    return found if isinstance(found, dict) else None
```

`spendable_profits_surface` takes the same aggregate through
`header_strip_surface.profits_payload`, which is the one builder
`MainWindow._refresh_dashboard` already calls, so no second arithmetic exists
on either host. `build_registry` installs both handlers beside the six that
were already bound.

### 4.5 the rerun

With nothing pushed in:

```
SPENDABLE $4,821.37   REALISED $1,263.48   LOCKED ****   MATURE $402.19   EXCH 2
Scrummed $92,184.55   Folded ****   Trades 1476   Bots 38   Errors 7
P/L $+3,424.4300      Crypto Mode
registered 19, reasonFor('spendable_profits') null, faults []
```

`EXCH 2` is the length of the settings manager's exchange list, which is the
list the Qt window builds one sub-tab from.

### 4.6 the control on the source

The manager's `get_aggregate_stats` was made to answer `None`, and the shell
opened again with nothing pushed in.

| | the aggregate reads | the aggregate broken |
| --- | --- | --- |
| SPENDABLE | `$4,821.37` | `—` |
| REALISED | `$1,263.48` | `—` |
| LOCKED, masked | `****` | `—` |
| MATURE | `$402.19` | `—` |
| EXCH | `2` | `—` |
| Scrummed | `$92,184.55` | `$0.00` |
| Trades | `1476` | `0` |
| Bots | `38` | `0` |
| Errors | `7` | `0` |
| P/L | `$+3,424.4300` | `$+0.0000` |
| the panel itself | drawn, no fault | drawn, no fault |

```
<scratchpad>/u128/react_header_strip_128_control_aggregate.png
```

The panel keeps drawing and every value falls away, so the figures come from
the aggregate and from nowhere else.

---

## 5 — Every privacy dot drew with the ordinary pointer

### 5.1 the error

```
qt      PrivacyDot.cursor()  PointingHandCursor, on all five column dots
react   [data-part="dot"]    cursor: auto
```

### 5.2 reproduction

The two strips were driven on one payload and the cursor read from
`QWidget.cursor().shape()` and from `getComputedStyle`.

### 5.3 the cause

`privacy_dot_surface.dot_view` publishes `flat`, `focus_policy` and
`cursor_shape`, and three surfaces cut a dot down to five fields that leave all
three out.

```python
_DOT_FIELDS = ("field_id", "masked", "text", "tooltip", "style_sheet")
```

`privacy_dot.js` reads `cursor_shape` and had nothing to read.

### 5.4 the correction

The two surfaces that build a dot for this strip keep the three fields:
`spendable_profits_surface._DOT_FIELDS` carries them, and
`header_strip_surface.privacy_dot` reads them from `privacy_dot_surface` rather
than spelling them again. `dashboard_stat_card_surface` is the third and is
`src/gui/widgets/dashboard_stat_card.py`, its own row, and is left alone.

### 5.5 the rerun

```
react column dots   pointer, pointer, pointer, pointer, pointer
react column dots   role="button" on all five
qt column dots      PointingHandCursor on all five
react counter dots  default on four, pointer on the pressable Errors card
```

---

## The two pictures

Both were read on the fleet snapshot and privacy state named above, with
nothing pushed into the page.

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
| 13a | column dot cursor | `PointingHandCursor` on all five | `pointer` on all five |
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
| 28 | counter dot cursor | `PointingHandCursor` on all five | `default` on four, `pointer` on Errors |

Twenty-seven of twenty-nine match. Every figure on the React side was fetched
over the bridge with nothing pushed into the page. No item matched because both
sides were empty: every figure, label, glyph and tooltip carried a value on
both sides.

Item 26 is a card neither picture shows. It is in both documents, hidden on
both, carrying the same text on both, so it is a match on the element and not
on anything drawn.

Items 27 and 28 are the two differences and both are the counter card.
`dashboard_stat_card_surface.FRAME_STYLE` is the empty string and the
`StyledPanel` frame shape reaches the page as an attribute no rule reads, so
Qt's style engine paints an edge the page does not; and the same file's
`_DOT_FIELDS` cuts `cursor_shape` away, so its dot takes no pointing hand. That
is `src/gui/widgets/dashboard_stat_card.py`, a row of its own, and neither is
changed here.

Item 14 differs by one pixel on the two widest labels, which is Chromium and Qt
rounding the same text metric.

## What is still owed

`BotManager.restore_bots_from_state` over the operator's own saved fleet is the
arm this run could not take, because that file belongs to a process trading
real money. The bound path is proved; the bots on it are not the operator's.

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
