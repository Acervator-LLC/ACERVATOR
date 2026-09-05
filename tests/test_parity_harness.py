"""v3.24.5 — pin tests for sim vs live trade parity harness.

THE TWELVE PINS BELOW PASSED ON A BROKEN READER, and the reason is
written into their own fixture. `_sim` builds a `SimpleNamespace` with
`.symbol`, `.side`, `.amount` and `.timestamp` in SECONDS — the
`FleetSimExchange` shape. `TabletBackend` replaced that class in
v3.24.84 and appends ccxt DICTS stamped in MILLISECONDS. `getattr` on
a dict does not read a key and, given a default, never raises, so every
field of a real sim fill read back as its default and every timestamp
read back as 1970.

The pins never saw it because they never fed the harness the shape the
Simulator actually produces. The tests at the bottom of this file feed
it a REAL `TabletBackend` tape, and they assert VALUES rather than the
existence of a report — the defect's output was a valid-looking report
full of zeros, and zero is a legal value.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.exchange.tablet_backend import TabletBackend  # noqa: E402
from src.trading.stone_tablets.parity_harness import (  # noqa: E402
    MS_PER_S,
    compare_trades,
    format_report_lines,
)


def _live(ts: float, sym: str, side: str, amt: float = 1.0) -> dict:
    return {"timestamp": ts, "symbol": sym, "side": side, "amount": amt, "price": 100.0}


def _sim(ts: float, sym: str, side: str, amt: float = 1.0):
    """OrderSide str is fine — harness handles both enum + str."""
    t = SimpleNamespace()
    t.timestamp = ts
    t.symbol = sym
    t.side = side  # "BUY"/"SELL"
    t.amount = amt
    return t


def test_exact_match_produces_matched_only():
    live = [_live(1000.0, "BTC/USD", "BUY", 1.0)]
    sim = [_sim(1000.0, "BTC/USD", "BUY", 1.0)]
    r = compare_trades(live, sim, tolerance_s=300)
    assert len(r.matched) == 1
    assert len(r.live_only) == 0
    assert len(r.sim_only) == 0
    assert r.matched[0].drift_s == 0.0


def test_within_tolerance_still_matches():
    live = [_live(1000.0, "BTC/USD", "BUY")]
    sim = [_sim(1250.0, "BTC/USD", "BUY")]  # 250s drift
    r = compare_trades(live, sim, tolerance_s=300)
    assert len(r.matched) == 1
    assert r.matched[0].drift_s == 250.0


def test_outside_tolerance_produces_live_only_and_sim_only():
    live = [_live(1000.0, "BTC/USD", "BUY")]
    sim = [_sim(2000.0, "BTC/USD", "BUY")]  # 1000s drift > 300s
    r = compare_trades(live, sim, tolerance_s=300)
    assert len(r.matched) == 0
    assert len(r.live_only) == 1
    assert len(r.sim_only) == 1


def test_side_mismatch_never_matches():
    live = [_live(1000.0, "BTC/USD", "BUY")]
    sim = [_sim(1000.0, "BTC/USD", "SELL")]
    r = compare_trades(live, sim, tolerance_s=300)
    assert len(r.matched) == 0
    assert len(r.live_only) == 1
    assert len(r.sim_only) == 1


def test_symbol_mismatch_never_matches():
    live = [_live(1000.0, "BTC/USD", "BUY")]
    sim = [_sim(1000.0, "ETH/USD", "BUY")]
    r = compare_trades(live, sim, tolerance_s=300)
    assert len(r.matched) == 0


def test_greedy_first_come_first_served_when_multiple_candidates():
    """Two live trades on same symbol/side, three sim candidates —
    the closest-in-time pair matches first, second matches with the
    next closest, third sim = sim_only."""
    live = [
        _live(1000.0, "BTC/USD", "BUY"),
        _live(2000.0, "BTC/USD", "BUY"),
    ]
    sim = [
        _sim(1050.0, "BTC/USD", "BUY"),  # closest to live #1
        _sim(2100.0, "BTC/USD", "BUY"),  # closest to live #2
        _sim(3500.0, "BTC/USD", "BUY"),  # no live partner
    ]
    r = compare_trades(live, sim, tolerance_s=300)
    assert len(r.matched) == 2
    assert len(r.live_only) == 0
    assert len(r.sim_only) == 1


def test_per_symbol_matrix_aggregates_correctly():
    live = [_live(1000.0, "BTC/USD", "BUY"), _live(1100.0, "ETH/USD", "SELL")]
    sim = [_sim(1000.0, "BTC/USD", "BUY")]
    r = compare_trades(live, sim, tolerance_s=300)
    m = r.per_symbol_counts()
    assert m["BTC/USD"]["matched"] == 1
    assert m["ETH/USD"]["live_only"] == 1
    assert m["ETH/USD"]["matched"] == 0


def test_match_rate_zero_when_no_live():
    r = compare_trades([], [], tolerance_s=300)
    assert r.match_rate == 0.0
    assert r.total_live == 0


def test_match_rate_100_when_all_matched():
    live = [_live(1000.0, "BTC/USD", "BUY"), _live(2000.0, "BTC/USD", "SELL")]
    sim = [_sim(1000.0, "BTC/USD", "BUY"), _sim(2000.0, "BTC/USD", "SELL")]
    r = compare_trades(live, sim, tolerance_s=300)
    assert r.match_rate == 100.0


def test_window_filter_excludes_out_of_range_trades():
    live = [_live(500.0, "BTC/USD", "BUY"), _live(1500.0, "BTC/USD", "BUY")]
    sim = [_sim(500.0, "BTC/USD", "BUY"), _sim(1500.0, "BTC/USD", "BUY")]
    # Only the 1500 pair should be in-window
    r = compare_trades(
        live, sim, tolerance_s=300, window_since_ts=1000.0, window_until_ts=2000.0
    )
    assert len(r.matched) == 1
    assert r.matched[0].live_ts == 1500.0


def test_format_report_lines_summary_present():
    live = [_live(1000.0, "BTC/USD", "BUY")]
    sim = [_sim(1000.0, "BTC/USD", "BUY")]
    r = compare_trades(live, sim)
    out = format_report_lines(r)
    assert any("Parity:" in line for line in out)
    assert any("Match rate" in line for line in out)


def test_format_report_lines_empty_message_when_nothing():
    r = compare_trades([], [])
    out = format_report_lines(r)
    assert any("nothing to compare" in line for line in out)


# ── a real tape, read the way the Simulator produces it ──────────

T0_MS = 1_776_778_500_000  # a 2026 instant on the tablets' 5m grid
STEP_MS = 300_000
SEED_USD = 10_000.0


def _tape_rows(n: int = 12, px0: float = 100.0) -> list[list[float]]:
    """A synthetic tablet on the 5-minute grid the real ones sit on."""
    out: list[list[float]] = []
    px = px0
    for i in range(n):
        px *= 1.0 + ((i % 5) - 2) * 0.003
        out.append([float(T0_MS + i * STEP_MS), px, px * 1.01, px * 0.99, px, 50.0])
    return out


def _traded_tape() -> tuple[TabletBackend, list[dict]]:
    """Return a tape that has FILLED, plus the fills its observer saw.

    THE SECOND WITNESS. The returned list comes from
    ``TabletBackend.on_trade``, the callback the backend invokes as it
    settles a fill. ``fetch_my_trades()`` is a DIFFERENT code path over
    the same events. Nothing below is compared against a written-down
    number: the expected instants, symbols and amounts are all read off
    the callback, and the harness is asked to reproduce them from the
    reader path.
    """
    rows = _tape_rows()
    tape = TabletBackend({"CHIP/USD": rows}, balances={"USD": SEED_USD})
    seen: list[dict] = []
    tape.on_trade(seen.append)
    for i in range(6):
        assert tape.step() is True, f"the tape ran out at step {i}"
        side = "buy" if i % 2 == 0 else "sell"
        tape.create_order("CHIP/USD", "market", side, 1.5)
    return tape, seen


def _live_from(observed: list[dict]) -> list[dict]:
    """The live-history shape, built from what the tape actually did.

    ``fetch_all_history_chunked`` hands ``compare_trades`` unix
    SECONDS. The tape stamps MILLISECONDS. Converting HERE, on the
    witness side, is what makes the assertions below a test of the
    harness's own conversion rather than a restatement of it.
    """
    return [
        {
            "timestamp": float(t["timestamp"]) / MS_PER_S,
            "symbol": t["symbol"],
            "side": t["side"],
            "amount": float(t["amount"]),
            "price": float(t["price"]),
        }
        for t in observed
    ]


def test_the_tape_fills_before_anything_is_measured_over_it() -> None:
    """THE INSTRUMENT'S POSITIVE CONTROL.

    Every assertion after this one reads numbers produced by a tape
    that traded. A tape that filled nothing would make the parity
    report an empty-set comparison, and 0 matched out of 0 live is
    exactly the shape the defect produced. So the population is
    measured before anything is measured over it.
    """
    tape, observed = _traded_tape()
    assert len(observed) >= 2, (
        f"the tape settled {len(observed)} fill(s); the parity "
        "assertions below cannot tell a working reader from a broken "
        "one over an empty tape"
    )
    assert len(tape.fetch_my_trades()) == len(observed), (
        f"the tape's reader path returned "
        f"{len(tape.fetch_my_trades())} fill(s) and its observer saw "
        f"{len(observed)}; one of the two is not watching the run"
    )


def test_a_tape_fill_matches_its_own_live_partner() -> None:
    """THE MEASUREMENT THIS FILE EXISTS FOR, on the real shape.

    Live history built from the tape's own fills must reproduce at
    100%. It is the strongest statement available here: the two sides
    describe the same events, so anything below 100% is the reader and
    not the strategy.

    On the broken reader every dict read back ``symbol=""`` and
    ``timestamp=0.0``, so no (symbol, side) key ever reached a live
    trade and this reported 0.0%.
    """
    tape, observed = _traded_tape()
    sim_trades = tape.fetch_my_trades()
    live = _live_from(observed)

    report = compare_trades(live, sim_trades)

    assert report.match_rate == 100.0, (
        f"{len(report.matched)} of {report.total_live} live trade(s) "
        f"matched ({report.match_rate:.1f}%) against "
        f"{len(sim_trades)} sim fill(s) describing the SAME events; "
        f"live_only={len(report.live_only)} "
        f"sim_only={len(report.sim_only)}"
    )
    assert report.live_only == []
    assert report.sim_only == []


def test_the_matched_pair_carries_the_tape_own_values() -> None:
    """VALUES, not the existence of a report.

    A report object exists whatever the reader returned. These are the
    three fields the defect zeroed: symbol, timestamp and amount.
    """
    tape, observed = _traded_tape()
    report = compare_trades(_live_from(observed), tape.fetch_my_trades())
    assert len(report.matched) == len(observed)

    pairs = zip(
        sorted(report.matched, key=lambda m: m.sim_ts),
        sorted(observed, key=lambda t: int(t["timestamp"])),
    )
    for match, fill in pairs:
        assert match.symbol == fill["symbol"], (
            f"the report names symbol {match.symbol!r}; the tape "
            f"filled {fill['symbol']!r}"
        )
        assert match.symbol != ""
        assert match.sim_amount == float(fill["amount"]) != 0.0, (
            f"the report read amount {match.sim_amount} from a fill of "
            f"{fill['amount']}"
        )
        assert match.sim_ts == float(fill["timestamp"]) / MS_PER_S, (
            f"the report placed the fill at {match.sim_ts} s; the tape "
            f"stamped it {fill['timestamp']} ms"
        )
        assert match.drift_s == 0.0


# ── the millisecond seam ─────────────────────────────────────────


def test_the_two_sim_shapes_land_on_the_same_instant() -> None:
    """THE SEAM, PINNED.

    A dict stamped in ms and an object stamped with the SAME instant in
    seconds are the same event, so the harness must place them at the
    same point on the live timeline. A wrong unit here does not raise;
    it moves the fill and prints a plausible percentage.
    """
    ts_ms = T0_MS + 4 * STEP_MS
    as_dict = {
        "timestamp": ts_ms,
        "symbol": "CHIP/USD",
        "side": "buy",
        "amount": 1.5,
        "price": 100.0,
    }
    as_object = _sim(ts_ms / MS_PER_S, "CHIP/USD", "BUY", 1.5)
    live = [_live(ts_ms / MS_PER_S, "CHIP/USD", "BUY", 1.5)]

    from_dict = compare_trades(live, [as_dict], tolerance_s=300)
    from_object = compare_trades(live, [as_object], tolerance_s=300)

    assert (
        len(from_dict.matched) == 1
    ), "the ms-stamped dict did not reach its own live partner"
    assert len(from_object.matched) == 1
    assert from_dict.matched[0].sim_ts == from_object.matched[0].sim_ts
    assert from_dict.matched[0].drift_s == 0.0


def test_a_millisecond_stamp_read_as_seconds_reaches_nothing() -> None:
    """THE FAILURE DIRECTION OF THE SEAM.

    The same fill, handed over in the object shape that declares
    SECONDS while carrying MILLISECONDS. It lands about 54,000 years
    from its partner, so nothing matches. This is what an unconverted
    read produces, and it is why the unit is stated per shape rather
    than inferred.
    """
    ts_ms = T0_MS + 4 * STEP_MS
    live = [_live(ts_ms / MS_PER_S, "CHIP/USD", "BUY", 1.5)]
    mis_stamped = [_sim(float(ts_ms), "CHIP/USD", "BUY", 1.5)]

    report = compare_trades(live, mis_stamped, tolerance_s=300)

    assert report.matched == []
    assert len(report.live_only) == 1
    assert len(report.sim_only) == 1
    assert report.match_rate == 0.0


def test_the_window_filter_reads_the_dict_in_milliseconds() -> None:
    """The window bounds are SECONDS on both sides of the comparison.

    Read without converting, every ms-stamped fill sits far above any
    ``window_until_ts`` and the filter drops the whole tape — a silent
    empty set, which reports as 0% reproduction.
    """
    early_ms = T0_MS
    late_ms = T0_MS + 10 * STEP_MS
    sim = [
        {"timestamp": early_ms, "symbol": "CHIP/USD", "side": "buy", "amount": 1.0},
        {"timestamp": late_ms, "symbol": "CHIP/USD", "side": "buy", "amount": 1.0},
    ]
    live = [_live(late_ms / MS_PER_S, "CHIP/USD", "BUY", 1.0)]

    report = compare_trades(
        live,
        sim,
        tolerance_s=300,
        window_since_ts=(early_ms + STEP_MS) / MS_PER_S,
        window_until_ts=(late_ms + STEP_MS) / MS_PER_S,
    )

    assert len(report.matched) == 1, (
        "the in-window ms fill did not survive a window stated in " "seconds"
    )
    assert report.matched[0].sim_ts == late_ms / MS_PER_S
    assert report.sim_only == [], "the out-of-window fill was not filtered out"


def test_the_per_symbol_matrix_names_the_dict_symbol() -> None:
    """An unmatched sim fill has to be attributable.

    Read through the object path a dict yields ``""``, so every
    over-triggered sim fill piled up under one nameless row and the
    operator could not see WHICH bot over-triggered.
    """
    sim = [{"timestamp": T0_MS, "symbol": "CHIP/USD", "side": "buy", "amount": 1.0}]
    report = compare_trades([], sim, tolerance_s=300)
    matrix = report.per_symbol_counts()
    assert "CHIP/USD" in matrix, f"the sim-only fill was filed under {list(matrix)}"
    assert matrix["CHIP/USD"]["sim_only"] == 1


# ── why the two fixes had to land together ───────────────────────


def _legacy_object_shaped_read(trade: Any) -> dict:
    """The reader exactly as it stood before this fix.

    Reproduced here rather than imported, because the point is what it
    DID. ``getattr`` with a default over a dict returns the default and
    never raises, so this is the silent-zero path.
    """
    return {
        "symbol": str(getattr(trade, "symbol", "")),
        "ts": float(getattr(trade, "timestamp", 0)),
        "amount": float(getattr(trade, "amount", 0)),
    }


def test_the_caller_fix_alone_would_report_a_false_match_rate() -> None:
    """THE COUPLING. DO NOT SPLIT THESE TWO FIXES.

    The panel used to hand ``compare_trades`` an empty list, because it
    pulled ``_trades`` off a ``CCXTConnector`` that has no such
    attribute. That produced an HONEST message: "sim produced 0 trades
    — 0% reproduction". Wrong about the run, right about itself.

    Point the panel at the real tape while this reader still reads the
    object shape, and the empty-list branch is no longer taken. The
    harness then receives N real fills, reads every field as a default,
    and prints "0.0% reproduction" over N sim trades it never read. The
    honest failure becomes a measurement-shaped lie, and the lie is the
    more expensive of the two.

    Both halves are asserted below on the same tape: what the old
    reader saw, and what a report built from it would have claimed.
    """
    tape, observed = _traded_tape()
    sim_trades = tape.fetch_my_trades()
    live = _live_from(observed)
    assert len(sim_trades) >= 2

    degraded = [_legacy_object_shaped_read(t) for t in sim_trades]
    assert {d["symbol"] for d in degraded} == {""}, (
        "the pre-fix reader is reproduced incorrectly here; it read "
        "every dict field as its default"
    )
    assert {d["ts"] for d in degraded} == {
        0.0
    }, "every fill read back at the epoch, not at its tablet instant"
    assert {d["amount"] for d in degraded} == {0.0}

    # What the panel prints with only the caller fixed: a report over a
    # non-empty sim set, so the honest zero-trades branch is never reached.
    as_the_old_reader_saw_them = [
        _sim(d["ts"], d["symbol"], "", d["amount"]) for d in degraded
    ]
    false_report = compare_trades(live, as_the_old_reader_saw_them)
    assert false_report.total_sim == len(sim_trades), (
        "the false report must be built over the SAME number of sim "
        "trades the panel now hands over — that is what makes it look "
        "like a measurement rather than a failure"
    )
    assert false_report.match_rate == 0.0
    assert "0.0%" in "\n".join(format_report_lines(false_report))

    # The same tape, through the reader as it now stands.
    honest = compare_trades(live, sim_trades)
    assert honest.match_rate == 100.0, (
        f"{honest.match_rate:.1f}% — the fixed reader must reproduce "
        "the tape's own fills, or the coupling argument above rests on "
        "nothing"
    )
