"""
launcher.py — Application launcher hub.

Presents two trading modes: Crypto and Stocks.
Each opens its own MainWindow. Both can run simultaneously.
"""

from __future__ import annotations

import logging

from .main_tabs.launcher_surface import crypto_features

logger = logging.getLogger("acervator.gui")

try:
    from PySide6.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QFrame,
        QGraphicsDropShadowEffect,
    )
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtGui import QColor, QPainter, QLinearGradient

    _HAS_QT = True
except ImportError:
    _HAS_QT = False

if _HAS_QT:

    class ModeCard(QFrame):
        """Large clickable card for a trading mode."""

        clicked = Signal()

        def __init__(
            self,
            title: str,
            subtitle: str,
            icon_char: str,
            color: str,
            features: list[str],
            parent=None,
        ):
            super().__init__(parent)
            self.setAccessibleName("Mode Card")
            self._color = color
            self._hovered = False
            self.setCursor(Qt.PointingHandCursor)
            self.setFixedSize(380, 420)
            self.setStyleSheet(
                f"ModeCard {{ background: #0e0e1a; border: 2px solid #1a1a2f; "
                f"border-radius: 16px; }}"
                f"ModeCard:hover {{ border-color: {color}; }}"
            )

            layout = QVBoxLayout(self)
            layout.setContentsMargins(30, 30, 30, 30)
            layout.setSpacing(12)

            # Icon
            icon = QLabel(icon_char)
            icon.setAlignment(Qt.AlignCenter)
            icon.setStyleSheet(f"font-size: 64px; color: {color};")
            layout.addWidget(icon)

            # Title
            title_lbl = QLabel(title)
            title_lbl.setAlignment(Qt.AlignCenter)
            title_lbl.setStyleSheet(
                f"font-size: 24px; font-weight: bold; color: {color};"
            )
            layout.addWidget(title_lbl)

            # Subtitle
            sub_lbl = QLabel(subtitle)
            sub_lbl.setAlignment(Qt.AlignCenter)
            sub_lbl.setStyleSheet("font-size: 12px; color: #888;")
            sub_lbl.setWordWrap(True)
            layout.addWidget(sub_lbl)

            layout.addSpacing(10)

            # Features list
            for feat in features:
                feat_lbl = QLabel(f"  {feat}")
                feat_lbl.setStyleSheet("font-size: 11px; color: #aaa;")
                layout.addWidget(feat_lbl)

            layout.addStretch()

            # Launch button
            btn = QPushButton(f"Launch {title}")
            btn.setStyleSheet(
                f"QPushButton {{ background: {color}; color: #0a0a12; "
                f"border: none; border-radius: 8px; padding: 12px; "
                f"font-size: 14px; font-weight: bold; }}"
                f"QPushButton:hover {{ background: {color}cc; }}"
            )
            btn.clicked.connect(self.clicked.emit)
            layout.addWidget(btn)

            # Shadow effect
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(30)
            shadow.setColor(QColor(color))
            shadow.setOffset(0, 0)
            self.setGraphicsEffect(shadow)

        def mousePressEvent(self, _event):
            self.clicked.emit()

    class LauncherWindow(QWidget):
        """
        Application launcher — choose between Crypto and Stock trading.
        """

        crypto_selected = Signal()
        stocks_selected = Signal()

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setAccessibleName("Launcher Window")
            self.setWindowTitle("Acervator")
            self.setFixedSize(900, 560)
            self.setStyleSheet("background: #08080f;")

            layout = QVBoxLayout(self)
            layout.setContentsMargins(40, 30, 40, 30)
            layout.setSpacing(20)

            # Title
            title = QLabel("QUANTUM AUTO TRADER")
            title.setAlignment(Qt.AlignCenter)
            title.setStyleSheet(
                "font-size: 28px; font-weight: bold; color: #e0e0f0; "
                "letter-spacing: 4px;"
            )
            layout.addWidget(title)

            version_lbl = QLabel("Select Trading Mode")
            version_lbl.setAlignment(Qt.AlignCenter)
            version_lbl.setStyleSheet("font-size: 13px; color: #666;")
            layout.addWidget(version_lbl)

            layout.addSpacing(10)

            # Cards row
            cards = QHBoxLayout()
            cards.setSpacing(40)

            # Crypto card
            crypto_card = ModeCard(
                title="Crypto Trading",
                subtitle="Multi-exchange cryptocurrency trading with "
                "Grid and Scrumming bots",
                icon_char="\u20bf",  # ₿
                color="#00ffcc",
                features=list(crypto_features()),
            )
            crypto_card.clicked.connect(self.crypto_selected.emit)
            cards.addWidget(crypto_card)

            # Stocks card
            stocks_card = ModeCard(
                title="Stock Trading",
                subtitle="Equity trading via TradingView signals "
                "with broker integration",
                icon_char="\u2191",  # ↑
                color="#00aaff",
                features=[
                    "TradingView Webhook Signals",
                    "Alpaca Broker Integration",
                    "Signal, DCA, Swing & Grid Bots",
                    "Market Hours Awareness",
                    "Paper Trading Support",
                    "Stop-Loss & Take-Profit",
                ],
            )
            stocks_card.clicked.connect(self.stocks_selected.emit)
            cards.addWidget(stocks_card)

            layout.addLayout(cards)

            # Footer
            footer = QLabel(
                "Both modes can run simultaneously  •  "
                "Shared analytics, risk management, and notifications"
            )
            footer.setAlignment(Qt.AlignCenter)
            footer.setStyleSheet("font-size: 11px; color: #555;")
            layout.addWidget(footer)

        def paintEvent(self, _event):
            """Draw subtle gradient background."""
            p = QPainter(self)
            grad = QLinearGradient(0, 0, 0, self.height())
            grad.setColorAt(0, QColor("#0a0a14"))
            grad.setColorAt(0.5, QColor("#08081a"))
            grad.setColorAt(1, QColor("#060612"))
            p.fillRect(self.rect(), grad)
            p.end()
