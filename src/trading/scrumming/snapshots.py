"""Forensic and telemetry snapshot emitters for ScrummingBot.

These write structured lines to the bus (bot.log / voting / gate logs) at
risk-block and trade-fire time. Every emitter is fail-soft: a snapshot must
never crash the trading tick.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Optional, TYPE_CHECKING

logger = logging.getLogger("acervator.scrumming")

if TYPE_CHECKING:
    from ..ta_engine import VotingSummary

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


def _build_panel_snapshot(summary: Optional[VotingSummary]) -> dict:
    """Capture a compact ``{indicator: {dir, conf, weight, detail}}`` dict
    from ``VotingSummary.signals``. NEUTRAL voters are kept (informative for
    forensics). Returns ``{}`` when ``summary`` is None (pre-TA tick).
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
            dir_name = "UNKNOWN"
        # Headline detail cell (ADX raw, ZSc signed, KER raw).
        detail_value = None
        for key in ("adx", "z", "er"):
            if key in (sig.details or {}):
                detail_value = sig.details[key]
                break
        snap[sig.indicator] = {
            "dir": dir_name,
            "conf": round(float(sig.confidence), 3),
            "weight": round(float(sig.weight), 3),
            "detail": detail_value,
        }
    return snap


class SnapshotEmitterMixin:

    # Supplied by ScrummingBot at runtime; declared so a type
    # checker can resolve them. Annotations only: no attribute is
    # created and the runtime base stays `object`.
    _bus: Any
    _last_gate_state: dict
    bot_id: Any
    config: Any

    def _emit_trade_notification(self, role: str, stage: str, extra: str = "") -> None:
        """Emit a uniformly-formatted trade lifecycle notification.

        Format: ``TRADE NOTIFICATION: <ROLE>: <SYMBOL>: <STAGE>[ — <extra>]``.
        The StatusLog widget detects the prefix and colors by stage (SENT /
        PLACED / FILLED / CANCELLED). ``role`` is the trade role
        (SCRUM/FOLD/INITIAL, MANUAL_*, WIRE_STACK_*, CARTRIDGE_*, HEDGE,
        DIST, …); ``stage`` is one of SENT/PLACED/FILLED/CANCELLED.

        No sim-mode guard here: sim isolation comes from a sim bot holding a
        private bus, so emitting is safe and preserves the CANCELLED-reason
        trace that a replay needs.
        """

        try:
            sym = self.config.symbol or self.config.target_asset
            msg = f"TRADE NOTIFICATION: {role}: {sym}: {stage}"
            if extra:
                msg += f" — {extra}"
            self._bus.emit("bot.log", bot_id=self.bot_id, message=msg)
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s",
                "_emit_trade_notification",
                type(_sup).__name__,
                _sup,
            )

    def _emit_risk_gate_snapshot(
        self,
        side: str,
        chain_result,
        summary,
        ticker_last: float,
    ) -> None:
        """Write a RISK GATE SNAPSHOT line to bot.log when a risk gate
        blocked this side's chain, capturing the full voter panel at the
        moment of the block.

        Risk gates (CircuitBreaker, SmartCeiling, Hysteresis) consume
        position/risk flags, not voter output, so their block message alone
        never shows the indicator state; this binds the two. Quiet by
        design: emits nothing when no risk gate is in the blocked list.
        """
        try:
            blocked_names = {n for n, _msg in (chain_result.blocked or [])}
        except Exception:
            return
        risk_blockers = blocked_names & _RISK_GATE_NAMES
        if not risk_blockers:
            return
        try:
            snapshot = _build_panel_snapshot(summary)
            # Stable ordering for grep + diff; JSON-shaped dict stays
            # machine-parseable and human-skimmable.
            risk_blockers_sorted = sorted(risk_blockers)
            msg = (
                f"RISK GATE SNAPSHOT [{side.upper()}] "
                f"risk_blockers={risk_blockers_sorted} "
                f"ticker_last={ticker_last:.6g} "
                f"panel={snapshot}"
            )
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=msg,
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
                    "_emit_risk_gate_snapshot",
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
        """Write a TRADE FIRED SNAPSHOT line to bot.log when a SCRUM or
        FOLD decision actually fires — the fired-side companion to
        ``_emit_risk_gate_snapshot``'s blocked-side line. ``decision_extra``
        is optional side-specific context surfaced under an ``extra`` key.
        """
        try:
            snapshot = _build_panel_snapshot(summary)
            extra_str = ""
            if decision_extra:
                # Sort keys for deterministic output.
                extra_kv = ", ".join(
                    f"{k}={v!r}" for k, v in sorted(decision_extra.items())
                )
                extra_str = f" extra={{{extra_kv}}}"
            msg = (
                f"TRADE FIRED SNAPSHOT [{side.upper()}] "
                f"ticker_last={ticker_last:.6g} "
                f"panel={snapshot}{extra_str}"
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
        """
        try:
            self._bus.emit(
                "bot.gate_decision",
                bot_id=self.bot_id,
                exchange=getattr(self.config, "exchange_id", "") or "",
                symbol=getattr(self.config, "symbol", "") or "",
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
        except Exception as _gate_exc:  # noqa: BLE001
            # Swallow so the trade path never breaks, but count the failure
            # via telemetry so an unpaired gate row is visible.
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
                getattr(self.config, "max_target_growth_pct", 0.0) or 0.0
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
