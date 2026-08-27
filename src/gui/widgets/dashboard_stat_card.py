"""Header stat card for the crypto main window.

A third card of this shape beside ``widgets.StatCard``. It subclasses
``QFrame`` directly rather than that card, so neither one carries the
other's skin.
"""

from __future__ import annotations

from typing import Optional

from ...core.privacy_mask_registry import mask_or

from .. import design_system as ds

try:
    from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtGui import QMouseEvent

    from .privacy_dot import PrivacyDot

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    # ---------------------------------------------------------------
    # Stat Card — vertical (label-on-top) layout for large-number safety
    # ---------------------------------------------------------------
    # v3.15.54 — operator directive 2026-04-25: "Labels should be above
    # the numbers. The scrum and fold fields are not going to do well
    # with large numbers with this letter size and arrangement."
    #
    # Switched from QHBoxLayout to QVBoxLayout: small dim label on top,
    # large heading value below. Value label gets enough horizontal
    # room to render multi-comma USD like "$1,234,567.89" without
    # truncation; vertical stacking keeps the card narrow so all five
    # cards still fit in one row at typical widths.
    class StatCard(QFrame):
        # v3.16.52 — emit `clicked` when the card is left-clicked. Cards
        # opt into clickability by connecting this signal; default behavior
        # is unchanged (regular cards stay non-interactive).
        clicked = Signal()

        def __init__(self, label: str, value: str = "---", parent=None):
            super().__init__(parent)
            self.setFrameShape(QFrame.StyledPanel)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(8, 4, 8, 4)
            layout.setSpacing(2)
            # v3.23.7 — label sits in an HBox for horizontal centering.
            # v3.23.23 — privacy dot no longer inserted here; it now
            # attaches BELOW the value in the outer VBox to match the
            # SpendableProfitsWidget layout. The HBox stays as-is for
            # the label centering it already provides.
            self._label_row = QHBoxLayout()
            self._label_row.setContentsMargins(0, 0, 0, 0)
            self._label_row.setSpacing(4)
            self._label = QLabel(label)
            self._label.setProperty("muted", True)
            self._label.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            self._label.setStyleSheet(f"font-size: 10px; color: {ds.MAIN_CAPTION};")
            self._label_row.addStretch()
            self._label_row.addWidget(self._label)
            # v3.23.7 — privacy dot slot, populated by attach_privacy_dot.
            self._privacy_dot: Optional[PrivacyDot] = None
            self._privacy_field_id: Optional[str] = None
            self._label_row.addStretch()
            self._value = QLabel(value)
            self._value.setProperty("heading", True)
            self._value.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
            # Value sized down a notch from heading default so wide
            # USD numbers don't blow the card width. The header strip
            # still grows the card horizontally as needed thanks to
            # the parent QHBoxLayout `stretch=1` on each card, but we
            # keep the typography readable.
            self._value.setStyleSheet(
                f"font-size: 14px; font-weight: bold; color: {ds.PRIMARY};"
            )
            layout.addLayout(self._label_row)
            layout.addWidget(self._value)
            # v3.23.7 — last raw (unmasked) value so a dot-toggle can
            # re-render immediately. set_value() updates it.
            self._raw_value: str = value
            # v3.16.52 — clickability state. Off by default; cards opt
            # in via set_clickable(True). Toggling pointer cursor is
            # the visual affordance.
            self._is_clickable = False

        def set_value(self, value: str) -> None:
            """Set the displayed value. If this card has a privacy dot
            attached, the value passes through mask_or() so the mask
            takes effect on the next set."""
            self._raw_value = str(value)
            if self._privacy_field_id:
                self._value.setText(mask_or(self._raw_value, self._privacy_field_id))
            else:
                self._value.setText(self._raw_value)

        def attach_privacy_dot(self, field_id: str) -> "PrivacyDot":
            """Wire a privacy dot to this card. The dot lives BELOW the
            value (outer VBox index 2, center-aligned) so its position
            matches SpendableProfitsWidget's dot placement — the top row
            of KPI cards presents a uniform "label / value / dot" column
            for every card. Toggling ``field_id`` re-renders this card's
            value automatically so masking takes effect immediately.

            v3.23.7  original: dot in label_row HBox next to label (top).
            v3.23.23 operator directive 2026-07-25: unify with
                     SpendableProfitsWidget — dot below the value."""
            if self._privacy_dot is not None:
                return self._privacy_dot
            self._privacy_field_id = field_id

            def _on_toggle():
                # Re-apply mask_or to the last raw value
                if self._privacy_field_id:
                    self._value.setText(
                        mask_or(self._raw_value, self._privacy_field_id)
                    )

            dot = PrivacyDot(field_id, on_toggle=_on_toggle)
            # v3.23.23 — dot goes BELOW the value in the outer VBox,
            # center-aligned, matching SpendableProfitsWidget's layout.
            self.layout().addWidget(dot, alignment=Qt.AlignHCenter)
            self._privacy_dot = dot
            # Render once with current mask state
            _on_toggle()
            return dot

        def refresh_privacy_dot(self) -> None:
            """v3.23.7 — called by the global Privacy Mode button after
            set_all() so the dot color + the displayed value reflect
            the new state without waiting for the next dashboard tick."""
            if self._privacy_dot is not None:
                self._privacy_dot.refresh()
            if self._privacy_field_id:
                self._value.setText(mask_or(self._raw_value, self._privacy_field_id))

        def set_clickable(self, clickable: bool, tooltip_suffix: str = "") -> None:
            """v3.16.52 — opt this card into click handling.
            When True, pointer cursor + tooltip suffix indicate it's
            actionable; the `clicked` signal fires on left-click release.
            """
            self._is_clickable = bool(clickable)
            if self._is_clickable:
                self.setCursor(Qt.PointingHandCursor)
                if tooltip_suffix:
                    base = self.toolTip() or ""
                    if tooltip_suffix not in base:
                        self.setToolTip((base + "\n\n" + tooltip_suffix).strip())
            else:
                self.unsetCursor()

        def mousePressEvent(self, event: QMouseEvent) -> None:
            # v3.16.52 — emit clicked on LMB press when the card opted
            # in. Always call super() to preserve default Qt behavior.
            #
            # 2026-08-13: the parameter was untyped and carried an
            # inline override suppression that mypy reported as UNUSED
            # on the live tree — a directive standing guard over an
            # error that does not exist, which is the shape the
            # operator's standing rule warns about. Annotating to the base
            # signature (QFrame.mousePressEvent) removes the need for it
            # in both directions: there is now no override mismatch to
            # suppress, and none can appear if the Qt stubs later
            # resolve. Behaviour is unchanged; the getattr guard below
            # stays because tests hand this method event doubles.
            if (
                self._is_clickable
                and getattr(event, "button", lambda: None)() == Qt.LeftButton
            ):
                self.clicked.emit()
            super().mousePressEvent(event)
