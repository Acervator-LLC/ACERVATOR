"""`tools.conversion_state` pairs a Qt module on the wiring, never on its name.

The report drives which screen gets converted next. Matching a `.py` file name
against a `.js` file name reported three finished screens as outstanding work
and sent a conversion unit at a screen that was already React. A pair is proved
here by the chain the running frontend uses: a surface publishes a bridge
method, the bridge registers it, a renderer module speaks it, and the page
loads that module. A Qt module that loads a renderer module itself pairs on
that alone.

The tests below build small repositories whose file names deliberately do not
line up, so a rule that went back to comparing stems fails them.
"""

from __future__ import annotations

import pathlib

import pytest

from tools.conversion_state import (
    NOT_A_SCREEN,
    PAIRED,
    UNPAIRED,
    ROOT,
    Verdict,
    control_state,
    imports_pyside,
    survey,
)

QT_IMPORT = "from PySide6.QtWidgets import QWidget\n"


def _write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def add_qt(root: pathlib.Path, relative: str, body: str = "") -> pathlib.Path:
    """Write a Qt module under `src/gui` and return its path."""
    path = root / "src" / "gui" / relative
    _write(path, QT_IMPORT + "\n\nclass Screen(QWidget):\n    pass\n" + body)
    return path


def add_surface(root: pathlib.Path, name: str, method: str) -> None:
    """Write a surface module publishing one bridge method."""
    _write(
        root / "src" / "gui" / "main_tabs" / (name + "_surface.py"),
        'METHOD = "' + method + '"\n',
    )


def register(root: pathlib.Path, *names: str) -> None:
    """Write a bridge whose handler table names these surfaces."""
    lines = ["def build_registry():", "    return {"]
    lines += ["        %s_surface.METHOD: None," % name for name in names]
    lines += ["    }", ""]
    _write(root / "src" / "core" / "desktop_bridge.py", "\n".join(lines))


def add_module(root: pathlib.Path, filename: str, method: str = "") -> None:
    """Write a renderer module, optionally declaring the method it speaks."""
    body = '"use strict";\n'
    if method:
        body += '  var METHOD = "' + method + '";\n'
    _write(root / "src" / "gui" / "web" / filename, body)


def load(root: pathlib.Path, *filenames: str) -> None:
    """Write the manifest the renderer page reads."""
    entries = "".join('  "' + name + '",\n' for name in filenames)
    _write(
        root / "desktop" / "renderer" / "module_manifest.js",
        "window.ACERVATOR_MODULES = [\n" + entries + "];\n",
    )


def add_parity_test(root: pathlib.Path, name: str, surface: str, qt: str) -> None:
    """Write a parity test importing one surface and one Qt module."""
    _write(
        root / "tests" / ("test_" + name + "_surface_parity.py"),
        "from src.gui.main_tabs import "
        + surface
        + "_surface as surface\nfrom "
        + qt.rsplit(".", 1)[0]
        + " import "
        + qt.rsplit(".", 1)[1]
        + " as shipped\n",
    )


def state_of(verdicts: list[Verdict], stem: str) -> str:
    """The state one module is in, named by its file stem."""
    for verdict in verdicts:
        if verdict.path.stem == stem:
            return verdict.state
    return "absent"


def evidence_of(verdicts: list[Verdict], stem: str) -> str:
    """The evidence recorded for one module, named by its file stem."""
    for verdict in verdicts:
        if verdict.path.stem == stem:
            return verdict.evidence
    return "absent"


def _wired(
    root: pathlib.Path, relative: str, surface: str, method: str, js: str
) -> None:
    add_qt(root, relative)
    add_surface(root, surface, method)
    register(root, surface)
    add_module(root, js, method)
    load(root, js)


def test_a_renderer_module_named_differently_from_the_qt_module_pairs_it(
    tmp_path: pathlib.Path,
) -> None:
    _wired(
        tmp_path,
        "live_settings/positions_held_tab.py",
        "positions_held",
        "positions_held_tab.state",
        "positions_held.js",
    )

    verdicts = survey(tmp_path)

    assert state_of(verdicts, "positions_held_tab") == PAIRED, (
        "positions_held.js speaks positions_held_tab.state, so the tab is "
        "served whatever the two files are called; got "
        + evidence_of(verdicts, "positions_held_tab")
    )


def test_a_qt_module_in_a_subfolder_pairs_on_the_flattened_address(
    tmp_path: pathlib.Path,
) -> None:
    _wired(
        tmp_path,
        "visualizer/themes.py",
        "visualizer_themes",
        "visualizer_themes.state",
        "visualizer_themes.js",
    )

    verdicts = survey(tmp_path)

    assert state_of(verdicts, "themes") == PAIRED, (
        "a surface names the screen, folder and all, so visualizer/themes.py is "
        "addressed as visualizer_themes; got " + evidence_of(verdicts, "themes")
    )


def test_a_qt_module_that_loads_a_renderer_module_itself_is_paired(
    tmp_path: pathlib.Path,
) -> None:
    add_qt(tmp_path, "react_history_panel.py", '\nSCRIPTS = ["history_panel.js"]\n')
    register(tmp_path)
    add_module(tmp_path, "history_panel.js")
    load(tmp_path, "history_panel.js")

    verdicts = survey(tmp_path)

    assert state_of(verdicts, "react_history_panel") == PAIRED, (
        "a widget that builds a page loading history_panel.js already draws "
        "React; got " + evidence_of(verdicts, "react_history_panel")
    )
    assert "history_panel.js" in evidence_of(
        verdicts, "react_history_panel"
    ), "the evidence must name the module the widget loads; got " + evidence_of(
        verdicts, "react_history_panel"
    )


def test_a_renderer_module_of_the_same_name_that_speaks_no_method_does_not_pair(
    tmp_path: pathlib.Path,
) -> None:
    add_qt(tmp_path, "indicator_panel.py")
    register(tmp_path)
    add_module(tmp_path, "indicator_panel.js")
    load(tmp_path, "indicator_panel.js")

    verdicts = survey(tmp_path)

    assert state_of(verdicts, "indicator_panel") == UNPAIRED, (
        "a .js of the same name is not evidence: it reaches no bridge method, "
        "so nothing proves it draws this screen; got "
        + evidence_of(verdicts, "indicator_panel")
    )


def test_a_method_the_bridge_does_not_register_does_not_pair(
    tmp_path: pathlib.Path,
) -> None:
    add_qt(tmp_path, "risk_tab.py")
    add_surface(tmp_path, "risk_tab", "risk_tab.state")
    register(tmp_path)
    add_module(tmp_path, "risk_tab.js", "risk_tab.state")
    load(tmp_path, "risk_tab.js")

    verdicts = survey(tmp_path)

    assert state_of(verdicts, "risk_tab") == UNPAIRED, (
        "the frontend may name any method it likes; only the bridge registry "
        "makes one reachable; got " + evidence_of(verdicts, "risk_tab")
    )


def test_a_renderer_module_the_page_never_loads_does_not_pair(
    tmp_path: pathlib.Path,
) -> None:
    add_qt(tmp_path, "alerts_tab.py")
    add_surface(tmp_path, "alerts_tab", "alerts_tab.state")
    register(tmp_path, "alerts_tab")
    add_module(tmp_path, "alerts_tab.js", "alerts_tab.state")
    load(tmp_path)

    verdicts = survey(tmp_path)

    assert state_of(verdicts, "alerts_tab") == UNPAIRED, (
        "a module absent from the manifest is never fetched, so it draws "
        "nothing; got " + evidence_of(verdicts, "alerts_tab")
    )


def test_a_qt_screen_with_no_renderer_module_is_unpaired(
    tmp_path: pathlib.Path,
) -> None:
    add_qt(tmp_path, "history_tab.py")
    register(tmp_path)
    load(tmp_path)

    verdicts = survey(tmp_path)

    assert state_of(verdicts, "history_tab") == UNPAIRED, (
        "a Qt screen with nothing wired to it is the work that is left; got "
        + evidence_of(verdicts, "history_tab")
    )


def test_a_parity_test_pinning_one_surface_to_one_qt_module_pairs_it(
    tmp_path: pathlib.Path,
) -> None:
    add_surface(tmp_path, "console_log", "console.log_lines")
    register(tmp_path, "console_log")
    add_module(tmp_path, "console_log.js", "console.log_lines")
    load(tmp_path, "console_log.js")
    add_parity_test(tmp_path, "console_log", "console_log", "src.gui.zzz_alpha")
    add_qt(tmp_path, "zzz_alpha.py")

    verdicts = survey(tmp_path)

    assert state_of(verdicts, "zzz_alpha") == PAIRED, (
        "a parity test that drives one surface against one Qt module declares "
        "the pairing whatever the two are called, and zzz_alpha shares no word "
        "with console.log_lines; got " + evidence_of(verdicts, "zzz_alpha")
    )


def test_a_parity_test_importing_two_qt_modules_pins_neither(
    tmp_path: pathlib.Path,
) -> None:
    add_surface(tmp_path, "console_log", "console.log_lines")
    register(tmp_path, "console_log")
    add_module(tmp_path, "console_log.js", "console.log_lines")
    load(tmp_path, "console_log.js")
    add_qt(tmp_path, "zzz_alpha.py")
    add_qt(tmp_path, "zzz_beta.py")
    _write(
        tmp_path / "tests" / "test_console_log_surface_parity.py",
        "from src.gui.main_tabs import console_log_surface as surface\n"
        "from src.gui import zzz_alpha, zzz_beta\n",
    )

    verdicts = survey(tmp_path)

    assert state_of(verdicts, "zzz_beta") == UNPAIRED, (
        "a second Qt import is a neighbour brought in as a control; pinning it "
        "would report an unconverted screen as finished; got "
        + evidence_of(verdicts, "zzz_beta")
    )
    assert state_of(verdicts, "zzz_alpha") == UNPAIRED, (
        "with two candidates the test declares nothing, so neither is pinned; "
        "got " + evidence_of(verdicts, "zzz_alpha")
    )


def test_a_panel_is_served_by_its_own_method_and_not_its_container(
    tmp_path: pathlib.Path,
) -> None:
    add_qt(tmp_path, "simulator_tab/simulator_tab.py")
    add_qt(tmp_path, "simulator_tab/sim_stat_strip.py")
    add_surface(tmp_path, "simulator_tab", "simulator_tab.state")
    add_surface(tmp_path, "sim_stat_strip", "sim_stat_strip.state")
    register(tmp_path, "simulator_tab", "sim_stat_strip")
    add_module(tmp_path, "simulator_tab.js", "simulator_tab.state")
    add_module(tmp_path, "sim_stat_strip.js", "sim_stat_strip.state")
    load(tmp_path, "simulator_tab.js", "sim_stat_strip.js")

    verdicts = survey(tmp_path)

    assert "sim_stat_strip.js" in evidence_of(verdicts, "sim_stat_strip"), (
        "a panel inside a folder carries the container's words as well as its "
        "own, so the closest address must win; got "
        + evidence_of(verdicts, "sim_stat_strip")
    )


def test_a_package_marker_is_not_a_screen(tmp_path: pathlib.Path) -> None:
    add_qt(tmp_path, "widgets/__init__.py")
    register(tmp_path)
    load(tmp_path)

    verdicts = survey(tmp_path)

    assert state_of(verdicts, "__init__") == NOT_A_SCREEN, (
        "a package marker is a directory, not a view, so counting it as "
        "outstanding work can never be cleared; got "
        + evidence_of(verdicts, "__init__")
    )


def test_a_module_that_defines_no_class_is_not_a_screen(
    tmp_path: pathlib.Path,
) -> None:
    _write(
        tmp_path / "src" / "gui" / "qt_safe_events.py",
        "from PySide6.QtWidgets import QApplication\n\n\ndef pump():\n    return None\n",
    )
    register(tmp_path)
    load(tmp_path)

    verdicts = survey(tmp_path)

    assert (
        state_of(verdicts, "qt_safe_events") == NOT_A_SCREEN
    ), "a module with no class builds nothing to draw; got " + evidence_of(
        verdicts, "qt_safe_events"
    )


def test_the_desktop_shell_is_not_a_screen(tmp_path: pathlib.Path) -> None:
    _write(
        tmp_path / "src" / "gui" / "main_window.py",
        "from PySide6.QtWidgets import QMainWindow\n\n\n"
        "class MainWindow(QMainWindow):\n    pass\n",
    )
    register(tmp_path)
    load(tmp_path)

    verdicts = survey(tmp_path)

    assert state_of(verdicts, "main_window") == NOT_A_SCREEN, (
        "the shell is the desktop window the renderer's web view lives inside, "
        "so it can never itself become React; got "
        + evidence_of(verdicts, "main_window")
    )


def test_an_ordinary_widget_is_still_a_screen(tmp_path: pathlib.Path) -> None:
    add_qt(tmp_path, "history_tab.py")
    register(tmp_path)
    load(tmp_path)

    verdicts = survey(tmp_path)

    assert state_of(verdicts, "history_tab") != NOT_A_SCREEN, (
        "a plain widget carries a class and no shell base, so the three "
        "plumbing shapes must leave it as work; got "
        + evidence_of(verdicts, "history_tab")
    )


def test_a_module_that_only_names_qt_gets_no_verdict(tmp_path: pathlib.Path) -> None:
    _write(
        tmp_path / "src" / "gui" / "note.py",
        'WARNING = "TradingView charts require PySide6-WebEngine"\n',
    )
    register(tmp_path)
    load(tmp_path)

    assert [verdict.path.name for verdict in survey(tmp_path)] == [], (
        "a module that imports no Qt is not a Qt surface at all and belongs in "
        "none of the three states"
    )
    assert imports_pyside('X = "PySide6"\n') is False, (
        "the same rule, read directly: naming PySide6 in a string is not an " "import"
    )


@pytest.fixture(scope="module")
def shipped() -> list[Verdict]:
    """The verdicts for the repository this test runs inside."""
    return survey(ROOT)


def test_bot_swarm_list_reports_paired(shipped: list[Verdict]) -> None:
    assert control_state(shipped, "bot_swarm_list") == PAIRED, (
        "bot_swarm_list is converted; a tool that cannot see one finished "
        "screen cannot be trusted about the rest"
    )


def test_theme_engine_and_design_tokens_report_born_react(
    shipped: list[Verdict],
) -> None:
    for probe in ("theme_engine", "design_tokens"):
        assert control_state(shipped, probe) not in (PAIRED, UNPAIRED, NOT_A_SCREEN), (
            probe + " has no Qt module to convert and must report born React"
        )


def test_the_three_modules_the_stem_match_missed_report_paired(
    shipped: list[Verdict],
) -> None:
    missed = {
        "src/gui/react_history_panel.py",
        "src/gui/live_settings/positions_held_tab.py",
        "src/gui/visualizer/themes.py",
    }
    states = {
        verdict.path.relative_to(ROOT).as_posix(): verdict.state
        + " -- "
        + verdict.evidence
        for verdict in shipped
        if verdict.path.relative_to(ROOT).as_posix() in missed
    }
    assert set(states) == missed, "all three modules must appear; got " + str(states)
    assert all(value.startswith(PAIRED) for value in states.values()), (
        "each of these is served by a renderer module under another name and "
        "was counted as remaining work; got " + str(states)
    )


def test_every_shipped_screen_carries_a_known_state(
    shipped: list[Verdict],
) -> None:
    known = {PAIRED, UNPAIRED, NOT_A_SCREEN}
    stray = {
        verdict.path.relative_to(ROOT).as_posix(): verdict.state
        for verdict in shipped
        if not any(verdict.state.startswith(state) for state in known)
    }
    assert shipped, "the survey found no Qt modules at all; it cannot report"
    assert not stray, (
        "every Qt module must land in one of the three states or it silently "
        "leaves the count; got " + str(stray)
    )


def test_the_desktop_shell_is_not_counted_as_remaining_work(
    shipped: list[Verdict],
) -> None:
    assert control_state(shipped, "main_window") == NOT_A_SCREEN, (
        "main_window hosts the web view the renderer draws into; counting it "
        "as outstanding makes the conversion permanently incompletable"
    )
