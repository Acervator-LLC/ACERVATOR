# F401 unused-import: the Use instead blocks python -m ruff rule F401 prints
def area(radius):
    return 3.14 * radius**2


from importlib.util import find_spec

if find_spec("numpy") is not None:
    print("numpy is installed")
else:
    print("numpy is not installed")
