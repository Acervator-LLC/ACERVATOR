"""Market Inspector tab of the Live Bot Settings dialog."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QWidget,
)

from .. import design_system as ds
from ..main_tabs import market_inspector_tab_surface as mi_surface

logger = logging.getLogger("acervator.gui")


class MarketInspectorTabMixin:
    """Per-bot view of the shared analyzer's most recent scan."""

    # Supplied by BotLiveSettingsDialog at runtime; annotation only, so
    # no attribute is created here.
    _bot: Any

    def _create_market_inspector_tab(self) -> QWidget:
        """Render this bot's card from the shared analyzer's most recent scan.

        ``build_per_bot_view`` reads the scan the top-level Market Inspector
        tab's Refresh button populates.
        """
        try:
            from ..market_inspector import build_per_bot_view

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
