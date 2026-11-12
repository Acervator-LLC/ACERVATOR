# PLR1733 unnecessary-dict-index-lookup: the Example block python -m ruff rule PLR1733 prints
FRUITS = {"apple": 1, "orange": 10, "berry": 22}

for fruit_name, fruit_count in FRUITS.items():
    print(FRUITS[fruit_name])
