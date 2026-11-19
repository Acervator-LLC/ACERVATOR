# LOOP004 open-method-readlines-in-for: the with name is bound afresh to a str buffer, so the loop reads no file an open method returned
import io
from pathlib import Path

path = Path("file.txt")
with path.open() as fp:
    fp = io.StringIO(fp.read().upper())
    for line in fp.readlines():
        print(line, end="")
