"""Per-archetype calibration prompts, stored as Markdown so they are
directly editable by humans (operator or Claude) without touching
archetype code.

Usage from an archetype:
    from tools.harness.calibrations import load
    prompt_text = load("coding")   # returns the coding.md contents
"""

from __future__ import annotations

from pathlib import Path

_DIR = Path(__file__).resolve().parent


def load(name: str) -> str:
    """Load a calibration prompt by short name. Returns raw Markdown."""
    p = _DIR / f"{name}.md"
    if not p.is_file():
        raise FileNotFoundError(
            f"no calibration file for {name!r} at {p}. "
            f"Available: {sorted(f.stem for f in _DIR.glob('*.md'))}"
        )
    return p.read_text(encoding="utf-8")


def available() -> list[str]:
    """List available calibration names."""
    return sorted(f.stem for f in _DIR.glob("*.md"))
