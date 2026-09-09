# 2026-09-09 — the web analyzers: one crash and forty-three unused names

Reference for issue #128. This page records what threw, what caused it, what
changed, and what the shell reports now. Files this unit changed:

```
src/gui/web/trade_charts_tab.js
src/gui/web/native_chart.js
src/gui/web/indicator_panel.js
src/gui/web/market_inspector.js
src/gui/web/header_strip.js
src/gui/web/spendable_profits.js
src/gui/web/bot_visualizer.js
src/gui/web/bot_swarm_tab.css
desktop/renderer/index.html
```

This unit wrote no test file and changed no file under `docs/`.

The Electron shell ran from `desktop/main.js` under the installed Electron
binary, with a throwaway user directory and a fresh remote debugging port for
every launch. The Chrome DevTools Protocol read the renderer. The Python
backend ran as the shell spawns it:

```
PYTHONWARNINGS=error
ACERVATOR_BRIDGE_ARGV="-X dev -X faulthandler -m src.core.desktop_bridge"
electron.exe <worktree>/desktop --disable-gpu --remote-debugging-port=<port>
```

This report writes every absolute path as `<worktree>`. The backend printed
nothing to its error channel on any launch.

---

## 1 — `mountedIds` raised on every call

### 1.1 the error

ESLint reported `no-undef 'mountedOrder'`. The shell then raised it. The bridge
loaded the model first, so `held` held a payload:

```
ReferenceError: mountedOrder is not defined
    at Object.mountedIds (file:///<worktree>/src/gui/web/trade_charts_tab.js:1229:17)
    at <anonymous>:4:41
    at <anonymous>:8:3
```

### 1.2 reproduction

```
window.acervatorLoadCharts({reset: true})   -> isLoaded true, loadError null
window.acervatorCharts.mountedIds()         -> the ReferenceError above
```

The module publishes `mountedIds` on its public surface, so any caller holding
a loaded model raised. A picture comparison missed it because that run never
called the function.

### 1.3 the cause

`mountedOrder` appears once in the whole tree, at that call site, and no file
defines it. The name it should carry is `knownOrder`, which the same file
defines:

```js
  // The bots the ticker list really offers, which is the order minus the unknown.
  function knownOrder(model) {
    var assets = assetsOf(model);
    var seen = {};
    return listField(model, ASSET_ORDER).filter(function (botId) {
      var name = String(botId);
      if (!isPlainObject(assets[name]) || owns(seen, name)) {
        return false;
      }
      seen[name] = true;
      return true;
    });
  }
```

`Content` already calls `knownOrder` to decide whether to draw a panel, and
writes its result to `data-mounted`. `checkPanels` calls an ordered bot with no
asset bag `unmounted`. A mounted id is therefore an ordered id that carries an
asset bag, once — which is what `knownOrder` returns.

The three readers sit together and now answer three different questions:

```
panelIds()     the asset keys, unordered
panelOrder()   the published order, verbatim, repeats and all
mountedIds()   the ids that get a panel, in published order
```

### 1.4 the correction

```js
  function mountedIds() {
    return held === null ? [] : knownOrder(held.model);
  }
```

### 1.5 the rerun

The live payload carried no bots, so the call answers with the empty list
instead of raising:

```
window.acervatorCharts.mountedIds()   ->  []
```

The module's own loader then took a payload with two ordered bots, one id twice
and one id with no asset bag:

```
panelIds     ["bot-a", "bot-b"]
panelOrder   ["bot-a", "bot-b", "bot-a", "bot-ghost"]
mountedIds   ["bot-a", "bot-b"]
```

`mountedIds` drops the repeat, drops the id with no asset bag, and keeps the
published order.

---

## 2 — forty-three unused names

ESLint reported 44 errors over seven modules. One was the crash above. The
other 43 name a value nothing reads. This unit read each one in place and put
it in one of two groups.

### 2.1 the split

```
leftovers, deleted                 41
wiring that never got connected     2
```

The counts break down per file as:

```
native_chart.js        7 deleted
header_strip.js       20 deleted
indicator_panel.js     1 deleted
market_inspector.js    5 deleted
spendable_profits.js   2 deleted
bot_visualizer.js      5 deleted, 1 connected
trade_charts_tab.js    1 deleted, 1 connected
```

### 2.2 the leftovers

Forty names carry a thing another module draws, or a second spelling of a value
the module already reads. Deleting them changes no output.

`header_strip.js` carried twenty. The strip draws a container for the spendable
panel and a container per counter card, and two child modules fill them:

```
spendable_profits.js   columns, separators, dots, labels, values, stretches
dashboard_stat_card.js the card label row, its caption, its amount, its dot
```

The strip's column, separator, label-row and stretch names therefore name
elements the strip never draws, and so do its value, dot and separator
alignment names. Each child module carries its own name for the same part and
reads it.

`native_chart.js` carried seven attribute names — slot, index, kind, major, up,
candle count and label. That file writes every one of those attributes as a
plain string, about twenty-five times, so the drawing carries them all.

The rest:

```
trade_charts_tab.js   CHANGE_EVENT     the module wires React onChange, not a DOM listener
indicator_panel.js    MINI_PART        a mini panel is two grid slots, not one element
market_inspector.js   MODULE_STATUS_PART, LEFT_STRETCH_PART   the file draws no such element
market_inspector.js   SIGNALS_TABLE, PAIRS_TABLE   two table names nothing reads, section 2.4
market_inspector.js   the caught error in `repeated`, which the handler never reads
spendable_profits.js  SEPARATOR_GAP, TRAILING_STRETCH   the item list carries both
bot_visualizer.js     ROW_MARGINS, ROW_SPACING   each row's own frame carries both
bot_visualizer.js     ROW_KINDS        the module's own live, sim and paper names
bot_visualizer.js     NEWLINE, BOT_ID_ATTR       data-key already carries the bot id
```

### 2.3 the wiring that was never connected

**`bot_visualizer.js`, `DOT_CURSOR`.** The surface publishes
`dot_cursor: "PointingHandCursor"` for the privacy dot. `PrivacyDot` wrote a
fixed `pointer` and never read the field. It now reads it through a name map:

```js
  var CURSOR_BY_NAME = { PointingHandCursor: POINTER };

  function cursorOf(name) {
    return owns(CURSOR_BY_NAME, name) ? CURSOR_BY_NAME[name] : undefined;
  }
```

The published name maps to `pointer`, so the dot draws as before.

**`trade_charts_tab.js`, `MAXIMUM_HEIGHT`.** The panel surface publishes
`maximum_height_px` beside `minimum_height_px`, and the Qt panel owns a setter
for each. The React panel read the floor and dropped the ceiling. It now reads
both:

```js
    style.minHeight = height(panel[MINIMUM_HEIGHT]);
    style.maxHeight = height(panel[MAXIMUM_HEIGHT]);
```

`PANEL_MAXIMUM_HEIGHT_PX` is `None` and no code calls `set_maximum_height`, so
this tab's payload carries null and `height` answers undefined, which writes no
style. Nothing on screen moves today.

### 2.4 the two table names, and the tables that do not draw

`market_inspector.js` declared `SIGNALS_TABLE` and `PAIRS_TABLE`, holding the
strings `signals` and `pairs`. A search of the whole tree, excluding the package
directories, finds each name twice: its own declaration, and this report.

```
grep -rn "SIGNALS_TABLE\|PAIRS_TABLE\|signals_table\|pairs_table\|SignalsTable\|PairsTable"
  src/gui/web/market_inspector.js:899  var SIGNALS_TABLE = "signals";
  src/gui/web/market_inspector.js:900  var PAIRS_TABLE = "pairs";
```

Both sat inside the module's function scope and neither reached the object at
`global.acervatorMarketInspector`, so no string lookup from another module can
name them. They are leftovers and this unit deletes them.

Deleting them settles nothing about the tables, and the tables are a separate
fact. `TableGroup` is defined and exported and no file constructs it. The
module `market_inspector_topologies.js` defines and draws its own `TableGroup`,
which is a different function. Read in the running shell:

```
payload   signal_columns 6   pair_columns 7   signal_rows 0   pair_rows 0
drawn     table-group 0  grid 0  grid-head 0  grid-row 0  grid-cell 0
          empty-note 0   [data-table] 0
          module-group 6
exports   TableGroup present   Grid present
```

The screen draws six module groups and no table of any kind. The `module-group`
count is the control: the same query reports the parts that do exist, so a zero
is a fact about the screen rather than about the query.

Drawing those two tables would change what the screen shows, which this unit
may not do. The finding stays named here and this unit does not act on it.

---

## 3 — one selector written twice in the swarm style sheet

### 3.1 the error

```
src/gui/web/bot_swarm_tab.css
  60:1  Duplicate selector ".acervator-swarm-tab [data-part=\"grid-page\"]",
        first used at line 54                       no-duplicate-selectors
```

### 3.2 the cause

Two blocks carried the same selector. Between them they named six properties
and no property twice:

```
line 54   flex, min-height, overflow
line 60   display, flex-wrap, align-content
```

Same selector, same specificity, no shared property. Both blocks applied, so
the page already got all six and lost nothing.

### 3.3 the correction

One block now carries the six declarations.

### 3.4 the rerun

The running renderer applied the two style sheets in turn to the same element,
then read the computed style back:

```
                              flex       min-height  overflow  display  wrap    align-content
sheet at HEAD                 1 1 auto   0px         auto      flex     wrap    flex-start
sheet on this branch          1 1 auto   0px         auto      flex     wrap    flex-start
control, no swarm ancestor    0 1 auto   auto        visible   block    nowrap  normal
```

The control differs on all six, so the reading can report a difference. The two
sheets do not differ. Stylelint now reports nothing on the file.

---

## 4 — five self-closing void tags in the shell page

### 4.1 the error

```
desktop/renderer/index.html
   4:27  Expected omitted end tag <meta> instead of self-closing element <meta/>
   8:5   Expected omitted end tag <meta> instead of self-closing element <meta/>
  10:71  Expected omitted end tag <link> instead of self-closing element <link/>
  11:74  Expected omitted end tag <link> instead of self-closing element <link/>
  12:47  Expected omitted end tag <link> instead of self-closing element <link/>
```

### 4.2 the correction

The two `meta` tags and the three `link` tags lost the trailing slash. HTML
parses a void element the same either way, so the page loads the same three
style sheets and carries the same content security policy.

### 4.3 the rerun

`html-validate` reports nothing on the file, and the renderer still draws every
panel — section 5.

---

## 5 — what the screens do after the change

A fresh launch opened every panel these files serve through the panel host.
`opened` carries the host's own answer, and it reads false when a panel fails
to register, refuses its model, or throws while drawing.

```
panel               registered  reason  opened  elements  parts
trade_charts_tab    yes         null    true    11        10
native_chart        yes         null    true    5         5
indicator_panel     yes         null    true    48        35
market_inspector    yes         null    true    102       97
header_strip        yes         null    true    62        62
spendable_profits   yes         null    true    50        50
bot_visualizer      yes         null    true    63        58
bot_swarm_tab       yes         null    true    3         3
status_log          yes         null    true    2         2

acervatorPanelHost.faults()   []
```

The visualizer's own privacy dot, read inside its host element rather than the
header strip's:

```
cursor  pointer
glyph   ●
```

### 5.1 the drawing does not change

Three captures took the rendered markup of all nine panels, one Electron launch
each:

```
branch, launch one   69,230 bytes
branch, launch two   69,230 bytes   identical to launch one
HEAD, launch three   69,230 bytes   identical to both
```

The three files match byte for byte, so this branch draws what `HEAD` draws.

A capture that always matches proves nothing, so the reading needed a control.
One part name in `trade_charts_tab.js` took a different value, the capture ran
again, and the file went back:

```
control capture vs branch capture   differ
file restored, captured again       identical to branch again
```

The instrument reports a difference when one exists.

---

## 6 — the checks

```
npx eslint            0
npx stylelint         0
npx html-validate     0
tools.local_ci black  VERDICT: PASSED
tools.local_ci flake8 VERDICT: PASSED
```
