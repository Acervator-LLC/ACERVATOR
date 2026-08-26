"""fleet_replay_panel.py — GUI panel for the Simulator's Fleet Replay
mode.

v3.23.79 upgrade of v3.23.72 MVP:
  * Bot row rendering is a real QTableWidget (was a bare list, which
    the operator called "sloppy" 2026-07-31).
  * Start Replay button ENABLED. Wires to FleetReplayController.
  * Panel drives the controller with synthetic candles for now
    (proves the whole pipeline plays real ScrummingBot.tick() against
    FleetSimExchange). Real YTD candles lands v3.23.79-B once the
    History Tab's Refresh signal is bridged.
  * Progress row shows candles played, trades fired, exception count.

sadp: R28 SSS + R70 RCN
"""

from __future__ import annotations

import asyncio
import logging
import math
import threading
from typing import Any, Callable, Optional

logger = logging.getLogger("acervator.simulator.fleet.panel")


# ── telemetry helpers (v3.24.8) ──────────────────────────────────
# Module-level so the per-tick visual refresh can call them without
# attribute lookup on self. Deliberately exception-swallowing:
# telemetry is advisory and must never break the feature it watches.


def _tel_call(name: str, count: int = 1) -> None:
    try:
        from src.core.feature_telemetry import get_telemetry

        get_telemetry().record_call(name, count=count)
    except Exception:  # noqa: BLE001,S110 - advisory only
        pass


def _tel_skip(name: str, reason: str) -> None:
    try:
        from src.core.feature_telemetry import get_telemetry

        get_telemetry().record_skip(name, reason=reason)
    except Exception:  # noqa: BLE001,S110 - advisory only
        pass


def _tel_exc(name: str, exc: BaseException) -> None:
    try:
        from src.core.feature_telemetry import get_telemetry

        get_telemetry().record_exception(name, exc)
    except Exception:  # noqa: BLE001,S110 - advisory only
        pass


try:
    from PySide6.QtCore import QTimer, Signal
    from PySide6.QtWidgets import (
        QCheckBox,
        QFrame,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    _HAS_QT = True
except ImportError:  # pragma: no cover - GUI-only guard
    _HAS_QT = False


def _synthesize_candles_for_symbol(
    symbol: str,
    n_candles: int = 200,
    base_price: float = 100.0,
) -> list[list[float]]:
    """Sine-wave candles for a symbol. Used until real YTD data is
    wired via History Tab's history_refreshed signal.

    Row shape [ts_ms, o, h, l, c, v] — same as ccxt.
    """
    # Deterministic per-symbol seed so re-runs of the same fleet
    # produce the same pattern (helps operator eyeball).
    seed = sum(ord(c) for c in symbol) or 1
    rows: list[list[float]] = []
    base_ts = 1_700_000_000_000
    step_ms = 3600_000  # 1h candles
    for i in range(n_candles):
        wave = math.sin((i + seed) * 0.05) * 0.03
        drift = 0.001 * i
        c = base_price * (1.0 + wave + drift)
        o = base_price * (
            1.0 + math.sin((i - 1 + seed) * 0.05) * 0.03 + 0.001 * (i - 1)
        )
        h = max(o, c) * 1.005
        low = min(o, c) * 0.995
        rows.append([base_ts + i * step_ms, o, h, low, c, 100.0])
    return rows


if _HAS_QT:

    class FleetReplayPanel(QWidget):
        """Left-column Simulator content for Fleet Replay mode.

        v3.23.79 upgrade:
          * Loaded-fleet is a QTableWidget with (Symbol, Target USD,
            Sim Trades, Status) columns instead of the sloppy
            single-string list rows.
          * Start Replay is live: builds synthetic candles for each
            loaded bot's symbol, boots a FleetReplayController, and
            plays candles until Stop or exhaustion.
          * Progress row updates on a 500 ms QTimer: candles played,
            trades fired, exceptions.

        Emits ``fleetLoaded(list)`` on Load, ``replayStarted()`` /
        ``replayStopped()`` for external listeners.
        """

        fleetLoaded = Signal(list)
        replayStarted = Signal()
        replayStopped = Signal()

        # v3.24.86 — 3 columns. The Gates column moved OUT to
        # `GateStatusPanel`, which the Simulator tab hosts where the
        # Performance Log used to sit (operator task 2026-08-08,
        # screenshot area 2). A ten-LED labelled row was bounded by the
        # column width here; in its own pane it draws at full size.
        COLUMNS = ("Symbol", "Target USD", "Sim Trades")

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            self.setAccessibleName("Fleet Replay Panel")
            # v3.24.86 — the gate display lives here and is HOSTED by
            # the Simulator tab, which reparents it into the pane the
            # Performance Log used to occupy. Owned by this panel
            # because this panel knows the fleet; positioned by the tab
            # because the tab owns the layout.
            self._gate_host_kind = "panel"
            self._gate_panel = None
            try:
                from .sim_visuals import GateStatusPanel as _gsp

                # PARENTED TO THIS PANEL. Built without a parent it is
                # a TOP-LEVEL WINDOW that only acquires an owner if a
                # host reparents it into a layout. Any FleetReplayPanel
                # constructed without one -- every headless test -- then
                # leaked a top-level widget, and enough of them
                # accumulating across a suite run segfaulted Qt (exit
                # 139, no failure summary). Reparenting into the tab's
                # layout afterwards is ordinary Qt and unaffected.
                self._gate_panel = _gsp(self)
            except Exception as _gsp_exc:  # noqa: BLE001 - GUI import guard
                logger.debug("GateStatusPanel unavailable: %s", _gsp_exc)
                self._gate_host_kind = "table"
            self._configs: list[dict] = []
            # v3.24.72 (C20) — bot_state's top-level smart_wires,
            # populated by Load alongside _configs.
            self._smart_wires: list[dict] = []
            self._controller = None
            self._progress_timer: Optional[QTimer] = None
            self._async_loop_getter = None
            # v3.23.84 — Load and Fetch YTD are INDEPENDENT.
            # Load reads bot_state.json → self._configs.
            # Fetch YTD calls fetch_all_history_chunked(bot_manager)
            # → self._ytd_trades. Neither depends on the other's
            # state. Operator directive 2026-07-31: "Why is it not
            # just doing a matching YTD fetch like the History Tab!?
            # You are merging bot loading (step 1) with YTD fetch
            # (2) and making the 2nd depend on non-relevant states
            # of the first?"
            self._bot_manager = None
            self._connectors_getter = None  # retained shim; unused
            # v3.24.1 — log-callback wiring. SimulatorTab calls
            # set_log_callbacks(activity_cb, perf_cb) after mount so
            # the fleet controller's per-event messages route to the
            # on-screen Activity/Performance panels. Prior default
            # (logger.info) meant the panels were unreachable.
            self._activity_log_cb: Optional[Callable[[str], None]] = None
            self._performance_log_cb: Optional[Callable[[str], None]] = None
            # v3.24.19 — worker->GUI handoff. The replay worker writes
            # a plain snapshot here; a QTimer on the Qt main thread
            # drains it. Latest-wins: an un-drained frame is replaced
            # rather than queued, because a stale frame has no value.
            self._snapshot_lock = threading.Lock()
            self._pending_snapshot: Optional[dict] = None
            self._drain_timer: Optional[QTimer] = None
            # v3.24.9 — stat strip handle. Set via set_visual_widgets.
            self._sim_stat_strip = None
            # v3.24.3 — visual widgets wired by SimulatorTab after
            # mount. Panel drives per-tick updates when Start Replay
            # runs. Kept as attrs (not required at construction) so
            # tests can construct the panel without Qt.
            self._sim_price_chart = None
            self._sim_voting_readout = None
            # bot_id -> GateLightsCell widget (indexed at Load time)
            self._gate_cells: dict[str, Any] = {}
            self._ytd_trades: list[dict] = []
            # v3.23.88 — restored after v3.23.83 rename purge that
            # missed line 454's `_on_start_clicked` reference. The
            # AttributeError there was swallowed by the Qt slot's
            # implicit try/except, which made Start Replay silently
            # do nothing — no status change, no log line, no error
            # popup. Exactly the scaffolding/hallucination-adjacent
            # bug pattern the operator flagged 2026-08-01.
            self._real_candles: dict[str, list[list[float]]] = {}

            outer = QVBoxLayout(self)
            outer.setContentsMargins(10, 10, 10, 10)
            outer.setSpacing(10)

            # ── Header ────────────────────────────────────────────
            header = QFrame()
            header.setStyleSheet(
                "QFrame{background:rgba(0,255,204,10);"
                "border:1px solid #00cccc44;border-radius:6px;}"
            )
            hlay = QVBoxLayout(header)
            title = QLabel("Fleet Replay — sim the live fleet against YTD data")
            title.setStyleSheet(
                "color:#00ffcc;font-size:15px;font-weight:bold;" "border:none;"
            )
            hlay.addWidget(title)
            sub = QLabel(
                "Loads every live bot config from bot_state.json and "
                "runs isolated ScrummingBot instances against a fake "
                "FleetSimExchange. Bot class code is unmodified — "
                "parity with live is the point. Start Replay currently "
                "plays synthetic candles for immediate observability; "
                "real YTD candle feed lands v3.23.79-B via History "
                "Tab's Refresh signal."
            )
            sub.setWordWrap(True)
            sub.setStyleSheet("color:#aaa;font-size:11px;border:none;")
            hlay.addWidget(sub)
            outer.addWidget(header)

            # ── Load bar ──────────────────────────────────────────
            load_row = QHBoxLayout()
            self._load_btn = QPushButton("Load live fleet")
            self._load_btn.setToolTip(
                "Read ~/.acervator/bot_state.json and load every "
                "Scrumming bot config as a fresh sim instance."
            )
            self._load_btn.clicked.connect(self._on_load_clicked)
            load_row.addWidget(self._load_btn)
            # v3.23.80 — Fetch YTD button pulls real OHLCV per
            # loaded-bot symbol from the connected exchange via
            # MarketDataPool. When populated, Start Replay uses the
            # real candles; otherwise it falls back to synthetic.
            self._fetch_ytd_btn = QPushButton("Fetch YTD")
            self._fetch_ytd_btn.setEnabled(False)
            self._fetch_ytd_btn.setToolTip(
                "Pull real 1d OHLCV (limit=200 candles ≈ 6.5 months) "
                "per loaded-bot symbol from the connected exchange. "
                "Coalesced through MarketDataPool. After this "
                "completes, Start Replay uses real market data "
                "instead of synthetic sine waves."
            )
            self._fetch_ytd_btn.clicked.connect(self._on_fetch_ytd_clicked)
            load_row.addWidget(self._fetch_ytd_btn)
            self._reset_btn = QPushButton("Reset")
            self._reset_btn.setToolTip(
                "Clear the loaded fleet + stop any running replay."
            )
            self._reset_btn.clicked.connect(self._on_reset_clicked)
            load_row.addWidget(self._reset_btn)

            # v3.24.15 — evaluation-mode toggle. Operator directive
            # 2026-08-03: "We want the simulated indicators to be
            # valid signals but we do not need to check it when
            # nothing happened historically. Its only necessary to
            # check every candle when customizing strategies or
            # implementing new ones."
            #
            # Unchecked (default) = validation run: the read head
            # evaluates only candles carrying a historical trade,
            # plus a warm-up window so the indicators are primed.
            # Checked = strategy run: every candle evaluated, which
            # is the only mode that can detect the sim FIRING where
            # live did not.
            self._full_eval_chk = QCheckBox("Full evaluation")
            self._full_eval_chk.setChecked(False)
            self._full_eval_chk.setToolTip(
                "Unchecked (default): validation run — only candles "
                "with a historical trade are evaluated, each preceded "
                "by a warm-up window so indicators are valid. Much "
                "faster.\n\n"
                "Checked: strategy run — every candle is evaluated. "
                "Slower, but required when developing or tuning a "
                "strategy, and the only mode that detects the sim "
                "trading where live did not."
            )
            load_row.addWidget(self._full_eval_chk)
            load_row.addStretch()
            self._status_lbl = QLabel("No fleet loaded — press Load live fleet.")
            self._status_lbl.setStyleSheet("color:#888;font-size:11px;")
            load_row.addWidget(self._status_lbl)
            outer.addLayout(load_row)

            # ── Loaded fleet table (v3.23.79 replaces the list) ──
            self._fleet_group = QGroupBox("Loaded fleet")
            fg = QVBoxLayout(self._fleet_group)
            self._fleet_table = QTableWidget(0, len(self.COLUMNS), self._fleet_group)
            self._fleet_table.setToolTip(
                "One row per Scrumming bot from bot_state.json. "
                "Sim Trades increments live during Start Replay."
            )
            self._fleet_table.setHorizontalHeaderLabels(list(self.COLUMNS))
            self._fleet_table.setAlternatingRowColors(True)
            self._fleet_table.setEditTriggers(QTableWidget.NoEditTriggers)
            hdr = self._fleet_table.horizontalHeader()
            hdr.setSectionResizeMode(QHeaderView.ResizeToContents)
            hdr.setStretchLastSection(True)
            fg.addWidget(self._fleet_table)
            outer.addWidget(self._fleet_group, stretch=1)

            # ── Progress row ──────────────────────────────────────
            self._progress_lbl = QLabel(
                "Replay idle — load a fleet + press Start Replay."
            )
            self._progress_lbl.setStyleSheet(
                "color:#7fb3ff; font-size:11px; padding:2px 6px;"
            )
            self._progress_lbl.setWordWrap(True)
            outer.addWidget(self._progress_lbl)

            # ── Start / stop ──────────────────────────────────────
            run_row = QHBoxLayout()
            run_row.addStretch()
            self._start_btn = QPushButton("Start Replay")
            self._start_btn.setEnabled(False)
            self._start_btn.setToolTip(
                "Play synthetic candles through each loaded bot's "
                "tick(). Real YTD data lands v3.23.79-B."
            )
            self._start_btn.clicked.connect(self._on_start_clicked)
            run_row.addWidget(self._start_btn)
            self._stop_btn = QPushButton("Stop")
            self._stop_btn.setEnabled(False)
            self._stop_btn.setToolTip(
                "Cooperative stop; tick loop drains its current " "iteration and exits."
            )
            self._stop_btn.clicked.connect(self._on_stop_clicked)
            run_row.addWidget(self._stop_btn)
            outer.addLayout(run_row)

        # ── External wiring hooks ────────────────────────────────
        def set_async_loop_getter(self, getter) -> None:
            """Wire the app's asyncio loop so Start Replay can schedule
            the controller. MainWindow calls this after construction."""
            self._async_loop_getter = getter

        def set_visual_widgets(
            self,
            price_chart=None,
            voting_readout=None,
            stat_strip=None,
        ) -> None:
            """v3.24.3 — wire the Indicator Voting Panel widgets so
            per-tick updates land in them. Called by SimulatorTab
            after both this panel + the visuals are constructed.

            v3.24.9 — stat_strip added. Telemetry proved
            ``SimStatStrip.set()`` had ZERO call sites, which is why
            the 10-field header showed dashes in every operator
            screenshot. Passing the widget here gives the per-tick
            refresh something to feed."""
            self._sim_price_chart = price_chart
            self._sim_voting_readout = voting_readout
            self._sim_stat_strip = stat_strip

        def set_log_callbacks(
            self,
            activity_cb: Optional[Callable[[str], None]],
            performance_cb: Optional[Callable[[str], None]],
        ) -> None:
            """v3.24.1 — wire the on-screen Activity/Performance log
            widgets so the fleet replay controller's messages actually
            reach the operator. Prior default routed to logger.info
            which meant the panels were unreachable (scaffolding scan
            finding #1)."""
            self._activity_log_cb = activity_cb
            self._performance_log_cb = performance_cb

        def set_bot_manager(self, bot_manager) -> None:
            """v3.23.84 — bot_manager is the SAME argument the History
            Tab passes to fetch_all_history_chunked. Fetch YTD does
            exactly what History Tab's Refresh does."""
            self._bot_manager = bot_manager
            self._fetch_ytd_btn.setEnabled(bot_manager is not None)

        def set_connectors_getter(self, getter) -> None:
            """v3.23.84 shim — retained so any MainWindow that only
            knows the connectors-getter API still boots. Fetch YTD
            no longer uses this path; it calls the same
            fetch_all_history_chunked() as History Tab."""
            del getter

        # ── H4 bridge slot (v3.23.88) ────────────────────────────
        def on_history_refreshed(self, trades) -> None:
            """v3.23.88 — receive History Tab's ``history_refreshed``
            signal. Operator directive 2026-07-31 (H4): History Tab
            Refresh front-loads Simulator with current YTD data.

            History Tab's signal payload is a ``list[dict]`` matching
            the same schema Fetch YTD produces — store it in
            ``_ytd_trades`` so Start Replay uses it directly (no
            need to click Fetch YTD after a History refresh).
            """
            try:
                self._ytd_trades = list(trades or [])
            except Exception as _bx_exc:  # noqa: BLE001 - defensive
                logger.warning(
                    "on_history_refreshed: list coercion failed: %s", _bx_exc
                )
                return
            n = len(self._ytd_trades)
            by_symbol: dict[str, int] = {}
            for t in self._ytd_trades:
                s = str(t.get("symbol", ""))
                if s:
                    by_symbol[s] = by_symbol.get(s, 0) + 1
            logger.info(
                "H4 front-load received from History: %d trades " "across %d symbol(s)",
                n,
                len(by_symbol),
            )
            if n > 0:
                self._status_lbl.setText(
                    f"YTD front-loaded from History: {n:,} trades "
                    f"across {len(by_symbol)} symbol(s)."
                )
            else:
                self._status_lbl.setText(
                    "History refresh emitted 0 trades " "(nothing to front-load)."
                )

        # ── Slots ────────────────────────────────────────────────
        def _on_load_clicked(self) -> None:
            try:
                from .bot_state_loader import (
                    load_bot_configs_from_state,
                    load_smart_wires_from_state,
                    summarize_loaded_configs,
                )

                self._configs = load_bot_configs_from_state()
                # v3.24.72 (C20) — the fleet's persisted Smart Wires.
                # Loaded alongside the configs because they join on the
                # same key (`_src_bot_id`), and a replay without them
                # runs with cross-bot compounding inert, which
                # understates the accumulation curve against live.
                self._smart_wires = load_smart_wires_from_state()
                summary = summarize_loaded_configs(self._configs)
            except Exception as exc:  # noqa: BLE001 - loader surface
                logger.exception("FleetReplayPanel load failed: %s", exc)
                self._status_lbl.setText(f"Load failed: {type(exc).__name__}: {exc}")
                return
            self._populate_fleet_table()
            # v3.24.96 — LOAD SPAWNS THE FLEET.
            #
            # Operator, 2026-08-09: "a fully simulated instance of every
            # live bot should be spawned when i click load... not
            # partial...not sort of...not diet versions...fully
            # simulated."
            #
            # Load used to fill a table and nothing else; real
            # ScrummingBot instances appeared only on Start Replay. The
            # table was therefore populated from bot_state DICTS, which
            # is how it ended up showing live bot IDs on a simulator
            # surface -- a Fire click there would resolve against the
            # LIVE manager.
            #
            # Now Load builds the controller and calls `_build_sim`, so
            # every row is backed by a constructed sim bot with a
            # `simulated_` id, its scrumming_state imported, its wires
            # attached and its capital registry isolated. Candles come
            # from the Stone Tablet registry on disk -- the same
            # `reg.get_candles` path Start Replay uses, not a second
            # one.
            _spawned = 0
            try:
                _spawned = self._spawn_sim_fleet()
            except Exception as _spawn_exc:  # noqa: BLE001
                logger.exception("sim fleet spawn failed: %s", _spawn_exc)
                self._status_error(
                    f"Fleet spawn failed: {type(_spawn_exc).__name__}: " f"{_spawn_exc}"
                )
            self._status_lbl.setText(
                f"Loaded {summary['bot_count']} bot(s) across "
                f"{summary['symbol_count']} symbol(s) — "
                f"${summary['total_target_usd']:,.0f} total target"
                + (
                    f" — {_spawned} simulated bot(s) spawned."
                    if _spawned
                    else " — NO bots spawned (no tablets?)."
                )
            )
            self._start_btn.setEnabled(len(self._configs) > 0)
            # v3.23.84 — Fetch YTD is INDEPENDENT of Load. It only
            # needs bot_manager (same as History Tab). Do NOT gate
            # on _configs being loaded — the two buttons are
            # independent workflows.
            try:
                self.fleetLoaded.emit(list(self._configs))
            except Exception:  # noqa: S110 - signal best-effort
                pass

        def _spawn_sim_fleet(self) -> int:
            """Construct a real sim bot for every loaded config.

            v3.24.96. Returns the number spawned.

            Reuses the Stone Tablet registry read that Start Replay
            performs, rather than adding a second candle path -- two
            paths to the same data is how they end up disagreeing.

            The controller is built but NOT started: the bots exist,
            hold their imported state and can be inspected, and the
            tape only advances when the operator presses Start Replay.
            """
            if not self._configs:
                return 0

            # 10.3 phase 2 — the spawn starts BELOW the two imports and
            # after the empty-configs guard. `sim.06.007` carries
            # `missing_tablets` in its context, so the operation it observes
            # INCLUDES loading candles from the tablet registry, not just
            # constructing the controller. That is still the boundary; only
            # the imports moved out of it.
            #
            # WHY THE IMPORTS SIT OUTSIDE THE CLOCK. They are lazy, so the
            # FIRST call in a process pays the whole interpreter cost of
            # loading both modules and every call after it pays nothing,
            # because Python serves them from `sys.modules`. Inside the
            # bracket that made record 1 incomparable to record 2: item 17
            # reads this field as latency, so the first spawn of every
            # process would always look like the slow one. Loading a module
            # is not spawn work and it never happens twice.
            #
            from src.trading.stone_tablets.registry import get_registry
            from .fleet_replay_controller import FleetReplayController

            reg = get_registry()
            candles: dict = {}
            missing: list = []
            for cfg in self._configs:
                sym = str(cfg.get("symbol", "") or "")
                if not sym or sym in candles:
                    continue
                asset = sym.split("/", 1)[0].upper() if "/" in sym else sym
                try:
                    rows = reg.get_candles(
                        asset=asset,
                        since_ms=0,
                        until_ms=9_999_999_999_999,
                        timeframe="5m",
                        exchange_id=str(
                            cfg.get("exchange_id", "coinbase") or "coinbase"
                        ),
                    )
                except Exception as _rc_exc:  # noqa: BLE001
                    logger.debug("tablet read failed for %s: %s", sym, _rc_exc)
                    rows = None
                if rows:
                    candles[sym] = list(rows)
                else:
                    missing.append(sym)
            if missing:
                # Named, not silently dropped: a bot with no tablet
                # cannot be simulated, and the operator needs to know
                # WHICH rather than discovering a short fleet.
                _log_missing = self._activity_log_cb or (
                    lambda m: logger.info("[FleetReplay] %s", m)
                )
                _log_missing(
                    f"No Stone Tablet for {len(missing)} symbol(s): "
                    f"{', '.join(missing[:8])}" + (" ..." if len(missing) > 8 else "")
                )
            if not candles:
                return 0

            # The SAME callback resolution Start Replay uses
            # (fleet_replay_panel.py:1272) rather than a second one.
            _act_cb = self._activity_log_cb or (
                lambda m: logger.info("[FleetReplay] %s", m)
            )
            _perf_cb = self._performance_log_cb or (
                lambda m: logger.info("[FleetReplay perf] %s", m)
            )
            self._controller = FleetReplayController(
                configs=list(self._configs),
                candles_by_symbol=candles,
                smart_wires=list(getattr(self, "_smart_wires", []) or []),
                tick_delay_s=0.0,
                activity_log_cb=_act_cb,
                performance_log_cb=_perf_cb,
                max_candles=None,
            )
            self._controller._build_sim()
            n = len(list(getattr(self._controller, "_bots", []) or []))
            _act_cb(
                f"Spawned {n} simulated bot(s) from bot_state "
                f"({len(candles)} symbol(s) with tablets)."
            )

            # v3.24.96 — PERSIST THE SIM FLEET'S OWN STATE, AND CHECK
            # IT AGAINST bot_state.
            #
            # Operator, 2026-08-09: sim bots must "have their own
            # configuration section under simulator_bot_state AFTER
            # being correctly spawned the first time.
            # simulator_bot_state parity checks against bot_state."
            #
            # Written to ~/.acervator/simulator_bot_state.json, BESIDE
            # bot_state and never into it -- `save_sim_state` refuses
            # the live path outright.
            #
            # The parity comparison is the point. Every sim bot records
            # the `source_bot_id` it was cloned from and a field-by-field
            # diff of its imported scrumming_state against that live
            # entry, as canonical JSON so lot CONTENTS count rather than
            # lot counts. Green here means the import was faithful;
            # divergence later is the simulation doing its job.
            try:
                from .simulator_bot_state import (
                    build_sim_state,
                    compare_to_bot_state,
                    diff_spawns,
                    load_sim_state,
                    save_sim_state,
                )

                _state = build_sim_state(
                    list(getattr(self._controller, "_bots", []) or []),
                    source_configs=list(self._configs),
                )
                _parity = compare_to_bot_state(_state)
                _bad = {
                    k: v
                    for k, v in _parity.items()
                    if v.get("differing") or v.get("error")
                }
                _state["parity"] = _parity
                # v3.24.99 — READ THE LAST SPAWN BEFORE OVERWRITING IT.
                # `save_sim_state` clobbers the file on every Load, so
                # this is the only moment the previous document exists.
                # Without it the persisted state was write-only and the
                # operator could not tell one Load from the next.
                _drift = diff_spawns(load_sim_state(), _state)
                save_sim_state(_state)
                _act_cb(
                    f"simulator_bot_state saved: {_state['bot_count']} "
                    f"bot(s); parity green on "
                    f"{len(_parity) - len(_bad)}/{len(_parity)}."
                )
                if _bad:
                    for _sid, _info in list(_bad.items())[:5]:
                        _act_cb(
                            f"  PARITY MISMATCH {_sid}: "
                            f"{_info.get('error') or _info.get('differing')}"
                        )
                if _drift.get("first_spawn"):
                    _act_cb("spawn drift: first spawn, no prior state.")
                else:
                    _act_cb(
                        f"spawn drift vs last Load: "
                        f"{len(_drift['added'])} added, "
                        f"{len(_drift['removed'])} removed, "
                        f"{len(_drift['changed'])} live-source changed, "
                        f"{_drift['unchanged']} identical."
                    )
                    for _sid in _drift["changed"][:5]:
                        _act_cb(f"  LIVE SOURCE MOVED {_sid}")
            except Exception as _sbs_exc:  # noqa: BLE001
                logger.exception("simulator_bot_state persist failed: %s", _sbs_exc)
                _act_cb(f"simulator_bot_state FAILED: {_sbs_exc}")
            return n

        def _gate_cell_for(self, symbol: str):
            """The gate row widget for *symbol*, wherever it lives.

            v3.24.86 - indirection added so moving the display out of
            the fleet table changes the SOURCE of the widget, not every
            call site that paints one. `_gate_panel` wins when present;
            the table cells remain the fallback until it exists.
            """
            panel = getattr(self, "_gate_panel", None)
            if panel is not None:
                return panel.cell_for(symbol)
            return self._gate_cells.get(symbol)

        def sim_bot_statuses(self) -> list:
            """The fleet as `BotStatusTable.update_bots()` status dicts.

            v3.24.91. Operator task 2026-08-08 (screenshot area 5):
            "Needs to be redesigned to match the Trading Tab's bot
            area."

            NOT A NEW TABLE. `BotStatusTable` already renders exactly
            the columns the operator pointed at -- Bot ID, Symbol, Mode,
            Trades, Target, Target BTC, Target ETH, Ammo, Fire, Detail
            -- with the header dots, the state colouring and the Ammo
            arithmetic. Rebuilding that here would be the
            `FleetSimExchange` mistake again: a second implementation
            of a thing that exists, guaranteed to drift.

            So this is an ADAPTER. It produces the shape that table
            already consumes, and the sim gets the Trading Tab's bot
            area because it IS the Trading Tab's bot area.

            The contract, read off `update_bots`:
              status: bot_id, symbol, mode, state, exchange,
                      target_balance, live_target_balance,
                      current_holdings, quote_to_usd, stats
              stats:  current_price, position_value
            """
            out: list = []
            ctl = getattr(self, "_controller", None)
            bots = list(getattr(ctl, "_bots", []) or [])
            tape = getattr(ctl, "_tape", None)
            for bot in bots:
                try:
                    cfg = getattr(bot, "config", None)
                    if cfg is None:
                        continue
                    sym = str(getattr(cfg, "symbol", "") or "")
                    px = 0.0
                    if tape is not None and hasattr(tape, "history"):
                        try:
                            rows = tape.history(sym, 1)
                            if rows:
                                px = float(rows[-1][4])
                        except Exception:  # noqa: BLE001 - tape may be idle
                            px = 0.0
                    holdings = float(getattr(bot, "_current_holdings", 0.0) or 0.0)
                    out.append(
                        {
                            "bot_id": str(getattr(bot, "bot_id", "")),
                            "symbol": sym,
                            "mode": str(
                                getattr(getattr(cfg, "mode", None), "value", "")
                                or getattr(cfg, "mode", "")
                                or "scrumming"
                            ),
                            # The sim has no live state machine; a bot that
                            # is being ticked is RUNNING. Saying IDLE would
                            # colour every row grey and hide the one thing
                            # the column exists to show.
                            "state": "RUNNING" if bots else "IDLE",
                            "exchange": str(
                                getattr(cfg, "exchange_id", "") or "coinbase"
                            ),
                            "target_balance": float(
                                getattr(cfg, "target_balance", 0.0) or 0.0
                            ),
                            "live_target_balance": float(
                                getattr(bot, "_target_balance", 0.0) or 0.0
                            ),
                            "current_holdings": holdings,
                            "quote_to_usd": float(
                                getattr(bot, "_quote_to_usd", 1.0) or 1.0
                            ),
                            "stats": {
                                "current_price": px,
                                "position_value": holdings * px,
                            },
                        }
                    )
                except Exception as _ad_exc:  # noqa: BLE001
                    logger.debug("sim bot status skip: %s", _ad_exc)
            return out

        def _bot_status_table(self):
            """The Trading Tab's `BotStatusTable`, or None.

            v3.24.91 — DEFERRED IMPORT, and the reason matters.

            `main_window` imports `simulator_tab` (main_window.py:3971),
            so importing `main_window` at module scope from here would
            be a cycle. Importing it inside the method is safe because
            `SimulatorTab` is only ever CONSTRUCTED by `main_window`, so
            by the time this runs that module is fully loaded.

            Returns None rather than raising when it cannot be
            resolved -- a headless test importing this panel alone is a
            legitimate caller, and the fleet table falls back to its own
            columns.
            """
            cached = getattr(self, "_bst_cls", "unset")
            if cached != "unset":
                return cached
            cls = None
            try:
                from ...main_window import BotStatusTable as cls
            except Exception as _bst_exc:  # noqa: BLE001 - import guard
                logger.debug("BotStatusTable unavailable: %s", _bst_exc)
                cls = None
            self._bst_cls = cls
            return cls

        def _populate_fleet_table(self) -> None:
            self._fleet_table.setRowCount(len(self._configs))
            # v3.24.86 — gate rows are built by `GateStatusPanel` now.
            # `_gate_cells` stays as the fallback `_gate_cell_for`
            # consults when no panel is attached (headless tests, and
            # any future host that does not build one).
            self._gate_cells = {}
            _syms = []
            for r, cfg in enumerate(self._configs):
                sym = str(cfg.get("symbol", "") or "")
                target = float(cfg.get("target_balance", 0.0) or 0.0)
                self._fleet_table.setItem(r, 0, QTableWidgetItem(sym))
                self._fleet_table.setItem(r, 1, QTableWidgetItem(f"${target:,.2f}"))
                self._fleet_table.setItem(r, 2, QTableWidgetItem("0"))
                if sym:
                    _syms.append(sym)
            panel = getattr(self, "_gate_panel", None)
            if panel is not None:
                panel.set_symbols(_syms)
            # v3.24.91 — feed the Trading-Tab table when one is mounted.
            _bst = getattr(self, "_bot_status_table_widget", None)
            if _bst is not None:
                try:
                    _st = self.sim_bot_statuses()
                    _bst.update_bots(_st)
                except Exception as _bt_exc:  # noqa: BLE001
                    logger.debug("bot table update failed: %s", _bt_exc)

        # ── C26 (v3.24.58) — operator-visible failure reporting ──────

        def _status_error(self, msg: str) -> None:
            """The single funnel for every operator-visible failure.

            Exit-gate requirement: no failure path may leave the status
            line empty. An empty reason is indistinguishable from "the
            button did nothing", which is the complaint SN-31 records.
            """
            text = str(msg or "").strip()
            if not text:
                text = "Unspecified failure (no reason was recorded)."
            self._status_lbl.setText(text)
            logger.warning("[FleetReplay] %s", text)

        def _run_in_flight(self) -> bool:
            """True when a replay is live enough that Reset would
            discard work the operator is waiting on.

            v3.25.1 — THIS BLOCKED START.

            It read `not progress.finished` alone. A fresh
            `ReplayProgress` has `finished = False`, so a controller that
            has never run reported in flight. That was harmless while the
            controller was built by Start (line 1376) and `_controller`
            stayed None until then. Load now builds one too (line 550),
            so after Load the guard at `_on_start_clicked` saw
            `_controller is not None and _run_in_flight()` and refused
            with "A replay is already running." Load then Start was
            dead: measured `finished=False`, `candles_played=0`,
            `_run_in_flight()=True` on a fleet of 37 bots that had never
            ticked.

            The controller already owns the honest test — `self._task is
            not None and not self._task.done()` at
            `fleet_replay_controller.py:510`. Ask it first. Fall back to
            `started_at_wall`, which is 0.0 until the run actually starts
            (`fleet_replay_controller.py:554`), so "never started" stops
            reading as "running".

            Reset keeps its meaning: a live task is in flight, and so is
            a started run whose task reference is gone.
            """
            ctl = self._controller
            if ctl is None:
                return False
            try:
                task = getattr(ctl, "_task", None)
                if task is not None:
                    return not task.done()
                prog = ctl.progress
                if not float(getattr(prog, "started_at_wall", 0.0) or 0.0):
                    return False
                return not bool(getattr(prog, "finished", False))
            except Exception:  # R28-OK: unreadable progress -> assume in flight
                return True

        def _confirm_reset(self) -> bool:
            """Ask before discarding a running replay (SN-35).

            Overridden in tests so the state machine can be driven
            without opening a modal.
            """
            try:
                from PySide6.QtWidgets import QMessageBox

                reply = QMessageBox.question(
                    self,
                    "Reset replay",
                    "A replay is still running.\n\n"
                    "Reset will stop it and clear the fleet. Continue?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                return bool(reply == QMessageBox.Yes)
            except Exception as exc:  # R28-OK: no dialog -> do not destroy work
                logger.warning(
                    "reset confirmation unavailable (%s); refusing to "
                    "reset a running replay",
                    exc,
                )
                return False

        def _on_reset_clicked(self) -> None:
            # SN-35 — a long run must not be reset out from under the
            # operator. Only asks when something is actually running:
            # confirming every Reset trains them to click through it.
            if self._run_in_flight() and not self._confirm_reset():
                return

            _stop_failed = False
            if self._controller is not None:
                try:
                    self._controller.request_stop()
                except Exception as exc:  # was `except: pass`
                    # SN-31 — this swallow meant Reset could fail to
                    # stop the run and still look like it worked.
                    _stop_failed = True
                    self._status_error(
                        f"Reset: could not stop the running replay "
                        f"({type(exc).__name__}: {exc}). It may still be "
                        f"running — check the Simulator log."
                    )

            # ⚠️ ORDER IS LOAD-BEARING (C26).
            #
            # The timers are stopped HERE, before `_controller` is
            # nulled. They previously self-stopped via
            # `_refresh_progress`, which returns early when
            # `_controller is None` — so nulling first, as the cascade
            # plan literally prescribes, means that branch is never
            # reached and both timers run for the life of the process.
            # Pinned by test_the_timers_are_stopped_before_the_
            # controller_is_nulled.
            for _t in (
                getattr(self, "_progress_timer", None),
                getattr(self, "_drain_timer", None),
            ):
                if _t is not None:
                    try:
                        _t.stop()
                    except Exception as exc:  # R28-OK: reset must complete
                        logger.debug("timer stop failed on reset: %s", exc)

            self._controller = None
            self._gate_cells = {}
            self._configs = []
            self._fleet_table.setRowCount(0)
            self._start_btn.setEnabled(False)
            self._stop_btn.setEnabled(False)
            if not _stop_failed:
                # Don't overwrite the failure reason with a cheerful
                # "cleared" — that is how the swallow read on screen.
                self._status_lbl.setText("Fleet cleared — press Load live fleet.")
            self._progress_lbl.setText(
                "Replay idle — load a fleet + press Start Replay."
            )

        def _on_fetch_ytd_clicked(self) -> None:
            """v3.23.84 — CALL THE SAME FUNCTION HISTORY TAB CALLS.

            History Tab's Refresh dispatches
                fetch_all_history_chunked(bot_manager, since_ts)
            at src/gui/history_tab.py:454-461. Same pattern here.

            No custom enumeration. No exchange_id matching. No
            connector-picking. Nothing. If History Tab returns N
            trades, Fleet Replay returns the same N trades."""
            if self._async_loop_getter is None:
                self._status_lbl.setText("Cannot fetch: async loop not wired.")
                return
            loop = self._async_loop_getter()
            if loop is None:
                self._status_lbl.setText("Cannot fetch: async loop unavailable.")
                return
            if self._bot_manager is None:
                self._status_lbl.setText(
                    "Cannot fetch: bot_manager not wired "
                    "(same requirement History Tab has)."
                )
                return
            self._fetch_ytd_btn.setEnabled(False)
            self._status_lbl.setText(
                "Fetching YTD trades via history_helpers "
                "(same call History Tab uses)…"
            )

            from src.gui.history_helpers import (
                fetch_all_history_chunked,
                DEFAULT_START_DATE,
            )

            since_ts = DEFAULT_START_DATE.timestamp()
            bot_mgr = self._bot_manager

            async def _do_fetch():
                trades = await fetch_all_history_chunked(bot_mgr, since_ts)
                self._ytd_trades = list(trades or [])
                by_symbol: dict[str, int] = {}
                for t in self._ytd_trades:
                    s = str(t.get("symbol", ""))
                    if s:
                        by_symbol[s] = by_symbol.get(s, 0) + 1
                logger.info(
                    "Fleet Replay Fetch YTD via "
                    "fetch_all_history_chunked: %d trades across "
                    "%d symbols. %s",
                    len(self._ytd_trades),
                    len(by_symbol),
                    dict(sorted(by_symbol.items())),
                )

            # v3.23.85 — use future.add_done_callback so
            # _on_fetch_ytd_done fires AFTER the fetch actually
            # completes (not on a wall-clock timeout). Prior wall-clock 15s timer declared the
            # fetch done before fetch_all_history_chunked finished
            # (4040-trade walks take longer than 15s), so the panel
            # read an empty _ytd_trades and reported "no trades"
            # while the async fetch was still running in the
            # background. History Tab's dispatch uses Qt slots
            # bound to the future's completion — mirror that.
            try:
                future = asyncio.run_coroutine_threadsafe(_do_fetch(), loop)
            except Exception as _sched_exc:  # noqa: BLE001
                self._status_lbl.setText(f"Fetch schedule failed: {_sched_exc}")
                self._fetch_ytd_btn.setEnabled(True)
                return

            # Marshal from the asyncio thread back onto the Qt
            # main thread via QTimer.singleShot(0, ...) which is
            # the standard idiom.
            def _bounce_to_qt(_fut):
                QTimer.singleShot(0, self._on_fetch_ytd_done)

            future.add_done_callback(_bounce_to_qt)

        def _on_fetch_ytd_done(self) -> None:
            # v3.23.84 — status reports trade count + symbol
            # breakdown from fetch_all_history_chunked (same shape
            # History Tab uses).
            trades = self._ytd_trades
            if not trades:
                self._status_lbl.setText(
                    "Fetch YTD returned no trades. "
                    "(Same behaviour as History Tab under identical "
                    "conditions.) Check console log for details."
                )
            else:
                by_symbol: dict[str, int] = {}
                for t in trades:
                    s = str(t.get("symbol", ""))
                    if s:
                        by_symbol[s] = by_symbol.get(s, 0) + 1
                self._status_lbl.setText(
                    f"YTD trades fetched: {len(trades):,} across "
                    f"{len(by_symbol)} symbol(s)."
                )
            self._fetch_ytd_btn.setEnabled(True)

        def _live_trade_timestamps(self) -> list[float]:
            """Historical trade times for anchoring + soft-start.

            Prefers ``_ytd_trades`` (front-loaded by History Refresh
            or Fetch YTD). Falls back to reading the live trade log
            directly, because v3.24.15 silently degraded to full
            evaluation whenever the operator had not clicked Fetch
            YTD in the current session — the anchor set came back
            empty and nothing said why.
            """
            out: list[float] = []
            for t in self._ytd_trades or []:
                try:
                    ts = float(t.get("timestamp", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if ts > 0:
                    out.append(ts)
            if out:
                return out
            try:
                from datetime import datetime
                from src.trading.live_log_reader import live_trades

                for t in live_trades(validate=False):
                    try:
                        out.append(
                            datetime.fromisoformat(t.get("timestamp", "")).timestamp()
                        )
                    except (TypeError, ValueError):
                        continue
            except Exception as _lt_exc:  # noqa: BLE001
                logger.debug("live trade fallback unavailable: %s", _lt_exc)
            return out

        def _compute_soft_start(self):
            """Validation window from gate coverage, or None.

            Returns a ``ValidationWindow``. ``None`` means the cap
            could not be derived (no gate log, no paired trades), in
            which case the caller keeps the full YTD span rather than
            guessing at a narrower one.
            """
            from datetime import datetime
            from src.trading.gate_coverage import (
                classify_trades,
                compute_validation_window,
            )
            from src.trading.live_log_reader import live_gate_decisions, live_trades

            # v3.24.24 — build the trade list FIRST so the gate read can
            # be bounded by it.
            #
            # This used to be `gates = list(live_gate_decisions())`,
            # materialising the entire rotation chain before doing
            # anything: 165,062 rows across 250.7 MB of NDJSON on the
            # operator's disk, all held at once, synchronously on the Qt
            # thread. `live_gate_decisions` has always been a generator
            # and has always accepted `since` — nothing passed it.
            norm: list[dict] = []
            for t in live_trades(validate=False):
                d = t.get("data") or {}
                try:
                    ts = datetime.fromisoformat(t.get("timestamp", "")).timestamp()
                except (TypeError, ValueError):
                    continue
                norm.append(
                    {
                        "timestamp": ts,
                        "bot_id": t.get("bot_id", ""),
                        "symbol": d.get("symbol", ""),
                        "side": d.get("side", ""),
                    }
                )
            if not norm:
                return None

            # Cut off just before the earliest trade. Pairing only ever
            # looks within DEFAULT_TOLERANCE_S of a trade, and LOG_GAP
            # detection needs the entry immediately before the earliest
            # one, so a generous margin keeps classification identical
            # while still skipping everything older.
            from datetime import timedelta, timezone as _tz

            from src.trading.gate_coverage import (
                LOG_GAP_THRESHOLD_S as _GAP,
            )

            _floor = min(t["timestamp"] for t in norm)
            _since = datetime.fromtimestamp(_floor, tz=_tz.utc) - timedelta(
                seconds=_GAP * 2
            )

            # validate=False: _validate_gate_entry runs 9 field checks on
            # every row for a computation that reads four of them.
            cov = classify_trades(
                norm, live_gate_decisions(since=_since, validate=False)
            )
            if cov.gate_entry_count == 0:
                return None
            return compute_validation_window(cov, warmup_candles=100)

        def _on_start_clicked(self) -> None:
            # C26 / SN-14 — re-entrancy. Without this, a second click
            # builds a second FleetReplayController while the first
            # run's timers and `_gate_cells` still point at the old one,
            # orphaning them with nothing able to stop them.
            if self._controller is not None and self._run_in_flight():
                self._status_error(
                    "A replay is already running. Press Stop or wait "
                    "for it to finish before starting another."
                )
                return
            if not self._configs:
                # SN-31 — this was a bare `return`: Start did nothing
                # and explained nothing.
                self._status_error(
                    "Cannot start: no fleet loaded. Press " "'Load live fleet' first."
                )
                return
            # SN-29 — record whether this run is comparable to live
            # BEFORE the run's own status lines start arriving.
            self._note_parity_state()
            if self._async_loop_getter is None:
                self._status_lbl.setText(
                    "Cannot start: async loop not wired by MainWindow."
                )
                return
            loop = self._async_loop_getter()
            if loop is None:
                self._status_lbl.setText("Cannot start: async loop unavailable.")
                return
            from .fleet_replay_controller import FleetReplayController

            # v3.23.80 — prefer real YTD candles if the operator has
            # fetched them; fall back to synthetic sine waves so the
            # panel still runs when the sim is disconnected from an
            # exchange.
            # v3.24.1 — read candles from the Stone Tablets registry.
            # Prior cascade read from self._real_candles (populated by
            # the retired v3.23.80 OHLCV Fetch YTD path, empty since
            # v3.23.84 switched Fetch YTD to trade-based). Operator
            # directive 2026-08-01: "The Stone Tablet read should
            # dictate the candle count." Full tablet coverage is now
            # played (no more 200-candle cap).
            from src.trading.stone_tablets import get_registry
            from src.trading.stone_tablets.fetcher import YTD_START_MS

            reg = get_registry()
            symbols = sorted(
                {
                    str(c.get("symbol", "") or "")
                    for c in self._configs
                    if c.get("symbol")
                }
            )
            import time as _t

            now_ms = int(_t.time() * 1000)
            # YTD window math (verified 2026-08-01):
            #   YTD_START_MS = 2026-04-01T00:00Z
            #   now_ms      = today
            #   expected    = (now - YTD_START) / 5min == 288 * days
            _ytd_days = (now_ms - YTD_START_MS) / 86_400_000
            _expected_per_sym = int(_ytd_days * 288)
            candles: dict[str, list[list[float]]] = {}
            from_tablet: list[tuple[str, int, int]] = []  # sym,got,short
            skipped_no_tablet: list[str] = []
            # v3.24.3 W1 fix — route per-bot exchange_id instead of
            # hardcoding "coinbase". Today all 35 bots are Coinbase
            # (verified 2026-08-01), so the outcome is identical for
            # now — but hardcoding was a silent hallucination-vector
            # the moment multi-exchange lands.
            sym_to_exch = {}
            for cfg in self._configs:
                _s = str(cfg.get("symbol", "") or "")
                _e = str(cfg.get("exchange_id", "") or "coinbase")
                if _s:
                    sym_to_exch.setdefault(_s, _e)
            # v3.24.16 — apply the validation soft-start cap.
            #
            # Operator directive 2026-08-03: "the oldest trade with
            # all validation data in the trade gate log should emit a
            # soft start read date cap of which the user will be
            # informed via the simulation log."
            #
            # v3.24.15 built compute_validation_window() but never
            # called it, so the panel kept fetching from YTD_START_MS
            # and replayed 35,282 candles — including 10 weeks that
            # predate gate logging and can never be validated.
            _since_ms = YTD_START_MS
            self._validation_window = None
            try:
                _win = self._compute_soft_start()
                if _win is not None and _win.has_cap:
                    self._validation_window = _win
                    _since_ms = _win.replay_start_ms
            except Exception as _sw_exc:  # noqa: BLE001
                logger.warning(
                    "soft-start cap unavailable, using full YTD: %s", _sw_exc
                )

            for sym in symbols:
                asset = sym.split("/", 1)[0].upper() if "/" in sym else sym
                exch = sym_to_exch.get(sym, "coinbase")
                rows = reg.get_candles(
                    asset=asset,
                    since_ms=_since_ms,
                    until_ms=now_ms,
                    timeframe="5m",
                    exchange_id=exch,
                )
                if rows:
                    candles[sym] = list(rows)
                    _shortfall = max(0, _expected_per_sym - len(rows))
                    from_tablet.append((sym, len(rows), _shortfall))
                else:
                    # No tablet → skip. NO synthetic fallback.
                    skipped_no_tablet.append(sym)
            total_tablet_candles = sum(g for _, g, _ in from_tablet)
            total_shortfall = sum(s for _, _, s in from_tablet)
            logger.info(
                "Fleet Replay Start (v3.24.1b): %d symbol(s) with "
                "tablet (total %d candles), %d skipped (no tablet)%s",
                len(from_tablet),
                total_tablet_candles,
                len(skipped_no_tablet),
                (f" [{', '.join(skipped_no_tablet)}]" if skipped_no_tablet else ""),
            )
            # v3.24.99 - GUARDED, like the other three bindings.
            #
            # `_activity_log_cb` defaults to None (line 170) and
            # `set_log_callbacks` has ONE caller, behind a hasattr
            # guard at simulator_tab.py:249. Any path that builds
            # this panel without that call raised TypeError on
            # Start Replay, which calls `_act` seven times.
            #
            # The same file already guards it at lines 535, 546
            # and 1322; one binding of four was bare. pyright
            # reported all seven call sites and no archetype ran
            # pyright on this file until today.
            _act = self._activity_log_cb or (
                lambda m: logger.info("[FleetReplay] %s", m)
            )
            if _act is not None:
                _act(
                    f"YTD window: {_ytd_days:.1f} days · expected "
                    f"~{_expected_per_sym:,} candles per symbol "
                    "(122 days × 288 5m candles)."
                )
                _act(
                    f"Stone Tablets: {len(from_tablet)} symbol(s) "
                    f"loaded · {total_tablet_candles:,} YTD candles "
                    f"total · {total_shortfall:,} candle shortfall "
                    "(gap between YTD expected and what tablets "
                    "actually cover)."
                )
                # Per-symbol shortfall table so operator can see which
                # tablets are current vs which are stale. Ordered by
                # shortfall descending.
                _sorted = sorted(from_tablet, key=lambda t: t[2], reverse=True)
                for sym, got, short in _sorted[:10]:
                    pct = 100.0 * got / _expected_per_sym if _expected_per_sym else 0.0
                    _act(
                        f"  {sym:<10} {got:>6,} / {_expected_per_sym:>6,} "
                        f"= {pct:5.1f}%  short {short:>6,}"
                    )
                if len(_sorted) > 10:
                    _act(
                        f"  ... and {len(_sorted) - 10} more "
                        "(check console log for full list)"
                    )
                if skipped_no_tablet:
                    _act(
                        f"Skipped {len(skipped_no_tablet)} symbol(s) "
                        "with no tablet (bot not instantiated): "
                        f"{', '.join(skipped_no_tablet)}"
                    )
                    _act(
                        "Fix: run the Fetch YTD build (v3.24.x GUI "
                        "button) or CLI `python -m "
                        "src.trading.stone_tablets.fetcher build-ytd`."
                    )
                # v3.24.6 — per-tablet availability notices per
                # operator directive 2026-08-01: 'This asset was
                # listed on Coinbase mm/dd/yyyy and no prior data
                # exists.' Emits only when status != full so the
                # log stays quiet for the majority. Reads
                # AvailabilityInfo + WindowStatus from the registry.
                try:
                    from src.trading.stone_tablets import (
                        WindowStatus,
                        get_registry as _reg,
                    )

                    _r = _reg()
                    _notices: list[str] = []
                    for sym, _got, _short in from_tablet:
                        _asset = sym.split("/", 1)[0].upper() if "/" in sym else sym
                        _eid = sym_to_exch.get(sym, "coinbase")
                        _st = _r.check_window_availability(
                            _asset, YTD_START_MS, now_ms, exchange_id=_eid
                        )
                        if _st == WindowStatus.FULL:
                            continue
                        _info = _r.get_asset_availability(_asset, exchange_id=_eid)
                        if _info is None:
                            continue
                        _notices.append(f"  [{_st}] {_info.listing_notice()}")
                    if _notices:
                        _act(
                            f"Availability flags ({len(_notices)} "
                            "symbol(s) not fully covering the "
                            "requested YTD window):"
                        )
                        for line in _notices[:20]:
                            _act(line)
                        if len(_notices) > 20:
                            _act(
                                f"  ... and {len(_notices) - 20} "
                                "more (see console log)"
                            )
                except Exception as _av_exc:  # noqa: BLE001
                    logger.debug("availability notice emit failed: %s", _av_exc)
            if not candles:
                self._status_lbl.setText(
                    "Cannot start: no Stone Tablets available for "
                    "any loaded bot. Run Fetch YTD first."
                )
                if _activity_cb := (self._activity_log_cb or None):
                    _activity_cb(
                        "Cannot start: no bots have Stone Tablets. " "Aborting."
                    )
                return
            # v3.24.1 — route callbacks to the real Simulator tab
            # widgets (scaffolding fix #1). Prior default was
            # logger.info, so on-screen Activity/Performance panels
            # could not display anything the controller emitted.
            _activity_cb = self._activity_log_cb or (
                lambda m: logger.info("[FleetReplay] %s", m)
            )
            _perf_cb = self._performance_log_cb or (
                lambda m: logger.info("[FleetReplay perf] %s", m)
            )
            self._controller = FleetReplayController(
                configs=self._configs,
                candles_by_symbol=candles,
                activity_log_cb=_activity_cb,
                performance_log_cb=_perf_cb,
                tick_delay_s=0.0,
                # v3.24.1 — no cap. Full tablet coverage plays.
                # Operator can hit Stop at any time.
                max_candles=None,
                # v3.24.72 (C20) — cross-bot compounding. Without
                # these the replay runs with Smart Wires inert and
                # its accumulation curve understates live's.
                smart_wires=self._smart_wires,
            )

            # v3.24.15 — anchored read head (default). Evaluate only
            # candles carrying a historical trade, each preceded by a
            # warm-up window so indicators are valid at the moment we
            # check them. "Full evaluation" opts out for strategy work.
            # v3.24.16 — report the soft-start cap. Operator asked to
            # be informed of it via the simulation log; v3.24.15
            # computed it and told no one.
            _win = getattr(self, "_validation_window", None)
            if _win is not None:
                try:
                    from src.trading.gate_coverage import format_window_lines

                    _full_n = int((now_ms - YTD_START_MS) // 300_000)
                    _scoped_n = max((len(r) for r in candles.values()), default=0)
                    for _ln in format_window_lines(_win, _full_n, _scoped_n):
                        _act(_ln)
                except Exception as _fw_exc:  # noqa: BLE001
                    logger.debug("window report failed: %s", _fw_exc)
            else:
                _act(
                    "Validation window: no gate data found — replaying "
                    "the full YTD span (nothing can be validated "
                    "against, so this is a strategy run, not parity)."
                )

            _full_eval = bool(self._full_eval_chk.isChecked())
            self._controller.progress.anchored = not _full_eval
            # v3.24.29 — compute the expected-trade index set in BOTH
            # modes. It drives chart marker colour (green = this fill
            # landed where a historical trade exists). In full
            # evaluation it is NOT used for skipping; without it every
            # marker in an FE run would paint red for want of a
            # reference set.
            try:
                from .fleet_replay_controller import (
                    build_anchor_indices as _bai,
                    clock_timestamps_from_candles as _cts,
                )

                _b0 = min(int(rows[0][0]) for rows in candles.values() if rows)
                # v3.24.70 (C20 / NF-18) — the master clock's union IS
                # the index space the run loop's cursor walks. Deriving
                # it here rather than reading progress.total_candles,
                # which is still 0 at this point: `start()` assigns it
                # AFTER `_build_sim()`, and this runs before start is
                # even scheduled. The `or max(len(...))` fallback below
                # therefore fired on EVERY run, bounding anchors by the
                # longest single series instead of the union.
                _clock = _cts(candles)
                _nn = len(_clock) or (
                    self._controller.progress.total_candles
                    or max(len(r) for r in candles.values())
                )
                self._controller._expected_indices = _bai(
                    self._live_trade_timestamps(),
                    base_ts_ms=_b0,
                    n_candles=_nn,
                    warmup=0,
                    clock_ts_ms=_clock,
                )
            except Exception as _exp_exc:  # noqa: BLE001
                logger.debug("expected-index build failed: %s", _exp_exc)
            if _full_eval:
                _act(
                    "Evaluation mode: FULL — every candle. Slower; "
                    "required for strategy work and the only mode "
                    "that detects sim-only trades."
                )
            else:
                try:
                    from .fleet_replay_controller import (
                        build_anchor_indices,
                        clock_timestamps_from_candles as _cts_a,
                    )

                    _base_ts = min(int(rows[0][0]) for rows in candles.values() if rows)
                    # v3.24.70 (C20 / NF-18) — see the note on the
                    # expected-index call above. Same union, same
                    # reason.
                    _clock_a = _cts_a(candles)
                    _n = len(_clock_a) or (
                        self._controller.progress.total_candles
                        or max(len(r) for r in candles.values())
                    )
                    # v3.24.16 — resilient source. Was reading only
                    # _ytd_trades, which is empty unless Fetch YTD
                    # ran this session, so anchoring silently fell
                    # back to full evaluation.
                    _trade_ts = self._live_trade_timestamps()
                    _anchors = build_anchor_indices(
                        _trade_ts,
                        base_ts_ms=_base_ts,
                        n_candles=_n,
                        warmup=100,
                        clock_ts_ms=_clock_a,
                    )
                    if _anchors:
                        self._controller._anchor_indices = _anchors
                        _pct = 100.0 * len(_anchors) / max(_n, 1)
                        _act(
                            f"Evaluation mode: ANCHORED — "
                            f"{len(_anchors):,} of {_n:,} candles "
                            f"({_pct:.1f}%) carry a historical trade "
                            "or its 100-candle warm-up; the rest are "
                            "skipped."
                        )
                        _act(
                            "  Note: bots are not evaluated on skipped "
                            "candles, so sim-only divergence is not "
                            "reliably measured in this mode. (The "
                            "exchange still steps, so a resting limit "
                            "CAN fill on a skipped candle.) Tick 'Full "
                            "evaluation' for strategy runs."
                        )
                    else:
                        _act(
                            "Evaluation mode: FULL (fallback) — no "
                            "historical trades landed inside the "
                            "candle window, so there is nothing to "
                            "anchor on."
                        )
                        self._controller.progress.anchored = False
                except Exception as _anc_exc:  # noqa: BLE001
                    logger.warning("anchor build failed, using full eval: %s", _anc_exc)
                    self._controller.progress.anchored = False
                    _act(
                        f"Evaluation mode: FULL (anchor build failed: "
                        f"{type(_anc_exc).__name__})"
                    )
            # v3.24.3 — prime the visual widgets with the fleet's
            # symbols so they can pre-allocate rows/bands, then wire
            # the visual-refresh callback so the controller pings us
            # every 100 ticks.
            _sim_syms = sorted(candles.keys())
            if self._sim_price_chart is not None:
                self._sim_price_chart.clear_data()
                self._sim_price_chart.set_symbols(_sim_syms)
                # v3.24.89 - where the YTD overlay begins.
                #
                # `compute_validation_window` walks BACK from the oldest
                # trade that has a gate decision by `warmup_candles`, so
                # `replay_start_ms` is the start of the WARM-UP, not of
                # validatable history. The overlay marks the latter:
                # shading the warm-up would claim gate coverage for
                # candles that predate any gate decision.
                # UNITS. `gate_first_ts` and `trade_ts` are SECONDS --
                # `compute_validation_window` converts with
                # `soft_start_ms = int(oldest * 1000)`. Candles are int
                # MILLISECONDS. Passing the seconds value straight
                # through makes every candle satisfy `ts >= ytd_from`
                # (1.78e12 >= 1.78e9) and shades the whole warm-up,
                # which is the precise claim this overlay must not make.
                _win = getattr(self, "_validation_window", None)
                if _win is not None:
                    _ytd0 = getattr(_win, "soft_start_ms", None)
                    if _ytd0:
                        for _s in _sim_syms:
                            self._sim_price_chart.set_ytd_start(_s, int(_ytd0))
                # v3.24.89 - repopulate the chart's bot picker.
                #
                # The picker lives on the Simulator tab and the roster
                # is known here, at fleet load. Without this it stays
                # on "All (bands)" with nothing to choose, and the
                # focused candle view is unreachable.
                _tab = self.window()
                _refresh = getattr(_tab, "refresh_chart_bot_roster", None)
                if _refresh is None:
                    _p = self.parent()
                    while _p is not None and _refresh is None:
                        _refresh = getattr(_p, "refresh_chart_bot_roster", None)
                        _p = _p.parent()
                if _refresh is not None:
                    try:
                        _refresh(_sim_syms)
                    except Exception as _rr:  # noqa: BLE001 - advisory
                        logger.debug("chart roster refresh failed: %s", _rr)
            if self._sim_voting_readout is not None:
                # v3.24.81 — the REAL IndicatorVotingPanel's contract.
                # `set_bots` belonged to the sim-only summary table this
                # replaced. `update_bot_list` filters on mode, so the
                # entries must declare "scrumming" or they are dropped
                # and the selector stays empty — which is what an empty
                # panel looks like.
                self._sim_voting_readout.update_bot_list(
                    [{"bot_id": s, "symbol": s, "mode": "scrumming"} for s in _sim_syms]
                )
            self._controller.set_visual_refresh_cb(
                # v3.24.14 — 100 -> 15. Operator directive
                # 2026-08-03: "Line generation should be a live
                # animation as the relevant sections of the Stone
                # Tablets play." At the measured ~12.5 candles/s a
                # 100-candle cadence redrew once every 8 seconds,
                # which reads as a stalled chart that occasionally
                # jumps. 15 gives roughly one repaint per second —
                # continuous to the eye without flooding the event
                # loop (repaint is batched across all symbols).
                self._on_visual_refresh_tick,
                every_n_candles=15,
            )
            try:
                asyncio.run_coroutine_threadsafe(self._controller.start(), loop)
            except Exception as _sched_exc:  # noqa: BLE001
                self._status_lbl.setText(f"Schedule failed: {_sched_exc}")
                return
            self._start_btn.setEnabled(False)
            self._stop_btn.setEnabled(True)
            self._progress_lbl.setText("Replay starting…")
            self.replayStarted.emit()
            # Progress-poll timer
            if self._progress_timer is None:
                self._progress_timer = QTimer(self)
                self._progress_timer.setInterval(500)
                self._progress_timer.timeout.connect(self._refresh_progress)
            self._progress_timer.start()
            # v3.24.19 — snapshot drain on the Qt MAIN thread at a
            # fixed wall-clock cadence. Paint cost can no longer feed
            # back into replay throughput: the worker only ever writes
            # a dict, and this timer decides how often the widgets
            # actually repaint. 250 ms = 4 Hz, fast enough to read as
            # live, slow enough that 35 gate cells + 35 chart bands +
            # 35 table rows never dominate the frame.
            if self._drain_timer is None:
                self._drain_timer = QTimer(self)
                self._drain_timer.setInterval(250)
                self._drain_timer.timeout.connect(self._drain_visual_snapshot)
            self._drain_timer.start()

        def _collect_stat_fields(self, bots: list, exchange) -> dict:
            """v3.24.19 — worker-thread half of the stat strip feed:
            pure arithmetic over bot + exchange state, returning
            formatted strings. Touches no Qt. ``_apply_stat_fields``
            pushes the result on the Qt main thread.

            Telemetry (v3.24.8) proved ``SimStatStrip.set()`` had
            ZERO call sites anywhere in the source tree, which is
            why every operator screenshot showed dashes across the
            whole strip. v3.24.9 added the feed; v3.24.19 split it
            across the thread boundary.

            Field semantics (sim-scoped, mirrors the live header):
                Spendable — quote-currency cash left in the sim wallet
                Realised  — sum of bot.stats.realised_pnl
                Locked    — capital currently held as positions
                Mature    — accumulated_fold across bots
                Exch      — count of distinct exchanges (sim: 1)
                Scrummed  — sum of stats.total_scrummed_usd
                Folded    — sum of stats.total_folded_usd
                Trades    — sim trades executed by the fake exchange
                Bots      — instantiated sim bots
                Errors    — tick exceptions recorded by the controller
            """
            try:
                spendable = 0.0
                if exchange is not None:
                    bal = getattr(exchange, "_balances", {}) or {}
                    for cur in ("USD", "USDC"):
                        spendable += float(bal.get(cur, 0.0) or 0.0)
                realised = 0.0
                locked = 0.0
                mature = 0.0
                scrummed = 0.0
                folded = 0.0
                for b in bots:
                    st = getattr(b, "stats", None)
                    if st is not None:
                        realised += float(getattr(st, "realised_pnl", 0.0) or 0.0)
                        mature += float(getattr(st, "accumulated_fold", 0.0) or 0.0)
                        scrummed += float(getattr(st, "total_scrummed_usd", 0.0) or 0.0)
                        folded += float(getattr(st, "total_folded_usd", 0.0) or 0.0)
                    holdings = float(getattr(b, "_current_holdings", 0.0) or 0.0)
                    price = float(getattr(b, "_last_price", 0.0) or 0.0)
                    locked += holdings * price
                trades = 0
                if exchange is not None:
                    trades = len(getattr(exchange, "_trades", []) or [])
                errors = int(
                    getattr(
                        getattr(self._controller, "progress", None), "exceptions", 0
                    )
                    or 0
                )
                return {
                    "Spendable": f"${spendable:,.2f}",
                    "Realised": f"${realised:,.2f}",
                    "Locked": f"${locked:,.2f}",
                    "Mature": f"${mature:,.2f}",
                    "Exch": "1",
                    "Scrummed": f"${scrummed:,.2f}",
                    "Folded": f"${folded:,.2f}",
                    "Trades": f"{trades:,}",
                    "Bots": f"{len(bots)}",
                    "Errors": f"{errors:,}",
                }
            except Exception as _ss_exc:  # noqa: BLE001
                _tel_exc("sim.stat_strip.feed", _ss_exc)
                return {}

        def _apply_stat_fields(self, fields: dict) -> None:
            """v3.24.19 — Qt-main-thread half: push formatted strings
            into the strip."""
            strip = self._sim_stat_strip
            if strip is None:
                _tel_skip("sim.stat_strip.feed", "no strip widget")
                return
            try:
                for name, value in fields.items():
                    strip.set(name, value)
                _tel_call("sim.stat_strip.feed")
            except Exception as _ap_exc:  # noqa: BLE001
                _tel_exc("sim.stat_strip.feed", _ap_exc)
                logger.debug("stat strip feed raised: %s", _ap_exc)

        def _on_visual_refresh_tick(self, candle_i: int) -> None:
            """v3.24.19 — PRODUCER. Runs on the asyncio worker thread.

            Builds a plain-Python snapshot of sim state and stores it.
            Touches NO Qt objects. ``_drain_visual_snapshot`` consumes
            it on the Qt main thread via a QTimer.

            Why this changed
            ----------------
            Until v3.24.19 this method called widget setters
            (``update_gates``, ``append_tick``, ``update_bot_row``,
            ``chart.update()``) directly from the worker thread, on
            the strength of a docstring claiming "Qt marshals via
            signal/slot for setter calls on paint widgets". That is
            false — direct method calls are not marshalled, so this
            was cross-thread widget access, which Qt does not define.

            Measured cost, from the operator's own persisted run logs
            (~/.acervator_logs/sim/runs/*/meta.json), same 35 bots and
            same machine on 2026-08-03/04:

                GUI-launched   :  1.42 / 1.52 / 5.47 candles/s
                harness-launched: 58.6 / 58.9 / 82.2 / 101.1 / 105.8

            At matched trade density (17.7 vs 19.2 trades per 1000
            candles) the gap is still 19x, so it is not explained by
            the GUI runs simply doing more trading.

            Decoupling makes replay throughput independent of GUI
            cost by construction, rather than relying on the paint
            path being cheap enough.
            """
            del candle_i  # cadence-only; content is read live
            if self._controller is None:
                return
            try:
                snap = self._collect_visual_snapshot()
            except Exception as _snap_exc:  # noqa: BLE001
                # A dropped frame must not kill the replay, but it must
                # not be invisible either. Debug-only logging here would
                # hide a total feed failure behind "the lights just
                # aren't moving" — route it to telemetry so the zero-call
                # report names it.
                _tel_exc("sim.visual_snapshot.collect", _snap_exc)
                logger.warning("visual snapshot failed: %s", _snap_exc)
                return
            with self._snapshot_lock:
                # Keep only the newest: if the GUI cannot keep up we
                # drop intermediate frames rather than queueing them.
                # A stale frame has no value here — the operator wants
                # current state, not a backlog.
                self._pending_snapshot = snap

        def _collect_visual_snapshot(self) -> dict:
            """Worker-thread read of sim state into plain data.

            No Qt calls. Safe to run off the GUI thread because the
            worker owns the bots and the sim exchange.
            """
            ctl = self._controller
            exchange = getattr(ctl, "_exchange", None)
            bots = list(getattr(ctl, "_bots", []) or [])
            per_symbol: dict = {}
            for bot in bots:
                try:
                    sym = getattr(getattr(bot, "config", None), "symbol", "") or ""
                    if not sym:
                        continue
                    gs = getattr(bot, "_last_gate_state", None) or {}
                    _sfx = gs.get("scrum_fixture") or {}
                    _ffx = gs.get("fold_fixture") or {}
                    entry: dict = {
                        "has_gate_state": bool(gs),
                        "scrum_armed": bool(gs.get("scrum_armed")),
                        "fold_armed": bool(gs.get("fold_armed")),
                        "scrum_blockers": list(gs.get("scrum_blockers") or []),
                        "fold_blockers": list(gs.get("fold_blockers") or []),
                        "landing_strip_side": str(
                            _sfx.get("landing_strip_side")
                            or _ffx.get("landing_strip_side")
                            or ""
                        ),
                        # v3.24.88 - OHLC, not just the close.
                        #
                        # The chart drew a close-only polyline because
                        # a close is all it was ever given. Stone Tablet
                        # candle playback (operator task 2026-08-08,
                        # screenshot area 4) needs the whole bar, and
                        # the tape has always had it.
                        "ts": None,
                        "open": None,
                        "high": None,
                        "low": None,
                        "close": None,
                        "volume": None,
                        "summary": getattr(bot, "_last_summary", None),
                    }
                    # v3.24.88 - READ THE TAPE, NOT `exchange._series`.
                    #
                    # REGRESSION REPAIRED. This read
                    # `exchange._series[sym].get_current()`. When the
                    # Simulator moved onto `CCXTConnector` +
                    # `TabletBackend`, `_series` stopped existing on
                    # either object, so `getattr(..., {})` returned an
                    # empty dict, `close` stayed None, and the chart
                    # silently drew nothing on every refresh. Nothing
                    # raised; the only trace was a
                    # `sim.price_chart.append` telemetry SKIP, which
                    # counts skips without an expectation to compare
                    # them against. That is precisely the failure the
                    # emitter below now makes impossible to miss.
                    _tape = getattr(ctl, "_tape", None)
                    # 10.4 - THE CHART FEED'S EXPECTATION, TAKEN ON THE
                    # THREAD THAT OWNS THE TAPE. `has_data` is the
                    # tape's own answer to "can this symbol supply a
                    # candle at the current master clock", and it is
                    # asked through a DIFFERENT call from the one that
                    # supplies the candle. It is read here, in the
                    # worker, for the same reason every other field is:
                    # the GUI thread does not own the tape.
                    _has_data = getattr(_tape, "has_data", None)
                    entry["tape_has_data"] = (
                        bool(_has_data(sym)) if callable(_has_data) else False
                    )
                    if _tape is not None and hasattr(_tape, "history"):
                        try:
                            _rows = _tape.history(sym, 1)
                        except Exception:  # noqa: BLE001 - tape may be idle
                            _rows = []
                        if _rows:
                            _r = _rows[-1]
                            entry["ts"] = int(_r[0])
                            entry["open"] = float(_r[1])
                            entry["high"] = float(_r[2])
                            entry["low"] = float(_r[3])
                            entry["close"] = float(_r[4])
                            entry["volume"] = float(_r[5])
                    elif exchange is not None:
                        # Legacy path, kept for any host still handing
                        # in a series-shaped exchange.
                        series = getattr(exchange, "_series", {}).get(sym)
                        # 10.4 - the expectation follows whichever
                        # source fed this entry. Without this a legacy
                        # host reports `tape_has_data` False for every
                        # symbol, so `expected` is 0 against a non-zero
                        # `actual` and the pin fails a healthy run -
                        # the exact shape this repair removes.
                        entry["tape_has_data"] = series is not None
                        cur = series.get_current() if series is not None else None
                        if cur and len(cur) >= 6:
                            entry["ts"] = int(cur[0])
                            entry["open"] = float(cur[1])
                            entry["high"] = float(cur[2])
                            entry["low"] = float(cur[3])
                            entry["close"] = float(cur[4])
                            entry["volume"] = float(cur[5])
                    per_symbol[sym] = entry
                except Exception as _b_exc:  # noqa: BLE001
                    logger.debug(
                        "snapshot per-bot skip (%s): %s",
                        getattr(bot, "bot_id", "?"),
                        _b_exc,
                    )
            _marks = []
            try:
                _marks = ctl.drain_markers()
            except Exception as _mk_exc:  # noqa: BLE001
                logger.debug("marker drain failed: %s", _mk_exc)
            return {
                "per_symbol": per_symbol,
                "trade_markers": _marks,
                "stat_fields": self._collect_stat_fields(bots, exchange),
            }

        def _drain_visual_snapshot(self) -> None:
            """v3.24.19 — CONSUMER. Runs on the Qt main thread.

            Applies the most recent worker snapshot to the widgets at
            a fixed wall-clock cadence, so paint cost can never feed
            back into replay throughput.
            """
            with self._snapshot_lock:
                snap = self._pending_snapshot
                self._pending_snapshot = None
            if not snap:
                return
            fields = snap.get("stat_fields") or {}
            if fields:
                self._apply_stat_fields(fields)
            # v3.24.60 (C29 / SN-15) — trade markers used to be applied
            # HERE, before the per-symbol loop below appends this
            # tick's candle. `mark_trade` pins the candle at the end of
            # the series, so marking first pinned the PREVIOUS drain's
            # candle — every marker, every time, off by one. The block
            # now runs after the appends; see below.
            # v3.24.86 - GATE RENDER ACCOUNTING.
            #
            # Step 4 of the emitter-first workflow, added BEFORE the
            # display moved out of the fleet table. Only
            # `feature_telemetry` watched this path; it counts calls and
            # skips and carries no expected-vs-actual, so "every bot
            # with gate state still gets a rendered row" was not a
            # checkable claim -- a migration that silently rendered
            # FEWER rows would look identical to one that worked.
            for sym, e in (snap.get("per_symbol") or {}).items():
                try:
                    cell = self._gate_cell_for(sym)
                    if cell is None:
                        _tel_skip("sim.gate_lights.update", "no cell for symbol")
                    elif not e.get("has_gate_state"):
                        _tel_skip(
                            "sim.gate_lights.update", "bot has no _last_gate_state"
                        )
                    else:
                        cell.update_gates(
                            scrum_armed=e["scrum_armed"],
                            fold_armed=e["fold_armed"],
                            scrum_blockers=e["scrum_blockers"],
                            fold_blockers=e["fold_blockers"],
                            landing_strip_side=e["landing_strip_side"],
                        )
                        _tel_call("sim.gate_lights.update")
                    if self._sim_price_chart is None:
                        _tel_skip("sim.price_chart.append", "chart widget absent")
                    elif e.get("close") is None:
                        _tel_skip("sim.price_chart.append", "no candle at cursor")
                    else:
                        # v3.24.89 - the whole bar, for candle
                        # playback. OHLC is optional on the signature,
                        # so a close-only caller still works.
                        self._sim_price_chart.append_tick(
                            sym,
                            close_price=e["close"],
                            volume=e["volume"] or 0.0,
                            ts=e.get("ts"),
                            open_price=e.get("open"),
                            high=e.get("high"),
                            low=e.get("low"),
                        )
                        _tel_call("sim.price_chart.append")
                    if self._sim_voting_readout is None:
                        _tel_skip("sim.voting_readout.update", "readout widget absent")
                    elif e.get("summary") is None:
                        _tel_skip(
                            "sim.voting_readout.update", "bot has no _last_summary"
                        )
                    else:
                        # v3.24.81 — feed the SAME shape the Trading
                        # Tab feeds (indicator_panel.py:958-973), built
                        # from the bot's own VotingSummary. One panel,
                        # one contract, so the two tabs cannot drift.
                        _sm = e["summary"]
                        _tf = str(getattr(_sm, "timeframe", "") or "5m")
                        self._sim_voting_readout.update_data(
                            {
                                _tf: {
                                    "bullish": _sm.bullish_count,
                                    "bearish": _sm.bearish_count,
                                    "neutral": _sm.neutral_count,
                                    "net_score": _sm.net_score,
                                    "confidence": _sm.consensus_confidence,
                                    "direction": _sm.consensus_direction.name,
                                    "signals": [
                                        {
                                            "indicator": _s.indicator,
                                            "direction": _s.direction.name,
                                            "confidence": _s.confidence,
                                            "details": {},
                                        }
                                        for _s in _sm.signals
                                    ],
                                    "locks": [],
                                }
                            },
                            sym,
                        )
                        _tel_call("sim.voting_readout.update")
                except Exception as _d_exc:  # noqa: BLE001
                    logger.debug("snapshot drain skip (%s): %s", sym, _d_exc)
            # v3.24.60 (C29 / SN-15) — markers AFTER the appends above.
            # `mark_trade` pins the candle currently at the end of the
            # series, so this must follow the tick it belongs to.
            _chart = self._sim_price_chart
            if _chart is not None:
                for _sym, _ok in snap.get("trade_markers") or []:
                    try:
                        _chart.mark_trade(_sym, _ok)
                    except Exception as _mm_exc:  # noqa: BLE001
                        logger.debug("mark_trade(%s) failed: %s", _sym, _mm_exc)
            if self._sim_price_chart is not None:
                self._sim_price_chart.update()

        def _on_stop_clicked(self) -> None:
            if self._controller is not None:
                try:
                    self._controller.request_stop()
                except Exception as exc:
                    # C26 / SN-31 — this was `except: pass`. The
                    # operator pressed Stop, the request was swallowed,
                    # and nothing on screen changed.
                    self._status_error(
                        f"Stop: the replay did not accept the stop "
                        f"request ({type(exc).__name__}: {exc}). It may "
                        f"still be running."
                    )
            self._stop_btn.setEnabled(False)

        def _note_parity_state(self) -> None:
            """Say so when the run cannot be compared to live (SN-29).

            `_ytd_trades` being empty is the NORMAL condition, and the
            panel said nothing about it — so a synthetic run looked
            exactly like a parity run on screen.
            """
            if self._ytd_trades:
                self._status_lbl.setText(
                    f"Parity active: {len(self._ytd_trades)} live YTD "
                    f"trade(s) loaded for comparison."
                )
            else:
                self._status_lbl.setText(
                    "Parity check SKIPPED — no live YTD trades loaded. "
                    "This run is synthetic and is NOT comparable to "
                    "live. Press Fetch YTD first if you want parity."
                )

        def _refresh_progress(self) -> None:
            if self._controller is None:
                return
            p = self._controller.progress
            # v3.23.80 — surface exception diagnostics. When every
            # tick fails the operator needs to see WHY, not just the
            # count. Show up to 3 distinct exception signatures with
            # their occurrence counts.
            # v3.24.14 — rate + ETA. A 35,282-candle replay runs ~47
            # minutes at the measured ~12.5 candles/s; with only a
            # raw counter on screen that is indistinguishable from a
            # hang, and the operator reasonably read it as frozen.
            # Rate is computed over the whole run so far (not an
            # instantaneous sample) so it stays readable rather than
            # flickering between refreshes.
            _rate = 0.0
            _eta_txt = ""
            try:
                import time as _t

                _el = _t.time() - float(p.started_at_wall or 0.0)
                if _el > 0 and p.candles_played > 0:
                    _rate = p.candles_played / _el
                    _left = max(0, p.total_candles - p.candles_played)
                    if _rate > 0 and _left > 0:
                        _secs = _left / _rate
                        if _secs >= 3600:
                            _eta_txt = f"  ·  ETA {_secs / 3600:.1f} h"
                        elif _secs >= 60:
                            _eta_txt = f"  ·  ETA {_secs / 60:.0f} min"
                        else:
                            _eta_txt = f"  ·  ETA {_secs:.0f} s"
            except (TypeError, ValueError, ZeroDivisionError) as _eta_exc:
                logger.debug("progress ETA maths skipped: %s", _eta_exc)
            _pct = (
                100.0 * p.candles_played / p.total_candles if p.total_candles else 0.0
            )
            base = (
                f"Replay: {p.candles_played:,}/{p.total_candles:,} "
                f"candles ({_pct:.1f}%)  ·  {p.trades_fired} sim "
                f"trades  ·  {p.exceptions} exceptions"
                + (f"  ·  {_rate:.1f} candles/s" if _rate else "")
                + _eta_txt
            )
            if p.exception_samples:
                top = sorted(
                    p.exception_samples.items(), key=lambda kv: kv[1], reverse=True
                )[:3]
                exc_str = "  |  ".join(f"{key} ×{count}" for key, count in top)
                base += f"\n{exc_str}"
            self._progress_lbl.setText(base)
            # v3.24.0 — actually update the per-row Sim Trades
            # column. Prior refresh only touched the aggregate
            # label; the column existed but was dead scaffolding
            # per operator directive 2026-08-01: "It supposedly
            # did 60 trades over 200 candles but none of the bot
            # trade counters incremented. More scaffolding..."
            counts = getattr(p, "per_symbol_trade_count", {}) or {}
            try:
                from PySide6.QtWidgets import QTableWidgetItem

                for r in range(self._fleet_table.rowCount()):
                    sym_item = self._fleet_table.item(r, 0)
                    if sym_item is None:
                        continue
                    sym = sym_item.text()
                    n = int(counts.get(sym, 0))
                    cur_item = self._fleet_table.item(r, 2)
                    if cur_item is None or cur_item.text() != str(n):
                        self._fleet_table.setItem(r, 2, QTableWidgetItem(str(n)))
            except Exception as _tc_exc:  # noqa: BLE001 - GUI paint best-effort
                logger.debug("Sim Trades column refresh failed: %s", _tc_exc)
            if p.finished:
                if self._progress_timer:
                    self._progress_timer.stop()
                # v3.24.19 — drain once more before stopping, so the
                # final frame lands. Without this the visuals freeze
                # on whatever the second-to-last tick produced.
                self._drain_visual_snapshot()
                if self._drain_timer:
                    self._drain_timer.stop()
                self._start_btn.setEnabled(True)
                self._stop_btn.setEnabled(False)
                # v3.24.9 — run the parity comparison. Telemetry
                # (v3.24.8) proved compare_trades() had ZERO callers:
                # 12 green pin tests, never invoked. This is the
                # "does sim reproduce live?" measurement the whole
                # harness exists for.
                self._run_parity_comparison()
                self.replayStopped.emit()

        def _run_parity_comparison(self) -> None:
            """v3.24.9 — compare sim trades to the live YTD trades
            already fetched into ``self._ytd_trades``, then dump the
            report to the Performance Log.

            Sim trades carry master-clock timestamps (v3.24.5 fix),
            so the ±tolerance match against live trade timestamps is
            meaningful. Before that fix every sim trade was stamped
            with wall-clock 'now' and parity was unmeasurable."""
            perf = self._performance_log_cb
            if self._controller is None:
                _tel_skip("sim.parity.compare_trades", "no controller")
                return
            exchange = getattr(self._controller, "_exchange", None)
            sim_trades = list(getattr(exchange, "_trades", []) or [])
            live_trades = list(self._ytd_trades or [])
            if not live_trades:
                _tel_skip(
                    "sim.parity.compare_trades", "no live trades loaded (run Fetch YTD)"
                )
                if perf:
                    perf(
                        "Parity: skipped — no live trades loaded. "
                        "Run Fetch YTD before Start Replay to "
                        "measure sim-vs-live reproduction."
                    )
                return
            if not sim_trades:
                _tel_skip("sim.parity.compare_trades", "sim produced no trades")
                if perf:
                    perf(
                        f"Parity: sim produced 0 trades against "
                        f"{len(live_trades):,} live trades — "
                        "0% reproduction."
                    )
                return
            try:
                from src.trading.stone_tablets.parity_harness import (
                    compare_trades,
                    format_report_lines,
                )

                report = compare_trades(live_trades, sim_trades)
                _tel_call("sim.parity.compare_trades")
                if perf:
                    for line in format_report_lines(report):
                        perf(line)
            except Exception as _pc_exc:  # noqa: BLE001
                _tel_exc("sim.parity.compare_trades", _pc_exc)
                logger.debug("parity comparison raised: %s", _pc_exc)
                if perf:
                    perf(
                        f"Parity comparison failed: "
                        f"{type(_pc_exc).__name__}: {_pc_exc}"
                    )

        def get_loaded_configs(self) -> list[dict]:
            return list(self._configs)


__all__ = ["_synthesize_candles_for_symbol"]
if _HAS_QT:
    __all__.append("FleetReplayPanel")
