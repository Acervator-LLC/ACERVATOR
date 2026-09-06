"""The build column of the conversion table, driven against fake react bundles.

``tools.conversion_table.rewrite`` is run over a small table whose rows differ
from each other in every cell, so a column read at the wrong index cannot pass.
Each test states the bundle it built and the marks that bundle must produce.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import conversion_table  # noqa: E402

TABLE = """# Heading

| Qt file | React module | Uses React | Bridge | Manifest | RENDERS |
| --- | --- | --- | --- | --- | --- |
| `a.py` | `alpha.js` | yes | yes | yes | yes |
| `b.py` | `beta.js` | no | yes | no | no |
| `c.py` | no | - | no | no | no |

Totals:

```
React module             2
Uses React               1
Bridge                   2
Manifest                 1
RENDERS                  1
```

Tail sentence.
"""


def make_bundle(root: pathlib.Path, names: tuple[str, ...]) -> pathlib.Path:
    """Build a bundle under ``root`` carrying one empty file per name."""
    web = root / conversion_table.BUNDLE_WEB
    web.mkdir(parents=True, exist_ok=True)
    for name in names:
        (web / name).write_text("", encoding="utf-8")
    return root


def write_table(tmp_path: pathlib.Path) -> pathlib.Path:
    """Write ``TABLE`` under ``tmp_path`` and return the path."""
    doc = tmp_path / "table.md"
    doc.write_text(TABLE, encoding="utf-8")
    return doc


def marks(doc: pathlib.Path) -> dict[str, str]:
    """The build cell of every row, keyed by the Qt file the row names."""
    lines = doc.read_text(encoding="utf-8").splitlines()
    start, end = conversion_table.table_span(lines)
    heads = conversion_table.split_cells(lines[start])
    at = heads.index(conversion_table.BUILD_COLUMN)
    found = {}
    for line in lines[start + 2 : end + 1]:
        cells = conversion_table.split_cells(line)
        found[cells[0]] = cells[at]
    return found


def totals(doc: pathlib.Path) -> dict[str, int]:
    """The name and count of every line in the fenced block after the table."""
    lines = doc.read_text(encoding="utf-8").splitlines()
    _, end = conversion_table.table_span(lines)
    opened = next(i for i in range(end + 1, len(lines)) if lines[i].startswith("```"))
    found = {}
    for line in lines[opened + 1 :]:
        if line.startswith("```"):
            break
        found[line[: conversion_table.TOTAL_WIDTH].strip()] = int(
            line[conversion_table.TOTAL_WIDTH :]
        )
    return found


def test_a_module_the_bundle_carries_is_marked_yes(tmp_path: pathlib.Path) -> None:
    """``alpha.js`` is in the bundle, so the row naming it reads yes."""
    doc = write_table(tmp_path)
    conversion_table.rewrite(doc, {"alpha.js"})
    assert marks(doc)["`a.py`"] == "yes", marks(doc)


def test_a_module_the_bundle_lacks_is_marked_no(tmp_path: pathlib.Path) -> None:
    """The control for the row above: ``beta.js`` is absent and its row reads no."""
    doc = write_table(tmp_path)
    conversion_table.rewrite(doc, {"alpha.js"})
    assert marks(doc)["`b.py`"] == "no", marks(doc)


def test_a_row_naming_no_module_is_marked_with_a_dash(tmp_path: pathlib.Path) -> None:
    """A row whose React module cell reads ``no`` has nothing to ship."""
    doc = write_table(tmp_path)
    conversion_table.rewrite(doc, {"alpha.js", "beta.js"})
    assert marks(doc)["`c.py`"] == "-", marks(doc)


def test_an_empty_bundle_marks_every_named_row_no(tmp_path: pathlib.Path) -> None:
    """No module ships, so no row that names one reads yes."""
    doc = write_table(tmp_path)
    conversion_table.rewrite(doc, set())
    assert marks(doc) == {"`a.py`": "no", "`b.py`": "no", "`c.py`": "-"}


def test_the_column_sits_immediately_before_the_renders_column(
    tmp_path: pathlib.Path,
) -> None:
    """``RENDERS`` stays the last column, and the build column precedes it."""
    doc = write_table(tmp_path)
    conversion_table.rewrite(doc, {"alpha.js"})
    lines = doc.read_text(encoding="utf-8").splitlines()
    start, _ = conversion_table.table_span(lines)
    heads = conversion_table.split_cells(lines[start])
    assert heads[-2:] == [conversion_table.BUILD_COLUMN, "RENDERS"], heads


def test_every_mark_already_in_the_table_survives_the_rewrite(
    tmp_path: pathlib.Path,
) -> None:
    """Only the build cell is written, and the other cells come back unchanged."""
    doc = write_table(tmp_path)
    before = [
        conversion_table.split_cells(line)
        for line in TABLE.splitlines()
        if line.startswith("| `")
    ]
    conversion_table.rewrite(doc, {"alpha.js"})
    lines = doc.read_text(encoding="utf-8").splitlines()
    start, end = conversion_table.table_span(lines)
    at = conversion_table.split_cells(lines[start]).index(conversion_table.BUILD_COLUMN)
    for old, line in zip(before, lines[start + 2 : end + 1]):
        cells = conversion_table.split_cells(line)
        del cells[at]
        assert cells == old, (cells, old)


def test_the_totals_block_counts_the_new_column(tmp_path: pathlib.Path) -> None:
    """One module ships, so the build total reads 1 beside the other counts."""
    doc = write_table(tmp_path)
    conversion_table.rewrite(doc, {"alpha.js"})
    assert totals(doc)[conversion_table.BUILD_COLUMN] == 1, totals(doc)


def test_the_totals_block_recounts_a_stale_column(tmp_path: pathlib.Path) -> None:
    """The written table marks RENDERS once, whatever the old block claimed."""
    doc = tmp_path / "stale.md"
    doc.write_text(TABLE.replace("RENDERS                  1", "RENDERS   9"), "utf-8")
    conversion_table.rewrite(doc, {"alpha.js"})
    assert totals(doc)["RENDERS"] == 1, totals(doc)


def test_the_prose_around_the_table_is_untouched(tmp_path: pathlib.Path) -> None:
    """Every line that is neither a table row nor a total survives verbatim."""
    doc = write_table(tmp_path)
    conversion_table.rewrite(doc, {"alpha.js"})
    fresh = doc.read_text(encoding="utf-8").splitlines()
    assert "# Heading" in fresh and "Tail sentence." in fresh, fresh


def test_a_second_run_changes_nothing(tmp_path: pathlib.Path) -> None:
    """``rewrite`` reports False on a table already carrying the measured marks."""
    doc = write_table(tmp_path)
    conversion_table.rewrite(doc, {"alpha.js"})
    assert conversion_table.rewrite(doc, {"alpha.js"}) is False


def test_a_file_with_no_totals_block_is_widened_all_the_same(
    tmp_path: pathlib.Path,
) -> None:
    """The issue body holds the table and no block, and still gets the column."""
    doc = tmp_path / "body.md"
    doc.write_text(TABLE.split("Totals:")[0], encoding="utf-8")
    conversion_table.rewrite(doc, {"beta.js"})
    assert marks(doc) == {"`a.py`": "no", "`b.py`": "yes", "`c.py`": "-"}


def test_bundle_modules_reads_the_names_the_bundle_carries(
    tmp_path: pathlib.Path,
) -> None:
    """``bundle_modules`` answers the ``.js`` names under ``BUNDLE_WEB``."""
    bundle = make_bundle(tmp_path / "one", ("alpha.js", "gamma.js"))
    assert conversion_table.bundle_modules(bundle) == {"alpha.js", "gamma.js"}


def test_main_refuses_when_no_bundle_holds_the_modules(
    tmp_path: pathlib.Path,
) -> None:
    """A missing bundle exits 1, so an unread bundle never reads as an empty one."""
    doc = write_table(tmp_path)
    code = conversion_table.main([str(doc), "--bundle", str(tmp_path / "absent")])
    assert code == 1
    assert conversion_table.BUILD_COLUMN not in doc.read_text(encoding="utf-8")


def test_main_refuses_a_bundle_carrying_nothing(tmp_path: pathlib.Path) -> None:
    """An empty ``BUNDLE_WEB`` exits 1 and marks no row."""
    doc = write_table(tmp_path)
    bundle = make_bundle(tmp_path / "empty", ())
    assert conversion_table.main([str(doc), "--bundle", str(bundle)]) == 1
    assert conversion_table.BUILD_COLUMN not in doc.read_text(encoding="utf-8")


def test_main_writes_the_column_from_a_real_bundle(tmp_path: pathlib.Path) -> None:
    """``main`` exits 0 and the marks follow the names the bundle carries."""
    doc = write_table(tmp_path)
    bundle = make_bundle(tmp_path / "built", ("beta.js",))
    assert conversion_table.main([str(doc), "--bundle", str(bundle)]) == 0
    assert marks(doc) == {"`a.py`": "no", "`b.py`": "yes", "`c.py`": "-"}


@pytest.mark.parametrize(
    ("cell", "carried", "expected"),
    [
        ("`alpha.js`", {"alpha.js"}, "yes"),
        ("`alpha.js`", set(), "no"),
        ("no", {"alpha.js"}, "-"),
        ("", {"alpha.js"}, "-"),
    ],
)
def test_ship_mark_answers_each_kind_of_cell(
    cell: str, carried: set, expected: str
) -> None:
    """``ship_mark`` reads one React module cell against the carried names."""
    assert conversion_table.ship_mark(cell, carried) == expected
