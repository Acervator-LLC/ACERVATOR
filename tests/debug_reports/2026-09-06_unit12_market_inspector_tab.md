# `src/gui/live_settings/market_inspector_tab.py`

The Market Inspector tab of the Live Bot Settings window. Qt draws the per-bot
card. React drew a Python error message instead. Both sides now draw the same
screen from one description.

## Edits

`src/gui/main_tabs/market_inspector_tab_surface.py` gains `per_bot_view`. It
reads the shared analyzer through `get_shared_inspector` and returns the whole
screen as values: the rows, the groups, the words, the colours and the layout
numbers. `row_html` and `row_style` turn one row into the rich text and the
style sheet a Qt label wears. `group_style` returns the Qt style sheet that
gives a group box the card shape `bot_live_settings.css` draws every group of
this window in. `SharedAnalyzerSource` is the builder the tab delegates to, and
`MarketInspectorTabModel` now takes it when no other source is given.

`src/gui/market_inspector.py` — `build_per_bot_view` now draws the rows and
groups `per_bot_view` returns. It holds no wording of its own. `_per_bot_label`
builds one label from one row.

`src/gui/live_settings/market_inspector_tab.py` — the failure screen now takes
its words, its colour, its padding and its layout numbers from the same surface
through `fallback_text`, `fallback_style` and `LAYOUT_MARGIN_PX`.

`src/gui/web/market_inspector_tab.js` — `ViewSlot` was an empty box. It now
draws the view: `Row` draws one line with its colour, size, font and padding,
and `Group` draws one card. `Fallback` takes the same margins as the Qt layout.
The payload carries a new `layout` field and the module reads it.

`desktop/main.js` — `bridgeArguments` reads `ACERVATOR_BRIDGE_ARGV`, so the
shell can be pointed at the bridge module alone. Unset, it starts the trading
program exactly as before. The window no longer names a background colour; it
stays hidden until the page has painted.

## Errors detected

The React side of this tab drew a Python error. Driven under `python -X dev -X
faulthandler` with `PYTHONWARNINGS=error`, through `react_bot_live_settings`
`tab_payload`, which is the call the Live Bot Settings window makes for every
tab:

```
DIALOG delegated False message '<b>Market Inspector unavailable.</b><br><br>AttributeError: 'NoneType' object has no attribute 'build_per_bot_view''
DIALOG order ['QLabel', 'stretch']
DIALOG warnings ['Market Inspector per-bot view unavailable: 'NoneType' object has no attribute 'build_per_bot_view'']
```

The cause is in `market_inspector_tab_surface`. `tab_payload` builds
`MarketInspectorTabModel(bot)` and calls `build_view_model(model,
build_now=True)`. `MarketInspectorTabModel.build` then ran
`self.source.build_per_bot_view(self.bot)` with `source` set to `None`. The
method catches `Exception`, so the failure it made itself became the screen.

The Qt side, on the same empty state, drew the real screen:

```
QLabel 9 9 622 104 | color: #aaa; padding: 12px;
'<b>No Market Inspector scan yet.</b><br><br>Open the Market Inspector top-level tab and press Refresh to populate. ...'
```

A second error sat behind the first. `market_inspector_tab.js` `ViewSlot`
returned an empty box, so even a delegation that answered drew nothing. The
per-bot card, the higher-scoring markets and the opposing pairs had no React
drawing at all.

A third error was reported by the GUI archetype on `desktop/main.js`:

```
gui-js GUIJS003 high line 165
colour literal #0a0a0f is written into the module. design_tokens.js serves
every colour from the Python surface, so a literal here is a second source of
truth for one skin and cannot follow a theme change.
```

## Resolution

The same three calls, rerun:

```
DIALOG delegated True message ''
DIALOG view {"available": true, "asset": "BTC", "spacing_px": 8, "margin_px": 9,
 "rows": [{"parts": [{"text": "No Market Inspector scan yet.", "bold": true, "breaks": 0},
 {"text": "Open the Market Inspector top-level tab and press Refresh to populate. ...",
 "bold": false, "breaks": 2}], "color": "#aaa", "word_wrap": true, "padding_px": 12}],
 "groups": [], "stretch": true}
BRIDGE delegated True message ''
CONTROL delegated False message '<b>Market Inspector unavailable.</b><br><br>RuntimeError: no scan'
```

The third line is the control. A real failure still fills the failure screen, so
the repair did not blind it.

The Electron shell, driven through the panel host:

```
drew true   faults []   loadError null   delegated true
row part x 9 y 185.4 w 622 h 108 color rgb(170, 170, 170) padding 12px
text 'No Market Inspector scan yet. Open the Market Inspector top...'
```

The GUI archetype on `desktop/main.js` after the colour literal was taken out:

```
gui desktop/main.js exit=0 passed=True scanned=True
tool_availability {"gui-js":"ok","scaffolding":"ok","hallucination":"ok"}
```

### Dimensions, read off the real objects

The tab page at 640 by 600 on both sides. Qt geometry comes from
`QWidget.geometry`. React geometry comes from `getBoundingClientRect` in the
page.

No scan, which is the state the operator reaches today:

| what | Qt | React |
| ---- | -- | ----- |
| page | 640 x 600 | 640 x 600 |
| layout margins | 9, 9, 9, 9 | 9px |
| message box | x 9, y 9, w 622 | x 9, y 9, w 622 |
| message height | 104 | 114 |
| message padding | 12 | 12 |
| colour | #aaa | rgb(170, 170, 170) |
| wrapping | on | on |
| headline in bold | yes | yes |
| blank lines under it | 2 | 2 |
| space below | stretch | 622 x 460 |

After a scan, driven with three signals and one pair:

| what | Qt | React |
| ---- | -- | ----- |
| asset card | x 9, y 9, w 622, h 100 | x 9, y 9, w 622, h 109.1 |
| signal row | x 18, y 42, w 604, h 18 | x 17.8, y 41.8, w 604.4, h 19.5 |
| 1d row | x 18, y 66, h 16 | x 17.8, y 67.3, h 18 |
| 1w row | x 18, y 88, h 16 | x 17.8, y 91.3, h 18 |
| higher-scoring card | x 9, y 121, w 622, h 78 | x 9, y 126.1, w 622, h 83.6 |
| opposing pairs card | x 9, y 207, w 622, h 58 | x 9, y 217.7, w 622, h 59.6 |
| card order | asset, higher, pairs | asset, higher, pairs |
| signal colour | #00ff88 | rgb(0, 255, 136) |
| higher row colours | #ff3366, #ffcc00 | rgb(255, 51, 102), rgb(255, 204, 0) |
| higher row font | monospace | monospace |

Every left edge and every width matches within 0.4 of a pixel. The heights and
the drift down the column are line height: a 12 pixel row measures 16 in Qt and
18 in the browser, and a 13 pixel row measures 18 and 19.5. That is a font
difference and it is the only one left.

Two colours also differ and both are the window's own. The card title is the
accent colour in React and the plain text colour in Qt, and the card border
takes the theme border colour rather than the Windows frame.

### Controls

The panel drove twenty-three named parts in the scanned state and six in the
empty state, read back off the page. The Qt side reports the same counts as
widgets. The failure screen is the negative control above.

`~/.acervator/settings.json` before `f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423`
and after `f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423`.
Nothing under the runtime tree was written.

### The manual figure

The manual page for this screen is *The window a bot row opens* in
[08-tabs.md](../../docs/manual/08-tabs.md), with the reference page
[market-inspector.md](../../docs/manual/08-tabs/market-inspector.md). Neither
cites a figure, so no figure was taken. The figure on the Market Inspector Tab
page belongs to the top-level tab, which is a different screen.
