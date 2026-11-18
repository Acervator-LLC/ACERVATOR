# PTH206 os-sep-split: the lines above the Example block python -m ruff rule PTH206 prints define its free names
blocklist = ["my"]
import os

"path/to/file_name.txt".split(os.sep)[-1]

"path/to/file_name.txt".split(os.sep)[-2]

# Iterating over the path parts
if any(part in blocklist for part in "my/file/path".split(os.sep)):
    ...
