# Paper Trader Tab

Reference. The third step of [the promotion pipeline](promotion-pipeline.md).
The screen is not built. The tab row carries a skeleton, and issue #19 carries
the build-out.

## The skeleton

The tab exists and draws three lines: its name, one sentence saying it is not
built, and the issue that owns it. It reads no bot, no price and no trade.

`src/gui/main_tabs/paper_trader_tab_surface.py` — the whole empty state

```python
HEADING = "Paper Trader"
ISSUE = 19
BUILT = False
STATE_TEXT = "This tab is not built."
ISSUE_TEXT = f"Issue #{ISSUE} carries the build-out."
```

Two frontends draw that one view model. `EmptyTabsMixin` in
`src/gui/main_tabs/empty_tabs.py` builds the Qt tab, and
`src/gui/web/paper_trader_tab.js` registers a panel with the Electron shell's
panel host. `src.core.desktop_bridge` serves the model under
`paper_trader_tab.state`.

## What the step is

Real time is its defining property. The Simulator replays stored candles as
fast as the machine allows. Paper takes the live feed at the speed the market
delivers it, and that is the whole difference between them.

Live, Paper and the Simulator differ in one thing only: where the data comes
from. The trading logic stays one body of pure code that all three call. Only
the stateful shells fork, which is what keeps a paper run from holding a live
object.

The paper budget is twice the dollar target, so a bot has room to fold without
the exercise ending on the first dip.

`src/trading/container/config.py` — `BotConfig`, the field it doubles

```python
target_balance: float = 200.0  # Balance the bot trades relative to
```

Paper sits behind two gates. The Simulator must first reproduce the gate
latches, and Nuclear Mode must survive its loops. Neither is earned yet.

## Where the platform still offers it

Two live surfaces name the step. The first is the Bot Swarm tab's third
sub-tab, labelled Paper Swarm. Its Start button flips a flag and relabels
itself. No bot is constructed, no feed is attached and no order is recorded.

`src/gui/bot_visualizer.py` — the Start handler inside `_create_paper_bot_row`

```python
def _toggle():
    if bot_data["running"]:
        bot_data["running"] = False
        start_btn.setText("▶ Start")
```

The second is the wing toggle on the header strip. Pressing it swaps the whole
wing and writes a line naming that wing's own Paper Trader. Neither wing has
one.

`src/gui/main_window.py` — `_toggle_trading_mode`, the line it writes

```python
"→ STOCK WING: equity exchanges + equity Paper Trader. "
```

Issue #422 carries the first caption and issue #426 the second.

## The screen as it stands now

The tab is built. It sits second on the bar and carries the Trading tab's panes
over the live exchange feed. `src/gui/paper_trader_tab.py` draws them in Qt and
`src/gui/web/paper_trader_tab.js` draws them in React, from one view model.

`src/gui/main_tabs/paper_trader_tab_surface.py` — the fields both hosts read

```python
DECLARED_FIELDS = (
    "accessible_name",
    "balance",
    "built",
    "feed",
    "fleet",
    "heading",
    "indicators",
    "issue",
    "method",
    "panes",
    "privacy_button",
    "reserved_rows",
    "run",
    "skin",
    "symbol",
    "symbols",
)
```

The left pane holds the Privacy Mode button, the market selector, the two button
rows and the bot list. The bot list uses the Trading tab's own columns. The right
pane holds the Indicator Voting Panel, computed from the live window. An empty
selector draws the empty state and invents no reading.

`src/gui/main_tabs/paper_trader_tab_surface.py` — the empty state

```python
def indicator_payload(
    candles: Sequence[Any], timeframe: str, symbol: str, refusal: str
) -> dict:
    model = ivp.IndicatorPanelModel()
    if refusal:
        model.show_no_data(refusal)
        return ivp.build_payload(model)
    summary = multi_tf_summary(candles, timeframe, symbol)
    if not summary:
        model.show_no_data(NO_SYMBOL_TEXT)
        return ivp.build_payload(model)
    model.set_summary(summary, symbol)
    return ivp.build_payload(model)
```

## The two presses

Import Live Fleet reads the stored bot record and lists what it finds. Start
Paper Run opens the run and begins ticking. The same button then reads Stop
Paper Run and ends it, leaving the balances and the trades on screen.

`src/gui/main_tabs/paper_trader_tab_surface.py` — the second row's two faces

```python
{
    "name": DATA_POOL_ROW,
    "height_px": 18,
    "action": STOP_RUN_ACTION if running else START_RUN_ACTION,
    "text": STOP_RUN_TEXT if running else START_RUN_TEXT,
    "button_name": button_name(
        STOP_RUN_ACTION if running else START_RUN_ACTION
    ),
}
```

## Downstream only

The feed reader answers six names and refuses every other one, so a send has no
spelling. It calls the venue's public market endpoints, which carry no key and
no signature.

`src/paper/live_feed_source.py` — the refusal

```python
def __getattr__(self, name: str):
    """Refuse every name outside ``READ_NAMES``."""
    raise SendRefused(
        f"LiveFeedSource answers {READ_NAMES} and cannot {name!r}. "
        "The Paper Trader receives and asks; it sends nothing."
    )
```

## One gate chain

A tick builds the same `GateContext` a live bot builds and evaluates the shipped
scrum and fold chains on it. The paper side adds no gate and changes none.

`src/paper/paper_run.py` — what a tick evaluates

```python
window = list(candles[-WINDOW_CANDLES:])
reading = bb_reading(window, bot)
summary = VotingEngine().compute_all(window, bot.ta_timeframe, symbol=bot.symbol)
context = tape_context(bot, balance, window, reading, summary)
armed = latch(context)
```

## The fake balance

Each bot opens a budget of twice its dollar target: units worth the target, and
the rest in cash to fund a fold. The balances live in memory and are dropped when
the tab goes away.

`src/paper/fake_balance.py` — the opening

```python
def opening_balance(target_usd: float, price: float) -> FakeBalance:
    whole = budget_usd(target_usd)
    held_usd = min(whole / BUDGET_MULTIPLE, whole)
    units = held_usd / float(price) if float(price) > 0.0 else 0.0
    return FakeBalance(
        units=units,
        cash_usd=whole - units * float(price),
        tranches=0,
        budget_usd=whole,
    )
```

## The fleet ledger

The fake balance is one figure for the whole fleet, not one figure per bot. Five
paper bots with a $200 target open Paper Spendable at $1000 and Paper Locked at
$1000. Each variable holds the full fleet sum, which is twice the fleet's dollar
target in total.

`src/paper/fake_balance.py` — the opening

```python
def opening_ledger(bots: Sequence[Any]) -> PaperLedger:
    total = fleet_target_usd(bots)
    return PaperLedger(
        fleet_target_usd=total,
        opening_spendable_usd=total,
        opening_locked_usd=total,
    )
```

The fleet changes when a bot is added or removed. Every press of Start Paper Run
rebuilds the ledger from the fleet it is handed, so both opening figures move on
the next press and never inside a run. Six $200 bots open $1200 in each figure
and four open $800.

Four figures are tracked. Paper Spendable is the cash the fleet holds. Paper
Locked is what its units are worth at the last price the feed answered. Paper
Realized Profits moves when a fold buy closes the tranche a scrum sell opened.
Paper Mature Profits is the profit on positions past 200 percent growth, the
figure the live wing already reads.

`src/trading/smart_wire.py` — the maturity rule both wings call

```python
MATURE_GROWTH_PCT: float = 200.0
"""A position is mature once its value exceeds its cost basis by this percent."""
```

The four figures are held apart from the live ones. They live in memory on the
run, they are never written into the stored bot record, and no paper figure
reaches the header strip's real-money columns.

`src/paper/fake_balance.py` — the four labels the strip prints

```python
FIGURE_LABELS = (
    ("spendable_usd", SPENDABLE_LABEL),
    ("locked_usd", LOCKED_LABEL),
    ("realized_profit_usd", REALIZED_LABEL),
    ("mature_profit_usd", MATURE_LABEL),
)
```

The Qt window and the React page print one line from one view model, so the two
hosts cannot report different money.

`src/gui/main_tabs/paper_trader_tab_surface.py` — the one line

```python
"text": LEDGER_SEPARATOR.join(f"{one['label']} {one['text']}" for one in cells),
```

## The Paper Trader log

Every paper action is written to one file. Each line carries two halves: the
gate decision that produced the action and, when one filled, the pretend trade
in the shape a Coinbase year-to-date row takes. Validation reads both of those
shapes already, so a paper run is checked by the reader that checks the live
wing.

`src/paper/paper_log.py` — the row

```python
return {
    "timestamp": iso_stamp(tick.wall_ms),
    "category": CATEGORY,
    "exchange": str(exchange_id),
    "bot_id": str(tick.bot_id),
    "data": gate_half(tick),
    "trade": trade_half(tick.filled) if tick.filled is not None else None,
    "ledger": dict(figures or {}),
}
```

The log has a home of its own. It is a sibling of the live folders and never
sits inside one, so nothing a paper run writes can land in a live tree.

`src/paper/paper_paths.py` — the root

```python
PAPER_ROOT: Path = Path.home() / ".acervator_paper"
```

Gate names come from one place. The row records the blocker phrases the chain
produced and the labels those phrases map to, and it spells no gate name of its
own.

`src/trading/gate_vocabulary.py` — the mapping the log calls

```python
def gate_for_blocker(blocker: str) -> str:
    """Map one blocker string to its gate label, or "" if unknown."""
```

A trade is never invented. A line carries a trade half only because the gate
chain latched and the fill was applied to a fake balance.

`src/paper/paper_run.py` — the only writer

```python
paper_log.append_row(
    paper_log.paper_row(seen, bot.exchange_id, run.figures())
)
```

## Real time

A run ticks on the wall clock and asks the feed for one bot per fire, so a fleet
of many bots never blocks the window on a single pass. One bar is shared across
the open bots.

`src/gui/paper_trader_tab.py` — the round robin

```python
def advance_once(self) -> list:
    """Tick the next open bot against its newest live window."""
    if self._run is None or not self._run.running or not self._run.bots:
        return []
    chosen = self._run.bots[self._cursor % len(self._run.bots)].bot_id
    self._cursor += 1
    made = surface.advance_run(self._run, self._feed, chosen)
    self.refresh()
    return made
```

## Paper Trade History

The manual's part list names a second History tab reading a paper trade log. No
such module exists. `HistoryTab` in `src/gui/history_tab.py` reads live venue
history alone.

The ledger such a tab would read now exists. Every paper action lands in the
file [the Paper Trader log](#the-paper-trader-log) names, and no screen reads
that file yet.

In development.

Back to [the subsystem index](README.md).
