# TC004 runtime-import-in-type-checking-block: the Example block python -m ruff rule TC004 prints
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import foo


def bar() -> None:
    foo.bar()  # raises NameError: name 'foo' is not defined
