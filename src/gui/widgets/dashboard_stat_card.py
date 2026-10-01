"""``StatCard``, the header stat card of the crypto main window.

``StatCard`` subclasses ``QFrame`` and carries no shared card skin.
``attach_privacy_dot`` makes ``set_value`` render through ``mask_or``.
"""

from __future__ import annotations

from typing import Optional

from ...core.privacy_mask_registry import mask_or

from .. import design_system as ds

try:
    from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtGui import QMouseEvent

    from .eliding_label import ElidingLabel
    from .privacy_dot import PrivacyDot

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    class StatCard(QFrame):
        # Emitted only while `set_clickable(True)` has armed the card.
        clicked = Signal()

        #: What the card leaves either side of its caption and its amount,
        #: matching ``header_strip_surface.CARD_SIDE_MARGIN_PX``.
        _SIDE_MARGIN_PX = 4

        def __init__(self, label: str, value: str = "---", parent=None):
            super().__init__(parent)
            self._setup_ui(label, value)

        def _setup_ui(self, label: str, value: str) -> None:
            """Build the caption, the amount and the dot slot under them."""
            self.setFrameShape(QFrame.StyledPanel)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(self._SIDE_MARGIN_PX, 4, self._SIDE_MARGIN_PX, 4)
            layout.setSpacing(2)
            self._label_row = QHBoxLayout()
            self._label_row.setContentsMargins(0, 0, 0, 0)
            self._label_row.setSpacing(4)
            self._label = ElidingLabel(label)
            self._label.setProperty("muted", True)
            self._label.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            self._label.setStyleSheet(
                f"color: {ds.MAIN_CAPTION}; font-size: 10px; font-weight: 600;"
            )
            self._label_row.addStretch()
            self._label_row.addWidget(self._label)
            self._privacy_dot: Optional[PrivacyDot] = None
            self._privacy_field_id: Optional[str] = None
            self._label_row.addStretch()
            self._value = ElidingLabel(value)
            self._value.setProperty("heading", True)
            self._value.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
            self._value.setStyleSheet(
                f"color: {ds.PRIMARY}; font-size: 14px; font-weight: bold;"
            )
            layout.addLayout(self._label_row)
            layout.addWidget(self._value)
            # The unmasked text `refresh_privacy_dot` re-renders from.
            self._raw_value: str = value
            self._is_clickable = False

        def set_value(self, value: str) -> None:
            """Show ``value`` and keep it in ``_raw_value``.

            A card holding a ``_privacy_field_id`` renders through
            ``mask_or``.
            """
            self._raw_value = str(value)
            if self._privacy_field_id:
                self._value.setText(mask_or(self._raw_value, self._privacy_field_id))
            else:
                self._value.setText(self._raw_value)

        def attach_privacy_dot(self, field_id: str) -> "PrivacyDot":
            """Add a ``PrivacyDot`` for ``field_id`` below the value, centred.

            Toggling it re-renders ``_raw_value`` through ``mask_or``; a
            second call returns the dot already attached.
            """
            if self._privacy_dot is not None:
                return self._privacy_dot
            self._privacy_field_id = field_id

            def _on_toggle():
                if self._privacy_field_id:
                    self._value.setText(
                        mask_or(self._raw_value, self._privacy_field_id)
                    )

            dot = PrivacyDot(field_id, on_toggle=_on_toggle)
            self.layout().addWidget(dot, alignment=Qt.AlignHCenter)
            self._privacy_dot = dot
            _on_toggle()
            return dot

        def refresh_privacy_dot(self) -> None:
            """Repaint the ``PrivacyDot`` and re-render the value.

            The text comes from ``_raw_value`` through ``mask_or``, not
            from a fresh dashboard tick.
            """
            if self._privacy_dot is not None:
                self._privacy_dot.refresh()
            if self._privacy_field_id:
                self._value.setText(mask_or(self._raw_value, self._privacy_field_id))

        def set_clickable(self, clickable: bool, tooltip_suffix: str = "") -> None:
            """Arm or disarm ``_is_clickable`` and set the pointer cursor.

            ``mousePressEvent`` emits ``clicked`` only while armed;
            ``tooltip_suffix`` is appended once.
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
            """Emit ``clicked`` on a left press while ``_is_clickable``.

            ``QFrame.mousePressEvent`` runs for every press either way.
            """
            if (
                self._is_clickable
                and getattr(event, "button", lambda: None)() == Qt.LeftButton
            ):
                self.clicked.emit()
            super().mousePressEvent(event)
