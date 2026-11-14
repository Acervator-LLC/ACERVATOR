# E401 multiple-imports-on-one-line: the Example block python -m ruff rule E401 prints, then __all__ naming its imports
import sys, os

__all__ = ["os", "sys"]
