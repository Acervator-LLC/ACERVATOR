# RUF059 unused-unpacked-variable: the lines above the Use instead block python -m ruff rule RUF059 prints define its free names
from os import get_terminal_size as get_pair
def foo():
    x, _ = get_pair()
    return x
