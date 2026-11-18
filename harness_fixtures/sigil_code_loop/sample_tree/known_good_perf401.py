# PERF401 manual-list-comprehension: the Use instead block python -m ruff rule PERF401 prints
original = list(range(10000))
filtered = [x for x in original if x % 2]
original = list(range(10000))
filtered.extend(x for x in original if x % 2)
