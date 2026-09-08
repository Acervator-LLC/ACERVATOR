# The Sim tab is a Trading-tab clone reading Stone Tablets

The tab that drew three sentences now draws the Trading tab's panes over one
Stone Tablet: the bot list with the live table's own ten columns, the Indicator
Voting Panel, and a second layer holding the VWAP window over the tablet
playback window, with one button between them. Both builds were opened and read
off the drawn window and the drawn page.

`~/.acervator/settings.json` hashed the same before and after every run.

```
before  2b1946b9560593d7e437805a62e9770a5aed28af0827251bb84c0125862abc7e
after   2b1946b9560593d7e437805a62e9770a5aed28af0827251bb84c0125862abc7e
```

Every run used a throwaway home holding a copy of the RA tablet files, so no
run could write into the operator's tree. `~/.acervator_ra_tablets` still holds
414 entries and its index file still carries its original timestamp. No
authenticated call, no credential, no order, and the running Acervator process
was never started, attached to or queried.

## Reproduce

The window was built and every tab was opened in turn, under both variants,
with a tablet copy on disk and again with none. Qt's own message handler was
installed and every message it emitted is quoted below.

```
MainWindow(None, None) built, then setCurrentIndex over every tab
python -X dev -X faulthandler
QT_QPA_PLATFORM=offscreen
QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu --disable-gpu-compositing
ACERVATOR_VARIANT=qt      resolve_variant answered qt
ACERVATOR_VARIANT=react   resolve_variant answered react
```

The toolkit emitted one message under Qt and two under React. Neither names the
Sim tab.

```
QFontDatabase: Cannot find font directory .../PySide6/lib/fonts.
GPUInfo not initialized on GpuInfoUpdate
```

## Every tab still opens

Ten tabs, in the operator's order, with no error, under both builds.

| tab | qt | react |
| --- | --- | --- |
| Sim | `SimulatorTabQt` | `SimulatorTabReact` |
| Paper | `EmptyTabQtPanel` | `EmptyTabReactPanel` |
| Live | `QWidget` | `QWidget` |
| Charts | `TradeChartsTab` | `TradeChartsTab` |
| Inspector | `MarketInspectorTab` | `MarketInspectorReactTab` |
| Swarm | `BotVisualizationTab` | `BotSwarmReactTab` |
| Accumulation | `EmptyTabQtPanel` | `EmptyTabReactPanel` |
| History | `HistoryTab` | `HistoryReactTab` |
| Status | `EmptyTabQtPanel` | `EmptyTabReactPanel` |
| Console | `ConsoleQtTab` | `ConsoleReactTab` |

The bar reads in the canonical order in all four runs.

```
Sim  Paper  Live  Charts  Inspector  Swarm  Accumulation  History  Status  Console
```

## The tablet that fed the tab

The selector listed every tablet the index holds and opened on the newest one.
The three windows read the last hundred rows of it.

```
tablets listed   411
tablet           XRP_1d_2026_coinbase
rows on disk     250 candles
first            2026-01-01   (first_ts_ms 1767225600000)
last             2026-09-07   (last_ts_ms  1788739200000)
source           coinbase_exchange_candles_ONE_DAY
window drawn     100 candles
```

The tab says the same thing on screen, in its Replay Log.

```
XRP_1d_2026_coinbase — 250 candles, 2026-01-01 to 2026-09-07
source coinbase_exchange_candles_ONE_DAY
window 100 of 250 candles
```

## What the four parts drew

The bot list drew the live table's ten column labels and its two fixed widths,
and no rows, because no simulated fleet exists yet.

```
columns        Bot ID, Symbol, Current Position Value, Trades, Target,
               Target BTC, Target ETH, Ammo, Fire, (detail)
fixed widths   column 8 = 70 px, column 9 = 60 px
rows           0
empty line     "No simulated fleet. Import Live Fleet builds one."
```

The Indicator Voting Panel drew twelve real votes over the tablet's candles,
across its two tables.

```
summary   5 bullish, 2 bearish, 5 neutral
row       1d
table A   TF BB VTX MACD SRsi Ichi Vol Net Comp Conf
          1d  ─ 0%  ▼ 32%  ▼ 60%  ▲ 50%  ▲ 59%  ▲ 20%  +1.71  —  15%
table B   TF Sling ADX STrd ZSc KER RSI
          1d  ─ 0%  ▲ 0  ▲ 60%  ─ +0.0  ─ 0.00  ─ 0%
```

The VWAP window drew a hundred points on each of its two lines, and the
playback window drew a hundred candles.

```
VWAP window   100 points, last close 1.388, last VWAP 1.2394338149030621
playback      100 candles, 100 shapes drawn on the page
```

The flip button moved the panel area to the chart layer and changed its own
words. On the page the layer attribute followed it.

```
before   layer indicators, button "Show Playback"
after    layer playback,   button "Show Indicators"
qt       stack index 1, showing the chart splitter
react    data-layer playback, 100 candle groups in the drawn page
```

## With no tablet on disk

The same runs against a home holding no tablet directory. Nothing was invented
in place of the missing tape.

```
tablets listed   0
selector         holds nothing
panel            "No TA data — No Stone Tablet on disk."
VWAP window      0 points
playback         0 candles
Replay Log       "No Stone Tablet on disk."
```

This is the positive control for every count above. One instrument, two
conditions, and the numbers move with the data rather than with the reader.

## The send rule

The Simulator's whole data path is one class that reads tablet files. It holds
no venue, defines no write, and refuses by name anything that is not a read.
Nine venue calls were asked of it and all nine were refused.

```python
    def __getattr__(self, name: str):
        """Refuse every name outside ``READ_NAMES``."""
        raise SendRefused(
            f"TabletSource answers {READ_NAMES} and cannot {name!r}. "
            "The Simulator receives and asks; it sends nothing."
        )
```

What the run printed:

```
public names on the class   candles, entries, entry_for, newest, root
create_order                hasattr False -> SendRefused
create_market_buy_order     hasattr False -> SendRefused
cancel_order                hasattr False -> SendRefused
edit_order                  hasattr False -> SendRefused
withdraw                    hasattr False -> SendRefused
set_leverage                hasattr False -> SendRefused
transfer                    hasattr False -> SendRefused
write_tablet                hasattr False -> SendRefused
save                        hasattr False -> SendRefused
reads answer                list of 411 entries
```

The drawn tab loads no venue code either. After a full model was built, one
exchange module was resident and it builds chart links.

```
src.exchange modules loaded   src.exchange, src.exchange.exchange_chart_urls
ccxt loaded                   False
src.core.event_bus loaded     False
src.trading.scrumming_bot     False
```

## Qt against React, value by value

Both sides were read off what they drew: the Qt values off live widgets, the
React values off the loaded document. Thirty-two values were compared and all
thirty-two matched, in both conditions.

```
with a tablet on disk    matched 32 of 32
with no tablet on disk   matched 32 of 32
```

| value | qt | react |
| --- | --- | --- |
| privacy button text | Privacy Mode: OFF | same |
| news ticker row present, children, height | yes, 0, 24 | yes, 0, 24px |
| data pool row present, children, height | yes, 0, 18 | yes, 0, 18px |
| fleet label | Scrumming Bots | same |
| fleet columns | the ten labels | same |
| fleet column count | 10 | 10 |
| fleet row count | 0 | 0 |
| fleet fixed widths | 8 = 70, 9 = 60 | same |
| fleet empty line | No simulated fleet… | same |
| tablet label | Tablet: | same |
| tablet options | 411 | 411 |
| tablet chosen | XRP_1d_2026_coinbase | same |
| flip button text | Show Playback | same |
| layer on open | indicators | indicators |
| indicator title | Indicator Voting Panel | same |
| indicator summary | 5 bullish, 2 bearish, 5 neutral | same |
| indicator table A columns, rows, first row | 10, 1, the ten cells | same |
| indicator table B columns, rows, first row | 7, 1, the seven cells | same |
| VWAP window points | 100 | 100 |
| playback candles | 100 | 100 |
| playback shapes drawn | 100 | 100 |
| replay log | the three lines | same |
| crypto news ticker widgets | 0 | 0 |
| data pool line present | no | no |
| layer before and after the flip | indicators, playback | same |
| flip button after | Show Indicators | same |
| VWAP points after the flip | 100 | 100 |

The two classes differ by build and that is the whole difference the comparison
found.

## The Sim tab against the Trading tab

The Live tab was measured in the same run. Four pane values match, and every
difference below is deliberate.

```
                     sim              trading
margins              2, 2, 2, 2       2, 2, 2, 2
spacing              2                2
splitter handles     5                5
children collapsible false            false
splitters            3                4
```

| difference | why |
| --- | --- |
| The crypto news ticker is not on the tab and its code is not carried over | The operator marked it. A live news feed describes nothing a tablet reader does |
| The data pool line is not on the tab and its code is not carried over | The operator marked it. A live cache-health line describes nothing a tablet reader does |
| Both rows keep their height and carry a button | Import Live Fleet and Generate From YTD in Validation, Import Live Fleet and Create New Bots in Back Test |
| The New Bot button is Back Test's | Create New Bots builds one simulated bot on the tablet the selector shows |
| No Fire cell and no Detail cell in the bot list | Both act on a live bot, and the Simulator sends nothing. The columns stay, so the widths match |
| One log pane, not two | The Trading tab's two panes are fed by the live activity spool and the live API log. The Simulator imports neither |
| Three splitters, not four | The fourth is the second log pane |
| A tablet selector where the Trading tab has none | The Simulator's unit of data is a tablet |
| A layer button and a second layer | The rebuild plan puts the VWAP and playback windows behind the panel |

The two removed strips were counted with an instrument proved on a control
widget holding a real ticker and a real data-pool line.

```
control widget   1 ticker, 1 data-pool line
sim tab          0 tickers, 0 data-pool lines
```

The Live tab reported zero of each in this run as well, because no exchange is
configured, so its per-exchange tab was never built. That is why the control
was needed.

## Errors the runs threw, and what changed

### The React page reported nothing to the reader

The first React run read an empty answer back from the loaded page while the
page itself had drawn. Driving the page alone and printing its console showed
the document was complete and the module held no fault.

```
page_ready True
module object
faults []
text  Privacy Mode: OFFScrumming BotsBot IDSymbol…
```

The reader was asking the page for a nested object and taking whatever the
conversion returned. The correction has the page stringify its own answer and
the reader parse it, so no conversion sits between the document and the
reading. The same read then returned every value.

### The tab book handed back no view

```
File "u117_drive_sim.py", line 366, in main
    report["sim"] = js(sim.panel_view(), READ_JS, app) or {}
AttributeError: 'NoneType' object has no attribute 'page'
```

The React tab now builds its web view on the first show, the way the empty tabs
do, so a tab nobody opens costs no browser. The window in the run is never
shown, so the reader calls the shipped build method first.

### The tab-order stub could not find the builder

```
File "tests/test_canonical_tab_order.py", line 157, in _empty
    MethodType(EmptyTabsMixin.__dict__[method], self)()
KeyError: '_build_simulator_tab'
```

The Sim tab is built now, so its builder moved out of the unbuilt-tab mixin
into one of its own. The stub ran shipped builders off a single class. It now
takes the owning class as an argument and still runs shipped code, so it would
fail again if the builder stopped inserting the tab. 1036 cases pass.

### The Privacy Mode button drew and answered nothing

The GUI archetype refused the renderer module with one high finding: a button
carrying no handler. It was right, and the Qt button was wired to nothing
either.

Both are now wired to the same registry the live button uses: pressing it masks
every registered field while any is revealed, and reveals them all otherwise.
The button reads its words back off the registry rather than from a constant.

```python
def privacy_masked() -> bool:
    """True when the registry holds fields and every one of them is masked."""
```

The guard on the field list is deliberate. An empty registry would make an
all-of check answer true, and the button would say every field is hidden when
none is registered.

## The archetypes

Every file this unit touched, with the archetype that owns it. Exit code and
high-severity count beside each verdict.

```
src/simulator/tablet_source.py               coding  passed=True exit=0 high=0
src/gui/main_tabs/simulator_tab_surface.py   coding  passed=True exit=0 high=0
src/gui/main_tabs/simulator_tab_surface.py   ta      passed=True exit=0 high=0
src/gui/main_tabs/simulator_tab.py           coding  passed=True exit=0 high=0
src/gui/main_tabs/simulator_tab.py           gui     passed=True exit=0 high=0
src/gui/simulator_tab.py                     coding  passed=True exit=0 high=0
src/gui/simulator_tab.py                     gui     passed=True exit=0 high=0
src/gui/simulator_tab.py                     ta      passed=True exit=0 high=0
src/gui/react_simulator_tab.py               coding  passed=True exit=0 high=0
src/gui/react_simulator_tab.py               gui     passed=True exit=0 high=0
src/gui/web/simulator_tab.js                 gui     passed=True exit=0 high=0
src/gui/main_tabs/empty_tabs.py              coding  passed=True exit=0 high=0
src/gui/main_tabs/empty_tabs.py              gui     passed=True exit=0 high=0
src/gui/variant_surface.py                   coding  passed=True exit=0 high=0
src/gui/variant_surface.py                   gui     passed=True exit=0 high=0
src/gui/main_window.py                       coding  passed=True exit=0 high=0
src/gui/main_window.py                       gui     passed=True exit=0 high=0
tests/test_canonical_tab_order.py            coding  passed=True exit=0 high=0
docs/manual/08-tabs.md                       docs    passed=True exit=0 high=0
docs/manual/08-tabs/simulator.md             docs    passed=True exit=0 high=0
```

The coding archetype has no analyser for JavaScript. It answers the same way
for two shipped modules this unit never touched, so the GUI archetype is the
one that reads a renderer module.

```
src/gui/web/simulator_tab.js   scanned False, no analyzer for javascript
src/gui/web/history_tab.js     scanned False, no analyzer for javascript
src/gui/web/console_tab.js     scanned False, no analyzer for javascript
```

The fixture control was run before any verdict above was trusted.

```
harness_fixtures/coding_archetype/known_good.py   exit 0
harness_fixtures/coding_archetype/known_bad.py    exit 1
```

## The tests that name what changed

```
tests/test_canonical_tab_order.py
tests/test_react_empty_tabs_render.py
tests/test_desktop_panel_host.py
tests/test_desktop_bridge.py
tests/test_conversion_scope_column.py
tests/test_conversion_state_pairs_on_the_bridge.py

1188 passed
```

## The manual

Both pages take additions only.

```
docs/manual/08-tabs.md              22 added, 0 removed
docs/manual/08-tabs/simulator.md   126 added, 0 removed
```

The Simulator page's record of the removed screen carries twenty-five citations
of files the rebuild deleted. Each already says so in the line beneath it, and
none of them is new here.

## What is not done

Import Live Fleet, Generate From YTD, Validation, Back Test and Portfolio
Battery are later units. The bot list holds no rows until the first of those
lands, and the tab says so rather than filling itself.
