# N811 constant-imported-as-non-constant: the Use instead block python -m ruff rule N811 prints, then __all__ naming its imports
from example import CONSTANT_VALUE

__all__ = ["CONSTANT_VALUE"]
