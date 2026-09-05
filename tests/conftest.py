"""Suite-wide isolation from the operator's runtime tree.

``TEST_HOME_ENV`` and the overrides in ``_redirect_writable_roots`` point every
writer at a throwaway directory, so no test writes into ``~/.acervator`` or
``~/.acervator_logs``. ``_snapshot`` reads both ``_live_roots`` before and after the
run and fails on a change the suite can be held to. ``_destroy_qt_widgets`` and
``_assert_no_widget_leak`` stop a Qt widget outliving the file that built it.
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
    from PySide6.QtWidgets import QApplication, QWidget

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

from tests.fixtures.qt_platform import choose_qt_platform

# The first QApplication fixes the platform for the whole process.
choose_qt_platform()

from src.trading.sim_run_log import SIM_LOG_ROOT_ENV  # noqa: E402

# Set at import: `main._get_crash_log_path` caches its directory on the first call.
_CRASH_LOG_TMP = Path(tempfile.mkdtemp(prefix="acervator-test-crash-"))
os.environ.setdefault("ACERVATOR_CRASH_LOG_ROOT", str(_CRASH_LOG_TMP))

# Set at import: `SIM_STATE_PATH` and `BOT_STATE_PATH` bind while their module loads.
_SIM_STATE_TMP = Path(tempfile.mkdtemp(prefix="acervator-test-simstate-"))
os.environ.setdefault("ACERVATOR_SIM_STATE_ROOT", str(_SIM_STATE_TMP))


def _live_roots() -> tuple[Path, ...]:
    """Return ``~/.acervator`` and ``~/.acervator_logs``, the roots the guard watches."""
    home = Path.home()
    return (home / ".acervator", home / ".acervator_logs")


def _stone_tablet_root() -> Path:
    """Return the stone tablet archive, a subtree of ``_live_roots`` with a stricter rule."""
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

    A live process writes the same tree ``_snapshot`` reads, so the guard
    downgrades its verdict to a report while this is True.
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

    Uses ``stat`` only and opens nothing, so the walk never reads
    ``coinbase_credentials.json``.
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

    The logging engine sets ``propagate = False`` on the ``acervator`` node, so
    records stop there and never reach the root handler ``caplog`` installs.

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


# RULE -- a silent capture is a failed capture.
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
    """Redirect every live-tree writer ``_redirect_sim_log_root`` does not cover.

    Sets ``TELEMETRY_ROOT_ENV``, ``SETTINGS_ROOT_ENV``, ``RESERVATION_ROOT_ENV``
    and the crash-log root at one throwaway directory for the whole session, and
    restores each prior value on teardown.
    """
    from src.core.feature_telemetry import TELEMETRY_ROOT_ENV
    from src.core.privacy_mask_registry import SETTINGS_ROOT_ENV
    from src.trading.capital_reservation import RESERVATION_ROOT_ENV

    tmp_root = Path(tempfile.mkdtemp(prefix="acervator-test-roots-"))
    (tmp_root / "acervator").mkdir(parents=True, exist_ok=True)
    (tmp_root / "acervator_logs").mkdir(parents=True, exist_ok=True)

    # `_telemetry_root` returns the override as-is and appends no leaf to it.
    # The crash-log key is a literal: importing main writes a BOOT line.
    overrides = {
        TELEMETRY_ROOT_ENV: str(tmp_root),
        SETTINGS_ROOT_ENV: str(tmp_root / "acervator"),
        "ACERVATOR_CRASH_LOG_ROOT": str(tmp_root / "acervator_logs"),
        # `get_registry` autosaves reservation_state.json beneath this root.
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
    """Split the diff between two ``_snapshot`` results into
    (created, tablet_touched, modified)."""
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


_LIVE_APP_CREATES: dict[str, str] = {
    ".acervator/preflight/": (
        "StateManager.preflight_snapshot copies bot_state.json under a "
        "launch timestamp"
    ),
    ".acervator/ta_snapshots/": (
        "indicator_panel writes one hash-named snapshot per indicator read"
    ),
    ".acervator_logs/trade/pnl/daily/": (
        "PnLCascade opens <date>.ndjson when the date changes"
    ),
    ".acervator_logs/console_": (
        "acervator_watchdog opens console_<timestamp>.log per launch"
    ),
    ".acervator_logs/crash_": (
        "main._get_crash_log_path opens crash_<timestamp>.log per launch"
    ),
    ".acervator_logs/faulthandler_": (
        "main._setup_faulthandler opens faulthandler_<timestamp>.log per launch"
    ),
    ".acervator_logs/postmortem_": (
        "acervator_watchdog.write_postmortem bundles the logs of a child it "
        "found crashed or stalled"
    ),
    ".acervator_logs/thread_violation_": (
        "_on_api_event appends thread_violation_<date>.log when it refuses a "
        "call arriving off the GUI thread"
    ),
}
"""The only new paths a running Acervator writes under ``_live_roots``.

Each key is a literal location and each value names the writer behind it.
``_excused_by_the_live_app`` matches nothing else, and only while
``_live_app_running`` is true.
"""


def _excused_by_the_live_app(path: str, roots: tuple[Path, ...]) -> str:
    """Return the ``_LIVE_APP_CREATES`` reason covering `path`, or "" for none."""
    for root in roots:
        prefix = f"{root}{os.sep}"
        if not path.startswith(prefix):
            continue
        rest = f"{root.name}/{path[len(prefix):]}".replace(os.sep, "/")
        for key, reason in _LIVE_APP_CREATES.items():
            if rest.startswith(key):
                return reason
    return ""


@pytest.fixture(scope="session", autouse=True)
def _assert_no_live_tree_writes(_redirect_sim_log_root):
    """Fail if the suite mutated the operator's runtime tree.

    ``_snapshot`` brackets the session and ``_classify`` splits the diff into
    three rules of deliberately different strictness: every path in ``created``
    fails except the ones ``_excused_by_the_live_app`` names, every
    ``tablet_touched`` path fails, and ``modified`` fails only while
    ``_live_app_running`` is false and is printed otherwise.
    """
    roots = _live_roots()
    tablet_root = _stone_tablet_root()
    before = _snapshot(roots)
    yield
    after = _snapshot(roots)
    created, tablet_touched, modified = _classify(before, after, tablet_root)

    problems: list[str] = []
    live_up = _live_app_running() and not _home_is_redirected()

    excused: list[str] = []
    if live_up and created:
        kept: list[str] = []
        for path in created:
            reason = _excused_by_the_live_app(path, roots)
            if reason:
                excused.append(f"{path}\n      {reason}")
            else:
                kept.append(path)
        created = kept

    if excused:
        print(
            f"\n[live-tree guard] EXCUSED {len(excused)} path(s) a running "
            f"Acervator creates:\n    " + "\n    ".join(excused[:8])
        )

    if live_up and modified:
        print(
            f"\n[live-tree guard] DEGRADED — a live Acervator process is "
            f"running, so a modified pre-existing file cannot be attributed "
            f"to the suite and is NOT being failed.\n"
            f"  modified {len(modified)}\n"
            f"  This run does NOT verify isolation against modification. "
            f"Re-run with Acervator closed for that.\n  " + "\n  ".join(modified[:8])
        )
        modified = []

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


_MAX_TEARDOWN_PASSES = 4
_WIDGET_TEARDOWN_WAIT_MS = 2000

# Widgets that still owned a running QThread after a bounded wait, by C++ address.
_SPARED_WIDGETS: dict[int, str] = {}

# Non-widget entries `QApplication.topLevelWidgets()` returned, by C++
# address and type name.
_ALIASED_ENTRIES: dict[int, str] = {}


def _top_level_windows(app: QApplication) -> list[QWidget]:
    """Return the widgets in `app.topLevelWidgets()`, recording every entry that is not one."""
    from PySide6.QtWidgets import QWidget as _QWidget
    from shiboken6 import Shiboken

    windows: list[QWidget] = []
    for entry in list(app.topLevelWidgets()):
        try:
            if not Shiboken.isValid(entry):
                continue
            if isinstance(entry, _QWidget):
                windows.append(entry)
                continue
            _ALIASED_ENTRIES[Shiboken.getCppPointer(entry)[0]] = type(entry).__name__
        except (RuntimeError, AttributeError):  # pragma: no cover
            continue  # destroyed mid-walk
    return windows


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
    for w in _top_level_windows(app):
        try:
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
    """Destroy every top-level Qt widget a test left behind, after the test.

    Runs up to ``_MAX_TEARDOWN_PASSES`` passes, since destroying a widget can
    expose new top-level widgets, and records in ``_SPARED_WIDGETS`` any widget
    whose threads ``_stop_owned_threads`` could not stop.
    """
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
        for w in _top_level_windows(app):
            try:
                if not Shiboken.isValid(w):
                    continue
                w.hide()
                if _stop_owned_threads(w):
                    # Destroying a widget that owns a live QThread calls std::terminate.
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
        # processEvents() never delivers DeferredDelete; sendPostedEvents does.
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
                for w in _top_level_windows(app)
                if Shiboken.getCppPointer(w)[0] not in _SPARED_WIDGETS
            ]:
                break  # the list is empty; no second look
        except RuntimeError:  # pragma: no cover
            break


@pytest.fixture(scope="module", autouse=True)
def _assert_no_widget_leak(request: pytest.FixtureRequest) -> Iterator[None]:
    """Fail the FILE that left a top-level Qt widget alive."""
    before = _live_top_level_widgets()
    aliased_before = set(_ALIASED_ENTRIES)
    yield
    after = _live_top_level_widgets()
    aliased = {a: n for a, n in _ALIASED_ENTRIES.items() if a not in aliased_before}
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
    if aliased:
        print(
            f"\n[widget teardown] {where} read "
            f"{len(aliased)} entry(ies) from "
            "`QApplication.topLevelWidgets()` that are not widgets: "
            + ", ".join(f"{n} at {a:#x}" for a, n in sorted(aliased.items()))
            + ". That address was read back through a wrapper of the "
            "wrong type, so the entry was left alone rather than hidden "
            "or destroyed."
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
