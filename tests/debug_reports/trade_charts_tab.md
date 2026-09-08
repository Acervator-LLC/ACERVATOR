# `src/gui/widgets/trade_charts_tab.py`

521 source lines. The row registers a panel and the panel draws. Neither side
drew a word, so nothing was compared.

## The error

No traceback, and no words either.

The Electron shell:

```
trade_charts_tab: ok=True late=False registered=True fiber=True react=7
                  children=1 markup=692 fault=None text=''
```

The Qt window, tab 3, `src.gui.widgets.trade_charts_tab.TradeChartsTab`, built
with no Python error and showing zero words. Built on its own, the widget
carries a `QScrollArea` over an empty inner `QWidget` and nothing that holds
text:

```
['QVBoxLayout', 'QScrollArea', 'QWidget', 'QWidget', 'QVBoxLayout',
 'QWidget', 'QScrollBar', 'QBoxLayout', 'QWidget', 'QScrollBar', 'QBoxLayout']
```

## Reproduction

The two runs described in [README.md](README.md), plus a direct construction of
`TradeChartsTab` under the same throwaway home.

## The cause

No exchange is configured under a throwaway home, so the tab has no asset to
chart and both sides draw an empty frame. This is what the screen does in an
empty state, not a defect found.

## The correction

None. The screen has nothing to correct until it has an asset to draw.

## The rerun

The Electron run after the unit's other corrections reports the same values:
`ok=True`, `fault=None`, 692 characters of markup, no text. The Qt window run
with `PYTHONWARNINGS=error` reports zero Python errors and zero words.

## Why this row is not confirmed

Two empty screens agree with each other whatever either of them would draw with
data. The comparison has nothing in it, so it cannot report a difference, and a
result that cannot report is not evidence. This row needs a run with at least
one configured exchange before the two sides can be said to agree.
