"""Shared PyInstaller spec content for Acervator_win.spec and Acervator_mac.spec.

``COMMON_HIDDENIMPORTS`` and ``EXCLUDES`` hold the names both spec files pass to
PyInstaller, and ``hiddenimports_for`` adds the one ``KEYRING_BACKENDS`` entry
that is per-platform. ``read_acervator_version`` and ``bake_version_datas``
resolve the version and write it under ``BAKE_SUBDIR`` for the bundle to carry.
``datas_candidates`` ships ``renderer_candidate`` in every variant, because the
Status tab reads ``panel_host.js`` from it under both, and adds
``shell_candidates`` to a ``REACT`` build alone. ``reachable_src_modules``
measures which modules ``ENTRY_SCRIPT`` can import, and ``reachable_only`` and
``unreachable_src_files`` keep the rest out of a build. Nothing here imports
PyInstaller, so the module imports on a machine that has none.
"""

from __future__ import annotations

import ast
import os
from collections import Counter
from collections.abc import Callable, Iterator
from typing import NamedTuple, TypeVar

from src._variant import REACT, normalise
from src._version import BAKED_FILENAME, UNKNOWN_VERSION, resolve_version

FALLBACK_VERSION = UNKNOWN_VERSION

# Regenerable and gitignored; `bake_version_datas` writes nothing into src/.
BAKE_SUBDIR = os.path.join("build", "version")

DESKTOP_DIRNAME = "desktop"
SHELL_RENDERER = "renderer"
SHELL_FILES: tuple[str, ...] = ("main.js", "preload.js", "package.json")

# npm writes this; a clone without `npm install` has the shell and no runtime.
ELECTRON_RUNTIME = os.path.join("node_modules", "electron", "dist")

#: The compiled-bytecode folder `build_graceful_datas` leaves out of a bundle.
CACHE_DIRNAME = "__pycache__"

#: Compiled file suffixes left out wherever they sit, inside `CACHE_DIRNAME` or not.
COMPILED_SUFFIXES: tuple[str, ...] = (".pyc", ".pyo")

#: The folder `src_modules` walks and `reachable_src_modules` measures.
SRC_DIRNAME = "src"

#: The one file `reachable_src_modules` starts its import walk from.
ENTRY_SCRIPT = "main.py"

#: The function a module calls on a module name it builds at run time.
DYNAMIC_IMPORT_CALL = "import_module"

#: The window's table of retired pages, as its module and its name.
RETIRED_PAGE_TABLE = ("src.gui.main_tabs.retired_surfaces", "SURFACE_MODULES")

#: The window's tuple of tabs ``MainWindow._setup_ui`` skips, as its module and its name.
UNBUILT_TAB_TUPLE = ("src.gui.main_tabs.main_window_surface", "UNBUILT_TABS")

#: The module that records each screen's two loaders through ``REGISTER_CALL``.
SCREEN_REGISTRY = "src.gui.variant_surface"

#: The call that records a screen's loaders in ``SCREEN_REGISTRY``.
REGISTER_CALL = "register"

#: The calls that ask ``SCREEN_REGISTRY`` for a screen by its name.
ASKING_CALLS: tuple[str, ...] = ("surface_class", "draws_react")

_Declared = TypeVar("_Declared", bound=ast.expr)


def read_acervator_version(project_root: str) -> str:
    """Return what ``resolve_version`` answers for the tree at ``project_root``."""
    return resolve_version(project_root)


def bake_version_datas(project_root: str) -> list[tuple[str, str]]:
    """Write ``read_acervator_version`` under ``BAKE_SUBDIR`` and return its pair.

    The destination is ``src``, where ``src/_version.py`` reads ``BAKED_FILENAME``.
    """
    out_dir = os.path.join(project_root, BAKE_SUBDIR)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, BAKED_FILENAME)
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(read_acervator_version(project_root) + "\n")
    return [(out_path, "src")]


def renderer_candidate(project_root: str) -> tuple[str, str]:
    """The (source, destination) pair of ``SHELL_RENDERER``, which every variant ships.

    ``src/gui/react_main_window.py`` reads ``panel_host.js`` from this folder
    under the bundle root, for the Status tab in both variants.
    """
    desktop = os.path.join(project_root, DESKTOP_DIRNAME)
    return (
        os.path.join(desktop, SHELL_RENDERER),
        os.path.join(DESKTOP_DIRNAME, SHELL_RENDERER),
    )


def shell_candidates(project_root: str) -> list[tuple[str, str]]:
    """Every (source, destination) pair the Electron shell needs beyond ``renderer_candidate``.

    ``SHELL_FILES`` keep the layout ``DESKTOP_DIRNAME`` has on disk, and
    ``ELECTRON_RUNTIME`` carries the electron executable; a ``REACT`` build
    ships them and no other variant does.
    """
    desktop = os.path.join(project_root, DESKTOP_DIRNAME)
    pairs = [(os.path.join(desktop, name), DESKTOP_DIRNAME) for name in SHELL_FILES]
    pairs.append(
        (
            os.path.join(desktop, ELECTRON_RUNTIME),
            os.path.join(DESKTOP_DIRNAME, ELECTRON_RUNTIME),
        )
    )
    return pairs


def datas_candidates(project_root: str, variant: str) -> list[tuple[str, str]]:
    """Every (source, destination) pair a ``variant`` build would ship.

    Every variant ships three directories and ``renderer_candidate``; ``REACT``
    adds ``shell_candidates``, and every other variant returns those four alone.
    """
    pairs = [
        (os.path.join(project_root, "src"), "src"),
        (os.path.join(project_root, "resources"), "resources"),
        # download_archive.py populates data/historical; a build without it works.
        (
            os.path.join(project_root, "data", "historical"),
            os.path.join("data", "historical"),
        ),
        renderer_candidate(project_root),
    ]
    if normalise(variant) == REACT:
        pairs.extend(shell_candidates(project_root))
    return pairs


def src_modules(project_root: str) -> dict[str, str]:
    """Map every module name under ``SRC_DIRNAME`` to the file that holds it."""
    held: dict[str, str] = {}
    root = os.path.join(project_root, SRC_DIRNAME)
    for here, children, names in os.walk(root):
        if CACHE_DIRNAME in children:
            children.remove(CACHE_DIRNAME)
        for name in names:
            if not name.endswith(".py"):
                continue
            path = os.path.join(here, name)
            dotted = os.path.relpath(path, project_root).replace(os.sep, ".")[:-3]
            if dotted.endswith(".__init__"):
                dotted = dotted[: -len(".__init__")]
            held[dotted] = os.path.normpath(path)
    return held


def _parsed(path: str) -> ast.Module:
    """Return the syntax tree of the file at ``path``."""
    with open(path, "rb") as handle:
        return ast.parse(handle.read(), filename=path)


def _in_src(name: str) -> bool:
    """True when ``name`` is ``SRC_DIRNAME`` or a dotted name under it."""
    return name == SRC_DIRNAME or name.startswith(SRC_DIRNAME + ".")


def _nodes_outside(tree: ast.AST, skipped: frozenset[str]) -> Iterator[ast.AST]:
    """Yield every node of ``tree`` that no function named in ``skipped`` holds."""
    pending = [tree]
    while pending:
        node = pending.pop()
        yield node
        for child in ast.iter_child_nodes(node):
            if (
                isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                and child.name in skipped
            ):
                continue
            pending.append(child)


def _called(call: ast.Call) -> str:
    """Return the name ``call`` calls, read off a bare name or an attribute."""
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return getattr(call.func, "id", "")


def _spelled(node: ast.AST) -> str | None:
    """Return the name or text ``node`` spells, or None for any other node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _src_import_names(
    tree: ast.Module,
    owner: str,
    is_package: bool,
    skipped: frozenset[str] = frozenset(),
) -> set[str]:
    """Return every ``SRC_DIRNAME`` module name the imports in ``tree`` name, for ``owner``.

    ``is_package`` marks an ``__init__`` file, whose relative imports resolve
    against ``owner`` itself, and an import inside a function ``skipped`` names
    is not read.
    """
    package = owner if is_package else owner.rpartition(".")[0]
    named: set[str] = set()
    for node in _nodes_outside(tree, skipped):
        if isinstance(node, ast.Import):
            named.update(alias.name for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            parts = package.split(".")
            base = ".".join(parts[: len(parts) - node.level + 1])
            head = f"{base}.{node.module}" if node.module else base
        else:
            head = node.module or ""
        if not head:
            continue
        named.add(head)
        named.update(f"{head}.{alias.name}" for alias in node.names)
    return {n for n in named if _in_src(n)}


def _joined_import_prefixes(
    tree: ast.Module, skipped: frozenset[str] = frozenset()
) -> set[str]:
    """Return every text literal a ``DYNAMIC_IMPORT_CALL`` argument joins a value onto.

    The literal is the left side of a ``+`` or the head of an f-string, an
    argument that is one whole literal adds nothing, and a call inside a function
    ``skipped`` names is not read.
    """
    out: set[str] = set()
    for node in _nodes_outside(tree, skipped):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        if _called(node) != DYNAMIC_IMPORT_CALL:
            continue
        head: ast.expr = node.args[0]
        if isinstance(head, ast.BinOp) and isinstance(head.op, ast.Add):
            head = head.left
        elif isinstance(head, ast.JoinedStr) and head.values:
            head = head.values[0]
        else:
            continue
        if isinstance(head, ast.Constant) and isinstance(head.value, str):
            out.add(head.value)
    return out


def _dynamic_src_names(
    tree: ast.Module, held: dict[str, str], skipped: frozenset[str] = frozenset()
) -> set[str]:
    """Return every ``held`` name a ``_joined_import_prefixes`` literal and a text value in ``tree`` spell together.

    A prefix outside ``SRC_DIRNAME`` is dropped, and a join that spells no
    ``held`` name is dropped with it.
    """
    prefixes = {
        found for found in _joined_import_prefixes(tree, skipped) if _in_src(found)
    }
    if not prefixes:
        return set()
    pieces = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    return {
        prefix + piece
        for prefix in prefixes
        for piece in pieces
        if prefix + piece in held
    }


class _Skipped(NamedTuple):
    """The edges ``_walk`` skips.

    ``builders`` in every module, ``loaders`` in ``SCREEN_REGISTRY`` and ``pages``
    from the ``RETIRED_PAGE_TABLE`` module.
    """

    builders: frozenset[str] = frozenset()
    loaders: frozenset[str] = frozenset()
    pages: frozenset[str] = frozenset()


def _tree_reader(held: dict[str, str]) -> Callable[[str], ast.Module]:
    """Return a function that parses each ``held`` module once and answers its tree."""
    trees: dict[str, ast.Module] = {}

    def tree_of(name: str) -> ast.Module:
        if name not in trees:
            trees[name] = _parsed(held[name])
        return trees[name]

    return tree_of


def _declaration(
    held: dict[str, str],
    tree_of: Callable[[str], ast.Module],
    home: tuple[str, str],
    kind: type[_Declared],
) -> _Declared:
    """Return the module-level value ``home`` names in its module.

    Raises ``LookupError`` when that value is absent or is not a ``kind``.
    """
    module, name = home
    found: ast.expr | None = None
    for node in tree_of(module).body if module in held else []:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            found = node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
        ):
            found = node.value
    if not isinstance(found, kind):
        missing = f"the build reads {name} from {module} and found no such declaration"
        raise LookupError(missing)
    return found


def _retired_pages(
    held: dict[str, str], tree_of: Callable[[str], ast.Module]
) -> frozenset[str]:
    """Return each ``held`` name the ``RETIRED_PAGE_TABLE`` module joins onto.

    Each one is a ``DYNAMIC_IMPORT_CALL`` prefix joined to a value of that table.
    """
    table = _declaration(held, tree_of, RETIRED_PAGE_TABLE, ast.Dict)
    pieces = {_spelled(value) for value in table.values}
    prefixes = _joined_import_prefixes(tree_of(RETIRED_PAGE_TABLE[0]))
    return frozenset(
        prefix + piece
        for prefix in prefixes
        for piece in pieces
        if piece is not None and _in_src(prefix) and prefix + piece in held
    )


def _unbuilt_guard(node: ast.If) -> str | None:
    """Return X when ``node`` is ``if X not in UNBUILT_TABS:``, else None."""
    test = node.test
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return None
    if not isinstance(test.ops[0], ast.NotIn) or not isinstance(test.left, ast.Name):
        return None
    if _spelled(test.comparators[0]) != UNBUILT_TAB_TUPLE[1]:
        return None
    return test.left.id


class _Index(NamedTuple):
    """What ``_indexed`` finds in one pass over the reached trees.

    ``spelled`` counts each ``_spelled`` text, ``guards`` holds each ``_unbuilt_guard``
    and ``asks`` holds each ``ASKING_CALLS`` call.
    """

    spelled: Counter[str]
    guards: list[ast.If]
    asks: list[ast.Call]


def _indexed(tree_of: Callable[[str], ast.Module], reached: frozenset[str]) -> _Index:
    """Return the ``_Index`` of every tree ``reached`` names."""
    index = _Index(Counter(), [], [])
    for name in reached:
        for node in ast.walk(tree_of(name)):
            text = _spelled(node)
            if text is not None:
                index.spelled[text] += 1
            if isinstance(node, ast.If) and _unbuilt_guard(node) is not None:
                index.guards.append(node)
            elif isinstance(node, ast.Call) and _called(node) in ASKING_CALLS:
                index.asks.append(node)
    return index


def _named_outside(index: _Index, kept: list[ast.AST]) -> set[str]:
    """Return every text ``index`` counts more often than the ``kept`` nodes spell it."""
    distinct = {id(node): node for node in kept}.values()
    held_back = Counter(
        text for node in distinct if (text := _spelled(node)) is not None
    )
    return {text for text, count in index.spelled.items() if count > held_back[text]}


def _unbuilt_builders(
    held: dict[str, str], tree_of: Callable[[str], ast.Module], index: _Index
) -> frozenset[str]:
    """Return each method an ``_unbuilt_guard`` body names on ``self``.

    A method ``_named_outside`` finds outside those bodies is not returned.
    """
    declared = _declaration(held, tree_of, UNBUILT_TAB_TUPLE, ast.Tuple)
    unbuilt = {elt.id for elt in declared.elts if isinstance(elt, ast.Name)}
    bodies = [
        deep
        for guard in index.guards
        if _unbuilt_guard(guard) in unbuilt
        for stmt in guard.body
        for deep in ast.walk(stmt)
    ]
    guarded = {
        node.attr
        for node in bodies
        if isinstance(node, ast.Attribute) and _spelled(node.value) == "self"
    }
    return frozenset(guarded - _named_outside(index, bodies))


def _unasked_loaders(
    held: dict[str, str], tree_of: Callable[[str], ast.Module], index: _Index
) -> frozenset[str]:
    """Return each ``SCREEN_REGISTRY`` loader whose screen no ``ASKING_CALLS`` call names.

    It returns none when an ask names no registered screen or an ``ASKING_CALLS``
    name is used but not called, and never a loader ``_named_outside`` finds.
    """
    if SCREEN_REGISTRY not in held:
        missing = f"the build reads screens from {SCREEN_REGISTRY}, which is absent"
        raise LookupError(missing)
    registry = tree_of(SCREEN_REGISTRY)
    loaders: dict[str, set[str]] = {}
    kept: list[ast.AST] = []
    for stmt in registry.body:
        call = stmt.value if isinstance(stmt, ast.Expr) else None
        if not isinstance(call, ast.Call) or _called(call) != REGISTER_CALL:
            continue
        named = [arg.id for arg in call.args if isinstance(arg, ast.Name)]
        if not named or len(named) != len(call.args):
            return frozenset()
        loaders.setdefault(named[0], set()).update(named[1:])
        kept.extend(call.args[1:])
    if set(ASKING_CALLS) & _named_outside(index, [call.func for call in index.asks]):
        return frozenset()
    passing = {
        id(deep)
        for node in registry.body
        if isinstance(node, ast.FunctionDef) and node.name in ASKING_CALLS
        for deep in ast.walk(node)
    }
    asked = {
        _spelled(call.args[0]) if call.args else None
        for call in index.asks
        if id(call) not in passing
    }
    if not asked <= set(loaders):
        return frozenset()
    unasked = {
        fn for screen, fns in loaders.items() if screen not in asked for fn in fns
    }
    return frozenset(unasked - _named_outside(index, kept))


def _walk(
    project_root: str,
    held: dict[str, str],
    tree_of: Callable[[str], ast.Module],
    skipped: _Skipped,
) -> frozenset[str]:
    """Return every ``held`` name ``ENTRY_SCRIPT`` reaches past ``skipped``.

    An import line and a ``_dynamic_src_names`` join each count as an edge.
    """
    entry = _parsed(os.path.join(project_root, ENTRY_SCRIPT))
    pending = list(_src_import_names(entry, "__main__", False, skipped.builders))
    pending.extend(_dynamic_src_names(entry, held, skipped.builders))
    seen: set[str] = set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        parts = name.split(".")
        pending.extend(".".join(parts[:depth]) for depth in range(1, len(parts)))
        path = held.get(name)
        if path is None:
            continue
        tree = tree_of(name)
        functions = skipped.builders
        if name == SCREEN_REGISTRY:
            functions = functions | skipped.loaders
        pending.extend(
            _src_import_names(tree, name, path.endswith("__init__.py"), functions)
        )
        joined = _dynamic_src_names(tree, held, functions)
        if name == RETIRED_PAGE_TABLE[0]:
            joined -= skipped.pages
        pending.extend(joined)
    return frozenset(seen & set(held))


def _readings(project_root: str) -> tuple[frozenset[str], frozenset[str]]:
    """Return what ``_walk`` reaches by every edge, then past the window's marks."""
    held = src_modules(project_root)
    tree_of = _tree_reader(held)
    every = _walk(project_root, held, tree_of, _Skipped())
    index = _indexed(tree_of, every)
    marks = _Skipped(
        builders=_unbuilt_builders(held, tree_of, index),
        loaders=_unasked_loaders(held, tree_of, index),
        pages=_retired_pages(held, tree_of),
    )
    return every, _walk(project_root, held, tree_of, marks)


def reachable_src_modules(project_root: str) -> frozenset[str]:
    """Return each ``src_modules`` name ``ENTRY_SCRIPT`` reaches through a built screen.

    ``_readings`` skips retired pages, unbuilt tabs' builders and unasked screens.
    """
    return _readings(project_root)[1]


def retired_src_modules(project_root: str) -> frozenset[str]:
    """Return each ``src_modules`` name only a screen the window never builds reaches.

    ``_readings`` answers it as every reached name less the ``_Skipped`` walk's names.
    """
    every, built = _readings(project_root)
    return every - built


def unreachable_src_modules(project_root: str) -> frozenset[str]:
    """Return every ``src_modules`` name ``reachable_src_modules`` does not hold."""
    return frozenset(src_modules(project_root)) - reachable_src_modules(project_root)


def unreachable_src_files(project_root: str) -> frozenset[str]:
    """Return the file path of each module ``unreachable_src_modules`` names."""
    held = src_modules(project_root)
    return frozenset(held[name] for name in unreachable_src_modules(project_root))


def report_unreachable(project_root: str) -> list[str]:
    """Print one line per ``unreachable_src_modules`` name and return the names printed.

    Both spec files call it before ``Analysis``; ``retired_src_modules`` names come last.
    """
    held = src_modules(project_root)
    every, built = _readings(project_root)
    unreached = sorted(set(held) - every)
    retired = sorted(every - built)
    print(f"  [spec] {len(unreached)} of {len(held)} src modules unreached, left out:")
    for name in unreached:
        print(f"  [spec]   {name}")
    print(
        f"  [spec] {len(retired)} of {len(held)} src modules reached only "
        "through a screen the window never builds, left out:"
    )
    for name in retired:
        print(f"  [spec]   {name}")
    return unreached + retired


def excludes_for(project_root: str) -> list[str]:
    """Return ``EXCLUDES`` plus every ``retired_src_modules`` name.

    Both spec files hand this list to ``Analysis`` as its excludes.
    """
    return [*EXCLUDES, *sorted(retired_src_modules(project_root))]


def reachable_only(module_names: list[str], project_root: str) -> list[str]:
    """Return ``module_names`` less every name ``unreachable_src_modules`` holds."""
    left_out = unreachable_src_modules(project_root)
    return [name for name in module_names if name not in left_out]


def files_outside_cache_dirs(
    src_path: str, dest_path: str, left_out: frozenset[str] = frozenset()
) -> list[tuple[str, str]]:
    """Return one (source, destination) pair per file under ``src_path``.

    PyInstaller expands a directory pair by walking it, and this returns the same
    files without any ``CACHE_DIRNAME`` folder, without any
    ``COMPILED_SUFFIXES`` file, and without any path ``left_out`` names.
    """
    pairs = []
    for here, children, names in os.walk(src_path):
        if CACHE_DIRNAME in children:
            children.remove(CACHE_DIRNAME)
        target = os.path.normpath(
            os.path.join(dest_path, os.path.relpath(here, src_path))
        )
        for name in names:
            if name.endswith(COMPILED_SUFFIXES):
                continue
            source = os.path.normpath(os.path.join(here, name))
            if source in left_out:
                continue
            if os.path.isfile(source):
                pairs.append((source, target))
    return pairs


def build_graceful_datas(project_root: str, variant: str) -> list[tuple[str, str]]:
    """Return the ``datas_candidates`` pairs for ``variant``, each directory expanded.

    ``files_outside_cache_dirs`` expands a directory source and drops every
    ``unreachable_src_files`` path, and ``build_graceful_datas`` prints and skips
    a source that is not on disk.
    """
    left_out = unreachable_src_files(project_root)
    result = []
    for src_path, dest_path in datas_candidates(project_root, variant):
        if not os.path.exists(src_path):
            print(f"  [spec] Skipping missing optional datas path: {src_path}")
        elif os.path.isdir(src_path):
            result.extend(files_outside_cache_dirs(src_path, dest_path, left_out))
        else:
            result.append((src_path, dest_path))
    return result


# A dropped name here fails the frozen application at run time, not the build.
COMMON_HIDDENIMPORTS: tuple[str, ...] = (
    "acervator_watchdog",
    "ccxt",
    "ccxt.async_support",
    "ccxt.async_support.binance",
    "ccxt.async_support.coinbase",
    "ccxt.async_support.kraken",
    "ccxt.async_support.kucoin",
    "ccxt.async_support.bybit",
    "ccxt.async_support.okx",
    "ccxt.async_support.gate",  # renamed from gateio in ccxt 4.x
    "ccxt.async_support.bitget",
    "ccxt.async_support.htx",  # renamed from huobi in ccxt 4.x
    "ccxt.async_support.mexc",
    "ccxt.async_support.bitfinex",
    "ccxt.async_support.gemini",
    "ccxt.async_support.poloniex",
    "ccxt.async_support.bitstamp",
    "ccxt.async_support.cryptocom",
    "cryptography",
    "cryptography.hazmat.primitives.ciphers.aead",
    "cryptography.hazmat.primitives.kdf.pbkdf2",
    "PySide6",
    "PySide6.QtWidgets",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWebEngineWidgets",
    "keyring",
    "keyring.backends",
    # No file in src/, tools/ or main.py imports pandas or ta; numpy is imported.
    "pandas",
    "numpy",
    "ta",
    "aiohttp",
    # `src/core/settings.py` imports tomli only in the tomllib ImportError arm.
    "tomli",
    "tomli_w",
    "psutil",
    # `src/gui/crypto_news_ticker.py` raises ImportError without defusedxml.
    # The frozen build keeps it inside the PYZ, not as an _internal folder.
    "defusedxml",
    "defusedxml.ElementTree",
)

# keyring chooses its backend at run time from what it can import.
KEYRING_BACKENDS: dict[str, str] = {
    "windows": "keyring.backends.Windows",
    "macos": "keyring.backends.macOS",
}


def hiddenimports_for(platform: str) -> list[str]:
    """``COMMON_HIDDENIMPORTS`` plus the ``KEYRING_BACKENDS`` entry for ``platform``.

    Raises ``ValueError`` on a platform ``KEYRING_BACKENDS`` does not name.
    """
    try:
        backend = KEYRING_BACKENDS[platform]
    except KeyError:
        raise ValueError(
            f"unknown spec platform {platform!r}; "
            f"expected one of {sorted(KEYRING_BACKENDS)}"
        ) from None
    return [*COMMON_HIDDENIMPORTS, backend]


# Passed to PyInstaller by both spec files. A name here must not appear in
# pyproject.toml `dependencies`, and every name here was read against the import
# set of the 498 modules under src/ plus main.py, by AST walk over both
# module-level and function-level imports. Control: a name that does not exist
# reads 0 importing files, PySide6 reads 74 and numpy 4.
#
#   tkinter, IPython, jupyter, notebook, pytest, sphinx, setuptools
#            0 importing files each.
#   matplotlib  src/design_system.py, at module load. Its only importer is
#            tools/build_product_manual.py, which no spec collects, so the
#            frozen application never reaches the import.
#   PIL      src/core/mini_display.py in `render`, which no module imports, and
#            seven functions of src/gui/main_tabs/splash_screen_painter.py that
#            only `compose_still` calls, which nothing calls. main.py reaches
#            `mark_ops` in that module, and `mark_ops` is Qt alone.
# `scipy` and `statsmodels` are deliberately NOT in the list. The Opposing Pairs
# table is a screen the operator opens, and its test is the only reading either
# package serves, so the bundle carries both: `CONSUMER_EXTRAS["build"]` installs
# the `cointegration` extra. Measured on the build host, neither
# `statsmodels.tsa.stattools` nor `statsmodels.tsa.vector_ar.vecm` imports with
# scipy refused, so excluding scipy alone would strip the test as surely as
# excluding statsmodels.
EXCLUDES: tuple[str, ...] = (
    "tkinter",
    "matplotlib",
    "PIL",
    "IPython",
    "jupyter",
    "notebook",
    "pytest",
    "sphinx",
    "setuptools",
)
