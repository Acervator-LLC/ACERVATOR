a = {'x': 1, 'y': 2}

a['x']  # OK

# Error: Invalid index type "int" for "dict[str, int]"; expected type "str"  [index]
print(a[1])

# Error: Invalid index type "bytes" for "dict[str, int]"; expected type "str"  [index]
a[b'x'] = 4
