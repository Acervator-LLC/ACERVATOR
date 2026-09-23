"""The Paper Trader's Market Inspector tab model, forked from
``market_inspector_tab_surface``.

``per_bot_view`` answers Live's no-scan screen for any bot: a stored record
holds no scan, and the shared analyzer is never imported. ``PaperMarketInspectorTabModel``
is Live's model over ``NoScanSource``, and ``build_view_model`` is Live's
builder under ``METHOD``.
"""

from __future__ import annotations

from typing import Any

from ..main_tabs import market_inspector_tab_surface as live

METHOD = "paper_market_inspector_tab.state"


def per_bot_view(bot: Any) -> dict:
    """Live's ``per_bot_view`` shape with its no-scan row and no group."""
    return {
        "available": True,
        "asset": live.bot_asset(bot),
        "spacing_px": live.VIEW_SPACING_PX,
        "margin_px": live.LAYOUT_MARGIN_PX,
        "rows": [
            live.view_row(
                [
                    live.view_part(live.NO_SCAN_HEADLINE, bold=True),
                    live.view_part(live.NO_SCAN_BODY, breaks=live.NO_SCAN_BREAKS),
                ],
                color=live.NO_SCAN_COLOR,
                word_wrap=True,
                padding_px=live.NO_SCAN_PADDING_PX,
            )
        ],
        "groups": [],
        "stretch": True,
    }


class NoScanSource:
    """The view builder the Paper tab delegates to: ``per_bot_view`` above."""

    def build_per_bot_view(self, bot: Any) -> dict:
        return per_bot_view(bot)


class PaperMarketInspectorTabModel(live.MarketInspectorTabModel):
    """Live's tab model over ``NoScanSource``."""

    def __init__(self, bot: Any = None, source: Any = None) -> None:
        super().__init__(bot, NoScanSource() if source is None else source)


def build_view_model(
    model: live.MarketInspectorTabModel, build_now: bool = False
) -> dict:
    """Live's ``build_view_model`` under ``METHOD``."""
    payload = dict(live.build_view_model(model, build_now=build_now))
    payload["method"] = METHOD
    return payload
