---
name: reachability-first
description: Load before reading, evaluating, testing, documenting or repairing any file. Establishes whether the running program reaches it, before any effort is spent on it. Invoke by name when the task mentions a file, a module, an audit, a sweep, or dead code.
---

# Reachability first

**Before a file is read, evaluated, tested, documented or repaired, establish
that the running program reaches it.** If nothing reaches it, it is not work.

Operator, 2026-09-06: *"Deprecated file and deprecated tests with old usage /
access dates that you are not checking. Learn to fucking check. Sick of this.
Tired of seeing them get evaluated or looked at."*

## The check, before the work

```
1  Does an entry point reach it?     import closure from the real entry points
2  Does anything construct it?       a class nothing builds is not a screen
3  When did it last change?          git log -1 on the path
4  What cites it?                    tests, documents, tooling — and only those?
```

**A file reached only by its own test and a document is dead.** That pair is the
signature: a test written to pin it, a document describing it, and no consumer.
The test keeps it green and the document keeps it looking intentional.

## Decide by import closure, never by name

A filename is a guess. `splash_screen.py` sounds peripheral and runs before the
window; `investor_screen.py` sounds live and nothing builds it.

Walk the imports from the real entry points and see what is reachable. Say what
you ran. **A guess dressed as a verdict has cost this project a repair on a file
nobody runs more than once.**

## What follows from the answer

| reached | do the work |
| not reached | **quarantine it**, then report — see below |
| not reached, and he named it | delete it, its tests, and every reference |

## Quarantine before deletion

An unused file is moved out of the way first, and deleted only after nothing
breaks without it. That order is his, and it is the safe one.

```
1  move the file to the quarantine directory, tracked, in one commit
2  remove the references that would break — tests that only pin it, cited paths
3  run the entry points under python -X dev -X faulthandler
4  run the canon checks that name the symbols involved
5  nothing broke — it stays quarantined until he calls for deletion
6  something broke — it was reachable after all, restore it and say what ran it
```

Step 5 is the whole point. A quarantined file is recoverable by a revert; a
deleted one costs a search through history.

**Never delete on your own reading.** A wrongly deleted file is far worse than a
quarantined one. Deletion is his call unless he has already named the file.

## This applies to effort, not just to edits

The cost is not only the repair. It is the reading, the archetype run, the
manual section, the row in a table, the paragraph in a report — every one spent
on something nobody executes, and every one reaching him as noise.

**An audit that sweeps a whole tree runs this check first and reports its
denominator.** "Forty-one findings" means nothing if eleven files are dead.

## Falsification

This skill is wrong if a file it calls unreachable turns out to run. Then the
import closure was walked from the wrong entry points — name them and walk it
again.
