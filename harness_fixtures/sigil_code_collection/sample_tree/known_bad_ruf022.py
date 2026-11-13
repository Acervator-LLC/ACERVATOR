# RUF022 unsorted-dunder-all: the Example block python -m ruff rule RUF022 prints
import sys

__all__ = [
    "b",
    "c",
    "a",
]

if sys.platform == "win32":
    __all__ += ["z", "y"]
