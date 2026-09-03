"""Reports issue #128 conversion state: Qt surfaces that still have no React module.

Run from anywhere in the repo. Pairs a `src/gui/*.py` that imports PySide6 with a
React module of the same stem under `src/gui/web/` or `desktop/renderer/`, vendor
excluded. A pair means a React module was written for that surface; it does not
prove the React one is live or the Qt one retired, so treat a pair as started
rather than finished and confirm at the surface.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
GUI = ROOT / "src" / "gui"
CONTROLS = ("bot_swarm_list", "theme_engine", "design_tokens")


def react_module_stems() -> set[str]:
    """Returns the stem of every React module, excluding the vendored library."""
    found: set[str] = set()
    for folder in (GUI / "web", ROOT / "desktop" / "renderer"):
        if not folder.exists():
            continue
        found |= {p.stem for p in folder.rglob("*.js") if "vendor" not in p.parts}
    return found


def main() -> int:
    """Prints the paired and unpaired counts, the remaining surface, and a control."""
    stems = react_module_stems()
    paired: list[pathlib.Path] = []
    unpaired: list[pathlib.Path] = []

    for py in sorted(GUI.rglob("*.py")):
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "PySide6" not in text:
            continue
        (paired if py.stem in stems else unpaired).append(py)

    print("React modules, vendor excluded : " + str(len(stems)))
    print("src/gui .py importing PySide6  : " + str(len(paired) + len(unpaired)))
    print("  a .js of the same name exists : " + str(len(paired)))
    print("  NO React counterpart          : " + str(len(unpaired)))
    print()
    print("REMAINING SURFACE, largest first:")
    rows = sorted(
        ((len(p.read_text(encoding="utf-8", errors="replace").splitlines()), p) for p in unpaired),
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
