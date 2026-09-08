# `src/gui/visualizer/quick_routing.py`

451 source lines. The table marked this row as registering a panel in the
Electron shell. The running shell says it does not.

## The error

```
Acervator panel not drawn: quick_routing: quick_routing.js registered no panel to draw
Panel quick_routing did not draw: quick_routing.js registered no panel to draw
```

`ok=False`, `registered=False`, `react=0`, `children=0`.

## Reproduction

The Electron run described in [README.md](README.md).

## The cause

`src/gui/web/quick_routing.js` never calls
`window.acervatorPanelHost.register`. It publishes
`acervatorSetQuickRouting`, `acervatorLoadQuickRouting` and
`acervatorQuickRouting` on the window.
`desktop/renderer/panel_host.js` faults any manifest name that never registers.

The routing matrix belongs to the swarm view.
`src/gui/web/bot_visualizer.js` holds the name in `QUICK_ROUTING_API` at line
366 and reads the object from the window, and `bot_visualizer` registered and
drew. The Bot Swarm tab shows the matrix's own buttons, `Connect`,
`Disconnect` and `Disconnect All`, on both sides.

## The correction

`Registers in Electron` for this row reads `no` in
[08-tabs.md](../../manual/08-tabs.md) and in the issue body. No code changed,
for the reason the sibling reports give: a registered panel is a tab.

## The rerun

The same Electron run after the unit's other corrections reports the same
answer, and the three button words still appear in both variants.
