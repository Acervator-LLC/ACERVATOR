# 2026-09-10 - #147 unit 34 - the fourth bucket in the conservation law

Two program errors were raised and corrected while the four-bucket law was built.
Both were reproduced by running the real code, not by reading it.

## Error 1 - the conservation guard did not exist

### The error: a guard that was called and never written

```
scaffolding:S003 line 360 [high]: self._require_embedded referenced in
QuintessenceLedger method but not assigned in __init__.
dev_harness.harness.coding_archetype on quintessence_ledger.py: passed=False
(92 findings) severity: high=2
```

### Reproduction: the coding archetype on the ledger

```
python -m dev_harness.harness.coding_archetype src/competition/quintessence_ledger.py
```

The four new movement methods were written before the guard they call.

### The cause: two methods reached a name that was never bound

`QuintessenceLedger.release_from_embedded` and `release_all_to_platonic` both call
`self._require_embedded`, which did not exist. Python would have raised
`AttributeError` on the first release.

### The correction: the guard beside its two siblings

`_require_embedded` was added beside `_require_balance` and `_require_held`, with
the same shape: it raises `ValueError` naming what the bucket holds and what was
asked for.

```python
def _require_embedded(self, amount: Decimal) -> None:
    """Raise ValueError when the embedded bucket holds less than ``amount``."""
    if amount > self._embedded:
        raise ValueError(
            f"the embedded bucket holds {self._embedded}, cannot release {amount}"
        )
```

### The rerun: both archetypes on the ledger

```
coding_archetype src/competition/quintessence_ledger.py   passed=True
ta_archetype     src/competition/quintessence_ledger.py   passed=True
```

Driven afterwards, the refusal reports:

```
the embedded bucket holds 0E-9, cannot release 1E-8
```

## Error 2 - a counting check reported a path no sequence reached

### The error: one of sixteen checks failed on an absence

```
[FAIL: no craft was attempted] invariant_everyCraftMovesEveryUnitItSpends
QuintessenceConservationTest invariants: 1/16 invariants broken
Suite result: FAILED. 0 passed; 1 failed; 0 skipped
```

Fifteen of the sixteen checks passed in the same run.

### Reproduction: the chain checks on one starting number

```
forge test --match-contract QuintessenceConservationTest --fuzz-seed 1
```

Reproduced on every seed, because the cause is in the set-up and not in the
campaign.

### The cause: the actor had already transferred its balance away

The set-up drives each path once so that every attempt counter is above zero
before the campaign starts. It called the wallet embed on actor 0. Two calls
earlier, the early-execution attempt had authorised a transfer of that actor's
whole balance and the execution had gone through, so actor 0 held nothing. The
handler wrapper reads the balance first and returns early when it is zero, so the
movement never ran and the counter stayed at zero.

The check was right and the set-up was wrong. This is the attempt counter doing
its job: a path nothing reached fails instead of passing on an absence.

### The correction: the call moved to the actor that holds the units

```solidity
handler.embedFromWallet(1, ORE_HIGH - 1, ORE_EMBEDDED_FROM_WALLET);
```

### The rerun: the chain checks on forty starting numbers

```
forge test --match-contract QuintessenceConservationTest --fuzz-seed 1
Suite result: ok. 1 passed; 0 failed; 0 skipped
40 seeds, 256 runs each, 16,384 calls each: 40 of 40 pass
```

## What the instruments were shown able to report

Each verdict surface was observed going red before any green was trusted.

### The sixteen chain checks

Twelve breakages were put into `contracts/Quintessence.sol` one at a time. Every
one of the sixteen checks was observed failing at least once. After each, the file
compared identical to the byte against
`ee07368b30a29100ddeb560d31086564c9f1d79d64a566ce162f137a318d6bf9`.

```
the platonic draw credits nothing        four buckets, nothing destroyed, the draw check
the fourth bucket set above the total    the fourth bucket within the total
the wallet embed drops its remainder     the wallet embed check
the release drops its remainder          the release check
the full release destroys the units      the full release check, nothing destroyed
the full release lowers the total        the total never falls, no movement mints
the cap guard made unconditional         the cap, and a mint past the cap refused
the spend drops its wallet total         the wallet total equals the balances
the registry guard made unconditional    only the registry moves units
the duration guard made unconditional    a transfer refused before it is due
the bleed step raised to seven hundred   every transfer bleeds four per cent or more
three transfer guards made unconditional the registry cannot move an unauthorised wallet
```

### The ore-scale figures

Changing the expected platonic gain from 33,000,000,000 to 33,000,000,001 - one
part in a million million million - fails the run:

```
[FAIL: setUp: the ore-scale movements did not balance to 0.000000033 in the
platonic] setUp() (gas: 0)
```

### The ledger's own report

The old three-bucket sum was computed over the same state the four-bucket sum
balances:

```
four-bucket delta    0
three-bucket delta   -0.00000004, short by exactly what is embedded
```

Zeroing the fourth bucket, inflating it by one ore unit, and making it negative
were each refused. Restoring it returned a report equal to the one before the
three changes.

### The named analyzers

```
forge 1.8.1      16 checks red on 12 breakages, 40 of 40 seeds green
slither 0.11.6   known_bad reports reentrancy-eth, known_good does not
solhint 6.2.4    known_bad exit 1, known_good exit 0
semgrep 1.171.0  known_bad reports unrestricted-transferownership, known_good nothing
```

slither exits 127 on this host whatever it finds, so its finding list is the
verdict and its exit code is not. semgrep exits 0 either way for the same reason.

### The archetypes

```
coding_archetype  known_good.py        passed=True    known_bad.py        passed=False
ta_archetype      known_good_ta001.py  passed=True    known_bad_ta001.py  passed=False
docs_archetype    known_good.md        passed=True    known_bad.md        passed=False
```

## Paths used

Every run wrote only under the session scratchpad. The real runtime tree was read
and never written.

```
U34_ledger_scratch/U34_quintessence_ledger.json
U34_ledger_scratch/U34_control_ledger.json
U34_install_scratch/quintessence_ledger_testnet.json
U34_install_scratch/U34_testnet_chain_copy.json
```

Before and after the install run, every file in the real runtime directory had the
same size and the same modification time. The chain file read 4,059,629 bytes and
sha256 `f84458bc69c8e894794836b8658be7518cb6e108e78861cd9769f12fe25988be` on both
sides, on the copy and on the original. `SCHEMA_VERSION` read 1 out of the running
module and was not changed.
