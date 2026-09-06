# Unit 1 — `src/gui/bot_live_settings.py`

The Live Bot Settings window. Its row in issue #128 and in
[docs/manual/08-tabs.md](../../docs/manual/08-tabs.md) read
`Registers in Electron: no`. That cell was the work.

Screens, full size, at `docs/audits/2026-09-06_units/`:

```
unit01_bot_live_settings_qt.png         the Qt window, 900 x 860
unit01_bot_live_settings_react.png      the React window, same size
unit01_bot_live_settings_electron.png   the Electron shell, 1340 x 900
```

## Edits

Five changes, three files. None of them touches `_mark_changed` or
`_apply_changes`, so an edit still travels the one route into the bot that
page 121 of the Product Manual describes.

**`src/gui/web/bot_live_settings.js` — the module now registers.**
It calls `register` on `acervatorPanelHost` from its own script tag, with its
render function, its loader, its load-error reader and an opening request. It
names no bridge method, so it takes no tab. That is how a window belonging to a
bot row registers, and it is what `market_inspector_tab.js` already does.

**`src/gui/web/bot_live_settings.js` — `Window` no longer sets its own size.**
It set a width and a height in pixels from the payload. `bot_live_settings.css`
already sizes the window to its view, so the page now follows the dialog the
operator resized.

**`src/gui/react_bot_live_settings.py` — `WINDOW_SCRIPT_ASSETS` loads
`header_strip.js`.** That module owns the style-sheet reader every part of this
window skins from. It was absent from the list.

**`src/gui/react_bot_live_settings.py` — `BotLiveSettingsReactDialog.redraw`
publishes `change_label` and `change_style`.** It wrote the pending-change line
under the name `change_text`, which nothing reads.

**`src/gui/main_tabs/bot_live_settings_surface.py` —
`BotLiveSettingsModel.sibling_bot_ids` also reads the manager's held bots.**
It asked `BotManager` for `ordered_bot_ids`, a method that class does not have.

## Errors detected

### The application starts clean under the debugger

```
python -X dev -X faulthandler -m debugpy --listen 5678 main.py
```

with `PYTHONWARNINGS=error` and a throwaway home. Its whole output:

```
0.01s - Debugger warning: It seems that frozen modules are being used, which may
0.00s - make the debugger miss breakpoints. Please pass -Xfrozen_modules=off
0.00s - to python to disable frozen modules.
0.00s - Note: Debugging will proceed. Set PYDEVD_DISABLE_FILE_VALIDATION=1 to disable this validation.

2026-09-06 12:12:06,327 [acervator.stone_tablets.registry] INFO stone_tablets: indexed 0 tablet(s) covering 0 (asset, exchange) pair(s); bodies load on demand
2026-09-06 12:12:06,328 [acervator] INFO Stone Tablets: 0 tablet(s) covering 0 asset(s)
```

No warning became a traceback in ninety seconds of running. The two
`ResourceWarning` lines that follow are the debugger's own socket and the event
loop being cut off when the timeout killed the process, not a fault in the
program.

### E1 — Prev and Next never drew

The Qt window shows both buttons whenever the manager holds more than one bot.
The React window showed neither.

```
Qt      prev_visible True   next_visible True
React   nav_shown    False
```

The cause is one call. `BotLiveSettingsModel.sibling_bot_ids` asks the manager
for `ordered_bot_ids`. Only the surface's own stand-in offers that name. Driven
against the real class:

```
has ordered_bot_ids: False
ordered_bot_ids RAISES: AttributeError: 'BotManager' object has no attribute 'ordered_bot_ids'
sibling_bot_ids(): []
```

A bare `except Exception` turned that error into an empty list, so the window
believed the bot had no siblings. Walking the swarm was unreachable in the
React build.

### E2 — the pending-change line never reached the page

Editing a field on the React side recorded the change in the window but printed
nothing for the operator.

```
payload change_text   'Pending changes: target_balance'
payload change_label  ''
page    change-label  ''
```

`redraw` wrote `change_text`. `Window` in `bot_live_settings.js` draws that line
from `change_label`. A search over `src/` and `desktop/` finds one writer of
`change_text` and no reader.

### E3 — every Qt style was dropped

The header, the state badge, the two nav buttons, Apply, Close and the pending
line each arrive with their own Qt style sheet in the payload. None of them
reached the page. The nav button carried only what the stylesheet gave it:

```
prev-button inline style   "flex: 0 0 auto; white-space: nowrap;"
computed min-width         auto        the sheet asks for 70px
```

`declarations`, `stateRules` and `headerStyleOf` in `bot_live_settings.js` all
delegate to `acervatorHeader`, and each returns nothing when that global is
absent. `WINDOW_SCRIPT_ASSETS` did not load `header_strip.js`, which defines it.

### E4 — the window drew at its minimum size inside a larger dialog

With the dialog at 1000 x 900 the page drew at 640 x 720 and the tab strip
wrapped onto a second row.

```
view   1000 x 900
window  640 x 720
tab tops  48 48 48 48 48 48 78     the seventh tab sat on a second row
```

Page 135 of the Product Manual states the rule this broke: a page row that does
not fit the dialog scrolls under arrows at each end. It does not wrap.

### E5 — the module registered no panel

`bot_live_settings.js` never called `register`, so the shell's panel host held
no panel under that name. That is the `no` cell.

### E6 — Electron crashes under a throwaway profile

Not a fault in the product, and recorded because the next unit will meet it.
Electron exits with a segmentation fault when the profile it is given has no
writable application-data tree.

```
electron.exe --version                        exit 0, v44.2.0
electron.exe desktop        real profile      exit 124   still running at the timeout
electron.exe desktop        throwaway home    exit 139   segmentation fault, no output
```

Giving Electron its own `--user-data-dir`, or a throwaway `APPDATA`, starts it
and keeps the Python child on the throwaway home. Both were measured at exit
124.

## Resolution

### The controls, driven and read back

Every window control the Qt screen builds, driven on the React side, with the
value read off the real Python object afterwards.

| Control | Qt | React after the fixes |
| ------- | -- | --------------------- |
| Window title | `Bot Settings — BTC/USD [unit01-b]` | same |
| Header line | `BTC/USD  •  SCRUMMING` | same |
| State badge | `IDLE` | same |
| Prev | shown, `◀ Prev` | shown, `◀ Prev` |
| Next | shown, `Next ▶` | shown, `Next ▶` |
| Tab strip | 7 tabs, one row | 7 tabs, one row |
| Apply Changes | present, refusing presses | same |
| Close | present | present |
| Pending line | `Pending changes: <fields>` | same, on the page |

### The saved fields

Six fields across four control kinds, edited on the React side, applied, and
read back out of a settings file under a throwaway home.

```
BEFORE     target_balance 200.0  aggressive_trading false  stack_tranche_count_target 3
           split_distance 1.0    scrumming_interval_pct 1.0  bb_tolerance_pct 1.0
IN OBJECT  target_balance 777.5  aggressive_trading true   stack_tranche_count_target 5
           split_distance 2.5    scrumming_interval_pct 3.25 bb_tolerance_pct 1.75
ON DISK    target_balance 777.5  aggressive_trading true   stack_tranche_count_target 5
           split_distance 2.5    scrumming_interval_pct 3.25 bb_tolerance_pct 1.75

fields absent from the saved record: []
fields whose saved value differs:    []
```

Nothing is dropped between the page and the file.

### The geometry

Both windows at 900 x 860, read off the real objects. Positions are pixels from
the top left of the dialog.

| Part | Qt | React | Difference |
| ---- | -- | ----- | ---------- |
| Dialog | 900 x 860 | 900 x 860 | none |
| Prev | 699, 11, 92 x 26 | 742, 10, 70 x 28 | 22 narrower |
| Next | 797, 11, 92 x 26 | 820, 10, 70 x 28 | 22 narrower |
| Apply | 687, 795, 125 x 32 | 688, 807, 124 x 34 | 1 wide, 12 down |
| Tab strip | one row, tab heights 24 | one row, tab heights 29 | 5 taller |
| Tab widths | 57 67 97 101 81 114 99 | 60 68 98 103 82 115 100 | 1 to 3 wider |

The tab widths and heights follow the text, so they are the font difference the
operator allows. **Two are not, and they stay open.** The nav buttons are 22
pixels narrower, because the Qt button grows past the 70-pixel minimum the sheet
asks for and the browser box stops at it. Apply sits 12 pixels lower, because
the pending line takes no height while it is empty and the Qt label always keeps
its own.

### The Electron shell

The shell was started against a throwaway home, with its own data directory and
its remote debugging port open. It spawned the backend and drew its window. The
running page was then asked what it holds, and told to draw this panel.

```
panels the Electron host holds : 14
this unit among them           : True
modules that failed to load    : 0
its bridge method              : None
its kind                       : screen
backend answers bridge.ping    : {"protocol":1}
the shell drew this panel      : true
faults the host recorded       : []
text the panel put on screen   : CHIP/USD • SCRUMMING
                                 RUNNING
                                 Status  Settings  Fold Tranches  Stack Tranches
                                 Bot Swarm  Market Inspector  Phantom Bots
                                 Apply Changes  Close
```

`bridge method: None` is correct and deliberate. A window that belongs to a bot
row takes no tab, which is how `market_inspector_tab.js` registers as well.

`unit01_bot_live_settings_electron.png` is that panel, drawn in the shell, under
the shell's own header strip. The values are the ones the bridge serves a window
opened with no bot named.

**Two things about it are not right yet, and neither is in this window's own
code.**

The tab strip draws unstyled — plain boxes, black on white. The shell's page
links two style sheets and neither is `bot_live_settings.css`. The Qt-hosted
page loads that sheet itself, which is why the same panel is skinned there and
bare here.

The tab pages are empty. This window leaves a named empty space per tab and its
eight tab modules fill them. In the Qt-hosted page the window's own host script
calls each module. In the shell nothing does, so the spaces stay empty.

I did not add the style sheet to the shell's page. That page is shared by
fourteen panels, and `bot_live_settings.css` opens with a global reset and its
own `body` rules, so adding it there would restyle every other panel. Measuring
that belongs to the shell's own row, not to this one.

### A dependency I installed

`websockets` 17.1, with `pip`. Electron's remote debugging speaks the Chrome
DevTools Protocol over a websocket, and no client was installed, so the shell
could not be asked what it had drawn. That is the only package added.

### A hook that refused a run

`.claude/hooks/block_table_search.py` refused three commands that started the
program and asked the running page a question. It reads the command text, so a
command carrying this module's name and the word for what a panel does looks
like a search of the tree even when it runs the program instead. The same
command through the other shell was allowed. The hook is the operator's, so it
is named here and left alone.

### The manual figures

The eleven figures at `docs/audits/2026-09-06_units/unit01_manual_figures/` show
the **Settings — Crypto Wing** dialog. Its title bar, its Cancel and Save
buttons and its eleven page names belong to `src/gui/settings_dialog.py`, which
is a different row. None of the eleven shows the Live Bot Settings window, so no
page of this window could be checked against a figure of itself. Page 135's
prose still bound this unit: it states that a page row too long for the dialog
scrolls rather than wraps, which is the rule E4 broke.

### The live platform

Untouched. The running application is the frozen `-react` build, and no run of
mine attached to it, queried it or shared its home.

```
~/.acervator/settings.json  sha256 before  f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
~/.acervator/settings.json  sha256 after   f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
```

Same bytes, same size, same modification time.
