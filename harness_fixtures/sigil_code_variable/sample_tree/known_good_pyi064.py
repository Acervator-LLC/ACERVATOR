# PYI064 redundant-final-literal: the Use instead block python -m ruff rule PYI064 prints, then __all__ naming its imports
from typing import Final, Literal

x: Final = 42
y: Final = 42

__all__ = ["Literal"]
