# FURB122 for-loop-writes: the lines above the Example block python -m ruff rule FURB122 prints define its free names
lines = lines_b = ["line\n"]
from pathlib import Path

with Path("file").open("w") as f:
    for line in lines:
        f.write(line)

with Path("file").open("wb") as f_b:
    for line_b in lines_b:
        f_b.write(line_b.encode())
