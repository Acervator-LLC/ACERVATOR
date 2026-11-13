# UP013 convert-typed-dict-functional-to-class: the Example block python -m ruff rule UP013 prints
from typing import TypedDict

Foo = TypedDict("Foo", {"a": int, "b": str})
