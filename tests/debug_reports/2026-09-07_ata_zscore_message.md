# ATA-SMP: the sentence the Z-Score post writes

The arithmetic is already shared. `src/trading/indicators/zscore.py` is reached
by ATA-SMP through `VotingEngine.compute_all`, so the upgrade needed no copy.
What is local to ATA-SMP is the wording, and the wording still named one field.

Every run used a throwaway home. `~/.acervator/settings.json` hashed the same
before and after:

```
before  f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
after   f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
```

## The error

The Z-Score entry named one detail key. The upgraded indicator publishes
fourteen, two of them prices. A post therefore reported a score with no scale
to read it against, and read identically on a market costing three millionths
of a dollar and on a market costing four thousand.

`src/trading/ata_spm.py` — the entry before

```python
"zscore": ("Z-Score", ("z",), "z-score {value:+.3f}"),
```

## Reproduction

Three hundred bars around a base price, with a two-bar excursion every
thirty-seven alternating in sign so peaks and troughs both pass the minimum
score, and volume on its own cycle so the smoothing weights unequal bars. The
last three bars fall five per cent, which is what makes the Z-Score vote the
consensus direction and so reach the post at all. The same tape runs at BONK's
live scale and at a four-figure price.

The message is read back through the chain ATA-SMP itself uses:
`VotingEngine.compute_all`, then `build_vote`, then `confirming_signals`, then
`indicator_message`. Nothing is formatted by hand.

## The readings

| scale | message |
| --- | --- |
| BONK 3.1e-06, before | `Z-Score: z-score -2.697. Votes bullish at 25% confidence.` |
| four-figure, before | `Z-Score: z-score -2.697. Votes bullish at 25% confidence.` |
| BONK 3.1e-06, after | `Z-Score: z-score -2.697, predictive zone 2.87885e-06 to 3.31141e-06. Votes bullish at 25% confidence.` |
| four-figure, after | `Z-Score: z-score -2.697, predictive zone 3803.8 to 4375.34. Votes bullish at 25% confidence.` |

The two rows before the change are the same string. The two rows after it differ
by nine orders of magnitude, which is the price scale the post now carries.

## The correction

The entry names the score and the two zone prices, in the shape the two other
multi-key entries use: named keys, no positional binding.

`src/trading/ata_spm.py` — the entry after

```python
"zscore": (
    "Z-Score",
    ("z", "support_price", "resistance_price"),
    "z-score {z:+.3f}, predictive zone {support_price:g} to {resistance_price:g}",
),
```

`resistance_price` and `support_price` are the published second formula's
output, the mean plus each target score times the deviation. The wording states
them and asserts nothing else. It does not say the price sits inside or outside
the zone: `in_resistance` and `in_support` compare the volume-weighted smoothed
score, not the close, so a claim about the close would be a claim the arithmetic
does not give.

`:g` is the spelling this file already uses for a price, in
`CHART_LINE_FORMAT` and `BAND_LINE_FORMAT`.

## The new wording is reached, and by the object the engine built

Broken twice in one run, once inside `VotingEngine.compute_all` where the Signal
is appended, and once inside `indicator_message` where the sentence is built.
The object identity is the same at both stops, so the sentence is written from
the reading the engine produced and not from a second one.

```
python -m pdb \
  -c "b <repo>/src/trading/ta_engine.py:248, sig.indicator == 'zscore'" \
  -c "b <repo>/src/trading/ata_spm.py:730" -c c -c c -c where ... <script>
```

BONK scale, the two stops:

```
> src/trading/ta_engine.py(248)compute_all()
-> signals.append(sig)
('zscore', 1409070783600)
(2.8788534263185648e-06, 3.3114132415560172e-06)

> src/trading/ata_spm.py(730)indicator_message()
-> message=written.format(
('zscore', 1409070783600)
{'z': -2.697, 'support_price': 2.8788534263185648e-06,
 'resistance_price': 3.3114132415560172e-06}
'Z-Score: z-score -2.697, predictive zone 2.87885e-06 to 3.31141e-06.
 Votes bullish at 25% confidence.'
```

Four-figure price, the same two stops:

```
> src/trading/ata_spm.py(730)indicator_message()
('zscore', 1537307173968)
{'z': -2.697, 'support_price': 3803.8011723228524,
 'resistance_price': 4375.338270133369}
'Z-Score: z-score -2.697, predictive zone 3803.8 to 4375.34.
 Votes bullish at 25% confidence.'
```

## The no-reading text cannot fire

`reading_values` answers None while any named key is missing, and the whole
sentence then reads `no reading published`. Both zone prices are set on every
reading the indicator publishes, because each target score falls back to the
reversal threshold when no turning point has been remembered. Read back at both
scales, the dictionary carries all three keys:

```
{'z': -2.697, 'support_price': 2.8788534263185648e-06,
 'resistance_price': 3.3114132415560172e-06}
{'z': -2.697, 'support_price': 3803.8011723228524,
 'resistance_price': 4375.338270133369}
```

## No decision can move

`READINGS` is read in one place, `indicator_message`, which builds a sentence
and returns it. It reaches no vote, no gate and no order.

```
grep -n "READINGS" src/trading/ata_spm.py
108:READINGS: dict[str, tuple[str, tuple, str]] = {
714:    label, keys, reading_format = READINGS.get(name, (name, (), ""))
```

## Checks run

```
python -m dev_harness.harness.coding_archetype  src/trading/ata_spm.py       passed=True
python -m dev_harness.harness.ta_archetype      src/trading/ata_spm.py       passed=True
python -m dev_harness.harness.docs_archetype    docs/manual/08-tabs.md       passed=True
python -m dev_harness.harness.docs_archetype    this report                  passed=True
```

## The manual

`docs/manual/08-tabs.md` gains thirty-one lines and loses none. Every existing
sentence stands byte for byte, and the file holds the LF line endings it
started with.
