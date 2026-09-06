# Qt to React: what is on screen today

Reference. This page checks 71 files against one sentence in the conversion
item: *"Every screen in the app is drawn by Qt widgets. This item replaces them
with React."*

Audit date: 5 September 2026. Read-only. This page changes no product code.

## The answer

**One of the 71 files puts React on the screen he opens: the History table.**

That is the same one the item named when it opened. The item's own sentence,
*"One panel is React: the History table"*, still describes the application
today.

The other 70 files have a React module, a Python view model and a place in the
page list. None of them draws a pixel in the application he runs.

## The 71 files, and how this page found them

A file counts as targeted when a conversion unit built a React module and a
Python view model for it. Two lists give the same set:

| source | count |
|---|---:|
| Python files under `src/gui` that import Qt today | 69 |
| plus `src/gui/preflight_check.py` and `splash_screen.py`, each with a view model and a paired test but no Qt import | 2 |
| **targeted files** | **71** |

The second row matters. Both files carry a view model in `src/gui/main_tabs/`
and a paired test under `tests/`, so a unit worked on them, and neither
imports Qt.

## The five questions, and why the fifth answers the item

| # | question | what a yes proves |
|---|---|---|
| 1 | Does a React module exist for it | a `.js` file sits on disk |
| 2 | Does that module use React | it calls `React.createElement` |
| 3 | Does the bridge register its view model | `src/core/desktop_bridge.py` answers a request for it |
| 4 | Does the page list name the module | `desktop/renderer/module_manifest.js` loads the file |
| 5 | Does the running program draw it | he sees React where he used to see Qt |

Questions 1 to 4 pass together for 63 files. Question 5 passes for one. The
first four are the ones the progress counts measured.

## What "paired" proves, and what it does not

`tools/conversion_state.py` reports 63 files paired, 1 unpaired and 5 not a
screen. Its own definition of paired is two conditions, and either one is
enough:

- A `.js` file that the page loads declares a bridge method, and
  `src/core/desktop_bridge.py` registers a view model for that same method, and
  the words of the method name sit inside the Qt file's folder path.
- The Qt file itself holds the name of a `.js` file the page loads.

**Paired proves the wiring exists.** A React module sits on disk, the Python
side answers it, and the page loads it.

**Paired proves none of these:**

- that the module draws anything,
- that the Electron shell runs,
- that the Qt widget stopped drawing,
- that he sees React when he opens the tab.

The word measures a link between three files. The item asks about a screen.

## What the Electron shell drew

Nobody had started the shell before. This audit started it and read the page.

The shell needed one repair first. `desktop/node_modules/electron` held the
wrapper package and no program. The folder that holds the program, and the file
that records where it sits, were both absent, so `electron` could not start.
The package's own installer fetched the 235 MB program, and the shell then
started.

What the running window reported about itself:

| measurement | value |
|---|---:|
| React modules the page list names | 70 |
| modules that failed to load | 0 |
| modules that register a panel to draw | 2 |
| panels the page asked to draw | 2 |
| panels that failed to draw | 0 |
| surfaces visible on the page | 3 |

The three that drew are the History table, the Console tab panel and the header
strip. Every other module loaded, defined its code, and registered nothing, so
the page had nothing to ask it for. Two files call `register` on the panel
host: `src/gui/web/console_tab.js` and `src/gui/web/header_strip.js`.

The screen capture shows one thing: an empty History table filling the window.
It reads `0 of 0 trades shown`. The shell asks the Python side for the History
view model and sends no trades with the request, and
`src/exchange/history_surface.py` takes its rows from the request. The shell
draws a correct, empty table.

The shell has no tab bar, no menu and no navigation. It stacks whatever draws
down one page.

**Method, and what it cannot see.** This audit ran the shipped
`desktop/main.js` without changing it, then read the page's own account of what
drew. The reading covers the first six seconds after the page loads. A panel
that draws later than that would not appear in the count.

## What his own application draws

`src/gui/history_tab.py` builds one table and asks
`src/gui/history_table_variant.py` which class to use. That file holds the only
call to `resolve_variant` in `src/_variant.py`, and `src/_variant.py` names
`react` as the default. The React build draws the History table with
`HistoryWebTable` in `src/gui/react_history_panel.py`, inside the browser view
Qt already ships. `src/gui/history_tab.py` feeds that table his real trades.

That one call site is the whole difference between the two builds. Every other
tab builds the same Qt widget in both.

Two files under `src/` build a browser view: `src/gui/react_history_panel.py`
and `src/gui/tradingview_chart.py`. Only the first loads React. The second
loads a charting library.

**Method, and what it cannot see.** This audit read the code path instead of
the running window, because the trading application must stay untouched while
it holds real money. The path has one branch and one caller, so it admits one
answer.

## The table

Column 5 answers one question: does he see a React panel when he opens that
screen.

- **yes** — React draws where Qt used to.
- **shell only** — the module draws in the Electron shell and nowhere else.
- **no - Qt draws it** — the Qt widget is still the screen.
- **no - screen not built** — the application constructs no such screen, so no
  conversion can show.
- **no - never loaded** — the React build never imports the file.
- **no - not a screen** — the file holds helpers or a package marker.

| Qt file | 1 React module | 2 uses React | 3 on the bridge | 4 in the page list | 5 on his screen |
| --- | --- | --- | --- | --- | --- |
| `splash_screen.py` | no | - | yes | no | no - never loaded |
| `src/gui/alerts_tab.py` | `alerts_tab.js` | createElement | yes | yes | no - screen not built |
| `src/gui/analytics_tab.py` | `analytics_tab.js` | createElement | yes | yes | no - screen not built |
| `src/gui/audio_suite.py` | `audio_suite.js` | createElement | yes | yes | no - screen not built |
| `src/gui/bot_live_settings.py` | `bot_live_settings.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/bot_swarm_list.py` | `bot_swarm_list.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/bot_visualizer.py` | `bot_visualizer.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/bot_wizard.py` | `bot_wizard.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/buy_confirmation_dialog.py` | `buy_confirmation.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/competition_tab.py` | `competition_tab.js` | createElement | yes | yes | no - screen not built |
| `src/gui/crypto_news_ticker.py` | `crypto_news_ticker.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/history_qt_table.py` | no | - | no | no | no - never loaded |
| `src/gui/history_tab.py` | `history_tab.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/indicator_panel.py` | `indicator_panel.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/init_wizard.py` | `init_wizard.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/instance_consent_dialog.py` | `instance_consent_dialog.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/journal_tab.py` | `journal_tab.js` | createElement | yes | yes | no - screen not built |
| `src/gui/launcher.py` | `launcher.js` | createElement | yes | yes | no - screen not built |
| `src/gui/live_bot_window.py` | no | - | yes | no | no - screen not built |
| `src/gui/live_settings/bot_swarm_tab.py` | `bot_swarm_settings_tab.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/live_settings/fold_chrome.py` | `fold_chrome.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/live_settings/fold_tokens.py` | `fold_tokens.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/live_settings/fold_tranches_tab.py` | `fold_tranches_tab.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/live_settings/market_inspector_tab.py` | `market_inspector_tab.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/live_settings/phantom_bots_tab.py` | `phantom_bots_tab.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/live_settings/positions_held_tab.py` | `positions_held.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/live_settings/settings_tab.py` | `live_settings_tab.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/live_settings/stack_tranches_tab.py` | `stack_tranches_tab.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/live_settings/status_tab.py` | `live_status_tab.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/main_tabs/console_log_handler.py` | `console_log.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/main_tabs/console_tab.py` | `console_tab.js` | createElement | yes | yes | shell only |
| `src/gui/main_tabs/header_strip.py` | `header_strip.js` | createElement | yes | yes | shell only |
| `src/gui/main_tabs/trading_tab.py` | `trading_tab.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/main_window.py` | no | - | yes | no | no - Qt draws it |
| `src/gui/market_inspector.py` | `market_inspector.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/market_inspector_topologies.py` | `market_inspector_topologies.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/native_chart.py` | `native_chart.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/preflight_check.py` | `preflight_check.js` | createElement | yes | yes | no - not a screen |
| `src/gui/qt_safe_events.py` | no | - | yes | no | no - not a screen |
| `src/gui/react_history_panel.py` | `history_panel.js` | createElement | yes | yes | **yes** - the History table |
| `src/gui/risk_tab.py` | `risk_tab.js` | createElement | yes | yes | no - screen not built |
| `src/gui/settings_dialog.py` | `settings_dialog.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/shared_testnet.py` | `shared_testnet.js` | neither | yes | yes | no - Qt draws it |
| `src/gui/simulator_tab/fleet/fleet_replay_panel.py` | `fleet_replay_panel.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/simulator_tab/fleet/sim_visuals.py` | `sim_visuals.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/simulator_tab/nuclear_mode_panel.py` | `nuclear_mode_panel.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/simulator_tab/sim_stat_strip.py` | `sim_stat_strip.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/simulator_tab/simulator_tab.py` | `simulator_tab.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/start_all_progress_dialog.py` | `start_all_progress.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/stock_main_window.py` | no | - | yes | no | no - screen not built |
| `src/gui/testnet_tab.py` | `testnet_tab.js` | createElement | yes | yes | no - screen not built |
| `src/gui/tradingview_chart.py` | `tradingview_chart.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/usb_auth_widget.py` | `usb_auth_widget.js` | createElement | yes | yes | no - screen not built |
| `src/gui/visualizer/bot_node.py` | `bot_node.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/visualizer/quick_routing.py` | `quick_routing.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/visualizer/themes.py` | `visualizer_themes.js` | neither | yes | yes | no - Qt draws it |
| `src/gui/visualizer/wire_canvas.py` | `wire_canvas.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/widgets/__init__.py` | `shared_widgets.js` | createElement | yes | yes | no - not a screen |
| `src/gui/widgets/api_tester_tab.py` | `api_tester_tab.js` | createElement | yes | yes | no - screen not built |
| `src/gui/widgets/bot_selection.py` | `bot_selection.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/widgets/bot_status_table.py` | `table_cells.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/widgets/capital_registry_panel.py` | `capital_registry.js` | createElement | yes | yes | no - screen not built |
| `src/gui/widgets/dashboard_stat_card.py` | `dashboard_stat_card.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/widgets/exchange_tab.py` | `exchange_tab.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/widgets/extractor_bot_table.py` | `extractor_bot_table.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/widgets/notification_spool.py` | `notification_spool.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/widgets/privacy_dot.py` | `privacy_dot.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/widgets/pulse_manager.py` | `pulse_manager.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/widgets/spendable_profits.py` | `spendable_profits.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/widgets/status_log.py` | `status_log.js` | createElement | yes | yes | no - Qt draws it |
| `src/gui/widgets/trade_charts_tab.py` | `trade_charts_tab.js` | createElement | yes | yes | no - Qt draws it |
| **totals of 71** | **65** | **63** | **70** | **65** | **1** |

### The column 5 count

| answer | files |
|---|---:|
| yes, React draws it in the application | 1 |
| the Electron shell draws it, and nothing else | 2 |
| no, the Qt widget still draws the screen | 50 |
| no, the application builds no such screen | 13 |
| no, the file holds helpers, not a screen | 3 |
| no, the React build never loads the file | 2 |
| **total** | **71** |

Thirteen of the 71 belong to screens the application never constructs. The
conversion cannot show on those, whatever the React module does, because he
has no way to open them.

## What the work produced

The record holds 319 commits on `current` whose message names the item, 78 of
them outside a merge. Here is what they left on disk.

### Code the conversion added

| what | files | lines |
|---|---:|---:|
| React modules, `src/gui/web/*.js` | 70 | 80,292 |
| Python view models, in `src/gui/main_tabs/` and `src/exchange/` | 74 | 74,207 |
| Electron shell, `desktop/` | 8 | 791 |
| **total** | **152** | **155,290** |

### Tests the conversion added

| what | files | lines |
|---|---:|---:|
| test files naming a view model or a React module | 180 | 287,342 |

That is **1.85 lines of test for every line of product code**.

### Qt code, at the item's start and today

| | files | lines |
|---|---:|---:|
| Python files under `src` importing Qt, 25 August | 36 | 47,865 |
| Python files under `src` importing Qt, 5 September | 69 | 39,952 |

The file count went up and the line count went down. The rise is a split, not
new Qt: `src/gui/live_settings/`, `src/gui/widgets/` and `src/gui/visualizer/`
did not exist on 25 August, and each now holds pieces carved out of two very
large files. `src/gui/main_window.py` fell from 11,013 lines to 3,548.

The item body states that 75 files under `src` import Qt. The measured figure
today is 69 by parsing each file's imports, and 74 by searching for the name.
The five-file gap is four view models and one tool that name Qt inside a text
message and import nothing.

## What is reusable, and what is not

**Reusable, and worth keeping:**

- The 70 React modules. 63 of the 71 targeted files have one, and 63 call
  `React.createElement`. They load without error.
- The 74 Python view models. They hold no Qt and no exchange call, so any
  frontend can read them.
- The request boundary in `src/core/desktop_bridge.py`. It answers 74 methods
  over the child process's own pipe. It opens no port and no socket.
- The split of the two large Qt files. `src/gui/main_window.py` is a third of
  its former size, and that gain holds whatever happens to the conversion.
- The Electron shell. It starts, it reaches the Python side, and it draws.

**Not yet what the item asked for:**

- 68 of the 70 React modules register no panel, so the page cannot draw them.
  A module that draws needs one call to `register` on the panel host, the way
  `src/gui/web/console_tab.js` does.
- The shell has no tab bar. Every panel that draws stacks down one page.
- The view models read their values out of the request. The shell sends an
  empty request, so a panel that does draw shows an empty state. Only
  `src/gui/history_tab.py`, on the Qt side, fills a view model with live
  values.
- Every tab except the History table still builds its Qt widget.

## The next three steps, in order

1. **Give one module a panel registration and a loader that asks for real
   values.** Console is the shortest path: `src/gui/web/console_tab.js`
   already registers, so it needs the data only.
2. **Give the shell a tab bar** so a panel can own a screen instead of a strip
   of one long page.
3. **Feed the view models from the running system** instead of from the
   request, so a drawn panel shows his numbers.

Until step 3, a panel in the shell is a correct drawing of nothing.
