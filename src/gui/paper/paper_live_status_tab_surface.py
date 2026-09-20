"""The Paper Trader's Status tab model, forked from ``live_status_tab_surface``.

``PaperLiveStatusTabModel`` is Live's model over a ``PaperBotView``, whose
``get_status`` and ``stats`` come from the stored record; ``build_view_model``
is Live's builder under ``METHOD``.
"""

from __future__ import annotations

from typing import Any

from ..main_tabs import live_status_tab_surface as live

METHOD = "paper_live_status_tab.state"


class PaperLiveStatusTabModel(live.LiveStatusTabModel):
    """Live's Status tab model, read from the record's ``stats``."""

    def __init__(self, bot: Any = None, clock: Any = None) -> None:
        super().__init__(bot, clock)


def build_view_model(model: live.LiveStatusTabModel, build_now: bool = False) -> dict:
    """Live's ``build_view_model`` under ``METHOD``."""
    payload = dict(live.build_view_model(model, build_now=build_now))
    payload["method"] = METHOD
    return payload
