# LOOP004 open-method-readlines-in-for: the corrected form dev_harness/sigils/code_loop.py holds in OWN
from pathlib import Path

path = Path("file.txt")
with path.open() as fp:
    for line in fp:
        print(line, end="")
