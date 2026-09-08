# `src/gui/main_tabs/console_log_handler.py`

152 source lines. The table marked this row as registering a panel in the
Electron shell. The running shell says it does not, and nothing else reads the
module either.

## The error

```
Acervator panel not drawn: console_log: console_log.js registered no panel to draw
Panel console_log did not draw: console_log.js registered no panel to draw
```

`ok=False`, `registered=False`, `react=0`, `children=0`.

## Reproduction

The Electron run described in [README.md](README.md), and a search of every
`.js` file under `src/gui/web` and `desktop/renderer` for the three names
`console_log.js` publishes.

## The cause

`src/gui/web/console_log.js` never calls
`window.acervatorPanelHost.register`. It publishes `acervatorSetConsoleLog`,
`acervatorLoadConsoleLog` and `acervatorConsoleLog` on the window, and each of
those three names occurs in exactly one file: `console_log.js` itself. No
other module reads it.

The Console screen does not need it. `src/gui/web/console_tab.js` draws the log
pane from its own view model: it reads the `log_pane` and `log_handler` fields
of `console.tab` and builds the blocks itself. The Qt side is the same shape —
`_QtLogHandler` and `_QtLogRelay` in this row paint into the pane that
`ConsoleQtTab` owns.

`console_log.js` is therefore a module the running shell loads, lists in
`desktop/renderer/module_manifest.js` and in `desktop/renderer/index.html`,
and never reaches.

## The correction

`Registers in Electron` for this row reads `no` in
[08-tabs.md](../../manual/08-tabs.md) and in the issue body.

The module is not deleted. An unused file is quarantined before it is removed,
and that call is the operator's; the finding is recorded here so it can be made
without rediscovering it.

## The rerun

The same Electron run after the unit's other corrections reports the same
answer. The Console tab drew on both sides with the same three words —
`⏸  Pause`, `Clear` and `SIGNALS — name · expected · actual` — and the Qt
Console tab built with no Python error.
