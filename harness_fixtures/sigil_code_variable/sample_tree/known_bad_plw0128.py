# PLW0128 redeclared-assigned-name: the Example block python -m ruff rule PLW0128 prints
a, b, a = (1, 2, 3)
print(a)  # 3
