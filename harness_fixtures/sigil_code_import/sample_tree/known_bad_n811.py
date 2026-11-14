# N811 constant-imported-as-non-constant: the Example block python -m ruff rule N811 prints, then __all__ naming its imports
from example import CONSTANT_VALUE as ConstantValue

__all__ = ["ConstantValue"]
