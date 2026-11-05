# Settings

This window sets who you are, which venues the app can reach, and how new bots start. It holds nine pages above one Cancel button and one Save button.

This page is for lookup. Each row names one control, gives its range and start value, says what it does and what reads it, and cites the code behind it.

## The pages

| Page | What it sets |
| --- | --- |
| User | Your name and the Fleet Lock password. |
| Exchanges | Each venue's keys, for the asset class active when the window opened. |
| Trading | Where a new bot's wizard opens: target, order visibility and aggressive mode. |
| TA Indicators | How far each of the twelve indicator votes counts. |
| Phantom Bots | Where a new bot's phantom choices open. |
| Theme | The colour theme and the accent colour. |
| Sound | Which events play a sound, and how loud. |
| SMS | Text message alerts: how they go, which events send them, and how often. |
| AI Monitor | The API key, the handshake phrases and the monitor's behaviour. |

Only the Exchanges page changes with the asset class. The title reads Settings — Crypto Wing on the Crypto class and Settings on every other class (`src/gui/settings_dialog.py, in SettingsDialog.__init__`).

### How the window opens

| Route | What opens and what follows |
| --- | --- |
| File > Settings | Opens on the User page. A Save reaches the running window at once. An exchange you add or remove here changes its tab at the next launch. `src/gui/main_window.py, in MainWindow._open_settings` |
| Exchange > Add Exchange | Opens on the Exchanges page, and the exchange tabs follow when the window closes. A Save here writes every page, and the running window takes the theme, weights, SMS and AI Monitor at the next launch or the next Save from File > Settings. `src/gui/main_window.py, in MainWindow._add_exchange` |
| Start on a broker with no stored key | Opens on the User page, for the bot's asset class. Start tries again when the window closes. `src/gui/main_window.py, in MainWindow._ask_for_venue_connection` |

### Two builds of this window

A frozen build draws the variant stamped into it. A source run reads `ACERVATOR_VARIANT` and draws React when nothing names a variant (`src/_variant.py, in resolve_variant`).

The React window inherits every handler of the Qt window, so both run the same code (`src/gui/react_settings_dialog.py, in SettingsDialogReact`). Two rows differ, API Key and API Secret on the Exchanges page, and each says how.

## What each page persists

Save writes the settings file in your home folder. The Exchanges page writes at each press instead. The store refuses a key it does not declare and a value of the wrong type (`src/core/settings.py, in SettingsManager.set`).

| Page | Stored as | Takes effect |
| --- | --- | --- |
| User | `username` | At Save. Fleet Lock writes its own key file. |
| Exchanges | `exchanges` | At each press, with no Save. |
| Trading | `default_target_balance`, `bot_visibility`, `aggressive_trading` | At the next bot wizard. |
| TA Indicators | `ta_indicator_weights` | At Save, on every bot. |
| Phantom Bots | `default_enable_phantoms`, `default_phantom_timeframe`, `default_lock_candle_count` | At the next bot wizard. |
| Theme | `theme`, `accent_color` | At Save. |
| Sound | `sound` | At each tick, and Save keeps it. |
| SMS | `message_channels` | At Save. |
| AI Monitor | `ai_monitor` | At Save. |

| Control | What it does and what it reads |
| --- | --- |
| Page tabs | Move between pages. Edits stay held on every page until Save or Cancel. Each tab's mouse-over says what the page holds. `src/gui/main_tabs/settings_dialog_surface.py, in TAB_TOOLTIPS` |
| Save | Asks the Username and Fleet Lock questions first, then writes every page and closes the window. A group the store refuses opens a box that names it, and the rest still save. `src/gui/settings_dialog.py, in SettingsDialog._save` |
| Cancel | Closes the window and writes nothing. A Sound box you ticked has already reached the engine. `src/gui/settings_dialog.py, in SettingsDialog._setup_ui` |
| A dash in a box | Marks a stored value the control cannot hold. A drop-down says so in its mouse-over instead. Save keeps the stored value until you set another. `src/gui/settings_dialog.py, in SettingsDialog._mark_refused` |

## How to use each page

The first column of each table gives the row's range and start value. Nine of the ten figures show an earlier capture, so their tab row lists Profit Folding or Logging pages the window does not draw. The Phantom Bots figure matches the drawn page.

### Settings > User Tab

This needs to be built out to accept and contain individual end user credentials. This will also be where a license is entered or a keyfile is imported depending on how we design the authentication piece.

Now: this page holds the Username row and the Fleet Lock group, venue keys go on the Exchanges page, and no license or keyfile row exists (`src/gui/settings_dialog.py, in SettingsDialog._create_user_tab`).

![Settings, the User page.](p34-i1.png)

The figure shows the Username row alone. The drawn page adds the Fleet Lock group under it.

| Row | What it does and what it reads |
| --- | --- |
| Username (text, empty) | Names you, and seals stored venue keys while no Fleet Lock password is set. A change over stored keys asks Yes or No at Save. Yes reseals them under the new name, and No puts the old name back. Reads `username`. `src/gui/settings_dialog.py, in SettingsDialog._settle_username_rename` |
| Fleet Lock state line | Says whether a password is set, read off the key file. A set password seals the saved fleet and the stored keys, and a launch starts no bot until you give it. `src/gui/settings_dialog.py, in SettingsDialog._show_fleet_lock_state` |
| Password (hidden, empty) | Sets a lock, or changes one this run has opened. Both rows empty changes nothing. Save asks Yes or No first, because nothing can recover a lost password. `src/gui/main_tabs/settings_dialog_surface.py, in fleet_lock_intent` |
| Confirm Password (hidden, empty) | Must match Password, or Save takes neither and logs why. It greys while Clear the lock is pressed in. `src/gui/main_tabs/settings_dialog_surface.py, in fleet_lock_intent` |
| Unlock the fleet now | Opens the unlock screen, which loads the sealed fleet. It works only while a lock is set and this run has not opened it. `src/gui/fleet_unlock_dialog.py, in ask_for_unlock` |
| Clear the lock | Stays pressed in until Save. Save needs the current password in the Password row and asks Yes or No. Yes writes the saved fleet back as plain text, reseals stored keys under your Username and deletes the key file. The question on screen says the keys are lost, and the code keeps them. `src/gui/settings_dialog.py, in SettingsDialog._clear_fleet_lock` |

### Settings > Exchanges

![Settings, the Exchanges page.](p35-i0.png)

The figure shows a drop-down and a list of stored exchanges. The drawn page puts the Exchange Status buttons in their place.

| Row | What it does and what it reads |
| --- | --- |
| Stock banner | Stock class only. It names the brokers the app builds a connector for, and says how each signs in. `src/gui/main_tabs/settings_dialog_surface.py, in stock_banner_text` |
| Exchange Status buttons | One button per venue the class serves, 16 to a page and four across. A stored venue no class lists follows in amber. A press binds the form below, and the mouse-over names the venue's state. A redraw reads a file and calls no venue. `src/gui/main_tabs/settings_dialog_surface.py, in exchange_status_page` |
| Button colour | Green: the venue answered an authenticated call. Red: the connection was lost. Grey: never asked, the venue refused a key, or a key whose shape alone was checked. Amber: stored, and listed under no class. `src/gui/main_tabs/settings_dialog_surface.py, in VENUE_STATE_WORDS` |
| Page button | Shows past 16 venues. A press moves to the next page, and the last wraps to the first. `src/gui/main_tabs/settings_dialog_surface.py, in venue_pages_button` |
| Exchange row | Names the pressed venue, and you cannot type in it. `src/gui/main_tabs/settings_dialog_surface.py, in chosen_venue_text` |
| API Key (text, empty) | The venue's key, or a Coinbase key name. The React build hides what you type, and the Qt build shows it. `src/gui/settings_dialog.py, in SettingsDialog._create_exchange_tab` |
| API Secret (text, empty) | The venue's secret or private key. Escaped newlines in a pasted PEM key turn into real ones. The React build hides what you type, and the Qt build shows it. `src/gui/settings_dialog.py, in SettingsDialog._typed_secret` |
| This exchange uses an API passphrase (off) | Shows the passphrase row. A press on a venue that needs one ticks it for you. `src/gui/settings_dialog.py, in SettingsDialog._on_exchange_changed` |
| Passphrase (hidden, empty) | The passphrase set on the API key. Test refuses a venue that needs one when this row is empty. `src/exchange/api_validator.py, in validate_credentials` |
| Verification Code (hidden, empty) | Shows for a venue that grants access only on a pasted code. The first Add press returns an address. Open it, approve, paste the code and press Add again. The code is used once and never stored. `src/gui/main_tabs/settings_dialog_surface.py, in connect_verification_code_venue` |
| Test Connection | Checks the typed key and secret and shows the balances. It stores no key, and it colours the button by the venue's answer. A hand-written connector checks the key's shape alone and asks no venue. It greys for a venue with no check path, and it refuses with no venue pressed or a blank row. `src/gui/settings_dialog.py, in SettingsDialog._test_api_connection` |
| Test and Add Exchange | A typed key on a venue Test can check must pass first, or nothing is stored. A venue with no check path stores the key unchecked. Blank rows add the venue with no key. Keys are stored encrypted. It then shows Exchange Added and closes the window. `src/gui/settings_dialog.py, in SettingsDialog._add_exchange` |
| Connect with a Browser | Replaces Test and Add for a venue that signs in at a browser, on the classes that sign in that way. The key rows hide. Approve at the venue's page, and the feedback line names its trade-approval setting. `src/gui/settings_dialog.py, in SettingsDialog._connect_browser_venue` |
| Feedback line | Shows the last answer: blue for a note, green for success, amber for a warning and red for an error. `src/gui/settings_dialog.py, in SettingsDialog._set_feedback` |
| Remove Selected | Removes the pressed venue's stored entry and its colour at once, with no Save. It refuses while a bot on that venue is neither idle nor stopped, and names each bot. `src/gui/settings_dialog.py, in SettingsDialog._remove_exchange` |

### Settings > Trading

![Settings, the Trading page.](p36-i0.png)

The figure shows Position Distance, Increment Style and Default Positions rows the page does not draw.

Each row sets where a bot wizard opens. A running bot keeps its own value.

| Row | What it does and what it reads |
| --- | --- |
| Default Target Balance ($1 to $1,000,000, $200) | Opens the wizard's Target Balance. Reads `default_target_balance`. `src/gui/bot_wizard.py, in _show_stored_target` |
| Bot Visibility (orderbook or internal, orderbook) | Opens the wizard's Order Visibility. Reads `bot_visibility`. `src/gui/bot_wizard.py, in TradingParamsPage` |
| Enable aggressive trading mode (off) | Opens the wizard's Aggressive Trading. The engine changes only Stack tranches in Order Book mode, which go out as immediate-or-cancel limits. The mouse-over claims more. Reads `aggressive_trading`. `src/trading/scrumming_bot.py, in ScrummingBot._open_stack_from_scrum` |

### Settings > TA Indicators

![Settings, the TA Indicators page.](p38-i0.png)

Each slider runs 0.00 to 2.00 and sets how far that indicator's vote counts. Save hands all twelve to every bot at once, and each bot reads them from its next tick (`src/trading/bot_container.py, in BotManager.push_ta_weights`). Reads `ta_indicator_weights`.

A new Scrumming bot from the Live wizard starts at twelve zeros and votes neutral until the next Save on this window (`src/gui/main_tabs/bot_wizard_surface.py, in with_new_bot_weights`). A running phantom keeps the figures its set was built with (`src/trading/scrumming_bot.py, in ScrummingBot.set_ta_weights`).

A bot's first-entry check and a Paper run vote at the start figures, whatever these sliders hold (`src/trading/scrumming/tick_phases.py, in TickPhaseMixin._tick_initial_entry`, `src/paper/paper_run.py, in PaperRunner.__init__`).

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

[07-indicators.md](../07-indicators.md) holds the indicator formulae.

### Settings > Phantom Bots

![Settings, the Phantom Bots page.](p39-i0.png)

Each row sets where a bot wizard's phantom choices open.

| Row | What it does and what it reads |
| --- | --- |
| Enable Phantom Bots for Scrumming (on) | Opens the wizard's Enable Phantom Bots box. Reads `default_enable_phantoms`. `src/gui/bot_wizard.py, in PhantomConfigPage` |
| Default Phantom Timeframes (1m to 1w, 1d) | Names the one timeframe the wizard ticks. One at or below the bot's own, or one the venue lacks, stays clear and its box says why. Reads `default_phantom_timeframe`. `src/gui/bot_wizard.py, in PhantomConfigPage._timeframe_refusal` |
| Lock duration (candles) (1 to 10, 2) | Opens the wizard's Candles to lock. Nothing creates a lock, so nothing uses it. Reads `default_lock_candle_count`. `src/trading/phantom_balance.py, in TimeframeCoordinator` |

### Settings > Theme

![Settings, the Theme page.](p40-i0.png)

The figure shows a Font Settings group the page does not draw.

| Row | What it does and what it reads |
| --- | --- |
| Visual Theme (five themes, Cyberpunk Dark) | Picks Cyberpunk Dark, Neon Light, Classic Terminal, Minimal Modern or Glass & Metal. Save repaints the Qt window and the chrome colours of each open React page. The Theme menu writes the same setting. A stored name no theme holds opens on Cyberpunk Dark. Reads `theme`. `src/gui/main_window.py, in MainWindow._switch_theme` |
| Accent Color (text, empty) | A hex colour of three or six digits replaces the theme's accent, and empty keeps the theme's own. Other text is refused, and so is a colour under 4.5 to 1 against the theme's ground. The log names a refusal. Reads `accent_color`. `src/gui/theme_engine.py, in accented` |

#### The Simulator's tone, nigredo

The Sim tab paints each theme's seven ground colours a quarter of the way to black. The accent, the text, the borders and the chart colours stay the theme's, so a Sim screen reads as the same theme, darker. No control sets it (`src/gui/theme_engine.py, in nigredo`).

### Settings > Logging

![Settings, the Logging page.](p41-i0.png)

The window draws no Logging page, and no row in Settings sets logging.

### Settings > Sound

![Settings, the Sound page.](p42-i0.png)

Each box reaches the sound engine the moment you tick it, before Save (`src/gui/settings_dialog.py, in SettingsDialog._push_sound_config`). Save keeps the page. Cancel writes nothing, and the engine holds your tick until the window next opens or the app restarts.

Sound plays on Windows alone. On other systems the boxes change nothing you can hear (`src/core/sound_engine.py, in SoundEngine.play`).

| Row | What it does and what it reads |
| --- | --- |
| Enable sound notifications (on) | The master switch. Off silences every sound. Reads `enabled`. `src/core/sound_engine.py, in SoundEngine.play` |
| Buy order fills (on) | Plays a rising tone on a buy fill. Reads `buy_sound`. `src/gui/main_tabs/main_window_surface.py, in trade_filled_sounds` |
| Sell order fills (on) | Plays a bell tone on a sell fill. Reads `sell_sound`. `src/gui/main_tabs/main_window_surface.py, in trade_filled_sounds` |
| Errors (on) | Plays an alert tone when a bot command fails, and on a critical risk alert. Reads `error_sound`. `src/gui/main_window.py, in MainWindow._on_bot_command` |
| Bot state changes (on) | Plays a click when a bot starts, pauses, stops or is built, when Apply changes a running bot, and when a venue connection drops. Reads `bot_state_sound`. `src/core/notifications.py, in NotificationManager._send_sound` |
| Scrum/Fold Fire (on) | Plays a rifle shot on a SCRUM, FOLD or DIST fill, and on a Manual Fire press. Reads `fire_sound`. `src/gui/main_window.py, in MainWindow._on_bot_fire` |
| Tracking beeps (on) | Beeps for the hottest running or paused bot: each 0.8 seconds in TRACK and each 0.2 seconds in FIRE. SEARCH stays silent. Reads `track_sound`. `src/gui/main_window.py, in MainWindow._dispatch_tracking_beep` |
| P/L increase (on) | Plays coins when a fill reports a profit above zero. The growth a cartridge, Manual Fire or manual tranche fire reports reads each tranche's sale price less its wire share. Reads `profit_sound`. `src/trading/scrumming/sizing.py, in discharge_gain_usd` |
| Accumulation (on) | Plays a water drip on a FOLD fill. Reads `drip_sound`. `src/gui/main_tabs/main_window_surface.py, in trade_filled_sounds` |
| SFX Volume (0 to 100%, 70%) | Sets the loudness of every clip. A move reaches the engine at once, and the engine remakes each clip at that level. Reads `volume`. `src/core/sound_engine.py, in SoundEngine.update_config` |
| Test Buy, Test Sell, Test Fire, Test Track, Test Profit, Test Drip | Each hands the engine the page's boxes, then plays its clip. The master box and that clip's own box still apply. `src/gui/settings_dialog.py, in SettingsDialog._test_sound` |

### Settings > SMS

![Settings, the SMS page.](p43-i0.png)

The figure shows the page's top half and no Twilio rows. The drawn page holds every row below, for both providers.

Save hands the page to the message engine at once. A message goes only while the master box and that event's box are ticked and the rate limits allow it (`src/core/sms_engine.py, in SMSEngine.send`).

| Row | What it does and what it reads |
| --- | --- |
| Enable SMS notifications (off) | The master switch. Off sends nothing. Reads `enabled`. `src/core/sms_engine.py, in SMSEngine.send` |
| Provider (Email-to-SMS Gateway or Twilio API, Email-to-SMS Gateway) | Picks how messages go. Reads `provider`. `src/core/sms_engine.py, in SMSEngine.send` |
| Phone Number (text, empty) | The number Twilio sends to, and the number Carrier builds the gateway address from. Reads `phone_number`. `src/core/sms_engine.py, in SMSEngine._send_twilio` |
| Twilio Account SID (text, empty) | Your Twilio account. Reads `twilio_sid`. `src/core/sms_engine.py, in SMSEngine._send_twilio` |
| Twilio Auth Token (hidden, empty) | Your Twilio token. Reads `twilio_auth_token`. `src/core/sms_engine.py, in SMSEngine._send_twilio` |
| Twilio From Number (text, empty) | The Twilio number messages come from. Reads `twilio_from_number`. `src/core/sms_engine.py, in SMSEngine._send_twilio` |
| Carrier (ten carriers, AT&T) | A pick fills Gateway Email from a ten-digit number, or eleven with a leading 1. Other (Manual) leaves that row as it is. Reads `carrier`. `src/core/sms_engine.py, in gateway_address` |
| Gateway Email (text, empty) | The address the email route sends to. The route sends nothing while it is empty. Reads `gateway_email`. `src/core/sms_engine.py, in SMSEngine._send_email_gateway` |
| SMTP Username (text, empty) | The email account that sends. The route sends nothing while it is empty. Reads `smtp_username`. `src/core/sms_engine.py, in SMSEngine._send_email_gateway` |
| SMTP Password (hidden, empty) | That account's app password. Reads `smtp_password`. `src/core/sms_engine.py, in SMSEngine._send_email_gateway` |
| Mail Server (text, smtp.gmail.com) | The outgoing mail server. Reads `smtp_server`. `src/core/sms_engine.py, in SMSEngine._send_email_gateway` |
| Mail Port (1 to 65535, 587) | The outgoing mail port. Reads `smtp_port`. `src/core/sms_engine.py, in SMSEngine._send_email_gateway` |
| Buy fills (on) | Sends a message when a buy fills. Reads `notify_buy_fills`. `src/core/notifications.py, in NotificationManager._on_trade_filled` |
| Sell fills (on) | Sends a message when a sell fills. Reads `notify_sell_fills`. `src/core/notifications.py, in NotificationManager._on_trade_filled` |
| Bot state changes (start/stop/error) (on) | Nothing raises a bot start, stop, error or risk-pause alert, so this box sends no message. Reads `notify_bot_state_changes`. `src/core/notifications.py, in EVENT_MESSAGE_KIND` |
| API errors and failures (on) | No alert event reaches this box, so it sends no message. Reads `notify_errors`. `src/core/notifications.py, in EVENT_MESSAGE_KIND` |
| P/L threshold alerts (off) | Sends a message at each new multiple of P/L threshold in realised profit, and on a critical risk alert. Reads `notify_pl_threshold`. `src/core/notifications.py, in NotificationManager.check_pnl_milestone` |
| P/L threshold ($1 to $100,000, $100) | Sets that multiple. Reads `pl_threshold_amount`. `src/core/notifications.py, in NotificationManager._pnl_threshold` |
| Low balance warnings (off) | No alert event reaches this box, so it sends no message. Reads `notify_balance_warning`. `src/core/notifications.py, in EVENT_MESSAGE_KIND` |
| Exchange connection status (off) | Sends a message when a venue connection drops and when it returns. Reads `notify_connection_status`. `src/exchange/ccxt_connector.py, in _alert_venue` |
| Max messages per hour (1 to 100, 20) | The most messages sent in one hour. Reads `max_messages_per_hour`. `src/core/sms_engine.py, in SMSEngine.send` |
| Min time between messages (5 to 300 sec, 30) | The shortest wait between two messages. Reads `cooldown_seconds`. `src/core/sms_engine.py, in SMSEngine.send` |

### Settings > AI Monitor

![Settings, the AI Monitor page.](p44-i0.png)

The figure stops above the Connection Status group.

The monitor runs only with its Enable box ticked and an API key stored. Save rebuilds it at once (`src/trading/bot_container.py, in BotManager.configure_live_monitor`).

| Row | What it does and what it reads |
| --- | --- |
| Anthropic API Key (hidden, empty) | The key the monitor calls Claude with. Reads `api_key`. `src/trading/live_monitor.py, in LiveMonitor._call` |
| Check interval (0.5 to 24 hours, 4) | Hours between two reviews. The first review falls due at once. Reads `interval_hours`. `src/trading/live_monitor.py, in LiveMonitor.should_check` |
| Connect phrase (text, empty) | The phrase the prompt carries. Empty uses the built-in phrase. Reads `connect_phrase`. `src/trading/live_monitor.py, in LiveMonitor.__init__` |
| Confirm phrase (text, empty) | The phrase the reply must carry to pass the handshake. Empty uses the built-in phrase. Reads `confirm_phrase`. `src/trading/live_monitor.py, in LiveMonitor.handshake` |
| Enable AI Monitor feedback loop (off) | Turns the monitor on. Reads `enabled`. `src/trading/bot_container.py, in BotManager.configure_live_monitor` |
| Auto-handshake on first analysis (on) | Stored, and nothing reads it. The monitor always shakes hands before its first review. Reads `auto_handshake`. `src/trading/live_monitor.py, in LiveMonitor.analyze` |
| Log AI feedback to trade journal (on) | Writes each answer into the trade journal. Reads `log_feedback`. `src/gui/main_window.py, in MainWindow._on_ai_feedback` |
| Status | Reads Not connected. Only Test Handshake writes it. The status bar's AI label shows the monitor's real state. `src/gui/main_window.py, in MainWindow._draw_ai_monitor_pill` |
| Journal hash | Shows a dash. Nothing writes it. `src/gui/settings_dialog.py, in SettingsDialog._create_ai_monitor_tab` |
| Checks completed | Shows 0. Nothing writes it. `src/gui/settings_dialog.py, in SettingsDialog._create_ai_monitor_tab` |
| Test Handshake | Calls nothing. It checks that the key and both phrases are filled, then writes one line to Status, and that line says Settings saved though no Save has run. `src/gui/settings_dialog.py, in SettingsDialog._test_ai_handshake` |
