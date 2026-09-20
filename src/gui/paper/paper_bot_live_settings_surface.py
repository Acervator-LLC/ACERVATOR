"""The Paper Trader's Bot Settings window model, forked from
``bot_live_settings_surface``.

``PaperBotLiveSettingsModel`` is Live's window model over a ``PaperBotView`` with
``sibling_bot_ids`` answered from ``sibling_ids``, the venue's paper fleet.
``refused_text`` is the pending line after a refused Apply.
``build_view_model`` is Live's builder under ``METHOD``.
"""

from __future__ import annotations

from typing import Any

from ..main_tabs import bot_live_settings_surface as live

METHOD = "paper_bot_live_settings.state"

CHANGE_REFUSED_FORMAT = "Refused {count} change(s) — the Paper Trader sends nothing"
CHANGE_REFUSED_STYLE = live.CHANGE_PENDING_STYLE


def refused_text(count: Any) -> str:
    """The pending line after Apply Changes is refused for ``count`` fields."""
    return CHANGE_REFUSED_FORMAT.format(count=count)


class PaperBotLiveSettingsModel(live.BotLiveSettingsModel):
    """Live's window model with the siblings read from ``sibling_ids``."""

    def __init__(self, bot: Any = None, sibling_ids: Any = None) -> None:
        super().__init__(bot, None)
        self.sibling_ids = [str(one) for one in (sibling_ids or ())]

    def sibling_bot_ids(self) -> list:
        """The venue's paper fleet ids, in the order the host handed them."""
        return list(self.sibling_ids)


def build_model(bot: Any, sibling_ids: Any = None) -> PaperBotLiveSettingsModel:
    """One window model over ``bot`` and ``sibling_ids``."""
    return PaperBotLiveSettingsModel(bot, sibling_ids)


def build_view_model(model: live.BotLiveSettingsModel) -> dict:
    """Live's ``build_view_model`` under ``METHOD``."""
    payload = dict(live.build_view_model(model))
    payload["method"] = METHOD
    return payload
