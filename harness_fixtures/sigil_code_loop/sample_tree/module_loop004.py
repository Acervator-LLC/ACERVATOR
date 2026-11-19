# LOOP004 open-method-readlines-in-for: a file an open method returned, bound at module scope and read
# at module scope, through an assignment expression, from a function and from a method
from pathlib import Path

PATH = Path("file.txt")
MODULE_FILE = PATH.open()

for module_line in MODULE_FILE.readlines():
    print(module_line)

if (MODULE_WALRUS := PATH.open()) is not None:
    for module_line in MODULE_WALRUS.readlines():
        print(module_line)


def faulty_read_module_file() -> None:
    for line in MODULE_FILE.readlines():
        print(line)


class FaultyReadsModuleFile:
    def lines(self) -> None:
        for line in MODULE_FILE.readlines():
            print(line)
