"""The Read Rate drop-down every Live, Paper and Simulator settings page and wizard draws."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox

from ..exchange.timeframes import read_timeframe, read_timeframes


def fill_read_combo(
    combo: QComboBox, exchange_id: str, ta_timeframe: str, chosen: str
) -> None:
    """Fill ``combo`` with ``read_timeframes(exchange_id, ta_timeframe)`` and select ``read_timeframe`` of ``chosen``."""
    combo.blockSignals(True)
    combo.clear()
    for timeframe in read_timeframes(exchange_id, ta_timeframe):
        combo.addItem(timeframe, timeframe)
    combo.setCurrentIndex(
        combo.findData(read_timeframe(exchange_id, ta_timeframe, chosen))
    )
    combo.blockSignals(False)
