# `src/gui/main_tabs/trading_tab.py`

438 source lines. The row registers a panel, the panel draws, and the two
variants show the same values.

## The error

None. Both runs are quoted below.

## Reproduction

The two runs described in [README.md](README.md).

## What each run printed

The Electron shell:

```
trading_tab: ok=True late=False registered=True fiber=True react=184
             children=1 markup=22179 fault=None
```

The first 220 characters it drew:

```
Get Started＋ Add Crypto ExchangeNo Crypto Exchanges Configured＋ Add Crypto
ExchangeAdd a Crypto exchange to begin tradingGet Started＋ Add Stock Exchange
No Stock Exchanges Configured＋ Add Stock ExchangeAdd a Stock exchang
```

The Qt window: the Trading tab shows 46 words, beginning:

```
API Interaction LogActivity LogIndicator Voting PanelBot:TF Lock:BTC —   ETH —
(currency rates pending)No active timeframe locksNo Stock Exchanges Configured
Add a Stock exchange to begin tradingNo Crypto Exchanges Configured…
```

All 46 are carried by the models the React side reads. Two of them,
`⏸  Pause API Log` and `⏸  Pause Console`, first read as absent; that was the
comparison escaping the pause character, and `trading.tab` carries both under
`pause_button.text`.

## The cause

Nothing to diagnose.

## The correction

None to this file.

## The rerun

The Electron run after the unit's other corrections reports the same values.
The Qt window run with `PYTHONWARNINGS=error` reports zero Python errors and
identical text.

## One thing worth recording

Under `ACERVATOR_VARIANT=react` the PySide6 window still builds the Qt Trading
tab; the React trading tab is what the Electron shell draws. The two hosts do
not agree about which Trading tab they build, and only the Electron shell is
the shipping surface for this conversion.
