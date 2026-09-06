# `src/gui/simulator_tab/simulator_tab.py`

947 source lines. The row registers a panel, the panel draws, and the two
variants show the same values.

## The error

None. Both runs are quoted below.

## Reproduction

The two runs described in [README.md](README.md).

## What each run printed

The Electron shell:

```
simulator_tab: ok=True late=False registered=True fiber=True react=261
               children=1 markup=39081 fault=None
```

The first 200 characters it drew:

```
Mode:ValidationLooping Back TestNuclearActive simulator bots:All botsFleet
Replay — sim the live fleet against YTD dataLoads every live bot config from
bot_state.json and runs isolated ScrummingBot instances against a fa
```

The Qt window: the Simulator tab is
`src.gui.simulator_tab.simulator_tab.SimulatorTab`, built with no Python error
and showing 143 words — the widest screen in the window. Every one of the 143
is carried by a model the React side reads.

Fourteen of them first read as absent. Every one was the comparison and not the
product: `⤢ Expand`, `● Bot ID` and the other column toggles were lost to the
escaping of non-ASCII characters, and the Nuclear Mode empty-fleet note was
lost to the escaping of its newlines. `nuclear_mode_panel.state` carries that
note whole.

## The cause

Nothing to diagnose in this file.

## The correction

None to this file. One correction landed in a panel this tab composes:
`src/gui/simulator_tab/nuclear_mode_panel.py` held its own copy of the
empty-fleet note, four lines long, identical to
`nuclear_mode_panel_surface.EMPTY_FLEET_TEXT`. The panel now reads the surface:

```python
            self._set_empty_notice(surface.EMPTY_FLEET_TEXT, True)
```

## The rerun

The Electron run after the corrections reports the same values. The Qt window
run with `PYTHONWARNINGS=error` reports zero Python errors, and the Simulator
tab's 143 words are byte for byte what they were before the change — which is
what a change from a literal to the identical constant must produce.
