"""
analytics_tab.py — Performance Analytics Dashboard tab.

Shows equity curve, portfolio summary, per-bot performance table,
timeframe comparison, and key metrics (Sharpe, profit factor, etc).
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger("acervator.gui")

try:
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
        QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
        QPushButton, QGroupBox, QSplitter, QScrollArea,
    )
    from PySide6.QtCore import Qt, QTimer, QPointF
    from PySide6.QtGui import QPainter, QColor, QPen, QLinearGradient, QFont, QPolygonF
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

if _HAS_QT:

    class MetricCard(QFrame):
        """Small card showing a single metric."""
        def __init__(self, label: str, value: str = "---", parent=None):
            super().__init__(parent)
            self.setAccessibleName("Metric Card")
            self.setFrameShape(QFrame.StyledPanel)
            self.setStyleSheet(
                "MetricCard { background: #12121f; border: 1px solid #2a2a3f; "
                "border-radius: 6px; }")
            layout = QVBoxLayout(self)
            layout.setContentsMargins(10, 8, 10, 8)
            layout.setSpacing(2)
            self._label = QLabel(label)
            self._label.setStyleSheet("color: #888; font-size: 10px;")
            self._value = QLabel(value)
            self._value.setStyleSheet("color: #e0e0f0; font-size: 16px; font-weight: bold;")
            layout.addWidget(self._label)
            layout.addWidget(self._value)

        def set_value(self, value: str, color: str = "#e0e0f0"):
            self._value.setText(value)
            self._value.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: bold;")

    class MiniEquityChart(QWidget):
        """Simple painted equity curve chart."""
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setAccessibleName("Mini Equity Chart")
            self._data: list[dict] = []
            self.setMinimumHeight(200)

        def set_data(self, equity_points: list[dict]):
            self._data = equity_points
            self.update()

        def paintEvent(self, event):
            if not self._data or len(self._data) < 2:
                p = QPainter(self)
                p.fillRect(self.rect(), QColor("#0a0a12"))
                p.setPen(QColor("#555"))
                p.drawText(self.rect(), Qt.AlignCenter, "Collecting equity data...")
                p.end()
                return

            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            w, h = self.width(), self.height()
            margin = 40

            # Background
            p.fillRect(self.rect(), QColor("#0a0a12"))

            equities = [d["equity"] for d in self._data]
            times = [d["timestamp"] for d in self._data]
            min_eq = min(equities) * 0.998
            max_eq = max(equities) * 1.002
            eq_range = max_eq - min_eq or 1
            t_range = times[-1] - times[0] or 1

            # Grid lines
            p.setPen(QPen(QColor("#1a1a2e"), 1))
            for i in range(5):
                y = margin + (h - 2 * margin) * i / 4
                p.drawLine(margin, int(y), w - margin, int(y))

            # Equity curve with gradient fill
            points = []
            for i, d in enumerate(self._data):
                x = margin + (d["timestamp"] - times[0]) / t_range * (w - 2 * margin)
                y = margin + (1 - (d["equity"] - min_eq) / eq_range) * (h - 2 * margin)
                points.append((int(x), int(y)))

            # Fill under curve
            if points:
                grad = QLinearGradient(0, margin, 0, h - margin)
                if equities[-1] >= equities[0]:
                    grad.setColorAt(0, QColor(0, 255, 136, 40))
                    grad.setColorAt(1, QColor(0, 255, 136, 5))
                    line_color = QColor("#00ff88")
                else:
                    grad.setColorAt(0, QColor(255, 51, 102, 40))
                    grad.setColorAt(1, QColor(255, 51, 102, 5))
                    line_color = QColor("#ff3366")

                poly = QPolygonF()
                for x, y in points:
                    poly.append(QPointF(x, y))
                poly.append(QPointF(points[-1][0], h - margin))
                poly.append(QPointF(points[0][0], h - margin))
                p.setBrush(grad)
                p.setPen(Qt.NoPen)
                p.drawPolygon(poly)

                # Line
                p.setPen(QPen(line_color, 2))
                for i in range(len(points) - 1):
                    p.drawLine(points[i][0], points[i][1],
                              points[i + 1][0], points[i + 1][1])

            # Current value label
            if equities:
                p.setPen(QColor("#e0e0f0"))
                p.setFont(QFont("Consolas", 9))
                p.drawText(margin + 5, margin + 15, f"${equities[-1]:,.2f}")
                p.setPen(QColor("#666"))
                p.drawText(margin + 5, h - margin - 5, f"${min_eq:,.2f}")

            p.end()

    class AnalyticsTab(QWidget):
        """Performance Analytics Dashboard."""

        def __init__(self, analytics_engine=None, parent=None):
            super().__init__(parent)
            self.setAccessibleName("Analytics Tab")
            self._analytics = analytics_engine
            self._setup_ui()

        def _setup_ui(self):
            layout = QVBoxLayout(self)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(8)

            # Header row with metric cards
            metrics_row = QHBoxLayout()
            self._card_pnl = MetricCard("Total P/L")
            self._card_winrate = MetricCard("Win Rate")
            self._card_sharpe = MetricCard("Sharpe Ratio")
            self._card_pf = MetricCard("Profit Factor")
            self._card_trades = MetricCard("Total Trades")
            self._card_dd = MetricCard("Max Drawdown")
            self._card_expect = MetricCard("Expectancy")
            self._card_today = MetricCard("Trades Today")

            for card in [self._card_pnl, self._card_winrate, self._card_sharpe,
                         self._card_pf, self._card_trades, self._card_dd,
                         self._card_expect, self._card_today]:
                metrics_row.addWidget(card)
            layout.addLayout(metrics_row)

            # Main content: equity chart + bot table
            splitter = QSplitter(Qt.Vertical)
            splitter.setHandleWidth(5)
            splitter.setChildrenCollapsible(False)

            # Equity curve
            chart_group = QGroupBox("Equity Curve")
            chart_group.setStyleSheet(
                "QGroupBox { background: #0a0a12; border: 1px solid #2a2a3f; "
                "border-radius: 6px; color: #00ffcc; font-weight: bold; }")
            chart_layout = QVBoxLayout(chart_group)
            self._equity_chart = MiniEquityChart()
            chart_layout.addWidget(self._equity_chart)
            splitter.addWidget(chart_group)

            # Bottom: bot performance table + timeframe comparison
            bottom = QSplitter(Qt.Horizontal)
            bottom.setHandleWidth(5)
            bottom.setChildrenCollapsible(False)

            # Per-bot performance table
            bot_group = QGroupBox("Bot Performance")
            bot_group.setStyleSheet(
                "QGroupBox { background: #0a0a12; border: 1px solid #2a2a3f; "
                "border-radius: 6px; color: #00ffcc; }")
            bot_layout = QVBoxLayout(bot_group)

            self._bot_table = QTableWidget()
            self._bot_table.setColumnCount(10)
            self._bot_table.setHorizontalHeaderLabels([
                "Bot", "Symbol", "Trades", "Win%", "P/L",
                "Profit Factor", "Sharpe", "Max DD%", "Avg Hold", "$/Trade"])
            self._bot_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            self._bot_table.setAlternatingRowColors(True)
            self._bot_table.setSelectionBehavior(QTableWidget.SelectRows)
            self._bot_table.setEditTriggers(QTableWidget.NoEditTriggers)
            self._bot_table.verticalHeader().setVisible(False)
            bot_layout.addWidget(self._bot_table)
            bottom.addWidget(bot_group)

            # Timeframe comparison
            tf_group = QGroupBox("Timeframe Performance")
            tf_group.setStyleSheet(
                "QGroupBox { background: #0a0a12; border: 1px solid #2a2a3f; "
                "border-radius: 6px; color: #00ffcc; }")
            tf_layout = QVBoxLayout(tf_group)

            self._tf_table = QTableWidget()
            self._tf_table.setColumnCount(4)
            self._tf_table.setHorizontalHeaderLabels([
                "Timeframe", "Trades", "Win Rate", "Total P/L"])
            self._tf_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            self._tf_table.setAlternatingRowColors(True)
            self._tf_table.setEditTriggers(QTableWidget.NoEditTriggers)
            self._tf_table.verticalHeader().setVisible(False)
            tf_layout.addWidget(self._tf_table)
            bottom.addWidget(tf_group)

            bottom.setSizes([600, 300])
            splitter.addWidget(bottom)
            splitter.setSizes([250, 350])
            layout.addWidget(splitter)

        def refresh(self, analytics_engine=None):
            """Refresh all analytics displays."""
            eng = analytics_engine or self._analytics
            if not eng:
                return

            # Summary cards
            summary = eng.get_portfolio_summary()
            pnl = summary.get("total_pnl", 0)
            pnl_color = "#00ff88" if pnl >= 0 else "#ff3366"
            self._card_pnl.set_value(f"${pnl:+,.4f}", pnl_color)
            self._card_winrate.set_value(f"{summary.get('win_rate', 0):.1f}%")
            self._card_sharpe.set_value(f"{summary.get('sharpe_ratio', 0):.2f}")
            pf = summary.get("profit_factor", 0)
            pf_str = f"{pf:.2f}" if pf != float('inf') else "∞"
            self._card_pf.set_value(pf_str)
            self._card_trades.set_value(str(summary.get("total_trades", 0)))
            self._card_dd.set_value(f"{summary.get('max_drawdown', 0):.1f}%", "#ffaa00")
            self._card_expect.set_value(f"${summary.get('expectancy', 0):+,.4f}")
            self._card_today.set_value(str(summary.get("trades_today", 0)))

            # Equity curve
            curve = eng.get_equity_curve(hours=24)
            self._equity_chart.set_data(curve)

            # Bot performance table
            perfs = eng.get_bot_performance()
            self._bot_table.setRowCount(len(perfs))
            for row, perf in enumerate(perfs):
                items = [
                    perf.bot_id[:8],
                    perf.symbol,
                    str(perf.total_trades),
                    f"{perf.win_rate:.1f}%",
                    f"${perf.total_pnl:+,.4f}",
                    f"{perf.profit_factor:.2f}" if perf.profit_factor != float('inf') else "∞",
                    f"{perf.sharpe_ratio:.2f}",
                    f"{perf.max_drawdown_pct:.1f}%",
                    eng._format_duration(perf.avg_hold_seconds),
                    f"${perf.expectancy:+,.4f}",
                ]
                for col, text in enumerate(items):
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignCenter)
                    if col == 4:  # P/L column
                        color = QColor("#00ff88") if perf.total_pnl >= 0 else QColor("#ff3366")
                        item.setForeground(color)
                    self._bot_table.setItem(row, col, item)

            # Timeframe comparison
            tf_data = eng.get_timeframe_comparison()
            self._tf_table.setRowCount(len(tf_data))
            for row, (tf, stats) in enumerate(sorted(tf_data.items())):
                items = [
                    tf,
                    str(stats["total_trades"]),
                    f"{stats['win_rate']:.1f}%",
                    f"${stats['total_pnl']:+,.4f}",
                ]
                for col, text in enumerate(items):
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignCenter)
                    self._tf_table.setItem(row, col, item)
