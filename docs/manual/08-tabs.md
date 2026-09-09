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

### 2026-09-09 07:23 - #128 - the header strip's spendable panel is a panel, its dot is not

The header strip is one registered panel that draws two other modules inside
itself. The shell mounts `header_strip` as chrome, above the tab bar and on
show for every tab. Inside it, the spendable panel and the five counter cards
each fill a space the strip leaves for them, and each of those spaces is a
mount of its own.

`src/gui/web/header_strip.js` — the spendable space, as the strip draws it

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

`spendable_profits.js` now registers, so the shell knows it by name and the
strip draws it the way the Live tab draws its Activity Log and the Charts tab
draws its chart. The registration names no bridge method, so the tab bar gives
it no tab. Nineteen panels register where eighteen did before.

The privacy dot is a different kind of thing. It has no space and no host: two
other modules render it as an element inside their own trees, so the panel host
never draws it and a registration would name a panel with nowhere to go. Its
Registers in Electron cell now reads `-`, the mark this table already uses for
a column that does not apply to a row.

`src/gui/web/spendable_profits.js` — where the dot comes from

```javascript
  function dotSpan() {
    var own = global.acervatorDot;
    if (own && own.Dot) {
      return own.Dot;
    }
    var api = global.acervatorHeader;
    return api && api.PrivacyDot ? api.PrivacyDot : null;
  }
```

Both builds were read on one fleet snapshot and one privacy state, with LOCKED
and Folded masked and every other field revealed. Nothing was written into the
page: the shell fetched every figure over the bridge. Every value, label,
glyph, colour and tooltip on the strip agrees between them.

The strip's slots now share the row the way the Qt layout shares it. A Qt
stretch divides the whole width; a CSS `flex-grow` divides only what is left
over, so the counters drew at five different widths. With a zero flex basis the
five cards measure 148 pixels each against Qt's 153, and the spendable panel
takes 34.6 per cent of the row against Qt's 34.8.

| Qt file | React module | Uses React | Bridge | Manifest | Registers in Electron | Ships in the build | RENDERS | Scope |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `src/gui/widgets/spendable_profits.py` | `spendable_profits.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/widgets/privacy_dot.py` | `privacy_dot.js` | yes | yes | yes | - | yes | yes | in scope |

The strip fetches its own figures. The shell asks for the strip with an empty
request, so both surfaces now read the fleet the bridge is bound to, the way
the History, Charts, Trading and Inspector surfaces already read theirs. The
aggregate is `BotManager.get_aggregate_stats`, the same call the Qt window's
own tick makes, and the exchange count is the length of
`SettingsManager.list_exchanges`, which is the list the window builds one
sub-tab from. Neither figure is derived in the surface or in the page.

`src/gui/main_tabs/header_strip_surface.py` — the request fills itself

```python
def live_view_model(params: dict, live: Any) -> dict:
    asked = dict(params or {})
    if asked.get(STATS_PARAM) is None:
        aggregate = fleet_aggregate(live)
        if aggregate is not None:
            asked[STATS_PARAM] = aggregate
```

The spendable columns take the same aggregate through
`header_strip_surface.profits_payload`, the one builder the Qt tick already
calls, so the two hosts read one snapshot and cannot disagree.

Each privacy dot in the strip's columns now carries the pointing hand the Qt
dot sets on itself. `privacy_dot_surface.dot_view` publishes `cursor_shape`,
and the two surfaces that build a dot for this strip now keep it.
`dashboard_stat_card_surface` still cuts it away, so the five counter dots
draw with the ordinary pointer; that card is its own row.

Qt draws a one pixel panel edge around each counter card where the page draws
none, because `dashboard_stat_card_surface.FRAME_STYLE` is empty and the
`StyledPanel` shape reaches the page as an attribute no rule reads. That is
the same row.

### 2026-09-09 08:42 - #128 - the counter cards and the bot table are components

The five counter cards and the Scrumming bot table are drawn inside a panel
that has already registered, and neither registers in its own right. The strip
leaves five spaces and builds a request for each one, carrying that counter's
caption, amount, privacy field and whether it is pressable. The bot table is
drawn once for the exchange the Trading tab is showing, from a payload the
module keeps under that exchange's own name.

`src/gui/web/header_strip.js` — one request per counter

```javascript
  function cardRequest(card) {
    var asked = {};
    asked[CARD_LABEL_PARAM] = text(card[LABEL]);
    asked[CARD_VALUE_PARAM] = text(card[TEXT]);
    if (text(card[FIELD_ID]) !== undefined) {
      asked[CARD_FIELD_ID_PARAM] = text(card[FIELD_ID]);
    }
    asked[CARD_CLICKABLE_PARAM] = card[CLICKABLE] === true;
    return asked;
  }
```

The panel host keeps one host element per panel name and asks each panel with
one request of its own. Registering either module was driven in the running
shell to see what it would give: the card drew an empty caption and the default
amount, and the table drew its ten headers over no rows, each into a host of its
own under the panel area, while the strip's five counters kept their figures.
Both cells now read `-`, the mark this table already uses for a column that does
not apply to a row, and the mark the privacy dot took for the same reason.

Each counter card now draws the one pixel edge, the rounded corner and the
padding that Qt paints around it. Qt takes all three from the theme rule for a
framed panel; the shell selects no theme, so the page had nothing to read and
drew a plain box. The card's own skin carries them, built from the design
tokens rather than from a colour written into the page.

`src/gui/main_tabs/dashboard_stat_card_surface.py` — the card's skin

```python
FRAME_STYLE = (
    "border-style: solid; "
    f"border-width: {FRAME_LINE_WIDTH_PX}px; "
    f"border-color: {ds.OUTLINE}; "
    f"border-radius: {ds.RADIUS_SM}px; "
    f"padding: {ds.SPACE_CARD_PAD}px;"
)
```

The five counter dots now carry the pointing hand as well. The card cut its dot
down to five fields and left out the cursor the dot publishes; it keeps all
eight now, which is what the spendable columns already do.

Both builds were read on one fleet snapshot with every field revealed. Nothing
was written into the page: the shell fetched the aggregate and the bot list over
the bridge, and breaking each source in turn emptied the figures it feeds and
left the other side drawing. Every label, amount, colour, glyph, tooltip, column
header, row order and cell text agrees between the two.

Two differences remain, and both belong to other rows. Qt fills each card with
the theme's card ground, which no design token carries. And the counter space is
141 pixels wide on all five while the card inside takes its content width, which
is how the strip has placed its counters since before this change.

| Qt file | React module | Uses React | Bridge | Manifest | Registers in Electron | Ships in the build | RENDERS | Scope |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `src/gui/widgets/dashboard_stat_card.py` | `dashboard_stat_card.js` | yes | yes | yes | - | yes | yes | in scope |
| `src/gui/widgets/bot_status_table.py` | `bot_status_table.js` | yes | yes | yes | - | yes | yes | in scope |

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

### 2026-09-09 09:42 - #128 - the HTF Signals and Opposing Pairs tables come out

Neither screen drew the two tables. The Qt tab built both group boxes and put
neither into a layout, so no table ever reached the window. In the running
shell, the React screen drew no table part at all, while its payload carried
six signal columns and seven pair columns.

`src/gui/market_inspector.py` — `_fill_pair_rows`

```python
def _fill_pair_rows(self, pairs: list) -> None:
    """Hold the opposing pairs the Opposing Trades stepper draws."""
    self._pairs = list(pairs)
    self._render_empty_notes()
```

The screen holds neither table by design. The six-zone layout moved HTF Signals
into the reserved Phantom Bot zone, and it hands each opposing pair to the
Opposing Trades stepper, one entry at a time. Both sides now drop the renderer,
the column sets and the two empty sentences, and the tab keeps only the rows the
zones read.

Nothing on the screen moved. The Qt picture and the React picture each match
byte for byte before and after the change, and the drawn markup of the panel
matches at 21,194 characters.

The earlier comparison that closed these two rows read its table items out of
the payload. `signalRow` and `pairRow` handed back cells from the model, which
agreed on both sides whatever the page drew. This change drops both. The run is
in [2026-09-09_market_inspector_tables.md](../../tests/debug_reports/2026-09-09_market_inspector_tables.md).

### 2026-09-09 23:05 - #128 - the Electron shell draws the Inspector tab and its proposals pane

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

The check boxes on the tab drew as the browser's own control, white and 13
pixels, where Qt paints an 18 pixel box with a `#7a7a9c` edge on `#0e0e1a`.
That ground was in no token, so the table gained one under the name of the role
it fills, and the stylesheet names the token rather than the value.

`src/gui/main_tabs/design_system_surface.py` — the check-box ground

```python
SURFACE_INPUT = "#0e0e1a"
```

Both screens were driven on one payload of 54 markets, 300 daily candles each
and three ranked proposals. Twenty-seven of twenty-seven picture items match,
so rows 878 and 879 read `yes` under Registers in Electron. The Opposing Pairs
rows match at nothing on either side, so that item proves the column set and
not the rows. The run is in
[2026-09-09_market_inspector_register.md](../../tests/debug_reports/2026-09-09_market_inspector_register.md).

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

## Live Tab

The Live tab is where the bots trade real money on a real exchange. The
exchange connections fill the left, the Indicator Voting Panel fills the right,
and the Activity Log and the API Interaction Log close the foot.

The tab is now called Live. It sits third on the bar, straight after Paper, on
the gold ground with red text.

### 2026-09-09 06:35 - #128 - the Live tab's two widgets register a panel

The Indicator Voting Panel and the Activity Log now register with the shell's
panel host, and the Live tab draws both through it. Before the change the shell
listed sixteen registered panels and named these two as modules that draw
nothing; it lists eighteen now and names neither.

`src/gui/web/status_log.js` — what each of the two modules adds

```javascript
  if (global.acervatorPanelHost) {
    global.acervatorPanelHost.register({
      render: renderLog,
      load: loadLog,
      loadError: loadError
    });
  }
```

Neither registration names a bridge method, so the tab bar gives neither a tab
of its own. The Live tab keeps a slot for each and hands the slot to the host,
which is how the Charts tab already draws the price chart.

`src/gui/web/trading_tab.js` — the Live tab's slot for the Activity Log

```javascript
    slot.setAttribute(CHILD_ATTR, STATUS_LOG_MODULE);
    return host.mount(STATUS_LOG_MODULE, slot, model) ? slot : null;
```

The host is the draw path now, not a second name for it. With both
registrations taken out and the same reading driven in, each slot fell from
43,264 and 4,532 characters of markup to 82 and 72, and each carried the
sentence naming the panel that did not draw.

Both builds were driven with one reading: 180 daily BTC/USD candles from
CoinGecko through the voting engine, at 15m, 1h and 1d, and eight Activity Log
messages covering a placed, a filled and a sent trade, a wire flow, a wire
stack, a warning and an error. The Qt tab was built at the size the shell gives
the React tab, 1386 by 708.

The twelve indicator columns carry the same name, direction and bar in both.
Each bar fills its share of a 70-pixel plot.

```
column  direction  confidence  Qt height  React height
BB      NEUTRAL    0.000       2.00       2.00
VTX     BEARISH    0.328       22.96      22.69
MACD    BEARISH    0.150       10.50      10.38
SRsi    BEARISH    0.200       14.00      13.84
Ichi    BEARISH    0.210       14.70      14.53
Vol     NEUTRAL    0.000       2.00       2.00
Sling   NEUTRAL    0.000       2.00       2.00
ADX     BEARISH    0.267       18.69      18.48
STrd    BULLISH    0.261       18.27      18.05
ZSc     NEUTRAL    0.000       2.00       2.00
KER     NEUTRAL    0.000       2.00       2.00
RSI     NEUTRAL    0.000       2.00       2.00
```

Net, Comp and Conf stand in the last three of the ten columns in both, take the
same three directions, and run from the ceiling of the top row of bars to the
floor of the bottom row. Only their bases carry a label, in a strip 22 pixels
deep under that floor.

No horizontal line crosses the three. Every element in the React panel was read
for a top border, a bottom border or a background gradient: ninety-three carry
one, and every box ends at or before 1185.93, where the Net column starts. The
1 pixel each indicator column carries is that column's own base, which Qt
paints as a line from the left margin to the x of the Net column. The dotted
increments sit on those same cells and on no other.

```
                Qt                       React
ceiling         171                       267.2
floor           428                       523.2
label strip     428 to 450                523.2 to 545.2
columns         8, 9, 10 of 10            8, 9, 10 of 10
rules end at    437, the Net column       1185.9, the Net column
```

The Activity Log draws the same eight lines in the same order with the same
text. Each line takes the colour of its kind, and a trade line is raised to 14
pixels and bold.

```
line                          colour            size  weight
Bot btc_core started          rgb(0,255,204)    12    normal
SCRUM PLACED                  rgb(255,170,0)    14    bold
SCRUM FILLED                  rgb(0,255,136)    14    bold
WIRE FLOW                     rgb(255,102,221)  12    bold
WIRE STACK                    rgb(255,204,68)   12    bold
Coinbase rate limit           rgb(255,170,0)    12    normal
Reconciliation refused        rgb(255,51,102)   12    normal
FOLD SENT                     rgb(0,255,204)    14    bold
```

Each mini-panel table shows its header and two rows in both builds, and both
cut the 1d row off the bottom. Qt fixes the table to that height and turns both
scrollbars off; the React table read neither of the two numbers the payload
publishes for it, stood two rows taller, and pushed the three pillar labels and
the six lower bar labels below the panel. It reads them now.

`src/gui/web/indicator_panel.js` — the height the table body takes

```javascript
    var bodyStyle = {
      display: BLOCK,
      maxHeight: length(slackHeight(table)),
      overflow: HIDDEN
    };
```

One line is drawn in one picture and not the other. The panel's locks line, `No
active timeframe locks`, sits inside the Qt panel and two pixels below the
bottom of the React one, which reaches it by scrolling. The Live tab's own
splitter is what differs: Qt gives its top section 472 pixels of the 708 the
tab has, the React tab gives it 411, and the panel cannot draw shorter than 415
because each bar graph carries a 100-pixel minimum in both.

Detail: [06-trading-tab.md](06-trading-tab.md).
Detail: [07-indicators.md](07-indicators.md).

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
| `src/gui/alerts_tab.py` | `alerts_tab.js` | yes | yes | yes | - | yes | yes | in scope |
| `src/gui/analytics_tab.py` | `analytics_tab.js` | yes | yes | yes | no | yes | no | shelved |
| `src/gui/audio_suite.py` | `audio_suite.js` | yes | yes | yes | no | yes | no | shelved |
| `src/gui/bot_live_settings.py` | `bot_live_settings.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/bot_swarm_list.py` | removed | - | - | - | - | - | - | deleted |
| `src/gui/bot_visualizer.py` | `bot_visualizer.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/bot_wizard.py` | `bot_wizard.js` | yes | yes | yes | - | yes | - | in scope |
| `src/gui/buy_confirmation_dialog.py` | `buy_confirmation.js` | yes | yes | yes | - | yes | yes | in scope |
| `src/gui/competition_tab.py` | `competition_tab.js` | yes | yes | yes | no | yes | no | shelved |
| `src/gui/crypto_news_ticker.py` | `crypto_news_ticker.js` | yes | yes | yes | - | yes | shell | in scope |
| `src/gui/history_qt_table.py` | no | - | no | no | no | - | no | React side |
| `src/gui/history_tab.py` | `history_tab.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/indicator_panel.py` | `indicator_panel.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/init_wizard.py` | `init_wizard.js` | yes | yes | yes | no | yes | no | shelved |
| `src/gui/instance_consent_dialog.py` | `instance_consent_dialog.js` | yes | no | yes | no | yes | no | shelved |
| `src/gui/journal_tab.py` | `journal_tab.js` | yes | yes | yes | no | yes | no | shelved |
| `src/gui/launcher.py` | `launcher.js` | yes | yes | yes | no | yes | no | shelved |
| `src/gui/live_bot_window.py` | no | - | yes | no | no | - | no | shelved |
| `src/gui/live_settings/bot_swarm_tab.py` | `bot_swarm_tab.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/live_settings/fold_chrome.py` | `fold_chrome.js` | yes | yes | yes | - | yes | yes | in scope |
| `src/gui/live_settings/fold_tokens.py` | `fold_tokens.js` | yes | yes | yes | no | yes | no | not a screen |
| `src/gui/live_settings/fold_tranches_tab.py` | `fold_tranches_tab.js` | yes | yes | yes | - | yes | yes | in scope |
| `src/gui/live_settings/market_inspector_tab.py` | `market_inspector_tab.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/live_settings/phantom_bots_tab.py` | `phantom_bots_tab.js` | yes | yes | yes | - | yes | yes | in scope |
| `src/gui/live_settings/positions_held_tab.py` | no | - | no | no | no | - | yes | in scope |
| `src/gui/live_settings/settings_tab.py` | `live_settings_tab.js` | yes | yes | yes | no | yes | yes | in scope |
| `src/gui/live_settings/stack_tranches_tab.py` | `stack_tranches_tab.js` | yes | yes | yes | - | yes | yes | in scope |
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
| `src/gui/settings_dialog.py` | `settings_dialog.js` | yes | yes | yes | - | yes | yes | in scope |
| `src/gui/shared_testnet.py` | `shared_testnet.js` | no | yes | yes | no | yes | no | shelved |
| `src/gui/simulator_tab.py` | `simulator_tab.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/simulator_tab/fleet/fleet_replay_panel.py` | `fleet_replay_panel.js` | yes | yes | yes | no | yes | yes | shelved |
| `src/gui/simulator_tab/fleet/sim_visuals.py` | `sim_visuals.js` | yes | yes | yes | no | yes | yes | shelved |
| `src/gui/simulator_tab/nuclear_mode_panel.py` | `nuclear_mode_panel.js` | yes | yes | yes | no | yes | yes | shelved |
| `src/gui/simulator_tab/sim_stat_strip.py` | `sim_stat_strip.js` | yes | yes | yes | no | yes | yes | shelved |
| `src/gui/simulator_tab/simulator_tab.py` | `simulator_tab.js` | yes | yes | yes | yes | yes | yes | shelved |
| `src/gui/start_all_progress_dialog.py` | `start_all_progress.js` | yes | yes | yes | - | yes | yes | in scope |
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
| `src/gui/widgets/bot_status_table.py` | `bot_status_table.js` | yes | yes | yes | - | yes | yes | in scope |
| `src/gui/widgets/capital_registry_panel.py` | no | - | no | no | no | - | no | shelved |
| `src/gui/widgets/dashboard_stat_card.py` | `dashboard_stat_card.js` | yes | yes | yes | - | yes | yes | in scope |
| `src/gui/widgets/exchange_tab.py` | `exchange_tab.js` | yes | yes | yes | no | yes | yes | in scope |
| `src/gui/widgets/extractor_bot_table.py` | `extractor_bot_table.js` | yes | yes | yes | no | yes | yes | in scope |
| `src/gui/widgets/notification_spool.py` | `notification_spool.js` | yes | yes | yes | no | yes | no | shelved |
| `src/gui/widgets/privacy_dot.py` | `privacy_dot.js` | yes | yes | yes | - | yes | yes | in scope |
| `src/gui/widgets/pulse_manager.py` | `pulse_manager.js` | yes | yes | yes | no | yes | no | shelved |
| `src/gui/widgets/spendable_profits.py` | `spendable_profits.js` | yes | yes | yes | yes | yes | yes | in scope |
| `src/gui/widgets/status_log.py` | `status_log.js` | yes | yes | yes | yes | yes | yes | in scope |
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

### 2026-09-09 10:31 - #128 - the Live Bot Settings window fills its tab pages

The window a bot row opens already registered with the shell's panel host. Its
cell read `no`, and the running shell named it among nineteen registered
panels, so the cell was stale.

```
registered  bot_live_settings bot_swarm_tab bot_visualizer console_tab
            header_strip history_tab indicator_panel market_inspector
            market_inspector_tab market_inspector_topologies native_chart
            paper_trader_tab proof_of_accumulation_tab simulator_tab
            spendable_profits status_log system_status_tab trade_charts_tab
            trading_tab
```

Registering was never the whole of it. The window drew its title, its tab
strip and its two footer buttons, and every one of its seven tab pages was an
empty box. Read off the drawn page, the window held 28 elements and each page
held none.

```
part                   children  characters
status-page                   0           0
settings-page                 0           0
fold-tranches-page            0           0
stack-tranches-page           0           0
bot-swarm-page                0           0
market-inspector-page         0           0
phantom-bots-page             0           0
```

Each tab module already carried a filler that looks for the empty space this
window leaves. Nothing called it. The window now asks each module's own loader
for its view model and hands it the page.

```javascript
    var wait =
      typeof loader === "function"
        ? loader(tabRequest(model))
        : Promise.resolve(null);
    return Promise.resolve(wait).then(function (found) {
      return api.fill(space, found) === null ? null : space;
    });
```

A tab is asked for the bot the window built, never for one of its own. The
window's answer now names that bot, and the request carries it under the name
the window's own surface publishes.

```python
    config = model.bot.config
    return {
        "bot_id": model.bot.bot_id,
        "symbol": config.symbol,
        "mode": config.mode,
        "state": model.bot.state,
    }
```

Three pages fill from it. Fold Tranches draws eleven health rows, three Clear
buttons, an order picker of five choices and a filter box. Stack Tranches draws
seven summary rows and two Clear buttons. Phantom Bots draws four summary rows,
twelve timeframe boxes and the candles-to-lock number. Take the bot out of the
window's answer and every one of those rows goes.

```
page                  rows  order choices  elements   with the bot removed
fold-tranches-page      11              5        69    0,  5, 33
stack-tranches-page      7              0        33    0,  0, 12
phantom-bots-page        4              0        92    0,  0, 46
```

The order picker survives the removal because the fold chrome is asked for its
own controls rather than for a bot, which is what proves the row counter was
reading the page and not returning zero everywhere.

Every page drew at once before this. A page not on show was marked hidden and
still carried an inline display, which beats the browser's own rule for a
hidden element. The page not on show now takes `display: none`, so one tab is
on screen at a time.

```javascript
    var style = {
      display: props.current === true ? FLEX : DISPLAY_NONE,
```

The window's own stylesheet had never reached the shell page, so its tab
buttons painted white on grey. The shell now links it. Its rules were written
for a page holding this window alone, and the shell page holds every panel: 17
of the 20 tables on that page belong to other panels, as do 5 of the 12 tab
buttons. Each rule is scoped to the window before the link, and five of six
other panels render byte-identical to the run before it.

```css
[data-part="bot-live-settings"] table {
  border-collapse: collapse;
  width: 100%;
}
```

The Settings page stays empty and its row stays `no`. Its surface builds from
the bot's own settings values, and it stops on the first one the window cannot
supply.

```
AttributeError: 'BotConfigSource' object has no attribute 'visibility'
```

The window answers a stand-in bot, not a running one. Giving it a running one
would also point Apply Changes at that bot, which is a change to what a control
writes and is not this unit's to make.

The exchange screen and the Extractor table are drawn inside the Live tab, not
by the shell. Both rows stay `no`: the Live tab names an exchange only when the
shell's backend is the trading program itself, and the backend reachable here
names none, so neither child is built.

```javascript
    slot.setAttribute(CHILD_ATTR, EXCHANGE_MODULE);
    return api.renderTab(slot, shown.model);
```

The Qt window could not be built beside the React one. It reads a mode and a
state that carry a `value`, then dozens of settings fields with no fallback, so
it needs a bot the running program holds.

```
AttributeError: 'str' object has no attribute 'value'
```

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

### 2026-09-09 11:34 - #128 - the four modal dialogs are opened, not mounted

Four rows read `no` under Registers in Electron: the bot wizard, the buy
confirmation, the Settings dialog and the Start All progress dialog. None of
the four is a panel the shell should hold, so all four now take the dash the
table already uses for a module that does not register in its own right.

The running shell was asked about each name before anything was changed. All
four modules load and none registers a panel.

```
manifest names        69
panels registered     19
bot_wizard            bot_wizard.js registered no panel to draw
buy_confirmation      buy_confirmation.js registered no panel to draw
settings_dialog       settings_dialog.js registered no panel to draw
start_all_progress    start_all_progress.js registered no panel to draw
```

Each was then registered by hand and opened into a host of its own, which is
the test that decides the cell. All four draw, so none is an empty shell; what
decides them is that nothing in the shell opens them and each one's look
belongs to the page its own host builds.

```
name                  elements  characters  where it belongs
bot_wizard                  27         906  a space exchange_tab.js keeps
buy_confirmation            29         254  a window the broker raises
settings_dialog            431        2465  a window the menu raises
start_all_progress          10         390  a window Start All raises
```

The wizard is the clearest of the four. The exchange screen keeps a space for
it and fills that space once + New Bot is pressed, so its content reaches the
shell through the tab above it.

```javascript
    space.setAttribute(CHILD_ATTR, moduleName);
    return api.fill(space, null, { onClosed: closeBotWizard });
```

The Settings dialog drew all eleven tab pages at once. A page not on show was
marked hidden and still carried an inline display, which beats the browser's
own rule for a hidden element. Read off the drawn page, 320 parts sat outside
the window; with the page not on show taking `none`, none do.

```javascript
      display: props.current === true ? FLEX : DISPLAY_NONE,
```

Every drop-down on that dialog drew one letter per choice. The dialog turns
each choice into plain data before it reaches the page, and listing a word
gives its letters, so ten carriers drew as ten letters. A choice that is one
word now stays that word.

```
before   sms_carrier   A  T  V  S  U  C  B  M  G  O
after    sms_carrier   AT&T  T-Mobile  Verizon  Sprint  US Cellular  Cricket
```

Thirty-eight tick boxes and eight number boxes drew with nothing beside them.
The words were already in the payload under `text`, and the units under
`suffix`, and neither was drawn. Both are drawn now, so the Sound page reads
the same on both builds.

```
part            before   after
row-label           31      31
check-text           0      38
value-prefix         0       2
value-suffix         0       6
```

The Start All progress page did not fit the window it is drawn in. It is sized
from the dialog's own width and height and then given padding, and the page
carried a margin of its own, so the box measured 548 by 388 inside a window of
520 by 360 and both buttons fell below the edge. A stylesheet of two rules puts
the padding and the margin inside that size.

```
before   window 520x360   page 548x388   parts outside the window 10
after    window 520x360   page 520x360   parts outside the window  0
```

The wizard's own walk row is not finished. It draws the four step names as
words, where the Qt wizard draws Back, Next, Commit, Finish and Cancel and
turns Back and Finish off on the first page. The payload names the four steps
and carries no words and no on-or-off state for them.

```python
WALK_STEPS = (WALK_NEXT, WALK_BACK, WALK_CANCEL, WALK_FINISH)
```

The RENDERS column asks what the operator sees when he opens the screen, so
each of the four was asked of the running build rather than of the table. The
variant seam holds sixteen screens and answers a class per build.

```
screen                      qt build                  react build
Settings dialog             SettingsDialog            SettingsDialogReact
Start All progress dialog   StartAllProgressDialog    StartAllProgressReactDialog
Buy confirmation dialog     BuyConfirmationDialog     BuyConfirmationReactDialog
bot wizard                  no entry: both builds open BotCreationWizard
```

Three of the four keep `yes`, and each was drawn under both builds and
pictured. The wizard takes the dash. It has no entry on the seam, so + New Bot
opens the Qt wizard whichever build is running, and its React module draws only
inside the exchange screen the shell builds when its backend names an exchange.

The buy confirmation keeps `yes` for the class the broker raises, which is the
React one. Nothing calls the broker's request method, so the operator reaches
neither build of that screen; the section above records that count and it has
not moved.

The wizard's walk row is a gap in what the payload carries, and the Python
surface owns it. Qt's wizard supplies its own five buttons and works out which
are live from the page it is on. The React module is handed four step names and
nothing else, so it has no words to draw and no state to grey.

```python
WALK_STEPS = (WALK_NEXT, WALK_BACK, WALK_CANCEL, WALK_FINISH)
```

Two things are missing from `bot_wizard_surface`: the words each step draws, and
whether each step is live on the page now showing. Back is dead on the first
page and Finish is dead until the last, and both follow from the step order the
surface already holds.

```
PROPOSED, in bot_wizard_surface.py

WALK_WORDS = {"back": "< Back", "next": "Next >", "commit": "Commit",
              "finish": "Finish", "cancel": "Cancel"}

walk_live(page) -> {"back": page is not the first, "next": a page follows,
                    "finish": no page follows, "cancel": True}
```

### 2026-09-09 12:45 - #128 - the alerts tab is opened, the news strip is drawn inside the exchange screen

Two rows read `no` under Registers in Electron: the Notifications and Alerts
tab and the crypto news strip. Neither is a panel the shell should hold, so
both now take the dash the table already uses for a module that does not
register in its own right.

The running shell was asked about each name before anything was changed. Both
modules load and neither registers a panel.

```
manifest names        69
panels registered     19
alerts_tab            alerts_tab.js registered no panel to draw
crypto_news_ticker    crypto_news_ticker.js registered no panel to draw
module load errors    []      faults []
```

Each was then registered by hand and opened into a host of its own, which is
the test that decides the cell. Both draw, so neither is an empty shell; what
decides them is that the shell opens neither, and that a panel host has no way
to give either one the values it needs.

```
name                  opened  elements  characters  what it drew
alerts_tab              true        54         233  both tables empty
crypto_news_ticker      true         2          21  Fetching crypto news
strips on the page                                  2, for one exchange space
```

The alerts tab is raised by a window rather than by a tab. The variant seam
holds it under the name ALERTS, so the Qt build opens `AlertsTab` and the
React build opens `AlertsReactTab`, which is one browser view filling the whole
tab. Opened as a panel instead, it draws every control and no row, because the
host asks with an empty request and no notification manager reaches it.

The news strip belongs to the exchange screen. That screen keeps a space for
it and fills that space, once per exchange, the way it fills the two bot
tables. A registration holds one host per name, so registering the strip put a
second copy of it on the page.

```javascript
    space.setAttribute(CHILD_ATTR, moduleName);
    return api.mount(target);
```

The two RENDERS cells part company. The variant seam answers a class per build
for the alerts tab, so that cell keeps `yes`. It holds no entry for the news
strip, so the exchange header builds the Qt strip whichever build is running,
and the React module draws in the Electron shell and nowhere else. That cell
now reads `shell`, the value this table already defines for exactly that.

```
screen                        qt build            react build
Notifications and Alerts      AlertsTab           AlertsReactTab
crypto news strip             no entry: both builds build CryptoNewsTicker
```

The strip was never fed. The exchange screen asked the backend for the strip's
state with an empty request, so the strip was built and never started, and the
line read "Fetching crypto news" for as long as the shell ran. Qt starts the
strip as it builds it and the screen already reports that it did, so the
request now carries the start it reports.

```javascript
  function tickerRequest(model) {
    var started = model[NEWS_TICKER_STARTED];
    return typeof started === "number" && started > ZERO ? { start: true } : {};
  }
```

The backend had no fetch to run either. The strip's model takes its fetch as an
argument and the bridge never gave it one, so the worker answered with no
stories. The bridge now hands in the same transport the Qt strip uses, and runs
the fetch away from the request that asked for it, so the answer arrives the
way it arrives in Qt.

```python
    crypto_news_ticker_surface.use_fetch(SafeRequest, safe_urlopen, time.monotonic)
```

With that in place the shell fetched 43 stories from the ten feeds and drew
them, one at a time, in the exchange header. Refusing every feed drops them
again, which is what proves the line carries what the fetch found.

```
live      [2/43] The Defiant - SEC Crypto Custody Rewrite Enters White House Review
broken    (no crypto news feeds reachable)
no start  Fetching crypto news
```

Both builds of each screen were then driven on one reading and compared item by
item. The alerts tab was read on one notification manager filled the way the
main window fills it: the risk rules over a three-bot fleet, the profit and
loss milestone, one bot error and one bot start. The news strip was read on one
answer from the shipped fetch, given to each side through its own receiver.

```
alerts tab       13 routing rows, 4 history rows      differences 0
news strip       6 stories, 8 steps, wraps 6 to 1     differences 0
```

Every alert row matches: its time, its priority word, its title, its message,
its channels, and the colour of each. The four priorities draw in four colours,
low grey through critical red, and the rows run newest first on both sides.
Emptied of notifications, both sides draw no rows and both read `Unread: 0`.

The strip shows the same story at each place, moves one place forward on each
step, and wraps from the last story to the first on both sides. Its words are
`#cfe6ff` on both and its pointer is the hand on both.

Two colours were wrong on the page and are now right. The tab's group boxes
carry a Qt style sheet whose colour paints the group's title alone; the page
was painting the whole box with it, so the routing table's Event and Priority
columns and the three field labels drew in the accent where Qt draws them in
the body colour. The page also carried no stylesheet of its own, so with the
group colour moved to the title it fell back to the browser's black.

```
                        before        after         qt
routing Event column    #00ffcc       #e0e0f0       #e0e0f0
field labels            #00ffcc       #e0e0f0       #e0e0f0
```

The two strips take the fetch at different moments. The Qt strip shows a story
as soon as the fetch answers, because the worker reports to it. The page has no
such report, so it shows the answer on its next 15 second step. Closing that
needs a route from the backend to a module the shell holds by name, and the
strip is drawn by its parent rather than held by name.

The Qt tables are drawn by the theme, not by the tab, so the page draws no grid
lines, no alternating row bands and no header underline. Those live in the Qt
style sheet for every table in the application and reach no payload.
