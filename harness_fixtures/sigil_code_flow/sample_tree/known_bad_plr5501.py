# PLR5501 collapsible-else-if: the Example block python -m ruff rule PLR5501 prints
def check_sign(value: int) -> None:
    if value > 0:
        print("Number is positive.")
    else:
        if value < 0:
            print("Number is negative.")
        else:
            print("Number is zero.")
