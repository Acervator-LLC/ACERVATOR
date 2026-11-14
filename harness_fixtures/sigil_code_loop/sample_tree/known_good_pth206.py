# PTH206 os-sep-split: the lines above the Use instead block python -m ruff rule PTH206 prints define its free names
blocklist = ["my"]
from pathlib import Path

Path("path/to/file_name.txt").name

Path("path/to/file_name.txt").parent.name

# Iterating over the path parts
if any(part in blocklist for part in Path("my/file/path").parts):
    ...
