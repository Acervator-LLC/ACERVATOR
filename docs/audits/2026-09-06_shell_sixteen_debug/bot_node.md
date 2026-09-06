# `src/gui/visualizer/bot_node.py`

455 source lines. The table marked this row as registering a panel in the
Electron shell. The running shell says it does not.

## The error

```
Acervator panel not drawn: bot_node: bot_node.js registered no panel to draw
Panel bot_node did not draw: bot_node.js registered no panel to draw
```

`ok=False`, `registered=False`, `react=0`, `children=0`.

## Reproduction

The Electron run described in [README.md](README.md). `bot_node` is one of the
74 names the manifest carries and is not one of the 13 the host registered.

## The cause

`src/gui/web/bot_node.js` never calls `window.acervatorPanelHost.register`. It
publishes `acervatorSetBotNode`, `acervatorLoadBotNode` and `acervatorBotNode`
on the window. `desktop/renderer/panel_host.js` faults any manifest name that
never registers.

A bot node is a card inside the swarm view, not a screen.
`src/gui/web/bot_visualizer.js` reads `global.acervatorBotNode` at line 1281,
and `bot_visualizer` registered and drew with 172 React calls and 22,626
characters of markup.

## The correction

`Registers in Electron` for this row reads `no` in
[08-tabs.md](../../manual/08-tabs.md) and in the issue body. No code changed:
a card that registered itself as a panel would gain a tab of its own, because
`acervatorPanelHost.screens` is what the tab bar draws from.

## The rerun

The same Electron run after the unit's other corrections reports the same
answer, and `bot_visualizer` still draws. Under Qt the Bot Swarm tab built with
no Python error and every word it shows is carried by a model the React side
reads.
