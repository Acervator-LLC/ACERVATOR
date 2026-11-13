# C420 unnecessary-dict-comprehension-for-iterable: the lines above the Use instead block python -m ruff rule C420 prints define its free names
iterable = ["a", "b"]
dict.fromkeys(iterable)
dict.fromkeys(iterable, 1)
