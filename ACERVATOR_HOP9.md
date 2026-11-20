# ACERVATOR HOP9 — orientation

Reference. This page carries current state and an index, for a session that has
lost its context or is starting on a new machine. Not a history.

Written 2026-11-20 against `a055b393`. **Every claim here names one command that
checks it. Run the command; do not trust the sentence.**

```bash
python -m tools.hop_check
```

Exit 1 means rewrite what moved; the threshold is 15 commits. **Rewrite what
moved. Never append.** HOP9 is the current handoff. HOP2 to HOP8 are archives and
none of them binds.

---

## HOW THE LAST SESSION ENDED

The session that wrote this was still running. The 12 pull requests since
`a4392bb9` are #1784, #1787, #1788 and #1790 to #1798: one on
#1633, one on #1786, three on #1622 and seven on #1789. #1786 and #1789 are
closed.

```bash
git log --oneline --first-parent a4392bb9..a055b393   # the 12 pull requests
gh pr view 1798 --json state --jq .state              # MERGED, and the same for the other 11
gh issue view 1633 --comments                         # each record, result and close, newest last
gh issue view 1622 --comments                         # the wire rulings and the units that built them
gh release list                                       # what is published
gh pr list --state open                               # what is still landing
```

- **Experiment 4 on #1633 runs as a one-task calibration loop.** Comment
  7029421149 sealed it. Task_14_Config_Dump left both arms before any result was
  read (comment 7030292555). The batch stopped after 14 counted pairs: the
  feedback alone removed the fault in 6, and the fault survived both arms in 8.
  Comment 7030709520 records those scores and turns the batch into the loop: one
  task, both arms, scored as soon as both end, then one change.
- **Task_07_Control_Tips has run three request forms** (comments 7030835431 and
  7031025142). Under the request a user would type, both arms removed the fault.
  Comment 7031761559 holds the code each version wrote, pair by pair: the version
  with feedback ended with fewer archetype findings in 10 of 17 pairs, the same in
  5 and more in 2. Each task's W5H file and each pair's code report sit in the
  gitignored folder artifacts/referee/.
- **CODE.REACH reads a file git ignores** (#1784, comment 7025635026). Before, it
  read such a file as REACHED without reading it, so it reported nothing on any
  run of experiment 3. OCIR row C160 records the shape.
- **The wire work on the money path.** #1787 grows the Target Balance on a
  buy-back only by its gain after both fees, and comment 7030618732 closes #1786.
  On #1622, #1788 sends each wire a share of the surplus, #1791 retires the Scrum
  Fold Ratio, and #1798 makes Settings refuse a wire set past 100% (comments
  7032645599, 7035168776 and 7044828212). HIS RULINGS THAT BIND THE CODE carries
  each rule with its symbol.
- **The VWAP charts draw five-minute candles and bands, with each Scrum-Fold
  pair** (#1790, #1792 to #1795), and no tracked text or image carries a dollar
  figure read from the account (#1796, #1797). Comment 7041401558 closes #1789.

### Standing state

- **The write hook's sigil feedback is on by default** (#1777). The function
  `dev_harness/hooks/archetype_gate.py, in _sigil_feedback_off` turns it off only
  when ACERVATOR_SIGIL_FEEDBACK reads off, or when a SIGIL_FEEDBACK_OFF file sits
  in the file's folder or a folder above it.
- **The sigils hold rules of their own.** CODE.SECURE holds SECURE001 (#1779) and
  CODE.LOOP holds LOOP001 to LOOP004 (#1782), each in its module's OWN_RULES.
- **No sigil page carries a figure measured on src/** (#1770): those figures live
  in the data sets under the gitignored artifacts/sigil_runs/.
- **Every iteration has a record first:** W5H and OCIR, gated by the Truth
  Archetype with `--item`, posted, then acted on. The rule is part 6 of Skill:
  canonized-workflow (#1742). In experiment 4 each task also carries its own W5H
  file (comment 7030835431).
- **A control is measured on its failure modes, not on a sweep** of src/: inputs
  that show each known failure mode, a corrected twin and a near-miss twin each,
  and a seeded sample stratified by folder where src/ is used. Every input cites
  the failure it is grounded in. The rule is in Skill: two-sided-control (#1765,
  #1771).
- **A worktree lacks what git ignores** (Skill: ocir, row C155): run the Truth
  Archetype's T008 from the main tree, and copy CODE.SECURE's rule packs into a
  worktree with their sha256 checked.
- **Skill: ocir holds rows C156 to C160.** Watch a log by polling its line count
  with `wc -l`, never with `tail -f` (C156). Give no two PowerShell variables in
  one command names that differ only by case (C157). Search for a folder by its
  path form, the name plus its separator, with the run's own folder path as the
  control (C158). A filter on a report's verdict word accepts every word each
  producer prints (C159). A tool that picks its files through git never reads a
  gitignored input, so run its listing on the input alone first (C160).
- **Running units are watched on a clock.** A loop runs the watcher every 300
  seconds, or sooner or later when a run's time is measured, and wakes the
  referee only on a flag: STALE, SPIRAL, LONG_WAIT, NO_ADVANCE, RUNAWAY or RAM.
  The watcher sits in the session scratchpad until #1764 commits it, and #1764
  waits on him (comment 6986794671).
- **CODE.SECURE needs its two held packs** in the gitignored folder
  `dev_harness/sigils/semgrep_rule_packs/`; both trees hold them. A new clone
  fetches them with the two commands on `docs/manual/16-sigil-project/code-secure.md`,
  and until then the sigil refuses and names the missing file.

### The releases and both trees

```
releases     gh release list      # three builds, 0831, 0106 and 2042
             0.2.0-20261120.0831.g041bde6396a5, from 041bde63, 6 assets, Latest
             0.2.0-20261120.0106.g5ae2c16acea1, from 5ae2c16a, 6 assets
             0.2.0-20261119.2042.g9db41524c4b6, from 9db41524, 6 assets
main         041bde63, a merge of current at a055b393
             git describe --tags origin/main     # build-0.2.0-20261120.0831.g041bde6396a5
             git log --oneline origin/main..origin/current     # prints nothing
both trees   the same content: one on current at a055b393, one detached at 041bde63
             git diff --stat a055b393 041bde63     # prints nothing
             dist/ in each holds four pairs: 2042, 2251, 0106 and 0831; 0831 is the newest
             and holds every pull request named above
he runs      2042, the dist folder of each running Acervator process
             Get-CimInstance Win32_Process -Filter "Name LIKE 'Acervator%'"   # ExecutablePath
             2042 holds #1784 and #1787 and none of #1788 to #1798
             git merge-base --is-ancestor 00ab281b 9db41524     # exit 0
             git merge-base --is-ancestor a1294458 9db41524     # exit 1
```

- **Held for him:** the Dependabot pull requests #1738, #1739 and #1747 pass
  ci-gate (`gh pr checks <n>`), and #1739 or #1747 closes alert 82, minimatch,
  which reads open. The unruled rows of the Decisions tables on #1643 and #1622.
  Moving the Coding Archetype's own ruff call onto the step 1c selection, a
  change in dev_harness/harness/ (comment 6870001755). #1764: committing the
  watcher as a new file under tools/ needs his word, because
  `dev_harness/hooks/block_detour.py` admits a new file there only when its
  COMMISSIONED set names it. The proposed rule in comment 7030292555: the dispatch
  hook's build pattern reads a word inside quoted data, such as a dictionary key,
  as a build verb. Do not raise them as a round.

---

## FIRST FIVE MINUTES

Load every skill first, by name, and count them against the listing. A subset
picked by judgement is the narrow reading.

```bash
ls dev_harness/skills                           # 34 when written
git fetch origin
git log --oneline -1 origin/current
python -m tools.hop_check
gh issue list --state open --limit 200          # gh pages at 30 without --limit
gh pr list --state open
```

**Prove the harness discriminates, once per session.** Read the exit code
directly, never through a pipe.

```bash
python -m dev_harness.harness.coding_archetype harness_fixtures/coding_archetype/known_good.py   # exit 0
python -m dev_harness.harness.coding_archetype harness_fixtures/coding_archetype/known_bad.py    # exit 1
python -m dev_harness.harness.docs_archetype   harness_fixtures/docs_archetype/known_good.md     # exit 0
python -m dev_harness.harness.docs_archetype   harness_fixtures/docs_archetype/known_bad.md      # exit 1
```

A fresh worktree has no `node_modules`. Run `npm install --no-audit --no-fund` at
its root before any markdown or JavaScript verdict: `jscpd` and `eslint` live
there, and a missing tool reads `passed=False` with zero findings. Read
`tool_availability` on every run.

---

## PROVE YOU ARE ORIENTED

```bash
python -m tools.queue_state                      # exit 0
python -m tools.conversion_state                 # exit 0
python -m tools.comment_audit count src          # exit 0
python -m tools.check_added_comments             # exit 0, per branch
python -m dev_harness.sigils.coding_house --root .   # exit 0, the rule house has no fault
```

Four rulings, answered from `dev_harness/skills/`, before any work:

1. Who may author code, and what your own role is.
2. You get `passed=False` and believe the verdict wrong. What do you do.
3. When may you edit or delete a check.
4. Where does a defect you found outside your item go.

---

## WHAT ACERVATOR IS, AND WHO DECIDES

An accumulation trading platform: the Scrum sells the excess above a bot's dollar
target and the Fold buys it back lower, so each completed cycle ends holding more
units. It trades real money. `CLAUDE.md` and `README.md` carry the rest.

The operator decides product and specification; the session decides
implementation. Bring him outcomes in plain words, never code questions. His
standing directive: clear the open issue list except the items listed as excluded
under THE QUEUE.

His ruling of 2026-11-13: the session sets the work order across items and rows
unless he prompts otherwise. Live faults on the Trading path go first, then each
issue's own row order, and a report states the order and its ground in one line.
An order he gives wins, and his focus on #1633 is such an order.

```bash
grep -n "prompt otherwise" ~/.claude/projects/*/memory/feedback_sequencing_is_mine.md
```

---

## HARD SAFETY RULES

- Never open, read, copy or commit anything under `~/.acervator/`: the credentials
  file, the state file, any vault. Never write under `~/.acervator/` or
  `~/.acervator_logs/`.
- Never start, stop or attach to the running application, never launch anything
  under `dist/`, never run `main.py` as the application.
- Never place, price, preview, amend or cancel an exchange order, never
  authenticate to a venue, never construct a bot against his real state.
- **The repository is public.** Never quote a live bot id, a balance, a fill or an
  asset name in any file, commit or comment. The committed manual uses labels in
  place of asset names; his venue exports name him and stay out of every tracked
  file.
- Never edit the tree he launches from; every unit takes `git worktree add`.
- No `noqa`, `nosec` or `type: ignore` to clear a finding.
- pytest runs serially, never `-n auto`. No heredocs and no `python -`: write the
  file, run `python <path>`, and commit with `git commit -F <path>`.
- No absolute or user-specific path in anything committed.
- Never edit `harness_fixtures/`. In `dev_harness/` a session may only ADD a
  hardening rule; weakening one goes to him first.
- Respect the RAM guard: a hook refuses heavy runs above 70% RAM while he trades,
  and a unit stops its own run at 70%.

---

## THE HARNESS

```bash
python -m dev_harness.harness.coding_archetype <path>    # all code
python -m dev_harness.harness.ta_archetype <path>        # any arithmetic
python -m dev_harness.harness.gui_archetype <path>       # Qt and JavaScript screens
python -m dev_harness.harness.docs_archetype <path>      # markdown
python -m dev_harness.harness.truth_archetype <path> --item <n>   # a report or a claim
```

One path per call; the archetype scans only its first argument. Report `passed`,
never a delta. Run the Truth Archetype before any public post: rule `T008` refuses a
machine path or an asset name read from the gitignored export.

**The merge gate** is GitHub CI's `ci-gate` status plus `passed=True` from the
owning archetype on every changed file. Arm a pull request with
`gh pr merge --squash --auto --delete-branch`. Check with `gh pr checks <n>`.
**Never name the local gate in a brief, never retry it, never wait on it**: two of
its lanes collect no test by his decision, and a hook refuses a brief that names
it.

**No step follows the gate.** A review workflow runs only when he asks for one. A
brief names no stand-in exchange, no drive, no sweep and no scratch test. Its
proof is the owning archetype, its known-good and known-bad pair, `ci-gate`, and a
named tool on the real program. Where those miss a fault class, the deliverable
is a proposed rule for him.

Briefs go to units through the Agent tool, where hooks refuse a brief that skips
the six questions (who, what, where, when, why, how), a reading shown to fail, the
`ci-gate` gate, a skill block of real skills, or the no-deletion clause on manual
work. `Workflow` meets the same checks through `gate_workflow_script.py`, and after a
context boundary `block_unloaded_skills.py` holds work until every skill loads. The
hooks that run sit in the Claude Code user folder; `dev_harness/hooks/` holds their
copies and `dev_harness/hooks/settings_hooks.json` their wiring. A merge that
changes `dev_harness/hooks/` reaches nothing until the referee copies the files
there; compare each with `git hash-object` against the merge commit.

---

## THE QUEUE

```bash
gh issue list --state open --limit 200          # 37 open when written
```

| To clear | Excluded, and why |
|---|---|
| #63, #319, #407, #412, #433, #665, #881, #993, #1125, #1136, #1486, #1622, #1633, #1643, #1656, #1657, #1659, #1660, #1695, #1785 | build-outs #23, #34, #55, #128, #147, #156, #300, #571; living #1440; stock window parked, #220, #571, #1120; Proof of Accumulation paused, #147, #594; his decisions, #937, #980, #1025, #1540, #1764 |

Read the body before dispatching, and grep the symbols a row names in the same
call: a row's status can be stale, and a scan that calls a row built has been
wrong far more often than right.

---

## ACTIVE ITEMS AND RESUME POINTS

- **#1633, the Coding Archetype, first, by his focus ruling.** His 2026-11-18
  refocus, verbatim: "the Coding Archetype with and without sigils attempting the
  same coding task. My goal is to measure this as scientifically as possible."
  The growth record, comment 6969215458, has four steps, and all four are built:
  step 1 in #1745, #1748, #1750, #1753 and #1754; step 2 in #1760; step 3 in
  #1762, #1766 and #1782; step 4 in #1767 and #1777. Experiment 3 has ended, and
  experiment 4 runs as the loop above. **Next:** the loop's next task, with its
  own iteration record first, by part 6 of Skill: canonized-workflow. Left, by
  comment 7030709520: the 8 tasks whose fault survived both arms, of which
  Task_07_Control_Tips has run, and the 7 counted tasks not yet run. **His alpha gate, 2026-11-19:** the comparison on a real
  Issue unit, with sigils against without, waits until the referee judges the
  sigil-based Coding Archetype ready for alpha. Until then the one-task loop runs,
  with organic requests.

```bash
gh issue view 1633 --comments      # loop 7030709520; Task_07 7030835431, 7031025142; code reports 7031761559
grep -n "ready for alpha" ~/.claude/projects/*/memory/project_sigil_alpha_gate.md
```

- **#1622, the wire rows, on his rulings of 2026-11-19** (comments 7028680362 to
  7029270222). #1787, #1788, #1791 and #1798 are built. The body's spine still
  describes a wire's share through the Scrum Fold Ratio and the growth cap's room,
  which #1788 and #1791 removed, so read the comments from 7028680362 for the
  wire model. Next, in this order:

```
the arriving-credit limit   a credit fills a tranche only up to full compounding growth at its
                            minimum entry price; today it spreads evenly, with no limit
                            src/trading/scrumming/wire_routing.py, in WireRoutingMixin.apply_wire_income
                            comments 7028937235 and 7029003659
the Extractor's stack share the arrival spread across the parent's stack tranches, unbuilt
                            src/trading/scrumming_bot.py, in ScrummingBot.apply_extractor_tranche_return
                            comment 7029071374
row 29, the outflow cap     with no cap inputs, Paper and the Simulator cap each wire at 100%
                            divided by the wire count, and Live leaves each at 100%
                            src/paper/paper_wire.py, in PaperWireManager.distribute_sale_surplus
                            src/simulator/sim_wire.py, in SimWireManager.distribute_sale_surplus
                            src/trading/scrumming/wire_routing.py, in WireRoutingMixin._route_scrum_proceeds_via_wires
the React swarm page        a dragged wire is drawn and never saved, and Connect stops at its
                            own confirm question, comment 7044828212
```

  The body's other unbuilt rows, in row order: 14, 18, 21, 22, 24 to 27, 30, 31,
  33, 35, 36, 38 and 39. Rows 28, 32, 34 and 37 wait on his answers in the
  Decisions table, and row 20 is partial (`gh issue view 1622`, the Status
  column).

- **#1656 and #1695: every row is built** and is in the build he runs, so read
  his logs, read only, for each row's lines:

```
#1695 rows 1 and 3   no Max Cartridge fold, fold rebuy or hedge top-up line names CCXTQueueFullError
#1695 row 2          a buy the venue cannot pay for writes "order not sent", the free balance and the cost
#1656 row 1          a breaker trip inside a send
#1656 row 2          a send with no answer keeps its id until the order comes back
#1656 row 3          FIRST BUY READ CLEARED
#1656 row 4          FIRST BUY MADE or FIRST BUY OWED
#1656 row 5          VENUE COMPARE CLEAR or its refusal
#1656 row 6          SETTINGS OPENED and SETTINGS CLOSED
#1656 row 7          BOT COMMAND, and LIVE PAGE COMMAND on a React build
#1656 row 8          VENUE KEPT, VENUE REMOVED, VENUE KEPT AT CLOSE or VENUE DROPPED AT CLOSE
#1656 row 9          ORDER LOST, LOST ORDER UNMATCHED, LOST ORDER ENDED and LOST ORDER ANSWERED
                     gh issue view 1695 and gh issue view 1656, the Status column
                     git merge-base --is-ancestor efd0e18a 9db41524      # exit 0, #1656 in 2042
                     git merge-base --is-ancestor a1429717 9db41524      # exit 0, #1695 in 2042
```

- **#1785, a slow venue link, waits.** His words in comment 7028058664 put it for
  later: "If we have an optimization opportunity here, we should make it an Issue
  and address it later." Its Decisions table holds two figures only he sets.
- **#1657, public text that breaks the writing rules.** Read the body before
  dispatch.
- **#1643, what the manual rewrites found.** Next, in order: row 66, the breaker
  window he ruled for; his ruling in Decision 2, a hard trip cancels the bot's
  resting orders; row 106, a cartridge obeys the Position Ceiling and Max Target
  Growth. Then the remaining unbuilt rows.
- **#412, the manual.** Row 12 is in progress, one page at a time: his sentences
  verbatim with one cited "Now:" line each, every dated reading gone. The issue
  lists the pages done and the pages left. Row 14, the one PDF rebuild, waits on
  rows 12 and 13. Row 16 carries his correction: one slide per asset, in
  `tools/build_product_manual.py, in write_evidence_deck`. The PDF builder is
  `tools/build_product_manual.py`; pass the gitignored export folder with
  `--evidence-dir`.
- **#433, novel concepts.** Concept 1, hunger and satiety, is built with a per-bot
  switch, off by default. Concepts 2 to 4 are unbuilt. Paper and the Simulator run
  none of the favours and no hunger: a gap against his one-trading-logic rule,
  recorded on the issue.
- **#665, the settings audit.** The open rows sit under "Units raised by the work
  itself", and none waits on him. Verify each against the current tree before any
  fix.
- The rest of the queue: read each body.

---

## HIS RULINGS THAT BIND THE CODE

```
three agreeing indicators   every favour, hunger, the plain floor, a landing strip,
                            the first entry and detonation
                            src/trading/ta_engine.py, in three_agree and three_indicator_floor
the opposing distance       never under two fees, on the venue's reported fee when higher
                            src/trading/otd_math.py, in distance_settings
the distribution sale       keeps the distance from the buy price of the fold that bought it
                            src/trading/scrumming/distribution.py
a buy-back's growth         its gain after both fees, never below zero, on every buy-back path
                            src/trading/scrumming/sizing.py, in gain_after_fees_usd, #1786
a wire's surplus            what a sale leaves past the dollars that re-zero its units at the
                            Minimum Opposing Trade Distance, buy fee included; the buy-back
                            distance carries no wire term
                            src/trading/scrumming/sizing.py, in sale_surplus_usd,
                            #1622 comments 7028937235 and 7029165701
wire shares                 each wire takes its share of the surplus; a bot's set never passes
                            100% and no share sits below zero
                            src/trading/smart_wire.py, in wire_set_refusal, #1622 comment 7044828212
the Scrum Fold Ratio        retired; a sale's tranche keeps every unit it sold
                            src/trading/container/config.py, in _DEPRECATED_KWARGS,
                            #1622 comment 7029270222
wire credits                surplus, never a hedge fund; spent only inside a fold tranche,
                            capped at the maximum growth per cycle; a remainder returns
                            to the pool, src/trading/scrumming/wire_routing.py
an arriving credit          waits in its bucket until a tranche spawns and never spawns one,
                            on fold and stack tranches alike, #1622 comment 7029003659
the Extractor's return      reaches its parent through their association, never a Smart Wire
                            src/trading/container/registry.py, in find_parent_bot_for_base_currency,
                            #1622 comment 7029071374
shared cash                 a cartridge leaves other bots' reserved dollars alone,
                            #1622 row 5
hunger                      off by default, a per-bot switch and pace
                            src/trading/container/config.py, in BotConfig
a breaker                   trips only on a move inside a short window set in Settings,
                            #1643 row 66, unbuilt
a hard trip                 cancels the bot's resting orders, and after Reset the bot
                            places what it still needs, #1643 Decision 2, unbuilt
a cartridge fold            obeys the Position Ceiling and Max Target Growth,
                            #1643 Decision 9 and row 106, unbuilt
an outside program          new code may run one on a path a caller passes in; ruff S603
                            and S607 read low, the grade bandit gives B603 and B607
                            dev_harness/harness/coding_archetype.py, in RUFF_SEVERITY_OVERRIDES
the manual                  his sentences verbatim; one cited "Now:" line; no dated reading
issue comments              every claim about the code cites "path, in symbol"
a coding rule               runs only where the input's file type, constructs and imports
                            select it; the house says "can run" for its count, #1633 step 1c
                            dev_harness/sigils/coding_partition.py, in selection
```

---

## OPEN DEFECTS

Repaired in the build he runs; each waits on his logs to show it:

```
a Max Cartridge fold, fold rebuy or hedge top-up refused on a full call queue
    src/exchange/ccxt_connector.py, in queue_cap_waived; #1695 rows 1 and 3
a buy sent for quote the venue does not hold
    src/exchange/ccxt_connector.py, in CCXTConnector._refuse_unheld_quote; #1695 row 2
a lost order booked twice when the venue answers after an audit took its units in
    src/trading/scrumming/reconciliation.py, in ReconciliationEngineMixin._return_audit_adoption; #1656 row 9
a wallet read older than the last fill
    src/trading/bot_container.py, in BotContainer._invalidate_symbol_balances; #1622 row 10
a refused send held as lost, so a same-size withdrawal books a sale that never happened
    src/exchange/ccxt_connector.py, in order_stayed_home; #1622 row 19
```

Open on `current`:

- A Gemini lost order that filled is still not booked; #1622 row 20 is partial
  (`gh issue view 1622`, row 20's Status).
- The React Bot Swarm page's layer buttons do nothing when pressed
  (`src/gui/web/bot_visualizer.js`, in `LayerHeader`); recorded on #23. Read at
  1400 by 900, the same page draws a dragged wire and never saves it, and its
  locust grid starts below the window (#1622, comment 7044828212).
- Paper and the Simulator judge the vote at the plain floor
  (`src/simulator/back_test.py`, in `ta_direction`); recorded on #433.
- The Extractor does not read the three-indicator line, and takes it in its
  release work: `grep -c three_agree src/trading/extractor_bot.py` reads 0.
- The New User Procedure's step 15 picture still shows the retired Scrum Fold
  Ratio row, as its page states. The picture's last commit, 542a615f, comes before
  #1791:

```bash
git log -1 --format=%h -- docs/new-user-procedure/figures/step-15-what-a-cycle-keeps.png   # 542a615f
```

- The prompt router's own row lists sit 2 of 11 entries short of the catalogue
  index of Skill: ocir. #1784 added C160 to the skill and left the router's
  `_CATALOGUE_RULES` as it was. An empty line means the two match:

```bash
python -c "from dev_harness.hooks.prompt_router import _build_catalogue_gaps; print(_build_catalogue_gaps())"
```

---

## DISCIPLINES LEARNED EXPENSIVELY

- `gh issue list` returns 30 rows unless given `--limit`.
- `python BUILD.py` ends on a prompt; a non-interactive run raises `EOFError` after
  writing every build. Read `dist/`, never the exit code.
- A local React build carries Electron only when that tree's `desktop/` holds it:
  run `npm ci --no-audit --no-fund` there, then, from the root,
  `node desktop/node_modules/electron/install.js`.
  The React window is web pages inside Qt, so a published React build opens
  without Electron. Never report the size gap as a fault.
- Nothing run may reach outside its process. `webbrowser.open` and
  `winsound.PlaySound` escape a redirected home and refused sockets.
- A manual brief carries the no-deletion clause, and names unit-written readings,
  never his text, as what may go.
- One branch update at a time, and at most three open unit branches.
- The session transcript grows all session; it passed 695 MB on 2026-11-14. Code
  that reads it reads from the end, through `dev_harness/hooks/transcript_tail.py`.
- A RAM rise outside a unit's own process tree is named before the unit runs
  again: record the largest processes on the machine, with their parents and
  command lines, at every sample.
- An absolute scratchpad path in a brief is refused as grounding outside the
  repository; name the scratch folder only.

---

## MOVING TO A NEW MACHINE

The repository carries the code, the harness, the skills under `dev_harness/skills/`
and this file. These live outside it and move by hand:

```
Claude Code user folder        hooks/, skills/, settings.json (wires the hooks)
                               projects/<project folder>/memory/ (the session memory;
                               the project folder name follows the repository path,
                               so copy the memory into the new name)
his runtime folders            ~/.acervator/ and ~/.acervator_logs/ (he copies them;
                               a session never reads the state or the credentials)
his venue exports              artifacts/evidence-input/ inside each tree (gitignored)
his product documentation      the folder holding his evidence presentation and
                               newest exports
GitHub                         gh auth login, and the git identity
```

Then, in each tree he launches from:

```bash
pip install -e .                                  # Python 3.14; groups in pyproject.toml
npm install --no-audit --no-fund                  # analyzers at the root
(cd desktop && npm ci --no-audit --no-fund) && node desktop/node_modules/electron/install.js
python BUILD.py                                   # read dist/ afterwards
python -m tools.hop_check                         # exit 0 before any work
```

---

## CITED AS ABSENT

- `dev_harness/sigils/semgrep_rule_packs/` is gitignored, because the two packs carry the registry's licence. A new clone holds no such folder until the two fetch commands on `docs/manual/16-sigil-project/code-secure.md` run.
