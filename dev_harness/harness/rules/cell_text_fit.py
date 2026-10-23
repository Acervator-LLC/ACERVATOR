"""cell_text_fit.py — a table cell's drawn text against its column's room.

`MEASURED_COLUMN_ROOM_PX` holds the room one cell column of a table measures,
`money_specimen` reads the narrowest figure a bare money format draws,
`drawn_text_names` takes the names a function returns under `DRAWN_TEXT_KEY`,
and `appended_texts` resolves what each later assignment adds to one of those
names. `module_constants` and `imported_constants` supply the string each of
those names resolves through. `scan` composes the specimen with every appended
text, measures the result through `measured_widths`, and reports CF001 for a
composition wider than the room. `measured_widths` runs a child process per Qt
platform plugin and takes the first reading whose font database holds a family;
a reading taken against zero families raises.
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import string
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FALSIFICATION = (
    "This rule module is wrong if: (a) it reports a composition the function "
    "cannot draw, including two appends that sit in sibling branches of one "
    "if/elif chain, which are counted once; (b) it reports a name the function "
    "returns under a key other than DRAWN_TEXT_KEY, a tooltip above all, whose "
    "length costs nothing; (c) it reports a composition narrower than the room "
    "MEASURED_COLUMN_ROOM_PX holds for that file; (d) it stays quiet on a "
    "composition wider than that room; (e) a width was taken against a font "
    "database holding zero families, in which case the run raises and reports "
    "nothing instead of passing; (f) it takes its specimen from a format "
    "carrying prose beside its money field, which writes a sentence and not a "
    "cell. Known gaps: a file absent from MEASURED_COLUMN_ROOM_PX is never "
    "measured, because no room has been read off its table; a figure wider "
    "than the narrowest a bare money format draws is not composed, so the rule "
    "under-reports every real figure above it; a name imported from a module "
    "that itself imports it is not resolved, because imported_constants reads "
    "one level only; an assignment whose added text does not resolve to a "
    "string constant is skipped; the same text appended twice outside a branch "
    "is measured once; and the room is the whole column, with no allowance for "
    "the cell's own padding, so a text that overruns only the padding is not "
    "reported."
)


@dataclass
class Finding:
    """One `cell_text_fit` result, shaped like every rule module's `Finding`."""

    tool: str
    severity: str
    file: str
    line: int
    rule_id: str
    message: str


_REPO_ROOT = Path(__file__).resolve().parents[3]

#: The room one cell column of a file's table measures, in pixels. Read off
#: `BotStatusTable.columnWidth` with the table resized to 1400, the width
#: `MainWindow` declares as its narrowest; its eight stretch columns read 159,
#: 159 and 158 six times. The table inside the window is narrower than the
#: window, so 158 is an upper bound and the rule under-reports.
MEASURED_COLUMN_ROOM_PX: dict[str, int] = {
    "src/gui/main_tabs/table_cells_surface.py": 158,
    "src/gui/table_cells.py": 158,
    "harness_fixtures/gui_archetype/known_good_cell_text_fit.py": 158,
    "harness_fixtures/gui_archetype/known_bad_cell_text_fit.py": 158,
}

#: The mapping key a cell's drawn text is returned under. Every other key, the
#: tooltip included, is left unmeasured.
DRAWN_TEXT_KEY = "text"

#: The currency sign a money format writes before its figure.
MONEY_SIGN = "$"

#: A money format's own decimal count, and whether it groups its thousands.
_MONEY_SPEC = re.compile(r"^(?P<group>,?)\.(?P<places>\d+)f$")

#: The integer part the narrowest grouped figure draws, so a grouping mark is
#: never measured against a figure too small to carry one.
_GROUPED_INTEGER = "1,000"

_UNGROUPED_INTEGER = "0"

#: The Qt platform plugins tried, in order, until one registers a font family.
_FONT_PLUGINS: dict[str, tuple[str, ...]] = {
    "win32": ("windows", "offscreen"),
    "darwin": ("cocoa", "offscreen"),
}

_FALLBACK_FONT_PLUGINS: tuple[str, ...] = ("xcb", "offscreen")

_MODULE = "dev_harness.harness.rules.cell_text_fit"

#: The variable the texts to measure are handed to the child on. Argv stays
#: literal, so the call draws no S603 and needs no suppression.
_TEXTS_VAR = "ACERVATOR_CELL_FIT_TEXTS"

_MEASURE_TIMEOUT_S = 120


def repo_path(target: Path) -> str:
    """Return `target` as a repo-relative posix path, empty when it is outside."""
    try:
        return Path(target).resolve().relative_to(_REPO_ROOT).as_posix()
    except ValueError:
        return ""


def module_constants(tree: ast.Module) -> dict[str, str]:
    """Return every module-level name bound to a string constant."""
    out: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            out[target.id] = node.value.value
    return out


def _imported_module_file(target: Path, node: ast.ImportFrom) -> Path | None:
    """Return the repo file `node` imports from, None when it names none."""
    parts = (node.module or "").split(".")
    if node.level:
        base = Path(target).resolve().parent
        for _step in range(node.level - 1):
            base = base.parent
    else:
        base = _REPO_ROOT
    candidate = base.joinpath(*parts).with_suffix(".py")
    return candidate if candidate.is_file() else None


def imported_constants(target: Path, tree: ast.Module) -> dict[str, str]:
    """Return every string constant `target` imports by name from a repo module.

    One level deep: the imported module's own constants are read and its own
    imports are not followed.
    """
    out: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        source_file = _imported_module_file(target, node)
        if source_file is None:
            continue
        try:
            held = module_constants(ast.parse(source_file.read_text(encoding="utf-8")))
        except (OSError, SyntaxError, ValueError):
            continue
        for alias in node.names:
            text = held.get(alias.name)
            if text is not None:
                out[alias.asname or alias.name] = text
    return out


def constant_text(node: ast.AST, consts: dict[str, str]) -> str | None:
    """Return the string `node` resolves to, None when it resolves to none."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return consts.get(node.id)
    return None


def _spec_specimen(spec: str) -> str | None:
    """Return the narrowest figure a `_MONEY_SPEC` spec commits to drawing."""
    match = _MONEY_SPEC.match(spec)
    if match is None:
        return None
    places = int(match.group("places"))
    integer = _GROUPED_INTEGER if match.group("group") else _UNGROUPED_INTEGER
    decimals = f".{'0' * places}" if places else ""
    return f"{MONEY_SIGN}{integer}{decimals}"


def _figure_specimen(text: str) -> str | None:
    """Return the specimen when `text` is a bare money figure format.

    A format carrying prose beside its field writes a sentence, never a cell,
    and supplies no specimen.
    """
    try:
        fields = list(string.Formatter().parse(text))
    except ValueError:
        return None
    if len(fields) != 1:
        return None
    literal, field, spec, _conversion = fields[0]
    if literal != MONEY_SIGN or field is None or spec is None:
        return None
    return _spec_specimen(spec)


def _joined_figure_specimen(node: ast.JoinedStr) -> str | None:
    """Return the specimen when the f-string `node` is a bare money figure."""
    if len(node.values) != 2:
        return None
    sign, field = node.values
    if not (isinstance(sign, ast.Constant) and sign.value == MONEY_SIGN):
        return None
    if not isinstance(field, ast.FormattedValue):
        return None
    spec = field.format_spec
    if not isinstance(spec, ast.JoinedStr) or not spec.values:
        return None
    resolved = constant_text(spec.values[0], {})
    return _spec_specimen(resolved) if resolved else None


def money_specimen(tree: ast.Module, consts: dict[str, str]) -> str | None:
    """Return the narrowest money figure a figure format in `tree` draws."""
    specimens: list[str] = []
    for text in consts.values():
        specimen = _figure_specimen(text)
        if specimen is not None:
            specimens.append(specimen)
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            specimen = _joined_figure_specimen(node)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            specimen = _figure_specimen(node.value)
        else:
            specimen = None
        if specimen is not None:
            specimens.append(specimen)
    if not specimens:
        return None
    return min(specimens, key=len)


def drawn_text_names(scope: ast.AST) -> set[str]:
    """Return every name `scope` returns in a mapping under `DRAWN_TEXT_KEY`."""
    names: set[str] = set()
    for node in ast.walk(scope):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values, strict=True):
            if not (isinstance(key, ast.Constant) and key.value == DRAWN_TEXT_KEY):
                continue
            if isinstance(value, ast.Name):
                names.add(value.id)
    return names


def _joined_addition(
    node: ast.JoinedStr, name: str, consts: dict[str, str]
) -> str | None:
    """Return the text an f-string adds beside `name`, None when a part is open."""
    added: list[str] = []
    carried = False
    for part in node.values:
        if isinstance(part, ast.FormattedValue):
            if isinstance(part.value, ast.Name) and part.value.id == name:
                carried = True
                continue
            if part.format_spec is not None:
                return None
            text = constant_text(part.value, consts)
        else:
            text = constant_text(part, consts)
        if text is None:
            return None
        added.append(text)
    return "".join(added) if carried else None


def _format_addition(node: ast.Call, name: str, consts: dict[str, str]) -> str | None:
    """Return the text a `format` call adds beside `name`, None when a field is open."""
    if not (isinstance(node.func, ast.Attribute) and node.func.attr == "format"):
        return None
    if node.args:
        return None
    template = constant_text(node.func.value, consts)
    if template is None:
        return None
    values: dict[str, str | None] = {}
    carried = ""
    for keyword in node.keywords:
        if keyword.arg is None:
            return None
        if isinstance(keyword.value, ast.Name) and keyword.value.id == name:
            carried = keyword.arg
            values[keyword.arg] = ""
            continue
        values[keyword.arg] = constant_text(keyword.value, consts)
    if not carried:
        return None
    return _filled_template(template, values)


def _filled_template(template: str, values: dict[str, str | None]) -> str | None:
    """Return `template` with each field taken from `values`, None when one is open."""
    added: list[str] = []
    try:
        fields = list(string.Formatter().parse(template))
    except ValueError:
        return None
    for literal, field, _spec, _conversion in fields:
        added.append(literal)
        if field is None:
            continue
        filled = values.get(field)
        if filled is None:
            return None
        added.append(filled)
    return "".join(added)


def appended_texts(scope: ast.AST, name: str, consts: dict[str, str]) -> list[str]:
    """Return each distinct text an assignment in `scope` adds to `name`, in order."""
    out: list[str] = []
    for node in ast.walk(scope):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not (isinstance(target, ast.Name) and target.id == name):
            continue
        if isinstance(node.value, ast.JoinedStr):
            added = _joined_addition(node.value, name, consts)
        elif isinstance(node.value, ast.Call):
            added = _format_addition(node.value, name, consts)
        else:
            added = None
        if added and added not in out:
            out.append(added)
    return out


def _measure_once(plugin: str, texts: list[str]) -> dict[str, Any] | None:
    """Return one child's font reading for `plugin`, None when it did not report."""
    scratch = Path(tempfile.mkdtemp(prefix="acervator_cell_fit_home_"))
    env = dict(os.environ)
    for key in ("HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA"):
        env[key] = str(scratch)
    env["QT_QPA_PLATFORM"] = plugin
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env[_TEXTS_VAR] = json.dumps(texts)
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "dev_harness.harness.rules.cell_text_fit"],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
            env=env,
            timeout=_MEASURE_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    printed = (proc.stdout or "").strip().splitlines()
    if not printed:
        return None
    try:
        reading = json.loads(printed[-1])
    except ValueError:
        return None
    return reading if int(reading.get("families", 0)) > 0 else None


def measured_widths(texts: list[str]) -> dict[str, Any]:
    """Return the drawn width of each text, read on a plugin that holds fonts.

    Raises when no plugin registers a font family, which leaves every glyph one
    blank box of a single width.
    """
    plugins = _FONT_PLUGINS.get(sys.platform, _FALLBACK_FONT_PLUGINS)
    for plugin in plugins:
        reading = _measure_once(plugin, texts)
        if reading is not None:
            return reading
    refusal = (
        f"no Qt platform plugin of {', '.join(plugins)} registered a font "
        f"family, so every drawn width reads as a blank box and no cell text "
        f"can be measured"
    )
    raise RuntimeError(refusal)


def _compositions(
    tree: ast.Module, consts: dict[str, str], base: str
) -> list[tuple[str, int, str, str]]:
    """Return `(function, line, composed, added)` for each marked drawn text."""
    out: list[tuple[str, int, str, str]] = []
    for scope in ast.walk(tree):
        if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for name in sorted(drawn_text_names(scope)):
            added = "".join(appended_texts(scope, name, consts))
            if not added:
                continue
            out.append((scope.name, scope.lineno, base + added, added))
    return out


def _finding(target: Path, line: int, message: str) -> Finding:
    """Return one CF001 `Finding` for `target` at `line`, severity high."""
    return Finding(
        tool="cell_text_fit",
        severity="high",
        file=str(target),
        line=line,
        rule_id="CF001",
        message=message,
    )


def scan(target: Path, source: str) -> list[Any]:
    """Return every CF001 finding for `source`, empty when no room is held."""
    room = MEASURED_COLUMN_ROOM_PX.get(repo_path(target))
    if room is None:
        return []
    try:
        tree = ast.parse(source, filename=str(target))
    except SyntaxError:
        return []
    consts = imported_constants(target, tree) | module_constants(tree)
    base = money_specimen(tree, consts)
    if base is None:
        return []
    compositions = _compositions(tree, consts, base)
    if not compositions:
        return []
    reading = measured_widths([composed for _f, _l, composed, _a in compositions])
    widths = dict(zip(reading["texts"], reading["widths"], strict=True))
    return [
        _finding(
            target,
            line,
            f"{function}() composes the drawn text {composed!r}, which measures "
            f"{int(widths[composed])} px in {reading['family']} at "
            f"{reading['point_size']:g} pt. The narrowest cell column of this "
            f"table measures {room} px, so the cell cannot draw the text whole "
            f"and cuts it. {base!r} is the narrowest figure this cell's own "
            f"money format commits to drawing, so a larger figure is cut "
            f"further. Move {added!r} into the cell's tooltip, which has no "
            f"width limit.",
        )
        for function, line, composed, added in compositions
        if int(widths[composed]) > room
    ]


def _emit_measurement(texts: list[str]) -> int:
    """Print one JSON font reading for `texts` and return the process exit code."""
    from PySide6.QtGui import QFont, QFontDatabase, QFontMetrics
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    font = QFont()
    metrics = QFontMetrics(font)
    reading = {
        "plugin": os.environ.get("QT_QPA_PLATFORM", ""),
        "families": len(QFontDatabase.families()),
        "family": font.family(),
        "point_size": font.pointSizeF(),
        "texts": texts,
        "widths": [metrics.horizontalAdvance(text) for text in texts],
    }
    sys.stdout.write(json.dumps(reading) + "\n")
    sys.stdout.flush()
    app.quit()
    return 0


def main() -> int:
    """Measure the texts `_TEXTS_VAR` carries and return the child's exit code."""
    try:
        texts = json.loads(os.environ[_TEXTS_VAR])
    except (KeyError, ValueError):
        sys.stderr.write(f"{_MODULE}: {_TEXTS_VAR} carries no list of texts\n")
        return 2
    return _emit_measurement([str(text) for text in texts])


__all__ = [
    "DRAWN_TEXT_KEY",
    "FALSIFICATION",
    "MEASURED_COLUMN_ROOM_PX",
    "Finding",
    "appended_texts",
    "drawn_text_names",
    "measured_widths",
    "money_specimen",
    "scan",
]


if __name__ == "__main__":
    raise SystemExit(main())
