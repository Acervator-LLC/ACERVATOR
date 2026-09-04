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

    # Supplied by BotLiveSettingsDialog at runtime; declared so a
    # type checker can resolve them. Annotations only: no attribute
    # is created and the runtime base stays `object`.
    _bot: Any

    # Tab 5: Market Inspector (v3.23.37, scrumming-only)
    # Delegates to src.gui.market_inspector.build_per_bot_view, which
    # reads the shared analyzer's most recent scan (populated by the
    # top-level Market Inspector tab's Refresh button). Renders this
    # bot's asset card, higher-scoring markets, and opposing pairs.
    # Replaces the retired Mr. Inspector tab (was a phantom for
    # crypto bots — no caller wired ScrummingBot._mr_inspector).
    def _create_market_inspector_tab(self) -> QWidget:
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
