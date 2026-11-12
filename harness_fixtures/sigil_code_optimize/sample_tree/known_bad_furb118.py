import functools

nums = [1, 2, 3]
total = functools.reduce(lambda x, y: x + y, nums)
