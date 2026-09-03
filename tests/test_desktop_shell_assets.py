"""Every JavaScript file the application ships parses, and the page asks
for assets that exist.

Node is not installed on this machine, so nothing here starts Electron.
What it does instead is parse the JavaScript with the engine PySide6
already ships and resolve every asset path the page names, which catches
a syntax error and a missing file without a Node toolchain.

The subjects are discovered, never written down. ``shipped_javascript``
walks ``src/gui/web`` for the React modules and adds the three shell
scripts, so a module a later unit adds is parsed with no edit here. A
hand-written list of three files is what left all 39 React modules
unparsed by anything.

Two broken sources make the parse result evidence. One is a bare
statement, which shows the engine reports an error at all. The other
sits inside ``(function (global) { ... })(window)`` -- the shape every
React module has -- which shows the engine still reports an error at the
depth the modules' real code occupies, rather than skipping nested
function bodies.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tools import sync_renderer_modules as renderer_modules

REPO_ROOT = Path(__file__).resolve().parents[1]
DESKTOP = REPO_ROOT / "desktop"
RENDERER = DESKTOP / "renderer"
INDEX_HTML = RENDERER / "index.html"
WEB_MODULES = REPO_ROOT / "src" / "gui" / "web"
MANIFEST_JS = RENDERER / "module_manifest.js"
WEB_PREFIX = "../../src/gui/web/"

SHELL_SCRIPTS = (
    DESKTOP / "main.js",
    DESKTOP / "preload.js",
    RENDERER / "boot.js",
    RENDERER / "module_errors.js",
    RENDERER / "module_manifest.js",
    RENDERER / "module_loader.js",
)


def web_modules() -> tuple:
    """Every React module under ``src/gui/web``, third-party ``vendor`` left out.

    ``vendor`` holds React itself, which this repository does not author
    and has no standing to judge.
    """
    return tuple(
        path for path in sorted(WEB_MODULES.rglob("*.js")) if "vendor" not in path.parts
    )


def shipped_javascript() -> tuple:
    """Every JavaScript file the application ships, discovered from disk."""
    return SHELL_SCRIPTS + web_modules()


SHIPPED_JS = shipped_javascript()

WRAPPER_HEAD = "(function(require, module, exports, process, window, document){"
WRAPPER_TAIL = "})"

BROKEN_SOURCE = "var = ;"
BROKEN_MODULE_SOURCE = "(function (global) { var = ; })(window);"


@pytest.fixture()
def js_engine(qapp):
    """A JavaScript engine, or a skip when Qt's QML module is absent.

    Depends on pytest-qt's ``qapp`` so that the application object the
    suite tears down is the ``QApplication`` it expects.
    """
    qtqml = pytest.importorskip("PySide6.QtQml")
    assert qapp is not None
    return qtqml.QJSEngine()


def parse_error(engine, source: str, label: str):
    """Return the engine's error for ``source``, or None when it parses.

    The source is wrapped in a function expression so that the body is
    parsed but never run: the shell's scripts call into Electron, which
    is not present here.
    """
    result = engine.evaluate(WRAPPER_HEAD + source + WRAPPER_TAIL, label)
    return result.toString() if result.isError() else None


def test_the_parser_rejects_broken_javascript(js_engine):
    """The control for the test below. Without this, a parser that
    accepted everything would report every shell script as valid."""
    assert parse_error(js_engine, BROKEN_SOURCE, "control") is not None


def test_the_parser_rejects_a_syntax_error_inside_a_module_body(js_engine):
    """A parser that skipped nested function bodies would pass every
    React module without reading a line of it, because each module keeps
    all of its code inside ``(function (global) { ... })(window)``."""
    error = parse_error(js_engine, BROKEN_MODULE_SOURCE, "module-control")
    assert error is not None, (
        "a syntax error inside a module-shaped function was not reported, "
        "so the parse result below says nothing about module bodies"
    )


@pytest.mark.parametrize("path", SHIPPED_JS, ids=lambda p: p.name)
def test_every_shipped_script_parses(path, js_engine):
    error = parse_error(js_engine, path.read_text(encoding="utf-8"), path.name)
    assert error is None, path.name + ": " + str(error)


def modules_the_page_loads() -> set:
    """The ``src/gui/web`` module names the page's script tags name."""
    return {
        resolved.name
        for _, resolved in referenced_assets()
        if resolved.suffix == ".js" and resolved.parent == WEB_MODULES
    }


def test_the_parse_check_covers_every_module_the_page_loads():
    """``index.html`` is written by hand and is not the source this
    discovery walks, so it answers whether the walk actually reached the
    modules rather than agreeing with itself."""
    covered = {path.name for path in SHIPPED_JS}
    missing = sorted(modules_the_page_loads() - covered)
    assert not missing, (
        str(len(missing))
        + " modules the page loads are never parsed: "
        + ", ".join(missing)
    )


def test_no_module_on_disk_goes_unloaded_by_tag_or_manifest():
    """Every module in `src/gui/web` is named by a script tag or by
    `module_manifest.js`."""
    reached = modules_the_page_loads() | set(manifest_names())
    unloaded = sorted({p.name for p in web_modules()} - reached)
    assert not unloaded, (
        str(len(unloaded))
        + " modules ship but neither a script tag nor the manifest names "
        "them: " + ", ".join(unloaded)
    )


def referenced_assets() -> list:
    """Every ``src`` and ``href`` the page names, as paths on disk."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    found = re.findall(r'(?:src|href)="([^"]+)"', html)
    return [(ref, (RENDERER / ref).resolve()) for ref in found]


def test_the_page_names_at_least_the_four_assets_it_needs():
    refs = [ref for ref, _ in referenced_assets()]
    assert any(r.endswith("history_panel.css") for r in refs)
    assert any(r.endswith("react.production.min.js") for r in refs)
    assert any(r.endswith("react-dom.production.min.js") for r in refs)
    assert any(r.endswith("history_panel.js") for r in refs)
    assert any(r.endswith("boot.js") for r in refs)


def test_every_asset_the_page_names_exists_on_disk():
    for ref, resolved in referenced_assets():
        assert resolved.is_file(), ref + " resolves to nothing at " + str(resolved)


def test_the_page_reuses_the_existing_panel_rather_than_a_copy():
    """The renderer loads the panel that already ships with the Qt build.
    A second copy under ``desktop`` would be a fork of the surface."""
    for ref, resolved in referenced_assets():
        if resolved.name in ("history_panel.js", "history_panel.css"):
            assert resolved == (REPO_ROOT / "src" / "gui" / "web" / resolved.name)


def test_the_page_forbids_every_network_connection():
    """The backend is a child process on a pipe. The page has no reason
    to open a socket, and its policy says so."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    policy = re.search(
        r'http-equiv="Content-Security-Policy"[^>]*content="([^"]+)"', html
    )
    assert policy, "index.html declares no Content-Security-Policy"
    assert "connect-src 'none'" in policy.group(1)


def test_the_package_entry_point_exists():
    manifest = json.loads((DESKTOP / "package.json").read_text(encoding="utf-8"))
    assert (DESKTOP / manifest["main"]).is_file()
    assert "electron" in manifest["devDependencies"]


@pytest.mark.parametrize("path", SHIPPED_JS, ids=lambda p: p.name)
def test_no_shipped_script_declares_an_http_listener(path):
    """The reverted loopback server is not coming back, through the shell
    or through a React module. The backend is a child process on a pipe,
    so no shipped file may open a port or speak HTTP."""
    source = path.read_text(encoding="utf-8")
    for banned in ("http.createServer", 'require("http")', "listen(", "fetch("):
        assert banned not in source, path.name + " contains " + banned


def manifest_names() -> list:
    """The module file names ``module_manifest.js`` declares, in order."""
    return renderer_modules.manifest_entries(MANIFEST_JS.read_text(encoding="utf-8"))


def not_loaded(names: list) -> list:
    """Every module in ``src/gui/web`` that the given list leaves out."""
    return sorted(set(renderer_modules.modules_on_disk()) - set(names))


def twice(names: list) -> list:
    """Every name the given list carries more than once."""
    return sorted({name for name in names if names.count(name) > 1})


def page_script_srcs() -> list:
    """Every ``src`` the page names, in document order."""
    return re.findall(r'src="([^"]+)"', INDEX_HTML.read_text(encoding="utf-8"))


def errors_first_and_loader_last(refs: list) -> bool:
    """True when the fault record precedes, and the loader follows, every
    ``src/gui/web`` module the given list names."""
    web = [at for at, ref in enumerate(refs) if ref.startswith(WEB_PREFIX)]
    if not web or "module_errors.js" not in refs or "module_loader.js" not in refs:
        return False
    return refs.index("module_errors.js") < min(web) and max(web) < refs.index(
        "module_loader.js"
    )


def test_the_manifest_parser_reports_the_names_it_is_given():
    """The control for the checks below: a parser answering nothing would
    report every manifest as agreeing with any directory."""
    text = 'window.ACERVATOR_MODULES = [\n  "a.js",\n  "b.js",\n];\n'
    assert renderer_modules.manifest_entries(text) == ["a.js", "b.js"]
    assert renderer_modules.manifest_entries("window.ACERVATOR_MODULES = [];") == []


def test_the_page_loads_every_web_module_on_disk():
    absent = not_loaded(manifest_names())
    assert not absent, (
        "run python -m tools.sync_renderer_modules; the page loads none of "
        + ", ".join(absent)
    )


def test_a_module_the_manifest_leaves_out_is_named():
    """The control for the check above, run against a manifest one short."""
    short = [name for name in manifest_names() if name != "design_tokens.js"]
    assert not_loaded(short) == ["design_tokens.js"]


def test_the_manifest_names_nothing_that_is_not_on_disk():
    on_disk = set(renderer_modules.modules_on_disk())
    strays = sorted(set(manifest_names()) - on_disk)
    assert not strays, "the manifest names " + ", ".join(strays)


def test_the_manifest_names_no_module_twice():
    """A union merge of two branches that both add the same module would
    leave the name twice, and the page would run that module twice."""
    assert not twice(manifest_names()), twice(manifest_names())


def test_the_repeated_name_check_can_report():
    """The control for the check above."""
    assert twice(["a.js", "b.js", "a.js"]) == ["a.js"]
    assert twice(["a.js", "b.js"]) == []


def test_the_page_records_a_fault_for_every_module_it_names():
    assert errors_first_and_loader_last(page_script_srcs()), page_script_srcs()[:3]


def test_the_load_order_check_can_report():
    """The control for the check above, run against both orders."""
    module = WEB_PREFIX + "design_tokens.js"
    assert not errors_first_and_loader_last(["module_loader.js", module, "x.js"])
    assert not errors_first_and_loader_last(["module_errors.js", module])
    assert errors_first_and_loader_last(
        ["module_errors.js", module, "module_loader.js"]
    )
