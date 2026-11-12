# FURB142 for-loop-set-mutations: the lines above the Use instead block python -m ruff rule FURB142 prints declare the type of s
s: set[int]
s = set()

s.update((1, 2, 3))
s.difference_update((1, 2, 3))
