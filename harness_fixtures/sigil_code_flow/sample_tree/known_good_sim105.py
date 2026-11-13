# SIM105 suppressible-exception: the Use instead block python -m ruff rule SIM105 prints
import contextlib

with contextlib.suppress(ZeroDivisionError):
    1 / 0
