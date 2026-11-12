# RUF006 asyncio-dangling-task: the lines above the Use instead block python -m ruff rule RUF006 prints define its free names
async def some_coro(param: int) -> int: return param
import asyncio

background_tasks = set()

for i in range(10):
    task = asyncio.create_task(some_coro(param=i))

    # Add task to the set. This creates a strong reference.
    background_tasks.add(task)

    # To prevent keeping references to finished tasks forever,
    # make each task remove its own reference from the set after
    # completion:
    task.add_done_callback(background_tasks.discard)
