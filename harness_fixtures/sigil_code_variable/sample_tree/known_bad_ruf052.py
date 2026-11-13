# RUF052 used-dummy-variable: the Example block python -m ruff rule RUF052 prints
def function():
    _variable = 3
    # important: avoid shadowing the builtin `id()` function!
    _id = 4
    return _variable + _id
