# PLE4703 modified-iterating-set: the Use instead block python -m ruff rule PLE4703 prints
nums = {1, 2, 3}
for num in nums.copy():
    nums.add(num + 5)
