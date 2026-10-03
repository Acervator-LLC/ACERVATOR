"""The one way a control carries a mouse-over description, and the wait before its box.

``set_description`` sets the text a control shows when the pointer rests
on it. ``WakeDelayStyle`` answers ``SH_ToolTip_WakeUpDelay`` with
``TOOLTIP_DELAY_MS`` and hands every other hint to the style it wraps,
and ``install`` puts it on the application. ``src.gui.theme_engine``
holds ``TOOLTIP_MAX_WIDTH_PX``, the width the box wraps at.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle, QWidget

__all__ = ["TOOLTIP_DELAY_MS", "WakeDelayStyle", "install", "set_description"]

#: Milliseconds the pointer must rest UNMOVED before Qt draws a description;
#: Qt restarts this wait on every pointer move, however small.
TOOLTIP_DELAY_MS = 1000


def set_description(widget: QWidget, text: str) -> None:
    """Sets ``text`` as the description ``widget`` shows under the pointer."""
    widget.setToolTip(text)


class WakeDelayStyle(QProxyStyle):
    """Answers ``SH_ToolTip_WakeUpDelay`` with ``TOOLTIP_DELAY_MS``."""

    def styleHint(  # noqa: N802
        self,
        hint: QStyle.StyleHint,
        option: Optional[Any] = None,
        widget: Optional[QWidget] = None,
        returnData: Optional[Any] = None,  # noqa: N803
    ) -> int:
        """Returns ``TOOLTIP_DELAY_MS`` for the wake hint and defers the rest."""
        if hint == QStyle.StyleHint.SH_ToolTip_WakeUpDelay:
            return TOOLTIP_DELAY_MS
        return int(super().styleHint(hint, option, widget, returnData))


def install(app: QApplication) -> None:
    """Puts ``WakeDelayStyle`` on ``app`` so every description waits ``TOOLTIP_DELAY_MS``."""
    app.setStyle(WakeDelayStyle())
