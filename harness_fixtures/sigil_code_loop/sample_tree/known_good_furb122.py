# FURB122 for-loop-writes: the lines above the Use instead block python -m ruff rule FURB122 prints define its free names
lines = lines_b = ["line\n"]
from pathlib import Path

with Path("file").open("w") as f:
    f.writelines(lines)

with Path("file").open("wb") as f_b:
    f_b.writelines(line_b.encode() for line_b in lines_b)
