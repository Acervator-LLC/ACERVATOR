"""
src/gui/simulator_tab/simulator_tab.py — SimulatorTab QWidget.

The Simulator tab IS the top-level QWidget that lives in MainWindow's
main tab bar. Its chrome (splitters + log panels + indicator panel
placeholder + inline stat strip) is a near-identical clone of the live
Trading tab's chrome: near-identical versions of the Trading tab, with
the tab-specific functions added.

Layout:
  * Stat strip at top (SimStatStrip)
  * Top-left: mode switcher (Fleet Replay | Nuclear Mode) + stack
  * Top-right: Indicator container — stacked price+VWAP lines
    (upper) + per-bot voting (lower)
  * Bottom: Activity Log + Performance Log, both wired to
    FleetReplayPanel via set_log_callbacks
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt

logger = logging.getLogger("acervator.simulator_tab")
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

try:
    from .nuclear_mode_panel import NuclearModePanel
except Exception:  # noqa: BLE001 - GUI-import guard
    NuclearModePanel = None
# Fleet Replay: live bot configs against a fake exchange driven by
# YTD candles.
try:
    from .fleet.fleet_replay_panel import FleetReplayPanel
except Exception:  # noqa: BLE001 - GUI-import guard
    FleetReplayPanel = None


def _section_label(text: str) -> QLabel:
    """A small section header label with the cyberpunk accent."""
    lbl = QLabel(text)
    lbl.setStyleSheet("color: #00ffcc; font-weight: bold;")
    return lbl


class SimulatorTab(QWidget):
    """
    The Simulator tab. Mirrors the Trading-tab chrome.

    Public attributes (used by main_window for stat-strip / log
    integration in later phases):

        stat_strip       : SimStatStrip — top header (10 fields)
        activity_log     : QPlainTextEdit — left bottom panel
        performance_log  : QPlainTextEdit — right bottom panel
        basic_modes      : BasicModesPanel — page 0 of the stack
        nuclear_mode     : QWidget        — page 1 of the stack
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Simulator Tab")
        self.setObjectName("SimulatorTab")

        # Set by MainWindow.set_async_loop after construction.
        self._async_loop = None
        # Simulator Swarm resolver. Set by MainWindow once both tabs mount.
        self._swarm_getter = None
        # Market Inspector topology resolver. Set once both tabs mount.
        self._topology_getter = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(2, 2, 2, 2)
        outer.setSpacing(2)

        self.stat_strip = self._build_stat_strip()
        outer.addWidget(self.stat_strip)
        # Declares every Simulator feed, so one that never fires is reported.
        try:
            from ...core.feature_telemetry import get_telemetry

            get_telemetry().declare(
                "sim.stat_strip.feed",
                "sim.price_chart.append",
                "sim.voting_readout.update",
                "sim.gate_lights.update",
                "sim.parity.compare_trades",
                "sim.controller.tick",
                "sim.activity_log.write",
                "sim.performance_log.write",
            )
        except Exception as _tel_exc:  # noqa: BLE001 - telemetry is advisory
            logger.debug("feature telemetry declare failed: %s", _tel_exc)

        main_splitter = QSplitter(Qt.Vertical)
        main_splitter.setHandleWidth(5)
        main_splitter.setChildrenCollapsible(False)

        top_splitter = QSplitter(Qt.Horizontal)
        top_splitter.setHandleWidth(5)
        top_splitter.setChildrenCollapsible(False)

        content_wrap = QWidget()
        content_lay = QVBoxLayout(content_wrap)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(0)

        from PySide6.QtWidgets import QComboBox as _ModeCB

        _mode_row = QHBoxLayout()
        _mode_row.setContentsMargins(6, 2, 6, 2)
        _mode_lbl = QLabel("Mode:")
        _mode_lbl.setStyleSheet("color:#888899;font-size:11px;")
        _mode_row.addWidget(_mode_lbl)
        self._mode_selector = _ModeCB()
        self._mode_selector.setMinimumWidth(210)
        for _label, _key, _tip in self.SIM_MODES:
            self._mode_selector.addItem(_label, _key)
            self._mode_selector.setItemData(
                self._mode_selector.count() - 1, _tip, Qt.ToolTipRole
            )
        self._mode_selector.setToolTip(
            "Validation — gate parity against documented YTD events.\n"
            "Looping Back Test — tablets looped with noise, for "
            "strategy work.\n"
            "Nuclear — load oscillation and swarm stress; measures the "
            "system, not the trades."
        )
        self._mode_selector.currentIndexChanged.connect(self._on_sim_mode_changed)
        _mode_row.addWidget(self._mode_selector)
        self._mode_hint = QLabel("")
        self._mode_hint.setStyleSheet("color:#666677;font-size:11px;")
        _mode_row.addWidget(self._mode_hint)
        _mode_row.addStretch()
        content_lay.addLayout(_mode_row)

        self._stack = QStackedWidget()
        if FleetReplayPanel is not None:
            self.fleet_replay = FleetReplayPanel()

            from PySide6.QtWidgets import QComboBox as _ABCB

            self._bot_area_host = QWidget()
            _bah = QVBoxLayout(self._bot_area_host)
            _bah.setContentsMargins(0, 0, 0, 0)
            _bah.setSpacing(2)
            _ab_row = QHBoxLayout()
            _ab_row.setContentsMargins(4, 2, 4, 0)
            _ab_lbl = QLabel("Active simulator bots:")
            _ab_lbl.setStyleSheet("color:#888899;font-size:11px;")
            _ab_row.addWidget(_ab_lbl)
            self._active_bot_picker = _ABCB()
            self._active_bot_picker.setMinimumWidth(220)
            self._active_bot_picker.setToolTip(
                "Bots currently loaded into the Simulator fleet."
            )
            self._active_bot_picker.addItem("All bots", "")
            _ab_row.addWidget(self._active_bot_picker)
            _ab_row.addStretch()
            _bah.addLayout(_ab_row)
            # Lets Start Replay schedule the tick controller on the app loop.
            self.fleet_replay.set_async_loop_getter(lambda: self._async_loop)
            # set_connectors_getter is called by MainWindow after mount.
            self._connectors_getter = None
            if hasattr(self.fleet_replay, "set_log_callbacks"):
                self.fleet_replay.set_log_callbacks(
                    self.log_activity, self.log_performance
                )
        else:
            from PySide6.QtWidgets import QLabel as _Lbl

            self.fleet_replay = _Lbl("FleetReplayPanel unavailable (import failed).")
        self.nuclear_mode = None
        if NuclearModePanel is not None:
            try:
                self.nuclear_mode = NuclearModePanel(
                    activity_log_cb=self.log_activity,
                    perf_log_cb=self.log_performance,
                    async_loop_getter=lambda: self._async_loop,
                )
            except Exception as _nuc_exc:  # noqa: BLE001 - GUI-build guard
                logger.exception("Nuclear Mode panel failed to construct: %s", _nuc_exc)
                try:
                    self.log_activity(
                        f"Nuclear Mode unavailable: "
                        f"{type(_nuc_exc).__name__}: {_nuc_exc}"
                    )
                except Exception:  # noqa: BLE001,S110 - log path best-effort
                    pass
        if self.nuclear_mode is None:
            from PySide6.QtWidgets import QLabel as _NucLbl

            self.nuclear_mode = _NucLbl(
                "Nuclear Mode unavailable (panel failed to load). "
                "See the Activity log for the reason."
            )
        # Inside stack page 0, not beside the stack: it must not stay on
        # screen while Nuclear Mode is showing.
        _fleet_page = QWidget()
        _fp_lay = QVBoxLayout(_fleet_page)
        _fp_lay.setContentsMargins(0, 0, 0, 0)
        _fp_lay.setSpacing(2)
        _host = getattr(self, "_bot_area_host", None)
        if _host is not None:
            _fp_lay.addWidget(_host)
        _fp_lay.addWidget(self.fleet_replay, stretch=1)
        self._stack.addWidget(_fleet_page)  # page 0
        self._stack.addWidget(self.nuclear_mode)  # page 1
        content_lay.addWidget(self._stack, stretch=1)
        self._on_sim_mode_changed()

        # fleetLoaded is emitted by the fleet panel's Load button: one
        # trigger for the bot table and both dropdowns.
        try:
            self.mount_bot_status_table()
        except Exception as _mnt_exc:  # noqa: BLE001 - GUI guard
            logger.warning("bot status table mount failed: %s", _mnt_exc)
        try:
            self.fleet_replay.fleetLoaded.connect(self._on_fleet_loaded)
        except Exception as _fl_exc:  # noqa: BLE001 - GUI guard
            logger.warning("fleetLoaded connect failed: %s", _fl_exc)
        # Sentinel for code paths that still reference .basic_modes.
        self.basic_modes = None

        top_splitter.addWidget(content_wrap)

        indicator_wrap = QWidget()
        ind_lay = QVBoxLayout(indicator_wrap)
        ind_lay.setContentsMargins(8, 8, 8, 8)

        # Upper half: per-bot price and VWAP on master-clock ticks.
        # Lower half: the voting readout.
        self._indicator_container = QFrame()
        self._indicator_container.setObjectName("SimIndicatorContainer")
        self._indicator_container.setStyleSheet(
            "QFrame#SimIndicatorContainer{background:#0a0a14;"
            "border:1px solid #2a2a44;border-radius:4px;}"
        )
        _ind_inner = QVBoxLayout(self._indicator_container)
        _ind_inner.setContentsMargins(0, 0, 0, 0)
        _ind_inner.setSpacing(0)
        try:
            from .fleet.sim_visuals import SimPriceVwapChart

            self._sim_price_chart = SimPriceVwapChart()
            # The Trading Tab's own panel, same feed contract:
            # update_data(multi_tf_summary, symbol).
            from ..indicator_panel import IndicatorVotingPanel

            self._sim_voting_readout = IndicatorVotingPanel()

            # Own scroll area per half. The chart asks 36px per symbol (35 bots
            # = 1,260px), which exceeds the pane height and blocks an even split.
            def _scrolled(widget: QWidget) -> QScrollArea:
                area = QScrollArea()
                area.setWidget(widget)
                area.setWidgetResizable(True)
                area.setFrameShape(QFrame.NoFrame)
                area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                # Let the splitter shrink this below content height.
                area.setMinimumHeight(80)
                return area

            def _titled(widget: QWidget, title: str, scroll: QScrollArea) -> QWidget:
                from PySide6.QtWidgets import QPushButton
                from .fleet.sim_visuals import _show_expanded

                box = QWidget()
                lay = QVBoxLayout(box)
                lay.setContentsMargins(6, 4, 6, 0)
                lay.setSpacing(2)

                head = QHBoxLayout()
                head.setContentsMargins(0, 0, 0, 0)
                head.addWidget(_section_label(title))
                head.addStretch()
                btn = QPushButton("⤢ Expand")
                btn.setToolTip(
                    f"Open {title} at full display width, half height, "
                    "centred on this screen."
                )
                btn.setStyleSheet(
                    "QPushButton{background:#1a1a3a;color:#88aaff;"
                    "border:1px solid #88aaff;border-radius:3px;"
                    "padding:1px 8px;font-size:10px;}"
                    "QPushButton:hover{background:#222250;}"
                )
                btn.clicked.connect(
                    lambda _c=False, w=widget, t=title: _show_expanded(w, t)
                )
                head.addWidget(btn)
                lay.addLayout(head)
                lay.addWidget(scroll, stretch=1)
                return box

            _chart_scroll = _titled(
                self._sim_price_chart,
                "Historical Price vs. Position VWAP",
                _scrolled(self._sim_price_chart),
            )
            # 37 stacked bands give each symbol 36px, in which a candle is a
            # smudge. Inserted at index 1 of the titled box, under its header.
            from PySide6.QtWidgets import QComboBox as _QCB

            _pick_row = QHBoxLayout()
            _pick_row.setContentsMargins(6, 0, 6, 2)
            _pick_lbl = QLabel("Bot:")
            _pick_lbl.setStyleSheet("color:#888899;font-size:11px;")
            _pick_row.addWidget(_pick_lbl)
            self._chart_bot_picker = _QCB()
            self._chart_bot_picker.setMinimumWidth(150)
            self._chart_bot_picker.setToolTip(
                "Which bot's Stone Tablet candles and VWAP to chart. "
                "Select a bot to chart its VWAP and Stone Tablet candles."
            )
            self._chart_bot_picker.addItem("(select a bot)", "")
            self._chart_bot_picker.currentIndexChanged.connect(
                self._on_chart_bot_changed
            )
            _pick_row.addWidget(self._chart_bot_picker)
            _pick_row.addStretch()
            _chart_scroll.layout().insertLayout(1, _pick_row)

            _vote_scroll = _titled(
                self._sim_voting_readout,
                "Indicator Voting Panel",
                _scrolled(self._sim_voting_readout),
            )

            _ind_splitter = QSplitter(Qt.Vertical)
            _ind_splitter.setHandleWidth(4)
            _ind_splitter.setChildrenCollapsible(False)
            _ind_splitter.addWidget(_chart_scroll)
            _ind_splitter.addWidget(_vote_scroll)
            # Equal stretch AND equal sizes — stretch alone is
            # advisory once a widget has been given an explicit size.
            _ind_splitter.setStretchFactor(0, 1)
            _ind_splitter.setStretchFactor(1, 1)
            _ind_splitter.setSizes([10_000, 10_000])
            _ind_inner.addWidget(_ind_splitter)
            if hasattr(self.fleet_replay, "set_visual_widgets"):
                self.fleet_replay.set_visual_widgets(
                    price_chart=self._sim_price_chart,
                    voting_readout=self._sim_voting_readout,
                    stat_strip=self.stat_strip,
                )
            if hasattr(self.nuclear_mode, "set_visual_widgets"):
                self.nuclear_mode.set_visual_widgets(
                    price_chart=self._sim_price_chart,
                    voting_readout=self._sim_voting_readout,
                    stat_strip=self.stat_strip,
                )
        except Exception as _vis_exc:  # noqa: BLE001 - GUI import guard
            logger.debug("sim visuals unavailable: %s", _vis_exc)
            self._sim_price_chart = None
            self._sim_voting_readout = None
        ind_lay.addWidget(self._indicator_container, stretch=1)

        top_splitter.addWidget(indicator_wrap)
        top_splitter.setSizes([600, 500])
        main_splitter.addWidget(top_splitter)

        # One pane for both streams. log_performance tags its lines so the
        # two stay readable apart.
        log_splitter = QSplitter(Qt.Horizontal)
        log_splitter.setHandleWidth(5)
        log_splitter.setChildrenCollapsible(False)

        activity_wrap = QWidget()
        act_lay = QVBoxLayout(activity_wrap)
        act_lay.setContentsMargins(2, 2, 2, 2)
        act_lay.setSpacing(2)
        act_header = QHBoxLayout()
        act_header.addWidget(_section_label("Simulator Log"))
        act_header.addStretch()
        self._activity_pause_btn = QPushButton("\u23f8  Pause")
        self._activity_pause_btn.setCheckable(True)
        self._activity_pause_btn.setStyleSheet(
            "QPushButton{background:#1a1a3a;color:#ffaa00;"
            "border:1px solid #ffaa00;border-radius:3px;"
            "padding:3px 10px;font-size:11px;}"
            "QPushButton:checked{background:#3a1a1a;color:#ff3366;"
            "border:1px solid #ff3366;}"
        )
        self._activity_paused = False
        self._perf_paused = False
        self._activity_pause_btn.toggled.connect(self._on_activity_paused)
        act_header.addWidget(self._activity_pause_btn)
        act_lay.addLayout(act_header)

        self.simulator_log = QPlainTextEdit()
        self.simulator_log.setReadOnly(True)
        # Both streams share this buffer now, so the cap covers both.
        self.simulator_log.setMaximumBlockCount(10000)
        self.simulator_log.setStyleSheet(
            "QPlainTextEdit{background:#0a0a14;color:#ccccdd;"
            "font-family:'Cascadia Code','Consolas',monospace;"
            "font-size:11px;border:1px solid #2a2a44;}"
        )
        act_lay.addWidget(self.simulator_log)

        # Aliases: the controller, the Nuclear panel and tests use both names.
        self.activity_log = self.simulator_log
        self.performance_log = self.simulator_log

        log_splitter.addWidget(activity_wrap)

        gate_wrap = QWidget()
        gate_lay = QVBoxLayout(gate_wrap)
        gate_lay.setContentsMargins(2, 2, 2, 2)
        gate_lay.setSpacing(2)
        gate_header = QHBoxLayout()
        gate_header.addWidget(_section_label("Gate Status"))
        gate_header.addStretch()
        gate_lay.addLayout(gate_header)
        # The fleet panel owns the gate display; reparenting keeps one instance.
        self._gate_status_host = QWidget()
        _gh = QVBoxLayout(self._gate_status_host)
        _gh.setContentsMargins(0, 0, 0, 0)
        _gate_panel = getattr(getattr(self, "fleet_replay", None), "_gate_panel", None)
        if _gate_panel is not None:
            _gh.addWidget(_gate_panel)
        else:
            _placeholder = QLabel("Gate status unavailable.")
            _placeholder.setStyleSheet("color:#666677;font-size:11px;padding:8px;")
            _gh.addWidget(_placeholder)
            _gh.addStretch()
        gate_lay.addWidget(self._gate_status_host)
        log_splitter.addWidget(gate_wrap)

        log_splitter.setSizes([500, 500])
        main_splitter.addWidget(log_splitter)

        main_splitter.setSizes([500, 350])
        outer.addWidget(main_splitter)

    def _build_stat_strip(self) -> QWidget:
        """Build the header stat strip the build variant asks for.

        ``variant_surface`` holds the Qt strip and the React strip under
        ``SIM_STAT_STRIP``; both answer ``set`` and ``clear``.
        """
        try:
            from ..variant_surface import SIM_STAT_STRIP, surface_class

            return surface_class(SIM_STAT_STRIP)(self)
        except Exception as exc:  # noqa: BLE001 - GUI import guard
            logger.warning("stat strip unavailable, using the Qt strip: %s", exc)
            from .sim_stat_strip import SimStatStrip

            return SimStatStrip(self)

    def mount_bot_status_table(self) -> bool:
        """Put the Trading Tab's bot table in the Simulator.

        It IS that table -- `BotStatusTable`, the same class the
        Trading Tab mounts -- fed by an adapter on the fleet panel.
        Rebuilding those columns here would be the `FleetSimExchange`
        mistake a second time: a copy of a thing that exists, certain
        to drift from it.

        Returns False when the class cannot be resolved (headless
        import, no main_window), leaving the existing fleet table in
        place rather than a blank pane.
        """
        panel = getattr(self, "fleet_replay", None)
        if panel is None:
            return False
        cls = panel._bot_status_table()
        if cls is None:
            return False
        if getattr(panel, "_bot_status_table_widget", None) is not None:
            return True
        try:
            # on_fire_clicked stays None: manual Fire is not used in the Simulator.
            widget = cls(on_bot_clicked=self._on_sim_bot_detail, on_fire_clicked=None)
        except Exception as exc:  # noqa: BLE001 - construction guard
            logger.debug("BotStatusTable construction failed: %s", exc)
            return False
        panel._bot_status_table_widget = widget
        panel._bot_table_columns = list(getattr(cls, "COLUMNS", []))
        host = getattr(self, "_bot_area_host", None)
        if host is not None and host.layout() is not None:
            host.layout().addWidget(widget)
        return True

    def _on_sim_bot_detail(self, bot_id: str) -> None:
        """Open the settings dialog for a SIMULATED bot.

        Resolves the id against the sim controller ONLY. A
        Simulator surface that resolved ids against the live BotManager
        would open — and edit — a live bot from a test screen.
        """
        panel = getattr(self, "fleet_replay", None)
        ctl = getattr(panel, "_controller", None) if panel else None
        bots = list(getattr(ctl, "_bots", []) or []) if ctl else []
        bot = next(
            (b for b in bots if str(getattr(b, "bot_id", "")) == str(bot_id)), None
        )
        if bot is None:
            logger.warning(
                "sim detail: no simulated bot %r (live bots are NOT "
                "reachable from here)",
                bot_id,
            )
            return
        try:
            from ..bot_live_settings import BotLiveSettingsDialog

            dlg = BotLiveSettingsDialog(bot, None, self)
            dlg.exec()
        except Exception as exc:  # noqa: BLE001
            logger.warning("sim detail dialog failed: %s", exc)

    def _disable_fire_buttons(self) -> None:
        """Grey out Fire on every row, with the reason on the tooltip.

        Not hidden: the column stays so the Simulator's table matches
        the Trading Tab's shape, and a disabled control with an
        explanation teaches more than a missing one.
        """
        panel = getattr(self, "fleet_replay", None)
        widget = getattr(panel, "_bot_status_table_widget", None)
        if widget is None:
            return
        try:
            fire_col = list(type(widget).COLUMNS).index("Fire")
        except (ValueError, AttributeError):
            return
        for row in range(widget.rowCount()):
            w = widget.cellWidget(row, fire_col)
            if w is not None:
                w.setEnabled(False)
                w.setToolTip(
                    "Manual Fire is disabled in the Simulator. This "
                    "surface tests trading AUTOMATION; a result that "
                    "depended on operator intervention would not "
                    "measure the thing being tested."
                )

    def refresh_active_bot_roster(self, statuses=None) -> None:
        """Repopulate the ACTIVE SIMULATOR BOTS dropdown.

        Sourced from the fleet panel's adapter, so the dropdown and the
        table are showing the same set by construction -- two lists
        built from two sources is how they end up disagreeing.
        """
        picker = getattr(self, "_active_bot_picker", None)
        if picker is None:
            return
        panel = getattr(self, "fleet_replay", None)
        if statuses is None:
            statuses = panel.sim_bot_statuses() if panel is not None else []
        keep = picker.currentData() or ""
        picker.blockSignals(True)
        picker.clear()
        picker.addItem("All bots", "")
        for st in statuses:
            bid = str(st.get("bot_id", ""))
            sym = str(st.get("symbol", ""))
            if bid:
                picker.addItem(f"{sym}  ({bid[:12]})", bid)
        idx = picker.findData(keep)
        picker.setCurrentIndex(idx if idx >= 0 else 0)
        picker.blockSignals(False)

    def active_bot_id(self) -> str:
        """The bot the operator has selected, or "" for all."""
        picker = getattr(self, "_active_bot_picker", None)
        return str(picker.currentData() or "") if picker is not None else ""

    # (label, key, tooltip)
    SIM_MODES = (
        (
            "Validation",
            "validation",
            "Stone Tablets paired with YTD data. Verifies trade-gate "
            "parity at documented events.",
        ),
        (
            "Looping Back Test",
            "looping",
            "Loops the tablets with market-restructuring noise at a fixed "
            "rate. Strategy development and calibration.",
        ),
        (
            "Nuclear",
            "nuclear",
            "Load oscillation, swarm injection and high-traffic smart "
            "wire. Measures performance, stability and reliability — not "
            "trade validity.",
        ),
    )

    def sim_mode(self) -> str:
        """The selected mode key, or 'validation' before setup."""
        sel = getattr(self, "_mode_selector", None)
        return str(sel.currentData() or "validation") if sel else "validation"

    def _on_sim_mode_changed(self, _idx: int = 0) -> None:
        """Route the stack and say what the mode collects.

        The page index is incidental; the MEANING is what the operator
        needs on screen, because the three modes answer different
        questions and their results are not interchangeable. Nuclear
        results in particular never validate a trade.
        """
        key = self.sim_mode()
        stack = getattr(self, "_stack", None)
        if stack is not None:
            # Validation and Looping both drive the fleet page.
            stack.setCurrentIndex(1 if key == "nuclear" else 0)
        hint = getattr(self, "_mode_hint", None)
        if hint is not None:
            hint.setText(
                {
                    "validation": "collects: gate-latch parity vs documented "
                    "YTD events",
                    "looping": "collects: strategy behaviour under looped "
                    "tapes + noise",
                    "nuclear": "collects: performance, stability, reliability "
                    "(NOT trade validity)",
                }.get(key, "")
            )
        panel = getattr(self, "fleet_replay", None)
        if panel is not None and hasattr(panel, "set_sim_mode"):
            try:
                panel.set_sim_mode(key)
            except Exception as exc:  # noqa: BLE001
                logger.debug("panel mode set failed: %s", exc)
        try:
            from src.core.signal_contract import emit as _md_emit

            # actual is the page the stack IS on: an out-of-range
            # setCurrentIndex is a no-op and the hand-off above swallows its own.
            _md_emit(
                "sim.06.013.state_transition.mode_selected",
                actual=(stack.currentIndex() if stack is not None else None),
                expected=(1 if key == "nuclear" else 0),
                context={
                    "mode": key,
                    "page": ("nuclear" if key == "nuclear" else "fleet"),
                    "stack": stack is not None,
                },
            )
        except Exception:  # noqa: BLE001,S110 - advisory
            pass

    def _on_fleet_loaded(self, configs) -> None:
        """Everything the fleet drives, from one signal.

        Fired by the Load button. Populates the bot table and
        both dropdowns; previously nothing called any of them.
        """
        panel = getattr(self, "fleet_replay", None)
        if panel is None:
            return
        syms = []
        for c in configs or []:
            s = str((c or {}).get("symbol", "") or "")
            if s:
                syms.append(s)
        chart = getattr(self, "_sim_price_chart", None)
        if chart is not None:
            try:
                chart.set_symbols(syms)
            except Exception as exc:  # noqa: BLE001
                logger.debug("chart set_symbols failed: %s", exc)
        try:
            self.refresh_chart_bot_roster(syms)
        except Exception as exc:  # noqa: BLE001
            logger.debug("chart roster refresh failed: %s", exc)
        # Bot table + active-bot dropdown, from the SAME adapter so the
        # two cannot disagree.
        try:
            statuses = panel.sim_bot_statuses()
            if not statuses:
                # Before Start Replay no bots are constructed, so the adapter is
                # empty. _src_scrumming_state (38 fields) and _src_stats (36) are it.
                statuses = []
                for c in configs or []:
                    c = c or {}
                    ss = c.get("_src_scrumming_state") or {}
                    stx = c.get("_src_stats") or {}
                    units = sum(
                        float(l.get("units", 0) or 0)
                        for l in (ss.get("main_lots") or [])
                        if isinstance(l, dict)
                    )
                    px = float(stx.get("current_price", 0.0) or 0.0)
                    pv = float(stx.get("position_value", 0.0) or 0.0)
                    if pv <= 0 and px > 0:
                        pv = units * px
                    statuses.append(
                        {
                            "bot_id": str(c.get("_src_bot_id", "") or ""),
                            "symbol": str(c.get("symbol", "") or ""),
                            "mode": str(c.get("mode", "scrumming") or "scrumming"),
                            "state": str(c.get("_src_state", "") or "IDLE"),
                            "exchange": str(
                                c.get("exchange_id", "coinbase") or "coinbase"
                            ),
                            # The operator's INPUT anchor, as the Trading
                            # Tab's Target column shows.
                            "target_balance": float(
                                ss.get(
                                    "anchor_target_balance",
                                    c.get("target_balance", 0.0),
                                )
                                or 0.0
                            ),
                            # The GROWN target the bot actually trades on.
                            "live_target_balance": float(
                                ss.get("target_balance", c.get("target_balance", 0.0))
                                or 0.0
                            ),
                            "current_holdings": units,
                            "quote_to_usd": float(ss.get("quote_to_usd", 1.0) or 1.0),
                            "stats": {
                                "current_price": px,
                                "position_value": pv,
                                "total_trades": int(stx.get("total_trades", 0) or 0),
                            },
                        }
                    )
            widget = getattr(panel, "_bot_status_table_widget", None)
            if widget is not None:
                widget.update_bots(statuses)
                self._disable_fire_buttons()
                panel.emit_bot_table(len(statuses))
            self.refresh_active_bot_roster(statuses)
        except Exception as exc:  # noqa: BLE001
            logger.warning("bot area refresh failed: %s", exc)

    def _on_chart_bot_changed(self, _idx: int) -> None:
        """Point the chart at one bot, or back to stacked bands."""
        picker = getattr(self, "_chart_bot_picker", None)
        chart = getattr(self, "_sim_price_chart", None)
        if picker is None or chart is None:
            return
        sym = picker.currentData() or ""
        chart.set_focus_symbol(str(sym))

    def refresh_chart_bot_roster(self, symbols) -> None:
        """Repopulate the picker after a fleet load.

        Keeps the operator's current selection when that symbol is
        still present -- a reload that silently jumped the chart back
        to a different bot would look like the chart had lost its data.
        """
        picker = getattr(self, "_chart_bot_picker", None)
        if picker is None:
            return
        keep = picker.currentData() or ""
        picker.blockSignals(True)
        picker.clear()
        picker.addItem("(select a bot)", "")
        for s in sorted({str(x) for x in (symbols or []) if str(x)}):
            picker.addItem(s, s)
        idx = picker.findData(keep)
        picker.setCurrentIndex(idx if idx >= 0 else 0)
        picker.blockSignals(False)
        self._on_chart_bot_changed(picker.currentIndex())

    def _on_activity_paused(self, checked: bool) -> None:
        self._activity_paused = checked
        self._activity_pause_btn.setText("▶  Resume" if checked else "⏸  Pause")

    @staticmethod
    def _emit_log_line(stream: str, line: str, delivered: bool) -> None:
        """Record one log line and the stream that produced it."""
        try:
            from ...core.signal_contract import emit as _emit

            # Sample, not a check: no independent expectation exists here, and
            # delivered varies with the pause button.
            _emit(
                "sim.06.014.event.log.line",
                actual=stream,
                context={"delivered": bool(delivered), "chars": len(line or "")},
            )
        except Exception:  # noqa: BLE001,S110 - instrumentation is advisory
            pass

    def log_activity(self, line: str) -> None:
        """Append a line to the simulator log unless paused."""
        if self._activity_paused:
            self._tel_skip("sim.activity_log.write", "paused")
            self._emit_log_line("activity", line, delivered=False)
            return
        self.activity_log.appendPlainText(line)
        self._tel_call("sim.activity_log.write")
        self._emit_log_line("activity", line, delivered=True)

    def log_performance(self, line: str) -> None:
        """Append a line to the simulator log unless paused."""
        if self._perf_paused:
            self._tel_skip("sim.performance_log.write", "paused")
            self._emit_log_line("performance", line, delivered=False)
            return
        # Tagged: an untagged line is indistinguishable from an activity line.
        self.performance_log.appendPlainText(f"[perf] {line}")
        self._tel_call("sim.performance_log.write")
        self._emit_log_line("performance", line, delivered=True)

    # Telemetry is advisory and must never break the feature it observes.

    @staticmethod
    def _tel_call(name: str, count: int = 1) -> None:
        try:
            from ...core.feature_telemetry import get_telemetry

            get_telemetry().record_call(name, count=count)
        except Exception:  # noqa: BLE001,S110 - advisory only
            pass

    @staticmethod
    def _tel_skip(name: str, reason: str) -> None:
        try:
            from ...core.feature_telemetry import get_telemetry

            get_telemetry().record_skip(name, reason=reason)
        except Exception:  # noqa: BLE001,S110 - advisory only
            pass

    def set_async_loop(self, loop) -> None:
        """Attach MainWindow's persistent asyncio loop so Nuclear Mode
        can schedule scout bot coroutines on the same loop everything
        else runs on. Called from MainWindow.set_async_loop after the
        loop is constructed in main.py.
        """
        self._async_loop = loop

    def set_connectors_getter(self, getter) -> None:
        """Kept for back-compat. The Fetch YTD enumeration moved to
        bot_manager (see set_bot_manager).
        This method is a no-op path retained so an older MainWindow
        build that only knows about the connectors path still boots
        without crashing."""
        self._connectors_getter = getter
        if hasattr(self.fleet_replay, "set_connectors_getter"):
            self.fleet_replay.set_connectors_getter(getter)

    def set_swarm_getter(self, getter) -> None:
        """Hand the Simulator Swarm to the Nuclear panel.

        The row API lives on
        `BotVisualizationTab` — a different top-level tab — and nothing
        connected the two. And `NuclearFleetController.set_swarm_hooks`
        had zero callers repo-wide, so all three hooks stayed None and
        every call site inside the controller was a silent no-op.

        A GETTER, not the object. `BotVisualizationTab` is constructed
        before `SimulatorTab` in MainWindow today, but binding to the
        instance here would make this wiring depend on that order
        staying true. The getter is resolved at Start, by which point
        both tabs certainly exist.

        Deliberately tolerant of a missing consumer: a build where the
        visualizer is absent should lose swarm rows, not the ability to
        run a soak.
        """
        self._swarm_getter = getter
        panel = getattr(self, "nuclear_mode", None)
        if panel is not None and hasattr(panel, "set_swarm_getter"):
            panel.set_swarm_getter(getter)

    def set_topology_getter(self, getter) -> None:
        """Market Inspector proposals for Nuclear to stress.

        Same shape as `set_swarm_getter`: a getter resolved at Start, so
        a soak stresses whatever the operator has on screen when they
        press it rather than a snapshot taken at tab-build time.

        READ ONLY. This is not the adopt path — adopting a proposal
        creates real bots and wires on the live fleet, while this only
        lets the simulator replay a proposal's shape across sim bots.
        """
        self._topology_getter = getter
        panel = getattr(self, "nuclear_mode", None)
        if panel is not None and hasattr(panel, "set_topology_getter"):
            panel.set_topology_getter(getter)

    def set_bot_manager(self, bot_manager) -> None:
        """Forward the live BotManager to Fleet Replay
        panel so its Fetch YTD button can enumerate real bots via
        the History Tab's `_pairs_from_bot_manager` pattern."""
        if hasattr(self.fleet_replay, "set_bot_manager"):
            self.fleet_replay.set_bot_manager(bot_manager)
