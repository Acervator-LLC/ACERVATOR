# C404 unnecessary-list-comprehension-dict: the lines above the Example block python -m ruff rule C404 prints define its free names
f, foo = str, [1]
dict([(x, f(x)) for x in foo])
