import functools
import operator

nums = [1, 2, 3]
total = functools.reduce(operator.add, nums)
