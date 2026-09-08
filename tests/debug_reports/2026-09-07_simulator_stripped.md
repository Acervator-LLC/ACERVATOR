# The Simulator is removed; the Sim tab draws an empty panel

The Sim tab built a whole Simulator: a fleet replay panel, a practice venue, a
stat strip, two chart panels and Nuclear Mode. All of it is gone. The tab keeps
its name, its first place on the bar and its black ground, and draws the same
empty panel the Paper, Status and Accumulation tabs draw.

Every run used a throwaway home. **`~/.acervator/settings.json` did not hash the
same before and after**, and the live application is what wrote it:

```
before  f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
after   2b1946b9560593d7e437805a62e9770a5aed28af0827251bb84c0125862abc7e
```

The file holds one key, `privacy_mask`, and its 19 fields are the privacy
toggles the running window sets. Eighteen read True and `bot_table.bot_id`
reads False, so a toggle moved. Four measurements say the writer was not this
work:

```
two Acervator-...-react.exe processes, started 2026-09-05, before this branch
the file's mtime is 17:09 local, and it carries no key but privacy_mask
tests/conftest.py points ACERVATOR_SETTINGS_ROOT at a throwaway root for the
    whole session, so no pytest run here can reach that path
the debugger runs set HOME and USERPROFILE to a scratch directory, and those
    directories hold no .acervator at all afterwards, only a GPU shader cache
```

The runs' own log lines name `.../u117_home_qt/.acervator/bot_state.json` as
not found, which is the redirect taking effect on a read.

No authenticated call, no credential, no order placed, and the running
Acervator process was never started, attached to or queried. `~/.acervator/`,
`~/.acervator_logs/` and `~/.acervator_ra_tablets/` were read only.

## Reproduce

The window was built and every tab in the bar was opened in turn, under both
variants, before and after. The runs used `python -X dev -X faulthandler`, the
offscreen platform, software rendering for the web views, and a throwaway home
directory.

```
MainWindow(None, None) built, then setCurrentIndex over every tab
ACERVATOR_VARIANT=qt      resolve_variant answered qt
ACERVATOR_VARIANT=react   resolve_variant answered react
QTWEBENGINE_CHROMIUM_FLAGS  --disable-gpu --disable-gpu-compositing
```

Qt's own message handler was installed with `qInstallMessageHandler` and every
message it emitted is quoted below. The before reading came from the same
worktree at `origin/current`, driven the same way.

## Every tab, before and after

Ten tabs opened in both runs, in the operator's order, with no error.

| tab | before, qt | after, qt | before, react | after, react |
| --- | --- | --- | --- | --- |
| Sim | `SimulatorTab`, 453 children | `EmptyTabQtPanel`, 4 | `SimulatorTab`, 318 | `EmptyTabReactPanel`, 1 |
| Paper | `EmptyTabQtPanel`, 4 | `EmptyTabQtPanel`, 4 | `EmptyTabReactPanel`, 1 | `EmptyTabReactPanel`, 1 |
| Live | `QWidget`, 196 | `QWidget`, 196 | `QWidget`, 196 | `QWidget`, 196 |
| Charts | `TradeChartsTab`, 11 | `TradeChartsTab`, 11 | `TradeChartsTab`, 11 | `TradeChartsTab`, 11 |
| Inspector | `MarketInspectorTab`, 95 | `MarketInspectorTab`, 95 | `MarketInspectorReactTab`, 5 | `MarketInspectorReactTab`, 5 |
| Swarm | `BotVisualizationTab`, 189 | `BotVisualizationTab`, 189 | `BotSwarmReactTab`, 5 | `BotSwarmReactTab`, 5 |
| Accumulation | `EmptyTabQtPanel`, 4 | `EmptyTabQtPanel`, 4 | `EmptyTabReactPanel`, 1 | `EmptyTabReactPanel`, 1 |
| History | `HistoryTab`, 109 | `HistoryTab`, 109 | `HistoryReactTab`, 5 | `HistoryReactTab`, 5 |
| Status | `EmptyTabQtPanel`, 4 | `EmptyTabQtPanel`, 4 | `EmptyTabReactPanel`, 1 | `EmptyTabReactPanel`, 1 |
| Console | `ConsoleQtTab`, 35 | `ConsoleQtTab`, 35 | `ConsoleReactTab`, 6 | `ConsoleReactTab`, 6 |

The bar reads the same in all four runs, and it is `CANONICAL_TAB_ORDER`:

```
Sim  Paper  Live  Charts  Inspector  Swarm  Accumulation  History  Status  Console
```

Nine of the ten tabs are unchanged. Only the Sim tab's class changed, and only
its child count moved.

## The Sim tab drawing its empty panel

Qt draws three labels, read off the live widgets after the tab was raised:

```
empty-tab-heading  'Sim'
empty-tab-state    'This tab is not built.'
empty-tab-issue    'Issue #117 carries the build-out.'
```

React draws the same three sentences. The text was read back out of the loaded
page with `toPlainText`, not off a picture:

```
SIM PAGE READY True
SIM PAGE TEXT   'Sim This tab is not built. Issue #117 carries the build-out.'
```

**The control for that reading is the Paper tab**, which is the same class fed a
different model and was not touched by this change. Reading Paper first and Sim
second:

```
PAPER PAGE TEXT 'Paper This tab is not built. Issue #19 carries the build-out.'
SIM PAGE TEXT   ''            second panel in the pass, page never settled
```

Reading Sim first and Paper second reverses that exactly. Whichever panel is
read first reports its own words, so the instrument reads the panel it is
pointed at and tells the two apart; the empty second reading is the driver
settling one web view per pass, not a fact about either tab.

## The error the debugger found, and the correction

The first run after the deletion did not draw the React Sim tab. `page_ready`
stayed False. Raising the panel outside the tab book made the program throw
where the tab book had swallowed it:

```
File "src/gui/react_empty_tab.py", line 176, in build_panel
    self._web.setHtml(panel_html(self._model))
File "src/gui/react_history_panel.py", line 87, in read_asset
    raise HistoryPanelAssetMissing(...)
HistoryPanelAssetMissing: History panel asset not readable:
    src\gui\web\simulator_tab.js (FileNotFoundError)
```

The cause is in `react_empty_tab.module_name`: an empty tab draws the renderer
module its own bridge method names, so `simulator_tab.state` asks for
`simulator_tab.js`. Deleting the Simulator's page deleted the file the Sim tab
now needs.

The correction gives the Sim tab the empty-tab renderer the other three already
have. `src/gui/web/simulator_tab.js` is now the Paper tab's module with three
names swapped, and the swap round-trips: reversing them returns the Paper file
byte for byte.

```
// The Sim tab's empty state, as the Python surface serves it.
var METHOD = "simulator_tab.state";
```

`desktop/renderer/module_manifest.js` names it beside the other three. It is not
in `desktop/renderer/index.html`, because an empty-tab module is inlined into
its own page rather than loaded by the shell.

After the correction the same run reports `SIM PAGE READY True` and the three
sentences above.

## What Qt reported

One message in every run, before and after, both variants:

```
QtWarningMsg  QFontDatabase: Cannot find font directory .../PySide6/lib/fonts.
              Note that Qt no longer ships fonts.
```

That is a fact about this machine, not about the product. Nothing else was
emitted, and `ERRORS 0` in all four runs.

The React runs end with a Chromium teardown crash after the work is done:

```
DONE                                    every tab opened, ERRORS 0
Windows fatal exception: access violation
Current thread [CrBrowserMain]: <no Python frame>
```

It fires after the last line the program prints, in the browser process, with no
Python frame. It reproduces identically at `origin/current` with the Simulator
still in place, so it is not caused by this change. The Qt runs exit 0.

## What was removed

103 files deleted outright, carrying 59,214 lines. Across the whole branch,
**63,048 lines are removed**; the difference is the two files that shrank in
place rather than going.

| area | files | lines |
| --- | --- | --- |
| `src/simulator/fleet/` | 7 | the replay controller, the practice venue, the tape reader, the clock |
| `src/simulator/` nuclear | 5 | both controllers, the noise source, the venue, the cache filler |
| `src/gui/simulator_tab/` | 7 | the tab, the fleet panel, the charts, the stat strip, Nuclear Mode |
| `src/gui/main_tabs/` | 5 | four surfaces and the tab mixin |
| `src/gui/react_*` | 4 | the four React panels |
| `src/gui/web/` | 8 | four scripts and four sheets |
| `src/trading/` | 4 | the run log, the validation guard, the verifier, the stress driver |
| `tests/` | 63 | 35,096 lines |
| **source total** | **40** | **24,118** |

Two files shrank in place instead of going, so they are not in that count:

```
src/gui/web/simulator_tab.js               1,767 lines -> 88   the empty-tab renderer
src/gui/main_tabs/simulator_tab_surface.py 1,580 lines -> 30   the empty-state model
```

Two neighbours survived untouched, as the issue requires:

```
src/simulator/portfolios.py          35 portfolios, 63 symbols
src/trading/stone_tablets/           ra_paths, ra_fetcher, ra_import, the package
```

Neither had to move. `portfolios.py` is the only module left under
`src/simulator/`, and `ra_import.py` still imports from it.

## The importers, found before the delete and fixed after

**Twenty-three files named a removed module and were repaired**; 63 further test
files were deleted with the code they pinned. Every one was found by resolving
the import, not by reading a list.

| file | what it named | what it does now |
| --- | --- | --- |
| `src/gui/main_window.py` | the Simulator mixin, in its bases | builds the Sim tab through `EmptyTabsMixin` |
| `src/gui/main_window.py` | `set_async_loop` forwarding to the tab | stores the loop and nothing else |
| `src/gui/main_tabs/empty_tabs.py` | three surfaces | four, with `_build_simulator_tab` |
| `src/gui/main_tabs/simulator_tab_surface.py` | the whole Simulator screen | the tab's empty state, same shape as Paper |
| `src/gui/main_tabs/history_tab.py` | the fleet panel's refresh slot | no Simulator wire |
| `src/gui/variant_surface.py` | five screens, ten loaders | none; the five registrations are gone |
| `src/core/desktop_bridge.py` | four surfaces and their handlers | none of the four |
| `src/trading/gate_vocabulary.py` | the Simulator's gate cell, in prose | names only the History table |
| `src/trading/stone_tablets/parity_harness.py` | `FleetSimExchange`, in prose | names `src.exchange.base.Trade` |
| `desktop/renderer/index.html` | five scripts | none |
| `desktop/renderer/module_manifest.js` | five modules | one, the empty-tab renderer |
| `tests/conftest.py` | the sim run log's root variable | the fixture is gone with the writer |
| `tests/test_desktop_panel_host.py` | the Simulator's own bridge request | the empty-tab default |
| `tests/test_canonical_tab_order.py` | the Simulator mixin and a stub for it | runs the shipped empty-tab builder |
| `tests/test_voting_panel_fits_its_pane.py` | the Simulator tab, to reach the panel | the panel directly, 8 tests pass |
| `tests/test_qt_colour_order.py` | two removed surfaces, two colour sites | the sites that remain |
| `tests/test_atomic_write_site_equivalence.py` | the sim state writer, one site of ten | nine sites, 31 tests pass |
| `tests/test_react_pages_carry_the_style_source.py` | two removed React pages | the page that remains |
| `tests/test_history_tab_keeps_every_control.py` | the History-to-Simulator wire | the wire is gone with it |
| `tests/test_bus_injection_isolation.py` | the Nuclear controller's source | the class is gone |
| `tests/test_relocated_modules_keep_their_repo_root.py` | two removed modules' path maths | the two tests are gone |
| `tests/test_suite_integrity.py` | a Simulator method check that now skips | the test is gone |
| `tests/test_web_module_lock.py` | two removed test modules | the rows are gone |

Nothing else in the tree resolved to a removed module. `pytest --collect-only`
over the whole suite collected **39,936 tests with no collection error**, which
is the check that no import anywhere is dangling.

## The registry entries that fail on a click, not on an import

Four of those are entries rather than imports, and none would have raised until
the operator opened something.

```
variant_surface     five register() calls, each holding a Qt and a React loader
desktop_bridge      four METHOD -> view_model rows the renderer calls by name
index.html          five <script src=...> lines the shell loads at startup
module_manifest.js  five module names the panel host waits for
```

`test_desktop_panel_host` caught the fifth: the Simulator asked its backend with
`{"reset": True, "panel": {"gate": True}, "nuclear": True}` and the empty tab
asks with `{}`. That row is gone from the test's request table.

## The search for the removed names

Every tracked file outside `docs/`, `dev_harness/` and the archived changelogs
was read and matched against 27 removed names.

```
TRACKED FILES SEARCHED             1067
REMOVED NAMES FOUND                   0
CONTROL, NAMES THAT STILL EXIST     234
```

The control is the same search over `BotStatusTable`, `IndicatorVotingPanel` and
`EmptyTabQtPanel`, which are all still in the tree. It returns 234 hits, so the
search reads files and reports matches; the zero above is a fact about the tree.

The names searched for:

```
FleetReplayController  FleetReplayPanel   FleetSimExchange
NuclearModePanel       NuclearController  NuclearFleetController
NuclearSimExchange     SimStatStrip       SimPriceVwapChart
GateStatusPanel        SimRunLog          SimValidationGuard
SimulatorTabMixin      SwarmFeatureVerifier
load_bot_configs_from_state   noised_series   run_topology_stress
src.simulator.fleet    src.gui.simulator_tab
react_sim_visuals      react_sim_stat_strip
react_nuclear_mode_panel   react_fleet_replay_panel
sim_visuals_surface    sim_stat_strip_surface
nuclear_mode_panel_surface   fleet_replay_panel_surface
```

The names remain in `ACERVATOR_HOP5.md` and in the archived changelogs under
`docs-archive/`, which are records of what happened and are not read by the
running program.

## What the manual says now

`docs/manual/08-tabs.md` and `docs/manual/08-tabs/simulator.md` each gained a
section saying the Simulator is removed, what the Sim tab draws, and that the
rest of the page is the record of the screen the rebuild replaces.

Every manual file is additions only:

```
docs/manual/08-tabs.md                          +22  -0
docs/manual/08-tabs/simulator.md                +44  -0
docs/manual/05-novel-concepts.md                 +1  -0
docs/manual/08-tabs/portfolio-panels.md          +1  -0
docs/manual/08-tabs/promotion-pipeline.md        +2  -0
docs/manual/11-hop-protocol-and-rules-registry.md +1 -0
docs/manual/12-adr-index-and-glossary.md         +1  -0
docs/manual/13-live-evidence.md                  +3  -0
```

Most of those additions are one sentence saying a cited file is not in the tree.
`tests/test_no_missing_file_references.py` fails a page that names a path with
no file behind it, and excuses a block that says so in words. Adding the
sentence keeps the guard honest without touching a sentence the operator wrote.

**Three of those dead citations were already dead before this branch.** Two
engineering notes name `tests/test_ta_engine_degenerate_abstention.py` and
`tests/test_indicator_numeric_identity.py`, deleted by commits `7980403` and
`0544936`. They carry the same absence sentence now.

**Stale manual sentences that describe the removed screen are left as they
are**, byte for byte, and the added sections say so.

## The tests, measured against the same run on `origin/current`

The tests that import the changed modules are 87 files. They were run serially,
with no `-n`, once on this branch and once on a second worktree at
`origin/current`, with the same file list and the same command.

```
this branch        17 failed   16,456 passed   44 skipped   705s
origin/current     17 failed   16,453 passed   44 skipped   706s
```

**The two failure lists are the same 17 tests, in the same 8 files.** Every one
is present before this branch exists, so none is caused by removing the
Simulator. They are the class the repository already bans: each reads the source
of the code under test and pattern-matches it.

```
test_bot_status_table_surface_parity.py     3
test_exchange_tab_surface_parity.py         6
test_header_strip_surface_parity.py         1
test_history_tab_keeps_every_control.py     1   repaired here
test_table_cells_surface_parity.py          1
test_theme_engine_surface_parity.py         2
test_trading_tab_surface_parity.py          1
test_visualizer_themes_surface_parity.py    1
test_wire_canvas_surface_parity.py          1
```

**One of the 17 is in a file this unit already touched, and it is repaired.**
`test_refreshes_on_tab_open` read `main_window.py` as text, sliced it between two
`def` lines, and asserted the literal `if tab_name == "History":` appeared. The
shipped handler has never spelled that; it reads `if tab_name == HISTORY_TAB:`.
The slice is 1,231 characters and byte-identical on both branches, and the
assertion is False on both.

It is now four tests that run the shipped `_on_main_tab_changed` against a stub
History tab and count the `refresh` calls:

```
History opened, last fetch at 0.0        refresh called 1 time
History opened, last fetch just now      refresh called 0 times
History opened, a fetch already running  refresh called 0 times
Console opened, History stale            refresh called 0 times
```

The first case is the positive control for the other three: it proves the stub's
`refresh` is reachable and counted, so a zero is a reading about the handler
rather than about a dead instrument. The file passes 27 of 27 on its own, up
from 24, and `coding_archetype` reports `passed=True` on it.

**The other 16 are named here and left.** They belong to eight surfaces this
unit does not touch, and repairing a source-shape test means rewriting it as a
behavioural one, which is a unit per surface.

## Verdicts

```
coding_archetype   21 files    passed=True   exit 0   errors []
gui_archetype       7 files    passed=True   exit 0   errors []
docs_archetype     13 pages    passed=True   exit 0   errors []
```

Every tool reported `ok` in each run: ruff, mypy, pyright, bandit, vulture,
semgrep, scaffolding, hallucination, slop and numeric_guard for coding;
gui-static, ruff, bandit, scaffolding and hallucination for GUI; proselint,
vale, structure, scaffolding and hallucination for docs.

The instruments were proved before the runs that matter:

```
coding_archetype  known_good exit 0   known_bad exit 1
gui_archetype     known_good exit 0   known_bad exit 1
docs_archetype    known_good exit 0   known_bad exit 1
```

`README.md` is the one page the docs archetype does not pass. Its two high
findings are `write-good.ThereIs` at line 113 and `write-good.So` at line 201,
both inside the operator's own account of how Acervator came to exist. The same
two findings come back from `origin/current`, so the page was already red before
this branch and this branch's only change to it is one added line at 528.
