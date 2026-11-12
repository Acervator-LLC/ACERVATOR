# F601 multi-value-repeated-key-literal: the Example block python -m ruff rule F601 prints
foo = {
    "bar": 1,
    "baz": 2,
    "baz": 3,
}
foo["baz"]  # 3
