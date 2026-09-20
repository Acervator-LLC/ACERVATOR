"""The exchange chooser Import Live Fleet opens when ``bot_state.json`` names
more than one exchange, on both Paper hosts, forked from the Simulator's.

``PaperExchangeChoiceDialog`` is Live's one-question ``QDialog``, the Bot Swarm
tab's Configure Profit Wire, holding the bot wizard's ``Exchange:`` combo row:
``exchange_prompt_text`` above ``exchange_choice_options`` under ``title``,
``EXCHANGE_CHOICE_TITLE`` when none is given, then Ok and Cancel. ``chosen``
answers the id picked once ``exec`` has accepted, and ``""`` after Cancel.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .paper_trading_tab_surface import (
    EXCHANGE_CHOICE_MIN_WIDTH_PX,
    EXCHANGE_CHOICE_ROW_LABEL,
    EXCHANGE_CHOICE_TITLE,
    exchange_choice_options,
    exchange_prompt_text,
)

logger = logging.getLogger("acervator.gui")

ACCESSIBLE_NAME = "paper-exchange-choice"

try:
    from PySide6.QtWidgets import (
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QLabel,
        QVBoxLayout,
    )

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    class PaperExchangeChoiceDialog(QDialog):
        """One exchange of ``options`` picked from a combo, Ok or Cancel."""

        def __init__(
            self,
            options: Any,
            parent: Optional[Any] = None,
            title: str = EXCHANGE_CHOICE_TITLE,
        ) -> None:
            super().__init__(parent)
            self.setWindowTitle(str(title or EXCHANGE_CHOICE_TITLE))
            self.setAccessibleName(ACCESSIBLE_NAME)
            self.setMinimumWidth(EXCHANGE_CHOICE_MIN_WIDTH_PX)
            column = QVBoxLayout(self)
            ids = [str(one) for one in options if one]
            column.addWidget(QLabel(exchange_prompt_text(ids)))
            row = QFormLayout()
            self._exchange = QComboBox()
            self._exchange.setAccessibleName(EXCHANGE_CHOICE_ROW_LABEL)
            for entry in exchange_choice_options(ids):
                self._exchange.addItem(entry["display_name"], entry["exchange_id"])
            row.addRow(EXCHANGE_CHOICE_ROW_LABEL, self._exchange)
            column.addLayout(row)
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            column.addWidget(buttons)

        def options(self) -> list:
            """The exchange ids the combo lists, in its order."""
            return [
                str(self._exchange.itemData(at)) for at in range(self._exchange.count())
            ]

        def chosen(self) -> str:
            """The exchange id picked, or ``""`` while the dialog is not accepted."""
            if self.result() != QDialog.Accepted:
                return ""
            return str(self._exchange.currentData() or "")
