# 2026-09-09 — Market Inspector: two tables that carry data and draw nothing

Issue #128, rows 878 and 879 of the conversion table in
[08-tabs.md](../../docs/manual/08-tabs.md). Files changed:
`src/gui/market_inspector.py`, `src/gui/main_tabs/market_inspector_surface.py`,
`src/gui/react_market_inspector_tab.py`, `src/gui/web/market_inspector.js` and
`src/gui/web/market_inspector.css`. No test file was written.

The Qt tab was built offscreen under `python -X dev -X faulthandler` with
`PYTHONWARNINGS=error`, themed `cyberpunk_dark`, with three Windows faces loaded
into the offscreen driver so the picture carries text. The Electron shell ran
from `desktop/main.js` under the installed Electron binary with a throwaway home
and profile, and the renderer was read over the Chrome DevTools Protocol. Every
`electron.exe` was killed before and after each run.

Both sides ran on one scan. `MarketInspector.scan_universe` read three markets
on three timeframes and returned three signals; `_find_opposing_pairs` ran the
real `cointegration_test` and returned one pair, ZEC against IMX at r=-0.999.

Pictures:

```
qt before     <scratchpad>/u128_tables/qt_market_inspector_tables.png
qt after      <scratchpad>/u128_tables/qt_market_inspector_tables_after.png
react before  <scratchpad>/u128_tables/react_market_inspector_tables_before.png
react after   <scratchpad>/u128_tables/react_market_inspector_tables_after.png
```

---

## 1 — How the earlier comparison took the two table items

### 1.1 the error

No traceback. The 27-item comparison in
[2026-09-09_market_inspector_register.md](2026-09-09_market_inspector_register.md)
reports item 20 as "HTF Signals columns ... the same six", item 21 as "5 rows,
ZEC ZK ZETA GRT IMX, cell for cell", item 22 as seven Opposing Pairs columns and
item 23 as zero rows on both sides. No table element exists on either screen, so
no picture can carry any of those four.

### 1.2 reproduction

The React module published four readers that answer from the payload and never
touch the page.

```javascript
function rowByName(columnsField, rowsField, wanted) {
  var columns = listField(held.model, columnsField);
  listField(held.model, rowsField).forEach(function (row) { ... });
}
```

`signalOrder`, `pairOrder`, `signalRow` and `pairRow` all resolve through
`held.model`, which is the payload the surface pushed. On the Qt side the same
items resolve through `_signals_tbl.item(row, column).text()`, a
`QTableWidget` that no layout held.

### 1.3 the cause

Both sides read one payload, so a value comparison agrees no matter what draws.
A deleted component gives the same green. The four table items came off the
model on the React side and off an orphaned widget object on the Qt side.

### 1.4 the correction

Items 20 to 23 are void, and the four model readers are removed so no later
comparison can repeat them. The other 23 items name elements that appear in
both pictures taken here: the six zone titles and their order, the two panes,
the filter row, the two Opposing Trades controls, the status line, the four zone
notes, the three Ready to Send buttons, the six stepper positions, the
topologies status and footer, the zone legend colour, the button ground, the
page ground and the check box. None of those depends on the model reader, so the
same route does not void them.

### 1.5 the rerun

Read in the shell after the change, `acervatorMarketInspector.signalRow` and
`pairRow` are `undefined`, and no reader on that module answers from the model
about a table.

---

## 2 — The Qt tab built two group boxes and put neither in a layout

### 2.1 the error

```
group_boxes_in_tree   6
visible_group_boxes   6
tables_in_tree        0
visible_tables        0
signals placed        False
pairs placed          False
```

The six group boxes are the control: the reading is not blind, and it still
finds no `QTableWidget` under the tab. Both tables held real data at that
moment.

```
signals headers  ['Asset', 'Signal', 'Score', 'Daily', 'Weekly', 'Active']
signals rows     2   ZEC ENTRY_LONG_MEDIUM 0.60 ... / IMX ENTRY_SHORT_MEDIUM ...
pairs headers    ['Long side', 'Short side', 'Method', 'Window', 'Statistic',
                  'Correlation', 'Score (Long+Short)']
pairs rows       1   ZEC (ENTRY_LONG_MEDIUM) | IMX (ENTRY_SHORT_MEDIUM) | ...
```

### 2.2 reproduction

```
ACERVATOR_VARIANT=qt QT_QPA_PLATFORM=offscreen
surface_class(MARKET_INSPECTOR)() ; tab._render_signals() ; tab.grab()
```

### 2.3 the cause

`_build_ui` created `self._signals_group` and `self._pairs_group`, filled each
with a table and an empty label, and added neither to `left_pane`. A parentless
group box is a window nobody shows. Two commits took them out of the layout on
purpose: the six-zone layout of 2026-09-06 moved HTF Signals to the reserved
Phantom Bot zone, and the one-entry-at-a-time change gave each opposing pair to
the Opposing Trades stepper.

### 2.4 the correction

The Qt tab no longer builds the two group boxes, their tables or their empty
labels. `_fill_pair_rows` keeps the pairs the stepper reads, `_fill_signal_rows`
takes the signals the tab has no widget for, and the zone count reads
`len(self._pairs)` where it read a row count.

```python
def _fill_pair_rows(self, pairs: list) -> None:
    """Hold the opposing pairs the Opposing Trades stepper draws."""
    self._pairs = list(pairs)
    self._render_empty_notes()
```

### 2.5 the rerun

```
group_boxes_in_tree 6, visible 6, tables_in_tree 0
pairs_held 1
zone positions   0 of 0 | 1 of 1 | 0 of 0 | 0 of 0 | 0 of 0 | 0 of 0
```

The Qt picture is byte-identical before and after: 59,556 bytes, sha256
`86828546a186badd`.

---

## 3 — The React screen carried the column sets and drew no table

### 3.1 the error

Counted in the running shell on the payload that scan produced:

```
table-group 0, grid 0, grid-row 0, head-cell 0, empty-note 0
module-group 6, module-legend 6, zone-entry 6      <- the control
payload  signal_columns 6, pair_columns 7, signal_rows 2, pair_rows 1
drew true, reasonFor null, faults []
```

The panel drew, reported no fault, and stamped no table element while its
payload carried both column sets and three rows.

### 3.2 reproduction

```
electron <tree>/desktop --user-data-dir=<scratchpad> --remote-debugging-port=9351
ACERVATOR_BRIDGE_ARGV="-m src.core.desktop_bridge"
acervatorTabBar.select('market_inspector')
acervatorPanelHost.mount('market_inspector', host, payload)
```

The counter is controlled in the same document. One element carrying
`data-part="grid-row"` was added to the body and removed again:

```
planted grid-row   1
page grid-row      0
```

### 3.3 the cause

`TableGroup` was defined and exported and never placed in the element tree.
`Screen` builds `Split`, which builds `LeftPane` and `TopologySlot`; `LeftPane`
builds one `ModuleGroup` per left zone and nothing else. `Grid`, `EmptyNote`,
`HeadCell`, `BodyRow`, `BodyCell` and `tableHeight` were reachable only from
`TableGroup`.

### 3.4 the correction

The module drops those seven components, the four model readers, the two table
checks and every field name that only they read. The surface stops publishing
`signal_columns`, `pair_columns`, `signal_rows`, `pair_rows`, the two group
titles, the two maximum heights, the four `table_*` settings, `no_cell`,
`scan_state` and `empty_texts`. The stylesheet drops the six rules for parts
nothing stamps.

### 3.5 the rerun

```
table-group 0, grid 0, grid-row 0, head-cell 0, empty-note 0
module-group 6, module-legend 6, zone-entry 6
payload  signal_columns 0, pair_columns 0, signal_rows 0, pair_rows 0
drew true, reasonFor null, faults []
acervatorMarketInspector.TableGroup   undefined   (function before)
```

The React picture is byte-identical before and after: 86,476 bytes, sha256
`7a09b1aed503398a`. The drawn markup of the panel matches byte for byte at
21,194 characters, sha256 `15d071bf0e68bd7a`.

---

## 4 — The control on the comparison

The markup comparison must be able to report a difference. One part name was
changed from `module-group` to `module-group-broken`, the same payload was
driven, and the file was restored byte for byte afterwards.

```
after     markup 21194 chars  sha256 15d071bf0e68bd7a  module-group 6
control   markup 21236 chars  sha256 4ec708dbdb832c47  module-group 0
identical False
```

Renaming one part moved the markup and drove the control count to zero, so the
byte-identical result above is a fact about the page and the zero counts are
facts about the page.

---

## The two pictures, table by table

Every row below was read off the two pictures named at the top, never off the
payload or a view model.

| # | item | Qt picture | React picture |
| --- | --- | --- | --- |
| 1 | HTF Signals column headers | none drawn | none drawn |
| 2 | HTF Signals rows | none drawn | none drawn |
| 3 | HTF Signals row order | no rows to order | no rows to order |
| 4 | HTF Signals empty sentence | none drawn | none drawn |
| 5 | Opposing Pairs column headers | none drawn | none drawn |
| 6 | Opposing Pairs rows | none drawn | none drawn |
| 7 | Opposing Pairs row order | no rows to order | no rows to order |
| 8 | Opposing Pairs empty sentence | none drawn | none drawn |

**Items 1 to 8 match at nothing on both sides, and that proves nothing about
either renderer.** The comparison was given rows that could have failed it: the
scan produced two signal rows and one pair row, and the Qt and React tabs both
held them at the moment the picture was taken.

The pair row does reach both pictures, in the zone the layout gives it, and
those items can fail:

| # | item | Qt picture | React picture |
| --- | --- | --- | --- |
| 9 | Opposing Trades stepper | `1 of 1` | `1 of 1` |
| 10 | pair headline | `ZEC (ENTRY_LONG_MEDIUM) ▸ IMX (ENTRY_SHORT_MEDIUM)` | the same |
| 11 | pair meta | `score 1.20 • correlation -0.999` | the same |
| 12 | pair method | `Cointegration • 365d • p=0.0000 · trace 1790.2>15.5` | the same |
| 13 | pair hint | `Click the entry for how and why it is here.` | the same |
| 14 | HTF Signals zone | `0 of 0`, `Phantom Bot source not wired.` | the same |
| 15 | the other five zone titles | ATA-SPM, Multi-Exchange Arbitrage, Ready to Send, Bot Swarm Topologies | the same |

Item 14 is where the signals went. The scan produced three, the screen shows
none, and the zone reserved for them says its source is not wired.

## What the rows read

Rows 878 and 879 stay `yes` under Registers in Electron, and the flip is now
earned on evidence that can fail. `acervatorPanelHost.registered()` names
`market_inspector` and `market_inspector_topologies` in the running shell,
`reasonFor` answers null for both, the Inspector tab and the proposals pane draw
in both pictures, and the control above shows the reading reports a difference
when one part name changes.

## What the screen still does not do

The Include active markets check box filters the signal list, and no zone draws
that list. Pressing it changes nothing a viewer can see, on either side, before
this change and after it. The reserved Phantom Bot zone is where those rows
belong once a source is wired.
