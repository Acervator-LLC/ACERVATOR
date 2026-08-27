"""Pure formatter for the Target-BTC and Target-ETH denomination rows.

Module scope so it is unit-testable without a QApplication; the widget
helper on the Settings tab delegates here.
"""

from __future__ import annotations

from .. import design_system as ds


def _compose_denom_row_text(
    quote_currency: str,
    target_usd: float,
    quote_usd: float,
    pair_pct_24h: float,
    usd_pair_pct_24h: float,
) -> tuple[str, str]:
    """Return ``(text, color_hex)`` for one denomination row.

    ``quote_usd`` is the USD price of one unit of the quote currency
    (e.g., BTC/USD or ETH/USD from CurrencyRateMonitor). Returns a
    "pending…" grey row when the quote-USD rate is not yet available.
    Colours: green (`#00ff88`) for divergence > +0.1 %, red
    (`#ff3366`) for < -0.1 %, grey (`#a8a8c5`) otherwise.
    """
    if quote_usd <= 0:
        return ("pending…", ds.TEXT_MED)
    _units = target_usd / quote_usd
    _delta = pair_pct_24h - usd_pair_pct_24h
    if abs(_delta) < 0.1:
        _color = ds.TEXT_MED
        _sign = ""
    elif _delta > 0:
        _color = ds.SUCCESS
        _sign = "+"
    else:
        _color = ds.ERROR
        _sign = ""
    if _units >= 1:
        _units_txt = f"{_units:.4f}"
    elif _units >= 0.01:
        _units_txt = f"{_units:.5f}"
    else:
        _units_txt = f"{_units:.6f}"
    _txt = f"{_units_txt} {quote_currency}  " f"(Δ24h vs USD: {_sign}{_delta:.2f} %)"
    return (_txt, _color)
