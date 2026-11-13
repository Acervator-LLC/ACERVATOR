# RUF022 unsorted-dunder-all: the Use instead block python -m ruff rule RUF022 prints
import sys

__all__ = [
    "a",
    "b",
    "c",
]

if sys.platform == "win32":
    __all__ += ["y", "z"]
