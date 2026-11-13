# ASYNC230 blocking-open-call-in-async-function: the Example block python -m ruff rule ASYNC230 prints
async def foo():
    with open("bar.txt") as f:
        contents = f.read()
