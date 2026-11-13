# PLC0415 import-outside-top-level: the Example block python -m ruff rule PLC0415 prints
def print_python_version():
    import platform

    print(platform.python_version())
