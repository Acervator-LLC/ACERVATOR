"""
stock_main_window.py — Stock Trading Main Window.

Parallel to the crypto MainWindow but adapted for equity trading.
Includes: Dashboard, TradingView charts, stock bot management,
market hours display, webhook status, and all shared subsystems.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

logger = logging.getLogger("acervator.gui.stocks")

try:
    from PySide6.QtWidgets import (
        QMainWindow,
        QTabWidget,
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
        QHeaderView,
        QStatusBar,
        QSplitter,
        QGroupBox,
        QTextEdit,
        QLineEdit,
        QFormLayout,
        QSpinBox,
        QMessageBox,
    )
    from PySide6.QtCore import Qt, QTimer, Slot, Signal, QObject
    from PySide6.QtGui import QColor, QFont  # v3.19.12 removed unused QAction, QIcon

    from . import design_system as ds
    from .widgets import ColumnarTableWidget, ColumnSpec, STOCK_CARD, StatCard

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    # ---------------------------------------------------------------
    # Stat Card (reused from crypto window)
    # ---------------------------------------------------------------
    class StockStatCard(StatCard):
        """The stock window stat strip card. Skin: STOCK_CARD."""

        def __init__(self, label: str, value: str = "---", parent=None):
            super().__init__(label, value, parent=parent, style=STOCK_CARD)

    # ---------------------------------------------------------------
    # Stock Bot Table
    # ---------------------------------------------------------------
    STOCK_COLUMNS = ColumnSpec(
        labels=(
            "Bot ID",
            "Symbol",
            "Mode",
            "State",
            "Position",
            "Entry $",
            "Current $",
            "P/L",
            "Trades",
            "Signals",
        ),
        accessible_name="Stock Bot Table",
    )

    class StockBotTable(ColumnarTableWidget):
        COLUMN_SPEC = STOCK_COLUMNS
        COLUMNS = STOCK_COLUMNS.labels

        def __init__(self, parent=None):
            super().__init__(parent=parent)

        def update_bots(self, bot_statuses: list[dict]):
            self.setRowCount(len(bot_statuses))
            for row, status in enumerate(bot_statuses):
                stats = status.get("stats", {})
                pnl = stats.get("total_pnl", 0)
                items = [
                    status.get("bot_id", "")[:8],
                    status.get("symbol", ""),
                    status.get("mode", ""),
                    status.get("state", ""),
                    str(stats.get("current_position", 0)),
                    f"${stats.get('avg_entry_price', 0):.2f}",
                    f"${stats.get('current_price', 0):.2f}",
                    f"${pnl:+.2f}",
                    str(stats.get("total_trades", 0)),
                    str(stats.get("signals_received", 0)),
                ]
                for col, text in enumerate(items):
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignCenter)
                    if col == 7:  # P/L
                        color = (
                            QColor(ds.STOCK_POSITIVE)
                            if pnl >= 0
                            else QColor(ds.STOCK_NEGATIVE)
                        )
                        item.setForeground(color)
                    self.setItem(row, col, item)

    # ---------------------------------------------------------------
    # Stock Main Window
    # ---------------------------------------------------------------
    class StockMainWindow(QMainWindow):

        def __init__(
            self,
            stock_bot_manager=None,
            settings_manager=None,
            tv_bridge=None,
            risk_manager=None,
            analytics=None,
            notification_manager=None,
            journal=None,
            parent=None,
        ):
            super().__init__(parent)
            self.setAccessibleName("Stock Main Window")
            self.setWindowTitle("Acervator — Stock Trading")
            self.setMinimumSize(1400, 900)

            self._bot_manager = stock_bot_manager
            self._settings = settings_manager
            self._tv_bridge = tv_bridge
            self._risk_manager = risk_manager
            self._analytics = analytics
            self._notif_manager = notification_manager
            self._journal = journal

            # Market hours tracker
            from ..stocks.market_hours import MarketHours

            self._market_hours = MarketHours()

            self._setup_menu()
            self._setup_ui()
            self._setup_status_bar()
            self._setup_refresh_timer()

            logger.info("Stock Trading window initialized")

        def _setup_menu(self):
            menu_bar = self.menuBar()
            file_menu = menu_bar.addMenu("&File")
            file_menu.addAction("&Settings", self._open_settings)
            file_menu.addSeparator()
            file_menu.addAction("&Back to Launcher", self._back_to_launcher)
            file_menu.addAction("E&xit", self.close)

            help_menu = menu_bar.addMenu("&Help")
            help_menu.addAction("&About", self._show_about)

        def _setup_ui(self):
            central = QWidget()
            self.setCentralWidget(central)
            main_layout = QVBoxLayout(central)
            main_layout.setContentsMargins(16, 12, 16, 12)
            main_layout.setSpacing(10)

            # Market status bar
            market_bar = QHBoxLayout()
            self._market_status = QLabel("Market Status: Loading...")
            self._market_status.setStyleSheet(
                f"color: {ds.STATUS_INFO}; font-size: 13px; font-weight: bold; "
                f"padding: 4px 12px; background: {ds.CARD_STOCK_PANEL}; "
                f"border-radius: 4px; border: 1px solid {ds.CARD_STOCK_BORDER};"
            )
            market_bar.addWidget(self._market_status)
            market_bar.addStretch()

            self._webhook_status = QLabel("Webhook: Inactive")
            self._webhook_status.setStyleSheet(
                f"color: {ds.CARD_METRIC_LABEL}; font-size: 11px; padding: 4px 8px;"
            )
            market_bar.addWidget(self._webhook_status)
            main_layout.addLayout(market_bar)

            # Dashboard stat cards
            dashboard = QHBoxLayout()
            self._stat_pnl = StockStatCard("Total P/L")
            self._stat_trades = StockStatCard("Total Trades")
            self._stat_bots = StockStatCard("Active Bots")
            self._stat_positions = StockStatCard("Open Positions")
            self._stat_pdt = StockStatCard("Day Trades (5d)")
            self._stat_settlement = StockStatCard("Unsettled")
            for card in [
                self._stat_pnl,
                self._stat_trades,
                self._stat_bots,
                self._stat_positions,
                self._stat_pdt,
                self._stat_settlement,
            ]:
                dashboard.addWidget(card)
            main_layout.addLayout(dashboard)

            # Main tabs
            self._main_tabs = QTabWidget()
            self._main_tabs.setMovable(True)
            self._main_tabs.setDocumentMode(True)

            # --- Tab 1: Trading Dashboard ---
            trading_tab = QWidget()
            trading_layout = QVBoxLayout(trading_tab)

            trading_split = QSplitter(Qt.Horizontal)
            trading_split.setHandleWidth(5)
            trading_split.setChildrenCollapsible(False)

            # Left: bot table + controls
            left_panel = QWidget()
            left_layout = QVBoxLayout(left_panel)
            left_layout.setContentsMargins(0, 0, 0, 0)

            # Bot controls
            btn_row = QHBoxLayout()
            self._btn_new_bot = QPushButton("＋ New Accumulation Bot")
            self._btn_new_bot.setStyleSheet(
                f"QPushButton {{ background: {ds.STATUS_INFO}; "
                f"color: {ds.SURFACE_CHART}; "
                "border: none; border-radius: 6px; padding: 8px 16px; "
                "font-weight: bold; }"
                f"QPushButton:hover {{ background: {ds.STOCK_BUTTON_HOVER}; }}"
            )
            self._btn_new_bot.clicked.connect(self._create_bot)
            btn_row.addWidget(self._btn_new_bot)

            for label, slot in [
                ("Start", self._start_bot),
                ("Stop", self._stop_bot),
                ("Delete", self._delete_bot),
            ]:
                btn = QPushButton(label)
                btn.setStyleSheet(
                    f"QPushButton {{ background: {ds.CARD_STOCK_BORDER}; "
                    f"color: {ds.CARD_STOCK_BODY}; "
                    f"border: 1px solid {ds.CARD_STOCK_BUTTON_BORDER}; "
                    f"border-radius: 4px; padding: 6px 12px; }}"
                    f"QPushButton:hover {{ background: {ds.CARD_STOCK_BUTTON_HOVER}; }}"
                )
                btn.clicked.connect(slot)
                btn_row.addWidget(btn)
            left_layout.addLayout(btn_row)

            # Bot table
            self._bot_table = StockBotTable()
            left_layout.addWidget(self._bot_table)
            trading_split.addWidget(left_panel)

            # Right: TradingView chart
            right_panel = QWidget()
            right_layout = QVBoxLayout(right_panel)
            right_layout.setContentsMargins(0, 0, 0, 0)

            chart_group = QGroupBox("TradingView Chart")
            chart_group.setStyleSheet(
                f"QGroupBox {{ background: {ds.CARD_STOCK_PANEL}; "
                f"border: 1px solid {ds.CARD_STOCK_BORDER}; "
                f"border-radius: 6px; color: {ds.STATUS_INFO}; }}"
            )
            chart_layout = QVBoxLayout(chart_group)
            try:
                from .tradingview_chart import TradingViewChart

                self._chart = TradingViewChart(symbol="AAPL", theme="dark")
                chart_layout.addWidget(self._chart)
            except Exception:
                self._chart = None
                chart_layout.addWidget(
                    QLabel("TradingView chart requires PySide6-WebEngine")
                )
            right_layout.addWidget(chart_group, stretch=3)

            # Indicator Voting Panel (shared component)
            try:
                from .indicator_panel import IndicatorVotingPanel

                self._indicator_panel = IndicatorVotingPanel()
                right_layout.addWidget(self._indicator_panel, stretch=2)
            except Exception:
                self._indicator_panel = None

            trading_split.addWidget(right_panel)

            trading_split.setSizes([500, 600])
            trading_layout.addWidget(trading_split)

            # Activity log
            log_group = QGroupBox("Activity Log")
            log_group.setStyleSheet(
                f"QGroupBox {{ background: {ds.CARD_STOCK_PANEL}; "
                f"border: 1px solid {ds.CARD_STOCK_BORDER}; "
                f"border-radius: 6px; color: {ds.STATUS_INFO}; }}"
            )
            log_layout = QVBoxLayout(log_group)
            self._status_log = QTextEdit()
            self._status_log.setReadOnly(True)
            self._status_log.setMaximumHeight(150)
            self._status_log.setStyleSheet(
                f"QTextEdit {{ background: {ds.CARD_STOCK_LOG_SURFACE}; "
                f"color: {ds.CARD_STOCK_BODY}; border: none; }}"
            )
            log_layout.addWidget(self._status_log)
            trading_layout.addWidget(log_group)

            self._main_tabs.addTab(trading_tab, "Trading")

            # --- Tab 2: Webhook Manager ---
            webhook_tab = QWidget()
            wh_layout = QVBoxLayout(webhook_tab)

            wh_config = QGroupBox("TradingView Webhook Configuration")
            wh_config.setStyleSheet(
                f"QGroupBox {{ background: {ds.CARD_STOCK_PANEL}; "
                f"border: 1px solid {ds.CARD_STOCK_BORDER}; "
                f"border-radius: 6px; color: {ds.STATUS_INFO}; }}"
            )
            wh_form = QFormLayout(wh_config)

            self._wh_port = QSpinBox()
            self._wh_port.setRange(1024, 65535)
            self._wh_port.setValue(8742)
            wh_form.addRow("Webhook Port:", self._wh_port)

            self._wh_token = QLineEdit()
            self._wh_token.setPlaceholderText("Optional auth token for security")
            self._wh_token.setEchoMode(QLineEdit.Password)
            wh_form.addRow("Auth Token:", self._wh_token)

            wh_btn_row = QHBoxLayout()
            self._btn_start_wh = QPushButton("Start Webhook Server")
            self._btn_start_wh.setStyleSheet(
                f"QPushButton {{ background: {ds.STATUS_INFO}; "
                f"color: {ds.SURFACE_CHART}; "
                "border: none; border-radius: 4px; padding: 8px 16px; font-weight: bold; }"
            )
            self._btn_start_wh.clicked.connect(self._toggle_webhook)
            wh_btn_row.addWidget(self._btn_start_wh)
            wh_form.addRow(wh_btn_row)

            self._wh_url_label = QLabel("URL: Not started")
            self._wh_url_label.setStyleSheet(
                f"color: {ds.CARD_METRIC_LABEL}; font-family: Consolas;"
            )
            wh_form.addRow(self._wh_url_label)

            wh_layout.addWidget(wh_config)

            # Alert format guide
            guide = QGroupBox("TradingView Alert Format")
            guide.setStyleSheet(
                f"QGroupBox {{ background: {ds.CARD_STOCK_PANEL}; "
                f"border: 1px solid {ds.CARD_STOCK_BORDER}; "
                f"border-radius: 6px; color: {ds.STATUS_INFO}; }}"
            )
            guide_layout = QVBoxLayout(guide)
            guide_text = QTextEdit()
            guide_text.setReadOnly(True)
            guide_text.setMaximumHeight(200)
            guide_text.setStyleSheet(
                f"QTextEdit {{ background: {ds.CARD_STOCK_LOG_SURFACE}; "
                f"color: {ds.CARD_STOCK_BODY}; "
                "border: none; font-family: Consolas; font-size: 11px; }"
            )
            guide_text.setHtml(
                f'<span style="color:{ds.STATUS_INFO}">TradingView Alert Message Format (JSON):</span><br><br>'
                f'<span style="color:{ds.CARD_METRIC_LABEL}">Set your alert webhook URL to:</span><br>'
                f'<span style="color:{ds.STOCK_POSITIVE}">http://YOUR_IP:8742/webhook</span><br><br>'
                f'<span style="color:{ds.CARD_METRIC_LABEL}">Alert message body:</span><br>'
                f'<span style="color:{ds.TEXT_HIGH}">{{</span><br>'
                f'<span style="color:{ds.TEXT_HIGH}">&nbsp;&nbsp;"symbol": "{{{{ticker}}}}",</span><br>'
                f'<span style="color:{ds.TEXT_HIGH}">&nbsp;&nbsp;"action": "buy",</span><br>'
                f'<span style="color:{ds.TEXT_HIGH}">&nbsp;&nbsp;"price": {{{{close}}}},</span><br>'
                f'<span style="color:{ds.TEXT_HIGH}">&nbsp;&nbsp;"strategy": "My Strategy"</span><br>'
                f'<span style="color:{ds.TEXT_HIGH}">}}</span><br><br>'
                f'<span style="color:{ds.CARD_METRIC_LABEL}">Supported actions: buy, sell, close</span>'
            )
            guide_layout.addWidget(guide_text)
            wh_layout.addWidget(guide)

            # Alert history
            alerts_group = QGroupBox("Recent Alerts")
            alerts_group.setStyleSheet(
                f"QGroupBox {{ background: {ds.CARD_STOCK_PANEL}; "
                f"border: 1px solid {ds.CARD_STOCK_BORDER}; "
                f"border-radius: 6px; color: {ds.STATUS_INFO}; }}"
            )
            alerts_layout = QVBoxLayout(alerts_group)
            self._alert_table = QTableWidget()
            self._alert_table.setColumnCount(5)
            self._alert_table.setHorizontalHeaderLabels(
                ["Time", "Symbol", "Action", "Price", "Strategy"]
            )
            self._alert_table.horizontalHeader().setSectionResizeMode(
                QHeaderView.Stretch
            )
            self._alert_table.setAlternatingRowColors(True)
            self._alert_table.verticalHeader().setVisible(False)
            alerts_layout.addWidget(self._alert_table)
            wh_layout.addWidget(alerts_group)

            self._main_tabs.addTab(webhook_tab, "Webhooks")

            # --- Tab 3: Paper Trader (equities) ---
            try:
                from .paper_trader_tab import PaperTraderTab

                self._paper_trader = PaperTraderTab(asset_type="equity")
                self._main_tabs.addTab(self._paper_trader, "Paper Trader")
            except Exception as _e:
                logging.getLogger("acervator").warning(
                    f"Paper Trader tab unavailable: {_e}"
                )

            # --- Analytics Dashboard — REMOVED per P1.7 / MEM-178 ---
            self._analytics_tab = None

            # --- Risk Management — REMOVED per P1.7 / MEM-178 ---
            self._risk_tab = None

            # --- Trade Journal — REMOVED per P1.7 / MEM-178 ---
            self._journal_tab = None

            # --- Alerts & Notifications — REMOVED per P1.7 / MEM-178 ---
            self._alerts_tab = None

            # --- Tab 7: Console ---
            self._console = QTextEdit()
            self._console.setReadOnly(True)
            self._console.setFont(QFont("Consolas", 9))
            self._console.setStyleSheet(
                f"QTextEdit {{ background: {ds.CARD_STOCK_LOG_SURFACE}; "
                f"color: {ds.CARD_STOCK_BODY}; "
                "border: none; padding: 4px; }"
            )
            self._console.setLineWrapMode(QTextEdit.NoWrap)

            # MEM-221 — thread-safe log handler. See main_window.py
            # for the full explanation. emit() runs on any thread;
            # the widget update is queued to the main thread via Signal.
            class _StockLogHandler(QObject, logging.Handler):
                COLORS = {
                    "DEBUG": ds.STOCK_LOG_DEBUG,
                    "INFO": ds.STATUS_NEUTRAL,
                    "WARNING": ds.STOCK_WARNING,
                    "ERROR": ds.STOCK_NEGATIVE,
                    "CRITICAL": ds.STOCK_LOG_CRITICAL,
                }
                _append_signal = Signal(str)

                def __init__(self, te):
                    QObject.__init__(self)
                    logging.Handler.__init__(self)
                    self._te = te
                    self._append_signal.connect(
                        self._append_to_widget, Qt.AutoConnection
                    )

                def emit(self, record):
                    try:
                        msg = self.format(record)
                        c = self.COLORS.get(record.levelname, ds.STATUS_NEUTRAL)
                        self._append_signal.emit(
                            f'<span style="color:{c}">{msg}</span>'
                        )
                    except Exception as _sf_exc:  # noqa: BLE001
                        logger.debug("stock window log append failed: %s", _sf_exc)

                @Slot(str)
                def _append_to_widget(self, html):
                    try:
                        self._te.append(html)
                        sb = self._te.verticalScrollBar()
                        sb.setValue(sb.maximum())
                    except Exception as _sf_exc:  # noqa: BLE001
                        logger.debug("stock window log append failed: %s", _sf_exc)

            handler = _StockLogHandler(self._console)
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    datefmt="%H:%M:%S",
                )
            )
            logging.getLogger().addHandler(handler)

            self._main_tabs.addTab(self._console, "Console")

            main_layout.addWidget(self._main_tabs)

        def _setup_status_bar(self):
            status = QStatusBar()
            status.showMessage("Ready — Stock Trading Mode")
            self.setStatusBar(status)

        def _setup_refresh_timer(self):
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._refresh_dashboard)
            self._timer.start(2000)

        @Slot()
        def _refresh_dashboard(self):
            try:
                # Market status
                status_str = self._market_hours.get_status_string()
                session = self._market_hours.get_session()
                from ..stocks.market_hours import MarketSession

                if session == MarketSession.REGULAR:
                    color = ds.STOCK_POSITIVE
                elif session in (MarketSession.PRE_MARKET, MarketSession.AFTER_HOURS):
                    color = ds.STOCK_WARNING
                else:
                    color = ds.STOCK_NEGATIVE
                self._market_status.setText(f"Market: {status_str}")
                self._market_status.setStyleSheet(
                    f"color: {color}; font-size: 13px; font-weight: bold; "
                    f"padding: 4px 12px; background: {ds.CARD_STOCK_PANEL}; "
                    f"border-radius: 4px; border: 1px solid {color}44;"
                )

                # Webhook status
                if self._tv_bridge and self._tv_bridge.running:
                    summary = self._tv_bridge.get_summary()
                    self._webhook_status.setText(
                        f"Webhook: Active (port {summary['port']}) | "
                        f"Alerts: {summary['total_alerts']}"
                    )
                    self._webhook_status.setStyleSheet(
                        f"color: {ds.STOCK_POSITIVE}; font-size: 11px;"
                    )

                # Bot stats
                if self._bot_manager:
                    agg = self._bot_manager.get_aggregate_stats()
                    pnl = agg.get("total_realised_pnl", 0)
                    self._stat_pnl.set_value(
                        f"${pnl:+,.2f}",
                        ds.STOCK_POSITIVE if pnl >= 0 else ds.STOCK_NEGATIVE,
                    )
                    self._stat_trades.set_value(str(agg.get("total_trades", 0)))
                    self._stat_bots.set_value(str(agg.get("running", 0)))

                    statuses = self._bot_manager.list_bots()
                    self._bot_table.update_bots(statuses)

                    # Open positions count
                    pos_count = sum(
                        1
                        for s in statuses
                        if s.get("stats", {}).get("current_position", 0) != 0
                    )
                    self._stat_positions.set_value(str(pos_count))

                    # Signals today
                    total_signals = sum(
                        s.get("stats", {}).get("signals_received", 0) for s in statuses
                    )
                    self._stat_signals.set_value(str(total_signals))

                    # Win rate
                    total_wins = sum(
                        s.get("stats", {}).get("winning_trades", 0) for s in statuses
                    )
                    total_trades = agg.get("total_trades", 0)
                    wr = (total_wins / total_trades * 100) if total_trades > 0 else 0
                    self._stat_winrate.set_value(f"{wr:.1f}%")

                    # Feed indicator panel with stock bot list
                    if self._indicator_panel:
                        try:
                            # Convert stock statuses to format indicator panel expects
                            panel_statuses = [
                                {
                                    **s,
                                    "mode": "scrumming",
                                }  # Panel filters for scrumming
                                for s in statuses
                                if s.get("mode") in ("swing", "signal")
                            ]
                            if panel_statuses:
                                self._indicator_panel.update_bot_list(panel_statuses)
                        except Exception as _sf_exc:  # noqa: BLE001
                            logger.warning(
                                "stock dashboard refresh failed — tiles are stale: %s",
                                _sf_exc,
                            )

                # Refresh shared tabs (throttled)
                if not hasattr(self, "_last_tab_refresh"):
                    self._last_tab_refresh = 0
                if time.time() - self._last_tab_refresh >= 4:
                    self._last_tab_refresh = time.time()
                    if self._analytics_tab and self._analytics:
                        self._analytics_tab.refresh(self._analytics)
                    if self._risk_tab and self._risk_manager:
                        self._risk_tab.refresh(self._risk_manager)
                    if self._alerts_tab and self._notif_manager:
                        self._alerts_tab.refresh(self._notif_manager)

                    # Update webhook alert table
                    if self._tv_bridge:
                        alerts = self._tv_bridge.alert_history[-50:]
                        self._alert_table.setRowCount(len(alerts))
                        for row, alert in enumerate(reversed(alerts)):
                            ts = time.strftime(
                                "%H:%M:%S", time.localtime(alert.timestamp)
                            )
                            items = [
                                ts,
                                alert.symbol,
                                alert.action,
                                f"${alert.price:.2f}",
                                alert.strategy,
                            ]
                            for col, text in enumerate(items):
                                item = QTableWidgetItem(text)
                                item.setTextAlignment(Qt.AlignCenter)
                                self._alert_table.setItem(row, col, item)

            except Exception as exc:
                logger.error("STOCK DASHBOARD: refresh crashed: %s", exc)

        def _log(self, message: str, level: str = "info"):
            """Log to activity panel."""
            ts = datetime.now().strftime("%H:%M:%S")
            colors = {
                "info": ds.STATUS_NEUTRAL,
                "success": ds.STOCK_POSITIVE,
                "warning": ds.STOCK_WARNING,
                "error": ds.STOCK_NEGATIVE,
            }
            color = colors.get(level, ds.STATUS_NEUTRAL)
            self._status_log.append(
                f'<span style="color:{ds.STOCK_LOG_TIMESTAMP}">[{ts}]</span> '
                f'<span style="color:{color}">{message}</span>'
            )

        def _create_bot(self):
            """Create a new stock accumulation bot."""
            from ..stocks.stock_accumulation_bot import (
                StockAccumulationBot,
                StockAccumulationConfig,
            )

            dlg = QMessageBox(self)
            dlg.setWindowTitle("New Accumulation Bot")
            dlg.setText(
                "Create an Accumulation Trading bot for stocks?\n\n"
                "• Harvest-Fold cycle (same as crypto mode)\n"
                "• 7-indicator TA voting engine\n"
                "• MR Inspector + Boosted Fold\n"
                "• Smart Wire cross-compounding\n"
                "• Market hours enforcement\n"
                "• PDT protection (3 day-trades / 5 days)\n"
                "• T+2 settlement tracking\n\n"
                "Symbol: AAPL | Target: $200 | TF: 1D"
            )
            dlg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
            if dlg.exec() == QMessageBox.Ok:
                config = StockAccumulationConfig(
                    symbol="AAPL",
                    target_balance=200.0,
                    ta_timeframe="1D",
                )
                bot = StockAccumulationBot(config)
                if self._bot_manager:
                    # v3.20.71 Phase B-2 — register() returns
                    # (granted, reason); refused on over-allocation.
                    _reg_result = self._bot_manager.register(bot)
                    if isinstance(_reg_result, tuple) and not _reg_result[0]:
                        self._log(
                            f"Bot creation refused by CapitalRegistry: "
                            f"{_reg_result[1]}",
                            "error",
                        )
                        return
                self._log(
                    f"Accumulation bot created: {config.symbol} "
                    f"target=${config.target_balance}",
                    "success",
                )

        def _start_bot(self):
            self._log("Start bot — select a bot first", "warning")

        def _stop_bot(self):
            self._log("Stop bot — select a bot first", "warning")

        def _delete_bot(self):
            self._log("Delete bot — select a bot first", "warning")

        def _toggle_webhook(self):
            """Start/stop the TradingView webhook server."""
            if not self._tv_bridge:
                self._log("TradingView bridge not initialized", "error")
                return

            if self._tv_bridge.running:
                import asyncio

                asyncio.ensure_future(self._tv_bridge.stop())
                self._btn_start_wh.setText("Start Webhook Server")
                self._wh_url_label.setText("URL: Stopped")
                self._log("Webhook server stopped", "warning")
            else:
                port = self._wh_port.value()
                token = self._wh_token.text().strip()
                if token:
                    self._tv_bridge.set_auth_token(token)
                self._tv_bridge._port = port
                import asyncio

                asyncio.ensure_future(self._tv_bridge.start())
                self._btn_start_wh.setText("Stop Webhook Server")
                self._wh_url_label.setText(f"URL: http://localhost:{port}/webhook")
                self._log(f"Webhook server started on port {port}", "success")

        def _open_settings(self):
            self._log("Settings dialog — coming soon", "info")

        def _back_to_launcher(self):
            """Return to launcher."""
            self.hide()
            # Signal parent to show launcher
            if hasattr(self, "_launcher_callback") and self._launcher_callback:
                self._launcher_callback()

        def _show_about(self):
            QMessageBox.about(
                self,
                "About",
                "Acervator — Stock Trading v3.1\n\n"
                "TradingView Webhook Integration\n"
                "Alpaca Broker Support\n"
                "Signal • DCA • Swing • Grid Bots\n"
                "Market Hours Awareness\n"
                "Shared Analytics & Risk Management",
            )

        def set_launcher_callback(self, callback):
            """Set callback to return to launcher."""
            self._launcher_callback = callback
