# ACERVATOR HOP9 — orientation

Reference. This page carries current state and an index, for a session that has
lost its context or is starting on a new machine. Not a history.

Written 2026-10-30 against `aaadc00d`. **Every claim here names one command that
checks it. Run the command; do not trust the sentence.**

```bash
python -m tools.hop_check
```

Exit 1 means rewrite what moved; the threshold is 15 commits. **Rewrite what
moved. Never append.** HOP9 is the current handoff. HOP2 to HOP8 are archives and
none of them binds.

---

## HOW THE LAST SESSION ENDED

The session of 2026-10-28 to 2026-10-30 stopped at the operator's weekly usage
limit, not at a crash or a context limit. Before it stopped, every unit that could
finish was finished, and the work below was held by his rulings until the usage
resets.

```bash
gh pr list --state open                  # what was still landing
gh issue view 1621                        # the History tab freeze, rows 1-2
gh issue view 1622                        # a buy-back that comes back short in units
```

- **In flight when written:** #1621 rows 1 and 2, in pull request #1625, armed to
  merge itself. Read it before resuming; a row the body marks built is done.
- **Built:** #1622 rows 1 and 4 and his two wire-credit rules, in `aaadc00d`.
- **Build nothing from `aaadc00d` on into his trees until #1622 row 6 lands.** Row 2
  lifted the buy-back distance by a wire's share, and his ruling overturned it: a
  wire carries surplus only. His launch builds stay on `b37c750e` until then.
- **Held until the reset:** #1622 rows 3, 5 and 6; #412 rows 12 to 16, the manual
  rewrite, the evidence presentation and the charts from his newest export; the
  open-row check of #665.

---

## FIRST FIVE MINUTES

```bash
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
- Respect the RAM guard: a hook refuses heavy runs above 70% RAM while he trades.

---

## THE HARNESS

```bash
python -m dev_harness.harness.coding_archetype <path>    # all code
python -m dev_harness.harness.ta_archetype <path>        # any arithmetic
python -m dev_harness.harness.gui_archetype <path>       # Qt and JavaScript screens
python -m dev_harness.harness.docs_archetype <path>      # markdown
```

One path per call; the archetype scans only its first argument. Report `passed`,
never a delta.

**The merge gate** is GitHub CI's `ci-gate` status plus `passed=True` from the
owning archetype on every changed file. Arm a pull request with
`gh pr merge --squash --auto --delete-branch`. Check with `gh pr checks <n>`.
**Never name the local gate in a brief, never retry it, never wait on it**: two of
its lanes collect no test by his decision, and a hook refuses a brief that names
it.

Briefs go to units through the Agent tool, where hooks refuse a brief that skips
the six questions (who, what, where, when, why, how), a reading shown to fail, the
`ci-gate` gate, a skill block of real skills, or the no-deletion clause on manual
work. The hooks and the user-level skills live in the Claude Code user folder, not
in the repository; see MOVING TO A NEW MACHINE.

---

## THE QUEUE

```bash
gh issue list --state open --limit 200          # 29 open when written
```

| To clear | Excluded, and why |
|---|---|
| #63, #319, #407, #412, #433, #665, #881, #993, #1125, #1136, #1486, #1621, #1622 | build-outs #23, #34, #55, #128, #147, #156, #300, #571; living #1440; stock window parked, #220, #571, #1120; Proof of Accumulation paused, #147, #594; his decisions, #937, #980, #1025, #1540 |

Read the body before dispatching, and grep the symbols a row names in the same
call: a row's status can be stale, and a scan that calls a row built has been
wrong far more often than right.

---

## ACTIVE ITEMS AND RESUME POINTS

- **#1621, History tab freeze.** The scan's fetch runs on the bot manager's loop,
  which a timer on the window's thread pumps every 50 ms
  (`src/core/tick_driver.py, in pump_once`), so it holds the window and the
  trading ticks together. Resume from the PR or from rows 1 and 2.
- **#1622, buy-back short in units.** Rows 1 and 4 built: the cartridge fold tests
  every tranche it pays off (`src/trading/scrumming/execution.py, in
  _execute_manual_rebalance`), and a fold logs the units it gained. Row 2, a wire
  term in the distance (`src/trading/otd_math.py, in wired_distance_pct`), is
  overturned: row 6 makes a wire carry surplus only
  (`src/trading/scrumming/wire_routing.py, in _route_scrum_proceeds_via_wires`) and
  takes the wire term out. Row 3 held: `src/exchange/idempotency.py, in
  TradeIntent.fingerprint` carries no time. Row 5: a cartridge leaves other bots'
  reserved dollars alone.
- **#412, the manual.** Rows 12 to 16 wait on the reset: his sentences verbatim
  with one cited "Now:" line each; the PDF holds his text plus how to use it; one
  PDF rebuild; every chart from his newest export; an evidence presentation under
  `docs/`. The builder is `tools/build_product_manual.py`.
- **#433, novel concepts.** Concept 1, hunger and satiety, is built with a per-bot
  switch, off by default. Concepts 2 to 4 are unbuilt. Paper and the Simulator run
  none of the favours and no hunger: a gap against his one-trading-logic rule,
  recorded on the issue.
- **#665, the settings audit.** 145 open rows, all under "Units raised by the work
  itself". Verify each against the current tree before any fix.
- The rest of the queue: read each body.

---

## HIS RULINGS FROM THIS SESSION THAT BIND THE CODE

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
the manual                  his sentences verbatim; one cited "Now:" line; no dated reading
issue comments              every claim about the code cites "path, in symbol"
```

---

## OPEN DEFECTS

- The order id repeats for a repeated intent in one session; #1622 row 3.
- The React Bot Swarm page's layer buttons do nothing when pressed
  (`src/gui/web/bot_visualizer.js`, in `LayerHeader`); recorded on #23.
- Paper and the Simulator judge the vote at the plain floor
  (`src/simulator/back_test.py`, in `ta_direction`); recorded on #433.
- The Extractor reads the vote's direction alone; it takes the three-indicator line
  in its release work.

---

## DISCIPLINES LEARNED EXPENSIVELY

- `gh issue list` returns 30 rows unless given `--limit`.
- `python BUILD.py` ends on a prompt; a non-interactive run raises `EOFError` after
  writing every build. Read `dist/`, never the exit code.
- A React build needs the Electron program in that tree: in `desktop/` run
  `npm ci --no-audit --no-fund`, then `node node_modules/electron/install.js`, and
  check `node_modules/electron/dist/electron.exe` exists.
- A manual brief carries the no-deletion clause, and names unit-written readings,
  never his text, as what may go.
- One branch update at a time, and at most three open unit branches.

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
cd desktop && npm ci --no-audit --no-fund && node node_modules/electron/install.js
python BUILD.py                                   # read dist/ afterwards
python -m tools.hop_check                         # exit 0 before any work
```

---

## CITED AS ABSENT

None.
