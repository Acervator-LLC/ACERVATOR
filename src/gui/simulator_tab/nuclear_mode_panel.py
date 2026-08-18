"""
src/gui/simulator_tab/nuclear_mode_panel.py — Nuclear Mode controls.

v3.24.78 — REPOINTED at NuclearFleetController (W3).

This panel drove `NuclearController`, the Phase-B single-tape prototype
that v2 was written to replace: the operator picked one tape and one
scout bot walked it. W3 recorded the gap for months —"the tab labelled
Nuclear Mode still drives the Phase-B single-tape prototype".

Operator directive 2026-08-07: Nuclear "does not run on a single tape or
stone tablet. It runs stone tablets in a loop through the simulator
bots. These loops are supposed to have varied market structure via an
oscillator that injects noise to simulate varied market structures
without writing over the stone tablets."

The panel now exposes:
  • Fleet readout — what Start will load from bot_state (bots, symbols,
    Smart Wires). Not a selector: the fleet IS bot_state.
  • Cycle length, max cycles, market-noise toggle, load-oscillation
    toggle
  • Start / Stop
  • Live status — cycles, market-noise amplitude, load multiplier,
    cooling, candles, trades, exceptions, failed cycles

NOT A VALIDATOR. Nuclear runs AFTER trade-logic alignment is proven on
the real tablets, and its noised tape is deliberately not history, so
nothing here compares its output to YTD or live. Its criteria are
coverage and survival.

`nuclear_controller.py` and `nuclear_candle_source.py` are deliberately
NOT deleted: the latter owns `noised_series`, which v2 depends on for
exactly the market-structure noise above.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QFormLayout, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from .nuclear_fleet_controller import (
    DEFAULT_CYCLE_CANDLES,
    NuclearFleetController,
)

logger = logging.getLogger("acervator.nuclear_panel")


_STATUS_FIELDS: tuple[tuple[str, str], ...] = (
    # v3.24.78 — v2's vocabulary. Every key here must exist in
    # `NuclearFleetController.snapshot()`; a key it does not emit renders
    # a permanently blank row, and the panel then looks wired while
    # reporting nothing. Pinned in tests/test_nuclear_panel_drives_v2.py.
    #
    # The retired single-tape fields were: scout_state, scout_holdings,
    # scout_target, tape_position, tape_direction, tape_wraps,
    # world_clock_ticks, trade_count, scrum_fold, error_count,
    # exception_count. Only `running` and `uptime_seconds` survived the
    # move, because v2 does not scout a tape — it loops the fleet's own
    # Stone Tablets under varying market structure and load.
    ("Run state", "running"),
    ("Uptime (s)", "uptime_seconds"),
    ("Fleet size", "fleet_size"),
    ("Symbols", "symbols"),
    ("Smart Wires loaded", "wires_loaded"),
    ("Cycle", "current_cycle"),
    ("Cycles completed", "cycles_completed"),
    ("Market noise", "noise_pct"),
    ("Load multiplier", "load_multiplier"),
    ("Cooling", "cooling"),
    ("Load sensed", "load_sensed"),
    ("Candles played", "total_candles"),
    ("Trades fired", "total_trades"),
    ("Exceptions", "total_exceptions"),
    ("Failed cycles", "failed_cycles"),
    ("Last error", "last_error"),
)
"""Short Live-status fields, laid out across two column-pairs.

``last_exception`` is intentionally absent — it carries arbitrary-length
exception text and gets its own full-width row so it cannot stretch a
column and re-crowd the panel.
"""


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("color: #00ffcc; font-weight: bold;")
    return lbl


class NuclearModePanel(QWidget):
    """Operator-facing panel for Nuclear Mode (fleet soak)."""

    def __init__(self,
                 activity_log_cb: Optional[Callable[[str], None]] = None,
                 perf_log_cb: Optional[Callable[[str], None]] = None,
                 async_loop_getter: Optional[Callable[[], asyncio.AbstractEventLoop]] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Nuclear Mode Panel")
        self._activity_log_cb = activity_log_cb or (lambda _msg: None)
        self._perf_log_cb = perf_log_cb or (lambda _msg: None)
        self._async_loop_getter = async_loop_getter
        # v3.24.77 — resolves the Simulator Swarm at Start. Set by
        # SimulatorTab.set_swarm_getter after MainWindow mounts both
        # tabs; None until then.
        self._swarm_getter = None
        # v3.24.79 — resolves Market Inspector proposals at Start.
        # Set by SimulatorTab.set_topology_getter; None until then.
        self._topology_getter = None
        self._controller: Optional[NuclearFleetController] = None
        # v3.24.28 — shared Simulator visual panels. Assigned by
        # simulator_tab via set_visual_widgets(); None until then, and
        # None is a supported state (the panel runs fine headless).
        self._sim_price_chart = None
        self._sim_voting_readout = None
        self._sim_stat_strip = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        # ─── Header ─────────────────────────────────────────────────
        header_card = QFrame()
        header_card.setStyleSheet(
            "QFrame{background:rgba(255,200,80,8);"
            "border:1px solid #ffcc4444;border-radius:6px;}"
        )
        header_lay = QVBoxLayout(header_card)
        header_lay.setSpacing(4)
        title = QLabel("Nuclear Mode — Fleet Soak")
        title.setStyleSheet(
            "color:#ffcc44;font-size:15px;font-weight:bold;border:none;")
        header_lay.addWidget(title)
        sub = QLabel(
            "Loops the LIVE fleet from bot_state — bots, Smart Wires and "
            "all — over its own Stone Tablets, re-rolling 10-25% "
            "market-structure noise every cycle so no two loops present "
            "the same conditions, while system load oscillates "
            "independently. Exercises real production code paths: trades, "
            "the Simulator Swarm, fold/stack tranches, and data "
            "reliability under load. Tablets are read-only and bot_state "
            "is never written; noise is applied to a copy. This is an "
            "abuse test, not a validation run — it measures coverage and "
            "survival, never trade accuracy.")
        sub.setStyleSheet("color:#aab;border:none;font-size:11px;")
        sub.setWordWrap(True)
        header_lay.addWidget(sub)
        outer.addWidget(header_card)

        # ─── Tape selector ──────────────────────────────────────────
        self._tape_card = QFrame()
        self._tape_card.setStyleSheet(
            "QFrame{background:#0a0a14;border:1px solid #2a2a44;"
            "border-radius:4px;}"
        )
        tape_outer = QVBoxLayout(self._tape_card)
        tape_outer.setContentsMargins(8, 8, 8, 8)
        tape_outer.addWidget(_section_label("Fleet (from bot_state)"))

        # The empty-state body is built but kept hidden when tapes exist
        self._empty_label = QLabel("")
        self._empty_label.setWordWrap(True)
        self._empty_label.setStyleSheet(
            "color:#ff9966;border:none;font-size:11px;")
        self._empty_label.hide()
        tape_outer.addWidget(self._empty_label)

        # v3.24.78 — a FLEET readout, not a tape selector.
        #
        # v1 let the operator pick one tape for one scout bot. v2 loops
        # the whole bot_state fleet over its own Stone Tablets, so there
        # is nothing to select — the fleet IS bot_state. What the
        # operator needs here is confirmation of what Start will load.
        tape_form = QFormLayout()
        tape_form.setSpacing(6)
        self._fleet_detail = QLabel("—")
        self._fleet_detail.setStyleSheet(
            "color:#88c0ff;border:none;font-size:11px;")
        self._fleet_detail.setWordWrap(True)
        tape_form.addRow("Fleet:", self._fleet_detail)

        self._refresh_btn = QPushButton("Reload fleet")
        self._refresh_btn.setStyleSheet(
            "QPushButton{background:#1a1a3a;color:#88aaff;"
            "border:1px solid #88aaff;border-radius:3px;"
            "padding:4px 12px;font-size:11px;}"
            "QPushButton:hover{background:#222250;}"
        )
        self._refresh_btn.clicked.connect(self._rescan_cache)
        tape_form.addRow("", self._refresh_btn)

        tape_outer.addLayout(tape_form)
        outer.addWidget(self._tape_card)

        # ─── Config ─────────────────────────────────────────────────
        cfg_card = QFrame()
        cfg_card.setStyleSheet(
            "QFrame{background:#0a0a14;border:1px solid #2a2a44;"
            "border-radius:4px;}"
        )
        cfg_outer = QVBoxLayout(cfg_card)
        cfg_outer.setContentsMargins(8, 8, 8, 8)
        cfg_outer.addWidget(_section_label("Run configuration"))

        # v3.24.78 — v2's controls. The retired ones (scout seed amount,
        # world-clock cadence) configured the single-tape prototype: a
        # lone scout bot walking one tape. v2 loops the WHOLE fleet from
        # bot_state over its Stone Tablets, so there is no seed to set
        # and no world clock to pace — the fleet's own capital and the
        # tablets' own timestamps supply both.
        cfg_form = QFormLayout()
        cfg_form.setSpacing(6)

        self._cycle_candles_spin = QSpinBox()
        self._cycle_candles_spin.setRange(120, 50_000)
        self._cycle_candles_spin.setSingleStep(500)
        self._cycle_candles_spin.setValue(DEFAULT_CYCLE_CANDLES)
        self._cycle_candles_spin.setSuffix(" candles")
        self._cycle_candles_spin.setToolTip(
            "Candles played per cycle. Each cycle replays the fleet's "
            "tablets under a freshly drawn market structure.")
        cfg_form.addRow("Cycle length:", self._cycle_candles_spin)

        self._max_cycles_spin = QSpinBox()
        self._max_cycles_spin.setRange(0, 100_000)
        self._max_cycles_spin.setValue(0)
        self._max_cycles_spin.setSpecialValueText("unlimited")
        self._max_cycles_spin.setToolTip(
            "Stop after this many cycles. 0 = run until Stop is "
            "clicked — the soak case.")
        cfg_form.addRow("Max cycles:", self._max_cycles_spin)

        self._noise_check = QCheckBox("Vary market structure per cycle")
        self._noise_check.setChecked(True)
        self._noise_check.setToolTip(
            "Re-roll a 10–25% noise amplitude for every cycle, so "
            "successive loops present different market conditions. "
            "Stone Tablets are never modified — the noise is applied to "
            "a copy. Untick to replay the tablets unperturbed, which is "
            "how you ask whether a failure also happens on clean data.")
        cfg_form.addRow("", self._noise_check)

        self._load_osc_check = QCheckBox("Oscillate system load")
        self._load_osc_check.setChecked(True)
        self._load_osc_check.setToolTip(
            "Sweep concurrency across cycles so the platform is "
            "stressed under varying load. Independent of market noise: "
            "this varies how hard the machine works, not what the "
            "market does.")
        cfg_form.addRow("", self._load_osc_check)

        cfg_outer.addLayout(cfg_form)
        outer.addWidget(cfg_card)

        # ─── Start / Stop ───────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._start_btn = QPushButton("Start Scout")
        self._start_btn.setStyleSheet(
            "QPushButton{background:#1a3a2a;color:#00ffcc;"
            "border:1px solid #00ffcc;border-radius:4px;"
            "padding:8px 22px;font-weight:bold;font-size:13px;}"
            "QPushButton:hover{background:#225040;}"
            "QPushButton:disabled{background:#202030;color:#666;"
            "border-color:#444;}"
        )
        self._start_btn.clicked.connect(self._on_start_clicked)
        btn_row.addWidget(self._start_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setStyleSheet(
            "QPushButton{background:#3a1a1a;color:#ff6688;"
            "border:1px solid #ff6688;border-radius:4px;"
            "padding:8px 22px;font-size:13px;}"
            "QPushButton:hover{background:#502222;}"
            "QPushButton:disabled{background:#202030;color:#666;"
            "border-color:#444;}"
        )
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._on_stop_clicked)
        btn_row.addWidget(self._stop_btn)
        btn_row.addStretch()
        outer.addLayout(btn_row)

        # ─── Live status ────────────────────────────────────────────
        status_card = QFrame()
        status_card.setStyleSheet(
            "QFrame{background:#0a0a14;border:1px solid #2a2a44;"
            "border-radius:4px;}"
        )
        status_outer = QVBoxLayout(status_card)
        status_outer.setContentsMargins(8, 8, 8, 8)
        status_outer.addWidget(_section_label("Live status"))

        # v3.24.28 — two column-pairs instead of one.
        #
        # Operator 2026-08-04, on the Nuclear Mode render: "Live status
        # rows are currently cramped. Could be two columns given the
        # amount of space of this specific panel."
        #
        # All 13 short fields previously stacked in a single (label,
        # value) pair, so the card ran tall and narrow while the panel
        # had horizontal room to spare. Splitting into two pairs halves
        # the height and uses the width that was already there.
        #
        # "Last exception" is deliberately NOT in the columns: it holds
        # arbitrary-length exception text, and inside a column it would
        # stretch that column and re-introduce the crowding. It spans
        # the full width on its own row instead.
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(5)
        self._status_labels: dict[str, QLabel] = {}

        def _mk_pair(label: str, key: str) -> tuple[QLabel, QLabel]:
            lbl = QLabel(f"{label}:")
            lbl.setStyleSheet("color:#88aaff;font-size:11px;border:none;")
            val = QLabel("—")
            val.setStyleSheet(
                "color:#fff;font-size:12px;font-weight:bold;border:none;")
            self._status_labels[key] = val
            return lbl, val

        half = (len(_STATUS_FIELDS) + 1) // 2
        for idx, (label, key) in enumerate(_STATUS_FIELDS):
            lbl, val = _mk_pair(label, key)
            if idx < half:
                row, col = idx, 0
            else:
                row, col = idx - half, 2
            grid.addWidget(lbl, row, col, alignment=Qt.AlignLeft)
            grid.addWidget(val, row, col + 1, alignment=Qt.AlignLeft)

        # Value columns absorb the slack; label columns stay tight so the
        # two halves read as two aligned pairs rather than drifting apart.
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 0)
        grid.setColumnStretch(3, 1)

        exc_lbl, exc_val = _mk_pair("Last exception", "last_exception")
        exc_val.setWordWrap(True)
        exc_row = half
        grid.addWidget(exc_lbl, exc_row, 0, alignment=Qt.AlignLeft)
        grid.addWidget(exc_val, exc_row, 1, 1, 3, alignment=Qt.AlignLeft)

        status_outer.addLayout(grid)
        outer.addWidget(status_card)

        outer.addStretch()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(500)
        self._refresh_timer.timeout.connect(self._refresh_status)

        # Initial cache scan to populate the combo
        self._rescan_cache()

    # ─── Tape combo population ──────────────────────────────────────────

    def _rescan_cache(self) -> None:
        """Preview the FLEET this soak will load (v3.24.78).

        This used to populate a tape combo: the operator picked one tape
        and a single scout bot walked it. v2 does not work that way.

        Operator directive 2026-08-07: the only bot source is "a fleet
        load that references bot_state and all pieces / functions of the
        fleet must import". So there is nothing to choose — the fleet IS
        bot_state — and the honest control is a preview of what Start
        will load, not a selector over something else.

        READ ONLY, and cheap: config + wire counts, so the operator can
        see an empty or unexpected fleet BEFORE committing to a soak.
        `prepare()` does the real load at Start and reports its own
        reasons for refusing.
        """
        self._empty_label.hide()
        try:
            from .fleet import bot_state_loader as _loader
            cfgs = _loader.load_bot_configs_from_state()
            wires = _loader.load_smart_wires_from_state()
        except Exception as exc:  # noqa: BLE001 - preview is best-effort
            self._fleet_detail.setText(
                f"Could not read bot_state — {type(exc).__name__}: {exc}")
            self._start_btn.setEnabled(False)
            return

        if not cfgs:
            self._fleet_detail.setText("—")
            self._start_btn.setEnabled(False)
            self._empty_label.setText(
                "bot_state has no scrumming bots, so there is no fleet to "
                "stress.\n\n"
                "Nuclear Mode loops the LIVE fleet's own Stone Tablets "
                "under varying\nmarket structure and system load. It does "
                "not synthesise bots, and it\nnever writes to bot_state or "
                "to the tablet archive.")
            self._empty_label.show()
            return

        symbols = sorted({
            str(c.get("symbol", "") or "") for c in cfgs if c.get("symbol")})
        self._fleet_detail.setText(
            f"{len(cfgs)} bot(s) · {len(symbols)} symbol(s) · "
            f"{len(wires)} Smart Wire(s) from bot_state")
        self._start_btn.setEnabled(True)

    # ─── Slots ──────────────────────────────────────────────────────────

    def _on_start_clicked(self) -> None:
        """Start a fleet soak (v3.24.78 — repointed at v2, per W3).

        This drove `NuclearController`, the single-tape prototype: it
        required a tape cache and a selected tape id, and its
        `start(loop)` was SYNCHRONOUS. `NuclearFleetController` needs
        neither — it reads the fleet from bot_state itself — and its
        `start()` is a COROUTINE.

        That asymmetry is the whole risk of this repoint. Calling a
        coroutine like a sync function produces an un-awaited coroutine
        object: nothing runs, nothing raises, and the buttons below
        latch into the running state over a soak that does not exist.
        Hence `run_coroutine_threadsafe` onto the loop main.py pumps
        from the Qt GUI thread.
        """
        if self._controller is not None and self._controller.is_running():
            return
        loop = None
        if self._async_loop_getter is not None:
            try:
                loop = self._async_loop_getter()
            except Exception:   # R28-OK
                loop = None
        if loop is None:
            self._activity_log_cb(
                "Nuclear: no async loop available; cannot start the soak. "
                "(SimulatorTab must call set_async_loop before launch.)")
            return
        try:
            self._controller = NuclearFleetController(
                cycle_candles=int(self._cycle_candles_spin.value()),
                activity_cb=self._activity_log_cb,
                perf_cb=self._perf_log_cb,
                max_cycles=(int(self._max_cycles_spin.value()) or None),
                load_oscillation=self._load_osc_check.isChecked(),
                noise_enabled=self._noise_check.isChecked(),
            )
        except Exception as exc:  # noqa: BLE001 - construction guard
            self._activity_log_cb(
                f"Nuclear: controller construction failed: "
                f"{type(exc).__name__}: {exc}")
            self._controller = None
            return

        # prepare() reads bot_state and the Stone Tablets, and returns
        # False with an operator-readable reason rather than raising.
        # Gate on it BEFORE scheduling anything: a soak whose fleet did
        # not load cannot do anything except waste a cycle looking busy.
        try:
            ready = self._controller.prepare()
        except Exception as exc:  # noqa: BLE001 - loader guard
            self._activity_log_cb(
                f"Nuclear: fleet load failed: "
                f"{type(exc).__name__}: {exc}")
            self._controller = None
            return
        if not ready:
            self._controller = None
            return

        # Hand over the Simulator Swarm before start, so cycle 0's rows
        # are registered rather than the first cycle running blind.
        _reg, _upd, _stop = self._swarm_hooks()
        if _reg is None:
            self._activity_log_cb(
                "Nuclear: Simulator Swarm unavailable — the soak will run "
                "but will not draw swarm rows.")
        self._controller.set_swarm_hooks(
            register=_reg, update=_upd, stop=_stop)

        # v3.24.79 — inject the Market Inspector's current proposals.
        #
        # Resolved HERE, not at wiring time, so a soak stresses what the
        # operator has on screen when they press Start. With none, the
        # fleet's own persisted bot_state topology stands — nothing is
        # invented to fill the gap (see _topology_pairs).
        _topos = self._resolve_topologies()
        if _topos:
            self._controller.set_topologies(_topos)
            self._activity_log_cb(
                f"Nuclear: injecting {len(_topos)} Market Inspector "
                "topology proposal(s) on top of the fleet's own wires.")
        else:
            self._activity_log_cb(
                "Nuclear: no Market Inspector proposal injected — "
                "stressing the fleet's own bot_state topology.")

        try:
            asyncio.run_coroutine_threadsafe(
                self._controller.start(), loop)
        except Exception as exc:  # noqa: BLE001 - scheduling guard
            self._activity_log_cb(
                f"Nuclear: could not schedule the soak: "
                f"{type(exc).__name__}: {exc}")
            self._controller = None
            return

        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._refresh_btn.setEnabled(False)
        self._cycle_candles_spin.setEnabled(False)
        self._max_cycles_spin.setEnabled(False)
        self._load_osc_check.setEnabled(False)
        self._noise_check.setEnabled(False)
        self._refresh_timer.start()

    def _on_stop_clicked(self) -> None:
        if self._controller is not None:
            self._controller.stop()
        self._stop_btn.setEnabled(False)
        self._start_btn.setEnabled(True)
        self._refresh_btn.setEnabled(True)
        # v3.24.78 — re-enable v2's controls. Must mirror the disable
        # list in _on_start_clicked exactly: a control disabled at Start
        # and not re-enabled here is dead for the rest of the session.
        self._cycle_candles_spin.setEnabled(True)
        self._max_cycles_spin.setEnabled(True)
        self._load_osc_check.setEnabled(True)
        self._noise_check.setEnabled(True)
        # One last poll so the final counts land before the timer stops.
        # Stop is cooperative — the controller drains its current cycle —
        # so this shows the state at the moment Stop was asked, not the
        # state after it completes.
        self._refresh_status()
        self._refresh_timer.stop()

    def set_swarm_getter(self, getter) -> None:
        """v3.24.77 — the Simulator Swarm this mode drives.

        Operator directive 2026-08-07: "Nuclear Mode is expected to use
        and abuse the Simulator Bot Swarm."

        Stored as a getter and resolved at Start, not bound here: the
        Simulator Swarm lives on `BotVisualizationTab`, a different
        top-level tab, and resolving late removes any dependence on
        which tab MainWindow builds first.

        This is the production caller `set_swarm_hooks` never had. Until
        now all three hooks stayed None, so every swarm call inside
        `NuclearFleetController` was a silent no-op — which is what
        `nuclear_verification.py:19` was describing with
        "register_sim_run() zero callers -> swarm rows never driven".
        """
        self._swarm_getter = getter

    def set_topology_getter(self, getter) -> None:
        """v3.24.79 — Market Inspector TOPOLOGY injection.

        Operator, 2026-08-08: "Strategies = Topologies for Market
        Inspector … we should avoid term conflation." A Market Inspector
        proposal IS a topology; "strategy" in the directive below means
        the same object.

        Operator directive 2026-08-07: Nuclear "is supposed to be able to
        receive strategy injections from the Market Inspector to test the
        strategy propagation function and swarm topologies under cycling
        load."

        `NuclearFleetController.set_topologies` had ZERO callers, so the
        proposal branch of `_topology_pairs` never ran — which is exactly
        why the fabricated circular fallback beneath it survived unnoticed
        until v3.24.76 deleted it. This is the caller it was missing.

        A getter resolved at Start, matching the swarm seam: proposals
        change as the operator refreshes the Market Inspector, and a soak
        should stress what is on screen when it starts, not whatever
        existed when the tabs were built.

        NOT THE ADOPT PATH. Adopting a proposal
        (`adoptRequested` → `MainWindow._adopt_topology_proposal`) creates
        real bots and real wires on the LIVE fleet. This only reads the
        proposal so a simulator can replay its shape across sim bots.
        """
        self._topology_getter = getter

    def _resolve_topologies(self) -> list:
        """Proposals to inject this run, or [].

        Degrades to [] on any failure: a broken Market Inspector should
        cost the soak its injection, never its ability to run. With no
        proposals the fleet's own persisted topology from bot_state
        stands, which is the correct baseline.
        """
        getter = getattr(self, "_topology_getter", None)
        if getter is None:
            return []
        try:
            return list(getter() or [])
        except Exception as exc:  # noqa: BLE001 - optional producer
            logger.debug("nuclear: topology getter failed: %s", exc)
            return []

    def _swarm_hooks(self):
        """Resolve (register, update, stop) from the swarm, or Nones.

        Returns the BOUND METHODS of `BotVisualizationTab`, whose
        signatures are the contract the controller calls against:
        `register_sim_run(sim_id, label, cfg)`,
        `update_sim_run(sim_id, pnl, trades, candle_idx)`,
        `stop_sim_run(sim_id, pnl, trades)`.

        Resolution failures degrade to Nones rather than raising: a
        soak that cannot draw its swarm rows is still a valid soak, and
        this must never be the reason Start fails.
        """
        getter = getattr(self, "_swarm_getter", None)
        if getter is None:
            return None, None, None
        try:
            swarm = getter()
        except Exception as exc:  # noqa: BLE001 - optional consumer
            logger.debug("nuclear: swarm getter failed: %s", exc)
            return None, None, None
        if swarm is None:
            return None, None, None
        return (
            getattr(swarm, "register_sim_run", None),
            getattr(swarm, "update_sim_run", None),
            getattr(swarm, "stop_sim_run", None),
        )

    def set_visual_widgets(
        self, price_chart=None, voting_readout=None, stat_strip=None,
    ) -> None:
        """Attach the shared Simulator visual panels.

        v3.24.28 — Nuclear Mode never received these. ``simulator_tab``
        called ``set_visual_widgets`` on the Fleet Replay panel ONLY, so
        the Indicator Voting Panel, the per-bot voting table and the
        price/VWAP chart could not populate while a scout ran — they had
        no feed at all, by construction. The Activity Log worked because
        it is wired through a separate ``activity_log_cb``, which is why
        the failure looked selective rather than structural.

        Mirrors ``FleetReplayPanel.set_visual_widgets`` so the two modes
        present the same contract to ``simulator_tab``.
        """
        self._sim_price_chart = price_chart
        self._sim_voting_readout = voting_readout
        self._sim_stat_strip = stat_strip

    def _feed_visuals(self, snap: dict) -> None:
        """Push scout state into the shared panels.

        Runs on the Qt main thread — ``_refresh_timer`` is a QTimer, so
        this is already the correct thread for widget mutation. That is
        deliberate: v3.24.19 had to undo exactly this being done from a
        worker thread in Fleet Replay.

        Best-effort per widget: a missing or failing panel must not stop
        the scout, but it is logged rather than swallowed.
        """
        symbol = str(snap.get("symbol", "") or "")
        if not symbol:
            return

        chart = getattr(self, "_sim_price_chart", None)
        if chart is not None:
            try:
                px = float(snap.get("last_price", 0.0) or 0.0)
                if px > 0:
                    chart.append_tick(
                        symbol, close_price=px,
                        volume=float(snap.get("last_volume", 0.0) or 0.0))
                    chart.update()
            except Exception as exc:  # noqa: BLE001 - GUI best-effort
                logger.debug("nuclear: price chart feed failed: %s", exc)

        readout = getattr(self, "_sim_voting_readout", None)
        summary = snap.get("voting_summary")
        if readout is not None and summary is not None:
            try:
                # v3.24.81 — the REAL IndicatorVotingPanel's contract,
                # identical to the Trading Tab's feed and to Fleet
                # Replay's. `update_bot_row` was the sim-only summary
                # table's API and no longer exists.
                _tf = str(getattr(summary, "timeframe", "") or "5m")
                readout.update_data({_tf: {
                    "bullish": summary.bullish_count,
                    "bearish": summary.bearish_count,
                    "neutral": summary.neutral_count,
                    "net_score": summary.net_score,
                    "confidence": summary.consensus_confidence,
                    "direction": summary.consensus_direction.name,
                    "signals": [
                        {"indicator": _s.indicator,
                         "direction": _s.direction.name,
                         "confidence": _s.confidence, "details": {}}
                        for _s in summary.signals],
                    "locks": [],
                }}, symbol)
            except Exception as exc:  # noqa: BLE001 - GUI best-effort
                logger.debug("nuclear: voting readout feed failed: %s", exc)


    def _refresh_status(self) -> None:
        """Fill the live status rows from the controller snapshot.

        v3.24.80 — REWRITTEN for v2's vocabulary.

        The v3.24.78 repoint changed `_STATUS_FIELDS` (which builds the
        LABELS) and left this function (which FILLS them) writing v1's
        keys: scout_state, tape_position, tape_wraps and nine more.
        Those labels no longer exist, so the third write raised
        KeyError and killed the 500 ms timer callback. On screen: Run
        state and Uptime populated, thirteen rows stuck on "-".

        The pin meant to catch this asserted every `_STATUS_FIELDS` key
        exists in `snapshot()`. It did. The pin checked the DECLARATION
        and never that anything WRITES them, so it passed against a
        visibly broken panel.

        Driven off `_STATUS_FIELDS` itself now, so the labels and the
        values cannot drift apart again, and defensively: a missing key
        renders "-" instead of killing the timer.
        """
        if self._controller is None:
            return
        try:
            snap = self._controller.snapshot()
        except Exception as exc:  # noqa: BLE001 - must not kill the timer
            logger.debug("nuclear: snapshot failed: %s", exc)
            return
        try:
            self._feed_visuals(snap)
        except Exception as exc:  # noqa: BLE001 - visuals are advisory
            logger.debug("nuclear: visual feed failed: %s", exc)

        for _label, key in _STATUS_FIELDS:
            lbl = self._status_labels.get(key)
            if lbl is None:
                continue
            try:
                lbl.setText(self._fmt_status(key, snap.get(key)))
            except Exception as exc:  # noqa: BLE001 - one bad field only
                logger.debug("nuclear: status field %s: %s", key, exc)

        last = self._status_labels.get("last_exception")
        if last is not None:
            txt = str(snap.get("last_error", "") or "")
            last.setText(txt if txt else "-")

    @staticmethod
    def _fmt_status(key: str, val) -> str:
        """Render one snapshot value for the status grid."""
        if val is None:
            return "-"
        if key == "running":
            return "RUNNING" if val else "stopped"
        if key == "uptime_seconds":
            return f"{float(val):.1f}"
        if key == "noise_pct":
            # Amplitude is a fraction (0.10-0.25); the operator's
            # directive is written in percent, so show percent.
            return f"{float(val) * 100.0:.1f}%" if val else "-"
        if key == "load_multiplier":
            return f"{float(val):.2f}x"
        if key in ("cooling", "load_sensed"):
            return "yes" if val else "no"
        if isinstance(val, bool):
            return "yes" if val else "no"
        if isinstance(val, float):
            return f"{val:,.2f}"
        if isinstance(val, int):
            return f"{val:,}"
        return str(val) if str(val) else "-"
