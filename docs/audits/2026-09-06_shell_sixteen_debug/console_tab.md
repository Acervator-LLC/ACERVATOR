# `src/gui/main_tabs/console_tab.py`

81 source lines. The row registers a panel, the panel draws, and the two
variants show the same values.

## The error

None. Both runs are quoted below.

## Reproduction

The two runs described in [README.md](README.md).

## What each run printed

The Electron shell:

```
console_tab: ok=True late=False registered=True fiber=True react=35
             children=1 markup=4831 fault=None
```

```
⏸  PauseClear  SIGNALS — name · expected · actual
```

The Qt window: the Console tab is `src.gui.qt_console_tab.ConsoleQtTab`, built
with no Python error, showing the same three words in a different order:

```
  SIGNALS — name · expected · actual⏸  PauseClear
```

All three are carried by the models the React side reads.

## The cause

Nothing to diagnose.

## The correction

None to this file.

## The rerun

The Electron run after the unit's other corrections reports the same values.
The Qt window run with `PYTHONWARNINGS=error` reports zero Python errors and
identical text.
