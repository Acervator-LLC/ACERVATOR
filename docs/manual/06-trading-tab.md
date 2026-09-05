# System Architecture and Features Catalogue

Acervator features a semi-modular / layered design that nests a hyper-vigilant trading engine capable of operating in multiple investment domains simultaneously and all from one terminal. The Main Window contains all of the various subsections found in each subsystem tab. As it stands the existing and planned subsystem tabs are: Simulator, Paper Trading, Trading (Live), Market Inspector, Bot Swarm, Asset Charts, History, Console, Proof of Accumulation (PoA), and System Status. Most of these subsystems interact with each other to some degree with key isolations existing between the three trading tabs and their wiring to Market Inspector, Bot Swarm, and History.

## Trading Tab

Here you see the first subsystem we are going to cover and this will primarily be due to familiarizing the prospective investor or user with the core trading philosophy and strategies that drive Acervator. To begin, the platform runs locally on whichever hardware is selected. A single authorization phase requiring a purchased license key will be the only non-exchange communication the application will ever need. The user’s keys and secrets are stored locally and encrypted after API handshake verification passes which allows the chosen exchange to be initialized. At a later development stage, I have plans for dedicated hardware that uses a hardware key for quick boot into a given user’s account and also allows the platform to run in isolation under Linux.

![The Trading tab, with Privacy Mode on.](p15-i0.png)

`TradingTabMixin._build_trading_tab` in `src/gui/main_tabs/trading_tab.py`
builds this screen. `HeaderStripMixin._build_header_strip` in
`src/gui/main_tabs/header_strip.py` builds the strip above it, which stays on
every tab. Privacy Mode is on in the figure, so each masked field draws four
asterisks in place of its value.

The header strip carries five columns and five counter cards:

- SPENDABLE, REALISED, LOCKED, MATURE and EXCH are the columns of
  `SpendableProfitsWidget` in `src/gui/widgets/spendable_profits.py`.
  `_refresh_dashboard` in `src/gui/main_window.py` fills them from one
  `get_aggregate_stats` call. SPENDABLE takes `wallet_cash_usd`, LOCKED takes
  `crypto_position_value_usd`, and EXCH counts the open exchange sub-tabs.
- REALISED and MATURE take `None` at both call sites, so `_money_text` draws an
  em dash for each. Privacy Mode masks that em dash to asterisks, which reads on
  screen as a hidden number.
- Scrummed, Folded, Trades, Bots and Errors are five `StatCard` widgets from
  `src/gui/widgets/dashboard_stat_card.py`. Scrummed and Folded add
  `total_scrummed_usd` and `total_folded_usd` across the fleet. Bots counts the
  bots in the running state and Errors adds `total_errors`. A click on Errors
  opens the rolling error log.
- Crypto Mode is `_mode_btn`. It switches `_trading_stack` between the crypto
  page and the stock page.
- The circle under each column and each card is a `PrivacyDot`. It masks that
  one field.

[08-tabs/portfolio-panels.md](08-tabs/portfolio-panels.md) covers the strip in
full.

The tab row takes its order from `CANONICAL_TAB_ORDER` in
`src/gui/main_window.py`: Trading, Market Inspector, Bot Swarm, Asset Charts,
History, Simulator, Console.

One sub-tab holds one exchange. `ExchangeTab` in
`src/gui/widgets/exchange_tab.py` builds it:

- Privacy Mode toggles every registered mask at once.
- The headline beside it comes from `CryptoNewsTicker`.
- `+ New Bot` opens the bot wizard for this exchange.
- The data pool line comes from `_update_pull_rate_label`, which reads
  `pull_rate_summary` on `MarketDataPool`. It names the slot count by kind, the
  freshest and oldest slot age, the count of slots past their time to live, and
  the coalesced cache-hit ratio.
- `+ Add Crypto Exchange` is the corner widget of the layer's tab bar.

The Scrumming Bots table is `BotStatusTable` in
`src/gui/widgets/bot_status_table.py`. `SCRUMMING_COLUMNS` names ten columns:
Bot ID, Symbol, Mode, Trades, Target, Target BTC, Target ETH, Ammo, Fire, and a
tenth column whose label is empty and which carries the Detail button. Mode
carries the state colour: green for running, amber for paused, grey for idle or
stopped, red for error, orange for cooldown, cyan for starting. Ammo is the
distance of the position value from Target, drawn green above the target, red
below it, and neutral grey inside the dust band. Target BTC and Target ETH
restate the Target in those two assets and stay blank when the pair is unlisted
or the target is that asset. A second table, `ExtractorBotTable`, sits under it.
Each table stays hidden until its own bot list holds a row.

Start, Pause, Stop, Restart and Delete act on the selected row of whichever
table the operator clicked last; `_cmd` reads `_last_clicked_table` to choose.

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

`ModeSelectionPage` in `src/gui/bot_wizard.py` is the wizard's start page.
`BotCreationWizard.setStartId` names it. It offers two radio buttons and one
description under each:

- Accumulation Trading (Scrumming) is checked at build time. Its description
  names 12-indicator TA voting, which matches the twelve voters
  `VotingEngine._create_indicators` builds in `src/trading/ta_engine.py`.
- Base Currency Extractor (Multi-Target) routes the wizard to the Extractor Pool
  page instead of the asset page. `nextId` makes that choice.

`is_extractor` is the method the rest of the wizard reads. A third mode, Grid,
is retired: `is_grid` returns False without reading a widget.

When the +New Bot button is pressed, the above window appears. Currently there are two “trading mode”

options (this will be change to Strategies). We are only interested in the Scrumming Bot at this point.

![The wizard's asset page: exchange, base currency and target asset.](p17-i0.png)

`AssetSelectionPage` in `src/gui/bot_wizard.py` draws four rows:

- Exchange lists the connected exchanges. Changing it re-scans that venue
  through `_fetch_markets`, which keeps spot markets that the venue marks
  active.
- Base Currency is a fixed list of seven: USDT, USDC, BTC, ETH, BNB, EUR and
  USD.
- Target Asset lists every asset that trades against the chosen base. Each entry
  carries a cached coin icon and, where the venue supplied one, a 24-hour volume
  figure. `_filter_assets` sorts the list by that volume.
- The round information button opens a description of the selected asset, taken
  from `ASSETS` in `src/exchange/crypto_assets.py`.

The line under the rows counts the pairs found and adds a note about volume
order when at least one pair carried a volume.

After Scrumming / Accumulation is selected, next we are presented with Exchange, Base Currency, and Target Asset options.

Exchange - A privately and federally licensed financial platform that allows API interfacing for remote or automated trade execution.

Base Currency - This will be a National Currency, Stable Coin, or High Volume Crypto (BTC, ETH, BNB) for which multiple trading pairs are available on the selected exchange.

Target Asset - This is the asset in which the scrumming bot bases its position. If $50 and ZEC are selected, it will strive to maintain and compound against a balance of $50 in ZEC until it is shut down or some other adverse market condition occurs.

### Trading Parameters

Next we come to the combined Scrumming Bot configuration page which has several sections for fine tuning how the specific instance behaves. Given that Acervator, at the time of this writing, is still in active development the description for each setting should be seen as a design intention should any issues be encountered.

![The Trading Parameters group of the wizard's parameter page.](p18-i0.png)

`TradingParamsPage` in `src/gui/bot_wizard.py` holds eight scrumming groups
and one Extractor group in a scroll area. `set_mode` shows one side or the
other, never both. The first group holds:

- Order Visibility: Order Book (Visible) or Internal (Invisible).
- Aggressive Trading (force IOC-limit takers), a checkbox, off at build time.
- Stack Mode (split SCRUM across upward tranches). Its start state comes from
  `STACK_MODE_DEFAULT` in `src/trading/bot_container.py`, so the box and the
  config cannot disagree.
- Split Distance, a percentage from 0.10 to 20.00, at 1.00 %.
- Tranche Count, a whole number from 2 to 20, at 3.
- Spacing: Linear, Quadratic or Exponential. The sequence beside each name is
  the cumulative distance from the anchor in units of Split Distance.
- Personal Hold (units), target-asset units the bot holds out of its own
  decision maths and out of any sibling bot's view.

The manual names Tranche Spread in the list below. The page carries no such
control, and `get_config` on this page emits no key of that name.

Order Visibility - Trades are listed on the order books or tracked internally to the platform.

Aggressive Trading - Trades are priced so that they fill immediately. Trading like this is a bit like guerilla warfare. In and out before anyone notices.

Stack Mode - Stack Mode enables Stack Tranches which operate on the Sell or Scrum side. This forms the “upside” of the organic ladder structure whereas Fold Tranches form its “downside”.

Split Distance - This setting determines the spacing between tranches if Tranche Spread (not available yet) is being used.

Tranche Spread - This allows a given Scrum or Fold to divide its result X# of times across multiple incremented (as dictated by Split Distance) positions.

Tranche Count - This can also be referred to as Spread Count. It determines how pieces a given Scrum or Fold is split into and distributed across incremented tranches as opposed to just one.

Spacing - This adds a scaling factor Split Distance and works in conjunction with Tranche Spread and Tranche Count to induce curves and more aggressive growth within the ladder structure.

Personal Hold - Setting to be removed.

![The Scrumming Settings group.](p19-i0.png)

The same page, scrolled down. Ten rows, each named here with the range the
widget accepts and the value it starts at:

- Opposing Trade Interval, 0.10 % to 20.00 %, at 1.00 %.
- BB Tolerance, 0.25 % to 5.00 %, at 1.00 %.
- Landing Strip Candles, 2 to 10, at 3.
- TA Timeframe. The combo starts with seven entries and 1h chosen.
  `set_exchange_id` replaces the list with the timeframes
  `available_timeframes` reports for the chosen venue, so a venue without 4h
  does not offer it.
- Target Balance, $1.00 to $1,000,000.00. Its start value comes from the
  `default_target_balance` the wizard was handed.
- Max Entry Price, eight decimal places, at $0.00000000, where zero means no
  ceiling.
- Min Entry Price, the same shape, where zero means no floor.
- Trading Fee %, 0.00 % to 5.00 %, at 0.60 %.
- Max Target Growth %, 0.00 % to 100.00 %, at 1.00 %.
- Scrum Fold Ratio, 1 % to 100 %, at 100 %.

Two of these read differently in the engine than the labels suggest.
`_execute_fold` in `src/trading/scrumming/execution.py` reads both entry-price
fields on the buy path only: it refuses a buy above `max_entry_price` and
refuses a buy below `min_entry_price`. Neither field reaches the sell path, so
the pair is a buy window rather than the entry-and-exit pair the manual names
below. Manual Fire skips both.

Read sites for `max_target_growth_pct` across `src/trading/` and `src/gui/` do
not agree on the value to use when the field is absent: some fall back to 0.0
and others to 1.0. A bot whose stored config lacks the key then compounds or
freezes depending on which site reads it.

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

Seven rows in the advanced group, then two in the hedge group:

- Detect Threshold, 10 % to 90 %, at 75 %. The distance from the Bollinger
  midline to the band, as a percentage, before the bot moves from search to
  track.
- Fire Threshold, 0.10 % to 10.00 %, at 0.50 %.
- BB Midline Gate, a checkbox, on at build time. When on, a scrum fires only
  above the midline and a fold only below it.
- Read Rate, 1 to 60 minutes, at 5 minutes. The search-mode read rate.
- Band Travel, 0 % to 100 %, at 70 %. Zero switches it off.
- BB Bullseye Check, a checkbox, on at build time.
- Wire Inflow Stack, 0.00 % to 100.00 %, at 1.00 %.
- Hedge Rebalance Active, a checkbox, on at build time.
- Hedge Balance, at $200.00, a reserve held apart from Target Balance.

The group title on screen carries an internal release identifier after the
words Advanced Scrumming.

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

Six rows:

- Soft CB Threshold, 0.0 % to 100.0 %, at 25.0 %. Zero switches it off.
- Hard CB Threshold, the same range, at 35.0 %. Zero switches it off.
- Soft CB Cooldown, 1 to 100 candles, at 3.
- Max Cartridge Size, 0.0 % to 200.0 %, at 10.0 %. The largest target
  delta, as a percentage of Target Balance, before the bot fires an aggressive
  rebalance.
- Smart Cartridge, one checkbox labelled Calibrate to BB range, off at build
  time.
- Smart Ceiling, 1.0 % to 100.0 %, at 30.0 %. It caps the cartridge threshold
  while Smart Cartridge is on.

The group title on screen carries an internal release identifier after the words
Circuit Breakers.

Now we arrive at some safety controls. Circuit Breakers are designed to fully inhibit trade actions for a given period should an extreme volatility (pump and dump) event occur. Soft Circuit Breakers have a candle-count based timer whereas Hard Circuit Breakers require the user to clear the bot to continue trading.

Soft CB Threshold - The amount of instantaneous, single-candle price action required for the bot to pause trading for a number of candles denoted by Soft CB Cooldown.

Hard CB Threshold - The amount of instantaneous, single-candle price action required for the bot to be hard stopped at which point the user must re-authorize trading.

Soft CB Cooldown - This is the number of candles that must close before the Soft Circuit Breaker opens again.

Max Cartridge Size - This is the maximum amount of deviation allowed for the Target Delta. At this threshold the bot is actively and aggressively looking for a trade opportunity.

Smart Cartridge - This allows the Max Cartridge Size to organically resize in response to current price range as defined by the current-candle Bollinger Band reading.

Smart Ceiling - To be re-evaluated.

![The Risk Controls and Strategy Gate Flags groups.](p22-i0.png)

Five rows of risk control, then five gate checkboxes:

- Enable Position Ceiling, off at build time.
- Ceiling Multiple, 1.0 to 10.0, at 5.0x anchor. The anchor is the target
  balance the bot was created with.
- Enable Detonation (auto-harvest on bullish TF), off at build time.
- Detonation TF: 1d or 1w.
- Min Confidence, 0.50 to 1.00, at 0.75.
- SCRUM requires bullish TA, SCRUM holds in sustained uptrend, SCRUM defers to
  higher-TF bullish, FOLD requires bearish TA, and FOLD defers to higher-TF
  bearish. All five start checked.

`ScrummingBot._check_detonation_trigger` in `src/trading/scrumming_bot.py`
matches the checkbox label: the trigger needs a BULLISH consensus at or above
`detonation_confidence_min`, a current value above the anchor, and a transition
into that bullish state. A bearish reading fires nothing.

`BotConfig` in `src/trading/container/config.py` declares six gate flags. The
box shows five. The sixth, `fold_hold_in_downtrend`, has no checkbox, and
`get_config` writes it as a literal True. Outside the config declaration and
the restore path, no module reads it, while its mirror `scrum_hold_in_uptrend`
is read in `src/trading/scrumming_bot.py`. The field is declared and unimplemented.

The two group titles on screen carry internal identifiers after their names.

After Circuit Breakers, which help defend against extreme volatility, we come to Risk Controls. These are designed to cap the amount of profit or growth a given bot can earn before performing a full position exit.

Enable Position Ceiling - Enables a growth cap for a given position.

Ceiling Multiple - This setting caps the maximum amount of growth a position at a multiple of the Target Balance (anchor) and, once reached (and under higher timeframe bullish conditions with Detonation enabled) will allow the entire position to be sold and the corresponding bot will pause all further operations. Without Detonation enabled, this becomes a user notification.

Enable Detonation - Enables an entire remaining position to be sold after the Ceiling Multiple growth threshold is crossed.

Detonation TF - Selects the timeframe for the chart that is being evaluated for bullish conditions that will allow the detonation to occur.

Min Confidence - This is the minimum technical analysis confidence index (via the Indicator Voting Panel) that will allow the detonation to occur.

Next we use the Strategy Gate Flags which allows top-level trade restrictions to be enabled or disabled thus relaxing or restricting the conditions under which a trade action can occur. The settings, in this case, are self-descriptive.

![The Profit Routing group.](p22-i1.png)

Two rows:

- Route offers four destinations: fold back to target balance, send to
  spendable, split fold and spendable by percentage, and route to another bot.
- Target bot ID, a free-text field. The placeholder tells the operator to leave
  it blank unless the route is the cross-bot one.

The group title on screen carries an internal release identifier after the words
Profit Routing.

Moving onto the final section, we have Profit Routing which was intended to allow profits to be routed differently during initial set-up. This will be re-evaluated and potentially removed.

Route - Destination for profits.

Target bot ID - Field for manually a bot ID which was intended to create a Smart Wire under the Bot Swarm tab.

![The Phantom Balance Bots page.](p23-i0.png)

`PhantomConfigPage` in `src/gui/bot_wizard.py` is the last page on the scrumming
path:

- Enable Phantom Balance Bots, a checkbox, off at build time.
- Active Timeframes, eleven checkboxes: 1m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h,
  1d and 1w. All start clear. `set_exchange_id` greys out and clears any
  timeframe the chosen venue does not carry, and writes the reason into that
  box's tooltip.
- Candles to lock, 1 to 10, at 2, inside the Higher-TF Lock Duration group.

`get_config` returns only the boxes that are both checked and enabled.
`validatePage` asks the API load monitor whether the chosen phantom count would
pass the safety threshold for that venue, and offers Back to adjust or Continue
anyway.

Lastly we have the selection for the Phantom (Balance) Bots. These are intended to provide trade action overrides from higher timeframe charts and indicator sets which, in turn, may result in an improved trade or prevent a premature one.

### Extractor Bot (Partially Built; Untested)

The second type of bot offered within Acervator is the Extractor. These operate quite differently from Scrumming Bots and actually operate as Siblings of them. In fact, an Extractor Bot cannot even be called unless a corresponding Base Currency Scrumming Bot (i.e. BTC:USD or ETH:USD) is already active. This is due to the core operating principle of the Extractor bot to acquire more of these base currencies by performing trades against available alternate currency pairings. It does this by using and blocking off a portion of the Parent’s position within an Extractor Tranche that represents an active position taken against one of the available alternate pairs. The Extractor Tranche remains open until its opposing accumulating (or Short Position if preferred by the user) or profit taking trade is filled. Extractor Tranches can be of any size but should generally be a relatively small fraction of the Parent’s total position which will allow the Extractor to take multiple positions if available and allowed by the specific user.

![The Trading Mode page with the Extractor selected.](p24-i0.png)

The same page as the figure `p16-i0.png`, with the other radio chosen.
`nextId` then routes to the Extractor Pool page rather than the asset page, and
`get_bot_config` sets `enable_phantoms` and `profit_folding_active` to False for
that bot.

![The Extractor Pool page.](p24-i1.png)

`ExtractorPoolPage` in `src/gui/bot_wizard.py`:

- Exchange, the connected venues. Changing it re-scans that venue.
- Pool Base Currency, a fixed list of five: BTC, ETH, USDT, USDC and BNB. It
  names the asset the pool accumulates.
- A line counting the pairs available against that base.
- Target alt pairs, a check list of every alt that trades against the base.
  Leaving every box clear selects the auto-scan by volume.
- Select all and Clear act on the whole list.

![The Extractor group of the parameter page, first nine rows.](p25-i0.png)

`set_mode` hides the eight scrumming groups and shows this one. Nine rows here
and five more in the figure below:

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

- Standing alt units (Inverted), eight decimal places, at 0. The Inverted
  direction reads it; the Normal direction ignores it.
- Correction skip candles, 0 to 100, at 4.
- Drawdown threshold, 0.00 % to 50.00 %, at 3.00 %.
- Hedge budget (USD), at $0.00, which switches it off. Neither of the manual's
  own lists names this control.
- Trend strength threshold, 0.000 to 1.000, at 0.650.

Standing alt units (inverted) - To be re-evaluated.

Correction skip candles - To be re-evaluated.

Drawdown threshold - To be re-evaluated.

Trend Strength Threshold - To be re-evaluated.

### Additional Main Window > Trading Tab Features

#### Trade Logic and Gate Activity

This spool displays the trading logic and gate activity.

![The Activity Log pane.](p26-i1.png)

`StatusLog` in `src/gui/widgets/status_log.py` draws this pane, read-only. Each
line opens with a timestamp in the muted card-label colour, and the message
takes its colour from its level: `PRIMARY` for info, `SUCCESS` for success,
`WARNING` for warning and `ERROR` for error. Three message shapes get their own
form: a line starting `TRADE NOTIFICATION:` draws larger and bold, coloured by
stage; a line starting `WIRE FLOW` or `WIRE INCOME` draws in magenta with a bolt
character; a line starting `WIRE STACK` draws in the pending colour with the
same character. The document keeps 5,000 blocks and drops the oldest beyond
that.

Pause Console is a toggle. While it is down, `log` diverts each line into a
buffer that holds 2,000 entries and drops the newest beyond that; `resume`
replays the buffer with the original timestamps and appends a line counting what
it replayed. `force_log` writes through the pause. A timer in
`src/gui/main_tabs/trading_tab.py` reads `health_stats` every sixty seconds and
writes a warning into the pane itself when the render-error count rises, or when
the pane has been silent for ten minutes while bots run.

#### API Interaction Log

This spool displays API handshake information and data transfer speeds for these messages.

![The API Interaction Log pane.](p26-i2.png)

A read-only `QPlainTextEdit` built in `src/gui/main_tabs/trading_tab.py`, capped
at 2,000 blocks and set to no line wrap. `_on_api_event` in
`src/gui/main_window.py` writes one entry per call, and refuses any call that
did not arrive on the GUI thread. An entry carries a timestamp, the exchange
name, the action, a Reason line, and then Endpoint, Result, Response time and
Data usage where the record holds them. Pause API Log buffers up to 2,000 lines
and flushes them on resume with a line counting them.

The Data usage text is written by the caller. `get_ohlcv` in
`src/exchange/ccxt_connector.py` writes a line naming a seven-indicator engine
and lists seven names. `VotingEngine._create_indicators` in
`src/trading/ta_engine.py` builds twelve indicators, and the Indicator Voting
Panel shows all twelve. The count in the log line and the count in the engine
disagree.

### Add Crypto Exchange Button (to be changed - Add Exchange)

While the initial set up of Acervator requires at least one valid exchange API, additional exchanges can be added and have their own bot swarms. The current upper operational limit of Acervator is unknown. Multi-exchange testing has yet to be attempted as of 8/25/26 with API compatibility work pending. This button also currently opens the Settings Panel but on the incorrect ‘User’ Tab when it should be ‘Exchanges’.

![The Add Crypto Exchange button.](p27-i0.png)

`_make_layer` in `src/gui/main_tabs/trading_tab.py` sets this button as the
corner widget of the layer's tab bar, so it sits at the right of the exchange
sub-tab row. Each layer builds its own, labelled for that layer: Add Crypto
Exchange on the crypto page and Add Stock Exchange on the stock page. It calls
the same `_add_exchange` handler as the button on the empty-state card that a
layer shows while it holds no exchange.

### Indicator Voting Panel

![The Indicator Voting Panel, at the right of the Trading tab.](p27-i1.png)

`IndicatorVotingPanel` in `src/gui/indicator_panel.py` fills the right half of
the Trading tab. `_build_trading_tab` adds it beside the exchange stack.

- The Bot selector at the top names the bot whose votes the panel draws.
  `_refresh_dashboard` refills the list every tick from `list_bots`. The badge
  beside it counts the bullish, bearish and neutral voters.
- TF Lock chooses a timeframe below which an opposing trade is refused.
- The rate line under it shows the BTC and ETH prices and their satoshi and gwei
  equivalents, with the venue name at the end.
- Two tables of six voters each, in the order `INDICATOR_COLS` declares: BB,
  VTX, MACD, SRsi, Ichi and Vol in the first, then Sling, ADX, STrd, ZSc, KER
  and RSI in the second. A green up triangle marks a bullish vote, a red down
  triangle a bearish one, and an em dash a neutral one. ADX, ZSc and KER print a
  raw value; the rest print a percentage.
- Net, Comp and Conf close the first table. Conf draws as a small filled bar
  with its percentage.
- A bar chart under each table draws the same twelve confidences at the width of
  the column above.
- The line at the foot names any active timeframe lock.

[07-indicators.md](07-indicators.md) carries the published formula for each of
the twelve and the gate logic chain behind them.

## The Extractor state machine and chunk accounting

Source: LEGACY, the fourteen-part manual, Part 3 "System Architecture", page 17.
[16-operator-settings.md](16-operator-settings.md) carries every Extractor
setting; this section carries the mechanism the legacy manual describes.

The Extractor holds one chunk of capital in a single base currency and fires
fixed-dollar rounds at several pairs from a watchlist. Each pair it holds runs
through its own small state machine.

### The four states

`src/trading/extractor_bot.py` holds them as four module-level strings at lines
54 to 57, not as an enum, and `ExtractorPosition.state` carries the current one.

| State | Meaning |
| ----- | ------- |
| `pending` | transitional, and never written to a stored position |
| `in_flight` | a round has filled and the position is open |
| `drawdown` | the position has fallen past the configured threshold |
| `bullish_exit` | the exit has been decided and is about to run |

`ExtractorBot._evaluate_open_position` at `extractor_bot.py:865` drives the
transitions. It sets `drawdown` when the position falls past
`extractor_drawdown_threshold_pct`, restores `in_flight` when the position
recovers, and sets `bullish_exit` immediately before `_execute_bullish_exit`
runs. Entry into `in_flight` happens in `_fire_artillery`, at
`extractor_bot.py:1392`.

### Chunk accounting

Five instance fields, all set in `ExtractorBot.__init__` at
`extractor_bot.py:187` to 191, hold the whole of the chunk's arithmetic.

| Field | What it holds |
| ----- | ------------- |
| `_chunk_size_usd` | the chunk's size in dollars, from `extractor_chunk_size_usd` |
| `_chunk_to_base_rate` | base-currency units per dollar |
| `_chunk_size_base` | the chunk's size in base units |
| `_chunk_free_base` | the part of the chunk not yet deployed |
| `_chunk_extracted_total` | base units taken out across the chunk's life |

`_chunk_free_base` is the remaining quantity, and it is the field to watch. It
falls in `_fire_artillery` and in `_maybe_fire_correction`, rises in
`_execute_bullish_exit`, and is rebased whenever the dollar-to-base rate is set
or the chunk is resized. `import_state` restores it from a stored position.

The position never asks the exchange for a balance. Its accounting is the chunk,
which is what keeps two Extractor positions on the same base currency from each
counting the same money as their own.

