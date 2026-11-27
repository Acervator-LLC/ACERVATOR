"""The Read Rate drop-down every Live, Paper and Simulator settings page and wizard draws."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox

from ..exchange.timeframes import read_timeframe, read_timeframes


def fill_read_combo(combo: QComboBox, ta_timeframe: str, chosen: str) -> None:
    """Fill ``combo`` with ``read_timeframes(ta_timeframe)`` and select ``read_timeframe`` of ``chosen``."""
    combo.blockSignals(True)
    combo.clear()
    for timeframe in read_timeframes(ta_timeframe):
        combo.addItem(timeframe, timeframe)
    combo.setCurrentIndex(combo.findData(read_timeframe(ta_timeframe, chosen)))
    combo.blockSignals(False)
