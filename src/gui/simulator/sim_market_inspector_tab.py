"""Market Inspector tab of the Simulator's Bot Settings window, forked from
``live_settings.market_inspector_tab``; the shared analyzer is never asked."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtWidgets import (
    QGroupBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from .. import design_system as ds
from ..main_tabs import market_inspector_tab_surface as mi_surface
from . import sim_market_inspector_tab_surface as sim_surface

logger = logging.getLogger("acervator.gui")


def _per_bot_label(one: dict) -> QLabel:
    """One row of the per-bot view as the label the tab shows."""
    label = QLabel(mi_surface.row_html(one))
    sheet = mi_surface.row_style(one)
    if sheet:
        label.setStyleSheet(sheet)
    if one.get("word_wrap"):
        label.setWordWrap(True)
    return label


def build_per_bot_view(bot: Any) -> QWidget:
    """Draw ``sim_market_inspector_tab_surface.per_bot_view`` as Live draws its view."""
    view = sim_surface.per_bot_view(bot)
    w = QWidget()
    layout = QVBoxLayout(w)
    margin = int(view["margin_px"])
    layout.setContentsMargins(margin, margin, margin, margin)
    layout.setSpacing(int(view["spacing_px"]))
    for one in view["rows"]:
        layout.addWidget(_per_bot_label(one))
    for group in view["groups"]:
        box = QGroupBox(group["title"])
        box.setStyleSheet(mi_surface.group_style())
        inner = QVBoxLayout(box)
        box_margin = mi_surface.GROUP_MARGIN_PX
        inner.setContentsMargins(box_margin, box_margin, box_margin, box_margin)
        inner.setSpacing(mi_surface.GROUP_SPACING_PX)
        for one in group["rows"]:
            inner.addWidget(_per_bot_label(one))
        layout.addWidget(box)
    if view["stretch"]:
        layout.addStretch()
    return w


class SimMarketInspectorTabMixin:
    """Per-bot view drawn from the no-scan screen, never from the analyzer."""

    # Supplied by SimBotDetailDialog at runtime; annotation only, so
    # no attribute is created here.
    _bot: Any

    def _create_market_inspector_tab(self) -> QWidget:
        """Render this bot's card from ``sim_surface.per_bot_view``.

        A record holds no scan, so the view is Live's own no-scan screen.
        """
        try:
            return build_per_bot_view(self._bot)
        except Exception as exc:  # noqa: BLE001 - GUI import guard
            logger.warning(mi_surface.WARNING_FORMAT, exc)
            w = QWidget()
            lay = QVBoxLayout(w)
            margin = mi_surface.LAYOUT_MARGIN_PX
            lay.setContentsMargins(margin, margin, margin, margin)
            lay.setSpacing(mi_surface.FALLBACK_SPACING_PX)
            msg = QLabel(mi_surface.fallback_text(type(exc).__name__, exc))
            msg.setStyleSheet(
                mi_surface.fallback_style(
                    ds.FOLD_RATIO_AMBER, mi_surface.FALLBACK_PADDING_PX
                )
            )
            msg.setWordWrap(mi_surface.FALLBACK_WORD_WRAP)
            lay.addWidget(msg)
            lay.addStretch()
            return w
