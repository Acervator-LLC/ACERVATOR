"""A sim fleet that cannot get a private registry must abort, not fall back.

C15, cascade 6 of the remediation sequence. Risk tier: live-money.

THE DEFECT
`CapitalReservationRegistry` is a process-wide singleton that PERSISTS to
`~/.acervator/reservation_state.json` — the operator's live capital
state. Sim bots must never touch it. v3.24.31 gave sim fleets a private,
non-persisting registry; v3.24.35 (CV1) made the factory RAISE instead of
returning `None`, because returning `None` sent `ScrummingBot._crr()` to
the process-wide singleton and silently reinstated the defect.

The recorded cost of that defect: 16,558 bot_ids against 35 real ones,
16,523 orphans, 6.5 MB of sim residue feeding live allocation decisions.

WHAT WAS STILL MISSING (audited 2026-08-07)
CV1 fixed the factory. The other four C15 steps were never done:

  - `_instantiate_bot` accepted `capital_registry=None` and built the bot
    anyway, so any caller that omitted it produced a sim bot wired to the
    live singleton.
  - `ScrummingBot._crr()` had no `_sim_mode` check and still fell through
    to `get_registry()` — the structural backstop the plan calls for.
  - `nuclear_controller.py:355` called the now-raising factory unguarded.
  - Nothing asserted at replay start that the constructed bots were
    actually isolated.

Defence in depth is the point. The factory raising is the first line; a
sim bot that somehow reaches `_crr()` without a registry must still
refuse rather than resolve the live one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

LIVE_STATE = Path.home() / ".acervator" / "reservation_state.json"


def _live_fingerprint():
    """(mtime, size) of the operator's real reservation state, or None.

    Every test that runs sim construction asserts this is unchanged. The
    file is READ, never written.
    """
    if not LIVE_STATE.exists():
        return None
    st = LIVE_STATE.stat()
    return (st.st_mtime, st.st_size)


class TestTheFactoryFailsClosed:
    def test_it_returns_a_private_registry_normally(self):
        """POSITIVE CONTROL. If the factory cannot produce a registry at
        all, every abort assertion below passes for the wrong reason."""
        from src.gui.simulator_tab.fleet.fleet_replay_controller import (
            _make_sim_capital_registry,
        )

        reg = _make_sim_capital_registry()
        assert reg is not None

    def test_the_private_registry_does_not_autosave(self):
        """Autosave is what would reach the operator's tree."""
        from src.gui.simulator_tab.fleet.fleet_replay_controller import (
            _make_sim_capital_registry,
        )

        reg = _make_sim_capital_registry()
        assert getattr(reg, "_autosave", False) is False

    def test_the_private_registry_is_not_the_singleton(self):
        from src.trading.capital_reservation import get_registry
        from src.gui.simulator_tab.fleet.fleet_replay_controller import (
            _make_sim_capital_registry,
        )

        assert _make_sim_capital_registry() is not get_registry()

    def test_it_raises_when_the_temp_dir_cannot_be_made(self, monkeypatch):
        """M10: abort with a reason rather than resolve the live one."""
        import tempfile

        from src.gui.simulator_tab.fleet.fleet_replay_controller import (
            _make_sim_capital_registry,
        )

        def _boom(*a, **k):
            raise OSError("no space left on device")

        monkeypatch.setattr(tempfile, "mkdtemp", _boom)
        with pytest.raises(RuntimeError) as ei:
            _make_sim_capital_registry()
        assert (
            "isolation" in str(ei.value).lower()
        ), "the abort must name WHY, not just fail"

    def test_the_abort_leaves_the_live_file_untouched(self, monkeypatch):
        import tempfile

        from src.gui.simulator_tab.fleet.fleet_replay_controller import (
            _make_sim_capital_registry,
        )

        before = _live_fingerprint()
        monkeypatch.setattr(
            tempfile, "mkdtemp", lambda *a, **k: (_ for _ in ()).throw(OSError("boom"))
        )
        with pytest.raises(RuntimeError):
            _make_sim_capital_registry()
        assert _live_fingerprint() == before


class TestInstantiateBotRefusesWithoutARegistry:
    """C15 step 3. The factory raising protects the callers that USE it;
    a caller that never asked would still have built a bot wired to the
    live singleton."""

    def test_no_registry_builds_no_bot(self):
        """NOTE ON VACUITY. `_instantiate_bot` catches everything and
        returns None, so `bot is None` alone proves nothing — the first
        version of this test passed on the UNFIXED code because a dummy
        exchange failed construction for an unrelated reason. The
        refusal is therefore pinned three ways: the return value here,
        the operator-visible reason below, and the structural check that
        the guard precedes the try block."""
        from src.gui.simulator_tab.fleet.fleet_replay_controller import _instantiate_bot

        before = _live_fingerprint()
        bot = _instantiate_bot({"symbol": "BTC/USD", "bot_id": "x"}, object(), None)
        assert bot is None, (
            "a sim bot must not be constructed without an injected "
            "capital registry — it would resolve the live singleton"
        )
        assert _live_fingerprint() == before

    def test_the_guard_runs_before_the_blanket_except(self):
        """Structural, and this is the assertion that is NOT vacuous.

        Inside the try block the missing registry would be swallowed
        into an ordinary construction failure and hidden among the
        others."""
        import ast

        import src.gui.simulator_tab.fleet.fleet_replay_controller as m

        src = Path(m.__file__).read_text(encoding="utf-8")
        fn = next(
            n
            for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.FunctionDef) and n.name == "_instantiate_bot"
        )
        body = [s for s in fn.body if not isinstance(s, ast.Expr)]
        first = body[0]
        assert isinstance(first, ast.If), (
            "the registry guard is not the first statement in " "_instantiate_bot"
        )
        first_try = next(
            (i for i, s in enumerate(fn.body) if isinstance(s, ast.Try)), None
        )
        assert first_try is None or first.lineno < fn.body[first_try].lineno

    def test_the_refusal_is_not_silent(self):
        """caplog cannot see this one: `logging_engine` sets
        `propagate = False` on the `acervator` logger, so records from
        its children never reach the root handler pytest attaches.
        Capture on the real logger instead."""
        import logging

        import src.gui.simulator_tab.fleet.fleet_replay_controller as m

        records = []

        class _Capture(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        h = _Capture(level=logging.WARNING)
        m.logger.addHandler(h)
        try:
            m._instantiate_bot({"symbol": "BTC/USD", "bot_id": "x"}, object(), None)
        finally:
            m.logger.removeHandler(h)

        blob = " ".join(records).lower()
        assert "registry" in blob, (
            "the operator must be told WHY the bot was skipped; got: " f"{records}"
        )
        assert "reservation_state" in blob, (
            "the message should name the live file at risk, so the "
            "operator can weigh the refusal"
        )


class TestCrrBackstop:
    """C15 step 4. The structural backstop: even if a sim bot is somehow
    constructed with no registry, `_crr()` must refuse rather than hand
    it the process-wide autosaving one."""

    def _bot(self, sim_mode):
        from src.trading.scrumming_bot import ScrummingBot

        b = object.__new__(ScrummingBot)
        b.bot_id = "b1"
        b._capital_registry = None
        b._sim_mode = sim_mode
        return b

    def test_a_sim_bot_gets_none_not_the_singleton(self):
        from src.trading.capital_reservation import get_registry

        got = self._bot(sim_mode=True)._crr()
        assert got is not get_registry(), (
            "a sim bot resolved the process-wide registry that autosaves "
            "to the operator's reservation_state.json"
        )
        assert got is None

    def test_a_live_bot_still_gets_the_singleton(self):
        """NEGATIVE CONTROL. Breaking live reservation would be a far
        worse outcome than the defect being fixed."""
        from src.trading.capital_reservation import get_registry

        assert self._bot(sim_mode=False)._crr() is get_registry()

    def test_an_injected_registry_always_wins(self):
        sentinel = object()
        b = self._bot(sim_mode=True)
        b._capital_registry = sentinel
        assert b._crr() is sentinel
