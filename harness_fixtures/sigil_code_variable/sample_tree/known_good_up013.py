# UP013 convert-typed-dict-functional-to-class: the Use instead block python -m ruff rule UP013 prints
from typing import TypedDict


class Foo(TypedDict):
    a: int
    b: str
