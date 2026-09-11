"""Movement across the world, derived from one record a journey leg.

``JourneyLeg`` carries the turn it opened, its two endpoints in whole steps and
its rate, and ``JourneyLeg.progress_at`` derives the steps travelled at any
later turn, so no turn writes a record. ``WorldJourneys.open_leg`` writes one
leg and ``_require_zone_covers_leg`` refuses one the named ``ZoneRegion`` does
not cover, while ``WorldJourneys.replay_progress`` rebuilds a leg from the
chain's own record and derives the same figures and ``mover_locator`` answers the
locator one mover's own latest leg reaches. ``terrain_rate`` and the
``encumbrance`` argument are the two multipliers on ``BASE_STEPS_PER_TURN``, and
neither carries a default.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal, localcontext
from pathlib import Path

from ..core.io_utils import atomic_write_json
from .world_grid import (
    SQUARE_STEPS,
    GridPosition,
    square_index,
    square_xy,
)

logger = logging.getLogger("acervator.world_movement")

#: Steps a mover covers in one world turn before any multiplier, one square.
BASE_STEPS_PER_TURN = SQUARE_STEPS

#: Decimal digits every figure ``progress_at`` derives is computed to.
MOVEMENT_PRECISION = 28

#: Steps across one square, read from ``SQUARE_STEPS`` so a step is one percent.
STEPS_PER_SQUARE = SQUARE_STEPS

JOURNEY_CONTRACT = "PoaJourneys"
OPEN_LEG_FUNCTION = "openLeg"
LEG_OPENED_EVENT = "LegOpened"

DEFAULT_JOURNEY_PATH = Path.home() / ".acervator" / "poa_journeys.json"
JOURNEY_FILE_VERSION = 1


class MovementError(RuntimeError):
    """Raised for a leg that does not move, a rate that is not positive, a turn before it opened."""


def absolute_steps(position: GridPosition, width: int) -> tuple[int, int]:
    """The whole steps from the grid's origin to ``position`` on a grid ``width`` across."""
    x, y = square_xy(position.square_index, width)
    return (
        x * STEPS_PER_SQUARE + position.step_x,
        y * STEPS_PER_SQUARE + position.step_y,
    )


def position_at_steps(step_x: int, step_y: int, width: int) -> GridPosition:
    """The ``GridPosition`` whole steps ``step_x`` and ``step_y`` from the origin name."""
    if step_x < 0 or step_y < 0:
        raise MovementError(
            f"({step_x}, {step_y}) steps is off the grid, which starts at (0, 0)"
        )
    square = square_index(step_x // STEPS_PER_SQUARE, step_y // STEPS_PER_SQUARE, width)
    return GridPosition(
        square_index=square,
        step_x=step_x % STEPS_PER_SQUARE,
        step_y=step_y % STEPS_PER_SQUARE,
    )


def leg_rate(terrain: Decimal, encumbrance: Decimal) -> Decimal:
    """``BASE_STEPS_PER_TURN`` under the ``terrain`` and ``encumbrance`` multipliers."""
    if terrain <= 0:
        raise MovementError(f"a terrain multiplier of {terrain} moves nobody")
    if encumbrance <= 0:
        raise MovementError(f"an encumbrance multiplier of {encumbrance} moves nobody")
    with localcontext() as ctx:
        ctx.prec = MOVEMENT_PRECISION
        return Decimal(BASE_STEPS_PER_TURN) * terrain * encumbrance


def leg_length_steps(span_x: int, span_y: int) -> Decimal:
    """The steps a leg spanning ``span_x`` and ``span_y`` runs, refusing a span of nothing."""
    if span_x == 0 and span_y == 0:
        raise MovementError("a leg spanning no step is not a leg")
    with localcontext() as ctx:
        ctx.prec = MOVEMENT_PRECISION
        return Decimal(span_x * span_x + span_y * span_y).sqrt()


def travelled_steps(rate: Decimal, turns: int, length: Decimal) -> Decimal:
    """The steps ``rate`` covers over ``turns``, held between nothing and ``length``."""
    if turns < 0:
        raise MovementError(f"{turns} turns is before the leg opened")
    with localcontext() as ctx:
        ctx.prec = MOVEMENT_PRECISION
        covered = rate * Decimal(turns)
        return max(Decimal(0), min(covered, length))


def turns_to_arrive(length: Decimal, rate: Decimal) -> int:
    """The whole turns ``rate`` needs to cover ``length``, rounding a part turn up."""
    if rate <= 0:
        raise MovementError(f"a rate of {rate} steps a turn arrives nowhere")
    with localcontext() as ctx:
        ctx.prec = MOVEMENT_PRECISION
        needed = length / rate
        return int(needed.to_integral_value(rounding=ROUND_CEILING))


@dataclass(frozen=True)
class JourneyLeg:
    """One constant-rate stretch across one ``zone_id``, ending at a terrain border.

    ``opened_turn``, the two endpoints and ``rate`` are every figure
    ``progress_at`` reads, so a leg stores no path.
    """

    journey_id: str
    world_id: str
    layer: int
    leg_index: int
    mover: str
    zone_id: str
    opened_turn: int
    from_step_x: int
    from_step_y: int
    to_step_x: int
    to_step_y: int
    rate: str
    open_tx: str

    @property
    def span(self) -> tuple[int, int]:
        """The steps this leg runs in ``x`` and in ``y``."""
        return self.to_step_x - self.from_step_x, self.to_step_y - self.from_step_y

    @property
    def length_steps(self) -> Decimal:
        """The steps ``span`` runs, through ``leg_length_steps``."""
        span_x, span_y = self.span
        return leg_length_steps(span_x, span_y)

    @property
    def rate_steps_per_turn(self) -> Decimal:
        """``rate`` as the ``Decimal`` ``travelled_steps`` reads."""
        return Decimal(self.rate)

    @property
    def arrival_turn(self) -> int:
        """The turn this leg reaches its own end, through ``turns_to_arrive``."""
        return self.opened_turn + turns_to_arrive(
            self.length_steps, self.rate_steps_per_turn
        )

    def progress_at(self, turn: int, width: int) -> dict:
        """Derive every movement figure this leg holds at ``turn``, writing nothing.

        Raises ``MovementError`` for a ``turn`` before ``opened_turn``.
        """
        if turn < self.opened_turn:
            raise MovementError(
                f"turn {turn} is before leg {self.leg_index} of journey "
                f"{self.journey_id} opened on turn {self.opened_turn}"
            )
        elapsed = turn - self.opened_turn
        length = self.length_steps
        rate = self.rate_steps_per_turn
        covered = travelled_steps(rate, elapsed, length)
        earlier = travelled_steps(rate, max(0, elapsed - 1), length)
        span_x, span_y = self.span
        with localcontext() as ctx:
            ctx.prec = MOVEMENT_PRECISION
            this_turn = covered - earlier
            part = covered / length
            step_x = Decimal(self.from_step_x) + Decimal(span_x) * part
            step_y = Decimal(self.from_step_y) + Decimal(span_y) * part
        here = position_at_steps(int(step_x), int(step_y), width)
        return {
            "journey_id": self.journey_id,
            "leg_index": self.leg_index,
            "zone_id": self.zone_id,
            "layer": self.layer,
            "mover": self.mover,
            "turn": turn,
            "opened_turn": self.opened_turn,
            "turns_elapsed": elapsed,
            "rate_steps_per_turn": str(rate),
            "length_steps": str(length),
            "travelled_steps": str(covered),
            "square_pct_this_turn": str(this_turn),
            "step_x": str(step_x),
            "step_y": str(step_y),
            "square_index": here.square_index,
            "square_step_x": here.step_x,
            "square_step_y": here.step_y,
            "has_arrived": covered == length,
        }

    def to_dict(self) -> dict:
        """Return this leg as a JSON-safe dict."""
        return {
            "journey_id": self.journey_id,
            "world_id": self.world_id,
            "layer": self.layer,
            "leg_index": self.leg_index,
            "mover": self.mover,
            "zone_id": self.zone_id,
            "opened_turn": self.opened_turn,
            "from_step_x": self.from_step_x,
            "from_step_y": self.from_step_y,
            "to_step_x": self.to_step_x,
            "to_step_y": self.to_step_y,
            "rate": self.rate,
            "open_tx": self.open_tx,
        }


def leg_from_chain(args: dict, mover: str, tx_hash: str) -> JourneyLeg:
    """Rebuild a ``JourneyLeg`` from the ``openLeg`` arguments the chain holds.

    ``mover`` comes from the transaction's own sender, which the leg record omits.
    """
    return JourneyLeg(
        journey_id=args["journey"],
        world_id=args["world"],
        layer=int(args["layer"]),
        leg_index=int(args["leg"]),
        mover=mover,
        zone_id=args["zone"],
        opened_turn=int(args["opened"]),
        from_step_x=int(args["fromX"]),
        from_step_y=int(args["fromY"]),
        to_step_x=int(args["toX"]),
        to_step_y=int(args["toY"]),
        rate=str(args["rate"]),
        open_tx=tx_hash,
    )


class WorldJourneys:
    """Holds every journey's legs and the terrain rate each zone applies.

    The ``LocalTestnet``, the ``PoaWorld`` and ``journey_path`` arrive by
    construction, so a demo run opens legs over a different chain through the
    same ``open_leg`` path.
    """

    def __init__(self, testnet, world, journey_path: str | Path | None = None) -> None:
        """Hold the chain, the ``PoaWorld`` and the record path, carrying no journey."""
        self._testnet = testnet
        self._world = world
        self._path: Path = Path(journey_path) if journey_path else DEFAULT_JOURNEY_PATH
        self._lock = threading.RLock()
        self._legs: dict[str, dict[str, list[JourneyLeg]]] = {}
        self._terrain: dict[str, dict[str, str]] = {}

    @property
    def journey_path(self) -> Path:
        """The file ``save`` writes and ``load`` reads."""
        return self._path

    @property
    def world(self):
        """The ``PoaWorld`` whose zones and grid width ``open_leg`` reads."""
        return self._world

    @property
    def world_ids(self) -> tuple[str, ...]:
        """The worlds this store holds a journey for, in opening order."""
        return tuple(self._legs)

    # -- The multiplier a zone's terrain applies ------------------------------

    def set_terrain_rate(
        self, world_id: str, zone_id: str, multiplier: Decimal
    ) -> Decimal:
        """Register the multiplier ``zone_id``'s terrain applies to ``BASE_STEPS_PER_TURN``."""
        held = Decimal(str(multiplier))
        if held <= 0:
            raise MovementError(
                f"zone {zone_id} of world {world_id} cannot apply a "
                f"multiplier of {held}; a terrain multiplier moves somebody"
            )
        self._world.zone(world_id, zone_id)
        with self._lock:
            self._terrain.setdefault(world_id, {})[zone_id] = str(held)
        self.save()
        logger.info(
            "zone %s of world %s multiplies %d steps a turn by %s",
            zone_id,
            world_id,
            BASE_STEPS_PER_TURN,
            held,
        )
        return held

    def terrain_rate(self, world_id: str, zone_id: str) -> Decimal:
        """The multiplier registered for ``zone_id``, refusing a zone with none."""
        held = self._terrain.get(world_id, {}).get(zone_id)
        if held is None:
            named = ", ".join(sorted(self._terrain.get(world_id, {}))) or "none"
            raise MovementError(
                f"no terrain multiplier is set for zone {zone_id} of world "
                f"{world_id}; zones carrying one: {named}"
            )
        return Decimal(held)

    def terrain_zones(self, world_id: str) -> tuple[str, ...]:
        """The zones of ``world_id`` carrying a terrain multiplier, sorted."""
        return tuple(sorted(self._terrain.get(world_id, {})))

    # -- One record a leg ----------------------------------------------------

    def open_leg(
        self,
        world_id: str,
        address: str,
        layer: int,
        journey_id: str,
        zone_id: str,
        start: GridPosition,
        end: GridPosition,
        opened_turn: int,
        encumbrance: Decimal,
    ) -> JourneyLeg:
        """Write the one record a leg costs, deriving its rate from zone and load.

        Raises ``MovementError`` for a zone the leg leaves, a turn before the
        journey's last leg arrives, or a start away from where that leg ended.
        """
        record = self._world.world(world_id)
        self._world.require_breached(world_id, layer)
        zone = self._world.zone(world_id, zone_id)
        if zone.layer != layer:
            raise MovementError(
                f"zone {zone_id} lies on layer {zone.layer}, not layer {layer}"
            )
        from_x, from_y = absolute_steps(start, record.width)
        to_x, to_y = absolute_steps(end, record.width)
        leg_length_steps(to_x - from_x, to_y - from_y)
        self._require_zone_covers_leg(
            zone, zone_id, record.width, from_x, from_y, to_x, to_y
        )
        rate = leg_rate(self.terrain_rate(world_id, zone_id), Decimal(str(encumbrance)))
        with self._lock:
            held = self._legs.setdefault(world_id, {}).setdefault(journey_id, [])
            self._require_follows(
                held, journey_id, address, opened_turn, from_x, from_y
            )
            args = {
                "world": world_id,
                "journey": journey_id,
                "leg": len(held),
                "layer": int(layer),
                "zone": zone_id,
                "opened": int(opened_turn),
                "fromX": from_x,
                "fromY": from_y,
                "toX": to_x,
                "toY": to_y,
                "rate": str(rate),
            }
            tx_hash = self._post(address, OPEN_LEG_FUNCTION, LEG_OPENED_EVENT, args)
            leg = JourneyLeg(
                journey_id=journey_id,
                world_id=world_id,
                layer=int(layer),
                leg_index=len(held),
                mover=address,
                zone_id=zone_id,
                opened_turn=int(opened_turn),
                from_step_x=from_x,
                from_step_y=from_y,
                to_step_x=to_x,
                to_step_y=to_y,
                rate=str(rate),
                open_tx=tx_hash,
            )
            held.append(leg)
        self.save()
        logger.info(
            "%s opened leg %d of journey %s on turn %d across zone %s at %s "
            "steps a turn, %s steps to run",
            address,
            leg.leg_index,
            journey_id,
            leg.opened_turn,
            zone_id,
            leg.rate,
            leg.length_steps,
        )
        return leg

    def journey_ids(self, world_id: str) -> tuple[str, ...]:
        """The journeys ``world_id`` holds, in opening order."""
        return tuple(self._legs.get(world_id, {}))

    def legs(self, world_id: str, journey_id: str) -> tuple[JourneyLeg, ...]:
        """The legs ``journey_id`` holds, refusing a journey nobody has opened."""
        held = self._legs.get(world_id, {}).get(journey_id)
        if not held:
            named = ", ".join(self._legs.get(world_id, {})) or "none"
            raise MovementError(
                f"no journey {journey_id!r} is open in world {world_id}; "
                f"journeys held: {named}"
            )
        return tuple(held)

    def leg_covering(self, world_id: str, journey_id: str, turn: int) -> JourneyLeg:
        """The leg of ``journey_id`` a mover travels under during ``turn``.

        A leg opening on ``turn`` has not moved yet, so the leg before it is the
        one that covers that turn.
        """
        held = self.legs(world_id, journey_id)
        moving = [leg for leg in held if leg.opened_turn < turn]
        if moving:
            return moving[-1]
        if turn == held[0].opened_turn:
            return held[0]
        raise MovementError(
            f"journey {journey_id} opens on turn {held[0].opened_turn}, "
            f"after turn {turn}"
        )

    def progress(self, world_id: str, journey_id: str, turn: int) -> dict:
        """Derive where ``journey_id`` has reached by ``turn``, writing no record."""
        record = self._world.world(world_id)
        leg = self.leg_covering(world_id, journey_id, turn)
        return leg.progress_at(turn, record.width)

    def mover_journeys(self, world_id: str, address: str) -> tuple[str, ...]:
        """The journeys of ``world_id`` ``address`` opened, in opening order."""
        held = self._legs.get(world_id, {})
        return tuple(
            journey_id
            for journey_id, legs in held.items()
            if legs and legs[0].mover == address
        )

    def mover_locator(self, world_id: str, address: str, turn: int) -> str | None:
        """The ``GridPosition.locator`` ``address`` stands at during ``turn``.

        None answers a mover whose own journeys all open after ``turn`` and one
        that has opened none, and the locator carries the covering leg's own
        ``layer``, so a position on two layers never reads as one place.
        """
        standing: str | None = None
        latest: int | None = None
        for journey_id in self.mover_journeys(world_id, address):
            if self.legs(world_id, journey_id)[0].opened_turn > turn:
                continue
            here = self.progress(world_id, journey_id, turn)
            if latest is None or here["opened_turn"] >= latest:
                latest = here["opened_turn"]
                standing = GridPosition(
                    square_index=here["square_index"],
                    step_x=here["square_step_x"],
                    step_y=here["square_step_y"],
                ).locator(here["layer"])
        return standing

    def replay_progress(
        self, world_id: str, journey_id: str, leg_index: int, turn: int
    ) -> dict:
        """Derive ``turn``'s figures from the chain's own ``openLeg`` record alone.

        Raises ``MovementError`` while the chain holds no transaction for that leg.
        """
        record = self._world.world(world_id)
        leg = self.legs(world_id, journey_id)[leg_index]
        tx = self._testnet.chain.get_tx(leg.open_tx)
        if tx is None:
            raise MovementError(
                f"the chain holds no transaction {leg.open_tx} for leg "
                f"{leg_index} of journey {journey_id}"
            )
        replayed = leg_from_chain(tx.args, tx.from_addr, tx.tx_hash)
        return replayed.progress_at(turn, record.width)

    def journey_summary(self, world_id: str, journey_id: str, turn: int) -> dict:
        """Every count ``journey_id`` holds at ``turn``, beside the records it cost."""
        legs = self.legs(world_id, journey_id)
        here = self.progress(world_id, journey_id, turn)
        return {
            "journey_id": journey_id,
            "world_id": world_id,
            "mover": legs[0].mover,
            "turn": turn,
            "legs": len(legs),
            "turns_open": turn - legs[0].opened_turn,
            "zones_crossed": tuple(leg.zone_id for leg in legs),
            "rates": tuple(leg.rate for leg in legs),
            "leg_index": here["leg_index"],
            "travelled_steps": here["travelled_steps"],
            "square_pct_this_turn": here["square_pct_this_turn"],
            "square_index": here["square_index"],
            "has_arrived": here["has_arrived"],
        }

    # -- Internals -----------------------------------------------------------

    def _require_zone_covers_leg(
        self,
        zone,
        zone_id: str,
        width: int,
        from_x: int,
        from_y: int,
        to_x: int,
        to_y: int,
    ) -> None:
        """Refuse a leg whose midpoint ``zone_id`` does not hold or whose end its extent misses.

        ``squares_in_extent`` bounds a leg to the zone's own squares, and a
        concave ``ZoneRegion`` the leg leaves and re-enters inside that bound is
        not decided here.
        """
        extent = zone.squares_in_extent(width)
        for step_x, step_y in ((from_x, from_y), (to_x, to_y)):
            end = position_at_steps(step_x, step_y, width)
            if end.square_index not in extent:
                raise MovementError(
                    f"zone {zone_id} does not cover square {end.square_index} at "
                    f"({step_x}, {step_y}) steps; a leg ends at the zone's border"
                )
        both = STEPS_PER_SQUARE * 2
        mid = (
            float(Decimal(from_x + to_x) / both),
            float(Decimal(from_y + to_y) / both),
        )
        if not zone.holds(mid):
            raise MovementError(
                f"zone {zone_id} does not hold the midpoint {mid} of the leg "
                f"from ({from_x}, {from_y}) to ({to_x}, {to_y}); a leg runs "
                f"across one terrain region and ends at its border"
            )

    def _require_follows(
        self,
        held: list,
        journey_id: str,
        address: str,
        opened_turn: int,
        from_x: int,
        from_y: int,
    ) -> None:
        """Refuse a leg that overlaps, jumps away from, or changes the mover of ``journey_id``."""
        if not held:
            if opened_turn < 0:
                raise MovementError(
                    f"journey {journey_id} cannot open on turn {opened_turn}"
                )
            return
        last = held[-1]
        if last.mover != address:
            raise MovementError(
                f"journey {journey_id} is {last.mover}'s, and {address} "
                f"cannot open a leg of it"
            )
        if opened_turn < last.arrival_turn:
            raise MovementError(
                f"leg {last.leg_index} of journey {journey_id} arrives on turn "
                f"{last.arrival_turn}, after turn {opened_turn}"
            )
        if (from_x, from_y) != (last.to_step_x, last.to_step_y):
            raise MovementError(
                f"leg {last.leg_index} of journey {journey_id} ended at "
                f"({last.to_step_x}, {last.to_step_y}), not ({from_x}, {from_y})"
            )

    def _post(self, sender: str, function: str, event: str, args: dict) -> str:
        """Send one leg record to the chain and emit its event."""
        chain = self._testnet.chain
        tx = chain.send_tx(sender, JOURNEY_CONTRACT, function, args)
        chain.emit(tx.tx_hash, JOURNEY_CONTRACT, event, args)
        return tx.tx_hash

    # -- Persistence ---------------------------------------------------------

    def save(self) -> None:
        """Write every journey's legs and every zone's terrain multiplier."""
        payload = {
            "version": JOURNEY_FILE_VERSION,
            "legs": {
                wid: {
                    jid: [leg.to_dict() for leg in legs] for jid, legs in held.items()
                }
                for wid, held in self._legs.items()
            },
            "terrain": {wid: dict(held) for wid, held in self._terrain.items()},
        }
        try:
            atomic_write_json(self._path, payload)
        except Exception as e:
            logger.warning("failed to write %s: %s", self._path, e)

    def load(self) -> "WorldJourneys":
        """Read ``journey_path`` back, keeping this store as it is when none is there."""
        if not self._path.exists():
            return self
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("failed to read %s: %s", self._path, e)
            return self
        if payload.get("version") != JOURNEY_FILE_VERSION:
            logger.warning(
                "%s carries version %s, not %d; nothing was read",
                self._path,
                payload.get("version"),
                JOURNEY_FILE_VERSION,
            )
            return self
        with self._lock:
            self._legs = {
                wid: {
                    jid: [JourneyLeg(**row) for row in rows]
                    for jid, rows in held.items()
                }
                for wid, held in payload.get("legs", {}).items()
            }
            self._terrain = {
                wid: dict(held) for wid, held in payload.get("terrain", {}).items()
            }
        logger.info(
            "read %d journey(s) from %s across %d world(s)",
            sum(len(held) for held in self._legs.values()),
            self._path,
            len(self._legs),
        )
        return self
