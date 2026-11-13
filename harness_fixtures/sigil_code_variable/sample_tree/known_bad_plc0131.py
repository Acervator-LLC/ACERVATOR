# PLC0131 type-bivariance: the Example block python -m ruff rule PLC0131 prints
from typing import TypeVar

T = TypeVar("T", covariant=True, contravariant=True)
