"""The Paper Trader's Fold Tranches tab model, forked from
``fold_tranches_tab_surface``.

``PaperFoldTranchesTabModel`` is Live's model over a ``PaperBotView``: the
tranches, the counters and the parked credits come from the stored record,
``open_extractor_tranches`` answers none, and no manager and no loop is
attached. ``build_view_model`` is Live's builder under ``METHOD``.
"""

from __future__ import annotations

from typing import Any

from ..main_tabs import fold_tranches_tab_surface as live

METHOD = "paper_fold_tranches_tab.state"


class PaperFoldTranchesTabModel(live.FoldTranchesTabModel):
    """Live's Fold Tranches model with no manager, no schedule and no save."""

    def __init__(self, bot: Any = None, now: float = 0.0) -> None:
        super().__init__(bot, now=now)


def build_view_model(model: live.FoldTranchesTabModel, build_now: bool = False) -> dict:
    """Live's ``build_view_model`` under ``METHOD``."""
    payload = dict(live.build_view_model(model, build_now=build_now))
    payload["method"] = METHOD
    return payload
