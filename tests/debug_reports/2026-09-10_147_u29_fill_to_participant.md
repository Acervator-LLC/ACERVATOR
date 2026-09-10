# `src/competition/event_redistribution.py`, `src/competition/action_spend.py`

A certified fill's grade now reaches the participant's event record the
redistribution divides on. Every run below used `python -X dev -X faulthandler`
with `PYTHONWARNINGS=error`.

No pytest file names any symbol this unit changed. The whole Python suite under
`tests/` is one `conftest.py`, so no pytest ran.

## The shared reproduction

```
cd <worktree>
PYTHONPATH=<worktree> PYTHONWARNINGS=error QT_QPA_PLATFORM=offscreen \
  python -X dev -X faulthandler <scratch>/U29_drive_fill_to_participant.py <scratch>/U29_run
```

The run reaches `SharedTestnetBridge.install_quint_ledger`,
`install_certification_socket`, `install_action_spend` and
`install_event_redistribution` directly, then `SharedTestnetBridge.install_on` for
all nine objects. `main.py` never runs: `main.py:812` takes an instance lock under
`~/.acervator`, which is the live process's own tree. Every path the run writes sits
under the scratch directory.

It reads the operator's fills through `src/trading/live_log_reader.py` `live_trades`,
grades each one through `src/exchange/history_read_contract.py` `graded_row`,
certifies them through `CertificationSocket.certify`, and joins each receipt through
`EventRedistribution.record_certified_fill`.

Two inputs are supplied rather than measured, and both are named.

```
the per-fill venue fee   1.0 USD. All 1,709 fills on disk carry a fee of 0, so
                         nothing would mint and no participant could spend
the capture bounds       absent. Opening a market pool needs a live market scout,
                         which unit 9 owns; the socket is built with no bounds,
                         the documented path on which every fill is awarded
```

## The instruments, proved before the verdicts

```
coding_archetype  known_good.py  exit 0  passed=True   11 tools ok
coding_archetype  known_bad.py   exit 1  passed=False
ta_archetype      known_good_ta001.py / ta010  exit 0  passed=True   3 tools ok
ta_archetype      known_bad_ta001.py  / ta010  exit 1  passed=False
docs_archetype    known_good.md  exit 0  passed=True   7 tools ok
docs_archetype    known_bad.md   exit 1  passed=False
```

The first attempt pointed the TA archetype at `harness_fixtures/ta_archetype/known_good.py`,
which does not exist. It answered `passed=False` with `tool_availability` empty and
`errors` naming the missing target. A verdict with no tool in it is not a verdict;
the real fixtures carry rule suffixes.

The date-order rule was proved the same way. Restamping this unit's manual block one
hour earlier, in a copy, turns the page red.

```
updates [high] line 4147: the update stamped 2026-09-10 09:53 follows the one
stamped 2026-09-10 10:07 at line 4015. Updates under a tab run forward.
```

## Error 1, the error — a private member held the one definition of an address

The participant's ledger address has exactly one definition in the tree,
`certification_socket.py:624`, and another unit holds that file. One call to it
from this unit's own module drew a finding.

```
low | ruff | Private member accessed: `_wallet_for`
```

## Error 1, reproduction

```
python -m dev_harness.harness.coding_archetype <scratch>/U29_premortem_private_access.py
```

## Error 1, the cause

Copying `f"0x{bot_id[:40]}"` into this unit's own module would make a second spelling
of a wallet address, which is how a payout and a mint end in different wallets.
Calling the private member avoids the copy and draws the finding above.

## Error 1, the correction

Neither. The address is read back off the chain. `_post_commitment` always sends the
certification from that address, so the transaction's own sender is the value the
mint used, with no second spelling and no private access.

```python
    tx_hash = _as_name(getattr(receipt, "tx_hash", None), "tx_hash")
    transaction = testnet.chain.get_tx(tx_hash)
    if transaction is None:
        not_on_chain = (
            f"transaction {tx_hash[:16]} is not on this chain, so the fill names "
            f"no participant"
        )
        raise RedistributionError(not_on_chain)
    return _as_name(transaction.from_addr, "from_addr")
```

## Error 1, the rerun

```
bot c8e5c5db  ->  identity 3ecef1619dd9  ->  0x3ecef1619dd90c8d933993228485eb1973971ce9
bot 5ca99f1f  ->  identity 48cce07b5732  ->  0x48cce07b5732795ff561bd78ade52212f84e1180
bot a8d95fed  ->  identity ca3e3124a322  ->  0xca3e3124a3226b2052a5310166c55bd40c943ddc
```

## Error 2, the error — the axis threshold was named and never imported

```
mypy:name-defined               line 489 [high]: Name "MIN_SCORED_AXES" is not defined
pyright:reportUndefinedVariable line 489 [high]: "MIN_SCORED_AXES" is not defined
```

## Error 2, reproduction

```
python -m dev_harness.harness.coding_archetype src/competition/action_spend.py
```

## Error 2, the cause

`add_graded_fill` leaves a fill below the minimum axis count out of the mean, and it
named that bound without importing it.

## Error 2, the correction

`from .capture_bounds import MIN_SCORED_AXES` in `action_spend.py`. Unit 10 sets that
number at 1 and unit 14 already imports it the same way, so one threshold stands for
the award, the share and the join. `capture_bounds` imports `market_rotation` and
`quintessence_ledger`, and neither reaches `action_spend`, so the import is acyclic.

## Error 2, the rerun

```
coding_archetype src/competition/action_spend.py  passed=True  81 findings, 0 high
```

Factoring `_as_scored_axes` and `_as_grade_numeric` out of `write_grade`, so both
writers share them, took that file from 90 findings to 81.

## Error 3, the error — the chain parameter was typed as a bare object

```
low | mypy    | "object" has no attribute "chain"
low | pyright | Cannot access attribute "chain" for class "object"
```

## Error 3, reproduction

```
python -m dev_harness.harness.coding_archetype src/competition/event_redistribution.py
```

## Error 3, the cause

`certified_participant` took `testnet: object`, so neither mypy nor pyright could resolve
the chain attribute on it.

## Error 3, the correction

`LocalTestnet | None`, imported under `TYPE_CHECKING`. Adding that import before the
annotation used it left vulture reporting it dead, at high, so the two changes belong
together.

## Error 3, the rerun

```
coding_archetype src/competition/event_redistribution.py  passed=True  30 findings, 0 high
```

## Error 4, the error — two driver calls against the wrong signature

```
AttributeError: 'QuintessenceLedger' object has no attribute 'ledger_path'
TypeError: ActionSpend.act() missing 2 required positional arguments: 'address' and 'band'
```

## Error 4, reproduction

The shared reproduction above, at the point the pot forms.

## Error 4, the cause

The ledger keeps its path private and reports through `supply_summary`. `act` takes
the event, the address and the band, and builds its own `ActionDraft`.

## Error 4, the correction

The driver reads `supply_summary()` and calls `act(event_id, address, band)`. The
negative-bucket count also comes from `conservation()`, which already reports it,
rather than from a scan written beside it.

## Error 4, the rerun

```
EXIT=0
pot 0.120   return pool 0.090   paid 0.089999999999999999
remainder 0.000000000000000001   reserve 0.030000000000000001   exact True
```

## Error 5, the error — the first spend control could not have failed

The first control multiplied every participant's spend by 100 and read the shares
back unchanged. A normalised share is proportional, so one figure applied to every
spend leaves the shares unchanged even in a division that reads spends.

## Error 5, reproduction

The shared reproduction above, at the spend section.

## Error 5, the cause

The control scaled the whole set instead of one member of it, so both arms agreed for
a reason that had nothing to do with the code.

## Error 5, the correction

One participant's spend alone goes up a thousandfold. A second arm halves that same
participant's score instead. The first arm must not move and the second must.

## Error 5, the rerun

```
spends  0.100    0.010  0.010   shares  0.0978696492  0.1492240350  0.1279063157
spends  100.000  0.010  0.010   shares  0.0978696492  0.1492240350  0.1279063157

scores  0.2869375  0.875  0.75  shares  0.0562788074  0.1716191036  0.1471020888
```

## Error 6, the error — the manual block opened a sentence with a filler phrase

```
high | vale | line 147 | Don't start a sentence with 'There is'.
```

## Error 6, reproduction

```
python -m dev_harness.harness.docs_archetype <scratch>/U29_manual_block.md
```

## Error 6, the cause

The demo-mode paragraph closed on a four-word sentence built around a filler phrase.

## Error 6, the correction

"No flag chooses between them." Four weasel words and two wordy phrases went the same
way in the same pass.

## Error 6, the rerun

```
docs_archetype docs/manual/08-tabs/proof-of-accumulation.md  passed=True
290 findings before the block, 290 after, 0 high, 7 tools ok
```

## What the join does, and what it refuses

```
certified_participant    the sender of the receipt's certification transaction
record_certified_fill    that address, the fill's trade_grade and its scored_axes
add_graded_fill          grade_total += grade, graded_fills += 1,
                         grade_numeric = grade_total / graded_fills
                         scored_axes = the least axis count behind the mean
```

A fill whose axis count falls below `MIN_SCORED_AXES` changes neither the total nor
the count, so it cannot act as a zero. A participant with no scoreable fill keeps a
count of nought, reads as `no_score`, and takes no share.

```
no bot named         bot_id must be a non-empty string, got ''
no such transaction  transaction 0xnotonthischain is not on this chain, so the
                     fill names no participant
no chain             bot d43c6de9d53e certified with no chain to read the sender
                     from, so the fill names no participant
accepted             0xd43c6de9d53e88201d4a4f16dd500dada3a111da
                     fills 1   total 1.0   score 1.0   axes 1
```

## The verdicts

```
coding_archetype  src/competition/action_spend.py          passed=True   81  0 high
coding_archetype  src/competition/event_redistribution.py  passed=True   30  0 high
coding_archetype  src/gui/shared_testnet.py                passed=True  149  0 high
ta_archetype      src/competition/action_spend.py          passed=True    0
ta_archetype      src/competition/event_redistribution.py  passed=True    0
ta_archetype      src/gui/shared_testnet.py                passed=True    0
gui_archetype     src/gui/shared_testnet.py                passed=True   21  0 high
docs_archetype    docs/manual/08-tabs/proof-of-accumulation.md  passed=True  290  0 high

python -m tools.local_ci --lane black    VERDICT: PASSED
python -m tools.local_ci --lane flake8   VERDICT: PASSED
```

`event_redistribution.py` carries two findings this unit added, both in classes the
file already held. One is a trailing comma ruff asks for and black removes, which the
file already carries eight of. The other reports `record_certified_fill` as uncalled,
the standing `settle` and `settled` already have, because nothing subscribes the join
to the live fill event.

## What the run could not answer

Nothing subscribes the join to `trade.filled`. Wiring it would mint and score against
the operator's real ledger on every trade, which is his decision.

The live fill payload carries no grade and no axis count, so a fill arriving that way
today carries the record's own defaults and stays out of the score.

## What the operator sees differently

Nothing on screen yet. The Redistribution panel already drew its figures; those
figures now come off the grades of real certified fills rather than grades handed to
the division by hand.
