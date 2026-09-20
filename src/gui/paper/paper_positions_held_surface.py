"""The Paper Trader's Positions Held tab model, forked from
``positions_held_surface``.

``PaperPositionsHeldTabModel`` is Live's model over a ``PaperBotView``, whose
``positions_for_gui`` and pool figures come from ``extractor_state``; no
manager and no schedule is attached. ``build_view_model`` is Live's
builder under ``METHOD``.
"""

from __future__ import annotations

from typing import Any

from ..main_tabs import positions_held_surface as live

METHOD = "paper_positions_held_tab.state"


class PaperPositionsHeldTabModel(live.PositionsHeldTabModel):
    """Live's Positions Held model with no manager and no schedule."""

    def __init__(self, bot: Any = None) -> None:
        super().__init__(bot)


def build_view_model(
    model: live.PositionsHeldTabModel, build_now: bool = False
) -> dict:
    """Live's ``build_view_model`` under ``METHOD``."""
    payload = dict(live.build_view_model(model, build_now=build_now))
    payload["method"] = METHOD
    return payload
