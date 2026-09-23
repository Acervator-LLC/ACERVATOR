"""The world grid, its zone regions and the three levels of discovery.

``square_index`` and ``square_xy`` address one layer of ``DEFAULT_GRID_WIDTH``
squares and ``squares_in_view`` bounds sight at ``BASE_VIEWRANGE_SQUARES``.
``ZoneRegion`` carries an irregular boundary joined at its own borders, and
``squares_in_extent`` with ``holds`` reads a zone's population across squares.
``PoaWorld.create_world`` commits a concealed seed, ``discover`` writes one
``WorldFact`` a location and one knowledge reference a participant, and
``extract`` runs once. ``arena_position`` with ``arena_locator`` answer the place
a participant stands on before it walks anywhere, which ``ARENA_LAYER`` layers.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import secrets
import threading
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Optional

from ..core.io_utils import atomic_write_json
from .poa_modes import base_impetus
from .rpg_classes import ARC_LEVELS

logger = logging.getLogger("acervator.world_grid")

#: Bytes one discovery record adds to the chain log, named fields, measured 1472.2 rounded up.
WORLD_RECORD_BYTES = 1473

#: One layer's byte ceiling for one world turn.
TURN_BYTE_CAPACITY = 1_048_576

#: Records one layer writes a world turn, each a block, a transaction and an event.
RECORDS_PER_LAYER_TURN = TURN_BYTE_CAPACITY // WORLD_RECORD_BYTES

#: Records a participant writes a world turn, the highest Impetus grant on the arc.
RECORDS_PER_PARTICIPANT_TURN = base_impetus(ARC_LEVELS)

#: Participants one layer carries, the count ``DEFAULT_GRID_WIDTH`` sizes its grid for.
PARTICIPANTS_PER_LAYER = RECORDS_PER_LAYER_TURN // RECORDS_PER_PARTICIPANT_TURN

#: Squares one layer holds, one a participant under the cap-together rule.
BUDGETED_SQUARES_PER_LAYER = PARTICIPANTS_PER_LAYER

#: Spheres on the Tree, each carrying ten character levels.
TREE_SPHERES = 10

#: The spheres and their inversions, read as the cube's third axis.
SEPHIROT_LAYERS = TREE_SPHERES * 2

#: The layer the arena sits on, the lowest ordinal ``breach_layer`` admits.
ARENA_LAYER = 0

#: Squares base sight covers, the participant's own.
BASE_VIEWRANGE_SQUARES = 1

#: Steps across one square, so a position is whole percent of a square.
SQUARE_STEPS = 100

#: Vertices a closed boundary ring needs at least.
MIN_BOUNDARY_VERTICES = 3

#: Hex digits of a leaf the band draw reads, 64 bits of it.
LEAF_DRAW_DIGITS = 16

#: Bytes of the concealed per-world seed ``create_world`` draws.
WORLD_SEED_BYTES = 16

WORLD_CONTRACT = "PoaWorld"
CREATE_FUNCTION = "createWorld"
BREACH_FUNCTION = "breachLayer"
ZONE_FUNCTION = "discoverZone"
ASSET_FUNCTION = "discoverAsset"
LEARN_FUNCTION = "learnAsset"
EXTRACT_FUNCTION = "extractQuintessence"
PUBLISH_FUNCTION = "publishSeed"

CREATED_EVENT = "WorldCreated"
BREACHED_EVENT = "LayerBreached"
ZONE_EVENT = "ZoneDiscovered"
ASSET_EVENT = "AssetDiscovered"
LEARNED_EVENT = "AssetLearned"
EXTRACTED_EVENT = "QuintessenceExtracted"
PUBLISHED_EVENT = "SeedPublished"

DEFAULT_WORLD_PATH = Path.home() / ".acervator" / "poa_world.json"
WORLD_FILE_VERSION = 1


class WorldGridError(RuntimeError):
    """Raised for a coordinate off the grid, an unbreached layer, a second extraction."""


def smallest_whole_side(square_count: int) -> int:
    """The smallest whole grid side whose area holds ``square_count`` squares."""
    if square_count <= 0:
        return 0
    side = math.isqrt(square_count)
    return side if side * side >= square_count else side + 1


def view_radius(visible_squares: int) -> int:
    """The squares past their own a participant sees covering ``visible_squares``."""
    return max(0, (smallest_whole_side(visible_squares) - 1) // 2)


def squares_at_radius(radius: int) -> int:
    """The squares a sight radius of ``radius`` covers, the centre included."""
    if radius < 0:
        raise WorldGridError(f"a sight radius of {radius} covers no square")
    return (2 * radius + 1) ** 2


#: The default grid side, holding ``BUDGETED_SQUARES_PER_LAYER`` squares.
DEFAULT_GRID_WIDTH = smallest_whole_side(BUDGETED_SQUARES_PER_LAYER)

#: Squares past their own a participant sees at ``BASE_VIEWRANGE_SQUARES``.
BASE_VIEWRANGE_RADIUS = view_radius(BASE_VIEWRANGE_SQUARES)


def addressable_squares(width: int = DEFAULT_GRID_WIDTH) -> int:
    """The squares a grid ``width`` squares across addresses."""
    if width <= 0:
        raise WorldGridError(f"a grid width of {width} addresses no square")
    return width * width


def square_index(x: int, y: int, width: int = DEFAULT_GRID_WIDTH) -> int:
    """The index square ``x``, ``y`` takes on a grid ``width`` squares across."""
    held = addressable_squares(width)
    if not 0 <= x < width or not 0 <= y < width:
        raise WorldGridError(
            f"square ({x}, {y}) is off a grid {width} across holding {held}"
        )
    return y * width + x


def square_xy(index: int, width: int = DEFAULT_GRID_WIDTH) -> tuple[int, int]:
    """The ``x`` and ``y`` of ``index`` on a grid ``width`` squares across."""
    held = addressable_squares(width)
    if not 0 <= index < held:
        raise WorldGridError(f"square {index} is off a grid holding {held}")
    return index % width, index // width


def squares_in_view(
    index: int,
    width: int = DEFAULT_GRID_WIDTH,
    radius: int = BASE_VIEWRANGE_RADIUS,
) -> tuple[int, ...]:
    """The squares within ``radius`` of ``index``, ``index`` among them.

    A radius reaching off the grid yields fewer than ``squares_at_radius``.
    """
    squares_at_radius(radius)
    centre_x, centre_y = square_xy(index, width)
    seen = []
    for y in range(centre_y - radius, centre_y + radius + 1):
        for x in range(centre_x - radius, centre_x + radius + 1):
            if 0 <= x < width and 0 <= y < width:
                seen.append(y * width + x)
    return tuple(seen)


def centre_square(width: int = DEFAULT_GRID_WIDTH) -> int:
    """The index of the middle square on a grid ``width`` squares across."""
    middle = (width - 1) // 2
    return square_index(middle, middle, width)


def discovery_leaf(seed: str, locator: str) -> str:
    """The leaf ``locator`` takes under ``seed``, which ``seed_commitment`` hides."""
    return hashlib.sha256(f"{seed}|{locator}".encode()).hexdigest()


def seed_commitment(seed: str) -> str:
    """The value a world posts at creation, naming no ``seed`` and no amount."""
    return hashlib.sha256(seed.encode()).hexdigest()


@dataclass(frozen=True)
class QuintessenceBand:
    """The lowest amount, the highest and the step a ``kind`` of asset may hold."""

    kind: str
    low: Decimal
    high: Decimal
    step: Decimal

    def __post_init__(self) -> None:
        """Refuse a band whose step is not positive and does not divide its span."""
        if self.step <= 0:
            raise WorldGridError(f"{self.kind} band step {self.step} is not positive")
        if self.high < self.low:
            raise WorldGridError(
                f"{self.kind} band runs {self.low} to {self.high}, high under low"
            )
        if (self.high - self.low) % self.step != 0:
            raise WorldGridError(
                f"{self.kind} band span {self.high - self.low} is not a whole "
                f"number of steps of {self.step}"
            )

    @property
    def draw_count(self) -> int:
        """The amounts ``step`` divides ``low`` through ``high`` into."""
        return int((self.high - self.low) / self.step) + 1

    def to_dict(self) -> dict:
        """Return this band as a JSON-safe dict."""
        return {
            "kind": self.kind,
            "low": str(self.low),
            "high": str(self.high),
            "step": str(self.step),
        }


def committed_quintessence(leaf: str, band: QuintessenceBand) -> Decimal:
    """The amount ``leaf`` draws in ``band``, one of its ``draw_count`` steps."""
    draw = int(leaf[:LEAF_DRAW_DIGITS], 16) % band.draw_count
    return band.low + band.step * draw


@dataclass(frozen=True)
class GridPosition:
    """A square and the whole percent of it a point sits across, in ``SQUARE_STEPS``."""

    square_index: int
    step_x: int = 0
    step_y: int = 0

    def __post_init__(self) -> None:
        """Refuse a step outside the ``SQUARE_STEPS`` a square divides into."""
        for name, step in (("step_x", self.step_x), ("step_y", self.step_y)):
            if not 0 <= step < SQUARE_STEPS:
                raise WorldGridError(
                    f"{name} of {step} is outside the {SQUARE_STEPS} steps of a square"
                )

    def locator(self, layer: int) -> str:
        """The text ``discovery_leaf`` hashes for this position on ``layer``."""
        return f"{layer}:{self.square_index}:{self.step_x}:{self.step_y}"

    def point(self, width: int = DEFAULT_GRID_WIDTH) -> tuple[float, float]:
        """This position as one continuous ``x`` and ``y`` across the grid."""
        x, y = square_xy(self.square_index, width)
        return x + self.step_x / SQUARE_STEPS, y + self.step_y / SQUARE_STEPS


@dataclass(frozen=True)
class ZoneRegion:
    """One terrain region, its closed boundary ring and who first found it.

    ``boundary`` names each vertex once, and the last vertex joins the first.
    """

    zone_id: str
    world_id: str
    layer: int
    boundary: tuple[tuple[float, float], ...]
    discovered_by: str
    discover_tx: str

    @property
    def vertex_count(self) -> int:
        """Vertices ``boundary`` carries."""
        return len(self.boundary)

    def holds(self, point: tuple[float, float]) -> bool:
        """Answer whether ``point`` lies inside ``boundary`` under the even-odd rule."""
        px, py = float(point[0]), float(point[1])
        inside = False
        ring = self.boundary
        for index in range(len(ring)):
            ax, ay = ring[index]
            bx, by = ring[index - 1]
            if (ay > py) == (by > py):
                continue
            # Cross products stand in for the crossing-x division, so no edge divides.
            left = (px - ax) * (by - ay)
            right = (bx - ax) * (py - ay)
            if (left < right) if by > ay else (left > right):
                inside = not inside
        return inside

    def squares_in_extent(self, width: int = DEFAULT_GRID_WIDTH) -> tuple[int, ...]:
        """The squares ``boundary``'s bounding box covers, lowest index first.

        A square here is a candidate, and ``holds`` decides a point inside it.
        """
        xs = [vertex[0] for vertex in self.boundary]
        ys = [vertex[1] for vertex in self.boundary]
        low_x = max(0, min(width - 1, math.floor(min(xs))))
        high_x = max(0, min(width - 1, math.floor(max(xs))))
        low_y = max(0, min(width - 1, math.floor(min(ys))))
        high_y = max(0, min(width - 1, math.floor(max(ys))))
        return tuple(
            y * width + x
            for y in range(low_y, high_y + 1)
            for x in range(low_x, high_x + 1)
        )

    def to_dict(self) -> dict:
        """Return this region as a JSON-safe dict."""
        return {
            "zone_id": self.zone_id,
            "world_id": self.world_id,
            "layer": self.layer,
            "boundary": [[vertex[0], vertex[1]] for vertex in self.boundary],
            "discovered_by": self.discovered_by,
            "discover_tx": self.discover_tx,
        }


@dataclass(frozen=True)
class WorldFact:
    """One asset's fact: where it is, the amount it holds and who first found it.

    ``fact_id`` carries the world and the locator, so one place holds one fact.
    """

    fact_id: str
    world_id: str
    layer: int
    square_index: int
    step_x: int
    step_y: int
    kind: str
    quintessence: str
    band: dict
    leaf: str
    discovered_by: str
    discover_tx: str

    @property
    def locator(self) -> str:
        """The text ``discovery_leaf`` hashed for this fact's place."""
        return f"{self.layer}:{self.square_index}:{self.step_x}:{self.step_y}"

    def to_dict(self) -> dict:
        """Return this fact as a JSON-safe dict."""
        return {
            "fact_id": self.fact_id,
            "world_id": self.world_id,
            "layer": self.layer,
            "square_index": self.square_index,
            "step_x": self.step_x,
            "step_y": self.step_y,
            "kind": self.kind,
            "quintessence": self.quintessence,
            "band": dict(self.band),
            "leaf": self.leaf,
            "discovered_by": self.discovered_by,
            "discover_tx": self.discover_tx,
        }


@dataclass(frozen=True)
class WorldRecord:
    """One world's grid, its declared layers, its arena and its seed commitment.

    ``commitment`` is on the chain from creation and names no amount.
    """

    world_id: str
    width: int
    declared_layers: int
    arena_square: int
    commitment: str
    create_tx: str

    def to_dict(self) -> dict:
        """Return this world as a JSON-safe dict."""
        return {
            "world_id": self.world_id,
            "width": self.width,
            "declared_layers": self.declared_layers,
            "arena_square": self.arena_square,
            "commitment": self.commitment,
            "create_tx": self.create_tx,
        }


class PoaWorld:
    """Holds every world's grid and only what its participants have found.

    The ``LocalTestnet`` and ``world_path`` arrive by construction, so a demo run
    is one world over a different chain running the same ``discover`` path.
    """

    def __init__(self, testnet, world_path: str | Path | None = None) -> None:
        """Hold the chain and the record path, carrying no world and no layer."""
        self._testnet = testnet
        self._path: Path = Path(world_path) if world_path else DEFAULT_WORLD_PATH
        self._lock = threading.RLock()
        self._worlds: dict[str, WorldRecord] = {}
        self._seeds: dict[str, str] = {}
        self._published: set[str] = set()
        self._breached: dict[str, dict[int, str]] = {}
        self._zones: dict[str, dict[str, ZoneRegion]] = {}
        self._facts: dict[str, dict[str, WorldFact]] = {}
        self._knowledge: dict[str, dict[str, set[str]]] = {}
        self._extracted: dict[str, dict[str, str]] = {}
        self._bands: dict[str, QuintessenceBand] = {}

    @property
    def world_path(self) -> Path:
        """The file ``save`` writes and ``load`` reads."""
        return self._path

    @property
    def world_ids(self) -> tuple[str, ...]:
        """The worlds this store holds, in creation order."""
        return tuple(self._worlds)

    # -- The bands a kind's amount draws from --------------------------------

    def set_band(self, band: QuintessenceBand) -> QuintessenceBand:
        """Register the band ``band.kind``'s committed amount draws from."""
        with self._lock:
            self._bands[band.kind] = band
        logger.info(
            "%s draws %s to %s in steps of %s, %d amounts",
            band.kind,
            band.low,
            band.high,
            band.step,
            band.draw_count,
        )
        return band

    def band_for(self, kind: str) -> QuintessenceBand:
        """The band registered for ``kind``, refusing a kind with none."""
        band = self._bands.get(kind)
        if band is None:
            held = ", ".join(sorted(self._bands)) or "none"
            raise WorldGridError(
                f"no Quintessence band is set for {kind!r}; bands held: {held}"
            )
        return band

    # -- Creation, and the arena that needs no discovery ---------------------

    def create_world(
        self,
        world_id: str,
        width: int = DEFAULT_GRID_WIDTH,
        declared_layers: int = SEPHIROT_LAYERS,
        seed: Optional[str] = None,
    ) -> WorldRecord:
        """Commit a concealed seed, fix the arena square and post the commitment.

        Raises ``WorldGridError`` while ``world_id`` is already held.
        """
        with self._lock:
            if world_id in self._worlds:
                raise WorldGridError(f"world {world_id} is already held")
            if declared_layers <= 0:
                raise WorldGridError(
                    f"world {world_id} declares {declared_layers} layers"
                )
            held_seed = seed or secrets.token_hex(WORLD_SEED_BYTES)
            commitment = seed_commitment(held_seed)
            arena = centre_square(width)
            args = {
                "world": world_id,
                "width": int(width),
                "layers": int(declared_layers),
                "arena": arena,
                "commitment": commitment,
            }
            tx_hash = self._post(world_id, CREATE_FUNCTION, CREATED_EVENT, args)
            record = WorldRecord(
                world_id=world_id,
                width=int(width),
                declared_layers=int(declared_layers),
                arena_square=arena,
                commitment=commitment,
                create_tx=tx_hash,
            )
            self._worlds[world_id] = record
            self._seeds[world_id] = held_seed
            self._breached[world_id] = {}
            self._zones[world_id] = {}
            self._facts[world_id] = {}
            self._knowledge[world_id] = {}
            self._extracted[world_id] = {}
        self.save()
        logger.info(
            "world %s declares %d squares on %d layers, arena at %d, commitment %s",
            world_id,
            addressable_squares(width),
            declared_layers,
            arena,
            commitment[:16],
        )
        return record

    def world(self, world_id: str) -> WorldRecord:
        """The ``WorldRecord`` for ``world_id``, refusing a world not held."""
        record = self._worlds.get(world_id)
        if record is None:
            held = ", ".join(self._worlds) or "none"
            raise WorldGridError(f"no world {world_id!r} is held; worlds: {held}")
        return record

    def arena_square(self, world_id: str) -> int:
        """The square every participant starts on, known with no discovery record."""
        return self.world(world_id).arena_square

    def arena_position(self, world_id: str) -> GridPosition:
        """Where a participant of ``world_id`` stands before it walks anywhere.

        ``world_movement.WorldJourneys.mover_standing`` answers this position for
        a mover holding no journey leg, so the arena is a place and not an
        absence. Raises ``WorldGridError`` for a world this store does not hold.
        """
        return GridPosition(square_index=self.world(world_id).arena_square)

    def arena_locator(self, world_id: str) -> str:
        """``arena_position`` as the locator text on ``ARENA_LAYER``."""
        return self.arena_position(world_id).locator(ARENA_LAYER)

    def is_reachable_without_discovery(self, world_id: str, square: int) -> bool:
        """Answer whether ``square`` is this world's arena, the one known origin."""
        return square == self.world(world_id).arena_square

    # -- A layer begins to exist when someone breaches it --------------------

    def breach_layer(self, world_id: str, address: str, layer: int) -> int:
        """Write the breach that makes ``layer`` exist, keeping the first breacher.

        Raises ``WorldGridError`` for a layer outside the world's declared count.
        """
        record = self.world(world_id)
        if not 0 <= layer < record.declared_layers:
            raise WorldGridError(
                f"layer {layer} is outside the {record.declared_layers} "
                f"layers world {world_id} declares"
            )
        with self._lock:
            breached = self._breached[world_id]
            if layer in breached:
                return layer
            args = {"world": world_id, "layer": int(layer), "by": address}
            self._post(address, BREACH_FUNCTION, BREACHED_EVENT, args)
            breached[layer] = address
        self.save()
        logger.info("%s breached layer %d of world %s", address, layer, world_id)
        return layer

    def breached_layers(self, world_id: str) -> tuple[int, ...]:
        """The layers of ``world_id`` that exist, lowest first."""
        self.world(world_id)
        return tuple(sorted(self._breached[world_id]))

    def require_breached(self, world_id: str, layer: int) -> None:
        """Refuse work on a layer of ``world_id`` nobody has breached."""
        if layer not in self._breached.get(world_id, {}):
            reached = (
                ", ".join(str(n) for n in self.breached_layers(world_id)) or "none"
            )
            raise WorldGridError(
                f"layer {layer} of world {world_id} does not exist; "
                f"layers breached: {reached}"
            )

    # -- A zone's boundary is written once, by its first discoverer ----------

    def discover_zone(
        self,
        world_id: str,
        address: str,
        layer: int,
        zone_id: str,
        boundary,
    ) -> ZoneRegion:
        """Write ``boundary`` on a first discovery, and a reference on every later one.

        Raises ``WorldGridError`` for a ring under ``MIN_BOUNDARY_VERTICES``.
        """
        self.world(world_id)
        self.require_breached(world_id, layer)
        with self._lock:
            held = self._zones[world_id]
            zone = held.get(zone_id)
            if zone is not None:
                self._learn(world_id, address, zone_id, LEARN_FUNCTION, LEARNED_EVENT)
                return zone
            ring = tuple((float(vx), float(vy)) for vx, vy in boundary)
            if len(ring) < MIN_BOUNDARY_VERTICES:
                raise WorldGridError(
                    f"zone {zone_id} carries {len(ring)} vertices, under the "
                    f"{MIN_BOUNDARY_VERTICES} a closed ring needs"
                )
            args = {
                "world": world_id,
                "zone": zone_id,
                "layer": int(layer),
                "boundary": [[vx, vy] for vx, vy in ring],
                "by": address,
            }
            tx_hash = self._post(address, ZONE_FUNCTION, ZONE_EVENT, args)
            zone = ZoneRegion(
                zone_id=zone_id,
                world_id=world_id,
                layer=int(layer),
                boundary=ring,
                discovered_by=address,
                discover_tx=tx_hash,
            )
            held[zone_id] = zone
            self._remember(world_id, address, zone_id)
        self.save()
        logger.info(
            "%s discovered zone %s on layer %d of world %s, %d vertices",
            address,
            zone_id,
            layer,
            world_id,
            zone.vertex_count,
        )
        return zone

    def zones(self, world_id: str) -> tuple[str, ...]:
        """The zones of ``world_id`` somebody has discovered."""
        self.world(world_id)
        return tuple(self._zones[world_id])

    def zone(self, world_id: str, zone_id: str) -> ZoneRegion:
        """The ``ZoneRegion`` for ``zone_id``, refusing an undiscovered zone."""
        zone = self._zones.get(world_id, {}).get(zone_id)
        if zone is None:
            raise WorldGridError(
                f"no zone {zone_id!r} is discovered in world {world_id}"
            )
        return zone

    def zones_touching(self, world_id: str, layer: int, square: int) -> tuple[str, ...]:
        """The discovered zones of ``layer`` whose extent covers ``square``."""
        record = self.world(world_id)
        return tuple(
            zone_id
            for zone_id, zone in self._zones[world_id].items()
            if zone.layer == layer and square in zone.squares_in_extent(record.width)
        )

    def zone_level(self, world_id: str, zone_id: str, occupants: dict) -> dict:
        """The mean level of the participants ``zone_id`` holds, across its squares.

        ``occupants`` maps an address to a ``GridPosition`` and a level, and
        ``level`` is ``None`` while the zone holds nobody.
        """
        record = self.world(world_id)
        zone = self.zone(world_id, zone_id)
        extent = zone.squares_in_extent(record.width)
        population: list[str] = []
        squares_holding: set[int] = set()
        level_total = Decimal(0)
        for address, (position, level) in sorted(occupants.items()):
            if position.square_index not in extent:
                continue
            if not zone.holds(position.point(record.width)):
                continue
            population.append(address)
            squares_holding.add(position.square_index)
            level_total += Decimal(str(level))
        mean_level = level_total / Decimal(len(population)) if population else None
        return {
            "zone_id": zone_id,
            "layer": zone.layer,
            "squares_in_extent": extent,
            "squares_holding": tuple(sorted(squares_holding)),
            "population": tuple(population),
            "level": mean_level,
        }

    # -- The fact, the knowledge and the extraction --------------------------

    def discover(
        self,
        world_id: str,
        address: str,
        layer: int,
        position: GridPosition,
        kind: str,
    ) -> tuple[WorldFact, bool]:
        """Write the fact on a first discovery, and return it with a reference after.

        The second member is True only for the discovery that wrote the fact.
        """
        self.world(world_id)
        self.require_breached(world_id, layer)
        band = self.band_for(kind)
        locator = position.locator(layer)
        fact_id = f"{world_id}:{locator}"
        with self._lock:
            held = self._facts[world_id]
            fact = held.get(fact_id)
            if fact is not None:
                self._learn(world_id, address, fact_id, LEARN_FUNCTION, LEARNED_EVENT)
                logger.info(
                    "%s discovered the standing fact %s holding %s",
                    address,
                    fact_id,
                    fact.quintessence,
                )
                return fact, False
            leaf = discovery_leaf(self._seeds[world_id], locator)
            amount = committed_quintessence(leaf, band)
            args = {
                "world": world_id,
                "fact": fact_id,
                "layer": int(layer),
                "square": position.square_index,
                "stepX": position.step_x,
                "stepY": position.step_y,
                "kind": kind,
                "quintessence": str(amount),
                "leaf": leaf,
                "by": address,
            }
            tx_hash = self._post(address, ASSET_FUNCTION, ASSET_EVENT, args)
            fact = WorldFact(
                fact_id=fact_id,
                world_id=world_id,
                layer=int(layer),
                square_index=position.square_index,
                step_x=position.step_x,
                step_y=position.step_y,
                kind=kind,
                quintessence=str(amount),
                band=band.to_dict(),
                leaf=leaf,
                discovered_by=address,
                discover_tx=tx_hash,
            )
            held[fact_id] = fact
            self._remember(world_id, address, fact_id)
        self.save()
        logger.info(
            "%s first discovered %s, a %s holding %s",
            address,
            fact_id,
            kind,
            amount,
        )
        return fact, True

    def fact(self, world_id: str, fact_id: str) -> WorldFact:
        """The ``WorldFact`` for ``fact_id``, refusing a place nobody has found."""
        fact = self._facts.get(world_id, {}).get(fact_id)
        if fact is None:
            raise WorldGridError(
                f"no fact {fact_id!r} is discovered in world {world_id}"
            )
        return fact

    def quintessence_at(
        self, world_id: str, layer: int, position: GridPosition
    ) -> Decimal:
        """The amount held where ``position`` is, refusing an undiscovered place."""
        fact_id = f"{world_id}:{position.locator(layer)}"
        return Decimal(self.fact(world_id, fact_id).quintessence)

    def knows(self, world_id: str, address: str) -> tuple[str, ...]:
        """The facts and zones ``address`` holds a reference to, sorted."""
        self.world(world_id)
        return tuple(sorted(self._knowledge[world_id].get(address, set())))

    def knowledge_references(self, world_id: str) -> int:
        """The references every participant of ``world_id`` holds in total."""
        self.world(world_id)
        return sum(len(held) for held in self._knowledge[world_id].values())

    def extract(self, world_id: str, address: str, fact_id: str) -> Decimal:
        """Take the one extraction a fact allows, refusing a second.

        Raises ``WorldGridError`` while ``address`` holds no reference to the fact.
        """
        fact = self.fact(world_id, fact_id)
        with self._lock:
            taken = self._extracted[world_id]
            if fact_id in taken:
                raise WorldGridError(
                    f"{fact_id} was already extracted by {taken[fact_id]}; "
                    f"one asset allows one extraction"
                )
            if fact_id not in self._knowledge[world_id].get(address, set()):
                raise WorldGridError(
                    f"{address} holds no knowledge of {fact_id} and cannot extract it"
                )
            args = {
                "world": world_id,
                "fact": fact_id,
                "quintessence": fact.quintessence,
                "by": address,
            }
            self._post(address, EXTRACT_FUNCTION, EXTRACTED_EVENT, args)
            taken[fact_id] = address
        self.save()
        logger.info("%s extracted %s from %s", address, fact.quintessence, fact_id)
        return Decimal(fact.quintessence)

    def extracted_by(self, world_id: str, fact_id: str) -> Optional[str]:
        """The participant who took ``fact_id``, or None while nobody has."""
        self.world(world_id)
        return self._extracted[world_id].get(fact_id)

    # -- The commitment, checked after the discovery -------------------------

    def verify_discovery(self, world_id: str, fact_id: str) -> dict:
        """Recompute a fact's leaf and amount, and the world's ``commitment``."""
        record = self.world(world_id)
        fact = self.fact(world_id, fact_id)
        held_seed = self._seeds[world_id]
        leaf = discovery_leaf(held_seed, fact.locator)
        band = QuintessenceBand(
            kind=fact.band["kind"],
            low=Decimal(fact.band["low"]),
            high=Decimal(fact.band["high"]),
            step=Decimal(fact.band["step"]),
        )
        amount = committed_quintessence(leaf, band)
        leaf_matches = leaf == fact.leaf
        amount_matches = amount == Decimal(fact.quintessence)
        commitment_matches = seed_commitment(held_seed) == record.commitment
        return {
            "fact_id": fact_id,
            "locator": fact.locator,
            "leaf": leaf,
            "stored_leaf": fact.leaf,
            "amount": str(amount),
            "stored_amount": fact.quintessence,
            "leaf_matches": leaf_matches,
            "amount_matches": amount_matches,
            "commitment_matches": commitment_matches,
            "verified": leaf_matches and amount_matches and commitment_matches,
        }

    def publish_seed(self, world_id: str) -> str:
        """Post the seed the commitment hid, so any holder checks every amount."""
        record = self.world(world_id)
        with self._lock:
            if world_id in self._published:
                raise WorldGridError(f"world {world_id}'s seed is already published")
            held_seed = self._seeds[world_id]
            args = {
                "world": world_id,
                "commitment": record.commitment,
                "seed": held_seed,
            }
            self._post(world_id, PUBLISH_FUNCTION, PUBLISHED_EVENT, args)
            self._published.add(world_id)
        self.save()
        logger.info(
            "world %s published its seed under %s", world_id, record.commitment[:16]
        )
        return held_seed

    def seed_is_published(self, world_id: str) -> bool:
        """Answer whether ``world_id`` has posted the seed its commitment hid."""
        self.world(world_id)
        return world_id in self._published

    # -- What the store holds ------------------------------------------------

    def world_summary(self, world_id: str) -> dict:
        """Every count this world holds, beside the figures its budget rests on."""
        record = self.world(world_id)
        zones = self._zones[world_id]
        return {
            "world_id": world_id,
            "width": record.width,
            "addressable_squares": addressable_squares(record.width),
            "declared_layers": record.declared_layers,
            "arena_square": record.arena_square,
            "commitment": record.commitment,
            "seed_published": world_id in self._published,
            "breached_layers": len(self._breached[world_id]),
            "discovered_zones": len(zones),
            "boundary_vertices": sum(zone.vertex_count for zone in zones.values()),
            "discovered_facts": len(self._facts[world_id]),
            "knowing_participants": len(self._knowledge[world_id]),
            "knowledge_references": self.knowledge_references(world_id),
            "extractions": len(self._extracted[world_id]),
            "participants_per_layer": PARTICIPANTS_PER_LAYER,
            "records_per_layer_turn": RECORDS_PER_LAYER_TURN,
            "base_viewrange_squares": squares_at_radius(BASE_VIEWRANGE_RADIUS),
        }

    # -- Internals -----------------------------------------------------------

    def _post(self, sender: str, function: str, event: str, args: dict) -> str:
        """Send one world record to the chain and emit its event."""
        chain = self._testnet.chain
        tx = chain.send_tx(sender, WORLD_CONTRACT, function, args)
        chain.emit(tx.tx_hash, WORLD_CONTRACT, event, args)
        return tx.tx_hash

    def _remember(self, world_id: str, address: str, reference: str) -> None:
        """Add ``reference`` to what ``address`` knows, holding no copy of it."""
        held = self._knowledge[world_id].setdefault(address, set())
        held.add(reference)

    def _learn(
        self, world_id: str, address: str, reference: str, function: str, event: str
    ) -> None:
        """Post a knowledge reference for a fact or zone already written."""
        if reference in self._knowledge[world_id].get(address, set()):
            return
        args = {"world": world_id, "reference": reference, "by": address}
        self._post(address, function, event, args)
        self._remember(world_id, address, reference)
        self.save()
        logger.info("%s now knows %s in world %s", address, reference, world_id)

    # -- Persistence ---------------------------------------------------------

    def save(self) -> None:
        """Write the worlds, the seeds, the breaches, the zones and the facts."""
        payload = {
            "version": WORLD_FILE_VERSION,
            "worlds": {wid: rec.to_dict() for wid, rec in self._worlds.items()},
            "seeds": dict(self._seeds),
            "published": sorted(self._published),
            "breached": {
                wid: {str(layer): by for layer, by in held.items()}
                for wid, held in self._breached.items()
            },
            "zones": {
                wid: {zid: zone.to_dict() for zid, zone in held.items()}
                for wid, held in self._zones.items()
            },
            "facts": {
                wid: {fid: fact.to_dict() for fid, fact in held.items()}
                for wid, held in self._facts.items()
            },
            "knowledge": {
                wid: {addr: sorted(refs) for addr, refs in held.items()}
                for wid, held in self._knowledge.items()
            },
            "extracted": {wid: dict(held) for wid, held in self._extracted.items()},
            "bands": {kind: band.to_dict() for kind, band in self._bands.items()},
        }
        try:
            atomic_write_json(self._path, payload)
        except Exception as e:
            logger.warning("failed to write %s: %s", self._path, e)

    def load(self) -> "PoaWorld":
        """Read ``world_path`` back, keeping this store as it is when none is there."""
        if not self._path.exists():
            return self
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("failed to read %s: %s", self._path, e)
            return self
        if payload.get("version") != WORLD_FILE_VERSION:
            logger.warning(
                "%s carries version %s, not %d; nothing was read",
                self._path,
                payload.get("version"),
                WORLD_FILE_VERSION,
            )
            return self
        with self._lock:
            self._worlds = {
                wid: WorldRecord(**rec)
                for wid, rec in payload.get("worlds", {}).items()
            }
            self._seeds = dict(payload.get("seeds", {}))
            self._published = set(payload.get("published", []))
            self._breached = {
                wid: {int(layer): by for layer, by in held.items()}
                for wid, held in payload.get("breached", {}).items()
            }
            self._zones = {
                wid: {
                    zid: ZoneRegion(
                        zone_id=row["zone_id"],
                        world_id=row["world_id"],
                        layer=row["layer"],
                        boundary=tuple(
                            (vertex[0], vertex[1]) for vertex in row["boundary"]
                        ),
                        discovered_by=row["discovered_by"],
                        discover_tx=row["discover_tx"],
                    )
                    for zid, row in held.items()
                }
                for wid, held in payload.get("zones", {}).items()
            }
            self._facts = {
                wid: {fid: WorldFact(**row) for fid, row in held.items()}
                for wid, held in payload.get("facts", {}).items()
            }
            self._knowledge = {
                wid: {addr: set(refs) for addr, refs in held.items()}
                for wid, held in payload.get("knowledge", {}).items()
            }
            self._extracted = {
                wid: dict(held) for wid, held in payload.get("extracted", {}).items()
            }
            self._bands = {
                kind: QuintessenceBand(
                    kind=row["kind"],
                    low=Decimal(row["low"]),
                    high=Decimal(row["high"]),
                    step=Decimal(row["step"]),
                )
                for kind, row in payload.get("bands", {}).items()
            }
        logger.info(
            "read %d world(s) from %s holding %d zone(s)",
            len(self._worlds),
            self._path,
            sum(len(held) for held in self._zones.values()),
        )
        return self
