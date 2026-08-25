"""v3.23.30 Option A — set_target_balance_live preserves accrued
growth on top-up.

Pins the four semantic cases:
  1. Top-up with accrued growth   → new anchor + preserved growth
  2. Top-up with zero accrued     → same as current (both == new)
  3. Lower                         → both to new (growth reset)
  4. Equal                         → no-op (both stay put)

These are source-shape pins (AST/text) — they verify the
scrumming_bot.py implementation without needing to instantiate a
live ScrummingBot (which would drag in the whole trading engine).
Behavioural tests against a full bot instance are 2B-scope.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture(scope="module")
def source() -> str:
    return (REPO / "src" / "trading" / "scrumming_bot.py").read_text(
        encoding="utf-8", errors="replace"
    )


@pytest.fixture(scope="module")
def method_body(source: str) -> str:
    """Isolate the body of set_target_balance_live for assertions."""
    m = re.search(
        r"def set_target_balance_live\([^)]*\)[^:]*:(.*?)" r"(?=\n    def |\n\S)",
        source,
        re.DOTALL,
    )
    assert m, "could not locate set_target_balance_live body"
    return m.group(1)


class TestSourceShape:
    """AST-level pins on the new behavior."""

    def test_accrued_computed_from_old_target_minus_anchor(self, method_body):
        """accrued = max(0, old_t - old_a)."""
        assert re.search(
            r"accrued\s*=\s*max\(0\.0,\s*old_t\s*-\s*old_a\)",
            method_body,
        ), "accrued growth must be computed from old_t - old_a"

    def test_topup_branch_triggers_on_nt_greater_than_old_t_with_accrued(
        self, method_body
    ):
        """Top-up branch: nt > old_t AND accrued > threshold."""
        assert re.search(
            r"if\s+nt\s*>\s*old_t\s+and\s+accrued\s*>\s*1e-9\s*:",
            method_body,
        )

    def test_topup_preserves_growth_on_top_of_new_anchor(self, method_body):
        """Top-up: target = nt + accrued; anchor = nt."""
        # Both assignments must be present under the top-up branch
        assert "self._anchor_target_balance = nt" in method_body
        assert re.search(
            r"self\._target_balance\s*=\s*nt\s*\+\s*accrued",
            method_body,
        ), "top-up branch must set target = nt + accrued"

    def test_else_branch_lockstep_lower_or_equal(self, method_body):
        """Non-top-up branch: both = nt."""
        # The else branch should set both to nt (lockstep)
        assert re.search(
            r"else\s*:\s*\n\s*"
            r"(?:#[^\n]*\n\s*)*"
            r"self\._target_balance\s*=\s*nt\s*\n\s*"
            r"self\._anchor_target_balance\s*=\s*nt",
            method_body,
        ), "else branch must set both target and anchor to nt"

    def test_config_target_balance_gets_operator_input_value(self, method_body):
        """config.target_balance should reflect operator's INPUT (anchor),
        not the accrued-growth-included target."""
        assert re.search(
            r"self\.config\.target_balance\s*=\s*nt",
            method_body,
        )

    def test_return_dict_includes_preserved_growth_field(self, method_body):
        """Return dict must include preserved_growth for callers."""
        assert '"preserved_growth"' in method_body


class TestBehavioralSemantic:
    """Behavioral tests using a lightweight stub to exercise the method
    without instantiating a full ScrummingBot."""

    def _make_stub(self, target: float, anchor: float, holdings: float = 0.0):
        """Build minimal duck-typed stub with the fields
        set_target_balance_live reads / writes."""
        from types import SimpleNamespace

        class _Bus:
            def emit(self, *a, **kw):
                pass

        class _Cfg:
            target_balance = None

        stub = SimpleNamespace()
        stub._target_balance = target
        stub._anchor_target_balance = anchor
        stub._current_holdings = holdings
        stub.bot_id = "test-bot"
        stub._bus = _Bus()
        stub.config = _Cfg()
        stub.stats = SimpleNamespace(current_price=1.0)
        return stub

    def _call(self, stub, new_target):
        # Rebind the unbound method to the stub instance
        from src.trading.scrumming_bot import ScrummingBot

        return ScrummingBot.set_target_balance_live(stub, new_target)

    def test_topup_with_accrued_growth_preserved(self):
        """Anchor=200, target=205 (5 accrued), operator sets 250 →
        anchor=250, target=255. Preserves the $5 growth."""
        stub = self._make_stub(target=205.0, anchor=200.0)
        r = self._call(stub, 250.0)
        assert r["applied"] is True
        assert stub._anchor_target_balance == 250.0, "anchor should be new"
        assert (
            stub._target_balance == 255.0
        ), "target should preserve $5 accrued on top of new $250 anchor"
        assert r["preserved_growth"] == 5.0

    def test_topup_with_zero_accrued_equals_old_behavior(self):
        """Anchor=200, target=200 (0 accrued), operator sets 250 →
        both = 250. Same as pre-v3.23.30 behaviour."""
        stub = self._make_stub(target=200.0, anchor=200.0)
        r = self._call(stub, 250.0)
        assert stub._anchor_target_balance == 250.0
        assert stub._target_balance == 250.0
        assert r["preserved_growth"] == 0.0

    def test_lower_wipes_accrued_growth(self):
        """Anchor=200, target=210 (10 accrued), operator sets 150
        (explicit lower / withdrawal) → both = 150."""
        stub = self._make_stub(target=210.0, anchor=200.0)
        r = self._call(stub, 150.0)
        assert stub._anchor_target_balance == 150.0
        assert stub._target_balance == 150.0
        assert r["preserved_growth"] == 0.0

    def test_equal_is_no_op(self):
        """Anchor=200, target=205, operator sets 205 (equal to current
        target) → both := 205 (no-op-ish; target unchanged since it was
        already 205)."""
        stub = self._make_stub(target=205.0, anchor=200.0)
        self._call(stub, 205.0)
        # nt == old_t, so else branch fires: both = nt = 205
        # (Accrued growth is COLLAPSED — operator is explicitly
        # confirming 205 as their target so anchor moves to 205.)
        assert stub._anchor_target_balance == 205.0
        assert stub._target_balance == 205.0

    def test_config_reflects_operator_input_not_preserved_target(self):
        """config.target_balance always shows what operator SET (anchor),
        not the accrued-growth-included target — so GUI and
        persistence reflect operator intent."""
        stub = self._make_stub(target=205.0, anchor=200.0)
        self._call(stub, 250.0)
        assert stub.config.target_balance == 250.0

    def test_return_dict_has_correct_keys(self):
        stub = self._make_stub(target=205.0, anchor=200.0)
        r = self._call(stub, 250.0)
        assert set(r.keys()) >= {
            "applied",
            "old_target",
            "old_anchor",
            "new_target",
            "new_anchor",
            "delta_usd",
            "preserved_growth",
        }
        assert r["old_target"] == 205.0
        assert r["old_anchor"] == 200.0
        assert r["new_target"] == 255.0
        assert r["new_anchor"] == 250.0

    def test_invalid_input_still_refused(self):
        """Guardrails from before v3.23.30 unchanged."""
        stub = self._make_stub(target=205.0, anchor=200.0)
        r = self._call(stub, -50.0)
        assert r["applied"] is False
        # State unchanged
        assert stub._target_balance == 205.0
        assert stub._anchor_target_balance == 200.0

    def test_non_numeric_refused(self):
        stub = self._make_stub(target=205.0, anchor=200.0)
        r = self._call(stub, "not a number")
        assert r["applied"] is False
