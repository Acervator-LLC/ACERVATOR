# PoA world state — what a world costs on the chain

2026-09-10. Reference. Every figure below came from driving records through the chain
the platform already runs, letting the chain save itself, and reading the file size
off the file system. Nothing here builds a grid, a tile, a position or a dungeon.

Raw captured output: `artifacts/147-u32/u32_raw_output.txt`. That directory is
gitignored because it holds captured run output, which `docs/` may not hold.

## The verdict first

A recorded world is affordable. The bytes and the load time are both comfortable,
even as a twenty-layer cube. The way the chain writes itself to disk is not, and
that is the single thing that has to change before the base and city system is
built. A cube saturates that write path inside two hours.

```
one action on the chain today            988 bytes
one action in a chosen encoding          399 bytes
recommended ceiling                      1 MB per layer per one-hour world turn
participants a layer                     655
squares a layer                          655
squares per participant                  1, and it is fixed rather than chosen
a twenty-layer world                     20 MB a world turn, 13,100 participants
his real 3,136-block chain reloads in    65 ms
a hundred times those records reload in  4.9 s
the binding constraint                   the save, not the size and not the load
the checkpoint a cube forces             about once a day at twenty layers
```

## How each figure was taken

The chain serialises itself through one path, and the file system reports how many
bytes that path wrote. No counter, sizer or timer was written for this note.

```
the save path      SharedTestnetBridge._save_now -> atomic_write_json
the size           Path.stat().st_size, read after the save returned
the record counts  LocalTestnet.get_competition_stats and verify_integrity
the load path      SharedTestnetBridge._try_load
the elapsed time   PowerShell Measure-Command over the whole process, against a
                   control process that does everything except the load
```

Every run used `python -X dev -X faulthandler` with `PYTHONWARNINGS=error`. The
operator's chain was copied to a scratch directory first and never written.

## The instrument was proved before any figure was read

A re-save of his loaded chain reproduces his own file, section for section. That is
the positive side: the path that produced the measurement is the path that produced
his file.

```
his file on disk                   4,059,629 bytes
his chain re-saved by the program   3,946,745 bytes
difference                           112,884 bytes, every one a carriage return
sections that differ                         none
```

The discriminating side is that the size moves, and moves differently, for each
record shape driven through it. A re-save with nothing added moves the file by one
byte, which is the `saved_at` value changing length.

## His per-record figures, confirmed and corrected

The record counts are exactly as recorded in the issue. The program reports them
about itself.

```
blocks         3,136    verify_integrity, genesis included
transactions   3,135    get_competition_stats total_transactions
events         2,565    get_competition_stats total_events
file bytes 4,059,629    the file system
```

The per-record averages of 291, 369 and 322 bytes rest on that 4,059,629 figure,
and 112,884 of those bytes are carriage returns rather than content. His file was
written by an older build in Windows text mode; the current writer emits one byte
per line ending. The averages are therefore 2.86% high.

```
his figure   corrected
   291          283      bytes a block
   369          359      bytes a transaction
   322          313      bytes an event
```

Nothing is lost by this. The next save of his chain will shrink the file by 112,884
bytes and change no record.

## What one action costs

One action was driven through the chain as a transaction named `act`, carrying a
grid move: an event id, a turn index, the actor, the action, a from-square, a
to-square and an Impetus cost. It is there to be measured and it is not a design.
One hundred were driven for each figure and the file-size change divided by one
hundred.

Each row is bytes per action, including the block the action rides in.

```
one block per action, named fields, indent=2   988   the path the chain runs today
one block per action, packed argument           781
one block per action, named fields, compact     969
one block per action, packed argument, compact  616
one block per turn,   named fields, indent=2    714
one block per turn,   packed argument, indent=2 508
one block per turn,   named fields, compact     526
one block per turn,   packed argument, compact  399   the chosen encoding
```

Two reference rows from the same run: an empty block costs 270 bytes, and a chain
event costs 266.

## What the chosen encoding gives up

Three changes take 988 bytes down to 399, and each one costs something real.

**The file stops being indented.** The save path asks for two-space indentation and
the chosen encoding asks for none, with the separators the chain's own consensus
encoder already uses. On his chain that alone saves 875,348 bytes, 22 per cent.
What it gives up is a file a person can read; the block explorer becomes the only
reader.

```
his chain saved with indentation   3,946,745 bytes
his chain saved compact            3,071,397 bytes
```

**The argument names disappear.** A packed argument saves 207 bytes an action and
makes the record unreadable without the code that wrote it. The chain records no
schema beside the record, so a future reader has no way to interpret the string.
The block explorer shows a single opaque value where it shows named fields today.

```
named fields, one block per turn    714 bytes
packed argument, one block per turn 508 bytes
```

**A turn's actions share one block.** That saves 274 bytes an action. What it gives
up is the ordering that block number supplies today, which is exactly the ordering
the world turn rule depends on. See the ordering section below.

## The two clocks

A world turn is one hour. A dungeon or raid turn is one candle. Both are read off
the code rather than assumed.

```
elite event turn      60 seconds   ELITE_TIMEFRAME 1m
standard event turn   300 seconds  STANDARD_TIMEFRAME 5m
world turn            3600 seconds TF_SECONDS carries 1h
```

The hour divides exactly into both: sixty elite turns or twelve standard ones. The
two cadences differ by twelve to sixty times, so an action rate quoted for one of
them says nothing about the other.

```
elite turns in an hour      60
standard turns in an hour   12
world turns in an hour       1
```

## Actions per turn, and the hole in the world turn

The Impetus pool bounds an event turn. Four Impetus at the first level, one more
every twenty levels, and a speed multiplier may at most double the level's own
grant. No partial action exists and nothing unspent carries forward.

```
level   1   grant 4   with the speed cap  8
level  20   grant 5
level  40   grant 6
level  60   grant 7
level 100   grant 9   with the speed cap 18
```

`poa_modes.py` holds no one-hour term at all. **Nothing bounds actions in a world
turn**, so the world turn has no budget today and the ceiling below can be stated
but not enforced.

To close it the design owes one term: a per-participant action allowance for the
world turn. The Impetus pool is the obvious shape to borrow, and borrowing it is a
product decision rather than an engineering one.

In development.

## Rebuilding a world from its own history

The operator's real chain, and then ten and a hundred times its records, were
loaded through the program's own load path. Each figure is the process wall time
less a control process that imports everything and constructs the same objects
without loading.

```
records    file bytes     load      per record
  8,836     4,059,629     65 ms      7.4 us
 65,265    26,031,824    516 ms      7.9 us
629,565   247,769,048  4,901 ms      7.8 us
```

The cost is flat per record across seventy-one times the history, so a world's load
time is its record count times eight microseconds. One second of load buys about
125,000 records. Ten seconds buys 1.28 million.

**Replay is not the constraint.** A hundred times his chain opens in five seconds.

## The save is the constraint

The save path serialises the whole chain and rewrites the whole file, every time.
The same three scales, timing one full save:

```
 3,946,745 bytes     67 ms    17.8 ms per MB
26,031,824 bytes    336 ms    13.5 ms per MB
247,769,048 bytes 3,444 ms    14.6 ms per MB
```

The save timer coalesces changes and fires half a second after the last one. At
fifteen milliseconds a megabyte a save finishes inside that half second only while
the chain is under about 34 megabytes.

```
34 MB at 399 bytes an action   about 85,000 actions, for the life of the world
512 MB, what a ten-second load allows   1.28 million actions
the gap                                 fifteen times
```

A world built on the current save path therefore stops at one fifteenth of what its
own load time would allow, and the limit sits on total history rather than on a rate.
**The question is not how many bytes. It is how often a checkpoint is written.**

The shape that removes it is the standard one: append each new record to the log
rather than rewriting the file, and write a full state snapshot periodically so a
load reads one snapshot plus a short tail. Neither is built.

In development.

## The recommended ceiling — a recommendation, not a decision

**One megabyte per layer per world turn.** Rounded from measurement in the safe
direction both times: the per-action cost up from 399 to 400 bytes, and the budget
down from the 1.28 megabytes a ten-second load would allow to a round one.

The ceiling is per layer rather than per world, and the next two sections are why.

```
1,048,576 bytes divided by 400 = 2,621 action records a world turn
```

Maximum world size and maximum participants reach the ceiling together, so there is
no remainder to spend on world and no trade-off between the two. One parameter moves
and both caps arrive at the same budget point.

```
participants = budget records / actions per participant per world turn
world squares = participants
```

At the recommended ceiling, with the first level's Impetus grant of four actions as
the per-participant allowance:

```
actions each   participants   world squares   squares per participant
      4             655            655                  1
      8             327            327                  1
     20             131            131                  1
     40              65             65                  1
```

The pair moves along that one line and never off it. The recommended point is the
first row: **655 participants on 655 squares, per layer.**

A single layer over a season of 720 world turns costs 720 megabytes. Loading that is
1.89 million records, which is 14.7 seconds. A fifteen-second load at the end of a
season is tolerable; an hour is not, and the budget exists to keep the first from
becoming the second.

## A world is a cube, and the layer count multiplies the chain

A world carries a third axis: the tree level. The Sephirot number ten and the Tree
of Death inverts each of them, which reads as twenty layers. **Twenty is a reading of
his wording and not a ruling**, so both figures are below.

```
layers   chain a world turn   participants   squares   season, 720 turns
   1            1 MB                 655        655       720 MB
  10           10 MB               6,550      6,550     7,200 MB
  20           20 MB              13,100     13,100    14,400 MB
```

The cube figure is the real one. The flat figure sits there only for comparison, and
quoting it for a world that has layers would be wrong by the layer count.

## The collision with constant density, named rather than resolved

Maximum world size and maximum participants cap together, which fixes area per
participant. A third axis can honour that in two ways, and they are not equivalent.

```
density per world   the same 655 participants spread over 20 layers, so a layer
                    holds 33 participants on 33 squares, about six by six
density per layer   the cap applies to each layer, so every layer stays a world
                    and the cube holds twenty times the participants and the storage
```

**These figures assume density per layer.** The ground is his own cap-together rule:
it fixes area per participant, and applying the cap per world would hold that
constant only by shrinking each layer to a six-by-six board, which is not a world and
leaves a zone thirty-three participants to take a level from. Keeping every layer a
world means the cap is per layer, and the storage multiplies.

The consequence is stated plainly rather than softened: **a twenty-layer world costs
twenty megabytes an hour, not one.**

## How often a checkpoint has to be written

A checkpoint is a full state snapshot beside the log, so a load reads one snapshot
and the records since it. The cadence follows from the two ceilings already measured:
512 megabytes is what a ten-second load allows, and 34 megabytes is where the current
full-file save stops keeping up with its own timer.

```
layers   reaches 512 MB in      reaches 34 MB in
   1     512 turns, 21 days     34 turns, 1.4 days
  10      51 turns, 2.1 days     3.4 turns, 3.4 hours
  20      26 turns, about a day   1.7 turns, under 2 hours
```

**A cube saturates the current save path inside two hours.** That settles the
question the whole measurement was for: appending each record and checkpointing
periodically is not an optimisation for later, it is the condition on the first
multi-layer world running at all.

In development.

**The trade is his.** The figure divides world change against participant count, and
one megabyte is a recommendation standing on the ten-second load ceiling and
nothing else.

## Why world size and participant count cap together

A chain holds transitions, so a square costs nothing until something changes it, and
a square changes only where a participant acts. A square's change records are
therefore the same records as that participant's actions, never an addition to them.

```
the seed            one record, once
a square unchanged  nothing
a square changed    the action record of the participant who changed it
```

A world larger than its participants can reach holds squares that never produce a
record, and a world smaller than them crowds every square. Neither is a separate
dial. One budget exhausts at one point, and both caps land on it.

## The density constant, and where it comes from

Squares per participant is fixed by two rules already set rather than chosen here.
Base viewrange is one square, and a zone's level tracks the average character level
of those in it.

```
base viewrange            one square
zone level                follows the participants in that zone
squares per participant   1
```

Above one square a participant the average square is empty, a one-square viewrange
shows nobody, and a zone has no population to take a level from. That fixes the
constant at one square a participant, and it is the number every later unit sizes a
map against.

A world at this density is never large and sparse, and never small and crowded.

## Bytes the chain holds against bytes a participant receives

Viewrange bounds sight and never storage. A chain holding only what one participant
can see would not be a chain. The two figures are separate and both follow from the
budget.

The layer axis multiplies what the chain holds and divides what a participant
receives, so the two figures pull apart rather than together. Higher and lower
layers are visible only to a participant able to enter them, and viewrange bounds
what they see on each one.

```
the chain holds, twenty layers         52,420 records a world turn
one participant, one layer, base range      4 records a world turn
one participant, all twenty layers         80 records a world turn
```

At base viewrange on one layer a participant receives one record in thirteen
thousand. A participant cleared for every layer receives one in six hundred and
fifty-five. A range boost multiplies a participant's share by the squares it adds
and changes nothing about what the chain stores.

Nothing in `src/competition/` carries a zone, a square, a tile, a layer or a
viewrange, so neither figure has a consumer in the code yet.

In development.

## Ordering a world turn, and the tension in it

World actions resolve in timestamp order when the block closes. A transaction
carries a timestamp, and the transaction's own id deliberately excludes it so that
two nodes holding the same transaction agree on its id. The block's id does cover
the block's own timestamp.

```
block_id        covers number, parent, timestamp and the transaction list
transaction_id  covers sender, recipient, function, arguments, gas and status
                and excludes block_number and timestamp
```

Two nodes can therefore hold one transaction with different timestamps, both chains
verify, and the two nodes order the world turn differently. The field the rule
orders by is the one field the id does not protect.

**Recommended direction: the block assigns each transaction its position at close,
and that position enters the transaction id.** The block already carries its
transactions as an ordered list and `block_id` already covers that list, so the
position exists and needs only to be made part of the record's identity.

The two alternatives were weighed and both fail.

```
the submitter's timestamp enters the id   a node can backdate its own action
the block timestamp orders everything     sub-block ordering is lost, which is
                                          the ordering the rule asks for
```

It does not move the ceiling. A position field costs about ten bytes on 399, which
is inside the rounding already taken. It is a change to every id on the chain, so
it is a schema change and it needs its own unit.

In development.

## Cross-zone ties

Turns follow the local market clock and cross-zone sequencing settles on UTC.
Nothing in the chain carries a zone today, so a tie between two zones has nothing
to decide it. Once the position above enters the record's identity, the tie-break
is available without a new field: a transaction's content id is the same on every
node, so ordering equal timestamps by content id is deterministic everywhere.

In development.

## One alarm found while measuring, and why it is not repaired here

Loading his chain makes the platform's own integrity check report every record as
altered.

```
chain NOT verified: 3135 of 3136 blocks altered, 0 parent links broken,
3135 of 3135 transactions altered
```

Recomputing block 1's id and transaction 0's id from their own stored fields gives
values that do not match the stored ones. His file was written before records were
named by the hash of their own contents, and the schema version did not change when
that landed, so the file loads and reads as wholly tampered.

```
stored block 1 hash   0xbc0047e11ff7d701b6729d2b14e57a4823c878162e4d214dfdbf0f0ffe9a1c12
recomputed block 1    0xef257af694dadf5fb42f8de41163013396eda69d6318993b8f774dd6c4f6349f
```

Neither available repair belongs to a measurement unit. Raising the schema version
makes the load delete his file, which destroys 3,136 blocks of his history.
Re-assigning ids on load is the one thing a tamper check must never do. Both change
what the integrity figure means, so the choice is his: keep the existing history
unverifiable, or start the chain again.

The replay premise is unaffected. The state rebuilds correctly from the file; only
the records written before content addressing cannot be verified.

In development.

## What this does not answer

```
the envelope in bytes rather than text   an id is 66 characters of hex and an
                                         address is 42; binary halves both, and
                                         that is a change to the chain's identity
                                         model, not an encoding choice, and it was
                                         not measured
the square count in the code             the density constant gives the figure, and
                                         no module carries a square to apply it to
the world turn allowance                 nothing bounds it today
the layer count                          twenty is a reading of his wording, not a
                                         ruling; ten is shown beside it
```
