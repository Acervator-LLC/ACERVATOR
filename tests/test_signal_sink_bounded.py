"""signals/session.jsonl must not grow without limit.

WHAT WAS MEASURED
=================
``~/.acervator_logs/signals/session.jsonl`` on 2026-08-13, read
straight off the operator's disk:

    2,445,435,093 bytes        4,942,000 records
    26 distinct signal names   32 distinct (name, site) pairs
    4 process runs             32.2 hours of ACTIVE process time
    72.5 MB per active hour    494.8 bytes per record

`SignalSink.flush` appended and nothing ever checked the size, and
``install_process_sink`` stamps a CONSTANT file name — so the comment
that said "one file per process" was wrong in effect: every process
appends to the same file, for ever. The 4 runs above are
distinguishable only by `seq` restarting.

The bound is the one the rest of the platform already uses: 50 MB x 5,
the same as ``NDJSONWriter``, with the same ``Path.replace`` primitive
so the ``.4 -> .5`` shift cannot raise WinError 183.

WHAT A FAILURE HERE WOULD MEAN
==============================
`test_the_default_sink_is_bounded` red: the emitter network is back to
filling the disk, and the operator's stated target of a thousand pins
makes that arrive roughly forty times faster.

`test_no_record_is_lost_across_the_boundary` red: the module whose
entire thesis is "silence must be impossible" is losing records at its
own rotation, silently.

`test_a_full_ladder_still_rolls` red: the v3.23.5 lesson has been
un-learned and the sink stalls the way gate.log did.

`test_rotation_leaves_every_reader_working` red: rotation is the wrong
fix and a cap should not ship at all.

THE ROW CAP IS GONE. WHAT REPLACED IT
=====================================
`MAX_ROWS = 2_000_000` stopped `emit` outright once reached. MEASURED
on the same file: of the four process runs, TWO ended at exactly
2,000,000 rows — run 0 after 13.10 hours, run 2 after 12.99. A 13-hour
session went blind and kept running, which in the instrument the
operator is scaling to "a thousand eyes" is the worst failure available.

Rotation now bounds the disk, so the cap's stated reason is spent. But
it had a SECOND, unstated one: it was the only bound on `_all`.
MEASURED at 818.1 retained bytes per record over 20,000 real records
from this file, it was quietly a 1,560 MB memory ceiling, and removing
it outright would have put 2.9 GB of Signal objects in the GUI thread's
process after 24 hours at the measured 153,669 records/hour.

So the bound stays and the stop does not: `RETAIN_ROWS` windows what is
kept resident, and nothing windows what is recorded.

`test_a_long_session_keeps_emitting_past_the_window` red: the network
goes blind partway through a session, silently. That is the defect.

`test_memory_stays_bounded_while_the_disk_keeps_everything` red: the
process grows until it is killed.

`test_the_buffer_is_bounded_when_there_is_nowhere_to_write` red: the
`_all` bound is worthless, because `_buf` holds the same objects and
pins every record `_all` evicted.

`test_the_walk_touches_what_arrived_not_the_whole_window` red: the Qt
GUI thread pays for the length of the session twice a second.
"""
from __future__ import annotations

import json
import threading

import pytest

from src.core.signal_contract import (
    FILE_BACKUP_COUNT,
    MAX_FILE_BYTES,
    SignalSink,
    get_sink,
    install_process_sink,
    read_records,
    set_sink,
)


@pytest.fixture
def restore_process_sink():
    """`install_process_sink` installs a PROCESS-GLOBAL sink.

    A test that calls it and walks away leaves every later test in the
    same interpreter emitting into a tmp_path that has been deleted.
    """
    saved = get_sink()
    yield
    set_sink(saved)


def _census(path):
    """(total lines, distinct lines) across the current file and backups."""
    lines = []
    for name in [path.name] + ["%s.%d" % (path.name, i) for i in range(1, 9)]:
        p = path.parent / name
        if p.is_file():
            lines.extend(p.read_text(encoding="utf-8").splitlines())
    return len(lines), len(set(lines))


def _slots(path):
    return [i for i in range(1, 9)
            if (path.parent / ("%s.%d" % (path.name, i))).is_file()]


class _CountingRecord:
    """Stands in for a Signal and reports how often its `seq` was read.

    A timing assertion would be flaky and would prove only that one
    machine was fast. Counting the reads measures the ALGORITHM: a walk
    that stops at the watermark touches what arrived, a scan touches
    the whole window, and the two are separated by an exact integer.
    """

    def __init__(self, seq, tally):
        self._seq = seq
        self._tally = tally

    @property
    def seq(self):
        self._tally.append(1)
        return self._seq


class TestTheBoundExists:
    def test_the_default_sink_is_bounded(self, tmp_path):
        """THE unit. A sink built the way the platform builds one must
        carry a cap without the caller asking for it."""
        s = SignalSink(path=tmp_path / "session.jsonl")
        assert s._max_bytes == MAX_FILE_BYTES
        assert s._backup_count == FILE_BACKUP_COUNT

    def test_the_bound_matches_every_other_writer_on_the_platform(self):
        """50 MB x 5 is not a new number: it is what NDJSONWriter has
        used for trade.log, gate.log, diagnostics.log and voting.log
        since v3.23.5."""
        assert MAX_FILE_BYTES == 50 * 1024 * 1024
        assert FILE_BACKUP_COUNT == 5

    @pytest.mark.usefixtures("restore_process_sink")
    def test_the_process_sink_is_bounded_too(self, tmp_path):
        """`install_process_sink` is the only caller that matters — it
        is what `main()` runs, and its file is the 2.4 GB one."""
        sink = install_process_sink(log_dir=tmp_path)
        assert sink is not None
        assert sink.path == tmp_path / "session.jsonl"
        assert sink._max_bytes == MAX_FILE_BYTES
        assert sink._backup_count == FILE_BACKUP_COUNT

    @pytest.mark.usefixtures("restore_process_sink")
    def test_the_file_name_is_still_constant(self, tmp_path):
        """DELIBERATE, and the reason the comment needed correcting
        rather than the code. Stamping a pid or a clock into the name
        would trade an unbounded FILE for an unbounded NUMBER of files —
        the failure `acervator_watchdog.prune_postmortem_bundles`
        already exists to clean up after. One name, bounded by
        rotation, so a reader always knows where to look.
        """
        a = install_process_sink(log_dir=tmp_path)
        b = install_process_sink(log_dir=tmp_path)
        assert a is not None and b is not None
        assert a.path == b.path


class TestTheRolloverBoundary:
    def test_rotation_happens_at_the_cap(self, tmp_path):
        p = tmp_path / "session.jsonl"
        s = SignalSink(path=p, flush_every=1, max_bytes=20_000,
                       backup_count=5)
        for i in range(300):
            s.emit("ctl", actual=i)
        s.flush()
        assert _slots(p), "the cap was never enforced"
        assert p.stat().st_size < 20_000

    def test_no_record_is_lost_across_the_boundary(self, tmp_path):
        """Counted two ways: raw lines, and the `seq` field, which is
        monotonic per sink. A gap in seq is a lost record even if the
        line count happened to work out."""
        p = tmp_path / "session.jsonl"
        s = SignalSink(path=p, flush_every=1, max_bytes=20_000,
                       backup_count=5)
        for i in range(300):
            s.emit("ctl", actual=i)
        s.flush()
        total, distinct = _census(p)
        assert total == 300, "records were lost at a rollover"
        assert distinct == 300, "records were duplicated at a rollover"

        seqs = []
        for name in [p.name] + ["%s.%d" % (p.name, i) for i in range(1, 9)]:
            f = tmp_path / name
            if f.is_file():
                for line in f.read_text(encoding="utf-8").splitlines():
                    seqs.append(json.loads(line)["seq"])
        assert sorted(seqs) == list(range(1, 301))

    def test_a_full_ladder_still_rolls(self, tmp_path):
        """THE .4 -> .5 CONDITION — every slot occupied, then a forced
        rollover. This is the state that stalled the gate.log writer for
        three days and produced 350,470 warnings."""
        p = tmp_path / "session.jsonl"
        before = {}
        for i in range(1, 6):
            f = tmp_path / ("session.jsonl.%d" % i)
            f.write_bytes(b'{"slot":%d}\n' % i)
            before[i] = f.read_bytes()
        p.write_bytes(b"x" * 30_000)

        s = SignalSink(path=p, flush_every=1, max_bytes=20_000,
                       backup_count=5)
        s.emit("ctl", actual="crosses a full ladder")
        s.flush()

        assert (tmp_path / "session.jsonl.1").read_bytes() == b"x" * 30_000
        for i in range(1, 5):
            assert (tmp_path / ("session.jsonl.%d" % (i + 1))).read_bytes() \
                == before[i], "slot %d did not shift to %d" % (i, i + 1)
        assert _slots(p) == [1, 2, 3, 4, 5]
        assert len(p.read_text(encoding="utf-8").strip().splitlines()) == 1
        assert s.health()["rotate_failures"] == 0

    def test_nothing_is_kept_beyond_the_backup_count(self, tmp_path):
        p = tmp_path / "session.jsonl"
        s = SignalSink(path=p, flush_every=1, max_bytes=8_000,
                       backup_count=3)
        for i in range(400):
            s.emit("ctl", actual=i)
        s.flush()
        assert _slots(p) == [1, 2, 3]
        assert not (tmp_path / "session.jsonl.4").exists()

    def test_rotation_can_be_switched_off_explicitly(self, tmp_path):
        """The control for every assertion above. If a sink with
        `max_bytes=0` ALSO rotated, none of them would be evidence that
        the cap is what causes rotation."""
        p = tmp_path / "session.jsonl"
        s = SignalSink(path=p, flush_every=1, max_bytes=0)
        for i in range(300):
            s.emit("ctl", actual=i)
        s.flush()
        assert _slots(p) == []
        assert p.stat().st_size > 20_000


class TestAFailedRotationKeepsTheRecords:
    def test_a_rotation_that_raises_still_writes_the_rows(self, tmp_path,
                                                          monkeypatch):
        """Missing the bound for one cycle is recoverable. Losing the
        batch is not, and a cap that silently stops being enforced is
        the same failure as a sink that silently stops recording — so
        it is counted in `health()`.
        """
        p = tmp_path / "session.jsonl"
        s = SignalSink(path=p, flush_every=1, max_bytes=20_000,
                       backup_count=5)
        for i in range(60):
            s.emit("ctl", actual=i)
        s.flush()

        def refuse():
            raise OSError(32, "held open by another process")

        monkeypatch.setattr(s, "_rotate_if_needed", refuse)
        s.emit("ctl", actual="written despite the failure")
        s.flush()

        assert s.health()["rotate_failures"] >= 1
        assert s.health()["dropped"] == 0
        assert "written despite the failure" in p.read_text(encoding="utf-8")


class TestRotationDoesNotBreakAReader:
    def test_rotation_leaves_every_reader_working(self, tmp_path):
        """EVERY READER OF THIS FILE, found by sweeping src/, tools/,
        tests/, main.py and acervator_watchdog.py:

          1. `signal_contract.read_records(path)` — the only code that
             opens the file. Its only callers are in the test suite.
          2. The GUI Console, `main_window._drain_signals`, which polls
             `sink.since(watermark)` IN MEMORY and never touches disk.

        Neither replays history from the file, so rotation is safe for
        both. This asserts it instead of asserting it in prose.
        """
        p = tmp_path / "session.jsonl"
        s = SignalSink(path=p, flush_every=1, max_bytes=20_000,
                       backup_count=5)
        for i in range(300):
            s.emit("ctl", actual=i, expected=i)
        s.flush()
        assert _slots(p), "no rotation happened, so nothing was proved"

        current = read_records(p)
        assert current, "read_records lost the current file"
        assert all(r.name == "ctl" for r in current)

        from_backups = 0
        for i in _slots(p):
            from_backups += len(read_records(
                tmp_path / ("session.jsonl.%d" % i)))
        assert len(current) + from_backups == 300, (
            "history was destroyed rather than moved")

        assert len(s.since(0)) == 300, (
            "the Console's in-memory reader was disturbed by a rotation")


class TestUnderLoad:
    def test_eight_threads_across_many_rollovers_lose_nothing(self, tmp_path):
        """`emit` is a module-level function with no thread affinity,
        called from scrumming_bot, ta_engine, smart_wire, ccxt_connector
        and the GUI, and `emit` calls `flush` itself when the buffer is
        due. Before this change `flush` did its file I/O with no lock
        held at all, so two threads could be inside the write block at
        once — and a rename racing an append raises on Windows and costs
        the whole batch."""
        p = tmp_path / "session.jsonl"
        # 10.3 — the ladder is deeper, and its depth is NAMED so the
        # capacity guard below compares against the real thing rather
        # than a literal that can drift away from it. Eight is the
        # ceiling `_census` and `_slots` scan to.
        LADDER_DEPTH = 8
        s = SignalSink(path=p, flush_every=1, max_bytes=40_000,
                       backup_count=LADDER_DEPTH)

        def worker(tid):
            for i in range(120):
                s.emit("ctl", actual={"t": tid, "i": i})

        threads = [threading.Thread(target=worker, args=(t,))
                   for t in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        s.flush()

        # 10.3 — THE CAPACITY PRECONDITION IS ASSERTED, NOT ASSUMED.
        #
        # This test was sized so 960 records at the record width of the
        # day only just fitted a 6-slot ladder. 10.3 added two fields,
        # records grew about a tenth, the oldest generation aged off the
        # end and `total` read 810. That is the ladder's bound working
        # exactly as designed — retirement, not loss — but the failure
        # was indistinguishable from the rename race this test exists to
        # catch.
        #
        # So the two facts the old assertion depended on in silence are
        # now checked out loud. Neither existed before, and the first of
        # them means a run that never rotated can no longer pass: the
        # old test asserted nothing about rotation at all.
        occupied = _slots(p)
        assert occupied, (
            "no rotation happened, so no rollover was exercised and the "
            "race this test is about was never reachable")
        assert len(occupied) < LADDER_DEPTH, (
            "the ladder overflowed: records aged off the end by design, "
            "so a short `total` below would mean retirement, not loss")
        total, distinct = _census(p)
        assert total == 960
        assert distinct == 960
        assert s.health()["dropped"] == 0
        assert s.health()["rotate_failures"] == 0


class TestTheEmitterNeverStops:
    """The row cap is gone. These pin what replaced it.

    ``MAX_ROWS = 2_000_000`` used to switch `emit` off for the rest of
    the process. MEASURED on the operator's own session.jsonl: of four
    process runs, TWO ended at exactly 2,000,000 rows -- run 0 after
    13.10 hours, run 2 after 12.99. A 13-hour session went blind and
    kept running.

    The window here is small so the eviction path is DRIVEN rather than
    described. It is the same path 350,000 takes; only the number
    differs.
    """

    def test_a_long_session_keeps_emitting_past_the_window(self, tmp_path):
        """THE unit. WHAT A FAILURE MEANS: the instrument the operator
        is scaling to a thousand eyes goes blind partway through a
        session and says nothing."""
        p = tmp_path / "session.jsonl"
        s = SignalSink(path=p, flush_every=1, retain_rows=100)
        returned = [s.emit("ctl", actual=i) for i in range(1000)]
        s.flush()

        assert all(r is not None for r in returned), (
            "emit refused a record; there is a row at which the "
            "instrument still switches itself off")
        assert [r.seq for r in returned] == list(range(1, 1001)), (
            "the sequence is not continuous, so records were skipped")
        assert s.health()["emitted"] == 1000

    def test_the_disk_still_holds_every_record(self, tmp_path):
        """Lifting the cap must not cost the record set. The FILE is
        the record set; memory is a window onto it."""
        p = tmp_path / "session.jsonl"
        s = SignalSink(path=p, flush_every=1, retain_rows=100)
        for i in range(1000):
            s.emit("ctl", actual=i)
        s.flush()
        total, distinct = _census(p)
        assert total == 1000, "records that were emitted never reached disk"
        assert distinct == 1000

    def test_memory_stays_bounded_while_the_disk_keeps_everything(
            self, tmp_path):
        """The cap's SECOND, unstated reason: it was the only bound on
        `_all`. MEASURED at 818.1 retained bytes per record, the
        2,000,000-row cap was a 1,560 MB ceiling, and lifting it
        without replacement would have put 2.9 GB of Signal objects in
        the GUI thread's process after 24 hours at the measured rate.

        WHAT A FAILURE MEANS: the process grows until it is killed."""
        p = tmp_path / "session.jsonl"
        s = SignalSink(path=p, flush_every=1, retain_rows=100)
        for i in range(1000):
            s.emit("ctl", actual=i)
        s.flush()

        assert len(s.records()) == 100, "the in-memory window is not bounded"
        assert s.health()["retained"] == 100
        assert s.health()["evicted"] == 900
        # The window holds the NEWEST, which is what a live reader wants.
        assert [r.actual for r in s.records()] == list(range(900, 1000))

    def test_an_evicted_record_is_not_reported_as_a_loss(self, tmp_path):
        """`evicted` and `dropped` mean different things and conflating
        them would make a healthy sink look like a lossy one. A record
        that aged out of memory is ON DISK."""
        p = tmp_path / "session.jsonl"
        s = SignalSink(path=p, flush_every=1, retain_rows=100)
        for i in range(1000):
            s.emit("ctl", actual=i)
        s.flush()
        assert s.health()["evicted"] == 900
        assert s.health()["dropped"] == 0

    def test_the_buffer_is_bounded_when_there_is_nowhere_to_write(self):
        """THE TRAP THE CAP WAS HIDING.

        `flush` deliberately does not drain `_buf` while `path` is None
        (v3.24.83: draining with nowhere to write destroyed 200 records
        a flush). So a pathless sink accumulates, and the row cap used
        to stop that by accident because `emit` returned before
        appending anywhere.

        `_buf` also holds the SAME objects as `_all`, so an unbounded
        buffer would pin every record `_all` had already evicted and
        the memory bound would be worthless.

        A buffer eviction IS a real loss -- that record never reached
        disk -- so it is counted in `dropped`, not in `evicted`."""
        s = SignalSink(path=None, flush_every=1, retain_rows=100)
        for i in range(1000):
            s.emit("ctl", actual=i)
        s.flush()                      # a no-op: there is no path

        assert s.health()["buffered"] == 100, (
            "the buffer grew without limit while there was nowhere to "
            "write, which pins every evicted record in memory too")
        assert s.health()["dropped"] == 900, (
            "records were lost from the buffer without being counted")

    def test_the_buffer_stays_bounded_across_a_flush(self, tmp_path):
        """`flush` swaps in a fresh buffer. Swapping in a plain list
        would leave the sink bounded until its first flush and
        unbounded for ever after -- which would pass every test that
        does not flush first."""
        p = tmp_path / "session.jsonl"
        s = SignalSink(path=p, flush_every=10_000, retain_rows=50)
        for i in range(60):
            s.emit("ctl", actual=i)
        s.flush()
        s.path = None                  # nowhere to write again
        for i in range(500):
            s.emit("ctl", actual=i)
        assert s.health()["buffered"] == 50, (
            "the post-flush buffer lost its bound")

    def test_health_does_not_report_a_cap_that_no_longer_exists(
            self, tmp_path):
        """`capped` meant "the emitter has stopped recording". Nothing
        stops it now, so a permanently-False key would be a promise no
        reader could falsify."""
        s = SignalSink(path=tmp_path / "session.jsonl", retain_rows=100)
        s.emit("ctl", actual=1)
        health = s.health()
        assert "capped" not in health
        # 10.3 — RESTATED, NOT RELAXED. `health()` gained `identities`
        # and `identity_overflow`, so the exact-set comparison is
        # re-pinned to the nine keys it now publishes. A key that
        # VANISHES still fails here, which is what the exact set was
        # protecting.
        #
        # And the invariant this test NAMES is stronger than any key
        # list, yet nothing asserted it: `capped` was bad because it was
        # a permanently-False BOOLEAN that no reader could falsify. So
        # no value in `health()` may be a bool at all. That catches the
        # next `capped` under any spelling; the old list could only
        # catch one called `capped`.
        # 10.3 phase 2 -- RESTATED AGAIN, NOT RELAXED. `health()`
        # gained `duration_rejected`, the count of durations the
        # ingress guard refused, so the exact set is re-pinned to
        # the ten keys it now publishes. A key that VANISHES still
        # fails here, which is what the exact set protects, and
        # the new one is an int, so the no-bool rule below still
        # covers it.
        # #62 -- RESTATED AGAIN, NOT RELAXED. `health()` gained the
        # seven digest keys when the second ladder arrived, so the
        # exact set is re-pinned to the seventeen it now publishes. A
        # key that VANISHES still fails here, which is what the exact
        # set protects.
        #
        # `digest_folded` is the one that MUST be in this dict. The
        # digest thins the loud emitters by about 97%, and a reader who
        # cannot see how much was folded is reading a thinned file as a
        # complete one -- the same class of mistake `capped` was. It is
        # an int, and `digest_interval` is a float, so the no-bool rule
        # below still covers every new key.
        assert set(health) == {"emitted", "buffered", "retained", "evicted",
                               "dropped", "rotate_failures", "identities",
                               "identity_overflow", "duration_rejected",
                               "path",
                               "digest_admitted", "digest_folded",
                               "digest_dropped", "digest_rotate_failures",
                               "digest_identity_overflow",
                               "digest_interval", "digest_path"}
        assert not any(isinstance(v, bool) for v in health.values()), (
            "a bool in health() is a promise no reader can falsify, "
            "which is exactly what `capped` was")

    def test_the_retention_window_cannot_be_zero(self, tmp_path):
        """A window of zero would be a sink that keeps nothing -- the
        silence this module exists to remove, reachable through a
        constructor argument."""
        s = SignalSink(path=tmp_path / "session.jsonl", retain_rows=0)
        assert s.emit("ctl", actual=1) is not None
        assert len(s.records()) == 1


class TestSinceCostsWhatArrived:
    """`since` is polled every 500 ms on the Qt GUI thread.

    `MainWindow._drain_signals` calls it on a QTimer at 500 ms. Its
    docstring already claimed "the cost is proportional to what
    arrived, not to the run", while the body scanned every retained
    record. At the old 2,000,000-row cap that was up to two million
    comparisons twice a second on the thread that also paints 37 bots.
    """

    def test_the_walk_touches_what_arrived_not_the_whole_window(self):
        """WHAT A FAILURE MEANS: the GUI thread pays for the length of
        the session on every poll, which is the unbounded-loop class
        that thread must not carry."""
        s = SignalSink(path=None, retain_rows=100_000)
        tally: list = []
        for i in range(1, 50_001):
            s._all.append(_CountingRecord(i, tally))

        out = s.since(49_995)

        assert [r._seq for r in out] == [49_996, 49_997, 49_998, 49_999,
                                         50_000]
        # Five arrivals plus the one that stops the walk. A scan of the
        # whole window would read 50,000.
        assert len(tally) <= 12, (
            "since() read %d records to return 5; it is scanning the "
            "whole window, so the GUI thread pays for session length "
            "on every poll" % len(tally))

    def test_the_walk_still_returns_everything_when_the_watermark_is_old(
            self):
        """The early stop must not truncate a caller that has fallen
        behind, or the Console silently skips records."""
        s = SignalSink(path=None, retain_rows=100)
        for i in range(50):
            s.emit("ctl", actual=i)
        assert len(s.since(0)) == 50
        assert len(s.since(25)) == 25
        assert s.since(50) == ()

    def test_records_evicted_from_the_window_are_not_re_served(self):
        """A watermark older than the window returns the window, not a
        crash and not a duplicate."""
        s = SignalSink(path=None, retain_rows=10)
        for i in range(100):
            s.emit("ctl", actual=i)
        out = s.since(0)
        assert len(out) == 10
        assert [r.actual for r in out] == list(range(90, 100))
