#!/usr/bin/env python3
"""
generate_splash.py — AcervatorOS Boot Splash Generator
=======================================================
Generates a 1920×1080 boot splash image using ReportLab.
Saved as PNG for use with Plymouth or as a desktop background.

Usage:
    python3 generate_splash.py --version 3.7.0 --output /boot/acervator-splash.png
"""

import argparse
import importlib.util
import math
import sys
import tempfile
from pathlib import Path


def _installed(module: str) -> bool:
    """Report whether ``module`` can be imported, without importing it."""
    return importlib.util.find_spec(module) is not None


def generate_splash(
    version: str, output_path: str, width: int = 1920, height: int = 1080
):
    """Generate the AcervatorOS boot splash as a PNG.

    Pillow draws the higher-quality image and reportlab is the fallback.
    Each delegate imports what it draws with, so this function only asks
    which of the two is installed.
    """
    if _installed("PIL"):
        return _generate_splash_pil(version, output_path, width, height)
    if _installed("reportlab"):
        return _generate_splash_reportlab(version, output_path, width, height)
    print("  reportlab and Pillow are both absent - skipping splash generation")
    return False


def _generate_splash_pil(version, output_path, width, height):
    """High-quality splash using Pillow."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (width, height), color=(10, 10, 20))
    draw = ImageDraw.Draw(img)

    # Background gradient (dark navy to near-black)
    for y in range(height):
        t = y / height
        r = int(10 + t * 5)
        g = int(10 + t * 5)
        b = int(20 + t * 10)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Draw oscillating wave (represents the harvest-fold cycle)
    cy = height // 2
    CYAN = (0, 204, 170)
    GOLD = (255, 184, 0)

    # Wave: three cycles, fading toward edges
    for i in range(width):
        t = i / width
        fade = math.sin(t * math.pi) ** 0.5
        y_wave = int(cy + math.sin(t * 6 * math.pi) * 40 * fade)
        alpha = int(180 * fade)
        draw.ellipse([(i - 1, y_wave - 2), (i + 1, y_wave + 2)], fill=(*CYAN, alpha))

    # Title text
    try:
        font_large = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 96
        )
        font_sub = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 42
        )
        font_ver = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28
        )
    except (IOError, OSError):
        font_large = ImageFont.load_default()
        font_sub = font_large
        font_ver = font_large

    # "ACERVATOR" — centred
    title = "ACERVATOR"
    bbox = draw.textbbox((0, 0), title, font=font_large)
    tw = bbox[2] - bbox[0]
    tx = (width - tw) // 2
    ty = height // 2 - 120
    draw.text((tx + 2, ty + 2), title, fill=(0, 60, 50), font=font_large)  # shadow
    draw.text((tx, ty), title, fill=CYAN, font=font_large)

    # Subtitle
    sub = "Accumulation Trading Platform"
    bbox = draw.textbbox((0, 0), sub, font=font_sub)
    sw = bbox[2] - bbox[0]
    sx = (width - sw) // 2
    draw.text((sx, ty + 110), sub, fill=(180, 220, 210), font=font_sub)

    # Version
    ver_text = f"v{version}"
    bbox = draw.textbbox((0, 0), ver_text, font=font_ver)
    vw = bbox[2] - bbox[0]
    vx = (width - vw) // 2
    draw.text((vx, ty + 175), ver_text, fill=GOLD, font=font_ver)

    # Bottom tagline
    tag = "Visual  ·  Tactical  ·  Direction-Agnostic"
    bbox = draw.textbbox((0, 0), tag, font=font_ver)
    tw = bbox[2] - bbox[0]
    draw.text(
        ((width - tw) // 2, height - 80), tag, fill=(100, 140, 130), font=font_ver
    )

    img.save(output_path, "PNG", optimize=True)
    print(f"  ✓ Boot splash saved: {output_path}")
    return True


def _generate_splash_reportlab(version, output_path, width, height):
    """Fallback splash using reportlab canvas → PNG via reportlab renderPM."""
    print("  Pillow not available - using minimal splash")
    # Create a minimal solid-colour PNG via reportlab
    from reportlab.graphics.shapes import Drawing, Rect, String
    from reportlab.lib.colors import HexColor
    from reportlab.graphics import renderPM

    d = Drawing(width, height)
    d.add(Rect(0, 0, width, height, fillColor=HexColor("#0A0A14"), strokeColor=None))
    d.add(
        String(
            width / 2,
            height / 2 + 20,
            "ACERVATOR",
            fontName="Helvetica-Bold",
            fontSize=80,
            fillColor=HexColor("#00CCAA"),
            textAnchor="middle",
        )
    )
    d.add(
        String(
            width / 2,
            height / 2 - 30,
            f"v{version}",
            fontName="Helvetica",
            fontSize=32,
            fillColor=HexColor("#FFB800"),
            textAnchor="middle",
        )
    )

    renderPM.drawToFile(d, output_path, fmt="PNG")
    print(f"  ✓ Minimal boot splash saved: {output_path}")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate AcervatorOS boot splash")
    parser.add_argument("--version", default="unknown", help="Version string")
    parser.add_argument(
        "--output",
        default=str(Path(tempfile.gettempdir()) / "acervator-splash.png"),
        help="Output PNG path",
    )
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    args = parser.parse_args()

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    success = generate_splash(args.version, args.output, args.width, args.height)
    sys.exit(0 if success else 1)
