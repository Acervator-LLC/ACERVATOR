# The Ready to Send thumbnail, its chart and the two layouts

Phase six was reported done and was not. The thumbnail drew an empty green
rectangle: no chart, and the ticker and the vote sat in one plain line. This unit
draws the chart the post carries, puts the ticker and the bull or bear word
beside it, opens the larger chart on a press, closes every dimension the two
builds did not share, shortens the topologies button, and removes TradingView
from the push targets.

**Nothing was sent to a real platform.** Phase five sent to
`ata_spm_push.RecordedDestination`, which keeps every artefact in memory and
answers the name `recorded-destination`. No network call was made and no real
credential exists in the tree. The only credentials stored were the strings
`key-<target>` and `signature-<target>`, typed into a `CredentialVault` built
inside the run and never written to disk.

Renders:

```
docs/audits/2026-09-06_units/bucket_thumbnails_qt.png
docs/audits/2026-09-06_units/bucket_thumbnails_react.png
docs/audits/2026-09-06_units/bucket_thumbnails_electron.png
docs/audits/2026-09-06_units/bucket_thumbnails_preview_react.png
```

The runtime tree was not touched. Every run set `HOME` and `USERPROFILE` to a
throwaway directory. `~/.acervator/settings.json` before and after:

```
sha256_before f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
sha256_after  f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
```

## Edits

`src/trading/ata_spm.py` — `ChartPull` gained `closes`, and `pull` fills it with
the close of every candle it read. That series is the only thing the chart needs
that phase three did not already carry.

`src/trading/ata_spm_push.py` — `FormattedPost` gained `closes`, and
`format_post` copies the series from the pull. `PUSH_TARGETS` lost its
TradingView row and `TARGET_TRADINGVIEW` is gone with it, so `TARGET_NAMES` is
now X, Instagram and LinkedIn. A target is still added by naming one row;
`format_post`, `distribute` and `ReadyToSend` read the row, never the name.

`src/gui/main_tabs/market_inspector_surface.py` — `post_strip` is replaced by
`post_chart`, which answers the chart one post draws at thumbnail or preview
size. `chart_closes` samples the series down to the column count, `chart_range`
answers the price band the chart is drawn between, `chart_row_px` puts one price
on a row, `chart_band_prices` keeps the Bollinger prices worth a rule, and
`chart_marks` answers every rectangle as its part, its box and its colour.
`post_vote` answers the bull or bear word and the colour it is drawn in.
`zone_entry` and `zone_view` carry `vote` and `headline_width_px` beside the
thumbnail and the preview. `push_action` gained `_press_thumbnail`, which opens
the Ready to Send expansion, and `THUMBNAIL_PART` joined `PUSH_PARTS`.
`action_row` carries a button width. `bucket_skin`, `settings_page` and
`ata_spm_skin` publish `PUSH_BUTTON_HEIGHT_PX`, `FIELD_HEIGHT_PX` and a width
for every control on the screen. `SECTOR_FIELD_WIDTH_PX` became
`SECTOR_FIELD_MIN_WIDTH_PX`, so the sector field takes the row's slack instead of
a width of its own.

`src/gui/market_inspector.py` — `_BandStrip` is replaced by `_PostChart`, which
fills each mark in `paintEvent` and reports a press through `clicked`.
`ProposalStepper` gained `vote_label`, wires the thumbnail press to
`actionPressed`, and sizes the headline from the width the view publishes.
`_show_strips` writes both charts, `_show_actions` sizes each button, and
`_on_push_action` opens the expansion on a thumbnail press. Every button, field
and check box in the tab takes the size the surface publishes, and the ATA-SPM
control row lost its stretch because the sector field is now the flexible item.

`src/gui/market_inspector_topologies.py` — the Refresh button takes
`REFRESH_TEXT` and `REFRESH_TOOLTIP` from the surface rather than its own two
string literals.

`src/gui/main_tabs/market_inspector_topologies_surface.py` — `REFRESH_TEXT`
reads `Refresh`.

`src/gui/web/market_inspector.js` — `BandStrip` is replaced by `PostChart` and
`ChartMark`, which place the same rectangles the Qt widget fills. `ZoneStepper`
draws the vote word beside the ticker and sizes the headline from the view.
`EntryAction`, `PushButton`, `ScanNowButton` and `SaveCredentialsButton` take
their width and height from the model. `fieldStyle` takes the field height.
`SectorField` takes the row's slack, `TimeframeBox` takes a published box size
and a part name a reader can find, and `AtaRow` lost its spacer.

`src/gui/web/market_inspector.css` — the page's scroll bars are 10 px wide with a
5 px radius, which is what `QScrollBar:vertical` is in `theme_engine`.

`src/gui/react_market_inspector_tab.py` — `PUSH_KEYS` is `surface.PUSH_PARTS`
rather than a second copy of the same six names.

`docs/manual/08-tabs.md` — the Market Inspector page gains the chart the
thumbnail draws, the push targets that ship, the published control sizes and the
topologies button wording. No sentence was deleted or reworded.

## Errors detected

### 1 The thumbnail press reached nothing in the Qt tab

The first Qt run died on the button the press was supposed to have drawn:

```
PYTHONWARNINGS=error python -X dev -X faulthandler bucketchart_qt_drive.py
Traceback (most recent call last):
  File "bucketchart_qt_drive.py", line 247, in <module>
    main()
    ~~~~^^
  File "bucketchart_qt_drive.py", line 153, in main
    names["approve-button"].click()
    ~~~~~^^^^^^^^^^^^^^^^^^
KeyError: 'approve-button'
```

`MarketInspectorTab._on_push_action` carries its own copy of the press map and
had no branch for the thumbnail, so the expansion never opened and Approve and
Decline were never built. `MarketInspectorScreenModel.push_action` had the
branch, which is why the page answered and the widgets did not. Corrected by
opening the Ready to Send expansion in `_on_push_action` on a thumbnail press.
The same run afterwards:

```
actions = ['Approve', 'Decline']
after Approve   state approved
after Decline   state declined
```

### 2 The chart placed its rectangles with no layout

The first `_PostChart` put one child frame per mark. The GUI archetype refused
the file:

```
python -m dev_harness.harness.gui_archetype src/gui/market_inspector.py
passed False {'gui-static': 9} {'high': 1}
gui-static:GUI003 line 318 [high]: setGeometry used without any QLayout - the
widget will not respond to resize / high-DPI / accessibil
```

Corrected by filling each mark in `paintEvent`, which is how Qt draws a chart,
and by having the mark carry its colour rather than a style sheet. The page
places the same boxes as elements, so both hosts read one mark list.

### 3 The ATA-SPM control row was wider than its pane

Read off the running widgets and off the page's own elements, the row overflowed
in both builds. The Qt sector field ended 11 px past where the layout put the
class box, and the page ran 6.2 px past the group's right edge:

```
qt   sector_field  [16, 56, 130, 37]     right edge 146
qt   class_box     [135, 56, 110, 37]    left edge 135
rc   ata_group     [6, 6, 684.5, 278.7]  right edge 690.5
rc   settings_button [600.7, 56.3, 96, 36] right edge 696.7
```

The two builds overflowed by different amounts, because the check-box labels take
different widths, and each build absorbs an overflow its own way. That is what
moved Settings and Scan Now apart. Corrected by publishing a width for the class
box, the four check boxes, Scan Now and Settings, and by making the sector field
the row's flexible item. The same row afterwards:

```
qt   sector_field  [16, 56, 72, 37]      rc [15.8, 55.8, 72, 37]
qt   settings_button [585, 56, 96, 36]   rc [585.8, 56.3, 96, 36]
```

### 4 The page's scroll bar was wider than the theme's

Save credentials fills the settings page, so its width is the page less the
scroll bar. Qt reported a 10 px bar and the page a 15.3 px one:

```
qt   settings_page [16, 99, 665, 175]  scrollbar 10  viewport [16, 99, 655, 175]
qt   save_button   [16, 228, 655, 36]
rc   save_button   [15.8, 227.8, 649.7, 36]
```

Corrected by giving the page's scrolling regions the 10 px width
`QScrollBar:vertical` declares in `theme_engine`. Afterwards: `qt [16, 228, 655,
36]` and `rc [15.8, 227.8, 655.3, 36]`.

### 5 The ticker line was as wide as its own text

With the vote word beside the ticker, the vote's position followed the width the
ticker text happened to take:

```
DIFFER headline_box  qt=[857, 137, 44, 36]  react=[856.1, 136.6, 40.4, 36]
DIFFER vote_box      qt=[905, 137, 24, 36]  react=[900.5, 136.6, 23.3, 36]
```

Corrected by publishing `BUCKET_HEADLINE_WIDTH_PX` with the entry, which the two
hosts both draw the ticker at. Afterwards:

```
MATCH headline_box   qt=[857, 137, 96, 36]  react=[856.1, 136.6, 96, 36]
MATCH vote_box       qt=[957, 137, 24, 36]  react=[956.1, 136.6, 23.3, 36]
```

### 6 The page read back as nothing

Every read of the React page came back empty:

```
{"raw": ""}
```

The reading script's own quoting was wrong: a selector written into it lost its
inner quotes and the script threw. This is a fault in how the page was asked, not
in the page. Corrected by selecting through the reader's own helper. The page
then answered, and reported no faults of its own:

```
faults []
```

### 7 The Electron driver left a file open

Under the strictest interpreter mode the shell driver reported its own handle:

```
ResourceWarning: unclosed file <_io.TextIOWrapper name='shell_log.txt'
mode='w' encoding='utf-8'>
```

The handle belongs to the driver that starts the shell, not to the product. The
shell itself started, answered every read and reported no page faults.

### The debugger, and what it printed

Every run set a throwaway home. All three hosts run clean under the strictest
interpreter mode:

```
PYTHONWARNINGS=error python -X dev -X faulthandler   engine, phases 4 to 6
EXIT=0

PYTHONWARNINGS=error python -X dev -X faulthandler   ACERVATOR_VARIANT=qt
EXIT=0

PYTHONWARNINGS=error python -X dev -X faulthandler   ACERVATOR_VARIANT=react
EXIT=0

PYTHONWARNINGS=error python -X dev -X faulthandler   the Electron shell
EXIT=0   shell_exit None   debug port answered
```

The same engine path under `pdb`:

```
PYTHONWARNINGS=error python -m pdb -c continue bucketchart_engine_drive.py
EXIT=0
=== the chart the thumbnail and the larger view draw ===
  closes pulled 200 first 200.0 last 219.82515271540598
  chart thumbnail post-thumbnail 120 x 36
    marks 44 {'chart-column': 40, 'chart-band': 3, 'chart-close': 1}
    first mark ['chart-column', 2, 33, 3, 1, '#66cc99']
    last mark  ['chart-close', 114, 3, 4, 4, '#00ff88']
  chart preview post-preview 320 x 160
    marks 84 {'chart-column': 80, 'chart-band': 3, 'chart-close': 1}
The program finished and will be restarted
```

## Resolution

### The chart the thumbnail draws

The thumbnail is 120 by 36 and the larger view 320 by 160. Each is drawn from one
list of rectangles the surface answers, so both hosts place the same boxes. The
thumbnail holds 44: forty close columns, three Bollinger band rules and the last
close. The larger view holds 84 on the same three parts.

The control proving the instrument can report nothing is a post with no closes:

```
control, no closes: []
```

Read off the running Qt widgets, the chart is painted rather than empty. The four
most common pixel values in the grabbed thumbnail:

```
thumbnail_drawn_pixels [3154, 2242, 951, 374]
preview_drawn_pixels   [41194, 35217, 2376, 1184]
```

### The ticker and the vote beside it

Read off all three hosts, on the same post:

```
headline  ETH 1d
vote      bull
tooltip   ETH 1d - bull - press for the larger chart.
```

### The press that opens the larger chart

Pressing the thumbnail opens the expansion in every host, and the larger chart,
Approve, Decline and the post body are under it. Read back after the press:

```
qt        preview_box [733, 215, 320, 160]  actions ['Approve', 'Decline']
react     preview_box [732.1, 215.4, 320, 160]  actions ['Approve', 'Decline']
electron  preview_box [725.3, 331.8, 320, 160]  actions ['Approve', 'Decline']
```

### The four buttons, driven in every host

Qt and React, read off the real widgets and the real elements:

```
after Approve   state approved   meta 'Instagram - approved'
Post Selected   Instagram - ETH 1d - not sent - No credential held for Instagram.
after Decline   state declined   meta 'Instagram - declined'
Post Selected   Instagram - ETH 1d - not sent - Declined. Not sent.
Post All        X - ETH 1d - sent to recorded-destination
                LinkedIn - ETH 1d - sent to recorded-destination
Full Auto on    X - ETH 1d - sent to recorded-destination
Full Auto off   no record
```

The Electron shell drives the same four. It holds no vault, so phase five refuses
each post by name rather than in silence:

```
after Approve   Instagram - approved
after Decline   Instagram - declined
credentials     ['X: Credential vault not wired.',
                 'Instagram: Credential vault not wired.',
                 'LinkedIn: Credential vault not wired.']
page faults     []
```

### Dimensions

Read off the Qt widgets and off the page's own elements, both sized 1400 by 860,
with the theme applied to each. A row matches when every number in it is within
1.5 px.

```
MATCH   tab                    qt=[1400, 860] react=[1400, 860]
MATCH   sector_field           qt=[16, 56, 72, 37] react=[15.8, 55.8, 72, 37]
MATCH   class_box              qt=[94, 56, 92, 37] react=[93.8, 55.8, 92, 37]
MATCH   scan_now               qt=[472, 56, 108, 36] react=[471.8, 56.3, 108, 36]
MATCH   settings_button        qt=[585, 56, 96, 36] react=[585.8, 56.3, 96, 36]
MATCH   post_selected          qt=[720, 56, 128, 36] react=[719.3, 55.8, 128, 36]
MATCH   post_all               qt=[854, 56, 92, 36] react=[853.3, 55.8, 92, 36]
MATCH   full_auto              qt=[1200, 56, 184, 36] react=[1200.2, 55.8, 184, 36]
MATCH   stepper                qt=[720, 98, 664, 176] react=[719.3, 97.8, 664.9, 177.1]
MATCH   back_button            qt=[720, 98, 26, 24] react=[719.3, 97.8, 26, 24]
MATCH   timeframe box 0        qt=[192, 63, 64, 22] react=[191.8, 63.3, 64, 22]
MATCH   timeframe box 1        qt=[262, 63, 64, 22] react=[261.8, 63.3, 64, 22]
MATCH   timeframe box 2        qt=[332, 63, 64, 22] react=[331.8, 63.3, 64, 22]
MATCH   timeframe box 3        qt=[402, 63, 64, 22] react=[401.8, 63.3, 64, 22]
MATCH   headline_box           qt=[857, 137, 96, 36] react=[856.1, 136.6, 96, 36]
MATCH   vote_box               qt=[957, 137, 24, 36] react=[956.1, 136.6, 23.3, 36]
MATCH   thumbnail_box          qt=[733, 137, 120, 36] react=[732.1, 136.6, 120, 36]
MATCH   preview_box            qt=[733, 215, 320, 160] react=[732.1, 215.4, 320, 160]
MATCH   thumbnail first mark   qt=[2, 33, 3, 1] react=[2, 33, 3, 1]
MATCH   thumbnail last mark    qt=[114, 3, 4, 4] react=[114, 3, 4, 4]
MATCH   chart mark counts      qt=[44, 84] react=[44, 84]
MATCH   action 0               qt=[733, 398, 100, 36] react=[732.1, 398.8, 100, 36]
MATCH   action 1               qt=[837, 398, 92, 36] react=[836.1, 398.8, 92, 36]
MATCH   save_button            qt=[16, 228, 655, 36] react=[15.8, 227.8, 655.3, 36]
MATCH   first_credential_key   qt=[172, 99, 96, 37] react=[171.8, 98.8, 96, 37]
MATCH   first_setting_field    qt=[172, 270, 180, 37] react=[171.8, 269.8, 180, 37]

rows 26 rows matched 26
numbers 100 numbers matched 100
```

**Every difference the report before this one listed is closed.** Thirteen rows
carried them: Post Selected, Post All, Send Bucket Full Auto, the stepper, the
back arrow, the thumbnail, the thumbnail marker, Approve, Decline, Settings, Save
credentials, the credential field and the setting field. Each of those thirteen
now matches, and eleven more rows were added and match as well.

One number inside the tolerance is worth naming, because it will not go to zero:
the vote word is 24 px wide in Qt and 23.3 px in the page. That is the width the
word `bull` takes in each font, and it moves nothing, because the element after
it is the row's stretch.

Text, read off all three hosts:

```
MATCH   bucket summary        MATCH   bucket total
MATCH   position              MATCH   headline
MATCH   vote                  MATCH   meta
MATCH   method                MATCH   thumbnail tooltip
MATCH   thumbnail mark kinds  MATCH   preview mark kinds
MATCH   actions               MATCH   detail lines
MATCH   approve state         MATCH   approve meta
MATCH   decline state         MATCH   declined record
MATCH   post selected         MATCH   post all
MATCH   full auto records     MATCH   full auto off
MATCH   credential state      MATCH   settings read back

text rows 22 matched 22
```

### The push targets

TradingView is gone. The set is the platforms that publish an interface for
posting, and three of them are built:

```
push targets ['X', 'Instagram', 'LinkedIn']
```

Each row names the target and the evidence sections its body carries in order. A
fourth is a fourth row; `format_post`, `distribute` and `ReadyToSend` read the
row, not the name. The settings page follows the same list, so it now carries
three credential rows and not four.

### The topologies button

```
topologies_refresh_text Refresh
```

The Qt pane and the page both read it from
`market_inspector_topologies_surface.REFRESH_TEXT`, which held the only other
copy of the wording.

### The gate

Fixture controls first. `known_good` exits 0 and `known_bad` exits 1 on all four
archetypes:

```
coding known_good exit=0    coding known_bad exit=1
docs   known_good exit=0    docs   known_bad exit=1
gui    known_good_widget.py exit=0    gui known_bad_widget.py exit=1
gui    known_good_screen.js exit=0    gui known_bad_screen.js exit=1
ta     known_good_ta001.py  exit=0    ta  known_bad_ta001.py  exit=1
ta     known_good_ta003.py  exit=0    ta  known_bad_ta004.py  exit=1
```

Every file this unit touched, with its exit code read on the same line as the
tool and every tool reporting `ok`:

```
coding src/trading/ata_spm.py                              exit=0 passed=True
ta     src/trading/ata_spm.py                              exit=0 passed=True
coding src/trading/ata_spm_push.py                         exit=0 passed=True
ta     src/trading/ata_spm_push.py                         exit=0 passed=True
coding src/gui/main_tabs/market_inspector_surface.py       exit=0 passed=True
ta     src/gui/main_tabs/market_inspector_surface.py       exit=0 passed=True
gui    src/gui/main_tabs/market_inspector_surface.py       exit=0 passed=True
coding src/gui/main_tabs/market_inspector_topologies_surface.py exit=0 passed=True
gui    src/gui/market_inspector.py                         exit=0 passed=True
coding src/gui/market_inspector.py                         exit=0 passed=True
gui    src/gui/market_inspector_topologies.py              exit=0 passed=True
coding src/gui/market_inspector_topologies.py              exit=0 passed=True
gui    src/gui/react_market_inspector_tab.py               exit=0 passed=True
coding src/gui/react_market_inspector_tab.py               exit=0 passed=True
gui    src/gui/web/market_inspector.js                     exit=0 passed=True
docs   docs/manual/08-tabs.md                              exit=0 passed=True
```

`src/gui/web/market_inspector.css` has no analyzer in the harness, and it says so
rather than reporting clean:

```
gui src/gui/web/market_inspector.css exit=1
[archetype] not green: no analyzer for css - this file type was NOT examined,
which is not the same as clean
```

That is the honest state of that one file: seventeen added lines of style, gated
by nothing.

`black --check` and `flake8` are clean on all seven Python files.

### Size against time

```
source lines produced       459
wall clock                  3706 s
seconds per source line      8.1
```

Phases one to three measured 2.51 and phases four to six 2.9, both counting test
lines in the denominator. This branch carries no tests, so the denominator here
is source only and the two figures do not compare directly.
