# LOOP002 list-insert-front-in-loop: each faulty_ function holds one form of the fault, its corrected_
# twin the deque form, and its outside_ twin the same call outside any loop
from collections import deque


def faulty_for(lines: list[str]) -> list[str]:
    history: list[str] = []
    for line in lines:
        history.insert(0, line.strip())
    return history


def corrected_for(lines: list[str]) -> list[str]:
    history: deque[str] = deque()
    for line in lines:
        history.appendleft(line.strip())
    return list(history)


def outside_for(lines: list[str]) -> list[str]:
    history = [line.strip() for line in lines]
    history.insert(0, "start")
    return history


def faulty_while(count: int) -> list[str]:
    stack: list[str] = []
    step = 0
    while step < count:
        stack.insert(0, str(step))
        step += 1
    return stack


def corrected_while(count: int) -> list[str]:
    stack: deque[str] = deque()
    step = 0
    while step < count:
        stack.appendleft(str(step))
        step += 1
    return list(stack)


def outside_while(count: int) -> list[str]:
    stack: list[str] = []
    stack.insert(0, "start")
    step = 0
    while step < count:
        step += 1
    return stack


def faulty_nested(groups: list[list[str]]) -> list[str]:
    order: list[str] = []
    for group in groups:
        for name in group:
            order.insert(0, name)
    return order


def corrected_nested(groups: list[list[str]]) -> list[str]:
    order: deque[str] = deque()
    for group in groups:
        for name in group:
            order.appendleft(name)
    return list(order)


def outside_nested(groups: list[list[str]]) -> list[str]:
    order = [name for group in groups for name in group]
    order.insert(0, "start")
    return order


def faulty_rebind(lines: list[str]) -> list[str]:
    history: list[str] = []
    for line in lines:
        history = [line] + history
    return history


def corrected_rebind(lines: list[str]) -> list[str]:
    history: deque[str] = deque()
    for line in lines:
        history.appendleft(line)
    return list(history)


def outside_rebind(lines: list[str]) -> list[str]:
    history = [line.strip() for line in lines]
    history = ["start"] + history
    return history
