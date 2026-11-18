# SIM107 return-in-try-except-finally: the Use instead block python -m ruff rule SIM107 prints
def squared(n):
    try:
        return_value = n**2
    except Exception:
        return_value = "An exception occurred"
    finally:
        return_value = -1
    return return_value
