# A001 builtin-variable-shadowing: the Example block python -m ruff rule A001 prints
def find_max(list_of_lists):
    max = 0
    for flat_list in list_of_lists:
        for value in flat_list:
            max = max(max, value)  # TypeError: 'int' object is not callable
    return max
