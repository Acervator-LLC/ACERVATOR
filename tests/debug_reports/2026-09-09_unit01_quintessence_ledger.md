# The Quintessence ledger and its debit path

## What the package carried before this unit

Two measurements, taken on the unmodified tree.

```
wc -l src/competition/token_ledger.py
  235 src/competition/token_ledger.py

grep -n "^\s*def " src/competition/token_ledger.py
  to_dict  from_dict  __init__  award  balance  awards  total_minted
  remaining_ever  season_minted  leaderboard  supply_summary  save  load
  _event_id

grep -rniE "\bdef (debit|spend|deduct|withdraw|transfer)" src/competition/ | wc -l
  0

grep -rni "quintessence\|quint" src/ | wc -l
  0
```

The second number is zero, so the instrument needs a control. The same command
over two words the tree does carry returns a count, so it can report when there
is something to find.

```
grep -rni "tokenledger" src/ | wc -l
  18
grep -rni "despawn" src/ | wc -l
  293
```

Both measurements in the work order hold. The award-only surface is exactly the
eleven methods above plus the two record helpers, and the word Quintessence
appeared nowhere under `src/`.

## Where the ledger went, and why not in the existing one

`src/competition/quintessence_ledger.py` is new. The existing ledger stays
untouched.

The two assets obey opposite rules, and the existing module says so about
itself.

`src/competition/token_ledger.py` — its own header

```python
Hard cap: 10,000,000 ACRV.  Once minted, tokens cannot be destroyed.
...
There is no "edit balance" operation — only "award tokens".
```

Its record type carries a competition tier, a tier emoji, a Merkle root and a
percentile rank, and it reads its cap and its tier table from the season
schedule. None of those describes Quintessence, which has a different cap, a
different origin, and a balance that falls. Putting a debit on that class would
contradict the sentence above in the same file.

## Errors detected

**No program error from the ledger.** The lifecycle below ran under development
mode with warnings promoted to errors and finished with exit code 0. A warning
would have become a traceback. None appeared.

```
PYTHONWARNINGS=error python -X dev -X faulthandler <driver>
RUN_EXIT=0
```

**One fault the coding archetype found, and the correction.** The first form of
the install helper logged a failed load with the phrase `load failed`.

```
scaffolding S001 medium src/gui/shared_testnet.py:170
  fallback string 'load failed' passed to error(...) - verify the operation
  was actually attempted before reporting failure
```

The rule asks for proof that the operation ran before a message claims it
failed. The message now names what the program observed instead of asserting a
failure, and it reports through the channel that carries the traceback.

`src/gui/shared_testnet.py` — the corrected handler

```python
        except (QuintessenceLedgerError, OSError):
            logger.exception(
                "QuintessenceLedger at %s raised while replaying its movements",
                ledger_path or "default",
            )
```

The finding is gone and the file reports `passed=True` with no scaffolding
finding.

**One instrument could not run, and it reported exit 0 while doing so.** The
touch-set baseline tool reuses the gate's routing table, which lives under the
untracked hooks directory, so it measures nothing inside a fresh worktree.

```
python -m dev_harness.touchset baseline <files> --pin <file>
  REFUSED: no routing rule at <worktree>/.claude/hooks/archetype_gate.py
  This module reuses the gate's routing rather than copying it,
  so with no rule to reuse it measures nothing. Nothing written.
EXIT=0
```

A refusal that exits 0 reads the same as a pass to anything checking the exit
code. The file belongs to the harness, so this unit changed nothing there and
recorded it instead. The baseline came from running each archetype directly on
the unmodified files.

## Reachability

**Constructed.** `SharedTestnetBridge.install_on` builds the ledger and attaches
it to the window, beside the local chain it already built. That method runs from
`MainWindow._setup_ui` at `src/gui/main_window.py:277`, with no condition around
it, so every launch builds one.

`src/gui/shared_testnet.py` — the construction

```python
        main_win._quint_ledger = cls.install_quint_ledger(quint_ledger_path)
```

What the program reports when it does so, with the chain bridge's own line
beside it for comparison:

```
LOG acervator.shared_testnet INFO QuintessenceLedger installed
    (path=<tmp>/quintessence_ledger.json, ever minted=0, balanced=True)
LOG acervator.shared_testnet INFO SharedTestnetBridge installed
    (persist=<tmp>/testnet_chain.json)
```

**Reached, for two methods.** `install_quint_ledger` calls `load` and
`conservation` on every launch. That is the whole of what a real caller reaches
today.

**Not reached: the debit path.** Nothing in the running program calls distil,
spend, transfer or respawn. Unit 7, the certified transaction socket, is where
distil gets its first caller. Unit 13 calls spend for the per-action Elite
charge, and Unit 15, the Quint Wallet, is the first screen to read a balance.

The run below reaches the debit path directly, because the entry point cannot be
launched while the operator is trading: the instance guard in `main.py` writes
into the live process's state directory.

## The lifecycle run

Four operations, each followed by the ledger's own conservation report. Every
figure below is what the program printed.

```
=== CONSTRUCTED: SharedTestnetBridge.install_on ===
   win._quint_ledger is QuintessenceLedger
   supply_summary: {"wallets_total": "0", "held_total": "0",
     "platonic_total": "0", "total_ever_minted": "0",
     "supply_cap": "33000000", "delta": "0", "is_balanced": true,
     "is_within_cap": true, "negative_buckets": 0,
     "remaining_ever": "33000000", "wallet_count": 0, "held_count": 0,
     "movement_count": 0}
```

```
   distil returned 1020.00
--- after distil alice fee 1200 grade 0.85
   wallets 1020.00 + held 0 + platonic 0 == 1020.00 ever minted, delta 0.00
```

```
   spend returned 200
   held_balance(event:elite-1) = 200
--- after spend alice 200 to event:elite-1
   wallets 820.00 + held 200 + platonic 0 == 1020.00 ever minted, delta 0.00
```

```
   transfer sent/received/bled: 500 460.00 40.00
   platonic_balance = 40.00
--- after transfer alice->bob 500 at skill 1
   wallets 780.00 + held 200 + platonic 40.00 == 1020.00 ever minted, delta 0.00
```

```
   respawn returned 40.00
--- after respawn platonic -> carol
   wallets 820.00 + held 200 + platonic 0.00 == 1020.00 ever minted, delta 0.00
   balances: 320.00 460.00 40.00
```

Nothing was minted after the first step, and the total stayed at 1020.00 through
a spend, a transfer and a respawn. The three buckets moved and their sum did not.

The file the run wrote replays to the same state.

```
=== RELOAD FROM THE FILE THE PROGRAM WROTE ===
   wallets 820.00 + held 200 + platonic 0.00 == 1020.00 ever minted, delta 0.00
   is_balanced true
```

The bleed at skill level one took 40.00 from 500, which is the recorded eight per
cent. Across the ten levels the fraction falls linearly to four per cent.

```
   level  1: 0.08
   level  5: 0.06222222222222222222222222222
   level 10: 0.04
```

## The three controls

Each one breaks the books, shows the report naming the breach, shows the write
path refusing the next operation, then restores and shows the report clean
again.

**Control 1 — credit a wallet with nothing minted.**

```
--- broken: alice credited 5, nothing minted
   wallets 825.00 + held 200 + platonic 0.00 against 1020.00 ever minted
   delta 5.00   is_balanced false
   write path refused: conservation broken: wallets 826.00 + held 200 +
     platonic 0.00 against 1021.00 ever minted, delta 5.00,
     0 negative bucket(s)
--- restored
   delta 0.00   is_balanced true
```

**Control 2 — destroy a unit.**

```
--- broken: one unit removed from bob
   wallets 819.00 + held 200 + platonic 0.00 against 1020.00 ever minted
   delta -1.00   is_balanced false
   write path refused: conservation broken: wallets 820.00 + held 200 +
     platonic 0.00 against 1021.00 ever minted, delta -1.00,
     0 negative bucket(s)
--- restored
   delta 0.00   is_balanced true
```

The refusal message in both controls reports a total one higher than the report
above it, because the attempted mint applied before the check ran. The write path
then rolled the attempt back, which is why the restored figures return to the
pre-control total rather than carrying the refused mint.

**Control 3 — mint past the cap.**

```
   remaining_ever = 32998980.00
   cap refused: Supply cap 33,000,000 Quintessence would be exceeded.
     Only 32998980.00 remain mintable.
--- after the refusal
   delta 0.00   is_balanced true   total_ever_minted 1020.00
   a legal mint of 10: 10
--- restored
   delta 0.00   is_balanced true   total_ever_minted 1030.00
```

**A fourth, on the file rather than on memory.** Rewriting the recorded total in
the saved file makes the load raise, and the ledger then refuses every write
rather than overwriting the file it could not read.

```
QuintessenceLedgerError: <tmp>/quintessence_ledger.json records 999999 ever
  minted, its movements replay to 1030.00
write refused after a failed load: <tmp>/quintessence_ledger.json failed to
  load; refusing to write over it
```

## The closed accepted-input set

Every amount the ledger takes goes through one gate, and the gate was driven over
its whole type and value domain. Three types are accepted and nothing else is.

```
int 10                      ACCEPTED
float 10.5                  ACCEPTED
Decimal('10.5')             ACCEPTED
Decimal('-0.0')             ACCEPTED as zero
int 0                       ACCEPTED as zero

bool True                   REFUSED TypeError  must be int, float or Decimal
str '10'                    REFUSED TypeError
None                        REFUSED TypeError
complex 1+0j                REFUSED TypeError
Fraction(1,2)               REFUSED TypeError
float subclass 10.0         REFUSED TypeError
object with __float__       REFUSED TypeError
float nan                   REFUSED ValueError  must be finite
float inf                   REFUSED ValueError
Decimal NaN                 REFUSED ValueError
Decimal Infinity            REFUSED ValueError
int -1                      REFUSED ValueError  must not be negative
```

The grade, the address and the skill level each have their own closed set.

```
grade 1            ACCEPTED        grade 1.0001   REFUSED  must be 0 to 1
'alice'            ACCEPTED        ''             REFUSED  non-empty string
                                   '   '          REFUSED
                                   None, 123, b'alice'     REFUSED
skill level 1, 10  ACCEPTED        0, 11          REFUSED  must be 1 to 10
                                   1.0, True, '1', Decimal(1)  REFUSED TypeError
```

The bounds on a balance and on the platonic refuse the same way.

```
spend 101 of 100                REFUSED  alice holds 100, cannot move 101
respawn 1 from an empty platonic REFUSED  the platonic holds 0
transfer alice -> alice          REFUSED  sender and recipient must differ
```

Two guards on the file itself came out of reading the module adversarially after
it worked. Replaying a file twice into one ledger would double every balance, and
reading a file written by a later format would silently misread it. Both now
refuse, and a ledger that failed to load refuses every write rather than
overwriting the file it could not read.

```
second load on the same object    REFUSED  already loaded; a second replay
                                           would double it
load a version this build cannot  REFUSED  is version 99, this build reads
                                           version 1
write after that failed load      REFUSED  failed to load; refusing to write
                                           over it
absent file loads to              0
```

**One bound that is recorded rather than fixed.** Decimal addition carries 28
significant digits. A mint small enough relative to the running total would round
the total while the wallet took the full amount, and the conservation check would
then refuse the write and roll it back. It cannot be reached from a fee in
dollars: the cap has eight integer digits, so an amount would need more than
twenty decimal places to reach it.

## The franchise invariant is not in this unit

The issue states where both invariants belong.

```
Two invariants, and both belong to the contracts work.
wallets + held addresses + the platonic == total ever distilled <= 33,000,000
franchise level >= current balance, for every address, always
```

This unit holds the first. The second needs a franchise level, which is a
governance quantity the contracts work carries, and Unit 6 is the Quintessence
contract.

The seam left for it is the absence of a mechanism. The ledger exposes a balance
to compare a franchise level against, and it carries no method that could move
Quintessence during a dormancy resynchronization. A decay therefore cannot move
anything through this ledger, which is the prohibition stated as structure rather
than as a rule someone has to remember.

## Numbers read from the decisions, and numbers still missing

Read and used.

| Number | Value |
| ------ | ----- |
| Supply cap | 33,000,000, total ever distilled |
| Distil rate | one Quintessence for one dollar of certified exchange fee |
| Grade curve | the trade's grade multiplies the award, zero to one |
| Bleed at level one | 8% |
| Bleed at level ten | 4%, falling linearly from level one |
| Skill levels | ten |

Recorded, and belonging to other units, so this unit uses none of them: the five
per cent share ceiling, five markets of twenty per window, the three-candle
cooldown, the transfer duration and its single slot, the skill cost multiplier,
the five action-budget bands, the two trophy lifetime caps, and the three
franchise timings.

**Missing, and not invented.** No decision records the smallest unit of
Quintessence, or how many decimal places it carries. The ledger therefore keeps
every amount as an exact decimal and rounds nothing, and every split derives its
remainder by subtraction, so the sum stays exact at whatever precision a caller
supplies. A later decision that fixes a decimal place can quantize on the way
in without changing the conservation law.

## Verdicts

| File | Archetype | passed |
| ---- | --------- | ------ |
| `src/competition/quintessence_ledger.py` | coding | true |
| `src/competition/quintessence_ledger.py` | ta | true |
| `src/gui/shared_testnet.py` | coding | true |
| `src/gui/shared_testnet.py` | ta | true |
| `src/gui/shared_testnet.py` | gui | true |
| `src/competition/__init__.py` | coding | true |
| `docs/manual/08-tabs/proof-of-accumulation.md` | docs | true |

Every tool in every run reported available. The fixture pair was driven once
before any of them: the known-good file exits 0 with `passed=true`, the known-bad
file exits 1 with `passed=false`.

Counts against the baseline taken on the unmodified files. The new module has no
baseline because it did not exist.

| File | Baseline | After |
| ---- | -------: | ----: |
| `src/gui/shared_testnet.py` | 85, zero high | 90, zero high |
| `src/competition/__init__.py` | 7 | 7 |
| `docs/manual/08-tabs/proof-of-accumulation.md` | 20 | 20 |

The five added findings on the bridge are all low, and each is a pattern that
file already uses: two deferred imports, one private attribute set on the window,
and two optional annotations in the spelling the rest of the file uses. The
fifth is the dead-code tool naming the new attribute unread, which is true and is
the reachability statement above.

Both lint lanes report `VERDICT: PASSED`.

## What the operator sees differently

Nothing on screen. No panel draws a Quintessence balance, and no trade certifies,
so every launch builds an empty ledger and logs that it balances at zero.
