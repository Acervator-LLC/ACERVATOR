# PLW0603 global-statement: the Example block python -m ruff rule PLW0603 prints
var = 1


def foo():
    global var  # [global-statement]
    var = 10
    print(var)


foo()
print(var)
