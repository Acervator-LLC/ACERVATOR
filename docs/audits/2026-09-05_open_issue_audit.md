# Open issue audit, 5 September 2026

Every open issue was read, then checked against the tree as it stands today.
The list held 147 numbers, from 2 to 442, opened between 19 August and today.
Seventeen are closed by this audit. The rest are ranked below by how fast each
one could be resolved.

The repository moved about 400 commits in three weeks. Files were retired, the
Simulator engine moved to its own package, and several defects were repaired
without their issue being closed. That is what this audit corrects.

## What the numbers say

| | count |
|---|---:|
| open at the start | 147 |
| closed as repaired | 13 |
| closed as folded | 4 |
| open after this audit | 130 |
| minutes to resolve | 31 |
| hours to resolve | 33 |
| days to resolve | 53 |
| blocked | 13 |
| issues citing a path that is gone | 23 |
| folds proposed and not yet made | 5 |

## How to read the bands

**Minutes** is a constant, a string, a citation or a declared key. One edit and
one check.

**Hours** is one function or one seam, with a test that fails without the fix.

**Days** is a subsystem, or several files that have to move together.

**Blocked** needs a decision from you, or another issue first.

Within a band the entries that unblock other work come first.

---

## Band 1 — minutes

These are single values. Each one is an edit and a check.

| # | what it is | why it is minutes | the anchor |
|---|---|---|---|
| 416 | Release gate cannot report ready | Three path constants point at deleted folders. The bodies they want exist under `harness_fixtures/` | `dev_harness/harness/check_release_readiness.py` lines 48, 56, 64 |
| 344 | Call timeout shorter than the library timeout | One number. The wrapper waits 25 seconds, the library it backs up waits 30 | `src/exchange/ccxt_connector.py` line 35 against line 325 |
| 408 | Volume floor cannot refuse a market | One boolean. An `or` clause makes any market above zero volume tradeable | `src/trading/volume_guard.py` line 352 |
| 409 | One config key, two defaults | Nine read sites disagree on the fallback. Three use zero, the rest use one | `src/trading/container/config.py` line 83 |
| 424 | Dismissing a topology proposal raises | One key is written that the settings schema does not declare | `src/core/settings.py` |
| 406 | Base class omits a parameter its caller passes | One parameter on one signature | `src/exchange/base.py` against `src/exchange/ccxt_connector.py` |
| 400 | Balance cache is never invalidated | The wrapper is written. Nothing calls it | `src/trading/scrumming_bot.py` |
| 313 | A refused change is drawn as done | The answer is returned and thrown away on one line | `src/gui/main_tabs/phantom_bots_tab_surface.py` line 1159 |
| 290 | A live connector is published as data | Publish the venue name, not the object | `src/gui/main_tabs/market_inspector_surface.py` |
| 272 | A stat card renders its value as markup | One text-format call on one label | `src/gui/widgets/dashboard_stat_card.py` |
| 268 | An error message renders as markup | One text-format call on one label | `src/gui/live_settings/market_inspector_tab.py` |
| 159 | Target BTC rounds a real number to zero | One format branch. Six decimals is the floor | `src/gui/table_cells.py` |
| 201 | Fold Tranches prints units that do not exist | Two cells routed through the reader already used in the same file | `src/gui/live_settings/fold_tokens.py` |
| 202 | A bad counter stops the Bot Settings dialog | One counter routed through the reader used eight lines below it | `src/gui/live_settings/stack_tranches_tab.py` |
| 240 | A stored true becomes a one percent wire | One value routed through the reader already used fifteen times in the file | `src/gui/live_settings/bot_swarm_tab.py` |
| 235 | Six fields destroyed while the window is built | One layout is given two parents | `src/gui/live_bot_window.py` |
| 403 | Five sweep checks cannot fail | Delete five checks that read paths never in this repository | `src/core/version_sweep.py` |
| 420 | Wizard titles show internal identifiers | Five group titles carry a release or memory number | `src/gui/bot_wizard.py` |
| 421 | The Extractor title loses its ampersand | One character doubled | `src/gui/bot_wizard.py` |
| 417 | The log names seven indicators, the engine builds twelve | One string | `src/trading/ta_engine.py` |
| 430 | The Vortex tooltip names the wrong colour | One string. The chart paints cyan, the tooltip says green | `src/gui/native_chart.py` |
| 435 | Start All states a pause the engine does not take | The screen says 2.5 seconds, the engine waits 0.6 | `src/trading/bot_container.py` |
| 426 | The wing toggle names a Paper Trader that is absent | Two log lines and their two mirrors | `src/gui/main_window.py` |
| 422 | The Paper Swarm tab promises live paper trading | One description string | `src/gui/main_tabs/bot_visualizer_surface.py` line 1672 |
| 428 | Counter tooltips describe the wrong total | Two strings. They follow issue 429 | `src/gui/main_tabs/header_strip.py` |
| 432 | The candle-count control reaches one detector | One literal replaced by the config value | `src/trading/indicators/landing_strip.py` |
| 438 | The Extractor prints a cost basis as a cap | One label on one printed number | `src/trading/extractor_bot.py` |
| 44 | A comment cites a line that moved | One citation survives of the nine, in a test docstring | `tests/test_c39g_bot_log_reaches_disk.py` line 14 |
| 93 | A test name carries a version | One file name, and one formatter rule naming a folder that is gone | `tests/test_indicator_panel_v3_23_50.py` |
| 146 | A test fixture leaks a stub | One restore line. Only the module table is put back | `tests/test_bot_visualizer_b0_red.py` |
| 440 | A former contributor's name is in the tree | Two mentions in one file | `ACERVATOR_HOP8.md` |

Issue 416 comes first. Until those three constants point at bodies that exist,
the release gate cannot report ready on any commit, so nothing else can be
promoted.

Issues 344, 408 and 409 come next. All three are on the live money path.

---

## Band 2 — hours

Each of these is one function or one seam. Each needs a test that fails without
the fix.

| # | what it is | why it is hours | the anchor |
|---|---|---|---|
| 427 | One guard fails open, the next fails closed | Two guards in one function behave oppositely on an exception. A sell proceeds when the capital check raises, and is refused when the order check raises | `src/trading/scrumming/execution.py` lines 1318 and 1360 |
| 148 | Two live trade-path calls raise | Two names on the money path do not exist on the class that calls them | `src/trading/scrumming/tick_phases.py` |
| 429 | The year-to-date walk stops 360 days in | A fixed anchor and twelve windows. Make the anchor roll | `src/trading/scrumming/reconciliation.py` |
| 418 | Two header columns are fed nothing | Two literals and one formula. Mature profit is 70 percent of profit and loss, not positions above 200 percent | `src/gui/widgets/spendable_profits.py` |
| 301 | A refused order leaves no record | One record on the failure path, and the log has to reach disk | `src/exchange/api_logger.py` |
| 327 | The startup check checks nothing | The function reads a stored blob and reports an exchange ready to trade | `src/gui/main_window.py` |
| 65 | Target Delta latched negative on BILL | The bot ledger is short of the exchange and the shortfall is saved | reconciliation against the venue |
| 367 | Spawned tranches do not match the scrum | One comparison against the venue export | `src/trading/scrumming/fold_tranches.py` |
| 107 | Detonation can fire twice across a restart | One flag that is never saved. Repair before enabling detonation | `src/trading/scrumming_bot.py` |
| 241 | A bad stored theme name stops the launch | One fallback around one read, before the splash appears | `src/gui/theme_engine.py` |
| 242 | One bad number blanks the dashboard | One guarded refresh on a two-second timer | `src/gui/main_window.py` |
| 226 | One bad value costs all eleven Settings tabs | One guarded loader | `src/gui/settings_dialog.py` |
| 223 | One bad price stops every chart | One guarded walk | `src/gui/widgets/trade_charts_tab.py` |
| 230 | One bad price loses the candlestick chart | One guarded paint | `src/gui/native_chart.py` |
| 184 | One bad field stops the table paint | One guarded row loop | `src/gui/widgets/bot_status_table.py` |
| 233 | A bot is created with a balance nobody entered | One reader on the wizard box | `src/gui/bot_wizard.py` |
| 208 | A made-up dollar figure for a bad stored balance | One reader on two boxes | `src/gui/live_settings/settings_tab.py` |
| 238 | A label from one timeframe above another's numbers | One refresh path | `src/gui/indicator_panel.py` |
| 239 | The Bot Swarm live rows have never worked | The container the Sim and Paper layers build is missing on the Live layer | `src/gui/bot_visualizer.py` line 1168 |
| 197 | Phantom profit and loss always reads zero | One key name. The tab reads a field the phantom never writes | `src/gui/live_settings/phantom_bots_tab.py` |
| 425 | History rebuilds two strings the contract declares | Two strings deleted, two reads added | `src/exchange/history_read_contract.py` |
| 436 | The vault phrase is written out four times | One shared builder for the phrase | `src/gui/settings_dialog.py` |
| 363 | Shutdown raises on the frozen build | One shutdown order. The fault lands during interpreter teardown | `src/gui/main_window.py` |
| 325 | A suppression now fires and hides a fault | One catch-and-discard, now silenced | `src/gui/main_window.py` |
| 402 | Inert suppressions read as handled findings | 346 mechanical deletions of a rule that is already off | `.flake8` |
| 423 | Four Settings pages discard what you set | 52 controls that Save never reads and Open never restores | `src/gui/settings_dialog.py` |
| 158 | Styling values that reach no pixel | A corner radius the engine rejects, a hardcoded splitter colour, and an ignored property | `src/gui/theme_engine.py` |
| 273 | A live-monitor check is skipped every second tick | Four names read and never assigned. Build them or delete the branch | `src/gui/main_window.py` |
| 190 | A test worker dies about one run in eight | One test isolation. A real news download starts inside a test | `tests/test_exchange_tab_surface_parity.py` |
| 288 | A browser test file fails at random | One test isolation. The page loads without its module | `tests/test_react_shared_widgets.py` |
| 259 | Unknown whether the React checks run | One measurement on the build machine. Seven files sit behind one skip | `tests/test_react_header_strip.py` |
| 330 | Three tests read source text | Three tests rewritten to assert behaviour | `src/trading/scrumming_bot.py` |
| 85 | Loose scripts at the repository root | Seven files moved, and one sweep updated to follow them | `src/core/version_sweep.py` |

---

## Band 3 — days

Each of these is a subsystem, or several files that have to move together.

| # | what it is | why it is days |
|---|---|---|
| 128 | Convert the interface from Qt to React | Every screen. One panel is converted |
| 157 | Remove the remaining Qt | 70 files still import the toolkit |
| 117 | Simulator rebuild | The whole tab. Every venue-seam finding belongs to it |
| 118 | Order writes run the ledger backwards | Eleven order behaviours, all wrong |
| 119 | Live indicators see 100 candles, the Simulator sees 300 | Five behaviours across the wrapper layer |
| 120 | Market metadata disagrees between venues | Every symbol falls back to one template |
| 121 | A taker order is charged the maker rate | The fee rate is keyed by symbol alone |
| 122 | Two exception vocabularies, one untested retry | The retry path decides on a class name |
| 123 | The bot code differs by venue | Seven rows checked, six wrong |
| 124 | Zero spread, one book level, wrong error type | Six rows checked, five wrong |
| 125 | Venue failure behaviour is stated once | One base class, 282 lines, one statement |
| 126 | Connect never runs and markets never populate | Five facts, three wrong |
| 127 | A feedback channel that exists on one side | The simulated venue calls back, the real one does not |
| 111 | The Simulator ledger disagrees with the venue | Fills depend on fleet size |
| 19 | Paper Trader build-out | No tab code. Gated behind the Simulator |
| 147 | Proof of Accumulation tab | The engine runs. Nothing displays it |
| 23 | Market Inspector build-out | It owns the topology and oppositional push work |
| 407 | Publish reversal zones to social media | A new tab, a scan, a chart capture and a push |
| 442 | Restyle the Indicator Voting Panel | Five changes across the panel and its React mirror |
| 55 | Asset Charts restructure | One chart at a time, twelve indicators, a ticker row |
| 59 | Simulator tab restructure | A bot list clone, two chart players, a ticker row |
| 154 | Migrate the voting panel to the Live tab | The panel and everything that reads it |
| 34 | System Status tab | A tab that does not exist |
| 300 | Audio Suite | Two files, and the running application reaches neither |
| 155 | Phantom Bots verification | The build-out and the behaviour, end to end |
| 2 | Emitter network | The register and its check script are not in the tree |
| 62 | Logs are not smartly pruned | 1,951 MB. Five emitters fill 45 percent of every file |
| 414 | Eight indicators depart from their formulae | Eight separate pieces of published mathematics |
| 316 | Upgrade the Z-Score indicator | A new variant with its own zones |
| 143 | Unencoded text reads fail on this locale | 57 sites, some of them silent |
| 319 | Comment compliance sweep | 334 source files and 555 test files |
| 411 | Tests assert on source text | 222 of 525 files |
| 336 | The wizard writes 52 settings, creation reads 26 | Two sides of the bot contract |
| 441 | Settings that reach nothing | Every settings group measured, group by group |
| 415 | The API Tester is not isolated | Connecting rebinds every bot's exchange handle |
| 362 | The whole fleet stops fetching | A recurrence with no reproduction yet |
| 410 | The platform dominates the machine's page faults | A full collection every five seconds on the interface thread |
| 133 | Tranches list, counts, lifetime and panel size | Four units, each gating separately |
| 149 | Derive the version from git | The literal, the sweep, the gate and the build |
| 156 | Run on a server with the full screen | A deployment target and its install path |
| 63 | Verify ten exchanges | One venue has ever traded |
| 305 | Exclude unreachable assets from the build | Both build specifications sweep the whole source tree |
| 306 | The news ticker fetches ten external feeds | Ten outbound calls on a live screen, and their text is drawn as markup |
| 53 | Mouse over descriptions | 292 of them, 184 over ten words, and no size rule |
| 412 | Anchor and extend the product manual | 44 pages, ten of them figures with no description |
| 413 | Build a redacted manual variant | A second build with its own normalisation |
| 431 | The manual embeds figures a clean checkout cannot rebuild | 39 charts with no producer in this repository |
| 433 | Four novel concepts have no code | Four builds, each specified in the manual |
| 75 | Two parallel simulators | About 12,000 lines with no shared base |
| 81 | The audits folder is mostly harness calibration | 141 files to sort and move |
| 87 | Duplicated build entry points | Three launchers and two near-identical specifications |
| 88 | Installer suite duplicates its own steps | The suite moved. The duplication moved with it |
| 90 | Development processes live only in prose | No recipe file exists, and one required tool has no install step |

---

## Band 4 — blocked

These wait on a decision from you, or on another issue.

| # | what it is | what it waits on |
|---|---|---|
| 150 | Capital reservation refused every request | Repaired in code. One reading of the running platform's log confirms it |
| 398 | The phantom lock guard is dead | Build the lock or delete the guard. Zero call sites |
| 404 | The wire routing path is dead | Build the routing or delete it. Zero call sites |
| 437 | The Extractor pool is never rated | Build the call or delete the method. Zero call sites |
| 419 | A declared fold gate has no checkbox and no reader | Build the gate or delete the key |
| 145 | Two methods read attributes that are never assigned | It is two issues in one. Split it |
| 220 | The stock dashboard crashes every two seconds | The screen is not reachable. Nothing constructs it |
| 26 | Retroactive review of self-authored units | Two of the five named targets no longer exist |
| 113 | Verify the suite green in the workflow | The workflow cannot run. Billing, not code |
| 114 | Turn on branch protection | A repository setting only you can change |
| 401 | A harness fixture passes when it should fail | A harness file. Only you may change it |
| 196 | A colour check switches off for whole functions | A harness file. Only you may change it |
| 252 | A run that could not read a file looks failed | A harness file. Only you may change it |

---

## Closed by this audit

Thirteen defects no longer reproduce. Four more were the same work as another
number. Each closure carries the measurement that proves it.

### Repaired

| # | what changed | the evidence |
|---|---|---|
| 38 | Line endings were normalised | 1,174 tracked files report a line feed. None reports a carriage return. Both trees agree |
| 96 | An instance guard was built | `src/core/instance_guard.py` holds an exclusive lock and writes a machine claim. The launch reads its verdict before any bot starts |
| 110 | The fill reader was taught the payload | The reader branches on whether the fill is a table, and reads keys on that path |
| 194 | The screen recorder was removed | The file is not in the tree, and no folder is made under the repository |
| 243 | The suppression markers were rejoined | Zero markers sit on a closing bracket. 375 markers in the source prove the scan reports |
| 257 | The encoder refuses a not-a-number | It writes strict output, and falls back to a walked copy when a response holds one |
| 266 | The card borders go through one helper | Both call the helper in `src/gui/color_alpha.py`, which writes the byte Qt reads |
| 276 | The row order travels as a list | The surface publishes three order lists, and the renderer reads all three by name |
| 283 | The test helper became one shared copy | It replaces the file atomically, retries while it is held, compares the bytes back, and fails by name if it cannot restore |
| 331 | A local runner was written | `tools/local_ci.py` runs the four lanes the workflow states, with the same markers and four workers |
| 399 | The epsilons were removed | None of the three named files carries one. The ratio branches on a positive divisor instead |
| 405 | The engine matches the readout | The dust-band test is now inclusive, and a test file pins it |
| 434 | The build takes a variant | The build script accepts a variant flag, and both halves read one shared setting |

### Folded

| # | into | what carried across |
|---|---|---|
| 25 | 239 | The Sim and Paper layers each build their row container when the tab is created and the Live layer does not, and the empty-state label is read twice and assigned nowhere |
| 285 | 416 | The commit that emptied the documentation folder is what deleted the three fixture directories |
| 322 | 423 | The six keys written on Save and never loaded, and that two of them are defaults applied to new bots |
| 144 | 403 | Seven lines naming the retired programme, and a check that reports a registry will be created by a command that no longer exists |

---

## Anchors that no longer resolve

Twenty-three issues cite a path that is gone. Each row names what died and what
took its place.

| # | the citation | what happened |
|---|---|---|
| 2 | the emitter register — not in the tree | It was never committed. The issue asks for it |
| 2 | the emitter check script — not in the tree | It was never committed |
| 19 | the Paper Trader tab module — not in the tree | Correct as written. The tab has no code |
| 26 | two of five review targets — not in the tree | The targets were rewritten. The issue is stale |
| 81 | the attestation ledger — not in the tree | It was deleted with the folder |
| 88 | the whole installer folder — not in the tree | It moved to `deploy/kiosk/`. The duplication came with it |
| 90 | the old gate path — not in the tree | The gate moved to `dev_harness/harness/check_release_readiness.py` |
| 93 | one of the two named tests — not in the tree | It was deleted. The other still carries a version in its name |
| 96 | its design note — not in the tree | The design landed as code |
| 107 | its audit note — not in the tree | The measurement survives in the issue body |
| 110 | the Simulator controller path — not in the tree | The engine moved to `src/simulator/fleet/fleet_replay_controller.py` |
| 110 | the stress tool path — not in the tree | It moved to `src/trading/topology_stress.py` |
| 117 | its audit note — not in the tree | It moved to `docs/engineering-notes/2026-08-25_the_venue_seam.md` |
| 118 | the same audit note — not in the tree | Same move |
| 119 | the same audit note — not in the tree | Same move |
| 122 | the same audit note — not in the tree | Same move |
| 123 | the same audit note — not in the tree | Same move |
| 124 | the same audit note — not in the tree | Same move |
| 125 | the same audit note — not in the tree | Same move |
| 126 | the same audit note — not in the tree | Same move |
| 143 | the screen recorder module — not in the tree | One of 58 sites. The file was removed. The other 57 stand |
| 157 | a service file name, cut short — not in the tree | A typing slip in the issue body |
| 194 | the screen recorder module — not in the tree | The whole subject was removed. Closed |
| 403 | a Simulator module path — not in the tree | Correct as written. The point is that it never existed |
| 412 | two lint tool paths — not in the tree | Both were retired |
| 426 | the Paper Trader tab module — not in the tree | Correct as written |

Seven of these are correct as written: the issue reports an absence, and the
absence is the defect. Nine are one Simulator audit note that moved into the
engineering notes folder. The rest are stale, and their issue text should follow
the file.

---

## Folds — issues that are one piece of work

A fold joins issues that share a build, not issues that share a file. Two
defects in one module repaired by two unrelated changes stay apart.

Four folds were made and are listed above. Five more are set out here for your
ruling.

### Made — the Bot Swarm live rows

**239 survives. 25 closed.** Both name the same missing container in the same
method of `src/gui/bot_visualizer.py`. One unit builds it and the rows appear.

### Made — the release gate fixtures

**416 survives. 285 closed.** Identical defect, identical three constants.

### Made — the Settings dialog contract

**423 survives. 322 closed.** One dialog, one save path, one load path. A unit
making Save and Open agree with the controls the dialog builds finishes both.

### Made — the version sweep

**403 survives. 144 closed.** Both name checks in `src/core/version_sweep.py`
that read paths absent from the tree, and the check sets overlap.

### Proposed — the simulated venue's answers

**124 survives, absorbing 120 and 126.** All three are one object answering like
a venue: what it says about markets, about prices, and about being connected.
One unit finishes them.

Carry to 124: from 120, that the controller builds the backend with candles,
balances and fees but leaves the market table empty, so every symbol falls back
to one template whose precision is decimals where the library means tick size.
From 126, that attaching a backend marks the connection live without the connect
step running, and that the market load never populates.

Issue 125 stays apart. It is the base class contract, and it also asks for a
Paper venue, which is 19.

All three are children of 117, so this fold is yours to make.

### Proposed — the topology proposal feature

**23 survives, absorbing 424.** Dismissing a proposal is part of the proposal
work that 23 now owns.

Carry to 23: the dismissal writes a key the settings schema does not declare, so
the write raises and the card returns on the next launch. The schema field has
to land with the build.

Against the fold: 424 is a one-line repair today, and 23 is a build. Folding it
delays a correction that costs nothing.

### Proposed — labels that render as markup

**272 survives, absorbing 268.** Both are a label with no text format, so Qt
guesses markup.

Carry to 272: on the Market Inspector the fixed half of the string is written as
markup, which is why the whole label is read that way, and the variable half is
an exception message.

Against the fold: they are two different screens. They share a repair shape, not
a build.

The news ticker draws feed text the same way. It stays with 306, because its
other half is ten outbound calls on a live screen.

### Proposed — the Paper Trader claim

**19 owns the build. 422 and 426 stay open for the strings.**

The strings are a minutes fix available today. The build behind them is gated
behind the Simulator and will not move soon. Folding the strings into 19 buries a
fast correction inside a blocked build.

Carry to 19: what a Paper Trader has to do, taken from the description string
that promises it.

### Proposed — split, do not fold

**145 is two issues.** Its first half is the Bot Swarm container, which is 239.
Its second half is two stat cards the stock dashboard reads and never builds,
which is 220. Neither half is new once the two are placed.

---

## Sequencing that is not a fold

Four pairs have to move in order.

**429 before 428.** The counter tooltips cannot state the truth until the
year-to-date walk stops truncating.

**414 before 316.** The Z-Score upgrade rewrites the file the formula repair
lands in.

**441 before 423.** Which of the 52 discarded controls are worth wiring depends
on which config keys anything reads.

**124 unblocks 23.** The Market Inspector's arbitrage work needs a simulated
venue that reports a spread. Today it reports zero.

---

## What needs your decision

**Issue 220, and the second half of 145.** The stock window class is declared
and nothing constructs it. It is not on the tab bar and no window builds it. A
defect there is a defect nobody can reach. Close both, or keep them against a
future build of that wing.

**Issue 150.** The mechanism the issue described is repaired. The claim is now
clamped to what the bot holds after other bots' claims, and a stale claim is
released after a failed attempt. Whether the warnings stopped cannot be shown
from the tree. That needs one reading of the running platform's log.

**Issue 427.** Its title is right and its body is half wrong. The body says the
check cannot run live because no live construction site passes a registry. It
can: the bot falls back to the process-wide registry when it is not in
simulation. The title's finding stands and is serious. In one function on the
money path, the capital check catches every exception and lets the sell proceed,
while the very next check catches every exception and refuses the sell. Two
guards, one function, opposite behaviour.

**Issues 398, 404, 437 and 419.** Four written features with no caller: the
phantom lock, the wire routing, the Extractor pool rating, and the sixth fold
gate. Each is either a build you still want or code to delete. The answer decides
whether each is minutes or days.

**Issue 26.** Two of its five named targets no longer exist. The work it asks for
cannot be done against the tree it was written for.

**Issues 113 and 114.** Neither can move while the workflow cannot run.

**Issues 196, 252 and 401.** All three are harness files. Only you may change
those.

**Issue 442 against 154.** Your restyle asks for the timeframe lock control and
its code to be removed. Issue 154 asks for the same panel to be migrated to the
Live tab. Whichever lands second inherits the other's shape.

---

## Titles that do not match their bodies

Three issues read differently from what the code shows.

**Issue 44** says nine comments cite a line number that moved. Eight are gone.
One survives, and it sits in a test docstring rather than in the source.

**Issue 427** claims the capital check cannot run live. It can.

**Issue 158** names three defects. The transparent glows are repaired: every one
of those values now goes through the alpha helper. The square corner, the
hardcoded splitter colour, the ignored property and the eight unread theme values
remain.
