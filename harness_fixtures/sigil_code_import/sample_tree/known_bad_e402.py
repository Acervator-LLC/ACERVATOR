# E402 module-import-not-at-top-of-file: the Example block python -m ruff rule E402 prints, then __all__ naming its imports
"One string"
"Two string"
a = 1
import os
from sys import x

__all__ = ["os", "x"]
