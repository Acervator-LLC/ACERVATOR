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
            logger.warning("Market Inspector per-bot view unavailable: %s", exc)
            w = QWidget()
            lay = QVBoxLayout(w)
            msg = QLabel(
                "<b>Market Inspector unavailable.</b><br><br>"
                f"{type(exc).__name__}: {exc}"
            )
            msg.setStyleSheet(f"color: {ds.FOLD_RATIO_AMBER}; padding: 12px;")
            msg.setWordWrap(True)
            lay.addWidget(msg)
            lay.addStretch()
            return w
