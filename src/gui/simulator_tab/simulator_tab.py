"""
src/gui/simulator_tab/simulator_tab.py — SimulatorTab QWidget.

The Simulator tab IS the top-level QWidget that lives in MainWindow's
main tab bar. Its chrome (splitters + log panels + indicator panel
placeholder + inline stat strip) is a near-identical clone of the live
Trading tab's chrome — operator directive 2026-05-19: "near-identical
versions of the Trading Tab or as close as we can get while including
the tab-specific functions."

Layout (v3.24.1):
  * Stat strip at top (SimStatStrip — awaits per-tick set() calls
    from v3.24.2 controller wiring)
  * Top-left: mode switcher (Fleet Replay | Nuclear Mode) + stack
  * Top-right: Indicator container — bisected in v3.24.2 into
    stacked price+VWAP lines (upper) + per-bot voting (lower)
  * Bottom: Activity Log + Performance Log (both wired to
    FleetReplayPanel via set_log_callbacks in v3.24.1)
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

# v3.24.75 — GUARDED, matching FleetReplayPanel below.
#
# This import and the construction at the panel site were the only
# unguarded ones on the Simulator path, and nothing upstream catches
# them: `SimulatorTab()` in main_window, `_setup_ui()`, and
# `MainWindow(...)` in main.py are all bare on this path. An exception
# in the Nuclear panel constructor therefore did not degrade the
# Simulator tab — it killed application startup.
#
# Armouring this BEFORE the Nuclear repoint is the difference between
# "the Nuclear tab shows a message" and "Acervator does not launch".
try:
    from .nuclear_mode_panel import NuclearModePanel
except Exception:  # noqa: BLE001 - GUI-import guard
    NuclearModePanel = None
from .sim_stat_strip import SimStatStrip

# v3.23.72 — Fleet Replay mode (loads live bot configs against a
# fake exchange driven by YTD candles).
try:
    from .fleet.fleet_replay_panel import FleetReplayPanel
except Exception:  # noqa: BLE001 - GUI-import guard
    FleetReplayPanel = None
# v3.23.79 — Basic Modes retired per operator directive 2026-07-31.
# The RAIntSimBat-battery launcher was the last surviving piece of
# the pre-v3.23.72 sim engine. The Fleet Replay + Nuclear (topology
# stress) pair supersedes it. The panel file (basic_modes_panel.py)
# is deleted in the same cascade.


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

        # v3.18.7 (Phase B) — async loop is propagated from MainWindow
        # via set_async_loop after construction. Until that's wired,
        # Nuclear Mode start attempts will fail loudly with a clear
        # activity-log message rather than silently dying.
        self._async_loop = None
        # v3.24.77 — resolves the Simulator Swarm (BotVisualizationTab).
        # Set by MainWindow after both tabs are mounted; None until then,
        # and a build without the visualizer simply loses swarm rows.
        self._swarm_getter = None
        # v3.24.79 — resolves Market Inspector topology proposals.
        # Set by MainWindow once both tabs are mounted; None until then.
        self._topology_getter = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(2, 2, 2, 2)
        outer.setSpacing(2)

        # ── Inline stat strip (mirrors live header field set) ─────────
        self.stat_strip = SimStatStrip(self)
        outer.addWidget(self.stat_strip)
        # v3.24.8 — declare every Simulator feed API up front so a
        # feature that never fires is REPORTED rather than silently
        # absent. The 2026-08-02 audit found stat_strip.set() had
        # zero call sites; declaring it here means the next replay
        # says so out loud instead of showing dashes forever.
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

        # ── Vertical splitter: top (content + indicator) / bottom (logs)
        main_splitter = QSplitter(Qt.Vertical)
        main_splitter.setHandleWidth(5)
        main_splitter.setChildrenCollapsible(False)

        # ── Top: horizontal splitter (content stack | indicator panel)
        top_splitter = QSplitter(Qt.Horizontal)
        top_splitter.setHandleWidth(5)
        top_splitter.setChildrenCollapsible(False)

        # -- Content (mode switcher + stacked pages) -------------------
        content_wrap = QWidget()
        content_lay = QVBoxLayout(content_wrap)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(0)

        # v3.24.97 — MODE DROPDOWN, replacing the two-tab bar.
        #
        # Operator, 2026-08-09: "Nuclear does not need its own tab. Its
        # needs to be integrated and available as mode of the Simulator
        # via a drop down menu."
        #
        # Three modes, and they are not three tabs wearing a new hat --
        # they differ in what runs and what is collected:
        #
        #   VALIDATION        plays Stone Tablets against paired YTD
        #                     data to verify trade-gate parity at
        #                     DOCUMENTED events. Collects: gate latch
        #                     agreement. This is the mode that decides
        #                     whether the Simulator is trustworthy.
        #
        #   LOOPING BACK TEST loops the tablets with market-restructuring
        #                     noise at a fixed rate, for strategy
        #                     development and calibration. NO generative
        #                     behaviour beyond the noise injection --
        #                     the tapes are real, only perturbed. Runs
        #                     whatever swarm and bots the operator set
        #                     up manually or by live fleet import.
        #
        #   NUCLEAR           system testing. Differs in HOW it runs
        #                     (load oscillation, swarm injection,
        #                     high-traffic smart-wire) and WHAT it
        #                     collects (performance, stability,
        #                     reliability) -- NOT trade validation.
        #                     Nuclear results never validate trades;
        #                     that is Validation's job.
        #
        # The noise source already exists (`nuclear_candle_source`,
        # per-pass 10-25% on forward/backward passes, operator directive
        # 2026-08-04). Looping Back Test is that looper WITHOUT
        # Nuclear's oscillation and swarm; Nuclear is the same looper
        # WITH them. One implementation, two configurations.
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

            # v3.24.91 - ACTIVE SIMULATOR BOTS dropdown + the host that
            # the Trading Tab's bot table is mounted into.
            #
            # Operator, 2026-08-08: "Add a drop down menu for active
            # simulator bots." Built here, populated from the fleet
            # panel's adapter so the dropdown and the table cannot show
            # different sets.
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
            # v3.23.79-A — wire the async-loop getter so Start Replay
            # can schedule the tick controller on the app loop.
            self.fleet_replay.set_async_loop_getter(lambda: self._async_loop)
            # v3.23.80 — connectors getter for Fetch YTD.
            # set_connectors is called by MainWindow after mount.
            self._connectors_getter = None
            # v3.24.1 — route Fleet Replay controller messages to
            # the on-screen Activity/Performance panels. Prior
            # default was logger.info → panels were unreachable
            # (scaffolding scan finding #1).
            if hasattr(self.fleet_replay, "set_log_callbacks"):
                self.fleet_replay.set_log_callbacks(
                    self.log_activity, self.log_performance
                )
        else:
            from PySide6.QtWidgets import QLabel as _Lbl

            self.fleet_replay = _Lbl("FleetReplayPanel unavailable (import failed).")
        # Nuclear panel still hosts the old tape-based prototype.
        # v3.23.79-B will repurpose it as the topology stress harness.
        #
        # v3.24.75 — construction guarded, and the failure is AUDIBLE.
        #
        # `except Exception` covers construction as well as the import
        # above, because the repoint changes what this constructor does.
        # The failure is logged rather than swallowed: main_window.py
        # already carries NF-162, a silent guard that failed on every
        # boot with nothing ever saying so. A panel that vanishes
        # quietly is worse than one that crashes, because a crash gets
        # investigated.
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
        # v3.24.91 - the bot area rides ON the Fleet Replay page.
        #
        # `_bot_area_host` carries the active-bots dropdown and hosts
        # the Trading Tab's `BotStatusTable`. It must live INSIDE stack
        # page 0, not beside the stack, or it would stay on screen
        # while the operator is looking at Nuclear Mode and describe a
        # fleet that page is not running.
        _fleet_page = QWidget()
        _fp_lay = QVBoxLayout(_fleet_page)
        _fp_lay.setContentsMargins(0, 0, 0, 0)
        _fp_lay.setSpacing(2)
        _host = getattr(self, "_bot_area_host", None)
        if _host is not None:
            _fp_lay.addWidget(_host)
        _fp_lay.addWidget(self.fleet_replay, stretch=1)
        self._stack.addWidget(_fleet_page)  # index 0 (primary)
        self._stack.addWidget(self.nuclear_mode)  # index 1
        content_lay.addWidget(self._stack, stretch=1)
        self._on_sim_mode_changed()

        # v3.24.96 - THE WIRING THAT WAS MISSING.
        #
        # `mount_bot_status_table`, `refresh_chart_bot_roster` and
        # `refresh_active_bot_roster` were each DEFINED and never
        # called: one occurrence apiece across all of src/. The
        # Simulator therefore kept its 3-column fleet table and two
        # empty dropdowns, while a probe that called those methods by
        # hand reported everything working. Testing a path the
        # application does not take is not verification.
        #
        # `fleetLoaded(list)` is emitted by the Load button
        # (fleet_replay_panel.py:456). Everything the fleet populates
        # hangs off it, so there is one trigger rather than three
        # methods waiting to be remembered.
        try:
            self.mount_bot_status_table()
        except Exception as _mnt_exc:  # noqa: BLE001 - GUI guard
            logger.warning("bot status table mount failed: %s", _mnt_exc)
        try:
            self.fleet_replay.fleetLoaded.connect(self._on_fleet_loaded)
        except Exception as _fl_exc:  # noqa: BLE001 - GUI guard
            logger.warning("fleetLoaded connect failed: %s", _fl_exc)
        # v3.23.79 — legacy attribute kept as sentinel for any
        # transitional code path that still references .basic_modes.
        self.basic_modes = None

        top_splitter.addWidget(content_wrap)

        # -- Indicator panel placeholder (Phase B+ binds to sim bots) --
        indicator_wrap = QWidget()
        ind_lay = QVBoxLayout(indicator_wrap)
        ind_lay.setContentsMargins(8, 8, 8, 8)
        # v3.24.29 — the outer "Indicator Voting Panel" label is gone.
        # It sat above BOTH halves, so it read as naming the price/VWAP
        # charts directly beneath it. Each half now carries its own
        # header (see _titled below): the charts are "Historical Price
        # vs. Position VWAP", and only the table is the voting panel.

        # v3.24.3 — Indicator panel bisected per operator directive:
        # upper half = stacked per-bot price + VWAP lines synced to
        # master-clock ticks, lower half = per-bot voting readout.
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
            # v3.24.81 — USE THE REAL PANEL, not a lookalike.
            #
            # This mounted `PerBotVotingReadout`, a 6-column summary
            # table (Symbol/Net/Conf/Bull/Bear/Direction) written for the
            # sim. The Trading Tab mounts `IndicatorVotingPanel`
            # (indicator_panel.py, constructed at main_window.py:3652) —
            # 12 indicators across two rows with per-indicator bars, a
            # bot selector and a TF lock.
            #
            # Two different widgets showing different things under the
            # same title is not a match. Operator directive: the sim's
            # panel must BE the Trading Tab's panel. Same class, same
            # feed contract: `update_data(multi_tf_summary, symbol)`.
            from ..indicator_panel import IndicatorVotingPanel

            self._sim_voting_readout = IndicatorVotingPanel()

            # v3.24.14 — each half goes inside its OWN scroll area.
            #
            # Both widgets size themselves to their content: the chart
            # asks for 36px per symbol (35 bots = 1,260px) and the
            # readout for one row per bot. Added to a splitter bare,
            # those minimums exceed the pane height, so Qt cannot
            # honour an even split — the chart won and the readout was
            # crushed to a sliver (operator screenshot 2026-08-03).
            #
            # Wrapping each in a scroll area caps what the splitter
            # sees at the viewport, so 50/50 holds and the overflow
            # scrolls instead of fighting for space.
            def _scrolled(widget: QWidget) -> QScrollArea:
                area = QScrollArea()
                area.setWidget(widget)
                area.setWidgetResizable(True)
                area.setFrameShape(QFrame.NoFrame)
                area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                # Let the splitter shrink this below content height.
                area.setMinimumHeight(80)
                return area

            # v3.24.29 — each half gets its OWN header + Expand button.
            #
            # Operator 2026-08-04: "The indicator voting panel label is
            # in the wrong place and above the line charts which should
            # have a corrected label of Historical Price vs. Position
            # VWAP."
            #
            # One label above the whole container read as naming the
            # charts, but the charts are not a voting panel — the table
            # below them is. Labelling each half puts the name on the
            # thing it describes.
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
            # v3.24.89 - BOT PICKER for the chart.
            #
            # Operator, 2026-08-08: "This needs to be changed to show
            # one chart and have the others be displayed when their
            # respective bot is selected from the... drop down menu."
            #
            # 37 stacked bands gave each symbol 36px, in which a candle
            # is a smudge. One symbol at full height is the only way the
            # bars carry information; this chooses which. Inserted at
            # index 1 of the titled box -- directly under its header and
            # above the chart, so the control sits with what it drives.
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
            # Wire the fleet-replay panel so it can push per-tick
            # updates when Start Replay runs.
            if hasattr(self.fleet_replay, "set_visual_widgets"):
                # v3.24.9 — stat_strip added so the 10-field header
                # actually receives data. Telemetry proved set() had
                # zero callers before this.
                self.fleet_replay.set_visual_widgets(
                    price_chart=self._sim_price_chart,
                    voting_readout=self._sim_voting_readout,
                    stat_strip=self.stat_strip,
                )
            # v3.24.28 — Nuclear Mode gets the SAME panels.
            #
            # Operator 2026-08-04: "No activity in any of these panel
            # after Start Scout is clicked." Only Fleet Replay was ever
            # wired here, so the Indicator Voting Panel, per-bot voting
            # table and price/VWAP chart had no feed at all while a
            # scout ran. The Activity Log worked because it arrives via
            # a separate activity_log_cb, which made the failure look
            # selective rather than structural.
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

        # ── Bottom: ONE simulator log, on the left ──────────────────
        #
        # v3.24.85 - Operator task 2026-08-08 (screenshot area 1):
        # "Combined these two logs and have them sit at the left where
        # Simulator Activity Log currently lives."
        #
        # `FleetReplayController` writes to two callbacks -- 22
        # `activity_log_cb` calls and 5 `performance_log_cb` calls -- so
        # both stay on the public surface and both now land in the same
        # widget. `log_performance` tags its lines so the streams remain
        # readable apart after they share a pane; merging panes must not
        # merge MEANING.
        #
        # The right-hand half is left empty and reserved: the gate status
        # display moves into it next (screenshot area 2). Splitting now
        # keeps that a layout change rather than a rebuild.
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

        # Both historical names resolve to the merged widget. Kept as
        # aliases rather than renamed call sites: the controller, the
        # Nuclear panel and existing tests all reach for these, and a
        # rename would be a second change riding along with this one.
        self.activity_log = self.simulator_log
        self.performance_log = self.simulator_log

        log_splitter.addWidget(activity_wrap)

        # Reserved for the gate status display (screenshot area 2).
        gate_wrap = QWidget()
        gate_lay = QVBoxLayout(gate_wrap)
        gate_lay.setContentsMargins(2, 2, 2, 2)
        gate_lay.setSpacing(2)
        gate_header = QHBoxLayout()
        gate_header.addWidget(_section_label("Gate Status"))
        gate_header.addStretch()
        gate_lay.addLayout(gate_header)
        # v3.24.86 — the fleet panel owns the gate display; this tab
        # positions it. Reparenting rather than rebuilding keeps ONE
        # instance, so `_gate_cell_for` and the widget on screen can
        # never be two different objects.
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

    def mount_bot_status_table(self) -> bool:
        """Put the Trading Tab's bot table in the Simulator.

        v3.24.91. Operator task 2026-08-08 (screenshot area 5): "Needs
        to be redesigned to match the Trading Tab's bot area."

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
            # v3.24.97 — the callbacks the table takes, wired to the SIM.
            #
            # `mount_bot_status_table` used to call `cls()` with no
            # arguments, so `_on_bot_clicked` and `_on_fire_clicked`
            # were both None and Detail/Fire did nothing. The columns
            # rendered, which made them look wired.
            #
            # `on_fire_clicked` is LEFT NONE ON PURPOSE. Operator,
            # 2026-08-09: manual fire "is not used for the Simulator
            # which is intended to strictly test trading automation and
            # make user intervention unnecessary." A Simulator whose
            # results depend on someone pressing Fire is not testing
            # automation. The buttons are disabled below so the
            # operator is told that rather than left clicking a dead
            # control.
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

        v3.24.97. Resolves the id against the sim controller ONLY. A
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

        Operator, 2026-08-08: "Add a drop down menu for active simulator
        bots."

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

    # (label, key, tooltip) — the operator's three modes.
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
            # Validation and Looping both drive the fleet page; Nuclear
            # has its own panel.
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

            # 10.4 - READ THE TRANSITION BACK OFF THE WIDGET.
            # `actual` and `expected` were both `key`, so `ok` derived
            # True on every call whatever the stack did. The state this
            # transition changes is the stack page, so `actual` is the
            # index the stack IS on and `expected` is the index the
            # requested mode demands. Qt treats an out-of-range
            # `setCurrentIndex` as a silent no-op, and the mode hand-off
            # above swallows its own exception, so a refused transition
            # was invisible twice over. The mode key moves to context,
            # where it is still recorded.
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

        v3.24.96. Fired by the Load button. Populates the bot table and
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
        # Chart picker + chart series.
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
                # v3.24.96 - REAL STATE, NOT CONFIG DEFAULTS.
                #
                # Before Start Replay no bots are constructed, so the
                # adapter is empty. The first version of this fallback
                # built rows from `config` alone: target 250.00, trades
                # 0, holdings 0 -- while the operator's CHIP bot is
                # 252.1391 with 363 trades and 11,018.76 units.
                #
                # Operator, 2026-08-09: "The button loads a fleet,
                # claims its the live one but it does not match. I do
                # not have my details. I do not have my settings. Its
                # fake." Correct: the LOAD was real, the DISPLAY was
                # config defaults wearing its name.
                #
                # `bot_state_loader` already attaches the whole entry as
                # `_src_scrumming_state` (38 fields) and `_src_stats`
                # (36). Everything below comes from there; config is the
                # fallback of last resort, per bot_state being the only
                # source of initiating state.
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

    # -- pause toggles ---------------------------------------------------

    def _on_activity_paused(self, checked: bool) -> None:
        self._activity_paused = checked
        self._activity_pause_btn.setText("▶  Resume" if checked else "⏸  Pause")

    # v3.24.85 - `_on_perf_paused` removed with the second pane. It
    # set `_perf_pause_btn.setText(...)` on a button that no longer
    # exists, so any caller would have raised AttributeError. Nothing
    # connects to it now: the single pause button drives both stream
    # flags via `_on_activity_paused`.

    # -- public log API (used by future phases) --------------------------

    # v3.24.85 - EMITTERS FOR THE LOG STREAMS.
    #
    # Step 4 of the operator's emitter-first workflow. Before the two
    # panes were merged there was NO emitter on either stream: the
    # existing `feature_telemetry` hooks count calls and skips but carry
    # no expected-vs-actual, so "both streams still arrive after the
    # merge" was not a checkable claim.
    #
    # `sim.06.014.event.log.line` carries the STREAM IDENTITY,
    # which is the property
    # a merge can destroy. One widget receiving everything looks
    # identical to one widget receiving one stream twice unless each
    # line says which stream produced it.
    #
    # Costs nothing when no sink is installed - `emit` is a dict lookup
    # and a return - so this is inert in normal operator runs.

    @staticmethod
    def _emit_log_line(stream: str, line: str, delivered: bool) -> None:
        """Record one log line and the stream that produced it."""
        try:
            from ...core.signal_contract import emit as _emit

            # 10.4 - A SAMPLE, NOT A CHECK. `actual` and `expected`
            # were both `stream`, so `ok` derived True for ever. No
            # independent expectation exists at this point and one must
            # not be invented: `delivered` does vary, but only because
            # the operator PAUSED the pane, so expecting it True would
            # paint the pin red every time the pause button is used.
            # This pin's job is to carry STREAM IDENTITY so a pane
            # merge is detectable, and a merge is only decidable by
            # grouping ACROSS records, never inside one. Dropping
            # `expected` makes `kind` "sample", which is what this
            # always was, and matches the `event` in its own name.
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
        # Tagged: once both streams share a pane, an untagged line is
        # indistinguishable from an activity line.
        self.performance_log.appendPlainText(f"[perf] {line}")
        self._tel_call("sim.performance_log.write")
        self._emit_log_line("performance", line, delivered=True)

    # -- telemetry helpers (v3.24.8) -------------------------------------
    # Deliberately tiny + exception-swallowing: telemetry is advisory
    # and must never break the feature it observes.

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

    # -- async loop wiring (v3.18.7 Phase B) -----------------------------

    def set_async_loop(self, loop) -> None:
        """Attach MainWindow's persistent asyncio loop so Nuclear Mode
        can schedule scout bot coroutines on the same loop everything
        else runs on. Called from MainWindow.set_async_loop after the
        loop is constructed in main.py.
        """
        self._async_loop = loop

    def set_connectors_getter(self, getter) -> None:
        """v3.23.80 shim — kept for back-compat. v3.23.81 moved the
        Fetch YTD enumeration to bot_manager (see set_bot_manager).
        This method is a no-op path retained so an older MainWindow
        build that only knows about the connectors path still boots
        without crashing."""
        self._connectors_getter = getter
        if hasattr(self.fleet_replay, "set_connectors_getter"):
            self.fleet_replay.set_connectors_getter(getter)

    def set_swarm_getter(self, getter) -> None:
        """v3.24.77 — hand the Simulator Swarm to the Nuclear panel.

        Operator directive 2026-08-07: "Nuclear Mode is expected to use
        and abuse the Simulator Bot Swarm."

        It never did, for two independent reasons. The row API lives on
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
        """v3.24.79 — Market Inspector proposals for Nuclear to stress.

        Operator directive 2026-08-07: Nuclear "is supposed to be able to
        receive strategy injections from the Market Inspector to test the
        strategy propagation function and swarm topologies under cycling
        load."

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
        """v3.23.81 — forward the live BotManager to Fleet Replay
        panel so its Fetch YTD button can enumerate real bots via
        the History Tab's `_pairs_from_bot_manager` pattern."""
        if hasattr(self.fleet_replay, "set_bot_manager"):
            self.fleet_replay.set_bot_manager(bot_manager)
