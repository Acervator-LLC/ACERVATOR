"""``FillHistory`` holds every ``Trade`` the exchange has for one symbol.

``FillHistory.refresh`` pages ``get_my_trades`` newest to oldest with ``until``
until a page is short or reaches a fill already held, so a second call fetches
one page. ``ReconciliationEngineMixin.refresh_exchange_position_health`` feeds
``FillHistory.trades`` to ``compute_position_health``.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .base import Trade

logger = logging.getLogger("acervator.exchange.fill_history")

FILL_PAGE_LIMIT = 500
"""``limit`` of every ``get_my_trades`` call ``FillHistory.refresh`` makes."""

FILL_PAGE_OVERLAP_S = 60.0
"""Seconds an older page's ``until`` sits above the previous page's oldest fill."""

FILL_PAGE_MAX = 200
"""Pages one ``FillHistory.refresh`` walks before it stops with ``complete`` False."""


def fill_key(trade: Trade) -> Any:
    """``trade.id``, or the (timestamp, side, amount, price) tuple when the id is empty."""
    if trade.id:
        return trade.id
    return (trade.timestamp, trade.side, trade.amount, trade.price)


class FillHistory:
    """Every ``Trade`` for ``symbol`` in ``trades``, oldest first.

    ``complete`` is False until a ``refresh`` walk ends on a short page, and
    False again when a walk stops on ``FILL_PAGE_MAX`` or adds nothing.
    """

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.trades: list[Trade] = []
        self.complete = False
        self.pages_last_refresh = 0
        self._keys: set = set()

    async def _page(self, exchange: Any, until_s: Optional[float]) -> Optional[list]:
        """One ``get_my_trades`` call; None when the exchange answers None or refuses ``params``."""
        if until_s is None:
            return await exchange.get_my_trades(self.symbol, limit=FILL_PAGE_LIMIT)
        try:
            return await exchange.get_my_trades(
                self.symbol,
                limit=FILL_PAGE_LIMIT,
                params={"until": int(until_s * 1000)},
            )
        except TypeError:
            logger.warning(
                "FillHistory %s: %s takes no params, history stops at %d fills",
                self.symbol,
                type(exchange).__name__,
                len(self.trades),
            )
            return None

    async def refresh(self, exchange: Any) -> Optional[list[Trade]]:
        """Merge every fill the exchange holds beyond ``trades``; None when the first page is None."""
        known = set(self._keys)
        until_s: Optional[float] = None
        pages = 0
        ended_short = False
        joined = False
        while pages < FILL_PAGE_MAX:
            page = await self._page(exchange, until_s)
            if page is None:
                if pages == 0:
                    return None
                break
            pages += 1
            fills = [t for t in page if isinstance(t, Trade)]
            added = 0
            for t in fills:
                key = fill_key(t)
                if key in known:
                    joined = True
                if key in self._keys:
                    continue
                self._keys.add(key)
                self.trades.append(t)
                added += 1
            if len(fills) < FILL_PAGE_LIMIT:
                ended_short = True
                break
            if joined:
                break
            if added == 0:
                logger.warning(
                    "FillHistory %s: page %d added no fill, history stops at %d fills",
                    self.symbol,
                    pages,
                    len(self.trades),
                )
                break
            until_s = min(t.timestamp for t in fills) + FILL_PAGE_OVERLAP_S
        self.pages_last_refresh = pages
        if ended_short:
            self.complete = True
        elif not joined:
            self.complete = False
        self.trades.sort(key=lambda t: (t.timestamp, t.id))
        if not self.complete:
            logger.warning(
                "FillHistory %s: %d fills after %d pages, history incomplete",
                self.symbol,
                len(self.trades),
                pages,
            )
        return self.trades
