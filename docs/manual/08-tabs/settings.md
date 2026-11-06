# Settings

This window sets who you are, which venues the app can reach, and how new bots start. It holds nine pages above one Cancel button and one Save button.

This page is for lookup. Each row of a control table names a control or a group of them, says what it does, and cites the code behind it. A row with a stored key names it after Reads. The page lists and the route and vote tables are summaries. A row that holds a value gives its range and start value.

## The pages

| Page | What it sets |
| --- | --- |
| User | Your name and the Fleet Lock password. |
| Exchanges | Each venue's keys, for the asset class active when the window opened, or the bot's own class when Start opened it. |
| Trading | Where a new bot's wizard opens: target, order visibility and aggressive mode. |
| TA Indicators | How far each of the twelve indicator votes counts. |
| Phantom Bots | Where a new bot's phantom choices open. |
| Theme | The colour theme and the accent colour. |
| Sound | Which events play a sound, and how loud. |
| SMS | Text message alerts: how they go, which events send them, and how often. |
| AI Monitor | The API key, the handshake phrases and the monitor's behaviour. |

Only the Exchanges page changes with the asset class. The title bar reads Settings — Crypto Wing on the Crypto class and Settings on every other class (`src/gui/settings_dialog.py, in SettingsDialog.__init__`).

The React page draws a second title line. It reads Settings — Crypto Wing on Crypto, Settings — Stock Wing on Stock, and Settings — Crypto Wing on every other class (`src/gui/main_tabs/settings_dialog_surface.py, in wing_or_default`, `src/gui/main_tabs/settings_dialog_surface.py, in title_for`).

### How the window opens

| Route | What opens and what follows |
| --- | --- |
| File > Settings | Opens on the User page. `src/gui/main_window.py, in MainWindow._open_settings` |
| Exchange > Add Exchange, or an Add button on the Trading tab | Opens on the Exchanges page. `src/gui/main_window.py, in MainWindow._add_exchange` |
| Start on a broker, or on Robinhood on the Crypto class, with no stored key | Opens on the Exchanges page with that venue pressed, for the bot's asset class. A class that does not list the venue gives way to the first class that does. A venue no class lists stays unpressed unless the store holds it, and a stored one is pressed on its not-offered row. In both cases the feedback line says why. Start tries again when the window closes. `src/gui/main_window.py, in MainWindow._ask_for_venue_connection`, `src/gui/main_tabs/settings_dialog_surface.py, in wing_showing_venue` |

One method builds the window on all three routes (`src/gui/main_window.py, in MainWindow._run_settings_window`). On each one, a Save reaches the running window at once.

An exchange you add or remove changes the tabs when the window closes, on both builds. A new tab draws its bot table at that moment (`src/gui/main_window.py, in MainWindow._sync_exchange_tabs`). A removed venue leaves the tab bars, the React Live page and the list of connectors (`src/gui/main_window.py, in MainWindow._forget_venue`).

A venue the store no longer lists keeps its tab and its connection while a bot on it is neither idle nor stopped, or while the fleet is sealed. The Activity Log names the venue and says why, at each close (`src/gui/main_window.py, in MainWindow._keep_unlisted_venues`). Start refuses a broker the store no longer holds, even while its connection is open (`src/gui/main_window.py, in MainWindow._open_broker_session`).

A key that changes in the window releases that venue's connection when the window closes, and the next Start connects with the new key. A live bot keeps its connection, and the Activity Log says the new key takes effect at that bot's next Start (`src/gui/main_window.py, in MainWindow._release_changed_keys`).

### Two builds of this window

A frozen build draws the variant stamped into it. A source run reads `ACERVATOR_VARIANT` and draws React when nothing names a variant (`src/_variant.py, in resolve_variant`).

The React window inherits Save, Test, Add, Remove and Fleet Lock from the Qt window, and replaces only the methods that draw (`src/gui/react_settings_dialog.py, in SettingsDialogReact`).

Seven things differ on screen:

- The React build hides what you type in API Key and API Secret.
- A form row the page hides loses its box in React and keeps its words (`src/gui/web/settings_dialog.js, in ControlRow`).
- React draws no dash for a stored value a control cannot hold.
- A typed accent paints the Qt window alone.
- React draws a title line inside the page (`src/gui/web/settings_dialog.js, in Dialog`).
- The React SFX Volume figure reads 70% until the slider moves, whatever is stored (`src/gui/react_settings_dialog.py, in SettingsDialogReact.apply_edit`).
- React number boxes print no fixed decimals (`src/gui/web/settings_dialog.js, in Control`).

## What each page persists

Save writes the settings file in your home folder. The Exchanges page writes at each press instead. The store refuses a key it does not declare and a value of the wrong type (`src/core/settings.py, in SettingsManager.set`).

The Twilio Auth Token, SMTP Password and Anthropic API Key rows hide only the screen. Those three go into the file as plain text. Passphrase and venue keys go in encrypted, and the two Fleet Lock rows and Verification Code are never stored (`src/gui/settings_dialog.py, in SettingsDialog._stored_groups`).

| Page | Stored as | Takes effect |
| --- | --- | --- |
| User | `username` | At Save. Fleet Lock writes its own key file. |
| Exchanges | `exchanges` | At each press, with no Save. |
| Trading | `default_target_balance`, `bot_visibility`, `aggressive_trading` | At the next bot wizard. |
| TA Indicators | `ta_indicator_weights` | At Save, on every Scrumming bot. |
| Phantom Bots | `default_enable_phantoms`, `default_phantom_timeframe`, `default_lock_candle_count` | At the next bot wizard. |
| Theme | `theme`, `accent_color` | At Save. |
| Sound | `sound` | At each tick, and Save keeps it. |
| SMS | `message_channels` | At Save. |
| AI Monitor | `ai_monitor` | At Save. |

| Control | What it does and what it reads |
| --- | --- |
| Page tabs | Move between pages. Edits stay held until Save, Cancel or a passing Add, which closes the window and drops every unsaved edit. Each tab's mouse-over says what the page holds. `src/gui/main_tabs/settings_dialog_surface.py, in TAB_TOOLTIPS` |
| Save | Asks the Username and Fleet Lock questions first, then writes every page but Exchanges and closes the window. A key typed with no Add press is dropped. A group the store refuses opens a box that names it, and the rest still save. `src/gui/settings_dialog.py, in SettingsDialog._save` |
| Cancel | Closes the window and writes nothing. A Sound box you ticked has already reached the engine. `src/gui/settings_dialog.py, in SettingsDialog._setup_ui` |
| A stored value a control cannot hold | A Qt number box shows a dash. A Qt slider and every React control keep a figure, and a mouse-over says the stored value is unusable. Save keeps the stored value until you set another. A top-level value of the wrong type falls back to the default at load, shows no mark, and Save writes the default over it. A stored Carrier the list lacks shows AT&T with no mark, and Save writes AT&T. A Save replaces a stored theme name no theme holds. `src/gui/settings_dialog.py, in SettingsDialog._mark_refused`, `src/core/settings.py, in SettingsManager._apply_dict`, `src/gui/settings_dialog.py, in SettingsDialog._sms_rows`, `src/gui/main_window.py, in MainWindow._remember_theme` |

## How to use each page

A row that holds a value gives its range and start value in the first column. The twelve TA sliders give their start value there and share the range in the line above their table. Nine of the ten figures show an earlier capture, so their tab row lists Profit Folding or Logging pages the window does not draw. The Phantom Bots figure matches the drawn page.

### Settings > User Tab

This needs to be built out to accept and contain individual end user credentials. This will also be where a license is entered or a keyfile is imported depending on how we design the authentication piece.

Now: this page holds the Username row and the Fleet Lock group, venue keys go on the Exchanges page, and no license or keyfile row exists (`src/gui/settings_dialog.py, in SettingsDialog._create_user_tab`).

![Settings, the User page.](p34-i1.png)

The figure shows the Username row alone. The drawn page adds the Fleet Lock group under it.

| Row | What it does and what it reads |
| --- | --- |
| Username (text, empty) | Names you. A change over keys on the Exchanges page asks Yes or No at Save. With no lock, those keys are sealed under this name, so Yes reseals them under the new name and No puts the old name back. With a lock, Yes changes the name alone. With no key on that page no question comes, and Market Inspector sign-ins stop opening. Reads `username`. `src/gui/settings_dialog.py, in SettingsDialog._settle_username_rename`, `src/gui/main_tabs/settings_dialog_surface.py, in username_rename_consequence` |
| Fleet Lock state line | Says whether a password is set, read off the key file. A set password seals the saved fleet and the stored keys, and a launch starts no bot until you give it. While Clear the lock is pressed in, this line shows the clear question. `src/gui/settings_dialog.py, in SettingsDialog._show_fleet_lock_state` |
| Password (hidden, empty) | Sets a lock, or changes one this run has opened. A change before you unlock is refused, and the log says why. Both rows empty changes nothing. Save asks Yes or No first, because nothing can recover a lost password. `src/gui/main_tabs/settings_dialog_surface.py, in fleet_lock_intent` |
| Confirm Password (hidden, empty) | Must match Password, or Save takes neither and logs why. It greys while Clear the lock is pressed in. `src/gui/main_tabs/settings_dialog_surface.py, in fleet_lock_intent` |
| Unlock the fleet now | Opens the unlock screen. The right password loads the sealed fleet, runs the launch check and starts every idle or stopped bot. It works only while a lock is set and this run has not opened it. Press it before you add a venue key, because a key added first does not open afterwards. `src/gui/fleet_unlock_dialog.py, in ask_for_unlock`, `src/gui/main_window.py, in MainWindow.unlock_fleet` |
| Clear the lock | Greys with no lock set. It stays pressed in until you press it again or Save. Save needs the current password in the Password row and asks Yes or No. With the right password, Yes writes the saved fleet back as plain text, reseals stored keys under your Username and deletes the key file. A wrong password logs a refusal and keeps the lock. The question on screen says the keys are lost, and the code keeps them. `src/gui/settings_dialog.py, in SettingsDialog._clear_fleet_lock` |

Change Username and the lock in separate Saves. One Save that renames and also sets or clears the lock leaves stored keys that do not open (`src/gui/settings_dialog.py, in SettingsDialog._username_phrase`).

### Settings > Exchanges

![Settings, the Exchanges page.](p35-i0.png)

The figure shows a drop-down and a list of stored exchanges. The drawn page puts the Exchange Status buttons where the list sat, and the Exchange row is plain words.

| Row | What it does and what it reads |
| --- | --- |
| Stock banner | Stock class only. It names the brokers the app builds a connector for, and says how each signs in. `src/gui/main_tabs/settings_dialog_surface.py, in stock_banner_text` |
| Exchange Status buttons | One button per venue the class serves, 16 to a page and four across. A stored venue no class lists follows in amber. A press binds the form below, and the mouse-over names the venue's state. An amber press greys Test and Add and hides the key rows, so only Remove Selected acts. A redraw reads a file and calls no venue. `src/gui/main_tabs/settings_dialog_surface.py, in exchange_status_page` |
| Button colour | Green: the venue answered an authenticated call. Red: the connection was lost. Grey: never asked, the venue refused a key, or a key whose shape alone was checked. Amber: stored, and listed under no class. `src/gui/main_tabs/settings_dialog_surface.py, in VENUE_STATE_COLOURS` |
| Page button | Shows past 16 venues. A press moves to the next page, and the last wraps to the first. `src/gui/main_tabs/settings_dialog_surface.py, in venue_pages_button` |
| Exchange row | Names the pressed venue, and you cannot type in it. `src/gui/main_tabs/settings_dialog_surface.py, in chosen_venue_text` |
| API Key (text, empty) | The venue's key, or a Coinbase key name. The React build hides what you type, and the Qt build shows it. `src/gui/main_tabs/settings_dialog_surface.py, in CONTROL_SPECS`, `src/gui/settings_dialog.py, in SettingsDialog._create_exchange_tab` |
| API Secret (text, empty) | The venue's secret or private key. Escaped newlines in a pasted PEM key turn into real ones. The React build hides what you type, and the Qt build shows it. `src/gui/main_tabs/settings_dialog_surface.py, in CONTROL_SPECS`, `src/gui/settings_dialog.py, in SettingsDialog._typed_secret` |
| This exchange uses an API passphrase (off) | Shows the passphrase row. A press on a venue that needs one ticks it for you. `src/gui/settings_dialog.py, in SettingsDialog._on_exchange_changed` |
| Passphrase (hidden, empty) | The passphrase set on the API key. Test refuses a venue that needs one when this row is empty. `src/exchange/api_validator.py, in validate_credentials` |
| Verification Code (hidden, empty) | Shows for a venue that grants access only on a pasted code. The first Add press returns an address. Open it, approve, paste the code and press Add again. The code is used once and never stored. `src/gui/main_tabs/settings_dialog_surface.py, in connect_verification_code_venue` |
| Test Connection | Checks the typed key and secret and shows the balances. It stores no key, and it colours the button by the venue's answer. A hand-written connector checks the key's shape alone and asks no venue. It greys for a venue with no check path, and it refuses with no venue pressed or a blank row. `src/gui/settings_dialog.py, in SettingsDialog._test_api_connection` |
| Test and Add Exchange | A typed key and secret on a venue Test can check must pass first, or nothing is stored. A venue with no check path stores them unchecked, except E*TRADE, which stores them only after the venue accepts the pasted code. With either row blank, Add runs no check and stores no typed key, and a stored venue keeps its key. A verification-code venue refuses a blank row and stores nothing. Keys are stored encrypted. A passing Add shows Exchange Added and closes the window. The box says the tab will appear for a venue the store did not hold, and says it is already in the main window for a stored one. `src/gui/settings_dialog.py, in SettingsDialog._add_exchange`, `src/gui/settings_dialog.py, in SettingsDialog._connect_verification_code_venue` |
| Connect with a Browser | Replaces Test and Add for a venue that signs in at a browser, on the classes that sign in that way. The key rows hide and Test greys. Approve at the venue's page, and the feedback line names its trade-approval setting. The window and every bot wait until the venue answers, up to 180 seconds, and then this window stays open. On Robinhood's Crypto class the key rows show, and the feedback line asks for the API key and secret. `src/gui/settings_dialog.py, in SettingsDialog._connect_browser_venue`, `src/trading/ata_spm_signin.py, in LoopbackReceiver.wait`, `src/gui/main_tabs/settings_dialog_surface.py, in venue_form_bound` |
| Feedback line | Shows the last answer: blue for a note, green for success, amber for a warning and red for an error. `src/gui/settings_dialog.py, in SettingsDialog._set_feedback` |
| Remove Selected | Removes the pressed venue's stored entry and its colour at once, with no Save. The press then lets go of the venue, on both builds, and the form returns to its opening shape. With no venue pressed it asks you to press one. It refuses while a bot on that venue is neither idle nor stopped, while a Start is taking a bot there through its connect, and while the fleet is sealed. The line names each bot, or says to unlock first. With orders or Stack rungs of a stopped bot resting at the venue it asks Yes or No. The box names how many rest, and says they stay at the venue and that nothing will read their fills. Yes reads the fleet again and then removes the venue, and No keeps it. `src/gui/settings_dialog.py, in SettingsDialog._remove_exchange`, `src/gui/main_tabs/settings_dialog_surface.py, in remove_refusal`, `src/gui/main_tabs/settings_dialog_surface.py, in remove_question` |

### Settings > Trading

![Settings, the Trading page.](p36-i0.png)

The figure shows Position Distance, Increment Style and Default Positions rows the page does not draw.

Each row sets where a bot wizard opens. A running bot keeps its own value.

| Row | What it does and what it reads |
| --- | --- |
| Default Target Balance ($1 to $1,000,000, $200) | Opens the wizard's Target Balance. A wizard opened by a Market Inspector topology Adopt press opens on the proposal's suggested target instead. Reads `default_target_balance`. `src/gui/bot_wizard.py, in _show_stored_target`, `src/gui/main_tabs/bot_wizard_surface.py, in BotWizardModel._apply_stored_target_balance`, `src/gui/main_window.py, in MainWindow._adopt_topology_proposal` |
| Bot Visibility (orderbook or internal, orderbook) | Opens the wizard's Order Visibility. Reads `bot_visibility`. `src/gui/bot_wizard.py, in TradingParamsPage`, `src/gui/main_tabs/bot_wizard_surface.py, in BotWizardModel._apply_stored_visibility` |
| Enable aggressive trading mode (off) | Opens the wizard's Aggressive Trading. The engine changes only Stack tranches in Order Book mode, which go out as immediate-or-cancel limits. A tranche above the market cancels unfilled, and Robinhood on the Crypto class refuses each one. The mouse-over says it changes every buy and sell. Reads `aggressive_trading`. `src/trading/scrumming_bot.py, in ScrummingBot._open_stack_from_scrum` |

### Settings > TA Indicators

![Settings, the TA Indicators page.](p38-i0.png)

Each slider runs 0.00 to 2.00 and sets how far that indicator's vote counts. Save hands all twelve to every Scrumming bot at once, and a bot at target shows its old reading until the next candle (`src/trading/bot_container.py, in BotManager.push_ta_weights`). Reads `ta_indicator_weights`.

| Slider (start) | What it weighs |
| --- | --- |
| Bollinger Bands (1.00) | The Bollinger Bands vote. `src/trading/indicators/bollinger.py, in BollingerBands` |
| Vortex (0.90) | The Vortex vote. `src/trading/indicators/vortex.py, in VortexIndicator` |
| Macd (1.20) | The MACD vote. `src/trading/indicators/macd.py, in MACD` |
| Stochastic Rsi (1.00) | The Stochastic RSI vote. `src/trading/indicators/stochastic_rsi.py, in StochasticRSI` |
| Ichimoku (1.10) | The Ichimoku Cloud vote. `src/trading/indicators/ichimoku.py, in IchimokuCloud` |
| Volume (0.80) | The volume vote. `src/trading/indicators/volume.py, in VolumeAnalysis` |
| Slingshot (1.00) | The Slingshot vote. `src/trading/indicators/slingshot.py, in SlingshotIndicator` |
| Adx (1.00) | The ADX vote. `src/trading/indicators/adx.py, in ADXIndicator` |
| Kaufman Er (1.00) | The Kaufman Efficiency Ratio vote. `src/trading/indicators/kaufman_er.py, in KaufmanERIndicator` |
| Supertrend (1.00) | The Supertrend vote. `src/trading/indicators/supertrend.py, in SupertrendIndicator` |
| Zscore (0.90) | The Z-Score vote. `src/trading/indicators/zscore.py, in ZScoreIndicator` |
| Rsi (0.80) | The RSI vote. `src/trading/indicators/rsi.py, in RSIIndicator` |

| Vote | Which figures it reads |
| --- | --- |
| A running Scrumming bot | These sliders. `src/trading/scrumming_bot.py, in ScrummingBot.set_ta_weights` |
| A new Scrumming bot from the Live wizard | Twelve zeros until the next Save on this window. It has no vote, so it makes no first buy. If it holds a position, a landing strip still sets its side. `src/gui/main_tabs/bot_wizard_surface.py, in with_new_bot_weights` |
| A running phantom | The figures its set was built with, so a wizard bot started before that Save keeps a twelve-zero phantom until it stops. `src/trading/scrumming_bot.py, in ScrummingBot.set_ta_weights` |
| A bot's first-entry check | These sliders, through the same vote as its later trades, at every Max Cartridge Size. It waits for a third indicator. A bot at twelve zeros waits for Save, and its line says so. `src/trading/scrumming/tick_phases.py, in TickPhaseMixin._first_buy_read` |
| A Simulator run | These sliders, read from the file when the run starts. `src/simulator/back_test.py, in walk` |
| A Paper run | The start figures. `src/paper/paper_run.py, in PaperRunner.__init__` |
| An Extractor | The start figures. `src/trading/extractor_bot.py, in ExtractorBot.__init__` |
| A Market Inspector scan | The start figures. `src/trading/ata_spm.py, in evaluate` |

[07-indicators.md](../07-indicators.md) holds the indicator formulae.

### Settings > Phantom Bots

![Settings, the Phantom Bots page.](p39-i0.png)

Each row sets where a bot wizard's phantom choices open.

| Row | What it does and what it reads |
| --- | --- |
| Enable Phantom Bots for Scrumming (on) | Opens the wizard's Enable Phantom Bots box. Reads `default_enable_phantoms`. `src/gui/bot_wizard.py, in PhantomConfigPage` |
| Default Phantom Timeframes (1m to 1w, 1d) | Names the one timeframe the wizard ticks. One at or below the bot's own, or one the venue lacks, stays clear and its box says why. With Enable on and no box ticked, the bot runs one phantom on the next timeframe the venue offers, and none where it offers none higher. Reads `default_phantom_timeframe`. `src/gui/bot_wizard.py, in PhantomConfigPage._timeframe_refusal`, `src/trading/phantom_balance.py, in default_phantom_timeframes` |
| Lock duration (candles) (1 to 10, 2) | Opens the wizard's Candles to lock. Nothing creates a lock, so nothing uses it. Reads `default_lock_candle_count`. `src/trading/phantom_balance.py, in TimeframeCoordinator` |

### Settings > Theme

![Settings, the Theme page.](p40-i0.png)

The figure shows a Font Settings group the page does not draw, and #00ffcc in Accent Color, where the drawn box opens empty.

| Row | What it does and what it reads |
| --- | --- |
| Visual Theme (five themes, Cyberpunk Dark) | Picks Cyberpunk Dark, Neon Light, Classic Terminal, Minimal Modern or Glass & Metal. Save repaints the Qt window and the chrome colours of each open React page. The Theme menu writes the same setting. A stored name no theme holds opens on Cyberpunk Dark, and a Save writes that name over it. Reads `theme`. `src/gui/main_window.py, in MainWindow._switch_theme`, `src/gui/main_window.py, in MainWindow._remember_theme` |
| Accent Color (text, empty) | A hex colour of three or six digits replaces the accent on Qt parts and the chart, and empty keeps the theme's own. React pages keep the theme's own either way. Other text is refused, and so is a colour under 4.5 to 1 against the theme's ground. The log names a refusal. Reads `accent_color`. `src/gui/theme_engine.py, in accented`, `src/gui/react_history_panel.py, in _palette` |

#### The Simulator's tone, nigredo

On the Sim tab, Qt windows move each theme's seven ground colours a quarter of the way to black. The accent, the text, the borders and the chart colours stay the theme's, so a Sim screen reads as the same theme, darker (`src/gui/theme_engine.py, in nigredo`).

The React Sim page darkens its two page grounds and the design system's grounds by the same share (`src/gui/simulator/sim_react_trading_tab.py, in nigredo_design`). No control sets the tone.

### Settings > Logging

![Settings, the Logging page.](p41-i0.png)

The window draws no Logging page, and no row in Settings sets logging.

### Settings > Sound

![Settings, the Sound page.](p42-i0.png)

Each box reaches the sound engine the moment you tick it, before Save (`src/gui/settings_dialog.py, in SettingsDialog._push_sound_config`). Save keeps the page. Cancel writes nothing, and the engine holds your tick until the window next opens or the app restarts.

These clips play on Windows alone, and each clip cuts off the one before, so a FOLD fill ends on the drip (`src/core/sound_engine.py, in SoundEngine.play`). The Market Inspector chime has no switch here (`src/gui/market_inspector.py, in MarketInspectorTab._chime_for`).

| Row | What it does and what it reads |
| --- | --- |
| Enable sound notifications (on) | The master switch. Off silences every clip on this page. Reads `enabled`. `src/core/sound_engine.py, in SoundEngine.play` |
| Buy order fills (on) | Plays a rising tone on a buy fill. Reads `buy_sound`. `src/gui/main_tabs/main_window_surface.py, in trade_filled_sounds` |
| Sell order fills (on) | Plays a bell tone on a sell fill. Reads `sell_sound`. `src/gui/main_tabs/main_window_surface.py, in trade_filled_sounds` |
| Errors (on) | Plays an alert tone when Start or Restart fails, and on a critical risk alert. Reads `error_sound`. `src/gui/main_window.py, in MainWindow._on_bot_command` |
| Bot state changes (on) | Plays a click when Start, Pause, Stop, Restart or Delete works on one bot, when a bot is built, when Apply changes a running bot, and when a venue connection drops. Pause All and Stop All on the Live tab play nothing. On the Paper tab each plays this click. Reads `bot_state_sound`. `src/gui/main_window.py, in MainWindow._on_bot_command`, `src/gui/main_window.py, in MainWindow._global_bot_cmd`, `src/gui/paper/paper_trading_tab.py, in PaperTradingTab._global_bot_cmd`, `src/gui/paper/paper_react_trading_tab.py, in PaperTradingTabReact._global_bot_cmd` |
| Scrum/Fold Fire (on) | Plays a rifle shot on a SCRUM, FOLD or DIST fill, and on a Manual Fire press. Reads `fire_sound`. `src/gui/main_window.py, in MainWindow._on_bot_fire` |
| Tracking beeps (on) | Beeps once per two-second refresh for the hottest Scrumming bot of the active asset class, running or paused, in TRACK or FIRE. SEARCH and a bot the hard breaker holds stay silent, and the rate does not rise in FIRE. Reads `track_sound`. `src/gui/main_window.py, in MainWindow._dispatch_tracking_beep` |
| P/L increase (on) | Plays coins when a fill reports a profit above zero. The growth a cartridge, Manual Fire or manual tranche fire reports reads each tranche's sale price less its wire share. Reads `profit_sound`. `src/gui/main_tabs/main_window_surface.py, in trade_filled_sounds`, `src/trading/scrumming/sizing.py, in discharge_gain_usd`, `src/trading/scrumming_bot.py, in ScrummingBot._book_manual_tranche_fill` |
| Accumulation (on) | Plays a water drip on a FOLD fill. Reads `drip_sound`. `src/gui/main_tabs/main_window_surface.py, in trade_filled_sounds` |
| SFX Volume (0 to 100%, 70%) | Sets the loudness of every clip. A move reaches the engine at once, and the engine remakes each clip at that level. Reads `volume`. `src/core/sound_engine.py, in SoundEngine.update_config` |
| Test Buy, Test Sell, Test Fire, Test Track, Test Profit, Test Drip | Each hands the engine the page's boxes, then plays its clip. The master box and that clip's own box still apply. `src/gui/settings_dialog.py, in SettingsDialog._test_sound` |

### Settings > SMS

![Settings, the SMS page.](p43-i0.png)

The figure shows Twilio API picked, with no Twilio rows and no Mail rows. The page opens on Email-to-SMS Gateway and draws every row below, for both providers.

Save hands the page to the message engine at once. A message goes only while the master box and that event's box are ticked, and a message inside a rate limit is dropped (`src/core/sms_engine.py, in SMSEngine.send`).

Alerts add their own waits: 10 seconds a side on fills, 60 seconds on a connection change, one hour on P/L and ten minutes on a critical risk alert (`src/core/notifications.py, in NotificationManager.DEFAULT_RULES`).

| Row | What it does and what it reads |
| --- | --- |
| Enable SMS notifications (off) | The master switch. Off sends nothing. Reads `enabled`. `src/core/sms_engine.py, in SMSEngine.send` |
| Provider (Email-to-SMS Gateway or Twilio API, Email-to-SMS Gateway) | Picks how messages go. Reads `provider`. `src/core/sms_engine.py, in SMSEngine.send` |
| Phone Number (text, empty) | The number Twilio sends to, and the number Carrier builds the gateway address from. Reads `phone_number`. `src/core/sms_engine.py, in SMSEngine._send_twilio` |
| Twilio Account SID (text, empty) | Your Twilio account. Reads `twilio_sid`. `src/core/sms_engine.py, in SMSEngine._send_twilio` |
| Twilio Auth Token (hidden, empty) | Your Twilio token. Reads `twilio_auth_token`. `src/core/sms_engine.py, in SMSEngine._send_twilio` |
| Twilio From Number (text, empty) | The Twilio number messages come from. Reads `twilio_from_number`. `src/core/sms_engine.py, in SMSEngine._send_twilio` |
| Carrier (ten carriers, AT&T) | A pick fills Gateway Email from a ten-digit number, or eleven with a leading 1, so type the number first. AT&T shows at the start, so to use it pick another carrier and return, or type Gateway Email yourself. Other (Manual) leaves that row as it is. Reads `carrier`. `src/core/sms_engine.py, in gateway_address`, `src/gui/settings_dialog.py, in SettingsDialog._fill_gateway_email` |
| Gateway Email (text, empty) | The address the email route sends to. The route sends nothing while it is empty. Reads `gateway_email`. `src/core/sms_engine.py, in SMSEngine._send_email_gateway` |
| SMTP Username (text, empty) | The email account that sends. The route sends nothing while it is empty. Reads `smtp_username`. `src/core/sms_engine.py, in SMSEngine._send_email_gateway` |
| SMTP Password (hidden, empty) | That account's app password. Reads `smtp_password`. `src/core/sms_engine.py, in SMSEngine._send_email_gateway` |
| Mail Server (text, smtp.gmail.com) | The outgoing mail server. Reads `smtp_server`. `src/core/sms_engine.py, in SMSEngine._send_email_gateway` |
| Mail Port (1 to 65535, 587) | The outgoing mail port. Reads `smtp_port`. `src/core/sms_engine.py, in SMSEngine._send_email_gateway` |
| Buy fills (on) | Sends a message when a buy fills. Reads `notify_buy_fills`. `src/core/notifications.py, in NotificationManager._on_trade_filled` |
| Sell fills (on) | Sends a message when a sell fills. Reads `notify_sell_fills`. `src/core/notifications.py, in NotificationManager._on_trade_filled` |
| Bot state changes (start/stop/error) (on) | Nothing raises a bot start, stop, error or risk-pause alert, so this box sends no message. Reads `notify_bot_state_changes`. `src/core/notifications.py, in EVENT_MESSAGE_KIND` |
| API errors and failures (on) | No alert event reaches this box, so it sends no message. Reads `notify_errors`. `src/core/notifications.py, in EVENT_MESSAGE_KIND` |
| P/L threshold alerts (off) | Sends a message when realised profit passes a new multiple of P/L threshold, at most one an hour, and a multiple passed inside that hour never sends. A critical risk alert sends too. Reads `notify_pl_threshold`. `src/core/notifications.py, in NotificationManager.check_pnl_milestone` |
| P/L threshold ($1 to $100,000, $100) | Sets that multiple. Reads `pl_threshold_amount`. `src/core/notifications.py, in NotificationManager._pnl_threshold` |
| Low balance warnings (off) | No alert event reaches this box, so it sends no message. Reads `notify_balance_warning`. `src/core/notifications.py, in EVENT_MESSAGE_KIND` |
| Exchange connection status (off) | Sends a message when a venue connection drops and when it returns. Reads `notify_connection_status`. `src/exchange/ccxt_connector.py, in _alert_venue` |
| Max messages per hour (1 to 100, 20) | The most messages sent in one hour. Reads `max_messages_per_hour`. `src/core/sms_engine.py, in SMSEngine.send` |
| Min time between messages (5 to 300 sec, 30) | The shortest wait between two messages. Reads `cooldown_seconds`. `src/core/sms_engine.py, in SMSEngine.send` |

### Settings > AI Monitor

![Settings, the AI Monitor page.](p44-i0.png)

The figure stops above the Connection Status group.

The monitor runs only with its Enable box ticked and an API key stored. Save rebuilds it at once (`src/trading/bot_container.py, in BotManager.configure_live_monitor`).

A review sends the fleet total and the bot count. Its trade lines read zero, because nothing writes the monitor's journal (`src/trading/live_monitor.py, in LiveMonitor.analyze`).

| Row | What it does and what it reads |
| --- | --- |
| Anthropic API Key (hidden, empty) | The key the monitor calls Claude with. Reads `api_key`. `src/trading/live_monitor.py, in LiveMonitor._call` |
| Check interval (0.5 to 24 hours, 4) | Hours between two reviews. The first falls due at once, and each Save makes one due. A failed handshake or a call that raises is asked again each two seconds. An error reply with no text counts as a passing review. Reads `interval_hours`. `src/trading/live_monitor.py, in LiveMonitor.should_check`, `src/trading/live_monitor.py, in LiveMonitor.analyze` |
| Connect phrase (text, empty) | The phrase the prompt carries. Empty uses the built-in phrase. Reads `connect_phrase`. `src/trading/live_monitor.py, in LiveMonitor.__init__` |
| Confirm phrase (text, empty) | The reply must be this phrase alone to pass the handshake. Empty uses the built-in phrase. Reads `confirm_phrase`. `src/trading/live_monitor.py, in LiveMonitor.handshake` |
| Enable AI Monitor feedback loop (off) | Turns the monitor on. Reads `enabled`. `src/trading/bot_container.py, in BotManager.configure_live_monitor` |
| Auto-handshake on first analysis (on) | Stored as `auto_handshake`, and nothing reads it. The monitor always shakes hands before its first review. `src/trading/live_monitor.py, in LiveMonitor.analyze` |
| Log AI feedback to trade journal (on) | Writes nothing. The window misses each answer, because the answer arrives one level down. Reads `log_feedback`. `src/gui/main_window.py, in MainWindow._on_ai_feedback`, `src/trading/bot_container.py, in BotManager.check_live_monitor` |
| Status | Reads Not connected. Only Test Handshake writes it. The status bar's AI label reads the settings: a passing review turns it to UNAUTH, and a failed handshake leaves it on READY. `src/gui/main_window.py, in MainWindow._draw_ai_monitor_pill` |
| Journal hash | Shows a dash. Nothing writes it. `src/gui/settings_dialog.py, in SettingsDialog._create_ai_monitor_tab` |
| Checks completed | Shows 0. Nothing writes it. `src/gui/settings_dialog.py, in SettingsDialog._create_ai_monitor_tab` |
| Test Handshake | Calls nothing. It checks that the key and both phrases are filled, then writes one line to Status, and that line says Settings saved though no Save has run. `src/gui/settings_dialog.py, in SettingsDialog._test_ai_handshake` |
