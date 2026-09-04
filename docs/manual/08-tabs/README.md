# Subsystem Detail

Reference. One file per subsystem tab, written from the source. Each file
names the module that implements the screen, the symbols inside it, the
bridge method that serves its renderer, and the screen's current state.

The parent section is [08-tabs.md](../08-tabs.md), which carries the
manual's own text for each of these screens.

## Contents

| File | Covers | State |
| ---- | ------ | ----- |
| [portfolio-panels.md](portfolio-panels.md) | The header strip: spendable columns, five counter cards, privacy dots | Live |
| [market-inspector.md](market-inspector.md) | Higher-timeframe scanner, opposing pairs, topology proposals, adopt | Live |
| [bot-swarm.md](bot-swarm.md) | Nodes, Smart Wires, wire credits, the fold-tranche book | Live |
| [asset-charts.md](asset-charts.md) | One candlestick panel per traded symbol | Live |
| [history.md](history.md) | Venue trade history, grading, gate analysis | Live |
| [simulator.md](simulator.md) | Fleet Replay, Stone Tablets, the gate-latch criterion, Nuclear Mode | Live, rebuild in progress |
| [paper-trader.md](paper-trader.md) | What the step is, and the proof no module implements it | Not built |
| [proof-of-accumulation.md](proof-of-accumulation.md) | Identity, Merkle log, competitions, ACRV, the local chain | Engine only, tabs shelved |
| [console.md](console.md) | Python log tail and the emitter signal stream | Live |
| [system-status.md](system-status.md) | Emitter Network and Watchdog, and the proof no tab exists | Not built |
| [settings.md](settings.md) | The User page, the Exchanges page, and what each of the eleven pages persists | Live |
| [promotion-pipeline.md](promotion-pipeline.md) | How a strategy earns its way to real money | Two of four steps |

## The live tab set

`CANONICAL_TAB_ORDER` in `src/gui/main_window.py` lists the seven tabs
the window builds, and `_reorder_main_tabs` moves each into that position
after the builders run:

Trading, Market Inspector, Bot Swarm, Asset Charts, History, Simulator,
Console.

The Trading tab has its own section:
[06-trading-tab.md](../06-trading-tab.md). The Indicator Voting Panel has
[07-indicators.md](../07-indicators.md).

`RetiredTabsMixin._install_retired_tab_sentinels` in
`src/gui/main_tabs/retired_tabs.py` assigns `None` for every screen the
window no longer builds, including the Competition and Local Testnet
tabs, the analytics, risk, journal, alerts and audio pages, and the Paper
Trader. The underlying engines behind several of those keep running; only
the surface is gone.

## How a screen reaches its renderer

`build_registry` in `src/core/desktop_bridge.py` maps a method name to a
view-model function. A surface is a plain function that takes the
request's parameters and returns a serialisable result, and a screen is
reachable exactly when its method appears in that registry. The transport
is one JSON object per line over the pipe the parent process already
owns: no socket and no port.

Each surface module holds the screen as data. Nothing in one imports Qt,
which is why the same view model serves the Qt tab and the renderer
without a second description of the screen existing.

Back to [the manual index](../README.md).
