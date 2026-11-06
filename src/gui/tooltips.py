"""The one way a control carries a mouse-over description, and the wait before its box.

``set_description`` sets the text a control shows when the pointer rests
on it, and ``DESCRIPTION_WORD_LIMIT`` is the length it holds that text to.
``WakeDelayStyle`` answers ``SH_ToolTip_WakeUpDelay`` with
``TOOLTIP_DELAY_MS`` and hands every other hint to the style it wraps,
and ``install`` puts it on the application. ``src.gui.theme_engine``
holds ``TOOLTIP_DELAY_MS`` beside the three size figures every
``QToolTip`` rule reads, so one declaration carries the wait and the box.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Union

from PySide6.QtWidgets import (
    QApplication,
    QProxyStyle,
    QStyle,
    QTableWidgetItem,
    QTreeWidgetItem,
    QWidget,
)

from .descriptions import DESCRIPTION_WORD_LIMIT
from .theme_engine import TOOLTIP_DELAY_MS

logger = logging.getLogger("acervator.gui")

__all__ = [
    "DESCRIPTION_WORD_LIMIT",
    "TOOLTIP_DELAY_MS",
    "WakeDelayStyle",
    "install",
    "set_description",
    "word_count",
]

Describable = Union[QWidget, QTableWidgetItem, QTreeWidgetItem]
"""The three things on a screen that carry a description of their own."""


def word_count(text: str) -> int:
    """Returns the words in ``text``, counting a line break as a word break."""
    return len(str(text).replace("\n", " ").split())


def set_description(
    widget: Describable, text: str, column: Optional[int] = None
) -> None:
    """Sets ``text`` as the description ``widget`` shows under the pointer.

    ``column`` names one column of a tree item, or one tab of a tab book; a
    ``text`` over ``DESCRIPTION_WORD_LIMIT`` words is still set and reaches ``logger``.
    """
    body = str(text)
    counted = word_count(body)
    if counted > DESCRIPTION_WORD_LIMIT:
        logger.warning(
            "description of %d words, limit %d: %.60s",
            counted,
            DESCRIPTION_WORD_LIMIT,
            body.replace("\n", " "),
        )
    tab_setter = getattr(widget, "setTabToolTip", None)
    if column is None:
        widget.setToolTip(body)
    elif callable(tab_setter):
        tab_setter(column, body)
    else:
        widget.setToolTip(column, body)


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
