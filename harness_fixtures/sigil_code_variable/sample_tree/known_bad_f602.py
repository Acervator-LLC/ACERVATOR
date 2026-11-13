# F602 multi-value-repeated-key-variable: the lines above the Example block python -m ruff rule F602 prints define its free names
bar, baz = "bar", "baz"
foo = {
    bar: 1,
    baz: 2,
    baz: 3,
}
foo[baz]  # 3
