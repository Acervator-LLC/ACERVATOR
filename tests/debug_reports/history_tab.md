# `src/gui/history_tab.py`

837 source lines. The row registers a panel, the panel draws, and the two
variants show the same values. One defect was found on the way and corrected.

## The error

No traceback. The error is a value the two screens cannot keep in step.

The Qt History tab showed, above the table:

```
Bot manager unavailable — cannot fetch history.
```

That sentence is declared once, in `src/exchange/history_read_contract.py`:

```python
STATUS_TEXT = {
    "idle": "No history loaded yet — click Refresh.",
    "no_bot_manager": "Bot manager unavailable — cannot fetch history.",
    "no_async_loop": "Async loop not ready — try again after platform starts.",
    "fetching": "Fetching trade history from exchanges…",
    "timeout": "Fetch timeout (60s). Exchange may be rate-limited; try again.",
}
```

A search of the whole tree for `STATUS_TEXT` and for `no_bot_manager` returned
the definition and nothing else. The dictionary had no reader. The Qt tab wrote
the same five sentences as literals of its own, and
`src/gui/main_tabs/history_tab_surface.py` read the dictionary, so the React
screen followed the contract and the Qt screen did not.

## Reproduction

The Qt run described in [README.md](README.md), and this, which changes the
contract and reads the label off the built widget:

```python
hrc.STATUS_TEXT["no_bot_manager"] = "PLANTED no bot manager line"
tab = HistoryTab()
tab.set_bot_manager(None)
tab._kick_async_fetch()
tab._summary.text()
```

Before the correction:

```
idle summary  : 'No history loaded yet — click Refresh.'
after refresh : 'Bot manager unavailable — cannot fetch history.'
follows the contract: False
```

## The cause

Nothing raised, so `pdb` has no traceback to post-mortem here. The evidence is
the label read off the built widget, quoted above and below.

`src/gui/history_tab.py` imports `history_read_contract as hrc` and uses
`hrc.PAGE_LABEL_IDLE` and `hrc.page_label`, but typed the five status
sentences again as literals at the summary label and in `_kick_async_fetch`
and its poll timer. A change to `STATUS_TEXT` reached the React screen through
`history_tab_surface.status_text` and never reached the Qt screen.

## The correction

The five literals now read the contract:

```python
self._summary = QLabel(hrc.STATUS_TEXT["idle"])
...
self._set_status(hrc.STATUS_TEXT["no_bot_manager"])
self._set_status(hrc.STATUS_TEXT["no_async_loop"])
self._set_status(hrc.STATUS_TEXT["fetching"])
self._set_status(hrc.STATUS_TEXT["timeout"])
```

This is the cause and not a symptom: the two screens now take those sentences
from one place, so no edit can move one without the other.

## The rerun

The same commands, after:

```
idle summary  : 'PLANTED idle line'
after refresh : 'PLANTED no bot manager line'
follows the contract: True
```

The Qt window was built again with `PYTHONWARNINGS=error`. Zero Python errors,
and every tab's text is byte for byte what it was before the change.

The Electron panel drew with `ok=True`, `fault=None` and 2,011 characters of
markup:

```
FiltersFrom:To:Exchange:(all)Symbol:(all)Side:(all)BUYSELLApplyResetRefresh
0 of 0 trades shown · BUYs: 0 ($0.00) · SELLs: 0 ($0.00) · no fetch yet
◀ PrevNo matchesNext ▶Export CSV…
```

All 19 words the Qt tab shows are carried by the model the React panel reads.
Asked for each status key in turn, `history_tab.chrome` answers each of the
five sentences, so both screens can now show all five.
