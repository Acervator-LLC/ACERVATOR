# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""Target-balance growth for ``apply_profit_fold``.

``apply_profit_fold`` returns ``(new_target, spillover)``: ``target`` grown by
at most ``cap_pct`` percent of itself, with the remainder handed back as
``spillover`` for the caller to book as realised P/L. ``portfolio_value`` times
0.995 caps ``new_target`` only while that ceiling stays at or above ``target``.
No module in this repository imports ``apply_profit_fold``.
"""

from __future__ import annotations


def apply_profit_fold(
    profit: float,
    price: float,
    target: float,
    entry_price: float,
    portfolio_value: float,
    cap_pct: float = 1.0,
) -> tuple[float, float]:
    """Return ``(new_target, spillover)`` for one fold of ``profit`` at ``price``.

    An ``entry_price`` below ``price`` shrinks the growth in proportion, and a
    ``cap_pct`` of 0 grows ``target`` by nothing.
    """
    if profit <= 0 or price <= 0:
        return target, 0.0

    ref = price if entry_price <= 0 else min(price, entry_price)
    adjusted_profit = profit * (ref / price)

    cap_amount = target * (cap_pct / 100.0) if target > 0 and cap_pct > 0 else 0.0
    applied = min(adjusted_profit, cap_amount)
    spillover = adjusted_profit - applied
    if spillover < 0:
        spillover = 0.0

    new_target = target + applied
    if portfolio_value > 0 and new_target >= portfolio_value:
        new_target = portfolio_value * 0.995

    if new_target < target:
        new_target = target

    return new_target, spillover
