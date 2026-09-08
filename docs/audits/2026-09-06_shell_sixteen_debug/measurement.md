# What the sixteen rows cost

## The figure

**Median 0.36 seconds per source line**, over a range of 0.06 to 2.92.

## How it was measured

Wall clock ran from the first program start to the last report written:
**2,244 seconds, 37 minutes 24 seconds**. The sixteen files hold **7,570
source lines**, counted with `wc -l`.

Almost every run covered all sixteen rows at once. One start of the Electron
shell opens every panel; one construction of `MainWindow` reaches every tab.
The time is therefore allocated equally: **140.2 seconds per file**. Seconds per source
line is that share divided by the file's own line count, and the figure above
is the median of those sixteen numbers.

| Qt file | source lines | seconds per source line |
| --- | --- | --- |
| `src/gui/bot_visualizer.py` | 2253 | 0.06 |
| `src/gui/simulator_tab/simulator_tab.py` | 947 | 0.15 |
| `src/gui/history_tab.py` | 837 | 0.17 |
| `src/gui/widgets/trade_charts_tab.py` | 521 | 0.27 |
| `src/gui/visualizer/bot_node.py` | 455 | 0.31 |
| `src/gui/live_settings/bot_swarm_tab.py` | 451 | 0.31 |
| `src/gui/visualizer/quick_routing.py` | 451 | 0.31 |
| `src/gui/main_tabs/trading_tab.py` | 438 | 0.32 |
| `src/gui/bot_swarm_list.py` | 351 | 0.40 |
| `src/gui/visualizer/wire_canvas.py` | 222 | 0.63 |
| `src/gui/main_tabs/console_log_handler.py` | 152 | 0.92 |
| `src/gui/main_tabs/header_strip.py` | 127 | 1.10 |
| `src/gui/main_tabs/empty_tabs.py` | 120 | 1.17 |
| `src/gui/visualizer/themes.py` | 116 | 1.21 |
| `src/gui/main_tabs/console_tab.py` | 81 | 1.73 |
| `src/gui/live_settings/market_inspector_tab.py` | 48 | 2.92 |

## What the number includes

Reading the conversion table and the issue body; four starts of the Electron
shell under `electron 44.2.0`; four constructions of the main window under
`CPython -X dev -X faulthandler` with `PYTHONWARNINGS=error`; the separate
constructions of the header strip, the charts tab and the two Live Bot Settings
tabs; the comparison of every word against every model the bridge serves,
including the two corrections that comparison itself needed; a `pdb`
post-mortem; three code corrections with a run before and a run after each; the
sixteen reports; and the table rewrite in the manual and the issue.

## What it does not include

The gate — `ruff`, `mypy`, `pyright`, `bandit`, `vulture`, `semgrep`, `black`,
`flake8`, `vale` and `proselint` — and the commit, both of which ran after the
clock was read. It does not include installing anything: `electron`, Node and
PySide6 were already in place.

## What the equal split hides

Four files needed a run of their own, because they are not built by the main
window: `live_settings/market_inspector_tab.py`,
`live_settings/bot_swarm_tab.py`, `main_tabs/header_strip.py` and
`widgets/trade_charts_tab.py`. Their true cost is above the share and the other
twelve are below it. The median is driven by the median file size, 394 lines,
rather than by any one file's difficulty.

## Errors

Four errors were found. Three were corrected and one is a conversion gap that
a correction cannot close.

| where | what | corrected |
| --- | --- | --- |
| `market_inspector_tab_surface.view_model` | ran a build with no builder, so an `AttributeError` reached the screen | yes |
| `history_tab.py` | typed five status sentences the contract declares, so a change to the contract reached one variant only | yes |
| `nuclear_mode_panel.py` | held its own copy of the surface's empty-fleet note | yes |
| `market_inspector_tab.js` | draws a placeholder slot where the Qt tab draws the per-bot card | no |
