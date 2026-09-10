"""Write the build column of the #128 conversion table from a built react bundle.

``bundle_modules`` reads the ``.js`` names a ``dist/Acervator-*-react`` bundle
carries under ``src/gui/web``, and ``rewrite`` puts one ``BUILD_COLUMN`` cell on
every row of the table in a markdown file. ``totals_block`` recounts the marks
under the table from the cells the rewrite leaves.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

DEFAULT_DOC = ROOT / "docs" / "manual" / "08-tabs.md"
BUNDLE_GLOB = "Acervator-*-react"
BUNDLE_WEB = pathlib.PurePosixPath("_internal/src/gui/web")

TABLE_HEAD = "| Qt file | React module |"
BUILD_COLUMN = "Ships in the build"
LAST_COLUMN = "RENDERS"
SCOPE_COLUMN = "Scope"
IN_SCOPE_PREFIX = "in scope"
SCOPE_TOTAL = "RENDERS, in scope"
OUT_OF_SCOPE_TOTAL = "out of scope"
TOTALS_FENCE = "```"

YES = "yes"
NO = "no"
NONE_MARK = "-"
TOTAL_WIDTH = 25


def newest_bundle(root: pathlib.Path) -> pathlib.Path | None:
    """The most recently written ``BUNDLE_GLOB`` directory under ``root/dist``."""
    found = sorted(
        (path for path in (root / "dist").glob(BUNDLE_GLOB) if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
    )
    return found[-1] if found else None


def bundle_modules(bundle: pathlib.Path) -> set[str]:
    """Every ``.js`` name the ``bundle`` carries at ``BUNDLE_WEB``."""
    return {path.name for path in (bundle / BUNDLE_WEB).glob("*.js")}


def module_name(cell: str) -> str:
    """The ``.js`` name a React module cell holds, or the empty string."""
    name = cell.strip().strip("`")
    return name if name.endswith(".js") else ""


def ship_mark(cell: str, carried: set[str]) -> str:
    """``YES``, ``NO`` or ``NONE_MARK`` for one React module ``cell``."""
    name = module_name(cell)
    if not name:
        return NONE_MARK
    return YES if name in carried else NO


def split_cells(line: str) -> list[str]:
    """The cells of one markdown table ``line``, each stripped."""
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def join_cells(cells: list[str]) -> str:
    """One markdown table line holding ``cells``."""
    return "| " + " | ".join(cells) + " |"


def table_span(lines: list[str]) -> tuple[int, int]:
    """The first and last index of the longest ``TABLE_HEAD`` table in ``lines``.

    A page quoting the head above a two-row excerpt holds several; the widest is
    the conversion table, and ``LookupError`` names an absent head.
    """
    spans = []
    for start, line in enumerate(lines):
        if line.startswith(TABLE_HEAD):
            end = start + 2
            while end < len(lines) and lines[end].startswith("|"):
                end += 1
            spans.append((start, end - 1))
    if not spans:
        raise LookupError("no line starts with " + TABLE_HEAD)
    return max(spans, key=lambda span: span[1] - span[0])


def place_cell(cells: list[str], value: str, at: int) -> list[str]:
    """``cells`` with ``value`` set at index ``at``, inserting when it is new."""
    widened = list(cells)
    if len(widened) <= at:
        widened.append(value)
    else:
        widened[at] = value
    return widened


def widen(lines: list[str], carried: set[str]) -> list[str]:
    """``lines`` with a ``BUILD_COLUMN`` cell on every row of the table.

    The column sits before ``LAST_COLUMN``, and a table already carrying it is
    remeasured in place.
    """
    start, end = table_span(lines)
    heads = split_cells(lines[start])
    at = heads.index(LAST_COLUMN) if LAST_COLUMN in heads else len(heads)
    if BUILD_COLUMN in heads:
        at = heads.index(BUILD_COLUMN)
    else:
        heads.insert(at, BUILD_COLUMN)
        for index in range(start + 1, end + 1):
            row = split_cells(lines[index])
            row.insert(at, "")
            lines[index] = join_cells(row)
    out = list(lines)
    out[start] = join_cells(heads)
    out[start + 1] = join_cells(["---"] * len(heads))
    for index in range(start + 2, end + 1):
        row = split_cells(out[index])
        out[index] = join_cells(place_cell(row, ship_mark(row[1], carried), at))
    return out


def scope_totals(heads: list[str], rows: list[list[str]]) -> list[str]:
    """The rendering-against-in-scope line and the out-of-scope count.

    Answers an empty list for a table carrying no ``SCOPE_COLUMN``.
    """
    if SCOPE_COLUMN not in heads:
        return []
    scope = heads.index(SCOPE_COLUMN)
    last = heads.index(LAST_COLUMN) if LAST_COLUMN in heads else scope
    inside = [row for row in rows if row[scope].startswith(IN_SCOPE_PREFIX)]
    drawn = sum(1 for row in inside if row[last] == YES)
    return [
        SCOPE_TOTAL.ljust(TOTAL_WIDTH) + str(drawn) + " of " + str(len(inside)),
        OUT_OF_SCOPE_TOTAL.ljust(TOTAL_WIDTH) + str(len(rows) - len(inside)),
    ]


def totals_block(lines: list[str]) -> list[str]:
    """One ``name count`` line per column of the table, the Qt file column apart.

    ``scope_totals`` summarises ``SCOPE_COLUMN``, which carries no mark to count.
    """
    start, end = table_span(lines)
    heads = split_cells(lines[start])
    rows = [split_cells(line) for line in lines[start + 2 : end + 1]]
    block = []
    for index, head in enumerate(heads):
        if index == 0 or head == SCOPE_COLUMN:
            continue
        marked = sum(1 for row in rows if row[index] not in (NO, NONE_MARK))
        block.append(head.ljust(TOTAL_WIDTH) + str(marked))
    return block + scope_totals(heads, rows)


def retotal(lines: list[str]) -> list[str]:
    """``lines`` with the fenced block after the table replaced by ``totals_block``.

    Lines carrying no fenced block after the table come back unchanged.
    """
    _, end = table_span(lines)
    opened = None
    for index in range(end + 1, len(lines)):
        if lines[index].startswith(TOTALS_FENCE):
            opened = index
            break
        if lines[index].startswith("|"):
            return lines
    if opened is None:
        return lines
    closed = next(
        (
            index
            for index in range(opened + 1, len(lines))
            if lines[index].startswith(TOTALS_FENCE)
        ),
        None,
    )
    if closed is None:
        return lines
    return lines[: opened + 1] + totals_block(lines) + lines[closed:]


def rewrite(path: pathlib.Path, carried: set[str]) -> bool:
    """Widen and recount the table in ``path``, reporting whether bytes changed."""
    text = path.read_text(encoding="utf-8")
    ending = "\r\n" if "\r\n" in text else "\n"
    lines = text.replace("\r\n", "\n").split("\n")
    made = retotal(widen(lines, carried))
    fresh = ending.join(made)
    if fresh == text:
        return False
    path.write_text(fresh, encoding="utf-8", newline="")
    return True


def main(argv: list[str] | None = None) -> int:
    """Rewrite each named markdown file against the bundle, or refuse with 1."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=pathlib.Path, default=[DEFAULT_DOC])
    parser.add_argument("--bundle", type=pathlib.Path, default=None)
    args = parser.parse_args(argv)

    bundle = args.bundle or newest_bundle(ROOT)
    if bundle is None or not (bundle / BUNDLE_WEB).is_dir():
        print("no built react bundle to read: " + str(bundle), file=sys.stderr)
        return 1
    carried = bundle_modules(bundle)
    if not carried:
        print("the bundle carries no module: " + str(bundle), file=sys.stderr)
        return 1

    print("bundle  : " + str(bundle))
    print("modules : " + str(len(carried)))
    for path in args.paths or [DEFAULT_DOC]:
        changed = rewrite(path, carried)
        print(("rewrote " if changed else "same    ") + str(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
