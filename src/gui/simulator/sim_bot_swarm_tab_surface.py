"""The Simulator's Bot Swarm tab model, forked from ``bot_swarm_tab_surface``.

``SimBotSwarmTabModel`` is Live's model over a ``SimBotView``; a record
holds no Smart Wire manager, so the tab draws Live's not-active screen.
``build_view_model`` is Live's builder under ``METHOD``.
"""

from __future__ import annotations

from typing import Any

from ..main_tabs import bot_swarm_tab_surface as live

METHOD = "sim_bot_swarm_tab.state"


class SimBotSwarmTabModel(live.BotSwarmTabModel):
    """Live's Bot Swarm model over a record with no wire manager."""

    def __init__(self, bot: Any = None) -> None:
        super().__init__(bot)


def build_view_model(model: live.BotSwarmTabModel) -> dict:
    """Live's ``build_view_model`` under ``METHOD``."""
    payload = dict(live.build_view_model(model))
    payload["method"] = METHOD
    return payload
