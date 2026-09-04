"""Live-path fill simulation and slippage tolerance.

``fill_price`` moves a price against the trader by a half-normal draw scaled
by ``LIVE_SPREAD_PCT``. ``verify_hit`` samples it up to ``VERIFY_MAX_SAMPLES``
times and cancels once the drift between samples exceeds ``VERIFY_DRIFT_PCT``.
``classify_symbol`` and ``verify_min_profit`` read the per-class tolerance out
of ``VERIFY_MIN_PROFIT_BY_CLASS``.
"""

from __future__ import annotations

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
    ``intended_price`` is returned untouched.
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
    outranks ``symbol``, which outranks ``VERIFY_MIN_PROFIT``.
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
                drift = (prev - sample) / max(intended_price, 1e-9)
            else:
                drift = (sample - prev) / max(intended_price, 1e-9)
            if drift > VERIFY_DRIFT_PCT:
                return None, "canceled", i + 1
        prev = sample
    return None, "canceled", VERIFY_MAX_SAMPLES


_live_verify_hit = verify_hit
_live_fill_price = fill_price
