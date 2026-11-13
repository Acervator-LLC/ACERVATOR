# PLC0131 type-bivariance: the Use instead block python -m ruff rule PLC0131 prints
from typing import TypeVar

T_co = TypeVar("T_co", covariant=True)
T_contra = TypeVar("T_contra", contravariant=True)
