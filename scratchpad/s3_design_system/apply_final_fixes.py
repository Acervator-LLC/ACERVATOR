"""Applies the last three comment repairs the checker named."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

EDITS = [
    (
        HERE / "add_order_checks.py",
        "ADDED = '''def test_a_number_like_token_name_keeps_its_published_"
        "position(js: JsRuntime):\n",
        "ADDED = '''\ndef test_a_number_like_token_name_keeps_its_position("
        "js: JsRuntime):\n",
    ),
    (
        HERE / "prove_repairs.py",
        '"""Puts each repair\'s old code back one at a time and reports what'
        ' fails."""',
        '"""Puts each repair\'s old code back into the target module, one at a'
        ' time."""',
    ),
    (
        REPO / "tests" / "test_react_design_system.py",
        '    """A name is published in order whether or not it renders, so the'
        ' order\n    is the surface list and not a walk of what rendered."""',
        '    """A name is published in order whether or not it renders, never'
        ' walked."""',
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


if __name__ == "__main__":
    main()
