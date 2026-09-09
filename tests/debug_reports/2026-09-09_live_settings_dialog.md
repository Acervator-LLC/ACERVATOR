# 2026-09-09 — Live Bot Settings: the shell fills the window's tab pages

Issue #128, the eight rows of the conversion table in
[08-tabs.md](../../docs/manual/08-tabs.md) that make the Live Bot Settings
dialog, plus the exchange screen and the Extractor table. Files changed:
`src/gui/web/bot_live_settings.js`, `src/gui/web/bot_live_settings.css`,
`src/gui/main_tabs/bot_live_settings_surface.py` and
`desktop/renderer/index.html`. No test file was written.

The Electron shell ran from `desktop/main.js` under the installed Electron
binary with a throwaway home, and the renderer was read over the Chrome
DevTools Protocol. Every Python run was under `PYTHONWARNINGS=error` with
`python -X dev -X faulthandler`.

```
electron.exe <tree>/desktop --user-data-dir=<scratchpad> --remote-debugging-port=9377
ACERVATOR_BRIDGE_ARGV="-m src.core.desktop_bridge"
```

Pictures, one per tab of the drawn window:

```
<scratchpad>/u128_live_settings/react_status.png
<scratchpad>/u128_live_settings/react_settings.png
<scratchpad>/u128_live_settings/react_fold_tranches.png
<scratchpad>/u128_live_settings/react_stack_tranches.png
<scratchpad>/u128_live_settings/react_phantom_bots.png
```

---

## 1 — `bot_live_settings.py`: the cell said no and the shell said yes

### 1.1 the error

No traceback. The shell was read before any edit and already named the panel.

```
registered  bot_live_settings bot_swarm_tab bot_visualizer console_tab
            header_strip history_tab indicator_panel market_inspector
            market_inspector_tab market_inspector_topologies native_chart
            paper_trader_tab proof_of_accumulation_tab simulator_tab
            spendable_profits status_log system_status_tab trade_charts_tab
            trading_tab
reasonFor('bot_live_settings')   null
kindOf('bot_live_settings')      "screen"
methodOf('bot_live_settings')    null
```

### 1.2 reproduction

`window.acervatorPanelHost.registered()` over the protocol, on the branch point
`06eadf1d`, before any file was touched.

### 1.3 the cause

`bot_live_settings.js` calls `acervatorPanelHost.register` at load. The cell was
measured before that call landed.

### 1.4 the correction

The cell reads `yes`. Nothing was added to the module to make it register.

### 1.5 the rerun

The same list after every change in this report still names the panel, and
`faults()` stays empty.

---

## 2 — `bot_live_settings.py`: seven tab pages, all empty

### 2.1 the error

No traceback. The window drew and every page it drew held nothing.

```
hostElements 28
part                   children  characters
status-page                   0           0
settings-page                 0           0
fold-tranches-page            0           0
stack-tranches-page           0           0
bot-swarm-page                0           0
market-inspector-page         0           0
phantom-bots-page             0           0
control: 681 elements under #panels
```

The control is the element count for the whole panel area, so the zero is a
fact about the pages rather than about the counter.

### 2.2 reproduction

```
acervatorPanelHost.open('bot_live_settings', hostFor(panels, 'bot_live_settings'))
```

### 2.3 the cause

`TabPage` returns an element with no children, and no caller filled it.

```javascript
    return element(DIV_TAG, pageProps, null);
```

Each tab module already exports `fill(root, model)`, whose own comment names
the empty space this window leaves. Nothing called it.

### 2.4 the correction

`renderWindow` mounts the pages after it draws, in the shape `exchange_tab.js`
already uses for its children.

```javascript
    var host = draw(target, element(Window, { key: mark, model: drawn }));
    mountPages(target, drawn);
    return host;
```

### 2.5 the rerun

```
hostElements 222
fold-tranches-page    children 1   characters 979
stack-tranches-page   children 1   characters 494
phantom-bots-page     children 1   characters 898
```

---

## 3 — `bot_live_settings.py`: every page drew at once

### 3.1 the error

No traceback. The saved picture carried the Fold Tranches, Stack Tranches and
Phantom Bots content together, and the picture digest did not move when a
different tab was picked.

```
Status          digest=6d0ebb815f8c
Settings        digest=6d0ebb815f8c
Fold Tranches   digest=6d0ebb815f8c
Stack Tranches  digest=6d0ebb815f8c
Phantom Bots    digest=6d0ebb815f8c
```

### 3.2 reproduction

Click each tab button, then capture the page.

### 3.3 the cause

`TabPage` set `hidden` and also set an inline `display: flex`. An inline
declaration beats the browser's own rule for a hidden element, so the page
stayed on screen. The Qt-hosted page never showed this because its own
stylesheet carries `[hidden] { display: none !important }` and the shell page
did not carry that sheet.

### 3.4 the correction

```javascript
    var style = {
      display: props.current === true ? FLEX : DISPLAY_NONE,
```

### 3.5 the rerun

Five digests, four of them different. Status and Settings share one because
both pages are empty.

```
Status          digest=08fa805250d9
Settings        digest=baf5874449ac
Fold Tranches   digest=74c90d8604ca
Stack Tranches  digest=e438a6b540ba
Phantom Bots    digest=7d1b5ecdeed9
```

The differing digests are the control on the camera: a repeated digest is now a
fact about the page.

---

## 4 — `bot_live_settings.py`: the tabs opened on their own bot

### 4.1 the error

No traceback. Each tab surface builds from the bot named in its request, and
the window's answer named no bot, so a mounted tab would have built a stand-in
of its own.

### 4.2 reproduction

`bot_live_settings.state` answered 143 keys and none of them named the bot.

### 4.3 the cause

`build_view_model` published the title and the header text and nothing the
tabs could read a bot from. Parsing the title in JavaScript would have made the
browser derive a value Python owns.

### 4.4 the correction

The window publishes the bot it holds, and the request name for it.

```python
    config = model.bot.config
    return {
        "bot_id": model.bot.bot_id,
        "symbol": config.symbol,
        "mode": config.mode,
        "state": model.bot.state,
    }
```

A window answering no bot sends no bot key, so a tab builds nothing rather than
building one of its own.

```javascript
    if (isPlainObject(given)) {
      params[String(paramNamed(model, TAB_BOT_PARAM))] = given;
    }
```

### 4.5 the rerun

Read off the drawn pages, fed and then with the bot taken out of the window's
answer.

```
page                  rows  order choices  elements   blinded
fold-tranches-page      11              5        69    0,  5, 33
stack-tranches-page      7              0        33    0,  0, 12
phantom-bots-page        4              0        92    0,  0, 46
```

The first attempt at this control reported no change, because an absent bag
still sent an empty object and the surface built from it. That is what the
guard above corrects.

---

## 5 — `bot_live_settings.py`: the window's stylesheet never reached the shell

### 5.1 the error

No traceback. The tab strip painted as browser-default buttons, black on white.

### 5.2 reproduction

`desktop/renderer/index.html` linked two stylesheets and neither was
`bot_live_settings.css`.

### 5.3 the cause

The sheet is written for a page holding this window alone. Linked as it stood
it restyled other panels: `trading_tab`, `history_tab` and `bot_visualizer` all
moved, because `table`, `th`, `td`, `button:disabled` and `[hidden]` selected
across the whole shell page.

```
trading_tab      5ab316aab9b2 -> dab534ec13bd
bot_visualizer   cfc277ff234f -> f5a6dabee9d6
```

Counted on the shell page with every panel mounted and the window drawn, the
sheet reached these elements belonging to other panels.

```
part            on the page   outside the window
header-row                4                    3
tab-bar                   4                    3
tab-button               12                    5
table                    20                   17
```

Every part the sheet names sits inside the window part when it belongs to this
window, so the scoping reaches all of them and none of the others.

### 5.4 the correction

Every selector is scoped to the window part, and `overflow` moved off `body`
onto the window. On the Qt-hosted page every element these rules select already
sits inside that part, so the scoping changes nothing there.

```css
[data-part="bot-live-settings"] table {
  border-collapse: collapse;
  width: 100%;
}
```

### 5.5 the rerun

Five of the six panels are byte-identical to the run before the link.

```
trading_tab       5ab316aab9b2  same
console_tab       ce1330fd55ae  same
market_inspector  75d943ff354f  same
bot_visualizer    cfc277ff234f  same
trade_charts_tab  4838ef6ba992  same
history_tab       8f531ec59f3c  differs
```

`history_tab` draws something that changes with each process start: two runs
under one stylesheet gave two digests, and two different stylesheets gave one.

---

## 6 — `live_settings/settings_tab.py`: the Settings page cannot be fed

### 6.1 the error

```
AttributeError: 'BotConfigSource' object has no attribute 'visibility'
  live_settings_tab_surface.view_model -> build_view_model -> build
  -> _add_control -> _read_control
```

### 6.2 reproduction

`live_settings_tab.state` asked with the bot the window publishes.

### 6.3 the cause

The tab seeds every control from the bot's own settings values, and reads the
ones marked with no fallback directly. Fifteen of its specs are marked that
way, among them the scrum interval, the fire threshold and the target balance.
The window answers a stand-in bot whose config carries a symbol and a mode and
nothing else.

### 6.4 the correction

None in this unit. Supplying those values from the shell would invent trading
parameters, and giving the window a running bot would also point Apply Changes
at that bot, which changes what a control writes. The page is left unmounted
and the row stays `no`.

### 6.5 the rerun

The Settings page draws nothing and the window records no fault.

---

## 7 — `live_settings/fold_chrome.py`: the row controls were never loaded

### 7.1 the error

No traceback. `fold_tranches_tab.js` keeps a space for the order picker and the
filter box and draws them only while the chrome module reports itself loaded.
Nothing loaded it.

```javascript
    if (!api || !api.RowControls || !api.isLoaded || !api.isLoaded()) {
      return element(DIV_TAG, spaceProps, null);
    }
```

### 7.2 reproduction

`fold_chrome.state` asked with `{reset: true}` answers `control_count` 0.

### 7.3 the cause

The chrome builds its row controls only when the request asks for them, the
same way a tab builds only when the request names a bot.

### 7.4 the correction

The window asks for them before the Fold Tranches page is filled, so the space
finds the module loaded.

```javascript
    params[String(paramNamed(model, FOLD_CHROME_CONTROLS_PARAM))] = true;
```

### 7.5 the rerun

Read off the drawn page: five order choices and one filter box.

```
options  Queue order, Oldest first, Newest first, Largest USD first,
         Smallest USD first
inputs   search, "Filter rows...", ""
```

---

## 8 — `live_settings/fold_tranches_tab.py`, `stack_tranches_tab.py`, `phantom_bots_tab.py`

### 8.1 the error

No traceback. Each is a component of the window and each drew nothing, for the
reason in section 2.

### 8.2 reproduction

Section 2.

### 8.3 the cause

Section 2.

### 8.4 the correction

Section 2. None of the three registers a panel of its own: each fills the page
space the window keeps, and a registration would put an empty shell in a host
of its own.

### 8.5 the rerun

Read off the drawn pages.

```
Fold Tranches   11 health rows, 3 Clear buttons, 5 order choices, 1 filter box
                Open tranches: 0
                Parked USD (in fold queue): $0.0000
                Oldest tranche age: no open tranches
Stack Tranches   7 summary rows, 2 Clear buttons
                Pending tranches: 0
                Fill ratio (filled/opened): —  (no stacks opened yet)
Phantom Bots     4 summary rows, 12 timeframe boxes, 1 number box
                Phantoms enabled: NO
                SCRUM lock state: UNLOCKED — SCRUM allowed
```

---

## 9 — `widgets/exchange_tab.py` and `widgets/extractor_bot_table.py`

### 9.1 the error

No traceback. Neither drew inside the Live tab in the shell.

```
trading_tab children  indicator_panel 48 elements, status_log 2 elements
extractor space       null
```

### 9.2 reproduction

`acervatorMountPanels()`, then read `[data-child-module]` inside the Live tab.

### 9.3 the cause

The exchange screen is drawn into a slot the Live tab keeps for one exchange,
and the Live tab names an exchange only when the backend is the trading program
itself. `trading.tab` served without a live system names none, so no slot
exists and the Extractor table inside the exchange screen is never reached.

### 9.4 the correction

None in this unit. Both are components of the Live tab, not panels of their
own, and their rows stay `no` because their content did not reach the shell
this run.

### 9.5 the rerun

Unchanged: the Live tab draws two children and neither is the exchange screen.

---

## 10 — the Qt side of this window

The window answers the variant switch: `variant_surface` holds it under
`BOT_LIVE_SETTINGS` and returns `BotLiveSettingsDialog` under `qt`. Building it
beside the React one was not possible.

```
AttributeError: 'str' object has no attribute 'value'
  bot_live_settings.py:342  QLabel(f"{cfg.symbol}  •  {cfg.mode.value.upper()}")
```

The Qt window reads a mode and a state carrying `value`, then settings fields
with no fallback. The React side of the same window reads a plain string, so
neither can be driven from the other's stand-in.

```
AttributeError: 'Mode' object has no attribute 'upper'
  bot_live_settings_surface.py:400  header_text
```

Both need a bot the running program holds. No Qt picture was taken and none was
invented.
