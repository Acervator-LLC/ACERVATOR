# N813 camelcase-imported-as-lowercase: the Example block python -m ruff rule N813 prints, then __all__ naming its imports
from example import MyClassName as myclassname

__all__ = ["myclassname"]
