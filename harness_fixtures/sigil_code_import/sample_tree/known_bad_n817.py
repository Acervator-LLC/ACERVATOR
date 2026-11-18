# N817 camelcase-imported-as-acronym: the Example block python -m ruff rule N817 prints, then __all__ naming its imports
from example import MyClassName as MCN

__all__ = ["MCN"]
