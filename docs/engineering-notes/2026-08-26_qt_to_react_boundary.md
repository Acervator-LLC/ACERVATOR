# The Qt-to-React boundary — what moves, what does not, and what it costs

**Reference.** This document records a measurement and a plan. It proposes no code.

Audit date: 2026-08-26. Read-only. No production file was changed. No code was written.

- Issue under audit: **#128 — "Convert UI from qt to React"**, filed by the CTO (`waldnzwrld`).
- Repository under audit: clone of `acervator_session27_CLOSE_hop5_v3_25_8` at HEAD `ad63de1`, branch `current`, version **3.27.0**.
- Clone path: a throwaway clone (`react`) outside the repository.
- The only file this audit added is this one. Nothing was committed.

---

## THE ANSWER IN FOUR NUMBERS

| Question | Answer | Instrument |
| --- | ---: | --- |
| How many lines of GUI must be re-expressed? | **50,050** | 37 shipped files that import PySide6, `git ls-files` + line count |
| How many places are presentation and trading tangled? | **74 privileged operations**, plus **13 timers** that drive the engine and **~490 lines** of duplicated trading logic in GUI files | hand-verified grep, false-positive rate stated per category |
| How many tests would a React UI invalidate? | **1,537 of 8,812** (17.4%) certain, **3,141** (35.6%) upper bound | AST per-test classifier with two positive and two negative controls |
| Which subsystem migrates first? | **History** | it is the only tab with zero writes into trading state, its own module, a helper already free of Qt, and seven emitters to verify the port against |

---

## PART ONE — FOR THE OPERATOR

Plain language. No code. Read this part and stop.

## What the CTO asked for

He wants the screen you look at to be built with React and Electron instead of Qt. He wants
the trading engine to stay in Python for now. He says this is step one toward selling
Acervator as a service.

## The one-paragraph answer

**It can be done, and the hardest part is already done for you.** Your trading engine does
not know Qt exists. I checked every file under `src/trading`, `src/exchange`, `src/core`,
`src/stocks` and `src/competition`: **not one of them imports Qt.** That is unusual and it is
worth a lot. It means the engine does not have to be rewritten, only re-plugged.

**But there are three walls, and none of them is React work.** They must be cleared before a
single line of React is worth writing:

1. **A Qt timer is currently your trading engine's heartbeat.** `main.py:687` sets up a
   50-millisecond timer. That timer is the only thing that advances the loop that reaches
   `bot.tick()`. Delete Qt today and nothing trades. This is not a display detail. It is the
   clock.
2. **9,580 lines of engine code are filed in the wrong folder.** The whole Simulator engine,
   the trade-history fetcher, the chart data fetcher and two of your safety gates sit inside
   `src/gui/`, even though not one of those files imports Qt. The folder name is lying to
   you. Moving them is mechanical and changes no behaviour.
3. **Python has no way to hand data to a web page today.** No server, no API and no socket
   exist. React cannot read a Python object. That layer has to be built from zero.

## What it costs

Honest answer: **this is a multi-month program, not a sprint.** I will not put a week number
on it, and here is why. Your git history was rewritten during the "rejoin", so I have no
trustworthy record of how fast work actually lands here. Inventing a schedule from a broken
instrument would be worse than saying nothing.

What I *can* count is the work itself:

| What must be built or rebuilt | Measured size |
| --- | ---: |
| Backend API that does not exist today | **0 lines exist**; 7 data feeds to serve |
| A replacement clock for the trading engine | 4 timer sites in `main.py` |
| Engine code to move out of the GUI folder | 9,580 lines, 18 files |
| Duplicated trading logic to delete | ~490 lines in 6 places |
| GUI to re-express in React | 50,050 lines, 982 methods, 115 classes |
| Features the new UI must reproduce | 77 framing features, 299 functions |
| Tests to rewrite | 1,537 certain, 3,141 at risk |
| Hand-drawn graphics with no React equivalent | 16 paint routines, 239 drawing calls |

For scale: the GUI is **17% of your whole Python codebase** (50,050 lines of 295,873).

## What it risks

**The one risk that matters is a second implementation of a trading decision.** Your standing
rule is that Live, Paper and Sim differ only in where the data comes from and share one
trading logic. A UI rewrite is the single easiest way to break that rule by accident, because
a React developer who needs a number will compute it in JavaScript rather than wait for the
backend.

That is not hypothetical here. It has already happened three times **inside Qt**:

- `src/gui/native_chart.py:276-424` computes Bollinger, EMA, Vortex, MACD, StochRSI and
  Ichimoku **again**, inside a chart widget. Its own comment says "Do NOT let chart
  computations diverge" from the real engine. They already have. The capability matrix
  records the chart's MACD as numerically wrong.
- `investor_screen.py:115-142` re-implements the scrum/fold strategy with its own hardcoded
  thresholds.
- `cartoon_screen.py:125-165` re-implements it a third time.

If those move to JavaScript unexamined, you will have the same defect in a language you
cannot run your Python gates against.

**The second risk is a chart widget that writes to your bot file.**
`src/gui/bot_visualizer.py:3085` writes directly to `~/.acervator/bot_state.json`. Its own
docstring is headed "SECOND WRITER WARNING" and says the two writers "have never been
reconciled". A picture of your bots can change your bots. That must not survive the port.

## The order it happens in

**Nothing React happens until steps 0-3 are done.**

| Step | What | Why it is first |
| --- | --- | --- |
| 0 | Move the 9,580 engine lines out of `src/gui/` | Mechanical. Makes the boundary real instead of imaginary. |
| 1 | Give the trading engine its own clock | Today a widget's timer runs your money. |
| 2 | Build the read API | React cannot read a Python object. Nothing exists yet. |
| 3 | Fix `trade.filled` — it has two different shapes | Five call sites send a nested payload, five send a flat one. |
| 4 | **History tab to React.** First real port. | Own file, zero writes into trading, clean 13-column contract, 7 emitters to prove the port. |
| 5 | Console to React | Cleanest stream contract in the app, but it is buried inside an 11,013-line file and must be carved out. |
| 6 | Market Inspector to React | Small and clean, but it has **zero emitters**, so today a port cannot be proved correct. Fix that first (issue #18). |
| 7 | Asset Charts to React | Only after the duplicate indicator maths is deleted. Never re-implement an indicator in JavaScript. |
| 8 | Bot Swarm to React | 4,038 lines of hand-drawn graphics, and it is the widget that writes to `bot_state.json`. |
| 9 | Simulator to React | 5,815 lines of panels, once the engine has moved out. |
| 10 | Trading tab to React, last | 24,040 lines, 21 money-moving call sites, the Fire button. This is the live-money surface. |

## What I recommend you do first

**Do step 0 this week.** Moving 9,580 lines out of `src/gui/` costs almost nothing, breaks
nothing, and it is worth doing whether or not you ever go to React. It is the single change
that turns "the boundary" from an idea into a fact you can see in the folder tree.

**Do not let anyone start React before step 2.** A React screen with no API behind it will
grow its own copy of your logic to fill the gap. That is exactly the failure this migration
must not produce.

**One more thing, and it is free.** Your shipped Windows build **already bundles a Chromium
web engine** (`tools/spec_common.py:153` declares `PySide6.QtWebEngineWidgets` as a hidden
import). A working example of an HTML and JavaScript chart already exists in your tree at
`src/gui/tradingview_chart.py`. That means you can put a React panel inside the app you have
today and look at it, without Electron, without a rewrite, and without touching the trading
engine. That is the cheapest possible proof that this plan works.

---

## PART TWO — THE EVIDENCE

For the CTO. Every number below carries its instrument and its control.

---

## 1. THE HEAD START, VERIFIED

The subsystem capability matrix dated 2026-08-25 is the specification of what a React UI must
reproduce. It claims **10 subsystems, 77 framing features, 299 functions, 376 stable IDs**.
This audit did not re-do that census. It checked whether the census still holds.

> **Note — that file does not exist in this repository.** It is **untracked in git**. The only
> copy sits in the operator's working tree, at the absolute path
> `docs/engineering-notes/2026-08-25_subsystem_capability_matrix.md`.
> It is in no commit, so it did not arrive in this clone, and it was read in place. This
> report deliberately avoids writing it as a repository-relative path, because such a path
> would not resolve for any other reader. **It should be committed.** An uncommitted
> specification is one `git clean` away from gone, and this migration depends on it.

| Matrix claim | Measured today | Verdict |
| --- | --- | --- |
| 78 emitter pins, 78 registry rows, controls OK, exit 0 | `python -m tools.emitter_registry_check` returns `pins in src: 78 / registry rows: 78 / instrument: controls OK`, **exit 0** | **exact** |
| 376 stable IDs | 378 found by regex | within 1 per class |
| 77 framing features | 78 found | within 1 |
| 299 functions | 300 found | within 1 |
| Test citations | **136 of 140 resolve** (97.1%) | current |

The one-per-class overcount is my regex reading the worked example in the matrix's own
"HOW TO READ A ROW" section as a real ID. The matrix's numbers are right.

**The four broken citations are all in one file**, `tests/test_sim_chart_marker_anchoring.py`
(the file exists; those four test names do not):
`test_a_marked_candle_is_never_decimated_away`, `test_clear_gates_still_clears_the_blockers`,
`test_ls_led_is_cleared`, `test_the_panel_appends_before_it_marks`.

**Control on the citation checker:** a deliberately fabricated node ID
(`tests/test_reconcile_lot_book.py::test_this_does_not_exist_control`) was reported broken.
The checker can fail.

**Drift since the matrix was written:** 134 commits (`cb58d9d..HEAD`, 2026-08-25 08:42 to
2026-08-25 23:59). Despite that volume, 97.1% of its citations still resolve and its emitter
count is exact.

**Verdict: the matrix is current. Build the React feature list from it.**

---

## 2. THE SURFACE, MEASURED

### 2.1 Lines

**Instrument.** `git ls-files "*.py"`, read each file, classify by whether the text contains
`PySide6`, bucket by tree location.

| Area | Files | Lines |
| --- | ---: | ---: |
| `tests/` | 310 | 128,403 |
| `src/trading/` | 70 | 54,205 |
| **`src/gui/` (widgets)** | **39** | **45,241** |
| `src/core/` | 24 | 14,338 |
| **`src/gui/simulator_tab/`** | **18** | **13,571** |
| `dev_harness/` | 20 | 9,130 |
| repo root | 10 | 8,090 |
| `src/exchange/` | 19 | 6,924 |
| `tools/` | 12 | 6,408 |
| `docs/` fixtures | 29 | 3,365 |
| `src/competition/` | 10 | 3,031 |
| `src/stocks/` | 8 | 2,035 |
| `src/design_system.py` | 1 | 698 |
| other | 3 | 434 |
| **TOTAL tracked `.py`** | **574** | **295,873** |

**The shipped Qt GUI is 37 files and 50,050 lines** — every file that imports PySide6 and
ships in the application. That excludes 85 test files (45,824 lines), 2 harness files, 8 docs
fixtures, `tools/spec_common.py`, and three build-only scripts.

The shipped GUI holds **115 classes**, of which **88 derive from a Qt class**, and **982
functions or methods**.

| Lines | Classes | Qt-derived | Methods | File |
| ---: | ---: | ---: | ---: | --- |
| 11,013 | 17 | 13 | 163 | `src/gui/main_window.py` |
| 7,952 | 2 | 2 | 70 | `src/gui/bot_live_settings.py` |
| 4,038 | 5 | 4 | 100 | `src/gui/bot_visualizer.py` |
| 2,507 | 1 | 1 | 39 | `src/gui/simulator_tab/fleet/fleet_replay_panel.py` |
| 2,293 | 4 | 4 | 59 | `src/gui/indicator_panel.py` |
| 2,188 | 6 | 2 | 46 | `src/gui/native_chart.py` |
| 2,083 | 7 | 7 | 35 | `src/gui/bot_wizard.py` |
| 1,775 | 1 | 0 | 30 | `main.py` |
| 1,427 | 1 | 1 | 18 | `src/gui/history_tab.py` |
| 1,333 | 1 | 1 | 24 | `src/gui/settings_dialog.py` |
| 1,207 | 4 | 4 | 33 | `src/gui/simulator_tab/fleet/sim_visuals.py` |
| 1,177 | 1 | 1 | 25 | `src/gui/simulator_tab/simulator_tab.py` |
| 888 | 4 | 2 | 27 | `src/gui/crypto_news_ticker.py` |
| 816 | 1 | 1 | 14 | `src/gui/simulator_tab/nuclear_mode_panel.py` |
| 759 | 4 | 4 | 23 | `src/gui/stock_main_window.py` |
| 755 | 4 | 2 | 35 | `src/gui/screen_recorder.py` |
| 648 | 2 | 1 | 17 | `src/gui/testnet_tab.py` |
| 638 | 7 | 5 | 30 | `src/gui/audio_suite.py` |
| 627 | 4 | 4 | 25 | `src/gui/usb_auth_widget.py` |
| 601 | 3 | 3 | 19 | `src/gui/market_inspector_topologies.py` |
| 575 | 1 | 1 | 17 | `src/gui/market_inspector.py` |
| 423 | 1 | 1 | 16 | `src/gui/live_bot_window.py` |
| 414 | 3 | 2 | 15 | `src/gui/bot_swarm_list.py` |
| 379 | 3 | 2 | 14 | `src/gui/shared_testnet.py` |
| 364 | 3 | 3 | 8 | `src/gui/risk_tab.py` |
| 355 | 7 | 2 | 11 | `src/gui/competition_tab.py` |
| 354 | 1 | 1 | 5 | `src/gui/journal_tab.py` |
| 340 | 2 | 1 | 10 | `src/gui/tradingview_chart.py` |
| 339 | 3 | 3 | 8 | `src/gui/analytics_tab.py` |
| 312 | 1 | 1 | 6 | `src/gui/alerts_tab.py` |
| 286 | 1 | 1 | 7 | `src/gui/instance_consent_dialog.py` |
| 276 | 4 | 2 | 7 | `src/gui/buy_confirmation_dialog.py` |
| 270 | 1 | 1 | 8 | `src/gui/init_wizard.py` |
| 231 | 1 | 1 | 6 | `src/gui/start_all_progress_dialog.py` |
| 211 | 2 | 2 | 4 | `src/gui/launcher.py` |
| 108 | 2 | 2 | 5 | `src/gui/simulator_tab/sim_stat_strip.py` |
| 88 | 0 | 0 | 3 | `src/gui/qt_safe_events.py` |
| **50,050** | **115** | **88** | **982** | **37 files** |

Three root-level presentation scripts (`splash_screen.py` 731, `cartoon_screen.py` 750,
`investor_screen.py` 994, built on `screen_fx.py` 410) also import Qt. They are demo and
marketing renderers, not product UI.

### 2.2 Qt classes, and how many times

**Instrument.** Regex `\bQ[A-Z][A-Za-z0-9_]+\b` over non-comment lines of the 41
Qt-importing shipped files, then every token resolved against the real PySide6 namespace
(`QtWidgets`, `QtCore`, `QtGui`, `QtCharts`, `QtMultimedia`, `QtSvg`, `QtTest` — 728 known
symbols).

**Control: 4,097 occurrences resolved to real Qt symbols, 31 did not. False-positive rate
0.75%.** The 31 rejects are constants and words that look like Qt (`QUEUE`, `QUALITY`,
`QFL`, `QT_DEBUG`), plus `QWebEngineView`, which lives in a module outside my probe list.

**95 distinct Qt classes are in use.** The top 40:

| Count | Class | Migration shape |
| ---: | --- | --- |
| 501 | `QColor` | a CSS colour |
| 384 | `QLabel` | a `<span>` |
| 282 | `QPushButton` | a `<button>` |
| 211 | `QVBoxLayout` | flexbox |
| 189 | `QWidget` | a component |
| 188 | `QMessageBox` | a modal |
| 162 | `QRectF` | **canvas geometry — no HTML equivalent** |
| 156 | `QGroupBox` | a `<fieldset>` |
| 138 | `QPen` | **canvas stroke** |
| 136 | `QHBoxLayout` | flexbox |
| 135 | `QTableWidgetItem` | a `<td>` |
| 110 | `QPointF` | **canvas geometry** |
| 103 | `QFont` | CSS font |
| 99 | `QTableWidget` | a `<table>` |
| 85 | `QTimer` | `setInterval`, **or a server push** |
| 85 | `QCheckBox` | `<input type=checkbox>` |
| 79 | `QBrush` | **canvas fill** |
| 75 | `QFrame` | a `<div>` |
| 70 | `QPainter` | **`<canvas>` or SVG — a rewrite, not a translation** |
| 70 | `QComboBox` | `<select>` |
| 65 | `QDoubleSpinBox` | `<input type=number>` |
| 63 | `QHeaderView` | `<thead>` |
| 57 | `QLineEdit` | `<input type=text>` |
| 56 | `QFormLayout` | a form grid |
| 48 | `QSpinBox` | `<input type=number>` |
| 34 | `QScrollArea` | `overflow: auto` |
| 30 | `QSplitter` | **no HTML equivalent — a library or hand-built** |
| 30 | `QSizePolicy` | flex-grow |
| 24 | `QApplication` | **the Electron main process** |
| 22 | `QDialog` | a modal |
| 21 | `QLinearGradient` | CSS gradient |
| 21 | `QObject` | — |
| 21 | `QTextEdit` | a rich text area |
| 20 | `QRadioButton` | `<input type=radio>` |
| 20 | `QPlainTextEdit` | a `<pre>` |
| 18 | `QTabWidget` | a tab strip |
| 17 | `QListWidget` | a `<ul>` |
| 14 | `QPolygonF` | **canvas geometry** |
| 14 | `QThread` | **a worker — must move to the backend** |
| 13 | `QProgressBar` | `<progress>` |

**About 470 of the 4,097 occurrences (11%) are painting primitives** — `QPainter`, `QPen`,
`QBrush`, `QRectF`, `QPointF`, `QPolygonF`, `QPainterPath`, `QLinearGradient`,
`QRadialGradient`, `QFontMetrics`. Those do not translate. They are re-drawn.

### 2.3 The categories that decide the difficulty

| Category | Count | Files |
| --- | ---: | ---: |
| `def paintEvent` — **hand-drawn surfaces** | **16** | 14 |
| `QPainter` references | 70 | 17 |
| `painter.draw*(...)` calls | **239** | 16 |
| `QTableWidget` references | 104 | 15 |
| `QTreeWidget` / `QTreeView` references | 3 | 1 |
| `QDialog` subclasses | 4 | 4 |
| `QWizard` / `QWizardPage` | 16 | 2 |
| `QTimer` references | 106 | 18 |
| `QThread` references | 20 | 3 |
| `threading.Thread` | 6 | 4 |
| `Signal(...)` declarations | 37 | 17 |
| `@Slot` decorators | 8 | 3 |
| `.connect(...)` — **the whole wiring graph** | **303** | 31 |
| `.setStyleSheet(...)` | **444** | 33 |
| `installEventFilter` | 1 | 1 |
| `QPropertyAnimation` | 1 | 1 |
| `QMediaPlayer` | 7 | 1 |
| `QWebEngineView` | 3 | 1 |

**The hand-drawn surfaces, ranked by drawing calls:**

| `paintEvent` | `draw*` calls | File | What it draws |
| ---: | ---: | --- | --- |
| 1 | **69** | `src/gui/native_chart.py` | The candle chart, its overlays and three sub-panes |
| 2 | 34 | `src/gui/bot_visualizer.py` | The bot swarm, its nodes and its wires |
| 1 | 25 | `cartoon_screen.py` | Marketing animation |
| 2 | 22 | `src/gui/simulator_tab/fleet/sim_visuals.py` | Simulator gate lights and tape |
| 1 | 20 | `investor_screen.py` | Marketing animation |
| 1 | 18 | `main.py` | Boot screen |
| 1 | 13 | `splash_screen.py` | Splash |
| 1 | 8 | `src/gui/indicator_panel.py` | Confidence bars |
| 1 | 6 | `src/gui/analytics_tab.py` | (dead — host nulled) |
| 1 | 4 | `src/gui/risk_tab.py` | (dead — host nulled) |
| 1 | 3 | `src/gui/audio_suite.py` | Level meter |
| 1 | 3 | `src/gui/bot_swarm_list.py` | Lane cells |
| 1 | 1 | `src/gui/usb_auth_widget.py` | Key indicator |
| 1 | 0 | `src/gui/launcher.py` | Background |

### 2.4 Styling

**444 `setStyleSheet` calls** across 33 files, and **287 distinct hex colour literals** in
the shipped GUI. Three files hold 209 of the 444: `bot_visualizer.py` (73),
`bot_live_settings.py` (69), `main_window.py` (67).

**Two** design-token modules exist — `src/design_system.py` (698 lines) and
`src/gui/design_system.py` (310 lines) — plus `src/gui/theme_engine.py` (646 lines). Between
them they define 42 named colours. The other 245 hex values are inline literals.

**Consequence for React:** the styling is not a theme that can be exported. It is 444 inline
stylesheet strings. The design tokens must be rebuilt from the pixels, not lifted from a
file.

---

## 3. THE BOUNDARY — WHERE PRESENTATION ENDS AND TRADING BEGINS

### 3.1 The good news, stated precisely

**The reverse edge is clean. Zero engine files import Qt.**

**Instrument.** `grep -rn "PySide6|from shiboken"` across `src/trading`, `src/exchange`,
`src/core`, `src/stocks`, `src/competition`, `src/utils`.

**Result: 1 hit — `src/core/version_sweep.py:630`, the string `"PySide6": "pyside6"` in a
requirements-check dictionary.** Not an import.

A wider probe (`QObject|QTimer|QApplication|QWidget|QThread|@Slot`) returns 4 hits, all
docstrings or comments. Two of them say the words "Not a QThread".

> **Control warning for anyone repeating this.** The naive pattern `Signal` returns 200+ hits
> across the engine at a **100% false-positive rate**. They are all the project's own
> indicator dataclass at `src/trading/indicators/types.py:60`, not `PySide6.QtCore.Signal`.
> A tool that greps `Signal` on this repository will report a crisis that does not exist.

**The EventBus is also Qt-free.** `src/core/event_bus.py:79` is a plain publish/subscribe
class built on `threading` and `dataclasses`, with `dict[str, list[_Subscriber]]` callbacks.
It is not a Qt Signal. It can feed a WebSocket unchanged.

**The emitter network is Qt-free.** `src/core/signal_contract.py` (2,704 lines) writes frozen
`Signal` dataclasses with 14 fields to `~/.acervator_logs/signals/session.jsonl`. It is
already a JSON stream.

**The instance guard is Qt-free.** `src/core/instance_guard.py` (924 lines) uses a filesystem
lease, and its own docstring records that it deliberately uses "no `QSharedMemory`, no
`QLocalServer`". It survives the migration untouched. Only its dialog
(`src/gui/instance_consent_dialog.py`, 286 lines) must be rebuilt.

### 3.2 The bad news — the runtime edge

Import-level cleanliness is not runtime cleanliness.

**A Qt timer is the application's entire asyncio event loop.**

```
main.py:651   ASYNC_PUMP_INTERVAL_MS = 50
main.py:654   def _make_async_pump_timer(loop, interval_ms=ASYNC_PUMP_INTERVAL_MS) -> QTimer
main.py:678       def pump_async():
main.py:679           loop.call_soon(loop.stop)
main.py:680           loop.run_forever()
main.py:687       timer.timeout.connect(pump_async)
```

The file states it itself at `main.py:642-645`, quoted verbatim:

```text
Every coroutine in this application runs on the Qt GUI thread. There is no separate
asyncio thread: this timer is the ONLY thing that advances the loop, so its cadence is
the loop's cadence.
```

That loop is what reaches `src/trading/bot_container.py:1718`
(`asyncio.create_task(self._run_with_guard())`), which is the trading loop. **The engine runs
on a widget's heartbeat.**

This is the same asyncio-on-GUI-thread condition already recorded as its own arc. The React
migration does not create it. It does make it blocking: you cannot remove Qt without first
giving the engine a clock.

### 3.3 The 74 privileged operations

These are the sites where a widget reaches into trading. They are the API surface that must
become RPC calls.

**Category 1 — a widget mutates trading state: 29 verified sites.**
Instrument: sweep for `<ident>.<attr> = ` excluding known-safe receivers. 74 raw hits, all
74 hand-read. 19 are widget-to-engine crossings, 27 are engine-internal (inside the shelved
simulator engine, and legitimate), 28 are presentation false positives.
**Presentation false-positive rate 37.8%.**

**Category 2 — a widget calls a method that moves money or changes a position: 45 verified
sites.** Instrument: broad token sweep, 185 raw hits, 45 verified. **False-positive rate
75.7%**, driven by `QTimer.start()`, `.stop()` and `widget.clear()`. A narrowed
high-signal pattern (`_execute_buy|place_order|manual_fire|self_destruct|detonate|despawn|force_fire|\.tick\(`)
gives 16 raw and 6 live — **62.5%** false positives, all six being docstrings.

**The twenty that matter most:**

| # | Site | What it does |
| ---: | --- | --- |
| 1 | `main.py:687` | A 50 ms `Qt.PreciseTimer` is the sole driver of the asyncio loop, therefore of every `bot.tick()`. |
| 2 | `src/gui/bot_visualizer.py:3085`, write at `:3130` | A chart widget renames a temp file over `~/.acervator/bot_state.json`. Its docstring is headed **"SECOND WRITER WARNING"** and says the two writers "have never been reconciled". |
| 3 | `src/gui/main_window.py:9721` | `force_fire(bot_id, aggressive=True)` — the Fire button makes the next tick place a MARKET order sized to the delta, bypassing the TA and BB gates. |
| 4 | `src/gui/bot_live_settings.py:2204` | `self._bot.self_destruct(confirmation_token=...)` — a settings dialog liquidates and destroys a live bot. |
| 5 | `src/gui/bot_live_settings.py:2541` | `manual_fire_position(pair)` — a dialog closes an Extractor position at market. |
| 6 | `src/gui/bot_live_settings.py:5153` | `manual_fire_tranche(idx)` — a dialog fires one fold tranche back to market. |
| 7 | `src/gui/bot_live_settings.py:2120` | `setattr(cfg, field, value)` — the dialog writes an arbitrary named field onto a live `BotConfig`. Untyped, unvalidated, persisted 60 s later. |
| 8 | `src/gui/bot_live_settings.py:2078-2093` | The `_RUNTIME_ROUTED` dict. *Which* config fields need a runtime hook is policy, and it lives in a Qt dialog. |
| 9 | `src/gui/native_chart.py:276-424` | A second full indicator suite inside a `QWidget`: Bollinger(20,2), EMA12/26, Vortex(14), MACD(12,26,9), StochRSI, Ichimoku(9,26,52). |
| 10 | `src/gui/main_window.py:114-305` | `_compose_ammo_cell` decides Scrum versus Fold territory, computes the dust band `max(target*0.001, 0.01)`, and predicts whether Manual Fire will no-op. |
| 11 | `main.py:1631,1641,1643,1647` | The fleet start-all sequencer is a `QTimer.singleShot` state machine calling `_on_bot_command(bot_id, "start")` on real live bots. |
| 12 | `main.py:1679` | `QTimer.singleShot(9500, _trigger_auto_restart)` — the whole fleet's auto-start hangs off the splash screen's fade-out finishing. |
| 13 | `main.py:1467` | `save_timer.timeout.connect(periodic_save)` calls `save_all_state()` every 60 s. Position persistence is on a Qt timer. |
| 14 | `src/gui/main_window.py:9185` | `bot._coordinator._lock_timeframe = tf` — a GUI handler reaches through two private attributes on every bot in the fleet. |
| 15 | `src/gui/main_window.py:9929` | `bot._user_verified = True` — the real-money consent flag is set by the dialog directly on the bot, immediately before `bot.start()` at `:9933`. |
| 16 | `src/gui/main_window.py:9667` | `bot.exchange = connector` — the GUI swaps a live bot's exchange object. |
| 17 | `src/gui/main_window.py:9012-9014` | A "Reset all errors" button zeroes `total_errors`, `consecutive_errors` and `last_error` on every bot. |
| 18 | `investor_screen.py:115-142` | The scrum/fold strategy re-implemented: sell surplus at +2%, buy back at -0.6%, top up at -3%, 0.999 fee factor. |
| 19 | `cartoon_screen.py:125-165` | The same strategy again. A third implementation. |
| 20 | `src/gui/indicator_panel.py:1729-1770` | A Qt panel imports the real `VotingEngine` and runs `compute_all` over 60 md5-seeded synthetic candles, labelled with a real bot's symbol. Reachable from `QTimer.singleShot(3000, self._auto_init_demo)` at `:811`. |

**Runners-up:** `src/gui/settings_dialog.py:381-384` (a dialog encrypts and writes API
credentials onto `ExchangeConfig`); `src/gui/preflight_check.py:169`
(`target_balance < min_cost * 3` blocks bot creation); `src/gui/start_balance_check.py:137`
(`sufficient = (base_free >= 1.0) or (target_free > 0)`, a hardcoded $1.00 start gate);
`src/gui/shared_testnet.py:364-379` (9 assignments rehydrating a testnet chain's private
balances and total supply).

### 3.4 Which timers drive the engine

**33 `QTimer` instantiations verified** from 34 raw grep hits. One was a docstring line.
**Control: verified/raw = 0.97.** Of the 33, **27 are live**, 5 are dead (the owning class is
never constructed), 1 is standalone.

Following each timer one hop into its slot:

**13 bindings advance the engine or move fleet state:**

| Site | Interval | What it drives |
| --- | ---: | --- |
| `main.py:687` | 50 ms | **the asyncio pump — the engine's clock** |
| `main.py:1467` | 60 s | `bot_manager.save_all_state()` |
| `main.py:1631`, `:1641`, `:1643`, `:1647` | 250 ms poll / 2 s gap | the start-all sequencer, starting live bots |
| `main.py:1679` | 9.5 s one-shot | fleet auto-restart |
| `src/gui/bot_live_settings.py:5271` | 500 ms | polls the manual-fire future |
| `src/gui/shared_testnet.py:162` | 250 ms | testnet queue drain |
| `src/gui/shared_testnet.py:169` | 500 ms | testnet persist |
| `src/gui/history_tab.py:561` | 400 ms | polls a trade-fetch future |
| `src/gui/indicator_panel.py:811` | 3 s one-shot | runs the real `VotingEngine` |
| `src/gui/main_window.py:7199` | 2 s | `_refresh_dashboard`, which at `:8014` calls `check_live_monitor()` |

That last one is the subtle case. It is nominally a display refresh, and it crosses into the
trading side once every two seconds.

**39 bindings refresh a display only** — pulse animation, news ticker, console drain, tooltip
scan, screen recorder, progress bars, USB scan, splash animation.

### 3.5 Engine code shelved inside the GUI package

**9,580 lines in 18 files under `src/gui/` never import Qt.** Two independent counts agree
exactly.

**The Simulator engine — 13 files, 7,756 lines:**

| Lines | File | What it is |
| ---: | --- | --- |
| 2,649 | `src/gui/simulator_tab/fleet/fleet_replay_controller.py` | Ticks real `ScrummingBot` instances against a replay tape. `await bot.tick()` at `:1894`. |
| 1,186 | `src/gui/simulator_tab/nuclear_fleet_controller.py` | Looped multi-cycle fleet runner |
| 851 | `src/gui/simulator_tab/fleet/sim_exchange.py` | A venue: order placement, fills, fees, cancellation |
| 751 | `src/gui/simulator_tab/nuclear_candle_source.py` | Tape construction and deterministic noise |
| 544 | `src/gui/simulator_tab/nuclear_sim_exchange.py` | A second venue implementation |
| 462 | `src/gui/simulator_tab/nuclear_controller.py` | The v1 single-tape controller |
| 385 | `src/gui/simulator_tab/fleet/bot_state_loader.py` | Reads `bot_state.json` into `BotConfig` |
| 359 | `src/gui/simulator_tab/fleet/simulator_bot_state.py` | Sim state persistence |
| 206 | `src/gui/simulator_tab/populate_nuclear_cache.py` | Cache warmer |
| 169 | `src/gui/simulator_tab/fleet/candle_series.py` | Candle cursor |
| 110 | `src/gui/simulator_tab/fleet/master_clock.py` | Clock |
| 84 | two `__init__.py` | Re-exports |

Their imports are stdlib plus `src.trading.*`, `src.exchange.*`, `src.core.*`. **Zero Qt.
Zero third-party.**

**Five more sit loose in `src/gui/` — 1,824 lines:**

| Lines | File | What it is |
| ---: | --- | --- |
| 727 | `src/gui/history_helpers.py` | Exchange trade-history ETL: chunked 30-day pagination, gate and voting log join on plus/minus 60 s |
| 398 | `src/gui/market_inspector_fetcher.py` | Three-tier exchange OHLC fetcher |
| 303 | `src/gui/chart_data.py` | Multi-source OHLCV fetcher with CoinGecko fallback |
| 250 | `src/gui/preflight_check.py` | Sync CCXT symbol validation — **blocks bot creation** |
| 146 | `src/gui/start_balance_check.py` | Wallet sufficiency gate — **blocks bot start** |

**The real reverse edge runs the other way.** `src/trading/topology_stress.py:216` and `:294`
import from `src.gui.simulator_tab`. Both are function-local, deferred imports. Both target
shelved engine code, not widgets. **This is a packaging error, not a Qt coupling**, and step
0 fixes it for free.

**281 references across 127 files in `tests/`, `tools/` and `dev_harness/` already depend on
these modules.** The move is a rename plus an import sweep. It changes no behaviour.

**Coverage note.** `pyproject.toml:229` excludes `src/gui/*` from coverage measurement. All
9,580 lines of shelved engine code are therefore invisible to the coverage tool. Step 0 makes
them visible.

### 3.6 The dependency edges, counted

**244 import lines** in 26 GUI files reach into `core` (122), `trading` (75) and `exchange`
(47). **55 of the 122 `core` imports are `signal_contract.emit`** — a logging facility, not
business logic. Netting those out, the real business coupling is **189 import lines**,
concentrated in `bot_container` (21), `event_bus` (17), `ccxt_connector` (12),
`stone_tablets` (9), `api_logger` (6), `scrumming_bot` (5).

**11 files carry both a Qt import and a `trading` or `exchange` import. That is the migration
front:**

| Engine imports | File |
| ---: | --- |
| 36 | `src/gui/main_window.py` |
| 18 | `src/gui/bot_live_settings.py` |
| 10 | `src/gui/bot_wizard.py` |
| 10 | `src/gui/simulator_tab/fleet/fleet_replay_panel.py` |
| 6 | `main.py` |
| 3 | `src/gui/live_bot_window.py` |
| 3 | `src/gui/market_inspector.py` |
| 3 | `src/gui/settings_dialog.py` |
| 2 | `src/gui/history_tab.py` |
| 2 | `src/gui/init_wizard.py` |
| 1 | `src/gui/indicator_panel.py` |

---

## 4. WHAT THE BACKEND MUST EXPOSE

### 4.1 No interface exists today

**Instrument.** `grep -rn "flask|fastapi|uvicorn|aiohttp.web|websockets|http.server|socketserver|zmq|grpc"` over `src/`, `main.py`, `tools/`.

**Result: one hit that is a server** — `src/stocks/tradingview_bridge.py:283-319`, a
`http.server.HTTPServer` that *receives* TradingView webhooks. It is inbound, and its owning
window is never constructed.

**No API exists. This layer is 0 lines today.**

### 4.2 The refresh rates, measured

| Rate | Live timers | What they drive |
| --- | ---: | --- |
| 16 ms | 1 (conditional) | Indicator confidence-bar interpolation |
| 25 ms | 1 (boot only) | Splash paint |
| 33 ms | 1 | Bot-swarm node and wire-glow animation |
| **50 ms** | 2 | **the asyncio pump**; accent-opacity pulse |
| 80 ms | 1 | Fire-button glow |
| **250 ms** | 2 | Testnet queue drain; **simulator visual-snapshot drain** |
| 400 ms | 1 (conditional) | History-fetch future poll |
| 500 ms | 6 | **Console signal drain**; pause label; sim progress; nuclear status; manual-fire poll; testnet persist |
| 1 s | 1 per exchange tab | Data-pool pull-rate label |
| **2 s** | 2 | **the dashboard refresh**; heartbeat file |
| 5 s | 4 | GC; console-health emit; tooltip scan; target-denom rows |
| 15 s | 1 | News headline advance |
| 60 s | 2 | `bot_state.json` save; activity-log watchdog |
| 10 min | 1 | Topology proposals refresh |
| 1 h | 1 | RSS refetch |

Plus **30 `QTimer.singleShot` sites**.

**Dead timers (5):** `audio_suite.py:630`, `screen_recorder.py:197`, `screen_recorder.py:678`,
`testnet_tab.py:148`, `stock_main_window.py:514`. Hosts are nulled at
`main_window.py:5980` and `:6011`, or never constructed.

**A documented timer that does not exist.** `src/gui/main_window.py:965` states "The
MainWindow wires a QTimer at 300000ms intervals." Grep for `300000|300_000` in that file
returns exactly **one hit — that sentence**. Its owning class `CapitalRegistryPanel`
(`main_window.py:950`) has one reference repo-wide: its own `class` statement.

### 4.3 The 2-second dashboard — the trunk contract

`src/gui/main_window.py:7198-7200` fires `_refresh_dashboard` at `:7600`, **424 lines**. Per
tick:

| Call | Site | Payload |
| --- | --- | --- |
| `get_aggregate_stats()` | `:7604` | dict, **19 keys** |
| `list_bots_by_exchange(eid)` per tab | `:7665` | `list[dict]` |
| `list_bots()` | `:7670` | `list[dict]` |
| `list_bots()` **again** | `:7775` | `list[dict]` |
| `_bot_viz.update_bots(...)` | `:7686` | swarm repaint |
| `_charts_tab.update_charts(...)` | `:7695` | chart repaint, 6 overlay layers |
| `_market_inspector.update_active_symbols(...)` | `:7706` | HTF symbol set |
| `_indicator_panel.update_data(merged, symbol)` | `:7862` | per-timeframe voting dict |
| `_pump_currency_rates()` | `:7724` | 60 s inner cadence |
| `_pump_market_pairs_scout()` | `:7736` | 10 s inner cadence |
| `_schedule_async(fetch_chart_data(...))` | `:7943` | **network**, 30 s inner throttle |

Sub-cadences ride the same 2 s tick: 4 s tab refresh (`:7994`), 10 s analytics snapshot
(`:7973`), 30 s crash-recovery snapshot (`:7980`).

**Measured cost.** `BotContainer.get_status()` (`src/trading/bot_container.py:1863`) runs
`N_bots x 2 + N_bots_in_tabs` times per tick. At the operator's measured fleet of 35 bots on
one exchange tab that is **105 dict-builds every 2 seconds**, each producing a **28
top-level plus 15 nested = 43-field** dict.

**A served endpoint must build it once, not three times.**

### 4.4 The two 250 ms drains

1. `src/gui/shared_testnet.py:160-163`, `QUEUE_DRAIN_INTERVAL_MS = 250` at `:55`, calling
   `_drain_queue` at `:223`. Serialised, one request per tick.
2. `src/gui/simulator_tab/fleet/fleet_replay_panel.py:1829-1832`, literal `250`, calling
   `_drain_visual_snapshot` at `:2114`. **Latest-wins** — the worker overwrites
   `_pending_snapshot` under a lock, so an undrained frame is replaced, never queued. The
   payload at `_collect_visual_snapshot` (`:1988`) has **3 keys**; each `per_symbol` entry has
   **14 keys**; `stat_fields` has **10**.

Latest-wins is exactly WebSocket semantics. This one ports cleanly.

### 4.5 The event surface — two networks, not one

**Surface A — the EventBus. This is the UI's push contract.**

`src/core/event_bus.py:79`. Singleton at `:292`. Signature
`emit(self, topic: str, **kwargs) -> Event` at `:217`. Synchronous, on the caller's thread.
Subscribers are plain callbacks in `dict[str, list[_Subscriber]]` with **strong references**.
Wildcards via `_matches` at `:274`. History ring bounded at 1000.

**Two independent AST sweeps agree: 27 topics, 315 call sites.**

| Sites | Topic |
| ---: | --- |
| **255** | `bot.log` (**81% of all bus traffic**) |
| 14 | `bot_manager.start_all_progress` |
| 10 | `trade.filled` |
| 6 | `pnl.event` |
| 5 | `wire.created` |
| 3 | `wire.removed` |
| 2 | `indicator.tf_lock_changed` |
| 1 each | `indicator.bot_selected`, `bot.started`, `bot.stopped`, `bot.paused`, `bot.resumed`, `bot.registered`, `bot.unregistered`, `bot.error`, `bot.cooldown`, `bot.register_refused`, `bot.restore_failed`, `bot.gate_decision`, `bot.voting_panel_snapshot`, `ai.feedback`, `capital.drift_alert`, `phantom.started`, `phantom.analysis`, `phantom.error`, `timeframe.lock_created`, `ta.voting` |

**Control on this number.** A raw single-line grep for `.emit(` returns 78 distinct strings —
**a 65% noise rate**. It over-counts Qt Signal payload strings (`"Stopped."`, `"Grab failed"`,
`"Encoding final chunk..."`) and under-counts the dominant multi-line form. **AST is the only
correct instrument here.** My independent AST sweep found 36 distinct string first-arguments
to any `.emit(`, of which 27 match the topic shape `lowercase.dotted` and 9 are Qt Signal
payloads. Both sweeps agree at 27.

**0 dynamic topics. 0 positional payload arguments. The whole surface is statically
enumerable — a TypeScript union can be generated from the AST.**

**GUI subscribers: 16 sites in 5 files** — `main_window.py:5063-5076` (6),
`live_bot_window.py:282-285` (4), `bot_visualizer.py:1329-1330` (2),
`nuclear_controller.py:321-323` (3), `start_all_progress_dialog.py:97` (1).

Against **37 `Signal(...)` declarations and 297 `.connect(` sites** in `src/gui/**`. The
ratio is **297 Qt to 27 bus**. Most GUI wiring is Qt-native and does not survive.

**Surface A defects that must be fixed before the port:**

- **`trade.filled` has two incompatible payloads.** Verified by AST over
  `src/trading/scrumming_bot.py`:

  | Shape | Lines | Keyword arguments |
  | --- | --- | --- |
  | nested | `:4344`, `:5315`, `:15131`, `:15844`, `:17021` | `bot_id`, `data` |
  | flat | `:9148` | `bot_id, side, type, price, amount, size, profit, operator_initiated` |
  | flat | `:11026`, `:12387`, `:12859` | `bot_id, side, type, price, amount, size, profit` |
  | flat | `:12789` | `bot_id, side, type, price, amount, `**`usd`**`, size, profit` |

  Five nested, five flat, and one flat variant carries an extra `usd` field. A React client
  cannot type this. **Normalise before serving.**
- **3 dangling subscriptions** — `exchange.request`, `exchange.response`
  (`live_bot_window.py:284-285`), `profit.cross_bot` (`bot_container.py:2245`). No producer.
- **16 of 27 topics have no subscriber.** Only **11 (41%) are live end to end.**
- `src/core/emit_contracts.py:119-153` declares **4 of the 27 topics (15%)**.
- **3 of 5 GUI subscriber files discard the unsubscribe closure** returned by
  `event_bus.py:159-168`. That leaks a strong reference.

**Surface B — the signal_contract pins. Do NOT port this as a UI feed.**

`src/core/signal_contract.py:2473` (`emit`), `:1497` (`SignalSink`), `:1073` (frozen `Signal`
dataclass, **14 fields**: `name, site, actual, expected, ok, seq, ts, context, module, kind,
count, dt, nth, duration`). **78 pins**, registry `docs/EMITTER_IDENTIFICATION.md`, enforced
by `tools/emitter_registry_check.py` (verified today: 78/78, controls OK, **exit 0**).

It has **zero subscribers**. It writes JSONL to
`~/.acervator_logs/signals/session.jsonl` and retains `RETAIN_ROWS = 350_000` in memory. The
Console **polls** it: `_drain_signals` (`main_window.py:6613`) calls `sink.since(watermark)`
every 500 ms and renders the newest 200 into a `setMaximumBlockCount(2000)` view.

This is a verification instrument, not a data feed. **Its value in the migration is as the
acceptance test for every port.** The React version of a tab must make the same pins fire with
the same `expected` and `actual` pairs as the Qt version.

### 4.6 Chart feeds

**Shape.** `@dataclass Candle` — 6 fields, `time` in unix **seconds**, then `open`, `high`,
`low`, `close`, `volume` (`src/gui/native_chart.py:51-58`). A second isomorphic dataclass
`OHLCVCandle` (`src/gui/chart_data.py:140-147`) is re-boxed field by field at
`main_window.py:1712-1722`. **No pandas on this path.**

**Points per series — the number is not what the code asks for.** Verified at source, on the
legacy path at `src/exchange/ccxt_connector.py:1266`, where live callers land:

```python
data = await self._call_sync(self._ex.fetch_ohlcv, symbol, timeframe, limit)
```

The ccxt signature is `fetch_ohlcv(symbol, timeframe, since, limit)`. **`limit` lands in the
`since` slot.** The file documents this at `:1233-1257` as a known, deliberately unfixed
defect: the requested limit has never applied on a live call, so the exchange returns its own
page size (Coinbase: 300). It is unfixed because Heikin-Ashi is a forward recurrence and EMA
is SMA-seeded, so 100 versus 300 changes live gate decisions.

> **React contract: budget about 300 candles x 6 floats, roughly 1,800 numbers per series per
> panel, not the 100 requested at `main_window.py:1705`.** The widget applies no cap at all:
> `set_candles` stores the whole list (`native_chart.py:261`).

**Cadence — push, parent-driven, two rates.** Repaint plus overlays every **2,000 ms**
(`main_window.py:7695` calls `update_charts` at `:1270`, which calls `panel.chart.update()`
at `:1517`). Candle data at **30 s or slower per panel** (`main_window.py:7943` calls
`fetch_chart_data` at `:1636`, throttle at `:1669`). **60 repaints per data refresh.** The
only upward signal is `timeframe_changed = Signal(str)` (`native_chart.py:93`).

**Origin — three-source fallback** (`chart_data.py:174-227`): ccxt REST, then CoinGecko public
REST (**no volume — hard-set to 0.0 at `chart_data.py:299`**), then an in-memory dict with a
30 s TTL.

**Overlays.** `native_chart.py` has 8 toggles (`:158-165`), 1 on by default, and up to 12 line
series plus 3 sub-panes. `indicator_panel.py` has 12 indicators (`INDICATOR_COLS`, `:504-517`).

**Staleness hazard.** On a failed fetch, `set_error` never clears `_candles`. The old series
stays on screen (`main_window.py:1643-1652`).

### 4.7 Tables — the row contract

**41 surfaces**: 35 direct instantiations plus 6 `QTableWidget` subclasses. **Control:
verified/raw = 41/41 = 1.00.** Every site was opened and read. By class: `QTableWidget` 27,
`QListWidget` 6, `QTreeWidget` 2, **`QTableView` 0, `QTreeView` 0**.

**Two structural facts dominate:**

1. **No model layer exists.** Zero `QTableView`, zero `QAbstractTableModel`. Every table is
   item-based. **The row contract must be reconstructed from the populate methods**, because
   it exists nowhere else.
2. **Both `QTreeWidget`s are flat** — `setRootIsDecorated(False)`, `addTopLevelItem` only, no
   `addChild` anywhere. No hierarchical view exists to port.

**18 of 41 (44%) are dead.** Hosts are nulled at `main_window.py:5974-6029` ("REMOVED per
P1.7 / MEM-178").

**The 23 live surfaces:**

| Table | file:line | Cols | Rows from |
| --- | --- | ---: | --- |
| `BotStatusTable` | `main_window.py:2068`, built `:3227` | **10** | `update_bots(...)` `:2259`, 2 s tick |
| `ExtractorBotTable` | `main_window.py:2845`, built `:3239` | 8 | `update_bots` `:2928` |
| `BotListView` | `bot_swarm_list.py:122`, built `bot_visualizer.py:1500` | **12** (4 plus 8 lanes) | `set_bots(rows)` `:158` |
| History | `history_tab.py:313` | **13** | `_render_page` `:786`, `PAGE_SIZE = 100` (`:174`) |
| Indicator row A | `indicator_panel.py:1129` | 10 | `update_data` `:1911`, 11 rows or fewer |
| Indicator row B | same factory | 7 | same |
| Fleet replay | `fleet_replay_panel.py:315` | 3 | `bot_state.json` |
| Market Inspector signals | `market_inspector.py:161` | 6 | `inspector.last_signals` |
| Market Inspector pairs | `market_inspector.py:178` | 4 | `inspector.last_pairs` |
| Topology bots / wires | `market_inspector_topologies.py:139` / `:175` | 4 / 4 | proposal dicts |
| Error dialog, two tables | `main_window.py:8942` / `:8963` | 4 / 5 | `deque(maxlen=200)` |
| `bot_live_settings.py`, eight tables | `:2436, :4298, :5869, :5926, :5982, :6070, :7796, :7874` | 9, 11, 3, 3, 4, 5, 7, 4 | bot, tranches, wires, phantom, coordinator |

**Full rebuild per tick.** `setRowCount(len(...))` then every cell rewritten
(`main_window.py:2269`, `:2936`). At 2 s that is a complete teardown 30 times a minute.
React would diff instead. **This is a place where React is measurably better, not merely
newer.**

**Row caps — the pagination contract:** history 100, error buffer 200, wire transactions 20,
journal 500, alerts 100, testnet 15 and 20, leaderboard 10, tranche viewport 18 against about
230 rows of data.

**Defect:** `indicator_panel.py:2277-2280` sets 15 columns (`len(INDICATOR_COLS) + 3`) and
supplies 5 header labels. Dead today, but any automated extractor reads it as a 15-column
contract.

### 4.8 The seven feeds Python must serve

```
2000 ms  bots/status         list[dict] x 43 fields x N_bots      <- the trunk
2000 ms  aggregate           dict x 19 fields
2000 ms  ta/voting           {timeframe: {8 fields + signals[12]}}
  30 s   candles/{sym}/{tf}  list[Candle] x ~300 x 6 floats
 500 ms  signals             Signal x 14 fields, newest 200, watermark cursor
  push   bus events          27 topics, kwargs dict (normalise trade.filled first)
  60 s   state save          bot_state.json - 35 bots / 1,949 lots / 829 tranches
```

Plus a **write** channel carrying the 74 privileged operations from section 3.3.

---

## 5. WHAT DOES NOT TRANSLATE

| Thing | Where | What happens to it |
| --- | --- | --- |
| **The candle chart** | `src/gui/native_chart.py` — 2,188 lines, 1 `paintEvent`, **69 `draw*` calls** | **Rewritten, not ported.** Nothing converts `QPainter` to the DOM. Options: `<canvas>`, SVG, or a charting library. `lightweight-charts` is already named in-tree (`tradingview_chart.py:5`). |
| **The bot swarm** | `src/gui/bot_visualizer.py` — 4,038 lines, 2 `paintEvent`, 34 `draw*` calls, 73 stylesheets | **Rewritten.** A node-and-wire graph, in SVG or canvas. It also carries the `bot_state.json` second writer. |
| **The simulator visuals** | `src/gui/simulator_tab/fleet/sim_visuals.py` — 1,207 lines, 2 `paintEvent`, 22 `draw*` | Rewritten. |
| **`tests/qt_pixel.py`** | 6 helpers: `render_widget`, `pixel_at`, `assert_pixel_colour`, `sample_pixels`, `table_cell_centre`, `ensure_app` | **Dies with Qt.** It grabs a widget with `widget.grab().toImage()` and reads `image.pixelColor(point)`. Its whole reason for existing — that `item.background().color().name()` returns `#b3261e` while the stylesheet paints `#101018` — **is a Qt bug that does not exist in CSS.** A React equivalent is a screenshot diff (Playwright), which is a different tool, a different runner, and a Node dependency the repository does not have. |
| **The offscreen platform** | `QT_QPA_PLATFORM=offscreen` set in 28 or more test files and in `tests/qt_pixel.py:55` | **Dies with Qt.** This is how the suite runs GUI tests without a display. The React equivalent is jsdom (no pixels) or a headless browser (pixels, but a browser). |
| **The widget-leak guard** | `tests/conftest.py:742` (`_destroy_qt_widgets`), `:826` (`_assert_no_widget_leak`), `:684` (`_live_top_level_widgets`), plus `tests/test_widget_leak_guard.py` (11 tests) | **Dies with Qt.** It tracks live top-level widgets **by C++ address** through `shiboken6.Shiboken`, stops owned `QThread`s with a bounded `wait()`, delivers `deleteLater` per widget, and loops up to `_MAX_TEARDOWN_PASSES = 4`. React has no C++ object graph. The equivalent problem, a component that does not unmount, is a different failure with a different detector. |
| **The GUI archetype** | `dev_harness/harness/gui_archetype.py` — 1,035 lines, rules **GUI001 to GUI006** | **Stops applying.** It is a static analyser for PySide6 source. A React UI falls outside every rule, including GUI006 (a colour assertion with no pixel check). |
| **`tools/orphan_widget_scan.py`** | Reads `src/gui` with `ast`, reports interactive widgets whose name never precedes a `.connect(` | **Stops applying.** Its entire premise is the Qt signal and slot graph. |
| **The Qt threads** | 20 `QThread` references in 3 files; 6 `threading.Thread` | **Move to the backend.** A browser has web workers, but none of this work belongs in a browser. |
| **`QSplitter`** | 30 references | No HTML equivalent. Hand-built or a library. |
| **444 `setStyleSheet` calls, 287 hex literals** | 33 files | Rebuilt as CSS. The tokens must be recovered from the pixels: only 42 are named in a design-system module. |
| **`QMediaPlayer` and `QAudioOutput`** | `src/gui/audio_suite.py` (7 plus 4 refs) | HTML `<audio>`, or drop. |
| **The screen recorder** | `src/gui/screen_recorder.py` — 755 lines, `widget.grab()` frame capture | Rewritten or dropped. Electron has `desktopCapturer`. |
| **The USB auth widget** | `src/gui/usb_auth_widget.py` — 627 lines | Rewritten. An Electron main process has filesystem access; a renderer does not. |
| **The instance consent dialog** | `src/gui/instance_consent_dialog.py` — 286 lines | Rewritten. **The guard behind it (`src/core/instance_guard.py`, 924 lines) is Qt-free and survives untouched.** |

### 5.1 The one thing that already translates

**The shipped Windows build already bundles Chromium.** `tools/spec_common.py:153` declares
`PySide6.QtWebEngineWidgets` as a hidden import. `EXCLUDES`, which begins at `:219`, holds ten
entries and does not contain it.

A working HTML and JavaScript chart already exists at `src/gui/tradingview_chart.py` (340
lines). It builds a `CHART_HTML` template, loads it into a `QWebEngineView` at `:295`, and
injects data through JavaScript bridge calls.

**Its only constructor is `src/gui/stock_main_window.py:292`, and `StockMainWindow` is never
constructed by `main.py`.** The code is therefore unreachable today. That does not diminish
the point: **the pattern is proven in this tree, and the dependency already ships.**

This gives a migration path that Electron does not: **render React inside the Qt app you have
today**, one panel at a time, and only replace the shell once the panels are done. Every panel
so rendered is a panel that Electron will later host unchanged.

---

## 6. THE ORDER OF WORK

### 6.1 Steps 0 to 3 — prerequisites, none of them React

**Step 0 — move the engine out of `src/gui/`.** 18 files, 9,580 lines, zero Qt imports, 281
existing references in `tests/`, `tools/` and `dev_harness/` to re-point. It is a `git mv`
plus an import sweep. It changes no behaviour, it fixes the `topology_stress.py` reverse edge,
and it makes those lines visible to coverage for the first time (`pyproject.toml:229` excludes
`src/gui/*`). **Worth doing whether or not React ever happens.**

**Step 1 — give the engine its own clock.** `main.py:687` (50 ms pump), `main.py:1467` (60 s
save), `main.py:1631-1647` (start-all sequencer), `main.py:1679` (auto-restart). Four sites.
This item already has its own arc. The React migration makes it blocking rather than optional.

**Step 2 — build the read API.** Seven feeds (section 4.8). This is where a framework decision
actually binds, and it binds on the Python side, not the JavaScript side.

**Step 3 — normalise `trade.filled`.** Five nested payloads, five flat, one with an extra
field. One shape, then serve it.

### 6.2 Why History is the first React subsystem

**Measured against every other tab:**

| Subsystem | Files | Lines | QTimer | Engine imports | Write-ish sites | Emitters | Matrix verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| **History** | **2** | **2,154** | 4 | 10 | **0** | **7** | 6 built, 5 working, 1 unverified, 1 non-compliant |
| Asset Charts | 3 | 2,831 | **0** | **1** | **0** | 5 | 6 built, 3 working, 2 partial, 2 rules broken |
| Market Inspector | 3 | 1,574 | 2 | 3 | **0** | **0** | 7 framing, 2 absent, **6 rules broken** |
| Simulator (panels) | 5 | 5,815 | 13 | 21 | 1 | 22 | 8 framing, 7 rules broken |
| Bot Swarm | 2 | 4,452 | 3 | 15 | 2 | 2 | 9 framing, 6 rules broken |
| Console | embedded | about 426 in `main_window.py` | — | — | — | 5 | 5 built, 5 working, **0 rules broken** |
| Trading | 6 | 24,040 | 36 | 119 | 21 | 11 | 9 framing, 2 rules broken |

**History wins on five counts, and every one of them is measured, not judged:**

1. **Zero writes into trading state.** A grep for mutation and money-moving patterns over
   `src/gui/history_tab.py` returns two hits, both false positives (a variable assignment at
   `:199` and a comment at `:911`). It holds `self._bot_manager` and only reads through it.
   Verified at `:403`, `:414`, `:433`, `:673`, `:814`, `:881`, `:1355`.
2. **Its own module.** 1,427 lines in one file, not carved out of an 11,013-line god file.
3. **The boundary is already proved there.** `src/gui/history_helpers.py` is **727 lines and
   imports no Qt at all.** It is already the backend serializer. It moves in step 0 and is
   then reused unchanged.
4. **The clearest data contract in the app.** 13 named columns (`history_tab.py:314-330`),
   `PAGE_SIZE = 100` (`:174`), and a CSV export that already flattens the same rows (`:1251`).
5. **Seven emitters — the second-largest set of any tab — and they are postconditions.**

   ```
   history.05.001.postcondition.scan_complete
   history.05.002.postcondition.trades_stored
   history.05.003.postcondition.filter_options_built
   history.05.004.postcondition.filters_applied
   history.05.005.postcondition.page_rendered
   history.05.006.postcondition.joiner_indexes_built
   history.05.007.postcondition.csv_exported
   ```

   Each carries an `expected` and an `actual`. **The React port is correct when these seven
   fire with the same pairs as the Qt version.** No other tab gives an acceptance test that
   specific. Market Inspector, the next smallest, has zero.

**Asset Charts has lower raw entanglement — 0 timers, 1 engine import — and it is still the
wrong first pick.** Its renderer is 69 `draw*` calls, its indicator maths is duplicated
(`native_chart.py:276-424`), and the matrix records its MACD as numerically wrong. Porting it
first means either carrying a known-wrong indicator into React or re-implementing indicator
maths in JavaScript. **Both are forbidden by the standing rule that an indicator has one
implementation and published maths.**

**Market Inspector is smaller still and is disqualified by its own instrument gap.** Zero
emitters means a port cannot be proved not to have changed behaviour. Issue #18 asks for
those emitters by name. Fix that first, then port.

**Fix before porting History; do not carry the defect across.** The "Cost USD" column.
`history_helpers.py:146` discards the venue's own cost field and writes `amount x price`.
`history_tab.py:306` labels the column "Cost USD" and `:779-782` prefixes a dollar sign. For
any pair not quoted in dollars, the operator sees a quote-currency figure under a dollar
heading. The same number is summed into the buy and sell totals (`:944-951`) and written to
the CSV (`:1251`). This breaks the rule the operator states most plainly — the exchange is
the authority — and a migration is the correct moment to stop shipping it.

### 6.3 The full order

| # | Subsystem | Lines | Why here |
| ---: | --- | ---: | --- |
| 0 | Move the engine out of `src/gui/` | 9,580 | Mechanical, no behaviour change, fixes the reverse edge |
| 1 | Replace the Qt clock | 4 sites | The engine cannot outlive Qt without one |
| 2 | Build the read API | 0 exist | React cannot read a Python object |
| 3 | Normalise `trade.filled` | 10 sites | Two payload shapes, one topic |
| 4 | **History** | 2,154 | Zero writes, own module, 13-column contract, 7 postcondition pins |
| 5 | Console | about 426, embedded | Cleanest stream contract; 0 rules broken; the cost is the carve-out from `main_window.py` |
| 6 | Market Inspector | 1,574 | Small and clean — **gated on issue #18 giving it emitters** |
| 7 | Asset Charts | 2,831 | **Gated on deleting `native_chart.py:276-424`.** Never re-implement an indicator in JavaScript |
| 8 | Bot Swarm | 4,452 | 34 `draw*` calls; also the `bot_state.json` second writer |
| 9 | Simulator panels | 5,815 | Only after step 0 removes the engine beneath it |
| 10 | **Trading** | 24,040 | Last. 21 money-moving call sites, the Fire button, the god file |

Then: the wizards (`bot_wizard.py` 2,083, `init_wizard.py` 270), the dialogs
(`settings_dialog.py` 1,333, `bot_live_settings.py` 7,952, `buy_confirmation_dialog.py` 276,
`instance_consent_dialog.py` 286), and the shell (splash, launcher, tray, single-instance
consent).

**`src/gui/bot_live_settings.py` deserves its own line.** At 7,952 lines it is the second
largest GUI file and it holds four of the twenty worst tangle sites: self-destruct at `:2204`,
two manual-fire paths at `:2541` and `:5153`, and an unvalidated `setattr` onto a live
`BotConfig` at `:2120`. It is not a dialog. It is a control surface for live money, and it
should be scheduled with the Trading tab, not with the other dialogs.

---

## 7. THE COST

### 7.1 Why there is no week number in this report

I looked for a velocity instrument in this repository and did not find a trustworthy one.
`git log --since="90 days ago" --no-merges --first-parent` returns **13 commits across 8
distinct calendar days**, and `git diff --stat` over `src/gui` for 60 days reports **146,614
lines added**. Those two numbers cannot both describe the same work. The history was rewritten
during the "rejoin" and line endings were renormalised, so churn and commit dates measure the
rewrite, not the work.

**A schedule derived from that instrument would be fiction.** A measurement is not a finding
until its instrument has a control, and this one fails its control. The cost below is
therefore stated in work units, which I can count.

### 7.2 The work, counted

| Item | Measured size | Notes |
| --- | ---: | --- |
| Backend API | **0 lines exist** | 7 feeds plus 74 write operations |
| Engine clock replacement | 4 sites in `main.py` | small edit, large blast radius |
| Engine move out of `src/gui/` | 9,580 lines, 18 files, 281 references | mechanical |
| Duplicate logic to delete | about 490 lines, 6 blocks | `native_chart`, `investor_screen`, `cartoon_screen`, `_compose_ammo_cell`, the `indicator_panel` demo, `_compose_table_target_denom_cell` |
| GUI to re-express | 50,050 lines, 982 methods, 115 classes, 4,097 Qt call sites | |
| Hand-drawn surfaces | 16 `paintEvent`, 239 `draw*` calls | rewritten, not ported |
| Styling | 444 `setStyleSheet`, 287 hex literals, 42 named tokens | tokens recovered from pixels |
| Signal graph | 297 `.connect(` plus 37 `Signal(...)` | re-expressed as props and events |
| Tables | 23 live surfaces, no model layer | row contracts reconstructed from populate methods |
| Features to reproduce | 77 framing, 299 functions, 376 IDs | the matrix is the spec |
| Tests to rewrite | 1,537 certain, 3,141 at risk | section 8 |
| Test infrastructure to replace | `qt_pixel.py`, the offscreen platform, the leak guard, `gui_archetype.py` (1,035 lines), `orphan_widget_scan.py` | four instruments, none with a drop-in successor |

### 7.3 Rough size per subsystem

Sized by lines to re-express, plus the qualitative multiplier the evidence supports.

| Subsystem | Lines | Multiplier | Reason |
| --- | ---: | --- | --- |
| History | 2,154 | **low** | 727 of those lines already move to the backend unchanged; the rest is a paged table |
| Console | about 426 | **low, plus a carve-out** | The stream is trivial. Extracting it from an 11,013-line file is not. |
| Market Inspector | 1,574 | **low** | Two flat trees and two small tables |
| Asset Charts | 2,831 | **high** | 69 `draw*` calls; a duplicate indicator suite to delete first |
| Bot Swarm | 4,452 | **high** | 34 `draw*` calls; a node-and-wire graph; the `bot_state.json` second writer |
| Simulator panels | 5,815 | **medium** | Mostly forms and tables once the engine has moved; one latest-wins 250 ms feed |
| Trading | 24,040 | **very high** | 21 money-moving call sites, 36 engine imports, a 424-line 2 s refresh, a 1,401-line `_setup_ui`, live-money controls |
| Wizards and dialogs | about 12,200 | **high** | `bot_live_settings.py` alone is 7,952 lines and is a live-money control surface |
| Shell (Electron) | — | **medium** | splash, tray, single-instance consent, USB auth, keyring bridge, auto-update, packaging for two platforms |

### 7.4 The honest statement

**This is a multi-month program.** I will not name a number of months, because I have no
instrument that converts these units into calendar time in this repository. What I can say
plainly, and can defend from the measurements above:

- **The largest single item is not React. It is the backend API, which is 0 lines today** and
  must serve 7 feeds and 74 privileged operations before any React screen is useful.
- **The second largest is the test suite.** 1,537 tests must be rewritten in a language and
  runner the repository does not currently have, and four verification instruments
  (`qt_pixel.py`, the offscreen platform, the widget-leak guard, the GUI archetype) have no
  successor.
- **The Trading tab alone is 24,040 lines and holds the live-money controls.** It should be
  last, and it should not be started until every other subsystem has proved the pattern.
- **The prerequisites, steps 0 to 3, deliver value even if React is cancelled.** Moving the
  engine out of the GUI package, giving the engine its own clock, and normalising
  `trade.filled` are all repairs the codebase needs regardless.

**Anyone who quotes a shorter figure should be asked which of these numbers they think is
wrong.**

---

## 8. WHAT BREAKS — THE TEST SUITE

### 8.1 The baseline

`python -m pytest --collect-only -q` returns **8,812 tests collected in 16.74 s, exit 0.**
(The brief said about 8,797. The suite has grown by 15.)

### 8.2 File-level classification

| Bucket | Files | Tests |
| --- | ---: | ---: |
| A. imports Qt **and** `src.gui` | 75 | 3,006 |
| B. imports Qt only | 8 | 135 |
| C. imports `src.gui`, no Qt | 58 | 999 |
| D. neither | 167 | 4,672 |
| **TOTAL** | **308** | **8,812** |

**A plus B is 3,141 tests (35.6%) living in a file that imports Qt. That is the upper bound.**

**Bucket C (999 tests) is mostly the shelved engine** — `test_fleet_replay_controller.py`,
`test_nuclear_tablet_tapes.py`, `test_sim_spawn_drift.py`, `test_topology_stress.py` and
their neighbours. **Those survive the migration untouched.** They only import `src.gui`
because of the packaging error that step 0 fixes.

### 8.3 Per-test classification — the tight number

The file-level number over-counts. A file can import Qt at module level and still hold tests
that only exercise trading logic on a stub.

**Instrument.** Python `ast`. For each `def test_*`, take its own source text and mark it
Qt-coupled if it (a) names a symbol that resolves in the real PySide6 namespace, (b) calls a
Qt widget method from a 50-name list, (c) takes a `qtbot`, `qapp` or `app` fixture, or (d)
calls a same-module helper that does any of those. Then scale each file's ratio by its
collected count, so `@pytest.mark.parametrize` expansion is carried.

**Controls — two positive, two negative:**

| Control file | Test functions | Flagged Qt | Expected |
| --- | ---: | ---: | --- |
| `tests/test_qt_pixel_control.py` | 4 | **4** | nearly all |
| `tests/test_widget_leak_guard.py` | 11 | **9** | nearly all |
| `tests/test_reconcile_lot_book.py` | 29 | **0** | none |
| `tests/test_ta_engine_degenerate_abstention.py` | 32 | **0** | none |

**Second negative control, at scale.** Across the 225 files that do **not** import PySide6,
the classifier flags **31 of 5,671 tests — a 0.55% false-positive rate.** All 31 were
inspected. They match `.emit(` on the EventBus, or `.value()`, `.clear()` and `.count()` on
plain objects. Fifteen files, 1 to 6 tests each.

**The instrument under-reports slightly** — 9 of 11 on the leak guard, because two of those
tests assert on the fixture's own bookkeeping rather than on a widget. It does not over-report
at scale.

**Hand verification.** Sampled test bodies confirm both directions.
`test_change_a_tab_builds_on_every_hostile_value`
(`tests/test_bot_live_settings_swarm_money_admission.py:434`) builds a widget and asserts on
`widget.layout()`, and is correctly flagged. `test_the_threshold_is_read_off_the_config`
(`tests/test_tranche_despawn_timer.py:416`) asserts on a stub bot's config, and is correctly
not flagged.

### 8.4 The result

| Measure | Tests | % of 8,812 |
| --- | ---: | ---: |
| **Qt-coupled at function level — must be rewritten** | **1,537** | **17.4%** |
| Live in a Qt-importing file — upper bound | 3,141 | 35.6% |
| In a Qt file but not Qt-coupled — likely survive | 1,604 | 18.2% |
| Untouched | 5,671 | 64.4% |

**1,537 is the number to plan against. 3,141 is the number to plan against if the rewrite
disturbs the fixtures those files share** — and in practice, a shared `_build()` helper being
rewritten does disturb them.

### 8.5 Where the loss concentrates

| Qt-coupled (scaled) | of total | File |
| ---: | ---: | --- |
| 296 | 387 | `tests/test_bot_live_settings_swarm_money_admission.py` |
| 202 | 337 | `tests/test_bot_live_settings_fold_row_admission.py` |
| 144 | 287 | `tests/test_bot_live_settings_numeric_admission.py` |
| 116 | 116 | `tests/test_bot_live_settings_fire_confirm_admission.py` |
| 63 | 427 | `tests/test_tranche_despawn_timer.py` |
| 36 | 38 | `tests/test_console_tab_emitters.py` |
| 35 | 63 | `tests/test_fold_panel_surface_remainder.py` |
| 35 | 43 | `tests/test_exchange_tab_emitters.py` |
| 32 | 38 | `tests/test_clear_lifetime_tranche_counters.py` |
| 31 | 38 | `tests/test_api_tester_tab_emitters.py` |
| 30 | 30 | `tests/test_fold_panel_settles_after_a_clear.py` |
| 24 | 33 | `tests/test_ivp_persist_and_named_causes.py` |
| 24 | 26 | `tests/test_details_dialog_opens_large_enough.py` |
| 23 | 27 | `tests/test_fold_tranche_rows_are_visible.py` |
| 22 | 27 | `tests/test_tranche_row_container_styling.py` |
| 21 | 23 | `tests/test_history_tab_emitters.py` |
| 21 | 67 | `tests/test_extractor_tranche_arbiter.py` |

**758 of the 1,537 (49%) sit in five `bot_live_settings` files.** That is the same file that
holds four of the twenty worst tangle sites. The tangle and the test cost are in the same
place, which is consistent, and which means fixing one addresses the other.

### 8.6 Runtime, measured

The ten highest-Qt test files were run through pytest:

```
1349 passed in 68.30s (0:01:08)   exit 0
```

The collected count for those ten files was independently 1,349 — an exact match. **931 of
those 1,349 (69%) are Qt-coupled by the classifier.** One minute of the suite's runtime is
therefore roughly 69% work that a React UI invalidates.

### 8.7 What has no successor

Beyond the 1,537 test rewrites, four verification instruments end:

1. **`tests/qt_pixel.py`** — offscreen pixel verification. It was built because
   `item.background().color().name()` returns `#b3261e` while the stylesheet paints
   `#101018`. **That specific bug class does not exist in CSS**, so the instrument is not
   needed. But nothing in the repository currently reads a rendered pixel any other way, and
   before this module existed the count was zero.
2. **The offscreen platform.** `QT_QPA_PLATFORM=offscreen` appears in 28 or more test files.
   It is how the suite runs a GUI without a display. The React equivalent is a headless
   browser and a Node toolchain the repository does not have.
3. **The widget-leak guard.** `tests/conftest.py:684-903`. It tracks widgets by C++ address
   through `shiboken6`, stops owned `QThread`s, delivers `deleteLater` per widget, and loops
   four passes. Plus 11 tests in `tests/test_widget_leak_guard.py`.
4. **`dev_harness/harness/gui_archetype.py`** — 1,035 lines, rules GUI001 to GUI006, plus
   `tools/orphan_widget_scan.py`. Both are static analysers for PySide6 source.

**Under the standing rule that only archetypes edit archetypes, replacing the GUI archetype is
not a task this migration can perform on its own authority. It must be commissioned.**

---

## 9. FRAMEWORK — WHAT THE CODE CONSTRAINS, WHAT IT LEAVES OPEN

The CTO named Electron, React and Next.js. This section reports what the codebase decides and
what it does not. **It does not recommend a framework.**

### What the codebase CONSTRAINS

| Constraint | Evidence |
| --- | --- |
| **The backend stays Python, at least initially.** | `src/trading` is 54,205 lines with 0 Qt imports. Rewriting it is a separate, larger programme with no bearing on the UI. |
| **The UI process cannot be the trading process.** | `main.py:642-645` — every coroutine currently runs on the GUI thread. The migration's whole point is to end that. Whatever ships, the engine gets its own process or its own loop. |
| **The transport must carry a 2 s trunk, a 500 ms stream and a push channel.** | Section 4.8. That rules out request-response-only designs. It wants a socket. |
| **Server-side rendering is a poor fit for the trunk feed.** | The dashboard is 43 fields x N bots every 2 s, plus a 500 ms signal stream. That is client state, not page render. Next.js server components would sit idle on the part of the app that matters most. |
| **Indicator maths must not cross into JavaScript.** | Standing rule, plus three existing in-tree violations (`native_chart.py`, `investor_screen.py`, `cartoon_screen.py`). Every indicator value arrives computed from Python. |
| **The app needs filesystem, keyring and single-instance access.** | `src/core/encryption.py:182-235` (OS keyring), `src/core/instance_guard.py` (filesystem lease), `src/gui/usb_auth_widget.py`. A browser tab cannot do these. Something with main-process privileges is required. |
| **Two platforms ship.** | `Acervator_win.spec`, `Acervator_mac.spec`, pinned by `tests/test_specs_parity.py` (22 tests). Whatever replaces PyInstaller must be pinned the same way. |

### What the codebase LEAVES OPEN

| Open question | Why the code does not decide it |
| --- | --- |
| **React versus anything else** | Nothing in the tree depends on a component model. The constraint is "a client that can hold state and diff a table", which many things satisfy. |
| **Electron versus the web engine already shipping** | `tools/spec_common.py:153` already bundles `PySide6.QtWebEngineWidgets`, and `src/gui/tradingview_chart.py` already proves the pattern. **A React panel can render inside today's app.** Electron becomes necessary only when the Qt shell itself is retired. |
| **The transport** | WebSocket, SSE, or local HTTP polling all satisfy section 4.8. Nothing in the tree prefers one. |
| **The API framework** | FastAPI, aiohttp (already a dependency at `pyproject.toml:39`), or `http.server` (already used at `src/stocks/tradingview_bridge.py:283`). No existing code constrains this. |
| **The chart library** | `lightweight-charts` is named in-tree (`tradingview_chart.py:5`) but is not a commitment. |
| **Whether the backend later leaves Python** | The CTO raised it. Nothing in this audit bears on it. The UI boundary is the same either way, which is an argument for defining the boundary first. |

### One alternative the CTO should see before choosing

`docs/guides/2026-08-23_run_acervator_in_the_cloud.md` (869 lines, merged) is an
already-completed study of running the **existing Qt app** in the cloud with its window
visible over VNC. If the SaaS goal is "reach it from anywhere", that path exists today and
costs no migration. If the SaaS goal is "many tenants, a real web client, a product other
people can buy", it does not, and this migration is the right answer. **Those are different
goals and they have different answers.** The CTO should say which one #128 is for.

---

## 10. CONTROLS — EVERY INSTRUMENT IN THIS REPORT

| Measurement | Instrument | Control | Result |
| --- | --- | --- | --- |
| Qt symbol census | regex `\bQ[A-Z]\w+\b` on non-comment lines | resolved against 728 real PySide6 symbols | 4,097 real, 31 false, **0.75% FP** |
| Test collection | `pytest --collect-only -q` | exit code checked | 8,812, **exit 0** |
| Per-test Qt coupling | `ast` classifier | 2 positive controls (4/4, 9/11), 2 negative (0/29, 0/32), plus a 5,671-test negative at scale | **0.55% FP**, slight under-report |
| Emitter registry | `python -m tools.emitter_registry_check` | the tool's own instrument controls | 78/78, controls OK, **exit 0** |
| Bus topic count | `ast`, two independent sweeps | raw grep gives 78 distinct strings — **65% noise** | both sweeps give **27** |
| `trade.filled` shapes | `ast` over `scrumming_bot.py` | keyword lists printed per site | 5 nested, 5 flat, verified |
| Matrix citation survival | node IDs versus the full collected list | a fabricated node ID was reported broken | 136/140 = **97.1%** |
| QTimer instantiations | grep, then read each site | 1 docstring line rejected | 33/34 = **0.97** |
| Table surfaces | grep, then open every site | every site read | 41/41 = **1.00** |
| `Signal(...)` declarations | grep in `src/gui/**` | every site read | 37/37 = **1.00** |
| Widget-to-engine mutations | attribute-assignment sweep, all 74 hits hand-read | categorised into 3 classes | **37.8% presentation FP** |
| Money-moving calls | broad token sweep, 185 raw | narrowed pattern cross-checked | **75.7% FP** broad, **62.5%** narrow |
| Decision logic in GUI | threshold sweep, 62 raw | worst FP class identified (`price_top <= y <= price_bot` are **pixel** coordinates) | **59.7% FP** |
| Reverse edge (Qt in engine) | narrowed grep | the naive `Signal` pattern gives 200+ at **100% FP** | **0** real |
| Engine lines in `src/gui/` | two independent counts | both agree | **9,580** |
| Qt test-file runtime | `pytest` on 10 files, `--durations=0` | collected count matched independently | 1,349 in 68.30 s, **exit 0** |
| Repo velocity | `git log --numstat` | **FAILED ITS CONTROL** — 13 commits over 8 days versus 146,614 lines in `src/gui` | **no schedule derived** |

---

## 11. WHAT THIS AUDIT DID NOT COVER

Stated so nobody reads a silence as a finding.

- **It did not re-census the features.** The capability matrix is the feature specification.
  This audit verified its counts and citations and stopped there.
- **It did not run the full 8,812-test suite.** Only collection (exit 0) and a 1,349-test
  Qt-heavy subset (exit 0). No claim is made about whether the suite is green.
- **It did not measure GUI performance.** No frame timings, no repaint costs, no memory. The
  claim that React would diff instead of rebuilding is a statement about the technique, not a
  measured comparison on this app.
- **It did not evaluate any JavaScript library.** No React, Electron or charting library was
  installed, benchmarked or read.
- **It did not size the Electron shell in lines.** Splash, tray, auto-update, code signing,
  notarisation and installer work are named, not measured.
- **It did not audit the trading engine.** `src/trading` was searched for Qt imports and
  nothing else.
- **It did not touch the running application.** `Acervator.exe` was never started, stopped,
  attached to or queried. `~/.acervator/` and `~/.acervator_logs/` were not written.
  `coinbase_credentials.json` was never opened.
- **It produced no schedule.** Section 7.1 explains why: the velocity instrument failed its
  control.

---

## FALSIFICATION

This report is wrong if any of the following holds.

1. **A file under `src/trading`, `src/exchange`, `src/core`, `src/stocks` or
   `src/competition` imports Qt.** Section 3.1 claims zero. One real import falsifies the
   central premise that the engine is already free.
2. **`main.py:687` is not the only thing advancing the asyncio loop.** If a second pump
   exists, step 1 is smaller than stated.
3. **The per-test classifier's 1,537 is off by more than its stated 0.55% false-positive
   rate.** Re-run it. The controls are named in section 8.3 and are re-runnable.
4. **`src/gui/history_tab.py` writes to trading state anywhere.** Section 6.2 claims zero
   write sites. One real write moves History out of first place.
5. **`src/gui/history_helpers.py` imports Qt.** It is claimed to be 727 Qt-free lines that
   move to the backend unchanged.
6. **The capability matrix's citations resolve at materially less than 97.1%.** That number
   is what makes it usable as the React specification.
7. **`tools/spec_common.py` excludes `PySide6.QtWebEngineWidgets` from the build.** Section
   5.1 claims it is a hidden import, not an exclusion, and the incremental path in Part One
   depends on that being right. `EXCLUDES` begins at `:219` and holds ten entries, none of
   them Qt.
