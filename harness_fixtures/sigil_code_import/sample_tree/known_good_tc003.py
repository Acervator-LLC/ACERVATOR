# TC003 typing-only-standard-library-import: the Use instead block python -m ruff rule TC003 prints
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def func(path: Path) -> str:
    return str(path)
