# Which Module Answers

Reference. One page of the shape the manual uses, naming each block's module
bare, where the names resolve to no file on disk.

## The engine

The engine sells the excess above a dollar target and buys back more on the
dip. Each completed cycle ends holding more of the asset.

`absent_engine_surface` — the tick that runs one cycle

```
HEADING = "Trading"
BUILT = True
```

## The guard every order passes

Each order leaves the bot through one guard. The guard reads the venue rules
first and refuses a size the venue will not accept.

`absent_guard_surface` — the guard

```
MIN_NOTIONAL_USD = 1.0
```

## Where the log lands

Nothing in the repository holds a run's output. The log root resolves against
the home directory, so two machines never share a tree.

`absent_log_surface` — the log root

```
LOG_ROOT_NAME = ".acervator_logs"
```

## Which venue answers

One connector serves every crypto venue. It loads the market table once and
sizes each order against the entry it finds there.

`absent_venue_surface` — the market table

```
MARKET_COUNT = 929
```

Each block above is quoted from the module named above it.
