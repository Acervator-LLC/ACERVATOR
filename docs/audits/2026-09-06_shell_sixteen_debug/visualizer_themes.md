# `src/gui/visualizer/themes.py`

116 source lines. The table marked this row as registering a panel in the
Electron shell. The running shell says it does not.

## The error

```
Acervator panel not drawn: visualizer_themes: visualizer_themes.js registered no panel to draw
Panel visualizer_themes did not draw: visualizer_themes.js registered no panel to draw
```

`ok=False`, `registered=False`, `react=0`, `children=0`.

## Reproduction

The Electron run described in [README.md](README.md).

## The cause

`src/gui/web/visualizer_themes.js` never calls
`window.acervatorPanelHost.register`. It publishes
`acervatorSetVisualizerThemes`, `acervatorLoadVisualizerThemes` and
`acervatorVisualizerThemes` on the window.
`desktop/renderer/panel_host.js` faults any manifest name that never registers.

A colour table draws nothing of its own.
`src/gui/web/bot_visualizer.js` reads `global.acervatorVisualizerThemes`, and
the Bot Swarm tab shows the four theme names the table carries on both sides:
the Qt combo box lists `Nebula`, `Matrix`, `Quantum Circuit` and `Deep Ocean`,
and the React panel lists `nebula`, `matrix`, `quantum` and `ocean` beside the
same `Theme:` label, which are the keys and the display names of one table.

## The correction

`Registers in Electron` for this row reads `no` in
[08-tabs.md](../../manual/08-tabs.md) and in the issue body. No code changed.

## The rerun

The same Electron run after the unit's other corrections reports the same
answer, and every word of the Qt Bot Swarm tab is still carried by a model the
React side reads.
