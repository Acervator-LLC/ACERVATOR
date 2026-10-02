"""The Bot Swarm tab and its Smart Wire canvas.

``BotVisualizationTab`` holds a ``BotNodeWidget`` per bot, a
``QuickRoutingMatrix``, and sub-tabs for the simulator and paper rows.
``_WireCanvas`` paints the wires between bot nodes, and ``THEMES``
supplies the accent colours.
"""

from __future__ import annotations

import logging
import math
import sys
import time
from typing import Optional

logger = logging.getLogger("acervator.gui.bot_visualizer")

# One registry shared with the Trading tab: a toggle here flips both.
try:
    from ..core.privacy_mask_registry import (
        get_privacy_mask_registry as _get_privacy_mask_registry,
    )
except Exception:  # a missing registry leaves the dot reading unmasked
    _get_privacy_mask_registry = None  # type: ignore[assignment]


try:
    from PySide6.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QComboBox,
        QLabel,
        QScrollArea,
        QFrame,
        QMenu,
        QTabWidget,
        QGroupBox,
        QPushButton,
        QDoubleSpinBox,
        QGridLayout,
        QMessageBox,
    )
    from PySide6.QtCore import Qt, QTimer, QPointF

    from . import design_system as ds

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    from .visualizer.bot_node import BotNodeWidget, _RNG
    from .visualizer.quick_routing import QuickRoutingMatrix
    from .visualizer.themes import THEMES
    from .visualizer.wire_canvas import _WireCanvas

    class BotVisualizationTab(QWidget):
        """The Bot Swarm tab, holding ``_bot_widgets`` and ``_wire_canvas``."""

        def __init__(self, parent=None):
            super().__init__(parent)
            from .main_tabs.bot_visualizer_surface import FrameCadence

            self._theme_key = "quantum"
            self._bot_widgets: dict[str, BotNodeWidget] = {}
            self._last_time = time.monotonic()
            self._frame_cadence = FrameCadence()
            self._wires: list[dict] = []  # [{source_id, target_id, pct, phase}]
            self._dragging_wire = False
            self._wire_start_id: str = ""
            self._wire_mouse_pos: Optional[QPointF] = None
            # _wire_opacity_pct is 0-100, the alpha multiplier on the wire sheet.
            self._wire_opacity_pct: int = 100
            from .visualizer.growth_stage import DEFAULT_THEME_NAME

            self._app_theme_name: str = DEFAULT_THEME_NAME

            # The startup restore and a wire drag both emit wire.created.
            try:
                from ..core.event_bus import get_event_bus

                _bus = get_event_bus()
                _bus.subscribe("wire.created", self._on_external_wire_created)
                _bus.subscribe("wire.removed", self._on_external_wire_removed)
            except Exception:  # noqa: S110
                pass

            layout = QVBoxLayout(self)
            layout.setContentsMargins(4, 4, 4, 4)
            layout.setSpacing(0)

            self._tabs = QTabWidget()
            self._tabs.setStyleSheet(
                f"QTabWidget::pane{{border:1px solid {ds.VIZ_PANEL_BORDER};background:{ds.VIZ_SWARM_SURFACE};}}"
                f"QTabBar::tab{{background:{ds.VIZ_PANEL_SURFACE};color:{ds.VIZ_TAB_TEXT};border:1px solid {ds.VIZ_PANEL_BORDER};"
                "padding:4px 12px;font-size:9px;}"
                f"QTabBar::tab:selected{{background:{ds.VIZ_TAB_SELECTED};color:{ds.PRIMARY_BRIGHT};"
                f"border-bottom:2px solid {ds.PRIMARY_BRIGHT};}}"
                f"QTabBar::tab:hover{{color:{ds.TEXT_INACTIVE};}}"
            )

            viz_tab = QWidget()
            viz_lay = QVBoxLayout(viz_tab)
            viz_lay.setContentsMargins(4, 4, 4, 4)
            viz_lay.setSpacing(4)

            header = QHBoxLayout()
            header.addWidget(QLabel("Bot Swarm"))
            header.addWidget(
                QLabel(
                    "   Drag between bots to connect  •  "
                    "Right-click wire to disconnect"
                )
            )

            # bot_swarm.identifiers masks both bot ids and symbol labels.
            self._bot_swarm_privacy_dot = QLabel("●")
            self._bot_swarm_privacy_dot.setCursor(Qt.PointingHandCursor)
            self._bot_swarm_privacy_dot.setToolTip(
                "Bot Swarm identifier privacy — masks bot hash IDs + "
                "symbol labels (● revealed / ○ masked)."
            )
            self._bot_swarm_privacy_dot.mousePressEvent = (
                lambda _e: self._toggle_bot_swarm_identifier_mask()
            )
            self._refresh_bot_swarm_privacy_dot()
            header.addWidget(self._bot_swarm_privacy_dot)

            header.addStretch()

            self._privacy_mode_btn = QPushButton("Privacy Mode: OFF")
            self._privacy_mode_btn.setToolTip(
                "Toggle ALL privacy masks across Trading + Bot Swarm "
                "tabs (shared singleton)."
            )
            self._privacy_mode_btn.clicked.connect(self._on_privacy_mode_btn_clicked)
            self._refresh_privacy_mode_btn()
            header.addWidget(self._privacy_mode_btn)

            # Filters both the visible swarm and the Quick Routing scope.
            header.addWidget(QLabel("Exchange:"))
            self._exchange_combo = QComboBox()
            self._exchange_combo.addItem("All", "")
            self._exchange_combo.setToolTip(
                "Filter Bot Swarm visualizer + Quick Routing scope by "
                "exchange. Default: All."
            )
            self._exchange_combo.currentIndexChanged.connect(
                self._on_exchange_filter_changed
            )
            header.addWidget(self._exchange_combo)

            header.addWidget(QLabel("Theme:"))
            self._theme_combo = QComboBox()
            for key, theme in THEMES.items():
                self._theme_combo.addItem(theme["name"], key)
            self._theme_combo.setCurrentIndex(2)
            self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)
            header.addWidget(self._theme_combo)

            header.addWidget(QLabel("Wires:"))
            from PySide6.QtWidgets import QSlider

            self._wire_opacity_slider = QSlider(Qt.Horizontal)
            self._wire_opacity_slider.setRange(0, 100)
            self._wire_opacity_slider.setValue(100)
            self._wire_opacity_slider.setFixedWidth(90)
            self._wire_opacity_slider.setToolTip(
                "Wire opacity 0–100 %. Lower for more contrast on "
                "underlying readouts; 100 = fully opaque."
            )
            self._wire_opacity_slider.valueChanged.connect(
                self._on_wire_opacity_changed
            )
            header.addWidget(self._wire_opacity_slider)

            viz_lay.addLayout(header)

            self._live_rows_scroll = QScrollArea()
            self._live_rows_scroll.setWidgetResizable(True)
            self._live_rows_scroll.setStyleSheet(
                f"QScrollArea{{border:1px solid {ds.VIZ_PANEL_BORDER};"
                f"background:{ds.VIZ_SWARM_SURFACE};}}"
            )
            self._live_rows_widget = QWidget()
            self._live_rows_widget.setStyleSheet(f"background:{ds.VIZ_SWARM_SURFACE};")
            self._live_rows_layout = QVBoxLayout(self._live_rows_widget)
            self._live_rows_layout.setSpacing(4)
            self._live_rows_layout.setContentsMargins(4, 4, 4, 4)
            self._live_rows_empty = QLabel("No live bots registered.")
            self._live_rows_empty.setStyleSheet(
                f"color:{ds.TEXT_PLACEHOLDER};font-size:8px;background:transparent;"
            )
            self._live_rows_layout.addWidget(self._live_rows_empty)
            self._live_rows_layout.addStretch()
            self._live_rows_scroll.setWidget(self._live_rows_widget)
            self._live_rows_scroll.setMaximumHeight(140)
            # Hidden while no live row exists, so _grid_layout keeps the tab height.
            self._live_rows_scroll.setVisible(False)
            viz_lay.addWidget(self._live_rows_scroll)

            self._live_bot_rows: dict = {}

            # No scroll area: _grid_layout wraps the locusts across rows.
            self._grid_widget = QWidget()
            self._grid_layout = QGridLayout(self._grid_widget)
            self._grid_layout.setSpacing(10)
            self._grid_layout.setContentsMargins(6, 6, 6, 6)
            self._grid_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            # 8 columns fits an 88px locust plus 10px spacing in the left pane.
            self._grid_cols = 8
            self._empty_label = QLabel(
                "No active bots. Start bots to see visualizations."
            )
            self._empty_label.setStyleSheet(
                f"color:{ds.TEXT_PLACEHOLDER};padding:40px;"
            )
            self._empty_label.setAlignment(Qt.AlignCenter)
            self._grid_layout.addWidget(self._empty_label, 0, 0, 1, self._grid_cols)

            self._quick_routing_matrix = QuickRoutingMatrix(self)

            inner_hbox = QHBoxLayout()
            # No gap: _quick_routing_matrix takes every pixel the grid leaves.
            inner_hbox.setSpacing(0)
            inner_hbox.addWidget(self._grid_widget)
            inner_hbox.addWidget(self._quick_routing_matrix, stretch=1)
            viz_lay.addLayout(inner_hbox, stretch=1)

            self._viz_tab = viz_tab  # kept for the wire canvas geometry
            self._bot_swarm_tab = viz_tab
            self._tabs.addTab(viz_tab, "⚡ Bot Swarm")

            # Stored wires replay as wire.created, through the drag handler.
            try:
                painted = self._hydrate_wires_from_disk()
            except Exception:
                logger.exception(
                    "wire hydration failed; the wire overlay may show"
                    " fewer wires than bot_state.json holds"
                )
            else:
                logger.info(
                    "wire hydration: %d wire.created event(s) " "emitted", painted
                )

            sim_tab = QWidget()
            sim_lay = QVBoxLayout(sim_tab)
            sim_lay.setContentsMargins(8, 8, 8, 8)
            sim_lay.setSpacing(6)

            sim_hdr = QHBoxLayout()
            sim_hdr_lbl = QLabel("SIMULATOR SWARM")
            sim_hdr_lbl.setStyleSheet(
                f"color:{ds.PRIMARY_BRIGHT};font-weight:bold;font-size:10px;font-family:Consolas;"
            )
            sim_hdr.addWidget(sim_hdr_lbl)
            sim_hdr.addStretch()

            sim_add_btn = QPushButton("+ Add Sim Bot")
            sim_add_btn.setStyleSheet(
                f"QPushButton{{background:{ds.VIZ_PANEL_SURFACE};color:{ds.SUCCESS};border:1px solid {ds.SUCCESS};"
                "border-radius:3px;padding:3px 10px;font-size:9px;font-weight:bold;}"
                f"QPushButton:hover{{background:{ds.VIZ_GO_HOVER};}}"
            )
            sim_hdr.addWidget(sim_add_btn)

            sim_run_all = QPushButton("▶ Run All")
            sim_run_all.setStyleSheet(
                f"QPushButton{{background:{ds.VIZ_PANEL_SURFACE};color:{ds.PRIMARY_BRIGHT};border:1px solid {ds.PRIMARY_BRIGHT};"
                "border-radius:3px;padding:3px 10px;font-size:9px;font-weight:bold;}"
                f"QPushButton:hover{{background:{ds.VIZ_SIM_HOVER};}}"
            )
            sim_hdr.addWidget(sim_run_all)

            sim_stop_all = QPushButton("■ Stop All")
            sim_stop_all.setStyleSheet(
                f"QPushButton{{background:{ds.VIZ_PANEL_SURFACE};color:{ds.ERROR};border:1px solid {ds.ERROR};"
                "border-radius:3px;padding:3px 10px;font-size:9px;font-weight:bold;}"
                f"QPushButton:hover{{background:{ds.VIZ_STOP_HOVER};}}"
            )
            sim_hdr.addWidget(sim_stop_all)
            sim_lay.addLayout(sim_hdr)

            sim_desc = QLabel(
                "Run multiple simultaneous simulators. Each bot runs independently "
                "on its own asset/timeframe. Results aggregate in the summary row."
            )
            sim_desc.setStyleSheet(f"color:{ds.VIZ_CAPTION};font-size:8px;")
            sim_desc.setWordWrap(True)
            sim_lay.addWidget(sim_desc)

            sim_scroll = QScrollArea()
            sim_scroll.setWidgetResizable(True)
            sim_scroll.setStyleSheet(
                f"QScrollArea{{border:1px solid {ds.VIZ_PANEL_BORDER};background:{ds.VIZ_SWARM_SURFACE};}}"
            )
            self._sim_swarm_widget = QWidget()
            self._sim_swarm_widget.setStyleSheet(f"background:{ds.VIZ_SWARM_SURFACE};")
            self._sim_swarm_layout = QVBoxLayout(self._sim_swarm_widget)
            self._sim_swarm_layout.setSpacing(4)
            self._sim_swarm_layout.setContentsMargins(4, 4, 4, 4)
            self._sim_swarm_layout.addStretch()
            sim_scroll.setWidget(self._sim_swarm_widget)
            sim_lay.addWidget(sim_scroll, stretch=1)

            sim_summary = QGroupBox("SWARM SUMMARY")
            sim_summary.setStyleSheet(
                f"QGroupBox{{border:1px solid {ds.VIZ_PANEL_BORDER};color:{ds.PRIMARY_BRIGHT};"
                "font-size:8px;font-weight:bold;margin-top:6px;padding-top:6px;}"
                "QGroupBox::title{subcontrol-origin:margin;left:8px;}"
            )
            sim_sum_lay = QHBoxLayout(sim_summary)
            sim_sum_lay.setSpacing(12)
            self._sim_swarm_wins = QLabel("Wins: —")
            self._sim_swarm_pnl = QLabel("Total PnL: —")
            self._sim_swarm_trades = QLabel("Trades: —")
            for lbl in (
                self._sim_swarm_wins,
                self._sim_swarm_pnl,
                self._sim_swarm_trades,
            ):
                lbl.setStyleSheet(
                    f"color:{ds.VIZ_HEADING};font-size:9px;font-family:Consolas;font-weight:bold;"
                )
                sim_sum_lay.addWidget(lbl)
            sim_sum_lay.addStretch()
            sim_lay.addWidget(sim_summary)

            self._sim_bots: list[dict] = []
            self._live_sim_rows: dict = {}  # sim_id → handle
            self._tabs.addTab(sim_tab, "🖥 Simulator Swarm")

            def _add_sim_bot():
                self._create_sim_bot_row()

            sim_add_btn.clicked.connect(_add_sim_bot)

            def _run_all_sims():
                for bot in self._sim_bots:
                    if not bot.get("running"):
                        btn = bot.get("run_btn")
                        if btn:
                            btn.click()

            sim_run_all.clicked.connect(_run_all_sims)

            def _stop_all_sims():
                for bot in self._sim_bots:
                    if bot.get("running"):
                        btn = bot.get("run_btn")
                        if btn:
                            btn.click()

            sim_stop_all.clicked.connect(_stop_all_sims)

            paper_tab = QWidget()
            paper_lay = QVBoxLayout(paper_tab)
            paper_lay.setContentsMargins(8, 8, 8, 8)
            paper_lay.setSpacing(6)

            paper_hdr = QHBoxLayout()
            paper_hdr_lbl = QLabel("PAPER TRADER SWARM")
            paper_hdr_lbl.setStyleSheet(
                f"color:{ds.ACCENT_GOLD};font-weight:bold;font-size:10px;font-family:Consolas;"
            )
            paper_hdr.addWidget(paper_hdr_lbl)
            paper_hdr.addStretch()

            paper_add_btn = QPushButton("+ Add Paper Bot")
            paper_add_btn.setStyleSheet(
                f"QPushButton{{background:{ds.VIZ_PANEL_SURFACE};color:{ds.ACCENT_GOLD};border:1px solid {ds.ACCENT_GOLD};"
                "border-radius:3px;padding:3px 10px;font-size:9px;font-weight:bold;}"
                f"QPushButton:hover{{background:{ds.VIZ_GOLD_HOVER};}}"
            )
            paper_hdr.addWidget(paper_add_btn)

            paper_start_all = QPushButton("▶ Start All")
            paper_start_all.setStyleSheet(
                f"QPushButton{{background:{ds.VIZ_PANEL_SURFACE};color:{ds.SUCCESS};border:1px solid {ds.SUCCESS};"
                "border-radius:3px;padding:3px 10px;font-size:9px;font-weight:bold;}"
                f"QPushButton:hover{{background:{ds.VIZ_GO_HOVER};}}"
            )
            paper_hdr.addWidget(paper_start_all)

            paper_stop_all = QPushButton("■ Stop All")
            paper_stop_all.setStyleSheet(
                f"QPushButton{{background:{ds.VIZ_PANEL_SURFACE};color:{ds.ERROR};border:1px solid {ds.ERROR};"
                "border-radius:3px;padding:3px 10px;font-size:9px;font-weight:bold;}"
                f"QPushButton:hover{{background:{ds.VIZ_STOP_HOVER};}}"
            )
            paper_hdr.addWidget(paper_stop_all)
            paper_lay.addLayout(paper_hdr)

            paper_desc = QLabel(
                "Run multiple live paper trading bots simultaneously. "
                "Each bot trades a different asset with virtual capital against real market data. "
                "Source: CoinGecko (crypto) or Yahoo Finance (equities). No geographic restrictions."
            )
            paper_desc.setStyleSheet(f"color:{ds.VIZ_CAPTION};font-size:8px;")
            paper_desc.setWordWrap(True)
            paper_lay.addWidget(paper_desc)

            paper_scroll = QScrollArea()
            paper_scroll.setWidgetResizable(True)
            paper_scroll.setStyleSheet(
                f"QScrollArea{{border:1px solid {ds.VIZ_PANEL_BORDER};background:{ds.VIZ_SWARM_SURFACE};}}"
            )
            self._paper_swarm_widget = QWidget()
            self._paper_swarm_widget.setStyleSheet(
                f"background:{ds.VIZ_SWARM_SURFACE};"
            )
            self._paper_swarm_layout = QVBoxLayout(self._paper_swarm_widget)
            self._paper_swarm_layout.setSpacing(4)
            self._paper_swarm_layout.setContentsMargins(4, 4, 4, 4)
            self._paper_swarm_layout.addStretch()
            paper_scroll.setWidget(self._paper_swarm_widget)
            paper_lay.addWidget(paper_scroll, stretch=1)

            paper_summary = QGroupBox("PORTFOLIO SUMMARY")
            paper_summary.setStyleSheet(
                f"QGroupBox{{border:1px solid {ds.VIZ_PANEL_BORDER};color:{ds.ACCENT_GOLD};"
                "font-size:8px;font-weight:bold;margin-top:6px;padding-top:6px;}"
                "QGroupBox::title{subcontrol-origin:margin;left:8px;}"
            )
            paper_sum_lay = QHBoxLayout(paper_summary)
            paper_sum_lay.setSpacing(12)
            self._paper_swarm_total = QLabel("Total Capital: —")
            self._paper_swarm_pnl = QLabel("Net PnL: —")
            self._paper_swarm_active = QLabel("Active Bots: 0")
            for lbl in (
                self._paper_swarm_total,
                self._paper_swarm_pnl,
                self._paper_swarm_active,
            ):
                lbl.setStyleSheet(
                    f"color:{ds.VIZ_HEADING};font-size:9px;font-family:Consolas;font-weight:bold;"
                )
                paper_sum_lay.addWidget(lbl)
            paper_sum_lay.addStretch()
            paper_lay.addWidget(paper_summary)

            self._paper_bots: list[dict] = []
            self._live_paper_rows: dict = {}  # paper_id → handle
            self._tabs.addTab(paper_tab, "📄 Paper Swarm")

            def _add_paper_bot():
                self._create_paper_bot_row()

            paper_add_btn.clicked.connect(_add_paper_bot)

            def _start_all_paper():
                for bot in self._paper_bots:
                    if not bot.get("running"):
                        btn = bot.get("start_btn")
                        if btn:
                            btn.click()

            paper_start_all.clicked.connect(_start_all_paper)

            def _stop_all_paper():
                for bot in self._paper_bots:
                    if bot.get("running"):
                        btn = bot.get("start_btn")
                        if btn:
                            btn.click()

            paper_stop_all.clicked.connect(_stop_all_paper)

            layout.addWidget(self._tabs)

            # _wire_canvas floats over the viz sub-tab, hidden on the others.
            self._wire_canvas = _WireCanvas(self)
            self._wire_canvas.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            self._wire_canvas.setMouseTracking(True)
            self._wire_canvas.hide()  # starts hidden; shown only on viz tab

            def _on_tab_changed(idx):
                # The overlay carries grid coordinates and belongs to that tab.
                if idx == 0:
                    self._wire_canvas.show()
                    self._wire_canvas.raise_()
                    self._reposition_wire_canvas()
                else:
                    self._wire_canvas.hide()

            self._tabs.currentChanged.connect(_on_tab_changed)
            # Qt fires no currentChanged for the first tab.
            _on_tab_changed(self._tabs.currentIndex())

            from .main_tabs import bot_visualizer_surface as surface

            self._anim_timer = QTimer(self)
            self._anim_timer.timeout.connect(self._animate)
            self._anim_timer.start(surface.FRAME_INTERVAL_MS)

        def _create_sim_bot_row(self):
            """Append one row to ``_sim_bots`` and ``_sim_swarm_layout``."""
            idx = len(self._sim_bots) + 1
            row = QFrame()
            row.setStyleSheet(
                f"QFrame{{background:{ds.VIZ_PANEL_SURFACE};border:1px solid {ds.VIZ_PANEL_BORDER};"
                "border-radius:4px;padding:2px;}"
            )
            rl = QHBoxLayout(row)
            rl.setContentsMargins(8, 4, 8, 4)
            rl.setSpacing(6)

            id_lbl = QLabel(f"SIM-{idx:02d}")
            id_lbl.setFixedWidth(48)
            id_lbl.setStyleSheet(
                f"color:{ds.PRIMARY_BRIGHT};font-size:9px;font-weight:bold;font-family:Consolas;"
            )
            rl.addWidget(id_lbl)

            asset_combo = QComboBox()
            asset_combo.setEditable(True)
            asset_combo.addItems(
                [
                    "BTC/USDT",
                    "ETH/USDT",
                    "SOL/USDT",
                    "XRP/USDT",
                    "BNB/USDT",
                    "ADA/USDT",
                    "DOGE/USDT",
                ]
            )
            asset_combo.setFixedWidth(110)
            asset_combo.setToolTip("Trading pair — type any symbol")
            rl.addWidget(asset_combo)

            preset_combo = QComboBox()
            preset_combo.addItems(
                [
                    "btc_bull",
                    "btc_range",
                    "eth_volatile",
                    "dust_coin_pump",
                    "dust_coin_sideways",
                    "high_volatility",
                    "crash_recovery",
                ]
            )
            preset_combo.setFixedWidth(120)
            rl.addWidget(preset_combo)

            cap_spin = QDoubleSpinBox()
            cap_spin.setRange(10, 999999)
            cap_spin.setValue(400)
            cap_spin.setPrefix("$")
            cap_spin.setFixedWidth(80)
            rl.addWidget(cap_spin)

            status_lbl = QLabel("IDLE")
            status_lbl.setFixedWidth(90)
            status_lbl.setStyleSheet(
                f"color:{ds.VIZ_CAPTION};font-size:8px;font-family:Consolas;font-weight:bold;"
            )
            rl.addWidget(status_lbl)

            pnl_lbl = QLabel("PnL: —")
            pnl_lbl.setFixedWidth(80)
            pnl_lbl.setStyleSheet(
                f"color:{ds.VIZ_CAPTION};font-size:8px;font-family:Consolas;"
            )
            rl.addWidget(pnl_lbl)

            rl.addStretch()

            run_btn = QPushButton("▶ Run")
            run_btn.setFixedSize(58, 22)
            run_btn.setStyleSheet(
                f"QPushButton{{background:{ds.VIZ_GO_HOVER};color:{ds.SUCCESS};border:1px solid {ds.SUCCESS};"
                "border-radius:3px;font-size:9px;font-weight:bold;}"
                f"QPushButton:hover{{background:{ds.VIZ_GO_HOVER_DEEP};}}"
            )
            rl.addWidget(run_btn)

            rem_btn = QPushButton("✕")
            rem_btn.setFixedSize(22, 22)
            rem_btn.setStyleSheet(
                f"QPushButton{{background:{ds.VIZ_STOP_HOVER};color:{ds.ERROR};border:1px solid {ds.ERROR};"
                "border-radius:3px;font-size:9px;}"
                f"QPushButton:hover{{background:{ds.VIZ_STOP_HOVER_DEEP};}}"
            )
            rl.addWidget(rem_btn)

            bot_data = {
                "widget": row,
                "idx": idx,
                "asset_combo": asset_combo,
                "preset_combo": preset_combo,
                "cap_spin": cap_spin,
                "status_lbl": status_lbl,
                "pnl_lbl": pnl_lbl,
                "run_btn": run_btn,
                "running": False,
            }
            self._sim_bots.append(bot_data)

            insert_pos = self._sim_swarm_layout.count() - 1
            self._sim_swarm_layout.insertWidget(insert_pos, row)

            def _toggle_run():
                if bot_data["running"]:
                    bot_data["running"] = False
                    run_btn.setText("▶ Run")
                    run_btn.setStyleSheet(
                        f"QPushButton{{background:{ds.VIZ_GO_HOVER};color:{ds.SUCCESS};border:1px solid {ds.SUCCESS};"
                        "border-radius:3px;font-size:9px;font-weight:bold;}"
                        f"QPushButton:hover{{background:{ds.VIZ_GO_HOVER_DEEP};}}"
                    )
                    status_lbl.setText("STOPPED")
                    status_lbl.setStyleSheet(
                        f"color:{ds.VIZ_CAPTION};font-size:8px;font-family:Consolas;font-weight:bold;"
                    )
                else:
                    bot_data["running"] = True
                    run_btn.setText("■ Stop")
                    run_btn.setStyleSheet(
                        f"QPushButton{{background:{ds.VIZ_STOP_HOVER};color:{ds.ERROR};border:1px solid {ds.ERROR};"
                        "border-radius:3px;font-size:9px;font-weight:bold;}"
                        f"QPushButton:hover{{background:{ds.VIZ_STOP_HOVER_DEEP};}}"
                    )
                    status_lbl.setText("RUNNING")
                    status_lbl.setStyleSheet(
                        f"color:{ds.SUCCESS};font-size:8px;font-family:Consolas;font-weight:bold;"
                    )
                self._update_sim_summary()

            run_btn.clicked.connect(_toggle_run)

            def _remove():
                self._sim_bots.remove(bot_data)
                row.setParent(None)
                row.deleteLater()
                self._update_sim_summary()

            rem_btn.clicked.connect(_remove)

        def _create_paper_bot_row(self):
            """Append one row to ``_paper_bots`` and ``_paper_swarm_layout``."""
            idx = len(self._paper_bots) + 1
            row = QFrame()
            row.setStyleSheet(
                f"QFrame{{background:{ds.VIZ_PANEL_SURFACE};border:1px solid {ds.MENU_SURFACE};"
                "border-radius:4px;padding:2px;}"
            )
            rl = QHBoxLayout(row)
            rl.setContentsMargins(8, 4, 8, 4)
            rl.setSpacing(6)

            id_lbl = QLabel(f"PAP-{idx:02d}")
            id_lbl.setFixedWidth(48)
            id_lbl.setStyleSheet(
                f"color:{ds.ACCENT_GOLD};font-size:9px;font-weight:bold;font-family:Consolas;"
            )
            rl.addWidget(id_lbl)

            pair_edit = QComboBox()
            pair_edit.setEditable(True)
            pair_edit.addItems(
                [
                    "BTC/USDT",
                    "ETH/USDT",
                    "SOL/USDT",
                    "SPY",
                    "QQQ",
                    "GLD",
                    "AAPL",
                    "NVDA",
                ]
            )
            pair_edit.setFixedWidth(110)
            pair_edit.setToolTip(
                "Crypto: any CoinGecko pair (BTC/USDT, SHIB/USDT …)\n"
                "Equity: any Yahoo Finance ticker (SPY, AAPL, TLT …)"
            )
            rl.addWidget(pair_edit)

            src_combo = QComboBox()
            src_combo.addItems(["CoinGecko", "Kraken", "Yahoo"])
            src_combo.setFixedWidth(88)
            rl.addWidget(src_combo)

            cap_spin = QDoubleSpinBox()
            cap_spin.setRange(10, 999999)
            cap_spin.setValue(400)
            cap_spin.setPrefix("$")
            cap_spin.setFixedWidth(80)
            rl.addWidget(cap_spin)

            price_lbl = QLabel("—")
            price_lbl.setFixedWidth(72)
            price_lbl.setStyleSheet(
                f"color:{ds.PRIMARY_BRIGHT};font-size:8px;font-family:Consolas;font-weight:bold;"
            )
            rl.addWidget(price_lbl)

            pnl_lbl = QLabel("PnL: —")
            pnl_lbl.setFixedWidth(80)
            pnl_lbl.setStyleSheet(
                f"color:{ds.VIZ_CAPTION};font-size:8px;font-family:Consolas;"
            )
            rl.addWidget(pnl_lbl)

            status_lbl = QLabel("IDLE")
            status_lbl.setFixedWidth(56)
            status_lbl.setStyleSheet(
                f"color:{ds.VIZ_CAPTION};font-size:8px;font-family:Consolas;font-weight:bold;"
            )
            rl.addWidget(status_lbl)

            rl.addStretch()

            start_btn = QPushButton("▶ Start")
            start_btn.setFixedSize(62, 22)
            start_btn.setStyleSheet(
                f"QPushButton{{background:{ds.VIZ_GO_HOVER};color:{ds.SUCCESS};border:1px solid {ds.SUCCESS};"
                "border-radius:3px;font-size:9px;font-weight:bold;}"
                f"QPushButton:hover{{background:{ds.VIZ_GO_HOVER_DEEP};}}"
            )
            rl.addWidget(start_btn)

            rem_btn = QPushButton("✕")
            rem_btn.setFixedSize(22, 22)
            rem_btn.setStyleSheet(
                f"QPushButton{{background:{ds.VIZ_STOP_HOVER};color:{ds.ERROR};border:1px solid {ds.ERROR};"
                "border-radius:3px;font-size:9px;}"
                f"QPushButton:hover{{background:{ds.VIZ_STOP_HOVER_DEEP};}}"
            )
            rl.addWidget(rem_btn)

            bot_data = {
                "widget": row,
                "idx": idx,
                "pair_edit": pair_edit,
                "src_combo": src_combo,
                "cap_spin": cap_spin,
                "price_lbl": price_lbl,
                "pnl_lbl": pnl_lbl,
                "status_lbl": status_lbl,
                "start_btn": start_btn,
                "running": False,
                "paper_exch": None,
            }
            self._paper_bots.append(bot_data)

            insert_pos = self._paper_swarm_layout.count() - 1
            self._paper_swarm_layout.insertWidget(insert_pos, row)

            def _toggle():
                if bot_data["running"]:
                    bot_data["running"] = False
                    start_btn.setText("▶ Start")
                    start_btn.setStyleSheet(
                        f"QPushButton{{background:{ds.VIZ_GO_HOVER};color:{ds.SUCCESS};border:1px solid {ds.SUCCESS};"
                        "border-radius:3px;font-size:9px;font-weight:bold;}"
                        f"QPushButton:hover{{background:{ds.VIZ_GO_HOVER_DEEP};}}"
                    )
                    status_lbl.setText("STOPPED")
                    status_lbl.setStyleSheet(
                        f"color:{ds.VIZ_CAPTION};font-size:8px;font-family:Consolas;font-weight:bold;"
                    )
                else:
                    bot_data["running"] = True
                    start_btn.setText("■ Stop")
                    start_btn.setStyleSheet(
                        f"QPushButton{{background:{ds.VIZ_STOP_HOVER};color:{ds.ERROR};border:1px solid {ds.ERROR};"
                        "border-radius:3px;font-size:9px;font-weight:bold;}"
                        f"QPushButton:hover{{background:{ds.VIZ_STOP_HOVER_DEEP};}}"
                    )
                    status_lbl.setText("LIVE")
                    status_lbl.setStyleSheet(
                        f"color:{ds.ACCENT_GOLD};font-size:8px;font-family:Consolas;font-weight:bold;"
                    )
                self._update_paper_summary()

            start_btn.clicked.connect(_toggle)

            def _remove():
                bot_data["running"] = False
                self._paper_bots.remove(bot_data)
                row.setParent(None)
                row.deleteLater()
                self._update_paper_summary()

            rem_btn.clicked.connect(_remove)

        # Accent colours per layer: (border, label, dot)
        _SWARM_ACCENTS = {
            "live": (ds.SUCCESS, ds.SUCCESS, ds.SUCCESS),
            "sim": (ds.SUCCESS, ds.PRIMARY_BRIGHT, ds.SUCCESS),
            "paper": (ds.ACCENT_GOLD, ds.ACCENT_GOLD, ds.ACCENT_GOLD),
        }

        def _create_swarm_row(self, kind: str, label: str, cfg: dict):
            """Build one swarm row for ``kind`` in {live, sim, paper}.

            The handle dict carries the same keys for every kind:
            widget, dot, id_lbl, context_lbl, mode_lbl, feed_lbl,
            cap_lbl, status_lbl, metric_lbl, pnl_lbl, trades_lbl, kind.
            """
            border, label_color, dot_color = self._SWARM_ACCENTS.get(
                kind, self._SWARM_ACCENTS["sim"]
            )

            bg_tint = {
                "live": ds.VIZ_LANE_LIVE,
                "sim": ds.VIZ_LANE_LIVE,
                "paper": ds.VIZ_LANE_PAPER,
            }.get(kind, ds.VIZ_PANEL_SURFACE)

            row = QFrame()
            row.setStyleSheet(
                f"QFrame{{background:{bg_tint};border:1px solid {border};"
                f"border-radius:4px;}}"
            )
            rl = QHBoxLayout(row)
            rl.setContentsMargins(8, 4, 8, 4)
            rl.setSpacing(6)

            dot = QLabel("●")
            dot.setFixedWidth(12)
            dot.setStyleSheet(
                f"color:{dot_color};font-size:10px;font-weight:bold;"
                f"background:transparent;"
            )
            rl.addWidget(dot)

            id_lbl = QLabel(label)
            id_lbl.setFixedWidth(80)
            id_lbl.setStyleSheet(
                f"color:{label_color};font-size:9px;font-weight:bold;"
                f"font-family:Consolas;background:transparent;"
            )
            rl.addWidget(id_lbl)

            context_lbl = QLabel(
                cfg.get("context", cfg.get("pair", cfg.get("asset", "—")))
            )
            context_lbl.setFixedWidth(88)
            context_lbl.setStyleSheet(
                f"color:{ds.PRIMARY_BRIGHT};font-size:9px;font-weight:bold;"
                "font-family:Consolas;background:transparent;"
            )
            rl.addWidget(context_lbl)

            mode_lbl = QLabel(cfg.get("mode", "—"))
            mode_lbl.setFixedWidth(72)
            mode_lbl.setStyleSheet(
                f"color:{ds.CARD_METRIC_LABEL};font-size:8px;font-family:Consolas;"
                "background:transparent;"
            )
            rl.addWidget(mode_lbl)

            # feed: timeframe for sim, data source for paper and live.
            feed_lbl = QLabel(
                cfg.get("feed", cfg.get("timeframe", cfg.get("source", "—")))
            )
            feed_lbl.setFixedWidth(60)
            feed_lbl.setStyleSheet(
                f"color:{ds.VIZ_CAPTION_DIM};font-size:8px;font-family:Consolas;"
                "background:transparent;"
            )
            rl.addWidget(feed_lbl)

            cap_lbl = QLabel(f"${cfg.get('capital', 0):,.0f}")
            cap_lbl.setFixedWidth(58)
            cap_lbl.setStyleSheet(
                f"color:{ds.VIZ_CAPTION_DIM};font-size:8px;font-family:Consolas;"
                "background:transparent;"
            )
            rl.addWidget(cap_lbl)

            initial_status = cfg.get("status", "RUNNING")
            status_lbl = QLabel(initial_status)
            status_lbl.setFixedWidth(60)
            status_lbl.setStyleSheet(
                f"color:{label_color};font-size:8px;font-family:Consolas;"
                f"font-weight:bold;background:transparent;"
            )
            rl.addWidget(status_lbl)

            # metric: progress share for sim, price for live and paper.
            metric_lbl = QLabel(cfg.get("metric_init", "—"))
            metric_lbl.setFixedWidth(58)
            metric_lbl.setStyleSheet(
                f"color:{ds.VIZ_CAPTION};font-size:8px;font-family:Consolas;"
                "background:transparent;"
            )
            rl.addWidget(metric_lbl)

            pnl_lbl = QLabel("PnL —")
            pnl_lbl.setFixedWidth(88)
            pnl_lbl.setStyleSheet(
                f"color:{ds.VIZ_CAPTION};font-size:8px;font-family:Consolas;"
                "background:transparent;"
            )
            rl.addWidget(pnl_lbl)

            trades_lbl = QLabel("0 trades")
            trades_lbl.setFixedWidth(68)
            trades_lbl.setStyleSheet(
                f"color:{ds.VIZ_CAPTION};font-size:8px;font-family:Consolas;"
                "background:transparent;"
            )
            rl.addWidget(trades_lbl)

            rl.addStretch()

            return {
                "kind": kind,
                "widget": row,
                "dot": dot,
                "id_lbl": id_lbl,
                "context_lbl": context_lbl,
                "mode_lbl": mode_lbl,
                "feed_lbl": feed_lbl,
                "cap_lbl": cap_lbl,
                "status_lbl": status_lbl,
                "metric_lbl": metric_lbl,
                "pnl_lbl": pnl_lbl,
                "trades_lbl": trades_lbl,
                "_accent": label_color,
                "running": True,
                "total_candles": cfg.get("candle_total", 0),
            }

        def _apply_stopped_style(self, handle: dict):
            """Clear a row handle's ``running`` flag and mute its colours."""
            handle["running"] = False
            handle["dot"].setStyleSheet(
                f"color:{ds.VIZ_CAPTION};font-size:10px;font-weight:bold;"
                "background:transparent;"
            )
            handle["widget"].setStyleSheet(
                f"QFrame{{background:{ds.VIZ_PANEL_SURFACE};border:1px solid {ds.VIZ_PANEL_BORDER};"
                "border-radius:4px;}"
            )
            handle["status_lbl"].setStyleSheet(
                f"color:{ds.VIZ_CAPTION};font-size:8px;font-family:Consolas;"
                "font-weight:bold;background:transparent;"
            )

        def _apply_pnl_color(self, handle: dict, pnl: float):
            """Colour a row's ``pnl_lbl`` by the sign of ``pnl``."""
            col = ds.SUCCESS if pnl >= 0 else ds.ERROR
            handle["pnl_lbl"].setText(f"PnL {pnl:+,.2f}")
            handle["pnl_lbl"].setStyleSheet(
                f"color:{col};font-size:8px;font-family:Consolas;"
                f"background:transparent;"
            )

        def register_sim_run(self, sim_id: str, label: str, cfg: dict):
            """Add one ``_live_sim_rows`` entry for an active sim.

            ``_create_swarm_row`` builds the widget; the returned handle
            carries ``update`` and ``stop``.
            """
            _dur_t0 = time.monotonic()
            self._remove_live_sim(sim_id)

            unified_cfg = {
                "context": cfg.get("asset", cfg.get("label", label)),
                "mode": cfg.get("mode", "SIM"),
                "feed": cfg.get("timeframe", "—"),
                "capital": cfg.get("capital", 0),
                "status": "RUNNING",
                "metric_init": "0%",
                "candle_total": cfg.get("candle_total", 1),
            }
            handle = self._create_swarm_row("sim", label, unified_cfg)
            handle["sim_id"] = sim_id

            insert_pos = self._sim_swarm_layout.count() - 1
            self._sim_swarm_layout.insertWidget(insert_pos, handle["widget"])

            # Timed before the emitter, which is not billed to the registration.
            _dur_elapsed = time.monotonic() - _dur_t0
            self._live_sim_rows[sim_id] = handle
            # `actual` is read back out of the store, never from the argument.
            try:
                from src.core.signal_contract import emit as _sw_emit

                _sw_emit(
                    "swarm.11.001.postcondition.sim_run_registered",
                    actual=(self._live_sim_rows.get(sim_id, {}) or {}).get("kind"),
                    expected="sim",
                    duration=_dur_elapsed,
                    context={
                        "layer": "sim",
                        "id": str(sim_id),
                        "rows_in_layer": len(self._live_sim_rows),
                    },
                )
            except Exception:  # noqa: BLE001,S110 - advisory
                pass
            self._update_sim_summary()
            return handle

        def update_sim_run(
            self, sim_id: str, pnl: float, trades: int, candle_idx: int = 0
        ):
            """Update one ``_live_sim_rows`` row from a sim tick."""
            h = self._live_sim_rows.get(sim_id)
            if h is None:
                return
            total = max(1, h.get("total_candles", 1))
            pct = min(100, int(candle_idx / total * 100))
            h["metric_lbl"].setText(f"{pct}%")
            self._apply_pnl_color(h, pnl)
            h["trades_lbl"].setText(f"{trades} trades")
            h["_pnl"] = pnl
            self._update_sim_summary()

        def stop_sim_run(self, sim_id: str, pnl: float = 0.0, trades: int = 0):
            """Mark one ``_live_sim_rows`` row stopped."""
            h = self._live_sim_rows.get(sim_id)
            if h is None:
                return
            self._apply_stopped_style(h)
            h["status_lbl"].setText("DONE")
            self._apply_pnl_color(h, pnl)
            h["trades_lbl"].setText(f"{trades} trades")
            h["metric_lbl"].setText("100%")
            self._update_sim_summary()

        def _remove_live_sim(self, sim_id: str):
            h = self._live_sim_rows.pop(sim_id, None)
            if h:
                h["widget"].setParent(None)
                h["widget"].deleteLater()

        def register_paper_run(self, paper_id: str, label: str, cfg: dict):
            """Add one ``_live_paper_rows`` entry for a paper session.

            ``_create_swarm_row`` builds the widget; the source lands in
            the feed column and the price in the metric column.
            """
            _dur_t0 = time.monotonic()
            self._remove_live_paper(paper_id)

            unified_cfg = {
                "context": cfg.get("pair", "—"),
                "mode": cfg.get("mode", "PAPER"),
                "feed": cfg.get("source", "—"),
                "capital": cfg.get("capital", 0),
                "status": "LIVE",
                "metric_init": "—",
            }
            handle = self._create_swarm_row("paper", label, unified_cfg)
            handle["paper_id"] = paper_id

            insert_pos = self._paper_swarm_layout.count() - 1
            self._paper_swarm_layout.insertWidget(insert_pos, handle["widget"])

            # Timed before the emitter, which is not billed to the registration.
            _dur_elapsed = time.monotonic() - _dur_t0
            self._live_paper_rows[paper_id] = handle
            # `actual` is read back out of the store, never from the argument.
            try:
                from src.core.signal_contract import emit as _sw_emit

                _sw_emit(
                    "swarm.11.002.postcondition.paper_run_registered",
                    actual=(self._live_paper_rows.get(paper_id, {}) or {}).get("kind"),
                    expected="paper",
                    duration=_dur_elapsed,
                    context={
                        "layer": "paper",
                        "id": str(paper_id),
                        "rows_in_layer": len(self._live_paper_rows),
                    },
                )
            except Exception:  # noqa: BLE001,S110 - advisory
                pass
            self._update_paper_summary()
            return handle

        def update_paper_run(
            self, paper_id: str, price: float, pnl: float, trades: int
        ):
            """Update one ``_live_paper_rows`` row from a paper tick."""
            h = self._live_paper_rows.get(paper_id)
            if h is None:
                return
            p_str = f"${price:,.4f}" if price < 1000 else f"${price:,.2f}"
            h["metric_lbl"].setText(p_str)
            h["metric_lbl"].setStyleSheet(
                f"color:{ds.PRIMARY_BRIGHT};font-size:8px;font-family:Consolas;"
                "background:transparent;"
            )
            self._apply_pnl_color(h, pnl)
            h["trades_lbl"].setText(f"{trades} trades")
            h["_pnl"] = pnl
            self._update_paper_summary()

        def stop_paper_run(self, paper_id: str, pnl: float = 0.0, trades: int = 0):
            """Mark one ``_live_paper_rows`` row stopped."""
            h = self._live_paper_rows.get(paper_id)
            if h is None:
                return
            self._apply_stopped_style(h)
            h["status_lbl"].setText("STOPPED")
            self._apply_pnl_color(h, pnl)
            h["trades_lbl"].setText(f"{trades} trades")
            self._update_paper_summary()

        def _remove_live_paper(self, paper_id: str):
            h = self._live_paper_rows.pop(paper_id, None)
            if h:
                h["widget"].setParent(None)
                h["widget"].deleteLater()

        def register_live_run(self, bot_id: str, label: str, cfg: dict):
            """Add one ``_live_bot_rows`` entry for a real-exchange bot.

            ``cfg`` carries pair or asset, mode, timeframe or source,
            and capital.
            """
            self._remove_live_bot_row(bot_id)

            unified_cfg = {
                "context": cfg.get("pair", cfg.get("asset", "—")),
                "mode": cfg.get("mode", "LIVE"),
                "feed": cfg.get("timeframe", cfg.get("source", "—")),
                "capital": cfg.get("capital", 0),
                "status": "RUNNING",
                "metric_init": cfg.get("metric_init", "—"),
            }
            handle = self._create_swarm_row("live", label, unified_cfg)
            handle["bot_id"] = bot_id

            if hasattr(self, "_live_rows_empty"):
                self._live_rows_empty.setVisible(False)
            self._live_rows_scroll.setVisible(True)
            insert_pos = self._live_rows_layout.count() - 1
            self._live_rows_layout.insertWidget(insert_pos, handle["widget"])

            self._live_bot_rows[bot_id] = handle
            return handle

        def update_live_run(
            self,
            bot_id: str,
            price: float = 0.0,
            pnl: float = 0.0,
            trades: int = 0,
            status: str = None,
        ):
            """Update one ``_live_bot_rows`` row from a bot tick."""
            h = self._live_bot_rows.get(bot_id)
            if h is None:
                return
            if status is not None:
                h["status_lbl"].setText(status)
            if price > 0:
                p_str = f"${price:,.4f}" if price < 1000 else f"${price:,.2f}"
                h["metric_lbl"].setText(p_str)
                h["metric_lbl"].setStyleSheet(
                    f"color:{ds.PRIMARY_BRIGHT};font-size:8px;font-family:Consolas;"
                    "background:transparent;"
                )
            self._apply_pnl_color(h, pnl)
            h["trades_lbl"].setText(f"{trades} trades")
            h["_pnl"] = pnl

        def stop_live_run(self, bot_id: str, pnl: float = 0.0, trades: int = 0):
            """Mark one ``_live_bot_rows`` row stopped."""
            h = self._live_bot_rows.get(bot_id)
            if h is None:
                return
            self._apply_stopped_style(h)
            h["status_lbl"].setText("STOPPED")
            self._apply_pnl_color(h, pnl)
            h["trades_lbl"].setText(f"{trades} trades")

        def _remove_live_bot_row(self, bot_id: str):
            h = self._live_bot_rows.pop(bot_id, None)
            if h:
                h["widget"].setParent(None)
                h["widget"].deleteLater()
            if not self._live_bot_rows and hasattr(self, "_live_rows_empty"):
                self._live_rows_empty.setVisible(True)
                self._live_rows_scroll.setVisible(False)

        def _update_sim_summary(self):
            running = sum(1 for b in self._sim_bots if b.get("running"))
            running += sum(1 for h in self._live_sim_rows.values() if h.get("running"))
            total = len(self._sim_bots) + len(self._live_sim_rows)
            self._sim_swarm_wins.setText(f"Bots: {running}/{total} running")
            pnls = [h.get("_pnl", 0) for h in self._live_sim_rows.values()]
            if pnls:
                self._sim_swarm_pnl.setText(f"Total PnL: ${sum(pnls):+,.2f}")
            else:
                self._sim_swarm_pnl.setText("Total PnL: —")
            self._sim_swarm_trades.setText("Aggregate trades: —")

        def _update_paper_summary(self):
            running = sum(1 for b in self._paper_bots if b.get("running"))
            total_cap = sum(b["cap_spin"].value() for b in self._paper_bots)
            self._paper_swarm_active.setText(
                f"Active: {running}/{len(self._paper_bots)}"
            )
            self._paper_swarm_total.setText(f"Total Capital: ${total_cap:,.0f}")
            self._paper_swarm_pnl.setText("Net PnL: —")

        def _reposition_wire_canvas(self):
            """Size ``_wire_canvas`` to the bot grid and nothing wider.

            The canvas takes mouse events, and a wider rectangle would
            swallow clicks outside the grid.
            """
            from PySide6.QtCore import QRect

            if hasattr(self, "_grid_widget") and self._grid_widget is not None:
                rect = self._grid_widget.rect()
                origin = self._grid_widget.mapTo(self, rect.topLeft())
                self._wire_canvas.setGeometry(QRect(origin, rect.size()))
            elif hasattr(self, "_viz_tab") and self._viz_tab is not None:
                rect = self._viz_tab.rect()
                origin = self._viz_tab.mapTo(self, rect.topLeft())
                self._wire_canvas.setGeometry(QRect(origin, rect.size()))
            else:
                self._wire_canvas.setGeometry(self.rect())

        def resizeEvent(self, event):
            super().resizeEvent(event)
            # Repositioned while hidden: a List-mode resize would leave stale geometry.
            self._reposition_wire_canvas()
            if self._wire_canvas.isVisible():
                self._wire_canvas.raise_()

        def _on_theme_changed(self):
            self._theme_key = self._theme_combo.currentData()
            for widget in self._bot_widgets.values():
                widget.set_theme(self._theme_key)

        def set_app_theme(self, theme_name: str) -> None:
            """Read every locust's growth-stage colours from theme_name."""
            self._app_theme_name = str(theme_name or "")
            for widget in self._bot_widgets.values():
                widget.set_app_theme(self._app_theme_name)

        def _refresh_bot_swarm_privacy_dot(self) -> None:
            """Draw the identifier privacy dot in the theme accent colour.

            The dot is filled while identifiers are revealed and hollow
            while they are masked.
            """
            try:
                if _get_privacy_mask_registry is None:
                    self._bot_swarm_privacy_dot.setText("●")
                    return
                reg = _get_privacy_mask_registry()
                masked = reg.is_masked("bot_swarm.identifiers")
            except Exception:  # a registry failure must not abort the paint
                masked = False
            glyph = "○" if masked else "●"
            self._bot_swarm_privacy_dot.setText(glyph)
            self._bot_swarm_privacy_dot.setStyleSheet(
                f"QLabel{{color:{ds.PRIMARY_BRIGHT};background:transparent;"
                "padding:0 4px;font-size:14px;}"
            )

        def _toggle_bot_swarm_identifier_mask(self) -> None:
            """Flip the shared ``bot_swarm.identifiers`` mask.

            The privacy dot, the Privacy Mode button and every
            ``BotNodeWidget`` repaint; a registry failure writes to
            stderr and recolours the dot.
            """
            try:
                if _get_privacy_mask_registry is None:
                    sys.stderr.write(
                        "[bot_swarm] WARNING: privacy_mask_registry "
                        "import unavailable — click NO-OP\n"
                    )
                    self._bot_swarm_privacy_dot.setStyleSheet(
                        f"QFrame{{background:{ds.VIZ_NUCLEAR_SURFACE};border:1px solid "
                        f"{ds.VIZ_NUCLEAR_BORDER};border-radius:3px;}}"
                        "/* wiring-broken indicator */"
                    )
                    return
                reg = _get_privacy_mask_registry()
                cur = reg.is_masked("bot_swarm.identifiers")
                reg.set_masked("bot_swarm.identifiers", not cur)
            except Exception as exc:
                sys.stderr.write(
                    f"[bot_swarm] WARNING: identifier mask toggle "
                    f"failed: {type(exc).__name__}: {exc}\n"
                )
                self._bot_swarm_privacy_dot.setStyleSheet(
                    f"QFrame{{background:{ds.VIZ_NUCLEAR_SURFACE};border:1px solid "
                    f"{ds.VIZ_NUCLEAR_BORDER};border-radius:3px;}}"
                    "/* wiring-broken indicator */"
                )
                return
            self._refresh_bot_swarm_privacy_dot()
            self._refresh_privacy_mode_btn()
            for w in self._bot_widgets.values():
                w.update()
            # The Source and Destination labels re-read the mask on re-render.
            self._rebuild_quick_routing_scope_in_place()

        def _refresh_privacy_mode_btn(self) -> None:
            """Draw the Privacy Mode button.

            It is green while any mask is on and muted while every mask
            is off.
            """
            try:
                if _get_privacy_mask_registry is None:
                    self._privacy_mode_btn.setText("Privacy Mode: OFF")
                    return
                reg = _get_privacy_mask_registry()
                snap = reg.to_dict()
                any_on = any(bool(v) for v in snap.values())
            except Exception:
                any_on = False
            if any_on:
                self._privacy_mode_btn.setText("Privacy Mode: ON")
                self._privacy_mode_btn.setStyleSheet(
                    f"QPushButton{{background:{ds.VIZ_CONFIRM_SURFACE};color:{ds.SUCCESS};"
                    f"border:1px solid {ds.SUCCESS};border-radius:3px;"
                    "padding:3px 12px;font-weight:bold;}"
                )
            else:
                self._privacy_mode_btn.setText("Privacy Mode: OFF")
                self._privacy_mode_btn.setStyleSheet(
                    f"QPushButton{{background:{ds.VIZ_PANEL_SURFACE};color:{ds.TEXT_INACTIVE};"
                    f"border:1px solid {ds.CARD_METRIC_BORDER};border-radius:3px;"
                    "padding:3px 12px;}"
                )

        def _on_privacy_mode_btn_clicked(self) -> None:
            """Turn every mask in the shared registry on, or every one off.

            A registry failure writes to stderr and recolours the
            Privacy Mode button.
            """
            try:
                if _get_privacy_mask_registry is None:
                    sys.stderr.write(
                        "[bot_swarm] WARNING: privacy_mask_registry "
                        "import unavailable — Privacy Mode click "
                        "NO-OP\n"
                    )
                    self._privacy_mode_btn.setStyleSheet(
                        f"QPushButton{{background:{ds.VIZ_NUCLEAR_SURFACE};color:white;"
                        f"border:1px solid {ds.VIZ_NUCLEAR_BORDER};padding:3px 12px;}}"
                        "/* wiring-broken */"
                    )
                    return
                reg = _get_privacy_mask_registry()
                snap = reg.to_dict()
                any_on = any(bool(v) for v in snap.values())
                reg.set_all(not any_on)
            except Exception as exc:
                sys.stderr.write(
                    f"[bot_swarm] WARNING: Privacy Mode toggle "
                    f"failed: {type(exc).__name__}: {exc}\n"
                )
                self._privacy_mode_btn.setStyleSheet(
                    f"QPushButton{{background:{ds.VIZ_NUCLEAR_SURFACE};color:white;"
                    f"border:1px solid {ds.VIZ_NUCLEAR_BORDER};padding:3px 12px;}}"
                    "/* wiring-broken */"
                )
                return
            self._refresh_privacy_mode_btn()
            self._refresh_bot_swarm_privacy_dot()
            for w in self._bot_widgets.values():
                w.update()
            # The Source and Destination labels re-read the masks on re-render.
            self._rebuild_quick_routing_scope_in_place()

        def _rebuild_quick_routing_scope_in_place(self) -> None:
            """Rebuild the ``_quick_routing_matrix`` lists over the shown
            bots, and do nothing while the matrix holds none.
            """
            mx = getattr(self, "_quick_routing_matrix", None)
            if mx is None:
                return
            ids = list(getattr(mx, "_last_scope_ids", []) or [])
            if not ids:
                # No prior scope tracked: rebuild from the QListWidget items.
                ids = [
                    mx._source_list.item(i).data(Qt.UserRole) or ""
                    for i in range(mx._source_list.count())
                ]
                ids = [b for b in ids if b]
            mx.rebuild_scope(ids)

        def _bot_exchange_id(self, bot_id: str) -> str:
            """Return a bot's exchange id from the status data it holds.

            The value comes from the widget, never from a disk read;
            unknown returns "".
            """
            w = self._bot_widgets.get(bot_id)
            data = getattr(w, "_bot_data", None) if w is not None else None
            if isinstance(data, dict):
                return str(data.get("exchange", "") or "")
            return ""

        def _all_bot_ids_in_scope(self) -> list[str]:
            """Return the bot ids the Quick Routing matrix may route.

            The Exchange selector narrows the list; an empty selection
            returns every id in ``_bot_widgets``.
            """
            sel = ""
            try:
                sel = str(self._exchange_combo.currentData() or "")
            except Exception:
                sel = ""
            ids = list(self._bot_widgets.keys())
            if not sel:
                return ids
            return [bid for bid in ids if self._bot_exchange_id(bid) == sel]

        def _rebuild_exchange_selector_items(self) -> None:
            """Refill ``_exchange_combo`` from the swarm's exchange ids.

            An "All" entry heads the list.
            """
            try:
                combo = self._exchange_combo
            except AttributeError:
                return
            current = ""
            try:
                current = str(combo.currentData() or "")
            except Exception:
                current = ""
            distinct = set()
            for bid in self._bot_widgets.keys():
                eid = self._bot_exchange_id(bid)
                if eid:
                    distinct.add(eid)
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("All", "")
            for eid in sorted(distinct):
                combo.addItem(eid, eid)
            if current:
                for i in range(combo.count()):
                    if str(combo.itemData(i) or "") == current:
                        combo.setCurrentIndex(i)
                        break
            combo.blockSignals(False)

        def _refresh_visible_bots(self) -> None:
            """Hide every ``BotNodeWidget`` the Exchange selector omits.

            A hidden widget stays alive and keeps its wire ends.
            """
            sel = ""
            try:
                sel = str(self._exchange_combo.currentData() or "")
            except Exception:
                sel = ""
            for bid, w in self._bot_widgets.items():
                if not sel:
                    w.setVisible(True)
                    continue
                w.setVisible(self._bot_exchange_id(bid) == sel)

        def _refresh_quick_routing_scope(self) -> None:
            """Re-sync ``_quick_routing_matrix`` to the filtered bot set."""
            mx = getattr(self, "_quick_routing_matrix", None)
            if mx is not None and hasattr(mx, "rebuild_scope"):
                try:  # noqa: SIM105
                    mx.rebuild_scope(self._all_bot_ids_in_scope())
                except Exception:  # noqa: S110
                    pass

        def _on_exchange_filter_changed(self, *_a) -> None:
            self._refresh_visible_bots()
            self._refresh_quick_routing_scope()
            if hasattr(self, "_wire_canvas") and self._wire_canvas:
                self._wire_canvas.update()

        def _on_wire_opacity_changed(self, value: int) -> None:
            self._wire_opacity_pct = int(value)
            if hasattr(self, "_wire_canvas") and self._wire_canvas:
                self._wire_canvas.update()

        # A wire is stored once, at the top level, under smart_wires.
        def _load_bot_state_dict(self) -> dict:
            try:
                from ..core.state_manager import StateManager

                return StateManager().load_state() or {}
            except Exception:
                return {}

        def _save_bot_state_dict(self, state: dict) -> None:
            """Write bot_state.json through ``atomic_write_json``.

            A ``state`` carrying no ``bots`` key is refused, because
            ``_load_bot_state_dict`` answers an empty dict when the read
            fails.
            """
            from .main_tabs import bot_visualizer_surface as surface

            if not isinstance(state, dict) or surface.BOTS_KEY not in state:
                logger.error(
                    "bot_visualizer: refusing to write bot_state.json from a "
                    "load carrying no %r key; the file is left as it is",
                    surface.BOTS_KEY,
                )
                return
            try:
                from pathlib import Path

                from ..core.io_utils import atomic_write_json

                p = Path.home() / ".acervator" / "bot_state.json"
                atomic_write_json(p, state, indent=2, default=str)
            except Exception as exc:  # noqa: BLE001 - GUI must not die
                logger.error(
                    "bot_visualizer: direct write to bot_state.json "
                    "FAILED (%s: %s). Wire routing changes made in the "
                    "GUI were not persisted by this path; the durable "
                    "smart_wires channel is unaffected.",
                    type(exc).__name__,
                    exc,
                )

        def _apply_routes_to_state(
            self, add: list[tuple[str, str, float]], remove: list[tuple[str, str]]
        ) -> None:
            """Write every ``add`` wire and drop every ``remove`` wire, then save.

            ``bot_visualizer_surface.apply_routes`` holds the wires under
            the key the next launch reads.
            """
            from .main_tabs import bot_visualizer_surface as surface

            state = self._load_bot_state_dict()
            surface.apply_routes(state, list(add), list(remove))
            self._save_bot_state_dict(state)
            logger.info(
                "Quick Routing: %d wire(s) written and %d removed in %s",
                len(add),
                len(remove),
                surface.WIRES_KEY,
            )

        def _clear_all_routes_in_state(self) -> list[tuple[str, str]]:
            """Empty the stored wire list and answer the pairs that were in it.

            Each pair is one ``wire.removed`` the caller emits, which
            ``BotManager._on_wire_removed_mgr`` turns into an
            ``unregister_wire`` on the topology's owner.
            """
            from .main_tabs import bot_visualizer_surface as surface

            state = self._load_bot_state_dict()
            removed_pairs = [
                (str(source), str(target))
                for source, target in surface.clear_all_routes(state)
            ]
            self._save_bot_state_dict(state)
            logger.info(
                "Disconnect All: %d wire(s) removed from %s",
                len(removed_pairs),
                surface.WIRES_KEY,
            )
            return removed_pairs

        def _report_wire_hydration_shortfall(
            self,
            painted: int,
            seen: int,
            rejected: int,
        ) -> None:
            """Log each stored route that did not reach ``_wires``.

            Writes nothing when every route was painted.
            """
            if painted == seen:
                return
            logger.warning(
                "wire hydration: %d of %d route(s) in"
                " bot_state.json painted -- %d rejected by the"
                " bus, %d unusable; the wire overlay"
                " under-reports the state file",
                painted,
                seen,
                rejected,
                seen - painted - rejected,
            )

        def _hydrate_wires_from_disk(self) -> int:
            """Emit one ``wire.created`` per stored wire and return the count.

            ``_on_external_wire_created`` receives them, and any wire
            that does not reach ``_wires`` is recorded first.
            """
            from .main_tabs import bot_visualizer_surface as surface

            plan = surface.hydration_plan(self._load_bot_state_dict())
            n = 0
            rejected = 0
            try:
                from ..core.event_bus import get_event_bus

                bus = get_event_bus()
            except Exception:
                logger.exception(
                    "wire hydration: no event bus, so no wire in"
                    " bot_state.json reaches the canvas"
                )
                return 0
            for source, target, pct in plan["events"]:
                try:
                    bus.emit(
                        "wire.created", source_id=source, target_id=target, pct=pct
                    )
                    n += 1
                except Exception:
                    rejected += 1
                    logger.warning(
                        "wire hydration: the bus rejected wire"
                        " %s -> %s (%s%%), so that wire is not"
                        " painted",
                        source,
                        target,
                        pct,
                        exc_info=True,
                    )
            self._report_wire_hydration_shortfall(n, plan["seen"], rejected)
            return n

        def _animate(self):
            now = time.monotonic()
            dt = now - self._last_time
            self._last_time = now
            for widget in self._bot_widgets.values():
                widget.animate(dt)
            for wire in self._wires:
                wire["phase"] = wire.get("phase", 0) + dt * 2.5
            if self._wires or self._dragging_wire:
                # Raised every frame: bots coming and going would drift the order.
                if self._wire_canvas.isVisible():
                    self._wire_canvas.raise_()
                self._wire_canvas.update()
            if self._frame_cadence.due(now):
                self._report_frame_cadence(now)

        def observe_frame(self, started: float, work_ms: float) -> None:
            """Take one wire-canvas paint's start time and its work, in milliseconds.

            ``_WireCanvas.paintEvent`` calls this at the end of every paint it
            draws, which is the cadence the operator watches.
            """
            self._frame_cadence.observe(started, work_ms)

        def _report_frame_cadence(self, now: float) -> None:
            """Emit one window of animation frame gaps on the cadence pin.

            ``actual`` is how many gaps in the window ran past the frame
            budget, which is the stutter count, and the context carries the
            window's median, 95th and worst gap in milliseconds.
            """
            from .main_tabs import bot_visualizer_surface as surface

            window = self._frame_cadence.take(now)
            context = dict(window)
            context["wires"] = len(self._wires)
            context["cards"] = len(self._bot_widgets)
            try:
                from src.core.signal_contract import emit as _sw_emit

                _sw_emit(
                    surface.FRAME_CADENCE_SIGNAL,
                    actual=window["late_frames"],
                    expected=surface.NO_LATE_FRAMES,
                    context=context,
                )
            except Exception:  # noqa: BLE001,S110 - advisory
                pass

        def _get_bot_center(self, bot_id: str) -> Optional[QPointF]:
            """Return a ``BotNodeWidget`` centre in ``_wire_canvas`` coordinates."""
            w = self._bot_widgets.get(bot_id)
            if not w:
                return None
            center = QPointF(w.width() / 2, w.height() / 2)
            global_pt = w.mapToGlobal(center.toPoint())
            local_pt = self._wire_canvas.mapFromGlobal(global_pt)
            return QPointF(local_pt)

        def _bot_at_pos(self, pos: QPointF) -> str:
            """Return the ``BotNodeWidget`` under a ``_wire_canvas`` position."""
            for bid, w in self._bot_widgets.items():
                global_pt = self._wire_canvas.mapToGlobal(pos.toPoint())
                local_pt = w.mapFromGlobal(global_pt)
                if w.rect().contains(local_pt):
                    return bid
            return ""

        def _start_wire_drag(self, bot_id: str, pos: QPointF):
            self._dragging_wire = True
            self._wire_start_id = bot_id
            self._wire_mouse_pos = pos

        def _update_wire_drag(self, pos: QPointF):
            self._wire_mouse_pos = pos
            self._wire_canvas.update()

        def _confirm_wire_removal(self, pairs: list, why: str = "") -> bool:
            """Ask before removing wires, and return True to proceed.

            ``remove_wire`` emits ``wire.removed``, which reaches
            ``SmartWireManager.unregister_wire`` with no undo. The dialog
            defaults to No and names each wire's rate.
            """
            if not pairs:
                return False
            lines = []
            for src, dst in pairs:
                pct = next(
                    (
                        w.get("pct")
                        for w in self._wires
                        if w.get("source_id") == src and w.get("target_id") == dst
                    ),
                    None,
                )
                pct_txt = f" at {pct}%" if pct is not None else ""
                lines.append(f"  • {src[:8]} → {dst[:8]}{pct_txt}")
            body = (
                f"{why}\n\n" if why else ""
            ) + f"Disconnect {len(pairs)} Smart Wire" + (
                "s" if len(pairs) != 1 else ""
            ) + "?\n\n" + "\n".join(
                lines
            ) + "\n\nThis stops profit routing between these bots and " "cannot be undone."
            try:
                reply = QMessageBox.question(
                    self,
                    "Disconnect Smart Wire?",
                    body,
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                return reply == QMessageBox.Yes
            except Exception as exc:  # noqa: BLE001
                # A dialog that cannot be shown refuses the removal.
                logger.error(
                    "wire-removal confirmation could not be shown (%s); "
                    "refusing the removal",
                    exc,
                )
                return False

        def _finish_wire_drag(self, pos: QPointF):
            target_id = self._bot_at_pos(pos)
            start_id = self._wire_start_id
            self._dragging_wire = False
            self._wire_mouse_pos = None

            if not start_id:
                self._wire_canvas.update()
                return

            if target_id and target_id != start_id:
                existing = [
                    w
                    for w in self._wires
                    if w["source_id"] == start_id and w["target_id"] == target_id
                ]
                if existing:
                    # An already-wired pair is confirmed before the drag disconnects it.
                    if not self._confirm_wire_removal(
                        [(start_id, target_id)],
                        "Dragging between two already-connected bots "
                        "disconnects them.",
                    ):
                        self._wire_start_id = ""
                        self._wire_canvas.update()
                        return
                    self.remove_wire(start_id, target_id)
                else:
                    self._show_wire_config(start_id, target_id)
            elif not target_id:
                wire_from_start = [w for w in self._wires if w["source_id"] == start_id]
                if len(wire_from_start) == 1:
                    # A release a few px off a locust edge reaches here with no picker.
                    if not self._confirm_wire_removal(
                        [
                            (
                                wire_from_start[0]["source_id"],
                                wire_from_start[0]["target_id"],
                            )
                        ],
                        "Releasing a drag on empty space disconnects "
                        "the source bot's only outgoing wire.",
                    ):
                        self._wire_start_id = ""
                        self._wire_canvas.update()
                        return
                    self.remove_wire(
                        wire_from_start[0]["source_id"], wire_from_start[0]["target_id"]
                    )
                elif len(wire_from_start) > 1:
                    self._show_disconnect_picker(start_id, pos)

            self._wire_start_id = ""
            self._wire_canvas.update()

        def _show_disconnect_picker(self, bot_id: str, pos: QPointF):
            """Offer a menu of a bot's wires and remove the one chosen."""
            menu = QMenu(self)
            menu.setStyleSheet(
                f"QMenu {{ background: {ds.MENU_SURFACE}; color: {ds.TEXT_HIGH}; border: 1px solid {ds.MENU_BORDER}; }}"
                f"QMenu::item:selected {{ background: {ds.MENU_ITEM_SELECTED}; }}"
            )

            outgoing = [w for w in self._wires if w["source_id"] == bot_id]
            incoming = [w for w in self._wires if w["target_id"] == bot_id]

            if outgoing:
                header = menu.addAction("Disconnect outgoing wire:")
                header.setEnabled(False)
                for w in outgoing:
                    tgt = w["target_id"][:8]
                    act = menu.addAction(f"  → {tgt} ({w['pct']}%)")
                    act.setData(("out", w["source_id"], w["target_id"]))

            if incoming:
                if outgoing:
                    menu.addSeparator()
                header = menu.addAction("Disconnect incoming wire:")
                header.setEnabled(False)
                for w in incoming:
                    src = w["source_id"][:8]
                    act = menu.addAction(f"  ← {src} ({w['pct']}%)")
                    act.setData(("in", w["source_id"], w["target_id"]))

            menu.addSeparator()
            menu.addAction("Cancel")

            global_pos = self._wire_canvas.mapToGlobal(pos.toPoint())
            result = menu.exec(global_pos)

            if result and result.data():
                _, src, tgt = result.data()
                self.remove_wire(src, tgt)

        def _show_wire_config(self, source_id: str, target_id: str):
            """Ask for a wire's pct and write it back through ``_save_bot_state``."""
            from PySide6.QtWidgets import (
                QDialog,
                QFormLayout,
                QSpinBox,
                QDialogButtonBox,
            )

            dlg = QDialog(self)
            dlg.setWindowTitle("Configure Profit Wire")
            dlg.setMinimumWidth(350)
            form = QVBoxLayout(dlg)

            form.addWidget(
                QLabel(
                    f"Route profits from bot {source_id[:8]}\n"
                    f"to bot {target_id[:8]}"
                )
            )

            params = QFormLayout()
            pct_spin = QSpinBox()
            pct_spin.setRange(1, 100)
            pct_spin.setValue(50)
            pct_spin.setSuffix("% of realized profit")
            params.addRow("Routing:", pct_spin)
            form.addLayout(params)

            btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            btns.accepted.connect(dlg.accept)
            btns.rejected.connect(dlg.reject)
            form.addWidget(btns)

            if dlg.exec() == QDialog.Accepted:
                pct = pct_spin.value()
                self._wires.append(
                    {
                        "source_id": source_id,
                        "target_id": target_id,
                        "pct": pct,
                        "phase": 0.0,
                    }
                )
                self._apply_routes_to_state(
                    add=[(source_id, target_id, float(pct))], remove=[]
                )
                from ..core.event_bus import get_event_bus

                bus = get_event_bus()
                bus.emit(
                    "bot.log",
                    bot_id=source_id,
                    message=f"WIRE CONNECTED: {pct}% of profit → bot {target_id[:8]}",
                )
                bus.emit(
                    "wire.created", source_id=source_id, target_id=target_id, pct=pct
                )

        def _on_external_wire_created(self, event) -> None:
            """Add the ``wire.created`` event's wire to ``_wires`` when new.

            A repeated pair updates its pct and adds no second entry.
            """
            try:
                data = getattr(event, "data", None) or {}
                src = str(data.get("source_id", "") or "")
                tgt = str(data.get("target_id", "") or "")
                pct = float(data.get("pct", 0) or 0)
                if not src or not tgt or pct <= 0:
                    return
                # The drag path also emits wire.created, so a repeat only updates pct.
                for w in self._wires:
                    if w.get("source_id") == src and w.get("target_id") == tgt:
                        w["pct"] = pct
                        return
                self._wires.append(
                    {
                        "source_id": src,
                        "target_id": tgt,
                        "pct": pct,
                        "phase": 0.0,
                    }
                )
                if hasattr(self, "_wire_canvas") and self._wire_canvas:
                    self._wire_canvas.update()
            except Exception:  # noqa: S110
                pass

        def _on_external_wire_removed(self, event) -> None:
            """Drop from ``_wires`` every pair the ``wire.removed`` event names."""
            try:
                data = getattr(event, "data", None) or {}
                src = str(data.get("source_id", "") or "")
                tgt = str(data.get("target_id", "") or "")
                if not src or not tgt:
                    return
                self._wires = [
                    w
                    for w in self._wires
                    if not (w.get("source_id") == src and w.get("target_id") == tgt)
                ]
                if hasattr(self, "_wire_canvas") and self._wire_canvas:
                    self._wire_canvas.update()
            except Exception:  # noqa: S110
                pass

        def remove_wire(self, source_id: str, target_id: str):
            """Drop one wire from ``_wires`` and from the stored wire list.

            The right-click menu and the drag picker both land here, so
            the pair leaves the store and the next launch paints none.
            """
            self._wires = [
                w
                for w in self._wires
                if not (w["source_id"] == source_id and w["target_id"] == target_id)
            ]
            self._wire_canvas.update()
            self._apply_routes_to_state(add=[], remove=[(source_id, target_id)])
            from ..core.event_bus import get_event_bus

            get_event_bus().emit(
                "bot.log",
                bot_id=source_id,
                message=f"WIRE DISCONNECTED from bot {target_id[:8]}",
            )
            get_event_bus().emit(
                "wire.removed", source_id=source_id, target_id=target_id
            )

        def _wire_at_pos(self, pos: QPointF, threshold: float = 12.0) -> dict | None:
            """Return the ``_wires`` entry nearest a position, within threshold.

            Measures against the same catenary_curve the wire canvas paints, so
            a right-click lands on the wire the operator can see.
            """
            from .main_tabs.wire_canvas_surface import catenary_curve, slack_for_offset

            best_wire = None
            best_dist = threshold

            for wire in self._wires:
                src = self._get_bot_center(wire["source_id"])
                tgt = self._get_bot_center(wire["target_id"])
                if not src or not tgt:
                    continue

                curve = catenary_curve(
                    (src.x(), src.y()),
                    (tgt.x(), tgt.y()),
                    slack_for_offset(self._get_wire_offset(wire)),
                )
                for px, py in curve["points"]:
                    dist = math.sqrt((pos.x() - px) ** 2 + (pos.y() - py) ** 2)
                    if dist < best_dist:
                        best_dist = dist
                        best_wire = wire

            return best_wire

        def _is_bidirectional(self, source_id: str, target_id: str) -> bool:
            """Report whether ``_wires`` holds the target-to-source pair."""
            return any(
                w["source_id"] == target_id and w["target_id"] == source_id
                for w in self._wires
            )

        def _get_wire_offset(self, wire: dict) -> float:
            """Return the vertical offset that keeps a wire pair apart.

            A left-to-right wire takes the lower slot and a
            right-to-left wire the upper; a wire with no reverse
            partner takes 0.0.
            """
            src_center = self._get_bot_center(wire["source_id"])
            tgt_center = self._get_bot_center(wire["target_id"])
            if not src_center or not tgt_center:
                return 0.0

            if not self._is_bidirectional(wire["source_id"], wire["target_id"]):
                return 0.0  # No offset needed for unidirectional

            # A source left of its target takes the lower slot.
            if src_center.x() <= tgt_center.x():
                return 25.0  # Lower slot
            else:
                return -25.0  # Upper slot

        def _show_disconnect_menu(self, pos: QPointF, wire: dict):
            """Offer the right-click menu that removes the wire under the cursor."""
            menu = QMenu(self)
            menu.setStyleSheet(
                f"QMenu {{ background: {ds.MENU_SURFACE}; color: {ds.TEXT_HIGH}; border: 1px solid {ds.MENU_BORDER}; }}"
                f"QMenu::item:selected {{ background: {ds.MENU_ITEM_SELECTED}; }}"
                f"QMenu::separator {{ background: {ds.MENU_BORDER}; height: 1px; }}"
            )

            src_short = wire["source_id"][:8]
            tgt_short = wire["target_id"][:8]
            pct = wire.get("pct", 0)

            header = menu.addAction(f"Wire: {src_short} → {tgt_short} ({pct}%)")
            header.setEnabled(False)
            menu.addSeparator()

            disconnect_action = menu.addAction("Disconnect Wire")
            disconnect_action.setIcon(
                self.style().standardIcon(
                    self.style().StandardPixmap.SP_DialogCloseButton
                )
            )

            if self._is_bidirectional(wire["source_id"], wire["target_id"]):
                disconnect_both = menu.addAction("Disconnect Both Directions")
            else:
                disconnect_both = None

            menu.addSeparator()
            menu.addAction("Cancel")

            global_pos = self._wire_canvas.mapToGlobal(pos.toPoint())
            result = menu.exec(global_pos)

            if result == disconnect_action:
                self.remove_wire(wire["source_id"], wire["target_id"])
            elif result == disconnect_both and disconnect_both:
                self.remove_wire(wire["source_id"], wire["target_id"])
                self.remove_wire(wire["target_id"], wire["source_id"])

        def update_bots(self, bot_statuses: list[dict]):
            """Rebuild ``_bot_widgets`` and ``_live_bot_rows`` from status data.

            One status dict per bot feeds the locust grid.
            """
            current_ids = set()

            # Insertion order fixes grid position, and wire ends read bot centres.
            for status in bot_statuses:
                bid = status.get("bot_id", "")
                if not bid:
                    continue
                current_ids.add(bid)

                if bid not in self._bot_widgets:
                    self._empty_label.setVisible(False)
                    node = BotNodeWidget()
                    node.set_theme(self._theme_key)
                    node.set_app_theme(self._app_theme_name)
                    self._bot_widgets[bid] = node
                    idx = len(self._bot_widgets) - 1
                    row = idx // self._grid_cols
                    col = idx % self._grid_cols
                    self._grid_layout.addWidget(node, row, col)

                self._bot_widgets[bid].set_bot_data(status)

            for bid in list(self._bot_widgets.keys()):
                if bid not in current_ids:
                    widget = self._bot_widgets.pop(bid)
                    self._grid_layout.removeWidget(widget)
                    widget.deleteLater()
                    self._wires = [
                        w
                        for w in self._wires
                        if w["source_id"] != bid and w["target_id"] != bid
                    ]

            # Re-laid out after a removal: the grid would otherwise hold a hole.
            if self._bot_widgets:
                widgets_in_order = list(self._bot_widgets.values())
                while self._grid_layout.count():
                    self._grid_layout.takeAt(0)
                    # No deleteLater: _bot_widgets still holds these widgets.
                for idx, w in enumerate(widgets_in_order):
                    row = idx // self._grid_cols
                    col = idx % self._grid_cols
                    self._grid_layout.addWidget(w, row, col)
                # The empty label is re-added hidden and survives the rebuild.
                self._grid_layout.addWidget(
                    self._empty_label,
                    (len(widgets_in_order) // self._grid_cols) + 1,
                    0,
                    1,
                    self._grid_cols,
                )

            if not self._bot_widgets:
                self._empty_label.setVisible(True)

            # A new widget would stack over _wire_canvas and eat its mouse events.
            if self._wire_canvas.isVisible():
                self._reposition_wire_canvas()
                self._wire_canvas.raise_()

            try:
                self._rebuild_exchange_selector_items()
                self._refresh_visible_bots()
                self._refresh_quick_routing_scope()
            except Exception:
                logger.exception(
                    "Bot Swarm refresh step failed; the exchange selector and the"
                    " quick routing scope hold their previous contents"
                )


__all__ = [
    "BotNodeWidget",
    "BotVisualizationTab",
    "QuickRoutingMatrix",
    "THEMES",
    "_RNG",
    "_WireCanvas",
]
