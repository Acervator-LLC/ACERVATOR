"""One row per Qt module, and the seven answers the conversion check reads.

``rows`` walks the tree for every module that imports PySide6, the rule the
issue's own table is built on, so a file joins or leaves by landing or being
converted. ``electron_report`` runs the shipped ``desktop/main.js`` under
Electron and reports what each panel drew; ``qt_build_report`` imports every
row under ``ACERVATOR_VARIANT=qt`` and constructs the widgets it defines.

Run as a script with an output path, this module is the Qt side of that
second report, one JSON line per row.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

WEB = REPO_ROOT / "src" / "gui" / "web"
RENDERER = REPO_ROOT / "desktop" / "renderer"
DESKTOP = REPO_ROOT / "desktop"
ELECTRON_EXE = DESKTOP / "node_modules" / "electron" / "dist" / "electron.exe"
ELECTRON_BIN = DESKTOP / "node_modules" / "electron" / "dist" / "electron"
PROBE_JS = pathlib.Path(__file__).resolve().parent / "electron_shell_probe.js"

VARIANT_ENV = "ACERVATOR_VARIANT"
QT_VARIANT = "qt"

_JS_METHOD = re.compile(r"(?:var|let|const)\s+METHOD\s*=\s*[\"']([^\"']+)[\"']")
_PAGE_SCRIPT = re.compile(r'src="([^"]+\.js)"')

MODULE = "module"
REACT = "react"
MANIFEST = "manifest"
BRIDGE = "bridge"
PANEL = "panel"
RENDERS = "renders"
QT_BUILDS = "qt"

STEPS = (MODULE, REACT, MANIFEST, BRIDGE, PANEL, RENDERS, QT_BUILDS)

#: How long the Electron probe waits, in milliseconds.
SETTLE_MS = 6000
PANEL_MS = 6000
DEADLINE_MS = 300000
PROBE_TIMEOUT_S = 420
QT_TIMEOUT_S = 900


def imports_pyside(text: str) -> bool:
    """Whether ``text`` imports PySide6. A mention alone answers False."""
    from tools import conversion_state

    return conversion_state.imports_pyside(text)


def rows() -> list:
    """Every module the conversion table has a row for, repo-relative.

    Walks ``src/gui`` and the repository root for a module importing PySide6.
    """
    found = []
    for path in sorted((REPO_ROOT / "src" / "gui").rglob("*.py")):
        if imports_pyside(path.read_text(encoding="utf-8", errors="replace")):
            found.append(path)
    for path in sorted(REPO_ROOT.glob("*.py")):
        if imports_pyside(path.read_text(encoding="utf-8", errors="replace")):
            found.append(path)
    return [path.relative_to(REPO_ROOT).as_posix() for path in found]


def panel_name(row: str) -> str:
    """The panel name a row is addressed by: its file name without ``.py``."""
    return pathlib.PurePosixPath(row).stem


def react_module(row: str) -> pathlib.Path | None:
    """The ``src/gui/web`` module named for ``row``, or ``None``."""
    candidate = WEB / (panel_name(row) + ".js")
    return candidate if candidate.is_file() else None


def loaded_module_list() -> list:
    """Every ``.js`` name the renderer runs, manifest entries then page tags.

    A name appears once per place that names it, so a module the page runs
    twice is counted twice.
    """
    from tools import sync_renderer_modules

    named = list(
        sync_renderer_modules.manifest_entries(
            (RENDERER / "module_manifest.js").read_text(encoding="utf-8")
        )
    )
    page = (RENDERER / "index.html").read_text(encoding="utf-8")
    for ref in _PAGE_SCRIPT.findall(page):
        if "vendor" not in ref:
            named.append(ref.rsplit("/", 1)[-1])
    return named


def loaded_module_names() -> set:
    """Every ``.js`` name in ``loaded_module_list``, each named once."""
    return set(loaded_module_list())


def declared_method(module: pathlib.Path) -> str:
    """The bridge method a React ``module`` declares, or the empty string."""
    found = _JS_METHOD.search(module.read_text(encoding="utf-8", errors="replace"))
    return found.group(1) if found else ""


def bridge_methods() -> set:
    """Every method name ``build_registry`` answers, read from the live table."""
    from src.core.desktop_bridge import build_registry

    return set(build_registry())


def electron_executable() -> pathlib.Path | None:
    """``ELECTRON_EXE`` or ``ELECTRON_BIN`` when npm has written one."""
    for candidate in (ELECTRON_EXE, ELECTRON_BIN):
        if candidate.is_file():
            return candidate
    return None


def probe_environment(out: pathlib.Path, home: pathlib.Path) -> dict:
    """The environment the Electron probe and its backend child run under.

    ``ELECTRON_RUN_AS_NODE`` makes the Electron binary run as plain Node and
    open no window, so it is dropped here.
    """
    env = dict(os.environ)
    env.pop("ELECTRON_RUN_AS_NODE", None)
    env["ACERVATOR_PROBE_OUT"] = str(out)
    env["ACERVATOR_PROBE_MAIN"] = str(DESKTOP / "main.js")
    env["ACERVATOR_PROBE_PYTHON"] = sys.executable
    env["ACERVATOR_PROBE_HOME"] = str(home)
    env["ACERVATOR_PROBE_SETTLE_MS"] = str(SETTLE_MS)
    env["ACERVATOR_PROBE_PANEL_MS"] = str(PANEL_MS)
    env["ACERVATOR_PROBE_DEADLINE_MS"] = str(DEADLINE_MS)
    env["ELECTRON_DISABLE_SECURITY_WARNINGS"] = "1"
    return env


def electron_report() -> dict:
    """Run the shipped shell under Electron and report what each panel drew.

    The answer carries ``panels`` keyed by panel name, ``registered``, and
    ``reason`` when the run produced nothing.
    """
    binary = electron_executable()
    if binary is None:
        return {"available": False, "reason": "no electron binary is installed"}
    work = pathlib.Path(tempfile.mkdtemp(prefix="acervator-shell-probe-"))
    out = work / "shell.json"
    home = work / "home"
    home.mkdir()
    completed = subprocess.run(  # noqa: S603
        [str(binary), str(PROBE_JS)],
        cwd=str(REPO_ROOT),
        env=probe_environment(out, home),
        capture_output=True,
        text=True,
        timeout=PROBE_TIMEOUT_S,
        check=False,
    )
    if not out.is_file():
        return {
            "available": False,
            "reason": "the probe wrote nothing: " + completed.stderr[-400:],
        }
    payload = json.loads(out.read_text(encoding="utf-8"))
    if not payload.get("ok"):
        return {"available": False, "reason": str(payload.get("reason"))}
    result = payload.get("result") or {}
    return {
        "available": True,
        "spawned": payload.get("spawned") or [],
        "registered": result.get("registered") or [],
        "names": result.get("names") or [],
        "missing": result.get("missing") or [],
        "bridge": result.get("bridge"),
        "panels": {one["panel"]: one for one in result.get("panels") or []},
    }


def qt_report_environment(home: pathlib.Path) -> dict:
    """The environment the Qt build probe runs under, its ``home`` redirected."""
    env = dict(os.environ)
    env[VARIANT_ENV] = QT_VARIANT
    env["ACERVATOR_TEST_HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["HOME"] = str(home)
    env["ACERVATOR_CRASH_LOG_ROOT"] = str(home / "crash")
    env["ACERVATOR_SIM_STATE_ROOT"] = str(home / "sim")
    env["QT_QPA_PLATFORM"] = "offscreen"
    return env


def qt_build_report() -> dict:
    """Import every row under the Qt variant and construct what it defines.

    Each row is written as its own JSON line as the probe reaches it, so a
    row that takes the process down leaves every earlier answer readable.
    """
    work = pathlib.Path(tempfile.mkdtemp(prefix="acervator-qt-probe-"))
    out = work / "qt.jsonl"
    home = work / "home"
    home.mkdir()
    completed = subprocess.run(  # noqa: S603
        [sys.executable, str(pathlib.Path(__file__).resolve()), str(out)],
        cwd=str(work),
        env=qt_report_environment(home),
        capture_output=True,
        text=True,
        timeout=QT_TIMEOUT_S,
        check=False,
    )
    answers = {}
    if out.is_file():
        for line in out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                one = json.loads(line)
                answers[one["row"]] = one
    return {
        "exit_code": completed.returncode,
        "stderr": completed.stderr[-600:],
        "answers": answers,
    }


def _dotted(row: str) -> str:
    """The import name of a ``row`` path."""
    return row[: -len(".py")].replace("/", ".")


def _zero_argument_widgets(module) -> list:
    """Every QWidget subclass ``module`` defines that takes no argument."""
    import inspect

    from PySide6.QtWidgets import QWidget

    found = []
    for name, value in vars(module).items():
        if not inspect.isclass(value) or value.__module__ != module.__name__:
            continue
        if not issubclass(value, QWidget):
            continue
        try:
            signature = inspect.signature(value)
        except (TypeError, ValueError):
            continue
        needed = [
            one
            for one in signature.parameters.values()
            if one.default is inspect.Parameter.empty
            and one.kind
            in (one.POSITIONAL_ONLY, one.POSITIONAL_OR_KEYWORD, one.KEYWORD_ONLY)
        ]
        if not needed:
            found.append((name, value))
    return found


def _probe_row(row: str) -> dict:
    """Import one ``row`` and construct the widgets it defines with no argument."""
    import importlib

    answer = {"row": row, "imported": False, "widgets": 0, "built": 0, "error": ""}
    try:
        module = importlib.import_module(_dotted(row))
    except BaseException as err:  # noqa: BLE001
        answer["error"] = type(err).__name__ + ": " + str(err)[:200]
        return answer
    answer["imported"] = True
    try:
        candidates = _zero_argument_widgets(module)
    except BaseException as err:  # noqa: BLE001
        answer["error"] = type(err).__name__ + ": " + str(err)[:200]
        return answer
    answer["widgets"] = len(candidates)
    for name, kind in candidates:
        try:
            widget = kind()
        except BaseException as err:  # noqa: BLE001
            answer["error"] = name + " -> " + type(err).__name__ + ": " + str(err)[:160]
            continue
        answer["built"] += 1
        widget.deleteLater()
    return answer


def _probe_main(destination: str) -> int:
    """Write one JSON line per row, flushed as each row is answered.

    Leaves through ``os._exit``, which skips the Qt teardown a nonzero exit
    code would otherwise be read from.
    """
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    with open(destination, "w", encoding="utf-8") as handle:
        for row in rows():
            handle.write(json.dumps(_probe_row(row)) + "\n")
            handle.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(_probe_main(sys.argv[1]))
