# N812 lowercase-imported-as-non-lowercase: the Use instead block python -m ruff rule N812 prints, then __all__ naming its imports
from example import myclassname

__all__ = ["myclassname"]
