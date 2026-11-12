# TC003 typing-only-standard-library-import: the Example block python -m ruff rule TC003 prints
from __future__ import annotations

from pathlib import Path


def func(path: Path) -> str:
    return str(path)
