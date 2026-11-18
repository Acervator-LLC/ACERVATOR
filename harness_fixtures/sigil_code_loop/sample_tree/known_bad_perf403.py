# PERF403 manual-dict-comprehension: the Example block python -m ruff rule PERF403 prints
pairs = (("a", 1), ("b", 2))
result = {}
for x, y in pairs:
    if y % 2:
        result[x] = y
