# F404 late-future-import: the Example block python -m ruff rule F404 prints, then __all__ naming its imports
from pathlib import Path
from __future__ import annotations

__all__ = ["Path"]
