"""The Simulator's emitter network: one private ``EventBus`` per Sim host,
Live's ``LogManager`` over the sim bucket listening on it through
``sim_log_manager``, and ``RunEmitter``, the run context each runner emits
Live's topics through. ``RunEmitter.gate_decision``, ``trade_filled``,
``voting_snapshot`` and ``bot_line`` emit ``bot.gate_decision``,
``trade.filled``, ``bot.voting_panel_snapshot`` and ``bot.log`` with
``run_id``, ``mode``, ``candle_ts_ms`` and ``candle_at`` beside Live's fields,
and ``close`` reads the ``EmitObserver`` held over ``sim_contracts`` for the
run. ``scrum_fixture``, ``fold_fixture``, ``tranche_snapshot`` and
``compounding_snapshot`` spell the shapes ``ScrummingBot`` writes at fire time
from a walk's ``GateContext``. ``fill_line`` is Live's fill message for one
``SimTrade``.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import asdict
from typing import TYPE_CHECKING, Any, Callable, Iterator, Optional

from ..core.emit_contracts import CONTRACTS, EmitContract, EmitObserver
from ..core.event_bus import EventBus
from ..core.log_paths import gate_log_files, get_sim_dir
from ..core.logging_engine import LogManager
from ..core.signal_contract import (
    PROCESS_SINK_FLUSH_EVERY,
    SignalSink,
    emit,
    get_sink,
    route_thread,
    unroute_thread,
)
from .validation import iso_stamp

if TYPE_CHECKING:
    from ..trading.gate_chain import GateContext
    from .back_test import SimPosition, SimTrade
    from .fleet_source import SimBot

GATE_TOPIC = "bot.gate_decision"
TRADE_TOPIC = "trade.filled"
VOTING_TOPIC = "bot.voting_panel_snapshot"
BOT_LOG_TOPIC = "bot.log"

#: The topics ``CONTRACTS`` declares among the four the Simulator emits.
SIM_TOPICS = (TRADE_TOPIC, GATE_TOPIC)

#: The files ``LogManager.attach_to_bus`` writes the four topics into. The gate
#: topic reaches one file per exchange and sector, which ``sim_log_paths`` lists.
SIM_LOG_FILES = ("trade.log", "voting.log", "diagnostics.log")

SCRUM_SIDE = "sell"
FOLD_SIDE = "buy"
SCRUM_ACTION = "SCRUM"
FOLD_ACTION = "FOLD"

#: Live's ``SELL FILLED`` and ``BUY FILLED`` bot line, the dollars as
#: ``_execute_sell`` prints them, without the window's ``[asset/id]`` prefix.
FILL_LINE_FORMAT = (
    "{word}: {units:.6f} {asset} @ ${price:.8f} ({usd_word} ${usd:.5f}, fee ${fee:.5f})"
)
SCRUM_FILL_WORD = "SELL FILLED"
FOLD_FILL_WORD = "BUY FILLED"
SCRUM_USD_WORD = "gross"
FOLD_USD_WORD = "spent"

#: ``_on_bot_log_bus`` writes ``symbol`` and ``message`` only, so a
#: diagnostics row names its run and candle inside the message.
BOT_LINE_FORMAT = "{message} (run {run_id}, candle {candle_at})"

#: The sim signal sink's file under ``get_sim_dir``: ``sim/signals/session.jsonl``.
SIGNALS_DIR = "signals"
SIGNALS_FILE = "session.jsonl"

#: The run name the replay layer's tablet retrieval routes under.
RETRIEVAL_RUN = "retrieval"

#: The row ``routed_run`` emits on the process sink at each run's end.
SINK_ROUTED_SIGNAL = "sim.sink.routed"

#: The Activity Log line ``routed_run`` writes at each run's start.
SINK_LINE_FORMAT = "{run} signals: {path}"

_SIGNAL_SINK: Optional[SignalSink] = None
_SIGNAL_SINK_LOCK = threading.Lock()


def sim_signal_sink() -> SignalSink:
    """The one ``SignalSink`` per process at ``SIGNALS_FILE`` under
    ``SIGNALS_DIR`` of ``get_sim_dir``, built as ``install_process_sink``
    builds the process sink and opened on the first call."""
    global _SIGNAL_SINK
    with _SIGNAL_SINK_LOCK:
        if _SIGNAL_SINK is None:
            sink = SignalSink(flush_every=PROCESS_SINK_FLUSH_EVERY)
            sink.path = get_sim_dir() / SIGNALS_DIR / SIGNALS_FILE
            _SIGNAL_SINK = sink
        return _SIGNAL_SINK


@contextmanager
def routed_run(run: str, line: Callable[[str], None]) -> Iterator[SignalSink]:
    """Route the calling thread's emits to ``sim_signal_sink`` for the block,
    hand ``line`` the ``SINK_LINE_FORMAT`` line on entry, and on exit unroute,
    flush the sim sink and emit ``SINK_ROUTED_SIGNAL`` on the process sink."""
    sink = sim_signal_sink()
    thread = threading.get_ident()
    rows_before = int(sink.health()["emitted"])
    route_thread(sink)
    try:
        line(SINK_LINE_FORMAT.format(run=run, path=sink.path))
        yield sink
    finally:
        routed = get_sink() is sink
        unroute_thread()
        sink.flush()
        restored = get_sink() is not sink
        emit(
            SINK_ROUTED_SIGNAL,
            actual={
                "thread": thread,
                "run": run,
                "path": str(sink.path),
                "routed": routed,
                "restored": restored,
                "rows": int(sink.health()["emitted"]) - rows_before,
            },
            expected={"routed": True, "restored": True},
            ok=routed and restored,
        )
        process_sink = get_sink()
        if process_sink is not None:
            process_sink.flush()


def new_sim_bus() -> EventBus:
    """A private ``EventBus`` for one Sim host, never ``get_event_bus``."""
    return EventBus()


def sim_contracts() -> tuple[EmitContract, ...]:
    """The ``CONTRACTS`` entries whose topic is in ``SIM_TOPICS``."""
    return tuple(one for one in CONTRACTS if one.topic in SIM_TOPICS)


def sim_asset_class(symbol: str, exchange_id: str) -> str:
    """The sector ``portfolios.asset_class`` answers for one sim market.

    A market it answers None for takes ``default_gate_sector``, the same
    fallback ``migrate_legacy_gate_logs`` files an unlabelled record under.
    """
    from ..core.logging_engine import default_gate_sector
    from .portfolios import asset_class

    return str(asset_class(symbol, exchange_id) or "") or default_gate_sector()


def sim_log_paths() -> dict[str, str]:
    """Each of ``SIM_LOG_FILES`` under ``get_sim_dir``, plus every gate log.

    A gate key reads ``gate/<exchange>/<sector>/gate.log`` relative to the sim
    directory, one key per file ``gate_log_files`` lists there.
    """
    root = get_sim_dir()
    found = {name: str(root / name) for name in SIM_LOG_FILES}
    for one in gate_log_files(root):
        found[one.relative_to(root).as_posix()] = str(one)
    return found


def sim_log_manager(
    bus: Any, symbol_of: Optional[Callable[[str], str]] = None
) -> LogManager:
    """A ``LogManager`` over ``get_sim_dir`` attached to ``bus``, with
    ``symbol_of`` as its symbol resolver when given."""
    manager = LogManager(log_dir=get_sim_dir())
    if symbol_of is not None:
        manager.set_symbol_resolver(symbol_of)
    manager.attach_to_bus(bus)
    return manager


def fill_line(trade: SimTrade) -> str:
    """``FILL_LINE_FORMAT`` over one ``SimTrade``: ``SCRUM_FILL_WORD`` and
    ``SCRUM_USD_WORD`` for a scrum, the fold words otherwise."""
    from .back_test import SCRUM

    asset = str(trade.symbol).split("/")[0]
    is_scrum = trade.side == SCRUM
    return FILL_LINE_FORMAT.format(
        word=SCRUM_FILL_WORD if is_scrum else FOLD_FILL_WORD,
        units=float(trade.units),
        asset=asset,
        price=float(trade.price),
        usd_word=SCRUM_USD_WORD if is_scrum else FOLD_USD_WORD,
        usd=float(trade.usd),
        fee=float(trade.fee_usd),
    )


def _landing(reading: Any) -> dict:
    """The three ``landing_strip`` keys both fixtures carry, off ``reading``."""
    return {
        "landing_strip": bool(getattr(reading, "landing_strip", False)),
        "landing_strip_side": str(getattr(reading, "landing_strip_side", "") or ""),
        "landing_strip_candles": int(getattr(reading, "landing_strip_candles", 0) or 0),
    }


def scrum_fixture(context: GateContext, reading: Any = None) -> dict:
    """The ``scrum_fixture`` keys ``ScrummingBot.tick`` writes, read off
    ``context`` and ``reading``."""
    return {
        "delta": float(context.delta),
        "below_interval": bool(context.below_interval),
        "ticker_last": float(context.ticker_last),
        "bb_pos": float(context.bb_pos),
        **_landing(reading),
        "bb_upper_dt": float(context.bb_upper_dt),
        "bb_lower_dt": float(context.bb_lower_dt),
        "is_bullish": bool(context.is_bullish),
        "trend_hold": bool(context.trend_hold),
        "eff_direction": str(context.eff_direction_name or ""),
        "trend_strength": float(context.trend_strength),
        "scrum_ok": bool(context.scrum_ok),
        "target_fires": bool(context.target_fires),
        "bb_above_upper_dt": bool(context.bb_above_upper_dt),
        "cb_blocks_scrum": bool(context.cb_blocks_scrum),
        "htf_bias_dir": context.htf_bias_name,
        "htf_blocks_scrum": bool(context.htf_blocks_scrum),
        "flag_require_ta_bullish": bool(context.flag_require_ta_bullish),
        "flag_hold_in_uptrend": bool(context.flag_hold_in_uptrend),
        "flag_defer_to_htf": bool(context.flag_defer_to_htf),
        "eff_is_bullish": bool(context.eff_is_bullish),
        "eff_trend_hold": bool(context.eff_trend_hold),
        "eff_htf_blocks": bool(context.eff_htf_blocks_scrum),
        "hyst_ok_scrum_side": bool(context.hyst_ok_scrum_side),
        "hyst_armed_scrum_side": bool(context.hyst_armed_scrum_side),
        "hyst_ref_scrum_side": float(context.hyst_ref_scrum_side),
    }


def fold_fixture(context: GateContext, reading: Any = None) -> dict:
    """The ``fold_fixture`` keys ``ScrummingBot.tick`` writes, read off
    ``context`` and ``reading``."""
    return {
        "has_fold_tranches": bool(context.has_fold_tranches),
        "n_fold_tranches": int(context.n_fold_tranches),
        **_landing(reading),
        "is_bearish": bool(context.is_bearish),
        "eff_direction": str(context.eff_direction_name or ""),
        "fold_ok_midline": bool(context.fold_ok_midline),
        "mem253_at_ceiling": bool(context.mem253_at_ceiling),
        "mem253_smart_ceiling_usd": float(context.mem253_smart_ceiling_usd),
        "mem253_current_pos": float(context.mem253_current_pos),
        "bb_below_lower_dt": bool(context.bb_below_lower_dt),
        "cb_blocks_fold": bool(context.cb_blocks_fold),
        "htf_blocks_fold": bool(context.htf_blocks_fold),
        "flag_fold_require_ta_bearish": bool(context.flag_fold_require_ta_bearish),
        "flag_fold_defer_to_htf": bool(context.flag_fold_defer_to_htf),
        "eff_is_bearish": bool(context.eff_is_bearish),
        "eff_htf_blocks_fold": bool(context.eff_htf_blocks_fold),
        "hyst_ok_fold_side": bool(context.hyst_ok_fold_side),
        "hyst_armed_fold_side": bool(context.hyst_armed_fold_side),
        "hyst_ref_fold_side": float(context.hyst_ref_fold_side),
    }


def tranche_snapshot(position: Optional[SimPosition]) -> dict:
    """The ``_tranche_snapshot`` keys over ``position.fold_tranches``; a walk
    holds no stack, so the stack figures read zero."""
    fold = list(position.fold_tranches) if position is not None else []
    refs = [
        float(one.get("ref", 0) or 0)
        for one in fold
        if float(one.get("ref", 0) or 0) > 0
    ]
    return {
        "fold_count": len(fold),
        "fold_total_usd": round(sum(float(one.get("usd", 0) or 0) for one in fold), 6),
        "fold_total_units": round(
            sum(float(one.get("units", 0) or 0) for one in fold), 8
        ),
        "fold_ref_min": round(min(refs), 8) if refs else 0.0,
        "fold_ref_max": round(max(refs), 8) if refs else 0.0,
        "stack_count": 0,
        "stack_total_usd": 0.0,
        "stack_price_min": 0.0,
        "stack_price_max": 0.0,
    }


def compounding_snapshot(bot: SimBot, position: Optional[SimPosition]) -> dict:
    """The ``_compounding_snapshot`` keys for ``bot``: the anchor is the
    target, and ``fold_cycle_cap_consumed`` is ``position.cycle_cap_consumed_usd``."""
    target = float(bot.target_usd or 0.0)
    growth_pct = float(bot.max_target_growth_pct or 0.0)
    consumed = float(position.cycle_cap_consumed_usd) if position is not None else 0.0
    return {
        "target_balance": round(target, 6),
        "anchor_target_balance": round(target, 6),
        "accrued_growth_usd": 0.0,
        "max_target_growth_pct": growth_pct,
        "cycle_growth_budget_usd": round(target * growth_pct / 100.0, 6),
        "fold_cycle_cap_consumed": round(consumed, 6),
        "profit_folding_active": False,
    }


class RunEmitter:
    """One run's emitter over ``bus``: every row carries ``run_id`` and
    ``mode``, ``emitted`` counts each topic, and ``close`` reads the
    ``EmitObserver`` subscribed to ``sim_contracts`` for the run."""

    def __init__(self, bus: Optional[EventBus], run_id: str, mode: str) -> None:
        self.bus = bus
        self.run_id = str(run_id)
        self.mode = str(mode)
        self.emitted: dict[str, int] = {}
        self._observer = EmitObserver(contracts=sim_contracts())
        self._unsubscribe: list = []
        self._read: Optional[dict] = None
        if bus is not None:
            for contract in sim_contracts():
                self._unsubscribe.append(
                    bus.subscribe(contract.topic, self._observe_as(contract.topic))
                )

    def _observe_as(self, topic: str) -> Callable[[Any], None]:
        """A subscriber handing ``event.data`` to ``EmitObserver.observe``
        under ``topic``."""

        def handler(event: Any) -> None:
            self._observer.observe(topic, getattr(event, "data", None) or {})

        return handler

    @property
    def live(self) -> bool:
        """True while ``bus`` is held and ``close`` has not run."""
        return self.bus is not None and self._read is None

    def stamp(self, candle_ts_ms: int) -> dict:
        """The four keys every row adds: ``run_id``, ``mode``,
        ``candle_ts_ms`` and ``candle_at``."""
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "candle_ts_ms": int(candle_ts_ms),
            "candle_at": iso_stamp(candle_ts_ms),
        }

    def _send(self, topic: str, **fields: Any) -> None:
        if not self.live:
            return
        self.emitted[topic] = self.emitted.get(topic, 0) + 1
        self.bus.emit(topic, **fields)

    def gate_decision(
        self,
        bot: SimBot,
        context: GateContext,
        armed: dict,
        candle_ts_ms: int,
        *,
        reading: Any = None,
        position: Optional[SimPosition] = None,
        tick: int = 0,
        trade_action: str = "",
        side: str = "",
        extra: Optional[dict] = None,
    ) -> None:
        """Emit ``GATE_TOPIC`` for ``bot`` with the fields
        ``_emit_gate_decision_at_fire`` puts in the event, the fixtures read
        off ``context`` and ``reading``, ``evaluated_at_tick`` as ``tick``, and
        ``extra`` merged beside them.

        ``asset_class`` comes from ``sim_asset_class``, so a sim decision is
        filed under the sector its live twin is filed under."""
        self._send(
            GATE_TOPIC,
            bot_id=bot.bot_id,
            exchange=bot.exchange_id,
            asset_class=sim_asset_class(bot.symbol, bot.exchange_id),
            symbol=bot.symbol,
            side=str(side or "").upper(),
            trade_action=str(trade_action or ""),
            scrum_armed=bool(armed.get("scrum_armed", False)),
            fold_armed=bool(armed.get("fold_armed", False)),
            scrum_blockers=list(armed.get("scrum_blockers") or []),
            fold_blockers=list(armed.get("fold_blockers") or []),
            evaluated_at_tick=int(tick),
            scrum_fixture=scrum_fixture(context, reading),
            fold_fixture=fold_fixture(context, reading),
            tranche_snapshot=tranche_snapshot(position),
            compounding_snapshot=compounding_snapshot(bot, position),
            **self.stamp(candle_ts_ms),
            **(extra or {}),
        )

    def trade_filled(self, trade: SimTrade, exchange: str = "") -> None:
        """Emit ``TRADE_TOPIC`` for ``trade`` on ``exchange`` with the fields
        the scrum and fold fire sites put in the event: ``side``, ``type``,
        ``price``, ``amount``, ``size``, ``profit`` and ``fee_usd``."""
        from ..trading.scrumming.sizing import sale_proceeds_usd
        from .back_test import SCRUM

        is_scrum = trade.side == SCRUM
        self._send(
            TRADE_TOPIC,
            bot_id=trade.bot_id,
            exchange=str(exchange or ""),
            symbol=trade.symbol,
            side=SCRUM_SIDE if is_scrum else FOLD_SIDE,
            type=SCRUM_ACTION if is_scrum else FOLD_ACTION,
            price=float(trade.price),
            amount=float(trade.units),
            size=(
                sale_proceeds_usd(float(trade.usd), float(trade.fee_usd))
                if is_scrum
                else float(trade.usd)
            ),
            profit=0,
            fee_usd=float(trade.fee_usd),
            operator_initiated=False,
            **self.stamp(trade.ts_ms),
        )

    def voting_snapshot(
        self,
        bot: SimBot,
        summary: Any,
        candle_ts_ms: int,
        trade_action: str = "",
        side: str = "",
    ) -> None:
        """Emit ``VOTING_TOPIC`` for ``bot`` with ``summary`` as
        ``_emit_voting_panel_snapshot_at_fire`` puts it: ``asdict`` of the
        ``VotingSummary``, or ``{}`` when it is None."""
        panel: dict = {}
        if summary is not None:
            panel = asdict(summary)
        self._send(
            VOTING_TOPIC,
            bot_id=bot.bot_id,
            exchange=bot.exchange_id,
            symbol=bot.symbol,
            side=str(side or "").upper(),
            trade_action=str(trade_action or ""),
            panel=panel,
            **self.stamp(candle_ts_ms),
        )

    def bot_line(self, bot_id: str, message: str, candle_ts_ms: int = 0) -> None:
        """Emit ``BOT_LOG_TOPIC`` for ``bot_id`` with ``message`` under
        ``BOT_LINE_FORMAT``."""
        self._send(
            BOT_LOG_TOPIC,
            bot_id=str(bot_id),
            message=BOT_LINE_FORMAT.format(
                message=message,
                run_id=self.run_id,
                candle_at=iso_stamp(candle_ts_ms) or "none",
            ),
        )

    def close(self) -> dict:
        """Finish the ``EmitObserver``, remove its subscriptions and answer
        ``to_dict`` with ``emitted`` beside it; a second call answers the same."""
        if self._read is not None:
            return self._read
        for remove in self._unsubscribe:
            remove()
        self._unsubscribe = []
        self._observer.finish()
        self._read = {
            "emitted": dict(self.emitted),
            "observer": self._observer.to_dict(),
        }
        return self._read


__all__ = [
    "BOT_LINE_FORMAT",
    "BOT_LOG_TOPIC",
    "FILL_LINE_FORMAT",
    "FOLD_ACTION",
    "FOLD_FILL_WORD",
    "FOLD_SIDE",
    "FOLD_USD_WORD",
    "GATE_TOPIC",
    "RETRIEVAL_RUN",
    "SCRUM_ACTION",
    "SCRUM_FILL_WORD",
    "SCRUM_SIDE",
    "SCRUM_USD_WORD",
    "SIGNALS_DIR",
    "SIGNALS_FILE",
    "SIM_LOG_FILES",
    "SIM_TOPICS",
    "SINK_LINE_FORMAT",
    "SINK_ROUTED_SIGNAL",
    "TRADE_TOPIC",
    "VOTING_TOPIC",
    "RunEmitter",
    "compounding_snapshot",
    "fill_line",
    "fold_fixture",
    "new_sim_bus",
    "routed_run",
    "scrum_fixture",
    "sim_contracts",
    "sim_log_manager",
    "sim_asset_class",
    "sim_log_paths",
    "sim_signal_sink",
    "tranche_snapshot",
]
