# F404 late-future-import: the Use instead block python -m ruff rule F404 prints, then __all__ naming its imports
from __future__ import annotations
from pathlib import Path

__all__ = ["Path"]
