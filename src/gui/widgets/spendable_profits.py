"""Spendable-profits strip shown under the main window header."""

from __future__ import annotations

import logging

from ...core.privacy_mask_registry import ABSENT_TEXT as _ABSENT_TEXT
from ...trading.target_bands import TERRITORY_FOLD, TERRITORY_SCRUM

from .. import design_system as ds
from ..main_tabs.header_strip_surface import VALUE_FONT_MIN_PX, VALUE_FONT_PX
from ..main_tabs.spendable_profits_surface import (
    COLUMNS,
    FIELD_ID_BY_KEY,
    MONEY_KEYS,
    column_cell,
    money_amount,
)

logger = logging.getLogger("acervator.gui")

try:
    from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout
    from PySide6.QtCore import Qt

    from .eliding_label import ElidingLabel
    from .fitted_label import FittedLabel
    from .privacy_dot import PrivacyDot

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    class SpendableProfitsWidget(QFrame):
        """One labelled column per KPI, divided by thin vertical rules."""

        _LABEL_STYLE = (
            f"color: {ds.CARD_METRIC_LABEL}; font-size: 10px; font-weight: 600;"
        )
        _SPENDABLE_LABEL_STYLE = (
            f"color: {ds.PRIMARY}; font-size: 10px; font-weight: 600;"
        )
        _LABEL_ALIGN = Qt.AlignHCenter | Qt.AlignBottom
        _VALUE_ALIGN = Qt.AlignHCenter | Qt.AlignTop
        #: One share of the row each, so every column sits at one pitch.
        _COLUMN_STRETCH = 1
        _VALUE_PX = VALUE_FONT_PX
        _VALUE_MIN_PX = VALUE_FONT_MIN_PX
        #: An amount's colour alone; ``FittedLabel`` appends the size it fits.
        _VALUE_SKIN_DEFAULT = f"color: {ds.TEXT_NEUTRAL};"
        _VALUE_SKIN_HIGHLIGHT = f"color: {ds.SUCCESS};"
        _VALUE_SKIN_NEGATIVE = f"color: {ds.ERROR};"
        _VALUE_SKIN_MUTED = f"color: {ds.CARD_METRIC_LABEL};"
        _VALUE_FONT = f"font-size: {_VALUE_PX}px; font-weight: bold;"
        _VALUE_STYLE_DEFAULT = f"{_VALUE_SKIN_DEFAULT} {_VALUE_FONT}"
        _VALUE_STYLE_HIGHLIGHT = f"{_VALUE_SKIN_HIGHLIGHT} {_VALUE_FONT}"
        _VALUE_STYLE_NEGATIVE = f"{_VALUE_SKIN_NEGATIVE} {_VALUE_FONT}"
        _VALUE_STYLE_MUTED = f"{_VALUE_SKIN_MUTED} {_VALUE_FONT}"
        _SEPARATOR_STYLE = (
            f"color: {ds.MAIN_SEPARATOR}; font-size: 24px; margin: 0 2px;"
        )
        #: The gap either side of a rule, matching ``SPENDABLE_COLUMN_GAP_PX``.
        _COLUMN_GAP_PX = 3
        #: One rule's own width, matching ``SPENDABLE_RULE_W_PX``.
        _RULE_W_PX = 12
        #: The skin each ``ammo_lean`` answer draws the Ammo total in.
        _AMMO_SKIN_BY_LEAN = {
            TERRITORY_SCRUM: _VALUE_SKIN_HIGHLIGHT,
            TERRITORY_FOLD: _VALUE_SKIN_NEGATIVE,
        }

        #: Every column drawing money, which shrinks rather than shortens.
        _MONEY_KEYS = MONEY_KEYS
        _PNL_TIP = (
            "P/L — the unrealised profit and loss the exchange answers across "
            "every bot's open position. It is the only profit and loss figure "
            "the strip carries."
        )
        _AMMO_TIP = (
            "Total Ammo — every bot's Target Delta added together, in whole "
            "dollars. Green while more bots hold more than their target, red "
            "while more hold less."
        )
        _SPENDABLE_ABSENT_TIP = (
            "This amount is not in the data the strip was given for this refresh."
        )
        _UNREADABLE_TIP = (
            "This amount did not arrive as a number, so nothing is shown for it."
        )
        #: The columns carrying a tooltip, by key. Every other column's
        #: caption says all there is to say about it.
        _TIP_BY_KEY = {"pnl": _PNL_TIP, "total_ammo": _AMMO_TIP}

        def __init__(self, parent=None):
            super().__init__(parent)
            self._setup_ui()

        @staticmethod
        def _hold_caption_width(label) -> None:
            """Floor one caption at the width its whole text needs, which
            ``ElidingLabel.minimumSizeHint`` does not."""
            label.setMinimumWidth(label.sizeHint().width())

        def _setup_ui(self) -> None:
            """Build the frame, one column per ``COLUMNS`` entry, and their dots."""
            self.setFrameShape(QFrame.StyledPanel)
            self.setStyleSheet(
                "SpendableProfitsWidget { "
                "  background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                "    stop:0 rgba(0,40,30,200), stop:1 rgba(0,60,45,200)); "
                "  border: 1px solid rgba(0,255,180,80); border-radius: 4px; }"
            )

            outer = QHBoxLayout(self)
            outer.setContentsMargins(6, 4, 6, 4)
            outer.setSpacing(0)

            # A dot toggle re-renders from this last data, not the next tick.
            self._last_data: dict = {}

            # refresh_privacy_dots repaints every dot in this list at once.
            self._privacy_dots: list = []

            spend_col = QVBoxLayout()
            spend_col.setSpacing(2)
            spend_col.setContentsMargins(0, 0, 0, 0)
            self._spend_label = ElidingLabel("SPENDABLE")
            self._spend_label.setStyleSheet(self._SPENDABLE_LABEL_STYLE)
            self._spend_label.setAlignment(self._LABEL_ALIGN)
            self._hold_caption_width(self._spend_label)
            self._spend_label.setToolTip(
                "Cash balance pulled from the exchange, across the bots "
                "sharing one wallet."
            )
            spend_col.addWidget(self._spend_label)
            self._amount = FittedLabel(_ABSENT_TEXT, self._VALUE_PX, self._VALUE_MIN_PX)
            self._amount.set_skin(self._VALUE_SKIN_MUTED)
            self._amount.setAlignment(self._VALUE_ALIGN)
            spend_col.addWidget(self._amount)
            # The dot sits at index 2, keeping label at 0 and value at 1.
            self._spend_dot = PrivacyDot(
                "kpi.spendable", on_toggle=self._on_privacy_toggle
            )
            self._privacy_dots.append(self._spend_dot)
            spend_col.addWidget(self._spend_dot, alignment=Qt.AlignHCenter)
            outer.addLayout(spend_col, self._COLUMN_STRETCH)

            # Spendable is built above; the rest come from the one column
            # declaration both hosts read, so no caption is spelled twice.
            self._stats = {}
            for column in COLUMNS[1:]:
                label_text = column["label"]
                key = column["key"]
                tip = self._TIP_BY_KEY.get(key, "")
                sep = QLabel("|")
                sep.setStyleSheet(self._SEPARATOR_STYLE)
                sep.setAlignment(Qt.AlignVCenter)
                sep.setFixedWidth(self._RULE_W_PX)
                outer.addSpacing(self._COLUMN_GAP_PX)
                outer.addWidget(sep)
                outer.addSpacing(self._COLUMN_GAP_PX)

                col = QVBoxLayout()
                col.setSpacing(2)
                col.setContentsMargins(0, 0, 0, 0)
                lbl = ElidingLabel(label_text)
                lbl.setStyleSheet(self._LABEL_STYLE)
                lbl.setAlignment(self._LABEL_ALIGN)
                self._hold_caption_width(lbl)
                lbl.setToolTip(tip)
                col.addWidget(lbl)
                if key in self._MONEY_KEYS:
                    val = FittedLabel(_ABSENT_TEXT, self._VALUE_PX, self._VALUE_MIN_PX)
                    val.set_skin(self._VALUE_SKIN_DEFAULT)
                else:
                    val = ElidingLabel(_ABSENT_TEXT)
                    val.setStyleSheet(self._VALUE_STYLE_DEFAULT)
                val.setAlignment(self._VALUE_ALIGN)
                val.setToolTip(tip)
                self._stats[key] = val
                col.addWidget(val)
                dot = PrivacyDot(
                    FIELD_ID_BY_KEY[key], on_toggle=self._on_privacy_toggle
                )
                self._privacy_dots.append(dot)
                col.addWidget(dot, alignment=Qt.AlignHCenter)
                outer.addLayout(col, self._COLUMN_STRETCH)

        # Every cell renders through the surface, so a format changed there
        # reaches this screen and the page in one edit.
        _amount_of = staticmethod(money_amount)

        def _ammo_skin(self, value, lean) -> str:
            """The skin the Ammo total draws in for one total and one lean."""
            if self._amount_of(value) is None:
                return self._VALUE_SKIN_MUTED
            return self._AMMO_SKIN_BY_LEAN.get(
                str(lean or ""), self._VALUE_SKIN_DEFAULT
            )

        def update_profits(self, data: dict) -> None:
            """Draw every column from one payload, then keep that payload.

            The cells are walked from ``COLUMNS``, the declaration
            ``_setup_ui`` built the columns from, so no text is rendered for a
            column this strip does not draw.
            """
            kept = dict(data) if isinstance(data, dict) else {}
            sp = kept.get("spendable")
            amount = self._amount_of(sp)
            if sp is None:
                skin, tip = self._VALUE_SKIN_MUTED, self._SPENDABLE_ABSENT_TIP
            elif amount is None:
                skin, tip = self._VALUE_SKIN_MUTED, self._UNREADABLE_TIP
            elif amount >= 0:
                skin, tip = self._VALUE_SKIN_HIGHLIGHT, ""
            else:
                skin, tip = self._VALUE_SKIN_NEGATIVE, ""
            ammo = kept.get("total_ammo")
            cells = {column["key"]: column_cell(column, kept) for column in COLUMNS}
            self._stats["total_ammo"].set_skin(
                self._ammo_skin(ammo, kept.get("ammo_lean"))
            )
            self._amount.set_skin(skin)
            self._amount.setToolTip(tip)
            self._amount.setText(cells[COLUMNS[0]["key"]]["text"])
            for key, label in self._stats.items():
                label.setText(cells[key]["text"])
            self._last_data = kept

        def _on_privacy_toggle(self) -> None:
            """Re-draw the kept payload so a dot toggle shows at once."""
            if self._last_data:
                self.update_profits(self._last_data)

        def refresh_privacy_dots(self) -> None:
            """Repaint every dot, then re-draw the kept payload."""
            for d in self._privacy_dots:
                try:
                    d.refresh()
                except RuntimeError as dot_exc:
                    logger.debug(
                        "money strip: the %s dot could not repaint (%s); it "
                        "keeps the glyph it already shows, which may name the "
                        "wrong mask state",
                        d.field_id(),
                        dot_exc,
                    )
            if self._last_data:
                self.update_profits(self._last_data)
