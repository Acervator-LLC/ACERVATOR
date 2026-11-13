# RUF070 unnecessary-assign-before-yield: the Example block python -m ruff rule RUF070 prints
def gen():
    x = 1
    yield x
