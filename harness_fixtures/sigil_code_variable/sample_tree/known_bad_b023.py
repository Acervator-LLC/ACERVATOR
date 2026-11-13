# B023 function-uses-loop-variable: the Example block python -m ruff rule B023 prints
adders = [lambda x: x + i for i in range(3)]
values = [adder(1) for adder in adders]  # [3, 3, 3]
