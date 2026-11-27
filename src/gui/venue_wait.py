"""``VenueWait`` runs one venue call off the window's thread and answers there inside ``VENUE_ASK_LIMIT_SEC``.

Settings' Test Connection and Add, the new-bot wizard's market list and the
pre-flight check each ask their venue through it.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import Future
from typing import Any, Callable

from PySide6.QtCore import QObject, QTimer

from ..exchange.ccxt_connector import CONNECT_LIMIT_SEC, SYNC_CALL_TIMEOUT_SEC

VENUE_ASK_LIMIT_SEC: float = CONNECT_LIMIT_SEC + SYNC_CALL_TIMEOUT_SEC
WAIT_LOOK_MS: int = 100

WAITING_FORMAT = "{doing}: waiting for {venue}, {waited} of {limit:g} s."
NO_ANSWER_FORMAT = "{venue} gave no answer in {limit:g}s"
ON_WAY_FORMAT = "{doing} is already on its way: it waits for {venue}."
WAIT_ENDED_FORMAT = "{doing} waited for {venue} and ended: {reason}."
WINDOW_CLOSED_ENDS_WAIT = "the window closed"


class VenueWait:
    """Runs ``call`` on its own thread; ``done`` or ``failed`` then runs on the window's thread."""

    def __init__(
        self,
        owner: QObject,
        venue: str,
        doing: str,
        call: Callable[[], Any],
        done: Callable[[Any], None],
        failed: Callable[[BaseException], None],
        tell: Callable[[str], None],
        limit_s: float = VENUE_ASK_LIMIT_SEC,
    ) -> None:
        self.venue = venue
        self.doing = doing
        self._call = call
        self._done = done
        self._failed = failed
        self._tell = tell
        self._limit_s = limit_s
        self._answer: "Future[Any]" = Future()
        self._began = 0.0
        self._told = -1
        self._ended = False
        self._timer = QTimer(owner)
        self._timer.setInterval(WAIT_LOOK_MS)
        self._timer.timeout.connect(self._look)

    @property
    def on_way(self) -> bool:
        """True from ``start`` until the answer lands, ``limit_s`` passes or ``end`` runs."""
        return self._began > 0.0 and not self._ended

    def start(self) -> None:
        """Run ``call`` on a daemon thread and look at it every ``WAIT_LOOK_MS``."""
        self._began = time.monotonic()
        threading.Thread(
            target=self._ask, name=f"venue-wait-{self.venue}", daemon=True
        ).start()
        self._timer.start()
        self._say(0)

    def end(self) -> None:
        """Stop waiting, so a later answer reaches neither ``done`` nor ``failed``."""
        self._ended = True
        self._timer.stop()

    def on_way_line(self) -> str:
        """``ON_WAY_FORMAT`` for this wait's ``doing`` and ``venue``."""
        return ON_WAY_FORMAT.format(doing=self.doing, venue=self.venue)

    def ended_line(self, reason: str) -> str:
        """``WAIT_ENDED_FORMAT`` for this wait, naming ``reason``."""
        return WAIT_ENDED_FORMAT.format(
            doing=self.doing, venue=self.venue, reason=reason
        )

    def _ask(self) -> None:
        try:
            self._answer.set_result(self._call())
        except Exception as exc:
            self._answer.set_exception(exc)

    def _say(self, waited: int) -> None:
        self._told = waited
        self._tell(
            WAITING_FORMAT.format(
                doing=self.doing, venue=self.venue, waited=waited, limit=self._limit_s
            )
        )

    def _look(self) -> None:
        if self._ended:
            self._timer.stop()
            return
        if self._answer.done():
            self.end()
            error = self._answer.exception()
            if error is None:
                self._done(self._answer.result())
            else:
                self._failed(error)
            return
        waited = time.monotonic() - self._began
        if waited >= self._limit_s:
            self.end()
            self._failed(
                TimeoutError(
                    NO_ANSWER_FORMAT.format(venue=self.venue, limit=self._limit_s)
                )
            )
            return
        if int(waited) != self._told:
            self._say(int(waited))
