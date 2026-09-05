"""A simulator run never reaches live capital state or the live event bus.

``scout`` builds a sim scout over the throwaway archive ``tablet_root`` and
pins that ``_crr`` is neither ``get_registry`` nor a writer inside
``~/.acervator``, and that ``_bus`` is not ``get_event_bus``.
``FleetReplayController._assert_capital_isolation`` is driven for the refusal
it owes a bot holding the process-wide registry or none at all.
``inside_runtime_tree`` is the shared predicate, also run against a planted
path so a pass here cannot mean a blind instrument.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.core.event_bus import get_event_bus
from src.simulator.fleet.fleet_replay_controller import (
    FleetReplayController,
    _make_sim_capital_registry,
)
from src.simulator.nuclear_candle_source import NuclearCandleSource
from src.simulator.nuclear_controller import NuclearController
from src.trading.capital_reservation import get_registry
from src.trading.stone_tablets.storage import (
    Tablet,
    TabletEntry,
    write_manifest,
    write_tablet,
)

BASE_TS_MS = 1_774_915_200_000
STEP_MS = 300_000


def inside_runtime_tree(path: Path) -> bool:
    """True when ``path`` resolves to, or under, ``~/.acervator``."""
    resolved = Path(path).resolve()
    runtime = (Path.home() / ".acervator").resolve()
    return resolved == runtime or runtime in resolved.parents


def _candles(count: int) -> list[list[float]]:
    rows = []
    price = 100.0
    for index in range(count):
        price *= 1.0 + (0.01 if index % 3 else -0.008)
        rows.append(
            [
                BASE_TS_MS + index * STEP_MS,
                price,
                price * 1.006,
                price * 0.994,
                price * 1.004,
                10.0 + index,
            ]
        )
    return rows


@pytest.fixture
def tablet_root(tmp_path, monkeypatch):
    """A throwaway tablet archive bound to ``storage.STONE_TABLETS_DIR``."""
    from src.trading.stone_tablets import storage

    root = tmp_path / "stone_tablets"
    root.mkdir(parents=True)
    monkeypatch.setattr(storage, "STONE_TABLETS_DIR", root)

    entries = []
    for asset, count in (("BTC", 400), ("ETH", 300)):
        tablet = Tablet(
            asset=asset,
            exchange_id="coinbase",
            timeframe="5m",
            year=2026,
            source="test",
            fetched_at="2026-08-04",
            candles=_candles(count),
        )
        write_tablet(tablet, root=root)
        entries.append(
            TabletEntry(
                asset=asset,
                exchange_id="coinbase",
                timeframe="5m",
                year=2026,
                file=f"{asset}_5m_2026_coinbase.json",
                checksum_sha256=tablet.compute_checksum(),
                candle_count=count,
                first_ts_ms=tablet.first_ts_ms,
                last_ts_ms=tablet.last_ts_ms,
                fetched_at="2026-08-04",
                source="test",
                listed_at_ms=tablet.first_ts_ms,
            )
        )
    write_manifest(entries, root=root)
    return root


@pytest.fixture
def scout(tablet_root):
    """The sim bot a controller constructs, over ``tablet_root`` only."""
    source = NuclearCandleSource(cache_dir=tablet_root / "_absent_legacy_cache")
    tapes = source.list_tapes()
    assert tapes, "the throwaway archive produced no tape to drive"
    controller = NuclearController(candle_source=source, tape_id=tapes[0])
    controller._build_context()
    controller._wire_bus_subscriptions()
    controller._construct_scout()
    return controller._scout


def _bot(bot_id: str, registry: object) -> object:
    return type("Bot", (), {"bot_id": bot_id, "_capital_registry": registry})()


def _replay(bots: list[object]) -> tuple[FleetReplayController, list[str]]:
    """A ``FleetReplayController`` holding ``bots``, plus its activity lines."""
    controller = object.__new__(FleetReplayController)
    controller._bots = list(bots)
    said: list[str] = []

    def record(message: str) -> None:
        said.append(str(message))

    controller._activity = record
    return controller, said


def test_the_sim_scout_does_not_resolve_the_live_capital_registry(scout):
    assert scout._crr() is not get_registry(), (
        "the sim scout resolved the process-wide capital registry, which "
        "persists into the operator's reservation_state.json"
    )


def test_the_live_capital_registry_is_one_object_every_call():
    """Positive control: the identity check above can fail."""
    assert get_registry() is get_registry()


def test_the_sim_scouts_capital_registry_does_not_autosave(scout):
    assert (
        scout._crr()._autosave is False
    ), "the sim scout's capital registry persists what a sim run reserves"


def test_the_live_capital_registry_does_autosave():
    """Positive control: ``_autosave`` is not False everywhere."""
    assert get_registry()._autosave is True


def test_the_sim_scouts_capital_registry_writes_its_own_file(scout):
    """``RESERVATION_ROOT_ENV`` is redirected for the suite, so the runtime-tree
    clause alone cannot fail here; the live registry's own path is the one that
    moves when the scout leaks."""
    path = scout._crr()._state_path
    assert not inside_runtime_tree(
        path
    ), f"the sim scout's capital registry writes inside the runtime tree: {path}"
    assert (
        Path(path).resolve() != Path(get_registry()._state_path).resolve()
    ), f"the sim scout writes the file the process-wide registry owns: {path}"


def test_the_runtime_tree_predicate_catches_a_path_inside_it():
    """Positive control: ``inside_runtime_tree`` answers both ways."""
    assert inside_runtime_tree(Path.home() / ".acervator" / "reservation_state.json")
    assert inside_runtime_tree(Path.home() / ".acervator")
    assert not inside_runtime_tree(
        Path(tempfile.gettempdir()) / "reservation_state.json"
    )


def test_the_sim_scout_is_not_on_the_global_event_bus(scout):
    assert (
        scout._bus is not get_event_bus()
    ), "the sim scout publishes onto the bus live subscribers read"


def test_the_global_event_bus_is_one_object_every_call():
    """Positive control: the identity check above can fail."""
    assert get_event_bus() is get_event_bus()


def test_a_replay_refuses_a_bot_holding_the_live_capital_registry():
    controller, _ = _replay([_bot("leak", get_registry())])
    with pytest.raises(RuntimeError) as raised:
        controller._assert_capital_isolation()
    message = str(raised.value)
    assert "isolation breached" in message, message
    assert "leak" in message, f"the offending bot is not named: {message}"


def test_a_replay_refuses_a_bot_with_no_capital_registry_at_all():
    controller, _ = _replay([_bot("bare", None)])
    with pytest.raises(RuntimeError) as raised:
        controller._assert_capital_isolation()
    assert "bare" in str(raised.value), str(raised.value)


def test_a_replay_admits_bots_on_private_non_persisting_registries():
    """Positive control: the guard does not refuse every fleet."""
    controller, said = _replay(
        [_bot(f"ok{index}", _make_sim_capital_registry()) for index in range(3)]
    )
    controller._assert_capital_isolation()
    assert any("isolation verified" in line for line in said), said


def test_an_empty_replay_fleet_is_not_refused():
    controller, said = _replay([])
    controller._assert_capital_isolation()
    assert any("isolation verified" in line for line in said), said
