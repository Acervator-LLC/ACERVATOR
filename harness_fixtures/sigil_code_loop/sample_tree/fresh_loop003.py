# LOOP003 str-concat-in-loop: each pass assigns the str afresh, so no str carries from pass to pass
words = ["Eric", "John", "Michael"]
labels: list[str] = []
for word in words:
    label = f"{word}:"
    label += " present"
    labels.append(label)
