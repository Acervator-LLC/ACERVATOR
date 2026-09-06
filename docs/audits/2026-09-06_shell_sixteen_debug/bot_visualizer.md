# `src/gui/bot_visualizer.py`

2,253 source lines. The row registers a panel, the panel draws, and the two
variants show the same values.

## The error

None. Both runs are quoted below.

## Reproduction

The two runs described in [README.md](README.md).

## What each run printed

The Electron shell:

```
bot_visualizer: ok=True late=False registered=True fiber=True react=172
                children=1 markup=22626 fault=None
```

The first 220 characters it drew:

```
⚡ Bot Swarm🖥 Simulator Swarm📄 Paper SwarmBot Swarm   Drag between bots to
connect  •  Right-click wire to disconnect●Privacy Mode: OFFExchange:AllTheme:
nebulamatrixquantumoceanView:ListGridWires:TickerInflowOutflow% OutL
```

The Qt window: the Bot Swarm tab is
`src.gui.bot_visualizer.BotVisualizationTab`, built with no Python error and
showing 50 words, beginning:

```
PAPER TRADER SWARMRun multiple live paper trading bots simultaneously. Each bot
trades a different asset with virtual capital against real market data. Source:
CoinGecko (crypto) or Yahoo Finance (equities). No geographic restrictions.
Total Capital: —Net PnL: —Active Bots: 0SIMULATOR SWARM…
```

All 50 of those words are carried by the models the React panel reads. Two of
them, `Total Capital: —` and `Net PnL: —`, first read as absent; that was the
comparison escaping non-ASCII characters, and after the search was corrected
`bot_visualizer.state` was found to carry both under
`paper_summary_capital_start` and `paper_summary_pnl`.

## The cause

Nothing to diagnose.

## The correction

None to this file.

## The rerun

The Electron run after the unit's other corrections reports the same values:
`ok=True`, `fault=None`, 172 React calls, 22,626 characters of markup. The Qt
window run with `PYTHONWARNINGS=error` reports zero Python errors and text
identical to the first run.
