# Content-derived block and transaction ids — the program errors and the runs

Reference. Subjects: `src/competition/local_testnet.py`,
`src/competition/node_link.py`, `src/gui/shared_testnet.py`,
`docs/manual/08-tabs/proof-of-accumulation.md`.

No test file was written. Every run below constructs the real objects through
`SharedTestnetBridge.install_on`, calls product methods only, and reads what the
program logs about itself. Nothing printed a line of its own. Every run used
`python -X dev -X faulthandler` with `PYTHONWARNINGS=error`.

`main.py` was never launched. Its instance guard writes into the runtime tree the
operator's live process holds, so the construction path was reached directly, the
way units 1, 4, 7, 15 and 16 reached it.

## What names a record now

```
transaction   from_addr, to_addr, function_name, args, gas_used, status
block         number, parent_hash, timestamp, transactions
bytes         json.dumps(sort_keys=True, separators=(",", ":"), allow_nan=False)
timestamp     rounded to 3 decimal places before storage and before hashing
genesis       GENESIS_BLOCK_ID, 64 zeros, as both its own id and its parent
```

`block_number` and `timestamp` are excluded from a transaction id. Two nodes
record one transaction at different moments into differently numbered blocks, so
either field would make the two nodes disagree. The block id carries both, and
carries its parent's id, so editing any block invalidates that block and every id
after it.

## Error 1 — the removed helper left two undefined call sites

```
mypy:name-defined line 223 [high]: Name "_fake_hash" is not defined
pyright:reportUndefinedVariable line 223 [high]: "_fake_hash" is not defined
mypy:name-defined line 252 [high]: Name "_fake_hash" is not defined
pyright:reportUndefinedVariable line 252 [high]: "_fake_hash" is not defined
```

Reproduction: `python -m dev_harness.harness.coding_archetype
src/competition/local_testnet.py` after the helper was replaced.

The cause: `_fake_hash` built an id from `time.time_ns()` and `uuid.uuid4()`. It
was deleted before `mine` and `send_tx` were repointed.

The correction: `mine` calls `block_id` and `send_tx` calls `transaction_id`. The
name `_fake_hash` is gone, and those two call sites were its only callers.

The rerun reports neither finding.

## Error 2 — the first peer sync hung for ever

The two-process run through `install_on` never completed. Node A stopped logging
after discovering its peer, and node B timed out against it five times.

```
acervator.node_link INFO node node-81c952b60ccf discovered 1 peers in ...\peers
acervator.node_link WARNING node node-a6d3f9f8b3c9 could not sync with
                            node-81c952b60ccf: timed out
```

Reproduction: two processes, one peer directory, both reaching `start_listening`
and `sync_all`. Node A had to be killed. It had run 180 seconds past the point
both nodes should have held two records.

The cause: `apply_records` held `_chain_lock` and then called a method that
acquired the same lock. `SharedTestnetBridge` passes its own `threading.Lock`,
which is not reentrant, so the second acquire blocked on the first in the same
thread. Every construction path that goes through the bridge hands the link that
lock, so no sync inside the running program could ever finish. The fault is on
`origin/current` at `9a711411`, and the same run on a worktree of that commit
hangs identically.

The correction: `apply_records` reads the held ids from `chain._txs` inside the
lock it already holds. The method that re-acquired is removed; it had no other
caller.

The rerun completes both exchanges and both nodes end on the same two records.

```
node node-952ca991e4da took 1 of 1 records from peer node-ae8a2c70bb84
node node-ae8a2c70bb84 synced with node-952ca991e4da: held 1, offered 2, took 1,
                        now holds 2
node node-952ca991e4da synced with node-ae8a2c70bb84: held 2, offered 2, took 0,
                        now holds 2
chain verified: 3 blocks and 2 transactions carry the id of their own contents
```

## Error 3 — a finished competition wrote its result into the repository

```
?? competition_results/COMP-D61BCDF7.json
```

Reproduction: reach `run_demo_competition` through `request_competition` and
`_drain_queue` with the working directory set to the repository, then run
`git status`.

The cause: `src/competition/competition_engine.py:117` defaulted its results
directory to the relative path `competition_results`, so the directory lands
wherever the process was started. The Local Testnet tab reaches
`request_competition`, and the operator launches from the repository, so a demo
competition writes generated output into a tracked tree. `CLAUDE.md` forbids that
in two separate hard rules.

The correction: `DEFAULT_RESULTS_DIR` is
`Path.home() / ".acervator" / "competition_results"`, the same shape
`SharedTestnetBridge` already uses for the chain file. The `results_dir`
parameter still overrides it and no caller passes one.

The rerun, with the home directory pointed at a scratch path so the operator's
runtime tree is never written:

```
<run>/home/.acervator/competition_results/COMP-E7C822E7.json
chain verified: 12 blocks and 11 transactions carry the id of their own contents
git status: no competition_results entry
```

## Error 4 — the demo price walk drew from the standard library random module

```
ruff:S311 line 877 [high]: Standard pseudo-random generators are not suitable
                           for cryptographic purposes
dev_harness.harness.coding_archetype: passed=False
```

Reproduction: `python -m dev_harness.harness.coding_archetype
src/competition/local_testnet.py`. The finding predates this unit and the file
carried it at `9a711411`.

The cause: `run_demo_competition` built `random.Random(42)` and drew
`rng.gauss(0, 0.022)` to fabricate 120 synthetic prices. S311 flags the standard
library `random` module.

The correction: `numpy.random.default_rng(DEMO_PRICE_SEED)` and
`rng.normal(0, 0.022)`, cast to `float` so no numpy scalar reaches a record that
`json.dumps` has to write. `numpy>=1.26.0` is already declared in
`pyproject.toml`. The seed is unchanged, so the walk stays repeatable. No
suppression was added.

The rerun reaches `run_demo_competition` through `request_competition` and
`_drain_queue`, with the home directory pointed at a scratch path. It completes,
names a winner and mints the award.

```
participants        3
winner_bot_id       5351c24c400382e0364c3f683687e8317c78cdee8841728e4dd1dac8f5d765d9
winner_tier         Harvest
winner_tokens       10
rank 1 final_value  371.46
sending transaction 0x7dd38320ea4c2125... calling mint
sending transaction 0xedfe825e135f5178... calling adjudicate
chain verified: 12 blocks and 11 transactions carry the id of their own contents
```

A second run on a fresh scratch home reproduced `371.46`, `370.79` and `370.58`,
so the seed still replays one series.

`coding_archetype` now reports `passed=True` on the file.

## Run 1 — two nodes, one id

Two processes, two chain files, two identities, two Quintessence ledgers, one
announcement directory. Each certified one fill of its own, then took the other's
record. The id each node logged for the other's record equals the id the owning
node logged.

```
node A own fill      0xc69ee5a4fa90328a9f730da334451160430c3e3c4279e8a863a83099d86d5cc0
node B took it as    0xc69ee5a4fa90328a9f730da334451160430c3e3c4279e8a863a83099d86d5cc0
node B own fill      0xaab8eefd0d4f2e481a6a7a79b3bfb730d8765846f4376c660d9534abc54ccf18
node A took it as    0xaab8eefd0d4f2e481a6a7a79b3bfb730d8765846f4376c660d9534abc54ccf18
```

The second exchange took nothing in either direction, which is the same record
arriving twice and being recognised by its id.

## Run 2 — the before state, taken from git

A detached worktree at `9a711411`, the same steps, the same fixed
`transferQuintessence` call in two processes. The ids each process wrote into its
own chain file:

```
before   node_a  0x692edd3d07a1b2019b3ce1ed84a262ce9e2a033181ab24805455ee580c84965d
         node_b  0x3d3153c056bb1bc55c4f613bebfc81d3b9ab6a7581e436c7263fb24684ac6b03
after    node_a  0x3472b3435c6b9c843317353b681810c2f416501d6ac2f2c302ff758cdbecdb6a
         node_b  0x3472b3435c6b9c843317353b681810c2f416501d6ac2f2c302ff758cdbecdb6a
```

The before state was never reconstructed by hand. `git worktree add --detach`
checked out the commit, and one file of calls ran unchanged in both trees.

## Run 3 — an altered record, and what refuses it

One stored record's amount was edited from `12.5` to `99.5` in a copy of node A's
chain file, its id left alone. Node A loaded that file and both nodes synced.

```
chain NOT verified: 0 of 3 blocks altered [], 0 parent links broken [],
                    1 of 2 transactions altered ['0x3472b3435c6b9c84']

node node-a7904d78dd27 refused record 0x3472b3435c6b9c843317353b681810c2f41650
    1d6ac2f2c302ff758cdbecdb6a calling transferQuintessence: its contents name
    0x1a4bdf2cbbfd171da96b52a51aab69358b7fdbff4ef8c4809c904fb6b1b0a54f
node node-a7904d78dd27 synced with node-6feb24ca8462: held 2, offered 3,
                        took 1, now holds 3
chain verified: 4 blocks and 3 transactions carry the id of their own contents
```

`PoaNodeLink.apply_records` is what refuses it, before `LocalChain.send_tx` is
reached. `LocalChain.verify_integrity` is what names it, and
`SharedTestnetBridge._try_load` calls that after every restore.

The same exchange took one good record and refused one altered record, so the
refusal is not a blanket rejection of the peer.

## Run 4 — the chain already on the operator's machine

`~/.acervator/testnet_chain.json` was copied to a scratch directory and loaded
there. The real file was never opened for writing.

```
chain restored from disk (block=3135, age=204388 min)
chain NOT verified: 3135 of 3136 blocks altered [1, 2, 3, 4, 5],
                    0 parent links broken [],
                    3135 of 3135 transactions altered ['0x3f79536e53815466', ...]
```

It loads. It is not rejected, not unlinked and not rewritten by the load. Block 0
verifies against `GENESIS_BLOCK_ID`; the other 3,135 blocks and all 3,135
transactions carry ids the old helper produced, so none of them is the id of its
own contents, and every parent link is intact.

A load followed by a save preserves every record.

```
before   4,059,629 bytes   3,136 blocks   3,135 transactions   2,565 events
after    3,946,745 bytes   3,136 blocks   3,135 transactions   2,565 events
```

The 112,884-byte difference is exactly the 112,885 carriage returns the original
file carries and the rewritten file does not. `atomic_write_json` writes `\n`, and
the file on disk was written by an older build in Windows text mode. No record,
field or value differs.

No migration was built. Renaming 3,135 records contradicts the node rule that
never removes or reorders a record, and a load that recomputed every id would
remove the property this unit adds, because an id recomputed from whatever is on
disk can never disagree with what is on disk.

## Run 5 — demo mode

The same steps over a different chain directory and the network name
`acervator-poa-testnet`. No flag and no setting.

```
PoaNodeLink installed (node=node-04b4e394a029, network=acervator-poa-testnet,
                       listening=False)
sending transaction 0x3472b3435c6b9c843317353b681810c2f416501d6ac2f2c302ff758cdbe
    cdb6a calling transferQuintessence
node-04b4e394a029 synced with node-2a283bba3115: held 3, offered 3, took 0,
                  now holds 3
chain verified: 4 blocks and 3 transactions carry the id of their own contents
```

The transfer carries the same id on the demo chain as on the live-network chain,
because the id reads the contents and nothing about the chain it sits on.

## Run 6 — the duplicate refusal against the path that mines most

`send_tx` now raises when the chain already holds a transaction of identical
contents. `run_demo_competition` is the heaviest caller and the bridge worker runs
it, so it was reached through `request_competition` and `_drain_queue`.

```
chain verified: 12 blocks and 11 transactions carry the id of their own contents
```

Eleven transactions, no refusal, no traceback.

## Archetype verdicts

```
src/competition/local_testnet.py       coding passed=True    ta  passed=True
src/competition/node_link.py           coding passed=True    ta  passed=True
src/competition/competition_engine.py  coding passed=True    ta  passed=True
src/gui/shared_testnet.py              coding passed=True    ta  passed=True
                                       gui    passed=True
docs/manual/08-tabs/
  proof-of-accumulation.md             docs   passed=True
tests/debug_reports/
  2026-09-10_unit23_content_ids.md     docs   passed=True
```

Every tool reported `ok` in `tool_availability` on every run above, and every
verdict was read out of the JSON on stdout rather than from an exit code.

```
python -m tools.local_ci --lane black    VERDICT: PASSED
python -m tools.local_ci --lane flake8   VERDICT: PASSED
known_good.py   exit 0
known_bad.py    exit 1
```

## Known limits

Block 0 keeps an id of 64 zeros, so its timestamp is the one stored value no id
covers. It holds no parent and no transaction.

A wire record now declares seven fields rather than six. The seventh is the
chain's id for the transaction, and the receiving side recomputes it from the
other five plus the success flag before accepting anything.

A chain file is not protected from whoever owns the machine. Editing a record and
recomputing its id by hand produces a file that verifies. What the ids buy is a
second node that disagrees out loud.
