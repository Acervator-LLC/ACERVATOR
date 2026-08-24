"""A noisy emitter must not be able to evict a quiet one.

WHAT WAS MEASURED, READ-ONLY, ON THE OPERATOR'S OWN DISK
========================================================
``~/.acervator_logs`` on 2026-08-24, nothing written, nothing pruned:

    whole tree                 1,990,281,407 bytes   4,183 files
    sim/                         700,386,599
    trade/                       536,205,818
    signals/                     274,889,372
    console/                     271,722,225

All six generations of ``signals/session.jsonl``, every line parsed,
zero decode failures and zero nameless records (that is the control --
a per-emitter count is only a fact about the world if the reader read
every line):

    488,000 records      267.4 MB      125.4 MB per hour
    span of the WHOLE 300 MB ladder: 2.13 hours
    distinct emitters present: 28, against 77 pins in the tree
    top 5 emitters: 44.0% of the bytes
    top 8 emitters: 62.9% of the bytes

So 49 of 77 pins are not in the retained window at all, and the window
is two hours wide. The standing rule on this platform is that every
emitter is tracked and every pin carries a prediction beside its
observed value. An emitter whose records are evicted before anybody
reads them is an emitter that does not exist. THAT is the defect. The
disk footprint is the symptom.

WHY THE OLD POLICY CANNOT FIX ITSELF
====================================
The main ladder is bounded by BYTES and evicted by AGE, one whole file
at a time. Nothing in it decides what is worth keeping. Whatever
arrived most recently wins, so the emitters that write most decide how
far back every OTHER emitter can be read. A rare event from four hours
ago is gone; a routine indicator reading from four minutes ago is
retained.

WHAT A FAILURE IN THIS FILE MEANS
=================================
`test_the_current_policy_evicts_every_quiet_emitter` red:
    the reproduction has stopped reproducing. Either the fixture no
    longer models the real traffic, or something else changed the
    ladder. Re-measure before trusting anything else here -- every
    other test in this file is judged against this one.

`test_the_reader_finds_every_emitter_before_the_ladder_rolls` red:
    THE INSTRUMENT IS BROKEN, and the test above is reporting a fact
    about the reader rather than about the ladder. This is the positive
    control for it and it must be read first. A zero from a reader that
    cannot see anything is not a measurement.

`test_the_digest_keeps_every_quiet_emitter_the_main_ladder_lost` red:
    the fix is not fixing it. Quiet channels are being evicted again.

`test_no_observation_is_unaccounted_for` red:
    THE WORST ONE. The digest is dropping records silently. Every
    observation must be on the main ladder verbatim AND accounted for
    in the digest, either as its own line or inside the `folded` count
    on a later line of the same identity. A digest that quietly loses
    records is a thinned file that reads as a complete one.

`test_a_loud_emitter_cannot_outspend_a_quiet_one` red:
    the fairness is gone. This is the property the whole design turns
    on and it is meant to hold BY CONSTRUCTION, not because today's
    traffic happens to be shaped conveniently.

`test_breaking_the_rate_limit_puts_the_defect_straight_back` red:
    the tests above cannot fail, which makes them worthless. This one
    breaks the fix on purpose and requires the green assertions to go
    red naming the real problem.

NO LOGGER IS CAPTURED IN THIS FILE
==================================
Every test here drives `SignalSink` directly and asserts on files under
`tmp_path`. Nothing requests `caplog`, so the silent-capture guard has
nothing to judge -- and `caplog` would be blind here anyway, because
`logging_engine` sets ``acervator.propagate = False``. Nothing in this
file reads, writes or even resolves ``~/.acervator_logs``.
"""

import json

import pytest

from src.core import signal_contract as sc
from src.core.signal_contract import SignalSink, read_records


# ── the fixture: a few loud emitters and many quiet ones ────────────
#
# Shaped from the measurement in the module docstring rather than
# invented. The real file has fifteen identities emitting 3.6-4.0
# records per second on a live loop and a tail of identities emitting
# roughly twice an hour. The ratio is what matters, so it is kept and
# the wall-clock is compressed: the run below is 900 simulated seconds
# instead of two hours, and the ladders are 40 KB instead of 50 MB, so
# the same eviction happens in a test that finishes in seconds.

LOUD = 5
QUIET = 20
LOUD_PERIOD = 0.25     # seconds between emissions, per loud identity
QUIET_PERIOD = 300.0   # seconds between emissions, per quiet identity
SPAN = 900.0           # simulated seconds of traffic
LADDER_BYTES = 40_000
LADDER_BACKUPS = 5


def _loud_names():
    return [f"ta.07.004.postcondition.raw.loud_{i}" for i in range(LOUD)]


def _quiet_names():
    return [f"exchange.15.{i:03d}.invariant.quiet_{i}" for i in range(QUIET)]


def _schedule():
    """Every emission of the run as ``(t_seconds, name)``, time-ordered.

    Deterministic and computed, never sampled from a clock, so the
    reproduction is the same on every machine and in every run. The
    quiet emitters are given a 10-second phase offset so that no quiet
    emission lands on the run's final instant by coincidence -- an
    accident there would let a quiet name survive the main ladder and
    make the reproduction look flaky when it is not.
    """
    events = []
    for name in _loud_names():
        t = 0.0
        while t < SPAN:
            events.append((t, name))
            t += LOUD_PERIOD
    for name in _quiet_names():
        t = 10.0
        while t < SPAN:
            events.append((t, name))
            t += QUIET_PERIOD
    events.sort(key=lambda e: (e[0], e[1]))
    return events


class _Clock:
    """A monotonic clock the fixture drives by hand.

    ONE class, at module level, used by every test here. Two copies of
    it would be two chances for the reproduction and the falsifier to
    disagree about what time it is, and the whole comparison rests on
    them not disagreeing.

    `__getattr__` delegates every attribute this shim does not fake, so
    `signal_contract`'s other uses of `time` -- `time.time`,
    `time.get_clock_info` -- keep working untouched. The real `time`
    module is never mutated; only the module-level NAME inside
    `signal_contract` is rebound, and it is put back in a `finally`.
    """

    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def __getattr__(self, item):
        import time as _real
        return getattr(_real, item)


def _drive(sink, events, failing=None):
    """Feed `events` through `sink` on a simulated monotonic clock.

    The sink measures `dt` -- the interval since the previous emission
    of the same identity -- off `time.monotonic()` at emit time, and
    `dt` is what the digest rule accumulates. So the clock is the one
    thing this fixture must control, and it is controlled by replacing
    the module's own `time` reference for the duration of the call.
    The real `time` module is never mutated: the shim delegates every
    attribute it does not fake, and the original object is put back in
    a `finally`.

    `failing` names one identity whose records are made to carry
    ``ok=False``, for the test that drives the rejected verdict
    carve-out. Left at None every emission passes.
    """
    clock = _Clock()
    original = sc.time
    sc.time = clock
    try:
        for t, name in events:
            clock.now = t
            sink.emit(name, actual=t,
                      expected=(t + 1) if name == failing else t)
        sink.flush()
    finally:
        sc.time = original


def _ladder_files(path):
    """The current file and every backup still on disk, oldest last."""
    found = [path] if path.is_file() else []
    for i in range(1, LADDER_BACKUPS + 1):
        b = path.parent / f"{path.name}.{i}"
        if b.is_file():
            found.append(b)
    return found


def _names_on_disk(path):
    """Every emitter name readable from a whole ladder.

    Uses `read_records`, the platform's own reader, so this measures
    what a real consumer would find and not what a bespoke parser in a
    test would find.
    """
    names = set()
    for f in _ladder_files(path):
        for r in read_records(f):
            names.add(r.name)
    return names


def _digest_lines(path):
    """Every digest line as a dict, oldest ladder file last.

    Read with plain `json` rather than `read_records` because the field
    under test -- `folded` -- is one `read_records` does not model. That
    it IGNORES the field rather than choking on it is asserted
    separately.
    """
    out = []
    for f in _ladder_files(path):
        with f.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    out.append(json.loads(line))
    return out


@pytest.fixture
def events():
    return _schedule()


class TestTheDefectAsItStandsToday:
    """The eviction, reproduced here rather than pointed at."""

    def test_the_reader_finds_every_emitter_before_the_ladder_rolls(
            self, tmp_path, events):
        """POSITIVE CONTROL. Read this before the test below it.

        Same fixture, same reader, one difference: the ladder is large
        enough that nothing rotates. Every one of the 25 identities
        must come back. If this is red then `_names_on_disk` cannot see
        emitters at all, and the empty set the next test asserts on
        would be a claim about this reader rather than about eviction.
        """
        p = tmp_path / "session.jsonl"
        sink = SignalSink(path=p, flush_every=500,
                          max_bytes=0,            # rotation off
                          digest_interval=0.0)    # digest off
        _drive(sink, events)

        found = _names_on_disk(p)
        assert set(_quiet_names()) <= found, (
            "the reader cannot see quiet emitters even when nothing "
            "rotated — the instrument is broken, not the ladder")
        assert set(_loud_names()) <= found
        assert len(_ladder_files(p)) == 1, "nothing should have rotated"

    def test_the_current_policy_evicts_every_quiet_emitter(
            self, tmp_path, events):
        """THE DEFECT. Age-ordered, whole-file eviction loses them all.

        The loud emitters survive because they are still writing. The
        quiet ones are gone — not because they failed, not because
        they were less interesting, but because five identities wrote
        enough bytes to push the whole ladder past them.
        """
        p = tmp_path / "session.jsonl"
        sink = SignalSink(path=p, flush_every=500,
                          max_bytes=LADDER_BYTES,
                          backup_count=LADDER_BACKUPS,
                          digest_interval=0.0)    # the OLD policy
        _drive(sink, events)

        found = _names_on_disk(p)
        assert set(_loud_names()) <= found, (
            "the loud emitters must survive — if they did not, the "
            "ladder is not behaving as the operator's is")
        survivors = set(_quiet_names()) & found
        assert survivors == set(), (
            f"expected every quiet emitter to be evicted under the "
            f"current policy; {len(survivors)} survived: "
            f"{sorted(survivors)}")

    def test_the_retained_window_is_a_fraction_of_the_run(
            self, tmp_path, events):
        """Says WHY they were evicted, in the units that caused it.

        The ladder holds a fixed number of BYTES, so the window it
        covers shrinks as the loud emitters get louder. This asserts
        the window is a small fraction of the run — which is the
        operator's 2.13 hours out of a multi-day platform, reproduced.
        """
        p = tmp_path / "session.jsonl"
        sink = SignalSink(path=p, flush_every=500,
                          max_bytes=LADDER_BYTES,
                          backup_count=LADDER_BACKUPS,
                          digest_interval=0.0)
        _drive(sink, events)

        kept = []
        for f in _ladder_files(p):
            kept.extend(read_records(f))
        assert kept, "the ladder is empty; nothing can be concluded"
        window = max(r.actual for r in kept) - min(r.actual for r in kept)
        assert window < SPAN * 0.25, (
            f"the retained window is {window:.0f}s of a {SPAN:.0f}s run; "
            f"the reproduction assumes it is a small tail")


class TestTheDigestKeepsTheQuietChannels:
    """The fix, on the same fixture, at the same disk budget."""

    def _both_ladders(self, tmp_path, events, digest_interval=None):
        p = tmp_path / "session.jsonl"
        kwargs = dict(path=p, flush_every=500,
                      max_bytes=LADDER_BYTES,
                      backup_count=LADDER_BACKUPS,
                      digest_max_bytes=LADDER_BYTES,
                      digest_backup_count=LADDER_BACKUPS)
        if digest_interval is not None:
            kwargs["digest_interval"] = digest_interval
        sink = SignalSink(**kwargs)
        _drive(sink, events)
        return sink, p, sink.digest_path

    def test_the_digest_keeps_every_quiet_emitter_the_main_ladder_lost(
            self, tmp_path, events):
        """THE FIX. Same fixture, same bytes, every channel readable.

        The digest ladder is given exactly the budget the main ladder
        has — 40 KB x 5 — so this is not a comparison won by spending
        more disk. It is won by spending it fairly.
        """
        _, main, digest = self._both_ladders(tmp_path, events)

        lost = set(_quiet_names()) - _names_on_disk(main)
        assert lost, (
            "the main ladder did not lose anything, so this test is "
            "not measuring a rescue — check the reproduction above")

        kept = {d["name"] for d in _digest_lines(digest)}
        assert set(_quiet_names()) <= kept, (
            f"the digest lost quiet emitters too: "
            f"{sorted(set(_quiet_names()) - kept)}")
        assert set(_loud_names()) <= kept, (
            "the digest must keep the loud emitters as well — it thins "
            "them, it does not silence them")

    def test_the_digest_covers_far_more_of_the_run(self, tmp_path, events):
        """At equal disk, the digest's window is the whole run.

        This is the number the issue is really about: how far back a
        reader can see. Compared at the same byte budget so the
        comparison is honest.
        """
        _, main, digest = self._both_ladders(tmp_path, events)

        kept = []
        for f in _ladder_files(main):
            kept.extend(read_records(f))
        main_window = (max(r.actual for r in kept)
                       - min(r.actual for r in kept))

        lines = _digest_lines(digest)
        digest_window = (max(d["actual"] for d in lines)
                         - min(d["actual"] for d in lines))

        assert digest_window > main_window * 4, (
            f"digest window {digest_window:.0f}s is not meaningfully "
            f"wider than the main ladder's {main_window:.0f}s")

    def test_no_observation_is_unaccounted_for(self, tmp_path, events):
        """NOTHING IS DROPPED SILENTLY, and this is how that is checked.

        Every observation is on the main ladder verbatim. In the digest
        it is either its own line or one tick inside the `folded` count
        on a later line of the SAME identity. So the folded counts on
        disk, plus whatever is still pending for an identity that has
        not emitted again yet, must add up to exactly what was emitted.

        Checked from the FILE, not from the health dict, because the
        health dict is the thing that would be lying if this were
        wrong.
        """
        sink, _, digest = self._both_ladders(tmp_path, events)

        emitted = sink.health()["emitted"]
        on_disk = sum(d["folded"] for d in _digest_lines(digest))
        pending = sum(sink._digest_pending.values())
        assert on_disk + pending == emitted, (
            f"{emitted} observations emitted but the digest accounts "
            f"for {on_disk} written + {pending} pending")

        # And the health dict must agree with the file, so a reader who
        # only has one of them is not misled by it.
        h = sink.health()
        assert h["digest_admitted"] + h["digest_folded"] == emitted
        assert h["digest_dropped"] == 0
        assert h["digest_rotate_failures"] == 0

    def test_every_digest_line_declares_what_it_stands_for(
            self, tmp_path, events):
        """A thinned line that does not say it is thinned is a lie."""
        _, _, digest = self._both_ladders(tmp_path, events)

        lines = _digest_lines(digest)
        assert lines
        assert all("folded" in d for d in lines), (
            "a digest line with no `folded` field reads as a single "
            "observation whatever it stands for")
        assert all(d["folded"] >= 1 for d in lines)
        # The quiet emitters are under the rate limit, so every one of
        # their lines stands for exactly itself. If this ever fails the
        # rate limit is biting channels it was never meant to touch.
        quiet = {n: [d["folded"] for d in lines if d["name"] == n]
                 for n in _quiet_names()}
        for n, folds in quiet.items():
            assert folds and set(folds) == {1}, (
                f"quiet emitter {n} is being folded: {folds}")

    def test_a_loud_emitter_cannot_outspend_a_quiet_one(
            self, tmp_path, events):
        """THE FAIRNESS, asserted as a bound and not as a ratio.

        The rule admits at most one line per identity per
        `DIGEST_MIN_INTERVAL`, so an identity's line count is bounded
        by the CLOCK. A loud identity may therefore write no more than
        ``span / interval + 1`` lines however loud it is — which is
        what makes eviction-by-volume impossible rather than merely
        unlikely at today's traffic mix.
        """
        _, main, digest = self._both_ladders(tmp_path, events)
        lines = _digest_lines(digest)

        ceiling = SPAN / sc.DIGEST_MIN_INTERVAL + 1
        for n in _loud_names():
            wrote = sum(1 for d in lines if d["name"] == n)
            assert wrote <= ceiling, (
                f"{n} wrote {wrote} digest lines against a clock "
                f"ceiling of {ceiling:.0f}")

        # In the main ladder the same five identities own essentially
        # the whole file. That contrast is the point.
        kept = []
        for f in _ladder_files(main):
            kept.extend(read_records(f))
        loud_share = sum(1 for r in kept if r.name in set(_loud_names()))
        assert loud_share / len(kept) > 0.95

    def test_the_platform_reader_still_reads_a_digest_file(
            self, tmp_path, events):
        """`read_records` must survive the extra field, not choke on it.

        Read across the whole digest ladder, not just its current file:
        the digest rotates like everything else on this platform, and a
        reader that opened only the head would report an absence that
        is really a backup it did not open — which is this issue's own
        defect committed by the test.
        """
        _, _, digest = self._both_ladders(tmp_path, events)
        recs = []
        for f in _ladder_files(digest):
            recs.extend(read_records(f))
        assert recs
        assert {r.name for r in recs} >= set(_quiet_names())
        # The extra field is IGNORED, never fatal, and never invented:
        # `read_records` does not model `folded`, so a record it hands
        # back carries the field's absence rather than a made-up value.
        assert all(not hasattr(r, "folded") for r in recs)

    def test_the_digest_follows_a_path_assigned_after_construction(
            self, tmp_path):
        """`install_process_sink` assigns `path` AFTER building the sink.

        A stored digest path would be computed from a `path` of None
        and stay None for the life of the process, so the second ladder
        would exist in the constructor and nowhere else.
        """
        sink = SignalSink(flush_every=1)
        assert sink.digest_path is None
        sink.path = tmp_path / "session.jsonl"
        assert sink.digest_path == tmp_path / "session.digest.jsonl"
        sink.emit("ctl.00.001.invariant.control", actual=1, expected=1)
        sink.flush()
        assert sink.digest_path.is_file()

    def test_the_digest_can_be_switched_off(self, tmp_path, events):
        """A caller that wants only the verbatim file can have it."""
        p = tmp_path / "session.jsonl"
        sink = SignalSink(path=p, flush_every=500, max_bytes=LADDER_BYTES,
                          backup_count=LADDER_BACKUPS, digest_interval=0.0)
        _drive(sink, events)
        assert not sink.digest_path.exists()
        assert sink.health()["digest_admitted"] == 0
        assert sink.health()["digest_folded"] == 0


class TestDriveItRed:
    """A test that cannot fail is worthless. These break the fix."""

    def test_breaking_the_rate_limit_puts_the_defect_straight_back(
            self, tmp_path, events):
        """Remove the per-identity clock and the quiet channels die.

        `digest_interval` at an interval no emission can be shorter
        than is the rate limit switched off while the second ladder
        stays on — exactly the "just give it another file" fix. The
        loud emitters then fill the digest the same way they fill the
        main ladder, and the assertion that
        `test_the_digest_keeps_every_quiet_emitter_the_main_ladder_lost`
        makes must go RED. It is re-made here so the red is proved and
        not assumed.
        """
        p = tmp_path / "session.jsonl"
        sink = SignalSink(path=p, flush_every=500, max_bytes=LADDER_BYTES,
                          backup_count=LADDER_BACKUPS,
                          digest_max_bytes=LADDER_BYTES,
                          digest_backup_count=LADDER_BACKUPS,
                          digest_interval=1e-9)   # BROKEN ON PURPOSE
        _drive(sink, events)

        kept = {d["name"] for d in _digest_lines(sink.digest_path)}
        missing = set(_quiet_names()) - kept
        assert missing, (
            "with the rate limit removed the digest STILL kept every "
            "quiet emitter — then the rate limit is not what is saving "
            "them and the green test above proves nothing")

        with pytest.raises(AssertionError):
            assert set(_quiet_names()) <= kept, "quiet emitters lost"

    def test_a_verdict_carve_out_would_hand_the_digest_to_one_identity(
            self, tmp_path):
        """The rejected "keep every ok=False" rule, driven red.

        MEASURED on the operator's disk 2026-08-24:
        `bot.01.001.postcondition.capital_reservation` emitted 53,558
        records in the 2.13-hour window and every single one is
        `ok=False`. So "keep by interest" implemented as a verdict
        carve-out hands the whole digest to one identity and rebuilds
        the eviction inside its own fix.

        Reproduced here by exempting failures from the rate limit and
        showing the quiet channels go under.
        """
        # `flush_every` is 100 here rather than 500, and the reason is
        # a real property of this platform's rotation rather than a
        # tuning knob. Rotation is checked ONCE PER FLUSH, before the
        # batch is appended, so a ladder file can overrun its cap by up
        # to one whole batch. At 500 records a batch is larger than the
        # 40 KB cap, so each file would hold an entire batch and the
        # ladder would keep six of them — far more than the cap says.
        # A batch smaller than the cap makes the ladder behave as its
        # bytes claim, which is what this test needs to measure.
        p = tmp_path / "session.jsonl"
        sink = SignalSink(path=p, flush_every=100, max_bytes=LADDER_BYTES,
                          backup_count=LADDER_BACKUPS,
                          digest_max_bytes=LADDER_BYTES,
                          digest_backup_count=LADDER_BACKUPS)

        original = sink._digest_rows

        def _carve_out(rows):
            admitted = original(rows)
            already = {id(r) for r, _ in admitted}
            for r in rows:
                if r.ok is False and id(r) not in already:
                    admitted.append((r, 1))
            return admitted

        sink._digest_rows = _carve_out

        failing = "bot.01.001.postcondition.capital_reservation"
        evts = [(t, failing) for t in
                [i * LOUD_PERIOD for i in range(int(SPAN / LOUD_PERIOD))]]
        evts += [(t, n) for n in _quiet_names()
                 for t in [10.0 + k * QUIET_PERIOD
                           for k in range(int(SPAN / QUIET_PERIOD))]]
        evts.sort(key=lambda e: (e[0], e[1]))

        # The SAME driver the green tests use, on the same clock, with
        # one identity's records made to fail. Anything else here would
        # let the falsifier and the test it falsifies disagree about
        # the fixture rather than about the policy.
        _drive(sink, evts, failing=failing)

        kept = {d["name"] for d in _digest_lines(sink.digest_path)}
        assert set(_quiet_names()) - kept, (
            "the verdict carve-out did NOT evict the quiet emitters — "
            "then the reason for rejecting it is wrong and the "
            "constant's docstring must be corrected")

    def test_a_digest_write_failure_is_counted_and_not_silent(
            self, tmp_path, monkeypatch):
        """A digest that stopped being written must say so.

        Otherwise it is indistinguishable from a platform that went
        quiet, which is the exact confusion the emitter network exists
        to remove.
        """
        p = tmp_path / "session.jsonl"
        sink = SignalSink(path=p, flush_every=1)

        real_open = type(p).open

        # The first parameter is the PATH being opened, not a test
        # instance: this function is bound onto the Path class below,
        # so it is called as `some_path.open(...)`. It is named
        # `target` rather than `self` for exactly that reason -- a
        # `self` here reads as the test object and is neither.
        def _refuse(target, *a, **k):
            if target.name.endswith(".digest.jsonl"):
                raise OSError(28, "no space left on device")
            return real_open(target, *a, **k)

        monkeypatch.setattr(type(p), "open", _refuse)
        sink.emit("ctl.00.001.invariant.control", actual=1, expected=1)
        sink.flush()

        assert sink.health()["digest_dropped"] == 1, (
            "a refused digest write was neither written nor counted")
        # The main ladder is untouched by the digest's failure.
        assert p.is_file()
        assert len(read_records(p)) == 1
