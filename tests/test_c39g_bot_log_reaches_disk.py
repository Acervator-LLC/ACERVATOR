"""C39g: ScrummingBot's diagnostics must reach a file.

THE DEFECT
ScrummingBot emits its entire diagnostic vocabulary over the `bot.log`
bus topic — [COMPOUND SKIPPED], TARGET GROWN, TARGET-GROW HELD,
FOLD_DIAG_SURPLUS_CHECK, [WIRE FIRE]. The source says outright that
these exist to be searched, e.g.

    "Grep for '[COMPOUND SKIPPED]' in the log to spot fold events that
     had no compounding effect."

That was impossible. `bot.log` had exactly two subscribers, both GUI
windows, and both terminate at `StatusLog.log()`
(main_window.py:256-268) — which contains no open(), no write(), no
logger call. The messages reached a scrollback panel and died with the
session.

MEASURED 2026-08-06, before the fix: zero occurrences of every one of
those markers across the entire log tree, including the 7.4 GB
console/system.log. Not because the code paths never ran — because the
channel never touched a file. The operator has been unable to diagnose
compounding for the whole development history while the instrument
built to explain it wrote to a widget.

These pins assert the channel reaches DISK. They deliberately do not
assert anything about compounding itself: that question cannot be
answered until this lands and one real session produces evidence.

tmp_path only — LogManager takes log_dir for exactly this.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.event_bus import EventBus  # noqa: E402
from src.core.logging_engine import LogManager  # noqa: E402


@pytest.fixture
def wired(tmp_path):
    """A LogManager rooted in tmp_path, attached to a private bus."""
    mgr = LogManager(log_dir=tmp_path)
    bus = EventBus()
    mgr.attach_to_bus(bus)
    return mgr, bus, tmp_path


def _diag_lines(root: Path) -> list[dict]:
    hits = list(root.rglob("diagnostics.log"))
    if not hits:
        return []
    return [
        json.loads(ln)
        for ln in hits[0].read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]


class TestBotLogReachesDisk:
    def test_a_bot_log_emission_is_written(self, wired):
        _mgr, bus, root = wired
        bus.emit("bot.log", bot_id="abc123", message="hello from a bot")
        lines = _diag_lines(root)
        assert lines, "bot.log produced no diagnostics.log entry"
        assert lines[0]["data"]["message"] == "hello from a bot"
        assert lines[0]["bot_id"] == "abc123"

    @pytest.mark.parametrize(
        "marker",
        [
            "[COMPOUND SKIPPED] (auto): profit_folding_active=False",
            "TARGET GROWN (auto): surplus $12.3456, applied $1.0000",
            "TARGET-GROW HELD (auto): surplus accrues to standing pool",
            "FOLD_DIAG_SURPLUS_CHECK: buy_fill=$0.00001234",
            "[WIRE FIRE] scrum-route: $4.2000",
        ],
    )
    def test_each_real_marker_survives_to_disk(self, wired, marker):
        """The exact vocabulary the operator was told to grep for."""
        _mgr, bus, root = wired
        bus.emit("bot.log", bot_id="b1", message=marker)
        blob = "\n".join(json.dumps(x) for x in _diag_lines(root))
        assert marker.split(":")[0] in blob, f"{marker!r} did not reach disk"

    def test_many_messages_all_land(self, wired):
        """One line per emission — no coalescing, no last-write-wins."""
        _mgr, bus, root = wired
        for i in range(50):
            bus.emit("bot.log", bot_id="b1", message=f"msg-{i}")
        assert len(_diag_lines(root)) == 50

    def test_it_is_ndjson_one_object_per_line(self, wired):
        """Grep-friendliness is the whole point; a pretty-printed blob
        would defeat the purpose as thoroughly as the GUI panel did."""
        _mgr, bus, root = wired
        bus.emit("bot.log", bot_id="b1", message="one")
        bus.emit("bot.log", bot_id="b1", message="two")
        f = list(root.rglob("diagnostics.log"))[0]
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                json.loads(line)  # each line parses alone


class TestItCannotBreakTheTradingLoop:
    def test_an_empty_message_is_skipped_not_written(self, wired):
        _mgr, bus, root = wired
        bus.emit("bot.log", bot_id="b1", message="")
        assert _diag_lines(root) == []

    def test_a_writer_failure_does_not_propagate(self, wired, monkeypatch):
        """A diagnostic writer must never take down the loop it
        observes."""
        mgr, bus, _root = wired

        def boom(*_a, **_kw):
            raise OSError("simulated disk failure")

        monkeypatch.setattr(mgr._diag_writer, "write", boom)
        bus.emit("bot.log", bot_id="b1", message="should not raise")

    def test_a_malformed_event_is_ignored(self, wired):
        _mgr, bus, root = wired
        bus.emit("bot.log")  # no message, no bot_id
        assert _diag_lines(root) == []


class TestSubscriptionIsSymmetric:
    def test_bot_log_is_subscribed_and_unsubscribed(self):
        """An asymmetric teardown leaks a handler on the global bus —
        the exact shape of the Nuclear BotManager leak found in the Bot
        Swarm audit."""
        src = (REPO_ROOT / "src" / "core" / "logging_engine.py").read_text(
            encoding="utf-8"
        )
        assert 'bus.subscribe("bot.log"' in src
        assert 'bus.unsubscribe("bot.log"' in src

    def test_detaching_stops_the_writes(self, wired):
        mgr, bus, root = wired
        bus.emit("bot.log", bot_id="b1", message="before")
        before = len(_diag_lines(root))
        if hasattr(mgr, "detach_from_bus"):
            mgr.detach_from_bus(bus)
            bus.emit("bot.log", bot_id="b1", message="after")
            assert len(_diag_lines(root)) == before
