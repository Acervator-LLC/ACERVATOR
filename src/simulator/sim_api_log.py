"""The Simulator's API Interaction Log: ``APIInteractionLog`` refusing by action.

``SimApiLog.record`` appends an entry whose ``action`` opens with a word in
``ALLOWED_ACTIONS`` and raises ``SendRefused`` for any other, before the entry,
the ``acervator.api`` line and the listeners. ``TABLET_ACTION`` opens every
Stone Tablet retrieval block and ``YTD_ACTION`` the Generate From YTD block;
``action_word`` reads the word ``record`` checks.
"""

from __future__ import annotations

import logging

from ..exchange.api_logger import APIInteractionLog
from .tablet_source import SendRefused

logger = logging.getLogger("acervator.simulator.api_log")

#: The word a Stone Tablet retrieval's action opens with; the tablet key follows.
TABLET_ACTION = "FETCH_TABLET"

#: The word the Generate From YTD read's action opens with.
YTD_ACTION = "FETCH_YTD"

#: Every action word ``SimApiLog.record`` accepts. Any other raises ``SendRefused``.
ALLOWED_ACTIONS = (TABLET_ACTION, YTD_ACTION)

REFUSED_FORMAT = (
    "SimApiLog refused action {action!r}: the Simulator's API log records "
    "{allowed} and nothing else."
)


def action_word(action: object) -> str:
    """The first whitespace-separated word of ``action``; ``""`` for a
    non-string or an empty action."""
    if not isinstance(action, str):
        return ""
    parts = action.split()
    return parts[0] if parts else ""


def action_allowed(action: object) -> bool:
    """Whether ``action_word(action)`` is in ``ALLOWED_ACTIONS``."""
    return action_word(action) in ALLOWED_ACTIONS


class SimApiLog(APIInteractionLog):
    """``APIInteractionLog`` whose ``record`` accepts ``ALLOWED_ACTIONS`` only."""

    def record(
        self,
        exchange: str,
        action: str,
        reason: str,
        endpoint: str = "",
        params: dict = None,
        result: str = "",
        elapsed_ms: float = 0.0,
        level: str = "info",
        data_usage: str = "",
    ) -> dict:
        """Append one entry as ``APIInteractionLog.record`` does when
        ``action_allowed(action)``; otherwise log one warning line and raise
        ``SendRefused`` with nothing appended, written or delivered."""
        if not action_allowed(action):
            message = REFUSED_FORMAT.format(action=action, allowed=ALLOWED_ACTIONS)
            logger.warning(message)
            raise SendRefused(message)
        return super().record(
            exchange,
            action,
            reason,
            endpoint=endpoint,
            params=params,
            result=result,
            elapsed_ms=elapsed_ms,
            level=level,
            data_usage=data_usage,
        )


__all__ = [
    "ALLOWED_ACTIONS",
    "SendRefused",
    "SimApiLog",
    "TABLET_ACTION",
    "YTD_ACTION",
    "action_allowed",
    "action_word",
]
