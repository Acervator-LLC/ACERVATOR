"""position_health.py — derive avg_entry / realized P/L from exchange trade history.

Operator directive 2026-05-10: *"Everything that is
available on the exchange and is related to position health should
not be getting calculated locally in some strange manner."*

This module aggregates exchange-pulled `Trade` records (from
`get_my_trades`) into the position-health values that bot stats and
the SpendableWidget previously approximated with internal
accumulators or ticker.last. The derivation matches Coinbase's
display semantic:

- **avg_entry**: running weighted-average buy price for the OPEN
  position. On BUY: new_avg = (old_qty × old_avg + buy_qty × buy_price)
  / new_qty. On SELL: qty reduces, avg stays. This matches what
  Coinbase shows in the "Crypto" position list under "Avg Entry".

- **realized_pnl**: FIFO-matched buy/sell pairs, summed
  (sell_price - buy_price) × matched_qty across all SELLs that
  closed against earlier BUYs. Aligns with Coinbase's Returns
  semantic for closed cycles.

These functions are pure — they take a list of Trade records and
return computed values. No exchange calls, no I/O. Easily testable.

Caching, refresh cadence, and integration into bot stats live
elsewhere (caller's responsibility).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Optional

from .base import Trade, OrderSide


@dataclass
class PositionHealth:
    """Derived position-health summary for one asset."""

    asset: str
    qty: float  # current position size (units)
    avg_entry: float  # weighted-avg cost basis for open position
    cost_basis_total_usd: float  # qty × avg_entry
    realized_pnl_usd: float  # cumulative realized P/L from closed cycles
    fees_paid_total: float  # cumulative fees in quote currency
    trade_count: int  # total trades counted (BUY + SELL)
    first_trade_ts: Optional[float] = None
    last_trade_ts: Optional[float] = None
    open_lot_basis_usd: float = 0.0  # sum of qty × price over the buys FIFO left open


def compute_position_health(
    trades: list, asset: Optional[str] = None
) -> PositionHealth:
    """Aggregate trade history into a single PositionHealth record.

    Args:
        trades: list of `Trade` records, ordered chronologically.
        asset: optional symbol filter — if provided, only trades whose
            symbol matches (e.g., "CHIP" matches "CHIP/USD") are
            considered. None = aggregate all trades.

    Returns:
        PositionHealth dataclass with derived values.
    """
    qty = 0.0
    avg_entry = 0.0
    realized = 0.0
    fees = 0.0
    count = 0
    first_ts: Optional[float] = None
    last_ts: Optional[float] = None

    # FIFO buy queue for realized-pnl matching
    buy_queue: deque = deque()  # entries: (qty_remaining, price)

    for t in trades:
        if not isinstance(t, Trade):
            continue
        if asset:
            sym_base = (t.symbol or "").split("/")[0]
            if sym_base != asset:
                continue
        if t.amount <= 0 or t.price <= 0:
            continue

        count += 1
        fees += float(t.fee or 0)
        if first_ts is None or (t.timestamp and t.timestamp < first_ts):
            first_ts = t.timestamp
        if last_ts is None or (t.timestamp and t.timestamp > last_ts):
            last_ts = t.timestamp

        if t.side == OrderSide.BUY:
            # Update running weighted-avg entry
            new_qty = qty + t.amount
            if new_qty > 0:
                avg_entry = (qty * avg_entry + t.amount * t.price) / new_qty
            qty = new_qty
            # Add to FIFO queue for realized-pnl matching
            buy_queue.append([t.amount, t.price])
        elif t.side == OrderSide.SELL:
            # Reduce qty; avg_entry unchanged (Coinbase semantic)
            qty -= t.amount
            if qty < 1e-12:
                qty = 0.0
                avg_entry = 0.0  # position closed; reset avg
            # FIFO-match to compute realized P/L
            sell_remaining = t.amount
            while sell_remaining > 1e-12 and buy_queue:
                buy_lot = buy_queue[0]
                take = min(buy_lot[0], sell_remaining)
                realized += (t.price - buy_lot[1]) * take
                buy_lot[0] -= take
                sell_remaining -= take
                if buy_lot[0] <= 1e-12:
                    buy_queue.popleft()

    return PositionHealth(
        asset=asset or "",
        qty=qty,
        avg_entry=avg_entry,
        cost_basis_total_usd=qty * avg_entry,
        realized_pnl_usd=realized,
        fees_paid_total=fees,
        trade_count=count,
        first_trade_ts=first_ts,
        last_trade_ts=last_ts,
        open_lot_basis_usd=sum(lot_qty * lot_price for lot_qty, lot_price in buy_queue),
    )


def compute_avg_entry(trades: list, asset: str) -> float:
    """Convenience: just the avg_entry value, or 0.0 if no position."""
    return compute_position_health(trades, asset).avg_entry


def compute_realized_pnl(trades: list, asset: str) -> float:
    """Convenience: just the realized P/L value (FIFO-matched)."""
    return compute_position_health(trades, asset).realized_pnl_usd
