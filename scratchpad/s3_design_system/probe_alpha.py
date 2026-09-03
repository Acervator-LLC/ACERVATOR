"""Measures what Chromium paints for each rgba tint the design surface declares."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

INDEX_HTML = REPO / "desktop" / "renderer" / "index.html"
TIMEOUT_MS = 30000

from PySide6.QtCore import QEventLoop, QTimer, QUrl
from PySide6.QtWidgets import QApplication

from src.gui.main_tabs import design_system_surface as dss


def run_js(view: Any, script: str) -> Any:
    loop = QEventLoop()
    box: dict = {}

    def answered(value: Any) -> None:
        box.setdefault("v", value)
        loop.quit()

    view.page().runJavaScript(script, answered)
    QTimer.singleShot(TIMEOUT_MS, loop.quit)
    loop.exec()
    return box.get("v")


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    from PySide6.QtWebEngineWidgets import QWebEngineView

    view = QWebEngineView()
    loop = QEventLoop()
    box: dict = {}

    def finished(ok: bool) -> None:
        box.setdefault("ok", ok)
        loop.quit()

    view.loadFinished.connect(finished)
    view.load(QUrl.fromLocalFile(str(INDEX_HTML)))
    QTimer.singleShot(TIMEOUT_MS, loop.quit)
    loop.exec()
    print("page loaded:", box.get("ok"))

    tints = {
        name: dss.TOKENS[name]
        for name in (
            "GLOW_PRIMARY",
            "GLOW_SECONDARY",
            "SCRIM",
            "GLOW_PRIMARY_EDGE",
            "GLOW_PRIMARY_FAINT",
        )
    }
    script = (
        "(function () {"
        "  var probe = document.createElement('div');"
        "  document.body.appendChild(probe);"
        "  var wanted = " + json.dumps(tints) + ";"
        "  var out = {};"
        "  Object.keys(wanted).forEach(function (n) {"
        "    probe.style.color = '';"
        "    probe.style.color = wanted[n];"
        "    out[n] = [wanted[n], getComputedStyle(probe).color];"
        "  });"
        "  probe.remove();"
        "  return JSON.stringify(out); })()"
    )
    answer = run_js(view, script)
    print("\n-- what Chromium paints for each rgba tint --")
    for name, pair in json.loads(answer).items():
        print(f"  {name:22s} declared {pair[0]:22s} -> painted {pair[1]}")

    shadow_script = (
        "(function () {"
        "  var probe = document.createElement('div');"
        "  document.body.appendChild(probe);"
        "  var out = {};"
        "  ['0px 2px 4px rgba(0,0,0,64)', '0px 2px 4px rgba(0,0,0,0.251)']"
        "    .forEach(function (d, i) {"
        "      probe.style.boxShadow = '';"
        "      probe.style.boxShadow = d;"
        "      out[i] = [d, getComputedStyle(probe).boxShadow];"
        "    });"
        "  probe.remove();"
        "  return JSON.stringify(out); })()"
    )
    print("\n-- box-shadow with an alpha byte against a CSS alpha --")
    for _, pair in json.loads(run_js(view, shadow_script)).items():
        print(f"  declared {pair[0]:36s} -> {pair[1]}")

    view.deleteLater()
    app.processEvents()


if __name__ == "__main__":
    main()
