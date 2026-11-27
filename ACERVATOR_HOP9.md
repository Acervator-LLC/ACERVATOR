# ACERVATOR HOP9 — orientation

Reference. This page carries current state and an index, for a session that has
lost its context or is starting on a new machine. Not a history.

Written 2026-11-21 against `84ab232e`. **Every claim here names one command that
checks it. Run the command; do not trust the sentence.**

```bash
python -m tools.hop_check
```

Exit 1 means rewrite what moved; the threshold is 15 commits. **Rewrite what
moved. Never append.** HOP9 is the current handoff. HOP2 to HOP8 are archives and
none of them binds.

---

## HOW THE LAST SESSION ENDED

The session that wrote this was still running. The 23 pull requests since
`a5e44099` are #1800 to #1822: fifteen on #1633, four on #1789, and one each on
#1622, #53, #1660 and #319. Five of the six issues are open. #1633 closed on
2026-11-23, as not planned.

```bash
git log --oneline --first-parent a5e44099..84ab232e   # the 23 pull requests
gh pr view 1822 --json state --jq .state              # MERGED, and the same for the other 22
gh issue view 1633 --json state,stateReason           # CLOSED, NOT_PLANNED
gh api repos/Acervator-LLC/ACERVATOR/issues/comments/7110762631 --jq .body   # the closure
gh issue view 1789 --comments                         # his chart rulings and the units that built them
gh release list                                       # what is published
gh pr list --state open                               # what is still landing
```

- **#1633 closed on 2026-11-23, as not planned.** His words:
  "Okay, that is fine.  We are done with 1633.  It is not showing enough promise to continue."
  Then:
  "Science must be allowed to win even if you do not like the results."
  The last measurement is comment 7094741655, and the closure is comment
  7110762631. Nothing under the restarted design was built, and no work on it
  resumes. `docs/manual/16-sigil-project.md` states the closure. The 334
  comments purged on 2026-11-21 stay in the gitignored folder
  `artifacts/referee/1633_archive/`.
- **#1813** declares `__all__` as a plain list in the Console and Status Qt tabs
  (#1660 row 5), and **#1814** makes the Activity Log surface obey the comment
  rule (#319).
- **The VWAP charts (#1789).** #1802 draws each Scrum-Fold cycle on five-minute
  candles and removes the weekly charts. #1804 makes the live-evidence market
  chart show the 33 bases its text names. #1805 puts each base's charts on one
  page and takes its pairs from order times and a 5% MOTD. #1807 pairs
  neighbouring runs only and draws no line between a pair. The PDF and both
  presentations carry each change, and the issue body states the charts as built.
- **#1801** saves a dragged or connected wire on the React Bot Swarm page
  (#1622). **#1803** fits an indicator cell's mouse-over text and the no-keys text
  to twenty words (#53). **#1800** lists the newest OCIR row under both prompt
  router sections that carry it.

### Standing state

- **The write hook's sigil feedback is off and removed.** The write hook,
  `dev_harness/hooks/archetype_gate.py`, runs no coding sigil, before a write or
  after it. His ruling of 2026-11-23:
  "Coding Sigils should not be active at all since they were supposed to be part of a separate archetype version that was being tested and not yet deployed."
  The nine stay under `dev_harness/sigils/` as the record of that version.
- **The sigils hold rules of their own.** CODE.SECURE holds SECURE001 (#1779) and
  CODE.LOOP holds LOOP001 to LOOP004 (#1782), each in its module's OWN_RULES.
- **A sigil run by hand gives one flag**, defined in `dev_harness/sigils/core.py,
  in FLAGS`. HOLD prints only for application source (`src`, `desktop` and
  `main.py`), FIX for a fault anywhere else, OPTIMIZE for a named optimization
  rule.
- **The hook that runs is the copy in the Claude Code user folder.** After a
  merge that changes `dev_harness/hooks/archetype_gate.py`, copy it there and
  compare `git hash-object` with the merge's blob.
- **No sigil page carries a figure measured on src/** (#1770): those figures live
  in the data sets under the gitignored artifacts/sigil_runs/.
- **Every iteration has a record first:** W5H and OCIR, gated by the Truth
  Archetype with `--item`, posted, then acted on. The rule is part 6 of Skill:
  canonized-workflow (#1742). Each experiment task also carries its own W5H
  file.
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
releases     gh release list      # three builds, 0529, 1408 and 1107
             0.2.0-20261121.0529.g997d995fd035, from 997d995f, Latest
             0.2.0-20261120.1408.gefb4a844c30d, from efb4a844
             0.2.0-20261120.1107.gd2ebd3849477, from d2ebd384
main         997d995f, a merge of current at 9d07671a, #1813
             git describe --tags origin/main     # build-0.2.0-20261121.0529.g997d995fd035
             #1814 after it changes comments only, and #1816 changes only the write hook
             and the manual, which no spec collects, so no build follows either
             python -m tools.comment_audit prove <the file at 9d07671a> src/gui/main_tabs/status_log_surface.py   # IDENTICAL
             git diff --stat 997d995f 1d137dee -- src desktop main.py tools Acervator_win.spec   # status_log_surface.py only
both trees   both on current at 1d137dee
             dist/ in each holds three pairs, 1107, 1408 and 0529, built from 997d995f
he runs      1107, the dist folder of each running Acervator process
             Get-CimInstance Win32_Process -Filter "Name LIKE 'Acervator%'"   # ExecutablePath
             1107 holds #1801 and none of #1802 to #1814; 0529 holds every pull request to #1813
             git merge-base --is-ancestor afaa030c d2ebd384     # exit 0
             git merge-base --is-ancestor 51a8a77f d2ebd384     # exit 1
```

- **Held for him:** the Dependabot pull requests #1738, #1739 and #1747 pass
  ci-gate (`gh pr checks <n>`), and #1739 or #1747 closes alert 82, minimatch,
  which reads open. The unruled rows of the Decisions tables on #1643, #1622 and
  #1789. A reading script the #1801 unit started at 10:35 still runs; the unit
  was refused permission to stop it, so it waits on his word and no one else
  stops it. Find it by its command line, which names the scratch file
  `react_swarm_saves_wires_readings.py`.
  #1764: committing the watcher as a new file under tools/ needs his word,
  because `dev_harness/hooks/block_detour.py` admits a new file there only when
  its COMMISSIONED set names it. A proposed rule: the dispatch hook's build
  pattern reads a word inside quoted data, such as a dictionary key, as a build
  verb. Do not raise them as a round.

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
An order he gives wins. His focus on #1633 ended when he closed it on
2026-11-23.

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
gh issue list --state open --limit 200          # 39 open when written
```

| To clear | Excluded, and why |
|---|---|
| #53, #63, #319, #407, #412, #433, #665, #881, #993, #1125, #1136, #1486, #1622, #1643, #1656, #1657, #1659, #1660, #1695, #1785, #1789 | build-outs #23, #34, #55, #128, #147, #156, #300, #571; living #1440; stock window parked, #220, #571, #1120; Proof of Accumulation paused, #147, #594; his decisions, #937, #980, #1025, #1540, #1764 |

Read the body before dispatching, and grep the symbols a row names in the same
call: a row's status can be stale, and a scan that calls a row built has been
wrong far more often than right.

---

## ACTIVE ITEMS AND RESUME POINTS

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
```

  The body's other unbuilt rows, in row order: 14, 18, 21, 22, 24 to 27, 30, 31,
  33, 35, 36, 38 and 39. Rows 28, 32, 34 and 37 wait on his answers in the
  Decisions table, and row 20 is partial (`gh issue view 1622`, the Status
  column).

- **#1656 and #1695: every row is built** and is in the build he runs. His logs
  show each row's lines; read them, read only, once he says so in this session:

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

- **#1789, the VWAP charts, waits on his review** of the pages and both
  presentations. Each base's page draws no cycle panel. It counts the base's
  market cycles from three alternating touches of its five-minute band and
  states the count beside its pair counts. Each pair's gain sits on a stem split
  into captured and preserved, and each Scrum and Fold is an 18 point down or up
  triangle on the window chart
  (`tools/build_product_manual.py, in market_cycle_count` and `_draw_orders`). The body's Decisions row holds the one reading only he can
  settle: his bound on the pair count against the MOTD pairing.
- **#53, the mouse-over texts.** #1803 is in 1408, and he runs 1107. Once he runs
  1408 and says so, count the console log's twenty-word refusals, read only, over
  a window as long as the one in comment 7050551568.
- **#1785, a venue that answers slowly. Row 1 is built.** One call's 25 s starts
  when the worker starts it, a read waits up to `READ_TURN_WAIT_SEC` for its turn,
  and a stuck call's worker is replaced at that limit: the reads behind it move to
  the fresh worker and an order is dropped unsent
  (`src/exchange/ccxt_connector.py, in CCXTConnector._replace_stuck_worker`). Row 8
  is built: the shared price read asks Coinbase for the markets the slots hold, and
  for every market once 15 minutes have passed, for the 24 hour volumes
  (`src/exchange/ccxt_connector.py, in CCXTConnector._named_ticker_params`). Row 10
  is built: the pairs scout asks Coinbase for the pairs its rows asked for, in a free
  place, and rests after each reading
  (`src/exchange/market_pairs_scout.py, in MarketPairsScout._read`). Row 9 is built: a
  window tick cancels no venue read, and each kind has one on its way and one waiting
  (`src/gui/read_slot.py, in ReadSlot.ask`). Row 4 is
  built: no order starts on a price or a rate older than `price_age_limit_s`, counted
  from the venue's answer, and Self-Destruct and the expiry close alone go at any age
  (`src/trading/bot_container.py, in BotContainer.order_refusal`). Its control is the
  Price Age Limit row of Settings, Trading, 10 to 60 seconds, in force at Save
  (`src/core/price_age.py, in limit_range_s`). Rows 3 and 7 are
  built, row 7 in its price, balance and candle parts: each exchange has its own
  refresher, whose rest follows the seconds its reads held the worker and doubles
  behind a throttled or lost answer (`src/exchange/data_pool.py, in SharedReads.rest_s`),
  and a bot waits for that read, 60 s at most (`in SharedReads.awaited`). Row 2
  is built: an order, a cancel and each read of an order's step go ahead of every
  other read on the worker, and the limit of eight counts the other reads alone
  (`src/exchange/ccxt_connector.py, in SyncCall.to_venue`). The body's build order
  names the rest: rows 5 and 6.
  His rule for every row is in comment 7141240463. How the fleet behaves on his
  link waits on his next run.
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
- **#1823, SPENDABLE reads the exchange's cash.** SPENDABLE now adds the cash each
  exchange's own balance answer reports, available plus held, in USD and USDC,
  from the shared balance cache, and its mouse-over names each exchange's figure
  (`src/trading/container/aggregation.py, in exchange_cash`). He reads it against
  each exchange's own Cash screen after the next build.
- **#1836, every buy opens its Stack ladder. Rows 1 and 2 are built.** On a
  Stack Mode bot every filled buy ladders the units it bought, the first buy, a
  hedge, a Manual Fire and a cartridge buy among them, and a buy that opens none
  writes one bot log line naming why
  (`src/trading/scrumming_bot.py, in ScrummingBot._spawn_stack_from_fold`). Row 3
  waits on his yes to a read of his logs and saved state; then rows 4 and 5, then
  6 to 8 with the Settings control of row 8, as the body orders them.
- **#1837, the Trade Calculator. Rows 1 to 3 are built.** Each trade log line
  names its venue order and the event ids of the tranches the fill spent and
  opened, and a fold that ran the growth step carries its figures under
  `target_growth` (`src/core/emit_contracts.py, in SettledFill`). The engine grows
  the target through `src/trading/scrumming/sizing.py, in target_growth_applied`
  alone. Next, in the body's build order: row 4, then row 5, then rows 6 to 8.
  Row 9 waits on his yes to a read of his logs.
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
VWAP pairs                  from order times and the MOTD only, never tranche data; a pair joins
                            a run of one side to the run straight after it, at 5% for every base
                            tools/build_product_manual.py, in motd_pairs,
                            #1789 comments 7053861463, 7055925541 and 7056674850
VWAP pages                  one page per base holds all its charts, and no line joins a pair,
                            #1789 comments 7054040450 and 7056959204
a coding rule               runs only where the input's file type, constructs and imports
                            select it; the house says "can run" for its count
                            dev_harness/sigils/coding_partition.py, in selection
```

---

## OPEN DEFECTS

Repaired in the build he runs; each waits on his logs to show it:

```
a Max Cartridge fold, fold rebuy or hedge top-up refused on a full call queue
    src/exchange/ccxt_connector.py, in SyncCall.to_venue; #1695 rows 1 and 3, #1785 row 2
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
  (`src/gui/web/bot_visualizer.js`, in `LayerHeader`); recorded on #23.
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
- A read of his state file or his logs needs his own words in this session. A
  read on inferred permission is refused, and a refused read is never handed to a
  unit.

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
- `artifacts/referee/1633_archive/` is gitignored and sits in the main tree only. It holds the 334 comments purged from #1633 on 2026-11-21 and the body's 68 earlier revisions. #1633 closed on 2026-11-23, and the folder stays as its record.
