# Which Module Answers

Reference. One page of the shape the manual uses, naming each block's module
bare, where every name resolves to a file on disk.

## The engine

The engine sells the excess above a dollar target and buys back more on the
dip. Each completed cycle ends holding more of the asset.

`scrumming_bot` — the tick that runs one cycle

```
# src/trading/scrumming_bot.py, in tick
```

## The guard every order passes

Each order leaves the bot through one guard. The guard reads the venue rules
first and refuses a size the venue will not accept.

`bot_container` — the guard

```
# src/trading/bot_container.py, in guarded_place_order
```

## Where the log lands

Nothing in the repository holds a run's output. The log root resolves against
the home directory, so two machines never share a tree.

`log_paths` — the log root

```
# src/core/log_paths.py, in resolve_log_root
```

## Which venue answers

One connector serves every crypto venue. It loads the market table once and
sizes each order against the entry it finds there.

`ccxt_connector` — the market table

```
# src/exchange/ccxt_connector.py, in load_markets
```

## The names this page holds

This sentence names absent_ledger_surface and absent_module_surface in plain
words, and neither name opens a block of its own.

A fenced block carries its own text:

```
`absent_fenced_surface` — a name inside a fenced block
```

The fold ladder spaces its rungs from the dollar target, and
`absent_wrapped_surface` — the fourth rung — sits one step above it.
