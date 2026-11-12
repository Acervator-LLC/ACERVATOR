# FURB140 reimplemented-starmap: the lines above the Use instead block python -m ruff rule FURB140 prints define its free names
from operator import lt as predicate
some_iterable = [(1, 2)]
from itertools import starmap


all(starmap(predicate, some_iterable))
