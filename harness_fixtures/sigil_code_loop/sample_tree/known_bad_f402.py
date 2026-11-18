# F402 import-shadowed-by-loop-var: the lines above the Example block python -m ruff rule F402 prints define its free names
files = ["a.txt"]
from os import path

for path in files:
    print(path)
