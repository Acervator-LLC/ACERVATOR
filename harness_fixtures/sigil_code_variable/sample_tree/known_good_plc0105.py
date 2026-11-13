# PLC0105 type-name-incorrect-variance: the Use instead block python -m ruff rule PLC0105 prints
from typing import TypeVar

T_co = TypeVar("T_co", covariant=True)
U_contra = TypeVar("U_contra", contravariant=True)
V = TypeVar("V")
