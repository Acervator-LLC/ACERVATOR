"""C02: one durable Smart Wire channel, and one staging file per writer.

WHICH CHANNEL IS REAL — measured, not argued
Two mechanisms claim to persist wires:

  1. `scrumming_state.smart_wire_routes`, written directly to
     bot_state.json by bot_visualizer
  2. top-level `smart_wires`, written by SmartWireManager.export_wires()
     through StateManager

Channel 1 cannot survive: `smart_wire_routes` is not among the keys
`export_scrumming_state` emits, so the 60-second save rebuilds
each bot's scrumming_state without it. On the operator's live file
2026-08-06: **0 of 35 bots carried the key, 0 route entries**, while
channel 2 held all **40 wires** and 48 ledger rows.

So channel 2 is the durable one. Channel 1 is a write-only key with a
60-second lifetime, and the module comment calling it *the* persistence
mechanism sends the next reader debugging a lost wire to a field that is
empty for all but a minute of every hour.

THE SHARED STAGING FILE — the reason this is a safety fix, not tidying
`bot_visualizer._save_bot_state_dict` once staged through
`p.with_suffix(".tmp")` — byte-for-byte the same `bot_state.tmp` that
`StateManager.save_state` used. Two independent writers, one temp name:
either could rename the other's partial write over the live position
file holding 1,949 lots. Both writers now route through
`core.io_utils.atomic_write_json`, whose staging file is unique per call,
so the collision is structurally impossible. `TestStagingFilesDoNotCollide`
pins that property behaviorally rather than by inspecting either writer's
source.

NOTHING HERE CONSTRUCTS A StateManager OR WRITES INTO THE LIVE TREE — the
staging tests write only under pytest's `tmp_path`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ROUTES_KEY = "smart_wire_routes"
GUI_ROUTES = [{"dest_bot_id": "b2", "pct": 25.0}]


def _bare_bot():
    """A ScrummingBot carrying every field ``export_scrumming_state`` reads.

    ``_smart_wire_routes`` is set beside them, so an exporter that carried the
    GUI's key would show it.
    """
    from src.trading.scrumming_bot import ScrummingBot

    bot = object.__new__(ScrummingBot)
    bot._target_balance = 100.0
    bot._anchor_target_balance = 100.0
    bot._last_trade_price = 1.0
    bot._last_trade_side = None
    bot._quote_to_usd = 1.0
    bot._fold_queue_usd = 0.0
    bot._dist_accumulator = 0.0
    bot._hedge_bal = 0.0
    bot._hedge_trades = 0
    bot._scrum_target_mode = "usd"
    bot._scrum_target_side = None
    bot._main_lots = [{"units": 1.0, "initial_buy_price": 1.0}]
    bot._fold_tranches = []
    bot._smart_wire_routes = list(GUI_ROUTES)
    bot._current_holdings = 1.0
    bot._pending_wire_credits = 0.0
    bot.bot_id = "c02-bot"
    bot._bus = type("B", (), {"emit": lambda self, *_a, **_k: None})()
    bot.config = type("C", (), {"position_ceiling_enabled": False})()
    return bot


def _exported_state() -> dict:
    """What ``export_scrumming_state`` writes for a ``_bare_bot``."""
    from src.trading.scrumming_bot import ScrummingBot

    return ScrummingBot.export_scrumming_state(_bare_bot())


class TestStagingFilesDoNotCollide:
    """The collision-safety property, exercised through the real helper
    both writers now route through. A second writer's in-flight staging
    file must never be clobbered, and a completed write must leave nothing
    behind — regardless of how either writer's source is shaped."""

    def test_a_second_writers_staging_file_is_never_clobbered(self, tmp_path):
        """The old collision made concrete: both writers staged through
        ``dest.with_suffix('.tmp')``. A file already sitting at that
        predictable path — standing in for the other writer's partial
        write — must survive the write untouched, proving the helper does
        not stage through it."""
        from src.core.io_utils import atomic_write_json

        dest = tmp_path / "bot_state.json"
        other_writers_partial = dest.with_suffix(".tmp")
        sentinel = "OTHER WRITER'S HALF-WRITTEN POSITION FILE"
        other_writers_partial.write_text(sentinel, encoding="utf-8")

        atomic_write_json(dest, {"bots": {"a": 1}})

        assert other_writers_partial.read_text(encoding="utf-8") == sentinel, (
            "the write reused the predictable shared staging path and "
            "clobbered a concurrent writer's in-flight file"
        )
        assert json.loads(dest.read_text(encoding="utf-8")) == {"bots": {"a": 1}}

    def test_a_completed_write_leaves_no_staging_file_behind(self, tmp_path):
        from src.core.io_utils import atomic_write_json

        dest = tmp_path / "bot_state.json"
        atomic_write_json(dest, {"bots": {}})

        leftovers = [p.name for p in tmp_path.iterdir() if p != dest]
        assert leftovers == [], f"staging files left behind: {leftovers}"

    def test_a_failed_write_leaves_target_and_dir_intact(self, tmp_path):
        """Positive control for the two assertions above: force the write
        to fail mid-flight and prove the destination is unchanged and no
        staging file survives. Without this, the green above could mean
        the writer simply never stages anything."""
        from src.core.io_utils import atomic_write_json

        dest = tmp_path / "bot_state.json"
        atomic_write_json(dest, {"bots": {"a": 1}})
        original = dest.read_text(encoding="utf-8")

        class Unserializable:
            pass

        with pytest.raises(TypeError):
            atomic_write_json(dest, {"bad": Unserializable()}, default=None)

        assert (
            dest.read_text(encoding="utf-8") == original
        ), "a failed write corrupted or truncated the existing file"
        leftovers = [p.name for p in tmp_path.iterdir() if p != dest]
        assert leftovers == [], f"staging file left behind after failure: {leftovers}"


class TestChannelOneCannotSurviveASave:
    def test_the_exporter_carries_the_keys_the_save_rebuilds(self):
        """POSITIVE CONTROL: every assertion below reads this dict."""
        exported = _exported_state()
        assert "main_lots" in exported, sorted(exported)
        assert len(exported) > 30, len(exported)

    def test_the_export_drops_the_gui_routes(self):
        """The 60-second save rebuilds ``scrumming_state`` from this dict, so
        a key it omits cannot survive."""
        exported = _exported_state()
        assert ROUTES_KEY not in exported, (
            f"{ROUTES_KEY} is now exported; channel 1 has become durable "
            f"and this cascade's premise needs revisiting"
        )

    def test_an_import_of_the_gui_routes_leaves_nothing_the_export_carries(self):
        """A restored state carrying the key round-trips without it."""
        from src.trading.scrumming_bot import ScrummingBot

        bot = _bare_bot()
        del bot._smart_wire_routes
        restored = dict(_exported_state())
        restored[ROUTES_KEY] = list(GUI_ROUTES)
        ScrummingBot.import_scrumming_state(bot, restored)
        assert ROUTES_KEY not in ScrummingBot.export_scrumming_state(bot)
        assert getattr(bot, "_" + ROUTES_KEY, None) is None


def _drive_the_gui_write(write_json):
    """Run the real ``_save_bot_state_dict`` with ``write_json`` in place.

    Returns the ERROR records ``bot_visualizer.logger`` emitted, collected off
    that logger directly: ``acervator`` does not propagate to caplog's handler.
    """
    import logging

    import src.core.io_utils as io_utils
    import src.gui.bot_visualizer as viz

    records: list = []

    class _Collect(logging.Handler):
        def emit(self, record):
            if record.levelno >= logging.ERROR:
                records.append(record.getMessage())

    handler = _Collect()
    kept = io_utils.atomic_write_json
    io_utils.atomic_write_json = write_json
    viz.logger.addHandler(handler)
    try:
        viz.BotVisualizationTab._save_bot_state_dict(None, {"bots": {}})
    finally:
        viz.logger.removeHandler(handler)
        io_utils.atomic_write_json = kept
    return records


class TestTheGuiWriterIsNoLongerSilent:
    def test_a_failed_write_is_logged(self):
        """``atomic_write_json`` raises, so no file is opened and the
        operator's tree is never touched."""
        import src.gui.bot_visualizer as viz

        if not viz._HAS_QT:
            pytest.skip("bot_visualizer declares its writer under the Qt guard")

        def _boom(*args, **kwargs):
            del args, kwargs
            raise OSError("disk full")

        said = _drive_the_gui_write(_boom)
        assert any(
            "bot_state.json" in message for message in said
        ), f"the failed write said nothing: {said}"

    def test_POSITIVE_CONTROL_a_successful_write_logs_no_error(self):
        """A writer that logged on every call would make the test above green
        without ever failing."""
        import src.gui.bot_visualizer as viz

        if not viz._HAS_QT:
            pytest.skip("bot_visualizer declares its writer under the Qt guard")

        written = {}

        def _record(path, payload, **kwargs):
            del kwargs
            written["path"] = path
            written["payload"] = payload

        said = _drive_the_gui_write(_record)
        assert written["payload"] == {"bots": {}}
        assert Path(written["path"]).name == "bot_state.json"
        assert said == [], said
