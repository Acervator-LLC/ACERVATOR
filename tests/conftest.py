"""v3.24.19 — suite-wide isolation from the operator's runtime tree.

WHY
===
The pin tests construct real ``SimRunLog`` objects, and ``SimRunLog``
defaulted to ``~/.acervator_logs/sim``. So every suite run wrote live
run directories into the operator's own log tree. By 2026-08-04 that
tree held 62 run directories of which 54 were 4-to-59-candle test
artifacts, and diagnosing the GUI replay slowdown meant filtering
them back out of the operator's performance record before the real
runs were even visible.

The standing constraint is explicit: test harnesses never write to
``~/.acervator`` or ``~/.acervator_logs``. This file enforces it
rather than leaving it to each test author to remember.

Scope note: ``~/.acervator`` (bot_state.json, credentials) is
operator-owned and read-only to the suite. Nothing here grants write
access to it. The Simulator's own state file used to land there and
now resolves through ``ACERVATOR_SIM_STATE_ROOT``, set below.
"""

from __future__ import annotations

import faulthandler
import logging
import os
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:  # pragma: no cover
    from PySide6.QtWidgets import QWidget

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

TEST_HOME_ENV = "ACERVATOR_TEST_HOME"
"""Point the whole suite at a throwaway home directory.

Unset, nothing changes. Set, every writer that resolves ``Path.home()``
lands there instead of the operator's tree, the guard below watches that
tree, and it keeps full strictness because a live Acervator cannot reach
it.
"""

_TEST_HOME = os.environ.get(TEST_HOME_ENV)
if _TEST_HOME:
    Path(_TEST_HOME).mkdir(parents=True, exist_ok=True)
    # Set before the first src import. A module that resolves Path.home()
    # while it is being imported must already see the throwaway home.
    os.environ["USERPROFILE"] = _TEST_HOME
    os.environ["HOME"] = _TEST_HOME

from src.trading.sim_run_log import SIM_LOG_ROOT_ENV  # noqa: E402

# v3.24.xx — set at conftest IMPORT time, not in a fixture, and this is
# the whole point.
#
# `main._get_crash_log_path` resolves the directory ONCE and caches it.
# `main` installs its diagnostic hooks at module exec and immediately
# emits a BOOT line, so the path is fixed the moment anything imports
# main -- which happens during COLLECTION, before any session-scoped
# fixture body runs. Setting this in the fixture below was too late: the
# suite still created a real crash log in ~/.acervator_logs, and the
# live-tree guard caught it on 2026-08-07.
#
# The other redirects can live in the fixture because their modules
# re-read the environment on every call. This one cannot.
#
# conftest is imported before any test module, so this is early enough.
_CRASH_LOG_TMP = Path(tempfile.mkdtemp(prefix="acervator-test-crash-"))
os.environ.setdefault("ACERVATOR_CRASH_LOG_ROOT", str(_CRASH_LOG_TMP))

# v3.25.x — the Simulator's own state file, set at conftest IMPORT time
# for the same reason and one more.
#
# `save_sim_state` and `load_sim_state` now resolve the root on every
# call, so a fixture would be soon enough for them. The module ALSO
# keeps two backwards-compatible constants that bind while the module is
# imported, and that import happens during COLLECTION, before any
# fixture body runs. Setting the variable here means even a test that
# reads the old constant gets the throwaway directory.
#
# What this prevents, measured: on 2026-08-22 a full run replaced
# ~/.acervator/simulator_bot_state.json -- the operator's saved
# Simulator fleet -- with one synthetic fixture bot. The writer is
# test_fleet_sim_infrastructure.py::test_fleet_replay_panel_mounts. It
# clicks Load on a real FleetReplayPanel; the spawn behind that button
# calls `save_sim_state` with no path. The test redirected the file it
# READ and nothing redirected the file it WROTE.
#
# The guard below SAW the write; it could not stop it. Only a redirect
# can. The guard stays exactly as it is: it is the backstop, this is the
# fix.
_SIM_STATE_TMP = Path(tempfile.mkdtemp(prefix="acervator-test-simstate-"))
os.environ.setdefault("ACERVATOR_SIM_STATE_ROOT", str(_SIM_STATE_TMP))


def _live_roots() -> tuple[Path, ...]:
    """The operator's runtime tree. Injectable so the guard below can be
    tested against fake roots instead of the real one -- a guard that can
    only be exercised by damaging the thing it protects is untestable."""
    home = Path.home()
    return (home / ".acervator", home / ".acervator_logs")


def _stone_tablet_root() -> Path:
    """The immutable archive. Lives INSIDE ~/.acervator, so it is covered
    by the roots above, but it gets its own stricter rule."""
    return Path.home() / ".acervator" / "stone_tablets"


def _home_is_redirected() -> bool:
    """True when TEST_HOME_ENV points the suite at a throwaway home.

    A live Acervator only ever writes the operator's real home, so a
    change under a redirected home can only be the suite's. The guard
    below therefore keeps full strictness in that case.
    """
    return bool(os.environ.get(TEST_HOME_ENV))


def _live_app_running() -> bool:
    """True if an Acervator process is running alongside the suite.

    This is not paranoia: measured 2026-08-05 with the suite running,
    two Acervator.exe processes were live and had rewritten
    bot_state.json 12 seconds earlier. A guard that fails whenever the
    operator has the app open is a guard that gets deleted, so
    modification-level strictness is conditioned on this.
    """
    try:
        import psutil  # type: ignore[import-untyped]

        return any(
            "acervator" in (p.info.get("name") or "").lower()
            for p in psutil.process_iter(["name"])
        )
    except Exception:  # noqa: BLE001 - absence of psutil must not fail a run
        return False


def _snapshot(roots: tuple[Path, ...]) -> dict[str, tuple[int, int]]:
    """Map every file under `roots` to (size, mtime_ns).

    stat() only -- nothing here ever OPENS a file. That is deliberate:
    ~/.acervator holds coinbase_credentials.json, and a guard that hashed
    file contents to protect the tree would itself be reading the
    credentials. Size + mtime_ns is sufficient to detect mutation.

    Measured cost: 0.05 s for 3,559 files across 7.6 GB.
    """
    out: dict[str, tuple[int, int]] = {}
    for root in roots:
        if not root.exists():
            continue
        for f in root.rglob("*"):
            try:
                if f.is_file():
                    st = f.stat()
                    out[str(f)] = (st.st_size, st.st_mtime_ns)
            except OSError:
                continue  # vanished mid-walk; the live app rotates logs
    return out


@pytest.fixture
def capture_log():
    """Capture records from a named logger, bypassing propagation.

    ``caplog`` cannot see Acervator's loggers once the logging engine has
    initialised: ``logging_engine.py:315`` sets
    ``logging.getLogger("acervator").propagate = False`` so records stop
    at that node and never reach the root handler pytest installs. A test
    asserting on logs therefore passes in isolation and fails in a full
    run, depending purely on whether some earlier test constructed the
    engine — which is exactly the flake this fixture removes.

    Usage::

        def test_x(capture_log):
            with capture_log("acervator.gui.start_all") as records:
                ...
            assert records
    """
    import logging
    from contextlib import contextmanager

    class _Sink(logging.Handler):
        def __init__(self):
            super().__init__()
            self.records: list[logging.LogRecord] = []

        def emit(self, record):
            self.records.append(record)

    @contextmanager
    def _capture(name: str, level: int = logging.DEBUG):
        target = logging.getLogger(name)
        sink = _Sink()
        sink.setLevel(level)
        prior_level = target.level
        target.addHandler(sink)
        target.setLevel(level)
        try:
            yield sink.records
        finally:
            target.removeHandler(sink)
            target.setLevel(prior_level)

    return _capture


# ---------------------------------------------------------------------
# RULE -- a silent capture is a failed capture.
# ---------------------------------------------------------------------
ACERVATOR_LOG_NODE = "acervator"

SILENT_CAPTURE_MARKER = "caplog_may_be_empty"


def silent_capture_verdict(
    caplog_record_count: int, blocked_record_count: int, *, marked: bool
) -> bool:
    """Return True when a test looked through a blind window.

    The conjunction IS the defect:

    * ``caplog_record_count == 0`` -- the test saw nothing, and
    * ``blocked_record_count > 0`` -- something DID log on the
      ``acervator`` node, at a level ``caplog`` was accepting, and the
      record stopped there because ``propagate`` is False.

    Either half alone is innocent. Together they mean the assertion the
    test made about its records was made against a list that could not
    have been anything but empty.

    ``marked`` is the explicit opt-out. See ``_silent_capture_guard``.
    """
    if marked:
        return False
    return caplog_record_count == 0 and blocked_record_count > 0


class _BlockedRecordProbe(logging.Handler):
    """Count records that reach the ``acervator`` node and stop there.

    Attached to the ``acervator`` logger, so it runs SYNCHRONOUSLY at
    emit time. That matters three times:

    * ``propagate`` is read at emit time, so a test that toggles the
      flag itself is measured correctly.
    * ``caplog.at_level(...)`` raises the capture handler's level for a
      block INSIDE the test and restores it on exit. Reading that level
      at teardown reads the restored value and is therefore useless.
      Reading it here reads the level in force when the record was
      made, which is the level that decides whether ``caplog`` would
      have kept the record. This is what keeps the guard quiet on a
      test that captures at ERROR while the code logs at INFO.
    * ``active`` bounds the count to the call phase, so records made by
      other fixtures during setup or teardown are not attributed to the
      test body.

    Nothing here changes a level or a flag. It only observes, and
    ``emit`` reads three attributes and appends to a set, so it has no
    raising path. A guard may never break the test it watches.
    """

    def __init__(self, capture_handler: logging.Handler, node: logging.Logger) -> None:
        super().__init__(level=logging.NOTSET)
        self._capture_handler = capture_handler
        self._node = node
        self.active = False
        self.blocked = 0
        self.names: set[str] = set()

    def emit(self, record: logging.LogRecord) -> None:
        if not self.active:
            return  # setup or teardown, not the test body
        if self._node.propagate:
            return  # caplog could still see it; not blind
        if record.levelno < self._capture_handler.level:
            return  # caplog would have dropped it anyway
        self.blocked += 1
        self.names.add(record.name)


@pytest.fixture(autouse=True)
def _silent_capture_guard(request: pytest.FixtureRequest) -> Iterator[None]:
    """Fail a test whose ``caplog`` window cannot see what happened.

    THE DEFECT
    ==========
    ``src/core/logging_engine.py`` sets
    ``logging.getLogger("acervator").propagate = False``. ``caplog``
    attaches its handler to the ROOT logger. So a record from any
    ``acervator.*`` logger stops at the ``acervator`` node and never
    reaches ``caplog``. A test that asserts on ``caplog.records`` then
    reads an empty list. When the assertion is a negative one -- "this
    must NOT be logged" -- the test PASSES. It fails green, which is
    why nothing pushes back on it. This has bitten twice.

    ORDER INDEPENDENCE -- HOW, EXACTLY
    ==================================
    The obvious form of this guard samples ``propagate``, and is then
    hostage to the same dependency it exists to catch: until some test
    constructs the logging engine, propagation is still on, ``caplog``
    works, and the guard stays silent.

    MEASURED on this tree 2026-08-24. Collection is alphabetical and
    deterministic -- ``pytest-randomly`` is not installed. The first
    test file to build a ``LogManager``, and so the first to set
    ``propagate = False``, is ``tests/test_c39g_bot_log_reaches_disk``
    at position 48 of 286. Nothing ever sets the flag back, so files
    1-47 run sighted and files 48-286 run blind. A prefix of the first
    35 files, 1,801 tests, ended with ``propagate=True`` and no handler
    on the node. Every ``caplog`` reader in the suite sat at positions
    23, 33 and 35 -- inside that sighted window. A sampling guard would
    have been asleep for all of them.

    So this guard does not sample the flag. It SETS it. For the
    duration of any test that requested ``caplog``, and only such a
    test, the ``acervator`` node is forced to ``propagate = False`` --
    which is the production state, because the live application always
    builds the logging engine. The test therefore meets the same wall
    in isolation, on the first file, in any collection order, that it
    would meet late in a full run. The guard is order-independent
    because it stopped reading an accidental global and now establishes
    the condition itself.

    Restoring is deliberate, not symmetrical. If the engine was built
    DURING the test it has set ``propagate = False`` and added its own
    handler to the node; restoring ``True`` would then double every
    record into the root handler. So the flag returns to its prior
    value only while the node still has no handlers of its own.

    COST
    ====
    A test that did not request ``caplog`` returns on the first line.
    No handler is attached, no flag is touched, no teardown work runs.

    THE OPT-OUT
    ===========
    ``@pytest.mark.caplog_may_be_empty("reason")`` suppresses the
    guard. It exists for the one shape the guard cannot read: a test
    that watches a NON-Acervator logger (``urllib3``, ``asyncio``) and
    expects nothing from it, while unrelated Acervator logging happens
    in the background. The guard sees an empty ``caplog`` beside
    blocked Acervator records and cannot know the test never cared
    about them. State a reason. The marker is not a silencer.

    THE FIX, WHEN IT FIRES
    ======================
    Use the ``capture_log`` fixture above. It attaches to the named
    logger directly and does not depend on propagation at all.

    WHAT IT DOES NOT SEE
    ====================
    One node, ``acervator``. A test blinded by ``propagate = False``
    on some other logger is outside this guard, and so is a test
    blinded by a filter, a disabled logger or a level set on the root.
    The rule is named for one measured defect and is scoped to it.
    """
    if "caplog" not in request.fixturenames:
        yield
        return

    caplog = request.getfixturevalue("caplog")
    node = logging.getLogger(ACERVATOR_LOG_NODE)
    probe = _BlockedRecordProbe(caplog.handler, node)
    prior_propagate = node.propagate
    node.addHandler(probe)
    node.propagate = False
    probe.active = True
    try:
        yield
    finally:
        probe.active = False
        node.removeHandler(probe)
        # Keep False if the engine claimed the node during this test.
        node.propagate = False if node.handlers else prior_propagate

    marked = request.node.get_closest_marker(SILENT_CAPTURE_MARKER) is not None
    seen = len(caplog.get_records("call"))
    if silent_capture_verdict(seen, probe.blocked, marked=marked):
        pytest.fail(
            "A silent capture is a failed capture.\n"
            "  caplog.records          : 0\n"
            f"  blocked on 'acervator'  : {probe.blocked}\n"
            f"  loggers                 : {sorted(probe.names)}\n"
            "logging_engine sets acervator.propagate = False, so these "
            "records never reach the root handler caplog installs. This "
            "test asserted on a list that could not have been anything "
            "but empty.\n"
            "Fix: use the `capture_log` fixture with the logger name. "
            "If an empty list is genuinely the pass condition for a "
            "NON-Acervator logger, mark the test with "
            "@pytest.mark.caplog_may_be_empty and state the reason.",
            pytrace=False,
        )


@pytest.fixture(scope="session", autouse=True)
def _redirect_sim_log_root():
    """Point the sim run log at a throwaway directory for the whole
    session, before any test constructs a SimRunLog."""
    tmp = tempfile.mkdtemp(prefix="acervator-test-sim-")
    prior = os.environ.get(SIM_LOG_ROOT_ENV)
    os.environ[SIM_LOG_ROOT_ENV] = tmp
    try:
        yield Path(tmp)
    finally:
        if prior is None:
            os.environ.pop(SIM_LOG_ROOT_ENV, None)
        else:
            os.environ[SIM_LOG_ROOT_ENV] = prior


@pytest.fixture(scope="session", autouse=True)
def _redirect_writable_roots():
    """Redirect every remaining live-tree writer for the whole session.

    v3.24.42 (C14 family). ``_redirect_sim_log_root`` covered the sim run
    log and nothing else, so two writers kept reaching the operator's
    runtime tree on every full run:

      ~/.acervator/feature_telemetry.json      feature_telemetry
      ~/.acervator_logs/feature_validation.md  feature_telemetry
      ~/.acervator/settings.json               PrivacyMaskRegistry

    The telemetry pair had a working override that nothing set. The
    settings file had no override at all, and PrivacyMaskRegistry
    auto-persists on EVERY set_masked, so any test touching privacy
    behaviour silently rewrote the operator's real settings file.

    This went unnoticed because the live-tree guard downgrades modified
    pre-existing files to a warning while a live Acervator process is
    running -- which it usually is on the developer's machine. The
    breach only surfaced on a run with the app closed. A guard that is
    conditional on the environment is a guard you have to run in the
    right environment to trust.
    """
    from src.core.feature_telemetry import TELEMETRY_ROOT_ENV
    from src.core.privacy_mask_registry import SETTINGS_ROOT_ENV
    from src.trading.capital_reservation import RESERVATION_ROOT_ENV

    tmp_root = Path(tempfile.mkdtemp(prefix="acervator-test-roots-"))
    (tmp_root / "acervator").mkdir(parents=True, exist_ok=True)
    (tmp_root / "acervator_logs").mkdir(parents=True, exist_ok=True)

    # _telemetry_root returns the override AS-IS -- it does NOT append
    # the ".acervator" / ".acervator_logs" leaf when one is set, so both
    # of its files land directly in tmp_root. The privacy registry wants
    # the directory that directly holds settings.json. Different shapes,
    # which is why they are not one variable.
    # v3.24.xx — the crash logger was the last unredirected writer. Its
    # constant lives in main.py and main.py is NOT imported here on
    # purpose: importing it installs the diagnostic hooks and emits a
    # BOOT line, which is itself a write. The literal is locked to
    # main.CRASH_LOG_ROOT_ENV by test_crash_log_redirect.py so a rename
    # breaks a test rather than silently un-redirecting the guard.
    overrides = {
        TELEMETRY_ROOT_ENV: str(tmp_root),
        SETTINGS_ROOT_ENV: str(tmp_root / "acervator"),
        "ACERVATOR_CRASH_LOG_ROOT": str(tmp_root / "acervator_logs"),
        # The capital-reservation singleton (get_registry) autosaves to
        # reservation_state.json; without this every test that touched it
        # wrote into the operator's real ~/.acervator.
        RESERVATION_ROOT_ENV: str(tmp_root / "acervator"),
    }
    prior = {k: os.environ.get(k) for k in overrides}
    os.environ.update(overrides)
    try:
        yield tmp_root
    finally:
        for k, v in prior.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@pytest.fixture(scope="session", autouse=True)
def _isolate_privacy_registry(_redirect_writable_roots):
    """Hand the whole suite a privacy register that saves nothing.

    A GUI surface builds its module-level model while it is imported and
    that model reads the register, so the process-wide register exists
    from COLLECTION, before SETTINGS_ROOT_ENV above is set. This one has
    autosave off and a throwaway path; the collected one is put back at
    the end.
    """
    from src.core import privacy_mask_registry as registry_module

    throwaway = registry_module.PrivacyMaskRegistry(
        settings_path=_redirect_writable_roots / "acervator" / "settings.json",
        autosave=False,
    )
    collected = registry_module._SINGLETON
    registry_module._SINGLETON = throwaway
    try:
        yield throwaway
    finally:
        registry_module._SINGLETON = collected


def _classify(
    before: dict[str, tuple[int, int]],
    after: dict[str, tuple[int, int]],
    tablet_root: Path,
) -> tuple[list[str], list[str], list[str]]:
    """Split the diff into (created, tablet_touched, modified).

    Separated from the fixture so it can be unit-tested on synthetic
    dicts -- see tests/test_live_tree_guard.py.
    """
    created = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    modified = sorted(p for p in (set(before) & set(after)) if before[p] != after[p])
    tr = str(tablet_root)
    tablet_touched = sorted(
        p for p in (created + removed + modified) if p.startswith(tr)
    )
    created = [p for p in created if not p.startswith(tr)]
    modified = [p for p in modified if not p.startswith(tr)]
    # A removal outside the tablet archive is reported with modifications;
    # the live app rotates logs, so removals there are routine.
    modified += [f"{p} (REMOVED)" for p in removed if not p.startswith(tr)]
    return created, tablet_touched, modified


@pytest.fixture(scope="session", autouse=True)
def _assert_no_live_tree_writes(_redirect_sim_log_root):
    """Fail if the suite mutated the operator's runtime tree.

    WHAT THE PREVIOUS VERSION MISSED
    ================================
    It watched exactly one directory -- ``~/.acervator_logs/sim/runs`` --
    and compared only the NAMES of its immediate children. ``_LIVE_ROOTS[0]``
    (``~/.acervator``) was defined and never used. So it could not see:

      * anything written anywhere under ``~/.acervator`` -- bot_state.json,
        reservation_state.json, feature_telemetry.json, credentials
      * anything in ``~/.acervator_logs`` outside ``sim/runs``
      * modification or deletion of an EXISTING file, only new names
      * the Stone Tablet archive

    Both isolation breaches this project has shipped landed in
    ``~/.acervator`` -- the sim capital registry autosaving
    reservation_state.json, and feature_telemetry writing to the live
    tree. **Both happened while this guard was green.** It was not a
    weak guard; for those two defects it was not a guard at all.

    THREE RULES, DELIBERATELY DIFFERENT IN STRICTNESS
    =================================================
    1. **Any newly created path fails, always.** The suite has no
       business creating files here, and this is the shape both real
       breaches took.
    2. **Any change under the Stone Tablet archive fails, always** --
       created, modified or deleted. Operator's standing rule is
       absolute, and normal trading never writes there.
    3. **Modification of a pre-existing file fails only when no live
       Acervator process is running.** Measured 2026-08-05: the operator
       had two Acervator.exe processes up while the suite ran, and the
       live app had rewritten bot_state.json 12 seconds earlier. Failing
       on that would make the guard fire on almost every run, and a
       guard that cries wolf gets deleted. When the app IS running the
       modifications are still PRINTED, so a real breach stays visible
       rather than silent.
    """
    roots = _live_roots()
    tablet_root = _stone_tablet_root()
    before = _snapshot(roots)
    yield
    after = _snapshot(roots)
    created, tablet_touched, modified = _classify(before, after, tablet_root)

    problems: list[str] = []
    live_up = _live_app_running() and not _home_is_redirected()

    # v3.24.42 — created and modified are now treated SYMMETRICALLY with
    # respect to a running app.
    #
    # Rule 1 used to fail on any created path unconditionally, while
    # rule 3 excused modified paths when a live Acervator process was
    # up. That asymmetry made the app frame the suite: launching
    # Acervator mid-run produces a preflight snapshot trio plus
    # console_*/crash_*/faulthandler_* logs, all newly created, and the
    # guard reported them as a suite breach. Observed 2026-08-06.
    #
    # A guard that cries wolf is worse than a lenient one, because the
    # next real breach gets waved through by a developer who has learned
    # to ignore it. So: with a live process up, both categories are
    # reported loudly and not failed.
    #
    # THE COST, stated plainly: while Acervator is running, this guard
    # cannot attribute a write and therefore cannot catch a real suite
    # breach. The trustworthy configuration is a run with the app
    # CLOSED, and the banner below says so on every degraded run rather
    # than letting a green suite imply a verified one.
    if live_up and (created or modified or tablet_touched):
        print(
            f"\n[live-tree guard] DEGRADED — a live Acervator process is "
            f"running, so live-tree changes cannot be attributed to the "
            f"suite and are NOT being failed.\n"
            f"  created {len(created)}, modified {len(modified)}, "
            f"tablet {len(tablet_touched)}\n"
            f"  This run does NOT verify test isolation. Re-run with "
            f"Acervator closed for that.\n  "
            + "\n  ".join((created + modified + tablet_touched)[:8])
        )
    else:
        if created:
            problems.append(
                f"created {len(created)} path(s) in the operator's live "
                f"tree:\n  " + "\n  ".join(created[:10])
            )
        if tablet_touched:
            problems.append(
                f"touched {len(tablet_touched)} Stone Tablet file(s) -- the "
                f"archive is immutable:\n  " + "\n  ".join(tablet_touched[:10])
            )
        if modified:
            problems.append(
                f"modified {len(modified)} pre-existing file(s) with no live "
                f"Acervator process running:\n  " + "\n  ".join(modified[:10])
            )

    assert not problems, (
        "the test suite mutated the operator's runtime tree.\n\n"
        + "\n\n".join(problems)
        + "\n\nTests must never write to ~/.acervator or ~/.acervator_logs. "
        "Redirect the writer at its root-resolution point (see "
        "SIM_LOG_ROOT_ENV / ACERVATOR_TELEMETRY_ROOT for the pattern)."
    )


# ── Qt widget teardown, suite-wide ───────────────────────────────────
#
# v3.24.97. Qt keeps a PARENTLESS widget alive for the life of the
# process. The GUI tests build whole SimulatorTab / FleetReplayPanel /
# BotLiveSettingsDialog trees, so without an explicit teardown they
# accumulate until the interpreter dies with SIGSEGV -- measured at
# exit 139 around 90% of the suite, with NO failure summary printed.
# The release gate reported "pytest failed:" followed by nothing, which
# reads as a broken gate rather than a crashing suite.
#
# Placed here rather than in each GUI test file: it applies to every
# test that ever builds a widget, including ones not yet written, and
# six separate copies of the same fixture is six places for it to rot.
#
# ── issue #101, v3.26.x — THE RECIPE DESTROYED NOTHING ───────────────
#
# The fixture did `hide()`, `setParent(None)`, `deleteLater()`, then
# `processEvents()`. Measured 2026-08-24, PySide6 on the offscreen
# plugin, one line of output each:
#
#     parentless dialog, Python reference dropped     0 alive
#     deleteLater() first, then reference dropped     1 alive
#     after sendPostedEvents(None, DeferredDelete)    0 alive
#
# `deleteLater()` posts a `DeferredDelete` event, and
# `QApplication.processEvents()` NEVER DELIVERS ONE. Only a running
# event loop, or an explicit `sendPostedEvents`, does. So every widget
# the fixture "cleaned up" stayed in `QApplication.topLevelWidgets()`
# for the rest of the session, and anything that walks that list -- as
# tests/test_sim_visuals_expand_reentrancy.py does -- read a stranger.
#
# ── WHAT THE OLD FIXTURE REALLY PROVIDED, AND WHICH LINE ─────────────
#
# It provided IMMORTALITY, not destruction, and that is what kept the
# process alive. Measured 2026-08-24, one ExchangeTab built and the
# script then allowed to exit:
#
#     no cleanup at all                        exit 127
#     hide() + setParent(None)                 exit 127
#     hide() + setParent(None) + deleteLater() exit 0
#
# `w.deleteLater()` IS THE LINE. It moves ownership from Python to C++
# -- `Shiboken.ownedByPython` reads True before the call and False
# after -- so Python's shutdown frees no widget and no widget is ever
# destroyed. `hide()` and `setParent(None)` provide nothing here; the
# first two rows above are the control that proves it.
#
# The same control at suite scale, 2026-08-24: with the body of this
# fixture replaced by a bare `yield`, a full `pytest tests` run reached
# 76% and died with exit 139 -- SIGSEGV, no failure summary. The
# docstring's claim was true. Keep `deleteLater()`.
#
# WHY DESTRUCTION KILLS THE PROCESS. `ExchangeTab` owns a
# `CryptoNewsTicker`, and `crypto_news_ticker.py:386` builds
# `QThread(self)` -- a thread PARENTED to the widget. Destroying the
# widget destroys a RUNNING QThread, which Qt answers with
# `std::terminate`: no traceback, no failure summary, exit 127. The
# first honest attempt at this repair -- a global
# `sendPostedEvents(None, DeferredDelete)` -- died exactly there, 2573
# tests into a full run, at `test_exchange_tab_boot_smoke.py`.
#
# ── THE REPAIR ───────────────────────────────────────────────────────
#
# 1. STOP THE THREADS FIRST. `quit()` then a bounded `wait()`. Measured
#    on the news ticker: `wait(3000)` returned True after 0.54 s, and
#    the widget then destroyed with exit 0.
# 2. DELIVER PER WIDGET, NOT GLOBALLY. `sendPostedEvents(w, ...)` sends
#    only the events posted to `w`. The global form also delivers the
#    `deleteLater()` calls SHIPPED code made on objects this fixture
#    never chose -- QThreads among them. Per-widget delivery destroys
#    what the fixture handled and touches nothing else.
# 3. SPARE WHAT WOULD ABORT. A widget whose thread will not stop keeps
#    the old immortality, and its address is recorded so the leak guard
#    below reports it by name instead of failing a file that has no fix
#    for it.
# 4. REPEAT UNTIL THE LIST IS EMPTY. Destroying a widget can EXPOSE new
#    top-level widgets: measured on `test_suite_integrity.py`, tearing
#    down a MainWindow left four `QMenu` popups behind with no parent
#    and no Python owner. They were never in the first pass's list, so
#    a single sweep could not reach them. The loop is bounded at
#    `_MAX_TEARDOWN_PASSES` so a widget that respawns cannot hang the
#    suite; a pass that destroys nothing ends it early.
_MAX_TEARDOWN_PASSES = 4
_WIDGET_TEARDOWN_WAIT_MS = 2000

# Addresses of widgets deliberately left alive because destroying them
# would abort the process. Runtime facts, not a name allowlist: the only
# way onto this list is to still own a running QThread after a bounded
# wait.
_SPARED_WIDGETS: dict[int, str] = {}


def _live_top_level_widgets() -> dict[int, str]:
    """Map every live top-level widget to its type name, by C++ address.

    The address is the identity, not the Python wrapper: a wrapper can
    be recreated for the same C++ object. An address CAN be reused after
    a destruction, which makes a brand-new widget look like an old one.
    That direction is deliberate. The leak guard below then UNDER-reports
    rather than accusing an innocent file.
    """
    try:
        from PySide6.QtWidgets import QApplication
        from shiboken6 import Shiboken
    except ImportError:  # pragma: no cover
        return {}
    app = QApplication.instance()
    if app is None:
        return {}
    live: dict[int, str] = {}
    for w in list(app.topLevelWidgets()):
        try:
            if not Shiboken.isValid(w):
                continue
            live[Shiboken.getCppPointer(w)[0]] = type(w).__name__
        except (RuntimeError, AttributeError):  # pragma: no cover
            continue  # destroyed mid-walk
    return live


def _stop_owned_threads(widget: QWidget) -> int:
    """Stop every QThread under `widget`. Return how many still run.

    A QThread destroyed while it runs makes Qt call `std::terminate`.
    The widget teardown below therefore asks first and destroys second.
    """
    try:
        from PySide6.QtCore import QThread
    except ImportError:  # pragma: no cover
        return 0
    try:
        running = [t for t in widget.findChildren(QThread) if t.isRunning()]
    except RuntimeError:  # pragma: no cover
        return 0  # already destroyed
    for t in running:
        try:
            t.quit()
            t.wait(_WIDGET_TEARDOWN_WAIT_MS)
        except RuntimeError:  # pragma: no cover
            continue
    left = 0
    for t in running:
        try:
            if t.isRunning():
                left += 1
        except RuntimeError:  # pragma: no cover
            continue
    return left


@pytest.fixture(autouse=True)
def _destroy_qt_widgets() -> Iterator[None]:
    yield
    try:
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtWidgets import QApplication
        from shiboken6 import Shiboken
    except ImportError:  # pragma: no cover
        return
    app = QApplication.instance()
    if app is None:
        return

    for _pass in range(_MAX_TEARDOWN_PASSES):
        doomed = []
        for w in list(app.topLevelWidgets()):
            try:
                if not Shiboken.isValid(w):
                    continue
                w.hide()
                if _stop_owned_threads(w):
                    # Destroying this one calls std::terminate. Hand it
                    # to C++ and never deliver the event, which is what
                    # the whole fixture used to do to everything.
                    _SPARED_WIDGETS[Shiboken.getCppPointer(w)[0]] = type(w).__name__
                    w.deleteLater()
                    continue
                w.setParent(None)
                w.deleteLater()
                doomed.append(w)
            except RuntimeError:
                # Already destroyed by its own parent; nothing to do.
                continue
        app.processEvents()
        for w in doomed:
            try:
                if Shiboken.isValid(w):
                    QCoreApplication.sendPostedEvents(w, QEvent.Type.DeferredDelete)
            except RuntimeError:  # pragma: no cover
                continue  # a parent in this same list took it first
        if not doomed:
            break  # nothing left this pass could own
        try:
            if not [
                w
                for w in app.topLevelWidgets()
                if Shiboken.getCppPointer(w)[0] not in _SPARED_WIDGETS
            ]:
                break  # the list is empty; no second look
        except RuntimeError:  # pragma: no cover
            break


# ── A leak fails in the file that caused it ──────────────────────────
#
# issue #101. Before this fixture a leaked widget failed a STRANGER.
# `tests/test_sim_visuals_expand_reentrancy.py` asks
# `app.topLevelWidgets()` for every open QDialog and takes element
# zero. One dialog left behind by ANY earlier file makes element zero
# the wrong widget, and the test then reports its own subject as leaked
# while it examines somebody else's. Three units spent a full diagnosis
# each on that shape on 2026-08-23 -- issues #96 and #98, and the
# referee who repaired #98's fallout. Every one of them started from
# "a neighbour test broke".
#
# WHY THIS GUARD CANNOT BECOME THE FLAKY THING EVERYONE DISABLES:
#
#  1. IT IS BASELINE-RELATIVE. Each file is judged only on the widgets
#     it ADDED. A leak from an earlier file cannot fail a later one, so
#     one defect gives exactly one failure, and it is in the file that
#     holds the fix. This one property stops the cascade.
#  2. IT RUNS AFTER `_destroy_qt_widgets`. Module-scoped finalizers run
#     after function-scoped ones, so it measures what survived a real
#     destruction pass, not what a test left bound in a local.
#  3. IT NEEDS NO RUN ORDER. No file's result depends on which files ran
#     before it, so `-k`, a single-file run and a full run all agree.
#  4. THERE IS NO ALLOWLIST AND NO ENVIRONMENT SWITCH. An allowlist rots
#     into a list of accepted leaks, and a switch is how a guard dies.
#     The only exclusion is `_SPARED_WIDGETS`, and a widget earns a
#     place there by still owning a running QThread -- a fact measured
#     at teardown, not a name written down in advance. Those are
#     PRINTED with the file that made them, so they stay visible.
#  5. A NON-GUI FILE PAYS NOTHING. With no QApplication both snapshots
#     are empty dicts.
@pytest.fixture(scope="module", autouse=True)
def _assert_no_widget_leak(request: pytest.FixtureRequest) -> Iterator[None]:
    """Fail the FILE that left a top-level Qt widget alive."""
    before = _live_top_level_widgets()
    yield
    after = _live_top_level_widgets()
    new = {a: n for a, n in after.items() if a not in before}
    spared = {a: n for a, n in new.items() if a in _SPARED_WIDGETS}
    leaked = {a: n for a, n in new.items() if a not in _SPARED_WIDGETS}

    import collections

    where = Path(getattr(request.module, "__file__", str(request.module))).name
    if spared:
        print(
            f"\n[widget teardown] {where} left "
            f"{len(spared)} widget(s) alive that cannot be destroyed: "
            + ", ".join(
                f"{n} x {t}"
                for t, n in collections.Counter(spared.values()).most_common()
            )
            + ". Each still owned a running QThread after "
            f"{_WIDGET_TEARDOWN_WAIT_MS} ms, and destroying a running "
            "QThread aborts the process."
        )
    if not leaked:
        return

    by_type = collections.Counter(leaked.values()).most_common()
    raise AssertionError(
        f"{where} left {len(leaked)} top-level Qt widget(s) alive after "
        f"its last test:\n  "
        + "\n  ".join(f"{n} x {t}" for t, n in by_type)
        + "\n\nA surviving widget is not local. Anything that walks "
        "`QApplication.topLevelWidgets()` -- and "
        "tests/test_sim_visuals_expand_reentrancy.py does -- then "
        "reads a widget from THIS file and reports the failure "
        "against ITSELF.\n\n"
        "THE REPAIR IS IN THIS FILE. The owner destroys the widget:\n"
        "    w.close()\n"
        "    w.setParent(None)          # only if it HAD a parent\n"
        "then drops the last Python reference to it. A parentless\n"
        "widget with no Python reference dies at once.\n\n"
        "DO NOT clean up with `deleteLater()`. That hands the object\n"
        "to C++ and posts a `DeferredDelete` event which\n"
        "`processEvents()` does not deliver, so the call MAKES the\n"
        "leak. If a `deleteLater()` is unavoidable, deliver the event\n"
        "to that object:\n"
        "    QCoreApplication.sendPostedEvents(\n"
        "        w, QEvent.Type.DeferredDelete)\n\n"
        "Read the answer into a local FIRST, destroy SECOND, return\n"
        "THIRD. And assert the count in a FIXTURE. `with _dialog() as\n"
        "d:` binds the widget in the test frame too, so a check inside\n"
        "the context manager can never see zero.",
    )


# --------------------------------------------------------------------------- #
# CI lane markers, applied by file (see [tool.pytest.ini_options].markers).    #
#                                                                              #
# Two lanes keep PR CI fast without losing coverage on merge:                  #
#   * `slow`      — end-to-end engine-replay suites. Each test builds a real   #
#                   FleetReplayController and plays synthetic candles through  #
#                   the live Scrum/Fold + TA engine; these are minutes of CPU  #
#                   and dominate the suite's wall clock.                       #
#   * `archetype` — archetype-harness tests. They shell out to heavy analyzers #
#                   (semgrep/mypy/vulture/vale/opencv) that ship only in the   #
#                   [dev] extra, so the fast lane — which installs [test] only #
#                   — must deselect them.                                      #
#                                                                              #
# Marking by file here (rather than a `pytestmark` in each module) keeps the   #
# lane definition in one auditable place and covers files added later that     #
# match the pattern.                                                           #
#                                                                              #
# `lane_marks` is the one definition. `tests/test_ci_fast_lane_packages.py`    #
# reads the same function to decide which files the fast lane collects.        #


# ── A crashed worker says what it was doing ──────────────────────────
#
# `pytest -n auto` reports a dead worker as one line -- "worker 'gw0'
# crashed while running <nodeid>" -- and nothing else. The worker's own
# stderr does not reach the master's log, so a SIGSEGV or a
# std::terminate arrives as silence. Measured on CI runs 33338069499 and
# 33341814352: both named the node id and printed no traceback.
#
# Each process holds one breadcrumb file. `logstart` writes the node id
# into it and re-arms faulthandler to dump there; `logfinish` empties it.
# A file still holding a node id at the end of the run names the test the
# process died inside, and carries the native traceback after it.
#
# faulthandler is re-armed per test, not once per session, because
# another test re-points it: tests/test_faulthandler_log_redirect.py
# drives the real `main._setup_faulthandler` and restores it to the
# handle main opened, not to this one.
_BREADCRUMB_ENV = "ACERVATOR_TEST_BREADCRUMBS"
os.environ.setdefault(
    _BREADCRUMB_ENV, tempfile.mkdtemp(prefix="acervator-test-breadcrumb-")
)
_BREADCRUMB_DIR = Path(os.environ[_BREADCRUMB_ENV])
_BREADCRUMB_HANDLE: list = []


def _breadcrumb_write(text: str) -> None:
    """Replace the breadcrumb with `text`, or empty it when `text` is empty."""
    if not _BREADCRUMB_HANDLE:
        return
    handle = _BREADCRUMB_HANDLE[0]
    try:
        handle.seek(0)
        handle.truncate()
        if text:
            handle.write(text + "\n")
        handle.flush()
    except (ValueError, OSError):  # pragma: no cover - handle already closed
        return


def pytest_configure(config: pytest.Config) -> None:
    worker = getattr(config, "workerinput", {}).get("workerid", "main")
    _BREADCRUMB_DIR.mkdir(parents=True, exist_ok=True)
    path = _BREADCRUMB_DIR / ("%s.txt" % worker)
    try:
        _BREADCRUMB_HANDLE.append(path.open("w", encoding="utf-8", newline="\n"))
    except OSError:  # pragma: no cover - no writable temp dir
        return


def pytest_runtest_logstart(nodeid: str) -> None:
    _breadcrumb_write(nodeid)
    if _BREADCRUMB_HANDLE:
        try:
            faulthandler.enable(file=_BREADCRUMB_HANDLE[0], all_threads=True)
        except (ValueError, OSError, RuntimeError):  # pragma: no cover
            return


def pytest_runtest_logfinish(nodeid: str) -> None:
    _breadcrumb_write("")


def pytest_sessionfinish(session: pytest.Session) -> None:
    """Print the breadcrumb of every process that died mid-test."""
    if hasattr(session.config, "workerinput"):
        return
    died = []
    for path in sorted(_BREADCRUMB_DIR.glob("*.txt")):
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:  # pragma: no cover
            continue
        if text:
            died.append("%s died inside:\n%s" % (path.stem, text))
    if died:
        session.config.get_terminal_writer().line("\n" + "\n\n".join(died))


def pytest_collection_modifyitems(items):
    from tests.fixtures.ci_lanes import lane_marks

    for item in items:
        for mark in lane_marks(Path(str(item.fspath)).name):
            item.add_marker(getattr(pytest.mark, mark))
