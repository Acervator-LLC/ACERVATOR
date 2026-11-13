# PLW0120 useless-else-on-loop: the lines above the Example block python -m ruff rule PLW0120 prints define its free names
items = ["a"]
for item in items:
    print(item)
else:
    print("All items printed")
