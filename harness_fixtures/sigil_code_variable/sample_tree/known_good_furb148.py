# FURB148 unnecessary-enumerate: the lines above the Use instead block python -m ruff rule FURB148 prints define its free names
sequence = ["a", "b"]
for index in range(len(sequence)):
    print(index)

for value in sequence:
    print(value)
