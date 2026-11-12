# PERF402 manual-list-copy: the Example block python -m ruff rule PERF402 prints
original = list(range(10000))
filtered = []
for i in original:
    filtered.append(i)
