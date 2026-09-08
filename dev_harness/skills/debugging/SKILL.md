---
name: debugging
description: Load after every code edit and whenever software throws. The standard five-step debugging process — reproduce, diagnose, fix, verify, document — run with a real debugger on real program errors. Invoke by name when the task mentions an error, a crash, a traceback, or a bug.
---

# Debugging

**Code is written. It is run. It throws. The error is diagnosed, corrected, and
run again.** That is the whole discipline, and it belongs to no subsystem.

## The five steps

The industry-standard process, in order. Every step is mandatory and none is
optional for a small error.

```
1  REPRODUCE   run it and make the error happen again, consistently
2  DIAGNOSE    locate the line and the reason — the root cause, not the symptom
3  FIX         change the cause
4  VERIFY      run the original scenario again, and check for side effects
5  DOCUMENT    what threw, why, what changed, what it prints now
```

**A bug that cannot be reproduced cannot be debugged.** Step 1 is not a
formality; if the error is intermittent, the first work is making it reliable.

**Step 2 is where the discipline lives.** The message names where the program
noticed, not where it went wrong. Step until the two are the same place.

## A program error is the developer's defect

A program error is a fault in the software, written by whoever wrote it. It is
found by running the program.

**Never induce one.** Making working code fail to see whether something notices
proves only that you can break code. The tree already has real errors; work
those. Inducing a fault is defensible only when building a brand-new instrument
that has no real failure available to prove it — and then it is stated plainly,
never presented as debugging.

## The tools are standard. Use them.

Nothing here is invented for this project, and no wrapper around them should be.

```
python -X dev                runtime checks the interpreter already has
python -X faulthandler       a traceback on a hard crash
PYTHONWARNINGS=error         a warning becomes a traceback with a stack
pdb, debugpy                 stepping, breakpoints, post-mortem
the program's own logging    what it already reports about itself
a runtime's console channel  exceptions from code the host is running
a toolkit's message handler  the diagnostics that toolkit already emits
```

**Post-mortem is the cheapest first move.** Run it, let it throw, inspect the
frames where it died. Reach for a breakpoint when post-mortem is not enough.

## The debug report

One section per error, in the standard shape:

```
the error         the exact message and stack, quoted from the run
reproduction      the command, the environment, the entry point
the cause         the module and symbol, and why it is wrong
the correction     what changed, and why that is the cause not a symptom
the rerun         the same command afterwards, and what it prints now
```

Written plainly. An error is a program error, a traceback is a traceback, a fix
is a fix. No coined vocabulary.

## What this is not

**Not a test.** A test asserts an expectation you wrote. A debugger reports what
the program actually did. Running the program and reading what it throws is the
evidence; a passing assertion about it is not.

**Not an instrument to build.** Wrapping standard tools in a bespoke rig
replaces a trusted, documented process with an unreviewed one. Run the tools.

**Not scoped to any subsystem.** It applies to every file: engine, connectors,
maths, state, tooling, screens, the harness itself. **A name, a check, a fixture
or a finding message that only makes sense for one feature is wrong** — if it
would read oddly for a different module, rename it.

## Falsification

This skill is wrong if a defect is corrected without the program having been run
and its error read. Then the fix rests on inference, and the cause was never
located.

Sources:
- [What is debugging? — IBM](https://www.ibm.com/think/topics/debugging)
- [Debugging: Process, Techniques, Tools and Examples — Bugfender](https://bugfender.com/blog/debugging/)
- [Debugging in software development explained — Tricentis](https://www.tricentis.com/learn/debugging)
