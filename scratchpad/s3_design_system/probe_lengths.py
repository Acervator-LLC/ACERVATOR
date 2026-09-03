"""Measures what Chromium computes for a bare design token number as a CSS length."""

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


PROBE = """
(function () {
  var host = document.createElement('div');
  document.body.appendChild(host);
  host.style.setProperty('--SPACE_M', WANTED.SPACE_M);
  host.style.setProperty('--RADIUS_MD', WANTED.RADIUS_MD);
  host.style.setProperty('--MOTION_MEDIUM', WANTED.MOTION_MEDIUM);
  host.style.setProperty('--TYPE_BODY', WANTED.TYPE_BODY);
  var kid = document.createElement('div');
  host.appendChild(kid);
  kid.style.padding = 'var(--SPACE_M)';
  kid.style.borderRadius = 'var(--RADIUS_MD)';
  kid.style.transitionDuration = 'var(--MOTION_MEDIUM)';
  kid.style.fontSize = 'var(--TYPE_BODY)';
  var seen = getComputedStyle(kid);
  var raw = {
    padding: seen.paddingTop,
    borderRadius: seen.borderTopLeftRadius,
    transitionDuration: seen.transitionDuration,
    fontSize: seen.fontSize
  };
  kid.style.padding = '';
  kid.style.borderRadius = '';
  kid.style.transitionDuration = '';
  kid.style.fontSize = '';
  host.style.setProperty('--SPACE_M', WANTED.SPACE_M + 'px');
  host.style.setProperty('--RADIUS_MD', WANTED.RADIUS_MD + 'px');
  host.style.setProperty('--MOTION_MEDIUM', WANTED.MOTION_MEDIUM + 'ms');
  host.style.setProperty('--TYPE_BODY', WANTED.TYPE_BODY + 'px');
  kid.style.padding = 'var(--SPACE_M)';
  kid.style.borderRadius = 'var(--RADIUS_MD)';
  kid.style.transitionDuration = 'var(--MOTION_MEDIUM)';
  kid.style.fontSize = 'var(--TYPE_BODY)';
  var seen2 = getComputedStyle(kid);
  var united = {
    padding: seen2.paddingTop,
    borderRadius: seen2.borderTopLeftRadius,
    transitionDuration: seen2.transitionDuration,
    fontSize: seen2.fontSize
  };
  host.remove();
  return JSON.stringify({ raw: raw, united: united });
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

    wanted = {
        n: str(dss.TOKENS[n])
        for n in ("SPACE_M", "RADIUS_MD", "MOTION_MEDIUM", "TYPE_BODY")
    }
    answer = run_js(view, "window.WANTED = " + json.dumps(wanted) + ";" + PROBE)
    found = json.loads(answer)
    print("\nsurface values:", wanted)
    print("\n-- the raw number, as design_tokens.js writes it --")
    for key, value in found["raw"].items():
        print(f"  {key:20s} -> {value!r}")
    print("\n-- the same number with its unit --")
    for key, value in found["united"].items():
        print(f"  {key:20s} -> {value!r}")

    view.deleteLater()
    app.processEvents()


if __name__ == "__main__":
    main()
