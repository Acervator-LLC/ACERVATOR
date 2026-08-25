"""The raw-indicator prefix, and the one consumer that slices it.

WHY THIS FILE EXISTS
====================
Queue item 10.2 renamed `ta.raw.` to `ta.07.004.postcondition.raw.`.
`fleet_replay_controller` filtered the sink with a literal `"ta.raw."`
and cut the indicator out with `_r.name[7:]` -- a hardcoded offset that
happened to equal the old prefix's length. Left alone, the rename makes
that filter match nothing, and the rollup below it STILL EMITS:
`ta.07.002.invariant.invariants` with `actual=0` violations over
`indicators=0`, on every run. A passing record asserting that no
indicator ever broke its bound, produced by a filter that saw no
indicators at all -- a silent false green inside the instrument built
to catch indicator faults.

The repair was to give the prefix a name, `TA_RAW_PREFIX`, owned by the
engine that emits it, and to take the leaf by that name's own length.
This file is what keeps the pair from drifting apart again.

WHY THE PIN STILL SPELLS THE PREFIX OUT
=======================================
`tools/emitter_registry_check.py` reads each pin's name off the syntax
tree. A name assembled from a variable renders as `{}{}`, loses its
subsystem token and falls out of the register. So the literal in the
f-string is the authority and `TA_RAW_PREFIX` is its copy;
`test_the_constant_is_the_string_the_engine_emits` is the check that
the copy still matches.
"""

from __future__ import annotations

import ast
from pathlib import Path

from src.core.signal_contract import SignalSink, emit, get_sink, set_sink
from src.trading.ta_engine import TA_RAW_PREFIX

# `tests/conftest.py` puts the repository root on `sys.path` before any
# test module is imported, so these two imports need no path juggling
# above them and this file carries no suppression to excuse one.
REPO_ROOT = Path(__file__).resolve().parent.parent
CONSUMER = REPO_ROOT / "src/gui/simulator_tab/fleet/fleet_replay_controller.py"
ENGINE = REPO_ROOT / "src/trading/ta_engine.py"


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_bytes().decode("utf-8"))


def _rollup(records, prefix):
    """The filter and the leaf, over records a real sink really holds.

    `test_the_filter_reads_the_named_constant` and
    `test_the_leaf_is_taken_by_the_constants_length` pin the shape of
    these two lines in the consumer, so `prefix` is the only thing left
    that can differ between this and the code under test.

    THE SINK IS PUT BACK. `set_sink` is process-global. Leaving this
    one installed would follow the suite into every module collected
    after this file, and `ta_engine` decides whether to run its whole
    instrumentation block on `get_sink() is None` -- so a leak here
    silently changes the path later TA tests take. Measured 2026-08-15:
    without the restore, `get_sink()` still returned a SignalSink
    holding this function's records after the module finished.
    """
    sink = SignalSink()
    previous = get_sink()
    set_sink(sink)
    try:
        for name, ok in records:
            emit(
                name,
                actual={"v": 1.0},
                expected=("rule" if ok is not None else None),
                ok=ok,
            )
        per = {}
        for record in sink.records():
            if not record.name.startswith(prefix):
                continue
            indicator = record.name[len(prefix) :]
            slot = per.setdefault(indicator, {"checked": 0, "violated": 0})
            if record.ok is False:
                slot["checked"] += 1
                slot["violated"] += 1
            elif record.ok is True:
                slot["checked"] += 1
        return per
    finally:
        set_sink(previous)


NEW = [
    (TA_RAW_PREFIX + "adx", True),
    (TA_RAW_PREFIX + "adx", False),
    (TA_RAW_PREFIX + "slingshot", True),
    (TA_RAW_PREFIX + "rsi", None),
]
OLD = [
    ("ta.raw.adx", True),
    ("ta.raw.adx", False),
    ("ta.raw.slingshot", True),
    ("ta.raw.rsi", None),
]


class TestTheTwoEndsCannotDisagree:
    def test_the_constant_is_the_string_the_engine_emits(self):
        """The pin's own f-string head, read off the syntax tree."""
        heads = [
            node.values[0].value
            for node in ast.walk(_tree(ENGINE))
            if isinstance(node, ast.JoinedStr)
            and node.values
            and isinstance(node.values[0], ast.Constant)
            and isinstance(node.values[0].value, str)
            and node.values[0].value.startswith("ta.")
        ]
        assert heads == [TA_RAW_PREFIX]

    def test_the_filter_reads_the_named_constant(self):
        """A literal here is the defect this file exists to stop."""
        args = [
            node.args[0]
            for node in ast.walk(_tree(CONSUMER))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "startswith"
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "name"
            and node.args
        ]
        assert len(args) == 1
        assert isinstance(args[0], ast.Name)
        assert args[0].id == "TA_RAW_PREFIX"

    def test_the_leaf_is_taken_by_the_constants_length(self):
        """`name[7:]` was the other half of the pair. Never again."""
        lowers = [
            node.slice.lower
            for node in ast.walk(_tree(CONSUMER))
            if isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "name"
            and isinstance(node.slice, ast.Slice)
        ]
        assert len(lowers) == 1
        low = lowers[0]
        assert isinstance(low, ast.Call)
        assert isinstance(low.func, ast.Name)
        assert low.func.id == "len"
        assert len(low.args) == 1
        assert isinstance(low.args[0], ast.Name)
        assert low.args[0].id == "TA_RAW_PREFIX"

    def test_no_bare_old_prefix_survives_in_either_file(self):
        """Both files still MENTION `ta.raw.` -- each explains what the
        old prefix was. Neither may still pass it to `startswith`."""
        for path in (CONSUMER, ENGINE):
            text = path.read_bytes().decode("utf-8")
            assert 'startswith("ta.raw."' not in text
            assert "startswith('ta.raw.'" not in text


class TestTheIndicatorComesBack:
    def test_three_indicators_under_the_new_prefix(self):
        per = _rollup(NEW, TA_RAW_PREFIX)
        assert sorted(per) == ["adx", "rsi", "slingshot"]
        assert per["adx"]["violated"] == 1

    def test_the_leaf_is_the_indicator_and_nothing_else(self):
        """A wrong offset returns a truncated or over-long leaf rather
        than an empty result, which is the harder failure to notice."""
        per = _rollup([(TA_RAW_PREFIX + "kaufman_er", True)], TA_RAW_PREFIX)
        assert list(per) == ["kaufman_er"]


class TestPositiveControls:
    """A zero is a claim about the instrument until it is shown that
    the instrument can report something other than zero."""

    def test_the_old_prefix_now_recovers_nothing(self):
        """The exact false green, reproduced on demand: new records, a
        filter still looking for the old prefix, zero indicators."""
        assert _rollup(NEW, "ta.raw.") == {}

    def test_old_records_do_not_match_the_new_prefix(self):
        assert _rollup(OLD, TA_RAW_PREFIX) == {}

    def test_the_rollup_helper_can_return_empty(self):
        """If `_rollup` could never be empty the two controls above
        would pass on a broken filter."""
        assert _rollup([("something.else", True)], TA_RAW_PREFIX) == {}


class TestTheHelperLeavesNothingBehind:
    """`set_sink` is process-global, so this file's helper can change
    what every module collected after it observes."""

    def test_the_sink_is_restored_to_what_it_found(self):
        """PREDICTION, recorded beside the observation: after the call
        `get_sink()` is exactly the object that was installed before it,
        `None` included. This failed before the `finally` was added --
        the assertion below saw the helper's own SignalSink."""
        before = get_sink()
        _rollup(NEW, TA_RAW_PREFIX)
        assert get_sink() is before

    def test_it_is_restored_even_when_a_caller_had_one(self):
        """A sink already installed must survive, not be replaced by
        None -- `set_sink(None)` on the way out would be its own leak."""
        mine = SignalSink()
        set_sink(mine)
        try:
            _rollup(NEW, TA_RAW_PREFIX)
            assert get_sink() is mine
            assert mine.records() == ()
        finally:
            set_sink(None)
