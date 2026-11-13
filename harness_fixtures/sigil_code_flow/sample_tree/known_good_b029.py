# B029 except-with-empty-tuple: the Use instead block python -m ruff rule B029 prints
try:
    1 / 0
except ZeroDivisionError:
    ...
