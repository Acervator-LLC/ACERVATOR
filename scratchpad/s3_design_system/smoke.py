"""Drives the design system module in QJSEngine beside design_tokens.js."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from PySide6.QtWidgets import QApplication

from src.gui.main_tabs import design_system_surface as dss

TOKENS_JS = REPO / "src" / "gui" / "web" / "design_tokens.js"
SYSTEM_JS = REPO / "src" / "gui" / "web" / "design_system.js"


def main() -> None:
    QApplication.instance() or QApplication(sys.argv)
    from PySide6.QtQml import QJSEngine

    engine = QJSEngine()
    engine.evaluate("var window = this;")
    for path in (TOKENS_JS, SYSTEM_JS):
        result = engine.evaluate(path.read_text(encoding="utf-8"), path.name)
        if result.isError():
            print("PARSE FAILED", path.name, result.toString())
            return
        print("parsed", path.name)

    payload = json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))
    engine.globalObject().setProperty("PAYLOAD", json.dumps(payload))
    engine.globalObject().setProperty("COLOUR", "TEXT_ON_LIGHT")

    def ask(expression: str):
        out = engine.evaluate("JSON.stringify(" + expression + ")")
        if out.isError():
            raise RuntimeError(expression + " -> " + out.toString())
        text = out.toString()
        return None if text == "undefined" else json.loads(text)

    engine.evaluate("acervatorSetTokens(JSON.parse(PAYLOAD));")
    counts = ask("acervatorSetDesignSystem(JSON.parse(PAYLOAD), COLOUR)")
    print("\ncounts:", counts)
    print("faults:", ask("acervatorDesignSystem.faults()"))
    print("\nconversions:")
    for row in ask("acervatorDesignSystem.conversions()"):
        print("  ", row)
    print("\nshadows:")
    for name in dss.SHADOW_NAMES:
        engine.globalObject().setProperty("N", name)
        print("  ", name, "->", ask("acervatorDesignSystem.declaration(N)"))
    print("\nsample declarations:")
    for name in (
        "SPACE_M",
        "RADIUS_MD",
        "MOTION_MEDIUM",
        "TYPE_BODY",
        "WEIGHT_BOLD",
        "LINE_HEIGHT_BODY",
        "FONT_FAMILY_UI",
        "SURFACE_0",
        "GLOW_PRIMARY",
        "SCRIM",
        "BG",
    ):
        engine.globalObject().setProperty("N", name)
        print(f"   {name:18s} {ask('acervatorDesignSystem.declaration(N)')}")
    print(
        "\norder equals the surface order:",
        ask("acervatorDesignSystem.declarationNames()") == list(dss.TOKEN_NAMES),
    )
    print("declared", counts["declared"], "of", len(dss.TOKEN_NAMES))
    print(
        "\ngroup order (shadows):", ask("acervatorDesignSystem.groupOrder('shadows')")
    )
    print("\nrefusals for a shared value 16px:")
    engine.globalObject().setProperty("W", "16px")
    print("  name:", ask("acervatorDesignSystem.tokenNameFor(W, 'length')"))
    print("  refusals:", ask("acervatorDesignSystem.refusals()"))
    print("\nalias agreement:")
    for alias in dss.ALIAS_NAMES:
        engine.globalObject().setProperty("N", alias)
        print("  ", alias, ask("acervatorDesignSystem.aliasAgrees(N)"))
    print("\nalpha scale:", ask("acervatorDesignSystem.alphaScale()"))


if __name__ == "__main__":
    main()
