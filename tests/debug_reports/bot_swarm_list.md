# `src/gui/bot_swarm_list.py`

351 source lines. The table marked this row as registering a panel in the
Electron shell. The running shell says it does not.

## The error

The shell's own panel host wrote the fault and printed it on the renderer's
console channel:

```
Acervator panel not drawn: bot_swarm_list: bot_swarm_list.js registered no panel to draw
```

The host element carried the same words:

```
Panel bot_swarm_list did not draw: bot_swarm_list.js registered no panel to draw
```

`ok=False`, `registered=False`, `react=0`, `children=0`.

## Reproduction

The Electron run described in [README.md](README.md). The shell reports 74
panel names and 13 registered panels; `bot_swarm_list` is not one of the 13.

## The cause

`src/gui/web/bot_swarm_list.js` never calls
`window.acervatorPanelHost.register`. It publishes
`acervatorSetBotSwarmList`, `acervatorLoadBotSwarmList` and
`acervatorSwarmList` on the window and nothing else.
`desktop/renderer/panel_host.js` answers `reasonFor` with
`"<name>.js registered no panel to draw"` for any manifest name that never
registers, so opening the module by name can only fault.

The module is not a screen. `src/gui/web/bot_swarm_tab.js` calls
`acervatorLoadBotSwarmList`, and `bot_swarm_tab` is one of the 13 that did
register and did draw — its panel carries the list's own column headers,
`Ticker`, `Inflow`, `Outflow`, `% Out`, `L1` to `L8`.

The module is converted and it reaches the screen. The mark is what is wrong:
this row draws inside another panel rather than registering one.

## The correction

`Registers in Electron` for this row reads `no` in
[08-tabs.md](../../manual/08-tabs.md) and in the issue body. No code changed:
registering a part of the Bot Swarm tab as a panel of its own would add a name
to `acervatorPanelHost.screens`, which is the list the tab bar draws tabs from.

## The rerun

The same Electron run after the unit's other corrections reports the same
thing, which is the expected answer for a module that is a part and not a
panel: `registered=False`, and `bot_swarm_tab` drawing with `ok=True`,
`fiber=True`, 42 React calls and 3,615 characters of markup.

Under Qt the Bot Swarm tab built with no Python error, and all 50 words it
shows are carried by the models the React side reads.
