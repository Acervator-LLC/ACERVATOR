# PLR1708 stop-iteration-return: the Use instead block python -m ruff rule PLR1708 prints
def my_generator():
    yield 1
    yield 2
    return  # Use return instead
