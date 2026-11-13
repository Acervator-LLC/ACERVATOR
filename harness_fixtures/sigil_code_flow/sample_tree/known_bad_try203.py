# TRY203 useless-try-except: the lines above the Example block python -m ruff rule TRY203 prints define its free names
bar = print
def foo():
    try:
        bar()
    except NotImplementedError:
        raise
