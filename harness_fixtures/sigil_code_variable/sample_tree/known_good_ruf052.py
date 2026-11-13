# RUF052 used-dummy-variable: the Use instead block python -m ruff rule RUF052 prints
def function():
    variable = 3
    # important: avoid shadowing the builtin `id()` function!
    id_ = 4
    return variable + id_
