"""v3.23.30 Option A — set_target_balance_live preserves accrued
growth on top-up. v3.25.9 — the comparison reads the ANCHOR.

Pins the semantic cases:
  1. Top-up above the anchor       → new anchor + preserved growth
  2. Top-up with zero accrued      → same as before (both == new)
  3. Lower than the anchor         → both to new (growth reset)
  4. Equal to the anchor           → no-op (both to new)

WHAT v3.25.9 CORRECTED
`new_target` reaches this method from the Target Balance spinbox,
which shows `cfg.target_balance` and is deliberately NOT repointed at
the grown runtime value — see the hazard note at
`bot_live_settings.py:3736` and the pins in
`tests/test_compounding_surface_is_visible.py`. The spinbox is
therefore ANCHOR-denominated. The branch nevertheless compared it
against the GROWN `_target_balance`, so any top-up smaller than the
accrued growth fell into the collapse branch.

Live bot IMU on 2026-08-21 carried anchor $50.00, target $63.5297,
$13.5297 accrued. The spinbox showed $50.00. An operator raising it to
$60 to add $10 of capital tested `60 > 63.5297`, took the else branch,
and set BOTH to $60 — destroying the $13.5297 AND lowering the target
below where it already stood. The position then sat above target, the
Delta flipped positive, and the bot folded the excess. Reachable on 35
of the 38 live bots.

`_without_the_anchor_reference` below restates that defective branch so
the falsifier survives as a record rather than being deleted. The
`TestTheIMUTopUpDefect` class carries the positive controls. Reverting
the one token `old_a` -> `old_t` was measured, not assumed: 14 tests in
this file fail, 10 of them in that class. The other 3 in the class are
regression pins on arms the repair does not touch, and they are
expected to hold either way.

Most of these are source-shape pins (AST/text) — they verify the
scrumming_bot.py implementation without needing to instantiate a
live ScrummingBot (which would drag in the whole trading engine).
Behavioural cases run the real method against a duck-typed stub.
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
        encoding="utf-8", errors="replace")


@pytest.fixture(scope="module")
def method_body(source: str) -> str:
    """Isolate the body of set_target_balance_live for assertions."""
    m = re.search(
        r"def set_target_balance_live\([^)]*\)[^:]*:(.*?)"
        r"(?=\n    def |\n\S)",
        source, re.DOTALL,
    )
    assert m, "could not locate set_target_balance_live body"
    return m.group(1)


# ---------------------------------------------------------------------
# The falsifier, kept as a record.
# ---------------------------------------------------------------------

def _without_the_anchor_reference(stub, new_target):
    """Restore the branch as it stood before the v3.25.9 repair.

    The only difference from the live method is the reference the
    comparison reads: `old_t` (the GROWN target) instead of `old_a`
    (the anchor the spinbox actually displays). Everything else --
    `accrued`, both assignments in each arm, the config write -- is
    identical, so any divergence in an assertion is attributable to the
    reference alone.

    The two guards below make this a real falsifier rather than a
    hand-written story. They read the live source and assert that the
    anchor form is present and the grown-target form is gone. A
    re-implementation that quietly drifts away from the code it claims
    to be the "before" of proves nothing.
    """
    src = (REPO / "src" / "trading" / "scrumming_bot.py").read_text(
        encoding="utf-8", errors="replace")
    assert "if nt > old_a and accrued > 1e-9:" in src, (
        "live source no longer carries the anchor reference; this "
        "falsifier is describing a tree that does not exist")
    assert "if nt > old_t and accrued > 1e-9:" not in src, (
        "live source carries the pre-v3.25.9 grown-target reference")

    nt = float(new_target)
    old_t = float(stub._target_balance)
    old_a = float(getattr(stub, "_anchor_target_balance", old_t))
    accrued = max(0.0, old_t - old_a)
    if nt > old_t and accrued > 1e-9:      # <-- the defect
        stub._anchor_target_balance = nt
        stub._target_balance = nt + accrued
    else:
        stub._target_balance = nt
        stub._anchor_target_balance = nt
    stub.config.target_balance = nt
    return {"new_target": stub._target_balance,
            "new_anchor": stub._anchor_target_balance,
            "preserved_growth": max(
                0.0, stub._target_balance - stub._anchor_target_balance)}


class TestSourceShape:
    """AST-level pins on the new behavior."""

    def test_accrued_computed_from_old_target_minus_anchor(self, method_body):
        """accrued = max(0, old_t - old_a)."""
        assert re.search(
            r"accrued\s*=\s*max\(0\.0,\s*old_t\s*-\s*old_a\)",
            method_body,
        ), "accrued growth must be computed from old_t - old_a"

    def test_topup_branch_triggers_on_nt_greater_than_old_a_with_accrued(
            self, method_body):
        """Top-up branch: nt > old_a AND accrued > threshold.

        v3.25.9. `nt` comes from an anchor-denominated spinbox, so the
        anchor is the only frame it can be compared in.
        """
        assert re.search(
            r"if\s+nt\s*>\s*old_a\s+and\s+accrued\s*>\s*1e-9\s*:",
            method_body,
        )

    def test_the_branch_no_longer_reads_the_grown_target(self, method_body):
        """RESTATED from the v3.23.30 pin, which asserted `nt > old_t`.

        That pin recorded the defect rather than the intent: `old_t` is
        the GROWN value and `nt` is anchor-denominated, so the two were
        never in the same frame. The assertion is inverted here so the
        original shape can never come back silently. See
        `_without_the_anchor_reference` for what it used to do.
        """
        assert not re.search(
            r"if\s+nt\s*>\s*old_t\s+and\s+accrued\s*>\s*1e-9\s*:",
            method_body,
        ), ("the top-up branch is comparing an anchor-denominated input "
            "against the grown target again - this is the v3.25.9 defect")

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
            """Records emissions instead of discarding them.

            The body was `pass`, which left `emit`, `*a` and `**kw`
            unreferenced and drew three high dead-code findings from
            the coding archetype. Recording the call clears all three
            and buys a real assertion surface: the top-up branch's
            `bot.log` line is the only place the operator ever sees
            that accrued growth survived, so
            `test_the_log_line_reports_the_preserved_growth` reads it
            back.
            """

            def __init__(self):
                self.calls: list = []

            def emit(self, *a, **kw):
                self.calls.append((a, kw))

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
        assert stub._target_balance == 255.0, (
            "target should preserve $5 accrued on top of new $250 anchor")
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

    def test_equal_to_the_anchor_is_the_no_op_path(self):
        """Anchor=200, target=205, operator sets 200 (equal to the
        ANCHOR, which is what the spinbox displays) → both := 200.

        v3.25.9 moved the no-op boundary from the grown target to the
        anchor, because the anchor is what the operator sees. The
        change-detector should skip this edit entirely; the else branch
        guards it for robustness. Values are unchanged from v3.23.30 —
        the old code also took the else branch here (200 > 205 is
        False), so this case is a regression pin, not new behaviour.
        """
        stub = self._make_stub(target=205.0, anchor=200.0)
        self._call(stub, 200.0)
        assert stub._anchor_target_balance == 200.0
        assert stub._target_balance == 200.0

    def test_equal_to_the_grown_target_is_now_a_top_up(self):
        """RESTATED from v3.23.30's `test_equal_is_no_op`.

        That test set 205 against anchor=200 / target=205 and asserted
        both collapsed to 205, calling it a no-op. It is not a no-op:
        205 is $5 ABOVE the anchor the operator was shown, so the edit
        is a $5 top-up, and collapsing both destroyed the $5 accrued.
        The old expectation is preserved as a record in
        `test_without_the_anchor_reference_the_same_edit_collapsed`.
        """
        stub = self._make_stub(target=205.0, anchor=200.0)
        r = self._call(stub, 205.0)
        assert stub._anchor_target_balance == 205.0
        assert stub._target_balance == 210.0
        assert r["preserved_growth"] == 5.0

    def test_without_the_anchor_reference_the_same_edit_collapsed(self):
        """The v3.23.30 expectation, kept as a record of the defect.

        Run against `_without_the_anchor_reference`, not against the
        live method. If this ever passes against the live method the
        fix has been reverted.
        """
        stub = self._make_stub(target=205.0, anchor=200.0)
        _without_the_anchor_reference(stub, 205.0)
        assert stub._anchor_target_balance == 205.0
        assert stub._target_balance == 205.0, (
            "pre-v3.25.9 branch collapsed the $5 accrued growth")

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
            "applied", "old_target", "old_anchor", "new_target",
            "new_anchor", "delta_usd", "preserved_growth",
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


class TestTheIMUTopUpDefect:
    """Positive controls, on the numbers the live fleet carried.

    From `~/.acervator/bot_state.json` saved 2026-08-21 23:34:27, bot
    IMU held `config.target_balance` $50.00, `anchor_target_balance`
    $50.00 and `target_balance` $63.5297 -- $13.5297 accrued. The
    spinbox showed $50.00. 35 of the 38 bots carried non-zero accrual;
    IMU was the largest, CAP the smallest still exposed at $5.4148.

    Every case below fails if the `old_a` reference is reverted to
    `old_t`, except the three marked as regression pins, which are
    unchanged by the repair and are here to prove it did not spill.
    """

    IMU_ANCHOR = 50.0
    IMU_TARGET = 63.5297
    IMU_ACCRUED = 13.5297

    def _imu(self):
        return TestBehavioralSemantic()._make_stub(
            target=self.IMU_TARGET, anchor=self.IMU_ANCHOR)

    def _call(self, stub, nt):
        return TestBehavioralSemantic()._call(stub, nt)

    def test_topup_above_anchor_below_grown_target_preserves_growth(self):
        """BEHAVIOUR 1. The reported case. Anchor 50, target 63.5297,
        operator raises the displayed 50 to 60 -> anchor 60,
        target 73.5297. The $10 lands and the $13.5297 survives."""
        stub = self._imu()
        r = self._call(stub, 60.0)
        assert r["applied"] is True
        assert stub._anchor_target_balance == pytest.approx(60.0)
        assert stub._target_balance == pytest.approx(73.5297)
        assert r["preserved_growth"] == pytest.approx(self.IMU_ACCRUED)
        assert stub._target_balance > self.IMU_TARGET, (
            "a top-up must never lower the traded target")

    def test_a_larger_topup_above_the_grown_target_still_works(self):
        """BEHAVIOUR 2. Anchor 50, target 63.5297, operator sets 75 ->
        anchor 75, target 88.5297. This case already worked before the
        repair (75 > 63.5297); it is pinned to prove the reference
        change did not break the arm that was healthy."""
        stub = self._imu()
        r = self._call(stub, 75.0)
        assert stub._anchor_target_balance == pytest.approx(75.0)
        assert stub._target_balance == pytest.approx(88.5297)
        assert r["preserved_growth"] == pytest.approx(self.IMU_ACCRUED)

    def test_a_genuine_withdrawal_below_the_anchor_still_clears_growth(self):
        """BEHAVIOUR 3. Anchor 50, target 63.5297, operator sets 40 ->
        both 40. Existing design, deliberately kept: growth cannot
        accrue above a base the operator has just lowered. Regression
        pin -- unchanged by the repair."""
        stub = self._imu()
        r = self._call(stub, 40.0)
        assert stub._anchor_target_balance == pytest.approx(40.0)
        assert stub._target_balance == pytest.approx(40.0)
        assert r["preserved_growth"] == 0.0

    def test_a_zero_accrued_bot_behaves_exactly_as_before(self):
        """BEHAVIOUR 4. LTC / LSETH / WLFI carried anchor == target ==
        25.00 with zero accrual. A top-up on those must move both in
        lockstep, as it always did. Regression pin -- unchanged by the
        repair."""
        stub = TestBehavioralSemantic()._make_stub(target=25.0, anchor=25.0)
        r = self._call(stub, 40.0)
        assert stub._anchor_target_balance == pytest.approx(40.0)
        assert stub._target_balance == pytest.approx(40.0)
        assert r["preserved_growth"] == 0.0

    def test_the_log_line_reports_the_preserved_growth(self):
        """The operator-visible surface for the repair.

        `emit` is asserted callable first. A recorder that has been
        renamed away would collect nothing and every assertion below
        would pass vacuously, which is the failure mode this ordering
        exists to stop.
        """
        stub = self._imu()
        assert callable(stub._bus.emit)
        self._call(stub, 60.0)
        msgs = [kw.get("message", "") for _a, kw in stub._bus.calls]
        assert msgs, "the method emitted nothing"
        joined = " ".join(msgs)
        assert "TARGET BALANCE LIVE UPDATE" in joined
        assert "top-up preserved" in joined, (
            "the preserved-growth note is missing; the operator has no "
            "way to see the repair worked")
        assert "13.5297" in joined
        assert "73.5297" in joined

    def test_the_config_value_still_carries_the_operator_input(self):
        """The contract the GUI and persistence depend on: whatever the
        branch does to the runtime pair, `config.target_balance` is the
        number the operator typed. Repointing it would make the spinbox
        show the grown value and re-fire this method on every panel
        open -- the hazard pinned in
        tests/test_compounding_surface_is_visible.py."""
        stub = self._imu()
        self._call(stub, 60.0)
        assert stub.config.target_balance == pytest.approx(60.0)
        assert stub._target_balance != stub.config.target_balance

    def test_without_the_anchor_reference_the_topup_destroyed_the_growth(
            self):
        """The defect, restated as a record.

        The pre-v3.25.9 branch on the same edit: `60 > 63.5297` is
        False, the else arm fires, both collapse to 60. $13.5297
        destroyed and the traded target FALLS from 63.5297 to 60 --
        which is what put the position above target, flipped the Delta
        positive and made the bot fold the excess."""
        stub = self._imu()
        r = _without_the_anchor_reference(stub, 60.0)
        assert stub._anchor_target_balance == pytest.approx(60.0)
        assert stub._target_balance == pytest.approx(60.0)
        assert r["preserved_growth"] == 0.0
        assert stub._target_balance < self.IMU_TARGET, (
            "the pre-repair branch lowered the traded target")

    @pytest.mark.parametrize("asset,anchor,target", [
        ("IMU",   50.0,  63.5297),
        ("CHIP", 250.0, 258.6812),
        ("BILL", 300.0, 307.6543),
        ("ALLO", 125.0, 132.4392),
        ("BICO",  50.0,  55.9479),
        ("CAP",   50.0,  55.4148),
    ])
    def test_every_exposed_live_bot_now_survives_a_small_topup(
            self, asset, anchor, target):
        """The blast radius, measured rather than assumed. These six
        carried more than $5 of accrued growth on 2026-08-21. A $1
        top-up -- the smallest edit the two-decimal spinbox makes
        meaningful -- fell into the collapse branch on every one of
        them, because $1 is below their accrual. All six now keep it."""
        accrued = target - anchor
        stub = TestBehavioralSemantic()._make_stub(
            target=target, anchor=anchor)
        self._call(stub, anchor + 1.0)
        assert stub._anchor_target_balance == pytest.approx(anchor + 1.0)
        assert stub._target_balance == pytest.approx(
            anchor + 1.0 + accrued), f"{asset} lost its accrued growth"

        control = TestBehavioralSemantic()._make_stub(
            target=target, anchor=anchor)
        _without_the_anchor_reference(control, anchor + 1.0)
        assert control._target_balance == pytest.approx(anchor + 1.0), (
            f"{asset} control: the pre-repair branch should collapse")
        assert control._target_balance < target
