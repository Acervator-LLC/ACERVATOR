"""The Simulator's Stack Tranches tab model, forked from
``stack_tranches_tab_surface``.

``SimStackTranchesTabModel`` is Live's model over a ``SimBotView``, the
ladder and the two counters read from the stored record with no saver and
no host. ``build_view_model`` is Live's builder under ``METHOD``.
"""

from __future__ import annotations

from typing import Any

from ..main_tabs import stack_tranches_tab_surface as live

METHOD = "sim_stack_tranches_tab.state"


class SimStackTranchesTabModel(live.StackTranchesTabModel):
    """Live's Stack Tranches model with no saver and no host."""

    def __init__(self, bot: Any = None) -> None:
        super().__init__(bot)


def build_view_model(model: live.StackTranchesTabModel) -> dict:
    """Live's ``build_view_model`` under ``METHOD``."""
    payload = dict(live.build_view_model(model))
    payload["method"] = METHOD
    return payload
