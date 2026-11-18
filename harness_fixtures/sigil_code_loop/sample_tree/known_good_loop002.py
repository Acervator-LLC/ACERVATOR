# LOOP002 list-insert-front-in-loop: the corrected form dev_harness/sigils/code_loop.py holds in OWN
from collections import deque

queue: deque[str] = deque()
for name in ["Eric", "John", "Michael"]:
    queue.appendleft(name)
