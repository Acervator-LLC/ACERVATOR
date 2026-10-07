# Where an Order Is Placed

Reference. One page of the shape the manual uses, citing each site by its
symbol.

## The guard every order passes

Each order leaves the bot through one guard. The guard reads the venue rules
first and refuses a size the venue will not accept.

```
# src/trading/bot_container.py, in guarded_place_order
```

## Where the log lands

Nothing in the repository holds a run's output. The log root resolves against
the home directory, so two machines never share a tree.

```
# src/core/log_paths.py, in resolve_log_root
# src/core/log_paths.py, in get_trade_dir
```

## Which venue answers

One connector serves every crypto venue. It loads the market table once and
sizes each order against the entry it finds there.

```
# src/exchange/ccxt_connector.py, in load_markets
```

A symbol survives every edit short of a rename, and a rename is a change the
author of that rename can see.
