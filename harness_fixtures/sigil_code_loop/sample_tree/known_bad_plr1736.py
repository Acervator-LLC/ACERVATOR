# PLR1736 unnecessary-list-index-lookup: the Example block python -m ruff rule PLR1736 prints
letters = ["a", "b", "c"]

for index, letter in enumerate(letters):
    print(letters[index])
