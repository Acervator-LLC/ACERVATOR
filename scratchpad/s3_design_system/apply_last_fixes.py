"""Applies the last comment repairs the checker named across the branch."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

TEST_DOCSTRING = '''"""Proves the design module renders each token into a CSS
declaration and carries no value.
"""
'''

EDITS = [
    (
        REPO / "src" / "gui" / "web" / "design_system.js",
        "// Renders each design token into the CSS declaration a screen paints"
        " with, units and alpha included.\n",
        "// Renders each design token into the CSS declaration a screen paints\n"
        "// with, units and alpha included.\n",
    ),
    (
        HERE / "comment_check.py",
        '"""Checks every comment and docstring on this branch against the words,'
        ' sentence and column rules."""',
        '"""Checks each comment and docstring on this branch for words,'
        ' sentences and columns."""',
    ),
    (
        HERE / "comment_check.py",
        '    """Every real docstring, found by parsing rather than by matching'
        " quotes.\n\n"
        "    A plain triple-quoted string assigned to a name is not a"
        " docstring,\n"
        "    and matching quotes cannot tell the two apart.\n"
        '    """',
        '    """Every real docstring, found by parsing rather than by matching'
        ' quotes."""',
    ),
    (
        HERE / "compare_qt.py",
        '"""Compares the surface token table against the Qt module it replaces,'
        ' pairing by name."""',
        '"""Compares the surface token table against the Qt module, pairing by'
        ' name."""',
    ),
    (
        HERE / "probe_lengths.py",
        '"""Measures what Chromium computes when a bare token number is used as'
        ' a CSS length."""',
        '"""Measures what Chromium computes for a bare design token number as a'
        ' CSS length."""',
    ),
    (
        HERE / "probe_lengths2.py",
        '"""Measures each bare token number beside a known-good declaration, so'
        ' the probe is calibrated."""',
        '"""Measures a bare design token beside a good declaration, calibrating'
        ' the probe."""',
    ),
    (
        HERE / "sweep_colours.py",
        '    """Every brace-delimited sub-block in a style sheet, nested'
        ' included."""',
        '    """Every brace-delimited block of a style sheet text, nested blocks'
        ' included."""',
    ),
]


def main() -> None:
    for path, old, new in EDITS:
        source = path.read_text(encoding="utf-8")
        if old not in source:
            print(f"  MISSED in {path.name}: {old[:60]!r}")
            continue
        path.write_text(source.replace(old, new, 1), encoding="utf-8", newline="")
        print(f"edited {path.name}")
    target = REPO / "tests" / "test_react_design_system.py"
    source = target.read_text(encoding="utf-8")
    close = source.index('"""', 3)
    target.write_text(
        TEST_DOCSTRING + source[close + 4 :], encoding="utf-8", newline=""
    )
    print("docstring set on test_react_design_system.py")


if __name__ == "__main__":
    main()
