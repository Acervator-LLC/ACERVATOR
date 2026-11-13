# RUF007 zip-instead-of-pairwise: the Example block python -m ruff rule RUF007 prints
letters = "ABCD"
zip(letters, letters[1:])  # ("A", "B"), ("B", "C"), ("C", "D")
