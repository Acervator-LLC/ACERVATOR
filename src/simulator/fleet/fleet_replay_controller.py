"""Async orchestrator for Fleet Replay: feeds YTD candle data through the
exchange the bots hold while ticking each ScrummingBot instance built
from bot_state.json configs.

Contract:
    ctrl = FleetReplayController(
        configs,                    # list[dict] from bot_state_loader
        candles_by_symbol,          # {symbol: rows} -- YTD candle window
        activity_log_cb=..,         # str -> None (Simulator Activity Log)
        performance_log_cb=..,      # str -> None (Simulator Performance Log)
    )
    await ctrl.start()   # spawns tick task, returns immediately
    ctrl.request_stop()  # cooperative shutdown
    await ctrl.stopped_event.wait()   # optional: block until fully stopped

Per-tick loop:
    1. Advance the TabletBackend cursor one candle across all symbols.
    2. For each bot: call bot.tick() (real class code, unmodified).
    3. Update progress state (candles played, per-bot trades, etc.).
    4. Repeat until every series exhausts or request_stop() is called.

Tick rate: ``tick_delay_s`` sets the sleep between ticks. 0.0 plays
at wall-clock speed; a caller can raise it for observability.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from bisect import bisect_right
from dataclasses import dataclass, field

from src.trading.stone_tablets import addressing

_YIELD_BUDGET_S = 0.020
"""Minimum wall-clock gap between event-loop yields in the replay loop.
See ``FleetReplayController._maybe_yield``."""
from typing import TYPE_CHECKING, Any, Callable, Optional

from src.exchange.ccxt_connector import CCXTConnector
from src.exchange.tablet_backend import TabletBackend
from .sim_exchange import make_symbol_series_map

if TYPE_CHECKING:
    # String annotations only, under `from __future__ import annotations`;
    # the module takes on no import of these at run time.
    from src.exchange.base import ExchangeInterface, Trade

logger = logging.getLogger("acervator.simulator.fleet.controller")


@dataclass
class ReplayProgress:
    """Snapshot of what the controller has done. Read by the GUI on
    a QTimer for the status line + per-bot trade counters."""

    candles_played: int = 0
    total_candles: int = 0
    bots_ticked: int = 0
    trades_fired: int = 0
    exceptions: int = 0
    # Candles fast-skipped in anchored mode; non-zero means a
    # screening pass, not authoritative parity.
    candles_skipped: int = 0
    # Event-loop yields so far; divided by candles_played it predicts
    # replay throughput under the GUI's asyncio pump.
    yields_emitted: int = 0
    anchored: bool = False
    started_at_wall: float = 0.0
    finished: bool = False
    stop_requested: bool = False
    last_error: Optional[str] = None
    # Count of each distinct exception signature seen, so repeated
    # failures collapse to one diagnosable line instead of flooding.
    exception_samples: dict[str, int] = field(default_factory=dict)
    per_bot_trade_count: dict[str, int] = field(default_factory=dict)
    # Trade count keyed by symbol; each symbol maps to exactly one
    # bot in the fleet.
    per_symbol_trade_count: dict[str, int] = field(default_factory=dict)
    # Ticks skipped because the symbol's tablet had not started yet.
    bot_ticks_before_tape: int = 0
    # Splits bots_ticked, which counts tick entries only, into
    # worked, throttled and unknown outcomes.
    bot_ticks_worked: int = 0
    bot_ticks_throttled: int = 0
    bot_ticks_unknown: int = 0
    # Candles advanced past the first on one tick, driven by
    # Nuclear's load pulse.
    candles_fed_under_load: int = 0


SIM_ID_PREFIX = "simulated_"
"""Prefix marking a bot id as a Simulator instance: ``simulated_<live
bot_id>``. Self-identifying against a live row, and joinable back to
the live id by stripping the prefix."""


def sim_bot_id(live_bot_id: str) -> str:
    """`simulated_<live id>`. Idempotent: prefixing twice is a bug that
    would silently break the wire join, so it is refused here."""
    _s = str(live_bot_id or "")
    return _s if _s.startswith(SIM_ID_PREFIX) else SIM_ID_PREFIX + _s


def live_bot_id(sim_id: str) -> str:
    """Inverse of `sim_bot_id` -- the join back to bot_state."""
    _s = str(sim_id or "")
    return _s[len(SIM_ID_PREFIX) :] if _s.startswith(SIM_ID_PREFIX) else _s


def _make_sim_capital_registry():
    """A private, non-persisting capital-reservation registry.

    Reservations are made, checked and released for real against a
    temp-file-backed registry with ``autosave=False``, so a sim fleet
    cannot corrupt or be blocked by the live registry at
    ``~/.acervator/reservation_state.json``.
    """
    try:
        import tempfile
        from pathlib import Path as _P
        from src.trading.capital_reservation import CapitalReservationRegistry

        tmp = _P(tempfile.mkdtemp(prefix="acervator-sim-crr-"))
        return CapitalReservationRegistry(
            state_path=tmp / "reservation_state.json", autosave=False
        )
    except Exception as exc:
        # Fails closed rather than falling back to the process-wide
        # registry, which autosaves into the operator's live state.
        logger.error(
            "sim capital registry could not be created (%s) — aborting "
            "rather than resolving the process-wide registry",
            exc,
        )
        raise RuntimeError(
            f"sim capital-registry isolation failed: {exc}. Refusing to "
            f"fall back to the process-wide registry, which autosaves "
            f"into the operator's runtime tree."
        ) from exc


def resolve_phantoms_enabled(cfg: dict, force: bool = False) -> bool:
    """Whether this bot's phantoms run in a replay.

    ``phantoms_enabled`` may sit at the top level of ``cfg`` or nested
    under ``cfg["config"]``; both shapes are checked. ``force`` is the
    per-run panel toggle and can only turn phantoms ON, never off.
    Defaults to False when neither shape declares it.
    """
    if force:
        return True
    if not isinstance(cfg, dict):
        return False
    if "phantoms_enabled" in cfg:
        return bool(cfg.get("phantoms_enabled"))
    _inner = cfg.get("config")
    if isinstance(_inner, dict) and "phantoms_enabled" in _inner:
        return bool(_inner.get("phantoms_enabled"))
    return False


def _instantiate_bot(
    cfg: dict,
    exchange: ExchangeInterface,
    capital_registry: Optional[Any] = None,
) -> Optional[Any]:
    """Build a ScrummingBot from a bot_state.json config against the
    exchange it will trade on, using ``make_bot_config`` for mode-shape
    validation.

    ``exchange`` is typed ``ExchangeInterface`` rather than a concrete
    class: it accepts both the ``CCXTConnector`` that ``_build_sim``
    passes and the older ``FleetSimExchange``.

    Returns None, with a logged warning, on any construction error;
    the caller skips that bot and continues.
    """
    # Refused before any construction: a bot built with no injected
    # registry would resolve the process-wide one, which autosaves to
    # the operator's live reservation state.
    if capital_registry is None:
        logger.warning(
            "FleetReplayController: refusing to construct sim bot %s — "
            "no capital registry was injected, and a sim bot without one "
            "resolves the process-wide registry that persists to the "
            "operator's reservation_state.json.",
            str(cfg.get("bot_id", "?")) if isinstance(cfg, dict) else "?",
        )
        return None
    try:
        from src.trading.bot_container import make_bot_config, BotMode
        from src.trading.scrumming_bot import ScrummingBot
    except Exception as _imp_exc:
        logger.warning("FleetReplayController: bot imports failed: %s", _imp_exc)
        return None

    if cfg.get("mode", "").lower() != "scrumming":
        return None

    try:
        # Every BotConfig field present on `cfg` passes through, using
        # bot_container's own Extractor-only exclusion set so the two
        # cannot drift apart.
        import dataclasses as _dc

        from src.trading.bot_container import (
            _BOT_CONFIG_EXTRACTOR_ONLY_FIELDS as _EXTRACTOR_ONLY,
        )
        from src.trading.bot_container import BotConfig as _BC

        _fields = {f.name for f in _dc.fields(_BC)}
        passthrough = {
            k: v
            for k, v in cfg.items()
            if k in _fields
            and k not in ("mode", "exchange_id")
            and k not in _EXTRACTOR_ONLY
        }
        # exchange_id carries the venue from `cfg`, not the sim
        # exchange object: `timeframes.py` keys phantom availability by
        # venue id, and the counterparty is decided by which exchange
        # object the bot holds, not by this string.
        _real_venue = str(cfg.get("exchange_id") or "").strip()
        passthrough["exchange_id"] = _real_venue or exchange.exchange_id
        # base_currency and target_asset have no BotConfig default;
        # a hand-built config omitting them would otherwise fail to
        # construct.
        passthrough.setdefault("base_currency", "USD")
        passthrough.setdefault("target_asset", "BTC")
        _dropped = sorted(k for k in cfg if k not in _fields and not k.startswith("_"))
        if _dropped:
            logger.debug(
                "sim bot %s: %d bot_state key(s) are not BotConfig "
                "fields and were not passed: %s",
                cfg.get("symbol", "?"),
                len(_dropped),
                _dropped,
            )

        bot_config = make_bot_config(BotMode.SCRUMMING, **passthrough)
        # sim_mode=True suppresses trade-notification bus emits so
        # main_window's sound engine stays silent during Fleet Replay.
        # enable_phantoms is read from the persisted per-bot flag; see
        # resolve_phantoms_enabled.
        return ScrummingBot(
            bot_config,
            exchange,
            enable_phantoms=resolve_phantoms_enabled(cfg),
            sim_mode=True,
            capital_registry=capital_registry,
        )
    except Exception as _cfg_exc:  # noqa: BLE001 - construction guard
        logger.warning(
            "FleetReplayController: skip %s config (build failed: %s)",
            cfg.get("symbol", "?"),
            _cfg_exc,
        )
        return None


# ccxt OHLCV column order is [ts, open, high, low, close, volume]; the
# close TabletBackend.fetch_ticker reads sits at index 4.
OHLCV_CLOSE = 4


def _positive_finite(value: object) -> Optional[float]:
    """Return *value* as a positive finite float, or None.

    Accepts int, float or str (the types JSON can hold); any other
    type, a string that fails to parse, or a non-positive or
    non-finite result returns None instead of raising.
    """
    if not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0.0:
        return None
    return number


def opening_lot_for_lotless(target_balance: object, rows: list[list]) -> Optional[dict]:
    """Return the one lot a bot with no bot_state opens locked with.

    Locked and spendable start equal: the base leg opens at the units
    ``target_balance`` buys at the tape's first close price, so the two
    sides value to the same number. A zero or non-finite basis is
    refused, matching ``ScrummingBot._book_reconciliation_lot``.

    Returns None -- open flat, unchanged -- when there is no target, no
    tape, or no usable price. The returned shape is
    ``{units, initial_buy_price, operator_initiated}``.
    """
    target = _positive_finite(target_balance)
    first = rows[0] if rows else []
    price = _positive_finite(first[OHLCV_CLOSE]) if len(first) > OHLCV_CLOSE else None
    if target is None or price is None:
        return None
    units = _positive_finite(target / price)
    if units is None:
        return None
    return {"units": units, "initial_buy_price": price, "operator_initiated": False}


class FleetReplayController:
    """Owns the async tick loop that plays YTD candles through sim
    bots. All GUI interactions run through callbacks so the
    controller stays testable outside Qt."""

    def __init__(
        self,
        configs: list[dict],
        candles_by_symbol: dict[str, list[list[float]]],
        activity_log_cb: Optional[Callable[[str], None]] = None,
        performance_log_cb: Optional[Callable[[str], None]] = None,
        tick_delay_s: float = 0.0,
        max_candles: Optional[int] = None,
        window_since_ms: Optional[int] = None,
        window_until_ms: Optional[int] = None,
        smart_wires: Optional[list[dict]] = None,
    ) -> None:
        self._configs = list(configs or [])
        # Passed in rather than read from bot_state, so the controller
        # stays free of file IO and is constructible without one.
        self._smart_wires = list(smart_wires or [])
        # symbol -> live bot id, for attributing sim fills; populated
        # in _build_sim, since the exchange reports a fill by symbol.
        self._bot_id_for_symbol: dict = {}
        # Per-bot TA observation counts; a fleet-wide ratio would be
        # meaningless across tablets with different start dates.
        self._ta_observed: dict = {}
        self._signal_sink = None
        # Set by Nuclear to drive candles-per-tick. None = 1.
        self._load_feed_cb = None
        self._ta_eligible: dict = {}
        # Built in _build_sim, only for a fleet joinable to bot_state;
        # owns a private EventBus.
        self._smart_wire_mgr: Optional[Any] = None
        self._sim_bus: Optional[Any] = None
        self._candles_by_symbol = dict(candles_by_symbol or {})
        self._activity = activity_log_cb or (lambda _m: None)
        self._perf = performance_log_cb or (lambda _m: None)
        self._tick_delay = float(tick_delay_s)
        self._max_candles = max_candles
        # YTD window bounds; when set, only candles with ts in
        # [window_since_ms, window_until_ms] play.
        self._window_since_ms = window_since_ms
        self._window_until_ms = window_until_ms
        # The connector the bots hold: a real CCXTConnector served by
        # the tape.
        self._exchange: Optional[Any] = None
        # Owns the replay's clock, cursors and ledger seeding.
        # Assigned in _build_sim.
        self._tape: Optional[TabletBackend] = None
        self._bots: list[Any] = []
        self._task: Optional[asyncio.Task] = None
        # Durable per-run record under ~/.acervator_logs/sim/; opened
        # in start(), closed in the run loop's finally block.
        self._run_log: Optional[Any] = None
        # Anchored screening mode: None evaluates every candle
        # (authoritative); a set of indices evaluates only those.
        self._anchor_indices: Optional[set[int]] = None
        # Candles where a historical trade is expected. Kept separate
        # from _anchor_indices so trade markers work in both modes.
        self._expected_indices: Optional[set[int]] = None
        self._candle_i: int = 0
        # Markers produced by the worker, drained by the GUI thread.
        self._pending_markers: list[tuple[str, bool]] = []
        self.progress = ReplayProgress()
        self.stopped_event = asyncio.Event()
        self.stopped_event.set()  # not-yet-started = "already stopped"
        # Visual refresh callback + cadence; the panel wires this via
        # set_visual_refresh_cb() after construction.
        self._visual_refresh_cb: Optional[Callable[[int], None]] = None
        # Set again in start(); initialised here so _maybe_yield is
        # safe if called before a run begins.
        self._last_yield: float = time.perf_counter()
        self._visual_refresh_every: int = 100

    # ── Public API ───────────────────────────────────────────────
    async def start(self) -> bool:
        """Build exchange + bots + launch the tick task. Returns
        immediately; use stopped_event to await completion.

        Returns True when a tick task was launched, False on refusal.
        On refusal this sets ``progress.finished`` and leaves
        ``stopped_event`` set, so a caller polling either one observes
        a terminated run rather than blocking forever.
        """
        if self._task is not None and not self._task.done():
            # Leaves `progress` untouched: another replay owns it and
            # is still running.
            self._activity("Controller already running.")
            return False
        # Sink installed before _build_sim, whose emitters
        # (fleet.03.005 through .008) need it live; no run directory
        # exists yet, so records buffer in memory until the path is
        # attached below.
        try:
            from src.core.signal_contract import SignalSink, get_sink, set_sink

            # Saved so teardown can restore it; the process-level sink
            # must survive a replay.
            self._prior_sink = get_sink()
            self._signal_sink = SignalSink()
            set_sink(self._signal_sink)
        except Exception as _ssx:  # noqa: BLE001 - advisory
            logger.debug("signal sink install failed: %s", _ssx)
        self._build_sim()
        if self._exchange is None or not self._bots:
            self._activity(
                "Cannot start: no bots instantiated. "
                "(Loaded configs OR candle series missing.)"
            )
            # Nothing else owns `progress`; `stopped_event` is already
            # set, so a never-started run reads as stopped.
            self.progress.finished = True
            return False
        self.progress = ReplayProgress(
            total_candles=self._total_candle_count(),
            per_bot_trade_count={
                str(getattr(b, "bot_id", i)): 0 for i, b in enumerate(self._bots)
            },
        )
        self.stopped_event.clear()
        self.progress.started_at_wall = time.time()
        self._last_yield = time.perf_counter()

        # Opens the durable run record and hooks each sim bot's
        # private bus: these handlers cannot see live events, and
        # live subscribers cannot see these.
        try:
            from src.trading.sim_run_log import SimRunLog

            self._run_log = SimRunLog()
            # Signal sink is scoped to the run, not the process:
            # opened beside the run log, cleared in the same finally
            # that closes it, so a finished run cannot keep collecting.
            self._run_log.start_run(
                config={
                    "bots": len(self._bots),
                    "symbols": sorted(self._candles_by_symbol.keys()),
                    "total_candles": self.progress.total_candles,
                    "max_candles": self._max_candles,
                    # Anchored mode skips bot.tick() on candles with no
                    # expected trade, so per-tick state can drift from
                    # full evaluation; parity checks need full
                    # evaluation, not anchored screening.
                    "anchored": bool(self._anchor_indices),
                    "full_evaluation": not bool(self._anchor_indices),
                    "anchor_candles": (
                        len(self._anchor_indices) if self._anchor_indices else 0
                    ),
                }
            )
            # SimRunLog._dir is created by start_run, not __init__, so
            # the sink's path can only be attached after this call.
            try:
                _rl_dir = getattr(self._run_log, "_dir", None)
                if _rl_dir is not None and self._signal_sink is not None:
                    self._signal_sink.path = _rl_dir / "signals.jsonl"
            except Exception as _spx:  # noqa: BLE001 - advisory
                logger.debug("signal sink path attach failed: %s", _spx)
            attached = sum(1 for b in self._bots if self._run_log.attach_to_bot_bus(b))
            self._activity(
                f"Sim run log: {self._run_log.run_id} "
                f"({attached}/{len(self._bots)} bot buses attached)"
            )
        except Exception as _rl_exc:  # noqa: BLE001 - logging is advisory
            self._run_log = None
            logger.warning("sim run log unavailable: %s", _rl_exc)
        self._activity(
            f"Fleet Replay started: {len(self._bots)} bot(s) × "
            f"{self.progress.total_candles} candles."
        )
        self._task = asyncio.create_task(self._run())
        return True

    @property
    def tape(self) -> Optional[TabletBackend]:
        """The run's ``TabletBackend`` -- the replay's ledger and clock.

        Public, so a consumer outside this class can read balances and
        fills through ``balances()``, ``snapshot()`` and
        ``fetch_my_trades()``, each returning a copy. None before
        ``_build_sim`` has run.
        """
        return self._tape

    def set_load_feed(self, cb) -> None:
        """Install a callable returning candles-to-feed for the next tick.

        Unset, the replay advances one candle per tick. Nuclear passes
        ``SystemLoadOscillator.tick_workload``.
        """
        self._load_feed_cb = cb

    def request_stop(self) -> None:
        """Cooperative stop. Tick loop exits after current iteration."""
        self.progress.stop_requested = True
        self._activity("Stop requested — draining current tick.")

    async def _maybe_yield(self) -> None:
        """Yield to the event loop, but at most once per _YIELD_BUDGET_S.

        Time-based rather than count-based: under the GUI,
        ``main._make_async_pump_timer`` drives the loop through
        ``src.core.tick_driver.pump_once`` on a 50 ms QTimer, so every
        yield costs a full pump period regardless of how many are
        requested in that window. A headless ``asyncio.run()`` loop is
        free-running, so a yield there costs microseconds.

        Do not shorten the GUI's pump interval to speed this up: the
        same pump drives every live bot tick.
        """
        if time.perf_counter() - self._last_yield < _YIELD_BUDGET_S:
            return
        self.progress.yields_emitted += 1
        await asyncio.sleep(0)
        # Stamped after the await, not before: taken earlier, the
        # elapsed time on resume would already exceed the budget and
        # every call would yield.
        self._last_yield = time.perf_counter()

    def set_visual_refresh_cb(
        self,
        cb: Optional[Callable[[int], None]],
        every_n_candles: int = 100,
    ) -> None:
        """Wire a per-N-candle visual refresh callback. Called after
        construction by the GUI panel; safe to call again to change
        cadence."""
        self._visual_refresh_cb = cb
        self._visual_refresh_every = max(1, int(every_n_candles))

    # ── Internal ─────────────────────────────────────────────────
    def _total_candle_count(self) -> int:
        if not self._exchange:
            return 0
        try:
            # The master clock's sorted union of every series'
            # timestamps: the actual denominator for playback length.
            if self._tape is None:
                return 0
            return int(self._tape.total_clock_ticks())
        except Exception:  # noqa: BLE001,S110 - progress best-effort
            return 0

    def _build_sim(self) -> None:
        if not self._candles_by_symbol:
            self._activity("No candle series provided.")
            return
        # Stone Tablets stay immutable; the YTD window is applied via
        # CandleSeries.step_to_ts at iteration time, not by trimming
        # the series.
        series_map = make_symbol_series_map(self._candles_by_symbol)
        available_symbols = set(series_map.keys())

        # Wallet seed sums each bot's target_balance ("locked"), per
        # quote currency, across bots with a Stone Tablet -- so
        # spendable starts equal to locked and a partial fleet gets a
        # proportionally-sized wallet.
        seed_by_quote: dict[str, float] = {}
        for cfg in self._configs:
            sym = str(cfg.get("symbol", "") or "")
            if sym not in available_symbols:
                continue
            quote = str(cfg.get("base_currency", "USD") or "USD").upper()
            try:
                seed_by_quote[quote] = seed_by_quote.get(quote, 0.0) + float(
                    cfg.get("target_balance", 0.0) or 0.0
                )
            except (TypeError, ValueError):
                continue
        seed_usd = sum(seed_by_quote.values())
        if seed_usd <= 0:
            # No usable targets — fall back to a nominal float so the
            # exchange is still constructible, and say so rather than
            # silently simulating with an arbitrary balance.
            seed_by_quote = {"USD": 1000.0}
            seed_usd = 1000.0
            self._activity(
                "Wallet seed: no target_balance found in configs — "
                "falling back to $1,000.00 nominal."
            )
        else:
            _detail = ", ".join(
                f"{q} ${v:,.2f}" for q, v in sorted(seed_by_quote.items())
            )
            self._activity(
                f"Wallet seed: ${seed_usd:,.2f} across "
                f"{len(seed_by_quote)} quote currenc"
                f"{'y' if len(seed_by_quote) == 1 else 'ies'} "
                f"({_detail}); spendable starts equal to locked."
            )

        # One private registry per replay, shared by that replay's
        # bots, so cross-bot reservation contention is exercised
        # without reaching live state.
        self._sim_capital_registry = _make_sim_capital_registry()
        # BotConfig.trading_fee_pct is a percent (e.g. 1.6); the
        # exchange multiplies notional by a fraction, hence the /100.
        _fees = {}
        for cfg in self._configs:
            _sym = str(cfg.get("symbol", "") or "")
            if not _sym:
                continue
            try:
                _fees[_sym] = float(cfg.get("trading_fee_pct", 0.6) or 0.0) / 100.0
            except (TypeError, ValueError):
                continue
        # Bots hold a real CCXTConnector; TabletBackend implements the
        # ccxt surface beneath it, so normalisation and fee logic are
        # the same code path as live. `_tape` owns the replay's clock,
        # cursors and seeding, and no bot touches it directly; bots
        # see only the connector, as in live.
        self._tape = TabletBackend(
            {
                sym: [list(r) for r in rows]
                for sym, rows in self._candles_by_symbol.items()
            },
            balances=dict(seed_by_quote),
            fee_rate_by_symbol=_fees,
        )
        _conn = CCXTConnector("coinbase")
        _conn.attach_backend(self._tape)
        self._exchange = _conn
        if _fees:
            _rates = sorted({round(v * 100.0, 4) for v in _fees.values()})
            self._activity(
                "Trading fees: charging per-symbol rates from bot_state "
                f"({', '.join(f'{r}%' for r in _rates)}) — the sim "
                "previously charged zero."
            )
        self._tape.on_trade(self._on_sim_trade)

        # Whether the fleet joins back to bot_state at all, decided
        # once for the whole fleet: a per-config decision would make a
        # broken join look like a synthetic fleet.
        _n_configs = len(self._configs)
        _n_joinable = sum(
            1 for c in self._configs if str(c.get("_src_bot_id", "") or "").strip()
        )
        _joinable = _n_joinable > 0
        if _joinable and _n_joinable == _n_configs:
            self._activity(
                f"Bot ids: joined to bot_state — {_n_joinable} bot(s) "
                "carry their persisted id, so Smart Wires, parity "
                "attribution and run-log correlation can resolve."
            )
        elif not _joinable:
            self._activity(
                f"Bot ids: SYNTHETIC — none of the {_n_configs} "
                "config(s) carry a persisted id, so each bot gets a "
                "fresh one. Smart Wires cannot route and parity "
                "attribution cannot join. Expected for a proposal or "
                "hand-built fleet; NOT expected for a bot_state replay."
            )

        # Instantiate bots. Skip any whose symbol isn't in the
        # candle series (can't sim without price data).
        _imported_state = 0
        _import_failed = 0
        _import_missing = 0
        # Bots with no `_src_scrumming_state`; see the locked-side
        # block below the loop.
        _no_bot_state: list[tuple[Any, dict]] = []
        for cfg in self._configs:
            sym = str(cfg.get("symbol", "") or "")
            if sym not in available_symbols:
                continue
            bot = _instantiate_bot(cfg, self._exchange, self._sim_capital_registry)
            if bot is not None:
                # BotContainer.__init__ mints a fresh uuid4 bot_id;
                # carrying the persisted one here is what lets
                # SmartWireManager.get_outgoing_wires and parity
                # attribution resolve against bot_state.
                #
                # Checked at the FLEET level: a partial join (some
                # configs carrying `_src_bot_id`, some not) raises,
                # since it would silently drop that bot's wires. A
                # fleet with none is synthetic and gets fresh uuid4s,
                # expected for a proposal fleet built by
                # `topology_stress._config_for`.
                if _joinable:
                    _src = str(cfg.get("_src_bot_id", "") or "").strip()
                    if not _src:
                        raise KeyError(
                            f"_src_bot_id missing from the config for "
                            f"{sym} while {_n_joinable} of "
                            f"{_n_configs} configs in this fleet carry "
                            "one — a partial join silently drops that "
                            "bot's Smart Wires, parity attribution and "
                            "run-log correlation"
                        )
                    bot.bot_id = sim_bot_id(_src)

                # bot_state is the only source of initiating state.
                # import_scrumming_state is the inverse of
                # export_scrumming_state; live calls the same pair
                # during restore (container/restore.py).
                _scrum = cfg.get("_src_scrumming_state")
                if isinstance(_scrum, dict) and hasattr(bot, "import_scrumming_state"):
                    try:
                        bot.import_scrumming_state(_scrum)
                        _imported_state += 1
                        # Round-trips the imported state through
                        # export_scrumming_state and compares
                        # field-for-field by canonical JSON, so a lot
                        # list with the right length but wrong
                        # contents fails. Differing field names are
                        # recorded in context, not just a count.
                        try:
                            import json as _pj

                            _back = bot.export_scrumming_state()
                            _bad = sorted(
                                k
                                for k in (set(_scrum) | set(_back))
                                if _pj.dumps(
                                    _scrum.get(k), sort_keys=True, default=repr
                                )
                                != _pj.dumps(_back.get(k), sort_keys=True, default=repr)
                            )
                            from src.core.signal_contract import emit as _pe

                            _pe(
                                "fleet.03.005.invariant.state_parity",
                                actual=len(_scrum) - len(_bad),
                                expected=len(_scrum),
                                context={
                                    "bot_id": bot.bot_id,
                                    "symbol": sym,
                                    "differing": _bad,
                                },
                            )
                        except Exception as _pex:  # noqa: BLE001
                            logger.debug("parity emit failed: %s", _pex)
                    except Exception as _isx:  # noqa: BLE001
                        self._activity(
                            f"  WARNING {sym}: scrumming_state import "
                            f"failed ({type(_isx).__name__}: {_isx}) — this "
                            "bot starts from config defaults, NOT from "
                            "bot_state. Its run is not comparable to live."
                        )
                        _import_failed += 1
                elif _scrum is None:
                    _import_missing += 1
                    _no_bot_state.append((bot, cfg))
                self._bots.append(bot)
                # Records the join for trade attribution.
                if sym:
                    self._bot_id_for_symbol[sym] = bot.bot_id
                # Warns when a bot's quote leg opened at zero; it can
                # never afford a buy, but nothing here skips the bot.
                _q = str(cfg.get("base_currency", "USD") or "USD").upper()
                if float(seed_by_quote.get(_q, 0.0)) <= 0.0:
                    self._activity(
                        f"  WARNING {sym}: quote {_q} opened with $0.00 "
                        "— this bot cannot fund a buy and will record "
                        "no trades. Its target_balance did not reach "
                        "the wallet seed."
                    )
        self._build_smart_wires(_joinable)
        # A bot with no bot_state opens with a locked side, so the
        # credit loop below has lots to seed it from.
        self._open_locked_sides(_no_bot_state)
        # Seeds the exchange from the fleet's own restored lots.
        # bot_state is the only source of initiating state; the
        # authoritative unit count is the restored `_main_lots`,
        # matching the invariant `ReconciliationEngineMixin` keeps:
        # sum(l["units"] for l in _main_lots) == _current_holdings.
        _seeded = 0
        _seeded_units = 0.0
        for _b in self._bots:
            _asset = str(
                getattr(getattr(_b, "config", None), "target_asset", "") or ""
            ).upper()
            if not _asset:
                continue
            _units = 0.0
            for _lot in getattr(_b, "_main_lots", None) or []:
                try:
                    _units += float(_lot.get("units", 0.0) or 0.0)
                except (TypeError, ValueError, AttributeError):
                    continue
            if _units <= 0:
                continue
            self._tape.credit(_asset, _units)
            _seeded += 1
            _seeded_units += _units
        self._tape.mark_opening_balances()

        try:
            from src.core.signal_contract import emit as _fs

            _fs(
                "fleet.03.006.postcondition.state_imported",
                actual=_imported_state,
                expected=len(self._bots),
                context={"failed": _import_failed, "missing": _import_missing},
            )
            _fs(
                "fleet.03.007.postcondition.positions_seeded_from_lots",
                actual=_seeded,
                expected=len(self._bots),
                context={"total_units": round(_seeded_units, 8)},
            )
        except Exception as _fx:  # noqa: BLE001 - advisory
            logger.debug("fleet state emit failed: %s", _fx)

        self._activity(
            f"Opening state: {_imported_state} of {len(self._bots)} bot(s) "
            f"imported scrumming_state from bot_state; {_seeded} seeded a "
            f"position from their own restored lots."
            + (f" {_import_failed} FAILED to import." if _import_failed else "")
            + (
                f" {_import_missing} had no scrumming_state in bot_state."
                if _import_missing
                else ""
            )
        )

        self._assert_capital_isolation()

    def _open_locked_sides(self, lotless: list[tuple[Any, dict]]) -> None:
        """Open every bot that carries no bot_state with a locked side.

        Locked and spendable start equal. Called immediately before
        the credit loop in `_build_sim`, since the lots this writes
        are what that loop reads.

        A proposal fleet built by `topology_stress._config_for`
        carries no `_src_scrumming_state`, so the import in
        `_build_sim` never runs and every such bot would otherwise
        open flat; `opening_lot_for_lotless` computes the lot this
        writes.

        Writes through the same export_scrumming_state /
        import_scrumming_state pair `_build_sim` uses on a restored
        fleet, replacing only `main_lots`; every other field is the
        bot's own current value. The tape itself is not touched here --
        the credit loop in `_build_sim` reads `_main_lots` and credits
        the venue for both paths alike.
        """
        opened = 0
        units = 0.0
        for bot, cfg in lotless:
            symbol = str(cfg.get("symbol", "") or "")
            lot = opening_lot_for_lotless(
                cfg.get("target_balance"), self._candles_by_symbol.get(symbol) or []
            )
            if lot is None:
                continue
            try:
                state = bot.export_scrumming_state()
                state["main_lots"] = [dict(lot)]
                bot.import_scrumming_state(state)
            except Exception as exc:  # noqa: BLE001 - never fail a build
                self._activity(
                    f"  WARNING {symbol or '?'}: could not open a locked "
                    f"side ({type(exc).__name__}: {exc}) — this bot "
                    "starts flat and must buy its whole target before "
                    "it can trade."
                )
                continue
            opened += 1
            units += float(lot["units"])
        if opened:
            self._activity(
                f"Locked side: {opened} of {len(lotless)} bot(s) carry "
                "no bot_state and opened holding their target_balance "
                "in base units at the tape's first close; locked and "
                "spendable start equal."
            )
        try:
            from src.core.signal_contract import emit as _ol

            _ol(
                "fleet.03.008.postcondition.lotless_opened_locked",
                actual=opened,
                expected=len(lotless),
                context={"total_units": round(units, 8)},
            )
        except Exception as _olx:  # noqa: BLE001 - advisory
            logger.debug("locked-side emit failed: %s", _olx)

    def _build_smart_wires(self, joinable: bool) -> None:
        """Attach the fleet's persisted Smart Wires to this replay.

        Called after the bot loop, since a wire has two endpoints and
        both must exist before the active count means anything.

        The manager gets a dedicated EventBus rather than an unbussed
        one: `SmartWireManager.__init__` defaults `bus=None` and then
        resolves the process-wide bus, which is why live instead
        passes its own (`BotManager.__init__`). Each sim bot already
        builds its own private `EventBus()`, so there is no single
        "sim bus" to reuse.

        A synthetic fleet (uuid4 ids, not joined to bot_state) gets no
        manager at all: wires are keyed by the persisted bot id, and
        nothing resolves against a uuid4.
        """
        if not joinable or not self._smart_wires:
            return
        try:
            from src.core.event_bus import EventBus
            from src.trading.smart_wire import SmartWireManager
        except Exception as _imp_exc:  # noqa: BLE001
            self._activity(
                f"Smart Wires: unavailable ({type(_imp_exc).__name__}) — "
                "the replay runs WITHOUT cross-bot compounding, so its "
                "accumulation curve is not comparable to live's."
            )
            return

        self._sim_bus = EventBus()
        mgr = SmartWireManager(bus=self._sim_bus)
        sim_ids = set()
        for bot in self._bots:
            mgr.attach_bot(bot.bot_id, bot)
            bot.set_smart_wire(mgr)
            sim_ids.add(bot.bot_id)

        # bot_state's wires are keyed by the live bot id, but sim bots
        # carry `simulated_<live id>`; both endpoints are remapped here
        # so the topology's edges and percentages carry over intact.
        _sim_wires = []
        for _w in self._smart_wires or []:
            if not isinstance(_w, dict):
                continue
            _tw = dict(_w)
            _tw["source_id"] = sim_bot_id(_w.get("source_id", ""))
            _tw["target_id"] = sim_bot_id(_w.get("target_id", ""))
            _sim_wires.append(_tw)

        imported = mgr.import_wires(_sim_wires)

        # `import_wires` performs no existence check; `active` counts
        # only wires whose both endpoints exist in this run's fleet.
        active = sum(
            1
            for w in _sim_wires
            if str(w.get("source_id", "")) in sim_ids
            and str(w.get("target_id", "")) in sim_ids
        )

        self._smart_wire_mgr = mgr
        self._activity(
            f"Smart Wires: {active} of {imported} imported wire(s) have "
            f"BOTH endpoints in this run's {len(sim_ids)}-bot fleet and "
            "can route; the rest reference bots this replay did not "
            "instantiate."
        )
        if active == 0 and imported:
            self._activity(
                "  WARNING: no wire can route in this run. Cross-bot "
                "compounding is inert, so the accumulation curve will "
                "understate live's."
            )
        # Ledgers are not imported: seeding live's accrued
        # wired_in/wired_out totals would pass a non-zero check without
        # a single sim wire firing during this replay.

    def _assert_capital_isolation(self) -> None:
        """Every constructed sim bot must be off the live registry.

        The guards upstream -- the factory raising, `_instantiate_bot`
        refusing, `_crr()` returning None in sim mode -- each protect
        one path. This checks the outcome they exist to produce, once,
        at the point where the bot set is final and before any of them
        can trade. Aborts the run rather than let a replay write sim
        reservations into the operator's live capital state.
        """
        # Checks the `autosave` property, not identity against the
        # live singleton: comparing against `get_registry()` would
        # resolve -- and construct, if absent -- the process-wide
        # registry from a sim path. Pinned by
        # tests/test_singleton_isolation.py.
        leaked = []
        for bot in self._bots:
            reg = getattr(bot, "_capital_registry", None)
            if reg is None or getattr(reg, "_autosave", True):
                leaked.append(str(getattr(bot, "bot_id", "?")))
        if leaked:
            raise RuntimeError(
                f"sim capital isolation breached: {len(leaked)} of "
                f"{len(self._bots)} sim bot(s) resolve the process-wide "
                f"capital registry, which persists to the operator's "
                f"reservation_state.json — {', '.join(leaked[:8])}"
                f"{' ...' if len(leaked) > 8 else ''}. Refusing to start "
                f"the replay."
            )
        self._activity(
            f"  capital isolation verified: {len(self._bots)} sim bot(s) "
            f"on private, non-persisting registries."
        )

    def _observe_ta(self, bot) -> None:
        """Compute this bot's TA on the current candle, for the record.

        Observation only: never feeds the bot, places an order, or
        touches bot state. `VotingEngine.compute_all` is stateless
        with no caching, so calling it here cannot perturb what the
        bot would have done.

        Emits via the engine's own
        `ta.07.004.postcondition.raw.<indicator>` records, covering
        every candle rather than only the ones the bot's own
        read-rate throttle lets through. Never raises.
        """
        try:
            _eng = getattr(bot, "_voting_engine", None)
            if _eng is None:
                return
            _sym = str(bot.config.symbol)
            if not self._tape.has_data(_sym):
                return
            _tf = str(getattr(bot.config, "ta_timeframe", "") or "5m")
            _need = int(getattr(self, "_ta_observe_window", 0) or 200)
            # Reads from the tape directly, not through the connector,
            # so it does not inherit the ccxt page-size limit that
            # governs what a bot's own exchange call receives.
            _rows = self._tape.history(_sym, _need)
            if not _rows or len(_rows) < 51:
                # 51 is the engine's deepest guard (ZScore, period + 1);
                # below it some indicators have no basis to compute on.
                return
            from src.trading.ta_engine import candles_from_raw

            _eng.compute_all(
                candles_from_raw([list(r) for r in _rows]),
                _tf,
                symbol=bot.config.symbol,
            )
            self._ta_observed[bot.bot_id] = self._ta_observed.get(bot.bot_id, 0) + 1
        except Exception as _ox:  # noqa: BLE001 - observation is advisory
            logger.debug("TA observation skipped: %s", _ox)

    def _candle_address_for(self, symbol: str) -> str:
        """``NNNNNN_TICKER`` for the candle under the tape's cursor.

        ``TabletBackend`` has no address concept of its own -- it
        serves rows, and an address is a Stone Tablet idea -- so this
        resolves it from the same cursor the fill was priced off,
        through the same ``format_address`` ``FleetSimExchange`` uses.
        Empty string when it cannot be resolved: the fill still
        records, it just carries no address rather than a wrong one.
        """
        tape = self._tape
        if tape is None:
            return ""
        try:
            return addressing.format_address(
                addressing.ticker_from_symbol(symbol), tape.cursor_for(symbol)
            )
        except Exception as exc:  # noqa: BLE001 - addressing is advisory
            logger.debug(
                "candle address for %s raised %s: %s", symbol, type(exc).__name__, exc
            )
            return ""

    def _read_fill(self, trade: dict | Trade) -> dict:
        """Normalise one fill payload into the fields this class records.

        ``TabletBackend.on_trade`` passes a ccxt-shaped dict; the
        object branch exists for ``FleetSimExchange``, whose
        ``on_trade`` still passes a ``Trade`` dataclass and which
        remains exported from ``fleet/__init__.py``. A dict is routed
        through the dict branch up front, since ``getattr`` with a
        default cannot fall back by exception.

        Time units differ between the two producers: the dict's
        ``timestamp`` is already the master clock in milliseconds
        (``TabletBackend.current_ts_ms``); the object carries seconds
        on ``.timestamp`` and the millisecond value on
        ``raw["sim_master_ts_ms"]``.
        """
        if isinstance(trade, dict):
            symbol = str(trade.get("symbol", "") or "")
            side_obj = trade.get("side", "")
            amount = float(trade.get("amount", 0) or 0)
            price = float(trade.get("price", 0) or 0)
            raw = trade.get("raw") or {}
            ts_ms = trade.get("timestamp")
        else:
            raw = getattr(trade, "raw", None) or {}
            symbol = str(getattr(trade, "symbol", "") or "")
            side_obj = getattr(trade, "side", "")
            amount = float(getattr(trade, "amount", 0) or 0)
            price = float(getattr(trade, "price", 0) or 0)
            ts_ms = raw.get("sim_master_ts_ms")
        # `OrderSide` is an enum on the object path and a plain
        # lowercase string on the dict path. `.value` unwraps the first
        # and passes the second through.
        side = str(getattr(side_obj, "value", side_obj) or "")
        addr = str(raw.get("candle_address", "") or "")
        if not addr and symbol:
            addr = self._candle_address_for(symbol)
        return {
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "price": price,
            "usd": amount * price,
            "sim_ts_ms": int(ts_ms) if ts_ms else None,
            "candle_address": addr,
        }

    def _on_sim_trade(self, trade) -> None:
        self.progress.trades_fired += 1
        fill = self._read_fill(trade)
        _sym = fill["symbol"]
        # Persists the fill under ~/.acervator_logs/sim/, never the
        # live tree.
        if self._run_log is not None:
            try:
                self._run_log.record_trade(
                    symbol=_sym,
                    # Resolved by symbol: the exchange does not report
                    # which bot placed the order. These are the live
                    # bot ids, carried in from bot_state.
                    bot_id=self._bot_id_for_symbol.get(_sym, ""),
                    # Schema declares both `action` and `side`.
                    action=fill["side"],
                    side=fill["side"],
                    amount=fill["amount"],
                    price=fill["price"],
                    usd=fill["usd"],
                    sim_ts_ms=fill["sim_ts_ms"],
                    # Spendable at fill time, so a replay's wallet
                    # trajectory is reconstructible from the log alone.
                    extra={"spendable_usd": round(self._spendable_now(), 8)},
                    # Tablet traceability.
                    candle_address=fill["candle_address"],
                )
            except Exception as _rl_exc:  # noqa: BLE001 - logging is advisory
                logger.debug("sim run log: trade record failed: %s", _rl_exc)
        # Attributed by symbol: the exchange does not report which
        # bot placed an order.
        try:
            if _sym:
                self.progress.per_symbol_trade_count[_sym] = (
                    self.progress.per_symbol_trade_count.get(_sym, 0) + 1
                )
                # Queues a chart marker: green if this candle carries
                # a historical trade, red if not. Queued because the
                # chart is a Qt widget and this runs on the worker.
                _exp = self._expected_indices
                _ok = bool(_exp) and self._candle_i in _exp
                self._pending_markers.append((_sym, _ok))
        except Exception:  # noqa: BLE001,S110 - counter best-effort
            pass

    def _spendable_now(self) -> float:
        """Quote-currency cash across the sim wallet.

        Sums every quote leg (USD + USDC + ...) rather than just
        "USD": the fleet is multi-quote, and reading one leg would
        under-report by whatever sits in the others.

        Reads ``TabletBackend.balances()``, the ledger's own public
        accessor, which returns a copy; this reaches into no private
        state and cannot mutate the wallet it reports.
        """
        tape = self._tape
        if tape is None:
            return 0.0
        quotes = {
            str(c.get("base_currency", "USD") or "USD").upper() for c in self._configs
        }
        try:
            wallet = tape.balances()
            return float(sum(float(wallet.get(q, 0.0) or 0.0) for q in quotes))
        except (AttributeError, TypeError, ValueError):
            return 0.0

    def drain_markers(self) -> list:
        """Hand queued trade markers to the GUI thread and clear.

        Called from the panel's snapshot collector. Returns a list of
        (symbol, validated) pairs.
        """
        out = self._pending_markers
        self._pending_markers = []
        return out

    async def _run(self) -> None:
        try:
            if self._exchange is None:
                return
            candle_i = 0
            while True:
                if self.progress.stop_requested:
                    self._activity(f"Stopped after {candle_i} candle(s).")
                    break
                # Anchored (screening) mode: when _anchor_indices is
                # set, only candles in that set get a full bot
                # evaluation; the rest just advance the cursor.
                #
                # Two costs stay live even though bot.tick() is
                # skipped: the skip path still steps the exchange
                # below, which sweeps resting limit orders, so a
                # skipped candle can settle a fill placed on an
                # earlier anchored one; and hysteresis arming, which
                # evolves on delta-sign crossings, loses crossings on
                # skipped ticks. A screening pass, never the
                # authoritative parity run. Default is None (evaluate
                # every candle).
                if (
                    self._anchor_indices is not None
                    and candle_i not in self._anchor_indices
                ):
                    self.progress.candles_skipped += 1
                    if not self._tape.step():
                        self._activity(
                            f"All series exhausted at candle " f"{candle_i}."
                        )
                        break
                    candle_i += 1
                    self._candle_i = candle_i
                    self.progress.candles_played = candle_i
                    if candle_i % 500 == 0:
                        await asyncio.sleep(0)
                    continue
                # Tick every bot for this candle
                self._candle_i = candle_i
                for _bi, bot in enumerate(self._bots):
                    if _bi > 0:
                        await self._maybe_yield()
                    try:
                        # A bot does not tick before its own symbol's
                        # tablet has data: the master clock is the
                        # union of every series' timestamps, so a
                        # symbol whose tablet starts later would
                        # otherwise read a candle stamped after the
                        # clock -- a price from its own future.
                        if not self._tape.has_data(bot.config.symbol):
                            self.progress.bot_ticks_before_tape += 1
                            continue
                        await bot.tick()
                        self.progress.bots_ticked += 1
                        # Observes TA on every ticked candle, not only
                        # the ones where ScrummingBot.tick's read-rate
                        # throttle lets an action through. compute_all
                        # is pure and places no orders, so this changes
                        # no trade behaviour.
                        #
                        # Counts this bot's own eligible candles, not
                        # the fleet's: a bot has no candle at a
                        # master-clock tick that predates its own
                        # tablet, so a candles_played x bots
                        # denominator would be wrong by construction.
                        if self._tape.cursor_for(bot.config.symbol) > 0:
                            self._ta_eligible[bot.bot_id] = (
                                self._ta_eligible.get(bot.bot_id, 0) + 1
                            )
                        self._observe_ta(bot)
                        # `bots_ticked` counts tick entries
                        # unconditionally, so it cannot distinguish a
                        # bot that acted from one that returned early.
                        # ScrummingBot.tick throttles by read rate: it
                        # returns early while `_tick_counter <
                        # _tick_skip`, and resets the counter to 0 only
                        # on an action tick. So a post-tick counter of
                        # 0 means work happened; non-zero means it was
                        # throttled. getattr-with-default so a bot
                        # without the attribute records as unknown
                        # rather than silently counted as working.
                        _tc = getattr(bot, "_tick_counter", None)
                        if _tc is None:
                            self.progress.bot_ticks_unknown += 1
                        elif _tc == 0:
                            self.progress.bot_ticks_worked += 1
                        else:
                            self.progress.bot_ticks_throttled += 1
                    except Exception as _tick_exc:  # noqa: BLE001
                        self.progress.exceptions += 1
                        _exc_key = (
                            f"{type(_tick_exc).__name__}: " f"{str(_tick_exc)[:120]}"
                        )
                        self.progress.last_error = _exc_key
                        # Counts distinct exception signatures so
                        # repeated failures collapse to one summary.
                        self.progress.exception_samples[_exc_key] = (
                            self.progress.exception_samples.get(_exc_key, 0) + 1
                        )
                        # Logs only the first occurrence of each
                        # distinct exception at warning level.
                        if self.progress.exception_samples[_exc_key] == 1:
                            logger.warning(
                                "sim bot tick raised: %s " "(bot=%s, symbol=%s)",
                                _exc_key,
                                getattr(bot, "bot_id", "?"),
                                getattr(getattr(bot, "config", None), "symbol", "?"),
                                exc_info=True,
                            )
                        else:
                            logger.debug("sim bot tick raised (dupe): %s", _exc_key)
                # Normally one candle per tick. Under Nuclear's load
                # pulse, `_load_feed_cb` (SystemLoadOscillator.
                # tick_workload) returns how many candles this tick
                # should advance -- the depth half of the pulse; the
                # rate half is `_tick_delay`. Every fed candle still
                # steps the exchange and counts, so resting limits
                # sweep and the master clock stays authoritative.
                _feed = 1
                if self._load_feed_cb is not None:
                    try:
                        _feed = max(1, int(self._load_feed_cb()))
                    except Exception as _lfx:  # noqa: BLE001
                        logger.debug("load feed cb raised: %s", _lfx)
                        _feed = 1
                _exhausted = False
                for _f in range(_feed):
                    if not self._tape.step():
                        self._activity(f"All series exhausted at candle {candle_i}.")
                        _exhausted = True
                        break
                    candle_i += 1
                    self.progress.candles_played = candle_i
                    self.progress.candles_fed_under_load += 1 if _f > 0 else 0
                if _exhausted:
                    break
                if self._max_candles is not None and candle_i >= self._max_candles:
                    self._activity(
                        f"Reached max_candles={self._max_candles}; " "stopping."
                    )
                    break
                if self._tick_delay > 0:
                    await asyncio.sleep(self._tick_delay)
                else:
                    await self._maybe_yield()
                # Perf heartbeat, once per 500 candles.
                if candle_i % 500 == 0:
                    self._perf(
                        f"tick {candle_i}/{self.progress.total_candles}"
                        f" · {self.progress.trades_fired} sim trades"
                        f" · {self.progress.exceptions} exceptions"
                    )
                # Visual refresh signal for GUI widgets (gate lights,
                # price+VWAP chart), sent every N candles rather than
                # every candle. Callback set via set_visual_refresh_cb().
                if (
                    self._visual_refresh_cb is not None
                    and candle_i % self._visual_refresh_every == 0
                ):
                    try:
                        self._visual_refresh_cb(candle_i)
                    except Exception as _vr_exc:  # noqa: BLE001
                        logger.debug("visual_refresh_cb raised: %s", _vr_exc)
        finally:
            self.progress.finished = True
            # Emitted in `finally` so a run that died still reports
            # what it managed.
            try:
                from src.core.signal_contract import emit as _s2

                _p = self.progress
                # `expected` is what the run was asked to play, not
                # the whole tape: the loop stops at `_max_candles` by
                # design. `outcome` names which of the four loop exits
                # applied (operator stop, cap, exhausted tape,
                # exception), so a deliberate stop is never read as a
                # shortfall. `overran_the_ask` is reachable: the load
                # feed steps `_feed` candles before the cap is
                # re-checked.
                _asked = (
                    _p.total_candles
                    if self._max_candles is None
                    else min(_p.total_candles, self._max_candles)
                )
                if _p.stop_requested:
                    _outcome = "stopped_by_operator"
                    _cok = 0 <= _p.candles_played <= _asked
                elif _p.candles_played == _asked:
                    _outcome = "played_every_candle_asked"
                    _cok = True
                elif _p.candles_played > _asked:
                    _outcome = "overran_the_ask"
                    _cok = False
                else:
                    _outcome = "ended_before_the_ask"
                    _cok = False
                _s2(
                    "sim.06.001.postcondition.candles_stepped",
                    actual=_p.candles_played,
                    expected=_asked,
                    ok=_cok,
                    context={
                        "outcome": _outcome,
                        "stop_requested": bool(_p.stop_requested),
                        "skipped": _p.candles_skipped,
                        "anchored": bool(_p.anchored),
                        "total_candles": _p.total_candles,
                        "max_candles": self._max_candles,
                        "fed_under_load": _p.candles_fed_under_load,
                    },
                )
                # `bots_ticked` counts tick entries and the read-rate
                # throttle skips most of them by design, so `expected`
                # is derived from the worked/throttled/unknown split
                # rather than from the raw entry count; a tick that
                # disappears between the entry count and the
                # classifier drives expected above actual.
                _worked = _p.bot_ticks_worked
                _s2(
                    "sim.06.002.postcondition.bot_ticks_did_work",
                    actual=_worked,
                    expected=(
                        _p.bots_ticked - _p.bot_ticks_throttled - _p.bot_ticks_unknown
                    ),
                    context={
                        "entered": _p.bots_ticked,
                        "throttled": _p.bot_ticks_throttled,
                        "unknown": _p.bot_ticks_unknown,
                        "worked_pct": (
                            round(100.0 * _worked / _p.bots_ticked, 2)
                            if _p.bots_ticked
                            else 0.0
                        ),
                    },
                )
                # Per-bot TA coverage: observed / that bot's own
                # eligible candles, emitted per bot so one starved
                # symbol cannot hide inside a fleet average.
                #
                # Walks the UNION of `_ta_eligible` and `_ta_observed`
                # keys, not eligible alone: a bot with observations but
                # zero eligibility is the maximal bound violation and
                # must still get a record. A bot in neither map (a
                # tablet that starts after the window) gets no bound
                # and no fabricated green; it is counted instead in
                # `fleet_bots_with_no_record`.
                #
                # Identity the record count satisfies:
                # records == len(set(eligible) | set(observed)), and
                # len(self._bots) == bots_in_union +
                # fleet_bots_with_no_record. `bots_in_union` is carried
                # in every record so the count can be reconciled from
                # the log alone. `pct` is None, not 0.0, where there
                # is no eligibility to divide by.
                _ta_union = set(self._ta_eligible) | set(self._ta_observed)
                _ta_absent = len(self._bots) - len(_ta_union)
                for _bid in sorted(_ta_union):
                    _elig = self._ta_eligible.get(_bid, 0)
                    _obs = self._ta_observed.get(_bid, 0)
                    if _elig and _obs:
                        _ta_state = "eligible_and_observed"
                    elif _elig:
                        _ta_state = "eligible_not_yet_observed"
                    else:
                        _ta_state = "observed_without_eligibility"
                    _s2(
                        "ta.07.001.postcondition.coverage_per_bot",
                        actual=_obs,
                        expected=_elig,
                        ok=(_obs <= _elig),
                        context={
                            "bot_id": _bid,
                            "bound": "observed <= eligible",
                            "state": _ta_state,
                            "bots_in_union": len(_ta_union),
                            "fleet_bots_with_no_record": _ta_absent,
                            "pct": (round(100.0 * _obs / _elig, 2) if _elig else None),
                        },
                    )
                # Rolls the per-candle `ta.07.004.postcondition.raw.*`
                # records into one row per indicator, whose `ok`
                # answers whether any candle left the range that
                # indicator's own formula defines. Derived from the
                # sink's retained records rather than from counters
                # kept during the run, so the hot path stays free of
                # tallying state.
                try:
                    from src.core.signal_contract import get_sink as _gs

                    # The prefix is a named constant owned by the
                    # engine that emits it, so a rename cannot
                    # decouple this filter from what it is matching.
                    from src.trading.ta_engine import TA_RAW_PREFIX

                    _sink = _gs()
                    if _sink is not None:
                        _per: dict = {}
                        _firsts: dict = {}
                        for _r in _sink.records():
                            if not _r.name.startswith(TA_RAW_PREFIX):
                                continue
                            _ind = _r.name[len(TA_RAW_PREFIX) :]
                            _slot = _per.setdefault(
                                _ind, {"checked": 0, "violated": 0, "unchecked": 0}
                            )
                            if _r.ok is None:
                                _slot["unchecked"] += 1
                            elif _r.ok:
                                _slot["checked"] += 1
                            else:
                                _slot["checked"] += 1
                                _slot["violated"] += 1
                                if _ind not in _firsts:
                                    _c = _r.context or {}
                                    # The ADDRESS of the first breach,
                                    # so it can be reproduced from the
                                    # tablet without grepping the log.
                                    _firsts[_ind] = {
                                        "rule": _r.expected,
                                        "symbol": _c.get("symbol"),
                                        "candle_ts": _c.get("candle_ts"),
                                        "window": _c.get("window"),
                                    }
                        _viol = sum(v["violated"] for v in _per.values())
                        _s2(
                            "ta.07.002.invariant.invariants",
                            actual=_viol,
                            expected=0,
                            context={
                                "per_indicator": _per,
                                "first_violations": _firsts,
                                "indicators": len(_per),
                            },
                        )
                except Exception as _inv_exc:  # noqa: BLE001
                    logger.debug("invariant rollup failed: %s", _inv_exc)
                # Causality accounting: on a staggered fleet these
                # skips are expected, so the useful signal is the
                # count and share, not a pass/fail.
                _s2(
                    "sim.06.003.counter.ticks_before_tape",
                    actual=_p.bot_ticks_before_tape,
                    context={
                        "ticked": _p.bots_ticked,
                        "pct_of_attempted": (
                            round(
                                100.0
                                * _p.bot_ticks_before_tape
                                / (_p.bot_ticks_before_tape + _p.bots_ticked),
                                2,
                            )
                            if (_p.bot_ticks_before_tape + _p.bots_ticked)
                            else 0.0
                        ),
                    },
                )
                _s2("sim.06.004.counter.trades_fired", actual=_p.trades_fired)
                _s2("sim.06.005.invariant.exceptions", actual=_p.exceptions, expected=0)
                # Window actually played -- a run that cannot say what
                # data it consumed cannot be re-checked. Reads
                # TabletBackend.clock_window() directly rather than a
                # getattr-with-default on an attribute the connector
                # does not carry.
                _first = _last = None
                try:
                    if self._tape is not None:
                        _first, _last = self._tape.clock_window()
                except Exception as _wx:  # noqa: BLE001
                    logger.debug("window read failed: %s", _wx)
                _s2(
                    "sim.06.006.event.window_played",
                    actual={
                        "first_ts": _first,
                        "last_ts": _last,
                        "symbols": len(self._candles_by_symbol or {}),
                    },
                )
            except Exception as _s2x:  # noqa: BLE001 - never break teardown
                logger.debug("S2 emit failed: %s", _s2x)

            # Sink flushed and cleared last, so every emitter above
            # runs while it is still installed.
            try:
                from src.core.signal_contract import set_sink as _clr

                if self._signal_sink is not None:
                    self._signal_sink.flush()
                # Restores the prior sink rather than clearing to
                # None, so process-wide collection survives a replay.
                _clr(getattr(self, "_prior_sink", None))
            except Exception as _sfx:  # noqa: BLE001 - advisory
                logger.debug("signal sink teardown failed: %s", _sfx)
            self._perf(
                f"Fleet Replay finished: {self.progress.candles_played}"
                f" candles, {self.progress.trades_fired} sim trades, "
                f"{self.progress.exceptions} exceptions."
            )
            # Closes the run record before the telemetry/report block
            # below, so a failure in reporting cannot cost the run's
            # data.
            if self._run_log is not None:
                try:
                    _el = 0.0
                    try:
                        _el = max(
                            0.0,
                            time.time() - float(self.progress.started_at_wall or 0.0),
                        )
                    except (TypeError, ValueError) as _el_exc:
                        logger.debug("elapsed calc: %s", _el_exc)
                    self._run_log.finish_run(
                        summary={
                            "candles_played": self.progress.candles_played,
                            "total_candles": self.progress.total_candles,
                            "trades_fired": self.progress.trades_fired,
                            "bots": len(self._bots),
                            "exceptions": self.progress.exceptions,
                            "stop_requested": self.progress.stop_requested,
                            "elapsed_s": round(_el, 2),
                            "candles_per_s": (
                                round(self.progress.candles_played / _el, 2)
                                if _el > 0
                                else None
                            ),
                            "trades_per_1k_candles": (
                                round(
                                    1000.0
                                    * self.progress.trades_fired
                                    / self.progress.candles_played,
                                    2,
                                )
                                if self.progress.candles_played
                                else None
                            ),
                            "visuals_attached": bool(
                                self._visual_refresh_cb is not None
                            ),
                            # yields_per_candle bounds candles/s under
                            # the GUI's pump.
                            "candles_skipped": self.progress.candles_skipped,
                            "bots_ticked": self.progress.bots_ticked,
                            "yields_emitted": self.progress.yields_emitted,
                            "yields_per_candle": (
                                round(
                                    self.progress.yields_emitted
                                    / self.progress.candles_played,
                                    4,
                                )
                                if self.progress.candles_played
                                else None
                            ),
                        }
                    )
                    _d = self._run_log.directory
                    self._perf(
                        f"Sim run persisted: {self._run_log.trade_count}"
                        f" trades, {self._run_log.gate_count} gates -> "
                        f"{_d if _d else '(not written)'}"
                    )
                    # Reported unconditionally, including a pass that
                    # removed nothing, so retention stays observable
                    # rather than silent between runs.
                    _ret = getattr(self._run_log, "retention", None)
                    if _ret is not None:
                        self._perf(_ret.summary())
                except Exception as _rl_exc:  # noqa: BLE001 - advisory
                    logger.warning("sim run log close failed: %s", _rl_exc)
            # Names any declared Simulator feature that never ran this
            # replay, and persists so a feature that goes silent
            # shows up as stalled on the next run.
            try:
                from src.core.feature_telemetry import get_telemetry

                _tel = get_telemetry()
                for _line in _tel.report_lines(scope="sim."):
                    self._perf(_line)
                _tel.save()
                # Written to ~/.acervator_logs/feature_validation.md so
                # it is readable next session without re-running.
                _md = _tel.write_markdown_report(
                    scope="sim.",
                    run_context={
                        "Candles played": (
                            f"{self.progress.candles_played:,} / "
                            f"{self.progress.total_candles:,}"
                        ),
                        "Sim trades": f"{self.progress.trades_fired:,}",
                        "Bots": f"{len(self._bots)}",
                        "Tick exceptions": (f"{self.progress.exceptions:,}"),
                    },
                )
                if _md is not None:
                    self._perf(f"Feature validation report: {_md}")
            except Exception as _tel_exc:  # noqa: BLE001 - advisory
                logger.debug("feature telemetry report failed: %s", _tel_exc)
            self.stopped_event.set()


__all__ = ["FleetReplayController", "ReplayProgress"]


def clock_timestamps_from_candles(
    candles_by_symbol: dict,
) -> list[int]:
    """The master clock's index space, derived from raw candle rows.

    Must stay bit-identical to ``MasterClock.from_series`` -- sorted
    union of every series's timestamps -- since this is the space
    anchor indices are compared against at run time. Pinned against it
    by ``tests/test_fleet_replay_anchors.py``.

    Exists because the panel builds anchors before ``start()`` calls
    ``_build_sim()``, before any exchange or clock exists; the panel
    already holds the raw ``candles`` dict, so the union is derivable
    there.
    """
    union: set[int] = set()
    for rows in (candles_by_symbol or {}).values():
        if not rows:
            continue
        for row in rows:
            try:
                union.add(int(row[0]))
            except (TypeError, ValueError, IndexError):
                continue
    return sorted(union)


def build_anchor_indices(
    trade_timestamps: list[float],
    base_ts_ms: int,
    n_candles: int,
    step_ms: int = 300_000,
    warmup: int = 100,
    clock_ts_ms: Optional[list[int]] = None,
) -> set[int]:
    """Candle indices the read head must actually evaluate.

    For each historical trade, includes the candle containing it plus
    the preceding ``warmup`` candles: a bot evaluated on a cold TA
    window would diverge from live for reasons unrelated to strategy.
    Overlapping warm-up ranges collapse naturally, since this is a
    set, so clustered trades cost far less than warmup × trade_count.
    Returns an empty set when there are no trades.

    Pass ``clock_ts_ms`` for exact results: the run loop compares
    these positions against ``candle_i``, the MasterClock cursor --
    an index into ``sorted(union_of_every_series_timestamp)``, not a
    slot number on a fixed-interval ruler. The two spaces agree only
    while the union is gapless; a missing slot shifts every later
    candle one position earlier under the ruler arithmetic.

    Without ``clock_ts_ms`` (``None``), falls back to the ruler
    arithmetic ``idx = int((ts * 1000.0 - base_ts_ms) // step_ms)``,
    exact only on a gapless union; used by
    ``tests/test_fleet_replay_controller.py``.
    """
    anchors: set[int] = set()
    warm = max(0, int(warmup))

    if clock_ts_ms:
        # Exact. bisect_right - 1 gives the candle CONTAINING the trade
        # (a trade exactly at a candle's open belongs to that candle),
        # matching the floor-division semantics of the grid path.
        bound = len(clock_ts_ms)
        if n_candles > 0:
            bound = min(bound, int(n_candles))
        for ts in trade_timestamps or []:
            try:
                t_ms = int(float(ts) * 1000.0)
            except (TypeError, ValueError):
                continue
            idx = bisect_right(clock_ts_ms, t_ms) - 1
            if idx < 0 or idx >= bound:
                continue
            anchors.update(range(max(0, idx - warm), idx + 1))
        return anchors

    if n_candles <= 0 or step_ms <= 0:
        return anchors
    for ts in trade_timestamps or []:
        try:
            idx = int((float(ts) * 1000.0 - base_ts_ms) // step_ms)
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        if idx < 0 or idx >= n_candles:
            continue
        anchors.update(range(max(0, idx - warm), idx + 1))
    return anchors
