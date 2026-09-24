"""The Paper Trader's bot manager, forked from ``SimBotManager``: the parts of
``BotManager`` that hold and move bots, over the ``PaperBot`` records
``PaperFleetSource`` holds from the paper fleet file.

``PaperBotManager`` answers ``get_bot``, ``bots``, ``start``, ``pause``,
``stop``, ``restart`` and ``unregister``, the verbs the command bar's handler
asks of the live bot manager and the live bot, and ``start_all``, ``pause_all``,
``stop_all`` and ``restart_all``, the four the command bar asks with SHIFT
held. Each verb moves
``state_when_saved`` on one held record through ``PaperFleetSource.set_state``
under ``BotContainer``'s own rule for that verb, and ``unregister`` drops the
record through ``PaperFleetSource.remove``. ``PaperBotManager`` holds one
``PaperFleetSource`` and no venue, no connector, no event bus and no coroutine.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..trading.container.config import BotState
from .fleet_source import PaperBot, PaperFleetSource

logger = logging.getLogger("acervator.paper.fleet")

#: The states ``BotContainer.start`` refuses to start from.
ALREADY_RUNNING_STATES = (BotState.RUNNING.value, BotState.STARTING.value)


class PaperBotManager:
    """The registry and the state moves of the paper fleet, over one
    ``PaperFleetSource``."""

    def __init__(self, fleet_source: PaperFleetSource) -> None:
        self._fleet = fleet_source

    def get_bot(self, bot_id: str) -> Optional[PaperBot]:
        """The held ``PaperBot`` under ``bot_id``, or None, as
        ``BotManager.get_bot`` answers None for an unregistered id."""
        return self._fleet.paper_bot_for(bot_id)

    def bots(self) -> list[PaperBot]:
        """Every held ``PaperBot``, the registry ``BotManager._bots`` holds on
        Live: what ``PaperFleetSource.bots`` answers."""
        return list(self._fleet.bots())

    def _require(self, bot_id: str) -> PaperBot:
        bot = self.get_bot(bot_id)
        if bot is None:
            raise KeyError(f"no paper bot is held under {str(bot_id)!r}")
        return bot

    def start(self, bot_id: str) -> str:
        """``BotContainer.start``'s rule: a bot in ``ALREADY_RUNNING_STATES``
        keeps its state and logs one warning, every other state clears
        ``stats.last_error`` and lands on ``running``. Answers the state
        after."""
        bot = self._require(bot_id)
        if bot.state in ALREADY_RUNNING_STATES:
            logger.warning("Bot %s already running", bot_id)
            return bot.state
        return self._fleet.set_state(bot_id, BotState.RUNNING.value, clear_error=True)

    def pause(self, bot_id: str) -> str:
        """``BotContainer.pause``'s rule: any state lands on ``paused``."""
        self._require(bot_id)
        return self._fleet.set_state(bot_id, BotState.PAUSED.value)

    def stop(self, bot_id: str) -> str:
        """``BotContainer.stop``'s rule: any state lands on ``stopped``."""
        self._require(bot_id)
        return self._fleet.set_state(bot_id, BotState.STOPPED.value)

    def restart(self, bot_id: str) -> str:
        """The window's restart sequence with no reconnect: ``stop`` then
        ``start``, so the bot lands on ``running``."""
        self.stop(bot_id)
        return self.start(bot_id)

    def start_all(self) -> int:
        """Run ``start`` over every held bot and answer how many landed on
        ``running``. A paper bot moves a saved state and connects to nothing,
        so the fleet needs no staggering."""
        return self._over_fleet(self.start, BotState.RUNNING.value)

    def pause_all(self) -> int:
        """Run ``pause`` over every held bot that reads ``running`` and answer
        how many landed on ``paused``."""
        return self._over_fleet(
            self.pause, BotState.PAUSED.value, only=(BotState.RUNNING.value,)
        )

    def stop_all(self) -> int:
        """Run ``stop`` over every held bot and answer how many landed on
        ``stopped``."""
        return self._over_fleet(self.stop, BotState.STOPPED.value)

    def restart_all(self) -> int:
        """Run ``restart`` over every held bot and answer how many landed on
        ``running``."""
        return self._over_fleet(self.restart, BotState.RUNNING.value)

    def _over_fleet(self, verb, wanted: str, only: Optional[tuple] = None) -> int:
        bots = [b for b in self.bots() if only is None or b.state in only]
        landed = 0
        for bot in bots:
            try:
                if verb(bot.bot_id) == wanted:
                    landed += 1
            except KeyError:
                logger.warning("Bot %s left the fleet mid-command", bot.bot_id)
        return landed

    def unregister(self, bot_id: str) -> bool:
        """Drop the held record through ``PaperFleetSource.remove``, as
        ``BotManager.unregister`` drops a bot from its registry and its state
        file; answers whether one was held."""
        return self._fleet.remove(bot_id)


__all__ = ["ALREADY_RUNNING_STATES", "PaperBotManager"]
