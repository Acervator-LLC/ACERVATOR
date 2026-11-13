# TC005 empty-type-checking-block: the Example block python -m ruff rule TC005 prints
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

print("Hello, world!")
