# F707 default-except-not-last: the Use instead block python -m ruff rule F707 prints
def reciprocal(n):
    try:
        reciprocal = 1 / n
    except ZeroDivisionError:
        print("Cannot divide by zero.")
    except:
        print("An exception occurred.")
    else:
        return reciprocal
