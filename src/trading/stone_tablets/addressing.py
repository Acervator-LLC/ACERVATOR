"""addressing.py — stable per-candle addresses for Stone Tablets.

Operator directive 2026-08-02:

    "Another piece we can add to more tightly tie the YTD trade
    actions to their respective Stone Tablets would be by counting
    the candles and assigning unique numbered addresses
    (candle_no_ticker) to them which are then associated with
    historical trade actions and should trigger the same validating
    logic in the sim."

WHY
===
Parity matching currently compares sim trades to live trades by
timestamp with a ±300s tolerance (see parity_harness). Tolerance
windows are fuzzy: two trades 4 minutes apart on the same symbol
"match" even if they were triggered by different candles, and a
trade that fires 6 minutes late does not match at all even though
it was the same decision.

A candle address removes the fuzz. Every candle in a tablet has an
index; a trade is tagged with the index of the candle it fired
within. Parity then asks an exact question:

    at ``1234_BTC``, live fired BUY — did the sim gate arm at
    ``1234_BTC``?

Address format is ``<index>_<TICKER>`` per the operator's
``candle_no_ticker`` shorthand. The index is zero-padded to 6
digits so lexical sort equals chronological sort (tablets run to
~61k candles; 6 digits covers 999,999).

    candle 0     of BTC  -> "000000_BTC"
    candle 1234  of BTC  -> "001234_BTC"
    candle 45598 of BTC  -> "045598_BTC"

INDEX SEMANTICS — IMPORTANT
===========================
The index is the position within THAT TABLET'S full candle list,
counted from its first candle (index 0). It is NOT a global clock
tick and NOT an offset from a shared epoch.

Consequence: the same index on two different tickers is NOT the
same moment in time, because tablets begin at different listing
dates (verified 2026-08-02: BTC starts 2026-01-01, CAP starts
2026-06-26). Address equality is only meaningful WITHIN one
ticker. Cross-ticker time alignment is the master clock's job,
not addressing's.

This is deliberate: an address must stay stable for a given candle
even when other tablets are backfilled or extended. Anchoring to a
shared epoch would renumber every asset whenever any one of them
gained earlier history.

STABILITY CONTRACT
==================
An address is stable as long as the tablet is only APPENDED to.
Stone Tablets are immutable + append-only by directive, so this
holds. If a tablet were ever back-filled with candles EARLIER than
its current first candle, every address for that ticker would
shift. ``verify_addressing_stable()`` exists to detect that.

sadp: R28 SSS + R70 RCN
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("acervator.stone_tablets.addressing")

INDEX_WIDTH: int = 6
"""Zero-pad width. 6 digits => lexical sort == chronological sort
for tablets up to 999,999 candles (current max ~61k)."""

_ADDRESS_RE = re.compile(r"^(?P<index>\d+)_(?P<ticker>[A-Z0-9.\-]+)$")


@dataclass(frozen=True)
class CandleAddress:
    """A parsed candle address.

    ``ticker`` is the BASE asset (BTC), not the pair (BTC/USD) — a
    tablet is keyed by base asset + exchange, so the pair's quote
    is not part of the address.
    """

    index: int
    ticker: str

    def __str__(self) -> str:
        return format_address(self.ticker, self.index)

    @property
    def text(self) -> str:
        return str(self)


def format_address(ticker: str, index: int) -> str:
    """Build ``<zero-padded index>_<TICKER>``.

    Raises ValueError on a negative index — a negative address would
    silently sort before every real candle and corrupt comparisons.
    """
    idx = int(index)
    if idx < 0:
        raise ValueError(f"candle index must be >= 0, got {idx}")
    t = str(ticker or "").upper().strip()
    if not t:
        raise ValueError("ticker must be non-empty")
    return f"{idx:0{INDEX_WIDTH}d}_{t}"


def parse_address(address: str) -> Optional[CandleAddress]:
    """Inverse of format_address. Returns None when the string is
    not a valid address (callers treat None as 'unaddressed')."""
    m = _ADDRESS_RE.match(str(address or "").strip())
    if m is None:
        return None
    return CandleAddress(index=int(m.group("index")), ticker=m.group("ticker"))


def ticker_from_symbol(symbol: str) -> str:
    """``BTC/USD`` -> ``BTC``. Passes through a bare base asset."""
    s = str(symbol or "").strip().upper()
    return s.split("/", 1)[0] if "/" in s else s


def index_for_ts(rows: list, ts_ms: int) -> Optional[int]:
    """Index of the candle whose window CONTAINS ts_ms.

    Semantics: returns the rightmost candle whose open timestamp is
    <= ts_ms. A trade that fires at any moment inside a 5-minute
    candle therefore maps to that candle — which is the behaviour
    parity needs, since the gate decision that caused the trade was
    evaluated on that candle.

    Returns None when ts_ms precedes the tablet's first candle (the
    asset was not yet listed) or rows is empty. Callers must treat
    None as 'no address' rather than defaulting to 0, otherwise
    every pre-listing trade would collide on candle 0.

    O(log n) bisect — safe on 61k-candle tablets.
    """
    if not rows:
        return None
    target = int(ts_ms)
    if target < int(rows[0][0]):
        return None
    lo, hi = 0, len(rows) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if int(rows[mid][0]) <= target:
            lo = mid
        else:
            hi = mid - 1
    return lo


def address_for_ts(
    ticker: str,
    rows: list,
    ts_ms: int,
) -> Optional[str]:
    """Convenience: resolve a timestamp straight to an address
    string, or None when the timestamp precedes the tablet."""
    idx = index_for_ts(rows, ts_ms)
    if idx is None:
        return None
    return format_address(ticker_from_symbol(ticker), idx)


def ts_for_index(rows: list, index: int) -> Optional[int]:
    """Open timestamp (ms) of the candle at ``index``, or None when
    the index is out of range."""
    if not rows:
        return None
    i = int(index)
    if i < 0 or i >= len(rows):
        return None
    return int(rows[i][0])


def verify_addressing_stable(
    rows: list,
    expected_first_ts_ms: int,
) -> bool:
    """True when the tablet still begins at the timestamp addresses
    were assigned against.

    Stone Tablets are append-only by directive, so this should
    always hold. It returns False if a tablet ever gained candles
    EARLIER than its previous first candle — which would silently
    shift every address for that ticker and invalidate any stored
    trade->address mapping. Call this before trusting persisted
    addresses across sessions.
    """
    if not rows:
        return False
    return int(rows[0][0]) == int(expected_first_ts_ms)


__all__ = [
    "INDEX_WIDTH",
    "CandleAddress",
    "address_for_ts",
    "format_address",
    "index_for_ts",
    "parse_address",
    "ticker_from_symbol",
    "ts_for_index",
    "verify_addressing_stable",
]
