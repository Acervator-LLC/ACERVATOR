"""The desktop shell's own files: its JavaScript parses, and the page
asks for assets that exist.

Node is not installed on this machine, so nothing here starts Electron.
What it does instead is parse the shell's JavaScript with the engine
PySide6 already ships and resolve every asset path the page names, which
catches a syntax error and a missing file without a Node toolchain. The
broken control below is what makes the parse result evidence: an engine
that accepted anything would report the same pass on every file.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DESKTOP = REPO_ROOT / "desktop"
RENDERER = DESKTOP / "renderer"
INDEX_HTML = RENDERER / "index.html"

SHELL_SCRIPTS = (
    DESKTOP / "main.js",
    DESKTOP / "preload.js",
    RENDERER / "boot.js",
)

WRAPPER_HEAD = "(function(require, module, exports, process, window, document){"
WRAPPER_TAIL = "})"

BROKEN_SOURCE = "var = ;"


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


@pytest.mark.parametrize("path", SHELL_SCRIPTS, ids=lambda p: p.name)
def test_every_shell_script_parses(path, js_engine):
    error = parse_error(js_engine, path.read_text(encoding="utf-8"), path.name)
    assert error is None, path.name + ": " + str(error)


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


def test_the_shell_declares_no_http_listener():
    """The reverted loopback server is not coming back through the shell.
    Nothing here may open a port or speak HTTP."""
    for path in SHELL_SCRIPTS:
        source = path.read_text(encoding="utf-8")
        for banned in ("http.createServer", 'require("http")', "listen(", "fetch("):
            assert banned not in source, path.name + " contains " + banned
