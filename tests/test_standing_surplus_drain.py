"""Phase 2 Steps 6-7 — the standing pool acquires an outlet.

STEP 7, THE DRAIN
`__init__` at :488-494 has always specified it:

    per_cycle_growth_budget = anchor x (max_target_growth_pct / 100)
    this_cycle_growth = min(this_cycle_surplus + standing_surplus,
                            per_cycle_growth_budget)
    target_balance += this_cycle_growth
    standing_surplus = (this_cycle_surplus + standing_surplus)
                       - this_cycle_growth

The code implemented `min(_new_surplus_usd, _cap_remaining)` -- only THIS
fold's surplus was eligible, and anything over the cap was ADDED to the
pool. `_standing_surplus_usd` has no decrement anywhere else in src/
either, so the pool took deposits and had no withdrawal. A later cycle
with cap headroom to spare could not reach money parked yesterday.

THE SECOND HALF, which the plan called out and the first draft missed
A break-even fold returned before reaching the drain, so the pool could
only ever be released by a PROFITABLE fold. The `[COMPOUND SKIPPED]`
message immediately above that return says a break-even fold is
EXPECTED -- "when a fold buys back at cost basis or when scrum->fold
spread is eaten by fees" -- which is the common case on this platform.
The pool's only outlet was the rare case. It now skips only when there is
nothing new AND nothing parked.

STEP 6, DETONATION HYGIENE
The detonation clear bumped no counter, so a detonation silently broke
the tranche accounting. It now counts them, and zeroes the standing pool:
detonation resets the target to anchor by design, so carrying
pre-detonation surplus forward would inject growth earned against a
position that no longer exists.

DELIBERATE DEVIATION FROM THE PLAN: it counts DISCARDED, not CLOSED.
Those tranches did not fold -- detonation sells the position and abandons
the queued rebuys -- and v3.24.44 established that `closed` means
"actually folded". Counting an abandoned tranche as closed re-introduces
the conflation that split was for.

BLAST RADIUS, MEASURED
Fleet standing surplus is $1.0992 (BIO/USD $0.6289, CAP/USD $0.4703),
released at no more than anchor x max_target_growth_pct/100 per cycle.
`detonation_enabled` is FALSE on all 35 bots, so Step 6 is dormant in
practice -- verified read-only against live state, which the repair plan
had explicitly not measured.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading.scrumming_bot import ScrummingBot  # noqa: E402


class _Bus:
    def __init__(self):
        self.msgs = []

    def emit(self, _ev, **kw):
        self.msgs.append(kw.get("message", ""))

    def text(self):
        return "\n".join(self.msgs)


class _Bot:
    """Only what _apply_fold_target_growth reads."""

    _apply_fold_target_growth = ScrummingBot._apply_fold_target_growth

    def __init__(self, *, anchor=200.0, cap_pct=1.0, consumed=0.0,
                 pool=0.0, target=None):
        self.bot_id = "bot-test-0001"
        self.config = type("C", (), {
            "max_target_growth_pct": cap_pct,
            "profit_folding_active": True})()
        self._bus = _Bus()
        self._quote_to_usd = 1.0
        self._anchor_target_balance = anchor
        self._target_balance = anchor if target is None else target
        self._fold_cycle_cap_consumed = consumed
        self._standing_surplus_usd = pool
        self._fold_accumulator = 0.0
        self._target_grow_last_side = None
        self.stats = type("S", (), {"standing_surplus_usd": 0.0})()


class TestTheHelperWorks:
    def test_a_plain_surplus_grows_the_target(self):
        """POSITIVE CONTROL. If growth never applied, every drain
        assertion below would pass against a broken helper."""
        b = _Bot()
        applied = b._apply_fold_target_growth(0.50, source="TEST")
        assert applied == pytest.approx(0.50)
        assert b._target_balance == pytest.approx(200.50)


class TestTheDrain:
    def test_the_plan_fixture(self):
        """pool 5.0, cap_remaining 2.0, surplus 0.5 -> applied 2.0,
        pool 3.5. Current code gave applied 0.5 and pool unchanged."""
        b = _Bot(anchor=200.0, cap_pct=1.0, consumed=0.0, pool=5.0)
        # cap = 200 * 1% = 2.00
        applied = b._apply_fold_target_growth(0.5, source="TEST")
        assert applied == pytest.approx(2.0)
        assert b._standing_surplus_usd == pytest.approx(3.5)

    def test_the_target_moved_by_the_applied_amount(self):
        b = _Bot(anchor=200.0, pool=5.0)
        b._apply_fold_target_growth(0.5, source="TEST")
        assert b._target_balance == pytest.approx(202.0)

    def test_a_break_even_fold_still_drains_the_pool(self):
        """THE second half. Zero new surplus used to return before the
        drain, so parked money was released only by a PROFITABLE fold --
        and the code's own message says break-even is the expected
        case."""
        b = _Bot(anchor=200.0, pool=5.0)
        applied = b._apply_fold_target_growth(0.0, source="TEST")
        assert applied == pytest.approx(2.0)
        assert b._standing_surplus_usd == pytest.approx(3.0)

    def test_nothing_new_and_nothing_parked_is_still_a_skip(self):
        """NEGATIVE CONTROL: the relaxed guard must not turn every
        break-even fold into a log line and a no-op write."""
        b = _Bot(anchor=200.0, pool=0.0)
        applied = b._apply_fold_target_growth(0.0, source="TEST")
        assert applied == 0.0
        assert "COMPOUND SKIPPED" in b._bus.text()

    def test_a_small_pool_drains_fully(self):
        """The real fleet case: $0.6289 parked against a $1.00 cap."""
        b = _Bot(anchor=100.0, cap_pct=1.0, pool=0.6289)
        applied = b._apply_fold_target_growth(0.0, source="TEST")
        assert applied == pytest.approx(0.6289)
        assert b._standing_surplus_usd == pytest.approx(0.0)

    def test_the_cap_still_bounds_growth(self):
        """NEGATIVE CONTROL. The drain must not let a large pool exceed
        the per-cycle cap -- that is the whole safety property."""
        b = _Bot(anchor=100.0, cap_pct=1.0, pool=999.0)
        applied = b._apply_fold_target_growth(50.0, source="TEST")
        assert applied == pytest.approx(1.0)
        assert b._target_balance == pytest.approx(101.0)

    def test_consumed_cap_still_parks_without_draining(self):
        """With no headroom there is nothing to drain into. The parking
        branch is unchanged."""
        b = _Bot(anchor=100.0, cap_pct=1.0, consumed=1.0, pool=5.0)
        applied = b._apply_fold_target_growth(2.0, source="TEST")
        assert applied == 0.0
        assert b._standing_surplus_usd == pytest.approx(7.0)

    def test_the_log_reports_the_drain(self):
        """A growth funded from the pool used to read as though it came
        from the fold."""
        b = _Bot(anchor=200.0, pool=5.0)
        b._apply_fold_target_growth(0.5, source="TEST")
        msg = b._bus.text()
        assert "standing" in msg
        assert "drained" in msg


class TestDetonationHygiene:
    def test_the_clear_counts_discarded_not_closed(self):
        """Those tranches did not fold. `closed` means folded, which is
        what makes created - closed - discarded = standing meaningful.

        Asserted over ASSIGNED ATTRIBUTE NAMES, not source text: the
        comment recording this deviation necessarily names the counter it
        declines to use, and text matching cannot tell a mention from a
        write. This has now caught me five times in this cascade."""
        import ast

        import src.trading.scrumming_bot as sbm

        src = Path(sbm.__file__).read_text(encoding="utf-8")
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and n.name == "_execute_detonation")
        written = set()
        for node in ast.walk(fn):
            tgts = []
            if isinstance(node, ast.Assign):
                tgts = node.targets
            elif isinstance(node, ast.AugAssign):
                tgts = [node.target]
            for t in tgts:
                if isinstance(t, ast.Attribute):
                    written.add(t.attr)
        assert "_tranches_discarded_lifetime" in written
        assert "_tranches_closed_lifetime" not in written

    def test_it_zeroes_the_standing_pool(self):
        import ast

        import src.trading.scrumming_bot as sbm

        src = Path(sbm.__file__).read_text(encoding="utf-8")
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and n.name == "_execute_detonation")
        seg = ast.get_source_segment(src, fn) or ""
        assert "self._standing_surplus_usd = 0.0" in seg

    def test_it_does_NOT_clear_the_cycle_cap(self):
        """NEGATIVE CONTROL. Zeroing _fold_cycle_cap_consumed unlatches
        folds, which is a buy-TIMING change and belongs in Phase 3."""
        import ast

        import src.trading.scrumming_bot as sbm

        src = Path(sbm.__file__).read_text(encoding="utf-8")
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and n.name == "_execute_detonation")
        seg = ast.get_source_segment(src, fn) or ""
        assert "_fold_cycle_cap_consumed = 0" not in seg
