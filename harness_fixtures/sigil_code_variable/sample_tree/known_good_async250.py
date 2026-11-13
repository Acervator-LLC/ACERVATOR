# ASYNC250 blocking-input-in-async-function: the Use instead block python -m ruff rule ASYNC250 prints
import asyncio


async def foo():
    loop = asyncio.get_running_loop()
    username = await loop.run_in_executor(None, input, "Username:")
