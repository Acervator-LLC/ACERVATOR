# ASYNC230 blocking-open-call-in-async-function: the Use instead block python -m ruff rule ASYNC230 prints
import anyio


async def foo():
    async with await anyio.open_file("bar.txt") as f:
        contents = await f.read()
