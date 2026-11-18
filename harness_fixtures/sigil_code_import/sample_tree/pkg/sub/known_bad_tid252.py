# TID252 relative-imports: the Example block python -m ruff rule TID252 prints, then __all__ naming its imports
from .. import foo

__all__ = ["foo"]
