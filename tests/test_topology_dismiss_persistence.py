"""A 24 h dismissal must actually last 24 h (C35 / SWARM-4.29).

THE DEFECT
`MarketInspectorTopologies._dismissed` was a plain dict on the widget. The Dismiss
button's tooltip says "Suppress this proposal for 24 hours" and the
confirm dialog asks "Suppress this proposal for 24 h?", but the cache
died with the widget: closing and reopening the tab resurrected every
dismissed card. `DISMISS_TTL_SECONDS` was defined and enforced only
within a single session.

WHY THE STORE IS INJECTED RATHER THAN CONSTRUCTED
`SettingsManager()` resolves `Path.home()/".acervator"` with no env
override (`settings.py:222`). Constructing one inside this widget would
mean any test that renders the pane writes the operator's live
settings.json — a breach that has already happened once in this repo.
The pane takes a store with `get`/`set` and defaults to None, so
headless construction touches no disk at all.

THE EXPIRY-ON-LOAD RULE
A dismissal that lapsed while the app was closed has lapsed. Importing
it and re-suppressing would silently extend a 24 h promise across every
restart, which is a different defect wearing the fix's clothes.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.market_inspector_topologies import (  # noqa: E402
    DISMISS_SETTINGS_KEY,
    DISMISS_TTL_SECONDS,
    MarketInspectorTopologies,
)


class _Store:
    """The `get`/`set` surface, backed by a dict. Never touches disk."""

    def __init__(self, initial=None):
        self.data = dict(initial or {})
        self.writes = 0

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.writes += 1
        self.data[key] = value


class _Boom(_Store):
    def set(self, key, value):
        raise RuntimeError("settings volume unavailable")

    def get(self, key, default=None):
        raise RuntimeError("settings volume unavailable")


def _pane(qtbot=None):
    """Built without __init__ — the pane's Qt construction is not what
    is under test, and avoiding it keeps this file headless."""
    p = MarketInspectorTopologies.__new__(MarketInspectorTopologies)
    p._dismissed = {}
    p._dismiss_store = None
    p._proposals = []
    p._render = lambda: None
    return p


class TestTheInstrumentWorks:
    def test_a_dismissal_registers_in_memory(self):
        """POSITIVE CONTROL for every persistence assertion below."""
        p = _pane()
        p.dismiss("prop-1", now=1000.0)
        assert p._dismissed["prop-1"] == pytest.approx(1000.0 + DISMISS_TTL_SECONDS)

    def test_the_ttl_really_is_24_hours(self):
        assert DISMISS_TTL_SECONDS == 24 * 60 * 60


class TestDismissalSurvivesRestart:
    def test_dismissing_writes_through_immediately(self):
        """Deferring the write to close would lose the dismissal on a
        crash — precisely when the operator least wants the card back."""
        store = _Store()
        p = _pane()
        p.set_dismiss_store(store)
        p.dismiss("prop-1", now=1000.0)
        assert store.data[DISMISS_SETTINGS_KEY]["prop-1"] == pytest.approx(
            1000.0 + DISMISS_TTL_SECONDS
        )

    def test_a_fresh_pane_reloads_the_dismissal(self):
        """THE exit-gate measurement: dismiss, 'restart', still gone."""
        store = _Store()
        first = _pane()
        first.set_dismiss_store(store)
        first.dismiss("prop-1")

        second = _pane()  # the restart
        second.set_dismiss_store(store)
        assert "prop-1" in second._dismissed
        assert second.is_dismissed("prop-1") is True

    def test_it_returns_after_the_persisted_timestamp_plus_ttl(self):
        """...and comes BACK afterwards. A dismissal that never expires
        is a different defect."""
        store = _Store()
        first = _pane()
        first.set_dismiss_store(store)
        first.dismiss("prop-1", now=1000.0)

        second = _pane()
        second.set_dismiss_store(store)
        later = 1000.0 + DISMISS_TTL_SECONDS + 1
        assert second.is_dismissed("prop-1", now=later) is False

    def test_an_entry_that_lapsed_while_closed_is_not_reimported(self):
        """Re-suppressing a lapsed dismissal would extend the 24 h
        promise across every restart, indefinitely."""
        stale = {DISMISS_SETTINGS_KEY: {"old": time.time() - 10.0}}
        p = _pane()
        p.set_dismiss_store(_Store(stale))
        assert "old" not in p._dismissed

    def test_sweeping_expired_entries_writes_through(self):
        """Otherwise the store keeps growing with dead ids forever."""
        store = _Store()
        p = _pane()
        p.set_dismiss_store(store)
        p.dismiss("prop-1", now=1000.0)
        before = store.writes
        p._sweep_dismissed(1000.0 + DISMISS_TTL_SECONDS + 1)
        assert p._dismissed == {}
        assert store.writes > before, "expiry was not persisted"


class TestItNeverTouchesTheOperatorsDisk:
    def test_no_store_means_no_persistence_and_no_error(self):
        """Default construction must behave exactly as before."""
        p = _pane()
        p.dismiss("prop-1")
        assert p._dismissed  # still suppressed in-session
        assert p._dismiss_store is None

    def test_the_pane_constructs_no_settings_manager(self):
        """The breach guard. A SettingsManager built in here resolves
        Path.home()/'.acervator' and would write the operator's real
        settings from any test that renders this pane."""
        import ast

        import src.gui.market_inspector_topologies as m

        src = Path(m.__file__).read_text(encoding="utf-8")
        called = {
            getattr(n.func, "id", "") or getattr(n.func, "attr", "")
            for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.Call)
        }
        assert "SettingsManager" not in called

    def test_a_failing_store_does_not_take_down_the_pane(self):
        """Losing a dismissal is a nuisance; losing the pane is not."""
        p = _pane()
        p.set_dismiss_store(_Boom())  # get() raises during load
        p.dismiss("prop-1")  # set() raises during write
        assert p._dismissed  # in-memory behaviour intact

    @pytest.mark.parametrize("junk", [None, [], "nope", 42])
    def test_a_malformed_persisted_value_is_ignored(self, junk):
        p = _pane()
        p.set_dismiss_store(_Store({DISMISS_SETTINGS_KEY: junk}))
        assert p._dismissed == {}

    def test_the_owner_actually_wires_a_store(self):
        """FIX-REACHES-THE-READ-PATH. Everything above verifies the pane
        CAN persist. If nothing ever calls set_dismiss_store in
        production, dismissals still evaporate on restart and every test
        in this file passes anyway.

        Asserted over the AST at both hops: main_window -> the tab, and
        the tab -> the pane.
        """
        import ast

        import src.gui.main_window as mw
        import src.gui.market_inspector as mi

        for mod, why in (
            (mw, "main_window never wires the dismiss store"),
            (mi, "the tab never forwards it to the pane"),
        ):
            src = Path(mod.__file__).read_text(encoding="utf-8")
            calls = [
                n
                for n in ast.walk(ast.parse(src))
                if isinstance(n, ast.Call)
                and getattr(n.func, "attr", "") == "set_dismiss_store"
            ]
            assert calls, why

    def test_unparseable_expiry_entries_are_skipped(self):
        p = _pane()
        p.set_dismiss_store(
            _Store(
                {
                    DISMISS_SETTINGS_KEY: {
                        "good": time.time() + 500,
                        "bad": "not-a-number",
                    }
                }
            )
        )
        assert "good" in p._dismissed and "bad" not in p._dismissed
