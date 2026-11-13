# UP014 convert-named-tuple-functional-to-class: the Example block python -m ruff rule UP014 prints
from typing import NamedTuple

Foo = NamedTuple("Foo", [("a", int), ("b", str)])
