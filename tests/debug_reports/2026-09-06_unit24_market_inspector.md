# Unit 24 — src/gui/market_inspector.py

Stage A of issue #407. The Market Inspector tab, compared side by side against
`MarketInspectorReactTab` and against the same screen drawn in the Electron
shell.

Manual figure for this screen: `docs/audits/2026-09-06_units/unit24_manual_market_inspector.png`,
taken from page 113 of `docs/Acervator-Product-Manual.pdf` with `pypdf`. The
manual calls it "The Market Inspector tab, before the first scan." That is the
only figure the manual gives this screen. The scanned state has no figure.

Renders:

```
docs/audits/2026-09-06_units/unit24_market_inspector_qt.png
docs/audits/2026-09-06_units/unit24_market_inspector_react.png
docs/audits/2026-09-06_units/unit24_market_inspector_electron.png
docs/audits/2026-09-06_units/unit24_market_inspector_qt_scanned.png
docs/audits/2026-09-06_units/unit24_market_inspector_react_scanned.png
```

## Edits

`src/gui/market_inspector.py` — `MarketInspectorTab.current_topology_proposals`
now answers `None` when the right pane never built or refused the read, and a
list when the pane answered. An empty list therefore means the pane holds no
proposals. Before this the method answered `[]` for both, which is the defect
issue #407 names.

`src/gui/main_tabs/market_inspector_surface.py` —
`MarketInspectorScreenModel.current_topology_proposals` takes the same two
answers, so the React side and the Qt side report the same thing. The module
also publishes two new layout values, `TABLE_VIEWPORT_PX` and
`SPLITTER_HANDLE_PX`, both measured off the running Qt widgets.

`src/gui/main_tabs/simulator_tab.py` — `SimulatorTabMixin._build_simulator_tab`
hands `None` on to the Simulator when there is no Market Inspector to ask. It
handed `[]`, which threw the distinction away one step later.

`src/gui/web/market_inspector.js` — three layout corrections.

- `tableHeight` gives each table body the height the Qt table draws, cut short
  by the group's own maximum. The body had no height at all, so an empty table
  drew nothing.
- `Split` keeps a gap the width of the Qt splitter's drag handle, so the two
  panes share what is left instead of the whole tab.
- `Grid` sizes the table to its content when the payload asks for
  `ResizeToContents`, which is what the Qt table does. It was stretched to the
  full width, so every column was wider than its Qt twin.
- `fillSlot` draws the proposals pane into the right-hand slot when no host has
  claimed it. A Qt host moves its own pane in and declares
  `acervatorMountTopologies`, so the slot is left alone there.

`src/gui/react_market_inspector_tab.py` — the screen root fills the view, so the
screen's own full height resolves against it.

`docs/manual/05-novel-concepts.md` — one line inside a code block, `else []`
changed to `else None`, so the quoted code matches
`SimulatorTabMixin._build_simulator_tab`. No sentence was added, removed or
reworded.

## Errors detected

### 1 The reported shell error does not reproduce

The item carries this from an earlier launch of the shell:

```
Market Inspector unavailable.
AttributeError: 'NoneType' object has no attribute 'build_per_bot_view'
```

Driven again through the running Electron shell against
`python -m src.core.desktop_bridge`, both calls answer:

```
MI_TAB_STATE {"message": "", "error_type": "", "error_text": "", "delegated": false}
MI_TAB_BUILD {"message": "", "error_type": "", "error_text": "", "delegated": true}
CONSOLE: []
```

`MarketInspectorTabModel` in `market_inspector_tab_surface` now takes a
`SharedAnalyzerSource` when no source is handed in, so the read that raised
cannot happen. Unit 12 closed it. This run is the re-check, not a new fix.

### 2 The React screen did not fill the tab

Read off the real objects, empty state, both sides sized to 1400 by 860:

```
Qt    splitter        1400 x 860      panes 697 and 696
React screen           1400 x 224     left pane 224 tall, right pane 224 tall
Shell screen           1386 x 206
```

`Screen` in `market_inspector.js` asks for its full height. Its host carried no
height, so the request resolved to the content height.

### 3 Both tables drew no body

```
Qt    HTF Signals table     665 x 192       Opposing Pairs table  665 x 180
React table body            665 x 0         table body            665 x 0
```

The Qt table keeps the same 192 px viewport whatever the row count, measured at
0, 1, 3, 8, 20 and 40 rows, and the group's own maximum cuts it to 180 for
Opposing Pairs. `TableGroup` set a maximum and no height, and a maximum on
empty content is nothing.

### 4 The right half of the screen was blank in the Electron shell

```
window.acervatorMountTopologies   undefined
elements carrying data-part=pane  0
parts drawn in the panel          34
```

`acervatorMountTopologies` is declared by the host script in
`react_market_inspector_tab`, which only runs inside the Qt web view. In the
shell nothing put the proposals pane into the slot, so half the screen was
empty.

### 5 Every column was wider than its Qt twin

Scanned state, three markets and one pair:

```
Qt    HTF Signals columns   57  121  58  132  118  63
React HTF Signals columns   59  158  60  170  154  65
```

The payload asks for `ResizeToContents`. The Qt table sizes each column to its
content and leaves the slack at the right. The React table was stretched to the
full width, so the slack was shared out across the columns.

### 6 The two panes took the splitter's drag handle

```
Qt    left pane 697   handle 7   right pane 696 at x=704
React left pane 701              right pane 699 at x=701
```

### 7 Both variants build clean under the strictest interpreter mode

```
PYTHONWARNINGS=error python -X dev -X faulthandler ...
=== ACERVATOR_VARIANT=qt ===
variant qt class MarketInspectorTab
proposals []
scan_state not_asked
EXIT=0
=== ACERVATOR_VARIANT=react ===
variant react class MarketInspectorReactTab
proposals []
scan_state not_asked
EXIT=0
```

### 8 One run under debugpy answered nothing

```
COMMAND: python -m debugpy --listen 5678 main.py --bridge
OSError: [Errno 22] Invalid argument
STDOUT frames: 0
```

The child closed its side of the pipe within twelve seconds and wrote no frame.
I did not isolate whether the cause is the child or my pipe, so this is recorded
and not claimed as a defect. The same two requests answer `ok=true` through
`python -m src.core.desktop_bridge`, and the shell draws the panel from that
same backend.

## Resolution

### The two proposal states are now told apart

Same method, four states, on the real tab:

```
A pane built, no proposals   -> []
B pane built, one proposal   -> [{'archetype': 'sector_cluster', 'assets': ['PEPE']}]
C pane never built           -> None
D pane refuses the read      -> None
```

And on the React model that feeds the page:

```
surface, no pane             -> None
surface, pane with one       -> [{'archetype': 'momentum_funnel'}]
surface, pane with none      -> []
```

### Dimensions, after the corrections

Read off the Qt widgets and off the page's own elements, both sized 1400 by 860.
Eighteen of twenty-nine measurements are identical.

```
MATCH   tab size                     qt=[1400, 860]  react=[1400, 860]
MATCH   left pane width              qt=[697]  react=[697]
MATCH   left pane height             qt=[860]  react=[860]
MATCH   right pane x                 qt=[704]  react=[704]
MATCH   right pane width             qt=[696]  react=[696]
MATCH   right pane height            qt=[860]  react=[860]
DIFFER  Refresh button size          qt=[88, 36]  react=[65, 24]
DIFFER  include-active width         qt=[158]  react=[136]
MATCH   status line width            qt=[141]  react=[141]
MATCH   HTF group x                  qt=[6]  react=[6]
MATCH   HTF group width              qt=[685]  react=[685]
DIFFER  HTF group height             qt=[273]  react=[253]
DIFFER  HTF table width              qt=[665]  react=[662]
MATCH   HTF table height             qt=[192]  react=[192]
MATCH   HTF column count             qt=[6]  react=[6]
MATCH   Pairs group x                qt=[6]  react=[6]
MATCH   Pairs group width            qt=[685]  react=[685]
DIFFER  Pairs group height           qt=[264]  react=[241]
DIFFER  Pairs table width            qt=[665]  react=[662]
MATCH   Pairs table height           qt=[180]  react=[180]
MATCH   Pairs column count           qt=[4]  react=[4]
DIFFER  scanned HTF table height     qt=[207]  react=[192]
MATCH   scanned Pairs table height   qt=[180]  react=[180]
DIFFER  scanned row height           qt=[30]  react=[22]
MATCH   scanned HTF col 2 width      qt=[121]  react=[121]
DIFFER  scanned HTF col 4 width      qt=[132]  react=[131]
MATCH   scanned HTF col 5 width      qt=[118]  react=[118]
DIFFER  scanned Pairs col 1 width    qt=[153]  react=[151]
DIFFER  scanned Pairs col 2 width    qt=[125]  react=[124]
```

The eleven that differ, and what each is:

- Refresh button and the Include-active control. Both sides draw the same
  control with the same words. The sizes differ by the padding each toolkit puts
  round a button and round a check box.
- Group heights, 20 px and 23 px. The Qt group box reserves a band for its title
  above the frame. The web group puts its title on the border line. Both bands
  are one line of text.
- Table widths, 3 px each. The web group's border is thicker than the Qt frame,
  so 3 px less is left inside.
- Scanned HTF table height, 15 px. When rows arrive the Qt table takes the space
  the hidden placeholder line leaves behind. That space is one line of text.
- Scanned row height, 30 against 22. Each toolkit builds its own row box round
  the same 12 px font.
- Three column widths inside 2 px. The columns whose width comes from their
  content now match to 1 px or exactly: 121 against 121, 132 against 131, 118
  against 118, 153 against 151, 125 against 124. The columns whose width comes
  from the heading text stay narrower on the web side by the heading padding.

Every remaining difference is padding, a border, or one line of text. Nothing
moved, nothing changed order, and nothing is missing.

### Values, driven and read back

Every control was pressed on the React page, and the answer read off the real
Python object.

```
AFTER switch click: python _show_active = True | checkbox on page = True
AFTER refresh click, no exchange wired: python status = 'Exchange source not wired - restart the app after connecting an exchange.'
  page status = 'Exchange source not wired - restart the app after connecting an exchange.'
AFTER refresh click, exchange wired: scan_state = running pending = True scheduled = 1
  python status = 'Fetching...' | page status = 'Fetching...'
  refresh enabled on page = False
AFTER scan lands: python rows signals = 3 pairs = 1
  page grid rows = 4
```

The cells the page drew, against the cells the Qt table drew, for the same three
markets and one pair:

```
Qt    [["BTC","ENTRY_LONG_HIGH","0.91","▲ bb=0.82 z=+1.40 T","▼ bb=0.21 z=-0.70","—"], ...]
React [["BTC","ENTRY_LONG_HIGH","0.91","▲ bb=0.82 z=+1.40 T","▼ bb=0.21 z=-0.70","—"], ...]
```

All four rows are identical character for character on both sides, and both
status lines read `Live CoinGecko  ·  3 markets  ·  just now`.

### The Electron shell

Same panel, same backend, after the corrections:

```
before   screen 1386 x 206   right pane absent   parts drawn 34
after    screen 1382 x 545   right pane 687 x 545   parts drawn 48
         table bodies 192 and 180, matching the Qt tables
         console messages: none
```

The right pane now carries its top row, its list group, its scroll area and its
footer. The gap between the panes is 7 px, the same drag-handle width the Qt
splitter keeps.

### Two things this unit did not take

- The proposals pane fills its slot in the shell but stops at 81 px inside the
  Qt web view. That pane is `market_inspector_topologies.js`, which is unit 25.
- The shell's page loads no style sheet for this panel, so its headings run
  together there. `desktop/renderer/index.html` links only the History sheet and
  the tab-bar sheet. `market_inspector.css` cannot be added as it stands,
  because it sets a page-wide height and selects on `data-part` names other
  panels also use. That is a shell-wide change, not a change to this row.

### The conversion table

Row 24 reads `yes` in every column, and every cell was confirmed against a
running program rather than read back off the table:

```
React module            src/gui/web/market_inspector.js on disk
Uses React              the page draws through ReactDOM, 4 rows appeared
Bridge                  market_inspector.state answered ok=true
Manifest                named in desktop/renderer/module_manifest.js
Registers in Electron   the shell drew a Market Inspector tab and its panel
Ships in the build      desktop/renderer/index.html loads the module
RENDERS                 rendered in the Qt web view and in the shell
```

No cell changes, so the row and the totals block are unchanged. The proof that
no manual sentence was touched:

```
git diff 9f2f29c -- docs/ | grep "^-" | grep -v "^---" | grep -v "^-|"
-            else []
```

The one line is the code-block correction described under Edits.

### Gate

```
coding_archetype  src/gui/market_inspector.py                     passed=True
coding_archetype  src/gui/react_market_inspector_tab.py           passed=True
coding_archetype  src/gui/main_tabs/market_inspector_surface.py   passed=True
coding_archetype  src/gui/main_tabs/simulator_tab.py              passed=True
gui_archetype     src/gui/market_inspector.py                     passed=True
gui_archetype     src/gui/react_market_inspector_tab.py           passed=True
gui_archetype     src/gui/web/market_inspector.js                 passed=True
```

No high or critical finding, and every tool reported `ok`. The fixture controls
ran first:

```
coding_archetype known_good exit=0 passed=true    known_bad exit=1 passed=false
gui_archetype    known_good_widget.py exit=0      known_bad_widget.py exit=1
gui_archetype    known_good_screen.js exit=0      known_bad_screen.js exit=1
docs_archetype   known_good exit=0                known_bad exit=1
```

`black --check` and `flake8` both exit 0 on the four Python files.

`docs_archetype` on `docs/manual/05-novel-concepts.md` reports `passed=False`
before my edit and after it. The single high finding is a style rule on a
sentence the operator wrote himself, and the brief forbids rewording any manual
sentence, so the sentence stands.

### Safety

Every run used a throwaway home. `~/.acervator/settings.json` is unchanged:

```
before f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
after  f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
```

No network call, no credential, no test run. The running platform was never
started, stopped or queried.

### What the operator sees differently

The Market Inspector in the React build now draws the same screen as the Qt
build: both tables at full size, the panes split the same way, and the proposals
pane appears in the Electron shell where before that half of the screen was
blank.
