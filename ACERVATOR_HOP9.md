# ACERVATOR HOP9 — orientation

Reference. This page carries current state and an index, for a session that has
lost its context or is starting on a new machine. Not a history.

Written 2026-11-18 against `70d2494b`. **Every claim here names one command that
checks it. Run the command; do not trust the sentence.**

```bash
python -m tools.hop_check
```

Exit 1 means rewrite what moved; the threshold is 15 commits. **Rewrite what
moved. Never append.** HOP9 is the current handoff. HOP2 to HOP8 are archives and
none of them binds.

---

## HOW THE LAST SESSION ENDED

The session that wrote this was still running, with one unit out. The 22 pull
requests since `4bd0012c` are #1728 to #1754: fifteen on #1633, four on #1734
and three on #1735. #1622, #1656 and #1695 stay paused, by his 2026-11-13 ruling,
until he points back to them.

```bash
git log --oneline --first-parent 4bd0012c..70d2494b   # the 22 pull requests
gh issue view 1633 --comments            # each record, result and close, newest last
gh release view                          # what is published
gh pr list --state open                  # what is still landing
```

- **In flight when written:** unit R5 on #1735 row 5, record comment 6974732500:
  the manual entry on getting and opening the application on Windows, macOS and
  Linux, the front page's file table, the reference page's release quotes, and
  the PDF.
- **Next, recorded and waiting:** #1633 step 2, record comment 6974831108: a
  follow-on runner in `dev_harness/sigils/fix_class.py`, beside `FOLLOW_ON`,
  applies ruff's own safe fix and runs `judge` again. It starts after R5 merges,
  because both units rebuild the PDF.
- **Every iteration has a record first:** W5H and OCIR, gated by the Truth
  Archetype with `--item`, posted, then acted on. The rule is part 6 of Skill:
  canonized-workflow (#1742).
- **CODE.SECURE needs its two held packs** in the gitignored folder
  `dev_harness/sigils/semgrep_rule_packs/`; both trees hold them. A new clone
  fetches them with the two commands on `docs/manual/16-sigil-project/code-secure.md`,
  and until then the sigil refuses and names the missing file.
- **The release and both trees:**

```
release      0.2.0-20261117.2340.g7b9828ed2044, from 7b9828ed, 6 assets, both AppImages labelled Linux
             gh release list      # 2340 and his running 1928 only
both trees   at 70d2494b; dist/ holds the 2340 pair and his 1928 pair
since        7b9828ed: no file the application is built from changed
             git diff --stat 7b9828ed origin/current -- src desktop tools main.py Acervator_win.spec Acervator_mac.spec Acervator_linux.spec
his app      0.2.0-20261113.1928.g5dbab0790e57, a Qt build, from the Documents tree's dist/
```

- **Held for him:** the Dependabot pull requests #1738, #1739 and #1747 pass
  `ci-gate`, and the permission classifier refuses a merge of them from this
  session; #1739 or #1747 closes alert 82 (`minimatch`). Also the unruled rows of
  the Decisions tables on #1643 and #1622, and moving the Coding Archetype's own
  ruff call onto the step 1c selection, which is a change in `dev_harness/harness/`.
  Do not raise them as a round.

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
| #63, #319, #407, #412, #433, #665, #881, #993, #1125, #1136, #1486, #1622, #1633, #1643, #1656, #1657, #1659, #1660, #1695, #1734, #1735 | build-outs #23, #34, #55, #128, #147, #156, #300, #571; living #1440; stock window parked, #220, #571, #1120; Proof of Accumulation paused, #147, #594; his decisions, #937, #980, #1025, #1540 |

Read the body before dispatching, and grep the symbols a row names in the same
call: a row's status can be stale, and a scan that calls a row built has been
wrong far more often than right.

---

## ACTIVE ITEMS AND RESUME POINTS

- **#1633, the Coding Archetype, first, by his focus ruling.** His 2026-11-18
  refocus, verbatim: "the Coding Archetype with and without sigils attempting the
  same coding task. My goal is to measure this as scientifically as possible."
  Experiment 2 is closed. The growth record, comment 6969215458, has four steps,
  each with its own record first: 1, one result on every run; 2, a follow-on
  runner built from `dev_harness/sigils/fix_class.py, in FOLLOW_ON`; 3, CODE.LOOP
  holds every loop rule; 4, feedback while code is written. Then experiment 3
  compares the Coding Archetype with and without the sigils, sealed first. Step 1
  is built in 1b (#1745), 1a (#1748), 1c (#1750), 1d (#1753) and 1e (#1754):
  every reading path refuses a tool version its card does not hold. Step 2 waits
  on R5, as above.

```bash
gh issue view 1633 --comments      # records 6969302729 (step 1), 6972840542 (1e), 6974831108 (step 2)
```

  Found by 1e and not yet changed: the selection proof exits 1 on every run,
  because `dev_harness/sigils/coding_partition.py, in main` exits 1 while the
  list of sigils without `CAN_RUN` is not empty; report comment 6974607394.

- **#1734, the fleet import and first-run choice.** Rows 1 to 5 and 7 are built.
  Row 6 is partial: no build workflow presses the import buttons on any system,
  and the macOS launch adds a web view sandbox switch a user does not have, in
  `.github/workflows/macos-build.yml`, job env `QTWEBENGINE_CHROMIUM_FLAGS`.
- **#1735, the Linux build.** Rows 1 to 4 are built: every release run builds
  both AppImages and attaches them labelled Linux, and both open their main
  window on a Linux runner with no sandbox switch, with Ubuntu's user namespace
  restriction off and on. Row 5 is in flight, as above.

- **#1622, #1656 and #1695, the money path, are paused.** When work returns to
  them: #1622's unbuilt rows in row order are 14, 18, 21, 22, 24 to 27, 29 to 31,
  33, 35, 36, 38 and 39; rows 28, 32, 34 and 37 wait on his answers in the
  Decisions table; row 20 is partial. Every row of #1656 and #1695 is built and
  is in the build he runs, so read his logs, read only, for each row's lines:

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
                     git merge-base --is-ancestor cd3af6d1 5dbab079      # exit 0
```

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
wire credits                surplus, never a hedge fund; spent only inside a fold tranche,
                            capped at the maximum growth per cycle; a remainder returns
                            to the pool, src/trading/scrumming/wire_routing.py
smart wires                 carry surplus only, never the dollars a buy-back needs;
                            the buy-back distance carries no wire term, #1622 row 6
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
  (`src/gui/web/bot_visualizer.js`, in `LayerHeader`); recorded on #23.
- Paper and the Simulator judge the vote at the plain floor
  (`src/simulator/back_test.py`, in `ta_direction`); recorded on #433.
- The Extractor reads the vote's direction alone; it takes the three-indicator line
  in its release work.
- The macOS build workflow launches both variants with the web view sandbox
  switched off (`.github/workflows/macos-build.yml`, job env
  `QTWEBENGINE_CHROMIUM_FLAGS`), so its launch reading does not match a user's
  launch; #1734 row 6.

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
