"""Reports Qt-to-React conversion state from the wiring, not from file names.

Run from anywhere in the repo. A Qt module under `src/gui` is paired when the
running frontend can draw it, and that is a chain of declarations rather than a
name:

* a surface under `src/gui/main_tabs` publishes a bridge `METHOD`;
* `src/core/desktop_bridge.py` registers that surface in its handler table;
* a module under `src/gui/web` declares the same method string;
* `desktop/renderer/module_manifest.js` or the renderer page loads that module.

A Qt module that instead loads a renderer module itself, by naming the `.js`
file, is paired on that alone: the React code is already what it draws.

Nothing here compares a `.py` file name with a `.js` file name. A surface is
addressed by the namespace of its bridge method and by its own module name, and
a parity test that imports one surface and exactly one Qt module pins the two
together whatever they are called.

Three states come out, because they are three different kinds of work:

* `paired`      -- a renderer module serves it;
* `unpaired`    -- a Qt screen with no renderer module, the work that is left;
* `not a screen`-- Qt plumbing that can never become React: a package marker, a
  module that defines no class, or the desktop shell that hosts the renderer.

A module counts as Qt only when it really imports PySide6. Naming the word in a
docstring, a comment or a warning string does not make a module Qt.
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys
from dataclasses import dataclass, field

ROOT = pathlib.Path(__file__).resolve().parents[1]
QT_PACKAGE = "PySide6"
SURFACE_SUFFIX = "_surface"
CONTROLS = ("bot_swarm_list", "theme_engine", "design_tokens")

PAIRED = "paired"
UNPAIRED = "unpaired"
NOT_A_SCREEN = "not a screen"
BORN_REACT = "born React"

PACKAGE_MARKER = "package marker"
NO_CLASS = "defines no class"
DESKTOP_SHELL = "desktop shell, hosts the renderer"

SHELL_BASE = "QMainWindow"

_JS_METHOD = re.compile(r"(?:var|let|const)\s+METHOD\s*=\s*[\"']([^\"']+)[\"']")
_MANIFEST_ENTRY = re.compile(r"\"([^\"]+\.js)\"")
_PAGE_SCRIPT = re.compile(r"src=\"([^\"]+\.js)\"")


@dataclass(frozen=True)
class Wiring:
    """Every declaration the pairing reads, gathered once from one repo root."""

    root: pathlib.Path
    served: dict[str, str] = field(default_factory=dict)
    addresses: dict[str, set[str]] = field(default_factory=dict)
    pins: dict[str, set[str]] = field(default_factory=dict)
    renderer_modules: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class Verdict:
    """One Qt module, the state it is in, and the evidence that put it there."""

    path: pathlib.Path
    state: str
    evidence: str
    lines: int


def imports_pyside(text: str) -> bool:
    """True when a module really imports PySide6, false when it only names it.

    The scan pairs a Qt module with its renderer module, so a module that
    carries the word inside a string or a comment must not count as Qt. A module
    that names the word but cannot be parsed stays counted, so a file the tool
    cannot read is reported rather than dropped from the total.
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


def _read(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _parse(path: pathlib.Path) -> ast.Module | None:
    try:
        return ast.parse(_read(path))
    except SyntaxError:
        return None


def _string_constant(tree: ast.Module, name: str) -> str:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                if isinstance(node.value, ast.Constant) and isinstance(
                    node.value.value, str
                ):
                    return node.value.value
    return ""


def surface_methods(root: pathlib.Path) -> dict[str, str]:
    """The bridge method each surface module publishes, keyed by module name.

    The whole of `src` is read, not one folder: the bridge imports surfaces
    from wherever the domain that owns them lives.
    """
    found: dict[str, str] = {}
    for path in sorted((root / "src").rglob("*" + SURFACE_SUFFIX + ".py")):
        tree = _parse(path)
        if tree is None:
            continue
        method = _string_constant(tree, "METHOD")
        if method:
            found[path.stem] = method
    return found


def registered_surfaces(root: pathlib.Path) -> set[str]:
    """The surface modules the bridge's handler table names."""
    tree = _parse(root / "src" / "core" / "desktop_bridge.py")
    if tree is None:
        return set()
    named: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "METHOD":
            if isinstance(node.value, ast.Name):
                named.add(node.value.id)
    return named


def renderer_modules(root: pathlib.Path) -> set[str]:
    """The `.js` file names the renderer loads, from the manifest and the page."""
    renderer = root / "desktop" / "renderer"
    names = set(_MANIFEST_ENTRY.findall(_read(renderer / "module_manifest.js")))
    for ref in _PAGE_SCRIPT.findall(_read(renderer / "index.html")):
        if "vendor" not in ref:
            names.add(ref.rsplit("/", 1)[-1])
    return names


def served_methods(root: pathlib.Path) -> dict[str, str]:
    """Bridge method to the renderer module that speaks it, loaded ones only.

    A module that declares a method the bridge does not register is left out:
    the frontend can name anything, and only the registry makes a method real.
    """
    loaded = renderer_modules(root)
    methods = surface_methods(root)
    registered = {
        methods[name] for name in registered_surfaces(root) if name in methods
    }
    served: dict[str, str] = {}
    for path in sorted((root / "src" / "gui" / "web").glob("*.js")):
        if path.name not in loaded:
            continue
        found = _JS_METHOD.search(_read(path))
        if found and found.group(1) in registered:
            served.setdefault(found.group(1), path.name)
    return served


def qt_modules(root: pathlib.Path) -> list[pathlib.Path]:
    """Every module under `src/gui` that imports Qt, sorted by path."""
    gui = root / "src" / "gui"
    return [path for path in sorted(gui.rglob("*.py")) if imports_pyside(_read(path))]


def dotted_name(root: pathlib.Path, path: pathlib.Path) -> str:
    """The import path of a module under `src`, as `src.gui.live_settings.x`."""
    return "src." + ".".join(path.relative_to(root / "src").with_suffix("").parts)


def path_words(root: pathlib.Path, path: pathlib.Path) -> set[str]:
    """Every word in the location of a Qt module under `src/gui`.

    A surface names the screen, never the file, so the two spellings differ in
    the folder and in the order: `live_settings/status_tab.py` is addressed as
    `live_status_tab`, and `visualizer/themes.py` as `visualizer_themes`. The
    words are what both spellings share.
    """
    parts = list(path.relative_to(root / "src" / "gui").with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return {word for part in parts for word in part.split("_") if word}


def address_words(name: str) -> set[str]:
    """The words of one bridge address, as a set to compare with a location."""
    return {word for word in name.split("_") if word}


def parity_pins(root: pathlib.Path) -> dict[str, set[str]]:
    """Surface module to the Qt modules a parity test pins it against.

    A parity test drives one surface and the Qt code it replaces side by side,
    so its imports declare the pairing outright. Only a test that imports one
    surface and one Qt module counts: a second of either is a neighbour brought
    in as a control, and guessing between them pairs a surface with a screen it
    never described.
    """
    qt_by_name = {dotted_name(root, path) for path in qt_modules(root)}
    surfaces = surface_methods(root)
    pins: dict[str, set[str]] = {}
    for path in sorted((root / "tests").glob("test_*_surface_parity.py")):
        tree = _parse(path)
        if tree is None:
            continue
        imported = _imported_names(tree)
        seen_qt = {name for name in imported if name in qt_by_name}
        seen_surfaces = {
            name.rsplit(".", 1)[-1]
            for name in imported
            if name.rsplit(".", 1)[-1] in surfaces
        }
        if len(seen_qt) != 1 or len(seen_surfaces) != 1:
            continue
        pins.setdefault(seen_surfaces.pop(), set()).update(seen_qt)
    return pins


def _imported_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module)
            names.update(node.module + "." + alias.name for alias in node.names)
    return names


def hosted_module(text: str, loaded: set[str]) -> str:
    """The renderer module a Qt module loads itself, or the empty string.

    A Qt widget that builds the page for a web view names the `.js` files that
    page pulls in. Naming a loaded one is the strongest pairing there is: the
    React code is already what the widget draws.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return ""
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            name = node.value.rsplit("/", 1)[-1]
            if name in loaded:
                return name
    return ""


def read_wiring(root: pathlib.Path) -> Wiring:
    """Gather every declaration the pairing reads from one repo root."""
    methods = surface_methods(root)
    served = served_methods(root)
    pins = parity_pins(root)
    spoken: dict[str, set[str]] = {}
    for surface, method in methods.items():
        if method not in served:
            continue
        for name in (method.split(".")[0], surface[: -len(SURFACE_SUFFIX)]):
            spoken.setdefault(method, set()).update(address_words(name))
    return Wiring(
        root=root,
        served=served,
        addresses=spoken,
        pins={
            methods[surface]: targets
            for surface, targets in pins.items()
            if surface in methods and methods[surface] in served
        },
        renderer_modules=renderer_modules(root),
    )


def serving_method(wiring: Wiring, path: pathlib.Path) -> str:
    """The live bridge method that addresses one Qt module, or the empty string.

    Several addresses can sit inside one location: a panel under
    `simulator_tab/` carries the words of the tab around it as well as its own.
    The closest address wins, measured on the module's own name first, so a
    panel is served by its own method and not by the one for its container.
    """
    words = path_words(wiring.root, path)
    own = address_words(path.stem)
    ranked = [
        (len(spoken & own), len(spoken), method)
        for method, spoken in wiring.addresses.items()
        if spoken and spoken <= words
    ]
    if ranked:
        return max(ranked)[2]
    dotted = dotted_name(wiring.root, path)
    for method, targets in sorted(wiring.pins.items()):
        if dotted in targets:
            return method
    return ""


def plumbing_reason(path: pathlib.Path, text: str) -> str:
    """Why a Qt module can never become React, or the empty string.

    Three shapes carry no screen. A package marker is a directory, not a view.
    A module that defines no class builds nothing to draw. A window deriving
    from the shell base is the desktop window the renderer's web view lives
    inside, so replacing it with React would leave the React nowhere to run.
    """
    if path.name == "__init__.py":
        return PACKAGE_MARKER
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return ""
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    if not classes:
        return NO_CLASS
    for node in classes:
        for base in node.bases:
            named = base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
            if named == SHELL_BASE:
                return DESKTOP_SHELL
    return ""


def survey(root: pathlib.Path) -> list[Verdict]:
    """Classify every Qt module under `src/gui`, one verdict each."""
    return classify(read_wiring(root))


def classify(wiring: Wiring) -> list[Verdict]:
    """Classify every Qt module against wiring already read."""
    root = wiring.root
    verdicts: list[Verdict] = []
    for path in qt_modules(root):
        text = _read(path)
        lines = len(text.splitlines())
        hosted = hosted_module(text, wiring.renderer_modules)
        if hosted:
            verdicts.append(Verdict(path, PAIRED, "loads " + hosted, lines))
            continue
        method = serving_method(wiring, path)
        if method:
            served_by = wiring.served[method]
            verdicts.append(
                Verdict(path, PAIRED, served_by + " speaks " + method, lines)
            )
            continue
        reason = plumbing_reason(path, text)
        if reason:
            verdicts.append(Verdict(path, NOT_A_SCREEN, reason, lines))
            continue
        verdicts.append(Verdict(path, UNPAIRED, "no renderer module", lines))
    return verdicts


def control_state(verdicts: list[Verdict], probe: str) -> str:
    """The state one probe name is in, or `born React` when it is not Qt."""
    for verdict in verdicts:
        if verdict.path.stem == probe:
            return verdict.state
    return BORN_REACT


def _rows(verdicts: list[Verdict], state: str) -> list[Verdict]:
    chosen = [verdict for verdict in verdicts if verdict.state == state]
    return sorted(chosen, key=lambda verdict: -verdict.lines)


def main() -> int:
    """Print the three states, what is left, and the built-in controls."""
    wiring = read_wiring(ROOT)
    verdicts = classify(wiring)
    paired = _rows(verdicts, PAIRED)
    unpaired = _rows(verdicts, UNPAIRED)
    plumbing = _rows(verdicts, NOT_A_SCREEN)

    print("renderer modules the page loads : " + str(len(wiring.renderer_modules)))
    print("bridge methods a module speaks  : " + str(len(wiring.served)))
    print("src/gui .py importing PySide6   : " + str(len(verdicts)))
    print("  paired, a React module serves it : " + str(len(paired)))
    print("  not a screen, Qt plumbing        : " + str(len(plumbing)))
    print("  UNPAIRED, the work that is left  : " + str(len(unpaired)))
    print()
    print("UNPAIRED, largest first:")
    for verdict in unpaired:
        print(
            "  "
            + str(verdict.lines).rjust(5)
            + "   "
            + verdict.path.relative_to(ROOT).as_posix()
        )
    print()
    print("NOT A SCREEN, never convertible:")
    for verdict in plumbing:
        print(
            "  "
            + verdict.evidence.ljust(34)
            + verdict.path.relative_to(ROOT).as_posix()
        )
    print()
    print("CONTROL, a converted name must report 'paired':")
    for probe in CONTROLS:
        print("  " + probe.ljust(18) + control_state(verdicts, probe))
    return 0


if __name__ == "__main__":
    sys.exit(main())
