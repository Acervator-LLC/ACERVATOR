# N814 camelcase-imported-as-constant: the Example block python -m ruff rule N814 prints, then __all__ naming its imports
from example import MyClassName as MY_CLASS_NAME

__all__ = ["MY_CLASS_NAME"]
