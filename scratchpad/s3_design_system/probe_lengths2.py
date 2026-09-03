"""Measures a bare token value beside a good declaration, calibrating the probe."""

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


PROBE = """
(function () {
  var out = {};
  function read(declaration, property, read_as) {
    var kid = document.createElement('div');
    kid.style.setProperty('--PROBE', declaration);
    document.body.appendChild(kid);
    kid.style.setProperty(property, 'var(--PROBE)');
    var seen = getComputedStyle(kid)[read_as];
    kid.remove();
    return seen;
  }
  out['padding literal 16px'] = read('16px', 'padding', 'paddingTop');
  out['padding bare 16'] = read('16', 'padding', 'paddingTop');
  out['radius literal 12px'] = read('12px', 'border-radius', 'borderTopLeftRadius');
  out['radius bare 12'] = read('12', 'border-radius', 'borderTopLeftRadius');
  out['duration literal 250ms'] =
      read('250ms', 'transition-duration', 'transitionDuration');
  out['duration bare 250'] =
      read('250', 'transition-duration', 'transitionDuration');
  out['font literal 13px'] = read('13px', 'font-size', 'fontSize');
  out['font bare 13'] = read('13', 'font-size', 'fontSize');
  out['colour literal'] = read('rgba(0,255,204,0.2)', 'color', 'color');
  out['colour alpha byte'] = read('rgba(0,255,204,51)', 'color', 'color');
  return JSON.stringify(out);
})()
"""


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

    found = json.loads(run_js(view, PROBE))
    for key, value in found.items():
        print(f"  {key:28s} -> {value!r}")

    view.deleteLater()
    app.processEvents()


if __name__ == "__main__":
    main()
