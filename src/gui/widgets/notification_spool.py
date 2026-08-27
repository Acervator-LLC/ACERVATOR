"""Market and bot notification pane for the main window."""

from __future__ import annotations

from datetime import datetime

from .. import design_system as ds

try:
    from PySide6.QtWidgets import QTextEdit

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    # ---------------------------------------------------------------
    # Notification Spool - replaces All Bots Overview
    # ---------------------------------------------------------------
    # DPA: Q-001 exception — fixed 100px height caps visible content;
    # HTML formatting useful for notification styling.
    class NotificationSpool(QTextEdit):
        """Horizontal-style scrolling notification area for market status
        and bot events. Shows timestamped events in a compact format."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setAccessibleName("Notification Spool")
            self.setReadOnly(True)
            self.setMaximumHeight(100)
            self.setPlaceholderText("Market status and bot notifications...")

        def notify(self, message: str, level: str = "info") -> None:
            ts = datetime.now().strftime("%H:%M:%S")
            colors = {
                "info": ds.PRIMARY,
                "success": ds.SUCCESS,
                "warning": ds.WARNING,
                "error": ds.ERROR,
                "market": ds.STATE_MARKET,
            }
            color = colors.get(level, ds.TEXT_HIGH)
            self.append(
                f'<span style="color:{ds.TEXT_PLACEHOLDER}">{ts}</span> '
                f'<span style="color:{color}">{message}</span>'
            )
            self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
