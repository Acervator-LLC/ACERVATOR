# TC003 and PLC0415: the Example blocks python -m ruff rule TC003 and rule PLC0415 print
from __future__ import annotations

from pathlib import Path


def func(path: Path) -> str:
    return str(path)


def print_python_version():
    import platform

    print(platform.python_version())
