# RUF007 zip-instead-of-pairwise: the Use instead block python -m ruff rule RUF007 prints
from itertools import pairwise

letters = "ABCD"
pairwise(letters)  # ("A", "B"), ("B", "C"), ("C", "D")
