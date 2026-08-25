"""fleet_replay_controller.py — async orchestrator for Fleet Replay.

v3.23.79-A. Feeds YTD candle data through the exchange the bots hold
while ticking each ScrummingBot instance built from bot_state.json
configs. Since v3.24.84 that exchange is a real ``CCXTConnector`` served
by ``TabletBackend``; before it, ``FleetSimExchange``.
Deferred from v3.23.72 per operator direction to ship the panel MVP
first + add the tick loop after the API-optimization detour.

Contract:
    ctrl = FleetReplayController(
        configs,                    # list[dict] from bot_state_loader
        candles_by_symbol,          # {symbol: rows}  — YTD candle window
        activity_log_cb=..,         # str → None (Simulator Activity Log)
        performance_log_cb=..,      # str → None (Simulator Performance Log)
    )
    await ctrl.start()   # spawns tick task, returns immediately
    ctrl.request_stop()  # cooperative shutdown
    await ctrl.stopped_event.wait()   # optional: block until fully stopped

Per-tick loop:
    1. Advance the TabletBackend cursor one candle across all symbols.
    2. For each bot: call bot.tick() (real class code, unmodified).
    3. Update progress state (candles played, per-bot trades, etc.).
    4. Repeat until every series exhausts OR request_stop() fires.

Speed control: ``tick_delay_s`` gates the sleep between ticks. 0.0
= wall-clock speed (as fast as possible); operator can bump for
observability.

sadp: R28 SSS + R70 RCN
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

Under the GUI each yield costs a full 50 ms QTimer period (see
``FleetReplayController._maybe_yield``), so yields must be rate-limited by
time rather than by candle or bot count. At 20 ms the GUI still gets a
slot ~50x/second — far more than a repaint needs — while the replay stops
paying a pump period per bot.
"""
from typing import TYPE_CHECKING, Any, Callable, Optional

from src.exchange.ccxt_connector import CCXTConnector
from src.exchange.tablet_backend import TabletBackend
from .sim_exchange import make_symbol_series_map

if TYPE_CHECKING:
    # Annotation only -- see `_instantiate_bot`. Guarded so the module
    # takes on no import it does not need at run time; the annotations
    # are strings already, under `from __future__ import annotations`.
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
    # v3.24.15 — candles fast-skipped in anchored mode. Non-zero
    # means the run is a SCREENING pass, not authoritative parity.
    candles_skipped: int = 0
    # v3.24.20 — how many times the replay loop actually yielded to the
    # event loop. Under the GUI pump each yield costs ~50 ms, so this
    # divided by candles_played is the single number that predicts
    # throughput. It is recorded so the next regression is measurable
    # instead of being re-derived from run timestamps.
    yields_emitted: int = 0
    anchored: bool = False
    started_at_wall: float = 0.0
    finished: bool = False
    stop_requested: bool = False
    last_error: Optional[str] = None
    # v3.23.80 — first-N distinct exception types seen. When every
    # bot tick fails with the same root cause (e.g. missing event
    # bus wiring), this collapses 7000 identical errors into "one
    # AttributeError: bus" so the operator sees the actual problem.
    exception_samples: dict[str, int] = field(default_factory=dict)
    per_bot_trade_count: dict[str, int] = field(default_factory=dict)
    # v3.24.0 — symbol-keyed trade counter. Simpler than the
    # bot_id path (each symbol has one bot in the fleet) and lets
    # the panel's Sim Trades column refresh by iterating table
    # rows and reading counts by symbol. The v3.23.80-era
    # per_bot_trade_count was never populated because trade.raw
    # never contained bot_id — a scaffolding pattern S001 would
    # catch (getattr fallback with no writer).
    per_symbol_trade_count: dict[str, int] = field(default_factory=dict)
    # Ticks SKIPPED because the symbol's tablet had not begun.
    # Counted rather than silently dropped: a skip that leaves no
    # trace is indistinguishable from a bot that never ran.
    bot_ticks_before_tape: int = 0
    # v3.24.81 (S2) — `bots_ticked` counts tick ENTRIES and cannot tell a
    # bot that worked from one that returned immediately. These split it.
    bot_ticks_worked: int = 0
    bot_ticks_throttled: int = 0
    bot_ticks_unknown: int = 0
    # v3.24.83 - candles advanced BEYOND the first on a tick,
    # i.e. the extra depth Nuclear's load pulse drove.
    candles_fed_under_load: int = 0


SIM_ID_PREFIX = "simulated_"
"""Operator directive 2026-08-08: bot ids import to the Simulator as
`simulated_(bot id)`, which "marries a live bot with its simulated
equivalent."

Two properties at once. The record is SELF-IDENTIFYING -- a sim row can
never be mistaken for a live one, in a log or in a swarm. And it stays
JOINABLE -- strip the prefix and you have the live bot_id, so a sim
result can be set beside its live counterpart.

A bare uuid4 (what the sim used before v3.24.71) has neither property.
A bare live id has the second but not the first.
"""


def sim_bot_id(live_bot_id: str) -> str:
    """`simulated_<live id>`. Idempotent: prefixing twice is a bug that
    would silently break the wire join, so it is refused here."""
    _s = str(live_bot_id or "")
    return _s if _s.startswith(SIM_ID_PREFIX) else SIM_ID_PREFIX + _s


def live_bot_id(sim_id: str) -> str:
    """Inverse of `sim_bot_id` -- the join back to bot_state."""
    _s = str(sim_id or "")
    return _s[len(SIM_ID_PREFIX):] if _s.startswith(SIM_ID_PREFIX) else _s


def _make_sim_capital_registry():
    """A private, non-persisting capital-reservation registry.

    v3.24.31 — operator directive 2026-08-05: sim bots must be
    "simulator equivalents with all of the same functionality except
    that operate in a simulated environment."

    Reservation used to be SKIPPED in sim, which removes the feature
    instead of simulating it. It was skipped because the registry is a
    process-wide singleton that PERSISTS to
    ~/.acervator/reservation_state.json — live capital state — so a sim
    fleet sharing it either corrupted live reservations or had its own
    sells refused by live bots' claims.

    ``autosave=False`` plus a temp state path gives the real code path
    a sim-only backend: reservations are made, checked and released for
    real, and nothing reaches the operator's runtime tree.
    """
    try:
        import tempfile
        from pathlib import Path as _P
        from src.trading.capital_reservation import (
            CapitalReservationRegistry)
        tmp = _P(tempfile.mkdtemp(prefix="acervator-sim-crr-"))
        return CapitalReservationRegistry(
            state_path=tmp / "reservation_state.json", autosave=False)
    except Exception as exc:
        # v3.24.35 (CV1) — FAIL CLOSED. This previously logged a warning
        # and returned None, and the comment said what that meant:
        # "falling back to None means the bot resolves the global
        # singleton, which is the pre-v3.24.31 behaviour."
        #
        # ScrummingBot._crr resolves the process-wide registry when it
        # receives None, and that registry autosaves to
        # ~/.acervator/reservation_state.json. So one tempfile.mkdtemp
        # failure silently reinstated the exact defect v3.24.31 removed,
        # whose cost is recorded at scrumming_bot.py:1053-1063 — 16,558
        # bot_ids against 35 real ones, 16,523 orphans, 6.5 MB of sim
        # residue feeding live allocation decisions.
        #
        # Method rule M10: a sim path that cannot obtain its private
        # registry ABORTS with an operator-visible reason. Losing a
        # replay is cheap; corrupting live reservation state is not.
        logger.error(
            "sim capital registry could not be created (%s) — aborting "
            "rather than resolving the process-wide registry", exc)
        raise RuntimeError(
            f"sim capital-registry isolation failed: {exc}. Refusing to "
            f"fall back to the process-wide registry, which autosaves "
            f"into the operator's runtime tree."
        ) from exc


def resolve_phantoms_enabled(cfg: dict, force: bool = False) -> bool:
    """Whether this bot's phantoms run in a replay.

    v3.24.64 (C18 / SN-57). The controller hardcoded
    ``enable_phantoms=True``, so every replay ran a configuration NONE
    of the operator's bots use — all 35 record ``phantoms_enabled``
    False — and any parity claim about SCRUM/FOLD decisions was
    comparing against a fleet that does not exist.

    The plan states the opposite (that a replay may construct zero
    phantoms). It had the direction backwards; the sim was forcing them
    on, not off.

    ``phantoms_enabled`` is an ENTRY-level key, a sibling of ``config``
    — it is absent from ``config`` on all 35 bots, so a lookup inside
    the config dict finds nothing. Both shapes are accepted here so a
    hand-built config in a test behaves the same way.

    ``force`` is the per-run panel toggle. It can only turn phantoms ON,
    never off: an override that can disable would be a second way to get
    a phantom-less replay that looks configured, and C17/C46's phantom
    changes would be "verified" by a run in which ``_tick`` never ran.
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
    # Default OFF: faithful to live, where 35/35 are False.
    return False


def _instantiate_bot(
    cfg: dict, exchange: ExchangeInterface,
    capital_registry: Optional[Any] = None,
) -> Optional[Any]:
    """Build a ScrummingBot from a bot_state.json config against the
    exchange it will trade on. Uses ``make_bot_config`` for mode-shape
    validation.

    ``exchange`` carried a ``FleetSimExchange`` annotation until issue
    #109. It stopped being true in v3.24.84, when ``_build_sim`` began
    passing a real ``CCXTConnector`` served by ``TabletBackend`` — the
    same version that stopped the Simulator trading. Both mypy and
    pyright reported the mismatch as soon as a test passed the real
    argument, which is one reason no test did.

    ``ExchangeInterface`` rather than ``CCXTConnector``: it is what this
    function actually needs (``exchange_id``) and what the consumer
    declares (``ScrummingBot.__init__``), and it accepts BOTH the
    connector ``_build_sim`` passes today and the ``FleetSimExchange``
    the older callers still pass. Naming one concrete class would only
    move the lie to the other caller.

    Returns None (with a logged warning) on any construction error;
    the caller skips that bot and continues.
    """
    # v3.24.54 (C15 step 3) — refuse BEFORE constructing anything.
    #
    # `capital_registry` defaults to None and the bot was built anyway.
    # A ScrummingBot with no injected registry resolves the
    # process-wide one, which autosaves to the operator's
    # ~/.acervator/reservation_state.json. The factory raising (CV1)
    # only protects callers that ASK for a registry; this protects the
    # ones that forget to.
    #
    # First statement in the function on purpose: after this point the
    # blanket `except` below would turn a missing registry into an
    # ordinary construction failure and hide it among the others.
    if capital_registry is None:
        logger.warning(
            "FleetReplayController: refusing to construct sim bot %s — "
            "no capital registry was injected, and a sim bot without one "
            "resolves the process-wide registry that persists to the "
            "operator's reservation_state.json.",
            str(cfg.get("bot_id", "?")) if isinstance(cfg, dict) else "?")
        return None
    try:
        from src.trading.bot_container import make_bot_config, BotMode
        from src.trading.scrumming_bot import ScrummingBot
    except Exception as _imp_exc:
        logger.warning(
            "FleetReplayController: bot imports failed: %s", _imp_exc)
        return None

    if cfg.get("mode", "").lower() != "scrumming":
        return None

    try:
        # v3.24.32 — pass EVERY BotConfig field through.
        #
        # This hand-enumerated 26 kwargs, silently defaulting the other
        # 44. The one that mattered most: `trading_fee_pct` is 1.6 on
        # 24 of 35 live bots and 0.6 on 11, but the sim always got the
        # 0.6 default. That value is the Minimum Opposing Trade Distance
        # term (scrumming_bot.py:10019-10023), so LIVE required a 6.6%
        # reversal to fire while SIM required 5.6% — the sim traded more
        # freely than live for the whole replay.
        #
        # Also silently defaulted: max_cartridge_smart (True on 12
        # bots), max_cartridge_size_pct (5.0 on 6), hedge_balance (0.0
        # on 33), every circuit_breaker_*, position_ceiling_*,
        # detonation_*, self_reserve_capital, personal_hold_qty,
        # wire_inflow_stack_pct. Those sit at defaults in TODAY's fleet,
        # so the whitelist looked correct — until the operator tunes one.
        #
        # Verified: all 70 BotConfig fields exist in bot_state; the only
        # extra key is the loader's own `_src_bot_id`.
        # Mode-foreign fields are excluded using bot_container's OWN
        # exclusion set rather than a local list, so the two cannot
        # drift. bot_state carries all 70 BotConfig fields including
        # the 15 Extractor-only ones (at defaults), and make_bot_config
        # correctly refuses those on a scrumming config — passing them
        # would store nonsense that leaks into display and persistence.
        import dataclasses as _dc

        from src.trading.bot_container import (
            _BOT_CONFIG_EXTRACTOR_ONLY_FIELDS as _EXTRACTOR_ONLY,
        )
        from src.trading.bot_container import BotConfig as _BC

        _fields = {f.name for f in _dc.fields(_BC)}
        passthrough = {
            k: v for k, v in cfg.items()
            if k in _fields
            and k not in ("mode", "exchange_id")
            and k not in _EXTRACTOR_ONLY
        }
        # v3.24.64 (C18 / SN-58) — carry the REAL venue.
        #
        # This used to write `exchange.exchange_id` ("fleet_sim") over
        # the venue already present in the config. `timeframes.py` is
        # keyed by lowercase venue id with a PERMISSIVE unknown-key
        # fallback, so "fleet_sim" did not select a sim timeframe set —
        # it disabled the availability filter entirely, making a 4h
        # phantom creatable for a Coinbase-sourced bot that cannot have
        # one.
        #
        # The counterparty is still the sim exchange; that is decided by
        # WHICH exchange object the bot is handed, not by this string.
        # The string's only job is to answer "what does this venue
        # offer", and for that the truthful answer is the real one.
        #
        # NOT solved by adding a `fleet_sim` key to timeframes.py: that
        # is a sim identifier in a live table (M9), and it would
        # silently apply Coinbase's set to a future Kraken fleet.
        #
        # HAZARD: this makes the sim's MarketDataPool key
        # ({exchange_id}|{symbol}|{timeframe}) identical to live's. Safe
        # only because no simulator path reaches get_data_pool() —
        # `set_data_pool` has one caller, on the live manager, so a sim
        # BotManager keeps `_data_pool = None`. Pinned by
        # tests/test_sim_ta_input_fidelity.py.
        # Falls back to the sim exchange's id when the config carries no
        # venue. Hand-built configs (tests, ad-hoc runs) omit it, and
        # `BotConfig` has no default for it — leaving the key unset made
        # every such bot fail construction and the replay report "0
        # bots", which is exactly the silent-skip failure the whitelist
        # comment below warns about.
        _real_venue = str(cfg.get("exchange_id") or "").strip()
        passthrough["exchange_id"] = _real_venue or exchange.exchange_id
        # BotConfig has three fields with NO default; a config that
        # omits them cannot be constructed. Real bot_state entries carry
        # all 70, but hand-built configs (tests, ad-hoc runs) need the
        # same defaults the previous whitelist supplied — otherwise
        # every such bot silently fails to build and the replay reports
        # "0 bots" with the reason only in a debug log.
        passthrough.setdefault("base_currency", "USD")
        passthrough.setdefault("target_asset", "BTC")
        _dropped = sorted(
            k for k in cfg
            if k not in _fields and not k.startswith("_"))
        if _dropped:
            logger.debug(
                "sim bot %s: %d bot_state key(s) are not BotConfig "
                "fields and were not passed: %s",
                cfg.get("symbol", "?"), len(_dropped), _dropped)

        bot_config = make_bot_config(
            BotMode.SCRUMMING, **passthrough)
        # v3.24.1 — sim_mode=True suppresses TRADE NOTIFICATION
        # bus emits so main_window's sound-engine handler stays
        # silent during Fleet Replay (scaffolding scan finding #3).
        # v3.24.31 — phantoms ENABLED and a private capital registry
        # injected. enable_phantoms=False removed the subsystem from
        # sim entirely; the operator's directive is that sim bots carry
        # the same functionality, isolated. Phantom balance is
        # per-bot in-memory state, so enabling it needs no external
        # isolation — it was simply switched off.
        # C18 / SN-57 — derived from the persisted per-bot flag, not
        # hardcoded. See resolve_phantoms_enabled.
        return ScrummingBot(
            bot_config, exchange,
            enable_phantoms=resolve_phantoms_enabled(cfg),
            sim_mode=True, capital_registry=capital_registry)
    except Exception as _cfg_exc:  # noqa: BLE001 - construction guard
        logger.warning(
            "FleetReplayController: skip %s config (build failed: %s)",
            cfg.get("symbol", "?"), _cfg_exc)
        return None


# ccxt OHLCV column order is [ts, open, high, low, close, volume], so
# the close a bot reads through `fetch_ticker` sits at index 4
# (tablet_backend.py:403). Named rather than written as a literal
# because `opening_lot_for_lotless` both indexes it and length-checks
# the row against it, and two spellings of one column would drift.
OHLCV_CLOSE = 4


def _positive_finite(value: object) -> Optional[float]:
    """Return *value* as a positive finite float, or None.

    One gate for the two readings `opening_lot_for_lotless` takes off
    caller-shaped data, so a target and a price are judged by the same
    rule rather than by two hand-copies of it. A config value comes out
    of JSON, so the accepted types are the ones JSON can hold; anything
    else is refused rather than coerced, and a string that does not
    parse is refused too.
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


def opening_lot_for_lotless(
        target_balance: object, rows: list[list]) -> Optional[dict]:
    """Return the one lot a bot with NO bot_state opens locked with.

    Issue #111 violation B. Operator ruling: "locked and spendable start
    equal". `_build_sim` seeds the quote leg at `target_balance`, so the
    base leg opens at the units that same money buys at the tape's own
    opening price -- `target_balance / price`. Valued at that price the
    two sides are the SAME NUMBER, which is the ruling stated literally.

    WHY A BOT NEEDS ONE. A bot that opens FLAT must buy its whole target
    before it can do anything else, and that costs `target x (1 + fee)`.
    The wallet seed is `sum(target_balance)` exactly, so N targets cannot
    fund N such acquisitions: the last bot is always short by the fees
    the earlier ones paid. Measured on a 400-candle synthetic tape,
    closing USD 100.00 / 99.40 / 98.80 at fleet sizes 1 / 2 / 3 -- the
    0.6% fee exactly. At size 1 the only bot IS the starved one, so it
    fired nothing at all. Whether a bot could trade depended on how many
    OTHER bots existed. Live has no such coupling, and Live, Paper and
    Sim may differ only in where market data comes from.

    THE PRICE IS THE TAPE'S FIRST CLOSE, not a separate opinion about
    the opening price. `TabletBackend` starts every cursor at 0
    (tablet_backend.py:115) and `fetch_ticker` serves `rows[-1][4]` of
    the visible slice (:404), so at the opening tick the bot reads this
    exact figure from the venue.

    Returns None -- open flat, unchanged -- when there is no target, no
    tape, or no usable price. A lot with a zero or non-finite basis
    "claims infinite profit against every price and can arm a sell that
    never should have armed" (`_book_reconciliation_lot`,
    scrumming_bot.py:11948); refusing to write one is that same rule.

    The lot shape is the documented one, `{units, initial_buy_price}`
    (scrumming_bot.py:692), carrying the `operator_initiated` flag both
    live lot writers set (scrumming_bot.py:3774 and :11983).
    """
    target = _positive_finite(target_balance)
    first = rows[0] if rows else []
    price = (_positive_finite(first[OHLCV_CLOSE])
             if len(first) > OHLCV_CLOSE else None)
    if target is None or price is None:
        return None
    units = _positive_finite(target / price)
    if units is None:
        return None
    return {"units": units,
            "initial_buy_price": price,
            "operator_initiated": False}


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
        # v3.24.72 (C20) — bot_state's top-level `smart_wires`, passed
        # in rather than read here so the controller stays free of file
        # IO and remains constructible in a test without a bot_state.
        self._smart_wires = list(smart_wires or [])
        # v3.24.80 — symbol -> LIVE bot id, for attributing sim fills.
        # Populated in _build_sim once the bots exist. The exchange
        # reports a fill by symbol and does not know the bot, and each
        # sim bot owns exactly one symbol, so this is the join.
        self._bot_id_for_symbol: dict = {}
        # v3.24.82 - per-bot TA observation coverage. Per BOT because
        # a fleet-wide ratio is meaningless when tablets start on
        # different dates.
        self._ta_observed: dict = {}
        self._signal_sink = None
        # Set by Nuclear to drive candles-per-tick. None = 1.
        self._load_feed_cb = None
        self._ta_eligible: dict = {}
        # Built in _build_sim, and ONLY for a fleet that can join to
        # bot_state. Owns a private EventBus — see the construction
        # site for why a None bus is not an option.
        self._smart_wire_mgr: Optional[Any] = None
        self._sim_bus: Optional[Any] = None
        self._candles_by_symbol = dict(candles_by_symbol or {})
        self._activity = activity_log_cb or (lambda _m: None)
        self._perf = performance_log_cb or (lambda _m: None)
        self._tick_delay = float(tick_delay_s)
        self._max_candles = max_candles
        # v3.24.7 — YTD window bounds. When set, the sim plays only
        # candles whose ts falls within [window_since_ms, window_until_ms]
        # so the operator's non-correlating-error signal is meaningful
        # (comparing sim vs live over the SAME window). Operator
        # directive 2026-08-02: "the Simulator only plays the
        # sections of the Stone Tablets that align with the user's
        # YTD data so that the Simulator itself knows when it should
        # expect validating trade action logic from the gates."
        self._window_since_ms = window_since_ms
        self._window_until_ms = window_until_ms
        # The connector the BOTS hold — a real CCXTConnector, served
        # by the tape. Typed loosely because the Simulator no longer
        # cares which concrete exchange class it is; that is the point.
        self._exchange: Optional[Any] = None
        # The replay control surface: clock, cursors, ledger seeding.
        # Assigned in `_build_sim`, so it is declared here — a method
        # that reads it before a run is built would otherwise raise
        # AttributeError rather than degrade.
        self._tape: Optional[TabletBackend] = None
        self._bots: list[Any] = []
        self._task: Optional[asyncio.Task] = None
        # v3.24.13 — durable per-run record under ~/.acervator_logs/sim/.
        # Created in start(), closed in the run loop's finally block.
        self._run_log: Optional[Any] = None
        # v3.24.15 — anchored screening mode. None = evaluate every
        # candle (authoritative). A set of candle indices = evaluate
        # only those; see the run loop for the correctness costs.
        self._anchor_indices: Optional[set[int]] = None
        # v3.24.29 — candles where a HISTORICAL trade is expected.
        #
        # Separate from _anchor_indices on purpose. _anchor_indices
        # controls SKIPPING and is None in full-evaluation mode, but
        # trade markers need "was a trade expected here?" in BOTH modes
        # — otherwise every marker in a full-evaluation run would paint
        # red for lack of a reference set.
        self._expected_indices: Optional[set[int]] = None
        self._candle_i: int = 0
        # Markers produced by the worker, drained by the GUI thread.
        # Never touch Qt from here; v3.24.19 removed exactly that.
        self._pending_markers: list[tuple[str, bool]] = []
        self.progress = ReplayProgress()
        self.stopped_event = asyncio.Event()
        self.stopped_event.set()  # not-yet-started = "already stopped"
        # v3.24.3 — visual refresh callback + cadence. Panel wires
        # this after construction via set_visual_refresh_cb(). The
        # controller's _run() calls it every N candles to keep GUI
        # updates bounded (19,680 tick replay → ~200 UI updates).
        self._visual_refresh_cb: Optional[Callable[[int], None]] = None
        # Set again at start(); initialised here so _maybe_yield is safe
        # if anything calls it before the run loop begins.
        self._last_yield: float = time.perf_counter()
        self._visual_refresh_every: int = 100

    # ── Public API ───────────────────────────────────────────────
    async def start(self) -> bool:
        """Build exchange + bots + launch the tick task. Returns
        immediately; use stopped_event to await completion.

        Returns True when a tick task was launched, False on refusal.

        v3.24.74 (C23 step 4) — REFUSAL MUST BE OBSERVABLE.

        This returned None on every path, so a caller could not tell a
        launched run from a refused one. `stopped_event` is created SET
        at :403-404 ("not-yet-started = already stopped") and only
        cleared BELOW both refusals, while `progress.finished` stayed
        False. A caller waiting the obvious way —

            while not ctl.progress.finished:
                await asyncio.wait_for(ctl.stopped_event.wait(), 0.5)

        — awaited an ALREADY-SET Event, which completes without ever
        suspending. The `timeout=0.5` never fires because nothing times
        out, so that loop never yields. Measured on a refused start:
        477,043 iterations in one second with a competing coroutine
        advancing ZERO. Not a busy poll — total starvation.

        `main.py:1085-1092` pumps ONE asyncio loop from the Qt GUI
        thread, shared by every live coroutine, so a non-suspending
        coroutine freezes the GUI and live trading together. The
        `timeout=0.5` reading like a mitigation is what made this
        survive review.

        THE TWO REFUSALS ARE NOT SYMMETRIC — see below.
        """
        if self._task is not None and not self._task.done():
            # DELIBERATELY does not touch `progress`. Another replay is
            # in flight and OWNS it; marking it finished would tell
            # `fleet_replay_panel.py:1532` to stop the progress timer and
            # drain the final frame for a run that is still going, and
            # `_run_in_flight` at :487 (which reads `not finished`) would
            # let Reset silently discard it.
            self._activity("Controller already running.")
            return False
        # Sink FIRST. `_build_sim` emits
        # fleet.03.001.postcondition.bots_loaded,
        # fleet.03.005.invariant.state_parity,
        # fleet.03.003.invariant.sections_imported and the rest, so
        # installing after it captured none of them. Opened with NO path
        # because the run directory does not exist yet; records buffer in
        # memory and the path is attached below once SimRunLog opens it.
        try:
            from src.core.signal_contract import (
                SignalSink, get_sink, set_sink)
            # v3.24.88 - remember what was collecting before this run.
            # The process-level sink installed at startup must survive
            # a replay; clearing to None at teardown used to end live
            # collection for the rest of the session.
            self._prior_sink = get_sink()
            self._signal_sink = SignalSink()
            set_sink(self._signal_sink)
        except Exception as _ssx:  # noqa: BLE001 - advisory
            logger.debug("signal sink install failed: %s", _ssx)
        self._build_sim()
        if self._exchange is None or not self._bots:
            self._activity(
                "Cannot start: no bots instantiated. "
                "(Loaded configs OR candle series missing.)")
            # Nothing was launched and nothing else owns this progress,
            # so close it out: a waiter must have an exit condition.
            # `stopped_event` is already set from :404, which is correct
            # here — "never started" is a legitimate "stopped".
            self.progress.finished = True
            return False
        self.progress = ReplayProgress(
            total_candles=self._total_candle_count(),
            per_bot_trade_count={
                str(getattr(b, "bot_id", i)): 0
                for i, b in enumerate(self._bots)},
        )
        self.stopped_event.clear()
        self.progress.started_at_wall = time.time()
        self._last_yield = time.perf_counter()

        # v3.24.13 — open the durable run record and hook each sim
        # bot's PRIVATE bus for gate decisions. Subscribing here is
        # safe precisely because v3.24.12 isolated those buses: these
        # handlers cannot see live events, and live subscribers
        # cannot see these.
        try:
            from src.trading.sim_run_log import SimRunLog
            self._run_log = SimRunLog()
            # ── INSTALL THE SIGNAL SINK ───────────────────────────
            # v3.24.83. Every emitter built for this cascade calls
            # `signal_contract.emit`, which is a no-op when no sink is
            # installed. `set_sink` had ZERO production callers, so in a
            # real run all of them fired into nothing: the Console
            # signals pane stayed empty and no JSONL was written. The
            # mechanism existed, its tests passed, and it was inert
            # exactly where it mattered — the same defect class this
            # cascade keeps finding, this time in the instrumentation.
            #
            # Scoped to the RUN, not the process: opened here beside the
            # run log and cleared in the same `finally` that closes it,
            # so signals land next to the trades and gates they explain
            # and a finished run cannot keep collecting.
            self._run_log.start_run(config={
                "bots": len(self._bots),
                "symbols": sorted(self._candles_by_symbol.keys()),
                "total_candles": self.progress.total_candles,
                "max_candles": self._max_candles,
                # v3.24.29 — record the EVALUATION MODE.
                #
                # Two runs over the same 15,211 candles produced 517 vs
                # 510 trades, and neither meta.json said which mode it
                # ran in, so the runs could not be told apart from their
                # own logs. The mode is the single most important thing
                # about a run: anchored skips bot.tick() on candles with
                # no expected trade, so per-tick state (holdings
                # refresh, compounding, tranche maturation, interval
                # timers) advances differently and position sizing
                # drifts. Measured: same timestamps and sides, ~72% of
                # trades differing in amount.
                #
                # Anchored is a SCREENING mode. Parity comparisons
                # against live must use full evaluation.
                "anchored": bool(self._anchor_indices),
                "full_evaluation": not bool(self._anchor_indices),
                "anchor_candles": (len(self._anchor_indices)
                                   if self._anchor_indices else 0),
            })
            # Attach the sink's PATH — only now does the run directory
            # exist. `SimRunLog._dir` is created by `start_run`, not by
            # `__init__`, so the previous placement (before this call)
            # always read None and every record was written nowhere.
            try:
                _rl_dir = getattr(self._run_log, "_dir", None)
                if _rl_dir is not None and self._signal_sink is not None:
                    self._signal_sink.path = _rl_dir / "signals.jsonl"
            except Exception as _spx:  # noqa: BLE001 - advisory
                logger.debug("signal sink path attach failed: %s", _spx)
            attached = sum(
                1 for b in self._bots
                if self._run_log.attach_to_bot_bus(b))
            self._activity(
                f"Sim run log: {self._run_log.run_id} "
                f"({attached}/{len(self._bots)} bot buses attached)")
        except Exception as _rl_exc:  # noqa: BLE001 - logging is advisory
            self._run_log = None
            logger.warning(
                "sim run log unavailable: %s", _rl_exc)
        self._activity(
            f"Fleet Replay started: {len(self._bots)} bot(s) × "
            f"{self.progress.total_candles} candles.")
        self._task = asyncio.create_task(self._run())
        return True

    @property
    def tape(self) -> Optional[TabletBackend]:
        """The run's `TabletBackend` — the replay's ledger and clock.

        A PUBLIC handle, because consumers outside this class have to
        read the run's balances and fills and there was no public way
        to reach them. They reached instead for `self._exchange` and
        pulled `_balances`, `_opening_balances` and `_trades` off it.
        Since v3.24.84 `_exchange` is a `CCXTConnector` and carries
        none of the three, so `getattr(..., default)` returned the
        default and the reader reported an empty wallet and an empty
        tape (issues #109, #110 and this one).

        `TabletBackend` answers those questions on its own public
        surface — `balances()`, `snapshot()` and `fetch_my_trades()`,
        each returning a copy — so a consumer that comes through here
        cannot mutate the run it is reporting, and a rename below can
        no longer be absorbed as a default.

        `None` before `_build_sim` has run: there is no tape yet, and
        an empty one would claim a run that never happened.
        """
        return self._tape

    def set_load_feed(self, cb) -> None:
        """Install a callable returning candles-to-feed for the next tick.

        v3.24.83. Nuclear passes `SystemLoadOscillator.tick_workload`.
        Unset, the replay advances one candle per tick exactly as before,
        so Fleet Replay is unaffected.
        """
        self._load_feed_cb = cb

    def request_stop(self) -> None:
        """Cooperative stop. Tick loop exits after current iteration."""
        self.progress.stop_requested = True
        self._activity("Stop requested — draining current tick.")

    async def _maybe_yield(self) -> None:
        """Yield to the event loop, but at most once per _YIELD_BUDGET_S.

        WHY THIS IS TIME-BASED AND NOT COUNT-BASED
        ==========================================
        Under the GUI, the asyncio loop is not free-running. ``main.py``
        drives it from a Qt QTimer (``main.py:955``)::

            def pump_async():
                loop.call_soon(loop.stop)
                loop.run_forever()
            async_timer.start(50)

        ``loop.stop`` is queued BEFORE ``run_forever()``, so each fire
        executes exactly one ``_run_once()`` pass. A task rescheduled by
        ``await asyncio.sleep(0)`` lands in ``_ready`` after that pass's
        snapshot, so it does not resume until the next timer fire.

        **One yield = one 50 ms QTimer tick.**

        The old code yielded once per candle plus once per 8 bots. With
        35 bots that is 4 + 1 = 5 yields/candle = 251 ms/candle = 3.98
        candles/s — which is exactly the operator's measured GUI rate
        (2.80 mean over 1.42 / 1.52 / 5.47; the 5.47 run was anchored
        mode, which yields far less often).

        Headless runs call ``asyncio.run()``, so the loop is free-running
        and a yield costs microseconds. That is the whole 29x
        GUI-vs-headless gap: same code, different pump.

        Yielding on a wall-clock budget instead decouples throughput from
        the pump period while still handing the GUI a slot ~50x/second,
        which is well above what a repaint needs.

        NOTE: do NOT "fix" this by lowering ``main.py``'s timer interval.
        That pump is shared with the live trading engine — every live bot
        tick goes through it.
        """
        if time.perf_counter() - self._last_yield < _YIELD_BUDGET_S:
            return
        self.progress.yields_emitted += 1
        await asyncio.sleep(0)
        # Stamp AFTER the await, not before.
        #
        # This ordering is the whole fix and it is easy to get backwards.
        # Under the GUI pump the await parks this coroutine for a full
        # ~50 ms. If the stamp were taken before the await, then on
        # resume the elapsed time would already exceed the 20 ms budget
        # and the very next call would yield again -- every call yields,
        # and the budget is "satisfied" by the delay it itself caused.
        #
        # Measured with that ordering: 35.1 yields/candle at 35 bots,
        # WORSE than the 5.0 of the count-based scheme it replaced.
        # Stamping here makes the budget measure real work done since
        # resuming, which is the quantity we actually want to bound.
        self._last_yield = time.perf_counter()

    def set_visual_refresh_cb(
        self,
        cb: Optional[Callable[[int], None]],
        every_n_candles: int = 100,
    ) -> None:
        """v3.24.3 — wire a per-N-tick visual refresh callback. The
        GUI panel uses this to redraw the price+VWAP chart and
        update gate-light cells without spamming the event loop with
        an update per candle. Called after construction; safe to
        call again to change cadence."""
        self._visual_refresh_cb = cb
        self._visual_refresh_every = max(1, int(every_n_candles))

    # ── Internal ─────────────────────────────────────────────────
    def _total_candle_count(self) -> int:
        if not self._exchange:
            return 0
        try:
            # v3.24.3 — read the sim exchange's master clock. Union
            # of all series timestamps, sorted. This is the ACTUAL
            # denominator: sim playback ends after this many master
            # ticks. Prior max(series lengths) was a proxy that got
            # right in most cases but drifted when series start
            # offsets differed (e.g., SPK starts 20 min after BTC).
            if self._tape is None:
                return 0
            return int(self._tape.total_clock_ticks())
        except Exception:  # noqa: BLE001,S110 - progress best-effort
            return 0

    def _build_sim(self) -> None:
        if not self._candles_by_symbol:
            self._activity("No candle series provided.")
            return
        # v3.24.7 — Stone Tablets are IMMUTABLE. Sim exchange loads
        # every candle unchanged. The YTD window is applied at
        # master-clock iteration time (see the run loop): the cursor
        # advances only across [window_since_ms, window_until_ms]
        # via CandleSeries.step_to_ts. Out-of-window candles remain
        # in the series but are never referenced during this run.
        # Operator directive 2026-08-02: 'You do not modify the
        # fucking stone tablets.'
        series_map = make_symbol_series_map(self._candles_by_symbol)
        available_symbols = set(series_map.keys())

        # v3.24.9 — seed the sim wallet from the fleet's own target
        # balances instead of a hardcoded $100,000.
        #
        # Operator directive 2026-08-02: "In a perfect world, the
        # locked and spendable amounts will start equal, this allows
        # maximum tolerance of volatility for any given position. As
        # such, let's just make the spendable amount for the sim
        # always equal the locked amount at the start of the sim
        # replay."
        #
        # 'Locked' for a scrumming bot is its target_balance — the
        # USD value of asset it is meant to hold. Summing that across
        # the bots this run will actually instantiate (symbols WITH
        # a Stone Tablet) gives the wallet seed. Verified against
        # bot_state 2026-08-02: 35 bots sum to $3,250 target /
        # $3,260.74 live position_value.
        #
        # Only symbols with tablets are counted, so a partial fleet
        # gets a proportionally-sized wallet rather than one sized
        # for bots that never spawn.
        # v3.24.32 — seed PER QUOTE CURRENCY.
        #
        # This summed every bot's target_balance into a single "USD"
        # deposit. The live fleet is 25 USD-quoted and 10 USDC-quoted
        # ($2,850 / $450), so all $3,300 landed under "USD" and the ten
        # USDC bots opened with a ZERO balance in their own quote leg.
        #
        # They could never fund a buy. Confirmed on run
        # 20260805T045429_926437: 510 fills across exactly 25 distinct
        # symbols, all USD-quoted; every /USDC symbol logged zero.
        # 29% of the fleet was inert in every replay ever run, and
        # nothing warned — sim_exchange seeds unknown quotes to 0.0 with
        # absent=False, so the MEM-254 absent-side handshake passes.
        seed_by_quote: dict[str, float] = {}
        for cfg in self._configs:
            sym = str(cfg.get("symbol", "") or "")
            if sym not in available_symbols:
                continue
            quote = str(cfg.get("base_currency", "USD") or "USD").upper()
            try:
                seed_by_quote[quote] = seed_by_quote.get(quote, 0.0) + float(
                    cfg.get("target_balance", 0.0) or 0.0)
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
                "falling back to $1,000.00 nominal.")
        else:
            _detail = ", ".join(
                f"{q} ${v:,.2f}" for q, v in sorted(seed_by_quote.items()))
            self._activity(
                f"Wallet seed: ${seed_usd:,.2f} across "
                f"{len(seed_by_quote)} quote currenc"
                f"{'y' if len(seed_by_quote) == 1 else 'ies'} "
                f"({_detail}); spendable starts equal to locked.")

        # One private registry per REPLAY, shared by that replay's bots
        # so cross-bot reservation contention is exercised within the
        # fleet — which is the behaviour live has — without any of it
        # reaching live state.
        self._sim_capital_registry = _make_sim_capital_registry()
        # v3.24.32 — charge the fees the fleet actually pays.
        #
        # fee_pct was 0.0, so the sim charged NOTHING on any trade,
        # biasing the accumulation curve upward on every fill. Measured
        # on run 20260805T045429_926437: 510 fills, $7,687.18 notional,
        # $122.99 uncharged at the 1.6% that 24 of 35 bots pay — 3.7%
        # of the entire $3,300 wallet over ~52.8 days of replay.
        #
        # UNIT CONVERSION: BotConfig.trading_fee_pct is a PERCENT (1.6);
        # the exchange multiplies notional by a FRACTION. Dividing by
        # 100 here is the whole difference between a 1.6% fee and a
        # 160% one.
        _fees = {}
        for cfg in self._configs:
            _sym = str(cfg.get("symbol", "") or "")
            if not _sym:
                continue
            try:
                _fees[_sym] = float(
                    cfg.get("trading_fee_pct", 0.6) or 0.0) / 100.0
            except (TypeError, ValueError):
                continue
        # v3.24.84 — THE SIMULATOR NOW RUNS LIVE'S CONNECTOR.
        #
        # Operator directive 2026-08-09: the Simulator must process
        # Stone Tablet and YTD data "in the exact same manner that Live
        # Mode processes API pulls from the exchange... just a different
        # data source", and 2026-08-09: "THE MATCH IS THE FIRST FIX."
        #
        # It used to build `FleetSimExchange` — a second implementation
        # of the connector, with its own ticker, balance ledger, order
        # settlement, market metadata and fee arithmetic. A seam-by-seam
        # audit of the fields ScrummingBot actually reads found 16
        # divergences, and fixing them one at a time cannot converge:
        # the copy drifts again the moment live changes.
        #
        # Now the bots hold a real `CCXTConnector`. `TabletBackend`
        # implements the raw ccxt surface beneath it, so normalisation,
        # `_parse_order`, fee reading, `AssetInfo` construction, retries
        # and the documented ccxt quirks are the SAME CODE in both
        # modes. The only thing that differs is where the bytes come
        # from.
        #
        # `_tape` is the replay control surface — clock, cursors,
        # seeding. No bot ever touches it; bots see only the connector,
        # exactly as in live.
        self._tape = TabletBackend(
            {sym: [list(r) for r in rows]
             for sym, rows in self._candles_by_symbol.items()},
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
                "previously charged zero.")
        self._tape.on_trade(self._on_sim_trade)

        # Whether the fleet joins back to bot_state at all. Decided
        # once for the whole fleet: a per-config decision would make a
        # broken join look like a synthetic fleet.
        _n_configs = len(self._configs)
        _n_joinable = sum(
            1 for c in self._configs
            if str(c.get("_src_bot_id", "") or "").strip())
        _joinable = _n_joinable > 0
        if _joinable and _n_joinable == _n_configs:
            self._activity(
                f"Bot ids: joined to bot_state — {_n_joinable} bot(s) "
                "carry their persisted id, so Smart Wires, parity "
                "attribution and run-log correlation can resolve.")
        elif not _joinable:
            self._activity(
                f"Bot ids: SYNTHETIC — none of the {_n_configs} "
                "config(s) carry a persisted id, so each bot gets a "
                "fresh one. Smart Wires cannot route and parity "
                "attribution cannot join. Expected for a proposal or "
                "hand-built fleet; NOT expected for a bot_state replay.")

        # Instantiate bots. Skip any whose symbol isn't in the
        # candle series (can't sim without price data).
        _imported_state = 0
        _import_failed = 0
        _import_missing = 0
        # Bots with NO `_src_scrumming_state` — see the locked-side
        # block below the loop. Collected HERE because this is where the
        # key is read; re-deriving it later would be a second answer to
        # the same question.
        _no_bot_state: list[tuple[Any, dict]] = []
        for cfg in self._configs:
            sym = str(cfg.get("symbol", "") or "")
            if sym not in available_symbols:
                continue
            bot = _instantiate_bot(
                cfg, self._exchange, self._sim_capital_registry)
            if bot is not None:
                # v3.24.71 (C20) — CARRY THE PERSISTED BOT ID.
                #
                # ScrummingBot mints `str(uuid.uuid4())[:8]`
                # (bot_container.py:881) and nothing overrode it here,
                # so every sim bot has always run under an id that
                # exists nowhere else — not in bot_state, not in the
                # live parity trace, not in the Smart Wire table.
                #
                # Smart Wires are keyed by the PERSISTED id:
                # `get_outgoing_wires(source_id)` looks up
                # `self._wires.get(source_id, {})` (smart_wire.py:344)
                # and the bot passes `source_id=self.bot_id`
                # (scrumming_bot.py:8706). Import wires keyed by live
                # ids, register bots keyed by uuid4s, and the two key
                # spaces never meet — `import_wires` does no existence
                # check, so it reports the full count while every scrum
                # takes the early return at scrumming_bot.py:1788.
                # A harness that logs "40 wires active" and routes
                # $0.00.
                #
                # This mirrors live's own restore rather than inventing
                # a mechanism: bot_container.py:3160-3161
                # `# Preserve original bot ID` / `bot.bot_id = bid`,
                # which is exactly why live's import_wires works.
                #
                # NOT EVERY FLEET HAS PERSISTED IDS, and demanding one
                # would break a working feature.
                #
                # `topology_stress._config_for` (:214) builds configs
                # from PROPOSAL bot entries — hypothetical bots that do
                # not exist in bot_state and never will. There is no
                # persisted id to carry and nothing to join to, so a
                # fresh uuid4 is the correct answer there.
                #
                # The first draft of this raised whenever the key was
                # absent. That is the same defect C18 shipped: a
                # precondition hand-built configs cannot satisfy, which
                # breaks the caller instead of the bug.
                #
                # So the check is on the FLEET, not the config. A
                # partial join — some configs carrying the key, some
                # not — cannot be anything but a defect, and that is
                # what raises. A fleet with none is synthetic, gets
                # uuid4s, and SAYS SO, because silence is what let the
                # id mismatch survive this long.
                if _joinable:
                    _src = str(cfg.get("_src_bot_id", "") or "").strip()
                    if not _src:
                        raise KeyError(
                            f"_src_bot_id missing from the config for "
                            f"{sym} while {_n_joinable} of "
                            f"{_n_configs} configs in this fleet carry "
                            "one — a partial join silently drops that "
                            "bot's Smart Wires, parity attribution and "
                            "run-log correlation")
                    bot.bot_id = sim_bot_id(_src)

                # ── IMPORT THE FLEET'S ACTUAL STATE ──────────────────
                # Operator directive 2026-08-08: "bot_state determines
                # the initiating state… NO OTHER SOURCE FOR INITIATING
                # STATE SHOULD BE CITED OR EXPECTED."
                #
                # `import_scrumming_state` (scrumming_bot.py:3786) is the
                # exact inverse of `export_scrumming_state`, which is what
                # WROTE this section. LIVE calls it at
                # bot_container.py:3217 during restore. The sim never did,
                # so every replay opened bots with no lots, no tranches,
                # no holdings and the ORIGINAL config target rather than
                # the grown one.
                _scrum = cfg.get("_src_scrumming_state")
                if isinstance(_scrum, dict) and hasattr(
                        bot, "import_scrumming_state"):
                    try:
                        bot.import_scrumming_state(_scrum)
                        _imported_state += 1
                        # ── STATE PARITY CHECK ────────────────────
                        # Operator directive 2026-08-08: "Parity must be
                        # green on import and bit identical."
                        #
                        # Round-trip: export the sim bot's state and
                        # compare field-for-field against the bot_state
                        # entry it was built from. `import_scrumming_state`
                        # is the inverse of `export_scrumming_state`, so a
                        # faithful import round-trips exactly. Measured on
                        # the live fleet: 38 of 38 fields identical.
                        #
                        # Compared by canonical JSON so list order and
                        # nested lot/tranche contents count — a lot list
                        # that imported with the right LENGTH but wrong
                        # contents must fail, not pass.
                        #
                        # The differing field NAMES go in context: a bare
                        # count would say parity broke without saying
                        # where, which is the failure this whole cascade
                        # exists to remove.
                        try:
                            import json as _pj
                            _back = bot.export_scrumming_state()
                            _bad = sorted(
                                k for k in (set(_scrum) | set(_back))
                                if _pj.dumps(_scrum.get(k), sort_keys=True,
                                             default=repr)
                                != _pj.dumps(_back.get(k), sort_keys=True,
                                             default=repr))
                            from src.core.signal_contract import emit as _pe
                            _pe("fleet.03.005.invariant.state_parity",
                                actual=len(_scrum) - len(_bad),
                                expected=len(_scrum),
                                context={"bot_id": bot.bot_id,
                                         "symbol": sym,
                                         "differing": _bad})
                        except Exception as _pex:  # noqa: BLE001
                            logger.debug("parity emit failed: %s", _pex)
                    except Exception as _isx:  # noqa: BLE001
                        self._activity(
                            f"  WARNING {sym}: scrumming_state import "
                            f"failed ({type(_isx).__name__}: {_isx}) — this "
                            "bot starts from config defaults, NOT from "
                            "bot_state. Its run is not comparable to live.")
                        _import_failed += 1
                elif _scrum is None:
                    _import_missing += 1
                    _no_bot_state.append((bot, cfg))
                self._bots.append(bot)
                # v3.24.80 — record the join for trade attribution.
                if sym:
                    self._bot_id_for_symbol[sym] = bot.bot_id
                # v3.24.32 — refuse to run a bot that cannot fund a buy.
                #
                # Ten USDC bots ran inert for the whole of every replay
                # because their quote leg opened at zero, and nothing
                # said so: the bot just never passed its funding gate.
                # A silent no-op bot is worse than a loud refusal — the
                # run still reports "35 bots" and the operator reads
                # the empty symbols as market conditions.
                _q = str(cfg.get("base_currency", "USD") or "USD").upper()
                if float(seed_by_quote.get(_q, 0.0)) <= 0.0:
                    self._activity(
                        f"  WARNING {sym}: quote {_q} opened with $0.00 "
                        "— this bot cannot fund a buy and will record "
                        "no trades. Its target_balance did not reach "
                        "the wallet seed.")
        self._build_smart_wires(_joinable)
        # A bot with NO bot_state opens with a locked side, so
        # that the credit loop below has lots to seed it from.
        # Issue #111 violation B; see the method for the ruling,
        # the measurement and why this is not the second source
        # of initiating state that block removed.
        self._open_locked_sides(_no_bot_state)
        # ── SEED THE EXCHANGE FROM THE FLEET'S OWN LOTS ─────────────
        # bot_state is the ONLY source of initiating state.
        #
        # MEM-254 deliberately does NOT persist `current_holdings`: the
        # EXCHANGE is authoritative and the MEM-226 init handshake pulls
        # the unit count from it on boot. Live queries a real exchange.
        # The sim has none, so it reads whatever this seeds — which is
        # why a synthetic `target_balance / open_price` deposit used to
        # live here. That was a second source of initiating state.
        #
        # The authoritative units are in the restored lots. Invariant,
        # scrumming_bot.py:550:
        #     sum(l["units"] for l in _main_lots) == _current_holdings
        # `import_scrumming_state` restores `_main_lots`, so the fleet's
        # real position is derivable without inventing anything.
        _seeded = 0
        _seeded_units = 0.0
        for _b in self._bots:
            _asset = str(getattr(getattr(_b, "config", None),
                                 "target_asset", "") or "").upper()
            if not _asset:
                continue
            _units = 0.0
            for _lot in (getattr(_b, "_main_lots", None) or []):
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
            _fs("fleet.03.006.postcondition.state_imported", actual=_imported_state,
                expected=len(self._bots),
                context={"failed": _import_failed,
                         "missing": _import_missing})
            _fs("fleet.03.007.postcondition.positions_seeded_from_lots", actual=_seeded,
                expected=len(self._bots),
                context={"total_units": round(_seeded_units, 8)})
        except Exception as _fx:  # noqa: BLE001 - advisory
            logger.debug("fleet state emit failed: %s", _fx)

        self._activity(
            f"Opening state: {_imported_state} of {len(self._bots)} bot(s) "
            f"imported scrumming_state from bot_state; {_seeded} seeded a "
            f"position from their own restored lots."
            + (f" {_import_failed} FAILED to import."
               if _import_failed else "")
            + (f" {_import_missing} had no scrumming_state in bot_state."
               if _import_missing else ""))

        self._assert_capital_isolation()

    def _open_locked_sides(
            self, lotless: list[tuple[Any, dict]]) -> None:
        """Open every bot that carries no bot_state with a locked side.

        Issue #111 violation B. Operator ruling: "locked and spendable
        start equal." Called immediately before the credit loop in
        `_build_sim`, because the lots this writes are what that loop
        reads.

        A proposal fleet carries no `_src_scrumming_state`
        (`topology_stress._config_for`, topology_stress.py:216, builds
        exactly such configs), so the import in `_build_sim` never ran,
        no bot got lots, and every bot opened FLAT.
        `opening_lot_for_lotless` carries the measurement of what that
        cost.

        WHY THIS IS NOT THE SECOND SOURCE OF INITIATING STATE THAT THE
        CREDIT BLOCK REMOVED. That removal was about OVERRIDING
        bot_state: the sim synthesised a position for bots that HAD a
        persisted one, so an invented figure won over the real lots.
        These bots have no bot_state at all. `_src_scrumming_state` is
        set only from a real `scrumming_state` entry
        (bot_state_loader.py:191-192), so its ABSENCE means there is
        nothing to override and no parity claim to break. The
        discriminator is the missing KEY, never an empty lot list: a bot
        whose bot_state says FLAT is a bot whose real state IS flat, and
        `_build_sim` does not put it in this list.

        THE LOT IS WRITTEN THROUGH THE PAIR THE BOT_STATE PATH USES.
        `export_scrumming_state` then `import_scrumming_state`
        (scrumming_bot.py:3786), the same inverse pair `_build_sim`
        calls on a restored fleet. Every field except `main_lots` is the
        bot's own current value, so the round trip resets nothing.

        THE TAPE IS NOT TOUCHED HERE. The single credit loop in
        `_build_sim` reads `_main_lots` and credits the venue, exactly
        as it does for a restored fleet. This method moves no balance
        and adds no second credit path.
        """
        opened = 0
        units = 0.0
        for bot, cfg in lotless:
            symbol = str(cfg.get("symbol", "") or "")
            lot = opening_lot_for_lotless(
                cfg.get("target_balance"),
                self._candles_by_symbol.get(symbol) or [])
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
                    "it can trade.")
                continue
            opened += 1
            units += float(lot["units"])
        if opened:
            self._activity(
                f"Locked side: {opened} of {len(lotless)} bot(s) carry "
                "no bot_state and opened holding their target_balance "
                "in base units at the tape's first close; locked and "
                "spendable start equal.")
        try:
            from src.core.signal_contract import emit as _ol
            _ol("fleet.03.008.postcondition.lotless_opened_locked",
                actual=opened, expected=len(lotless),
                context={"total_units": round(units, 8)})
        except Exception as _olx:  # noqa: BLE001 - advisory
            logger.debug("locked-side emit failed: %s", _olx)

    def _build_smart_wires(self, joinable: bool) -> None:
        """Attach the fleet's persisted Smart Wires to THIS replay.

        v3.24.72 (C20). Called after the bot loop on purpose: a wire has
        two endpoints and both must exist before the active count means
        anything.

        WHY THE BUS IS INJECTED AND NOT LEFT None.

        The cascade plan said "the class has no bus and no singleton"
        and cited `nuclear_fleet_controller.py:551` — `SmartWireManager()`
        — as the precedent to copy. No singleton is right. No bus is
        WRONG, and wrong in the dangerous half: `SmartWireManager.
        __init__` takes `bus=None` (smart_wire.py:217), and both emit
        paths resolve the process-wide `get_event_bus()` when it is None
        (:507-511 and :695-698) and then emit `bot.log`. The class
        comment at smart_wire.py:220-226 quotes that plan sentence and
        answers "That correction is itself wrong."

        So the cited precedent IS the leak: a bus-less manager puts sim
        wire logs on the operator's LIVE bus, while the sim bots around
        it are fail-closed onto private buses (scrumming_bot.py:393-394,
        raising at :412-416). The model copied here is live's own:
        bot_container.py:1621 `SmartWireManager(bus=self._bus)`.

        There is no single "sim bus" to borrow — each sim bot builds its
        own `EventBus()` — so this controller owns a dedicated one.

        WHY A SYNTHETIC FLEET GETS NO MANAGER AT ALL. Wires are keyed by
        the persisted bot id. Against uuid4 ids nothing resolves, and a
        manager holding wires that can never fire is precisely the
        green-log-zero-effect state this cascade exists to remove.
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
                "accumulation curve is not comparable to live's.")
            return

        self._sim_bus = EventBus()
        mgr = SmartWireManager(bus=self._sim_bus)
        sim_ids = set()
        for bot in self._bots:
            mgr.attach_bot(bot.bot_id, bot)
            bot.set_smart_wire(mgr)
            sim_ids.add(bot.bot_id)

        # TRANSLATE THE WIRE ENDPOINTS INTO SIM ID SPACE.
        #
        # bot_state's wires are keyed by the PERSISTED bot id, and sim
        # bots now carry `simulated_<live id>` so a sim row can never be
        # mistaken for a live one. Importing the rows verbatim would put
        # live ids in `_wires` and sim ids in `_bot_refs` -- disjoint
        # key spaces, `get_outgoing_wires(self.bot_id)` returns {}, and
        # the run logs "40 wires imported" while routing $0.00. That is
        # the exact failure C20 was opened for; the prefix would have
        # silently reintroduced it.
        #
        # Both endpoints are mapped, so the topology is preserved
        # exactly -- same edges, same percentages, expressed in the id
        # space the sim fleet actually uses.
        _sim_wires = []
        for _w in (self._smart_wires or []):
            if not isinstance(_w, dict):
                continue
            _tw = dict(_w)
            _tw["source_id"] = sim_bot_id(_w.get("source_id", ""))
            _tw["target_id"] = sim_bot_id(_w.get("target_id", ""))
            _sim_wires.append(_tw)

        imported = mgr.import_wires(_sim_wires)

        # ACTIVE is not IMPORTED, and the difference is the whole point.
        #
        # `import_wires` (smart_wire.py:456-478) performs NO existence
        # check — it setdefaults every well-formed row and returns the
        # count. Reporting that number is how a harness comes to log
        # "40 wires active" while routing $0.00: a wire whose endpoints
        # are not both in this run's fleet can never fire, and the sim
        # fleet is filtered by `available_symbols` above, so a partial
        # tablet set silently produces exactly that.
        active = sum(
            1 for w in _sim_wires
            if str(w.get("source_id", "")) in sim_ids
            and str(w.get("target_id", "")) in sim_ids)

        self._smart_wire_mgr = mgr
        self._activity(
            f"Smart Wires: {active} of {imported} imported wire(s) have "
            f"BOTH endpoints in this run's {len(sim_ids)}-bot fleet and "
            "can route; the rest reference bots this replay did not "
            "instantiate.")
        if active == 0 and imported:
            self._activity(
                "  WARNING: no wire can route in this run. Cross-bot "
                "compounding is inert, so the accumulation curve will "
                "understate live's.")
        # Ledgers are deliberately NOT imported. Live's persisted rows
        # carry accrued wired_in/wired_out totals; seeding them here
        # would make a "non-zero wired_in" check pass without a single
        # sim wire firing. Wire income must accrue from zero during the
        # replay or it measures nothing.

    def _assert_capital_isolation(self) -> None:
        """Every constructed sim bot must be off the live registry.

        v3.24.54 (C15 step 5). The three guards upstream — the factory
        raising, `_instantiate_bot` refusing, `_crr()` returning None in
        sim mode — each protect one path. This checks the OUTCOME they
        exist to produce, once, at the point where the bot set is final
        and before any of them can trade.

        A guard verifies its own path; this verifies the property. If a
        future path constructs a bot some other way, the guards stay
        green and this does not.

        Aborts the run. The alternative is a replay that writes sim
        reservations into the operator's live capital state, which is
        the exact defect this cascade exists to close.
        """
        # Checks a PROPERTY, not identity against the live singleton.
        #
        # The obvious implementation compares each bot's registry to
        # `get_registry()`. That call RESOLVES — and constructs, if it
        # does not yet exist — the process-wide autosaving registry,
        # from a sim path. Verifying isolation by touching the thing
        # being isolated from is the rule this cascade exists to
        # enforce, broken inside its own guard.
        # `test_singleton_isolation.py` caught exactly that.
        #
        # `autosave` is the property that matters: a registry which does
        # not autosave cannot reach ~/.acervator/reservation_state.json
        # no matter which object it is.
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
                f"the replay.")
        self._activity(
            f"  capital isolation verified: {len(self._bots)} sim bot(s) "
            f"on private, non-persisting registries.")

    def _observe_ta(self, bot) -> None:
        """Compute this bot's TA on the CURRENT candle, for the record.

        v3.24.82. Observation only — never feeds the bot, never places an
        order, never touches bot state. `VotingEngine.compute_all` is
        stateless (ta_engine.py:2474) with no caching, so calling it here
        cannot perturb what the bot would have done.

        Emits via the engine's own
        `ta.07.004.postcondition.raw.<indicator>` records, so an
        observed candle is indistinguishable in the log from one the bot
        evaluated itself — which is the point: the record set covers
        every candle, not the ~4% the throttle let through.

        Never raises: an observation that breaks a replay is worse than
        no observation.
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
            # Read from the TAPE, not through the connector. This is the
            # Simulator observing its own replay, not a bot making an
            # exchange call, so it must not inherit the ccxt page-size
            # quirk that governs what a BOT receives.
            _rows = self._tape.history(_sym, _need)
            if not _rows or len(_rows) < 51:
                # 51 is the deepest guard in the engine (ZScore,
                # period + 1). Below it some indicators cannot compute
                # and would record a value with no basis.
                return
            from src.trading.ta_engine import candles_from_raw
            _eng.compute_all(candles_from_raw([list(r) for r in _rows]), _tf,
                             symbol=bot.config.symbol)
            self._ta_observed[bot.bot_id] = (
                self._ta_observed.get(bot.bot_id, 0) + 1)
        except Exception as _ox:  # noqa: BLE001 - observation is advisory
            logger.debug("TA observation skipped: %s", _ox)

    def _candle_address_for(self, symbol: str) -> str:
        """``NNNNNN_TICKER`` for the candle under the tape's cursor.

        ``FleetSimExchange`` stamped this onto every fill's ``raw``
        (sim_exchange.py:642). ``TabletBackend`` has no address
        concept -- it serves rows, and an address is a Stone Tablet
        idea -- so the Simulator resolves it here, from the same
        cursor the fill was priced off and through the same
        ``format_address``. Empty string when it cannot be resolved:
        the fill still records, it just carries no address rather than
        a wrong one.
        """
        tape = self._tape
        if tape is None:
            return ""
        try:
            return addressing.format_address(
                addressing.ticker_from_symbol(symbol),
                tape.cursor_for(symbol))
        except Exception as exc:  # noqa: BLE001 - addressing is advisory
            logger.debug(
                "candle address for %s raised %s: %s",
                symbol, type(exc).__name__, exc)
            return ""

    def _read_fill(self, trade: dict | Trade) -> dict:
        """Normalise one fill payload into the fields this class records.

        ISSUE #110 -- THE SHAPE CHANGED AND THE READER DID NOT.
        ``TabletBackend.on_trade`` hands out ``dict(_t)``, a ccxt-shaped
        DICT (tablet_backend.py:527). Every reader below was written for
        ``FleetSimExchange``'s ``Trade`` OBJECT, and ``getattr`` on a
        dict does not read a key. So each field returned its default and
        a replay that filled a REAL trade recorded
        ``per_symbol_trade_count == {}``, queued no chart marker, and
        wrote ``symbol="" side="" amount=0.0 price=0.0`` to the run log.

        A dict is therefore routed through the dict branch UP FRONT --
        the same resolution ``history_helpers.py:90`` already applies to
        this exact ambiguity. Falling back by exception cannot work
        here, because ``getattr`` with a default never raises.

        THE OBJECT BRANCH IS A LIVE SURFACE, NOT SCAFFOLDING. Verified:
        ``TabletBackend`` is the only producer wired to this observer
        (:900) and ``FleetSimExchange`` is instantiated nowhere in
        ``src/`` or ``tools/``. But ``FleetSimExchange.on_trade`` still
        passes a ``Trade`` (sim_exchange.py:680) and the class is still
        exported from ``fleet/__init__.py``, so a host that wires it is
        read correctly instead of silently zeroed.

        TIME UNITS DIFFER BETWEEN THE TWO PRODUCERS and the run log
        wants MILLISECONDS. The dict's ``timestamp`` IS the master
        clock in ms (``current_ts_ms()``, tablet_backend.py:522); the
        object carries SECONDS on ``.timestamp`` and the ms value on
        ``raw["sim_master_ts_ms"]``. Reading the object's seconds as ms
        would date every sim row to 1970 and make parity unmeasurable.
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
        # v3.24.13 - persist the fill. Before this, sim trades lived
        # only in the sim exchange's own list and vanished when the
        # process ended, so a replay could not be compared against
        # anything afterwards. Writes to ~/.acervator_logs/sim/,
        # never the live tree.
        if self._run_log is not None:
            try:
                self._run_log.record_trade(
                    symbol=_sym,
                    # v3.24.80 - ATTRIBUTE THE FILL TO A BOT.
                    #
                    # `bot_id` was never passed, so every trade row on
                    # disk carried "". 8,250 fills across a soak, none
                    # attributable to a bot, which makes the trade log
                    # useless for exactly the question it exists to
                    # answer.
                    #
                    # The trade arrives from the exchange, which does
                    # not know which bot placed the order - so it is
                    # resolved by symbol, the same single-writer
                    # attribution the per-bot trade counter below has
                    # used since v3.24.0. These are the LIVE bot ids
                    # (carried in from bot_state since v3.24.71), so a
                    # sim fill is traceable straight back to the
                    # operator's own bot.
                    bot_id=self._bot_id_for_symbol.get(_sym, ""),
                    # v3.24.80 - the side, under the key the schema
                    # declares. `action` was empty on every row.
                    action=fill["side"],
                    side=fill["side"],
                    amount=fill["amount"],
                    price=fill["price"],
                    usd=fill["usd"],
                    sim_ts_ms=fill["sim_ts_ms"],
                    # v3.24.32 - spendable at fill time. Operator
                    # directive 2026-08-05: "We can also add Spendable
                    # to the trade log for use as an additional
                    # validation point."
                    #
                    # Recorded per fill so a replay's wallet trajectory
                    # can be reconstructed from the log alone and
                    # checked against the header - a drift between the
                    # two means the header is lying, which is how
                    # Spendable $0.00 / Locked $2,995.14 went unnoticed.
                    extra={"spendable_usd": round(
                        self._spendable_now(), 8)},
                    # v3.24.17 - tablet traceability
                    candle_address=fill["candle_address"],
                )
            except Exception as _rl_exc:  # noqa: BLE001 - logging is advisory
                logger.debug(
                    "sim run log: trade record failed: %s", _rl_exc)
        # v3.24.0 - attribute by symbol (single writer path,
        # actually populated). Replaces v3.23.80's trade.raw
        # bot_id lookup which was scaffolding - nothing ever
        # wrote raw["bot_id"], so per_bot_trade_count stayed at 0
        # for every bot despite trades_fired ticking up.
        try:
            if _sym:
                self.progress.per_symbol_trade_count[_sym] = (
                    self.progress.per_symbol_trade_count.get(_sym, 0)
                    + 1)
                # v3.24.29 - queue a chart marker. GREEN when this fill
                # landed on a candle that carries a historical trade
                # (validated), RED when it did not (a sim-only fire).
                # Queued rather than drawn: this runs on the replay
                # worker, and the chart is a Qt widget.
                _exp = self._expected_indices
                _ok = bool(_exp) and self._candle_i in _exp
                self._pending_markers.append((_sym, _ok))
        except Exception:  # noqa: BLE001,S110 - counter best-effort
            pass

    def _spendable_now(self) -> float:
        """Quote-currency cash across the sim wallet.

        Sums every quote leg (USD + USDC + ...) rather than just "USD":
        the fleet is multi-quote, and reading one leg would under-report
        by whatever sits in the others — the same single-currency
        assumption that left ten USDC bots unfunded.

        ISSUE #110 SWEEP -- READS THE TAPE, NOT ``self._exchange``.
        This read ``self._exchange._balances``. ``_balances`` belonged
        to ``FleetSimExchange``; since v3.24.84 ``self._exchange`` is a
        ``CCXTConnector``, which has no such attribute, so the
        ``AttributeError`` below was caught on EVERY call and this
        returned 0.0 for the whole life of the Simulator. Measured on a
        replay whose tape ledger held $99.40 of USD: ``_spendable_now()
        == 0.0``, and every trade row on disk carried
        ``spendable_usd: 0.0`` -- the exact "Spendable $0.00" that the
        caller records this field to catch.

        ``TabletBackend.balances()`` is the ledger's own PUBLIC
        accessor and returns a copy, so this reaches into no private
        state and cannot mutate the wallet it reports.
        """
        tape = self._tape
        if tape is None:
            return 0.0
        quotes = {
            str(c.get("base_currency", "USD") or "USD").upper()
            for c in self._configs}
        try:
            wallet = tape.balances()
            return float(sum(
                float(wallet.get(q, 0.0) or 0.0) for q in quotes))
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
                    self._activity(
                        f"Stopped after {candle_i} candle(s).")
                    break
                # v3.24.20 — count-based yielding REMOVED. See
                # _maybe_yield() for the measurement; in short, every
                # yield costs a full 50 ms under the GUI's QTimer
                # asyncio pump, so "yield every 8 bots" was buying
                # GUI responsiveness at 5x the replay's throughput.
                # v3.24.15 — anchored (screening) mode. When
                # _anchor_indices is set, only candles in that set
                # get a full bot evaluation; the rest advance the
                # cursor and move on.
                #
                # Operator directive 2026-08-03: "fast read over for
                # candles that do not have expected trade events".
                #
                # v3.24.70 — the saving claimed here was "15,212 ->
                # 4,258 candles (28%), ~20 min -> ~6 min". The most
                # recent recorded run contradicts it: 14,598 anchored
                # of 15,212, i.e. 96% still evaluated, ~4% saved.
                # Whether anchored mode earns its correctness cost at
                # that ratio is an open question — re-measure before
                # relying on the mode for anything but screening.
                #
                # TWO COSTS, deliberately not hidden:
                #   1. Sim-only divergence (sim fires where live did
                #      not) becomes much harder to detect, because the
                #      bot is not evaluated on skipped candles.
                #      v3.24.70 — this used to read "a skipped candle
                #      cannot produce a sim trade". That is FALSE and
                #      the panel repeated it to the operator as fact.
                #      The skip path still calls `_exchange.step()`
                #      below, which advances the clock and sweeps
                #      RESTING LIMIT ORDERS — so a skipped candle can
                #      settle a fill placed on an earlier anchored
                #      one. What is skipped is bot.tick(), not the
                #      exchange.
                #   2. Hysteresis arming evolves per tick on delta
                #      sign crossings; skipping loses crossings, so
                #      arming state at a trade candle may differ
                #      from live for reasons unrelated to strategy.
                #
                # Hence: screening pass, never the authoritative
                # parity run. Default is None (evaluate everything).
                if (self._anchor_indices is not None
                        and candle_i not in self._anchor_indices):
                    self.progress.candles_skipped += 1
                    if not self._tape.step():
                        self._activity(
                            f"All series exhausted at candle "
                            f"{candle_i}.")
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
                        # ── CAUSALITY: A BOT DOES NOT RUN BEFORE ITS
                        #    SYMBOL HAS A PRICE ──────────────────────
                        # The master clock is the UNION of every
                        # series' timestamps, so it starts at the
                        # earliest tablet in the fleet. Until a given
                        # symbol's tablet begins, its series is parked
                        # on row 0 — a candle stamped AFTER the clock.
                        # Ticking the bot there fed it a price from its
                        # own future, which no live exchange can do.
                        #
                        # On the operator's fleet 13 of 35 symbols
                        # start after the union origin; GROVE's begins
                        # 2026-07-06 against 2026-01-01, a 186-day
                        # lead-in.
                        #
                        # No sim-only FILL came of it — the read-rate
                        # throttle drops ~11 of 12 ticks and the one
                        # candle available fails the `>= 30` TA guard —
                        # but the bot's STATE moved: the fold-side
                        # hysteresis pivot was captured months early
                        # and is sticky, and holdings reconciliation,
                        # capital reservation and circuit breakers all
                        # ran against that phantom price.
                        #
                        # The discriminator was already being computed
                        # ten lines below, where `_bser.cursor > 0`
                        # decided TA-coverage ELIGIBILITY. It fixed a
                        # counter and let the tick through.
                        if not self._tape.has_data(bot.config.symbol):
                            self.progress.bot_ticks_before_tape += 1
                            continue
                        await bot.tick()
                        self.progress.bots_ticked += 1
                        # ── PER-CANDLE TA OBSERVATION ─────────────
                        # Operator directive 2026-08-08: "One entry per
                        # indicator and measurement for every candle
                        # that ticks through the reader."
                        #
                        # The bot's own TA runs on ~4% of ticks: the
                        # read-rate throttle at scrumming_bot.py:5046
                        # exits early on ~91%, and further pre-TA
                        # returns account for the rest. That throttle
                        # limits how often a bot ACTS — in LIVE each
                        # action tick costs an exchange call. It is not
                        # about how often TA can be computed.
                        #
                        # `compute_all` is a pure function that places
                        # no orders and mutates no bot state, so running
                        # it here for OBSERVATION changes no trade
                        # behaviour and no gate outcome. The action
                        # cadence is untouched, which is what keeps sim
                        # comparable to live.
                        #
                        # Sim-only by construction: it lives in the
                        # replay loop, not in the bot.
                        # Count this bot's OWN eligible candles, not
                        # the fleet's. A bot has no candle at a
                        # master-clock tick that predates its tablet:
                        # measured, SPK's first 300 candles are
                        # 2026-01-01 and CHIP's are 2026-04-21, so a
                        # candles_played x bots denominator is wrong
                        # by construction and makes correct coverage
                        # look broken.
                        if self._tape.cursor_for(bot.config.symbol) > 0:
                            self._ta_eligible[bot.bot_id] = (
                                self._ta_eligible.get(bot.bot_id, 0) + 1)
                        self._observe_ta(bot)
                        # ── S2 EMITTER ────────────────────────────
                        # S2 is "run front-loaded YTD + simulated bots
                        # against it". Its only evidence was
                        # `bots_ticked`, which increments here
                        # UNCONDITIONALLY — it counts tick ENTRIES, so
                        # the number is identical whether the bot did
                        # work or returned on its first line.
                        #
                        # ScrummingBot throttles by read rate
                        # (scrumming_bot.py:5033-5048): it returns early
                        # while `_tick_counter < _tick_skip`, and RESETS
                        # the counter to 0 only on an action tick. So a
                        # post-tick counter of 0 means work happened and
                        # non-zero means it was throttled. Measured on
                        # the live fleet: scrum_read_rate_min is 1 on 29
                        # bots and 5 on 6, against a hardcoded
                        # tick_interval of 5.0 — a 1-in-12 action rate
                        # for most of the fleet.
                        #
                        # Reading the bot's counter couples this to a
                        # private attribute, deliberately: instrumenting
                        # scrumming_bot itself would leave the Simulator
                        # Tab scope. getattr-with-default so a bot that
                        # does not have it is recorded as UNKNOWN rather
                        # than silently counted as working.
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
                            f"{type(_tick_exc).__name__}: "
                            f"{str(_tick_exc)[:120]}")
                        self.progress.last_error = _exc_key
                        # v3.23.80 — count distinct exception
                        # signatures so 7000 identical failures
                        # collapse to a diagnosable summary.
                        self.progress.exception_samples[_exc_key] = (
                            self.progress.exception_samples.get(
                                _exc_key, 0) + 1)
                        # Log the FIRST occurrence of each distinct
                        # exception at warning level (subsequent
                        # duplicates at debug so we don't flood).
                        if self.progress.exception_samples[_exc_key] == 1:
                            logger.warning(
                                "sim bot tick raised: %s "
                                "(bot=%s, symbol=%s)",
                                _exc_key,
                                getattr(bot, "bot_id", "?"),
                                getattr(getattr(bot, "config", None),
                                        "symbol", "?"),
                                exc_info=True)
                        else:
                            logger.debug(
                                "sim bot tick raised (dupe): %s",
                                _exc_key)
                # ── LOAD FEED ────────────────────────────────────
                # Normally one candle per tick. Under Nuclear's load
                # pulse, `_load_feed_cb` returns how many candles this
                # tick should advance — the `_tick_feed` consumer the
                # oscillator was written for and which never existed:
                # "each engine tick adds current multiplier to the
                # accumulator; the integer part becomes the number of
                # _tick_feed iterations that tick"
                # (system_load_oscillator.py header).
                #
                # This is the DEPTH half of the pulse; the RATE half is
                # `_tick_delay`, set from `effective_tick_interval`.
                # Together they are the 4x peak the spec calls for,
                # applied to ONE fleet.
                #
                # Every fed candle still steps the exchange and counts,
                # so resting limits sweep and the master clock stays
                # authoritative — the depth changes how much history
                # crosses per tick, not what a candle means.
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
                        self._activity(
                            f"All series exhausted at candle {candle_i}.")
                        _exhausted = True
                        break
                    candle_i += 1
                    self.progress.candles_played = candle_i
                    self.progress.candles_fed_under_load += (
                        1 if _f > 0 else 0)
                if _exhausted:
                    break
                if (self._max_candles is not None
                        and candle_i >= self._max_candles):
                    self._activity(
                        f"Reached max_candles={self._max_candles}; "
                        "stopping.")
                    break
                if self._tick_delay > 0:
                    await asyncio.sleep(self._tick_delay)
                else:
                    await self._maybe_yield()
                # v3.24.1 perf heartbeat.
                if candle_i % 500 == 0:
                    self._perf(
                        f"tick {candle_i}/{self.progress.total_candles}"
                        f" · {self.progress.trades_fired} sim trades"
                        f" · {self.progress.exceptions} exceptions")
                # v3.24.3 — visual refresh signal for GUI widgets
                # (gate lights, price+VWAP chart). Fires every N
                # candles to keep 19,680 tick replay under ~200
                # UI updates total. Callback is set by the panel via
                # set_visual_refresh_cb().
                if (self._visual_refresh_cb is not None
                        and candle_i % self._visual_refresh_every == 0):
                    try:
                        self._visual_refresh_cb(candle_i)
                    except Exception as _vr_exc:  # noqa: BLE001
                        logger.debug(
                            "visual_refresh_cb raised: %s", _vr_exc)
        finally:
            self.progress.finished = True
            # ── S2 EMITTERS ───────────────────────────────────────
            # "Run front-loaded YTD + simulated bots against it."
            # Emitted in `finally` so a run that died still reports what
            # it managed — a partial run must not be silent, which is
            # the same reason the sink reports its own dropped count.
            try:
                from src.core.signal_contract import emit as _s2
                _p = self.progress
                # 10.4 - EXPECT THE TAPE THE RUN WAS ASKED TO PLAY.
                # `total_candles` is the whole tape, but the loop stops
                # at `_max_candles` BY DESIGN, so a correct run read
                # ok=False on all 13 recorded runs (expected 15212,
                # actual 250). `expected` is now what was asked for. A
                # genuine early stop - a series exhausted before the
                # master clock ran out, or an exception that ended the
                # loop mid-tape - still drives `actual` below it.
                #
                # 10.4 F2 - A DELIBERATE STOP IS NOT A SHORTFALL, AND
                # THE RECORD MUST SAY WHICH HAPPENED.
                #
                # The loop has four exits and they do not mean the same
                # thing. `stop_requested` is the operator pressing Stop
                # and it is read at the top of the loop; the others are
                # the cap, an exhausted tape, and an exception. Folding
                # `_max_candles` into the expectation fixed the cap and
                # left the Stop, so a run he ended at candle 40 of 200
                # still read ok=False, with `total_candles` and
                # `max_candles` in the context and NOTHING naming the
                # stop. A reader could not tell a deliberate stop from
                # a tape that broke - one verdict standing for two
                # different worlds, which is the disjunction defect.
                #
                # A stop still carries a real bound, so this is not a
                # widening: what CANNOT happen is a stopped run that
                # played MORE than it was asked for, and an
                # under-reported clock does exactly that. Every other
                # exit stays an equality.
                #
                # `outcome` names which of the four applied, so the
                # reader never infers it from the numbers.
                # `overran_the_ask` is REACHABLE and is not new red:
                # the load feed steps `_feed` candles before the cap is
                # re-checked, so a Nuclear cycle at feed 4 played 52
                # candles against max_candles=50 - measured, and
                # already ok=False before this change. It is now named,
                # with `fed_under_load` beside it to attribute it.
                _asked = (_p.total_candles if self._max_candles is None
                          else min(_p.total_candles, self._max_candles))
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
                _s2("sim.06.001.postcondition.candles_stepped",
                    actual=_p.candles_played,
                    expected=_asked,
                    ok=_cok,
                    context={"outcome": _outcome,
                             "stop_requested": bool(_p.stop_requested),
                             "skipped": _p.candles_skipped,
                             "anchored": bool(_p.anchored),
                             "total_candles": _p.total_candles,
                             "max_candles": self._max_candles,
                             "fed_under_load": _p.candles_fed_under_load})
                # THE ONE THAT MATTERS. `bots_ticked` counts ENTRIES;
                # these separate work from throttle, so "the bots ran"
                # is finally falsifiable.
                # 10.4 - EXPECT THE UNACCOUNTED REMAINDER, NOT EVERY
                # ENTRY. `bots_ticked` counts tick ENTRIES and the
                # read-rate throttle skips most of them BY DESIGN, so
                # `expected=bots_ticked` called a healthy run a failure
                # on all 13 recorded runs: 2074 worked against 8461
                # entered, 6387 throttled. Those add up exactly, and
                # THAT is the invariant - every entry is classified as
                # worked, throttled or unknown. `expected` is derived
                # from the other three counters, so a tick that
                # disappears between the entry count and the classifier
                # (an exception raised in the window between them)
                # drives expected above actual and reports ok=False.
                _worked = _p.bot_ticks_worked
                _s2("sim.06.002.postcondition.bot_ticks_did_work",
                    actual=_worked,
                    expected=(_p.bots_ticked - _p.bot_ticks_throttled
                              - _p.bot_ticks_unknown),
                    context={"entered": _p.bots_ticked,
                             "throttled": _p.bot_ticks_throttled,
                             "unknown": _p.bot_ticks_unknown,
                             "worked_pct": (
                                 round(100.0 * _worked / _p.bots_ticked, 2)
                                 if _p.bots_ticked else 0.0)})
                # PER-BOT TA COVERAGE: observed / that bot's own
                # eligible candles. Emitted per bot so one starved
                # symbol cannot hide inside a fleet average.
                # 10.4 - THE VERDICT IS THE BOUND, NOT THE EQUALITY.
                # `_elig` counts the candles a bot was eligible for,
                # decided by `cursor_for(sym) > 0` in the tick loop.
                # `_obs` counts the candles TA was actually run on,
                # decided by `_observe_ta`'s own guards, whose deepest
                # indicator needs 51 rows. Two mechanisms, so equality
                # is false for the whole warm-up and the pin read FAIL
                # on 132 of 132 records. What CANNOT happen in a sound
                # run is an observation with no eligibility behind it:
                # that means the tape served history the master clock
                # has not reached, which is the causality break the sim
                # exists to keep out. Coverage stays reported, in
                # `expected` and in `pct`.
                #
                # 10.4 F3 - WALK THE UNION, NOT ONE SIDE. THE BOUND WAS
                # FORCEABLE AND ITS WORST CASE STILL EMITTED NOTHING.
                #
                # This loop read `_ta_eligible` alone. A bot with
                # observations and ZERO eligibility is not a key in that
                # map, so the MAXIMAL violation of the bound - the exact
                # state the paragraph above says cannot happen - was the
                # one state that produced no record. Measured on this
                # coroutine, 120 candles, one symbol's cursor pinned at
                # 0 while history kept serving it: eligible
                # {bot0001: 119}, observed {bot0000: 70, bot0001: 70},
                # ONE record emitted, for bot0001, ok=True. bot0000
                # observed 70 candles against eligibility 0 and said
                # nothing, so the run read green with a causality break
                # live inside it.
                #
                # FOUR STATES EXIST AND THE PIN OWNS THREE:
                #   in BOTH maps  the normal case; the bound is
                #                 meaningful and can fail
                #   ELIGIBLE only warm-up. `_observe_ta` needs 51 rows
                #                 and `_visible` serves cursor + 1, so
                #                 no observation is possible below
                #                 cursor 50 while eligibility starts at
                #                 cursor 1. `0 <= elig` holds and the
                #                 record is honestly green
                #   OBSERVED only THE VIOLATION. `obs > 0 == elig`, so
                #                 the same bound reports ok=False. No
                #                 new verdict is invented; the existing
                #                 one is finally evaluated
                #   NEITHER map   the bot never became eligible and was
                #                 never observed - on a real fleet, a
                #                 tablet that starts after the window.
                #                 NO BOUND APPLIES. `0 <= 0` would be a
                #                 fabricated green, so it gets NO
                #                 record and is COUNTED instead, in
                #                 `fleet_bots_with_no_record`, which
                #                 keeps the fleet total accountable
                #                 without inventing an expectation.
                #
                # THE IDENTITY THE RECORD COUNT MUST SATISFY:
                #   records == len(set(eligible) | set(observed))
                # `bots_in_union` carries it inside every record, so a
                # reader can reconcile the count from the log alone.
                # The fleet residue is the complement:
                #   len(self._bots) == bots_in_union
                #                      + fleet_bots_with_no_record
                # derived by subtraction rather than by reading
                # `bot_id` off every bot, because an AttributeError
                # here is raised inside the emitter block's own `try`
                # and would silence every pin after this one.
                #
                # `pct` is None, not 0.0, where there is no eligibility
                # to divide by. 0.0 reads as "observed nothing", and a
                # bot in the OBSERVED-only state observed everything.
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
                    _s2("ta.07.001.postcondition.coverage_per_bot",
                        actual=_obs,
                        expected=_elig,
                        ok=(_obs <= _elig),
                        context={"bot_id": _bid,
                                 "bound": "observed <= eligible",
                                 "state": _ta_state,
                                 "bots_in_union": len(_ta_union),
                                 "fleet_bots_with_no_record": _ta_absent,
                                 "pct": (round(100.0 * _obs / _elig, 2)
                                         if _elig else None)})
                # ── INDICATOR INVARIANTS: ONE ACTIONABLE ROW ──────
                # The per-candle `ta.07.004.postcondition.raw.*`
                # records now carry a verdict,
                # but ~1200 green rows per indicator is not a report —
                # it is the same flood with a tick on it. This rolls
                # them into a single record whose `ok` answers the only
                # question worth asking at run end: did any indicator
                # leave the range its own formula defines?
                #
                # Derived from the sink rather than from counters kept
                # during the run: the sink already retains every record,
                # so this costs one pass at shutdown and keeps the hot
                # path free of tallying state.
                try:
                    from src.core.signal_contract import get_sink as _gs
                    # 10.2 — the prefix is a NAMED CONSTANT owned by the
                    # engine that emits it, and the leaf is taken by
                    # that constant's own length. The pair used to be a
                    # literal `"ta.raw."` here and a hardcoded 7 on the
                    # next line, which the rename would have silently
                    # decoupled: the filter matches nothing, and the
                    # rollup below still emits, reporting 0 violations
                    # over 0 indicators. A false green from an
                    # instrument built to catch indicator faults.
                    from src.trading.ta_engine import TA_RAW_PREFIX
                    _sink = _gs()
                    if _sink is not None:
                        _per: dict = {}
                        _firsts: dict = {}
                        for _r in _sink.records():
                            if not _r.name.startswith(TA_RAW_PREFIX):
                                continue
                            _ind = _r.name[len(TA_RAW_PREFIX):]
                            _slot = _per.setdefault(
                                _ind, {"checked": 0, "violated": 0,
                                       "unchecked": 0})
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
                                        "window": _c.get("window")}
                        _viol = sum(v["violated"] for v in _per.values())
                        _s2("ta.07.002.invariant.invariants", actual=_viol, expected=0,
                            context={"per_indicator": _per,
                                     "first_violations": _firsts,
                                     "indicators": len(_per)})
                except Exception as _inv_exc:  # noqa: BLE001
                    logger.debug("invariant rollup failed: %s", _inv_exc)
                # Causality accounting. `expected` is not zero: on a
                # staggered fleet these skips are CORRECT and expected,
                # so the useful signal is the count and the share, not
                # a pass/fail.
                _s2("sim.06.003.counter.ticks_before_tape",
                    actual=_p.bot_ticks_before_tape,
                    context={"ticked": _p.bots_ticked,
                             "pct_of_attempted": (
                                 round(100.0 * _p.bot_ticks_before_tape
                                       / (_p.bot_ticks_before_tape
                                          + _p.bots_ticked), 2)
                                 if (_p.bot_ticks_before_tape
                                     + _p.bots_ticked) else 0.0)})
                _s2("sim.06.004.counter.trades_fired", actual=_p.trades_fired)
                _s2("sim.06.005.invariant.exceptions", actual=_p.exceptions, expected=0)
                # Which window was actually played — a run that cannot
                # say what data it consumed cannot be re-checked.
                #
                # ISSUE #110 SWEEP -- ASKS THE TAPE. This read
                # `getattr(self._exchange, "clock", None)`, and NO
                # exchange this controller has ever held carries a
                # `clock`. `FleetSimExchange` named it `master_clock`
                # (sim_exchange.py:247) and `CCXTConnector`, which
                # replaced it in v3.24.84, has no clock at all. So
                # `getattr` returned None, `_ts` fell to `[]`, and this
                # pin has reported `first_ts=None last_ts=None` on
                # EVERY healthy run since it was written -- a run that
                # cannot say what data it consumed, which is the one
                # thing the comment above demands.
                #
                # Older than the hand-over, and the same failure class:
                # a `getattr` default standing in for data it never had.
                _first = _last = None
                try:
                    if self._tape is not None:
                        _first, _last = self._tape.clock_window()
                except Exception as _wx:  # noqa: BLE001
                    logger.debug("window read failed: %s", _wx)
                _s2("sim.06.006.event.window_played",
                    actual={"first_ts": _first, "last_ts": _last,
                            "symbols": len(self._candles_by_symbol or {})})
            except Exception as _s2x:  # noqa: BLE001 - never break teardown
                logger.debug("S2 emit failed: %s", _s2x)

            # Sink LAST. Clearing it before the emitters above ran meant
            # every run-end signal fired into nothing — the first cut of
            # this did exactly that, and the file came out missing.
            try:
                from src.core.signal_contract import set_sink as _clr
                if self._signal_sink is not None:
                    self._signal_sink.flush()
                # v3.24.88 - RESTORE, do not clear. `None` here ended
                # process-wide collection the first time a replay was
                # run, so the platform went quiet for the rest of the
                # session and nobody could tell the difference.
                _clr(getattr(self, "_prior_sink", None))
            except Exception as _sfx:  # noqa: BLE001 - advisory
                logger.debug("signal sink teardown failed: %s", _sfx)
            self._perf(
                f"Fleet Replay finished: {self.progress.candles_played}"
                f" candles, {self.progress.trades_fired} sim trades, "
                f"{self.progress.exceptions} exceptions.")
            # v3.24.13 — close the run record FIRST, before the
            # telemetry/report block below, so a failure in reporting
            # cannot cost us the run's data.
            if self._run_log is not None:
                try:
                    # v3.24.19 — persist throughput. Diagnosing the
                    # 29x GUI-vs-headless slowdown meant hand-deriving
                    # candles/s from started_at/finished_at across 62
                    # run directories, because the run log recorded
                    # neither the rate nor which launcher produced it.
                    # A performance record you have to reconstruct is
                    # not a performance record.
                    _el = 0.0
                    try:
                        _el = max(
                            0.0,
                            time.time()
                            - float(self.progress.started_at_wall or 0.0))
                    except (TypeError, ValueError) as _el_exc:
                        logger.debug("elapsed calc: %s", _el_exc)
                    self._run_log.finish_run(summary={
                        "candles_played": self.progress.candles_played,
                        "total_candles": self.progress.total_candles,
                        "trades_fired": self.progress.trades_fired,
                        "bots": len(self._bots),
                        "exceptions": self.progress.exceptions,
                        "stop_requested": self.progress.stop_requested,
                        "elapsed_s": round(_el, 2),
                        "candles_per_s": (
                            round(self.progress.candles_played / _el, 2)
                            if _el > 0 else None),
                        "trades_per_1k_candles": (
                            round(1000.0 * self.progress.trades_fired
                                  / self.progress.candles_played, 2)
                            if self.progress.candles_played else None),
                        "visuals_attached": bool(
                            self._visual_refresh_cb is not None),
                        # v3.24.20 — the throughput predictor. Under the
                        # GUI pump each yield costs ~50 ms, so this ratio
                        # bounds candles/s directly.
                        "candles_skipped": self.progress.candles_skipped,
                        "bots_ticked": self.progress.bots_ticked,
                        "yields_emitted": self.progress.yields_emitted,
                        "yields_per_candle": (
                            round(self.progress.yields_emitted
                                  / self.progress.candles_played, 4)
                            if self.progress.candles_played else None),
                    })
                    _d = self._run_log.directory
                    self._perf(
                        f"Sim run persisted: {self._run_log.trade_count}"
                        f" trades, {self._run_log.gate_count} gates -> "
                        f"{_d if _d else '(not written)'}")
                    # v3.25.x - report the retention pass beside the
                    # run it just bounded.
                    #
                    # UNCONDITIONALLY, including the pass that removed
                    # nothing. A policy that speaks only when it acts
                    # is indistinguishable from a policy that is dead,
                    # and `sim/runs/` reached 674 MB in 102 directories
                    # with nothing watching it. One line per run end is
                    # the price of that being observable.
                    _ret = getattr(self._run_log, "retention", None)
                    if _ret is not None:
                        self._perf(_ret.summary())
                except Exception as _rl_exc:  # noqa: BLE001 - advisory
                    logger.warning(
                        "sim run log close failed: %s", _rl_exc)
            # v3.24.8 — dump the feature-telemetry report. This is
            # the operator-facing payoff: any declared Simulator
            # feature that never fired during this replay is named
            # explicitly instead of being invisible. Persist too, so
            # a feature that worked last session and went silent
            # shows up as STALLED on the next run.
            try:
                from src.core.feature_telemetry import get_telemetry
                _tel = get_telemetry()
                for _line in _tel.report_lines(scope="sim."):
                    self._perf(_line)
                _tel.save()
                # Markdown report — operator directive 2026-08-02.
                # Written to ~/.acervator_logs/feature_validation.md
                # so it is readable next session without the operator
                # pasting anything.
                _md = _tel.write_markdown_report(
                    scope="sim.",
                    run_context={
                        "Candles played": (
                            f"{self.progress.candles_played:,} / "
                            f"{self.progress.total_candles:,}"),
                        "Sim trades": f"{self.progress.trades_fired:,}",
                        "Bots": f"{len(self._bots)}",
                        "Tick exceptions": (
                            f"{self.progress.exceptions:,}"),
                    })
                if _md is not None:
                    self._perf(f"Feature validation report: {_md}")
            except Exception as _tel_exc:  # noqa: BLE001 - advisory
                logger.debug(
                    "feature telemetry report failed: %s", _tel_exc)
            self.stopped_event.set()


__all__ = ["FleetReplayController", "ReplayProgress"]


def clock_timestamps_from_candles(
    candles_by_symbol: dict,
) -> list[int]:
    """The master clock's index space, derived from raw candle rows.

    v3.24.70 (C20 / NF-18). Must stay bit-identical to
    ``MasterClock.from_series`` — sorted union of every series's
    timestamps — because this is the space anchor indices are compared
    against at run time. `tests/test_fleet_replay_anchors.py` pins the
    two against each other.

    Exists because of an ordering constraint, not a design preference:
    the panel builds anchors BEFORE `start()` calls `_build_sim()`, so
    no exchange and no clock exist yet. The panel does already hold the
    raw `candles` dict, so the union is derivable there. The
    alternative — moving anchor construction into the controller — is
    a larger restructure for the same answer.
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

    Operator directive 2026-08-03:

        "the read head reaches a candle, first checks for an expected
         trade, if none are identified, it skips."

        "We want the simulated indicators to be valid signals but we
         do not need to check it when nothing happened historically.
         Its only necessary to check every candle when customizing
         strategies or implementing new ones."

    For each historical trade we include the candle containing it
    PLUS the preceding ``warmup`` candles. The warm-up is what keeps
    the indicators valid: a bot evaluated on a cold TA window would
    diverge from live for reasons that have nothing to do with
    strategy, which would make the comparison meaningless.

    Overlapping warm-up ranges collapse naturally — this is a set —
    so clustered trades cost far less than warmup × trade_count.

    Returns an empty set when there are no trades; callers should
    treat that as "nothing to validate" rather than "skip everything".

    INDEX SPACE — v3.24.70 (C20 / NF-18). Pass `clock_ts_ms`.

    This returns positions the run loop compares against `candle_i`,
    and `candle_i` is the MasterClock CURSOR — an index into
    `sorted(union_of_every_series_timestamp)`. It is NOT a slot number
    on a 5-minute ruler.

    The two spaces agree only while the union is gapless, and the
    original implementation computed the ruler slot:

        idx = int((ts * 1000.0 - base_ts_ms) // step_ms)

    Every missing slot in the union shifts every later candle one
    position earlier, so a trade after k missing slots anchored k
    candles too late — or fell outside the bound and was dropped
    silently. Measured on the full-YTD union: 78 missing slots.

    The grid arithmetic is RETAINED for `clock_ts_ms=None` because it
    is exactly correct on a gapless union, and the existing callers in
    `tests/test_fleet_replay_controller.py` construct one. It is a
    fallback, not an equivalent: without the clock this function cannot
    know where the gaps are, so it assumes there are none.
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
