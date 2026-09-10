"""The capture bounds on one Quintessence award, and the market allotment they bound.

``CaptureBounds.activate`` opens a ``MarketRotation`` window and sizes one
``MarketAllotment`` per drawn market from the volume snapshot ``EligiblePool``
carries, so ``max_participant_share`` has a pool to take 5% of. ``award``
refuses a second allotment inside one ``Activation``, an amount above that
share, an award still inside the candle cooldown, an amount the allotment cannot
pay, a grade no axis could score and a grade resting on one clamped axis. Every
granted award is recorded on the ``LocalTestnet`` this object was built over, so
a demo run is the same ``award`` path over a different chain.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Optional

from ..core.io_utils import atomic_write_json
from ..exchange.data_pool import TF_SECONDS
from .market_rotation import IN_ROTATION, MarketRotation, max_participant_share
from .quintessence_ledger import QUINTESSENCE_PER_FEE_USD

logger = logging.getLogger("acervator.capture_bounds")

#: Candles of the awarding bot's own timeframe that must close after an award.
COOLDOWN_CANDLES = 3

#: No cooldown runs shorter, so three 1m candles still wait out 15 minutes.
COOLDOWN_FLOOR_S = 900

#: Sub-scores a grade needs before it may curve an award.
MIN_SCORED_AXES = 1

#: Basis points past which the execution axis clamps and stops reading the fill.
#: Measured on 1,560 live fills: 87.7% sit past it, so distance alone is no bound.
EXECUTION_READABLE_BPS = 100.0

DEFAULT_CAPTURE_BOUNDS_PATH = Path.home() / ".acervator" / "capture_bounds.json"
CAPTURE_BOUNDS_FILE_VERSION = 1

CAPTURE_CONTRACT = "CaptureBounds"
AWARD_FUNCTION = "recordAward"
AWARDED_EVENT = "QuintessenceAwarded"

AWARDED = "awarded"
NOT_ACTIVATED = "not_activated"
GRADE_NOT_COMPUTED = "grade_not_computed"
SOLE_AXIS_CLAMPED = "sole_axis_clamped"
UNKNOWN_TIMEFRAME = "unknown_timeframe"
COOLDOWN_RUNNING = "cooldown_running"
ALLOTMENT_TAKEN = "allotment_taken"
ABOVE_SHARE_CEILING = "above_share_ceiling"
ALLOTMENT_EXHAUSTED = "allotment_exhausted"

_NUMBER_TYPES = (int, float, Decimal)


class CaptureRefusedError(RuntimeError):
    """Raised when a bound refuses an award, carrying that bound's ``reason``."""

    def __init__(self, reason: str, message: str) -> None:
        """Hold ``reason`` beside the sentence the bound refused with."""
        super().__init__(message)
        self.reason = reason


def _as_decimal(value: object, name: str) -> Decimal:
    """Return ``value`` as a finite non-negative Decimal; bool, str and NaN raise."""
    if type(value) is bool or type(value) not in _NUMBER_TYPES:
        raise TypeError(
            f"{name} must be int, float or Decimal, not {type(value).__name__}"
        )
    amount = value if isinstance(value, Decimal) else Decimal(str(value))
    if not amount.is_finite():
        raise ValueError(f"{name} must be finite, got {value!r}")
    if amount < 0:
        raise ValueError(f"{name} must not be negative, got {value!r}")
    return amount


def _as_grade(value: object) -> Decimal:
    """Return ``value`` as a Decimal grade of zero to one; outside that raises."""
    grade = _as_decimal(value, "grade_numeric")
    if grade > 1:
        raise ValueError(f"grade_numeric must be 0 to 1, got {value!r}")
    return grade


def _as_name(value: object, name: str) -> str:
    """Return ``value`` as a non-empty stripped string; every other value raises."""
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} must be a non-empty string, got {value!r}")
    return value.strip()


def activation_key(exchange_id: str, season: int) -> str:
    """The key one exchange's activation period is held under."""
    return f"{_as_name(exchange_id, 'exchange_id')}:{int(season)}"


def cooldown_seconds(ta_timeframe: str) -> int:
    """``COOLDOWN_CANDLES`` candles of ``ta_timeframe``, floored at ``COOLDOWN_FLOOR_S``.

    Raises ``CaptureRefusedError`` for a timeframe ``TF_SECONDS`` does not carry.
    """
    timeframe = str(ta_timeframe)
    candle_s = TF_SECONDS.get(timeframe)
    if candle_s is None:
        raise CaptureRefusedError(
            UNKNOWN_TIMEFRAME,
            f"{timeframe!r} is not a candle the platform measures; the cooldown "
            f"counts {COOLDOWN_CANDLES} candles of the awarding bot's own "
            f"timeframe, one of {', '.join(TF_SECONDS)}",
        )
    return max(COOLDOWN_CANDLES * int(candle_s), COOLDOWN_FLOOR_S)


def allot_by_volume(emission: object, volumes: dict[str, float]) -> dict[str, Decimal]:
    """Split ``emission`` across ``volumes``, the largest book taking the remainder.

    Raises ``ValueError`` for an empty ``volumes`` and for a total volume of zero.
    """
    total_emission = _as_decimal(emission, "emission")
    if not volumes:
        raise ValueError("an allotment needs at least one market to divide across")
    total_volume = Decimal(0)
    for symbol, volume in volumes.items():
        total_volume += _as_decimal(volume, f"volume of {symbol}")
    if total_volume == 0:
        raise ValueError(
            f"the {len(volumes)} markets carry no volume between them, so no "
            f"volume-proportional split of {total_emission} exists"
        )
    ordered = sorted(volumes, key=lambda symbol: (-float(volumes[symbol]), symbol))
    shares: dict[str, Decimal] = {}
    for symbol in ordered[1:]:
        volume = _as_decimal(volumes[symbol], f"volume of {symbol}")
        shares[symbol] = total_emission * volume / total_volume
    shares[ordered[0]] = total_emission - sum(shares.values(), Decimal(0))
    return shares


@dataclass(frozen=True)
class MarketAllotment:
    """One market's Quintessence pool for one activation period.

    ``pool`` is the snapshot ``allot_by_volume`` sized, and ``share_ceiling`` is
    the most one participant may take of it.
    """

    exchange_id: str
    season: int
    symbol: str
    quote_volume_24h: float
    pool: Decimal

    @property
    def share_ceiling(self) -> Decimal:
        """``max_participant_share`` of ``pool``, which is 5% of it."""
        return max_participant_share(self.pool)

    def to_dict(self) -> dict:
        """Return this allotment as a JSON-safe dict with every Decimal as a string."""
        return {
            "exchange_id": self.exchange_id,
            "season": self.season,
            "symbol": self.symbol,
            "quote_volume_24h": self.quote_volume_24h,
            "pool": str(self.pool),
            "share_ceiling": str(self.share_ceiling),
        }


@dataclass(frozen=True)
class Activation:
    """One exchange's activation period, and the pool each drawn market offers.

    ``commitment`` is the ``RotationWindow`` root that concealed the drawn set,
    and ``allotments`` holds one ``MarketAllotment`` a drawn market.
    """

    exchange_id: str
    season: int
    commitment: str
    emission: Decimal
    allotments: dict

    @property
    def key(self) -> str:
        """The key ``activation_key`` gives this ``exchange_id`` and ``season``."""
        return activation_key(self.exchange_id, self.season)

    def allotment_for(self, symbol: str) -> Optional[MarketAllotment]:
        """The ``MarketAllotment`` for ``symbol``, or None for a market not drawn."""
        return self.allotments.get(symbol)

    def to_dict(self) -> dict:
        """Return this activation as a JSON-safe dict."""
        return {
            "exchange_id": self.exchange_id,
            "season": self.season,
            "commitment": self.commitment,
            "emission": str(self.emission),
            "allotments": {k: v.to_dict() for k, v in self.allotments.items()},
        }


@dataclass(frozen=True)
class AwardRequest:
    """One Quintessence award offered against one market's allotment.

    ``scored_axes`` and ``execution_bps`` are the ``TradeGrade`` fields of the
    same name, and ``ta_timeframe`` is the awarding bot's configured timeframe.
    """

    exchange_id: str
    season: int
    symbol: str
    participant: str
    fee_usd: float
    grade_numeric: float
    scored_axes: int
    ta_timeframe: str
    execution_bps: Optional[float] = None
    at_epoch: Optional[float] = None

    @property
    def amount(self) -> Decimal:
        """``fee_usd`` times ``grade_numeric`` at ``QUINTESSENCE_PER_FEE_USD``."""
        fee = _as_decimal(self.fee_usd, "fee_usd")
        return fee * QUINTESSENCE_PER_FEE_USD * _as_grade(self.grade_numeric)

    @property
    def epoch(self) -> float:
        """``at_epoch``, or the current time while the caller leaves it unset."""
        return time.time() if self.at_epoch is None else float(self.at_epoch)


@dataclass(frozen=True)
class CaptureAward:
    """One granted award, and the bounds it passed on the way through.

    ``cooldown_until`` is the epoch second the participant's next award may
    arrive at, and ``pool_drawn`` is that market's allotment spent so far.
    """

    participant: str
    exchange_id: str
    season: int
    symbol: str
    amount: Decimal
    pool: Decimal
    share_ceiling: Decimal
    pool_drawn: Decimal
    ta_timeframe: str
    cooldown_candles: int
    cooldown_s: int
    cooldown_until: float
    tx_hash: str
    reason: str = AWARDED

    def to_dict(self) -> dict:
        """Return this award as a JSON-safe dict with every Decimal as a string."""
        return {
            "participant": self.participant,
            "exchange_id": self.exchange_id,
            "season": self.season,
            "symbol": self.symbol,
            "amount": str(self.amount),
            "pool": str(self.pool),
            "share_ceiling": str(self.share_ceiling),
            "pool_drawn": str(self.pool_drawn),
            "ta_timeframe": self.ta_timeframe,
            "cooldown_candles": self.cooldown_candles,
            "cooldown_s": self.cooldown_s,
            "cooldown_until": self.cooldown_until,
            "tx_hash": self.tx_hash,
            "reason": self.reason,
        }


class CaptureBounds:
    """Bounds what one participant takes of one market's Quintessence allotment.

    The ``LocalTestnet`` and the ``MarketRotation`` arrive by construction, so a
    demo run is one ``CaptureBounds`` over a different chain running ``award``.
    """

    def __init__(
        self,
        testnet,
        rotation: MarketRotation,
        bounds_path: str | Path | None = None,
    ) -> None:
        """Hold the chain, the ``MarketRotation`` and ``bounds_path``; no file is read."""
        self._testnet = testnet
        self._rotation = rotation
        self._path: Path = (
            Path(bounds_path) if bounds_path else DEFAULT_CAPTURE_BOUNDS_PATH
        )
        self._activations: dict[str, Activation] = {}
        self._taken: dict[str, set[str]] = {}
        self._drawn: dict[str, Decimal] = {}
        self._cooldown_until: dict[str, float] = {}
        self._state_lock = threading.RLock()

    @property
    def bounds_path(self) -> Path:
        """The file ``save`` writes and ``load`` reads."""
        return self._path

    @property
    def rotation(self) -> MarketRotation:
        """The ``MarketRotation`` ``activate`` draws its markets from."""
        return self._rotation

    # -- The activation and its allotments -----------------------------------

    def activate(
        self,
        exchange_id: str,
        season: int,
        emission: object,
        scout=None,
    ) -> Activation:
        """Open a ``MarketRotation`` window and size one allotment a drawn market.

        Splits ``emission`` by the ``quote_volume_24h`` each drawn market carries
        at this call.
        """
        exchange = _as_name(exchange_id, "exchange_id")
        key = activation_key(exchange, season)
        with self._state_lock:
            if key in self._activations:
                raise CaptureRefusedError(
                    ALLOTMENT_TAKEN,
                    f"{key} is already activated and holds "
                    f"{len(self._activations[key].allotments)} market allotments",
                )
        pool = self._rotation.eligible_pool(exchange, season, scout)
        window = self._rotation.open_window(pool)
        volumes = {
            row.symbol: row.quote_volume_24h
            for row in pool.markets
            if self._rotation.reward_reason(exchange, row.symbol) == IN_ROTATION
        }
        shares = allot_by_volume(emission, volumes)
        allotments = {
            symbol: MarketAllotment(
                exchange_id=exchange,
                season=int(season),
                symbol=symbol,
                quote_volume_24h=volumes[symbol],
                pool=share,
            )
            for symbol, share in shares.items()
        }
        activation = Activation(
            exchange_id=exchange,
            season=int(season),
            commitment=window.commitment,
            emission=_as_decimal(emission, "emission"),
            allotments=allotments,
        )
        with self._state_lock:
            self._activations[key] = activation
            self.save()
        logger.info(
            "%s activated: %s Quintessence across %d drawn markets under %s",
            key,
            activation.emission,
            len(allotments),
            window.commitment[:16],
        )
        return activation

    def activation_for(self, exchange_id: str, season: int) -> Optional[Activation]:
        """The ``Activation`` held for ``exchange_id`` and ``season``, or None."""
        return self._activations.get(activation_key(exchange_id, season))

    def close_activation(self, exchange_id: str, season: int) -> tuple:
        """Close the rotation window and drop this activation's allotments and takes.

        Returns the ``RotationReveal`` and the ``MarketAllotment`` entries it held.
        """
        key = activation_key(exchange_id, season)
        with self._state_lock:
            activation = self._activations.get(key)
            if activation is None:
                raise CaptureRefusedError(
                    NOT_ACTIVATED, f"{key} holds no activation to close"
                )
        reveal = self._rotation.close_window(activation.exchange_id)
        with self._state_lock:
            del self._activations[key]
            self._taken.pop(key, None)
            for symbol in activation.allotments:
                self._drawn.pop(f"{key}|{symbol}", None)
            self.save()
        logger.info("%s closed; %d allotments retired", key, len(activation.allotments))
        return (reveal, activation.allotments)

    # -- The bounds ----------------------------------------------------------

    def cooldown_remaining_s(self, participant: str, at_epoch: float) -> float:
        """Seconds left on ``participant``'s cooldown, never below zero."""
        until = self._cooldown_until.get(_as_name(participant, "participant"), 0.0)
        return max(0.0, until - float(at_epoch))

    def pool_drawn(self, exchange_id: str, season: int, symbol: str) -> Decimal:
        """The Quintessence already awarded from one market's allotment."""
        key = activation_key(exchange_id, season)
        return self._drawn.get(f"{key}|{_as_name(symbol, 'symbol')}", Decimal(0))

    def may_award(self, request: AwardRequest) -> str:
        """``AWARDED`` while every bound admits ``request``, else the refusing reason."""
        try:
            self._refusal_for(request)
        except CaptureRefusedError as refused:
            return refused.reason
        return AWARDED

    def _refusal_for(self, request: AwardRequest) -> tuple:
        """Raise ``CaptureRefusedError`` for the first bound that refuses ``request``.

        Returns the ``MarketAllotment``, the award amount and ``cooldown_seconds``.
        """
        participant = _as_name(request.participant, "participant")
        symbol = _as_name(request.symbol, "symbol")
        key = activation_key(request.exchange_id, request.season)
        activation = self._activations.get(key)
        allotment = None if activation is None else activation.allotment_for(symbol)
        if allotment is None:
            raise CaptureRefusedError(
                NOT_ACTIVATED,
                f"{symbol} holds no Quintessence allotment in {key}, so there is "
                f"no pool for an award to come out of",
            )
        axes = int(request.scored_axes)
        if axes < MIN_SCORED_AXES:
            raise CaptureRefusedError(
                GRADE_NOT_COMPUTED,
                f"the grade on this trade scored {axes} of four axes, so its "
                f"{request.grade_numeric} is the default and not a measurement; "
                f"an award needs at least {MIN_SCORED_AXES} scored axis",
            )
        bps = request.execution_bps
        clamped = bps is not None and abs(float(bps)) > EXECUTION_READABLE_BPS
        if clamped and axes == 1:
            raise CaptureRefusedError(
                SOLE_AXIS_CLAMPED,
                f"this grade scored execution and nothing else, and its reference "
                f"price sits {float(bps):+.1f} basis points from the fill, past "
                f"the {EXECUTION_READABLE_BPS:.0f} the axis reads; a reference "
                f"that far out is stale, so the one axis reports a clamp and the "
                f"grade of {request.grade_numeric} rests on nothing",
            )
        cooldown_s = cooldown_seconds(request.ta_timeframe)
        left = self.cooldown_remaining_s(participant, request.epoch)
        if left > 0:
            raise CaptureRefusedError(
                COOLDOWN_RUNNING,
                f"{participant} has {left:.0f}s left of a {cooldown_s}s cooldown "
                f"of {COOLDOWN_CANDLES} {request.ta_timeframe} candles; the gate "
                f"pays nothing until it clears",
            )
        if f"{participant}|{symbol}" in self._taken.get(key, set()):
            raise CaptureRefusedError(
                ALLOTMENT_TAKEN,
                f"{participant} already took an allotment of {symbol} in {key}; "
                f"one allotment a participant a market an activation period",
            )
        amount = request.amount
        ceiling = allotment.share_ceiling
        if amount > ceiling:
            raise CaptureRefusedError(
                ABOVE_SHARE_CEILING,
                f"{amount} Quintessence is above the {ceiling} ceiling on "
                f"{symbol}, which holds a pool of {allotment.pool}; one "
                f"participant takes at most 5% of a market's pool",
            )
        drawn = self.pool_drawn(request.exchange_id, request.season, symbol)
        if drawn + amount > allotment.pool:
            raise CaptureRefusedError(
                ALLOTMENT_EXHAUSTED,
                f"{symbol} has awarded {drawn} of its {allotment.pool} pool, "
                f"which leaves {allotment.pool - drawn} and cannot pay {amount}",
            )
        return (allotment, amount, cooldown_s)

    def award(self, request: AwardRequest) -> CaptureAward:
        """Grant ``request``, record it on the chain and open the cooldown.

        Raises ``CaptureRefusedError`` naming the first bound that refuses it.
        """
        participant = _as_name(request.participant, "participant")
        symbol = _as_name(request.symbol, "symbol")
        key = activation_key(request.exchange_id, request.season)
        with self._state_lock:
            allotment, amount, cooldown_s = self._refusal_for(request)
            drawn = (
                self.pool_drawn(request.exchange_id, request.season, symbol) + amount
            )
            until = request.epoch + cooldown_s
            self._taken.setdefault(key, set()).add(f"{participant}|{symbol}")
            self._drawn[f"{key}|{symbol}"] = drawn
            self._cooldown_until[participant] = until
            self.save()
        tx_hash = self._post_award(participant, allotment, amount, until)
        award = CaptureAward(
            participant=participant,
            exchange_id=allotment.exchange_id,
            season=allotment.season,
            symbol=symbol,
            amount=amount,
            pool=allotment.pool,
            share_ceiling=allotment.share_ceiling,
            pool_drawn=drawn,
            ta_timeframe=str(request.ta_timeframe),
            cooldown_candles=COOLDOWN_CANDLES,
            cooldown_s=cooldown_s,
            cooldown_until=until,
            tx_hash=tx_hash,
        )
        logger.info(
            "%s awarded %s Quintessence of %s in %s: %s of the %s pool drawn, "
            "cooldown %ds of %d %s candles",
            participant,
            amount,
            symbol,
            key,
            drawn,
            allotment.pool,
            cooldown_s,
            COOLDOWN_CANDLES,
            request.ta_timeframe,
        )
        return award

    def _post_award(
        self,
        participant: str,
        allotment: MarketAllotment,
        amount: Decimal,
        cooldown_until: float,
    ) -> str:
        """Send one award to the chain and emit ``AWARDED_EVENT``."""
        args = {
            "participant": participant,
            "exchange": allotment.exchange_id,
            "season": allotment.season,
            "symbol": allotment.symbol,
            "amount": str(amount),
            "shareCeiling": str(allotment.share_ceiling),
            "cooldownUntil": cooldown_until,
        }
        chain = self._testnet.chain
        tx = chain.send_tx(participant, CAPTURE_CONTRACT, AWARD_FUNCTION, args)
        chain.emit(tx.tx_hash, CAPTURE_CONTRACT, AWARDED_EVENT, args)
        return tx.tx_hash

    # -- Persistence ---------------------------------------------------------

    def save(self) -> Path:
        """Write the activations, the takes, the drawn totals and the cooldowns."""
        payload = {
            "version": CAPTURE_BOUNDS_FILE_VERSION,
            "cooldown_candles": COOLDOWN_CANDLES,
            "cooldown_floor_s": COOLDOWN_FLOOR_S,
            "activations": {k: v.to_dict() for k, v in self._activations.items()},
            "taken": {k: sorted(v) for k, v in self._taken.items()},
            "drawn": {k: str(v) for k, v in self._drawn.items()},
            "cooldown_until": dict(self._cooldown_until),
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        return atomic_write_json(self._path, payload, sort_keys=True)

    def load(self) -> CaptureBounds:
        """Fill the activations, takes, drawn totals and cooldowns from ``bounds_path``."""
        try:
            with open(self._path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except FileNotFoundError:
            return self
        except (OSError, ValueError) as exc:
            logger.warning("capture bounds record %s unreadable: %s", self._path, exc)
            return self
        for key, row in payload.get("activations", {}).items():
            self._activations[key] = Activation(
                exchange_id=row["exchange_id"],
                season=int(row["season"]),
                commitment=row["commitment"],
                emission=Decimal(str(row["emission"])),
                allotments={
                    symbol: MarketAllotment(
                        exchange_id=entry["exchange_id"],
                        season=int(entry["season"]),
                        symbol=entry["symbol"],
                        quote_volume_24h=float(entry["quote_volume_24h"]),
                        pool=Decimal(str(entry["pool"])),
                    )
                    for symbol, entry in row.get("allotments", {}).items()
                },
            )
        self._taken = {
            key: set(names) for key, names in payload.get("taken", {}).items()
        }
        self._drawn = {
            key: Decimal(str(total)) for key, total in payload.get("drawn", {}).items()
        }
        self._cooldown_until = {
            name: float(until)
            for name, until in payload.get("cooldown_until", {}).items()
        }
        return self

    def bounds_summary(self) -> dict:
        """The four bounds, the open activations and every running cooldown."""
        return {
            "bounds_path": str(self._path),
            "cooldown_candles": COOLDOWN_CANDLES,
            "cooldown_floor_s": COOLDOWN_FLOOR_S,
            "min_scored_axes": MIN_SCORED_AXES,
            "execution_readable_bps": EXECUTION_READABLE_BPS,
            "activations": {k: v.to_dict() for k, v in self._activations.items()},
            "taken": {k: sorted(v) for k, v in self._taken.items()},
            "drawn": {k: str(v) for k, v in self._drawn.items()},
            "cooldown_until": dict(self._cooldown_until),
        }
