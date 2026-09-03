"""Sweeps every colour the design system declares, in Python and in CSS text."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

HEX = re.compile(r"#[0-9a-fA-F]+")
RGBA = re.compile(r"rgba?\(([^)]*)\)")

TARGETS = [
    REPO / "src" / "gui" / "main_tabs" / "design_system_surface.py",
    REPO / "src" / "gui" / "design_system.py",
]


def qt_reading(digits: str) -> str:
    """What Qt paints for a hex body, by Qt's #AARRGGBB rule."""
    n = len(digits)
    if n == 3:
        return "rgb " + "".join(c * 2 for c in digits) + " opaque"
    if n == 6:
        return "rgb " + digits.lower() + " opaque"
    if n == 8:
        a, r, g, b = digits[0:2], digits[2:4], digits[4:6], digits[6:8]
        return f"rgb {r}{g}{b} alpha 0x{a} -> HUE {r}{g}{b}".lower()
    if n == 9:
        return "rgb (9-digit, Qt #AAARRRGGGBBB form)"
    return f"INVALID ({n} digits) -> Qt drops the declaration"


def css_reading(digits: str) -> str:
    """What a browser paints for a hex body, by the CSS #RRGGBBAA rule."""
    n = len(digits)
    if n == 3:
        return "rgb " + "".join(c * 2 for c in digits) + " opaque"
    if n == 4:
        body = "".join(c * 2 for c in digits)
        return f"rgb {body[:6]} alpha 0x{body[6:]}"
    if n == 6:
        return "rgb " + digits.lower() + " opaque"
    if n == 8:
        return f"rgb {digits[:6].lower()} alpha 0x{digits[6:].lower()}"
    return f"INVALID ({n} digits) -> browser drops the declaration"


def three_equal(digits: str) -> bool:
    """Whether the three channels are the same byte, hiding a swap."""
    n = len(digits)
    if n == 3:
        return digits[0] == digits[1] == digits[2]
    if n >= 6:
        return digits[0:2].lower() == digits[2:4].lower() == digits[4:6].lower()
    return False


def rgba_reading(body: str) -> str:
    """How Qt and a browser each read one rgba argument list."""
    parts = [p.strip() for p in body.split(",")]
    if len(parts) != 4:
        return f"{len(parts)} arguments"
    alpha = parts[3]
    if alpha.endswith("%"):
        return "percent alpha: both engines agree"
    try:
        number = float(alpha)
    except ValueError:
        return "alpha is not a number"
    if number <= 1.0:
        return (
            f"alpha {alpha}: Qt reads 0-255 int -> near transparent; CSS reads {number}"
        )
    return (
        f"DIVERGENT alpha {alpha}: Qt reads {number} of 255 = "
        f"{number / 255.0:.3f}; CSS clamps to 1.0 (OPAQUE)"
    )


def blocks_of(text: str) -> list:
    """Every brace-delimited block of a style sheet text, nested blocks included."""
    found = []
    depth = 0
    start = 0
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                found.append(text[start : i + 1])
    return found


def main() -> None:
    total = 0
    faults = []
    equals = []
    rgbas = []
    for path in TARGETS:
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        for lineno, line in enumerate(lines, 1):
            for m in HEX.finditer(line):
                digits = m.group(0)[1:]
                total += 1
                n = len(digits)
                site = f"{path.name}:{lineno}"
                if n not in (3, 6):
                    faults.append((site, m.group(0), n, line.strip()))
                if three_equal(digits):
                    equals.append((site, m.group(0)))
            for m in RGBA.finditer(line):
                rgbas.append((f"{path.name}:{lineno}", m.group(0)))
        sub = 0
        for block in blocks_of(text):
            if ":hover" in block or ":disabled" in block or ":checked" in block:
                sub += len(HEX.findall(block))
        print(f"{path.name}: colours in sub-blocks reachable = {sub}")

    print(f"\nTOTAL hex colour sites swept: {total}")
    print(f"THREE-EQUAL-CHANNEL sites: {len(equals)}")
    for site, value in equals:
        print(f"  {site}  {value}")
    print(f"\nHEX DIGIT-COUNT FAULTS: {len(faults)}")
    for site, value, n, line in faults:
        print(f"  {site}  {value}  ({n} digits)")
        print(f"      Qt : {qt_reading(value[1:])}")
        print(f"      CSS: {css_reading(value[1:])}")
        print(f"      src: {line[:90]}")
    print(f"\nRGBA SITES: {len(rgbas)}")
    for site, value in rgbas:
        body = RGBA.match(value).group(1)
        print(f"  {site}  {value}")
        print(f"      {rgba_reading(body)}")


if __name__ == "__main__":
    main()
