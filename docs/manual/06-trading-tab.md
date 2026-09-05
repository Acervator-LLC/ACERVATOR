# System Architecture and Features Catalogue

Acervator features a semi-modular / layered design that nests a hyper-vigilant trading engine capable of operating in multiple investment domains simultaneously and all from one terminal. The Main Window contains all of the various subsections found in each subsystem tab. As it stands the existing and planned subsystem tabs are: Simulator, Paper Trading, Trading (Live), Market Inspector, Bot Swarm, Asset Charts, History, Console, Proof of Accumulation (PoA), and System Status. Most of these subsystems interact with each other to some degree with key isolations existing between the three trading tabs and their wiring to Market Inspector, Bot Swarm, and History.

## Trading Tab

Here you see the first subsystem we are going to cover and this will primarily be due to familiarizing the prospective investor or user with the core trading philosophy and strategies that drive Acervator. To begin, the platform runs locally on whichever hardware is selected. A single authorization phase requiring a purchased license key will be the only non-exchange communication the application will ever need. The user’s keys and secrets are stored locally and encrypted after API handshake verification passes which allows the chosen exchange to be initialized. At a later development stage, I have plans for dedicated hardware that uses a hardware key for quick boot into a given user’s account and also allows the platform to run in isolation under Linux.

![The Trading tab, with Privacy Mode on.](p15-i0.png)

#### The screen itself

**Functional.** One method builds this whole screen. It makes two layers, one
for crypto and one for equities, and stacks them so only one is on show at a
time. The crypto layer opens first. A second method builds the strip along the
top, and that strip stays put on every tab. Privacy Mode is on in the figure,
so each masked field draws four asterisks where its number would be.

`src/gui/main_tabs/trading_tab.py` — `TradingTabMixin._build_trading_tab`

```python
self._trading_stack.addWidget(crypto_page)  # index 0
self._trading_stack.addWidget(stock_page)  # index 1
self._trading_stack.setCurrentIndex(0)  # start in crypto
```

**Design intention.** One terminal, several investment domains at once. The
two-layer stack is the part of that aim you can use today. Pressing the mode
button swaps the whole wing, tables and Paper Trader together.

`src/gui/main_window.py` — `_toggle_trading_mode`

```python
self._trading_mode = "stock"
self._mode_btn.setText("Stock Mode")
self._mode_btn.setChecked(True)
self._trading_stack.setCurrentIndex(1)
```

The Modulus Bot and the Paper Trading layer named in the paragraph above have
no module behind them. This manual marks them unbuilt where it reaches them.

#### The header strip

**Functional.** Five columns and five counter cards run along the top. The
columns read SPENDABLE, REALISED, LOCKED, MATURE and EXCH. One call to
`get_aggregate_stats` fills all of them once a tick. Spendable takes the wallet
cash, Locked takes the value tied up in crypto, and Exch counts the open
exchange sub-tabs. Realised and Mature are handed nothing at all, and the
widget draws an em dash for each. Privacy Mode then masks that em dash to
asterisks, which reads on screen as a hidden number rather than a missing one.

The five cards are Scrummed, Folded, Trades, Bots and Errors. Scrummed and
Folded total the fleet's sold and bought dollars, Bots counts the bots that are
running, and Errors totals the lifetime error count. Click Errors and the
rolling error log opens. The small circle under every column and every card is
a privacy dot, and it masks that one field on its own.

`src/gui/main_window.py` — `_refresh_dashboard`

```python
if _wallet_cash > 0 or _crypto_value > 0:
    self._spendable_widget.update_profits(
        {
            "spendable": _wallet_cash,
            "total_realised": None,
            "locked": _crypto_value,
            "mature": None,
            "exchange_count": exchanges,
        }
    )
```

**Design intention.** The strip should answer one question at a glance: what
the fleet holds, what it has earned, and what it has spent. Two of the five
columns do not answer it. Realised profit and matured profit are the numbers
those columns were built for, and nothing computes either one. The aggregate
already carries a realised total, so the first half is a short change at the
one call site.

*Proposed, not present:*

```python
self._spendable_widget.update_profits(
    {
        "spendable": _wallet_cash,
        "total_realised": float(agg.get("total_realised_pnl", 0.0) or 0.0),
        "locked": _crypto_value,
        "mature": None,
        "exchange_count": exchanges,
    }
)
```

`total_realised_pnl` is already read two lines above this call, for the
Scrummed card. Mature has no source yet and stays an em dash.

[08-tabs/portfolio-panels.md](08-tabs/portfolio-panels.md) covers the strip in
full.

#### The tab row

**Functional.** The row of main tabs takes its order from one list. Each label
in the list is moved to its own index at build time. Any tab the list does not
name keeps the position it was added at.

`src/gui/main_window.py` — `_reorder_main_tabs`

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
self._reorder_main_tabs(CANONICAL_TAB_ORDER)
```

**Design intention.** The order should read as the working order. Trade first,
then the screens that inspect the trade, then the screens that replay it. One
list decides it, so the order cannot drift as tabs are added. A tab the list
never names is left exactly where it was.

`src/gui/main_window.py` — `_reorder_main_tabs`

```python
tab_bar = self._main_tabs.tabBar()
for target_idx, name in enumerate(desired):
    for cur_idx in range(self._main_tabs.count()):
        if self._main_tabs.tabText(cur_idx) == name:
            if cur_idx != target_idx:
                tab_bar.moveTab(cur_idx, target_idx)
            break
```

#### One sub-tab per exchange

**Functional.** One sub-tab holds one exchange. Along its header sit Privacy
Mode, a news headline, and the + New Bot button that opens the wizard for this
venue. Privacy Mode toggles all eighteen masks at once. Under the header is a
data pool line: how many slots are held by kind, the age of the freshest and
the oldest, how many have run past their time to live, and the cache hit ratio.
At the right of the sub-tab row sits the button that adds another venue.

`src/gui/widgets/exchange_tab.py` — `ExchangeTab.__init__`

```python
self._privacy_mode_btn = QPushButton("Privacy Mode: OFF")
self._privacy_mode_btn.setToolTip(
    "Toggle ALL 18 privacy masks at once. When ON, every "
```

**Design intention.** One venue, one tab, one swarm. Add a second exchange and
it arrives beside the first with its own bots and its own data pool, and
nothing about the first changes.

`src/gui/main_window.py` — `_sync_exchange_tabs`

```python
def _sync_exchange_tabs(self) -> None:
    """Add a tab for each configured exchange missing one, in its own layer."""
```

#### The bot tables

**Functional.** The Scrumming Bots table carries ten columns. Nine are named
and the tenth is blank, because that one holds the Detail button. Mode is the
coloured cell: green while running, amber while paused, grey while idle or
stopped, red on error, orange in cooldown, cyan while starting. Ammo is the
distance between what the position is worth now and its Target. It draws green
above the target, red below it, and neutral grey inside the dust band. Target
BTC and Target ETH restate the Target in those two assets, and go blank when
the pair is unlisted or when the target already is that asset. The Extractor
table sits underneath. Both tables start hidden and appear when their own list
gains a row.

`src/gui/widgets/bot_status_table.py` — `BotStatusTable.SCRUMMING_COLUMNS`

```python
SCRUMMING_COLUMNS = ColumnSpec(
    labels=(
        "Bot ID",
        "Symbol",
        "Mode",
        "Trades",
        "Target",
        "Target BTC",
        "Target ETH",
        "Ammo",
        "Fire",
        "",
    ),
```

**Design intention.** Ammo is the operator's own word for Target Delta, defined
under Scrumming Bot Terms below. The column exists so you can see, in one
sweep of the table, how much value each bot is holding ready to fire.

`src/gui/widgets/bot_status_table.py` — the target the Ammo cell measures
against

```python
target_val = float(
    status.get("live_target_balance", status.get("target_balance", 0.0))
    or status.get("target_balance", 0.0)
    or 0.0
)
```

The live target comes first, so the reading follows the grown balance the
engine re-zeroes to rather than the frozen number typed into the wizard.

#### The command bar

**Functional.** Start, Pause, Stop, Restart and Delete all act on one bot. Two
tables share the bar, so the bar takes its bot from whichever table you clicked
last. If that table holds no selection it tries the other one. If neither holds
a selection it says "Select a bot first." and does nothing.

`src/gui/widgets/exchange_tab.py` — `ExchangeTab._cmd`

```python
def _cmd(self, command: str) -> None:
    if self._last_clicked_table == "extractor":
        bot_id = self._extractor_table.get_selected_bot_id()
        if not bot_id:
            bot_id = self._bot_table.get_selected_bot_id()
    else:
        bot_id = self._bot_table.get_selected_bot_id()
        if not bot_id:
            bot_id = self._extractor_table.get_selected_bot_id()
```

**Design intention.** One command bar for two tables means the bar has to guess
which bot you meant. The last table you clicked is the tie-breaker, and the
fallback keeps a stray click from swallowing the command. With nothing selected
anywhere it refuses out loud rather than acting on a guess.

`src/gui/widgets/exchange_tab.py` — the refusal

```python
if not bot_id:
    if self._status_log:
        self._status_log.log("Select a bot first.", "warning")
    return
```

#### The rest of the screen

The right half is the Indicator Voting Panel, described at the end of this
section. The two panes at the foot are the Activity Log and the API Interaction
Log. The status bar carries the API load pill written by
`_refresh_api_load_pill` and the `AI:` state label.

1 - Add Exchange - User provides valid API key and secret for target exchange - Platforms validates with an API handshake - Exchange Initializes

After an exchange is connected to the platform, bots can be added to target entire or portions of existing positions as well as using standing liquidity to enter positions for the first time. The two primary bots used by Acervator are known as Scrumming and Extractor with the conceptual Modulus Bot to be added later. The first two are the active traders that continuously interact with the market whereas the Modulus Bot will be a macro-strategic interface designed to trigger portfolio-scale shifts in response to custom market signals and it can best be visualized as a modular synthesizer with investment and market-specific functions.

### Scrumming Bot

If Acervator has a crown jewel, this is it. The scrumming bot is what houses and executes the harvest-fold method and the harvest-fold method is what leads to the creation of the platform itself. All else stems from this origin point and the simple revelation that allowed the method to be discovered (or probably rediscovered) by nonmathematical eyes. Instead of paying attention to what my entire portfolio was doing, I opted to start focusing on a single position until I had found a strategy that was more reliable than Grid Bots or standard speculation. I was convinced such a method existed and thought it absurd that price charts could not be played better when there was obviously so much room for improvement. You do not have to predict the market. You flow and mold your portfolio to it as time goes. Scrumming allows profits to be shaved off, held and re-investment in a cyclical, reliable manner that sizes its trades in direct proportion to actual market movement as it relates to position value drift. Trading in this manner allows a fixed balance for a position to be maintained and asserts the truth that “Position X is Y value. Any deviation from Y is a Target Delta and is subject to a Scrum (Sell) or Fold (Buy).” The primary weaknesses to this strategy are not have an equal amount of liquidity to the position value (a $500 Scrumming Bot should be supported by $500 of liquidity when initialized) and severe market downturns will little or no short term upside which can lock most liquidity for the position into the Target Asset. Scrumming is a survival strategy and is directionally agnostic but also depends on the market to cycle. I also refer to this simply as Accumulation Trading.

### Scrumming Bot Terms

Target Balance - The initial value of the position to be taken or controlled by the Scrumming Bot. The bot will monitor the market for bullish or bearish conditions, check for Target Balance deviations (Target Delta), and re-zero back to the set point. It will repeat this until stopped by the user or some other market condition.

Target Delta - The amount by which a position value has drifted from the Target Balance. The Target Delta is denoted by the Ammo column under the Scrumming Bot list of the Trading Tab. This is the amount of value that will be fired during the appropriate market conditions.

Scrum - To sell an amount from an investment position that allows it to return to its initial price level. This never closes the position. This is the first half of the infinitely divisible circle that can persist for such positions in a healthy market.

Fold - To buy an amount for an investment position that allows it to return to its initial price level. This also drives Compounding Growth based on Local Volatility and is restricted by the Maximum Growth Per Cycle setting which has been set to a conservative 1% globally for Acervator’s live test and development run.

![The wizard's first page: Trading Mode, with Scrumming selected.](p16-i0.png)

When the +New Bot button is pressed, the above window appears. Currently there are two “trading mode”

options (this will be change to Strategies). We are only interested in the Scrumming Bot at this point.

**Functional.** This is the wizard's first page, and the wizard opens on it.
Two radio buttons, one description under each. Accumulation Trading is already
selected when the page opens, and its description promises 12-indicator voting,
which is what the engine builds. Choosing Base Currency Extractor sends you to
the Extractor Pool page instead of the asset page. One question decides that
branch, and the rest of the wizard asks the same question whenever it needs to
know which kind of bot it is building.

A third mode, Grid, is retired. Its test returns False without looking at a
widget, and the branch that reads it is marked unreachable in the source.

`src/gui/bot_wizard.py` — `BotCreationWizard.nextId`

```python
def nextId(self):
    current = self.currentId()
    if current == PAGE_MODE:
        if self._mode_page.is_extractor():
            return PAGE_EXTRACTOR_POOL
        return PAGE_ASSET
```

**Design intention.** These two entries become Strategies, in the operator's
own words above. A strategy list is the shape wanted; two radio buttons is the
shape built. What a strategy entry should carry beyond a label has not been
decided, so nothing is proposed here.

In development.

![The wizard's asset page: exchange, base currency and target asset.](p17-i0.png)

After Scrumming / Accumulation is selected, next we are presented with Exchange, Base Currency, and Target Asset options.

Exchange - A privately and federally licensed financial platform that allows API interfacing for remote or automated trade execution.

Base Currency - This will be a National Currency, Stable Coin, or High Volume Crypto (BTC, ETH, BNB) for which multiple trading pairs are available on the selected exchange.

Target Asset - This is the asset in which the scrumming bot bases its position. If $50 and ZEC are selected, it will strive to maintain and compound against a balance of $50 in ZEC until it is shut down or some other adverse market condition occurs.

**Functional.** Four rows. Pick the exchange and the page re-scans that venue,
keeping only the spot markets the venue itself marks active. Base Currency is a
fixed list of seven. Target Asset then lists every asset trading against the
base you chose, each with a cached coin icon and, where the venue reported one,
a 24-hour volume figure. The list sorts by that volume. The round information
button opens a written description of the selected asset. The line under the
rows counts the pairs found, and says the list is in volume order when at least
one pair carried a volume.

`src/gui/bot_wizard.py` — `AssetSelectionPage`, the base list

```python
self._base.addItems(["USDT", "USDC", "BTC", "ETH", "BNB", "EUR", "USD"])
```

`src/gui/bot_wizard.py` — the market filter inside `_fetch_markets`

```python
for sym, info in exch.markets.items():
    if (
        not info.get("active", True)
        or info.get("type", "spot") != "spot"
    ):
        continue
```

**Design intention.** The three definitions above are the intention for these
rows, and the code meets them. The base list holds exactly the national
currencies, stable coins and high-volume crypto named there. Sorting by volume
puts the tradeable pairs at the top of a list that runs to several hundred
entries on a large venue, and the sort reads a cached figure rather than
fetching one, so opening the list never stalls the screen.

`src/gui/bot_wizard.py` — the volume sort

```python
# Cached volume only, since a network fetch here blocks the GUI thread.
filtered.sort(
    key=lambda m: _market_number(m.get("volume")) or 0.0, reverse=True
)
```

### Trading Parameters

Next we come to the combined Scrumming Bot configuration page which has several sections for fine tuning how the specific instance behaves. Given that Acervator, at the time of this writing, is still in active development the description for each setting should be seen as a design intention should any issues be encountered.

![The Trading Parameters group of the wizard's parameter page.](p18-i0.png)

**Functional.** This page holds eight groups for a Scrumming Bot and one for an
Extractor, all in one scroll area. You see one side or the other, never both.
The first group holds seven controls, listed here with the range each accepts
and the value it starts at:

- Order Visibility: Order Book (Visible) or Internal (Invisible).
- Aggressive Trading (force IOC-limit takers), a checkbox, off at the start.
- Stack Mode (split SCRUM across upward tranches). Its start state is read from
  the engine, not typed into the page twice.
- Split Distance, a percentage from 0.10 to 20.00, at 1.00 %.
- Tranche Count, a whole number from 2 to 20, at 3.
- Spacing: Linear, Quadratic or Exponential. The sequence beside each name is
  the cumulative distance from the anchor in units of Split Distance.
- Personal Hold (units), target-asset units the bot holds out of its own
  decision maths and out of any sibling bot's view.

Tranche Spread appears in the list below. The page carries no such control, and
this group emits no setting of that name.

`src/gui/bot_wizard.py` — `TradingParamsPage`, the Stack Mode default

```python
from ..trading.bot_container import STACK_MODE_DEFAULT

self._stack_mode = QCheckBox(
    "Stack Mode (split SCRUM across upward tranches)"
)
# One declaration, so the box and the config cannot disagree.
self._stack_mode.setChecked(STACK_MODE_DEFAULT)
```

`src/gui/bot_wizard.py` — `TradingParamsPage.get_config`, the settings this
group emits

```python
"stack_mode": self._stack_mode.isChecked(),
"split_distance": self._split_distance.value(),
"stack_tranche_count_target": int(self._stack_count.value()),
"stack_spacing_mode": self._stack_spacing.currentData(),
"personal_hold_qty": float(self._personal_hold_qty.value()),
```

**Design intention.** The operator says it plainly in the paragraph above the
figure: read each description below as a design intention, not as a report of
what happens. Tranche Spread is the clearest case. He describes it, he marks it
"not available yet", and Split Distance and Tranche Count are already there
waiting for it. What the control should look like on the page has not been
decided, so nothing is proposed here.

In development.

Order Visibility - Trades are listed on the order books or tracked internally to the platform.

Aggressive Trading - Trades are priced so that they fill immediately. Trading like this is a bit like guerilla warfare. In and out before anyone notices.

Stack Mode - Stack Mode enables Stack Tranches which operate on the Sell or Scrum side. This forms the “upside” of the organic ladder structure whereas Fold Tranches form its “downside”.

Split Distance - This setting determines the spacing between tranches if Tranche Spread (not available yet) is being used.

Tranche Spread - This allows a given Scrum or Fold to divide its result X# of times across multiple incremented (as dictated by Split Distance) positions.

Tranche Count - This can also be referred to as Spread Count. It determines how pieces a given Scrum or Fold is split into and distributed across incremented tranches as opposed to just one.

Spacing - This adds a scaling factor Split Distance and works in conjunction with Tranche Spread and Tranche Count to induce curves and more aggressive growth within the ladder structure.

Personal Hold - Setting to be removed.

![The Scrumming Settings group.](p19-i0.png)

**Functional.** The same page, scrolled down. Ten rows, each named here with
the range the widget accepts and the value it starts at:

- Opposing Trade Interval, 0.10 % to 20.00 %, at 1.00 %.
- BB Tolerance, 0.25 % to 5.00 %, at 1.00 %.
- Landing Strip Candles, 2 to 10, at 3.
- TA Timeframe. The list starts with seven entries and 1h chosen. Pick an
  exchange and the list is rebuilt from the timeframes that venue carries, so a
  venue without 4h does not offer it.
- Target Balance, $1.00 to $1,000,000.00. Its start value is whatever default
  the wizard was handed.
- Max Entry Price, eight decimal places, at $0.00000000, where zero means no
  ceiling.
- Min Entry Price, the same shape, where zero means no floor.
- Trading Fee %, 0.00 % to 5.00 %, at 0.60 %.
- Max Target Growth %, 0.00 % to 100.00 %, at 1.00 %.
- Scrum Fold Ratio, 1 % to 100 %, at 100 %.

Two of these read differently in the engine than their labels suggest. The buy
path is the only place either entry-price field is read. It refuses a buy above
the ceiling and refuses a buy below the floor. Neither number ever reaches the
sell path, so the pair works as a buy window and nothing else. Manual Fire runs
its own rebalance and reads neither.

`src/gui/bot_wizard.py` — `TradingParamsPage.get_config`, the settings this
group emits

```python
"scrumming_interval_pct": self._scrumming_interval.value(),
"bb_tolerance_pct": self._bb_tolerance.value(),
"bb_landing_strip_candles": self._ls_candles.value(),
"ta_timeframe": self._ta_timeframe.currentData(),
"target_balance": self._target_balance.value(),
"max_entry_price": (float(_max_ep) if _max_ep > 0 else None),
"min_entry_price": (float(_min_ep) if _min_ep > 0 else None),
"trading_fee_pct": self._trading_fee.value(),
"max_target_growth_pct": self._max_target_growth_pct.value(),
"scrum_fold_pct": self._scrum_fold_pct.value(),
```

`src/trading/scrumming/execution.py` — `_execute_buy`

```python
_max_ep = getattr(self.config, "max_entry_price", None)
_min_ep = getattr(self.config, "min_entry_price", None)
try:
    _px = float(price) if price is not None else 0.0
except (TypeError, ValueError):
    _px = 0.0
if _max_ep is not None and _px > 0 and _px > float(_max_ep):
```

**Design intention.** The operator's definitions below carry the intention for
each row, and two of them do not match what runs.

He calls Min Entry Price an exit threshold. He goes further and writes "(Should
Be Exit)" into the heading himself. The buy path is the only reader, so a bot
that holds the asset and reaches that price sells nothing. The sell path takes
the price already, so the check has somewhere to attach.

*Proposed, not present, in `_execute_sell`:*

```python
_min_ep = getattr(self.config, "min_entry_price", None)
if _min_ep is not None and price > 0 and price < float(_min_ep):
    self._bus.emit(
        "bot.log",
        bot_id=self.bot_id,
        message=(
            f"SELL REFUSED (min_entry_price floor): current price "
            f"${price:.8f} < ${float(_min_ep):.8f}."
        ),
    )
    return None
```

`min_entry_price` is declared in `src/trading/container/config.py` and reaches
the bot through the wizard block above, so the proposal adds no new setting.

The second gap is Max Target Growth %. He describes one hard limit per market
cycle. The engine holds two different answers for a bot whose stored config
lacks the key: nine read sites fall back to 1.0 and three fall back to 0.0. A
bot then compounds or freezes depending on which site read it first. The
declared default is 1.0, and the three outliers should say the same.

*Proposed, not present, at each of the three sites:*

```python
_growth = float(getattr(self.config, "max_target_growth_pct", 1.0) or 0.0)
```

The three outliers are the manual rebalance, the compounding snapshot and the
SWOS inputs.

```
src/trading/scrumming/execution.py   _execute_manual_rebalance
src/trading/scrumming/snapshots.py   _compounding_snapshot
src/trading/scrumming_bot.py         get_swos_inputs
```

Scrolling down we next find the first block of Scrumming Settings. These are the core or basic metrics for a Scrumming Bot.

Opposing Trade Interval - Establishes the minimum travel distance required by price action from the point a given trade in order the next trade of the opposite type to occur.

BB Tolerance - Determines the minimum distance of the Bollinger Band extent price action must be in order for a trade action to occur.

Landing Strip Candles - Determines the strictness of Landing Strip detection. Minimum is three candles. Longer Landing Strips are historically more likely to indicate an impending market reversal than shorter ones assuming the taper remains intact or grows tighter.

TA Timeframe - This is the timeframe at which the bot operates and denotes the price chart it will monitor for trade decisions.

Target Balance - This is the intended starting and locked value for the investment position that the Scrumming Bot is controlling.

Max Entry Price - If the new bot does not detect the requisite amount (as dictated by Target Balance) of the Target Asset, this price threshold sets a limit at which it will attempt to perform the initiating Fold.

Min Entry (Should Be Exit) Price - If the new bot detects a requisite amount (as dictated by the Target Balance) of the Target Asset, this price threshold sets a limit at which it will attempt to perform the initiating Scrum.

Trading Fee % - This allows the trading fee for the target exchange to be set. This is added to Minimum Opposing Trade Distance to further ensure buys / sells are properly distant and that a given bot is not losing an excessive amount to fee chop in volatile but overly tight market regimes.

Max Target Growth % - This determines the maximum amount of growth the Target Balance can increase in a given Market Cycle with a cycle being a Fold / Scrum / Fold sequence. Essentially any Fold preceded by a Scrum will be allowed to Fold an amount of profit back in and, if Surplus remains after the Target Delta is re-zero’d, it can be used to increase Target Balance up to this hard limit for that cycle. This is the organic compounding mechanic.

Scrum Fold Ratio - This precedes Surplus calculation as described under Max Target Growth %. It determines how much of a given trade’s profits will be redistributed to directly contribute to its own organic compounding. Note that this does not interfere with normal Target Delta re-zeroing and is intended to only serve as a “cushion” to slow runaway compounding when Wire Credits are being received from multiple sources.

![The Advanced Scrumming and Hedge Rebalance groups.](p20-i0.png)

**Functional.** Seven rows in the advanced group, then two in the hedge group:

- Detect Threshold, 10 % to 90 %, at 75 %. The distance from the Bollinger
  midline to the band, as a percentage, before the bot moves from search to
  track. At 75 the engine reads that as a lower mark of 0.125 and an upper mark
  of 0.875, measured across the band rather than in dollars.
- Fire Threshold, 0.10 % to 10.00 %, at 0.50 %.
- BB Midline Gate, a checkbox, on at the start. When on, a scrum fires only
  above the midline and a fold only below it.
- Read Rate, 1 to 60 minutes, at 5 minutes. The search-mode read rate.
- Band Travel, 0 % to 100 %, at 70 %. Zero switches it off.
- BB Bullseye Check, a checkbox, on at the start.
- Wire Inflow Stack, 0.00 % to 100.00 %, at 1.00 %.
- Hedge Rebalance Active, a checkbox, on at the start.
- Hedge Balance, at $200.00, a reserve held apart from Target Balance.

The group title on screen carries an internal release identifier after the
words Advanced Scrumming.

`src/gui/bot_wizard.py` — `TradingParamsPage.get_config`, the settings these
two groups emit

```python
"scrum_detect_pct": self._scrum_detect_pct.value(),
"scrum_fire_pct": self._scrum_fire_pct.value(),
"bb_midline_gate": self._bb_midline_gate.isChecked(),
"scrum_read_rate_min": self._scrum_read_rate.value(),
"band_travel_pct": self._band_travel_pct.value(),
"bb_bullseye_check": self._bb_bullseye.isChecked(),
"wire_inflow_stack_pct": self._wire_inflow_stack_pct.value(),
"hedge_rebalance_active": self._hedge_rebalance.isChecked(),
"hedge_balance": self._hedge_amount.value(),
```

`src/trading/scrumming/circuit_breakers.py` — `_bb_detect_thresholds`, where
Detect Threshold becomes a band position

```python
detect_frac = max(0.0, min(1.0, detect_pct / 100.0))
half = detect_frac * 0.5
return (0.5 - half, 0.5 + half)
```

**Design intention.** Calibrating the scope, in the operator's words below.
Four of the nine rows carry his own note, "To be re-evaluated": Detect
Threshold, Read Rate, Band Travel and Wire Inflow Stack. Read those four as
open questions rather than settled design. No replacement has been chosen for
any of them.

In development.

Next are the “advanced” Scrumming settings which primarily affect when the bot is allowed to fire a trade. These can be thought of as “calibrating the scope”.

Detect Threshold - Intended as the point at which the bot “takes the safety off” and starts looking for a shot. To be re-evaluated.

Fire Threshold - The final Bollinger Band approach metric. Once satisfied, the bot can fire a trade.

BB Midline Gate - This is another, perhaps redundant layer, of Bollinger Band travel protection. It is different in that it is concerned with distance from the midline instead of the entire local width.

Read Rate - To be re-evaluated.

Band Travel - Previously described. To be re-evaluated.

BB Bullseye Check - If current price and Bollinger Band thresholds are equal, the user can opt to perform a double-sized trade.

Wire Inflow Stack - To be re-evaluated.

Hedge Rebalance Active - Determines if Current Price drifting below Initial Entry Price will have a limited amount of funds that can be used to keep re-zeroing the Target Delta at key bearish thresholds or areas of possible reversal.

Hedge Balance - Sets a limit on the amount of additional liquidity a given bot is allowed to absorb when Current Price drifts below Initial Entry Price.

![The Circuit Breakers group.](p21-i0.png)

**Functional.** Six rows:

- Soft CB Threshold, 0.0 % to 100.0 %, at 25.0 %. Zero switches it off.
- Hard CB Threshold, the same range, at 35.0 %. Zero switches it off.
- Soft CB Cooldown, 1 to 100 candles, at 3.
- Max Cartridge Size, 0.0 % to 200.0 %, at 10.0 %. The largest target
  delta, as a percentage of Target Balance, before the bot fires an aggressive
  rebalance.
- Smart Cartridge, one checkbox labelled Calibrate to BB range, off at the
  start.
- Smart Ceiling, 1.0 % to 100.0 %, at 30.0 %. It caps the cartridge threshold
  while Smart Cartridge is on.

The group title on screen carries an internal release identifier after the words
Circuit Breakers. A trip stops a trade at one gate on each side of the chain,
and [07-indicators.md](07-indicators.md) lists both chains in full.

`src/gui/bot_wizard.py` — `TradingParamsPage.get_config`, the settings this
group emits

```python
"circuit_breaker_soft_pct": self._cb_soft_pct.value(),
"circuit_breaker_hard_pct": self._cb_hard_pct.value(),
"circuit_breaker_cooldown_candles": self._cb_cooldown.value(),
"max_cartridge_size_pct": self._max_cartridge_pct.value(),
"max_cartridge_smart": self._cartridge_smart_chk.isChecked(),
"max_cartridge_smart_ceiling_pct": self._cartridge_smart_ceiling.value(),
```

**Design intention.** A pump and dump should stop the bot, not feed it. The
operator splits that aim in two below. A soft breaker clears itself after a
number of candles. A hard breaker holds until a person clears it by hand. Both
halves are built, and the gate on each side of the chain is where the stop
lands.

`src/trading/gate_chain.py` — the two breaker gates in the built chains

```python
CircuitBreakerGate(side="scrum"),
```

`src/trading/gate_chain.py` — and the fold chain

```python
CircuitBreakerGate(side="fold"),
```

Now we arrive at some safety controls. Circuit Breakers are designed to fully inhibit trade actions for a given period should an extreme volatility (pump and dump) event occur. Soft Circuit Breakers have a candle-count based timer whereas Hard Circuit Breakers require the user to clear the bot to continue trading.

Soft CB Threshold - The amount of instantaneous, single-candle price action required for the bot to pause trading for a number of candles denoted by Soft CB Cooldown.

Hard CB Threshold - The amount of instantaneous, single-candle price action required for the bot to be hard stopped at which point the user must re-authorize trading.

Soft CB Cooldown - This is the number of candles that must close before the Soft Circuit Breaker opens again.

Max Cartridge Size - This is the maximum amount of deviation allowed for the Target Delta. At this threshold the bot is actively and aggressively looking for a trade opportunity.

Smart Cartridge - This allows the Max Cartridge Size to organically resize in response to current price range as defined by the current-candle Bollinger Band reading.

Smart Ceiling - To be re-evaluated.

![The Risk Controls and Strategy Gate Flags groups.](p22-i0.png)

**Functional.** Five rows of risk control, then five gate checkboxes:

- Enable Position Ceiling, off at the start.
- Ceiling Multiple, 1.0 to 10.0, at 5.0x anchor. The anchor is the target
  balance the bot was created with.
- Enable Detonation (auto-harvest on bullish TF), off at the start.
- Detonation TF: 1d or 1w.
- Min Confidence, 0.50 to 1.00, at 0.75.
- SCRUM requires bullish TA, SCRUM holds in sustained uptrend, SCRUM defers to
  higher-TF bullish, FOLD requires bearish TA, and FOLD defers to higher-TF
  bearish. All five start checked.

Detonation does what its label says. It needs the box ticked, a position worth
more than its anchor, and a bullish reading at or above the confidence you set.
It also needs the reading to have just turned bullish. A tape that was already
bullish last time fires nothing, and a bearish tape fires nothing. The two
group titles on screen carry internal identifiers after their names.

`src/trading/scrumming_bot.py` — `ScrummingBot._check_detonation_trigger`

```python
conf_min = float(getattr(self.config, "detonation_confidence_min", 0.75))
is_bullish = (
    summary.consensus_direction == SignalDirection.BULLISH
    and summary.consensus_confidence >= conf_min
)

fired = is_bullish and not self._detonation_last_signal_bullish
```

`src/gui/bot_wizard.py` — `TradingParamsPage.get_config`, the settings these
two groups emit

```python
"position_ceiling_enabled": self._position_ceiling_enabled.isChecked(),
"position_ceiling_multiple": self._position_ceiling_multiple.value(),
"detonation_enabled": self._detonation_enabled.isChecked(),
"detonation_timeframe": self._detonation_timeframe.currentData(),
"detonation_confidence_min": self._detonation_confidence_min.value(),
"scrum_require_ta_bullish": self._gate_scrum_ta_chk.isChecked(),
"scrum_hold_in_uptrend": self._gate_scrum_uptrend_chk.isChecked(),
"scrum_defer_to_htf": self._gate_scrum_htf_chk.isChecked(),
"fold_require_ta_bearish": self._gate_fold_ta_chk.isChecked(),
"fold_hold_in_downtrend": True,  # reserved, no gate
"fold_defer_to_htf": self._gate_fold_htf_chk.isChecked(),
```

**Design intention.** Cap what one bot can grow to, then take the whole
position off the table once the cap is crossed. Both halves of that are built
and both run.

The gate flags are a different story. Six flags are declared, the box shows
five, and the missing one is the fold-side twin of a scrum gate that works. It
is written out as a hard True with the note "reserved, no gate" beside it, and
nothing in the engine ever reads it. Its scrum mirror holds a sell during a
sustained uptrend, and the fold twin would hold a buy during a sustained
downtrend.

*Proposed, not present, in `src/trading/gate_chain.py`:*

```python
class FoldTrendHoldGate(Gate):
    """FOLD-only: hold the buy while a sustained downtrend runs."""

    name = "trend_hold_fold"
    side = "fold"

    def evaluate(self, ctx: GateContext) -> GateResult:
        if not ctx.eff_trend_hold:
            return GateResult(passed=True)
        return GateResult(
            passed=False,
            blocker_message=f"trend_hold_fold({ctx.trend_strength:.0%})",
        )
```

The gate would join the fold chain beside its scrum twin, and
`fold_hold_in_downtrend` in `src/trading/container/config.py` would arm it. A
checkbox has to arrive with it, or the flag stays a hard True. Issue #419
carries this.

After Circuit Breakers, which help defend against extreme volatility, we come to Risk Controls. These are designed to cap the amount of profit or growth a given bot can earn before performing a full position exit.

Enable Position Ceiling - Enables a growth cap for a given position.

Ceiling Multiple - This setting caps the maximum amount of growth a position at a multiple of the Target Balance (anchor) and, once reached (and under higher timeframe bullish conditions with Detonation enabled) will allow the entire position to be sold and the corresponding bot will pause all further operations. Without Detonation enabled, this becomes a user notification.

Enable Detonation - Enables an entire remaining position to be sold after the Ceiling Multiple growth threshold is crossed.

Detonation TF - Selects the timeframe for the chart that is being evaluated for bullish conditions that will allow the detonation to occur.

Min Confidence - This is the minimum technical analysis confidence index (via the Indicator Voting Panel) that will allow the detonation to occur.

Next we use the Strategy Gate Flags which allows top-level trade restrictions to be enabled or disabled thus relaxing or restricting the conditions under which a trade action can occur. The settings, in this case, are self-descriptive.

![The Profit Routing group.](p22-i1.png)

**Functional.** Two rows:

- Route offers four destinations: fold back to target balance, send to
  spendable, split fold and spendable by percentage, and route to another bot.
- Target bot ID, a free-text field. The placeholder says to leave it blank
  unless you chose the cross-bot route.

The group title on screen carries an internal release identifier after the words
Profit Routing.

`src/gui/bot_wizard.py` — `TradingParamsPage.get_config`, the settings this
group emits

```python
"profit_route": self._profit_route.currentData(),
"profit_route_bot_id": self._profit_route_bot_id.text().strip(),
```

**Design intention.** The operator marks this group for re-evaluation and
possible removal below, and says the cross-bot route was meant to create a
Smart Wire under the Bot Swarm tab. Read the whole group as provisional. A
group that may be deleted gets no proposal.

In development.

Moving onto the final section, we have Profit Routing which was intended to allow profits to be routed differently during initial set-up. This will be re-evaluated and potentially removed.

Route - Destination for profits.

Target bot ID - Field for manually a bot ID which was intended to create a Smart Wire under the Bot Swarm tab.

![The Phantom Balance Bots page.](p23-i0.png)

**Functional.** This is the last page on the scrumming path:

- Enable Phantom Balance Bots, a checkbox, off at the start.
- Active Timeframes, eleven checkboxes: 1m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h,
  1d and 1w. All start clear. A timeframe the chosen venue does not carry is
  greyed out and cleared, with the reason written into its tooltip.
- Candles to lock, 1 to 10, at 2, inside the Higher-TF Lock Duration group.

The page hands on only the boxes that are both ticked and available. Before it
lets you leave, it asks the API load monitor whether that many phantoms would
breach the safety threshold for the venue, and offers you Back to adjust or
Continue anyway.

`src/gui/bot_wizard.py` — `PhantomConfigPage.get_config`

```python
def get_config(self):
    checked = [
        tf
        for tf, cb in self._tf_checks.items()
        if cb.isChecked() and cb.isEnabled()
    ]
    return {
        "enable_phantoms": self._enable.isChecked(),
        "phantom_timeframes": checked,
        "lock_candle_count": self._lock_candles.value(),
    }
```

**Design intention.** A higher timeframe should be able to override a trade the
primary timeframe wanted, either improving it or holding it back. That is the
aim below. The operator states the present position himself in the Indicator
Voting Panel section: "Phantom bots are still in active development so any
related features are not yet working." This page is the settings surface for an
engine he marks unfinished, so it gets no proposal here.

In development.

Lastly we have the selection for the Phantom (Balance) Bots. These are intended to provide trade action overrides from higher timeframe charts and indicator sets which, in turn, may result in an improved trade or prevent a premature one.

### Extractor Bot (Partially Built; Untested)

The second type of bot offered within Acervator is the Extractor. These operate quite differently from Scrumming Bots and actually operate as Siblings of them. In fact, an Extractor Bot cannot even be called unless a corresponding Base Currency Scrumming Bot (i.e. BTC:USD or ETH:USD) is already active. This is due to the core operating principle of the Extractor bot to acquire more of these base currencies by performing trades against available alternate currency pairings. It does this by using and blocking off a portion of the Parent’s position within an Extractor Tranche that represents an active position taken against one of the available alternate pairs. The Extractor Tranche remains open until its opposing accumulating (or Short Position if preferred by the user) or profit taking trade is filled. Extractor Tranches can be of any size but should generally be a relatively small fraction of the Parent’s total position which will allow the Extractor to take multiple positions if available and allowed by the specific user.

![The Trading Mode page with the Extractor selected.](p24-i0.png)

**Functional.** The same first page as before, with the other radio chosen.
From here the wizard goes to the Extractor Pool page instead of the asset page.
Phantom bots and profit folding are both switched off for this bot as it is
built, and an Extractor never sees the Phantom page at all.

`src/gui/bot_wizard.py` — `BotCreationWizard.get_bot_config`

```python
config.update(self._params_page.get_config())
if config["mode"] == "extractor":
    config["enable_phantoms"] = False
    config["profit_folding_active"] = False
else:
    config.update(self._phantom_page.get_config())
```

**Design intention.** The Extractor is a sibling, not a peer. It lives off a
base-currency Scrumming Bot and trades against alt pairs rather than holding
one target of its own. Phantom overrides and profit folding belong to the
parent, and the two hard False values above are that decision written down. The
mode is stamped onto the config at the very top of the same method, so nothing
downstream has to guess which kind of bot it received.

`src/gui/bot_wizard.py` — the mode stamp

```python
if self._mode_page.is_extractor():
    config["mode"] = "extractor"
    config.update(self._extractor_pool_page.get_config())
else:
    config["mode"] = "scrumming"
    config.update(self._asset_page.get_config())
```

![The Extractor Pool page.](p24-i1.png)

**Functional.** This page draws:

- Exchange, the connected venues. Changing it re-scans that venue.
- Pool Base Currency, a fixed list of five. It names the asset the pool
  accumulates.
- A line counting the pairs available against that base.
- Target alt pairs, a check list of every alt that trades against the base.
  Leave every box clear and the bot picks its own pairs by volume at run time.
- Select all and Clear act on the whole list.

The page hands on a single asterisk where a Scrumming Bot would hand on one
target asset. Its own docstring calls that the pool sigil. An Extractor holds a
pool of alts rather than one target, and the sigil keeps the field's shape for
the code downstream that builds a trading symbol.

`src/gui/bot_wizard.py` — `ExtractorPoolPage._POOL_BASES`

```python
_POOL_BASES = ["BTC", "ETH", "USDT", "USDC", "BNB"]
```

`src/gui/bot_wizard.py` — `ExtractorPoolPage.get_config`

```python
return {
    "exchange_id": self._exchange.currentData(),
    "base_currency": base,
    "target_asset": "*",  # pool sigil — multi-pair indicator
    "extractor_alt_targets": checked,
}
```

**Design intention.** Get more of a base currency by trading against alternate
pairs. That is the aim in the operator's paragraph above, and the five pool
bases are exactly the assets he names as base currencies. Leaving the list
empty hands the choice back to the bot, and only a box that is both ticked and
available reaches the config.

`src/gui/bot_wizard.py` — how a ticked alt is collected

```python
for i in range(self._alt_list.count()):
    item = self._alt_list.item(i)
    if item.checkState() == Qt.Checked:
        sym = item.data(Qt.UserRole)
        if sym:
            checked.append(sym)
```

![The Extractor group of the parameter page, first nine rows.](p25-i0.png)

**Functional.** Choosing the Extractor hides the eight scrumming groups and
shows this one. The two sides never appear together. Nine rows here and five
more in the figure below:

- Chunk size (USD), $10.00 to $10,000,000.00, at $100.00.
- Artillery size (USD), $0.50 to $100,000.00, at $5.00.
- Watch list top-N, 5 to 10, at 8.
- Watch list refresh, 10 to 240 candles, at 60.
- Pool reserve, 0.0 % to 90.0 %, at 50.0 %.
- Exit %, 10.0 % to 100.0 %, at 100.0 %.
- Max compounding tier, 1 to 10, at 3.
- Max cost-basis multiple, 1.0x to 10.0x, at 2.0x. Setting it to 1.0 stops
  averaging down.
- Direction: Normal (base to alt, buy first) or Inverted (standing alt to base,
  sell first).

The group title in the source reads Extractor, an em dash, Pool, an ampersand,
then Artillery. Qt reads that ampersand as a keyboard-mnemonic marker, so the
rendered title drops it and underlines the A of Artillery. The figure shows the
gap the dropped character leaves.

`src/gui/bot_wizard.py` — `TradingParamsPage.set_mode`, the group swap

```python
scrum_visible = not is_grid and not is_extractor
for g in (
    self._mode_group,
    self._scrum_group,
    self._adv_group,
    self._hedge_group,
    self._cb_group,
    self._risk_group,
    self._gates_group,
    self._routing_group,
):
    g.setVisible(scrum_visible)
self._extractor_group.setVisible(is_extractor)
```

`src/gui/bot_wizard.py` — `TradingParamsPage.get_config`, the settings this
group emits

```python
"extractor_chunk_size_usd": self._ext_chunk_size_usd.value(),
"extractor_artillery_size_usd": self._ext_artillery_size_usd.value(),
"extractor_scan_top_n": int(self._ext_scan_top_n.value()),
"extractor_scan_refresh_candles": int(
    self._ext_scan_refresh.value()
),
"extractor_pool_reserve_pct": self._ext_pool_reserve.value(),
"extractor_exit_pct": self._ext_exit_pct.value(),
```

**Design intention.** The operator marks the whole Extractor "Partially Built;
Untested" in this section's heading, and puts "To be re-evaluated" against four
of these nine rows: Pool Reserve, Exit %, Max cost-basis multiple and
Direction. This is a settings surface sitting ahead of a settled design, and
nothing about the four is decided.

In development.

Chunk size (USD) - This determines the maximum amount of the parent’s pool that the Extractor can use.

Artillery size (USD) - This determines the individual size of Extractor Tranches.

Watch list top-N - The determines the number of Alternate Currency pairs the bot will scan for potential extraction.

Watch list refresh - This determines the rate at which the Extractor will scan its watched markets. This is the equivalent of a Timeframe for the Extractor but covers multiple pairs.

Pool Reserve - To be re-evaluated.

Exit % - To be re-evaluated.

Max compounding tier - Allows the Extractor to attempt a number of compounding Swing Trades with a given Extractor Tranche with subsequent re-entries based upon the Parent Scrumming Bot’s Minimum Opposing Trade Distance + Trade Fee + Bollinger Band extension settings.

Max cost-basis multiple - To be re-evaluated.

Direction - To be re-evaluated.

![The Extractor group, remaining five rows.](p26-i0.png)

**Functional.**

- Standing alt units (Inverted), eight decimal places, at 0. The Inverted
  direction reads it; the Normal direction ignores it.
- Correction skip candles, 0 to 100, at 4.
- Drawdown threshold, 0.00 % to 50.00 %, at 3.00 %.
- Hedge budget (USD), at $0.00, which switches it off. Neither of the manual's
  own lists names this control.
- Trend strength threshold, 0.000 to 1.000, at 0.650.

`src/gui/bot_wizard.py` — `TradingParamsPage.get_config`, the remaining
Extractor settings

```python
"inverted_extractor_standing_alt_units": self._ext_standing_alt_units.value(),
"extractor_correction_skip_candles": int(
    self._ext_correction_skip.value()
),
"extractor_drawdown_threshold_pct": self._ext_drawdown_threshold.value(),
"extractor_hedge_budget_usd": self._ext_hedge_budget.value(),
"extractor_trend_strength_threshold": self._ext_trend_strength.value(),
```

**Design intention.** All four rows the operator names below carry his "To be
re-evaluated". The fifth control, Hedge budget, he does not name at all. It
sits on the page and no text of his describes it, so this manual states the
control exists and claims nothing about what it is for.

In development.

Standing alt units (inverted) - To be re-evaluated.

Correction skip candles - To be re-evaluated.

Drawdown threshold - To be re-evaluated.

Trend Strength Threshold - To be re-evaluated.

### Additional Main Window > Trading Tab Features

#### Trade Logic and Gate Activity

This spool displays the trading logic and gate activity.

![The Activity Log pane.](p26-i1.png)

**Functional.** The pane is read-only. Every line opens with a timestamp in a
muted colour, and the message takes its colour from its level: one colour for
info, one for success, one for warning, one for error. Three kinds of message
get a shape of their own. A trade notification draws larger and bold and takes
its colour from the stage of the trade. A wire flow or wire income line draws
in magenta behind a bolt character. A wire stack line draws in the pending
colour behind the same character. The pane holds 5,000 lines and drops the
oldest past that.

Pause Console is a toggle. While it is down, each new line goes into a buffer
of 2,000 instead of the screen, and a full buffer drops the newest rather than
the oldest. Resume replays the buffer with the original timestamps and adds a
line counting what it replayed. One writer goes through the pause regardless,
for a message you must not miss. A timer checks the pane's health every sixty
seconds and writes a warning into the pane itself when the render-error count
rises, or when nothing has rendered for ten minutes while bots are running.

`src/gui/widgets/status_log.py` — `StatusLog.log`

```python
def log(self, message: str, level: str = "info") -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    if self._paused:
        # A full ``_pause_buffer`` drops the newest entry, not the oldest.
        if len(self._pause_buffer) < self._pause_buffer_cap:
            self._pause_buffer.append((ts, message, level))
        return
    self._render(ts, message, level)
```

**Design intention.** This pane is the spool for trading logic and gate
activity, in the operator's words above. Two decisions follow from that. The
buffer drops the newest line rather than the oldest, so the lines around the
moment you hit pause are the ones that survive. And a pane that has gone quiet
says so in the pane, because silence otherwise reads as calm.

`src/gui/main_tabs/trading_tab.py` — the silence check

```python
if bots_active and age > 600:
    # Throttle: re-alert every 10 min while silent
```

#### API Interaction Log

This spool displays API handshake information and data transfer speeds for these messages.

![The API Interaction Log pane.](p26-i2.png)

**Functional.** The pane is read-only, holds 2,000 lines, and never wraps. One
entry is written per API call. A call that arrives on any thread but the GUI
thread is refused outright and written to a thread-violation file under the
runtime log directory instead, because touching a widget from a background
thread ends the process. An entry carries a timestamp, the exchange name, the
action and a Reason line, then Endpoint, Result, Response time and Data usage
wherever the record holds them. Pause API Log buffers up to 2,000 lines and
flushes them on resume with a count.

`src/gui/main_window.py` — `_on_api_event`

```python
def _on_api_event(self, entry: dict) -> None:
    """Append one API entry to `_api_log_view`, refusing off-thread calls."""
    # Touching a widget off the GUI thread ends the process through Qt.
    import threading as _threading

    current = _threading.current_thread().name
    origin = entry.get("_thread_name", "unknown")
    if current != "MainThread":
```

**Design intention.** The pane should tell you what the platform did with the
bytes it just paid for. One line does the opposite. The candle fetch writes a
Data usage note naming a seven-indicator engine and lists seven names. The
engine builds twelve and the Voting Panel shows all twelve, so the log tells
you something the screen next to it contradicts.

`src/exchange/ccxt_connector.py` — `get_ohlcv`, what it writes today

```python
data_usage="Fed into 7-indicator TA engine (BB, Vortex, MACD, StochRSI, Ichimoku, Volume, Slingshot) for voting",
```

*Proposed, not present:*

```python
data_usage=(
    "Fed into the "
    f"{len(DEFAULT_WEIGHTS)}-indicator TA engine for voting"
),
```

`DEFAULT_WEIGHTS` in `src/trading/ta_engine.py` is the one declaration of the
voter set, so a count taken from it cannot drift again. Issue #417 carries
this.

### Add Crypto Exchange Button (to be changed - Add Exchange)

While the initial set up of Acervator requires at least one valid exchange API, additional exchanges can be added and have their own bot swarms. The current upper operational limit of Acervator is unknown. Multi-exchange testing has yet to be attempted as of 8/25/26 with API compatibility work pending. This button also currently opens the Settings Panel but on the incorrect ‘User’ Tab when it should be ‘Exchanges’.

![The Add Crypto Exchange button.](p27-i0.png)

**Functional.** The button sits at the right of the exchange sub-tab row, as
the corner widget of that row. Each layer builds its own and labels it for that
layer: Add Crypto Exchange on the crypto page, Add Stock Exchange on the stock
page. Both run the same handler as the button on the empty card a layer shows
while it holds no exchange at all.

`src/gui/main_tabs/trading_tab.py` — `_make_layer`

```python
tab_w = QTabWidget()
add_btn = QPushButton(f"＋ Add {label_text} Exchange")
add_btn.setMinimumWidth(140)
add_btn.setToolTip(f"Add a {label_text} exchange connection")
add_btn.clicked.connect(self._add_exchange)
tab_w.setCornerWidget(add_btn)
```

**Design intention.** More than one exchange, each with its own bot swarm. The
operator names the defect himself above: the button opens the Settings Panel on
the User tab when it should open Exchanges. The handler already knows which
wing you are in and passes that to the dialog, so it has somewhere to say which
tab to open.

`src/gui/main_window.py` — `_add_exchange` today

```python
dlg = SettingsDialog(self._settings, self._status_log, self, wing=_wing)
dlg.exec()
```

*Proposed, not present:*

```python
dlg = SettingsDialog(self._settings, self._status_log, self, wing=_wing)
dlg.show_exchanges_tab()
dlg.exec()
```

The dialog in `src/gui/settings_dialog.py` has no such method yet. The proposal
adds one rather than changing the call shape, so the wing argument already
passed here keeps working exactly as it does.

### Indicator Voting Panel

![The Indicator Voting Panel, at the right of the Trading tab.](p27-i1.png)

**Functional.** The panel fills the right half of the Trading tab.

- The Bot selector at the top names the bot whose votes the panel draws. The
  list refills every tick. The badge beside it counts the bullish, bearish and
  neutral voters.
- TF Lock chooses a timeframe below which an opposing trade is refused. The
  list opens on "None (no lock)".
- The rate line under it shows the BTC and ETH prices with their satoshi and
  gwei equivalents, and the venue name at the end.
- Two tables of six voters each. A green up triangle is a bullish vote, a red
  down triangle a bearish one, an em dash a neutral one. ADX, ZSc and KER print
  a raw value; the other nine print a percentage.
- Each voter belongs to one of three groups, trend, momentum or structure, and
  the group decides its header colour.
- Net, Comp and Conf close the first table. Conf draws as a small filled bar
  with its percentage beside it.
- A bar chart under each table draws that table's six confidences at the width
  of the column above.
- The line at the foot names any timeframe lock that is active.

`src/gui/indicator_panel.py` — `IndicatorVotingPanel.INDICATOR_COLS`

```python
INDICATOR_COLS = [
    ("bollinger_bands", "BB", "S"),
    ("vortex", "VTX", "T"),
    ("macd", "MACD", "M"),
    ("stochastic_rsi", "SRsi", "M"),
    ("ichimoku", "Ichi", "T"),
    ("volume", "Vol", "S"),
    ("slingshot", "Sling", "S"),
    ("adx", "ADX", "T"),
    ("supertrend", "STrd", "T"),
    ("zscore", "ZSc", "M"),
    ("kaufman_er", "KER", "M"),
    ("rsi", "RSI", "M"),
]
```

**Design intention.** One place that shows what every voter thinks and how far
they agree. The names, the split into two rows and the three colour groups all
come out of the one list above, so the panel cannot fall out of step with
itself as voters are added or reordered.

`src/gui/indicator_panel.py` — the two rows, both cut from that list

```python
_ROW_A_INDICATOR_COLS = INDICATOR_COLS[:6]  # BB VTX MACD SRsi Ichi Vol
_ROW_B_INDICATOR_COLS = INDICATOR_COLS[6:]  # Sling ADX STrd ZSc KER RSI
```

The operator's own reading of each column follows in the next section.

[07-indicators.md](07-indicators.md) carries the published formula for each of
the twelve and the gate logic chain behind them.
