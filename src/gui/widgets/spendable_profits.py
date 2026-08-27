"""Spendable-profits strip shown under the main window header."""

from __future__ import annotations

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
        """Estimated expendable liquidity across all bots/exchanges.

        v3.19.29 — column-per-stat layout per operator UX request
        2026-05-22: "We should put the labels on top for this panels data
        fields as this will match the styling of the other top components
        and allow for larger number entries in the future."

        Each stat is a vertical column with:
          • SMALL UPPERCASE LABEL on top (muted color)
          • Larger numeric value below (stat-appropriate accent color)
        Columns separated by thin vertical dividers. The "Spendable"
        column is highlighted with the bright accent; other columns use
        a more muted palette.
        """

        # Style tokens — kept as class attributes so contract tests can
        # introspect the styling intent without re-parsing the literal
        # stylesheet strings each refactor.
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

            # v3.23.7 — last-known payload so a dot-toggle can re-render
            # the displayed values from the same data the dashboard
            # passed in. Without this, clicking a dot between dashboard
            # ticks would leave the cell showing the old value formatting.
            self._last_data: dict = {}

            # v3.23.7 — track privacy dots so set_all-style global flips
            # can refresh every dot at once from the parent MainWindow.
            self._privacy_dots: list = []

            # Spendable — featured column with bright accent
            spend_col = QVBoxLayout()
            spend_col.setSpacing(2)
            spend_col.setContentsMargins(0, 0, 0, 0)
            self._spend_label = QLabel("SPENDABLE")
            self._spend_label.setStyleSheet(
                f"color: {ds.PRIMARY}; font-size: 10px; letter-spacing: 1px; "
                "font-weight: 700;"
            )
            self._spend_label.setToolTip(
                "Estimated expendable liquidity from positions filled 30+ days.\n"
                "Passive income safely withdrawable without disrupting positions."
            )
            spend_col.addWidget(self._spend_label)
            self._amount = QLabel("$0.00")
            self._amount.setStyleSheet(self._VALUE_STYLE_HIGHLIGHT)
            spend_col.addWidget(self._amount)
            # v3.23.7 privacy dot — toggles kpi.spendable mask. Lives
            # at index 2 in the VBox so the v3.19.29 layout pin
            # (label at index 0, value at index 1) still passes.
            self._spend_dot = PrivacyDot(
                "kpi.spendable", on_toggle=self._on_privacy_toggle
            )
            self._privacy_dots.append(self._spend_dot)
            spend_col.addWidget(self._spend_dot, alignment=Qt.AlignHCenter)
            outer.addLayout(spend_col)

            # v3.23.7 — field id per KPI column. Spendable handled above
            # (it has the featured-style accent label); the rest share
            # the same label-row-with-dot pattern.
            _KPI_FIELD_BY_KEY = {
                "total_realised": "kpi.realised",
                "locked": "kpi.locked",
                "mature": "kpi.mature",
                "exchanges": "kpi.exch",
            }

            # Build a column per remaining stat
            self._stats = {}
            self._kpi_dots: dict = {}
            for label_text, key in [
                ("REALISED", "total_realised"),
                ("LOCKED", "locked"),
                ("MATURE", "mature"),
                ("EXCH", "exchanges"),
            ]:
                # Vertical separator between columns
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
                # v3.23.7 privacy dot per KPI column. Placed at index 2
                # (after the label at index 0 and the value at index 1)
                # so the v3.19.29 column-VBox layout contract still
                # holds: itemAt(0).widget() is QLabel, itemAt(1).widget()
                # is QLabel.
                dot = PrivacyDot(
                    _KPI_FIELD_BY_KEY[key], on_toggle=self._on_privacy_toggle
                )
                self._privacy_dots.append(dot)
                self._kpi_dots[key] = dot
                col.addWidget(dot, alignment=Qt.AlignHCenter)
                outer.addLayout(col)

            outer.addStretch()

        def update_profits(self, data: dict) -> None:
            # v3.16.46 — None-aware rendering. If a field is None it
            # means "not currently derivable from a trustworthy source"
            # — display "—" rather than fabricate a value (operator
            # directive: stop displaying fictional numbers).
            # v3.19.29 — uses class style tokens so the column layout
            # styling stays consistent.
            # v3.23.7 — each value passes through mask_or() so the
            # privacy dot per column can hide the number on demand.
            # We keep the original styling logic (color by sign for
            # Spendable, "—" for None) and only swap the FINAL string.
            self._last_data = dict(data) if isinstance(data, dict) else {}
            sp = data.get("spendable")
            if sp is None:
                raw_sp = "—"
                self._amount.setStyleSheet(self._VALUE_STYLE_MUTED)
                self._amount.setToolTip(
                    "Spendable amount is not derivable from current data "
                    "sources. Requires exchange-pulled position-age data "
                    "(see P0a in NEXT_SESSION_ORDERS.md)."
                )
            else:
                style = (
                    self._VALUE_STYLE_HIGHLIGHT
                    if sp >= 0
                    else self._VALUE_STYLE_NEGATIVE
                )
                raw_sp = f"${sp:,.2f}"
                self._amount.setStyleSheet(style)
                self._amount.setToolTip("")
            self._amount.setText(mask_or(raw_sp, "kpi.spendable"))

            tr = data.get("total_realised", 0)
            raw_tr = f"${tr:,.2f}" if tr is not None else "—"
            self._stats["total_realised"].setText(mask_or(raw_tr, "kpi.realised"))
            lk = data.get("locked")
            raw_lk = f"${lk:,.2f}" if lk is not None else "—"
            self._stats["locked"].setText(mask_or(raw_lk, "kpi.locked"))
            mt = data.get("mature")
            raw_mt = f"${mt:,.2f}" if mt is not None else "—"
            self._stats["mature"].setText(mask_or(raw_mt, "kpi.mature"))
            raw_ex = str(data.get("exchange_count", 0))
            self._stats["exchanges"].setText(mask_or(raw_ex, "kpi.exch"))

        def _on_privacy_toggle(self) -> None:
            """v3.23.7 — re-render values with the last payload so a
            dot toggle takes effect immediately without waiting for the
            5-second dashboard refresh tick."""
            if self._last_data:
                self.update_profits(self._last_data)

        def refresh_privacy_dots(self) -> None:
            """v3.23.7 — global Privacy Mode button calls this on every
            child widget so all dots repaint after a set_all() flip."""
            for d in self._privacy_dots:
                try:  # noqa: SIM105
                    d.refresh()
                except Exception:  # R28-OK  # noqa: S110
                    pass
            if self._last_data:
                self.update_profits(self._last_data)
