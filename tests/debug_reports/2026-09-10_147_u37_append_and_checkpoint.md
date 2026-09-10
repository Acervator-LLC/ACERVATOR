# Unit 37 - the chain saves by appending, with a periodic snapshot

Branch `unit/147-u37-append-and-checkpoint`, cut from `e8745b49`. Files changed:
`src/core/io_utils.py`, `src/gui/shared_testnet.py`,
`docs/manual/08-tabs/proof-of-accumulation.md`.

Nothing in this unit wrote into `~/.acervator`. Every run was given an explicit scratch
path, and `~/.acervator/testnet_chain.json` was 4,059,629 bytes at sha256
`f84458bc69c8e894794836b8658be7518cb6e108e78861cd9769f12fe25988be` before and after. The
one read of that tree was `SharedTestnetBridge.node_id`, which reads
`bot_identity.json` and writes nothing.

| scratch path | what ran there |
|---|---|
| `%TEMP%/claude/u37_append_checkpoint` | the git worktree |
| `%TEMP%/.../scratchpad/U37_chain` | the copy of his chain file |
| `%TEMP%/.../scratchpad/U37_his` | his copy loaded through `install_on` |
| `%TEMP%/.../scratchpad/U37_legacy` | his copy loaded, a competition run, saved, reloaded |
| `%TEMP%/.../scratchpad/U37_run_8836`, `U37_run_110k` | the size sweeps |
| `%TEMP%/.../scratchpad/U37_base`, `U37_baseB` | two chains of 25,196 blocks each |
| `%TEMP%/.../scratchpad/U37_s1` … `U37_s6` | the six load conditions |
| `%TEMP%/.../scratchpad/U37_demo` | a live chain and a demo chain in one program |

`main.py` was never launched: `main.py:812` builds an instance guard whose
`take_ownership` writes into `~/.acervator`, and the operator is trading. Every run
reached `SharedTestnetBridge` directly, either through its constructor or through
`SharedTestnetBridge.install_on` with a `QObject` standing in for the window and every
one of its nine paths given a scratch path.

---

## Error one - a snapshot made the load slower than having no snapshot

### The error in the load

First run of the finished load path, on a chain of 110,002 log records whose snapshot
had absorbed 100,002 of them:

```
chain log holds 110002 whole records in 41589714 bytes
chain restored from disk (block=55000, log replayed=10000 of 110002, age=0 min, ms=2580.6)
```

2,580.6 ms to replay 10,000 records. The same history replayed from genesis costs
about 860 ms at the 7.8 microseconds a record the world budget measured, so the
snapshot was making the load three times slower than no snapshot at all.

### Reproducing the load error

```
PYTHONPATH=<worktree> PYTHONWARNINGS=error python -X dev -X faulthandler \
  U37_d1_size_sweep.py <scratch>/U37_run_110k 110000
```

The driver builds a chain through `LocalChain.send_tx`, calls `_save_now` every 100
placements, then constructs a second bridge over the same path and calls `_try_load`.
Every number above is the bridge's own logging.

### The cause of the load error

`SharedTestnetBridge._read_log` called `read_json_lines` over the whole file and
passed `_line_names_its_record` as the accept check. That parses every line and takes
a sha256 over every record, including the 100,002 the snapshot already held. The log
read alone was about 1.5 seconds of the 2.58, and it grew with the history rather than
with the tail, which is the cost a snapshot exists to remove.

### The correction to the load

The snapshot now records the byte offset it absorbed, and the load starts reading
there.

```python
CHECKPOINT_RECORD_INTERVAL = 50_000
```

`src/core/io_utils.py` gained `start` on `read_json_lines`, which seeks before reading,
and `read_json_line_before`, which reads back at most `MAX_JSON_LINE_BYTES` to find the
one line ending at a given offset. `_write_checkpoint` stamps `log_bytes` and
`log_tail_id` into the payload after the append it covers, and
`_confirmed_log_start` reads the line ending at `log_bytes` and compares its id with
`log_tail_id` before the load trusts the snapshot.

This is a byte offset and not a record index on purpose: an index still requires
parsing every line before it, which is the defect.

### The rerun of the load

```
chain log read 10000 whole records from byte 37806315 of 41590316 (ms=96.3)
chain restored from disk (block=55000, log records replayed=10000, log bytes=41590316, age=0 min, ms=1047.7)
```

96.3 ms instead of about 1,500, and the whole load 1,047.7 ms instead of 2,580.6. The
state is identical either way: 55,000 transactions, 55,001 blocks, verified.

---

## Error two - a save could read a record a worker was still writing

### The error in the save

No traceback. The condition was named in this issue by the unit that swept this file's
comments, and left unrepaired because no worker ran:

> `_serialize_state` reads `chain._blocks`, `chain._txs`, `chain._events`,
> `acrv._balances` and `registry._comps` on the Qt main thread and takes no lock.

Under a whole-file rewrite the consequence is bounded: the next save replaces whatever
half-written snapshot landed. Under an append it is not, because a half-written record
goes onto the end of the history and stays there.

### Reproducing the save error

Not driven. `_CompetitionWorker.run` holds `_mutation_lock` for a whole competition,
the 250 ms drain timer can start the next worker before the 500 ms persist timer fires,
and nothing in the running application enqueues a request, so the race has no reachable
input today. The change was made because the append makes its consequence permanent.

### The cause of the save error

`_save_now` read the chain directly with no lock at all.

### The correction to the save

`_plan_save` takes `_mutation_lock` with `blocking=False` and returns `None` when it
cannot have it; `_save_now` then re-arms `_persist_timer` and tries again later. The
snapshot of the new records is taken inside the lock and every file write happens after
the release, so the drawing thread never waits for a competition and never reads a
record mid-write.

### The rerun of the save

550 appends and two snapshots across one run, every one of them after the lock was
taken and released, with no deferral observed because the driver drives one thread.
The deferral path is reached only with a worker running, which nothing in the
application starts.

---

## What the six load conditions reported

One chain of 25,196 blocks, 25,195 transactions, 9 events and one competition worth 10
ACRV, copied six times.

| condition | records replayed | what loaded |
|---|---|---|
| snapshot and tail | 368 | 25,195 transactions, verified, 429.0 ms |
| snapshot removed | 50,401 | the same state, 663.3 ms |
| log cut by 150 bytes | 367 | 25,194 transactions, 218 bytes dropped |
| the same cut, snapshot removed | 50,400 | 25,194 transactions, same |
| one digit changed in a record | 367 | 25,194 transactions, line still valid |
| A's snapshot beside B's log | 50,401 | B's chain, `COMP-1DA0EFC1` |

The last row is the disagreement rule. With its own log the same snapshot loads
`COMP-489CF6D4`, so the reading follows the log and is not a constant.

A seventh condition truncated the log below the bytes the snapshot absorbed. That is
not a disagreement, because a log that short carries nothing the snapshot does not, so
the snapshot stands and the short log is emptied.

## His own chain

```
chain restored from disk (block=3135, log records replayed=0, log bytes=0, age=204973 min, ms=48.1)
3,136 blocks  3,135 transactions  2,565 events  285 competitions  2,850 ACRV
3,135 legacy blocks, 3,135 legacy transactions, 0 altered, is_verified True
chain save planned (records=32, checkpoint=False, ms=2.1)
chain log appended (records=32, bytes=185843, log bytes=185843, ms=4.3)
reloaded: 3,147 blocks  3,146 transactions  2,574 events  286 competitions
his chain file: 4,059,629 bytes, sha256 f84458bc…, unchanged
```

A competition on his chain costs a 185,843 byte append instead of a 4.2 megabyte
rewrite, and his chain file is not touched until 50,000 records have gone by.
`SCHEMA_VERSION` is still 1, and the branch at `src/gui/shared_testnet.py` that unlinks
the file on a version mismatch was not changed.

## What could not be answered

`python -m tools.build_product_manual` cannot run in a fresh worktree: it stops at
`06-trading-tab.md needs figure p15-i0.png, absent from artifacts/manual-figures`, and
`artifacts/` is gitignored and absent. Its own contents-row validation was therefore
unavailable, so the new page section was checked by `docs_archetype` alone.
