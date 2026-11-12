# ASYNC110 async-busy-wait: the Use instead block python -m ruff rule ASYNC110 prints
import asyncio

DONE = asyncio.Event()


async def func():
    await DONE.wait()
