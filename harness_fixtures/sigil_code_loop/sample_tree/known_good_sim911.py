# SIM911 zip-dict-keys-and-values: the Use instead block python -m ruff rule SIM911 prints
flag_stars = {"USA": 50, "Slovenia": 3, "Panama": 2, "Australia": 6}

for country, stars in flag_stars.items():
    print(f"{country}'s flag has {stars} stars.")
