# Paper Trader Tab

Reference. The third step of [the promotion pipeline](promotion-pipeline.md).
The screen is not built. No module implements it, the tab row does not name it,
and issue #19 carries the initial build-out.

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
