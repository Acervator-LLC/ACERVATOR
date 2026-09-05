# Paper Trader Tab

Reference. The third step of [the promotion pipeline](promotion-pipeline.md).
No module implements it.

## The measurement

I asked the repository for every path ever added, deleted or renamed, in every
commit reachable from every ref. Two of the answers carry the word paper, and
both of those are markdown documents. No module, no test, no renderer file.

```
git log --all --diff-filter=ADR --name-only
```

The same query returns modules, a renderer file and four tests for the History
tab, which proves it finds files that existed. The empty result is a statement
about the tree, not about the query.

## What stands in its place

One method assigns nothing-at-all to the four attributes the tab would own. A
legacy code path that reads one of them gets that sentinel rather than an
error, and nothing in the module ever assigns them anything else.

`src/gui/main_tabs/retired_tabs.py` — `RetiredTabsMixin._install_retired_tab_sentinels`

```python
self._paper_trader = None
self._paper_trader_stack = None
self._paper_trader_crypto = None
self._paper_trader_equity = None
```

Two places already expect the tab to arrive. The window treats it as an
isolated screen alongside the Simulator, and the header-strip surface carries
the same pair as a constant. The strip will hide itself the day the tab lands,
with no change to either site.

`src/gui/main_window.py` — `_on_main_tab_changed`

```python
isolated_tabs = {"Simulator", "Paper Trader"}
```

The tab row itself names seven screens, and Paper Trader is not among them.

`src/gui/main_window.py` — `CANONICAL_TAB_ORDER`

```python
CANONICAL_TAB_ORDER = [
    "Trading",
    "Market Inspector",
    "Bot Swarm",
    "Asset Charts",
    "History",
    "Simulator",
    "Console",
]
```

## The Paper Swarm sub-tab is chrome

The Bot Swarm tab adds a third sub-tab labelled Paper Swarm. Its Start button
flips a flag and relabels itself. No bot is constructed, no feed is attached
and no order is recorded.

`src/gui/bot_visualizer.py` — the Start handler inside `_create_paper_bot_row`

```python
def _toggle():
    if bot_data["running"]:
        bot_data["running"] = False
        start_btn.setText("▶ Start")
```

The row dict is read nowhere outside that one module, and only to count the
active rows for a summary label.

`src/gui/bot_visualizer.py` — `_update_paper_summary`

```python
running = sum(1 for b in self._paper_bots if b.get("running"))
total_cap = sum(b["cap_spin"].value() for b in self._paper_bots)
```

Issue #422 carries the caption on that sub-tab, which tells the operator the
rows run live paper bots against real market data.

## What the step is, when it lands

Real time is its defining property. The Simulator replays stored candles as
fast as the machine allows. Paper takes the live feed at the speed the market
delivers it, and that is the whole difference between them.

Live, Paper and the Simulator differ in one thing only: where the data comes
from. The trading logic stays one body of pure code that all three call. Only
the stateful shells fork, which is what keeps a paper run from holding a live
object.

The paper budget is twice the dollar target, so a bot has room to fold without
the exercise ending on the first dip.

Paper sits behind two gates. The Simulator must first reproduce the gate
latches, and Nuclear Mode must survive its loops. Neither is earned yet, which
is why the step is not built.

## What the next build is

Three pieces, and each attaches to something that already exists.

**One.** The tab needs a name in the row. The list is the only thing that
decides tab order, and an entry there is what makes the screen reachable.

*Proposed, not present, in `src/gui/main_window.py`:*

```python
CANONICAL_TAB_ORDER = [
    "Trading",
    "Market Inspector",
    "Bot Swarm",
    "Asset Charts",
    "History",
    "Simulator",
    "Paper Trader",
    "Console",
]
```

Both isolation sites already name the screen, so nothing else in the window
changes when the entry arrives.

**Two.** The step needs its own exchange shell. The Simulator's shell is the
model: it subclasses the exchange interface, holds its own balances, and its
caller advances the tape. Paper's shell subclasses the same interface and takes
its candles from the live connector instead of a stored series. It is a fork,
not an import — no paper object may hold a live one.

*Proposed, not present. It belongs in a package of its own, beside the
Simulator's shell rather than inside it:*

```python
class PaperExchange(ExchangeInterface):
    """Live-feed prices, fake balances. Orders fill against the last ticker."""

    def __init__(self, connector, starting_balances: dict[str, float]):
        self._connector = connector
        self._balances = dict(starting_balances)
```

The base class is `ExchangeInterface` in `src/exchange/base.py`. The
Simulator's shell already subclasses that same one.

**Three.** The budget rule needs a home. Every bot already carries the dollar
target the whole strategy re-zeroes to, and the paper budget is that number
doubled.

`src/trading/container/config.py` — `BotConfig`, the field it doubles

```python
target_balance: float = 200.0  # Balance the bot trades relative to
```

*Proposed, not present, in that same new package:*

```python
PAPER_BUDGET_MULTIPLE = 2.0


def paper_starting_balance(config: BotConfig) -> float:
    """Return the fake budget a paper run of ``config`` starts with."""
    return float(config.target_balance) * PAPER_BUDGET_MULTIPLE
```

The multiple is named once so a later change to the rule has one site.

## The Paper Trade History Tab

The manual's part list names a second History tab reading a paper trade log.
The same query above finds no such module either. `HistoryTab` in
`src/gui/history_tab.py` reads live venue history alone.

In development.

Back to [the subsystem index](README.md).
