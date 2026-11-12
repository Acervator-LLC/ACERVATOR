def first(x: list[int]) -> int:
    return x[0] if x else 0

t = (5, 4)
# Error: Argument 1 to "first" has incompatible type "tuple[int, int]";
#        expected "list[int]"  [arg-type]
print(first(t))
