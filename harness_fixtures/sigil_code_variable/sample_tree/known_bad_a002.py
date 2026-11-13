# A002 builtin-argument-shadowing: the Example block python -m ruff rule A002 prints
def remove_duplicates(list, list2):
    result = set()
    for value in list:
        result.add(value)
    for value in list2:
        result.add(value)
    return list(result)  # TypeError: 'list' object is not callable
