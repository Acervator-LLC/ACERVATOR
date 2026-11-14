# TID252 relative-imports: the Use instead block python -m ruff rule TID252 prints, then __all__ naming its imports
from mypkg import foo

__all__ = ["foo"]
