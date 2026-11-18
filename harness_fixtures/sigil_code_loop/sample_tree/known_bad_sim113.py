# SIM113 enumerate-for-loop: the Example block python -m ruff rule SIM113 prints
fruits = ["apple", "banana", "cherry"]
i = 0
for fruit in fruits:
    print(f"{i + 1}. {fruit}")
    i += 1
