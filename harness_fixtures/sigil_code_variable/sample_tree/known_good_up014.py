# UP014 convert-named-tuple-functional-to-class: the Use instead block python -m ruff rule UP014 prints
from typing import NamedTuple


class Foo(NamedTuple):
    a: int
    b: str
