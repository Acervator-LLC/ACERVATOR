# `src/gui/main_tabs/header_strip.py`

127 source lines. The row registers a chrome panel, the panel draws, and the
five cards this file owns carry the same values on both sides.

## The error

None in this file. One value on the strip differs between the two runs and it
belongs to another row; it is recorded below.

## Reproduction

The two runs described in [README.md](README.md). The Qt side reads
`MainWindow._header_strip_container`, which is what `_build_header_strip`
assembles.

## What each run printed

The Electron shell:

```
header_strip: ok=True late=False registered=True fiber=True react=100
              children=1 markup=15029 fault=None
```

```
SPENDABLE—●|REALISED—●|LOCKED—●|MATURE—●|EXCH0●Scrummed$0.00●Folded$0.00●
Trades0●Bots0●Errors0●Crypto ModeP/L$+0.0000
```

The Qt strip:

```
SPENDABLE—|REALISED—|LOCKED—|MATURE—|EXCH—Scrummed$0.00Folded$0.00Trades0
Bots0Errors0●●●●●●●●●●Crypto Mode
```

The five counter cards this file builds agree exactly: `Scrummed $0.00`,
`Folded $0.00`, `Trades 0`, `Bots 0`, `Errors 0`.

`P/L $+0.0000` appears in the React text and not in the Qt text. It is not on
either screen. `header_strip.py` builds the card and calls
`setVisible(False)`; `header_strip_surface.HIDDEN_CARD` carries
`"visible": False`; and `src/gui/web/header_strip.js` sets the element's
`hidden` attribute from that field. A page's text content includes hidden
elements, so the reading is a limit of the instrument, not a difference on
screen.

## The cause

Nothing to diagnose in this file.

## The value that differs, and whose it is

`EXCH` reads `—` under Qt and `0` under React. The five KPI cards are built by
`_spendable_profits_class()`, which is `src/gui/widgets/spendable_profits.py`,
not this row. `—` is that widget's starting text and the window's dashboard
tick had not yet run in a one-shot build; the bridge computed the count of
configured exchanges, which is zero, and
`header_strip_surface.exchange_count_text(0)` renders `0`. The difference is
the first paint, and it belongs to the spendable-profits row.

## The correction

None.

## The rerun

The Electron run after the unit's other corrections reports the same values.
The Qt window run with `PYTHONWARNINGS=error` reports zero Python errors and
identical text.
