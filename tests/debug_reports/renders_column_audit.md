# The RENDERS column, measured against the running program

## The denominator

The conversion table in `docs/manual/08-tabs.md` holds 80 rows. 42 of them are
marked in scope. 41 of those 42 claim `yes`; one claims a dash.

```
rows in the conversion table       80
marked in scope                    42
  RENDERS reads yes                41
  RENDERS reads a dash              1
measured here                      38
could not measure                   4
```

Of the 38 measured, 26 agree with the cell and 12 disagree. Every disagreement
is the same direction: the cell claims more than the operator gets. No row
claims less than he gets.

## What was measured, and with what

Five readings were taken, each from a running program. No cell was read as
evidence for itself, and no module was driven by hand.

```
W  the built window     MainWindow() offscreen, then add_exchange_tab as main.py calls it
S  the variant seam     surface_class(screen) at run time, with the qt side as the control
D  the settings window  the Live Bot Settings window on the real 38-bot fleet
E  the Electron shell   one launch, all panels mounted, the text each one drew
L  the root logger      the handler classes the window installs
```

The main program was never started. It writes an ownership file into the live
runtime tree, and the operator is trading. Every probe ran with a temporary
home directory, so nothing was written into that tree. Where a real fleet was
needed the saved state file was copied out and read from the copy.

### The instruments have controls

Each reading below reports a control beside it, so a zero is a fact about the
screen and not about the counter.

```
W  window census      8 modules report Qt widgets present, 34 report none
S  seam               all 16 screens answer a different class under qt
D  settings window    React holds 2 widgets, Qt holds 394 on the same bot
D  page reader        7 tabs give 7 different text lengths, 362 to 2182
D  element reader     window-root is found, the eight page ids are not
E  shell panels       17 panels drew text, 2 drew none
L  root logger        0 handlers before the window, 1 after
```

### What the built window showed

The window builds ten tabs. Eight hold a web view that drew React text. Two
hold none.

```
Sim            react_simulator_tab.SimulatorTabReact        559 characters
Paper          react_paper_trader_tab.PaperTraderTabReact   829
Live           PySide6.QtWidgets.QWidget                    no web view
Charts         widgets.trade_charts_tab.TradeChartsTab      no web view
Inspector      react_market_inspector_tab                   724
Swarm          react_bot_swarm_tab.BotSwarmReactTab        3400
Accumulation   react_empty_tab.EmptyTabReactPanel            71
History        react_history_tab.HistoryReactTab            177
Status         react_empty_tab.EmptyTabReactPanel            64
Console        react_console_tab.ConsoleReactTab            784
```

The same window holds these Qt product classes, counted by walking it:

```
crypto_news_ticker.CryptoNewsTicker         1
indicator_panel.IndicatorVotingPanel        1
indicator_panel.CollatedPillarsWidget       1
indicator_panel.ConfidenceBarsWidget        2
indicator_panel._IVPPrivacyDot              1
native_chart.ChartPanel                     1
native_chart.CandlestickChart               1
widgets.bot_status_table.BotStatusTable     1
widgets.exchange_tab.ExchangeTab            1
widgets.extractor_bot_table.ExtractorBotTable 1
widgets.status_log.StatusLog                1
widgets.trade_charts_tab.TradeChartsTab     1
```

### What the Live Bot Settings window showed

Opened on a bot from the real fleet, the running build gives a window of two
widgets: one container and one web view. The Qt side of the same seam entry
gives 394 widgets on the same bot. Both sides carry the same seven tab labels.

```
running   BotLiveSettingsReactDialog     2 widgets   1 web view
qt        BotLiveSettingsDialog        394 widgets   0 web views

tab labels, both sides
Status  Settings  Fold Tranches  Stack Tranches  Bot Swarm  Market Inspector  Phantom Bots

text each tab drew, React side
Status 362   Settings 2182   Fold Tranches 1094   Stack Tranches 526
Bot Swarm 657   Market Inspector 379   Phantom Bots 902
```

The Status page drew the bot's own figures, so the page is filled from the
fleet and not from a fixture.

```
CHIP/USD SCRUMMING  IDLE
Realised P/L: $+36.2965      Unrealised P/L: $+53.7583
Avg Entry (exchange): $0.03965625     Cost Basis Total: $214.6593
Fees Paid: $45.5352   Total Trades: 508   Uptime: 90581s
```

Neither side carries a Positions Held tab.

### What the Electron shell showed

One launch, the backend started as the surface bridge rather than the trading
program. The renderer list names 69 modules. Every one loaded. 19 of them
register a panel, and mounting all 19 raised no fault.

```
modules named in the renderer list    69
modules that failed to load            0
modules that register a panel         19
panels that faulted                    0
panels that drew text                 17
panels that drew nothing               2   bot_swarm_tab, market_inspector_topologies
```

## The table

`claims` is the cell today. `measured` is what the operator gets. The values
are the three the page defines: React draws where Qt used to, the module draws
in the shell alone, or the Qt widget is still the screen.

| Qt file | claims | measured | evidence | verdict |
| --- | --- | --- | --- | --- |
| `src/gui/alerts_tab.py` | yes | yes | S: React holds 2 widgets and 1 web view, Qt holds 60 and none | agree |
| `src/gui/bot_live_settings.py` | yes | yes | D: React window 2 widgets against Qt 394 | agree |
| `src/gui/bot_visualizer.py` | yes | yes | W: the Swarm page is the React class, the Qt class is absent | agree |
| `src/gui/bot_wizard.py` | - | not measured | W: 7 Qt classes defined, none built; no shell panel | none |
| `src/gui/buy_confirmation_dialog.py` | yes | yes | S: the seam returns the React dialog, the qt call returns the Qt one | agree |
| `src/gui/crypto_news_ticker.py` | yes | **-** | W: the Qt ticker is in the window; no shell panel | **disagree** |
| `src/gui/history_tab.py` | yes | yes | W: the History page is React and drew 177 characters | agree |
| `src/gui/indicator_panel.py` | yes | **shell** | W: 5 Qt widgets in the window; E: the panel drew 216 | **disagree** |
| `src/gui/live_settings/bot_swarm_tab.py` | yes | yes | D: the Bot Swarm tab drew 657 characters | agree |
| `src/gui/live_settings/fold_chrome.py` | yes | yes | D: the Qt window is not built, so its delegate never runs | agree |
| `src/gui/live_settings/fold_tranches_tab.py` | yes | yes | D: the Fold Tranches tab drew 1094 characters | agree |
| `src/gui/live_settings/market_inspector_tab.py` | yes | yes | D: the Market Inspector tab drew 379 characters | agree |
| `src/gui/live_settings/phantom_bots_tab.py` | yes | yes | D: the Phantom Bots tab drew 902 characters | agree |
| `src/gui/live_settings/positions_held_tab.py` | yes | **-** | D: no such tab on either side, 7 labels each | **disagree** |
| `src/gui/live_settings/settings_tab.py` | yes | yes | D: the Settings tab drew 2182 characters | agree |
| `src/gui/live_settings/stack_tranches_tab.py` | yes | yes | D: the Stack Tranches tab drew 526 characters | agree |
| `src/gui/live_settings/status_tab.py` | yes | yes | D: the Status tab drew 362 characters of live figures | agree |
| `src/gui/main_tabs/console_log_handler.py` | yes | **-** | L: its handler is installed on the root logger, 0 before and 1 after | **disagree** |
| `src/gui/main_tabs/console_tab.py` | yes | yes | W: the Console page is React and drew 784 characters | agree |
| `src/gui/main_tabs/empty_tabs.py` | yes | yes | W: both empty pages are the React panel, the Qt panel is absent | agree |
| `src/gui/main_tabs/header_strip.py` | yes | not measured | W: the file defines no widget class, so no instance can be counted | none |
| `src/gui/main_tabs/trading_tab.py` | yes | **-** | W: the Live tab has no web view; its page holds the Qt exchange screen | **disagree** |
| `src/gui/main_window.py` | yes | **part** | W: the tab book is React; the frame, menu bar and status bar are Qt | **disagree** |
| `src/gui/market_inspector.py` | yes | yes | W: the Inspector page is React and drew 724 characters | agree |
| `src/gui/market_inspector_topologies.py` | yes | not measured | E: its shell panel drew 0 characters; the app screen was not resolved to it | none |
| `src/gui/native_chart.py` | yes | **shell** | W: both Qt chart classes are in the window; E: the panel drew 22 | **disagree** |
| `src/gui/paper_trader_tab.py` | yes | yes | W: the Paper page is React and drew 829 characters | agree |
| `src/gui/settings_dialog.py` | yes | yes | S: the seam returns the React dialog, the qt call returns the Qt one | agree |
| `src/gui/simulator_tab.py` | yes | yes | W: the Sim page is React and drew 559 characters | agree |
| `src/gui/start_all_progress_dialog.py` | yes | yes | S: the seam returns the React dialog, the qt call returns the Qt one | agree |
| `src/gui/visualizer/bot_node.py` | yes | yes | W: the Swarm page is React, drew 3400 characters, Qt class absent | agree |
| `src/gui/visualizer/quick_routing.py` | yes | yes | W: the Swarm page is React, Qt class absent | agree |
| `src/gui/visualizer/themes.py` | yes | not measured | W: the file defines no widget; it is a colour table, not a screen | none |
| `src/gui/visualizer/wire_canvas.py` | yes | yes | W: the Swarm page drew the wire instructions, Qt class absent | agree |
| `src/gui/widgets/bot_status_table.py` | yes | **-** | W: the Qt table is in the window; no shell panel | **disagree** |
| `src/gui/widgets/dashboard_stat_card.py` | yes | yes | W: five React cards in the window, no Qt card | agree |
| `src/gui/widgets/exchange_tab.py` | yes | **-** | W: the Qt exchange screen is the Live tab's page; no shell panel | **disagree** |
| `src/gui/widgets/extractor_bot_table.py` | yes | **-** | W: the Qt table is in the window; no shell panel | **disagree** |
| `src/gui/widgets/privacy_dot.py` | yes | yes | W: no Qt dot in the window while five React cards are open | agree |
| `src/gui/widgets/spendable_profits.py` | yes | yes | S: React holds 2 widgets, Qt holds 19; the React one is in the window | agree |
| `src/gui/widgets/status_log.py` | yes | **shell** | W: the Qt log is in the window; E: the panel drew 15 | **disagree** |
| `src/gui/widgets/trade_charts_tab.py` | yes | **shell** | W: the Charts tab has no web view; E: the panel drew 24 | **disagree** |

## Rows where the cell overclaims

Twelve rows say `yes` and the operator does not get React.

| Qt file | measured | what the operator gets |
| --- | --- | --- |
| `src/gui/main_tabs/trading_tab.py` | - | the Live tab draws no web view at all |
| `src/gui/widgets/exchange_tab.py` | - | the Qt exchange screen is the Live tab's page |
| `src/gui/widgets/bot_status_table.py` | - | the Qt bot table, inside that exchange screen |
| `src/gui/widgets/extractor_bot_table.py` | - | the Qt extractor table, inside that exchange screen |
| `src/gui/crypto_news_ticker.py` | - | the Qt ticker; its module registers no shell panel |
| `src/gui/live_settings/positions_held_tab.py` | - | no Positions Held tab exists on either side |
| `src/gui/main_tabs/console_log_handler.py` | - | its Qt handler is installed and running |
| `src/gui/main_window.py` | part | a React tab book inside a Qt frame, menu bar and status bar |
| `src/gui/widgets/trade_charts_tab.py` | shell | the Qt Charts tab; the React module draws only in the shell |
| `src/gui/native_chart.py` | shell | the Qt chart, inside that Charts tab |
| `src/gui/indicator_panel.py` | shell | the Qt voting panel; the React module draws only in the shell |
| `src/gui/widgets/status_log.py` | shell | the Qt log pane; the React module draws only in the shell |

Nine of the twelve are one connected area. The Live tab, the exchange screen
inside it and its two tables are one stack. The Charts tab and its chart are a
second. The voting panel, the log pane and the ticker sit beside them.

## Rows where the cell underclaims

None. One row claims a dash, and it is in the list below.

## Rows I could not measure

Four rows, each with the reason.

| Qt file | why not |
| --- | --- |
| `src/gui/bot_wizard.py` | it opens only from a button inside the exchange screen. Seven Qt classes are defined and none is built in the window; its module registers no shell panel. The cell already claims a dash |
| `src/gui/main_tabs/header_strip.py` | the file defines no widget class, so the class census cannot see it, and the strip's container in the window is a plain widget naming no module. Its React children are present: five stat cards and the profits strip |
| `src/gui/market_inspector_topologies.py` | its two Qt classes are not built, and the Inspector screen is React. Its own shell panel mounted and drew no text, so nothing showed that the topologies content draws anywhere |
| `src/gui/visualizer/themes.py` | the file defines no widget. It is a colour table, so none of the three values describes it |

## What the three rows with no React module show

The brief named three rows marked React module `no` and RENDERS `yes`. They do
not share an answer.

**Status tab.** React draws it. The Live Bot Settings window is one web view,
and its Status page drew 362 characters of the bot's own figures. The renderer
list does carry a module for this screen; the React module cell is what is
wrong on that row, not the RENDERS cell.

**Positions Held tab.** Nothing draws it. The Qt window and the React window
carry the same seven tab labels, and Positions Held is not among them. The
renderer list carries a file for it, and no panel of that name registers.

**Console log handler.** Its Qt code is running. Building the window takes the
root logger from zero handlers to one, and that one is the handler this file
defines. The file draws no screen of its own, so no React module can replace
it; the Console pane it feeds is React.

## What the operator sees differently because of this unit

Nothing. This unit changed no screen. It measured the column that says whether
a screen is finished, and found twelve of the forty-two in-scope rows claiming
a screen the operator does not have.
