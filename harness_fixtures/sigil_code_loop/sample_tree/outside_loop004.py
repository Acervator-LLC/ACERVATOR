# LOOP004 open-method-readlines-in-for: the same call outside any loop, kept as a list a builder indexes
from pathlib import Path

path = Path("file.txt")
with path.open() as fp:
    lines = fp.readlines()
picked = [lines[index] for index in (0, 2) if index < len(lines)]
