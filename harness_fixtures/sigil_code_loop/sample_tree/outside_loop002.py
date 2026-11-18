# LOOP002 list-insert-front-in-loop: the same call outside any loop, beside a loop that reads the list
queue: list[str] = ["John", "Michael"]
queue.insert(0, "Eric")
upper = [name.upper() for name in queue]
