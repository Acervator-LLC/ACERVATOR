---
name: ocir
description: Observe, Calibrate, Iterate, Repeat. Load before trusting any measurement, gate, test or scan — and before reporting a zero, a pass, or a count. Invoke by name when the operator asks whether an instrument is sound, or when a check reports nothing found.
---

# OCIR — Observe, Calibrate, Iterate, Repeat

**A zero is a claim about the instrument, not about the world.**

## The loop

**Observe.** Take the measurement. State the number and the method that produced
it — the grep pattern, the run id, the file list, the command.

**Calibrate.** Prove the instrument can report. Point it at a known positive and
show it fires. Point it at a known negative and show it stays quiet. **A check
nobody has watched fail is not a check.**

**Iterate.** When the instrument and the result disagree, the instrument is
suspect first. Narrow it, fix it, run it again.

**Repeat.** Re-measure after every change. A result from before the change is
evidence about a tree that no longer exists.

## The rules that follow from it

**Never report a delta. Report `passed`.** Fewer findings than last time is not
a pass.

**A green gate whose instrument was never proved proves nothing.** Run the
positive control before the run that matters.

**A fixed instrument is proved once per session, not once per unit.** The
archetypes do not change between units. Proving them 24 times over 12 units
found nothing 24 times. Prove at the start, then trust it until something
changes it.

**Check the exit code.** 139 is SIGSEGV and prints no failure summary — a crash
reads as silence.

**Two-sided or it did not happen.** Red before, green after, both quoted.

## Failure modes measured in this project

- A pin reading `worked=100 of 100` on a run where nothing worked.
- `caplog` assertions that could never fail, because the loggers set
  `propagate = False`.
- A test suite passing 40 of 40 while the guard it covered was already dead —
  its fixtures wrote synthetic values the real tree no longer had.
- A colour assertion passing on 6 pixels of an antialiasing edge.
- A scan whose file list moved with the code, so it went green by emptiness.
- A fallback that could never fire because the failure produced a non-empty
  value.

Every one read as evidence. None was.

## How to reach the right rows

**Ask which question you are asking, then read only that section.**

| section | the question it answers | rows |
|---|---|---|
| **Counting and searching** | the number is wrong, or the search never looked where it claimed | C8, C15, C25, C26, C30, C33, C45, C56, C82, C83, C87, C89, C103, C107, C116, C123, C129 |
| **A check that cannot fail** | the green means nothing because the instrument was never able to report | C1, C2, C3, C4, C5, C6, C7, C9, C10, C17, C18, C22, C23, C29, C38, C47, C51, C52, C57, C84, C85, C96, C100, C106, C108, C110, C114, C115, C124, C126, C128, C131 |
| **The machine you are on** | the reading is a fact about this host, not about the product | C11, C27, C35, C37, C50, C65, C66, C69, C71, C84, C98, C104, C127, C134 |
| **Order, identity and position** | every value matches and the arrangement is still wrong | C3, C19, C24, C43, C46, C60, C128 |
| **Objects, threads and windows that outlive their owner** | the thing read was freed, replaced, or still running | C12, C20, C21, C42, C44, C68, C70, C133 |
| **Absence read as a value** | nothing found, nothing ran, or nothing declared, reported as a result | C13, C30, C40, C41, C57, C59, C92, C99, C120, C121 |
| **A number from recall instead of measurement** | written from memory of a library or a neighbour, never taken here | C48, C67, C86, C88, C119, C125, C129, C130 |
| **The referee's own conduct** | rules I invented, counts I reported, briefs that lose to a default, and context spent on my own output | C25, C82, C83, C86, C88, C89, C90, C91, C93, C94, C95, C97, C101, C102, C103, C104, C105, C109, C112, C113, C124, C125, C126, C131 |
| **Shells, files and other runs** | the command, the file, or a neighbouring worker changed the answer | C16, C62, C63, C64, C73, C76, C79, C80, C111, C117, C118, C122, C126, C127, C131, C132 |
| **Comparing values and types** | the two sides agree on paper and not in the machine | C14, C31, C32, C36, C77, C122, C130 |
| **Names, markers and registries** | a name, a suppression or a registry entry drifted from what it points at | C28, C34, C39, C49, C53, C54, C55, C58, C61, C72, C74, C75, C78, C81, C123 |

A row can appear in two sections; the same shape is reached by two different questions. **When a shape is not on the list, write the new row and name its section.**

## How a row is written

A row is read mid-task to decide whether a result can be trusted. It carries
four things and nothing else:

1. **The shape** — the check or action, named in the terms the code uses.
2. **The measurement** — the number, command, file or exit code that showed
   it. **No measurement, no row.**
3. **The question** — one question, answerable yes or no, before trusting the
   result.
4. **The command** — the exact thing to run or write instead.

**Banned in a row:**

- A slogan or aphorism. `A report is not a unit of work` names nothing to do.
- First-person narrative of the incident, or what the operator said or felt.
- `it reads as`, `this means`, `the cost is` — state the effect, not a reading
  of it.
- A repeat count, unless the count is the measurement.
- Any sentence not checkable against a file, a command, or a number.

A row failing this is rewritten, not annotated.

## The catalogue — checks that could not fail

Every one was found in this project. **Hunt these in your own checks before
reporting a count.** Add to the list when a new shape appears; that is the
Iterate step.

| id | shape | how it hides |
|---|---|---|
| **C1** a value compared to itself | always true |
| **C2** a literal typed into the trace | the widget is never read |
| **C3** order keyed by position | a swap reads as unchanged |
| **C4** types compared where several share a type | a swap reads as unchanged |
| **C5** a name read from the file under test | a rename moves both sides |
| **C6** a colour check on `#888` | all three digits equal, so a channel swap reads the same |
| **C7** `caplog` on this project's loggers | they set `propagate = False`; it sees nothing |
| **C8** counting rows without checking WHICH survived | dropping the wrong end passes |
| **C9** a check a later step overwrites | the rewrite hides it |
| **C10** a measuring script whose edit never applied | "nothing broke" was never measured |
| **C11** **asserting a property of the machine you are on** | green here, red on another host |
| **C12** **a declared value the platform repaints** | the window asks `#225522`, Windows paints `#183d18` — the pixel check states an OS fact, not a product fact |
| **C13** **reading the log, never the state** | a method logs "removed" without removing; compare the data structure, not the message about it |
| **C14** **a picture compared against another picture from the same side** | whether a changed value is invisible depends on the host's fonts |
| **C15** **a command that counts the wrong unit** | a byte count reported 658 carriage returns in a file holding zero |
| **C16** **a wait keyed on a file another run may have written** | the wait returns instantly on stale data and reports a run that never happened |
| **C17** **two cells driven with the same input** | swapping them compares a value to itself |
| **C18** **a planted defect that paints no pixel** | it belongs in a text check, not the picture set — prove it moves a pixel before trusting it |
| **C19** **field order wrong while every value matches** | a value-by-value check passes; only an order check reports |
| **C20** **reading a widget whose owner was collected** | the check dies with an error instead of reporting, and an error reads as noise in a large run |
| **C21** **a declared value the platform rewrites** | `setSizes([250,350])` reads back `[220,255]`; assert the request, not the read-back |
| **C22** **a control driven with different elements on each side** | a grey card against a green one differs for the wrong reason |
| **C23** **a guard that asks the wrong question** | "did this run load a font?" is not "does this machine have fonts?" — the build machine ships them unasked |
| **C24** **a test whose result depends on what ran before it** | the code under test writes module-level state; the build machine runs `-n auto` and orders differently |
| **C25** **a control file named without a path** | two files share the basename; `src/gui/history_tab.py` builds 1 timer, `src/gui/main_tabs/history_tab.py` builds none |
| **C26** **counting a name instead of a use** | `grep -c QTimer` counts the import line too; count the construction |
| **C27** **measuring text width in a typewriter font** | every letter takes identical space by design, so no two strings of one length can differ; measure in the general application font |
| **C28** **a reset that clears only its declared keys** | a field the register does not know keeps the first side's value into the second |
| **C29** **a refusal message that lists every type it accepts** | asking whether it names a type can never fail; read the headline line |
| **C30** **a "nothing reads this" count that counts the new file** | the converted module names the value, so `grep -c` returns 1 and the value looks read. **Ask: does the match list include the file the change added?** Exclude it, then count |
| **C31** **a whole number and a decimal** | `12` equals `12.0` in a value check and hashes apart |
| **C32** **a not-a-number compared to itself** | never equal, so a plain comparison reports a difference that is not one |
| **C33** **a tag counted by text, not by line** | a marker inside a string inflates the count and hides a lost one |
| **C34** **a style sheet that selects by class name** | a rebuilt element of another class gets none of the look |
| **C35** **a test needing a package the build machine does not install** | the fast lane installs four; the development host has everything |
| **C36** **a settled value that depends on WHEN it was requested** | pane sizes set before the labels hold text settle differently from after |
| **C37** **a picture of a window a browser draws** | no product value reaches the pixel; it renders flat white |
| **C38** **a recorder wrapped around a helper that drives BOTH sides** | it reports the sum, so a line lost on one side is hidden by the other's |
| **C39** **a reset pointed at a name the shared module does not carry** | `setattr(..., raising=False)` creates a fresh attribute instead of failing, so the guard resets nothing while reading as present |
| **C40** **a reader that folds two different absences into one value** | a cell that does not exist and a cell with no colour set both read as empty, so a lost cell passes as a plain one |
| **C41** **a step driven through a mechanism that swallows a failure** | one side clicked through a signal that catches and prints, the other called directly; the difference came from the driver, not the product |
| **C42** **a worker thread that outlives the window that started it** | cleanup looks for threads owned by the window; an unowned one is missed, so cleanup reports clean and the thread runs into other files' tests |
| **C43** **the parallel runner blames the test that was running** | an asynchronous killer is charged to whichever test the worker held, so the same defect names a different test each run and reads as flakiness |
| **C44** **a guarded call whose result is used outside the guard** | the failure the guard was written for arrives from the line after it, so no error shows and the status line silently keeps its old text |
| **C45** **a construction counted by text finds one inside a comment** | the pattern reports 2 where the code builds 1; count from the parsed file, which cannot see prose |
| **C46** **a merged order decided by which worker finished first** | records fetched in parallel and stably sorted put equal keys in the machine's order; comparing the sequence reads the worker pool, not the product |
| **C47** **a statement whose value is never used** | it reaches no output, so no comparison of two sides can report it; only reading the file finds it |
| **C48** **a constant written from recall of a library instead of measured** | the probe checked the behaviour but never its boundary; `1e-10` from memory where the real threshold was below `1e-12` |
| **C49** **a recorder subclass overriding a method the class never declares** | the method belongs to the platform, so a counter reading the class object counts it for ever after; read the shipped file, not the class |
| **C50** **a colour read off a live widget instead of off a rendered picture** | the declared value is not the painted one; the GUI archetype has rejected this on at least six units |
| **C51** **a stand-in argument the test never reads** | the stand-in accepts a value and drops it, so a wrong value passes |
| **C52** **an unreachable branch inside an assertion** | the check reads a constant, so it cannot report |
| **C53** **a test window with no accessible name** | nothing announces it, and the omission is invisible to every other check |
| **C54** **a constant named so a security scanner reads it as a secret** | the finding is real about the name even when the value is not a secret |
| **C55** **a handler whose message names an operation other than the one that failed** | the log points a reader at the wrong call, and a search for the real failure finds nothing |
| **C56** **a search whose filter is narrower than the world** | the absence is a fact about the filter and reads as a fact about the world; one narrow platform label reported PySide6 missing for 3.14 |
| **C57** **a gate that never started looks identical to one that failed** | a stale fixture path returns "failed" with zero tools run; read the tool count, not just the verdict |
| **C58** **a sanitiser applied to the field that cannot hold the character** | the guard is on the value that never carries it and absent from the one that does, so every real input passes and the guard reads as working |
| **C59** **a known-finding allowlist keyed on a line number** | the finding is real and the pin is right, but the key moves whenever anything above it moves, so a comment edit reads as a new defect; key on the file and the symbol |
| **C60** **a position assertion naming a neighbour** | "this sits immediately after X" holds only until something sorts between them; ordering is already proved by comparing the list to its own sorted copy |
| **C61** **a guard written for one name and not its twin** | an absent optional library leaves 2 names unset; a guard covering 1 of them raises `NameError` at import, only on a host without the library. **Ask: does the guard name every symbol the same import binds?** Guard all of them, or import none |
| **C62** **a repair tool that assumes one line per item** | a merge resolver sorting lines inside a conflict split a two-line entry and produced a file that would not parse; a tool that rewrites a list must refuse any run it cannot prove balanced |
| **C63** **a program typed through a shell heredoc** | the outer quoting layer rewrites the inner text, so the file that lands is not the file written |
| **C64** **a command after a heredoc** | its output and exit code are lost or read from the heredoc |
| **C80** **a test that rewrites a file another worker is loading** | a multi-step write under `-n auto` serves a truncated file; the page defines no module and the failure names a different test each run. Replace in one step with `os.replace` |
| **C81** **a child element with no read-back name** | the page reads its text as empty, so no check can see a wrong value in it. Name every child a check must read |
| **C79** **a Windows error code the retry does not catch** | `mkdir` on a directory mid-`rmdir` raises `PermissionError`, not `FileExistsError`; a retry catching only exists crashes |
| **C78** **brief vocabulary in a shipped comment** | *gate, plant, blind, fires, control, harness, seam* name nothing in the file. Comments cap at 20 words, one sentence, every word an identifier in the block |
| **C77** **a value resolved by looking up which name carries it** | five of six card numbers are carried by 2 or 3 tokens; `10` is a text size and a spacing step. Resolve only when exactly one non-alias name carries it. Necessary, not sufficient: a margin of 6 resolved to a token named for a corner radius |
| **C75** **a check matching by class name against a global registry** | two files add a handler of the same class; the check cannot tell whose is whose. Snapshot inside your own scope, compare by identity |
| **C76** **a line-ending count taken through a Git Bash pipe** | the pipe adds the carriage returns it reports. Use `git ls-files --eol` |
| **C74** **a suppression marker the formatter moved** | `black` wraps a long `except` and carries the trailing `# noqa` to the closing `):`, so it binds to nothing. Run the checker with and without `--ignore-noqa` and compare counts |
| **C73** **a scratch artefact under a generic name** | the next unit reads another unit's file; it exists, parses and answers, so nothing reports the swap. Name every artefact for its unit |
| **C72** **a container sized before it is filled** | `setRowCount(n)` then filling; a refusal mid-fill leaves empty rows the count still reports as present. Keep declared and held as two numbers |
| **C71** **a native crash the shell reports as command-not-found** | on Windows a crash exits `-1073740791` and Git Bash reports exit 127 with no output. Read the code through PowerShell |
| **C65** **the surrounding cost pinned as a positive control** | `import src` starts a process on one host and not another; the number is a machine fact. Pin that surrounding work exists, never how much, or use a planted control |
| **C66** **a skin control on a widget that paints its own rectangle** | `paintEvent` fills the rectangle after the style resolves, so the control render equals the plain render. Holds only while the fill is opaque: at reduced alpha the rule moves pixels again |
| **C67** **one file's measurement carried into a brief as a general fact** | a control rule measured on one widget was written into the next brief as "measured to work"; it reached no pixel on that file. A measurement names the thing it was taken on, or it is recall wearing a number (**C48** with a citation attached). **Measured again 2026-09-10, and this row did not reach the brief that needed it:** a record size of **1,305 bytes** went into a brief as the size of a world-grid discovery record. It was measured on a **movement leg**, a different action with fewer argument fields; the unit re-measured discovery at **1,472.2 bytes**, twice. The same brief also offered **478** as a compact alternative, and no compact encoding exists in the code at all — the chain writes full named fields, so both smaller figures describe an encoding nothing writes. **The operational rule, because the question alone was not enough: a byte figure written anywhere must carry the ACTION it was measured on, in the same sentence.** `1,472 bytes a discovery record` survives being moved; `1,472 bytes a record` does not. Write the subject or do not write the number |
| **C68** **a runtime counter scoped to the whole object graph** | reading the framework's connection count across a widget tree returned 888 where the product wired 10, because the window frame's own buttons are connected internally. Scope the counter to what the product wires, and prove a bare instance reads zero |
| **C69** **a fix aimed at the test the parallel runner named** | the name a runner prints is a fact about scheduling, not about cost; measured, the named test was the cheapest in its file while two others held 370 and 245 live widgets. Measure every test in the file before treating the named one as the outlier |
| **C70** **a refusal reported on two channels** | the binding raises to the caller and also reports through the framework's own unraisable channel, so a test that correctly catches the refusal is still failed by the runner's exception capture |
| **C82** **a brief that names a width instead of a bounded number** | `-n auto` expands to 24 workers plus one browser each on this host; 2 agents at once is 48 of each, measured at 4.1 GB while the live app traded. **Ask: does the brief name a number, or a word the machine expands?** Write `-n 4`; the cap for rate measurements is 8 |
| **C83** **an unbounded run count asked for as "enough"** | "enough runs that the rate is a number" was read as 28 consecutive suite runs at full width. A measurement instruction carries its own ceiling, and the report says what that ceiling cannot distinguish |
| **C84** **a rendered-pixel reading taken as a widget fact** | the same markup comparison said "the label swallows the tags" alone and the opposite after another file ran, because the answer follows whichever platform plugin the process picked. The width the widget asks for is identical in both conditions. Read a value the widget reports, never two pictures |
| **C85** **a style walk that reads only the base block** | a declaration walk never enters `QPushButton:disabled`, so two swapped colours inside it were unreachable; the sweep found them only by splitting the raw sheet on the colour mark. A walk that cannot reach a sub-block reports a clean sheet that is not clean |
| **C86** **a brief rule with no named author** | two harness-scoped rules were generalised into "reported, not fixed" for product defects and written into 20 briefs; 20 units obeyed it and left their defects unrepaired. **Ask: for each rule in the brief, who gave it — quote the source.** A rule with no quotable author is invented; delete it before dispatch |
| **C87** **a checker pointed at a typed list of files** | the comment checker reported 0 faults while a two-sentence, 28-word docstring sat in a test file the unit wrote after the list was typed. A list goes stale the moment a file is written that was not planned. **Discover the subjects from the branch diff**, and prove the discovery finds a file added after the checker was built (same shape as the swap-module discovery, C83) |
| **C88** **a brief rule that competes with an environment default** | auto-mode's Bash guidance recommends heredocs for file edits; the brief forbids them. 4 agents broke it in one day and 3 hung `python -` processes had to be found and killed. Restating the rule in the brief did not stop it. **Ask: does the brief give the compliant command verbatim?** Write `Write the file, then run python <path>` and `git commit -F <path>`, and name the guidance being overridden. See C91 |
| **C89** **a similarity where a structural fact was available** | picking which tests exercise a module by grepping its symbol names matched 435 files, because `count` and `emit` appear everywhere. The fix offered was to keep only names that look distinctive — one guess swapped for another, tuned until the number felt right. **The import closure is a fact and gives the same answer twice.** Three sweeps had already selected tests this way. Ask what relation is actually being measured; if it can be resolved, resolving it beats matching it |
| **C90** **a turn ended with a report while an agent seat was free** | measured: 7 turns in one session ended in a summary with `ListAgents` reporting 0 running agents. **Ask: does `ListAgents` return fewer running agents than seats?** If yes, dispatch into every free seat first, then write the report. Read the seat count from `ListAgents` in this turn, never from the last dispatch you remember |
| **C91** **a ban enforced only by a refusal, against guidance that arrives every turn** | measured: `block_heredoc.py` refuses 17 of 17 heredoc forms and refused this session again after shipping, because auto-mode's Bash guidance recommends heredocs for file edits on every turn while the hook fires only after the command is typed. **Ask: is the banned form named by guidance that arrives every turn?** If yes, add it to `_ENVIRONMENT_CONFLICTS` in `.claude/hooks/prompt_router.py`, which prints the ban and its replacement before the turn starts. Proved on 6 prompts sharing no keyword, plus an empty-prompt control |
| **C92** **a present-tense command answering a question about the past** | `git ls-files .githooks` returned nothing, and that became "the hook was never committed" in a shipped guide. `git log --diff-filter=D -- .githooks/` returns `8b7097b remove the pre-push gate hook; CI replaces it` — a deliberate removal, not a gap, and the guide then argued for undoing it. **Ask: does this command read the working tree, or the history?** For "was this ever here", run `git log --diff-filter=D -- <path>` and read the commit message before naming an absence a defect |

| **C93** **a brief rule competing with a permanent rule in a loaded skill** | 7 agents in one session ran `python -m tools.gate` after a brief forbade it, each citing harness-law's FIFTH PERMANENT RULE — "Code does not leave the branch or get merged until all gates are passing", marked NO EXEMPTIONS. Obeying it was correct; the brief was written without reading it, and each run cost 500-700 seconds on the machine running the live app. **Ask: does a loaded skill already rule on what this brief is about to forbid?** Read it first. When it rules and is stale, edit that skill and quote the later commit that superseded it — `8b7097b` here — rather than writing a brief that competes with it. See C88, C91 |

| **C94** **the same brief retyped into every dispatch** | 332 agent dispatches averaging 7.8 KB, 2.58 MB, 9.9% of a 26 MB session that ended on "prompt is too long"; assistant-generated blocks were ~70% of that total. The standing sweep brief — worktree rule, prohibitions, comment standard, identity-proof method — was retyped verbatim into each one. **Ask: is this text already a file the agent can read?** Put the standing brief on disk and pass its path; a dispatch carries the target, its measured counts, and the facts specific to it. Measure with `measure_context.py` before blaming input |
| **C95** **a pasted export instead of a path** | one attached CSV measured 1,113,493 bytes, ~309,000 tokens — larger than the whole context window, and attachments cannot be compacted away. Eleven copies of that export were already on disk. **Ask: does this data exist as a file?** Read it with `grep`, `sed -n` or pandas and quote the rows that matter. The same applies to screenshots: 25 images measured 1.81 MB, 6.9% |
| **C96** **an exit code read through a pipe** | the pipe reports the LAST command's status, not the tool's. Twice in one session: an archetype run through `grep` reported 255 while the archetype itself exited 0, and a fixture control read `$?` after `tail`, so `known_good` and `known_bad` BOTH looked like exit 0 — the control was dead and its green meant nothing. **Ask: whose exit code is this?** Capture it on the same line as the tool (`$out = cmd; $code = $LASTEXITCODE`), then filter the captured text. This matters most on a positive control, where a swallowed code turns a two-sided check into no check at all. **Stdin through a pipe is the same family and worse**: `$payload \| python hook.py` does not deliver stdin here — the script reads EOF, its `json.load` fails, and it exits 0, which reads as ALLOWED while nothing ran. Measured twice, both times a hook under test reporting a pass without ever seeing a payload. Drive it with `subprocess.run([sys.executable, HOOK], input=payload, ...)` from a probe file. **ENFORCED IN PYTHON** — `~/.claude/hooks/block_heredoc.py` denies the pipe. See C84, C85 |
| **C97** **a file added to a directory that keeps a register** | three guards went red in one session from the same act, each found by a unit tripping over it rather than by the author. Restoring the handoffs broke `test_repo_root_inventory` (six undeclared root files) and `test_no_live_file_still_points_at_the_old_path`; committing two new tools broke `test_every_tool_on_disk_is_declared` — "tools/ holds undeclared scripts: ['conversion_state', 'hop_check']". Each register exists precisely so a new file must argue for its location. **Ask: what enumerates this directory?** Before committing a new file, grep `tests/` for a listing that names its neighbours — `test_repo_root_inventory.py` for the root, `test_tools_are_reachable.py` for `tools/`, `test_harness_is_reachable.py` for harness callers. Declare it with the MECHANISM that requires the location, never "tidier here". A register also guards against an allowance outliving its file, so a stale entry fails too |
| **C99** **an AST call scan blind to an aliased import** | walking `ast.Call` and matching the called name is the right instrument for "does this have a caller" — grep cannot tell a docstring example from a call — but it misses `from m import f as g`, because the call site says `g`. Measured: a scan reported `main.py` as a non-caller of `get_registry`; `main.py:478` imports it as `_get_st_reg` and calls it two lines later, so a true claim would have been called false. A recheck found **six** aliased bindings of that one name. **Ask: could this name be bound under another?** Confirm a zero with a second instrument — every occurrence of the name outside docstrings and comments — and report aliased imports separately. Two zero-caller findings were re-verified this way and stood: `create_lock` and `_invalidate_balance` each have exactly one occurrence, their own `def`. See C13, C30, C56 |
| **C100** **RUF100 read as proof a suppression is inert** | `--select RUF100` switches every other rule off, so every directive looks unused — that is the known half. The unknown half: **the archetype's ruff and the repo's ruff enable different rules.** Measured — RUF100 reported two `# noqa: S311` as non-enabled; removing one turned S311 into a **high** finding and the archetype `passed=False`. Following the guidance would have stripped a load-bearing suppression and turned the gate red. The same guidance sat in every unit brief for a day. **Ask: whose rule set answered this?** The only proof of inertness is REMOVAL — delete the directive, re-run the archetype, compare rule ids against the baseline; a rule id that appears was suppressed by it. `# noqa: E402` is the one confirmed-inert case, because `.flake8` ignores E402 globally (#402). See C96, C99 |
| **C101** **a one-off instrument built where a toolbox exists** | measured across 529 test files: **485 define their own helpers, 148 import the shared fixtures**. `digest` is written in 72 separate files, `app` 69, `js` 68, `browser` 65, `render_offscreen` 46. Every rebuild rediscovers the same traps, and several fail: a `git show` read decoded as cp1252 reported a false identity mismatch TWICE; a control mutated a token inside a comment and passed while proving nothing; an `ast.Call` scan missed an aliased import and would have called a true claim false. **Ask: does this instrument already exist?** Before writing a probe, a control, a call scan or an identity check, look for it in `tests/fixtures/` and in what a sibling unit shipped this session. A calibrated instrument reused is worth more than a fresh one, because the fresh one carries every trap the old one already fell into. Reinvention is also what turns a suite into 16,788 tests nobody can reason about. See C99, C100 |
| **C102** **a producer's own check re-derived by hand outside it** | `tools/build_product_manual.py` validates its output and prints `contents pages: ok - 211 contents rows land on the page they name`. That check was hand-written twice anyway, minutes apart: a regex keyed on dot leaders parsed **0 of 211** rows and returned a zero that was nearly reported as fact, then a replacement checked **14 of 211** and led with the count instead of the result. The producer had already done it, correctly, on every row. **Ask: does the thing that made this artefact already check it?** Read the producer's own validation output before writing a reader for its output, and when a check belongs to every run rather than to one, it goes in the archetype — a check reachable only by building is a check nobody runs. See C101, C57, C89 |
| **C103** **a sample reported as verification of the whole** | 14 rows of 211 were checked and the reply opened with `211 rows parsed`. The number that sounded like coverage measured only how much the parser found; the number that mattered — rows actually confirmed — was fourteen, and it was not stated as a fraction. **Ask: what is the denominator, and did every member get checked?** Check every member when the set is finite and small enough to walk, and when sampling is genuinely required, report it as a fraction and say what the unchecked remainder could hide. A count of what an instrument parsed is never a count of what it verified. See C8, C83, C89 |
| **C104** **a guard fires and the answer is a lighter tool** | `block_heavy_run.py` refused a shell call at **84.2% RAM against a 70% ceiling**, on a machine running two live trading instances. Four units were dispatched at once. The guard was obeyed literally and evaded in substance: the same reading was taken through the file tools, which the guard does not gate, and the load stayed up. **The guard names a machine state, not a forbidden command.** Ask: **is the fix a different tool, or less load?** When a resource guard fires, stop a consumer — the operator's own answer was "or can just unitize and do work sequentially". Sequential dispatch also makes the thing being blocked runnable: a CI lane cannot start at 84%. See C98, C82, C11 |
| **C105** **a tool that exists, absent from every brief** | `tools/local_ci.py` runs the lanes `.github/workflows/ci.yml` states, capped at 4 workers for this machine. **Eleven unit briefs in one session never named it.** Each carried "no full gate, run serially, no `-n`" — written to protect the trading host, which is the same reason that tool caps itself — so units concluded the archetypes were the only gate and one wrote that conclusion down. The operator: *"I never said disable local CI."* **Ask: does a canonized tool already do what this brief is talking around?** A constraint repeated into every brief hardens into a policy nobody chose; check the tooling before writing the constraint again. See C101, C102, C57 |
| **C106** **an instrument whose verdict is not on its exit code** | The four archetypes do not answer the same way. Measured on the fixture pairs: `coding_archetype` and `docs_archetype` exit 0 on `known_good` and **1** on `known_bad`. `gui_archetype` on `known_bad_widget.py` and `known_bad_screen.js`, and `ta_archetype` on `known_bad_ta004.py`, **exited 0** while their JSON reported `passed=False`. **RE-MEASURED 2026-09-10 and that no longer holds: all four now exit 1 on `known_bad` and 0 on `known_good`** — `known_bad_ta004` exit 1, `known_bad_ta001` exit 1, `known_bad_widget.py` exit 1, `known_bad_screen.js` exit 1, `known_good_ta001` exit 0, `known_good_widget.py` exit 0. The row is kept because the rule outlived its example: **the exit code is necessary and never sufficient**, and a unit told only to read it will report green off a `passed=False` file the day an archetype changes again. **Ask: which channel carries this instrument's verdict?** Read `passed` out of the JSON, and put the channel in the brief. This row was itself carried past the change it described, which is C119 reaching the catalogue — re-measure a row before quoting it. See C57, C96, C4, C119 |
| **C107** **a search in one naming convention across a boundary that renames** | `grep -rn "bot_swarm_list" src/ desktop/ tools/` returned no JavaScript consumer, so the module read as mounted by nothing, and that absence went into a unit brief as a measured fact. `src/gui/web/bot_swarm_tab.js` reads it at four sites, through the globals `acervatorSwarmList` and `acervatorLoadBotSwarmList` — camelCase names a snake_case pattern cannot match. The unit refuted the premise I had written for it. The absence was a fact about the pattern. **Ask: does the other side of this boundary spell the name the same way?** Across a Python-to-JavaScript seam, search every convention the seam uses — snake_case, camelCase and PascalCase — or search the stem with separators stripped, then confirm the hit count from both sides. See C56, C5, C30 |
| **C109** **a skill named in a brief instead of loaded, while its contents are hand-written every time** | 29 skills exist, identical under `~/.claude/skills/` and `dev_harness/skills/`, and every name used in a brief resolves. **Six were never loaded across a whole session**, and each one encodes what was then written by hand, per brief: `two-sided-control` ("prove a check can fail before trusting that it passed") was retyped into every brief for hours; `branch-discipline` carries the worktree, line-ending and process-reaping rules a unit then rediscovered through 2,314 CRLF endings; `unit-decomposition` sizes units, and an eight-module unit was hand-bounded instead; `file-passes-only` defines the operator's own six-line reporting format, and the replies ran to paragraphs; `archetype-peer-review` is recommended by `prompt_router` on every turn. The names resolving is not the same as the skills binding. **Ask: which loadable skill already says what I am about to write out by hand?** Load it by name before writing the clause, and when a brief needs a rule, name the skill that holds it rather than paraphrasing the rule into the brief. A paraphrase drifts from the skill and nothing reconciles them. See C101, C105, C102 |
| **C108** **an item in a picture comparison read off the model, not the picture** | A 27-item comparison closed two conversion rows, and among the items it reported as matching were "both table column sets" and "5 identical signal rows". Measured afterwards in the shell: `table-group 0, grid 0, grid-row 0, empty-note 0`, against a control of `module-group 6`, with the payload carrying `signal_columns 6, pair_columns 7`. **The tables draw nothing.** The values were equal on both sides because both sides read one payload, so the item agreed no matter what rendered — the same green a deleted component would give. One such item taints every other item taken the same way, so the whole comparison becomes unverified rather than just that row. **Ask: for each item, which surface did I read this value from?** Read every reported item off the rendered page or the saved picture, name that source per item, and count elements with a control count beside them that is non-zero, so a zero is a fact about the page and not about the counter. See C50, C22, C40, C84 |
| **C110** **a build comparison served a cached artifact** | A unit moved the trophy contract's metadata helpers into a shared library and had to prove the deployed bytecode did not change. `forge inspect` answered from a **cached artifact** and reported no change on a contract that had genuinely changed. The comparison was then rebuilt with `forge build --force` and the metadata tail switched off, and proved able to report by mutating `MAX_EKTHELIUS` from 21 to 22 and watching the hash move before restoring it. An "identical" from a cache is indistinguishable from an "identical" from the code. **Ask: did this comparison rebuild, or read a file an earlier build left behind?** Force the rebuild, strip whatever the compiler stamps in that is not the code, and move a constant to watch the output change before trusting that it did not. See C9, C10, C47, C106 |
| **C111** **a .NET file call from PowerShell wrote the live tree, inside a worktree** | A unit working in a git worktree used PowerShell .NET file calls, which resolve a relative path against the **process** working directory rather than the shell's `cd`. It wrote `contracts/AcervatorTrophy.sol` in the operator's live trading tree with a changed constant, then wrote the original bytes back; `git status` and `git diff HEAD -- contracts/` were both empty afterwards and all four tier ceilings read their declared values. A worktree protects the tree only from tools that respect the working directory. **Ask: does this call resolve its path against the shell, or against the process?** Use the editing tools for every file change, and where a shell must write, pass an absolute path rooted at the worktree — never a relative one. See C73, C63, C64, C79 |
| **C112** **a brief forbidding a file while assigning a feature that lives in it** | A unit brief listed the tab surface among five files not to touch, and separately assigned "the wallet's loot section", which is inside that file. The unit took the specific assignment, confined its edit, and reported the contradiction. Neither list looked wrong on its own: **files not to touch were named by file, and the assignment was named by feature.** A feature lives in a file, so the two can disagree silently, and the unit has to choose which half of the brief to obey. **Ask: is every boundary in this brief written as a path?** Name the assignment by file as well as by feature, and check the assignment list against the do-not-touch list by path before dispatch. See C25, C101, C105 |
| **C113** **a skill edited in the tracked copy while the loaded copy binds** | 29 skills exist twice: `dev_harness/skills/` is tracked in git, and `~/.claude/skills/` is what the Skill tool loads — every loaded skill reports `Path: userSettings:<name>`. Measured after a session of adding rows: **two of the 29 had diverged.** `ocir` was missing C106 through C109 in the loaded copy, so four rows written to harden the work bound nothing. `canonized-code-testing` was missing its whole web-analyzer section in the loaded copy — `eslint`, `stylelint` and `html-validate`, all three installed and configured at `node_modules/eslint/bin/eslint.js`, `node_modules/stylelint/bin/stylelint.mjs`, `node_modules/html-validate/bin/html-validate.mjs` — so every unit that loaded it was told the Python tools and never told the three the operator had authorised. A row in the tracked copy is a record; only the loaded copy changes behaviour. **Ask: did this edit reach the copy the Skill tool loads?** Write the tracked copy, copy it to `~/.claude/skills/<name>/SKILL.md`, and diff all 29 pairs afterwards — a silent divergence reads exactly like a skill that was followed. See C109, C105, C39 |
| **C114** **a control that scales every input, against a function that is scale-invariant** | A unit had to prove a pot division reads performance and never spend. Its first control multiplied **every** participant's spend, and the payouts did not move — which proves nothing, because a proportional share is invariant under a common factor on any input, including one it genuinely reads. The control was rewritten to scale **one** participant's spend by 1000, showing all three payouts identical to the digit, with the discriminating half beside it: halving that participant's score moved all three. **Ask: would this control also leave the output unchanged if the function DID read the input?** Vary one subject, not the population, and pair it with a change to the input the function is supposed to read. See C1, C17, C22, C38 |
| **C115** **a Solidity analyzer's exit code is not its verdict, and the code itself moves with the invocation** | A unit reported that on this host `slither`'s exit code is 127 whatever it finds and `semgrep`'s is 0 either way, and concluded the finding list is the verdict. Refereeing it, the same two tools were run directly: `slither contracts/ACRV.sol` exited **1** and `semgrep --config=p/solidity contracts/ACRV.sol` exited **7** — neither 127 nor 0. **The unit's numbers did not reproduce, which strengthens its conclusion rather than weakening it**: the code varies by invocation, config and host, so it carries no stable verdict for either tool. **And that semgrep 7 was not a scan at all** — a later unit found `p/solidity` returns HTTP 404, so the run downloaded no rules and scanned nothing; re-measured here, `--config=r/solidity` exits **2** on the same file. A config that does not exist and a file with findings produce different non-zero codes and neither is the verdict. **Ask: have I seen this tool's exit code move with its findings on THIS invocation, or am I reading a number that means something else?** Read the finding list as the verdict for both, and when an exit code is quoted, quote the exact command beside it — a code from one invocation says nothing about another. See C106, C96, C57, C71 |
| **C116** **a line count reported as an occurrence count, over a file set wider than the repository** | A rename's footprint was measured with `grep -rci platonic <files>` and written into a brief as 38, 40, 79 and 45 **occurrences** across **39 tracked files**. The unit re-measured with `git grep -o -i`: **47, 49, 97 and 49 occurrences across 21 tracked files**, and the missing 18 files were an untracked second copy under `.claude/worktrees/`. **Two errors in one figure** — `-c` counts matching LINES rather than matches, so a line holding the word twice counted once; and `grep -r` walks the working directory rather than the index, so untracked scratch copies inflate the file count. **Ask: is this a count of matches or of lines, and is it over the index or the directory?** Use `git grep -o <pattern> | wc -l` for occurrences and `git grep -l` for files, both of which read the index and exclude scratch. See C26, C15, C30, C25 |
| **C117** **`ln -s` on Git Bash for Windows silently COPIES, so deleting the "link" deletes real files** | A unit tried to save a `npm install` by symlinking `node_modules` into its worktree. Git Bash cannot always create a symlink on Windows and **falls back to a real recursive copy with no error** — the result was a 292-entry directory that looked like a link and was not. Deleting it would have been deleting files, and had the path been the operator's own `node_modules` it would have removed 290 live packages including the Solidity dependencies and the web analyzers. It was caught because the unit checked the path for a reparse point before deleting. **Ask: did this command create a link, or a copy that looks like one?** Test the path — a real link reports as a reparse point and a copy does not — before any delete, and prefer `npm install` in the worktree over linking at all. See C73, C111, C63, C79 |
| **C118** **a diff taken against a file a writer has not finished writing** | A background diff of an analyzer baseline reported **all 37 findings as deletions**, because the branch-side file was still being written and read as empty. An empty file against a populated one is indistinguishable from a deliberate deletion of everything. Re-run twice to completion, the real result was one ADDED line. **Ask: is anything still writing the file I am about to compare?** Compare only after the writer has exited, and treat a diff that reports wholesale removal as a suspected race before treating it as a finding — a result that says "everything is gone" is far more often a timing fault than a change. See C16, C80, C9, C57 |
| **C121** **a name that resolves for a reason nothing declared** | A package's own entry file held **zero** import lines for two of its modules, and `hasattr` on the imported package answered **True** for both anyway. A sibling module imported from them — `conversion_rates.py:25` and `:33` — and importing a submodule binds it onto the parent package as a side effect. **A static read of the declaring file counted 10 modules absent; a runtime read counted 8.** The runtime figure looks authoritative and is the fragile one: deleting one unrelated import line unbinds a module the entry file never mentioned, with nothing reporting it. **Ask: does this name resolve because something DECLARED it, or because something else happened to touch it?** Read the declaring file for what is intended and the runtime for what is true, and when they disagree treat the declaration as the contract. A reachability result that a sibling's import can revoke is not reachability |
| **C120** **a universal claimed after looking at part of the evidence** | Two in one turn, both written into briefs a unit then built against. **"Nothing in the tree has a turn budget"**, after searching the package for the operator's new phrase `turn point`: the pool exists as `IMPETUS_AT_FIRST_LEVEL = 4` and `IMPETUS_LEVELS_PER_STEP = 20` with a grant function in `poa_modes.py`, and a loot tier field named `impetus_relief` had already been read and quoted. **"The package file re-exports every module"**, after reading the head of that file: **8 of 24 modules are absent from it**, measured by enumerating both sets. One search used a vocabulary the design does not use; one read a prefix and spoke about the whole. **Ask: did I see ALL of it, and did I search the names the DESIGN uses rather than the names I chose?** For a universal over a file, enumerate both sets and diff them; for an absence, search the design's own term before concluding a mechanism is missing. A brief carrying either becomes a unit's premise. See C30, C56, C87, C26 |
| **C119** **a figure that was measured honestly, carried forward after the thing it measured changed** | A record's size was measured at **1,015 bytes**, and a compact form at **399**, and both went into two later briefs as the cost of one action. A unit re-measured the same records: **1,305 and 478**. Nothing was wrong when taken — two units had since landed, one adding a position to every id and one adding an append log that writes each record with a content id, and an event emitter added 422 bytes of its own. **A measurement names a tree, and the tree moved.** This differs from a figure written from recall (C48, C86): the number was real, the date was not carried with it. **Ask: what landed between this measurement and now, and did any of it touch what I measured?** Quote the commit or the unit a figure was taken against, and re-measure rather than re-quote once anything has merged into that path. The conclusion here strengthened — per-turn writing costs 81.5% of the budget rather than 63.4% — but a figure that moved the other way would have been a false green. See C48, C67, C86, C22 |
| **C98** **a per-run cap mistaken for a total budget** | `-n 4` caps ONE pytest run. Nobody capped the NUMBER of concurrent runs. Measured: a background full lane at `-n 4` plus several dispatched units each running their own `-n 4` with Chromium reached **10 python processes, 5.6 GB, 76.4% RAM** on the machine running two live trading instances. Each decision was locally reasonable and the total was never computed. Stopping the lane and one unit: 6 processes, 1.0 GB, 61.5%. **Ask: how many heavy consumers will exist AT ONCE, not how parallel is each one?** Measure RAM by family BEFORE adding load, never after a complaint. Throughput on a box the operator trades from is not free, and a resource ceiling is the operator's to feel first only if the instrument never looked. **ENFORCED IN PYTHON** — `~/.claude/hooks/block_heavy_run.py` denies the call; see *Rows enforced in Python* below. See C11, C27, C50, C65 |
| **C122** **a name-set comparison across a Windows shell boundary, where no line can equal its partner** | A unit compared two name lists for collisions before adding exports to `src/competition/__init__.py`. `python -c` printed one side, a shell pipeline filtered the other, and the comparison reported **zero** collisions. Re-measured on this host: the printed name writes 16 bytes and ends in a carriage return and a newline, the same name taken from the source file with `grep -o` writes 15 bytes and ends in a newline only, and `comm -12` over the two sorted lines reports **0** matches for a name that is in both files. Strip the carriage returns off the printed side and the same comparison reports **1**. The true figure was **four** collisions, recorded in commit `fbd7421d`: ABSENT_READERS, ABSENT_READER_NOTES and FIGURE_ABSENT from world_turn, ABSENT_MECHANISMS from dungeon_entry. **Three of the four hold a different value in each module** — only FIGURE_ABSENT is None on both sides — so the zero would have replaced three working exports with three different values. **Ask: does either side of this comparison cross a Python-print to shell-filter boundary on Windows?** Strip carriage returns on both sides before comparing, and feed the comparison a name known to be in both files to prove it can report. C76 is the sibling and the inverse: there the pipe ADDS the line endings it counts, here the endings make two identical names compare unequal. See C76, C15, C31, C111 |
| **C123** **a document's subheading namespace is the whole page, not the new section** | The documentation archetype refused a write on `docs/manual/08-tabs/proof-of-accumulation.md` with one **high** finding, rule DOC005, because a new dated section reused a subheading an earlier dated section on the same page already carried. Measured with that rule's own pattern: the page holds **613** heading texts across **67** dated sections, and **12** of those headings name what is still owed, so the obvious heading for a new entry is already taken. The rule matches every heading level, folds case, and does not skip fenced blocks — **5** of the 613 are comment lines inside code fences, and the rule refuses two of those that match each other just the same. Two earlier commits on the same page carry the same repair: `585fa591` renamed a clock heading so no two headings shared text, and `edccee9a` changed a heading after the archetype reported one high finding. The page holds **0** repeated heading texts today, so every refusal held. **Ask: is this subheading already used anywhere on the page, not just in my own section?** Search the whole file for the heading text before writing it, and expect the refusal when two sections share one. See C97, C25, C56, C33 |
| **C124** **an archetype invocation given several files reports on the first and exits 0** | Measured on this host: `python -m dev_harness.harness.coding_archetype harness_fixtures/coding_archetype/known_good.py harness_fixtures/coding_archetype/known_bad.py` exits **0**, answers `passed=True`, `scanned=True` and **7** findings, and its `target` field names `known_good.py` alone. The same `known_bad.py` passed on its own exits **1**, so the second file was never opened and nothing in the JSON says so — `target` is one path, not a list. A seven-file call therefore reads as seven passes with six files unscanned, and it was reported by a unit that had just made one. **Ask: does this JSON's `target` name the file I am about to claim a verdict for?** One file per call, one JSON per file, and read `target` before quoting `passed`. See C57, C38, C30 |
| **C125** **a brief citing a fixture path the referee never listed** | My own brief told a unit to calibrate on `harness_fixtures/ta_archetype/known_good.py` and its bad partner. Measured with `ls harness_fixtures/ta_archetype/`: the directory holds **12** files and every one is per-rule — `known_good_ta001.py` through `known_good_ta011.py` and the matching bad ones — so neither cited name exists. That archetype refused to report green on the empty scan, so this instrument caught it; a wrong name that happened to exist would not have been caught, and the unit had to pick a substitute mid-run, which hands the referee's judgement to the operative. **Ask: did I list this directory, or recall it?** Run `ls` on every fixture directory a brief cites and paste the names the listing returned. See C86, C88, C67 |
| **C126** **a debugging variable a brief mandates reaches an analyzer subprocess and removes it** | Measured on this host: with `PYTHONWARNINGS=error` exported, `python -m dev_harness.harness.coding_archetype harness_fixtures/coding_archetype/known_good.py` exits **1**, answers `passed=false`, lists `unavailable_required: ["bandit"]` and records `bandit: RuntimeError: bandit exited 1 without output`. The same command with the variable unset exits **0** and reports all **11** analyzers `ok`. bandit runs as a subprocess, inherits the variable, and a warning inside its own import becomes an error. The archetype refused instead of reporting green, so the instrument held — the hazard runs the other way: a unit reads exit 1 against the file it just wrote and hunts a defect that is not there, and a unit that never calibrated loses one of eleven analyzers for every run in the job. The variable came from my own brief, which told each unit to set it in the environment. **Ask: does the shell that runs this archetype carry a variable I set for a different command?** Put a debugging variable on the driving script's own command line only, and read `unavailable_required` before reading a verdict. See C57, C125, C88 |
| **C127** **a default path bound from the home directory at import, redirected after it** | Measured with `grep -rn "Path.home()" src/competition/*.py`: **12** module-level constants in one package each resolve a default file under the operator's live `~/.acervator` AT IMPORT — `DEFAULT_LEDGER_PATH`, `DEFAULT_DUNGEON_PATH`, `DEFAULT_WORLD_PATH`, `DEFAULT_LOOT_PATH` and eight more. `QuintessenceLedger._commit` calls `save()` on every movement, so a ledger built with no explicit path writes his live file on the first movement, and a driving script that predicted it would write nothing printed `ledger path exists on disk: True`. A redirect of the home applied AFTER the import misses all twelve, because each constant already holds the resolved path. This is the mechanism behind the incident that put three files into his live runtime directory. **Ask: is the home redirected BEFORE the first import of this package, and does the redirected home read empty at the end of the run?** Redirect first, print the resolved home inside the run, pass an explicit path to every store you build, and list the redirected home afterwards. See C84, C11, C73 |
| **C128** **a place compared on fewer coordinates than name it** | `world_grid.GridPosition` carries `square_index`, `step_x` and `step_y` and **no layer**, so two positions on different layers of a twenty-layer world compare equal. A dungeon-entry check written against `GridPosition` objects would have admitted a party member standing at `1:9:50:50` into a dungeon at `0:9:50:50`; the comparison was changed to the whole locator and the refusal then drove on exactly that pair. The equality is right for the class — a position IS a square and a step — and wrong for the question, which is whether this mover stands in this place. A check of this shape reports nothing: every field it reads matches. **Ask: does the value I am comparing carry every coordinate the question needs?** Compare the locator the world uses to address a place, not the part of it that one class happens to hold. See C4, C19, C77 |
| **C129** **a sample too small to tell a coincidence from a correlation** | A unit drew a square's material and grade from two windows of that square's own hash, then checked that a second world seed draws differently. Across **64** squares the two seeds named the same material and grade on **6** of them, against **1.83** expected from 7 materials and 5 grades, which reads as a correlation and would have been reported as a broken derivation. Across **10,000** squares the same measurement read **283** against **285.71** expected. The two seeds' leaves and window values differ — 779,275,405 against 2,597,397,249 — and both leave the same remainder over seven, which is the coincidence. **Ask: how many draws does one agreement cost at this sample size, and is my sample large enough for the expected count to be more than one?** Compute the expected rate before reading the observed one, and raise the sample until the two can be told apart. See C83, C120, C48 |
| **C130** **a share that repeats in decimal, held as a decimal** | TWICE IN ONE SESSION, and the second time in money-shaped code. Renormalising a loot chart with two of five tiers cut gives shares of `220/3`, `70/3` and `10/3`: each repeats for ever, so a `Decimal` renormalisation lands NEAR one hundred and never ON it, which silently loses a tier or a slice of the span a roll is drawn from. The unit held the share as a `fractions.Fraction` and summed the whole numbers each tier already owned, and all five bands then totalled exactly `100/1`. Earlier the same shape reached the live Quintessence ledger: the transfer bleed fraction repeats, the sender was debited a hair more than held, and a full-balance transfer was IMPOSSIBLE at **4 of 10** skill levels, the ledger refusing its own write with a negative bucket, with unspendable dust left at four more. **Ask: does this share repeat, and does the total have to land exactly on its source?** Compute every share that must sum back to its source as an exact fraction, apply the grain once, at the point the value is written, and send the residue where the design says it goes. See C31, C48, C14 |
| **C131** **a draft gated outside the repo reports every real path it cites as dead** | The documentation archetype's hallucination rule resolves a cited path against the TARGET FILE's own tree, not the working directory. Measured two-sided with one control file citing a real path and a fabricated one: scanned from inside the repo it reported **1** hallucination finding, the fabricated path alone; the same bytes scanned in the session scratch directory reported **2**, calling `src/competition/vessels.py` nonexistent. The fabricated path reports in both, so the rule can fire and the difference is location. A unit drafting an issue body in scratch read **16 and 20** dead paths that all exist, and a unit that trusted that reading would have deleted good citations to clear it. I had told every unit the opposite, that resolution is against the working directory. THE MECHANISM, measured by a second unit on the same day: the rule finds a repo root by walking UP from the target file for `pyproject.toml`, or for a directory holding both `src/` and `tools/`. A scratch directory has neither above it, so the root it settles on holds no `src/`, and **76** correct citations read as dead in one run. **Ask: is there a `pyproject.toml` above the file I am scanning?** Gate a draft from a gitignored directory inside the repo, or from a git worktree, then remove the copy. See C125, C57, C30 |
| **C132** **a JavaScript verdict taken inside a git worktree** | The screen archetype runs `eslint` from the working directory, and `node_modules` sits at the MAIN repository root, never in a worktree. Measured two-sided on the archetype's own known-good screen file: inside a worktree it read **exit 1, `passed=False`, `eslint` unavailable**; the same bytes with the main tree as the working directory read **exit 0, `passed=True`**. A unit working in a worktree, which every brief orders, therefore reads a FALSE RED on good JavaScript and a false green is available the same way. **Ask: did this verdict run where `node_modules` is, and what does `tool_availability` say about `eslint`?** Take every JavaScript verdict with the main repository root as the working directory, and read `tool_availability` before `passed`. See C57, C131, C35 |
| **C133** **a 139 that arrives at shutdown, after every reading** | OCIR already says 139 is a crash that prints no summary, and that rule read alone throws away good measurements. Measured: a driver that built two embedded web pages and exited with no event loop running ended `139`, an access violation on the browser main thread with **no Python frame**, and it happened AFTER all output was printed. The same arm skipped, the same set exits 0; one page, two pages, one of each kind, a save, and a later wizard each exit 0 on the unchanged tree and on the branch. The application itself runs a loop, so the crash is the driver's and not the product's. **Ask: did the output complete before the code, and does the running program hold a loop where my driver does not?** Read the readings first, then the code; name the frame the crash reports; and run the page inside a loop or leave that arm out and say so. See C71, C70, C42 |
| **C134** **the first embedded web page a process renders carries a warm-up share** | A unit comparing four unknown theme names against the process's FIRST render read `0.9269` against `0.9223` and reported all four as different pictures. Re-rendering the KNOWN value late in the same loop gave the control: first against late `False`, a second theme early against late `True`, and the two late readings of different themes `False`. Against the late reading all four unknown names matched, which is the opposite verdict. **Reported the first way it would have been a fabricated defect in a file the unit had already repaired.** **Ask: is the picture I am comparing against the first one this process drew?** Render the known value again late in the run and compare against that, never against the opening render. See C14, C36, C50 |

---

## ROWS ENFORCED IN PYTHON

Measured: blocking hooks held at **0 violations**, injected prose at **10 of
10**. A row decidable from the command string plus machine state belongs in a
hook; a row needing judgement about the code stays prose.

| row | hook | what it refuses |
|---|---|---|
| **C98** per-run cap read as a budget | `~/.claude/hooks/block_heavy_run.py` | a heavy run above the RAM ceiling, a heavy run while another is resident, and `-n auto` outright |
| **C96** stdin through a pipe | `~/.claude/hooks/block_heredoc.py` | `\| python <script>.py`, which exits 0 without ever reading a payload |
| heredocs and `python -` | `~/.claude/hooks/block_heredoc.py` | the call, before it hangs on stdin |
| unanchored docstrings | `~/.claude/hooks/block_unanchored_docstring.py` | a NEW docstring with a justification clause, a banner heading, over the sentence cap, or a sentence naming no identifier from the file |

`block_heavy_run.py` denies with exit 2 and a reason on stderr, the same shape
`block_heredoc.py` uses:

```python
HEAVY = re.compile(r"\bpytest\b(?=.*\s-n\s)|\blocal_ci\b|check_release_readiness")
N_AUTO = re.compile(r"\s-n\s+auto\b")

RAM_CEILING_PCT = 70.0     # Acervator itself holds about 2.7 GB
PYTHON_BUDGET_MB = 2500.0  # another heavy run is already live above this

if pct >= RAM_CEILING_PCT:
    print(f"Heavy run refused: RAM is at {pct:.1f}%, ceiling {RAM_CEILING_PCT:.0f}%.",
          file=sys.stderr)
    sys.exit(2)
```

**Both directions are controlled.** Forcing the ceiling to 5% denies
(`exit=2`, *"RAM is at 60.7%, ceiling 5%"*); restored to 70% it allows, and the
file compares byte-identical afterwards. Seven command shapes were driven
through it — `-n auto` denied, and a single-file pytest, an archetype run,
`git status` and the word "auto" appearing elsewhere all allowed. Zero control
failures.

**Adding a row here is hardening and is allowed. Removing or weakening one is
not** — that comes to the operator first.

**A row qualifies for a hook when it is decidable from the command string plus
machine state.** A row needing judgement about the code stays prose.

## R10 - Write the program to a file, then run it

Never pass a program or a message through a shell heredoc. Never put a command
after one.

1. Write the file with the file-writing tool.
2. Parse it.
3. Run it and read its exit code.

A heredoc adds a quoting layer that rewrites the text (**C63**). A command after a
heredoc reports the wrong exit code (**C64**).

Commit messages, pull request bodies and issue bodies: write the file, then
`git commit -F <file>` or `--body-file <file>`.

Name scratch files for their unit (**C73**).

## R1 — Never assert a property of the machine you are on

A test states what the PRODUCT does. It never states what THIS computer has.

Fonts, screen size, path separator, drive letter, CPU count, locale, an
installed package's version, an environment variable — none of these is a fact
about the product. Asserting one is green here and red on the build machine.

Measured three times in this project. Each time the test read
`QFontDatabase.families() == []` — true on the operator's Windows laptop,
false on the Linux build machine, which ships the DejaVu family.

**Ask the machine, then check the right thing either way.** Both answers get a
live branch and both branches get proved.

When two tests need the same question answered, they import ONE helper. A
second private copy is how the third occurrence got written.

## R2 — A picture is compared old-side against new-side, and nothing else

Two renders taken on the SAME machine from the TWO sides being compared is a
sound check on every host. That is what parity means.

Painting the same side twice with one value changed, then asserting the pictures
match, is not. Whether that value is invisible depends on the host's fonts.
Measured four times in this project.

**A claim that a value is invisible to a picture is proved WITHOUT a picture** —
read the value off both sides and compare it directly.

A fixed pixel count, a fixed colour count and a fixed picture fingerprint are the
same defect wearing a number.

## R3 — Run the picture tests both ways before reporting

This host has no fonts for offscreen drawing. The build machine has 287. A green
run here is half a measurement.

Run every file holding a picture comparison twice — once with no fonts, once with
real fonts loaded into the OFFSCREEN driver. Both must pass.

Do not switch to the real Windows display driver to get fonts. Windows draws text
through its own smoothing and ignores the no-smoothing setting the picture tools
rely on, which produces a false failure about the measuring setup.

## R4 — Do not manufacture failures. Take the ones the work gives you

**Never plant defects to prove a check works.**

Measured across five conversion units: **359 defects planted, zero found a
defect in the new code.** Six of the seven that came back silent were holes in
the unit's own tests. One was a dead line in the shipped file. Every real defect
was found by comparing both sides, or by reading the shipped file.

Planting was the bulk of the cost. One unit spent 411 tool rounds, almost all
campaign.

What proves the work instead:

**Compare both sides on every value.** Drive the shipped code and the new code
together in one run. Every value, every hash. Difference zero. This is the test.

**Check the comparison is complete.** One test asserting every constant in the
new code appears in the snapshot the comparison reads. A comparison reading 40
of 50 constants passes identically whether the other 10 match or not. One check
closes that for all of them.

**Red before green comes free.** The comparison was written against the shipped
side and failed before the new side existed. Record the red, record the green.
Two-sided, nothing manufactured.

**Two real inputs are the control.** To prove a comparison can report, feed it
two genuinely different real data sets, one from each side. It costs one
comparison, proves the same thing, and breaks nothing.

**Enumerate the shipped file.** The table of every item and where it went. This
is what found the real defects.

**The archetypes and the build machine.** They author and they adjudicate.

A check nobody has watched fail is still not a check. The answer is to watch it
fail on the way to green, not to break working code so it has something to say.

## R5 — A shell command does work, or it does not run

**`echo` is not work.** A command whose only job is to announce what the next
command will do burns a round and measures nothing.

Measured on one unit: **213 of its 304 shell commands started with `echo`.**
Seventy per cent of everything it ran was narration.

Progress belongs in the final report, as a table, once. Not in the shell.

Same rule for `sleep`, for re-running a command that already answered, and for
`cd` as its own command.

## R6 — Never start a program with no input to read

**`python` with no script opens an interactive session.** In a background shell
it reads end-of-file for ever and writes tracebacks into the output.

Measured: one such shell wrote **5.4 GB** into a single file before the agent
stopped. Always `python -c` or `python file.py`.

Do not poll a background job either. Start it and wait, or run it in front.
Measured: one unit spent 40 of its 168 minutes polling.

## R7 — A timeout above two minutes is a wrong command

**No command gets a timeout above 120000 ms.** Two exceptions, capped at
300000 ms: one full run of the unit's own test file, and an archetype run.

A targeted test run finishes in seconds. A command needing more than two minutes
is running too much, not waiting too long. Narrow it.

A command that hits its timeout has answered: the command was wrong. Re-running
it with a bigger number is not a measurement, it is a stall.

Measured: agents set timeouts in the millions. 3000000 ms is fifty minutes
blocked on one command.

## R8 — Report size against time, every unit

Drift shows in the ratio before it shows in the work. State four numbers at the
end of every unit:

| number | how |
|---|---|
| source lines in | `wc -l` of the file you were given |
| lines produced | surface + test |
| minutes spent | wall clock, start to report |
| tool rounds | count of commands run |
| test lines per source line | produced test / source in |

**Read them against the run before.** A ratio climbing unit over unit is the
signal — not the absolute number.

Measured on this project's conversion units:

| unit | source in | produced | minutes | test per source |
|---|---|---|---|---|
| start all progress | 233 | 2167 | 47 | 7.3 |
| buy confirmation | 276 | 2733 | 88 | 7.6 |
| instance consent | 286 | 3354 | 47 | 9.4 |

Two things visible here and in nothing else: buy confirmation took **twice the
minutes for the same size** — it ran a whole test file per planted defect
instead of the tests covering that defect. And test lines per source line is
climbing across a set of near-identical files, which is proof growing for its
own sake, not for the product.

**A unit far off its neighbours' ratio stops and says so before continuing.**

## Every archetype finding becomes a row

The archetype is the harness. When it rejects your work, that is the most
authoritative signal in the run — more authoritative than any check you wrote.

**A finding that made you rewrite anything goes into the catalogue.** Name the
tool, the finding, and what you changed. If the shape is already a row, cite the
id and say so — a row cited repeatedly is a rule that is not landing.

Measured: the GUI archetype has rejected **reading a colour off a live widget
instead of off a rendered picture** on at least six separate units. Six agents
each met it fresh, each called it "a finding", each fixed it, and none of them
could see it was the sixth time. That is C50, and it should have been a row after
the second.

**Report `passed`, never a delta — and never call a finding a false positive.**
You have no standing to. When it fails your work, you change your code.

## R9 — every unit answers: what does the operator SEE differently

Every rule above checks whether the work is correct **against its own brief**.
None of them asks whether the brief was the right thing to build. That gap ran
for thirty-nine files before a human closed it.

**End every unit report with one line: what the operator sees differently today
because of this unit.** "Nothing yet" is a correct and acceptable answer — it is
only dangerous unsaid.

**Every tenth unit, the referee states it for the whole run**, in the operator's
own terms, before any other number. Not files converted. Not tests passing. What
is different on his screen.

Measured: 39 units reported green, every archetype passed, CI passed, the
catalogue grew — and the answer to this question was "nothing" the whole time.
The work was real and the reporting was true. The question was simply never
asked.

A green gate proves the work matches the brief. **It never proves the brief was
worth building.** That question has no instrument. It has to be asked out loud.

## Cite the entry, and add one when you find a new shape

Every rule above carries an id — **R1** to **R9**. Every catalogue row carries
one — **C1** to **C37**.

**When you report a defect you found, or a check of your own you had to fix,
name the id.** "Fixed a blind check" says nothing. "C21 — my guard asked whether
the run loaded a font, not whether the machine has one" says what happened, what
it belongs to, and whether it has happened before.

**When the shape is not on the list, say so and write the new row.** Give it the
next free number, one line for the shape and one for how it hides. A shape found
twice under two names is a shape nobody can count.

The point is the count. A row cited three times is a rule that is not landing,
and that is a defect in the rule, not in the person who tripped on it.

## The referee's own numbers get the same rules

A count reported to the operator is a measurement like any other. Every rule
here binds it.

Measured: a progress count of "41 remaining" was wrong because the matcher
looked for `<name>_surface.py` and eight surfaces are named for a different
source — `live_status_tab_surface` from `status_tab.py`, `history_surface` from
another folder. **C25.** The true figure was 31, and the operator caught it by
adding two numbers that should have summed to a total he remembered.

Before reporting a count: state the method, and check the parts sum to the whole
you already know. A total that has drifted is the instrument, not the tree.

## Before reporting

Say how it was measured. If the method cannot be stated, the number is not a
measurement.

## A form instruction answered with prose about the form

An instruction that names a **shape** is not satisfied by prose describing that
shape. The operator asked for "narrative blocks paired with code blocks and
functional description paired design intention". What came back was a paragraph
running eight inline code spans together — `IntervalGate`, `ScrummingBot.tick`,
`TrendHoldGate`, `fold_hold_in_downtrend` — inside continuous sentences. Every
symbol was correct. The form was absent.

**A dense inline-citation paragraph reads as machine output to a human**, however
well grounded it is. The operator's words: a normal reader will see it and scream
AI slop. Accuracy does not rescue a shape nobody wants to read, and a manual that
looks generated will not be trusted by the people it is written for.

**Inline citation is not a code block.** A paragraph carrying more than about two
inline spans has substituted density for structure, and a reader cannot tell at a
glance whether the code exists.

The counter, and it is cheap: after a narrative, put a block. Exactly one of

```
a code block of real code                when the thing is built
a PROPOSED code block, marked proposed   when it is not
the sentence "In development."           when there is nothing to propose
```

A proposal is a legitimate manual artefact. It records the fact and specifies the
next build in the same passage, so an absence becomes a design rather than an
apology.

Measured on this session: the substitution survived a Docs Archetype `passed`, a
`docs_archetype` fixture control, and a subsequence proof, because none of those
instruments reads for shape. **A gate that checks truth does not check form.**
When the operator names a form, the check is a count — inline spans per
paragraph, and a block present after each narrative.

Related, same root: a rule stated in prose does not bind, while a hook that
refuses a dispatch without the clause does. This session shipped three false
refusals from that hook before it was right, and each blocked correct work, which
is the mirror defect and costs the same.

## Intent written as action, and the apology that repeats it

A sentence in the present continuous — "dispatching", "I'm running", "next up" —
reads to the operator as a thing that happened. When the turn ends without the
call, the report was false.

**Counted this session: three times.** Once claiming an audit unit was running
when the last had merged and none replaced it; twice claiming a dispatch inside
the same message that ended without one. The operator caught all three.

The second count is the one that matters. **The apology recurred with the
error.** "I wrote intent as if it were action, again" was written, and the next
turn did the same thing. An acknowledgement that does not change the order of
operations is not a correction; it is the same defect with better manners.

The counter is mechanical and costs nothing:

```
make the call, read the result, then write the sentence
```

A dispatch is reported only after the tool returns an id. A count of running
units comes from `ListAgents`, never from memory of what was sent. If a turn ends
with work intended but not dispatched, the honest sentence is "not dispatched",
not "dispatching".

This is the same root as reporting a measurement before the instrument ran, and
the same root as reporting a green from a control that never fired. **The
ordering is the rule: act, observe, then speak.** Every other row here is a
special case of it.

A recurrence is a defect in the rule, not in the attention. This row exists
because the rule was prose and prose did not bind. Where a check is possible it
is written; where it is not, the count is kept, and a row cited three times is a
rule that needs a different shape.

## C90 — a style rule stays prose, so it comes back

The density rule was written, catalogued, put in a skill and read aloud to
three units. It was cited three separate times by the operator, each time as a
fresh regression, and each time the reply was an apology and a rewrite of the
passages he had spotted himself.

The measurement that was missing:

```
density_gate.py <tree>    one unit per paragraph or bullet
                          tables skipped, fenced blocks skipped
                          exit 1 while any unit carries three or more spans
```

**CITED AS ABSENT, measured 2026-09-10: `density_gate.py` is NOT in the tree.**
`git ls-files` matching that name returns nothing. The figures below were taken
when it existed; the instrument behind them is gone, so the density rule is once
again prose with no check — which is this row's own subject arriving a second
time. **The row now reads as its own open finding rather than a closed one.**
A unit reporting a density count today is counting by hand.

First run, when it existed: 2,137 prose units, 42 over. None of them had been
named by anybody. The operator was finding them by reading, which is the whole
reason he kept seeing the same defect after it was fixed.

The earlier instrument counted a markdown table as one dense unit, so the real
number sat under 47 rows of table noise. An instrument that reports a true
total in an unreadable shape is not a working instrument.

The rule generalises past this manual. **A rule about form is enforced by a
count or it is not enforced.** Truth gates do not read for shape: a passage can
carry a `passed` from every archetype, a fixture control and a token proof, and
still be unreadable. Where a form is specified, write the counter in the same
turn the form is specified, and give it a control that fails.

A rule cited three times is not an attention failure. It is a rule in the wrong
shape.

## C91 — a control token published into the thing it measures

The crumb check proves no sentence of the operator has been lost. Its control
plants a token that cannot be in the manual and asks whether the check reports
it short. For weeks the answer was yes.

Then a unit needed a negative control of its own for a git pickaxe, took the
sentinel out of the instrument, and published the result into the manual. From
that commit onward the planted token WAS in the manual, so the control answered
no, and the check reported a clean five with no ability to report anything else.

It was caught by accident. A sibling unit measured the same property against a
different baseline and got fifteen. Chasing the disagreement is what surfaced
the dead control; the disagreement itself was innocent, two different source
sets, and the real defect was underneath it.

Three rules come out of this:

```
a sentinel is generated per run, never a literal
a control that reports no is louder than a check that reports zero
never publish a token taken out of an instrument
```

The second one is the general case. **A control has two failure modes and only
one of them is loud.** A control that fires proves the instrument works. A
control that stops firing looks exactly like a quiet green unless its own output
is read every time. Print the control result beside the count, always, and read
it before reading the count.

The same run also carried a second control that printed yes while the number it
was supposed to move did not move. It cut one copy of a common token from a
manual that held many, so the deficit stayed put and the wording claimed
success. **A control must cut something at parity** — where one fewer is
immediately one short. A control that cannot change the answer is decoration.

## C92 — a suppression dead to one linter and alive to another

A brief told units that `# noqa: E402` is the known-inert case, on the evidence
that the project flake8 config ignores E402 globally. The reasoning was sound
and the conclusion was wrong.

Two units measured it independently, in different buckets, on different files:
removing the directive raises E402 findings that are not in the baseline,
because the archetype runs its own ruff with its own rule set. flake8 exits 0
either way. That is exactly what makes the case dangerous — the tool a person
reaches for to check reports no difference, so the directive looks like dead
weight worth deleting.

```
flake8 with the directive      exit 0
flake8 without it              exit 0     <- the trap
archetype without it           new rule ids, passed=False
```

The general rule is stronger than the E402 case. **A green from one tool says
nothing about another tool rule set.** Two linters over one file are two
instruments, not one, and they do not agree on which rules exist. A suppression
is live or dead only with respect to a named tool, and the only tool that
matters here is the one the gate runs.

The proof stays what it was: delete the directive, re-run the ARCHETYPE, compare
rule ids against the baseline. Never substitute a friendlier tool for the gate.
That is the same error as running a gentler pytest invocation than the release
gate and calling the result a pass.

The brief carried the wrong claim for the length of a sweep. A rule written into
a brief propagates to every unit that reads it, so a wrong one is worse than no
rule at all: it manufactures confident, uniform, wrong work. When a unit
contradicts the brief with a measurement, the brief is what gets corrected, in
the same turn, before the next dispatch.

## C93 — a guard pattern that reads the whole command line

Two hooks refused correct work this session, and both had the same shape: a
regex written to spot one thing, applied to a string that carries many things.

The heavy-run guard refuses a parallel pytest. Its pattern was
`\bpytest\b(?=.*\s-n\s)` — a lookahead that scans the rest of the command
line. A compound line that ran a serial pytest and then a `sed -n` matched, and
a unit sat blocked for twenty minutes on a run that was never parallel.

The dispatch guard refuses a manual brief with no protection clause. It matched
any mention of the manual path, so a brief that named those files only to
forbid them was refused as a manual brief.

The fix in both cases is to bound the match to the segment that owns it:

```
pytest ... -n     must sit in ONE command segment    [^;&|]*
a manual path     must be assigned, not excluded     drop exclusion clauses
```

A guard has two failure modes and the loud one is not the dangerous one. Letting
a bad call through is visible later. **Refusing a good call is invisible except
as lost time**, and it teaches whoever hit it to route around the guard, which
is worse than not having it.

A guard needs a two-sided probe like any other instrument: a table of
commands it MUST refuse and commands it MUST NOT, run against the shipped
pattern rather than a copy. The probe written here reports both counts, so a
pattern edited into uselessness fails the same table that catches a pattern
edited into over-reach. Narrowing without that table is indistinguishable from
deleting the guard.

## C94 — a file list read as a boundary on responsibility

Units are given a file list so two of them do not edit one file at once. Four
separate units met the same failing test, and each wrote a careful paragraph
saying it was outside their list. Every paragraph was accurate. The test stayed
red through all four.

One unit went further and wrote the reasoning into a shipped document — a page
the operator reads now carries a sentence about what a unit did not do.

The operator: *"If you find it, you fix it. You own everything."*

The list answers WHERE TO START. It never answers where to stop. A defect found
inside a unit belongs to that unit, and the two real carve-outs are the
operators own standing rules — the harness, which only he may weaken, and a fix
that would change what a number he reads means. Both are handed UP with enough
detail to act on without rediscovery. Neither is a place to leave something.

The referees share is the larger one. **A defect reported and not dispatched is
the referees defect, not the units.** Four reports naming one red test is four
chances taken and missed. The rule for me:

```
a unit names something it could not take   ->  dispatch it THAT TURN
the same thing named twice                ->  the miss is already mine
```

And the tell to watch for in a report is the heading "things I did not fix". It
reads as diligence. It is a queue nobody owns.
