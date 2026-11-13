# A001 builtin-variable-shadowing: the Use instead block python -m ruff rule A001 prints
def find_max(list_of_lists):
    result = 0
    for flat_list in list_of_lists:
        for value in flat_list:
            result = max(result, value)
    return result
