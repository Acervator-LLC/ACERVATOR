# Changelog

Reference. Newest first.

Entries before `3.23.20` live in [`_archive/root_docs/CHANGELOG.md`](_archive/root_docs/CHANGELOG.md).
That file was moved under `_archive/` at some point during the 3.23.x series and
never replaced at the repo root, so the `3.24.x` cascades shipped with the
changelog step of the documented version-bump sequence silently skipped. This
file restores it; the `3.24.19` and `3.24.20` entries below are reconstructed
from the work actually performed.

---

## 3.27.0

**Why this version exists.** Two lines of work joined in this release. One is a
real test and lint pipeline from the CTO, which touched every file. The other is
a Simulator that stopped producing nothing.

The two histories had no common ancestor after `main` was force-pushed. They are
joined here. 12,540 functions and classes were checked across both sides; none
was lost.

### The Simulator ran for nine months and produced nothing

**No sim bot initialised after v3.24.84.** `TabletBackend` replaced
`FleetSimExchange` and did not carry across its balance seeding. `fetch_balance`
never listed a base asset, `get_balance` marked it absent, and `tick` correctly
refused to initialise on an absent read. Every bot re-ran the handshake on every
tick, for ever. That handshake holds a 0.25 s sleep, which is why one test file
took 917 seconds. Same file now: 23 seconds. A 400-candle replay went from 212
seconds and 0 trades to 2.24 seconds and 1 trade.

**Nothing asserted that a replay fires a trade.** `trades_fired` was only ever
asserted `== 0`. A dead Simulator and a healthy one were indistinguishable.

**Every fill recorded as zero.** `_on_sim_trade` read a dict with `getattr`,
which returns the default for every field. A replay that filled a trade reported
an empty per-symbol count, drew no chart marker, and wrote a run-log entry with
an empty symbol and zero price. A deliberate sweep of that hand-over found five
more consumers with the same fault, including the stat strip, which reported
`Spendable $0.00` and `Trades 0` on every run that traded.

**The sim venue accepted an order the wallet could not fund.** It returned a
`rejected` order object; the live venue raises. The bot booked the estimate and
carried a position it never bought. The sim venue now raises the same exception
live raises. No bot code changed.

**A bot's ability to trade depended on how many other bots existed.** The wallet
was seeded at the sum of the fleet's targets with no fee headroom, so the last
bot was always short by the accumulated fees. At a fleet of one, that was the
only bot. Lot-less bots now open with a locked side equal to their spendable
side, and fleet size no longer decides whether a bot trades.

### The rest

**The news ticker could abort the process with no traceback.** A thread was
parented to a widget, so destroying the widget destroyed a running thread. The
50 ms wait could never have worked: the fetch had no bound at all, because a
timeout raised by the iterator escaped its own `try` and the pool's exit blocked
until every feed finished. Three reproduction modes went from exit 127 to exit 0.

**The growth cap never compounded.** Eight sites computed it from the anchor,
which no Fold moves, so the cap held one dollar value for the life of a bot. Two
of those sites were the number the panel displays. The fleet's per-cycle cap
moves from $35.02 to $35.93 and releases parked surplus.

**49 of 77 emitters were evicted before anyone could read them.** Five emitters
filled 45% of every file and the retained window was 2.1 hours. A second, thinner
ladder keeps every identity at 100% for the quiet ones and folds the loud ones,
taking the window to 25.7 hours for 4.8% more disk. Nothing is dropped; every
folded observation is counted.

**A chart kept fetching the old pair after a bot's symbol changed.** The label
followed the bot. The fetch did not.

**A failed singleton retried every tick, for ever, at DEBUG.** Three unrelated
features flooded the log every two seconds for hours and said nothing an operator
could act on. A failure now backs off, reports once at ERROR naming what stopped
working, and recovers on its own.

**Emitters are categorised.** 16 always-on, 62 toggle. A silent toggle is off; a
silent always-on is broken. Before this, silence meant nothing.

**`sim/` had no retention policy** and reached 674 MB. It demotes before it
evicts, so old runs keep their metadata and lose only bulk.

### Known and not fixed

The venue seam carries 45 measured spec violations between Simulator and Live,
enumerated in `docs/audits/2026-08-25_the_venue_seam.md` and tracked as #117.
The largest: Live's indicators see 100 candles and the Simulator's see 300, from
the same tape on the same call.

165 of 651 files do not pass their archetype, 907 of 913 findings predating the
recorded history. See `docs/audits/2026-08-24_archetype_census.md`.

## 3.26.0

**Why this version exists.** Forty-three merges landed after `3.25.8`, and the
version string did not move. The rule is: gate first, then bump. The gate ran.
The bump did not follow. A rebuild would have reported the old version.

This is a minor bump, not a patch. The application reports 74 signals where it
reported 40. Six tabs that reported nothing now report. The package changed its
name. The version now lives in one file and nowhere else.

### Faults you could see, now repaired

**A bot showed a BUY on a position that was already above its target.**
Target Delta is the current balance from the exchange minus the target balance
in the application. The first number did not come from the exchange. The bot
kept its own count of what it held, and it refused every upward correction. A
bot whose count fell behind the wallet traded on the stale number for as long
as it ran. Bot `95340bda` counted 14,131 units against a wallet of 15,778. The
bot had bought those 1,647 units itself and had failed to record them. The Ammo
cell then showed `buy $16.27` on a position $17 ABOVE target. The signal was
inverted. The bot now adopts the exchange figure when its own count is low. It
still refuses a surplus it cannot attribute, and it now states the reason. The
line `Resetting internal state to exchange reality` printed before the bot made
the decision. It printed 735 times on BILL while the bot preserved instead. That
line is gone.

**The same wrong number came back at every launch.** Three more paths reached
that first number and were left open. Start-up re-seeded holdings with the
lower of the wallet and the book, which can only pull the number DOWN. Every
launch re-seeded 14,131 against the 15,778 wallet. A downward correction is
unchanged, and an empty book still starts at zero. The correction also measured
its top-up from the wrong counter, so the bot's two counts of the same holding
could stand 869 units apart. The correction lot could also take a cost basis of
0.00 on a bot that had not yet completed a priced tick. A cost of zero claims
unlimited profit against every price and can arm a sell. One writer now creates
that lot, and it refuses a cost that is not a finite positive number.

**A small rise in Target Balance destroyed accrued growth.** The Target Balance
box shows the anchor, which is the number you typed. The traded target grows
above the anchor as the bot accumulates. The top-up compared your new number
against the GROWN target instead of the anchor, so the two were never in the
same frame. Live bot IMU on 2026-08-21 held an anchor of $50.00 and a target of
$63.5297. Raising the displayed $50 to $60 compared 60 against 63.5297, took the
collapse branch, and set BOTH to 60. That destroyed $13.5297 of accrued growth
and lowered the traded target below where it already stood. The position then
sat above target, the Delta turned positive, and the bot folded the excess. 35
of the 38 live bots carried growth, and six carried more than $5. The comparison
now uses the anchor. The top-up policy itself is unchanged, and only inputs
inside the defect window behave differently.

**Starting a bot froze the window for about two minutes.** The connection to the
exchange ran on the same thread that draws the window, so the application
stopped repainting until the connection finished. Measured at about 111 seconds.
The connection now runs off that thread.

**A bot safety check reported green on every tick and could never fail.** The
capital reservation check compared the requested amount with itself. Two
identical numbers are always equal, so the check passed on every bot, on every
tick, for its whole life. It now compares what the bot needs against what the
reservation registry holds, and it reports a fault when the held amount leaves
the 1% band the update path is supposed to keep it inside.

**A command could reach the wrong bot after the tables refreshed.** The bot
tables rewrite every row every two seconds. The highlight tracked a row number,
not a bot. Deleting one bot moves every row below it, so the highlight then sat
over a different bot, and Stop or Start went to that bot. Driven before the
repair, a Stop aimed at `bot-AAA` reached `bot-BBB`. The highlight now follows
the bot. If the selected bot leaves the fleet, the selection clears and the
application asks you to choose a bot. The repair sits on the table itself, so
the Simulator's copy of the table gets it too.

**A command could reach the wrong bot when you pressed a Detail button.** The
Detail button sits inside a table cell, and pressing a cell widget changes no
row selection. The window then fell back to the other table's selection and sent
the command there. Driven before the repair: select `scrum-1`, press Detail on
the Extractor table's row, press Stop, and Stop reached `scrum-1`. The Detail
button now selects its own row first, on both tables. The same repair also
corrected a misroute inside one table, where Detail on row 1 with row 0 selected
commanded row 0.

**Console Pause stopped only one pane.** Pause stopped the log pane and left the
signals pane scrolling, although its own description promised that one control
quiets both. Driven on real widgets, the signals pane grew from 10 to 51 blocks
over four passes while the log pane held at 10. One control now quiets both.

**The signals pane discarded records and said nothing.** Each pass drew only the
newest 200 records and stepped over everything older. Measured: 250 records
showed 200 and dropped 50; 5,000 records showed 200 and dropped 4,800. Nothing
on the screen said the other records existed. The system never lost them. It
writes every record to disk as it arrives. The pane now stays current and draws
a marked gap line that counts what it skipped and names the file that holds it.

**The Market Inspector had no refresh limit.** Its own description promised a
gap of 15 minutes between network fetches and named the Refresh button as the
way to override it. Both halves were false. The limit was declared and never
read, so every refresh went to the venue, and the button passed an override into
a function that ignored it. The limit now works, the button overrides it, and
the panel reports the age of the data and whether it came from the network or
from cache. An empty result is not cached, because that would serve nothing for
15 minutes and look like a working feed.

**One stopped exchange tab could hide behind a healthy one.** Two tabs of the
same kind run the same line, so their rate-limited reports collapsed into one
counter. Driven on two real tabs, a healthy pair and a pair with one tab's
reporting dead produced the identical record. Each tab now declares which
exchange it belongs to, and each one reports separately.

**The History tab used a display check that never worked without a screen.** Its
fallback bound four Qt names to nothing and then called them at thirteen sites,
so the tab imported and then failed at the first call. It now uses the same check as the
rest of the interface modules.

### The Simulator can no longer overwrite your saved fleet

On 2026-08-22 a full test run replaced `~/.acervator/simulator_bot_state.json`,
which held the operator's saved Simulator fleet, with one synthetic test bot.
That state cannot be rebuilt. The Simulator built its save path when the module
loaded and accepted no override, so any code that drove the Simulator wrote into
the live runtime folder. The writer was found by experiment: a test that clicks
Load on a real replay panel. The Simulator now builds the path at the moment of
the save, and it honours a directory override that the test suite sets before it
collects any test. The shipping application is unchanged, because the override defaults to
the same folder. The live fleet file is refused outright, so a redirect cannot
become a way back onto the operator's bots.

### The application now reports on itself

The application reported 40 signals. It reports 74. Six tabs that reported
nothing now report: Trading, Exchange, Console, Asset Charts, API Tester and the
Bot Swarm. The History tab went from one signal to seven. Each signal states
what it checked, what it expected, what it found, and whether that passed.

Every signal now also declares whether it can carry a timing, in one of four
fixed terms. A number on all 74 is not possible. 26 of them do not follow a
completed operation, and a timing on one of those would be invented. 21 signals
measure a real elapsed time, and every other signal states which of three
reasons applies to it. Three new gate rules hold each declaration to the code it
describes, in both directions, so the column cannot rot.

One real Simulator run then proved the network through the operator's own path:
38 real bots and 33 Smart Wires loaded, 38 simulated bots spawned from the real
Stone Tablets, 15,211 of 15,212 candles played, 414 simulated trades, 234,139
bot ticks, 0 exceptions, and 3,799,113 records observed. 36 of the 74 signals
fired. Every one of the 36 carried the name, the type and the site the register
declares. Every timing agreed with its declaration in both directions. Nothing
fired that the register does not list. The live tree was sandboxed and checked
after the run: the same 478 files under `~/.acervator/`, no new files under
`~/.acervator_logs/`, and the credentials never read.

### The release gate now enforces what it claimed

The gate ran when asked, and nothing made it run before code merged. It now
stamps the exact commit it proved, and a push is refused for any commit the gate
has not stamped. A green gate on a dirty tree is not stamped, because it
measured content that is in no commit.

The gate also checks the signal network. Every signal in the code must have a
register row, and every row must have a signal in the code, so a signal cannot
be deleted or invented in silence. Two further rules reject broken checks at the
gate. The first rejects a check whose two sides are the same expression, which
is exactly the fault the capital reservation check carried. The second restricts
timings to the one kind of check that can honestly carry one.

The gate's own self-tests were not sound. Each rule had a pair of controls, and
the half that proves a rule FIRES matched a violation anywhere in the tree, so
it could pass on somebody else's defect. Both halves are now scoped to the
planted case, and the suite runs them.

The repository now stores and checks out every text file with LF line endings. A
fresh clone on Windows used to write broken shell scripts, including the script
that runs the gate before a push.

### One version, one name

`src/__init__.py` is the only place the version is written. The entry point, the
packaging file, both screens and the manual generator all read it. Nothing else
declares a version. Before this, five other places stated a version, and every
one had gone stale: the packaging file said `1.0.0`, the README said `3.15.94`,
the splash screen said `3.9.0`, the investor screen said `3.7.0`, and the manual
generator said `3.1.98`. Nothing compared any of them with the package, so they
rotted unseen. A file named `ver.txt` at the repository root held a sixth
number. A search of
every file type found no reader for it anywhere in the tree, so this release
deletes it.

New tests hold the rule: a file either imports the version or states a value
equal to it, and there is no third option. One value is exempt, because it
records which English manual the Japanese text was translated from, which is a
true statement about the past. That exemption is earned by a naming convention,
and its own test keeps the convention from becoming a hiding place.

The project is named `acervator`. The old name was `quantum-auto-trader`, which
is not the product. The installed command is `acervator`.

The developer note at the top of `src/__init__.py` told the reader to bump a
second copy in `main.py` and keep the two in step. The entry point stopped
holding its own version some time ago, so that instruction was false and would have restored
the drift at the next release. Both notes now state what the code does.

### The development harness moved out of the product path

The harness moved from `tools/harness/` to `dev_harness/`. Nothing was deleted,
disabled or made optional. The harness stays fully in use. The move touched 47 caller
files and 160 references. Five callers built the old path from parts, so no text
search could find them. One of those five was the migration tool itself, which
would have skipped a moved file in silence, and it would have reported nothing. A new test reads the caller
files and requires every harness module they name to import, so a caller left
behind by a future move fails at the gate.

### Four files cleared, with no suppressions

The splash screen, the investor screen, the Japanese manual generator and the
version sweep carried 44 high findings between them. All four are now clear, and
no finding was silenced. The splash screen seeded the shared random number
generator with a fixed value, which changed the numbers every other module drew
from it. That call is gone, and both screens now draw from the operating system
entropy source. Ten unused imports were deleted. Both screens render across
their whole timeline with frame counts that match the baseline exactly, and the
Japanese manual builds a document that is byte-identical to the baseline once
the creation date and the document identifier are normalised.

### Reported, and NOT fixed

Everything in this section is a KNOWN fault. This release RECORDS it. This
release does NOT repair it.

**The investor screen's Proof chapter has never drawn its chart.** The chart
method in `investor_screen.py` calls two methods on itself that exist nowhere in
the tree. Every attempt raises, so 39 of the 401 frames in that presentation
fail. This is not new damage. The chart has never rendered.

**One of the 74 signals cannot fire anywhere.** The signal that records a Paper
run in the Bot Swarm has no call, no attribute reference and no mention of any
kind anywhere in the source. Its sibling, which records a Simulator run, fired
in the proving run. Until that signal is wired, silence from it means nothing.

**Coverage measurement is blind to the whole interface.** `pyproject.toml` omits
`src/gui/*` from coverage. Every window, tab and panel sits outside the coverage
number, and a coverage figure quoted for this application does not
describe the interface at all.

**An Asset Charts panel keeps fetching the old pair after a bot changes pair.**
The panel relabels its title from the new pair but keeps the pair it stored at
creation, and that stored pair drives the request to the exchange. The
chart shows the new pair's name above the old pair's candles, and it never
corrects itself. This release DETECTS and REPORTS the fault. Treat a chart whose
bot changed pair as showing wrong data.

**Two counts of one holding can disagree inside the 0.5% band and be called
aligned.** The audit reads the higher of the two internal counts against the
wallet. With a scalar of 15,778, a book of 14,131 and a wallet of 15,778, it
reports agreement and leaves the two internal counts 1,647 apart. This is a
different path from the correction repaired above, and it needs its own decision
about what a disagreement inside a band should do.

---

## 3.25.8

**Why this version exists.** A package was cut at `3.25.7`, and four
promotions landed after it. Two trees would otherwise carry one version
string, which is the exact condition `3.25.6` was cut to end.

The four, in promotion order, from `tools/.island_ledger.jsonl`:
`ISLAND_P1GREEN`, `ISLAND_DEGEN2`, `ISLAND_PINWORST`,
`ISLAND_U6VENUEGATE`.

**An order amount that was not a number could reach the venue.**
`bot_container.guarded_place_order` had no type test. `float(amount)`
accepted anything convertible, then `math.floor(nan * scale)` raised, so
the step counts fell back to `None`, the check degraded to
`_amt < _min_amount`, and **`nan < 0.001` is False** — every comparison
against `nan` is. The guard could not fire.

Measured across 76 shapes x 2 market-metadata regimes x 2 dispatch paths,
304 drives per tree, venue replaced by a recorder that never sends:

| tree | escapes |
|---|---|
| pristine twin (pre-change bytes) | **198 / 304** |
| after the gate | **4 / 304** |

The escapes included `nan`, `+inf`, `True`, `"5.0"`, `"nan"`,
`Decimal("NaN")`, `Decimal("Infinity")`, a `Decimal` subclass, a float
subclass holding `nan`, an int subclass, an `IntEnum` member, an object
whose `__float__` returns `nan`, and `numpy` scalars. The four that remain
need a class whose METACLASS defines `__eq__` — an AST walk found zero
classes in the tree deriving from `type` or declaring `metaclass=`, so the
shape cannot be produced here. Recorded rather than hidden; the identity
form `type(x) is int` closes it and is its own unit.

**The other half of that gate is that it refuses nothing real.** 37 real
order sizes at real precisions x 6 metadata regimes x 2 sides x 2 dispatch
paths = 888 drives per tree. Cells differing from the pre-change tree: **0**.
Hiding regressions: **0**. The 37 amounts produced 6 distinct outcome
vectors, so that zero is a measurement and not a uniform answer.

**A halted market voted BULLISH at full conviction.** On a flat window
`_stdev_tail` leaves sigma at a few ULPs rather than exactly zero, because
summing 20 copies of one price rounds. An exact `upper - lower <= 0` test
therefore never fired, the `1e-9` epsilon became the whole denominator, and
BollingerBands answered BULLISH at confidence 1.0000 and weight 1.0 — the
largest vote the engine casts — on a market that had not moved. The repair
guards the SOURCE quantity, which cancels exactly: a window has no channel
when `max(window) == min(window)`. Leak over 468 venue-decimal pegs on
eight degenerate shapes: **467 → 0**. The window boundary is exact — an odd
bar at index n-21 leaks 0, at n-20 the guard declines. Two fabricated
`mid * 0.01` band fallbacks were removed; no coefficient was invented.

Verified against real data: 169,008 twenty-bar windows across 11 assets,
read-only. Windows in the class the guard closes: **0**. Smallest band ever
observed: 5.455e-08.

**A coverage pin could not report the violation it existed to catch.**
`ta.07.001` walked only the eligible map, so a bot observed on candles the
master clock never reached emitted **no record at all** and the run read
green. It now walks the union of both maps, with a reconciliation identity
proved on five scenarios and shown false on the defect. A bot in neither map
still gets no record — it has no bound to assert, and inventing one would be
decoration that reads as evidence.

**Two committed test files were archetype-red before anything was edited.**
`touchset` refused to write a pin at all: "a unit cannot be greener than the
files it lands in." The dead names were parameters of a bus stub; deleting
them was tested and rejected, because production wraps every emit in a
`try/except` that swallows into a debug log, so a broken stub signature
would never fail a test. The parameters were kept and only the names marked
unused.

---

## 3.25.7

**Why this version exists.** Twenty-five promotions landed after the
`3.25.6` banner was cut, so the version string could no longer tell that
tree from this one. It can now.

The twenty-five, in promotion order, from `tools/.island_ledger.jsonl`:
`ISLAND_BOOLPRED`, `ISLAND_RATESPIKE2`, `ISLAND_STACKROW`,
`ISLAND_FOLDROW`, `ISLAND_FHLEAK`, `ISLAND_FIRECONF_RB`, `ISLAND_SWIRE`,
`ISLAND_SWARMAGE_RB`, `ISLAND_TAENG`, `ISLAND_SWOFFER`,
`ISLAND_SWARMMONEY`, `ISLAND_STALEDIST`, `ISLAND_R40V2`,
`ISLAND_R40V2_SINKFIX`, `ISLAND_LATCH`, `ISLAND_TIMEB`, `ISLAND_U3GATE3`,
`ISLAND_SLINGCANON`, `ISLAND_FOLDFIN`, `ISLAND_SNAPDOM`,
`ISLAND_FOLDUNITS`, `ISLAND_WIREVIS`, `ISLAND_WIREHOLE`, `ISLAND_PINFIN`,
`ISLAND_P1GREEN`.

**The gate that produced this banner.** `check_release_readiness` on the
live tree: `[OK] Release-ready (v3.25.6, 6605 tests)`, exit 0, run before
the bump. `claim_ledger check` exit 0, no open claims. The tree was
hashed before and after that run — 402 files,
`916b4c609e7366b643b46c5ed0304724ce8a08daf046aaafa6edb1af65663671`,
unchanged — so the banner describes this exact tree and not a moving one.

**A launch-path check now runs beside the gate.** A green suite does not
prove the application starts: a module no test imports can carry a bad
import and the suite stays green. All 165 modules under `src/` plus
`main.py` are now imported in a spawned child before a package is cut.
165 of 165, exit 0. The child's home directory is redirected to a
temporary path, which earned its place immediately — import alone creates
`.acervator_logs/`, so an unsandboxed check would write into the live log
tree while bots are trading.

**`ISLAND_P1GREEN` — the committed ground was red.** `coding_archetype`
returned `passed=False` on `tests/test_manual_fire_fold_growth.py` and
`tests/test_fold_target_growth_helper.py` on the *unmodified* tree, two
dead-code highs each. `touchset baseline` refused to write a pin at all:
"a unit cannot be greener than the files it lands in." Both files now
return `passed=True`, verified here against a two-sided positive control
on the known-good and known-bad fixtures.

**Measured, and recorded because it changes how the next unit is sized.**
The whole suite runs 522-679 s. One unit carrying seven two-sided controls
ran it 17 times inside a single agent, because every revert re-runs it —
231 minutes of pytest in one job, of which 94.5 % was unedited code
(13 of 235 test files name `ta_engine`, the only source file that unit
changed). The coverage rule is correct and unchanged. Putting seven
controls in one unit is what was wrong.

---

## 3.25.6

**Why this version exists.** The frozen build of 2026-08-11 18:30 and
the source tree both reported `v3.25.5`, and they were not the same
code. Twelve promotions had landed since that build, so the version
string could not tell the two apart. It can now. A splash reading
`v3.25.6` is this code; `v3.25.5` is the older binary.

The twelve, in promotion order, from `tools/.island_ledger.jsonl`:
`ISLAND_DESPAWN3`, `ISLAND_U1LABEL2`, `ISLAND_U2VENUE`, `ISLAND_MWPIN`,
`ISLAND_C43GAPS`, `ADV2_BOTVIZ_REBASE`, `ISLAND_CCXT_LAND`,
`ISLAND_IVPPERSIST3`, `BWA11Y`, `ISLAND_U12BOUNDS`, `ISLAND_DEFXML2`,
`LOGSINK2`.

**Two unbounded logs, both measured on the operator's disk 2026-08-13.**
`ISLAND_U12BOUNDS`.

* `console/system.log` held 9,146,281,918 bytes and was still climbing.
  It was the one writer in `logging_engine.py` with no `maxBytes` and
  no `backupCount`, while `trade.log`, `gate.log`, `diagnostics.log`
  and `voting.log` were all capped. The new `SizeBoundedFileHandler`
  caps it at 50 MB x 5 — the same threshold the other four have
  rotated on since v3.23.5, measured holding at 52,428,9xx bytes per
  backup on this filesystem.
* `signals/session.jsonl` held 2,445,435,093 bytes over 4,942,000
  records, 72.5 MB/h across 32.2 hours of active process time. It now
  rotates at 50 MB x 5 as well.

**The emitter network no longer switches itself off.** `SignalSink.emit`
compared its sequence counter against `MAX_ROWS = 2_000_000` and
returned None for the rest of the process once it passed. Two of the
four process runs in the operator's own `session.jsonl` reached exactly
2,000,000 rows — one after 13.10 hours, one after 12.99 hours — so the
network ran blind for whatever was left of both sessions. That cap is
gone. Emission is unbounded; memory is bounded instead. `_buf` and
`_all` are now `deque`s with `maxlen=RETAIN_ROWS` (350,000), which
holds the resident cost near 273 MB against the 300 MB the file ladder
already occupies. The replacement is not optional: at the measured
818.1 bytes per record, lifting the cap alone projected to 2.9 GB of
Signal objects inside the GUI process after a day. Eviction is counted
and the two evictions are reported separately, because falling out of
`_all` is a window and falling out of `_buf` is a loss.

**A failed rotation no longer silences a log for the life of the
process.** `LOGSINK2`. `SizeBoundedFileHandler.doRollover` reopened the
stream as its last statement, so a raise from `_open()` left
`self.stream` bound to a closed file. `shouldRollover` reopens only
when that attribute is None, so it never reopened, every later record
raised, and `handleError` absorbed each one. Measured through one
transient `OSError(28)` on this interpreter: our handler went silent
for the run and left no current file on disk, where the stdlib handler
self-healed on the next record. The stream is now cleared at the close,
before anything that can raise. The backup shift keeps `Path.replace`,
a single `MoveFileExW` with no interval in which the destination is
missing.

**RSS feeds are parsed by `defusedxml`.** `ISLAND_DEFXML2`. The crypto
news ticker takes bytes from ten third-party hosts, on a worker thread
of a trading GUI. Measured on CPython 3.14.4 with expat 2.7.5, driving
the real `parse_rss`: a 20,922-byte feed declaring one 20,000-character
entity and referencing it 150 times expanded to 3,000,027 characters
under `xml.etree.ElementTree` and still returned a headline — expat's
own amplification guard does not activate that low. The textbook
billion-laughs document cost 59,097,148 bytes of peak allocation and
0.51 s before expat refused it. Under `defusedxml` the first raises
`EntitiesForbidden` and the second costs 15,551 bytes and 0.0001 s.
Refused feeds log at WARNING; a merely malformed feed still logs at
DEBUG and returns `[]`. `defusedxml` is declared in `pyproject.toml`
and in BOTH PyInstaller specs, which `tests/test_specs_parity.py`
requires. External entity resolution was never a live hole: the stdlib
parser installs no external-entity handler, and the local file was
measured unread either way. Fetches now route through
`src.core.safe_url` and the response body is capped at 4 MiB.

**The TA indicator panel keeps its last reading.** `ISLAND_IVPPERSIST3`.
`_last_summary` lived only on the bot object. A restart threw it away,
and a bot parked in its dust band returns before the TA block, so it
never computes another one — permanently, not slowly. The panel now
writes each rendered read to a snapshot file and reads it back after a
restart. The snapshot directory is resolved from the running
`StateManager` rather than re-derived, so a custom `config_dir` cannot
leave snapshots written where nothing will look for them.

The empty state also names ONE cause. The old text answered both
RUNNING cases with one sentence — "first read can take ~60s; a bot
parked at target evaluates no TA" — and it led with the transient
clause, so the operator waited on a condition that never resolves. The
panel now reports `not_running`, `bot_error`, `parked_at_target`,
`too_few_candles` or `cold_start`, checked in that order, from fields
already in memory. It performs no fetch and computes no TA.

**The lot-book reconcile reads the number the operator sees.**
`ISLAND_U2VENUE`. Three defects in one method:

* It read `balance.free`. The startup handshake reads `balance.total`,
  and MEM-255 records why: `total` is the figure on the exchange
  screen. The branch multiplies every lot by venue / internal, so on a
  bot holding a resting order `free` is short by exactly the committed
  units, and the book would be rescaled down to exclude coins the
  operator still owns — discarding those units and their
  `initial_buy_price` permanently, because the drift-up branch never
  claims units back. Exposure today is zero: all 37 bots carry zero
  active orders, so `total == free` on every one. Stack tranches place
  resting orders, so the condition that makes this bite is the one the
  queue is heading for.
* An absent reading was read as a zero. `get_balance` returns three
  zeros with `absent=True` when the exchange OMITTED the currency, and
  the same three zeros with `absent=False` when it reported a real
  zero. Read as a zero the ratio is 0.0, every lot is multiplied to
  nothing, every lot is then dropped by the tolerance filter, and the
  whole position and its cost basis are erased from a response that
  never mentioned the coin. The reconcile now refuses, names the asset
  and the reason, and retries at the next interval.
* The audit compared the scalar against the wallet, which is the wallet
  against itself, so any excess stranded in the lot book with nothing
  left to detect it. Measured in a read-only pin of `bot_state.json`
  taken 2026-08-13 19:18Z: 20 of 37 bots carried a lot book ABOVE their
  scalar and zero carried one below — one direction only, which is what
  a `min` against an unaudited counter produces. The audit now reads
  the book, and refuses the whole reconcile when an input falls outside
  the reconcilable domain.

**Failures in the GUI that used to vanish are now recorded.**
`ISLAND_MWPIN` carries seven repairs from the 2026-08-13 suppression
audit.

* `_do_disconnect` submitted `disconnect()` to a pool and never read
  the Future, so the worker exception died with the executor while the
  label read "Disconnected". The connector reference is dropped either
  way, so an unreported failure left an exchange session that nothing
  could close. It now reads the Future and reports the failure.
* Delete-bot swallowed a failed `bot.stop()` and then unregistered.
  `unregister` releases the reservation and detaches the wires; it
  never sets the stop event and never cancels an order. A scheduling
  failure therefore left a task trading real money that the manager no
  longer held. It is logged at error level now.
* `_wire_read_back_confirms` answered True when the read-back raised,
  so a renamed manager interface counted as "the engine took it". It
  answers False. An engine that is present and unreadable has confirmed
  nothing.
* The `bot.error` capture dropped a whole record when `consecutive` was
  non-numeric, so the Errors card under-reported in silence.
* The thread-violation refusal, the AI feedback journal write, and the
  `mousePressEvent` override annotation complete the set.

**Tranches, labels, and the harness.**

* `ISLAND_DESPAWN3` — a despawn sweep delists fold and stack tranches
  older than `config.tranche_despawn_days`. The forbidden `noqa` is
  deleted, the stack discard accounting mirrors the fold path, and the
  missed int conversion site is closed.
* `ISLAND_U1LABEL2` — the settled-fill fallback emit carries its
  caller's label, drawn from a closed set, so the operator can tell
  which path produced it.
* `ISLAND_C43GAPS` — five harness gaps, G1 to G5. An archetype report
  can no longer read green for an unscanned target or an absent
  analyzer, dead type-ignores are reportable, `ta_archetype` gained
  `by_severity` so the gate prints its real finding count, and H10/H11
  resolve through PATH. 29 dead `noqa` headers were removed from tests.
* `ADV2_BOTVIZ_REBASE` — 14 high rows cleared in `bot_visualizer.py` by
  code, plus the H4 wire-hydration fix that names three silent losses.
* `ISLAND_CCXT_LAND` — the last 10 coding highs in `ccxt_connector.py`,
  cleared by typing rather than by suppression. `HistoryCallback` is a
  real alias, the preflight uses `SafeRequest`, and no order path
  changed.
* `BWA11Y` — `bot_wizard.py`. Three coding highs and two accessibility
  highs. `_get_coin_icon` is annotated `Optional[QIcon]`, which is what
  all three callers already assumed, and the Extractor pool page gained
  tooltips and an accessible name.

**Also shipping, outside the twelve.** `main.py` now sets the asyncio
pump timer to `Qt.TimerType.PreciseTimer`. A QTimer whose type is never
set is coarse, and Qt allows a coarse timer 5% of drift plus permission
to coalesce with other timers. Measured on the operator's machine, 240
firings per configuration with the first 20 discarded: 62.63 ms median
for a 50 ms request, against 49.96 ms precise. `timeBeginPeriod(1)`
left the coarse median at 62.30 ms, so the timer type is the whole
difference. Every coroutine in this application runs on the Qt GUI
thread and this timer is the only thing that advances the loop, so its
cadence is the loop's cadence. Scope, so it is not mistaken for the
freeze fix: it recovers about 12.6 ms per pump cycle. It does not
explain a multi-second button delay and is not offered as one. This
change is in the tree and ships; it did not come through
`tools/.island_ledger.jsonl`.

**The splash is the ONLY version signal on this build. Windows file
properties carry none at all.** The artefact has no `RT_VERSION`
resource. `Acervator_win.spec:168` passes the block as `version_info=`,
and PyInstaller's `EXE` reads that keyword as `version` —
`PyInstaller/building/api.py:442`, `self.versrsrc = kwargs.get('version',
None)` — so the dict is accepted and discarded. Measured on the artefact
three ways: `pyi-grab_version` fails with WinError 1813, "the specified
resource type cannot be found in the image file"; the build log records
"Copying icon to EXE" and "Copying 0 resources to EXE" but never
"Copying version information to EXE"; and a UTF-16 search of the exe for
`Acervator v3.25.6` returns zero hits. The hardcoded `FileVersion`
`1.1.0.0` at `:171` therefore never reaches the file either, and neither
does the `FileDescription` built from `ACERVATOR_VERSION`. The
properties dialog will show nothing. Do not read that as "unchanged".
Read the splash. It prints `v{__version__}` from `src/__init__.py`, and
this package holds 3.25.6 in both copies: `_internal/src/__init__.py` on
disk, and the `src` collected into the PYZ from the same file in the
same build.

Reported, not repaired. The spec is not this change's to edit, and no
build has carried a version resource this way, so writing one now would
alter what the operator's file manager reports without a rule that asked
for it.

Gate `[OK] Release-ready (v3.25.6, 4690 tests)`, exit 0, run AFTER the
bump on the tree that was packaged. Ledger clean. The tree was hashed
before the gate and again after the build — 165 files, `main.py` plus
every `src/**/*.py` — so a promotion landing mid-package could not go
unseen. No test was weakened and no suppression was added.

---

## 3.25.5

Dead arbitration stack removed. 457 lines, two files, zero behaviour
change.

* `src/trading/capital_arbiter_bridge.py` (163 lines)
* `src/trading/opportunity_arbiter.py` (294 lines)

Operator directive 2026-08-10: "Do not connect to dead code. Clean it up
if you identify it as floating bloat that no other instance caught."
The Extractor Tranche Arbiter needed a name, and these two would have
read as its home.

**Proof of death.** Six independent methods, every one empty: AST import
graph over `src/`, `tests/`, `tools/` and `main.py`; raw text search for
each module plus every public symbol; dynamic reach through
`importlib`, `getattr`, entry points and string dispatch; test reach;
packaging manifests; and GUI reach including widget-building strings.
Neither module appears in the transitive import closure from `main.py`
plus `acervator_watchdog.py` (263 modules) or from 179 test files (551
modules). `opportunity_arbiter`'s only importer was
`capital_arbiter_bridge` — lazily at `:90`, and under `TYPE_CHECKING` at
`:45` — so the two had to go together or the second would leave a
dangling import.

**The instrument was calibrated before the measurement.** `known_good.py`
exit 0 `passed=True`; `known_bad.py` exit 1 `passed=False`; all nine
tools `ok`. Both reachability probes carried their own positive controls
— `gate_chain` and `ta_engine` as known-live modules — and both returned
reachable. A zero from a blind instrument would have proved nothing.

**Evidence the code never ran.** `capital_arbiter_bridge.py:156` assigned
`pool_capacity_fraction = free_usd`, a dollar amount, into a parameter
`opportunity_arbiter.py:275` documents as "total share of pool available
(0.0 to 1.0)". With a $200 pool and candidates at 0.1, roughly 2,000
candidates would fit. The cap was silently disabled. One real execution
would have surfaced it. Both files also FAILED `coding_archetype`:
`passed=False`, high=1 and high=5.

**What the adversarial pass found, and why it did not block.**
`_archive/tests_pre_2026_07_25/test_capital_arbiter_bridge_v3_20_81.py`
loads the bridge by STRING PATH at `:22-27` via
`importlib.util.spec_from_file_location`. That reference is invisible to
both text search on module names and AST import scanning, and neither
the prover's scan nor the adversary's own first pass saw it. It is inert
three ways: `pyproject.toml:33` sets `testpaths=["tests"]`, so `_archive`
is never collected; the test's own `REPO_ROOT` resolves into `_archive`
itself; and it points at a retired `sadp/` tree. Recorded because a
future un-archive would break it.

**Two briefing errors, corrected by the archetype.** The task briefing
claimed `capital_registry.py` "is imported by several live modules" —
false. Its only import was `capital_arbiter_bridge.py:44` under
`TYPE_CHECKING`. The live, widely-imported module is the similarly named
`capital_reservation.py` (9 importers), and the two were conflated. The
archetype kept `safe_to_remove=false` regardless, on the grounds that a
wrong reason does not grant standing to remove an operator-ruled file.
It also refused to count packaging as evidence: both `.spec` files use
`collect_submodules('src')`, so every module ships wholesale and that
method returns empty for live modules too.

**Kept, despite looking dead to a grep.** `smart_orders.py` — zero
importers, but it is the Volume Guard skeleton and operator-confirmed.
`volume_guard.py` — verified LIVE, `main.py:747-749` imports, constructs
and wires it. `capital_registry.py` — operator-ruled.

Gate `[OK] Release-ready, 2495 tests`, exit 0, ledger clean. Test count
2495 before and after: no test existed to exercise either module, so
none was lost. No file was edited and no test was weakened.

---

## 3.25.4

TA Quant compliance for queue item 1, under the operator rule of
2026-08-09: "TA Quant is now the only entity that is allowed to write
arithmetic."

`ta_archetype` reported **`passed = False`, 19 high** on
`src/trading/scrumming_bot.py` — 18 `TA004` and one `TA002`. v3.25.3 was
reported complete on the coding verdict alone, without ever running the
quant one.

**Every one was cleared by changing the code, not the rule.**
`tools/harness/ta_archetype.py` is untouched. The archetype was right
about the shape even where the arithmetic was correct: building a ratio
and comparing it against a configured percentage makes the units
implicit, and an implicit unit is how the Bollinger squeeze shipped as a
price test for four minor versions.

Decisions now compare like against like, and the ratios are retained for
the log lines only:

* `delta_pct` vs `scrumming_interval_pct` (5 sites) — now `abs(delta)`
  against `_interval_usd`. USD against USD.
* `move_pct` vs the circuit-breaker thresholds (2 sites) — now the
  candle range against `pct / 100 * open`. Price against price.
* `_dist_to_band` and `_dist_down` vs `detect_pct_frac` (5 sites) — now
  the absolute gap against `frac * band_span`.
* `band_travel_frac` vs `band_travel_pct` — absolute travel against
  `pct / 100 * band_width`.
* `scrum_asset` / `_fold_buy_units` vs exchange `min_amount` (2 sites) —
  now notional against `min_amount * price`.
* `drift_pct` vs `_TOLERANCE_PCT` — now `abs(drift_units)` against
  `_tolerance_units`. Units against units.
* `_own` vs `_uncapped` — the cap decision moved into USD and records
  itself in `_was_capped`, so no divided value is compared against an
  undivided one.
* `TA002` at the Slingshot skew — `min(1.0, ...)` gained its missing
  floor, `max(0.0, min(1.0, ...))`. A no-op on value; explicit on
  intent.

Also in this cascade:

* `apply_extractor_tranche_return` no longer executed `import math` on
  every call. `math` moved to module scope.
* **A bug this cascade introduced and fixed.** Renaming `_t_usd` to
  `_tranche_usd` in the fold-queue cap loop orphaned
  `_running_usd += _t_usd`, which would have read a stale binding from
  the distribution path. Caught by reading the block, not by a verdict —
  which is the failure mode of writing first and checking after.

Verdicts, all three item-1 files: `coding_archetype passed = True`,
0 high; `ta_archetype passed = True`, 0 high. Gate
`[OK] Release-ready (v3.25.3, 2495 tests)` exit 0, ledger clean after
`CLM-20260810-002` was verified against re-measured working-tree
evidence.

**Known, not fixed.** `S105`/`B105` still flag
`confirmation_token != "SELF-DESTRUCT"` as a hardcoded password. It is a
confirmation phrase and the operator-facing contract of
`self_destruct`, so it is suppressed at the line rather than renamed.

---

## 3.25.3

Redo of queue item 1 under the operator rule of 2026-08-09: "The Coding
Archetype is the only entity that is allowed to write code and must also
adversarial check all code."

`src/trading/scrumming_bot.py` now reports **`coding_archetype
passed = True`, 0 high** — from `passed = False`, 90 high. v3.25.2
shipped into that file while it failed, and was reported as done on a
delta ("90 before, 90 after") rather than on the verdict. A delta is
context; it is not a pass.

### Fixed — 3.25.3

- **98 silent exception swallows now log what they suppressed.** Every
  `except ...: pass` in the file binds the exception and emits
  `logger.debug("suppressed in %s: %s: %s", <function>, <type>, <exc>)`.
  78 were high-severity `S110`.

  This is not lint hygiene. The cascade validity sweep's lead finding is
  C16: capital-reservation failures across 25 live symbols were
  invisible because `_ensure_capital_reservation` is called inside
  `try/except Exception: logger.debug(...)`. One silent swallow hid a
  live-money defect for a day. These 98 are the same class.

  **Control flow is unchanged.** Each handler still catches exactly what
  it caught and still does not re-raise. The only difference is one
  debug record. The edit was applied to TEXT under AST guidance, so
  every comment survived — `ast.unparse` would have destroyed them
  across 12,000 lines.

- **`Any` was used in an annotation and never imported**
  (`scrumming_bot.py:332`, `capital_registry: Optional[Any]`). Latent
  only because `from __future__ import annotations` at `:38` defers
  evaluation. mypy `name-defined` and pyright `reportUndefinedVariable`
  both flagged it.

- **A construction guard written as an `assert`** (`:334`) is removed
  entirely under `python -O`, so the mode check did not exist in an
  optimised run. It is now an explicit `raise ValueError`. Nothing
  catches `AssertionError` from construction.

- Two missing annotations: `_htf_bias_detail` (`:7535`) and `raw_votes`
  (`:10022`).

- **A test pinned an implementation shape, not its invariant.**
  `test_increment_blocks_are_guarded_against_bad_values` matched the
  source with `r"# v3\.23\.78 — per-trade YTD .+?except.+?pass"`. Its
  stated invariant is that those blocks catch `(TypeError, ValueError)`
  and do not let them escape; `pass` was one way to spell that, and the
  regex broke while the invariant held.

  It now asserts the invariant on the AST, which is strictly stronger —
  a regex cannot tell whether a handler re-raises. Mutation-verified:
  narrowing the guard to `except ValueError` is CAUGHT, and adding a
  `raise` to the handler is CAUGHT. Source restored byte-identical after
  each.

### Removed — 3.25.3

- Four dead imports, each confirmed by AST to have zero `Name` uses
  before deletion: `field` (`:43`), `get_event_bus` (`:50`),
  `compute_heikin_ashi` and `TighteningResult` (`:53`).

### Verified — 3.25.3

- `coding_archetype`: `passed = True`, 0 high on
  `src/trading/scrumming_bot.py`, `tests/test_ytd_per_trade_increment.py`
  and `tests/test_extractor_tranche_containment.py`.
- Gate `[OK] Release-ready (v3.25.2, 2495 tests)`, exit 0, on the island
  before promotion and on the working tree after.
- `claim_ledger` CLM-20260810-001 logged, then verified against the
  re-measured working tree. `check` reports no open claims.
- `logger` is defined at `:71`; the earliest rewritten handler is at
  `:942` and no local binding shadows it, so no handler can raise
  `NameError` while logging.

### Known, not fixed

- `S105`/`B105` at `:3165` flag `confirmation_token != "SELF-DESTRUCT"`
  as a hardcoded password. It is a confirmation phrase, not a
  credential. Suppressed at the line with `# noqa: S105  # nosec B105`
  rather than renamed, because the string is the operator-facing
  contract of `self_destruct`.

## 3.25.2

Queue item 1: the Extractor Tranche containment primitive. Gate before
the bump: `[OK] Release-ready (v3.25.1, 2495 tests)`, exit 0.

### Added — 3.25.2

- **`ScrummingBot.apply_extractor_tranche_return`** — contains base
  currency returned by a child Extractor Tranche.

  Operator design 2026-08-09: "rather than have an immediate Base
  Currency to USD sell fire this profit off as Surplus we want it
  protected by lifting the Target Balance to contain it".

  The failure it prevents: a child Extractor sells its tranche and the
  gain folds back into the base currency balance. Holdings rise, so
  `current_value` rises, so `delta = current_value - _target_balance`
  (`scrumming_bot.py:6469`) goes positive, and the shipped model then
  says "If delta > 0 and delta_pct >= interval: SCRUM (sell excess)".
  The parent would sell the child's gain straight back out. Lifting the
  target by the arrival holds delta flat.

  Three properties, each deliberate:

  - **The lift is sized from an OBSERVED ARRIVAL, not a computed
    profit.** The caller passes what actually landed in the balance,
    already net of every fee the Extractor paid on both legs. Nothing there
    can be gross or net. Same exchange-truth principle as
    `buy_safety`.
  - **It is UNCAPPED.** `_apply_fold_target_growth` (`:1524`) applies
    the per-cycle Growth Rate Cap (`max_target_growth_pct`, default 1.0%
    of anchor). A cap is wrong for containment: a return larger than the
    cap would be truncated, the remainder would read as excess, and the
    parent would scrum exactly what the method exists to protect.
  - **It is FAIL-CLOSED.** Non-numeric, non-finite, zero and negative
    inputs are refused and mutate nothing.

  Target, anchor and `config.target_balance` move in one block,
  following the co-movement precedent at `:2148-2160`.

  Emits `extractor.tranche_contained` carrying `actual` = the observed
  target movement and `expected` = the arrival, so a cap or a partial
  write is falsifiable at runtime.

- `tests/test_extractor_tranche_containment.py`, 13 tests. The purpose
  test asserts delta is unchanged after an arrival; its paired positive
  control asserts that WITHOUT the containment call the same arrival
  drives delta to +$20 and past the scrum threshold. Without that pair
  the first test proves nothing.

### Verified — 3.25.2

- Written test-first. 12 of 13 failed before the method existed; the one
  that passed was the positive control, which does not call it.
- `coding_archetype` on `scrumming_bot.py`: 90 high before, 90 after.
  The first implementation added 2 (`ruff:S110`, `try`/`except`/`pass`
  in the two advisory handlers); both now log at debug instead of
  swallowing, and the count returned to baseline.
- Island gate `[OK] Release-ready (v3.25.1, 2495 tests)`, exit 0. The
  island first FAILED collection because `.claude/hooks` was omitted
  from the copy — `tests/test_release_gate_hook.py` needs it. Fidelity
  restored before the run was trusted.

## 3.25.1

### Fixed — 3.25.1

- **Load then Start was dead.** `_on_start_clicked` refuses when
  `_controller is not None and _run_in_flight()`. `_run_in_flight` read
  `not progress.finished`, and a fresh `ReplayProgress` has
  `finished = False`. That was harmless while only Start built a
  controller and `_controller` stayed `None` until then. This session's
  `_spawn_sim_fleet` makes Load build one at
  `fleet_replay_panel.py:550`, so after Load the guard saw a run in
  flight for a fleet that had never ticked and answered "A replay is
  already running."

  Measured on 37 loaded bots: `finished=False`, `candles_played=0`,
  `_run_in_flight()=True`, and `[FleetReplay] A replay is already
  running.` in the log with zero candles played.

  The controller already owns the honest test — `self._task is not None
  and not self._task.done()` at `fleet_replay_controller.py:510`. The
  panel now asks that first, then falls back to `started_at_wall`, which
  is `0.0` until a run actually starts (`:554`). Reset keeps its
  meaning: a live task is in flight, and so is a started run whose task
  reference is gone.

  Regression is uncommitted-only. It never shipped.

- **A test double that could not express the broken state.**
  `test_fleet_replay_panel_state_machine._Controller` modelled
  `progress.finished` alone. A real running controller also has `_task`
  (`:627`) and `started_at_wall` (`:554`). The double now carries all
  three, and a finished run gets a completed task rather than a
  contradiction — done replaying with the task still running. New case
  added for the state the double could not previously build: loaded, not
  started.

### Added — 3.25.1

- `tests/test_replay_start_guard.py`, 7 tests over the four controller
  states the guard must separate. Mutation-verified: restoring the old
  one-field guard fails them, and the panel was restored byte-identical
  after the check.

- [`docs/audits/2026-08-09_simulator_tab_complexity.md`](docs/audits/2026-08-09_simulator_tab_complexity.md)
  — the time and space pass the triage plan listed as not started.

  Measured over 1,500 candles with 37 bots: **0.0745 s/candle**, 13.4
  candles/s, extrapolating to 43.8 minutes for a full 35,282-candle run.
  Per-candle cost is flat — first-to-last block ratio 0.65x. The emitter
  sink holds 14 rows against a 2,000,000 cap, with 0 dropped.

  Two instrument errors are recorded there rather than hidden. The first
  harness pumped asyncio behind a 20 ms sleep and measured itself at
  1.0692 s/candle, extrapolating to 10.5 hours — caught because the
  panel already documents ~12.5 candles/s and the corrected harness
  reads 12.35. The second wrote `~/.acervator/feature_telemetry.json`
  because the probe never set `ACERVATOR_TELEMETRY_ROOT`; that was the
  probe's defect, and the override works.

## 3.25.0

Patch space in the `3.24.x` series ran to `.99`. The minor rolls; nothing
about this release is a break.

Closes the triage plan in
[`docs/audits/2026-08-09_simulator_tab_archetype_triage.md`](docs/audits/2026-08-09_simulator_tab_archetype_triage.md).
All 11 high findings on the Simulator tab are cleared. Gate:
`[OK] Release-ready (v3.24.99, 2474 tests)` before the bump.

### Fixed — 3.25.0

- **`_act` could be `None` and was called seven times.**
  `fleet_replay_panel.py:1242` bound `_act = self._activity_log_cb`
  unguarded. That attribute defaults to `None`; `set_log_callbacks` has
  one caller, behind a `hasattr` guard at `simulator_tab.py:249`. Any
  path that built the panel without that call raised `TypeError` on
  Start Replay. The same file already guarded it at lines 535, 546 and
  1322 — one binding of four was bare. It now uses the same fallback.

- **The router test asserted the rule the operator replaced.**
  `test_archetype_pick_logic_module_level` required exactly one
  archetype per file, so a Qt widget got `gui_archetype` and nothing
  else. `gui_archetype` runs 3 tools; `coding_archetype` runs 6. mypy,
  pyright, vulture and semgrep therefore never ran on any file under
  `src/gui/`. The test now asserts the SET, requires `coding` on every
  `.py` file, and keeps a negative half so a router that returned
  everything for everything would still fail. Verified by mutation: the
  old behaviour makes the test fail, and the file was restored
  byte-identical afterwards.

### Removed — 3.25.0

- Four dead imports: `Qt` and `QSizePolicy` (`fleet_replay_panel.py`),
  `Qt` (`sim_stat_strip.py`), `QTabBar` (`simulator_tab.py`). `QTabBar`
  was left behind when the tab bar became the mode dropdown in
  `3.24.97`. Each name was confirmed unused by AST, not by regex — an
  earlier regex pass reported false counts of 18/1/0/1 because the shell
  mangled the pattern.

- `MasterClock.progress_pct` and `FleetSimExchange.cursor_ts_ms`, both
  uncalled. `progress_pct` reports clock cursor position; the panel's
  on-screen percentage reports candles executed. Those are two different
  quantities, so wiring one to the other would have stated one number
  and measured another. `cursor_ts_ms` returned a per-symbol series row
  timestamp beside the authoritative `MasterClock.current_ts_ms()`.

### Added — 3.25.0

- **Spawn-over-spawn drift.** `load_sim_state` existed with no caller:
  `save_sim_state` clobbers `~/.acervator/simulator_bot_state.json` on
  every Load, so the persisted document was write-only and no Load could
  be told apart from the one before it. `diff_spawns` now reads the
  previous document before the overwrite and reports added, removed and
  changed bots on the activity log, plus a `sim.spawn_drift` emitter.

  It compares `source_state_at_load` — the live entry each sim bot was
  cloned from — and NOT the sim bot's own state, which is supposed to
  move once a replay runs. A live source that moved between two Loads
  means the live fleet traded, which is what has to be known before
  reading one replay as comparable to the last.

- `tests/test_sim_spawn_drift.py`, 12 tests. Each "no drift" case is
  paired with a case that produces drift, so a helper that returned an
  empty result for every input fails here.

### Verified — 3.25.0

- The Load button reaches `diff_spawns` on all three presses of a
  headless probe: press 1 `first_spawn=True, added=37`; press 2
  `changed=0, unchanged=37`; press 3, with one bot's saved source
  doctored, `changed=1` naming exactly that bot. Two presses reporting
  zero is also what a blind detector reports, so the third press is the
  control.
- Parity green 37/37 on every press.
- `~/.acervator` files changed by three Loads: **0**. `SIM_STATE_PATH`
  was redirected into the scratchpad before any widget was built.

## 3.24.99

### Fixed — 3.24.99

- **A fabricated citation shipped in v3.24.92 and is corrected here.** The
  `max_adoptable_usd` comments in `bot_container.py` and `scrumming_bot.py`,
  the `test_adoption_cap.py` docstring, and the v3.24.92 changelog entry all
  quoted Hummingbot's `balance limit` as keeping funds "left untouched for
  other bots or manual trading".

  That phrase appears NOWHERE in Hummingbot's documentation. The real wording
  is: "Sets the amount limit on how much assets Hummingbot can use in an
  exchange or wallet. This can be useful when running multiple bots on
  different trading pairs with same tokens."
  (https://hummingbot.org/client/global-configs/balance-limit/)

  The feature is real, the analogy is sound, and the real quote fits the case
  BETTER than the invention -- it names the multiple-bots-same-token scenario
  outright. Only the quotation marks were false.

  How it happened is the part worth keeping: the research document
  (`2026-08-09_position_attribution_shared_account_research.md`, line 89)
  carries the CORRECT quote. The fabrication entered when the code comment was
  written -- the real quote was paraphrased, and then the paraphrase was quoted.
  A correct source upstream did not prevent an invented citation downstream of
  it, and the invented one sat in a comment justifying a change to live trading
  configuration.

---

## 3.24.98

### Fixed — 3.24.98

- **History Gates column: two thirds of it was a dash over information that was
  already there.** `gate_cell_text` returned the same "—" BOTH when no gate
  record could be joined to a trade AND when a record existed but neither side
  armed. Those are opposite facts -- missing evidence versus evidence of a
  deliberate hold -- and the operator could not tell them apart.

  MEASURED on the live gate.log: 433 of 646 records (67%) have NEITHER side
  armed, and every one names the gate that held it. Rendered against all 648
  real records after the fix: ZERO bare dashes. Held rows now read
  `S⊘ delta≤0   F⊘ TA-not-bearish(dir=BULLISH)`; an unjoined row reads
  "no record".

- **The column now draws the Simulator's own `GateLightsCell`** -- the same ten
  labelled LEDs with the same colour semantics (grey not evaluated, green
  passed, red blocked, amber not-the-blocker). Operator, 2026-08-08: it "should
  align with gate row indicators found in the Simulator... This will keeps
  styling and readability consistent." One rendering shared by both surfaces
  rather than two that can drift. The widget is only used where a record
  exists: ten grey lights on a row with no data would read as "evaluated,
  nothing fired", which is the confusion being removed.

- **Gate tooltip rewritten** in the order the question is asked -- did anything
  arm, and if not what held it -- listing every blocker rather than a summary,
  and carrying the bot state, because "held" means something different in TRACK
  than in COOLDOWN. Dropping the state was a real regression in my first draft
  and `test_gate_tooltip_lists_scrum_and_fold_blockers` caught it.

- **Live-side voting panel column asymmetry** resolved by the v3.24.97 equal-
  column change; the confidence bars inherit it via `set_column_positions`.
  Measured across three panel widths: 1px spread on both tables and both bar
  strips.

### Changed — 3.24.98

- Two tooltip tests now assert PROPERTIES (both sides described, states
  distinguishable, every blocker named, missing join explains itself) instead of
  exact phrasing, so a clarity improvement no longer reads as a regression.

---

## 3.24.97

### Changed — 3.24.97

- **Nuclear is a Simulator MODE, not a tab.** Operator, 2026-08-09: "Nuclear
  does not need its own tab. Its needs to be integrated and available as mode of
  the Simulator via a drop down menu." The two-tab bar is replaced by a
  three-mode selector:

    Validation         Stone Tablets + paired YTD; verifies trade-gate parity
                       at DOCUMENTED events. Collects gate-latch agreement.
    Looping Back Test  loops the tablets with market-restructuring noise at a
                       fixed rate, for strategy development and calibration.
                       No generative behaviour beyond the noise; runs whatever
                       swarm and bots the operator set up manually or by live
                       import.
    Nuclear            load oscillation, swarm injection, high-traffic smart
                       wire. Collects performance, stability and reliability --
                       NOT trade validity.

  Each mode states on screen what it collects, so Nuclear's numbers cannot be
  read as trade validation. The noise source already existed
  (`nuclear_candle_source`, per-pass 10-25% forward/backward, operator directive
  2026-08-04): Looping Back Test is that looper without Nuclear's oscillation
  and swarm, Nuclear is the same looper with them. One implementation, two
  configurations.

- **Detail is wired to the SIM controller; Fire is disabled by design.**
  `mount_bot_status_table` called `cls()` with no arguments, so the table's
  `on_bot_clicked` and `on_fire_clicked` were both None and every button was
  dead while the columns rendered. Detail now resolves ids against the sim
  controller ONLY -- a Simulator surface that resolved against the live
  BotManager could open and edit a live bot from a test screen.

  Manual Fire stays unwired and is greyed with the reason on its tooltip.
  Operator: it "is not used for the Simulator which is intended to strictly test
  trading automation and make user intervention unnecessary." A Simulator whose
  result depends on someone pressing Fire is not testing automation.

### Fixed — 3.24.97

- **The test suite was dying with SIGSEGV and the gate could not say so.**
  Qt keeps a parentless widget alive for the life of the process; the GUI tests
  build whole SimulatorTab / FleetReplayPanel / BotLiveSettingsDialog trees, so
  they accumulated until the interpreter crashed -- exit 139 at roughly 90% of
  the suite, with NO failure summary. The release gate printed "pytest failed:"
  followed by nothing, which reads as a broken gate rather than a crashing
  suite.

  An autouse teardown in `tests/conftest.py` destroys top-level widgets after
  every test. Placed there rather than in each GUI file: it covers tests not yet
  written, and six copies of one fixture is six places for it to rot.

---

## 3.24.96

### Fixed — 3.24.96

- **Three Simulator methods were defined and never called.**
  `mount_bot_status_table`, `refresh_chart_bot_roster` and
  `refresh_active_bot_roster` each had exactly ONE occurrence across all of
  `src/` -- the definition. The Simulator kept its 3-column fleet table and two
  empty dropdowns while a probe that called those methods by hand reported them
  working. Now wired to `fleetLoaded`, the signal the Load button emits.

- **The bot table showed config defaults, not live state.** It rendered target
  $250.00 / 0 trades / 0 holdings while CHIP is $252.1391 with 363 trades and
  11,018.76 units. `bot_state_loader` already attaches the whole entry as
  `_src_scrumming_state` (38 fields) and `_src_stats` (36); the adapter ignored
  both. Rows now match the Trading Tab exactly.

- **Voting-panel columns.** v3.24.87 fixed truncation with
  ResizeToContents + stretchLastSection, which made the last column absorb all
  slack -- RSI ran the full panel width. Equal columns now, each no narrower
  than its label. "Comp Net" shortened to "Comp": one 84px outlier was setting
  the floor for nine 48px columns, and the pad trimmed from +10 to +2 because at
  1600x900 a 544px viewport allows at most 54px per column.

- **The chart panel is bisected** -- VWAP above, Stone Tablet candles below,
  sharing one x-axis. It previously drew VWAP over the candles, which was my
  choice and not the instruction.

- **An unimported `QFontMetrics` silently removed three panels.** The NameError
  was caught by an `except Exception` that logs at debug and nulls the widgets,
  so the chart, voting panel and picker all vanished while the tab still looked
  loaded.

### Added — 3.24.96

- **Load spawns the fleet.** 37 real `ScrummingBot` instances with imported
  lots, grown targets, `simulated_*` ids and isolated capital registries, built
  from the Stone Tablet registry via the same `reg.get_candles` path Start
  Replay uses. Bots no longer appear only at Start Replay, and the table is
  backed by real bots rather than dicts -- which also removes live bot ids from
  a simulator surface.

- **`simulator_bot_state.json`**, beside `bot_state` and never into it
  (`save_sim_state` refuses the live path). 37 bots, each recording its
  `source_bot_id` and a field-by-field parity record against the bot_state entry
  AS LOADED. 37/37 green on all 38 fields.

  Parity compares the LOAD-TIME SNAPSHOT, not a fresh read: the live app
  autosaves `bot_state.json` every 60 seconds (observed writes at 12:11:26 and
  12:12:26 with nothing else running), so re-reading produced false mismatches
  for any bot that traded mid-load.

### Verified — 3.24.96

- Sim fleet safety, cycled 50 master ticks with outbound sockets blocked at the
  OS level: 37 bots, 1,100 `bot.tick()` calls, 0 errors, **0 outbound connection
  attempts**, **0 files changed under `~/.acervator`**, 17 sim trades executed.
  Rejections report `API not called`.
- Tape candles byte-identical to the tablet files; timestamps still `int`;
  7 of 37 symbols live at the clock origin, the other 30 correctly refusing to
  serve until their tablet begins.
- The vote driving the bots is computed from tablet candles (12 indicators,
  net_score +0.3516) and the panel displays that same vote to the last digit.

---

## 3.24.95

### Fixed — 3.24.95

- **Trade-history scan storm: every symbol was scanned ~35 times at startup
  instead of once.** `CCXTConnector.refresh_history(symbol)` swapped the shared
  `_scan_symbols` set out and back:

      orig = self._scan_symbols.copy()
      self._scan_symbols = {symbol}
      self._scan_trade_history()
      self._scan_symbols = orig

  and `add_scan_symbol` calls it in a DAEMON THREAD PER SYMBOL. With 37 bots
  registering at startup, 37 threads raced on one mutable set: each replaced
  it, and `_scan_trade_history` iterated whatever was there at that instant --
  frequently another thread's restored snapshot of the whole registry. A thread
  meant to fetch 1 symbol fetched up to 37.

  MEASURED on the 3.24.94 launch: 37 distinct symbols, 1,294 scans, exactly
  35.0 per symbol, against N^2 = 1,369 for N = 37. 200 fetches in the first 24
  seconds.

  `TradeHistorian._fetch_sync` calls the RAW ccxt object, bypassing this
  connector's `_rate_limit()`, its single-worker `_call_sync` executor and its
  retry decorator -- therefore nothing spaced them. Coinbase rate-limited the lot and
  1,708 failures were logged as `TradeHistorian.analyze_sync(...)` errors. That
  is the wall of red present in console logs since 2026-07-30 and carried
  through every release since.

  Three parts: symbols pass as an argument instead of through a shared field
  (removes the race); a lock serialises concurrent scans; `scan_on_connect`
  paces between symbols at the connector's own configured interval, since the
  guards that would normally do that are bypassed on this path.

- `history.scan_complete` emitter -- expected = symbols requested, actual =
  symbols analysed.

### Added — 3.24.95

- 11 tests, including a negative control that FORCES the interleaving with
  events rather than waiting for a race. Two earlier versions of that control
  were unsound and are documented in the test: re-running the old body against
  the patched connector cannot race because the fix also added a lock, and a
  timing-based model does not race in-process because without real network I/O
  the window is a few bytecodes wide. In production the window is a live
  `fetch_my_trades` per symbol, which is why it fired on every launch.

---

## 3.24.94

### Investigated — no code change

- **Target Delta "glitchy and not showing correctly"** (operator, 2026-08-09;
  the reason BICO was deleted and recreated). The defect was NOT in the Ammo
  cell. `_compose_ammo_cell` renders its inputs correctly in every branch; it
  was being fed `holdings = 0` by the attribution bug that also caused the
  BICO/IMU double-buy.

  MEASURED with the operator's BICO position (347.96 units @ 0.0706380489,
  target $50):

      holdings correct            $25.4208            tracks price
      holdings 0, no cache        $50.0000            full target, FOLD
      holdings 0, stale cache     $25.4200 (stale)    FROZEN
      holdings present, no price  pending...

  The second row tells the operator to buy in to a position he already holds.
  The third serves the last cached value and keeps serving it, so the number
  stops tracking price — it does not move, which reads as a broken display
  rather than wrong holdings.

  Root cause already fixed: opening-position adoption (v3.24.85) and
  `max_adoptable_usd` (v3.24.92).

### Added — 3.24.94

- 13 tests pinning the Ammo cell across all four states, including a negative
  control proving the freeze is attributable to the holdings input rather than
  to the cell: with holdings present the same price move DOES change the delta.
  A regression in holdings attribution now fails with a name instead of
  surfacing as an operator deleting a bot.

---

## 3.24.93

### Fixed — 3.24.93

- **Fleet-wide capital-reservation over-commit, firing once per tick on nearly
  every bot.** Operator log 2026-08-08. Two independent causes, told apart by
  whether `existing` is zero.

  **The 110% claim.** `_compute_reservation_qty` returns `base_units * 1.10`;
  the 10% is drift headroom so a live bot is never left UNDER-reserved between
  ticks. But a bot at its target holds ~100% of target-worth, so the claim is
  ~110% of its own inventory and the guard refuses it — permanently, because
  the condition never changes. The log shows the arithmetic in plain sight:
  "existing reservations 0 + requested 80.3863967 > total holdings 74", and
  80.3863967 / 1.10 = 73.08 base units against 74 held. The claim is now capped
  at actual holdings; the margin still applies BELOW that ceiling, where it
  does its job. Not applied when holdings are unknown, so a transient
  balance-fetch failure cannot silently shrink a live reservation.

  **The orphaned token.** The failure handler set `_crr_token = None` without
  releasing the reservation, so the registry held units under a token nobody
  owned. The next ensure saw no token, called `reserve()` afresh, and the
  over-commit check counted the orphan — one failure became permanent. That is
  the second signature: "over-commit on LINK — existing reservations
  30.02068843 + requested 9.984649731". Nothing held 30 LINK under a live
  token; 30.02 was abandoned. The handler now releases before forgetting.

### Added — 3.24.93

- `bot.capital_reservation` on BOTH paths, throttled (60s success, 30s
  failure). The success record carries `capped`, so a bound ceiling stays
  visible instead of only surfacing once it stops working.

### Note

- `CapitalReservationRegistry(autosave=False)` still READS
  `~/.acervator/reservation_state.json` — `autosave` governs writes only. A
  test here omitted `state_path` and loaded the operator's live reservations,
  failing with his real LINK position (30.02068843) rather than its own
  fixture. The registry's docstring already warned about this. Sim is
  unaffected: `_make_sim_capital_registry` passes a temp path.

---

## 3.24.92

### Added — 3.24.92

- **`BotConfig.max_adoptable_usd` — a ceiling on what a bot may adopt from the
  exchange.** Default 0.0, meaning "use `target_balance`".

  Adoption (v3.24.85, a never-scrummed bot taking an operator-placed position
  as its opening lot) INFERS ownership from the exchange balance. Nothing on
  the exchange distinguishes "the seed the operator bought for this bot" from
  "coins the operator holds and wants left alone", so a fresh bot on an asset
  the operator already held would have taken all of it. The inference cannot
  answer that question; only the operator can.

  Modelled on Hummingbot's `balance limit` command, documented as: "Sets the
  amount limit on how much assets Hummingbot can use in an exchange or wallet.
  This can be useful when running multiple bots on different trading pairs with
  same tokens." — https://hummingbot.org/client/global-configs/balance-limit/
  Researched against Freqtrade, Hummingbot and Coinbase Portfolios —
  docs/audits/2026-08-09_position_attribution_shared_account_research.md.

  A bot asked to hold $25 no longer adopts $500 because it happened to be
  there. The cap only ever REDUCES: a holding below it is adopted whole, and a
  failed ticker read (price 0) leaves the holding alone rather than discarding
  a real position.

- `bot.adoption_capped` emitter plus an operator log line naming the lever,
  so a withheld surplus is stated once and loudly rather than silently skipped.

### Measured — 3.24.92

- 3 of 37 bots are eligible to adopt at all (never scrummed): LTC, LSETH,
  WLFI, each capped at its $25 target. Every other bot has scrum history, so
  adoption never runs and the cap is irrelevant to it.
- Conditional lot isolation was investigated and REJECTED. The fleet has 37
  distinct target assets across 37 bots — zero shared — so "isolate only when a
  sibling shares the asset" would have removed isolation from all 37 bots
  rather than narrowing it, reinstating the class of bug the BICO/IMU fix
  closed. `has_sibling_target_bots` stays wired for when two bots do share an
  asset.

---

## 3.24.91

### Changed — 3.24.91

- **The Simulator's bot area IS the Trading Tab's bot table.** Operator task
  2026-08-08, screenshot area 5: "Needs to be redesigned to match the Trading
  Tab's bot area."

  It mounts `BotStatusTable` -- the same class `main_window` mounts -- therefore the
  Simulator gets Bot ID, Symbol, Mode, Trades, Target, Target BTC, Target ETH,
  Ammo, Fire and Detail with the header dots, state colouring and Ammo
  arithmetic already built. Rebuilding those columns would have been the
  `FleetSimExchange` mistake a second time: a copy of something that exists,
  certain to drift.

  `FleetReplayPanel.sim_bot_statuses()` is the adapter, producing the exact
  status-dict shape `update_bots()` consumes, read off that method rather than
  guessed.

  The import is deferred by necessity: `main_window` imports `simulator_tab`
  (main_window.py:3971), so a module-scope import back would be a cycle.
  `SimulatorTab` is only ever constructed BY `main_window`, so resolving the
  class inside a method is safe, and returning None when it cannot be resolved
  keeps a headless import of the panel a legitimate caller.

### Added — 3.24.91

- **Active-simulator-bots dropdown.** Operator, same day: "Add a drop down menu
  for active simulator bots." Populated from the same adapter that fills the
  table, so the two cannot show different sets; keeps the operator's selection
  across a reload.

- `sim.bot_table.rendered` emitter -- expected = bots in the fleet, actual =
  rows rendered, throttled at 2s. A redesign that quietly drops a row would
  otherwise look exactly like one that works. 19 tests, including a negative
  control that reports ok=False when a row is missing.

---

## 3.24.90

### Added — the emitter message standard

Operator directives 2026-08-08, locking the contract before more emitters exist.

- **`module` is a first-class field.** "module not being a field is something we
  can fix and should in order to establish the emitter message standard."
  `site` carried `file:line`, so the module was implied but not queryable --
  grouping meant parsing a field whose line number changes on every edit.
  Auto-captured from the frame, like `site`.

- **`Signal.message()` — the operator-facing line.** `render()` was a debug repr
  that dumped the dataclass including `mappingproxy`; unreadable in a console
  and useless in a bug report. Fixed columns so a wall of them scans:

      HH:MM:SS  module            name                 VERDICT  detail  [context]

  PASS is terse, FAIL carries expected AND actual, a sample shows its
  observation. Context always trails, because that says which bot and which
  candle.

- **`kind` — check or sample, declared.** "expected=none is functionally useless
  as designed." It meant BOTH "a raw observation asserting nothing" and
  "somebody forgot an expectation", indistinguishable on 92.8% of records. A
  sample is now a declaration; a check without an expectation is a defect the
  contract can point at.

- **The synchroniser.** "I am concerned that because programs are constantly
  looping that some emitters (maybe most) will be spamming I/O messages."
  `emit(..., every=N)` admits one record per N seconds per (name, site) and
  folds the suppressed ones into the next record's `count`, so nothing vanishes
  silently -- the line says how many it stands for. Measured: 5,000 loop
  iterations collapse to 1 record.

  **A FAILING check is never suppressed.** Rate-limiting the thing the network
  exists to catch would turn a spam control into a blindfold. Measured: 500
  failing emits with a 3600s window all wrote.

  Keyed by (name, site) rather than name alone -- the same signal from two
  places is two things to a reader. `reset_throttle()` clears windows and any
  pending tally; that limit is pinned by test rather than left to be
  discovered.

23 tests. JSON field order is now ts, seq, module, name, kind, ok, expected,
actual, count, site, context.

---

## 3.24.89

### Added — 3.24.89

- **Stone Tablet candle playback.** Operator task 2026-08-08, screenshot area 4.
  The chart drew a close-only polyline because a close was all it received;
  `append_tick` now takes the whole bar (OHLC optional, so close-only callers
  still work) and the focused view draws real candles -- green up, red down,
  wick from high to low -- with the VWAP polyline over them rather than beside
  them.

- **One bot at a time, chosen from a dropdown.** Operator, same day: "show one
  chart and have the others be displayed when their respective bot is selected
  from the drop down menu." Stacked bands gave each of 37 symbols 36px, in
  which a candle body is a smudge. The picker sits under the chart's header,
  defaults to "All (bands)", repopulates on fleet load, and keeps the
  operator's selection across a reload when that symbol is still present.

- **YTD overlay from the first documented historical trade.** Shaded region
  plus a dashed boundary, starting at `ValidationWindow.soft_start_ms`.

### Fixed — 3.24.89

- **YTD overlay units.** `gate_first_ts` and `trade_ts` are SECONDS --
  `compute_validation_window` converts via `soft_start_ms = int(oldest * 1000)`
  -- while candles are int MILLISECONDS. The first wiring passed the seconds
  value straight through, which makes every candle satisfy `ts >= ytd_from`
  (1.78e12 >= 1.78e9) and shades the entire warm-up as validated. Measured on
  an 80-bar series: seconds shaded 80/80, milliseconds shade 40/80.

- **`GateStatusPanel` was a leaked top-level window.** Built with no parent in
  `FleetReplayPanel.__init__`, it only acquired an owner if a host reparented
  it. Every panel constructed without one -- every headless test -- leaked a
  top-level widget, and enough accumulating across a suite run SEGFAULTED Qt
  (exit 139, once 127, no failure summary, crash point moving between runs).
  Now parented at construction. The new GUI tests also destroy top-level
  widgets after each test; three consecutive full-suite runs are clean.

---

## 3.24.88

### Fixed — 3.24.88

- **The Simulator price chart had stopped receiving data entirely.**
  `_collect_visual_snapshot` read the current candle from
  `exchange._series[sym].get_current()`. When the Simulator moved onto
  `CCXTConnector` + `TabletBackend` in 3.24.84, `_series` ceased to exist on
  either object; `getattr(exchange, "_series", {})` returned an empty dict, so
  `close` stayed None and the chart drew nothing on every refresh. Nothing
  raised. Introduced by that migration and repaired here -- the feed now reads
  the tape.

### Added — 3.24.88

- **Whole candles in the visual snapshot.** The feed carried close and volume
  only; `ts`/`open`/`high`/`low` are now included, which Stone Tablet candle
  playback needs (operator task 2026-08-08, screenshot area 4). The tape always
  had them.

- **Process-level signal collection.** Operator, 2026-08-08: "Emitters don't
  work unless program is running or a debug is performed." Accurate --
  `set_sink` had a single caller, the Fleet Replay controller, so outside a
  replay every `emit()` in the platform was inert and the expected-vs-actual
  network said nothing about live operation. `install_process_sink()` is now
  called from `main()`, and a replay RESTORES the prior sink instead of
  clearing it to None, so live collection resumes when a run ends rather than
  stopping for the rest of the session.

- `sim.price_chart.fed` emitter, and `tests/test_price_chart_feed.py` -- 7
  tests that fail against the broken feed and pass against the repaired one.
  The tests are the guard that runs unattended in the release gate; the emitter
  is the runtime complement.

---

## 3.24.87

### Fixed — 3.24.87

- **Indicator Voting Panel truncated its own column headers**, in the Simulator
  AND the Trading Tab. Operator task 2026-08-08, screenshot area 3.

  The cause was not a shortage of space. `QHeaderView.Stretch` divides width
  EVENLY regardless of what each label needs, so measured at 1920x1080 the
  10-column table had 584px for 564px of content -- more than required -- and
  truncated anyway, because the surplus went to columns that did not want it:
  `Comp Net` needed 108px and got 61 (rendering as "omp N"), while `BB` needed
  36px and also got 61. No extra width fixes an even split.

  Columns now size to content with the last section absorbing the slack, and
  the table + header type drop one point per "will have to adjust text sizes as
  needed". Content width fell 564px -> 373px against a 544-582px viewport, so
  it fits at 1920x1080, 1600x900 and 1366x768 with room to spare.

### Added — 3.24.87

- **`gui.voting_panel.fit` emitter** and `header_fit_report()`, added before the
  layout change so the fix could be measured rather than eyeballed.

  The instrument took two corrections, both recorded in its docstring. It first
  compared QFontMetrics + an invented 12px against the column width; Qt's own
  padding is 4px, so it reported every column 8px short even when correct. It
  then compared `columnWidth` against `sectionSizeHint` -- equal by construction
  under `ResizeToContents`, so it passed both a good layout and a table squeezed
  to 90px. It now measures total content width against the VIEWPORT, which is
  what actually decides whether a header is clipped, and its negative control
  fails when the table is squeezed.

---

## 3.24.86

### Changed — 3.24.86

- **Simulator: the gate status display moved out of the fleet table** into its
  own pane, where the Performance Log used to sit. Operator task 2026-08-08,
  screenshot area 2. It was column 3 of the table, one `GateLightsCell` per row;
  a ten-LED labelled row is bounded by the column width, which is why the labels
  stayed cramped even after v3.24.18 measured the pitch from the widest label.
  MEASURED: a gate row asks for 700px of natural width and the table column gave
  it ~100px.

  This is a MOVE. The same `GateLightsCell` paints, `update_gates` keeps its
  signature, and the colour semantics are untouched. `GateStatusPanel` owns one
  labelled row per bot; `FleetReplayPanel` builds it because it knows the fleet,
  and the Simulator tab positions it because it owns the layout. The fleet table
  is now three columns.

### Added — 3.24.86

- **`sim.gate_status.rendered` emitter** on the render path, added BEFORE the
  move. Only `feature_telemetry` watched it, counting calls and skips with no
  expected-vs-actual, so a migration that silently painted fewer rows would have
  looked identical to one that worked. Carries `expected` (bots reporting gate
  state), `actual` (rows painted) and `host` (where they painted). Measured on
  the real 37-bot fleet: 37 rows, host=panel, one panel instance.

- `_gate_cell_for()` — the single point that resolves where a gate row lives,
  so the display can move without rewriting every call site that paints one.

---

## 3.24.85

### Changed — 3.24.85

- **Simulator: the Activity and Performance logs are now one pane**, on the
  left where the Activity Log sat. Operator task 2026-08-08, screenshot area 1.
  `FleetReplayController` writes to two callbacks -- 22 `activity_log_cb` calls
  and 5 `performance_log_cb` -- therefore both stay on the public surface and both land
  in the same widget; `log_performance` tags its lines `[perf]` so merging panes
  does not merge meaning. The right half is reserved for the gate status display
  (area 2).

### Added — 3.24.85

- **`sim.log.line` emitter** on both simulator log streams. Neither had one:
  `feature_telemetry` counted calls and skips but carried no
  expected-vs-actual, so "both streams still arrive after the merge" was not a
  checkable claim. The emitter carries the stream identity, which is the
  property a merge destroys -- one widget receiving everything is otherwise
  indistinguishable from one widget receiving a single stream twice. Measured on
  a real tab: 27 records, activity=22 performance=5, 27 lines in the single
  pane, 5 tagged.

### Fixed — 3.24.85

- `_on_perf_paused` removed with the second pane. It called `setText` on a
  button that no longer exists, so any caller would have raised
  `AttributeError`. The single pause button now drives both stream flags.

---

## 3.24.84

### Fixed — 3.24.84

- **A bot that has never scrummed now treats the exchange as its opening
  position.** v3.23.43 made `_main_lots` the sole source of holdings and applied
  it unconditionally. That rule exists to stop a bot claiming units belonging to
  the operator, a sibling bot, or a prior bot on the asset -- all statements
  about a bot with TRADING HISTORY. A bot that has never scrummed has no history
  for a surplus to be measured against, so it reported $0.00 while the operator
  was looking at coins on the exchange.

  The condition is `_tranches_created_lifetime == 0`, not "no lots" -- BICO and
  IMU carry a lot from the erroneous cartridge buy while their scrum history is
  still zero, so keying on empty lots would have missed exactly the bots that
  needed it. Isolation remains in force when a sibling bot targets the same
  asset: those units are subtracted rather than claimed.

### Added — 3.24.84

- **Autonomous fires are verified against the exchange before they trade.**
  `_execute_manual_rebalance` bypasses the gate chain by design -- no TA, no BB
  thresholds, no MEM-171 floor. That is acceptable for a button the operator
  pressed; it is not acceptable for `wire_stack` and `max_cartridge`, where
  `delta_usd` was the only thing between a bad holdings number and a market
  order.

  Those two intents now re-read the target asset balance and refuse to trade if
  it disagrees with the bot's own position by more than the dust band, if the
  exchange omitted the currency, or if the balance cannot be read. On the buy
  side a hard ceiling is enforced -- position may not exceed
  `Target x (1 + Max Target Growth %/100)`, which the live-settings tooltip has
  stated as a guarantee (MEM-246/249/251) while nothing on this path enforced
  it. Operator-pressed fires are exempt.

  This is independent of the holdings fix above: it refuses on any disagreement
  with the exchange, whatever produced it.

---

## 3.24.83

### Fixed — 3.24.83

- **Live settings dialog: eight settings groups were invisible on any bot that
  had never traded.** `bot_live_settings.py:2486`, the `if _over:` branch that
  reports fold tranches exceeding the per-cycle budget, had swallowed 287
  statements instead of its intended 2. Scrumming Settings, Advanced Scrumming,
  Hedge Rebalance, Circuit Breakers, Self-Destruct, Risk Controls, Strategy Gate
  Flags and Profit Routing were all constructed and then added to the layout
  only when `_over` was non-empty. A bot with no fold tranches has an empty
  `_over`, so every one of them was discarded and the Settings tab ended after
  Trading Parameters.

  Operator report 2026-08-09: BICO/USDC and IMU/USDC, both created that day,
  showed no scrumming settings while AERO/USDC showed them in full. Both are
  USDC pairs — the base currency was never the discriminator; having traded was.

- **ADX ran at ~14x its definitional maximum.** `ADXIndicator._wilder_smooth`
  documented itself as returning `sum/period` and returned the sum. +DI/-DI are
  a ratio of two of its outputs so the scale cancelled, but DX is already a
  0-100 percentage. Measured across 1174 records: 99.8% of ADX readings exceeded
  100, max 761.5, and `strong_trend`/`parabolic` were true on 100% of them.
  `ADXTrendSuppressionGate.adx_threshold` reset 500.0 -> 30.0 in the same
  change, as that gate's own docstring required.

- **Bollinger `squeeze` was a test on price, not volatility.** `band_width` is
  dimensionless (divided by the mean) while the historical widths it was
  compared against were absolute price units, so the flag reduced to
  `mid > 1.33`. Measured across all 35 fleet symbols: every symbol at or below
  $0.42 squeezed on 0.0% of windows, every symbol at or above $8.28 on 100.0%.
  After the fix all 35 land between 17.7% and 29.6%.

- **Slingshot `squeeze_conf` was clamped on one side only** and reported
  confidences as low as -0.2722.

### Changed — 3.24.83

- The Simulator now runs live's `CCXTConnector` with a Stone Tablet backend
  (`src/exchange/tablet_backend.py`) beneath it, rather than a parallel
  re-implementation. Normalisation, `_parse_order`, fee reading and the
  documented ccxt quirks are now the same code in both modes.
- A bot that has never scrummed adopts an operator-placed position as its
  opening lot instead of reading $0.00 and buying a second one.

---

## [3.24.82] - 2026-08-08 — per-candle TA capture, raw values, simulated_ ids

RAW INDICATOR VALUES, PER INDICATOR, PER CANDLE. Operator directive:
"capturing the raw indicator values so we [have] more comparative data",
and "one entry per indicator and measurement for every candle that ticks
through the reader".

`Signal.details` already held each indicator's internals — bollinger's
upper/middle/lower/bb_position, macd's macd_line/signal_line/histogram,
zscore's z/sma/std. Nothing persisted them, so a run held a DIRECTION
and a CONFIDENCE but not the numbers they came from. Two runs could
disagree with no way to see where.

`ta.raw.<indicator>` emits per indicator (not one blob) so a single
indicator is queryable across a whole run, carrying `candle_ts` and
`window` — which is what makes a value RECOMPUTABLE. Also the address
YTD trade events need.

PER-CANDLE TA OBSERVATION. The bot's own TA runs on ~4% of ticks: the
read-rate throttle exits early on ~91%. That throttle limits how often a
bot ACTS — in live each action tick costs an exchange call. It says
nothing about how often TA can be COMPUTED. `compute_all` is stateless
and places no orders, so the replay loop now computes it every candle
for observation. Trade behaviour and live parity are untouched.

PER-BOT COVERAGE, not a fleet ratio. A bot has no candle at a
master-clock tick predating its own tablet — measured, SPK's first 300
candles are 2026-01-01 and CHIP's are 2026-04-21. A
candles_played x bots denominator is wrong by construction. On a common
window all bots read 350/399 = 87.72%, the 49-candle shortfall being
exactly the 51-row warm-up guard.

INDICATOR CORRECTNESS VERIFIED by independent recomputation against
textbook definitions on 600 real CHIP candles: Bollinger mid/upper/lower
and bb_position, ZScore z (population sigma, -1.345, not sample -1.332),
Kaufman ER, MACD line, RSI (Wilder). Five of five match. Seven others
have implementation-variant choices where writing an "independent"
version from the engine's own source would prove nothing.

SIM IDS ARE `simulated_<live id>`. Operator: this "marries a live bot
with its simulated equivalent." Self-identifying (a sim row cannot be
read as live) and joinable (strip the prefix for bot_state).
`sim_bot_id` is idempotent; `live_bot_id` is its inverse.

THE TRAP THAT CAME WITH IT: wires are keyed by the PERSISTED id.
Prefixing bots alone would leave live ids in `_wires` and sim ids in
`_bot_refs` — disjoint key spaces, `get_outgoing_wires` returns {}, and
the run logs "40 wires imported" while routing $0.00. That is exactly
the failure C20 was opened for. Both endpoints are translated; verified
$20.00 delivered at the wire's 20%, and the raw-id lookup asserted EMPTY
in both directions.

Suite 2219.

## [3.24.81] - 2026-08-08 — bot_state is the initiating state; the real voting panel

TWO THINGS THE SIMULATOR WAS DOING INSTEAD OF WHAT IT WAS TOLD.

1. IT INVENTED ITS OWN STARTING STATE.

`bot_state_loader` returned `entry["config"]` only. `scrumming_state`
(38 keys: lots, tranches, the grown target, anchors, hysteresis) and
`stats` (36 keys) were dropped whole. `_build_sim` then SYNTHESISED an
opening position — `target_balance / open_price` — and its own comment
admitted the substitution: "current_holdings is not persisted in
bot_state... so target_balance is the import."

Operator directive: "bot_state determines the initiating state... NO
OTHER SOURCE FOR INITIATING STATE SHOULD BE CITED OR EXPECTED."

`import_scrumming_state` (scrumming_bot.py:3786) already existed and is
what LIVE calls at bot_container.py:3217. The sim simply never fed it.
Now it does. The synthetic deposit block is DELETED, not deprecated.

Positions now come from the fleet's own restored lots, per the invariant
at scrumming_bot.py:550 — sum(l["units"] for l in _main_lots) ==
_current_holdings. MEM-254 deliberately does not persist holdings
(exchange is authoritative, handshake repopulates); live queries a real
exchange, the sim has none, so the sim exchange is seeded from the lots
rather than from an invented figure.

Measured on the real fleet:
  CHIP/USD  lots=175  units=10174.208381  target=$252.14  anchor=$250.00
  SPK/USD   lots= 40  units= 9582.635659  target=$200.76  tranches=105
  XRP/USD   lots= 27  units=   41.164747  target=$ 75.77  tranches= 26

Every bot previously opened with ZERO lots, ZERO tranches and the
ORIGINAL config target. SPK now carries 105 real tranches.

STATE PARITY, bit-identical, as a round trip: `import_scrumming_state`
is the inverse of `export_scrumming_state`, so a faithful import
re-exports exactly what it was given. Compared as canonical JSON so
nested lot and tranche CONTENTS count — a lot list of the right length
with wrong contents fails. Measured: 38 of 38 fields identical on every
bot. `fleet.state_parity` emits the differing field NAMES, because a
count would say parity broke without saying where.

2. THE TA VOTING PANEL WAS A LOOKALIKE.

The Simulator mounted `PerBotVotingReadout` — a 6-column summary table
(Symbol/Net/Conf/Bull/Bear/Direction) written for the sim. The Trading
Tab mounts `IndicatorVotingPanel` (main_window.py:3652): 12 indicators
across two rows with per-indicator bars, bot selector and TF lock. Two
different widgets under the same title is not a match.

The Simulator now mounts the SAME CLASS, fed through the same contract
`update_data(multi_tf_summary, symbol)` at all three sites — Fleet
Replay bot list, Fleet Replay per-tick, and Nuclear. Verified rendering
real engine output:

  TF  BB     VTX    MACD   SRsi   Ichi   Vol   Net    Comp Net  Conf
  5m  ▲ 78%  ▼ 44%  ▼ 60%  ▲ 20%  ▼ 11%  ─ 0%  -1.86  —         16%

NEW EMITTERS: fleet.state_imported, fleet.positions_seeded_from_lots,
fleet.state_parity, sim.candles_stepped, sim.bot_ticks_did_work,
sim.trades_fired, sim.exceptions, sim.window_played, ta.computed,
tick.worked, tick.throttled, topology.wires_received,
topology.bot_attached.

`ta.computed` is emitted at ta_engine.py's compute_all — the true site
every TA computation passes through. Measured on a real replay: 1800
tick entries, 177 worked, 73 TA computations. Directive 2 ("per-candle
TA every tick") reports NOT SATISFIED, from data, at the sites where the
work happens. `bots_ticked` would have reported 1800.

Suite 2208 -> 2219.

## [3.24.80] - 2026-08-08 — Emitters that carry their own expectation

The static gates read SOURCE. They cannot catch a false claim about RUNTIME.
"Per-candle TA ran", "the tablets were processed", "the swarm was driven" were
all asserted and all wrong, and no gate could have known. Measured: Nuclear
computes TA on ~2-5% of ticks (read-rate throttle, scrumming_bot.py:5046), and
NOTHING in the run artifacts recorded it — `bots_ticked` counts tick ENTRIES,
so the ~91% that return early are indistinguishable from the ~5% that compute.

`src/core/signal_contract.py` (new). One record carries name, location,
declared expectation, observation, and verdict.

EMITS ON THE SUCCESS PATH, which is the whole point. Research surveyed Design
by Contract, the Linux kernel Runtime Verification subsystem, JavaMOP and
icontract: every one is FAILURE-TRIGGERED and emits nothing when the
expectation holds. Silence is then indistinguishable from never-executed —
exactly the class of false claim this exists to make impossible.

The record shape is not invented: Great Expectations'
`ExpectationValidationResult` binds declared-expectation + verdict +
observation in one persisted record. One deliberate departure — GX lets the
observed half be suppressed by a result-format tier; here `actual` is
MANDATORY. A record that can drop its observation degrades to a pass/fail bit,
which is what we already had.

Design constraints taken from THIS codebase, not from a paper:
- NO I/O ON THE EMIT PATH. `EventBus.emit` calls subscribers "synchronously on
  the caller's thread", and the sim ticks on the loop main.py pumps from the Qt
  GUI thread. Buffered; flushed every 200 rows, mirroring SimRunLog.
- NOT routed through EventBus: `Event.data` is handed to subscribers by
  reference, so any subscriber can mutate it — which violates the no-mutation
  rule outright.
- IMMUTABLE. `freeze()` deep-freezes actual/expected/context. This closed a
  hole in the module's OWN contract: `actual` was stored by reference, so a
  caller mutating it after emitting rewrote the record retroactively.
  Demonstrated and fixed.

FEATURE EMITTERS, built feature-by-feature against the operator's stated
directives rather than in the abstract:

S1, bot_state half — `fleet.bots_loaded`, `fleet.bot_ids_mirror_live`,
`fleet.sections_imported`, `fleet.wires_loaded`. The old record was
`meta.json config.bots`, a COUNT, which cannot evidence WHICH bots loaded or
what was dropped. `fleet.sections_imported` now records ok=False naming the 5
sections that drop whole — `stats` (36 keys) and `scrumming_state` (38 keys)
among them, which is where positions and the grown targets live.

S1, YTD half — `ytd.trades_fetched`, `ytd.fleet_symbol_coverage`,
`ytd.per_symbol_counts`. YTD is the operator's REAL live trade history and the
REFERENCE DATASET: S3 is defined as diffing gate outputs against it, and it is
the defence against a self-consistent lie. It was fetched into panel memory,
used for anchors, and lost when the panel died, with a logger.info the only
trace. Coverage is judged — a fleet symbol with no YTD trades has no reference
to diff against, so S3 cannot speak for that bot.

CONSOLE SIGNALS PANE. Operator directive: wire the emitters into the console
for later refinement when upgrading the Watchdog. Split below the existing raw
log tail. POLLED via `since(seq)`, not pushed: emit must stay I/O-free on the
tick path, and a push would arrive on whatever thread emitted — a cross-thread
touch for a Qt widget. Two defects found by actually rendering it: `appendHtml`
silently SWALLOWED any payload containing angle brackets (a site of "<stdin>"
vanished, leaving ":23"; most object reprs look like "<Foo at 0x...>"), and
`mappingproxy(...)` leaked the freeze implementation into the operator's view.
Both fixed — everything escaped, `render()` added.

Suite 2159 -> 2208.

## [3.24.79] - 2026-08-08 — Market Inspector strategy injection reaches Nuclear

Operator: Nuclear *"is supposed to be able to receive strategy injections from
the Market Inspector to test the strategy propagation function and swarm
topologies under cycling load."*

`NuclearFleetController.set_topologies` had existed with **zero callers**, so
the proposal branch of `_topology_pairs` never ran — which is precisely why the
fabricated circular fallback beneath it survived unnoticed until v3.24.76
deleted it. This is the caller it was missing.

The chain: `MainWindow` → `SimulatorTab.set_topology_getter` →
`NuclearModePanel.set_topology_getter` → `set_topologies` at Start. A getter,
resolved at Start rather than at wiring time, so a soak stresses what the
operator has on screen when they press it. Every hop degrades to no-injection
rather than raising: a broken Market Inspector should cost the soak its
injection, never its ability to run. With none, the fleet's own persisted
bot_state topology stands — nothing is invented to fill the gap.

**THE SAFETY LINE.** Market Inspector already has an **adopt** path —
`adoptClicked` → `adoptRequested` → `MainWindow._adopt_topology_proposal` —
which creates **real bots and real wires on the live fleet**. Stressing a
proposal in Nuclear is a separate journey that must never reach it. Three pins
defend the separation rather than just the connection:

- the Nuclear panel references no adopt orchestrator, `create_bot` or `add_bot`;
- `_topology_pairs` reads the proposal's `wires` but **never its `bots` key** —
  that key is the adopt path's create-these-bots instruction, and a stress run
  instantiates only the fleet from `bot_state`;
- a **negative control** that the live adopt wiring still exists, so separation
  cannot be achieved by accidentally deleting adoption.

- `market_inspector_topologies.py` — `current_proposals()`, returning a copy so
  a consumer cannot mutate what the pane renders.
- `market_inspector.py` — `current_topology_proposals()`, `[]` when the pane
  never constructed.
- `nuclear_mode_panel.py`, `simulator_tab.py`, `main_window.py` — the seam.
- `tests/test_nuclear_receives_topology_injections.py` (new, 13 pins) — 9 RED.

**Process correction, on the operator's OCIR rule — Observe, Calibrate,
Iterate, Repeat.** The v3.24.78 SIGSEGV happened because every suite run this
session set `QT_QPA_PLATFORM=offscreen` while the release gate sets nothing —
the same tests, a friendlier measurement, and one that cannot see Qt
lifetime bugs. The rule has teeth at *Calibrate*, which is the step that was
skipped. This version was validated by running
`check_release_readiness` **on the island before promoting** — the gate's own
invocation, ahead of touching the working tree — which reported
`[OK] Release-ready (2155 tests)` before a single file moved.

Suite 2142 -> **2155**.

## [3.24.78] - 2026-08-08 — Nuclear Mode is repointed at the fleet controller (W3)

The tab labelled Nuclear Mode drove `NuclearController` — the Phase-B
single-tape prototype `NuclearFleetController` was written to replace. W3 had
this recorded for months, and `simulator_tab.py` said it in-tree: *"Nuclear
panel still hosts the old tape-based prototype."*

Operator: Nuclear *"does not run on a single tape or stone tablet. It runs
stone tablets in a loop through the simulator bots."*

**Four things differed, each its own failure if missed.**

*Construction.* v1 needed a tape cache and a selected tape id. v2 needs
neither — it reads the fleet from `bot_state` itself.

*Lifecycle.* v1's `start(loop)` is **sync**; v2's `start()` is a **coroutine**.
Calling it like v1 yields an un-awaited coroutine: nothing runs, nothing
raises, and the buttons latch into the running state over a soak that does not
exist. Now scheduled with `run_coroutine_threadsafe` onto the loop `main.py`
pumps from the Qt GUI thread.

*Gating.* `prepare()` returns False with an operator-readable reason (no
bot_state, no scrumming bots, no tablets). Gated on **before** anything is
scheduled.

*Vocabulary.* The readout asked for `scout_state`, `tape_position`,
`tape_wraps`… v2 emits `cycles_completed`, `load_multiplier`, `cooling`,
`failed_cycles`. Only `running` and `uptime_seconds` overlapped, so a careless
repoint leaves eleven rows permanently blank — wired-looking and reporting
nothing.

- Tape selector → **fleet readout**. Nothing remains to select: the fleet *is*
  `bot_state`. It shows what Start will load, verified against the live file:
  `35 bot(s) · 35 symbol(s) · 40 Smart Wire(s) from bot_state`.
- Scout seed / world-clock → **cycle length, max cycles, market-noise toggle,
  load-oscillation toggle**. The two toggles are deliberately separate: one
  varies what the market does, the other how hard the machine works.
- `noise_pct` and `wires_loaded` added to `snapshot()` and surfaced. A varied
  market structure the operator cannot see is indistinguishable from an
  unvaried one, and a run that silently loaded zero wires must be readable off
  the panel.
- `tests/test_nuclear_panel_drives_v2.py` (new, 16 pins) — 9 RED. Includes a
  pin that every `_STATUS_FIELDS` key exists in `snapshot()`, and controls
  proving v2's `start` is a coroutine while v1's is not, so the scheduling code
  keeps its stated reason.

**A crash I introduced and had to chase.** After promoting, the release gate
went `[FAIL]` with the suite dying at ~90% — **exit 139, SIGSEGV**, no
traceback, surfacing inside `test_suite_integrity.py`, which has nothing to do
with this panel. It reproduced only under the gate's invocation, because the
gate runs pytest **without** `QT_QPA_PLATFORM=offscreen` and every run of mine
had set it.

Two hypotheses died before the real one: blocking disk I/O in the constructor
(measured — 13–18 ms, not blocking) and randomized test order (the plugin is
not configured). Bisecting by stashing showed the baseline completing cleanly,
and `--ignore` on the new test file made the crash vanish — **the tests were
the fault, not the repoint.** They built `NuclearModePanel(parent=None)`, an
orphan top-level widget owning a `QTimer`; Python then collected the wrapper at
an arbitrary later moment while Qt's C++ side was mid-teardown. Panels are now
parented to a fixture-owned widget so Qt controls the lifetime. `deleteLater()`
alone would not do it — that needs an event-loop turn a headless run does not
guarantee.

Suite 2126 -> **2142**.

## [3.24.77] - 2026-08-08 — Nuclear drives the Simulator Swarm

Operator directive: *"Nuclear Mode is expected to use and abuse the Simulator
Bot Swarm."* It never did, for two independent reasons — either alone was
sufficient to make it silent.

**1. The register hook had the wrong shape.**
`BotVisualizationTab.register_sim_run(sim_id, label, cfg)` takes **three**
arguments. Nuclear called its hook with **two** — passing the config dict where
`label` goes and omitting `cfg` entirely. A `TypeError` on the first cycle,
swallowed to `logger.debug`, so the rows never appeared and nothing said why.
`nuclear_verification.py:19` had recorded the symptom without the cause:
*"register_sim_run() zero callers -> swarm rows never driven."*

**2. Nothing ever called `set_swarm_hooks`.** Zero callers repo-wide, so all
three hooks stayed `None` and every call site inside the controller was a no-op
regardless of shape. The row API lives on `BotVisualizationTab` — a different
top-level tab from `SimulatorTab` — and nothing connected them.

The chain now exists end to end: `MainWindow` → `SimulatorTab.set_swarm_getter`
→ `NuclearModePanel.set_swarm_getter` → `set_swarm_hooks` at Start. Passed as a
**getter**, not a bound instance: `_bot_viz` is built before `_simulator`
today, but binding here would make the wiring depend on that order never
changing. Resolved at Start, when both tabs certainly exist. Every hop degrades
to no-swarm rather than raising — a soak that cannot draw its rows is still a
valid soak.

**A reporting defect fixed in the same pass.** Nuclear passed
`float(progress.trades_fired)` as the row's **PnL**, so the swarm would have
rendered *"PnL +37.00"* for 37 trades — a count formatted as dollars. Nuclear
does not measure P&L; it measures coverage and survival, against a deliberately
noised tape that is not history. It now reports `0.0` and says why at the call
site. A real number in the wrong unit is worse than no number.

- `nuclear_fleet_controller.py` — three-argument register; `0.0` PnL on update
  and stop.
- `simulator_tab.py`, `nuclear_mode_panel.py`, `main_window.py` — the seam.
- `tests/test_nuclear_drives_the_sim_swarm.py` (new, 9 pins) — 5 RED. The shape
  pins read the **real consumer's** signature out of `bot_visualizer.py` rather
  than hard-coding 3, so if that API changes the pin says so instead of
  enforcing a stale contract. An **AST** pin holds the production caller in
  `main_window.py` — without it, `set_swarm_getter` would exist and never be
  called, which is exactly the defect class C58 is queued to catch.

*Acknowledged, not fixed: `main_window.py` fails its archetype gate with 9 high
findings — verified identical on the untouched baseline, so this change adds
none. Rewriting unrelated parts of a 6,000-line file is not in scope here.*

Suite 2117 -> **2126**.

## [3.24.76] - 2026-08-08 — Nuclear wires the REAL fleet; the invented topology is deleted

Operator directive: *"The ONLY source beyond the user adding new bots manually
to Simulator or Paper Trader must be a fleet load that references bot_state and
**all pieces / functions of the fleet must import**."* And: *"no more inventing
things to generate results from elements that exist and must be tested."*

**What was wrong.** `_topology_pairs` had two branches: Market Inspector
proposals when injected, otherwise a hard-coded circular wire chain — bot 1 →
bot 2 → … → last → bot 1 at a fixed percentage. Nothing designed that circle as
a strategy; it was invented so the tranche-chain verifier would have *some*
wires to exercise, back when no simulator path built Smart Wires at all.

The proposal branch **never ran**, because `set_topologies` has zero callers
anywhere in the codebase. Every Nuclear cycle ever executed therefore took the
fallback and silently rewired the operator's fleet into a circle that exists
nowhere in `bot_state` — and every coverage number it produced described a
topology the operator does not have.

Meanwhile `bot_state`'s top-level `smart_wires` were never loaded into Nuclear
at all.

**The corrected hierarchy has no invented tier:**

1. Injected Market Inspector proposals — the strategy-propagation and
   swarm-topology test the mode exists for.
2. Otherwise the fleet's **persisted wires from `bot_state`**, imported with
   the fleet like every other piece of it.
3. Neither → wire **nothing**, and say so. A fleet with no topology is a
   finding about the fleet, not a licence to give it one.

- `nuclear_fleet_controller.py` — `prepare()` loads `smart_wires` alongside the
  configs, so a run cannot start without them; `_run_cycle` passes them to its
  `FleetReplayController`, which already knows how to import and attach them
  (C20/v3.24.72); the circular fallback is **deleted**.
- `_wire_topology` no longer builds a second `SmartWireManager` and reassigns
  `bot._smart_wire_mgr`. That would have discarded the operator's real topology
  on every cycle — the moment Nuclear started passing `smart_wires=`, the
  collision that did not previously exist would have become real. An injected
  proposal is now registered **on top of** the fleet's own manager, so the
  strategy is stressed against the real topology rather than instead of it.
- Each of the three outcomes is announced distinctly in the activity log, and a
  pin holds them apart — an unfalsifiable "no wires" message is worth nothing.
- `tests/test_nuclear_uses_the_real_fleet_topology.py` (new, 9 pins) — 6 RED.
  Two are **AST** pins that no modular index and no `range()` over the bot-id
  list remain in `_topology_pairs`: generating wires positionally from the bot
  list is the structural signature of manufacturing a topology instead of
  loading one.

*Every fleet in that test file is a small synthetic fixture and is labelled as
such. The operator's real fleet is 35 bots and 40 persisted wires; no test
touches it.*

Suite 2108 -> **2117**.

## [3.24.75] - 2026-08-08 — Nuclear · boot armour, and a Stop that actually stops

Two preconditions for repointing the Nuclear panel at v2. Neither is glamorous;
both are the difference between "it works after building" and not.

**1. A failing Nuclear panel could kill application startup.**
`simulator_tab.py` imported and constructed `NuclearModePanel` with **no
guard** — while the sibling `FleetReplayPanel` eight lines above *is* guarded,
with a `None` fallback and a placeholder label. Nothing upstream catches
either: `SimulatorTab()`, `_setup_ui()` and `MainWindow(...)` are all bare on
that path, AST-verified. An exception in that constructor therefore did not
degrade the Simulator tab, it killed the launch.

The repoint edits that constructor, so this lands first. Guarded now, with a
placeholder that says *why* the pane is empty — and the failure is **audible**:
`main_window.py` already carries NF-162, a silent guard that failed on every
boot with nothing ever saying so. A panel that vanishes quietly is worse than
one that crashes, because a crash gets investigated.

**2. Stop did not reach the running fleets.**
`stop_requested` was written by `request_stop()` and read in exactly **one**
place — the between-cycles `while` in `_run`. Nothing inside a cycle read it,
and the child `FleetReplayController` (which has a working `request_stop()`)
was a local inside the `_one()` closure, so nothing outside could reach it to
ask.

A cycle is 3000 candles across up to 6 gathered fleets. At the measured
~25.8 candles/s that is **minutes of an unresponsive Stop**, on the single
asyncio loop `main.py` pumps from the Qt GUI thread and shares with live
trading. The realistic failure of "must launch AND run" is not a crash — it is
an application that ignores the operator.

Also added `is_running()` and `stop()`, which the panel already calls and
which existed only on v1. Repointing without them is an `AttributeError` on the
first Stop click; a pin now holds v2's surface against v1's.

- `simulator_tab.py` — guarded import + construction, audible failure,
  placeholder page (the mode bar adds two tabs unconditionally, so the stack
  must keep two pages or selecting Nuclear indexes past the end).
- `nuclear_fleet_controller.py` — `is_running()`, `stop()`; a `_live_fleets`
  registry populated **before** `await ctl.start()` (the await is a suspension
  point, so a Stop arriving during start would otherwise find an empty
  registry), drained in a `finally` so a crashed worker cannot leave a stale
  controller for the next cycle's Stop to poke; `request_stop()` fans out
  best-effort per child; and an in-cycle `stop_requested` check so a slow child
  cannot hold the operator for the rest of the cycle.
- `tests/test_simulator_tab_boot_armour.py` (new, 8 pins) — 6 RED.
- `tests/test_nuclear_stop_is_responsive.py` (new, 7 pins) — 6 RED.

**A test-isolation defect worth recording.** The boot-armour log assertion used
`caplog`; it passed alone and failed in the full suite. `logging_engine.py:341`
sets `logging.getLogger("acervator").propagate = False`, so once any other test
initialises the logging engine, records from `acervator.simulator_tab` stop at
that ancestor and never reach caplog's root handler. The test was asserting on
a delivery path another test globally disables — a real defect in the test, not
a flake. It now observes the module logger directly.

*No collision after all:* an earlier note claimed Nuclear's `_wire_topology`
overwrites C20's persisted Smart Wires. It does not. Nuclear constructs its
`FleetReplayController` with six kwargs and no `smart_wires=`, so
`_build_smart_wires` returns early and C20's manager is never built on a
Nuclear run. The stale docstring is real; the conflict was not.

Suite 2093 -> **2108**.

## [3.24.74] - 2026-08-07 — C23/SN-25 · A refused start froze the shared event loop

**This is the one that had to land before the Nuclear panel is repointed.**

`FleetReplayController.start()` creates `stopped_event` and **sets** it —
*"not-yet-started = already stopped"* — and only clears it **after** both early
returns. On a refusal the event is therefore set while `progress.finished` is
still False. The Nuclear worker then ran the obvious wait:

    while not ctl.progress.finished:
        await asyncio.wait_for(ctl.stopped_event.wait(), timeout=0.5)

Awaiting an **already-set** Event completes without ever suspending, so the
`timeout=0.5` never fires and the loop never yields.

**Measured, with a positive control, before the fix: 477,043 iterations in one
second with a competing coroutine advancing ZERO.** Not a busy poll — total
starvation. Reproduced against the real controller by the new pin: *"the loop
spun 172542 times and NOTHING else on the event loop ran."*

`main.py:1085-1092` pumps **one** asyncio loop from the Qt GUI thread
(`loop.run_forever()` on a 50 ms QTimer), shared by every live coroutine. A
coroutine that never suspends means `run_forever()` never returns — the GUI
thread and live trading freeze together. The `timeout=0.5` reading like a
mitigation is what let this survive review.

Latent only because `NuclearFleetController` has no production caller. It ships
the instant the panel is repointed at it, which is why it lands first.

**The two refusals are not symmetric — and the cold read that found this got
that part wrong.** It prescribed setting `progress.finished = True` on *both*
paths. That is wrong for "Controller already running": another replay owns that
progress and is mid-flight, so marking it finished would tell
`fleet_replay_panel.py:1532` to stop the progress timer and drain the final
frame of a live run, and `_run_in_flight` at `:487` would let Reset discard it.
Only the "no bots instantiated" path — where nothing launched — may touch it.

- `fleet_replay_controller.py` — `start()` returns `bool`; the no-bots refusal
  closes out `progress.finished`; the already-running refusal deliberately
  touches nothing.
- `nuclear_fleet_controller.py` — honours the refusal instead of waiting on a
  fleet that never launched, plus an independent `WORKER_WAIT_CAP_S` wall-clock
  bound and an explicit `sleep(0)`, so any future finished-but-not-stopped
  window degrades to a slow poll rather than a freeze.
- `tests/test_start_refusal_does_not_spin.py` (new, 9 pins) — 5 observed RED.
  Carries a **negative control** that the probe can still detect an unbounded
  spin, because the fix makes the loop exit immediately and a bound that can no
  longer observe the failure proves nothing. Every await is individually
  wall-clock bounded: `pytest-timeout` is not installed here, so a hang must
  fail rather than wedge the suite.

*A test correction worth recording: the first version asserted the competitor
must advance — a symptom's signature rather than the property. The fix makes
the loop exit on the first check, so the competitor legitimately never gets a
window, and that assertion failed on correct code. It now checks the property
with both branches: exit promptly, or yield while looping.*

Suite 2084 -> **2093**.

## [3.24.73] - 2026-08-07 — Nuclear · the loop now varies the market, not just the load

Operator, 2026-08-07: Nuclear *"does not run on a single tape or stone tablet.
It runs stone tablets in a loop through the simulator bots. These loops are
supposed to have varied market structure via an oscillator that injects noise
to simulate varied market structures **without writing over the stone
tablets**."*

`NuclearFleetController` loaded tablets once and handed the **same dict** to
every cycle. Its oscillator is `SystemLoadOscillator` — CPU load, not market
structure — so the loop varied how hard the machine worked while replaying a
byte-identical tape. A bot can learn one fixed tape; that is the entire reason
the noise exists.

The perturbation itself was never missing. `NuclearCandleSource._Tape` has had
it since v3.24.20. Only Nuclear v1 used it.

- `nuclear_candle_source.py` — new `noised_series(rows, seed)`, promoted next to
  `_Tape` as THE canonical perturbation. `topology_stress._noised_rows` now
  delegates to it instead of hand-copying the `_Tape` construction. Its own
  docstring gave the reason: a second implementation *"could drift from it, and
  then a stress result would describe a market structure the operator never
  actually simulates."* Three copies would let the stress backtester and both
  Nuclear versions each simulate a different market while reporting the same
  noise percentage.
- `nuclear_fleet_controller.py` — `_noised_candles_for_cycle(idx)` produces one
  perturbed **copy** per cycle; `noise_enabled=False` returns the tablets
  untouched, which is how an operator asks *"does this fail on the clean tape
  too?"*
- `NuclearCycle.noise_pct` recorded and serialized — a varied structure the
  operator cannot see is indistinguishable from an unvaried one, and a soak
  report that cannot say **which** market a failure happened in is an anecdote.

**The cycle is the unit of structure.** All workers within a cycle share one
noised tape: concurrency is the *load* stressor, and giving each worker its own
market would mean one cycle's results described several markets at once.

**Seeding is fixed, not random.** `DEFAULT_NOISE_SEED` with the cycle index
mixed in, so cycle 40 replays identically after it fails. Drawing from the
existing `_rng` would have coupled a cycle's market to how many unrelated
jitter draws preceded it, making the same index differ between runs that took
different load paths. Pass `seed=` for a different sequence.

Stone Tablets are never written: `noised_series` copies, and nothing here
touches disk. Timestamps are never perturbed — the master clock stays
authoritative — and the OHLC invariant is re-established after perturbation.

- `tests/test_nuclear_cycle_noise.py` (new, 18 pins) — positive control that
  the perturbation is not a no-op, non-aliasing and non-mutation of the source
  tablets, per-pass coherence (deterministic in `(seed, idx)`, because
  `history()` re-reads the same indices every tick and moving values would
  compute TA over a series that never existed), and a pin that
  `topology_stress` produces the byte-identical series.

*Nuclear is not a validation instrument — its noised tape deliberately is not
history, so nothing here compares trades to YTD or live. See the audit's
section 1.0.*

Suite 2066 -> **2084**.

## [3.24.72] - 2026-08-07 — C20 · Smart Wires reach the sim, and stop reaching the live bus

The parity harness now runs with the fleet's persisted Smart Wires. Two
failures were designed against, because the cascade plan would have shipped
both.

**1. A harness that reports wires and routes nothing.** `import_wires`
(`smart_wire.py:456-478`) performs **no existence check** — it `setdefault`s
every well-formed row and returns the count. The plan's exit criterion was
*"the replay reports 40 wires active"*, which that satisfies while nothing
moves. Nothing here asserts an import count. The activity log reports
`N of M imported wire(s) have BOTH endpoints in this run's fleet and can
route`, computed against the actual instantiated fleet — which matters
because the sim fleet is filtered by `available_symbols`, so a partial tablet
set silently produces exactly the inert case. A zero-active run warns
explicitly that the accumulation curve will understate live's.

**2. A sim manager emitting on the operator's live bus.** The plan said *"the
class has no bus and no singleton"* and cited
`nuclear_fleet_controller.py:551` — `SmartWireManager()` — as the precedent to
copy. No singleton is right; **no bus is wrong**. The class takes `bus=None`
(`smart_wire.py:217`) and both emit paths resolve the process-wide
`get_event_bus()` when it is None (`:507-511`, `:695-698`) and emit `bot.log`.
`smart_wire.py:220-226` already quotes that plan sentence and answers *"That
correction is itself wrong."*

**The cited precedent was the leak, and this is measured, not argued.** The
premise control in the new test file passes on the **unmodified** baseline: a
bus-less `SmartWireManager` with wires registered genuinely does reach a spy
subscribed to the live bus. (The leak only arms once wires exist — with none,
`smart_wire.py:500-501` returns before the bus is resolved, so a naive version
of that test would pass for the wrong reason.) `nuclear_fleet_controller.py`
is fixed in the same commit rather than left standing as a cited precedent.

The model copied is live's own: `bot_container.py:1621`
`SmartWireManager(bus=self._bus)`. No single "sim bus" exists to borrow — each
sim bot builds its own `EventBus()` — so the controller owns a dedicated one.

A **synthetic** fleet gets no manager at all. Wires key on the persisted bot
id; against uuid4s nothing resolves, and a manager holding wires that can
never fire is the same green-log-zero-effect state.

Ledgers are deliberately **not** imported. Live's persisted rows carry accrued
`wired_in`/`wired_out`; seeding them would satisfy a "non-zero `wired_in`"
check without a single sim wire firing.

- `bot_state_loader.py` — new `load_smart_wires_from_state()`, read-only.
- `fleet_replay_controller.py` — `smart_wires` parameter; `_build_smart_wires`
  after the bot loop so both endpoints exist; endpoint-resolved active count.
- `fleet_replay_panel.py` — Load reads the wires; the controller receives them.
- `nuclear_fleet_controller.py` — private bus injected.
- `tests/test_build_sim_smart_wires.py` (new, 22 pins) — 16 observed RED on the
  unmodified baseline. Includes the live-bus premise control, a negative
  control that an unwired bot routes nothing, and AST pins that the panel
  actually feeds the feature — every other test builds the controller directly,
  which proves the manager works but not that production ever calls it.

Suite 2044 -> **2066**.

## [3.24.71] - 2026-08-07 — C20 · Sim bots ran under ids that existed nowhere else

`ScrummingBot.__init__` mints `str(uuid.uuid4())[:8]`
(`bot_container.py:881`) and nothing overrode it on the sim path. The
persisted per-bot config carries no `bot_id` at all — 0 of 35 verified — so
every Fleet Replay bot has always run under an identifier that appears in no
other system.

**Why that matters, and why it lands before the Smart Wire work.** Wires are
keyed by the persisted id: `get_outgoing_wires(source_id)` reads
`self._wires.get(source_id, {})` (`smart_wire.py:344`) and the bot passes
`source_id=self.bot_id` (`scrumming_bot.py:8706`). Import 40 wires keyed by
live ids, register 40 bots keyed by uuid4s, and the two key spaces never
meet — and `import_wires` performs **no existence check**
(`smart_wire.py:456-478`), so it would have reported all 40 while every scrum
took its early return at `scrumming_bot.py:1788`. A harness logging
"40 wires active" and routing **$0.00**.

Landing the remap first means that failure cannot hide behind a green import
count.

**The join key already existed and was read by nothing.**
`bot_state_loader.py:86` stamps `_src_bot_id`. A grep of `src/` found exactly
one other occurrence: a comment. It was also excluded from the dropped-keys
debug log by the underscore filter at `fleet_replay_controller.py:304-306`, so
its uselessness was invisible. This mirrors live's own restore rather than
inventing a mechanism — `bot_container.py:3160-3161`
`# Preserve original bot ID` / `bot.bot_id = bid` is exactly why live's
`import_wires` works.

**A first draft of this was wrong and is worth recording.** It raised whenever
`_src_bot_id` was absent from a config. That broke 8 existing tests, and
chasing the breakage found the reason: `topology_stress.py:214` builds configs
from **proposal** bot entries — hypothetical bots that do not exist in
`bot_state` and never will. No persisted id exists to carry, and demanding
one would have broken the Nuclear topology stress backtester at runtime. That
is the same defect C18 shipped: a precondition hand-built configs cannot
satisfy, which breaks the caller instead of the bug.

The check therefore moved from the **config** to the **fleet**:

- every config carries an id → join, and say so
- no config carries one → synthetic fleet, keep uuid4s, and **say so loudly** —
  silence is what let the mismatch survive this long
- some do and some do not → cannot be anything but a broken join → **raise**,
  naming the symbol and the ratio

The 8 tests pass **unmodified** under the corrected design, because their
fixtures genuinely are synthetic fleets.

- `fleet_replay_controller.py` — fleet-level join decision before the bot loop;
  `bot.bot_id` set from `_src_bot_id`; both outcomes announced in the activity
  log.
- `tests/test_build_sim_bot_id_remap.py` (new, 14 pins) — 7 observed RED on the
  unmodified baseline. Includes a positive control that bots are constructed at
  all, and a pin that the key survives the BotConfig passthrough filter, which
  keeps only BotConfig fields and would drop it if `_build_sim` ever stopped
  iterating the raw dicts.

Suite 2030 -> **2044**.

## [3.24.70] - 2026-08-07 — C20/NF-18 · Anchors were computed in the wrong index space

`build_anchor_indices` computed a slot on a gapless 5-minute ruler:

    idx = int((ts * 1000.0 - base_ts_ms) // step_ms)

The run loop compares that against `candle_i` — the **MasterClock cursor**, a
position in `sorted(union_of_every_series_timestamp)`. Two different spaces,
with nothing converting between them. They agree only while the union has no
gaps.

**Measured on the 35 live tablets** (read-only) rather than assumed:

    union size       61,201 candles    2026-01-01 -> 2026-08-01
    longest single   61,200 candles
    MISSING SLOTS    79  across exactly 3 gaps
      +1  slot  after 2026-02-19 22:15   cumulative drift +1
      +77 slots after 2026-05-08 01:15   cumulative drift +78   (~6.4 h outage)
      +1  slot  after 2026-05-08 19:45   cumulative drift +79

**No trade is dropped.** Drift (79) stays below `warmup` (100), so the true
candle remains inside `range(idx-100, idx+1)`. What is lost is warm-up DEPTH:
every trade after 2026-05-08 got **21 real warm-up candles instead of 100** —
a 79% truncated TA window on a harness whose entire purpose is that simulated
indicators match live ones. Before 2026-05-08 the drift is +1 and negligible.

Margin is 21 candles. One more outage of that size and the anchored run starts
skipping the very candles it exists to evaluate, silently.

The BOUND was in the wrong space too, though barely: the panel passes
`progress.total_candles or max(len(r) for r in candles.values())`, and
`progress.total_candles` is assigned inside `start()` — which runs *after*
`_build_sim()` and after the panel has already built its anchors. The fallback
therefore fired on every run. Practical error: **one candle** (61,200 vs
61,201).

- `fleet_replay_controller.py` — new `clock_timestamps_from_candles()`, pinned
  bit-identical to `MasterClock.from_series`; `build_anchor_indices` takes
  `clock_ts_ms` and bisects into it. The grid path is retained for
  `clock_ts_ms=None` because it is exactly correct on a gapless union — a
  documented fallback, not an equivalent.
- `fleet_replay_panel.py` — both call sites pass the union, as clock and as
  bound.
- `tests/test_fleet_replay_anchors.py` (new, 15 pins) — including a positive
  control that the fixture really does separate the two spaces, and a negative
  control that a gapless union leaves both answers identical.

**Two stale comments corrected in the same path.** One claimed anchored mode
saves `15,212 -> 4,258 candles (28%)`; the most recent recorded run shows
**14,598 of 15,212** — ~4% saved. The other said *"a skipped candle cannot
produce a sim trade"* — **false**, and the panel repeated it to the operator as
fact in the activity log. The skip path still calls `_exchange.step()`, which
sweeps resting limit orders, so a skipped candle can settle a fill placed on an
earlier one. What gets skipped is `bot.tick()`, not the exchange.

Suite 2015 -> **2030**.

## [3.24.69] - 2026-08-07 — SN-18 · Closed as not-a-defect, and the docstring that caused it

SN-18 said the sim's `crosses` test is unconditionally true for every
order the fleet places. That is **true**, and it is **intended**.

`fill_price` applies one-directional adverse slippage — `abs()` of a
zero-mean gauss — and the bot places its LIMIT *at* that slipped price.
A sell lands below the bid, a buy above the ask: marketable by
construction, so `crosses` is always true.

`scrumming_bot.py:10929` already documented why, in the code that does
it: *"For LIMIT orders the exec_price below already includes a -0.1%
drift for **fast fill**."* The bot deliberately places a marketable
limit to guarantee execution; `verify_hit` is the cap that cancels when
the drift exceeds per-asset-class tolerance. **Removing the `abs()` to
make limits rest would make live orders less likely to fill** — a
strategy change degrading execution on a live fleet, dressed as a fix.

What *is* true is narrower and is not a correctness defect: Fleet's
resting-order model is never exercised by the fleet, because the fleet
never places a non-marketable limit. A coverage gap in the harness. The
resting code works and is pinned by `test_fleet_sim_infrastructure.py`.

**The docstring that produced the wrong reading.** `fill_price`
described itself as a *"zero-mean half-normal"* draw. Those cannot both
hold: `abs()` of a zero-mean normal *is* a half-normal, whose mean is
`spread × √(2/π)` — strictly positive. The underlying gauss is
zero-mean; the slippage applied is not.

The wording matters more than a typo would, because it invites the
conclusion that slippage cancels out across fills and can be ignored in
aggregate. It cannot. Over N fills the expected cost is
`N × price × spread × √(2/π)`, and on an accumulation platform doing
thousands of small fills that is a real cost, not a rounding error.

Corrected, with the SN-18 reasoning recorded at the function so the next
audit doesn't re-derive "limits always cross" and call it a bug again.

- `src/core/execution_discipline.py` — docstring corrected; adverse-by-
  design and the marketable-limit rationale recorded inline
- `tests/test_slippage_is_adverse.py` (new, 10 pins) — slippage is
  one-directional in both trade directions, its mean matches
  `spread × √(2/π)` within 10%, and it does **not** cancel over 20k
  fills. Positive control (the draw actually varies) and negative
  control (zero spread ⇒ zero slippage, so the displacement comes from
  the spread and not a baked-in constant).
- `docs/audits/2026-08-05_remediation_methodology.md` — SN-18 closure
  recorded at the finding. **SN-19 stands and is unaffected**:
  `Balance.used` is still hardcoded and resting orders still pledge
  nothing.

Suite 2005 → **2015**.

## [3.24.68] - 2026-08-07 — C19/SN-20 · The two sim venues disagreed on the smallest order

Second pass on C19, tier sim-only.

    Fleet    min_cost = 1.00
    Nuclear  min_cost = 0.01

A **100x gap** in the smallest order either harness accepts. The same
strategy replayed on both produced different trade **counts** — small
orders Nuclear took and Fleet rejected — and a difference appearing on
one venue and not the other reads as a finding rather than a harness
artefact. That is the hazard C19 names, present in the limits table
rather than the order path.

Aligned on the **higher** floor deliberately. A too-low minimum lets the
sim place orders the real exchange would refuse, so the harness reports
fills that could never happen — false positives, in the direction that
flatters a strategy. A too-high floor only suppresses trades, which
shows up honestly as a lower trade count.

### What remains of SN-20, stated accurately

The finding asks for *real* per-symbol limits. Those are exchange
**metadata**, and no capture step exists for them yet — unlike candles,
which the Stone Tablets already capture and append. Nothing about this
requires the Simulator to make a live call at run time; it runs off
tablets and YTD data. What is missing is a periodic metadata capture of
the same shape the tablets already perform.

Until that exists the uniform value is a placeholder, and both sites now
say so explicitly with a note to keep them in step. A fabricated uniform
limit that is *not* labelled is how the next reader concludes the sim
honours venue limits.

Suite 2005 passing.

---

## [3.24.67] - 2026-08-07 — C19/SN-21 · Aggressive mode could not be simulated

Second pass on C19, tier sim-only. **Suite passes 2000 tests.**

The two venues failed on `IOC_LIMIT` in **opposite directions**:

- **Fleet** ended its dispatch in `else: raise ... unsupported type`, so
  an IOC order **aborted the whole run**.
- **Nuclear** tested only `OrderType.LIMIT`, so an IOC fell through to
  the market path and filled at the close with the **limit price
  discarded**. Reproduced: an IOC BUY capped at 99.0 filled at 100.0,
  and an uncrossed 1.00 bid came back `FILLED`.

One harness refused to run; the other ran and reported a fill the real
order would never have taken. **Two venues disagreeing is worse than
both being wrong the same way**, because a result that appears on one
and not the other reads as a finding.

### This was not waiting on Stack Mode

The cascade plan attributes the `IOC_LIMIT` dependency to C40a (Stack
Mode, unshipped). It is already live: `scrumming_bot.py:10529` selects
`OrderType.IOC_LIMIT` whenever **Aggressive mode** is on. A mode the
operator can enable today therefore could not be replayed in Fleet at
all, and was replayed wrongly in Nuclear.

### Semantics

Immediate-or-Cancel is the LIMIT crosses test plus the one difference
that **defines** the type — it never rests:

    crosses  -> fill, at min(limit, close) / max(limit, close)
    no cross -> CANCELLED, not OPEN

`CANCELLED` rather than `OPEN` is the whole point. An IOC that rests
*is* a LIMIT, and a simulator that converts one into the other tells the
operator their taker-forcing order got a maker fill.

`min`/`max` on both venues: the limit is a ceiling for a BUY and a floor
for a SELL, but a fill must never be **worse** than the market actually
was.

A negative control pins that making IOC cancel did not also make plain
LIMIT cancel — Fleet still rests those, Nuclear is single-shot by
design, and flattening that difference is what the no-shared-helper
reasoning protects.

Suite 2000 passing.

---

## [3.24.66] - 2026-08-07 — C19/SN-17 · Sim orders settled against money that was not there

Second pass on C19, tier sim-only. Applied to **both** venues, since two
harnesses that disagree mean neither is authoritative.

Neither venue read a balance before debiting it. Both `_adjust_balance`
bodies were plain addition — no floor, no compare, no raise. A BUY with
no quote currency settled and drove the balance negative; a SELL of coins
never held settled too. Reproduced before the fix on each venue:
`{'USD': -50.0}`.

**This is quieter than it sounds.** Every number downstream of a sim run
is denominated in that ledger, so a replay that spent money it never had
still reported P&L, fill counts and target-growth figures — computed
against an impossible starting position, with nothing indicating
anything was wrong. The run did not fail; it lied.

- **Fleet**: the guard sits in `_settle_fill`, the single mutation choke
  point. All three settle paths (MARKET, LIMIT-crosses, and the
  open-order **sweep**) funnel through it. Guarding the entry points
  instead would need writing three times and would miss the sweep —
  which settles orders placed on an earlier tick, when the balance may
  since have been spent.
- **Nuclear**: inline before the debits, matching Fleet's tolerance
  exactly so the venues cannot disagree about what is affordable.
- Raises rather than refusing quietly: `amount<=0`, unknown symbol and
  missing candle already raise on both venues, an insufficient balance
  is the same class of caller error, and a silent refusal would
  reproduce the defect in a new shape — the caller carries on believing
  it traded.
- A `1e-12` tolerance admits an **exactly** funded order. Without it,
  float error would silently suppress the last trade of many runs, which
  is harder to notice than the defect being fixed. Pinned as a negative
  control on both venues.

### A tripwire fired exactly as intended

v3.24.65 corrected a false docstring claiming zero balances raise, and
left a pin asserting the *opposite* — that a zero-balance BUY settles
and drives the ledger negative — carrying the note *"if SN-17 landed,
update this pin and the docstring together"*.

SN-17 landed, the pin went red, and this release is that update: the
guarantee is restored to the docstring and the assertion flipped **in
the same commit**. The documented guarantee and the behaviour now move
together or the suite fails.

Suite 1985 passing.

---

## [3.24.65] - 2026-08-07 — Nuclear filled limit orders at any price you named

**Found during the C19 cold read. Not in the cascade plan, and more
severe than any finding it lists.** Shipped alone by operator decision
so the rest of C19 lands against a corrected baseline.

`nuclear_sim_exchange.py` set the fill price to whatever the caller
asked for, with **no comparison to the candle at all**:

```python
fill_price = float(c[4])                      # candle close
if order_type == OrderType.LIMIT and price is not None:
    fill_price = float(price)                 # whatever was named
```

Reproduced before the fix: a BUY limit at **$1.00** against a **$100**
candle returned `filled=1.0, average=1.0`. A SELL at $10,000 filled at
$10,000.

That is not an unrealistic resting model — it is free money, and it gets
**better the further from market the order bids**. Any strategy
evaluated in Nuclear that places limit orders was scored against a
fabricated discount, so the harness actively recommended the wrong
behaviour. **Nuclear results involving limit orders taken before this
release should be discarded, not re-interpreted.**

A limit now fills only if the candle traded through it:

    BUY  fills iff low  <= limit, at min(limit, close)
    SELL fills iff high >= limit, at max(limit, close)

`min`/`max` rather than the limit itself: a BUY limit **above** the
market must not fill at its own worse price when the market was
cheaper — that would fabricate a **loss**, the mirror of the defect
being removed. An unfillable order returns OPEN with **no ledger
movement**; recording a purchase that did not happen is the same class
of lie as the fill price it replaces.

Fleet's resting/sweep model is deliberately **not** copied. Nuclear is
single-shot by design; only the fill-price contract is shared, so the
two venues stay forks.

**A false docstring corrected in the same edit.** The module claimed
"unknown symbols + **zero balances** + negative amounts all raise loud
exceptions". Zero balances do not raise — `_adjust_balance` is plain
addition with no floor, and the constructor deliberately *seeds* zero
balances. The claim is corrected rather than the code, because the
balance precondition is C19's SN-17 and rides in its own cascade; a red
pin now waits for it.

Suite 1966 passing.

---

## [3.24.64] - 2026-08-07 — C18 · The simulator's TA inputs were not faithful

Cascade 30, tier sim-only. Findings SN-1, SN-57, SN-58, **plus a fourth
the plan does not contain**.

- **SN-1 — six phantoms read one series.** `FleetSimExchange.get_ohlcv`
  did `del timeframe` and served a single per-symbol sequence, so every
  phantom fed the identical 5m data into `get_higher_tf_bias`. Six
  timeframes agreeing perfectly is not a signal; it is one signal
  counted six times, and it gates SCRUM. Now keyed by
  `(symbol, timeframe)`, with an explicit **warned** fallback — a silent
  one is how six phantoms end up agreeing again.
- **SN-58 — the sim discarded the real venue.** It overwrote
  `exchange_id` with `"fleet_sim"`. `timeframes.py` uses a *permissive*
  unknown-key fallback, so that did not select a sim timeframe set — it
  **disabled the availability filter entirely**, making a 4h phantom
  creatable for a Coinbase bot that cannot have one. The real venue now
  wins, falling back to the sim id only when a config carries none.
- **The cadence was wall-clock** (`phantom_balance.py:210`):
  `min(candle_seconds, 60)` is 60 *real* seconds for every phantom. A
  replay covering ~15,000 candles in minutes gave each phantom a handful
  of ticks at arbitrary replay positions. **Fixing SN-1 without this
  leaves the HTF bias just as unfaithful** — six different series
  sampled at random moments. Sim phantoms now advance through
  `tick_for_cursor`, driven by the replay clock, idempotent within a
  candle so the sampling moment is deterministic across replays.

### SN-57 was inverted

The plan says all 35 bots record `phantoms_enabled=False` so a replay may
construct **zero** phantoms. The controller **hardcoded
`enable_phantoms=True`** — the sim forced them on for all 35, running a
configuration none of the live fleet uses, so parity claims about
SCRUM/FOLD were compared against a fleet that does not exist.

The flag is also not where a fix would look: it is an **entry-level**
key, False on 35/35 and **absent from `config` on 35/35**.

Operator decision 2026-08-07: honour the persisted value (default off,
faithful to live) with a per-run toggle that can only force phantoms
**on**, never off.

### The hazard gate is latent, not active

`set_data_pool` has one caller — `main.py:735`, the live manager — so a
sim `BotManager` keeps `_data_pool = None` and sim bots never reach the
pool. Restoring the real `exchange_id` makes the sim's pool key
identical to live's, so the guard is a **structural pin** keeping the
pool unreachable from `simulator_tab/`, not the key redesign the plan
describes.

### Pin replacement (M7) and a regression I caused

`test_sim_bots_are_constructed_with_phantoms_enabled` asserted the
string `enable_phantoms=True`, while its own failure message demanded
sim bots behave "like live bots" — which have phantoms **off**. The
requirement was right, the implementation contradicted it, and a
substring cannot tell whether a phantom ever *ticked*. Replaced by
behavioural pins; recorded before the edit in
`docs/audits/2026-08-07_C18_pin_replacement_record.md`.

Separately, my first venue fix only set `exchange_id` when a config
carried one — hand-built configs omit it, `BotConfig` has no default, and
the replay reported **0 bots**. Caught by an existing pin, fixed with an
explicit fallback.

Suite 1953 passing.

---

## [3.24.63] - 2026-08-07 — C16 · Sim reservations always failed, so a gate could never fire

Cascade 29, tier sim-only. Finding SN-5. Hard after C15.

`_compute_reservation_qty` claims `target / (price × qrate)` with a
**10% safety margin**, so tick-to-tick drift cannot leave a *live* bot
under-reserved. Sim inventory is seeded at exactly `target / open_px`,
so the claim is ~110% of what a sim bot holds, `reserve()` saw
`qty > total_holdings`, raised on over-commit, and the reservation
failed **for every bot on every tick**.

Consequence: the "SELL REFUSED (capital reservation)" branch was
**unreachable in sim**. A gate that can never fire is a gate the
simulator cannot tell you anything about.

Sim now declines to assert `total_holdings` on the **first** reserve.
The over-commit check exists to stop bots sharing one live exchange
balance from collectively over-claiming it; a sim fleet holds a private,
non-persisting registry (C15) and no live inventory, so there the check
measures the wrong thing. Subsequent updates still pass holdings, so
drift is still caught.

**The tempting alternative is wrong and the site says so.** Seeding sim
holdings at the reservation ceiling would hand every sim bot 110% of a
live bot's base units — sim out-scrums live, and the inflation reads as
the fix working. The 1.10 is over-commit headroom, not an inventory
target. Sim seeding is unchanged, pinned by assertion.

### Pin replacement, with operator acknowledgement (M7)

`test_ensure_reservation_has_no_sim_mode_skip` failed. Its *requirement*
was right — sim bots must reserve, not skip — but its *implementation*
asserted the string `_sim_mode` was absent from non-comment source, as a
**proxy** for that behaviour.

The proxy was both too broad and too weak. Too broad: it failed any use
of `_sim_mode`, including one that does not skip. Too weak: it never
checked a reservation happened, so it stayed green throughout the entire
period SN-5 describes.

Replaced by `test_a_sim_bot_actually_obtains_a_reservation`, which
asserts the behaviour, plus a structural pin that a bare
`if _sim_mode: return` cannot return — asserted over the AST so the
comment recording the v3.24.31 removal can neither satisfy nor trip it.
Recorded before the edit in
`docs/audits/2026-08-07_C16_pin_replacement_record.md`.

**One of my own new pins fell for the same trap** it was written to
guard: it matched `_sim_mode` as a substring and passed against unfixed
code, because of that very comment. Trap #5, sprung inside the test
verifying the fix for it.

Suite 1937 passing.

---

## [3.24.62] - 2026-08-07 — C22 · A sim run can record why a trade did not fire

Cascade 28, tier sim-only. Finding SN-54. Unblocked by C17.

`_emit_trade_notification` returned early for sim bots, so a replay
produced no SENT / PLACED / FILLED / CANCELLED trace — and the CANCELLED
**reason string** is the only place a sim run records *why* a trade did
not fire. Skipping it removed the feature instead of simulating it, the
same shape as the capital-reservation skip corrected in v3.24.31.

**That guard was doing real work.** Sim notifications reached the shared
bus, `main_window` forwarded them to the sound engine, and a replay made
noise. Removing it before C17 would have been a regression, not a fix.
C17's fail-closed private-bus swap means a sim bot either holds a
private `EventBus` or is never constructed — isolation now comes from
*which bus the bot holds*, not from refusing to emit.

The removal site records all of that, including an explicit instruction
**not to reinstate the guard to silence a noisy replay**: noise would
mean a sim bot is holding the live bus, which is a C17 isolation failure
and must be fixed there.

**The measurement is an instrumented counter, not silence.** A wildcard
subscriber is attached to the live bus and asserted to receive exactly
zero events across 200 sim notifications. "No sound was heard" and "no
event was delivered" are different claims; only the second is checkable.

### Corrections to the plan

- Step 2 cites `:1966`. The notification guard is at **`:2133`**, in
  `_emit_trade_notification`.
- `:1138` records a *different* `if _sim_mode: return`, already removed
  in v3.24.31 — the comment naming it is what made this cascade look
  already-shipped on first inspection. Exactly trap #5 in
  `docs/audits/2026-08-07_traps_that_pass_a_naive_test.md`, hit while
  reading for that document's own subject matter.

Suite 1927 passing.

---

## [3.24.61] - 2026-08-07 — C17 · Sim objects were subscribing to the LIVE event bus

Cascade 27, tier **live-behaviour**, rides alone per M2. Findings
SWARM-4.23, SN-42, SN-39, SN-44, NF-9. Keystone of the sim band — a hard
predecessor of C22, C23, C46 and C20.

**The leak.** `BotManager.__init__` subscribes three handlers to the
process-wide bus *inside the constructor*.
`nuclear_controller` rebound `._bus` on the very next line after
constructing — too late. Three bound methods of an **abandoned sim
manager** stayed attached to the live bus and fired on **live** events,
three more per replay, for the life of the process. `EventBus` had no
way to retract them.

- **`EventBus.unsubscribe`** (NF-9), plus `subscriber_count` and
  `subscription_fingerprint`. `subscribe` always returned an unsubscribe
  closure and every caller in `src/` discarded it.
- **`BotManager(bus=...)`**, resolved 40 lines ahead of the subscribes,
  with the closures now retained and a `detach_bus()` that retracts
  them. Nuclear injects at construction and detaches at teardown.
- **`TimeframeCoordinator(bus=...)` and `PhantomBalanceBot(bus=...)`**;
  `ScrummingBot` threads its own bus into the coordinator, which it
  builds *after* the private-bus swap and previously without it.
- **The sim bus swap fails closed** (SN-39). It logged
  `"sim emits may reach live logs"` and continued, leaving `self._bus`
  on the process-wide bus — one failed construction silently reinstated
  the whole defect.

**Two implementation traps, both of which pass a naive test.** Handlers
are bound methods, and `obj.m is obj.m` is `False` in CPython — an
identity-based `unsubscribe` removes nothing. And `_subscribers` is a
`defaultdict`, so a count accessor written with `[topic]` *creates* the
key and mutates what it measures. Both are pinned.

### The plan's own scope correction was wrong

C17 states: *"SmartWireManager takes no bus and emits nothing, so
SN-28's stated fix is misdiagnosed."* It resolves `get_event_bus()` at
`smart_wire.py:491` and `:675` and emits `bot.log` on both paths, and
`BotManager` constructs one — so a sim manager's wire activity reached
the live bus even after its owner was isolated. Now injected, with a
structural sweep pinning that no emit site can reach the global bus
without consulting the injected one first.

**SN-44 is misdiagnosed too.** The exit gate requires
`idempotency._bus is not get_event_bus()`; `IdempotencyLayer` has **zero
bus references**. The clause is unsatisfiable as written and is recorded
rather than chased.

Line numbers in the plan were wrong again: the subscribes are at
`:1598/:1602/:1603`, not `:1461/:1465/:1466`.

Live construction is unchanged — every `bus` parameter defaults to
`get_event_bus()`, pinned by negative control.

Suite 1915 passing.

---

## [3.24.60] - 2026-08-07 — C29 · Trade markers sat on the wrong candle, twice over

Cascade 26 of the remediation sequence, tier gui-truth. Findings SN-15,
SN-16, SN-30, SN-37, NF-51.

**SN-15 — the drain marked before it appended.** The panel called
`mark_trade` before the loop that appends the tick's candle.
`mark_trade` pins the candle at the end of the series, so every marker
landed on the *previous* drain's candle. Off by one, always, invisible
by eye. The marker block now runs after the appends.

**SN-16 — decimation slid them further.** Past `_MAX_POINTS` the series
halves with `[::2]` and markers were remapped `i // 2` — exact for even
indices, wrong for odd, compounding on every subsequent halving. Markers
now anchor on a monotonic **ordinal** carried in a parallel series, and
resolve to a position only at paint time, so nothing can move between
recording and drawing.

*The cascade says "anchor by timestamp". The series carries none:
`_series[symbol]` is `(prices, vwaps)` and `append_tick` never receives
one. The ordinal is the same idea without changing the caller.*

**Ordinal anchoring alone was still wrong, and a pin caught it.** It
fixes the arithmetic, but `[::2]` simply deletes odd-ordinal candles, so
those markers resolved to nothing — a long replay quietly losing the
operator's trades. Different failure, same wrongness. Decimation now
**never discards a candle carrying a marker**, bounded by
`_MAX_MARKERS`, with a negative-control pin proving that cannot defeat
the point cap.

- **SN-30** — `clear_data` left `_markers` populated, so the previous
  run's trades were drawn against the new run's candles.
- **SN-37** — `_markers` was an unbounded list, now a bounded `deque`
  that discards the oldest; the operator watches the live end.
- **NF-51** — `clear_gates` reset five fields and not `_ls_scrum`, so a
  cleared row went on claiming an active landing-strip override.

Suite 1878 passing.

---

## [3.24.59] - 2026-08-07 — C28 · A second Expand orphaned the chart into a hidden dialog

Cascade 25 of the remediation sequence, tier gui-truth. Findings SN-10,
SN-36.

`_show_expanded` reparents the chart into a modeless dialog and hands it
back on close, remembering home as `widget.parentWidget()`. With a
dialog already open that is the **dialog's** container, not the panel —
so a second Expand recorded the dialog as home and returned the chart
into a widget the operator cannot see. The chart disappeared from the
panel with no way to retrieve it (SN-10).

Reproduced before the fix: `parentWidget()` came back a `QDialog`, two
clicks produced two dialogs, and the dialog survived its own close.

- **Re-entry guard** claims the widget for its dialog, and a second
  Expand raises the existing one rather than opening another. Silently
  ignoring the click would read as a broken button.
- **The claim is released first in `_restore`**, before the reparent, so
  a failure there cannot leave Expand permanently dead — a guard that
  outlives its dialog would be worse than the defect.
- **`WA_DeleteOnClose`** (SN-36). Modeless and parented to the window,
  so the parent chain kept every dialog alive and each Expand leaked
  one.

The lifetime assertion checks the **C++** side via `shiboken6.isValid`,
falling back to a wrapper weakref. A `QDialog` can be destroyed
C++-side while the Python wrapper survives, so a weakref alone would
have passed against the unfixed code.

Suite 1864 passing.

---

## [3.24.58] - 2026-08-07 — C26 · Fleet Replay panel: Stop and Reset could fail silently

Cascade 24 of the remediation sequence, tier gui-truth. Findings SN-31,
SN-12, SN-13, SN-14, SN-35, SN-29. **SN-34 deliberately excluded** —
see below.

- **Stop and Reset swallowed their own failure.** Both wrapped
  `request_stop()` in `except Exception: pass`. The operator pressed the
  button, the request was discarded, and nothing on screen changed.
  Both now report, and Reset no longer overwrites the failure reason
  with a cheerful "Fleet cleared".
- **Reset now nulls `_controller` and clears `_gate_cells`**, neither of
  which it did.
- **Start is no longer re-entrant** (SN-14). A second click built a
  second controller while the first run's timers and gate cells still
  pointed at the old one, orphaning them with nothing able to stop them.
- **The empty-fleet return says why** instead of returning bare.
- **A run with no live YTD trades now says the parity check was
  skipped** (SN-29). That is the *normal* condition, and the panel said
  nothing — so a synthetic run looked exactly like a parity run.
- New `_status_error` funnel guarantees no failure path leaves the
  status line empty.

### The plan's own step 2 would have caused a hang

Reset's timers self-stop through `_refresh_progress`, which returns
early when `_controller is None`. "Null `_controller`" — exactly what
the cascade prescribes — means that branch is never reached and both
`QTimer`s run for the life of the process. **Order is load-bearing:**
the timers are stopped *before* the controller is nulled, pinned
structurally by `test_the_timers_are_stopped_before_the_controller_is_nulled`.

### Corrections to the plan, from the cold read

- **`_status_error` did not exist.** Zero hits repo-wide. The plan says
  to "route the nine failure sites through" it; it had to be authored.
- **Those nine sites already reported.** They are a consolidation, not a
  defect. The genuinely silent aborts were elsewhere — and the two that
  mattered were Stop and Reset.
- **SN-34's remedy is impossible as written.** `main.py` pumps the
  asyncio loop from a Qt `QTimer`, so that loop **is** the GUI thread;
  scheduling onto it moves nothing off, and no worker thread exists to
  use. The plan's alternative — memoising the trade-log walks — targets
  work a subagent measured at ~0.2% of the block. Operator decision
  2026-08-07: ship the other four steps, measure the real block first.
  The falsified remedy is recorded in the test file so it is not
  retried.

Suite 1856 passing.

---

## [3.24.57] - 2026-08-07 — C35 · Topology proposal ranking + dismissal persistence

Cascade 23 of the remediation sequence, tier gui-truth. Findings
SWARM-4.28, SWARM-4.29. Operator decision 2026-08-07: liquidity is the
tie-break signal.

### Ranking was decided by dict iteration order

`detect_sector_cluster` scored purely on cluster size, so every sector
at `max_cluster` landed on exactly 100.0. `build_proposals` then applied
a STABLE sort, which leaves ties in input order — and that order came
from `by_sector` insertion, which came from `tickers_by_asset`
iteration.

Measured on a three-full-sector fixture before the change: scores
`[100.0, 100.0, 100.0]`; across 20 shuffles of the same input the ranked
leader landed on **all three** sectors and the full ranking produced
**five distinct orders**. The operator's top recommendation was
effectively random.

Score is now a blend — `0.7 x size + 0.3 x liquidity`, weights summing
to 1.0 so the documented 0..100 scale holds and size stays dominant.
Liquidity costs nothing: `baseVolume` is already fetched and already
used inside the same function to rank members and choose the hub.
Determinism is enforced at three levels: sectors iterate sorted, member
ranking breaks ties on asset name, and the final sort takes an explicit
`(-score, archetype_rank, title)` key.

**The comment above that sort was also wrong.** It claimed ties fall
back to "the higher archetype priority order ... so a stable sort
suffices". That covers ties BETWEEN archetypes only; nine tied sector
clusters are all the same archetype, so archetype priority could not
separate them at all.

### A 24 h dismissal lasted until you closed the tab

`_dismissed` was a plain dict on the widget, while the button tooltip
and the confirm dialog both promise 24 hours. Reopening the tab
resurrected every dismissed card.

Now persisted through the settings namespace, written through
immediately on dismiss (deferring to close would lose it on a crash —
precisely when the operator least wants the card back) and swept on
expiry so the key cannot grow without bound.

**The store is INJECTED, never constructed in the widget.**
`SettingsManager()` resolves `Path.home()/".acervator"` with no env
override (`settings.py:222`), so a widget building its own would write
the operator's live settings from any headless render — a breach that
has already happened once in this repo. Unset means memory-only, exactly
today's behaviour. Entries that lapsed while the app was closed are
dropped rather than re-imported, since re-suppressing them would extend
a 24 h promise across restarts indefinitely.

**A pin caught the wiring gap.** Everything above verifies the pane
*can* persist; a store nothing injects persists nothing. The
fix-reaches-the-read-path pin asserts both hops —
`main_window` → tab → pane — and failed until the tab's forwarding was
rewritten from `getattr`-dispatch to a `hasattr`-guarded direct call.

Suite 1834 passing.

---

## [3.24.56] - 2026-08-07 — C52 · History tab grades were computed backwards in time

Cascade 21 of the remediation sequence, tier gui-truth. Finding NF-16.

> **Previously displayed or screenshotted letter grades are NOT
> comparable to grades shown after this release.** Every grade and grade
> tooltip in the History tab was computed with the time axis reversed.
> Re-grade before drawing any conclusion from an older screenshot.

`_grade_row` split the page around the graded row with `j < row_i` as
"before" and `j > row_i` as "after". That is only correct for an
oldest-first page. `history_helpers.py:295` sorts the fetch
`reverse=True` — **newest-first** — and nothing re-sorts between there
and the grader: `_all_trades` is assigned verbatim, `_filtered`
preserves its order, `_render_page` slices it. A lower index is
therefore a *later* trade, and both halves were inverted: the ref came
from trades that happened *after* the one being graded, and the MFE/MAE
window came from trades *before* it.

**The two errors do not cancel.** On a buy at 100 immediately followed
by a fall to 90, the correct grade is **D** and the shipped code
returned **A+** — the best available grade for one of the worst
available trades, presented to the operator as feedback.

Both halves were flipped together (C52 step 1), and so were the slice
directions that depend on the axis: the ref price now takes the five
*nearest* priors (`[:5]`, not `[-5:]`) and the MFE/MAE window the ten
*nearest* subsequent prices (`[-10:]`, not `[:10]`). With the list order
reversed, the old slices would have reached for the most distant rows on
the page.

**On building the pin.** The obvious fixture cannot detect this: the
flip inverts both sub-scores and `grade_trade` takes their unweighted
mean, so exec 1.0/timing 0.0 and exec 0.0/timing 1.0 both average to
0.5 and grade D either way. The fixture is deliberately asymmetric —
the graded row sits near the top of the page, so the inverted reading
finds only two "prior" prices, falls below the `>= 3` minimum, and drops
the execution axis entirely. That changes the denominator, not just the
numerator, and is what makes D vs A+ visible.

Suite 1809 passing.

---

## [3.24.55] - 2026-08-07 — C11 · Main-window dead startup branches: deleted

Cascade 20 of the remediation sequence, tier record-only. Findings
NF-162, NF-109. Operator decision 2026-08-07: **delete**.

- **`set_bot_viz` had zero definitions repo-wide** and two callers. The
  `_simulator` one raised `AttributeError` into `except Exception: pass`
  on **every boot**, and nothing ever reported it (NF-162).
- **The `_paper_trader` branch was structurally unreachable** (NF-109).
  `_paper_trader`, `_paper_trader_stack`, `_paper_trader_crypto` and
  `_paper_trader_equity` are assigned `None` in `main_window` and never
  assigned anything else, so the view-mode reassignments can only ever
  copy `None` into `None`.
- **Deleted, not implemented.** `_bot_viz` is a live
  `BotVisualizationTab`; implementing `set_bot_viz` would inject a live
  GUI object into the Simulator tab — a sim↔live bridge, which is a
  standing prohibition. The Simulator's other injection points
  (`set_bot_manager`, `set_connectors_getter`, `set_async_loop`) were
  each deliberate; this one was only ever called, never built. The
  reasoning is recorded at the deletion site for C49 to reconsider.
- Both bare `except Exception: pass` handlers went with the branch —
  there is no enclosing boot guard at that point, so removal is
  strictly better than converting them to logged handlers.

**Scope held deliberately.** The `_paper_trader = None` assignments and
the view-mode handlers are untouched: `_paper_trader_equity` is
stock-side and the Stock Panel is off-limits by operator directive. C49
makes this wire-or-delete judgement systematically.

**Two corrections to the plan, from the cold read.** Line numbers had
drifted (`:3816`→`:4017`, `:3779`→`:3980`), and the boot smoke test the
plan says CV1 delivered as `tests/test_main_window_boot_smoke.py` does
not exist under that name — it lives in `tests/test_suite_integrity.py`,
which is where the new pins went. The pins assert over the AST, because
the comment recording the deletion necessarily names the deleted method
and a substring search would match it forever.

Suite 1797 passing.

---

## [3.24.54] - 2026-08-07 — C15 · Sim capital registry: fail closed (completing a half-shipped cascade)

Cascade 6 of the remediation sequence, tier **live-money**, rides alone
per M2. Findings SWARM-4.24, SN-52.

**Why this shipped out of order.** A status audit found C15 had no
evidence in git, CHANGELOG or audits, while items on both sides had
shipped. Step 1 turned out to have landed under **CV1 (v3.24.35)** — the
factory now raises — which is why no C15 label existed. The other four
steps were never done, and C15 is a declared hard predecessor of C16,
C18, C19, C20, C23, C26, C61 and C13. Running eight dependants on a
half-built isolation guarantee is how the two prior isolation breaches
shipped.

`CapitalReservationRegistry` is a process-wide singleton that persists to
`~/.acervator/reservation_state.json` — live capital state. The recorded
cost of a sim fleet reaching it: 16,558 bot_ids against 35 real ones,
16,523 orphans, 6.5 MB of sim residue feeding live allocation decisions.

- **Step 2 — the Nuclear call site is guarded.** `nuclear_controller.py`
  called the now-raising factory inline in a `ScrummingBot(...)` argument
  list from inside a Qt slot, so a `mkdtemp` failure aborted Nuclear Mode
  with a bare traceback and no reason. It still aborts — that is correct
  — but now names the cause.
- **Step 3 — `_instantiate_bot` refuses without a registry**, as its
  first statement, ahead of the blanket `except` that would otherwise
  hide a missing registry among ordinary construction failures.
- **Step 4 — `_crr()` structural backstop.** A bot with `_sim_mode` and
  no injected registry now returns `None` instead of resolving the
  process-wide singleton. The upstream guards protect callers that *ask*
  for a registry; this protects the ones that never do.
- **Step 5 — the replay asserts the outcome**, once, after the bot set
  is final and before anything can trade. Guards verify their own paths;
  this verifies the property they exist to produce.

**Two defects caught by pins rather than by review.** The first version
of `_assert_capital_isolation` compared each bot's registry against
`get_registry()` — resolving, and potentially constructing, the live
singleton from a sim path. `test_singleton_isolation.py` failed it: the
guard broke the rule it was written to enforce. It now checks the
property that actually matters (`autosave` off), which never touches the
live object. Separately, one new pin passed vacuously on unfixed code
because `_instantiate_bot` swallows all exceptions; it is now pinned
three ways, including structurally.

Suite 1794 passing.

---

## [3.24.53] - 2026-08-07 — The system log was dropping most of its records

Found while trying to *read* the system log to answer an unrelated
Indicator-Voting-Panel question. The operator's 2026-08-07 08:18 boot
produced:

```
console_20260807_081802.log
  15,616 lines
     825 "--- Logging error ---" blocks
       3 surviving log records
```

`logging_engine.py:348` built the only logging handler in the codebase
as `logging.FileHandler(path)` with no encoding, so it opened with the
locale codec — cp1252 on Windows. This codebase logs arrows, em-dashes
and multiplication signs freely (`trade.filled → trade.log`,
`take × (ref − fill)`), and Python's logging swallows the resulting
`UnicodeEncodeError` into a traceback and **drops the record**.

The instrument the operator relies on to diagnose the platform had been
reporting almost nothing, and nothing said so.

Now `encoding="utf-8", errors="replace"` — utf-8 so the glyphs survive,
`errors=` so a genuinely bad byte degrades to a marker instead of
costing the whole record.

Same class as the archetype subprocess defect fixed in 3.24.51: that one
*decoded* tool output with the locale codec, this one *encoded* log
output with it. Two ends of one mistake. `test_system_log_encoding.py`
pins both the construction site and a sweep over every handler in `src/`,
with a positive control that proves a bare handler really does drop the
arrow on this machine.

Suite 1773 passing.

---

## [3.24.52] - 2026-08-07 — C09 · Lane canvas: exhaustion visibility + endpoint resolution

Cascade 19 of the remediation sequence. Findings SWARM-A3, SWARM-4.14.

- **A wire that cannot be drawn is now reported.** Both skip branches in
  `LaneWireCanvas.paintEvent` were bare `continue`s, so a wire missing
  from the canvas was indistinguishable from one that was never
  configured. New `undrawable_wire_count()` / `undrawable_wires()`, and
  a log line on CHANGE — the canvas repaints ~2.5×/sec, so per-frame
  reporting would bury the log while saying nothing new.
- **The reason names the real cause.** `set_wires` filters unlisted
  endpoints *before* lane assignment, so at paint time they look
  identical to allocator exhaustion. The first implementation reported
  every one as `no-lane`, pointing the operator at lane capacity when
  the row set was what had gone stale. Now `unlisted-bot` vs `no-lane`.
  Caught by its own pin, not by inspection.
- **Endpoint resolution is O(1).** `row_of_bot` is
  `self._bot_ids.index(...)`, and the paint called it twice per wire —
  measured at 16 calls for 8 wires over 30 rows. New
  `BotListView.row_index_map()` is built once per paint. `row_of_bot`
  stays for single lookups, where a scan beats allocating a dict.

**Pin replacement, with operator acknowledgement (M7).**
`test_wire_canvas_ignores_unknown_bot` was named "ignores", commented
"wire silently skipped", and asserted the silent drop was correct — the
finding written down as a requirement. Replaced by
`test_wire_canvas_reports_unknown_bot`, which asserts strictly more: the
original invariant survives verbatim as its first assertion, and the
silence is withdrawn. Recorded before the edit in
`docs/audits/2026-08-07_C09_pin_replacement_record.md`.
`test_returns_none_when_all_lanes_full` is untouched — allocator
exhaustion returning `None` is legitimate, not a defect.

Both new pins were observed RED on the unmodified baseline (M4).

Suite 1767 passing, zero failures.

---

## [3.24.51] - 2026-08-07 — Manual Fire re-zero, bulk ticker refresh, and two silent instruments

Operator items 1 and 2 of the Target Delta report, plus two measurement
failures found while verifying them.

### Manual Fire now re-zeroes (operator ruled all three, 2026-08-07)

- **Settled fills.** `Order.average` was declared on the dataclass and
  `_parse_order` — the only place the connector builds an `Order` —
  never populated it, so it was `0.0` on every live order ever placed.
  Eleven call sites read it as the primary fill price with an `or`
  fallback, so it never raised; it just meant every live fill price was
  an estimate. `sim_exchange` did set it, so sim had real fills and live
  never did. `_parse_order` now populates it (falling back to
  `cost/filled`), and new `ScrummingBot._settled_fill` re-reads the
  order after submit. Estimates are still permitted but never silent.
- **Fold sizes against the post-growth target.** The buy was sized
  before `_apply_fold_target_growth` raised the target, so position
  landed on the old one and the residual was identically the growth —
  and always inside Manual Fire's own 1% dust band, so firing again
  reported "already within dust band". New `_preview_fold_growth`
  computes the growth without mutating anything; the fold solves a
  cap-bounded fixed point and buys deficit plus growth. Actual growth
  still applies exactly once, after the fill.
- **Shared-wallet reservations.** New `src/trading/wallet_reservations.py`.
  All 35 bots read one wallet; the fold now nets off other bots'
  in-flight holds and releases in a `try/finally`.

### Bulk ticker refresh

`MarketDataPool.refresh_all_tickers` warms every cached entry from one
bulk call per exchange; `BotManager` runs it on a 5s cadence matched to
the pool's own TTL. Measured 10,272 ticker fetches/hour reduced to ~720.
Decision cadence unchanged.

### Two instruments that were reporting success while measuring nothing

- **The prose layer.** `docs_archetype` read proselint through
  `subprocess.run(text=True)` with no encoding, so Python decoded with
  the Windows locale codec. proselint's curly-quote message contains
  curly quotes, which cp1252 cannot decode; `stdout` came back `None`
  and the layer returned zero findings for every document it checked.
  Fixed across all 10 subprocess sites in the three archetypes —
  `check_release_readiness` already had the fix and it had never been
  propagated. Pinned structurally by `test_archetype_subprocess_encoding.py`.
- **The crash logger wrote to the live tree.** `_get_crash_log_path`
  resolved `~/.acervator_logs` with no override, so any test tripping an
  excepthook appended to a real crash log. Fixed with
  `ACERVATOR_CRASH_LOG_ROOT`, set at conftest *import* time because
  `main` caches the path at module exec during collection.

Suite 1764 passing.

---

## [3.24.50] - 2026-08-06 — Tranche lifecycle: Phase 1 complete, plus C05/C06c/C51/C10/C54/C03

Suite 1332 → 1556. **No trading behaviour changed in this release.** Every
change is disclosure, diagnosis, persistence, or record protection. Buy
sizing and buy timing are untouched.

### The finding that framed the release

10,197 fold tranches have closed across the fleet. Total lifetime
target-balance growth from all of it is **$26.20** — 0.794% of a $3,300
combined base, $0.00257 per closed tranche. Compounding has never
functioned globally. See
`docs/audits/2026-08-06_measurement_tranche_compounding_fleet.md`.

The compounding code is not producing zero growth; it is **never
reached**. Folds are refused upstream by a gate stack whose diagnostics
named the wrong blocker.

### Tranche lifecycle — Phase 1 (truth)

- **Step 1** — the fold diagnostics name gates that actually run. `FOLD:
  Bought` blamed a "MEM-171 initial_buy_price floor" absent from the
  executor's filter; `NO_STRICT_ELIGIBLE` reported an activation price
  ignoring the OTD factor, so it read as closer to firing than it was.
- **Step 2** — the instrument measures the executor's predicate. The
  counters used `< ref AND <= initial_buy_price` while the executor uses
  `<= ref * _otd_factor`. One hoisted binding now serves both.
- **Step 3** — the compounding surface is visible. `get_status` exported
  the config target and never the runtime `_target_balance` the bot
  trades against. Live target, standing surplus, cycle budget and
  over-cap tranche count now render; the Target Balance spinbox is
  deliberately NOT repointed.
- **Step 4** — diagnostic state survives a restart. Five fields were
  written every session and persisted by none, including the provenance
  of parked wire credit.
- **Step 5** — a failed restore no longer destroys the saved record. The
  handler logged "do not let that record be replaced" and then let it be
  replaced sixty seconds later.

### Operator-directed tranche tooling

- `clear_fold_tranches()` and `clear_pending_wire_credits()` with buttons
  on the Fold Tranches tab. Discards queued intent and parked earmarks;
  places no order, moves no funds, leaves holdings, cost basis and target
  untouched.

### Cascades

- **C05** — Quick Routing mass operations confirmed; 1,190 wires from one
  unconfirmed click, six silent returns, four swallowed failures.
- **C06c** — topology adopt: unvalidated asset binding could route a
  proposal's wires through the wrong asset. Overwrites disclosed;
  D23 ruled — an adopt applies the whole topology.
- **C51** — the Indicator Voting Panel stops fabricating TA under real bot
  symbols on all three entry paths.
- **C10 / NF-5** — the Ammo column stops inverting the Scrum/Fold signal.
  `max(stale, fresh)` reported SELL when the truth was BUY, but only in
  falling markets.
- **C54** — per-bot status contract, a reachable `BotState.ERROR`, and an
  AI monitor no longer analysing a $0.00 portfolio.
- **C03** — real exchange ids, and privacy that covers the tooltip and the
  list view.
- **Isolation** — the suite no longer writes to the operator's runtime
  tree; the live-tree guard reports DEGRADED rather than crying wolf.

### Known open

D1 (fold capital cap), D5 (wires exporting principal), merge-downward,
and the dormant Stack Mode write path that bypasses the growth cap.

## [3.24.36] - 2026-08-06 — Cascades C12, C02, C06b, C04

**1332 passed / 0 failed.** (1296 → 1332, +36 pins.)

Four cascades. The last two are ordered as a pair on purpose, and the
first is the one most likely to be visible on next launch.

### C04 — the wire overlay stops covering the default List view

`_on_tab_changed` called `_wire_canvas.show()` whenever the Bot Swarm
tab was active, ignoring which VIEW was showing. It fires at
construction and the default view is List, so the canvas was shown over
the list on every launch — taking its geometry from `_grid_widget`, the
HIDDEN stacked page, which QStackedLayout never geometries. It sat at a
stale 640×480 over the list's top ~452 px and 93% of its width, is not
transparent for mouse events, and defines no `wheelEvent`. Clicks and
scrolls in the first ~15 rows of the default view were swallowed.

Measured with a headless render probe: `childAt(200, 200)` returned
`_WireCanvas` before and the list widget after; the Grid rect went from
a stale 640×480 to the real 680×733.

### C06b — destructive wire gestures are confirmed

Dragging between two already-connected bots, or releasing a drag on
empty space when the source had exactly one outgoing wire, deleted a
live Smart Wire with no dialog and no undo. A press that slipped 2–3 px
off a locust edge was enough. With MORE than one wire the operator got a
picker — so having fewer wires was more dangerous — while the only
confirmation in the file guarded "Disconnect All", the button nobody
presses by accident.

This had to land BEFORE C04: while broken, the overlay was the only
thing shielding the default view from those gestures.

### C02 — one durable Smart Wire channel, one staging file per writer

Two mechanisms claimed to persist wires. Measured on the live file:
`scrumming_state.smart_wire_routes` was carried by 0 of 35 bots, because
`export_scrumming_state` does not emit that key and the 60-second save
rebuilds `scrumming_state` without it. Top-level `smart_wires` held all
40 wires. The durable channel is not in doubt.

More serious: `bot_visualizer._save_bot_state_dict` staged through
`bot_state.tmp` — byte-for-byte the path `StateManager.save_state` uses.
Two writers, one temp name, either able to rename the other's partial
write over the live position file. Now `bot_state.gui.<pid>.tmp`, and
its silent `except: pass` is gone.

### C12 — five settings were discarded on every save

`AppSettings` had 14 fields; the Settings dialog wrote 16 keys.
`font_family`, `font_size`, `heading_font_size`, `log_font_size` and
`ai_monitor` were not fields at all, so `set()` raised `KeyError`,
`_save()` swallowed it, and the status line reported success anyway.
Four font choices and the entire AI Monitor configuration were dropped
on every save since those tabs shipped. Fields added; a partial save now
logs at ERROR and raises a modal.

### A defect introduced and caught in the same series

`bot_visualizer.py` used `logger.` at three sites with no module-level
binding and no `import logging` — a latent `NameError` inside `except`
handlers, the same shape as NF-154 fixed earlier in this series. Two of
the three call sites were added by C02 and C06b in this release. Caught
by verifying the name before shipping, not by the suite, which stayed
green because those paths never execute in tests. Fixed and pinned two
ways.

---

## [3.24.35] - 2026-08-06 — Cascades CV1, CV2, C01, C14, C39g, C39f

**1296 passed / 0 failed.** (1105 → 1296, +191 pins.)

Six cascades from `docs/audits/2026-08-05_remediation_methodology.md`.
Doctrine 0 (make the instruments trustworthy) is complete; four real
defect fixes follow it.

### CV1 — verification substrate

The live-tree guard watched exactly one directory
(`~/.acervator_logs/sim/runs`) by directory-name diff, and
`_LIVE_ROOTS[0]` was defined and never referenced. **Both isolation
breaches this project has shipped happened while it was green.** Now
file-granularity over both roots with three graded rules: any created
path fails; any Stone Tablet change fails; modification of a
pre-existing file fails only when no live Acervator process is running
(measured: the operator had two running while the suite executed).
`stat()` only — never opens a file, because `~/.acervator` holds
credentials.

Plus: collection floors counted statically from disk, Qt absence now
fails instead of skipping, and the first `MainWindow` boot smoke test
this repo has had (`grep -rn "MainWindow(" tests/*.py` previously
returned zero).

### CV2 — live decision-diff harness

Replays the REAL gate chains over REAL Stone Tablet windows and diffs
decisions, so a live-path cascade can prove it moved no SCRUM/FOLD
verdict. Borrows `TASignalProvider` and the real chain builders rather
than reimplementing them.

Measured while building it: perturbing the Bollinger period 20 → 21
across 72 decisions produced 36 indicator changes and **zero** decision
differences — true, but it meant the decision path went unproven, so the
tests lead with a synthetic flip that must be reported.

### C01 — a save never removes a bot record

`save_state` rebuilt `"bots"` purely from memory, so any transient
in-memory condition became permanent loss on the next 60s tick. The
sharpest case: `register()` refuses on capital over-allocation
(MEM-417) — a momentary state — and a minute later that bot's per-lot
cost basis is gone.

The adversarial pass found that **deletion was never implemented**:
`unregister()` touches no storage, and records vanished only because the
save rebuilt the file from RAM. "Saves never delete" therefore needed
`delete_bot()`, or deleted bots would have returned forever.

Verified on the operator's real 35-bot state: 3 saves preserve
1,965 lots / 819 tranches unchanged; a bot dropped from memory survives
two saves; an explicit delete stays deleted.

### C14 — telemetry resolves its root at call time

`ACERVATOR_TELEMETRY_ROOT` existed and was honoured — and unreachable,
because `TELEMETRY_PATH` bound at import. An earlier fix added the env
var and stopped there; it looked complete and changed nothing.

### C39g — bot.log diagnostics reach disk

`[COMPOUND SKIPPED]`, `TARGET GROWN`, `TARGET-GROW HELD`,
`FOLD_DIAG_SURPLUS_CHECK`, `[WIRE FIRE]` — the vocabulary the source
tells the operator to grep for — had only GUI subscribers, both ending
at `StatusLog.log()`, which never writes. Zero occurrences across the
whole log tree including the 7.4 GB `system.log`, not because the paths
never ran but because the channel never touched a file. Now routed to
`~/.acervator_logs/trade/diagnostics.log`, unfiltered, bounded by the
same rotation as its siblings.

This is why compounding has been undiagnosable for the entire
development history.

### C39f — drawing a wire no longer rewrites config

`_on_wire_created` set `profit_folding_active = True` on every
`wire.created`, and `bot_container.py:2404` re-emits that for every
stored wire on every boot — so an operator's OFF choice could not stick.
The handler now reports state instead of owning it. Blast radius
measured: 35/35 bots persisted `True`, so no immediate behaviour change.

### Supporting work

`C00` established version control (this tree had none), permissions
consolidated 3,866 → 121 with a deny list, and the release gate can no
longer print `[OK]` with checks skipped.

---

## [3.24.34] - 2026-08-05 — Cascades C00 + C43: make the instruments trustworthy

**1150 passed / 0 failed.** (1105 → 1150, +45 pins.)

Covers C00 (v3.24.33, folded in) and C43 from
`docs/audits/2026-08-05_remediation_methodology.md`. Doctrine 0: nothing
below these cascades can be verified while the tool that blesses every
release can print `[OK]` with every check skipped. Zero product
behaviour changes.

### C00 — baseline snapshot

This tree had never been under version control. `git rev-parse` returned
`fatal: not a git repository`, which made 66 `rollback` fields and every
"observe RED on the unmodified baseline" step in the remediation plan
name an operation that did not exist. `git init` + baseline commit;
`.gitignore` excludes build artefacts, caches, `_logs/`, a 63 MB
transcript backup and the generated sidecar, and deliberately TRACKS
`_archive/` because later cascades restore archived pin tests from it.
Scanned for secrets before staging: none present.

### C43 — release-gate integrity

Three defects, each measured rather than inferred:

- **Vacuous green.** `--no-pytest --no-archetypes --no-claims` left
  `failures` empty and printed `[OK] Release-ready (v3.24.32, 0 tests)`
  while writing a green sidecar. Observed in the wild: a `tests: 0`
  sidecar sat in the tree for 46 minutes advertising readiness.
- **Silently missing analyzers — a family of seven, not one.** Runners
  invoked as `python -m <tool>` do not raise `FileNotFoundError` when
  the module is absent; stdout is empty, so each took its
  `if not proc.stdout.strip(): return findings, "ok"` path. Affected
  `coding_archetype` (ruff, mypy, bandit, vulture), `gui_archetype`
  (ruff, bandit) and `docs_archetype` (proselint). `_run_vale` had the
  same shape via a different trigger — vale writes runtime errors to
  **stderr** with an empty stdout.
- **`main.py` version drift.** The gate never opened `main.py`. At build
  v3.24.32 the boot log read `Acervator v3.1.26 starting` and
  `setApplicationVersion` said `3.1.26` — 23 minor versions stale, so
  every log the operator had collected carried the wrong build.

Fixes: the sidecar now records `checks_run`, and a skipped check or a
zero-test run fails the gate and writes nothing; `verify_release_gate.py`
denies on a missing `checks_run`, any skipped entry, or `tests <= 0`;
`main()` binds `from src import __version__` and all three literals
derive from it.

### C43 step 7 — the boot guard that could kill boot (NF-154)

`_check_stale_dist_binary()` runs at `main.py:130`; `logger` is not bound
until `:225`. An inner `except` calling `logger.debug` raised
`NameError`, which the outer handler caught and then raised again from
its own `logger.debug` — escaping to module level and killing the process
before the GUI starts. The guard's own comment reads "Guard must NEVER
raise." Replaced with `_early_debug()`, gated on `ACERVATOR_DEBUG_BOOT=1`
and unable to raise. Armed only when a source tree sits beside a stale
build — exactly when the warning is supposed to help.

### vale

Installed (3.17.1), configured (`.vale.ini` + write-good, styles
committed so the gate needs no network), and promoted from optional to
required. Installing the binary alone was a measured REGRESSION: with no
config, vale errored and `_run_vale` reported `ok` with zero findings,
which is strictly worse than the honest `missing` it reported while
absent. `OPTIONAL_ANALYZERS` is now empty — a clone without vale on PATH
fails the gate rather than passing with reduced coverage.

### Records corrected

`CHANGELOG.md:263-265` claimed "The Simulator Swarm is driven" —
`register_sim_run` has no production caller in this build. Two
currently-green pins in `test_hooks.py` / `test_hooks_integration.py`
built a `tests: 0` sidecar with no `checks_run` — the signature of a
skipped run — and asserted ALLOW; their fixtures moved to the real shape
with assertions unchanged.

### Known debt

`_module_absent` now exists in three modules. Consolidation is a
cross-module refactor deliberately not done mid-cascade; noted at each
copy.

---

## [3.24.32] - 2026-08-05 — Sim fidelity: funding, fees, config, crossover

**1105 passed / 0 failed.**

Four defects found by the 2.0 audit, each of which silently biased or
invalidated results. Measured before and after on the live 35-bot fleet:

| | before | after |
|---|---|---|
| symbols trading | 25 | **35** |
| USDC symbols trading | **0** | **10** |
| fees charged | $0.00 | **$51.12** |
| Locked vs Spendable at t0 | $0 vs $3,300 | **equal** |

### Ten bots never traded, in any replay ever run

`seed_usd` summed every bot's `target_balance` into a single `"USD"`
deposit. The fleet is 25 USD-quoted and 10 USDC-quoted ($2,850/$450), so
all $3,300 landed under `"USD"` and the ten USDC bots opened with a zero
balance **in their own quote leg**. They could never fund a buy.

Confirmed on run `20260805T045429_926437`: 510 fills across exactly 25
distinct symbols, all USD-quoted; every `/USDC` symbol logged zero.

Nothing warned, because `sim_exchange` seeds unknown quotes to `0.0`
with `absent=False`, so the MEM-254 absent-side handshake passes. Now
seeded per quote currency, with a loud per-bot warning if any quote leg
opens empty — a silent no-op bot is worse than a loud refusal, because
the run still reports "35 bots" and the empty symbols read as market
conditions.

### The sim charged no fees at all

`fee_pct=0.0`. Measured on the same run: 510 fills, **$7,687.18
notional**, so **$122.99** went uncharged at the 1.6% that 24 of 35 bots
actually pay — 3.7% of the entire $3,300 wallet across ~52.8 days.
Biased the accumulation curve upward on every single fill.

Fees are now per-symbol, sourced from each bot's own config, because one
exchange-wide rate cannot represent 24 bots at 1.6% and 11 at 0.6%.

**Unit trap, documented in both files:** `BotConfig.trading_fee_pct` is a
PERCENT (1.6) consumed as `_eff_pct / 100.0`; the exchange multiplies
notional by a FRACTION. The `/100.0` is the difference between a 1.6%
fee and a 160% one.

### 44 of 70 config fields were silently defaulted

`_instantiate_bot` hand-enumerated 26 kwargs. The one that mattered
most: `trading_fee_pct` is 1.6 on 24 of 35 bots but the sim always got
the 0.6 default — and that value is the Minimum Opposing Trade Distance
term (`scrumming_bot.py:10019-10023`), so **live required a 6.6%
reversal to fire while sim required 5.6%**. The sim traded more freely
than live for entire replays.

Also defaulted: `max_cartridge_smart` (True on 12 bots),
`max_cartridge_size_pct` (5.0 on 6), `hedge_balance` (0.0 on 33), every
`circuit_breaker_*`, `position_ceiling_*`, `detonation_*`,
`self_reserve_capital`, `personal_hold_qty`, `wire_inflow_stack_pct`.
Those sit at defaults in *today's* fleet, so the whitelist looked
correct — until the operator tunes one.

Now filtered by `dataclasses.fields(BotConfig)` and splatted. Verified:
35 bots built, **zero field mismatches**, `trading_fee_pct` distribution
matches live exactly.

Mode-foreign fields are excluded using `bot_container`'s own
`_BOT_CONFIG_EXTRACTOR_ONLY_FIELDS` rather than a local copy, so the two
cannot drift — `make_bot_config` correctly refuses Extractor fields on a
scrumming config, and it caught this during development.

### Locked now equals Spendable at t0

Operator directive: *"Locked and Spendable amounts should be the same at
the start of any simulation run. Locked amount is a bot_state import."*

Sim bots started with **zero** base holdings, so the header read
Spendable = full seed, Locked = $0.00. Worse than a display bug: every
replay began with the whole fleet buying in from flat, a phase that
never occurs live, and the accumulation curve was measured across it.

`current_holdings` is not persisted (verified: 0 of 35 bots carry it),
so `target_balance` is the import — it IS the USD value of the position
the bot maintains. Each bot now opens holding `target_balance` worth of
base at the first candle. Verified: **$3,300.00 == $3,300.00**.

Spendable is also recorded per fill in the sim trade log, so a replay's
wallet trajectory can be reconstructed from the log alone and checked
against the header.

### Live crossover on the GUI-reachable Nuclear path

`NuclearController._construct_scout` built its bot **without**
`sim_mode`, with three consequences:

1. It resolved the process-wide `CapitalReservationRegistry` and wrote
   into `~/.acervator/reservation_state.json` — **live capital state**.
   That is the leak that accumulated 16,523 orphan reservations (6.5 MB)
   before v3.24.14.
2. Bus isolation happens *inside* `__init__` under `if self._sim_mode:`.
   With it False the scout wired to the **global** bus during
   construction; assigning `_bus` afterwards does not move subscriptions
   already made.
3. `enable_phantoms=False` removed a subsystem rather than isolating it.

Now constructed with `sim_mode=True`, an injected private registry, and
phantoms enabled. Verified at runtime: not the global registry, not the
global bus, phantoms on, live state file unchanged by hash.

`tests/test_nuclear_scout_isolation.py` pins all three.

Also: four `try/except/pass` handlers in `nuclear_controller.py` now log.

### Telemetry was writing into the live tree

`feature_telemetry.json` and `feature_validation.md` were written to
`~/.acervator` and `~/.acervator_logs` on every replay — both present on
disk, timestamped 2026-08-05 10:16, produced by a sim run. Same
isolation-breach class as the sim run-log and the capital registry.
Root is now overridable via `ACERVATOR_TELEMETRY_ROOT`; the live default
is unchanged.

### Live safety

Every shared-code edit was verified against the LIVE path: injected
registry defaults to `None` → same singleton; `_sma`/`_stdev` default to
full-length output; `wire_credits` conserves USD and never touches
tranche `usd`; telemetry default path unchanged. 13 checks, 0 failures.

Two changes do alter live behaviour, both deliberate fixes: `wire_credits`
bounding (shrinks `bot_state.json` 1.45 MB → 551 KB, USD conserved) and
the HEDGE emit now carrying `amount`/`usd` (it was logging every hedge
rebalance with `amount=0.0`). Neither touches order placement, sizing,
or gate decisions.

---

## [3.24.31] - 2026-08-05 — Sim bots are equivalents, not reduced copies

**1098 passed / 0 failed.**

Operator directive 2026-08-05:

    "Sim loads the fleet but the bots are instantiated as simulator
    equivalents with all of the same functionality except that operate
    in a simulated environment. I assumed the bots were the same
    already... but it may not yet be the case."

They were not. Audited from source, a sim bot was the live class with
features **subtracted**, not simulated:

| subsystem | before | site |
|---|---|---|
| capital reservation | **removed** — `if _sim_mode: return` | `scrumming_bot.py:1068` |
| reservation pre-check | **removed** (v3.24.27) | `:10089` |
| phantom balance | **disabled** — `enable_phantoms=False` | `fleet_replay_controller.py` |
| Smart Wire | **never ran in sim at all** | fixed v3.24.30 |
| event bus | isolated (correct) | `:330` |
| trade notifications | suppressed (cosmetic, correct) | `:1929` |

The flags switched features off rather than pointing them at simulated
backends. That is the opposite of the directive: a sim bot that never
reserves is not an equivalent of a live bot that does, and a soak built
on it cannot exercise reservation contention at all.

### The fix — isolate the backend, not the code path

- `ScrummingBot` accepts an injected `capital_registry`. `_crr()`
  resolves the injected instance when present and the process-wide
  singleton otherwise, so live behaviour is unchanged.
- The fleet controller builds a **private, non-persisting** registry per
  replay (`autosave=False`, temp state path) and injects it. The real
  reservation code path now executes against sim-only state.
- Both `if _sim_mode: return` gates are gone.
- **Phantoms enabled** in sim. Phantom balance is per-bot in-memory
  state, so it required no external isolation — it had simply been
  switched off.

The original defect that motivated the gates still stands and is still
prevented: the registry persists to `~/.acervator/reservation_state.json`
— live capital state — and sim sharing it produced **16,523 orphan
reservations (6.5 MB)** plus sells refused by live bots' claims.
Isolation now comes from *which* registry the bot holds. Verified by
hashing the live state file across a replay: **unchanged**.

### Honest limit

Reservations created during a sim replay: **still 0**. The plumbing is
correct and isolated — private registry injected, gates removed,
`self_reserve_capital=True` — but the feature does not yet demonstrably
fire. `_ensure_capital_reservation` is called at
`scrumming_bot.py:4675` with `self._last_price`, which is not assigned
until `:4739`, so the first tick returns on `current_price <= 0`. Not
claimed as working.

### Tests

`tests/test_sim_reservation_isolation.py` was rewritten. Its v3.24.27
version asserted sim **skips** the registry — a requirement this
directive reverses. It now pins the property that actually mattered all
along: live state is never touched (not the singleton, no autosave,
state path outside `~/.acervator`), plus that the feature runs rather
than being gated.

`tests/test_scrumming_capital_reservation.py`'s hand-built stub gained
`_crr` so it models the new seam. Its behavioural assertions are
unchanged — 26 pass exactly as before.

---

## [3.24.30] - 2026-08-05 — Nuclear Mode v2 + emit-contract detection

**1094 passed / 0 failed.**

Operator directive: *"Nuclear Mode does not run singular tapes. It runs
full Stone Tablets in loop across the fleet loaded from bot_state"* and
*"must be using the Simulator Swarm and testing all feature
functionality of the swarm. Every system feature must be able to be
verified and tested. This is the core design intention."*

### Nuclear Mode v2 — fleet soak

`nuclear_fleet_controller.py` loops the bot_state fleet over Stone
Tablet history until stopped. It **drives `FleetReplayController`**
rather than re-implementing a tick loop, so a Nuclear failure is
attributable to a real defect instead of to two simulators disagreeing.

Measured on the live fleet — 35 bots, 35 symbols:

| cycle | load | fleets | candles | c/s |
|---:|---:|---:|---:|---:|
| 1 | 0.99x | 1 | 200 | 21.0 |
| 3 | 2.46x | 2 | 400 | 39.3 |
| 5 | 3.95x | 4 | 800 | 65.2 |

- **`SystemLoadOscillator` is now wired.** Built v3.13.7, zero callers
  until now. Supplies the cosine-smoothed ramp (45 s up / 30 s sustain
  at 4x / 45 s down); per-cycle jitter supplies the noise.
- **Load is applied as CONCURRENCY**, not tick delay. An earlier draft
  scaled `tick_delay_s`, which only ever ADDS idle time — a "4x load"
  pulse would have made the machine quieter. Measured before the fix:
  throughput held at ~25.8 c/s while the multiplier swept 0.99x→3.14x.
- **COOLING is real.** Two defects made it dead-but-reporting-healthy:
  the sensor interface was guessed (`regime()` + property) when the
  oscillator calls `sample(now)` then reads the `current_regime`
  attribute, so every sample raised AttributeError; and `is_cooling` is
  a property, so calling it raised TypeError into a swallowing guard and
  pinned load to 1.00x. Unsensed runs cap at 1.5x — a 4x pulse shares
  this machine with the live trading engine.
- **The Simulator Swarm is driven.** `register_sim_run` /
  `update_sim_run` / `stop_sim_run` existed with zero callers; Nuclear
  Mode is the producer they were built for.

### Feature verification — coverage, not assertions of coverage

`nuclear_verification.py` declares the swarm's feature surface up front
so a feature that never fires reports **UNVERIFIED**, which is not the
same as passing. That distinction is the point: `SimStatStrip.set()`,
`compare_trades()`, `SystemLoadOscillator` and `register_sim_run()` each
passed their tests without ever running.

The tranche chain, per operator: *"Tranches are a core bot feature
generated by bot trade actions but they are supposed to be fed by smart
wire transactions to boost compounding potential across a given
topology."* Four separately-falsifiable links, now all passing:

    [PASS] tranche created by trade action
    [PASS] fed by smart wire
    [PASS] compounding boost applied
    [PASS] credit crossed bots (topology)
    85 tranches, 31 wire-fed, $23.02 wire USD, 31 cross-bot credits

Link 4 is the one that is easy to fake — a tranche fed by its own bot
proves nothing about topology. `wire_credits_rolled.by_source` keeps
per-source totals, so the source is compared against the owner. Bounding
`wire_credits` with a lossless per-source aggregate in v3.24.28 rather
than deleting it turned out to be load-bearing here.

**Smart Wire never ran in the simulator.** `grep SmartWireManager` found
live and stocks wiring, no sim path — so no tranche could ever be
wire-fed and links 2-4 could not pass however long a soak ran. Nuclear
now supplies the manager the bot already looks for
(`scrumming_bot.py:8259` calls `distribute_fold_profit` whenever
`_smart_wire_mgr` is set) and registers wires from adopted proposals, or
a ring across the fleet so cross-bot credit is exercised both ways.

### Emit-contract detection

Operator directive: *"develop emit detection intelligence... We are
always dealing with expected inputs and outputs."*

`src/core/emit_contracts.py` declares each topic's expected payload and
validates what actually appears. Three silent failure classes:
never-emitted, missing/renamed field, bad value.

It was written because it caught me. The verifier read
`data["action"]`; the bus writes `data["type"]`
(`scrumming_bot.py:5773/:7271/:8308`) — `action` is the LOG schema's
name. Nothing raised. Coverage reported **0/17 while 665 trades flowed
past**. A key-name mismatch is invisible to both sides: the producer
emits fine, the consumer reads fine and gets `None`.

**Live defect found on its first run.** `scrumming_bot.py:8568` (HEDGE
rebalance) emitted `size=_use` — USD spent, not base units — and no
`amount`. `LogManager._on_trade_filled_bus` reads
`merged.get("amount", 0)`, so **every hedge rebalance was written to the
live trade.log with amount=0.0**; the fill quantity was absent from the
trade record. Now emits `amount=_hedge_asset` and `usd=_use`.

`trade.filled` also has two payload shapes — five sites nest under
`data={...}`, five pass kwargs flat. Both are accepted; the split is
documented rather than papered over.

### Known limits — Nuclear Mode v2

- Nuclear Mode is **not reachable from the GUI**: the panel still drives
  the old single-tape controller.
- Coverage is **9/17**. Unverified: `entry`, `dist`, `auto_detonation`,
  all three gate features, and both wire features. Not failures —
  features this workload never exercised.
- The soak reproduced an existing live defect under load:
  `PRE-FLIGHT REJECTED: SELL notional $0.1550 below ZEC/USD min_cost`.

---

## [3.24.29] - 2026-08-05 — Simulator chart work + evaluation-mode telemetry

**1066 passed / 0 failed.**

### The 510-vs-517 question

The same 15,211 candles run twice — anchored, then Full Evaluation —
produced 517 vs 510 trades.

The delta is not 7. Both runs fire at the **same timestamps, same
symbols, same sides**; what differs is the *amount*:

    2026-06-15T22:20  CHIP/USD BUY   76.505452972  vs  76.6050569051
    2026-06-15T23:20  CHIP/USD BUY   77.068947095  vs  77.0700677759

**371 of 517 and 364 of 510 trades differ** — ~72%, almost entirely by
small sizing fractions. The gates agree; position sizing drifts.

Cause is the skip path: on a skipped candle the exchange steps (cursor
and price advance) but `bot.tick()` never runs. TA stays correct — it is
read from exchange history at each anchor — but per-tick state (holdings
refresh, compounding, tranche maturation, interval timers) does not
advance, and that state feeds sizing.

This is the anchored design working as directed, not a defect. The
consequence is what matters: **anchored is a screening mode. Parity
comparisons against live must use Full Evaluation**, because live ticks
every candle.

- **Evaluation mode is now recorded.** Neither run's `meta.json` said
  which mode it ran in, so the two could not be told apart from their own
  logs. `anchored`, `full_evaluation`, `anchor_candles`,
  `candles_skipped` and `bots_ticked` are now persisted.

### Charts

- **Plot boundaries** around each price/VWAP band, drawn after the
  polylines so a line touching the edge cannot overdraw the frame.
- **Trade markers** — 3px dots. Green = the fill landed on a candle
  carrying a historical trade; red = a sim-only fire. Markers store a
  series INDEX, not an x-coordinate, so they survive resize; the index is
  remapped through the downsample in `append_tick`, because halving the
  series without halving the indices would slide every marker off its
  candle and compound on each decimation.
  - Markers are queued by the replay worker and applied on the Qt thread
    via the existing snapshot path. Drawing them at fire time would be
    cross-thread widget access — exactly what v3.24.19 removed.
  - Colour is classified against a new `_expected_indices` set, built in
    BOTH modes. `_anchor_indices` is `None` under Full Evaluation, so
    reusing it would have painted every FE marker red.
- **Expand button** per half — full display width, half height, centred
  on the screen the window is actually on (not the primary screen) and
  inside `availableGeometry` so it does not slide under the taskbar. The
  widget is reparented into the dialog and **handed back on close**;
  without the restore, expanding once would permanently strip the chart
  out of the panel behind it.

### Labels + layout

- **The charts are no longer labelled "Indicator Voting Panel."** That
  label sat above both halves and read as naming the price/VWAP charts
  directly beneath it. Each half now carries its own header: the charts
  are **"Historical Price vs. Position VWAP"**, and only the table is the
  voting panel.
- **Voting table stretched to full panel width.** Was
  `ResizeToContents`, which sized six short-value columns to their text
  and left ~40% of the panel empty. Symbol keeps content sizing; the five
  numeric columns divide the remainder.

### Known limits

- The chart work was visually confirmed against a headless render with
  synthetic data through the real widgets. Geometry, borders, dots,
  labels and stretch are real; behaviour under a live replay is not yet
  observed.
- Marker colour depends on `_expected_indices`, built from live trade
  timestamps. If Fetch YTD has not run, that set is empty and every
  marker paints red — honest (there is nothing to validate against) but
  it can read as failure.

---

## [3.24.27] - 2026-08-04 — Sim isolation from the capital-reservation registry

**1,066 passed / 0 failed.**

### The defect

`CapitalReservationRegistry` is a process-wide singleton persisted to
`~/.acervator/reservation_state.json` — **live state**, autosaved on
every mutation.

The WRITE side was already gated on `_sim_mode`, and its own comment
names the pattern (`scrumming_bot.py` ~L1036):

> "Same defect class as the v3.24.12 event-bus leak, but worse: that one
> was in-memory per-process, this one survives on disk and feeds live
> allocation decisions."

**The READ side was not gated.** A sim bot consulted the live registry
and refused its own sells because *live* bots held reservations on that
asset. Observed during a replay on 2026-08-04:

    CRR.effective_available: 0bee0dac on ETH — others reserved
    0.1183015458 > total_holdings 0.08404350092. Clamping to 0.

No live bot competes for a sim bot's assets, so the comparison is
meaningless. Worse, it made a replay's outcome depend on whichever
reservations happened to be on disk at the time — which destroys
reproducibility, and reproducibility is the entire point of the parity
work this feeds.

### The fix

The registry consultation in `_execute_sell` is now behind a `_sim_mode`
guard, and the skip is logged rather than silent. Live behaviour is
untouched: the refusal message, the `return None`, and the smart_orders
backstop fall-through all remain.

Verified: a 6-asset / 900-candle replay now emits **0** over-reservation
warnings (was one per affected tick), and `reservation_state.json` mtime
is unchanged.

A pin asserts that *every* `effective_available(` call site in the bot
has a `_sim_mode` guard within 40 lines above it, so the leak cannot
simply move to a new call site.

### Two testing notes worth keeping

- **Stale `__pycache__` made a passing guard look absent.** An early run
  of these tests reported the guard missing when it was present in the
  file; `inspect.getsource` was serving cached source. `main.py` purges
  bytecode at startup for exactly this reason — pytest does not. The
  helper now clears `linecache` first.
- **Searching for `effective_available` matched the comments** that
  explain the guard, which sit above it, so the search found prose and
  concluded the guard was missing. The assertion now matches
  `effective_available(` — the call, not the name.

---

## [3.24.26] - 2026-08-04 — Topology stress backtester

**1,057 passed / 0 failed.**

Operator directive: "Nuclear Mode = topology stress backtester."

### What it answers

`topology_proposals` scores candidate topologies against one price
history. A score computed on one history says nothing about whether the
topology survives a different one.

`src/trading/topology_stress.py` replays the same proposal across
several noise realisations and reports the **distribution**. The headline
is dispersion, not the mean: a topology whose accumulation changes SIGN
between trials was fitted to one particular sequence of price wiggles,
and the score that recommended it is an artefact. A single backtest
cannot see that, which is precisely why single backtests over-promise.

Verdicts: `ROBUST`, `NOISY`, `NEGATIVE`, `FRAGILE` (sign changed),
`NO_DATA`.

### Design decisions worth recording

- **Measures accumulation, not P&L.** Acervator accumulates a base asset
  by scrumming profit off volatility. Scoring on realised P&L would rate
  a bot that liquidated its entire position as a triumph.
- **Drives the real engine.** Trials run the real
  `FleetReplayController` against a real `FleetSimExchange`, ticking real
  `ScrummingBot` instances on a private `EventBus`. Nothing re-implements
  trading logic — a stress result from a simplified model would measure
  the model.
- **Reuses Nuclear Mode's noise.** Perturbation comes from
  `nuclear_candle_source._Tape`, not a second implementation, so the
  stress conditions are the ones Nuclear Mode actually plays. A parallel
  implementation would drift and then describe a market that is never
  simulated.
- **Undefined dispersion is reported as undefined.** When the median is
  zero but trials disagree, the ratio has no meaning; returning 0.0 there
  would report perfect stability for trials that flatly disagree.
- **A failed trial does not discard the run.** One asset with short
  history should not throw away the other trials' evidence.

Stone Tablets are read-only throughout; noise is applied to copies, and
that is pinned.

### Verified against the real archive

BTC + ETH, 61,200 candles each, 3 trials at 12.19% / 18.72% / 12.22%
noise, 599 candles played per trial:

    VERDICT: ROBUST   median base gained +0.07766592   dispersion 0.27
      seed 100  noise 12.19%   14 trades   base +0.09047800
      seed 101  noise 18.72%   17 trades   base +0.06963672
      seed 102  noise 12.22%   12 trades   base +0.07766592

### Supporting change

`FleetSimExchange` now records `_opening_balances`. `_balances` mutates
as the replay trades, so without a snapshot no caller can answer "what
did this run actually change?" — the only question an accumulation
backtest asks.

### Two live-engine findings surfaced by the run

Both are real bot behaviour under simulation, not defects in this module,
and neither is fixed here:

- `PRE-FLIGHT REJECTED: BUY amount 0.00000000 ... below ETH/USD
  min_amount` — a zero-amount order reaching the pre-flight guard.
- `CRR.effective_available: others reserved 0.1183 > total_holdings
  0.0810. Clamping to 0.` — the same over-reservation class as the 16,523
  orphaned reservations cleaned up earlier in this session.

### Not shipped

GUI wiring into the Nuclear Mode panel. The engine and its operational
report are complete and tested; surfacing them in the panel is a visual
change and wants operator confirmation on the render before it ships.

---

## [3.24.25] - 2026-08-04 — StochasticRSI bound; Group B closed

**1,031 passed / 0 failed.** Bit-identical across 72 real-tablet windows.

### Step 4 — StochasticRSI stoch window bounded

Only `k_line[-1]`, `k_line[-2]`, `d_line[-1]` and `d_line[-2]` are read.
Walking the chain backwards, `d_line[-2] = mean(k_line[-4:-1])` needs
`k_line[-4:]`, which needs `stoch[-6:]` — so exactly
`k_smooth + d_smooth` trailing stoch values suffice, and every entry
those reads touch is past `_sma`'s shorter-divisor warm-up branch.

Taking fewer would silently alter `k_line[-2]` / `d_line[-2]`, which
drive the K/D crossover tests emitting confidence-0.8 SCRUM/FOLD
signals. Pinned so a later change cannot quietly shrink the bound.

### Correction to the audit's estimate

The audit predicted `StochasticRSI.compute` would go **0.0390 → 0.0026
ms**. It does not. Measured:

| window | `compute()` | RSI loop | stoch loop (full → bounded) |
|---:|---:|---:|---:|
| 100 | 0.0414 ms | **0.0335 ms (81%)** | 0.0322 → 0.0029 |
| 300 | 0.1082 ms | 0.0978 ms | 0.1111 → 0.0027 |
| 1000 | 0.3655 ms | 0.3476 ms | 0.4323 → 0.0026 |

0.0026 ms is the *isolated stoch loop*, not the indicator — the audit
conflated a loop measurement with the whole function. The RSI series
build is a forward recurrence over the full history, cannot be
tail-bounded, and is 81% of the cost at the 100-candle production
window. The real gain here is modest and scales with window size.

### Step 3 — shared TA bundle: NOT SHIPPED

Measured its actual headroom before committing to it:

| candidate | cost | share of the 0.672 ms TA tick |
|---|---:|---:|
| 13× `closes` rebuild | 0.0232 ms | 3.5% |
| duplicate `compute_heikin_ashi` | 0.0399 ms | 5.9% |
| **realistic total** | **~0.061 ms** | **~9%** |

The audit estimated ~0.12 ms — roughly double what is measurable. TA is
~29% of candle cost, so the whole of Step 3 buys **~2.6% of replay
time**, in exchange for threading a bundle kwarg through three public
functions with six external call sites, in code the live engine runs.
The audit itself notes the memo variant can "silently feed one asset's
Bollinger bands to another bot."

Dropped on that evidence. It can be revisited if TA ever becomes the
dominant cost again.

### Also

`ta_engine.py` now passes the coding archetype gate cleanly. Its one
blocking finding was an unannotated accumulator in the A/D line — which
is a forward recurrence and genuinely cannot be tail-bounded, now noted
in place so the next reader does not try.

---

## [3.24.24] - 2026-08-04 — gate.log analysis path

**1,029 passed / 0 failed.**

Audit item #5. Measured on the operator's real logs: `gate.log` +
`gate.log.1`–`.5` = **165,062 rows across 262,868,525 bytes** of NDJSON,
83 distinct bot_ids, 1,989 entries per bot on average, 12,366 for the
busiest. Both consumers run synchronously on the Qt thread.

### Streaming instead of materialising

`_compute_soft_start` did `gates = list(live_gate_decisions())` —
building the entire rotation chain in memory before doing anything.
`live_gate_decisions` has always been a generator and has always
accepted `since`; nothing passed it.

| | materialised | streamed |
|---|---:|---:|
| time | 4.329 s | **2.701 s** |
| heap | **1,123.9 MB** | **20.2 MB** |
| gate rows | 165,062 | 165,062 |

**55× less heap**, with per-trade classification verified identical
across all 612 live trades.

Two supporting changes: `build_gate_index` retains a four-field
projection instead of the whole parsed line (the only fields any
`gate_entry` consumer reads — verified by grep), and this path now passes
`validate=False`, since `_validate_gate_entry` ran nine field checks per
row for a computation that reads four.

### `since` now actually saves work

The filter ran *after* `json.loads`, so the cutoff discarded work already
done — and the `history_tab` docstring claiming it stopped the iterators
scanning back was simply false. Two conservative pre-parse filters:

- **File-level:** a *rotated* file whose mtime precedes the cutoff cannot
  hold a qualifying row, since mtime is its last write. The active file
  is never skipped — it is still being appended to, so its mtime says
  nothing about its oldest row.
- **Line-level:** raw-text ISO prefix comparison before parsing.

| window | rows | time |
|---|---:|---:|
| 90d (all) | 165,062 | 1.726 s |
| **30d** | 366 | **0.004 s** |
| 7d | 284 | 0.004 s |

**431×** on a realistic History page window. Neither filter is
authoritative — the parsed-timestamp check still runs, so a false keep
costs one parse and a false reject is impossible by construction. That
matters because sim-parity tooling reads this same path; a silently
dropped gate decision would corrupt a parity claim rather than merely
slow it down.

### `_nearest` → bisect

The docstring claimed "per-bot lists are small relative to the total".
Against real data that is false — 597 trades × their bot's list is
3.4 M iterations, measured at 0.971 s on the Qt thread.
`build_gate_index` already sorted each list, so the ordering bisect needs
was being built and then ignored. On a sorted list the minimiser of
`|ts - target|` is at the insertion point or immediately before it, so
probing both is exact, not approximate. `i-1` is probed first to preserve
the original first-wins tie-break.

### A status that was being mislabelled

`classify_trades` assigned `LOG_GAP` in **both** the
`elif _in_log_gap(...)` branch and the `else`, so the scan was dead work
*and* two different findings were reported as one.

New `NO_GATE_IN_TOLERANCE`: the bot was logging on both sides of the
trade, but nothing landed within tolerance. That is materially different
from "the app was down", and it is the more alarming of the two. On the
operator's real logs the split changes from 218 `log_gap` to **211
`log_gap` + 7 `no_gate_in_tolerance`** — seven trades whose missing gate
decision had nothing to do with an outage, previously invisible.

---

## [3.24.23] - 2026-08-04 — Stone Tablet lazy bodies (shared with live)

**996 passed / 0 failed.**

Audit items #3 and #4, which share one fix: stop deriving from candle
bodies what the 0.19 MB MANIFEST already carries.

### #4 — boot no longer loads the archive

`StoneTabletsRegistry.__init__` called `read_tablet()` for every manifest
row, fully parsing all 406 tablet files. `main.py:486` builds the
registry at app boot.

| | before | after |
|---|---:|---:|
| construction | **13.154 s** | **0.008 s** |
| resident memory | **+2,282 MB** | **+6.4 MB** |
| bodies held | 406 | 0 |
| `coverage_summary()` total | 7,230,993 | 7,230,993 |

That was a 13-second blocking startup stall and 2.3 GB held for the
lifetime of the process that executes real trades — for candle bodies
boot never reads.

Boot asks for exactly `coverage_summary()` and `stale_assets()`. Both are
answerable from metadata: manifest rows carry `candle_count`,
`first_ts_ms`, `last_ts_ms` and `listed_at_ms`, and summing
`candle_count` over the live manifest reproduces the archive total
(7,230,993) exactly. `read_manifest()` costs 0.0021 s.

Bodies now load on first genuine need — `get_candles`, `missing_ranges`,
`ingest_candles` — through a `_tablet()` helper, behind a 64-entry LRU so
a 406-asset sweep cannot re-accumulate the 2.3 GB this removes. A 35-bot
fleet replay touches ~35 tablets.

The old warn-and-skip behaviour for a manifest row whose file is gone is
preserved via a `Path.exists()` check — 406 stat calls instead of 406
JSON parses. Corruption is discovered on first body read and treated as
absent rather than raising.

### #3 — ingest no longer re-checksums the whole archive

`_persist_manifest` rebuilt every row through `entry_from_tablet()`,
which calls `Tablet.compute_checksum()` on all 406 tablets.
`ingest_candles` calls it once per 350-candle chunk — roughly 103 chunks
per asset for a YTD fill.

It now rebuilds from the metadata index, reusing each tablet's stored
checksum, and `ingest_candles` refreshes only the row it actually
changed. Measured: one checksum is 4.68 ms for 4,026 candles
(1.16 µs/candle), so a full-archive pass over 7,230,993 candles is
**~8.4 s** — corroborating the audit's directly-measured 7.46 s. The new
shape is one checksum plus a 0.93 ms write.

MANIFEST is still written every chunk. The fetcher depends on that so a
crash mid-fetch loses at most one chunk; the fix makes the write cheap
rather than less frequent.

Audit finding #15 (missing `(asset, exchange)` index) is folded in — the
metadata index serves that role via `_keys_for()`.

### Verification — lazy bodies

18 pin tests, the important ones being equivalence: metadata-derived
totals, timestamp bounds and availability are asserted equal to what the
candle bodies actually contain, because a fast path that disagrees with
the data is worse than a slow one. Also pinned: boot-path queries load
zero bodies, eviction does not lose data, and `_persist_manifest` does
not drop un-loaded assets from MANIFEST — the failure mode if it had been
rebuilt from the body cache instead of the index.

Live archive verified unchanged after the full run: 406 entries,
7,230,993 candles, 407 files on disk.

Note for future readers: `_load_from_manifest` derives each tablet path
from `asset/timeframe/year/exchange_id` via `tablet_path()`. The
manifest's `file` field is informational and is not used for lookup.

---

## [3.24.22] - 2026-08-04 — TA suffix-only windows (shared with live)

**978 passed / 0 failed.**

First item of the audit's Group B — the first change in this series that
alters code the live trading engine executes. It ships only because the
output is provably unchanged.

### The change

`_sma` and `_stdev` were O(n·period): each of n outputs re-sums a window
of `period` values across the full history. Every consumer reads at most
the last 35 entries, so the leading n−35 were computed and discarded on
every tick, for every bot, for every candle.

New `_sma_tail` / `_stdev_tail` compute only the trailing entries.
Earlier positions are `None` rather than `0.0`, so reading one raises at
the point of misuse instead of feeding a plausible wrong number into a
gate.

Four call sites converted, each with a tail derived from **its own
config** rather than the module default, so a non-default period still
gets every value it reads:

| site | tail | reads |
|---|---|---|
| `BollingerBands.compute` | `self.period` | `[-1]` + widths slice |
| `SlingshotIndicator.compute` | `squeeze_lookback + 5` | `range(n-win, n)` |
| `detect_bb_proximity` | `1` | `[-1]` only |
| `detect_landing_strip_v2` | `1` | `[-1]` only |

`StochasticRSI` was deliberately left on full history: it chains
`d_line = _sma(k_line, …)`, so a `None` prefix would propagate into a
sum. That is the audit's Step 4 and needs its own bound.

**Prerequisite fix:** `BollingerBands` built its `widths` list over
`range(len(sma))` — the entire history — while consuming only
`widths[-period:]`. That was the sole site indexing across the full
range, so no suffix form was possible until it was narrowed.

### Why suffix and not rolling

A rolling sum / sum-of-squares accumulator is the obvious optimisation
and it is **prohibited here**. It was measured at 2.02e-12 max relative
difference — close, not identical. Every consumer of these values is a
threshold comparison (`bb_pos < 0.15`, `band_width < avg_width * 0.75`,
`price >= upper - tol_val`) and `upper/lower = mid ± 2·std`, so drift in
the last bits of `std` propagates straight into a live SCRUM/FOLD
decision on a knife-edge candle.

Narrowing the range of `i` leaves each computed element's arithmetic
byte-for-byte unchanged. An accumulator changes the order of float
operations, and therefore the result.
`test_a_rolling_accumulator_would_NOT_be_bit_identical` asserts this
executably rather than by comment.

### Verification

Bit-identity was established **before** the change was accepted, against
72 windows of real Stone Tablet data across 6 assets — all 12 voting
signals with their direction/confidence/weight/details, both standalone
detectors, and the raw `_sma`/`_stdev` series at three periods, compared
by `repr()` so the check is exact rather than approximate.

    [OK] BIT-IDENTICAL across 72 windows x 14 fields

### Measured — 3.24.83

| | before | after |
|---|---:|---:|
| `VotingEngine.compute_all` | 0.9532 ms/tick | 0.6210 ms/tick |

**1.53×**, saving 0.332 ms/tick — about 174 s of CPU across a 35-bot ×
15,000-candle replay. End-to-end replay under the simulated GUI pump
moved 14.41 → 14.95 candles/s; the smaller end-to-end delta is expected,
since TA is now one cost among several rather than the dominant one.

---

## [3.24.21] - 2026-08-04 — Silent-failure sweep

**967 passed / 0 failed.**

Every `except: pass` that hid a failure without recording it is now
either logged or gone. Counted by AST across `src/`, `tools/` and
`main.py`:

| category | before | after |
|---|---:|---:|
| broad (`Exception`/bare) handlers | 250 | 211 |
| **broad AND unjustified** | **39** | **0** |
| carrying a justification comment | 212 | 212 |
| narrow (specific types) | 64 | 65 |

The 212 justified best-effort probes were left alone — they are
deliberate and annotated. The 39 unjustified ones are where real bugs
lived.

### A live bug the swallow was hiding

**`start_all_progress_dialog.py` — the Start All dialog never worked.**
`_on_progress_event` read `event.payload`. That attribute never existed:
`EventBus.emit` builds `Event(topic=topic, data=kwargs)`
(`event_bus.py:136`) and `Event.__getattr__` raises
`AttributeError("Event has no data field 'payload'")` for anything not in
`data`. All six emits in `BotManager.start_all` pass their fields as
kwargs, so the handler raised on *every* event — and
`except Exception: pass` ate it.

Operator-visible symptom: Start All opens a dialog stuck on "Preparing to
auto-start bots…" with an empty list and a disabled Close button for the
entire staggered start, which then never auto-dismisses. The defect
survived its whole lifetime because the swallow removed the only
evidence.

### Failures that are now visible

- **`state_manager.py`** — a failed state *backup* was silently skipped,
  then the state file was overwritten anyway. The backup is the only
  recovery path `load_state` has; the safety net could have been gone for
  weeks with no signal. A failed `clear_state` unlink was also swallowed,
  so state the caller believed was deleted would resurrect on next boot.
- **`capital_registry.py`** — reservation persistence failures were
  swallowed as "in-memory authoritative". True only within one process:
  if every persist fails, reservations vanish on restart and capital the
  operator believes is reserved is free for other bots to claim. That is
  the shape of the 16,523 orphaned reservations already cleaned up once.
- **`extractor_bot.py`** — a ticker fetch failure after an entry signal
  had already matched was a bare `continue`, so a trade the bot decided
  to take and then did not make looked identical to no signal at all.
- **`stock_accumulation_bot.py`** — a TA compute failure left
  `_last_summary` at its previous value, so the bot kept trading against
  a stale snapshot that looked current downstream.
- **`version_sweep.py`** — every scanning loop skipped unreadable files
  silently, including `check_secrets`. A sweep that skipped a file then
  reported "no hard-coded credentials" was reporting that it had not
  looked, in language indistinguishable from having looked and found
  nothing. Skips are now recorded and exposed via `skipped_files`.

Five modules had no `logger` at all and now have one.

### Also fixed

- **`_target` / `_entry_px` in `scrumming_bot.py`** were bound only inside
  a `try` whose `except` can fire before either is set, then read under a
  flag that merely correlates with them being bound. Safe today by
  accident, one control-flow edit from a `NameError` on a live
  wire-income event.
- **`caplog` cannot see Acervator loggers.** `logging_engine.py:315` sets
  `logging.getLogger("acervator").propagate = False`, so records stop
  there and never reach the root handler pytest installs. Any log
  assertion passed in isolation and failed in a full run depending purely
  on whether an earlier test had constructed the engine. New
  `capture_log` fixture in `tests/conftest.py` attaches directly to the
  named logger.

---

## [3.24.20] - 2026-08-04 — Quality-gate calibration, Nuclear Mode revival, replay throughput

**941 passed / 0 failed.**

The release gate was green while shipping a guaranteed startup crash. This
cascade fixes the gate, then fixes what the corrected gate found — and
takes the first group of wins from the complexity audit.

### Replay throughput — the real cause of the 29× gap

Measured A/B against the real controller under a simulated 50 ms GUI pump,
35 bots, 200 candles:

| | before | after |
|---|---:|---:|
| candles/s | **3.67** | **14.46** |
| yields/candle | 4.37 | 0.32 |
| elapsed | 54.6 s | 13.8 s |

**3.94×.** The before-figure brackets both the operator's measured GUI mean
(2.80 c/s) and the audit's predicted ceiling (3.98 c/s), so the bench
reproduces the real defect rather than a synthetic one.

- **Yielding is now time-budgeted, not count-based**
  (`fleet_replay_controller.py::_maybe_yield`). Under the GUI the asyncio
  loop is pumped by a Qt QTimer — `loop.call_soon(loop.stop);
  loop.run_forever()` at `main.py:955` — which executes exactly one
  `_run_once()` pass per fire. A task rescheduled by `await
  asyncio.sleep(0)` therefore does not resume until the next 50 ms tick:
  **one yield costs one full pump period.** The old scheme yielded once per
  candle plus once every 8 bots = 5 yields/candle at 35 bots = 251
  ms/candle. `_YIELD_EVERY_N_BOTS` is deleted.
  - The stamp is taken **after** the `await`, not before. Stamping first
    means the parked 50 ms already exceeds the budget on resume, so every
    call yields — measured at 35.1 yields/candle, *worse* than the scheme
    it replaced. Pinned by `test_replay_yield_budget.py`.
  - `main.py`'s timer interval is deliberately untouched: that pump is
    shared with the live trading engine.
- **`FleetSimExchange.get_ohlcv` copied every row twice.** `get_history`
  already returns freshly-built lists; mapping `_ohlcv_row_from_series`
  (itself `list(row)`) over them copied 100 new lists into 100 more —
  ~105 million redundant allocations across a 35-bot/15,000-candle replay.
  The removed copy protected nothing.
- **The open-order sweep was quadratic in trade count.**
  `_sweep_open_limit_orders` walked `list(self._orders.values())` every
  candle step, and `self._orders` never shrinks. Replaced with an
  `_open_by_symbol` index maintained at all three status transitions.
  Pinned against the failure the index introduces — a stale entry
  re-settling a filled order and moving balances twice.

The replay is now **compute-bound rather than pump-bound**: ~69 ms/candle,
of which only ~16 ms is pump wait. Further gains have to come from the TA
bundle (audit item #2), not from scheduling.

### Live state — `wire_credits` no longer grows without bound

`wire_credits` accumulated inside every fold tranche and was never
pruned. Each wire-income event appends one entry to *every* open tranche,
so growth is credits × tranches, not credits. The list was also
**write-only** — appends at exactly two sites, zero readers anywhere.

Measured against the operator's live `bot_state.json` (read-only):

| | before | after |
|---|---:|---:|
| `bot_state.json` | 1,450,426 B | **551,297 B** |
| wire_credit entries | 3,376 | 567 |

**62.0% smaller.** One bot (`7c4c4ff3`) held 3,325 entries — 96% of its
385,930-byte record. The file is re-serialised on a 60 s timer, so this
was recurring I/O.

Detail is capped at the 20 most recent entries per tranche; everything
older folds into `wire_credits_rolled`, preserving count, total USD and
USD-per-source. These are money provenance, so the record is compacted
rather than discarded — no credited dollar leaves the totals (reconciled
at $128.244664, residual $2.06e-7 from decimal rounding in the aggregate;
tranche `usd` balances are not touched by this path at all). Compaction
also runs on state restore, since the append-side cap alone would never
reach a tranche that stops receiving credits.

Also hardened while in this function: `_target` and `_entry_px` were
bound only inside a `try` whose `except` can fire before either is set,
and read later under a flag that happens to correlate. Safe today by
accident, one control-flow edit away from a `NameError` on a live
wire-income event. Now bound explicitly.

### Nuclear Mode — revived

- **Tapes now come from the Stone Tablet archive.**
  `NuclearCandleSource` scanned only `sadp/RAIntSimBat/data/cache/*.json`,
  a directory removed with SADP. `list_tapes()` returned `[]` on every
  call, so the mode was inert — while its empty state told the operator to
  "run an RAIntSimBat battery", an instruction that could no longer be
  followed. It now selects the fullest tablets (406 available, 7,230,993
  candles) as tapes A–L. The legacy cache still wins when present.
- **10–25% market-structure noise per pass** (operator directive
  2026-08-04). Amplitude is drawn once per direction flip, not per candle,
  so a pass has consistent volatility character. Perturbation is
  deterministic in `(seed, index)` — `history()` re-reads the same indices
  every tick, and values that moved between reads would mean TA computed
  over a series that never existed. OHLC validity is re-established after
  perturbation and timestamps are never touched.
- **Tablets are read-only.** Asserted at byte level: SHA-256 across all
  tablet files is identical before and after a 1,200-candle noisy playback
  (`test_playback_does_not_alter_tablet_files`).

### Gate calibration

- **`reportPossiblyUnbound` was demoted wholesale to `low`** in
  `tools/harness/coding_archetype.py`. It is genuinely noisy in the
  `try: import X / except ImportError` pattern this codebase uses everywhere —
  but that noise was suppressing the real signal. Measured over all 174 source
  files: **2,456 import-bound occurrences (noise) vs 9 assignment-bound (real),
  zero ambiguous.** Severity is now decided by walking the AST to find how the
  name is bound, so the import pattern stays quiet and a genuine
  conditionally-assigned local blocks the gate.
- **Ruff rule families were matched on `code[0]`**, a single character. So
  `SIM114` (a style suggestion) resolved to family `S` — bandit-mirror,
  `high` — and blocked releases, while `RUF*` and `ANN*` collapsed to `R`/`A`
  and fell through to `low`. Family extraction now uses the full alphabetic
  prefix.
- **`F821 Undefined name` was `medium`** and therefore non-blocking, so a
  guaranteed `NameError` scored the same as an unused import. The fatal
  pyflakes codes (`F821`, `F822`, `F823`, `F811`) are now `high`.

**Proof:** `main.py` before the fix — passed, 259 findings, zero high. After —
**failed, exactly one high finding: the startup crash below.**

### Found by the corrected gate

- **`main.py:1107` — `UnboundLocalError` on every fresh install.**
  `_autostart_bot_count` is assigned only at `main.py:699`, nested inside
  `if state_mgr.has_saved_state():`, but read at function-body indent at 1107.
  On a new machine, after deleting all bots, or on a state parse failure, the
  app dies before `app.exec()` — the visible symptom is a splash screen that
  flashes and vanishes. Fixed by binding the counter before the conditional.
- **`fleet_replay_panel.py:1061` — `NameError` inside an error handler.**
  A v3.24.19 regression: the exception variable was renamed to `_ap_exc` when
  `_feed_stat_strip` was split across the thread boundary, but the `logger.debug`
  below still referenced the old `_ss_exc`.

### Docs gate

- **`typography.symbols` demoted out of the blocking set** in
  `tools/harness/docs_archetype.py`. Measured across 40 markdown files:
  **747 of 773 findings (96.6%) were `typography.symbols`** — 735 of them
  curly-quotes alone — while `misc.illogic` and `security`, the two other
  families marked blocking, produced **zero findings and never once fired**.
  The gate's entire blocking signal was straight-vs-curly quotes.
- **proselint no longer sees code.** It has no markdown model, so it linted
  fenced blocks and inline spans as English. Two real false positives:
  `O(R)` (Big-O over reservations) matched the registered-trademark rule, and
  `DB_PASSWORD = "hunter2"` inside a code span was linted as prose. Acting on
  either would have corrupted the sample. `_strip_markdown_code` now blanks
  code while preserving line numbers exactly.

### Test isolation

- **The suite was writing into the operator's live log tree.** `SimRunLog`
  defaulted to `~/.acervator_logs/sim`, so every pin test created a real run
  directory there. By 2026-08-04 that tree held 62 run directories of which
  **54 were 4-to-59-candle test artifacts**, and diagnosing the replay slowdown
  meant filtering them out of the operator's own performance record first.
  `tests/conftest.py` now redirects the root per-session and asserts the live
  tree did not grow.

---

## [3.24.19] - 2026-08-04 — Simulator visual/replay decoupling

**875 passed / 0 failed.**

- **The replay worker thread called Qt widget setters directly**
  (`update_gates`, `append_tick`, `update_bot_row`, `chart.update()`), on the
  strength of a docstring claiming Qt would marshal them. It does not — a direct
  method call is a direct method call. Replaced with a producer/consumer split:
  the worker builds a plain-dict snapshot touching no Qt, and a main-thread
  QTimer drains the newest frame at 4 Hz, dropping stale frames rather than
  queueing them.
- **Throughput telemetry persisted.** `candles_per_s`, `elapsed_s`,
  `trades_per_1k_candles` and `visuals_attached` are now written to each run's
  `meta.json`. Diagnosing the GUI-vs-headless gap previously required
  hand-deriving rates from `started_at`/`finished_at` across 62 run directories.

> **Correction, recorded 2026-08-04.** This cascade was shipped with the stated
> rationale that cross-thread widget access caused the measured 29× GUI-vs-
> headless throughput gap (2.80 vs 81.32 candles/s). **That attribution was
> wrong.** The dominant cause is the 50 ms QTimer asyncio pump at `main.py:955`:
> `pump_async` drains only already-queued callbacks then stops, so every `await`
> in the replay loop parks the coroutine until the next 50 ms tick. At ~5 yield
> points per candle that is ~250 ms/candle ≈ 4 candles/s, independently
> reproduced at 251 ms/candle. The decoupling in this cascade remains correct —
> cross-thread widget access is undefined behaviour regardless — but it was not
> the throughput cause.
