# `src/gui/live_settings/bot_swarm_tab.py`

451 source lines. The row registers a panel, the panel draws, and the two
variants show the same values.

## The error

None. Both runs are quoted below.

## Reproduction

The Electron run described in [README.md](README.md). This tab belongs to the
Live Bot Settings window rather than the main tab book, so the Qt side was
built on its own: `BotSwarmTabMixin._create_bot_swarm_tab` was called twice,
once with a bot whose `_smart_wire_mgr` is `None` and once with an empty
manager, and the text read off the built widget.

## What each run printed

The Electron shell:

```
bot_swarm_tab: ok=True late=False registered=True fiber=True react=42
               children=1 markup=3615 fault=None
```

```
TickerInflowOutflow% OutL1L2L3L4L5L6L7L8
```

The Qt tab with no manager, one label:

```
Bot Swarm not active for this bot. Smart Wire manager has not been attached.
The bot is operating standalone — no wire connections can fire to/from it. …
```

The Qt tab with an empty manager, 14 words:

```
Swarm Connections & Capital Flow
Outbound wires: 0 target(s)   Inbound wires: 0 source(s)
Lifetime wired-in (received): $0.0000
Lifetime wired-out (sent): $0.0000
Net flow (in − out): $+0.0000
Pending wire credits: $0.0000
Bot Swarm manager is attached but this bot has no wire activity yet. …
```

Both long messages are carried whole by `bot_swarm_tab.state`. The four numbers
are not carried as numbers, and they are not meant to be: the model serves the
formats the React side fills.

```
"formats": {
  "outbound_count": "{count} target(s)",
  "inbound_count": "{count} source(s)",
  "money": "${value:,.4f}",
  "signed_money": "${value:+,.4f}",
  ...
```

## The cause

Nothing to diagnose.

## The correction

None.

## The rerun

The Electron run after the unit's other corrections reports the same values.
The Qt tab, built again both ways, shows the same words.
