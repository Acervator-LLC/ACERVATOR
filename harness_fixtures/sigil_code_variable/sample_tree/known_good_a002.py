# A002 builtin-argument-shadowing: the Use instead block python -m ruff rule A002 prints
def remove_duplicates(list1, list2):
    result = set()
    for value in list1:
        result.add(value)
    for value in list2:
        result.add(value)
    return list(result)
