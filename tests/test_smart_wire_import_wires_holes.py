"""Two holes in one restore loop, both closed 2026-08-15.

HOLE 1 - THE EXCEPT TUPLE WAS TOO NARROW. `import_wires` coerced the
saved pct with `float(w.get("pct", 0))` under
`except (TypeError, ValueError)`. float() has a third failure mode
neither covers: OverflowError, on an integer too large for a double.
`json.loads` parses integer literals at arbitrary precision, so a bare
309-to-4300-digit integer in a corrupt, truncated or hand-edited save
reached that line and raised.

The escape cost the WHOLE restore, not the row. It left `_wires`
partially applied, ran neither the per-row DROPPED line nor the
reconciling headline (both live after the loop), and never reached the
emitter - so topology.09.002 produced NO RECORD AT ALL.
`BotManager.restore_smart_wires_from_state` then caught it, returned 0,
and thereby skipped the ledger import AND the `wire.created` re-emit.
Measured on the operator's own 33-row topology: one planted row
destroyed 33 wires and 50 ledgers, and wrote one line that named none of
them.

HOLE 2 - nan PASSED THE RANGE GUARD AND WAS COUNTED AS A SUCCESS. nan is
unordered, so `nan <= 0` and `nan > 100` are both False and a nan pct
satisfied every clause. It was stored, counted as imported, reported as
a clean restore, and then computed `share = profit * nan / 100 = nan` in
`distribute_fold_profit`, which booked it as a COMPLETED transfer. The
dust floor could not stop it either, because `nan < min_wire` is False.
It was the one bad shape that was broken AND silent AND counted as a
success; every other one was at least refused and named.

BOTH HOLES EXISTED AT BOTH WRITERS INTO `_wires`. `register_wire` is the
other one, and it is where a NaN-bearing save comes from: it accepted
nan, `export_wires` wrote it, and `json.dumps` emitted a bare `NaN`
token. It also carried the identical narrow tuple, so
`register_wire("a", "b", int("9" * 400))` RAISED out of a method whose
whole documented contract is to return {"applied": ..., "reason": ...}.
That third defect was found by this unit's own control, not by the work
order, and is closed here with the other two.

EACH TEST STATES WHAT ITS OWN FAILURE WOULD MEAN. The first class is a
positive control: if log or emit capture goes blind, every later
assertion here is vacuous rather than passing.
"""

from __future__ import annotations

import json
import logging
import math
import re
import sys

import pytest

# NO sys.path BLOCK AND NO E402 SUPPRESSION. tests/conftest.py inserts
# the repo root at conftest import time, which pytest runs before any
# test module loads. This file carries zero forbidden directives.
from src.core.signal_contract import SignalSink, set_sink
from src.trading import smart_wire as smart_wire_module
from src.trading.smart_wire import SmartWireManager

LOGGER_NAME = "acervator.smart_wire"
PIN = "topology.09.002.postcondition.wires_received"

HEADLINE = re.compile(
    r"import accepted (\d+) of (\d+) wire row\(s\) offered; "
    r"(\d+) lost \((\d+) not a row, (\d+) had an unreadable pct, "
    r"(\d+) had no endpoint or a pct outside 0-100\)"
)

# 400 digits: comfortably inside the reachable window measured below.
WIDE_INT = int("9" * 400)
GOOD = {"source_id": "A", "target_id": "B", "pct": 25.0}


# --------------------------------------------------------------------- #
# helpers                                                               #
# --------------------------------------------------------------------- #
def _warnings(records) -> list[str]:
    return [
        r.getMessage()
        for r in records
        if r.name == LOGGER_NAME and r.levelno >= logging.WARNING
    ]


def _infos(records) -> list[str]:
    return [
        r.getMessage()
        for r in records
        if r.name == LOGGER_NAME and r.levelno == logging.INFO
    ]


def _dropped(records) -> list[str]:
    return [w for w in _warnings(records) if "DROPPED" in w]


def _heads(records) -> list[re.Match[str]]:
    return [m for m in (HEADLINE.search(w) for w in _warnings(records)) if m]


def _accepted(mgr: SmartWireManager) -> dict:
    """The accepted topology, read through the public snapshot API."""
    out: dict[str, dict[str, float]] = {}
    for row in mgr.export_wires():
        out.setdefault(row["source_id"], {})[row["target_id"]] = row["pct"]
    return out


def _has_nan(mgr: SmartWireManager) -> bool:
    """True if any stored pct is a nan, read through the public API."""
    return any(
        isinstance(row["pct"], float) and math.isnan(row["pct"])
        for row in mgr.export_wires()
    )


def _boom(message: str):
    """A logger stand-in that raises instead of logging.

    Not a lambda: a lambda's `*a, **k` are unused variables the coding
    archetype reports, and consuming them here also puts the call shape
    into the message, so a red says WHICH log call was reached.
    """

    def raise_it(*args, **kwargs):
        raise RuntimeError(
            f"{message} (reached with {len(args)} positional and "
            f"{len(kwargs)} keyword arguments)"
        )

    return raise_it


class _Unprintable:
    """A source_id whose str() raises, ON THE STORE LINE.

    The store is `self._wires.setdefault(str(src), {})[str(tgt)] = pct`,
    which sits AFTER the guarded region. This plant proves the widened
    except does not reach it.
    """

    def __str__(self):
        raise RuntimeError("PLANTED store-line failure")


class _Hostile:
    """A pct whose float() raises, INSIDE the guarded region."""

    def __float__(self):
        raise RuntimeError("PLANTED coercion failure")


class _Target:
    """A bot stand-in on the REAL apply_wire_income signature.

    smart_wire.py calls `apply_wire_income(share, source=..., ref=...)`.
    A stand-in with the wrong keyword makes the route raise and be
    booked applied=False, which would let a nan share pass for entirely
    the wrong reason. It did, on the first run of the probe this test
    came from, and that is why the signature is stated here.
    """

    def __init__(self):
        self.got = []
        self.calls = []

    def apply_wire_income(self, amount, source, ref=""):
        """Accept anything, so the guard under test is the only one."""
        self.got.append(amount)
        self.calls.append((source, ref))
        return {"applied": True, "amount": amount}


@pytest.fixture
def wirelog(capture_log):
    """Records from acervator.smart_wire, bypassing propagation.

    NOT `caplog`. `logging_engine` sets
    `logging.getLogger("acervator").propagate = False`, so records never
    reach the root handler pytest installs and caplog sees nothing once
    any earlier test has built the engine - an oracle false negative
    that depends purely on collection order.
    """
    with capture_log(LOGGER_NAME, logging.DEBUG) as records:
        yield records


@pytest.fixture
def sink():
    signal_sink = SignalSink(flush_every=10_000)
    set_sink(signal_sink)
    yield signal_sink
    set_sink(None)


# --------------------------------------------------------------------- #
# POSITIVE CONTROLS — run these first or nothing below means anything    #
# --------------------------------------------------------------------- #
class TestTheInstrumentSees:
    """FAILURE MEANS: the instrument is blind and every assertion in
    this file is vacuous rather than passing. A silence assertion read
    through a dead capture is the cheapest false green there is."""

    def test_log_capture_sees_the_clean_info_line(self, wirelog):
        SmartWireManager().import_wires([dict(GOOD)])
        assert _infos(wirelog), "no INFO captured on a clean import; capture is blind"

    def test_log_capture_sees_a_dropped_line(self, wirelog):
        SmartWireManager().import_wires(["not-a-dict"])
        assert _dropped(wirelog), (
            "no DROPPED line captured on a total-loss import; every "
            "'is named' assertion below is worthless"
        )

    def test_emit_capture_sees_the_pin(self, sink):
        SmartWireManager().import_wires([dict(GOOD)])
        assert sink.count(PIN) == 1, (
            "the pin did not reach the sink; the emitter assertions "
            "cannot tell 'correct' from 'never fired'"
        )


# --------------------------------------------------------------------- #
# HOLE 1 — the narrow except tuple                                       #
# --------------------------------------------------------------------- #
class TestHoleOneTheWideIntegerNoLongerAbortsTheImport:
    """FAILURE MEANS: one corrupt pct in a saved topology still takes
    the whole restore with it. Every wire, every ledger and every
    wire.created re-emit vanish for the session, the operator's fold
    profit stops being divided, and the only trace is one line that
    names no bot."""

    def test_overflow_error_is_outside_the_old_tuple(self):
        """The mechanism itself, so a later reader need not re-derive
        it. FAILURE MEANS: the premise of this whole class is wrong."""
        assert not issubclass(OverflowError, (TypeError, ValueError))
        assert issubclass(OverflowError, ArithmeticError)
        with pytest.raises(OverflowError):
            float(WIDE_INT)

    def test_json_delivers_the_bare_integer_intact(self):
        """FAILURE MEANS: this input shape cannot actually arrive, and
        the repair is defending against something imaginary."""
        payload = json.dumps([{"source_id": "A", "target_id": "B", "pct": WIDE_INT}])
        assert "e+" not in payload, "json must not float-ify it"
        assert json.loads(payload)[0]["pct"] == WIDE_INT

    def test_the_import_returns_instead_of_raising(self, wirelog):
        rows = [
            dict(GOOD),
            {"source_id": "C", "target_id": "D", "pct": WIDE_INT},
            {"source_id": "E", "target_id": "F", "pct": 40.0},
        ]
        mgr = SmartWireManager()
        assert mgr.import_wires(json.loads(json.dumps(rows))) == 2
        assert mgr.get_outgoing_wires("A") == {"B": 25.0}
        assert mgr.get_outgoing_wires("E") == {"F": 40.0}, (
            "the row AFTER the bad one must still be imported; before "
            "the repair the raise abandoned it"
        )
        assert mgr.get_outgoing_wires("C") == {}

    def test_the_lost_row_is_counted_and_named(self, wirelog):
        rows = [
            dict(GOOD),
            {"source_id": "C", "target_id": "D", "pct": WIDE_INT},
            {"source_id": "E", "target_id": "F", "pct": 40.0},
        ]
        SmartWireManager().import_wires(json.loads(json.dumps(rows)))
        dropped = _dropped(wirelog)
        assert len(dropped) == 1, "exactly one per-row line"
        assert "row 2 of 3" in dropped[0]
        assert "C" in dropped[0] and "D" in dropped[0]
        assert "OverflowError" in dropped[0], (
            "a widened except that does not name what it caught is the "
            "silent-swallow defect this file exists to remove"
        )
        assert "the save is corrupt" in dropped[0]

    def test_the_message_no_longer_claims_it_is_not_a_number(self, wirelog):
        """RESTATED CONTRACT. The old wording was 'pct is %r, which is
        not a number'. FAILURE MEANS: the log tells the operator
        something false - a 400-digit integer IS a number, it simply has
        no double to land on - and sends him after the wrong defect."""
        SmartWireManager().import_wires(
            [{"source_id": "C", "target_id": "D", "pct": WIDE_INT}]
        )
        line = _dropped(wirelog)[0]
        assert "which is not a number" not in line
        assert "float() refused" in line

    def test_the_headline_reconciles_and_blames_unreadable(self, wirelog):
        rows = [
            dict(GOOD),
            {"source_id": "C", "target_id": "D", "pct": WIDE_INT},
            {"source_id": "E", "target_id": "F", "pct": 40.0},
        ]
        SmartWireManager().import_wires(json.loads(json.dumps(rows)))
        heads = _heads(wirelog)
        assert len(heads) == 1
        assert tuple(int(g) for g in heads[0].groups()) == (2, 3, 1, 0, 1, 0)

    def test_the_digit_boundary_is_swept_not_asserted(self, wirelog):
        """A THRESHOLD IS NOT CLOSED BY A HAND-WRITTEN ROW. An all-nines
        integer pct crosses THREE regimes as it grows, and the sweep
        finds the widths rather than assuming them:

          1-2 digits   9 and 99 are valid percentages: ACCEPTED
          3-308 digits representable, and simply exceeds 100: UNROUTABLE
          309+ digits  no double to land on: UNREADABLE, and this is the
                       band the repair opened

        FAILURE MEANS: the accept/reject frontier moved, or a width
        inside the reachable window raises instead of being counted.

        THE FIRST DRAFT OF THIS TEST ASSERTED `got == 0` FOR EVERY
        WIDTH AND WENT RED ON ONE DIGIT, because 9 is a perfectly good
        pct. The code was right and the test's model of the low end was
        wrong. It is written out here because that is the red this test
        was actually shown to produce."""
        first_overflow = None
        for digits in range(1, 400):
            try:
                float(int("9" * digits))
            except OverflowError:
                first_overflow = digits
                break
        assert first_overflow == 309, (
            f"measured boundary moved to {first_overflow}; the window "
            f"this repair covers is defined by it"
        )

        widths = [1, 2, 3, 4, 20, 100, 307, 308, 309, 310, 400, 1000, 4300]
        for digits in widths:
            value = int("9" * digits)
            mgr = SmartWireManager()
            wirelog.clear()
            got = mgr.import_wires([{"source_id": "C", "target_id": "D", "pct": value}])

            if value <= 100:
                assert got == 1, f"{digits} digits: {value} is a valid pct"
                assert mgr.get_outgoing_wires("C") == {"D": float(value)}
                assert (
                    _dropped(wirelog) == []
                ), f"{digits} digits: a valid pct must not be reported"
                assert _heads(wirelog) == []
                continue

            assert got == 0, f"{digits} digits: nothing may be stored"
            assert mgr.get_outgoing_wires("C") == {}
            assert (
                len(_dropped(wirelog)) == 1
            ), f"{digits} digits: exactly one named line"
            assert len(_heads(wirelog)) == 1, f"{digits} digits: exactly one headline"
            _, _, _, mal, unr, uno = (int(g) for g in _heads(wirelog)[0].groups())
            if digits >= first_overflow:
                assert (mal, unr, uno) == (0, 1, 0), (
                    f"{digits} digits overflows a double, so it is an "
                    f"unreadable pct"
                )
                assert "OverflowError" in _dropped(wirelog)[0]
            else:
                assert (mal, unr, uno) == (0, 0, 1), (
                    f"{digits} digits is representable and simply "
                    f"exceeds 100, so it is unroutable"
                )

    def test_above_the_json_limit_is_a_different_defect(self):
        """FAILURE MEANS: the window this repair covers is not bounded
        where it is claimed to be, so the claim is wrong even though the
        tests pass."""
        assert sys.get_int_max_str_digits() == 4300
        with pytest.raises(ValueError):
            json.loads('{"pct": ' + "9" * 4301 + "}")


class TestHoleOneTheRestoreDownstreamNowRuns:
    """FAILURE MEANS: the caller still loses the ledgers and the GUI
    re-emit. The wires being right is not the whole repair - the escape
    made BotManager return 0, and the two blocks after that return are
    what rehydrate every bot's wired_in/wired_out and what draws the
    topology on screen."""

    @staticmethod
    def _drive(rows):
        from src.trading.bot_container import BotManager

        restore = BotManager.__dict__["restore_smart_wires_from_state"]

        class Bus:
            def __init__(self):
                self.events = []

            def emit(self, name, **kwargs):
                self.events.append((name, kwargs))

        class Receiver:
            def __init__(self):
                self._smart_wire_mgr = SmartWireManager()
                self._bus = Bus()
                self._bots = {f"bot_{c}": object() for c in "ABCDEF"}

        receiver = Receiver()
        state = {
            "smart_wires": rows,
            "smart_wire_ledgers": [
                {"bot_id": "bot_A", "asset": "BTC", "total_profit": 10.0},
                {"bot_id": "bot_B", "asset": "ETH", "total_profit": 20.0},
            ],
        }
        return restore(receiver, state), receiver

    def test_a_wide_int_row_no_longer_costs_the_ledgers(self):
        rows = [
            {"source_id": "bot_A", "target_id": "bot_B", "pct": 25.0},
            {"source_id": "bot_C", "target_id": "bot_D", "pct": WIDE_INT},
            {"source_id": "bot_E", "target_id": "bot_F", "pct": 40.0},
        ]
        got, receiver = self._drive(json.loads(json.dumps(rows)))
        assert got == 2, "the caller must see the accepted count, not 0"
        assert len(receiver._smart_wire_mgr.export_ledgers()) == 2, (
            "the ledger import runs AFTER the wire import and was "
            "skipped entirely by the escape"
        )
        created = [e for e in receiver._bus.events if e[0] == "wire.created"]
        assert len(created) == 2, (
            "the GUI re-emit runs after the ledger import and was "
            "skipped too, so the operator's topology drew empty"
        )

    def test_the_clean_case_is_unchanged(self):
        rows = [
            {"source_id": "bot_A", "target_id": "bot_B", "pct": 25.0},
            {"source_id": "bot_E", "target_id": "bot_F", "pct": 40.0},
        ]
        got, receiver = self._drive(rows)
        assert got == 2
        assert len(receiver._smart_wire_mgr.export_ledgers()) == 2
        assert len([e for e in receiver._bus.events if e[0] == "wire.created"]) == 2


class TestHoleOneAtTheOriginWriter:
    """FAILURE MEANS: `register_wire` still RAISES on a value it is
    supposed to refuse. Its entire documented contract is to return
    {"applied": bool, "reason": str}; an exception instead of a refusal
    is a crash in every caller that reads the dict."""

    def test_a_wide_int_is_refused_not_raised(self):
        got = SmartWireManager().register_wire("a", "b", WIDE_INT)
        assert got["applied"] is False
        assert "OverflowError" in got["reason"], (
            "what was caught must be named; an anonymous refusal is the "
            "silent swallow one layer up"
        )

    def test_the_reason_no_longer_claims_it_is_not_numeric(self):
        got = SmartWireManager().register_wire("a", "b", WIDE_INT)
        assert "must be numeric" not in got["reason"], (
            "a 400-digit integer IS numeric; saying otherwise sends the "
            "reader after the wrong defect"
        )

    @pytest.mark.parametrize("bad", [0, -5, 101, "x", None, [], {}])
    def test_every_previously_refused_value_is_still_refused(self, bad):
        """FAILURE MEANS: widening the except changed a verdict it had
        no business changing."""
        assert SmartWireManager().register_wire("a", "b", bad)["applied"] is False

    @pytest.mark.parametrize("good", [25.0, 100, 0.001, "25", True])
    def test_every_previously_accepted_value_is_still_accepted(self, good):
        assert SmartWireManager().register_wire("a", "b", good)["applied"] is True


# --------------------------------------------------------------------- #
# HOLE 2 — nan passed the range guard                                    #
# --------------------------------------------------------------------- #
class TestHoleTwoNanIsRefusedCountedAndNamed:
    """FAILURE MEANS: a nan wire is stored and reported as a successful
    import again. It is the only bad shape that used to be broken AND
    silent AND counted as a success, and it reaches the money path."""

    def test_the_mechanism_is_what_the_message_says(self):
        """FAILURE MEANS: the explanation in the log and the comment is
        wrong, whatever the guard now does."""
        nan = float("nan")
        assert (nan <= 0) is False
        assert (nan > 100) is False
        assert (nan < 0.01) is False, "the dust floor cannot stop a nan share either"

    def test_a_nan_row_is_refused(self, wirelog):
        mgr = SmartWireManager()
        rows = [dict(GOOD), {"source_id": "C", "target_id": "D", "pct": float("nan")}]
        assert mgr.import_wires(rows) == 1
        assert mgr.get_outgoing_wires("C") == {}
        assert mgr.get_outgoing_wires("A") == {"B": 25.0}
        assert not _has_nan(mgr)

    def test_the_nan_row_is_named_as_nan_not_as_out_of_range(self, wirelog):
        """FAILURE MEANS: the operator is told the value was outside
        0 < pct <= 100. It was not - nan is unordered, both comparisons
        return False, and that is exactly why the row used to pass."""
        SmartWireManager().import_wires(
            [{"source_id": "C", "target_id": "D", "pct": float("nan")}]
        )
        line = _dropped(wirelog)[0]
        assert "nan" in line
        assert "unordered" in line
        assert "pct is outside the accepted" not in line

    def test_the_headline_blames_unroutable(self, wirelog):
        SmartWireManager().import_wires(
            [dict(GOOD), {"source_id": "C", "target_id": "D", "pct": float("nan")}]
        )
        heads = _heads(wirelog)
        assert len(heads) == 1
        assert tuple(int(g) for g in heads[0].groups()) == (1, 2, 1, 0, 0, 1)

    @pytest.mark.parametrize(
        "value", [float("nan"), "nan", "NaN", "-nan", float("-nan")]
    )
    def test_every_spelling_of_nan_is_refused_by_both_writers(self, value):
        importer = SmartWireManager()
        assert (
            importer.import_wires([{"source_id": "A", "target_id": "B", "pct": value}])
            == 0
        )
        assert not _has_nan(importer)
        register = SmartWireManager()
        assert register.register_wire("A", "B", value)["applied"] is False
        assert not _has_nan(register)

    def test_the_register_refusal_names_nan(self):
        got = SmartWireManager().register_wire("A", "B", float("nan"))
        assert "nan" in got["reason"]
        assert "unordered" in got["reason"]
        assert "must be in (0, 100]" not in got["reason"], (
            "nan does not fail a range test; saying it did describes a "
            "check that never ran"
        )

    def test_a_nan_can_never_be_exported_so_never_saved(self):
        """FAILURE MEANS: the save file can still grow a bare `NaN`
        token, which is not valid JSON, and the next launch reads it
        back. Closing only the importer would leave this open."""
        mgr = SmartWireManager()
        mgr.register_wire("A", "B", float("nan"))
        mgr.import_wires([{"source_id": "C", "target_id": "D", "pct": float("nan")}])
        assert mgr.export_wires() == []
        assert "NaN" not in json.dumps({"smart_wires": mgr.export_wires()})


# The whole input universe json.loads can deliver, plus the edges of
# every numeric frontier this method has. NOT a table of interesting
# cases: the point is that the accepted set may not contain a nan for
# ANY of them, at EITHER writer.
DOMAIN = [
    25.0,
    100,
    100.0,
    0.001,
    "25",
    "100",
    True,
    False,
    float("nan"),
    float("-nan"),
    "nan",
    "NaN",
    "-nan",
    float("inf"),
    float("-inf"),
    "inf",
    "-inf",
    "1e400",
    "-1e400",
    0,
    0.0,
    -1,
    101,
    100.0000001,
    99.9999999,
    WIDE_INT,
    -WIDE_INT,
    int("9" * 309),
    int("9" * 308),
    None,
    [],
    {},
    "abc",
    "",
    "  ",
    "nan(ind)",
]


class TestNoNanSurvivesAnywhere:
    """FAILURE MEANS: some value still reaches `_wires` as a nan, and
    every downstream number computed from it is a nan that no guard
    below can see."""

    @pytest.mark.parametrize("value", DOMAIN, ids=[repr(v)[:24] for v in DOMAIN])
    def test_neither_writer_stores_a_nan_and_neither_raises(self, value):
        register = SmartWireManager()
        register.register_wire("A", "B", value)
        assert not _has_nan(register), "register_wire stored nan"

        importer = SmartWireManager()
        importer.import_wires([{"source_id": "A", "target_id": "B", "pct": value}])
        assert not _has_nan(importer), "import_wires stored nan"

    @pytest.mark.parametrize("value", DOMAIN, ids=[repr(v)[:24] for v in DOMAIN])
    def test_the_two_writers_agree_on_every_value(self, value):
        """FAILURE MEANS: the same pct is accepted through the GUI and
        refused on restore, or the reverse - a wire the operator drew
        disappears on the next launch with nothing said."""
        register = SmartWireManager()
        by_register = register.register_wire("A", "B", value)["applied"]
        importer = SmartWireManager()
        by_import = (
            importer.import_wires([{"source_id": "A", "target_id": "B", "pct": value}])
            == 1
        )
        assert by_register == by_import, (
            f"register_wire={by_register} import_wires={by_import} "
            f"for pct={value!r}"
        )


class TestNoNanReachesTheMoneyPath:
    """FAILURE MEANS: `distribute_fold_profit` computes
    `share = profit * nan / 100`, hands a nan to apply_wire_income, and
    books it as a COMPLETED WireTransaction. The dust floor cannot stop
    it, because `nan < min_wire` is False."""

    def test_a_nan_wire_cannot_be_built_so_nothing_nan_is_routed(self):
        mgr = SmartWireManager()
        mgr.import_wires(
            [
                {"source_id": "bot_A", "target_id": "bot_B", "pct": 25.0},
                {"source_id": "bot_A", "target_id": "bot_D", "pct": float("nan")},
            ]
        )
        good, refused = _Target(), _Target()
        mgr.attach_bot("bot_A", object())
        mgr.attach_bot("bot_B", good)
        mgr.attach_bot("bot_D", refused)

        results = mgr.distribute_fold_profit("bot_A", 40.0, ref="fold-1")
        assert [
            r
            for r in results
            if isinstance(r["share"], float) and math.isnan(r["share"])
        ] == []
        assert good.got == [10.0], "the healthy 25% wire still pays"
        assert good.calls == [("bot_A", "fold-1")]
        assert refused.got == [], "the nan target is paid nothing"
        assert refused.calls == [], "and is never called at all"
        stats = mgr.stats
        assert stats["transactions"] == 1
        assert not math.isnan(stats["total_wired"])
        assert stats["total_wired"] == 10.0


# --------------------------------------------------------------------- #
# THE HAZARD IN THE FIX — a broader except can hide a real bug           #
# --------------------------------------------------------------------- #
class TestTheWidenedExceptHidesNothing:
    """FAILURE MEANS: the guarded region grew past the coercion. A
    failed store swallowed as 'unreadable' would shrink the topology
    while the headline still reconciled - a lie that reads as truth -
    and a broken log call swallowed there would make a row vanish with
    no line at all, the exact defect this method was repaired for."""

    def test_a_raise_on_the_store_line_still_escapes(self, wirelog):
        with pytest.raises(RuntimeError, match="PLANTED store-line"):
            SmartWireManager().import_wires(
                [{"source_id": _Unprintable(), "target_id": "B", "pct": 25.0}]
            )
        assert _dropped(wirelog) == [], (
            "a store failure counted as a corrupt row is the widened "
            "except reaching code it must never cover"
        )
        assert _heads(wirelog) == []

    def test_a_raise_in_a_log_call_still_escapes(self, monkeypatch):
        monkeypatch.setattr(
            smart_wire_module.logger, "warning", _boom("PLANTED log failure")
        )
        with pytest.raises(RuntimeError, match="PLANTED log failure"):
            SmartWireManager().import_wires(["not-a-dict"])

    def test_a_raise_in_the_widened_handler_itself_still_escapes(self, monkeypatch):
        """FAILURE MEANS: the handler is somehow re-protected, so the
        row it was reporting on disappears with no line at all."""
        monkeypatch.setattr(
            smart_wire_module.logger, "warning", _boom("PLANTED handler failure")
        )
        with pytest.raises(RuntimeError, match="PLANTED handler"):
            SmartWireManager().import_wires(
                [{"source_id": "A", "target_id": "B", "pct": WIDE_INT}]
            )

    def test_a_raise_from_the_coercion_is_caught_counted_and_named(self, wirelog):
        """THE OTHER SIDE. FAILURE MEANS: the except is too narrow
        again, and an arbitrary coercion failure abandons every
        remaining row."""
        mgr = SmartWireManager()
        got = mgr.import_wires(
            [
                {"source_id": "A", "target_id": "B", "pct": _Hostile()},
                {"source_id": "C", "target_id": "D", "pct": 25.0},
            ]
        )
        assert got == 1
        assert mgr.get_outgoing_wires("C") == {"D": 25.0}
        line = _dropped(wirelog)[0]
        assert "RuntimeError" in line
        assert "PLANTED coercion failure" in line

    def test_register_wire_catches_the_coercion_and_still_refuses(self):
        got = SmartWireManager().register_wire("A", "B", _Hostile())
        assert got["applied"] is False
        assert "RuntimeError" in got["reason"]
        assert "PLANTED coercion failure" in got["reason"]

    def test_a_raise_on_register_wires_overwrite_log_still_escapes(self, monkeypatch):
        mgr = SmartWireManager()
        mgr.register_wire("A", "B", 20.0)
        monkeypatch.setattr(
            smart_wire_module.logger, "warning", _boom("PLANTED overwrite failure")
        )
        with pytest.raises(RuntimeError, match="PLANTED overwrite"):
            mgr.register_wire("A", "B", 50.0)

    @pytest.mark.parametrize(
        "needle", ['pct = float(w.get("pct", 0))', "p = float(pct)"]
    )
    def test_each_guarded_region_is_textually_one_statement(self, needle):
        """FAILURE MEANS: somebody widened the BLOCK rather than the
        except, and a future defect inside it will be reported as a
        corrupt saved row."""
        from pathlib import Path

        source = (
            Path(smart_wire_module.__file__)
            .read_text(encoding="utf-8", newline="")
            .split("\n")
        )
        hits = [i for i, line in enumerate(source) if line.strip() == needle]
        assert len(hits) == 1, f"{needle}: {len(hits)} matches"
        idx = hits[0]
        assert source[idx - 1].strip() == "try:"
        assert source[idx + 1].strip().startswith("except ")


# --------------------------------------------------------------------- #
# CONSERVATION — accepted + lost == offered, read off the headline       #
# --------------------------------------------------------------------- #
def _pool():
    """Row factories tagged with the cause the GUARD ORDER assigns."""
    return [
        (
            "accepted",
            lambda i: {"source_id": f"s{i}", "target_id": f"t{i}", "pct": 10.0},
        ),
        (
            "accepted",
            lambda i: {"source_id": f"s{i}", "target_id": f"t{i}", "pct": "20"},
        ),
        (
            "accepted",
            lambda i: {"source_id": f"s{i}", "target_id": f"t{i}", "pct": 100},
        ),
        (
            "accepted",
            lambda i: {"source_id": f"s{i}", "target_id": f"t{i}", "pct": True},
        ),
        ("malformed", lambda i: f"row-{i}-is-a-string"),
        ("malformed", lambda i: None),
        ("malformed", lambda i: [i]),
        (
            "unreadable",
            lambda i: {"source_id": f"s{i}", "target_id": f"t{i}", "pct": "abc"},
        ),
        (
            "unreadable",
            lambda i: {"source_id": f"s{i}", "target_id": f"t{i}", "pct": []},
        ),
        (
            "unreadable",
            lambda i: {"source_id": f"s{i}", "target_id": f"t{i}", "pct": WIDE_INT},
        ),
        ("unreadable", lambda i: {"target_id": f"t{i}", "pct": WIDE_INT}),
        ("unroutable", lambda i: {"target_id": f"t{i}", "pct": 10.0}),
        ("unroutable", lambda i: {"source_id": f"s{i}", "pct": 10.0}),
        (
            "unroutable",
            lambda i: {"source_id": f"s{i}", "target_id": f"t{i}", "pct": 0},
        ),
        (
            "unroutable",
            lambda i: {"source_id": f"s{i}", "target_id": f"t{i}", "pct": 500},
        ),
        (
            "unroutable",
            lambda i: {"source_id": f"s{i}", "target_id": f"t{i}", "pct": -3},
        ),
        (
            "unroutable",
            lambda i: {"source_id": f"s{i}", "target_id": f"t{i}", "pct": float("inf")},
        ),
        (
            "unroutable",
            lambda i: {"source_id": f"s{i}", "target_id": f"t{i}", "pct": float("nan")},
        ),
        (
            "unroutable",
            lambda i: {"source_id": f"s{i}", "target_id": f"t{i}", "pct": "nan"},
        ),
        (
            "unroutable",
            lambda i: {
                "source_id": f"s{i}",
                "target_id": f"t{i}",
                "pct": int("9" * 308),
            },
        ),
    ]


def _lcg(seed: int):
    """Deterministic index stream, hand-rolled.

    `random.Random` is a ruff S311 finding and a suppression is
    forbidden. Determinism is what a control wants anyway: a batch that
    fails must be re-drivable, and an irreproducible red says nothing.
    """
    value = seed & 0x7FFFFFFF
    while True:
        value = (value * 1103515245 + 12345) & 0x7FFFFFFF
        yield value


class TestConservationStillHolds:
    """FAILURE MEANS: the two new branches broke the reconciliation the
    unit before this one built. A row is lost without being counted, or
    counted under the wrong cause, and a wrong total reads as a checked
    one - which is worse than no total at all."""

    def test_random_mixed_batches_reconcile(self, wirelog, sink):
        stream = _lcg(20260815)
        factories = _pool()
        seen: dict[str, int] = {}
        rows_driven = 0

        for batch in range(240):
            handed = {"accepted": 0, "malformed": 0, "unreadable": 0, "unroutable": 0}
            payload = []
            for i in range(1 + next(stream) % 12):
                cause, make = factories[next(stream) % len(factories)]
                payload.append(make(batch * 100 + i))
                handed[cause] += 1
                seen[cause] = seen.get(cause, 0) + 1
            rows_driven += len(payload)

            wirelog.clear()
            before = sink.count(PIN)
            got = SmartWireManager().import_wires(list(payload))

            lost = handed["malformed"] + handed["unreadable"] + handed["unroutable"]
            assert (
                got == handed["accepted"]
            ), f"batch {batch}: accepted disagrees with rows handed in"

            records = sink.records(PIN)
            assert (
                len(records) == before + 1
            ), f"batch {batch}: the pin did not fire exactly once"
            assert records[-1].expected == len(
                payload
            ), f"batch {batch}: `expected` is not the offered count"
            assert records[-1].actual == got

            heads = _heads(wirelog)
            if not lost:
                assert not heads, f"batch {batch}: a clean batch fired the headline"
                continue
            assert len(heads) == 1, f"batch {batch}: one headline"
            acc, off, tot, mal, unr, uno = (int(g) for g in heads[0].groups())
            assert off == len(payload), f"batch {batch}: offered"
            assert acc == got, f"batch {batch}: headline accepted != n"
            assert acc + tot == off, f"batch {batch}: {acc}+{tot}!={off}"
            assert mal + unr + uno == tot, f"batch {batch}: causes"
            assert mal == handed["malformed"], f"batch {batch}: malformed"
            assert unr == handed["unreadable"], f"batch {batch}: unread"
            assert uno == handed["unroutable"], f"batch {batch}: unroute"

        assert (
            rows_driven >= 1600
        ), f"only {rows_driven} rows driven; too few to close anything"
        for cause in ("accepted", "malformed", "unreadable", "unroutable"):
            assert seen.get(cause, 0) > 0, (
                f"no {cause} row was generated, so that bucket is "
                f"untested and its zero says nothing"
            )


# --------------------------------------------------------------------- #
# THE PIN — both sides                                                   #
# --------------------------------------------------------------------- #
# 33 rows, the size and shape of the operator's real topology, measured
# read-only from his save on 2026-08-15: 33 offered, 33 accepted, 0 lost.
OPERATOR_SHAPED = [
    {
        "source_id": f"bot{i:02d}",
        "target_id": f"bot{(i + 7) % 37:02d}",
        "pct": float(5 + (i % 20)),
    }
    for i in range(33)
]


class TestThePinStillFiresAndCanStillFail:
    """FAILURE MEANS: topology.09.002 stopped firing, or its `expected`
    stopped being the true offered count, or it can no longer disagree.
    A pin that cannot fail is noise that reads as assurance."""

    def test_a_clean_restore_passes(self, sink):
        SmartWireManager().import_wires(list(OPERATOR_SHAPED))
        record = sink.records(PIN)[0]
        assert (record.actual, record.expected, record.ok) == (33, 33, True)

    def test_the_pin_can_fail_on_a_row_that_was_always_caught(self, sink):
        """THE CONTROL FOR THE TWO BELOW. FAILURE MEANS: the pin is
        vacuous, and its green on the nan and wide-int cases proves
        nothing at all."""
        SmartWireManager().import_wires(
            [
                dict(GOOD),
                {"source_id": "C", "target_id": "D", "pct": 25.0},
                {"source_id": "E", "target_id": "F", "pct": 500},
            ]
        )
        record = sink.records(PIN)[0]
        assert (record.actual, record.expected, record.ok) == (2, 3, False)

    def test_hole_two_now_fails_the_pin(self, sink):
        """It used to read actual=3 expected=3 ok=True: correct and
        useless at the same time, because the nan row was accepted so
        accepted == offered. FAILURE MEANS: it reads green again."""
        SmartWireManager().import_wires(
            [
                dict(GOOD),
                {"source_id": "C", "target_id": "D", "pct": 25.0},
                {"source_id": "E", "target_id": "F", "pct": float("nan")},
            ]
        )
        record = sink.records(PIN)[0]
        assert (record.actual, record.expected, record.ok) == (2, 3, False)

    def test_hole_one_now_produces_a_record_at_all(self, sink):
        """It used to produce NO RECORD, because the emitter sits after
        the loop and the raise passed it. FAILURE MEANS: the pin is
        blind to the failure mode with the largest blast radius."""
        SmartWireManager().import_wires(
            [
                dict(GOOD),
                {"source_id": "C", "target_id": "D", "pct": 25.0},
                {"source_id": "E", "target_id": "F", "pct": WIDE_INT},
            ]
        )
        assert sink.count(PIN) == 1, "no record at all is the old bug"
        record = sink.records(PIN)[0]
        assert (record.actual, record.expected, record.ok) == (2, 3, False)

    def test_an_empty_topology_still_emits_zero_of_zero(self, sink):
        SmartWireManager().import_wires([])
        record = sink.records(PIN)[0]
        assert (record.actual, record.expected, record.ok) == (0, 0, True)


# --------------------------------------------------------------------- #
# NO FALSE ALARM                                                         #
# --------------------------------------------------------------------- #
class TestNoFalseAlarmOnACleanTopology:
    """FAILURE MEANS: the repair fires on a launch that used to be
    clean. The operator restores on every start and carries a
    guard-clean 33-row topology, so a line he sees every time is one he
    learns to ignore - which is the same defect as silence.

    Verified against his real save, read-only, on 2026-08-15: the
    emitted output is byte-identical before and after this change."""

    def test_an_operator_sized_topology_says_nothing_new(self, wirelog):
        mgr = SmartWireManager()
        assert mgr.import_wires(list(OPERATOR_SHAPED)) == 33
        assert _warnings(wirelog) == []
        assert len(_infos(wirelog)) == 1
        assert "imported 33 wire(s)" in _infos(wirelog)[0]

    def test_a_full_round_trip_through_both_writers_stays_silent(self, wirelog):
        source = SmartWireManager()
        for i in range(12):
            assert (
                source.register_wire(f"src{i}", f"tgt{i}", 5.0 + i)["applied"] is True
            )
        snapshot = json.loads(json.dumps({"smart_wires": source.export_wires()}))[
            "smart_wires"
        ]
        wirelog.clear()
        restored = SmartWireManager()
        assert restored.import_wires(snapshot) == 12
        assert _warnings(wirelog) == []
        assert _accepted(restored) == _accepted(source)

    def test_re_importing_the_same_snapshot_stays_silent(self, wirelog):
        mgr = SmartWireManager()
        mgr.import_wires(list(OPERATOR_SHAPED))
        wirelog.clear()
        assert mgr.import_wires(list(OPERATOR_SHAPED)) == 33
        assert _warnings(wirelog) == []
