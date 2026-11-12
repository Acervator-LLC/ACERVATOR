# C416 unnecessary-comprehension: the lines above the Use instead block python -m ruff rule C416 prints define its free names
iterable = [("a", 1)]
dict(iterable)
list(iterable)
set(iterable)
