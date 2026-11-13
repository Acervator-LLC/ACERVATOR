# FURB140 reimplemented-starmap: the lines above the Example block python -m ruff rule FURB140 prints define its free names
from operator import lt as predicate
some_iterable = [(1, 2)]
all(predicate(a, b) for a, b in some_iterable)
