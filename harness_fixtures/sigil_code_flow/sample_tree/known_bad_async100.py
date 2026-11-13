# ASYNC100 cancel-scope-no-checkpoint: the lines above the Example block python -m ruff rule ASYNC100 prints define its free names
do_something = print
import asyncio


async def func():
    async with asyncio.timeout(2):
        do_something()
