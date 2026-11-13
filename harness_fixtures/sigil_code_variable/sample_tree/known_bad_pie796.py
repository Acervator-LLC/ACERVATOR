# PIE796 non-unique-enums: the Example block python -m ruff rule PIE796 prints
from enum import Enum


class Foo(Enum):
    A = 1
    B = 2
    C = 1
