"""Fill modelling and slippage tolerance; no live order is priced here.

``fill_price`` moves a price against the trader by a half-normal draw scaled
by ``LIVE_SPREAD_PCT``, and no live order carries its answer as a limit price.
``verify_hit`` samples it up to ``VERIFY_MAX_SAMPLES`` times and cancels once
the drift between samples exceeds ``VERIFY_DRIFT_PCT``. ``classify_symbol``
and ``verify_min_profit`` read the per-class tolerance out of
``VERIFY_MIN_PROFIT_BY_CLASS``.

At the shipped constants no sample can fail, so nothing past the first sample
runs. ``random.gauss`` is bounded at 8.5717 standard deviations, because the
smallest value ``1.0 - random()`` reaches is 2**-53, and a draw scaled by
``LIVE_SPREAD_PCT`` therefore reaches 0.6857% of price at most. The smallest
entry in ``VERIFY_MIN_PROFIT_BY_CLASS`` is 1%. The first sample clears every
class, so "adjusted", the drift test and "canceled" need a ``spread`` or a
``min_profit`` the caller supplies, or a slippage read from the venue.

``book_spread_pct`` and ``verify_book_spread`` take that venue reading: the
bid-ask gap off the venue's own book, judged against the same per-class
tolerance. The live sell and buy paths call those two; ``verify_hit`` and
``fill_price`` stay for the Simulator.
"""

from __future__ import annotations

import math
import random
from typing import Optional, Tuple

# VERIFY_DRIFT_PCT and LIVE_SPREAD_PCT are fractions of price, not percents.
VERIFY_HIT_ENABLED: bool = True
VERIFY_MAX_SAMPLES: int = 5
VERIFY_DRIFT_PCT: float = 0.005
LIVE_SPREAD_PCT: float = 0.0008

VERIFY_MIN_PROFIT_BY_CLASS = {
    "crypto": 0.04,
    "meme": 0.04,
    "equity": 0.02,
    "bond": 0.01,
    "etf": 0.015,
    "default": 0.02,
}
VERIFY_MIN_PROFIT: float = VERIFY_MIN_PROFIT_BY_CLASS["default"]

_CRYPTO = {
    "BTC",
    "ETH",
    "SOL",
    "XRP",
    "BNB",
    "ADA",
    "DOGE",
    "TRX",
    "AVAX",
    "DOT",
    "COIN",
    "LINK",
    "MATIC",
    "ATOM",
}
_BOND = {"TLT", "IEF", "TIP", "AGG", "BND"}
_ETF_IDX = {"SPY", "QQQ", "IWM", "GLD", "SLV", "USO", "VNQ", "XLU", "MCHI"}
_MEME = {
    "GME",
    "AMC",
    "BBBY",
    "KOSS",
    "EXPR",
    "SNDL",
    "PTON",
    "ZM",
    "TDOC",
    "ROKU",
    "CVNA",
    "DKNG",
    "OPEN",
    "UWMC",
    "IPOF",
    "CCIV",
    "ARKK",
    "ARKG",
    "ARKW",
    "ARKF",
    "PRNT",
    "NIO",
}


def classify_symbol(symbol: str) -> str:
    """Return the class of ``symbol``: crypto, bond, etf, meme or equity.

    An empty ``symbol`` returns "default"; anything after a "/" or "-" quote
    separator is dropped before the sets are searched.
    """
    if not symbol:
        return "default"
    s = symbol.upper().strip()
    for sep in ("/", "-"):
        if sep in s:
            s = s.split(sep)[0]
    if s in _CRYPTO:
        return "crypto"
    if s in _BOND:
        return "bond"
    if s in _ETF_IDX:
        return "etf"
    if s in _MEME:
        return "meme"
    return "equity"


def verify_min_profit(symbol: str | None = None) -> float:
    """Return the tolerance for ``symbol`` from ``VERIFY_MIN_PROFIT_BY_CLASS``.

    A ``symbol`` of None, or a class missing from the table, resolves to the
    "default" entry.
    """
    if symbol is None:
        return VERIFY_MIN_PROFIT_BY_CLASS["default"]
    cls = classify_symbol(symbol)
    return VERIFY_MIN_PROFIT_BY_CLASS.get(cls, VERIFY_MIN_PROFIT_BY_CLASS["default"])


def fill_price(
    intended_price: float, side: str, spread: float = LIVE_SPREAD_PCT
) -> float:
    """Move ``intended_price`` against the trader by a half-normal draw.

    A ``side`` of "sell" fills below ``intended_price`` and every other side
    above it, with mean displacement ``spread`` * sqrt(2/pi); a non-positive
    ``intended_price`` is returned untouched, and no live order carries the
    returned figure as its limit price.
    """
    if intended_price <= 0:
        return intended_price
    slip = abs(random.gauss(0.0, spread))
    if side == "sell":
        return intended_price * (1.0 - slip)
    return intended_price * (1.0 + slip)


def verify_hit(
    intended_price: float,
    side: str,
    symbol: Optional[str] = None,
    spread: Optional[float] = None,
    min_profit: Optional[float] = None,
) -> Tuple[Optional[float], str, int]:
    """Draw ``fill_price`` repeatedly until one sample clears the tolerance.

    Returns ``(price, status, samples)``, where status is "clean", "adjusted"
    or "canceled" and a canceled price is None; an explicit ``min_profit``
    outranks ``symbol``, which outranks ``VERIFY_MIN_PROFIT``. At the shipped
    ``LIVE_SPREAD_PCT`` the first sample clears every per-class tolerance, so
    the answer is "clean" at one sample and the other two statuses need a
    ``spread`` or ``min_profit`` the caller supplies.
    """
    if spread is None:
        spread = LIVE_SPREAD_PCT
    if min_profit is None:
        if symbol is not None:
            min_profit = verify_min_profit(symbol)
        else:
            min_profit = VERIFY_MIN_PROFIT

    if not VERIFY_HIT_ENABLED:
        return fill_price(intended_price, side, spread), "clean", 1

    if side == "sell":
        floor = intended_price * (1.0 - min_profit)
    else:
        floor = intended_price * (1.0 + min_profit)

    prev = None
    for i in range(VERIFY_MAX_SAMPLES):
        sample = fill_price(intended_price, side, spread)
        ok = (sample >= floor) if side == "sell" else (sample <= floor)
        if ok:
            return sample, ("clean" if i == 0 else "adjusted"), i + 1
        if prev is not None:
            if side == "sell":
                drift_price = prev - sample
            else:
                drift_price = sample - prev
            if drift_price > intended_price * VERIFY_DRIFT_PCT:
                return None, "canceled", i + 1
        prev = sample
    return None, "canceled", VERIFY_MAX_SAMPLES


def book_spread_pct(best_bid: float, best_ask: float) -> Optional[float]:
    """Return the venue's bid-ask gap as a fraction of the mid price.

    A ``best_bid`` or ``best_ask`` that is not finite and positive, or a pair
    that crosses, returns None.
    """
    try:
        bid = float(best_bid)
        ask = float(best_ask)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(bid) and math.isfinite(ask)):
        return None
    if bid <= 0.0 or ask <= 0.0 or ask < bid:
        return None
    mid = (bid + ask) / 2.0
    return (ask - bid) / mid


def verify_book_spread(
    intended_price: float,
    spread_pct: Optional[float],
    symbol: Optional[str] = None,
    min_profit: Optional[float] = None,
) -> Tuple[Optional[float], str, Optional[float]]:
    """Judge ``spread_pct`` against the ``min_profit`` the asset class carries.

    Returns ``(price, status, spread_pct)``: "unread" with ``intended_price``
    when ``spread_pct`` is None, "clean" within ``VERIFY_DRIFT_PCT``,
    "adjusted" up to ``min_profit``, and "canceled" with a None price above it.
    """
    if min_profit is None:
        if symbol is not None:
            min_profit = verify_min_profit(symbol)
        else:
            min_profit = VERIFY_MIN_PROFIT
    if spread_pct is None:
        return intended_price, "unread", None
    if not VERIFY_HIT_ENABLED:
        return intended_price, "clean", spread_pct
    if spread_pct > min_profit:
        return None, "canceled", spread_pct
    if spread_pct > VERIFY_DRIFT_PCT:
        return intended_price, "adjusted", spread_pct
    return intended_price, "clean", spread_pct


_live_verify_hit = verify_hit
_live_fill_price = fill_price
