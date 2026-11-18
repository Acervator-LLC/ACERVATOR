# NPY201 numpy2-deprecation: the Use instead block python -m ruff rule NPY201 prints
import numpy as np

arr1 = [np.inf, np.nan, np.nan, np.inf, np.inf]
arr2 = [np.float64(1.5), np.float64(5.1)]
np.round(arr2)
