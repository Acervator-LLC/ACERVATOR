# RUF006 asyncio-dangling-task: the lines above the Example block python -m ruff rule RUF006 prints define its free names
async def some_coro(param: int) -> int: return param
import asyncio

for i in range(10):
    # This creates a weak reference to the task, which may be garbage
    # collected at any time.
    asyncio.create_task(some_coro(param=i))
