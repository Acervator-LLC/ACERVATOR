# LOOP001 list-pop-front-in-loop: the same call outside any loop, beside a loop that reads the list
queue = ["Eric", "John", "Michael"]
first = queue.pop(0)
upper = [name.upper() for name in queue]
