# 2026-09-09 — the alerts tab and the crypto news strip

Issue #128, the rows for `src/gui/alerts_tab.py` and
`src/gui/crypto_news_ticker.py` in the conversion table in
[08-tabs.md](../../docs/manual/08-tabs.md). Files changed:
`src/core/desktop_bridge.py`, `src/gui/main_tabs/crypto_news_ticker_surface.py`,
`src/gui/react_alerts_tab.py`, `src/gui/web/alerts_tab.js`,
`src/gui/web/alerts_tab.css` and `src/gui/web/exchange_tab.js`. No test file
was written.

`main.py` was not launched. `main.py:812` builds an instance guard whose
`take_ownership` writes into `~/.acervator`, the tree of the process trading
real money on this machine. The Qt side was reached the way the running program
reaches it — `variant_surface.surface_class` for the alerts tab and
`CryptoNewsTicker` for the strip, both under `PYTHONWARNINGS=error` with
`python -X dev -X faulthandler` and `ThemeManager.apply_theme("cyberpunk_dark")`.
The React side ran in the Electron shell from `desktop/main.js` under the
installed Electron binary with a throwaway home, read over the Chrome DevTools
Protocol.

```
electron.exe <tree>/desktop --user-data-dir=<scratchpad> --remote-debugging-port=9427
ACERVATOR_BRIDGE_ARGV=<scratchpad>/u128at/ticker_bridge.py
ACERVATOR_VARIANT=qt      python alerts_variant.py qt    full <png> <json>
ACERVATOR_VARIANT=react   python alerts_variant.py react full <png> <json>
```

Pictures, under `<scratchpad>/u128at/`:

```
qt_u128_alerts_full.png        react_u128_alerts_full.png
qt_u128_alerts_empty.png       react_u128_alerts_empty.png
qt_u128_alerts_broken.png      react_u128_alerts_broken.png
u128_ticker_qt.png             u128_ticker_react.png
u128_ticker_shell_live.png     u128_ticker_shell_broken.png
u128_ticker_qtvariant_react.png
u128_control_registration.png  u128_control_no_start.png
qt_u128_control_alerts.png     react_u128_control_alerts.png
```

The alerts reading: one `NotificationManager`, the process singleton, filled
the way `main_window` fills it — `RiskManager.evaluate` over a three-bot fleet,
its one critical alert forwarded to `AlertEvent.DRAWDOWN_CRITICAL`, then
`check_pnl_milestone(3424.43)`, then one `BOT_ERROR` and one `BOT_STARTED`.
Four notifications, thirteen routing rules. Both builds read that one manager.

The strip reading: one answer from the shipped fetch,
`src.gui.crypto_news_ticker.fetch_all()` over the ten feeds, 43 stories. The
first six of them were given to each side through its own receiver.

The fleet is a stand-in, not the operator's own. `bot_state.json` belongs to a
process trading real money, so it is neither copied nor read here.

---

## 1 — both modules: the shell holds no panel for either

### 1.1 the error

No traceback. The shell was read before any edit. Nineteen panels registered
and neither module was among them.

```
manifest names                        69
panels registered                     19
reasonFor('alerts_tab')               alerts_tab.js registered no panel to draw
reasonFor('crypto_news_ticker')       crypto_news_ticker.js registered no panel to draw
reasonFor('exchange_tab')             exchange_tab.js registered no panel to draw
acervatorModuleErrors.names()         []
typeof acervatorAlertsTab             object
typeof acervatorTicker                object
faults()                              []
tab bar names                         10
```

### 1.2 reproduction

```
window.acervatorPanelHost.registered()
window.acervatorPanelHost.reasonFor('alerts_tab')
window.acervatorPanelHost.reasonFor('crypto_news_ticker')
```

`ELECTRON_RUN_AS_NODE` is set in this session's environment and is inherited by
a child process. With it set the binary starts as Node and the shell dies on
`whenReady` of an undefined `app`. Every reading below comes from a child
started without it.

### 1.3 the cause

Neither module calls `acervatorPanelHost.register`, and neither should.

`alerts_tab.js` is drawn by `AlertsReactTab`, a Qt widget holding one
`QWebEngineView` that builds its own page. `variant_surface` records the pair
under `ALERTS`, so the running build opens one class or the other. Nothing in
the shell opens the tab: the tab bar names ten tabs and this is not one.

`crypto_news_ticker.js` is drawn by `exchange_tab.js`, which keeps a space
named `news-ticker` in the exchange header and fills it once per exchange, the
same way it fills the Scrumming and Extractor tables.

```javascript
    space.setAttribute(CHILD_ATTR, moduleName);
    return api.mount(target);
```

### 1.4 the correction

No registration was added. Both rows take the `-` mark this table already uses
for a column that does not apply, the mark `privacy_dot`, `bot_status_table`
and the four modal dialogs took for the same reason.

Each was registered by hand and opened into a host of its own, to see what a
registration would give.

```
name                  registered  opened  elements  characters  what it drew
alerts_tab                  true    true        54         233  both tables empty
crypto_news_ticker          true    true         2          21  Fetching crypto news
panels registered           19 before, 21 after
faults()                    []
[data-part="ticker"]        2 on the page, for 1 exchange space
```

Both draw, so neither is an empty shell. The alerts tab drew every control and
no row: `panel_host.open` composes the request from `spec.request()`, and no
notification manager reaches it that way. The strip drew its opening line and
no story, for the same reason, and registering it put a second strip on the
page under one name — `panel_host.mount` keeps one host per name, and the
exchange screen needs one strip per exchange.

### 1.5 the rerun

The final run on the changed tree reads the same 19 registered panels, the same
two reasons, and no faults.

---

## 2 — `crypto_news_ticker.py`: the strip was never started, so it never fetched

### 2.1 the error

No traceback. The strip drew in the exchange header and its line never changed.

```
data-child-module   crypto_news_ticker
strip box           148,168 540x19
line text           Fetching crypto news
after 40 s and 4 steps, the same words
```

### 2.2 reproduction

```
ACERVATOR_TICKER_SOURCE=replay python read_ticker.py replay <png> <json>
window.acervatorTabBar.select('trading_tab')
document.querySelector('[data-part="headline"]').textContent
```

### 2.3 the cause

Two things, one on each side of the bridge.

`ExchangeTab.__init__` builds the strip and calls `start()` on it. The exchange
screen asked the backend for the strip's state with an empty request, so
`view_model` built the strip and never started it.

```javascript
    var wait = typeof loader === "function" ? loader({}) : Promise.resolve(null);
```

`CryptoNewsTickerModel` takes its fetch as an argument and `pane_model` built
it with none, so `FetchWorkerModel.run` answered with an empty list even when
asked. Nothing called `run_worker` either.

```python
        stories = self.fetcher() if self.fetcher else []
```

### 2.4 the correction

The exchange screen already reports that it started the strip, so the request
carries that.

```javascript
  function tickerRequest(model) {
    var started = model[NEWS_TICKER_STARTED];
    return typeof started === "number" && started > ZERO ? { start: true } : {};
  }
```

`use_fetch` holds the transport, which `build_registry` hands in, so the
surface still reaches no network of its own. `start_fetch` runs the worker away
from the request, which is where the Qt strip runs it, so the bridge answers at
once and the line keeps its opening words until the answer lands.

```python
    crypto_news_ticker_surface.use_fetch(SafeRequest, safe_urlopen, time.monotonic)
```

### 2.5 the rerun

```
stories fetched     43
line text           [2/43] The Defiant - SEC Crypto Custody Rewrite Enters White House Review
title               The Defiant - click to open in default browser. https://thedefiant.io/...
colour              rgb(207, 230, 255)
walk                [3/43] [4/43] [5/43] [6/43]
```

### 2.6 the control

The request change was taken out and the run repeated. The line stays on its
opening words for the whole run, so the change is the draw path.

```
with    start in the request     [2/43] The Defiant - SEC Crypto Custody Rewrite ...
without start in the request     Fetching crypto news
```

The source was then broken: an opener no feed answers through. The stories fall
away and the strip says so, which is what `CryptoNewsTicker` says for an empty
answer.

```
live      43 stories, 6 places seen, each step moves 1
broken     0 stories, 1 place seen,  each step moves nothing
line       (no crypto news feeds reachable)
```

---

## 3 — `crypto_news_ticker.py`: what the two strips draw

Read off the widget for the Qt build and off the drawn page for the React
build, both driven with the first six stories of one shipped fetch.

```
story count                same    6
story at each place        same    6 of 6, title and tooltip
direction of travel        same    1, 1, 1, 1, 1, 1, 1, 1
words colour               same    #cfe6ff
pointer                    same    hand
accessible name            same    Crypto News Ticker
differences                0
```

Place 6 is followed by place 1 on both sides, so both wrap the same way.

```
[1/6] The Defiant - Revolut Starts EURR Rollout With Bridge as Regulated Issuer
[2/6] The Defiant - SEC Crypto Custody Rewrite Enters White House Review
[3/6] Decrypt - Crypto, Banks Take Clarity Act Lobbying Fight to Senators' Home States
[4/6] Crypto Briefing - World XYZ website goes down after launch traffic overload
[5/6] Crypto Briefing - Trump hints at US-Iran negotiations post-election amid tanker tensions
[6/6] Crypto Briefing - Napoli excludes Noa Lang from squad against Arsenal due to discipline
```

The pairing was proved able to report. Read against the run with the feed
source broken it answers three differences, and the counts move with it.

```
                        both sides drawing   source broken
stories                              6 / 6           6 / 0
places seen                          6 / 6           6 / 1
direction of travel      1,1,1,1,1,1,1,1     none on the React side
differences                              0               3
```

The offscreen platform puts the pointer on the Qt label as it is shown, which
is the strip's own pause. The walk sends the label a Leave first, which is the
strip's own release.

```
paused on show          true
paused after Leave      false
```

### 3.1 what the seam answers

`variant_surface` holds no entry for the strip, so both builds build the Qt
class. That is why the RENDERS cell reads `shell` and not `yes`.

```
ACERVATOR_VARIANT=qt      CryptoNewsTicker
ACERVATOR_VARIANT=react   CryptoNewsTicker
```

### 3.2 the difference that stands

The Qt strip shows a story as soon as the fetch answers, because the worker
reports to it. The page has no such report and shows the answer on its next
15 second step. A push would need the shell to hold the module by name, and the
strip is drawn by its parent instead.

---

## 4 — `alerts_tab.py`: the page painted the group colour on the whole box

### 4.1 the error

No traceback. Read off the drawn page against the drawn widget, five parts
carried the accent where Qt carries the body colour.

```
                        react page   qt widget
routing Event column       #00ffcc     #e0e0f0
routing Priority column    #00ffcc     #e0e0f0
Bot Token:                 #00ffcc     #e0e0f0
Chat ID:                   #00ffcc     #e0e0f0
Phone:                     #00ffcc     #e0e0f0
```

### 4.2 reproduction

```
python alerts_variant.py both full <png> <json>
python compare_alerts.py qt_alerts_full.json react_alerts_full.json
```

### 4.3 the cause

`alerts_tab.py` gives each group box a style sheet carrying `color: #00ffcc`.
Qt paints that on the group's title and leaves the widgets inside it on the
application colour; the table resolves `#e0e0f0`. `Group` put the whole sheet
on the outer element, and a CSS colour cascades to every child.

```javascript
    var style = merged(styleOf(props.sheet), {
```

### 4.4 the correction

The colour goes to the title and the box keeps every other declaration. The
page then had no base colour at all, because it carried no stylesheet, so it
fell back to the browser's black; `alerts_tab.css` gives it the ground and the
words the Qt rule gives every widget.

```javascript
    var sheet = styleOf(props.sheet);
    var painted = sheet[COLOR];
    delete sheet[COLOR];
```

```css
body {
  background: var(--bg);
  color: var(--text);
}
```

`--bg` is `#0a0a0f` and `--text` is `#e0e0f0`, which are the two values the Qt
rule for every widget carries in this theme.

### 4.5 the rerun

```
routing Event column    #e0e0f0    field labels    #e0e0f0
group title colours     same       differences     0
```

### 4.6 the control

Both changes were taken out and the pair read again. Five parts go back to the
accent, so the changes are the draw path.

```
with the changes      differences 0
without them          differences 2, naming the five parts above
```

---

## 5 — `alerts_tab.py`: what the two tabs draw

Read off the widget for the Qt build and off the drawn page for the React
build, both built in one process on one notification manager, so both carry one
set of times.

```
status text                 same    Notifications: Active
unread text                 same    Unread: 4
notes                       same    "", Not configured
group titles                same    Telegram Bot, SMS Alerts, Event Routing, Notification History
group title colours         same
buttons                     same    Test Telegram, Save Configuration, Acknowledge All
field labels                same    Bot Token:, Chat ID:, Phone:
field label colours         same
field placeholders          same
field types                 same    password, text, text
routing columns             same    Event, Priority, In-App, Telegram, Sound
routing row count           same    13
routing cell words          same
routing cell colours        same
history columns             same    Time, Priority, Title, Message, Channels
history row count           same    4
history cell words          same
history cell colours        same
differences                 0
```

The four history rows, newest first, on both sides:

```
12:26:58  low       Bot started: bot-sol-0003  SOL/USD is running                IN_APP
12:26:58  high      Bot error: bot-eth-0002    ETH/USD order rejected by the ve  IN_APP, SOUND
12:26:58  medium    P/L Milestone: $10         Portfolio has reached $3,424.43   IN_APP, TELEGRAM
12:26:58  critical  Risk: critical_drawdown    Portfolio drawdown 120.0% exceed  IN_APP, TELEGRAM, SMS, SOUND
```

Every cell of those four rows draws `#e0e0f0` on both sides, because none of
the four has been acknowledged. The routing table's three channel columns draw
`#00ff88` for Yes and `#555555` for No on both sides, on all thirteen rows.

### 5.1 the empty state

Built with no notification manager, both sides draw no rows and keep their
opening words. The manager was then emptied instead of removed, and both sides
fall the same way, which is what proves the rows came from it.

```
                       rules rows  history rows  unread   png bytes qt / react
manager with 4 alerts          13             4       4      64630 / 61856
manager emptied                 0             0       0      36350 / 23413
no manager at all               0             0       0      36306 / 23379
```

The one line the pairing still reports on the emptied run is the colour of a
routing cell, which the page has no cell to read when the table holds none.

### 5.2 what the seam answers

```
ACERVATOR_VARIANT=qt      AlertsTab
ACERVATOR_VARIANT=react   AlertsReactTab
```

### 5.3 the difference that stands

The Qt tables take their grid lines, their alternating row bands and their
header underline from the application style sheet for every table, not from
this tab, so no payload carries them and the page draws none of the three.

---

## 6 — the archetypes

Run on every file this unit changed, with the fixture control taken first.

```
known_good.py   passed=True    exit 0
known_bad.py    passed=False   exit 1
```
