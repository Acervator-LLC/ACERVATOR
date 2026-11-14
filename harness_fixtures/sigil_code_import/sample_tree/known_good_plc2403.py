# PLC2403 non-ascii-import-name: the first Use instead block python -m ruff rule PLC2403 prints, then __all__ naming its imports
import bar

__all__ = ["bar"]
