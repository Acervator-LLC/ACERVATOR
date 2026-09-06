"""Scope column for the #128 conversion table, measured from the running window.

``closure`` walks ``src/gui/main_window.py`` over use edges: an imported name
becomes an edge only where the module calls it, subclasses it, decorates with
it or reads an attribute of it. ``verdict`` answers one of ``IN_SCOPE``,
``REACT_SIDE``, ``NOT_A_SCREEN``, ``SHELL`` and ``SHELVED`` for one Qt file,
and ``rewrite`` writes that answer into a ``SCOPE_COLUMN`` cell on every row.
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import conversion_state, conversion_table  # noqa: E402

DEFAULT_DOC = ROOT / "docs" / "manual" / "08-tabs.md"

WINDOW = pathlib.PurePosixPath("src/gui/main_window.py")
REGISTRY = pathlib.PurePosixPath("src/gui/variant_surface.py")
PACKAGE_ROOT = "src"
TAB_INSERTERS = ("addTab", "insertTab")
MAIN_TAB_BOOK = "_main_tabs"

IN_SCOPE = "in scope"
REACT_SIDE = "React side"
NOT_A_SCREEN = "not a screen"
SHELL = "builds the shell"
SHELVED = "shelved"

SCOPE_COLUMN = conversion_table.SCOPE_COLUMN


def module_path(root: pathlib.Path, dotted: str) -> pathlib.Path | None:
    """The file a dotted import name resolves to, or None."""
    parts = dotted.split(".")
    module = root.joinpath(*parts).with_suffix(".py")
    if module.is_file():
        return module
    package = root.joinpath(*parts) / "__init__.py"
    return package if package.is_file() else None


def dotted_name(root: pathlib.Path, path: pathlib.Path) -> str:
    """The dotted import name of a file inside the repository."""
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def absolute_target(
    root: pathlib.Path, owner: pathlib.Path, node: ast.ImportFrom
) -> str:
    """The dotted module one ``from`` import names, relative levels resolved."""
    if not node.level:
        return node.module or ""
    parts = dotted_name(root, owner).split(".")
    if owner.name != "__init__.py":
        parts = parts[:-1]
    climb = node.level - 1
    if climb:
        parts = parts[:-climb] if climb <= len(parts) else []
    named = [part for part in parts if part]
    return ".".join(named + ([node.module] if node.module else []))


def used_names(tree: ast.Module) -> set[str]:
    """Every name the module calls, subclasses, decorates with or reads from.

    A name held only by an import and an ``__all__`` string is not among them.
    """
    found: set[str] = set()

    def owner(node: ast.AST) -> None:
        while isinstance(node, (ast.Attribute, ast.Subscript)):
            node = node.value
        if isinstance(node, ast.Name):
            found.add(node.id)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            owner(node.func)
        elif isinstance(node, ast.ClassDef):
            for base in node.bases:
                owner(base)
            for decorator in node.decorator_list:
                owner(decorator)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                owner(decorator)
        elif isinstance(node, ast.Attribute):
            owner(node.value)
    return found


def _parse(path: pathlib.Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return None


def screen_loaders(root: pathlib.Path) -> dict[str, set[pathlib.Path]]:
    """The modules each ``variant_surface`` screen constant can load.

    ``register(SCREEN, qt_loader, react_loader)`` names the two loaders, and
    each loader body imports the one widget module it returns.
    """
    registry = root / REGISTRY
    tree = _parse(registry)
    if tree is None:
        return {}
    inside: dict[str, set[pathlib.Path]] = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        reached = set()
        for inner in ast.walk(node):
            if isinstance(inner, ast.ImportFrom):
                target = module_path(root, absolute_target(root, registry, inner))
                if target is not None:
                    reached.add(target)
        inside[node.name] = reached
    screens: dict[str, set[pathlib.Path]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id == "register"):
            continue
        names = [arg.id for arg in node.args if isinstance(arg, ast.Name)]
        if not names:
            continue
        holder = screens.setdefault(names[0], set())
        for loader in names[1:]:
            holder.update(inside.get(loader, set()))
    return screens


def edges(root: pathlib.Path, path: pathlib.Path) -> set[pathlib.Path]:
    """Every repository module ``path`` uses, the registry followed by screen.

    An ``__init__.py`` re-exports, so every import it carries is an edge.
    """
    tree = _parse(path)
    if tree is None or path.relative_to(root).as_posix() == str(REGISTRY):
        return set()
    screens = screen_loaders(root)
    transparent = path.name == "__init__.py"
    used = None if transparent else used_names(tree)
    reached: set[pathlib.Path] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            target = absolute_target(root, path, node)
            if not target.startswith(PACKAGE_ROOT + "."):
                continue
            owner = module_path(root, target)
            named = owner is not None and owner.relative_to(root).as_posix()
            if named == str(REGISTRY):
                for alias in node.names:
                    reached.update(screens.get(alias.name, set()))
                continue
            for alias in node.names:
                local = alias.asname or alias.name
                if used is not None and local not in used:
                    continue
                sub = module_path(root, target + "." + alias.name)
                if sub is not None:
                    reached.add(sub)
                elif owner is not None:
                    reached.add(owner)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if not alias.name.startswith(PACKAGE_ROOT + "."):
                    continue
                local = alias.asname or alias.name.split(".")[0]
                if used is not None and local not in used:
                    continue
                owner = module_path(root, alias.name)
                if owner is not None:
                    reached.add(owner)
    return reached


def closure(root: pathlib.Path, start: pathlib.Path) -> set[pathlib.Path]:
    """Every module reached from ``start`` over the use edges, ``start`` included."""
    seen = {start}
    pending = [start]
    while pending:
        for step in edges(root, pending.pop()):
            if step not in seen:
                seen.add(step)
                pending.append(step)
    return seen


def class_names(tree: ast.Module) -> set[str]:
    """Every class the module defines."""
    return {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}


def constructed_names(tree: ast.Module) -> set[str]:
    """Every bare name the module calls or names as a base class.

    ``Klass.helper()`` reads an attribute of ``Klass`` and is not among them.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            found.add(node.func.id)
        elif isinstance(node, ast.ClassDef):
            for base in node.bases:
                if isinstance(base, ast.Name):
                    found.add(base.id)
    return found


def built_modules(
    root: pathlib.Path, reached: set[pathlib.Path]
) -> dict[pathlib.Path, set[pathlib.Path]]:
    """Each class-defining module one of ``reached`` builds, and what builds it.

    ``constructed_names`` reads the bare calls, so a module reached only by a
    constant read stays out.
    """
    found: dict[pathlib.Path, set[pathlib.Path]] = {}
    defined: dict[pathlib.Path, set[str]] = {}
    for path in reached:
        tree = _parse(path)
        if tree is None:
            continue
        makes = constructed_names(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            target = absolute_target(root, path, node)
            if not target.startswith(PACKAGE_ROOT + "."):
                continue
            for alias in node.names:
                if (alias.asname or alias.name) not in makes:
                    continue
                owner = module_path(root, target)
                if owner is None:
                    continue
                if owner not in defined:
                    inner = _parse(owner)
                    defined[owner] = class_names(inner) if inner else set()
                if defined[owner]:
                    found.setdefault(owner, set()).add(path)
    return found


def fills_the_tab_bar(path: pathlib.Path) -> bool:
    """Whether the module calls a ``TAB_INSERTERS`` name on ``MAIN_TAB_BOOK``.

    A dialog that builds a tab book of its own answers False.
    """
    tree = _parse(path)
    if tree is None:
        return False
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr not in TAB_INSERTERS:
            continue
        book = node.func.value
        if isinstance(book, ast.Attribute) and book.attr == MAIN_TAB_BOOK:
            return True
    return False


def react_pairs(root: pathlib.Path) -> set[pathlib.Path]:
    """Every module the conversion itself produced, and the Qt half each replaces.

    A module loading a renderer file, a view model the bridge registers, and
    the Qt loader ``screen_loaders`` pairs with a loading React one.
    """
    loaded = conversion_state.renderer_modules(root)
    found: set[pathlib.Path] = set()
    for members in screen_loaders(root).values():
        hosts = {
            path
            for path in members
            if conversion_state.hosted_module(
                path.read_text(encoding="utf-8", errors="replace"), loaded
            )
        }
        if hosts:
            found.update(members)
    registered = conversion_state.registered_surfaces(root)
    for name in conversion_state.surface_methods(root):
        if name not in registered:
            continue
        for path in (root / "src").rglob(name + ".py"):
            found.add(path)
    return found


def verdict(
    row: str,
    renders: str,
    root: pathlib.Path,
    reach: tuple[set[pathlib.Path], set[pathlib.Path], set[pathlib.Path]],
) -> str:
    """One of the five scope answers for one row of the conversion table."""
    window, built, pairs = reach
    path = root / row
    if not path.is_file():
        return SHELVED
    if renders == conversion_table.YES:
        return IN_SCOPE
    if path in window and (fills_the_tab_bar(path) or row == str(WINDOW)):
        return SHELL
    if path in pairs:
        return REACT_SIDE
    reason = conversion_state.plumbing_reason(
        path, path.read_text(encoding="utf-8", errors="replace")
    )
    if path in window and reason in (
        conversion_state.PACKAGE_MARKER,
        conversion_state.NO_CLASS,
    ):
        return NOT_A_SCREEN
    return IN_SCOPE if path in built else SHELVED


def owning_screens(root: pathlib.Path, path: pathlib.Path, built: dict) -> str:
    """The modules that build ``path``, named by file and comma joined."""
    owners = built.get(path, set())
    return ", ".join(
        sorted(one.relative_to(root).as_posix().rsplit("/", 1)[-1] for one in owners)
    )


def scope_cells(root: pathlib.Path, rows: list[tuple[str, str]]) -> dict[str, str]:
    """One scope cell per ``(row, renders)`` pair, keyed by the row."""
    window = closure(root, root / str(WINDOW))
    built = built_modules(root, window)
    reach = (window, set(built), react_pairs(root))
    cells: dict[str, str] = {}
    for row, renders in rows:
        answer = verdict(row, renders, root, reach)
        if answer == IN_SCOPE and renders != conversion_table.YES:
            owners = owning_screens(root, root / row, built)
            answer = IN_SCOPE + (", built by " + owners if owners else "")
        cells[row] = answer
    return cells


def table_rows(lines: list[str]) -> list[tuple[str, str]]:
    """The Qt file and RENDERS cell of every row of the conversion table."""
    start, end = conversion_table.table_span(lines)
    heads = conversion_table.split_cells(lines[start])
    last = heads.index(conversion_table.LAST_COLUMN)
    rows = []
    for index in range(start + 2, end + 1):
        cells = conversion_table.split_cells(lines[index])
        rows.append((cells[0].strip("`"), cells[last]))
    return rows


def widen(root: pathlib.Path, lines: list[str]) -> list[str]:
    """``lines`` with a ``SCOPE_COLUMN`` cell on every row of the table."""
    start, end = conversion_table.table_span(lines)
    heads = conversion_table.split_cells(lines[start])
    cells = scope_cells(root, table_rows(lines))
    if SCOPE_COLUMN in heads:
        at = heads.index(SCOPE_COLUMN)
    else:
        at = len(heads)
        heads.append(SCOPE_COLUMN)
    out = list(lines)
    out[start] = conversion_table.join_cells(heads)
    out[start + 1] = conversion_table.join_cells(["---"] * len(heads))
    for index in range(start + 2, end + 1):
        row = conversion_table.split_cells(out[index])
        value = cells[row[0].strip("`")]
        out[index] = conversion_table.join_cells(
            conversion_table.place_cell(row, value, at)
        )
    return out


def rewrite(root: pathlib.Path, path: pathlib.Path) -> bool:
    """Write the scope column and recount the totals, reporting a byte change."""
    text = path.read_text(encoding="utf-8")
    ending = "\r\n" if "\r\n" in text else "\n"
    lines = text.replace("\r\n", "\n").split("\n")
    fresh = ending.join(conversion_table.retotal(widen(root, lines)))
    if fresh == text:
        return False
    path.write_text(fresh, encoding="utf-8", newline="")
    return True


def main(argv: list[str] | None = None) -> int:
    """Write the scope column into each named markdown file."""
    parser = argparse.ArgumentParser(description="Scope column for the #128 table.")
    parser.add_argument("paths", nargs="*", type=pathlib.Path)
    args = parser.parse_args(argv)
    for path in args.paths or [DEFAULT_DOC]:
        changed = rewrite(ROOT, path)
        print(("rewrote " if changed else "same    ") + str(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
