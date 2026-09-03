"""Read-only table of per-bot capital reservations."""

from __future__ import annotations

try:
    from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    class CapitalRegistryPanel(QTableWidget):
        """A read-only table drawing one row per reservation the
        registry reports."""

        _COLS = [
            "Bot ID",
            "Exchange",
            "Base",
            "Reserved USD",
            "Reserved Base",
            "Mode",
            "Last Rate USD/Base",
            "Initial USD",
            "Profit Δ",
        ]

        def __init__(self, parent=None):
            super().__init__(0, len(self._COLS), parent)
            self.setAccessibleName("Capital Registry Panel")
            self.setHorizontalHeaderLabels(self._COLS)
            self.setEditTriggers(QTableWidget.NoEditTriggers)
            self.setSelectionBehavior(QTableWidget.SelectRows)
            self.setAlternatingRowColors(True)
            self.verticalHeader().setVisible(False)
            self.horizontalHeader().setStretchLastSection(True)
            self._initial_usd_by_bot: dict[str, float] = {}

        def update_from_registry(self, registry) -> None:
            """Repopulate the table, recording no starting figure for a
            reservation the table refuses to format."""
            if registry is None:
                self.setRowCount(0)
                return
            try:
                reservations = registry.get_reservations()
            except Exception:
                self.setRowCount(0)
                return
            amounts = [float(one.reserved_usd) for one in reservations]
            self.setRowCount(len(reservations))
            for row, r in enumerate(reservations):
                amount = amounts[row]
                initial = self._initial_usd_by_bot.get(r.bot_id, amount)
                profit_delta = amount - initial
                values = [
                    r.bot_id,
                    r.exchange_id,
                    r.base_currency,
                    f"${r.reserved_usd:.2f}",
                    f"{r.reserved_base:.6f}",
                    r.bot_mode,
                    f"${r.last_rate_usd_per_base:.4f}",
                    f"${initial:.2f}",
                    f"${profit_delta:+.2f}",
                ]
                self._initial_usd_by_bot.setdefault(r.bot_id, amount)
                for col, v in enumerate(values):
                    self.setItem(row, col, QTableWidgetItem(str(v)))

        def clear_table(self) -> None:
            """Empty the table and forget every bot's starting figure."""
            self.setRowCount(0)
            self._initial_usd_by_bot.clear()
