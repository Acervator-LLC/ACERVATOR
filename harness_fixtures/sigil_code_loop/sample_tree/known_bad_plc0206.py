# PLC0206 dict-index-missing-items: the Example block python -m ruff rule PLC0206 prints
ORCHESTRA = {
    "violin": "strings",
    "oboe": "woodwind",
    "tuba": "brass",
    "gong": "percussion",
}

for instrument in ORCHESTRA:
    print(f"{instrument}: {ORCHESTRA[instrument]}")
