# PLC0206 dict-index-missing-items: the Use instead block python -m ruff rule PLC0206 prints
ORCHESTRA = {
    "violin": "strings",
    "oboe": "woodwind",
    "tuba": "brass",
    "gong": "percussion",
}

for instrument, section in ORCHESTRA.items():
    print(f"{instrument}: {section}")
