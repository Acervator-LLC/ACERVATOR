# 2026-09-10 — Proof of Accumulation: the skill ladder and the transfer skill

Issue #147, unit 21. Files changed: `src/competition/skill_ladder.py` (new),
`src/gui/main_tabs/proof_of_accumulation_tab_surface.py`,
`src/gui/web/proof_of_accumulation_tab.js`,
`src/gui/web/proof_of_accumulation_tab.css` and
[docs/manual/08-tabs/proof-of-accumulation.md](../../docs/manual/08-tabs/proof-of-accumulation.md).
No test file was written.

Unit 1 built the Quintessence ledger with the bleed already in it. This unit
builds the ladder the bleed's level comes from, and the tab draws it.

Three runs drove the change, all under `python -X dev -X faulthandler` with
`PYTHONWARNINGS=error`. Two drove the ladder and a real transfer directly. The
third built the tab the way the main window builds it, through
`ProofOfAccumulationReactPanel`, and read the page back through its own
`runJavaScript`. `main.py` was never launched: it takes an instance lock in the
operator's live tree while he is trading.

Every path used was a throwaway. `USERPROFILE`, `HOME`, `HOMEDRIVE` and
`HOMEPATH` were redirected to a fresh temporary directory before the surface was
imported, and the run printed `Path.home()` and the surface's own `LEDGER_DIR` to
show where it had landed.

```
Path.home()          <temp>\U21_home_qu9b7vea
surface LEDGER_DIR   <temp>\U21_home_qu9b7vea\.acervator
ledger file          <temp>\U21_a6bkirzx\quintessence_ledger.json
```

Nothing under the real `~/.acervator` was read or written.

---

## 1 — The standing line printed "1 transfers recorded"

### 1.1 the error

No traceback. The page drew

```
Quintessence Transfer - level 0 - effect 1.0x - bleed -- - 1 transfers recorded
```

where the ledger holds one transfer.

### 1.2 reproduction

The panel was built for the live chain against a seeded ledger holding exactly
one transfer, and the drawn text was read back with the repository's own
`DRAWN_TEXT_JS`.

### 1.3 the cause

The sentence pasted a count into a fixed plural. Any participant with exactly one
transfer read wrongly. The same class was repaired on this tab once before, on
the wallet's movement count.

### 1.4 the correction

The count follows a label that does not change with the number.

```python
STANDING_TEXT = (
    "{name} - level {level} - effect {effect} - bleed {bleed} "
    "- transfers sent {uses}"
)
```

### 1.5 the rerun

```
live      transfers sent 1
testnet   transfers sent 3
```

---

## 2 — A missing ledger file read as a participant who had sent nothing

### 2.1 the error

No traceback. With the live ledger file deleted, the page drew

```
Quintessence Transfer - level 0 - effect 1.0x - bleed -- - transfers sent 0
```

### 2.2 reproduction

The live ledger file was unlinked and the panel was built again for the live
chain.

### 2.3 the cause

`QuintessenceLedger.load` returns itself when its file does not exist, so the
count came back as nought from an empty replay. Nought is also the true answer
for a participant who has sent nothing, and the two cases were indistinguishable
on screen.

### 2.4 the correction

An absent file answers None, and None prints two dashes.

```python
    path = chain_file(QUINT_LEDGER_NAME, chain)
    if not path.exists():
        return None
```

### 2.5 the rerun

```
live, file present   transfers sent 1
live, file removed   transfers sent --
```

---

## 3 — The docs archetype refused the manual page for a repeated heading

### 3.1 the error

```
structure:DOC005 line 2394 [high]: Duplicate heading text 'demo mode takes the
same path' (also appears at line 1671). Breaks TOC generation
```

`passed=False` on `docs/manual/08-tabs/proof-of-accumulation.md`.

### 3.2 reproduction

```
python -m dev_harness.harness.docs_archetype docs/manual/08-tabs/proof-of-accumulation.md
```

### 3.3 the cause

The new dated block reused the heading an earlier block on the same page already
carries, so two anchors on one page share a name.

### 3.4 the correction

The heading names what this block's demo run actually reads.

```
### Demo mode reads the other chain's ledger file
```

### 3.5 the rerun

```
passed=True, 170 findings, no high or critical, errors []
```

---

## 4 — Two new docstrings ran past the line length

### 4.1 the error

```
ruff medium line 224: Line too long (91 > 88)
ruff medium line 229: Line too long (92 > 88)
```

on `src/competition/skill_ladder.py`.

### 4.2 reproduction

```
python -m dev_harness.harness.coding_archetype src/competition/skill_ladder.py
```

### 4.3 the cause

Two one-line docstrings named every constant they referred to and ran past the
column the formatter holds.

### 4.4 the correction

Both say the same thing in fewer words.

```python
    """Return the bleed ``progress``'s level pays, gated by ``transfer_level``."""
    """Return the hours ``amount`` takes at ``level``, floored at one hour."""
```

### 4.5 the rerun

No length finding remains, on either file, in either lane.

```
python -m tools.local_ci --lane black    VERDICT: PASSED
python -m tools.local_ci --lane flake8   VERDICT: PASSED
```

---

## What the runs report

### The four decided numbers, as the program prints them

```
level   level_cost        cost_to_reach     effect   bleed
 1          1                 1              1.1     0.08
 2          2.5               3.5            1.2     0.07555555555555555555555555556
 3          6.25              9.75           1.3     0.07111111111111111111111111111
 4         15.625            25.375          1.4     0.06666666666666666666666666667
 5         39.0625           64.4375         1.5     0.06222222222222222222222222222
 6         97.65625         162.09375        1.6     0.05777777777777777777777777778
 7        244.140625        406.234375       1.7     0.05333333333333333333333333333
 8        610.3515625      1016.5859375      1.8     0.04888888888888888888888888889
 9       1525.87890625     2542.46484375     1.9     0.04444444444444444444444444444
10       3814.697265625    6357.162109375    2.0     0.04
```

Ten levels. Each level's cost is two and a half times the one below, exactly.
The effect rises a tenth a level, from 1.0 untrained to 2.0 at the cap.

### The 6,357 figure, and the one place the issue's table differs

The run that records perfect uses until the level stops rising reports what it
counted, and the ladder reports what it costs.

```
topped out: weighted_uses 6358.0   level 10   effect 2.0
cost_to_reach(10)                  6357.162109375
at quality 0.5: weighted_uses 6357.5   level 10
```

The exact sum of the ten level costs is 6,357.162109375, which rounds to the
6,357 the design names. Topping out at full quality takes 6,358 uses, because the
6,358th use is the one that crosses the line. No constant was adjusted to land
there.

The issue's own cumulative column carries rounding of its own and reads 6,356.7,
which is 0.462 below the exact geometric sum. Its level-5 and level-8 rows differ
the same way, by 0.2375 and 0.5859375. The per-level costs agree exactly and the
headline figure agrees at the rounding.

### A use of quality nought is refused

```
a use of quality 0.0 advances nothing; Quintessence Transfer stands at level 0
on 0 weighted uses

quality must be 0 to 1, got 1.5
quality must be int, float or Decimal, not bool
```

After all three refusals the run printed `weighted_uses 0`, so nothing was
recorded by a refused use.

### Where a use's quality reads from

Nowhere. The ledger records that a transfer happened and records no quality
beside it, so no use on this platform can be weighted today and the skill stands
at level 0 on every chain. The only nought-to-one quality the platform computes
is the trade grade in `src/trading/trade_grader.py`, which grades a trade rather
than a transfer; unit 10 owns it.

The one real figure the panel does read per chain is the count of transfers the
sender has made, which is the ledger's own record of a use having happened.

### Two real transfers, and the conservation law after each

```
level 1    bleed fraction 0.08   hours 10
           sent 100   received 92.00   bled 8.00   bled / sent 0.08
           wallets 992.00 + held 0 + platonic 8.00 == 1000 ever minted
           delta 0.00   is_balanced true   is_within_cap true   negatives 0

level 10   bleed fraction 0.04   hours 1
           sent 100   received 96.00   bled 4.00   bled / sent 0.04
           wallets 988.00 + held 0 + platonic 12.00 == 1000 ever minted
           delta 0.00   is_balanced true   is_within_cap true   negatives 0
```

The same ledger file replayed from disk reports the same three buckets and the
same zero delta. Nothing in this unit changed what the conservation law means or
how the ledger enforces it.

### The skill gate

```
Quintessence Transfer stands at level 0 on 0 weighted uses; level 1 costs 1
and no transfer runs below it
```

That sentence is the program's own refusal and it is what the panel prints while
the skill is untrained.

### The duration, the guild and the single slot

```
transfer_hours(1000, 1)    100
transfer_hours(1000, 10)    10
transfer_hours(5, 10)        1      the one-hour floor
```

The duration is set, from the decided formula: hours are the amount divided by
ten times the level, never below one hour. No guild, roster or membership record
exists anywhere in the platform, so the guild term has nothing to read. Nothing
keeps an in-flight record either, so no code serialises one transfer at a time.

### Constructed and reached

The tab was built the way the main window builds it, and the page reported on
itself. The drawn text carries the whole ladder.

```
panel.chain()              live            testnet
page_ready                 True            True
isLoaded                   True            True
faults                     []              []
declaredFields().length    18              18
indexOf("skills")          14              14
drawn text length          2195            2195
```

The drawn text, from the skill panel onward, on the live chain:

```
Skills
Quintessence Transfer - level 0 - effect 1.0x - bleed -- - transfers sent 1
Quintessence Transfer stands at level 0 on 0 weighted uses; level 1 costs 1
  and no transfer runs below it
L1  1.0 uses        1.0 to reach        1.1x effect   8.00% bleed
L2  2.5 uses        3.5 to reach        1.2x effect   7.56% bleed
L3  6.2 uses        9.8 to reach        1.3x effect   7.11% bleed
L4  15.6 uses       25.4 to reach       1.4x effect   6.67% bleed
L5  39.1 uses       64.4 to reach       1.5x effect   6.22% bleed
L6  97.7 uses       162.1 to reach      1.6x effect   5.78% bleed
L7  244.1 uses      406.2 to reach      1.7x effect   5.33% bleed
L8  610.4 uses      1016.6 to reach     1.8x effect   4.89% bleed
L9  1525.9 uses     2542.5 to reach     1.9x effect   4.44% bleed
L10 3814.7 uses     6357.2 to reach     2.0x effect   4.00% bleed
6357.2 quality-weighted uses reach level 10.
1000 Quint takes 100 hours at level 1 and 10 hours at level 10.
No field holds a use's quality, so no use is weighted and the skill stands at
  level 0.
No guild roster is built, so the guild term of a transfer reads nothing.
No in-flight record is kept, so nothing holds a transfer in a queue.
```

The page's field count is the control that its nought readings mean anything: it
reports 18 declared fields and no fault on every run, so `--` under a value is a
fact about that value.

### Demo mode

The chain rides in at construction, the same way the wallet takes it. Three arms
of one run, same module, same page, same panel class.

```
live                  transfers sent 1    quintessence_ledger.json
testnet               transfers sent 3    quintessence_ledger_testnet.json
live, file removed    transfers sent --   file absent
```

The three readings differ and the seeding explains each one: one transfer on the
live file, three on the demo file, no file at all in the third arm.

## The archetypes

Read from the `passed` field of each run's JSON, with `tool_availability`
checked. Every tool in every run reported ok, and every `errors` list was empty.

| file | archetype | passed |
| --- | --- | --- |
| `src/competition/skill_ladder.py` | coding, ta | true |
| `src/gui/main_tabs/proof_of_accumulation_tab_surface.py` | coding, ta, gui | true |
| `src/gui/web/proof_of_accumulation_tab.js` | coding, gui | true |
| `src/gui/web/proof_of_accumulation_tab.css` | gui | true |
| `docs/manual/08-tabs/proof-of-accumulation.md` | docs | true |
| `tests/debug_reports/2026-09-10_poa_skill_ladder.md` | docs | true |

The TA archetype reports `passed=True` with no finding at all on the new module,
which is the one carrying the cost curve, the effect curve and the bleed.

The instrument was proved on the fixtures before any of the above.

```
known_good.py   exit 0
known_bad.py    exit 1
```

## What the skill system does not reach

No control on the panel starts a transfer. Only one skill exists, and the rest of
the tree, the alignment each skill carries and the abilities along the level arc
are later work.

No store holds a participant's weighted uses, so a level cannot survive a
restart. Nothing supplies a use's quality, so no level can rise.
