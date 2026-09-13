# System Architecture and Features Catalogue

Acervator features a semi-modular / layered design that nests a hyper-vigilant trading engine capable of operating in multiple investment domains simultaneously and all from one terminal. The Main Window contains all of the various subsections found in each subsystem tab. As it stands the existing and planned subsystem tabs are: Simulator, Paper Trading, Trading (Live), Market Inspector, Bot Swarm, Asset Charts, History, Console, Proof of Accumulation (PoA), and System Status. Most of these subsystems interact with each other to some degree with key isolations existing between the three trading tabs and their wiring to Market Inspector, Bot Swarm, and History.

## Trading Tab

Here you see the first subsystem we are going to cover and this will primarily be due to familiarizing the prospective investor or user with the core trading philosophy and strategies that drive Acervator. To begin, the platform runs locally on whichever hardware is selected. A single authorization phase requiring a purchased license key will be the only non-exchange communication the application will ever need. The user’s keys and secrets are stored locally and encrypted after API handshake verification passes which allows the chosen exchange to be initialized. At a later development stage, I have plans for dedicated hardware that uses a hardware key for quick boot into a given user’s account and also allows the platform to run in isolation under Linux.

![The Trading tab, with Privacy Mode on.](p15-i0.png)

This is the whole tab in one capture. The title bar and the menu row open it.
The header strip and the tab row run under them. Below those the exchange
sub-tab fills the left with the Scrumming Bots table and the command bar, the
Indicator Voting Panel fills the right, and the Activity Log and the API
Interaction Log close the foot. The status bar carries the API load pill and
the AI state label. The parts below take that screen in that order.

Privacy Mode is on, so every masked field draws four asterisks and the bot
table reads as ten columns of them. The title bar is the one reading no part
below names. It carries the version the tree answered with on the day of the
capture, v0.1.0. Nothing types that string out. Git answers for a source
checkout and the baked file answers for a frozen bundle, so the title cannot
name a release the build is not.

`src/gui/main_window.py` — the window title

```python
self.setWindowTitle("Acervator v" + __version__ + "")
```

Press the mode button once and the title is rewritten to name the wing. The
version leaves the title for the rest of the session, and only a restart brings
it back. Issue #426 carries that handler.

`src/gui/main_window.py` — `_toggle_trading_mode`, the title after a swap

```python
self.setWindowTitle("Acervator — CRYPTO WING")
```

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

**Design intention.** The two-layer stack is the part of the multi-domain aim
you can use today. Pressing the mode button swaps the whole wing, tables and
Paper Trader together.

`src/gui/main_window.py` — `_toggle_trading_mode`

```python
self._trading_mode = "stock"
self._mode_btn.setText("Stock Mode")
self._mode_btn.setChecked(True)
self._trading_stack.setCurrentIndex(1)
```

The Modulus Bot and the Paper Trading layer this section names have no module
behind them. This manual marks them unbuilt where it reaches them.

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
Scrummed card. Mature has no source yet and stays an em dash. Issue #418
carries this.

[08-tabs/portfolio-panels.md](08-tabs/portfolio-panels.md) covers the strip in
full.

**Both columns are now fed, and both are fed from the exchange.** The window no
longer writes the payload itself. It calls the same builder the React strip
calls, so one function decides what the five columns hold and neither host can
drift from the other.

`src/gui/main_window.py` — `_refresh_dashboard`

```python
self._spendable_widget.update_profits(
    header_strip_surface.profits_payload(agg, exchanges)
)
```

Realised profit is the exchange's own figure, matched buy against sell. Mature
profit is the profit on positions that have grown past two hundred per cent over
what they cost. Neither is computed from the platform's internal running totals,
because the venue is the authority on money.

`src/gui/main_tabs/header_strip_surface.py` — `profits_payload`

```python
"total_realised": exchange_amount(data, "total_realized_exchange"),
"mature": exchange_amount(data, "total_mature_exchange"),
```

Where the exchange has answered for no bot, both columns stay empty and say so.
The aggregate counts the bots the venue has answered for, and at zero the two
columns are handed nothing rather than a computed zero, so an empty column is
never a figure the platform made up.

`src/gui/main_tabs/header_strip_surface.py` — `exchange_amount`

```python
answered = int(data.get(EXCHANGE_FRESHNESS_KEY, 0) or 0)
if answered <= 0:
    return None
```

An empty column stays empty under Privacy Mode. The mask replaces a number with
four asterisks and leaves the empty marker alone, so the operator can always
tell a hidden figure from a missing one.

`src/core/privacy_mask_registry.py` — `mask_or`

```python
text = str(value)
if field_id not in ALL_FIELD_IDS or text == ABSENT_TEXT:
    return text
```

#### The tab row

**Functional.** The row of main tabs takes its order from one list. Each label
in the list is moved to its own index at build time. Any tab the list does not
name keeps the position it was added at.

`src/gui/main_tabs/main_window_surface.py` — the order, declared once

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

Each of those ten names is a constant holding the label the tab bar shows,
and the main window applies the order once, after the last builder has run.

`src/gui/main_window.py` — where the order is applied

```python
self._reorder_main_tabs(list(CANONICAL_TAB_ORDER))
```

**Design intention.** The order should read as the promotion order. Practise
first, then paper, then real money, then the screens that inspect the trade. One
list decides it, so the order cannot drift as tabs are added.

`src/gui/main_window.py` — the move loop

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

#### The news line

**Functional.** The headline between Privacy Mode and + New Bot is one item
from the crypto news ticker. The counter in front of it gives that item's place
in the batch the ticker holds, so a reading of 23 of 42 marks the twenty-third
headline of forty-two. The item itself carries the feed name, a middle dot,
then the story title. A timer steps to the next item and wraps at the end of
the batch.

`src/gui/crypto_news_ticker.py` — the line the strip draws

```python
_prefix = f"[{self._index + 1}/{len(self._headlines)}] "
self._label.setText(_prefix + h.display_text())
```

**Design intention.** The counter tells you the batch is whole. A feed that
came back short shows a smaller second number rather than a strip that looks
the same and carries less. With nothing reachable the strip says so in words
instead of going blank.

`src/gui/crypto_news_ticker.py` — the empty state

```python
self._label.setText("(no crypto news feeds reachable)")
```

**Functional.** In the React build the strip is drawn by
`crypto_news_ticker.js` into the header space the exchange screen keeps between
the Privacy Mode button and + New Bot. The exchange screen names that space
only when the strip is there; where the strip would not build, the header takes
plain space instead and the two buttons keep their positions.

`src/gui/main_tabs/exchange_tab_surface.py` — `react_news_ticker`

```python
def react_news_ticker() -> str:
    """The module that draws the news strip, as ``build_news_ticker`` reads it.

    ``ExchangeTabModel`` calls this as its ``news_ticker_factory``, so
    ``news_ticker`` is set and the header keeps the strip's space.
    """
    return NEWS_TICKER_MODULE
```

**Functional.** Hovering the headline pauses the step timer and moving away
starts it again. Clicking the headline opens that story. Each of the three
sends one request and redraws the strip from the answer, so the strip on screen
matches what the backend holds.

`src/gui/main_tabs/crypto_news_ticker_surface.py` —
`CryptoNewsTickerModel.handle_event`

```python
if event_type == EVENT_ENTER:
    self.paused = True
    self.calls.append([HOVER_PAUSED])
    return False
if event_type == EVENT_LEAVE:
    self.paused = False
    self.calls.append([HOVER_RELEASED])
    return False
```

#### The bot tables

**Functional.** The Scrumming Bots table carries ten columns. Nine are named
and the tenth is blank, because that one holds the Detail button. Mode is the
coloured cell: green while running, amber while paused, grey while idle or
stopped, red on error, orange in cooldown, cyan while starting. The Ammo cell
draws green above the target, red below it, and neutral grey inside the dust
band. Target BTC and Target ETH restate the Target in those two assets, and go
blank when the pair is unlisted or when the target already is that asset. The
Extractor table sits underneath. Both tables start hidden and appear when their
own list gains a row.

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

**Functional.** Column 2 is Current Position Value. It shows what the bot's
holdings are worth at the exchange's own price. It is blank whenever no fresh
exchange price exists, and a blank cell names the missing thing in its tooltip:
no position held, no exchange price for the pair yet, no exchange price this
tick, or a price older than twenty seconds. The cell never falls back to a
last-known figure, to a stand-in, or to a value read out of the bot's own
ledger. The state colour now sits on the Bot ID cell, which is green while
running, amber while paused, grey while idle or stopped, red on error, orange
in cooldown and cyan while starting. That cell's tooltip names the mode and the
state.

`src/gui/main_tabs/table_cells_surface.py` — the one multiplication both priced
cells read, so the Position Value cell and the Ammo cell can never disagree

```python
def priced_position(holdings: float, price: float, quote_rate: float) -> float:
    """The position value at one price: ``holdings`` times ``price`` times
    ``quote_rate``."""
    return holdings * price * quote_rate
```

**Functional.** The price both cells read comes from the shared exchange price
cache, and it carries its own age. An age of None means the cache held nothing
and the bot's own last reading was used instead, which is why the Position
Value cell goes blank on that path.

`src/gui/main_tabs/table_cells_surface.py` — the four blank paths and the one
priced path

```python
POSITION_PATH_PRICED = "priced"
POSITION_PATH_NO_HOLDINGS = "no_holdings"
POSITION_PATH_NO_PRICE = "no_price"
POSITION_PATH_OFF_EXCHANGE = "off_exchange"
POSITION_PATH_AGED = "aged"
```

**Design intention.** The Ammo cell measures against the live target, not the
frozen number typed into the wizard, so the reading follows the grown balance
the engine re-zeroes to.

`src/gui/widgets/bot_status_table.py` — the target the Ammo cell measures
against

```python
target_val = float(
    status.get("live_target_balance", status.get("target_balance", 0.0))
    or status.get("target_balance", 0.0)
    or 0.0
)
```

**Functional.** In the React build the Scrumming Bots table is drawn by
`bot_status_table.js`. The exchange screen keeps a named empty space for it and
fills that space when it draws itself. The rows come from the backend, not from
the exchange screen: the renderer asks the bridge for the table's own state and
names the exchange it wants rows for. Each exchange gets its own table state, so
two exchange screens on one page never share rows or a highlight.

`src/gui/web/exchange_tab.js` — `mountScrumTable`

```javascript
function mountScrumTable(target, model) {
  var loader = global[LOAD_BOT_TABLE];
  var wait =
    typeof loader === "function" ? loader(askFor(model)) : Promise.resolve(null);
  return Promise.resolve(wait).then(function () {
    return renderScrumTable(target, exchangeOf(model)) === null
      ? null
      : BOT_TABLE_MODULE;
  });
}
```

**Functional.** The four things the operator can press on the table each send
one request and redraw from the answer. A column header toggles that column's
privacy mask, a Symbol cell opens the chart address, Fire hands the bot to
Manual Fire, and Detail selects the row and opens the bot. `on_detail` is the
handler behind the Detail button.

`src/gui/main_tabs/bot_status_table_surface.py` — `BotStatusTableModel.on_detail`

```python
def on_detail(self, bot_id: str) -> None:
    """Select the row, then hand the bot to whatever opens the detail."""
    self.select_row_for_bot(bot_id)
    self.detail_clicks.append(bot_id)
    self.calls.append([DETAIL_CLICKED, bot_id])
    if self.on_bot_clicked:
        self.on_bot_clicked(bot_id)
```

**Design intention.** The exchange screen redraws itself once a second to keep
the data-pool line fresh. Each redraw re-fills the table space, so the table is
drawn from the state the renderer holds for that exchange rather than from the
answer captured at first paint. A row the operator selected therefore survives
the next redraw.

`src/gui/web/bot_status_table.js` — `modelFor`

```javascript
function modelFor(exchangeId) {
  return owns(models, String(exchangeId)) ? models[String(exchangeId)] : null;
}
```

**Functional.** The Extractor table underneath is drawn the same way, by
`extractor_bot_table.js` into the second named space the exchange screen keeps.
Its rows come from the same fleet list, kept to the records whose mode is
extractor. The Detail button is the one control the Extractor table offers;
Fire stays disabled on this screen, because Manual Fire is per position and
lives in the Positions Held tab of the bot's own window.

`src/gui/main_tabs/extractor_bot_table_surface.py` — `extractor_statuses`

```python
def extractor_statuses(statuses: Any) -> list:
    """The records of ``statuses`` whose mode is ``MODE_TEXT``.

    ``update_bots`` builds a row for every record it is handed, so only the
    Extractor bots reach the Extractor table.
    """
    return [
        found
        for found in statuses or []
        if isinstance(found, dict) and found.get("mode") == MODE_TEXT
    ]
```

**Functional.** The exchange screen mounts its three children in one step, each
into its own space and each asked for its own view model.

`src/gui/web/exchange_tab.js` — `mountChildren`

```javascript
function mountChildren(target, model) {
  return Promise.all([
    mountScrumTable(target, model),
    mountExtractorTable(target, model),
    mountNewsTicker(target, model)
  ]).then(function (drawn) {
    return drawn.filter(function (name) {
      return name !== null;
    });
  });
}
```

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

The pill names the venue, the calls that venue took in the last minute, the
ceiling for it and the two as a percentage. It reads the worst-loaded connected
venue, so one busy exchange cannot hide behind a quiet one.

`src/gui/main_window.py` — the pill text

```python
text = (
    f"API {worst.exchange}: "
    f"{worst.calls_per_minute:.0f}/"
    f"{worst.ceiling_cpm:.0f} CPM ({pct} %)"
)
```

Its colour is the warning. Green under half load, amber above that, red past
the venue's safety percentage. With no venue connected the pill draws an em
dash and no number.

`src/gui/main_window.py` — the three colours

```python
if worst.load_score > mon.safety_pct:
    colour = ds.ERROR
elif worst.load_score > 0.5:
    colour = ds.FOLD_RATIO_AMBER
else:
    colour = ds.SUCCESS
```

1 - Add Exchange - User provides valid API key and secret for target exchange - Platforms validates with an API handshake - Exchange Initializes

After an exchange is connected to the platform, bots can be added to target entire or portions of existing positions as well as using standing liquidity to enter positions for the first time. The two primary bots used by Acervator are known as Scrumming and Extractor with the conceptual Modulus Bot to be added later. The first two are the active traders that continuously interact with the market whereas the Modulus Bot will be a macro-strategic interface designed to trigger portfolio-scale shifts in response to custom market signals and it can best be visualized as a modular synthesizer with investment and market-specific functions.

### Scrumming Bot

If Acervator has a crown jewel, this is it. The scrumming bot is what houses and executes the harvest-fold method and the harvest-fold method is what leads to the creation of the platform itself. All else stems from this origin point and the simple revelation that allowed the method to be discovered (or probably rediscovered) by nonmathematical eyes. Instead of paying attention to what my entire portfolio was doing, I opted to start focusing on a single position until I had found a strategy that was more reliable than Grid Bots or standard speculation. I was convinced such a method existed and thought it absurd that price charts could not be played better when there was obviously so much room for improvement. You do not have to predict the market. You flow and mold your portfolio to it as time goes. Scrumming allows profits to be shaved off, held and re-investment in a cyclical, reliable manner that sizes its trades in direct proportion to actual market movement as it relates to position value drift. Trading in this manner allows a fixed balance for a position to be maintained and asserts the truth that “Position X is Y value. Any deviation from Y is a Target Delta and is subject to a Scrum (Sell) or Fold (Buy).” The primary weaknesses to this strategy are not have an equal amount of liquidity to the position value (a $500 Scrumming Bot should be supported by $500 of liquidity when initialized) and severe market downturns will little or no short term upside which can lock most liquidity for the position into the Target Asset. Scrumming is a survival strategy and is directionally agnostic but also depends on the market to cycle. I also refer to this simply as Accumulation Trading.

### Scrumming Bot Terms

Target Balance - The initial value of the position to be taken or controlled by the Scrumming Bot. The bot will monitor the market for bullish or bearish conditions, check for Target Balance deviations (Target Delta), and re-zero back to the set point. It will repeat this until stopped by the user or some other market condition.

The figure is one field on the bot's own configuration. It is carried in from
the wizard and held for the life of the bot, and every other term on this page
is measured against it.

`src/trading/container/config.py` — `BotConfig.target_balance`

```python
target_balance: float = 200.0  # Balance the bot trades relative to
```

Target Delta - The amount by which a position value has drifted from the Target Balance. The Target Delta is denoted by the Ammo column under the Scrumming Bot list of the Trading Tab. This is the amount of value that will be fired during the appropriate market conditions.

One subtraction, and the platform does it in two places with opposite signs.
The Ammo cell takes the position value less the target, so a surplus reads
positive. The fold path takes the target less the position, so a deficit reads
positive. Both measure the same drift.

`src/gui/table_cells.py` — `ammo_cell`, the figure the Ammo column shows

```python
delta = position_val - target_val
territory = target_territory(position_val, target_val)
```

Scrum - To sell an amount from an investment position that allows it to return to its initial price level. This never closes the position. This is the first half of the infinitely divisible circle that can persist for such positions in a healthy market.

One shared helper decides which half of the cycle a position sits in. It
answers scrum above the target and fold below it, and it answers at target
inside a dust band, so a position that has barely moved is left alone.

`src/trading/target_bands.py` — `target_territory`

```python
delta = float(position_value) - float(target_balance)
band = at_target_dust_band(target_balance)
if delta > band:
    return "scrum"
if delta < -band:
    return "fold"
return "at_target"
```

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

**Functional.** In the React build the wizard is drawn by `bot_wizard.js` into
a space the exchange screen keeps for it. The screen keeps that space only
after + New Bot is pressed. The press asks the surface, and the surface answers
with the name of the module that draws the wizard.

`src/gui/main_tabs/exchange_tab_surface.py` — `react_bot_wizard`

```python
def react_bot_wizard(exchange_id: str) -> str:
    """The module that draws the Create Auto Trader wizard for ``exchange_id``.

    ``ExchangeTabModel`` calls this as its ``on_new_bot``, so
    ``on_new_bot_clicked`` puts the module name in ``bot_wizard``.
    """
    return BOT_WIZARD_MODULE
```

**Functional.** Cancel closes the wizard. Finish closes it from the last page
and refuses from any other. Either close drops the module the screen holds, so
the space goes with the wizard and the exchange screen underneath it is whole
again.

`src/gui/main_tabs/exchange_tab_surface.py` — `ExchangeTabModel.close_bot_wizard`

```python
def close_bot_wizard(self) -> None:
    """Drop the wizard, so the screen keeps no space for it."""
    if self.bot_wizard is None:
        return
    self.bot_wizard = None
    self.calls.append([BOT_WIZARD_CLOSED, self.exchange_id])
```

**Functional.** Every control on the page sends the steps taken so far, not the
one just pressed. The surface lays out fresh pages on each call and keeps
nothing between them, so the page holds the walk and sends the whole of it. The
answer replaces the payload the page holds and the wizard draws again.

`src/gui/web/bot_wizard.js` — `press`

```javascript
function press(name, step) {
  lastPress = { name: name, step: step };
  dispatched.push(lastPress);
  remember(step);
  lastAnswer = hasBridge()
    ? global.acervator.call(METHOD, copyOf(heldSteps)).then(take)
    : Promise.resolve(null);
  return lastPress;
}
```

![The wizard's asset page: exchange, base currency and target asset.](p17-i0.png)

After Scrumming / Accumulation is selected, next we are presented with Exchange, Base Currency, and Target Asset options.

Exchange - A privately and federally licensed financial platform that allows API interfacing for remote or automated trade execution.

The row lists the venues already connected. Picking one re-scans that venue and
keeps only the spot markets the venue itself marks active.

`src/gui/bot_wizard.py` — the market filter inside `_fetch_markets`

```python
for sym, info in exch.markets.items():
    if (
        not info.get("active", True)
        or info.get("type", "spot") != "spot"
    ):
        continue
```

Base Currency - This will be a National Currency, Stable Coin, or High Volume Crypto (BTC, ETH, BNB) for which multiple trading pairs are available on the selected exchange.

The page offers a fixed list of seven, and it holds exactly the national
currencies, stable coins and high-volume crypto named above.

`src/gui/bot_wizard.py` — `AssetSelectionPage`, the base list

```python
self._base.addItems(["USDT", "USDC", "BTC", "ETH", "BNB", "EUR", "USD"])
```

Target Asset - This is the asset in which the scrumming bot bases its position. If $50 and ZEC are selected, it will strive to maintain and compound against a balance of $50 in ZEC until it is shut down or some other adverse market condition occurs.

The list holds every asset trading against the base you chose, each with a
cached coin icon and, where the venue reported one, a 24-hour volume figure.
The round information button opens a written description of the selected asset,
and the line under the rows counts the pairs found. Sorting by volume puts the
tradeable pairs at the top of a list that runs to several hundred entries on a
large venue, and the sort reads a cached figure rather than fetching one.

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

Order Visibility - Trades are listed on the order books or tracked internally to the platform.

Two entries, Order Book (Visible) and Internal (Invisible). `ScrummingBot`
reads the choice once at construction and holds it as its invisible flag. The
label a reader sees and the value the bot stores are two different strings on
the same row.

`src/gui/bot_wizard.py` — the Order Visibility row

```python
self._visibility = QComboBox()
self._visibility.addItem("Order Book (Visible)", "orderbook")
self._visibility.addItem("Internal (Invisible)", "internal")
self._visibility.setToolTip("How orders appear on the exchange.")
self._visibility.currentIndexChanged.connect(self._on_visibility_changed)
mf.addRow("Order Visibility:", self._visibility)
```

Driven on a bot rebuilt from a stored record, the two choices take different
branches on the same tick: Internal activated all three stored Stack tranches,
and Order Book activated none of them. The order type an engine trade carries is
chosen off the same flag, on the sell side and the buy side alike.

`src/trading/scrumming/execution.py` — the sell side's order type

```python
if self._invisible:
    ot = OrderType.MARKET
    exec_price = None
else:
    ot = OrderType.LIMIT
    exec_price = vh_fp
```

Aggressive Trading - Trades are priced so that they fill immediately. Trading like this is a bit like guerilla warfare. In and out before anyone notices.

A checkbox, off at the start. Every engine-initiated order then leaves as an
immediate-or-cancel limit priced through the spread, so it pays the taker fee
for an immediate fill. Manual Fire is unaffected.

`src/gui/bot_wizard.py` — the Aggressive Trading row

```python
self._aggressive = QCheckBox("Aggressive Trading (force IOC-limit takers)")
```

The box's value reaches the bot and reaches no order. One place in the trading
package builds an immediate-or-cancel order, inside the method that opens a Stack
from a SCRUM, and that method raises before it gets there. The two places that do
choose an order type read Order Visibility and never this flag.

`src/trading/scrumming_bot.py` — the only reader that would change an order

```python
_aggressive = bool(getattr(self, "_aggressive", False))
_order_type_for_visible = (
    OrderType.IOC_LIMIT if _aggressive else OrderType.LIMIT
)
```

Stack Mode - Stack Mode enables Stack Tranches which operate on the Sell or Scrum side. This forms the “upside” of the organic ladder structure whereas Fold Tranches form its “downside”.

The box takes its start state from the engine rather than from a second literal
typed onto the page.

`src/gui/bot_wizard.py` — `TradingParamsPage`, the Stack Mode default

```python
from ..trading.bot_container import STACK_MODE_DEFAULT

self._stack_mode = QCheckBox(
    "Stack Mode (split SCRUM across upward tranches)"
)
# One declaration, so the box and the config cannot disagree.
self._stack_mode.setChecked(STACK_MODE_DEFAULT)
```

The box's value arrives on the bot and gates four places: the branch that turns a
SCRUM into a Stack, and the three reconciliation stages. Driven, the guard
discriminates — on, all three stored tranches activated; off, none did. No tranche
can be created today, because the one method that appends one raises on an
attribute no object in the tree carries. That raise is the reason the four rows
below report a value that arrives and a behaviour that waits.

`src/trading/scrumming_bot.py` — the refusal, read from a restored bot

```
AttributeError: 'ScrummingBot' object has no attribute 'exchange_interface'
```

Split Distance - This setting determines the spacing between tranches if Tranche Spread (not available yet) is being used.

A percentage from 0.10 to 20.00, at 1.00 % to start. The bot hands it to the
stack maths as the gap between one tranche and the next, and the Spacing row
below decides how that gap grows across the ladder.

`src/gui/bot_wizard.py` — the Split Distance row

```python
self._split_distance = QDoubleSpinBox()
self._split_distance.setRange(0.1, 20.0)
self._split_distance.setDecimals(2)
self._split_distance.setSuffix(" %")
self._split_distance.setValue(1.0)
```

Driven at the maths the bot hands it to, 1.00 % priced three rungs a gap of
0.9901 and 0.9804 per cent apart, and 2.50 % priced the same three 2.439 and 2.381
per cent apart. The figure reaches that maths only through the method named under
Stack Mode above, so the value is correct and the ladder is not yet built.

`src/trading/scrumming_bot.py` — the hand-off

```python
split_dist = float(getattr(self.config, "split_distance", 1.0) or 1.0)
```

Tranche Spread - This allows a given Scrum or Fold to divide its result X# of times across multiple incremented (as dictated by Split Distance) positions.

The page carries no control of that name, and no setting named
`tranche_spread` reaches the engine.

The same sweep run for `split_distance` returns a declaration, a restore entry
and a reader, so the sweep itself finds a setting when one is there.

In development.

The sentence that opens this row is retired. Counted over the whole tracked tree,
the name appears once, and that once is this page describing its own absence.
Spacing is the control that exists and is read, and it names the four models the
engine carries. Tranche Count decides how many pieces a Scrum becomes, and Spacing
decides where each piece sits.

`src/trading/stack_math.py` — the models Spacing chooses from

```python
SPACING_MODES = ("quadratic", "fibonacci", "linear", "exponential")
```

Tranche Count - This can also be referred to as Spread Count. It determines how pieces a given Scrum or Fold is split into and distributed across incremented tranches as opposed to just one.

A whole number from 2 to 20, at 3 to start, written out as
`stack_tranche_count_target`. It is a target rather than a promise: the runtime
count drops when a tranche would fall under the venue minimum, or when two
computed prices land within a tenth of a percent of each other and merge.

`src/gui/bot_wizard.py` — the Tranche Count row

```python
self._stack_count = QSpinBox()
self._stack_count.setRange(2, 20)
self._stack_count.setValue(3)
```

Driven at the same maths, a target of 3 built three rungs and a target of 7 built
seven, each rung's size falling from 0.4 to 0.171429 units out of one 1.2-unit
Scrum. The count reaches that maths through the method named under Stack Mode, so
it too is a correct value waiting on a ladder.

`src/trading/scrumming_bot.py` — the hand-off

```python
n_target = int(getattr(self.config, "stack_tranche_count_target", 3) or 3)
```

Spacing - This adds a scaling factor Split Distance and works in conjunction with Tranche Spread and Tranche Count to induce curves and more aggressive growth within the ladder structure.

Three entries: Linear, Quadratic and Exponential. The sequence beside each name
is the cumulative distance from the anchor in units of Split Distance.

`src/gui/bot_wizard.py` — the Spacing row

```python
self._stack_spacing = QComboBox()
self._stack_spacing.addItem("Linear (1, 2, 3, 4…)", "linear")
self._stack_spacing.addItem("Quadratic (1, 2, 4, 7…)", "quadratic")
self._stack_spacing.addItem("Exponential (1, 2, 4, 8…)", "exponential")
```

The Quadratic entry read 1, 2, 4, 7 and the engine prices that model at n squared,
so the row named a ladder the engine has never built. Both the wizard row and the
live bot window now read 1, 4, 9, 16, which is what the engine publishes. The
engine also carries a fourth model, Fibonacci at 1, 2, 3, 5, that neither control
offers.

`src/trading/stack_math.py` — `level_multipliers`, driven for four levels

```
linear       [1.0, 2.0, 3.0, 4.0]
quadratic    [1.0, 4.0, 9.0, 16.0]
exponential  [1.0, 2.0, 4.0, 8.0]
fibonacci    [1.0, 2.0, 3.0, 5.0]
```

Personal Hold - Setting to be removed.

The control is still on the page. `TradingParamsPage.get_config` still emits
`personal_hold_qty`, and the capital reservation mixin still reads it, adding
it to the units the bot claims against its siblings. A removal has that reader
to retire with it.

`src/trading/scrumming/capital_reservation_mixin.py` —
`_compute_reservation_qty`

```python
_hold = float(getattr(self.config, "personal_hold_qty", 0.0) or 0.0)
```

`src/gui/bot_wizard.py` — `TradingParamsPage.get_config`, the settings this
group emits, in the order of the rows above

```python
"stack_mode": self._stack_mode.isChecked(),
"split_distance": self._split_distance.value(),
"stack_tranche_count_target": int(self._stack_count.value()),
"stack_spacing_mode": self._stack_spacing.currentData(),
"personal_hold_qty": float(self._personal_hold_qty.value()),
```

The same method writes `visibility` and `aggressive_trading` before it branches
on the kind of bot, so an Extractor carries those two as well.

Five sites read the number, not one. Two of them change what the engine decides.
The other three carry the value to those two, or draw the row the operator types
into.

```
src/trading/container/restore.py:254                    stored key into the kwarg
src/trading/scrumming/capital_reservation_mixin.py:67   the size of the claim
src/trading/scrumming/capital_reservation_mixin.py:134  the text of the claim
src/trading/scrumming/reconciliation.py:412             the adoption ceiling
src/gui/live_settings/settings_tab.py:304               seeds the live row
```

Both deciding readers are reached on every run. The claim is sized at the top of
every tick. The adoption ceiling is read once when a bot starts, and again every
reconcile interval after that.

```
src/trading/scrumming_bot.py:2571   the claim, once per tick
src/trading/bot_container.py:891    the ceiling, on bot start
src/trading/scrumming_bot.py:2643   the ceiling, every reconcile interval
```

The adoption ceiling is the reader that bears on a sale. A bot whose venue
balance stands above its own book adopts the difference as a lot, and the hold is
subtracted before that adoption, so the held units never enter the book the sell
pre-check is measured against.

```
src/trading/scrumming/execution.py:1408 — the sell pre-check reads the book
```

Driven on a restored record carrying a five-unit hold, with twenty units in the
book, thirty at the venue and a price of one hundred, against the same code with
all five readers taken out:

```
with the readers    claimable 25.0   adopted 5.0    book 25.0
readers removed     claimable 30.0   adopted 10.0   book 30.0
```

That bot may sell 25 units as the code stands and 30 with the readers gone. The
five it holds back are the hold itself. The claim a bot places against its
siblings moves the same way, 16.0 units down to 11.0, which raises a co-tenant
bot's own permitted sale from 14.0 units to 19.0.

```
src/trading/capital_reservation.py:443 — effective_available, the co-tenant's cap
```

The removal is not taken. Stored state does load without the value — three
records of three restored, 26 of 27 stored fields identical, none different, and
nothing raised — but a bot carrying a hold would be free to sell the units the
hold keeps back. The removal is safe only for a bot whose hold reads zero.

![The Scrumming Settings group.](p19-i0.png)

Scrolling down we next find the first block of Scrumming Settings. These are the core or basic metrics for a Scrumming Bot.

Opposing Trade Interval - Establishes the minimum travel distance required by price action from the point a given trade in order the next trade of the opposite type to occur.

A percentage from 0.10 to 20.00, at 1.00 % to start. The Trading Fee below is
added to it, so the real distance a reversal must travel is the two together.

`src/gui/bot_wizard.py` — the Opposing Trade Interval row

```python
self._scrumming_interval = QDoubleSpinBox()
self._scrumming_interval.setRange(0.1, 20.0)
self._scrumming_interval.setDecimals(2)
self._scrumming_interval.setSuffix(" %")
self._scrumming_interval.setValue(1.0)
```

Driven on a bot restored from a stored configuration, the percentage sets two
thresholds. One is the dollar drift the position must show before the tick looks
at anything else. The other is the price a reversal must reach after an opposite
trade, and the Trading Fee is inside both of them.

```
target $200.00
  interval 1.00 %   drift threshold $2.00    the tick reads the gates
  interval 5.00 %   drift threshold $10.00   the tick holds and says so

pivot $100.00000000, one tick later at $101.00000000
  interval 0.10 %   required $100.70000000   cleared, no hysteresis blocker
  interval 1.00 %   required $101.60000000   hysteresis blocker raised
  interval 5.00 %   required $105.60000000   hysteresis blocker raised
```

Asked for a figure under its floor the box answers the floor: asked for 0.00 it
answers 0.10.

BB Tolerance - Determines the minimum distance of the Bollinger Band extent price action must be in order for a trade action to occur.

A percentage from 0.25 to 5.00, at 1.00 % to start. The band-proximity detector
takes it as its tolerance. This is the narrowest range on the page, and it
cannot be set to zero.

`src/gui/bot_wizard.py` — the BB Tolerance row

```python
self._bb_tolerance = QDoubleSpinBox()
self._bb_tolerance.setRange(0.25, 5.0)
self._bb_tolerance.setDecimals(2)
self._bb_tolerance.setSuffix(" %")
self._bb_tolerance.setValue(1.0)
```

Driven on one tape whose last close sat at band position 0.976123, the tolerance
decides whether that close counts as sitting at the upper band, and the landing
strip follows that answer. Asked for 0.00 the box answers 0.25, so it cannot be
set to zero.

```
band position 0.976123, one tape, one tick
  tolerance 0.25 %   near upper False   landing strip False
  tolerance 5.00 %   near upper True    landing strip True, upper side
```

Landing Strip Candles - Determines the strictness of Landing Strip detection. Minimum is three candles. Longer Landing Strips are historically more likely to indicate an impending market reversal than shorter ones assuming the taper remains intact or grows tighter.

A whole number of candles from 2 to 10, at 3 to start. The widget accepts 2,
one below the minimum of three the description names, and the number reaches
only one of the two landing-strip detectors. Issue #432 carries this.

`src/gui/bot_wizard.py` — the Landing Strip Candles row

```python
self._ls_candles = QSpinBox()
self._ls_candles.setRange(2, 10)
self._ls_candles.setValue(3)
self._ls_candles.setSuffix(" candles")
```

Both halves of the correction above were re-measured, and both hold. The box does
accept 2: its declared floor is 2, asked for 0 or 1 it answers 2, and 2 is the
one figure under three it keeps. The number does reach one detector of the two
the tick runs over the same candles.

```
the tick runs two detectors, and they count different things
  band proximity   its minimum pattern candles = the stored figure
  tightening       its minimum consecutive run = a platform constant of 3

one tape, trailing tight bodies 2
  stored 2    landing strip True     confidence boost 0.1900
  stored 3    landing strip False    confidence boost 0.0000
  stored 2 and stored 12 both logged: TIGHTENING (upper BB): 3 candles
```

Raising the floor to three is not taken, and the reason is a measurement. A box
holding a stored 2 answers 3 the moment its range starts at three, and putting
the range back leaves the 3 behind, so the next Save would write three into a
bot whose record says two.

The tightening detector keeps its own run length, because a run of shrinking
bodies is not a count of tight bodies at a band. The four figures the tick hands
that detector are now the names the gate scan already declared for them, and the
values are unchanged.

```python
tightening = detect_landing_strip_v2(
    candles,
    min_consecutive=TIGHTENING_MIN_CONSECUTIVE,
    shrink_threshold=TIGHTENING_SHRINK_THRESHOLD,
    bb_tolerance_pct=TIGHTENING_TOLERANCE_PCT,
)
```

TA Timeframe - This is the timeframe at which the bot operates and denotes the price chart it will monitor for trade decisions.

Seven entries to start, with 1h chosen. Pick an exchange and the list is
rebuilt from the timeframes that venue carries, so a venue without 4h does not
offer it. The starting choice is an index into the list rather than a named
timeframe.

`src/gui/bot_wizard.py` — the TA Timeframe row

```python
self._ta_timeframe = QComboBox()
```

```python
self._ta_timeframe.setCurrentIndex(4)  # Default 1h
```

Driven on a bot restored from a stored configuration, the name decides which
chart the bot fetches, and every indicator vote is then computed on that chart.

```
one bot, one tick each, two stored names
  1h   chart asked for 1h   consensus BULLISH 0.0219   band position 0.500000
  1d   chart asked for 1d   consensus BEARISH 0.0863   band position 0.976123
```

Target Balance - This is the intended starting and locked value for the investment position that the Scrumming Bot is controlling.

From $1.00 to $1,000,000.00. Its start value is whatever default the wizard was
handed, which is the figure the Settings Trading page stores.

`src/gui/bot_wizard.py` — the Target Balance row

```python
self._target_balance = QDoubleSpinBox()
self._target_balance.setRange(1.0, 1000000.0)
self._target_balance.setDecimals(2)
self._target_balance.setPrefix("$ ")
self._target_balance.setValue(defaults.get("default_target_balance", 200.0))
```

Driven on one position worth $203.00, the figure is the line the excess is
measured from, and the Opposing Trade Interval above is a percentage of it. A
dollar and a half of target turns the same position from one the tick evaluates
into one it holds.

```
one position of $203.00, one tick each
  target $200.00   excess +$3.00   scrum side   interval $2.0000   gates read
  target $201.50   excess +$1.50   scrum side   interval $2.0150   tick holds
```

The start value does come from the figure the wizard is handed: handed 200.00 the
row opens at 200.00, and handed 777.50 it opens at 777.50. Asked for 0.00 the box
answers 1.00.

Max Entry Price - If the new bot does not detect the requisite amount (as dictated by Target Balance) of the Target Asset, this price threshold sets a limit at which it will attempt to perform the initiating Fold.

Eight decimal places, at $0.00000000, where zero means no ceiling. The buy path
is the only reader, and it refuses a buy above the ceiling. Manual Fire goes
around it.

`src/gui/bot_wizard.py` — the Max Entry Price row

```python
self._max_entry_px = QDoubleSpinBox()
self._max_entry_px.setRange(0.0, 10_000_000.0)
self._max_entry_px.setDecimals(8)
self._max_entry_px.setPrefix("$ ")
self._max_entry_px.setValue(0.0)
```

Min Entry (Should Be Exit) Price - If the new bot detects a requisite amount (as dictated by the Target Balance) of the Target Asset, this price threshold sets a limit at which it will attempt to perform the initiating Scrum.

The same shape, where zero means no floor. The buy path is the only reader here
too, so the number refuses a buy below the floor and never reaches a sell. The
row is labelled Min Entry Price on the page, without the parenthesis his line
carries.

`src/gui/bot_wizard.py` — the Min Entry Price row

```python
self._min_entry_px = QDoubleSpinBox()
self._min_entry_px.setRange(0.0, 10_000_000.0)
self._min_entry_px.setDecimals(8)
self._min_entry_px.setPrefix("$ ")
self._min_entry_px.setValue(0.0)
```

Trading Fee % - This allows the trading fee for the target exchange to be set. This is added to Minimum Opposing Trade Distance to further ensure buys / sells are properly distant and that a given bot is not losing an excessive amount to fee chop in volatile but overly tight market regimes.

A percentage from 0.00 to 5.00, at 0.60 % to start, which is the Coinbase
Advanced Trade maximum tier. It steps in twentieths of a percent, and it is a
per-side figure.

`src/gui/bot_wizard.py` — the Trading Fee row

```python
self._trading_fee = QDoubleSpinBox()
self._trading_fee.setRange(0.0, 5.0)
self._trading_fee.setSuffix(" %")
self._trading_fee.setDecimals(2)
self._trading_fee.setSingleStep(0.05)
self._trading_fee.setValue(0.6)
```

Max Target Growth % - This determines the maximum amount of growth the Target Balance can increase in a given Market Cycle with a cycle being a Fold / Scrum / Fold sequence. Essentially any Fold preceded by a Scrum will be allowed to Fold an amount of profit back in and, if Surplus remains after the Target Delta is re-zero’d, it can be used to increase Target Balance up to this hard limit for that cycle. This is the organic compounding mechanic.

A percentage from 0.00 to 100.00, at 1.00 % to start. Setting it to zero
freezes Target Balance. It steps a quarter of a percent at a time, and it is
the only mechanism allowed to raise the figure.

`src/gui/bot_wizard.py` — the Max Target Growth row

```python
self._max_target_growth_pct = QDoubleSpinBox()
self._max_target_growth_pct.setRange(0.0, 100.0)
self._max_target_growth_pct.setSuffix(" %")
self._max_target_growth_pct.setDecimals(2)
self._max_target_growth_pct.setSingleStep(0.25)
self._max_target_growth_pct.setValue(1.0)
```

Scrum Fold Ratio - This precedes Surplus calculation as described under Max Target Growth %. It determines how much of a given trade’s profits will be redistributed to directly contribute to its own organic compounding. Note that this does not interfere with normal Target Delta re-zeroing and is intended to only serve as a “cushion” to slow runaway compounding when Wire Credits are being received from multiple sources.

A whole percentage from 1 to 100, at 100 % to start.

`src/gui/bot_wizard.py` — `TradingParamsPage.get_config`, the settings this
group emits, in the order of the rows above

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

**Where the code departs.** Two of these rows read differently in the engine
than the entries above say.

Min Entry Price is the first. The entry above writes the correction into its
own heading, and the code follows the label on screen rather than that
correction. The buy
path is the only place either entry-price field is read; it refuses a buy above
the ceiling and refuses a buy below the floor. Neither number reaches the sell
path, so a bot that holds the asset and reaches that price sells nothing.
Manual Fire runs its own rebalance and reads neither.

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

The sell path already takes the price, so the floor check has somewhere to
attach.

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

Max Target Growth % is the second. The engine holds two answers for a bot whose
stored config lacks the key. Ten read sites take it with a fallback: seven fall
back to 1.0 and three fall back to 0.0. A bot compounds or freezes depending on
which site read it first. The declared default is 1.0, and the three outliers
should say the same.

*Proposed, not present, at each of the three sites:*

```python
_growth = float(getattr(self.config, "max_target_growth_pct", 1.0) or 0.0)
```

The three outliers are the manual rebalance, the compounding snapshot and the
SWOS inputs. Issue #409 carries this.

```
src/trading/scrumming/execution.py   _execute_manual_rebalance
src/trading/scrumming/snapshots.py   _compounding_snapshot
src/trading/scrumming_bot.py         get_swos_inputs
```

![The Advanced Scrumming and Hedge Rebalance groups.](p20-i0.png)

Next are the “advanced” Scrumming settings which primarily affect when the bot is allowed to fire a trade. These can be thought of as “calibrating the scope”.

Detect Threshold - Intended as the point at which the bot “takes the safety off” and starts looking for a shot. To be re-evaluated.

A whole percentage from 10 to 90, at 75 % to start. The engine reads 75 as a
lower mark of 0.125 and an upper mark of 0.875, measured across the band rather
than in dollars.

`src/trading/scrumming/circuit_breakers.py` — `_bb_detect_thresholds`

```python
detect_frac = max(0.0, min(1.0, detect_pct / 100.0))
half = detect_frac * 0.5
return (0.5 - half, 0.5 + half)
```

Driven on one 40-candle tape, both marks move with the figure: 10 gave 0.45 and
0.55, 50 gave 0.25 and 0.75, 75 gave 0.125 and 0.875, and 90 gave 0.05 and 0.95.
The tick reads the pair twice, and the upper mark is a hard gate. On a tape at
band position 0.75 the figure at 75 held the scrum and named two blockers, and
the same tape at 40 cleared both and armed it.

`src/trading/scrumming_bot.py` — the two readings in one tick

```python
_bb_lower_dt_pre, _bb_upper_dt_pre = self._bb_detect_thresholds()
```

Fire Threshold - The final Bollinger Band approach metric. Once satisfied, the bot can fire a trade.

A percentage from 0.10 to 10.00, at 0.50 % to start. It measures distance from
the band, where the Detect Threshold above it measures distance from the
midline.

`src/gui/bot_wizard.py` — the Fire Threshold row

```python
self._scrum_fire_pct = QDoubleSpinBox()
self._scrum_fire_pct.setRange(0.1, 10.0)
self._scrum_fire_pct.setDecimals(2)
self._scrum_fire_pct.setSuffix(" %")
self._scrum_fire_pct.setValue(0.5)
```

The ramp's near-band test is the only place this figure lands. Driven on one tape
at band position 0.75, 0.50 % and 2.00 % each left the ramp short of FIRE and the
scrum blocked; 10.00 % took the ramp from SEARCH to FIRE in one tick and removed
that blocker.

`src/trading/scrumming/tick_phases.py` — the near-band test

```python
fire_pct_frac = self.config.scrum_fire_pct / 100.0
_near_band = abs(_price - _bb_upper) <= fire_pct_frac * _bb_upper
```

BB Midline Gate - This is another, perhaps redundant layer, of Bollinger Band travel protection. It is different in that it is concerned with distance from the midline instead of the entire local width.

A checkbox, on at the start. While it is on, a scrum fires only above the
midline and a fold only below it.

`src/gui/bot_wizard.py` — the BB Midline Gate row

```python
self._bb_midline_gate = QCheckBox("BB Midline Gate")
self._bb_midline_gate.setChecked(True)
```

Driven on one tape at band position 0.27 with the position above target: on, the
tick refused the scrum and named the band gate in its blocker list; off, that
blocker was gone. The fold half of the same reading stayed open both ways,
because the price sat below the midline.

`src/trading/scrumming_bot.py` — the midline block

```python
if self.config.bb_midline_gate:
    scrum_ok = (bb_pos > 0.50) and not self._phantom_locked
    fold_ok_midline = bb_pos < 0.50
else:
    scrum_ok = not self._phantom_locked
    fold_ok_midline = True
```

Read Rate - To be re-evaluated.

From 1 to 60 minutes, at 5 minutes to start. It sets the search-mode read rate;
track mode reads ten times faster. Fire mode reads at that same faster rate.

The wizard writes it as `scrum_read_rate_min`, bot creation passes it through,
and the bot reads it at the top of every tick. The range starts at 1, so this
control cannot switch the throttle off.

`src/trading/scrumming_bot.py` — `ScrummingBot.tick`, the throttle

```python
if self.config.scrum_read_rate_min > 0 and not self._manual_fire_pending:
    _tick_sec = max(self.tick_interval, 0.1)
    _base_skip = max(1, int((self.config.scrum_read_rate_min * 60) / _tick_sec))
    self._tick_skip_search = _base_skip
    if self._scrum_target_mode in ("track", "fire"):
        self._tick_skip = max(1, _base_skip // 10)
    else:
        self._tick_skip = _base_skip
```

The tick itself runs every five seconds, so the figure in minutes becomes a count
of skipped ticks. Driven over eighty ticks: 1 minute skipped 12 and worked 6, 5
minutes skipped 60 and worked 1, and 60 minutes skipped 720 and worked none. A
skipped tick fetches no price and runs no gate.

`src/trading/scrumming_bot.py` — the tick period the count divides

```python
@property
def tick_interval(self) -> float:
    return 5.0
```

Band Travel - Previously described. To be re-evaluated.

A whole percentage from 0 to 100, at 70 % to start. Zero switches it off. The
wizard writes it as `band_travel_pct` and bot creation passes it through.

The engine reads it once per evaluation. It measures how far price has moved
since the last trade, as a share of the current band width, and raises a second
trigger once price covers that share. The same trigger overrides a trend hold,
so Band Travel can release a trade the trend gates were holding.

`src/trading/scrumming_bot.py` — the band-travel trigger

```python
_bb_width = max(bb_result.upper - bb_result.lower, 1e-12)
band_travel_frac = abs(ticker.last - self._last_trade_price) / _bb_width
if (
    abs(ticker.last - self._last_trade_price)
    >= self.config.band_travel_pct / 100.0 * _bb_width
    and delta > 0
):
    band_travel_triggered = True
```

Driven on one rising tape where 95 % of the last twenty candles closed up, with
price 37 % of the band width above the last trade: 0 left the trend hold in place
and suppressed the scrum, 30 raised the trigger and the override released it, and
70 left the hold in place again, because 37 is under 70. The figure decides, not
an on and an off.

`src/trading/scrumming_bot.py` — the override the trigger feeds

```python
trend_override = abs(delta) >= _interval_usd * 2.0 or band_travel_triggered
if trend_hold and trend_override:
```

BB Bullseye Check - If current price and Bollinger Band thresholds are equal, the user can opt to perform a double-sized trade.

A checkbox, on at the start.

`src/gui/bot_wizard.py` — the BB Bullseye row

```python
self._bb_bullseye = QCheckBox("BB Bullseye Check")
self._bb_bullseye.setChecked(True)
```

A double size is not in the engine. Nothing sizes a trade off this box. Its one
decision reader counts a band touch within 0.5 %, or a candle wick within 0.2 %,
as band proximity, and proximity with the delta at or over the interval arms the
BB priority skew. Driven on one tape with price at the upper band, on emitted the
skew and took the confidence floor from 0.25 to 0.1923; off emitted nothing and
left the floor where it was.

`src/trading/scrumming_bot.py` — the band touch the box admits

```python
_bb_proximity_upper = (
    (bb_pos >= _bb_upper_dt_pre) or _be_upper or _be_upper_wick
)
```

It does not bypass the Fire Threshold. Driven with price 0.3 % under the upper
band and the Fire Threshold at its lowest 0.10 %, the ramp stayed short of FIRE
with the box on and with it off, and the scrum carried the same blocker both ways.
What changes is the floor the TA confidence must clear.

`src/trading/scrumming_bot.py` — the floor the skew divides

```python
_ta_conf_skew = position_boost + bb_confidence_boost
if _bb_priority_arm:
    _ta_conf_skew += _BB_PRIORITY_SKEW
_eff_conf_floor = _skewed_confidence_floor(_ta_conf_skew)
```

The second reader writes the two BULLSEYE notices onto the Activity Log and
changes no decision.

`src/trading/scrumming/tick_phases.py` — the notice reader

```python
if bullseye_upper or bullseye_upper_wick:
    _ramp = self._scrum_target_mode.upper()
    _fire_gate = "passes" if _ramp == "FIRE" else "holds"
```

Wire Inflow Stack - To be re-evaluated.

A percentage from 0.00 to 100.00, at 1.00 % to start. The wizard writes it as
`wire_inflow_stack_pct`, and one method in the engine reads it. Above zero, wire
income arriving while the position sits within that band of its target and
within that band of its entry price goes onto the target and queues an
aggressive buy, rather than spreading over the fold queue.

Bot creation does not pass this setting, so a new bot takes the declared default
of 1.00 whatever you type here. The declared default and the wizard's start
value are the same number, so the loss shows only once you change it. Bot
Settings can set it on a bot that is already running. Issue #336 carries this.

`src/trading/scrumming/wire_routing.py` — `WireRoutingMixin.apply_wire_income`

```python
try:
    stack_pct = float(getattr(self.config, "wire_inflow_stack_pct", 1.0) or 0)
except (TypeError, ValueError):
    stack_pct = 0.0
_stack_eligible = False
_stack_reason = ""
_target = 0.0
_entry_px = 0.0
if stack_pct > 0:
```

Bot creation passes it now. One declaration serves the wizard path and the restore
path together, so every field the config declares reaches a new bot. Driven
through the creation route the wizard uses, a stored 0.00 arrived on the bot as
0.00 rather than the declared 1.00, which is what the sentence above was written
against.

`src/trading/container/config.py` — the one carried set

```python
carried = {f.name for f in fields(BotConfig)} - foreign - {"mode"}
kwargs = {
    key: value
    for key, value in _sanitize_deprecated_kwargs(collected).items()
    if key in carried
}
```

The caller is live. A fold routes its compounded profit through Smart Wire, which
hands the share to the target bot, and that is where this figure decides. Driven
on one bot sitting at its target and at its entry price, 0.00 parked ten dollars
as pending and left the target at 200.00, while 1.00 stacked it, took the target
to 210.00 and queued ten dollars for the next tick.

`src/trading/scrumming/tick_phases.py` — the live caller

```python
mgr.distribute_fold_profit(
    source_id=self.bot_id,
    profit_usd=float(_growth_applied),
    ref=f"fold-compound@{buy_fill:.8f}",
)
```

Hedge Rebalance Active - Determines if Current Price drifting below Initial Entry Price will have a limited amount of funds that can be used to keep re-zeroing the Target Delta at key bearish thresholds or areas of possible reversal.

A checkbox, on at the start. It opens the one group on the page that holds a
reserve outside Target Balance.

`src/gui/bot_wizard.py` — the Hedge Rebalance row

```python
self._hedge_rebalance = QCheckBox("Hedge Rebalance Active")
self._hedge_rebalance.setChecked(True)
```

Hedge Balance - Sets a limit on the amount of additional liquidity a given bot is allowed to absorb when Current Price drifts below Initial Entry Price.

At $200.00 to start, a reserve the bot holds apart from Target Balance.

`src/gui/bot_wizard.py` — `TradingParamsPage.get_config`, the settings these
two groups emit, in the order of the rows above

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

The group title on screen carries an internal release identifier after the
words Advanced Scrumming. Issue #420 carries that, and four more group titles
with it.

![The Circuit Breakers group.](p21-i0.png)

Now we arrive at some safety controls. Circuit Breakers are designed to fully inhibit trade actions for a given period should an extreme volatility (pump and dump) event occur. Soft Circuit Breakers have a candle-count based timer whereas Hard Circuit Breakers require the user to clear the bot to continue trading.

Soft CB Threshold - The amount of instantaneous, single-candle price action required for the bot to pause trading for a number of candles denoted by Soft CB Cooldown.

A percentage from 0.0 to 100.0, at 25.0 % to start. Zero switches it off. It
interrupts only the side of the market that moved, so an upward candle stops
scrums and a downward one stops folds.

`src/gui/bot_wizard.py` — the Soft CB Threshold row

```python
self._cb_soft_pct.setSuffix(" %")
self._cb_soft_pct.setValue(25.0)
```

The move the figure is compared against is the candle's own span, high minus low
over open, as a percentage. The figure decides: on one candle spanning 24.9 %, a
stored 10.0 % tripped the breaker and a stored 30.0 % did not, and on one
spanning exactly 25.0 % a stored 25.0 % tripped. A stored 0.0 % left a 50 %
candle alone, which is the off position the paragraph above describes.

The side follows the close against the open. A candle closing up shut the SCRUM
side, a candle closing down shut the FOLD side, and a shut side refuses the
trade at `circuit_breaker_scrum` or `circuit_breaker_fold` in the gate chain
while the other side's chain is untouched. The breaker is read once per worked
tick, and only a candle timestamp the bot has not seen can trip it, so one
candle never trips twice.

Hard CB Threshold - The amount of instantaneous, single-candle price action required for the bot to be hard stopped at which point the user must re-authorize trading.

The same range, at 35.0 % to start. Zero switches it off. Where the soft
breaker interrupts one side, this one pauses the bot outright and the pause
survives a restart.

`src/gui/bot_wizard.py` — the Hard CB Threshold row

```python
self._cb_hard_pct = QDoubleSpinBox()
self._cb_hard_pct.setRange(0.0, 100.0)
self._cb_hard_pct.setDecimals(1)
self._cb_hard_pct.setSuffix(" %")
self._cb_hard_pct.setValue(35.0)
```

Driven on the same span reading: at a stored 35.0 % a candle spanning 35.0 %
tripped the hard breaker and paused the bot, one spanning 34.9 % did not, and a
stored 40.0 % left the 35.0 % candle alone. A stored 0.0 % left a 90 % candle
alone. Once tripped it holds every later candle, quiet ones included, and only
the Reset All Breakers button clears it — the reset reports the trip percentage
it cleared and returns the bot from paused to running. The pause is written into
the bot's stored record, so a bot restored from a hard trip comes back paused.

The pause reaches the scrum and the fold gate chain. It does not reach the five
trade paths the tick reads before it: Manual Fire, the Wire Stack fire, Max
Cartridge, Detonation and the initial entry. Measured on a hard-tripped, paused
bot with a position $30.00 past a $20.00 Max Cartridge threshold: the bot still
wrote MAX CARTRIDGE FIRE and still sent the cartridge trade notification, while
the same bot with Max Cartridge at 0.0 % wrote nothing. Nothing is changed here
for that, because raising the hard breaker above the cartridge would stop a
rebalance that fires on live bots today.

Soft CB Cooldown - This is the number of candles that must close before the Soft Circuit Breaker opens again.

From 1 to 100 candles, at 3 to start. It is counted in closed candles, so its
real length follows the bot's own timeframe.

`src/gui/bot_wizard.py` — the Soft CB Cooldown row

```python
self._cb_cooldown = QSpinBox()
self._cb_cooldown.setRange(1, 100)
self._cb_cooldown.setValue(3)
```

The figure is the count of fresh candles the shut side waits out, and it is the
count the code uses: a stored 1 re-opened on the first fresh candle, a stored 3
on the third, and a stored 10 on the tenth. The count only moves on a candle
timestamp the bot has not seen, so a repeated candle left the remaining count
where it was. A record carrying a cooldown of 0 is read as 3, the declared
default. A record carrying a word stops the breaker check for that tick with a
warning, which leaves the soft breaker unable to trip.

While a cooldown holds, the shut side is refused at the breaker gate and the bot
keeps running — the cooldown pauses nothing. It ends on its own when the count
reaches zero, with a SOFT CIRCUIT BREAKER RESET line naming the side that
re-opens, and the Reset All Breakers button ends it early.

Max Cartridge Size - This is the maximum amount of deviation allowed for the Target Delta. At this threshold the bot is actively and aggressively looking for a trade opportunity.

A percentage from 0.0 to 200.0, at 10.0 % to start. Crossing it fires an
aggressive rebalance that bypasses the detection, hysteresis and soft-breaker
checks. It is the one figure on the page whose range runs past 100.

`src/gui/bot_wizard.py` — the Max Cartridge Size row

```python
self._max_cartridge_pct = QDoubleSpinBox()
self._max_cartridge_pct.setRange(0.0, 200.0)
self._max_cartridge_pct.setDecimals(1)
self._max_cartridge_pct.setSuffix(" %")
self._max_cartridge_pct.setValue(10.0)
```

The threshold is Target Balance times the figure over 100, and the fire is on
absolute Target Delta. Driven on a $200.00 target: at 10.0 % the threshold was
$20.00, a position $20.00 past target fired and $19.99 past target did not; at
5.0 % the threshold was $10.00, $11.00 fired and $9.99 did not; at 0.0 % a
position $100.00 past target fired nothing, which is the off position.

A correction to the sentence above it: the hysteresis check is not bypassed. The
tick tests the opposing-trade pivot before the fire and writes MAX CARTRIDGE
BLOCKED instead, naming the price the pivot still needs. What the fire does
bypass is the band detection, the higher-timeframe bias and the soft breaker —
and, because the tick reads this figure before it reads either breaker, the hard
breaker as well.

Smart Cartridge - This allows the Max Cartridge Size to organically resize in response to current price range as defined by the current-candle Bollinger Band reading.

One checkbox labelled Calibrate to BB range, off at the start. While it is on,
the cartridge size comes from the current band range instead of the fixed
percentage above it.

`src/gui/bot_wizard.py` — the Smart Cartridge row

```python
self._cartridge_smart_chk = QCheckBox("Calibrate to BB range")
self._cartridge_smart_chk.setChecked(False)
```

The band range is upper minus lower over the midline, as a percentage, and the
box swaps it in for the fixed figure. It is held between two bounds: never below
the Opposing Trade Interval, never above Smart Ceiling. Driven on a $200.00
target with the fixed figure at 10.0 %: off, the threshold stayed $20.00; on,
with a band spanning 20.0 % of its midline, the threshold became $40.00. On the
same tick the bot read a band spanning 80.0 %, the clamp gave 30.0 % and the
threshold $60.00, and a position $30.00 past target that fired with the box off
fired nothing with it on.

The band the box reads is the one the previous worked tick stored, so the first
worked tick after a start has no band and keeps the fixed figure.

Smart Ceiling - To be re-evaluated.

A percentage from 1.0 to 100.0, at 30.0 % to start. It caps the cartridge
threshold while Smart Cartridge is on.

It is the upper of the two bounds on the band range, and it binds only when the
band is wider than it. Driven on a $200.00 target with Smart Cartridge on: a
band spanning 120.0 % under a 30.0 % ceiling gave 30.0 % and a $60.00 threshold,
the same band under a 15.0 % ceiling gave 15.0 % and $30.00, and a band spanning
29.0 % under the 30.0 % ceiling gave 29.0 % and $58.00 — the ceiling did not
bind. A band spanning 0.5 % gave 1.0 %, the Opposing Trade Interval, because the
lower bound binds there instead.

The control cannot emit a zero. A record hand-edited to carry one is read as
30.0 %, the declared default, not as no ceiling.

`src/gui/bot_wizard.py` — `TradingParamsPage.get_config`, the settings this
group emits, in the order of the rows above

```python
"circuit_breaker_soft_pct": self._cb_soft_pct.value(),
"circuit_breaker_hard_pct": self._cb_hard_pct.value(),
"circuit_breaker_cooldown_candles": self._cb_cooldown.value(),
"max_cartridge_size_pct": self._max_cartridge_pct.value(),
"max_cartridge_smart": self._cartridge_smart_chk.isChecked(),
"max_cartridge_smart_ceiling_pct": self._cartridge_smart_ceiling.value(),
```

A trip stops a trade at one gate on each side of the chain, and
[07-indicators.md](07-indicators.md) lists both chains in full.

`src/trading/gate_chain.py` — the two breaker gates in the built chains

```python
CircuitBreakerGate(side="scrum"),
```

`src/trading/gate_chain.py` — and the fold chain

```python
CircuitBreakerGate(side="fold"),
```

![The Risk Controls and Strategy Gate Flags groups.](p22-i0.png)

After Circuit Breakers, which help defend against extreme volatility, we come to Risk Controls. These are designed to cap the amount of profit or growth a given bot can earn before performing a full position exit.

Enable Position Ceiling - Enables a growth cap for a given position.

A checkbox, off at the start. Nothing in the Risk Controls group acts until it
is on.

`src/gui/bot_wizard.py` — the Position Ceiling row

```python
self._position_ceiling_enabled = QCheckBox("Enable Position Ceiling")
self._position_ceiling_enabled.setChecked(False)
```

**Functional.** The box gates six places in the engine. Five refuse or shrink a
buy: the ceiling figure itself, the pre-buy check, the buy executor, the first
entry of a brand-new bot, and the fold hold. The sixth runs on restore and pulls
a stored target back down to the ceiling. The box is read at the moment of each
decision and never copied aside, so unticking it releases the brake on the very
next read. Driven on a two hundred dollar anchor at three times: with the box
off, a fold rebuy of fifty dollars onto a seven hundred dollar position passed;
with it on, the same buy was refused; untick, and it passed again.

`src/trading/scrumming_bot.py` — `ScrummingBot.position_ceiling_usd`

```python
if not getattr(self.config, "position_ceiling_enabled", False):
    return None
```

**Where the code departs.** Two of the three Detonation rows below do not wait
for this box. The detonation check reads its own box and the anchor, and a search
of the engine for a detonation site that reads the ceiling box returns nothing.
Driven: with the ceiling box off and Detonation on, the hourly check ran and
asked the venue for candles. The sentence above holds for the ceiling and the
fold taper, and Detonation is the exception.

`src/trading/scrumming_bot.py` — `ScrummingBot._check_detonation_trigger`, its
first two conditions

```python
if not getattr(self.config, "detonation_enabled", False):
    return False
...
if current_value <= self._anchor_target_balance:
    return False
```

Ceiling Multiple - This setting caps the maximum amount of growth a position at a multiple of the Target Balance (anchor) and, once reached (and under higher timeframe bullish conditions with Detonation enabled) will allow the entire position to be sold and the corresponding bot will pause all further operations. Without Detonation enabled, this becomes a user notification.

From 1.0 to 10.0, at 5.0x anchor to start. The anchor is the target balance the
bot was created with, not the balance it has grown to. It steps half a multiple
at a time and carries its unit in the box.

`src/gui/bot_wizard.py` — the Ceiling Multiple row

```python
self._position_ceiling_multiple = QDoubleSpinBox()
self._position_ceiling_multiple.setRange(1.0, 10.0)
self._position_ceiling_multiple.setDecimals(1)
self._position_ceiling_multiple.setSingleStep(0.5)
self._position_ceiling_multiple.setSuffix("x anchor")
self._position_ceiling_multiple.setValue(5.0)
```

**Functional.** The figure becomes a dollar ceiling, the anchor times the
multiple. On a two hundred dollar anchor the four corners of the range read: one
gives two hundred dollars, three gives six hundred, five gives one thousand, ten
gives two thousand. The refusal is strictly above, so a projected position of
exactly six hundred dollars is allowed against a six hundred dollar ceiling and
six hundred dollars and one cent is refused. The same seven hundred and fifty
dollar projection is refused at three and allowed at six, which is the figure
changing the answer.

`src/trading/scrumming_bot.py` — `ScrummingBot._pre_buy_allowed`, layer two

```python
_smart_mult = max(1.0, min(10.0, _smart_mult))
_smart_ceiling_usd = _anchor * _smart_mult
if _projected > _smart_ceiling_usd:
```

**Functional.** While the ceiling binds, the bot still sells and stops buying.
The fold side shrinks first and then stops: the fold's dollar size is multiplied
by a taper that is full below half the ceiling, falls in a straight line to a
tenth across the upper half, and reaches zero at the ceiling. Measured against a
six hundred dollar ceiling: two hundred and ninety dollars held full size, five
hundred and ninety dollars cut the fold to thirteen per cent, and six hundred
dollars stopped it. Three things release the brake — price falling back under the
ceiling, a detonation resetting the target to the anchor, and unticking the box.

`src/trading/scrumming/tick_phases.py` — `_tick_execute_fold` spends the taper

```python
_taper = self.fold_rate_taper
...
buy_cost = _fusd * _taper
```

**Where the code departs.** The sentence above says the bot pauses all further
operations once the ceiling is reached and the position is sold. The executor
does not pause it. It resets the target balance to the anchor, clears the fold
queue and the tranches, reseeds the lots at the fill price, and logs that the bot
will re-accumulate from scratch on the next dip. A search of the detonation
executor for a pause call returns nothing. The second half of the sentence does
hold: with Detonation off, the ceiling only brakes, and the operator is told
through the Console line and through the Fire button's own tooltip on the Bot
Swarm row.

`src/trading/scrumming/execution.py` — `_execute_detonation`, what it resets

```python
prior_target = self._target_balance
self._target_balance = self._anchor_target_balance
...
self._fold_tranches.clear()
self._fold_queue_usd = 0.0
```

**Functional.** One name serves two unrelated mechanisms, and the engine's own
wording has been corrected in this unit. The percentage box in Circuit Breakers
labelled Smart Ceiling caps the cartridge threshold, and the engine reports it
inside its cartridge line as a percentage. This dollar ceiling is what every
ceiling refusal in the engine names, and those lines now read Position Ceiling
and Ceiling Multiple, which are the labels on this screen. A reader can now tell
the two apart: one is a percentage under a cartridge heading, the other is a
dollar figure under the name of the control that set it.

`src/trading/scrumming/tick_phases.py` — the cartridge line, for contrast

```python
f"SMART CARTRIDGE calibrated to "
f"{_smart_pct:.2f}% "
f"(BB range {_bb_range_pct:.2f}%, "
f"floor={_interval_floor:.2f}%, "
f"ceiling={_smart_ceiling:.2f}%). "
```

Enable Detonation - Enables an entire remaining position to be sold after the Ceiling Multiple growth threshold is crossed.

A checkbox, off at the start. Detonation needs the box ticked, a position worth
more than its anchor, and a bullish reading at or above the confidence you set.
It also needs the reading to have just turned bullish, so a tape that was
already bullish last time fires nothing.

`src/trading/scrumming_bot.py` — `ScrummingBot._check_detonation_trigger`

```python
conf_min = float(getattr(self.config, "detonation_confidence_min", 0.75))
is_bullish = (
    summary.consensus_direction == SignalDirection.BULLISH
    and summary.consensus_confidence >= conf_min
)

fired = is_bullish and not self._detonation_last_signal_bullish
```

**Where the code departs.** The sentence above says the sale happens after the
Ceiling Multiple threshold is crossed. The engine's bar is the anchor, not the
ceiling. Driven on a two hundred dollar anchor: a position worth two hundred
dollars and one thousandth of a cent passed the bar and the hourly check fetched
candles; a position worth exactly two hundred dollars was refused before any
fetch. A bot with Detonation on and the ceiling left off can therefore harvest at
any value above its starting target, well below any multiple.

`src/trading/scrumming_bot.py` — the bar `_check_detonation_trigger` actually uses

```python
current_value = (
    self._current_holdings * price * float(self._quote_to_usd or 1.0)
)
if current_value <= self._anchor_target_balance:
    return False
```

**Functional.** The box is what starts the whole path. Driven with the box off,
the detonation phase returned at once and asked the venue for nothing; with it on,
the check ran and asked for one candle series. Behind the box sits an hourly rate
limit, measured: a gap of three thousand five hundred and ninety-nine seconds
since the last check fetched nothing and a gap of three thousand six hundred
fetched once.

`src/trading/scrumming/tick_phases.py` — `_tick_detonation`

```python
if getattr(self.config, "detonation_enabled", False):
    try:
        fired = await self._check_detonation_trigger(ticker)
```

Detonation TF - Selects the timeframe for the chart that is being evaluated for bullish conditions that will allow the detonation to occur.

Two entries, 1d and 1w. The label and the stored value are the same string on
both rows, which is not true of every picker in the wizard.

`src/gui/bot_wizard.py` — the Detonation TF row

```python
self._detonation_timeframe = QComboBox()
self._detonation_timeframe.addItem("1d", "1d")
self._detonation_timeframe.addItem("1w", "1w")
```

**Functional.** The pick does two jobs. It names the candle series the vote reads,
and it sets how long the one-shot bullish latch survives between checks. One day
keeps the latch eighty-six thousand four hundred seconds and one week keeps it six
hundred and four thousand eight hundred. Driven on one bullish tape with the latch
already set and exactly eighty-six thousand four hundred seconds since the last
check: the daily pick retired the latch and fired, the weekly pick kept the latch
and did not. One second earlier, neither fired. That is the pick changing the
answer on identical candles.

`src/trading/scrumming_bot.py` — the latch life

```python
latch_ttl = max(
    float(TIMEFRAME_SECONDS.get(tf, TIMEFRAME_SECONDS["1d"])),
    _DETONATION_LATCH_MIN_TTL_S,
)
if elapsed >= latch_ttl:
    self._detonation_last_signal_bullish = False
```

Min Confidence - This is the minimum technical analysis confidence index (via the Indicator Voting Panel) that will allow the detonation to occur.

From 0.50 to 1.00, at 0.75 to start.

**Functional.** The reader works, and it is exact. On one tape whose consensus
read zero point two three three four, a bar of zero point two three three three
fired and a bar of zero point two three three five did not, on the same candles
with the same state. The comparison is at or above, so a bar set to the reading
itself fires.

`src/trading/scrumming_bot.py` — the comparison

```python
conf_min = float(getattr(self.config, "detonation_confidence_min", 0.75))
is_bullish = (
    summary.consensus_direction == SignalDirection.BULLISH
    and summary.consensus_confidence >= conf_min
)
```

**Where the code departs.** No figure this box can emit was reached. The box
starts at zero point five, and across one hundred and seventy-one tapes — nine
shapes, three lengths, three noise levels — the highest bullish consensus the
voting panel produced was zero point two five three four. The engine's own floors
on the same quantity sit lower still: a quarter for an ordinary trade, and
nineteen hundredths on the band-priority arm. A bar of zero point five refused
every tape driven, including the strongest. Nothing in this reading is impossible
in principle: with every voter agreed at its own best reading the panel would
reach eighty-four hundredths, and the twelve voters simply cancel each other long
before that. The gap is between the range the box offers and the range the panel
produces.

`src/trading/scrumming_bot.py` — the quantity, and the two floors the rest of the
engine uses against it

```python
_TA_CONFIDENCE_FLOOR = 0.25
_BB_PRIORITY_CONFIDENCE_FLOOR = _TA_CONFIDENCE_FLOOR / (1.0 + _BB_PRIORITY_SKEW)
```

**Design intention.** Two repairs are possible and both change what a live bot
does on its next tick, so neither is shipped here. The box's floor could move down
to meet the panel, or the detonation could compare against the same floor the rest
of the engine uses. Either one arms a control that is quiet today, on bots holding
real money, which is the operator's decision and not a wiring job.

PROPOSED — `src/gui/main_tabs/live_settings_tab_surface.py`, the row's range

```python
"range": (0.10, 1.00),
```

**Functional.** Two things the bar does not reach. It is absent from the record
the Bot Swarm row reads, so that tooltip can report the timeframe a bot is
watching and never the bar it must clear. And the detonation check builds a fresh
voting panel with no weights, so a bot carrying the operator's own indicator
weights is judged for detonation by the default weights instead.

`src/trading/scrumming_bot.py` — the panel the detonation check builds

```python
engine = VotingEngine()
parsed = candles_from_raw(candles)
summary = engine.compute_all(parsed, tf)
```

`src/gui/bot_wizard.py` — `TradingParamsPage.get_config`, the settings this
group emits, in the order of the rows above

```python
"position_ceiling_enabled": self._position_ceiling_enabled.isChecked(),
"position_ceiling_multiple": self._position_ceiling_multiple.value(),
"detonation_enabled": self._detonation_enabled.isChecked(),
"detonation_timeframe": self._detonation_timeframe.currentData(),
"detonation_confidence_min": self._detonation_confidence_min.value(),
```

Next we use the Strategy Gate Flags which allows top-level trade restrictions to be enabled or disabled thus relaxing or restricting the conditions under which a trade action can occur. The settings, in this case, are self-descriptive.

**Functional.** The box draws five checkboxes, all ticked at the start: SCRUM
requires bullish TA, SCRUM holds in sustained uptrend, SCRUM defers to
higher-TF bullish, FOLD requires bearish TA, and FOLD defers to higher-TF
bearish.

`src/gui/bot_wizard.py` — `TradingParamsPage.get_config`, the six flags this
group emits

```python
"scrum_require_ta_bullish": self._gate_scrum_ta_chk.isChecked(),
"scrum_hold_in_uptrend": self._gate_scrum_uptrend_chk.isChecked(),
"scrum_defer_to_htf": self._gate_scrum_htf_chk.isChecked(),
"fold_require_ta_bearish": self._gate_fold_ta_chk.isChecked(),
"fold_hold_in_downtrend": True,  # reserved, no gate
"fold_defer_to_htf": self._gate_fold_htf_chk.isChecked(),
```

**Design intention.** Six flags are declared, the box shows five, and the
missing one is the fold-side twin of a scrum gate that works. It goes out as a
hard True, and nothing in the engine reads it. Its scrum mirror holds a sell
during a sustained uptrend, and the fold twin would hold a buy during a
sustained downtrend.

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

**Functional.** The sixth flag is gone. It is removed from the bot config, from
the restore round-trip and from both wizard surfaces, so the wizard emits five
gate flags and the box still draws five checkboxes. A bot record written before
the removal still loads. Bot creation keeps only the fields the config declares,
so the old key is dropped on the way in and every other flag arrives unchanged.

Nothing the engine does changes. The field had no reader that moved a decision,
so no running bot fires differently on its next tick. Driven on both sides over
five candle tapes, every gate verdict read the same before the removal and
after it.

Two measured facts bear on the proposal above. The engine holds one trend
figure, a count of the last twenty candles that close above their open, and it
holds no downtrend figure for a gate to read. The proposed gate reads
`ctx.eff_trend_hold`, which is that bullish count after the scrum checkbox has
been applied to it. As written it would hold a buy during an uptrend, and the
scrum checkbox would switch it. A fold hold needs its own measurement and its
own control before it needs a flag.

![The Profit Routing group.](p22-i1.png)

Moving onto the final section, we have Profit Routing which was intended to allow profits to be routed differently during initial set-up. This will be re-evaluated and potentially removed.

The group writes two settings and stores them with the bot. No module under
`src/trading/` reads either one. The wizard records the route, Bot Settings can
change it, and a restart restores it. None of that reaches a trade:
`_route_scrum_proceeds_via_wires` moves the scrum proceeds, and it never asks
what the route says.

The bot config declares both fields with a default, so the destination a bot
holds is always the first entry in the list. Issue #336 carries this, with the
rest of the settings the wizard writes and bot creation drops.

`src/trading/container/restore.py` — the round-trip that puts both fields back
on a restarted bot

```python
"profit_route": cfg.get("profit_route", "fold_to_target"),
"profit_route_bot_id": cfg.get("profit_route_bot_id", ""),
```

Route - Destination for profits.

Four destinations: fold back to target balance, send to spendable, split fold
and spendable by percentage, and route to another bot. Only the last of the
four makes the Target bot ID field below it mean anything.

`src/gui/bot_wizard.py` — the Route row

```python
self._profit_route = QComboBox()
self._profit_route.addItem("Fold back to target balance", "fold_to_target")
self._profit_route.addItem("Send to spendable", "spendable")
self._profit_route.addItem("Split fold/spendable per %", "split")
self._profit_route.addItem("Route to another bot (cross-bot)", "cross_bot")
```

Target bot ID - Field for manually a bot ID which was intended to create a Smart Wire under the Bot Swarm tab.

A free-text field. Its placeholder tells you to leave it blank unless you chose
the cross-bot route.

`src/gui/bot_wizard.py` — `TradingParamsPage.get_config`, the settings this
group emits, in the order of the rows above

```python
"profit_route": self._profit_route.currentData(),
"profit_route_bot_id": self._profit_route_bot_id.text().strip(),
```

![The Phantom Balance Bots page.](p23-i0.png)

Lastly we have the selection for the Phantom (Balance) Bots. These are intended to provide trade action overrides from higher timeframe charts and indicator sets which, in turn, may result in an improved trade or prevent a premature one.

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

**Design intention.** The engine behind this page is unfinished. The Indicator
Voting Panel section of this manual records that phantom bots are still in
active development and that related features do not yet work, so nothing is
proposed for the page.

In development.

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

**Design intention.** Phantom overrides and profit folding belong to the
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

**Design intention.** The five pool bases are exactly the assets named as base
currencies above. Leaving the list empty hands the choice back to the bot, and
only a box that is both ticked and available reaches the config.

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
shows this one. The two sides never appear together.

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

The group title in the source reads Extractor, an em dash, Pool, an ampersand,
then Artillery. Qt reads that ampersand as a keyboard-mnemonic marker, so the
rendered title drops it and underlines the A of Artillery. The figure shows the
gap the dropped character leaves. Issue #421 carries this.

Chunk size (USD) - This determines the maximum amount of the parent’s pool that the Extractor can use.

From $10.00 to $10,000,000.00, at $100.00 to start. It is the pool every
artillery round below is drawn from.

`src/gui/bot_wizard.py` — the Chunk size row

```python
self._ext_chunk_size_usd = QDoubleSpinBox()
self._ext_chunk_size_usd.setRange(10.0, 10_000_000.0)
self._ext_chunk_size_usd.setPrefix("$")
self._ext_chunk_size_usd.setDecimals(2)
self._ext_chunk_size_usd.setValue(100.0)
```

Artillery size (USD) - This determines the individual size of Extractor Tranches.

From $0.50 to $100,000.00, at $5.00 to start. The default is set small enough
to fire often and still clear a venue's minimum order cost.

`src/gui/bot_wizard.py` — the Artillery size row

```python
self._ext_artillery_size_usd = QDoubleSpinBox()
self._ext_artillery_size_usd.setRange(0.5, 100_000.0)
self._ext_artillery_size_usd.setPrefix("$")
self._ext_artillery_size_usd.setDecimals(2)
self._ext_artillery_size_usd.setValue(5.0)
```

Watch list top-N - The determines the number of Alternate Currency pairs the bot will scan for potential extraction.

From 5 to 10, at 8 to start. The pairs are ranked by twenty-four hour volume,
so the list holds the most liquid alternates against the chosen base.

`src/gui/bot_wizard.py` — the watch list size row

```python
self._ext_scan_top_n = QSpinBox()
self._ext_scan_top_n.setRange(5, 10)
self._ext_scan_top_n.setValue(8)
```

Watch list refresh - This determines the rate at which the Extractor will scan its watched markets. This is the equivalent of a Timeframe for the Extractor but covers multiple pairs.

From 10 to 240 candles, at 60 to start, which is once an hour at a one-minute
cadence. It re-ranks the list rather than re-reading one pair.

`src/gui/bot_wizard.py` — the watch list refresh row

```python
self._ext_scan_refresh = QSpinBox()
self._ext_scan_refresh.setRange(10, 240)
self._ext_scan_refresh.setValue(60)
self._ext_scan_refresh.setSuffix(" candles")
```

Pool Reserve - To be re-evaluated.

A percentage from 0.0 to 90.0, at 50.0 % to start. Bot creation passes it
through as `extractor_pool_reserve_pct`, and one method reads it: the capacity
check the artillery path runs before it fires a round. The reserve is that share
of the pool, and the check refuses any round that would take the free pool below
it.

The share counts against the pool the operator allocated, not against what is
left of it. Corrections that have already drained the pool therefore cannot hide
inside the reserve arithmetic.

`src/trading/extractor_bot.py` — `ExtractorBot._has_chunk_capacity`

```python
reserve = self._chunk_size_base * (
    self.config.extractor_pool_reserve_pct / 100.0
)
return (self._chunk_free_base - artillery_base) >= reserve
```

Exit % - To be re-evaluated.

A percentage from 10.0 to 100.0, at 100.0 % to start. Bot creation passes it
through as `extractor_exit_pct`. It sets the share of a position's alt units an
exit sells, and the Extractor reads it nine times across three methods: the
profitability test, the bullish exit, and the per-position Manual Fire.

The profitability test is the one that can refuse. It prices the proportional
sell in base units, takes the trading fee off, and compares the result against
the same share of the cost basis. An exit that would gain dollars but lose base
units does not happen.

`src/trading/extractor_bot.py` — `ExtractorBot._exit_is_profitable_in_base`

```python
units_to_sell = pos.alt_units * (self.config.extractor_exit_pct / 100.0)
base_back = units_to_sell * alt_price_in_base
fee_pct = float(getattr(self.config, "trading_fee_pct", 0.6))
base_back_after_fee = base_back * (1.0 - fee_pct / 100.0)
base_in_proportional = pos.cost_basis_base * (
    self.config.extractor_exit_pct / 100.0
)
return base_back_after_fee > base_in_proportional
```

Max compounding tier - Allows the Extractor to attempt a number of compounding Swing Trades with a given Extractor Tranche with subsequent re-entries based upon the Parent Scrumming Bot’s Minimum Opposing Trade Distance + Trade Fee + Bollinger Band extension settings.

From 1 to 10, at 3 to start. The first tier always locks its gain back to the
pool, and the counter is held by the position rather than by the bot, so it
ends when the position does.

`src/gui/bot_wizard.py` — the compounding tier row

```python
self._ext_max_tier = QSpinBox()
self._ext_max_tier.setRange(1, 10)
self._ext_max_tier.setValue(3)
```

Max cost-basis multiple - To be re-evaluated.

From 1.0x to 10.0x, at 2.0x to start. Setting it to 1.0 stops averaging down.
Bot creation passes it through as `extractor_max_cost_basis_multiple`, and the
correction path reads it twice. The first read is the ceiling: the bot may
average a position down until its cost basis reaches this multiple of its
opening round, then it holds and waits for the exit.

The second read writes a log line, and it prints this multiple where a
correction count belongs. The line reads corrections=1/2x cap, and nothing
anywhere compares the correction counter against a cap. Issue #438 carries this.

`src/trading/extractor_bot.py` — `ExtractorBot._maybe_fire_correction`, the
ceiling

```python
max_basis = pos.artillery_size_base * float(
    self.config.extractor_max_cost_basis_multiple
)
headroom = max_basis - pos.cost_basis_base
if headroom <= 0:
    return  # hard floor reached; wait for bullish exit
```

Direction - To be re-evaluated.

Two entries: Normal, which runs base to alt and buys first, and Inverted, which
runs standing alt to base and sells first.

`src/gui/bot_wizard.py` — `TradingParamsPage.get_config`, the settings this
group emits, in the order of the rows above

```python
"extractor_chunk_size_usd": self._ext_chunk_size_usd.value(),
"extractor_artillery_size_usd": self._ext_artillery_size_usd.value(),
"extractor_scan_top_n": int(self._ext_scan_top_n.value()),
"extractor_scan_refresh_candles": int(
    self._ext_scan_refresh.value()
),
"extractor_pool_reserve_pct": self._ext_pool_reserve.value(),
"extractor_exit_pct": self._ext_exit_pct.value(),
"extractor_max_compounding_tier": int(
    self._ext_max_tier.value()
),
"extractor_max_cost_basis_multiple": self._ext_max_cost_basis.value(),
"extractor_direction": self._ext_direction.currentData(),
```

![The Extractor group, remaining five rows.](p26-i0.png)

Standing alt units (inverted) - To be re-evaluated.

Eight decimal places, at 0 to start. The Inverted direction reads it; the
Normal direction ignores it. The field takes up to a billion units. The wizard
writes it as `inverted_extractor_standing_alt_units`.

Bot creation passes neither this number nor the Direction beside it, so a new
Extractor runs Normal with a standing position of zero whatever you enter.
The one method that reads the number, `set_initial_chunk_rate`, has no caller in
the product source either. Only tests call it. Issue #437 carries the method,
and issue #336 the settings creation drops.

`src/trading/extractor_bot.py` — `ExtractorBot.set_initial_chunk_rate`, the
inverted branch

```python
_standing = float(
    getattr(self.config, "inverted_extractor_standing_alt_units", 0) or 0
)
if self._is_inverted and _standing > 0:
    self._chunk_size_base = _standing
    self._chunk_size_usd = _standing * usd_per_base
```

Correction skip candles - To be re-evaluated.

From 0 to 100 candles, at 4 to start. It throttles averaging down: the Extractor
will not correct the same position again until this many have passed. One method
reads it, the correction path, and it counts ticks rather than candles. The
Extractor ticks every five seconds, so 4 is twenty seconds on any timeframe.

Bot creation does not pass it, so a new bot takes the declared default of 4.
Issue #438 carries the counting, and issue #336 the drop.

`src/trading/extractor_bot.py` — `ExtractorBot._maybe_fire_correction`, the
throttle

```python
last_tick = self._last_correction_tick.get(pos.pair, -(10**9))
if self._tick_counter - last_tick < int(
    self.config.extractor_correction_skip_candles
):
    return  # skip-candles throttle
```

Drawdown threshold - To be re-evaluated.

A percentage from 0.00 to 50.00, at 3.00 % to start. One method reads it, and
that method decides when a position counts as down: the current dollar value
against the dollar value snapshotted at firing, which never changes afterwards.
Crossing the threshold puts a position in front of the correction path.

The wizard writes it as `extractor_drawdown_threshold_pct`, and bot creation
does not pass it, so a new bot takes the declared default of 3.00. Issue #336
carries this.

`src/trading/extractor_bot.py` — `ExtractorBot._is_in_drawdown`

```python
current_usd = self._position_value_usd(pos, alt_price_in_base)
threshold = pos.artillery_size_usd_at_entry * (
    1.0 - self.config.extractor_drawdown_threshold_pct / 100.0
)
return current_usd < threshold
```

Trend Strength Threshold - To be re-evaluated.

From 0.000 to 1.000, at 0.650 to start.

A sixth control sits in this part of the group and no entry above names it.
Hedge budget (USD) starts at $0.00, which switches it off. Above zero, the bot
converts it into a base-currency reserve held out of artillery rotation. This
manual states that the control exists and claims nothing about what it is for.

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

`src/gui/widgets/status_log.py` — `StatusLog.log`, the pause branch

```python
if len(self._pause_buffer) < self._pause_buffer_cap:
    self._pause_buffer.append((ts, message, level))
return
```

**Design intention.** Two decisions follow from the pane's job. The buffer
drops the newest line rather than the oldest, so the lines around the moment
you hit pause are the ones that survive. And a pane that has gone quiet says so
in the pane, because silence otherwise reads as calm.

`src/gui/main_tabs/trading_tab.py` — the silence check

```python
bots_active = self._bot_manager and any(
    b.state.value == "running"
    for b in getattr(self._bot_manager, "_bots", {}).values()
)
if bots_active and age > 600:
```

**What the lines say.** Every tick message follows one shape: the event in
capitals, the side in square brackets where the message has one, then a short
sentence and the numbers behind it. A message names the gate that refused and
the reading that made it refuse. It never names a direction or a strength the
data behind it cannot give.

The gate snapshot is the longest of them. It writes the twelve-voter panel as a
count and three groups, strongest confidence first, with an indicator's own raw
reading in brackets where it publishes one. A neutral vote carries no
confidence, so only its name prints.

```
RISK GATE [SCRUM] blocked by hysteresis_scrum. Price $0.00000317.
Panel 6 bullish, 3 bearish, 3 neutral.
bullish vortex 1.00, kaufman_er 0.70 (er 1.0), macd 0.60, adx 0.36 (adx 25.52),
volume 0.35, supertrend 0.26.
bearish bollinger_bands 0.82, stochastic_rsi 0.50, slingshot 0.35.
neutral ichimoku, rsi, zscore (z 0.143).
```

A hold line names the half of the gate that failed. Two conditions must both
hold before the TA gate lets a scrum through: the direction has to be bullish
or neutral, and the confidence has to clear the floor. The line says which one
refused, so a bullish reading held back by its confidence is never reported as
a wait for a bullish reading.

`src/trading/scrumming_bot.py` — the scrum hold reason

```python
if eff_direction not in (
    SignalDirection.BULLISH,
    SignalDirection.NEUTRAL,
):
    _scrum_why = f"TA={eff_direction.name} is not BULLISH or NEUTRAL"
else:
    _scrum_why = (
        f"TA={eff_direction.name} but confidence "
        f"{eff_confidence:.4f} < {_eff_conf_floor:.4f} floor"
    )
```

**Design intention.** A confidence and the floor it is measured against print
at four decimals wherever a message compares them. At two decimals they
collided, and the pane showed a comparison of a number against itself, which is
not a statement anybody can act on.

Both snapshot lines read one renderer, so the blocked half and the fired half
of a decision cannot drift into two shapes.

`src/trading/scrumming/snapshots.py` — the one panel renderer

```python
def _panel_line(summary: Optional[VotingSummary]) -> str:
    panel = _build_panel_snapshot(summary)
    if not panel:
        return PANEL_ABSENT_TEXT
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

`src/gui/main_window.py` — `_on_api_event`, the thread check

```python
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

#### Two mechanisms with no control on this tab

Two more mechanisms sit inside the engine and the wizard offers no switch for
either. Neither appears anywhere else in this manual, and their state differs:
one runs, one is declared and dormant.

**Fair Value Gap.** Three candles that leave a gap between the first and the
third mark a price band the market tends to come back to. The indicator scans
the last 24 candles for those bands, reports whether price sits inside one or
is approaching one, counts how many are open, and gives the bounds of the
nearest. It is not one of the twelve voters. It adjusts the confidence of a
side that already has a case: a fold gains ten points near a bullish band, a
scrum gains eight inside a bearish one.

`src/trading/indicators/fvg.py` — the four constants that set its reach

```python
FVG_LOOKBACK = 24  # candles to scan for 3-candle gap patterns

FVG_PROXIMITY_PCT = 0.005  # "approaching from above": within 0.5% of FVG top

FVG_BULL_BOOST = 0.10  # fold confidence boost when in/near bullish FVG

FVG_BEAR_BOOST = 0.08  # scrum confidence boost when inside bearish FVG
```

The engine imports the indicator and its four constants together, so the
adjustment travels with the reading rather than being applied somewhere else.

`src/trading/ta_engine.py` — what it takes from that module

```python
from .indicators.fvg import (
    FVG_BEAR_BOOST,
    FVG_BULL_BOOST,
    FVG_LOOKBACK,
    FVG_PROXIMITY_PCT,
    FVGIndicator,
)
```

**Boost Fold.** The intent is a pair: sell a slice of holdings when the mean
reversion reading goes extreme, then buy that slice back when price returns to
its moving average, and let the difference raise the target. The Market
Inspector states the pair at the head of its own module.

`src/trading/mr_inspector.py` — the pair, in the module's own words

```
# │ When all 3 gates pass → Boost Sell (sell 2.5% of holdings) │
# │ When price returns to SMA → Boost Fold (buy back cheaper)  │
# │ Profit from boost fold increments target (compound growth)  │
```

Where it runs is the stock accumulation bot, which carries the queued amount,
the reference price, the moving average and the two counters, and works all of
them. The crypto Scrumming Bot declares the same four fields, sets them to zero
and never reads them again: across the whole trading package the only lines
naming them are those four assignments. A crypto bot therefore takes no boost
fold, whatever the Market Inspector reads.

`src/trading/scrumming_bot.py` — the four fields, written once and never read

```python
        self._boost_fold_q: float = 0.0
        self._boost_fold_ref: float = 0.0
        self._boost_fold_sma: float = 0.0

        self._boost_folds: int = 0
```

*Proposed, not present, in `src/trading/scrumming_bot.py`:* the crypto side
needs the read half of the pair, taking the queued amount back at the moving
average the way the stock bot does, guarded so a bot with an empty queue takes
no action.

```python
if self._boost_fold_q > 0 and self._boost_fold_sma > 0:
    if price <= self._boost_fold_sma and price < self._boost_fold_ref:
        buy_usd = self._boost_fold_q
        self._boost_folds += 1
        self._boost_fold_q = 0
```

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

**Design intention.** The handler already knows which wing you are in and
passes that to the dialog, so it has somewhere to say which tab to open.

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

**The exchange row in the Electron shell.** The shell draws one tab button per
configured exchange, and the screen under the button is drawn by
`exchange_tab.js`. A layer shows its empty card only while it holds no
exchange, which is what the Qt tab row does once it drops the Get Started tab.

`src/gui/main_tabs/trading_tab_surface.py` — `layer_exchanges`

```python
for entry in entries or []:
    holder = entry if isinstance(entry, dict) else {}
    exchange_id = str(holder.get("exchange_id") or "")
    if not exchange_id:
        continue
    layer = "stock" if is_equity_exchange(exchange_id) else "crypto"
    split[layer][exchange_id] = exchange_display_name(holder)
```

**One caption for one exchange.** The caption on a tab comes from a single
helper, so the start-up path and the settings path cannot label the same
exchange two different ways. An exchange saved with no name is captioned from
its own id, and an entry with no id gets no tab at all.

`src/gui/main_tabs/trading_tab_surface.py` — `exchange_display_name`

```python
def exchange_display_name(entry: Any) -> str:
    holder = entry if isinstance(entry, dict) else {}
    exchange_id = str(holder.get("exchange_id") or "")
    named = str(holder.get("display_name") or "")
    return named or exchange_id.capitalize()
```

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

**Where the maths lives.** [07-indicators.md](07-indicators.md) is the single
home for all twelve. Each voter is described once there and once only: the
operator's own line, then what the cell prints and what makes the vote bullish,
bearish or neutral, then the published formula with the code that computes it.
Nine voters print a direction arrow and a confidence percentage. Three print a
raw value instead, and those three are ADX, Z-Score and Kaufman ER.

| Voter | Its formula and its vote |
| ----- | ------------------------ |
| BB | [Bollinger Bands](07-indicators.md#bollinger-bands) |
| VTX | [Vortex Indicator](07-indicators.md#vortex-indicator) |
| MACD | [MACD](07-indicators.md#macd) |
| SRsi | [Stochastic RSI](07-indicators.md#stochastic-rsi) |
| Ichi | [Ichimoku Cloud](07-indicators.md#ichimoku-cloud) |
| Vol | [Volume](07-indicators.md#volume) |
| Sling | [Slingshot](07-indicators.md#slingshot) |
| ADX | [ADX and DMI](07-indicators.md#adx-and-dmi) — raw value |
| STrd | [Supertrend](07-indicators.md#supertrend) |
| ZSc | [Z-Score](07-indicators.md#z-score) — raw value |
| KER | [Kaufman Efficiency Ratio](07-indicators.md#kaufman-efficiency-ratio) — raw value |
| RSI | [RSI](07-indicators.md#rsi) |

One decision picks the text a cell carries. Three voters are named in it and
every other voter falls through to the percentage.

`src/gui/indicator_panel.py` — `_populate_indicator_cell`

```python
if ind_key == "adx":
    adx_v = details.get("adx", 0)
    if details.get("ranging"):
        cell_text = f"Rng {adx_v:.0f}"
    else:
        cell_text = f"{sym} {adx_v:.0f}"
elif ind_key == "zscore":
    cell_text = f"{sym} {details.get('z', 0):+.1f}"
elif ind_key == "kaufman_er":
    cell_text = f"{sym} {details.get('er', 0):.2f}"
else:
    cell_text = f"{sym} {confidence:.0%}"
```

The same file carries the gate logic chain that turns those twelve votes into a
trade decision.

### The Indicator Voting Panel, restyled

The panel beside the exchange stack carries seven columns on each row, aligned
under each other: TF and six indicators above, TF and six more below. The three
collated columns — Net, Comp and Conf — close the first row and stand as one
pillar each behind both rows.

`src/gui/indicator_panel.py` — the two rows share one grid

```python
col_names = ["TF"] + [short for _, short, _ in indicator_subset]
col_names += [""] * (_PANEL_COLUMN_COUNT - len(col_names))
```

The TF Lock row is gone, and so are the pair symbol and the vote tally that
stood in the upper right. The bot selector and its privacy dot moved there.
[07-indicators.md](07-indicators.md) carries the panel's own entry.

![The Trading tab in the Electron shell](../audits/2026-09-07_units/trading_tab_electron.png)

## 2026-09-11 16:48 - #665 - the wizard's values reach a new bot

Bot creation held two dict literals. Each named the settings it would pass to a
new bot, and the wizard collected more settings than either named. A name absent
from both lists was collected, held in memory and never read, so the bot took the
declared default for that field instead. Twenty-five Scrumming settings and six
Extractor settings went that way.

One function now selects the kwargs, and it reads the declaration rather than a
list of names. `bot_config_kwargs` keeps every key that names a field `BotConfig`
declares, and drops the keys that belong to the other mode — which is the same
rule `make_bot_config` applies when it refuses one. A field added to `BotConfig`
and emitted by the wizard arrives with no second edit.

`src/trading/container/config.py` — `bot_config_kwargs`, the selection

```python
foreign = (
    _BOT_CONFIG_SCRUMMING_ONLY_FIELDS
    if mode == BotMode.EXTRACTOR
    else _BOT_CONFIG_EXTRACTOR_ONLY_FIELDS
)
# make_bot_config sets mode itself and raises on a foreign field.
carried = {f.name for f in fields(BotConfig)} - foreign - {"mode"}
```

### What the entries above now read

Five entries on this page state that bot creation does not pass a setting. Each
sentence described the creation path as it stood, and the creation path has
moved. The corrected reading for each:

| entry | the sentence above | what it now does |
|---|---|---|
| Wire Inflow Stack | "Bot creation does not pass this setting, so a new bot takes the declared default of 1.00 whatever you type here." | Bot creation passes `wire_inflow_stack_pct`. A new bot takes the figure on the row. |
| Profit Routing | "Issue #336 carries this, with the rest of the settings the wizard writes and bot creation drops." | Bot creation passes `profit_route` and `profit_route_bot_id`. No module under `src/trading/` reads either one, so the destination a bot holds still reaches no trade. |
| Standing alt units (inverted) | "Bot creation passes neither this number nor the Direction beside it, so a new Extractor runs Normal with a standing position of zero whatever you enter." | Bot creation passes `inverted_extractor_standing_alt_units` and `extractor_direction`. `set_initial_chunk_rate` still has no caller in the product source. |
| Correction skip candles | "Bot creation does not pass it, so a new bot takes the declared default of 4." | Bot creation passes `extractor_correction_skip_candles`. The reader still counts ticks rather than candles. |
| Drawdown threshold | "bot creation does not pass it, so a new bot takes the declared default of 3.00" | Bot creation passes `extractor_drawdown_threshold_pct`. |

Five entries already read "bot creation passes it through": Read Rate, Band
Travel, Pool Reserve, Exit % and Max cost-basis multiple. Those sentences stand
unchanged.

### What the run measured

One run drove the real wizard on both modes. It moved every control on every
page the wizard reaches, collected the config, built a real bot through the
creation path, and read each value back off that bot's own config.

```
scrumming   wizard emits 52 keys
            before   26 passed, 24 settings held the default against a typed value
            after    48 passed, 0 held a default against a typed value
extractor   wizard emits 23 keys
            before   20 passed, 6 settings held the default against a typed value
            after    22 passed, 0 of those 6 held a default
```

The Extractor's 22 names hold two the wizard does not emit: Target Balance and
Stack Mode, each supplied at creation as it was before. One Extractor key still
holds a default and it is the Profit Folding flag, which the table below covers.

The same run drove a save and a restore of a bot built from typed values. All 72
fields came back holding what was saved, so a restart puts back what it put back
before.

A wizard left untouched still builds a bot at the declared defaults. Every
Scrumming field matches its declaration. Two Extractor fields do not, and both
are deliberate: the Extractor's parameter page offers no Target Balance row, so
its pool figure stands in; and the page offers no Stack Mode box, so an absent
key reads as off rather than as `STACK_MODE_DEFAULT`.

### Three settings the wizard still collects and a new bot still cannot read

| setting | why |
|---|---|
| Lock duration (candles) | `lock_candle_count` is no field on `BotConfig` and no argument of `ScrummingBot.__init__`. The phantom coordinator holds an attribute of that name, and Bot Settings writes it there on a running bot. |
| Profit Folding, on an Extractor | `BotCreationWizard.get_bot_config` writes `profit_folding_active: False` for an Extractor. The field is Scrumming-only, so `make_bot_config` refuses it on an Extractor config. No control types it. |
| Max adoptable USD | `max_adoptable_usd` is the one `BotConfig` field no page offers and the restore path does not read either. Nothing writes it and nothing types it. |

`enable_phantoms` and `phantom_timeframes` are not on that list. Both already
reach the bot, as arguments to `ScrummingBot.__init__` rather than through the
bot config.

## 2026-09-12 - the second half of the Scrumming Settings group, driven

Six rows of that group were driven on a bot built from a record written for the
run. The home was redirected into a scratch directory before the settings module
was imported, so the settings directory and the log root both bound under it. No
stored file of the running install was opened, no venue was contacted, and the
exchange object handed to the bot defines no order method at all, so the run
could not place an order even where a path reached for one.

```
Max Entry Price        the price an auto-buy is refused above
Min Entry Price        the price an auto-buy is refused below
Trading Fee %          the figure added to the opposing-trade distance
Max Target Growth %    the ceiling one fold cycle may add to Target Balance
Scrum Fold Ratio       the share of a sale's tranches kept for the fold
Profit Folding Active  whether a fold may raise Target Balance at all
```

### What each row did when it was driven

Every reading below is one call into the shipped engine, with the figure on the
row as the only thing changed between the two sides.

```
Max Entry Price    ceiling $90 against a price of $100   buy refused at the gate
                   ceiling $110 against the same price   gate silent
Min Entry Price    floor $110 against a price of $100    buy refused at the gate
                   the same floor, the same price, sell  no refusal of any kind
Trading Fee %      fee 0.60 %, pivot $100, buy at $98.70 refused, needs 1.60 %
                   fee 0.00 %, pivot $100, buy at $98.70 not refused
                   fee 0.60 %, pivot $100, sell at $101.30 refused, needs 1.60 %
                   fee 0.00 %, pivot $100, sell at $101.30 not refused
Max Target Growth  1.00 % on a $200 target   cap $2.00, target became $202.00
                   0.00 % on a $200 target   cap $0.00, target stayed $200.00
                   5.00 % on a $200 target   cap $10.00, target became $210.00
Scrum Fold Ratio   100 % on two $100 tranches  queued $200.00, 2.0000 units
                   40 %  on the same two       queued $80.00, 0.8000 units
                   1 %   on the same two       queued $2.00, 0.0200 units
Profit Folding     on   applied $2.00, target $202.00, preview $2.00
                   off  applied $0.00, target $200.00, preview $0.00
```

The Profit Folding row emits its own line when it is off, and that line is the
one a reader should look for rather than the absence of a growth.

`src/trading/scrumming_bot.py` — the line the off state emits

```python
f"[COMPOUND SKIPPED] ({source}): "
f"profit_folding_active=False — the "
f"compound-growth feature is off for "
f"this bot. No target bump."
```

### A zero in either entry-price box is not the same thing in both

Both entries above say zero means no ceiling and no floor, and both controls
honour that: a box left at zero emits nothing rather than a number, measured on
the wizard the Electron shell draws. The engine's own guard is narrower than the
sentence. It treats only the absent value as off, so a record carrying a literal
zero in the ceiling refuses **every** auto-buy for as long as it stands — driven,
a ceiling of zero against a price of one hundred refused the buy at the gate. The
same zero in the floor is harmless, because no price is below it.

`src/trading/scrumming/execution.py` — the two guards, as they stand

```python
if _max_ep is not None and _px > 0 and _px > float(_max_ep):
if _min_ep is not None and _px > 0 and _px < float(_min_ep):
```

No control can write that zero. The three places that collect the value each
write an absent value in its place, so a record carrying a literal zero came from
an older build or from an edit outside the application.

```
src/gui/bot_wizard.py:1540                    absent unless the box reads above 0
src/gui/live_settings/settings_tab.py:517     absent unless the box reads above 0
src/gui/main_tabs/bot_wizard_surface.py:2267  absent unless the box reads above 0
```

*Proposed, not present, in both guards:*

```python
if _max_ep and float(_max_ep) > 0 and _px > 0 and _px > float(_max_ep):
```

It is proposed rather than taken because a bot standing on such a record is
refusing every buy today, and a build that reads the zero as off would have it
buying on its next tick. That is his decision, not this unit's.

### The floor on the Scrum, measured on both sides

The entry above records that the buy path is the only reader. Driven, that is
exactly what happens, and the reading is worth stating as a pair because the
pair is what proves the instrument was working.

```
floor $110, price $100, buy   BUY REFUSED (min_entry_price gate)
floor $110, price $100, sell  no refusal emitted, the sale went on
```

The count agrees with the drive. `_execute_sell` runs from line 1333 to line
1669 of that module and the floor's name appears **nowhere** in it, against three
appearances inside the buy executor above. The number his own sentence ties to a
Scrum therefore reaches no sell, and a bot sitting at the floor holding the asset
sells as if the figure were not set.

Read against the standing test, the behaviour the code does have is the part no
sentence on this page asks for: nothing here specifies a floor under a buy. The
sell-side proposal already on this page stands, and the removal of the buy-side
floor is the other half of the same decision. Both move money on the next tick of
any bot carrying the figure, so both are reported here and neither is taken.

### A fee of zero is read two ways at once

The entry above says the fee is added to the Minimum Opposing Trade Distance, and
it is. At every figure the box offers except one, every reader agrees. At a stored
zero they split: ten reads inside the trading package treat a zero as six tenths
of a percent, and two inside the same executor honour the zero.

```
stored 0.60 %   distance filter 1.60 %   buy and sell hysteresis 1.60 %
stored 2.50 %   distance filter 3.50 %   buy and sell hysteresis 3.50 %
stored 0.00 %   distance filter 1.60 %   buy and sell hysteresis 1.00 %
```

The box accepts a zero, and so does the wizard the shell draws — typed at zero it
emitted a zero. The two controls then show six tenths when that record is
reopened, because each seeds itself the same way the ten reads do.

`src/trading/otd_math.py` — the read, and its own note on the quirk

```python
return minimum_opposing_trade_distance_pct(
    getattr(config, "scrumming_interval_pct", 0) or 0,
    getattr(config, "trading_fee_pct", 0.6) or 0.6,
)
```

That module's docstring already names the quirk and says it is named there and
not repaired there, so the split is known rather than newly found. Closing it
changes the distance a reversal must travel for any bot whose fee is zero, which
is a live figure on a live tick, so it is reported here and not taken.

### What the Max Target Growth entry above now reads

That entry records ten read sites, seven falling back to one and three to zero,
and a bot that compounds or freezes depending on which read first. The first half
holds and the second does not.

| the entry's reading | what the run measured |
| --- | --- |
| three sites fall back to zero against a declared default of one | Held before this change. The three were the manual rebalance, the compounding snapshot and the Smart Wire inputs, exactly as named |
| a bot compounds or freezes depending on which site read first | Does not hold. No bot can reach the fallback: every construction path builds the config through one factory, and the class declares the field, so the value is never absent |
| ten read sites take it with a fallback | Nine now. One of the ten was an expression whose value was discarded, and it is gone |

The three sites now name the declared default. Driven against a stand-in that
genuinely lacks the field, the two reachable ones moved from zero to one and then
agreed with the cycle cap; every other reading in the run was identical before
and after, which is what makes the change inert on a real bot.

```
before   swos 0.0   snapshot 0.0   cycle cap $2.00
after    swos 1.0   snapshot 1.0   cycle cap $2.00
```

`src/trading/scrumming_bot.py` — the shape all nine now share

```python
_growth = float(getattr(self.config, "max_target_growth_pct", 1.0) or 0.0)
```

### Where the Scrum Fold Ratio is read

The entry above gives the row its range and its start value and says nothing
about where the engine reads it. One method does, once per sale, and it runs on
the slice of tranches that sale appended rather than on the whole queue.

`src/trading/scrumming/fold_tranches.py` — the read and the clamp

```python
_fold_pct = max(0, min(100, int(getattr(self.config, "scrum_fold_pct", 100))))
_new_tranches = self._fold_tranches[_tranche_count_before:]
if _fold_pct < 100 and _new_tranches:
```

At a hundred the branch does not run and the sale's tranches keep every dollar.
Below a hundred each tranche keeps the ratio's share of units and of the sale's
own proceeds, and the remainder is retired as cash with a realised profit line.
Money in a tranche that did not come from this sale is wired-in credit and keeps
its full value.

The clamp's lower bound is zero and both controls start at one. A record carrying
a zero therefore empties the sale's whole fold queue — driven, one hundred
dollars and one unit became zero dollars and zero units, with the cash retired
instead. Raising the clamp to match the controls would change what such a bot
rebuys on its next sale, so it is reported here and not taken.

### The Profit Folding Active row on a running bot

No entry above describes this row, because the group on the creation wizard does
not carry it. The running bot's own Scrumming Settings group does, and so does
the row list the shell draws from.

| | the control |
| --- | --- |
| Where | `src/gui/live_settings/settings_tab.py:575` |
| React row | `src/gui/main_tabs/live_settings_tab_surface.py:769` |
| Kind | checkbox, on at the start |
| What it writes | the bot config key the engine reads four times |

Profit Folding Active - When it is on, a fold's surplus may raise Target Balance
up to the Max Target Growth % cap above. When it is off, the surplus is not
applied, the preview of a prospective fold reads zero, and the bot writes a
skipped line naming the flag. A bot restored from its own record takes its own
flag and reads no application setting.

```
on   surplus $10.00 applied $2.00   target $200.00 became $202.00   preview $2.00
off  surplus $10.00 applied $0.00   target stayed $200.00           preview $0.00
```

The creation wizard holds a checkbox for the same flag on a page no route
reaches, so a new bot opens on the declared default until that page is reachable.

## 2026-09-12 - the Hedge Rebalance group and the despawn timer, driven

Three rows were driven on a bot built from a record written for the run. The home
was redirected into a scratch directory before the settings module was imported,
so the settings directory and the log root both bound under it. No stored file of
the running install was opened, no venue was contacted, and the exchange object
handed to the bot defines no order method at all, so the run could not place an
order even where a path reached for one.

```
Hedge Rebalance Active  whether the bot holds a reserve outside Target Balance
Hedge Balance           the size of that reserve, and the ceiling it refills to
Tranche Despawn Timer   the age at which a tranche record is removed
```

### What the hedge switch decides

The switch reaches four places in the engine and every one of them moves a
decision. Two are the seeds that set the reserve at construction, one is the gate
that arms a hedge buy on a tick, and one is the gate that refills the reserve out
of a completed fold's profit.

`src/trading/scrumming_bot.py` — the two seeds

```python
self._hedge_bal: float = (
    float(config.hedge_balance) if config.hedge_rebalance_active else 0.0
)
self._hedge_balance_initial: float = (
    float(config.hedge_balance) if config.hedge_rebalance_active else 0.0
)
```

Driven both ways at three figures, the seeds read what the two sentences above
this section promise.

```
active=True   balance $200.00   reserve $200.00   cap $200.00
active=True   balance  $50.00   reserve  $50.00   cap  $50.00
active=True   balance   $0.00   reserve   $0.00   cap   $0.00
active=False  balance $200.00   reserve   $0.00   cap   $0.00
active=False  balance  $50.00   reserve   $0.00   cap   $0.00
active=False  balance   $0.00   reserve   $0.00   cap   $0.00
```

The budget layer that refuses an oversized buy reads the same reserve, so the
switch decides the ceiling as well as the gate. With half a unit held at one
hundred dollars, the hedge path's ceiling is the position plus the reserve.

```
active=True   balance $200.00   a $25 buy allowed, a $210 buy refused at $251.00
active=True   balance  $50.00   a $25 buy allowed, a  $75 buy refused at $100.25
active=False  balance $200.00   every buy refused at $50.00, the position alone
```

The control for the figure on the scrum path is the same call with a different
path name. At a reserve of zero it still allows a seventy-five dollar buy, which
is what proves the refusals above came from the hedge reserve and not from the
position.

### The reserve a restart re-seeds and a toggle does not

Turning the switch on while the bot runs arms nothing. The two reserve fields are
read once, at construction, and nothing on the live path writes them again, so a
bot built with the switch off keeps a reserve of zero and a ceiling of zero for
as long as it stands.

```
built with the switch off   reserve $0.00   cap $0.00
config flipped to on        reserve $0.00   cap $0.00
a $25 hedge buy then reads  refused
```

A restart is the one route back, and it is a partial one. The ceiling is rebuilt
from the stored config, because it is not itself persisted, while the drainable
reserve is restored from the saved record.

```
rebuilt with the switch on        reserve $200.00   cap $200.00
then restored from the off record reserve   $0.00   cap $200.00
the fold replenish terms then     open
```

The reserve then refills from compound growth at eight hundredths of each fold's
profit, and only after a restart. Making the toggle re-seed the reserve would
hand a drained bot its full reserve back the moment the operator flicked the box
twice, which is money on a live tick and his decision rather than this unit's.

*Proposed, not present, in the live-settings route:*

```python
RUNTIME_ROUTED = {
    "hedge_rebalance_active": "set_hedge_active_live",
}
```

### What the Hedge Balance figure bounds

The figure is the reserve's starting size and the ceiling a refill stops at. Six
of its ten engine readers decide something: the two seeds, the arm test, the size
of the buy, and the two budget layers that refuse an oversized one.

`src/trading/scrumming_bot.py` — the figure that sizes one hedge buy

```python
_use = min(self._hedge_bal * 0.5, _gap)
```

The running bot's own row is routed through a method rather than written straight
onto the config, and that method refuses a figure it cannot use.

```
set $500.00  applied   cap $500.00  reserve $120.00 unchanged
set   $0.00  applied   cap   $0.00  reserve $120.00 unchanged
set  -$5.00  refused   hedge_balance must be >= 0
set   "abc"  refused   hedge_balance must be numeric
set  $75.00  applied   cap  $75.00  reserve $120.00 unchanged
```

A cap of zero is accepted, and it shuts the refill gate for good while leaving
the old reserve drainable. The bot can still spend what it holds and can never
get any of it back. Raising the cap back above zero re-opens the gate, so the
state is recoverable by the same control that caused it, and the refusal that
would make a zero mean off instead of empty would change what a bot carrying one
does on its next fold. Reported here and not taken.

### The despawn timer has no creation-wizard control

The timer is the one row of these three that a new bot cannot be given. Searching
both wizard builds for the word returns nothing, so a new bot opens at the
declared default of zero, which is off.

```
src/gui/bot_wizard.py                      0 matches
src/gui/main_tabs/bot_wizard_surface.py     0 matches
src/gui/live_settings/settings_tab.py      the one control, 0 to 365 days
src/gui/main_tabs/live_settings_tab_surface.py   the React row for it
```

The label on both screens reads Tranche Despawn Timer. The engine reads the
stored figure exactly once, through one shared helper, and the sweep that uses it
runs once per tick outside every exception handler.

`src/trading/container/config.py` — the one reading

```python
def despawn_threshold_days(config) -> int:
    days = as_finite_float(getattr(config, "tranche_despawn_days", 0))
    if days is None:
        return 0
    return min(DESPAWN_MAX_DAYS, max(0, int(days)))
```

Driven across thirteen stored values, every shape the control cannot type reads
as off rather than as a number.

```
0 -> 0      1 -> 1      7 -> 7      365 -> 365      30.9 -> 30
-5 -> 0     True -> 0   "7" -> 0    None -> 0       nan -> 0    inf -> 0
the field absent altogether -> 0
```

### The five claims the despawn tooltip makes

The tooltip on that control is the only specification the row has, and it makes
five checkable claims. Each one was driven on a bot holding seven fold records
and five stack records.

| The claim | What the run measured |
| --- | --- |
| Despawn is not a trade | Zero calls reached the exchange object across every sweep, at every threshold |
| No order is placed or cancelled | The exchange object defines none of the five order methods, and the sweep calls none of them |
| Holdings and cost basis are untouched | Holdings 0.5 before and after; both cost-basis lots identical, 0.3 at $91.00 and 0.2 at $103.00 |
| A tranche with no timestamp is never despawned | At a one-day threshold the ageless record survived alone, counted as kept |
| A stack tranche holding a resting order is kept until it settles | Pending with an order id was kept at four hundred days; the same record removed once filled, and once cancelled |

The target balance and the anchor are unchanged too, which the line the operator
reads already claims.

```
_current_holdings          0.5   ->  0.5
_target_balance          200.0   ->  200.0
_anchor_target_balance   200.0   ->  200.0
_hedge_bal               200.0   ->  200.0
exchange calls               0   ->  0
```

The threshold is inclusive, as the tooltip says. A record at exactly seven days
goes at a seven-day threshold and a record one second younger stays.

```
exactly 7 days     removed 1, 0 rows left
one second under   removed 0, 1 row left
```

### Three declarations of one despawn predicate agree

The predicate is written three times: once in the sweep that removes, once in the
shared preview the Qt panel reads, and once again inside the React surface. Driven
on one tape of records across thirteen thresholds, all three answer the same
counts on every row.

```
days    sweep   shared preview   React preview
   0     0/0             0/0            0/0
   1     2/2             2/2            2/2
   7     2/2             2/2            2/2
  30     1/2             1/2            1/2
 365     0/0             0/0            0/0
30.9     1/2             1/2            1/2
```

The dollars agree as well, and the queue total recomputes to match what is left
rather than being decremented.

```
 7 days   queue $138.00 -> $68.00   the sweep reports $70.00 removed
30 days   queue $138.00 -> $98.00   the sweep reports $40.00 removed
```

A third copy of a predicate is a drift hazard rather than a present fault, and
collapsing it would reach files other rows own.

### The word a removal now uses

Merge, despawn and clear are the only three things that collapse or remove a
tranche, and despawn removes rather than delists. The sweep's own report and the
line the operator read said delisted in five places, against a preview beside it
that already said removed. The words now agree and the counts did not move.

```
before   TRANCHES DESPAWNED (>= 7d): delisted 2 fold tranche(s) holding $70.0000
after    TRANCHES DESPAWNED (>= 7d): removed 2 fold tranche(s) holding $70.0000
```

The sweep's key set is now a subset of the preview's, so either report can be
read by one consumer. [08-tabs/bot-swarm.md](08-tabs/bot-swarm.md) carries the
block.

```
sweep     ageless_kept  fold_removed  stack_kept_live_order  stack_removed
          threshold_days  usd_removed
preview   the same six, plus fold_open, stack_open and units_removed
```
