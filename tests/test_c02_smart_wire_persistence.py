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
`StateManager.save_state` used. Two independent writers, one temp name:
either can rename the other's partial write over the live position file
holding 1,949 lots. No interleaving was demonstrated (asyncio is pumped
on the Qt main thread), but the collision is structural, and it becomes
corruption the moment either writer moves off that thread.

Neither writer names a staging path now. Both call
`src.core.io_utils.atomic_write_json`, which stages through
`tempfile.mkstemp` — created O_EXCL, so the name is unique against every
other process and thread. The collision is closed by the operating
system rather than by two conventions happening to differ, and the
runtime demonstration of that is in
`tests/test_atomic_write_site_equivalence.py`.

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


def _source_file_of(qualname_owner, method_name: str) -> Path:
    """Path to the file that actually defines ``method_name``, following
    the method wherever it has been extracted to."""
    import inspect

    sf = inspect.getsourcefile(getattr(qualname_owner, method_name))
    assert sf is not None
    return Path(sf)


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


IO_UTILS = REPO_ROOT / "src" / "core" / "io_utils.py"


def _called_names(fn: ast.FunctionDef) -> set[str]:
    """Names of every function called directly inside `fn`."""
    return {
        n.func.id
        for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    } | {
        n.func.attr
        for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }


class TestStagingFilesDoNotCollide:
    def test_the_extractor_sees_both_writers(self):
        """Positive control. If either walk found nothing, the collision
        tests below would pass by finding no evidence of a collision."""
        assert "atomic_write_json" in _called_names(
            _fn(STATE_MGR, "save_state")
        ), "StateManager.save_state does not reach the shared writer"
        assert "atomic_write_json" in _called_names(
            _fn(VIZ, "_save_bot_state_dict")
        ), "bot_visualizer does not reach the shared writer"

    def test_neither_writer_names_a_staging_path(self):
        """The collision itself. A literal staging name here is a name
        the other writer can also produce."""
        for path, name in ((STATE_MGR, "save_state"), (VIZ, "_save_bot_state_dict")):
            fn = _fn(path, name)
            assert _suffix_args(fn) == [], (
                f"{name} names its own staging path {_suffix_args(fn)}; "
                f"either writer can rename the other's partial write over "
                f"the live position file."
            )
            assert "mkstemp" not in _called_names(fn)

    def test_the_shared_writer_stages_through_mkstemp(self):
        """What makes the name unique. mkstemp creates with O_EXCL, so
        no second writer can be handed the same staging path."""
        fn = _fn(IO_UTILS, "atomic_write_bytes")
        assert "mkstemp" in _called_names(fn)
        assert "replace" in _called_names(fn)


class TestChannelOneCannotSurviveASave:
    def test_export_does_not_emit_smart_wire_routes(self):
        """Why channel 1 is empty on all 35 live bots: the exporter
        that rebuilds scrumming_state every 60s does not carry it."""
        from src.trading.scrumming_bot import ScrummingBot

        fn = _fn(
            _source_file_of(ScrummingBot, "export_scrumming_state"),
            "export_scrumming_state",
        )
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
