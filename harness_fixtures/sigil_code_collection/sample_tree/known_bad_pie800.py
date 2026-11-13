# PIE800 unnecessary-spread: the Example block python -m ruff rule PIE800 prints
foo = {"A": 1, "B": 2}
bar = {**foo, **{"C": 3}}
