# PLC0105 type-name-incorrect-variance: the Example block python -m ruff rule PLC0105 prints
from typing import TypeVar

T = TypeVar("T", covariant=True)
U = TypeVar("U", contravariant=True)
V_co = TypeVar("V_co")
