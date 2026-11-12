# ASYNC110 async-busy-wait: the Example block python -m ruff rule ASYNC110 prints
import asyncio

DONE = False


async def func():
    while not DONE:
        await asyncio.sleep(1)
