# FURB103 write-whole-file: the Use instead block python -m ruff rule FURB103 prints
from pathlib import Path

Path("file.txt").write_text("some text")
