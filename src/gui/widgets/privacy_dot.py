"""Per-field reveal toggle backed by the process privacy-mask registry."""

from __future__ import annotations

import logging

from ...core.privacy_mask_registry import get_privacy_mask_registry

from .. import design_system as ds

logger = logging.getLogger("acervator.gui.privacy_dot")

try:
    from PySide6.QtWidgets import QPushButton
    from PySide6.QtCore import Qt

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    class PrivacyDot(QPushButton):
        """Clickable dot toggling one ``field_id`` in the privacy-mask registry.

        ``refresh`` paints ● for revealed and ○ for masked, and ``on_toggle``
        is called after the registry write so the parent can re-render.
        """

        def __init__(self, field_id: str, on_toggle=None, parent=None):
            super().__init__(parent)
            self._field_id = field_id
            self._on_toggle = on_toggle
            # No setFixedSize: the glyph sizes to its own text metrics.
            self.setFlat(True)
            self.setFocusPolicy(Qt.NoFocus)
            self.setCursor(Qt.PointingHandCursor)
            self.clicked.connect(self._on_click)
            self.refresh()

        def field_id(self) -> str:
            return self._field_id

        def _on_click(self):
            try:
                reg = get_privacy_mask_registry()
                reg.set_masked(self._field_id, not reg.is_masked(self._field_id))
            except Exception as exc:
                logger.debug("privacy toggle failed for %s: %s", self._field_id, exc)
            self.refresh()
            if callable(self._on_toggle):
                try:
                    self._on_toggle()
                except Exception as exc:
                    logger.debug("on_toggle failed for %s: %s", self._field_id, exc)

        def refresh(self) -> None:
            """Repaint the dot and its tooltip from current registry state.

            The glyph is ● when revealed and ○ when masked, in
            ``ds.PRIMARY_BRIGHT`` on a transparent flat button.
            """
            try:
                masked = get_privacy_mask_registry().is_masked(self._field_id)
            except Exception:
                masked = False
            if masked:
                glyph = "○"
                tip = f"{self._field_id}: MASKED. " "Click to reveal."
            else:
                glyph = "●"
                tip = f"{self._field_id}: REVEALED. " "Click to mask."
            self.setText(glyph)
            self.setStyleSheet(
                "PrivacyDot { "
                f"  color: {ds.PRIMARY_BRIGHT}; "
                "  background: transparent; "
                "  border: none; "
                "  padding: 0 4px; "
                "  font-size: 14px; "
                "} "
                f"PrivacyDot:hover {{ color: {ds.TEXT_MAX}; }}"
            )
            self.setToolTip(tip)
