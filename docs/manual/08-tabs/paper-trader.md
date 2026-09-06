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

## Paper Trade History

The manual's part list names a second History tab reading a paper trade log. No
such module exists. `HistoryTab` in `src/gui/history_tab.py` reads live venue
history alone.

In development.

Back to [the subsystem index](README.md).
