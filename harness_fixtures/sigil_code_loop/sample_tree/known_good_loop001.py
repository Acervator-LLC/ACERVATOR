# LOOP001 list-pop-front-in-loop: the corrected form dev_harness/sigils/code_loop.py holds in OWN
from collections import deque

queue = deque(["Eric", "John", "Michael"])
served: list[str] = []
while queue:
    served.append(queue.popleft())
