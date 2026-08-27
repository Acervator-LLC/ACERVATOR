"""
fmt.py — Formatting utilities
================================
Universal price and value formatting for dust-priced coins.
"""


def _adaptive_spec(value: float) -> str:
    """Return the format spec for a price magnitude: ,.2f / .4f / .6f / .8f.

    The single definition of the adaptive-precision ladder. Bands are on
    abs(value), so a negative price gets the precision of its magnitude.
    """
    av = abs(value)
    if av >= 1000:
        return ",.2f"
    elif av >= 1:
        return ".4f"
    elif av >= 0.01:
        return ".6f"
    else:
        return ".8f"


def fmt_price_raw(value: float) -> str:
    """Format a price without $ prefix (for log strings that add their own).

    Zero renders as "0.00". Sub-cent prices keep 8 decimals, so BONK at
    $0.00002 never truncates to 0.00.
    """
    if value == 0:
        return "0.00"
    return format(value, _adaptive_spec(value))


def fmt_price(value: float) -> str:
    """Format a price with a $ prefix and adaptive precision."""
    return "$" + fmt_price_raw(value)


def fmt_price_coerced(value) -> str:
    """Adaptive price format for values that may be None, "" or a string.

    Two contract differences from fmt_price_raw: the input passes through
    float(value or 0), and zero renders as "0" rather than "0.00".
    """
    v = float(value or 0)
    if v == 0:
        return "0"
    return format(v, _adaptive_spec(v))


def fmt_usd(value: float) -> str:
    """Format a USD dollar amount (investment, balance, P/L).
    Always 2 decimals since these are always in dollar terms."""
    return f"${value:,.2f}"


def fmt_pnl(value: float) -> str:
    """Format P/L with sign."""
    return f"${value:+,.4f}"
