"""The Qt shared TestNet bridge stays wired while React reads beside it.

The React module reads the same state over the ``shared_testnet.state``
bridge method, but the writes still cross threads through this QObject:
a queue any producer may fill, a drain timer, a single-shot save timer
and three signals. Until the running application's logs verify the React
side, this object is what carries a competition onto the chain, so these
tests construct the real bridge and count the live Qt children and the
live signals it holds.

Nothing here writes a real file: the bridge is given a path under
``tmp_path`` or none at all, and no competition is ever run.
"""

from __future__ import annotations

import collections
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui import shared_testnet as shipped
from src.gui.main_tabs import shared_testnet_surface as surface
from tests.qt_pixel import ensure_app

#: The Qt children this bridge builds itself, by class and by count.
BUILT_CHILDREN = {"QTimer": 2}


#: A stand-in chain. It opens no file, reaches no network and makes no key.
def stand_in_chain():
    return surface.SharedTestnetModel()


@pytest.fixture()
def bridge(tmp_path):
    """The real Qt bridge over a stand-in chain, its timers stopped."""
    from PySide6.QtCore import QTimer

    ensure_app()
    built = shipped.SharedTestnetBridge(
        stand_in_chain(), tmp_path / "testnet_chain.json"
    )
    for one in built.findChildren(QTimer):
        one.stop()
    yield built
    built.deleteLater()


def live_kinds(node) -> dict:
    from PySide6.QtCore import QObject

    counted = collections.Counter(
        one.__class__.__name__ for one in node.findChildren(QObject)
    )
    return {name: counted.get(name, 0) for name in BUILT_CHILDREN}


def test_the_bridge_is_a_real_qt_object(bridge):
    from PySide6.QtCore import QObject

    assert isinstance(bridge, QObject)


def test_the_bridge_still_holds_both_timers_it_builds(bridge):
    """A deleted timer stops the drain or the save, and drops out here."""
    assert live_kinds(bridge) == BUILT_CHILDREN


def test_the_count_falls_when_a_timer_is_taken_off_the_bridge(bridge):
    """The positive control: the counter sees a timer leave the object."""
    bridge._persist_timer.setParent(None)
    after = live_kinds(bridge)
    assert after["QTimer"] == BUILT_CHILDREN["QTimer"] - 1
    assert after != BUILT_CHILDREN


def test_the_two_timers_carry_the_intervals_the_surface_declares(bridge):
    assert bridge._drain_timer.interval() == surface.QUEUE_DRAIN_INTERVAL_MS
    assert bridge._persist_timer.interval() == surface.PERSIST_DEBOUNCE_MS
    assert bridge._persist_timer.isSingleShot() is True
    assert bridge._drain_timer.isSingleShot() is False
    assert surface.TIMERS == {
        "drain": surface.QUEUE_DRAIN_INTERVAL_MS,
        "persist": surface.PERSIST_DEBOUNCE_MS,
    }


def watch(bridge) -> dict:
    """Connect a recorder to every signal the surface names."""
    seen: dict = {name: [] for name in surface.SIGNALS}
    for name in surface.SIGNALS:
        getattr(bridge, name).connect(lambda *args, key=name: seen[key].append(args))
    return seen


def test_a_finished_competition_raises_the_two_signals_the_surface_names(bridge):
    """The write path still announces itself, so the tab still refreshes."""
    seen = watch(bridge)
    bridge._on_worker_done({"competition_id": "C-1"})
    assert seen["chain_updated"] == [()]
    assert seen["competition_completed"] == [({"competition_id": "C-1"},)]
    assert seen["chain_reset"] == []
    assert bridge._persist_timer.isActive() is True


def test_a_failed_competition_raises_only_the_one_that_carries_the_error(bridge):
    """The positive control: the recorder would have seen the other two."""
    seen = watch(bridge)
    bridge._on_worker_done({"error": "it broke"})
    assert seen["competition_completed"] == [({"error": "it broke"},)]
    assert seen["chain_updated"] == []
    assert seen["chain_reset"] == []
    assert bridge._persist_timer.isActive() is False


def test_a_queued_request_reaches_the_bridge_without_running_anything(bridge):
    """The write path is a queue, so any producer thread may fill it."""
    asked = shipped.CompetitionRequest(symbol="BTC/USDT", season=1, n_bots=3)
    assert bridge._queue.qsize() == 0
    bridge.request_competition(asked)
    assert bridge._queue.qsize() == 1
    assert bridge._queue.get_nowait() is asked
    assert bridge._queue.qsize() == 0


def test_the_request_carries_the_four_fields_the_surface_names():
    import dataclasses

    named = [one.name for one in dataclasses.fields(shipped.CompetitionRequest)]
    assert named == list(surface.REQUEST_FIELDS)
    built = shipped.CompetitionRequest(symbol="ETH/USDT", season=3)
    assert built.n_bots == surface.DEFAULT_BOT_COUNT
    assert built.round_id is None


def test_the_bridge_and_the_surface_name_the_same_saved_file():
    assert shipped.DEFAULT_PERSIST_PATH == Path.home().joinpath(*surface.PERSIST_PARTS)
    assert shipped.SCHEMA_VERSION == surface.SCHEMA_VERSION
    assert shipped.QUEUE_DRAIN_INTERVAL_MS == surface.QUEUE_DRAIN_INTERVAL_MS
    assert shipped.PERSIST_DEBOUNCE_MS == surface.PERSIST_DEBOUNCE_MS
