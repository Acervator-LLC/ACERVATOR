# PLW0128 redeclared-assigned-name: the Use instead block python -m ruff rule PLW0128 prints
# this is assuming you want to assign 3 to `a`
_, b, a = (1, 2, 3)
print(a)  # 3
