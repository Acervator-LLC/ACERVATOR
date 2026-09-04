"""Per-field reveal toggle backed by the process privacy-mask registry."""

from __future__ import annotations

from ...core.privacy_mask_registry import get_privacy_mask_registry

from .. import design_system as ds

try:
    from PySide6.QtWidgets import QPushButton
    from PySide6.QtCore import Qt

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    # Privacy Mask Dot — clickable indicator per masked field (v3.23.7)
    # A small ~10×10px clickable dot widget that toggles the masked
    # state of a single field_id in the PrivacyMaskRegistry. Color
    # encodes state from the operator's point of view:
    #   RED   = field is REVEALED (visible). Click to mask.
    #   GRAY  = field is MASKED   (hidden).  Click to reveal.
    #
    # Operator directive (v3.23.7 spec Q7): "operator can see at a
    # glance which cells are masked." Red = open eye / visible; gray
    # = closed / hidden. The dot does NOT redraw on every refresh —
    # it only repaints when its own state changes or when a parent
    # widget calls refresh().
    #
    # Wiring: parent widgets pass a callable `on_toggle` that is
    # invoked AFTER the registry is updated. Typical callback re-runs
    # the parent's value-render path so the masked text reflows.
    class PrivacyDot(QPushButton):
        """Clickable dot toggling one field's privacy-mask state.

        v3.23.23 restyle (operator directive 2026-07-25): renders as a
        Unicode glyph (● revealed / ○ masked) in cyan #00FFEE on a
        transparent, flat button — matching the Bot Swarm dot
        (bot_visualizer.py:2154) and the Scrumming Bots column-header
        dot (main_window.py:1318). Prior styling was a 12px solid-blue
        square, which visibly diverged from the header/bot-swarm style.

        QPushButton subclass (rather than QLabel) preserves native
        click hit-testing + focus semantics.
        """

        def __init__(self, field_id: str, on_toggle=None, parent=None):
            super().__init__(parent)
            self._field_id = field_id
            self._on_toggle = on_toggle
            # v3.23.23 — no setFixedSize; let text sizing carry the
            # width so the glyph renders at natural text metrics.
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
            except (
                Exception
            ):  # R28-OK: GUI repaint never crashes on registry  # noqa: S110
                pass
            self.refresh()
            if callable(self._on_toggle):
                try:  # noqa: SIM105
                    self._on_toggle()
                except Exception:  # R28-OK  # noqa: S110
                    pass

        def refresh(self) -> None:
            """Repaint the dot from current registry state.

            v3.23.23 — Operator directive 2026-07-25: unify the dot
            style with the Bot Swarm dot (bot_visualizer.py:2154) and
            the Scrumming Bots column-header dot (this file:1318).
            Style spec:
              - Unicode glyph: ● (revealed) / ○ (masked)
              - Cyan text color #00FFEE (Acervator theme accent)
              - Transparent, borderless flat button
              - 14px font — matches header + bot-swarm sizing
            Prior v3.23.15 style (12px solid-blue square) is retired.
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
