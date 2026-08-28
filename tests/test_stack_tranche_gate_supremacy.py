"""v3.23.44 — a Stack tranche never supersedes a trading gate.

OPERATOR DIRECTIVE, 2026-08-11, verbatim:

    "Its also important to verify that tranches do not supersede any
     trading gates. They are only are 'used' when a valid trading
     condition occurs."

    "A price threshold being passed activates the tranche which allows it
     to be spent when the trading condition manifests."

Two stages, and this file pins the SECOND one's position in `tick`.
`tests/test_stack_mode_execution.py` pins what each stage DOES; here we
pin WHERE the spend happens, because that is what makes a refusal
protective. The two files together are the proof: stage one is reachable
on a refused tick and places nothing, stage two places the order and is
reachable only under an authorised gate-chain verdict.

Every check below is read at the surface it reports through -- the AST of
the shipped file -- and every one is paired with a PLANTED DEFECT that it
must be observed failing on. A structural check with no plant proves
nothing: it would report clean against a file that had never been
gated at all.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

SOURCE_PATH = REPO / "src" / "trading" / "scrumming_bot.py"

ACTIVATE = "_reconcile_stack_tranches_invisible"
SPEND = "_spend_activated_stack_tranches"
CHAIN_VERDICT = "_scrum_chain_result.should_fire"
FOLD_VERDICT = "_fold_chain_result.should_fire"

# The pre-chain returns the read phase identified, each named by its own
# guard condition rather than by a line number, so the pins survive an
# edit above them. Every one of these ends the tick: if it executes, no
# trading decision is reached at all.
#
# The guards are matched EXACTLY against an unparsed `if` test, not by
# substring. A substring match on `self._manual_fire_pending` also caught
# the read-rate throttle, whose condition merely mentions it and which
# sits ABOVE the activation call -- the check would then have reported a
# violation that is not one.
PRE_CHAIN_REFUSALS = {
    "dust band (MEM-258 delta-zero short circuit)": "not self._manual_fire_pending and "
    "abs(current_value - self._target_balance) <= _dust_band_usd",
    "manual fire pending": "self._manual_fire_pending",
    "wire-stack pending (MEM-257)": "_stack_pending > 0",
    "max-cartridge": "_cartridge_pct > 0 and self._target_balance > 0",
    "detonation harvest": "await self._tick_detonation(ticker)",
    "zero-balance acquisition": "current_value < self._target_balance * 0.01",
    "HARD circuit breaker": "self._cb_hard_tripped",
    "below scrumming interval": "below_interval and self._fold_queue_usd == 0 and "
    "(self._dist_accumulator == 0)",
    "insufficient candles for TA": "not summary",
}


# --------------------------------------------------------------------------
# The instrument
# --------------------------------------------------------------------------


def _read_source() -> str:
    return SOURCE_PATH.read_text(encoding="utf-8")


def _phase_source() -> str:
    """The module that owns the ``_tick_*`` phase methods."""
    import inspect

    from src.trading.scrumming_bot import ScrummingBot

    path = inspect.getsourcefile(ScrummingBot._tick_detonation)
    assert path is not None
    return Path(path).read_text(encoding="utf-8")


def _phase(name: str) -> ast.AST:
    """One ``_tick_*`` phase method, from the module that owns it."""
    return next(
        n
        for n in ast.walk(ast.parse(_phase_source()))
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    )


def _tick(source: str) -> ast.AsyncFunctionDef:
    tree = ast.parse(source)
    cls = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ScrummingBot"
    )
    return next(
        n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "tick"
    )


def _method(source: str, name: str) -> ast.AsyncFunctionDef:
    return next(
        n
        for n in ast.walk(ast.parse(source))
        if isinstance(n, ast.AsyncFunctionDef) and n.name == name
    )


def _span(stmts: list) -> tuple[int, int] | None:
    if not stmts:
        return None
    return (
        min(s.lineno for s in stmts),
        max(getattr(s, "end_lineno", s.lineno) for s in stmts),
    )


def _enclosing_tests(fn: ast.AST, lineno: int) -> list[str]:
    """Source of every `if` whose taken branch contains `lineno`.

    An `orelse` branch is reported as `NOT <test>` so an else-arm is never
    mistaken for the guarded arm.
    """
    found: list[tuple[int, str]] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.If):
            continue
        body = _span(node.body)
        if body and body[0] <= lineno <= body[1]:
            found.append((body[0], ast.unparse(node.test)))
        orelse = _span(node.orelse)
        if orelse and orelse[0] <= lineno <= orelse[1]:
            found.append((orelse[0], "NOT " + ast.unparse(node.test)))
    found.sort()
    return [test for _, test in found]


def _call_linenos(fn: ast.AST, attr: str) -> list[int]:
    return sorted(
        node.lineno
        for node in ast.walk(fn)
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == attr
    )


def _called_names(fn: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
        if isinstance(name, str):
            names.add(name)
    return names


def _ungated_calls(source: str, attr: str, verdict: str) -> list[int]:
    """Lines where `attr` is called inside `tick` without `verdict`
    among the conditions that had to hold to reach it."""
    tick = _tick(source)
    return [
        ln
        for ln in _call_linenos(tick, attr)
        if not any(verdict in t for t in _enclosing_tests(tick, ln))
    ]


def _refusals_that_do_not_protect(source: str) -> list[str]:
    """Named pre-chain refusals that fail to sit between the activation
    call and every spend call.

    A refusal ABOVE the activation call cannot stop a fire (it is why the
    old top-of-tick sell was defective). A refusal BELOW the spend call
    cannot stop it either. Only one that lies strictly between does.
    """
    tick = _tick(source)
    activate = _call_linenos(tick, ACTIVATE)
    spend = _call_linenos(tick, SPEND)
    if not activate or not spend:
        return [f"instrument blind: activate={activate} spend={spend}"]
    first_activate, first_spend = min(activate), min(spend)

    returns = [n.lineno for n in ast.walk(tick) if isinstance(n, ast.Return)]
    problems: list[str] = []
    for label, guard in PRE_CHAIN_REFUSALS.items():
        guarded = [r for r in returns if guard in _enclosing_tests(tick, r)]
        if not guarded:
            problems.append(f"{label}: no return found under {guard!r}")
            continue
        for r in guarded:
            if not first_activate < r < first_spend:
                problems.append(
                    f"{label}: return at :{r} is not between the activation "
                    f"call (:{first_activate}) and the spend call "
                    f"(:{first_spend})"
                )
                break
    return problems


# --------------------------------------------------------------------------
# The planted defects. Each is the exact defect its check exists to catch.
# --------------------------------------------------------------------------


def _plant_hoisted_spend(source: str) -> str:
    """THE DEFECT UNDER REPAIR: spend the tranche at the top of the tick,
    where the old code sold, instead of under the chain verdict."""
    old = (
        "            await self._reconcile_stack_tranches_invisible(\n"
        "                current_price=float(ticker.last)\n"
        "            )\n"
    )
    assert source.count(old) == 1, "plant anchor moved"
    new = (
        old + "            await self._spend_activated_stack_tranches(\n"
        "                current_price=float(ticker.last), summary=None\n"
        "            )\n"
    )
    return source.replace(old, new)


def _plant_ungated_fold_buy(source: str) -> str:
    """A fold-side buy issued outside the fold chain's verdict."""
    old = "        _delta_early = current_value - self._target_balance\n"
    assert source.count(old) == 1, "fold plant anchor moved"
    return source.replace(
        old, "        await self._execute_buy(1.0, 1.0, None)\n" + old
    )


def _plant_order_in(source: str, method_name: str) -> str:
    """An order placed from a method that is supposed to only read."""
    marker = f"    async def {method_name}(self"
    assert source.count(marker) == 1, f"{method_name} anchor moved"
    head, tail = source.split(marker, 1)
    body_start = tail.index('"""', tail.index('"""') + 3) + 3
    injected = "\n        await self.guarded_place_order(1, 2, 3, 4, 5)"
    return head + marker + tail[:body_start] + injected + tail[body_start:]


# --------------------------------------------------------------------------
# Stage two sits under the chain verdict
# --------------------------------------------------------------------------


class TestTheSpendIsGated:
    def test_every_spend_call_is_under_the_chain_verdict(self):
        """A REFUSAL BLOCKS THE FIRE. The chain refusing is expressed by
        the spend call being unreachable, which is what this asserts."""
        ungated = _ungated_calls(_read_source(), SPEND, CHAIN_VERDICT)
        assert ungated == [], (
            f"{SPEND} is called at line(s) {ungated} without "
            f"{CHAIN_VERDICT} among the conditions that had to hold. A "
            f"tranche would be spendable on a tick the chain refused."
        )

    def test_POSITIVE_CONTROL_a_hoisted_spend_is_reported_ungated(self):
        """Without this the check above is worthless: it would report
        clean on a file that had never been gated."""
        planted = _plant_hoisted_spend(_read_source())
        ungated = _ungated_calls(planted, SPEND, CHAIN_VERDICT)
        assert ungated, (
            "the walker reported a top-of-tick spend as gated. Its clean "
            "verdict on the shipped file carries no information."
        )

    def test_the_spend_call_is_reached_only_through_the_verdict(self):
        source = _read_source()
        tick = _tick(source)
        calls = _call_linenos(tick, SPEND)
        assert len(calls) == 1, f"expected one spend call site, got {calls}"
        tests = _enclosing_tests(tick, calls[0])
        assert tests == [CHAIN_VERDICT], (
            f"the spend call's enclosing conditions are {tests}, not "
            f"exactly [{CHAIN_VERDICT!r}]"
        )


class TestEveryPreChainRefusalPreventsTheFire:
    def test_each_named_refusal_sits_between_activation_and_spend(self):
        problems = _refusals_that_do_not_protect(_read_source())
        assert problems == [], "\n".join(problems)

    def test_POSITIVE_CONTROL_a_hoisted_spend_breaks_every_one(self):
        """The plant puts a spend above all nine refusals. Every one must
        be reported, or the check is reading something else."""
        problems = _refusals_that_do_not_protect(_plant_hoisted_spend(_read_source()))
        assert len(problems) == len(PRE_CHAIN_REFUSALS), (
            f"a spend hoisted above every refusal produced "
            f"{len(problems)} complaint(s), not {len(PRE_CHAIN_REFUSALS)}: "
            f"{problems}"
        )

    @pytest.mark.parametrize("label", sorted(PRE_CHAIN_REFUSALS))
    def test_the_refusal_condition_still_exists_in_tick(self, label):
        """Each guard must still be a real condition in `tick`, or the pin
        above is asserting something about a branch that is gone. Read off
        the AST, not the raw text: `ast.unparse` normalises quoting, so a
        text search misses `getattr(self.config, "detonation_enabled",
        False)` for a guard written with single quotes."""
        tests = {
            ast.unparse(n.test)
            for n in ast.walk(_tick(_read_source()))
            if isinstance(n, ast.If)
        }
        assert (
            PRE_CHAIN_REFUSALS[label] in tests
        ), f"guard for {label!r} is no longer a condition in tick()"


class TestTheDetonationRefusalStillReadsTheFlag:
    def test_the_phase_reads_the_config_flag(self):
        """The tick-level guard above is the phase CALL. Without this the
        phase could ignore the operator's switch and nothing would say so."""
        src = ast.unparse(_phase("_tick_detonation"))
        assert (
            "detonation_enabled" in src
        ), "the detonation phase no longer reads config.detonation_enabled"

    def test_the_phase_aborts_the_tick_when_it_fires(self):
        """The phase returns True and tick returns on it. A phase that
        never returns True cannot end the tick."""
        returns = [
            ast.unparse(n.value)
            for n in ast.walk(_phase("_tick_detonation"))
            if isinstance(n, ast.Return) and n.value is not None
        ]
        assert "True" in returns, returns


class TestStageOneIsDeliberatelyUngated:
    def test_the_activation_call_is_at_tick_top_level(self):
        """Stage one is NOT gated, and must not be: it runs before the
        chain's inputs exist. That is safe only because it places no
        order -- pinned in tests/test_stack_mode_execution.py."""
        source = _read_source()
        tick = _tick(source)
        calls = _call_linenos(tick, ACTIVATE)
        assert len(calls) == 1
        assert _enclosing_tests(tick, calls[0]) == [], (
            "the activation call acquired a condition. If stage one is now "
            "gated, the stickiness the operator asked for is gone."
        )

    def test_POSITIVE_CONTROL_the_same_walker_reports_a_gated_call(self):
        """An empty result must mean 'no conditions', not 'walker blind'.
        The same walker, same file, on the gated fold buy."""
        fold = _phase("_tick_execute_fold")
        gated = [
            ln
            for ln in _call_linenos(fold, "_execute_buy")
            if _enclosing_tests(fold, ln)
        ]
        assert gated, (
            "the walker found no conditions on any _execute_buy call in "
            "the fold phase, so its empty verdict on the activation call "
            "is void"
        )

    def test_activation_places_nothing(self):
        called = _called_names(_method(_read_source(), ACTIVATE))
        for forbidden in (
            "_execute_sell",
            "_execute_buy",
            "guarded_place_order",
            "place_order",
            "create_order",
        ):
            assert forbidden not in called, (
                f"stage one calls {forbidden!r} -- it would sell on ticks "
                f"the bot refused to trade on"
            )


# --------------------------------------------------------------------------
# What this change must NOT have touched
# --------------------------------------------------------------------------


class TestFoldSideGatingUnchanged:
    def test_no_execute_buy_in_tick_is_unconditional(self):
        source = _read_source()
        tick = _tick(source)
        ungated = [
            ln
            for ln in _call_linenos(tick, "_execute_buy")
            if not _enclosing_tests(tick, ln)
        ]
        assert ungated == [], f"unconditional _execute_buy at {ungated}"

    def test_the_fold_buy_is_under_the_fold_chain_verdict(self):
        """The buy sits inside the fold phase, so the verdict gates the
        phase CALL. Both halves are asserted: the phase buys, and every
        call to it is under the verdict."""
        source = _read_source()
        assert _call_linenos(_phase("_tick_execute_fold"), "_execute_buy"), (
            "the fold phase no longer calls _execute_buy; this pin is "
            "reading the wrong method"
        )
        ungated = _ungated_calls(source, "_tick_execute_fold", FOLD_VERDICT)
        total = len(_call_linenos(_tick(source), "_tick_execute_fold"))
        assert total > 0, "tick no longer runs the fold phase at all"
        assert ungated == [], (
            f"the fold phase is called at line(s) {ungated} without "
            f"{FOLD_VERDICT} among the conditions that had to hold"
        )

    def test_POSITIVE_CONTROL_an_unconditional_fold_buy_is_caught(self):
        planted = _plant_ungated_fold_buy(_read_source())
        tick = _tick(planted)
        ungated = [
            ln
            for ln in _call_linenos(tick, "_execute_buy")
            if not _enclosing_tests(tick, ln)
        ]
        assert ungated, "a buy planted at tick top level was reported as gated"


class TestVisibleModeUnchanged:
    def test_the_visible_reconciler_only_reads(self):
        """Visible mode's gates are evaluated once, at placement time,
        which is ordinary limit-order semantics. Its reconciler must stay
        a reader: the EXCHANGE fills the resting order, not the bot."""
        called = _called_names(
            _method(_read_source(), "_reconcile_stack_tranches_visible")
        )
        for forbidden in (
            "_execute_sell",
            "_execute_buy",
            "guarded_place_order",
            "place_order",
            "create_order",
        ):
            assert (
                forbidden not in called
            ), f"the Visible reconciler calls {forbidden!r}"
        assert {"get_open_orders", "get_order"} <= called, (
            "positive control: the Visible reconciler no longer reads "
            "exchange state at all, so its silence proves nothing"
        )

    def test_POSITIVE_CONTROL_a_planted_order_is_caught(self):
        planted = _plant_order_in(_read_source(), "_reconcile_stack_tranches_visible")
        called = _called_names(_method(planted, "_reconcile_stack_tranches_visible"))
        assert "guarded_place_order" in called, (
            "the call scanner missed an order planted in the Visible " "reconciler"
        )

    def test_visible_placement_is_still_inside_the_visible_branch(self):
        source = _read_source()
        fn = _method(source, "_open_stack_from_scrum")
        placements = _call_linenos(fn, "guarded_place_order")
        assert placements, "Visible mode no longer places anything"
        for ln in placements:
            assert any("_visible" in t for t in _enclosing_tests(fn, ln)), (
                f"guarded_place_order at :{ln} escaped the `if _visible:` "
                f"branch -- Invisible mode would place resting orders"
            )
