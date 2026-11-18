# NPY201 numpy2-deprecation: the Example block python -m ruff rule NPY201 prints
import numpy as np

arr1 = [np.Infinity, np.NaN, np.nan, np.PINF, np.inf]
arr2 = [np.float_(1.5), np.float64(5.1)]
np.round_(arr2)
