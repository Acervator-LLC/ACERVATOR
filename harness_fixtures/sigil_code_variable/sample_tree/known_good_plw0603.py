# PLW0603 global-statement: the Use instead block python -m ruff rule PLW0603 prints
var = 1


def foo():
    var = 10
    print(var)
    return var


var = foo()
print(var)
