# 2026-09-09 — System Status: the tab draws the emitter network

Issue #34. Files changed: `src/core/signal_contract.py`,
`src/gui/main_tabs/system_status_tab_surface.py`,
`src/gui/main_tabs/system_status_tab.py`, `src/gui/main_tabs/empty_tabs.py`,
`src/gui/react_system_status_tab.py`, `src/gui/main_window.py`,
`src/gui/web/system_status_tab.js`, `src/gui/web/system_status_tab.css`,
`desktop/renderer/index.html`, `docs/manual/08-tabs.md` and
`docs/manual/08-tabs/system-status.md`. No test file was written.

The Electron shell ran from `desktop/main.js` under the installed Electron
binary with a throwaway user-data directory, and the renderer was read over the
Chrome DevTools Protocol with `websockets`. The desktop window's panel was
built offscreen under `PYTHONWARNINGS=error` with
`python -X dev -X faulthandler`.

The emitter activity in both runs is real. `VotingEngine.compute_all` ran three
times over 260 candles, which is the call site that emits
`ta.07.003.postcondition.computed` and `ta.07.004.postcondition.raw.{}`. No
value was pushed into the sink by hand.

Picture: `<scratchpad>/u34/u34_system_status_shell_live.png`.
Control picture: `<scratchpad>/u34/u34_system_status_shell_nofeed.png`.

## 0 — the cold read, before any change

`CANONICAL_TAB_ORDER` holds ten labels and `STATUS_TAB` is the ninth, so the
tab was not absent. It drew the shared empty state: a heading, one sentence
saying the tab is not built, and the issue that carries the build-out.

```python
HEADING = "Status"
ISSUE = 34
BUILT = False
STATE_TEXT = "This tab is not built."
```

`EmptyTabsMixin` built it from `EMPTY_TAB_SURFACES`, the same path the
Accumulation tab uses. Of the issue's three parts, all three were open: the
record carried no subsystem, no report of health per subsystem existed, and the
screen drew three lines of text.

No Qt original exists. `variant_surface.py` records sixteen screens and none of
them is this one. A search for a Qt widget class over `src/` for
`class .*(Status|Health|Watchdog|Emitter)` returns `StatusTabMixin`,
`BotStatusTableModel`, `LiveStatusTabModel`, `StatusLogSink`, `StatusLogModel`,
`WatchdogState`, `UsbStatusIndicatorModel`, `USBStatusIndicator`, `GateStatus`,
`WindowStatus`, `PositionHealth`, `OrderStatus`, `CompetitionStatus` and
`SnapshotEmitterMixin` — none draws a System Status screen. Every
`SystemStatus` in the tree names the Kraken endpoint
`https://api.kraken.com/0/public/SystemStatus`.

---

## 1 — the record named no subsystem the report could group by

### 1.1 the error

No traceback. The persisted row carried the emitter name and nothing that said
which subsystem the name belonged to, while `SignalSink.by_subsystem` split the
name itself:

```python
            sub = r.name.split(".", 1)[0]
```

### 1.2 reproduction

```
python -X dev -X faulthandler <scratchpad>/u34/drive_ta_emitters.py
sink.records()[0].to_json()
```

### 1.3 the cause

`Signal.to_json` in `src/core/signal_contract.py` listed thirteen fields and no
subsystem, so any consumer had to re-split the name and could split it
differently.

### 1.4 the correction

`subsystem_of` is the one function that splits a name. `to_json` carries its
answer and `by_subsystem` calls it, so the row on disk and the panel on screen
cannot disagree.

### 1.5 the rerun

```
{"ts":"...","seq":1,"module":"src.trading.ta_engine",
 "name":"ta.07.003.postcondition.computed","subsystem":"ta","kind":"check",
 "ok":true,"expected":12,"actual":12,...}
```

---

## 2 — the offscreen page never finished loading

### 2.1 the error

The panel was built and its page stayed blank. Every read came back `None`.

```
page_ready False pumped False
heading -> None
subsystem panels -> None
```

### 2.2 reproduction

```
QT_QPA_PLATFORM=offscreen PYTHONWARNINGS=error python -X dev -X faulthandler
    <scratchpad>/u34/drive_status_panel.py
```

### 2.3 the cause

The driver waited in a `QApplication.processEvents()` loop. That drains the
queue without ever yielding, so `QWebEngineView` never reached `loadFinished`.
The defect was in the driver, not in the panel.

### 2.4 the correction

The wait runs a real `QEventLoop` with a `QTimer.singleShot` tick.

### 2.5 the rerun

```
page_ready True pumped True
heading -> Status
subsystem panels -> 17.0   tab groups -> 11.0   emitter rows -> 78.0
green lights -> 1.0   yellow lights -> 6.0   red lights -> 0.0
faults -> []
```

---

## 3 — electron.exe ran the shell as plain Node

### 3.1 the error

```
TypeError: Cannot read properties of undefined (reading 'whenReady')
    at Object.<anonymous> (.../desktop/main.js:182:5)
```

Before that, with no `NODE_PATH` set:

```
Error: Cannot find module 'electron'
Require stack:
- .../desktop/main.js
```

### 3.2 reproduction

```
electron.exe <tree>/desktop --user-data-dir=<scratchpad> --remote-debugging-port=9349
ACERVATOR_BRIDGE_ARGV="-m src.core.desktop_bridge"
```

### 3.3 the cause

The editor host exports `ELECTRON_RUN_AS_NODE=1`. Any Electron binary launched
from this shell inherits it and runs the entry file as Node, where
`require("electron")` is not the built-in module and `app` is undefined. It is
a fact about the launching shell, not about `desktop/main.js`.

### 3.4 the correction

The driver removes `ELECTRON_RUN_AS_NODE` and `NODE_PATH` from the child's
environment.

### 3.5 the rerun

```
target Acervator file:///.../desktop/renderer/index.html
panel host present: True
registered -> ... status_log, system_status_tab, trade_charts_tab, trading_tab
tab labels -> [... ,"history_tab","system_status_tab","console_tab"]
select(system_status_tab) -> system_status_tab
```

---

## 4 — the shell dropped every margin, gap and type size

### 4.1 the error

Every count ran into its own label, and the totals strip drew with no card.

```
subsystems17declared78fired2silent76always-on silent14records39failed0
```

### 4.2 reproduction

The shell drew the tab and the picture was read.

### 4.3 the cause

`design_system_surface` serves a size token as a bare number, and
`design_tokens.js` writes it to the page unchanged.

```
SPACE_S 8      TYPE_BODY 13     RADIUS_XS 4
```

`margin-right: var(--SPACE_S)` is then `margin-right: 8`, which is not a length,
so the browser drops the declaration. The desktop window's page did not show it,
because `SKIN` wrote `8px` there — two writers of one token name disagreeing on
its form.

### 4.4 the correction

The sheet multiplies each size token by `1px`, and `SKIN` writes the number
unitless, so both writers now serve the form `design_tokens.js` already used.

```css
  padding: calc(var(--SPACE_L) * 1px);
```

### 4.5 the rerun

The same reads, after the change:

```
subsystem panels -> 17   tab groups -> 11   emitter rows -> 78
green lights -> 1   yellow lights -> 6   red lights -> 0
green light colour -> rgb(0, 255, 136)      SUCCESS is #00ff88
emitter name colour -> rgb(224, 224, 240)   TEXT_HIGH is #e0e0f0
```

---

## 5 — a picture of the offscreen web view is blank

### 5.1 the error

`QWebEngineView.grab()` under the offscreen platform saved a 1396x874 file
holding one colour.

```
u34_system_status_qt_window.png 1396x874 6882 bytes distinct colours 1
    (255, 255, 255) 1220104
```

### 5.2 reproduction

The same offscreen run as section 2, then the file was read.

### 5.3 the cause

The offscreen platform composites nothing for a `QWebEngineView`, so the grab
carries the widget's blank backing store. The page itself had drawn: the same
run read seventeen panels and seventy-eight rows out of the live document.

### 5.4 the correction

The picture is taken from the Electron shell with `Page.captureScreenshot`,
which reads the compositor. The blank file was deleted rather than kept under a
name that claims to show the tab.

### 5.5 the rerun

```
u34_system_status_shell_live.png 1733x1048 113316 bytes distinct colours 1762
```

---

## 6 — break the feed

The control removes the sink and drives the same page. Every number that came
from the emitter network falls, and the ones that do not come from it hold.

| read | feed live | feed removed |
| --- | ---: | ---: |
| feed line | the sink's file, 39 records | `No emitter sink is installed in this process.` |
| subsystem panels | 17 | 17 |
| tab groups | 11 | 11 |
| emitter rows | 78 | 78 |
| green lights | 1 | 0 |
| yellow lights | 6 | 7 |
| red lights | 0 | 0 |
| `ta` panel | `green ... fired 2 ... records 39` | `yellow ... fired 0 ... records 0` |
| green light colour | `rgb(0, 255, 136)` | the selector matches nothing |

The seventeen panels and seventy-eight rows are the declared registry, which is
why they hold. The counts and the lights are the feed, and they go to zero.

The last row is the counter's own control: the same selector that answered
`rgb(0, 255, 136)` with the feed live matches no element without it, so the zero
is a fact about the page.

## 7 — Red cannot be reached

`subsystem_health` returns `HEALTH_GREEN`, `HEALTH_YELLOW` or None.
`HEALTH_RED` is declared and no branch assigns it. Both runs read
`red lights -> 0` beside `green lights -> 1` and `yellow lights -> 6`, so the
counter can see a light when there is one. Red waits on issue #14, which is
what would give each emitter an expected rhythm; without one, a hung subsystem
and an idle subsystem are the same silence.
