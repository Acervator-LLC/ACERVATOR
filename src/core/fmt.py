"""
fmt.py — Formatting utilities
================================
Universal price and value formatting for dust-priced coins.
"""


def fmt_price(value: float) -> str:
    """Format a price with adaptive precision.

    Ensures dust-priced coins like BONK ($0.00002) are never truncated to $0.00.
    Always shows at least 8 significant digits for sub-cent prices.
    """
    if value == 0:
        return "$0.00"
    av = abs(value)
    if av >= 1000:
        return f"${value:,.2f}"
    elif av >= 1:
        return f"${value:.4f}"
    elif av >= 0.01:
        return f"${value:.6f}"
    else:
        return f"${value:.8f}"


def fmt_price_raw(value: float) -> str:
    """Format a price without $ prefix (for log strings that add their own)."""
    if value == 0:
        return "0.00"
    av = abs(value)
    if av >= 1000:
        return f"{value:,.2f}"
    elif av >= 1:
        return f"{value:.4f}"
    elif av >= 0.01:
        return f"{value:.6f}"
    else:
        return f"{value:.8f}"


def fmt_usd(value: float) -> str:
    """Format a USD dollar amount (investment, balance, P/L).
    Always 2 decimals since these are always in dollar terms."""
    return f"${value:,.2f}"


def fmt_pnl(value: float) -> str:
    """Format P/L with sign."""
    return f"${value:+,.4f}"
