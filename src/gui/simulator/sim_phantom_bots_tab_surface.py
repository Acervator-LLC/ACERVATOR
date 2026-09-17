"""The Simulator's Phantom Bots tab model, forked from
``phantom_bots_tab_surface``.

``SimPhantomBotsTabModel`` is Live's model over a ``SimBotView``: the enable
flag, the timeframes and the lock count come from the record's own keys, and
the runtime rows read as a bot before its first tick. ``build_view_model``
is Live's builder under ``METHOD``.
"""

from __future__ import annotations

from typing import Any

from ..main_tabs import phantom_bots_tab_surface as live

METHOD = "sim_phantom_bots_tab.state"


class SimPhantomBotsTabModel(live.PhantomBotsTabModel):
    """Live's Phantom Bots model over the record's three phantom keys."""

    def __init__(self, bot: Any = None) -> None:
        super().__init__(bot)


def build_view_model(model: live.PhantomBotsTabModel, build_now: bool = False) -> dict:
    """Live's ``build_view_model`` under ``METHOD``."""
    payload = dict(live.build_view_model(model, build_now=build_now))
    payload["method"] = METHOD
    return payload
