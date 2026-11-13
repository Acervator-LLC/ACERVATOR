# SIM117 multiple-with-statements: the lines above the Example block python -m ruff rule SIM117 prints define its free names
from contextlib import nullcontext as A, nullcontext as B
with A() as a:
    with B() as b:
        pass
