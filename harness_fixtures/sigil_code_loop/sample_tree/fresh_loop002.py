# LOOP002 list-insert-front-in-loop: each pass assigns the list afresh, so no list carries from pass to pass
names = ["Eric", "John", "Michael"]
rows: list[list[str]] = []
for name in names:
    row = [name]
    row.insert(0, "Hello")
    rows.append(row)
