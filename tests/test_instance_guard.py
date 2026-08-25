"""Issue #96 - a second instance cannot begin trading without consent.

WHAT THESE TESTS PIN, AND WHAT THEY DELIBERATELY DO NOT
=======================================================
The regression that matters most is NOT a refusal. It is the permission:
the operator's own machine, coming back after a crash or a reboot, must
still start its 37 bots with no dialog and no click. A guard that made
him hand-start the fleet would be a worse product than the defect it
repairs, so `test_same_machine_resume_still_auto_starts` and
`test_crash_left_a_lock_file_and_the_fleet_still_resumes` are the first
two tests in the file and the two that must never be relaxed.

The refusals are pinned beside them: a different machine, a copied
directory, a second copy on one machine, and four separate ways of being
uncertain.

NO TEST TOUCHES `~/.acervator/`
================================
The operator's Acervator is running and trading real money. Every test
here names a `tmp_path` directory, and
`test_the_guard_cannot_default_to_the_operators_directory` reads the
constructor signature to prove a forgotten argument could not reach the
live directory even by accident.

HOW A DIFFERENT MACHINE IS SIMULATED
=====================================
`_platform_machine_id` is the ONE seam. It is the single function that
reads the fact living outside the state directory - `MachineGuid`,
`/etc/machine-id`, `IOPlatformUUID` - and everything else in the
derivation runs for real against it. Substituting the platform fact is
what "a different machine" means, so the test substitutes exactly that
and nothing else.
"""

from __future__ import annotations

import ast
import contextlib
import gc
import hashlib
import inspect
import json
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Iterator, Optional

import pytest

import src.core.signal_contract as sc
from src.core import instance_guard as ig
from src.core.signal_contract import SignalSink

if TYPE_CHECKING:  # pragma: no cover - typing only
    from PySide6.QtWidgets import QApplication

_NO_DISPLAY = "no display"

PIN = "instance.17.001.postcondition.auto_start_permitted"

MACHINE_A = "aaaaaaaa-1111-4444-8888-aaaaaaaaaaaa"
MACHINE_B = "bbbbbbbb-2222-4444-8888-bbbbbbbbbbbb"

FLEET = 37
"""The operator's real fleet size. A count of one would let an
off-by-one in the dialog text pass unnoticed."""


# ── seams ──────────────────────────────────────────────────────────────


def _be_machine(
    monkeypatch: pytest.MonkeyPatch,
    machine_id: Optional[str],
    host: str = "desk-01",
    user: str = "brown",
) -> None:
    """Run the rest of the test as the named machine.

    `machine_id=None` means the platform id could not be read at all,
    which is the weak-identity case.
    """
    monkeypatch.setattr(
        ig, "_platform_machine_id", lambda: (machine_id, "test:platform-id")
    )
    monkeypatch.setattr(ig, "_safe_host", lambda: host)
    monkeypatch.setattr(ig, "_safe_user", lambda: user)


@contextlib.contextmanager
def _guard(config_dir: Path) -> Iterator[ig.InstanceGuard]:
    """A guard whose exclusive handle is always released again.

    A leaked handle would make the NEXT test in the file see
    `live_instance` and pass or fail for a reason that has nothing to do
    with what it asserts.
    """
    guard = ig.InstanceGuard(config_dir, app_version="test")
    try:
        yield guard
    finally:
        guard.release()


@contextlib.contextmanager
def _collect() -> Iterator[SignalSink]:
    """Install a sink and restore the PREVIOUS one, never None."""
    sink = SignalSink(flush_every=1)
    previous = sc.get_sink()
    sc.reset_throttle()
    sc.set_sink(sink)
    try:
        yield sink
    finally:
        sc.set_sink(previous)
        sc.reset_throttle()


def _claim_owned_by(
    config_dir: Path, machine_id: str, host: str = "desk-01", user: str = "brown"
) -> None:
    """Write a claim as though that machine had run here."""
    monkey = pytest.MonkeyPatch()
    try:
        _be_machine(monkey, machine_id, host, user)
        ig.write_claim(config_dir, ig.read_machine_identity(), "test")
    finally:
        monkey.undo()


@contextlib.contextmanager
def capture_errors(logger_name: str) -> Iterator[list]:
    """Collect ERROR records from one logger.

    `caplog` cannot see them: `logging_engine.py:315` sets
    `propagate = False` on the `acervator` logger, so records stop there
    and never reach the root handler pytest installs.
    """
    import logging

    found: list = []

    class _Sink(logging.Handler):
        def emit(self, record: "logging.LogRecord") -> None:
            if record.levelno >= logging.ERROR:
                found.append(record.getMessage())

    target = logging.getLogger(logger_name)
    sink = _Sink()
    target.addHandler(sink)
    try:
        yield found
    finally:
        target.removeHandler(sink)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ── the permission, which is the regression that matters ───────────────


def test_same_machine_resume_still_auto_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The operator's own machine resumes its own fleet with no prompt.

    This is the behaviour issue #96 must not break. `bot_container.py`
    records `_was_running` so a crash or a reboot brings the fleet back
    without the operator rebuilding it by hand.
    """
    _be_machine(monkeypatch, MACHINE_A)
    _claim_owned_by(tmp_path, MACHINE_A)

    with _guard(tmp_path) as guard:
        decision = guard.evaluate(FLEET)

    assert decision.verdict == ig.VERDICT_SAME_MACHINE
    assert decision.permits_auto_start is True


def test_crash_left_a_lock_file_and_the_fleet_still_resumes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crash leaves the lock FILE behind. The operating system drops
    the HANDLE, so the next launch finds it free and resumes silently."""
    _be_machine(monkeypatch, MACHINE_A)
    _claim_owned_by(tmp_path, MACHINE_A)
    # What a killed process leaves on disk: the file, with its note, and
    # no live handle on it.
    (tmp_path / ig.LOCK_FILENAME).write_text("pid=999999\n", encoding="utf-8")

    with _guard(tmp_path) as guard:
        decision = guard.evaluate(FLEET)

    assert decision.verdict == ig.VERDICT_SAME_MACHINE
    assert decision.permits_auto_start is True


def test_first_run_with_no_fleet_permits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty directory holds no fleet, so nothing can collide."""
    _be_machine(monkeypatch, MACHINE_A)

    with _guard(tmp_path) as guard:
        decision = guard.evaluate(0)

    assert decision.verdict == ig.VERDICT_FIRST_RUN
    assert decision.permits_auto_start is True


def test_ownership_is_recorded_and_the_next_launch_is_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Take ownership once; the launch after it needs no prompt."""
    _be_machine(monkeypatch, MACHINE_A)

    with _guard(tmp_path) as first:
        first.evaluate(FLEET)
        assert first.take_ownership() is True

    with _guard(tmp_path) as second:
        decision = second.evaluate(FLEET)

    assert decision.verdict == ig.VERDICT_SAME_MACHINE
    assert decision.permits_auto_start is True


# ── the refusals ───────────────────────────────────────────────────────


def test_a_different_machine_does_not_auto_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A different machine is refused, and the reason names both."""
    _claim_owned_by(tmp_path, MACHINE_A, host="desk-01")
    _be_machine(monkeypatch, MACHINE_B, host="cloud-vm-01")

    with _guard(tmp_path) as guard:
        decision = guard.evaluate(FLEET)

    assert decision.verdict == ig.VERDICT_FOREIGN_MACHINE
    assert decision.permits_auto_start is False
    # It must SAY why, in words the operator can act on.
    assert "desk-01" in decision.detail
    assert "cloud-vm-01" in decision.detail
    assert "desk-01" in decision.owner_line
    assert "cloud-vm-01" in decision.this_machine_line


def test_a_cloned_acervator_directory_is_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The operator's actual cloud scenario, copied file by file.

    A machine id written INTO the directory would travel with the copy
    and prove nothing. The identity is derived from outside it, so the
    copy carries the original's claim and computes its own value against
    it. The copy is what makes the mismatch visible.
    """
    original = tmp_path / "desk"
    original.mkdir()
    _claim_owned_by(original, MACHINE_A, host="desk-01")
    (original / "bot_state.json").write_text(
        json.dumps({"bots": {f"bot-{i}": {} for i in range(FLEET)}}), encoding="utf-8"
    )

    # `scp -r ~/.acervator cloud:` - every byte, nothing left behind.
    clone = tmp_path / "cloud"
    shutil.copytree(original, clone)
    assert (clone / ig.CLAIM_FILENAME).exists(), "the claim was copied"

    _be_machine(monkeypatch, MACHINE_B, host="cloud-vm-01")
    with _guard(clone) as guard:
        decision = guard.evaluate(FLEET)

    assert decision.verdict == ig.VERDICT_FOREIGN_MACHINE
    assert decision.permits_auto_start is False


def test_a_saved_fleet_with_no_claim_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fleet with no owner beside it is the upgrade-or-copy pair.

    Nothing on disk separates "the first launch of the build that added
    this guard" from "a directory copied out of a build that had none",
    so the guard asks once rather than guessing about real money.
    """
    _be_machine(monkeypatch, MACHINE_A)

    with _guard(tmp_path) as guard:
        decision = guard.evaluate(FLEET)

    assert decision.verdict == ig.VERDICT_UNCLAIMED_FLEET
    assert decision.permits_auto_start is False


def test_a_second_copy_on_one_machine_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two copies on ONE computer share a fingerprint, so only the
    operating system can tell them apart. The handle is that answer."""
    _be_machine(monkeypatch, MACHINE_A)
    _claim_owned_by(tmp_path, MACHINE_A)

    with _guard(tmp_path) as running:
        first = running.evaluate(FLEET)
        assert first.permits_auto_start is True

        with _guard(tmp_path) as second_copy:
            decision = second_copy.evaluate(FLEET)

    assert decision.verdict == ig.VERDICT_LIVE_INSTANCE
    assert decision.permits_auto_start is False
    # And no answer the operator gives makes this one safe.
    assert decision.consent_is_possible is False


# ── the uncertain cases, which must all fail closed ────────────────────


def test_an_unreadable_claim_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A corrupt claim is NOT the same as no claim."""
    _be_machine(monkeypatch, MACHINE_A)
    (tmp_path / ig.CLAIM_FILENAME).write_text("{not json", encoding="utf-8")

    with _guard(tmp_path) as guard:
        decision = guard.evaluate(FLEET)

    assert decision.claim_state == "unreadable"
    assert decision.verdict == ig.VERDICT_UNCERTAIN
    assert decision.permits_auto_start is False


def test_a_claim_with_no_fingerprint_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A well-formed file that names no machine establishes nothing."""
    _be_machine(monkeypatch, MACHINE_A)
    (tmp_path / ig.CLAIM_FILENAME).write_text(
        json.dumps({"host": "desk-01"}), encoding="utf-8"
    )

    with _guard(tmp_path) as guard:
        decision = guard.evaluate(FLEET)

    assert decision.verdict == ig.VERDICT_UNCERTAIN
    assert decision.permits_auto_start is False


def test_no_platform_machine_id_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without a platform id the identity is host plus user, and two
    cloud machines from one image share both. It never permits."""
    _claim_owned_by(tmp_path, MACHINE_A)
    _be_machine(monkeypatch, None)

    with _guard(tmp_path) as guard:
        decision = guard.evaluate(FLEET)

    assert decision.identity.strength == ig.STRENGTH_WEAK
    assert decision.verdict == ig.VERDICT_UNCERTAIN
    assert decision.permits_auto_start is False


def test_a_renamed_machine_is_uncertain_rather_than_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same platform id, different host name.

    Two causes and no evidence to split them: the operator renamed his
    computer, or two machines were cloned from one disk image and given
    different host names. One is harmless and one is the hazard, so the
    guard asks.
    """
    _claim_owned_by(tmp_path, MACHINE_A, host="desk-01")
    _be_machine(monkeypatch, MACHINE_A, host="desk-02")

    with _guard(tmp_path) as guard:
        decision = guard.evaluate(FLEET)

    assert decision.verdict == ig.VERDICT_UNCERTAIN
    assert decision.permits_auto_start is False


def test_a_lock_that_cannot_be_taken_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No locking facility means no proof of exclusivity."""
    _be_machine(monkeypatch, MACHINE_A)
    _claim_owned_by(tmp_path, MACHINE_A)
    monkeypatch.setattr(ig.InstanceLock, "_try_lock", staticmethod(lambda _fd: None))

    with _guard(tmp_path) as guard:
        decision = guard.evaluate(FLEET)

    assert decision.lock_state == ig.LOCK_UNAVAILABLE
    assert decision.verdict == ig.VERDICT_UNCERTAIN
    assert decision.permits_auto_start is False
    assert decision.consent_is_possible is False


def test_every_refusal_verdict_is_outside_the_permitted_set() -> None:
    """The permitted set is closed by construction, not by inspection."""
    refusals = {
        ig.VERDICT_LIVE_INSTANCE,
        ig.VERDICT_FOREIGN_MACHINE,
        ig.VERDICT_UNCLAIMED_FLEET,
        ig.VERDICT_UNCERTAIN,
    }
    assert refusals.isdisjoint(ig.AUTO_START_PERMITTED)
    assert ig.AUTO_START_PERMITTED == {ig.VERDICT_FIRST_RUN, ig.VERDICT_SAME_MACHINE}


# ── what a refusal must not do ─────────────────────────────────────────


def test_a_refusal_leaves_the_previous_owners_claim_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refusal writes no claim, so a second look reaches the same
    verdict and the real owner's record is not quietly taken."""
    _claim_owned_by(tmp_path, MACHINE_A, host="desk-01")
    before = _digest(tmp_path / ig.CLAIM_FILENAME)

    _be_machine(monkeypatch, MACHINE_B, host="cloud-vm-01")
    with _guard(tmp_path) as guard:
        guard.evaluate(FLEET)
        again = guard.evaluate(FLEET)

    assert _digest(tmp_path / ig.CLAIM_FILENAME) == before
    assert again.verdict == ig.VERDICT_FOREIGN_MACHINE


def test_take_ownership_refuses_without_the_exclusive_handle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Taking the record from a copy that is provably alive would tell
    the next launch a lie, so it is refused even after consent."""
    _be_machine(monkeypatch, MACHINE_A)
    _claim_owned_by(tmp_path, MACHINE_A)
    before = _digest(tmp_path / ig.CLAIM_FILENAME)

    with _guard(tmp_path) as running:
        running.evaluate(FLEET)
        with _guard(tmp_path) as second_copy:
            second_copy.evaluate(FLEET)
            assert second_copy.take_ownership() is False

    assert _digest(tmp_path / ig.CLAIM_FILENAME) == before


def test_the_guard_never_reads_its_identity_out_of_the_state_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The property the whole design turns on, asserted directly.

    A machine id planted inside the directory - under any of the names a
    future reader might reach for - must not change the verdict.
    """
    _claim_owned_by(tmp_path, MACHINE_A, host="desk-01")
    for name in ("machine_id", "machine-id", "machine_id.txt"):
        (tmp_path / name).write_text(MACHINE_A, encoding="utf-8")

    _be_machine(monkeypatch, MACHINE_B, host="cloud-vm-01")
    with _guard(tmp_path) as guard:
        decision = guard.evaluate(FLEET)

    assert decision.verdict == ig.VERDICT_FOREIGN_MACHINE


def test_the_guard_cannot_default_to_the_operators_directory() -> None:
    """`config_dir` has NO default, so no forgotten argument can write a
    lock into the directory the operator's live application reads."""
    parameter = inspect.signature(ig.InstanceGuard.__init__).parameters["config_dir"]
    assert parameter.default is inspect.Parameter.empty
    with pytest.raises(TypeError):
        ig.InstanceGuard()


# ── the words the operator reads ───────────────────────────────────────


def test_the_consequence_names_the_bot_count_and_the_live_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dialog that says "continue?" without naming the consequence
    collects a click, not consent."""
    _claim_owned_by(tmp_path, MACHINE_A, host="desk-01")
    _be_machine(monkeypatch, MACHINE_B, host="cloud-vm-01")

    with _guard(tmp_path) as guard:
        decision = guard.evaluate(FLEET)

    consequence = decision.consequence_line
    assert str(FLEET) in consequence
    assert "live exchange account" in consequence
    assert "desk-01" in decision.owner_line
    assert decision.claim is not None
    assert decision.claim.claimed_at_human, "the owner line needs a date"


# ── the emitter ────────────────────────────────────────────────────────


def test_the_pin_reports_the_verdict_and_agrees_with_the_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pin 17-001 on the permitted path."""
    _be_machine(monkeypatch, MACHINE_A)
    _claim_owned_by(tmp_path, MACHINE_A)

    with _collect() as sink, _guard(tmp_path) as guard:
        guard.evaluate(FLEET)

    records = [r for r in sink.records() if r.name == PIN]
    assert len(records) == 1
    record = records[0]
    assert record.ok is True
    assert record.context["verdict"] == ig.VERDICT_SAME_MACHINE
    assert record.context["fleet_bots"] == FLEET
    assert record.duration is not None


def test_the_pin_fires_on_a_refusal_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refusal is the record the operator most needs to find later."""
    _claim_owned_by(tmp_path, MACHINE_A, host="desk-01")
    _be_machine(monkeypatch, MACHINE_B, host="cloud-vm-01")

    with _collect() as sink, _guard(tmp_path) as guard:
        guard.evaluate(FLEET)

    records = [r for r in sink.records() if r.name == PIN]
    assert len(records) == 1
    record = records[0]
    # `ok` says the flag and the evidence AGREE. Both are False here, so
    # the check passes while the verdict refuses -- those are two
    # different questions and the pin must not merge them.
    assert record.ok is True
    assert record.context["verdict"] == ig.VERDICT_FOREIGN_MACHINE
    assert record.context["owner_machine"].startswith("desk-01")
    assert record.context["this_machine"].startswith("cloud-vm-01")


def test_the_pin_carries_no_credential_material(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The record must never carry the raw platform id, and the claim
    file must not either. A digest is not the identifier."""
    _be_machine(monkeypatch, MACHINE_A)

    with _collect() as sink, _guard(tmp_path) as guard:
        guard.evaluate(0)
        guard.take_ownership()

    rendered = json.dumps(
        [r.context for r in sink.records() if r.name == PIN], default=str
    )
    assert MACHINE_A not in rendered
    assert MACHINE_A not in (tmp_path / ig.CLAIM_FILENAME).read_text(encoding="utf-8")


# ── the consent surface ────────────────────────────────────────────────


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """The QApplication the dialog tests run against."""
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    running = QApplication.instance()
    if isinstance(running, QApplication):
        return running
    return QApplication(sys.argv)


def _refused_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> ig.GuardDecision:
    _claim_owned_by(tmp_path, MACHINE_A, host="desk-01")
    _be_machine(monkeypatch, MACHINE_B, host="cloud-vm-01")
    with _guard(tmp_path) as guard:
        return guard.evaluate(FLEET)


def _live_consent_dialogs(qapp: "QApplication") -> int:
    """How many consent dialogs are still top-level widgets right now."""
    from src.gui.instance_consent_dialog import InstanceConsentDialog

    return len(
        [w for w in qapp.topLevelWidgets() if isinstance(w, InstanceConsentDialog)]
    )


@contextlib.contextmanager
def _consent_dialog(
    decision: ig.GuardDecision, qapp: "QApplication"
) -> Iterator[object]:
    """Build the dialog and release it when the block ends.

    NEVER `deleteLater()`. MEASURED 2026-08-23: `deleteLater()` moves
    ownership from Python to C++, and the `DeferredDelete` event that
    then has to arrive is NOT delivered by `QApplication.processEvents()`
    - only by a running event loop. A dialog cleaned up that way stays in
    `QApplication.topLevelWidgets()` for the rest of the process.

    That is not a cosmetic leak. `tests/test_sim_visuals_expand_reentrancy.py`
    takes `[w for w in app.topLevelWidgets() if isinstance(w, QDialog)][0]`
    and asserts on that object's lifetime. A surviving consent dialog
    becomes element zero, and the test reports the Expand dialog as
    leaked while it is examining a different widget entirely.

    The exit hands ownership back to Python with `setParent(None)` and
    drops the helper's reference. It does NOT check the result: the `with`
    target still names the widget in the test's own frame at this point,
    so any count taken here reads at least one and would be a check that
    can never pass. `_no_consent_dialog_outlives_its_test` asks the
    question after the test's frame is gone.
    """
    from src.gui.instance_consent_dialog import InstanceConsentDialog, release_dialog

    dialog = InstanceConsentDialog(decision)
    try:
        yield dialog
    finally:
        release_dialog(dialog)
        del dialog
        gc.collect()
        qapp.processEvents()


@pytest.fixture(autouse=True)
def _no_consent_dialog_outlives_its_test(
    request: pytest.FixtureRequest,
) -> Iterator[None]:
    """After every test in THIS file, no consent dialog may still exist.

    IT IS A FIXTURE AND NOT PART OF `_consent_dialog` BECAUSE THE `with`
    TARGET OUTLIVES THE BLOCK. `with _consent_dialog(...) as dialog:`
    binds the widget in the TEST's frame as well as the helper's, so a
    check written inside the helper's `finally` can never see zero - it
    runs while the caller still names the object. Measured: the first
    version of this check asserted 1 == 0 on every dialog test. The
    teardown of a function-scoped fixture runs after the test function
    has returned and its frame is released, which is the first moment the
    question can be answered honestly.

    This does not duplicate `tests/conftest.py::_destroy_qt_widgets`. That
    fixture CLEANS UP for the whole suite. This one ASSERTS, for this file
    only, and it fails rather than tidies - because the defect it exists
    to catch was a cleanup everybody assumed had worked.
    """
    yield
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    gc.collect()
    app.processEvents()
    survivors = _live_consent_dialogs(app)
    assert survivors == 0, (
        f"{survivors} consent dialog(s) outlived "
        f"{request.node.name} and are still top-level widgets; every "
        f"later test that walks topLevelWidgets() will see them"
    )


def test_the_dialog_defaults_to_not_starting_the_bots(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Return, Escape and the title-bar X must all mean no."""
    decision = _refused_decision(tmp_path, monkeypatch)
    with _consent_dialog(decision, qapp) as dialog:
        assert dialog.consented is False
        assert dialog._refuse_button.isDefault() is True
        assert dialog._consent_button.isDefault() is False
        dialog.reject()  # Escape and the X both land here
        assert dialog.consented is False


def test_the_dialog_states_both_machines_and_the_bot_count(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every fact the operator needs is on screen at once."""
    from PySide6.QtWidgets import QLabel

    decision = _refused_decision(tmp_path, monkeypatch)
    with _consent_dialog(decision, qapp) as dialog:
        shown = " ".join(w.text() for w in dialog.findChildren(QLabel))
        assert "desk-01" in shown
        assert "cloud-vm-01" in shown
        assert "live exchange account" in shown
        assert str(FLEET) in dialog._consent_button.text()


def test_the_dialog_offers_no_consent_against_a_live_second_copy(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Consent cannot make two live copies on one account safe, so it is
    not offered rather than offered and ignored."""
    _be_machine(monkeypatch, MACHINE_A)
    _claim_owned_by(tmp_path, MACHINE_A)
    with _guard(tmp_path) as running:
        running.evaluate(FLEET)
        with _guard(tmp_path) as second_copy:
            decision = second_copy.evaluate(FLEET)

    with _consent_dialog(decision, qapp) as dialog:
        assert dialog._consent_button.isEnabled() is False


def test_a_dialog_that_cannot_be_shown_counts_as_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A consent surface that never appeared has collected no consent."""
    import src.gui.instance_consent_dialog as dlg

    decision = _refused_decision(tmp_path, monkeypatch)

    def _explode(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError(_NO_DISPLAY)

    monkeypatch.setattr(dlg, "InstanceConsentDialog", _explode)
    assert dlg.ask_for_consent(decision) is False


# ── the seam main.py calls ─────────────────────────────────────────────


def test_an_owner_is_authorised_and_never_sees_a_dialog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The crash-recovery path asks nothing. This is the regression."""
    _be_machine(monkeypatch, MACHINE_A)
    _claim_owned_by(tmp_path, MACHINE_A)
    asked: list[ig.GuardDecision] = []

    def _record_and_consent(decision: ig.GuardDecision) -> bool:
        asked.append(decision)
        return True

    with _guard(tmp_path) as guard:
        decision = guard.evaluate(FLEET)
        authorised, why = ig.authorise_auto_start(guard, decision, _record_and_consent)

    assert authorised is True
    assert why == ig.AUTHORISED_ALREADY_OWNER
    assert asked == [], "an owner must not be prompted"


def test_a_refusal_from_the_operator_ends_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No means no, and nothing else is tried after it."""
    _claim_owned_by(tmp_path, MACHINE_A, host="desk-01")
    _be_machine(monkeypatch, MACHINE_B, host="cloud-vm-01")

    with _guard(tmp_path) as guard:
        decision = guard.evaluate(FLEET)
        authorised, why = ig.authorise_auto_start(guard, decision, lambda _d: False)

    assert authorised is False
    assert why == ig.WITHHELD_BY_OPERATOR
    # The previous owner keeps the record.
    claim = ig.read_claim(tmp_path)
    assert claim is not None
    assert claim.host == "desk-01"


def test_consent_on_a_foreign_machine_takes_ownership_and_proceeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The operator can still move his fleet. He just has to say so."""
    _claim_owned_by(tmp_path, MACHINE_A, host="desk-01")
    _be_machine(monkeypatch, MACHINE_B, host="cloud-vm-01")

    with _guard(tmp_path) as guard:
        decision = guard.evaluate(FLEET)
        authorised, why = ig.authorise_auto_start(guard, decision, lambda _d: True)

    assert authorised is True
    assert why == ig.AUTHORISED_BY_OPERATOR
    claim = ig.read_claim(tmp_path)
    assert claim is not None
    assert claim.host == "cloud-vm-01"

    # And the launch after it is silent, because this machine now owns it.
    with _guard(tmp_path) as later:
        assert later.evaluate(FLEET).verdict == ig.VERDICT_SAME_MACHINE


def test_consent_cannot_override_a_live_second_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even an operator saying yes must not start a second copy while
    the first one is provably alive."""
    _be_machine(monkeypatch, MACHINE_A)
    _claim_owned_by(tmp_path, MACHINE_A)

    with _guard(tmp_path) as running:
        running.evaluate(FLEET)
        with _guard(tmp_path) as second_copy:
            decision = second_copy.evaluate(FLEET)
            authorised, why = ig.authorise_auto_start(
                second_copy, decision, lambda _d: True
            )

    assert authorised is False
    assert why == ig.WITHHELD_NO_EXCLUSIVE_HANDLE


def test_a_consent_surface_that_raises_counts_as_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dialog that cannot be drawn has collected no consent."""
    _claim_owned_by(tmp_path, MACHINE_A, host="desk-01")
    _be_machine(monkeypatch, MACHINE_B, host="cloud-vm-01")

    def _explode(_decision: ig.GuardDecision) -> bool:
        raise RuntimeError(_NO_DISPLAY)

    with _guard(tmp_path) as guard:
        decision = guard.evaluate(FLEET)
        authorised, why = ig.authorise_auto_start(guard, decision, _explode)

    assert authorised is False
    assert why == ig.WITHHELD_BY_OPERATOR


# ── the wiring in main.py ──────────────────────────────────────────────
#
# These read main.py's SYNTAX TREE, not its text. `main()` is one
# 841-line function that no test can call - it builds a QApplication,
# reads the operator's real state directory and starts trading - so the
# alternative to a structural assertion is no assertion at all. The
# tree is checked rather than the characters, so re-indenting, renaming
# a local or re-wrapping a comment cannot make these pass or fail. What
# they catch is the gate being deleted or moved after the bots start.

_MAIN = Path(__file__).resolve().parent.parent / "main.py"


def _main_tree() -> "ast.Module":
    return ast.parse(_MAIN.read_text(encoding="utf-8"))


def _function_named(name: str) -> "ast.FunctionDef":
    for node in ast.walk(_main_tree()):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    missing = f"main.py has no function named {name!r}"
    raise AssertionError(missing)


def test_the_auto_restart_trigger_asks_the_guard_before_it_starts_bots() -> None:
    """The gate must run BEFORE the eligible list is built.

    Order is the whole assertion. A consent check that ran after the
    first bot started would collect consent for a decision already made.
    """
    trigger = _function_named("_trigger_auto_restart")
    gate_lines = [
        node.lineno
        for node in ast.walk(trigger)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "authorise_auto_start"
    ]
    assert gate_lines, "_trigger_auto_restart no longer asks the guard"

    start_lines = [
        node.lineno
        for node in ast.walk(trigger)
        if isinstance(node, ast.Attribute) and node.attr == "_on_bot_command"
    ]
    assert start_lines, "the trigger no longer starts any bot"
    assert min(gate_lines) < min(start_lines)

    returns = [
        node.lineno for node in ast.walk(trigger) if isinstance(node, ast.Return)
    ]
    assert any(
        min(gate_lines) < line < min(start_lines) for line in returns
    ), "the trigger has no way to stop between the gate and the start"


def test_main_gives_the_guard_the_state_managers_own_directory() -> None:
    """Never a second `Path.home()` derivation.

    A guard pointed at a different directory from the one the fleet was
    loaded from would claim the wrong thing, and every test passes
    `config_dir=` to the state manager.
    """
    import ast

    constructions = [
        node
        for node in ast.walk(_main_tree())
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "InstanceGuard"
    ]
    assert len(constructions) == 1, "main.py builds the guard exactly once"
    first = constructions[0].args[0]
    assert isinstance(first, ast.Attribute)
    assert first.attr == "config_dir"
    assert isinstance(first.value, ast.Name)
    assert first.value.id == "state_mgr"


def test_main_releases_the_exclusive_handle_at_shutdown() -> None:
    """A handle held past exit would refuse this machine's next launch."""
    main_fn = _function_named("main")
    released = [
        node
        for node in ast.walk(main_fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "release"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "instance_guard"
    ]
    assert released, "main() never releases the instance handle"


# ── the positive control on the instrument ─────────────────────────────


def test_the_real_platform_identity_reads_on_this_machine() -> None:
    """Every other test substitutes the platform fact. This one does not.

    Without this the whole file could pass against a `_machine_id_*`
    that returns None on every platform: the guard would then mark every
    identity weak, refuse every launch, and the mocked tests would stay
    green. A zero from an uncalibrated instrument is a claim about the
    instrument, so the real reader is exercised once, here.
    """
    if not (sys.platform.startswith(("win", "linux")) or sys.platform == "darwin"):
        pytest.skip(f"no platform machine id is defined for {sys.platform}")
    identity = ig.read_machine_identity()
    assert identity.strength == ig.STRENGTH_STRONG, (
        f"the platform machine id could not be read on {sys.platform} "
        f"({identity.source}); the guard would refuse every launch"
    )
    assert len(identity.fingerprint) == 64
    assert identity.host and identity.os_user


def test_the_real_identity_is_stable_across_calls() -> None:
    """An identity that changed between two reads would refuse the
    operator's own fleet on his own machine."""
    assert (
        ig.read_machine_identity().fingerprint == ig.read_machine_identity().fingerprint
    )


def test_the_real_identity_ignores_the_state_directory(tmp_path: Path) -> None:
    """Planting every plausible id file changes nothing, because the
    reader never looks in the directory at all."""
    before = ig.read_machine_identity().fingerprint
    for name in ("machine_id", "machine-id", "instance_claim.json", "bot_state.json"):
        (tmp_path / name).write_text("deadbeef", encoding="utf-8")
    guard = ig.InstanceGuard(tmp_path, app_version="test")
    try:
        guard.evaluate(0)
        assert guard.decision is not None
        assert guard.decision.identity.fingerprint == before
    finally:
        guard.release()


def test_ask_for_consent_leaves_no_dialog_behind(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The PRODUCT path, not just the tests.

    `ask_for_consent` is called once per launch with `parent=` the main
    window. A parented widget is owned by its parent in C++, so before
    this repair the dialog stayed attached to the main window, hidden,
    for the whole session. The function now reads the answer into a
    local, destroys the dialog, and returns the local - in that order,
    because any other order reads a widget that may already be gone.
    """
    from PySide6.QtWidgets import QWidget

    import src.gui.instance_consent_dialog as dlg

    decision = _refused_decision(tmp_path, monkeypatch)
    monkeypatch.setattr(
        dlg.InstanceConsentDialog, "exec", lambda self: self._on_consent()
    )

    window = QWidget()
    try:
        assert dlg.ask_for_consent(decision, parent=window) is True
        gc.collect()
        qapp.processEvents()
        assert _live_consent_dialogs(qapp) == 0
        assert not window.findChildren(dlg.InstanceConsentDialog), (
            "the consent dialog is still attached to the window that " "parented it"
        )
    finally:
        window.setParent(None)
        del window
        gc.collect()
        qapp.processEvents()


def test_ask_for_consent_reads_the_answer_before_it_destroys_the_dialog(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refusal must survive the destruction that follows it.

    Reading `consented` after the widget is gone would raise
    RuntimeError, and an exception on this path would be swallowed into
    a refusal - which happens to look correct, so nothing would ever
    report the fault.
    """
    import src.gui.instance_consent_dialog as dlg

    decision = _refused_decision(tmp_path, monkeypatch)
    monkeypatch.setattr(
        dlg.InstanceConsentDialog, "exec", lambda self: self._on_refuse()
    )
    with capture_errors("acervator.gui.instance_consent") as errors:
        assert dlg.ask_for_consent(decision) is False
    assert errors == [], f"the destroy path logged an error: {errors}"
    gc.collect()
    qapp.processEvents()
    assert _live_consent_dialogs(qapp) == 0
