"""Spendable-profits strip shown under the main window header."""

from __future__ import annotations

import math

from ...core.privacy_mask_registry import mask_or

from .. import design_system as ds

try:
    from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout
    from PySide6.QtCore import Qt

    from .privacy_dot import PrivacyDot

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    class SpendableProfitsWidget(QFrame):
        """One labelled column per KPI, divided by thin vertical rules."""

        _LABEL_STYLE = (
            f"color: {ds.CARD_METRIC_LABEL}; font-size: 10px; "
            "letter-spacing: 1px; font-weight: 600;"
        )
        _VALUE_STYLE_DEFAULT = (
            f"color: {ds.TEXT_NEUTRAL}; font-size: 16px; font-weight: bold;"
        )
        _VALUE_STYLE_HIGHLIGHT = (
            f"color: {ds.SUCCESS}; font-size: 16px; font-weight: bold;"
        )
        _VALUE_STYLE_NEGATIVE = (
            f"color: {ds.ERROR}; font-size: 16px; font-weight: bold;"
        )
        _VALUE_STYLE_MUTED = (
            f"color: {ds.CARD_METRIC_LABEL}; font-size: 16px; font-weight: bold;"
        )
        _SEPARATOR_STYLE = (
            f"color: {ds.MAIN_SEPARATOR}; font-size: 24px; margin: 0 2px;"
        )
        _SPENDABLE_ABSENT_TIP = (
            "This amount is not in the data the strip was given for this refresh."
        )
        _UNREADABLE_TIP = (
            "This amount did not arrive as a number, so nothing is shown for it."
        )

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setFrameShape(QFrame.StyledPanel)
            self.setStyleSheet(
                "SpendableProfitsWidget { "
                "  background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                "    stop:0 rgba(0,40,30,200), stop:1 rgba(0,60,45,200)); "
                "  border: 1px solid rgba(0,255,180,80); border-radius: 4px; }"
            )

            outer = QHBoxLayout(self)
            outer.setContentsMargins(12, 6, 12, 6)
            outer.setSpacing(0)

            # A dot toggle re-renders from this last data, not the next tick.
            self._last_data: dict = {}

            # refresh_privacy_dots repaints every dot in this list at once.
            self._privacy_dots: list = []

            spend_col = QVBoxLayout()
            spend_col.setSpacing(2)
            spend_col.setContentsMargins(0, 0, 0, 0)
            self._spend_label = QLabel("SPENDABLE")
            self._spend_label.setStyleSheet(
                f"color: {ds.PRIMARY}; font-size: 10px; letter-spacing: 1px; "
                "font-weight: 700;"
            )
            self._spend_label.setToolTip(
                "Cash balance pulled from the exchange, across the bots "
                "sharing one wallet."
            )
            spend_col.addWidget(self._spend_label)
            self._amount = QLabel("—")
            self._amount.setStyleSheet(self._VALUE_STYLE_MUTED)
            spend_col.addWidget(self._amount)
            # The dot sits at index 2, keeping label at 0 and value at 1.
            self._spend_dot = PrivacyDot(
                "kpi.spendable", on_toggle=self._on_privacy_toggle
            )
            self._privacy_dots.append(self._spend_dot)
            spend_col.addWidget(self._spend_dot, alignment=Qt.AlignHCenter)
            outer.addLayout(spend_col)

            # Spendable is built above; these four share one KPI field shape.
            _KPI_FIELD_BY_KEY = {
                "total_realised": "kpi.realised",
                "locked": "kpi.locked",
                "mature": "kpi.mature",
                "exchanges": "kpi.exch",
            }

            self._stats = {}
            for label_text, key in [
                ("REALISED", "total_realised"),
                ("LOCKED", "locked"),
                ("MATURE", "mature"),
                ("EXCH", "exchanges"),
            ]:
                sep = QLabel("|")
                sep.setStyleSheet(self._SEPARATOR_STYLE)
                sep.setAlignment(Qt.AlignVCenter)
                outer.addSpacing(14)
                outer.addWidget(sep)
                outer.addSpacing(14)

                col = QVBoxLayout()
                col.setSpacing(2)
                col.setContentsMargins(0, 0, 0, 0)
                lbl = QLabel(label_text)
                lbl.setStyleSheet(self._LABEL_STYLE)
                col.addWidget(lbl)
                val = QLabel("—")
                val.setStyleSheet(self._VALUE_STYLE_DEFAULT)
                self._stats[key] = val
                col.addWidget(val)
                dot = PrivacyDot(
                    _KPI_FIELD_BY_KEY[key], on_toggle=self._on_privacy_toggle
                )
                self._privacy_dots.append(dot)
                col.addWidget(dot, alignment=Qt.AlignHCenter)
                outer.addLayout(col)

            outer.addStretch()

        @staticmethod
        def _amount_of(value):
            """The finite number a payload value carries, unconverted."""
            if type(value) is int:
                return value
            if type(value) is float and math.isfinite(value):
                return value
            return None

        @staticmethod
        def _money_text(value) -> str:
            """Render one amount as money text, or as the empty marker."""
            amount = SpendableProfitsWidget._amount_of(value)
            if amount is None:
                return "—"
            return f"${amount:,.2f}"

        @staticmethod
        def _count_text(value) -> str:
            """Render a whole exchange count, or the empty marker."""
            if type(value) is not int:
                return "—"
            return str(value)

        def update_profits(self, data: dict) -> None:
            """Draw every column from one payload, then keep that payload."""
            kept = dict(data) if isinstance(data, dict) else {}
            sp = data.get("spendable")
            amount = self._amount_of(sp)
            if sp is None:
                skin, tip = self._VALUE_STYLE_MUTED, self._SPENDABLE_ABSENT_TIP
            elif amount is None:
                skin, tip = self._VALUE_STYLE_MUTED, self._UNREADABLE_TIP
            elif amount >= 0:
                skin, tip = self._VALUE_STYLE_HIGHLIGHT, ""
            else:
                skin, tip = self._VALUE_STYLE_NEGATIVE, ""
            drawn = {
                "spendable": self._money_text(sp),
                "total_realised": self._money_text(data.get("total_realised")),
                "locked": self._money_text(data.get("locked")),
                "mature": self._money_text(data.get("mature")),
                "exchanges": self._count_text(data.get("exchange_count")),
            }
            self._amount.setStyleSheet(skin)
            self._amount.setToolTip(tip)
            self._amount.setText(mask_or(drawn["spendable"], "kpi.spendable"))
            for key, field_id in (
                ("total_realised", "kpi.realised"),
                ("locked", "kpi.locked"),
                ("mature", "kpi.mature"),
                ("exchanges", "kpi.exch"),
            ):
                self._stats[key].setText(mask_or(drawn[key], field_id))
            self._last_data = kept

        def _on_privacy_toggle(self) -> None:
            """Re-draw the kept payload so a dot toggle shows at once."""
            if self._last_data:
                self.update_profits(self._last_data)

        def refresh_privacy_dots(self) -> None:
            """Repaint every dot, then re-draw the kept payload."""
            for d in self._privacy_dots:
                try:  # noqa: SIM105
                    d.refresh()
                except Exception:  # R28-OK  # noqa: S110
                    pass
            if self._last_data:
                self.update_profits(self._last_data)
