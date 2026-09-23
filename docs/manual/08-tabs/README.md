# Subsystem Detail

Reference. One file per subsystem tab, written from the source. Each file
names the module that implements the screen, the symbols inside it, the
bridge method that serves its renderer, and the screen's current state.

The parent part is [08-tabs.md](../08-tabs.md), which points here for every
screen but Main Window, Market Inspector and Asset Charts, and carries the
manual's own text for those three. The rows below run in the
order the tab list in [04-manual-parts.md](../04-manual-parts.md) sets,
which is the order [08-tabs.md](../08-tabs.md) runs its sections in.

## How an update is written down

Each tab has one section, and that section is its file below. An update to a
tab takes a dated subsection under that one heading and never a second section
named for the tab.

```
    ## 2026-09-08 14:20 - #407, #442 - the six zones and their arrows
       date       time    issues addressed   what the update did
```

The date leads so the subsections sort, and they run forward down the page.
An update with no issue behind it writes `no issue recorded` in that field
rather than a number nothing supports. `.claude/rules/documentation.md` bans
an issue number in documentation, and the operator's directive of 2026-09-08
amends it for this header alone; version names stay banned everywhere.

`dev_harness/harness/docs_archetype.py` refuses both halves

```python
rule_id="DOC011"   # two contents sections naming one tab
rule_id="DOC012"   # a dated update that runs backwards
```

## Contents

| File | Covers | State |
| ---- | ------ | ----- |
| [portfolio-panels.md](portfolio-panels.md) | The header strip: spendable columns, five counter cards, privacy dots | Live |
| [simulator.md](simulator.md) | Live's tab forked over Stone Tablets: Validation, Back Test, Portfolio Battery, the gate-latch criterion, the replay layer | Live, rebuilt under issue #117 |
| [paper-trader.md](paper-trader.md) | The live feed, the fake balance, the paper log | Live — issue #19 |
| [proof-of-accumulation.md](proof-of-accumulation.md) | Identity, Merkle log, competitions, ACRV, the local chain | Skeleton tab, engine only — issue #147 |
| [market-inspector.md](market-inspector.md) | Higher-timeframe scanner, opposing pairs, topology proposals, adopt | Live |
| [bot-swarm.md](bot-swarm.md) | Nodes, Smart Wires, wire credits, the fold-tranche book | Live |
| [asset-charts.md](asset-charts.md) | One candlestick panel per traded symbol | Live |
| [history.md](history.md) | Venue trade history, grading, gate analysis | Live |
| [console.md](console.md) | Python log tail and the emitter signal stream | Live |
| [system-status.md](system-status.md) | Emitter Network and Watchdog, the two halves that run today | Skeleton tab — issue #34 |
| [settings.md](settings.md) | The User page, the Exchanges page, and what each of the eleven pages persists | Live |
| [promotion-pipeline.md](promotion-pipeline.md) | How a strategy earns its way to real money | Four of four steps built |

## The live tab set

One list names the ten tabs the window builds, and each one is moved into that
position after the builders run. Two of them are empty: Accumulation and Status.

`src/gui/main_tabs/main_window_surface.py` — `CANONICAL_TAB_ORDER`

```python
CANONICAL_TAB_ORDER = (
    SIM_TAB,
    PAPER_TAB,
    LIVE_TAB,
    CHARTS_TAB,
    INSPECTOR_TAB,
    SWARM_TAB,
    ACCUMULATION_TAB,
    HISTORY_TAB,
    STATUS_TAB,
    CONSOLE_TAB,
)
```

The Live tab has its own section: [06-trading-tab.md](../06-trading-tab.md).
The Indicator Voting Panel has [07-indicators.md](../07-indicators.md).

Every screen the window does not build gets a sentinel instead of a widget, so
a legacy reader gets that sentinel rather than an error. The list covers the
Competition and Local Testnet tabs, the analytics, risk, journal, alerts and
audio pages, and the retired Paper Trader widget, which is not the Paper tab
issue #19 built.

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
