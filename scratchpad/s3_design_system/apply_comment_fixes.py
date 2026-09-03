"""Applies every remaining comment repair the checker named, file by file."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

EDITS = {
    "src/gui/web/design_system.js": [
        (
            "// Renders each design token into the CSS declaration a screen"
            " paints with.\n"
            "//\n"
            "// Every value comes from `design_tokens.js` through"
            " `acervatorTokens`, so\n"
            "// this file carries no colour, size or duration of its own.\n"
            "//\n"
            "// `design_tokens.js` copies a token's raw text onto the page under"
            " its own\n"
            "// name. A browser reads a bare `16` as no length, a bare `250` as"
            " no\n"
            "// duration, and an `rgba` alpha byte as fully opaque, so a screen"
            " painting\n"
            "// from those raw values gets nothing where Qt gets a size and a"
            " tint. This\n"
            "// file adds the unit the token's own group implies and converts"
            " Qt's alpha\n"
            "// byte to the alpha a browser reads, leaving the surface value"
            " untouched.\n"
            "//\n"
            "// The kind of each token comes from the group the surface"
            " publishes it in.\n"
            "// A group the surface adds and this file has no kind for is"
            " recorded in\n"
            "// `faults` rather than rendered under a guessed unit.\n"
            "//\n"
            "// It reports and it does not repair a payload. A colour whose"
            " digit count\n"
            "// Qt and a browser read differently is named and left as it"
            " arrived.\n",
            "// Renders each design token into the CSS declaration a screen"
            " paints with, units and alpha included.\n",
        ),
        (
            "  // Reuses the one ask `design_tokens.js` already makes for the"
            " same method.\n",
            "  // Reuses the one ask for tokens already made, so this adds no"
            " round trip.\n",
        ),
    ],
    "tests/test_react_design_system.py": [
        (
            "#: The module as it stands before any check writes into it, so a"
            " check in\n#: another worker cannot read a written copy.\n",
            "#: The module source read before any check writes into it.\n",
        ),
        (
            "#: The CSS unit each token group implies. Paired against the"
            " surface's\n#: own group list by name, so a group added on one side"
            " alone is named.\n",
            "#: The CSS unit each token group implies, paired against the"
            " surface group\n#: list by name.\n",
        ),
        (
            "#: The token a caller names to render the shadows; black, and the"
            " only\n#: name carrying it, so the shadow channels are"
            " unambiguous.\n",
            "#: The token a caller names for the shadow colour, carried by no"
            " other name.\n",
        ),
        (
            "#: Every rendered value the surface carries under more than one"
            " non-alias\n#: name. Two raw numbers that collide can render apart"
            " once each carries\n#: its own unit, so this is measured after"
            " rendering and not before.\n",
            "#: Every rendered value that more than one non-alias name carries,"
            " measured\n#: after the unit is added.\n",
        ),
        (
            "#: Reads one whole declaration back off a probe element, so nothing"
            " here\n#: types the value the module is being measured against.\n",
            "#: Reads one whole declaration back off a probe element, typing no"
            " value here.\n",
        ),
        (
            "# -- 8. hostile payloads -----------------------------------------"
            "------\n",
            "# -- 8. a hostile payload, each field damaged in turn -------------"
            "------\n",
        ),
        (
            '    """A caller handed the module\'s own list could reorder every'
            ' screen by sorting\n    it."""\n',
            '    """A caller handed the module\'s own list could reorder every'
            ' screen, so\n    each declaration list is fresh."""\n',
        ),
    ],
}

DOCSTRINGS = {
    "comment_check.py": (
        "Checks every comment and docstring on this branch against the words,"
        " sentence and column rules."
    ),
    "compare_qt.py": (
        "Compares the surface token table against the Qt module it replaces,"
        " pairing by name."
    ),
    "count_lists.py": (
        "Counts every published list in the design system and compares each"
        " pair by name."
    ),
    "probe_alpha.py": (
        "Measures what Chromium paints for each rgba tint the design surface"
        " declares."
    ),
    "probe_lengths.py": (
        "Measures what Chromium computes when a bare token number is used as a"
        " CSS length."
    ),
    "probe_lengths2.py": (
        "Measures each bare token number beside a known-good declaration, so"
        " the probe is calibrated."
    ),
    "repair_module.py": (
        "Cuts the written lines off the end of the shipped design system" " module."
    ),
    "smoke.py": (
        "Drives the design system module in QJSEngine beside design_tokens.js."
    ),
    "sweep_colours.py": (
        "Sweeps every colour the design system declares, in Python and in CSS" " text."
    ),
    "show_faults.py": (
        "Prints each faulting comment line of one file with the lines under it."
    ),
    "show_docstrings.py": (
        "Prints each faulting docstring of one file beside the function name"
        " holding it."
    ),
    "rewrite_docstrings.py": (
        "Puts a short one-sentence docstring on each function the checker" " named."
    ),
    "apply_comment_fixes.py": (
        "Applies every remaining comment repair the checker named, file by" " file."
    ),
    "probe_made_after_the_checker.py": (
        "Exists only to show discovery finds a file made after the checker."
    ),
}


def replace_module_docstring(path: Path, text: str) -> bool:
    """Put one short sentence in place of a file's whole module docstring."""
    source = path.read_text(encoding="utf-8")
    if not source.startswith('"""'):
        return False
    close = source.index('"""', 3)
    body = " ".join(text.split())
    opened = f'"""{body}"""'
    if len(opened) > 88:
        opened = '"""' + body + '"""'
    return_text = opened + source[close + 3 :]
    path.write_text(return_text, encoding="utf-8", newline="")
    return True


def main() -> None:
    for name, pairs in EDITS.items():
        path = REPO / name
        source = path.read_text(encoding="utf-8")
        for old, new in pairs:
            if old not in source:
                print(f"  MISSED in {name}: {old[:60]!r}")
                continue
            source = source.replace(old, new, 1)
        path.write_text(source, encoding="utf-8", newline="")
        print(f"edited {name}")
    for name, text in DOCSTRINGS.items():
        path = HERE / name
        if not path.exists():
            print(f"  ABSENT {name}")
            continue
        if replace_module_docstring(path, text):
            print(f"docstring set on {name}")
        else:
            print(f"  NO MODULE DOCSTRING in {name}")


if __name__ == "__main__":
    main()
