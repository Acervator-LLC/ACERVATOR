# N812 lowercase-imported-as-non-lowercase: the Example block python -m ruff rule N812 prints, then __all__ naming its imports
from example import myclassname as MyClassName

__all__ = ["MyClassName"]
