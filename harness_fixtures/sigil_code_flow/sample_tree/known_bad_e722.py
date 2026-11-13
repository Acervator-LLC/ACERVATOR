# E722 bare-except: the Example block python -m ruff rule E722 prints
try:
    raise KeyboardInterrupt("You probably don't mean to break CTRL-C.")
except:
    print("But a bare `except` will ignore keyboard interrupts.")
