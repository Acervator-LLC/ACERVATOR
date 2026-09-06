"""One check, the same seven steps, run over every Qt module in the tree.

``conversion_rows.rows`` derives the row list from the tree, so a module
joins by importing PySide6 and leaves by being converted. ``shell`` runs the
shipped ``desktop/main.js`` under Electron once and every step that needs a
drawn panel reads that one run; ``qt_build`` imports each row under
``ACERVATOR_VARIANT=qt``. A row that is not yet converted is reported and
never failed; what fails is a module that registered a panel and drew nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.fixtures import conversion_rows as rowset  # noqa: E402

ROWS = rowset.rows()

#: Every panel the shell drew markup into needs at least this much of it.
MARKUP_FLOOR = 1


@pytest.fixture(scope="session")
def shell() -> dict:
    """What the running Electron shell drew, one entry per panel name."""
    return rowset.electron_report()


@pytest.fixture(scope="session")
def qt_build() -> dict:
    """What each row did when imported and constructed under the Qt variant."""
    return rowset.qt_build_report()


def drawn(shell: dict, row: str) -> dict:
    """The shell's entry for ``row``, empty when the shell drew no such panel."""
    if not shell.get("available"):
        pytest.skip("the Electron shell did not run: " + str(shell.get("reason")))
    return shell["panels"].get(rowset.panel_name(row)) or {}


def test_the_row_list_is_derived_from_the_tree_and_is_not_empty() -> None:
    """``rows`` finds Qt modules, and every one of them imports PySide6."""
    assert ROWS, "no module under src/gui or the repository root imports PySide6"
    for row in ROWS:
        text = (REPO_ROOT / row).read_text(encoding="utf-8", errors="replace")
        assert rowset.imports_pyside(text), row + " is a row and imports no PySide6"


def test_a_module_that_names_pyside_without_importing_it_is_not_a_row() -> None:
    """The control for the walk above: naming PySide6 does not make a row."""
    assert rowset.imports_pyside("from PySide6.QtWidgets import QWidget") is True
    assert rowset.imports_pyside("# PySide6 is named here and never imported") is False


# -- step 1: a React module exists for the row -------------------------


@pytest.mark.parametrize("row", ROWS, ids=ROWS)
def test_step_1_a_react_module_that_exists_is_one_the_page_runs(row: str) -> None:
    """A module named for the row is named by the manifest or a script tag."""
    module = rowset.react_module(row)
    if module is None:
        pytest.skip("step 1 no: no src/gui/web module is named for " + row)
    assert module.name in rowset.loaded_module_names(), (
        module.name
        + " sits in src/gui/web and the renderer runs it from nowhere;"
        + " run python -m tools.sync_renderer_modules"
    )


# -- step 2: that module calls React -----------------------------------


@pytest.mark.parametrize("row", ROWS, ids=ROWS)
def test_step_2_a_panel_that_drew_markup_was_drawn_by_react(
    row: str, shell: dict
) -> None:
    """React marks every node it makes, and the drawn host holds one."""
    entry = drawn(shell, row)
    if not entry.get("ok"):
        pytest.skip("step 2 not driven: the shell drew no panel for " + row)
    assert entry.get("fiber") is True, (
        row
        + " drew "
        + str(entry.get("markup"))
        + " characters of markup carrying no React node: "
        + str(entry.get("html"))[:200]
    )


# -- step 3: the module is named in the shell's manifest ---------------


@pytest.mark.parametrize("row", ROWS, ids=ROWS)
def test_step_3_the_running_shell_holds_the_module_in_its_roster(
    row: str, shell: dict
) -> None:
    """The roster the shell built in Electron names the module and loaded it."""
    module = rowset.react_module(row)
    drawn(shell, row)
    if module is None:
        pytest.skip("step 3 no: no src/gui/web module is named for " + row)
    name = rowset.panel_name(row)
    assert name in (shell.get("names") or []), (
        module.name + " is on disk and the shell's own roster does not name it"
    )
    assert module.name not in (shell.get("missing") or []), (
        module.name + " is named by the roster and the shell did not run it"
    )


# -- step 4: the view model is registered on the bridge ----------------


@pytest.mark.parametrize("row", ROWS, ids=ROWS)
def test_step_4_the_declared_method_is_one_the_bridge_serves(row: str) -> None:
    """The method the module asks for is a key of ``build_registry``."""
    module = rowset.react_module(row)
    if module is None:
        pytest.skip("step 4 no: no src/gui/web module is named for " + row)
    method = rowset.declared_method(module)
    if not method:
        pytest.skip("step 4 no method: " + module.name + " declares no METHOD")
    assert method in rowset.bridge_methods(), (
        module.name
        + " asks the backend for "
        + method
        + ", which build_registry does not answer"
    )


# -- step 5: the module registers or composes into a panel -------------


@pytest.mark.parametrize("row", ROWS, ids=ROWS)
def test_step_5_a_registered_panel_is_one_the_manifest_names(
    row: str, shell: dict
) -> None:
    """A panel the host holds is addressable, so its name is in the roster."""
    name = rowset.panel_name(row)
    drawn(shell, row)
    if name not in (shell.get("registered") or []):
        pytest.skip("step 5 no: " + name + " registers no panel with the host")
    assert name in (shell.get("names") or []), (
        name + " registered a panel the manifest does not name, so no tab reaches it"
    )


# -- step 6: it renders in the running Electron shell ------------------


@pytest.mark.parametrize("row", ROWS, ids=ROWS)
def test_step_6_a_registered_panel_draws_markup_in_the_electron_shell(
    row: str, shell: dict
) -> None:
    """The item. A registered panel puts markup on screen, and here is its text."""
    name = rowset.panel_name(row)
    entry = drawn(shell, row)
    if name not in (shell.get("registered") or []):
        pytest.skip("step 6 no: " + name + " registers no panel to draw")
    assert entry.get("ok") is True, (
        name + " did not draw: " + str(entry.get("fault") or entry.get("text"))
    )
    assert entry.get("children", 0) >= MARKUP_FLOOR, (
        name
        + " drew an empty host in the Electron shell; the operator sees a blank"
        + " rectangle. Text drawn: "
        + repr(entry.get("text"))
    )


# -- step 7: the Qt widget still builds --------------------------------


@pytest.mark.parametrize("row", ROWS, ids=ROWS)
def test_step_7_the_row_still_builds_its_widgets_under_the_qt_variant(
    row: str, qt_build: dict
) -> None:
    """Under ``ACERVATOR_VARIANT=qt`` the row imports and its widgets build."""
    answer = qt_build["answers"].get(row)
    assert answer is not None, (
        row
        + " was never answered; the probe exited "
        + str(qt_build["exit_code"])
        + ": "
        + qt_build["stderr"]
    )
    assert answer["imported"] is True, row + " did not import: " + answer["error"]
    if not answer["widgets"]:
        pytest.skip("step 7 no widget: " + row + " defines no zero-argument widget")
    assert answer["built"] == answer["widgets"], (
        row
        + " builds "
        + str(answer["built"])
        + " of its "
        + str(answer["widgets"])
        + " widgets under the Qt variant: "
        + answer["error"]
    )


# -- the report -------------------------------------------------------


def step_answers(row: str, shell: dict, qt_build: dict) -> dict:
    """The seven answers for one row, each yes or no."""
    module = rowset.react_module(row)
    name = rowset.panel_name(row)
    entry = (shell.get("panels") or {}).get(name) or {}
    method = rowset.declared_method(module) if module is not None else ""
    answer = qt_build["answers"].get(row) or {}
    return {
        rowset.MODULE: module is not None,
        rowset.REACT: bool(entry.get("fiber")),
        rowset.MANIFEST: name in (shell.get("names") or [])
        and module is not None
        and module.name not in (shell.get("missing") or []),
        rowset.BRIDGE: bool(method) and method in rowset.bridge_methods(),
        rowset.PANEL: name in (shell.get("registered") or []),
        rowset.RENDERS: bool(entry.get("ok"))
        and entry.get("children", 0) >= MARKUP_FLOOR,
        rowset.QT_BUILDS: bool(answer.get("imported"))
        and answer.get("built") == answer.get("widgets"),
    }


def test_every_row_is_answered_for_every_step(shell: dict, qt_build: dict) -> None:
    """The per-row report, and the per-step totals across every row."""
    if not shell.get("available"):
        pytest.skip("the Electron shell did not run: " + str(shell.get("reason")))
    totals = dict.fromkeys(rowset.STEPS, 0)
    lines = []
    for row in ROWS:
        answers = step_answers(row, shell, qt_build)
        for step, held in answers.items():
            totals[step] += 1 if held else 0
        entry = (shell.get("panels") or {}).get(rowset.panel_name(row)) or {}
        lines.append(
            "  "
            + "".join("y" if answers[step] else "." for step in rowset.STEPS)
            + "  "
            + row.ljust(52)
            + repr(str(entry.get("text") or "")[:60])
        )
    print("\nsteps: " + " ".join(rowset.STEPS))
    print("\n".join(lines))
    print(
        "\ntotals over "
        + str(len(ROWS))
        + " rows: "
        + ", ".join(step + "=" + str(totals[step]) for step in rowset.STEPS)
    )
    assert len(qt_build["answers"]) == len(ROWS), (
        "the Qt probe answered "
        + str(len(qt_build["answers"]))
        + " of "
        + str(len(ROWS))
        + " rows"
    )
    assert totals[rowset.RENDERS] == totals[rowset.PANEL], (
        "of "
        + str(totals[rowset.PANEL])
        + " rows registering a panel, "
        + str(totals[rowset.RENDERS])
        + " drew markup"
    )


def test_the_shell_ran_the_shipped_main_process_against_the_bridge(
    shell: dict,
) -> None:
    """The run behind every drawn answer is the shipped shell, not a stand-in."""
    if not shell.get("available"):
        pytest.skip("the Electron shell did not run: " + str(shell.get("reason")))
    assert shell["bridge"] == "function", (
        "the page held no window.acervator.call, so no panel could reach the"
        " backend: " + str(shell["bridge"])
    )
    asked = [one["args"] for one in shell["spawned"]]
    assert asked == [["main.py", "--bridge"]], (
        "desktop/main.js asked for " + str(asked) + " rather than the trading program"
    )
    assert len(shell["names"]) > 60, "the shell named " + str(len(shell["names"]))
