# LOOP001 list-pop-front-in-loop: each pass assigns the list afresh, so no list carries from pass to pass
names = ["Eric", "John", "Michael"]
firsts: list[str] = []
for name in names:
    letters = list(name)
    firsts.append(letters.pop(0))
