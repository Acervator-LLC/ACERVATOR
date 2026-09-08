---
name: no-detours
description: Load at the start of every unit. Bans building a tool, a workaround, or an intermediary reading step between the issue and the work. Invoke by name when the operator says detour, workaround, tool, or unnecessary step.
---

# No detours

**The action originates off the issue. The skills and the harness load. The work
proceeds.** Nothing goes between those.

Operator, 2026-09-06: *"BAN THE CREATION OF TOOLS AND OTHER UNNEEDED STEPS.
ACTIONS MUST ORIGINATE OFF THE ISSUE. BAN YOURSELF FROM CREATING DETOURS AND
WORK AROUNDS OR UNNECESSARY INTERMEDIARY FILE READING STEPS."*

## The shape of a unit

```
1  load the skills, by name
2  read the issue, and the manual page it names
3  do the work
4  run the archetype that owns the file
5  report
```

**Five steps. Anything inserted between them is a detour.**

## What a detour looks like

Each of these was built here, and each cost more than the work it served:

| the detour | what it was for | why it was wrong |
|---|---|---|
| a path finder | locating the harness | the manual states the path |
| a notes file of standing rules | telling units the rules | the skills are the rules |
| a migration script | copying the harness elsewhere | one home, no copying |
| a source-shape test | proving code has a shape | the debugger reports behaviour |

**They share one shape: a thing written to make it possible to do the thing.**
The work was always reachable directly.

## The bans

- **No new tool.** If a task seems to need one, the task is being approached
  sideways. Run a program someone else maintains, by its official name.
- **No intermediary reading step.** A unit reads the issue, the manual and its
  skills. A file written to be read on the way to the work is a detour, and it
  drifts.
- **No workaround.** When something blocks, name the block and stop. A path
  around it is a second system, and now two things can be wrong.
- **No re-deriving what the manual states.** Code that computes an answer the
  manual already gives creates a competitor, and one of the two will be silently
  wrong.

## The test, before writing any file

> **Is this file the work, or is it something that makes the work possible?**

The second kind does not get written. Say what is missing and stop — that is a
proposed rule for him, and his to decide.

## Falsification

This skill is wrong if a unit cannot proceed without a file that is not the work
itself. Then say exactly what is missing and why nothing already installed can
supply it, and stop.
