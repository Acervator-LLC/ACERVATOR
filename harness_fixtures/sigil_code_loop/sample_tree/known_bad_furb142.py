# FURB142 for-loop-set-mutations: the lines above the Example block python -m ruff rule FURB142 prints declare the type of s
s: set[int]
s = set()

for x in (1, 2, 3):
    s.add(x)

for x in (1, 2, 3):
    s.discard(x)
