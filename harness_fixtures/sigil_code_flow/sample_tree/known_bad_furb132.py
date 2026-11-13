# FURB132 check-and-remove-from-set: the Example block python -m ruff rule FURB132 prints
nums = {123, 456}

if 123 in nums:
    nums.remove(123)
