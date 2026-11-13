# PERF401 manual-list-comprehension: the Example block python -m ruff rule PERF401 prints
original = list(range(10000))
filtered = []
for i in original:
    if i % 2:
        filtered.append(i)
