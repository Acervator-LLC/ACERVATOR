"""Accumulation Shadows for ScrummingBot.

A sale in a bearish regime marks its fold tranche with ``SHADOW_KIND``. That
tranche's fold moves the units past ``units_at_scrum`` onto
``_shadow_tranches``, off ``_main_lots`` and ``_current_holdings``. A bullish
regime sends each row at its floor through ``_execute_detonation``, which sells
what the row stands above its cost and reseeds the rest into ``_main_lots``.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import replace
from typing import Any, Callable, Optional

from ...core.emit_contracts import FILL_SELL
from ..container.config import as_finite_float, shadow_switched_on
from ..otd_math import DistanceSettingUnreadable, opposing_sale_price
from ..stack_math import SHADOW_KIND, TRANCHE_KIND_KEY
from ..ta_engine import three_agree
from ..indicators.types import SignalDirection
from .sizing import (
    EVENT_ID_KEY,
    UNITS_DUST,
    opposing_event_id,
    priced_usd,
    shadow_take_units,
)

logger = logging.getLogger("acervator.scrumming")

REGIME_NONE = ""
REGIME_BEARISH = SignalDirection.BEARISH.name
REGIME_BULLISH = SignalDirection.BULLISH.name

SHADOW_UNITS_KEY = "units"
SHADOW_PRICE_KEY = "price"
SHADOW_AGE_KEY = "created_ts"
SHADOW_EVENT_LABEL = "SHADOW"
SHADOW_FILL_KIND = "SHADOW_DETONATION"
SHADOW_BOOKER = "_book_shadow_detonation"
SHADOW_RESEED_FLAG = "shadow_reseed"

EXIT_EVENT_KEY = "event"
EXIT_UNITS_KEY = "units"
EXIT_SALE_KEY = "sell"


def regime_of(summary: Any) -> str:
    """``REGIME_BEARISH`` on a BEARISH ``summary``, which only marks a row, and
    ``REGIME_BULLISH`` on a BULLISH one ``three_agree`` holds on, which sells."""
    direction = summary.consensus_direction
    if direction == SignalDirection.BEARISH:
        return REGIME_BEARISH
    if direction == SignalDirection.BULLISH and three_agree(
        summary.consensus_confidence, summary.signals
    ):
        return REGIME_BULLISH
    return REGIME_NONE


def shadow_row(
    units: object, price: object, created_ts: float, serial: int = 0
) -> Optional[dict]:
    """One held row of ``units`` bought at ``price``, named by ``created_ts`` and
    ``serial``, None where either figure is not a positive finite number."""
    held = as_finite_float(units)
    paid = as_finite_float(price)
    if held is None or paid is None or held <= UNITS_DUST or paid <= 0.0:
        return None
    return {
        TRANCHE_KIND_KEY: SHADOW_KIND,
        SHADOW_UNITS_KEY: held,
        SHADOW_PRICE_KEY: paid,
        SHADOW_AGE_KEY: created_ts,
        EVENT_ID_KEY: opposing_event_id(f"{SHADOW_EVENT_LABEL}_{serial}", created_ts),
    }


def shadow_units(rows: list) -> float:
    """The ``SHADOW_UNITS_KEY`` figures of ``rows``, summed by ``math.fsum``."""
    return math.fsum(float(row[SHADOW_UNITS_KEY]) for row in rows)


def shadow_floor_price(row: dict, otd_pct: float) -> float:
    """``opposing_sale_price`` of ``row``'s ``SHADOW_PRICE_KEY`` at ``otd_pct``."""
    return opposing_sale_price(row[SHADOW_PRICE_KEY], otd_pct)


def shadow_rows_clearing(rows: list, price: float, otd_pct: float) -> list:
    """The rows in ``rows`` whose ``shadow_floor_price`` at ``otd_pct`` sits at or
    under ``price``."""
    return [row for row in rows if shadow_floor_price(row, otd_pct) <= price]


def shadow_sale_units(row: dict, price: float) -> float:
    """The units of ``row`` worth what ``price`` stands above its cost; the rest are
    worth what the row paid, and 0.0 answers a ``price`` at or under that cost."""
    paid = float(row[SHADOW_PRICE_KEY])
    if price <= paid or price <= 0.0:
        return 0.0
    return float(row[SHADOW_UNITS_KEY]) * (1.0 - paid / price)


def shadow_rows_from_saved(stored: object) -> list:
    """The rows of a saved ``stored`` list, dropping every entry ``shadow_row`` cannot
    rebuild and keeping each row's own identity."""
    if not isinstance(stored, list):
        return []
    rebuilt = []
    for entry in stored:
        if not isinstance(entry, dict):
            continue
        created = as_finite_float(entry.get(SHADOW_AGE_KEY)) or 0.0
        row = shadow_row(
            entry.get(SHADOW_UNITS_KEY), entry.get(SHADOW_PRICE_KEY), created
        )
        if row is None:
            continue
        row[EVENT_ID_KEY] = str(entry.get(EVENT_ID_KEY) or row[EVENT_ID_KEY])
        rebuilt.append(row)
    return rebuilt


class ShadowTrancheMixin:
    """Mark, fill, list and detonate Shadow Tranches beside the parent's own book."""

    # The rows this bot opened since it started; every write lands on the instance.
    _shadow_opened: int = 0

    # ScrummingBot supplies these at runtime; the annotations create no attributes.
    _apply_fold_target_growth: Callable[..., float]
    _announce_fill: Callable[..., None]
    _bus: Any
    _count_trade_volume: Callable[..., Any]
    _current_holdings: float
    _emit_gate_decision_at_fire: Callable[..., None]
    _emit_voting_panel_snapshot_at_fire: Callable[..., None]
    _execute_detonation: Callable[..., Any]
    _fill_fee_fields: Callable[..., dict]
    _fold_tranches: list[dict]
    _main_lots: list[dict]
    _quote_to_usd: float
    _read_shadow_regime: Callable[..., Any]
    _record_venue_units_after_fill: Callable[..., float]
    _refusal_is_new: Callable[..., bool]
    _refuse_unreadable_distance: Callable[..., None]
    _resting_order_for: Callable[..., Any]
    _route_unfoldable_proceeds: Callable[..., float]
    _shadow_regime: str
    _shadow_tranches: list[dict]
    bot_id: Any
    config: Any
    opposing_trade_distance_pct: Callable[..., float]

    def _shadow_held_units(self) -> float:
        """The units this bot's ``_shadow_tranches`` hold at the venue."""
        return shadow_units(self._shadow_tranches)

    def _net_of_shadows(self, currency: str, balance: Any) -> Any:
        """``balance`` less ``_shadow_held_units`` for ``config.target_asset``, ``balance``
        itself for any other currency or while no row stands."""
        if not self._shadow_tranches or currency != self.config.target_asset:
            return balance
        held = self._shadow_held_units()
        return replace(
            balance,
            free=max(0.0, float(balance.free or 0.0) - held),
            total=max(0.0, float(balance.total or 0.0) - held),
        )

    def _mark_shadow_rows(self, first_new_index: int) -> int:
        """Mark this sale's rows from ``first_new_index`` with ``SHADOW_KIND`` while the
        switch is on and ``_shadow_regime`` reads ``REGIME_BEARISH``."""
        if not shadow_switched_on(self.config):
            return 0
        if self._shadow_regime != REGIME_BEARISH:
            return 0
        fresh = self._fold_tranches[first_new_index:]
        for row in fresh:
            row[TRANCHE_KIND_KEY] = SHADOW_KIND
        if fresh:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"SHADOW OPENED: the regime reads {REGIME_BEARISH}, so "
                    f"{len(fresh)} fold tranche(s) from this sale are marked. Each "
                    f"buys back on the fold chain as usual, and the units past those "
                    f"the sale sold go to a Shadow Tranche."
                ),
            )
        return len(fresh)

    def _shadow_take(
        self, units: float, asked: float, booking: Optional[dict]
    ) -> float:
        """The units of one fold fill a Shadow Tranche takes under ``booking``'s
        ``eligible`` slices, 0.0 where none is marked or the take is dust."""
        eligible = (booking or {}).get("eligible")
        if not eligible:
            return 0.0
        share = min(1.0, float(units) / asked) if asked > 0 else 1.0
        take = shadow_take_units(eligible, units, share)
        return take if take > UNITS_DUST else 0.0

    def _book_shadow_take(self, units: float, price: float) -> None:
        """Move ``units`` of a settled fold bought at ``price`` onto a new row, off
        ``_current_holdings`` and ``_audited_venue_units``."""
        row = shadow_row(units, price, time.time(), self._shadow_opened)
        if row is None:
            return
        self._shadow_opened += 1
        self._shadow_tranches.append(row)
        self._current_holdings = max(0.0, self._current_holdings - units)
        self._record_venue_units_after_fill(-units)
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"SHADOW ACCUMULATED: {units:.8f} units bought @ ${price:.8f} went "
                f"to a Shadow Tranche. {len(self._shadow_tranches)} row(s) hold "
                f"{self._shadow_held_units():.8f} units, and no scrum, DIST sale "
                f"or stack rung may sell them."
            ),
        )

    async def _tick_shadow(self, ticker: Any) -> bool:
        """Read the regime while the switch is on or a row stands, and answer True when
        a bullish regime sent the rows at their floor through ``_execute_detonation``.

        Every send leaves ``_shadow_regime`` at ``REGIME_NONE``, so one reading sends at
        most one order, and a ``_book_shadow_detonation`` order still resting holds the
        next.
        """
        if not self._shadow_tranches and not shadow_switched_on(self.config):
            return False
        price = float(getattr(ticker, "last", 0.0) or 0.0)
        try:
            regime = await self._read_shadow_regime()
            if regime != REGIME_BULLISH or not self._shadow_tranches:
                return False
            if self._resting_order_for(SHADOW_BOOKER) is not None:
                return False
            otd_pct = self.opposing_trade_distance_pct()
            clearing = shadow_rows_clearing(self._shadow_tranches, price, otd_pct)
            if not clearing:
                self._hold_shadow_rows(price, otd_pct)
                return False
            self._shadow_regime = REGIME_NONE
            return bool(await self._execute_detonation(ticker, shadow_rows=clearing))
        except DistanceSettingUnreadable as unread:
            self._refuse_unreadable_distance(unread, "SHADOW", price)
        except Exception as exc:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"SHADOW DETONATION: check/execute raised: {exc}. "
                    f"Continuing tick."
                ),
            )
            logger.exception("Shadow detonation raised")
        return False

    def _hold_shadow_rows(self, price: float, otd_pct: float) -> None:
        """Log, once per held refusal, the lowest floor among ``_shadow_tranches`` that
        ``price`` has not reached."""
        if not self._refusal_is_new("shadow_floor", price):
            return
        lowest = min(self._shadow_tranches, key=lambda row: row[SHADOW_PRICE_KEY])
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"SHADOW HELD (opposing distance): the regime reads {REGIME_BULLISH}, "
                f"and the lowest of {len(self._shadow_tranches)} row(s) may sell at "
                f"${shadow_floor_price(lowest, otd_pct):.8f}, its buy price "
                f"${lowest[SHADOW_PRICE_KEY]:.8f} plus the {otd_pct:.2f}% opposing "
                f"trade distance. Price ${price:.8f}."
            ),
        )

    def _shadow_exit_plan(self, rows: list, price: float) -> tuple[float, dict]:
        """The units ``_execute_detonation`` sells for ``rows`` at ``price``, and the
        booking ``_book_shadow_detonation`` settles each piece of that sale from."""
        entries = [
            {
                EXIT_EVENT_KEY: row[EVENT_ID_KEY],
                EXIT_UNITS_KEY: float(row[SHADOW_UNITS_KEY]),
                EXIT_SALE_KEY: shadow_sale_units(row, price),
            }
            for row in rows
        ]
        return math.fsum(one[EXIT_SALE_KEY] for one in entries), {"rows": entries}

    async def _book_shadow_detonation(
        self,
        units: float,
        fill_price: float,
        asked: float,
        _first: bool,
        *,
        rows: list,
    ) -> None:
        """Settle one piece of a shadow detonation: each row in ``rows`` gives up the
        share of ``asked`` filled, ``_route_unfoldable_proceeds`` sends each wire its
        share, and what the sale left unsold joins ``_main_lots`` at ``fill_price`` under
        the cycle growth cap.
        """
        share = min(1.0, float(units) / asked) if asked > 0 else 1.0
        standing = {row[EVENT_ID_KEY]: row for row in self._shadow_tranches}
        kept_units = 0.0
        for entry in rows:
            row = standing.get(entry[EXIT_EVENT_KEY])
            if row is None:
                continue
            row[SHADOW_UNITS_KEY] = (
                float(row[SHADOW_UNITS_KEY]) - float(entry[EXIT_UNITS_KEY]) * share
            )
            kept_units += (
                float(entry[EXIT_UNITS_KEY]) - float(entry[EXIT_SALE_KEY])
            ) * share
        self._shadow_tranches = [
            row
            for row in self._shadow_tranches
            if float(row[SHADOW_UNITS_KEY]) > UNITS_DUST
        ]
        _quote = float(self._quote_to_usd or 1.0)
        fill_usd = priced_usd(float(units), fill_price, _quote) - (
            self._route_unfoldable_proceeds(float(units), fill_price, "shadow_exit")
            * _quote
        )
        self._count_trade_volume(units, fill_price)
        growth = 0.0
        if kept_units > UNITS_DUST:
            self._main_lots.append(
                {
                    "units": kept_units,
                    "initial_buy_price": fill_price,
                    SHADOW_RESEED_FLAG: True,
                }
            )
            self._current_holdings += kept_units
            self._record_venue_units_after_fill(kept_units)
            growth = self._apply_fold_target_growth(
                kept_units * fill_price, source=SHADOW_EVENT_LABEL
            )
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"SHADOW DETONATED: sold {units:.8f} @ ${fill_price:.8f} = "
                f"${fill_usd:.2f} of profit. {kept_units:.8f} units worth what the "
                f"rows paid joined the lots, target growth ${growth:.4f}. "
                f"{len(self._shadow_tranches)} row(s) still hold "
                f"{self._shadow_held_units():.8f} units."
            ),
        )
        self._emit_voting_panel_snapshot_at_fire(
            side="SELL", trade_action=SHADOW_FILL_KIND
        )
        self._emit_gate_decision_at_fire(side="SELL", trade_action=SHADOW_FILL_KIND)
        self._announce_fill(
            kind=SHADOW_FILL_KIND,
            side=FILL_SELL,
            units=units,
            price=fill_price,
            usd=fill_usd,
            profit=fill_usd,
            operator_initiated=False,
            fee=self._fill_fee_fields(fill_price),
        )

    def _return_shadows_to_lots(self, reason: str) -> float:
        """Move every held row back onto ``_main_lots`` at its own buy price, for an exit
        that sells the whole position, and answer the units moved."""
        rows = self._shadow_tranches
        if not rows:
            return 0.0
        units = shadow_units(rows)
        for row in rows:
            self._main_lots.append(
                {
                    "units": float(row[SHADOW_UNITS_KEY]),
                    "initial_buy_price": float(row[SHADOW_PRICE_KEY]),
                    SHADOW_RESEED_FLAG: True,
                }
            )
        self._shadow_tranches = []
        self._current_holdings += units
        self._record_venue_units_after_fill(units)
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"SHADOW RETURNED ({reason}): {units:.8f} units left "
                f"{len(rows)} Shadow Tranche(s) for the lots, so this exit "
                f"sells them with the position."
            ),
        )
        return units
