# TC001 typing-only-first-party-import: the Use instead block python -m ruff rule TC001 prints
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import local_module


def func(sized: local_module.Container) -> int:
    return len(sized)
