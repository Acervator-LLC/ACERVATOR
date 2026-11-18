# I001 unsorted-imports: the Example block python -m ruff rule I001 prints, then __all__ naming its imports
import pandas
import numpy as np

__all__ = ["np", "pandas"]
