# B012 jump-statement-in-finally: the Use instead block python -m ruff rule B012 prints
def speed(distance, time):
    try:
        return distance / time
    except ZeroDivisionError:
        raise ValueError("Time cannot be zero")
