"""`SmartWireManager.import_wires` reports every wire row it drops.

`import_wires` names each dropped row with its ordinal and cause, closes
with the reconciling headline `HEADLINE` matches, and stays silent on a
guard-clean payload. Each test drives the real manager and reads
`LOGGER_NAME` through `wirelog`, or the `PIN` records through `sink`.
"""

from __future__ import annotations

import logging
import math
import re

import pytest

from src.core.signal_contract import SignalSink, set_sink
from src.trading.smart_wire import SmartWireManager

LOGGER_NAME = "acervator.smart_wire"
PIN = "topology.09.002.postcondition.wires_received"

HEADLINE = re.compile(
    r"import accepted (\d+) of (\d+) wire row\(s\) offered; "
    r"(\d+) lost \((\d+) not a row, (\d+) had an unreadable pct, "
    r"(\d+) had no endpoint or a pct outside 0-100\)"
)


def _accepted(mgr: SmartWireManager) -> dict:
    """The accepted set, read through the public snapshot API."""
    out: dict[str, dict[str, float]] = {}
    for row in mgr.export_wires():
        out.setdefault(row["source_id"], {})[row["target_id"]] = row["pct"]
    return out


def _same_wires(got: dict, want: dict) -> bool:
    """Report got equal to want, treating a nan pct on either side as a difference."""
    for side in (got, want):
        for targets in side.values():
            for pct in targets.values():
                if isinstance(pct, float) and math.isnan(pct):
                    return False
    return got == want


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


@pytest.fixture
def wirelog(capture_log):
    """Records from `LOGGER_NAME`, captured with `capture_log`.

    `logging_engine` sets `propagate = False` on the acervator logger, and
    `caplog` then sees no record from `LOGGER_NAME`.
    """
    with capture_log(LOGGER_NAME, logging.DEBUG) as records:
        yield records


@pytest.fixture
def sink():
    s = SignalSink(flush_every=10_000)
    set_sink(s)
    yield s
    set_sink(None)


GOOD = {"source_id": "A", "target_id": "B", "pct": 25.0}

ROW_SHAPES = [
    ("good", [GOOD], {"A": {"B": 25.0}}, 1),
    ("good_plus_string", [GOOD, "not-a-dict"], {"A": {"B": 25.0}}, 1),
    ("good_plus_none", [GOOD, None], {"A": {"B": 25.0}}, 1),
    ("pct_unparseable", [{"source_id": "A", "target_id": "B", "pct": "abc"}], {}, 0),
    ("missing_source", [{"target_id": "B", "pct": 25.0}], {}, 0),
    ("missing_target", [{"source_id": "A", "pct": 25.0}], {}, 0),
    ("pct_zero", [{"source_id": "A", "target_id": "B", "pct": 0}], {}, 0),
    (
        "pct_100",
        [{"source_id": "A", "target_id": "B", "pct": 100}],
        {"A": {"B": 100.0}},
        1,
    ),
    ("pct_101", [{"source_id": "A", "target_id": "B", "pct": 101}], {}, 0),
    ("pct_negative", [{"source_id": "A", "target_id": "B", "pct": -1}], {}, 0),
    ("pct_nan", [{"source_id": "A", "target_id": "B", "pct": float("nan")}], {}, 0),
    ("pct_inf", [{"source_id": "A", "target_id": "B", "pct": float("inf")}], {}, 0),
    (
        "pct_neg_inf",
        [{"source_id": "A", "target_id": "B", "pct": float("-inf")}],
        {},
        0,
    ),
    ("pct_nan_string", [{"source_id": "A", "target_id": "B", "pct": "nan"}], {}, 0),
    (
        "pct_numeric_string",
        [{"source_id": "A", "target_id": "B", "pct": "25"}],
        {"A": {"B": 25.0}},
        1,
    ),
    (
        "pct_true",
        [{"source_id": "A", "target_id": "B", "pct": True}],
        {"A": {"B": 1.0}},
        1,
    ),
    (
        "pct_wide_int",
        [{"source_id": "A", "target_id": "B", "pct": int("9" * 400)}],
        {},
        0,
    ),
    (
        "pct_wide_int_representable",
        [{"source_id": "A", "target_id": "B", "pct": int("9" * 308)}],
        {},
        0,
    ),
    ("pct_false", [{"source_id": "A", "target_id": "B", "pct": False}], {}, 0),
    (
        "duplicate_route",
        [
            {"source_id": "A", "target_id": "B", "pct": 25.0},
            {"source_id": "A", "target_id": "B", "pct": 40.0},
        ],
        {"A": {"B": 40.0}},
        2,
    ),
    ("empty_list", [], {}, 0),
    (
        "mixed_six_row",
        [
            GOOD,
            "not-a-dict",
            {"source_id": "C", "target_id": "D", "pct": "abc"},
            {"target_id": "E", "pct": 10.0},
            {"source_id": "F", "target_id": "G", "pct": 500},
            {"source_id": "H", "target_id": "I", "pct": 5.0},
        ],
        {"A": {"B": 25.0}, "H": {"I": 5.0}},
        2,
    ),
]

NON_LIST_ARGS = [("dict_arg", {"source_id": "A"}), ("none_arg", None)]


class TestTheInstrumentSees:
    """`wirelog` sees an INFO and a WARNING, and `sink` sees `PIN`."""

    def test_log_capture_sees_the_clean_info_line(self, wirelog):
        SmartWireManager().import_wires([GOOD])
        assert _infos(wirelog), (
            "no INFO captured on a clean import; a clean import MUST "
            "log 'imported 1 wire(s)', so capture is blind"
        )

    def test_log_capture_sees_a_warning(self, wirelog):
        SmartWireManager().import_wires(["not-a-dict"])
        assert _warnings(wirelog), (
            "no WARNING captured on a total-loss import; capture is "
            "blind and every silence assertion below is worthless"
        )

    def test_emit_capture_sees_the_pin(self, sink):
        SmartWireManager().import_wires([GOOD])
        assert sink.count(PIN) == 1, (
            "the pin did not reach the sink; the emitter assertions "
            "below cannot distinguish 'correct' from 'never fired'"
        )


class TestTheAcceptedSetIsUnchanged:
    """`import_wires` stores the set and returns the count `ROW_SHAPES` names."""

    @pytest.mark.parametrize(
        ("label", "payload", "want", "count"),
        ROW_SHAPES,
        ids=[r[0] for r in ROW_SHAPES],
    )
    def test_row_shape_lands_exactly_as_before(self, label, payload, want, count):
        mgr = SmartWireManager()
        got_n = mgr.import_wires(list(payload))
        assert got_n == count, f"{label}: returned count changed"
        assert _same_wires(
            _accepted(mgr), want
        ), f"{label}: the restored topology changed"

    @pytest.mark.parametrize(
        ("label", "arg"), NON_LIST_ARGS, ids=[r[0] for r in NON_LIST_ARGS]
    )
    def test_non_list_argument_still_returns_zero_and_stores_nothing(self, label, arg):
        mgr = SmartWireManager()
        assert mgr.import_wires(arg) == 0
        assert _accepted(mgr) == {}

    def test_public_reader_agrees_with_the_snapshot(self):
        mgr = SmartWireManager()
        mgr.import_wires([GOOD, {"source_id": "H", "target_id": "I", "pct": 5.0}])
        assert mgr.get_outgoing_wires("A") == {"B": 25.0}
        assert mgr.get_outgoing_wires("H") == {"I": 5.0}
        assert mgr.get_outgoing_wires("nobody") == {}


def _pool():
    """Row factories tagged with the `HEADLINE` bucket each row counts under."""
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
            "unroutable",
            lambda i: {"source_id": f"s{i}", "target_id": f"t{i}", "pct": float("nan")},
        ),
        (
            "unreadable",
            lambda i: {
                "source_id": f"s{i}",
                "target_id": f"t{i}",
                "pct": int("9" * 400),
            },
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
    ]


def _lcg(seed: int):
    """Yield a deterministic index stream from seed, one congruential step apart."""
    x = seed & 0x7FFFFFFF
    while True:
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        yield x


class TestTheTotalReconciles:
    """The `HEADLINE` numbers reconcile with the rows handed to `import_wires`.

    Each `_pool` row is tagged with the bucket it belongs in, and the six
    captured groups are checked against those tags batch by batch.
    """

    def test_random_mixed_batches_reconcile(self, wirelog):
        stream = _lcg(20260815)
        pool = _pool()
        seen_causes: dict[str, int] = {}
        rows_driven = 0
        batches = 0

        for batch in range(120):
            handed: dict[str, int] = {
                "accepted": 0,
                "malformed": 0,
                "unreadable": 0,
                "unroutable": 0,
            }
            payload = []
            for i in range(1 + next(stream) % 12):
                cause, make = pool[next(stream) % len(pool)]
                payload.append(make(batch * 100 + i))
                handed[cause] += 1
                seen_causes[cause] = seen_causes.get(cause, 0) + 1
            rows_driven += len(payload)
            batches += 1

            wirelog.clear()
            mgr = SmartWireManager()
            n = mgr.import_wires(list(payload))

            lost = handed["malformed"] + handed["unreadable"] + handed["unroutable"]
            assert n == handed["accepted"], (
                f"batch {batch}: accepted count disagrees with the " f"rows handed in"
            )

            heads = [m for m in (HEADLINE.search(w) for w in _warnings(wirelog)) if m]
            if not lost:
                assert not heads, f"batch {batch}: a clean batch fired the headline"
                continue
            assert len(heads) == 1, (
                f"batch {batch}: expected exactly one headline, got " f"{len(heads)}"
            )
            acc, off, tot, mal, unr, uno = (int(g) for g in heads[0].groups())
            assert off == len(payload), (
                f"batch {batch}: offered {off} != rows handed in " f"{len(payload)}"
            )
            assert acc == n, f"batch {batch}: headline accepted != n"
            assert acc + tot == off, f"batch {batch}: {acc} + {tot} != {off}"
            assert mal == handed["malformed"], f"batch {batch}: malformed"
            assert unr == handed["unreadable"], f"batch {batch}: unreadable"
            assert uno == handed["unroutable"], f"batch {batch}: unroutable"
            assert mal + unr + uno == tot, f"batch {batch}: causes != lost"

        assert batches == 120
        assert rows_driven >= 100, (
            f"only {rows_driven} rows driven; the control needs at " f"least 100"
        )
        for cause in ("accepted", "malformed", "unreadable", "unroutable"):
            assert seen_causes.get(cause, 0) > 0, (
                f"no {cause} row was ever generated, so that bucket is "
                f"untested and its zero says nothing"
            )


class TestTheSilentCaseSpeaks:
    """A payload `import_wires` drops in full still writes one line per row.

    The `n > 0` guard keeps the INFO line silent, and `HEADLINE` carries the
    ordinal, the cause and the operator consequence for every dropped row.
    """

    def test_total_loss_is_reported(self, wirelog):
        payload = [
            "not-a-dict",
            {"source_id": "A", "target_id": "B", "pct": 500},
            {"target_id": "B", "pct": 10.0},
        ]
        mgr = SmartWireManager()
        assert mgr.import_wires(payload) == 0
        assert _accepted(mgr) == {}
        assert not _infos(
            wirelog
        ), "a total-loss import must not claim it imported anything"
        warns = _warnings(wirelog)
        assert len(warns) == 4, (
            f"expected one line per lost row plus one headline, got " f"{len(warns)}"
        )
        head = [m for m in (HEADLINE.search(w) for w in warns) if m]
        assert len(head) == 1
        acc, off, tot, mal, unr, uno = (int(g) for g in head[0].groups())
        assert (acc, off, tot, mal, unr, uno) == (0, 3, 3, 1, 0, 2)

    def test_each_lost_row_names_its_ordinal_and_cause(self, wirelog):
        payload = [
            "not-a-dict",
            {"source_id": "C", "target_id": "D", "pct": "abc"},
            {"target_id": "E", "pct": 10.0},
            {"source_id": "F", "pct": 10.0},
            {"source_id": "G", "target_id": "H", "pct": 500},
        ]
        SmartWireManager().import_wires(payload)
        rows = [w for w in _warnings(wirelog) if "DROPPED" in w]
        assert len(rows) == 5, "one line per lost row"
        assert "row 1 of 5" in rows[0] and "not a row" in rows[0]
        assert "row 2 of 5" in rows[1] and "float() refused" in rows[1]
        assert "ValueError" in rows[1], (
            "a widened except that does not name what it caught is the "
            "silent swallow this file exists to remove"
        )
        assert "C" in rows[1] and "D" in rows[1]
        assert "row 3 of 5" in rows[2] and "source_id is empty" in rows[2]
        assert "row 4 of 5" in rows[3] and "target_id is empty" in rows[3]
        assert "row 5 of 5" in rows[4]
        assert "pct is outside the accepted 0 < pct <= 100" in rows[4]
        for line in rows:
            assert "the save is corrupt" in line, (
                "no writer in this codebase produces these shapes, so "
                "the message must say the save is corrupt rather than "
                "imply routine filtering"
            )

    def test_partial_loss_is_no_longer_hidden_behind_a_cheerful_info(self, wirelog):
        payload = [GOOD, "not-a-dict", None]
        mgr = SmartWireManager()
        assert mgr.import_wires(payload) == 1
        assert _same_wires(_accepted(mgr), {"A": {"B": 25.0}})
        assert any("imported 1 wire(s)" in m for m in _infos(wirelog))
        head = [m for m in (HEADLINE.search(w) for w in _warnings(wirelog)) if m]
        assert len(head) == 1, (
            "the INFO alone is true and reassuring; without the "
            "headline beside it two lost routes stay invisible"
        )
        assert tuple(int(g) for g in head[0].groups()) == (1, 3, 2, 2, 0, 0)

    def test_the_consequence_is_stated_in_operator_terms(self, wirelog):
        SmartWireManager().import_wires([{"source_id": "A", "pct": 1.0}])
        head = [w for w in _warnings(wirelog) if HEADLINE.search(w)]
        assert len(head) == 1
        assert "configured transfer route" in head[0]
        assert "fold profit is never divided" in head[0]
        assert "wired_in never grows" in head[0]


OPERATOR_SHAPED = [
    {
        "source_id": f"bot{i:02d}",
        "target_id": f"bot{(i + 7) % 37:02d}",
        "pct": float(5 + (i % 20)),
    }
    for i in range(33)
]


class TestNoFalseAlarm:
    """A guard-clean payload leaves `import_wires` with no WARNING at all.

    `OPERATOR_SHAPED`, an export round trip, a repeated import and an empty
    list each import whole.
    """

    def test_a_real_export_import_round_trip_says_nothing_new(self, wirelog):
        source = SmartWireManager()
        for i in range(12):
            source.register_wire(f"src{i}", f"tgt{i}", 5.0 + i)
        snapshot = source.export_wires()
        assert len(snapshot) == 12

        wirelog.clear()
        restored = SmartWireManager()
        assert restored.import_wires(snapshot) == 12
        assert _warnings(wirelog) == [], "a well-formed topology produced a new line"
        assert any("imported 12 wire(s)" in m for m in _infos(wirelog))
        assert _accepted(restored) == _accepted(source)

    def test_an_operator_sized_topology_says_nothing_new(self, wirelog):
        mgr = SmartWireManager()
        assert mgr.import_wires(list(OPERATOR_SHAPED)) == 33
        assert (
            _warnings(wirelog) == []
        ), "33 guard-clean rows must produce no warning at all"

    def test_re_importing_the_same_snapshot_stays_silent(self, wirelog):
        mgr = SmartWireManager()
        mgr.import_wires(list(OPERATOR_SHAPED))
        wirelog.clear()
        assert mgr.import_wires(list(OPERATOR_SHAPED)) == 33
        assert _warnings(wirelog) == [], "idempotent re-import must not start warning"

    def test_an_empty_topology_says_nothing(self, wirelog):
        assert SmartWireManager().import_wires([]) == 0
        assert _warnings(wirelog) == []
        assert _infos(wirelog) == []


class TestTheEmitterIsUnchanged:
    """`import_wires` emits `PIN` once, with `expected` set to the offered count.

    A lossy payload leaves the record with `ok` False, and a non-list argument
    emits nothing.
    """

    @pytest.mark.parametrize(
        ("label", "payload", "want", "count"),
        ROW_SHAPES,
        ids=[r[0] for r in ROW_SHAPES],
    )
    def test_expected_is_always_the_offered_count(
        self, sink, label, payload, want, count
    ):
        n = SmartWireManager().import_wires(list(payload))
        rec = sink.records(PIN)
        assert len(rec) == 1, f"{label}: the pin did not fire once"
        assert rec[0].expected == len(
            payload
        ), f"{label}: expected must be the offered count"
        assert rec[0].actual == n == count

    def test_the_pin_passes_on_a_clean_restore(self, sink):
        SmartWireManager().import_wires(list(OPERATOR_SHAPED))
        rec = sink.records(PIN)[0]
        assert rec.expected == 33
        assert rec.actual == 33
        assert rec.ok is True

    def test_the_pin_can_still_fail(self, sink):
        payload = [GOOD, "not-a-dict", {"target_id": "E", "pct": 1.0}]
        SmartWireManager().import_wires(payload)
        rec = sink.records(PIN)[0]
        assert rec.expected == 3
        assert rec.actual == 1
        assert rec.ok is False, (
            "a lossy restore that reads as a pass is a pin that cannot " "fail"
        )

    def test_the_pin_carries_the_source_count(self, sink):
        SmartWireManager().import_wires(
            [GOOD, {"source_id": "H", "target_id": "I", "pct": 5.0}]
        )
        assert sink.records(PIN)[0].context["sources"] == 2

    @pytest.mark.parametrize(
        ("label", "arg"), NON_LIST_ARGS, ids=[r[0] for r in NON_LIST_ARGS]
    )
    def test_a_non_list_argument_still_emits_nothing(self, sink, label, arg):
        assert SmartWireManager().import_wires(arg) == 0
        assert sink.count(PIN) == 0, (
            "the early return above the emitter is unchanged behaviour "
            "and is pinned here so a later edit cannot move it quietly"
        )


class TestTheNanPinIsNowAFixPin:
    """`import_wires` refuses a nan pct, counts it unroutable and names it unordered.

    An accepted nan would reach `distribute_fold_profit`, where the dust floor
    does not stop it.
    """

    def test_nan_pct_is_now_refused_counted_and_named(self, wirelog):
        row = {"source_id": "A", "target_id": "B", "pct": float("nan")}
        mgr = SmartWireManager()
        assert mgr.import_wires([row]) == 0, (
            "nan fails both `pct <= 0` and `pct > 100` because it is "
            "unordered; the guard now tests for it directly"
        )
        assert _accepted(mgr) == {}
        warns = _warnings(wirelog)
        assert len(warns) == 2, (
            "one per-row line and one headline; a refused row that is "
            "not reported is the silence this file exists to remove"
        )
        assert "unordered" in warns[0], (
            "the line must name nan as unordered rather than as "
            "'outside 0 < pct <= 100', which it is not"
        )
        assert tuple(int(g) for g in HEADLINE.search(warns[1]).groups()) == (
            0,
            1,
            1,
            0,
            0,
            1,
        )


class TestKnownDefectsArePinnedNotFixed:
    """`import_wires` counts rows, and two rows for one route return 2.

    The stored topology holds the one route at the second row's pct, and no
    row was lost.
    """

    def test_duplicate_rows_are_still_counted_twice(self, wirelog):
        payload = [
            {"source_id": "A", "target_id": "B", "pct": 25.0},
            {"source_id": "A", "target_id": "B", "pct": 40.0},
        ]
        mgr = SmartWireManager()
        assert mgr.import_wires(payload) == 2, (
            "DEFECT PIN: two rows accepted, one route exists; the "
            "count is of ROWS, not of routes"
        )
        assert _accepted(mgr) == {"A": {"B": 40.0}}
        assert _warnings(wirelog) == [], "both rows were accepted, so nothing was lost"
