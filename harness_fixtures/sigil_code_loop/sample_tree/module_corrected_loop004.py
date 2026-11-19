# LOOP004 open-method-readlines-in-for: the corrected twin of module_loop004.py, iterating each file object
from pathlib import Path

PATH = Path("file.txt")
MODULE_FILE = PATH.open()

for module_line in MODULE_FILE:
    print(module_line)

if (MODULE_WALRUS := PATH.open()) is not None:
    for module_line in MODULE_WALRUS:
        print(module_line)


def corrected_read_module_file() -> None:
    for line in MODULE_FILE:
        print(line)


class CorrectedReadsModuleFile:
    def lines(self) -> None:
        for line in MODULE_FILE:
            print(line)
