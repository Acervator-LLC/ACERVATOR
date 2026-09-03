"""Reports Qt-to-React conversion state: Qt surfaces that still have no React module.

Run from anywhere in the repo. Pairs a `src/gui/*.py` that imports PySide6 with a
React module of the same stem under `src/gui/web/` or `desktop/renderer/`, vendor
excluded. A pair means a React module was written for that surface; it does not
prove the React one is live or the Qt one retired, so treat a pair as started
rather than finished and confirm at the surface.

A module counts as a Qt surface only when it really imports PySide6. Naming the
word in a docstring, a comment or a warning string does not make a module Qt, so
the pairing reads the parsed import statements rather than the file text.
"""

from __future__ import annotations

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
GUI = ROOT / "src" / "gui"
CONTROLS = ("bot_swarm_list", "theme_engine", "design_tokens")
QT_PACKAGE = "PySide6"


def imports_pyside(text: str) -> bool:
    """True when a module really imports PySide6, false when it only names it.

    The scan pairs a Qt surface with its React module, so a module that carries
    the word inside a string or a comment must not count as Qt. A module that
    names the word but cannot be parsed stays counted, so a file the tool cannot
    read is reported as remaining work rather than dropped from the total.
    """
    if QT_PACKAGE not in text:
        return False
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return True
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.split(".")[0] == QT_PACKAGE for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] == QT_PACKAGE:
                return True
    return False


def react_module_stems(root: pathlib.Path = ROOT) -> set[str]:
    """Returns the stem of every React module, excluding the vendored library."""
    found: set[str] = set()
    for folder in (root / "src" / "gui" / "web", root / "desktop" / "renderer"):
        if not folder.exists():
            continue
        found |= {p.stem for p in folder.rglob("*.js") if "vendor" not in p.parts}
    return found


def split_surfaces(
    gui: pathlib.Path, stems: set[str]
) -> tuple[list[pathlib.Path], list[pathlib.Path]]:
    """Splits the Qt surfaces under `gui` into those paired by stem and those not."""
    paired: list[pathlib.Path] = []
    unpaired: list[pathlib.Path] = []
    for py in sorted(gui.rglob("*.py")):
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not imports_pyside(text):
            continue
        (paired if py.stem in stems else unpaired).append(py)
    return paired, unpaired


def main() -> int:
    """Prints the paired and unpaired counts, the remaining surface, and a control."""
    stems = react_module_stems()
    paired, unpaired = split_surfaces(GUI, stems)

    print("React modules, vendor excluded : " + str(len(stems)))
    print("src/gui .py importing PySide6  : " + str(len(paired) + len(unpaired)))
    print("  a .js of the same name exists : " + str(len(paired)))
    print("  NO React counterpart          : " + str(len(unpaired)))
    print()
    print("REMAINING SURFACE, largest first:")
    rows = sorted(
        (
            (len(p.read_text(encoding="utf-8", errors="replace").splitlines()), p)
            for p in unpaired
        ),
        reverse=True,
        key=lambda row: row[0],
    )
    for count, path in rows:
        print("  " + str(count).rjust(5) + "   " + path.relative_to(ROOT).as_posix())

    print()
    print("CONTROL, a converted name must report 'paired':")
    for probe in CONTROLS:
        if any(p.stem == probe for p in paired):
            where = "paired"
        elif any(p.stem == probe for p in unpaired):
            where = "unpaired"
        else:
            where = "no .py at all, born React"
        print("  " + probe.ljust(18) + where)
    return 0


if __name__ == "__main__":
    sys.exit(main())
