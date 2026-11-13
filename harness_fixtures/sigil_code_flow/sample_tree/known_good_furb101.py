# FURB101 read-whole-file: the Use instead block python -m ruff rule FURB101 prints
from pathlib import Path

contents = Path("file.txt").read_text()
