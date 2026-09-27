# ACERVATOR HOP8 — orientation

Reference. This page carries current state and an index, for a session that has
lost its context. Not a history. The session transcript is the archive.

Rewritten 2026-09-10 against `a0ba4975`. **Every claim here names one command
that checks it. Run the command; do not trust the sentence.** Every command
below ran in a worktree off `origin/current` on that date.

**Protocol.** Rewrite a section that drifted. Never append. Three earlier
handoffs grew past 100 KB and stopped being read, and one draft swallowed the
standing queue and became the thing it replaced.

```bash
python -m tools.hop_check
```

It reports commits landed since this file last changed, cited paths that are
gone, and cited commits that do not resolve. Exit 1 means rewrite what moved.
The threshold is 15 commits.

All six `ACERVATOR_HOP*.md` files sit tracked at the repository root, restored by
`4520c840`. HOP8 is the current one. The other five are archives and none of
them binds.

---

## FOUR CHANGES THAT RETIRE EVERY OLDER HANDOFF

### 1. The Python test suite left the tree

`05449360`, the operator's own commit, 2026-09-06, subject: *“remove the
non-canon tests, and put the whole harness in the tree.”* 267 of the removed
tests called `read_text`, `inspect.getsource`, `ast.parse` or `open` on a `.py`
path. 72 more carried hand-maintained constant registries. `tests/` now holds
`tests/conftest.py`, one data file, two Solidity test files, and the debug
reports. **One Python file, and it is the conftest:**

```bash
git ls-files tests | grep -c '\.py$'          # 1
git ls-files tests | grep    '\.py$'          # tests/conftest.py
```

His replacement, verbatim from that commit: *“Verification is now the debugger:
the program runs, debugpy and pdb report what it does, and the archetypes own
every verdict.”*

**You do not write a test. You run a canon tool.** Load
`canonized-code-testing` and `debugging` before touching anything.

### 2. The harness sits in the tree

`dev_harness/` carries four things: `dev_harness/harness/` holds the archetypes,
`dev_harness/hooks/` holds 28 hooks plus
`dev_harness/hooks/REGISTRATIONS.md`, `dev_harness/skills/` holds 33 skills, and
`dev_harness/agents/` holds the evaluator. The skill set matches the user-level
copy exactly.

The comparison reads each pair's text, not the directory names, and strips
carriage returns from both sides first. The tracked copies are `eol=lf` and the
user-level copies are CRLF, so a raw byte comparison calls 6 of the 33 drifted
when no rule in them differs. The loop walks the tracked directory, so
`~/.claude/skills/synced` never enters it; that directory is a bucket and holds
no `SKILL.md`.

```bash
for d in dev_harness/skills/*/; do n=$(basename "$d"); \
  diff <(tr -d '\r' < "$d/SKILL.md") \
       <(tr -d '\r' < ~/.claude/skills/"$n"/SKILL.md) \
  > /dev/null || echo "$n differs"; done          # prints nothing
```

A fresh clone gets the gate. Older handoffs claim the opposite.

### 3. GitHub Actions does not run

```bash
gh workflow list --all        # CI   disabled_manually
```

`tools/local_ci.py` runs the lanes `.github/workflows/ci.yml` names, on this
machine, capped at four workers and never `auto`.

```bash
python -m tools.local_ci --lane black  --all      # VERDICT: PASSED
python -m tools.local_ci --lane flake8 --all      # VERDICT: PASSED
```

Without `--all` a lane skips when only non-functional files changed, and a skip
still prints `PASSED` with `0 lane(s) ran`. **Read the lane count, not the
word.** The `fast` and `full` lanes call pytest, which now collects from a
`tests/` tree holding one Python file.

`.github/workflows/ci.yml` still installs a `[test]` extra and names a test
module that left with `05449360`. The workflow stays disabled, so nothing acts
on it.

### 4. The Simulator came out

`e568197b`, 2026-09-07: *“remove the Simulator down to an empty tab.”* 103 files
and 63,048 lines went. The tab keeps its name, its first place on the bar and
its black ground. `src/simulator/` keeps nine modules. **#117** rebuilds it, and
every Simulator finding folds in there as a comment.

---

## FIRST FIVE MINUTES

```bash
git fetch origin
git log --oneline origin/current..origin/main     # empty on 2026-09-10
git branch -r                                    # check for unannounced work
```

Run that before starting any issue. On 2026-08-28 three fixes got built twice
for want of it.

```bash
python -m tools.hop_check                        # drift in this file
gh issue list --state open                       # 104 open on 2026-09-10
gh pr list --state open                          # what is waiting to land
```

**Prove the harness discriminates, once per session.** Both halves, exit code
read directly and never through a pipe.

```bash
python -m dev_harness.harness.coding_archetype harness_fixtures/coding_archetype/known_good.py   # exit 0
python -m dev_harness.harness.coding_archetype harness_fixtures/coding_archetype/known_bad.py    # exit 1
python -m dev_harness.harness.docs_archetype   harness_fixtures/docs_archetype/known_good.md     # exit 0
python -m dev_harness.harness.docs_archetype   harness_fixtures/docs_archetype/known_bad.md      # exit 1
```

139 is a crash and prints no summary. 143 is a timeout kill.

**A JavaScript verdict needs `eslint`, which git does not carry.** A fresh
worktree has no `node_modules`, and the archetype then fails closed with zero
findings.

```bash
python -m dev_harness.harness.coding_archetype harness_fixtures/coding_archetype/known_good.js
```

It answers `passed: false` with `tool_availability {'eslint': 'missing'}` and
zero findings.

Read `tool_availability` on every run. A tool marked `missing` did not run, and
its silence is not a pass.

---

## PROVE YOU ARE ORIENTED

Saying *“I have read HOP8”* is self-reporting, which this project refuses
everywhere else. Four measurements, each with the command you ran:

```bash
python -m tools.queue_state                      # exit 0
python -m tools.conversion_state                 # exit 0
python -m tools.comment_audit count src          # exit 0
python -m tools.check_added_comments             # exit 0, per branch
```

Four rulings, which reading cannot give you. The answers sit in
`dev_harness/skills/`:

1. Who may author code, and what your own role is.
2. You get `passed=False` and believe the verdict wrong. What do you do.
3. When may you edit or delete a check.
4. Where does a defect you found outside your item go.

---

## WHAT ACERVATOR IS

A desktop **accumulation** platform trading real money on Coinbase across
**38 live bots**.

```bash
python -c "import json,pathlib; print(json.loads((pathlib.Path.home()/'.acervator'/'bot_state.json').read_text(encoding='utf-8'))['bot_count'])"
```

It accumulates base assets by scrumming a slice of profit off intra-cycle
volatility and folding it back into base position size. Every completed
Scrum/Fold cycle ends holding more of the asset. **Not** a grid bot, a DCA bot
or a rebalancer.

**The frontend is React inside Electron.** Qt is still present while the
conversion runs. Never cite Qt as the architecture in an issue or a brief.
Acervator is a desktop application, not a browser.

The window carries ten tabs, and one constant decides the order:

```bash
grep -n 'CANONICAL_TAB_ORDER' -A 12 src/gui/main_tabs/main_window_surface.py
```

Sim, Paper, Live, Charts, Inspector, Swarm, Accumulation, History, Status,
Console. `README.md` states which of them carry live capital, and which two draw
an empty panel.

## THE OPERATOR

Anthony L. Brown, “Ekthelius the Accumulator”. Sole developer, **not a
programmer**. Blunt, high-signal, no tolerance for scaffolding dressed as
delivery.

- **He numbers the queue.** Do not renumber it, re-decompose it, or jump it.
- **Done means exactly as specified.** Two states, OPEN or SHIPPED. If OPEN, say
  what is MISSING before what is done.
- **One item at a time**, built end to end, then the next.
- **Never ask him a code question.** He decides product and spec. You decide
  implementation. A precedent in his own tree is a ruling: follow it, narrow it,
  write down why, tell him after.
- **A green gate is approval to close.** Do not ask.
- **The queue never idles.** Dispatch before replying. Run units in parallel
  when their files do not overlap.
- He mis-states colour names and points at the right widget. Build to the style
  token at the place he named, and quote the token back.
- **Everything you find is yours.** A defect you found, and a decision you could
  close from the issue or the manual, both belong to you.

## HARD SAFETY RULES

- `~/.acervator/coinbase_credentials.json` — **never open, echo or commit.**
- `~/.acervator/bot_state.json` — **read only.** *“You do not modify the fucking
  stone tablets.”* Never write, move or delete anything under `~/.acervator/`.
  `~/.acervator_logs/` is read only too.
- **Never start, stop, attach to or query the running `Acervator.exe`.** It
  trades real money and usually runs live.
- **Never place, cancel or modify an exchange order.** No authenticated exchange
  call in a unit. No real network call and no credential anywhere.
- **Never edit the tree he launches from.** A branch checkout replaces the
  working tree. Take `git worktree add` for every unit.
- Never add a `noqa`, a `nosec` or a `type: ignore` to clear a finding. Treat
  every one already there as unverified. One `# nosec B310` glossed a real
  `file:///` hole for the life of a file.
- **`-n 4` at most for pytest, never `-n auto`.** 24 workers plus a browser each
  will take his machine down while it trades.
- **No heredocs and no `python -`.** A hook refuses both. Write the file, run
  `python <path>`, and use `git commit -F <path>` for a message.
- No absolute or user-specific path in anything committed.
- **Never edit `harness_fixtures/`.** In `dev_harness/` you may ADD a hardening
  rule that prevents a measured mistake. Removing or weakening one goes to him
  first.
- No `⟦ctx …⟧` footers, ever.
- **The version is derived, never written.** `src/__init__.py` calls
  `resolve_version()` and `src/_version.py` reads the git tag. Do not type a
  version into the tree.

---

## THE HARNESS

Six archetypes author and judge. **They are the only entity permitted to write
code.** You referee. Report each one's own `passed`, never a delta.
`passed=False` is INVALID work, and you have no standing to call a finding a
false positive. **No archetype run at all is also INVALID.**

| what it owns | command |
|---|---|
| all code | `python -m dev_harness.harness.coding_archetype <path>` |
| any arithmetic | `python -m dev_harness.harness.ta_archetype <path>` |
| PySide6 and JavaScript screens | `python -m dev_harness.harness.gui_archetype <path>` |
| markdown | `python -m dev_harness.harness.docs_archetype <path>` |
| a report or a claim | `python -m dev_harness.harness.truth_archetype <path>` |
| the emitters | `python -m dev_harness.harness.watchdog_archetype <path>` |

Six rule modules sit under `dev_harness/harness/rules/`: hallucination,
scaffolding, slop, story, `numeric_guard` and `delegated_canon`.
`harness_fixtures/` holds a known-good and known-bad pair for five of the six
archetypes, plus four Solidity analyzers.

**The release gate cannot report ready.** Its three self-check fixtures point at
directories that left the tree. That is **#416**, open. Do not treat a gate
failure there as a verdict on your work.

**Do not run the whole suite or the release gate from a unit.** It loads the
machine his bots trade from. A unit runs the archetype that owns each file it
touched, plus the `black` and `flake8` lanes.

**Load these before the first edit:** `harness-law`, `ocir`,
`canonized-code-testing`, `branch-discipline`, `found-it-own-it`,
`ground-to-issue-and-manual`, `no-detours`, `reachability-first`, `truth-check`,
`hyper-refocus`. `ocir` carries over 100 catalogued checks that could not fail,
indexed by the question you are asking.

**Ground to three sources and nothing else:** the issue, the Product Manual
under `docs/manual/`, and the loaded skills. A notes file you wrote to hold
standing rules is an alternate grounding point, whatever its name. Older
handoffs pointed every dispatch at one. That is now forbidden.

**Emitters.** Every emitter enters through `emit()` in
`src/core/signal_contract.py`, produces the same `Signal`, and reaches the same
sink. The Watchdog reads that sink from outside for health and crash context.
The Console reads it for display. One format, three consumers, no IPC. Track
every emitter in `src/core/emit_contracts.py`. **No emitter means nothing can
verify the directive, and a claim about it invents the answer.**

---

## THE QUEUE

104 issues open and 107 closed on 2026-09-10. The GitHub issues are the queue.
`python -m tools.queue_state` measures his older numbered items 4 to 20 from the
code, so a stale written table cannot mislead you.

Measured order of work, from where the merges actually went since 2026-09-03.
103 pull requests merged in that window. Match `Merge pull request`, or a
branch-sync merge inflates every count:

```bash
git log --merges --since=2026-09-03 --format=%s origin/current \
  | grep -oE 'Merge pull request #[0-9]+ from Acervator-LLC/unit/[0-9]+' \
  | grep -oE 'unit/[0-9]+$' | sort | uniq -c | sort -rn
```

| merged | item |
|---|---|
| 86 | **#147** Proof of Accumulation tab |
| 72 | **#665** Phantom Bots page |
| 50 | **#117** Simulator rebuild |
| 26 | **#23** ATA-SMP |
| 18 | **#585** PoA Content |
| 17 | **#586** PoA Action |
| 15 | **#128** Qt to React conversion, surface by surface on his call |
| 11 | **#407** ATA-PMT, reversal zones from Market Inspector |
| 2 | **#19** Paper tab — the active item since 2026-09-19, see its section below |

Re-measured 2026-09-19 with the command above. The table before that date
read 36, 15, 11 and 8 for #147, #128, #407 and #117.

**Issue routing, learned the hard way twice.** Every Simulator finding folds
into **#117**. Every TestNet, PoA or **Competition** finding folds into **#147**
— `src/competition/` IS the PoA package, and that word is the trigger. Never
open a new issue for either. A finding on an unbuilt screen gets one line folded
into its owning item, never an issue of its own.

---

## #19 — THE PAPER TAB. THE ACTIVE ITEM.

The operator, 2026-09-19: a clone of the Live tab that trades real exchange
data in real time against a fake, unbounded budget opening at the fleet's
total Target Balance, receiving only, recording every event as if executed.
Issue 19 comments 5747250193, 5747250703 and 5747250806 hold the contract,
the W5H and the eight units Q1 to Q8 in build order.

**Q1 landed on branch `unit/19-q1-paper-clone`**: Live's tab code under Paper
names in both builds, under `src/gui/paper/` and `src/paper/`; the seam in
`src/gui/variant_surface.py` answers `PaperTradingTab` and
`PaperTradingTabReact`; the header strip shows on Paper and reads the paper
ledger through `header_strip_reads_paper` in
`src/gui/main_tabs/main_window_surface.py` and one branch in
`src/gui/main_window.py`; Import Live Fleet copies `bot_state.json` records
whole into `paper_fleet.json` under `PAPER_ROOT` through
`src/paper/fleet_source.py`, each written `idle`. The old hosts
`src/gui/paper_trader_tab.py` and `src/gui/react_paper_trader_tab.py` stay on
disk, loaded by nothing, until Q3. The manual section is
`docs/manual/08-tabs/paper-trader.md`, "2026-09-19 - #19 - Live's tab code
cloned under Paper names".

**Q2 landed on branch `unit/19-q2-paper-feed`**: `PaperExchange` in
`src/paper/paper_exchange.py`, the paper exchange adapter: `products`,
`ticker` with `best_bid` and `best_ask`, `candles` at the nine granularity
names with `1w` rolled from daily pages through the stone tablets' `_rollup`,
`windows`, `quote_rate`; held in `TickerEntry` and `CacheEntry` slots from
`src/exchange/data_pool.py`, paced at `PUBLIC_MIN_INTERVAL_S` from
`src/exchange/market_inspector_fetcher.py`, one `APIInteractionLog` entry per
venue call, `__getattribute__` refusing every public name outside
`READ_NAMES`. Both hosts under `src/gui/paper/` carry `apiEntryLogged` and
`_cross_api_event`, and after Import Live Fleet a `paper-feed-import` thread
runs `read_fleet` and one `feed_line` lands on the Activity Log. The manual
section is `docs/manual/08-tabs/paper-trader.md`, "2026-09-20 - #19 - The
paper exchange adapter feeds the tab". Settled against the venue itself: one
candles ask per granularity name on `BTC-USD` answered 200 with rows for all
nine, `FOUR_HOUR` at 14,400 s spacing; `src/exchange/timeframes.py` still
says eight and no `4h`, is Live's, and was not touched.

**Resume at Q3**, the runner on one worker thread per run at Live's cadence,
the tick rebuilt on `src/trading/scrumming/sizing.py` over `tape_context` and
`latch`, a scrum at `best_bid`, a fold at `best_ask`, the venue's taker fee,
the budget unbounded; comment 5747250806 row Q3 holds the acceptance. The
runner reads the tab's `exchange()`; the old hosts
`src/gui/paper_trader_tab.py` and `src/gui/react_paper_trader_tab.py` are
removed in Q3, and `src/paper/paper_run.py` is the tick Q3 rebuilds. Read the
Paper tab off the running program
with a scratch home and every socket but loopback refused before changing a
line; `main.py` sets its window floor at 1400 by 900, so the tab is reached at
that width and no narrower.

```bash
git log --oneline origin/current -- src/gui/paper src/paper | head -5
```

## #147 — PROOF OF ACCUMULATION. START HERE.

**The issue body is the specification.** It runs in seven parts: the body, then
six comments. Nothing sits in a separate file.

```bash
gh issue view 147                  # the body: 22 units, the choices, what he owes
gh issue view 147 --comments       # parts 2 to 7, and the design provenance
```

The body lists twenty-two units, ordered so no unit depends on a later one. His
later rulings added more past that number. Which ones landed:

```bash
git log --merges --format=%s origin/current \
  | grep -oE 'Merge pull request #[0-9]+ from Acervator-LLC/unit/147-u[0-9]+' \
  | grep -oE 'u[0-9]+$' | sort -u
```

**Run it rather than reading a list; units land hourly.** Units 1 and 3 landed
under their own names, `unit/147-quintessence-ledger` and
`unit/147-solidity-audit-toolchain`, so the command misses those two. On
2026-09-10 the unlanded units were 13, 14 and 19.

Two units stay blocked on him: 18 waits on whether an outside firm reviews the
contracts before mainnet, and 20 waits on his art direction.

**Every unit updates the manual page in the same unit it lands**, and runs the
archetype that owns each file it touched. The page is
`docs/manual/08-tabs/proof-of-accumulation.md`.

**The Solidity side.** Four contracts sit in `contracts/`, built through npm:
`package.json` carries `solhint`, `eslint`, `html-validate`, `stylelint` and the
OpenZeppelin and Chainlink libraries. `foundry.toml`, `.solhint.json` and
`.solhintignore` configure them. Two Foundry tests live at
`tests/contracts/QuintessenceConservation.t.sol` and
`tests/contracts/TrophyTierCaps.t.sol`. The audit record is
`docs/audits/2026-09-10_contract_audit_ethtrust_levels.md`.

---

## #128 — THE CONVERSION

He picks which surface goes next and when. Do not open a conversion unit
uninvited. Keep the measurement current so he chooses from real numbers.

```bash
python -m tools.conversion_state
```

```
75   renderer modules the page loads
65   bridge methods a module speaks
85   src/gui .py importing PySide6
77     paired, a React module serves it
 5     not a screen, Qt plumbing
 3     UNPAIRED, the work that is left
```

**What that proves.** It walks the chain the running frontend uses: a surface
publishes a bridge method, `src/core/desktop_bridge.py` registers it, a module
under `src/gui/web` speaks it, and the renderer manifest loads that module. No
`.py` name gets compared with a `.js` name. A pair means React can draw the
screen. It does not prove the Qt one retired, so confirm at the surface. The
control is `bot_visualizer`, which must report `paired`.

The three unpaired files are `src/gui/history_qt_table.py`,
`src/gui/main_tabs/main_tab_bar.py` and `src/gui/main_tabs/empty_tabs.py`. The
five that can never convert are the three desktop shells, the package marker
`src/gui/widgets/__init__.py`, and `src/gui/qt_safe_events.py`, which defines no
class. Counting those five as outstanding is what made this item look
impossible to finish.

**#128's own comments carry the per-surface protocol** — a seven-step table
naming the React module, whether it calls React, the bridge method, the manifest
line, the Electron registration, the build, and whether it RENDERS. Follow the
shape of the last one he accepted.

**Two conditions gate Qt's removal, not one.** Operator, 2026-08-31: preserve Qt
until React and Electron **run** AND the operational logs **verify** it. A
screen that draws and emits nothing is a picture. **Never delete a widget before
its replacement runs.** Removing the remaining PySide6 imports is **#157**.

**The in-tree React pattern.** React is vendored at `src/gui/web/vendor/`. Plain
JavaScript calling `React.createElement`. **No bundler, no JSX, no build step**
for the renderer. `connect-src` is `'none'`. The bridge is
`window.acervator.call(method, params)`. The Electron shell is `desktop/main.js`
with `desktop/preload.js`, and it spawns `src/core/desktop_bridge.py` as a child
process. Node and npm ARE installed on this machine; the renderer still does not
use them.

**The manifest is generated, never hand-edited.** Never hand-edit
`desktop/renderer/index.html`.

```bash
python -m tools.sync_renderer_modules      # exit 0, writes desktop/renderer/module_manifest.js
```

**Two traps, both measured.**

- **Colour.** Qt reads an 8-digit hex as `#AARRGGBB`; CSS reads it as
  `#RRGGBBAA`. `rgba()` carries the same trap — Qt takes a 0 to 255 alpha byte
  and a browser takes a 0 to 1 fraction, so `rgba(0,255,204,51)` paints opaque
  in Chromium. `src/gui/color_alpha.py` holds the one `rgba` helper.
- **Timers.** Chromium throttles `setTimeout` and `setInterval` unpredictably
  under an offscreen web view. **Expose and read the delay value**, never the
  wall clock.

---

## #319 — THE COMMENT SWEEP

His framing: *“I would wager that having all of this mess in these files is
contributing to drift when you re-read the nonsense.”*

The rule it enforces lives in `.claude/rules/code-comments.md`: default to no
comment, and where one is warranted, **one sentence, twenty words or fewer,
naming something in the block it sits on.** The sweep changes no executable
line, so it runs between other units. His bucket order is `src/`, then
`dev_harness/`, then `docs/`, then `docs-archive/`. `tests/` left that order with
`05449360`. The `tools/` count below sits outside his order, for reference.

```bash
python -m tools.comment_audit count src            # 370 files
python -m tools.comment_audit count dev_harness    #  49 files
python -m tools.comment_audit count tools          #  27 files
```

Read on 2026-09-10. **The tool is the authority, not this table** — these move
with every merge.

| target | own-line | trailing | blocks of 3+ | outside code |
|---|---|---|---|---|
| `src/` | 3,365 | 1,131 | 33 | 25 |
| `dev_harness/` | 454 | 87 | 29 | 12 |
| `tools/` | 176 | 35 | 4 | 1 |

`python -m tools.comment_audit prove before.py after.py` proves a cleanup
changed no code: it parses both versions, replaces every docstring with a
stand-in, and compares the trees, so a line ending or a docstring edit cannot
read as a code change.

`python -m tools.check_added_comments` judges every comment a branch adds
against the repository's comment rule. Run it on your branch before the PR.

**Cite a symbol, never a line number.** The sweep shrinks files, so every line
citation rots. Check the file name too: a citation can be in bounds and name the
wrong file.

**An untrue comment is a DEFECT.** The shapes measured here: a docstring calling
live code dead; a stated direction reversed; a named caller that never calls; a
diagram of behaviour the code does not perform; a fabricated figure; an invented
citation of a file or a check that does not exist; a function named `verify` or
`validate` that returns a constant; a suppression sitting on a line the linter
does not report.

**Comment wrong and code right, fix the comment. Code wrong, fix it in the same
unit**, with a check that fails without the fix. The three exceptions are
harness files, an unbuilt screen, and a fix that would change what a number he
reads means.

---

## OPEN DEFECTS

**The issues are the record.** Read them; do not re-derive them.

```bash
gh issue list --state open
gh issue view <n>
```

The ones a cold session meets first:

| # | what it reports |
|---|---|
| 416 | the release gate cannot report ready; three fixture paths left the tree |
| 362 / 363 | all exchange fetching stops and only a restart recovers it, plus a shutdown fault; almost certainly one fault |
| 367 | a spawned tranche does not match the scrum that spawned it |
| 150 / 427 | capital reservation refuses every request, and fails open on a pre-check exception |
| 410 | a full `gc.collect()` every five seconds on the GUI thread |
| 538 | VolumeGuard is wired to every live bot and cannot fire |
| 541 | the hallucination rule does not read this file's own absence declaration |

**#362, diagnosed to the timestamp.** Fetching ran about 230 calls a minute,
then stopped dead for six minutes. The GUI thread never blocked: the feed logged
every two seconds through the whole silence and the state save fired mid-way.
**Qt timers survived; the asyncio work that issues exchange calls did not.** Any
fix aimed at a blocked GUI thread aims at the wrong target.

**#367 has its data waiting.** Establish whether the delta is constant,
proportional or scattered **before** naming a cause, and check value and
distance separately. Never recalibrate a constant to close a gap — find the
helper that produces the wrong number and land its coupled consumers in the same
change. **The exchange is the authority.** Internal ledgers reconcile to the
venue and never override it.

---

## DISCIPLINES LEARNED EXPENSIVELY

**Measure, do not recall.** A written queue table said an item was open. The
code said it shipped four days earlier.

**A zero is a claim about the instrument, not about the world.** A measurement
is not a finding until its instrument has a positive control.

**Ask history, not the working tree.** `git ls-files` returning nothing says
nothing about whether a file ever existed. For *“was this ever here”*, run
`git log --all --diff-filter=D -- <path>` and read the commit message. That
mistake cost a false claim in a shipped guide, then cost it again eight days
later.

**A brief cannot outrank a loaded skill.** Seven agents in one session ran the
full gate against an explicit prohibition, each correctly citing a permanent
rule. The brief was wrong, not them. If a permanent rule is stale, edit the rule
and quote the commit that superseded it.

**A uniform answer across a tree is the instrument.** A miscalled scanner
reported two emitters for all 164 files, because the function returns a pair and
`len()` read the pair.

**Vertical, not horizontal.** One thing end to end, then the next. Only shared
infrastructure with no consumer yet is legitimately horizontal.

**Two-sided or it did not happen.** Red before, green after, both quoted. Never
reconstruct a before-state by reversing your own edit; read it from git.

**A fix must reach the read path.** Trace it to the exact field the consumer
reads. Freshening an adjacent cache fixes nothing.

**Indicator formulae are published.** 21 indicators live in
`src/trading/indicators/`, beside `__init__`, `helpers` and `types`. Where the
code departs from the published math, the code is wrong. Each indicator computes
its own math and never blends another's output. Deletion is not a repair option.

**Recurrence is a skill defect.** The second time an error class appears, fix the
skill in the same turn. Narrating a recurrence reads as tolerating it.

**`nan` is truthy**, so `float(x) or 0.0` misses it, and every comparison
against `nan` is False. `type(inf) is float` is True, and
`math.isfinite(10**400)` raises.

**Your own output is the context risk.** One session died on *“prompt is too
long”* at 26 MB, about 70% of it assistant-generated, with 332 agent dispatches
averaging 7.8 KB of retyped brief. A second block was one pasted CSV of
1,113,493 bytes, larger than the whole context window. Send a path, never the
content. Read with `grep` and `sed -n`, not whole-file reads. Fewer, larger
units.

---

## WHERE THE DEPTH LIVES

| what | where |
|---|---|
| the law, 33 skills | `dev_harness/skills/`, mirrored at `~/.claude/skills/` |
| the blocking hooks | `dev_harness/hooks/`, declared in `dev_harness/hooks/REGISTRATIONS.md` |
| the three auto-loaded rules | `.claude/rules/`, loaded with `CLAUDE.md` |
| the Product Manual | `docs/manual/`, rendered by `tools/build_product_manual.py` |
| this protocol, in the manual | `docs/manual/11-hop-protocol-and-rules-registry.md` |
| debug evidence, one file per run | `tests/debug_reports/` |
| engineering notes and audits | `docs/engineering-notes/`, `docs/audits/` |
| calibration fixtures | `harness_fixtures/` |
| the contracts | `contracts/`, with `foundry.toml` |
| every decision verbatim | the session transcripts, grep-able JSONL |

**Search the transcript rather than trusting a summary, including this one.**

---

## SESSION OPENING PROTOCOL

1. `git fetch origin`. Check `origin/current..origin/main` and the remote branch
   list for work already pushed.
2. `python -m tools.hop_check`. Clean before you claim orientation.
3. Prove the harness discriminates: both fixture halves, exit codes read
   directly.
4. Read the queue. Work **one** item, fully, end to end.
5. `git worktree add` for every unit. His tree never leaves `current`.
6. Run the owning archetype on every file you touched, plus the `black` and
   `flake8` lanes. Report `passed` as returned.
7. Update the manual page in the same unit.
8. Open the PR. Report only what you measured.

## KEEPING THIS FILE USEFUL

- **Rewrite, never append.**
- **Anything measurable belongs in a tool, not in prose.**
- **Every claim here needs one command that checks it.** If you cannot name the
  command, the claim does not belong.
- Run `python -m tools.hop_check` at the start and the end of every session.

## CITED AS ABSENT

This path appears above **because it left the tree**, and that absence is the fact
being carried. The drift check excuses a path under this heading, and only
under it. Do not delete the citation, and do not recreate the file.

- `docs/audits/2026-07-24_coding_archetype_multi_agent_test/fixtures/known_good.py`
  — the release gate's own self-check fixture, which is why the gate cannot
  report ready. The issue is #416.
- `src/gui/main_tabs/main_tab_bar.py` — named in the #128 section as one of
  the three unpaired files; commit `59c59d59` removed it when the tab bar was
  unpainted, so the unpaired count there is one lower than written.

The docs archetype still reports that path as a medium hallucination finding,
because its rule does not read this heading. That gap is **#541**, open. The
finding is expected and the citation stays.
