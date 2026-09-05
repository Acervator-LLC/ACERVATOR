"""fleet_replay_panel.py -- the Simulator's Fleet Replay panel.

Loads every live bot config from bot_state.json and spawns one
simulated ScrummingBot per config, then plays Stone Tablet candles
through them. The loaded fleet is a table of one row per bot, and a
progress row reports candles played, trades fired and tick failures.
"""

from __future__ import annotations

import asyncio
import logging
import math
import threading
import time
from typing import Any, Callable, Optional

from ...color_alpha import rgba

logger = logging.getLogger("acervator.simulator.fleet.panel")

HEADER_BORDER_COLOR = "#00cccc"
HEADER_BORDER_ALPHA = 68


# Advisory: a telemetry failure never breaks the feature it watches.


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
    # Per-symbol seed, so one symbol always draws the same wave.
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

        Load reads the stored fleet into a table of one row per bot and
        spawns a sim bot for each. Start Replay hands the run to the
        application's loop; two timers then poll it, one for the progress
        row and one for the visual refresh.

        Emits ``fleetLoaded(list)`` on Load, ``replayStarted()`` /
        ``replayStopped()`` for external listeners.
        """

        fleetLoaded = Signal(list)
        replayStarted = Signal()
        replayStopped = Signal()

        # Three columns. The gate row lives in GateStatusPanel, not here.
        COLUMNS = ("Symbol", "Target USD", "Sim Trades")

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            self.setAccessibleName("Fleet Replay Panel")
            self._gate_host_kind = "panel"
            self._gate_panel = None
            try:
                from .sim_visuals import GateStatusPanel as _gsp

                # Parented here. Built with no parent it is a top-level
                # window, and enough leaked ones segfault Qt (exit 139).
                self._gate_panel = _gsp(self)
            except Exception as _gsp_exc:  # noqa: BLE001 - GUI import guard
                logger.debug("GateStatusPanel unavailable: %s", _gsp_exc)
                self._gate_host_kind = "table"
            self._configs: list[dict] = []
            # bot_state's top-level smart_wires, loaded beside the configs.
            self._smart_wires: list[dict] = []
            self._controller = None
            self._progress_timer: Optional[QTimer] = None
            self._async_loop_getter = None
            # Load and Fetch YTD are independent: neither reads the other's
            # state.
            self._bot_manager = None
            # SimulatorTab calls set_log_callbacks after mount; until then the
            # lines reach the console logger, which no panel reads.
            self._activity_log_cb: Optional[Callable[[str], None]] = None
            self._performance_log_cb: Optional[Callable[[str], None]] = None
            # The replay worker writes a snapshot here; a timer on the Qt
            # thread drains it. An undrained frame is replaced, not queued.
            self._snapshot_lock = threading.Lock()
            self._pending_snapshot: Optional[dict] = None
            self._drain_timer: Optional[QTimer] = None
            self._sim_stat_strip = None
            # Wired by SimulatorTab after mount, so the panel builds without them.
            self._sim_price_chart = None
            self._sim_voting_readout = None
            # bot_id -> GateLightsCell, indexed at Load time.
            self._gate_cells: dict[str, Any] = {}
            self._ytd_trades: list[dict] = []
            self._real_candles: dict[str, list[list[float]]] = {}

            outer = QVBoxLayout(self)
            outer.setContentsMargins(10, 10, 10, 10)
            outer.setSpacing(10)

            header = QFrame()
            header.setStyleSheet(
                "QFrame{background:rgba(0,255,204,10);"
                f"border:1px solid {rgba(HEADER_BORDER_COLOR, HEADER_BORDER_ALPHA)};"
                "border-radius:6px;}"
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

            load_row = QHBoxLayout()
            self._load_btn = QPushButton("Load live fleet")
            self._load_btn.setToolTip(
                "Read ~/.acervator/bot_state.json and load every "
                "Scrumming bot config as a fresh sim instance."
            )
            self._load_btn.clicked.connect(self._on_load_clicked)
            load_row.addWidget(self._load_btn)
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

            # Unchecked: only candles carrying a historical trade, each with a
            # warm-up. Checked: every candle, the only mode finding sim-only trades.
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

            self._progress_lbl = QLabel(
                "Replay idle — load a fleet + press Start Replay."
            )
            self._progress_lbl.setStyleSheet(
                "color:#7fb3ff; font-size:11px; padding:2px 6px;"
            )
            self._progress_lbl.setWordWrap(True)
            outer.addWidget(self._progress_lbl)

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
            """Wire the Indicator Voting Panel widgets so per-tick updates
            land in them. Called by SimulatorTab after both this panel and
            the visuals are constructed. Without ``stat_strip`` the ten-field
            header has nothing to feed."""
            self._sim_price_chart = price_chart
            self._sim_voting_readout = voting_readout
            self._sim_stat_strip = stat_strip

        def set_log_callbacks(
            self,
            activity_cb: Optional[Callable[[str], None]],
            performance_cb: Optional[Callable[[str], None]],
        ) -> None:
            """Wire the on-screen Activity and Performance log widgets so the
            fleet replay controller's messages reach the operator. With no
            callback the lines reach the console logger, which no on-screen
            panel reads."""
            self._activity_log_cb = activity_cb
            self._performance_log_cb = performance_cb

        def set_bot_manager(self, bot_manager) -> None:
            """Wire the bot manager Fetch YTD passes to
            ``fetch_all_history_chunked``, the same call the History tab's
            Refresh makes."""
            self._bot_manager = bot_manager
            self._fetch_ytd_btn.setEnabled(bot_manager is not None)

        def set_connectors_getter(self, getter) -> None:
            """Accept and drop a connectors getter.

            Retained so a MainWindow that only knows this API still boots.
            Fetch YTD reads no connector.
            """
            del getter

        def on_history_refreshed(self, trades) -> None:
            """Receive the History tab's ``history_refreshed`` signal.

            The payload is a ``list[dict]`` in the same shape Fetch YTD
            produces, so Start Replay can use it without a Fetch YTD click of
            its own.
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

        def _on_load_clicked(self) -> None:
            try:
                from src.simulator.fleet.bot_state_loader import (
                    load_bot_configs_from_state,
                    load_smart_wires_from_state,
                    summarize_loaded_configs,
                )

                self._configs = load_bot_configs_from_state()
                # The wires join the configs on `_src_bot_id`; without them
                # cross-bot compounding is inert.
                self._smart_wires = load_smart_wires_from_state()
                summary = summarize_loaded_configs(self._configs)
            except Exception as exc:  # noqa: BLE001 - loader surface
                logger.exception("FleetReplayPanel load failed: %s", exc)
                self._status_lbl.setText(f"Load failed: {type(exc).__name__}: {exc}")
                return
            self._populate_fleet_table()
            # Load builds the controller and calls `_build_sim`, so every row
            # is backed by a constructed sim bot with a `simulated_` id.
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
            try:
                self.fleetLoaded.emit(list(self._configs))
            except Exception:  # noqa: S110 - signal best-effort
                pass

        def _spawn_sim_fleet(self) -> int:
            """Construct a real sim bot for every loaded config.

            Returns the number spawned. Reads the Stone Tablet registry
            through the same call Start Replay uses, rather than adding a
            second candle path.

            The controller is built but NOT started: the bots exist, hold
            their imported state and can be inspected, and the tape only
            advances when the operator presses Start Replay.
            """
            if not self._configs:
                return 0

            # The two imports sit outside the timed span: sys.modules serves
            # them after the first call, so the first spawn would look slow.
            from src.trading.stone_tablets.registry import get_registry
            from src.simulator.fleet.fleet_replay_controller import (
                FleetReplayController,
            )

            _dur_t0 = time.monotonic()
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
                # Named, not dropped: a bot with no tablet cannot be simulated.
                _log_missing = self._activity_log_cb or (
                    lambda m: logger.info("[FleetReplay] %s", m)
                )
                _log_missing(
                    f"No Stone Tablet for {len(missing)} symbol(s): "
                    f"{', '.join(missing[:8])}" + (" ..." if len(missing) > 8 else "")
                )
            if not candles:
                return 0

            # The same callback resolution Start Replay uses.
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
            # Stop the clock before the count and the emitter, so neither is
            # billed to the spawn.
            _dur_elapsed = time.monotonic() - _dur_t0
            n = len(list(getattr(self._controller, "_bots", []) or []))
            try:
                from src.core.signal_contract import emit as _sp_emit

                _sp_emit(
                    "sim.06.007.postcondition.fleet_spawned",
                    actual=n,
                    expected=len(self._configs),
                    duration=_dur_elapsed,
                    context={
                        "symbols_with_tablet": len(candles),
                        "missing_tablets": len(missing),
                    },
                )
            except Exception:  # noqa: BLE001,S110 - advisory
                pass
            _act_cb(
                f"Spawned {n} simulated bot(s) from bot_state "
                f"({len(candles)} symbol(s) with tablets)."
            )

            # Written beside bot_state, never into it. The parity diff is
            # canonical JSON, so lot CONTENTS count rather than lot counts.
            try:
                from src.simulator.fleet.simulator_bot_state import (
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
                # `save_sim_state` clobbers the file on every Load, so this is the
                # only moment the previous document exists.
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
                try:
                    from src.core.signal_contract import emit as _sbs_emit

                    _sbs_emit(
                        "sim.06.008.invariant.state_persisted",
                        actual=len(_parity) - len(_bad),
                        expected=len(_parity),
                        context={
                            "path": "simulator_bot_state.json",
                            "mismatched": sorted(_bad)[:8],
                        },
                    )
                    # Expected 0: a repeat Load with the live fleet at rest
                    # reproduces the same sources.
                    _sbs_emit(
                        "sim.06.009.invariant.spawn_drift",
                        actual=len(_drift["changed"]),
                        expected=0,
                        context={
                            "first_spawn": _drift["first_spawn"],
                            "added": _drift["added"][:8],
                            "removed": _drift["removed"][:8],
                            "changed": _drift["changed"][:8],
                            "unchanged": _drift["unchanged"],
                        },
                    )
                except Exception:  # noqa: BLE001,S110 - advisory
                    pass
            except Exception as _sbs_exc:  # noqa: BLE001
                logger.exception("simulator_bot_state persist failed: %s", _sbs_exc)
                _act_cb(f"simulator_bot_state FAILED: {_sbs_exc}")
            return n

        def _gate_cell_for(self, symbol: str):
            """The gate row widget for *symbol*, wherever it lives.

            ``_gate_panel`` wins when present; the table cells are the
            fallback when no panel is attached.
            """
            panel = getattr(self, "_gate_panel", None)
            if panel is not None:
                return panel.cell_for(symbol)
            return self._gate_cells.get(symbol)

        def sim_bot_statuses(self) -> list:
            """The fleet as ``BotStatusTable.update_bots()`` status dicts.

            An ADAPTER, not a second table. ``BotStatusTable`` already draws
            these columns with their header dots, state colouring and Ammo
            arithmetic, so the sim gets the Trading tab's bot area because it
            IS the Trading tab's bot area.

            The contract, read off ``update_bots``:
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
                            # A bot being ticked is RUNNING. IDLE would grey
                            # every row and hide what the column exists to show.
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

        def emit_bot_table(self, rendered: int) -> None:
            """Report what the bot area actually drew.

            `expected` is the number of sim bots, `actual` the number of
            rows rendered. A redesign that quietly drops rows -- an
            adapter raising on one bot, say -- would otherwise look
            exactly like one that works.
            """
            try:
                from src.core.signal_contract import emit as _bt_emit

                ctl = getattr(self, "_controller", None)
                _bt_emit(
                    "sim.06.010.postcondition.bot_table.rendered",
                    actual=int(rendered),
                    expected=len(list(getattr(ctl, "_bots", []) or [])),
                    every=2.0,
                    context={
                        "columns": len(getattr(self, "_bot_table_columns", []) or [])
                    },
                )
            except Exception:  # noqa: BLE001,S110 - advisory
                pass

        def _bot_status_table(self):
            """The Trading tab's ``BotStatusTable``, or None.

            Deferred import. ``main_window`` imports ``simulator_tab``, so
            importing ``main_window`` at module scope from here would be a
            cycle. Inside the method it is safe: ``SimulatorTab`` is only ever
            constructed by ``main_window``, so that module is fully loaded by
            the time this runs.

            Returns None rather than raising when it cannot be resolved, so a
            test importing this panel alone is a legitimate caller and the
            fleet table falls back to its own columns.
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
            # Gate rows are built by `GateStatusPanel`; `_gate_cells` is the
            # fallback when no panel is attached.
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
            # Feed the Trading tab's table when one is mounted.
            _bst = getattr(self, "_bot_status_table_widget", None)
            if _bst is not None:
                try:
                    _st = self.sim_bot_statuses()
                    _bst.update_bots(_st)
                    self.emit_bot_table(len(_st))
                except Exception as _bt_exc:  # noqa: BLE001
                    logger.debug("bot table update failed: %s", _bt_exc)

        def _status_error(self, msg: str) -> None:
            """The single funnel for every operator-visible failure.

            No failure path may leave the status line empty: an empty reason
            reads on screen as "the button did nothing".
            """
            text = str(msg or "").strip()
            if not text:
                text = "Unspecified failure (no reason was recorded)."
            self._status_lbl.setText(text)
            logger.warning("[FleetReplay] %s", text)

        def _run_in_flight(self) -> bool:
            """True when a replay is live enough that Reset would discard
            work the operator is waiting on.

            Asks the controller first: a live task is in flight. Falls back to
            ``started_at_wall``, which is 0.0 until the run actually starts, so
            "never started" does not read as "running". Reading
            ``progress.finished`` alone reported a controller that had never
            run as in flight, which refused Start after a Load.

            A controller that cannot be read is treated as running, so Reset
            never throws away a run it could not measure.
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
            except Exception:  # unreadable progress reads as still in flight
                return True

        def _confirm_reset(self) -> bool:
            """Ask before discarding a running replay.

            Overridden in tests so the state machine can be driven without
            opening a modal.
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
            except Exception as exc:  # no dialog means the work is kept
                logger.warning(
                    "reset confirmation unavailable (%s); refusing to "
                    "reset a running replay",
                    exc,
                )
                return False

        def _on_reset_clicked(self) -> None:
            # Only asks when something is running: confirming every Reset
            # trains the operator to click through it.
            if self._run_in_flight() and not self._confirm_reset():
                return

            _stop_failed = False
            if self._controller is not None:
                try:
                    self._controller.request_stop()
                except Exception as exc:  # was `except: pass`
                    # A swallowed stop let Reset fail and still look like it worked.
                    _stop_failed = True
                    self._status_error(
                        f"Reset: could not stop the running replay "
                        f"({type(exc).__name__}: {exc}). It may still be "
                        f"running — check the Simulator log."
                    )

            # Stop the timers BEFORE nulling `_controller`. `_refresh_progress`
            # returns early on a None controller, so nulling first never stops them.
            for _t in (
                getattr(self, "_progress_timer", None),
                getattr(self, "_drain_timer", None),
            ):
                if _t is not None:
                    try:
                        _t.stop()
                    except Exception as exc:  # the reset still completes
                        logger.debug("timer stop failed on reset: %s", exc)

            self._controller = None
            self._gate_cells = {}
            self._configs = []
            self._fleet_table.setRowCount(0)
            self._start_btn.setEnabled(False)
            self._stop_btn.setEnabled(False)
            if not _stop_failed:
                # Do not overwrite the failure reason with "cleared".
                self._status_lbl.setText("Fleet cleared — press Load live fleet.")
            self._progress_lbl.setText(
                "Replay idle — load a fleet + press Start Replay."
            )

        def _on_fetch_ytd_clicked(self) -> None:
            """Call the same function the History tab calls.

            The History tab's Refresh dispatches
            ``fetch_all_history_chunked(bot_manager, since_ts)``. No custom
            enumeration, no exchange matching, no connector picking: if the
            History tab returns N trades, Fleet Replay returns the same N.
            """
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

            from src.exchange.history_helpers import (
                fetch_all_history_chunked,
                DEFAULT_START_DATE,
            )

            since_ts = DEFAULT_START_DATE.timestamp()
            bot_mgr = self._bot_manager

            async def _do_fetch():
                # The span holds the awaited venue walk alone. Measured: a
                # 4040-trade walk takes over 15 s, the slowest call this panel makes.
                _fetch_t0 = time.monotonic()
                trades = await fetch_all_history_chunked(bot_mgr, since_ts)
                _fetch_s = time.monotonic() - _fetch_t0
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

                # The YTD trades are the reference dataset: an expectation derived
                # from live cannot be quietly rewritten to match a sim bug.
                try:
                    from src.core.signal_contract import emit as _emit

                    _fleet_syms = {
                        str(c.get("symbol", "") or "")
                        for c in (self._configs or [])
                        if c.get("symbol")
                    }
                    _emit(
                        "ytd.10.001.gauge.trades_fetched",
                        actual=len(self._ytd_trades),
                        context={"since_ts": since_ts, "symbols": len(by_symbol)},
                    )
                    # A fleet symbol with no YTD trade has no live reference.
                    _covered = sorted(set(by_symbol) & _fleet_syms)
                    _emit(
                        "ytd.10.002.postcondition.fleet_symbol_coverage",
                        actual=_covered,
                        expected=sorted(_fleet_syms),
                        context={"uncovered": sorted(_fleet_syms - set(by_symbol))},
                        duration=_fetch_s,
                    )
                    _emit(
                        "ytd.10.003.gauge.per_symbol_counts",
                        actual=dict(sorted(by_symbol.items())),
                    )
                except Exception as _emx:  # noqa: BLE001 - never break the fetch
                    logger.debug("ytd emit failed: %s", _emx)

            # add_done_callback fires when the fetch really finishes. A
            # wall-clock timer declared it done early, on an empty `_ytd_trades`.
            try:
                future = asyncio.run_coroutine_threadsafe(_do_fetch(), loop)
            except Exception as _sched_exc:  # noqa: BLE001
                self._status_lbl.setText(f"Fetch schedule failed: {_sched_exc}")
                self._fetch_ytd_btn.setEnabled(True)
                return

            # Marshal from the asyncio thread back onto the Qt thread.
            def _bounce_to_qt(_fut):
                QTimer.singleShot(0, self._on_fetch_ytd_done)

            future.add_done_callback(_bounce_to_qt)

        def _on_fetch_ytd_done(self) -> None:
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
            """Historical trade times for anchoring and soft-start.

            Prefers ``_ytd_trades``, front-loaded by a History refresh or by
            Fetch YTD. Falls back to reading the live trade log directly:
            without that fallback the anchor set came back empty whenever
            Fetch YTD had not run this session, and nothing said why.
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

            # Build the trade list first so the gate read is bounded by it.
            # Measured unbounded: 165,062 rows across 250.7 MB, on the Qt thread.
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

            # Cut off just before the earliest trade. Pairing looks within
            # DEFAULT_TOLERANCE_S, and LOG_GAP needs the entry before it.
            from datetime import timedelta, timezone as _tz

            from src.trading.gate_coverage import (
                LOG_GAP_THRESHOLD_S as _GAP,
            )

            _floor = min(t["timestamp"] for t in norm)
            _since = datetime.fromtimestamp(_floor, tz=_tz.utc) - timedelta(
                seconds=_GAP * 2
            )

            # validate=False: the validator runs 9 field checks for a
            # computation that reads four of them.
            cov = classify_trades(
                norm, live_gate_decisions(since=_since, validate=False)
            )
            if cov.gate_entry_count == 0:
                return None
            return compute_validation_window(cov, warmup_candles=100)

        def _on_start_clicked(self) -> None:
            # Without this a second click builds a second controller while the
            # first run's timers still point at the old one.
            if self._controller is not None and self._run_in_flight():
                self._status_error(
                    "A replay is already running. Press Stop or wait "
                    "for it to finish before starting another."
                )
                return
            if not self._configs:
                self._status_error(
                    "Cannot start: no fleet loaded. Press " "'Load live fleet' first."
                )
                return
            # Record whether this run is comparable to live before the run's
            # own status lines arrive.
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
            from src.simulator.fleet.fleet_replay_controller import (
                FleetReplayController,
            )

            # Candles come from the Stone Tablets registry. Full tablet
            # coverage plays; there is no candle cap.
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
            # expected per symbol = (now - YTD_START) / 5 min == 288 * days
            _ytd_days = (now_ms - YTD_START_MS) / 86_400_000
            _expected_per_sym = int(_ytd_days * 288)
            candles: dict[str, list[list[float]]] = {}
            from_tablet: list[tuple[str, int, int]] = []  # sym,got,short
            skipped_no_tablet: list[str] = []
            # Route the per-bot exchange_id rather than hardcoding one venue.
            sym_to_exch = {}
            for cfg in self._configs:
                _s = str(cfg.get("symbol", "") or "")
                _e = str(cfg.get("exchange_id", "") or "coinbase")
                if _s:
                    sym_to_exch.setdefault(_s, _e)
            # Cap the read at the validation soft start, so weeks that predate
            # gate logging are not replayed.
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
            # `_activity_log_cb` defaults to None and `set_log_callbacks` has
            # one caller, so an unwired panel raised TypeError on Start Replay.
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
                # Per-symbol shortfall, worst first, so a stale tablet is visible.
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
                # Emits only when a tablet does not fully cover the window, so the
                # log stays quiet for the majority.
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
                # No cap. Full tablet coverage plays; Stop ends it.
                max_candles=None,
                # Without the wires the replay runs with cross-bot compounding inert.
                smart_wires=self._smart_wires,
            )

            # Anchored by default: only candles carrying a historical trade,
            # each preceded by a warm-up window.
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
            # Built in both modes: it drives marker colour, not skipping.
            # Without it every marker in a full run paints red.
            try:
                from src.simulator.fleet.fleet_replay_controller import (
                    build_anchor_indices as _bai,
                    clock_timestamps_from_candles as _cts,
                )

                _b0 = min(int(rows[0][0]) for rows in candles.values() if rows)
                # The master clock's union is the index space the run loop walks.
                # `progress.total_candles` is still 0 here, so the fallback fired.
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
                    from src.simulator.fleet.fleet_replay_controller import (
                        build_anchor_indices,
                        clock_timestamps_from_candles as _cts_a,
                    )

                    _base_ts = min(int(rows[0][0]) for rows in candles.values() if rows)
                    # Same union as the expected-index call above.
                    _clock_a = _cts_a(candles)
                    _n = len(_clock_a) or (
                        self._controller.progress.total_candles
                        or max(len(r) for r in candles.values())
                    )
                    # Reading only `_ytd_trades` made anchoring fall back to full
                    # evaluation whenever Fetch YTD had not run this session.
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
            # Install a sink before the fleet load: the four loader emitters
            # fire inside `load_bot_configs_from_state`, before a controller.
            try:
                from src.core.signal_contract import (
                    SignalSink as _SS,
                    get_sink as _gs,
                    set_sink as _ss,
                )

                if _gs() is None:
                    _ss(_SS())
            except Exception as _sx:  # noqa: BLE001 - advisory
                logger.debug("load-time sink install failed: %s", _sx)
            _sim_syms = sorted(candles.keys())
            if self._sim_price_chart is not None:
                self._sim_price_chart.clear_data()
                self._sim_price_chart.set_symbols(_sim_syms)
                # The overlay marks validatable history, not the warm-up.
                # `soft_start_ms` is milliseconds; the two trade times are seconds.
                _win = getattr(self, "_validation_window", None)
                if _win is not None:
                    _ytd0 = getattr(_win, "soft_start_ms", None)
                    if _ytd0:
                        for _s in _sim_syms:
                            self._sim_price_chart.set_ytd_start(_s, int(_ytd0))
                # The picker lives on the Simulator tab and the roster is known
                # here, at fleet load.
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
                # `update_bot_list` filters on mode, so an entry must declare
                # "scrumming" or it is dropped and the selector stays empty.
                self._sim_voting_readout.update_bot_list(
                    [{"bot_id": s, "symbol": s, "mode": "scrumming"} for s in _sim_syms]
                )
            self._controller.set_visual_refresh_cb(
                # 15 candles is about one repaint per second at the measured
                # 12.5 candles/s. 100 redrew once every 8 s, which reads as stalled.
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
            if self._progress_timer is None:
                self._progress_timer = QTimer(self)
                self._progress_timer.setInterval(500)
                self._progress_timer.timeout.connect(self._refresh_progress)
            self._progress_timer.start()
            # 250 ms drain on the Qt thread, so paint cost cannot feed back
            # into replay throughput.
            if self._drain_timer is None:
                self._drain_timer = QTimer(self)
                self._drain_timer.setInterval(250)
                self._drain_timer.timeout.connect(self._drain_visual_snapshot)
            self._drain_timer.start()

        def _collect_stat_fields(self, bots: list, ledger) -> dict:
            """The worker-thread half of the stat strip feed.

            Pure arithmetic over bot and ledger state, returning formatted
            strings. Touches no Qt. ``_apply_stat_fields`` pushes the result
            on the Qt main thread.

            ``ledger`` IS THE TAPE, not ``ctl._exchange``. The exchange is a
            ``CCXTConnector`` and carries neither ``_balances`` nor
            ``_trades``, so reading it made both ``getattr`` defaults fire and
            the strip reported Spendable $0.00 and Trades 0 on a replay
            holding $99.40 and one filled trade. ``TabletBackend.snapshot()``
            answers both questions in one call, so a tape that cannot answer
            raises rather than defaulting to a zero.

            Field semantics, sim-scoped, mirroring the live header:
                Spendable - quote-currency cash left in the sim wallet
                Realised  - sum of bot.stats.realised_pnl
                Locked    - capital currently held as positions
                Mature    - accumulated_fold across bots
                Exch      - count of distinct exchanges (sim: 1)
                Scrummed  - sum of stats.total_scrummed_usd
                Folded    - sum of stats.total_folded_usd
                Trades    - sim trades executed by the fake exchange
                Bots      - instantiated sim bots
                Errors    - tick exceptions recorded by the controller
            """
            try:
                snap = ledger.snapshot() if ledger is not None else {}
                spendable = 0.0
                bal = snap.get("balances") or {}
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
                trades = int(snap.get("trades", 0) or 0)
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
            """The Qt-main-thread half: push formatted strings into the strip."""
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
            """The producer half, running on the asyncio worker thread.

            Builds a plain-Python snapshot of sim state and stores it. Touches
            NO Qt objects. ``_drain_visual_snapshot`` consumes it on the Qt
            main thread through a QTimer.

            This method used to call widget setters straight from the worker
            thread, which is cross-thread widget access and undefined in Qt.
            Measured on the operator's own run logs, same 35 bots and same
            machine:

                GUI-launched    :  1.42 / 1.52 / 5.47 candles/s
                harness-launched: 58.6 / 58.9 / 82.2 / 101.1 / 105.8

            At matched trade density (17.7 against 19.2 trades per 1000
            candles) the gap is still 19x, so it is not explained by the GUI
            runs simply trading more. Decoupling makes replay throughput
            independent of paint cost by construction.
            """
            del candle_i  # cadence-only; content is read live
            if self._controller is None:
                return
            try:
                snap = self._collect_visual_snapshot()
            except Exception as _snap_exc:  # noqa: BLE001
                _tel_exc("sim.visual_snapshot.collect", _snap_exc)
                logger.warning("visual snapshot failed: %s", _snap_exc)
                return
            with self._snapshot_lock:
                # Keep only the newest frame. A stale frame has no value.
                self._pending_snapshot = snap

        def _collect_visual_snapshot(self) -> dict:
            """Worker-thread read of sim state into plain data.

            No Qt calls. Safe to run off the GUI thread because the
            worker owns the bots and the sim exchange.
            """
            ctl = self._controller
            exchange = getattr(ctl, "_exchange", None)
            # The ledger is the tape, a different object from the connector the
            # bots trade through. `exchange` stays for the legacy branch below.
            ledger = getattr(ctl, "_tape", None)
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
                        # The whole bar, not just the close: candle playback
                        # needs it and the tape has always had it.
                        "ts": None,
                        "open": None,
                        "high": None,
                        "low": None,
                        "close": None,
                        "volume": None,
                        "summary": getattr(bot, "_last_summary", None),
                    }
                    # Read the tape. `exchange._series` stopped existing when the
                    # Simulator moved onto `CCXTConnector`, and nothing raised.
                    _tape = getattr(ctl, "_tape", None)
                    # `has_data` is the tape's own answer to whether this symbol can
                    # supply a candle now, through a different call from the supplier.
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
                        # The expectation follows whichever source fed this
                        # entry, or a legacy host reports 0 against a non-zero actual.
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
                "stat_fields": self._collect_stat_fields(bots, ledger),
            }

        def _drain_visual_snapshot(self) -> None:
            """The consumer half, running on the Qt main thread.

            Applies the most recent worker snapshot to the widgets at a fixed
            wall-clock cadence, so paint cost can never feed back into replay
            throughput.
            """
            with self._snapshot_lock:
                snap = self._pending_snapshot
                self._pending_snapshot = None
            if not snap:
                return
            fields = snap.get("stat_fields") or {}
            if fields:
                self._apply_stat_fields(fields)
            # `expected` is the number of bots reporting gate state, `actual`
            # the number of rows painted, so a dropped row reports ok=False.
            _gate_expected = sum(
                1
                for _e in (snap.get("per_symbol") or {}).values()
                if _e.get("has_gate_state")
            )
            _gate_actual = 0
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
                        _gate_actual += 1
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
                        # OHLC is optional, so a close-only caller still works.
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
                        # The same shape the Trading tab feeds its voting
                        # panel, so the two cannot drift.
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
            # `expected` is the tape's own `has_data` count, not `len(per_symbol)`:
            # a bot whose tablet starts after the master clock has no candle to give.
            try:
                from src.core.signal_contract import emit as _pc_emit

                _pc_per = snap.get("per_symbol") or {}
                _pc_fed = sum(
                    1 for _e in _pc_per.values() if _e.get("close") is not None
                )
                _pc_emit(
                    "sim.06.011.postcondition.price_chart.fed",
                    actual=_pc_fed,
                    expected=sum(
                        1 for _e in _pc_per.values() if _e.get("tape_has_data")
                    ),
                    context={
                        "symbols": len(_pc_per),
                        "with_ohlc": sum(
                            1 for _e in _pc_per.values() if _e.get("open") is not None
                        ),
                    },
                )
            except Exception:  # noqa: BLE001,S110 - instrumentation is advisory
                pass

            try:
                from src.core.signal_contract import emit as _gs_emit

                _gs_emit(
                    "sim.06.012.postcondition.gate_status.rendered",
                    actual=_gate_actual,
                    expected=_gate_expected,
                    context={"host": getattr(self, "_gate_host_kind", "table")},
                )
            except Exception:  # noqa: BLE001,S110 - instrumentation is advisory
                pass

            # `mark_trade` pins the candle at the end of the series, so this
            # must follow the tick it belongs to.
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
                    self._status_error(
                        f"Stop: the replay did not accept the stop "
                        f"request ({type(exc).__name__}: {exc}). It may "
                        f"still be running."
                    )
            self._stop_btn.setEnabled(False)

        def _note_parity_state(self) -> None:
            """Say so when the run cannot be compared to live.

            ``_ytd_trades`` being empty is the NORMAL condition, and the panel
            said nothing about it, so a synthetic run looked exactly like a
            parity run on screen.
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
            # Up to 3 exception signatures with their counts. Rate is over the
            # whole run, so it stays readable rather than flickering.
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
                # Drain once more before stopping, so the final frame lands.
                self._drain_visual_snapshot()
                if self._drain_timer:
                    self._drain_timer.stop()
                self._start_btn.setEnabled(True)
                self._stop_btn.setEnabled(False)
                # The sim-against-live measurement the harness exists for.
                self._run_parity_comparison()
                self.replayStopped.emit()

        def _run_parity_comparison(self) -> None:
            """Compare sim trades with the live YTD trades already fetched
            into ``self._ytd_trades``, then write the report to the
            Performance log.

            Sim trades carry master-clock timestamps, so the tolerance match
            against live trade times is meaningful. Before that they were
            stamped with wall-clock now and parity was unmeasurable.

            THE TAPE, NOT THE CONNECTOR. Reading ``_exchange._trades`` made
            ``sim_trades`` empty on every run, so this always took the
            "sim produced 0 trades" branch. ``fetch_my_trades()`` returns
            copies as DICTS stamped in MILLISECONDS, which is the shape and
            the unit ``compare_trades`` reads.
            """
            perf = self._performance_log_cb
            if self._controller is None:
                _tel_skip("sim.parity.compare_trades", "no controller")
                return
            tape = getattr(self._controller, "tape", None)
            sim_trades = list(tape.fetch_my_trades()) if tape is not None else []
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
