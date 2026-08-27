"""Read-only table of per-bot capital reservations."""

from __future__ import annotations

try:
    from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    # ---------------------------------------------------------------
    # Spendable Profits Widget - compact single row
    # ---------------------------------------------------------------
    class CapitalRegistryPanel(QTableWidget):
        """v3.20.73 Phase D — operator-visible per-bot reservation table.

        Reads from `BotManager.capital_registry.get_reservations()`
        and renders one row per active reservation. Columns:
        Bot ID | Exchange | Base | Reserved USD | Reserved Base |
        Mode | Last Rate | Initial USD | Profit Δ.

        The "Profit Δ" column tracks `reserved_usd - initial_usd`,
        showing the operator how much of each bot's reservation came
        from initial allocation (v3.20.71 wizard) vs accumulated
        profit (v3.20.72 grow_reservation). Bots that haven't earned
        any profit show Δ = $0.00.

        Update cadence per locked Q1: every 5 minutes. The MainWindow
        wires a QTimer at 300000ms intervals. Manual refresh via
        operator-triggered method call (Phase D / v3.20.74+).

        MEM-419.
        """

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
            # Tracks each bot's initial USD reservation so the
            # Profit Δ column can compute reservation growth since
            # creation. Populated lazily as reservations appear.
            self._initial_usd_by_bot: dict[str, float] = {}

        def update_from_registry(self, registry) -> None:
            """Repopulate the table from the live CapitalRegistry.

            Idempotent — call as often as needed. The 5-min QTimer
            in MainWindow drives the periodic refresh; manual refresh
            calls are safe."""
            if registry is None:
                self.setRowCount(0)
                return
            try:
                reservations = registry.get_reservations()
            except (
                Exception
            ):  # R28-OK: GUI refresh best-effort; never crash on registry probe
                self.setRowCount(0)
                return
            # Capture initial USD for any new bot — first observation wins
            for r in reservations:
                if r.bot_id not in self._initial_usd_by_bot:
                    self._initial_usd_by_bot[r.bot_id] = float(r.reserved_usd)
            self.setRowCount(len(reservations))
            for row, r in enumerate(reservations):
                initial = self._initial_usd_by_bot.get(r.bot_id, float(r.reserved_usd))
                profit_delta = float(r.reserved_usd) - initial
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
                for col, v in enumerate(values):
                    self.setItem(row, col, QTableWidgetItem(str(v)))

        def clear_table(self) -> None:
            """Explicit clear — used by tests + on bot manager teardown."""
            self.setRowCount(0)
            self._initial_usd_by_bot.clear()
