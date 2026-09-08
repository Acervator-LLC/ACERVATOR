# `src/gui/visualizer/wire_canvas.py`

222 source lines. The table marked this row as registering a panel in the
Electron shell. The running shell says it does not.

## The error

```
Acervator panel not drawn: wire_canvas: wire_canvas.js registered no panel to draw
Panel wire_canvas did not draw: wire_canvas.js registered no panel to draw
```

`ok=False`, `registered=False`, `react=0`, `children=0`.

## Reproduction

The Electron run described in [README.md](README.md).

## The cause

`src/gui/web/wire_canvas.js` never calls
`window.acervatorPanelHost.register`. It publishes `acervatorSetWireCanvas`,
`acervatorLoadWireCanvas` and `acervatorWireCanvas` on the window.
`desktop/renderer/panel_host.js` faults any manifest name that never registers.

The wire sheet is drawn over the swarm view, not beside it.
`src/gui/web/bot_visualizer.js` holds the name in `WIRE_CANVAS_API` at line 362
and reads the object from the window, and `bot_visualizer` registered and drew.

## The correction

`Registers in Electron` for this row reads `no` in
[08-tabs.md](../../manual/08-tabs.md) and in the issue body. No code changed:
`acervatorPanelHost.screens` feeds the tab bar, so a sheet that registered
itself would take a tab.

## The rerun

The same Electron run after the unit's other corrections reports the same
answer. The Bot Swarm tab's own text carries the wire columns `Ticker`,
`Inflow`, `Outflow` and `% Out` on both sides.
