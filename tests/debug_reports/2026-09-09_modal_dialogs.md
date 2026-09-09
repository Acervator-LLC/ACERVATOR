# 2026-09-09 — the four modal dialogs: wizard, buy, Settings, Start All

Issue #128, the four rows of the conversion table in
[08-tabs.md](../../docs/manual/08-tabs.md) that are modal dialogs rather than
tab pages. Files changed: `src/gui/web/settings_dialog.js`,
`src/gui/react_settings_dialog.py`, `src/gui/react_start_all_progress.py` and
`src/gui/web/start_all_progress.css`. No test file was written.

Every Python run was under `PYTHONWARNINGS=error` with
`python -X dev -X faulthandler`. The Electron shell ran from `desktop/main.js`
under the installed Electron binary with a throwaway home, and the renderer was
read over the Chrome DevTools Protocol. Both builds of each dialog were built
in one process each and read off the drawn widget tree or the drawn page.

```
electron.exe <tree>/desktop --user-data-dir=<scratchpad> --remote-debugging-port=9412
ACERVATOR_BRIDGE_ARGV="-m src.core.desktop_bridge"
ACERVATOR_VARIANT=qt      python variant_items.py <dialog> qt    <png> <json>
ACERVATOR_VARIANT=react   python variant_items.py <dialog> react <png> <json>
```

The offscreen platform on this host carries no font, so a first picture drew
boxes where every letter belonged. Four faces are added by file before any
dialog is built, and the reports carry the count.

```
font families before addApplicationFont   0
font families after                       4
```

Pictures, under `<scratchpad>/u128_modals/`:

```
qt_bot_wizard.png            react_bot_wizard.png
qt_buy_confirmation.png      react_buy_confirmation.png
qt_settings_dialog.png       react_settings_dialog.png
qt_settings_sound.png        react_settings_sound.png
qt_start_all_progress.png    react_start_all_progress.png
control_settings_dialog.png  control_start_all_progress.png
```

---

## 1 — all four: the shell holds no panel for any of them

### 1.1 the error

No traceback. The shell was read before any edit and named none of the four.

```
manifest names        69
panels registered     19
reasonFor bot_wizard            bot_wizard.js registered no panel to draw
reasonFor buy_confirmation      buy_confirmation.js registered no panel to draw
reasonFor settings_dialog       settings_dialog.js registered no panel to draw
reasonFor start_all_progress    start_all_progress.js registered no panel to draw
faults []   module load errors []
```

All four modules load: `acervatorBotWizard`, `acervatorBuyConfirmation`,
`acervatorSettingsDialog` and `acervatorStartAllProgress` are all on the page.

### 1.2 reproduction

`window.acervatorPanelHost.registered()` and `reasonFor` over the protocol, on
the branch point `26170a4a`, before any file was touched.

### 1.3 the cause

None of the four calls `acervatorPanelHost.register`. Each is drawn by a host
that builds a page of its own: `BuyConfirmationReactDialog`,
`SettingsDialogReact` and `StartAllProgressReactDialog` are Qt windows with one
browser view, and the wizard is filled into a space `exchange_tab.js` keeps.

### 1.4 the correction

None. Each was registered by hand and opened, with the request each dialog is
opened with in the running program, to see what a registration would give.

```
name                  open  elements  characters  loadError
bot_wizard            true        27         906  null
buy_confirmation      true        29         254  null
settings_dialog       true       431        2465  null
start_all_progress    true        10         390  null
```

All four draw, so none of them is an empty shell. They are still not panels:
nothing in the shell opens them, and the shell page carries no stylesheet for
any of them, so the wizard drew with the browser's own button chrome. The four
cells take the dash the table uses for a module that does not register in its
own right, and the shipped tree registers nothing new.

The first attempt at this measurement was wrong and is recorded here because it
reads like a product fault and is not one. `buy_confirmation.js` takes the host
element first and the request second, and it was wired as if it took the
request alone.

```
Panel buy_confirmation did not draw: the view model never arrived:
Minified React error #299
```

### 1.5 the rerun

The final run on the changed tree reads the same 19 registered panels, the same
four reasons, and no faults.

---

## 2 — `settings_dialog.py`: every tab page drew at once

### 2.1 the error

No traceback. The dialog drew, and it drew all eleven pages stacked.

```
window 700x600   page 700x600
tab-page parts 11
parts outside the window 320
```

The Qt dialog shows one page: the User tab holds `Username:` and nothing else.

### 2.2 reproduction

```
ACERVATOR_VARIANT=react python variant_items.py settings_dialog react ...
```

### 2.3 the cause

`TabPage` marked a page not on show with the `hidden` attribute and gave every
page an inline `display: flex`. An inline declaration beats the browser's own
rule for a hidden element, so every page drew.

```javascript
    one.hidden = !props.current;
```

### 2.4 the correction

The page not on show takes `display: none`, which is what the Live Bot Settings
window already does for its own pages.

```javascript
      display: props.current === true ? FLEX : DISPLAY_NONE,
```

### 2.5 the rerun

```
parts outside the window   before 320   after 0
```

Put back, the count returns to 320, so the change is the draw path.

---

## 3 — `settings_dialog.py`: every drop-down drew one letter a choice

### 3.1 the error

No traceback. Read off the drawn page, each `select` held one letter an option.

```
increment_style   l  l
visibility        o  i
sms_provider      E  T
sms_carrier       A  T  V  S  U  C  B  M  G  O
font_family       S  C  C  C  A  H  R  F  J  S  U  V
```

The payload itself is right: `view_model` carries
`['AT&T', 'T-Mobile', 'Verizon', ...]`.

### 3.2 reproduction

The same run as section 2, reading `select.options` off the page.

### 3.3 the cause

`SettingsDialogReact.redraw` turned every choice into plain data with `list`.
A pair of display name and key becomes a two-item list, which is right; a
choice that is one word becomes its letters.

```python
{**spec, "items": [list(one) for one in combo_items(spec["name"])]}
```

The Electron bridge does not share the fault. `view_model` sends the specs
through `_plain`, which leaves a word alone.

### 3.4 the correction

`plain_combo_item` lists a pair and leaves a word alone.

```python
def plain_combo_item(one: Any) -> Any:
    return list(one) if isinstance(one, (tuple, list)) else one
```

### 3.5 the rerun

```
sms_carrier   AT&T  T-Mobile  Verizon  Sprint  US Cellular  Cricket ...
font_family   Segoe UI  Consolas  Cascadia Code  Courier New  Arial ...
```

---

## 4 — `settings_dialog.py`: tick boxes and number boxes drew no words

### 4.1 the error

No traceback. The page drew 79 form rows and 31 labels, and no tick box carried
its words. Reading the Qt build and the page together, 54 words the widgets
draw were absent from the page.

```
Enable sound notifications      Buy fills          Equal distribution
Fold to ALL buy positions       6.0 hours          $350.00        2.5%
```

### 4.2 reproduction

`compare_items.py qt_settings_dialog.json react_settings_dialog.json`, which
looks for every word one build draws in what the other drew.

### 4.3 the cause

A spec carries `label` for a row heading, `text` for a tick box and `prefix` or
`suffix` for a number. `ControlRow` drew the label only. The other two names
were already declared in the module and used for an attribute, never drawn.

### 4.4 the correction

`sideWords` draws a prefix before the control, a suffix after it, and a tick
box's own words after it.

```javascript
    if (label(held[TEXT_KEY]) !== undefined) {
      drawn.push(sideWords(CHECK_TEXT_PART, props.name, held[TEXT_KEY]));
    }
```

### 4.5 the rerun

```
part            before   after
row-label           31      31
check-text           0      38
value-prefix         0       2
value-suffix         0       6
words the page does not draw   54  ->  16
```

The sixteen that remain are the Qt number box's own reading, which joins the
value and the unit into one word: the page draws `2.5` and `%` as two elements.

---

## 5 — `start_all_progress_dialog.py`: the page did not fit its window

### 5.1 the error

No traceback. Both buttons fell below the window edge.

```
window 520x360   page 548x388   dialog box right 556 bottom 396
parts outside the window 10, including button:cancel and button:close
```

### 5.2 reproduction

```
ACERVATOR_VARIANT=react python variant_items.py start_all_progress react ...
```

### 5.3 the cause

The page carried no stylesheet, so the box is measured without its padding and
the page keeps the browser's own margin. The module asks for the dialog's own
520 by 360 and then adds 14 of padding on each side.

```python
    return page_html((), DIALOG_SCRIPT_ASSETS, DIALOG_BODY, theme, (HOST_SCRIPT,))
```

### 5.4 the correction

`start_all_progress.css` puts the padding and the margin inside the asked size,
which is what the buy confirmation and Settings pages already do. It sets no
colour and no space: those arrive on the element from Python.

```css
* {
  box-sizing: border-box;
}

html,
body {
  height: 100%;
  margin: 0;
  overflow: hidden;
}
```

### 5.5 the rerun

```
window 520x360   page 520x360   parts outside the window 0
```

Put back, the page measures 548 by 388 again and ten parts fall outside, so the
change is the draw path.

---

## 6 — what the two builds draw, item by item

Read off the widget tree for the Qt build and off the drawn page for the React
build, both driven with the same values.

```
dialog               title            words the page misses   pictures
buy confirmation     both the same                        0   both
Start All progress   both the same                        0   both
Settings dialog      both the same                       16   both
```

The buy confirmation draws the same seven detail lines on both builds.

```
Symbol: BTC/USD                            Cost: $250.0000 USD
Price: $62500.00000000                     Amount: 0.004000 BTC
Current holdings: 0.019000 (~$1187.5000)   Target balance: $1200.00
After this buy: $1437.5000
```

The comparison was proved able to report: one detail line changed on the Qt
side alone made the pairing read `DIFF` on that line and `same` on the other
six, and the pairing returned to seven `same` when it was put back.

The Start All progress dialog draws the same headline, the same wrapped
sentence, the same two bot lines, Cancel remaining live and Close dead.

```
Auto-starting 3 bots (1/3 verified, starting ETH-USD-2...)
[OK] BTC-USD-1
[!] ETH-USD-2 (start verify timed out - may still come up)
Cancel remaining  (live)      Close  (dead)
```

The Settings dialog draws the same eleven tab names, the same title, the same
Cancel and Save, and the same nine tick boxes and six test buttons on the Sound
page.

---

## 7 — `settings_dialog.py`: twelve names the module never read

### 7.1 the error

`coding_archetype` refused the file, before and after the changes above, with
twelve findings of the same shape.

```
high  eslint  no-unused-vars  'VALUE' is assigned a value but never used.
high  eslint  no-unused-vars  'CONTROL_ROLE' is assigned a value but never used.
```

### 7.2 reproduction

```
python -m dev_harness.harness.coding_archetype src/gui/web/settings_dialog.js
```

### 7.3 the cause

Twelve names were declared and never read. Each appears exactly once in the
file, on its own declaring line.

### 7.4 the correction

The twelve declarations are gone. Three of the names the archetype listed
before the changes above are now read rather than dropped: `text`, `prefix` and
`suffix` are what section 4 draws.

### 7.5 the rerun

```
coding_archetype src/gui/web/settings_dialog.js   passed=True
```

The dialog draws the same after the removal: 487 elements, 38 tick-box words,
eleven tab pages with one on show.

---

## 8 — `bot_wizard.py`: the walk row is not finished

The wizard draws its title, its six-stop rail, the page it opens on, both mode
choices with the first one picked, and both mode notes. Every one of those
matches the Qt wizard, which also opens on the mode page.

Its walk row does not. The page draws the four step names as words, where the
Qt wizard draws Back, Next, Commit, Finish and Cancel and turns Back and Finish
off on the first page.

```
qt      < &Back (dead)   &Next > (live)   Commit   &Finish (dead)   Cancel
react   next   back   cancel   finish        every one live
```

The payload names the four steps and carries no words and no on-or-off state
for them, so the page has nothing to draw them from. That is a missing source
rather than a drawing fault, and it is left for the unit that adds it.

```python
WALK_STEPS = (WALK_NEXT, WALK_BACK, WALK_CANCEL, WALK_FINISH)
```

The Qt wizard was built with an empty venue list. A venue makes its asset page
fetch that exchange's live market list, so the venue box and the target asset
box are empty on both sides and prove nothing.
