# B023 function-uses-loop-variable: the Use instead block python -m ruff rule B023 prints
adders = [lambda x, i=i: x + i for i in range(3)]
values = [adder(1) for adder in adders]  # [1, 2, 3]
from functools import partial

adders = [partial(lambda x, i: x + i, i=i) for i in range(3)]
values = [adder(1) for adder in adders]  # [1, 2, 3]
