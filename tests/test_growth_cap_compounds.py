"""Issue #106 -- the per-Fold growth cap compounds.

THE DEFECT
==========
Four sites computed the per-cycle Growth Rate Cap as::

    self._anchor_target_balance * (max_target_growth_pct / 100.0)

``_anchor_target_balance`` is the operator's input value. It moves on
operator input, on wire income and on tranche arrival. A Fold NEVER
moves it. So the cap held one fixed dollar value for the life of the
bot, and the target's curve was ``anchor x (1 + 0.01N)`` where the
operator asked for ``target x 1.01^N``.

Operator report 2026-08-21: "the compounding rate appears to stay frozen
as a calculation based on the starting value of the bot but this should
refresh after each Fold so as to induce the appropriate curve."

Measured on the live fleet 2026-08-24, read-only: 35 of 38 bots carried
accrued growth; fleet anchor $3,501.51 had grown to $3,593.75; $13.37
sat parked in ``standing_surplus_usd`` behind the frozen number. IMU was
+27.1% and still capped each Fold at $0.50 where a compounding cap reads
$0.6353.

EVERY CHECK IS DRIVEN BOTH WAYS
===============================
Two twins are built here, and every behavioural assertion is made
against all three functions rather than against the shipping one alone.

``_frozen_cap`` is the expression this change DELETES. It is written out
because it no longer exists in the tree to import. Each test asserts
what it returns as well as what the property returns, so a revert does
not merely fail an equality -- it fails an assertion whose message names
the frozen dollar value that came back.

``_raw_target_cap`` is the tempting WRONG repair: take the percentage of
``_target_balance`` directly. It compounds, so it passes the headline
test, and it is still broken -- see ``TestTheBaseIsTheCycleOpenTarget``.
A test suite that only drove the anchor/target axis would have shipped
it.

WHAT IS NOT WIDENED
===================
MEM-249 states that fold surplus is the only mechanism that may grow the
target, bounded per event. This change moves the BASE of the bound and
nothing else. ``TestMEM249StillHolds`` is the pin on that.
"""

from __future__ import annotations

import ast
import io
import math
import re
import sys
import tokenize
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading.scrumming_bot import ScrummingBot  # noqa: E402

SB_SRC = (REPO_ROOT / "src" / "trading" / "scrumming_bot.py").read_text(
    encoding="utf-8"
)
# Every mixin carved out of the engine, for the same reason.
SCRUMMING_MIXIN_SRC = {
    _n: (REPO_ROOT / "src" / "trading" / "scrumming" / _n).read_text(encoding="utf-8")
    for _n in (
        "execution.py",
        "fold_tranches.py",
        "reconciliation.py",
        "tick_phases.py",
    )
}
BC_SRC = (REPO_ROOT / "src" / "trading" / "bot_container.py").read_text(
    encoding="utf-8"
)
MW_SRC = (REPO_ROOT / "src" / "gui" / "main_window.py").read_text(encoding="utf-8")
# Every widget carved out of the main window, so the scan below cannot go
# blind on a class that moved.
WIDGET_SRC = {
    q.name: q.read_text(encoding="utf-8")
    for q in sorted((REPO_ROOT / "src" / "gui" / "widgets").glob("*.py"))
}
# Every per-tab builder carved out of `_setup_ui`, for the same reason.
TAB_BUILDER_SRC = {
    q.name: q.read_text(encoding="utf-8")
    for q in sorted((REPO_ROOT / "src" / "gui" / "main_tabs").glob("*.py"))
}
CHART_SRC = WIDGET_SRC["trade_charts_tab.py"]


def _live_settings_source(gui_dir):
    """The Live Bot Settings dialog's whole source: the module and its
    per-tab package, concatenated in a fixed order."""
    parts = [gui_dir / "bot_live_settings.py"]
    parts += sorted((gui_dir / "live_settings").glob("*.py"))
    return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in parts)


BLS_SRC = _live_settings_source(REPO_ROOT / "src" / "gui")

# The live IMU bot, read-only from ~/.acervator/bot_state.json on
# 2026-08-24 and pinned here so the arithmetic below is the operator's
# own state rather than a fixture nobody has seen.
IMU_ANCHOR = 50.00
IMU_TARGET = 63.53
IMU_PCT = 1.0


# ── the bot, and the two twins ───────────────────────────────────────


class _Bus:
    def __init__(self) -> None:
        self.msgs: list[str] = []

    def emit(self, _ev: str, **kw) -> None:
        self.msgs.append(kw.get("message", ""))

    def text(self) -> str:
        return "\n".join(self.msgs)


class _Bot:
    """Only what the cap and the applier read."""

    cycle_growth_cap_usd = ScrummingBot.cycle_growth_cap_usd
    _apply_fold_target_growth = ScrummingBot._apply_fold_target_growth

    def __init__(
        self,
        *,
        anchor=100.0,
        target=None,
        pct=1.0,
        consumed=0.0,
        pool=0.0,
        active=True,
        qrate=1.0,
    ):
        self.bot_id = "bot-106"
        self.config = type(
            "C", (), {"max_target_growth_pct": pct, "profit_folding_active": active}
        )()
        self._bus = _Bus()
        self._quote_to_usd = qrate
        self._anchor_target_balance = anchor
        self._target_balance = anchor if target is None else target
        self._fold_cycle_cap_consumed = consumed
        self._standing_surplus_usd = pool
        self._fold_accumulator = 0.0
        self._target_grow_last_side = None
        self.stats = type("S", (), {"standing_surplus_usd": 0.0})()


def _frozen_cap(bot) -> float:
    """THE DELETED EXPRESSION. The defect, written out.

    This is not production code and cannot be imported, because this
    change removes it from every site that held it.
    """
    return bot._anchor_target_balance * (bot.config.max_target_growth_pct / 100.0)


def _raw_target_cap(bot) -> float:
    """THE TEMPTING WRONG REPAIR: the raw target, not the cycle-open one.

    It compounds across cycles, so it passes the headline test. It also
    lets the cap grow WHILE the cycle spends it, which is a per-event
    bound that expands as you consume it.
    """
    return bot._target_balance * (bot.config.max_target_growth_pct / 100.0)


# ── the headline: the cap compounds ──────────────────────────────────


class TestTheCapCompounds:
    def test_the_grown_target_carries_the_cap(self):
        """IMU, live: anchor $50.00, target $63.53, 1.0%."""
        b = _Bot(anchor=IMU_ANCHOR, target=IMU_TARGET, pct=IMU_PCT)
        assert b.cycle_growth_cap_usd == pytest.approx(0.6353), (
            "the cap is not compounding: it should be 1.0% of the grown "
            "target $63.53 = $0.6353. Getting $0.5000 back means the "
            "base returned to `_anchor_target_balance`, which no Fold "
            "ever moves -- issue #106, and the curve is linear again"
        )

    def test_DRIVEN_THE_OTHER_WAY_the_frozen_twin_stays_frozen(self):
        """Without this, the test above could pass on a broken tree.

        If ``_frozen_cap`` ever stopped returning the anchor's
        percentage, the contrast the test above draws would be against
        nothing and its green would mean nothing.
        """
        b = _Bot(anchor=IMU_ANCHOR, target=IMU_TARGET, pct=IMU_PCT)
        assert _frozen_cap(b) == pytest.approx(0.5000)
        assert _frozen_cap(b) != pytest.approx(b.cycle_growth_cap_usd), (
            "the twin and the shipping property agree on a bot with "
            "27.1% accrued growth, so one of them is not what this file "
            "says it is"
        )

    def test_the_gap_is_the_accrued_growth_times_the_rate(self):
        b = _Bot(anchor=IMU_ANCHOR, target=IMU_TARGET, pct=IMU_PCT)
        accrued = IMU_TARGET - IMU_ANCHOR
        assert b.cycle_growth_cap_usd - _frozen_cap(b) == pytest.approx(
            accrued * IMU_PCT / 100.0
        )

    def test_a_bot_that_never_compounded_is_untouched(self):
        """The no-op case. target == anchor means the base IS the anchor."""
        b = _Bot(anchor=200.0, pct=1.0)
        assert b.cycle_growth_cap_usd == pytest.approx(2.0)
        assert b.cycle_growth_cap_usd == pytest.approx(_frozen_cap(b)), (
            "this change moved a number on a bot with no accrued "
            "growth, which it has no business doing"
        )

    @pytest.mark.parametrize("pct", [0.25, 1.0, 3.0, 10.0, 100.0])
    def test_it_is_the_percentage_of_the_target_at_every_rate(self, pct):
        b = _Bot(anchor=50.0, target=63.53, pct=pct)
        assert b.cycle_growth_cap_usd == pytest.approx(63.53 * pct / 100.0)


# ── the base is the CYCLE-OPEN target ────────────────────────────────


class TestTheBaseIsTheCycleOpenTarget:
    """The half a target/anchor test cannot see.

    ``_apply_fold_target_growth`` adds the same ``_growth_applied`` to
    ``_target_balance`` and to ``_fold_cycle_cap_consumed``. So a cap
    read off the RAW target grows every time the cycle spends it, and
    the per-event bound MEM-249 states stops being a bound.
    """

    def test_the_cap_does_not_move_as_the_cycle_consumes_it(self):
        opened = _Bot(anchor=100.0, target=100.0, pct=1.0, consumed=0.0)
        cap0 = opened.cycle_growth_cap_usd
        assert cap0 == pytest.approx(1.0)
        # half a cap consumed: the applier moved BOTH fields by 0.50
        mid = _Bot(anchor=100.0, target=100.50, pct=1.0, consumed=0.50)
        assert mid.cycle_growth_cap_usd == pytest.approx(cap0), (
            "the cap moved mid-cycle. A bound that grows while it is "
            "spent is not a per-event bound -- MEM-249"
        )

    def test_DRIVEN_THE_OTHER_WAY_the_raw_target_twin_does_move(self):
        """The wrong repair, caught. This is why the base subtracts."""
        opened = _Bot(anchor=100.0, target=100.0, pct=1.0, consumed=0.0)
        mid = _Bot(anchor=100.0, target=100.50, pct=1.0, consumed=0.50)
        assert _raw_target_cap(mid) > _raw_target_cap(opened), (
            "the raw-target twin no longer expands mid-cycle, so the "
            "contrast this class exists to draw has gone"
        )
        assert _raw_target_cap(mid) == pytest.approx(1.005)

    def test_one_cycle_grows_the_target_by_exactly_the_rate(self):
        """End to end, through the real applier, in tiny bites.

        Twenty folds inside ONE cycle, each with more surplus than the
        cap. The total must be exactly 1.0% of the target the cycle
        opened at, not a penny more.
        """
        b = _Bot(anchor=100.0, target=100.0, pct=1.0)
        for _ in range(20):
            b._apply_fold_target_growth(0.10, source="TEST")
        assert b._target_balance == pytest.approx(101.0, abs=1e-9)
        assert b._fold_cycle_cap_consumed == pytest.approx(1.0, abs=1e-9)

    def test_DRIVEN_THE_OTHER_WAY_a_raw_target_base_would_overrun(self):
        """The overrun the subtraction prevents, computed exactly.

        With a raw-target base the cycle settles where
        ``c = (target0 + c) * pct``, that is ``c = target0*pct/(1-pct)``.
        At 1.0% that is $1.0101 on a $100 target: an overrun of the
        per-event bound by 1.01%.
        """
        target0, pct = 100.0, 0.01
        fixed_point = target0 * pct / (1.0 - pct)
        assert fixed_point == pytest.approx(1.0101010101, abs=1e-9)
        assert fixed_point > target0 * pct, (
            "the raw-target base no longer overruns, so the reason the "
            "shipped base subtracts the consumption has changed"
        )

    def test_a_reset_cycle_opens_at_the_new_grown_target(self):
        """The compounding itself: cycle two is bigger than cycle one."""
        b = _Bot(anchor=100.0, target=100.0, pct=1.0)
        cap1 = b.cycle_growth_cap_usd
        for _ in range(4):
            b._apply_fold_target_growth(0.50, source="TEST")
        b._fold_cycle_cap_consumed = 0.0  # the D2-b cycle reset
        cap2 = b.cycle_growth_cap_usd
        assert cap1 == pytest.approx(1.00)
        assert cap2 == pytest.approx(1.01)
        assert _frozen_cap(b) == pytest.approx(1.00), (
            "the frozen twin moved between cycles, so it is not the "
            "defect this file describes"
        )


# ── the curve ────────────────────────────────────────────────────────


class TestTheCurveIsGeometric:
    def test_twenty_seven_cycles_match_the_issue_table(self):
        """Issue #106 projects a $50.00 bot at 1% per Fold.

        27 folds: frozen $63.50, compounding $65.41.
        """
        frozen = 50.0 + 27 * 0.50
        assert frozen == pytest.approx(63.50)
        compound = 50.0
        for _ in range(27):
            b = _Bot(anchor=50.0, target=compound, pct=1.0)
            compound += b.cycle_growth_cap_usd
        assert compound == pytest.approx(50.0 * (1.01**27), abs=1e-9)
        assert round(compound, 2) == pytest.approx(65.41)

    @pytest.mark.parametrize(
        "n,frozen_expected", [(27, 63.50), (100, 100.00), (200, 150.00)]
    )
    def test_the_two_curves_at_the_issue_horizons(self, n, frozen_expected):
        assert 50.0 + n * 0.50 == pytest.approx(frozen_expected)
        t = 50.0
        for _ in range(n):
            t += _Bot(anchor=50.0, target=t, pct=1.0).cycle_growth_cap_usd
        assert t == pytest.approx(50.0 * (1.01**n), abs=1e-6)
        assert t > frozen_expected

    def test_DRIVEN_THE_OTHER_WAY_the_frozen_curve_is_linear(self):
        """A geometric assertion means nothing without the linear one."""
        t = 50.0
        for _ in range(200):
            b = _Bot(anchor=50.0, target=t, pct=1.0)
            t += _frozen_cap(b)
        assert t == pytest.approx(150.0), (
            "the frozen twin stopped being linear, so the contrast this "
            "file draws between the two curves has gone"
        )


# ── fail-closed ──────────────────────────────────────────────────────


class TestItFailsClosed:
    @pytest.mark.parametrize(
        "field,value",
        [
            ("_target_balance", float("nan")),
            ("_target_balance", float("inf")),
            ("_fold_cycle_cap_consumed", float("nan")),
            ("_fold_cycle_cap_consumed", float("-inf")),
        ],
    )
    def test_a_non_finite_field_yields_no_cap(self, field, value):
        b = _Bot(anchor=100.0, target=150.0, pct=1.0)
        setattr(b, field, value)
        assert b.cycle_growth_cap_usd == 0.0, (
            "a cap of zero is no growth, which is the safe answer. A "
            "non-zero cap taken from state nobody can read would grow "
            "the target off a number that is not a number"
        )

    def test_a_non_finite_percentage_yields_no_cap(self):
        b = _Bot(anchor=100.0, target=150.0, pct=float("nan"))
        assert b.cycle_growth_cap_usd == 0.0

    def test_an_unreadable_field_yields_no_cap(self):
        b = _Bot(anchor=100.0, target=150.0, pct=1.0)
        b._target_balance = "not a number"
        assert b.cycle_growth_cap_usd == 0.0

    @pytest.mark.parametrize("pct", [0.0, -1.0, -100.0])
    def test_a_non_positive_percentage_yields_no_cap(self, pct):
        assert _Bot(anchor=100.0, target=150.0, pct=pct).cycle_growth_cap_usd == 0.0

    def test_the_base_never_goes_negative(self):
        """Detonation and a withdrawal can leave consumption above target.

        ``_execute_detonation`` sets the target back to the anchor and
        deliberately does NOT clear ``_fold_cycle_cap_consumed``. A
        negative base would make the cap negative, and
        ``cap - consumed`` would then be wrong in the other direction.
        """
        b = _Bot(anchor=100.0, target=100.0, pct=1.0, consumed=140.0)
        assert b.cycle_growth_cap_usd == 0.0
        assert b.cycle_growth_cap_usd >= 0.0

    def test_POSITIVE_CONTROL_a_readable_bot_gets_a_cap(self):
        """Every zero above is only meaningful if a good bot is not zero."""
        assert _Bot(
            anchor=100.0, target=150.0, pct=1.0
        ).cycle_growth_cap_usd == pytest.approx(1.50)


# ── no site respells the formula ─────────────────────────────────────

_FROZEN_RE = re.compile(
    r"_anchor_target_balance\s*\*?\s*\n?\s*\*?\s*\(?\s*"
    r"[_A-Za-z0-9]*(?:cap_pct|growth_pct|max_target_growth_pct)"
)


def _code_only(src: str) -> str:
    """The file with every COMMENT and every STRING token removed.

    A line-wise ``#`` filter is not enough, and the difference is not
    academic: the property's own docstring QUOTES the deleted
    expression in order to say what it replaced, and four repaired
    comments quote it to say what they used to claim. A scanner that
    read those would report the repair as the defect.
    """
    return " ".join(
        tok.string
        for tok in tokenize.generate_tokens(io.StringIO(src).readline)
        if tok.type not in _TEXT_TOKENS
    )


# From Python 3.12 an f-string is NOT a STRING token. It arrives as
# FSTRING_START / FSTRING_MIDDLE / FSTRING_END with the interpolations
# tokenised as ordinary code between them. Every emit in
# `scrumming_bot.py` is an f-string, so a filter that named only
# `tokenize.STRING` would leave every operator-facing message in the
# "code" view and take none of them into the "literals" view -- both
# scanners below would then be measuring the opposite of what they
# claim. `getattr` because the names do not exist before 3.12.
_FSTRING_START = getattr(tokenize, "FSTRING_START", -101)
_FSTRING_MIDDLE = getattr(tokenize, "FSTRING_MIDDLE", -102)
_FSTRING_END = getattr(tokenize, "FSTRING_END", -103)
_TEXT_TOKENS = frozenset(
    (tokenize.COMMENT, tokenize.STRING, _FSTRING_START, _FSTRING_MIDDLE, _FSTRING_END)
)


def _string_literals(src: str) -> list[str]:
    """Every literal the operator can actually be shown.

    Plain strings and the literal RUNS of every f-string. The
    interpolated expressions are deliberately not included: an
    f-string's `{...}` is code, and it is the surrounding prose that
    makes a claim to the operator.
    """
    return [
        tok.string
        for tok in tokenize.generate_tokens(io.StringIO(src).readline)
        if tok.type in (tokenize.STRING, _FSTRING_MIDDLE)
    ]


class TestOneDefinitionOnly:
    def test_no_source_file_respells_the_cap(self):
        """A second spelling is how the four sites drifted apart."""
        for name, src in (
            ("scrumming_bot.py", SB_SRC),
            *sorted(SCRUMMING_MIXIN_SRC.items()),
            ("bot_container.py", BC_SRC),
            ("main_window.py", MW_SRC),
            *sorted(WIDGET_SRC.items()),
            *sorted(TAB_BUILDER_SRC.items()),
            ("bot_live_settings.py", BLS_SRC),
        ):
            hits = _FROZEN_RE.findall(_code_only(src))
            assert hits == [], (
                f"{name} still computes the growth cap from the anchor: "
                f"{hits}. That is issue #106 back in one more place"
            )

    def test_POSITIVE_CONTROL_the_scanner_finds_a_planted_one(self):
        planted = (
            "_cycle_cap_growth = self._anchor_target_balance"
            " * (_cap_pct / 100.0)" + chr(10)
        )
        assert _FROZEN_RE.findall(_code_only(planted)), (
            "the scanner cannot see the exact line this change deleted, "
            "so its zero above is a claim about the regex"
        )

    def test_POSITIVE_CONTROL_the_stripper_leaves_the_code_behind(self):
        """A stripper that removed everything would also report zero."""
        code = _code_only(SB_SRC)
        assert "_anchor_target_balance" in code, (
            "the code-only view holds no `_anchor_target_balance` at "
            "all, so the scan above ran over nothing"
        )
        assert "Growth Rate Cap" not in code, (
            "prose survived the strip, so the scan above can still be "
            "tripped by a comment"
        )

    def test_the_four_sites_all_read_the_property(self):
        reads = []
        for name, src in [("scrumming_bot.py", SB_SRC)] + sorted(
            SCRUMMING_MIXIN_SRC.items()
        ):
            reads += [
                (name, n)
                for n in ast.walk(ast.parse(src))
                if isinstance(n, ast.Attribute)
                and n.attr == "cycle_growth_cap_usd"
                and isinstance(n.value, ast.Name)
                and n.value.id == "self"
            ]
        assert len(reads) == 4, (
            f"expected exactly four `self.cycle_growth_cap_usd` reads across "
            f"the engine -- the applier, the preview, the eligibility queue "
            f"and the diagnostic -- found {len(reads)}: {[r[0] for r in reads]}"
        )

    def test_the_property_exists_and_is_a_property(self):
        assert isinstance(ScrummingBot.__dict__.get("cycle_growth_cap_usd"), property)


# ── the coupled consumers ────────────────────────────────────────────


class TestTheCoupledConsumers:
    def test_the_chart_draws_the_enforced_ceiling(self):
        """It drew ``anchor_px * (1 + cap_pct/100)`` and the bot
        enforces against ``_target_balance``. On IMU the chart said
        $50.50 where the bot enforced $64.17."""
        i = CHART_SRC.index("set_target_balance_lines")
        seg = CHART_SRC[max(0, i - 4000) : i + 400]
        assert "cycle_growth_cap_usd" in seg, (
            "the chart ceiling no longer reads the property the bot "
            "enforces with, so the drawn line and the enforced line can "
            "disagree again -- issue #106"
        )
        assert "ceiling_px = anchor_px * (1.0 + cap_pct / 100.0)" not in CHART_SRC

    def test_the_enforced_ceiling_on_the_live_IMU_numbers(self):
        b = _Bot(anchor=IMU_ANCHOR, target=IMU_TARGET, pct=IMU_PCT)
        ceiling = b._target_balance + b.cycle_growth_cap_usd
        assert round(ceiling, 2) == pytest.approx(64.17)
        drawn_before = IMU_ANCHOR * (1.0 + IMU_PCT / 100.0)
        assert round(drawn_before, 2) == pytest.approx(50.50)

    def test_get_status_exports_the_property(self):
        seg = BC_SRC[BC_SRC.index('"cycle_growth_budget_usd"') :][:300]
        assert "cycle_growth_cap_usd" in seg, (
            "the status export respells the cap again, so the GUI row "
            "and the bound can drift apart"
        )

    def test_the_over_cap_summary_uses_the_same_budget(self):
        seg = BC_SRC[BC_SRC.index("_over_cap_summary") :][:900]
        assert "cycle_growth_cap_usd" in seg

    def test_the_settings_row_reads_the_property(self):
        i = BLS_SRC.index("Cycle growth budget:")
        assert "cycle_growth_cap_usd" in BLS_SRC[max(0, i - 900) : i]

    def test_the_status_number_equals_the_enforced_number(self):
        """Not the source text -- the value."""
        b = _Bot(anchor=IMU_ANCHOR, target=IMU_TARGET, pct=IMU_PCT)
        exported = round(float(getattr(b, "cycle_growth_cap_usd", 0.0)), 8)
        assert exported == pytest.approx(b.cycle_growth_cap_usd)
        assert exported != pytest.approx(_frozen_cap(b))


# ── MEM-249 ──────────────────────────────────────────────────────────


class TestMEM249StillHolds:
    def test_only_fold_surplus_grows_the_target(self):
        """The applier must still be the only writer, still bounded."""
        b = _Bot(anchor=100.0, target=120.0, pct=1.0)
        before = b._target_balance
        assert b._apply_fold_target_growth(0.0, source="TEST") == 0.0
        assert b._target_balance == before

    def test_growth_is_still_bounded_per_event(self):
        b = _Bot(anchor=100.0, target=120.0, pct=1.0)
        applied = b._apply_fold_target_growth(999.0, source="TEST")
        assert applied == pytest.approx(1.20)
        assert b._target_balance == pytest.approx(121.20)
        assert b._standing_surplus_usd == pytest.approx(999.0 - 1.20)

    def test_the_bound_is_wider_than_it_was_and_that_is_the_change(self):
        b = _Bot(anchor=100.0, target=120.0, pct=1.0)
        assert _frozen_cap(b) == pytest.approx(1.00)
        assert b.cycle_growth_cap_usd == pytest.approx(1.20)

    def test_profit_folding_off_still_grows_nothing(self):
        b = _Bot(anchor=100.0, target=120.0, pct=1.0, active=False)
        assert b._apply_fold_target_growth(50.0, source="TEST") == 0.0
        assert b._target_balance == pytest.approx(120.0)

    def test_a_consumed_cycle_still_parks_rather_than_grows(self):
        b = _Bot(anchor=100.0, target=120.0, pct=1.0, consumed=1.20)
        assert b._apply_fold_target_growth(5.0, source="TEST") == 0.0
        assert b._standing_surplus_usd == pytest.approx(5.0)
        assert b._target_balance == pytest.approx(120.0)


# ── the emitted diagnostics tell the truth ───────────────────────────


class TestTheLogsNameTheRightBase:
    def test_the_grown_message_quotes_the_compounding_cap(self):
        b = _Bot(anchor=100.0, target=120.0, pct=1.0)
        b._apply_fold_target_growth(0.10, source="TEST")
        assert "$1.2000" in b._bus.text(), (
            f"the TARGET GROWN line does not name the compounding cap; "
            f"it said: {b._bus.text()!r}"
        )

    def test_no_emitted_string_still_says_percent_of_anchor(self):
        """STRING tokens only. A comment may still discuss the old base;
        an emit may not still assert it, because the operator reads
        emits and does not read comments."""
        bad = [s for s in _string_literals(SB_SRC) if "% of anchor" in s]
        assert bad == [], (
            f"an emit still tells the operator the cap is a percentage "
            f"of the anchor, which it is not: {bad}"
        )

    def test_POSITIVE_CONTROL_the_emit_scanner_can_see_that_phrase(self):
        planted = 'x = f"cycle_budget=$1.00 ({p}% of anchor ${a})"' + chr(10)
        assert [s for s in _string_literals(planted) if "% of anchor" in s]


# ── finiteness of the whole property, exhaustively ───────────────────


class TestTheReturnIsAlwaysUsable:
    @pytest.mark.parametrize("target", [0.0, 1e-9, 1.0, 1e6, 1e12])
    @pytest.mark.parametrize("consumed", [0.0, 0.5, 1e12])
    @pytest.mark.parametrize("pct", [0.01, 1.0, 100.0])
    def test_it_is_finite_and_non_negative(self, target, consumed, pct):
        v = _Bot(
            anchor=1.0, target=target, pct=pct, consumed=consumed
        ).cycle_growth_cap_usd
        assert math.isfinite(v)
        assert v >= 0.0
