# E401 multiple-imports-on-one-line: the Use instead block python -m ruff rule E401 prints, then __all__ naming its imports
import os
import sys

__all__ = ["os", "sys"]
