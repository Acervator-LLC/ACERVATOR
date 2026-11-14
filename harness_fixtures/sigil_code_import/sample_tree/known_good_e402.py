# E402 module-import-not-at-top-of-file: the Use instead block python -m ruff rule E402 prints, then __all__ naming its imports
import os
from sys import x

"One string"
"Two string"
a = 1

__all__ = ["os", "x"]
