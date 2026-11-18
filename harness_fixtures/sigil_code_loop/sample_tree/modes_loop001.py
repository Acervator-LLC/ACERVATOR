# LOOP001 list-pop-front-in-loop: each faulty_ function holds one form of the fault, its corrected_
# twin the deque form, and its outside_ twin the same call outside any loop
from collections import deque
from collections.abc import Callable


def faulty_for(names: list[str]) -> list[str]:
    queue = list(names)
    served: list[str] = []
    for _ in range(len(names)):
        served.append(queue.pop(0))
    return served


def corrected_for(names: list[str]) -> list[str]:
    queue = deque(names)
    served: list[str] = []
    for _ in range(len(names)):
        served.append(queue.popleft())
    return served


def outside_for(names: list[str]) -> list[str]:
    queue = list(names)
    first = queue.pop(0)
    return [first, *(name.upper() for name in queue)]


def faulty_while(names: list[str]) -> int:
    queue = list(names)
    count = 0
    while len(queue) > 1:
        queue.pop(0)
        count += 1
    return count


def corrected_while(names: list[str]) -> int:
    queue = deque(names)
    count = 0
    while len(queue) > 1:
        queue.popleft()
        count += 1
    return count


def outside_while(names: list[str]) -> int:
    queue = list(names)
    queue.pop(0)
    count = 0
    while count < len(queue):
        count += 1
    return count


def faulty_nested(batches: list[list[str]]) -> list[str]:
    queue: list[str] = []
    served: list[str] = []
    for batch in batches:
        queue.extend(batch)
        while queue:
            served.append(queue.pop(0))
    return served


def corrected_nested(batches: list[list[str]]) -> list[str]:
    queue: deque[str] = deque()
    served: list[str] = []
    for batch in batches:
        queue.extend(batch)
        while queue:
            served.append(queue.popleft())
    return served


def outside_nested(batches: list[list[str]]) -> list[str]:
    queue = [name for batch in batches for name in batch]
    first = queue.pop(0)
    return [first, *queue]


def faulty_rebind(names: list[str]) -> list[str]:
    queue = list(names)
    served: list[str] = []
    while queue:
        served.append(queue[0])
        queue = queue[1:]
    return served


def corrected_rebind(names: list[str]) -> list[str]:
    queue = deque(names)
    served: list[str] = []
    while queue:
        served.append(queue.popleft())
    return served


def outside_rebind(names: list[str]) -> list[str]:
    queue = list(names)
    queue = queue[1:]
    return [name.upper() for name in queue]


def faulty_site_fetch_all(
    sources: tuple[str, ...], should_stop: Callable[[], bool], deadline: float
) -> list[str]:
    outstanding = list(sources)
    fetched: list[str] = []
    while outstanding:
        if should_stop() or deadline <= 0:
            break
        source = outstanding.pop(0)
        fetched.append(source)
    return fetched


def corrected_site_fetch_all(
    sources: tuple[str, ...], should_stop: Callable[[], bool], deadline: float
) -> list[str]:
    outstanding = deque(sources)
    fetched: list[str] = []
    while outstanding:
        if should_stop() or deadline <= 0:
            break
        source = outstanding.popleft()
        fetched.append(source)
    return fetched


def outside_site_fetch_all(sources: tuple[str, ...]) -> list[str]:
    outstanding = list(sources)
    source = outstanding.pop(0)
    return [source, *(name for name in outstanding if name)]
