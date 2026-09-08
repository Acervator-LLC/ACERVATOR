# `analytics_tab.py`

322 source lines. The row is **not convertible**. The running program never
imports this file and never builds the `AnalyticsTab` class inside it.

The file paints a performance dashboard. What it draws when it is built by hand
is in
[analytics_tab.png](../../docs/audits/2026-09-06_row_by_row/analytics_tab.png).

## Edits

`docs/audits/2026-09-06_row_by_row/analytics_tab.png` — added. It is the screen
`AnalyticsTab` paints today under Qt, with no analytics source attached.

`docs/manual/08-tabs.md` — unchanged. Every cell of the row was measured, and
every cell already reads what the tree holds. The measurements are below.

The item's issue body — unchanged, and it carries the same nine cells as the
manual.

`src/gui/analytics_tab.py` — unchanged.

## Errors detected

**No program error.** The module was run under the debugger and it finished.

```
python -X dev -X faulthandler -m pdb -c continue -c quit -m src.gui.analytics_tab

The program finished and will be restarted
pdb exit=0
```

The debugger was then put around the construction itself, so it stepped into
`AnalyticsTab.__init__` rather than only the import.

```
> <string>(12)<lambda>()
(Pdb)   ...\lib\bdb.py(956)runcall()
-> res = func(*args, **kwds)
> <string>(12)<lambda>()
(Pdb)
accessibleName: Analytics Tab
children: 107
refresh with no engine returns: None
```

`pdb` reported no traceback and entered no post-mortem frame.
`PYTHONWARNINGS=error` was set for every run, so a warning would have become a
traceback. None appeared.

**Nothing in the application reaches the file.** The walk is the repository's
own `tools.conversion_scope.closure`, which follows a name only where a module
uses it. It was run from each entry point, with `history_tab.py` as a control.

```
main.py                  n=287  analytics_tab=False  history_tab=True
src/gui/main_window.py   n=279  analytics_tab=False  history_tab=True
src/core/desktop_bridge  n=153  analytics_tab=False  history_tab=False
```

The control is reached from two of the three roots, so the walk can report a
file that is reached. `analytics_tab.py` is reached from none.

**Nothing builds the class.** `conversion_scope.built_modules` names the module
that constructs each screen. It names `react_history_tab.py` for the control and
names nothing for this row.

```
history_tab owners:   ['src\gui\react_history_tab.py']
analytics_tab owners: []
```

The reason is in `RetiredTabsMixin._install_retired_tab_sentinels`. That method
assigns `None` to `_analytics_tab` and nothing assigns it again, so the guarded
refresh call in the main window can never run.

**The bridge names this screen.** This is where the row differs from
`splash_screen.py`. `src.core.desktop_bridge` registers
`analytics_tab_surface.view_model`, and that surface describes the same eight
cards, the same ten-column table and the same four-column table as the Qt file.
A count of `1` means the text is in the file and `0` means it is not.

```
                          analytics_tab.py  analytics_tab_surface.py
"Sharpe Ratio"                           1                         1
"Profit Factor"                          2                         2
"Collecting equity data"                 1                         1
"Timeframe Performance"                  1                         1
"The market doesn't sleep"               0                         0
```

The last row is a text known to be in neither file, so the count can report an
absence.

**The React module draws in no shell.** A module draws in the Electron shell
only when it calls `acervatorPanelHost.register`. `market_inspector.js` makes
that call and `analytics_tab.js` makes none, so the shell loads the module and
never mounts a panel from it.

**Three group box titles are painted over.** Measured off the built widget, the
child sits five pixels above the bottom of its own title.

```
                       label bottom   child top   overlap
Equity Curve                     15          10        +5
Bot Performance                  15          10        +5
Timeframe Performance            15          10        +5

control, a plain QGroupBox       15          29       -14
```

The control is the same reader on a group box with no style sheet, and it
reports no overlap. The cause is the style sheet `AnalyticsTab._setup_ui` sets
on each group box: it declares a border and no top padding, so the title keeps
its place while the contents move up to the frame. The clipping is visible in
the image.

**Four colours are written as numbers.** `MiniEquityChart.paintEvent` builds its
gradient from raw red, green and blue values while the line beside it reads
`design_system.SUCCESS` and `design_system.ERROR`. The same method names a font
family as a literal string.

**The coding archetype reports `passed=False`.** One high finding, from
`vulture`, on the file as it stands.

```
coding_archetype src/gui/analytics_tab.py   passed=False   exit 1
  vulture   high   unused variable 'event'
```

Every tool in that run reported `ok` and the run recorded no errors. The finding
sits on the `event` argument of `MiniEquityChart.paintEvent`, which the toolkit
requires and the method does not read.

None of the three defects above was repaired. The application does not reach
this file, and repairing an unreached file makes it load-bearing.

## Resolution

No code changed, so the reruns measure the same file.

`analytics_tab.py` reads no variant name. The search finds `src/_variant.py`,
which does read one, so it can report a reader when one exists.

```
grep -n ACERVATOR_VARIANT src/gui/analytics_tab.py     (no output)
grep -rln ACERVATOR_VARIANT --include=*.py src/        src/_variant.py
```

Both variants were run anyway. Each built the widget and saved the picture, and
the two pictures are the same file.

```
ACERVATOR_VARIANT=qt      exit=0  grabbed 2000 x 1250  sha256 8c04f685...
ACERVATOR_VARIANT=react   exit=0  grabbed 2000 x 1250  sha256 8c04f685...
control, one card value set        grabbed 2000 x 1250  sha256 f12d544a...
```

The control changed one card and the picture changed with it, so two equal
hashes mean the variant name reaches nothing in this screen. The renders were
taken with the platform's own fonts, and the run reported 287 font families.

The file was moved out of the tree, the entry point was imported again, and it
started clean.

```
file present    analytics_tab findable: True   imported main and main_window OK   exit=0
file moved away analytics_tab findable: False  imported main and main_window OK   exit=0
```

The first line is the control. The interpreter can see the module in one run and
cannot see it in the other, so the second run measures a real absence. The file
was put back and `git status` reports it unchanged.

The file stays where it is. The repository map in `CLAUDE.md` gives every folder
one role and names no quarantine folder, so adding one is the operator's call,
not this unit's. Nothing was deleted.

The archetypes report on the two files this row owns:

```
gui_archetype  src/gui/analytics_tab.py       passed=True    exit 0
gui_archetype  src/gui/web/analytics_tab.js   passed=True    exit 0
```

`black` and `flake8` both exit 0 on the Qt file.

The fixture controls were run first. `known_good` exits 0 and `known_bad` exits
1 for the coding, GUI and docs archetypes, so a green from them carries a
meaning.

Every cell of the row was measured and every cell already reads true.

| Cell | Reads | Measured |
| ---- | ----- | -------- |
| React module | `analytics_tab.js` | the file is in `src/gui/web` and serves the same method |
| Uses React | yes | it calls `React.createElement` and `ReactDOM.createRoot` |
| Bridge | yes | `desktop_bridge` registers the surface under `analytics.tab` |
| Manifest | yes | the shell's module list names the file |
| Registers in Electron | no | the module calls no register |
| Ships in the build | yes | the built React bundle carries the file |
| RENDERS | no | Qt never builds the widget and React mounts no panel |
| Scope | shelved | `conversion_scope.verdict` answers shelved |

The second table of the manual already carries the reason for this row, so no
cell and no sentence changed.

The operator sees one new thing today: a picture of a dashboard the application
has never shown him.
