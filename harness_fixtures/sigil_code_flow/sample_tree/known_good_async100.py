# ASYNC100 cancel-scope-no-checkpoint: the lines above the Use instead block python -m ruff rule ASYNC100 prints define its free names
from asyncio import Future as awaitable
do_something = print
import asyncio


async def func():
    async with asyncio.timeout(2):
        do_something()
        await awaitable()
