# Simulator Tab (Hot Mess; Complete Rebuild In Progress)

Now: the Sim tab draws the Live tab's layout over stored candles, with three run modes, and it sends no order (`src/gui/simulator/sim_trading_tab.py, in SimTradingTab`).

![The Simulator tab, with no fleet loaded.](p33-i0.png)

The figure shows the tab the rebuild replaced. Its Mode list, Load live fleet, Fetch YTD, Start Replay and Simulator Log are gone.

## How to use the Simulator tab

This part is for lookup. Each row names a control or a group of them, says what it does and what reads it, and cites the code behind it. A row that holds a value gives its range and start value, or links to the Live row that holds them. Where a control is Live's own, the row links to Live's row and says what differs.

The Sim tab holds its own fleet. A bot here is a stored record and not a live bot. The tab places no order, and it saves to the sim fleet file and not to the live fleet file (`src/simulator/fleet_source.py, in FleetSource.save`).

### Two builds of this tab

A frozen build draws the variant stamped into it. A source run reads `ACERVATOR_VARIANT` and draws React when nothing names a variant (`src/_variant.py, in resolve_variant`).

The React page sends its presses to Python (`src/gui/simulator/sim_react_trading_tab.py, in SimTradingTabReact.run_action`). Two reach nothing there: the panel's Privacy dot and a press on an Extractor row. A row names a build where the two differ.

### The three run modes

The tab opens on the mode the sim fleet file names, else Validation (`src/simulator/fleet_source.py, in _read_sim_mode`). Each mode holds its own fleet. A mode press draws that fleet and writes one line on the Activity Log (`src/gui/simulator/sim_trading_tab.py, in SimTradingTab.set_mode`).

| Mode | What a run does and what it reads |
| --- | --- |
| Validation | Puts each trade in the YTD trade files on its Stone Tablet candle, runs the gate chains again on that candle, and sets the new gate lights beside the lights Live recorded. A trade needs a tablet and a recorded gate row within five minutes of it. A pair with files for two years reruns the newest file alone. One press reruns up to 400 trades. `src/simulator/validation.py, in _validate`, `src/gui/main_tabs/simulator_tab_surface.py, in VALIDATION_RERUN_LIMIT` |
| Back Test | Walks each bot along every stored bar of its asset on its venue, rolled up to its TA Timeframe. The bot opens worth its Target Balance at the 30th bar, and each fold spends that bot's own sale proceeds. `src/simulator/back_test.py, in walk` |
| Portfolio Battery | Walks a named historical portfolio over one span and sets each Harvest-Fold end beside the HODL end. No cash cap holds a fold, though a venue's settlement delay can. The budget, the sum of the Target Balances, is a reported figure. A crypto bot walks its own timeframe and 1d, and any other bot walks 1d, 1w and 1M. `src/simulator/portfolio_battery.py, in bot_timeframes`, `src/simulator/back_test.py, in apply_fold` |

The three fleets, their wires and the mode in force reach the sim fleet file on each fleet change, and every bot loads idle at the next launch (`src/simulator/fleet_source.py, in loaded_idle`).

### The fleet and run buttons

With no fleet held, the Get Started card offers the mode's two ways in. With a fleet held, a row above the exchange tabs offers Clear Fleet, the two ways in and Start Run (`src/gui/simulator/sim_trading_tab_surface.py, in way_in_buttons`).

| Button | What it does and what it reads |
| --- | --- |
| Import Live Fleet (Validation, Back Test) | Copies the saved live bots of one exchange into this mode's fleet, under their own ids, each idle. It reads the live fleet file and writes nothing there. With two or more exchanges saved, a chooser asks which. A sealed fleet reads as holding no bot. `src/simulator/fleet_source.py, in FleetSource.import_live_fleet` |
| Generate From YTD (Validation) | Holds one idle bot per traded pair in one exchange's YTD trade files, on the bot config's built-in values with phantoms off. Its Target Balance is the units bought less the units sold, at the last fill's price. A pair that sold as much as it bought holds no Target Balance, and one line counts them. A pair with a listed file missing is not held, and one line names the file. `src/simulator/fleet_source.py, in FleetSource.generate_from_ytd`, `src/simulator/fleet_source.py, in ytd_record` |
| Create New Bots (Back Test) | Opens the [Bot Wizard](#how-to-use-the-bot-wizard-on-this-tab). `src/gui/simulator/sim_trading_tab.py, in SimTradingTab._create_bot` |
| Run Portfolio (Portfolio Battery) | Opens a chooser of one portfolio and one span, then walks that portfolio. The held fleet walks when it holds a Scrumming bot with a Target Balance for each symbol, on that symbol's venue. Otherwise the press generates one bot per symbol, at the portfolio's recorded size, else at $500 a symbol shared by its mix. Either way, a held record outside the run leaves the fleet. `src/simulator/portfolio_battery.py, in plan_run`, `src/simulator/fleet_source.py, in FleetSource.hold_battery_fleet` |
| Run Every Portfolio (Portfolio Battery) | Opens the chooser with the span alone, and the press empties the held fleet. The run holds one portfolio's bots, walks them, writes their report and clears them, then takes the next. `src/gui/simulator/sim_trading_tab.py, in SimTradingTab._run_battery`, `src/simulator/portfolio_battery.py, in run_battery` |
| Clear Fleet | Asks Yes or No. Yes empties this mode's fleet and its wires, and the other two fleets stay. `src/gui/simulator/sim_trading_tab.py, in SimTradingTab._clear_fleet` |
| Start Run | Runs the mode. Portfolio Battery opens Run Portfolio's chooser. Validation and Back Test cover the Scrumming bots of one venue. The Qt build takes the venue on the Crypto tab bar, whichever layer is on show, and with none seated there it writes one line and starts nothing. The React build takes the last venue pressed, else the first seated. `src/gui/simulator/sim_trading_tab.py, in SimTradingTab._start_run_pressed`, `src/gui/simulator/sim_react_trading_tab.py, in SimTradingTabReact._current_venue_id` |
| Push to Sim, on the Inspector tab | Holds one bot per pushed market in the Back Test fleet, registers the pushed wires, and shows Back Test. A market with no Stone Tablet, an unusable target or a wire that cannot be delivered refuses the whole push, and one line says why. `src/gui/simulator/sim_trading_tab.py, in SimTradingTab.push_to_back_test` |

While a Validation or Back Test run is in flight, a mode press, Clear Fleet, Start Run and the command bar each write one line and do nothing, except Stop on a bot of that run (`src/gui/simulator/sim_trading_tab_surface.py, in run_in_flight_line`). While a Portfolio Battery walks, a mode press, Clear Fleet and Start Run do the same.

### The choosers

| Row | What it does and what it reads |
| --- | --- |
| Exchange (the exchanges saved, first) | Picks the exchange for Import Live Fleet or Generate From YTD. It shows with two or more to pick from. `src/gui/simulator/sim_exchange_choice.py, in SimExchangeChoiceDialog` |
| Portfolio (35 portfolios, first by name) | Picks the portfolio, with its symbol count and description. Run Every Portfolio draws no such row. `src/gui/simulator/sim_exchange_choice.py, in SimPortfolioChoiceDialog`, `src/simulator/portfolios.py, in PORTFOLIOS` |
| Span (All and seven periods, All) | Picks the candles a walk covers. `src/simulator/portfolio_battery.py, in SPANS` |
| Cost line | States what the choice would fetch before OK: candles, calls and size, or that nothing needs fetching. `src/simulator/portfolio_battery.py, in cost_line` |
| OK, Cancel | OK takes the pick. Cancel writes one line and moves nothing. `src/gui/simulator/sim_trading_tab.py, in SimTradingTab._import_live_fleet`, `src/gui/simulator/sim_trading_tab.py, in SimTradingTab._run_battery` |

### The Get Started card

| Part | What it does and what it reads |
| --- | --- |
| Get Started tab | Shows on a class layer that seats no venue. The title reads No Crypto Fleet Loaded and the hint Load a Crypto fleet to begin a run, each naming the layer's class. `src/gui/simulator/sim_trading_tab_surface.py, in placeholder_title_text` |
| Validation, Back Test, Portfolio Battery | The venue page's three mode buttons, so an empty mode can be left. `src/gui/simulator/sim_trading_tab_surface.py, in placeholder_mode_buttons` |
| Clear Fleet and the two ways in | The same buttons as the row above. Clear Fleet shows while this mode holds a bot. `src/gui/simulator/sim_trading_tab_surface.py, in placeholder_way_in_buttons` |

### The venue page

Each venue sub-tab holds one exchange's page. Live's Privacy Mode, news line, Add Exchange button and DATA POOL STOPPED banner are not on this tab.

An exchange that serves no class seats nothing. Portfolio Battery files a non-crypto bot on `yahoo` unless another venue alone holds its tablet, and `yahoo` is that case. Such a bot walks with no sub-tab, no row and no Stop (`src/gui/simulator/sim_trading_tab.py, in SimTradingTab.add_exchange_tab`, `src/simulator/portfolio_battery.py, in plan_venue`).

| Control | What it does and what it reads |
| --- | --- |
| Venue sub-tabs (the exchanges the fleet names, the first seated) | A press shows that exchange, in both builds. The Qt build seats a venue on one layer: Stock for a broker in `EQUITY_VENUES`, Crypto for the rest. The React build seats it on each layer it serves, so Coinbase draws on all six. See [Live's row](../06-trading-tab.md#one-sub-tab-per-exchange). `src/gui/main_tabs/asset_class_surface.py, in EQUITY_VENUES`, `src/gui/main_tabs/trading_tab_surface.py, in layer_exchanges` |
| Validation, Back Test, Portfolio Battery (the saved mode, else Validation) | Pick the run mode. The lit button names the mode in force. `src/gui/simulator/sim_exchange_tab_surface.py, in mode_style` |
| + New Bot | Opens the [Bot Wizard](#how-to-use-the-bot-wizard-on-this-tab) in any mode, in both builds. Finish holds one idle record in this mode's fleet. See [Live's row](../06-trading-tab.md#one-sub-tab-per-exchange). `src/simulator/fleet_source.py, in FleetSource.create` |
| Data pool row | Holds nothing, and keeps the height of [Live's line](../06-trading-tab.md#one-sub-tab-per-exchange). `src/gui/simulator/sim_exchange_tab_surface.py, in DATA_POOL_ROW_TEXT` |
| Splitter handles | A drag shares the space between two panes, in both builds. `src/gui/simulator/sim_trading_tab.py, in SimTradingTab._build`, `src/gui/web/sim_trading_tab.js, in Splitter` |

### The asset class group on this tab

A press moves the tab to that class's layer and keeps that class's rows (`src/gui/simulator/sim_trading_tab.py, in SimTradingTab.set_asset_class`). While the class keeps no row, the tab draws a note that reads No Crypto simulated bot to show, with that class's name (`src/gui/main_tabs/class_filter_tab.py, in ClassFilterTabMixin._draw_class_notes`).

In the Qt build the kept rows go to the venue's own page, on the Crypto or Stock layer. A Stock pair on a Crypto-layer venue lands on a page that is not on show. The Commodities, Forex, Indices and Futures / Perps layers seat no venue, so they draw no row (`src/gui/simulator/sim_trading_tab.py, in SimTradingTab.refresh_bots`).

In the React build a venue's page fills on the first layer that seats it. A later layer shows the sub-tab with an empty page (`src/gui/web/sim_trading_tab.js, in renderExchangePane`).

A row carries no class of its own, so its class comes from the venue. The venue's market recording names the pair, or the venue serves one class. A pair on a venue that serves several classes, with no recording of the pair, draws no row, and the bot stays in the fleet and in the panel's selector (`src/gui/main_tabs/class_filter_surface.py, in bot_class`, `src/gui/main_tabs/asset_class_surface.py, in symbol_class`).

### The bot tables

Both tables are Live's. The Scrumming table is Live's own class with three readings replaced (`src/gui/simulator/sim_bot_status_table.py, in SimBotStatusTable`). Each row below links to [The bot tables](../06-trading-tab.md#the-bot-tables), and each Scrumming press works in both builds.

| Scrumming Bots column | What differs from Live |
| --- | --- |
| Row press, column sort | Nothing. See [The bot tables](../06-trading-tab.md#the-bot-tables). `src/gui/main_tabs/bot_status_table_surface.py, in selection_after_press`, `src/gui/main_tabs/bot_status_table_surface.py, in order_statuses` |
| Round header dots | Nothing. See [The bot tables](../06-trading-tab.md#the-bot-tables). `src/gui/main_tabs/bot_status_table_surface.py, in BotStatusTableModel.on_privacy_toggled` |
| Asset, Symbol, Trades, Target | Nothing. See [The bot tables](../06-trading-tab.md#the-bot-tables). `src/gui/simulator/sim_bot_status_table.py, in SimBotStatusTable` |
| Current Position Value | Held units at the row's own last price, which a walk writes. No age check applies. See [The bot tables](../06-trading-tab.md#the-bot-tables). `src/gui/simulator/sim_bot_status_table.py, in SimBotStatusTable._display_price` |
| Target A15, Target A14 | The target at the rate of the A15 or A14 row in this table, with no 24-hour drift. It reads pending with no such row or with no price on that row, and it never reads Live's unlisted dash. See [The bot tables](../06-trading-tab.md#the-bot-tables). `src/gui/simulator/sim_bot_status_table_surface.py, in sim_target_denom_cell` |
| Ammo | Live's cell, over the row's own last price. See [The bot tables](../06-trading-tab.md#the-bot-tables). `src/gui/main_tabs/table_cells_surface.py, in TableCellsModel.ammo_cell` |
| Fire | A press on a running or paused bot writes one refusal line on the Activity Log and moves nothing. A stored record arms nothing, so Live's solid, dashed and ceiling looks do not draw. See [The Fire button](../06-trading-tab.md#the-fire-button). `src/gui/simulator/sim_trading_tab.py, in SimTradingTab._on_bot_fire`, `src/simulator/fleet_source.py, in row_status` |
| Detail button | Opens the [Bot Settings window](#how-to-use-the-bot-settings-window-on-this-tab). See [The bot tables](../06-trading-tab.md#the-bot-tables). `src/gui/simulator/sim_trading_tab.py, in SimTradingTab._on_bot_detail` |

| Extractor Bots column | What differs from Live |
| --- | --- |
| Bot ID, Symbol, Mode, Trades, Pool, Liquid, Fire | Nothing, and a run walks no Extractor. See [The bot tables](../06-trading-tab.md#the-bot-tables). `src/gui/simulator/sim_extractor_bot_table.py, in SimExtractorBotTable`, `src/gui/simulator/sim_trading_tab.py, in SimTradingTab._run_bots` |
| Row press | The Qt build selects the row for the command bar, as Live's does. On the React page the press reaches nothing. `src/gui/web/sim_extractor_bot_table.js, in BotRow` |
| Detail button | Opens the [Bot Settings window](#how-to-use-the-bot-settings-window-on-this-tab), in both builds. On the React page it also selects the row for the command bar. See [The bot tables](../06-trading-tab.md#the-bot-tables). `src/gui/web/sim_extractor_bot_table.js, in ActionButton` |

### The command bar

Each command acts on the selected row, as on [The command bar](../06-trading-tab.md#the-command-bar). With no row selected it logs "Select a bot first." This bar has no SHIFT form, connects to no venue and walks nothing (`src/gui/simulator/sim_trading_tab.py, in SimTradingTab._on_bot_command`).

| Button | What differs from Live |
| --- | --- |
| Start | Moves the record to running, which lets the panel read its tablet. See [Live's row](../06-trading-tab.md#the-command-bar). `src/simulator/sim_bot_manager.py, in SimBotManager.start` |
| Pause | Moves the record to paused. See [Live's row](../06-trading-tab.md#the-command-bar). `src/simulator/sim_bot_manager.py, in SimBotManager.pause` |
| Stop | Moves the record to stopped. On a bot of the run in flight, it ends the run, a walk at the bar reached and a Validation before its next trade, and the report reads as stopped. See [Live's row](../06-trading-tab.md#the-command-bar). `src/gui/simulator/sim_trading_tab.py, in SimTradingTab._stop_run`, `src/gui/simulator/sim_trading_tab.py, in SimTradingTab._stop_battery` |
| Restart | Moves the record to stopped, then to running. See [Live's row](../06-trading-tab.md#the-command-bar). `src/simulator/sim_bot_manager.py, in SimBotManager.restart` |
| Delete | Asks Yes or No, as [Live's row](../06-trading-tab.md#the-command-bar) does. Yes drops the record from this mode's fleet. `src/simulator/sim_bot_manager.py, in SimBotManager.unregister` |

### The Indicator Voting Panel on this tab

The panel is a copy of Live's, and fed one reading the two fill the same table cells (`src/gui/simulator/sim_indicator_panel.py, in SimIndicatorVotingPanel`).

| Control | What differs from Live |
| --- | --- |
| Flip button: Replay, Indicators | Not on Live's panel. Replay shows the replay layer and Indicators brings the panel back. It sits first in the header on both layers. `src/gui/simulator/sim_trading_tab.py, in SimTradingTab.flip_layer` |
| Bot selector (the fleet's Scrumming bots, the first) | Lists the Scrumming bots of the mode's fleet. A pick also moves the Tablet chooser. No Previous or Next button draws, and a Bot: label stands before it. See [Live's panel](../06-trading-tab.md#the-indicator-voting-panel-on-this-tab). `src/gui/simulator/sim_indicator_panel.py, in SimIndicatorVotingPanel.update_bot_list` |
| Votes | Read the last 100 candles of a tablet at the bot's own timeframe, while the bot is running or paused, at the weights your settings hold now. The repository's tablets are 5m, so a bot at the wizard's 1h start value reads none. `src/gui/simulator/sim_trading_tab_surface.py, in ivp_feed` |
| TF column, Comp | A phantom's row needs a tablet at the phantom's timeframe. With 5m tablets the bot's own row draws alone, and Comp reads no phantom. See [Live's panel](../06-trading-tab.md#the-indicator-voting-panel-on-this-tab). `src/gui/simulator/sim_trading_tab_surface.py, in ivp_feed` |
| Bars | Each pillar fills the panel's height, where Live's stands at the height of its own reading. See [Live's panel](../06-trading-tab.md#the-indicator-voting-panel-on-this-tab). `src/gui/simulator/sim_indicator_panel.py, in CollatedPillarsWidget` |
| Staleness label | Names the age of the votes, the tablet's last day and the weights note. With no votes, the React page names the cause and the Qt build hides the label. See [Live's panel](../06-trading-tab.md#the-indicator-voting-panel-on-this-tab). `src/gui/simulator/sim_indicator_panel.py, in SimIndicatorVotingPanel.show_no_data` |
| Rate strip | A15 and A14 rates from the fleet's own rows, and a dash with no such row. See [Live's panel](../06-trading-tab.md#the-indicator-voting-panel-on-this-tab). `src/gui/simulator/sim_trading_tab_surface.py, in rate_snapshot` |
| Privacy dot | The Qt build masks the selector text as Live's does, and its dot shows the state by colour where Live's shows a glyph. On the React page the press reaches nothing. See [Live's panel](../06-trading-tab.md#the-indicator-voting-panel-on-this-tab). `src/gui/simulator/sim_indicator_panel.py, in SimIndicatorVotingPanel._apply_privacy_mask`, `src/gui/web/sim_indicator_panel.js, in renderPanel` |
| BB, VTX, MACD, SRsi, Ichi, Vol, Sling, ADX, STrd, ZSc, KER, RSI, Net, Conf, Locks line | Nothing. See [Live's panel](../06-trading-tab.md#the-indicator-voting-panel-on-this-tab). `src/gui/simulator/sim_indicator_panel.py, in SimIndicatorVotingPanel` |

### The replay layer

The flip button's Replay face swaps the panel for this layer.

| Control | What it does and what it reads |
| --- | --- |
| Tablet chooser (the tablets the mode reads, the newest) | Lists every tablet the mode reads, then each held market with no tablet, marked no tablet. A bot pick moves it to that bot's tablet. After a run it takes the tablet of the bot with the run's last fill. With no such bot it takes the selected bot's tablet, else the newest. `src/gui/main_tabs/simulator_tab_surface.py, in tablet_choices`, `src/gui/main_tabs/simulator_tab_surface.py, in default_tablet_key` |
| Retrieve Tablet, Update Tablet | Reads Retrieve for a market with no tablet and Update for one with a tablet. A press fetches the missing 5m candles through the venue's public candle adapter and appends them to the tablet. Coinbase and CoinGecko hold an adapter, and any other venue fetches nothing and the line reads refused. Each call draws a block on the API Interaction Log, and the first refusal ends the walk. `src/simulator/back_test.py, in adapter_for`, `src/simulator/tablet_retrieval.py, in retrieve` |
| Figures line | Names the shown bot, its scrum and fold pairs, their mean and median distance and its improvement over HODL. It reads no run while no fill of that bot matches the tablet's timeframe. A 1h bot over a 5m tablet reads no run, and so does the layer after Run Every Portfolio, which holds no bot. `src/gui/main_tabs/simulator_tab_surface.py, in fills_for`, `src/gui/main_tabs/simulator_tab_surface.py, in shown_bot` |
| VWAP window | Draws the close and the VWAP over the tablet's last 100 candles. `src/gui/main_tabs/simulator_tab_surface.py, in vwap_payload` |
| Stone Tablet Playback window | Draws those candles and marks the shown bot's fills: the bot with the run's last fill, else the selected bot, else the lowest id on that market. A fill marks when its timeframe matches the tablet's and its time is a candle's stamp in the window. A Validation fill keeps its own time, so it marks on an exact stamp alone. `src/gui/main_tabs/simulator_tab_surface.py, in mark_shapes`, `src/simulator/validation.py, in rerun_trade` |

### The two log panes

| Control | What differs from Live |
| --- | --- |
| Activity Log | The same pane as [Live's](../06-trading-tab.md#the-two-log-panes), with no gate lights. A walk's trade line carries its candle's time and a Validation trade line its fill's time, and each run adds its own lines. `src/gui/simulator/sim_trading_tab.py, in SimTradingTab.log_trade`, `src/gui/simulator/sim_status_log.py, in SimStatusLog.log` |
| Pause Console, Resume Console | The same hold and buffer as [Live's](../06-trading-tab.md#the-two-log-panes), and both presses work in both builds. `src/gui/simulator/sim_status_log.py, in SimStatusLog` |
| API Interaction Log | The same block as [Live's](../06-trading-tab.md#the-two-log-panes), and it takes two entries: one per Stone Tablet call and one per Generate From YTD read. Any other entry is refused. `src/simulator/sim_api_log.py, in SimApiLog.record` |
| Pause API Log, Resume API Log | Both presses work in both builds. The Qt build holds as [Live's](../06-trading-tab.md#the-two-log-panes) does, and a full buffer drops the oldest. On the React page a full buffer drops the newest. `src/gui/simulator/sim_trading_tab.py, in SimTradingTab._on_api_event`, `src/gui/main_tabs/trading_tab_surface.py, in ApiPauseBuffer.hold` |

### The header strip with Sim in front

The strip reads the fleet of the mode in force and repaints as [Live's strip](../06-trading-tab.md#the-header-strip) does (`src/gui/main_window.py, in MainWindow._refresh_header_strip`). No walk stamps a record with a venue reading, so the cells that need one read a dash until a held record brings its stamp from Live.

| Cell | What it reads with Sim in front |
| --- | --- |
| SPENDABLE | Under Validation and Portfolio Battery, the sum of the held Target Balances. Under Back Test, the highest cash a held record carries, and a walk writes none. `src/gui/main_tabs/simulator_tab_surface.py, in fleet_aggregate` |
| P/L | The sum of the held records' unrealised figures, and a dash until a held record carries a venue stamp. `src/gui/main_tabs/header_strip_surface.py, in unrealised_amount` |
| LOCKED | Each bot's units at its own price, else its stored position value, summed. `src/simulator/fleet_source.py, in aggregate_stats` |
| MATURE | A dash until a held record carries a venue stamp. `src/simulator/fleet_source.py, in aggregate_stats` |
| EXCH | Venues seated on the Crypto layer. `src/gui/simulator/sim_trading_tab.py, in SimTradingTab.exchange_count` |
| AMMO | A dash in both builds, because the strip reads no fleet rows from this tab. `src/gui/main_window.py, in MainWindow._fleet_rows` |
| SCRUMMED, FOLDED | The fleet's sum of this year's dollars, and the sum of lifetime dollars while that reads zero. A walk writes lifetime dollars. `src/simulator/fleet_source.py, in aggregate_stats` |
| ACCUMULATED | A dash. The sim fleet publishes no such figure. `src/gui/main_tabs/header_strip_surface.py, in COUNTER_CARDS` |
| TRADES, ERRORS | Sums over the held records. `src/simulator/fleet_source.py, in aggregate_stats` |
| BOTS | Held bots reading running. `src/simulator/fleet_source.py, in aggregate_stats` |

## How to read a run

### The gate-latch criterion

Validation's criterion is that the rerun latches every gate as the recorded row did. Profit and a trade count play no part (`src/simulator/validation.py, in RowComparison.latches_identically`). The run prints two counts, the reruns that latched identically and the gate lights that agreed, and no word of pass or fail (`src/simulator/validation.py, in verdict_lines`).

The recorded row is the one nearest the trade within five minutes, so it can sit on another candle (`src/simulator/validation.py, in nearest_gate_row`).

A bot imported from Live matches gate rows by its own id. Any other bot matches on exchange and symbol (`src/simulator/validation.py, in _validate`).

### Which markets a run can walk

Each bot trades under a unit rule, fractional or whole, read from one table by class and venue. A bot whose class and venue hold no row walks nothing. Back Test names it on the Activity Log. Portfolio Battery names it in `diagnostics.log` and counts its asset on one Activity Log line (`src/simulator/back_test.py, in cited_rule_for`, `src/trading/scrumming/sizing.py, in CITED_UNIT_RULES`).

Where the market recording holds the venue's size step or minimum for the pair, the walk sizes each order on those. Elsewhere it sizes on the unit rule. A Back Test writes one line per bot saying which (`src/simulator/back_test.py, in rule_source_line`). A walk needs at least 30 bars, and a bot with no bar at its timeframe walks nothing (`src/simulator/back_test.py, in walk`).

### What a run writes

| Output | What it holds |
| --- | --- |
| Activity Log | One line per fill, and the run's start and end lines. A walk adds progress lines, and a Validation adds none. `src/gui/simulator/sim_trading_tab_surface.py, in trade_line` |
| The bot rows | A walk writes each bot's figures into its record, once per two seconds on screen. Validation and Back Test leave their bots stopped. Under Portfolio Battery a walk's end stops its bot, a bot that walked nothing stays idle, and Run Every Portfolio clears each fleet. `src/gui/simulator/sim_trading_tab.py, in SimTradingTab._take_bot_stats`, `src/gui/simulator/sim_trading_tab.py, in SimTradingTab._battery_portfolio_finished` |
| Trade parity report | One Markdown file and one JSON file under `reports/simulator` in the log folder, named for the mode, the subject, the span and the time. The Activity Log names it. Run Every Portfolio writes one pair per portfolio and one summary pair. A run that raises writes a partial report, and the Activity Log gets the failed line alone. `src/simulator/parity_report.py, in report_name`, `src/simulator/parity_report.py, in write_partial` |
| The sim bucket | `trade.log`, `voting.log`, `diagnostics.log` and one `gate/<exchange>/<sector>/gate.log` under `sim` in the log folder. `src/simulator/sim_bus.py, in sim_log_paths` |
| The sim signal file | `signals/session.jsonl` under `sim`. A run's worker thread sends its signals here, the Activity Log names the path at the start, and the main signal file gains one row at the end. `src/simulator/sim_bus.py, in routed_run` |
| The sim fleet file | `sim_fleet.json` under `sim`, with each mode's fleet, wires and wire ledgers. `src/gui/simulator/sim_trading_tab.py, in SimTradingTab._hold_run_wires`, `src/simulator/fleet_source.py, in FleetSource.save` |

### Where the data comes from

| Source | What it is |
| --- | --- |
| Stone Tablets | Stored 5m candles by asset, year and exchange, tracked in the repository's `stone_tablets` folder. A frozen build reads `.acervator/stone_tablets` in your home folder instead. Validation and Back Test read these. `src/trading/stone_tablets/storage.py, in _tablet_root` |
| RA-StoneTablets | The portfolios' own history in `.acervator_ra_tablets` in your home folder: 5m for crypto and 1d for the rest. Portfolio Battery reads these, and fetches missing crypto candles first. `src/trading/stone_tablets/ra_paths.py, in RA_STONE_TABLETS_DIR`, `src/simulator/portfolio_battery.py, in retrieve_tablets` |
| The recorded gate log | Live's gate rows, read only. Validation compares against them. `src/simulator/gate_log_source.py, in GateLogSource` |
| Saved live fleet | The live fleet file, read only, for Import Live Fleet. `src/simulator/fleet_source.py, in FleetSource.stored_records` |

### The YTD trade files

One file holds one exchange, one symbol and one year, and a manifest beside the files lists them. Each row holds a fill's id, time, side, amount, price, cost and fee (`src/exchange/ytd_trade_store.py, in YtdTrade`).

A gap record marks a year the export covers with no trade for a symbol, and the covered days before that symbol's first row and after its last. A quiet stretch between two trades writes no gap (`src/exchange/ytd_csv_import.py, in _store_year`, `src/exchange/ytd_csv_import.py, in _edge_gaps`).

The import reads an exchange's export through that exchange's column map. A map exists for Coinbase, and an exchange with no map is refused by name (`src/exchange/ytd_csv_import.py, in export_map_for`). Nothing in the running program calls the import (`src/exchange/ytd_csv_import.py, in import_ytd_csv`). The Sim tab reads the files through one reader, which writes no trade file (`src/simulator/ytd_trade_source.py, in YtdTradeSource`).

## How to use the Bot Wizard on this tab

The wizard's title reads Create Auto Trader. The Qt build draws `SimBotCreationWizard` and the React build draws `SimBotWizardReactDialog`, through `src/gui/variant_surface.py, in surface_class`. Finish holds a record, and the bot stays idle. Its walk matches [Live's walk](../06-trading-tab.md#the-walk-through-the-wizard), apart from the rows below.

### What differs from Live's wizard

| Part | What differs from Live |
| --- | --- |
| Trading Mode page: Accumulation Trading (Scrumming), Base Currency Extractor (Multi-Target) | The Qt build offers these two on each class. The React build offers Crypto Scrumming and the same Extractor on each class. See [Live's page](../06-trading-tab.md#trading-mode-page). `src/gui/simulator/sim_bot_wizard.py, in SimModeSelectionPage`, `src/gui/simulator/sim_react_bot_wizard.py, in SimBotWizardReactDialog.model` |
| Select Asset Pair page: Exchange | Lists the venues seated on the Crypto layer, then each venue a tablet names. See [Live's row](../06-trading-tab.md#select-asset-pair-page). `src/gui/simulator/sim_bot_wizard_surface.py, in wizard_exchanges`, `src/gui/simulator/sim_trading_tab.py, in SimTradingTab._create_bot` |
| Select Asset Pair page: Base Currency, Target Asset, Status line | Target Asset lists each tablet's asset under each base currency, and no venue is called. A seated venue with no tablet lists nothing in the Qt build and its recorded markets in the React build. The Qt list marks no market as untradeable. See [Live's row](../06-trading-tab.md#select-asset-pair-page). `src/gui/simulator/sim_bot_wizard_surface.py, in tablet_markets`, `src/gui/main_tabs/bot_wizard_surface.py, in BotWizardModel.on_exchange_changed` |
| Information button | Nothing. See [Live's row](../06-trading-tab.md#select-asset-pair-page). `src/gui/simulator/sim_bot_wizard.py, in SimAssetSelectionPage._show_info` |
| Extractor Pool page: Exchange, Pool Base Currency, Alternate pair list | The same venue list. The alternate pair list reads the tablet's markets. See [Extractor rows](../06-trading-tab.md#extractor-rows). `src/gui/simulator/sim_bot_wizard.py, in SimExtractorPoolPage` |
| Whole-Unit Market group, Contract Expiry group: Open Position At, Expiry Close, Expiry Lead Mode, Lead Fraction, Lead Days, Expiry Horizon | The Qt build draws neither group. The React build draws each as Live does when the market recording makes the pair whole-unit or dated, and Finish stores their values, which no walk reads. See [Live's rows](../06-trading-tab.md#whole-unit-market-and-contract-expiry-rows). `src/gui/simulator/sim_bot_wizard.py, in SimTradingParamsPage`, `src/gui/main_tabs/bot_wizard_surface.py, in BotWizardModel.set_market_groups` |
| Unit lines | Neither build draws them. See [Live's row](../06-trading-tab.md#scrumming-settings-rows). `src/gui/simulator/sim_bot_wizard.py, in SimTradingParamsPage` |
| Finish on a market no bot can trade | The Qt build takes the market. The React build keeps the wizard open, and its line shows the bare word `market_untradeable`. See [Live's row](../06-trading-tab.md#the-walk-through-the-wizard). `src/gui/simulator/sim_bot_wizard.py, in SimBotCreationWizard`, `src/gui/main_tabs/bot_wizard_surface.py, in BotWizardModel.finish` |
| Phantom Bots page, Next | The Qt build asks no API load box. `src/gui/simulator/sim_bot_wizard.py, in SimPhantomConfigPage.validatePage` |
| Pre-flight check | None runs. See [Live's row](../06-trading-tab.md#the-walk-through-the-wizard). `src/gui/simulator/sim_trading_tab.py, in SimTradingTab._create_bot` |
| Parent check | Live's rule, over this mode's fleet. See [Live's row](../06-trading-tab.md#the-walk-through-the-wizard). `src/gui/simulator/sim_bot_wizard_surface.py, in extractor_parent_refusal` |

### What a run reads from the wizard's rows

Each row below holds Live's range and start value, and its link gives them. A walk reads a bot's record through a shorter list than a live bot does, so most rows store a value that no walk reads (`src/simulator/fleet_source.py, in SimBot`, `src/simulator/back_test.py, in tape_context`).

| Rows | In a Back Test walk |
| --- | --- |
| Target Balance, TA Timeframe, Opposing Trade Interval, Trading Fee %, Landing Strip Candles, BB Tolerance. See [Scrumming Settings rows](../06-trading-tab.md#scrumming-settings-rows) | Read. The fold distance leaves out Band Travel. The fee is the box's figure, and a box of 0 reads as 0.6. `src/simulator/back_test.py, in apply_fold` |
| Max Target Growth %. See [Scrumming Settings rows](../06-trading-tab.md#scrumming-settings-rows) | Read for the cycle cap. `src/simulator/back_test.py, in grow_target` |
| Detect Threshold, BB Midline Gate. See [Advanced Scrumming rows](../06-trading-tab.md#advanced-scrumming-rows) | Read. `src/simulator/back_test.py, in tape_context` |
| SCRUM requires bullish TA, SCRUM holds in sustained uptrend, SCRUM defers to higher-TF bullish, FOLD requires bearish TA, FOLD defers to higher-TF bearish. See [Strategy Gate Flags rows](../06-trading-tab.md#strategy-gate-flags-rows) | Read. `src/simulator/back_test.py, in tape_context` |
| Enable Position Ceiling, Ceiling Multiple. See [Risk Controls rows](../06-trading-tab.md#risk-controls-rows) | Read for the fold taper. `src/simulator/back_test.py, in fold_taper` |
| Enable Phantom Bots, Timeframe boxes. See [Phantom Bots rows](../06-trading-tab.md#phantom-bots-rows) | Read. Each phantom is the walk's own candles rolled up to that timeframe. `src/simulator/back_test.py, in phantom_tapes` |
| Order Visibility, Aggressive Trading, Stack Mode, Split Distance, Tranche Count, Spacing. See [Trading Parameters rows](../06-trading-tab.md#trading-parameters-rows) | Stored and not read. A walk sells in one piece, with no ladder. `src/simulator/back_test.py, in apply_scrum` |
| Max Entry Price, Min Entry Price, Scrum Fold Ratio. See [Scrumming Settings rows](../06-trading-tab.md#scrumming-settings-rows) | Stored and not read. A sale queues all its proceeds for buy-back. `src/simulator/back_test.py, in apply_scrum` |
| Fire Threshold, Read Rate, Band Travel, BB Bullseye Check. See [Advanced Scrumming rows](../06-trading-tab.md#advanced-scrumming-rows) | Stored and not read. A walk evaluates each bar from the 30th on. `src/simulator/back_test.py, in evaluations_expected` |
| Hedge Rebalance Active, Hedge Balance. See [Hedge Rebalance rows](../06-trading-tab.md#hedge-rebalance-rows) | Stored and not read. `src/simulator/fleet_source.py, in SimBot` |
| Soft CB Threshold, Hard CB Threshold, Soft CB Cooldown. See [Circuit Breakers rows](../06-trading-tab.md#circuit-breakers-rows) | Stored and not read. Neither breaker blocks a gate in a walk. `src/simulator/back_test.py, in tape_context` |
| Max Cartridge Size, Smart Cartridge, Smart Ceiling. See [Circuit Breakers rows](../06-trading-tab.md#circuit-breakers-rows) | Stored and not read. `src/simulator/fleet_source.py, in SimBot` |
| Enable Detonation, Detonation TF, Min Confidence. See [Risk Controls rows](../06-trading-tab.md#risk-controls-rows) | No walk reads them. The Fire button's mouse-over shows them. `src/simulator/fleet_source.py, in row_status`, `src/gui/main_tabs/bot_status_table_surface.py, in risk_lines` |
| Candles to lock. See [Phantom Bots rows](../06-trading-tab.md#phantom-bots-rows) | Stored and not read. `src/simulator/sim_bot_view.py, in PhantomLock` |
| Chunk size (USD), Artillery size (USD), Watch list top-N, Watch list refresh, Exit %. See [Extractor rows](../06-trading-tab.md#extractor-rows) | Stored, and no run walks an Extractor. `src/gui/simulator/sim_trading_tab.py, in SimTradingTab._run_bots` |

A Portfolio Battery walk reads the same rows of a held bot. A bot it generates walks on built-in values, and a non-crypto bot walks 1d, 1w and 1M whatever its TA Timeframe (`src/simulator/portfolio_battery.py, in generated_bot`, `src/simulator/portfolio_battery.py, in bot_timeframes`).

## How to use the Bot Settings window on this tab

The Detail button opens this window over one stored record. A Scrumming bot's window carries Status, Settings, Fold Tranches, Stack Tranches, Bot Swarm, Market Inspector and Phantom Bots, and an Extractor's carries Status, Settings and Positions Held, as [Live's window](../06-trading-tab.md#how-to-use-a-running-bot) does (`src/gui/simulator/sim_bot_detail.py, in SimBotDetailDialog`). The window shows the record and changes nothing: each write it tries is refused (`src/simulator/sim_bot_view.py, in SimBotView`).

| Control | What it does and what it reads |
| --- | --- |
| Apply Changes | Greys until a row moves. A press refuses each pending change, the line under it reads Refused, with the count, and the record keeps its values. See [Live's row](../06-trading-tab.md#the-windows-own-buttons). `src/gui/simulator/sim_bot_detail.py, in SimBotDetailDialog._apply_changes` |
| Close | Closes the window and drops unapplied edits, as [Live's](../06-trading-tab.md#the-windows-own-buttons) does. `src/gui/simulator/sim_bot_detail.py, in SimBotDetailDialog._setup_ui` |
| Prev, Next | Walk the bots of the same exchange and keep the tab, where [Live's](../06-trading-tab.md#the-windows-own-buttons) walk every bot. `src/gui/simulator/sim_trading_tab.py, in SimTradingTab._on_bot_detail` |
| Status tab | Read-only: the record's trades, open orders, price and uptime. Realised P/L reads a pending dash until the record brings a venue figure from Live. See [Live's row](../06-trading-tab.md#the-windows-other-tabs). `src/gui/simulator/sim_bot_detail.py, in SimBotDetailDialog._create_status_tab` |
| Settings tab, the wizard's rows | Show the record's values, and Apply refuses a change. The note that changes take effect at Apply is Live's text. `src/gui/simulator/sim_settings_tab.py, in SimSettingsTabMixin` |
| Live target, Standing surplus, Cycle growth budget, Over-cap tranches, Target A15, Target A14 | Show the record's figures, as [Live's rows](../06-trading-tab.md#rows-only-a-running-bot-shows) do. The two target rows read the fleet's own rates, with no 24-hour gap and no 5-second repaint. `src/gui/simulator/sim_settings_tab.py, in SimSettingsTabMixin._refresh_target_denom_rows` |
| Profit Folding Active | Shows the stored value. A walk reads it, and Apply refuses a change. See [Live's row](../06-trading-tab.md#rows-only-a-running-bot-shows). `src/simulator/back_test.py, in grow_target` |
| Tranche Despawn Timer | Shows the stored value. No walk reads it. See [Live's row](../06-trading-tab.md#rows-only-a-running-bot-shows). `src/simulator/fleet_source.py, in SimBot` |
| Hunger, Hunger Pace, Accumulation Shadow | Not drawn. No walk reads them. See [Live's rows](../06-trading-tab.md#rows-only-a-running-bot-shows). `src/gui/simulator/sim_live_settings_tab_surface.py, in SimLiveSettingsTabModel` |
| Reset All Breakers | Changes nothing. The Qt button reads Reset failed for two seconds, and the React page's line under the buttons names the refusal. See [Live's row](../06-trading-tab.md#rows-only-a-running-bot-shows). `src/gui/simulator/sim_react_bot_detail.py, in press_method` |
| Self-Destruct | The Qt build asks for the typed word, then a box says nothing was sold. The React page refuses at once, and the line under the buttons names the refusal. See [Live's row](../06-trading-tab.md#rows-only-a-running-bot-shows). `src/gui/simulator/sim_settings_tab.py, in SimSettingsTabMixin._on_self_destruct_clicked`, `src/gui/simulator/sim_react_bot_detail.py, in press_method` |
| Fold Tranches tab | Lists the record's queued buy-backs and their counters. Fire, each Clear button and Clear Wire Credits end in a refusal. See [Live's row](../06-trading-tab.md#the-windows-other-tabs). `src/gui/simulator/sim_fold_tranches_tab.py, in SimFoldTranchesTabMixin` |
| Fold Tranches: Order, Filter | Qt build only. They sort and hide rows, as [Live's](../06-trading-tab.md#the-windows-other-tabs) do. `src/gui/live_settings/fold_chrome.py, in build_fold_row_controls` |
| Stack Tranches tab | Lists the record's rising sell levels and counters. Its Clear buttons end in a refusal, and a walk opens no level. See [Live's row](../06-trading-tab.md#the-windows-other-tabs). `src/gui/simulator/sim_stack_tranches_tab.py, in SimStackTranchesTabMixin` |
| Bot Swarm tab | Reads Bot Swarm not active, because the tab hands the window no wire manager. See [Live's row](../06-trading-tab.md#the-windows-other-tabs). `src/simulator/sim_bot_view.py, in SimBotView` |
| Market Inspector tab | Reads No Market Inspector scan yet, because a stored record holds no scan. See [Live's row](../06-trading-tab.md#the-windows-other-tabs). `src/gui/simulator/sim_market_inspector_tab_surface.py, in per_bot_view` |
| Phantom Bots tab | Enable Phantom Bots, Timeframe and Candles to lock show the stored set. In the Qt build Apply refuses a change. On the React page these controls take no edit and Apply stays grey. Phantoms started reads NO and SCRUM lock state reads UNLOCKED, whatever the record holds. See [Live's row](../06-trading-tab.md#the-windows-other-tabs). `src/gui/simulator/sim_phantom_bots_tab.py, in SimPhantomBotsTabMixin`, `src/gui/web/sim_phantom_bots_tab.js, in renderTab` |
| Positions Held tab | Lists an Extractor's stored positions, and each Fire is refused. See [Live's section](../06-trading-tab.md#a-running-extractor). `src/gui/simulator/sim_positions_held_tab.py, in SimPositionsHeldTabMixin` |
