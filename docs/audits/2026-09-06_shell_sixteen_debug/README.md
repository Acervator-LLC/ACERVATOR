# Debug reports — the sixteen shell rows

One report per Qt file that the conversion table in
[08-tabs.md](../../manual/08-tabs.md) marks as registering a panel in the
Electron shell. Each report records one run of the program under each variant
and what that run printed.

These reports sit here because `dev_harness/hooks/block_new_test.py` refuses any
new file under `tests/`.

## The tools these runs used

Each is named by its package and its command.

```
electron 44.2.0                 desktop/node_modules/electron/dist/electron.exe
CPython -X dev -X faulthandler  the interpreter's own runtime checks
PYTHONWARNINGS=error            a warning becomes a traceback
pdb                             post-mortem on the frame that raised
PySide6 qInstallMessageHandler  the toolkit's own diagnostics
```

The gate that cleared the changed files ran `ruff`, `mypy`, `pyright`,
`bandit`, `vulture`, `semgrep`, `black` and `flake8` over the Python, and
`vale` and `proselint` over these pages.

## How every run was made

Both variants ran with a throwaway home, so nothing read or wrote
`~/.acervator/` or `~/.acervator_logs/`. `~/.acervator/settings.json` hashed
`F366F42F0E49B4B3468F301B4F2F701669CC13005CFE1EBAC7A56988EC376423` before the
work and the same after it.

**React, in the Electron shell.** `tests/fixtures/conversion_rows.electron_report`
starts `desktop/main.js` under the installed Electron binary through
`tests/fixtures/electron_shell_probe.js`, redirects the backend child to a
throwaway home, opens every panel the manifest names and reports what each one
drew.

```
python -X dev -X faulthandler
# from tests/: fixtures.conversion_rows.electron_report()
```

The run answered `available: True`, 74 panel names, 13 registered panels, no
module that failed to load, and one spawned child: `python main.py --bridge`.

**Qt.** `src.gui.main_window.MainWindow` was constructed under
`ACERVATOR_VARIANT=qt` with `QT_QPA_PLATFORM=offscreen`, `HOME` and
`USERPROFILE` pointed at a throwaway directory, `PYTHONWARNINGS=error`, and
`qInstallMessageHandler` recording the toolkit's own messages. Every tab was
selected in turn and the text of each label, button, group box, combo box and
table header read off the live widget.

```
ACERVATOR_VARIANT=qt QT_QPA_PLATFORM=offscreen PYTHONWARNINGS=error \
python -X dev -X faulthandler
```

The run answered ten tabs, zero Python errors, two log warnings naming the
absent `bot_state.json` under the throwaway home, and one toolkit warning:

```
QFontDatabase: Cannot find font directory .../PySide6/lib/fonts.
```

That warning states what this machine has, not what the product does, so it is
recorded and not repaired.

**Comparing the two.** Every word a Qt tab shows was searched for in the answer
of every method `src.core.desktop_bridge.build_registry` serves and in the text
each Electron panel drew. The search is two-sided: a word known to be served,
`Ready — press Refresh.`, is found, and a word known to be absent,
`ZZ-no-such-word-ZZ`, is not.

Two faults in that search were found and corrected before any result was used.
`json.dumps` escaped every character outside ASCII, so `⏸  Pause API Log` and
five others read as absent while the model carried them. It also escaped
newlines, so the nuclear panel's empty-fleet note read as absent for the same
reason. The search now walks the values themselves.

## The reports

| Qt file | verdict |
| --- | --- |
| [bot_swarm_list.md](bot_swarm_list.md) | registers no panel |
| [bot_visualizer.md](bot_visualizer.md) | known good |
| [history_tab.md](history_tab.md) | known good, one defect corrected |
| [live_settings_bot_swarm_tab.md](live_settings_bot_swarm_tab.md) | known good |
| [live_settings_market_inspector_tab.md](live_settings_market_inspector_tab.md) | draws a placeholder, one defect corrected |
| [console_log_handler.md](console_log_handler.md) | its module is reached by nothing |
| [console_tab.md](console_tab.md) | known good |
| [empty_tabs.md](empty_tabs.md) | known good |
| [header_strip.md](header_strip.md) | known good |
| [trading_tab.md](trading_tab.md) | known good |
| [simulator_tab.md](simulator_tab.md) | known good |
| [bot_node.md](bot_node.md) | registers no panel |
| [quick_routing.md](quick_routing.md) | registers no panel |
| [visualizer_themes.md](visualizer_themes.md) | registers no panel |
| [wire_canvas.md](wire_canvas.md) | registers no panel |
| [trade_charts_tab.md](trade_charts_tab.md) | neither side drew a word |

[measurement.md](measurement.md) carries the size and time figures.
