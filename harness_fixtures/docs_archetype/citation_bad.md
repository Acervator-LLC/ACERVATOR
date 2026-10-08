# Where an Order Is Placed

Reference. One page of the shape the manual uses, citing each site by a line
number.

## The guard every order passes

Each order leaves the bot through one guard. The guard reads the venue rules
first and refuses a size the venue will not accept.

```
# src/trading/bot_container.py:325
```

## Where the log lands

Nothing in the repository holds a run's output. The log root resolves against
the home directory, so two machines never share a tree.

```
# src/core/log_paths.py:46
# src/core/log_paths.py:99
```

## Which venue answers

One connector serves every crypto venue. It loads the market table once and
sizes each order against the entry it finds there.

The connector table sits at `src/exchange/ccxt_connector.py:1128`, and
src/exchange/ccxt_connector.py line 1181 sizes the order against it.

A line number stops naming the code as soon as anything above it in that file
moves.
