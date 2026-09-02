"""Every Qt screen the application ships is still present and still builds.

Qt stays until the React and Electron front end runs and verifies against
the operational logs. A brief cannot stop a deletion; this file does. It
discovers the screens at runtime, builds the ones that need no collaborator,
and names any screen that goes missing or stops constructing.

The inventory is DERIVED, never typed by hand: a screen added tomorrow is
covered with no edit here. The floors below are the measured size of the
tree, so a discovery that silently finds nothing fails instead of passing
empty.

FALSIFICATION
=============
Wrong if (a) discovery stops importing `src.gui` submodules, when every
count reads zero and the floors are the only thing left reporting, or
(b) a screen keeps a constructible widget class that no longer paints or
wires anything -- this file proves a class EXISTS and BUILDS, never that
it still does its job.
"""

from __future__ import annotations

import dataclasses
import gc
import importlib
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from tests.fixtures.quiet_news_ticker import (  # noqa: E402
    fetch_threads_running,
    install_quiet_ticker,
)

GUI_PACKAGE = "src.gui"

# Measured on the tree at the time of writing. `>=` not `==`: a new screen
# must not fail the guard, a lost one must.
MIN_SCREEN_MODULES = 47
MIN_SCREEN_CLASSES = 83
MIN_CONSTRUCTIBLE = 50

# react_history_panel and tradingview_chart each define one constructible
# widget class only when QtWebEngineWidgets imports. Without it they define
# none, so a fixed floor would state a fact about the host, not the product.
WEBENGINE_ONLY_SCREENS = 2

MISSING_COLLABORATOR = (
    "required positional argument",
    "required keyword-only argument",
)


def _has_webengine() -> bool:
    """Report whether QtWebEngineWidgets imports on this host."""
    try:
        importlib.import_module("PySide6.QtWebEngineWidgets")
    except ImportError:
        return False
    return True


def _gui_module_names() -> list[str]:
    """Dotted names of every module under src/gui, read from the filesystem."""
    root = REPO / Path(GUI_PACKAGE.replace(".", "/"))
    names = set()
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        parts = path.relative_to(REPO).with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            names.add(".".join(parts))
    return sorted(names)


@dataclass
class ScreenSweep:
    """What one discovery-and-build pass over src/gui found.

    Holds class objects and names only. A built screen is destroyed before
    the next is built, so no widget instance is ever stored here.
    """

    import_errors: dict[str, str] = field(default_factory=dict)
    classes: dict[str, type] = field(default_factory=dict)
    built: list[str] = field(default_factory=list)
    refused: dict[str, tuple[str, str]] = field(default_factory=dict)
    root_handlers_added: list[str] = field(default_factory=list)
    root_handlers_before: list[str] = field(default_factory=list)
    root_handlers_after: list[str] = field(default_factory=list)
    root_level_before: int = -1
    root_level_after: int = -1

    @property
    def modules(self) -> set[str]:
        """The src/gui modules that define at least one Qt widget class."""
        return {key.rsplit(".", 1)[0] for key in self.classes}


def _discover(sweep: ScreenSweep) -> None:
    """Import every src/gui module and collect the widget classes it defines."""
    for name in _gui_module_names():
        try:
            module = importlib.import_module(name)
        except BaseException as exc:  # noqa: BLE001 - any failure is the finding
            sweep.import_errors[name] = f"{type(exc).__name__}: {exc}"
            continue
        for obj in vars(module).values():
            if not isinstance(obj, type):
                continue
            if getattr(obj, "__module__", None) != name:
                continue
            if not issubclass(obj, QWidget):
                continue
            sweep.classes[f"{name}.{obj.__name__}"] = obj


def _restore_root(
    sweep: ScreenSweep, handlers: list[logging.Handler], level: int
) -> None:
    """Put the root logger back to `handlers` and `level`, recording additions.

    Restores unconditionally and by identity. One screen attaches two handlers
    and drops the root level to DEBUG, and a second screen attaches a handler
    of a class already present, so removing only what is recognised by class
    name would leave the later instances behind.
    """
    root = logging.getLogger()
    added = [type(h).__name__ for h in root.handlers if h not in handlers]
    if added:
        sweep.root_handlers_added.extend(added)
    root.handlers[:] = handlers
    root.setLevel(level)


def _build_each(
    sweep: ScreenSweep, handlers: list[logging.Handler], level: int
) -> None:
    """Build every discovered class alone, destroying each before the next.

    Restores the root logger after each screen. A handler a screen attaches is
    bound to a widget that screen owns; left attached, it writes into a
    destroyed widget and every later log record in the process raises.

    The refusal is stored as text. Keeping the exception would pin its
    traceback, and the traceback pins the frame that holds the widget.
    """
    for key in sorted(sweep.classes):
        try:
            widget = sweep.classes[key]()
        except BaseException as exc:  # noqa: BLE001 - the refusal is the finding
            sweep.refused[key] = (type(exc).__name__, str(exc))
        else:
            sweep.built.append(key)
            widget.close()
            del widget
            gc.collect()
        _restore_root(sweep, handlers, level)


@pytest.fixture(scope="module")
def sweep(tmp_path_factory: pytest.TempPathFactory) -> ScreenSweep:
    """One discovery-and-build pass, shared by every test in this file.

    Discovery runs BEFORE the quiet news strip is installed. Installing it
    first would replace `CryptoNewsTicker` on its own module, and the
    replacement is defined elsewhere, so discovery would drop that screen
    and read the loss as normal.

    The build pass runs from a temp directory. `CompetitionTab` defaults its
    `data_dir` to the relative path `competition_data`, so building it from
    the repo root writes `competition_data/bot_identity.json` into the tree.

    The root logger baseline is taken BEFORE discovery. Importing a screen
    module can attach a handler, and a baseline taken after the imports would
    adopt that handler as normal instead of removing it. Both snapshots are
    taken inside this fixture, so a handler another test file leaked onto the
    root logger sits in both and cannot fail this file.
    """
    if QApplication.instance() is None:
        QApplication(sys.argv)
    root = logging.getLogger()
    baseline_handlers = list(root.handlers)
    baseline_level = root.level
    result = ScreenSweep()
    result.root_handlers_before = [type(h).__name__ for h in baseline_handlers]
    result.root_level_before = baseline_level
    _discover(result)
    _restore_root(result, baseline_handlers, baseline_level)
    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(tmp_path_factory.mktemp("screen_sweep"))
        install_quiet_ticker(patch)
        _build_each(result, baseline_handlers, baseline_level)
    result.root_handlers_after = [type(h).__name__ for h in root.handlers]
    result.root_level_after = root.level
    return result


def test_every_gui_module_imports(sweep: ScreenSweep) -> None:
    """A screen deleted out from under an importer names both, here."""
    listed = "\n  ".join(
        f"{name}: {err}" for name, err in sorted(sweep.import_errors.items())
    )
    assert sweep.import_errors == {}, (
        f"src/gui modules that no longer import:\n  {listed}\n\n"
        "A screen class removed while another module still imports it by "
        "name fails here, and the message names the missing name."
    )


def test_discovery_finds_the_whole_screen_inventory(sweep: ScreenSweep) -> None:
    """A blinded discovery reads as zero screens, never as 'all present'."""
    bonus = WEBENGINE_ONLY_SCREENS if _has_webengine() else 0
    expected_modules = MIN_SCREEN_MODULES + bonus
    expected_classes = MIN_SCREEN_CLASSES + bonus
    found = "\n  ".join(sorted(sweep.classes))

    assert len(sweep.modules) >= expected_modules, (
        f"discovery found {len(sweep.modules)} src/gui modules defining a Qt "
        f"widget class, expected at least {expected_modules}. A screen module "
        f"was deleted, or discovery stopped importing.\nFound:\n  {found}"
    )
    assert len(sweep.classes) >= expected_classes, (
        f"discovery found {len(sweep.classes)} Qt widget classes under "
        f"src/gui, expected at least {expected_classes}. A screen's widget "
        f"class was deleted or gutted.\nFound:\n  {found}"
    )


def test_every_screen_that_needs_no_collaborator_builds(sweep: ScreenSweep) -> None:
    """A screen that stops constructing is named with the error it raised."""
    broken = {
        key: reason
        for key, reason in sweep.refused.items()
        if reason[0] != "TypeError"
        or not any(phrase in reason[1] for phrase in MISSING_COLLABORATOR)
    }
    listed = "\n  ".join(
        f"{key}: {kind}: {text}" for key, (kind, text) in sorted(broken.items())
    )
    assert broken == {}, (
        "screens that refused to build for a reason other than a missing "
        f"collaborator:\n  {listed}"
    )

    expected = MIN_CONSTRUCTIBLE + (WEBENGINE_ONLY_SCREENS if _has_webengine() else 0)
    assert len(sweep.built) >= expected, (
        f"{len(sweep.built)} screens built alone, expected at least "
        f"{expected}. Built:\n  " + "\n  ".join(sorted(sweep.built))
    )


def test_screens_needing_a_collaborator_are_still_importable(
    sweep: ScreenSweep,
) -> None:
    """These screens cannot be built alone. Their class must still be there."""
    assert sweep.refused, (
        "no screen refused construction. Every screen in this tree that needs "
        "a manager, a bot or a proposal was expected to refuse, so an empty "
        "refusal set means the build pass never ran."
    )
    for key, (kind, text) in sorted(sweep.refused.items()):
        module_name, class_name = key.rsplit(".", 1)
        module = importlib.import_module(module_name)
        screen = getattr(module, class_name, None)
        assert screen is not None, f"{key} is gone from {module_name}"
        assert isinstance(screen, type), f"{key} is no longer a class: {screen!r}"
        assert issubclass(screen, QWidget), (
            f"{key} is no longer a Qt widget class; it is {screen!r}. "
            f"It refused construction with {kind}: {text}"
        )


def test_the_root_logger_restore_puts_back_handlers_and_level() -> None:
    """The restore must undo a handler and a level change, or the sweep leaks."""
    root = logging.getLogger()
    baseline_handlers = list(root.handlers)
    baseline_level = root.level
    dirty_level = logging.ERROR if baseline_level == logging.DEBUG else logging.DEBUG

    root.addHandler(logging.NullHandler())
    root.addHandler(logging.NullHandler())
    root.setLevel(dirty_level)
    assert (
        len(root.handlers) == len(baseline_handlers) + 2
    ), "the plant did not attach two handlers, so this control proves nothing"
    assert (
        root.level == dirty_level
    ), "the plant did not change the root level, so this control proves nothing"

    probe = ScreenSweep()
    _restore_root(probe, baseline_handlers, baseline_level)

    assert root.handlers == baseline_handlers, (
        "restore left the root handler list as "
        f"{[type(h).__name__ for h in root.handlers]}, expected "
        f"{[type(h).__name__ for h in baseline_handlers]}"
    )
    assert (
        root.level == baseline_level
    ), f"restore left the root level at {root.level}, expected {baseline_level}"
    assert probe.root_handlers_added == ["NullHandler", "NullHandler"], (
        f"restore recorded {probe.root_handlers_added}; both planted handlers "
        "share a class, and a restore keyed on the class name records one"
    )


def test_the_sweep_leaves_the_root_logger_as_it_found_it(
    sweep: ScreenSweep,
) -> None:
    """A screen's log handler outliving its widget breaks every later record."""
    assert sweep.root_handlers_after == sweep.root_handlers_before, (
        "the sweep changed the root logger handler list from "
        f"{sweep.root_handlers_before} to {sweep.root_handlers_after}. "
        f"Screens attached {sorted(set(sweep.root_handlers_added))} while it "
        "ran, and the restore did not put the list back. Such a handler "
        "writes into a destroyed widget, so every later log record raises."
    )
    assert sweep.root_level_after == sweep.root_level_before, (
        f"the sweep left the root logger level at {sweep.root_level_after}, "
        f"expected {sweep.root_level_before}. One screen sets the root level "
        "to DEBUG and never puts it back."
    )


def test_the_sweep_holds_no_screen_open(sweep: ScreenSweep) -> None:
    """Screens are built one at a time, never accumulated in this file."""
    held = []
    for spec in dataclasses.fields(sweep):
        value = getattr(sweep, spec.name)
        if isinstance(value, dict):
            items = list(value.values())
        elif isinstance(value, (list, tuple, set)):
            items = list(value)
        else:
            continue
        held += [
            f"{spec.name} holds a live {type(item).__name__}"
            for item in items
            if isinstance(item, QWidget)
        ]
    assert not held, (
        f"the sweep built {len(sweep.built)} screens and kept "
        f"{len(held)} of them alive:\n  " + "\n  ".join(held)
    )


def test_the_sweep_starts_no_news_fetch_thread(sweep: ScreenSweep) -> None:
    """A fetch thread outliving this file would share the process with the rest."""
    running = fetch_threads_running()
    assert running == 0, (
        f"{running} news fetch thread(s) still running after building "
        f"{len(sweep.built)} screens. Constructing CryptoNewsTicker must not "
        "open a socket; only start() does."
    )
