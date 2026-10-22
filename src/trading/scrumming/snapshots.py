"""Forensic and telemetry snapshot emitters for ScrummingBot.

These write structured lines to the bus (bot.log / voting / gate logs) at
risk-block and trade-fire time. Every emitter is fail-soft: a snapshot must
never crash the trading tick.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import TYPE_CHECKING, Any, Optional

from ...core.event_bus import LINE_KIND_TRADE
from ..gate_vocabulary import gate_light_row, unknown_blockers

logger = logging.getLogger("acervator.scrumming")

if TYPE_CHECKING:
    from ..ta_engine import VotingSummary
    from ..scrumming_bot import ScrummingBot as _Host
else:
    _Host = object

# Gate-chain entries that count as risk gates for forensics; names match
# Gate.name in src/trading/gate_chain.py.
_RISK_GATE_NAMES: frozenset = frozenset(
    {
        "circuit_breaker_scrum",
        "circuit_breaker_fold",
        "smart_ceiling",
        "hysteresis_scrum",
        "hysteresis_fold",
    }
)

NEUTRAL = "NEUTRAL"
UNKNOWN_DIRECTION = "UNKNOWN"
_PANEL_GROUPS: tuple[str, ...] = ("BULLISH", "BEARISH", NEUTRAL)
_DETAIL_KEYS: tuple[str, ...] = ("adx", "z", "er")

PANEL_ABSENT_TEXT = "Panel not computed on this tick."
NONE_TEXT = "none"
YES_TEXT = "yes"
NO_TEXT = "no"

#: The word the per-tick gate line opens with, and the two banks it reads.
GATE_LINE_PREFIX = "GATES"
_GATE_LINE_BANKS: tuple[tuple[str, str], ...] = (("S", "Scrum"), ("F", "Fold"))
_LANDING_STRIP_SIDE_KEY = "landing_strip_side"
_SCRUM_FIXTURE_KEY = "scrum_fixture"
_FOLD_FIXTURE_KEY = "fold_fixture"

#: The per-side record key holding each refusal an override replaced, written
#: by ``ScrummingBot.tick`` as ``OVERRIDES_APPLIED_KEY``.
_OVERRIDES_APPLIED_KEY = "overrides_applied"

#: The word the GATES line opens an overridden clause with.
OVERRIDDEN_WORD = "overridden"

#: The ``tick_exit`` a row carries when ``ScrummingBot.tick`` reached the gate
#: chain and neither side fired.
GATE_CHAIN_EXIT = "gate-chain"

#: Ticks a refusal already in the record may hold before it writes a further
#: row, so a reader is never far from an anchor and a stopped bot reads as a
#: gap. The retained record's own tick rate is 315 evaluated ticks per bot per
#: hour, so this is about one anchor an hour.
GATE_ROW_TICK_CAP = 300

#: Distinct refusals one stretch remembers before it starts the record again.
#: The widest stretch in the retained record holds 62.
GATE_ROW_KEY_MEMORY = 64


def yes_no(flag: Any) -> str:
    """Render one flag as ``yes`` or ``no`` for a bot.log message."""
    return YES_TEXT if flag else NO_TEXT


def _build_panel_snapshot(summary: Optional[VotingSummary]) -> dict:
    """Capture ``{indicator: {dir, conf, weight, detail, detail_key}}`` from
    ``VotingSummary.signals``, NEUTRAL voters included. Returns ``{}`` when
    ``summary`` is None.
    """
    if summary is None:
        return {}
    snap: dict = {}
    for sig in summary.signals:
        try:
            dir_name = (
                sig.direction.name
                if hasattr(sig.direction, "name")
                else str(sig.direction)
            )
        except Exception:
            dir_name = UNKNOWN_DIRECTION
        # Headline detail cell (ADX raw, ZSc signed, KER raw).
        detail_key = ""
        detail_value = None
        for key in _DETAIL_KEYS:
            if key in (sig.details or {}):
                detail_key = key
                detail_value = sig.details[key]
                break
        snap[sig.indicator] = {
            "dir": dir_name,
            "conf": round(float(sig.confidence), 3),
            "weight": round(float(sig.weight), 3),
            "detail": detail_value,
            "detail_key": detail_key,
        }
    return snap


def _panel_counts(panel: dict) -> str:
    """The three direction counts one panel snapshot holds, as one sentence.

    ``_panel_line`` opens with it and the GATES line carries it alone.
    """
    tally: dict[str, int] = {name: 0 for name in _PANEL_GROUPS}
    for cell in panel.values():
        direction = str(cell.get("dir", "") or UNKNOWN_DIRECTION)
        tally[direction] = tally.get(direction, 0) + 1
    counts = ", ".join(f"{tally[name]} {name.lower()}" for name in _PANEL_GROUPS)
    return f"Panel {counts}."


def _light_key(lights: list) -> str:
    """One string naming every light's bank, label and state in draw order.

    Two ticks whose gate state is identical produce the same key, which is
    what the GATES line compares to decide whether it has anything to say.
    """
    return "|".join(
        f"{one.get('bank', '')}{one.get('label', '')}={one.get('state', '')}"
        for one in lights or []
    )


def _labels_in_state(lights: list, bank: str, state: str) -> list[str]:
    """The labels one bank's lights in ``state`` carry, in draw order."""
    return [
        str(one.get("label", ""))
        for one in lights or []
        if one.get("bank") == bank and one.get("state") == state
    ]


def _latched_risk_gates(blockers: list) -> list[str]:
    """The names in ``blockers`` that ``_RISK_GATE_NAMES`` holds.

    ``_gate_line_text`` names them, so the operator reads that the block
    holds until its own condition clears.
    """
    # Stable ordering for grep + diff.
    return sorted({str(one) for one in blockers or []} & _RISK_GATE_NAMES)


def bare_gate_name(blocker: Any) -> str:
    """A blocker phrase with the live figures it carries dropped.

    ``BB-below-upper-detect(bb_pos=0.39<0.88)`` answers
    ``BB-below-upper-detect``, so one gate refusing at two different prices
    answers one name. ``_gate_row_key`` groups a tick's refusal by these names.
    """
    text = str(blocker)
    for mark in ("(", "="):
        cut = text.find(mark)
        if cut > 0:
            text = text[:cut]
    return text


def _gate_row_key(
    tick_exit: str,
    scrum_armed: bool,
    fold_armed: bool,
    scrum_blockers: Optional[list],
    fold_blockers: Optional[list],
) -> tuple:
    """One tuple naming where a tick ended and which gates refused it.

    Two ticks refused by the same gates at the same exit answer the same key.
    ``_emit_gate_decision_at_quiet_tick`` compares it against the last row this
    bot wrote, so an answer the record already holds is not written again.
    """
    return (
        str(tick_exit),
        bool(scrum_armed),
        bool(fold_armed),
        tuple(sorted({bare_gate_name(one) for one in scrum_blockers or []})),
        tuple(sorted({bare_gate_name(one) for one in fold_blockers or []})),
    )


def _gate_line_text(
    lights: list, ticker_last: float, panel: dict, unknown: list, latched: list
) -> str:
    """The words the GATES line carries beside its lights.

    Each bank reads ``armed`` or its blocked labels, then its overridden
    labels under ``OVERRIDDEN_WORD``, and ``ticker_last``, ``panel``,
    ``latched`` and ``unknown`` close it.
    """
    banks = []
    for bank, title in _GATE_LINE_BANKS:
        blocked = _labels_in_state(lights, bank, "blocked")
        replaced = _labels_in_state(lights, bank, OVERRIDDEN_WORD)
        state = f"blocked {', '.join(blocked)}" if blocked else "armed"
        if replaced:
            state = f"{state}, {OVERRIDDEN_WORD} {', '.join(replaced)}"
        banks.append(f"{title} {state}.")
    said = " ".join(banks)
    tail = f" Latched {', '.join(latched)}." if latched else ""
    tail += f" Unmapped {', '.join(sorted(set(unknown)))}." if unknown else ""
    return (
        f"{GATE_LINE_PREFIX} {said} "
        f"Price ${ticker_last:.8f}. {_panel_counts(panel)}{tail}"
    )


def _panel_line(summary: Optional[VotingSummary]) -> str:
    """Render ``_build_panel_snapshot`` as a count and one group per
    direction, strongest ``conf`` first. A NEUTRAL vote holds zero
    ``conf``, so only its indicator name prints.
    """
    panel = _build_panel_snapshot(summary)
    if not panel:
        return PANEL_ABSENT_TEXT
    grouped: dict[str, list[tuple[float, str]]] = {name: [] for name in _PANEL_GROUPS}
    for indicator, cell in panel.items():
        direction = str(cell.get("dir", "") or UNKNOWN_DIRECTION)
        confidence = float(cell.get("conf", 0.0) or 0.0)
        text = indicator if direction == NEUTRAL else f"{indicator} {confidence:.2f}"
        reading = cell.get("detail")
        if reading is not None:
            shown = f"{reading:.4f}" if isinstance(reading, float) else reading
            text = f"{text} ({cell['detail_key']} {shown})"
        grouped.setdefault(direction, []).append((confidence, text))
    rows = [_panel_counts(panel)]
    for direction, voters in grouped.items():
        voters.sort(key=lambda one: (-one[0], one[1]))
        named = ", ".join(text for _, text in voters) or NONE_TEXT
        rows.append(f"{direction.lower()} {named}.")
    return " ".join(rows)


class SnapshotEmitterMixin(_Host):
    #: ``ScrummingBot.__init__`` sets it; the GATES line reads it to stay quiet
    #: while the gate state has not moved.
    _last_gate_light_key: str

    #: ``ScrummingBot.__init__`` sets both; the gate row reads them to write one
    #: row per distinct refusal per quiet stretch.
    _gate_row_keys_seen: set
    _ticks_since_gate_row: int

    # One sentence of the docstring below is overtaken. Quoted whole:
    #   "The StatusLog widget detects the prefix and colors by stage (SENT /
    #   PLACED / FILLED / CANCELLED)."
    # The emit names ``LINE_KIND_TRADE``, and ``stage_color`` reads the stage.
    # ``STAGE_COLORS`` names SENT, PLACED, FILLED and REFUSED; no caller in the
    # tree passes CANCELLED or PLACED.
    def _emit_trade_notification(self, role: str, stage: str, extra: str = "") -> None:
        """Emit a uniformly-formatted trade notification.

        Format: ``TRADE NOTIFICATION: <ROLE>: <SYMBOL>: <STAGE>[ — <extra>]``.
        ``role`` is the trade role (SCRUM/FOLD/INITIAL, MANUAL_*,
        WIRE_STACK_*, CARTRIDGE_*, HEDGE, DIST, …). ``stage`` is SENT before
        ``guarded_place_order``, FILLED after the venue reports the fill, and
        REFUSED when a gate stopped the trade with no order sent.

        A sim bot holds a private bus, which is where sim isolation comes
        from, and the emit keeps the REFUSED reason a replay reads.
        """
        try:
            sym = self.config.symbol or self.config.target_asset
            msg = f"TRADE NOTIFICATION: {role}: {sym}: {stage}"
            if extra:
                msg += f" — {extra}"
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=msg,
                kind=LINE_KIND_TRADE,
            )
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s",
                "_emit_trade_notification",
                type(_sup).__name__,
                _sup,
            )

    def _chain_risk_gates(self, chain_result) -> list:
        """The ``_RISK_GATE_NAMES`` entries one ``ChainResult`` blocked on.

        ``_last_gate_state`` carries a phrase per condition the bot tests, and
        this adds the risk gates ``gate_chain`` reports under its own names.
        """
        try:
            named = [str(name) for name, _msg in (chain_result.blocked or [])]
        except Exception:
            return []
        return _latched_risk_gates(named)

    # Two sentences of the docstring below are overtaken. Quoted whole:
    #   "Write a RISK GATE line to bot.log when a risk gate blocked this
    #   side's chain, naming the blockers and the voter panel behind them."
    #   "Quiet by design: emits nothing when no risk gate is in the blocked
    #   list."
    # It writes one GATES line a tick carrying ``gate_light_row``'s nineteen
    # lights for both banks, and it is quiet while the light row is unchanged.
    def _emit_gate_light_line(
        self,
        scrum_result,
        fold_result,
        summary,
        ticker_last: float,
    ) -> None:
        """Write a RISK GATE line to bot.log when a risk gate blocked this
        side's chain, naming the blockers and the voter panel behind them.

        Risk gates (CircuitBreaker, SmartCeiling, Hysteresis) consume
        position/risk flags, not voter output, so their block message alone
        never shows the indicator state; this binds the two. Quiet by
        design: emits nothing when no risk gate is in the blocked list.
        """
        try:
            state = self._last_gate_state
            scrum_blockers = list(state.get("scrum_blockers") or [])
            scrum_blockers += self._chain_risk_gates(scrum_result)
            fold_blockers = list(state.get("fold_blockers") or [])
            fold_blockers += self._chain_risk_gates(fold_result)
            fixture = state.get(_SCRUM_FIXTURE_KEY) or {}
            scrum_replaced = list(fixture.get(_OVERRIDES_APPLIED_KEY) or [])
            fold_replaced = list(
                (state.get(_FOLD_FIXTURE_KEY) or {}).get(_OVERRIDES_APPLIED_KEY) or []
            )
            lights = gate_light_row(
                scrum_armed=bool(state.get("scrum_armed", False)),
                fold_armed=bool(state.get("fold_armed", False)),
                scrum_blockers=scrum_blockers,
                fold_blockers=fold_blockers,
                landing_strip_side=str(fixture.get(_LANDING_STRIP_SIDE_KEY, "") or ""),
                scrum_overridden=scrum_replaced,
                fold_overridden=fold_replaced,
            )
            key = _light_key(lights)
            # A host without the attribute draws every tick; it never goes dark.
            if key == getattr(self, "_last_gate_light_key", ""):
                return
            self._last_gate_light_key = key
            unknown = unknown_blockers(
                scrum_blockers + scrum_replaced
            ) + unknown_blockers(fold_blockers + fold_replaced)
            latched = _latched_risk_gates(scrum_blockers + fold_blockers)
            panel = _build_panel_snapshot(summary)
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=_gate_line_text(lights, ticker_last, panel, unknown, latched),
                lights=lights,
            )
            # The whole voter panel and the blocker phrases the pane no longer
            # draws; system.log keeps them for the Console tab to read.
            logger.info(
                "Bot %s GATES %s | scrum %s | fold %s | %s",
                self.bot_id[:8],
                key,
                scrum_blockers,
                fold_blockers,
                _panel_line(summary),
            )
        except Exception as exc:
            # Don't disrupt the tick if the forensic emit itself fails.
            # Log at debug for diagnostics but do not propagate.
            try:
                logger.debug(
                    "Bot %s risk-gate snapshot emit failed: %s: %s",
                    self.bot_id[:8],
                    type(exc).__name__,
                    exc,
                )
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "_emit_gate_light_line",
                    type(_sup).__name__,
                    _sup,
                )

    def _emit_trade_fire_snapshot(
        self,
        side: str,
        summary,
        ticker_last: float,
        decision_extra: Optional[dict] = None,
    ) -> None:
        """Write a TRADE FIRED line to bot.log when a SCRUM or FOLD
        decision fires, the fired-side companion to
        ``_emit_risk_gate_snapshot``'s blocked-side line. ``decision_extra``
        is optional side-specific context printed after the price.
        """
        try:
            extra_str = ""
            if decision_extra:
                # Sort keys for deterministic output.
                extra_kv = ", ".join(
                    f"{k} {v}" for k, v in sorted(decision_extra.items())
                )
                extra_str = f"{extra_kv}. "
            msg = (
                f"TRADE FIRED [{side.upper()}] at ${ticker_last:.8f}. "
                f"{extra_str}"
                f"{_panel_line(summary)}"
            )
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=msg,
            )
        except Exception as exc:
            try:
                logger.debug(
                    "Bot %s trade-fire snapshot emit failed: %s: %s",
                    self.bot_id[:8],
                    type(exc).__name__,
                    exc,
                )
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "_emit_trade_fire_snapshot",
                    type(_sup).__name__,
                    _sup,
                )

    def _emit_voting_panel_snapshot_at_fire(
        self,
        side: str,
        trade_action: str,
    ) -> None:
        """Emit ``bot.voting_panel_snapshot`` at trade-fire time so the
        VotingSummary that drove the trade lands in voting.log alongside it.

        Called after each ``trade.filled`` emit. Fail-soft: when
        ``self._last_summary`` is None (startup window, manual-fire bypass)
        it emits ``panel={}`` rather than skipping.
        """
        try:
            panel: dict = {}
            try:
                _summary = getattr(self, "_last_summary", None)
                if _summary is not None:
                    panel = asdict(_summary)
            except Exception:
                panel = {}
            self._bus.emit(
                "bot.voting_panel_snapshot",
                bot_id=self.bot_id,
                exchange=getattr(self.config, "exchange_id", "") or "",
                symbol=getattr(self.config, "symbol", "") or "",
                side=str(side or "").upper(),
                trade_action=str(trade_action or "") or "",
                panel=panel,
            )
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s",
                "_emit_voting_panel_snapshot_at_fire",
                type(_sup).__name__,
                _sup,
            )

    def _emit_gate_decision_at_fire(
        self,
        side: str,
        trade_action: str,
    ) -> None:
        """Emit ``bot.gate_decision`` after each ``trade.filled`` so every
        fired trade has a paired gate.log row.

        ``self._last_gate_state`` is read at fire time. In-tick sites see
        state just refreshed by the scrum/fold evaluators; out-of-tick sites
        (manual fire, self_destruct, manual rebalance, detonation) see the
        most-recent autonomous tick's state — informational, not
        authoritative (the consumer differentiates via trade_action).

        ``asset_class`` carries ``BotContainer._asset_class`` for the traded
        symbol, which is the sector ``LogManager._gate_writer_for`` files the
        decision under.
        """
        symbol = getattr(self.config, "symbol", "") or ""
        try:
            self._bus.emit(
                "bot.gate_decision",
                bot_id=self.bot_id,
                exchange=getattr(self.config, "exchange_id", "") or "",
                asset_class=self._asset_class(symbol),
                symbol=symbol,
                side=str(side or "").upper(),
                trade_action=str(trade_action or "") or "",
                scrum_armed=bool(self._last_gate_state.get("scrum_armed", False)),
                fold_armed=bool(self._last_gate_state.get("fold_armed", False)),
                scrum_blockers=list(self._last_gate_state.get("scrum_blockers") or []),
                fold_blockers=list(self._last_gate_state.get("fold_blockers") or []),
                scrum_fixture=self._last_gate_state.get("scrum_fixture"),
                fold_fixture=self._last_gate_state.get("fold_fixture"),
                tranche_snapshot=self._tranche_snapshot(),
                compounding_snapshot=self._compounding_snapshot(),
            )
            # A fire ends the quiet stretch, so the next refusal writes a row.
            self._gate_row_keys_seen.clear()
            self._ticks_since_gate_row = 0
        except Exception as _gate_exc:  # noqa: BLE001
            # Counted in telemetry, so an unpaired gate row stays visible.
            try:
                from ...core.feature_telemetry import get_telemetry

                get_telemetry().record_exception("live.gate_decision.emit", _gate_exc)
            except Exception as _sup:  # noqa: BLE001,S110
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "_emit_gate_decision_at_fire",
                    type(_sup).__name__,
                    _sup,
                )
            logger.debug("Bot %s gate_decision emit failed: %s", self.bot_id, _gate_exc)

    def _emit_gate_decision_at_quiet_tick(self, tick_exit: str) -> None:
        """Emit ``bot.gate_decision`` for a tick that fired nothing, so the
        record answers why a trade did not happen.

        ``tick_exit`` names where ``ScrummingBot.tick`` ended.
        ``GATE_CHAIN_EXIT`` reads the scrum and fold banks the tick has just
        written; an earlier exit carries ``tick_exit`` as the blocker on both
        sides, because no gate was evaluated there.

        Each distinct refusal writes one row per stretch, and a stretch runs
        until a trade fires or ``GATE_ROW_TICK_CAP`` ticks pass with nothing
        new. A refusal the stretch already recorded writes nothing, so a gate
        that flips on and off between two states costs two rows rather than one
        a tick. ``quiet_ticks`` counts the ticks since this bot's last row, so
        an unchanged refusal reads differently from a bot that stopped ticking.
        """
        self._ticks_since_gate_row = int(self._ticks_since_gate_row) + 1
        at_gate_chain = str(tick_exit) == GATE_CHAIN_EXIT
        state: dict = self._last_gate_state if at_gate_chain else {}
        scrum_blockers = (
            list(state.get("scrum_blockers") or []) if at_gate_chain else [tick_exit]
        )
        fold_blockers = (
            list(state.get("fold_blockers") or []) if at_gate_chain else [tick_exit]
        )
        scrum_armed = bool(state.get("scrum_armed", False))
        fold_armed = bool(state.get("fold_armed", False))
        key = _gate_row_key(
            tick_exit, scrum_armed, fold_armed, scrum_blockers, fold_blockers
        )
        recorded = key in self._gate_row_keys_seen
        if recorded and self._ticks_since_gate_row < GATE_ROW_TICK_CAP:
            return
        quiet_ticks = self._ticks_since_gate_row
        symbol = getattr(self.config, "symbol", "") or ""
        try:
            self._bus.emit(
                "bot.gate_decision",
                bot_id=self.bot_id,
                exchange=getattr(self.config, "exchange_id", "") or "",
                asset_class=self._asset_class(symbol),
                symbol=symbol,
                tick_exit=str(tick_exit),
                quiet_ticks=int(quiet_ticks),
                scrum_armed=scrum_armed,
                fold_armed=fold_armed,
                scrum_blockers=scrum_blockers,
                fold_blockers=fold_blockers,
                scrum_fixture=state.get(_SCRUM_FIXTURE_KEY),
                fold_fixture=state.get(_FOLD_FIXTURE_KEY),
                evaluated_at_tick=state.get("evaluated_at_tick"),
                tranche_snapshot=self._tranche_snapshot(),
                compounding_snapshot=self._compounding_snapshot(),
            )
            if recorded or len(self._gate_row_keys_seen) >= GATE_ROW_KEY_MEMORY:
                self._gate_row_keys_seen.clear()
            self._gate_row_keys_seen.add(key)
            self._ticks_since_gate_row = 0
        except Exception as _quiet_exc:  # noqa: BLE001
            # Counted in telemetry, so a missing refusal row stays visible.
            try:
                from ...core.feature_telemetry import get_telemetry

                get_telemetry().record_exception(
                    "live.gate_decision.quiet_emit", _quiet_exc
                )
            except Exception as _sup:  # noqa: BLE001,S110
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "_emit_gate_decision_at_quiet_tick",
                    type(_sup).__name__,
                    _sup,
                )
            logger.debug(
                "Bot %s quiet gate_decision emit failed: %s",
                self.bot_id,
                _quiet_exc,
            )

    def _tranche_snapshot(self) -> dict:
        """Fold + stack tranche aggregates at fire time (count, USD, unit
        totals, price extremes) — aggregates rather than full contents to
        keep gate.log small.
        """
        snap: dict = {}
        try:
            fold = list(getattr(self, "_fold_tranches", []) or [])
            f_usd = sum(float(t.get("usd", 0) or 0) for t in fold)
            f_units = sum(float(t.get("units", 0) or 0) for t in fold)
            f_refs = [
                float(t.get("ref", 0) or 0)
                for t in fold
                if float(t.get("ref", 0) or 0) > 0
            ]
            snap["fold_count"] = len(fold)
            snap["fold_total_usd"] = round(f_usd, 6)
            snap["fold_total_units"] = round(f_units, 8)
            snap["fold_ref_min"] = round(min(f_refs), 8) if f_refs else 0.0
            snap["fold_ref_max"] = round(max(f_refs), 8) if f_refs else 0.0
        except Exception as _f_exc:  # noqa: BLE001
            snap["fold_error"] = f"{type(_f_exc).__name__}"
        try:
            stack = list(getattr(self, "_stack_tranches", []) or [])
            s_prices = []
            s_usd = 0.0
            for t in stack:
                # Stack entries may be dicts or objects depending on
                # the path that created them — handle both.
                px = t.get("price") if isinstance(t, dict) else getattr(t, "price", 0)
                uu = t.get("usd") if isinstance(t, dict) else getattr(t, "usd", 0)
                if px:
                    s_prices.append(float(px))
                if uu:
                    s_usd += float(uu)
            snap["stack_count"] = len(stack)
            snap["stack_total_usd"] = round(s_usd, 6)
            snap["stack_price_min"] = round(min(s_prices), 8) if s_prices else 0.0
            snap["stack_price_max"] = round(max(s_prices), 8) if s_prices else 0.0
        except Exception as _s_exc:  # noqa: BLE001
            snap["stack_error"] = f"{type(_s_exc).__name__}"
        return snap

    def _compounding_snapshot(self) -> dict:
        """Target-growth state at fire time: anchor, live target, accrued
        delta between them, the per-cycle growth budget, and how much of the
        cap this cycle consumed — enough to answer whether a fold raised the
        target and, if not, why not.
        """
        snap: dict = {}
        try:
            target = float(getattr(self, "_target_balance", 0.0) or 0.0)
            anchor = float(getattr(self, "_anchor_target_balance", 0.0) or 0.0)
            growth_pct = float(
                getattr(self.config, "max_target_growth_pct", 1.0) or 0.0
            )
            snap["target_balance"] = round(target, 6)
            snap["anchor_target_balance"] = round(anchor, 6)
            # Positive => target has grown above anchor via compounding.
            snap["accrued_growth_usd"] = round(target - anchor, 6)
            snap["max_target_growth_pct"] = growth_pct
            snap["cycle_growth_budget_usd"] = round(anchor * growth_pct / 100.0, 6)
            snap["fold_cycle_cap_consumed"] = round(
                float(getattr(self, "_fold_cycle_cap_consumed", 0.0) or 0.0), 6
            )
            snap["profit_folding_active"] = bool(
                getattr(self.config, "profit_folding_active", False)
            )
        except Exception as _c_exc:  # noqa: BLE001
            snap["error"] = f"{type(_c_exc).__name__}"
        return snap
