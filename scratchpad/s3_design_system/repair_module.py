"""Cuts the written lines off the end of the shipped design system module."""

from __future__ import annotations

import hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TARGET = REPO / "src" / "gui" / "web" / "design_system.js"

WRITTEN = '\nvar written = /ab+c/;\n\nvar written = "#00ffcc";\n'
END = "})(window);\n"


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    print("before:", hashlib.sha256(text.encode("utf-8")).hexdigest())
    if not text.endswith(WRITTEN):
        print("tail does not match the written lines; nothing changed")
        print(repr(text[-120:]))
        return
    fixed = text[: -len(WRITTEN)]
    if not fixed.endswith(END):
        print("cut would not end the module correctly; nothing changed")
        return
    TARGET.write_text(fixed, encoding="utf-8", newline="")
    landed = TARGET.read_bytes()
    print("after :", hashlib.sha256(landed).hexdigest())
    print("CRLF", landed.count(b"\r\n"), "LF", landed.count(b"\n"))
    print("last line:", repr(landed.decode("utf-8").splitlines()[-1]))


if __name__ == "__main__":
    main()
