# Which OCIR rows are cases

Reference. This page lists every row of the OCIR catalogue and says whether it
is a case for [the OCIR cases](ocir-cases.md). It is part of
[the sigil project](../16-sigil-project.md).

The catalogue is `dev_harness/skills/ocir/SKILL.md`. It holds 154 rows in the
table under "The catalogue — checks that could not fail", 2 rows in the table
under "ROWS ENFORCED IN PYTHON", and 15 sections from C90 to C104 that give an
id a second shape. That is 171 entries.

## The test

An entry is a case when all three of these are true:

```
shape    it names a code shape: Python code that was wrong, not a measurement,
         a shell command, a habit of work, or a document
place    the entry, or a commit message in git log, names the file or the commit
fix      one commit changed that code, so a before and an after exist in git
```

For each entry that names a code shape and no file, the messages of all 3,865
commits in the history of `788e1401` were searched for the entry's own words.
"None found" means that search named no commit.

## The catalogue table

| Row | Case | Reason |
| --- | ---- | ------ |
| C1 | yes | `416b614a`: `src/trading/scrumming_bot.py` passed one expression as both its actual and its expected value |
| C2 | no | a check that types a value in place of reading it; none found |
| C3 | no | a check keyed on position; none found |
| C4 | no | a check that compares types; none found |
| C5 | no | the tests that read their own source were deleted in `05449360`, so no after code exists |
| C6 | no | a colour check; none found |
| C7 | yes | `a17b274a`: a test read caplog, which this project's loggers never reach |
| C8 | no | a row count; none found |
| C9 | no | a check a later step overwrites; none found |
| C10 | no | a measuring script, not code in the tree |
| C11 | yes | `3ec415d1`: a test asserted that the host has no fonts |
| C12 | no | a pixel check; none found |
| C13 | no | a method that logs a removal it did not make; none found |
| C14 | no | a picture comparison; none found |
| C15 | no | a shell command |
| C16 | no | a wait between runs, a habit of work |
| C17 | no | a check driven with one input on both sides; none found |
| C18 | no | a planted defect in a measurement |
| C19 | no | a field order check; none found |
| C20 | yes | `864f9ac5`: six fields were built on a group box the window then dropped |
| C21 | no | a check of a size read back from the toolkit; none found |
| C22 | no | a control in a picture comparison |
| C23 | no | a font guard; none found |
| C24 | no | a test that depends on the order of the run; none found |
| C25 | no | a file named without its path, a habit of work |
| C26 | no | a shell count |
| C27 | no | a measurement of text width |
| C28 | no | a reset of declared keys; none found |
| C29 | no | a check of a refusal message; none found |
| C30 | no | a shell count |
| C31 | no | a whole number compared with a decimal; none found |
| C32 | no | a not-a-number value compared with itself; none found |
| C33 | no | a count by text |
| C34 | no | a style sheet that selects by class name; none found |
| C35 | no | the packages a host installs, not code |
| C36 | no | a value that depends on when it was asked for; none found |
| C37 | no | a picture of a browser window, a measurement |
| C38 | no | a recorder around a helper that drives both sides; none found |
| C39 | no | a reset of a name the module does not hold; none found |
| C40 | no | a reader that gives two absences one value; none found |
| C41 | no | a step driven through a call that hides its failure; none found |
| C42 | no | a thread that outlives its window; none found |
| C43 | no | a test runner's report, a measurement |
| C44 | no | a guarded call used outside its guard; none found |
| C45 | no | a count by text |
| C46 | no | an order set by which worker finished first; none found |
| C47 | yes | `78dbb615`: a bare expression threw its value away in `src/trading/scrumming/execution.py` |
| C48 | no | a constant written from memory; none found |
| C49 | no | a recorder that overrides a toolkit method; none found |
| C50 | no | a colour read off a live widget; none found |
| C51 | no | a stand-in argument a test never reads; none found |
| C52 | no | an unreachable branch inside an assertion; none found |
| C53 | no | a test window with no accessible name; none found |
| C54 | yes | `0f951fe3`: `tools/exchange_diagnostic.py` set a name a scanner reads as a password to an empty string |
| C55 | no | a handler that names the wrong operation; none found |
| C56 | no | a search filter, a habit of work |
| C57 | no | a gate run, a measurement |
| C58 | no | a sanitiser on the wrong field; none found |
| C59 | no | a list of known findings keyed on a line number; none found |
| C60 | yes | `ae9d147a`: a test asserted that one import sits next to another |
| C61 | yes | `16162214`: a fallback for a missing toolkit bound some of its names and not others |
| C62 | no | a merge tool run on a conflict, not code in the tree |
| C63 | no | a shell command |
| C64 | no | a shell command |
| C65 | no | a surrounding cost used as a control; none found |
| C66 | no | a control in a picture comparison |
| C67 | no | a measurement carried into a brief, a habit of work |
| C68 | no | a measuring counter, a measurement |
| C69 | no | a repair aimed at the named test, a habit of work |
| C70 | no | how the toolkit and the test runner report one refusal, not code |
| C71 | no | a shell report |
| C72 | no | a table sized before it is filled; none found |
| C73 | no | a scratch file name, a habit of work |
| C74 | yes | `a5b664f6`: a suppression comment sat on the closing line of a wrapped except clause |
| C75 | no | a check by class name in a shared register; none found |
| C76 | no | a shell count |
| C77 | no | a value found by the name that carries it, in a conversion; none found |
| C78 | no | brief words in a shipped comment; none found |
| C79 | no | a Windows error a retry does not catch; none found |
| C80 | yes | `9830d60f`: a test rewrote a shipped module in two steps while a page could read it |
| C81 | no | a page element with no name to read back; none found |
| C82 | no | a brief, a habit of work |
| C83 | no | a brief, a habit of work |
| C84 | no | a rendered picture, a measurement |
| C85 | no | a style walk in a sweep, a measurement |
| C86 | no | a brief, a habit of work |
| C87 | no | a typed list of files, a habit of work |
| C88 | no | a brief, a habit of work |
| C89 | no | a search method, a habit of work |
| C90 | no | a report while a seat is free, a habit of work |
| C91 | no | how a ban reaches a session, a habit of work |
| C92 | no | a present-tense command, a habit of work |
| C93 | no | a brief, a habit of work |
| C94 | no | a brief, a habit of work |
| C95 | no | a pasted export, a habit of work |
| C96 | no | an exit code read through a pipe, a shell command |
| C97 | no | a file added beside a register, a habit of work |
| C98 | no | a cap per run, a habit of work |
| C99 | no | a call scan, a measurement |
| C100 | no | a reading of a suppression, a measurement |
| C101 | no | a private instrument, a habit of work |
| C102 | no | a check written again by hand, a habit of work |
| C103 | no | a sample reported as the whole, a habit of work |
| C104 | no | a lighter tool after a guard, a habit of work |
| C105 | no | a brief, a habit of work |
| C106 | no | an exit code read as a verdict, a measurement |
| C107 | no | a search across a naming boundary, a habit of work |
| C108 | no | a picture comparison, a measurement |
| C109 | no | a skill named and not loaded, a habit of work |
| C110 | no | a cached build artifact, a measurement |
| C111 | no | a shell file call |
| C112 | no | a brief, a habit of work |
| C113 | no | a skill copy, a habit of work |
| C114 | no | a control design, a measurement |
| C115 | no | an analyzer's exit code, a measurement |
| C116 | no | a shell count |
| C117 | no | a shell link |
| C118 | no | a diff taken while a file is written, a measurement |
| C119 | no | a figure carried forward, a measurement |
| C120 | no | a claim made after part of the evidence, a habit of work |
| C121 | no | a reading of a package's exports; no commit changes the entry file for it |
| C122 | no | a shell comparison |
| C123 | no | a heading in a manual page, a document |
| C124 | no | an archetype run on several files, a shell command |
| C125 | no | a brief, a habit of work |
| C126 | no | an environment variable, a shell setting |
| C127 | no | still in `src/competition` at `788e1401`, such as `DEFAULT_LEDGER_PATH`; no commit fixes it |
| C128 | no | never in a commit: `8bcf34e6` wrote the whole-locator check first |
| C129 | no | a sample size, a measurement |
| C130 | yes | `d20f5039`: a transfer held a repeating share as a decimal and debited more than the sender held |
| C131 | no | a draft gated outside the repository, a measurement |
| C132 | no | a verdict taken inside a worktree, a measurement |
| C133 | no | a crash at shutdown, a measurement |
| C134 | no | a first rendered page, a measurement |
| C135 | no | a branch behind its base, a shell command |
| C136 | no | a breakpoint, a habit of work |
| C137 | no | never in a commit: only the catalogue commit `cbbf13c9` names it |
| C138 | no | a channel no session reads, a habit of work |
| C139 | no | a search of a file that names no package, a shell command |
| C140 | no | a runtime log, a measurement |
| C141 | no | a merged capture of two streams, a shell command |
| C142 | no | a claim given to a merge, a habit of work |
| C143 | yes | `ca642b7d`: a tie-break took the first sector by name |
| C144 | yes | `ca642b7d`: a docstring named a case the code answered wrongly |
| C145 | no | how a filter was checked, a measurement |
| C146 | no | a build number, a shell command |
| C147 | no | a dispatch before a merge, a habit of work |
| C148 | no | a retry loop, a habit of work |
| C149 | yes | `4a32f604`: two buttons kept a fixed height after their row grew |
| C150 | no | a narrowed tool run, a shell command |
| C151 | yes | `1bfab86f`: a bulk read waited on a queue depth that almost never held |
| C152 | yes | `ccc8ea8f`: a venue dropdown stayed beside the venue buttons that replaced it |
| C153 | no | a claim about what a gate runs, a habit of work |
| C154 | no | a step after the gate, a habit of work |

## The rows enforced in Python

| Row | Case | Reason |
| --- | ---- | ------ |
| C98 | no | the hook row refuses a heavy shell command |
| C96 | no | the hook row refuses a pipe into Python, a shell command |

## The sections below the table

| Section | Case | Reason |
| ------- | ---- | ------ |
| C90 | no | a style rule kept as prose, a habit of work |
| C91 | no | a control token in the thing it measures, a measurement |
| C92 | no | a suppression read by two linters, a measurement |
| C93 | no | `dev_harness/hooks/block_heavy_run.py` entered the tree in `05449360` already bound to one command segment, so no commit holds the earlier pattern |
| C94 | no | a file list read as a boundary, a habit of work |
| C95 | no | a saved file read as the code, a measurement |
| C96 | no | an issue body quoted as current, a habit of work |
| C97 | no | a size priced by name, a measurement |
| C98 | no | a report's prose read as a reading, a habit of work |
| C99 | no | a dependency declaration, not Python code |
| C100 | no | a dependency declaration, not Python code |
| C101 | no | a folder listing of a build, a measurement |
| C102 | no | a draft gated outside the repository, a measurement |
| C103 | no | a cause read from the source, a habit of work |
| C104 | no | a count off a cut listing, a shell command |

## The count

| Part | Entries | Cases |
| ---- | ------- | ----- |
| the catalogue table | 154 | 16 |
| the rows enforced in Python | 2 | 0 |
| the sections C90 to C104 | 15 | 0 |
| all | 171 | 16 |

C143 and C144 share one commit, one file and one symbol, so the 16 rows are 15
restored pairs.
