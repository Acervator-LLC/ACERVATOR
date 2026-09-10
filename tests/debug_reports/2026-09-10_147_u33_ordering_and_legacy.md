# Unit 33 - deterministic ordering at a block close, and an honest word for a legacy file

Branch `unit/147-u33-ordering-and-legacy`, cut from `0a27153b`. Files changed:
`src/competition/local_testnet.py`, `src/competition/node_link.py`,
`src/gui/shared_testnet.py`, `docs/manual/08-tabs/proof-of-accumulation.md`.

Nothing in this unit wrote into `~/.acervator`. Every run set `USERPROFILE` and `HOME`
to a scratch directory and passed every path to `SharedTestnetBridge.install_on`
explicitly.

| scratch path | what ran there |
|---|---|
| `%TEMP%/claude/U33_wt` | the git worktree |
| `%TEMP%/claude/U33_scratch/fakehome` | `Path.home()` for every run |
| `%TEMP%/claude/U33_scratch/final/{records.json,nodeA,nodeB}` | the two-node order proof |
| `%TEMP%/claude/U33_scratch/final_real` | a copy of his chain, loaded and saved |
| `%TEMP%/claude/U33_scratch/final_mixed` | his chain plus one current record |
| `%TEMP%/claude/U33_scratch/save_before` | his chain saved by the pre-change code |

---

## Error one - two nodes execute one world turn in different orders, silently

### The error in the order

`src/competition/local_testnet.py`, `transaction_id`, excluded the transaction's own
timestamp from its id. `TxRecord` carries a timestamp and `apply_records` stamped a
peer's record with the receiving node's clock, so two nodes held one action under one
id at two different times and ran the hour in two different orders. Nothing reported a
disagreement, because every id was correct on both sides.

### Reproducing the order error

Three processes at commit `0a27153b`, three separate chain files, the same three
actions handed to two of them in two different arrival orders.

```
PYTHONWARNINGS=error python -X dev -X faulthandler U33_node.py source  records.json
PYTHONWARNINGS=error python -X dev -X faulthandler U33_node.py apply   records.json nodeA 2,0,1
PYTHONWARNINGS=error python -X dev -X faulthandler U33_node.py apply   records.json nodeB 1,2,0
```

```
source  alpha, bravo, charlie    chain verified: 4 blocks and 3 transactions
nodeA   charlie, alpha, bravo    chain verified: 4 blocks and 3 transactions
nodeB   bravo, charlie, alpha    chain verified: 4 blocks and 3 transactions
```

Three orders, three verified chains. The pre-change state came from the repository at
`0a27153b` with a clean tree, never from reversing an edit.

### The cause of the order error

`LocalChain.mine` appended each transaction in the order it was handed, and
`PoaNodeLink.apply_records` called `LocalChain.send_tx` once per record, so one block
held one record and arrival order was the only order there was. `mine` already accepted
a list and no caller ever passed more than one.

### The correction to the order

`mine` is now the close. It sorts its transactions through `block_order`, gives each
one a `block_position`, and writes the `transaction_id` of its contents at that
position. `block_order` sorts on the declared placement time, then on the record's
`placement_id`, so arrival order is read nowhere.

`apply_records` closes one block over the whole batch instead of one block per record,
and the wire record carries `placed_at`, so the receiving node keeps the placing node's
declared time rather than stamping its own. The wire record's id is the `placement_id`,
which covers the declared time and excludes the position, so a relay that rewrites
either the time or the contents produces an id its own contents do not name.

`send_tx` keeps its duplicate refusal, now keyed on `placement_id` and backed by an
index `mine` maintains and `reindex_placements` rebuilds after a load.

### The rerun after the order change

```
nodeA heard   charlie, alpha, bravo    applied 3
nodeB heard   bravo, charlie, alpha    applied 3

both closed   0  0x9218cce8...  bravo     placed 1789049829.404
              1  0x46b36816...  alpha     placed 1789049829.404
              2  0xc2de4239...  charlie   placed 1789049829.405
```

Both chains report `is_verified` true with `broken_parents` empty. Neither arrival
order matches the closed order. Alpha and bravo share a millisecond, so the
`placement_id` tie-break ordered those two and the clock ordered charlie.

Re-offering the same three records to node A after a save and reload reports
`applied 0`, so the identity of an action survives the position change and nothing
duplicates.

`send_tx` refuses a second identical action at the same millisecond:

```
attempt 0 landed 0x8b596115... stamp=1789049716.211
attempt 1 refused: action 0xa43b111b... calling place_action is already on this chain
```

### What a node can and cannot influence

```
can      declare when it placed its own action, to the millisecond
cannot   move where another node's action lands
cannot   make arrival order count, because arrival order is not read
cannot   change a time, an amount or a position later, all three being inside the id
```

### What the cost is

His chain was loaded and written out by the pre-change code and by the changed code,
so only the new field separates the two files. Comparing two saves by the same writer
avoids a line-ending difference: his file on disk is CRLF and `atomic_write_json`
writes LF, which is unrelated to this unit and unchanged by it.

```
before   3,946,745 bytes
after    4,031,424 bytes
         +84,679 over 3,135 transactions  = 27 bytes a transaction
         +34 bytes once                   = the file's own marker
```

Twenty-seven bytes takes one action from 988 bytes to 1,015, so a one-megabyte layer
holds 1,033 actions an hour rather than 1,061. Unit 32's recommended ceiling of one
megabyte per layer per world turn does not move, and its 655 participants on one
square each sits far under both figures.

### What it does not reach

A block's membership is whatever a node held when it closed. Two nodes that close
different sets give one action different positions, so its stored id differs on the
two chains while its `placement_id` stays the same. The hour boundary that would make
every node close the same set does not exist, and nothing bounds the actions inside a
world turn.

---

## Error two - a legacy file reports as tampered with

### The error in the legacy report

Loading his chain reported every record as altered.

```
chain NOT verified: 3135 of 3136 blocks altered [1, 2, 3, 4, 5], 0 parent links
broken [], 3135 of 3135 transactions altered ['0x3f79536e53815466', ...]
```

### Reproducing the legacy report

```
PYTHONWARNINGS=error python -X dev -X faulthandler U33_node.py load before_real chain.json
```

A copy of `~/.acervator/testnet_chain.json`, 4,059,629 bytes, under commit `0a27153b`.

### The cause of the legacy report

`verify_integrity` had one verdict for two different facts. A record whose id is not
its content hash was written either before ids derived from contents or after, and the
check could not tell which, so it named both altered.

### The correction to the legacy report

A saved chain carries `content_ids_from_block`, the first block number whose stored
ids derive from contents. `verify_integrity` reports a mismatch below that number as
legacy and one at or above it as altered, and `is_verified` reads the altered list
only. `_restore_state` reads the key and, when a payload has none, sets the boundary
one past the last block it loaded, so a file written under the older scheme is read
entirely as legacy.

`SCHEMA_VERSION` is still 1 and the wipe branch in `_try_load` is untouched. No
record is re-identified on load and no file is unlinked.

### The rerun after the legacy change

```
chain holds 3135 legacy blocks and 3135 legacy transactions: written before block
3136, when ids began to derive from contents, so the chain keeps them and does not
vouch for them
chain verified: 1 blocks and 0 transactions carry the id of their own contents
```

```
blocks 3136   blocks_legacy 3135   blocks_altered []
transactions 3135   transactions_legacy 3135   transactions_altered []
content_ids_from_block 3136   broken_parents []   is_verified true
```

The file is untouched afterwards: 4,059,629 bytes, sha256
`f84458bc69c8e894794836b8658be7518cb6e108e78861cd9769f12fe25988be`, the same as
before the run.

### The controls

**The boundary decides it, read both ways.** The same saved file, once with its own
marker and once with the marker set to zero by hand.

```
marker 3136   3,135 legacy, 0 altered, is_verified true
marker 0      0 legacy, 3,135 altered, is_verified false
```

**A current record is still held to its contents.** One record was applied to a copy of
his chain, mining block 3136, and the file was saved. One amount inside that one
record was then edited.

```
blocks 3137   transactions 3136
legacy        3,135 blocks and 3,135 transactions
altered       1 transaction, 0x86be12a8...
is_verified   false
```

The tampered file is still on disk at 4,032,175 bytes, so the load refuses to vouch
for the record and does not delete anything.

**The wire refusal is unchanged and selective.** One record of three was edited and
offered to a node.

```
node node-d696c55d048f refused record 0xa5c75b7a... calling place_action: its
contents name 0x9e7853d2...
applied 2
```

**A current file behaves as it did.** A file saved by the changed code reloads with
`content_ids_from_block` 0, no legacy, no altered, `is_verified` true.

---

## Constructed and reached

Every run above reached `SharedTestnetBridge.install_on`, which the window calls at
`src/gui/main_window.py:277`. `main.py` was not launched: `main.py:812` builds an
instance guard whose `take_ownership` writes into `~/.acervator`, which is the live
process's tree.

## Demo mode

No flag and no second path. Each node was a separate `LocalTestnet` and a separate
`SharedTestnetBridge`, each handed its own chain and its own persist path at
construction, and the same `mine`, `apply_records` and `verify_integrity` ran over all
of them. Four chains in this unit, four scratch files, one set of methods.

## Verification

```
npm install                                    ok
python -m tools.local_ci --lane black  --all   PASSED, 1 lane ran
python -m tools.local_ci --lane flake8 --all   PASSED, 1 lane ran
```

| file | archetype | passed | errors | tools |
|---|---|---|---|---|
| `src/competition/local_testnet.py` | coding | True | [] | 11 ok |
| `src/competition/local_testnet.py` | ta | True | [] | 3 ok |
| `src/competition/node_link.py` | coding | True | [] | 11 ok |
| `src/competition/node_link.py` | ta | True | [] | 3 ok |
| `src/gui/shared_testnet.py` | coding | True | [] | 11 ok |
| `src/gui/shared_testnet.py` | ta | True | [] | 3 ok |
| `src/gui/shared_testnet.py` | gui | True | [] | 5 ok |
| `docs/manual/08-tabs/proof-of-accumulation.md` | docs | True | [] | 7 ok |

Each archetype was shown able to report before it was trusted: `known_good` exits 0
with `passed` true and `known_bad` exits 1 with `passed` false, for coding, docs, ta
and gui.

No test file in `tests/` names `local_testnet`, `node_link` or `shared_testnet`, so no
canon test covers these three modules. That gap is the harness owner's to close.
