"""C02: one durable Smart Wire channel, and one staging file per writer.

WHICH CHANNEL IS REAL — measured, not argued
Two mechanisms claim to persist wires:

  1. `scrumming_state.smart_wire_routes`, written directly to
     bot_state.json by bot_visualizer
  2. top-level `smart_wires`, written by SmartWireManager.export_wires()
     through StateManager

Channel 1 cannot survive: `export_scrumming_state` emits 31 keys and
`smart_wire_routes` is not among them, so the 60-second save rebuilds
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

import ast
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

VIZ = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"
STATE_MGR = REPO_ROOT / "src" / "core" / "state_manager.py"
SCRUM = REPO_ROOT / "src" / "trading" / "scrumming_bot.py"


def _fn(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name
    )


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

        assert dest.read_text(encoding="utf-8") == original, (
            "a failed write corrupted or truncated the existing file"
        )
        leftovers = [p.name for p in tmp_path.iterdir() if p != dest]
        assert leftovers == [], f"staging file left behind after failure: {leftovers}"


class TestChannelOneCannotSurviveASave:
    def test_export_does_not_emit_smart_wire_routes(self):
        """Why channel 1 is empty on all 35 live bots: the exporter
        that rebuilds scrumming_state every 60s does not carry it."""
        fn = _fn(SCRUM, "export_scrumming_state")
        keys = {
            k.value
            for n in ast.walk(fn)
            if isinstance(n, ast.Dict)
            for k in n.keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
        }
        assert (
            "main_lots" in keys
        ), "positive control failed — extractor found no known key"
        assert "smart_wire_routes" not in keys, (
            "smart_wire_routes is now exported; if that is deliberate, "
            "channel 1 has become durable and this cascade's premise "
            "needs revisiting"
        )

    def test_the_trading_layer_never_reads_it(self):
        """A key only the GUI knows about is not a persistence
        mechanism for the engine."""
        hits = []
        for p in (REPO_ROOT / "src" / "trading").rglob("*.py"):
            if "smart_wire_routes" in p.read_text(encoding="utf-8"):
                hits.append(p.name)
        assert not hits, f"src/trading now references it: {hits}"


class TestTheGuiWriterIsNoLongerSilent:
    def test_failure_is_logged(self):
        """A failed write to the operator's position file could
        previously fail for weeks with no signal."""
        fn = _fn(VIZ, "_save_bot_state_dict")
        handlers = [n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler)]
        assert handlers, "no exception handler in _save_bot_state_dict"
        for h in handlers:
            bare_pass = len(h.body) == 1 and isinstance(h.body[0], ast.Pass)
            assert not bare_pass, (
                "the write to bot_state.json still swallows failures " "silently"
            )
        src = ast.get_source_segment(VIZ.read_text(encoding="utf-8"), fn) or ""
        assert "logger.error" in src
