# Node linking between instances — the program errors, the runs and the control

Reference. Subjects: `src/competition/node_link.py`, `src/gui/shared_testnet.py`,
`src/competition/__init__.py`,
`docs/manual/08-tabs/proof-of-accumulation.md`.

No test file was written. The evidence is two scratch drivers that construct the
real objects and let the program's own logging report. Neither driver prints a
line of its own.

`main.py` was never launched. Its instance guard writes into the runtime tree the
operator's live process holds, so the construction path was reached directly, the
way units 1, 4, 7 and 15 reached it.

## The five safety and design decisions, each as a mechanism

```
nothing binds at construction   no socket object exists until start_listening
                                constructs _LinkServer; endpoint raises while
                                _server is None
loopback only                   LOOPBACK_HOST is the bind address and no method
                                takes a host argument; verify_request refuses a
                                client address that is not LOOPBACK_HOST
no trading state crosses        ChainRecord is a frozen dataclass of six fields,
                                so from_payload raises TypeError on a seventh;
                                the link holds the chain and reaches only
                                send_tx and emit; function_name is stored text
                                and nothing calls it
discovery                       one announcement file per node under peer_dir,
                                read back by peers(); no broadcast and no
                                listener beyond the node's own port
agreement                       a record is named by the sha256 of its own
                                canonical JSON; apply_records adds what the
                                chain does not hold and removes nothing
```

## The chain cannot express a fork

`LocalChain` keeps one `_blocks` list, `mine` always parents on `_blocks[-1]`,
`_block_number` only increments, and no index maps a hash to a block. The class
holds no second competing branch and selects no head.

`src/competition/local_testnet.py:49` — a block's identifier

```python
def _fake_hash(seed: str = "") -> str:
    raw = f"{seed}{time.time_ns()}{uuid.uuid4()}"
    return "0x" + hashlib.sha256(raw.encode()).hexdigest()
```

The identifier is built from the clock and a random number, not from the block's
contents, so two nodes holding the identical record give their blocks different
identifiers. Every named consensus rule needs a block whose hash commits to its
parent and its contents so a peer can verify a branch it did not build. That does
not exist here, so no such rule was built. The rule taken instead refuses to
remove a record, refuses to reorder one already held, and refuses to claim the
two chains are identical block for block.

## Error 1 — a method declared with no colon and no body

```
mypy:syntax line 345 [high]: Expected ':'
pyright:no-code line 345 [high]: Expected ":"
dev_harness.harness.coding_archetype: passed=False (11 findings, high=2)
```

Reproduction: `python -m dev_harness.harness.coding_archetype
src/competition/node_link.py` on the first draft.

The cause: `def stop_listening(self) -> None` carried a docstring and nothing
else, so the file did not parse.

The correction: `stop_listening` now clears `_server` and `_serve_thread`,
withdraws the announcement, shuts the server down and joins its thread.

The rerun reports `passed=True` with no high finding.

## Error 2 — a sync that reported nothing at all

The two-process run left node A holding 2 records but printed no line for its own
sync, so "found no peer" and "took nothing new" were the same silence.

```
node 9176c045969a took 1 of 1 records from peer 5f908eb0161f
node 9176c045969a ends with 2 chain records
```

Reproduction: run the pair, read node A's log, and find no sync line between the
handler line and the closing line.

The cause: `sync_all` logged inside the peer loop and inside the failure branch
only, so an empty peer list produced no output.

The correction: `sync_all` logs the discovered peer count and the directory it
read before the loop runs.

The rerun named the real condition, which turned out to be the driver's ordering
rather than the module — node B withdrew its announcement on stop before node A
took its turn.

```
node 9176c045969a discovered 0 peers in ...\U16_run2\peers
```

## Error 3 — a non-ASCII dash in a log message

```
... Call generate() first.) ? this node is node-694eca0b8dc2 for as long as it runs
```

Reproduction: run the install driver and read the line on a console that cannot
encode the character.

The cause: an em dash in the `node_id` fallback message.

The correction: the message reads "so this node is %s for as long as it runs" in
ASCII.

The rerun prints the whole line.

## Error 4 — a reply declared a dict that could arrive as a list

```
mypy:no-any-return line 453: Returning Any from function declared to return
"dict[Any, Any]"
```

The cause: `_exchange` returned `json.loads(...)` unchecked. A peer answering a
JSON array would reach `reply.get` in `sync_with` and raise `AttributeError`
naming neither the peer nor the cause.

The correction: a reply that is not an object raises `NodeLinkError` naming the
peer and the type that arrived.

## Error 5 — a dead constant cited by its own docstring

```
vulture:dead-code line 38: unused variable 'RECORD_FIELDS'
```

The cause: `RECORD_FIELDS` was declared, never read, and the `ChainRecord`
docstring named it as the thing that refuses an unknown key. The refusal is the
frozen dataclass raising `TypeError`, so the docstring pointed at a tuple that
did no work.

The correction: the constant is gone and the docstring names the six declared
fields.

## The two-process run, on separate chains

Two processes, each with its own `LocalTestnet` held only in its own memory, its
own identity, Quintessence ledger and socket file under its own directory, and
one shared announcement directory. Neither process writes a chain file, so no
chain file is shared and none could explain the agreement.

```
node_a books   ...\U16_m1\node_a\{bot_identity,quintessence_ledger,socket}.json
node_b books   ...\U16_m1\node_b\{bot_identity,quintessence_ledger,socket}.json
peer_dir       ...\U16_m1\peers
~/.acervator   never written; no poa_nodes directory exists in it
```

Each node certified one fill of its own, so each started with one record the other
did not have.

```
node c95159286bba starts with 1 chain records on node_a
node c95159286bba listening on 127.0.0.1:65384 (network=acervator-poa, records=1)
node c633f9c39f24 starts with 1 chain records on node_b
node c633f9c39f24 listening on 127.0.0.1:65439 (network=acervator-poa, records=1)
node c633f9c39f24 discovered 1 peers in ...\U16_m1\peers
node c633f9c39f24 synced with c95159286bba: held 1, offered 2, took 1, now holds 2
node c95159286bba took 1 of 1 records from peer c633f9c39f24
node c95159286bba synced with c633f9c39f24: held 2, offered 2, took 0, now holds 2
node c633f9c39f24 took 0 of 2 records from peer c95159286bba
node c95159286bba ends with 2 chain records
node c633f9c39f24 ends with 2 chain records
```

The second exchange took nothing in both directions. That is the same record
arriving twice and being recognised, which is the property the whole rule rests
on: a record re-derived from the chain after `send_tx` and `emit` keeps its
digest, because the digest covers only the six values those two calls carry.

## The control — break the link and they diverge

The same two processes, the link constructed and `start_listening` never called.

```
node fe54c6df3573 ends with 1 chain records, never having listened
node 489b5307bb07 ends with 1 chain records, never having listened
announcement files in peer_dir: none
```

One record each, not two. The agreement in the run above came over the socket.
The empty announcement directory is the same control read a second way:
construction wrote no endpoint and bound no port.

## Constructed and reached

`SharedTestnetBridge.install_on` is the established route, called at
`src/gui/main_window.py:277` inside `_setup_ui` before any tab is built. The link
is built there because that bridge owns the only mutation lock for that chain, and
the link writes that chain; built anywhere else it would write without the lock.

```
PoaNodeLink installed (node=node-7a83a8672a67, peers=...\U16_mi\poa_nodes,
                       network=acervator-poa, listening=False)
SharedTestnetBridge installed (persist=...\U16_mi\testnet_chain.json)
install_on attached node_link='PoaNodeLink' to the window: same object=True
after install: listening=False, announced files=no directory, chain=[]
endpoint before start_listening raised NodeLinkError:
    node node-7a83a8672a67 is not listening, so it has no endpoint
```

Nothing in the running program calls `start_listening`. No unit on the issue
carries a control that would, so the caller is named as owed rather than invented.

## Demo mode

The chain reaches the link by construction, as it reaches the certification
socket. A demo node is the same object over a different `LocalTestnet`, a
different announcement directory and a different network name.

```
two demo nodes   node efad997ddc19 synced with 56d934d38462:
                 held 1, offered 2, took 1, now holds 2
                 network=acervator-poa-testnet

one of each,     node 883079b27380 discovered 0 peers   network=acervator-poa
one directory    node b1435252aa59 discovered 0 peers   network=acervator-poa-testnet
                 each ends with 1 chain records
```

Both nodes were listening at the same moment and both announced into one
directory. Each found no peer, because `peers()` drops a file whose network is not
its own.

## Known limit

A node killed outright leaves its announcement file behind. The next node to read
it logs that it could not be reached and carries on. Expiring the file needs a
lease interval, which is a number nobody has set, so none was invented.

## Verification

```
python -m tools.local_ci --lane black     VERDICT: PASSED
python -m tools.local_ci --lane flake8    VERDICT: PASSED
known_good.py   exit 0
known_bad.py    exit 1
```
