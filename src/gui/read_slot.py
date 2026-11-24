"""``ReadSlot`` keeps one kind of venue read to one on its way and one waiting."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any, Optional

from ..exchange.ccxt_connector import (
    CCXT_TIMEOUT_HEADROOM_SEC,
    READ_TURN_WAIT_SEC,
    SYNC_CALL_TIMEOUT_SEC,
)

logger = logging.getLogger("acervator.gui")

#: Longest one venue call takes: its turn, its run and the hand-off of its answer.
VENUE_CALL_SEC: float = (
    READ_TURN_WAIT_SEC + SYNC_CALL_TIMEOUT_SEC + CCXT_TIMEOUT_HEADROOM_SEC
)

Read = Coroutine[Any, Any, Any]


@dataclass
class ReadAsk:
    """One ``read`` of ``calls`` venue calls, at ``venue`` where it asks one alone."""

    read: Read
    calls: int
    venue: str = ""

    @property
    def limit_sec(self) -> float:
        """The longest ``read`` takes, one ``VENUE_CALL_SEC`` for each of ``calls``."""
        return self.calls * VENUE_CALL_SEC


class ReadSlot:
    """The read of one kind on its way, and the newest asked for meanwhile."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._waiting: Optional[ReadAsk] = None
        self._on_way: Optional[ReadAsk] = None
        self._serving = False
        self._server: Optional[Future[Any]] = None

    def ask(
        self, ask: ReadAsk, schedule: Callable[[Read], Optional[Future[Any]]]
    ) -> None:
        """Make ``ask`` the waiting one, and ``schedule`` ``_serve`` where no read is
        on its way."""
        self._close_waiting()
        self._waiting = ask
        if self._serving:
            return
        self._serving = True
        server = self._serve()
        try:
            self._server = schedule(server)
        except Exception:
            server.close()
            self._serving = False
            self._close_waiting()
            raise

    def may_ask(self, venue: str) -> bool:
        """Whether the read on its way, or the one that starts next, may ask ``venue``."""
        ask = self._on_way or self._waiting
        return ask is not None and ask.venue in ("", venue)

    def end(self) -> None:
        """Close the waiting read and cancel ``_server`` with the one on its way."""
        self._close_waiting()
        if self._server is not None:
            self._server.cancel()

    def _close_waiting(self) -> None:
        """Close the read of ``_waiting``, which has not started."""
        if self._waiting is not None:
            self._waiting.read.close()
            self._waiting = None

    async def _serve(self) -> None:
        """Run ``_waiting`` to its end, again while another has taken its place."""
        try:
            while self._waiting is not None:
                self._on_way, self._waiting = self._waiting, None
                await self._answer(self._on_way)
        finally:
            self._on_way = None
            self._serving = False
            self._close_waiting()

    async def _answer(self, ask: ReadAsk) -> None:
        """Wait for the read of ``ask``, and end it once its ``limit_sec`` has passed."""
        task = asyncio.ensure_future(ask.read)
        try:
            await asyncio.wait({task}, timeout=ask.limit_sec)
            if not task.done():
                logger.warning(
                    "window read %s gave no answer in %.1fs and was ended",
                    self.name,
                    ask.limit_sec,
                )
                task.cancel()
                await asyncio.wait({task}, timeout=CCXT_TIMEOUT_HEADROOM_SEC)
        finally:
            task.cancel()
        if task.done() and not task.cancelled() and task.exception() is not None:
            logger.debug("window read %s raised: %r", self.name, task.exception())
