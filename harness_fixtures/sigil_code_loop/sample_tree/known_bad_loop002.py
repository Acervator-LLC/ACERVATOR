# LOOP002 list-insert-front-in-loop: the faulty form dev_harness/sigils/code_loop.py holds in OWN
queue: list[str] = []
for name in ["Eric", "John", "Michael"]:
    queue.insert(0, name)
