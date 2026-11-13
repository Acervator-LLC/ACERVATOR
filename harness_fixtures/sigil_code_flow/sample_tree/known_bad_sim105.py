# SIM105 suppressible-exception: the Example block python -m ruff rule SIM105 prints
try:
    1 / 0
except ZeroDivisionError:
    pass
