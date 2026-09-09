# 2026-09-09 — The header cards and the Scrumming bot table: both are components

Issue #128, the rows for `src/gui/widgets/dashboard_stat_card.py` and
`src/gui/widgets/bot_status_table.py` in the conversion table in
[08-tabs.md](../../docs/manual/08-tabs.md). Files changed:
`src/gui/main_tabs/dashboard_stat_card_surface.py` and the two table rows.
No test file was written.

`main.py` was not launched. `main.py:812` builds an `InstanceGuard` and
`take_ownership` writes into `~/.acervator`, which belongs to the process
trading real money on this machine. The Qt side was reached the way the running
program reaches it: `HeaderStripMixin._build_header_strip` under
`ACERVATOR_VARIANT=qt`, with `ThemeManager.apply_theme("cyberpunk_dark", app)`,
`PYTHONWARNINGS=error` and `python -X dev -X faulthandler`. The React side ran
in the Electron shell from `desktop/main.js` under the installed Electron
binary with a throwaway home, read over the Chrome DevTools Protocol.

Pictures:

```
qt     <scratchpad>/u128cards/u128_cards_table_qt.png
react  <scratchpad>/u128cards/u128_cards_table_react.png
```

Both sides ran on one fleet snapshot and one privacy state: scrummed 92184.55,
folded 88760.12, 1476 trades, 38 running bots, 7 lifetime errors, realised
profit and loss 3424.43, wallet cash 4821.37, position value 17394.06, exchange
realised 1263.48, exchange mature 402.19, 38 bots answering the venue, two
configured exchanges, three Scrumming bots on `coinbase`, and every privacy
field revealed.

**Nothing is written into the page.** The shell fetched every figure over the
bridge. The bridge was `build_registry(live)` with `live.bot_manager` answering
`get_aggregate_stats` and `list_bots_by_exchange`, and `live.settings_manager`
answering `list_exchanges`. Section 5 breaks each of those two sources and shows
the figures fall away.

The fleet is a stand-in, not the operator's own. `bot_state.json` belongs to a
process trading real money, so it is neither copied nor read here. What is
proved is the path, not whose bots travel it.

---

## 1 — Panels or components: what the running shell says

### 1.1 the error

No traceback. The shell was read before any edit. Nineteen panels registered and
neither module was among them.

```
registered = bot_live_settings, bot_swarm_tab, bot_visualizer, console_tab,
             header_strip, history_tab, indicator_panel, market_inspector,
             market_inspector_tab, market_inspector_topologies, native_chart,
             paper_trader_tab, proof_of_accumulation_tab, simulator_tab,
             spendable_profits, status_log, system_status_tab,
             trade_charts_tab, trading_tab
reasonFor('dashboard_stat_card')   dashboard_stat_card.js registered no panel to draw
reasonFor('bot_status_table')      bot_status_table.js registered no panel to draw
acervatorModuleErrors.names()      []
typeof acervatorStatCard           object
typeof acervatorBotTable           object
faults()                           []
```

Both modules load, both draw, and neither registers.

### 1.2 reproduction

```
electron.exe <tree>/desktop --user-data-dir=<scratchpad> --remote-debugging-port=9361
ACERVATOR_BRIDGE_ARGV=<scratchpad>/u128cards/live_bridge.py
PYTHONWARNINGS=error
window.acervatorTabBar.select('trading_tab')
window.acervatorPanelHost.registered()
```

`ELECTRON_RUN_AS_NODE` is set in this session and is inherited by a child
process. With it set, `electron.exe` runs as plain Node and the shell dies on
`whenReady` of an undefined `app`. The run clears it.

### 1.3 the cause

Neither module can compose its own request, and each is drawn several times
under one name.

`dashboard_stat_card.js` is drawn into five spaces at once. The strip builds one
request per counter and asks the bridge itself:

`src/gui/web/header_strip.js` — `mountCounters`

```javascript
      chain = chain
        .then(function () {
          return global.acervator.call(api.method, cardRequest(card));
        })
        .then(function (built) {
          space.setAttribute(CHILD_ATTR, STAT_CARD_MODULE);
          api.renderCard(space, built);
```

`cardRequest` carries the counter's `label`, `value`, `field_id` and
`clickable`. The card has none of those without the strip.

`bot_status_table.js` holds one payload per exchange and one root per host, and
the exchange screen names which exchange each host is for:

`src/gui/web/bot_status_table.js`

```javascript
  // The payload this module holds for one exchange, or null for none.
  function modelFor(exchangeId) {
    return owns(models, String(exchangeId)) ? models[String(exchangeId)] : null;
  }
```

`panel_host.mount` keeps `hosts[name] = target`, one target per name, and
`panel_host.open` composes one request from `spec.request()`. One registration
cannot express five cards with five requests, nor one table per exchange.

That is the shape `privacy_dot.js` already has and `spendable_profits.js` does
not: `spendable_profits` is one panel, asked with `{}`, answering for the whole
fleet. These two are drawn by a registered parent, once per counter and once per
exchange, from a request only that parent holds.

### 1.4 the correction

No registration was added. Both rows take the `-` mark this table already uses
for a column that does not apply, the mark `privacy_dot` took for the same
reason.

### 1.5 the rerun

```
registered                              19, unchanged
data-child-module="dashboard_stat_card" 5 spaces, one per counter
data-child-module="bot_status_table"    1 space, on the exchange screen
acervatorBotTable.drawnExchanges()      ["coinbase"]
[data-panel="dashboard_stat_card"]      none: no stray host was built
[data-panel="bot_status_table"]         none
faults()                                []
data-panel-error on the page            absent
```

### 1.6 the control on that answer

Both modules were registered at runtime on the terms `spendable_profits.js`
uses — a render, a loader and a load error — and opened through the panel host
into a host element of its own.

| | drawn by its parent | opened as a panel |
| --- | --- | --- |
| panels registered | 19 | 21 |
| `open` returned | — | `true` for both |
| the card's label | Scrummed, Folded, Trades, Bots, Errors | empty |
| the card's amount | five figures | `---`, the default |
| the table's rows | 3 | 0 |
| the table's headers | ten | the same ten |
| `faults()` | [] | [] |
| the strip's five counters | five figures | the same five figures |

```
<scratchpad>/u128cards/u128_control_registration.png
```

The registration succeeds and records no fault; what the host cannot supply is
the request. The strip's counters keep their figures in both arms, which is the
positive control: the run still reached the bridge and still drew a strip.

---

## 2 — The card drew no edge

### 2.1 the error

```
qt      QFrame.lineWidth()  1, on all five cards; frameWidth() 13
react   [data-part="card"]  border 0px none, border-radius 0px, padding 0px
```

### 2.2 reproduction

Both cards were driven on the same aggregate and the skin read from
`QFrame.frameWidth` and the applied style sheet in Qt, and from
`getComputedStyle` on the page.

### 2.3 the cause

Qt paints the card from the theme, not from the widget:

`src/gui/theme_engine.py` — `generate_qss`, as the running application applied it

```
QFrame[frameShape="6"] {
    background-color: #16162a;
    border: 1px solid #7a7a9c;
    border-radius: 8px;
    padding: 12px;
}
```

`dashboard_stat_card.js` reads that rule through `themeFrameBody`, which asks
`acervatorThemes.current()`. Nothing in the shell selects a theme, so
`current()` answers null, `themeFrameBody` answers undefined, and `paintRules`
writes no card rule. `FRAME_STYLE` was the empty string, so the card carried no
skin of its own either and the page drew nothing.

Measured in the shell: `acervatorThemes.isLoaded()` false and `current()` null
before any load; after `acervatorLoadThemes()`, `isLoaded()` true, five theme
names held, `current()` still null and `themeFrameBody()` still undefined.

### 2.4 the correction

`dashboard_stat_card_surface.FRAME_STYLE` carries the frame skin, built from
`design_system` tokens so the page holds no colour of its own.

```python
FRAME_STYLE = (
    "border-style: solid; "
    f"border-width: {FRAME_LINE_WIDTH_PX}px; "
    f"border-color: {ds.OUTLINE}; "
    f"border-radius: {ds.RADIUS_SM}px; "
    f"padding: {ds.SPACE_CARD_PAD}px;"
)
```

`ds.OUTLINE` is `#7a7a9c`, the same value the theme's `border_primary` carries;
`ds.RADIUS_SM` is 8 and `ds.SPACE_CARD_PAD` is 12. `border-color` reaches the
page through `shared_widgets.variableFor` as `var(--OUTLINE, #7a7a9c)`, and
`--OUTLINE` reads `#7a7a9c` off the root element.

### 2.5 the rerun

```
react   border 0.8px solid rgb(122, 122, 156), radius 8px, padding 12px
qt      1px solid #7a7a9c, radius 8px, padding 12px
```

`devicePixelRatio` on the shell is 1.25, so Chromium reports one device pixel of
border as 0.8 CSS pixels. It is the same one-pixel edge.

---

## 3 — Every counter dot drew with the ordinary pointer

### 3.1 the error

```
qt      PrivacyDot.cursor().shape()   PointingHandCursor, on all five dots
react   the dot's own element         cursor default on four, pointer on Errors
```

The Errors dot read pointer because its card is clickable and the cursor came
down from the card, not from the dot.

### 3.2 reproduction

Both strips were driven on one payload and the cursor read from
`QWidget.cursor().shape()` and from `getComputedStyle`.

### 3.3 the cause

`privacy_dot_surface.dot_view` publishes `flat`, `focus_policy` and
`cursor_shape`, and the card cut a dot down to five fields that left all three
out.

```python
_DOT_FIELDS = ("field_id", "masked", "text", "tooltip", "style_sheet")
```

`privacy_dot.js` reads `cursor_shape` and had nothing to read.

### 3.4 the correction

`_DOT_FIELDS` carries the three fields, which is what
`spendable_profits_surface` already does for the strip's column dots.

### 3.5 the rerun

```
react counter dots   pointer on all five
react counter dots   role="button" and data-cursor-shape="PointingHandCursor"
qt counter dots      PointingHandCursor on all five
```

---

## 4 — Both variants of the card

`variant_surface` registers `DASHBOARD_STAT_CARD`, so `_build_header_strip` asks
`surface_class` for it and the switch is honoured.

```
ACERVATOR_VARIANT=qt      type(_stat_scrummed).__name__   StatCard
ACERVATOR_VARIANT=react   type(_stat_scrummed).__name__   StatCardReact
                          page_ready                      True
                          label read off the page          Scrummed
                          amount read off the page         $92,184.55
                          frame style sheet on the model   the five declarations above
                          dot fields on the model          align, cursor_shape, field_id,
                                                           flat, focus_policy, masked,
                                                           style_sheet, text, tooltip
```

```
<scratchpad>/u128cards/react_variant_cards_128.png
```

`variant_surface` registers no name for the Scrumming bot table, so
`ACERVATOR_VARIANT` selects nothing for it. Its Qt side was reached by building
`BotStatusTable` directly, which is what `ExchangeTab` does.

---

## 5 — The controls on the two sources

### 5.1 the aggregate

`get_aggregate_stats` was made to answer `None` and the shell opened again with
nothing pushed in.

| | the aggregate reads | the aggregate broken |
| --- | --- | --- |
| Scrummed | `$92,184.55` | `$0.00` |
| Folded | `$88,760.12` | `$0.00` |
| Trades | `1476` | `0` |
| Bots | `38` | `0` |
| Errors | `7` | `0` |
| the card edge | 0.8px solid rgb(122,122,156) | the same |
| the dot cursor | pointer on five | the same |
| the table's rows | 3 | 3 |

```
<scratchpad>/u128cards/u128_control_aggregate.png
```

### 5.2 the bot list

`list_bots_by_exchange` was made to answer an empty list.

| | the list reads | the list broken |
| --- | --- | --- |
| table rows | 3 | 0 |
| table markup | 14,802 characters | 4,309 |
| table headers | ten | the same ten |
| the five counters | five figures | the same five figures |

```
<scratchpad>/u128cards/u128_control_bots.png
```

Each arm keeps the other side drawing, which is the positive control on both.

### 5.3 the skin and the cursor

One counter was re-drawn from the same fetched payload with `frame.style_sheet`
blanked and `dot.cursor_shape` deleted, then re-drawn from the payload again.

| | the payload as served | the two fields taken out | restored |
| --- | --- | --- | --- |
| border | 0.8px solid rgb(122,122,156) | 0px none | 0.8px solid rgb(122,122,156) |
| border-radius | 8px | 0px | 8px |
| padding | 12px | 0px | 12px |
| dot cursor | pointer | default | pointer |
| the amount | `$92,184.55` | `$92,184.55` | `$92,184.55` |

```
<scratchpad>/u128cards/u128_control_edge.png
```

The amount is unchanged in all three arms, so the instrument was reading a card
that still drew.

---

## The two pictures

Both were read on the fleet snapshot and privacy state named above, with nothing
pushed into the page.

| # | item | Qt picture | React picture |
| --- | --- | --- | --- |
| 1 | counter order, left to right | Scrummed, Folded, Trades, Bots, Errors | the same five, same order |
| 2 | counter labels | `#7a7d99`, 10px | `rgb(122, 125, 153)`, 10px |
| 3 | counter amounts | `$92,184.55` `$88,760.12` `1476` `38` `7` | the same five |
| 4 | counter amount colour | `#00ffcc`, 14px bold | `rgb(0, 255, 204)`, 14px, weight 700 |
| 5 | counter tooltips | five, each naming what the card counts | the same five, word for word |
| 6 | Errors card is pressable | cursor PointingHandCursor | `data-clickable="true"`, cursor pointer |
| 7 | counter dot glyphs | ● ● ● ● ● | the same five |
| 8 | counter dot colour | `#00ffee`, 14px | `rgb(0, 255, 238)`, 14px |
| 9 | counter dot tooltips | `counter.scrummed: REVEALED. Click to mask.` and its four siblings | the same five |
| 10 | counter dot cursor | PointingHandCursor on all five | pointer on all five |
| 11 | card edge | 1px solid `#7a7a9c` | one device pixel solid `rgb(122, 122, 156)` |
| 12 | card corner | 8px radius | 8px |
| 13 | card padding | 12px | 12px |
| 14 | P/L card | present, hidden, `$+3,424.4300` | present, hidden, `$+3,424.4300` |
| 15 | table column headers | ● Bot ID, ● Symbol, ● Current Position Value, ● Trades, ● Target, ● Target BTC, ● Target ETH, ● Ammo, ● Fire, and one blank | the same ten, same order |
| 16 | table header tooltips | ten, each ending with the field id and `Click this header to toggle.` | the same ten |
| 17 | table row order | bot-btc-0001, bot-eth-0002, bot-sol-0003 | the same three, same order |
| 18 | Bot ID cells | `bot-btc-0001` `bot-eth-0002` `bot-sol-0003` | the same three |
| 19 | Bot ID colours | `#00ff88`, `#ffaa00`, `#ff3366` | `rgb(0,255,136)`, `rgb(255,170,0)`, `rgb(255,51,102)` |
| 20 | Symbol cells | BTC/USD, ETH/USD, SOL/USD | the same three |
| 21 | Trades cells | 214, 97, 41 | the same three |
| 22 | Target cells | `$2,500.0000`, `$1,800.0000`, `$900.0000` | the same three |
| 23 | Target BTC cells | empty, `pending`, `pending` | the same three |
| 24 | Target ETH cells | `pending`, empty, `pending` | the same three |
| 25 | Ammo cells | `$211.4544`, `$137.3357`, `$143.7500` | the same three |
| 26 | Fire and Detail buttons | Fire, Detail on all three rows | the same, on all three rows |
| 27 | card ground | `#16162a` | transparent |
| 28 | card fills its space | the card is the layout cell, 153 to 154 wide | the space is 141 on all five, the card 114, 114, 78, 69, 75 |
| 29 | Current Position Value cells | empty on all three rows | empty on all three rows |

Item 29 matches because both sides are empty. No fresh exchange price exists for
these three pairs, so `_compose_position_value_cell` blanks the cell on both
hosts. It proves the blank, and nothing about a figure.

Item 14 is a card neither picture shows. It is in both documents, hidden on
both, carrying the same text on both.

Items 27 and 28 are the two differences.

**Item 27.** No `design_system` token carries `#16162a`; the nearest,
`SURFACE_1`, is `#141420`. The value belongs to the theme's `bg_card`, and
`src/gui/design_system.py` is outside this unit's files, so no token was added
and no near value was painted in its place.

**Item 28.** The counter space is 141 pixels on all five and the card inside it
takes its content width. The space is drawn by `header_strip.js` from
`header_strip_surface.CARD_LAYOUT`, and it centred its child before this change
too — the card measured 88 in a 141 space on `origin/current`. Both files belong
to the header strip's own row.

## What is still owed

A run over the operator's own saved fleet. That file belongs to a process
trading real money. The bound path is proved; the bots on it are not his.
