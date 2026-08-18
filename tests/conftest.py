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

Scope note: this redirects the SIM log root only. ``~/.acervator``
(bot_state.json, credentials) is operator-owned and read-only to the
suite; nothing here grants write access to it.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

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
        return any("acervator" in (p.info.get("name") or "").lower()
                   for p in psutil.process_iter(["name"]))
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
                continue          # vanished mid-walk; the live app rotates logs
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


def _classify(before: dict[str, tuple[int, int]],
              after: dict[str, tuple[int, int]],
              tablet_root: Path) -> tuple[list[str], list[str], list[str]]:
    """Split the diff into (created, tablet_touched, modified).

    Separated from the fixture so it can be unit-tested on synthetic
    dicts -- see tests/test_live_tree_guard.py.
    """
    created = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    modified = sorted(p for p in (set(before) & set(after))
                      if before[p] != after[p])
    tr = str(tablet_root)
    tablet_touched = sorted(
        p for p in (created + removed + modified) if p.startswith(tr))
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
    live_up = _live_app_running()

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
            + "\n  ".join((created + modified + tablet_touched)[:8]))
    else:
        if created:
            problems.append(
                f"created {len(created)} path(s) in the operator's live "
                f"tree:\n  " + "\n  ".join(created[:10]))
        if tablet_touched:
            problems.append(
                f"touched {len(tablet_touched)} Stone Tablet file(s) -- the "
                f"archive is immutable:\n  "
                + "\n  ".join(tablet_touched[:10]))
        if modified:
            problems.append(
                f"modified {len(modified)} pre-existing file(s) with no live "
                f"Acervator process running:\n  " + "\n  ".join(modified[:10]))

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
@pytest.fixture(autouse=True)
def _destroy_qt_widgets():
    yield
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:                                # pragma: no cover
        return
    app = QApplication.instance()
    if app is None:
        return
    for w in list(app.topLevelWidgets()):
        try:
            w.hide()
            w.setParent(None)
            w.deleteLater()
        except RuntimeError:
            # Already destroyed by its own parent; nothing to do.
            continue
    app.processEvents()
