# `src/gui/main_tabs/empty_tabs.py`

120 source lines. The row registers three panels, all three draw, and the two
variants show the same words.

## The error

None. Both runs are quoted below.

## Reproduction

The two runs described in [README.md](README.md).

## What each run printed

The Electron shell, three panels:

```
paper_trader_tab         : ok=True registered=True fiber=True react=5 markup=357
system_status_tab        : ok=True registered=True fiber=True react=5 markup=359
proof_of_accumulation_tab: ok=True registered=True fiber=True react=5 markup=377
```

with no fault on any of them, and these words:

```
Paper TraderThis tab is not built.Issue #19 carries the build-out.
System StatusThis tab is not built.Issue #34 carries the build-out.
Proof of AccumulationThis tab is not built.Issue #147 carries the build-out.
```

The Qt window, tabs 7, 8 and 9, each
`src.gui.main_tabs.empty_tabs.EmptyTabQtPanel`, built with no Python error:

```
Paper TraderThis tab is not built.Issue #19 carries the build-out.
System StatusThis tab is not built.Issue #34 carries the build-out.
Proof of AccumulationThis tab is not built.Issue #147 carries the build-out.
```

The two sides are identical, word for word, on all three tabs.

## The cause

Nothing to diagnose.

## The correction

None.

## The rerun

The Electron run after the unit's other corrections reports the same three
panels drawing the same words. The Qt window run with `PYTHONWARNINGS=error`
reports zero Python errors and identical text.
