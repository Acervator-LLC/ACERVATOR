# Subsystem Detail

Reference. One file per subsystem tab, written from the source. Each file
names the module that implements the screen, the symbols inside it, the
bridge method that serves its renderer, and the screen's current state.

The parent section is [08-tabs.md](../08-tabs.md), which carries the
manual's own text for each of these screens. The rows below run in the
order the tab list in [04-manual-parts.md](../04-manual-parts.md) sets,
which is the order [08-tabs.md](../08-tabs.md) runs its sections in.

## Contents

| File | Covers | State |
| ---- | ------ | ----- |
| [portfolio-panels.md](portfolio-panels.md) | The header strip: spendable columns, five counter cards, privacy dots | Live |
| [simulator.md](simulator.md) | Fleet Replay, Stone Tablets, the gate-latch criterion, Nuclear Mode | Live, rebuild in progress |
| [paper-trader.md](paper-trader.md) | What the step is, and the two live surfaces that still offer it | Skeleton tab — issue #19 |
| [proof-of-accumulation.md](proof-of-accumulation.md) | Identity, Merkle log, competitions, ACRV, the local chain | Skeleton tab, engine only — issue #147 |
| [market-inspector.md](market-inspector.md) | Higher-timeframe scanner, opposing pairs, topology proposals, adopt | Live |
| [bot-swarm.md](bot-swarm.md) | Nodes, Smart Wires, wire credits, the fold-tranche book | Live |
| [asset-charts.md](asset-charts.md) | One candlestick panel per traded symbol | Live |
| [history.md](history.md) | Venue trade history, grading, gate analysis | Live |
| [console.md](console.md) | Python log tail and the emitter signal stream | Live |
| [system-status.md](system-status.md) | Emitter Network and Watchdog, the two halves that run today | Skeleton tab — issue #34 |
| [settings.md](settings.md) | The User page, the Exchanges page, and what each of the eleven pages persists | Live |
| [promotion-pipeline.md](promotion-pipeline.md) | How a strategy earns its way to real money | Two of four steps |

## The live tab set

One list names the ten tabs the window builds, and each one is moved into that
position after the builders run. The last three are skeletons.

`src/gui/main_tabs/main_window_surface.py` — `CANONICAL_TAB_ORDER`

```python
CANONICAL_TAB_ORDER = (
    TRADING_TAB,
    MARKET_INSPECTOR_TAB,
    BOT_SWARM_TAB,
    ASSET_CHARTS_TAB,
    HISTORY_TAB,
    SIMULATOR_TAB,
    CONSOLE_TAB,
    PAPER_TRADER_TAB,
    SYSTEM_STATUS_TAB,
    PROOF_OF_ACCUMULATION_TAB,
)
```

The Trading tab has its own section: [06-trading-tab.md](../06-trading-tab.md).
The Indicator Voting Panel has [07-indicators.md](../07-indicators.md).

Every screen the window does not build gets a sentinel instead of a widget, so
a legacy reader gets that sentinel rather than an error. The list covers the
Competition and Local Testnet tabs, the analytics, risk, journal, alerts and
audio pages, and the retired Paper Trader widget, which is not the Paper Trader
skeleton the tab row now carries.

`src/gui/main_tabs/retired_tabs.py` — `RetiredTabsMixin._install_retired_tab_sentinels`

```python
def _install_retired_tab_sentinels(self) -> None:
    """Assign None to ``_paper_trader``, ``_competition_tab`` and the rest.

    ``main_window`` tests ``_analytics_tab``, ``_risk_tab``,
    ``_journal_tab`` and ``_alerts_tab`` before refreshing them.
    """
```

The underlying engines behind several of those keep running; only the surface
is gone.

## How a screen reaches its renderer

One registry maps a method name to a view-model function. A surface is a plain
function that takes the request's parameters and returns a serialisable result,
and a screen is reachable exactly when its method appears in that registry.

`src/core/desktop_bridge.py` — `build_registry`

```python
def build_registry() -> Dict[str, Handler]:
    """Return the methods the frontend may call, keyed by method name.

    This is the wiring point for the whole frontend: a surface is
    reachable exactly when it appears here. Surfaces are imported inside
    the function so that the transport above carries no dependency on any
    one domain package.
    """
```

The transport is one JSON object per line over the pipe the parent process
already owns: no socket and no port.

Each surface module holds the screen as data. Nothing in one imports Qt, which
is why the same view model serves the Qt tab and the renderer without a second
description of the screen existing.

Back to [the manual index](../README.md).
