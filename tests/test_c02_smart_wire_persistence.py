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
`bot_visualizer._save_bot_state_dict` staged through
`p.with_suffix(".tmp")` — byte-for-byte the same `bot_state.tmp` that
`StateManager.save_state` uses. Two independent writers, one temp name:
either can rename the other's partial write over the live position file
holding 1,949 lots. No interleaving was demonstrated (asyncio is pumped
on the Qt main thread), but the collision is structural, and it becomes
corruption the moment either writer moves off that thread.

NOTHING HERE CONSTRUCTS A StateManager OR WRITES ANYTHING. Its default
config_dir is the operator's live tree.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

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


def _suffix_args(fn: ast.FunctionDef) -> list[str]:
    """Literal arguments passed to `.with_suffix(...)` inside `fn`."""
    out = []
    for n in ast.walk(fn):
        if (
            isinstance(n, ast.Call)
            and getattr(n.func, "attr", "") == "with_suffix"
            and n.args
        ):
            a = n.args[0]
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                out.append(a.value)
            elif isinstance(a, ast.JoinedStr):
                out.append("<f-string>")
    return out


class TestStagingFilesDoNotCollide:
    def test_the_extractor_sees_both_writers(self):
        """Positive control. If either walk found nothing, the collision
        test below would pass by finding no evidence of a collision."""
        assert _suffix_args(
            _fn(STATE_MGR, "save_state")
        ), "no with_suffix() found in StateManager.save_state"
        assert _suffix_args(
            _fn(VIZ, "_save_bot_state_dict")
        ), "no with_suffix() found in _save_bot_state_dict"

    def test_gui_writer_does_not_stage_through_bot_state_tmp(self):
        """The collision itself. `.tmp` here means the GUI stages
        through the same file StateManager does."""
        gui = _suffix_args(_fn(VIZ, "_save_bot_state_dict"))
        assert ".tmp" not in gui, (
            f"bot_visualizer stages through {gui} — the same temp path "
            f"StateManager.save_state uses. Either writer can rename "
            f"the other's partial write over the live position file."
        )

    def test_state_manager_still_uses_its_own(self):
        """Negative control: the fix must move the GUI writer, not
        StateManager, whose path is the long-standing one."""
        assert ".tmp" in _suffix_args(_fn(STATE_MGR, "save_state"))


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
