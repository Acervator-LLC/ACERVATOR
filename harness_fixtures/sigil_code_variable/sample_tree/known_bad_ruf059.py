# RUF059 unused-unpacked-variable: the Example block python -m ruff rule RUF059 prints
def get_pair():
    return 1, 2


def foo():
    x, y = get_pair()
    return x
