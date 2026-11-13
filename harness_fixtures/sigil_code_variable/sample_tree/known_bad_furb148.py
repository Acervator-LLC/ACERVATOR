# FURB148 unnecessary-enumerate: the lines above the Example block python -m ruff rule FURB148 prints define its free names
sequence = ["a", "b"]
for index, _ in enumerate(sequence):
    print(index)

for _, value in enumerate(sequence):
    print(value)
