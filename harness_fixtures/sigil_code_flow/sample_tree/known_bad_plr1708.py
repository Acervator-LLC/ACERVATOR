# PLR1708 stop-iteration-return: the Example block python -m ruff rule PLR1708 prints
def my_generator():
    yield 1
    yield 2
    raise StopIteration  # This causes RuntimeError at runtime
