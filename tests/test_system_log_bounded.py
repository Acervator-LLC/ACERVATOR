"""console/system.log must not grow without limit.

WHAT WAS MEASURED
=================
``~/.acervator_logs/console/system.log`` on 2026-08-13: 9,146,281,918
bytes, still climbing. Every other writer in ``logging_engine`` was
already bounded — ``trade.log``, ``gate.log``, ``diagnostics.log`` and
``voting.log`` all run through ``NDJSONWriter`` at 50 MB x 5, and the
operator's disk shows each of their backups sitting at 52,428,9xx
bytes. The one writer that used the standard-library ``logging`` module
was built with a plain ``logging.FileHandler``: no ``maxBytes``, no
``backupCount``, no rotation of any kind.

So this file pins the bound, and it pins the boundary behaviour that
makes a bound safe to have:

  * the record that TRIGGERS a rollover still lands, exactly once
  * the ``.4 -> .5`` shift succeeds with every slot already occupied —
    the state that stalled ``gate.log`` for three days and produced
    350,470 warnings
  * a rollover that FAILS does not leave the handler holding a closed
    stream, which is how the stdlib turns one bad rename into permanent
    silence
  * the encoding contract from v3.24.53 survives rotation, in every slot

WHAT A FAILURE HERE WOULD MEAN
==============================
`test_the_installed_handler_is_bounded` red: the operator's disk fills
again, and the file that is supposed to explain a fault becomes too
large to open while explaining nothing.

`test_no_record_is_lost_across_the_boundary` red: the log drops exactly
the line that was interesting enough to cross the cap.

`test_a_full_ladder_still_rolls` red: v3.23.5 has been un-learned and
the writer stalls.

`test_a_failed_rollover_does_not_kill_the_handler` red: one locked file
silences the system log for the rest of the process, with nothing said.

`test_a_failed_REOPEN_does_not_silence_the_log_for_ever` red: the same
permanent silence, through the hole the `finally` did not cover. The
`finally` closed the failed-SHIFT case and opened a wider one, because
`self._open()` can raise too and it was the last statement — so a raise
left `self.stream` bound to the file object that had just been CLOSED,
never to None. `shouldRollover` reopens only on None. MEASURED: OURS
self-healed False against the stdlib's True on the identical transient,
current file ABSENT from disk, `flush()` and `close()` both raising.
One disk hiccup, every later line of the trading log gone, no error the
operator can see.

`test_the_handler_can_still_be_shut_down_after_a_failed_reopen` red:
shutdown — the last chance to get buffered records onto disk — raises
instead of flushing.
"""
from __future__ import annotations

import logging
import threading
from logging.handlers import RotatingFileHandler

import pytest

from src.core.logging_engine import (
    SYSTEM_LOG_BACKUP_COUNT,
    SYSTEM_LOG_MAX_BYTES,
    LogManager,
    SizeBoundedFileHandler,
)


@pytest.fixture
def clean_acervator_logger():
    """Hand the test an empty "acervator" logger and put it back after.

    The logger is process-global and `LogManager` only installs its
    handler when the logger has none, so a test that left one behind
    would silently disable the next test's handler.
    """
    log = logging.getLogger("acervator")
    saved = list(log.handlers)
    saved_level = log.level
    for h in saved:
        log.removeHandler(h)
    yield log
    for h in list(log.handlers):
        h.close()
        log.removeHandler(h)
    for h in saved:
        log.addHandler(h)
    log.setLevel(saved_level)


def _census(base):
    """(total lines, distinct lines) across the current file and backups."""
    lines = []
    for name in [base.name] + ["%s.%d" % (base.name, i) for i in range(1, 9)]:
        p = base.parent / name
        if p.is_file():
            lines.extend(
                p.read_text(encoding="utf-8", errors="replace").splitlines())
    return len(lines), len(set(lines))


def _slots(base):
    return [i for i in range(1, 9)
            if (base.parent / ("%s.%d" % (base.name, i))).is_file()]


class TestTheBoundExists:
    def test_the_installed_handler_is_bounded(self, tmp_path,
                                              clean_acervator_logger):
        """THE unit. Asserted on the handler LogManager actually
        installs, not on the source text, because a source that says
        `maxBytes` and a handler that rotates are different claims."""
        LogManager(log_dir=tmp_path)
        handlers = clean_acervator_logger.handlers
        assert len(handlers) == 1
        h = handlers[0]
        assert isinstance(h, SizeBoundedFileHandler)
        assert h.maxBytes == SYSTEM_LOG_MAX_BYTES
        assert h.backupCount == SYSTEM_LOG_BACKUP_COUNT
        assert h.baseFilename.endswith("system.log")

    def test_the_bound_matches_every_other_writer_in_the_module(self):
        """50 MB x 5 is not a new number. It is what NDJSONWriter has
        used for trade.log, gate.log, diagnostics.log and voting.log
        since v3.23.5, measured holding on the operator's disk."""
        assert SYSTEM_LOG_MAX_BYTES == 50 * 1024 * 1024
        assert SYSTEM_LOG_BACKUP_COUNT == 5

    def test_the_encoding_contract_survived_the_change(
            self, tmp_path, clean_acervator_logger):
        """v3.24.53 cost 825 dropped records. Swapping the handler class
        is exactly the kind of change that would quietly undo it."""
        LogManager(log_dir=tmp_path)
        h = clean_acervator_logger.handlers[0]
        assert (h.stream.encoding or "").lower().replace("-", "") == "utf8"
        assert h.stream.errors == "replace"


class TestTheRolloverBoundary:
    def test_no_record_is_lost_across_the_boundary(self, tmp_path,
                                                   clean_acervator_logger):
        base = tmp_path / "system.log"
        h = SizeBoundedFileHandler(base, maxBytes=4096, backupCount=5,
                                   encoding="utf-8", errors="replace")
        h.setFormatter(logging.Formatter("%(message)s"))
        clean_acervator_logger.setLevel(logging.DEBUG)
        clean_acervator_logger.addHandler(h)
        for i in range(400):
            clean_acervator_logger.warning("record-%05d" % i)
        h.flush()
        total, distinct = _census(base)
        assert _slots(base), "nothing rotated, so there is no boundary"
        assert total == 400, "records were lost at a rollover"
        assert distinct == 400, "records were duplicated at a rollover"

    def test_the_triggering_record_lands_in_the_new_file(
            self, tmp_path, clean_acervator_logger):
        """The record that pushes the file over the cap must be written
        AFTER the rename, not into the handle that was just renamed."""
        base = tmp_path / "system.log"
        base.write_bytes(b"z" * 5000)
        h = SizeBoundedFileHandler(base, maxBytes=4096, backupCount=5,
                                   encoding="utf-8", errors="replace")
        h.setFormatter(logging.Formatter("%(message)s"))
        clean_acervator_logger.setLevel(logging.DEBUG)
        clean_acervator_logger.addHandler(h)
        clean_acervator_logger.warning("the triggering record")
        h.flush()
        assert base.read_text(encoding="utf-8").strip() == (
            "the triggering record")
        assert (tmp_path / "system.log.1").read_bytes() == b"z" * 5000

    def test_a_full_ladder_still_rolls(self, tmp_path,
                                       clean_acervator_logger):
        """THE .4 -> .5 CONDITION.

        Every backup slot occupied, then a forced rollover. This is the
        state that stalled the gate.log writer between 2026-06-10 and
        2026-06-13. `Path.rename` refuses it on Windows with WinError
        183; `Path.replace` is the documented overwrite primitive and
        does not.
        """
        base = tmp_path / "system.log"
        before = {}
        for i in range(1, 6):
            p = tmp_path / ("system.log.%d" % i)
            p.write_bytes(b"slot-%d\n" % i)
            before[i] = p.read_bytes()
        base.write_bytes(b"z" * 5000)

        h = SizeBoundedFileHandler(base, maxBytes=4096, backupCount=5,
                                   encoding="utf-8", errors="replace")
        h.setFormatter(logging.Formatter("%(message)s"))
        clean_acervator_logger.setLevel(logging.DEBUG)
        clean_acervator_logger.addHandler(h)
        clean_acervator_logger.warning("crosses a full ladder")
        h.flush()

        assert (tmp_path / "system.log.1").read_bytes() == b"z" * 5000
        for i in range(1, 5):
            assert (tmp_path / ("system.log.%d" % (i + 1))).read_bytes() == (
                before[i]), "slot %d did not shift to %d" % (i, i + 1)
        assert _slots(base) == [1, 2, 3, 4, 5]
        assert not (tmp_path / "system.log.6").exists()
        assert base.read_text(encoding="utf-8").strip() == (
            "crosses a full ladder")

    def test_the_rollover_is_not_the_stdlib_one(self):
        """A NAMED, DELIBERATE OVERRIDE.

        `BaseRotatingHandler.rotate` — the documented hook — is
        consulted only for `base -> .1`. The `.4 -> .5` loop calls
        `os.rename` directly and never goes through it, so setting
        `handler.rotator` would leave the dangerous step on the banned
        primitive. Overriding `doRollover` is the only place it is
        reachable, and this asserts the override is still in place.
        """
        assert (SizeBoundedFileHandler.doRollover
                is not RotatingFileHandler.doRollover)

    def test_a_custom_rotator_is_still_honoured(self, tmp_path,
                                                clean_acervator_logger):
        """Overriding doRollover must not silently disable the hook it
        bypasses — including for the .4 -> .5 step, which the stdlib
        never routed through it."""
        seen = []

        def rotator(source, dest):
            seen.append((source, dest))

        base = tmp_path / "system.log"
        for i in range(1, 6):
            (tmp_path / ("system.log.%d" % i)).write_bytes(b"x")
        base.write_bytes(b"z" * 5000)
        h = SizeBoundedFileHandler(base, maxBytes=4096, backupCount=5,
                                   encoding="utf-8", errors="replace")
        h.rotator = rotator
        h.setFormatter(logging.Formatter("%(message)s"))
        clean_acervator_logger.setLevel(logging.DEBUG)
        clean_acervator_logger.addHandler(h)
        clean_acervator_logger.warning("rotate through the hook")
        h.flush()
        assert len(seen) == 5, "the hook was skipped for some slot"
        assert seen[0][0].endswith("system.log.4")
        assert seen[0][1].endswith("system.log.5")
        assert seen[-1][0].endswith("system.log")


class TestAFailedRolloverIsSurvivable:
    def test_a_failed_rollover_does_not_kill_the_handler(
            self, tmp_path, clean_acervator_logger):
        """THE SILENT-DEATH CASE.

        The stdlib closes the stream, shifts, then reopens. If a shift
        raises, the reopen never runs and every later record hits a
        closed stream, so the log stops for the life of the process and
        nothing says why. Here the reopen is in a `finally`.

        The fault is injected through the public `rotator` hook rather
        than by monkeypatching internals, so this drives a real branch
        rather than a simulated one.
        """
        base = tmp_path / "system.log"
        base.write_bytes(b"z" * 5000)

        def broken(source, dest):
            raise OSError(32, "destination is held open by another process")

        h = SizeBoundedFileHandler(base, maxBytes=4096, backupCount=5,
                                   encoding="utf-8", errors="replace")
        h.rotator = broken
        h.setFormatter(logging.Formatter("%(message)s"))
        clean_acervator_logger.setLevel(logging.DEBUG)
        clean_acervator_logger.addHandler(h)

        clean_acervator_logger.warning("during the broken rollover")
        h.rotator = None
        clean_acervator_logger.warning("after the broken rollover")
        h.flush()

        assert not h.stream.closed, "the handler was left holding a dead stream"
        text = base.read_text(encoding="utf-8")
        assert "after the broken rollover" in text, (
            "the handler went silent after one failed rollover")

    def test_a_failed_REOPEN_does_not_silence_the_log_for_ever(
            self, tmp_path, clean_acervator_logger):
        """THE SILENT-DEATH CASE THE ``finally`` DID NOT COVER.

        The test above injects the fault into the SHIFT, which the
        ``finally`` handles. This one injects it into the REOPEN
        itself, which the ``finally`` cannot handle because the reopen
        IS the ``finally``.

        MEASURED before the fix, both handlers driven through the
        identical transient -- one OSError(28) out of ``_open`` which
        then clears:

            OURS    stream_is_None=False  stream_closed=True
                    SELF-HEALED=False     handleError=3
            STDLIB  stream_is_None=False  stream_closed=False
                    SELF-HEALED=True      handleError=1

        and worse than the census shows: the shift had already moved
        the current file to ``.1``, so the directory held ``.1`` and
        NOTHING ELSE. ``flush()`` and ``close()`` both raised
        ValueError. The operator would have had no file to open and no
        error to read.

        WHAT A FAILURE HERE MEANS: one disk hiccup during one rollover
        costs every subsequent line of the log that records his
        trading, for the life of the process, with nothing said. Real
        money, 37 bots.
        """
        base = tmp_path / "system.log"
        base.write_bytes(b"z" * 5000)

        h = SizeBoundedFileHandler(base, maxBytes=4096, backupCount=5,
                                   encoding="utf-8", errors="replace")
        h.setFormatter(logging.Formatter("%(message)s"))

        real_open = h._open
        fired: list = []

        def flaky_open():
            """One transient failure, then the disk recovers."""
            if not fired:
                fired.append(True)
                raise OSError(28, "No space left on device")
            return real_open()

        h._open = flaky_open
        clean_acervator_logger.setLevel(logging.DEBUG)
        clean_acervator_logger.addHandler(h)

        clean_acervator_logger.warning("during the failed reopen")
        assert fired, ("the transient never fired, so this test proved "
                       "nothing about a failed reopen")
        # THE PROPERTY. Not "a stream exists" -- a CLOSED stream also
        # exists, and that is exactly the bug. The slot must be empty,
        # because an empty slot is what makes shouldRollover reopen.
        assert h.stream is None, (
            "doRollover left a closed file object bound to self.stream; "
            "shouldRollover only reopens when it is None, so every later "
            "record dies in handleError and the log is silent for ever")

        clean_acervator_logger.warning("after the failed reopen")
        clean_acervator_logger.warning("and the one after that")
        h.flush()

        assert h.stream is not None and not h.stream.closed
        assert base.is_file(), (
            "the rollover moved the current file to .1 and never "
            "recreated it, so there is no log to read")
        text = base.read_text(encoding="utf-8")
        assert "after the failed reopen" in text
        assert "and the one after that" in text
        assert text.strip(), "the current file is empty"

    def test_the_handler_can_still_be_shut_down_after_a_failed_reopen(
            self, tmp_path, clean_acervator_logger):
        """``FileHandler.close`` flushes, and ``flush`` touches the
        stream. A handler holding a closed file object could therefore
        not even be closed: both raised ValueError, measured. Shutdown
        is the last chance to get records onto disk, so it failing is
        its own loss and not merely untidy."""
        base = tmp_path / "system.log"
        base.write_bytes(b"z" * 5000)
        h = SizeBoundedFileHandler(base, maxBytes=4096, backupCount=5,
                                   encoding="utf-8", errors="replace")
        h.setFormatter(logging.Formatter("%(message)s"))
        real_open = h._open
        fired: list = []

        def flaky_open():
            if not fired:
                fired.append(True)
                raise OSError(28, "No space left on device")
            return real_open()

        h._open = flaky_open
        clean_acervator_logger.setLevel(logging.DEBUG)
        clean_acervator_logger.addHandler(h)
        clean_acervator_logger.warning("during the failed reopen")
        assert fired

        h.flush()          # must not raise
        clean_acervator_logger.removeHandler(h)
        h.close()          # must not raise


class TestRotationKeepsTheFileReadable:
    def test_every_slot_stays_whole_utf8_text(self, tmp_path,
                                              clean_acervator_logger):
        """The only reader of system.log is the operator, in an editor.
        Nothing in src/, tools/, main.py or acervator_watchdog.py opens
        it: live_log_reader — the single sanctioned reader of the live
        log root — reads only trade/. So "does not break a reader" means
        every rotated file is still whole, decodable lines."""
        base = tmp_path / "system.log"
        h = SizeBoundedFileHandler(base, maxBytes=4096, backupCount=5,
                                   encoding="utf-8", errors="replace")
        h.setFormatter(logging.Formatter("%(message)s"))
        clean_acervator_logger.setLevel(logging.DEBUG)
        clean_acervator_logger.addHandler(h)
        for i in range(400):
            clean_acervator_logger.warning(
                "arrow → dash — record-%05d" % i)
        h.flush()
        checked = 0
        for name in [base.name] + ["%s.%d" % (base.name, i)
                                   for i in range(1, 6)]:
            p = tmp_path / name
            if not p.is_file():
                continue
            checked += 1
            raw = p.read_bytes()
            assert raw.endswith(b"\n"), "%s ends mid-line" % name
            for line in raw.decode("utf-8").splitlines():
                assert "→" in line and "record-" in line
        assert checked >= 2, "no rotation happened, so nothing was proved"


class TestUnderLoad:
    def test_eight_threads_across_many_rollovers_lose_nothing(
            self, tmp_path, clean_acervator_logger):
        """The handler is reachable from bot threads, ccxt worker
        threads and the GUI thread at once. `logging.Handler.handle`
        serialises `emit` on the handler's own lock, so rotation cannot
        interleave with an append — this asserts that rather than
        assuming it."""
        base = tmp_path / "system.log"
        h = SizeBoundedFileHandler(base, maxBytes=8192, backupCount=5,
                                   encoding="utf-8", errors="replace")
        h.setFormatter(logging.Formatter("%(message)s"))
        clean_acervator_logger.setLevel(logging.DEBUG)
        clean_acervator_logger.addHandler(h)

        def worker(tid):
            for i in range(150):
                clean_acervator_logger.warning("t%02d-r%05d" % (tid, i))

        threads = [threading.Thread(target=worker, args=(t,))
                   for t in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        h.flush()
        total, distinct = _census(base)
        assert total == 1200
        assert distinct == 1200
