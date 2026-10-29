# What the Build Includes

Reference. What a packaged build of Acervator carries out of the source folder,
the reading that decides it, and what that reading cannot see.

The index is [README.md](README.md). How the build gets its version number, what
each variant ships and how the bundle's own archive is read are in
[09-updates-and-versioning.md](09-updates-and-versioning.md).

## The rule

A module enters the build when the program can reach it from its starting file.
A module nothing can reach stays out, and its source file stays out with it.

The starting file is named once, in `tools/spec_common.py, ENTRY_SCRIPT`, and it
is `main.py`. Nothing else is a starting point. A screen that only another
screen opens is still reached, because the reading follows the chain.

The rule is a reading taken at every build. It is not a list anybody keeps up to
date. Delete a screen and the next build stops carrying it with no edit
anywhere.

## The three readings that make up "reached"

`tools/spec_common.py, in reachable_src_modules` joins three readings.

**One, the import lines.** Every `import` line in the starting file is followed,
then every `import` line in each file that reaches, and so on until no new name
appears. `tools/spec_common.py, in _src_import_names` does the following, and it
reads an import line wherever it sits, at the top of a file or inside a
function.

**Two, the folders on the way.** A module named `src.gui.main_window` needs
`src`, then `src.gui`, before Python can load it. Each of those parent names is
added.

**Three, the names the program builds while it runs.** Three screens ask Python
for a module by a name they assemble from text, so no `import` line names it.
`tools/spec_common.py, in _joined_import_prefixes` finds the text each one joins
onto, by reading the call itself, and
`tools/spec_common.py, in _dynamic_src_names` tries every piece of text in that
file against it. A join that spells a real module is reached. A join that spells
nothing is dropped.

The three screens doing the joining are
`src/gui/react_bot_live_settings.py, in tab_payload`,
`src/gui/paper/paper_react_bot_detail.py, in tab_payload` and
`src/gui/simulator/sim_react_bot_detail.py, in tab_payload`. Each names eight
tab pages in its own table, `MODEL_BY_SURFACE`, so twenty-four modules reach the
build this way.

Anything else stays out. A file reaches the build because something names it,
never because of the folder it sits in.

## What leaves when a module leaves

Three things leave together.

The module is dropped from the forced-import list by
`tools/spec_common.py, in reachable_only`, so the packager is not told to go and
find it.

Its source file is dropped from the copied files by
`tools/spec_common.py, in unreachable_src_files`, which hands the paths to
`tools/spec_common.py, in build_graceful_datas`.

Any outside package that only that module used then has no reader left, so the
packager's own walk never reaches it and it is not carried. One retired screen
took a whole image library out of the product this way.

## The outside packages named outright

`tools/spec_common.py, EXCLUDES` names nine outside packages the build refuses
by name: the old desktop toolkit, the plotting library, the image library, and
six notebook, test and documentation packages. Each one was read against every
import line in the source folder first. A package the product actually uses is
never on that list.

## What the build log says

`tools/spec_common.py, in report_unreachable` prints the count and then every
name the build is leaving out. Both recipes, `Acervator_win.spec` and
`Acervator_mac.spec`, call it before the packager starts, so the names are near
the top of the build output.

```
  [spec] 29 of 498 src modules unreached, left out:
  [spec]   src.core.mini_display
  [spec]   src.core.system_load_oscillator
  ...
```

If a screen the operator wants is on that list, the build log says so before the
build finishes.

## Today's reading

Measured on this tree: the source folder holds **498** modules, **469** of them
reached and **29** not.

The 29, grouped by what they are:

| what it is | modules |
| --- | --- |
| screens no window builds | `src.gui.analytics_tab`, `src.gui.competition_tab`, `src.gui.init_wizard`, `src.gui.launcher`, `src.gui.live_bot_window`, `src.gui.stock_main_window`, `src.gui.testnet_tab`, `src.gui.usb_auth_widget`, `src.gui.journal_tab` |
| React strips nothing draws | `src.gui.react_crypto_news_ticker`, `src.gui.react_simulator_tab`, `src.gui.react_status_log` |
| the equities engine, not wired | `src.stocks.stock_accumulation_bot`, `src.stocks.stock_assets`, `src.stocks.stock_bot`, `src.stocks.tradingview_bridge` |
| trading parts nothing calls | `src.trading.arbitrage`, `src.trading.logo_library`, `src.trading.mr_inspector` |
| tablet record helpers | `src.trading.stone_tablets.addressing`, `src.trading.stone_tablets.parity_harness`, `src.trading.stone_tablets.ra_import` |
| hardware and import helpers | `src.core.mini_display`, `src.core.system_load_oscillator`, `src.core.usb_auth`, `src.exchange.market_data`, `src.exchange.tablet_backend`, `src.exchange.ytd_csv_import` |
| the manual builder's own chart module | `src.design_system` |

Read again once the main window stopped building the analytics engine: the source
folder holds **501** modules, **471** reached and **30** not. The thirtieth is
`src.trading.analytics_engine`, which no reached module imports any more. Its
file stays on disk, and the build leaves it out.

`tools/spec_common.py` — `report_unreachable`, the build log on this tree

```
  [spec] 30 of 501 src modules unreached, left out:
  ...
  [spec]   src.trading.analytics_engine
  ...
```

Two modules read as reached and are worth naming, because an earlier reading had
them wrong. `src.gui.audio_suite` is reached from
`src/gui/market_inspector.py`, which imports it for the chime.
`src.gui.alerts_tab` is reached from `src/gui/variant_surface.py`, which the
live tabs reach. Leaving either one out would break a screen the operator uses.

## What the reading cannot see

The reading is taken from the text of the files, not from a running program. It
can be wrong in one direction, and that direction matters.

A module named from a value the program reads while it runs, from a file or from
a setting, would read as not reached. So would a module that only loads because
some other module happened to touch it first. A wrong answer there costs an
error at the moment the operator opens the screen that needed it.

One thing holds that mistake back. The module list is **subtracted from and
never replaced**, so the packager's own import walk still runs over the real
imports. A name dropped by this reading that any carried file imports is pulled
back in by the packager and ships anyway.

The reading cannot be proved by this repository. Nothing here launches the
packaged application. The proof is the operator's own launch.

## What the reading does not decide

The reading answers one question: can the program reach this module. It does not
answer whether the screen behind the module is finished.

Nothing in the source folder marks a screen finished.
`src/gui/main_tabs/retired_tabs.py, in RetiredTabsMixin` marks a screen the main
window does not build at all. `src/gui/main_tabs/empty_tabs.py, in EmptyTabsMixin`
draws a placeholder for a screen that is not written yet, and nothing calls it.
Neither says that a screen the window *does* build is half built.

So a half-built screen the window builds reads as reached, and it ships. Keeping
it out needs the operator to name which screens are not finished.

In development.
