# LOOP001 list-pop-front-in-loop: the faulty form dev_harness/sigils/code_loop.py holds in OWN
queue = ["Eric", "John", "Michael"]
served: list[str] = []
while queue:
    served.append(queue.pop(0))
