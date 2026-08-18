"""C39f: drawing a wire must not rewrite persisted trading config.

THE DEFECT
`_on_wire_created` executed `bot.config.profit_folding_active = True` on
every `wire.created` event. Three things made that indefensible rather
than merely convenient:

  1. It rewrote PERSISTED TRADING CONFIG from a GUI event handler, and
     the 60-second save then wrote it to disk. An operator who turned
     Profit Folding OFF found it back on, with nothing recording who
     changed it.
  2. `bot_container.py:2404` re-emits `wire.created` for every stored
     wire on EVERY BOOT — so this was not a one-time convenience at draw
     time. It re-applied at every launch, permanently. The setting could
     not be made to stick.
  3. The flag is load-bearing: it gates target growth
     (`scrumming_bot.py:1356`) and the DIST tranche rebuild (`:8688`).

Operator, 2026-08-06: "Persisted systems configurations should only be
getting modified at the user level, no?"

WHY RESTORING IT "SO WIRES WORK" WOULD BE WRONG
The dominant wire flow does not depend on this flag.
`_route_scrum_proceeds_via_wires` — scrum-time routing, the primary
path — never reads it. Only the secondary fold-compound route is gated,
and indirectly, via `_growth_applied`. Removing the override does not
disable wiring.

The handler is exercised directly with a stub `self`; constructing a
whole MainWindow would test Qt, not this decision.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_window import MainWindow  # noqa: E402


class _Log:
    def __init__(self):
        self.lines = []

    def log(self, msg, level="info"):
        self.lines.append((level, msg))


def _call(folding: bool):
    """Drive _on_wire_created against a bot with the given flag."""
    bot = SimpleNamespace(config=SimpleNamespace(
        profit_folding_active=folding))
    mgr = SimpleNamespace(get_bot=lambda _bid: bot)
    log = _Log()
    me = SimpleNamespace(_bot_manager=mgr, _status_log=log)
    event = SimpleNamespace(data={
        "source_id": "abcdef1234", "target_id": "target99", "pct": 50})
    MainWindow._on_wire_created(me, event)
    return bot, log


class TestItDoesNotRewriteConfig:
    def test_folding_OFF_stays_off(self):
        """The whole cascade in one assertion."""
        bot, _log = _call(folding=False)
        assert bot.config.profit_folding_active is False, \
            "drawing a wire re-enabled Profit Folding without consent"

    def test_folding_ON_stays_on(self):
        """Negative control: it must not flip the other way either.
        The handler reports state; it does not own it."""
        bot, _log = _call(folding=True)
        assert bot.config.profit_folding_active is True

    def test_the_boot_reemit_path_cannot_flip_it(self):
        """bot_container.py:2404 re-emits wire.created for every stored
        wire on every boot. Ten replays must leave the flag alone."""
        bot = SimpleNamespace(config=SimpleNamespace(
            profit_folding_active=False))
        mgr = SimpleNamespace(get_bot=lambda _bid: bot)
        me = SimpleNamespace(_bot_manager=mgr, _status_log=_Log())
        event = SimpleNamespace(data={"source_id": "abc", "pct": 50})
        for _ in range(10):
            MainWindow._on_wire_created(me, event)
        assert bot.config.profit_folding_active is False


class TestItStillReportsUsefully:
    def test_folding_off_is_surfaced_not_silently_accepted(self):
        """Removing the override must not make the consequence
        invisible — the operator should know the fold-compound
        contribution will not fire."""
        _bot, log = _call(folding=False)
        assert log.lines, "wire creation produced no operator feedback"
        level, msg = log.lines[0]
        assert level == "warning"
        assert "OFF" in msg
        assert "scrum" in msg.lower(), \
            "must say scrum-time routing is unaffected, or the operator " \
            "will think the wire is dead"

    def test_folding_on_reports_success(self):
        _bot, log = _call(folding=True)
        level, msg = log.lines[0]
        assert level == "success"
        assert "ON" in msg


class TestTheAssignmentIsGone:
    def test_source_no_longer_assigns_the_flag_in_the_handler(self):
        """Structural guard. The behavioural tests above use a stub, so
        a restored assignment guarded by some other condition could slip
        past them."""
        import ast
        src = (REPO_ROOT / "src" / "gui" / "main_window.py").read_text(
            encoding="utf-8")
        tree = ast.parse(src)
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "_on_wire_created")
        assigns = [
            n for n in ast.walk(fn)
            if isinstance(n, ast.Assign)
            for t in n.targets
            if isinstance(t, ast.Attribute)
            and t.attr == "profit_folding_active"
        ]
        assert not assigns, (
            f"_on_wire_created assigns profit_folding_active at line(s) "
            f"{[a.lineno for a in assigns]} — a GUI handler must not "
            f"rewrite persisted trading config")
