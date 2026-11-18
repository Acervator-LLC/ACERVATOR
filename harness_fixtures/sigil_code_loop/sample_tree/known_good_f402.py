# F402 import-shadowed-by-loop-var: the lines above the Use instead block python -m ruff rule F402 prints define its free names, and __all__ names its import
files = ["a.txt"]
from os import path


for filename in files:
    print(filename)

__all__ = ["path"]
