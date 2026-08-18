"""
risk_tab.py — Risk & Capital Management Dashboard tab.

Shows portfolio exposure, drawdown gauges, correlated asset warnings,
risk alerts history, and configurable risk rules.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger("acervator.gui")

try:
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
        QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
        QPushButton, QGroupBox, QSplitter, QDoubleSpinBox,
        QComboBox, QProgressBar,
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPainter, QColor, QPen, QFont  # v3.19.12 removed unused QConicalGradient
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

if _HAS_QT:

    class DrawdownGauge(QWidget):
        """Circular gauge showing current drawdown %."""
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setAccessibleName("Drawdown Gauge")
            self._value = 0.0
            self._max = 25.0
            self.setMinimumSize(160, 160)
            self.setMaximumSize(200, 200)

        def set_value(self, pct: float, max_pct: float = 25):
            self._value = pct
            self._max = max_pct
            self.update()

        def paintEvent(self, event):
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            size = min(self.width(), self.height())
            margin = 15
            rect_size = size - 2 * margin

            # Background arc
            p.setPen(QPen(QColor("#1a1a2e"), 8))
            p.drawArc(margin, margin, rect_size, rect_size, 225 * 16, -270 * 16)

            # Value arc
            ratio = min(self._value / self._max, 1.0)
            if ratio < 0.4:
                color = QColor("#00ff88")
            elif ratio < 0.7:
                color = QColor("#ffaa00")
            else:
                color = QColor("#ff3366")

            p.setPen(QPen(color, 8))
            span = int(-270 * ratio * 16)
            p.drawArc(margin, margin, rect_size, rect_size, 225 * 16, span)

            # Center text
            p.setPen(QColor("#e0e0f0"))
            p.setFont(QFont("Consolas", 18, QFont.Bold))
            p.drawText(self.rect(), Qt.AlignCenter, f"{self._value:.1f}%")

            # Label
            p.setPen(QColor("#888"))
            p.setFont(QFont("Consolas", 9))
            label_rect = self.rect().adjusted(0, size // 2 + 10, 0, 0)
            p.drawText(label_rect, Qt.AlignHCenter | Qt.AlignTop, "Drawdown")

            p.end()

    class ExposureBar(QFrame):
        """Horizontal bar showing exposure breakdown."""
        def __init__(self, label: str, parent=None):
            super().__init__(parent)
            self.setAccessibleName("Exposure Bar")
            layout = QHBoxLayout(self)
            layout.setContentsMargins(4, 2, 4, 2)
            self._label = QLabel(label)
            self._label.setMinimumWidth(80)
            self._label.setStyleSheet("color: #aaa; font-size: 11px;")
            self._bar = QProgressBar()
            self._bar.setRange(0, 100)
            self._bar.setTextVisible(True)
            self._bar.setStyleSheet(
                "QProgressBar { background: #1a1a2e; border: 1px solid #2a2a3f; "
                "border-radius: 3px; height: 18px; color: #e0e0f0; font-size: 10px; }"
                "QProgressBar::chunk { background: #00aaff; border-radius: 2px; }")
            self._value_label = QLabel("$0")
            self._value_label.setMinimumWidth(70)
            self._value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._value_label.setStyleSheet("color: #e0e0f0; font-size: 11px;")
            layout.addWidget(self._label)
            layout.addWidget(self._bar, stretch=1)
            layout.addWidget(self._value_label)

        def set_value(self, pct: float, amount: float, color: str = "#00aaff"):
            self._bar.setValue(int(min(pct, 100)))
            self._bar.setFormat(f"{pct:.1f}%")
            self._value_label.setText(f"${amount:,.0f}")
            self._bar.setStyleSheet(
                f"QProgressBar {{ background: #1a1a2e; border: 1px solid #2a2a3f; "
                f"border-radius: 3px; height: 18px; color: #e0e0f0; font-size: 10px; }}"
                f"QProgressBar::chunk {{ background: {color}; border-radius: 2px; }}")

    class RiskTab(QWidget):
        """Risk & Capital Management tab."""

        def __init__(self, risk_manager=None, parent=None):
            super().__init__(parent)
            self.setAccessibleName("Risk Tab")
            self._risk = risk_manager
            self._setup_ui()

        def _setup_ui(self):
            layout = QVBoxLayout(self)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(8)

            main_split = QSplitter(Qt.Horizontal)
            main_split.setHandleWidth(5)
            main_split.setChildrenCollapsible(False)

            # Left: gauges and exposure
            left = QWidget()
            left_layout = QVBoxLayout(left)
            left_layout.setContentsMargins(0, 0, 0, 0)

            # Drawdown gauge + key metrics
            gauge_row = QHBoxLayout()
            self._dd_gauge = DrawdownGauge()
            gauge_row.addWidget(self._dd_gauge)

            metrics = QVBoxLayout()
            self._lbl_peak = QLabel("Peak P/L: $0.00")
            self._lbl_peak.setStyleSheet("color: #00ff88; font-size: 13px;")
            self._lbl_exposure = QLabel("Total Exposure: $0.00")
            self._lbl_exposure.setStyleSheet("color: #e0e0f0; font-size: 13px;")
            self._lbl_bots = QLabel("Running Bots: 0")
            self._lbl_bots.setStyleSheet("color: #aaa; font-size: 12px;")
            self._lbl_status = QLabel("STATUS: MONITORING")
            self._lbl_status.setStyleSheet(
                "color: #00ffcc; font-size: 14px; font-weight: bold;")
            metrics.addWidget(self._lbl_status)
            metrics.addWidget(self._lbl_peak)
            metrics.addWidget(self._lbl_exposure)
            metrics.addWidget(self._lbl_bots)
            metrics.addStretch()
            gauge_row.addLayout(metrics, stretch=1)
            left_layout.addLayout(gauge_row)

            # Asset exposure bars
            asset_group = QGroupBox("Asset Exposure")
            asset_group.setStyleSheet(
                "QGroupBox { background: #0a0a12; border: 1px solid #2a2a3f; "
                "border-radius: 6px; color: #00ffcc; }")
            self._asset_layout = QVBoxLayout(asset_group)
            self._asset_bars: dict[str, ExposureBar] = {}
            left_layout.addWidget(asset_group)

            # Exchange exposure bars
            exch_group = QGroupBox("Exchange Exposure")
            exch_group.setStyleSheet(
                "QGroupBox { background: #0a0a12; border: 1px solid #2a2a3f; "
                "border-radius: 6px; color: #00ffcc; }")
            self._exch_layout = QVBoxLayout(exch_group)
            self._exch_bars: dict[str, ExposureBar] = {}
            left_layout.addWidget(exch_group)

            left_layout.addStretch()
            main_split.addWidget(left)

            # Right: alerts table + rules config
            right = QWidget()
            right_layout = QVBoxLayout(right)
            right_layout.setContentsMargins(0, 0, 0, 0)

            # Risk alerts table
            alerts_group = QGroupBox("Risk Alerts")
            alerts_group.setStyleSheet(
                "QGroupBox { background: #0a0a12; border: 1px solid #2a2a3f; "
                "border-radius: 6px; color: #00ffcc; }")
            alerts_layout = QVBoxLayout(alerts_group)

            self._alerts_table = QTableWidget()
            self._alerts_table.setColumnCount(5)
            self._alerts_table.setHorizontalHeaderLabels([
                "Time", "Severity", "Rule", "Message", "Action"])
            self._alerts_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            self._alerts_table.setAlternatingRowColors(True)
            self._alerts_table.setEditTriggers(QTableWidget.NoEditTriggers)
            self._alerts_table.verticalHeader().setVisible(False)
            alerts_layout.addWidget(self._alerts_table)
            right_layout.addWidget(alerts_group, stretch=2)

            # Rules configuration
            rules_group = QGroupBox("Risk Rules")
            rules_group.setStyleSheet(
                "QGroupBox { background: #0a0a12; border: 1px solid #2a2a3f; "
                "border-radius: 6px; color: #00ffcc; }")
            rules_layout = QVBoxLayout(rules_group)

            self._rules_table = QTableWidget()
            self._rules_table.setColumnCount(4)
            self._rules_table.setHorizontalHeaderLabels([
                "Rule", "Threshold", "Action", "Enabled"])
            self._rules_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            self._rules_table.setAlternatingRowColors(True)
            self._rules_table.verticalHeader().setVisible(False)
            rules_layout.addWidget(self._rules_table)
            right_layout.addWidget(rules_group, stretch=1)

            main_split.addWidget(right)
            main_split.setSizes([400, 500])
            layout.addWidget(main_split)

        def refresh(self, risk_manager=None):
            """Refresh risk dashboard."""
            rm = risk_manager or self._risk
            if not rm:
                return

            status = rm.get_status()

            # Drawdown gauge
            dd = status.get("drawdown_pct", 0)
            self._dd_gauge.set_value(dd)

            # Key metrics
            self._lbl_peak.setText(f"Peak P/L: ${status.get('peak_pnl', 0):,.4f}")
            self._lbl_exposure.setText(
                f"Total Exposure: ${status.get('total_exposure', 0):,.2f}")

            critical = status.get("critical_alerts", 0)
            if critical > 0:
                self._lbl_status.setText("STATUS: CRITICAL")
                self._lbl_status.setStyleSheet(
                    "color: #ff3366; font-size: 14px; font-weight: bold;")
            elif status.get("alerts_1h", 0) > 0:
                self._lbl_status.setText("STATUS: WARNING")
                self._lbl_status.setStyleSheet(
                    "color: #ffaa00; font-size: 14px; font-weight: bold;")
            else:
                self._lbl_status.setText("STATUS: MONITORING")
                self._lbl_status.setStyleSheet(
                    "color: #00ffcc; font-size: 14px; font-weight: bold;")

            # Update exposure bars from snapshots
            snapshots = rm.snapshots
            if snapshots:
                latest = snapshots[-1]
                self._lbl_bots.setText(f"Running Bots: {latest.running_count}")
                total = latest.total_exposure or 1

                # Asset bars
                for asset, amount in latest.asset_exposures.items():
                    pct = amount / total * 100
                    if asset not in self._asset_bars:
                        bar = ExposureBar(asset)
                        self._asset_bars[asset] = bar
                        self._asset_layout.addWidget(bar)
                    color = "#ff3366" if pct > 40 else "#ffaa00" if pct > 25 else "#00aaff"
                    self._asset_bars[asset].set_value(pct, amount, color)

                # Exchange bars
                for exch, amount in latest.exchange_exposures.items():
                    pct = amount / total * 100
                    if exch not in self._exch_bars:
                        bar = ExposureBar(exch.capitalize())
                        self._exch_bars[exch] = bar
                        self._exch_layout.addWidget(bar)
                    color = "#ff3366" if pct > 60 else "#ffaa00" if pct > 40 else "#00aaff"
                    self._exch_bars[exch].set_value(pct, amount, color)

            # Alerts table
            alerts = rm.alerts
            recent = [a for a in alerts if time.time() - a.timestamp < 86400]
            self._alerts_table.setRowCount(len(recent))
            for row, alert in enumerate(reversed(recent)):
                ts = time.strftime("%H:%M:%S", time.localtime(alert.timestamp))
                items = [
                    ts,
                    alert.severity.upper(),
                    alert.rule_name,
                    alert.message[:80],
                    alert.action_taken.value,
                ]
                for col, text in enumerate(items):
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignCenter)
                    if col == 1:
                        color = QColor("#ff3366") if alert.severity == "critical" else QColor("#ffaa00")
                        item.setForeground(color)
                    self._alerts_table.setItem(row, col, item)

            # Rules table
            rules = status.get("rules", {})
            self._rules_table.setRowCount(len(rules))
            for row, (name, rule) in enumerate(rules.items()):
                items = [
                    name.replace("_", " ").title(),
                    f"{rule['threshold']:.1f}",
                    rule["action"],
                    "Yes" if rule["enabled"] else "No",
                ]
                for col, text in enumerate(items):
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignCenter)
                    if col == 3:
                        color = QColor("#00ff88") if rule["enabled"] else QColor("#ff3366")
                        item.setForeground(color)
                    self._rules_table.setItem(row, col, item)
