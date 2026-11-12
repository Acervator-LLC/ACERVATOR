# SIM911 zip-dict-keys-and-values: the Example block python -m ruff rule SIM911 prints
flag_stars = {"USA": 50, "Slovenia": 3, "Panama": 2, "Australia": 6}

for country, stars in zip(flag_stars.keys(), flag_stars.values()):
    print(f"{country}'s flag has {stars} stars.")
