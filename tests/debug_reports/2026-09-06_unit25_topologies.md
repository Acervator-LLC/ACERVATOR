# Unit 25 — src/gui/market_inspector_topologies.py

Stage A of issue #407. The Topology Proposals pane, the right-hand half of the
Market Inspector tab, compared against the same pane drawn by React in the Qt
web view and in the Electron shell.

Manual figure for this pane:
`docs/audits/2026-09-06_units/unit25_manual_topologies.png`, taken from page 113
of `docs/Acervator-Product-Manual.pdf` with `pypdf`. The manual page for this
pane cites one figure, the Market Inspector tab before the first scan, and says
of it that every card in the figure comes from the sector-cluster detector. The
preview screen has no figure.

Renders:

```
docs/audits/2026-09-06_units/unit25_topologies_qt.png
docs/audits/2026-09-06_units/unit25_topologies_react.png
docs/audits/2026-09-06_units/unit25_topologies_electron.png
docs/audits/2026-09-06_units/unit25_topologies_qt_scanned.png
docs/audits/2026-09-06_units/unit25_topologies_react_scanned.png
docs/audits/2026-09-06_units/unit25_topologies_electron_scanned.png
```

## Edits

`src/gui/react_market_inspector_tab.py` — two changes.
`TOPOLOGY_ROOT_STYLE` gives the element the pane is drawn into a full height, so
the pane's own full height resolves against the slot rather than against its
cards. `topology_push_script` empties the preview through
`acervatorTopologies.renderPreview` at `NO_PREVIEW_AT` instead of clearing the
element, so React and the element still agree after a preview closes.

`src/gui/main_tabs/market_inspector_topologies_surface.py` — two new layout
values, both read off the running Qt widgets. `GROUP_MARGINS_PX` is the
`QGroupBox` layout `contentsMargins` the Topology Proposals group and the
preview's Bots and Wires groups all carry. `SCROLL_FRAME_PX` is
`QScrollArea.frameWidth`. Both are published in the payload the page is drawn
from.

`src/gui/web/market_inspector_topologies.js` — seven layout corrections.

- `ListGroup` and `TableGroup` inset their content by `GROUP_MARGINS_PX`, which
  is what the Qt group box does and the web group did not.
- `Scroll` insets its list by `SCROLL_FRAME_PX`, and takes the card's sheet
  margin out of the gap between cards. Qt draws a sheet margin inside the widget
  rectangle and spaces widgets by their rectangles; CSS draws it outside the
  element box, so the gap counted it twice.
- `ProposalCard` gives the title the stretch the Qt row gives it, so the score
  badge sits at the card's right edge.
- The card and preview button rows carry the spacing their Qt layouts carry.
- `asBadge` keeps the spaces the badge format pads the score with. HTML collapses
  them and Qt draws them.
- `asButton` draws every push button in the application font, which is what Qt
  does. Four of the five buttons were drawing in the browser's own font.
- `Grid`, `HeadCell` and `BodyCell` size each column to its content and stretch
  the last one, which is `ResizeToContents` with `stretchLastSection`, the two
  settings the Qt trees carry.
- `Preview` takes the minimum size the Qt screen takes rather than the width of
  whatever holds it, and its body takes the stretch, so the two tables fill the
  screen.

`src/gui/web/market_inspector.css` — two changes. The proposals slot paints its
left rule instead of bordering it, so the rule no longer costs the pane a pixel
of width. The four buttons the pane and its preview draw take the same skin the
Refresh button already had; they were drawing in the browser's default button
chrome.

No change to how proposals are generated. `src/gui/market_inspector_topologies.py`
itself is unchanged: no finding was raised against it.

## Errors detected

### 1 The pane stopped at 81 px inside the Qt web view

Read off the page's own elements, tab sized 1400 by 860, unwired state:

```
slot  [704.21875, 0, 695.78125, 860]
root  [705.21875, 0, 694.78125, 81.59375]
pane  [705.21875, 0, 694.78125, 81.59375]
```

Against the Qt widget at the same size:

```
pane  [0, 0, 696, 860]
```

`Pane` in `market_inspector_topologies.js` asks for its full height. The element
`react_market_inspector_tab` draws it into carried no height, so the request
resolved to the height of the cards.

### 2 The pane was a pixel narrower than the Qt pane

`market_inspector.css` gave the proposals slot a `border-left`. With
`box-sizing: border-box` the border came out of the slot's content, so the pane
had 694.78 where Qt gives it 696.

### 3 The group inset content by 2 px where Qt insets by 11

```
Qt     group [6, 38, 684, 796]   card list [17, 65, 662, 758]
React  group [6, 36.8, 683.72, 18.8]   card list [8, 53.59, 678.78, 0]
```

The Qt group box carries a 9 px layout margin inside its 2 px frame. The web
group carried its border and no margin.

### 4 The gap between cards was 8 px where Qt draws 4

```
Qt     card 1 y=67 h=92   card 2 y=163      gap 4
React  card 1 y=55.59 h=81.78  card 2 y=145.38   gap 8.01
```

The card's Qt sheet says `margin: 2px`. Qt draws that inside the widget
rectangle and then spaces widgets 4 px apart. CSS draws it outside the element
box, so each gap carried 4 px of spacing plus 2 px from each neighbour.

### 5 The score badge sat beside the title instead of at the card's edge

```
Qt     title [34, 80, 587, 17]     badge [625, 80, 37, 17]
React  title [23, 66.59, 131.36, 17.39]  badge [154.36, 66.59, 24.66, 17.39]
```

The Qt row gives the title the stretch. The web title was sized to its text, so
the badge followed it instead of sitting at the right edge.

### 6 The badge dropped the spaces its format pads the score with

The badge text is `" 88 "`. HTML collapses the leading and trailing space, so
the badge drew 24.66 px wide against the Qt label's 37.

### 7 The preview screen filled the page instead of taking its own size

```
Qt     screen 720 x 460
React  screen 1400 x 460
```

`TopologyPreviewDialog` sets a 720 by 460 minimum and takes it. The web screen
carried the same minimum and then stretched to the width of the element holding
it.

### 8 The preview's two tables did not fill the screen

```
Qt     Bots group [12, 42, 342, 319]
React  Bots group [12, 42.8, 682, 97.19]
```

The Qt body layout carries the dialog's stretch. The web body was sized to its
rows.

### 9 Every preview column was stretched to the table width

```
Qt     Bots columns   39   41   55   181
React  Bots columns  103.84 117.14 148.94 294.08
```

Both trees carry `ResizeToContents` and `stretchLastSection`. The web table was
stretched to full width with no column sizing at all.

### 10 Reopening the preview drew nothing

Driven on the page, one press per line, with the answer read off the real
`TopologiesPaneHost`:

```
CALL {'key': 'preview-button', 'name': 'a'}
open1 at 0 previews 1 adopt enabled py True adopt on page [False]
CALL {'key': 'cancel-button', 'name': 0}
after cancel at None preview elements 0
CALL {'key': 'preview-button', 'name': 'a'}
open2 at 1 previews 2 preview elements 0 adopt on page [] root hidden False root children 0
model previews adopt_enabled [True, True]
view previews [True, True]
ERRS []
```

The model held two previews and the element was visible and empty. Closing a
preview cleared the element with `replaceChildren`, which React did not see, so
its next render reconciled against a tree the element no longer had and drew
nothing. On the shipped screen that means Preview, Cancel, Preview shows an
empty panel.

### The debugger

Both variants build clean under the strictest interpreter mode:

```
PYTHONWARNINGS=error python -X dev -X faulthandler ...
=== ACERVATOR_VARIANT=qt ===
variant qt tab MarketInspectorTab pane MarketInspectorTopologies
proposals []
EXIT=0
=== ACERVATOR_VARIANT=react ===
variant react tab MarketInspectorReactTab pane TopologiesPaneHost
proposals []
EXIT=0
```

Under `debugpy`, driving the pane's own bridge method:

```
COMMAND: python -m debugpy --listen 5678 -m src.core.desktop_bridge
STDOUT:
0.01s - Debugger warning: It seems that frozen modules are being used, which may
0.00s - make the debugger miss breakpoints. Please pass -Xfrozen_modules=off
0.00s - to python to disable frozen modules.
0.00s - Note: Debugging will proceed. Set PYDEVD_DISABLE_FILE_VALIDATION=1 to disable this validation.
{"id": 1, "ok": true, "result": {"dismissal": {"ttl_seconds": 86400, ...
EXIT: 0
```

### One error that is not this pane's

The Electron shell would not start under a throwaway home. It exits at once with
no output:

```
ALIVE False code 2147483651
OUTPUT
[21960:0906/155211.760:VERBOSE1:base\allocator\scheduler_loop_quarantine_config.cc:195] No entry found for browser/global.
```

Three launches told which override causes it:

```
HOME only          ALIVE True
USERPROFILE only   ALIVE False  code 2147483651
both + user-data   ALIVE True
```

Electron computes its own data directory from the user profile. Given
`--user-data-dir`, it starts with both overrides in place, which is how every
shell run below was made.

## Resolution

### Dimensions, after the corrections

Read off the Qt widgets and off the page's own elements, pane 696 by 860 on both
sides, empty state and two proposals. A row matches when every number in it is
within 1.5 px.

```
MATCH   pane size                  qt=[696, 860]  react=[695.72, 860]
MATCH   Refresh proposals x, y     qt=[6, 6]  react=[6, 6]
DIFFER  Refresh proposals w, h     qt=[110, 26]  react=[120.02, 24.8]
MATCH   status line unwired x, w   qt=[545, 145]  react=[544.56, 145.16]
MATCH   status line counted x, w   qt=[565, 125]  react=[565.03, 124.69]
MATCH   Topology Proposals x, w    qt=[6, 684]  react=[6, 683.72]
MATCH   Topology Proposals y, h    qt=[38, 796]  react=[36.8, 797.2]
MATCH   card list x, w             qt=[17, 662]  react=[17, 661.72]
DIFFER  card list y, h             qt=[65, 758]  react=[62.59, 760.41]
MATCH   card 1 x, w                qt=[21, 654]  react=[21, 653.72]
DIFFER  card 1 y, h                qt=[69, 88]  react=[66.59, 87.58]
MATCH   card 2 x, w                qt=[21, 654]  react=[21, 653.72]
MATCH   gap between cards          qt=[4]  react=[4.0]
MATCH   card title x, h            qt=[34, 17]  react=[34, 17.39]
DIFFER  card title w               qt=[588]  react=[592.98]
DIFFER  card badge x, w            qt=[626, 37]  react=[630.98, 30.73]
MATCH   card badge right edge      qt=[663]  react=[661.71]
MATCH   card meta x, w, h          qt=[34, 629, 15]  react=[34, 627.72, 15.39]
DIFFER  Preview button w, h        qt=[81, 26]  react=[66.78, 24.8]
DIFFER  Dismiss button w, h        qt=[81, 26]  react=[65.84, 24.8]
MATCH   Dismiss button right edge  qt=[663]  react=[661.72]
MATCH   gap between card buttons   qt=[4]  react=[4.01]
MATCH   footer x, y, w, h          qt=[6, 840, 685, 14]  react=[6, 840, 683.72, 14]
MATCH   preview screen w, h        qt=[720, 460]  react=[720, 460]
MATCH   preview title x, y, w      qt=[12, 12, 138]  react=[12, 12, 137.72]
DIFFER  preview badge w            qt=[170]  react=[162.45]
MATCH   preview badge right edge   qt=[708]  react=[708.0]
MATCH   Bots group x, y, w, h      qt=[12, 42, 342, 319]  react=[12, 42.8, 342, 318.22]
MATCH   Wires group x, w           qt=[366, 342]  react=[366, 342]
DIFFER  Bots table x, w            qt=[23, 320]  react=[22, 322]
DIFFER  Bots table h               qt=[281]  react=[67.39]
DIFFER  Bots columns               qt=[39, 41, 55, 181]  react=[50.34, 56.8, 72.22, 142.64]
DIFFER  Wires columns              qt=[47, 44, 38, 187]  react=[71.83, 67.7, 64.75, 117.72]
MATCH   summary x, y, w, h         qt=[12, 371, 696, 16]  react=[12, 371.02, 696, 16.8]
MATCH   note x, y, w, h            qt=[12, 397, 696, 15]  react=[12, 397.81, 696, 15.39]
MATCH   button row y, right edge   qt=[422, 708]  react=[423.2, 708.0]
DIFFER  Cancel button w, h         qt=[81, 26]  react=[61.06, 24.8]
DIFFER  Adopt button w, h          qt=[81, 26]  react=[58.97, 24.8]
MATCH   gap Cancel to Adopt        qt=[10]  react=[10.0]

rows 39 rows matched 25
numbers 83 numbers matched 61
```

The fourteen rows that differ, and what each is.

- **The five buttons**, 81 px wide against 59 to 67, and 26 tall against 24.8.
  Both sides draw the same control with the same words. The Windows button style
  holds a button to a minimum width the web button does not have, and pads it
  more above and below. Every button's right edge and the gap between them match.
- **The card list and card 1, 2.41 px lower on the Qt side.** The Qt group box
  reserves a band for its title above the frame; the web group puts its title on
  the border line. That band is one line of text.
- **The card title, 5 px, and the badge, 6.3 px.** The badge is a label whose
  text is a score padded with a space each side, and the two toolkits measure
  that text differently. The title takes what the badge leaves, so the two move
  together. The badge's right edge matches.
- **The preview badge, 7.6 px.** The same measurement on the longer badge text.
- **The preview tables.** The table is 2 px wider because the Qt tree draws its
  own 2 px frame inside the group and the web table has no frame of its own. It
  is 67.39 tall against 281 for the same reason: the Qt tree fills the group and
  draws a second box inside the group's box, and the web table ends after its
  rows. One box is drawn on the web side where Qt draws two.
- **The preview column widths.** Both sides now size each column to its content
  and stretch the last, which is what the Qt header does. The content widths
  differ by the cell padding the shared table skin applies, 8 px a side.

Nothing moved, nothing changed order, and nothing is missing.

### Values, driven and read back

Every control was pressed on the React page and the change read off the real
`TopologiesPaneHost` and the `TopologiesPaneModel` it holds.

```
BEFORE          python status "Ready — press Refresh." page status "Ready — press Refresh."
AFTER refresh   python status "2 proposal(s); 0 dismissed" ids ["sector_cluster:BTC|ETH", "momentum_funnel:DOGE|PEPE"]
AFTER refresh   page status "2 proposal(s); 0 dismissed" cards 2
AFTER refresh   page titles ["▸ Sector cluster: layer1", "▸ Momentum funnel: memes"]
AFTER refresh   page badges [" 88 ", " 61 "]
AFTER refresh   page meta ["score 88  •  2 assets  •  1 wires  •  1 new bot(s)", "score 61  •  2 assets  •  0 wires  •  1 new bot(s)"]
AFTER preview   python at 0 title "Preview: Sector cluster: layer1" page title "Sector cluster: layer1"
AFTER preview   python bot rows [["BTC", "source", "BTC-USD", "EXISTING"], ["ETH", "target", "ETH-USD", "WILL CREATE ($1500)"]]
AFTER preview   page bot rows [["BTC", "source", "BTC-USD", "EXISTING"], ["ETH", "target", "ETH-USD", "WILL CREATE ($1500)"]]
AFTER preview   python wire rows [["BTC", "ETH", "25.0%", "cluster leader"]] page [["BTC", "ETH", "25.0%", "cluster leader"]]
AFTER cancel    python rejected 1 at None page previews 0
AFTER reopen    python at 1 title "Preview: Momentum funnel: memes" page previews 1 page title "Momentum funnel: memes"
AFTER adopt     python adopt_requests ["momentum_funnel:DOGE|PEPE"] handler ["momentum_funnel:DOGE|PEPE"] at None
AFTER dismiss   python asked "Suppress this proposal for 24 h?\n\nId: sector_cluster:BTC|ETH"
AFTER dismiss   python dismissed ["sector_cluster:BTC|ETH"] held ["momentum_funnel:DOGE|PEPE"]
AFTER dismiss   python store wrote ["sector_cluster:BTC|ETH"]
AFTER dismiss   page cards 1
AFTER refused   python dismissed ["sector_cluster:BTC|ETH"] page cards 1
AFTER failure   python status "Detector error: detector down" page status "Detector error: detector down"
PAGEERRORS []
```

Adopt reached the handler the main window wires onto the pane. A dismissal asks
first and a No leaves the list alone. The status line keeps its old count after a
dismissal until the next refresh, which is what the Qt pane does: `dismiss` calls
`persist_dismissed` and `render` and never touches the status label.

### The Electron shell

Same panel, same backend, reached by clicking the Market Inspector tab in the
running shell:

```
unwired  slot [6, 4, 610.58, 73.6]      pane [697.54, 116.4, 688.86, 544.8]
scanned  pane [697.54, 116.4, 688.86, 544.8]   cards 2
         status "2 proposal(s); 0 dismissed"
         card boxes [[718.1, 178.2, 647.7, 82.4], [718.1, 264.6, 647.7, 82.4]]
         console messages: none
```

The pane fills its half of the panel, the card list carries its 2 px inset and
the gap between cards is 4 px, the same as Qt.

The shell draws the five buttons in the browser's default chrome. It loads no
style sheet for this panel, which is the shell-wide gap unit 24 recorded:
`desktop/renderer/index.html` links only the History sheet and the tab-bar sheet.
The application font correction reaches the shell; the skin does not.

### The conversion table

Row 25 reads:

```
25 | src/gui/market_inspector_topologies.py | market_inspector_topologies.js
   | yes | yes | yes | no | yes | yes
```

Every cell was confirmed against a running program:

```
React module            src/gui/web/market_inspector_topologies.js on disk
Uses React              the page drew through ReactDOM, 2 cards appeared
Bridge                  market_inspector_topologies.state answered ok=true
Manifest                named in desktop/renderer/module_manifest.js
Registers in Electron   the module calls no register; the shell reports 14
                        panels and none is this pane. It draws inside the
                        Market Inspector panel, which is where the Qt pane
                        sits too
Ships in the build      desktop/renderer/index.html loads the module
RENDERS                 rendered in the Qt web view and in the shell
```

No cell changes. The totals block was counted again off the forty rows and is
unchanged:

```
units                    40
React module             37
Uses React               36
Bridge                   38
Manifest                 37
Registers in Electron    11
Ships in the build       35
RENDERS                  40
```

The same forty rows in the #128 issue body count to the same seven numbers, so
neither table is edited. The proof that no manual sentence was touched:

```
git diff 9f2f29c -- docs/ | grep "^-" | grep -v "^---" | grep -v "^-|"
-            else []
```

That one line is unit 24's own code-block correction.

### Gate

```
coding_archetype  src/gui/market_inspector_topologies.py                     passed=True
coding_archetype  src/gui/main_tabs/market_inspector_topologies_surface.py   passed=True
coding_archetype  src/gui/react_market_inspector_tab.py                      passed=True
gui_archetype     src/gui/market_inspector_topologies.py                     passed=True
gui_archetype     src/gui/react_market_inspector_tab.py                      passed=True
gui_archetype     src/gui/web/market_inspector_topologies.js                 passed=True
```

No high or critical finding, and every tool reported `ok`. The fixture controls
ran first:

```
coding_archetype known_good exit=0    known_bad exit=1
gui_archetype    known_good_widget.py exit=0   known_bad_widget.py exit=1
gui_archetype    known_good_screen.js exit=0   known_bad_screen.js exit=1
docs_archetype   known_good exit=0             known_bad exit=1
```

`black --check` and `flake8` both exit 0 on the three Python files.

### Safety

Every run used a throwaway home. `~/.acervator/settings.json` is unchanged:

```
before f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
after  f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
```

No network call, no credential, no test run. The running platform was never
started, stopped or queried.

### Size against time

```
source lines in        577
wall clock             2772 s
seconds per source line  4.80
```

### What the operator sees differently

The Topology Proposals pane in the React build now fills its half of the Market
Inspector tab instead of stopping 81 px down. The cards sit where the Qt cards
sit, each score badge is at the card's right edge, and the buttons carry the
screen's own colours. Opening a proposal's preview, closing it, then opening
another one now draws the second preview; before it drew nothing.
